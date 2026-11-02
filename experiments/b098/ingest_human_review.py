"""Ingest a completed human review worksheet and produce the adjudicated dataset.

Refuses to write anything unless every row passes validation (five-label vocabulary, reviewer name, reason,
independent confirmation for Confirmed Shift, no duplicate packets). On success emits ADJUDICATION_HUMAN_V1.json with
the human labels, the reviewers, the timestamp, per-label counts and the (descriptive-only) agreement with the agent
rubric.

    python experiments/b098/ingest_human_review.py --in HUMAN_REVIEW_WORKSHEET.csv [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.studies.humanreview import (  # noqa: E402
    agreement,
    normalise_label,
    summarise_review,
    validate_rows,
)

STUDY = Path("research/studies/early_signal_5firms")
OUT = STUDY / "ADJUDICATION_HUMAN_V1.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="input_path", default=str(STUDY / "HUMAN_REVIEW_WORKSHEET.csv"))
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    path = Path(args.input_path)
    if not path.exists():
        print(f"worksheet not found: {path}")
        return 1
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    validation = validate_rows(rows)
    if not validation["valid"]:
        print(f"REFUSING TO WRITE: {len(validation['problems'])} problem(s)")
        for problem in validation["problems"][:40]:
            print(f"  - {problem}")
        if len(validation["problems"]) > 40:
            print(f"  ... and {len(validation['problems']) - 40} more")
        return 2

    summary = summarise_review(rows)
    agreement_stats = agreement(rows)
    payload = {
        "schema": "adjudication_human_v1",
        "authority": "human",
        "source_worksheet": str(path).replace("\\", "/"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": summary["total"],
        "reviewers": summary["reviewers"],
        "label_counts": summary["counts"],
        "agent_agreement": agreement_stats,
        "note": ("human labels: these replace the agent's preliminary rubric as the study's Target B labels. The "
                 "agreement statistic is descriptive only and must not be used to tune the rubric."),
        "rows": [{"packet_id": row["packet_id"],
                  "company": row.get("company"),
                  "technology_track": row.get("technology_track"),
                  "final_label": normalise_label(row.get("human_label")),
                  "reason": row.get("human_reason"),
                  "independent_confirmation": row.get("independent_confirmation"),
                  "reviewer": row.get("reviewer"),
                  "reviewed_at": row.get("reviewed_at")}
                 for row in rows],
    }
    if args.dry_run:
        print(f"DRY RUN — would write {args.out}")
        print(f"rows: {summary['total']}  reviewers: {summary['reviewers']}  labels: {summary['counts']}")
        print(f"agent agreement (descriptive): {agreement_stats['agreement']}")
        return 0

    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")
    print(f"rows: {summary['total']}  reviewers: {summary['reviewers']}")
    print(f"labels: {summary['counts']}")
    print(f"agent agreement (descriptive): {agreement_stats['agreement']} over "
          f"{agreement_stats['compared']} compared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
