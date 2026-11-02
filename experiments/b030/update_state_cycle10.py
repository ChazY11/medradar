"""Update research/STATE.json for cycle 10 (hiring coverage correction)."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("research/STATE.json")
state = json.loads(PATH.read_text(encoding="utf-8"))

state["updated_at"] = "2026-11-02T21:10:00+08:00"
state["phase"] = "hiring_coverage_corrected"
state["cycle"] = 12
state["last_completed_cycle"] = {
    "cycle": 10,
    "name": "hiring_coverage_correction",
    "branch": "research/change-detection-v1",
    "report": "experiments/b030/REPORT.md",
    "summary": "research/RESULTS/cycle10_hiring_v2_2026-11-02.md",
    "verdict": ("cycle 9's 'coverage too thin' was partly a collector bug (collapse=urlkey + "
                "limit/page does not page); corrected coverage is 11 companies with posting URLs "
                "and 6 with >=24 months. The pre-registered lag test is still UNRUN (3 usable "
                "companies), not answered."),
}
state["hiring_lane"] = {
    "status": "CORRECTED COVERAGE - lag question still unrun (power, not depth)",
    "source": "Wayback Machine CDX API (public archive, index only, keyless)",
    "collector_bug": ("cycle 9 combined collapse=urlkey with limit+page pagination, which does not "
                      "page on this endpoint, so most of the archive was invisible and the "
                      "conclusion 'archive depth is the limit' was an artefact"),
    "panel_v2": "experiments/b030/hiring_panel_v2.json",
    "coverage_v2": {"companies_probed": 16, "companies_with_postings": 11,
                    "companies_with_24plus_months": 6, "companies_with_50plus_postings": 9,
                    "truncated_hosts": ["medtronic", "bd", "boston_scientific", "stryker"],
                    "no_coverage": ["philips", "draeger", "mindray", "zimmer_biomet", "masimo"]},
    "depth_evidence": "experiments/b030/host_depth.json",
    "lag_test": {"panel": "experiments/b030/lag_analysis_v2.json",
                 "usable_companies": ["bd", "boston_scientific", "stryker"],
                 "result": "every value inside the null band; sign uninterpretable; UNRUN not null"},
    "remaining_blockers": ["statistical power (3 usable companies)",
                           "board discovery for 5 firms incl. 2 mandated focus companies",
                           "platform-migration audit before any level-shift claim"],
}
state["established_findings"] = [
    finding for finding in state["established_findings"]
    if "hiring coverage is thin" not in finding
] + [
    "OBSERVE: the Wayback hiring lane covers 11 of 16 probed device firms with posting URLs and 6 "
    "with >=24 months (Boston Scientific 4,999 postings/123 months; Stryker 8,839/90; Medtronic "
    "5,107/60; BD 4,709/68) - cycle 9's 'coverage too thin' was a collector pagination bug",
    "OBSERVE: the pre-registered hiring/regulatory lag test remains UNRUN - 3 usable companies, all "
    "values inside the null band, negative sign uninterpretable (capture-gap confound)",
    "OBSERVE: 5 probed firms still have no archived board (Philips, Draeger, Mindray, Zimmer Biomet, "
    "Masimo); 4 firms hit the per-host cap so their series are lower bounds",
    "METHOD: a negative conclusion about data availability is as falsifiable as a positive claim; "
    "the measurement must be checked before the conclusion is carried forward",
]
state["blockers"] = [
    "hiring lag question: statistical power (3 usable companies) and board discovery for 5 firms "
    "(B-048)",
    "independent change confirmation: trial lane exists but is too sparse at cell level (cycle 5)",
    "patents: no key and no accessible bulk route (B-031)",
    "B-015 matured-forecast calibration blocked on wall-clock (windows close 2027-10)",
]
state["next_actions"] = [
    "B-048: career-board discovery for the five uncovered firms (Philips, Draeger, Mindray, Zimmer "
    "Biomet, Masimo), two of them mandated focus companies",
    "B-027: company technology-profile engine (Understand layer; independent of a positive "
    "association result)",
    "re-run the pre-registered lag test only when enough firms clear the unchanged floor",
    "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
]
PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"],
      "findings:", len(state["established_findings"]))
