"""Phase 0: are Dräger and Mindray actually present as raw applicants, even though the store has no company_key?

The main store's `companies` table has no row for either firm, so `company_key`-based counting reports zero. That is
a statement about the store's roster, not about the data. The frozen research lane resolves applicants through a
deterministic entity universe, so the honest probe is over `applicant_raw`.

Read-only.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

LANES = {
    "research": Path("data/research.sqlite"),
    "main_store": Path("D:/DEPPSKK/medradar/data/medradar.sqlite"),
}
PATTERNS = {
    "draeger": ("%DRAGER%", "%DRÄGER%", "%DRAEGERWERK%"),
    "mindray": ("%MINDRAY%",),
}

for label, path in LANES.items():
    if not path.exists():
        print(f"{label}: absent")
        continue
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    print("=" * 78)
    print(f"{label}  ({path})")
    for firm, patterns in PATTERNS.items():
        clause = " or ".join("upper(applicant_raw) like ?" for _ in patterns)
        params = [pattern for pattern in patterns]
        rows = con.execute(
            f"select source, kind, count(*), min(event_date), max(event_date) from events "
            f"where {clause} group by source, kind order by count(*) desc", params).fetchall()
        total = sum(row[2] for row in rows)
        print(f"  {firm}: total={total}")
        for source, kind, n, lo, hi in rows:
            print(f"    {source:28s} {kind:14s} {n:>6}  {lo} .. {hi}")
        print(f"    top tracks: {con.execute(f'select track_id, count(*) from events where {clause} and track_id is not null group by track_id order by count(*) desc limit 8', params).fetchall()}")
    con.close()
