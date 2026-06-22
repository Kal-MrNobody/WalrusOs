"""
Example 2: Software Engineering Team
=====================================
WalrusOS Capability Demonstrated: FORK / MERGE DAG BRANCHING

The Architect creates a plan on the main stream.
Backend and Frontend fork independent branches to work in parallel.
The Reviewer merges both branches back into the main timeline.

Key concepts:
  - stream.fork()   : create a parallel branch from any event
  - stream.merge()  : reconcile two branches into a single head
  - timeline()      : full DAG history including merge commits
"""
from __future__ import annotations

import asyncio
import uuid

from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree
from rich import print as rprint

from walrusos import WalrusOS

console = Console()

runtime   = WalrusOS()  # Production: reads ~/.walrusos/config.json
# Dev/offline: WALRUSOS_USE_MOCKS=1 python main.py
workspace = runtime.workspace("eng_team")

architect = workspace.agent("Architect")
backend   = workspace.agent("Backend")
frontend  = workspace.agent("Frontend")
reviewer  = workspace.agent("Reviewer")

main_stream     = workspace.stream("sprint_42")
backend_stream  = workspace.stream("sprint_42_backend")
frontend_stream = workspace.stream("sprint_42_frontend")

async def architect_phase() -> None:
    console.print("\n[bold blue]◆ Architect[/] publishing system design...")
    await asyncio.sleep(0.2)
    await architect.publish(main_stream, {
        "phase":    "design",
        "decision": "Adopt event-driven microservices architecture",
        "services": ["API Gateway", "Auth", "Memory Service", "Search"],
        "adr":      "ADR-042: Async-first, no shared mutable state",
    })
    await asyncio.sleep(0.2)
    await architect.publish(main_stream, {
        "phase":    "tasks",
        "backend":  "Implement REST API + WebSocket server",
        "frontend": "Implement React dashboard with real-time feeds",
    })
    console.print("  [blue]→[/] System design anchored to main stream")

async def backend_phase() -> None:
    await asyncio.sleep(0.8)
    console.print("\n[bold cyan]◆ Backend[/] forking branch for API development...")
    # Fork the main stream — Backend works independently
    fork_id = await backend_stream._engine.create_stream(backend.agent_id)
    backend_stream.stream_id = fork_id

    commits = [
        "Scaffold FastAPI project structure",
        "Implement /auth/login and JWT middleware",
        "Implement /memory/streams REST endpoints",
        "Add WebSocket /ws/events handler",
        "Write integration tests (coverage: 94%)",
    ]
    for commit in commits:
        await asyncio.sleep(0.25)
        await backend.publish(backend_stream, {"commit": commit, "branch": "backend/sprint-42"})
        console.print(f"  [cyan]→[/] {commit}")

async def frontend_phase() -> None:
    await asyncio.sleep(0.9)
    console.print("\n[bold green]◆ Frontend[/] forking branch for UI development...")
    fork_id = await frontend_stream._engine.create_stream(frontend.agent_id)
    frontend_stream.stream_id = fork_id

    commits = [
        "Scaffold Next.js 14 with App Router",
        "Build sidebar navigation component",
        "Implement Agent Graph with React Flow",
        "Build Memory Timeline with replay",
        "Connect WebSocket live event feed",
    ]
    for commit in commits:
        await asyncio.sleep(0.3)
        await frontend.publish(frontend_stream, {"commit": commit, "branch": "frontend/sprint-42"})
        console.print(f"  [green]→[/] {commit}")

async def reviewer_merge_phase() -> None:
    await asyncio.sleep(4.0)
    console.print("\n[bold yellow]◆ Reviewer[/] merging branches into main stream...")

    # Code review summary published before merge
    await reviewer.publish(main_stream, {
        "phase":          "code_review",
        "backend_status": "APPROVED — clean architecture, 94% test coverage",
        "frontend_status":"APPROVED — accessible, responsive, perf score 98",
        "action":         "Initiating merge to main",
    })

    # Merge both feature streams into main
    merge_event = await main_stream.merge(backend_stream.stream_id)
    console.print("  [yellow]→[/] Backend branch merged ✓")
    merge_event2 = await main_stream.merge(frontend_stream.stream_id)
    console.print("  [yellow]→[/] Frontend branch merged ✓")

    await reviewer.publish(main_stream, {
        "phase":   "release",
        "version": "v1.4.2",
        "status":  "DEPLOYED to production",
        "sha":     "abc123def456",
    })
    console.print("  [yellow]→[/] Release v1.4.2 deployed ✓")

async def display_dag_tree() -> None:
    await asyncio.sleep(5.5)
    tree = Tree("[bold magenta]sprint_42[/] (main)")
    design = tree.add("[blue]design[/] — Architect: ADR-042")
    tasks  = design.add("[blue]tasks[/] — Architect: assign work")

    be = tasks.add("[cyan]fork → backend/sprint-42[/]")
    for msg in ["Scaffold FastAPI", "Auth API", "Memory API", "WebSocket", "Tests"]:
        be.add(f"[cyan]{msg}[/]")

    fe = tasks.add("[green]fork → frontend/sprint-42[/]")
    for msg in ["Next.js", "Sidebar", "Agent Graph", "Timeline", "Live Events"]:
        fe.add(f"[green]{msg}[/]")

    merge = tasks.add("[yellow]merge ← backend + frontend[/]")
    merge.add("[yellow]Code Review: APPROVED[/]")
    merge.add("[yellow]Release v1.4.2 → PRODUCTION[/]")

    console.print()
    console.print(tree)

async def main() -> None:
    console.print(Panel.fit(
        "[bold]Example 2: Software Engineering Team[/]\n"
        "[dim]Capability: Fork / Merge DAG Branching[/]\n\n"
        "Architect designs on main. Backend and Frontend work on\n"
        "parallel forked branches. Reviewer merges all into main.",
        border_style="cyan",
        title="[bold magenta]WalrusOS[/]",
    ))

    await asyncio.gather(
        architect_phase(),
        backend_phase(),
        frontend_phase(),
        reviewer_merge_phase(),
        display_dag_tree(),
    )

    console.print(Panel.fit(
        "[green]✓ Sprint 42 complete![/]\n\n"
        "Fork/merge DAG preserved the full parallel work history.\n"
        "The merge commit has two parents — both branches are traceable.",
        border_style="green",
    ))

if __name__ == "__main__":
    asyncio.run(main())
