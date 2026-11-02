"""B-060: append a promotion to the append-only ledger, with attribution enforced.

A promoted alert is an operational decision, not a finding. It goes to
`research/RESULTS/PROMOTIONS.md` - never to the results ledger - and it cannot be written without a named
signer, a justification and a timestamp.

Usage (refuses to write anything unattributable):
    python experiments/b027/log_promotion.py --company medtronic --track insulin_delivery \
        --quarter 2025-Q3 --signer "name" --justification "reason" [--dry-run]

With no --signer the script prints the pending row and exits 2, which is the expected state in an autonomous
session: the programme can prepare a promotion but cannot sign one for a human.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence.promotion import (  # noqa: E402
    PROMOTION_COLUMNS,
    build_promotion_record,
    render_promotion_row,
)

LEDGER = Path("research/RESULTS/PROMOTIONS.md")
PROFILES = Path("experiments/b027/profiles.json")
HEADER = """# Promotions

**These are promotion decisions, not findings.** A promotion records that an alert's change persisted under
the confirmed two-month rule (D-043, replicated D-048) and that a named human accepted it. Findings live in
`README.md`; this file is append-only and each row names its signer.

| """ + " | ".join(PROMOTION_COLUMNS) + """ |
|""" + "|".join("---" for _ in PROMOTION_COLUMNS) + """|
"""


def find_decision(company: str, track: str, quarter: str) -> dict[str, Any] | None:
    payload = json.loads(PROFILES.read_text(encoding="utf-8"))
    profile = payload["profiles"].get(company)
    if not profile:
        return None
    for alert in profile["momentum"]["deployment_alerts"]["flagged"]:
        if alert.get("track") == track and alert.get("quarter") == quarter:
            return alert.get("promotion")
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", required=True)
    parser.add_argument("--track", required=True)
    parser.add_argument("--quarter", required=True)
    parser.add_argument("--signer", default="")
    parser.add_argument("--justification", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    decision = find_decision(args.company, args.track, args.quarter)
    if decision is None:
        print(f"no promotion decision found for {args.company}/{args.track} {args.quarter}")
        return 1

    try:
        record = build_promotion_record(
            decision, company=args.company, signer=args.signer,
            justification=args.justification,
            signed_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    except ValueError as exc:
        print(f"REFUSED: {exc}")
        print("\npending row (evidence complete, signature missing):")
        row = render_promotion_row({
            "id": f"{args.company}:{args.track}:{args.quarter}", "company": args.company,
            "track": args.track, "alert_quarter": args.quarter, "shape": decision.get("shape"),
            "relative_post_rate": decision.get("relative_post_rate"),
            "policy_version": decision.get("policy_version"), "verdict": "PENDING_SIGNOFF",
            "signer": "—", "signed_at_utc": "—", "justification": "—"})
        print(row)
        return 2

    if args.dry_run:
        print(render_promotion_row(record))
        return 0

    if not LEDGER.exists():
        LEDGER.write_text(HEADER, encoding="utf-8", newline="\n")
    existing = LEDGER.read_text(encoding="utf-8")
    if record["id"] in existing:
        print(f"{record['id']} is already logged")
        return 1
    LEDGER.write_text(existing.rstrip("\n") + "\n" + render_promotion_row(record) + "\n",
                      encoding="utf-8", newline="\n")
    print(f"logged promotion {record['id']} signed by {record['signer']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
