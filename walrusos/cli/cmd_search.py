"""
walrusos search — Semantic search across MemoryStreams.
"""
from __future__ import annotations

import asyncio
import typer
from rich.table import Table
from rich.text import Text

from walrusos.cli._state import console, require_login, get_config, get_runtime

app = typer.Typer(help="Semantic search across all streams.")


@app.callback(invoke_without_command=True)
def search(
    query:     str = typer.Argument(..., help="Search query"),
    stream:    str = typer.Option(None, "--stream", "-s", help="Scope to a specific stream"),
    limit:     int = typer.Option(10, "--limit", "-n", help="Max results"),
    workspace: str = typer.Option(None, "--workspace", "-w"),
) -> None:
    """
    Perform a semantic vector search across WalrusOS MemoryStreams.
    """
    require_login()
    ws_name = workspace or get_config("workspace", "default")

    console.print(f"[info]Searching[/] [muted]\"{query}\"[/] in [stream]{ws_name}[/]…\n")

    ws = get_runtime().workspace(ws_name)
    s  = ws.stream(stream or "papers")

    results = asyncio.run(s._engine.semantic_search(query))

    if not results:
        console.print("[muted]No results found.[/]")
        return

    table = Table(border_style="dim", header_style="bold magenta")
    table.add_column("Score", style="green", width=7)
    table.add_column("Stream", style="cyan", width=12)
    table.add_column("Content", no_wrap=False)

    for r in results[:limit]:
        score = r.get("score", 0.0)
        bar   = "█" * int(score * 10) + "░" * (10 - int(score * 10))
        table.add_row(f"{score:.2f}", r.get("stream", "—"), r.get("content", "—"))

    console.print(table)
