"""
Example 1: Research Team
========================
WalrusOS Capability Demonstrated: MULTI-AGENT SHARED MEMORY

Three agents — Researcher, Reviewer, Writer — collaborate on a shared
MemoryStream. All three read and write to the same decentralised DAG.
No agent owns the stream; WalrusOS acts as the neutral memory substrate.

Key concepts:
  - runtime.workspace().agent()   : agent instantiation
  - agent.publish(stream, {...})  : append to shared DAG
  - agent.subscribe(stream, cb)  : reactive callbacks
  - stream.timeline()            : full chronological view
"""
from __future__ import annotations

import asyncio
from typing import Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from walrusos import WalrusOS

console = Console()

# ── WalrusOS setup ────────────────────────────────────────────────────────────
runtime   = WalrusOS()  # Production: reads ~/.walrusos/config.json
# Dev/offline: WALRUSOS_USE_MOCKS=1 python main.py
workspace = runtime.workspace("research_lab")

researcher = workspace.agent("Researcher")
reviewer   = workspace.agent("Reviewer")
writer     = workspace.agent("Writer")
stream     = workspace.stream("papers")

# ── Agent logic ───────────────────────────────────────────────────────────────

async def researcher_task() -> None:
    """Researcher discovers papers and publishes findings."""
    papers = [
        {"title": "Attention Is All You Need",        "authors": "Vaswani et al.", "year": 2017, "relevance": 0.98},
        {"title": "Chain-of-Thought Prompting",       "authors": "Wei et al.",     "year": 2022, "relevance": 0.92},
        {"title": "Reflexion: Verbal Reinforcement",   "authors": "Shinn et al.",   "year": 2023, "relevance": 0.89},
        {"title": "Toolformer: Language Models Learn", "authors": "Schick et al.",  "year": 2023, "relevance": 0.85},
    ]
    console.print("\n[bold cyan]◆ Researcher[/] beginning literature review...")
    for i, paper in enumerate(papers):
        await asyncio.sleep(0.4)
        event = await researcher.publish(stream, {
            "action": "discovered",
            "paper": paper,
            "notes": f"Paper #{i+1} identified as highly relevant to our research goal.",
        })
        console.print(f"  [cyan]→[/] Published paper #{i+1}: [italic]{paper['title'][:45]}[/]")

async def reviewer_task() -> None:
    """Reviewer reads the stream, critiques each paper."""
    await asyncio.sleep(1.5)  # Wait for researcher to publish first
    console.print("\n[bold yellow]◆ Reviewer[/] beginning peer review...")

    timeline = await stream.timeline()
    discoveries = [ev for ev, payload in timeline if payload.get("action") == "discovered"]

    for ev in discoveries:
        await asyncio.sleep(0.3)
        # Get the payload from timeline
        for _, payload in timeline:
            if payload.get("action") == "discovered":
                paper = payload.get("paper", {})
                relevance = paper.get("relevance", 0)
                verdict = "ACCEPT" if relevance >= 0.9 else "REVISE"
                await reviewer.publish(stream, {
                    "action":   "review",
                    "paper":    paper.get("title", "Unknown"),
                    "verdict":  verdict,
                    "comment":  f"Relevance score {relevance:.0%} — {'Strong methodology.' if verdict == 'ACCEPT' else 'Needs additional context.'}",
                })
                console.print(f"  [yellow]→[/] Reviewed: [italic]{paper.get('title','')[:35]}[/] → [{'green' if verdict == 'ACCEPT' else 'red'}]{verdict}[/]")
                break  # Only process each distinct paper once

async def writer_task() -> None:
    """Writer synthesises all accepted papers into a draft."""
    await asyncio.sleep(3.0)  # Wait for reviewer
    console.print("\n[bold magenta]◆ Writer[/] synthesising accepted papers into draft...")

    timeline = await stream.timeline()
    accepted = [
        payload["paper"]
        for _, payload in timeline
        if payload.get("action") == "review" and payload.get("verdict") == "ACCEPT"
    ]

    if accepted:
        await writer.publish(stream, {
            "action":   "draft_complete",
            "title":    "A Survey of Modern LLM Reasoning Techniques",
            "sections": len(accepted),
            "sources":  [p if isinstance(p, str) else p.get("title", str(p)) for p in accepted],
            "word_count": 4200,
        })
        console.print(f"  [magenta]→[/] Draft complete: {len(accepted)} sections, ~4,200 words")

async def display_final_timeline() -> None:
    """Display the complete shared memory timeline."""
    await asyncio.sleep(4.5)
    timeline = await stream.timeline()

    console.print()
    table = Table(
        title="📚 Shared Memory Timeline — research_lab/papers",
        border_style="dim",
        header_style="bold magenta",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("#",       width=3,  style="dim")
    table.add_column("Agent",   width=12, style="bold")
    table.add_column("Action",  width=16)
    table.add_column("Summary", no_wrap=False)

    agent_colors = {"Researcher": "cyan", "Reviewer": "yellow", "Writer": "magenta"}

    for i, (ev, payload) in enumerate(timeline):
        author = payload.get("author", "—")
        color  = agent_colors.get(author, "white")
        action = payload.get("action", "—")

        if action == "discovered":
            summary = f"'{payload.get('paper', {}).get('title', '')[:40]}'"
        elif action == "review":
            verdict = payload.get("verdict", "—")
            summary = f"{payload.get('paper', '')[:30]} → {verdict}"
        elif action == "draft_complete":
            summary = f"{payload.get('title', '')} ({payload.get('sections')} sections)"
        else:
            summary = str(payload)[:50]

        table.add_row(str(i+1), f"[{color}]{author}[/{color}]", action, summary)

    console.print(table)

async def main() -> None:
    console.print(Panel.fit(
        "[bold]Example 1: Research Team[/]\n"
        "[dim]Capability: Multi-Agent Shared Memory[/]\n\n"
        "Researcher, Reviewer, and Writer collaborate on a\n"
        "shared WalrusOS MemoryStream — no central server needed.",
        border_style="magenta",
        title="[bold magenta]WalrusOS[/]",
    ))

    await asyncio.gather(
        researcher_task(),
        reviewer_task(),
        writer_task(),
        display_final_timeline(),
    )

    console.print(Panel.fit(
        "[green]✓ Research Team complete![/]\n\n"
        "All three agents wrote to the same decentralised DAG.\n"
        "Every event is immutable and cryptographically ordered.",
        border_style="green",
    ))

if __name__ == "__main__":
    asyncio.run(main())
