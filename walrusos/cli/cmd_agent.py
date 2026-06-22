"""
walrusos agent — Manage WalrusOS agents.
"""
from __future__ import annotations

import asyncio
import json
import typer
from rich.table import Table

from walrusos.cli._state import console, require_login, get_config, get_runtime

app = typer.Typer(help="Manage agents.")


@app.command("list")
def agent_list(
    workspace: str = typer.Option(None, "--workspace", "-w"),
) -> None:
    """List agents registered in a workspace."""
    require_login()
    ws_name = workspace or get_config("workspace", "default")

    table = Table(
        title=f"Agents — {ws_name}",
        border_style="dim",
        header_style="bold magenta",
        show_lines=True,
    )
    table.add_column("Name",   style="magenta bold")
    table.add_column("Agent ID",     style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Execs", justify="right")
    table.add_column("Memory", justify="right")

    rt = get_runtime()
    ws = rt.workspace(ws_name)
    agents = ws.list_agents()

    if not agents:
        table.add_row("[dim](no agents yet)[/]", "-", "-", "-", "-")
    else:
        for a in sorted(agents, key=lambda x: x.agent_name):
            status_color = "green" if a.status == "active" else ("yellow" if a.status == "paused" else "red")
            table.add_row(
                a.agent_name,
                a.agent_id[:16] + "…",
                f"[{status_color}]{a.status}[/]",
                str(a.execution_counter),
                str(a.memory_counter),
            )

    console.print(table)


@app.command("create")
def agent_create(
    name:      str = typer.Argument(..., help="Agent name"),
    workspace: str = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Register a new agent in a workspace."""
    require_login()
    ws_name = workspace or get_config("workspace", "default")
    rt      = get_runtime()
    agent   = rt.workspace(ws_name).agent(name)
    
    console.print(f"[success]✓[/] Registered agent [agent]{name}[/] in [stream]{ws_name}[/]")
    console.print(f"  Agent ID  : [muted]{agent.identity.agent_id}[/]")
    console.print(f"  Trust Root: [muted]{agent.identity.trust_root}[/]")
    console.print(f"  Public Key: [muted]{agent.identity.public_key[:16]}…[/]")


@app.command("inspect")
def agent_inspect(
    name:      str = typer.Argument(..., help="Agent name"),
    workspace: str = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Show full identity card for an agent."""
    require_login()
    ws_name = workspace or get_config("workspace", "default")
    rt      = get_runtime()
    agent   = rt.workspace(ws_name).agent(name)
    id_     = agent.identity

    table = Table(title=f"Agent Identity: {name}", show_header=False)
    table.add_column("Field", style="magenta bold")
    table.add_column("Value")
    
    table.add_row("Agent ID", id_.agent_id)
    table.add_row("Workspace ID", id_.workspace_id)
    table.add_row("Owner Wallet", id_.owner_wallet)
    table.add_row("Trust Root", id_.trust_root)
    table.add_row("Public Key", id_.public_key)
    table.add_row("Status", id_.status)
    table.add_row("Capabilities", ", ".join(id_.capabilities))
    table.add_row("Created At", id_.created_at)
    table.add_row("Executions", str(id_.execution_counter))
    table.add_row("Memories", str(id_.memory_counter))
    table.add_row("Artifacts", str(id_.artifact_counter))

    console.print(table)


@app.command("pause")
def agent_pause(
    name:      str = typer.Argument(..., help="Agent name"),
    workspace: str = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Pause an agent."""
    require_login()
    ws_name = workspace or get_config("workspace", "default")
    rt      = get_runtime()
    agent   = rt.workspace(ws_name).agent(name)
    agent.pause()
    console.print(f"[success]✓[/] Agent [agent]{name}[/] paused.")


@app.command("terminate")
def agent_terminate(
    name:      str = typer.Argument(..., help="Agent name"),
    workspace: str = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Permanently terminate an agent."""
    require_login()
    ws_name = workspace or get_config("workspace", "default")
    rt      = get_runtime()
    agent   = rt.workspace(ws_name).agent(name)
    agent.terminate()
    console.print(f"[success]✓[/] Agent [agent]{name}[/] terminated.")


@app.command("publish")
def agent_publish(
    agent_name:  str = typer.Argument(..., help="Agent name"),
    stream_name: str = typer.Argument(..., help="Stream name"),
    payload:     str = typer.Option('{"message": "hello"}', "--payload", "-p", help="JSON payload"),
    workspace:   str = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Publish a memory event from an agent to a stream."""
    require_login()
    ws_name = workspace or get_config("workspace", "default")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        console.print("[error]Invalid JSON payload.[/]")
        raise typer.Exit(1)

    rt     = get_runtime()
    ws     = rt.workspace(ws_name)
    agent  = ws.agent(agent_name)
    stream = ws.stream(stream_name)

    try:
        event = asyncio.run(agent.publish(stream, data))
        console.print(f"[success]✓[/] Published event [muted]{event.id[:16]}…[/]")
        console.print(f"  Agent ID: [muted]{event.agent_id}[/]")
        console.print(f"  Blob ID : [blob]{event.content_blob_id[:16]}…[/]")
        console.print(f"  Stream  : [stream]{stream_name}[/]")
        console.print(f"  Epoch   : [muted]{event.epoch}[/]")
    except RuntimeError as e:
        console.print(f"[error]Error:[/] {e}")
        raise typer.Exit(1)
