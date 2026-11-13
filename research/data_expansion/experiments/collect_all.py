#!/usr/bin/env python
"""Collect a bounded sample from every discovered connector into the staging store."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT.parents[1]))

import harness  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25, help="records requested per source")
    parser.add_argument("--only", nargs="*", default=None, help="restrict to these source ids")
    args = parser.parse_args(argv)

    connectors = harness.discover_connectors()
    broken = harness.broken_modules(connectors)
    if broken:
        print("BROKEN CONNECTORS:", file=sys.stderr)
        for entry in broken:
            print(f"  {entry}", file=sys.stderr)
    payload = harness.collect_all(connectors, limit=args.limit, sources=args.only)
    print(json.dumps(payload["totals"], indent=2))
    print(f"{'source':<34} {'returned':>8} {'written':>7} {'dup':>5} {'invalid':>7} {'req':>4}  error")
    for row in payload["sources"]:
        print(
            f"{row['source_id']:<34} {row['records_returned']:>8} {row['records_written']:>7} "
            f"{row['content_duplicates']:>5} {row['invalid_rejected']:>7} {row['requests']:>4}  "
            f"{row['error'][:70]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
