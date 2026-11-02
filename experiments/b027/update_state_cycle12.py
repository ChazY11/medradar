"""Update research/STATE.json for cycle 12 (Understand layer: profiles)."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("research/STATE.json")
state = json.loads(PATH.read_text(encoding="utf-8"))

state["updated_at"] = "2026-11-02T23:50:00+08:00"
state["phase"] = "understand_profiles_shipped"
state["cycle"] = 14
state["last_completed_cycle"] = {
    "cycle": 12,
    "name": "understand_layer_profiles",
    "branch": "research/change-detection-v1",
    "report": "experiments/b027/profiles.json",
    "summary": "research/RESULTS/cycle12_profiles_2026-11-02.md",
    "verdict": ("first Understand-layer deliverable shipped: a pure, unit-tested profile engine with "
                "seven required fields (contradictory evidence is structural, not optional), and "
                "profiles generated for all five mandated deep-case companies; selfcheck 5/5, "
                "selftest 829 tests OK"),
}
state["understand_layer"] = {
    "status": "SHIPPED for the five mandated deep cases",
    "library": "medradar/intelligence/profile.py (pure; 34 unit tests in tests/test_profile.py)",
    "builder": "experiments/b027/build_profiles.py",
    "artifacts": ["experiments/b027/profiles.json", "experiments/b027/profiles/*.md",
                  "experiments/b027/selfcheck.py"],
    "seven_fields": ["identity", "technology_footprint", "momentum", "concentration",
                     "independent_corroboration", "contradictory_evidence",
                     "limits_and_provenance"],
    "design_rules": [
        "no scores: prose is generated from the same numbers it describes",
        "contradictory evidence is a required field; validate_profile rejects a profile without it "
        "and render_markdown refuses to render it",
        "degrade honestly: missing trial support / hiring / sparse months are stated, not dropped",
    ],
    "profiles": {
        "medtronic": {"events": 299, "tracks": 24, "momentum": "rising (90 vs 66)",
                      "trial_supported_tracks": "14/24", "contradictions": 2},
        "ge_healthcare": {"events": 274, "tracks": 5, "momentum": "stable",
                          "trial_supported_tracks": "n/a", "contradictions": 0},
        "philips": {"events": 224, "tracks": 11, "momentum": "rising",
                    "trial_supported_tracks": "n/a", "contradictions": 1},
        "draeger": {"events": 16, "tracks": 2, "momentum": "stable",
                    "trial_supported_tracks": "n/a", "contradictions": 1,
                    "note": "thin evidence - the profile states this rather than scoring it"},
        "mindray": {"events": 82, "tracks": 3, "momentum": "rising",
                    "trial_supported_tracks": "n/a", "contradictions": 1},
    },
    "selfcheck": "experiments/b027/selfcheck.py - 5/5 profiles pass",
}
state["established_findings"] = state["established_findings"] + [
    "UNDERSTAND: seven-field company technology profiles are now generated for all five mandated "
    "deep cases from holdings alone (no new data), with contradictory evidence as a required field",
    "UNDERSTAND: automated self-check re-derives every number the Markdown states from the JSON; "
    "5/5 profiles pass and rendering is deterministic",
]
state["next_actions"] = [
    "extend profiles beyond the five deep cases to the full curated roster and freeze a dated "
    "snapshot set (rolling-origin prerequisite)",
    "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
    "wire the detection frontier (cycle 3c) into the profile's momentum field so 'change' means a "
    "calibrated detection rather than a rate ratio",
    "do not resume hiring probing (structural limit, D-031); patents only if a route opens",
]
PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
