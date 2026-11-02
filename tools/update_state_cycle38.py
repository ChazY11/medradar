"""Update STATE and BACKLOG for cycle 38 (methods paper Figure 1)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-071
    layer: publish
    priority: P2
    title: Figure 1 of the methods paper — the retraction-to-rule map
    status: done
    owner: lead
    depends_on: [B-069]
    acceptance: >
      papers/figures/fig5_retraction_rules.svg generated from papers/rules_map.py: ten events, nine rules, 21
      filled cells; verify_figures.py re-derives every cell and compares with figures_data.json. Three layout
      defects found only by a headless-Edge render (legend covering columns 8-9, decision ids printed on top of
      event labels, legend running off the canvas) and fixed; recorded as a recurring class. PAPER_METHODS_v1.md
      links the figure with captions tied to the counts; CLAIMS_METHODS.json is now 25 claims, three asserting the
      figure's numbers; the round-end gate runs both figure verifications (9 steps).


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-04T01:40:00+08:00"
    state["phase"] = "methods_figure_shipped"
    state["cycle"] = 40
    state["last_completed_cycle"] = {
        "cycle": 38,
        "name": "methods_figure",
        "branch": "research/change-detection-v1",
        "report": "papers/figures/fig5_retraction_rules.svg",
        "summary": "research/RESULTS/cycle38_rules_figure_2026-11-03.md",
        "verdict": ("fifth figure maps ten events to nine rules (21 filled cells); Rules 7 and 3 carry the most "
                    "independent evidence (four and three events). Three layout defects were found only by a "
                    "rendered check and fixed; the methods paper now links its own figure and the gate runs both "
                    "figure verifications (9 steps)"),
    }
    state["publication"]["second_paper"]["figures"] = {
        "file": "papers/figures/fig5_retraction_rules.svg",
        "source": "papers/rules_map.py",
        "events": 10, "rules": 9, "filled_cells": 21,
        "max_rule": {"rule": 7, "events": 4},
        "claims": 3, "gate_step": "methods figures",
    }
    state["established_findings"] = state["established_findings"] + [
        "PUBLISH: the retraction-to-rule map shows Rule 7 (check the pipeline) motivated by four separate events and "
        "Rule 3 (benchmark outcome independence) by three - the two most 'boilerplate'-looking rules have the most "
        "independent evidence",
        "METHOD: a rendered check caught three layout defects the SVG validator could not (legend covering column "
        "headings, overlapping labels, legend off-canvas); this is the fourth such case and is now treated as a "
        "recurring class rather than an accident",
    ]
    state["next_actions"] = [
        "mark backlog items whose data is structurally unavailable as blocked rather than open",
        "mature the prospective forecast set when the lane advances (earliest 2026-Q4)",
        "keep tools/round_end.py as the gate at the end of every round",
        "consider a rendering check step for figures in the gate (currently manual)",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-071" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-071 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
