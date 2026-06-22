"""
Demo: Event Mesh — autonomous agent chain reaction.

Research publishes → Writer auto-responds → Reviewer auto-approves.
No manual orchestration after the first publish.

Run (mock mode — no network required):
    $env:WALRUSOS_USE_MOCKS="1"
    python scripts/demo_mesh.py
"""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")


async def main() -> None:
    from walrusos import WalrusOS

    runtime   = WalrusOS(use_mocks=True)
    workspace = runtime.workspace("mesh-demo")

    research = workspace.agent("Research")
    writer   = workspace.agent("Writer")
    reviewer = workspace.agent("Reviewer")
    stream   = research.stream("papers")

    print("Event Mesh Demo")
    print("=" * 50)
    print("Research publishes → Writer auto-responds → Reviewer auto-approves")
    print()

    writer_log:   list[str] = []
    reviewer_log: list[str] = []

    # Writer reacts when Research publishes to the stream
    async def writer_reacts(event):
        preview = event.content_blob_id[:30] if event.content_blob_id else "?"
        print(f"  [Writer] Woke up — processing {preview}…")
        writer_log.append(event.event_id)

        writer_stream = writer.stream("papers")
        await writer_stream.append(
            {"summary": f"Summary: indexed blob {preview}"},
        )
        print(f"  [Writer] Summary written.")

    # Reviewer reacts to Writer's output
    async def reviewer_reacts(event):
        if event.agent_id == writer._agent_id_str:
            preview = event.content_blob_id[:30] if event.content_blob_id else "?"
            print(f"  [Reviewer] Approving {preview}…")
            reviewer_log.append(event.event_id)

            reviewer_stream = reviewer.stream("papers")
            await reviewer_stream.append(
                {"verdict": "approved", "ref": preview},
            )
            print(f"  [Reviewer] Approval written.")

    # Subscribe to the same stream name
    await writer.subscribe(writer.stream("papers"),   callback=writer_reacts)
    await reviewer.subscribe(reviewer.stream("papers"), callback=reviewer_reacts)

    # Research publishes — this triggers the entire chain
    print("[Research] Publishing finding…")
    await stream.append(
        {"finding": "Transformers use multi-head self-attention for parallel sequence processing."},
    )
    print("[Research] Done.  Waiting 1s for reactive chain…")
    print()

    # Give the create_task callbacks time to run
    await asyncio.sleep(1)

    print(f"Writer  reacted to: {len(writer_log)} event(s)")
    print(f"Reviewer reacted to: {len(reviewer_log)} event(s)")
    print()
    print("Event mesh demo complete.")
    print("Agents reacted automatically — no manual orchestration.")


if __name__ == "__main__":
    asyncio.run(main())
