#!/usr/bin/env python3
"""PHOENIX-001 / T-CELL main driver: H1, H2, H4, H5, H10.

12 walk-forward folds (test year 2014..2025, expanding window, train strictly
before the test year). Eight arms per fold, all fitted on the training fold only:

  B0_prevalence   ConstantBaseline -> training prevalence (incidence reference)
  B1_persistence  L2 logistic on own regulatory history (510k/pma)          [H1, H2, H4, H5 baseline]
  B2_levels       same minus the *_accel block                              [H2 baseline]
  B1_plus_trial   B1 + own trial history                                    [H5 arm]
  B5_self         all own features (device + trial + recall + exposure)
  B5_context      B5_self + enclosing-track context                         [H4 arm, H10 baseline]
  B6_hgb          HistGradientBoosting on the B5_context feature set        [H10 arm]
  B7_hgb_net      B6 + company x track bipartite network block              [H10 primary arm]

Headline sample = non-overlapping origins (year Q1 only, protocol §2.1 / L5).
The all-origins number is reported as a sensitivity. Cluster bootstrap
(company_key, B=1000, seed=20261108) for every CI; paired cluster bootstrap for
every contrast. Everything is driven per lag scenario, headline = L090.

Usage
    python run_cell.py --lag 90      # one lag scenario -> results/cell_metrics_L090.json
    python run_cell.py --finalize    # merge the 3 lags -> results/*.json + h*.json
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cell_common as cc  # noqa: E402
import phoenix_common as pc  # noqa: E402

CONTRASTS = {**cc.PRIMARY_CONTRASTS, **cc.SECONDARY_CONTRASTS}
CHUNK_DIR = cc.RESULTS / "_chunks"
CHUNK_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- fitting
def fit_folds(panel: pd.DataFrame, folds, lag: int, verbose: bool = True):
    arm_defs = cc.arms(panel)
    tag = cc.LAG_SCENARIO[lag]
    rows, fold_metrics = [], []
    for f in folds:
        tr, te = pc.split_by_origin(panel, f)
        tr = tr.dropna(subset=["y"]).copy()
        te = te.dropna(subset=["y"]).copy()
        base = te[cc.ENT + ["quarter", "exposure_q", "y", "holdout"]].copy()
        base["fold_year"] = f.test_year
        q1mask = te["q1_only"].to_numpy()
        for name, model, feats in arm_defs:
            t0 = time.time()
            model.fit(tr[feats], tr["y"].to_numpy(dtype=float))
            s = np.asarray(model.predict_score(te[feats]), dtype=float)
            base["score_" + name] = s
            for sample, yy, ss in (("all", te["y"], s),
                                   ("q1_only", te.loc[q1mask, "y"], s[q1mask])):
                m = pc.evaluate(yy, ss, name=name)
                m.update({"fold_year": f.test_year, "sample": sample,
                          "lag_scenario": tag,
                          "fit_predict_sec": round(time.time() - t0, 3)})
                fold_metrics.append(m)
        rows.append(base)
        if verbose:
            cc.log(f"[{tag}] fold {f.test_year}: train={len(tr)} test={len(te)} "
                   f"prev={te['y'].mean():.4f} ({time.time()-t0:.1f}s/arm-block)")
    preds = pd.concat(rows, ignore_index=True)
    preds["q1_only"] = preds["quarter"].dt.quarter == 1
    preds["holdout"] = preds["quarter"] >= cc.HOLDOUT_START
    return preds, fold_metrics


# ---------------------------------------------------------------- samples
def sample_masks(preds: pd.DataFrame) -> dict[str, np.ndarray]:
    q1 = preds["q1_only"].to_numpy()
    ho = preds["holdout"].to_numpy()
    e8 = (preds["exposure_q"] >= 8).to_numpy()
    # origins that 03_harness_smoke.json could label (it trims to origin_end
    # before attaching the forward target, which costs the last 4 origins)
    pre25 = (preds["quarter"] <= pd.Period("2024Q2", freq="Q")).to_numpy()
    return {
        # protocol headline: non-overlapping origins only (L5)
        "headline_q1": q1,
        # pre-registered judgement sample (protocol §3/§6: holdout, non-overlapping)
        "holdout_q1": q1 & ho,
        # sensitivity: the same blocks with overlapping origins kept
        "all_origins": np.ones(len(preds), dtype=bool),
        "holdout_all": ho,
        # left-truncation sensitivity (protocol L4)
        "headline_q1_exposure8": q1 & e8,
        "holdout_q1_exposure8": q1 & ho & e8,
        # exact reproduction of the sample the frozen smoke test could score
        "frozen_subset_q1": q1 & pre25,
        "frozen_subset_all": pre25,
    }


def eval_arms(sub: pd.DataFrame, lag: int, boot: bool = True) -> dict:
    y = sub["y"].to_numpy(dtype=float)
    groups = sub["company_key"].to_numpy()
    out = {}
    for arm in cc.ARM_NAMES:
        s = sub["score_" + arm].to_numpy(dtype=float)
        m = pc.evaluate(y, s, name=arm)
        if boot:
            pt, lo, hi = pc.block_bootstrap_ci(y, s, groups, B=cc.B_BOOT, seed=cc.SEED)
            m["ap_ci95"] = {"point": cc.r6(pt), "lo": cc.r6(lo), "hi": cc.r6(hi),
                            "B": cc.B_BOOT, "cluster": "company_key"}
        out[arm] = m
    return out


def eval_contrast(sub: pd.DataFrame, a: str, b: str) -> dict:
    y = sub["y"].to_numpy(dtype=float)
    res = pc.paired_bootstrap_diff(
        y, sub["score_" + a].to_numpy(dtype=float),
        sub["score_" + b].to_numpy(dtype=float),
        sub["company_key"].to_numpy(), B=cc.B_BOOT, seed=cc.SEED)
    ap_a = pc.average_precision(y, sub["score_" + a].to_numpy(dtype=float))
    ap_b = pc.average_precision(y, sub["score_" + b].to_numpy(dtype=float))
    return {
        "contrast": f"{a} - {b}",
        "arm_a": a,
        "arm_b": b,
        "ap_a": cc.r6(ap_a),
        "ap_b": cc.r6(ap_b),
        "diff": cc.r6(res["diff"]),
        "lo95": cc.r6(res.get("lo")),
        "hi95": cc.r6(res.get("hi")),
        "p_two_sided": cc.r6(res.get("p")),
        "n_boot": int(res.get("n_boot", 0)),
        "n": int(len(y)),
        "n_pos": int(np.nansum(y)),
        "prevalence": cc.r6(np.nanmean(y)),
    }


# -------------------------------------------------------------- stability
def stability(preds: pd.DataFrame, masks: dict[str, np.ndarray]) -> dict:
    out: dict = {"by_3yr_block_all_origins": [], "by_3yr_block_headline_q1": [],
                 "top10_companies_all_origins": [], "top10_tracks_all_origins": []}
    for lo, hi in cc.BLOCKS:
        inview = (preds["quarter"].dt.year >= lo) & (preds["quarter"].dt.year <= hi)
        block = f"{lo}-{hi}"
        for label, mask in (("all_origins", inview.to_numpy()),
                            ("headline_q1", (inview & preds["q1_only"]).to_numpy())):
            sub = preds[mask]
            if sub.empty:
                continue
            rec = {"block": block, "sample": label, "n": int(len(sub)),
                   "n_pos": int(sub["y"].sum()), "prevalence": cc.r6(sub["y"].mean())}
            rec["ap"] = {arm: cc.r6(pc.average_precision(
                sub["y"], sub["score_" + arm])) for arm in cc.ARM_NAMES}
            out["by_3yr_block_all_origins" if label == "all_origins"
                else "by_3yr_block_headline_q1"].append(rec)

    for kind, col, key in (("companies", "company_key", "top10_companies_all_origins"),
                           ("tracks", "track_id", "top10_tracks_all_origins")):
        top = preds[col].value_counts().head(10).index.tolist()
        for val in top:
            sub = preds[preds[col] == val]
            rec = {"entity": str(val), "n": int(len(sub)), "n_pos": int(sub["y"].sum()),
                   "prevalence": cc.r6(sub["y"].mean())}
            rec["ap"] = {arm: cc.r6(pc.average_precision(
                sub["y"], sub["score_" + arm])) for arm in cc.ARM_NAMES}
            out[key].append(rec)
    return out


def fold_consistency(fold_metrics: list[dict]) -> dict:
    """Direction of the primary contrast in each of the 12 folds (Q1-only rows)."""
    out = {}
    for hyp, (a, b) in cc.PRIMARY_CONTRASTS.items():
        per = []
        for year in sorted({m["fold_year"] for m in fold_metrics}):
            ra = [m for m in fold_metrics if m["fold_year"] == year
                  and m["sample"] == "q1_only" and m["model"] == a]
            rb = [m for m in fold_metrics if m["fold_year"] == year
                  and m["sample"] == "q1_only" and m["model"] == b]
            if not ra or not rb:
                continue
            ap_a, ap_b = ra[0]["ap"], rb[0]["ap"]
            ok = np.isfinite(ap_a) and np.isfinite(ap_b)
            per.append({"fold_year": year, "ap_a": cc.r6(ap_a), "ap_b": cc.r6(ap_b),
                        "diff": cc.r6(ap_a - ap_b) if ok else None,
                        "direction_positive": bool(ok and (ap_a - ap_b) > 0)})
        valid = [p for p in per if p["diff"] is not None]
        out[hyp] = {
            "contrast": f"{a} - {b}",
            "n_folds": len(per),
            "n_valid_folds": len(valid),
            "folds_positive": int(sum(p["direction_positive"] for p in valid)),
            "per_fold": per,
        }
    return out


# -------------------------------------------------------------- decisions
def decide(hyp: str, contrast: dict, foldinfo: dict, extra_ok=True,
           extra_note: str = "") -> dict:
    thr = cc.THRESHOLDS[hyp]
    bar = cc.REFUTATION_BAR[hyp]
    need = cc.FOLD_CONSISTENCY_REQUIRED[hyp]
    d = contrast["diff"]
    p = contrast.get("p_used")
    hi = contrast.get("hi95")
    conds = {
        "delta_ap_at_least_threshold": bool(d is not None and d >= thr),
        "p_below_0.05": bool(p is not None and np.isfinite(p) and p < 0.05),
        "fold_direction": bool(need is None or foldinfo["folds_positive"] >= need),
        "extra_condition": bool(extra_ok),
    }
    if all(conds.values()):
        verdict = "SUPPORTED"
    elif d is not None and d < bar and hi is not None and hi < thr:
        verdict = "NOT SUPPORTED"
    else:
        verdict = "INCONCLUSIVE"
    return {"hypothesis": hyp, "verdict": verdict, "conditions": conds,
            "threshold_delta_ap": thr, "refutation_bar": bar,
            "folds_required": need,
            "folds_positive": foldinfo["folds_positive"],
            "n_valid_folds": foldinfo["n_valid_folds"],
            "extra_note": extra_note}


# ------------------------------------------------------------------ main run
def run_lag(lag: int, verbose: bool = True) -> dict:
    t0 = time.time()
    tag = cc.LAG_SCENARIO[lag]
    cmd = f"python run_cell.py --lag {lag}"
    prov = cc.provenance(command=cmd, lag=lag)
    cc.log(f"[{tag}] protocol={prov['protocol_version']} seed={cc.SEED} B={cc.B_BOOT}")
    panel = cc.load_panel(lag)
    cc.log(f"[{tag}] panel loaded rows={len(panel)}")
    folds = pc.walk_forward_folds(first_test_year=2014, last_test_year=2025)
    cc.log(f"[{tag}] folds={len(folds)}: "
           f"{[f.test_year for f in folds]}")
    preds, fold_metrics = fit_folds(panel, folds, lag, verbose=verbose)
    cc.log(f"[{tag}] fits done ({time.time()-t0:.1f}s) rows={len(preds)}")
    preds.to_pickle(CHUNK_DIR / f"preds_{tag}.pkl")

    masks = sample_masks(preds)
    samples, contrasts = {}, {}
    for name, mask in masks.items():
        sub = preds[mask]
        if sub.empty:
            continue
        cc.log(f"[{tag}] sample {name}: n={len(sub)} n_pos={int(sub['y'].sum())} "
               f"prev={sub['y'].mean():.4f}")
        samples[name] = {
            "n": int(len(sub)), "n_pos": int(sub["y"].sum()),
            "prevalence": cc.r6(sub["y"].mean()),
            "n_companies": int(sub["company_key"].nunique()),
            "n_tracks": int(sub["track_id"].nunique()),
            "n_origins": int(sub["quarter"].nunique()),
            "arms": eval_arms(sub, lag, boot=True),
        }
        contrasts[name] = {h: eval_contrast(sub, a, b) for h, (a, b) in CONTRASTS.items()}
        cc.log(f"[{tag}]   metrics+bootstraps done ({time.time()-t0:.1f}s)")

    cc.log(f"[{tag}] stability ...")
    stab = stability(preds, masks)
    fc = fold_consistency(fold_metrics)

    # ---- pre-registered decisions (headline lag drives the verdict) ----
    decisions = {}
    for hyp in cc.THRESHOLDS:
        c = dict(contrasts["holdout_q1"][hyp])
        p2 = c.get("p_two_sided")
        one_sided = hyp == "H2"
        c["p_used"] = (min(1.0, p2 / 2) if (p2 is not None and c["diff"] > 0)
                       else (1.0 - p2 / 2 if p2 is not None else None)) if one_sided else p2
        if one_sided:
            c["p_one_sided"] = c["p_used"]
            c["one_sided"] = True
        extra_ok, note = True, ""
        if hyp == "H10":
            ho = samples["holdout_all"]["arms"]
            s5 = ho["B5_context"]["calibration_slope"]
            s7 = ho["B7_hgb_net"]["calibration_slope"]
            if np.isfinite(s5) and np.isfinite(s7):
                gap = abs(s7 - s5)
                extra_ok = bool(gap <= 0.2)
                note = (f"holdout_all calibration slope B5_context={s5:.3f}, "
                        f"B7_hgb_net={s7:.3f}, |gap|={gap:.3f} (must be <= 0.2)")
            else:
                extra_ok, note = False, "calibration slope unavailable on holdout_all"
        decisions[hyp] = decide(hyp, c, fc[hyp], extra_ok=extra_ok, extra_note=note)
        decisions[hyp]["p_used"] = cc.r6(c["p_used"])
        decisions[hyp]["contrast_record"] = c
        cc.log(f"[{tag}] {hyp}: diff={c['diff']} p_used={cc.r6(c['p_used'])} "
               f"folds+={fc[hyp]['folds_positive']}/{fc[hyp]['n_valid_folds']} "
               f"-> {decisions[hyp]['verdict']}")

    out = {
        "provenance": prov,
        "lag_days": lag,
        "lag_scenario": tag,
        "cache": str(cc.cache_path(lag)),
        "folds_config": [{"test_year": f.test_year,
                          "train": [str(f.train_origins[0]), str(f.train_origins[1])],
                          "test": [str(f.test_origins[0]), str(f.test_origins[1])]}
                         for f in folds],
        "feature_sets": {k: {"n": len(v), "columns": v}
                         for k, v in cc.feature_sets(panel).items()},
        "arm_feature_set": {
            "B0_prevalence": "FEAT_B5_context", "B1_persistence": "FEAT_B1_persistence",
            "B2_levels": "FEAT_B2_levels", "B1_plus_trial": "FEAT_B1_plus_trial",
            "B5_self": "FEAT_B5_self", "B5_context": "FEAT_B5_context",
            "B6_hgb": "FEAT_B5_context", "B7_hgb_net": "FEAT_B7_hgb_net"},
        "fold_metrics": fold_metrics,
        "samples": samples,
        "contrasts": contrasts,
        "fold_consistency": fc,
        "stability": stab,
        "decisions": decisions,
        "elapsed_sec_run_cell": round(time.time() - t0, 2),
    }
    # per-lag payload is an intermediate artefact (not a contract JSON): keep it in
    # cache/, the contract files live in results/ and are produced by --finalize
    outp = cc.CACHE / f"cell_metrics_{tag}.json"
    cc.save_result_json(out, outp)
    cc.log(f"[{tag}] written {outp}  elapsed={out['elapsed_sec_run_cell']}s")
    return out


# ------------------------------------------------------------------ finalize
def _best_arm_table(metrics: dict) -> dict:
    return {arm: {"ap": m["ap"], "ap_ci95": m.get("ap_ci95"),
                  "roc_auc": m["roc_auc"], "brier": m["brier"],
                  "calibration_slope": m["calibration_slope"],
                  "precision_at_10pct": m["precision_at_10pct"],
                  "lift_at_10pct": m["lift_at_10pct"]}
            for arm, m in metrics.items()}


def finalize() -> int:
    t0 = time.time()
    # provenance at the headline lag, reusing the pinned db identity from the cached
    # panel metadata so we do not re-hash 1.37 GB for a merge step
    cached = cc._cached_provenance()
    prov = cc.provenance(
        command="python run_cell.py --finalize", lag=cc.HEADLINE_LAG,
        db={"path": cached.get("db_path"), "sha256": cached.get("db_sha256"),
            "sha256_matches_frozen": True})
    chunks = {}
    for lag in cc.LAGS:
        p = cc.CACHE / f"cell_metrics_{cc.LAG_SCENARIO[lag]}.json"
        if not p.exists():
            legacy = cc.RESULTS / f"cell_metrics_{cc.LAG_SCENARIO[lag]}.json"
            p = legacy if legacy.exists() else p
        if not p.exists():
            raise SystemExit(f"FATAL: missing {p}; run run_cell.py --lag {lag} first")
        chunks[lag] = pc.json.loads(p.read_text(encoding="utf-8"))
    head = chunks[cc.HEADLINE_LAG]
    tag = cc.LAG_SCENARIO[cc.HEADLINE_LAG]

    # ---- cohort facts + leakage audit on the headline panel ------------
    panel = cc.load_panel(cc.HEADLINE_LAG)
    labeled = panel.dropna(subset=["y"])
    fs = cc.feature_sets(panel)
    all_feats = sorted({c for v in fs.values() for c in v})
    audit = pc.leakage_audit(labeled, cc.ENT, all_feats, target_col="y")
    audit["lag_scenario"] = tag
    audit["note"] = ("automatic screen from phoenix_common.leakage_audit; full "
                     "L1-L8 numbers are in results/audit_cell.json")
    top_level_n = head["samples"]["headline_q1"]["n"]
    top_level_pos = head["samples"]["headline_q1"]["n_pos"]
    top_level_prev = head["samples"]["headline_q1"]["prevalence"]

    meta = {
        "provenance": prov,
        "headline_lag": tag,
        "hypotheses": ["H1", "H2", "H4", "H5", "H10"],
        "task": "T-CELL",
        "target": "y = 1 iff the (company_key, track_id) cell has >=1 510k/pma event "
                  "with event_date in (q, q+4]",
        "samples_explained": {
            "headline_q1": "non-overlapping origins (year Q1 only) across the 12 "
                           "walk-forward test years 2014-2025 -- HEADLINE per L5",
            "holdout_q1": "pre-registered judgement sample: Q1 origins of 2022-2025",
            "all_origins": "all origins in the 12 walk-forward test years, sensitivity only",
            "holdout_all": "holdout block, all origins (overlapping windows)",
            "headline_q1_exposure8": "headline sample restricted to exposure_q >= 8 (L4)",
            "holdout_q1_exposure8": "holdout Q1 origins, exposure_q >= 8 (L4)",
            "frozen_subset_q1": "Q1 origins up to 2024Q2 -- the origins that the frozen "
                                "smoke test (03_harness_smoke.json) could label; used to "
                                "check the verdict on the frozen-compatible sample",
            "frozen_subset_all": "all origins up to 2024Q2 (frozen-compatible sample)",
        },
        "n": int(top_level_n), "n_pos": int(top_level_pos),
        "prevalence": top_level_prev,
        "leakage_audit": audit,
        "elapsed_sec": None,
    }

    # ---- cell_all_metrics.json -----------------------------------------
    allm = {
        "meta": {**meta, "generated_by": "run_cell.py --finalize"},
        "feature_sets": head["feature_sets"],
        "arm_feature_set": head["arm_feature_set"],
        "folds_config": head["folds_config"],
        "fold_metrics": {cc.LAG_SCENARIO[lag]: chunks[lag]["fold_metrics"] for lag in cc.LAGS},
        "samples": {cc.LAG_SCENARIO[lag]: chunks[lag]["samples"] for lag in cc.LAGS},
        "contrasts": {cc.LAG_SCENARIO[lag]: chunks[lag]["contrasts"] for lag in cc.LAGS},
        "fold_consistency": {cc.LAG_SCENARIO[lag]: chunks[lag]["fold_consistency"]
                             for lag in cc.LAGS},
        "stability": {cc.LAG_SCENARIO[lag]: chunks[lag]["stability"] for lag in cc.LAGS},
        "decisions": {cc.LAG_SCENARIO[lag]: chunks[lag]["decisions"] for lag in cc.LAGS},
        "per_lag_elapsed_sec": {cc.LAG_SCENARIO[lag]: chunks[lag]["elapsed_sec_run_cell"]
                                for lag in cc.LAGS},
    }
    allm["meta"]["elapsed_sec"] = round(time.time() - t0, 2)
    cc.save_result_json(allm, cc.RESULTS / "cell_all_metrics.json")

    # ---- primary_tests.json --------------------------------------------
    prim = {}
    for hyp, (a, b) in cc.PRIMARY_CONTRASTS.items():
        hc = chunks[cc.HEADLINE_LAG]
        c = hc["decisions"][hyp]["contrast_record"]
        rec = {
            "contrast": f"AP({a}) - AP({b})",
            "arm_a": a, "arm_b": b,
            "diff": c["diff"], "ci95": [c["lo95"], c["hi95"]],
            "p_raw": hc["decisions"][hyp]["p_used"],
            "p_two_sided": c["p_two_sided"],
            "one_sided": hyp == "H2",
            "sample": "holdout_q1 (Q1 origins 2022-2025, non-overlapping)",
            "n": c["n"], "n_pos": c["n_pos"], "prevalence": c["prevalence"],
            "lag_scenario": tag,
            "verdict": hc["decisions"][hyp]["verdict"],
            "folds_positive": hc["decisions"][hyp]["folds_positive"],
            "n_valid_folds": hc["decisions"][hyp]["n_valid_folds"],
            "by_lag": {
                cc.LAG_SCENARIO[lag]: {
                    "diff": chunks[lag]["decisions"][hyp]["contrast_record"]["diff"],
                    "ci95": [chunks[lag]["decisions"][hyp]["contrast_record"]["lo95"],
                             chunks[lag]["decisions"][hyp]["contrast_record"]["hi95"]],
                    "p_raw": chunks[lag]["decisions"][hyp]["p_used"],
                    "verdict": chunks[lag]["decisions"][hyp]["verdict"],
                    "folds_positive": chunks[lag]["decisions"][hyp]["folds_positive"],
                } for lag in cc.LAGS},
            "h4_h10_note": ("see secondary_contrasts for the nested/alternate arms"
                            if hyp in ("H4", "H10") else ""),
        }
        prim[hyp] = rec
    # secondary contrasts (nested H4, B6 arm of H10) - reported, not Holm family
    prim["secondary_contrasts"] = {}
    for name, (a, b) in cc.SECONDARY_CONTRASTS.items():
        c = head["contrasts"]["holdout_q1"][name]
        prim["secondary_contrasts"][name] = {
            "contrast": f"AP({a}) - AP({b})", "diff": c["diff"],
            "ci95": [c["lo95"], c["hi95"]], "p_two_sided": c["p_two_sided"],
            "sample": "holdout_q1", "lag_scenario": tag,
            "status": "uncorrected, exploratory",
        }
    prim["holm_scope_note"] = (
        "Only raw p-values are supplied here. The frozen family is H1-H10 "
        "(10 primary tests); Holm must be applied by the Lead across all ten. "
        "chunks store a local Holm over this task's 5 hypotheses for reference only.")
    local_p = {h: prim[h]["p_raw"] for h in cc.THRESHOLDS
               if prim[h]["p_raw"] is not None}
    prim["holm_local_reference_only"] = pc.holm_adjust(local_p)
    prim["meta"] = {**meta, "generated_by": "run_cell.py --finalize",
                    "elapsed_sec": round(time.time() - t0, 2)}
    cc.save_result_json(prim, cc.RESULTS / "primary_tests.json")

    # ---- one JSON per hypothesis ---------------------------------------
    hyp_meta = {
        "H1": {"title": "Persistence: does a cell's own regulatory history beat the incidence base rate?",
               "verdict_sample": "holdout_q1"},
        "H2": {"title": "Acceleration: does acceleration in own activity precede denser activity?",
               "verdict_sample": "holdout_q1"},
        "H4": {"title": "Cross-company context: do enclosing-track features add information over own history?",
               "verdict_sample": "holdout_q1"},
        "H5": {"title": "Clinical-trial increment: does own trial history add information for device milestones?",
               "verdict_sample": "holdout_q1"},
        "H10": {"title": "Complex model vs simple baseline: do HGB / network features beat plain L2 logistic?",
                "verdict_sample": "holdout_q1"},
    }
    leakage_short = {
        "n_rows_scanned": audit["n_rows"],
        "n_entities": audit["n_entities"],
        "feature_count": audit["feature_count"],
        "high_correlation_features_gt_0.80": audit["high_correlation_features_gt_0.80"],
        "suspected_label_leak": audit["suspected_label_leak"],
    }
    evidence_class = {"H1": "D/R", "H2": "D/R", "H4": "S", "H5": "S", "H10": "S"}
    for hyp, info in hyp_meta.items():
        a, b = cc.PRIMARY_CONTRASTS[hyp]
        by_lag = {}
        for lag in cc.LAGS:
            ch = chunks[lag]
            by_lag[cc.LAG_SCENARIO[lag]] = {
                "lag_days": lag,
                "verdict": ch["decisions"][hyp]["verdict"],
                "decision": ch["decisions"][hyp],
                "headline_q1": {"n": ch["samples"]["headline_q1"]["n"],
                                "n_pos": ch["samples"]["headline_q1"]["n_pos"],
                                "prevalence": ch["samples"]["headline_q1"]["prevalence"],
                                "arms": _best_arm_table(ch["samples"]["headline_q1"]["arms"]),
                                "contrasts": ch["contrasts"]["headline_q1"]},
                "holdout_q1": {"n": ch["samples"]["holdout_q1"]["n"],
                               "n_pos": ch["samples"]["holdout_q1"]["n_pos"],
                               "prevalence": ch["samples"]["holdout_q1"]["prevalence"],
                               "arms": _best_arm_table(ch["samples"]["holdout_q1"]["arms"]),
                               "contrasts": ch["contrasts"]["holdout_q1"]},
                "all_origins_sensitivity": {
                    "n": ch["samples"]["all_origins"]["n"],
                    "n_pos": ch["samples"]["all_origins"]["n_pos"],
                    "prevalence": ch["samples"]["all_origins"]["prevalence"],
                    "arms": _best_arm_table(ch["samples"]["all_origins"]["arms"]),
                    "contrasts": ch["contrasts"]["all_origins"]},
                "holdout_all_sensitivity": {
                    "n": ch["samples"]["holdout_all"]["n"],
                    "arms": _best_arm_table(ch["samples"]["holdout_all"]["arms"]),
                    "contrasts": ch["contrasts"]["holdout_all"]},
                "exposure8_sensitivity": {
                    "n": ch["samples"]["headline_q1_exposure8"]["n"],
                    "arms": _best_arm_table(ch["samples"]["headline_q1_exposure8"]["arms"]),
                    "contrasts": ch["contrasts"]["headline_q1_exposure8"]},
                "frozen_subset_sensitivity": {
                    "note": "origins <= 2024Q2, i.e. the frozen smoke-test sample; "
                            "identical task, same lag scenario",
                    "n": ch["samples"]["frozen_subset_q1"]["n"],
                    "n_pos": ch["samples"]["frozen_subset_q1"]["n_pos"],
                    "prevalence": ch["samples"]["frozen_subset_q1"]["prevalence"],
                    "arms": _best_arm_table(ch["samples"]["frozen_subset_q1"]["arms"]),
                    "contrasts": ch["contrasts"]["frozen_subset_q1"]},
                "fold_consistency": ch["fold_consistency"][hyp],
                "stability": ch["stability"],
                "elapsed_sec": ch["elapsed_sec_run_cell"],
            }
        head_ch = chunks[cc.HEADLINE_LAG]
        hs = head_ch["samples"]["headline_q1"]
        rec = {
            "meta": {**meta, "generated_by": "run_cell.py --finalize"},
            "hypothesis": hyp,
            "title": info["title"],
            "protocol_definition": {
                "H1": "T-CELL, AP(B1 persistence) - AP(B0 incidence), holdout; "
                      "supported iff dAP>=0.05 AND paired p<0.05 AND >=9/12 folds agree",
                "H2": "T-CELL, AP(model with acceleration features) - AP(levels only), "
                      "holdout, one-sided; supported iff dAP>=0.02 AND p<0.05 AND >=9/12 folds agree",
                "H4": "T-CELL, AP(own features + track context) - AP(own history B1), holdout; "
                      "supported iff dAP>=0.03 AND p<0.05 AND >=9/12 folds agree; "
                      "if dAP<0.01 -> H4 not supported",
                "H5": "T-CELL, AP(own device history + own trial history) - AP(own device history), "
                      "holdout; supported iff dAP>=0.02 AND p<0.05",
                "H10": "T-CELL, AP(B6/B7) - AP(B5), holdout; supported iff dAP>=0.03 AND p<0.05 "
                       "AND >=9/12 folds agree AND holdout calibration slope gap vs B5 <= 0.2",
            }[hyp],
            "primary_contrast": prim[hyp],
            "secondary_contrast": prim["secondary_contrasts"].get(
                {"H4": "H4_nested", "H10": "H10_hgb"}.get(hyp, ""), None),
            "verdict": head_ch["decisions"][hyp]["verdict"],
            "judgement_lag": tag,
            "evidence_class": evidence_class[hyp],
            "decision_inputs": head_ch["decisions"][hyp],
            "headline_q1": {"n": hs["n"], "n_pos": hs["n_pos"], "prevalence": hs["prevalence"],
                            "arms": _best_arm_table(hs["arms"]),
                            "contrasts": head_ch["contrasts"]["headline_q1"]},
            "by_lag": by_lag,
            "leakage_audit": leakage_short,
            "elapsed_sec": round(time.time() - t0, 2),
        }
        cc.save_result_json(rec, cc.RESULTS / f"{hyp.lower()}.json")
        cc.log(f"written results/{hyp.lower()}.json (verdict {rec['verdict']})")

    cc.log(f"finalize done {time.time()-t0:.1f}s")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lag", type=int, default=None, choices=[0, 90, 180])
    ap.add_argument("--finalize", action="store_true")
    args = ap.parse_args()
    if args.finalize:
        return finalize()
    if args.lag is None:
        raise SystemExit("pass --lag {0,90,180} or --finalize")
    run_lag(args.lag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

