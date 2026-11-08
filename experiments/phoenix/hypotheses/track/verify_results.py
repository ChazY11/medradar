"""Validate that every result JSON carries the required provenance fields."""
import json
from pathlib import Path

R = Path(__file__).resolve().parent / "results"
REQ = ["protocol_version", "db_sha256", "lag_scenario", "command", "elapsed_sec",
       "n", "n_pos", "prevalence"]
ok_all = True
for p in sorted(R.glob("*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    missing = [k for k in REQ if k not in d]
    ok = not missing
    ok_all &= ok
    print(f"{'OK  ' if ok else 'MISS'} {p.name:34s} " +
          (f"missing={missing}" if missing else
           f"lag={str(d['lag_scenario'])[:22]:22s} n={d['n']} n_pos={d['n_pos']} "
           f"prev={d['prevalence']} elapsed={d['elapsed_sec']}"))
print()
print("ALL REQUIRED FIELDS PRESENT:", ok_all)

# determinism spot check: the numbers the report cites
m = json.loads((R / "track_all_metrics.json").read_text(encoding="utf-8"))
c = json.loads((R / "changepoint_bench.json").read_text(encoding="utf-8"))
print()
print("H8 L090 dAP", round(m["lags"]["L090"]["contrasts"]["H8"]["diff"], 6),
      "p", m["lags"]["L090"]["contrasts"]["H8"]["p"])
print("H3 L090 dAP", round(m["lags"]["L090"]["contrasts"]["H3"]["diff"], 6))
print("H7 pelt gain", round(c["best_cp_gain_vs_fixed"], 6),
      "tuned", c["tuned_parameters"])
print("panel check", json.loads((R / "panel_facts.json").read_text(encoding="utf-8"))
      ["frozen_reference_check"]["match"])
