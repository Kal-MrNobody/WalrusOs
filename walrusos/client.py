"""
WalrusOS — Top-level developer entrypoint.

Configuration priority:
  1. Arguments passed to WalrusOS()
  2. WALRUSOS_* environment variables
  3. ~/.walrusos/config.json
  4. Built-in defaults (testnet)

Usage:
    # Production (reads wallet from ~/.sui/sui_config, config from ~/.walrusos/)
    runtime = WalrusOS()

    # Development / testing (all in-process, no network)
    runtime = WalrusOS(use_mocks=True)

    # Explicit testnet (same as default)
    runtime = WalrusOS(
        publisher_url="https://publisher.walrus-testnet.walrus.space",
        aggregator_url="https://aggregator.walrus-testnet.walrus.space",
    )
"""
from __future__ import annotations

import logging
from typing import Optional

from walrusos.config import load_config, WalrusOSConfig
from walrusos.engine.event_store import EventStoreEngine
from walrusos.engine.memory import MemoryEngine
from walrusos.sdk.workspace import WorkspaceClient

logger = logging.getLogger(__name__)


class WalrusOS:
    """
    Top-level WalrusOS runtime.

    Wires storage, ledger, and vector adapters together into a single
    EventStoreEngine and exposes the workspace() API.

    In production mode (use_mocks=False, the default):
      - Storage: WalrusAdapter (Walrus testnet/mainnet HTTP)
      - Ledger:  SuiLedgerAdapter (SQLite + Sui event anchoring)
      - Vector:  InMemoryVector (TF-IDF, zero deps — swap for embedding model if needed)

    In mock mode (use_mocks=True):
      - Storage: InMemoryStorage
      - Ledger:  InMemoryLedger
      - Vector:  InMemoryVector
      Used for unit tests and offline development.
    """

    def __init__(
        self,
        use_mocks:      Optional[bool] = None,
        publisher_url:  Optional[str]  = None,
        aggregator_url: Optional[str]  = None,
        walrus_epochs:  Optional[int]  = None,
        sui_rpc_url:    Optional[str]  = None,
        package_id:     Optional[str]  = None,
        db_path:        Optional[str]  = None,
    ) -> None:
        # Load config (env vars + JSON file + defaults)
        cfg: WalrusOSConfig = load_config()

        # Allow constructor args to override config
        if publisher_url:
            cfg.publisher_url = publisher_url
        if aggregator_url:
            cfg.aggregator_url = aggregator_url
        if walrus_epochs is not None:
            cfg.walrus_epochs = walrus_epochs
        if sui_rpc_url:
            cfg.sui_rpc_url = sui_rpc_url
        if package_id:
            cfg.package_id = package_id
        if db_path:
            cfg.db_path = db_path

        # use_mocks: explicit arg > env > config > False
        _use_mocks = cfg.use_mocks
        if use_mocks is not None:
            _use_mocks = use_mocks

        if _use_mocks:
            self._init_mocks()
        else:
            self._init_production(cfg)

        self._event_store  = EventStoreEngine(self._ledger, self._storage, self._vector)
        self._memory_engine = MemoryEngine(self._ledger, self._storage, self._vector)
        self._engine = self._event_store
        self._config  = cfg
        from walrusos.runtime.event_bus import EventMesh
        self.event_mesh = EventMesh()
        self.event_bus  = self.event_mesh  # backward-compat alias

    def _init_mocks(self) -> None:
        """Wire all InMemory adapters (no network, for tests and dev)."""
        from walrusos.adapters.in_memory import (
            InMemoryLedger,
            InMemoryStorage,
            InMemoryVector,
        )
        self._storage = InMemoryStorage()
        self._ledger  = InMemoryLedger()
        self._vector  = InMemoryVector()
        logger.debug("WalrusOS initialised in mock mode (no network)")

    def _init_production(self, cfg: WalrusOSConfig) -> None:
        """
        Wire production adapters:
          - WalrusAdapter    → Walrus testnet/mainnet
          - SuiLedgerAdapter → SQLite cache + Sui event anchoring
          - InMemoryVector   → TF-IDF (no ML deps)

        Initialization order:
          1. SuiIdentityAdapter — needed to supply wallet_address to KeyStore.
          2. WalrusAdapter      — uses KeyStore for persistent AES key management.
          3. SuiLedgerAdapter   — restores Sui stream object mappings from SQLite.
          4. InMemoryVector     — TF-IDF, no external deps.
        """
        from walrusos.adapters.walrus import WalrusAdapter
        from walrusos.adapters.sui import SuiIdentityAdapter, SuiLedgerAdapter
        from walrusos.adapters.in_memory import InMemoryVector

        # Step 1 — identity / wallet (must be first for KEK derivation)
        self._identity = SuiIdentityAdapter(rpc_url=cfg.sui_rpc_url)
        wallet_address = cfg.sui_address or (
            self._identity.active_address if self._identity.is_connected else None
        )

        # Step 2 — storage with persistent KeyStore (P0 Fix 1)
        self._storage = WalrusAdapter(
            publisher_url  = cfg.publisher_url,
            aggregator_url = cfg.aggregator_url,
            epochs         = cfg.walrus_epochs,
            db_path        = cfg.db_path,
            wallet_address = wallet_address,
        )

        # Step 3 — ledger: restores Sui stream objects from SQLite (P0 Fix 3)
        self._ledger = SuiLedgerAdapter(
            identity   = self._identity,
            package_id = cfg.package_id,
            db_path    = cfg.db_path,
        )

        # Step 4 — vector index
        self._vector = InMemoryVector()

        if not self._identity.is_connected:
            logger.warning(
                "Sui wallet not connected. "
                "Data will be stored on Walrus but NOT anchored on Sui. "
                "Run `walrusos login` to connect a wallet."
            )
        elif not cfg.package_id or cfg.package_id == "0x0":
            logger.warning(
                "WALRUSOS_PACKAGE_ID not set. "
                "Data will be stored on Walrus but NOT anchored on Sui. "
                "Deploy the Move package: python scripts/deploy_walrusos.py"
            )
        else:
            logger.info(
                "WalrusOS initialised (wallet: %s, package: %s)",
                self._identity.active_address[:16],
                cfg.package_id[:16],
            )

    def workspace(self, name: str) -> WorkspaceClient:
        """
        Open a workspace.

        Workspaces are the top-level container for agents and streams.
        They are lazily initialized — the workspace is registered in the
        ledger only when the first event is written.

        Parameters
        ----------
        name:
            Human-readable workspace name.  Use consistent names across
            process restarts — the same name always resolves to the same
            workspace UUID.

        Example
        -------
        ::

            runtime   = WalrusOS(use_mocks=True)
            workspace = runtime.workspace("research")
            agent     = workspace.agent("Researcher")
            stream    = agent.stream("findings")

            await stream.append({"title": "Attention Is All You Need"})
        """
        owner_wallet: str = ""
        if hasattr(self, "_identity"):
            owner_wallet = getattr(self._identity, "active_address", "") or ""
        elif hasattr(self, "_config"):
            owner_wallet = getattr(self._config, "sui_address", "") or ""

        return WorkspaceClient(
            self._engine,
            self._memory_engine,
            name,
            owner_wallet=owner_wallet,
            event_bus=self.event_bus,
        )

    async def run_agents(self, *agents: "AgentClient") -> None:
        """Starts all agents listening. Runs until interrupted."""
        # EventBus operations are non-blocking, so we just keep the loop alive.
        if any(hasattr(a, "_listen") for a in agents):
            # Future-proofing if agents implement an explicit listen loop
            coros = [a._listen() for a in agents if hasattr(a, "_listen")]
            if coros:
                await asyncio.gather(*coros)
        else:
            await asyncio.Event().wait()

    def to_dict(self) -> Dict[str, Any]:
        """Only expose the public API in IDE autocomplete."""
        return ["workspace"]

    # ── Dunder ────────────────────────────────────────────────────────────────

    def __dir__(self) -> list:
        """Only expose the public API in IDE autocomplete."""
        return ["workspace"]

    def __repr__(self) -> str:
        mode = "mock" if getattr(self._config, "use_mocks", False) else "production"
        network = getattr(self._config, "sui_rpc_url", "unknown")
        return f"<WalrusOS mode={mode!r} network={network!r}>"
