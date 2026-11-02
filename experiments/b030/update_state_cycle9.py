"""Update research/STATE.json for cycle 9 (hiring lane feasibility)."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("research/STATE.json")
state = json.loads(PATH.read_text(encoding="utf-8"))

state["updated_at"] = "2026-11-02T19:40:00+08:00"
state["phase"] = "data_acquisition_blocked_on_coverage"
state["cycle"] = 11
state["last_completed_cycle"] = {
    "cycle": 9,
    "name": "hiring_lane_feasibility",
    "branch": "research/change-detection-v1",
    "report": "experiments/b030/REPORT.md",
    "summary": "research/RESULTS/cycle9_hiring_2026-11-02.md",
    "verdict": ("a lawful, keyless, genuinely historical hiring proxy was built from the Wayback "
                "CDX archive, but only 2 of 16 probed firms pass the pre-declared usability floor, "
                "so the company-level lag question is unrun rather than answered"),
}
state["hiring_lane"] = {
    "status": "FEASIBILITY PARTIAL - source obtained, coverage too thin",
    "source": "Wayback Machine CDX API (public archive, index only, keyless)",
    "rejected_routes": {
        "patentsview_bulk_s3": "403 Forbidden - credentials required",
        "common_crawl_index": "persistent 504 Gateway Time-out",
    },
    "proxy": "distinct job-posting URLs whose earliest archive capture falls in a month",
    "panel": "experiments/b030/hiring_panel.json",
    "coverage": {"firms_probed": 16, "firms_with_postings": 6,
                 "firms_usable": 2, "usable_keys": ["bd", "boston_scientific"]},
    "why_not_a_result": ("the pre-registered lag test rests on 2 companies and the proxy's sign is "
                         "uninterpretable because capture gaps and regulatory gaps can align"),
    "deliberately_not_done": ("the usability floor was NOT loosened to raise the sample - that is the "
                              "specification search closed by D-027"),
    "unblock_path": "B-047: per-company career-domain mapping + platform-change audit + CDX deep-paging fix",
}
state["established_findings"] = [
    finding for finding in state["established_findings"]
    if "attempt a lawful" not in finding
] + [
    "OBSERVE: a lawful, keyless, genuinely historical hiring proxy exists (Wayback CDX index) and a "
    "bounded collector builds a monthly panel from it",
    "OBSERVE: hiring coverage is thin - 2 of 16 probed device firms pass the pre-declared usability "
    "floor; the company-level hiring/regulatory lag question is unrun, not answered",
    "ACCESS: PatentsView bulk is 403 (key required) and the Common Crawl index returns persistent 504",
]
state["blockers"] = [
    "hiring lag question: coverage too thin (B-030 blocked; unblock via B-047 career-domain mapping)",
    "independent change confirmation: trial lane exists but is too sparse at cell level (cycle 5)",
    "patents: no key and no accessible bulk route (B-031)",
    "B-015 matured-forecast calibration blocked on wall-clock (windows close 2027-10)",
]
state["next_actions"] = [
    "B-047: per-company career-domain mapping + platform-change audit + CDX deep-paging fix, then "
    "run the pre-registered hiring lag test",
    "B-027: company technology-profile engine (Understand layer; does not depend on a positive "
    "clustering or hiring result)",
    "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
    "B-031: revisit patents only if an accessible bulk route is identified",
]
PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"],
      "findings:", len(state["established_findings"]))
