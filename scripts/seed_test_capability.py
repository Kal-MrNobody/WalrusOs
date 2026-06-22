"""Seed one test capability row into the local SQLite to verify the
/api/permissions read path. Safe to run multiple times — uses fixed test IDs
so re-runs are no-ops (PRIMARY KEY conflict raises only IntegrityError,
which we swallow).

Usage:
    python scripts/seed_test_capability.py

To wipe the seeded rows afterwards:
    python scripts/seed_test_capability.py --clear
"""
from __future__ import annotations

import sys
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB = Path.home() / ".walrusos" / "walrusos.db"

# Use any existing stream_id so the join against memory_streams resolves to
# a real owner agent. Falls back gracefully if none exists.
SEED_GRANTS = [
    # (sui_object_id, target_stream_id_or_None, verb_bitmask, valid_until_epoch)
    ("0xCAP_SEED_001", None, 3,  0),    # READ + WRITE, never expires
    ("0xCAP_SEED_002", None, 11, 0),    # READ + WRITE + PUBLISH, never expires
]


def _resolve_stream_id(cur: sqlite3.Cursor) -> str | None:
    cur.execute("SELECT stream_id FROM memory_streams LIMIT 1")
    row = cur.fetchone()
    return row[0] if row else None


def main() -> None:
    if not DB.exists():
        sys.exit(f"DB not found: {DB}")

    clear = "--clear" in sys.argv
    con = sqlite3.connect(str(DB))
    cur = con.cursor()

    if clear:
        for cap_id, *_ in SEED_GRANTS:
            cur.execute("DELETE FROM capabilities WHERE sui_object_id = ?", (cap_id,))
        con.commit()
        print(f"Cleared {len(SEED_GRANTS)} seed grants.")
        return

    stream_id = _resolve_stream_id(cur)
    if stream_id is None:
        sys.exit("No memory_streams row to attach a capability to; aborting.")

    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for cap_id, _, bitmask, valid_until in SEED_GRANTS:
        try:
            cur.execute(
                "INSERT INTO capabilities "
                "(sui_object_id, target_stream_id, verb_bitmask, valid_until_epoch, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (cap_id, stream_id, bitmask, valid_until, now),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            print(f"  {cap_id}: already exists, skipped")
    con.commit()
    print(f"Seeded {inserted} new capability rows (stream_id={stream_id}).")

    # Verify
    cur.execute("SELECT COUNT(*) FROM capabilities")
    print(f"Total rows in capabilities table now: {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
