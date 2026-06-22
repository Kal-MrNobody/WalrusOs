"""
walrusos events — Stream live runtime events from the bridge.
"""
from __future__ import annotations

import asyncio
import json
import typer

from walrusos.cli._state import console, require_login

app = typer.Typer(help="Stream live runtime events from the WalrusOS bridge.")

TYPE_STYLE = {
    "memory.append":       "magenta",
    "agent.publish":       "green",
    "stream.fork":         "yellow",
    "permission.delegate": "cyan",
}


@app.callback(invoke_without_command=True)
def events(
    url:    str = typer.Option("ws://localhost:8787/ws/events", "--url", help="Bridge WebSocket URL"),
    filter: str = typer.Option(None, "--filter", "-f", help="Filter by event type prefix"),
) -> None:
    """
    Stream live WalrusOS runtime events from the dashboard bridge WebSocket.
    Press Ctrl+C to stop.
    """
    require_login()
    try:
        import websockets  # type: ignore
    except ImportError:
        console.print("[error]websockets not installed.[/] Run: [accent]pip install websockets[/]")
        raise typer.Exit(1)

    console.print(f"[info]Connecting to[/] [muted]{url}[/]…  (Ctrl+C to stop)\n")

    async def _stream() -> None:
        try:
            async with websockets.connect(url) as ws:
                console.print("[success]✓ Connected[/]\n")
                async for raw in ws:
                    ev = json.loads(raw)
                    t  = ev.get("type", "unknown")
                    if filter and not t.startswith(filter):
                        continue
                    color = TYPE_STYLE.get(t, "white")
                    console.print(
                        f"[dim]{ev.get('timestamp','')[:19]}[/]  "
                        f"[{color}]{t:<26}[/]  "
                        f"[cyan]{ev.get('agent','?'):<12}[/]  "
                        f"[stream]{ev.get('stream','?')}[/]"
                    )
        except Exception as exc:
            console.print(f"\n[error]Disconnected:[/] {exc}")

    try:
        asyncio.run(_stream())
    except KeyboardInterrupt:
        console.print("\n[muted]Stream closed.[/]")
