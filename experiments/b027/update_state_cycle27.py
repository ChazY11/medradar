"""Update STATE.json and BACKLOG.yaml for cycle 27 (promotion ledger with attribution)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-060
    layer: understand
    priority: P1
    title: Promotion ledger with enforced attribution
    status: done
    owner: lead
    depends_on: [B-057]
    acceptance: >
      research/RESULTS/PROMOTIONS.md is an append-only ledger separate from the findings ledger; rows
      carry signer, timestamp, justification and policy version. build_promotion_record raises on an empty
      signer, missing justification, missing timestamp or a non-promotable verdict, so an unattributed
      promotion cannot be written. freeze_snapshot hashes the ledger as an input source so every future
      manifest ties profiles to the exact ledger. The Medtronic insulin_delivery alert is recorded
      PENDING_SIGNOFF because the programme cannot sign for a human.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T14:40:00+08:00"
    state["phase"] = "promotions_attributed"
    state["cycle"] = 29
    state["last_completed_cycle"] = {
        "cycle": 27,
        "name": "promotion_ledger",
        "branch": "research/change-detection-v1",
        "report": "research/RESULTS/PROMOTIONS.md",
        "summary": "research/RESULTS/cycle27_promotions_ledger_2026-11-03.md",
        "verdict": ("promotions now live in their own append-only ledger with enforced attribution (signer, "
                    "timestamp, justification); the logger refuses unsigned promotions and the ledger is "
                    "hashed into snapshot manifests; the one candidate promotion is left PENDING_SIGNOFF "
                    "because the programme cannot sign for a human"),
    }
    state["publication"]["promotion_policy"].update({
        "ledger": "research/RESULTS/PROMOTIONS.md (append-only, separate from findings)",
        "logger": "experiments/b027/log_promotion.py",
        "attribution_enforced": True,
        "manifest_attribution": "freeze_snapshot hashes the ledger as an input source (7 sources total)",
        "first_entry": {"id": "medtronic:insulin_delivery:2025-Q3", "verdict": "PENDING_SIGNOFF",
                        "reason": "the programme cannot sign for a human; inventing a signer would "
                                  "defeat the mechanism"},
    })
    state["established_findings"] = state["established_findings"] + [
        "ACCOUNTING: promotions are recorded in their own append-only ledger with enforced attribution and "
        "are explicitly not findings - nothing in the findings ledger may cite a promotion as evidence",
        "ACCOUNTING: the promotion ledger is hashed into snapshot manifests, so a promotion recorded after a "
        "snapshot is visibly absent from that snapshot's manifest",
    ]
    state["next_actions"] = [
        "add a reviewer checklist to the promotion ledger (what a signer must inspect)",
        "extend the profile's limits field with the governing promotion policy version",
        "third domain only if >=15 eligible series exist at these floors",
        "add promotion policy and the two blind spots to the paper's limitations section",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-060" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-060 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
