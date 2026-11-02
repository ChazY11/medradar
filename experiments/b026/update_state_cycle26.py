"""Update STATE.json, BACKLOG.yaml and paper claims for cycle 26 (second-domain validation)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")
CLAIMS = Path("papers/CLAIMS.json")
BUILD = Path("papers/build_claims.py")

TASK = """  - id: B-059
    layer: detect
    priority: P0
    title: Second-domain validation of the promotion rule
    status: done
    owner: lead
    depends_on: [B-054, B-055, B-030]
    acceptance: >
      Domain chosen by measured feasibility (trial lane had 5 eligible cells; hiring lane 8 series), then
      the identical detector, classifier, shapes and 3x elevation applied to archived job-posting series.
      43 scored alerts: balanced accuracy 0.593 (0.503-0.806), sustained precision 0.929 (0.872-1.000) vs
      a 0.794 base rate, interval width 0.128 below the declared underpowered threshold. Verdict:
      CONSISTENT. Not a second confirmation and no portability beyond this one domain.


"""

EXTRA = [
    ("X1", "second-domain balanced accuracy", "0.593", "research/DECISIONS.md", "0.593"),
    ("X2", "second-domain sustained precision", "0.929", "research/DECISIONS.md", "0.929"),
    ("X3", "second-domain sustained base rate", "0.794", "research/DECISIONS.md", "0.794"),
    ("X4", "eligible hiring series in the second domain", "8", "research/DECISIONS.md", "8 of 13"),
]


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T13:40:00+08:00"
    state["phase"] = "second_domain_consistent"
    state["cycle"] = 28
    state["last_completed_cycle"] = {
        "cycle": 26,
        "name": "second_domain_validation",
        "branch": "research/change-detection-v1",
        "report": "experiments/b026/validate_hiring_domain.json",
        "summary": "research/RESULTS/cycle26_second_domain_2026-11-03.md",
        "verdict": ("the promotion rule is CONSISTENT on a second domain (archived job postings): balanced "
                    "accuracy 0.593 (0.503-0.806), sustained precision 0.929 (0.872-1.000) vs a 0.794 base "
                    "rate over 43 alerts. Domain chosen by measured feasibility (trial lane had 5 eligible "
                    "cells). Not a second confirmation; no portability beyond this domain."),
    }
    state["detection_layer"]["second_domain"] = {
        "artifact": "experiments/b026/validate_hiring_domain.json",
        "decision": "research/DECISIONS.md D-052 (pre-registration), D-053 (outcome)",
        "domain": "archived job-posting lane (Internet Archive CDX)",
        "domain_choice_evidence": {"trial_lane_eligible_cells": 5, "hiring_series_eligible": 8},
        "alerts": 43,
        "balanced_accuracy": 0.593, "ci": [0.503, 0.806],
        "sustained_precision": 0.929, "precision_ci": [0.872, 1.0],
        "sustained_base_rate": 0.794, "interval_width": 0.128,
        "verdict": "CONSISTENT",
        "scope": ("transfers once to a different recording process; not a second confirmation, no "
                  "portability beyond this domain, registry error rates remain the policy numbers"),
    }
    state["established_findings"] = state["established_findings"] + [
        "DETECT: the promotion rule is CONSISTENT on a second domain (archived job postings, 43 alerts): "
        "balanced accuracy 0.593, sustained precision 0.929 vs a 0.794 base rate - it is not a property of "
        "the FDA filing corpus alone",
        "DETECT: the second-domain result is not a second confirmation (43 vs 494/1,196 alerts) and grants "
        "no portability beyond that domain; ramp recall there (0.300) rests on ten cases",
        "METHOD: the domain was chosen by measured feasibility - the trial lane was inspected first and "
        "rejected with 5 eligible cells",
    ]
    state["next_actions"] = [
        "add the window analysis and the second-domain result to the paper (negative-with-diagnosis and a "
        "scoped positive)",
        "decide how promoted changes enter the results ledger (a promoted alert is not a finding)",
        "record sign-off identity in the snapshot manifest so a promotion is attributable",
        "consider a third domain only if it has >=15 eligible series at these floors",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-059" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-059 appended")

    payload = json.loads(CLAIMS.read_text(encoding="utf-8"))
    by_id = {claim["id"]: claim for claim in payload["claims"]}
    for claim_id, statement, value, source, needle in EXTRA:
        by_id[claim_id] = {"id": claim_id, "statement": statement, "value": value,
                           "source": source, "source_needle": needle}
    payload["claims"] = [by_id[key] for key in sorted(by_id)]
    CLAIMS.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8", newline="\n")

    build_text = BUILD.read_text(encoding="utf-8")
    if '"X1"' not in build_text:
        block = "\n".join(
            f'    ("{claim_id}", "{statement}", "{value}", "{source}", "{needle}"),'
            for claim_id, statement, value, source, needle in EXTRA)
        anchor = [line for line in build_text.splitlines() if '"W5"' in line][0]
        build_text = build_text.replace(
            anchor, anchor + "\n    # ---- second-domain validation (cycle 26)\n" + block, 1)
        BUILD.write_text(build_text, encoding="utf-8", newline="\n")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"],
          "claims:", len(payload["claims"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
