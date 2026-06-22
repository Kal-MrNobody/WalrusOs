"""Diagnostic: dump recent protocol events to see if any have transaction_digest."""
import sqlite3
from pathlib import Path

db = Path.home() / ".walrusos" / "walrusos.db"
print(f"DB: {db} (exists={db.exists()})")
if not db.exists():
    raise SystemExit(1)

con = sqlite3.connect(str(db))
cur = con.cursor()

cur.execute(
    "SELECT COUNT(*), "
    "SUM(CASE WHEN transaction_digest IS NOT NULL AND transaction_digest != '' THEN 1 ELSE 0 END) "
    "FROM protocol_events WHERE event_type='MemoryAppended'"
)
total, anchored = cur.fetchone()
print(f"MemoryAppended events: total={total}  anchored={anchored}")

cur.execute(
    "SELECT event_id, agent_id, blob_id, transaction_digest, timestamp "
    "FROM protocol_events WHERE event_type='MemoryAppended' "
    "ORDER BY timestamp DESC LIMIT 15"
)
rows = cur.fetchall()
print(f"\nLast 15 MemoryAppended events:")
for r in rows:
    event_id, agent_id, blob_id, digest, ts = r
    digest_str = (digest or "NULL")[:24]
    print(
        f"  ts={ts}  ev={event_id[:14]}  "
        f"agent={(agent_id or '')[:8]}  "
        f"blob={(blob_id or '')[:14]}  digest={digest_str}"
    )

# Bridge's package id from .env
import os
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)
print()
print(f"WALRUSOS_PACKAGE_ID      = {os.environ.get('WALRUSOS_PACKAGE_ID', '<unset>')}")
print(f"WALRUSOS_LEDGER_ANCHOR_ID = {os.environ.get('WALRUSOS_LEDGER_ANCHOR_ID', '<unset>')}")
print(f"WALRUSOS_DEPLOYER_ADDRESS = {os.environ.get('WALRUSOS_DEPLOYER_ADDRESS', '<unset>')}")
print(f"WALRUSOS_NETWORK         = {os.environ.get('WALRUSOS_NETWORK', '<unset>')}")
