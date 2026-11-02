"""Update STATE.json and BACKLOG.yaml for cycle 17 (paper draft v1)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-052
    layer: publish
    priority: P1
    title: Paper draft v1 from the committed record
    status: done
    owner: lead
    depends_on: [B-020, B-023, B-050, B-051]
    acceptance: >
      papers/PAPER_v1.md covering corpus and provenance, controlled-truth frontier, five retracted
      findings with the control that killed each, calibration result, rolling-origin null, verdict
      instability, the Understand layer, seven measurement rules, limitations and reproduction. Every
      quantitative claim declared in papers/CLAIMS.json with its artifact and exact substring, verified
      in both directions by papers/verify_claims.py (45/45). Draft only: not submitted, no venue
      claimed, no figures.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T04:40:00+08:00"
    state["phase"] = "publish_draft_v1"
    state["cycle"] = 19
    state["last_completed_cycle"] = {
        "cycle": 17,
        "name": "paper_draft_v1",
        "branch": "research/change-detection-v1",
        "report": "papers/PAPER_v1.md",
        "summary": "research/RESULTS/cycle17_paper_2026-11-03.md",
        "verdict": ("paper draft v1 shipped with a machine-verified claim map (45/45 claims sourced "
                    "both ways); it reports five retractions, a controlled false-alarm frontier, the "
                    "calibration result, a rolling-origin null, verdict instability and a leakage-free "
                    "point-in-time chain, and claims no predictive success"),
    }
    state["publication"] = {
        "status": "DRAFT v1 IN REPOSITORY - not submitted, no venue claimed",
        "paper": "papers/PAPER_v1.md",
        "claims": "papers/CLAIMS.json",
        "verifier": "papers/verify_claims.py",
        "claims_verified": 45,
        "headline": "no surviving positive result; five retractions with mechanisms; methodological "
                    "artifacts (frontier, calibration rule, point-in-time chain, measurement rules)",
        "known_gaps": ["no figures", "no external validation on a second domain",
                       "retraction table needs a per-finding reproduction index",
                       "independent lanes reported as measured limits, not standalone studies"],
    }
    state["established_findings"] = state["established_findings"] + [
        "PUBLISH: paper draft v1 exists as a repository artifact with 45 machine-verified claims; every "
        "number is traced to a committed artifact in both directions (source contains it, paper contains it)",
        "PUBLISH: the paper's headline is negative by design - five retractions with their control "
        "mechanisms, no predictive success claimed",
    ]
    state["next_actions"] = [
        "B-026: spike vs sustained level-shift classifier (last P1 model task needing no new data)",
        "add figures to the paper from existing artifacts (frontier curve, calibration scatter, "
        "verdict-stability matrix) - the only blocking gap for a readable submission",
        "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
        "consider external validation of the measurement rules on a second domain before any submission",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-052" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-052 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
