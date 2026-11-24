"""Fill the patent tables from EPO OPS instead of USPTO bulk files.

    python3 tools/ops_patents.py --check
    python3 tools/ops_patents.py --assignee "Medtronic" --assignee "Stryker"
    python3 tools/ops_patents.py --top-companies 40 --rows 50

Requires two environment variables, both from a free consumer key at
https://developers.epo.org (that host answers 403 to non-browser clients, so the registration
has to happen in a real browser):

    EPO_OPS_KEY, EPO_OPS_SECRET

Rows land in the same `bulk_patent` / `bulk_patent_assignee` tables the file importer writes, so
`device_view` answers the patent section without knowing which origin filled it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medradar.radar.http import HostPolicy, PoliteFetcher
from medradar.radar.patents_ops import (KEY_ENV, MAX_RANGE, OpsClient,
                                        OpsCredentialMissing, import_assignee)
from medradar.radar.patents_bulk import bulk_summary
from medradar.radar.reference import UdiReference

DEFAULT_REFERENCE = "/srv/medradar/reference_slim.db"
USER_AGENT = "MedRadar/0.1 (+https://github.com/ChazY11/medradar; research)"
#: OPS publishes a 4 GB/month fair-use ceiling and throttles per minute. One query is a small
#: JSON page; one request a second keeps a few hundred assignees well inside both.
OPS_POLICY = HostPolicy(requests_per_second=1.0, timeout_seconds=45.0)


def top_assignees(reference, limit: int) -> list[str]:
    """Company names from the device register, biggest labeler first.

    OPS indexes applicants by the name they filed under, which for a group is usually the parent,
    so the legal name in the register is the right thing to ask for here - unlike ClinicalTrials,
    whose sponsor strings are subsidiaries.
    """
    rows = reference.conn.execute(
        "SELECT company_name FROM udi_company ORDER BY device_count DESC LIMIT ?",
        (max(1, limit),)).fetchall()
    return [str(row[0]) for row in rows if row[0]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--assignee", action="append", default=[],
                        help="applicant name to query; repeatable")
    parser.add_argument("--top-companies", type=int, default=0,
                        help="also query the biggest labelers in the register")
    parser.add_argument("--rows", type=int, default=MAX_RANGE,
                        help=f"hits per assignee (max {MAX_RANGE})")
    parser.add_argument("--check", action="store_true",
                        help="verify the credentials and exit without writing")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    fetcher = PoliteFetcher(user_agent=USER_AGENT,
                            policies={"ops.epo.org": OPS_POLICY}, max_requests=5_000)
    try:
        client = OpsClient.from_env(fetcher)
    except OpsCredentialMissing as error:
        print(str(error), file=sys.stderr)
        return 3

    try:
        token = client.token()
    except Exception as error:  # noqa: BLE001 - surfaced verbatim so the operator can act
        print(f"token request failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 4
    print(f"  token acquired ({len(token)} chars)", file=sys.stderr)

    # A credential check must not depend on a local store: the question it answers is whether the
    # key works, and requiring the database would report a path problem as an auth problem.
    if args.check and not args.assignee and not args.top_companies and not args.summary:
        print(json.dumps({"credentials": "ok"}, ensure_ascii=False))
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

        if args.check:
            print(json.dumps({"credentials": "ok", "assignees": len(assignees)},
                             ensure_ascii=False))
        for name in assignees:
            try:
                result = import_assignee(store, name, client=client, rows=args.rows)
            except Exception as error:  # noqa: BLE001 - one bad name must not stop the batch
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
