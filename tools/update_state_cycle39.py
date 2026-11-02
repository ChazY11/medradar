"""Update STATE and BACKLOG for cycle 39 (static figure layout check)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-072
    layer: govern
    priority: P2
    title: Static figure-layout check in the round-end gate
    status: done
    owner: lead
    depends_on: [B-071]
    acceptance: >
      papers/check_layout.py catches the two mechanical defect classes that only a rendered review had caught before
      (text outside the canvas; text painted over by a later filled shape), measures rotated axis labels vertically,
      and is verified against injected defects rather than only clean figures. Seven unit tests including one that
      asserts the committed figures are clean. tools/round_end.py runs it as a tenth step: "layout checks: 5
      figures; problems: 0".


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-04T02:40:00+08:00"
    state["phase"] = "layout_check_automated"
    state["cycle"] = 41
    state["last_completed_cycle"] = {
        "cycle": 39,
        "name": "static_layout_check",
        "branch": "research/change-detection-v1",
        "report": "tools/round_end.json",
        "summary": "research/RESULTS/cycle39_layout_check_2026-11-03.md",
        "verdict": ("the recurring render-only defect class is now a static check: off-canvas text and text painted "
                    "over by a later shape are detected without a browser, verified against injected defects, and the "
                    "round-end gate is 10 steps with 0 failures"),
    }
    state["governance_routine"]["steps"].append("figure layout")
    state["governance_routine"]["last_result"] = {"passed": 10, "failed": 0}
    state["governance_routine"]["layout_check"] = {
        "tool": "papers/check_layout.py",
        "classes": ["text outside the canvas", "text painted over by a later filled shape"],
        "tests": "tests/test_check_layout.py (7, incl. injected defects and a committed-figures assertion)",
        "calibration": ("character width ratio 0.50 after 0.56 produced three false alarms; the estimate errs toward "
                        "over-width, so a clean pass is meaningful and a failure needs a glance"),
        "limits": ("does not replace a rendered review: contrast, text-on-text overlap and other SVG features are "
                   "still the render's job"),
    }
    state["established_findings"] = state["established_findings"] + [
        "GOVERN: the fourth render-only defect class is now static - off-canvas text and text painted over by a "
        "later shape are caught by check_layout.py, proven against injected defects, and run as gate step 10",
    ]
    state["next_actions"] = [
        "reclassify backlog items whose data is structurally unavailable as blocked, with the evidence recorded",
        "mature the prospective forecast set when the lane advances (earliest 2026-Q4)",
        "keep tools/round_end.py as the gate at the end of every round",
        "a rendered review is still needed for contrast and text-on-text overlap; schedule one before any submission",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-072" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-072 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
