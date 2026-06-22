"""
walrusos branch — Commands to fork, merge, and compare protocol event timelines.
"""
from __future__ import annotations

import asyncio
import typer
from rich.panel import Panel

from walrusos.cli._state import console, require_login, get_config, get_runtime
from walrusos.engine.time_travel import TimeTravelEngine

app = typer.Typer(help="Time Travel: Fork, Merge, and Compare timelines.")

def _get_tt_engine() -> TimeTravelEngine:
    runtime = get_runtime()
    return TimeTravelEngine(ledger=runtime._engine.ledger, storage=runtime._engine.storage)

@app.command()
def fork(
    original_stream: str = typer.Argument(..., help="The ID of the stream to fork"),
    fork_event: str = typer.Argument(..., help="The event ID to branch from"),
    agent: str = typer.Option(None, "--agent", "-a", help="The agent performing the fork")
):
    """
    Fork an existing stream at a specific event ID.
    Creates a new independent branch starting from that historical event.
    """
    require_login()
    console.print(f"[accent]▶ Forking stream {original_stream} at event {fork_event}...[/]")
    
    wallet = get_config("wallet_address")
    agent_id = agent or "default-agent" # In reality, resolved via AgentIdentity
    
    tt = _get_tt_engine()
    
    try:
        new_stream = asyncio.run(tt.fork_stream(
            agent_id=agent_id,
            wallet=wallet,
            original_stream=original_stream,
            fork_event_id=fork_event,
            private_key_hex="" # Simplification
        ))
        console.print(f"\n[success]✓ Successfully created branch![/]\nNew Stream ID: [bold white]{new_stream}[/]")
    except Exception as e:
        console.print(f"[error]Failed to fork: {e}[/]")
        raise typer.Exit(1)

@app.command()
def merge(
    source_stream: str = typer.Argument(..., help="The source branch to merge from"),
    target_stream: str = typer.Argument(..., help="The target branch to merge into"),
    agent: str = typer.Option(None, "--agent", "-a", help="The agent performing the merge")
):
    """
    Merge the divergent events of a source stream into a target stream.
    """
    require_login()
    console.print(f"[accent]▶ Merging {source_stream} into {target_stream}...[/]")
    
    wallet = get_config("wallet_address")
    agent_id = agent or "default-agent"
    
    tt = _get_tt_engine()
    
    try:
        merge_event_id = asyncio.run(tt.merge_streams(
            agent_id=agent_id,
            wallet=wallet,
            source_stream=source_stream,
            target_stream=target_stream,
            private_key_hex=""
        ))
        console.print(f"\n[success]✓ Successfully merged![/]\nMerge Event ID: [bold white]{merge_event_id}[/]")
    except Exception as e:
        console.print(f"[error]Failed to merge: {e}[/]")
        raise typer.Exit(1)

@app.command()
def diff(
    stream_a: str = typer.Argument(..., help="First stream"),
    stream_b: str = typer.Argument(..., help="Second stream")
):
    """
    Compare two streams and find the Lowest Common Ancestor (LCA).
    Displays the divergent events between both timelines.
    """
    console.print(f"[accent]▶ Finding Lowest Common Ancestor between {stream_a} and {stream_b}...[/]")
    
    tt = _get_tt_engine()
    lca, div_a, div_b = asyncio.run(tt.find_lca(stream_a, stream_b))
    
    if lca:
        console.print(f"\n[success]✓ LCA Found:[/] {lca.event_id} at {lca.timestamp}")
    else:
        console.print("\n[warning]No Common Ancestor found. These streams are completely divergent.[/]")
        
    console.print(Panel(
        f"[bold cyan]Branch A ({stream_a})[/]\n" + 
        (f"  {len(div_a)} divergent events ahead of LCA\n" if div_a else "  No divergent events\n") +
        f"[bold magenta]Branch B ({stream_b})[/]\n" +
        (f"  {len(div_b)} divergent events ahead of LCA" if div_b else "  No divergent events")
    ))
