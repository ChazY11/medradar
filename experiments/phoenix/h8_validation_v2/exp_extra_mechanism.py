"""Post-hoc mechanism probes (EXPLORATORY, added after the Audit C finding).

These are NOT part of the frozen primary family and do not enter the GO/NO-GO gates.
They exist to explain *why* H8's delta-AP appears, and are labelled exploratory in the
report:

  1. Y5 (absolute level) and Y6 (any activity) targets: remove the trailing-ratio rule
     from the label entirely.  If H8's gain is a target-definition artifact, it should
     collapse when the label no longer contains a relative-growth denominator.
  2. Feature-block decomposition on the real panel: which part of the H8 block carries
     the delta-AP (the four growth ratios, or the nonlinear level transforms
     slope12 / volatility8 / pma_share4).

Run:  python exp_extra_mechanism.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

import data as D
import features as F
import metrics as M
import protocol as P
import runner as R

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
EVIDENCE = HERE / "evidence"


def add_level_targets(panel: pd.DataFrame) -> pd.DataFrame:
    """Y5 = fwd4_total >= 3 (absolute level); Y6 = fwd4_total >= 1 (any activity)."""
    panel = panel.copy()
    base_ok = panel["fwd_total"].notna()
    panel["y_Y5_abs_level"] = ((panel["fwd_total"] >= 3).where(base_ok)).astype(float)
    panel["y_Y6_any_activity"] = ((panel["fwd_total"] >= 1).where(base_ok)).astype(float)
    return panel


def run_target(panel: pd.DataFrame, target_col: str, name: str,
               store: list | None = None) -> dict:
    res, oof = R.run_config(panel, target_col, "purged", 90,
                            arms=("M1_persistence", "M4_h8_growth"),
                            with_ci=True, B=P.B_BOOT_SECONDARY)
    if store is not None and not oof.empty:
        keep = oof[["track_id", "quarter", "qnum", "fold_year", "y",
                    "M1_persistence", "M4_h8_growth"]].copy()
        keep["target_name"] = name
        store.append(keep)
    c = res["contrasts"]["M4_h8_growth - M1_persistence"]
    rec = {"name": name, "target": target_col,
           "n": res["n"], "n_pos": res["n_pos"], "prevalence": res["prevalence"],
           "ap_M1": c["ap_b"], "ap_M4": c["ap_a"], "dap": c["diff"],
           "ci95": [c["lo"], c["hi"]], "p": c["p"]}
    print(f"[target] {name:28s} n={rec['n']:5d} pos={rec['n_pos']:4d} "
          f"prev={rec['prevalence']:.4f} AP_M1={rec['ap_M1']:.4f} AP_M4={rec['ap_M4']:.4f} "
          f"dAP={rec['dap']:+.4f} CI=[{c['lo']:+.4f},{c['hi']:+.4f}] p={c['p']:.4f}")
    return rec


def run_arm(panel: pd.DataFrame, features: list[str], name: str,
            target_col: str = "y_Y1_growth_ratio", store: list | None = None) -> dict:
    fs = R.feature_sets_dict()
    fs["M4_block"] = features
    oof, meta, _ = R.run_oof(panel, target_col, R.make_folds("purged", 90), fs,
                             arms=("M4_block", "M1_persistence"))
    if store is not None and not oof.empty:
        keep = oof[["track_id", "quarter", "qnum", "fold_year", "y",
                    "M1_persistence", "M4_block"]].copy()
        keep["block_name"] = name
        store.append(keep)
    d = oof.dropna(subset=["y", "M4_block", "M1_persistence"])
    c = M.paired_bootstrap_diff(d["y"].to_numpy(float), d["M4_block"].to_numpy(float),
                                d["M1_persistence"].to_numpy(float),
                                d["track_id"].to_numpy(), B=P.B_BOOT_SECONDARY)
    rec = {"name": name, "features": features, "n": int(len(d)),
           "n_pos": int(d["y"].sum()),
           "ap_block": M.average_precision(d["y"], d["M4_block"]),
           "ap_M1": M.average_precision(d["y"], d["M1_persistence"]),
           "dap": c["diff"], "ci95": [c["lo"], c["hi"]], "p": c["p"]}
    print(f"[block] {name:26s} dAP={rec['dap']:+.4f} CI=[{c['lo']:+.4f},{c['hi']:+.4f}] "
          f"p={c['p']:.4f}")
    return rec


def main() -> int:
    t0 = time.time()
    RESULTS.mkdir(exist_ok=True)
    EVIDENCE.mkdir(exist_ok=True)
    LOG = EVIDENCE / "exp_extra_mechanism.log"
    fh = LOG.open("w", encoding="utf-8")

    def say(msg: str) -> None:
        print(msg, flush=True)
        fh.write(msg + "\n")
        fh.flush()

    say("# PHOENIX-002 exploratory mechanism probes (NOT part of the frozen primary family)")
    db = D.verify_db(verbose=True)
    if not db["sha256_matches_frozen"]:
        say("ABORT: db hash mismatch")
        return 2
    events = D.load_events(P.ALL_KINDS)
    cov = D.coverage_stats(events)
    panel = R.add_attribution_rate(F.build_features(D.build_panel("attr38", 90, mode="v2")), cov)
    panel = add_level_targets(panel)

    out = {"experiment": "EXPLORATORY_MECHANISM_PROBES",
           "status": "EXPLORATORY — added after Audit C; not in the frozen primary family",
           "db_sha256": P.DB_SHA256, "targets": [], "feature_blocks": []}

    say("\n## 1. denominator-free / level-only targets (same features, same folds)")
    target_oof: list = []
    for tgt, name in (("y_Y1_growth_ratio", "Y1 frozen ratio target"),
                      ("y_Y2_abs_increase", "Y2 additive increase"),
                      ("y_Y3_new_plateau", "Y3 new plateau"),
                      ("y_Y5_abs_level", "Y5 absolute level (fwd>=3)"),
                      ("y_Y6_any_activity", "Y6 any activity (fwd>=1)")):
        out["targets"].append(run_target(panel, tgt, name, target_oof))
    if target_oof:
        pd.concat(target_oof, ignore_index=True).to_csv(
            RESULTS / "oof_extra_targets.csv", index=False)

    say("\n## 2. H8 feature-block decomposition on the real panel (target Y1)")
    block_oof: list = []
    blocks = {
        "B1_only": list(F.B1_FEATS),
        "B1+growth_ratios(4)": list(F.B1_FEATS) + ["sct_growth1", "sct_growth2",
                                                   "sct_growth4", "sct_growth8"],
        "B1+slope12": list(F.B1_FEATS) + ["sct_slope12"],
        "B1+volatility8": list(F.B1_FEATS) + ["sct_volatility8"],
        "B1+pma_share4": list(F.B1_FEATS) + ["sct_pma_share4"],
        "B1+H8_full(7)": list(F.B1_FEATS + F.GROWTH_FEATS),
    }
    for name, feats in blocks.items():
        out["feature_blocks"].append(run_arm(panel, feats, name, store=block_oof))
    if block_oof:
        pd.concat(block_oof, ignore_index=True).to_csv(
            RESULTS / "oof_extra_blocks.csv", index=False)

    out["elapsed_sec"] = round(time.time() - t0, 1)
    (RESULTS / "exp_extra_mechanism.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    say(f"\n# wrote results/exp_extra_mechanism.json  elapsed={out['elapsed_sec']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
