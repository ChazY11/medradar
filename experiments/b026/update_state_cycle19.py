"""Update STATE.json and BACKLOG.yaml for cycle 19 (spike vs sustained classifier)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

CONFIRM = """  - id: B-054
    layer: detect
    priority: P1
    title: Confirm the corrected confirmation window on fresh injections
    status: todo
    owner: lead
    depends_on: [B-026]
    acceptance: >
      The post-hoc window fix (exclude the alert month) lifted balanced accuracy from 0.394 to 0.608
      and sustained-change precision from 0.764 to 0.940 against a 0.728 base rate. Because it was
      found after seeing the pre-registered rule fail, re-pre-register it and confirm on injections
      with fresh origins and cells (no reuse), reporting the same estimands. If it does not confirm,
      the promotion rule stays at the pre-registered accuracy and the fix is recorded as overfit.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T06:40:00+08:00"
    state["phase"] = "detection_shape_classification"
    state["cycle"] = 21
    state["last_completed_cycle"] = {
        "cycle": 19,
        "name": "spike_vs_sustained_classification",
        "branch": "research/change-detection-v1",
        "report": "experiments/b026/spike_vs_shift.json",
        "summary": "research/RESULTS/cycle19_spike_shift_2026-11-03.md",
        "verdict": ("pre-registered shape classifier FAILED by its own criterion (balanced accuracy "
                    "0.394 vs 0.333 chance; sustained precision 0.764 vs 0.728 base rate). The failure "
                    "was the rule's window: excluding the alert month lifts balanced accuracy to 0.608 "
                    "and sustained precision to 0.940, but that is POST-HOC and must be confirmed on "
                    "fresh injections (B-054). Three-way ramp/level separation does not work (0.17)."),
    }
    state["detection_layer"] = {
        "status": "alert shape classification: pre-registered failure, post-hoc improvement pending "
                  "confirmation",
        "artifact": "experiments/b026/spike_vs_shift.json",
        "design": "research/DECISIONS.md D-040 (pre-registered), D-041 (outcome)",
        "scale": {"cells": 329, "eligible": 65, "injections": 171, "alerts": 151},
        "pre_registered": {"balanced_accuracy": 0.394, "ci": [0.361, 0.438],
                           "sustained_precision": 0.764, "sustained_precision_ci": [0.727, 0.811],
                           "sustained_base_rate": 0.728, "spike_recall": 0.171, "ramp_recall": 0.151},
        "posthoc_window_fix": {"balanced_accuracy": 0.608, "ci": [0.552, 0.659],
                               "sustained_precision": 0.940, "sustained_precision_ci": [0.903, 0.978],
                               "spike_recall": 0.829, "ramp_recall": 0.170,
                               "status": "POST-HOC, not confirmed"},
        "reading": ("binary spike-vs-sustained promotion becomes useful (0.94 precision vs 0.73 base "
                    "rate) once the pulse is excluded from the confirmation window; ramp-vs-level is "
                    "not recoverable at this counting rate"),
        "not_claimed": "shape recovery is a property of the time series, never of the technology",
    }
    state["established_findings"] = state["established_findings"] + [
        "DETECT: the pre-registered alert-shape classifier fails (balanced accuracy 0.394 vs 0.333 "
        "chance; sustained precision 0.764 vs 0.728 base rate) because its window contains the pulse",
        "DETECT: excluding the alert month from the confirmation window raises balanced accuracy to "
        "0.608 and sustained-change precision to 0.940 - a POST-HOC result awaiting confirmation (B-054)",
        "DETECT: ramp-versus-level separation is not recoverable from a two-month window (ramp recall "
        "0.17) at ~0.2 events per cell-month",
    ]
    state["next_actions"] = [
        "B-054: confirm the corrected confirmation window on fresh injections (pre-register, no reuse)",
        "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
        "B-026 follow-up: consider a longer confirmation window and report the precision/recall "
        "trade-off explicitly if the ramp class stays unrecoverable",
        "add the shape classifier to the paper as a further negative-with-diagnosis result",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    replacements = [("""  - id: B-026
    layer: detect""", """  - id: B-026
    layer: detect""")]
    # mark B-026 done
    if "id: B-026" in text:
        marker = "  - id: B-026"
        start = text.index(marker)
        end = text.index("  - id:", start + len(marker))
        block = text[start:end]
        if "status: todo" in block:
            text = text.replace(block, block.replace("status: todo", "status: done", 1), 1)
    if "id: B-054" not in text:
        text = text.rstrip("\n") + "\n\n" + CONFIRM
        print("B-054 appended")
    BACKLOG.write_text(text, encoding="utf-8", newline="\n")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
