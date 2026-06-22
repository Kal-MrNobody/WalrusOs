"""
WalrusOS Configuration System.

All configuration is read in this priority order:
  1. Environment variables  (highest priority)
  2. ~/.walrusos/config.json  (written by `walrusos login` / `walrusos init`)
  3. Hardcoded defaults  (lowest priority)

Environment variable names match the JSON key names, prefixed with WALRUSOS_.
Example: WALRUSOS_PACKAGE_ID overrides config["package_id"].
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Paths ─────────────────────────────────────────────────────────────────────

CONFIG_DIR  = Path.home() / ".walrusos"
CONFIG_FILE = CONFIG_DIR / "config.json"
DB_PATH     = CONFIG_DIR / "walrusos.db"

# ── Testnet defaults ──────────────────────────────────────────────────────────

_TESTNET_PUBLISHER  = "https://publisher.walrus-testnet.walrus.space"
_TESTNET_AGGREGATOR = "https://aggregator.walrus-testnet.walrus.space"
_TESTNET_SUI_RPC    = "https://fullnode.testnet.sui.io:443"

PACKAGE_ID       = "0x3339a7cf05650525acb7233eb68c584974b164c4ff03d65e3de8169e41d369e8"
LEDGER_ANCHOR_ID = "0x0f96188ee403ecc58bd498fb874ef3037078775deb68e2061964ac1d3827e27d"
UPGRADE_CAP_ID   = "0xac27e694fd2fae8743b2735def5f04fa4cc775d19d58df24f550f5e6985d0067"
DEPLOYER_ADDRESS = "0x114702611c4e6411af933347f2268b32f286af5a05478af8516e670aeb756de1"
NETWORK          = "testnet"


# ── Config dataclass ──────────────────────────────────────────────────────────

@dataclass
class WalrusOSConfig:
    """
    All runtime configuration for WalrusOS.

    Fields map 1-to-1 with ``~/.walrusos/config.json`` keys and
    ``WALRUSOS_*`` environment variables.
    """

    # ── Walrus network ────────────────────────────────────────────────────────
    publisher_url:  str   = _TESTNET_PUBLISHER
    aggregator_url: str   = _TESTNET_AGGREGATOR
    walrus_epochs:  int   = 5

    # ── Sui network ───────────────────────────────────────────────────────────
    sui_rpc_url:    str           = _TESTNET_SUI_RPC
    sui_address:    Optional[str] = None   # Active Sui wallet address
    package_id:     Optional[str] = PACKAGE_ID   # Deployed WalrusOS Move package

    # ── Local storage ─────────────────────────────────────────────────────────
    db_path:        str   = str(DB_PATH)

    # ── Feature flags ─────────────────────────────────────────────────────────
    use_mocks:      bool  = False   # True = all InMemory, no network calls
    chain_anchoring: bool = True    # False = Walrus only, no Sui event emission


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_file() -> dict:
    """Load the JSON config file if it exists."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _env(key: str) -> Optional[str]:
    """Read a WALRUSOS_<KEY> environment variable (case-insensitive)."""
    return os.environ.get(f"WALRUSOS_{key.upper()}")


def load_config() -> WalrusOSConfig:
    """
    Build a ``WalrusOSConfig`` by merging defaults ← file ← environment.

    This function is cheap to call repeatedly; config objects are immutable.
    """
    file_data = _load_file()

    def get(key: str, default):
        """env → file → default"""
        env_val = _env(key)
        if env_val is not None:
            return env_val
        return file_data.get(key, default)

    def get_bool(key: str, default: bool) -> bool:
        raw = get(key, str(default))
        return str(raw).lower() in ("1", "true", "yes")

    def get_int(key: str, default: int) -> int:
        try:
            return int(get(key, default))
        except (TypeError, ValueError):
            return default

    return WalrusOSConfig(
        publisher_url   = get("publisher_url",  _TESTNET_PUBLISHER),
        aggregator_url  = get("aggregator_url", _TESTNET_AGGREGATOR),
        walrus_epochs   = get_int("walrus_epochs", 5),
        sui_rpc_url     = get("sui_rpc_url",    _TESTNET_SUI_RPC),
        sui_address     = get("sui_address",    None),
        package_id      = get("package_id",     PACKAGE_ID),
        db_path         = get("db_path",        str(DB_PATH)),
        use_mocks       = get_bool("use_mocks", False),
        chain_anchoring = get_bool("chain_anchoring", True),
    )


def save_config(updates: dict) -> None:
    """
    Merge ``updates`` into the config file and write it back.

    Creates ``~/.walrusos/`` if it does not exist.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    current = _load_file()
    current.update(updates)
    CONFIG_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")


def get_config_value(key: str, default=None):
    """Convenience: read a single config value."""
    return getattr(load_config(), key, default)
