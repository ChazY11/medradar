"""Update research/STATE.json for cycle 5 (independent device-trial lane)."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("research/STATE.json")
state = json.loads(PATH.read_text(encoding="utf-8"))

state["updated_at"] = "2026-11-02T15:10:00+08:00"
state["phase"] = "understand_and_dense_signal_acquisition"
state["cycle"] = 7
state["last_completed_cycle"] = {
    "cycle": 5,
    "name": "independent_device_trial_lane",
    "branch": "research/change-detection-v1",
    "report": "experiments/b040/REPORT.md",
    "summary": "research/RESULTS/cycle5_independent_lane_2026-11-02.md",
    "verdict": ("an independent device-trial lane now exists (2,663 events, 43 device tracks), but "
                "the pre-declared lag test shows no association with regulatory clearances at any "
                "lag from -6 to +12 months; 16 eligible cells, profile inside the null band"),
}
state["independence_audit"] = {
    "status": "ADDRESSED - independent lane collected; association test run and null",
    "lane": {
        "source": "ClinicalTrials.gov API v2, interventional, device tracks",
        "events": 2663,
        "date_range": "2016-09 .. 2026-10",
        "companies": 46,
        "device_tracks": 43,
        "sponsor_attribution_rate": 0.55,
        "device_track_mapping_rate": 0.48,
        "manifest": "experiments/b040/collection_manifest.json",
        "rows_committed": False,
        "why_not_committed": "data/ is git-ignored and the registry is live; the manifest pins the sample",
    },
    "test": {
        "pre_registration": "DECISIONS D-022",
        "cells_in_both_lanes": 26,
        "cells_eligible": 16,
        "lags": "-6..+12 months",
        "largest_observed_r": 0.036,
        "largest_observed_lag": 7,
        "null_band_at_that_lag": [-0.046, 0.048],
        "verdict": "no detectable association at any lag",
    },
    "what_is_not_licensed": ("that trials and clearances are unrelated - coverage 55%/48%, sparse "
                             "series, and company-vs-legal-entity granularity all dominate"),
}
state["established_findings"] = [
    finding for finding in state["established_findings"]
    if "no independent confirmation source exists" not in finding
] + [
    "OBSERVE: a device-track-mapped ClinicalTrials.gov lane now exists (2,663 events, 43 tracks, 46 "
    "companies) and is documented in a committed manifest",
    "OBSERVE: the two independent lanes show NO detectable aligned time structure at cell level "
    "(16 eligible cells; whole lag profile -6..+12 inside the null band)",
    "OBSERVE: evidence-fusion claims between trials and clearances are unsupported by this test",
]
state["blockers"] = [
    "dense per-cell independent signal: hiring and patents remain uncollected (B-030, B-031); the "
    "trial lane exists but is too sparse at cell level for association testing",
    "B-015 matured-forecast calibration blocked on wall-clock (windows close 2027-10)",
]
state["next_actions"] = [
    "B-042: company entry-cohort unit of analysis (replaces cell-month counts where density fails)",
    "B-030: attempt a lawful, point-in-time hiring source (the densest remaining independent signal)",
    "B-031: patents via bulk files or a key (second declared gap)",
    "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
    "B-027: company technology-profile engine (Understand layer) with the seven evidence fields",
]
PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
