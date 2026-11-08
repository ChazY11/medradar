#!/usr/bin/env python3
"""PHOENIX-001 / T-CELL structural sensitivity: device-capable cells only.

Why this exists
---------------
The frozen T-CELL unit is "(company_key, track_id) with >=1 event of ANY of the
six kinds", and trials are assigned to a completely different 21-track taxonomy
(t_*) than device events (38 tracks). Consequences, measured in this script:

  * every (company, t_*) cell is structurally incapable of ever being positive,
    because the label counts 510k/pma events only;
  * therefore a large share of the row population is trivially negative, which
    inflates AP for every arm, and
  * H5's "own trial history" is identically zero inside every cell that can be
    positive, i.e. it is not identifiable by construction, not just weak.

This script re-scores the frozen headline samples on the subset of cells that
ever record a device event, using the prediction pickles written by run_cell.py
(no model is refitted, nothing is reselected). It is a reporting sensitivity,
not a new hypothesis.

Usage
    python sensitivity.py
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

CHUNK_DIR = cc.RESULTS / "_chunks"
CONTRASTS = {**cc.PRIMARY_CONTRASTS, **cc.SECONDARY_CONTRASTS}


def main() -> int:
    t0 = time.time()
    prov = cc.provenance(command="python sensitivity.py", lag=cc.HEADLINE_LAG)
    rep = {"provenance": prov, "structural_facts": {}, "by_lag": {}}

    # ---- structural facts (label clock, lag independent) -----------------
    con = pc.connect_ro()
    try:
        ev = pc.load_events(con)
    finally:
        con.close()
    tr_tracks = set(ev.loc[ev["kind"] == "trial", "track_id"].unique())
    dv_tracks = set(ev.loc[ev["kind"].isin(pc.DEVICE_KINDS), "track_id"].unique())
    panel = cc.load_panel(cc.HEADLINE_LAG)
    cells = panel.groupby(cc.ENT, observed=True)["n_device"].sum()
    n_rows = len(panel)
    cell_classes = pd.DataFrame({"n_device": cells})
    cell_classes["is_trial_track"] = [t in tr_tracks for _, t in cell_classes.index]
    cell_classes["device_capable"] = cell_classes["n_device"] > 0
    lab = panel.dropna(subset=["y"])
    cap_index = cell_classes.index[cell_classes["device_capable"]]
    lab_cap = lab.set_index(cc.ENT).index.isin(cap_index)
    rep["structural_facts"] = {
        "n_trial_tracks": len(tr_tracks),
        "n_device_tracks": len(dv_tracks),
        "n_shared_track_ids": len(tr_tracks & dv_tracks),
        "trial_track_prefixes": sorted({t.split("_")[0] for t in tr_tracks}),
        "n_cells_total": int(len(cell_classes)),
        "n_cells_device_capable": int(cell_classes["device_capable"].sum()),
        "n_cells_in_trial_tracks": int(cell_classes["is_trial_track"].sum()),
        "n_cells_neither_device_nor_trial_track": int(
            (~cell_classes["device_capable"] & ~cell_classes["is_trial_track"]).sum()),
        "share_cells_device_capable": cc.r6(cell_classes["device_capable"].mean()),
        "rows_in_device_capable_cells": int(lab_cap.sum()),
        "share_rows_device_capable": cc.r6(lab_cap.mean()),
        "prevalence_all_cells": cc.r6(lab["y"].mean()),
        "prevalence_in_device_capable_cells": cc.r6(lab.loc[lab_cap, "y"].mean()),
        "note": ("a (company, t_*) cell can never satisfy the 510k/pma label, so "
                 "trial-track cells are structurally always-negative rows; likewise "
                 "any cell whose only events are recalls or drug approvals"),
    }
    cc.log("structural facts: " + str({k: rep["structural_facts"][k] for k in
                                       ("n_shared_track_ids", "n_cells_device_capable",
                                        "share_rows_device_capable",
                                        "prevalence_all_cells",
                                        "prevalence_in_device_capable_cells")}))

    # ---- re-score frozen samples on device-capable cells ------------------
    for lag in cc.LAGS:
        tag = cc.LAG_SCENARIO[lag]
        pf = CHUNK_DIR / f"preds_{tag}.pkl"
        if not pf.exists():
            cc.log(f"[{tag}] missing {pf.name}, skipped")
            continue
        preds = pd.read_pickle(pf)
        cap = pd.MultiIndex.from_frame(preds[cc.ENT]).isin(
            cell_classes.index[cell_classes["device_capable"]])
        preds = preds.assign(dev_capable=cap)
        q1 = preds["q1_only"].to_numpy()
        ho = preds["holdout"].to_numpy()
        cap = preds["dev_capable"].to_numpy()
        subsets = {
            "headline_q1_device_capable": q1 & cap,
            "holdout_q1_device_capable": q1 & ho & cap,
            "all_origins_device_capable": cap,
        }
        out = {"n_cells_device_capable": int(cell_classes["device_capable"].sum())}
        for name, mask in subsets.items():
            sub = preds[mask]
            if len(sub) == 0:
                continue
            y = sub["y"].to_numpy(dtype=float)
            grp = sub["company_key"].to_numpy()
            rec = {"n": int(len(sub)), "n_pos": int(y.sum()),
                   "prevalence": cc.r6(y.mean()), "arms": {}, "contrasts": {}}
            for arm in cc.ARM_NAMES:
                s = sub["score_" + arm].to_numpy(dtype=float)
                m = pc.evaluate(y, s, name=arm)
                pt, lo, hi = pc.block_bootstrap_ci(y, s, grp, B=cc.B_BOOT,
                                                   seed=cc.SEED)
                m["ap_ci95"] = {"point": cc.r6(pt), "lo": cc.r6(lo),
                                "hi": cc.r6(hi), "B": cc.B_BOOT}
                rec["arms"][arm] = {"ap": m["ap"], "ap_ci95": m["ap_ci95"],
                                    "roc_auc": m["roc_auc"], "brier": m["brier"],
                                    "calibration_slope": m["calibration_slope"],
                                    "precision_at_10pct": m["precision_at_10pct"],
                                    "lift_at_10pct": m["lift_at_10pct"]}
            for cname, (a, b) in CONTRASTS.items():
                res = pc.paired_bootstrap_diff(
                    y, sub["score_" + a].to_numpy(dtype=float),
                    sub["score_" + b].to_numpy(dtype=float), grp,
                    B=cc.B_BOOT, seed=cc.SEED)
                rec["contrasts"][cname] = {
                    "contrast": f"{a} - {b}", "diff": cc.r6(res["diff"]),
                    "lo95": cc.r6(res.get("lo")), "hi95": cc.r6(res.get("hi")),
                    "p_two_sided": cc.r6(res.get("p")),
                }
            out[name] = rec
            cc.log(f"[{tag}] {name}: n={rec['n']} n_pos={rec['n_pos']} "
                   f"prev={rec['prevalence']} AP(B1)={cc.r6(rec['arms']['B1_persistence']['ap'])} "
                   f"AP(B0)={cc.r6(rec['arms']['B0_prevalence']['ap'])}")
        rep["by_lag"][tag] = out

    rep["interpretation_hint"] = (
        "The frozen task keeps all cells, so these numbers are sensitivities only; "
        "they answer 'does the conclusion survive on the cells that can actually "
        "be positive?'. H5 is different: its added features are identically zero on "
        "every device-capable cell, so H5 has zero within-cell identifiability "
        "regardless of the sample.")
    rep["elapsed_sec"] = round(time.time() - t0, 2)
    rep["n"] = int(len(lab))
    rep["n_pos"] = int(lab["y"].sum())
    rep["prevalence"] = cc.r6(lab["y"].mean())
    out_p = cc.RESULTS / "sensitivity_device_cells.json"
    pc.save_json(rep, out_p)
    cc.log(f"written {out_p} in {rep['elapsed_sec']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
