"""
WalrusOS Key Store — Persistent AES-256 key management.

Design
======
AES data keys (DEKs) are encrypted with a Key Encryption Key (KEK) before
being stored in SQLite.  The KEK is derived using PBKDF2-HMAC-SHA256 from:

  Priority 1 — ``WALRUSOS_KEY_PASSWORD`` environment variable
  Priority 2 — Wallet signature over a deterministic challenge (requires pysui)
  Priority 3 — Machine-derived key (platform.node + wallet address + stored salt)

The third priority is the weakest but still ensures keys survive restarts
on the same machine.  For production deployments, set ``WALRUSOS_KEY_PASSWORD``
or use a hardware security module.

Key Rotation
============
Each key has a ``key_id`` (UUID) and a generation counter.  Calling
``rotate()`` retires the current active key and generates a new one.
Old keys are kept in the store so that blobs encrypted with them can still
be decrypted.

Blob Format (V1)
================
Every blob uploaded with a KeyStore-aware WalrusAdapter has this header:

  b"WKEY"        4 bytes — magic number
  b"\\x01"       1 byte  — format version
  key_id         16 bytes — UUID bytes (big-endian)
  nonce          12 bytes — AES-GCM nonce
  ciphertext     N bytes  — AES-GCM ciphertext + 16-byte GCM tag

Blobs uploaded before the KeyStore migration (V0 format) have no header
and are decrypted with the key that was active at upload time — the caller
must supply the legacy key if it still has it.
"""
from __future__ import annotations

import hashlib
import logging
import os
import platform
import uuid
from base64 import b64decode, b64encode
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from sqlmodel import Field, Session, SQLModel, create_engine, select

logger = logging.getLogger(__name__)

# ── Format constants ──────────────────────────────────────────────────────────

BLOB_MAGIC   = b"WKEY"
BLOB_VERSION = b"\x01"
BLOB_HEADER_SIZE = 4 + 1 + 16 + 12   # magic + version + key_id + nonce = 33 bytes
KDF_ITERATIONS   = 600_000


# ── SQLModel table ────────────────────────────────────────────────────────────

class KeyRecord(SQLModel, table=True):
    """One row per AES key version."""
    __tablename__ = "key_store"

    key_id:       str = Field(primary_key=True)        # UUID hex
    wrapped_key:  str = Field(...)                     # base64(AESGCM(kek).encrypt(dek))
    kek_salt:     str = Field(...)                     # base64 random 32-byte salt
    kek_method:   str = Field(default="pbkdf2")        # "pbkdf2" | "machine"
    generation:   int = Field(default=1)               # monotonically increasing
    is_active:    int = Field(default=1)               # 1 = active, 0 = retired
    created_at:   str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    retired_at:   Optional[str] = Field(default=None)


# ── Key Encryption Key derivation ─────────────────────────────────────────────

def _derive_kek(password: bytes, salt: bytes) -> bytes:
    """Derive a 32-byte Key Encryption Key using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(password)


def _get_password(wallet_address: Optional[str] = None) -> bytes:
    """
    Return the password used to derive the KEK.

    Priority:
      1. WALRUSOS_KEY_PASSWORD env var (recommended for production)
      2. WALRUSOS_MACHINE_SECRET env var (acceptable for server deployments)
      3. Machine-derived fallback (WEAK — logs a prominent warning)

    CVE-WOS-003 fix: the old fallback was predictable if the attacker knew
    the machine hostname and wallet address.  The new fallback mixes in a
    random 32-byte secret that is generated once and stored in the DB directory
    alongside walrusos.db.  An attacker who only has a copy of the SQLite file
    but NOT the secret file still cannot derive the KEK.
    """
    env_pw = os.environ.get("WALRUSOS_KEY_PASSWORD", "")
    if env_pw:
        logger.debug("KeyStore: using WALRUSOS_KEY_PASSWORD for KEK derivation")
        return env_pw.encode("utf-8")

    machine_secret_env = os.environ.get("WALRUSOS_MACHINE_SECRET", "")
    if machine_secret_env:
        logger.debug("KeyStore: using WALRUSOS_MACHINE_SECRET for KEK derivation")
        return machine_secret_env.encode("utf-8")

    # CVE-WOS-003 fix: derive from a random secret file written once, not just
    # platform.node() which is public information.
    wallet_str  = wallet_address or "no-wallet"
    machine_str = platform.node()

    # Locate / create the secret file next to walrusos.db
    secret_path = os.path.join(
        os.path.expanduser("~"), ".walrusos", ".machine_secret"
    )
    try:
        os.makedirs(os.path.dirname(secret_path), exist_ok=True)
        if os.path.exists(secret_path):
            with open(secret_path, "rb") as fh:
                machine_secret_bytes = fh.read()
            if len(machine_secret_bytes) < 32:
                raise ValueError("Secret file too short")
        else:
            machine_secret_bytes = os.urandom(32)
            with open(secret_path, "wb") as fh:
                fh.write(machine_secret_bytes)
            # Restrict permissions to owner-only on POSIX
            try:
                os.chmod(secret_path, 0o600)
            except OSError:
                pass  # Windows — ignore
            logger.info(
                "KeyStore: generated machine secret at %s. "
                "Back this file up alongside walrusos.db.",
                secret_path,
            )
    except Exception as exc:
        # Absolute last resort: fall back to hostname + wallet + static string.
        # This is WEAK — warn loudly.
        machine_secret_bytes = hashlib.sha256(
            f"{machine_str}:{wallet_str}:walrusos-last-resort-v1".encode()
        ).digest()
        logger.warning(
            "KeyStore: WALRUSOS_KEY_PASSWORD not set and machine secret file could not "
            "be created (%s). Using a WEAK machine-derived KEK. "
            "Set WALRUSOS_KEY_PASSWORD in production.",
            exc,
        )

    derived = f"{machine_str}:{wallet_str}:".encode() + machine_secret_bytes
    logger.warning(
        "KeyStore: WALRUSOS_KEY_PASSWORD not set. Using machine-derived KEK. "
        "Set WALRUSOS_KEY_PASSWORD in production for stronger key protection."
    )
    return hashlib.sha256(derived).digest()


# ── Key wrapping helpers ──────────────────────────────────────────────────────

def _wrap_key(dek: bytes, kek: bytes) -> Tuple[str, str]:
    """Wrap (encrypt) a DEK with a KEK.  Returns (wrapped_key_b64, kek_salt_b64)."""
    salt  = os.urandom(32)
    kek   = _derive_kek(kek if len(kek) == 32 else kek, salt)
    nonce = os.urandom(12)
    ct    = AESGCM(kek).encrypt(nonce, dek, None)
    wrapped = b64encode(nonce + ct).decode()
    return wrapped, b64encode(salt).decode()


def _unwrap_key(wrapped_b64: str, salt_b64: str, password: bytes) -> bytes:
    """Unwrap (decrypt) a DEK using the KEK derived from password + salt."""
    salt    = b64decode(salt_b64)
    kek     = _derive_kek(password, salt)
    data    = b64decode(wrapped_b64)
    nonce, ct = data[:12], data[12:]
    return AESGCM(kek).decrypt(nonce, ct, None)


# ── KeyStore ──────────────────────────────────────────────────────────────────

class KeyStore:
    """
    Persistent AES-256 key store backed by SQLite.

    Usage::

        ks = KeyStore(db_path="~/.walrusos/walrusos.db", wallet_address="0x…")
        key_id, dek = ks.active_key()       # get current DEK
        _, dek_old  = ks.key_by_id(old_id) # get DEK for old blob
        ks.rotate()                          # retire current, generate new

    The KeyStore is NOT thread-safe — intended for single-process asyncio use.
    """

    def __init__(
        self,
        db_path:        str = "~/.walrusos/walrusos.db",
        wallet_address: Optional[str] = None,
    ) -> None:
        import os as _os
        resolved = _os.path.expanduser(db_path)
        _os.makedirs(_os.path.dirname(resolved), exist_ok=True)
        self._engine = create_engine(
            f"sqlite:///{resolved}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        SQLModel.metadata.create_all(self._engine)
        self._wallet_address = wallet_address

        # In-process cache: key_id → DEK bytes
        self._cache: Dict[str, bytes] = {}

        # Ensure at least one active key exists
        self._ensure_active_key()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _password(self) -> bytes:
        return _get_password(self._wallet_address)

    def _ensure_active_key(self) -> None:
        """Create the initial key if the store is empty."""
        with Session(self._engine) as session:
            existing = session.exec(
                select(KeyRecord).where(KeyRecord.is_active == 1)
            ).first()
            if existing is None:
                self._create_key_record(session, generation=1)
                session.commit()

    def _create_key_record(self, session: Session, generation: int) -> KeyRecord:
        """Generate a fresh DEK, wrap it, and insert into the store."""
        dek       = AESGCM.generate_key(bit_length=256)
        password  = self._password()
        wrapped, salt = _wrap_key(dek, password)
        key_id    = uuid.uuid4()
        record    = KeyRecord(
            key_id=str(key_id),
            wrapped_key=wrapped,
            kek_salt=salt,
            kek_method="pbkdf2",
            generation=generation,
            is_active=1,
        )
        session.add(record)
        # Cache plaintext DEK to avoid immediate unwrap
        self._cache[str(key_id)] = bytes(dek)
        return record

    # ── Public API ────────────────────────────────────────────────────────────

    def active_key(self) -> Tuple[str, bytes]:
        """
        Return ``(key_id, dek_bytes)`` for the currently active key.

        The DEK is cached in-process after the first decryption.
        Raises ``RuntimeError`` if no active key exists.
        """
        with Session(self._engine) as session:
            record = session.exec(
                select(KeyRecord).where(KeyRecord.is_active == 1)
            ).first()
            if record is None:
                raise RuntimeError("KeyStore has no active key")
            return self._load_dek(record)

    def key_by_id(self, key_id: str) -> Tuple[str, bytes]:
        """
        Return ``(key_id, dek_bytes)`` for any key (active or retired) by ID.

        Raises ``KeyError`` if the key_id is not found.
        """
        if key_id in self._cache:
            return key_id, self._cache[key_id]

        with Session(self._engine) as session:
            record = session.get(KeyRecord, key_id)
            if record is None:
                raise KeyError(f"Key '{key_id}' not found in key store")
            return self._load_dek(record)

    def _load_dek(self, record: KeyRecord) -> Tuple[str, bytes]:
        """Unwrap and cache a DEK from a KeyRecord."""
        if record.key_id in self._cache:
            return record.key_id, self._cache[record.key_id]

        password = self._password()
        dek      = _unwrap_key(record.wrapped_key, record.kek_salt, password)
        self._cache[record.key_id] = dek
        return record.key_id, dek

    def rotate(self) -> str:
        """
        Retire the current active key and generate a new one.

        Old blobs encrypted with the previous key are still readable
        (the retired key is kept in the store).

        Returns the new key_id.
        """
        with Session(self._engine) as session:
            # Find current active key
            current = session.exec(
                select(KeyRecord).where(KeyRecord.is_active == 1)
            ).first()
            if current is None:
                raise RuntimeError("No active key to rotate")

            # Retire it
            current.is_active  = 0
            current.retired_at = datetime.now(timezone.utc).isoformat()
            session.add(current)

            # Create new key
            new_record = self._create_key_record(session, generation=current.generation + 1)
            session.commit()

            logger.info(
                "KeyStore: rotated key %s → %s (generation %d)",
                current.key_id[:8],
                new_record.key_id[:8],
                new_record.generation,
            )
            return new_record.key_id

    def list_keys(self) -> list[dict]:
        """Return a list of all key records (for auditing, without DEK bytes)."""
        with Session(self._engine) as session:
            records = session.exec(select(KeyRecord)).all()
            return [
                {
                    "key_id":     r.key_id,
                    "generation": r.generation,
                    "is_active":  bool(r.is_active),
                    "kek_method": r.kek_method,
                    "created_at": r.created_at,
                    "retired_at": r.retired_at,
                }
                for r in records
            ]

    # ── Blob header helpers ────────────────────────────────────────────────────

    @staticmethod
    def make_v1_blob(key_id: str, nonce: bytes, ciphertext: bytes) -> bytes:
        """Assemble a V1 blob with the WKEY header."""
        kid_bytes = uuid.UUID(key_id).bytes   # 16 bytes, big-endian
        return BLOB_MAGIC + BLOB_VERSION + kid_bytes + nonce + ciphertext

    @staticmethod
    def parse_v1_header(data: bytes) -> Tuple[Optional[str], bytes, bytes]:
        """
        Parse a V1 blob header.

        Returns ``(key_id_str, nonce, ciphertext)`` if V1 format.
        Returns ``(None, data[:12], data[12:])`` if V0 (legacy, no header).
        """
        if len(data) >= 5 and data[:4] == BLOB_MAGIC and data[4:5] == BLOB_VERSION:
            key_id_bytes = data[5:21]
            nonce        = data[21:33]
            ciphertext   = data[33:]
            key_id_str   = str(uuid.UUID(bytes=key_id_bytes))
            return key_id_str, nonce, ciphertext
        # V0: no header — nonce is first 12 bytes
        return None, data[:12], data[12:]
