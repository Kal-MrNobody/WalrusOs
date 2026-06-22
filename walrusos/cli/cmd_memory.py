"""
walrusos memory — Inspect MemoryStreams.
"""
from __future__ import annotations

import asyncio
import typer
from rich.table import Table

from walrusos.cli._state import console, require_login, get_config, get_runtime

app = typer.Typer(help="Inspect MemoryStreams.")


def _ws(workspace: str | None = None) -> object:
    ws_name = workspace or get_config("workspace", "default")
    return get_runtime().workspace(ws_name)  # type: ignore[return-value]


@app.command("list")
def memory_list(
    workspace: str = typer.Option(None, "--workspace", "-w"),
) -> None:
    """List all MemoryStreams in a workspace."""
    require_login()
    ws_name = workspace or get_config("workspace", "default")
    console.print(f"[info]Streams in workspace:[/] [stream]{ws_name}[/]\n")
    console.print("  [muted](No streams yet. Run [accent]walrusos agent publish[/] to create one.)[/]")


@app.command("show")
def memory_show(
    stream: str = typer.Argument(..., help="Stream name"),
    limit:  int = typer.Option(20, "--limit", "-n", help="Number of events to show"),
    workspace: str = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Show the timeline of a MemoryStream."""
    require_login()
    ws_name = workspace or get_config("workspace", "default")
    ws      = get_runtime().workspace(ws_name)
    s       = ws.stream(stream)

    timeline = asyncio.run(s.timeline())

    if not timeline:
        console.print(f"[muted]Stream [stream]{stream}[/] is empty.[/]")
        return

    table = Table(title=f"Stream: {stream}", border_style="dim", header_style="bold magenta", show_lines=True)
    table.add_column("#",       style="dim",     width=4)
    table.add_column("Author",  style="magenta", width=14)
    table.add_column("Type",    style="cyan",    width=12)
    table.add_column("Blob ID", style="green",   width=20)
    table.add_column("Content", no_wrap=False)

    for ev, payload in timeline[:limit]:
        import json as _json
        table.add_row(
            str(ev.id)[:6],
            payload.get("author", "—"),
            ev.class_type,
            str(ev.content_blob_id)[:18] + "…",
            _json.dumps(payload)[:80],
        )
    console.print(table)


@app.command("verify")
def memory_verify(
    stream: str = typer.Argument(..., help="Stream name"),
    workspace: str = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Cryptographically verify all events in a MemoryStream."""
    require_login()
    ws_name = workspace or get_config("workspace", "default")
    ws      = get_runtime().workspace(ws_name)
    s       = ws.stream(stream)

    timeline = asyncio.run(s.timeline())

    if not timeline:
        console.print(f"[muted]Stream [stream]{stream}[/] is empty.[/]")
        return

    table = Table(title=f"Verification: {stream}", border_style="dim", header_style="bold magenta", show_lines=True)
    table.add_column("Epoch",   style="dim",     width=6)
    table.add_column("Event Hash", style="cyan", width=20)
    table.add_column("Author",  style="magenta", width=14)
    table.add_column("Status",  width=12)

    all_verified = True
    for ev, payload in timeline:
        is_valid = asyncio.run(ws._engine.verify_event(ev.id))
        if not is_valid:
            all_verified = False
        
        status_str = "[bold green]VERIFIED[/]" if is_valid else "[bold red]FAILED[/]"
        hash_str = ev.event_hash[:18] + "…" if getattr(ev, "event_hash", None) else "unsigned"
        
        table.add_row(
            str(ev.epoch),
            hash_str,
            payload.get("author", "—"),
            status_str,
        )
    
    console.print(table)
    if not all_verified:
        console.print("\n[bold red]WARNING: One or more events failed cryptographic verification![/]")
        raise typer.Exit(code=1)
    else:
        console.print("\n[bold green]All events successfully verified.[/]")

