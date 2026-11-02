"""Update STATE.json and BACKLOG.yaml for cycle 28 (objective audit)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-061
    layer: govern
    priority: P0
    title: Mechanical audit of the mission objective
    status: done
    owner: lead
    depends_on: []
    acceptance: >
      tools/audit_objectives.py turns the mission text into checks and writes research/AUDIT.json and
      research/AUDIT.md: eleven required state files, backlog integrity, state completeness, loop evidence
      (decisions, result rows, negatives, retractions), committed experiments, point-in-time snapshots
      verifying, the rolling-origin benchmark, frozen forecasts, the paper's claim map, figures, the
      profile self-check and working-tree cleanliness. Current result: 11 PASS, 0 FAIL, 1 N/A, exit 0.
      Re-runnable, so "the objective is met" is tested rather than asserted.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T15:40:00+08:00"
    state["phase"] = "objective_mechanical_audit"
    state["cycle"] = 30
    state["last_completed_cycle"] = {
        "cycle": 28,
        "name": "objective_audit",
        "branch": "research/change-detection-v1",
        "report": "research/AUDIT.md",
        "summary": "research/RESULTS/cycle28_audit_2026-11-03.md",
        "verdict": ("objective audited mechanically: 11 PASS, 0 FAIL, 1 N/A across state files, backlog, loop "
                    "evidence, experiments, 5 verifying snapshots, the rolling-origin benchmark, frozen "
                    "forecasts, 66/66 claims, 4 figures and the profile self-check"),
    }
    state["audit"] = {
        "tool": "tools/audit_objectives.py",
        "artifacts": ["research/AUDIT.json", "research/AUDIT.md"],
        "last_result": {"passed": 11, "failed": 0, "not_applicable": 1},
        "not_applicable_reason": "working tree is expected to be dirty while a cycle is in progress",
        "checks": ["state files", "backlog integrity", "state completeness", "loop evidence",
                   "committed experiments", "snapshots verify", "rolling-origin benchmark",
                   "frozen forecasts", "paper claims", "figures", "profile self-check",
                   "working tree"],
        "purpose": ("completeness and reproducibility, not correctness: it cannot prove the science is right, "
                    "only that the artifacts exist, verify and are committed"),
    }
    state["established_findings"] = state["established_findings"] + [
        "GOVERN: the objective is checked mechanically and re-runnably (11 PASS, 0 FAIL, 1 N/A); a claim of "
        "progress no longer depends on a narrative",
        "UNDERSTAND: profiles now name the governing promotion policy version in their limits, and the "
        "promotion ledger carries a reviewer checklist for signers",
    ]
    state["next_actions"] = [
        "wire the audit into the round-end routine so every round reports it",
        "third domain only if >=15 eligible series exist at the established floors",
        "add the promotion policy and both blind spots to the paper's limitations section",
        "consider a second paper focused on the measurement rules rather than the frontier",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-061" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-061 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
