"""Update STATE, BACKLOG and audit for cycle 32 (labelled snapshots + promotion diff)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-065
    layer: govern
    priority: P1
    title: Labelled snapshots and a promotion-label diff
    status: done
    owner: lead
    depends_on: [B-060, B-064]
    acceptance: >
      freeze_snapshot --label allows a second snapshot at the same as-of (2026-11-03-policy-v2) with the
      manifest recording the true as-of; selfcheck and snapshot_diff accept as-of or as-of-<label>; the leakage
      audit uses the manifest as-of. snapshot_diff compares per-alert (verdict, shape, policy version) and
      reports changes. Result: 32 alert labels changed between v1 and v2, 8 of them from ramp to
      sustained_unresolved, while the data-level diff reports zero change. 6 of 6 snapshots verify; 0 leakage
      problems.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T19:40:00+08:00"
    state["phase"] = "policy_change_visible_in_record"
    state["cycle"] = 34
    state["last_completed_cycle"] = {
        "cycle": 32,
        "name": "labelled_snapshots_and_promotion_diff",
        "branch": "research/change-detection-v1",
        "report": "experiments/b027/snapshot_diff.json",
        "summary": "research/RESULTS/cycle32_snapshot_labels_2026-11-03.md",
        "verdict": ("a sixth auditable snapshot (2026-11-03-policy-v2) and a promotion-label diff make the "
                    "policy change visible: 32 alert labels changed, 8 from ramp to sustained_unresolved, while "
                    "the data-level diff reports zero change; 6/6 snapshots verify, 0 leakage problems"),
    }
    state["point_in_time"]["snapshots"] = ["2020-12-31", "2022-12-31", "2024-12-31", "2026-11-02",
                                           "2026-11-03", "2026-11-03-policy-v2"]
    state["point_in_time"]["auditable_snapshots"] = 6
    state["point_in_time"]["labelled_snapshots"] = {
        "supported_by": "freeze_snapshot.py --label",
        "example": "2026-11-03-policy-v2 (manifest 44abde1672df)",
        "as_of_handling": ("manifest records the true as-of; selfcheck and snapshot_diff accept as-of or "
                           "as-of-<label>; the leakage audit uses the manifest value"),
    }
    state["point_in_time"]["promotion_diff"] = {
        "artifact": "experiments/b027/snapshot_diff.json",
        "policy_v1_to_v2": {"alert_labels_changed": 32, "shape_changes": 8,
                            "shape_change_direction": "ramp -> sustained_unresolved",
                            "data_level_changes": 0},
        "reading": ("both readings are correct: the data did not move, the labels did - only reporting one "
                    "of them would mislead"),
    }
    state["established_findings"] = state["established_findings"] + [
        "POINT-IN-TIME: the record can now show WHICH claims a policy change altered (32 labels, 8 shape "
        "changes from ramp to sustained_unresolved) alongside zero data-level movement",
        "POINT-IN-TIME: labelled snapshots are supported (as-of plus suffix) without weakening verification: "
        "6 of 6 snapshots verify and the leakage audit stays clean",
    ]
    state["next_actions"] = [
        "wire the audit into the round-end routine so every round reports it",
        "consider a second paper focused on the measurement rules and the density confirmation",
        "decide whether the promotion ledger should record relabelling events as an audit trail",
        "revisit the 1.0/month floor if a denser domain becomes available",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-065" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-065 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
