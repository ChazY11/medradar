"""Update paper, claims, STATE and BACKLOG for cycle 34 (end-to-end pipeline evaluation)."""
from __future__ import annotations

import json
from pathlib import Path

PAPER = Path("papers/PAPER_v1.md")
CLAIMS = Path("papers/CLAIMS.json")
BUILD = Path("papers/build_claims.py")
STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

PAPER_ADDITION = """*End-to-end check, added after the component results.* Every component above was validated in
isolation; the pipeline as a whole was then evaluated on real history (quarterly origins 2019-Q1 … 2024-Q4,
detector z ≥ 3.5, the confirmed two-quarter rule, outcome = activity four quarters later). Of **68 alerts**, 35 were
promoted and 33 were not. Promoted alerts persisted **0.800** of the time (95 % CI 0.652–0.917), unpromoted ones
**0.667**, and comparable non-alert cell-quarters **0.373**. The alert therefore carries real information about
persistence — but the **marginal** contribution of the promotion filter is **not established**: the difference is
**+0.133** with an interval of **−0.074 … 0.344**. With only 33 unpromoted alerts the test is underpowered,
because the filter exists precisely to make spikes rare. The filter remains justified by its shape-classification
performance on injected changes, not by this test, and the paper reports both so that neither is read alone.

"""

EXTRA = [
    ("BB1", "pipeline promoted persistence rate", "0.800", "research/DECISIONS.md", "0.800"),
    ("BB2", "pipeline unpromoted persistence rate", "0.667", "research/DECISIONS.md", "0.667"),
    ("BB3", "pipeline control persistence rate", "0.373", "research/DECISIONS.md", "0.373"),
    ("BB4", "pipeline promotion difference", "0.133", "research/DECISIONS.md", "0.133"),
]

TASK = """  - id: B-067
    layer: evaluate
    priority: P1
    title: End-to-end rolling-origin evaluation of the promotion pipeline
    status: done
    owner: lead
    depends_on: [B-064]
    acceptance: >
      Pre-registered design (D-064): quarterly origins 2019-Q1..2024-Q4, deployed detector, confirmed two-quarter
      rule, outcome = activity four quarters on. Result: 68 alerts (35 promoted, 33 unpromoted), control 4,594.
      P(persisted) promoted 0.800 (0.652-0.917), unpromoted 0.667, control 0.373; difference +0.133 with interval
      -0.074..0.344 -> NO ADDED VALUE by the pre-declared rule. Alerts carry information about persistence; the
      filter's marginal value is unestablished (underpowered: spikes are rare by design).


"""


def main() -> int:
    paper = PAPER.read_text(encoding="utf-8")
    anchor = "*What no window fixes.* A pre-registered sensitivity analysis over confirmation windows of 1–6 months found"
    if "*End-to-end check, added after the component results.*" not in paper:
        index = paper.find(anchor)
        if index == -1:
            print("paper anchor missing")
            return 1
        paper = paper[:index] + PAPER_ADDITION + paper[index:]
        PAPER.write_text(paper, encoding="utf-8", newline="\n")
        print("paper extended")

    payload = json.loads(CLAIMS.read_text(encoding="utf-8"))
    by_id = {claim["id"]: claim for claim in payload["claims"]}
    for claim_id, statement, value, source, needle in EXTRA:
        by_id[claim_id] = {"id": claim_id, "statement": statement, "value": value,
                           "source": source, "source_needle": needle}
    payload["claims"] = [by_id[key] for key in sorted(by_id)]
    CLAIMS.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8", newline="\n")

    build_text = BUILD.read_text(encoding="utf-8")
    if '"BB1"' not in build_text:
        block = "\n".join(
            f'    ("{claim_id}", "{statement}", "{value}", "{source}", "{needle}"),'
            for claim_id, statement, value, source, needle in EXTRA)
        anchor_line = [line for line in build_text.splitlines() if '"AA5"' in line][0]
        build_text = build_text.replace(
            anchor_line, anchor_line + "\n    # ---- pipeline evaluation (cycle 34)\n" + block, 1)
        BUILD.write_text(build_text, encoding="utf-8", newline="\n")

    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T21:40:00+08:00"
    state["phase"] = "pipeline_evaluated"
    state["cycle"] = 36
    state["last_completed_cycle"] = {
        "cycle": 34,
        "name": "pipeline_rolling_origin",
        "branch": "research/change-detection-v1",
        "report": "experiments/b067/promotion_rolling_origin.json",
        "summary": "research/RESULTS/cycle34_pipeline_2026-11-03.md",
        "verdict": ("end-to-end pipeline evaluation: alerts predict persistence (promoted 0.800, unpromoted 0.667, "
                    "control 0.373), but the promotion filter's MARGINAL value is not established (difference "
                    "+0.133, CI -0.074..0.344) - recorded as a documentation discipline, not a measured "
                    "predictive improvement"),
    }
    state["evaluation"] = state.get("evaluation", {})
    state["evaluation"]["pipeline_rolling_origin"] = {
        "artifact": "experiments/b067/promotion_rolling_origin.json",
        "decision": "research/DECISIONS.md D-064 (pre-registration), D-065 (outcome)",
        "alerts": 68, "promoted": 35, "unpromoted": 33, "control_cell_quarters": 4594,
        "rates": {"promoted": 0.800, "unpromoted": 0.667, "control": 0.373},
        "difference": 0.133, "difference_ci": [-0.074, 0.344],
        "verdict": "NO ADDED VALUE by the pre-declared rule",
        "reading": ("alerts carry information about persistence; the two-month filter's marginal contribution is "
                    "unestablished and underpowered because spikes are rare by design"),
    }
    state["established_findings"] = state["established_findings"] + [
        "EVALUATE: end-to-end, alerts persist far more than non-alert cell-quarters (0.80 / 0.67 vs 0.37) - the "
        "detector carries real information about persistence",
        "EVALUATE: the promotion filter's MARGINAL value is NOT established (difference +0.133, CI -0.074..0.344) "
        "with only 33 unpromoted alerts; it remains justified by shape-classification performance, not by this test",
    ]
    state["next_actions"] = [
        "run tools/round_end.py as the gate at the end of every round",
        "consider a second paper focused on the measurement rules and the two confirmations",
        "decide whether the promotion ledger should log relabelling events as an audit trail",
        "revisit the pipeline test only if a longer history becomes available",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-067" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-067 appended")
    print("updated; claims:", len(payload["claims"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
