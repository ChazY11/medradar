#!/usr/bin/env python3
"""PHOENIX-001 / Step 00: read-only asset inventory for the frozen experiment protocol.

Opens data/medradar.sqlite in immutable read-only mode. Never writes to the DB.
Writes a JSON report to experiments/phoenix/reports/00_asset_inventory.json
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DB = REPO / "data" / "medradar.sqlite"
OUT = REPO / "experiments" / "phoenix" / "reports" / "00_asset_inventory.json"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def connect_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)


def table_info(con: sqlite3.Connection) -> dict:
    rows = con.execute(
        "select name, type from sqlite_master where type in ('table','view') order by name"
    ).fetchall()
    out = {"tables": [], "views": []}
    for name, typ in rows:
        entry = {"name": name}
        try:
            entry["columns"] = [
                {"name": r[1], "type": r[2], "notnull": r[3], "pk": r[5]}
                for r in con.execute(f'pragma table_info("{name}")')
            ]
            entry["rows"] = con.execute(f'select count(*) from "{name}"').fetchone()[0]
        except Exception as e:  # noqa: BLE001
            entry["error"] = repr(e)
        out["tables" if typ == "table" else "views"].append(entry)
    return out


def main() -> int:
    rep: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": str(REPO),
        "db": str(DB),
        "db_exists": DB.exists(),
        "python": sys.version,
        "os": os.name,
    }
    if not DB.exists():
        rep["status"] = "MISSING"
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(rep, indent=2), encoding="utf-8")
        print(json.dumps(rep, indent=2))
        return 1

    st = DB.stat()
    rep["db_size_bytes"] = st.st_size
    rep["db_sha256"] = sha256_file(DB)
    rep["db_mtime_utc"] = datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()

    con = connect_ro(DB)
    try:
        info = table_info(con)
        rep["schema"] = info
        rep["integrity_check"] = con.execute("pragma integrity_check").fetchone()[0]
        rep["page_count"] = con.execute("pragma page_count").fetchone()[0]
        rep["freelist_count"] = con.execute("pragma freelist_count").fetchone()[0]

        names = {t["name"] for t in info["tables"]}
        if "events" in names:
            rep["events_kind"] = [
                dict(zip(("kind", "n"), r))
                for r in con.execute(
                    "select kind, count(*) from events group by kind order by 2 desc"
                )
            ]
            rep["events_source"] = [
                dict(zip(("source", "n"), r))
                for r in con.execute(
                    "select source, count(*) from events group by source order by 2 desc"
                )
            ]
            rep["events_year"] = [
                dict(zip(("year", "n"), r))
                for r in con.execute(
                    "select substr(event_date,1,4) y, count(*) from events "
                    "where event_date is not null and length(event_date)>=4 "
                    "group by y order by y"
                )
            ]
            rep["timestamp_quality"] = [
                dict(zip(("timestamp_quality", "n"), r))
                for r in con.execute(
                    "select timestamp_quality, count(*) from events group by 1 order by 2 desc"
                )
            ]
            rep["events_columns_present"] = [
                r[1] for r in con.execute("pragma table_info(events)")
            ]
            for col in ("company_key", "track_id", "product_code"):
                try:
                    n = con.execute(
                        f"select count(*) from events where {col} is not null and {col} <> ''"
                    ).fetchone()[0]
                    rep[f"events_nonnull_{col}"] = n
                except Exception as e:  # noqa: BLE001
                    rep[f"events_nonnull_{col}"] = f"ERR {e!r}"
    finally:
        con.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "schema"}, indent=2))
    print("\n--- tables ---")
    for t in rep["schema"]["tables"]:
        print(f"  {t['name']}: {t.get('rows')} rows, {len(t.get('columns', []))} cols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
