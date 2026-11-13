#!/usr/bin/env python3
"""PHOENIX-001 / Step 01: coverage facts needed to FREEZE the experiment protocol."""
from __future__ import annotations

import json
from pathlib import Path

import sqlite3

REPO = Path(__file__).resolve().parents[3]
DB = REPO / "data" / "medradar.sqlite"
OUT = REPO / "experiments" / "phoenix" / "reports" / "01_coverage_facts.json"


def q(con, sql):
    try:
        return con.execute(sql).fetchall()
    except Exception as e:  # noqa: BLE001
        return [["ERR", repr(e)]]


def main() -> int:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro&immutable=1", uri=True)
    rep: dict = {}
    rep["kind_date_range"] = q(
        con,
        "select kind, count(*), min(event_date), max(event_date) from events "
        "where event_date is not null group by kind order by 2 desc",
    )
    rep["track_count"] = q(con, "select count(*) from tracks")
    rep["tracks"] = q(
        con, "select track_id, name_zh, name_en, domain from tracks order by track_id"
    )
    rep["events_by_track"] = q(
        con,
        "select track_id, count(*) n from events where track_id is not null "
        "group by track_id order by n desc",
    )
    rep["companies"] = q(con, "select * from companies order by 1")
    rep["company_events"] = q(
        con,
        "select company_key, count(*) n from events where company_key is not null "
        "group by company_key order by n desc",
    )
    rep["company_track_cells"] = q(
        con,
        "select count(*) from (select distinct company_key, track_id from events "
        "where company_key is not null and track_id is not null)",
    )
    rep["product_code_top"] = q(
        con,
        "select product_code, count(*) n from events where product_code is not null "
        "group by product_code order by n desc limit 40",
    )
    rep["510k_year"] = q(
        con,
        "select substr(event_date,1,4) y, count(*) from events where kind='510k' "
        "group by y order by y",
    )
    rep["pma_year"] = q(
        con,
        "select substr(event_date,1,4) y, count(*) from events where kind='pma' "
        "group by y order by y",
    )
    rep["trial_year"] = q(
        con,
        "select substr(event_date,1,4) y, count(*) from events where kind='trial' "
        "group by y order by y",
    )
    rep["recall_year"] = q(
        con,
        "select substr(event_date,1,4) y, count(*) from events where kind='device_recall' "
        "group by y order by y",
    )
    rep["track_kind_matrix"] = q(
        con,
        "select track_id, kind, count(*) n from events where track_id is not null "
        "group by track_id, kind order by track_id, n desc",
    )
    rep["available_at_null"] = q(
        con,
        "select kind, sum(case when available_at is null or available_at='' then 1 else 0 end) nul, "
        "count(*) tot from events group by kind",
    )
    rep["published_at_null"] = q(
        con,
        "select kind, sum(case when published_at is null or published_at='' then 1 else 0 end) nul, "
        "count(*) tot from events group by kind",
    )
    rep["event_sources_per_company_track_dup"] = q(
        con,
        "select count(*) from (select event_id, count(*) c from events group by event_id having c>1)",
    )
    # overlap: same applicant_raw string maps to more than one company_key
    rep["entity_multi_map"] = q(
        con,
        "select applicant_raw, count(distinct company_key) k from events "
        "where company_key is not null and applicant_raw is not null "
        "group by applicant_raw having k>1 order by k desc limit 30",
    )
    rep["tracks_config_path_hint"] = q(
        con, "select key, substr(value,1,200) from meta"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print("written", OUT)
    for k in (
        "kind_date_range",
        "track_count",
        "company_track_cells",
        "available_at_null",
        "published_at_null",
        "event_sources_per_company_track_dup",
    ):
        print(k, "=", rep[k])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
