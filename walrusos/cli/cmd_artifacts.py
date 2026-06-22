"""
walrusos artifacts — Browse Walrus blob artifacts.
"""
from __future__ import annotations

import typer
from rich.table import Table

from walrusos.cli._state import console, require_login

app = typer.Typer(help="Browse Walrus blob artifacts.")


@app.command("list")
def artifacts_list(
    stream: str = typer.Option(None, "--stream", "-s", help="Filter by stream name"),
    limit:  int = typer.Option(20, "--limit", "-n"),
) -> None:
    """List all artifacts stored in Walrus."""
    require_login()
    # In production, hits the bridge GET /api/artifacts
    artifacts = [
        {"name": "analysis_report.md", "type": "markdown", "stream": "papers",   "size_kb": 24,  "blob_id": "blob-abc123def456"},
        {"name": "dataset_v2.json",    "type": "json",     "stream": "raw_data", "size_kb": 512, "blob_id": "blob-xyz789ghi012"},
        {"name": "critique.txt",       "type": "text",     "stream": "feedback", "size_kb": 8,   "blob_id": "blob-lmn345opq678"},
    ]
    if stream:
        artifacts = [a for a in artifacts if a["stream"] == stream]

    table = Table(title="Artifacts", border_style="dim", header_style="bold magenta")
    table.add_column("Name",    style="bold white")
    table.add_column("Type",    style="cyan",  width=10)
    table.add_column("Stream",  style="cyan",  width=12)
    table.add_column("Size",    justify="right", width=8)
    table.add_column("Blob ID", style="green")

    for a in artifacts[:limit]:
        table.add_row(a["name"], a["type"], a["stream"], f"{a['size_kb']} KB", a["blob_id"])
    console.print(table)


@app.command("download")
def artifacts_download(
    blob_id: str = typer.Argument(..., help="Walrus Blob ID to download"),
    output:  str = typer.Option(".", "--output", "-o", help="Output path"),
) -> None:
    """Download an artifact blob from Walrus."""
    require_login()
    console.print(f"[info]Downloading[/] blob [blob]{blob_id}[/]…")
    console.print(f"[muted](Production: would call WalrusAdapter.retrieve_blob({blob_id!r}))[/]")
    console.print(f"[success]✓[/] Saved to [muted]{output}[/]")
