"""
walrusos replay — Replay a ProtocolEvent stream in the terminal.
"""
from __future__ import annotations

import asyncio
import time
import typer
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.align import Align

from walrusos.cli._state import console, require_login, get_config, get_runtime
from walrusos.engine.replay import ReplayEngine, CryptographicVerificationError

app = typer.Typer(help="Replay ProtocolEvents.")


@app.callback(invoke_without_command=True)
def replay(
    workspace: str   = typer.Option(None, "--workspace", "-w", help="Workspace to replay"),
    agent:     str   = typer.Option(None, "--agent", "-a", help="Agent to replay"),
    stream:    str   = typer.Option(None, "--stream", help="Stream to replay"),
    speed:     float = typer.Option(0.8, "--speed", "-s", help="Seconds between events"),
    until_time:  str = typer.Option(None, "--until-time", help="Stop replay at this ISO timestamp"),
    until_event: str = typer.Option(None, "--until-event", help="Stop replay at this event ID"),
    verify:      bool = typer.Option(False, "--verify", help="Verify cryptographic signatures and hashes"),
    rebuild_net: bool = typer.Option(False, "--rebuild-from-network", help="Rebuild SQLite from Sui Network before replay"),
) -> None:
    """
    Replay the Event Sourced DAG, rendering each event with syntax highlighting 
    and optional cryptographic verification.
    """
    require_login()
    ws_name  = workspace or get_config("workspace", "default")
    
    runtime = get_runtime()
    engine = runtime._engine
    replay_engine = ReplayEngine(ledger=engine.ledger, storage=engine.storage)

    if rebuild_net:
        if hasattr(engine.ledger, "sync_events_from_network"):
            console.print("[accent]▶ Synchronizing with Sui Network...[/]")
            try:
                events = asyncio.run(engine.ledger.sync_events_from_network())
                console.print(f"[success]✓ Network sync complete. Fetched {len(events)} events.[/]")
            except Exception as e:
                console.print(f"[error]Network sync failed: {e}[/]")
                raise typer.Exit(1)
        else:
            console.print("[error]Ledger does not support network sync.[/]")
            raise typer.Exit(1)

    # Need workspace_id
    import uuid
    workspace_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, ws_name))
    agent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{ws_name}.agent.{agent}")) if agent else None

    console.print("[accent]▶ Fetching and verifying events...[/]")
    try:
        timeline = asyncio.run(replay_engine.replay(
            workspace_id=workspace_id,
            agent_id=agent_id,
            stream_id=stream,
            until_timestamp=until_time,
            until_event=until_event,
            verify_crypto=verify,
            verify_capabilities=verify,
        ))
    except CryptographicVerificationError as e:
        console.print(f"\n[error]Cryptographic Verification Failed![/]\n{e}")
        raise typer.Exit(1)

    if not timeline:
        console.print("[muted]No events found for the given filters.[/]")
        raise typer.Exit(0)

    console.print(f"\n[accent]▶ Replaying[/] — {len(timeline)} events @ {speed}s interval\n")
    time.sleep(0.5)

    import json as _json
    for i, ev in enumerate(timeline):
        class_colors = {"MemoryAppended": "magenta", "AgentRegistered": "green", "WorkspaceCreated": "yellow"}
        color = class_colors.get(ev.event_type.value, "cyan")

        title_text = f"[{color}]Event {i+1}/{len(timeline)}[/]  [{color}]{ev.event_type.value}[/]  [dim]{ev.event_id[:16]}...[/]"
        if verify:
            title_text += " [green]✓ Verified[/]"

        panel = Panel(
            _json.dumps(ev.payload, indent=2),
            title=title_text,
            border_style=color,
            subtitle=f"[dim]ts: {ev.timestamp}[/]",
        )
        console.print(panel)
        time.sleep(speed)

    console.print(f"\n[success]✓ Replay complete.[/] {len(timeline)} events replayed.")
