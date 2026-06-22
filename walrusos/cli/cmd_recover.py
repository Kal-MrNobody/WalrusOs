"""
walrusos recover — Reconstruct the local SQLite ledger and Vector database from the Sui blockchain.
"""
from __future__ import annotations

import asyncio
import typer
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from walrusos.cli._state import console, require_login, get_runtime
from walrusos.engine.recovery import DisasterRecoveryEngine

app = typer.Typer(help="Recover system state from the Sui network.")

@app.callback(invoke_without_command=True)
def recover(
    workspace: str = typer.Option(None, "--workspace", "-w", help="Workspace to recover (optional)"),
) -> None:
    """
    Trigger the Disaster Recovery Engine to fetch ProtocolEventAnchored 
    headers from Sui, hydrate payloads from Walrus, cryptographically verify them, 
    and rebuild the SQLite ledger and Vector search index.
    """
    require_login()
    
    runtime = get_runtime()
    engine = runtime._engine
    
    recovery_engine = DisasterRecoveryEngine(
        ledger=engine.ledger,
        storage=engine.storage,
        vector=engine.vector
    )

    console.print(f"\n[accent]▶ Initiating Disaster Recovery Pipeline[/]")
    console.print(f"Connecting to Sui RPC and Walrus storage...\n")

    # We need a custom event loop handler to update the rich progress bar
    async def run_recovery():
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            
            task_id = progress.add_task("[cyan]Syncing and Verifying Events...", total=100)
            
            def progress_cb(current, total):
                progress.update(task_id, completed=current, total=total)

            try:
                count = await recovery_engine.recover(progress_callback=progress_cb)
                progress.update(task_id, completed=count, total=count, description="[green]Recovery Complete!")
                return count
            except Exception as e:
                progress.stop()
                console.print(f"[error]Recovery failed:[/] {e}")
                raise typer.Exit(1)

    count = asyncio.run(run_recovery())
    
    if count == 0:
        console.print("[muted]No events found to recover on the network.[/]")
    else:
        console.print(f"\n[success]✓ Disaster Recovery Successful.[/] {count} events hydrated, verified, and indexed.")

