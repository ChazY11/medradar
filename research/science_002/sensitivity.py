"""Pre-registered sensitivities S1-S3 for SCIENCE-002.

Each scenario rebuilds the universe, the panel and the primary statistic from the
same cached bytes with one rule changed, and reports the pre-registered decision
inputs. The sensitivities use 1,000 permutations and 1,000 bootstrap draws (the
primary test uses 2,000 of each) to bound runtime; that difference is recorded in
the PROTOCOL deviations log and affects only the resolution of the p-value and CI,
never the point estimate.

S1  remove tier-B attribution (the 2026 FDA owner/operator map), keeping only
    exact matches to the registrant's current or former SEC name;
S2  remove SIC 3826 (laboratory analytical instruments) from the universe;
S3  change the clearance-availability lag from 30 days to 0 and 60 days.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import experiment, panel, pipeline, universe
from .sources import Cache

SCENARIOS = {
    "base": {},
    "S1_strict_attribution": {"include_tier_b": False},
    "S2_no_sic_3826": {"sic_set": universe.DEVICE_SIC_WITHOUT_3826},
    "S3a_lag_0": {"lag": 0},
    "S3b_lag_60": {"lag": 60},
}


def _run_one(cache: Cache, *, include_tier_b: bool = True,
             sic_set: Mapping[str, str] | None = None, lag: int = panel.AVAILABILITY_LAG_DAYS,
             seed: int, n_perm: int, n_boot: int) -> dict[str, Any]:
    build = pipeline.build_universe(cache, verbose=False, include_tier_b=include_tier_b,
                                    sic_set=sic_set)
    index = pipeline.clearance_index(build)
    p = panel.build_panel(build, index, availability_lag_days=lag)
    result = experiment.run(p, seed=seed, n_perm=n_perm, n_boot=n_boot, n_placebo=5)
    ci = result["bootstrap"]["delta_B3c_minus_B2c"]
    return {
        "n_firms": len(build.included),
        "n_rows": len(p.rows),
        "n_complete_case": result["meta"]["n_rows_complete_case"],
        "n_holdout": result["meta"]["n_holdout"],
        "n_firms_stratified": result["conditional"]["B2c"]["n_firms"],
        "delta": result["primary"]["delta_stratified_auc_B3c_minus_B2c"],
        "p_two_sided": result["permutation"]["p_two_sided"],
        "ci_lo": ci.get("lo"),
        "ci_hi": ci.get("hi"),
        "pooled_B1": result["pooled"]["B1"],
        "lofo_delta": result["lofo"]["delta_B3_minus_B2"]["mean"],
        "verdict": result["verdict"]["verdict"],
    }


def run_all(cache: Cache, seed: int = 20261114, n_perm: int = 1000,
            n_boot: int = 1000, verbose: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, params in SCENARIOS.items():
        if verbose:
            print("  sensitivity", name, flush=True)
        out[name] = _run_one(cache, seed=seed, n_perm=n_perm, n_boot=n_boot, **params)
    deltas = [out[name]["delta"] for name in out
              if name != "base" and out[name]["delta"] is not None]
    out["_summary"] = {
        "n_scenarios": len(SCENARIOS),
        "all_deltas_negative_or_null": all(d <= 0.02 for d in deltas) if deltas else None,
        "max_delta": max(deltas) if deltas else None,
        "any_go": any(out[name]["verdict"] == "GO" for name in SCENARIOS),
        "note": "sensitivities use 1,000 permutations / 1,000 bootstrap draws",
    }
    return out
