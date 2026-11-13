"""Validate the AI evidence-review record for the 69 early-signal packets.

Checks structure, vocabulary, source links, summary readability and — importantly — that the
review never pretends to be human data and that the frozen study material is untouched.

Run from anywhere:  python research/studies/early_signal_5firms/ai_review/verify_ai_review.py
Exit code 0 = all checks pass.
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
REPO = STUDY.parents[2]

RECORD = HERE / "AI_EVIDENCE_REVIEW.jsonl"
WORKSHEET = STUDY / "HUMAN_REVIEW_WORKSHEET.csv"

LABELS = {"Confirmed Shift", "Routine Iteration", "False Signal / No Confirmed Shift",
          "Uncertain", "Insufficient Observation"}
STATUSES = {"AI_ADJUDICATED", "AI_UNRESOLVED"}
AGREEMENTS = {"agree", "disagree_resolved"}
CATEGORIES = {"CONSISTENT_CLEAR", "DIVERGENT", "INSUFFICIENT_SOURCE_OR_TIME",
              "NEEDS_DOMAIN_EXPERT", "CONCLUSION_CRITICAL"}
ARTEFACTS = {"administrative_record_not_product_event", "cross_device_pair",
             "same_device_under_another_code", "entity_resolution"}
FROZEN = [
    "research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv",
    "research/studies/early_signal_5firms/LABELING_PROTOCOL.md",
    "research/studies/early_signal_5firms/ADJUDICATION_AGENT_V1.json",
    "research/studies/early_signal_5firms/STUDY_DECISIONS.md",
    "research/studies/early_signal_5firms/PROTOCOL.md",
]
REQUIRED_TOP = {"packet_id", "origin", "company", "technology_track", "event_date", "packet_claim",
                "review", "evidence", "zh_summary", "limits"}
FORBIDDEN_KEYS = {"human_label", "human_reason", "reviewer", "reviewed_at",
                  "independent_confirmation", "final_label"}
FORBIDDEN_TEXT = ("HUMAN_CONFIRMED", "human-confirmed", "expert-signature")

errors: list[str] = []
warnings: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


def main() -> int:
    if not RECORD.is_file():
        print(f"missing {RECORD}")
        return 1
    rows = [json.loads(line) for line in RECORD.read_text(encoding="utf-8").splitlines() if line.strip()]

    # 1. count and ids
    check(len(rows) == 69, f"expected 69 records, found {len(rows)}")
    ids = [r.get("packet_id") for r in rows]
    check(len(set(ids)) == len(ids), "duplicate packet_id in record")
    with WORKSHEET.open(encoding="utf-8-sig", newline="") as fh:
        ws_ids = [row["packet_id"] for row in csv.DictReader(fh)]
    check(set(ids) == set(ws_ids),
          f"packet ids differ from worksheet: missing={sorted(set(ws_ids) - set(ids))[:5]} "
          f"extra={sorted(set(ids) - set(ws_ids))[:5]}")

    for r in rows:
        pid = r.get("packet_id", "?")
        check(REQUIRED_TOP <= set(r), f"{pid}: missing top-level keys {REQUIRED_TOP - set(r)}")
        check(r.get("origin") in {"candidate", "small_sample"}, f"{pid}: bad origin")
        check(r.get("limits", "").lower().find("not human") >= 0 or "not human" in r.get("limits", ""),
              f"{pid}: limits must state it is not human adjudication")
        rev = r.get("review", {})
        ev = r.get("evidence", {})

        # 2. vocabulary and status semantics
        label = rev.get("label")
        check(label in LABELS, f"{pid}: bad label {label!r}")
        status = rev.get("status")
        check(status in STATUSES, f"{pid}: bad status {status!r}")
        if label in {"Uncertain", "Insufficient Observation"}:
            check(status == "AI_UNRESOLVED", f"{pid}: unresolved label must have AI_UNRESOLVED")
        else:
            check(status == "AI_ADJUDICATED", f"{pid}: decided label must have AI_ADJUDICATED")
        check(rev.get("agreement") in AGREEMENTS, f"{pid}: bad agreement {rev.get('agreement')!r}")
        if rev.get("agreement") == "disagree_resolved":
            check(bool(rev.get("adjudication_note")), f"{pid}: disagreement without adjudication_note")
        check(rev.get("label_authority") == "ai_evidence_review_v1", f"{pid}: wrong label_authority")
        check(rev.get("not_human_truth") is True, f"{pid}: not_human_truth must be true")
        for cat in rev.get("categories") or []:
            check(cat in CATEGORIES, f"{pid}: unknown category {cat!r}")
        for art in rev.get("candidate_artefacts") or []:
            check(art in ARTEFACTS, f"{pid}: unknown artefact {art!r}")
        for role in ("reviewer_a", "reviewer_b"):
            check(role in rev, f"{pid}: missing {role}")
            check(rev.get(role, {}).get("model"), f"{pid}: {role} has no model name")

        # 3. no human data may be present
        flat = json.dumps(r, ensure_ascii=False)
        for key in FORBIDDEN_KEYS:
            check(f'"{key}"' not in flat, f"{pid}: forbidden human field {key!r} present")
        for text in FORBIDDEN_TEXT:
            check(text not in flat, f"{pid}: forbidden human-truth wording {text!r} present")

        # 4. evidence must be real and traceable
        check(bool(ev.get("record_ref")), f"{pid}: no record_ref")
        urls = ev.get("source_urls") or []
        check(len(urls) >= 1, f"{pid}: no source_urls")
        for u in urls:
            check(isinstance(u, str) and re.match(r"^https?://", u), f"{pid}: bad source url {u!r}")
        check(bool(ev.get("sources_searched")), f"{pid}: no sources_searched list")
        check(bool(ev.get("retrieved_at")), f"{pid}: no retrieved_at")
        check("checked against the live" in (ev.get("verification") or ""),
              f"{pid}: verification method not stated")
        check("openFDA" in " ".join(ev.get("sources_searched") or []), f"{pid}: openFDA not in sources")

        # 5. readable Chinese summary, 150-250 characters, four questions
        s = r.get("zh_summary") or ""
        check(150 <= len(s) <= 250, f"{pid}: zh_summary length {len(s)} outside 150-250")
        for marker in ("发生了什么", "为什么算技术变化", "证据是否支持", "还缺什么"):
            check(marker in s, f"{pid}: zh_summary missing {marker}")
        check(re.search(r"[\u4e00-\u9fff]", s) is not None, f"{pid}: zh_summary has no Chinese text")

        # 6. lead-time packets must cite both ends
        if r.get("origin") == "small_sample":
            trial = ev.get("trial") or {}
            check(bool(trial.get("nct")), f"{pid}: small_sample record without a verified trial id")
            check(any("clinicaltrials.gov" in (u or "") for u in urls),
                  f"{pid}: small_sample record without a ClinicalTrials.gov url")

    # 7. frozen material untouched (best effort: needs git and a clean-enough checkout)
    try:
        diff = subprocess.run(["git", "diff", "--name-only", "HEAD", "--", *FROZEN],
                              cwd=REPO, capture_output=True, text=True, timeout=60)
        if diff.returncode == 0:
            changed = [x for x in diff.stdout.splitlines() if x.strip()]
            check(not changed, f"frozen study files were modified: {changed}")
        else:
            warnings.append("git diff unavailable; frozen-file check skipped")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"git check skipped: {type(exc).__name__}")

    # 8. report
    labels: dict[str, int] = {}
    for r in rows:
        labels[r["review"]["label"]] = labels.get(r["review"]["label"], 0) + 1
    print(f"records: {len(rows)}")
    for k in sorted(labels, key=lambda x: -labels[x]):
        print(f"  {k}: {labels[k]}")
    unresolved = sum(1 for r in rows if r["review"]["status"] == "AI_UNRESOLVED")
    divergent = sum(1 for r in rows if r["review"]["agreement"] != "agree")
    print(f"  AI_UNRESOLVED: {unresolved}  |  adjudicated disagreements: {divergent}")
    for w in warnings:
        print(f"WARN {w}")
    if errors:
        print(f"\nFAIL ({len(errors)} problem(s)):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\nOK - all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
