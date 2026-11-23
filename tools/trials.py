"""Load clinical trials for a set of sponsors, then report what is queryable.

    python tools/trials.py --sponsor "Medtronic" --sponsor "Stryker"
    python tools/trials.py --top-companies 20          # derive sponsors from the register
    python tools/trials.py --summary
    python tools/trials.py --whois "Medtronic"

No credential, no registration. Measured against the live registry: 200 from the production
host, ``totalCount`` 1,677 for Medtronic, and each record carries the device names under study.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medradar.radar.reference import UdiReference
from medradar.radar.trials import import_trials, trials_for_sponsor, trials_summary

DEFAULT_REFERENCE = "/srv/medradar/reference_slim.db"
#: Words that start a company name but do not identify the group.
_SKIP = {"THE", "UNITED", "AMERICAN", "GENERAL", "ADVANCED", "GLOBAL", "INTEGRA"}


def group_tokens(reference, limit: int) -> list[str]:
    """The most common first tokens of the biggest labelers.

    Registry sponsors are subsidiaries ("Medtronic - MITG"), so querying a full UDI legal name
    usually returns nothing. The group token is what the registry actually indexes.
    """
    rows = reference.conn.execute(
        "SELECT company_name FROM udi_company ORDER BY device_count DESC LIMIT ?",
        (max(limit * 5, 100),),
    ).fetchall()
    counts: dict[str, int] = {}
    for (name,) in rows:
        tokens = str(name or "").replace(",", " ").split()
        if not tokens:
            continue
        first = tokens[0].strip(".").upper()
        if len(first) < 5 or first in _SKIP:
            continue
        counts[first] = counts.get(first, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: -kv[1])
    return [token for token, _ in ordered[:limit]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--sponsor", action="append", default=[],
                        help="sponsor string to query; repeatable")
    parser.add_argument("--top-companies", type=int, default=0,
                        help="also derive group tokens from the biggest labelers")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--whois", help="count trials for one sponsor")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    reference_path = Path(args.reference)
    if not reference_path.exists():
        print(f"reference store not found: {reference_path}", file=sys.stderr)
        return 2

    store = UdiReference(str(reference_path))
    try:
        sponsors = list(args.sponsor)
        if args.top_companies:
            sponsors.extend(group_tokens(store, args.top_companies))
        sponsors = list(dict.fromkeys(s for s in sponsors if s.strip()))

        if sponsors:
            def progress(stats):
                print(f"  {stats.sponsors} sponsors · {stats.requests} requests · "
                      f"{stats.rows_written:,} rows · errors {len(stats.errors)}", flush=True)
            stats = import_trials(store, sponsors, page_size=args.page_size,
                                  max_pages=args.max_pages, progress=progress)
            print(json.dumps(stats.summary(), ensure_ascii=False, indent=2))

        if args.summary or not (sponsors or args.whois):
            print("tables:", json.dumps(trials_summary(store), ensure_ascii=False))
        if args.whois:
            print(json.dumps(trials_for_sponsor(store, args.whois, limit=args.limit),
                             ensure_ascii=False, indent=2))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
