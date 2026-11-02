"""Update STATE.json and BACKLOG.yaml for cycle 24 (promotion policy + snapshot)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-057
    layer: understand
    priority: P0
    title: Promotion policy as code, and a snapshot carrying the deployment block
    status: done
    owner: lead
    depends_on: [B-043, B-046]
    acceptance: >
      medradar/intelligence/promotion.py gates promotion through validated-detector provenance, the
      confirmed two-quarter window, the contradiction check and human sign-off, and can only return
      reject or promote_pending_signoff (automated promotion disabled and asserted by a test). Policy
      written into PREDICTION_PROTOCOL.md section 8. A sixth frozen snapshot (2026-11-03) carries the
      deployment block and promotion verdicts; its diff against 2026-11-02 reports identical data,
      which is the correct reading. selfcheck enforces the verdict set, the sign-off flag, the
      filing-rate statement and the markdown presence.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T11:40:00+08:00"
    state["phase"] = "promotion_policy_shipped"
    state["cycle"] = 26
    state["last_completed_cycle"] = {
        "cycle": 24,
        "name": "promotion_policy_and_snapshot",
        "branch": "research/change-detection-v1",
        "report": "medradar/intelligence/promotion.py",
        "summary": "research/RESULTS/cycle24_promotion_policy_2026-11-03.md",
        "verdict": ("promotion policy implemented as code and tested (18 tests): validated-detector "
                    "provenance, confirmed two-quarter window, contradiction check and mandatory human "
                    "sign-off; only reject or promote_pending_signoff can be returned, automated path "
                    "asserted absent. Sixth snapshot frozen with the deployment block; diff vs "
                    "2026-11-02 shows identical data, i.e. knowledge changed, not data"),
    }
    state["publication"]["promotion_policy"] = {
        "module": "medradar/intelligence/promotion.py",
        "tests": "tests/test_promotion.py (18)",
        "protocol": "research/PREDICTION_PROTOCOL.md section 8",
        "gates": ["calibrated_alert", "confirmation_window", "contradiction_check", "human_signoff"],
        "verdicts": ["reject", "promote_pending_signoff"],
        "automated_promotion_allowed": False,
        "live_results": {"medtronic:coronary:2026-Q3": "reject (no confirmation quarters yet)",
                         "medtronic:insulin_delivery:2025-Q3": "promote_pending_signoff (ramp)"},
        "statement": ("promotion marks a sustained change in PUBLIC FILING RATE; not intent, "
                      "capability, internal R&D or technological significance"),
    }
    state["point_in_time"]["snapshots"] = ["2020-12-31", "2022-12-31", "2024-12-31", "2026-11-02",
                                           "2026-11-03"]
    state["point_in_time"]["auditable_snapshots"] = 5
    state["point_in_time"]["latest_snapshot"] = {
        "as_of": "2026-11-03", "manifest_hash": "5b7062d2f9dd432d",
        "adds": "deployment block and promotion verdicts",
        "diff_vs_previous": "identical data (3,928 events, 0 momentum changes, 0 track changes); "
                            "knowledge changed, not data",
    }
    state["established_findings"] = state["established_findings"] + [
        "UNDERSTAND: promotion to 'technology change' is gated in code by validated-detector provenance, "
        "the confirmed two-quarter window, the contradiction check and mandatory human sign-off; no "
        "automated promotion path exists and a test prevents one being added quietly",
        "POINT-IN-TIME: a fifth auditable snapshot (2026-11-03) carries the deployment block; its diff "
        "against 2026-11-02 shows identical data, which is the correct way to report a knowledge-only change",
    ]
    state["next_actions"] = [
        "second-domain validation before any portability claim",
        "decide how promoted changes enter the paper's results ledger (a promoted alert is not a finding)",
        "consider a longer confirmation window for ramps and report the precision/recall trade-off",
        "extend the promotion policy to record the sign-off identity in the snapshot manifest",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-057" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-057 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
