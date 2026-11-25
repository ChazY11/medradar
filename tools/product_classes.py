"""Fill product code -> device class from the FDA classification database.

    python3 tools/product_classes.py --missing 600      # the next 600 register codes
    python3 tools/product_classes.py --codes MAX KWP    # specific codes
    python3 tools/product_classes.py --summary

The register names 5,229 distinct product codes; one request carries twenty of them, so a full fill
is 262 requests and finishes in about a minute at the rate measured to stay inside openFDA's
unauthenticated limit. Idempotent: --missing only asks for codes the table has not answered for.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_REFERENCE = "/srv/medradar/reference_slim.db"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--missing", type=int, default=0,
                        help="fetch this many register codes the table has not answered for")
    parser.add_argument("--codes", nargs="*", default=[], help="specific product codes")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    from medradar.radar.http import HostPolicy, PoliteFetcher
    from medradar.radar.product_codes import (POLICY, codes_missing, fetch_classes,
                                              product_codes_summary, store_classes)

    reference_path = Path(args.reference)
    if not reference_path.exists():
        print(f"reference store not found: {reference_path}", file=sys.stderr)
        return 2

    from medradar.radar.reference import UdiReference

    fetcher = PoliteFetcher(user_agent="medradar/0.5 (classification fill)",
                            policies={"api.fda.gov": HostPolicy(**POLICY)}, max_requests=2_000)
    store = UdiReference(str(reference_path))
    try:
        wanted = [code.upper() for code in args.codes]
        if args.missing:
            wanted.extend(codes_missing(store, limit=args.missing))
        wanted = list(dict.fromkeys(wanted))
        if wanted:
            records = fetch_classes(fetcher, wanted)
            at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            written = store_classes(store, records, at=at)
            # A code can be missing from the classification database (retired, regional). Saying so
            # beats leaving it looking unfetched for ever.
            answered = {record["product_code"] for record in records}
            unanswered = [code for code in wanted if code not in answered]
            print(json.dumps({"asked": len(wanted), "answered": written,
                              "unanswered": unanswered[:20],
                              "unanswered_total": len(unanswered)}, ensure_ascii=False))
        if args.summary or not wanted:
            print(json.dumps(product_codes_summary(store), ensure_ascii=False, indent=2))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
