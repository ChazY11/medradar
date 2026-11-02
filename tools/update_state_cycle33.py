"""Update STATE and BACKLOG for cycle 33 (round-end routine + paper limitations)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-066
    layer: govern
    priority: P0
    title: Executable round-end routine and honest paper limitations
    status: done
    owner: lead
    depends_on: [B-061]
    acceptance: >
      tools/round_end.py runs seven verifiers in one pass (test suite, claim map, figures, profile self-check,
      snapshot chain, objective audit, repository state) and writes tools/round_end.json plus a readable log;
      exit code is the claim. Current result 7 PASS / 0 FAIL in ~23 s. Paper section 6 now states that exactly
      one decision rule was confirmed against five retractions, that promotion requires human sign-off with no
      automated path, that the ramp label is withheld below 1.0 event/month, and that the density scaling is a
      post-failure confirmation.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T20:40:00+08:00"
    state["phase"] = "round_end_routine_executable"
    state["cycle"] = 35
    state["last_completed_cycle"] = {
        "cycle": 33,
        "name": "round_end_routine_and_limitations",
        "branch": "research/change-detection-v1",
        "report": "tools/round_end.json",
        "summary": "research/RESULTS/cycle33_round_end_2026-11-03.md",
        "verdict": ("a round now ends with one command: tools/round_end.py runs seven verifiers and exits with "
                    "the claim (7 PASS / 0 FAIL, ~23 s); the paper's limitations section states the 1-confirmed-rule "
                    "to 5-retraction ratio, the human sign-off requirement, the density floor and the "
                    "post-failure status of the density confirmation"),
    }
    state["governance_routine"] = {
        "tool": "tools/round_end.py",
        "artifacts": ["tools/round_end.json", "tools/round_end.log"],
        "steps": ["test suite", "paper claim map", "paper figures", "profile self-check",
                  "snapshot chain", "objective audit", "repository state"],
        "last_result": {"passed": 7, "failed": 0, "runtime_seconds": 23},
        "lesson": ("unittest writes its summary to stderr and per-step marker extraction is required; a generic "
                   "keyword heuristic reported the wrong line on the first attempt"),
        "rule": "a round is not finished until this command exits 0",
    }
    state["established_findings"] = state["established_findings"] + [
        "GOVERN: a round ends with an executable verification routine (7 steps, one exit code), so the round-end "
        "claim is re-runnable rather than asserted",
        "PUBLISH: the paper's limitations now state the honest ratio - one confirmed decision rule against five "
        "retractions - plus the sign-off requirement, the density floor and the post-failure status of the "
        "density confirmation",
    ]
    state["next_actions"] = [
        "run tools/round_end.py at the end of every round as the completion gate",
        "consider a second paper focused on the measurement rules and the density confirmation",
        "decide whether the promotion ledger should log relabelling events as an audit trail",
        "revisit the 1.0/month floor if a denser domain becomes available",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-066" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-066 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
