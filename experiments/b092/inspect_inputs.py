"""Inspect the inputs the crosswalk needs: track keyword lists and trial text fields."""
from __future__ import annotations

import json
import sqlite3

con = sqlite3.connect("file:D:/DEPPSKK/medradar/data/medradar.sqlite?mode=ro", uri=True)
rows = con.execute("select id, name_en, keywords from tracks where id not like 't\\_%' escape '\\'").fetchall()
print(f"device tracks: {len(rows)}")
for track_id, name, keywords in rows[:8]:
    try:
        parsed = json.loads(keywords) if keywords else []
    except (TypeError, ValueError):
        parsed = keywords
    print(f"  {track_id:22s} | {name} | {str(parsed)[:110]}")

print("\ntrial text fields (first 3):")
for (payload,) in con.execute("select payload from events where kind='trial' limit 3"):
    data = json.loads(payload or "{}")
    print(f"  conditions={data.get('conditions')} title={(data.get('brief_title') or '')[:70]}")

print("\ntrial track distribution (top):")
for track, count in con.execute(
        "select track_id, count(*) from events where kind='trial' group by track_id "
        "order by count(*) desc limit 10"):
    print(f"  {track}: {count}")
con.close()
