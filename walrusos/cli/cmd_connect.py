"""
walrusos connect — generate MCP config for supported AI tools.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax

from walrusos.cli._state import console

app = typer.Typer(
    name="connect",
    help="Generate MCP configuration for AI tools.",
    no_args_is_help=True,
)

_FRAMEWORKS = {
    "claude-code": "Claude Desktop / Claude Code",
    "cursor":      "Cursor",
    "windsurf":    "Windsurf",
    "gemini":      "Gemini CLI",
    "antigravity": "Antigravity",
    "custom":      "Custom / other MCP client",
}

_FRAMEWORK_DEFAULTS = {
    "claude-code": "Claude Code",
    "cursor":      "Cursor",
    "windsurf":    "Windsurf",
    "gemini":      "Gemini",
    "antigravity": "Antigravity",
    "custom":      "MCP Agent",
}


def _mcp_entry(framework: str) -> dict:
    """Build the MCP server entry for a given framework, including env vars
    so the connecting agent shows up with the right name & framework in the
    WalrusOS dashboard."""
    return {
        "command": "walrusos",
        "args":    ["mcp", "start"],
        "env": {
            "WALRUSOS_MCP_AGENT_NAME": _FRAMEWORK_DEFAULTS.get(framework, "MCP Agent"),
            "WALRUSOS_MCP_FRAMEWORK":  framework,
            "WALRUSOS_USE_MOCKS":      "0",
        },
    }


def _mcp_block(framework: str) -> str:
    """JSON snippet shown to the user for copy/paste."""
    return json.dumps({"mcpServers": {"walrusos": _mcp_entry(framework)}}, indent=2)


# Generic snippet for the --list / fallback path
_MCP_BLOCK = _mcp_block("custom")


def _claude_config_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "~")) / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "claude" / "claude_desktop_config.json"


@app.command("connect")
def connect_cmd(
    framework: Optional[str] = typer.Argument(None, help="Framework name (claude-code, cursor, windsurf, …)"),
    list_frameworks: bool     = typer.Option(False, "--list",   help="List all supported frameworks"),
    verify:          bool     = typer.Option(False, "--verify", help="Verify MCP server + all tools"),
    write:           bool     = typer.Option(False, "--write",  help="Write config file automatically"),
) -> None:
    """Generate or write MCP config for a supported AI tool."""

    if list_frameworks:
        console.print("\n[bold]Supported frameworks:[/]\n")
        for key, label in _FRAMEWORKS.items():
            console.print(f"  [accent]{key:<14}[/] {label}")
        console.print()
        return

    if verify:
        _verify_mcp()
        return

    if not framework:
        console.print("[red]Error:[/] specify a framework (e.g. [accent]walrusos connect claude-code[/]) or --list")
        raise typer.Exit(1)

    framework = framework.lower()
    if framework not in _FRAMEWORKS:
        console.print(f"[red]Unknown framework:[/] {framework!r}")
        console.print("Run [accent]walrusos connect --list[/] to see supported options.")
        raise typer.Exit(1)

    console.print()
    console.print(f"[bold magenta]WalrusOS[/] — connecting [accent]{_FRAMEWORKS[framework]}[/]\n")

    if framework == "claude-code":
        _show_claude(write)
    elif framework in ("cursor", "windsurf", "antigravity"):
        _show_editor(framework, write)
    elif framework == "gemini":
        _show_gemini()
    else:
        _show_generic()


def _show_claude(write: bool) -> None:
    cfg_path = _claude_config_path()
    block = _mcp_block("claude-code")
    console.print(f"Config file: [dim]{cfg_path}[/]\n")
    console.print("Add or merge this into your config:")
    console.print(Syntax(block, "json", theme="monokai"))
    console.print()
    console.print("Then restart Claude Desktop.")
    console.print()

    if write:
        _write_json_merge(cfg_path, {"mcpServers": {"walrusos": _mcp_entry("claude-code")}})
        console.print(f"[green]✓[/] Written to {cfg_path}")
    else:
        console.print("[dim]Add [accent]--write[/] to write the config file automatically.[/]")


def _show_editor(framework: str, write: bool) -> None:
    if framework == "cursor":
        target = Path(".cursor") / "mcp.json"
        label  = ".cursor/mcp.json"
    elif framework == "windsurf":
        target = Path(".windsurf") / "mcp.json"
        label  = ".windsurf/mcp.json"
    else:
        target = Path(f".{framework}") / "mcp.json"
        label  = f".{framework}/mcp.json"

    block = _mcp_block(framework)
    console.print(f"Config file: [dim]{label}[/] in your project root\n")
    console.print("Create or merge this file:")
    console.print(Syntax(block, "json", theme="monokai"))
    console.print()

    if write:
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_json_merge(target, {"mcpServers": {"walrusos": _mcp_entry(framework)}})
        console.print(f"[green]✓[/] Written to {target}")
    else:
        console.print("[dim]Add [accent]--write[/] to write the file automatically.[/]")


def _show_gemini() -> None:
    console.print("Use the [accent]--mcp[/] flag:\n")
    console.print("  [dim]gemini --mcp 'walrusos mcp start'[/]")
    console.print()


def _show_generic() -> None:
    console.print("Generic MCP config block:\n")
    console.print(Syntax(_MCP_BLOCK, "json", theme="monokai"))
    console.print()
    console.print("The command is always: [accent]walrusos mcp start[/]")
    console.print()


def _write_json_merge(path: Path, new_data: dict) -> None:
    """Merge new_data into existing JSON file, or create it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except Exception:
            existing = {}
    for key, val in new_data.items():
        if key not in existing:
            existing[key] = val
        elif isinstance(existing[key], dict) and isinstance(val, dict):
            existing[key].update(val)
        else:
            existing[key] = val
    path.write_text(json.dumps(existing, indent=2))


def _verify_mcp() -> None:
    """Run a full preflight check: MCP server, all tools, Walrus, Sui, bridge."""
    import shutil
    import subprocess

    console.print("[bold]Verifying MCP server…[/]\n")

    # 1. MCP server + tools
    try:
        result = subprocess.run(
            [sys.executable, "-m", "walrusos.cli.main", "mcp", "list-tools"],
            capture_output=True, text=True, timeout=15,
        )
        output = result.stdout + result.stderr
        server_ok = result.returncode == 0
    except Exception as exc:
        output = str(exc)
        server_ok = False

    if server_ok:
        console.print("[green]✓[/] MCP server starts")
    else:
        console.print("[red]✗[/] MCP server failed to start")

    expected_tools = [
        "memory_search", "memory_append", "memory_latest", "memory_context",
        "memory_timeline", "workspace_sync", "agent_status",
        "task_claim", "task_complete", "agent_discover",
    ]
    missing = [t for t in expected_tools if t not in output]
    if missing:
        console.print(f"[red]✗[/] {len(missing)}/{len(expected_tools)} tools missing: {missing}")
    else:
        console.print(f"[green]✓[/] {len(expected_tools)} tools registered")

    # 2. Walrus reachability (HEAD on aggregator)
    import httpx
    aggregator = os.environ.get(
        "WALRUSOS_AGGREGATOR_URL",
        "https://aggregator.walrus-testnet.walrus.space",
    )
    try:
        resp = httpx.get(aggregator, timeout=5.0, follow_redirects=True)
        if resp.status_code < 500:
            console.print(f"[green]✓[/] Walrus reachable ({aggregator})")
        else:
            console.print(f"[yellow]![/] Walrus returned {resp.status_code} ({aggregator})")
    except Exception as exc:
        console.print(f"[red]✗[/] Walrus unreachable: {exc.__class__.__name__}")

    # 3. Sui CLI available
    if shutil.which("sui"):
        try:
            sui_v = subprocess.run(
                ["sui", "--version"], capture_output=True, text=True, timeout=10,
            )
            ver = (sui_v.stdout.strip() or sui_v.stderr.strip()).splitlines()[0] if sui_v.stdout or sui_v.stderr else "installed"
            console.print(f"[green]✓[/] Sui CLI available ({ver})")
        except Exception:
            console.print("[green]✓[/] Sui CLI available")
    else:
        console.print("[red]✗[/] Sui CLI not found on PATH (install: cargo install --git https://github.com/MystenLabs/sui sui)")

    # 4. Bridge reachable
    bridge = os.environ.get("WALRUSOS_BRIDGE_URL", "http://localhost:8787")
    try:
        resp = httpx.get(f"{bridge}/agent/presence", timeout=2.0)
        if resp.status_code == 200:
            console.print(f"[green]✓[/] Bridge reachable ({bridge})")
        else:
            console.print(f"[yellow]![/] Bridge returned {resp.status_code} ({bridge}) — dashboard may not show presence")
    except Exception:
        console.print(f"[yellow]![/] Bridge offline ({bridge}) — dashboard won't show presence")

    console.print()
