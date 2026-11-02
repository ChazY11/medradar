"""Bin-width sweep (B-038): does the detector ranking track the expected count per bin?

The cycle-3b correction (DECISIONS D-018) found that the ranking of change detectors
reverses between 1-month and 3-month aggregation. The stated mechanism was a *hypothesis*:
at ~0.2 events/month one observation already crosses a rate threshold, favouring a matched
rate-ratio test, while at coarser bins a bin aggregates several events and an
evidence-accumulating detector can separate a sustained shift from a burst.

This sweep tests it by varying the bin width (1, 2, 3, 4, 6 months) with everything else
held fixed: same lane, same entity assignment, same calendar onsets, same 12-month horizon,
same 2 % false-alarm budget, same seeds discipline. It reports, per width, the expected
events per bin and each detector's detection probability, and locates the crossover.

Usage:
    python experiments/detect_v1/bin_sweep.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.cycle2_coverage.panel import write_json  # noqa: E402
from experiments.detect_v1.benchmark import (  # noqa: E402
    DETECTOR_ORDER,
    run_level,
)

BUDGET = 0.02


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--widths", default="experiments/detect_v1/widths.json")
    parser.add_argument("--out", default="experiments/detect_v1/bin_sweep.json")
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.widths).read_text(encoding="utf-8"))
    results: dict[str, Any] = {
        "design": {
            "purpose": "locate the resolution crossover found in DECISIONS D-018 and test the "
                       "expected-events-per-bin mechanism",
            "widths_months": payload["widths"],
            "budget": BUDGET,
            "held_fixed": ["event lane", "entity assignment", "calendar onsets",
                           "12-month horizon", "false-alarm budget", "seed discipline"],
            "eligibility": payload["eligibility"],
        },
        "panels": {},
    }

    for width in payload["widths"]:
        panel = payload["panels"][str(width)]
        level_key = f"w{width}m"
        print(f"\n=== width {width} month(s): {panel['summary']['cells']} cells, "
              f"{panel['bins']} bins, median expected events/bin "
              f"{panel['summary']['median_expected_events_per_bin']:.3f} ===")
        output = run_level(level_key, panel["cells"], panel["labels"], bin_months=width)
        readout = output["frontier_readout"][str(BUDGET)]
        paired = output["paired_comparison"]["comparisons"]
        results["panels"][str(width)] = {
            "bin_months": width,
            "bins": panel["bins"],
            "cells": output["cells_total"],
            "evaluation_cells": output["evaluation_cells"],
            "median_events_per_cell": panel["summary"]["median_events_per_cell"],
            "median_expected_events_per_bin": panel["summary"]["median_expected_events_per_bin"],
            "mean_expected_events_per_bin": panel["summary"]["mean_expected_events_per_bin"],
            "onsets_used": output["onsets_used"],
            "horizon_bins": output["horizon_bins"],
            "onset_tolerance_bins": output["onset_tolerance_bins"],
            "shift_trials": output["shift_trials"],
            "readout": {name: {"knob": readout[name].get("knob"),
                               "false_alarm_rate": readout[name].get("false_alarm_rate"),
                               "detection_probability": readout[name].get("detection_probability"),
                               "median_delay_months": readout[name].get("median_delay_months")}
                        for name in DETECTOR_ORDER if name in readout},
            "paired_vs_naive": paired,
            "detector_priors": output["detectors"],
        }

    # Crossover description derived from the readouts, not hand-written.
    widths = [int(width) for width in results["panels"]]
    crossover = None
    for width in widths:
        block = results["panels"][str(width)]["readout"]
        naive = block["naive_multiplier"]["detection_probability"]
        likelihood = {name: block[name]["detection_probability"]
                      for name in DETECTOR_ORDER if name != "naive_multiplier"}
        winner = max({**{"naive_multiplier": naive}, **likelihood}.items(),
                     key=lambda item: item[1] if item[1] is not None else -1)
        block_best = {"winner": winner[0], "winner_probability": winner[1],
                      "naive_probability": naive}
        results["panels"][str(width)]["best_detector"] = block_best
        if crossover is None and winner[0] != "naive_multiplier":
            crossover = {"bin_months": width,
                         "best_detector": winner[0],
                         "median_expected_events_per_bin":
                             results["panels"][str(width)]["median_expected_events_per_bin"]}
    results["crossover"] = crossover or {"status": "no crossover: naive best at every width"}

    print("\nwidth  median ev/bin   naive    z     CUSUM   Bayes   best")
    for width in widths:
        block = results["panels"][str(width)]
        read = block["readout"]
        probs = {name: read[name]["detection_probability"] for name in DETECTOR_ORDER}
        print(f"{width:>5}m {block['median_expected_events_per_bin']:>13.3f} "
              f"{probs['naive_multiplier']:>7.3f} {probs['rolling_zscore']:>5.3f} "
              f"{probs['poisson_cusum']:>7.3f} {probs['poisson_bayes_factor']:>7.3f} "
              f"{block['best_detector']['winner']}")
    print("\ncrossover:", json.dumps(results["crossover"]))
    write_json(Path(args.out), results)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
