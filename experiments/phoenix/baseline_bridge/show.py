#!/usr/bin/env python3
"""Print the baseline-bridge comparison table (called by the Lead, not committed data)."""
import json
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "baseline_bridge" / "results" / "baseline_bridge.json"
d = json.loads(P.read_text(encoding="utf-8"))
print("panel:", d["panel"])
print(f"n_test={d['n_test_total']}  n_pos={d['n_pos_total']}  pooled_prevalence={d['pooled_prev']:.4f}")
print()
print(f"{'arm':34s} {'bridge AP':>10s} {'S-028 published':>16s} {'delta':>9s}")
for k, v in d["comparison_vs_published"].items():
    b = v["phoenix_bridge"]
    print(f"{k:34s} {b:10.4f} {v['s028_published']:16.4f} {b - v['s028_published']:+9.4f}")
print()
print("per-fold prevalence (test):")
for f in d["folds"]:
    if f.get("status") == "ok":
        print(f"  {f['year']}  n={f['n_test']:4d}  n_pos={f['n_pos_test']:3d}  prev={f['prev_test']:.4f}")
