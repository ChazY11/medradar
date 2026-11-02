"""Update STATE.json and BACKLOG.yaml for cycle 22 (deployment detector in the product)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-056
    layer: understand
    priority: P1
    title: Carry the validated deployment detector inside the profile
    status: done
    owner: lead
    depends_on: [B-039, B-027]
    acceptance: >
      Momentum carries a nested deployment_alerts block applying the D-045 detector (quarterly rolling
      z-score, threshold 3.5, measured FAR 0.018, sensitivity 0.147), reporting alerts from the last
      eight quarters with track/quarter/count/baseline/z, and stating the measured FAR and sensitivity
      inside the profile. selfcheck fails any profile whose block names another detector/resolution,
      whose alert fails its own threshold, or whose markdown omits the detector line or FAR. The
      promotion rule stays manual.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T09:40:00+08:00"
    state["phase"] = "product_carries_validated_detector"
    state["cycle"] = 24
    state["last_completed_cycle"] = {
        "cycle": 22,
        "name": "deployment_detector_in_product",
        "branch": "research/change-detection-v1",
        "report": "experiments/b027/profiles.json",
        "summary": "research/RESULTS/cycle22_product_2026-11-03.md",
        "verdict": ("the profile's momentum field now carries the validated detector (quarterly rolling "
                    "z-score, threshold 3.5, FAR 0.018, sensitivity 0.147) with the measured rates "
                    "printed inside the profile; 44 profile tests; selfcheck enforces the detector, "
                    "resolution, threshold and FAR statement; the promotion rule stays manual"),
    }
    state["understand_layer"]["deployment_alerts"] = {
        "status": "SHIPPED - nested in momentum, no schema change",
        "resolution_months": 3, "detector": "rolling_zscore", "threshold": 3.5,
        "memory_months": 12, "baseline_months": 24,
        "false_alarm_rate": 0.0179, "sensitivity": 0.147,
        "recency_quarters": 8,
        "provenance_in_profile": True,
        "medtronic_live_alerts": [{"track": "coronary", "quarter": "2026-Q3", "events": 2,
                                   "baseline_mean": 0.25, "z": 3.5},
                                  {"track": "insulin_delivery", "quarter": "2025-Q3", "events": 2,
                                   "baseline_mean": 0.25, "z": 3.5}],
        "honest_reading": ("two-event alerts are legitimate at the measured false-alarm rate and "
                           "substantively thin; the profile prints counts and baselines beside the alert"),
        "promotion_rule": "manual - D-043 rule recorded but deliberately not auto-applied",
        "enforcement": "selfcheck.py checks detector, resolution, threshold clearance and FAR statement",
    }
    state["established_findings"] = state["established_findings"] + [
        "UNDERSTAND: the validated deployment detector now runs inside every profile with its measured "
        "false-alarm rate and sensitivity printed in the profile itself, not in a methods note",
        "UNDERSTAND: on real data the quarterly detector returns sparse, thin alerts (Medtronic: two "
        "events against a 0.25 baseline) - calibrated is not the same as substantial, and the profile "
        "says so beside the alert",
    ]
    state["next_actions"] = [
        "B-055: confirm the promotion rule on fresh cells (requires a larger eligible-cell set)",
        "decide the promotion policy explicitly (manual review vs automated) before wiring D-043",
        "second-domain validation before calling any of this portable",
        "extend the profile snapshot chain with the deployment block (new as-of snapshot)",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-056" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-056 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
