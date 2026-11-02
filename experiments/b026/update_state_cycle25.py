"""Update STATE.json and BACKLOG.yaml for cycle 25 (window trade-off)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-058
    layer: detect
    priority: P2
    title: Confirmation-window sensitivity analysis for the ramp class
    status: done
    owner: lead
    depends_on: [B-026, B-055]
    acceptance: >
      Pre-registered window grid (1,2,3,4,6 months), both units, three fresh origins per cell, fixed
      seeds; recommendation rule fixed in advance (ramp recall > 0.40 and precision >= 0.85 on both
      units). Result: no window qualifies; best ramp recall 0.229 with precision falling monotonically.
      Policy stays at two months; the blind spot and the quarterly-only validation are now carried in
      every profile's limits field, with tests.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T12:40:00+08:00"
    state["phase"] = "ramp_limitation_established"
    state["cycle"] = 27
    state["last_completed_cycle"] = {
        "cycle": 25,
        "name": "confirmation_window_sensitivity",
        "branch": "research/change-detection-v1",
        "report": "experiments/b026/window_tradeoff.json",
        "summary": "research/RESULTS/cycle25_window_tradeoff_2026-11-03.md",
        "verdict": ("no confirmation window between 1 and 6 months recovers the ramp class: best ramp "
                    "recall 0.229 and precision falls monotonically; the two-month policy stands and the "
                    "ramp blind spot is now carried in every profile's limits field"),
    }
    state["detection_layer"]["ramp_limitation"] = {
        "artifact": "experiments/b026/window_tradeoff.json",
        "decision": "research/DECISIONS.md D-050 (pre-registration), D-051 (outcome)",
        "windows_months": [1, 2, 3, 4, 6],
        "best_ramp_recall": {"company": 0.229, "entity": 0.128},
        "precision_range": [0.862, 0.937],
        "qualifying_windows": [],
        "metric_trap": ("balanced accuracy is highest at the one-month window because it can never see a "
                        "ramp forming; class-specific recall is the metric that matters"),
        "consequence": ("policy stays at two months; three-way shape classification is recorded as NOT "
                        "AVAILABLE at this counting rate rather than as a tuning problem"),
        "product": "both limits are in limits_and_provenance and asserted by two tests",
    }
    state["established_findings"] = state["established_findings"] + [
        "DETECT: no confirmation window between 1 and 6 months recovers the ramp class (best recall 0.229); "
        "the ramp blind spot is a property of the counting rate, not of the classifier",
        "METHOD: reporting balanced accuracy alone would have recommended the one-month window, the worst "
        "choice for detecting ramps; class-specific recall must be reported with it",
    ]
    state["next_actions"] = [
        "second-domain validation before any portability claim",
        "decide how promoted changes enter the paper's results ledger (a promoted alert is not a finding)",
        "add the window sensitivity analysis to the paper as a further negative-with-diagnosis result",
        "record sign-off identity in the snapshot manifest so a promotion is attributable",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-058" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-058 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
