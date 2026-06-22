"""
walrusos permissions — Manage Sui on-chain capability tokens.
"""
from __future__ import annotations

import typer
from rich.table import Table

from walrusos.cli._state import console, require_login

app = typer.Typer(help="Manage Sui on-chain capability tokens.")

_MOCK_PERMS = [
    {"id": "cap-001", "agent": "Researcher", "stream": "papers",   "verbs": "READ,WRITE", "valid_until": "∞"},
    {"id": "cap-002", "agent": "Writer",     "stream": "papers",   "verbs": "READ",       "valid_until": "∞"},
    {"id": "cap-003", "agent": "Critic",     "stream": "feedback", "verbs": "READ,WRITE", "valid_until": "∞"},
]


@app.command("list")
def permissions_list() -> None:
    """List all active capability tokens."""
    require_login()
    table = Table(title="Capability Tokens", border_style="dim", header_style="bold magenta")
    table.add_column("ID",    style="dim",     width=10)
    table.add_column("Agent", style="magenta", width=14)
    table.add_column("Stream",style="cyan",    width=12)
    table.add_column("Verbs", style="yellow")
    table.add_column("Valid Until", width=12)
    for p in _MOCK_PERMS:
        table.add_row(p["id"], p["agent"], p["stream"], p["verbs"], p["valid_until"])
    console.print(table)


@app.command("delegate")
def permissions_delegate(
    agent:  str = typer.Argument(..., help="Agent name to grant access"),
    stream: str = typer.Argument(..., help="Stream name"),
    verbs:  str = typer.Option("READ", "--verbs", "-v", help="Comma-separated: READ,WRITE"),
) -> None:
    """Delegate a Sui capability token to an agent."""
    require_login()
    console.print(f"[info]Delegating[/] [yellow]{verbs}[/] on [stream]{stream}[/] → [agent]{agent}[/]…")
    console.print(f"[muted](Production: executes a Sui PTB via SuiIdentityAdapter.delegate_capability())[/]")
    console.print(f"[success]✓[/] Capability delegated. Cap ID: [dim]cap-{hash(agent+stream) % 10000:04d}[/]")


@app.command("revoke")
def permissions_revoke(
    cap_id: str = typer.Argument(..., help="Capability token ID to revoke"),
) -> None:
    """Revoke a Sui capability token."""
    require_login()
    console.print(f"[info]Revoking[/] capability [dim]{cap_id}[/]…")
    console.print(f"[muted](Production: destroys the Sui object via PTB)[/]")
    console.print(f"[success]✓[/] Capability [dim]{cap_id}[/] revoked.")
