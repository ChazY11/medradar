"""Update research/STATE.json and BACKLOG.yaml for cycle 15 (rolling-origin benchmark)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-050
    layer: evaluate
    priority: P1
    title: Rolling-origin benchmark of the change signal
    status: done
    owner: lead
    depends_on: [B-027]
    acceptance: >
      First rolling-origin benchmark: 376 (company, track) cells, 12 origins (2019-12..2025-06), 717
      observations, signal uses only data up to each origin, outcome is the next 12 months,
      company-clustered bootstrap. Pre-registered in D-035, outcome and the design flaw in D-036.
      Result: no predictor's 95% interval excludes 1 against the long-run baseline; the naive
      increase point estimate is 1.22 [0.95, 1.53]; calibrated flags are too rare (5/717) to predict
      with at ~0.2 events per cell-month.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T02:40:00+08:00"
    state["phase"] = "rolling_origin_benchmark_v1"
    state["cycle"] = 17
    state["last_completed_cycle"] = {
        "cycle": 15,
        "name": "rolling_origin_benchmark",
        "branch": "research/change-detection-v1",
        "report": "experiments/b050/rolling_origin.json",
        "summary": "research/RESULTS/cycle15_rolling_origin_2026-11-03.md",
        "verdict": ("first rolling-origin benchmark (376 cells, 12 origins, 717 observations): NO "
                    "predictor's 95% interval excludes 1 against the long-run baseline. The "
                    "pre-registered outcome was biased toward regression to the mean; corrected, the "
                    "naive increase lift flips from 0.49 to 1.22 [0.95,1.53]. Calibrated flags are too "
                    "rare (5/717) to predict with."),
    }
    state["rolling_origin"] = {
        "status": "FIRST BENCHMARK SHIPPED - honest null",
        "design": "research/DECISIONS.md D-035 (pre-registered), D-036 (outcome + design flaw)",
        "artifact": "experiments/b050/rolling_origin.json",
        "scale": {"cells": 376, "origins": 12, "observations": 717,
                  "origin_range": "2019-12..2025-06", "bootstrap": "company-clustered, 2000 reps"},
        "pre_registered_result": {
            "design_flaw": ("outcome compared with the same recent block that triggered the flag; "
                            "regression to the mean is built into the numerator"),
            "naive_increase_lift": 0.486, "naive_increase_ci": [0.32, 0.66],
            "persistence_increase_lift": 0.456, "ci": [0.31, 0.61],
        },
        "corrected_result": {
            "baseline": "cell long-run rate up to the origin x 12 months",
            "naive_increase_lift": 1.222, "naive_increase_ci": [0.95, 1.53],
            "persistence_increase_lift": 1.200, "ci": [0.94, 1.49],
            "calibrated_increase_lift": 0.598, "ci": [0.0, 2.08], "flags": 5,
            "calibrated_decrease_lift": 1.351, "ci": [0.90, 1.57], "flags": 16,
            "verdict": "no predictor's interval excludes 1",
        },
        "reading": ("no evidence that a change signal predicts 12-month-ahead filing activity above the "
                    "cell's long-run rate; the calibrated signal is too sparse (5/717) to trigger on at "
                    "~0.2 events per cell-month"),
        "not_claimed": ("not evidence that corporate technological evolution is unpredictable - the "
                        "observation is about public filing rates and the data cannot see far enough"),
    }
    state["design_lessons"] = state.get("design_lessons", []) + [
        "a benchmark outcome must not be defined relative to the same window that triggered the signal "
        "(fourth self-caught design flaw; first caught inside a benchmark)",
    ]
    state["established_findings"] = state["established_findings"] + [
        "EVALUATE: the first rolling-origin benchmark finds no 12-month-ahead predictability above the "
        "long-run baseline for any predictor (all 95% intervals include 1)",
        "EVALUATE: the naive-increase point estimate is 1.22 [0.95, 1.53] after correcting the "
        "regression-to-the-mean bias that made the pre-registered lift look like anti-prediction",
        "EVALUATE: the calibrated change signal is too rare to be a prediction trigger (5 flags in 717 "
        "observations) at this lane's resolution",
    ]
    state["next_actions"] = [
        "freeze a second profile snapshot at the next as-of date and diff it (first point-in-time "
        "comparison)",
        "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
        "B-026: spike vs sustained level-shift classifier - the one remaining P1 model task that can "
        "improve alert precision without needing new data",
        "do not resume hiring probing (D-031); patents only if a route opens",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-050" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-050 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
