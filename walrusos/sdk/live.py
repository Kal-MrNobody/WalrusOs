"""
WalrusOS High-Level SDK — End-to-End Real Integration.

This module wires together the real Walrus and Sui adapters into
the clean developer API:

    from walrusos.sdk.live import WalrusOS

    os = WalrusOS()
    os.login()
    workspace = os.workspace("my-project")
    agent     = workspace.agent("Research")
    stream    = workspace.stream("papers")
    stream.grant(agent, permissions=["read", "append"])
    agent.publish(stream, "Hello from WalrusOS!")
    messages = agent.read(stream)

Every call is real:
  - Workspaces and agents are Sui objects on testnet
  - Blobs are stored on Walrus testnet
  - Events are anchored on Sui with transaction digests
  - Ed25519 signatures are generated and verified
"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

EXPLORER_BASE = "https://suiexplorer.com"
WALRUS_AGG = "https://aggregator.walrus-testnet.walrus.space"
DB_DIR = Path.home() / ".walrusos"
DB_PATH = DB_DIR / "walrusos_live.db"

PERM_READ = 1
PERM_APPEND = 2
PERM_REVIEW = 4
PERM_PUBLISH = 8
PERM_MAP = {"read": PERM_READ, "append": PERM_APPEND, "review": PERM_REVIEW, "publish": PERM_PUBLISH}


# ── Exceptions ────────────────────────────────────────────────────────────────


class LoginError(Exception):
    """Raised when Sui wallet login fails."""


class PermissionDeniedError(Exception):
    """Raised when an agent lacks permission for an operation."""


class TamperedMemoryError(Exception):
    """Raised when a downloaded event fails hash or signature verification."""


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class PublishResult:
    event_id: str
    blob_id: str
    tx_digest: str
    walrus_url: str
    sui_url: str


@dataclass
class MemoryMessage:
    content: str
    agent_name: str
    agent_id: str
    timestamp: str
    blob_id: str
    tx_digest: str
    verified: bool = True


# ── SQLite Schema ─────────────────────────────────────────────────────────────


def _init_db(db_path: str) -> sqlite3.Connection:
    """Create the live SDK database tables."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS workspaces (
            name TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            tx_digest TEXT
        );
        CREATE TABLE IF NOT EXISTS agents (
            name TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            public_key BLOB NOT NULL,
            private_key BLOB NOT NULL,
            tx_digest TEXT,
            PRIMARY KEY (name, workspace_id)
        );
        CREATE TABLE IF NOT EXISTS streams (
            name TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            stream_id TEXT NOT NULL,
            PRIMARY KEY (name, workspace_id)
        );
        CREATE TABLE IF NOT EXISTS capabilities (
            capability_id TEXT PRIMARY KEY,
            stream_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            bitmask INTEGER NOT NULL,
            tx_digest TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            stream_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            blob_id TEXT NOT NULL,
            tx_digest TEXT,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            hash TEXT NOT NULL,
            signature BLOB NOT NULL
        );
    """)
    conn.commit()
    return conn


# Persistent event loop for sync->async bridge.
# asyncio.run() closes the loop after each call, which breaks httpx's
# connection pool on subsequent calls. We keep a single loop alive.
_LOOP: Optional[asyncio.AbstractEventLoop] = None


def _run(coro):
    """Run an async coroutine from synchronous code using a persistent loop."""
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


# ── Helpers ───────────────────────────────────────────────────────────────


def _uuid_to_sui_address(u: str) -> str:
    """Convert a UUID string into a 0x-prefixed 32-byte Sui address.
    
    We derive a deterministic address by SHA-256 hashing the UUID bytes,
    so the same stream name always maps to the same on-chain address.
    """
    raw = hashlib.sha256(u.encode("utf-8")).hexdigest()
    return "0x" + raw


# ── Stream ────────────────────────────────────────────────────────────────────


class Stream:
    """A named event stream within a workspace."""

    def __init__(self, name: str, stream_id: str, workspace_id: str, db: sqlite3.Connection, sui) -> None:
        self.name = name
        self.stream_id = stream_id
        self.workspace_id = workspace_id
        # Derive a Sui-compatible address from the stream UUID
        self.sui_address = _uuid_to_sui_address(stream_id)
        self._db = db
        self._sui = sui

    def grant(self, agent: "Agent", permissions: List[str]) -> dict:
        """
        Grant permissions to an agent on this stream.

        Creates a real Capability object on Sui.
        """
        bitmask = 0
        for perm in permissions:
            if perm not in PERM_MAP:
                raise ValueError(f"Unknown permission '{perm}'. Valid: {list(PERM_MAP.keys())}")
            bitmask |= PERM_MAP[perm]

        result = self._sui.delegate_capability(
            target_stream=self.sui_address,
            recipient=agent.wallet_address or self._sui.deployer_address,
            bitmask=bitmask,
            until_epoch=0,
        )

        # Save to SQLite
        self._db.execute(
            "INSERT OR REPLACE INTO capabilities (capability_id, stream_id, agent_id, bitmask, tx_digest) "
            "VALUES (?, ?, ?, ?, ?)",
            (result["capability_id"], self.stream_id, agent.agent_id, bitmask, result["tx_digest"]),
        )
        self._db.commit()

        perm_str = ", ".join(permissions)
        print(f"  [OK] Granted [{perm_str}] to {agent.name}: {result['explorer_url']}")

        return result

    def __repr__(self) -> str:
        return f"<Stream name={self.name!r} id={self.stream_id[:16]}...>"


# ── Agent ─────────────────────────────────────────────────────────────────────


class Agent:
    """An agent with an Ed25519 identity registered on Sui."""

    def __init__(
        self,
        name: str,
        agent_id: str,
        workspace_id: str,
        public_key_bytes: bytes,
        private_key_bytes: bytes,
        db: sqlite3.Connection,
        sui,
        walrus,
        wallet_address: str = "",
    ) -> None:
        self.name = name
        self.agent_id = agent_id
        self.workspace_id = workspace_id
        self.public_key_bytes = public_key_bytes
        self._private_key_bytes = private_key_bytes
        self._db = db
        self._sui = sui
        self._walrus = walrus
        self.wallet_address = wallet_address

        # Load Ed25519 keys
        self._private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        self._public_key = self._private_key.public_key()

    def _check_permission(self, stream: Stream, required_bit: int, action: str) -> None:
        """Check if agent has the required permission on the stream."""
        row = self._db.execute(
            "SELECT bitmask FROM capabilities WHERE stream_id=? AND agent_id=?",
            (stream.stream_id, self.agent_id),
        ).fetchone()

        if not row:
            raise PermissionDeniedError(
                f"Agent '{self.name}' has no capabilities for stream '{stream.name}'. "
                f"Call stream.grant({self.name}, permissions=['{action}']) first."
            )

        if not (row["bitmask"] & required_bit):
            raise PermissionDeniedError(
                f"Agent '{self.name}' lacks '{action}' permission on stream '{stream.name}'. "
                f"Current bitmask: {row['bitmask']}. Required bit: {required_bit}."
            )

    def publish(self, stream: Stream, content: str) -> PublishResult:
        """
        Publish content to a stream.

        Pipeline: sign -> compress -> Walrus upload -> Sui anchor -> SQLite save.
        """
        # 1. Check permission
        self._check_permission(stream, PERM_APPEND, "append")

        # 2. Create event
        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        event = {
            "event_id": event_id,
            "stream_id": stream.stream_id,
            "agent_id": self.agent_id,
            "agent_name": self.name,
            "content": content,
            "timestamp": timestamp,
        }

        # 3. Serialize and hash
        event_json = json.dumps(event, sort_keys=True).encode("utf-8")
        event_hash = hashlib.sha256(event_json).digest()

        # 4. Sign with Ed25519
        signature = self._private_key.sign(event_hash)

        # 5. Create envelope
        envelope = {
            "event": event,
            "hash": event_hash.hex(),
            "signature": signature.hex(),
            "public_key": self.public_key_bytes.hex(),
            "agent_id": self.agent_id,
        }

        # 6. Compress
        envelope_bytes = gzip.compress(json.dumps(envelope).encode("utf-8"))

        # 7. Upload to Walrus
        blob_id = _run(self._walrus.upload_blob(envelope_bytes, store_epochs=5))
        walrus_url = f"{WALRUS_AGG}/v1/blobs/{blob_id}"
        print(f"  [OK] Published to Walrus: {blob_id}")

        # 8. Anchor on Sui
        anchor_result = self._sui.anchor_event(
            blob_id=blob_id,
            event_hash=event_hash,
            event_id=event_id,
            event_type="memory_append",
            workspace_id=stream.workspace_id,
            agent_id=self.agent_id,
        )
        tx_digest = anchor_result["tx_digest"]
        sui_url = anchor_result["explorer_url"]
        print(f"  [OK] Anchored on Sui: {sui_url}")

        # 9. Save to SQLite
        self._db.execute(
            "INSERT OR REPLACE INTO events "
            "(event_id, stream_id, agent_id, agent_name, blob_id, tx_digest, content, timestamp, hash, signature) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, stream.stream_id, self.agent_id, self.name,
             blob_id, tx_digest, content, timestamp, event_hash.hex(), signature),
        )
        self._db.commit()

        # 10. Return result
        return PublishResult(
            event_id=event_id,
            blob_id=blob_id,
            tx_digest=tx_digest,
            walrus_url=walrus_url,
            sui_url=sui_url,
        )

    def read(self, stream: Stream) -> List[MemoryMessage]:
        """
        Read all events from a stream.

        Pipeline: SQLite query -> Walrus download -> decompress -> verify hash -> verify signature.
        """
        # 1. Check permission
        self._check_permission(stream, PERM_READ, "read")

        # 2. Query SQLite
        rows = self._db.execute(
            "SELECT * FROM events WHERE stream_id=? ORDER BY timestamp",
            (stream.stream_id,),
        ).fetchall()

        messages = []
        for row in rows:
            # 3. Download from Walrus
            blob_data = _run(self._walrus.download_blob(row["blob_id"]))

            # 4. Decompress and deserialize
            envelope = json.loads(gzip.decompress(blob_data).decode("utf-8"))

            # 5. Verify SHA-256 hash
            event_json = json.dumps(envelope["event"], sort_keys=True).encode("utf-8")
            computed_hash = hashlib.sha256(event_json).hexdigest()
            if computed_hash != envelope["hash"]:
                raise TamperedMemoryError(
                    f"Hash mismatch for event {row['event_id']}! "
                    f"Expected: {envelope['hash']}, Got: {computed_hash}"
                )

            # 6. Verify Ed25519 signature
            pub_key_bytes = bytes.fromhex(envelope["public_key"])
            pub_key = Ed25519PublicKey.from_public_bytes(pub_key_bytes)
            sig_bytes = bytes.fromhex(envelope["signature"])
            hash_bytes = bytes.fromhex(envelope["hash"])
            try:
                pub_key.verify(sig_bytes, hash_bytes)
                verified = True
            except Exception:
                raise TamperedMemoryError(
                    f"Signature verification failed for event {row['event_id']}!"
                )

            messages.append(MemoryMessage(
                content=envelope["event"]["content"],
                agent_name=envelope["event"].get("agent_name", "unknown"),
                agent_id=envelope["event"]["agent_id"],
                timestamp=envelope["event"]["timestamp"],
                blob_id=row["blob_id"],
                tx_digest=row["tx_digest"],
                verified=verified,
            ))

        return messages

    def __repr__(self) -> str:
        return f"<Agent name={self.name!r} id={self.agent_id[:16]}...>"


# ── Workspace ─────────────────────────────────────────────────────────────────


class Workspace:
    """A workspace is the top-level container for agents and streams on Sui."""

    def __init__(
        self,
        name: str,
        workspace_id: str,
        db: sqlite3.Connection,
        sui,
        walrus,
        wallet_address: str = "",
    ) -> None:
        self.name = name
        self.workspace_id = workspace_id
        self.sui_explorer_url = f"{EXPLORER_BASE}/object/{workspace_id}?network=testnet"
        self._db = db
        self._sui = sui
        self._walrus = walrus
        self._wallet_address = wallet_address

    def agent(self, name: str) -> Agent:
        """
        Get or create an agent in this workspace.

        If the agent exists in SQLite, loads it (including Ed25519 private key).
        If not, generates a new Ed25519 keypair and registers on Sui.
        """
        # Check SQLite first
        row = self._db.execute(
            "SELECT * FROM agents WHERE name=? AND workspace_id=?",
            (name, self.workspace_id),
        ).fetchone()

        if row:
            logger.info("Agent '%s' loaded from local store", name)
            return Agent(
                name=name,
                agent_id=row["agent_id"],
                workspace_id=self.workspace_id,
                public_key_bytes=bytes(row["public_key"]),
                private_key_bytes=bytes(row["private_key"]),
                db=self._db,
                sui=self._sui,
                walrus=self._walrus,
                wallet_address=self._wallet_address,
            )

        # Generate Ed25519 keypair
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        private_key_bytes = private_key.private_bytes(
            Encoding.Raw, PrivateFormat.Raw, NoEncryption()
        )
        public_key_bytes = public_key.public_bytes(
            Encoding.Raw, PublicFormat.Raw
        )

        # Register on Sui
        result = self._sui.register_agent(
            workspace_id=self.workspace_id,
            name=name,
            public_key_bytes=public_key_bytes,
        )

        agent_id = result["agent_id"]

        # Save to SQLite
        self._db.execute(
            "INSERT INTO agents (name, workspace_id, agent_id, public_key, private_key, tx_digest) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, self.workspace_id, agent_id, public_key_bytes, private_key_bytes, result["tx_digest"]),
        )
        self._db.commit()

        print(f"  [OK] Agent '{name}' registered: {result['explorer_url']}")

        return Agent(
            name=name,
            agent_id=agent_id,
            workspace_id=self.workspace_id,
            public_key_bytes=public_key_bytes,
            private_key_bytes=private_key_bytes,
            db=self._db,
            sui=self._sui,
            walrus=self._walrus,
            wallet_address=self._wallet_address,
        )

    def stream(self, name: str) -> Stream:
        """Get or create a named stream in this workspace."""
        row = self._db.execute(
            "SELECT * FROM streams WHERE name=? AND workspace_id=?",
            (name, self.workspace_id),
        ).fetchone()

        if row:
            logger.info("Stream '%s' loaded from local store", name)
            return Stream(
                name=name,
                stream_id=row["stream_id"],
                workspace_id=self.workspace_id,
                db=self._db,
                sui=self._sui,
            )

        # Create new stream (local only — Sui stream objects are created on first anchor)
        stream_id = str(uuid.uuid4())
        self._db.execute(
            "INSERT INTO streams (name, workspace_id, stream_id) VALUES (?, ?, ?)",
            (name, self.workspace_id, stream_id),
        )
        self._db.commit()

        print(f"  [OK] Stream '{name}' created: {stream_id}")

        return Stream(
            name=name,
            stream_id=stream_id,
            workspace_id=self.workspace_id,
            db=self._db,
            sui=self._sui,
        )

    def __repr__(self) -> str:
        return f"<Workspace name={self.name!r} id={self.workspace_id[:16]}...>"


# ── WalrusOS ──────────────────────────────────────────────────────────────────


class WalrusOS:
    """
    Top-level WalrusOS entry point — real Walrus + real Sui.

    Usage::

        from walrusos.sdk.live import WalrusOS

        os = WalrusOS()
        os.login()
        workspace = os.workspace("my-project")
        agent = workspace.agent("Research")
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or str(DB_PATH)
        self._db = _init_db(self._db_path)
        self._sui = None
        self._walrus = None
        self._wallet_address = ""
        self._logged_in = False

    def login(self) -> str:
        """
        Connect to Sui wallet and initialize real adapters.

        Loads wallet from ~/.sui/sui_config/client.yaml (the default
        location used by the Sui CLI).

        Returns the active Sui address.
        Raises LoginError if the wallet is not configured.
        """
        from walrusos.adapters.sui_real import RealSuiClient, SuiNotFoundError
        from walrusos.adapters.walrus_real import RealWalrusClient

        try:
            self._sui = RealSuiClient()
        except SuiNotFoundError as exc:
            raise LoginError(
                "Sui CLI not found. Install it:\n"
                "  1. Download from https://docs.sui.io/build/install\n"
                "  2. Run: sui client active-address\n"
                "  3. Fund your wallet: sui client faucet"
            ) from exc

        if not self._sui.active_address:
            raise LoginError(
                "Sui wallet not configured. Set it up:\n"
                "  1. Run: sui client active-address\n"
                "  2. Fund your wallet: sui client faucet"
            )

        self._walrus = RealWalrusClient()
        self._wallet_address = self._sui.active_address
        self._logged_in = True

        print(f"  [OK] Logged in: {self._wallet_address}")
        print(f"       Network:   testnet")
        print(f"       Package:   {self._sui.package_id[:20]}...")

        return self._wallet_address

    def workspace(self, name: str) -> Workspace:
        """
        Get or create a workspace.

        If the workspace exists in SQLite, loads it.
        If not, creates a Workspace object on Sui testnet.
        """
        if not self._logged_in:
            raise LoginError("Call os.login() before creating a workspace.")

        # Check SQLite first
        row = self._db.execute(
            "SELECT * FROM workspaces WHERE name=?", (name,)
        ).fetchone()

        if row:
            logger.info("Workspace '%s' loaded from local store", name)
            ws = Workspace(
                name=name,
                workspace_id=row["workspace_id"],
                db=self._db,
                sui=self._sui,
                walrus=self._walrus,
                wallet_address=self._wallet_address,
            )
            print(f"  [OK] Workspace '{name}' loaded: {ws.sui_explorer_url}")
            return ws

        # Create on Sui
        result = self._sui.create_workspace(name)
        workspace_id = result["workspace_id"]

        # Save to SQLite
        self._db.execute(
            "INSERT INTO workspaces (name, workspace_id, tx_digest) VALUES (?, ?, ?)",
            (name, workspace_id, result["tx_digest"]),
        )
        self._db.commit()

        ws = Workspace(
            name=name,
            workspace_id=workspace_id,
            db=self._db,
            sui=self._sui,
            walrus=self._walrus,
            wallet_address=self._wallet_address,
        )
        print(f"  [OK] Workspace '{name}' created: {result['explorer_url']}")

        return ws

    def __repr__(self) -> str:
        status = "connected" if self._logged_in else "not logged in"
        return f"<WalrusOS status={status!r}>"
