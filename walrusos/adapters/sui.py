"""
Sui Identity and Ledger Adapters — Production pysui integration.

Architecture
============
``SuiIdentityAdapter``:
  - Loads wallet from the local pysui config (~/.sui/sui_config/client.yaml)
  - Executes Programmable Transaction Blocks (PTBs) for:
      create_workspace, register_agent, delegate_capability, revoke_capability
  - Requires a deployed WalrusOS Move package (WALRUSOS_PACKAGE_ID)

``SuiLedgerAdapter``:
  - Hybrid strategy: SQLite (fast, persistent) + Sui (tamper-evident anchoring)
  - All reads come from SQLite (zero RPC latency)
  - On every append_event: persist to SQLite, then asynchronously emit on Sui
  - On-chain emission is fire-and-forget; errors are logged but never propagated
  - Without package_id, operates in SQLite-only mode (no chain anchoring)

pysui API compatibility
=======================
This file targets pysui >= 0.50.0 (the async API with SuiTransactionAsync).
If pysui is not installed or the wallet is not configured, the adapter
initialises but raises clear errors when on-chain operations are attempted.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from walrusos.engine.interfaces import LedgerAdapter
from walrusos.core.models.memory import MemoryEvent

logger = logging.getLogger(__name__)


# ── pysui lazy import helpers ─────────────────────────────────────────────────

def _import_pysui():
    """
    Import pysui modules.  Returns (SuiConfig, AsyncClient, SuiTransactionAsync)
    or raises ImportError with a helpful message.
    """
    try:
        from pysui import SuiConfig                                    # type: ignore[import]
        from pysui.sui.sui_clients.async_client import SuiClient       # type: ignore[import]
        from pysui.sui.sui_txn.async_transaction import (              # type: ignore[import]
            SuiTransactionAsync,
        )
        return SuiConfig, SuiClient, SuiTransactionAsync
    except ImportError as exc:
        raise ImportError(
            "pysui is required for Sui integration. "
            "Install it with: pip install pysui\n"
            "Then configure your wallet: sui client active-address"
        ) from exc


# ── SuiIdentityAdapter ────────────────────────────────────────────────────────

class SuiIdentityAdapter:
    """
    Handles Sui wallet authentication and on-chain object management.

    On initialisation, attempts to load the wallet from the pysui default
    configuration (~/.sui/sui_config/client.yaml).  If pysui is not installed
    or the wallet is not configured, ``is_connected`` will be False and all
    on-chain operations will raise ``RuntimeError``.

    Attributes:
        active_address: The connected Sui wallet address (0x…).
        is_connected:   True if a wallet is successfully loaded.
    """

    def __init__(self, rpc_url: Optional[str] = None) -> None:
        self.active_address: str = "0x" + "0" * 64
        self.is_connected: bool  = False
        self._config:  Any       = None
        self._client:  Any       = None
        self._rpc_url            = rpc_url

        self._try_connect()

        # Real CLI-based client for direct Sui interactions (no pysui needed)
        use_mocks = os.environ.get("WALRUSOS_USE_MOCKS", "").lower() in ("1", "true", "yes")
        if not use_mocks:
            try:
                from walrusos.adapters.sui_real import RealSuiClient
                self._real_client: Any = RealSuiClient()
                # If pysui failed but CLI works, update connection state
                if not self.is_connected and self._real_client.active_address:
                    self.active_address = self._real_client.active_address
                    self.is_connected = True
            except Exception:
                self._real_client = None
        else:
            self._real_client = None

    @property
    def real(self):
        """
        Access the ``RealSuiClient`` for CLI-based Sui transactions.

        Returns None when ``WALRUSOS_USE_MOCKS=1`` is set.
        """
        return self._real_client

    def _try_connect(self) -> None:
        """
        Attempt to load the pysui wallet config and create an async client.

        Failures are caught and logged — the SDK loads cleanly even without
        a configured Sui wallet.
        """
        try:
            SuiConfig, SuiClient, _ = _import_pysui()
            self._config = SuiConfig.default_config()

            # Respect an explicit RPC URL override
            if self._rpc_url:
                self._config.rpc_url = self._rpc_url

            # pysui >= 0.50 exposes active_address as an object with .address
            addr = self._config.active_address
            self.active_address = addr.address if hasattr(addr, "address") else str(addr)

            # SuiClient is async; we hold the config and build the client on demand
            self._client    = SuiClient(self._config)
            self.is_connected = True
            logger.info("Sui wallet connected: %s", self.active_address)

        except ImportError:
            logger.warning(
                "pysui not installed — falling back to sui CLI for on-chain operations."
            )
        except Exception as exc:
            logger.warning(
                "Sui wallet not configured (%s). "
                "Run `sui client active-address` to verify setup.",
                exc,
            )

    def _require_connected(self) -> None:
        if not self.is_connected:
            raise RuntimeError(
                "Sui wallet not configured. "
                "Run `sui client active-address` and then `walrusos login`."
            )

    def login(self) -> str:
        """Return the active Sui address. Raises if not connected."""
        self._require_connected()
        return self.active_address

    async def create_workspace(self, name: str, package_id: str) -> str:
        """
        Execute a PTB to create a Workspace object on Sui.

        Calls: ``<package_id>::identity::create_workspace(name: String)``

        Returns the Sui object ID of the created Workspace.
        Raises RuntimeError if the wallet is not connected or gas is insufficient.
        """
        self._require_connected()
        _, _, SuiTransactionAsync = _import_pysui()

        txn = SuiTransactionAsync(client=self._client)
        txn.move_call(
            target=f"{package_id}::identity::create_workspace",
            arguments=[txn.pure(value=name, encode_as="string")],
            type_arguments=[],
        )
        result = await txn.execute(gas_budget=50_000_000)

        if result.is_err():
            raise RuntimeError(
                f"create_workspace PTB failed: {result.result_string}"
            )

        created = result.result_data.to_dict().get("objectChanges", [])
        for change in created:
            if change.get("type") == "created":
                return change["objectId"]

        raise RuntimeError("create_workspace succeeded but no created object found in result")

    async def register_agent(
        self,
        workspace_id: str,
        name: str,
        public_key: str,
        trust_root: str,
        package_id: str,
    ) -> str:
        """
        Execute a PTB to register an AgentIdentity object on Sui.

        Calls: ``<package_id>::identity::register_agent(workspace_id, name, public_key, trust_root)``

        Returns the Sui object ID of the created AgentIdentity.
        """
        self._require_connected()
        _, _, SuiTransactionAsync = _import_pysui()

        txn = SuiTransactionAsync(client=self._client)
        txn.move_call(
            target=f"{package_id}::identity::register_agent",
            arguments=[
                txn.pure(value=workspace_id, encode_as="address"),
                txn.pure(value=name,         encode_as="string"),
                txn.pure(value=bytes.fromhex(public_key), encode_as="vector<u8>"),
                txn.pure(value=bytes.fromhex(trust_root), encode_as="vector<u8>"),
            ],
            type_arguments=[],
        )
        result = await txn.execute(gas_budget=50_000_000)
        if result.is_err():
            raise RuntimeError(f"register_agent PTB failed: {result.result_string}")

        for change in result.result_data.to_dict().get("objectChanges", []):
            if change.get("type") == "created":
                return change["objectId"]
        raise RuntimeError("register_agent succeeded but no object in result")

    async def update_agent_status(
        self, agent_id: str, new_status: int, package_id: str
    ) -> str:
        """
        Execute a PTB to update an AgentIdentity status.

        Calls: ``<package_id>::identity::update_agent_status(agent: address, new_status: u8)``
        Returns the transaction digest.
        """
        self._require_connected()
        _, _, SuiTransactionAsync = _import_pysui()
        txn = SuiTransactionAsync(client=self._client)
        txn.move_call(
            target=f"{package_id}::identity::update_agent_status",
            arguments=[
                txn.object(agent_id),
                txn.pure(value=new_status, encode_as="u8"),
            ],
            type_arguments=[],
        )
        result = await txn.execute(gas_budget=50_000_000)
        if result.is_err():
            raise RuntimeError(f"update_agent_status PTB failed: {result.result_string}")
        return result.result_data.digest

    async def increment_agent_counters(
        self, agent_id: str, execution: int, memory: int, artifact: int, package_id: str
    ) -> str:
        """
        Execute a PTB to increment an AgentIdentity's counters.

        Calls: ``<package_id>::identity::increment_counters(agent, execution, memory, artifact)``
        Returns the transaction digest.
        """
        self._require_connected()
        _, _, SuiTransactionAsync = _import_pysui()
        txn = SuiTransactionAsync(client=self._client)
        txn.move_call(
            target=f"{package_id}::identity::increment_counters",
            arguments=[
                txn.object(agent_id),
                txn.pure(value=execution, encode_as="u64"),
                txn.pure(value=memory, encode_as="u64"),
                txn.pure(value=artifact, encode_as="u64"),
            ],
            type_arguments=[],
        )
        result = await txn.execute(gas_budget=50_000_000)
        if result.is_err():
            raise RuntimeError(f"increment_agent_counters PTB failed: {result.result_string}")
        return result.result_data.digest

    async def delegate_capability(
        self,
        target_stream_address: str,
        bitmask: int,
        recipient: str,
        package_id: str,
        valid_until_epoch: int = 0,
    ) -> str:
        """
        Delegate a Capability token to ``recipient`` for ``target_stream_address``.

        Bitmask encoding:
          0b0001 = read
          0b0010 = write
          0b0100 = fork
          0b1000 = merge

        Args:
            target_stream_address: Address of the stream to grant access to.
            bitmask:               Permission bitmask.
            recipient:             Sui address of the recipient.
            package_id:            Deployed WalrusOS Move package ID.
            valid_until_epoch:     Sui epoch after which the capability expires.
                                   0 (default) means the capability never expires.

        Calls: ``<package_id>::identity::delegate_capability(
            target_stream: address, bitmask: u64,
            recipient: address, valid_until_epoch: u64
        )``

        Returns the Sui transaction digest.
        """
        self._require_connected()
        _, _, SuiTransactionAsync = _import_pysui()

        txn = SuiTransactionAsync(client=self._client)
        txn.move_call(
            target=f"{package_id}::identity::delegate_capability",
            arguments=[
                txn.pure(value=target_stream_address, encode_as="address"),
                txn.pure(value=bitmask,               encode_as="u64"),
                txn.pure(value=recipient,              encode_as="address"),
                txn.pure(value=valid_until_epoch,      encode_as="u64"),
            ],
            type_arguments=[],
        )
        result = await txn.execute(gas_budget=50_000_000)
        if result.is_err():
            raise RuntimeError(f"delegate_capability PTB failed: {result.result_string}")
        return result.result_data.digest

    async def revoke_capability(self, capability_object_id: str, package_id: str) -> str:
        """
        Revoke a Capability by consuming and destroying the capability object.

        Calls: ``<package_id>::identity::revoke_capability(cap: Capability)``

        The Capability object must be owned by the connected wallet.
        Returns the Sui transaction digest.
        """
        self._require_connected()
        _, _, SuiTransactionAsync = _import_pysui()

        txn = SuiTransactionAsync(client=self._client)
        txn.move_call(
            target=f"{package_id}::identity::revoke_capability",
            arguments=[txn.object(capability_object_id)],
            type_arguments=[],
        )
        result = await txn.execute(gas_budget=50_000_000)
        if result.is_err():
            raise RuntimeError(f"revoke_capability PTB failed: {result.result_string}")
        return result.result_data.digest

    async def create_memory_stream(
        self, agent_address: str, package_id: str
    ) -> str:
        """
        Create a MemoryStream anchor object on Sui.

        Calls: ``<package_id>::memory::create_stream(agent_id: address)``

        Returns the Sui object ID of the created MemoryStream.
        """
        self._require_connected()
        _, _, SuiTransactionAsync = _import_pysui()

        txn = SuiTransactionAsync(client=self._client)
        txn.move_call(
            target=f"{package_id}::memory::create_stream",
            arguments=[txn.pure(value=agent_address, encode_as="address")],
            type_arguments=[],
        )
        result = await txn.execute(gas_budget=50_000_000)
        if result.is_err():
            raise RuntimeError(f"create_stream PTB failed: {result.result_string}")

        # Phase 4: memory::create_stream now mints a MemoryStream AND a Capability
        stream_id = None
        cap_id = None
        for change in result.result_data.to_dict().get("objectChanges", []):
            if change.get("type") == "created":
                obj_type = change.get("objectType", "")
                if "MemoryStream" in obj_type:
                    stream_id = change["objectId"]
                elif "Capability" in obj_type:
                    cap_id = change["objectId"]
        
        if not stream_id:
            raise RuntimeError("create_stream succeeded but no MemoryStream object in result")
            
        return stream_id, cap_id

    async def anchor_event(
        self,
        stream_object_id: str,
        workspace_object_id: str,
        agent_object_id: str,
        capability_object_id: str,
        parent_id: str,
        blob_id: str,
        package_id: str,
        event_hash: Optional[str] = None,
        signature: Optional[str] = None,
    ) -> str:
        """
        Emit a MemoryEvent on Sui for tamper-evident anchoring.

        Calls: ``<package_id>::memory::append_event`` or ``append_signed_event``

        The MemoryStream object must be owned by the connected wallet.
        Returns the Sui transaction digest.
        """
        self._require_connected()
        _, _, SuiTransactionAsync = _import_pysui()

        txn = SuiTransactionAsync(client=self._client)
        if event_hash and signature:
            txn.move_call(
                target=f"{package_id}::memory::append_signed_event",
                arguments=[
                    txn.object(workspace_object_id),
                    txn.object(agent_object_id),
                    txn.object(capability_object_id),
                    txn.object(stream_object_id),
                    txn.pure(value=parent_id, encode_as="string"),
                    txn.pure(value=blob_id,   encode_as="string"),
                    txn.pure(value=event_hash, encode_as="string"),
                    txn.pure(value=signature,  encode_as="string"),
                    txn.object("0x6"), # Clock object
                ],
                type_arguments=[],
            )
        else:
            txn.move_call(
                target=f"{package_id}::memory::append_event",
                arguments=[
                    txn.object(stream_object_id),
                    txn.pure(value=parent_id, encode_as="string"),
                    txn.pure(value=blob_id,   encode_as="string"),
                ],
                type_arguments=[],
            )
        result = await txn.execute(gas_budget=10_000_000)
        if result.is_err():
            raise RuntimeError(f"anchor_event PTB failed: {result.result_string}")
        return result.result_data.digest


# ── SuiLedgerAdapter ──────────────────────────────────────────────────────────

class SuiLedgerAdapter(LedgerAdapter):
    """
    Hybrid SQLite + Sui ledger adapter.

    Write path:
      1. Write event to SQLite (synchronous, authoritative for reads)
      2. Emit anchor event on Sui (async, fire-and-forget, best-effort)

    Read path:
      Always from SQLite — zero Sui RPC latency.

    Network Recovery:
      sync_events_from_network() allows full database reconstruction from the Sui RPC.

    On-chain anchoring:
      Requires ``package_id`` and a configured wallet.
      Without these, the adapter runs in SQLite-only mode:
        - All data still goes to Walrus (real storage)
        - No Sui event emissions (no chain anchoring)
        - Full functionality, minus the tamper-evident audit log

    MemoryStream Sui object registry:
      A local dict maps stream_id (UUID) → Sui object ID.
      Populated when create_stream() executes a PTB.
      Not persisted across restarts — will be moved to SQLite in v0.2.
    """

    def __init__(
        self,
        identity:   SuiIdentityAdapter,
        package_id: Optional[str],
        db_path:    str = "~/.walrusos/walrusos.db",
    ) -> None:
        from walrusos.adapters.sqlite_ledger import SQLiteLedger
        from walrusos.config import load_config
        self._sqlite = SQLiteLedger(db_path)
        self.package_id = package_id or load_config().package_id
        self._identity = identity
        self.identity = identity
        
        self._stream_objects: Dict[str, str] = self._sqlite.get_sui_stream_objects()
        if self._stream_objects:
            logger.info(
                "SuiLedgerAdapter: restored %d stream object mapping(s) from SQLite",
                len(self._stream_objects),
            )

    def __getattr__(self, name: str) -> Any:
        """
        Delegate any unknown attribute to the inner SQLiteLedger.

        This allows EventStoreEngine and other callers to use SQLiteLedger
        methods (get_events_for_agent, get_events_for_workspace, etc.) via
        the SuiLedgerAdapter without explicitly forwarding every method.
        Explicit overrides in SuiLedgerAdapter always take precedence since
        __getattr__ is only called after the normal attribute lookup fails.
        """
        return getattr(self._sqlite, name)

    async def sync_events_from_network(self) -> None:
        """
        Reconstruct the local SQLite event store by querying ProtocolEventAnchored 
        events from the Sui RPC, and fetching their payloads from Walrus.
        """
        self._identity._require_connected()
        if not self.package_id:
            raise RuntimeError("Cannot sync from network without package_id configured.")
            
        logger.info("Starting network sync from Sui RPC...")
        
        # Query Sui events for our module: <package_id>::protocol::ProtocolEventAnchored
        try:
            from pysui.sui.sui_builders.get_builders import GetEvents # type: ignore
            from pysui.sui.sui_types.scalars import SuiString # type: ignore
        except ImportError:
            raise RuntimeError("pysui is required to sync events.")
            
        client = self._identity._client
        event_struct = f"{self.package_id}::protocol::ProtocolEventAnchored"
        
        # We need to construct a builder query and paginate.
        # For simplicity in this implementation, we assume a basic query
        query = GetEvents(query={"MoveEventType": event_struct}, cursor=None, limit=100)
        
        events_retrieved = []
        has_next_page = True
        
        while has_next_page:
            result = await client.execute(query)
            if result.is_err():
                raise RuntimeError(f"Failed to query Sui events: {result.result_string}")
                
            page = result.result_data
            for ev in page.data:
                parsed = ev.parsed_json
                events_retrieved.append(parsed)
                
            if page.has_next_page:
                query.cursor = page.next_cursor
            else:
                has_next_page = False
                
        logger.info(f"Found {len(events_retrieved)} anchored events on Sui. Reconstructing payloads...")
        
        # We assume the caller will map blob_id -> payload using WalrusStorageAdapter
        # and then append to sqlite.
        # This requires access to storage, so we yield the parsed headers to the caller or engine.
        return events_retrieved



    def _can_anchor(self) -> bool:
        """True when we have both a connected wallet and a deployed package."""
        # If we have a package_id, also emit the anchor event to Sui testnet
        if self.package_id:
            return self.identity.is_connected
        return False

    def _emit_anchor_bg(
        self,
        stream_id: uuid.UUID,
        event: MemoryEvent,
    ) -> None:
        """
        Schedule a best-effort Sui event anchor in the background.

        Uses ``asyncio.create_task`` so it never blocks the write path.
        Errors are caught and logged — a failed anchor does not corrupt
        the local SQLite ledger.
        """
        if not self._can_anchor():
            return

        sui_obj_id = self._stream_objects.get(str(stream_id))
        if not sui_obj_id:
            logger.debug(
                "No Sui MemoryStream object registered for stream %s — "
                "skipping on-chain anchor for event %s",
                stream_id,
                event.id[:16],
            )
            return

        async def _anchor() -> None:
            try:
                # Phase 4 Capability Enforcement
                agent_id = getattr(event, "agent_id", None)
                if not agent_id:
                    logger.debug("Event %s lacks agent_id, cannot anchor", event.id[:16])
                    return
                
                agent_identity = self._sqlite.get_agent_identity(agent_id)
                if not agent_identity or not agent_identity.sui_object_id:
                    logger.debug("Agent %s lacks Sui object ID, cannot anchor", agent_id)
                    return
                
                workspace_object_id = self._sqlite.get_workspace_sui_object(agent_identity.workspace_id)
                if not workspace_object_id:
                    logger.debug("Workspace lacks Sui object ID, cannot anchor")
                    return
                
                caps = self._sqlite.get_capabilities_for_stream(sui_obj_id)
                if not caps:
                    logger.debug("No capabilities found for stream %s, cannot anchor", stream_id)
                    return
                capability_object_id = caps[0].sui_object_id

                digest = await self.identity.anchor_event(
                    stream_object_id=sui_obj_id,
                    workspace_object_id=workspace_object_id,
                    agent_object_id=agent_identity.sui_object_id,
                    capability_object_id=capability_object_id,
                    parent_id=event.parent_id,
                    blob_id=event.content_blob_id,
                    package_id=self.package_id,  # type: ignore[arg-type]
                    event_hash=getattr(event, "event_hash", None),
                    signature=getattr(event, "signature", None),
                )
                logger.debug(
                    "Event %s anchored on Sui (tx: %s)", event.id[:16], digest[:16]
                )
            except Exception as exc:
                logger.warning(
                    "Sui anchor failed for event %s: %s", event.id[:16], exc
                )

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_anchor())
        except RuntimeError:
            # No event loop running (e.g., called from sync context) — skip anchor
            pass

    # ── LedgerAdapter interface ───────────────────────────────────────────────

    async def create_stream(self, agent_id: uuid.UUID) -> uuid.UUID:
        """
        Create a new MemoryStream in SQLite.
        If package_id is set and wallet is connected, also create a Sui MemoryStream object.
        The Sui object ID is persisted to SQLite immediately so it survives restarts.
        """
        stream_id = await self._sqlite.create_stream(agent_id)

        if self._can_anchor():
            try:
                sui_obj, cap_obj = await self.identity.create_memory_stream(
                    agent_address=self.identity.active_address,
                    package_id=self.package_id,  # type: ignore[arg-type]
                )
                self._stream_objects[str(stream_id)] = sui_obj
                # P0 Fix: persist to SQLite immediately so the mapping survives restart
                self._sqlite.save_sui_stream_object(stream_id, sui_obj)
                if cap_obj:
                    self._sqlite.save_capability(cap_obj, sui_obj, 15, 0)
                logger.info(
                    "MemoryStream %s created on Sui (object: %s, cap: %s)", stream_id, sui_obj, cap_obj
                )
            except Exception as exc:
                logger.warning(
                    "Sui MemoryStream creation failed for %s: %s. "
                    "Continuing in SQLite-only mode.",
                    stream_id,
                    exc,
                )

        return stream_id

    async def register_stream(self, stream_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        """Register a deterministic stream UUID (delegates to SQLiteLedger)."""
        await self._sqlite.register_stream(stream_id, agent_id)

    async def delete_stream(self, stream_id: uuid.UUID) -> None:
        await self._sqlite.delete_stream(stream_id)
        self._stream_objects.pop(str(stream_id), None)
        # P0 Fix: remove from SQLite persistence too
        self._sqlite.delete_sui_stream_object(stream_id)

    async def append_event(self, stream_id: uuid.UUID, event: MemoryEvent) -> None:
        """
        Write event to SQLite (authoritative), then fire-and-forget Sui anchor.
        """
        await self._sqlite.append_event(stream_id, event)
        self._emit_anchor_bg(stream_id, event)

    async def get_event(self, event_id: str) -> Optional[MemoryEvent]:
        return await self._sqlite.get_event(event_id)

    async def get_head(self, stream_id: uuid.UUID) -> Optional[str]:
        return await self._sqlite.get_head(stream_id)

    async def list_events(self, stream_id: uuid.UUID) -> List[MemoryEvent]:
        return await self._sqlite.list_events(stream_id)

    async def get_epoch_counter(self, stream_id: uuid.UUID) -> int:
        return await self._sqlite.get_epoch_counter(stream_id)

    async def append_protocol_event(self, event: Any) -> None:
        """Persist a ProtocolEvent to SQLite (delegates to inner SQLiteLedger)."""
        if hasattr(self._sqlite, "append_protocol_event"):
            await self._sqlite.append_protocol_event(event)

    async def anchor_protocol_event(self, event: Any) -> Optional[str]:
        """
        Best-effort Sui anchor for a ProtocolEvent via RealSuiClient CLI.

        Returns the tx_digest on success, None on failure or in mock mode.
        Errors are logged but never propagated.
        """
        real = getattr(self._identity, "_real_client", None)
        if real is None:
            return None
        try:
            import asyncio as _asyncio
            import hashlib
            event_hash = hashlib.sha256(event.event_id.encode()).digest()
            event_type_val = (
                event.event_type.value
                if hasattr(event.event_type, "value")
                else str(event.event_type)
            )
            result = await _asyncio.to_thread(
                real.anchor_event,
                blob_id=event.blob_id or "",
                event_hash=event_hash,
                event_id=event.event_id,
                event_type=event_type_val,
                workspace_id=event.workspace_id,
                agent_id=event.agent_id or "default",
                parent_event=event.parent_event or "genesis",
            )
            tx = result.get("tx_digest")
            if tx:
                logger.info(
                    "ProtocolEvent %s anchored on Sui (tx: %s)",
                    event.event_id[:16], tx[:16],
                )
            return tx
        except Exception as exc:
            # Log at ERROR level with the full exception details. The previous
            # WARNING + truncated %s buried the real CLI output and made the
            # anchoring failure look like a no-op for a long time.
            logger.error(
                "Sui anchor_protocol_event failed for event %s:\n%s",
                getattr(event, "event_id", "?")[:16],
                exc,
                exc_info=False,
            )
            return None
