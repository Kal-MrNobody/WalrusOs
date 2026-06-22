"""End-to-end verification: run a single anchor via the adapter path used by
the demo, then re-query SQLite to confirm the digest was persisted (i.e. the
anchor-before-append fix from event_store.py is still in effect).
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# Real mode: must not be mocked, must hit testnet
os.environ["WALRUSOS_USE_MOCKS"] = "0"


async def main() -> None:
    from walrusos import WalrusOS

    runtime   = WalrusOS(use_mocks=False)
    workspace = runtime.workspace("anchor-diag")
    agent     = workspace.agent("Diag Agent")
    stream    = agent.stream("anchor-diag-stream")

    print("Writing one memory through the full adapter path…")
    event = await stream.append(
        {"content": "Adapter-path anchor diagnostic — single test write."}
    )
    print()
    print(f"  event_id:          {getattr(event, 'event_id', getattr(event, 'id', ''))[:32]}…")
    blob_id = getattr(event, "blob_id", "") or getattr(event, "content_blob_id", "")
    print(f"  walrus blob_id:    {blob_id}")
    tx_digest = getattr(event, "transaction_digest", "") or ""
    print(f"  sui tx_digest:     {tx_digest or '(none — anchor failed)'}")

    if not tx_digest:
        print()
        print("❌ Adapter path did NOT receive a tx_digest. Check the logs above.")
        sys.exit(1)

    # Confirm the digest landed in SQLite (anchor-before-append invariant)
    db = Path.home() / ".walrusos" / "walrusos.db"
    con = sqlite3.connect(str(db))
    cur = con.cursor()
    cur.execute(
        "SELECT transaction_digest FROM protocol_events WHERE event_id = ?",
        (event.event_id,),
    )
    row = cur.fetchone()
    print()
    if row and row[0]:
        print(f"✓ Persisted in SQLite: transaction_digest = {row[0]}")
        if row[0] == tx_digest:
            print("✓ DB digest matches in-memory digest (anchor-before-append works).")
        else:
            print(f"⚠ DB digest differs from in-memory: db={row[0]} vs ev={tx_digest}")
    else:
        print(f"❌ DB has NULL transaction_digest for {event.event_id[:16]}…")
        sys.exit(1)

    print()
    print("Verify on Sui Explorer:")
    print(f"  https://suiscan.xyz/testnet/tx/{tx_digest}")
    print()
    print("Walrus blob:")
    print(f"  https://aggregator.walrus-testnet.walrus.space/v1/blobs/{blob_id}")


if __name__ == "__main__":
    asyncio.run(main())
