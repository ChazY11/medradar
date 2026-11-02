"""Update STATE.json and BACKLOG.yaml for cycle 16 (point-in-time rebuild)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-051
    layer: understand
    priority: P0
    title: Point-in-time rebuild and leakage audit of the profile engine
    status: done
    owner: lead
    depends_on: [B-027, B-049]
    acceptance: >
      build_profiles --as-of cuts regulatory events, the trial lane and the product-code first-seen
      map at the as-of date, and records a per-profile leakage_audit block. Three backdated snapshots
      frozen (2020-12-31, 2022-12-31, 2024-12-31) with manifests; snapshot_diff.py audits leakage
      (0 problems) and diffs consecutive snapshots; verdict_stability.py measures how often verdicts
      flip across as-of dates. Result: 40 of 53 verdicts stable, 13 change, 2 reverse.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T03:40:00+08:00"
    state["phase"] = "point_in_time_validated"
    state["cycle"] = 18
    state["last_completed_cycle"] = {
        "cycle": 16,
        "name": "point_in_time_rebuild_and_leakage_audit",
        "branch": "research/change-detection-v1",
        "report": "experiments/b027/snapshot_diff.json",
        "summary": "research/RESULTS/cycle16_point_in_time_2026-11-03.md",
        "verdict": ("point-in-time rebuild shipped and audited: 3 backdated snapshots, 0 leakage "
                    "problems; a real leakage path (trial lane + code first-seen were not cut at the "
                    "as-of date) was found and closed; 40 of 53 verdicts stable across as-of dates, "
                    "13 change, 2 reverse"),
    }
    state["point_in_time"].update({
        "status": "VALIDATED - leakage audit clean, snapshot chain frozen",
        "snapshots": ["2020-12-31", "2022-12-31", "2024-12-31", "2026-11-02"],
        "auditable_snapshots": 3,
        "unauditable_snapshots": {"2026-11-02": "frozen before the audit block existed"},
        "leakage_path_fixed": ("the trial lane and the product-code first-seen map were read in full "
                               "regardless of as-of; both are now truncated at the as-of date and the "
                               "trial cut is recorded in each profile's leakage_audit"),
        "lane_events_used": {"2020-12-31": 12853, "2022-12-31": 19182, "2024-12-31": 25772,
                             "2026-11-02": 31802},
        "diff_artifact": "experiments/b027/snapshot_diff.json",
        "stability_artifact": "experiments/b027/verdict_stability.json",
        "verdict_stability": {"companies": 53, "stable": 40, "changed": 13, "reversed": 2,
                              "reversals": ["hologic", "zimmer_biomet"]},
        "leakage_problems": 0,
    })
    state["established_findings"] = state["established_findings"] + [
        "POINT-IN-TIME: three backdated profile snapshots are frozen and leakage-audited (0 problems); "
        "the 2020-12-31 / 2022-12-31 / 2024-12-31 views use 12,853 / 19,182 / 25,772 lane events",
        "POINT-IN-TIME: a real leakage path was found and closed - the trial lane and the code "
        "first-seen map were previously read in full regardless of the as-of date",
        "POINT-IN-TIME: verdict stability across four as-of dates is 40 stable / 13 changed / 2 "
        "reversed of 53 companies - a quarter of nowcasts move with the date, consistent with the "
        "calibrated test's measured low power",
    ]
    state["next_actions"] = [
        "B-026: spike vs sustained level-shift classifier (the last P1 model task not needing new data)",
        "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
        "consider a paper draft from the surviving artifacts (lane provenance, frontier benchmark, "
        "calibration results, point-in-time chain) - the objective lists papers as deliverables",
        "do not resume hiring probing (D-031); patents only if a route opens",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-051" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-051 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
