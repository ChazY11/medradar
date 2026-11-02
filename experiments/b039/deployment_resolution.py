"""B-039: choose the deployment resolution and decide whether a detector can be named.

Pre-registered in research/DECISIONS.md D-044 before this script was first run.

The layer must operate at a resolution. This script reads the existing bin-width sweep (widths 1, 2, 3, 4,
6 months, all detector memory expressed in calendar months per D-020), takes 3 months (quarterly) as the
deployment resolution justified by the decision cadence, and asks the question B-039 poses:

    at the deployment resolution, is one detector identifiable?

Rules fixed in D-044: operating point = sweep row with achieved false-alarm rate closest to and not above
the 2 % budget; a detector with no such row is reported as not calibratable at this budget; uncertainty by
Wilson intervals; a detector is named only if the same detector wins at every width AND every pairwise
Kendall tau between width rankings is at least 0.5.

Usage:
    python experiments/b039/deployment_resolution.py
"""
from __future__ import annotations

import argparse
import itertools
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.cycle2_coverage.panel import write_json  # noqa: E402

SWEEP = Path("experiments/detect_v1/bin_sweep.json")
BUDGET = 0.02
DEPLOYMENT_WIDTH = 3
KENDALL_FLOOR = 0.5
DETECTOR_ORDER = ("naive_multiplier", "poisson_cusum", "poisson_bayes_factor", "rolling_zscore")


def wilson(successes: int, trials: int, z: float = 1.959963985) -> list[float]:
    """Wilson score interval for a binomial proportion."""
    if trials <= 0:
        return [None, None]
    proportion = successes / trials
    denominator = 1 + z * z / trials
    centre = (proportion + z * z / (2 * trials)) / denominator
    margin = (z * math.sqrt(proportion * (1 - proportion) / trials
                            + z * z / (4 * trials * trials)) / denominator)
    return [max(0.0, centre - margin), min(1.0, centre + margin)]


def operating_point(block: dict[str, Any], budget: float) -> dict[str, Any] | None:
    rows = [row for row in (block.get("frontier") or [])
            if row.get("false_alarm_rate") is not None
            and row["false_alarm_rate"] <= budget]
    if not rows:
        return None
    best = max(rows, key=lambda row: (row["detection_probability"],
                                      -abs(row["false_alarm_rate"] - budget)))
    return best


def kendall_tau(ranking_a: list[str], ranking_b: list[str]) -> float | None:
    """Kendall tau over detectors present in both rankings."""
    common = [detector for detector in ranking_a if detector in ranking_b]
    if len(common) < 2:
        return None
    index_a = {detector: position for position, detector in enumerate(ranking_a)}
    index_b = {detector: position for position, detector in enumerate(ranking_b)}
    concordant = discordant = 0
    for left, right in itertools.combinations(common, 2):
        delta = ((index_a[left] - index_a[right]) * (index_b[left] - index_b[right]))
        if delta > 0:
            concordant += 1
        elif delta < 0:
            discordant += 1
    total = concordant + discordant
    return ((concordant - discordant) / total) if total else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiments/b039/deployment_resolution.json")
    args = parser.parse_args(argv)

    sweep = SWEEP.read_text(encoding="utf-8")
    import json
    payload_sweep = json.loads(sweep)

    widths = sorted(payload_sweep["panels"], key=int)
    per_width: dict[str, dict[str, Any]] = {}
    for width in widths:
        panel = payload_sweep["panels"][width]
        detectors: dict[str, Any] = {}
        for detector in DETECTOR_ORDER:
            block = panel["detector_priors"].get(detector)
            if block is None:
                continue
            point = operating_point(block, BUDGET)
            if point is None:
                detectors[detector] = {"calibratable": False,
                                       "reason": "no sweep row at or below the 2 % budget"}
                continue
            # the sweep row carries its own cluster-bootstrap interval and per-multiplier trial counts;
            # fall back to a Wilson interval only if neither is available
            ci = point.get("detection_probability_ci")
            by_multiplier = point.get("by_multiplier") or {}
            trials = max((block.get("trials") or 0) for block in by_multiplier.values()) \
                if by_multiplier else 0
            if trials:
                successes = int(round(point["detection_probability"] * trials))
                low, high = wilson(successes, trials) if ci is None else ci
            else:
                successes = 0
                low, high = (ci if ci is not None else (None, None))
            detectors[detector] = {
                "calibratable": True,
                "achieved_false_alarm_rate": point["false_alarm_rate"],
                "sensitivity": point["detection_probability"],
                "trials": trials,
                "detected": successes,
                "ci": [low, high],
                "median_delay_months": point.get("median_delay_months"),
            }
        ranked = sorted((detector for detector, value in detectors.items() if value["calibratable"]),
                        key=lambda detector: -detectors[detector]["sensitivity"])
        per_width[width] = {"bins": panel["bins"], "cells": panel["cells"],
                            "evaluation_cells": panel["evaluation_cells"],
                            "median_expected_events_per_bin": panel["median_expected_events_per_bin"],
                            "detectors": detectors, "ranking": ranked,
                            "winner": ranked[0] if ranked else None}
        summary = ", ".join(f"{detector}={detectors[detector].get('sensitivity', float('nan')):.3f}"
                            if detectors[detector]["calibratable"] else f"{detector}=n/a"
                            for detector in DETECTOR_ORDER if detector in detectors)
        print(f"width {width:>2s} months: {summary}  -> winner {per_width[width]['winner']}")

    deployment = per_width[str(DEPLOYMENT_WIDTH)]
    taus = {}
    for width in widths:
        if width == str(DEPLOYMENT_WIDTH):
            continue
        tau = kendall_tau(deployment["ranking"], per_width[width]["ranking"])
        taus[width] = tau
    winners = {width: per_width[width]["winner"] for width in widths}
    same_winner = len({winner for winner in winners.values() if winner}) == 1
    taus_ok = all(tau is not None and tau >= KENDALL_FLOOR for tau in taus.values())
    identifiable = bool(same_winner and taus_ok)

    deployment_point = deployment["detectors"].get(deployment["winner"], {})
    conclusion = {
        "resolution_months": DEPLOYMENT_WIDTH,
        "winner": deployment["winner"],
        "winner_sensitivity": deployment_point.get("sensitivity"),
        "winner_ci": deployment_point.get("ci"),
        "identifiable": identifiable,
        "same_winner_across_widths": same_winner,
        "kendall_all_at_least_floor": taus_ok,
        "kendall_floor": KENDALL_FLOOR,
        "statement": (f"At the quarterly deployment resolution, {deployment['winner']} has the highest "
                       f"measured sensitivity ({deployment_point.get('sensitivity'):.3f}), but the "
                       f"detector ranking is NOT identifiable across resolutions, so the choice is "
                       f"resolution-specific and must not be reported as a general winner."
                       if not identifiable else
                       f"{deployment['winner']} is identifiable as the best detector across resolutions."),
    }

    payload = {
        "design": {
            "decision": "research/DECISIONS.md D-044 (pre-registered)",
            "budget": BUDGET,
            "deployment_width_months": DEPLOYMENT_WIDTH,
            "resolution_justification": ("quarterly technology reviews and analyst re-forecasting; "
                                         "monthly resolution leaves ~0.2 events per cell-month, where "
                                         "the detectors cannot resolve a change (measured in D-018/D-024)"),
            "operating_point_rule": "sweep row with achieved FAR closest to and not above the budget",
            "kendall_floor": KENDALL_FLOOR,
            "identifiability_rule": "same winner at every width AND all pairwise Kendall tau >= floor",
        },
        "per_width": per_width,
        "kendall_tau_vs_deployment": taus,
        "winners": winners,
        "conclusion": conclusion,
    }
    write_json(Path(args.out), payload)

    print(f"\ndeployment resolution: {DEPLOYMENT_WIDTH} months ({deployment['bins']} bins)")
    print(f"winners by width: {winners}")
    print(f"kendall tau vs deployment: { {k: (None if v is None else round(v, 2)) for k, v in taus.items()} }")
    print(f"identifiable: {identifiable}")
    print(conclusion["statement"])
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
