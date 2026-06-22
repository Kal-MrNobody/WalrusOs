"""Show every MemoryAppended row written in the last 30 minutes and whether
each has a transaction_digest. Reveals whether the latest demo run anchored
vs. whether the proof file is showing old un-anchored writes from before
the BOM/PTB fixes."""
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

db = Path.home() / ".walrusos" / "walrusos.db"
con = sqlite3.connect(str(db))
cur = con.cursor()

cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
print(f"Looking for events written since {cutoff}")
print()

cur.execute(
    "SELECT event_id, agent_id, blob_id, transaction_digest, timestamp, payload_json "
    "FROM protocol_events "
    "WHERE event_type='MemoryAppended' AND timestamp > ? "
    "ORDER BY timestamp DESC",
    (cutoff,),
)
rows = cur.fetchall()
print(f"Total MemoryAppended in last 30 min: {len(rows)}")
anchored = [r for r in rows if r[3]]
no_anchor = [r for r in rows if not r[3]]
print(f"  anchored:    {len(anchored)}")
print(f"  no anchor:   {len(no_anchor)}")
print()

import json as _j
for r in rows[:25]:
    event_id, agent_id, blob_id, digest, ts, payload_json = r
    short_digest = (digest[:24] + "…") if digest else "NULL"
    # Pull a tag if present to identify "cross-vendor" events
    tags = ""
    try:
        p = _j.loads(payload_json)
        if "tags" in p:
            tags = str(p["tags"])
    except Exception:
        pass
    print(f"  ts={ts}  ev={event_id[:12]}  agent={(agent_id or '')[:8]}  "
          f"blob={(blob_id or '')[:14]}  digest={short_digest}  tags={tags[:30]}")
