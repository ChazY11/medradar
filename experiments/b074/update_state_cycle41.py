"""Update STATE and BACKLOG for cycle 41 (seasonality quantified; FAR stated as an upper bound)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-037
    layer: observe
    priority: P1
    title: Seasonal and lane-volume artifact adjustment
    status: done
    owner: lead
    depends_on: [B-073]
    notes: >
      Month-of-year effects quantified on the frozen lane (329 cells, 3,928 events, 119 months): January and February
      factor 0.891 against a 1.255x annual spread, permutation p = 0.0005 with 0 of 2,000 shuffles reaching the
      observed dispersion; quarter-boundary months run at 1.058x and 1.054x the interior mean. Per-cell scaling
      cannot remove the effect: it changes 9 of 39,151 cell-months because the lane is 91.8 % zeros, so the detector's
      alert rate is identical on raw and adjusted counts (0.0090, 89 of 9,870). The measured false-alarm rate 0.0179 is
      therefore reported as an upper bound this correction cannot reduce. No detector change.
"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-04T04:40:00+08:00"
    state["phase"] = "seasonality_quantified"
    state["cycle"] = 43
    state["last_completed_cycle"] = {
        "cycle": 41,
        "name": "seasonality",
        "branch": "research/change-detection-v1",
        "report": "experiments/b074/seasonality.json",
        "summary": "research/RESULTS/cycle41_seasonality_2026-11-03.md",
        "verdict": ("month-of-year effects are real and quantified (Jan/Feb 0.891, 1.255x spread, permutation "
                    "p = 0.0005) but per-cell scaling cannot remove them (9 of 39,151 cell-months change, 91.8 % zeros), "
                    "so the alert rate is identical raw vs adjusted (0.0090) and the 0.0179 false-alarm rate is stated "
                    "as an upper bound; no detector change"),
    }
    state["detection_layer"]["seasonality"] = {
        "artifact": "experiments/b074/seasonality.json",
        "decision": "research/DECISIONS.md D-072 (pre-registration), D-073 (outcome)",
        "month_factors": {"january": 0.891, "february": 0.891, "march": 1.118, "spread_max_over_min": 1.255},
        "permutation": {"p_value": 0.0005, "permutations": 2000, "exceedances": 0},
        "boundary": {"quarter_start": 1.058, "quarter_end": 1.054},
        "adjustment_effect": {"cell_months_changed": 9, "cell_months_total": 39151,
                              "zero_share": 0.918},
        "alert_rate": {"raw": 0.0090, "adjusted": 0.0090, "opportunities": 9870, "alerts": 89},
        "verdict": "alert rate is an upper bound; the correction cannot reduce it",
        "no_detector_change": True,
    }
    state["established_findings"] = state["established_findings"] + [
        "DETECT: calendar month explains a real share of lane volume (Jan/Feb factor 0.891, annual spread 1.255x, "
        "permutation p = 0.0005) and quarter-boundary months run 1.058x/1.054x the interior mean",
        "DETECT: per-cell deseasonalisation is inapplicable at this density - it changes 9 of 39,151 cell-months "
        "(91.8 % zeros), so the measured false-alarm rate 0.0179 is an upper bound the correction cannot reduce",
    ]
    state["next_actions"] = [
        "final consolidation: verify the whole record and state the completion position",
        "mature the prospective forecast set when the lane advances (earliest 2026-Q4)",
        "keep tools/round_end.py as the gate at the end of every round",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    start = text.find("  - id: B-037")
    if start != -1:
        following = text.find("  - id:", start + len("  - id: B-037"))
        end = len(text) if following == -1 else following
        text = text[:start] + TASK + "\n\n" + text[end:]
        print("B-037 replaced with its completed record")
    else:
        text = text.rstrip("\n") + "\n\n" + TASK
        print("B-037 appended")
    BACKLOG.write_text(text, encoding="utf-8", newline="\n")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
