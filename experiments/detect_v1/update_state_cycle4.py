"""Update research/STATE.json for cycle 4 (independence audit + co-movement)."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("research/STATE.json")
state = json.loads(PATH.read_text(encoding="utf-8"))

state["updated_at"] = "2026-11-02T14:00:00+08:00"
state["phase"] = "understand_prerequisites"
state["cycle"] = 6
state["last_completed_cycle"] = {
    "cycle": 4,
    "name": "independence_audit_and_comovement",
    "branch": "research/change-detection-v1",
    "report": "experiments/detect_v1/COMOVEMENT.md",
    "summary": "research/RESULTS/cycle4_independence_comovement_2026-11-02.md",
    "verdict": ("no independent confirmation source exists in the spine (trial lane is drug-track "
                "only; 0/104 cells matchable), and no month-level cross-firm co-movement survives "
                "a null that conditions on the track's own volume (0/32 tracks)"),
}
state["independence_audit"] = {
    "status": "BLOCKED - measured, not assumed",
    "evidence": "experiments/detect_v1/probe_trials_source.py",
    "reason": ("the only genuinely different registry in the data spine (ClinicalTrials.gov, 55,592 "
               "events) is mapped to drug tracks (22 x t_*), which are disjoint from the device "
               "tracks used by the detection panel: 0 of 104 detection cells contain a trial event"),
    "other_sources_rejected": {
        "openalex_publications": "annual, 51 curated companies only",
        "usaspending": "award_date NULL in all 3,453 rows, pit_usable=0",
        "pma_vs_510k": "same filing system, not independent",
    },
    "unblock_path": "B-040: collect ClinicalTrials.gov DEVICE trials with device-track mapping",
}
state["comovement"] = {
    "question": "do several competitors become active in the same technology track at once?",
    "lane_volume_null_tracks_rejected": 3,
    "lane_volume_null_rejected_keys": ["ivd_molecular", "medical_ai", "spine"],
    "track_volume_null_tracks_rejected": 0,
    "track_volume_null_tests": 32,
    "strongest_positive_z": 1.21,
    "conclusion": ("month-level cross-firm synchronisation is not detectable once the track's own "
                   "growth is conditioned out; the three apparent cases are track growth admitting "
                   "firms over time"),
    "limitation": ("most tracks sit below the null because the null draws firm-months independently "
                   "while firms file in bursts; the test is conservative in the positive direction "
                   "and the negative direction is an artefact, not anti-synchronisation"),
    "artifacts": ["experiments/detect_v1/comovement.json",
                  "experiments/detect_v1/COMOVEMENT.md"],
}
state["established_findings"] = [
    finding for finding in state["established_findings"]
    if "independent confirmation" not in finding
] + [
    "OBSERVE: no independent confirmation source exists in the shipped spine - the only different "
    "registry (ClinicalTrials.gov) is mapped to drug tracks disjoint from device tracks (0/104 cells)",
    "OBSERVE: no month-level cross-firm co-movement survives a null conditioning on the track's own "
    "volume (0/32 tracks; lane-wide null would have reported 3 false positives)",
    "OBSERVE: technology activity in this lane is firm-specific plus track-level growth; the data do "
    "not show firms moving together",
]
state["blockers"] = [
    "independent change confirmation: no second source (B-033 measured-blocked; unblock via B-040)",
    "B-015 matured-forecast calibration blocked on wall-clock (windows close 2027-10)",
    "B-030 hiring blocked on lawful snapshot history",
    "B-031 patents blocked on API key or bulk files",
]
state["next_actions"] = [
    "B-040: collect ClinicalTrials.gov DEVICE trials with device-track mapping - the prerequisite "
    "for independent confirmation",
    "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
    "B-037: seasonal and lane-volume artifact adjustment",
    "B-027: company technology-profile engine (Understand layer) with the seven required evidence fields",
    "B-020: acquisition-chain-aware parent panel",
]
PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
