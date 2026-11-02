"""Update research/STATE.json for cycle 7 (retraction of the entry-wave finding)."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("research/STATE.json")
state = json.loads(PATH.read_text(encoding="utf-8"))

state["updated_at"] = "2026-11-02T17:20:00+08:00"
state["phase"] = "entry_definition_repaired"
state["cycle"] = 9
state["last_completed_cycle"] = {
    "cycle": 7,
    "name": "entry_definition_control_and_retraction",
    "branch": "research/change-detection-v1",
    "report": "experiments/detect_v1/compare_entry_specs.py",
    "summary": "research/RESULTS/cycle7_retraction_2026-11-02.md",
    "verdict": ("the cycle-6 ivd_immuno entry wave is RETRACTED: 79% of entries were first-ever "
                "appearances of a legal entity, not established firms entering; under the "
                "prior-filer control ivd_immuno collapses (p=1.0) and the surviving track becomes "
                "specification-dependent (ivd_molecular on 5 entries). No track has a "
                "specification-stable wave."),
}
state["retraction"] = {
    "retracts": "the ivd_immuno positive finding recorded in cycle 6 / D-024",
    "reason": ("entry events were scored for cells whose entity was not in the risk set: 3,804 of "
               "4,814 entries (79%) were first-ever appearances of a legal entity in the lane"),
    "control": "--require-prior-filer: entry counts only if the entity had an event in another "
               "track before the entry month",
    "evidence": {
        "ivd_immuno": {"all_events": {"entries": 49, "p": 0.0055},
                       "churn": {"entries": 40, "p": 0.0010},
                       "prior_filer": {"entries": 8, "p": 1.0},
                       "prior_filer_churn": {"entries": 5, "p": 1.0}},
        "ivd_molecular": {"prior_filer": {"entries": 5, "p": 0.0025},
                          "note": "n=5 after being p=0.69 with 68 entries - specification noise"},
        "aesthetics": {"p_range": [0.0070, 0.0150], "fdr": "fails in every specification",
                       "status": "candidate only"},
        "firm_bursts": "0 rejected in every specification",
    },
}
state["measurement_rule"] = (
    "most 'entry' events in this lane are first appearances of legal entities, not established "
    "firms entering new technology areas; an entry study must state which of the two it measures, "
    "because mixing them manufactures waves")
state["established_findings"] = [
    finding for finding in state["established_findings"]
    if "ivd_immuno shows FDR-controlled" not in finding
    and "medical_ai's apparent entry wave was partly" not in finding
] + [
    "OBSERVE: 79% of raw entry events are first appearances of a legal entity; firm-level entry "
    "requires the prior-filer control, which leaves 1,010 of 4,814 events",
    "OBSERVE: NO device track has a specification-stable industry entry wave (ivd_immuno collapses "
    "under the prior-filer control; ivd_molecular rejects on 5 entries; aesthetics fails FDR in "
    "every specification)",
    "OBSERVE: medical_ai's apparent entry wave was partly taxonomy churn (p 0.0040 -> 0.0365)",
    "OBSERVE: no firm shows multi-track entry bursts (0 of 46-60 in every specification)",
]
state["next_actions"] = [
    "B-046: split-sample pre-registered test of the aesthetics candidate (fix the track now, "
    "estimate on an early window, test on a held-out later window without touching the threshold)",
    "B-030: attempt a lawful, point-in-time hiring source (densest remaining independent signal)",
    "B-031: patents via bulk files or a key",
    "B-039: fix the OBSERVE deployment resolution and re-run the width sweep there",
    "B-027: company technology-profile engine (Understand layer)",
]
PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"],
      "findings:", len(state["established_findings"]))
