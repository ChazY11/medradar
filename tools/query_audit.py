"""Find the queries that scan a big table, by exercising the pages and reading their plans.

Why this exists
---------------
Two performance defects so far were the same shape: a query keyed on a column without an index, found
by measuring a page that felt slow rather than by looking for the cause. Audit 02 found a ten-second
page; audit 05 found the literature blocks had turned /device and /area into five-second pages because
`paper_term` had an index on `term` and none on `paper_id`.

Waiting for a page to feel slow is not a method. This tool renders the same data the pages render,
records every SQL statement they run, and asks SQLite for the plan of each one:

    python tools/query_audit.py --db /srv/medradar/reference_slim.db

A statement that plans as ``SCAN <table>`` over a table large enough to matter is a candidate defect,
with the row count and the measured time attached - not a guess.

This is a read-only instrument: it opens the store with mode=ro and never writes.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: A full scan is only interesting on a table this big or bigger. Below it the scan is faster than the
#: index lookup would be, and "add an index" would be advice that makes the product slower.
BIG_TABLE_ROWS = 50_000


def _row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        try:
            counts[str(name)] = int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
        except sqlite3.Error:
            continue
    return counts


def _capture(store: Any, work: list[tuple[str, Any]]) -> list[tuple[str, str]]:
    """Run each named piece of work with the SQL trace on; return (label, sql) pairs in order."""
    seen: list[tuple[str, str]] = []
    conn = store.conn
    current = {"label": "startup"}

    def tracer(sql: str) -> None:
        text = " ".join(str(sql).split())
        if text.upper().startswith(("SELECT", "WITH")):
            seen.append((current["label"], text))

    conn.set_trace_callback(tracer)
    try:
        for label, fn in work:
            current["label"] = label
            try:
                fn()
            except Exception as error:  # noqa: BLE001 - one broken surface must not stop the audit
                seen.append((label, f"-- failed: {type(error).__name__}: {error}"))
    finally:
        conn.set_trace_callback(None)
    return seen


def _plan(conn: sqlite3.Connection, sql: str) -> list[str]:
    try:
        return [" | ".join(str(part) for part in row)
                for row in conn.execute("EXPLAIN QUERY PLAN " + sql)]
    except sqlite3.Error as error:
        return [f"-- could not plan: {error}"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=40, help="how many findings to print")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    rows = _row_counts(conn)

    from medradar.radar import coverage as coverage_mod
    from medradar.radar import paper_passes, papers_index, specialty, store_stats
    from medradar.radar import device_view
    from medradar.radar.reference import UdiReference

    store = UdiReference(args.db)

    work: list[tuple[str, Any]] = [
        ("landing counts", lambda: store_stats.peek(store)),
        ("field list", lambda: specialty.read(store)),
        ("one field", lambda: specialty.one(store, "Dental")),
        ("field companies", lambda: specialty.companies_in_specialty(store, "Dental")),
        ("literature per field", lambda: paper_passes.by_specialty(store)),
        ("field topics", lambda: paper_passes.field_topics(store, "Dental")),
        ("recent in a field", lambda: paper_passes.recent_for(store, "Dental")),
        ("recent anywhere", lambda: paper_passes.recent_any(store)),
        ("paper terms", lambda: papers_index.paper_terms(store, "PMC13788955")),
        ("coverage page", lambda: coverage_mod.coverage(store)),
        ("device dossier", lambda: device_view.build(store, query="K213506")),
    ]

    captured = _capture(store, work)
    store.close()

    findings: list[dict[str, Any]] = []
    for label, sql in captured:
        if sql.startswith("--"):
            continue
        plan = _plan(conn, sql)
        scans = []
        for line in plan:
            if "SCAN " not in line:
                continue
            table = ""
            for token in line.replace("SCAN ", " ").split():
                if token.upper() not in {"SCAN", "USING", "INDEX", "COVERING", "TEMP", "B-TREE"}:
                    table = token
                    break
            scans.append({"table": table, "rows": rows.get(table, 0), "plan": line})
        big = [item for item in scans if item["rows"] >= BIG_TABLE_ROWS]
        if big:
            findings.append({"surface": label, "sql": sql[:220],
                             "tables": [item["table"] for item in big],
                             "rows": max(item["rows"] for item in big), "plan": plan})

    findings.sort(key=lambda item: -item["rows"])
    if args.json:
        print(json.dumps({"findings": findings, "statements": len(captured),
                          "big_tables": {k: v for k, v in rows.items() if v >= BIG_TABLE_ROWS}},
                         ensure_ascii=False, indent=2))
        conn.close()
        return 0

    print(f"  抓到 {len(captured)} 条 SELECT，大表（≥{BIG_TABLE_ROWS:,} 行）："
          f"{len([1 for v in rows.values() if v >= BIG_TABLE_ROWS])} 张")
    if not findings:
        print("  没有在 5 万行以上的表上做全扫的查询。")
    for item in findings[:args.limit]:
        print(f"\n  [{item['surface']}] {item['tables']} ({item['rows']:,} 行)")
        print(f"    {item['sql'][:150]}")
        for line in item["plan"]:
            print(f"      {line}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
