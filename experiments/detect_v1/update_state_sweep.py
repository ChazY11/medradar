"""Update research/STATE.json for the bin-width sweep and the memory correction."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("research/STATE.json")
state = json.loads(PATH.read_text(encoding="utf-8"))

state["updated_at"] = "2026-11-02T13:05:00+08:00"
state["phase"] = "observe_deployment_calibration"
state["cycle"] = 5
state["last_completed_cycle"] = {
    "cycle": "3c",
    "name": "detector_memory_and_bin_width_sweep",
    "branch": "research/change-detection-v1",
    "report": "experiments/detect_v1/REPORT.md",
    "summary": "research/RESULTS/cycle3c_sweep_2026-11-02.md",
    "verdict": ("memory was parameterised in bins, so the quarterly winner was confounded; with "
                "calendar-matched memory the naive detector still collapses at quarterly "
                "resolution but the winner is the rolling z-score. The bin-width sweep puts the "
                "crossover at 2 months and shows the winner above it is NOT identifiable."),
}
state["correction_to_cycle3"]["correction_2"] = {
    "what": ("cycle 3b named the Bayes factor as the quarterly winner (+0.104). That was partly a "
             "72-month-baseline artefact: detector memory was in bins, not calendar months."),
    "fix": "make_detector rescales z-score window to 12 months and CUSUM/Bayes baseline to 24 months",
    "corrected_numbers": {"rolling_zscore": 0.147, "poisson_bayes_factor": 0.073,
                          "poisson_cusum": 0.065, "naive_multiplier": 0.025},
    "what_survives": "the quarterly reversal (naive collapses; all three likelihood detectors win)",
    "what_does_not": "the identity of the winner",
    "evidence": "experiments/detect_v1/benchmark.json track_quarterly; DECISIONS D-020",
}
state["bin_width_sweep"] = {
    "widths_months": [1, 2, 3, 4, 6],
    "crossover_months": 2,
    "crossover_expected_events_per_bin": 0.424,
    "naive_detection_by_width": [0.223, 0.007, 0.025, 0.004, 0.071],
    "winner_by_width": ["naive_multiplier", "poisson_cusum", "rolling_zscore",
                        "poisson_cusum", "rolling_zscore"],
    "conclusion": ("the naive rate-ratio test is resolution-fragile; the identity of the best "
                   "detector above the crossover is not identifiable at this sample size"),
    "artifacts": ["experiments/detect_v1/bin_sweep.json", "experiments/detect_v1/widths.json"],
}
state["established_findings"] = [
    finding for finding in state["established_findings"]
    if "quarterly resolution the ranking reverses" not in finding
] + [
    "OBSERVE: at quarterly resolution the naive detector collapses (0.025) and all three likelihood "
    "detectors beat it; the best is the rolling z-score (0.147), not the Bayes factor",
    "OBSERVE: bin-width sweep (1/2/3/4/6 months) puts the crossover at 2 months (~0.42 expected "
    "events per bin) and shows the winner above it alternates, so it is not identifiable",
    "OBSERVE: detector memory must be parameterised in calendar time - the first quarterly result "
    "was confounded by memory expressed in bins (D-020)",
]
state["next_actions"] = [
    "B-039: fix the deployment resolution for the OBSERVE layer and re-run the sweep there with "
    "calendar-parameterised memory before naming a detector",
    "B-033: find a genuinely independent confirmation source (the Understand-layer entry condition)",
    "B-037: seasonal and lane-volume artifact adjustment",
    "B-025: cross-company anomaly detection (do competitors move together?)",
    "B-027: company technology-profile engine with the seven required evidence fields",
]
PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
