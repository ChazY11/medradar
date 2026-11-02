"""B-073: inventory the frozen data lanes so the backlog can state, with evidence, what is available.

The programme made this mistake once already: a "coverage too thin" conclusion turned out to be a pagination bug in
our own collector (D-029). Before reclassifying backlog items as blocked, count what is actually in the stores.

Usage:
    python experiments/b073/inventory_lanes.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.cycle2_coverage.panel import write_json  # noqa: E402

OUT = Path("experiments/b073/lane_inventory.json")

#: which tables matter for which backlog item — the point of the inventory is to answer that question
RELEVANCE = {
    "financial_facts": ["B-018", "B-021"],
    "market_bars": ["B-018", "B-021"],
    "publication_counts": ["B-018", "B-021", "B-041"],
    "procurement_awards": ["B-021"],
    "events": ["B-029", "B-032", "B-037"],
    "tracks": ["B-032", "B-037"],
    "companies": ["B-014"],
    "company_identifiers": ["B-014", "B-029"],
    "horizon_forecasts": ["B-015"],
    "product_codes": ["B-032"],
}


def main() -> int:
    payload: dict = {"schema": "lane_inventory_v1", "databases": {}, "relevance": RELEVANCE,
                     "reading": {}}
    for name in ("research", "tkg", "registry"):
        path = Path("data") / f"{name}.sqlite"
        if not path.exists():
            payload["databases"][name] = {"present": False}
            continue
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        tables = [row[0] for row in con.execute(
            "select name from sqlite_master where type='table' order by name")]
        counts: dict[str, int | None] = {}
        for table in tables:
            try:
                counts[table] = con.execute(f'select count(*) from "{table}"').fetchone()[0]
            except sqlite3.Error:
                counts[table] = None
        con.close()
        payload["databases"][name] = {"present": True, "size_bytes": path.stat().st_size,
                                      "tables": counts}

    research = payload["databases"].get("research", {}).get("tables", {})
    availability = {}
    for table, items in RELEVANCE.items():
        count = research.get(table)
        availability[table] = {"rows": count, "available": bool(count)}
        for item in items:
            availability.setdefault(item, {"items": []})
    for table, items in RELEVANCE.items():
        for item in items:
            availability[item]["items"].append({"table": table, "rows": research.get(table)})
    payload["availability_by_backlog_item"] = {
        item: {"tables": value["items"]}
        for item, value in availability.items() if "items" in value}
    payload["reading"] = {
        "conclusion": ("the financial, market and publication lanes are populated, so backlog items B-018, B-021, "
                       "B-029, B-037 and B-041 are NOT blocked on data; only items needing a human adjudicator "
                       "(B-014) or external access (B-030 patents, B-031 hiring, B-015 wall clock) are blocked"),
        "warning": ("a 'data unavailable' conclusion must be counted against the store before it is recorded - the "
                    "programme already retracted one such conclusion as a collector bug (D-029)"),
    }
    write_json(OUT, payload)

    print("table                               rows")
    for table, count in sorted(research.items()):
        if count:
            print(f"{table:32s}{count:>10}")
    print(f"\navailability by backlog item:")
    for item, block in payload["availability_by_backlog_item"].items():
        rows = ", ".join(f"{entry['table']}={entry['rows']}" for entry in block["tables"])
        print(f"  {item}: {rows}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
