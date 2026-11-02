"""Smoke test for verify.py internals on a small subset (not a deliverable)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify  # noqa: E402

payload = json.loads((ROOT / "experiments/detect_v1/streams.json").read_text(encoding="utf-8"))
labels = payload["labels"]
cells = verify.split_cells(payload["track_cells"])[:8]
print("cells", len(cells))

step = verify.evaluate(cells, labels, "step", "inject-shift")
print("trials", step["shift_trials"], step["spike_trials"])
print("picks", step["paired"]["picks"])
print("readout2%", {k: (v.get("knob"), v.get("detection_probability")) for k, v in step["readout"]["0.02"].items()})
print("paired", {k: round(v["difference"], 4) for k, v in step["paired"]["comparisons"].items()})

ramp = verify.evaluate(cells, labels, "ramp", "inject-ramp", spikes_for=None)
plan = verify.bootstrap_plan(step["_scores"]["naive_multiplier"][6.0]["trials"])
alt = verify.alternative_readout(ramp, plan, verify.BENCHMARK_PICKS)
print("ramp picks", alt["picked_knobs"])
print("ramp cusum", json.dumps(alt["detectors"]["poisson_cusum"], indent=1)[:600])
print("ramp naive", alt["detectors"]["naive_multiplier"]["detection_probability"])
print("verdict", verify.scientific_verdict({"ramp": alt}))
