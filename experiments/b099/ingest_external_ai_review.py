"""B-099: ingest the external AI review of the 69 five-firm packets as a NON-HUMAN tier.

The project owner commissioned an independent AI review (Codex/chat-GPT-driven, delivered 2026-11-03) of the 69
adjudication packets that had been blocked on a named human reviewer.  The review's own header states that it is
"AI advice only, not a human gold standard, and may not be used to score detectors".  This script therefore does NOT
write human labels and does NOT produce a Target B ground truth.  It:

  1. validates the delivered worksheet and its machine-readable twin against the frozen 69-packet worksheet;
  2. re-asserts that no human field is filled anywhere (the human boundary is preserved);
  3. registers the review under a new explicit tier, EXTERNAL_AI_REVIEW, with `can_count_as_human_truth: false`;
  4. computes the label distribution, the descriptive agreement with the earlier agent pre-adjudication, and the
     counts that matter for the study's own decision rules (false signals among the 9 small-sample pairs,
     left-censored gap=None entries, manufacturing-notice candidates, prior-record evidence);
  5. applies the pre-registered halt rule: fewer than 10 `Confirmed Shift` labels across the confirmatory tracks
     means the study narrows to a descriptive design and Target B remains unlabelled.

Output: research/studies/early_signal_5firms/AI_REVIEW_ADJUDICATION_V1.json
Exit 0 on success; 2 on any validation failure (no output file is written on failure).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research" / "studies" / "early_signal_5firms"
REVIEW = STUDY / "external_ai_review_2026-11-03"
WORKSHEET = REVIEW / "AI_REVIEW_WORKSHEET.csv"
REVIEW_JSON = REVIEW / "AI_REVIEW_69.json"
HUMAN_WORKSHEET = STUDY / "HUMAN_REVIEW_WORKSHEET.csv"
AGENT = STUDY / "ADJUDICATION_AGENT_V1.json"
OUT = STUDY / "AI_REVIEW_ADJUDICATION_V1.json"

REVIEWED_COMMIT = "969fd0cc4fea040cbdb7a518f3c300b9122980b5"
HUMAN_FIELDS = ("human_label", "human_reason", "independent_confirmation", "reviewer", "reviewed_at")
ALLOWED_AI_LABELS = ("Confirmed Shift", "Routine Iteration", "False Signal / No Confirmed Shift", "Uncertain",
                     "Insufficient Observation")
HALT_RULE_CONFIRMED_FLOOR = 10


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    import csv

    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def cohen_kappa(pairs: list[tuple[str, str]]) -> dict:
    """Descriptive Cohen's kappa for two labellings (no inferential claim)."""
    n = len(pairs)
    if not n:
        return {"n": 0, "observed_agreement": None, "expected_agreement": None, "kappa": None}
    agree = sum(1 for a, b in pairs if a == b) / n
    counts_a = Counter(a for a, _ in pairs)
    counts_b = Counter(b for _, b in pairs)
    expected = sum((counts_a[k] / n) * (counts_b[k] / n) for k in set(counts_a) | set(counts_b))
    kappa = None if expected >= 1.0 else (agree - expected) / (1.0 - expected)
    return {"n": n, "observed_agreement": agree, "expected_agreement": expected, "kappa": kappa}


def collapse_ai(label: str) -> str:
    if label == "Confirmed Shift":
        return "confirmed"
    if label == "Routine Iteration":
        return "routine"
    return "other"


def collapse_agent(label: str) -> str:
    text = (label or "").lower()
    if "confirmed" in text:
        return "confirmed"
    if "routine" in text:
        return "routine"
    return "other"


def flags_of(row: dict) -> set[str]:
    raw = (row.get("ai_flags") or "").strip()
    return {part.strip() for part in raw.split(";") if part.strip()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worksheet", default=str(WORKSHEET))
    parser.add_argument("--review-json", default=str(REVIEW_JSON))
    parser.add_argument("--human-worksheet", default=str(HUMAN_WORKSHEET))
    parser.add_argument("--agent", default=str(AGENT))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    worksheet_path = Path(args.worksheet)
    review_path = Path(args.review_json)
    human_path = Path(args.human_worksheet)
    agent_path = Path(args.agent)
    out_path = Path(args.out)

    problems: list[str] = []
    if not worksheet_path.is_file():
        print(f"missing {worksheet_path}")
        return 2
    if not review_path.is_file():
        print(f"missing {review_path}")
        return 2

    worksheet = read_csv(worksheet_path)
    review = read_json(review_path)
    human = read_csv(human_path)
    agent = read_json(agent_path)

    # ---- 1. structural validation -------------------------------------------------
    if len(worksheet) != 69:
        problems.append(f"worksheet has {len(worksheet)} rows, expected 69")
    ids = [row.get("packet_id", "") for row in worksheet]
    if len(set(ids)) != len(ids):
        problems.append("duplicate packet_id in the review worksheet")
    human_ids = {row.get("packet_id", "") for row in human}
    if set(ids) != human_ids:
        problems.append(f"review ids differ from the frozen worksheet: {sorted(set(ids) ^ human_ids)[:6]}")
    for field in HUMAN_FIELDS:
        filled = [row.get("packet_id") for row in worksheet if (row.get(field) or "").strip()]
        if filled:
            problems.append(f"human field {field} is non-empty on {len(filled)} rows; the human boundary is violated")
    for row in worksheet:
        label = (row.get("ai_label") or "").strip()
        if label not in ALLOWED_AI_LABELS:
            problems.append(f"{row.get('packet_id')}: ai_label {label!r} is outside the frozen vocabulary")
        if (row.get("ai_eligible_for_target_b_scoring") or "").strip().lower() != "false":
            problems.append(f"{row.get('packet_id')}: ai_eligible_for_target_b_scoring is not false")
        if (row.get("ai_source_commit") or "").strip() != REVIEWED_COMMIT:
            problems.append(f"{row.get('packet_id')}: ai_source_commit differs from {REVIEWED_COMMIT}")
        if "human" not in (row.get("ai_reviewer") or "").lower():
            problems.append(f"{row.get('packet_id')}: ai_reviewer does not identify a non-human reviewer")

    if review.get("authority") != "AI_ONLY_NOT_HUMAN_GOLD_STANDARD":
        problems.append(f"review json authority is {review.get('authority')!r}")
    if review.get("may_score_detectors") is not False:
        problems.append("review json does not forbid detector scoring")
    if review.get("blind_review") is not False:
        problems.append("review json claims a blind review; the disclosure says it is not blind")
    json_rows = review.get("rows") or []
    if len(json_rows) != 69:
        problems.append(f"review json has {len(json_rows)} rows, expected 69")
    json_labels = {row.get("packet_id"): row.get("ai_label") for row in json_rows}
    for row in worksheet:
        if json_labels.get(row.get("packet_id")) != (row.get("ai_label") or "").strip():
            problems.append(f"{row.get('packet_id')}: csv and json labels disagree")

    if problems:
        print(f"VALIDATION FAILED ({len(problems)} problems); nothing written")
        for problem in problems[:12]:
            print("  -", problem)
        return 2

    # ---- 2. descriptive statistics ------------------------------------------------
    labels = Counter((row.get("ai_label") or "").strip() for row in worksheet)
    uncertainty = Counter((row.get("ai_uncertainty") or "").strip() for row in worksheet)
    by_origin = Counter()
    for row in worksheet:
        by_origin[((row.get("origin") or "").strip(), (row.get("ai_label") or "").strip())] += 1
    by_company = Counter()
    for row in worksheet:
        by_company[((row.get("company") or "").strip(), (row.get("ai_label") or "").strip())] += 1
    by_track = Counter()
    for row in worksheet:
        by_track[((row.get("technology_track") or "").strip(), (row.get("ai_label") or "").strip())] += 1

    flag_counts = Counter()
    for row in worksheet:
        for flag in flags_of(row):
            flag_counts[flag] += 1
    left_censored = sorted(row["packet_id"] for row in worksheet if "LEFT_CENSORED_GAP_NONE" in flags_of(row))
    manufacturing = sorted(row["packet_id"] for row in worksheet
                           if "MANUFACTURING_NOTICE_NOT_NEW_PRODUCT" in flags_of(row))
    lt_rows = [row for row in worksheet if (row.get("origin") or "").strip() == "small_sample"]
    lt_false = sorted(row["packet_id"] for row in lt_rows
                      if (row.get("ai_label") or "").strip() == "False Signal / No Confirmed Shift")
    lt_uncertain = sorted(row["packet_id"] for row in lt_rows
                          if (row.get("ai_label") or "").strip() == "Uncertain")
    prior_evidence = sorted(row["packet_id"] for row in json_rows if row.get("ai_prior_same_applicant_code"))
    changed_vs_agent = sum(1 for row in json_rows if row.get("ai_changed_from_previous_rubric") is True)

    # ---- 3. agreement with the earlier agent pre-adjudication (descriptive) -------
    agent_labels = {row.get("packet_id"): (row.get("agent_preliminary_label") or "") for row in agent.get("rows", [])}
    pairs = []
    for row in worksheet:
        pairs.append((collapse_agent(agent_labels.get(row["packet_id"], "")),
                      collapse_ai((row.get("ai_label") or "").strip())))
    agreement = cohen_kappa(pairs)
    agreement.update({
        "classes": {"confirmed": "Confirmed Shift", "routine": "Routine Iteration",
                    "other": "Uncertain / False Signal / Not Assessable"},
        "note": ("descriptive only: the external reviewer had read the earlier agent labels "
                 "(blind_review=false in its own disclosure), so this is not an independent agreement estimate "
                 "and it may not be used to score any detector"),
    })

    # ---- 4. the study's own decision rules ---------------------------------------
    confirmed = labels.get("Confirmed Shift", 0)
    halt_triggered = confirmed < HALT_RULE_CONFIRMED_FLOOR
    decision = {
        "halt_rule": {
            "criterion": (f"fewer than {HALT_RULE_CONFIRMED_FLOOR} `Confirmed Shift` labels across the confirmatory "
                          "tracks -> narrow the study to a descriptive design"),
            "confirmed_shift_labels": confirmed,
            "triggered": halt_triggered,
            "consequence": ("the study is narrowed to a descriptive design; Target B has no labels and no Target B "
                            "analysis may be reported; the human-review requirement remains open"
                            if halt_triggered else
                            "Target B could be analysed, but only after a named human reviewer signs the labels"),
        },
        "small_sample_lead_time": {
            "pairs": len(lt_rows),
            "false_signal_pairs": lt_false,
            "uncertain_pairs": lt_uncertain,
            "consequence": ("8 of the 9 small-sample pairs are device/project mismatches under the external review "
                            "(and the ninth is Uncertain): the 9-event median lead of 3.3 quarters is withdrawn as a "
                            "lead-time estimate. It was already labelled 'descriptive only, below the floor of 10'; "
                            "it must not be quoted as a finding at all."
                            if len(lt_false) >= 8 else
                            "the small-sample lead-time description remains descriptive only"),
        },
        "novel_entry_left_censoring": {
            "packets_flagged": left_censored,
            "count": len(left_censored),
            "consequence": ("these packets are first observations inside the study window, not demonstrated first "
                            "entries (gap=None), so they cannot be used as novel-entry labels without a left-censoring "
                            "correction"),
        },
        "manufacturing_notices": {
            "packets_flagged": manufacturing,
            "count": len(manufacturing),
            "consequence": ("a manufacturing/QC supplement is not a product-platform event and cannot be evidence of a "
                            "technology shift"),
        },
        "prior_record_evidence": {
            "packets_with_prior_same_applicant_code": len(prior_evidence),
            "note": ("the reviewer searched the current store for earlier records by the same applicant and product "
                     "code; these are evidence against treating an in-window first observation as a first entry, but "
                     "they are current-store lookups, not historical snapshots"),
        },
    }

    payload = {
        "schema": "early_signal.ai_review_adjudication.v1",
        "tier": "EXTERNAL_AI_REVIEW",
        "authority": "AI_ONLY_NOT_HUMAN_GOLD_STANDARD",
        "can_count_as_human_truth": False,
        "eligible_for_target_b_scoring": False,
        "human_boundary_preserved": True,
        "human_fields_filled": 0,
        "acceptance_rule": ("registered as a documented non-human tier; the study's Target B remains unlabelled and "
                            "the pre-registered human-adjudication requirement is not discharged"),
        "reviewed_commit": REVIEWED_COMMIT,
        "generated_at_utc": "2026-11-03T00:00:00+00:00",
        "source_hashes": {
            "AI_REVIEW_WORKSHEET.csv": sha256(worksheet_path),
            "AI_REVIEW_69.json": sha256(review_path),
            "HUMAN_REVIEW_WORKSHEET.csv": sha256(human_path),
            "ADJUDICATION_AGENT_V1.json": sha256(agent_path),
        },
        "external_sources_note": ("the reviewer's PDF/HTML evidence bundle (59 MB) is pinned by "
                                  "external_ai_review_2026-11-03/SHA256SUMS.txt and is not committed; every record "
                                  "also carries its public FDA/CT.gov URL"),
        "validation": {"passed": True, "rows": len(worksheet), "unique_ids": len(set(ids)),
                       "ids_match_frozen_worksheet": True, "csv_json_labels_agree": True,
                       "blind_review": False, "reviewer": "Codex AI (not a human reviewer)"},
        "label_distribution": dict(sorted(labels.items())),
        "uncertainty_distribution": dict(sorted(uncertainty.items())),
        "by_origin": {f"{origin}|{label}": n for (origin, label), n in sorted(by_origin.items())},
        "by_company": {f"{company}|{label}": n for (company, label), n in sorted(by_company.items())},
        "by_track": {f"{track}|{label}": n for (track, label), n in sorted(by_track.items())},
        "flag_counts": dict(sorted(flag_counts.items())),
        "changed_vs_earlier_agent_rubric": changed_vs_agent,
        "agreement_with_agent_pre_adjudication": agreement,
        "decision": decision,
        "packets": [
            {
                "packet_id": row.get("packet_id"),
                "company": row.get("company"),
                "track": row.get("technology_track"),
                "origin": row.get("origin"),
                "ai_label": (row.get("ai_label") or "").strip(),
                "ai_uncertainty": row.get("ai_uncertainty"),
                "ai_reason": row.get("ai_reason"),
                "ai_primary_record": row.get("ai_primary_record"),
                "ai_primary_url": row.get("ai_primary_url"),
                "ai_flags": row.get("ai_flags"),
                "ai_human_question": row.get("ai_human_question"),
                "evidence_locator": row.get("ai_evidence_locator"),
                "human_label": None,
                "final_label": None,
                "human_review_status": "PENDING_HUMAN_REVIEW",
            }
            for row in worksheet
        ],
        "not_claimed": [
            "that these labels are human truth; they are not",
            "any Target B metric, calibration or detector score",
            "that the external review is independent: it read the earlier labels (blind_review=false)",
            "that the 69 packets are five-firm comparable: 0 Dräger packets exist (Philips 23, Medtronic 21, GE 16, Mindray 9)",
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    print("labels:", payload["label_distribution"])
    print("halt rule triggered:", halt_triggered, "| confirmed =", confirmed)
    print("small-sample false signals:", len(lt_false), "of", len(lt_rows))
    print("left-censored novel-entry packets:", len(left_censored),
          "| manufacturing notices:", len(manufacturing),
          "| packets with prior same-applicant-code records:", len(prior_evidence))
    print("agreement with agent pre-adjudication (descriptive):",
          f"observed {agreement['observed_agreement']:.3f}, kappa {agreement['kappa']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
