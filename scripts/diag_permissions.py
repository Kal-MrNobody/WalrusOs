"""Diagnostic: what does the local DB actually know about capabilities?"""
import sqlite3
import json
from pathlib import Path

db = Path.home() / ".walrusos" / "walrusos.db"
print(f"DB: {db}")
con = sqlite3.connect(str(db))
cur = con.cursor()

# All tables
print("\nALL TABLES:")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for r in cur.fetchall():
    print(f"  {r[0]}")

# Capabilities schema + row count
print("\nCAPABILITIES TABLE:")
cur.execute("PRAGMA table_info(capabilities)")
for col in cur.fetchall():
    print(f"  col: {col[1]} ({col[2]})")
cur.execute("SELECT COUNT(*) FROM capabilities")
print(f"  rows: {cur.fetchone()[0]}")
cur.execute("SELECT * FROM capabilities LIMIT 5")
for r in cur.fetchall():
    print(f"  row: {r}")

# Protocol event types
print("\nPROTOCOL EVENT TYPES:")
cur.execute(
    "SELECT event_type, COUNT(*) FROM protocol_events GROUP BY event_type ORDER BY 2 DESC"
)
for r in cur.fetchall():
    print(f"  {r[0]:30}  count={r[1]}")

# Any capability-related rows in protocol_events?
print("\nCAPABILITY-RELATED PROTOCOL EVENTS:")
cur.execute(
    "SELECT event_id, event_type, agent_id, blob_id, transaction_digest, payload_json "
    "FROM protocol_events "
    "WHERE event_type LIKE '%Capability%' OR event_type LIKE '%Delegate%'"
)
rows = cur.fetchall()
print(f"  total: {len(rows)}")
for r in rows[:5]:
    event_id, event_type, agent_id, blob_id, tx_digest, payload_json = r
    print(f"  type={event_type}  agent={agent_id}  tx={(tx_digest or '')[:20]}")
    try:
        p = json.loads(payload_json)
        for k in (
            "target_stream", "target_stream_id", "recipient",
            "agent_id", "verb_bitmask", "capability_id", "sui_object_id",
        ):
            if k in p:
                print(f"    payload.{k} = {p[k]}")
    except Exception:
        pass

# Stream → name lookup
print("\nMEMORY_STREAMS:")
try:
    cur.execute("SELECT stream_id, name FROM memory_streams LIMIT 10")
    for r in cur.fetchall():
        print(f"  {r[0]}  name={r[1]}")
except sqlite3.OperationalError as e:
    print(f"  (table missing or differently named: {e})")

# Agent identity lookup
print("\nAGENT_IDENTITIES sample:")
try:
    cur.execute("SELECT agent_id, agent_name FROM agent_identities LIMIT 5")
    for r in cur.fetchall():
        print(f"  {r[0][:16]}…  name={r[1]}")
except sqlite3.OperationalError as e:
    print(f"  (different table name: {e})")
