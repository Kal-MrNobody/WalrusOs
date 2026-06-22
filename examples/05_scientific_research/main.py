"""
Example 5: Scientific Research Pipeline
=========================================
WalrusOS Capability Demonstrated: CHECKPOINT + REPLAY

A multi-stage scientific experiment — Data Collection, Analysis,
Hypothesis, Validation — is run with checkpoints after each stage.
After a simulated "crash", the pipeline resumes from the last
checkpoint and replays the entire experiment history.

Key concepts:
  - stream.timeline()          : reconstructing state after failure
  - replay via event iteration  : deterministic re-execution
  - append-only DAG             : no event is ever lost or mutated
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Dict, Any, List

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich import box

from walrusos import WalrusOS

console = Console()

runtime   = WalrusOS()  # Production: reads ~/.walrusos/config.json
# Dev/offline: WALRUSOS_USE_MOCKS=1 python main.py
workspace = runtime.workspace("cern_lab")

collector   = workspace.agent("DataCollector")
analyst     = workspace.agent("Analyst")
hypothesis  = workspace.agent("Hypothesis")
validator   = workspace.agent("Validator")

experiment_stream = workspace.stream("experiment_42")

# ── Pipeline Stages ───────────────────────────────────────────────────────────

async def stage_1_data_collection() -> None:
    console.print("[bold cyan]Stage 1:[/] Data Collection")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  BarColumn(), TimeElapsedColumn(), transient=True) as prog:
        task = prog.add_task("Collecting particle collision events...", total=1000)
        for i in range(0, 1001, 100):
            prog.update(task, completed=i)
            await asyncio.sleep(0.05)

    await collector.publish(experiment_stream, {
        "stage":          "data_collection",
        "checkpoint":     True,
        "events_collected": 10_482,
        "run_id":         "RUN-42-A",
        "energy_tev":     13.6,
        "detector":       "ATLAS",
        "collision_rate": "40 MHz",
        "duration_hours": 72,
    })
    console.print("  [cyan]✓[/] Checkpoint 1 saved: 10,482 collision events")

async def stage_2_analysis() -> None:
    await asyncio.sleep(0.5)
    console.print("[bold blue]Stage 2:[/] Statistical Analysis")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  BarColumn(), TimeElapsedColumn(), transient=True) as prog:
        task = prog.add_task("Running Monte Carlo simulation...", total=100)
        for i in range(0, 101, 10):
            prog.update(task, completed=i)
            await asyncio.sleep(0.06)

    await analyst.publish(experiment_stream, {
        "stage":        "analysis",
        "checkpoint":   True,
        "method":       "Monte Carlo (N=100,000)",
        "sigma":        5.2,
        "p_value":      0.0000003,
        "signal_events": 847,
        "background_events": 203,
        "systematic_uncertainty": "±2.1%",
    })
    console.print("  [blue]✓[/] Checkpoint 2 saved: σ=5.2 (>5σ discovery threshold)")

async def stage_3_hypothesis() -> None:
    await asyncio.sleep(1.0)
    console.print("[bold magenta]Stage 3:[/] Hypothesis Formulation")
    await hypothesis.publish(experiment_stream, {
        "stage":         "hypothesis",
        "checkpoint":    True,
        "claim":         "Evidence for a new vector boson at 152 GeV",
        "confidence":    "5.2σ — exceeds discovery threshold (5σ)",
        "model":         "Beyond Standard Model — Z' boson candidate",
        "implications":  ["Dark matter mediator", "B-L gauge symmetry"],
        "peer_review":   "Submitted to Physical Review Letters",
    })
    console.print("  [magenta]✓[/] Checkpoint 3 saved: Z' boson hypothesis formulated")

async def simulate_crash() -> None:
    await asyncio.sleep(1.5)
    console.print("\n[bold red]⚡ SYSTEM CRASH SIMULATED[/] — pipeline interrupted at Stage 4\n")
    await asyncio.sleep(0.5)

async def resume_from_checkpoint() -> None:
    await asyncio.sleep(2.2)
    console.print("[bold yellow]◆ RECOVERY:[/] Detecting last checkpoint from WalrusOS DAG...")
    await asyncio.sleep(0.4)

    # Reconstruct state from the immutable DAG
    timeline = await experiment_stream.timeline()
    checkpoints = [(ev, p) for ev, p in timeline if p.get("checkpoint")]

    if checkpoints:
        last_ev, last_checkpoint = checkpoints[-1]
        stage = last_checkpoint.get("stage", "unknown")
        console.print(f"  [yellow]→[/] Last checkpoint found: Stage '{stage}' (event {last_ev.id})")
        console.print(f"  [yellow]→[/] Resuming from checkpoint — no data loss\n")

        # Stage 4: Validation (resumed)
        console.print("[bold green]Stage 4:[/] Independent Validation [dim](resumed from checkpoint)[/]")
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      BarColumn(), TimeElapsedColumn(), transient=True) as prog:
            task = prog.add_task("Cross-validating with CMS detector data...", total=100)
            for i in range(0, 101, 10):
                prog.update(task, completed=i)
                await asyncio.sleep(0.05)

        await validator.publish(experiment_stream, {
            "stage":        "validation",
            "checkpoint":   True,
            "cms_sigma":    5.1,
            "atlas_sigma":  5.2,
            "combined":     5.7,
            "verdict":      "CONFIRMED — independent replication successful",
            "publication":  "Nature Physics — accepted",
        })
        console.print("  [green]✓[/] Checkpoint 4 saved: Combined σ=5.7 — DISCOVERY CONFIRMED")

async def display_replay() -> None:
    await asyncio.sleep(4.5)
    console.print("\n[bold]📼 Full Experiment Replay:[/]\n")
    timeline = await experiment_stream.timeline()

    table = Table(
        title="Experiment 42 — Complete Timeline Replay",
        border_style="dim",
        header_style="bold magenta",
        box=box.SIMPLE_HEAVY,
        show_lines=True,
    )
    table.add_column("Stage",       style="bold", width=18)
    table.add_column("Agent",       style="magenta", width=14)
    table.add_column("Key Finding", no_wrap=False)
    table.add_column("✓", width=3, justify="center")

    stage_info = {
        "data_collection": ("Data Collection", "collector",  "10,482 collision events @ 13.6 TeV"),
        "analysis":        ("Analysis",        "analyst",    "σ=5.2, p=3×10⁻⁷ — above discovery threshold"),
        "hypothesis":      ("Hypothesis",      "hypothesis", "Z' boson at 152 GeV — BMS candidate"),
        "validation":      ("Validation",      "validator",  "Combined σ=5.7 — CONFIRMED by CMS+ATLAS"),
    }

    for _, payload in timeline:
        stage = payload.get("stage", "")
        if stage in stage_info:
            label, agent_name, finding = stage_info[stage]
            table.add_row(label, agent_name.capitalize(), finding, "[green]✓[/]")

    console.print(table)

async def main() -> None:
    console.print(Panel.fit(
        "[bold]Example 5: Scientific Research Pipeline[/]\n"
        "[dim]Capability: Checkpoint + Crash Recovery + Replay[/]\n\n"
        "A 4-stage particle physics experiment. After a simulated crash,\n"
        "WalrusOS reconstructs state from the immutable DAG and resumes.",
        border_style="blue",
        title="[bold magenta]WalrusOS[/]",
    ))

    await stage_1_data_collection()
    await stage_2_analysis()
    await stage_3_hypothesis()
    await asyncio.gather(
        simulate_crash(),
        resume_from_checkpoint(),
        display_replay(),
    )

    console.print(Panel.fit(
        "[green]✓ Experiment 42 complete![/]\n\n"
        "Discovery confirmed: New vector boson at 152 GeV (σ=5.7).\n"
        "Zero data lost despite simulated crash — WalrusOS DAG is immutable.",
        border_style="green",
    ))

if __name__ == "__main__":
    asyncio.run(main())
