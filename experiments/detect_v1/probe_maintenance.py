"""Probe: what fields let us separate technical activity from product maintenance?

B-035 needs to distinguish a 510(k) that introduces a technology from one that
modifies the filer's own existing device ("Special" 510(k)). Check what the lane carries.
Also probe the legacy full-history DB for product-code first-appearance (B-036 proxy).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

RESEARCH = Path("data/research.sqlite")
LEGACY = Path(r"D:\DEPPSKK\medradar\data\medradar.sqlite")


def main() -> int:
    con = sqlite3.connect(f"file:{RESEARCH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute("select payload from events where kind='510k' limit 4").fetchall()
    print("== sample 510(k) payloads ==")
    keys: Counter[str] = Counter()
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except ValueError:
            continue
        keys.update(payload.keys())
        print(json.dumps(payload, indent=1, ensure_ascii=False)[:900])
        print("---")
    print("payload key frequency:", dict(keys))

    print("\n== searching for maintenance/type indicators in 510(k) payloads ==")
    for token in ("special", "third party", "510(k) exempt", "decision_description",
                  "clearance_type", "review_type", "knumber", "product_code"):
        count = 0
        for row in con.execute("select payload from events where kind='510k'"):
            if token.lower() in str(row["payload"] or "").lower():
                count += 1
        print(f"  {token!r}: {count} rows contain it")
    con.close()

    print("\n== legacy full-history DB: product-code first appearance (taxonomy churn proxy) ==")
    if not LEGACY.exists():
        print("  legacy DB missing")
        return 0
    legacy = sqlite3.connect(f"file:{LEGACY}?mode=ro", uri=True)
    legacy.row_factory = sqlite3.Row
    rows = legacy.execute(
        "select product_code, min(event_date) first_seen, count(*) n from events "
        "where kind in ('510k','pma') and product_code is not null and product_code<>'' "
        "group by product_code").fetchall()
    print(f"  codes with any appearance: {len(rows)}")
    years = Counter()
    for row in rows:
        years[str(row["first_seen"])[:4]] += 1
    recent = {year: n for year, n in sorted(years.items()) if year >= "2016"}
    print(f"  codes first seen in 2016+ (inside the research window): {sum(recent.values())}")
    print(f"  distribution of first-seen years (2016+): {recent}")
    total_codes = len(rows)
    print(f"  share of codes whose first appearance is inside the research window: "
          f"{sum(recent.values()) / total_codes:.1%}" if total_codes else "n/a")
    legacy.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
