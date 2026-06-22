"""
Demo: Watch a REAL external AI agent connect through MCP.

This script does NOT simulate an agent. It polls the WalrusOS bridge and
prints whatever a real third-party tool (Claude Code, Cursor, …) does.

Run order:
  1. Start bridge:  python -m uvicorn dashboard.walrusos_bridge:app --port 8787
  2. Connect tool:  walrusos connect claude-code --write   (then restart that tool)
  3. Start watcher: python scripts/demo_real_agent.py
  4. In the connected tool, ask it to use memory_append / memory_search

The watcher shows the real session appear, the real events arrive, and
the real Walrus blob IDs / Sui anchors as they're produced.
"""
from __future__ import annotations

import asyncio
import os
import time

from dotenv import load_dotenv
load_dotenv()

BRIDGE_URL = os.environ.get("WALRUSOS_BRIDGE_URL", "http://localhost:8787")
POLL_INTERVAL = 2.0
TOTAL_RUNTIME_SECONDS = 120


def _is_real_external_framework(framework: str) -> bool:
    """A real external tool sets framework explicitly to one of these."""
    return framework in ("claude-code", "cursor", "windsurf", "claude-desktop")


async def main() -> None:
    import httpx

    print("=" * 64)
    print("  WalrusOS — Real Agent Watcher")
    print(f"  Bridge: {BRIDGE_URL}")
    print("=" * 64)
    print()
    print("[setup] In one terminal, start the bridge:")
    print("        python -m uvicorn dashboard.walrusos_bridge:app --port 8787")
    print("[setup] Then connect a tool: walrusos connect claude-code --write")
    print("[setup] Restart that tool and ask it to use memory_append.")
    print()
    print(f"[watch] Polling every {POLL_INTERVAL:.0f}s for up to {TOTAL_RUNTIME_SECONDS}s. Ctrl+C to stop.")
    print()

    # First — confirm bridge is up
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{BRIDGE_URL}/agent/presence")
            r.raise_for_status()
    except Exception as exc:
        print(f"[error] Bridge not reachable at {BRIDGE_URL}: {exc.__class__.__name__}")
        print("        Start it first: python -m uvicorn dashboard.walrusos_bridge:app --port 8787")
        return

    seen_real_agents: set[str] = set()
    seen_event_ids: set[str]   = set()
    start = time.time()

    async with httpx.AsyncClient(timeout=5.0) as client:
        while time.time() - start < TOTAL_RUNTIME_SECONDS:
            # Presence — look for a real external agent
            try:
                resp = await client.get(f"{BRIDGE_URL}/agent/presence")
                sessions = resp.json() if resp.status_code == 200 else []
            except Exception:
                sessions = []

            for s in sessions:
                agent_id  = s.get("agent_id", "")
                framework = s.get("framework", "")
                name      = s.get("agent_name", "?")
                if not _is_real_external_framework(framework):
                    continue
                if agent_id in seen_real_agents:
                    continue
                seen_real_agents.add(agent_id)
                print(f"[real-agent] DETECTED: {name!r} via {framework!r}  (agent_id={agent_id[:8]}…)")

            # Memory events — print new ones with their blob/anchor
            try:
                resp = await client.get(f"{BRIDGE_URL}/api/memory/events", params={"limit": 20})
                events = resp.json() if resp.status_code == 200 else []
            except Exception:
                events = []

            new_events = [e for e in events if e.get("event_id") not in seen_event_ids]
            # Sort by timestamp ascending so newest prints last
            new_events.sort(key=lambda e: e.get("timestamp", ""))
            for ev in new_events:
                eid       = ev.get("event_id") or ev.get("id") or ""
                if not eid:
                    continue
                seen_event_ids.add(eid)
                agent     = ev.get("agent_name") or ev.get("agent_id", "?")
                blob_id   = ev.get("content_blob_id") or ev.get("blob_id") or "?"
                content   = ev.get("content") or ev.get("preview") or ""
                if isinstance(content, dict):
                    content = content.get("content") or str(content)
                preview = (content[:80] + "…") if len(str(content)) > 80 else content
                print(f"[event]     {agent!s:14}  {preview!s}")
                print(f"            blob: {blob_id}")
                print(f"            anchor (sui tx): {eid[:32]}…")

            await asyncio.sleep(POLL_INTERVAL)

    print()
    print("=" * 64)
    print(f"  Done. Real agents seen: {len(seen_real_agents)}")
    print(f"  Events captured:        {len(seen_event_ids)}")
    print("=" * 64)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[stop] interrupted")
