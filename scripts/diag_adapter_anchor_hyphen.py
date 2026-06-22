"""End-to-end: directly call the adapter's anchor_event() with a synthetic
`-`-prefixed blob_id to prove the PTB dispatch path works against live testnet.
Doesn't write to Walrus — just exercises the anchor function in isolation.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

os.environ["WALRUSOS_USE_MOCKS"] = "0"


async def main() -> None:
    from walrusos.adapters.sui_real import RealSuiClient

    client = RealSuiClient(
        package_id=os.environ["WALRUSOS_PACKAGE_ID"],
        ledger_anchor_id=os.environ["WALRUSOS_LEDGER_ANCHOR_ID"],
    )

    synthetic_blob_id = "-NLO" + hashlib.sha256(b"diag-hyphen").hexdigest()[:39]
    event_hash = hashlib.sha256(b"diag-hyphen-event").digest()

    print(f"Synthetic blob_id (leading '-'): {synthetic_blob_id}")
    print(f"  → forces dispatch to PTB path")
    print()
    print("Calling client.anchor_event(...)…")
    result = await asyncio.to_thread(
        client.anchor_event,
        blob_id=synthetic_blob_id,
        event_hash=event_hash,
        event_type="MemoryAppended",
        workspace_id="diag-ws",
        agent_id="diag-agent",
    )
    print()
    tx = result.get("tx_digest", "")
    if tx:
        print(f"✓ tx_digest: {tx}")
        print(f"  Verify:    https://suiscan.xyz/testnet/tx/{tx}")
    else:
        print(f"❌ no tx_digest returned: {result}")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
