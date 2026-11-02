"""Probe the 510(k) clearance-type distribution and per-cell code-age churn."""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

DB = Path("data/research.sqlite")


def main() -> int:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "select event_id, event_date, product_code, payload from events where kind='510k'").fetchall()
    con.close()

    types: Counter[str] = Counter()
    third: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    by_type_code: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except ValueError:
            payload = {}
        clearance = str(payload.get("clearance_type") or "(missing)").strip()
        types[clearance] += 1
        third[str(payload.get("third_party_flag") or "(missing)")] += 1
        decisions[str(payload.get("decision_code") or "(missing)")] += 1
        by_type_code[clearance][str(row["product_code"] or "")] += 1

    total = sum(types.values())
    print(f"== clearance_type over {total} 510(k) rows ==")
    for name, n in types.most_common():
        print(f"  {name:24s} {n:7d} ({n/total:6.2%})")
    print("\n== third_party_flag ==", dict(third))
    print("== decision_code (top) ==", dict(decisions.most_common(8)))

    print("\n== code first appearance inside the lane (churn risk) ==")
    first_seen: dict[str, str] = {}
    for row in rows:
        code = str(row["product_code"] or "")
        date = str(row["event_date"] or "")
        if code and (code not in first_seen or date < first_seen[code]):
            first_seen[code] = date
    years = Counter(value[:4] for value in first_seen.values())
    print(f"  distinct 510(k) product codes in lane: {len(first_seen)}")
    print(f"  first-seen year distribution: {dict(sorted(years.items()))}")
    late = {code for code, date in first_seen.items() if date >= "2022-01-01"}
    print(f"  codes first seen 2022+: {len(late)} ({len(late)/len(first_seen):.1%})")
    recent_events = sum(1 for row in rows if str(row["product_code"] or "") in late)
    print(f"  events under those codes: {recent_events} ({recent_events/total:.1%} of 510k rows)")
    late_clearance = Counter(
        str(json.loads(row["payload"] or "{}").get("clearance_type") or "(missing)")
        for row in rows if str(row["product_code"] or "") in late)
    print(f"  clearance types among those events: {dict(late_clearance)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
