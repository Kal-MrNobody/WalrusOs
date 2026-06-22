"""
walrusos coordinate — Autonomous task-graph execution.

The coordinator decomposes the goal into tasks, matches each task to the
best-capable online agent, and executes respecting dependencies.
No --agents flag required — the engine decides who does what.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

import typer
from rich.rule import Rule
from rich.table import Table

from walrusos.cli._state import console, require_login, get_config, get_runtime

app = typer.Typer(help="Coordinate agents autonomously toward a goal.")


@app.callback(invoke_without_command=True)
def coordinate_cmd(
    goal:    str           = typer.Option(..., "--goal",  "-g", help="Goal to accomplish"),
    llm:     Optional[str] = typer.Option(None, "--llm",        help="LLM: auto, gemini, anthropic, stub"),
    model:   Optional[str] = typer.Option(None, "--model",      help="Model name"),
    api_key: Optional[str] = typer.Option(None, "--api-key",    help="API key for the LLM provider"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
) -> None:
    """
    Coordinate agents autonomously toward a goal.

    Example::

        walrusos coordinate --goal "Build OAuth" --llm gemini
    """
    require_login()
    ws_name = workspace or get_config("workspace", "default")

    rt = get_runtime()
    ws = rt.workspace(ws_name)

    # ── Resolve LLM provider ──────────────────────────────────────────────────
    llm_provider = None
    if llm:
        from walrusos.runtime.llm import get_provider
        try:
            llm_provider = get_provider(llm, api_key=api_key, model=model)
            pname = type(llm_provider).__name__
            console.print(f"  [bold]LLM:[/] [accent]{pname}[/]")
        except ValueError as exc:
            console.print(f"  [warning]LLM setup failed:[/] {exc}")

    console.print()
    console.print(f"  [bold]Coordinating:[/] [accent]\"{goal}\"[/]")
    console.print()

    plan_display: list = []

    async def _run() -> None:
        nonlocal plan_display

        console.print("  [dim]Decomposing goal into tasks...[/]")

        completed_count = 0

        def on_task(task) -> None:
            nonlocal completed_count
            completed_count += 1
            status_icon = "[green]done[/]" if task.status == "done" else "[red]failed[/]"
            console.print(
                f"    [{task.assigned_to_name or '?'}] "
                f"{task.title[:55]}... {status_icon}"
            )

        result = await ws.coordinate(
            goal=goal,
            llm=llm_provider,
            on_task_complete=on_task,
        )

        # Print execution plan table after decomposition
        console.print()
        console.print("  [bold]Execution Plan:[/]")
        table = Table(show_header=False, box=None, pad_edge=False, padding=(0, 2))
        table.add_column("num",  style="dim", width=4)
        table.add_column("title")
        table.add_column("cap",  style="cyan")
        table.add_column("agent", style="magenta")
        table.add_column("deps", style="dim")

        for i, task in enumerate(result.plan.tasks, 1):
            deps = f"(needs: {len(task.depends_on)})" if task.depends_on else ""
            status_marker = (
                "[green]✓[/]" if task.status == "done"
                else "[red]✗[/]" if task.status in ("failed", "blocked")
                else "[dim]?[/]"
            )
            table.add_row(
                f"{status_marker} {i}.",
                task.title[:50],
                task.required_capability,
                task.assigned_to_name or "—",
                deps,
            )
        console.print(table)
        console.print()

        console.print(Rule(style="dim"))
        status = "[success]Complete[/]" if result.completed else "[warning]Partial[/]"
        console.print(
            f"  {status}: {result.tasks_completed}/{len(result.plan.tasks)} tasks, "
            f"{len(result.agents_used)} agent(s), "
            f"{result.duration_seconds:.1f}s"
        )
        console.print()
        console.print("  [bold]Summary[/]")
        for line in result.final_summary.splitlines():
            console.print(f"  {line}")
        console.print()
        if result.blob_ids:
            console.print(
                f"  [dim]{len(result.blob_ids)} event(s) on Walrus"
                + (f" · {len(result.sui_anchors)} anchor(s) on Sui" if result.sui_anchors else "")
                + "[/]"
            )
        console.print()

    asyncio.run(_run())
