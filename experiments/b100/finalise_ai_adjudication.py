"""B-100: promote the owner-authorised external AI review to the study's FINAL Target B adjudication.

This is the formal, auditable step the project owner authorised on 2026-11-03 (see
`research/studies/early_signal_5firms/OWNER_AUTHORISATION_2026-11-03.md`):

  * the 69 AI labels become the study's final labels, under a new tier
    `FINAL_ADJUDICATION_AI_OWNER_AUTHORISED`;
  * the human sign-off gate for this study is waived by owner instruction;
  * the labels remain `human_truth = false` and must be reported as AI-adjudicated, not expert adjudication.

The script validates the authorisation and the labels, writes the final adjudication and a merged packet file, and
computes the Target B result that was blocked until now: label distribution, confirmed-shift rate with a Wilson
interval, false-signal structure, and the status of H1-H4.

Outputs (committed):
  research/studies/early_signal_5firms/ADJUDICATION_FINAL_V1.json
  research/studies/early_signal_5firms/CASE_PACKETS_FINAL_V1.json
  research/studies/early_signal_5firms/TARGET_B_RESULTS_V1.md   (rendered from the JSON)

Exit 0 on success, 2 on validation failure (nothing written).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research" / "studies" / "early_signal_5firms"
AI_ADJ = STUDY / "AI_REVIEW_ADJUDICATION_V1.json"
AI_WORKSHEET = STUDY / "external_ai_review_2026-11-03" / "AI_REVIEW_WORKSHEET.csv"
AUTHORISATION = STUDY / "OWNER_AUTHORISATION_2026-11-03.md"
PACKETS = STUDY / "CASE_PACKETS_SMALL_SAMPLE_V2.json"
CANDIDATES = STUDY / "CASE_CANDIDATES.json"
OUT_FINAL = STUDY / "ADJUDICATION_FINAL_V1.json"
OUT_PACKETS = STUDY / "CASE_PACKETS_FINAL_V1.json"
OUT_MD = STUDY / "TARGET_B_RESULTS_V1.md"

LABELS = ("Confirmed Shift", "Routine Iteration", "False Signal / No Confirmed Shift", "Uncertain",
          "Insufficient Observation")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def wilson_upper(successes: int, total: int, z: float = 1.959963984540054) -> float | None:
    """One-sided 95 % Wilson upper bound for a binomial proportion (clamped to [0,1])."""
    if total <= 0:
        return None
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return min(1.0, (centre + margin) / denominator)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ai-adjudication", default=str(AI_ADJ))
    parser.add_argument("--authorisation", default=str(AUTHORISATION))
    parser.add_argument("--packets", default=str(PACKETS))
    parser.add_argument("--candidates", default=str(CANDIDATES))
    parser.add_argument("--out-final", default=str(OUT_FINAL))
    parser.add_argument("--out-packets", default=str(OUT_PACKETS))
    parser.add_argument("--out-md", default=str(OUT_MD))
    parser.add_argument("--out-candidates", default=str(STUDY / "CASE_CANDIDATES_FINAL_V1.json"))
    args = parser.parse_args(argv)

    for required in (Path(args.ai_adjudication), Path(args.authorisation), Path(args.packets),
                     Path(args.candidates)):
        if not required.is_file():
            print(f"missing required input: {required}")
            return 2

    ai = read_json(Path(args.ai_adjudication))
    packets_v2 = read_json(Path(args.packets))
    candidates = read_json(Path(args.candidates))
    authorisation_text = Path(args.authorisation).read_text(encoding="utf-8")
    problems: list[str] = []

    # ---- 1. the authorisation must be explicit and scoped -------------------------
    if "OWNER AUTHORISATION" not in authorisation_text or "2026-11-03" not in authorisation_text:
        problems.append("the owner-authorisation record is missing or undated")
    if "not human" not in authorisation_text.lower():
        problems.append("the authorisation does not restate the non-human evidentiary status")
    if ai.get("tier") != "EXTERNAL_AI_REVIEW" or ai.get("can_count_as_human_truth") is not False:
        problems.append("the AI adjudication is not the non-human tier it claims to be")
    if ai.get("authority") != "AI_ONLY_NOT_HUMAN_GOLD_STANDARD":
        problems.append("unexpected AI adjudication authority")

    # ---- 2. labels must be complete, in vocabulary, and rule-consistent ------------
    rows = ai.get("packets") or []
    if len(rows) != 69:
        problems.append(f"expected 69 packets, found {len(rows)}")
    ids = [row.get("packet_id") for row in rows]
    if len(set(ids)) != len(ids):
        problems.append("duplicate packet ids in the AI adjudication")
    for row in rows:
        label = row.get("ai_label")
        if label not in LABELS:
            problems.append(f"{row.get('packet_id')}: label {label!r} outside the frozen vocabulary")
        if label == "Confirmed Shift":
            problems.append(f"{row.get('packet_id')}: the review reports no Confirmed Shift; a confirmed label "
                            "would need an independent-confirmation field, which does not exist")
        if row.get("final_label") is not None or row.get("human_label") is not None:
            problems.append(f"{row.get('packet_id')}: a human/final label was already present; refusing to overwrite")
    packet_ids = {row.get("event_id") or row.get("packet_id") for row in (packets_v2.get("packets") or [])}
    candidate_ids = {row.get("case_id") or row.get("packet_id") for row in (candidates.get("cases") or [])}
    known = packet_ids | candidate_ids
    if known and not set(ids) <= known:
        problems.append(f"AI labels for unknown packets: {sorted(set(ids) - known)[:5]}")

    if problems:
        print(f"VALIDATION FAILED ({len(problems)} problems); nothing written")
        for problem in problems[:12]:
            print("  -", problem)
        return 2

    # ---- 3. the final adjudication -------------------------------------------------
    distribution = Counter(row["ai_label"] for row in rows)
    by_origin: Counter = Counter()
    by_company: Counter = Counter()
    by_track: Counter = Counter()
    for row in rows:
        by_origin[(row.get("origin") or "", row["ai_label"])] += 1
        by_company[(row.get("company") or "", row["ai_label"])] += 1
        by_track[(row.get("track") or "", row["ai_label"])] += 1
    total = len(rows)
    confirmed = distribution.get("Confirmed Shift", 0)
    confirmed_rate = confirmed / total
    upper_bound = wilson_upper(confirmed, total)
    false_signals = distribution.get("False Signal / No Confirmed Shift", 0)
    small = [row for row in rows if (row.get("origin") or "") == "small_sample"]
    small_false = [row["packet_id"] for row in small
                   if row["ai_label"] == "False Signal / No Confirmed Shift"]

    hypotheses = {
        "H1_fusion": {
            "status": "NOT_EVALUABLE",
            "why": ("H1 needs positive labels to compare fusion recall against the best single source at a fixed "
                    "false-alarm budget; the final adjudication contains no `Confirmed Shift`, so recall is undefined"),
        },
        "H2_lead_time": {
            "status": "NOT_EVALUABLE (and the prior description is withdrawn)",
            "why": ("lead time is measured from an alert to a confirmed milestone; with zero confirmed milestones "
                    "there is no lead time to measure, and the 9-event description was withdrawn in S-034 because "
                    "8/9 pairs are device/project mismatches"),
        },
        "H3_heterogeneity": {
            "status": "DESCRIPTIVE_ONLY",
            "why": ("the label distribution by firm/track is reported, but with zero confirmed shifts there is no "
                    "positive class to compare across firms"),
        },
        "H4_density": {
            "status": "NOT_TESTABLE",
            "why": ("density bounds recall and lead time only if positives exist; there are none in the final set"),
        },
    }
    verdict = {
        "confirmed_shift_count": confirmed,
        "confirmed_shift_rate": confirmed_rate,
        "confirmed_rate_wilson_upper_95": upper_bound,
        "false_signal_count": false_signals,
        "routine_count": distribution.get("Routine Iteration", 0),
        "uncertain_count": distribution.get("Uncertain", 0),
        "small_sample_false_signals": small_false,
        "statement": (
            f"Under the owner-authorised AI adjudication, {confirmed}/{total} candidate packets are `Confirmed Shift` "
            f"({confirmed_rate:.1%}; one-sided 95 % Wilson upper bound {upper_bound:.1%}), {false_signals} are "
            f"`False Signal / No Confirmed Shift`, {distribution.get('Routine Iteration', 0)} are `Routine Iteration` "
            f"and {distribution.get('Uncertain', 0)} are `Uncertain`. The study's Target B is therefore NEGATIVE: the "
            f"candidate-generation design produced no confirmed technology shift in this set, and the exploratory "
            f"fusion/lead-time aims cannot be evaluated. This conclusion is AI-adjudicated and owner-authorised, not "
            f"human gold standard."),
    }

    final = {
        "schema": "early_signal.final_adjudication.v1",
        "tier": "FINAL_ADJUDICATION_AI_OWNER_AUTHORISED",
        "study": "early_signal_5firms",
        "is_final_for_this_study": True,
        "human_truth": False,
        "human_signoff_waived": True,
        "waived_by": "project owner",
        "waived_on": "2026-11-03",
        "authorisation_record": "OWNER_AUTHORISATION_2026-11-03.md",
        "adjudicator": "Codex AI (not a human reviewer)",
        "adjudicator_authority": "AI_ONLY_NOT_HUMAN_GOLD_STANDARD",
        "eligible_for_target_b_scoring": True,
        "eligible_for_scoring_note": ("eligible FOR THIS STUDY ONLY, by owner amendment; remains ineligible as human "
                                      "gold standard and may not be pooled with human-labelled benchmark sets"),
        "reviewed_commit": ai.get("reviewed_commit"),
        "source_hashes": {
            "AI_REVIEW_ADJUDICATION_V1.json": sha256(Path(args.ai_adjudication)),
            "OWNER_AUTHORISATION_2026-11-03.md": sha256(Path(args.authorisation)),
            "CASE_PACKETS_SMALL_SAMPLE_V2.json": sha256(Path(args.packets)),
            "CASE_CANDIDATES.json": sha256(Path(args.candidates)),
        },
        "n_packets": total,
        "label_distribution": dict(sorted(distribution.items())),
        "by_origin": {f"{origin}|{label}": n for (origin, label), n in sorted(by_origin.items())},
        "by_company": {f"{company}|{label}": n for (company, label), n in sorted(by_company.items())},
        "by_track": {f"{track}|{label}": n for (track, label), n in sorted(by_track.items())},
        "hypotheses": hypotheses,
        "target_b_result": verdict,
        "packets": [
            {
                "packet_id": row["packet_id"],
                "company": row.get("company"),
                "track": row.get("track"),
                "origin": row.get("origin"),
                "final_label": row["ai_label"],
                "final_label_source": "AI_REVIEW_2026-11-03",
                "ai_uncertainty": row.get("ai_uncertainty"),
                "ai_reason": row.get("ai_reason"),
                "ai_primary_record": row.get("ai_primary_record"),
                "ai_primary_url": row.get("ai_primary_url"),
                "ai_flags": row.get("ai_flags"),
                "human_label": None,
                "human_truth": False,
            }
            for row in rows
        ],
        "not_claimed": [
            "that these labels are human truth",
            "that the study now has expert adjudication",
            "that the candidate generator has no false positives outside this 69-packet set",
            "that the firms never shift: the labels judge whether these packets' evidence chains support a shift",
        ],
    }

    # ---- 4. merged packet file (additive; V2 is not rewritten) ---------------------
    merged = dict(packets_v2)
    merged["schema"] = packets_v2.get("schema", "") + "+final_adjudication"
    merged["final_adjudication"] = {
        "artifact": "ADJUDICATION_FINAL_V1.json",
        "tier": final["tier"],
        "human_truth": False,
        "owner_authorised": True,
        "n_packets": total,
        "label_distribution": final["label_distribution"],
    }
    labels_by_id = {row["packet_id"]: row["ai_label"] for row in rows}
    merged_packets = []
    for packet in packets_v2.get("packets") or []:
        packet = dict(packet)
        pid = packet.get("packet_id") or packet.get("event_id")
        if pid in labels_by_id:
            packet["final_label"] = labels_by_id[pid]
            packet["final_label_source"] = "AI_REVIEW_2026-11-03"
            packet["final_label_human_truth"] = False
            packet["human_review_status"] = "WAIVED_BY_OWNER_2026-11-03"
        merged_packets.append(packet)
    merged["packets"] = merged_packets
    merged["packets_with_final_label"] = sum(1 for p in merged_packets if p.get("final_label"))

    # the 60-candidate file keeps its own id field (case_id); merge the same final labels additively
    merged_candidates = dict(candidates)
    merged_candidates["schema"] = str(candidates.get("schema", "")) + "+final_adjudication"
    merged_candidates["final_adjudication"] = {
        "artifact": "ADJUDICATION_FINAL_V1.json",
        "tier": final["tier"],
        "human_truth": False,
        "owner_authorised": True,
        "n_packets": total,
        "label_distribution": final["label_distribution"],
    }
    merged_cases = []
    for case in candidates.get("cases") or []:
        case = dict(case)
        cid = case.get("case_id")
        if cid in labels_by_id:
            case["final_label"] = labels_by_id[cid]
            case["final_label_source"] = "AI_REVIEW_2026-11-03"
            case["final_label_human_truth"] = False
            case["human_review_status"] = "WAIVED_BY_OWNER_2026-11-03"
        merged_cases.append(case)
    merged_candidates["cases"] = merged_cases
    merged_candidates["cases_with_final_label"] = sum(1 for c in merged_cases if c.get("final_label"))

    Path(args.out_final).write_text(json.dumps(final, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(args.out_packets).write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(args.out_candidates).write_text(json.dumps(merged_candidates, indent=2, ensure_ascii=False) + "\n",
                                         encoding="utf-8")

    # ---- 5. rendered results -------------------------------------------------------
    lines = [
        "# Target B — final adjudication results (owner-authorised AI adjudication)",
        "",
        "**Status:** final for this study by owner authorisation (2026-11-03). **Human truth: no.** The labels are the",
        "owner-authorised external AI review; they may not be described as expert or human adjudication.",
        "**Artifacts:** `ADJUDICATION_FINAL_V1.json` (labels + provenance), `CASE_PACKETS_FINAL_V1.json` (additive merge;",
        "V2 unchanged). **Reproduce:** `python experiments/b100/finalise_ai_adjudication.py`.",
        "",
        "## Label distribution (69 packets)",
        "",
        "| label | packets |",
        "|---|---:|",
    ]
    for label in LABELS:
        lines.append(f"| `{label}` | {distribution.get(label, 0)} |")
    lines += [
        "",
        f"**Target B result:** {confirmed}/{total} confirmed shifts ({confirmed_rate:.1%}; one-sided 95 % Wilson upper "
        f"bound {upper_bound:.1%}); {false_signals} false signals; "
        f"{distribution.get('Routine Iteration', 0)} routine iterations; {distribution.get('Uncertain', 0)} uncertain.",
        "",
        "## By origin",
        "",
        "| origin | label | packets |",
        "|---|---|---:|",
    ]
    for (origin, label), n in sorted(by_origin.items()):
        lines.append(f"| {origin} | {label} | {n} |")
    lines += ["", "## By firm", "", "| firm | label | packets |", "|---|---|---:|"]
    for (company, label), n in sorted(by_company.items()):
        lines.append(f"| {company} | {label} | {n} |")
    lines += ["", "## Hypotheses", "", "| hypothesis | status | why |", "|---|---|---|"]
    for name, block in hypotheses.items():
        lines.append(f"| {name} | {block['status']} | {block['why']} |")
    lines += [
        "",
        "## What this means",
        "",
        "- The candidate-generation design is **not validated**: it produced 0 confirmed shifts in 69 candidates.",
        "- The nine-event lead-time description stays withdrawn (8/9 pairs are device/project mismatches, S-034).",
        "- H1 (fusion) and H2 (lead time) cannot be evaluated for lack of positives; H3 is descriptive only; H4 is not",
        "  testable. No recall, precision, calibration or lead-time claim is made.",
        "- The study closes as a **negative result about its candidate generator**, not as evidence that the firms do",
        "  not shift.",
        "",
    ]
    Path(args.out_md).write_text("\n".join(lines), encoding="utf-8")

    print(f"wrote {Path(args.out_final).name}, {Path(args.out_packets).name}, {Path(args.out_md).name}, "
          f"{Path(args.out_candidates).name}")
    print("label distribution:", dict(sorted(distribution.items())))
    print(f"confirmed rate: {confirmed}/{total} = {confirmed_rate:.4f}; Wilson-upper95 = {upper_bound:.4f}")
    print("small-sample false signals:", len(small_false), "of", len(small))
    print("merged packets with final label:", merged["packets_with_final_label"],
          "| merged cases with final label:", merged_candidates["cases_with_final_label"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
