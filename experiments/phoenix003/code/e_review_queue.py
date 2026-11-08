"""E — build the human-review queue.

The machine tiers are *verifiable*, not *authoritative*: L2 proves that the same firm published
a record containing the exact distinctive product-name token before the milestone, and it proves
nothing about whether the record is about the same technology. This script emits a deterministic,
decision-ready CSV so a human can adjudicate the links, and it states the machine verdict next to
an empty human column — the human column is never filled by a model.

Ordering is frozen: (1) product-specific AND pre-regulatory, (2) product-specific, (3)
pre-regulatory, (4) everything else; then by descending lead time, then anchor id. The first
``--limit`` rows form the review batch, so the queue is reproducible.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phoenix003_common as pc

COLUMNS = [
    "queue_rank",
    "anchor_id",
    "firm",
    "stratum",
    "product_code",
    "milestone_key",
    "milestone_name",
    "milestone_date",
    "evidence_source",
    "evidence_id",
    "evidence_date",
    "lead_days",
    "matched_token",
    "token_applicant_df",
    "product_specific",
    "regulatory_status",
    "tier",
    "evidence_title",
    "evidence_journal",
    "evidence_permalink_id",
    "anchor_evidence_url",
    # ---- human columns: leave empty, a human fills them
    "human_decision",
    "human_same_technology_0_1",
    "human_public_before_milestone_0_1",
    "human_identifiable_without_outcome_0_1",
    "human_note",
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args(argv)

    rows = [json.loads(line) for line in
            open(pc.EXPERIMENT_DIR / "EVIDENCE_LINKS.jsonl", encoding="utf-8")]
    anchors = {json.loads(line)["anchor_id"]: json.loads(line)
               for line in open(pc.EXPERIMENT_DIR / "REGULATORY_ANCHORS.jsonl", encoding="utf-8")}

    def bucket(r):
        if r["tier"] not in ("VERIFIED_L1", "VERIFIED_L2"):
            return 9
        spec = bool(r.get("product_specific"))
        pre = r.get("regulatory_status") == "PRE_REGULATORY"
        if spec and pre:
            return 0
        if spec:
            return 1
        if pre:
            return 2
        return 3

    cand = [r for r in rows if r["tier"] in ("VERIFIED_L1", "VERIFIED_L2")]
    cand.sort(key=lambda r: (bucket(r), -(r.get("lead_days") or 0), r["anchor_id"],
                             r["evidence_date"] or ""))
    # one row per anchor in the top buckets so a reviewer sees distinct products first
    seen_anchor, queue = set(), []
    for r in cand:
        b = bucket(r)
        if b <= 2 and r["anchor_id"] in seen_anchor:
            continue
        seen_anchor.add(r["anchor_id"])
        queue.append(r)
    queue = queue[: args.limit]

    out = pc.EXPERIMENT_DIR / "HUMAN_REVIEW_QUEUE.csv"
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for i, r in enumerate(queue, 1):
            a = anchors.get(r["anchor_id"], {})
            w.writerow({
                "queue_rank": i,
                "anchor_id": r["anchor_id"],
                "firm": r["firm"],
                "stratum": r["stratum"],
                "product_code": r["product_code"],
                "milestone_key": r["milestone_key"],
                "milestone_name": r["milestone_name"],
                "milestone_date": r["anchor_date"],
                "evidence_source": r["evidence_source"],
                "evidence_id": r["evidence_id"],
                "evidence_date": r["evidence_date"],
                "lead_days": r["lead_days"],
                "matched_token": r["matched_token"],
                "token_applicant_df": r.get("token_applicant_df"),
                "product_specific": r.get("product_specific"),
                "regulatory_status": r.get("regulatory_status"),
                "tier": r["tier"],
                "evidence_title": (r.get("evidence_title") or "")[:300],
                "evidence_journal": r.get("evidence_journal") or "",
                "evidence_permalink_id": r.get("evidence_url_id") or "",
                "anchor_evidence_url": a.get("url") or "",
                "human_decision": "",
                "human_same_technology_0_1": "",
                "human_public_before_milestone_0_1": "",
                "human_identifiable_without_outcome_0_1": "",
                "human_note": "",
            })

    # a companion markdown sheet so the queue is readable without a spreadsheet
    md = pc.EXPERIMENT_DIR / "HUMAN_REVIEW_QUEUE.md"
    lines = [
        "# PHOENIX-003 human review queue",
        "",
        f"{len(queue)} links, ordered by the frozen buckets "
        "(1) product-specific AND pre-regulatory, (2) product-specific, (3) pre-regulatory, "
        "(4) other verified links; then descending lead time.",
        "",
        "The three questions a reviewer must answer are the three the study asks:",
        "1. is this really the same technology or product?",
        "2. was the evidence publicly available before the milestone?",
        "3. without knowing the later regulatory outcome, could an observer have identified "
        "this candidate from what was already public?",
        "",
        "No model fills the `human_*` columns.",
        "",
        "| # | firm | milestone (date) | token | df | regime | lead d | evidence |",
        "|---:|---|---|---|---:|---|---:|---|",
    ]
    for i, r in enumerate(queue, 1):
        lines.append(
            f"| {i} | {r['firm']} | {r['milestone_name'][:48]} ({r['anchor_date']}) | "
            f"`{r['matched_token']}` | {r.get('token_applicant_df')} | "
            f"{r.get('regulatory_status')} | {r['lead_days']} | "
            f"{r['evidence_source']}:{r['evidence_id']} — {(r.get('evidence_title') or '')[:70]} |")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"wrote {out} ({len(queue)} rows) and {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
