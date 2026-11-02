"""Update research/STATE.json for the cycle-3b correction (deterministic, no hand editing)."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("research/STATE.json")
state = json.loads(PATH.read_text(encoding="utf-8"))

state["updated_at"] = "2026-11-02T12:10:00+08:00"
state["phase"] = "observe_detection_resolution_sweep"
state["cycle"] = 4
state["last_completed_cycle"] = {
    "cycle": "3b",
    "name": "detection_sensitivity_and_correction",
    "branch": "research/change-detection-v1",
    "report": "experiments/detect_v1/REPORT.md",
    "summary": "research/RESULTS/cycle3b_correction_2026-11-02.md",
    "verdict": ("detector ranking is resolution-dependent: the naive alert wins monthly but the "
                "Poisson Bayes factor wins quarterly (+0.104 [+0.068,+0.140]); maintenance and "
                "churn sensitivities confirm the monthly result"),
}
state["correction_to_cycle3"] = {
    "what": ("cycle 3's headline 'the simple baseline is not beaten' is monthly-resolution-specific "
             "and must not be stated generally"),
    "evidence": "experiments/detect_v1/benchmark.json levels track_quarterly / track_no_special / track_stable_codes",
    "pre_registered": "DECISIONS D-017; outcome recorded in D-018",
    "reproduction_check": "experiments/detect_v1/check_frozen_reproduction.py -> PASS (default panels identical to the frozen frontier)",
}
state["layer_status"]["observe"]["measured"] = (
    "monthly (104 cells): best detector recovers 0.223 of injected sustained shifts; "
    "quarterly: Bayes factor 0.129, naive 0.025. Detector ranking is resolution-dependent. "
    "2x shifts remain undetectable at any honest budget; data density is the binding constraint.")
state["layer_status"]["observe"]["gaps"] = [
    "hiring not collected",
    "patents not collected",
    "8-K CIK linking missing (19,616 events)",
    "no independent source to confirm a detected change",
    "no seasonal adjustment; lane-wide boundary volume artifacts",
    "Special 510(k)s (15.01%) are not separated in the primary panel",
]
state["next_actions"] = [
    "B-038: bin-width sweep (1/2/3/4/6 months) to test whether the resolution crossover tracks the expected count per bin",
    "B-033: find a genuinely independent confirmation source (the Understand-layer entry condition)",
    "B-037: seasonal and lane-volume artifact adjustment",
    "B-025: cross-company anomaly detection (do competitors move together?)",
    "B-027: company technology-profile engine with the seven required evidence fields",
]
state["established_findings"] = [
    f for f in state["established_findings"]
    if not f.startswith("OBSERVE:")
] + [
    "OBSERVE: at monthly resolution the naive rate-multiplier is not beaten by likelihood detectors "
    "(0.223 vs 0.181/0.122/0.112 at a 2% budget)",
    "OBSERVE: at quarterly resolution the ranking reverses - Poisson Bayes factor 0.129 vs naive "
    "0.025, paired +0.104 [+0.068,+0.140]; detector choice is resolution-dependent",
    "OBSERVE: removing Special 510(k)s and masking late product codes do not change the monthly ranking",
    "OBSERVE: independent confirmation of a detected change is BLOCKED - no second source exists in the spine",
]
PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
