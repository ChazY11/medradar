"""Refresh the specialty distribution the /areas page reads.

    python3 tools/specialty_stats.py --refresh
    python3 tools/specialty_stats.py --show

The work itself lives in medradar.radar.specialty, so the page can read the same table without the
web process needing this directory on its path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_REFERENCE = "/srv/medradar/reference_slim.db"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--leaders", type=int, default=5)
    args = parser.parse_args()

    from medradar.radar.reference import UdiReference
    from medradar.radar.specialty import read, refresh

    path = Path(args.reference)
    if not path.exists():
        print(f"reference store not found: {path}", file=sys.stderr)
        return 2
    store = UdiReference(str(path))
    try:
        if args.refresh:
            print(json.dumps(refresh(store, leaders=args.leaders), ensure_ascii=False))
        if args.show or not args.refresh:
            current = read(store)
            print(json.dumps({**current, "items": current["items"][:8]},
                             ensure_ascii=False, indent=2))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
