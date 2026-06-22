import sqlite3
from pathlib import Path
con = sqlite3.connect(str(Path.home()/".walrusos"/"walrusos.db"))
cur = con.cursor()
cur.execute(
    "SELECT event_id, transaction_digest FROM protocol_events "
    "WHERE event_id LIKE '7d93ac6531fbc3f8%' LIMIT 1"
)
row = cur.fetchone()
print(f"event_id:  {row[0]}")
print(f"tx_digest: {row[1]}")
print(f"verify:    https://suiscan.xyz/testnet/tx/{row[1]}")
