"""Update research/STATE.json for cycle 11 (B-048 board discovery closes with a measured limit)."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("research/STATE.json")
state = json.loads(PATH.read_text(encoding="utf-8"))

state["updated_at"] = "2026-11-02T22:40:00+08:00"
state["phase"] = "understand_layer_priority"
state["cycle"] = 13
state["last_completed_cycle"] = {
    "cycle": 11,
    "name": "hiring_board_discovery_limit",
    "branch": "research/change-detection-v1",
    "report": "experiments/b030/REPORT.md",
    "summary": "research/RESULTS/cycle11_b048_2026-11-02.md",
    "verdict": ("board discovery found a real Philips board (669 postings / 38 months) but it fails "
                "the silence criterion; Dräger, Mindray and Masimo have no archived job-level URLs. "
                "The hiring lane covers only 1 of the 5 mandated deep-case companies (Medtronic), "
                "which is a structural limit, not an outstanding search."),
}
state["hiring_lane"].update({
    "coverage_v3": {"companies_probed": 16, "companies_with_postings": 13,
                    "companies_with_24plus_months": 7, "companies_with_50plus_postings": 10,
                    "new_boards": {"philips": "philips.taleo.net/careersection/* (669/38 months)",
                                   "zimmer_biomet": "careers.zimmer.com/* (4/4 months)"}},
    "mandated_focus_coverage": {
        "mandated": ["medtronic", "ge_healthcare", "philips", "draeger", "mindray"],
        "covered_with_usable_series": ["medtronic"],
        "why_not": {
            "ge_healthcare": "independent filer only since 2023; archived board yields 1 URL",
            "philips": "real board but 38 of 119 months; fails the silence criterion",
            "draeger": "only marketing career pages archived; no job-level URLs",
            "mindray": "only marketing career pages archived; no job-level URLs",
        },
        "consequence": ("the hiring lane cannot serve the mandated deep-case requirement; those "
                        "cases need filings, device trials and publications instead"),
    },
    "lag_test": {"panel": "experiments/b030/lag_analysis_v2.json",
                 "usable_companies": ["bd", "boston_scientific", "stryker"],
                 "result": "UNRUN - 3 companies, all values inside the null band"},
})
state["established_findings"] = state["established_findings"] + [
    "OBSERVE: board discovery added a real Philips hiring board (669 postings, 38 months) but it "
    "fails the pre-declared silence criterion; Dräger, Mindray and Masimo have no archived job-level "
    "URLs at all",
    "OBSERVE: the hiring lane covers 1 of the 5 mandated deep-case companies (Medtronic); GE "
    "HealthCare's independence dates from 2023, Philips is archived too sparsely, Dräger/Mindray post "
    "on unarchived systems",
    "DESIGN: the mandated deep cases must be served by filings + device trials + publications, not by "
    "the hiring lane",
]
state["blockers"] = [
    "hiring lag question: unrun - 3 usable companies; the remaining firms are unreachable from this "
    "source (D-031), so the limit is now structural",
    "independent change confirmation: trial lane exists but is too sparse at cell level (cycle 5)",
    "patents: no key and no accessible bulk route (B-031)",
    "B-015 matured-forecast calibration blocked on wall-clock (windows close 2027-10)",
]
state["next_actions"] = [
    "B-027: company technology-profile engine (Understand layer) - assemble filings, tracks, trials "
    "and entries into explicit, contradictory-evidence-aware statements for the deep-case companies",
    "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
    "do not resume hiring probing; the remaining firms are structurally unreachable (D-031)",
    "B-031: revisit patents only if an accessible bulk route is identified",
]
PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
