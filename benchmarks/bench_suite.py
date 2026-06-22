"""
WalrusOS Benchmark Suite
=========================
Measures four key performance dimensions:
  1. Startup time (cold import + WalrusOS() instantiation)
  2. Memory append throughput (ops/sec)
  3. Semantic search latency (ms p50/p95/p99)
  4. Upload latency simulation (compression + encryption pipeline)

Run:
  python benchmarks/bench_suite.py
  python benchmarks/bench_suite.py --iterations 50000 --search-corpus 5000
"""
from __future__ import annotations

import asyncio
import gc
import statistics
import time
import uuid
from typing import List

import typer
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()
app = typer.Typer()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ns() -> float:
    return time.perf_counter_ns() / 1e6  # ms


# ── Benchmark 1: Startup Time ─────────────────────────────────────────────────

def bench_startup(runs: int = 10) -> dict:
    """Measures cold import + instantiation time."""
    import importlib
    times: list[float] = []
    for _ in range(runs):
        start = _ns()
        import walrusos  # noqa: F401 - intentional re-import probe
        from walrusos import WalrusOS
        rt = WalrusOS(use_mocks=True)
        elapsed = _ns() - start
        times.append(elapsed)
        # Force re-evaluation by clearing cached state
        del rt
        gc.collect()

    return {
        "name":   "Startup Time",
        "unit":   "ms",
        "p50":    round(statistics.median(times), 2),
        "p95":    round(sorted(times)[int(len(times) * 0.95)], 2),
        "p99":    round(sorted(times)[int(len(times) * 0.99)], 2),
        "mean":   round(statistics.mean(times), 2),
        "runs":   runs,
    }


# ── Benchmark 2: Memory Append Throughput ─────────────────────────────────────

async def _run_appends(iterations: int) -> float:
    from walrusos.engine.memory import MemoryEngine
    from walrusos.adapters.in_memory import InMemoryStorage, InMemoryLedger, InMemoryVector
    engine   = MemoryEngine(InMemoryLedger(), InMemoryStorage(), InMemoryVector())
    agent_id = uuid.uuid4()
    stream_id = await engine.create_stream(agent_id)

    start = time.perf_counter()
    for i in range(iterations):
        await engine.append(stream_id, "working", {"i": i, "data": "X" * 256})
    elapsed = time.perf_counter() - start
    return iterations / elapsed  # ops/sec


def bench_append_throughput(iterations: int = 10_000, runs: int = 5) -> dict:
    """Measures append throughput across multiple runs."""
    results = [asyncio.run(_run_appends(iterations)) for _ in range(runs)]
    return {
        "name":   "Append Throughput",
        "unit":   "ops/sec",
        "p50":    round(statistics.median(results), 0),
        "p95":    round(sorted(results)[int(len(results) * 0.95) - 1], 0),
        "p99":    round(sorted(results)[-1], 0),
        "mean":   round(statistics.mean(results), 0),
        "runs":   runs,
    }


# ── Benchmark 3: Semantic Search Latency ─────────────────────────────────────

async def _build_corpus(n: int) -> object:
    from walrusos.engine.memory import MemoryEngine
    from walrusos.adapters.in_memory import InMemoryStorage, InMemoryLedger, InMemoryVector
    engine   = MemoryEngine(InMemoryLedger(), InMemoryStorage(), InMemoryVector())
    agent_id = uuid.uuid4()
    stream_id = await engine.create_stream(agent_id)
    topics = [
        "machine learning model training optimization",
        "blockchain consensus mechanism performance",
        "distributed storage fault tolerance",
        "transformer attention mechanism efficiency",
        "reinforcement learning reward shaping",
    ]
    for i in range(n):
        await engine.append(stream_id, "semantic", {
            "content": f"{topics[i % len(topics)]} iteration {i}"
        })
    return engine, stream_id


async def _run_searches(engine: object, stream_id: object, query: str, n: int) -> list[float]:
    from walrusos.engine.memory import MemoryEngine
    eng: MemoryEngine = engine  # type: ignore[assignment]
    latencies = []
    for _ in range(n):
        start = _ns()
        await eng.semantic_search(query)
        latencies.append(_ns() - start)
    return latencies


def bench_search_latency(corpus_size: int = 1_000, search_runs: int = 100) -> dict:
    """Measures semantic search latency over a corpus."""
    async def _run() -> list[float]:
        engine, stream_id = await _build_corpus(corpus_size)
        return await _run_searches(engine, stream_id, "distributed memory agent collaboration", search_runs)

    latencies = asyncio.run(_run())
    s = sorted(latencies)
    return {
        "name":   f"Search Latency (corpus={corpus_size})",
        "unit":   "ms",
        "p50":    round(s[len(s) // 2], 3),
        "p95":    round(s[int(len(s) * 0.95)], 3),
        "p99":    round(s[int(len(s) * 0.99)], 3),
        "mean":   round(statistics.mean(latencies), 3),
        "runs":   search_runs,
    }


# ── Benchmark 4: Upload Pipeline Latency ─────────────────────────────────────

def bench_upload_pipeline(payload_kb: int = 64, runs: int = 50) -> dict:
    """Measures local compress + encrypt pipeline (no network)."""
    import os
    try:
        import zstandard as zstd
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        return {"name": "Upload Pipeline", "unit": "ms", "p50": 0, "p95": 0, "p99": 0, "mean": 0, "runs": 0}

    key    = AESGCM.generate_key(bit_length=256)
    aesgcm = AESGCM(key)
    cctx   = zstd.ZstdCompressor(level=3)
    data   = os.urandom(payload_kb * 1024)
    latencies = []
    for _ in range(runs):
        start = _ns()
        compressed = cctx.compress(data)
        nonce      = os.urandom(12)
        _          = aesgcm.encrypt(nonce, compressed, None)
        latencies.append(_ns() - start)

    s = sorted(latencies)
    return {
        "name":   f"Upload Pipeline ({payload_kb}KB)",
        "unit":   "ms",
        "p50":    round(s[len(s) // 2], 3),
        "p95":    round(s[int(len(s) * 0.95)], 3),
        "p99":    round(s[int(len(s) * 0.99)], 3),
        "mean":   round(statistics.mean(latencies), 3),
        "runs":   runs,
    }


# ── CLI Entry ─────────────────────────────────────────────────────────────────

@app.command()
def main(
    iterations:    int = typer.Option(10_000, "--iterations", "-n",     help="Append iterations"),
    search_corpus: int = typer.Option(1_000,  "--search-corpus", "-s",  help="Corpus size for search bench"),
    startup_runs:  int = typer.Option(10,     "--startup-runs",         help="Startup measurement runs"),
    upload_kb:     int = typer.Option(64,     "--upload-kb",            help="Upload payload size in KB"),
) -> None:
    """Run the full WalrusOS benchmark suite."""
    console.print("\n[bold magenta]WalrusOS Benchmark Suite[/] — v0.1.0\n")

    results = []

    with console.status("[cyan]1/4[/] Benchmarking startup time…"):
        results.append(bench_startup(runs=startup_runs))

    with console.status(f"[cyan]2/4[/] Benchmarking {iterations:,} memory appends…"):
        results.append(bench_append_throughput(iterations=iterations))

    with console.status(f"[cyan]3/4[/] Benchmarking search over {search_corpus:,} events…"):
        results.append(bench_search_latency(corpus_size=search_corpus))

    with console.status(f"[cyan]4/4[/] Benchmarking upload pipeline ({upload_kb}KB)…"):
        results.append(bench_upload_pipeline(payload_kb=upload_kb))

    # ── Results Table ─────────────────────────────────────────────────────────
    table = Table(
        title="Benchmark Results",
        border_style="dim",
        header_style="bold magenta",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("Benchmark",   style="bold white", no_wrap=True)
    table.add_column("Unit",        style="dim",        width=10)
    table.add_column("p50",         justify="right",    style="green")
    table.add_column("p95",         justify="right",    style="yellow")
    table.add_column("p99",         justify="right",    style="red")
    table.add_column("Mean",        justify="right",    style="cyan")
    table.add_column("Runs",        justify="right",    style="dim")

    for r in results:
        table.add_row(
            r["name"], r["unit"],
            str(r["p50"]), str(r["p95"]), str(r["p99"]),
            str(r["mean"]), str(r["runs"]),
        )

    console.print()
    console.print(table)
    console.print("\n[dim]Benchmarks use in-memory adapters (no network). "
                  "Production Walrus upload latency varies by network.[/]\n")


if __name__ == "__main__":
    app()
