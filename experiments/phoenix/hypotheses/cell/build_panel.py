#!/usr/bin/env python3
"""PHOENIX-001 / T-CELL step 1: build and cache the joint cell panel.

For each lag scenario L000 / L090 / L180:
  * load the frozen event table read-only,
  * build the joint (label clock + feature clock) company x track panel,
  * attach the frozen 4-quarter forward label (`any_activity`),
  * attach own-history features on the `f_n_*` counts,
  * attach enclosing-track context features (H4 arm) and
  * the company x track bipartite network block (B7 / H10 arm),
  * cache the result as a pickle (pyarrow is not installed, so no parquet).

Usage
    python build_panel.py                 # all three lags
    python build_panel.py --lag 90        # one lag
    python build_panel.py --force         # rebuild even if cached
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

# The frozen facts from experiments/phoenix/reports/03_harness_smoke.json.
# Origins <= 2024Q2 are exactly the origins that report could label, because the
# harness trims the joint panel before the forward target is attached.
FROZEN_LAST_LABELED_ORIGIN = pd.Period("2024Q2", freq="Q")
FROZEN_LABELED_ROWS = 62732
FROZEN_N_POS = 12517
FROZEN_PREVALENCE = 0.19953133966715553


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lag", type=int, default=None, choices=[0, 90, 180])
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    lags = [args.lag] if args.lag is not None else list(cc.LAGS)

    t_all = time.time()
    prov = cc.provenance(command="python build_panel.py" +
                         (f" --lag {args.lag}" if args.lag is not None else ""))
    cc.log(f"db sha256 verified: {prov['db_sha256']}")
    cc.log(f"protocol={prov['protocol_version']} seed={prov['seed']} lags={lags}")

    con = pc.connect_ro()
    try:
        events = pc.load_events(con)
        con.close()
    except Exception:
        con.close()
        raise
    cc.log(f"events loaded (company_key & track_id present): {len(events)}")
    by_kind = events["kind"].value_counts().to_dict()
    cc.log(f"events by kind: {by_kind}")

    meta = {
        "provenance": prov,
        "events_loaded": int(len(events)),
        "events_by_kind": {k: int(v) for k, v in by_kind.items()},
        "panels": {},
    }
    if cc.meta_path().exists():
        try:
            old = pc.json.loads(cc.meta_path().read_text(encoding="utf-8"))
            if old.get("provenance", {}).get("db_sha256") == prov["db_sha256"]:
                meta["panels"] = old.get("panels", {})
        except Exception:  # noqa: BLE001
            pass

    for lag in lags:
        tag = cc.LAG_SCENARIO[lag]
        out = cc.cache_path(lag)
        if out.exists() and not args.force:
            cc.log(f"[{tag}] cache exists, skip ({out.name})")
            continue
        cc.log(f"[{tag}] building panel ...")
        t0 = time.time()
        panel = cc.build_cell_panel(lag, events=events)
        p = cc.save_panel(panel, lag)
        fs = cc.feature_sets(panel)
        d = panel.dropna(subset=["y"])
        q1 = d[d["q1_only"]]

        # ---- frozen-numbers reproducibility check ----------------------
        # The task definition is unchanged; only the (harness) order of "trim to
        # origin_end" vs "attach the forward label" differs. Restricting this
        # panel to the origins that 03_harness_smoke.json could label must
        # reproduce its numbers exactly, else something really did change.
        froz = d[d["quarter"] <= FROZEN_LAST_LABELED_ORIGIN]
        froz_facts = {
            "last_origin_included": str(FROZEN_LAST_LABELED_ORIGIN),
            "labeled_rows": int(len(froz)),
            "n_pos": int(froz["y"].sum()),
            "prevalence": round(float(froz["y"].mean()), 12),
            "expected_labeled_rows": FROZEN_LABELED_ROWS,
            "expected_n_pos": FROZEN_N_POS,
            "expected_prevalence": FROZEN_PREVALENCE,
        }
        froz_facts["matches_03_harness_smoke"] = bool(
            froz_facts["labeled_rows"] == FROZEN_LABELED_ROWS
            and froz_facts["n_pos"] == FROZEN_N_POS
            and abs(froz_facts["prevalence"] - FROZEN_PREVALENCE) < 1e-9
        )
        if lag == cc.HEADLINE_LAG and not froz_facts["matches_03_harness_smoke"]:
            cc.log(f"[{tag}] WARNING: frozen 03_harness_smoke numbers NOT reproduced")
        cc.log(f"[{tag}] frozen-subset check (origins <= {FROZEN_LAST_LABELED_ORIGIN}): "
               f"n={froz_facts['labeled_rows']} n_pos={froz_facts['n_pos']} "
               f"prev={froz_facts['prevalence']:.6f} -> "
               f"{'MATCH' if froz_facts['matches_03_harness_smoke'] else 'MISMATCH'}")

        facts = {
            "rows": int(len(panel)),
            "cols": int(panel.shape[1]),
            "labeled_rows": int(len(d)),
            "n_pos": int(d["y"].sum()),
            "prevalence": float(d["y"].mean()),
            "n_cells": int(panel.groupby(cc.ENT, observed=True).ngroups),
            "n_companies": int(panel["company_key"].nunique()),
            "n_tracks": int(panel["track_id"].nunique()),
            "origin_first": str(panel["quarter"].min()),
            "origin_last": str(panel["quarter"].max()),
            "unlabeled_rows": int(panel["y"].isna().sum()),
            "q1_only_rows": int(len(q1)),
            "q1_only_n_pos": int(q1["y"].sum()),
            "q1_only_prevalence": float(q1["y"].mean()),
            "holdout_rows": int(panel["holdout"].sum()),
            "feature_set_sizes": {k: len(v) for k, v in fs.items()},
            "n_net_features": len([c for c in panel.columns if c.startswith("net_")]),
            "n_ctx_features": len([c for c in panel.columns if c.startswith("ctx_")]),
            "share_rows_exposure_lt_8": float((panel["exposure_q"] < 8).mean()),
            "f_n_8k_nonzero_rows": int((panel.get("f_n_8k_catalyst", pd.Series(0, index=panel.index)) > 0).sum()),
            "frozen_subset_check": froz_facts,
            "cache_path": str(p),
            "cache_bytes": int(p.stat().st_size),
            "build_elapsed_sec": round(time.time() - t0, 2),
        }
        meta["panels"][tag] = facts
        cc.log(f"[{tag}] rows={facts['rows']} labeled={facts['labeled_rows']} "
               f"prev={facts['prevalence']:.4f} cells={facts['n_cells']} "
               f"net={facts['n_net_features']} ctx={facts['n_ctx_features']} "
               f"features={facts['feature_set_sizes']}")
        cc.log(f"[{tag}] cached -> {p.name} ({facts['cache_bytes']/1e6:.1f} MB) "
               f"in {facts['build_elapsed_sec']}s")
        del panel
    meta["elapsed_sec"] = round(time.time() - t_all, 2)
    pc.save_json(meta, cc.meta_path())
    any_bad = any(
        not v.get("frozen_subset_check", {}).get("matches_03_harness_smoke", False)
        for v in meta["panels"].values()
    )
    cc.log(f"meta written -> {cc.meta_path()}  total {meta['elapsed_sec']}s  "
           f"frozen_facts_reproduced={not any_bad}")
    return 0 if not any_bad else 2


if __name__ == "__main__":
    raise SystemExit(main())
