"""
walrusos run — Autonomous multi-agent goal execution.
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Optional

import typer
from rich.rule import Rule

from walrusos.cli._state import console, require_login, get_config, get_runtime

app = typer.Typer(help="Run an autonomous multi-agent goal.")


@app.callback(invoke_without_command=True)
def run_cmd(
    goal:      str           = typer.Option(...,  "--goal",    "-g",  help="Goal for the agents"),
    agents:    Optional[str] = typer.Option(None, "--agents",  "-a",  help="Comma-separated agent names"),
    rounds:    int           = typer.Option(3,    "--rounds",  "-r",  help="Maximum rounds"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    stream:    Optional[str] = typer.Option(None, "--stream",   "-s", help="Stream name (auto-created if omitted)"),
    llm:       Optional[str] = typer.Option(None, "--llm",           help="LLM provider: auto, gemini, anthropic, stub"),
    model:     Optional[str] = typer.Option(None, "--model",         help="Model name (e.g. gemini-2.5-flash)"),
    api_key:   Optional[str] = typer.Option(None, "--api-key",       help="API key for the LLM provider"),
) -> None:
    """
    Run an autonomous multi-agent loop toward a goal.

    Example::

        walrusos run --goal "Design an OAuth system" --agents "Research,Coder,Writer" --rounds 3
    """
    require_login()
    ws_name = workspace or get_config("workspace", "default")

    rt = get_runtime()
    ws = rt.workspace(ws_name)

    # ── Resolve agents ────────────────────────────────────────────────────────
    agent_list = None
    agent_names: list[str] = []
    if agents:
        agent_names = [n.strip() for n in agents.split(",") if n.strip()]
        agent_list = [ws.agent(n) for n in agent_names]

    # ── Resolve stream ────────────────────────────────────────────────────────
    stream_client = ws.agent(agent_names[0] if agent_names else "_runner").stream(stream) if stream else None

    # ── Print header ──────────────────────────────────────────────────────────
    console.print()
    console.print(f"  [bold]Running:[/] [accent]\"{goal}\"[/]")
    if agent_names:
        console.print(f"  [bold]Agents:[/]  {', '.join(agent_names)}")
    else:
        console.print(f"  [bold]Agents:[/]  [dim](all workspace agents)[/]")
    console.print(f"  [bold]Max rounds:[/] {rounds}")
    console.print()

    # ── Resolve LLM provider ─────────────────────────────────────────────────
    llm_provider = None
    if llm:
        from walrusos.runtime.llm import get_provider
        try:
            llm_provider = get_provider(llm, api_key=api_key, model=model)
            pname = type(llm_provider).__name__
            console.print(f"  [bold]LLM:[/]       [accent]{pname}[/]")
        except ValueError as exc:
            console.print(f"  [warning]⚠ LLM setup failed:[/] {exc}")
    console.print()

    # ── Callbacks ─────────────────────────────────────────────────────────────
    # event_log holds (agent_name, response_text) in call order;
    # on_round_complete pops them to match with the MemoryEvent blobs.
    event_log: deque[tuple[str, str]] = deque()

    def on_event_cb(agent: object, prompt: str, context: str) -> str:
        name = getattr(agent, "agent_name", str(agent))
        response = f"Contributing to '{goal[:50]}...'"
        event_log.append((name, response))
        return f"[{name}] {response}"

    def on_round_complete(round_num: int, events: list) -> None:
        console.print(f"  [dim]Round {round_num}/{rounds}[/]")
        for ev in events:
            name, text = event_log.popleft() if event_log else ("?", "?")
            blob = (ev.content_blob_id or "")[:12]
            anchor = ""
            # ProtocolEvent.transaction_digest is on the internal proto event;
            # MemoryEvent doesn't carry it — show blob only.
            console.print(
                f"    [bold magenta]{name:12}[/] {text[:55]}"
                f"  → Blob: [green]{blob}[/]…"
            )
        console.print()

    # ── Execute ───────────────────────────────────────────────────────────────
    async def _run() -> None:
        result = await ws.run(
            goal=goal,
            agents=agent_list,
            stream=stream_client,
            max_rounds=rounds,
            on_event=None if llm_provider else on_event_cb,
            on_round_complete=on_round_complete,
            llm=llm_provider,
        )

        # ── Final summary ─────────────────────────────────────────────────────
        console.print(Rule(style="dim"))
        status = "[success]✓ Complete[/]" if result.completed else "[warning]⚠ Max rounds reached[/]"
        console.print(
            f"  {status} in {result.rounds_completed} round(s), "
            f"{len(result.events)} event(s), "
            f"{result.duration_seconds:.1f}s"
        )
        console.print()
        console.print("  [bold]Summary[/]")
        for line in result.final_summary.splitlines():
            console.print(f"  {line}")
        console.print()
        if result.blob_ids:
            console.print(
                f"  [dim]{len(result.blob_ids)} event(s) on Walrus · "
                f"{len(result.sui_anchors)} anchor(s) on Sui[/]"
            )
        console.print()

    asyncio.run(_run())
