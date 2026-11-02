"""Update research/STATE.json for cycle 8 (split-sample test; entry thread closed as null)."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("research/STATE.json")
state = json.loads(PATH.read_text(encoding="utf-8"))

state["updated_at"] = "2026-11-02T18:30:00+08:00"
state["phase"] = "data_acquisition_priority"
state["cycle"] = 10
state["last_completed_cycle"] = {
    "cycle": 8,
    "name": "split_sample_test_and_thread_closure",
    "branch": "research/change-detection-v1",
    "report": "experiments/detect_v1/aesthetics_holdout.json",
    "summary": "research/RESULTS/cycle8_holdout_2026-11-02.md",
    "verdict": ("no entry-clustering claim survives: the aesthetics candidate is not nominated by a "
                "clean early-window design and its apparent split-sample replication used the "
                "holdout; under the clean design 3 tracks nominated and 0 confirmed. The "
                "entry-clustering thread is closed as a null."),
}
state["entry_thread_closure"] = {
    "status": "CLOSED AS NULL",
    "candidates": {
        "ivd_immuno": "failed as entity appearance (79% of raw entries were first-ever legal entities)",
        "aesthetics": ("failed as post-hoc selection: not nominated by a clean early-window design; "
                       "apparent replication used the holdout"),
    },
    "clean_design": {
        "nomination": "estimation window only (2016-11..2022-12), BH q=0.10 over 30 tracks",
        "confirmation": "untouched holdout 2023-01..2026-09 at alpha=0.05",
        "nominated": ["ivd_molecular", "medical_ai", "vascular_access"],
        "confirmed": [],
        "power": {"holdout_entries": 13,
                  "detection_probability_at_wave_share": {"0.3": 0.25, "0.5": 0.52, "0.7": 0.95}},
    },
    "reading": ("no evidence of replication, not proven absence; the holdout can rule out strong "
                "clustering only"),
    "why_stop": ("three cycles of re-specifying clustering tests on one sparse filing stream is the "
                 "unlimited algorithm trial-and-error the mission forbids; the limit is information "
                 "content, not the statistic"),
}
state["established_findings"] = [
    finding for finding in state["established_findings"]
    if "NO device track has a specification-stable industry entry wave" not in finding
] + [
    "OBSERVE: the entry-clustering thread is CLOSED AS NULL - under a clean split-sample design 3 "
    "tracks are nominated and 0 replicate; no device track shows an industry entry wave",
    "OBSERVE: the aesthetics candidate failed as post-hoc selection (its apparent replication used "
    "the holdout; it is not nominated by the early window)",
    "OBSERVE: holdout power for entry clustering is 0.25/0.52/0.95 at 30/50/70% wave concentration, "
    "so the null excludes strong clustering only",
    "METHOD: a holdout cannot confirm a hypothesis that was nominated with its help; nomination and "
    "confirmation must use disjoint data",
]
state["next_actions"] = [
    "B-030: attempt a lawful, point-in-time hiring source - the densest remaining independent signal "
    "and the one that would change information content rather than the estimator",
    "B-031: patents via bulk files or a key (second declared gap)",
    "B-027: company technology-profile engine (Understand layer, does not depend on a positive "
    "clustering result)",
    "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
    "stop re-specifying clustering tests on the current lane (recorded reason in D-027)",
]
PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"],
      "findings:", len(state["established_findings"]))
