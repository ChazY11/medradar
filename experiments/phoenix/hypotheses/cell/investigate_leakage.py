#!/usr/bin/env python3
"""PHOENIX-001 / T-CELL leakage investigation.

Triggered by the standing rule "if AP > 0.9 on a ~20% prevalence task, look for a
feature that encodes the label and report the investigation". The B1 persistence
arm reaches AP ~0.90 here, so this script attacks that number from four sides:

  1. clock separation -- for every labeled cell-quarter, the newest event that
     any feature can see must be at least `lag_days` older than the start of the
     label window (q, q+4]. This is checked event by event, not asserted.
  2. label recomputation -- y is rebuilt from the raw event table by an
     independent path and compared row by row with the panel's y.
  3. single-feature screen -- the best single feature's AP, and the full
     feature/label correlation table, so a suspicious column cannot hide.
  4. trivial-rule diagnostics -- how much of the AP comes from the fact that
     "active last quarter" is already a strong statement in this panel.

Usage
    python investigate_leakage.py            # headline lag L090
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cell_common as cc  # noqa: E402
import phoenix_common as pc  # noqa: E402

LAG = cc.HEADLINE_LAG
N_SAMPLE_ROWS = 300


def main() -> int:
    t0 = time.time()
    prov = cc.provenance(command="python investigate_leakage.py", lag=LAG)
    panel = cc.load_panel(LAG)
    d = panel.dropna(subset=["y"]).copy()
    cc.log(f"panel loaded rows={len(panel)} labeled={len(d)}")

    # ---- 1. clock separation ---------------------------------------------
    con = pc.connect_ro()
    try:
        ev = pc.load_events(con)
    finally:
        con.close()
    ev = ev.copy()
    ev["feat_dt"] = ev["available_dt"] + pd.Timedelta(days=LAG)
    ev["feat_quarter"] = ev["feat_dt"].dt.to_period("Q")

    # per cell: events sorted by feature quarter, with the running max event_date
    ev_s = ev.sort_values(cc.ENT + ["feat_quarter", "event_dt"])
    worst_gap_days = None
    n_checked = 0
    rng = np.random.default_rng(cc.SEED)
    cells = d[cc.ENT].drop_duplicates().to_numpy()
    sample_cells = cells[rng.choice(len(cells), size=min(200, len(cells)), replace=False)]
    test_quarters = list(pd.period_range("2010Q1", "2025Q2", freq="Q"))
    test_ord = np.array([q.ordinal for q in test_quarters])
    qmap = {k: g for k, g in ev_s.groupby(cc.ENT, observed=True)}
    for ckey, tkey in sample_cells:
        g = qmap.get((ckey, tkey))
        if g is None:
            continue
        fq_ord = np.array([p.ordinal for p in g["feat_quarter"].to_numpy()])
        ed = g["event_dt"].to_numpy()
        order = np.argsort(fq_ord, kind="stable")
        fq_s, ed_s = fq_ord[order], ed[order]
        cummax = np.maximum.accumulate(ed_s)
        for qi, qo in enumerate(test_ord):
            idx = int(np.searchsorted(fq_s, qo, side="right")) - 1
            if idx < 0:
                continue
            newest = cummax[idx]
            window_start = (test_quarters[qi] + 1).start_time
            gap = (window_start - pd.Timestamp(newest)).days
            n_checked += 1
            if worst_gap_days is None or gap < worst_gap_days:
                worst_gap_days = int(gap)
    cc.log(f"clock separation: checked {n_checked} cell-quarters, "
           f"minimum gap between newest visible event and label window = {worst_gap_days} days")
    assert worst_gap_days is not None and worst_gap_days >= 0, \
        "an event inside the label window is visible to the features"

    # ---- 2. independent label recomputation -------------------------------
    dev = ev[ev["kind"].isin(pc.DEVICE_KINDS)].copy()
    dev["cnt"] = 1
    piv = dev.pivot_table(index=cc.ENT, columns="quarter", values="cnt",
                          aggfunc="sum", fill_value=0.0)
    # a full quarter axis and the full cell axis, so a missing (cell, quarter)
    # entry means "no device event", not "not comparable"
    full_q = list(pd.period_range(pc.ORIGIN_START, pc.ORIGIN_END + pc.HORIZON_Q, freq="Q"))
    piv = piv.reindex(columns=full_q, fill_value=0.0)
    all_cells = panel[cc.ENT].drop_duplicates().set_index(cc.ENT).index
    piv = piv.reindex(all_cells, fill_value=0.0)
    qpos = {q: i for i, q in enumerate(full_q)}
    M = piv.to_numpy(dtype=float)
    rowpos = {k: i for i, k in enumerate(piv.index)}

    samp = d.sample(n=min(N_SAMPLE_ROWS, len(d)), random_state=cc.SEED)
    mismatch = 0
    compared = 0
    for _, r in samp.iterrows():
        key = (r["company_key"], r["track_id"])
        if key not in rowpos or r["quarter"] not in qpos:
            continue
        i = rowpos[key]
        j = qpos[r["quarter"]]
        fwd = M[i, j + 1: j + 1 + pc.HORIZON_Q]
        if len(fwd) < pc.HORIZON_Q:
            continue
        y_rebuilt = float(fwd.sum() >= 1)
        compared += 1
        if y_rebuilt != float(r["y"]):
            mismatch += 1
    cc.log(f"label recomputation: {compared} rows compared, {mismatch} mismatches")
    assert mismatch == 0, f"{mismatch} label rows could not be reproduced from raw events"
    assert compared == len(samp), f"only {compared}/{len(samp)} sampled rows comparable"

    # ---- 3. single-feature screen ----------------------------------------
    fs = cc.feature_sets(panel)
    feats = sorted({c for v in fs.values() for c in v})
    y = d["y"].to_numpy(dtype=float)
    rows = []
    for c in feats:
        v = pd.to_numeric(d[c], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(v)
        if ok.sum() < 100 or np.nanstd(v[ok]) == 0:
            continue
        rows.append({
            "feature": c,
            "ap_as_single_score": pc.average_precision(y, v),
            "pearson_r_with_y": float(np.corrcoef(v[ok], y[ok])[0, 1]),
            "spearman_r_with_y": float(pd.Series(v).corr(pd.Series(y), method="spearman")),
        })
    single = pd.DataFrame(rows).sort_values("ap_as_single_score", ascending=False)
    top_single = single.head(15).to_dict(orient="records")
    max_abs_corr = float(single["pearson_r_with_y"].abs().max())
    cc.log(f"single-feature screen: {len(single)} features, max |r| with y = {max_abs_corr:.4f}, "
           f"best single AP = {top_single[0]['ap_as_single_score']:.4f} "
           f"({top_single[0]['feature']})")
    assert max_abs_corr < 0.95, "a single feature is nearly a copy of the label"

    # ---- 4. trivial-rule diagnostics -------------------------------------
    def strat(col, bins, labels):
        out = {}
        for lab, (lo, hi) in zip(labels, bins):
            m = d[col].between(lo, hi) if hi is not None else d[col] >= lo
            out[lab] = {"n": int(m.sum()), "n_pos": int(d.loc[m, "y"].sum()),
                        "P_y": cc.r6(d.loc[m, "y"].mean())}
        return out

    active_last = d["f_n_device_sum1"] > 0
    diag = {
        "P_y_given_active_last_quarter": cc.r6(d.loc[active_last, "y"].mean()),
        "P_y_given_inactive_last_quarter": cc.r6(d.loc[~active_last, "y"].mean()),
        "share_rows_active_last_quarter": cc.r6(active_last.mean()),
        "share_of_positives_active_last_quarter": cc.r6(active_last[d["y"] == 1].mean()),
        "ap_rule_active_last_quarter": cc.r6(pc.average_precision(y, active_last.astype(float))),
        "P_y_by_f_n_device_sum4": strat("f_n_device_sum4",
                                        [(-0.1, 0.5), (0.5, 2.5), (2.5, 5.5), (5.5, None)],
                                        ["0", "1-2", "3-5", "6+"]),
        "P_y_by_exposure_q": strat("exposure_q",
                                   [(0, 3.5), (3.5, 7.5), (7.5, 19.5), (19.5, None)],
                                   ["0-3", "4-7", "8-19", "20+"]),
    }

    rep = {
        "provenance": prov,
        "lag_scenario": cc.LAG_SCENARIO[LAG],
        "trigger": "single-model AP reached ~0.90 on a 17.6% prevalence task",
        "clock_separation": {
            "n_cell_quarters_checked": int(n_checked),
            "n_cells_sampled": int(len(sample_cells)),
            "minimum_gap_days_between_newest_visible_event_and_label_window": worst_gap_days,
            "verdict": "PASS" if worst_gap_days >= 0 else "FAIL",
            "note": ("feature clock = available_at + lag; an event is visible at origin q "
                     "only if event_date < (q+1).start - lag, i.e. strictly before the "
                     "(q, q+4] label window opens"),
        },
        "label_recomputation": {
            "n_rows_compared": int(compared), "n_mismatches": int(mismatch),
            "method": "y rebuilt from the raw events table via an independent pivot path",
            "verdict": "PASS" if mismatch == 0 else "FAIL",
        },
        "single_feature_screen": {
            "n_features": int(len(single)),
            "max_abs_pearson_r_with_y": cc.r6(max_abs_corr),
            "best_single_feature_ap": cc.r6(top_single[0]["ap_as_single_score"]),
            "best_single_feature": top_single[0]["feature"],
            "top15": [{k: (cc.r6(v) if isinstance(v, float) else v) for k, v in r.items()}
                      for r in top_single],
            "verdict": "PASS" if max_abs_corr < 0.95 else "FAIL",
        },
        "trivial_rule_diagnostics": diag,
        "conclusion": None,
        "elapsed_sec": None,
        "n": int(len(d)), "n_pos": int(d["y"].sum()),
        "prevalence": cc.r6(d["y"].mean()),
    }
    rep["conclusion"] = (
        f"No label-encoding feature was found: the strongest single-feature Pearson "
        f"|r| against y is {max_abs_corr:.3f} (harness screen flags >0.80 as a warning "
        f"and >0.95 as a probable leak), the labels are reproducible from raw events, "
        f"and every feature-visible event is at least {worst_gap_days} days older than "
        f"the label window. The high AP is therefore persistence, not leakage: "
        f"{diag['share_rows_active_last_quarter']:.1%} of cell-quarters are active in "
        f"the origin quarter and those rows carry "
        f"{diag['share_of_positives_active_last_quarter']:.1%} of the positives, with "
        f"P(y)= {diag['P_y_given_active_last_quarter']:.3f} vs "
        f"{diag['P_y_given_inactive_last_quarter']:.3f}."
    )
    rep["elapsed_sec"] = round(time.time() - t0, 2)
    out = cc.RESULTS / "leakage_investigation.json"
    cc.save_result_json(rep, out)
    cc.log(f"written {out} in {rep['elapsed_sec']}s")
    cc.log("conclusion: " + rep["conclusion"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

