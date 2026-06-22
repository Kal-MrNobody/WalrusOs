"""
Demo: Autonomous multi-agent run powered by Gemini 2.5 Flash.

Requires a real GEMINI_API_KEY.  Writes real blobs to Walrus and anchors
every event on Sui testnet.  Set WALRUSOS_USE_MOCKS=1 to run offline.

Usage::

    $env:GEMINI_API_KEY = "your-key-here"
    python scripts/demo_gemini_agents.py

    # Offline / mock mode (no Walrus/Sui calls):
    $env:WALRUSOS_USE_MOCKS = "1"
    python scripts/demo_gemini_agents.py
"""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
load_dotenv()


async def main() -> None:
    from walrusos import WalrusOS
    from walrusos.runtime.llm import GeminiProvider, get_provider

    api_key = os.environ.get("GEMINI_API_KEY")

    runtime   = WalrusOS()  # real mode; set WALRUSOS_USE_MOCKS=1 for offline
    workspace = runtime.workspace("gemini-demo")

    researcher = workspace.agent("Researcher")
    architect  = workspace.agent("Architect")
    writer     = workspace.agent("Writer")

    print("=" * 60)
    print("  WalrusOS x Gemini 2.5 Flash - Autonomous Agent Demo")
    print("=" * 60)
    print()

    if api_key:
        llm = GeminiProvider(api_key=api_key, model="gemini-2.5-flash")
        print("[LLM] GeminiProvider (gemini-2.5-flash) - real API calls")
    else:
        llm = get_provider("stub")
        print("[LLM] StubProvider - set GEMINI_API_KEY for real Gemini calls")
    print()

    goal = (
        "Design a decentralised AI memory system where agents store "
        "cryptographically signed memories on Walrus and anchor ownership "
        "proofs on Sui blockchain."
    )

    print(f"[GOAL] {goal[:80]}...")
    print(f"[AGENTS] {researcher.agent_name}, {architect.agent_name}, {writer.agent_name}")
    print("[ROUNDS] 2 max")
    print()

    rounds_done = []

    def on_round_complete(round_num: int, events: list) -> None:
        rounds_done.append(round_num)
        print(f"  Round {round_num} complete - {len(events)} event(s) written")
        for ev in events:
            print(f"    blob: {ev.content_blob_id[:20]}...")

    result = await workspace.run(
        goal=goal,
        agents=[researcher, architect, writer],
        max_rounds=2,
        llm=llm,
        on_round_complete=on_round_complete,
    )

    print()
    print("=" * 60)
    print(f"  Completed: {result.completed}")
    print(f"  Rounds:    {result.rounds_completed}")
    print(f"  Events:    {len(result.events)}")
    print(f"  Duration:  {result.duration_seconds:.2f}s")
    print()
    print("  Summary:")
    for line in result.final_summary.splitlines():
        print(f"    {line}")
    print()
    print(f"  Blob IDs on Walrus: {len(result.blob_ids)}")
    print(f"  Anchors on Sui:     {len(result.sui_anchors)}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
