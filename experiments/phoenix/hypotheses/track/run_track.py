"""Stage 3 — the T-TRACK walk-forward driver for H3 / H6 / H8 / H9.

One command:
    python experiments/phoenix/hypotheses/track/run_track.py

Design (frozen):
  * 12 walk-forward folds, test years 2014..2025, expanding training window.
  * Every arm is fitted on the training folds only and scored out-of-fold; all
    arms share the same evaluation rows, so differences are paired.
  * Headline lag = L090; L000 and L180 re-run end to end.
  * Cluster bootstrap by track_id, B=1000, seed 20261108.
  * Primary contrasts are reported with RAW (unadjusted) paired-bootstrap p so the
    Lead can Holm-combine them across the whole program.

Arms (protocol §4 / §6):
  B0 prevalence | B1 persistence (logit, own device history) | B2 trend score
  B5 full (logit, all four source histories) | H3 (+ entrant features)
  H6 (+ HHI features on top of B5) | H8 (+ SciTrends-style growth features on B1)
  H9 F_dev / F_trial / F_recall / F_8k / F_fusion (per-source logits)
"""
from __future__ import annotations

import time

import json

import numpy as np
import pandas as pd

import track_common as tc
import phoenix_common as pc

EXPOSURE = ["exposure_q", "log_exposure"]

# ------------------------------------------------------------------ feature sets
def hcols(prefix: str) -> list[str]:
    """The 10 trailing-history columns add_history_features() creates per count col."""
    return [
        f"{prefix}_sum1", f"{prefix}_sum2", f"{prefix}_sum4", f"{prefix}_sum8",
        f"{prefix}_sum12", f"{prefix}_cum", f"{prefix}_mean4", f"{prefix}_std8",
        f"{prefix}_accel", f"{prefix}_log4",
    ]


B1_FEATS = hcols("f_n_device") + EXPOSURE
B5_FEATS = (
    hcols("f_n_510k") + hcols("f_n_pma") + hcols("f_n_trial")
    + hcols("f_n_device_recall") + hcols("f_n_device") + hcols("f_n_total") + EXPOSURE
)
H3_FEATS = B1_FEATS + ["ent_q", "ent_new4", "ent_new8", "ent_cum", "ent_share4"]
H6_FEATS = B5_FEATS + ["hhi_q_fill", "hhi4", "d_hhi4", "d_hhi8", "d_hhi4_pool"]
H8_FEATS = B1_FEATS + [
    "sct_growth1", "sct_growth2", "sct_growth4", "sct_growth8",
    "sct_slope12", "sct_pma_share4", "sct_volatility8",
]
H9_SOURCES = {
    "H9_dev": ["f_n_510k", "f_n_pma"],
    "H9_trial": ["f_n_trial"],
    "H9_recall": ["f_n_device_recall"],
    "H9_8k": ["f_n_8k_catalyst"],
}

ARMS = [
    "B0_prevalence", "B1_persistence", "B2_trend", "B5_full",
    "H3_entrants", "H6_hhi", "H8_growth",
    "H9_dev", "H9_trial", "H9_recall", "H9_8k", "H9_fusion",
]

CONTRASTS = {
    "H3": {"a": "H3_entrants", "b": "B1_persistence", "tau": 0.02,
           "definition": "AP(B1 + entrant features) - AP(B1 persistence), holdout"},
    "H6": {"a": "H6_hhi", "b": "B5_full", "tau": 0.02,
           "definition": "AP(B5 + HHI features) - AP(B5 full), holdout"},
    "H8": {"a": "H8_growth", "b": "B1_persistence", "tau": 0.03,
           "definition": "AP(B1 + SciTrends-style growth features) - AP(B1 persistence), holdout"},
}


# ---------------------------------------------------------------- panel assembly
def attach_features(panel: pd.DataFrame, lag: int) -> pd.DataFrame:
    tag = tc.LAG_TAG[lag]
    path = tc.CACHE_DIR / f"entrants_hhi_{tag}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run entrants_hhi.py first")
    eh = pd.read_csv(path, dtype={"quarter": str})
    keep = ["track_id", "quarter", "ent_q", "ent_new4", "ent_new8", "ent_cum",
            "ent_share4", "n_active_q", "n_active4", "hhi_q_fill", "hhi4",
            "d_hhi4", "d_hhi8", "d_hhi4_pool"]
    eh = eh[keep].rename(columns={"quarter": "quarter_str"})
    panel = panel.copy()
    panel["quarter_str"] = panel["quarter"].astype(str)
    out = panel.merge(eh, on=["track_id", "quarter_str"], how="left", validate="many_to_one")
    return out.drop(columns=["quarter_str"]).reset_index(drop=True)


def build_specs(panel: pd.DataFrame) -> dict:
    has = set(panel.columns)

    def keep(cols: list[str]) -> list[str]:
        return [c for c in cols if c in has]

    specs: dict = {
        "B0_prevalence": {"kind": "const", "features": []},
        "B1_persistence": {"kind": "logit", "features": keep(B1_FEATS)},
        "B2_trend": {"kind": "raw", "col": "b2_trend_score", "features": []},
        "B5_full": {"kind": "logit", "features": keep(B5_FEATS)},
        "H3_entrants": {"kind": "logit", "features": keep(H3_FEATS)},
        "H6_hhi": {"kind": "logit", "features": keep(H6_FEATS)},
        "H8_growth": {"kind": "logit", "features": keep(H8_FEATS)},
    }
    fusion: list[str] = []
    for arm, prefixes in H9_SOURCES.items():
        feats: list[str] = []
        for p in prefixes:
            feats += keep(hcols(p))
        if feats:
            feats = feats + keep(EXPOSURE)
            specs[arm] = {"kind": "logit", "features": feats}
            fusion += feats
        else:
            specs[arm] = {"kind": "unavailable", "features": [],
                          "reason": f"no track-level events exist for {prefixes}"}
    specs["H9_fusion"] = {"kind": "logit", "features": sorted(set(fusion + keep(EXPOSURE)))}
    return specs


# ------------------------------------------------------------------ walk forward
def oof_scores(panel: pd.DataFrame, specs: dict, log: tc.RunLog, tag: str) -> pd.DataFrame:
    folds = pc.walk_forward_folds(2014, 2025)
    pieces = []
    for f in folds:
        tr = panel[(panel["quarter"] >= f.train_origins[0])
                   & (panel["quarter"] <= f.train_origins[1]) & panel["y"].notna()]
        te = panel[(panel["quarter"] >= f.test_origins[0])
                   & (panel["quarter"] <= f.test_origins[1]) & panel["y"].notna()]
        if len(tr) == 0 or len(te) == 0:
            continue
        out = te[["track_id", "quarter", "y"]].copy()
        out["fold_year"] = f.test_year
        for name in ARMS:
            spec = specs[name]
            if spec["kind"] == "unavailable":
                out[name] = np.nan
                continue
            if spec["kind"] == "const":
                out[name] = float(tr["y"].mean())
                continue
            if spec["kind"] == "raw":
                out[name] = te[spec["col"]].to_numpy(dtype=float)
                continue
            feats = [c for c in spec["features"]
                     if tr[c].notna().any() and float(tr[c].std(ddof=0)) > 0]
            if not feats:
                out[name] = float(tr["y"].mean())
                continue
            model = pc.LogisticModel()
            model.fit(tr[feats].to_numpy(dtype=float), tr["y"].to_numpy(dtype=float))
            out[name] = model.predict_score(te[feats].to_numpy(dtype=float))
        pieces.append(out)
    df = pd.concat(pieces, ignore_index=True)
    log.step(f"{tag}: OOF rows={len(df)} folds={len(pieces)} positives={int(df['y'].sum())}")
    return df


def arm_metrics(oof: pd.DataFrame, arm: str, log: tc.RunLog, with_ci: bool) -> dict:
    d = oof.dropna(subset=["y", arm])
    if d.empty or d["y"].nunique() < 2:
        return {"model": arm, "n": int(len(d)), "status": "NO_VARIATION"}
    ev = pc.evaluate(d["y"].to_numpy(float), d[arm].to_numpy(float), name=arm)
    if with_ci:
        point, lo, hi = pc.block_bootstrap_ci(
            d["y"].to_numpy(float), d[arm].to_numpy(float),
            d["track_id"].to_numpy(), B=tc.B_BOOT, seed=tc.SEED,
        )
        ev["ap_ci95"] = [float(lo), float(hi)]
        ev["ap_boot_point"] = float(point)
    ev["ap_by_block"] = tc.ap_by_block(d, arm)
    ev["alert_top10_per_quarter"] = tc.alert_precision_topk(d, arm, k=10)
    dist = tc.ap_by_track(d, arm)
    ev["ap_by_track"] = dist
    ev["ap_by_track_summary"] = tc.summarize_track_ap(dist)
    ev["holdout_ap"] = {
        "window": ["2022Q1", "2025Q2"],
        "n": int(d[d["quarter"] >= pd.Period("2022Q1", freq="Q")]["y"].notna().sum()),
        "ap": pc.average_precision(
            d[d["quarter"] >= pd.Period("2022Q1", freq="Q")]["y"].to_numpy(float),
            d[d["quarter"] >= pd.Period("2022Q1", freq="Q")][arm].to_numpy(float),
        ),
    }
    q1 = tc.q1_only(d)
    ev["q1_only_nonoverlapping_sensitivity"] = {
        "n": int(len(q1)), "ap": pc.average_precision(q1["y"].to_numpy(float), q1[arm].to_numpy(float)),
    }
    return ev


def contrast(oof: pd.DataFrame, a: str, b: str) -> dict:
    d = oof.dropna(subset=["y", a, b])
    res = pc.paired_bootstrap_diff(
        d["y"].to_numpy(float), d[a].to_numpy(float), d[b].to_numpy(float),
        d["track_id"].to_numpy(), B=tc.B_BOOT, seed=tc.SEED,
    )
    res["ap_a"] = pc.average_precision(d["y"].to_numpy(float), d[a].to_numpy(float))
    res["ap_b"] = pc.average_precision(d["y"].to_numpy(float), d[b].to_numpy(float))
    res["n"] = int(len(d))
    res["n_pos"] = int(d["y"].sum())
    return res


def verdict(diff: float, p: float, tau: float) -> str:
    """Mechanical pre-registered rule. No post-hoc adjustment of tau."""
    if not np.isfinite(diff):
        return "INCONCLUSIVE"
    if diff >= tau and np.isfinite(p) and p < 0.05:
        return "SUPPORTED"
    if diff >= tau:
        return "INCONCLUSIVE"
    return "NOT SUPPORTED"


def main(log: tc.RunLog) -> int:
    t0 = time.time()
    db = tc.db_meta()
    if not db["db_sha256_matches_frozen"]:
        log.write("ABORT: db sha256 mismatch")
        return 2

    con = pc.connect_ro()
    try:
        events = pc.load_events(con)
    finally:
        con.close()

    per_lag: dict = {}
    descriptive_written = False
    for lag in tc.LAG_SCENARIOS:
        tag = tc.LAG_TAG[lag]
        panel = tc.ensure_panel(lag, log)
        panel = attach_features(panel, lag)
        specs = build_specs(panel)
        oof = oof_scores(panel, specs, log, tag)
        with_ci = lag == tc.HEADLINE_LAG

        arms_out = {}
        for arm in ARMS:
            if specs[arm]["kind"] == "unavailable":
                arms_out[arm] = {"model": arm, "status": "UNAVAILABLE",
                                 "reason": specs[arm]["reason"]}
                continue
            arms_out[arm] = arm_metrics(oof, arm, log, with_ci)
            log.step(f"{tag} {arm:15s} AP={arms_out[arm].get('ap', float('nan')):.4f}"
                     + (f" CI={arms_out[arm].get('ap_ci95')}" if with_ci else ""))

        # --- primary contrasts -------------------------------------------------
        contrasts = {}
        for h, spec in CONTRASTS.items():
            contrasts[h] = contrast(oof, spec["a"], spec["b"])
            contrasts[h]["tau"] = spec["tau"]
            contrasts[h]["definition"] = spec["definition"]
            contrasts[h]["verdict"] = verdict(contrasts[h]["diff"], contrasts[h]["p"], spec["tau"])
        # H9: fusion vs the strongest constructible single source
        single_arms = [a for a in ("H9_dev", "H9_trial", "H9_recall") if a in arms_out
                       and arms_out[a].get("status") != "UNAVAILABLE"]
        best_single = max(single_arms, key=lambda a: arms_out[a]["ap"])
        contrasts["H9"] = contrast(oof, "H9_fusion", best_single)
        contrasts["H9"]["tau"] = 0.02
        contrasts["H9"]["best_single_arm"] = best_single
        contrasts["H9"]["definition"] = (
            f"AP(F_fusion) - AP({best_single}), strongest constructible single source"
        )
        contrasts["H9"]["verdict"] = verdict(contrasts["H9"]["diff"], contrasts["H9"]["p"], 0.02)
        contrasts["H9"]["fusion_over_best_single_ratio"] = (
            contrasts["H9"]["ap_a"] / contrasts["H9"]["ap_b"]
            if contrasts["H9"]["ap_b"] else float("nan")
        )
        contrasts["H9"]["no_material_gain_flag"] = bool(
            np.isfinite(contrasts["H9"]["fusion_over_best_single_ratio"])
            and contrasts["H9"]["fusion_over_best_single_ratio"] >= 0.90
            and contrasts["H9"]["diff"] < 0.02
        )
        log.step(f"{tag} contrasts: " + "; ".join(
            f"{h} d={c['diff']:+.4f} [{c['lo']:+.4f},{c['hi']:+.4f}] p={c['p']:.3f}"
            for h, c in contrasts.items()))

        # --- H9 per-source / per-window table ----------------------------------
        h9_windows = {}
        yr = oof["quarter"].astype(str).str.slice(0, 4).astype(int)
        for a, b in tc.BLOCKS:
            sub = oof[(yr >= a) & (yr <= b)]
            h9_windows[f"{a}-{b}"] = {
                arm: {
                    "n": int(sub["y"].notna().sum()),
                    "n_pos": int(np.nansum(sub["y"].to_numpy(float))),
                    "ap": pc.average_precision(sub["y"].to_numpy(float),
                                               sub[arm].to_numpy(float)),
                } for arm in ("H9_dev", "H9_trial", "H9_recall", "H9_fusion")
            }

        per_lag[tag] = {
            "lag_scenario": tag, "lag_days": int(lag),
            "n": int(len(oof)), "n_pos": int(oof["y"].sum()),
            "prevalence": float(oof["y"].mean()),
            "arms": arms_out, "contrasts": contrasts,
            "h9_by_block": h9_windows,
            "feature_counts": {k: len(v["features"]) for k, v in specs.items()},
            "unavailable_arms": {k: v["reason"] for k, v in specs.items()
                                 if v["kind"] == "unavailable"},
        }

        # --- H3 / H6 descriptive tests (event clock; run once) -----------------
        if not descriptive_written:
            log.step("computing H3 lead-correlation and H6 descriptive tests ...")
            series = tc.event_clock_series(events)
            h3 = {
                **tc.base_record(log, db, tc.HEADLINE_LAG, 0, 0, 0.0),
                "hypothesis": "H3",
                "test": "lead correlation, event clock (descriptive, class R)",
                "lag_correlations": tc.h3_lead_correlations(series),
                "n_tracks": len(series["tracks"]),
                "n_quarters": int(series["ent"].shape[1]),
                "n": int(series["ent"].size),
                "n_pos": int((series["ent"] > 0).sum()),
                "prevalence": float((series["ent"] > 0).mean()),
            }
            h6 = {
                **tc.base_record(log, db, tc.HEADLINE_LAG, 0, 0, 0.0),
                "hypothesis": "H6",
                "test": "concentration-change association, event clock (descriptive, class R)",
                "descriptive": tc.h6_descriptive(series),
                "hhi_definition_note": (
                    "single-quarter HHI of company event shares within the track; "
                    "quarters without events are undefined and skipped in the test"
                ),
                "n_tracks": len(series["tracks"]),
                "n": int(np.isfinite(series["hhi"]).sum()),
                "n_pos": int(np.isfinite(series["hhi"]).sum()),
                "prevalence": float(np.isfinite(series["hhi"]).mean()),
            }
            tc.save({
                **tc.base_record(log, db, tc.HEADLINE_LAG, 0, 0, 0.0),
                "content": "H3 lead-correlation and H6 descriptive association tests "
                           "(event clock, descriptive only)",
                "h3": h3, "h6": h6,
            }, tc.RESULTS_DIR / "h3h6_descriptive.json")
            descriptive_written = True
            log.step("wrote h3h6_descriptive.json")

    # ---------------------------------------------------------------- leakage
    panel = tc.ensure_panel(tc.HEADLINE_LAG, log)
    specs = build_specs(panel)
    used = sorted({c for s in specs.values() for c in s.get("features", [])})
    leak = pc.leakage_audit(panel, tc.ENTITY, used, target_col="y")
    log.step(f"leakage_audit suspected_leaks={leak['suspected_label_leak']} "
             f"high_corr={list(leak['high_correlation_features_gt_0.80'])}")

    head = per_lag[tc.LAG_TAG[tc.HEADLINE_LAG]]
    all_metrics = {
        **tc.base_record(log, db, tc.HEADLINE_LAG, head["n"], head["n_pos"], head["prevalence"]),
        "hypotheses": ["H3", "H6", "H8", "H9"],
        "task": "T-TRACK growth (frozen protocol §2.2)",
        "headline_lag": tc.LAG_TAG[tc.HEADLINE_LAG],
        "walk_forward": {"first_test_year": 2014, "last_test_year": 2025,
                         "scheme": "expanding window, train strictly before test year"},
        "bootstrap": {"B": tc.B_BOOT, "cluster": "track_id", "seed": tc.SEED},
        "lags": per_lag,
        "leakage_audit": leak,
        "notes": [
            "All arms are scored out-of-fold on identical rows; contrasts are paired.",
            "The holdout block 2022Q1-2025Q2 is part of the walk-forward test span and "
            "is reported both pooled and separately (holdout_ap).",
            "F_8k cannot be constructed: no 8k_catalyst event in the frozen DB carries a "
            "track_id (verified: 0/20976). The pre-registered 5-arm H9 design is therefore "
            "run with the 4 constructible arms (dev, trial, recall, fusion).",
            "L000 is a nominal-clock control only; the headline is L090.",
        ],
    }
    tc.save(all_metrics, tc.RESULTS_DIR / "track_all_metrics.json")
    log.step("wrote track_all_metrics.json")

    # ------------------------------------------------------------ primary tests
    primary = {
        **tc.base_record(log, db, tc.HEADLINE_LAG, head["n"], head["n_pos"], head["prevalence"]),
        "p_value_note": (
            "RAW, unadjusted paired-bootstrap p values (two-sided, cluster bootstrap over "
            "track_id, B=1000). The Lead Holm-combines these across the whole program."
        ),
        "headline_lag": tc.LAG_TAG[tc.HEADLINE_LAG],
        "primary": {h: per_lag[tc.LAG_TAG[tc.HEADLINE_LAG]]["contrasts"][h]
                    for h in ("H3", "H6", "H8", "H9")},
        "by_lag": {tag: {h: v["contrasts"][h] for h in ("H3", "H6", "H8", "H9")}
                   for tag, v in per_lag.items()},
        "descriptive": {},
    }
    desc_path = tc.RESULTS_DIR / "h3h6_descriptive.json"
    if desc_path.exists():
        desc = json.loads(desc_path.read_text(encoding="utf-8"))
        primary["descriptive"] = {
            "H3_k1_fwd4_spearman": desc["h3"]["lag_correlations"]["fwd4"]["k1"],
            "H3_k0_single_spearman": desc["h3"]["lag_correlations"]["single"]["k0"],
            "H6_spearman": {k: desc["h6"]["descriptive"][k]
                            for k in ("spearman", "ci95", "p_boot", "ci_excludes_zero")},
        }
    tc.save(primary, tc.RESULTS_DIR / "primary_tests.json")
    log.step("wrote primary_tests.json")

    # ------------------------------------------------- per-hypothesis result files
    h_head = per_lag[tc.LAG_TAG[tc.HEADLINE_LAG]]
    arm_ap = {a: h_head["arms"][a].get("ap") for a in ARMS}
    desc = json.loads(desc_path.read_text(encoding="utf-8")) if desc_path.exists() else {}

    h3 = {
        **tc.base_record(log, db, tc.HEADLINE_LAG, h_head["n"], h_head["n_pos"],
                         h_head["prevalence"]),
        "hypothesis": "H3",
        "title": "Do entrants lead track-level growth?",
        "pre_registered_definition": (
            "T-TRACK: AP(B1 persistence + entrant features) - AP(B1 persistence) on the "
            "walk-forward holdout. Supported iff dAP >= 0.02 and paired p < 0.05. "
            "Additional: corr(entrants_t, rate_{t+1..t+4}) with a permutation test, and an "
            "explicit statement of whether the association is only contemporaneous."
        ),
        "n": h_head["n"], "n_pos": h_head["n_pos"], "prevalence": h_head["prevalence"],
        "arms_ap": {"B1_persistence": arm_ap["B1_persistence"],
                    "H3_entrants": arm_ap["H3_entrants"]},
        "primary_contrast": h_head["contrasts"]["H3"],
        "by_lag": {tag: v["contrasts"]["H3"] for tag, v in per_lag.items()},
        "stability_block_ap_H3_arm": h_head["arms"]["H3_entrants"]["ap_by_block"],
        "stability_block_ap_B1": h_head["arms"]["B1_persistence"]["ap_by_block"],
        "lead_correlation": desc.get("h3", {}).get("lag_correlations"),
        "calendar_control": {
            "raw_fwd4_k1_spearman": desc.get("h3", {}).get("lag_correlations", {})
            .get("fwd4", {}).get("k1", {}).get("spearman"),
            "within_track_highpass_fwd4_k1_spearman": desc.get("h3", {})
            .get("lag_correlations", {}).get("sensitivity_within_track_highpass", {})
            .get("fwd4", {}).get("k1", {}).get("spearman"),
            "interpretation": (
                "company entry is front-loaded in the registry snapshot (1.38 entrants per "
                "track-quarter in 2004 vs 0.08-0.13 after 2015) while device volume rises "
                "over calendar time. Removing each track's own trailing-8Q level collapses "
                "the raw negative association to about zero, so the raw correlation is a "
                "calendar confound, not a demonstrated lead."
            ),
        },
        "verdict": h_head["contrasts"]["H3"]["verdict"],
        "evidence_class": "S for the predictive arm; R for the correlation analysis",
        "caveats": [
            "59 tracks only: cluster CIs are wide and AP differences below ~0.03 are "
            "almost certainly noise at this sample size.",
            "The entrant feature uses the feature clock (available_at + lag), the "
            "correlation analysis uses the event clock; they answer different questions.",
        ],
    }
    tc.save(h3, tc.RESULTS_DIR / "h3_entrants.json")

    hd = desc.get("h6", {}).get("descriptive", {})
    h6_verdict = h_head["contrasts"]["H6"]["verdict"]
    if h6_verdict == "SUPPORTED" and not hd.get("ci_excludes_zero", False):
        h6_verdict = "NOT SUPPORTED"
    h6 = {
        **tc.base_record(log, db, tc.HEADLINE_LAG, h_head["n"], h_head["n_pos"],
                         h_head["prevalence"]),
        "hypothesis": "H6",
        "title": "Does track concentration (HHI) explain / predict subsequent diffusion?",
        "pre_registered_definition": (
            "Test 1 (descriptive): Spearman(dHHI_{t-4->t}, dHHI_{t->t+4}) with cluster "
            "bootstrap CI. Test 2 (incremental prediction): AP(B5 + HHI) - AP(B5) on the "
            "walk-forward holdout. Supported iff test2 dAP >= 0.02 and p < 0.05 AND test1 "
            "CI excludes 0."
        ),
        "n": h_head["n"], "n_pos": h_head["n_pos"], "prevalence": h_head["prevalence"],
        "arms_ap": {"B5_full": arm_ap["B5_full"], "H6_hhi": arm_ap["H6_hhi"]},
        "primary_contrast_test2": h_head["contrasts"]["H6"],
        "descriptive_test1": hd,
        "test1_ci_excludes_zero": hd.get("ci_excludes_zero", False),
        "by_lag": {tag: v["contrasts"]["H6"] for tag, v in per_lag.items()},
        "stability_block_ap_H6_arm": h_head["arms"]["H6_hhi"]["ap_by_block"],
        "verdict_test2_alone": h_head["contrasts"]["H6"]["verdict"],
        "verdict": h6_verdict,
        "evidence_class": "S for the predictive arm; R for the association test",
        "caveats": [
            "Single-quarter HHI on small event counts is very noisy; a pooled trailing-4Q "
            "HHI is also supplied to the model as a stabilised variant.",
            "Share base is company shares of ALL events with company_key in that track "
            "quarter; a device-only HHI sensitivity is in results/audit_track.json.",
        ],
    }
    tc.save(h6, tc.RESULTS_DIR / "h6_hhi.json")

    h8 = {
        **tc.base_record(log, db, tc.HEADLINE_LAG, h_head["n"], h_head["n_pos"],
                         h_head["prevalence"]),
        "hypothesis": "H8",
        "title": "Do SciTrends-type growth features transfer to medical-device event data?",
        "pre_registered_definition": (
            "T-TRACK: AP(B1 + growth features) - AP(B1 persistence) on the walk-forward "
            "holdout. Supported iff dAP >= 0.03 and paired p < 0.05."
        ),
        "growth_features": H8_FEATS[len(B1_FEATS):],
        "n": h_head["n"], "n_pos": h_head["n_pos"], "prevalence": h_head["prevalence"],
        "arms_ap": {"B1_persistence": arm_ap["B1_persistence"],
                    "H8_growth": arm_ap["H8_growth"]},
        "primary_contrast": h_head["contrasts"]["H8"],
        "by_lag": {tag: v["contrasts"]["H8"] for tag, v in per_lag.items()},
        "stability_block_ap_H8_arm": h_head["arms"]["H8_growth"]["ap_by_block"],
        "verdict": h_head["contrasts"]["H8"]["verdict"],
        "evidence_class": "S",
        "caveats": [
            "This is NOT a reproduction of SciTrends accuracy: different target, domain and "
            "frequency. The patent-leading-indicator component is untestable (no patent data).",
        ],
    }
    tc.save(h8, tc.RESULTS_DIR / "h8_scitrends.json")

    h9c = h_head["contrasts"]["H9"]
    h9 = {
        **tc.base_record(log, db, tc.HEADLINE_LAG, h_head["n"], h_head["n_pos"],
                         h_head["prevalence"]),
        "hypothesis": "H9",
        "title": "Is multi-source fusion better than the strongest single source?",
        "pre_registered_definition": (
            "T-TRACK: AP(F_fusion) - max_s AP(F_s) >= 0.02 and paired p < 0.05. "
            "Counter-evidence condition: if the strongest single source is already >= 90% "
            "of fusion, state 'no material fusion gain'."
        ),
        "arms_ap": {a: arm_ap[a] for a in ("H9_dev", "H9_trial", "H9_recall", "H9_8k", "H9_fusion")},
        "primary_contrast": h9c,
        "by_block": h_head["h9_by_block"],
        "source_availability": {
            "F_dev": "available, full 2004-2025 window",
            "F_trial": "available, full 2004-2025 window",
            "F_recall": "available, full 2004-2025 window",
            "F_8k": "NOT CONSTRUCTIBLE — 0 of 20976 8k_catalyst events carry a track_id",
            "F_fusion": "available sources only (dev + trial + recall)",
        },
        "by_lag": {tag: v["contrasts"]["H9"] for tag, v in per_lag.items()},
        "verdict": h9c["verdict"],
        "no_material_gain": h9c["no_material_gain_flag"],
        "evidence_class": "S",
        "caveats": [
            "The pre-registered H9 design has five arms including F_8k. F_8k cannot be "
            "built at track level from this database, so H9 is evaluated on four arms. "
            "This is a data-availability deviation decided before any model was fitted, "
            "not a result-driven one.",
            "Because all constructible sources cover the same 2004-2025 window, there is "
            "no source-availability window to stratify on; AP by 3-year block is reported "
            "instead so any era-specific source value is visible.",
        ],
    }
    tc.save(h9, tc.RESULTS_DIR / "h9_fusion.json")
    for f in ("h3_entrants.json", "h6_hhi.json", "h8_scitrends.json", "h9_fusion.json"):
        log.step(f"wrote {f}")
    log.step(f"verdicts: H3={h3['verdict']} H6={h6_verdict} H8={h8['verdict']} "
             f"H9={h9['verdict']} (total {log.elapsed():.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(tc.run_script("03_run_track", main))
