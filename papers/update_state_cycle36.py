"""Update STATE and BACKLOG for cycle 36 (methods paper)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-069
    layer: publish
    priority: P1
    title: Second paper — measurement rules derived from the retractions
    status: done
    owner: lead
    depends_on: [B-063, B-068]
    acceptance: >
      papers/PAPER_METHODS_v1.md: nine rules each tied to the failure that motivated it, the two enforcement
      mechanisms (contradictory-evidence schema; round-end command), and the two results needing an intermediate
      category (post-failure density confirmation; pipeline test that found the detector not the filter).
      papers/CLAIMS_METHODS.json declares 22 quantitative claims with artifacts and exact substrings;
      verify_claims.py --claims checks both directions (22/22). round_end.py now runs both claim maps (8 steps).
      papers/README.md indexes the two papers and how to read them together.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T23:40:00+08:00"
    state["phase"] = "two_papers_shipped"
    state["cycle"] = 38
    state["last_completed_cycle"] = {
        "cycle": 36,
        "name": "methods_paper",
        "branch": "research/change-detection-v1",
        "report": "papers/PAPER_METHODS_v1.md",
        "summary": "research/RESULTS/cycle36_methods_paper_2026-11-03.md",
        "verdict": ("second paper shipped: nine measurement rules each tied to the failure that motivated it, the "
                    "two enforcement mechanisms, and two results needing an intermediate category; its own 22-claim "
                    "map verifies in both directions and the round-end gate now runs both claim maps (8 steps)"),
    }
    state["publication"]["second_paper"] = {
        "paper": "papers/PAPER_METHODS_v1.md",
        "claims": "papers/CLAIMS_METHODS.json (22)",
        "verifier": "papers/verify_claims.py --claims papers/CLAIMS_METHODS.json",
        "index": "papers/README.md",
        "rules": 9,
        "mechanisms": ["contradictory-evidence schema", "round-end completion gate"],
        "intermediate_category_results": ["post-failure density confirmation",
                                          "pipeline test: detector yes, filter unestablished"],
        "status": "draft v1, not submitted",
    }
    state["established_findings"] = state["established_findings"] + [
        "PUBLISH: two papers now exist with independent machine-verified claim maps (82 and 22 claims) and the "
        "round-end gate runs both, so neither can drift",
        "PUBLISH: the methods paper names nine rules each tied to the specific failure that motivated it, and the "
        "two enforcement mechanisms that make the rules structural rather than advisory",
    ]
    state["next_actions"] = [
        "mature the prospective forecast set as the lane advances (earliest 2026-Q4)",
        "keep tools/round_end.py as the gate at the end of every round",
        "refresh ROADMAP with what is done and what remains before the objective is declared complete",
        "consider adding a figure to the methods paper showing the retraction-to-rule mapping",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-069" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-069 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
