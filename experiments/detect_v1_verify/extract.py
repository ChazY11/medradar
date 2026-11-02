"""Scratch: extract expected readout numbers for the final report message."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
benchmark = json.loads((ROOT / "experiments" / "detect_v1" / "benchmark.json").read_text(encoding="utf-8"))
for level in ("track", "track_clean", "domain"):
    block = benchmark["levels"][level]
    print(f"== {level}: cells={block['evaluation_cells']} entities={block['evaluation_entities']} "
          f"trials={block['shift_trials']}")
    for name in ("naive_multiplier", "rolling_zscore", "poisson_cusum", "poisson_bayes_factor"):
        entry = block["frontier_readout"]["0.02"][name]
        print(f"  {name:22s} knob={entry['knob']:>5} FAR={entry['false_alarm_rate']:.4f} "
              f"P={entry['detection_probability']:.6f}")
    for name, comparison in block["paired_comparison"]["comparisons"].items():
        print(f"  PAIRED {name:22s} d={comparison['difference']:+.6f} "
              f"CI=[{comparison['ci_low']:+.6f}, {comparison['ci_high']:+.6f}]")
