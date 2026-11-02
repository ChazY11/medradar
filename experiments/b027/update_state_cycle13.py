"""Update research/STATE.json for cycle 13 (calibrated momentum)."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("research/STATE.json")
state = json.loads(PATH.read_text(encoding="utf-8"))

state["updated_at"] = "2026-11-03T00:50:00+08:00"
state["phase"] = "understand_calibrated_momentum"
state["cycle"] = 15
state["last_completed_cycle"] = {
    "cycle": 13,
    "name": "calibrated_momentum",
    "branch": "research/change-detection-v1",
    "report": "experiments/b027/profiles.json",
    "summary": "research/RESULTS/cycle13_momentum_2026-11-02.md",
    "verdict": ("momentum is now an exact binomial rate-ratio test at alpha=0.05 with a reported MDE; "
                "THREE of five cycle-12 momentum readings did not survive (Medtronic 90v66 p=0.065 "
                "MDE 1.57x, Mindray 18v12 p=0.362, GE HealthCare 57v48 p=0.435); only Philips' "
                "doubling survives (73v36 p=0.001)"),
}
state["understand_layer"]["momentum_test"] = {
    "method": "two-sided exact binomial test of the recent count given the total (Poisson rate-ratio "
              "under a constant-rate null)",
    "alpha": 0.05,
    "power_for_mde": 0.80,
    "mde_definition": "smallest rate ratio detectable at alpha and 80% power given the observed "
                      "counts; reported whenever the test does not reject",
    "results": {
        "medtronic": {"recent": 90, "prior": 66, "ratio": 1.36, "p": 0.065, "mde": 1.57,
                      "detected": False, "supersedes": "was 'rising' in cycle 12"},
        "philips": {"recent": 73, "prior": 36, "ratio": 2.03, "p": 0.001, "mde": 1.77,
                    "detected": True, "direction": "increasing"},
        "ge_healthcare": {"recent": 57, "prior": 48, "ratio": 1.19, "p": 0.435, "mde": 1.73,
                          "detected": False},
        "mindray": {"recent": 18, "prior": 12, "ratio": 1.50, "p": 0.362, "mde": 2.84,
                    "detected": False, "supersedes": "was 'rising' in cycle 12"},
        "draeger": {"recent": 10, "prior": 10, "ratio": 1.00, "p": 1.000, "mde": 3.50,
                    "detected": False},
    },
    "reading_rule": "a non-detection is never reported as stability: the MDE must accompany it",
}
state["established_findings"] = state["established_findings"] + [
    "UNDERSTAND: momentum is a calibrated test (exact binomial, alpha=0.05) with a reported minimum "
    "detectable ratio; 3 of 5 cycle-12 momentum readings were noise and were overturned inside the "
    "product by design",
    "UNDERSTAND: only Philips' activity increase survives (73 vs 36, p=0.001); Medtronic's +36% has "
    "p=0.065 and an MDE of 1.57x, so the data cannot distinguish it from a constant rate",
]
state["next_actions"] = [
    "B-049: extend profiles to the full curated roster and freeze a dated snapshot set (point-in-time "
    "artifact prerequisite for any rolling-origin evaluation)",
    "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
    "use the cycle-3c detection frontier, not only the 24-month rate test, for the per-track change "
    "field so 'change' is calibrated against the controlled-truth benchmark",
    "do not resume hiring probing (structural limit, D-031); patents only if a route opens",
]
PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
