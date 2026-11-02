"""Update STATE.json and BACKLOG.yaml for cycle 20 (confirmed decision rule)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

NEW = """  - id: B-055
    layer: detect
    priority: P2
    title: Confirm the promotion rule on fresh CELLS, not just fresh origins
    status: todo
    owner: lead
    depends_on: [B-054]
    acceptance: >
      The two-month post-alert promotion rule is confirmed on fresh injection months but the same 65
      cells, so cell reuse is a declared limitation. Expand the eligible-cell set (lower the baseline
      floor or widen the roster / add a second lane) and re-run the confirmatory design with cells that
      never appeared in discovery. If the rule does not survive fresh cells, restrict promotion to the
      companies where it was measured.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T07:40:00+08:00"
    state["phase"] = "first_confirmed_rule"
    state["cycle"] = 22
    state["last_completed_cycle"] = {
        "cycle": 20,
        "name": "promotion_rule_confirmation",
        "branch": "research/change-detection-v1",
        "report": "experiments/b026/confirm_window.json",
        "summary": "research/RESULTS/cycle20_confirmation_2026-11-03.md",
        "verdict": ("FIRST CONFIRMED PRE-REGISTERED PREDICTION: on fresh injection months the corrected "
                    "confirmation window reaches balanced accuracy 0.584 (CI 0.556-0.607) and "
                    "sustained-change precision 0.914 (CI 0.892-0.934) vs a 0.696 base rate, clearing "
                    "every pre-declared floor. The binary promotion rule is confirmed; the three-way "
                    "ramp/level distinction is not (ramp recall 0.142); cells were reused, which is a "
                    "declared limitation."),
    }
    state["detection_layer"].update({
        "status": "promotion rule CONFIRMED on fresh origins (post-discovery confirmation)",
        "confirmation": {
            "artifact": "experiments/b026/confirm_window.json",
            "decision": "research/DECISIONS.md D-042 (pre-registration), D-043 (outcome)",
            "alerts": 494, "balanced_accuracy": 0.584, "ci": [0.556, 0.607],
            "sustained_precision": 0.914, "precision_ci": [0.892, 0.934],
            "sustained_base_rate": 0.696, "spike_recall": 0.787, "ramp_recall": 0.142,
            "verdict": "CONFIRMED by the pre-declared rule",
            "scope": "binary promotion decision only; three-way ramp/level not recovered",
            "caveat": "post-discovery confirmation - fresh injection months, same 65 cells",
        },
    })
    state["established_findings"] = state["established_findings"] + [
        "DETECT: the corrected two-month post-alert promotion rule is CONFIRMED out of sample (494 alerts; "
        "balanced accuracy 0.584, sustained precision 0.914 vs 0.696 base rate; 78.7% of spikes caught) - "
        "the programme's first pre-registered prediction to survive confirmation",
        "DETECT: the confirmation does NOT extend to three-way shape recovery (ramp recall 0.142) and does "
        "NOT rescue any earlier association finding",
        "PUBLISH: the paper title, abstract and a new section 4.9 now report the confirmed rule with its "
        "post-discovery caveat; 51 of 51 claims verified",
    ]
    state["next_actions"] = [
        "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
        "B-055: confirm the promotion rule on fresh CELLS (requires expanding the eligible-cell set)",
        "wire the confirmed promotion rule into the profile alert field with its measured error rate",
        "consider a second-domain validation of the promotion rule before calling it portable",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-054" in text:
        start = text.index("  - id: B-054")
        following = text.find("  - id:", start + len("  - id: B-054"))
        end = len(text) if following == -1 else following
        block = text[start:end]
        if "status: todo" in block:
            text = text.replace(block, block.replace("status: todo", "status: done", 1), 1)
    if "id: B-055" not in text:
        text = text.rstrip("\n") + "\n\n" + NEW
        print("B-055 appended")
    BACKLOG.write_text(text, encoding="utf-8", newline="\n")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
