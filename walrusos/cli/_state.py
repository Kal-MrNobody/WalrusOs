"""
WalrusOS CLI — Shared state, helpers, and Rich console.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.theme import Theme

# ── Console ───────────────────────────────────────────────────────────────────
THEME = Theme({
    "info":    "bold cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "error":   "bold red",
    "accent":  "bold magenta",
    "muted":   "dim",
    "blob":    "bold green",
    "stream":  "bold cyan",
    "agent":   "bold magenta",
})
console = Console(theme=THEME)

# ── Config paths ──────────────────────────────────────────────────────────────
CONFIG_DIR  = Path.home() / ".walrusos"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE    = CONFIG_DIR / "walrusos.log"

def load_config() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def save_config(data: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def get_config(key: str, default: Any = None) -> Any:
    return load_config().get(key, default)

def require_login() -> str:
    """Exits with a helpful error if the user isn't logged in."""
    address = get_config("sui_address")
    if not address:
        console.print("[error]Not logged in.[/] Run [accent]walrusos login[/] first.")
        raise typer.Exit(1)
    return address  # type: ignore[return-value]

def append_log(message: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as f:
        from datetime import datetime
        f.write(f"[{datetime.now().isoformat()}] {message}\n")

# ── Runtime factory ───────────────────────────────────────────────────────────

def get_runtime(use_mocks: bool = False):
    """
    Return a WalrusOS runtime using production adapters from config.

    In CI or when WALRUSOS_USE_MOCKS=1 is set, returns a mock runtime.
    """
    from walrusos import WalrusOS
    # Allow env override for CI
    if os.environ.get("WALRUSOS_USE_MOCKS", "").lower() in ("1", "true", "yes"):
        return WalrusOS(use_mocks=True)
    return WalrusOS(use_mocks=use_mocks)
