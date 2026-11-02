"""Final state update: record the completion position and close the consolidation task."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-075
    layer: govern
    priority: P0
    title: Final consolidation — reproducibility audit and completion report
    status: done
    owner: lead
    depends_on: [B-037, B-068, B-070, B-073]
    notes: >
      tools/final_audit.py re-runs four deterministic scripts into a temporary directory and compares with the
      committed JSON: 4 of 4 reproduced identically, 10 of 10 verifiers passing. research/COMPLETION_REPORT.md maps
      each objective clause to an artifact and a verification step, and states what remains (prospective maturation
      2026-Q4..2028-Q1, legacy nowcasts 2027-10, one human signature, three access-blocked lanes, one human-adjudicated
      label set) and what is explicitly not claimed. Record at closure: 73 decisions, 152 result rows (27
      negative/null), 6 auditable snapshots, 2 forecast sets, 113 verified claims across two papers, 43 cycle reports,
      157 commits; main untouched at 7a639f7.
"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-04T05:40:00+08:00"
    state["phase"] = "complete_verified"
    state["cycle"] = 44
    state["completion"] = {
        "verified_at": "2026-11-03",
        "branch": "research/change-detection-v1",
        "main_untouched": "7a639f7",
        "audits": {"round_end": "10 steps, 0 failures",
                   "final_audit": "10 of 10 verifiers pass; 4 of 4 artifacts reproduced identically",
                   "objective_audit": "11 PASS / 0 FAIL / 1 N/A of 12",
                   "tests": "913 tests, selftest exit 0"},
        "record": {"decisions": 74, "result_rows": 152, "negative_rows": 27, "snapshots": 6,
                   "forecast_sets": 2, "prospective_forecasts": 25, "claims": 88,
                   "methods_claims": 25, "cycle_reports": 43, "commits_on_branch": 157},
        "deliverables_satisfied": True,
        "remaining_not_rounds": [
            "25 prospective forecasts mature 2026-Q4..2028-Q1",
            "25 legacy registry nowcasts mature 2027-10",
            "one promotion awaits a human signature",
            "patents and broad hiring blocked on external access",
            "B-014 needs a human adjudicator",
        ],
        "not_claimed": [
            "predictive skill over technology (zero matured prospective forecasts)",
            "visibility into intent, capability or internal R&D",
            "generalisability of the density scaling beyond this corpus",
            "submission-readiness of either paper (drafts; rendered figure review outstanding)",
        ],
        "report": "research/COMPLETION_REPORT.md",
        "audit_artifact": "research/FINAL_AUDIT.json",
    }
    state["next_actions"] = [
        "when the lane advances past 2026-Q4, run experiments/b068/maturate_forecasts.py and report Brier/calibration",
        "when a human reviewer is available, sign or reject the pending promotion in research/RESULTS/PROMOTIONS.md",
        "schedule the six scheduled analyses (B-018, B-021, B-029, B-041, cohort re-run) with proven data",
        "run a rendered figure review before any submission",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-075" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-075 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
