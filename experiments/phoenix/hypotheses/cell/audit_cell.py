#!/usr/bin/env python3
"""PHOENIX-001 / T-CELL audits + H1/H2 descriptive statistics.

Covers the protocol §7 audit list as far as it is measurable for the cell panel:

  L1  automated label-leak screen (phoenix_common.leakage_audit)
  L2  future-information test -- executed by selftest.py, embedded here from
      results/selftest.json (same check, one implementation, no duplicated cost)
  L3  entity mapping: unmapped company_key / track_id shares, mapping conflicts
  L4  left truncation: exposure_q distribution, share of rows with exposure < 8
  L5  overlapping origins: overlap accounting of the forward windows
  L6  cross-source duplication: same company/track/product_code/day groups and
      510k -> PMA double-counting of the same product
  L7  track-taxonomy anachronism: first-seen quarter per track, share of cell
      rows whose track appears only after 2014
  L8  single-snapshot backfill: recorded as an irreducible limitation

Plus the pre-registered descriptive statistics:
  H1  Spearman autocorrelation of the quarterly own-activity series (lag 1 and
      lag 4) with a company-clustered bootstrap CI, and
      P(active_{t+1} | active_t) against a rate-matched permutation null.
  H2  forward 4-quarter rate ratio for acceleration events, with a
      company-clustered bootstrap CI, a permutation p, and the median lead time
      in quarters (right censoring reported).
  H5  median lead time from first trial activity to the next device milestone.

Usage
    python audit_cell.py            # all lags for the descriptive sensitivity
    python audit_cell.py --lag 90   # headline lag only
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cell_common as cc  # noqa: E402
import phoenix_common as pc  # noqa: E402

N_PERM = 200


# --------------------------------------------------------------- CI helpers
def cluster_mean_ci(values, groups, B: int = cc.B_BOOT, seed: int = cc.SEED) -> dict:
    """Company-clustered bootstrap CI for the mean of a per-cell statistic."""
    df = pd.DataFrame({"v": np.asarray(values, dtype=float),
                       "g": np.asarray(groups)}).dropna()
    if df.empty:
        return {"point": None, "lo": None, "hi": None, "n_units": 0}
    v = df["v"].to_numpy()
    garr = df["g"].to_numpy()
    uniq = np.unique(garr)
    idx = [np.flatnonzero(garr == g) for g in uniq]
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        pick = rng.integers(0, len(uniq), size=len(uniq))
        cat = np.concatenate([idx[i] for i in pick])
        vals.append(v[cat].mean())
    lo, hi = np.quantile(vals, [0.025, 0.975])
    return {"point": cc.r6(v.mean()), "lo": cc.r6(lo), "hi": cc.r6(hi),
            "n_units": int(len(v)), "n_clusters": int(len(uniq)), "B": B}


def cluster_ratio_ci(num_hit, num_den, groups, B: int = cc.B_BOOT,
                     seed: int = cc.SEED) -> dict:
    """Company-clustered bootstrap CI for a ratio of two binomial rates."""
    hit = np.asarray(num_hit, dtype=float)
    den = np.asarray(num_den, dtype=float)
    garr = np.asarray(groups)
    ok = np.isfinite(hit) & np.isfinite(den)
    hit, den, garr = hit[ok], den[ok], garr[ok]
    uniq = np.unique(garr)
    idx = [np.flatnonzero(garr == g) for g in uniq]
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        pick = rng.integers(0, len(uniq), size=len(uniq))
        cat = np.concatenate([idx[i] for i in pick])
        h, d = hit[cat].sum(), den[cat].sum()
        if d > 0:
            vals.append(h / d)
    if len(vals) < 20:
        return {"point": None, "lo": None, "hi": None}
    lo, hi = np.quantile(vals, [0.025, 0.975])
    return {"point": cc.r6(hit.sum() / den.sum()), "lo": cc.r6(lo), "hi": cc.r6(hi),
            "B": B, "n_clusters": int(len(uniq))}


# ------------------------------------------------------------- L1..L8 audits
def audit_l1(panel: pd.DataFrame) -> dict:
    labeled = panel.dropna(subset=["y"])
    fs = cc.feature_sets(panel)
    feats = sorted({c for v in fs.values() for c in v})
    out = pc.leakage_audit(labeled, cc.ENT, feats, target_col="y")
    out["note"] = ("|corr|>0.80 warns, >0.95 is declared a probable label leak. "
                   "No feature is derived from the label window; the screen is on "
                   "the feature/label correlation at row level.")
    return out


def audit_l2(panel_meta_path: Path) -> dict:
    p = cc.RESULTS / "selftest.json"
    if not p.exists():
        return {"status": "MISSING",
                "note": "run selftest.py first; L2 is proved there"}
    st = pc.json.loads(p.read_text(encoding="utf-8"))
    l2 = st.get("L2_future_information")
    if not l2:
        return {"status": "MISSING"}
    return {"status": l2.get("verdict"), "source": "results/selftest.json",
            "detail": l2}


def audit_l3() -> dict:
    con = pc.connect_ro()
    try:
        cov = pd.read_sql_query(
            "select kind, count(*) n, "
            "sum(case when company_key is null then 1 else 0 end) no_company, "
            "sum(case when track_id is null then 1 else 0 end) no_track, "
            "sum(case when company_key is null or track_id is null then 1 else 0 end) no_cell "
            "from events where event_date >= '2004-01-01' and event_date <= '2026-10-30' "
            "group by kind", con)
        conf = pd.read_sql_query(
            "select applicant_raw, count(distinct company_key) k, count(*) n from events "
            "where company_key is not null and applicant_raw is not null "
            "group by applicant_raw having k > 1 order by k desc, n desc limit 20", con)
        multi = pd.read_sql_query(
            "select count(*) c, sum(n) n_events from ("
            " select applicant_raw, count(distinct company_key) k, count(*) n from events "
            " where company_key is not null and applicant_raw is not null "
            " group by applicant_raw having k > 1)", con)
    finally:
        con.close()
    rows = {}
    for _, r in cov.iterrows():
        rows[r["kind"]] = {
            "n": int(r["n"]),
            "share_no_company_key": round(float(r["no_company"]) / float(r["n"]), 4),
            "share_no_track_id": round(float(r["no_track"]) / float(r["n"]), 4),
            "share_not_in_cell_universe": round(float(r["no_cell"]) / float(r["n"]), 4),
        }
    device_n = rows.get("510k", {}).get("n", 0) + rows.get("pma", {}).get("n", 0)
    device_drop = (rows.get("510k", {}).get("share_not_in_cell_universe", 0) * rows.get("510k", {}).get("n", 0)
                   + rows.get("pma", {}).get("share_not_in_cell_universe", 0) * rows.get("pma", {}).get("n", 0))
    return {
        "by_kind": rows,
        "device_events_in_window": int(device_n),
        "device_events_not_in_cell_universe": int(round(device_drop)),
        "device_share_not_in_cell_universe": round(device_drop / device_n, 4) if device_n else None,
        "applicant_raw_mapping_conflict_groups": int(multi["c"].iloc[0]),
        "applicant_raw_mapping_conflict_events": int(multi["n_events"].iloc[0]),
        "examples": conf.head(10).to_dict(orient="records"),
        "note": ("the label universe is (510k, pma) that carry BOTH company_key and "
                 "track_id; every device event outside that intersection is invisible "
                 "to T-CELL. That is the binding coverage bias, not a nuisance."),
    }


def audit_l4(panel: pd.DataFrame) -> dict:
    labeled = panel.dropna(subset=["y"])
    ex = labeled["exposure_q"]
    return {
        "exposure_q_quantiles_labeled_rows": {
            str(k): float(v) for k, v in ex.describe(
                percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).items()},
        "share_labeled_rows_exposure_lt_8": cc.r6((ex < 8).mean()),
        "n_labeled_rows_exposure_lt_8": int((ex < 8).sum()),
        "share_labeled_rows_exposure_lt_4": cc.r6((ex < 4).mean()),
        "cells_with_exposure_lt_8_at_some_origin": int(
            labeled.loc[labeled["exposure_q"] < 8, cc.ENT]
            .drop_duplicates().shape[0]),
        "n_cells": int(labeled.groupby(cc.ENT, observed=True).ngroups),
        "note": ("exposure_q < 8 cells are still observable (they have events); the "
                 "exclusion sensitivity is reported as headline_q1_exposure8 in "
                 "results/cell_all_metrics.json"),
    }


def audit_l5(panel: pd.DataFrame) -> dict:
    labeled = panel.dropna(subset=["y"])
    q1 = labeled[labeled["q1_only"]]
    return {
        "all_origins": {"n": int(len(labeled)), "n_pos": int(labeled["y"].sum()),
                        "prev": cc.r6(labeled["y"].mean())},
        "non_overlapping_q1_origins": {
            "n": int(len(q1)), "n_pos": int(q1["y"].sum()),
            "prev": cc.r6(q1["y"].mean()),
            "share_of_all_rows": cc.r6(len(q1) / len(labeled))},
        "max_cells_per_origin": int(labeled.groupby("quarter", observed=True).size().max()),
        "origins": int(labeled["quarter"].nunique()),
        "note": ("adjacent origins share 3 of 4 forward quarters; only Q1 origins "
                 "are non-overlapping and they carry the headline numbers"),
    }


def audit_l6() -> dict:
    con = pc.connect_ro()
    try:
        dup = pd.read_sql_query(
            "select count(*) c from (select company_key, track_id, product_code, "
            "substr(event_date,1,10) d from events "
            "where company_key is not null and track_id is not null and product_code is not null "
            "group by 1,2,3,4 having count(*) > 1)", con)
        a = pd.read_sql_query(
            "select company_key, product_code, event_date d510 from events "
            "where kind = '510k' and company_key is not null and product_code is not null "
            "and event_date is not null", con)
        b = pd.read_sql_query(
            "select company_key, product_code, event_date dpma from events "
            "where kind = 'pma' and company_key is not null and product_code is not null "
            "and event_date is not null", con)
    finally:
        con.close()
    # pandas merge instead of a SQL self-join: the pair-keyed join is tiny here,
    # while the unindexed self-join is O(n^2) in sqlite.
    m = a.merge(b, on=["company_key", "product_code"], how="inner")
    dt = (pd.to_datetime(m["dpma"]) - pd.to_datetime(m["d510"])).dt.days
    win = dt[(dt > 0) & (dt <= 730)]
    return {
        "same_company_track_code_day_duplicate_groups": int(dup["c"].iloc[0]),
        "same_company_code_510k_pma_pairs_total": int(len(m)),
        "n_510k_rows_with_company_and_code": int(len(a)),
        "n_pma_rows_with_company_and_code": int(len(b)),
        "pma_within_730d_after_510k_same_company_code": int(len(win)),
        "pma_within_730d_median_delay_days": cc.r6(win.median()) if len(win) else None,
        "note": ("y counts events, not distinct products, so a PMA that follows a 510k "
                 "on the same product_code inside the same forward window makes that "
                 "window positive twice over. The pair count above bounds that "
                 "double-counting channel."),
    }


def audit_l7(panel: pd.DataFrame) -> dict:
    con = pc.connect_ro()
    try:
        ev = pc.load_events(con)
    finally:
        con.close()
    dev = ev[ev["kind"].isin(pc.DEVICE_KINDS)]
    first = dev.groupby("track_id", observed=True)["event_dt"].min()
    labeled = panel.dropna(subset=["y"])
    cells = labeled.groupby(cc.ENT, observed=True).size().reset_index(name="n")
    cells["track_first"] = cells["track_id"].map(first)
    cells_after14 = cells["track_first"] >= pd.Timestamp("2014-01-01")
    track_after14 = (first >= pd.Timestamp("2014-01-01"))
    return {
        "n_tracks_in_cell_universe": int(panel["track_id"].nunique()),
        "track_first_seen": first.dt.strftime("%Y-%m-%d").to_dict(),
        "cells_whose_track_first_appears_after_2014": int(cells_after14.sum()),
        "share_cells_track_first_after_2014": cc.r6(cells_after14.mean()),
        "cells_whose_track_first_appears_after_2018": int(
            (cells["track_first"] >= pd.Timestamp("2018-01-01")).sum()),
        "share_labeled_rows_in_post_2014_tracks": cc.r6(
            labeled["track_id"].map(track_after14).fillna(False).mean()),
        "note": ("all evaluated folds are >= 2014, so the anachronism window is the "
                 "2014-2025 test block itself: a track whose taxonomy label only "
                 "exists because of post-2014 events cannot be back-projected cleanly "
                 "for its own first years"),
    }


def audit_l8() -> dict:
    return {
        "issue": "single snapshot: fetched_at covers only 2026-10-30/31",
        "consequence": ("available_at == event_date for every row, so no real "
                        "point-in-time clock exists; the L090 lag scenario is an "
                        "injected assumption. Histories may contain backfilled "
                        "track assignments (see L7). Irreducible; not corrected."),
    }


# --------------------------------------------------------- H1 descriptives
def _cell_series(panel: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, list[str], list[str]]:
    """Dense (cells x quarters) matrix of own device-event counts on the LABEL clock."""
    piv = panel.pivot_table(index=cc.ENT, columns="quarter", values="n_device",
                            aggfunc="sum", fill_value=0.0)
    cols = sorted(piv.columns)
    piv = piv[cols]
    cells = piv.index
    companies = [c for c, _ in cells]
    return piv.to_numpy(dtype=float), np.array([str(c) for c in cols]), companies, \
        [f"{c}|{t}" for c, t in cells]


def h1_descriptives(panel: pd.DataFrame, n_perm: int = N_PERM) -> dict:
    M, qlabels, companies, cell_labels = _cell_series(panel)
    n_cells, n_q = M.shape
    companies = np.asarray(companies)

    # --- Spearman autocorrelation per cell -----------------------------
    out_ac = {}
    for lag in (1, 2, 4):
        rhos = []
        for i in range(n_cells):
            x, y = M[i, :-lag], M[i, lag:]
            if np.std(x) == 0 or np.std(y) == 0:
                continue
            r = sps.spearmanr(x, y).statistic
            if np.isfinite(r):
                rhos.append((r, companies[i]))
        if rhos:
            vals = np.array([r for r, _ in rhos])
            grp = np.array([g for _, g in rhos])
            out_ac[f"lag{lag}"] = cluster_mean_ci(vals, grp)
            out_ac[f"lag{lag}"]["share_positive"] = cc.r6(float((vals > 0).mean()))
    out_ac["n_cells_in_panel"] = int(n_cells)
    out_ac["note"] = ("per-cell Spearman between the quarterly own-device-event count "
                      "series and its lag-k self; cells with a constant series are "
                      "skipped (ties are dense: most cell-quarters are 0)")

    # --- P(active_{t+1} | active_t) vs rate-matched permutation null ----
    active = M > 0
    prev = float(M.sum() / (active.size))  # mean count per cell-quarter
    act_rate = float(active.mean())
    p11_obs = float(active[:, :-1][active[:, :-1] & active[:, 1:]].size
                    / active[:, :-1].sum())
    p01_obs = float(active[:, 1:][~active[:, :-1] & active[:, 1:]].size
                    / (~active[:, :-1]).sum() if (~active[:, :-1]).sum() else np.nan)
    rng = np.random.default_rng(cc.SEED)
    null = []
    for _ in range(n_perm):
        A2 = np.empty_like(M)
        for i in range(n_cells):
            A2[i] = rng.permutation(M[i])
        act2 = A2 > 0
        denom = act2[:, :-1].sum()
        null.append(float((act2[:, :-1] & act2[:, 1:]).sum() / denom) if denom else np.nan)
    null = np.asarray([v for v in null if np.isfinite(v)])
    p_perm = (1 + int((null >= p11_obs).sum())) / (1 + len(null))
    return {
        "autocorrelation_spearman": out_ac,
        "persistence_transition": {
            "definition": "active_t := own device-event count in quarter t > 0 (label clock)",
            "mean_count_per_cell_quarter": cc.r6(prev),
            "share_active_cell_quarters": cc.r6(act_rate),
            "P_active_t1_given_active_t": cc.r6(p11_obs),
            "P_active_t_given_inactive_t1": cc.r6(p01_obs),
            "lift_vs_unconditional": cc.r6(p11_obs / act_rate) if act_rate else None,
            "permutation_null_rate_matched": {
                "n_perm": int(len(null)),
                "mean": cc.r6(null.mean()),
                "q95": cc.r6(np.quantile(null, 0.95)),
                "p_value_empirical": cc.r6(p_perm),
                "null_construction": ("each cell's own count series is permuted in time, "
                                      "so every cell keeps its activity level exactly; "
                                      "only the temporal order is destroyed"),
            },
        },
        "base_rate_vs_history_stratum": {
            "P_y_given_no_recent_device_activity": cc.r6(
                panel.loc[panel["f_n_device_sum4"] == 0, "y"].mean()),
            "P_y_given_1_to_2_recent": cc.r6(
                panel.loc[panel["f_n_device_sum4"].between(1, 2), "y"].mean()),
            "P_y_given_3plus_recent": cc.r6(
                panel.loc[panel["f_n_device_sum4"] >= 3, "y"].mean()),
            "n_by_stratum": {
                "0": int((panel["f_n_device_sum4"] == 0).sum()),
                "1-2": int(panel["f_n_device_sum4"].between(1, 2).sum()),
                "3+": int((panel["f_n_device_sum4"] >= 3).sum()),
            },
        },
    }


# --------------------------------------------------------- H2 / H5 descriptives
def _lead_time(panel: pd.DataFrame, signal_mask: pd.Series, max_lead: int = 60) -> dict:
    """Quarters from a signal quarter to the next own device event (label clock)."""
    work = panel[cc.ENT + ["quarter", "n_device"]].copy()
    work = work.sort_values(cc.ENT + ["quarter"])
    work["sig"] = signal_mask.to_numpy()
    leads, censored = [], 0
    for _, g in work.groupby(cc.ENT, observed=True, sort=False):
        qs = g["quarter"].to_numpy()
        n_dev = g["n_device"].to_numpy()
        sig = g["sig"].to_numpy()
        for i in np.flatnonzero(sig):
            fut = np.flatnonzero(n_dev[i + 1:] > 0)
            if len(fut) == 0:
                censored += 1
                continue
            lead = int(fut[0] + 1)
            if lead <= max_lead:
                leads.append(lead)
    leads = np.asarray(leads, dtype=float)
    return {
        "n_signal_events": int(signal_mask.sum()),
        "n_with_subsequent_event": int(len(leads)),
        "n_right_censored": int(censored),
        "share_censored": cc.r6(censored / max(1, int(signal_mask.sum()))),
        "median_lead_quarters": cc.r6(np.median(leads)) if len(leads) else None,
        "q25_lead_quarters": cc.r6(np.quantile(leads, 0.25)) if len(leads) else None,
        "q75_lead_quarters": cc.r6(np.quantile(leads, 0.75)) if len(leads) else None,
        "note": ("lead counted in quarters from the signal origin to the first later "
                 "quarter with a device event; signal events with no later event in "
                 "the data are right-censored and reported, not imputed"),
    }


def h2_descriptives(panel: pd.DataFrame, n_perm: int = N_PERM) -> dict:
    p = panel.dropna(subset=["y"]).copy()
    # frozen definition: accel > 0 AND trailing 4-quarter own count >= 2
    gate = p["f_n_device_sum4"] >= 2
    accel = p["f_n_device_accel"] > 0
    ev = gate & accel
    rest = ~ev
    y = p["y"].to_numpy(dtype=float)
    groups = p["company_key"].to_numpy()
    hit_ev = (y * ev.to_numpy())
    den_ev = ev.to_numpy().astype(float)
    hit_rest = (y * rest.to_numpy())
    den_rest = rest.to_numpy().astype(float)
    r_ev = cluster_ratio_ci(hit_ev, den_ev, groups)
    r_rest = cluster_ratio_ci(hit_rest, den_rest, groups)
    point_ratio = (r_ev["point"] / r_rest["point"]) if (r_ev["point"] and r_rest["point"]) else None
    # bootstrap the ratio itself
    uniq = np.unique(groups)
    idx = [np.flatnonzero(groups == g) for g in uniq]
    rng = np.random.default_rng(cc.SEED)
    ratios = []
    for _ in range(cc.B_BOOT):
        pick = rng.integers(0, len(uniq), size=len(uniq))
        cat = np.concatenate([idx[i] for i in pick])
        a = hit_ev[cat].sum() / max(1.0, den_ev[cat].sum())
        b = hit_rest[cat].sum() / max(1.0, den_rest[cat].sum())
        if b > 0:
            ratios.append(a / b)
    ratios = np.asarray(ratios)
    # permutation p for "acceleration adds nothing over the same activity gate"
    obs = float(hit_ev.sum() / max(1.0, den_ev.sum()) - hit_rest.sum() / max(1.0, den_rest.sum()))
    null = []
    for _ in range(n_perm):
        perm = rng.permutation(ev.to_numpy())
        a = y[perm].sum() / max(1.0, perm.sum())
        b = y[~perm].sum() / max(1.0, (~perm).sum())
        null.append(a - b)
    null = np.asarray(null)
    p_perm = (1 + int((null >= obs).sum())) / (1 + len(null))
    # strata: among active cells only (same gate), accel vs not
    sub = p[gate]
    return {
        "definition": ("acceleration event := f_n_device_accel > 0 AND trailing "
                       "4-quarter own device count >= 2 (protocol §6 H2); features "
                       "on the lagged clock, label on the event clock"),
        "n_rows": int(len(p)),
        "n_accel_events": int(ev.sum()),
        "share_accel_events": cc.r6(ev.mean()),
        "forward_rate_accel": cc.r6(hit_ev.sum() / max(1.0, den_ev.sum())),
        "forward_rate_non_accel": cc.r6(hit_rest.sum() / max(1.0, den_rest.sum())),
        "forward_rate_ratio": cc.r6(point_ratio),
        "forward_rate_ratio_ci95": {"lo": cc.r6(np.quantile(ratios, 0.025)),
                                    "hi": cc.r6(np.quantile(ratios, 0.975)),
                                    "B": cc.B_BOOT, "cluster": "company_key"},
        "forward_rate_accel_ci95": r_ev,
        "forward_rate_non_accel_ci95": r_rest,
        "permutation_test": {
            "statistic": "P(y|accel) - P(y|not accel)",
            "observed": cc.r6(obs),
            "n_perm": int(len(null)),
            "p_value_empirical": cc.r6(p_perm),
            "null_mean": cc.r6(null.mean()),
            "null_q95": cc.r6(np.quantile(null, 0.95)),
        },
        "within_gate_strata": {
            "n_active_rows": int(len(sub)),
            "P_y_given_accel_and_gate": cc.r6(sub.loc[sub["f_n_device_accel"] > 0, "y"].mean()),
            "P_y_given_no_accel_and_gate": cc.r6(
                sub.loc[sub["f_n_device_accel"] <= 0, "y"].mean()),
            "note": "same activity gate on both sides: isolates acceleration from level",
        },
        "lead_time": _lead_time(panel, panel["f_n_device_accel"].gt(0)
                                & panel["f_n_device_sum4"].ge(2)),
    }


def h5_lead_time(panel: pd.DataFrame) -> dict:
    out = _lead_time(panel, panel["f_n_trial"] > 0)
    out["definition"] = ("signal := a cell-quarter with any trial event on the lagged "
                         "feature clock; target := next quarter with a device "
                         "(510k/pma) event on the event clock")
    out["note"] = ("there is no public device-level trial-to-approval key, so this is "
                   "a within-cell co-movement lead time, not a causal chain")
    return out


# --------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lag", type=int, default=None, choices=[0, 90, 180])
    ap.add_argument("--skip-ledger", action="store_true")
    args = ap.parse_args()
    lags = [args.lag] if args.lag is not None else list(cc.LAGS)
    t0 = time.time()
    tag = cc.LAG_SCENARIO[cc.HEADLINE_LAG]
    prov = cc.provenance(command="python audit_cell.py" +
                         (f" --lag {args.lag}" if args.lag is not None else ""),
                         lag=cc.HEADLINE_LAG)
    cc.log(f"audit started, headline panel {tag}")

    panel = cc.load_panel(cc.HEADLINE_LAG)
    cc.log(f"panel loaded rows={len(panel)}")

    rep = {
        "provenance": prov,
        "lag_scenario": tag,
        "panel": {
            "rows": int(len(panel)),
            "labeled_rows": int(panel["y"].notna().sum()),
            "n_pos": int(panel["y"].sum()),
            "prevalence": cc.r6(panel["y"].mean()),
            "n_cells": int(panel.groupby(cc.ENT, observed=True).ngroups),
            "n_companies": int(panel["company_key"].nunique()),
            "n_tracks": int(panel["track_id"].nunique()),
            "origins": int(panel["quarter"].nunique()),
            "origin_first": str(panel["quarter"].min()),
            "origin_last": str(panel["quarter"].max()),
        },
        "L1_label_leak_screen": audit_l1(panel),
        "L2_future_information": audit_l2(cc.meta_path()),
        "L3_entity_mapping": audit_l3(),
        "L4_left_truncation": audit_l4(panel),
        "L5_overlapping_origins": audit_l5(panel),
        "L6_cross_source_duplication": audit_l6(),
        "L7_track_anachronism": audit_l7(panel),
        "L8_single_snapshot": audit_l8(),
        "H1_descriptives": h1_descriptives(panel),
        "H2_descriptives": h2_descriptives(panel),
        "H5_lead_time": h5_lead_time(panel),
    }
    cc.log(f"core audits done ({time.time()-t0:.1f}s)")

    # per-lag sensitivity of the H2 descriptive ratio
    h2_by_lag = {}
    for lag in lags:
        if lag == cc.HEADLINE_LAG:
            h2_by_lag[cc.LAG_SCENARIO[lag]] = {
                "forward_rate_ratio": rep["H2_descriptives"]["forward_rate_ratio"],
                "forward_rate_ratio_ci95": rep["H2_descriptives"]["forward_rate_ratio_ci95"],
                "n_accel_events": rep["H2_descriptives"]["n_accel_events"],
            }
            continue
        p2 = cc.load_panel(lag).dropna(subset=["y"]).copy()
        ev = (p2["f_n_device_sum4"] >= 2) & (p2["f_n_device_accel"] > 0)
        y = p2["y"].to_numpy(dtype=float)
        hit = y * ev.to_numpy()
        den = ev.to_numpy().astype(float)
        a = hit.sum() / max(1.0, den.sum())
        b = (y * (~ev.to_numpy())).sum() / max(1.0, (~ev.to_numpy()).sum())
        h2_by_lag[cc.LAG_SCENARIO[lag]] = {
            "forward_rate_accel": cc.r6(a), "forward_rate_non_accel": cc.r6(b),
            "forward_rate_ratio": cc.r6(a / b) if b else None,
            "n_accel_events": int(ev.sum()),
            "note": "ratio only (no CI) -- sensitivity across the three lag scenarios",
        }
        del p2
    rep["H2_descriptives"]["by_lag_scenario"] = h2_by_lag

    rep["elapsed_sec"] = round(time.time() - t0, 2)
    rep["n"] = rep["panel"]["labeled_rows"]
    rep["n_pos"] = rep["panel"]["n_pos"]
    rep["prevalence"] = rep["panel"]["prevalence"]
    out = cc.RESULTS / "audit_cell.json"
    pc.save_json(rep, out)
    cc.log(f"written {out}  elapsed={rep['elapsed_sec']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
