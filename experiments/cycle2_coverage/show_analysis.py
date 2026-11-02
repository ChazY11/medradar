"""Compact console view of the cycle-2 analysis.json."""
from __future__ import annotations

import json
from pathlib import Path

path = Path("experiments/cycle2_coverage/analysis.json")
data = json.loads(path.read_text(encoding="utf-8"))
for panel, payload in data["panels"].items():
    print(f"\n===== {panel} =====")
    for window in payload.get("windows", []):
        print(f"  window {window['origin']}: n={window['rows']} pos={window['positives']} "
              f"train={window['training_rows']} AP={window['model_pr_auc']:.6f} "
              f"base={window['baseline_pr_auc']:.6f} d={window['delta_ap']:.6f}")
    inference = payload.get("inference", {})
    if not inference:
        continue
    pooled = inference.get("pooled", {})
    print(f"  pooled: n={pooled.get('rows')} pos={pooled.get('positives')} "
          f"prev={pooled.get('prevalence'):.5f} AP={pooled.get('model_pr_auc'):.6f} "
          f"base={pooled.get('baseline_pr_auc'):.6f} "
          f"clusters={pooled.get('entity_clusters')}E/{pooled.get('pair_clusters')}P")
    for cluster_name, ci in (inference.get("clustered_bootstrap") or {}).items():
        if not isinstance(ci, dict) or "delta" not in ci:
            print(f"  cluster[{cluster_name}]: {ci}")
            continue
        print(f"  cluster[{cluster_name}]: delta={ci['delta']:.6f} "
              f"CI=[{ci['ci_low']:.6f}, {ci['ci_high']:.6f}] se={ci.get('se_delta'):.6f} "
              f"p(d<=0)={ci.get('p_delta_le_zero')} n_clusters={ci.get('n_clusters')}")
    mde = inference.get("mde") or {}
    for key, value in mde.items():
        if isinstance(value, dict) and "mde_delta_ap" in value:
            print(f"  mde[{key}] = {value['mde_delta_ap']:.6f}")
        elif isinstance(value, dict) and "mde" in value:
            print(f"  mde[{key}] = {value['mde']:.6f} ({value.get('method')})")
        else:
            print(f"  mde[{key}] = {value}")
    lead = payload.get("lead_time", {})
    print(f"  censor_date={lead.get('censor_date')}")
    for entry in lead.get("windows", []):
        matched = entry.get("matched_far") or {}
        print(f"  lead {entry['origin']}: naive model={entry.get('model', {}).get('mean_lead_days')} "
              f"base={entry.get('baseline', {}).get('mean_lead_days')} | matched_far keys={list(matched)[:8]}")
    het = payload.get("heterogeneity", {})
    print(f"  heterogeneity by_entity_activity: {json.dumps(het.get('by_entity_activity'))[:400]}")
