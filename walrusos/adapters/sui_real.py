"""
Real Sui Transaction Adapter — executes PTBs on Sui Testnet via the CLI.

This adapter calls the ``sui`` CLI binary to execute Move function calls
on the live Sui testnet. It does NOT depend on pysui — it uses subprocess
to invoke ``sui client call --json`` and parses the JSON output.

Why CLI instead of pysui?
  - Zero Python dependency conflicts
  - Works with any Sui version that has ``sui client call --json``
  - Same binary the deployer already used to publish the package
  - JSON output is stable and well-documented

All methods return a dict containing at minimum:
  - tx_digest:    The Sui transaction digest
  - explorer_url: Link to view the transaction on Sui Explorer

Configuration:
  Reads PACKAGE_ID and LEDGER_ANCHOR_ID from ``walrusos.config``.
  Reads the wallet from ``~/.sui/sui_config/client.yaml`` (Sui CLI default).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import shutil
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

EXPLORER_BASE = "https://suiexplorer.com/txblock"
NETWORK = "testnet"
GAS_BUDGET = 50_000_000


# ── Exceptions ────────────────────────────────────────────────────────────────


class SuiTransactionError(Exception):
    """Raised when a Sui transaction fails."""

    def __init__(
        self,
        message: str,
        tx_digest: Optional[str] = None,
        move_abort_code: Optional[int] = None,
    ) -> None:
        self.tx_digest = tx_digest
        self.move_abort_code = move_abort_code
        detail = message
        if move_abort_code is not None:
            detail += f" (Move abort code: {move_abort_code})"
        if tx_digest:
            detail += f" [tx: {tx_digest}]"
        super().__init__(detail)


class SuiNotFoundError(Exception):
    """Raised when the sui CLI binary is not found."""


# ── Helper: find sui binary ──────────────────────────────────────────────────


def _find_sui() -> str:
    """Locate the sui binary. Checks common locations."""
    # Check env var first
    env_sui = os.environ.get("SUI_BINARY")
    if env_sui and os.path.isfile(env_sui):
        return env_sui

    # Check the user's local bin (where we downloaded it)
    home_sui = os.path.join(os.path.expanduser("~"), "sui_bin", "sui.exe")
    if os.path.isfile(home_sui):
        return home_sui

    # Check PATH
    path_sui = shutil.which("sui") or shutil.which("sui.exe")
    if path_sui:
        return path_sui

    raise SuiNotFoundError(
        "sui CLI not found. Install it from https://docs.sui.io/build/install "
        "or set SUI_BINARY=/path/to/sui"
    )


def _explorer_url(tx_digest: str) -> str:
    """Build a Sui Explorer URL for a transaction."""
    return f"{EXPLORER_BASE}/{tx_digest}?network={NETWORK}"


# ── RealSuiClient ────────────────────────────────────────────────────────────


class RealSuiClient:
    """
    Executes Move function calls on Sui testnet via the CLI.

    Each method builds a ``sui client call`` command, executes it,
    parses the JSON output, and returns a structured result dict.

    Args:
        package_id:       Deployed WalrusOS Move package ID.
        ledger_anchor_id: Object ID of the shared LedgerAnchor.
        sui_binary:       Path to the sui CLI binary (auto-detected if None).
    """

    def __init__(
        self,
        package_id: Optional[str] = None,
        ledger_anchor_id: Optional[str] = None,
        sui_binary: Optional[str] = None,
    ) -> None:
        # Load from config if not provided
        from walrusos.config import (
            PACKAGE_ID as _PKG,
            LEDGER_ANCHOR_ID as _LEDGER,
            DEPLOYER_ADDRESS as _DEPLOYER,
        )
        self.package_id = package_id or _PKG
        self.ledger_anchor_id = ledger_anchor_id or _LEDGER
        self.deployer_address = _DEPLOYER
        self.sui_binary = sui_binary or _find_sui()

        # Verify the binary works
        try:
            result = subprocess.run(
                [self.sui_binary, "client", "active-address"],
                capture_output=True, text=True, timeout=15,
            )
            self.active_address = result.stdout.strip()
            logger.info("Sui wallet connected: %s", self.active_address)
        except Exception as exc:
            logger.warning("Failed to connect to Sui wallet: %s", exc)
            self.active_address = ""

    def _run_call(
        self,
        module: str,
        function: str,
        args: List[str],
    ) -> Dict[str, Any]:
        """
        Execute ``sui client call --json`` and return the parsed JSON result.

        Raises SuiTransactionError on failure with Move abort code if available.
        """
        cmd = [
            self.sui_binary, "client", "call",
            "--package", self.package_id,
            "--module", module,
            "--function", function,
            "--gas-budget", str(GAS_BUDGET),
            "--json",
        ]
        if args:
            cmd.append("--args")
            # Use -- to terminate options before args so values starting with '-'
            # (e.g. Walrus blob IDs like "-8BFb...") are not parsed as flags.
            if any(str(a).startswith("-") for a in args):
                cmd.append("--")
            cmd.extend(args)

        logger.info("Sui PTB: %s::%s(%s)", module, function, ", ".join(args[:3]))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            raise SuiTransactionError(
                f"Sui CLI timed out executing {module}::{function}"
            )

        # Parse output
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            # Try to extract Move abort code from stderr OR stdout
            # (sui CLI sometimes writes Move-abort details to stdout in --json mode).
            abort_code = None
            for haystack in (stderr, stdout):
                if "MoveAbort" in haystack:
                    try:
                        import re
                        match = re.search(r"MoveAbort\([^,]+,\s*(\d+)\)", haystack)
                        if match:
                            abort_code = int(match.group(1))
                            break
                    except Exception:
                        pass

            # Surface stdout, stderr, returncode, AND the failing command so the
            # error is debuggable. The previous "{stderr[:500]}" alone produced
            # an empty message when the CLI failed silently to stdout.
            detail_lines = [
                f"{module}::{function} failed",
                f"  returncode: {result.returncode}",
                f"  cmd:        {' '.join(cmd)}",
            ]
            if stderr:
                detail_lines.append(f"  stderr:     {stderr[:1000]}")
            else:
                detail_lines.append("  stderr:     (empty)")
            if stdout:
                detail_lines.append(f"  stdout:     {stdout[:1000]}")
            else:
                detail_lines.append("  stdout:     (empty)")
            if abort_code is not None:
                detail_lines.append(f"  abort_code: {abort_code}")

            full_msg = "\n".join(detail_lines)
            # Log loudly at ERROR — previously buried in WARNING swallowing,
            # which hid this bug for weeks.
            logger.error("Sui CLI failure:\n%s", full_msg)

            raise SuiTransactionError(
                full_msg,
                move_abort_code=abort_code,
            )

        # Parse JSON output
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            raise SuiTransactionError(
                f"Failed to parse JSON from sui CLI output: {stdout[:500]}"
            )

        return data

    def _run_ptb_call(
        self,
        module: str,
        function: str,
        args: List[str],
    ) -> Dict[str, Any]:
        """Execute ``sui client ptb --move-call ...`` and return parsed JSON.

        Why this exists: ``sui client call --args <values>`` is greedy/clap-based
        and rejects any value that starts with ``-`` as an unknown flag. There
        is no ``--`` escape that works (it ends option-parsing globally and the
        LedgerAnchor object id becomes a stray positional). Walrus blob_ids are
        43-char base64url Blake2b hashes, so ~3 in 64 start with ``-``.

        PTB form quotes string values inline: ``'"foo"'`` is one argv token
        whose bytes are literally ``"foo"`` (the quotes are part of the value
        clap sees). Address/ObjectId values are passed as ``@0x…``. This
        sidesteps the ``-`` problem entirely.
        """
        target = f"{self.package_id}::{module}::{function}"
        move_call_tokens: List[str] = [target]
        for a in args:
            sa = str(a)
            if sa.startswith("0x") and len(sa) > 4:
                move_call_tokens.append(f"@{sa}")
            else:
                # Quote the value so clap accepts -prefixed strings.
                # Escape embedded double-quotes (rare in practice).
                escaped = sa.replace('"', r'\"')
                move_call_tokens.append(f'"{escaped}"')

        cmd = [
            self.sui_binary, "client", "ptb",
            "--move-call", *move_call_tokens,
            "--gas-budget", str(GAS_BUDGET),
            "--json",
        ]

        logger.info(
            "Sui PTB: %s::%s(%s) via ptb form", module, function, ", ".join(args[:3]),
        )

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise SuiTransactionError(
                f"Sui PTB timed out executing {module}::{function}"
            )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            abort_code = None
            for haystack in (stderr, stdout):
                if "MoveAbort" in haystack:
                    try:
                        import re
                        m = re.search(r"MoveAbort\([^,]+,\s*(\d+)\)", haystack)
                        if m:
                            abort_code = int(m.group(1))
                            break
                    except Exception:
                        pass
            full_msg = "\n".join([
                f"{module}::{function} (ptb) failed",
                f"  returncode: {result.returncode}",
                f"  cmd:        {' '.join(cmd)}",
                f"  stderr:     {stderr[:1000] or '(empty)'}",
                f"  stdout:     {stdout[:1000] or '(empty)'}",
            ])
            logger.error("Sui PTB failure:\n%s", full_msg)
            raise SuiTransactionError(full_msg, move_abort_code=abort_code)

        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            raise SuiTransactionError(
                f"Failed to parse JSON from sui ptb output: {stdout[:500]}"
            )

    def _call(
        self,
        module: str,
        function: str,
        args: List[str],
    ) -> Dict[str, Any]:
        """Dispatch to ``client call`` (greedy --args) by default, falling back
        to PTB form when any arg starts with ``-`` (which ``client call`` can't
        accept). PTB returns the same JSON shape, so callers don't care."""
        needs_ptb = any(str(a).startswith("-") for a in args)
        if needs_ptb:
            return self._run_ptb_call(module, function, args)
        return self._run_call(module, function, args)

    @staticmethod
    def _extract_digest(data: Dict[str, Any]) -> str:
        """Extract the transaction digest from sui client call JSON output."""
        return data.get("digest", "")

    @staticmethod
    def _extract_created_objects(
        data: Dict[str, Any],
        type_filter: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Extract created object IDs from the objectChanges array."""
        changes = data.get("objectChanges", [])
        created = []
        for change in changes:
            if change.get("type") == "created":
                obj_type = change.get("objectType", "")
                obj_id = change.get("objectId", "")
                if type_filter is None or type_filter in obj_type:
                    created.append({"objectId": obj_id, "objectType": obj_type})
        return created

    # ── Method 1: create_workspace ────────────────────────────────────────────

    def create_workspace(self, name: str) -> Dict[str, Any]:
        """
        Create a Workspace object on Sui.

        Calls: PACKAGE_ID::identity::create_workspace(name: String)
        Returns: { tx_digest, workspace_id, explorer_url }
        """
        data = self._call(
            module="identity",
            function="create_workspace",
            args=[name],
        )

        digest = self._extract_digest(data)
        created = self._extract_created_objects(data, "Workspace")

        workspace_id = created[0]["objectId"] if created else ""
        if not workspace_id:
            raise SuiTransactionError(
                "create_workspace succeeded but no Workspace object in result",
                tx_digest=digest,
            )

        return {
            "tx_digest": digest,
            "workspace_id": workspace_id,
            "explorer_url": _explorer_url(digest),
        }

    # ── Method 2: register_agent ──────────────────────────────────────────────

    def register_agent(
        self,
        workspace_id: str,
        name: str,
        public_key_bytes: bytes,
    ) -> Dict[str, Any]:
        """
        Register an AgentIdentity on Sui.

        Calls: PACKAGE_ID::identity::register_agent(
            workspace_id: address, name: String,
            public_key: vector<u8>, trust_root: vector<u8>
        )
        Returns: { tx_digest, agent_id, explorer_url }
        """
        # trust_root = SHA-256(public_key) — deterministic identity anchor
        trust_root = hashlib.sha256(public_key_bytes).digest()

        # Format bytes as Sui CLI vector<u8> literal
        pk_hex = f'vector[{",".join(str(b) for b in public_key_bytes)}]'
        tr_hex = f'vector[{",".join(str(b) for b in trust_root)}]'

        data = self._call(
            module="identity",
            function="register_agent",
            args=[workspace_id, name, pk_hex, tr_hex],
        )

        digest = self._extract_digest(data)
        created = self._extract_created_objects(data, "AgentIdentity")

        agent_id = created[0]["objectId"] if created else ""
        if not agent_id:
            raise SuiTransactionError(
                "register_agent succeeded but no AgentIdentity object in result",
                tx_digest=digest,
            )

        return {
            "tx_digest": digest,
            "agent_id": agent_id,
            "explorer_url": _explorer_url(digest),
        }

    # ── Method 3: anchor_event ────────────────────────────────────────────────

    def anchor_event(
        self,
        blob_id: str,
        event_hash: bytes,
        event_id: Optional[str] = None,
        event_type: str = "memory_append",
        workspace_id: str = "default",
        agent_id: str = "default",
        parent_event: str = "genesis",
    ) -> Dict[str, Any]:
        """
        Anchor a protocol event on Sui by calling the shared LedgerAnchor.

        Calls: PACKAGE_ID::protocol::anchor_event(
            ledger: &mut LedgerAnchor,
            event_id, event_type, workspace_id, agent_id,
            blob_id, blob_hash, parent_event, previous_hash, signature
        )
        Returns: { tx_digest, explorer_url }
        """
        if event_id is None:
            event_id = hashlib.sha256(event_hash + blob_id.encode()).hexdigest()[:16]

        blob_hash = event_hash.hex() if isinstance(event_hash, bytes) else str(event_hash)
        previous_hash = "genesis"
        signature = "cli-unsigned"

        data = self._call(
            module="protocol",
            function="anchor_event",
            args=[
                self.ledger_anchor_id,  # &mut LedgerAnchor (shared object)
                event_id,
                event_type,
                workspace_id,
                agent_id,
                blob_id,
                blob_hash,
                parent_event,
                previous_hash,
                signature,
            ],
        )

        digest = self._extract_digest(data)

        return {
            "tx_digest": digest,
            "explorer_url": _explorer_url(digest),
        }

    # ── Method 4: delegate_capability ─────────────────────────────────────────

    def delegate_capability(
        self,
        target_stream: str,
        recipient: str,
        bitmask: int = 7,
        until_epoch: int = 0,
    ) -> Dict[str, Any]:
        """
        Delegate a Capability token to a recipient.

        Calls: PACKAGE_ID::identity::delegate_capability(
            target_stream: address, bitmask: u64,
            recipient: address, valid_until_epoch: u64
        )
        Returns: { tx_digest, capability_id, explorer_url }
        """
        data = self._call(
            module="identity",
            function="delegate_capability",
            args=[
                target_stream,
                str(bitmask),
                recipient,
                str(until_epoch),
            ],
        )

        digest = self._extract_digest(data)
        created = self._extract_created_objects(data, "Capability")

        capability_id = created[0]["objectId"] if created else ""
        if not capability_id:
            raise SuiTransactionError(
                "delegate_capability succeeded but no Capability object in result",
                tx_digest=digest,
            )

        return {
            "tx_digest": digest,
            "capability_id": capability_id,
            "explorer_url": _explorer_url(digest),
        }

    # ── Method 5: revoke_capability ───────────────────────────────────────────

    def revoke_capability(self, capability_id: str) -> Dict[str, Any]:
        """
        Revoke a Capability by consuming and destroying it.

        Calls: PACKAGE_ID::identity::revoke_capability(cap: Capability)
        Returns: { tx_digest, explorer_url }
        """
        data = self._call(
            module="identity",
            function="revoke_capability",
            args=[capability_id],
        )

        digest = self._extract_digest(data)

        return {
            "tx_digest": digest,
            "explorer_url": _explorer_url(digest),
        }

    # ── Utility: query object ─────────────────────────────────────────────────

    def get_object(self, object_id: str) -> Dict[str, Any]:
        """Query a Sui object by ID. Returns the JSON representation."""
        result = subprocess.run(
            [self.sui_binary, "client", "object", object_id, "--json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            raise SuiTransactionError(
                f"Failed to query object {object_id}: {result.stderr[:300]}"
            )
        return json.loads(result.stdout)

    # ── Utility: query anchored events via JSON-RPC ───────────────────────────

    def query_anchored_events(
        self,
        limit: int = 50,
        rpc_url: str = "https://fullnode.testnet.sui.io:443",
    ) -> List[str]:
        """
        Query Sui for all ProtocolEventAnchored events emitted by this package.

        Uses the suix_queryEvents JSON-RPC method directly (no CLI dependency).
        The Move contract (protocol.move) emits ProtocolEventAnchored on every
        anchor_event() call; each event contains the blob_id field.

        Args:
            limit:   Maximum number of events to retrieve per page (default 50).
            rpc_url: Sui JSON-RPC endpoint (default: testnet fullnode).

        Returns:
            List of blob_id strings extracted from on-chain events, in order.

        Raises:
            SuiTransactionError: If the RPC call fails or returns an error.
        """
        try:
            import httpx
        except ImportError:
            raise SuiTransactionError(
                "httpx is required for query_anchored_events. "
                "Install it: pip install httpx"
            )

        # The canonical event type as defined in protocol.move
        candidate_types = [
            f"{self.package_id}::protocol::ProtocolEventAnchored",
            f"{self.package_id}::protocol::EventAnchored",
            f"{self.package_id}::protocol::BlobAnchored",
        ]

        blob_ids: List[str] = []

        for event_type in candidate_types:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "suix_queryEvents",
                "params": [
                    {"MoveEventType": event_type},
                    None,    # cursor — start from the beginning
                    limit,
                    False,   # ascending order
                ],
            }

            try:
                resp = httpx.post(
                    rpc_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=20,
                )
                resp.raise_for_status()
                body = resp.json()
            except Exception as exc:
                raise SuiTransactionError(
                    f"suix_queryEvents HTTP request failed: {exc}"
                )

            if "error" in body:
                rpc_err = body["error"].get("message", str(body["error"]))
                logger.debug("suix_queryEvents error for %s: %s", event_type, rpc_err)
                continue  # Try next candidate type

            data = body.get("result", {}).get("data", [])
            if not data:
                logger.debug("suix_queryEvents: 0 events for %s", event_type)
                continue

            for ev in data:
                parsed = ev.get("parsedJson", {})
                bid = parsed.get("blob_id") or parsed.get("blobId")
                if bid and bid not in blob_ids:
                    blob_ids.append(bid)

            logger.info(
                "query_anchored_events: found %d blob IDs via %s",
                len(blob_ids),
                event_type,
            )
            break  # Success — stop iterating candidates

        return blob_ids

    # ── Utility: query events filtered by workspace_id ────────────────────────

    def query_events_by_workspace(
        self,
        workspace_id: str,
        limit: int = 50,
        rpc_url: str = "https://fullnode.testnet.sui.io:443",
    ) -> List[str]:
        """
        Query ProtocolEventAnchored events scoped to one workspace.

        Strategy (scalable to 100k+ events):
          1. Try the compound ``All`` filter [MoveEventType, MoveEventField].
             This is a server-side O(workspace events) query.
          2. If the node rejects the compound filter (older testnet builds),
             fall back to fetching all MoveEventType events and filtering
             parsedJson["workspace_id"] in Python.

        In both paths blob_ids from other workspaces are strictly excluded.

        Args:
            workspace_id: On-chain workspace object ID to filter by.
            limit:        Max events per RPC page (default 50).
            rpc_url:      Sui JSON-RPC endpoint.

        Returns:
            List[str] of blob_id values belonging to this workspace, in order.

        Raises:
            SuiTransactionError: On unrecoverable network or parse failure.
        """
        try:
            import httpx
        except ImportError:
            raise SuiTransactionError(
                "httpx is required for query_events_by_workspace. "
                "Install it: pip install httpx"
            )

        event_type = f"{self.package_id}::protocol::ProtocolEventAnchored"

        def _post(payload: dict) -> dict:
            resp = httpx.post(
                rpc_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()

        def _extract(data: list) -> List[str]:
            """Pull blob_ids from a page of events, filtering by workspace_id."""
            ids: List[str] = []
            for ev in data:
                parsed = ev.get("parsedJson", {})
                if parsed.get("workspace_id") != workspace_id:
                    continue  # never cross workspace boundaries
                bid = parsed.get("blob_id") or parsed.get("blobId")
                if bid and bid not in ids:
                    ids.append(bid)
            return ids

        blob_ids: List[str] = []

        # ── Attempt 1: compound server-side filter ─────────────────────────────
        compound_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "suix_queryEvents",
            "params": [
                {
                    "All": [
                        {"MoveEventType": event_type},
                        {
                            "MoveEventField": {
                                "path": "/workspace_id",
                                "value": workspace_id,
                            }
                        },
                    ]
                },
                None,   # cursor — start from beginning
                limit,
                False,  # ascending
            ],
        }

        try:
            body = _post(compound_payload)
            if "error" not in body:
                data = body.get("result", {}).get("data", [])
                blob_ids = _extract(data)
                logger.info(
                    "query_events_by_workspace: compound filter → %d blob IDs "
                    "for workspace %.16s",
                    len(blob_ids), workspace_id,
                )
                return blob_ids
            else:
                rpc_err = body["error"].get("message", str(body["error"]))
                logger.debug(
                    "MoveEventField filter not supported: %s — "
                    "falling back to Python filter",
                    rpc_err,
                )
        except Exception as exc:
            logger.debug(
                "compound filter request failed: %s — falling back to "
                "Python filter",
                exc,
            )

        # ── Attempt 2: fetch all events, filter in Python ──────────────────────
        simple_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "suix_queryEvents",
            "params": [
                {"MoveEventType": event_type},
                None,
                limit,
                False,
            ],
        }

        try:
            body = _post(simple_payload)
        except Exception as exc:
            raise SuiTransactionError(
                f"suix_queryEvents fallback request failed: {exc}"
            )

        if "error" in body:
            raise SuiTransactionError(
                f"suix_queryEvents error: {body['error']}"
            )

        data = body.get("result", {}).get("data", [])
        blob_ids = _extract(data)

        logger.info(
            "query_events_by_workspace: Python filter → %d blob IDs "
            "for workspace %.16s",
            len(blob_ids), workspace_id,
        )
        return blob_ids
