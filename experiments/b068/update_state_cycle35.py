"""Update STATE and BACKLOG for cycle 35 (frozen prospective forecasts)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASK = """  - id: B-068
    layer: predict
    priority: P1
    title: Frozen prospective forecast sets with maturation
    status: done
    owner: lead
    depends_on: [B-067]
    acceptance: >
      medradar/intelligence/forecasts.py (18 tests) provides quarter arithmetic, fixed windows, registration,
      validation and scoring (Brier/log loss/accuracy, pending always reported); the maturer refuses a modified
      set by content hash. Two committed sets: the original 32-forecast registration (which exposed 7 backfilled
      labels: matured at registration, Brier 0.337/accuracy 0.429, excluded as evidence) and a clean prospective
      set of 25 (13 promoted, 12 not; 7 backfilled excluded; earliest maturation 2026-Q4; hash 09525994...). The
      objective audit verifies committed sets by structure and hash.


"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T22:40:00+08:00"
    state["phase"] = "frozen_forecasts_registered"
    state["cycle"] = 37
    state["last_completed_cycle"] = {
        "cycle": 35,
        "name": "frozen_prospective_forecasts",
        "branch": "research/change-detection-v1",
        "report": "research/forecasts/FORECAST_SET_2026-11-03_prospective.json",
        "summary": "research/RESULTS/cycle35_forecasts_2026-11-03.md",
        "verdict": ("frozen forecast capability shipped: 25 genuinely prospective forecasts (13 promoted, 12 not) "
                    "with content hash and explicit maturation dates; the first registration exposed 7 backfilled "
                    "labels, which are excluded and reported (Brier 0.337, accuracy 0.429 - no better than the "
                    "majority class)"),
    }
    state["forecasts"] = {
        "module": "medradar/intelligence/forecasts.py (18 tests)",
        "registrar": "experiments/b068/register_forecasts.py",
        "maturer": "experiments/b068/maturate_forecasts.py (refuses a modified set by content hash)",
        "prospective_set": {
            "path": "research/forecasts/FORECAST_SET_2026-11-03_prospective.json",
            "count": 25, "promoted": 13, "not_promoted": 12,
            "backfilled_excluded": 7, "earliest_maturation": "2026-Q4",
            "hash": "09525994e7b6ae12",
            "can_count_as_evidence": True,
        },
        "original_set": {
            "path": "research/forecasts/FORECAST_SET_2026-11-03.json",
            "count": 32, "matured_at_registration": 7,
            "score_on_backfilled": {"brier": 0.337, "accuracy": 0.429, "log_loss": 0.896},
            "can_count_as_evidence": False,
            "reason": "a forecast registered after its outcome is known is a label, not a forecast",
        },
        "rule": ("register only alerts whose outcome window is entirely in the future; report backfilled alerts "
                 "separately"),
    }
    state["established_findings"] = state["established_findings"] + [
        "PREDICT: 25 genuinely prospective forecasts are frozen with content hashes and explicit maturation "
        "dates (2026-Q4..2028-Q1); editing them breaks the hash and the maturer refuses to score",
        "METHOD: 7 of the first 32 forecasts were backfilled (their outcome windows were already observed); they "
        "score Brier 0.337 / accuracy 0.429, no better than the majority class, and are excluded as evidence",
    ]
    state["next_actions"] = [
        "mature the prospective set as the lane advances (earliest 2026-Q4) and report Brier/calibration",
        "run tools/round_end.py as the gate at the end of every round",
        "consider a second paper focused on the measurement rules and the two confirmations",
        "decide whether the promotion ledger should log relabelling events",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-068" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
        print("B-068 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
