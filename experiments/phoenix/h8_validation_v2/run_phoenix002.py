"""PHOENIX-002 main experiment entry point.

Runs experiments 2-6 plus the adversarial battery, writes one result JSON per
experiment, a summary JSON with the mechanical verdict, and the out-of-fold
predictions used by the independent verifier.

Usage:
    python run_phoenix002.py                 # full run (~10-15 min)
    python run_phoenix002.py --skip-exp1     # if exp1_v1_replication.py already ran

Everything is deterministic (seed in protocol.py).  Read-only database.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime
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
for _d in (RESULTS, EVIDENCE):
    _d.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------------- logging
class Log:
    def __init__(self, name: str):
        self.t0 = time.time()
        self.path = EVIDENCE / f"{name}.log"
        self.fh = self.path.open("w", encoding="utf-8")
        self.write(f"# PHOENIX-002 experiment log: {name}")
        self.write(f"# start: {datetime.now().astimezone().isoformat(timespec='seconds')}")
        self.write(f"# protocol: {P.PROTOCOL_VERSION}  seed: {P.SEED}")

    def write(self, msg: object = "") -> None:
        line = str(msg)
        print(line, flush=True)
        self.fh.write(line + "\n")
        self.fh.flush()

    def step(self, msg: object) -> None:
        self.write(f"[{time.time() - self.t0:8.2f}s] {msg}")

    def close(self) -> None:
        self.write(f"# end: {datetime.now().astimezone().isoformat(timespec='seconds')}")
        self.write(f"# elapsed_sec: {time.time() - self.t0:.2f}")
        self.fh.close()


def sanitize(o):
    if isinstance(o, dict):
        return {str(k): sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [sanitize(v) for v in o]
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return v if np.isfinite(v) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Period):
        return str(o)
    return o


def save(obj, name: str) -> Path:
    p = RESULTS / name
    p.write_text(json.dumps(sanitize(obj), indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def brief(res: dict, a: str = "M4_h8_growth", b: str = "M1_persistence") -> dict:
    """Compact contrast summary for logging and aggregation."""
    c = res.get("contrasts", {}).get(f"{a} - {b}", {})
    return {
        "n": res.get("n"), "n_pos": res.get("n_pos"),
        "prevalence": res.get("prevalence"), "n_tracks": res.get("n_tracks"),
        "ap_a": c.get("ap_a"), "ap_b": c.get("ap_b"), "dap": c.get("diff"),
        "ci95": [c.get("lo"), c.get("hi")], "p": c.get("p"),
        "ci_width": c.get("ci_width"),
        "folds_ok": sum(1 for f in res.get("folds", []) if f.get("status") == "OK"),
        "maturity_violating_share": res.get("maturity", {}).get("total_violating_share"),
    }


# ------------------------------------------------------------------------ helpers
def prep_panel(universe: str, lag: int, mode: str = "v2",
               coverage: dict | None = None,
               dedupe: bool = False) -> pd.DataFrame:
    panel = D.build_panel(universe, lag, mode=mode)
    if dedupe:
        panel = _dedupe_panel(panel, universe, lag, mode)
    panel = F.build_features(panel)
    if coverage is not None:
        panel = R.add_attribution_rate(panel, coverage)
    return panel


def _dedupe_panel(panel: pd.DataFrame, universe: str, lag: int, mode: str) -> pd.DataFrame:
    """Rebuild counts after dropping duplicate regulatory records.

    Dedupe key: (kind, track_id, event_date, product_code, company_key).  This keeps
    distinct applicants on the same day and drops only exact duplicate records.
    Implemented by rebuilding the panel from a deduplicated event table.
    """
    require_company = universe in ("attr38", "attr59")
    ev = D.load_events(P.ALL_KINDS, require_company=require_company)
    tracks = D.universe_tracks(ev, universe)
    ev = ev[ev["track_id"].isin(tracks)].copy()
    ev = ev.drop_duplicates(subset=["kind", "track_id", "event_dt", "product_code",
                                    "company_key"])
    # temporarily rebuild using data.build_panel machinery: monkeypatch load_events
    orig = D.load_events
    try:
        D.load_events = lambda kinds=P.ALL_KINDS, require_company=False: ev.copy()  # noqa: ARG005
        panel2 = D.build_panel(universe, lag, mode=mode)
    finally:
        D.load_events = orig
    return panel2


def alt_target_panel(panel: pd.DataFrame, count_col: str) -> pd.DataFrame:
    """Rewrite `n_device` as another event count and recompute labels (negative control)."""
    out = panel.copy()
    out["n_device"] = out[count_col].to_numpy(dtype=float)
    out = D.add_targets(out)
    return out


def subset_contrast(oof: pd.DataFrame, mask: np.ndarray, a: str, b: str,
                    B: int = P.B_BOOT) -> dict:
    sub = oof[mask]
    rec = {"n": int(len(sub)), "n_pos": int(sub["y"].sum())}
    if sub.empty or sub["y"].sum() < 3 or sub["y"].nunique() < 2:
        rec["status"] = "TOO_SMALL"
        return rec
    c = M.contrast(sub, a, b, B=B)
    rec.update(c)
    return rec


# ============================================================== experiment blocks
def exp2_maturity(log: Log, panels: dict, coverage: dict) -> dict:
    """Experiment 2: mature-label isolation on the published construct and on v2."""
    log.step("EXP2 maturity isolation")
    out = {"experiment": "EXP2_MATURITY_ISOLATION",
           "question": "Does excluding training labels not yet observable at the test "
                       "decision time change AP / dAP / evaluable sample?",
           "configs": {}}
    p59 = panels[("attr59", 90)]
    for lag_label in (0, 90, 180):
        for rule in ("v1_naive", "purged"):
            key = f"attr59_v1like_L90_labelL{lag_label:03d}_{rule}"
            res, oof = R.run_config(p59, f"y_{P.PRIMARY_TARGET}", rule, lag_label,
                                    arms=("M0_prevalence", "M1_persistence", "M4_h8_growth"),
                                    with_ci=True)
            out["configs"][key] = {
                "brief": brief(res),
                "maturity": {"purge_quarters_required": res["maturity"]["purge_quarters_required"],
                             "violating_rows": res["maturity"]["total_violating_training_rows"],
                             "violating_share": res["maturity"]["total_violating_share"],
                             "rows_depending_on_test_period": res["maturity"]["total_rows_depending_on_test_period_events"],
                             "leak_channel_share": res["maturity"]["total_leak_channel_share"]},
                "arms": {k: {kk: vv for kk, vv in v.items() if kk in
                             ("model", "n", "n_pos", "prevalence", "ap", "ap_ci95")}
                         for k, v in res["arms"].items()},
            }
            log.step(f"  {key}: n={res['n']} pos={res['n_pos']} "
                     f"dAP={brief(res)['dap']:+.4f} CI={brief(res)['ci95']} "
                     f"viol={res['maturity']['total_violating_training_rows']}"
                     f"/{res['maturity']['total_training_rows']}")
            # keep primary comparison OOF
            if lag_label == P.HEADLINE_LABEL_LAG and rule == "purged":
                oof.to_csv(RESULTS / "oof_attr59_purged.csv", index=False)
    p38 = panels[("attr38", 90)]
    for rule in ("v1_naive", "purged"):
        key = f"attr38_v2_L90_labelL090_{rule}"
        res, oof = R.run_config(p38, f"y_{P.PRIMARY_TARGET}", rule, 90,
                               arms=("M0_prevalence", "M1_persistence", "M4_h8_growth"))
        out["configs"][key] = {"brief": brief(res),
                               "maturity": res["maturity"]}
        log.step(f"  {key}: n={res['n']} pos={res['n_pos']} dAP={brief(res)['dap']:+.4f} "
                 f"CI={brief(res)['ci95']}")
    return out


def exp3_risksets(log: Log, panels: dict) -> dict:
    """Experiment 3: structurally-impossible units and the real predictable risk set."""
    log.step("EXP3 risk set / universe")
    out = {"experiment": "EXP3_PREDICTABLE_RISK_SET",
           "question": "What happens when tracks that can never carry a device label are "
                       "removed and the universe is redefined?", "configs": {},
           "universe_composition": {}}
    p59 = panels[("attr59", 90)]
    # composition of the v1 universe
    dev_any = p59.groupby("track_id", observed=True)["n_device"].sum()
    zero_tracks = dev_any[dev_any == 0].index.tolist()
    out["universe_composition"] = {
        "attr59_tracks": int(len(dev_any)),
        "tracks_with_zero_device_events": int(len(zero_tracks)),
        "zero_device_tracks": sorted(zero_tracks),
        "rows_total": int(len(p59)),
        "rows_from_zero_device_tracks": int(p59["track_id"].isin(zero_tracks).sum()),
        "labelled_rows_from_zero_device_tracks": int(
            p59.loc[p59["track_id"].isin(zero_tracks), "y"].notna().sum()),
        "labels_from_zero_device_tracks": int(np.nansum(p59.loc[p59["track_id"].isin(zero_tracks), "y"])),
    }
    for key, (universe, mode, rule, lag_label) in {
        "attr59_v1like_purged": ("attr59", "v1like", "purged", 90),
        "attr38_v2_purged": ("attr38", "v2", "purged", 90),
        "track38_v2_purged": ("track38", "v2", "purged", 90),
    }.items():
        panel = panels[(universe, 90)]
        res, _ = R.run_config(panel, f"y_{P.PRIMARY_TARGET}", rule, lag_label,
                              arms=("M0_prevalence", "M1_persistence", "M4_h8_growth"))
        out["configs"][key] = {"brief": brief(res),
                               "n_tracks": res["n_tracks"],
                               "prevalence": res["prevalence"]}
        log.step(f"  {key}: tracks={res['n_tracks']} n={res['n']} pos={res['n_pos']} "
                 f"dAP={brief(res)['dap']:+.4f} CI={brief(res)['ci95']}")
    return out


def exp4_targets(log: Log, panel38: pd.DataFrame) -> dict:
    """Experiment 4: different prediction targets, each reported independently."""
    log.step("EXP4 alternative targets")
    out = {"experiment": "EXP4_TARGETS", "configs": {},
           "note": "Each target is reported independently; Y1 remains the primary target."}
    pvals = {}
    for tgt in P.TARGETS:
        col = f"y_{tgt}"
        res, oof = R.run_config(panel38, col, "purged", 90,
                                arms=("M0_prevalence", "M1_persistence", "M4_h8_growth",
                                      "M7_mean_reversion"), B=P.B_BOOT_SECONDARY)
        rec = {"brief": brief(res),
               "maturity": {"violating_share": res["maturity"]["total_violating_share"]},
               "stratum_composition": {
                   "n_dormant": int((oof["trail8_total"].fillna(0) == 0).sum()),
                   "n_dormant_pos": int(oof.loc[oof["trail8_total"].fillna(0) == 0, "y"].sum()),
                   "vacuous_ratio_positives": int(oof.loc[(oof["trail8_total"] == 0)
                                                          & (oof["y"] == 1)].shape[0]),
                   "positives_with_trail8_le_2": int(oof.loc[(oof["trail8_total"] <= 2)
                                                             & (oof["y"] == 1)].shape[0]),
                   "total_positives": int(oof["y"].sum())},
               "ap_by_stratum": res["stratified_by_activity"]["buckets"]}
        out["configs"][tgt] = rec
        if tgt != "Y4_dormant_emergence":
            pvals[tgt] = res["contrasts"]["M4_h8_growth - M1_persistence"]["p"]
        log.step(f"  {tgt}: n={res['n']} pos={res['n_pos']} prev={res['prevalence']:.4f} "
                 f"dAP={brief(res)['dap']:+.4f} CI={brief(res)['ci95']} p={brief(res)['p']}")
        if tgt == P.PRIMARY_TARGET:
            oof.to_csv(RESULTS / "oof_primary.csv", index=False)
    out["holm_over_targets"] = M.holm_adjust(pvals)
    # stratum-specific contrasts for the primary target
    res1, oof1 = R.run_config(panel38, f"y_{P.PRIMARY_TARGET}", "purged", 90,
                              arms=("M1_persistence", "M4_h8_growth"), with_ci=False)
    t = oof1["trail8_total"].fillna(0).to_numpy(dtype=float)
    out["primary_stratum_contrasts"] = {
        "all": subset_contrast(oof1, np.ones(len(oof1), dtype=bool),
                               "M4_h8_growth", "M1_persistence"),
        "active_trail8_ge_1": subset_contrast(oof1, t >= 1, "M4_h8_growth", "M1_persistence"),
        "low_base_trail8_le_2": subset_contrast(oof1, t <= 2, "M4_h8_growth", "M1_persistence"),
        "excl_low_base_trail8_gt_2": subset_contrast(oof1, t > 2, "M4_h8_growth", "M1_persistence"),
        "dormant_trail8_eq_0": subset_contrast(oof1, t == 0, "M4_h8_growth", "M1_persistence"),
    }
    for k, v in out["primary_stratum_contrasts"].items():
        log.step(f"  stratum {k}: n={v.get('n')} pos={v.get('n_pos')} "
                 f"dAP={v.get('diff')} p={v.get('p')}")
    return out


def exp5_lags(log: Log, panels: dict) -> dict:
    """Experiment 5: feature-lag and label-lag sensitivity."""
    log.step("EXP5 lag scenarios")
    out = {"experiment": "EXP5_LAGS", "feature_lag": {}, "label_lag": {},
           "note": "L000 is a nominal-clock reference only; the headline is L090."}
    for lag in P.FEATURE_LAGS:
        panel = panels.get(("attr38", lag))
        if panel is None:
            continue
        res, _ = R.run_config(panel, f"y_{P.PRIMARY_TARGET}", "purged", 90,
                              arms=("M1_persistence", "M4_h8_growth"), B=P.B_BOOT_SECONDARY)
        out["feature_lag"][P.LAG_TAG[lag]] = {
            "brief": brief(res),
            "maturity_violating_share": res["maturity"]["total_violating_share"]}
        log.step(f"  feature {P.LAG_TAG[lag]}: dAP={brief(res)['dap']:+.4f} "
                 f"CI={brief(res)['ci95']} pos={res['n_pos']}")
    panel = panels[("attr38", 90)]
    for lag_label in P.LABEL_LAGS:
        res, _ = R.run_config(panel, f"y_{P.PRIMARY_TARGET}", "purged", lag_label,
                              arms=("M1_persistence", "M4_h8_growth"), B=P.B_BOOT_SECONDARY)
        out["label_lag"][f"labelL{lag_label:03d}"] = {
            "brief": brief(res),
            "purge_quarters": res["maturity"]["purge_quarters_required"],
            "violating_share": res["maturity"]["total_violating_share"]}
        log.step(f"  label L{lag_label:03d}: dAP={brief(res)['dap']:+.4f} "
                 f"CI={brief(res)['ci95']}")
    return out


def exp6_baselines(log: Log, panel38: pd.DataFrame) -> dict:
    """Experiment 6: all baselines on identical rows."""
    log.step("EXP6 baselines")
    res, oof = R.run_config(panel38, f"y_{P.PRIMARY_TARGET}", "purged", 90,
                            arms=P.ARMS, with_ci=True)
    out = {
        "experiment": "EXP6_BASELINES",
        "n": res["n"], "n_pos": res["n_pos"], "prevalence": res["prevalence"],
        "arms": res["arms"],
        "contrasts": res["contrasts"],
        "definition": {
            "M0_prevalence": "training-fold incidence",
            "M1_persistence": "logit on 10 trailing device-history features + exposure",
            "M2_ma_level": "logit on 4/8Q moving average and level",
            "M3_trend": "logit on slope/trend-score/acceleration",
            "M4_h8_growth": "M1 + 7 SciTrends-style growth features",
            "M5_full_regularised": "M1 + growth + all-source histories, L2 C=0.5",
            "M6_hgb": "HistGradientBoosting on the M4 feature set (max_iter=150, depth<=4)",
            "M7_mean_reversion": "logit on level only (mean-reversion channel control)",
        },
        "ap_by_year": res["ap_by_year"],
        "delta_ap_by_year": res["delta_ap_by_year"],
        "stratified_by_activity": res["stratified_by_activity"],
        "stratified_by_attribution": res["stratified_by_attribution"],
    }
    for arm, a in res["arms"].items():
        log.step(f"  {arm:22s} AP={a.get('ap', float('nan')):.4f} "
                 f"CI={[round(v, 4) for v in a.get('ap_ci95', [float('nan')] * 2)]}")
    out["ranking_by_ap"] = sorted(
        [{"arm": k, "ap": v.get("ap"), "ap_ci95": v.get("ap_ci95")}
         for k, v in res["arms"].items() if np.isfinite(v.get("ap", np.nan))],
        key=lambda r: -r["ap"])
    oof.to_csv(RESULTS / "oof_exp6_all_arms.csv", index=False)
    return out


def adversarial(log: Log, panel38: pd.DataFrame, coverage: dict) -> dict:
    """Pre-specified counter-evidence battery."""
    log.step("ADV counter-evidence battery")
    out = {"experiment": "ADVERSARIAL", "target": P.PRIMARY_TARGET,
           "panel": "attr38 v2, feature L090, label L090, purged folds"}
    target = f"y_{P.PRIMARY_TARGET}"
    folds = R.make_folds("purged", 90)

    def oof_for(panel, arms):
        fs = R.feature_sets_dict()
        o, _, _ = R.run_oof(panel, target, folds, fs, arms=arms)
        return o

    base = oof_for(panel38, ("M1_persistence", "M4_h8_growth"))
    obs = M.average_precision(base["y"], base["M4_h8_growth"]) - \
        M.average_precision(base["y"], base["M1_persistence"])
    out["observed_dap"] = float(obs)
    log.step(f"  observed dAP={obs:+.4f}")

    cols = R.growth_columns()
    # ---- A1 within-track time shuffle (feature time-correspondence destroyed)
    rng = np.random.default_rng(P.SEED)
    null = []
    for i in range(P.N_PLACEBO_PERM):
        pp = R.shuffle_growth_within_track(panel38, cols, rng)
        o = oof_for(pp, ("M4_h8_growth",))
        d = M.average_precision(o["y"], o["M4_h8_growth"]) - \
            M.average_precision(base["y"], base["M1_persistence"])
        null.append(float(d))
        if (i + 1) % 50 == 0:
            log.step(f"    within-track shuffle perm {i + 1}/{P.N_PLACEBO_PERM} "
                     f"null_mean={np.mean(null):+.4f}")
    null = np.asarray(null)
    p_perm = float((1 + np.sum(null >= obs)) / (1 + len(null)))
    out["A1_within_track_time_shuffle"] = {
        "n_perm": int(len(null)), "observed_dap": float(obs),
        "null_mean": float(null.mean()), "null_sd": float(null.std(ddof=1)),
        "null_p05": float(np.quantile(null, 0.05)), "null_p95": float(np.quantile(null, 0.95)),
        "p_one_sided": p_perm,
        "interpretation": "destroying the within-track time alignment of the growth "
                          "features should remove the gain if it is time-aligned information",
    }
    log.step(f"  A1 within-track shuffle: p={p_perm:.4f} null_mean={null.mean():+.4f} "
             f"null_sd={null.std(ddof=1):.4f}")

    # ---- A2 cross-track within-quarter shuffle (PHOENIX-001 style)
    rng2 = np.random.default_rng(P.SEED + 1)
    null2 = []
    for i in range(100):
        pp = R.shuffle_growth_across_tracks(panel38, cols, rng2)
        o = oof_for(pp, ("M4_h8_growth",))
        d = M.average_precision(o["y"], o["M4_h8_growth"]) - \
            M.average_precision(base["y"], base["M1_persistence"])
        null2.append(float(d))
    null2 = np.asarray(null2)
    out["A2_cross_track_shuffle"] = {
        "n_perm": 100, "observed_dap": float(obs),
        "null_mean": float(null2.mean()), "null_sd": float(null2.std(ddof=1)),
        "p_one_sided": float((1 + np.sum(null2 >= obs)) / (1 + len(null2))),
    }
    log.step(f"  A2 cross-track shuffle: null_mean={null2.mean():+.4f}")

    # ---- A3 time-shifted growth features (t-8)
    pps = R.shift_growth_within_track(panel38, cols, P.PLACEBO_SHIFT_Q)
    o3 = oof_for(pps, ("M4_h8_growth",))
    d3 = M.average_precision(o3["y"], o3["M4_h8_growth"]) - \
        M.average_precision(base["y"], base["M1_persistence"])
    out["A3_time_shifted_growth_t_minus_8"] = {
        "shift_quarters": P.PLACEBO_SHIFT_Q, "dap": float(d3),
        "delta_vs_observed": float(d3 - obs),
        "interpretation": "a generic activity signal would survive a lag-8 shift; a "
                          "recent-growth signal should not",
    }
    log.step(f"  A3 shift-8: dAP={d3:+.4f} (observed {obs:+.4f})")

    # ---- A4 low-base and activity strata (already in exp4; repeated compactly here)
    res1, oof1 = R.run_config(panel38, target, "purged", 90,
                              arms=("M1_persistence", "M4_h8_growth"), with_ci=False)
    t = oof1["trail8_total"].fillna(0).to_numpy(dtype=float)
    out["A4_strata"] = {
        "excl_low_base_trail8_le_2": subset_contrast(oof1, t > 2, "M4_h8_growth", "M1_persistence"),
        "low_base_trail8_le_2": subset_contrast(oof1, t <= 2, "M4_h8_growth", "M1_persistence"),
        "active": subset_contrast(oof1, t >= 1, "M4_h8_growth", "M1_persistence"),
    }

    # ---- A5 attribution-quality strata
    out["A5_attribution_strata"] = res1.get("stratified_by_attribution", {})

    # ---- A6 duplicate-record sensitivity (deduplicated counts)
    log.step("  A6 duplicate-record dedupe sensitivity (rebuilding panel)")
    p_dd = prep_panel("attr38", 90, "v2", coverage, dedupe=True)
    res_dd, _ = R.run_config(p_dd, target, "purged", 90,
                             arms=("M1_persistence", "M4_h8_growth"), B=P.B_BOOT_SECONDARY)
    out["A6_deduplicated_records"] = {
        "brief": brief(res_dd),
        "duplicates": D.duplicate_stats(D.load_events(P.ALL_KINDS, require_company=True)),
        "interpretation": "if the effect depends on duplicate regulatory rows, removing "
                          "them should shrink it",
    }
    log.step(f"  A6 dedupe: dAP={brief(res_dd)['dap']:+.4f} CI={brief(res_dd)['ci95']}")

    # ---- A7 training-cutoff / window sensitivity
    out["A7_fold_sensitivity"] = {}
    for first_year, window in ((2012, "expanding"), (2014, "expanding"),
                               (2016, "expanding"), (2014, "rolling8")):
        res_f, _ = R.run_config(panel38, target, "purged", 90,
                                arms=("M1_persistence", "M4_h8_growth"),
                                first_test_year=first_year, train_window=window,
                                B=P.B_BOOT_SECONDARY)
        key = f"first{first_year}_{window}"
        out["A7_fold_sensitivity"][key] = brief(res_f)
        log.step(f"  A7 {key}: n={res_f['n']} pos={res_f['n_pos']} "
                 f"dAP={brief(res_f)['dap']:+.4f} CI={brief(res_f)['ci95']}")

    # ---- A8 negative-control target: predict another event kind with device growth features
    # (n_trial is not constructible for the 38 device tracks: every attributed trial event
    #  sits in a t_* trial track, so device tracks have zero attributed trial history.
    #  Device recalls ARE attributed to device tracks, so the recall series is the usable
    #  negative-control target.)
    alt_col = "n_device_recall" if "n_device_recall" in panel38.columns else "n_510k"
    log.step(f"  A8 negative-control target (growth of {alt_col} with device growth features)")
    p_trial = alt_target_panel(panel38, alt_col)
    res_t, _ = R.run_config(p_trial, f"y_{P.PRIMARY_TARGET}", "purged", 90,
                            arms=("M1_persistence", "M4_h8_growth"), B=P.B_BOOT_SECONDARY)
    out["A8_negative_control_trial_growth"] = {
        "brief": brief(res_t),
        "interpretation": "device growth features predicting trial growth is a generic "
                          "activity signal; the contrast is device persistence vs device "
                          "growth on a trial-event target",
    }
    log.step(f"  A8 trial-growth target: dAP={brief(res_t)['dap']:+.4f} "
             f"CI={brief(res_t)['ci95']}")
    return out


# ------------------------------------------------------------------------- verdict
def build_verdict(exp2, exp3, exp4, exp5, exp6, adv) -> dict:
    """Mechanical application of the frozen gates. No human discretion."""
    primary = exp3["configs"]["attr38_v2_purged"]["brief"]
    d, lo, hi, p = primary["dap"], primary["ci95"][0], primary["ci95"][1], primary["p"]
    tau = P.TAU_AP
    active = exp4["primary_stratum_contrasts"]["active_trail8_ge_1"]
    cross = exp3["configs"]["track38_v2_purged"]["brief"]
    placebo = adv["A1_within_track_time_shuffle"]
    comp = exp4["configs"][P.PRIMARY_TARGET]["stratum_composition"]

    gates = {
        "G1_primary_dap_ge_tau": bool(np.isfinite(d) and d >= tau),
        "G1b_primary_ci_low_positive": bool(np.isfinite(lo) and lo > 0),
        "G2_cross_universe_track38_dap_ge_0.02": bool(
            np.isfinite(cross["dap"]) and cross["dap"] >= P.GATE_CROSS_UNIVERSE["dap_min"]),
        "G3_placebo_p_lt_0.05": bool(np.isfinite(placebo["p_one_sided"])
                                     and placebo["p_one_sided"] < P.GATE_PLACEBO["p_placebo_max"]),
        "G4_active_stratum_dap_ge_0.02": bool(
            np.isfinite(active.get("diff", np.nan))
            and active.get("diff") >= P.GATE_ACTIVE_STRATUM["dap_min"]),
        "G5_enough_positives": bool(primary["n_pos"] >= P.GATE_MIN_POSITIVES),
        "G6_ci_resolves_tau": bool(np.isfinite(hi) and hi >= tau),
    }
    vacuous_share = (comp["vacuous_ratio_positives"] / comp["total_positives"]
                     if comp["total_positives"] else float("nan"))
    low_base_share = (comp["positives_with_trail8_le_2"] / comp["total_positives"]
                      if comp["total_positives"] else float("nan"))
    artifact_flags = {
        "vacuous_ratio_positive_share": vacuous_share,
        "low_base_positive_share": low_base_share,
        "majority_of_positives_are_low_base": bool(low_base_share > 0.5),
        "placebo_collapses_effect": bool(adv["A1_within_track_time_shuffle"]["null_p95"] >= d),
    }
    if not gates["G5_enough_positives"] or not np.isfinite(d):
        verdict = "INCONCLUSIVE"
        reason = "insufficient evaluable positives or non-finite primary estimate"
    elif gates["G1_primary_dap_ge_tau"] and gates["G1b_primary_ci_low_positive"] \
            and gates["G3_placebo_p_lt_0.05"] and gates["G4_active_stratum_dap_ge_0.02"] \
            and gates["G2_cross_universe_track38_dap_ge_0.02"] \
            and not artifact_flags["majority_of_positives_are_low_base"]:
        verdict = "GO"
        reason = "primary dAP >= tau with CI excluding 0, placebo separates, active stratum " \
                 "and second universe both replicate, and positives are not majority low-base"
    elif gates["G1_primary_dap_ge_tau"] and gates["G1b_primary_ci_low_positive"]:
        verdict = "LIMITED_GO"
        failed = [k for k, ok in gates.items() if not ok and k.startswith(("G2", "G3", "G4"))]
        if artifact_flags["majority_of_positives_are_low_base"]:
            failed.append("majority_of_positives_are_low_base")
        reason = f"primary effect meets tau but fails gate(s): {failed}"
    elif np.isfinite(hi) and hi < tau:
        verdict = "NO-GO"
        reason = "95% CI upper bound is below the pre-registered tau=0.03: the effect is " \
                 "too small to be practically meaningful"
    elif np.isfinite(lo) and lo > 0:
        verdict = "NO-GO"
        reason = "point estimate is positive but below the pre-registered practical " \
                 "threshold tau=0.03"
    else:
        verdict = "INCONCLUSIVE"
        reason = "CI straddles both zero and tau: the data cannot distinguish the " \
                 "pre-registered effect size from no effect"
    return {
        "verdict": verdict, "reason": reason, "gates": gates,
        "artifact_flags": artifact_flags,
        "primary_contrast": primary,
        "tau": tau,
        "gate_definitions": {
            "G1": f"primary dAP >= {tau}",
            "G1b": "primary 95% CI lower bound > 0",
            "G2": f"track38 universe dAP >= {P.GATE_CROSS_UNIVERSE['dap_min']}",
            "G3": f"within-track time-shuffle placebo p < {P.GATE_PLACEBO['p_placebo_max']}",
            "G4": f"active stratum (trail8_total>=1) dAP >= {P.GATE_ACTIVE_STRATUM['dap_min']}",
            "G5": f"evaluable positives >= {P.GATE_MIN_POSITIVES}",
            "G6": f"95% CI upper bound >= tau={tau} (otherwise tau is ruled out)",
        },
    }


# ---------------------------------------------------------------------------- main
def main(skip_exp1: bool = False) -> int:
    log = Log("run_phoenix002")
    try:
        log.step(f"protocol {P.PROTOCOL_VERSION}; seed {P.SEED}")
        db = D.verify_db(verbose=True)
        if not db["sha256_matches_frozen"]:
            log.write("ABORT: database SHA-256 does not match the frozen value")
            return 2
        events = D.load_events(P.ALL_KINDS)
        coverage = D.coverage_stats(events)
        duplicates = D.duplicate_stats(events)
        log.step(f"events={len(events)} tracked_device_events={coverage['n_tracked_device_events']} "
                 f"attribution_rate={coverage['overall_attribution_rate']:.4f} "
                 f"tracks_below_50pct={coverage['n_tracks_below_50pct']}")
        log.step(f"duplicates={duplicates}")

        panels = {}
        for lag in P.FEATURE_LAGS:
            t0 = time.time()
            panels[("attr38", lag)] = prep_panel("attr38", lag, "v2", coverage)
            log.step(f"panel attr38 L{lag:03d} built in {time.time() - t0:.1f}s "
                     f"rows={len(panels[('attr38', lag)])}")
        panels[("track38", 90)] = prep_panel("track38", 90, "v2", coverage)
        log.step(f"panel track38 L090 rows={len(panels[('track38', 90)])}")
        panels[("attr59", 90)] = prep_panel("attr59", 90, "v1like", coverage)
        log.step(f"panel attr59 v1like L090 rows={len(panels[('attr59', 90)])}")
        p38 = panels[("attr38", 90)]

        allres = {
            "meta": {
                "protocol_version": P.PROTOCOL_VERSION,
                "spec": P.spec(),
                "db": db,
                "coverage": coverage,
                "duplicates": duplicates,
                "run_started": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        }
        if not skip_exp1:
            p = RESULTS / "exp1_v1_replication" / "exp1_replication.json"
            allres["exp1"] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {
                "status": "MISSING — run exp1_v1_replication.py"}
        allres["exp2"] = exp2_maturity(log, panels, coverage)
        save(allres["exp2"], "exp2.json")
        allres["exp3"] = exp3_risksets(log, panels)
        save(allres["exp3"], "exp3.json")
        allres["exp4"] = exp4_targets(log, p38)
        save(allres["exp4"], "exp4.json")
        allres["exp5"] = exp5_lags(log, panels)
        save(allres["exp5"], "exp5.json")
        allres["exp6"] = exp6_baselines(log, p38)
        save(allres["exp6"], "exp6.json")
        allres["adversarial"] = adversarial(log, p38, coverage)
        save(allres["adversarial"], "adversarial.json")
        allres["verdict"] = build_verdict(allres["exp2"], allres["exp3"], allres["exp4"],
                                          allres["exp5"], allres["exp6"], allres["adversarial"])
        save(allres, "summary.json")
        # per-experiment copies for readability
        for k in ("exp2", "exp3", "exp4", "exp5", "exp6", "adversarial", "verdict"):
            save(allres[k], f"{k}.json")
        log.step(f"VERDICT: {allres['verdict']['verdict']} — {allres['verdict']['reason']}")
        log.step("wrote summary.json and per-experiment JSONs")
        return 0
    except Exception:
        log.write("EXCEPTION:\n" + traceback.format_exc())
        return 1
    finally:
        log.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-exp1", action="store_true")
    a = ap.parse_args()
    raise SystemExit(main(skip_exp1=a.skip_exp1))
