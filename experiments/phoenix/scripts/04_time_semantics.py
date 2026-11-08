#!/usr/bin/env python3
"""PHOENIX-001 / Step 04: time-semantics audit.

Is `available_at` a real public-availability clock, or a backfill of event_date?
The answer determines how strongly our forecasts may be labelled 'point in time'.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
import phoenix_common as pc  # noqa: E402

OUT = HERE.parent / "reports" / "04_time_semantics.json"


def main() -> int:
    con = sqlite3.connect(f"file:{pc.DB_PATH.as_posix()}?mode=ro&immutable=1", uri=True)
    rep: dict = {}

    sql = """
      select kind,
             count(*) n,
             sum(case when available_at = event_date then 1 else 0 end) avail_eq_event,
             sum(case when published_at = event_date then 1 else 0 end) pub_eq_event,
             sum(case when available_at = published_at then 1 else 0 end) avail_eq_pub,
             min(available_at) min_avail, max(available_at) max_avail
      from events group by kind order by n desc
    """
    rep["by_kind"] = [list(r) for r in con.execute(sql)]

    # where they differ, how much?
    sql2 = """
      select kind,
             count(*) n,
             avg(julianday(available_at) - julianday(event_date)) mean_lag_days,
             min(julianday(available_at) - julianday(event_date)) min_lag,
             max(julianday(available_at) - julianday(event_date)) max_lag
      from events
      where available_at <> event_date
      group by kind order by n desc
    """
    rep["lag_where_different"] = [list(r) for r in con.execute(sql2)]

    sql3 = """
      select kind, count(*) from events
      where substr(available_at,1,10) > substr(fetched_at,1,10)
      group by kind
    """
    try:
        rep["available_after_fetch"] = [list(r) for r in con.execute(sql3)]
    except Exception as e:  # noqa: BLE001
        rep["available_after_fetch"] = repr(e)

    sql4 = "select kind, min(fetched_at), max(fetched_at) from events group by kind"
    rep["fetched_range"] = [list(r) for r in con.execute(sql4)]

    sql5 = "select * from meta"
    rep["meta"] = [list(r) for r in con.execute(sql5)]

    sql6 = """
      select substr(event_date,1,4) y, count(*) n, min(first_seen_at) ,
             avg(julianday(first_seen_at)-julianday(event_date)) mean_firstseen_lag
      from events where kind in ('510k','pma') group by y order by y desc limit 12
    """
    rep["first_seen_lag_by_year"] = [list(r) for r in con.execute(sql6)]

    con.close()
    pc.save_json(rep, OUT)
    print(json.dumps(rep, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
