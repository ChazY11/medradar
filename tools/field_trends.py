"""Materialise the top rising term per field, so /areas can show it without paying for it.

Measured 2026-11-28: twenty fields cost 3.27 s cold and 0.84 s warm, on a page that answers in 0.67 s. The
index page needs the answer on every visit, so it is computed here - nightly, when nobody is waiting - and the
page prints the date it was computed. Same rule as `store_stats.py`: a number the page shows on every visit is
materialised, and a stale set is visible by its own timestamp.

    python3 tools/field_trends.py --reference /srv/medradar/reference_slim.db
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
    parser.add_argument("--limit", type=int, default=1,
                        help="how many rising terms to keep per field (the page shows one)")
    args = parser.parse_args()

    from medradar.radar.paper_passes import field_trends, store_field_trends
    from medradar.radar.reference import UdiReference

    store = UdiReference(args.reference)
    try:
        written = store_field_trends(store, limit=args.limit)
        print(json.dumps(written, ensure_ascii=False))
        sample = list(field_trends(store).items())[:5]
        for specialty, row in sample:
            print(f"  {specialty}: {row['term'] or '（无）'} "
                  f"{row['recent']}/{row['baseline']} {row['lift']}x")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
