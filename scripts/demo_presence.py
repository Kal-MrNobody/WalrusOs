"""
Demo: Agent Session Protocol — live presence in the WalrusOS runtime.

Shows multiple agents going online, updating status, writing memory, and
disconnecting while the PresenceStore tracks every heartbeat.

Run (no bridge required — uses mock mode):
    $env:WALRUSOS_USE_MOCKS="1"
    python scripts/demo_presence.py
"""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


async def main() -> None:
    from walrusos import WalrusOS, MemoryType
    from walrusos.runtime.presence import get_presence_store

    console.print(Panel.fit(
        "[bold magenta]WalrusOS[/] — Agent Session Protocol Demo",
        border_style="magenta",
    ))
    console.print()

    # ── Setup ─────────────────────────────────────────────────────────────────
    runtime  = WalrusOS(use_mocks=True)
    ws       = runtime.workspace("presence-demo")
    store    = get_presence_store()

    # Subscribe to presence events
    events_log: list[str] = []
    def on_presence(msg: str) -> None:
        import json
        data = json.loads(msg)
        events_log.append(f"[dim]{data['type']}[/] → {data.get('agent_name', data.get('agent_id', '?'))}")

    store.subscribe(on_presence)

    # ── Three agents go online ────────────────────────────────────────────────
    console.print("[bold]Step 1[/] — Three agents going online…")
    alice   = ws.agent("Alice")
    bob     = ws.agent("Bob")
    charlie = ws.agent("Charlie")

    # Register directly with store (no bridge needed)
    await store.register(str(alice.agent_id),   "Alice",   ws.workspace_id)
    await store.register(str(bob.agent_id),     "Bob",     ws.workspace_id)
    await store.register(str(charlie.agent_id), "Charlie", ws.workspace_id)

    console.print(f"  [green]✓[/] Registered {len(store.list_sessions())} agents")
    console.print()

    # ── Heartbeats with status transitions ───────────────────────────────────
    console.print("[bold]Step 2[/] — Status transitions…")

    await store.heartbeat(str(alice.agent_id),   status="thinking")
    await store.heartbeat(str(bob.agent_id),     status="working")
    await store.heartbeat(str(charlie.agent_id), status="idle")

    console.print("  Alice   → thinking")
    console.print("  Bob     → working")
    console.print("  Charlie → idle")
    console.print()

    # ── Alice writes memory ───────────────────────────────────────────────────
    console.print("[bold]Step 3[/] — Alice writes 3 memories…")

    stream = alice.stream("research-notes")
    for i in range(3):
        await stream.append(
            {"note": f"Research insight #{i+1}", "confidence": 0.8 + i * 0.05},
            memory_type=MemoryType.SEMANTIC,
        )
        await store.heartbeat(str(alice.agent_id), memory_writes_delta=1)

    console.print("  [green]✓[/] 3 memory events written")
    console.print()

    # ── Stale detection ───────────────────────────────────────────────────────
    console.print("[bold]Step 4[/] — Stale detection…")
    from datetime import datetime, timedelta

    charlie_session = store.get_session(str(charlie.agent_id))
    charlie_session.last_heartbeat = datetime.utcnow() - timedelta(seconds=45)

    stale = [s for s in store.list_sessions() if s.is_stale]
    console.print(f"  {len(stale)} stale agent(s): {[s.agent_name for s in stale]}")
    console.print()

    # ── Presence snapshot ─────────────────────────────────────────────────────
    console.print("[bold]Step 5[/] — Current presence snapshot:")
    console.print()

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Agent")
    table.add_column("Status")
    table.add_column("Writes", justify="right")
    table.add_column("Stale")

    for s in store.list_sessions():
        stale_mark = "[red]yes[/]" if s.is_stale else "[green]no[/]"
        table.add_row(s.agent_name, s.status, str(s.memory_writes), stale_mark)

    console.print(table)
    console.print()

    # ── Agents go offline ─────────────────────────────────────────────────────
    console.print("[bold]Step 6[/] — Agents going offline…")

    for agent_id, name in [
        (str(alice.agent_id),   "Alice"),
        (str(bob.agent_id),     "Bob"),
        (str(charlie.agent_id), "Charlie"),
    ]:
        await store.unregister(agent_id)
        console.print(f"  [dim]{name} disconnected[/]")

    console.print()
    console.print(f"  Active sessions remaining: {len(store.list_sessions())}")
    console.print()

    # ── Event log ────────────────────────────────────────────────────────────
    console.print("[bold]Presence events received by subscriber:[/]")
    for line in events_log:
        console.print(f"  {line}")

    console.print()
    console.print(Panel.fit(
        "[bold green]✓ Agent Session Protocol demo complete.[/]\n\n"
        "Start the bridge to see live presence in the dashboard:\n"
        "  [accent]uvicorn dashboard.walrusos_bridge:app --port 8787[/]",
        border_style="green",
    ))

    store.unsubscribe(on_presence)


if __name__ == "__main__":
    asyncio.run(main())
