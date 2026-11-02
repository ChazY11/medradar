"""Add the entity-level confirmation claims (cycle 23) and update STATE/BACKLOG."""
from __future__ import annotations

import json
from pathlib import Path

CLAIMS = Path("papers/CLAIMS.json")
BUILD = Path("papers/build_claims.py")
STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

EXTRA = [
    ("W1", "entity-level balanced accuracy", "0.594", "research/DECISIONS.md", "0.594"),
    ("W2", "entity-level sustained precision", "0.917", "research/DECISIONS.md", "0.917"),
    ("W3", "entity-level sustained base rate", "0.705", "research/DECISIONS.md", "0.705"),
    ("W4", "entity-level ramp recall", "0.117", "research/DECISIONS.md", "0.117"),
    ("W5", "eligible entity cells", "191", "research/DECISIONS.md", "191"),
]


def update_claims() -> None:
    payload = json.loads(CLAIMS.read_text(encoding="utf-8"))
    by_id = {claim["id"]: claim for claim in payload["claims"]}
    for claim_id, statement, value, source, needle in EXTRA:
        by_id[claim_id] = {"id": claim_id, "statement": statement, "value": value,
                           "source": source, "source_needle": needle}
    payload["claims"] = [by_id[key] for key in sorted(by_id)]
    CLAIMS.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8", newline="\n")

    text = BUILD.read_text(encoding="utf-8")
    if '"W1"' not in text:
        block = "\n".join(
            f'    ("{claim_id}", "{statement}", "{value}", "{source}", "{needle}"),'
            for claim_id, statement, value, source, needle in EXTRA)
        anchor = [line for line in text.splitlines() if '"V2"' in line][0]
        text = text.replace(anchor, anchor + "\n    # ---- entity-level confirmation (cycle 23)\n" + block, 1)
        BUILD.write_text(text, encoding="utf-8", newline="\n")
    print(f"claims: {len(payload['claims'])}")


def update_state() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T10:40:00+08:00"
    state["phase"] = "promotion_rule_confirmed_two_units"
    state["cycle"] = 25
    state["last_completed_cycle"] = {
        "cycle": 23,
        "name": "entity_level_confirmation",
        "branch": "research/change-detection-v1",
        "report": "experiments/b026/confirm_entity_cells.json",
        "summary": "research/RESULTS/cycle23_entity_confirm_2026-11-03.md",
        "verdict": ("the promotion rule CONFIRMS at the legal-entity unit too: balanced accuracy 0.594 "
                    "(CI 0.583-0.616), sustained precision 0.917 (CI 0.909-0.941) vs a 0.705 base rate, "
                    "essentially identical to the company-level result - so it is not an aggregation "
                    "artefact; entity cells nest inside company cells, so this is not an independent "
                    "sample, and ramp recall stays at 0.117"),
    }
    detection = state["detection_layer"]
    detection["confirmation_entity_level"] = {
        "artifact": "experiments/b026/confirm_entity_cells.json",
        "decision": "research/DECISIONS.md D-047 (pre-registration), D-048 (outcome)",
        "entity_cells": 6841, "eligible": 191, "scored_alerts": 1196,
        "balanced_accuracy": 0.594, "ci": [0.583, 0.616],
        "sustained_precision": 0.917, "precision_ci": [0.909, 0.941],
        "sustained_base_rate": 0.705, "spike_recall": 0.785, "ramp_recall": 0.117,
        "verdict": "CONFIRMED AT ENTITY LEVEL",
        "reading": ("not an aggregation artefact; still not an independent sample because entity cells "
                    "nest inside company cells"),
    }
    state["established_findings"] = state["established_findings"] + [
        "DETECT: the promotion rule confirms at the legal-entity unit with essentially identical numbers "
        "(balanced accuracy 0.594 vs 0.584; sustained precision 0.917 vs 0.914), so it is not an artefact "
        "of the curated-company unit",
        "DETECT: entity cells nest inside company cells, so the confirmation narrows the caveat rather than "
        "removing it; three-way shape recovery still fails (ramp recall 0.117 at both units)",
    ]
    state["next_actions"] = [
        "decide the promotion policy explicitly (manual review vs automated) before wiring D-043",
        "freeze a new dated snapshot carrying the deployment block so point-in-time diffs include alerts",
        "second-domain validation before calling any of this portable",
        "consider whether ramp detection needs a longer confirmation window and report the trade-off",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-055" in text:
        start = text.index("  - id: B-055")
        following = text.find("  - id:", start + len("  - id: B-055"))
        end = len(text) if following == -1 else following
        block = text[start:end]
        if "status: todo" in block:
            text = text.replace(block, block.replace("status: todo", "status: done", 1), 1)
            BACKLOG.write_text(text, encoding="utf-8", newline="\n")
            print("B-055 marked done")


def main() -> int:
    update_claims()
    update_state()
    print("state and backlog updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
