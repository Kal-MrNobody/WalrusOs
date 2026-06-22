"""
Demo: Multi-Framework Agent Integration.

4 agents from different frameworks connect, discover each other,
and collaborate through the event mesh.

Run (mock mode):
    $env:WALRUSOS_USE_MOCKS="1"
    python scripts/demo_integration.py
"""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")


async def main() -> None:
    from walrusos import WalrusOS
    from walrusos.integrations.connect import (
        connect_claude_code, connect_cursor,
        connect_gemini, connect_antigravity,
    )
    from walrusos.runtime.registry import get_registry

    runtime   = WalrusOS(use_mocks=True)
    workspace = runtime.workspace("integration-demo")
    stream    = workspace.agent("Claude Code").stream("collaboration")

    print("=" * 60)
    print("  WalrusOS — Multi-Framework Agent Integration Demo")
    print("=" * 60)
    print()

    # ── 1. Connect 4 agents ────────────────────────────────────────────────
    print("[1] Connecting agents from 4 different frameworks…")
    claude      = await connect_claude_code(workspace)
    cursor      = await connect_cursor(workspace)
    gemini      = await connect_gemini(workspace)
    antigravity = await connect_antigravity(workspace)

    print("  ✓ Claude Code  (code_generation, code_review, debugging, research)")
    print("  ✓ Cursor       (code_generation, code_review, file_editing)")
    print("  ✓ Gemini       (research, reasoning, code_generation)")
    print("  ✓ Antigravity  (code_generation, planning, architecture)")
    print()

    # ── 2. Discover by capability (local registry — no bridge needed) ──────
    print("[2] Discovering agents by capability…")
    registry    = get_registry()
    reviewers   = registry.find_by_capability("code_review")
    researchers = registry.find_by_capability("research")

    print(f"  Code reviewers online:  {[r.agent_name for r in reviewers]}")
    print(f"  Researchers online:     {[r.agent_name for r in researchers]}")
    print()

    # ── 3. Reactive collaboration chain ───────────────────────────────────
    print("[3] Starting reactive collaboration chain…")

    gemini_reacted  = asyncio.Event()
    cursor_reacted  = asyncio.Event()

    async def gemini_reacts(event) -> None:
        if event.agent_id != gemini._agent_id_str:
            await gemini.set_status("thinking")
            await asyncio.sleep(0.2)
            gemini_stream = gemini.stream("collaboration")
            await gemini_stream.append(
                {"summary": f"Research confirms: blob {event.content_blob_id[:16]}"},
            )
            await gemini.set_status("idle")
            gemini_reacted.set()

    async def cursor_reacts(event) -> None:
        if event.agent_id == gemini._agent_id_str:
            await cursor.set_status("working")
            await asyncio.sleep(0.2)
            cursor_stream = cursor.stream("collaboration")
            await cursor_stream.append(
                {"code": "class MultiHeadAttention: ..."},
            )
            await cursor.set_status("idle")
            cursor_reacted.set()

    await gemini.subscribe(gemini.stream("collaboration"), callback=gemini_reacts)
    await cursor.subscribe(cursor.stream("collaboration"),   callback=cursor_reacts)

    # Claude fires the chain
    await claude.set_status("working")
    await stream.append(
        {"finding": "Transformers use multi-head self-attention for parallel processing."},
    )
    await claude.set_status("idle")

    # Wait for chain (generous timeout for mock mode)
    try:
        await asyncio.wait_for(gemini_reacted.wait(),  timeout=5.0)
        await asyncio.wait_for(cursor_reacted.wait(),  timeout=5.0)
        print("  ✓ Claude published → Gemini reacted → Cursor generated code")
    except asyncio.TimeoutError:
        print("  (chain incomplete — some tasks may still be pending)")
    print()

    # ── 4. Registry summary ────────────────────────────────────────────────
    print("[4] Registered agents:")
    for reg in registry.list_all():
        caps = ", ".join(c.name for c in reg.capabilities)
        print(f"  ● {reg.agent_name:<14} ({reg.framework}) — {caps}")
    print()

    print("=" * 60)
    print("  4 frameworks. 1 workspace. Real-time collaboration.")
    print("  All memories on Walrus. All anchors on Sui.")
    print("=" * 60)

    # Cleanup
    for agent in (claude, cursor, gemini, antigravity):
        await agent.go_offline()


if __name__ == "__main__":
    asyncio.run(main())
