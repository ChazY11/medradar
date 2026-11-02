"""Update research/STATE.json for cycle 14 (full roster + frozen snapshot)."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("research/STATE.json")
state = json.loads(PATH.read_text(encoding="utf-8"))

state["updated_at"] = "2026-11-03T01:40:00+08:00"
state["phase"] = "point_in_time_snapshots"
state["cycle"] = 16
state["last_completed_cycle"] = {
    "cycle": 14,
    "name": "full_roster_and_frozen_snapshot",
    "branch": "research/change-detection-v1",
    "report": "experiments/b027/snapshots/2026-11-02/manifest.json",
    "summary": "research/RESULTS/cycle14_snapshot_2026-11-03.md",
    "verdict": ("53 full-roster profiles and a hash-verified frozen snapshot (2026-11-02) shipped; a "
                "naive ratio rule would have flagged 35 of 53 companies while the exact binomial test "
                "supports 4 (Olympus, Philips, Steris, Medline) - 31 would have been unsupported "
                "claims"),
}
state["point_in_time"] = {
    "status": "FIRST FROZEN SNAPSHOT SHIPPED",
    "snapshot": "experiments/b027/snapshots/2026-11-02",
    "manifest_hash": "31af25c989f2650d",
    "companies": 53,
    "scope": "roster (51-company device roster + Draeger and Mindray from the universe focus list)",
    "sources_hashed": ["data/research.sqlite", "data/b040_device_trials.sqlite",
                       "config/companies_device.json", "config/universe_v1.json",
                       "config/product_code_tracks.json"],
    "verification": {
        "library": "medradar/intelligence/snapshot.py (23 unit tests)",
        "selfcheck": "manifest hashes, summary/profile agreement, markdown reproduction, as-of match",
        "result": "snapshot OK; markdown reproduces exactly from the JSON",
    },
    "calibration": {
        "naive_ratio_rule_flags": 35,
        "exact_binomial_detections": 4,
        "unsupported_naive_claims": 31,
        "detected": {"olympus": {"ratio": 4.17, "p": 0.0001, "mde": 2.46},
                     "philips": {"ratio": 2.03, "p": 0.0005, "mde": 1.77},
                     "steris": {"ratio": 0.50, "p": 0.0198, "mde": 2.25},
                     "medline": {"ratio": 0.44, "p": 0.0288, "mde": 2.76}},
        "report": "experiments/b027/momentum_calibration.json",
    },
    "next_prerequisite": "freeze a second snapshot at the next as-of date and diff the two - the first "
                         "genuinely point-in-time comparison available to the programme",
}
state["established_findings"] = state["established_findings"] + [
    "POINT-IN-TIME: a dated, source-hashed, self-verifying profile snapshot now exists "
    "(snapshots/2026-11-02, 53 companies, manifest 31af25c9); later cycles can prove what this one knew",
    "CALIBRATION: across 53 companies a naive ratio rule flags 35 and the exact binomial test supports "
    "4 - 31 would have been unsupported claims (e.g. iRhythm 4 vs 1, ratio 4.00, p=0.375, MDE 22.9x)",
    "CALIBRATION: per-company MDEs range from 1.77x to 22.9x, so detected counts cannot be compared as "
    "an innovation ranking",
]
state["next_actions"] = [
    "freeze a second snapshot at the next as-of date and diff the two (first point-in-time comparison)",
    "wire the cycle-3c detection frontier into the per-track change field so per-track 'change' is "
    "calibrated against the controlled-truth benchmark rather than only a rate test",
    "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
    "do not resume hiring probing (structural limit, D-031); patents only if a route opens",
]
PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
