"""Refresh the materialised counts the landing page reads.

    python3 tools/store_stats.py --refresh
    python3 tools/store_stats.py --show

Run by the nightly job and after any large import. The page prints the timestamp this writes, so a
stale set is visible rather than silent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_REFERENCE = "/srv/medradar/reference_slim.db"
DEFAULT_CORPUS = "/srv/medradar/intel/corpus510k"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--corpus", default=DEFAULT_CORPUS)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    from medradar.radar.reference import UdiReference
    from medradar.radar.store_stats import age_seconds, read, refresh

    path = Path(args.reference)
    if not path.exists():
        print(f"reference store not found: {path}", file=sys.stderr)
        return 2
    store = UdiReference(str(path))
    try:
        if args.refresh:
            print(json.dumps(refresh(store, corpus_dir=args.corpus), ensure_ascii=False))
        if args.show or not args.refresh:
            current = read(store)
            current["age_seconds"] = age_seconds(current)
            print(json.dumps(current, ensure_ascii=False, indent=2))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
