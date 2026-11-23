"""Load ODP bulk patent tables into the device register, then report what is queryable.

    python tools/bulk_patents.py --patents g_patent.tsv.zip \
                                 --assignees g_assignee_disambiguated.tsv.zip
    python tools/bulk_patents.py --summary
    python tools/bulk_patents.py --whois "Medtronic Sofamor Danek"

No API key and no network: these are the ODP bulk files, which are a full historical dump rather
than a paginated query. Once they are loaded, ``device_view`` starts answering the patent section
with no further change - it reads whatever is in the register.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medradar.radar.patents_bulk import (bulk_summary, import_tables,
                                         patents_for_assignee)
from medradar.radar.reference import UdiReference

DEFAULT_REFERENCE = "/srv/medradar/reference_slim.db"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--patents", help="g_patent.tsv or g_patent.tsv.zip")
    parser.add_argument("--assignees", help="g_assignee_disambiguated.tsv or .zip")
    parser.add_argument("--summary", action="store_true", help="report table contents and exit")
    parser.add_argument("--whois", help="count patents for one organisation")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    reference_path = Path(args.reference)
    if not reference_path.exists():
        print(f"reference store not found: {reference_path}", file=sys.stderr)
        return 2

    store = UdiReference(str(reference_path))
    try:
        if args.patents or args.assignees:
            def progress(table, stats):
                print(f"  {table}: {json.dumps(stats.summary(), ensure_ascii=False)}",
                      flush=True)
            result = import_tables(store, args.patents, args.assignees, progress=progress)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.summary or not (args.patents or args.assignees or args.whois):
            print("tables:", json.dumps(bulk_summary(store), ensure_ascii=False))
        if args.whois:
            found = patents_for_assignee(store, args.whois, limit=args.limit)
            print(json.dumps(found, ensure_ascii=False, indent=2))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
