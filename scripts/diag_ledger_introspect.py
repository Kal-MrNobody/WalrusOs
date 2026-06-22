"""Introspect the production ledger to see why demo writes aren't anchoring.

Mirrors demo_cross_vendor.py's setup:
  - WALRUSOS_USE_MOCKS=0
  - workspace_name="default"
  - real Walrus + real Sui
Then asks: is the ledger configured to actually call Sui?
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

os.environ["WALRUSOS_USE_MOCKS"] = "0"

# Force logging to surface every WARNING/ERROR — the demo doesn't configure
# logging, so anchor-failure WARNING messages disappear.
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")


async def main() -> None:
    from walrusos import WalrusOS

    runtime   = WalrusOS(use_mocks=False)
    workspace = runtime.workspace("default")

    print()
    print("=" * 72)
    print("  Ledger introspection")
    print("=" * 72)

    ledger = runtime._ledger
    print(f"  runtime._ledger type:                  {type(ledger).__name__}")
    print(f"  hasattr(ledger, 'anchor_protocol_event'): "
          f"{hasattr(ledger, 'anchor_protocol_event')}")

    identity = getattr(ledger, "_identity", None)
    print(f"  ledger._identity type:                 {type(identity).__name__}")
    print(f"  identity.is_connected:                 {getattr(identity, 'is_connected', '?')}")
    real_client = getattr(identity, "_real_client", None)
    print(f"  identity._real_client:                 {real_client!r}")
    if real_client is not None:
        print(f"  real_client type:                      {type(real_client).__name__}")
        print(f"  real_client.package_id:                {getattr(real_client, 'package_id', '?')[:20]}…")
        print(f"  real_client.ledger_anchor_id:          {getattr(real_client, 'ledger_anchor_id', '?')[:20]}…")

    cfg = runtime._config
    print()
    print(f"  cfg.package_id:                        {cfg.package_id!r}")
    print(f"  cfg.sui_rpc_url:                       {cfg.sui_rpc_url!r}")
    print(f"  cfg.sui_address:                       {cfg.sui_address!r}")

    # Now attempt one anchor and see what happens with logging on
    print()
    print("=" * 72)
    print("  Attempting one stream.append() (with logging visible)")
    print("=" * 72)
    agent  = workspace.agent("Diag Introspect")
    stream = agent.stream("diag-introspect-stream")
    event  = await stream.append({"content": "introspect test"})
    print()
    print(f"  event.event_id:           {getattr(event, 'event_id', getattr(event, 'id', ''))[:32]}…")
    print(f"  event.blob_id:            {getattr(event, 'blob_id', getattr(event, 'content_blob_id', ''))}")
    print(f"  event.transaction_digest: {getattr(event, 'transaction_digest', '') or '(empty)'}")

    if getattr(event, "transaction_digest", None):
        print()
        print(f"  ✓ Anchor landed! Verify: https://suiscan.xyz/testnet/tx/"
              f"{event.transaction_digest}")
    else:
        print()
        print("  ❌ No transaction_digest on the returned event.")
        print("  (The logging output above should show WHY — anchor errors will appear.)")


if __name__ == "__main__":
    asyncio.run(main())
