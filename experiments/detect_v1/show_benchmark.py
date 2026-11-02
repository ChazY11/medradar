"""Compact view of benchmark.json: per-detector, per-multiplier detection and spike rates."""
from __future__ import annotations

import json
from pathlib import Path

data = json.loads(Path("experiments/detect_v1/benchmark.json").read_text(encoding="utf-8"))
print("design:", {k: data["design"][k] for k in
                  ("multipliers", "onsets", "horizon_months", "target_false_alarm_rate")})
for level, block in data["levels"].items():
    print(f"\n===== level {level} =====")
    print(f"cells calib={block['calibration_cells']} eval={block['evaluation_cells']} "
          f"entities calib={block['calibration_entities']} eval={block['evaluation_entities']}")
    print(f"{'detector':24s} {'knob':>6s} {'FPRc':>6s} {'FPRe':>6s} "
          f"{'P(det)@2x':>10s} {'@3x':>7s} {'@5x':>7s} {'delay2x':>8s} {'delay5x':>8s} "
          f"{'spike2x':>8s} {'spike5x':>8s}")
    for name, entry in block["detectors"].items():
        if "metrics" not in entry:
            print(f"{name:24s} ERROR {entry}")
            continue
        cal = entry["calibration"]
        met = entry["metrics"]
        by = met["shift_detection"]
        spike = met["spike_false_change_rate"]
        def num(block_, key, field):
            value = block_.get(key, {}).get(field)
            return f"{value:.3f}" if isinstance(value, (int, float)) else "  -  "
        print(f"{name:24s} {cal['chosen_knob']:>6} "
              f"{cal['chosen_false_alarm_rate_calibration']:>6.3f} "
              f"{met['realised_false_alarm_rate']:>6.3f} "
              f"{num(by,'2.0','detection_probability'):>10s} "
              f"{num(by,'3.0','detection_probability'):>7s} "
              f"{num(by,'5.0','detection_probability'):>7s} "
              f"{num(by,'2.0','median_delay_months'):>8s} "
              f"{num(by,'5.0','median_delay_months'):>8s} "
              f"{spike.get('2.0', 0):>8.3f} {spike.get('5.0', 0):>8.3f}")
        print(f"    budget_met={cal['budget_met']}  overall P(det)={met['shift_overall']['detection_probability']:.3f} "
              f"median={met['shift_overall']['median_delay_months']}m "
              f"trials={met['shift_trials']}")
