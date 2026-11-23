"""Query one device's full public life: clearance, document sections, failures, gaps.

    python tools/device_view.py --query X1209255
    python tools/device_view.py --query K210313 --json
    python tools/device_view.py --query 557821945 --corpus /srv/medradar/intel/corpus510k

Default paths point at the deployed layout on the intel host, so the command works there with
no arguments beyond the query.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medradar.radar.device_view import build, render
from medradar.radar.reference import UdiReference

DEFAULT_REFERENCE = "/srv/medradar/reference_slim.db"
DEFAULT_CORPUS = "/srv/medradar/intel/corpus510k"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True,
                        help="K number, DI, DUNS, model number, catalog number, brand or company")
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--corpus", default=DEFAULT_CORPUS)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--no-failures", action="store_true",
                        help="skip the failure lookup (faster for a company-wide query)")
    args = parser.parse_args()

    reference_path = Path(args.reference)
    if not reference_path.exists():
        print(f"reference store not found: {reference_path}", file=sys.stderr)
        return 2
    corpus = Path(args.corpus) if args.corpus and Path(args.corpus).exists() else None

    reference = UdiReference(str(reference_path))
    try:
        timeline = build(reference, args.query, corpus_root=corpus, limit=args.limit,
                         failures=not args.no_failures)
    finally:
        reference.close()

    if args.json:
        print(json.dumps(timeline.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render(timeline))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
