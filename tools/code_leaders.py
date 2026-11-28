"""Materialise the biggest registrants per product code, so a device page can say who else is in its category.

The grouping takes 12.4 s on the production store (73,462 code/company pairs, measured 2026-11-29) and a
per-code lookup is worse at 14.6 s, so a page cannot afford either. The night computes it; the page reads one
indexed row set per code.

    python3 tools/code_leaders.py --reference /srv/medradar/reference_slim.db
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default="/srv/medradar/reference_slim.db")
    parser.add_argument("--top", type=int, default=5, help="how many companies to keep per code")
    args = parser.parse_args()

    from medradar.radar.code_leaders import leaders_for, store_leaders
    from medradar.radar.reference import UdiReference

    store = UdiReference(args.reference)
    try:
        written = store_leaders(store, top=args.top)
        print(json.dumps(written, ensure_ascii=False))
        sample = leaders_for(store, ["DZE"], limit=3).get("DZE") or []
        for item in sample:
            print(f"  DZE #{item['rank']} {item['company_name'][:44]} {item['devices']:,}")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
