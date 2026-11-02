"""Update research/STATE.json for cycle 6 (entry-cohort analysis)."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("research/STATE.json")
state = json.loads(PATH.read_text(encoding="utf-8"))

state["updated_at"] = "2026-11-02T16:20:00+08:00"
state["phase"] = "understand_positive_signal_case_study"
state["cycle"] = 8
state["last_completed_cycle"] = {
    "cycle": 6,
    "name": "entry_cohort_unit_of_analysis",
    "branch": "research/change-detection-v1",
    "report": "experiments/detect_v1/entries.log",
    "summary": "research/RESULTS/cycle6_entries_2026-11-02.md",
    "verdict": ("entry events solve the density ceiling (4,814 events); after controlling for "
                "risk-set size and product-code churn, ONE track shows FDR-significant industry "
                "entry clustering (ivd_immuno, p=0.0010, strengthened by the churn control), "
                "medical_ai did not survive, and no firm shows entry bursts (0/60)"),
}
state["entry_cohort"] = {
    "design": "research/DECISIONS.md D-024 (constants fixed in the module before the first run)",
    "unit": "technology-entry event: first observed touch of a track by a company",
    "entries_all_events": 4814,
    "entries_churn_controlled": 4590,
    "churn_control": "dropped 467 events on 506 product codes first seen 2022-01 or later",
    "industry_clustering": {
        "all_events": {"tracks_rejected": 0, "tests": 38, "smallest_p": 0.0040,
                       "smallest_track": "medical_ai"},
        "churn_controlled": {"tracks_rejected": 1, "tests": 36,
                             "rejected": ["ivd_immuno"], "p": 0.0010, "z": 4.73,
                             "second": "aesthetics p=0.0070",
                             "medical_ai_p": 0.0365},
    },
    "firm_clustering": {"entities_rejected": 0, "tests": 60,
                        "reading": "no detectable multi-track entry bursts (strategic redirection)"},
    "first_positive_finding": (
        "ivd_immuno shows an industry-wide wave of first entries that survives risk-set "
        "conditioning and taxonomy-churn control; single rejection under 10% FDR, so suggestive "
        "not established, but the churn control strengthens rather than weakens it"),
}
state["established_findings"] = state["established_findings"] + [
    "OBSERVE: the entry-cohort unit removes the density ceiling (4,814 entry events vs ~0.2 "
    "events per cell-month) and makes the industry-wave question testable",
    "OBSERVE: ivd_immuno shows FDR-controlled industry entry clustering that STRENGTHENS under "
    "product-code churn control (p 0.0055 -> 0.0010) - the first positive finding that survived "
    "its own controls",
    "OBSERVE: medical_ai's apparent entry wave was partly taxonomy churn (p 0.0040 -> 0.0365 "
    "after removing late-created product codes)",
    "OBSERVE: no firm shows multi-track entry bursts (0 of 60), so simultaneous-entry is not a "
    "detectable signature of strategic redirection at this granularity",
]
state["next_actions"] = [
    "B-043: ivd_immuno entry-wave case study - which firms entered in 2019 and 2023-24, with what "
    "evidence, and is the wave visible in the independent device-trial lane (B-040)?",
    "B-030: attempt a lawful, point-in-time hiring source",
    "B-031: patents via bulk files or a key",
    "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
    "B-027: company technology-profile engine (Understand layer)",
]
PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
