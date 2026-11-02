"""Verify that every quantitative claim in the paper is sourced in a committed artifact.

Two checks per claim:
  1. the source artifact really contains the recorded substring;
  2. the paper text really contains the value as written.

The second check is what stops the paper from drifting away from its evidence: if a number changes
in the paper without changing in CLAIMS.json (or vice versa), this fails.

    python papers/verify_claims.py [--paper papers/PAPER_v1.md]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def read_any(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", "replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper", default="papers/PAPER_v1.md")
    parser.add_argument("--claims", default="papers/CLAIMS.json")
    args = parser.parse_args(argv)

    claims = json.loads(Path(args.claims).read_text(encoding="utf-8"))["claims"]
    paper = read_any(Path(args.paper))
    failures: list[str] = []
    for claim in claims:
        source = Path(claim["source"])
        if not source.exists():
            failures.append(f"{claim['id']}: source missing: {claim['source']}")
            continue
        if claim["source_needle"] not in read_any(source):
            failures.append(f"{claim['id']}: needle not in source: {claim['source_needle']!r}")
        if claim["value"] not in paper:
            failures.append(f"{claim['id']}: value {claim['value']!r} not present in the paper")
    print(f"claims checked: {len(claims)}; failures: {len(failures)}")
    for failure in failures:
        print(f"  - {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
