"""Fill the patent tables from Google Patents while the EPO account is under review.

    python3 tools/google_patents.py --assignee Medtronic --pages 3
    python3 tools/google_patents.py --top-companies 40 --pages 2
    python3 tools/google_patents.py --probe          # one request, print the shape

No credential is needed. EPO OPS stays the durable source (``tools/ops_patents.py``); both write
the same two tables, so a device answers the patent section regardless of which lane filled it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medradar.radar.http import HostPolicy, PoliteFetcher
from medradar.radar.patents_bulk import bulk_summary
from medradar.radar.patents_google import (MAX_PAGES, GooglePatentsClient,
                                           GooglePatentsError, import_assignee, parse)
from medradar.radar.reference import UdiReference

DEFAULT_REFERENCE = "/srv/medradar/reference_slim.db"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/131.0.0.0 Safari/537.36")
#: This is an undocumented internal endpoint, so it is treated as a guest: one request every two
#: seconds is slower than a person clicking through the same pages.
GOOGLE_POLICY = HostPolicy(requests_per_second=0.5, timeout_seconds=45.0, max_attempts=2,
                           backoff_base_seconds=5.0)


def top_assignees(reference, limit: int) -> list[str]:
    rows = reference.conn.execute(
        "SELECT company_name FROM udi_company ORDER BY device_count DESC LIMIT ?",
        (max(1, limit),)).fetchall()
    return [str(row[0]) for row in rows if row[0]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--assignee", action="append", default=[])
    parser.add_argument("--top-companies", type=int, default=0)
    parser.add_argument("--pages", type=int, default=1,
                        help=f"10 hits per page, hard ceiling {MAX_PAGES} pages")
    parser.add_argument("--country", default="", help="optional country filter, e.g. US")
    parser.add_argument("--probe", action="store_true",
                        help="issue one request for --assignee and print the parsed shape")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    fetcher = PoliteFetcher(user_agent=USER_AGENT,
                            policies={"patents.google.com": GOOGLE_POLICY}, max_requests=2_000)
    client = GooglePatentsClient(fetcher)

    if args.probe:
        name = (args.assignee or ["Medtronic"])[0]
        try:
            payload = client.search(name, page=0, country=args.country)
            total, hits = parse(payload)
        except GooglePatentsError as error:
            print(f"probe failed: {error}", file=sys.stderr)
            return 4
        print(json.dumps({"assignee": name, "total": total, "page_hits": len(hits),
                          "first": hits[0].to_dict() if hits else None},
                         ensure_ascii=False, indent=2))
        return 0

    reference_path = Path(args.reference)
    if not reference_path.exists():
        print(f"reference store not found: {reference_path}", file=sys.stderr)
        return 2

    store = UdiReference(str(reference_path))
    try:
        assignees = list(args.assignee)
        if args.top_companies:
            assignees.extend(top_assignees(store, args.top_companies))
        assignees = list(dict.fromkeys(a for a in assignees if a.strip()))
        for name in assignees:
            try:
                result = import_assignee(store, name, client=client, pages=args.pages,
                                        country=args.country)
            except Exception as error:  # noqa: BLE001 - one bad name must not stop a batch
                print(f"  {name}: {type(error).__name__}: {error}", file=sys.stderr)
                continue
            print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        if args.summary or not assignees:
            print("tables:", json.dumps(bulk_summary(store), ensure_ascii=False))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
