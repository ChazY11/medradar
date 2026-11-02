"""Update STATE.json and BACKLOG.yaml for cycle 21 (deployment resolution)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T08:40:00+08:00"
    state["phase"] = "deployment_resolution_fixed"
    state["cycle"] = 23
    state["last_completed_cycle"] = {
        "cycle": 21,
        "name": "deployment_resolution",
        "branch": "research/change-detection-v1",
        "report": "experiments/b039/deployment_resolution.json",
        "summary": "research/RESULTS/cycle21_deployment_2026-11-03.md",
        "verdict": ("the OBSERVE layer deploys at 3-month (quarterly) resolution; at that resolution the "
                    "rolling z-score has the highest measured sensitivity (0.147, CI 0.112-0.182) and no "
                    "detector is identifiable across resolutions (winner changes; Kendall tau -1.0 vs "
                    "monthly), so the choice is resolution-specific and must never be cited as a ranking"),
    }
    state["observe_layer"] = {
        "deployment_resolution_months": 3,
        "resolution_justification": ("quarterly portfolio-decision cadence; monthly resolution leaves "
                                     "~0.2 events per cell-month where detectors cannot resolve a change"),
        "deployed_detector": "rolling_zscore (resolution-specific choice, not a ranking claim)",
        "artifact": "experiments/b039/deployment_resolution.json",
        "decision": "research/DECISIONS.md D-044 (pre-registration), D-045 (outcome)",
        "at_deployment_resolution": {
            "rolling_zscore": {"sensitivity": 0.147, "ci": [0.112, 0.182], "delay_months": 2},
            "poisson_bayes_factor": {"sensitivity": 0.073, "ci": [0.051, 0.096], "delay_months": 0},
            "poisson_cusum": {"sensitivity": 0.065, "ci": [0.036, 0.102], "delay_months": 3},
            "naive_multiplier": {"sensitivity": 0.025, "ci": [0.011, 0.042], "delay_months": 2},
        },
        "identifiability": {"winners_by_width": {"1": "naive_multiplier", "2": "poisson_cusum",
                                                 "3": "rolling_zscore", "4": "poisson_cusum",
                                                 "6": "rolling_zscore"},
                            "kendall_tau_vs_deployment": {"1": -1.0, "2": 0.0, "4": 0.33, "6": 0.67},
                            "identifiable": False,
                            "rule": "same winner everywhere AND all tau >= 0.5"},
        "carry_forward": ("every artifact using the detector must state resolution: 3 months; a change of "
                          "resolution requires re-measurement (at monthly the same detector ranks last)"),
    }
    state["established_findings"] = state["established_findings"] + [
        "OBSERVE: deployment resolution fixed at 3 months (quarterly), justified by the decision cadence "
        "and by the measured sparsity ceiling",
        "OBSERVE: at quarterly resolution the rolling z-score is significantly best (0.147, CI 0.112-0.182; "
        "no overlap with the other three) but NO detector is identifiable across resolutions (Kendall tau "
        "-1.0 against the monthly ranking), so the choice is resolution-specific",
    ]
    state["next_actions"] = [
        "wire the deployment choice (quarterly, rolling z-score) into the profile alert provenance",
        "B-055: confirm the promotion rule on fresh cells (requires a larger eligible-cell set)",
        "add the deployment-resolution section to the paper's reproduction notes (done in this cycle)",
        "consider a second-domain validation before calling any of this portable",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-039" in text:
        start = text.index("  - id: B-039")
        following = text.find("  - id:", start + len("  - id: B-039"))
        end = len(text) if following == -1 else following
        block = text[start:end]
        if "status: todo" in block:
            text = text.replace(block, block.replace("status: todo", "status: done", 1), 1)
    BACKLOG.write_text(text, encoding="utf-8", newline="\n")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
