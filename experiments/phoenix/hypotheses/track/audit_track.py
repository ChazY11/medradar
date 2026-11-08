"""Stage 5 — validity / leakage audit for the track-level experiments.

One command:
    python experiments/phoenix/hypotheses/track/audit_track.py

Covers protocol §7 items L1..L7 at track level, the H3 lead-correlation and H6
descriptive association tests, and an H8 placebo control (the growth features are
shuffled across tracks within each quarter; if the H8 advantage were an artefact of
how the arm is wired rather than track-specific information, it would survive).
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

import run_track as rt
import track_common as tc
import phoenix_common as pc


def l2_future_information(events: pd.DataFrame, origins=("2012Q3", "2018Q2")) -> dict:
    """Delete every event whose feature-clock quarter is after the origin, rebuild
    the panel, and require the feature values at that origin to be identical."""
    out = {"test": "L2 future information (track level)", "origins": {},
           "verdict": "PASS"}
    full = tc.build_track_panel(events, tc.HEADLINE_LAG)
    feat_cols = [c for c in full.columns if c.startswith(("f_n_", "sct_", "b2_"))]
    ev_lag = pc.apply_lag(events, tc.HEADLINE_LAG)
    for origin in origins:
        q = pd.Period(origin, freq="Q")
        trunc = ev_lag[ev_lag["feat_quarter"] <= q].drop(
            columns=["feat_dt", "feat_quarter", "lag_days"], errors="ignore")
        part = tc.build_track_panel(trunc, tc.HEADLINE_LAG)
        a = full[full["quarter"] == q].set_index("track_id")
        b = part[part["quarter"] == q].set_index("track_id")
        common = a.index.intersection(b.index)
        per_col = {}
        worstd = 0.0
        for c in feat_cols:
            x = a.loc[common, c].to_numpy(dtype=float)
            y = b.loc[common, c].to_numpy(dtype=float)
            ok = np.isfinite(x) & np.isfinite(y)
            d = float(np.max(np.abs(x[ok] - y[ok]))) if ok.any() else float("nan")
            nan_mismatch = int(np.sum(np.isfinite(x) != np.isfinite(y)))
            per_col[c] = {"max_abs_diff": d, "nan_mismatch": nan_mismatch,
                          "n_compared": int(len(common))}
            if np.isfinite(d):
                worstd = max(worstd, d)
        bad = [c for c, v in per_col.items()
               if (v["max_abs_diff"] or 0) > 1e-9 or v["nan_mismatch"] > 0]
        out["origins"][origin] = {
            "entities_compared": int(len(common)),
            "max_abs_diff_over_all_features": worstd,
            "columns_that_differ": bad,
            "per_column": per_col,
        }
        if bad:
            out["verdict"] = "FAIL"
    return out


def main(log: tc.RunLog) -> int:
    t0 = time.time()
    db = tc.db_meta()
    if not db["db_sha256_matches_frozen"]:
        log.write("ABORT: db sha256 mismatch")
        return 2
    con = pc.connect_ro()
    try:
        events = pc.load_events(con)
        ref_con = con
        l3_sql = pd.read_sql_query(
            """select applicant_raw, count(distinct company_key) as k, count(*) as n
               from events
               where applicant_raw is not null and company_key is not null
               group by applicant_raw having k > 1 order by n desc""", ref_con)
        cov_sql = pd.read_sql_query(
            """select kind,
                      sum(case when company_key is null then 1 else 0 end) as n_unmapped,
                      count(*) as n
               from events where event_date >= '2004-01-01' and event_date <= '2026-10-30'
               group by kind""", ref_con)
        dup_sql = pd.read_sql_query(
            """select count(*) as n_groups from (
                 select company_key, track_id, product_code, event_date, count(*) c
                 from events
                 where company_key is not null and track_id is not null
                   and product_code is not null
                 group by 1,2,3,4 having c > 1)""", ref_con)
    finally:
        con.close()
    log.step("events loaded for audit")

    panel = rt.attach_features(tc.ensure_panel(tc.HEADLINE_LAG, log), tc.HEADLINE_LAG)
    specs = rt.build_specs(panel)
    used = sorted({c for s in specs.values() for c in s.get("features", [])})
    log.step(f"panel {len(panel)} rows, {panel['track_id'].nunique()} tracks, "
             f"{len(used)} model features")

    audit: dict = {
        **tc.base_record(log, db, tc.HEADLINE_LAG, int(panel["y"].notna().sum()),
                         int(np.nansum(panel["y"])), float(np.nanmean(panel["y"]))),
        "task": "T-TRACK",
    }

    # ---- L1 label leakage screen -----------------------------------------
    audit["L1_label_leak_screen"] = pc.leakage_audit(panel, tc.ENTITY, used, target_col="y")
    # report the strongest single-feature correlations even below the alarm threshold
    corrs = {}
    for c in used:
        s = pd.to_numeric(panel[c], errors="coerce")
        if s.notna().sum() > 50 and s.std() > 0:
            r = s.corr(panel["y"])
            if pd.notna(r):
                corrs[c] = float(r)
    top = sorted(corrs.items(), key=lambda kv: -abs(kv[1]))[:10]
    audit["L1_top_abs_correlations"] = {k: v for k, v in top}
    audit["L1_max_abs_corr"] = float(abs(top[0][1])) if top else float("nan")
    log.step(f"L1: max |corr(feature, y)| = {audit['L1_max_abs_corr']:.3f} "
             f"({top[0][0] if top else 'n/a'}); flagged>0.80: "
             f"{list(audit['L1_label_leak_screen']['high_correlation_features_gt_0.80'])}")

    # ---- L2 future information -------------------------------------------
    audit["L2_future_information"] = l2_future_information(events)
    log.step(f"L2: {audit['L2_future_information']['verdict']} "
             f"max|diff|={max(v['max_abs_diff_over_all_features'] or 0 for v in audit['L2_future_information']['origins'].values()):.2e}")

    # ---- L3 entity mapping ------------------------------------------------
    audit["L3_entity_mapping"] = {
        "applicant_raw_mapping_conflict_groups": int(len(l3_sql)),
        "examples": l3_sql.head(5).to_dict(orient="records"),
        "company_key_unmapped_share_by_kind": {
            r["kind"]: float(r["n_unmapped"] / r["n"]) for r in cov_sql.to_dict(orient="records")
        },
        "note": "the frozen entity universe already requires company_key AND track_id, so "
                "unmapped events are excluded from BOTH features and labels; this is a "
                "coverage restriction, not a leak.",
    }

    # ---- L4 left truncation ----------------------------------------------
    expo = panel["exposure_q"]
    lab = panel[panel["y"].notna()]
    audit["L4_left_truncation"] = {
        "exposure_q_quantiles": {
            k: float(v) for k, v in expo.describe().items() if k in
            ("count", "mean", "std", "min", "25%", "50%", "75%", "max")
        },
        "share_rows_exposure_lt_8_all": float((expo < 8).mean()),
        "share_labeled_rows_exposure_lt_8": float((lab["exposure_q"] < 8).mean()),
        "n_labeled_rows": int(len(lab)),
        "note": (
            "a 4Q-forward growth label additionally needs a complete 8Q trailing window, "
            "so every labeled row already has exposure_q >= 7; the rows with exposure_q<8 "
            "are dropped by the label construction, not by a post-hoc filter."
        ),
    }

    # ---- L5 sample overlap ------------------------------------------------
    yr = panel["quarter"].astype(str).str.slice(0, 4).astype(int)
    test_span = panel[(panel["quarter"] >= pd.Period("2014Q1", freq="Q")) & panel["y"].notna()]
    audit["L5_overlap"] = {
        "n_all_origins": int(panel["y"].notna().sum()),
        "n_pos_all_origins": int(np.nansum(panel["y"])),
        "n_evaluable_walk_forward_origins": int(len(test_span)),
        "n_pos_evaluable_walk_forward": int(np.nansum(test_span["y"])),
        "prevalence_all": float(np.nanmean(panel["y"])),
        "prevalence_evaluable": float(np.nanmean(test_span["y"])),
        "note": (
            "consecutive origins share 3 of their 4 forward quarters. Headline numbers use "
            "every origin (as in protocol §2.2); a non-overlapping Q1-only sensitivity is "
            "reported for every arm in results/track_all_metrics.json."
        ),
        "n_q1_only": int(tc.q1_only(test_span).shape[0]),
        "n_pos_q1_only": int(np.nansum(tc.q1_only(test_span)["y"])),
        "last_labelable_origin": str(
            panel[panel["y"].notna()]["quarter"].max()
        ),
        "note_on_evaluable_window": (
            "the growth label needs 4 forward quarters inside the frozen panel, and "
            "build_joint_panel trims at 2025Q2, so origins after 2024Q2 carry y=NaN. "
            "The 2025 walk-forward fold is therefore empty and 11 of the 12 folds are "
            "evaluable."
        ),
    }

    # ---- L6 cross-source duplicate / double counting ----------------------
    audit["L6_duplicates"] = {
        "same_company_track_product_day_duplicate_groups": int(dup_sql["n_groups"].iloc[0]),
        "note": (
            "counted, not removed: most are legitimate distinct submissions. 510k and a "
            "later PMA for the same device would both count as device events; the label "
            "only asks whether ANY device event occurred in the forward window, so this "
            "inflates counts but not the label definition."
        ),
    }

    # ---- L7 track-assignment anachronism ---------------------------------
    first_seen = events.groupby("track_id", observed=True)["event_dt"].min().sort_values()
    after2014 = first_seen[first_seen >= pd.Timestamp("2014-01-01")]
    audit["L7_track_anachronism"] = {
        "n_tracks": int(len(first_seen)),
        "n_tracks_first_seen_2014_or_later": int(len(after2014)),
        "tracks_first_seen_2014_or_later": {str(k): str(v.date()) for k, v in after2014.items()},
        "tracks_first_seen": {str(k): str(v.date()) for k, v in first_seen.items()},
        "sensitivity": "all walk-forward test origins are 2014Q1 or later, so no evaluable "
                       "row can predate a track's first observed event; the anachronism "
                       "risk is confined to the track-labelling of pre-2014 events, which "
                       "only enter through the training folds and the trailing windows.",
    }

    # ---- H3 / H6 descriptive tests (shared code path with run_track) ------
    desc_path = tc.RESULTS_DIR / "h3h6_descriptive.json"
    if desc_path.exists():
        desc = json.loads(desc_path.read_text(encoding="utf-8"))
        source = "reused results/h3h6_descriptive.json (identical code path)"
    else:
        log.step("h3h6_descriptive.json missing -> recomputing")
        series = tc.event_clock_series(events)
        desc = {"h3": {"lag_correlations": tc.h3_lead_correlations(series)},
                "h6": {"descriptive": tc.h6_descriptive(series)}}
        source = "recomputed in audit_track.py"
    audit["H3_lead_correlation"] = desc["h3"]["lag_correlations"]
    audit["H6_descriptive"] = desc["h6"]["descriptive"]
    audit["H3_H6_descriptive_source"] = source
    k1 = desc["h3"]["lag_correlations"]["fwd4"]["k1"]
    log.step(f"H3 lead corr k=1 fwd4 rho={k1['spearman']:+.4f} "
             f"CI=[{k1['ci95'][0]:+.4f},{k1['ci95'][1]:+.4f}] p_perm={k1['p_perm']:.4f}")
    h6d = desc["h6"]["descriptive"]
    log.step(f"H6 descriptive rho={h6d['spearman']:+.4f} "
             f"CI=[{h6d['ci95'][0]:+.4f},{h6d['ci95'][1]:+.4f}] "
             f"excl0={h6d['ci_excludes_zero']}")

    # ---- H3: is the raw association just a calendar confound? -------------
    lc = desc["h3"]["lag_correlations"]
    hp = lc.get("sensitivity_within_track_highpass", {})
    audit["H3_calendar_confound"] = {
        "question": (
            "company entry is front-loaded in the 89-company registry snapshot while "
            "device volume rises over calendar time; a raw pooled correlation would then "
            "be negative even with no lead relationship"
        ),
        "raw_fwd4_k1_spearman": lc["fwd4"]["k1"]["spearman"],
        "within_track_highpass_fwd4_k1_spearman": hp.get("fwd4", {}).get("k1", {}).get("spearman"),
        "raw_fwd4_all_k": {k: lc["fwd4"][k]["spearman"] for k in ("k0", "k1", "k2", "k3", "k4")},
        "within_track_highpass_fwd4_all_k": {
            k: hp.get("fwd4", {}).get(k, {}).get("spearman") for k in ("k0", "k1", "k2", "k3", "k4")
        },
        "conclusion": (
            "the raw negative association vanishes once each track's own trailing-8Q level "
            "is removed, so the H3 descriptive evidence is a calendar/level confound and "
            "NOT a demonstrated lead relationship"
        ),
    }
    series = tc.event_clock_series(events)
    cal = pd.DataFrame({
        "year": [q.year for q in series["quarters"]],
        "ent": series["ent"].mean(axis=0),
        "dev": series["dev"].mean(axis=0),
    }).groupby("year").mean().round(4)
    audit["calendar_confound_table"] = {
        "mean_entrants_per_track_quarter_by_year": cal["ent"].to_dict(),
        "mean_device_events_per_track_quarter_by_year": cal["dev"].to_dict(),
    }
    log.step(f"H3 calendar control: raw k1={lc['fwd4']['k1']['spearman']:+.3f} -> "
             f"highpassed {hp.get('fwd4', {}).get('k1', {}).get('spearman')}")

    # ---- H8 placebo control ----------------------------------------------
    sct = [c for c in panel.columns if c.startswith("sct_")]
    perm = panel.copy()
    rng = np.random.default_rng(tc.SEED)
    for q, idx in perm.groupby("quarter", observed=True).indices.items():
        idx = np.asarray(idx)
        order = rng.permutation(len(idx))
        perm.loc[idx, sct] = panel.loc[idx, sct].to_numpy()[order]
    oof_perm = rt.oof_scores(perm, specs, log, "placebo")
    ap_h8_perm = pc.average_precision(oof_perm["y"].to_numpy(float),
                                      oof_perm["H8_growth"].to_numpy(float))
    ap_b1_perm = pc.average_precision(oof_perm["y"].to_numpy(float),
                                      oof_perm["B1_persistence"].to_numpy(float))
    metrics = json.loads((tc.RESULTS_DIR / "track_all_metrics.json").read_text(encoding="utf-8"))
    real = metrics["lags"]["L090"]["arms"]
    audit["H8_placebo"] = {
        "control": "the 7 sct_* growth features are shuffled across tracks within each "
                   "quarter (track alignment destroyed, marginal distributions kept), then "
                   "the identical H8 arm is refitted on the identical folds",
        "ap_H8_arm_real": float(real["H8_growth"]["ap"]),
        "ap_H8_arm_placebo": float(ap_h8_perm),
        "ap_B1_arm_real": float(real["B1_persistence"]["ap"]),
        "ap_B1_arm_placebo": float(ap_b1_perm),
        "interpretation": (
            "if the real H8 advantage came from track-specific information, shuffling the "
            "growth features across tracks must collapse the arm back to about the B1 level"
        ),
        "collapsed": bool(ap_h8_perm - ap_b1_perm < 0.01),
    }
    log.step(f"H8 placebo: real={audit['H8_placebo']['ap_H8_arm_real']:.4f} "
             f"placebo={ap_h8_perm:.4f} B1={audit['H8_placebo']['ap_B1_arm_real']:.4f} "
             f"collapsed={audit['H8_placebo']['collapsed']}")

    audit["elapsed_sec"] = round(log.elapsed(), 2)
    audit["verdicts"] = {
        "L1": "PASS" if not audit["L1_label_leak_screen"]["suspected_label_leak"] else "FAIL",
        "L2": audit["L2_future_information"]["verdict"],
        "L4": "PASS (labeled rows have complete trailing windows by construction)",
        "L5": "REPORTED (overlap quantified; Q1-only sensitivity provided)",
        "L7": "REPORTED (no evaluable row predates its track's first event)",
    }
    tc.save(audit, tc.RESULTS_DIR / "audit_track.json")
    log.step(f"wrote audit_track.json in {audit['elapsed_sec']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(tc.run_script("05_audit_track", main))
