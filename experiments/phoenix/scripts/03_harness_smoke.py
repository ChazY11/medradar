#!/usr/bin/env python3
"""PHOENIX-001 / harness smoke test on the real database.

Proves the shared harness runs, and records the real prevalence / sample sizes
that the frozen protocol has to be written against.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
import phoenix_common as pc  # noqa: E402

OUT = HERE.parent / "reports" / "03_harness_smoke.json"


def main() -> int:
    t0 = time.time()
    rep: dict = {"harness": pc.HARNESS_VERSION, "protocol": pc.PROTOCOL_VERSION}
    rep["db"] = pc.verify_db(check_hash=True)

    con = pc.connect_ro()
    try:
        ev = pc.load_events(con)
        ref = pc.load_reference(con)
    finally:
        con.close()

    rep["events_loaded"] = int(len(ev))
    rep["events_by_kind"] = ev["kind"].value_counts().to_dict()
    rep["events_date_range"] = [str(ev["event_dt"].min().date()), str(ev["event_dt"].max().date())]
    rep["availability_lag_days"] = {
        k: float(v)
        for k, v in ((ev["available_dt"] - ev["event_dt"]).dt.days.describe().items())
        if k in ("mean", "50%", "min", "max")
    }
    rep["n_companies"] = int(ev["company_key"].nunique())
    rep["n_tracks"] = int(ev["track_id"].nunique())
    rep["n_cells"] = int(ev.groupby(["company_key", "track_id"], observed=True).ngroups)
    rep["ref_tables"] = {k: int(len(v)) for k, v in ref.items() if hasattr(v, "__len__")}

    # ---- cell-level panel -------------------------------------------------
    cells = pc.build_panel(ev, ["company_key", "track_id"], start=pc.ORIGIN_START,
                           end=pc.ORIGIN_END, min_history_q=0)
    cells = pc.add_forward_target(cells, ["company_key", "track_id"], value_col="n_device")
    cells = pc.add_history_features(
        cells, ["company_key", "track_id"],
        ["n_device", "n_510k", "n_pma", "n_trial", "n_device_recall"],
    )
    cells = pc.add_context_features(
        cells, ["company_key", "track_id"], ["track_id"],
        ["n_device", "n_trial"],
    )
    rep["cell_panel"] = {
        "rows": int(len(cells)),
        "entities": int(cells.groupby(["company_key", "track_id"], observed=True).ngroups),
        "quarters": int(cells["quarter"].nunique()),
        "pos_rate_any_activity_4q": float(cells["y"].mean(skipna=True)),
        "n_labeled": int(cells["y"].notna().sum()),
        "n_pos": int(cells["y"].sum(skipna=True)),
        "device_events_per_cell_quarter_mean": float(cells["n_device"].mean()),
        "share_cell_quarters_with_device_event": float((cells["n_device"] > 0).mean()),
    }

    # ---- track-level panel ------------------------------------------------
    tracks = pc.build_panel(ev, ["track_id"], start=pc.ORIGIN_START, end=pc.ORIGIN_END)
    tracks = pc.add_forward_target(tracks, ["track_id"], value_col="n_device", target="growth")
    tracks = pc.add_history_features(tracks, ["track_id"], ["n_device", "n_trial", "n_510k"])
    rep["track_panel"] = {
        "rows": int(len(tracks)),
        "entities": int(tracks["track_id"].nunique()),
        "pos_rate_growth_4q": float(tracks["y"].mean(skipna=True)),
        "n_labeled": int(tracks["y"].notna().sum()),
        "n_pos": int(tracks["y"].sum(skipna=True)),
        "device_events_per_track_quarter_mean": float(tracks["n_device"].mean()),
    }

    # ---- per-kind panel sanity -------------------------------------------
    rep["cell_quarters_with_trial"] = float((cells["n_trial"] > 0).mean())
    rep["cell_quarters_with_recall"] = float((cells["n_device_recall"] > 0).mean())

    # ---- folds -----------------------------------------------------------
    folds = pc.walk_forward_folds(first_test_year=2010, last_test_year=2025)
    rep["folds"] = [
        {"year": f.test_year, "train": [str(f.train_origins[0]), str(f.train_origins[1])],
         "test": [str(f.test_origins[0]), str(f.test_origins[1])]}
        for f in folds
    ]
    rep["holdout_policy"] = pc.holdout_policy()

    # ---- metric functions actually work ----------------------------------
    d = cells.dropna(subset=["y"])
    y = d["y"].to_numpy()
    score = d["n_device_sum4"].to_numpy(dtype=float)
    rep["metric_smoke"] = {
        "ap": pc.average_precision(y, score),
        "roc_auc": pc.roc_auc(y, score),
        "precision_at_10pct": pc.precision_at_k(y, score, 0.10),
        "recall_at_10pct": pc.recall_at_k(y, score, 0.10),
        "lift_at_10pct": pc.lift_at_k(y, score, 0.10),
        "brier": pc.brier(y, score),
    }
    point, lo, hi = pc.block_bootstrap_ci(
        y, score, d["company_key"].to_numpy(), B=300
    )
    rep["bootstrap_smoke"] = {"ap": point, "lo95": lo, "hi95": hi, "B": 300}

    rep["elapsed_sec"] = round(time.time() - t0, 2)
    rep["status"] = "OK"
    pc.save_json(rep, OUT)
    print(pc.json.dumps(rep, indent=2, ensure_ascii=False, default=str)[:6000])
    print("\nwritten:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
