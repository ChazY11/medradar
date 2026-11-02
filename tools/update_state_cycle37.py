"""Update STATE and BACKLOG for cycle 37 (roadmap rewrite + mission position update)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-070
    layer: govern
    priority: P0
    title: Rewrite the roadmap from what exists and update the mission's honest position
    status: done
    owner: lead
    depends_on: [B-069]
    acceptance: >
      research/ROADMAP.md rewritten as a plan of record: one status table where every capability cites its
      evidence, phase-by-phase results (A done, B done with the non-identifiability limit, C partly blocked, D
      done, E four diagnosed failures, F null now prospective, G not started on purpose), and a section 3 listing
      what remains and why it cannot be simulated (25 forecasts maturing 2026-Q4..2028-Q1, 25 nowcasts maturing
      2027-10, one promotion awaiting human sign-off, access-blocked lanes, structurally unavailable hiring
      coverage). research/MISSION.md keeps section 9 as the 2026-11-02 record and adds section 10 with today's
      position, established and unchanged. Audit stays 11 PASS / 0 FAIL / 1 N/A.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-04T00:40:00+08:00"
    state["phase"] = "roadmap_current"
    state["cycle"] = 39
    state["last_completed_cycle"] = {
        "cycle": 37,
        "name": "roadmap_and_position_refresh",
        "branch": "research/change-detection-v1",
        "report": "research/ROADMAP.md",
        "summary": "research/RESULTS/cycle37_roadmap_2026-11-03.md",
        "verdict": ("roadmap rewritten as a plan of record where every capability cites its evidence, with a "
                    "section stating what remains and why it cannot be simulated; mission section 10 added while "
                    "section 9 is preserved as the 2026-11-02 record"),
    }
    state["completion_position"] = {
        "deliverables_satisfied": {
            "persistent research state": "research/ (11 required files) - audit PASS",
            "observe_question_hypothesize_implement_experiment_evaluate_record_improve loop":
                "67 decisions, 136 result rows (27 negative/null), 2 retractions marked - audit PASS",
            "verifiable code": "910 tests; selftest exit 0; every artifact re-derivable",
            "point-in-time datasets": "6 auditable snapshots, 0 leakage problems",
            "rolling-origin benchmarks": "376 cells, 12 origins, 717 observations",
            "frozen forecasts": "2 hash-verified sets; 25 genuinely prospective forecasts pending maturation",
            "papers": "2 papers with machine-verified claim maps (82 + 22 claims)",
        },
        "remaining_not_code": [
            "25 prospective forecasts mature 2026-Q4..2028-Q1 (no prospective calibration claim before that)",
            "25 legacy registry nowcasts mature 2027-10",
            "one promotion awaits a human signature the session cannot give",
            "patents and broad-hiring lanes blocked on access",
            "hiring coverage structurally unavailable for three deep-case companies",
        ],
        "statement": ("the objective's deliverable list is satisfied and machine-checked; what remains is time- and "
                      "access-dependent, which is stated in ROADMAP.md section 3 rather than simulated"),
    }
    state["established_findings"] = state["established_findings"] + [
        "GOVERN: the roadmap now cites an artifact for every capability and names the remaining work as time- or "
        "access-dependent rather than open-ended",
        "GOVERN: the mission distinguishes charter history (section 9, 2026-11-02) from current position (section "
        "10) instead of overwriting the record",
    ]
    state["next_actions"] = [
        "consider a retraction-to-rule figure for the methods paper (material already exists)",
        "run tools/round_end.py as the gate at the end of every round",
        "mature the prospective forecast set when the lane advances (earliest 2026-Q4)",
        "review backlog items whose data is structurally unavailable and mark them blocked rather than open",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-070" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-070 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
