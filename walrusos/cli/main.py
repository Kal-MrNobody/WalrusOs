"""
WalrusOS CLI — Root Typer application.
Registered as 'walrusos' entry point in pyproject.toml.
"""
from __future__ import annotations

import typer
from rich.panel import Panel

from walrusos.cli._state import console, get_config
from walrusos.cli import (
    cmd_init, cmd_login, cmd_workspace, cmd_agent,
    cmd_memory, cmd_search, cmd_replay, cmd_artifacts,
    cmd_permissions, cmd_events, cmd_logs, cmd_recover, cmd_branch,
    cmd_run, cmd_connect, cmd_coordinate,
)

app = typer.Typer(
    name="walrusos",
    help="[bold magenta]WalrusOS[/] — Decentralised AI Memory Infrastructure.",
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=True,
    pretty_exceptions_enable=False,
)

# ── Sub-apps ──────────────────────────────────────────────────────────────────
app.add_typer(cmd_workspace.app,   name="workspace",   help="Manage workspaces")
app.add_typer(cmd_agent.app,       name="agent",        help="Manage agents")
app.add_typer(cmd_memory.app,      name="memory",       help="Inspect MemoryStreams")
app.add_typer(cmd_artifacts.app,   name="artifacts",    help="Browse Walrus artifacts")
app.add_typer(cmd_permissions.app, name="permissions",  help="Manage Sui capabilities")
app.add_typer(cmd_branch.app,      name="branch",       help="Manage memory branches")

from walrusos.cli import cmd_mcp
app.add_typer(cmd_mcp.app,         name="mcp",          help="Run the MCP Server")
app.add_typer(cmd_run.app,         name="run",          help="Autonomous multi-agent run")
app.add_typer(cmd_coordinate.app,  name="coordinate",   help="Autonomous task-graph coordination")
app.add_typer(cmd_connect.app,     name="connect",      help="Generate MCP config for AI tools")


# ── Leaf commands ─────────────────────────────────────────────────────────────
@app.command("init")
def init_cmd(
    workspace: str = typer.Option("default", "--workspace", "-w"),
    network:   str = typer.Option("testnet",  "--network",   "-n"),
) -> None:
    """Initialise WalrusOS in the current project."""
    cmd_init.init(workspace=workspace, network=network)


@app.command("login")
def login_cmd(
    address: str = typer.Option(None, "--address", "-a"),
) -> None:
    """Authenticate with a Sui wallet."""
    cmd_login.login(address=address)


@app.command("search")
def search_cmd(
    query:     str = typer.Argument(...),
    stream:    str = typer.Option(None, "--stream", "-s"),
    limit:     int = typer.Option(10, "--limit", "-n"),
    workspace: str = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Semantic search across all streams."""
    cmd_search.search(query=query, stream=stream, limit=limit, workspace=workspace)


@app.command("replay")
def replay_cmd(
    stream:    str   = typer.Argument(...),
    speed:     float = typer.Option(0.8, "--speed", "-s"),
    from_id:   str   = typer.Option(None, "--from"),
    workspace: str   = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Replay a MemoryStream event-by-event."""
    cmd_replay.replay(stream=stream, speed=speed, from_id=from_id, workspace=workspace)


@app.command("recover")
def recover_cmd(
    workspace: str = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Recover the local state from the Sui network."""
    cmd_recover.recover(workspace=workspace)

@app.command("events")
def events_cmd(
    url:    str = typer.Option("ws://localhost:8787/ws/events", "--url"),
    filter: str = typer.Option(None, "--filter", "-f"),
) -> None:
    """Stream live runtime events from the bridge WebSocket."""
    cmd_events.events(url=url, filter=filter)


@app.command("logs")
def logs_cmd(
    lines:  int  = typer.Option(50, "--lines", "-n"),
    follow: bool = typer.Option(False, "--follow", "-f"),
    clear:  bool = typer.Option(False, "--clear"),
) -> None:
    """View the local WalrusOS CLI log."""
    cmd_logs.logs(lines=lines, follow=follow, clear=clear)


@app.command("status")
def status() -> None:
    """Show the current WalrusOS CLI status."""
    address   = get_config("sui_address", "[dim]not logged in[/]")
    workspace = get_config("workspace",   "[dim]not set[/]")
    network   = get_config("network",     "[dim]not set[/]")
    console.print(Panel.fit(
        f"  Address  : [accent]{address}[/]\n"
        f"  Workspace: [stream]{workspace}[/]\n"
        f"  Network  : [info]{network}[/]",
        title="[bold magenta]WalrusOS Status[/]",
        border_style="magenta",
    ))


@app.command("demo")
def demo_cmd() -> None:
    """Run an in-process demo to verify your WalrusOS installation."""
    import asyncio
    from rich.panel import Panel
    from rich.table import Table

    async def _run_demo() -> None:
        from walrusos import WalrusOS, MemoryType

        console.print(Panel.fit(
            "[bold magenta]WalrusOS[/] installation check",
            border_style="magenta",
        ))
        console.print()

        # Step 1: Runtime
        console.print("[dim]Step 1/5[/] Initialising runtime (mock mode)...")
        runtime = WalrusOS(use_mocks=True)
        console.print(f"[green]✓[/] Runtime ready: {runtime!r}")
        console.print()

        # Step 2: Workspace + agents
        console.print("[dim]Step 2/5[/] Creating workspace and agents...")
        workspace  = runtime.workspace("demo")
        researcher = workspace.agent("Researcher")
        reviewer   = workspace.agent("Reviewer")
        console.print(f"[green]✓[/] Workspace 'demo' ready")
        console.print(f"[green]✓[/] Agent: Researcher")
        console.print(f"[green]✓[/] Agent: Reviewer")
        console.print()

        # Step 3: Write events
        console.print("[dim]Step 3/5[/] Writing memory events...")
        stream = researcher.stream("findings")
        papers = [
            {"title": "Attention Is All You Need", "year": 2017, "venue": "NeurIPS"},
            {"title": "BERT: Pre-training of Deep Bidirectional Transformers", "year": 2018, "venue": "NAACL"},
            {"title": "GPT-3: Language Models are Few-Shot Learners", "year": 2020, "venue": "NeurIPS"},
        ]
        events = []
        for paper in papers:
            ev = await stream.append(paper, memory_type=MemoryType.SEMANTIC)
            events.append(ev)
            console.print(f"  [green]✓[/] Appended: [bold]{paper['title']!r}[/]  id={ev.event_id[:16]}...")

        # Reviewer writes too
        review_stream = reviewer.stream("findings")
        await review_stream.append({"verdict": "accepted", "notes": "Strong results."}, memory_type=MemoryType.EPISODIC)
        console.print()

        # Step 4: Read timeline
        console.print("[dim]Step 4/5[/] Reading timeline...")
        timeline = await stream.timeline()
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Timestamp", style="dim", width=26)
        table.add_column("Title")
        table.add_column("Year", justify="right")
        for ev, payload in timeline:
            table.add_row(
                ev.timestamp[:26],
                payload.get("title", "—"),
                str(payload.get("year", "—")),
            )
        console.print(table)
        console.print()

        # Step 5: Search
        console.print("[dim]Step 5/5[/] Semantic search: 'language models'...")
        results = await stream.search("language models", limit=2)
        for payload, score in results:
            console.print(f"  [{score:.2f}] {payload.get('title', '—')}")
        console.print()

        console.print(Panel.fit(
            "[bold green]✓ WalrusOS is working correctly.[/]\n\n"
            "Next: [accent]walrusos init[/] to configure a project, or [accent]walrusos login[/] for Sui.\n"
            "Docs: [link]https://docs.walrusos.network[/]",
            border_style="green",
        ))

    asyncio.run(_run_demo())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
