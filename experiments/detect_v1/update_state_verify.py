"""Add the independent-verification outcome to research/STATE.json."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("research/STATE.json")
state = json.loads(PATH.read_text(encoding="utf-8"))
state["updated_at"] = "2026-11-02T12:40:00+08:00"
state["correction_to_cycle3"]["independent_verification"] = {
    "report": "experiments/detect_v1_verify/REPORT.md",
    "reproduction": "PASS - 2844 of 2844 checks match benchmark.json (every frontier point)",
    "monthly_robustness": ("the monthly negative survives ramp, transient and heterogeneous "
                           "injections at the 2% budget; no likelihood win is interval-confirmed "
                           "on the 1/3/5% frontier"),
    "prose_correction": ("an earlier claim that the naive detector was strongest at every budget "
                         "was false and has been corrected (DECISIONS D-019)"),
    "operational_reversal": ("reading a 6-month surge as a nuisance to reject, the Bayes factor "
                             "declares a sustained change on 0.011 vs 0.168 for naive "
                             "(+0.157 [+0.119,+0.196])"),
}
state["established_findings"] += [
    "OBSERVE: independent reproduction of the detection benchmark PASSES 2844/2844 checks",
    "OBSERVE: the monthly negative is robust to injection shape (ramp/transient/heterogeneous) but "
    "reverses under quarterly aggregation - statements about the best detector require budget, "
    "resolution and cost model",
    "OBSERVE: on nuisance rejection (not declaring a sustained change for a 6-month surge) the "
    "Bayes factor beats naive by +0.157 [+0.119,+0.196]",
]
state["next_actions"] = [
    "B-038: bin-width sweep (1/2/3/4/6 months) to test whether the resolution crossover tracks the expected count per bin",
    "B-033: find a genuinely independent confirmation source (the Understand-layer entry condition)",
    "B-037: seasonal and lane-volume artifact adjustment",
    "B-025: cross-company anomaly detection (do competitors move together?)",
    "B-027: company technology-profile engine with the seven required evidence fields",
]
PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATE.json updated; findings:", len(state["established_findings"]))
