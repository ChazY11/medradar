"""Ad-hoc diagnostic: how does the rules baseline treat the tracks it misses?

The deterministic A arm assigns a technology track to only ~6% of the snapshot. That
number is only interpretable if we know *why*: is the track absent from the adverts, or
present in the text but refused by the gate? This diagnostic measures both, for a small
set of tracks, and writes the evidence a reviewer needs to judge the classifier.

It is a diagnostic, not a result: it does not change any label.

Usage:
    python experiments/innovation_signals_observatory/sources/diagnose_track_coverage.py \
        --jobs results/2026-11-04/jobs_medtronic.jsonl --out results/2026-11-04
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from medradar.recruitment import taxonomy as tax  # noqa: E402

#: Plain-language probe terms, deliberately NOT the taxonomy keywords, so a hit means
#: "the advert talks about this" independently of how the taxonomy is worded.
PROBES = {
    "surgical_robotics": [r"\brobot", r"\bhugo\b", r"robotic"],
    "medical_ai": [r"\bai\b", r"artificial intelligence", r"machine learning", r"\bml\b", r"deep learning"],
    "ep_pfa": [r"pulsed field", r"electroporation", r"\bpfa\b", r"electrophysiolog", r"ablation"],
    "neurostimulation": [r"neurostimulat", r"deep brain", r"\bdbs\b", r"spinal cord stimulat", r"neuromodulat"],
    "structural_heart": [r"transcatheter", r"\btavr\b", r"mitral", r"tricuspid", r"structural heart"],
    "cardiac_rhythm": [r"pacemaker", r"defibrillat", r"\bicd\b", r"cardiac rhythm", r"bradycardia"],
    "imaging_us": [r"ultrasound", r"echocardiograph", r"sonograph"],
    "diabetes": [r"insulin pump", r"continuous glucose", r"\bcgm\b", r"diabetes"],
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rows = tax.load_job_rows(Path(args.jobs))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    report: dict[str, dict] = {}
    for track, patterns in PROBES.items():
        regex = re.compile("|".join(patterns), re.I)
        mentioned, assigned, refused = [], [], []
        for row in rows:
            text = f"{row.get('job_title') or ''}\n{row.get('job_description') or ''}"
            if not regex.search(text):
                continue
            cls = tax.classify_rules(row)
            entry = {
                "posting_id": row.get("posting_id"),
                "title": row.get("job_title"),
                "function_class": cls["function_class"],
                "track_id": cls["track_id"],
                "track_status": cls.get("track_status"),
            }
            mentioned.append(entry)
            if cls["track_id"] == track:
                assigned.append(entry)
            elif cls["track_id"] is None:
                refused.append(entry)
        report[track] = {
            "n_postings_mentioning": len(mentioned),
            "n_assigned_to_this_track": len(assigned),
            "n_mentioned_but_no_track": len(refused),
            "function_classes_among_mentions": dict(Counter(e["function_class"] for e in mentioned)),
            "track_statuses_among_mentions": dict(Counter(str(e["track_status"]) for e in mentioned)),
            "examples_assigned": assigned[:5],
            "examples_mentioned_but_unassigned": refused[:5],
        }

    payload = {
        "diagnostic": "rules-baseline track coverage on job adverts",
        "jobs_file": str(Path(args.jobs).name),
        "n_postings": len(rows),
        "note": ("probe terms are independent plain-language phrasings, not the taxonomy keywords; "
                 "a large gap between 'mentioning' and 'assigned' is the measured transfer failure of "
                 "a taxonomy built for product-code/regulatory text, and is reported rather than fixed "
                 "by loosening the gate"),
        "tracks": report,
        "versions": tax.label_versions(),
    }
    path = out / "track_coverage_diagnostic.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for track, r in report.items():
        print(f"{track:20s} mentioned={r['n_postings_mentioning']:4d} assigned={r['n_assigned_to_this_track']:3d} "
              f"no_track={r['n_mentioned_but_no_track']:4d}  "
              f"top_classes={list(r['function_classes_among_mentions'].items())[:3]}")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
