"""Update STATE.json and BACKLOG.yaml for cycle 18 (paper figures)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-053
    layer: publish
    priority: P1
    title: Paper figures generated from artifacts (stdlib SVG)
    status: done
    owner: lead
    depends_on: [B-052]
    acceptance: >
      papers/figures.py emits four SVG plates directly (no plotting dependency): detection frontier,
      ratio-vs-p calibration scatter, rolling-origin lift with CIs, verdict-stability matrix.
      papers/verify_figures.py re-derives every plotted value from its source artifact, parses each
      SVG, rejects numeric artefacts, and requires the paper to link each figure. Rendered to PNG and
      visually inspected; three layout defects found and fixed.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T05:40:00+08:00"
    state["phase"] = "publish_draft_v1_figures"
    state["cycle"] = 20
    state["last_completed_cycle"] = {
        "cycle": 18,
        "name": "paper_figures",
        "branch": "research/change-detection-v1",
        "report": "papers/figures/figures_data.json",
        "summary": "research/RESULTS/cycle18_figures_2026-11-03.md",
        "verdict": ("four SVG figures generated from the artifacts with zero dependencies, 131 plotted "
                    "points re-derived and verified, paper links checked; headless rendering caught "
                    "three layout defects that structural checks missed"),
    }
    state["publication"].update({
        "figures": {
            "count": 4,
            "generator": "papers/figures.py (hand-written SVG, no dependencies)",
            "verifier": "papers/verify_figures.py (re-derives 131 plotted points, 0 failures)",
            "plates": ["fig1_frontier.svg", "fig2_calibration.svg", "fig3_rolling_origin.svg",
                       "fig4_verdict_stability.svg"],
            "visual_check": "rendered with headless Edge; three layout defects found and fixed",
        },
        "known_gaps": ["no external validation on a second domain",
                       "retraction table needs a per-finding reproduction index",
                       "independent lanes reported as measured limits, not standalone studies"],
    })
    state["established_findings"] = state["established_findings"] + [
        "PUBLISH: the paper now has four generated, verified, dependency-free figures (131 plotted "
        "points re-derived from artifacts); the only previously blocking readability gap is closed",
        "PROCESS: structural SVG validity is not readability - headless rendering caught three layout "
        "defects (clipped labels, annotation off-frame, missing row labels) that checks could not",
    ]
    state["next_actions"] = [
        "B-026: spike vs sustained level-shift classifier (last P1 model task needing no new data)",
        "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
        "add a per-finding reproduction index to the paper's retraction table",
        "consider external validation of the measurement rules on a second domain before submission",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-053" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-053 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
