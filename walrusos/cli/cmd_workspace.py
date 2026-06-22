"""
walrusos workspace — Manage WalrusOS workspaces.
"""
from __future__ import annotations

import typer
from rich.table import Table

from walrusos.cli._state import console, require_login, get_config, get_runtime

app = typer.Typer(help="Manage workspaces.")


@app.command("list")
def workspace_list() -> None:
    """List all workspaces in the current runtime."""
    require_login()
    workspaces = [
        {"name": get_config("workspace", "default"), "agents": 0, "streams": 0, "network": get_config("network", "testnet")},
    ]
    table = Table(title="Workspaces", border_style="dim", header_style="bold magenta")
    table.add_column("Name",    style="cyan bold")
    table.add_column("Agents",  justify="right")
    table.add_column("Streams", justify="right")
    table.add_column("Network", style="dim")
    for ws in workspaces:
        table.add_row(ws["name"], str(ws["agents"]), str(ws["streams"]), ws["network"])
    console.print(table)


@app.command("create")
def workspace_create(
    name: str = typer.Argument(..., help="Workspace name"),
) -> None:
    """Create a new workspace."""
    require_login()
    runtime = get_runtime()
    ws = runtime.workspace(name)
    console.print(f"[success]✓[/] Created workspace [stream]{name}[/] (id: [muted]{ws.workspace_id}[/])")


@app.command("use")
def workspace_use(
    name: str = typer.Argument(..., help="Workspace name to activate"),
) -> None:
    """Switch the active workspace."""
    from walrusos.cli._state import load_config, save_config
    cfg = load_config()
    cfg["workspace"] = name
    save_config(cfg)
    console.print(f"[success]✓[/] Active workspace → [stream]{name}[/]")
