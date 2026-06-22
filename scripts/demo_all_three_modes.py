"""
Demo: All three autonomous-run modes side by side.

Mode 1 - Stub     : no LLM, deterministic responses (always works)
Mode 2 - Gemini   : GeminiProvider via GEMINI_API_KEY
Mode 3 - Custom   : on_event callback (you bring your own LLM)

Usage::

    $env:WALRUSOS_USE_MOCKS = "1"
    python scripts/demo_all_three_modes.py

For real Gemini calls also set::

    $env:GEMINI_API_KEY = "your-key-here"
"""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")


async def run_mode(label: str, workspace, agents: list, **kwargs) -> None:
    print("\n" + "-" * 50)
    print(f"  Mode: {label}")
    print("-" * 50)

    result = await workspace.run(
        goal="Explain how WalrusOS stores AI agent memory on-chain.",
        agents=agents,
        max_rounds=1,
        **kwargs,
    )

    print(f"  completed={result.completed}  rounds={result.rounds_completed}  events={len(result.events)}")
    print(f"  duration={result.duration_seconds:.2f}s")
    for ev in result.events[:2]:
        print(f"    blob: {ev.content_blob_id[:24]}...")


async def main() -> None:
    from walrusos import WalrusOS
    from walrusos.runtime.llm import get_provider, StubProvider

    runtime   = WalrusOS(use_mocks=True)
    workspace = runtime.workspace("three-modes-demo")

    alice  = workspace.agent("Alice")
    bob    = workspace.agent("Bob")
    agents = [alice, bob]

    print("=" * 50)
    print("  WalrusOS - All Three Autonomous Run Modes")
    print("=" * 50)

    # Mode 1: Stub (default - no LLM)
    await run_mode("STUB (no LLM)", workspace, agents)

    # Mode 2: Gemini (or fallback to stub if no key)
    llm = get_provider("auto")   # uses GEMINI_API_KEY if set, else stub
    provider_name = type(llm).__name__
    await run_mode(f"LLM ({provider_name})", workspace, agents, llm=llm)

    # Mode 3: Custom on_event callback
    call_count = {"n": 0}

    def custom_callback(agent, prompt: str, context: str) -> str:
        call_count["n"] += 1
        name = getattr(agent, "agent_name", "Agent")
        return (
            f"[Custom callback #{call_count['n']}] {name}: "
            f"Walrus stores signed blobs, Sui anchors ownership."
        )

    await run_mode("CUSTOM CALLBACK", workspace, agents, on_event=custom_callback)

    print("\n" + "=" * 50)
    print("  All 3 modes completed successfully.")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
