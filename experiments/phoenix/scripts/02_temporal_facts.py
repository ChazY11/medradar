#!/usr/bin/env python3
"""PHOENIX-001 / Step 02: temporal coverage & left-truncation facts."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DB = REPO / "data" / "medradar.sqlite"
OUT = REPO / "experiments" / "phoenix" / "reports" / "02_temporal_facts.json"

SQL = {
    "device_year_track_co": """
        select substr(event_date,1,4) y,
               sum(case when track_id is not null then 1 else 0 end) with_track,
               sum(case when company_key is not null then 1 else 0 end) with_co,
               count(*) n
        from events where kind in ('510k','pma') group by y order by y""",
    "all_year_by_kind": """
        select substr(event_date,1,4) y, kind, count(*) n from events
        where kind in ('510k','pma','device_recall','trial','8k_catalyst')
        and cast(substr(event_date,1,4) as int) >= 1995
        group by y, kind order by y, kind""",
    "track_first_last": """
        select track_id, min(event_date), max(event_date), count(*) n
        from events where track_id is not null group by track_id order by n desc""",
    "company_first_last": """
        select company_key, min(event_date), max(event_date), count(*) n
        from events where company_key is not null group by company_key order by n desc""",
    "track_by_year_matrix": """
        select substr(event_date,1,4) y, track_id, count(*) n from events
        where track_id is not null and kind in ('510k','pma')
        and cast(substr(event_date,1,4) as int) >= 2000
        group by y, track_id order by y, n desc""",
    "recall_510k_paired": """
        select count(*) from events a join events b
          on a.kind='device_recall' and b.kind='510k'
         and substr(a.payload,1,400) like '%'||b.product_code||'%'
        where 0""",
    "payload_sample": "select event_id, kind, payload from events where kind='510k' limit 2",
    "recall_payload_sample": "select event_id, kind, payload from events where kind='device_recall' limit 2",
    "trial_payload_sample": "select event_id, kind, payload from events where kind='trial' limit 2",
    "tracks_meta_sample": "select * from meta",
    "product_codes_sample": "select * from product_codes limit 5",
}


def main() -> int:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro&immutable=1", uri=True)
    rep = {}
    for name, sql in SQL.items():
        try:
            cur = con.execute(sql)
            rep[name] = [list(r) for r in cur.fetchall()]
        except Exception as e:  # noqa: BLE001
            rep[name] = ["ERR", repr(e)]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("written", OUT)
    print("== device_year_track_co ==")
    for r in rep["device_year_track_co"]:
        print(r)
    print("== meta ==")
    for r in rep["tracks_meta_sample"]:
        print(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
