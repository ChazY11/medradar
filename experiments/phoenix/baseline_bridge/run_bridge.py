#!/usr/bin/env python3
"""PHOENIX-001 — baseline bridge to MedRadar's existing S-028 study.

Why this exists
---------------
The PHOENIX cell task (T-CELL) uses an "all observable cells" risk set, which has a
19.95% positive rate. The pre-existing MedRadar study S-028 uses the SAME label
definition (Traditional 510(k) or original PMA inside the forward 12 months) but a
*quiescence* risk set: the cell must have had no material event in the previous
36 months. That drives its positive rate down to ~1.02% and its APs to ~0.07.

AP is prevalence-sensitive, so the two sets of numbers are NOT comparable head to
head. This script closes that gap: it re-runs the same baseline family on the
S-028-style quiescence risk set, so the comparison against the published S-028
numbers is like-for-like.

Published S-028 reference numbers (research/studies/graph_early_signal_s028/
BASELINE_RESULTS.md §1.1/1.2, H = 4 quarters, pooled over 3 holdout windows):
    constant training prevalence  AP 0.0134
    company base rate            AP 0.0380
    track base rate              AP 0.0339
    pair base rate               AP 0.0406
    B1_history10  (logistic)     AP 0.0690
    B2_spec16     (logistic)     AP 0.0751
    B2g_hgb_spec16 (HGB)         AP 0.0567

This is an APPROXIMATE bridge, not an exact replication: the S-028 feature
definitions are implemented here from their protocol summary, not imported from
their code. Reported as such.
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

ENTS = ["company_key", "track_id"]
OUT = HERE / "results" / "baseline_bridge.json"
LAG = 90

PUBLISHED = {
    "constant_training_prevalence": 0.0134,
    "company_base_rate": 0.0380,
    "track_base_rate": 0.0339,
    "pair_base_rate": 0.0406,
    "B1_history10_logistic": 0.0690,
    "B2_spec16_logistic": 0.0751,
    "B2g_hgb_spec16": 0.0567,
}


def qidx(q: pd.Period) -> int:
    return (q.year - 2000) * 4 + (q.quarter - 1)


def build() -> pd.DataFrame:
    con = pc.connect_ro()
    ev = pc.load_events(con)
    ev = ev[ev["kind"].isin(pc.DEVICE_KINDS)]  # bridge uses device events only
    con.close()
    p = pc.build_joint_panel(ev, ENTS, kinds=pc.ALL_KINDS, lag_days=LAG)
    p = pc.add_forward_target(p, ENTS, value_col="n_device", horizon=4)
    p = pc.add_history_features(p, ENTS, ["f_n_device", "f_n_510k", "f_n_pma"])
    p = p.sort_values(ENTS + ["quarter"]).reset_index(drop=True)
    p["qidx"] = [qidx(q) for q in p["quarter"]]

    # ---- quiescence risk set: no device event in the previous 12 quarters ----
    p["_last"] = p["qidx"].where(p["n_device"] > 0)
    p["last_dev_qidx"] = p.groupby(ENTS, observed=True)["_last"].transform(lambda s: s.ffill())
    p["quarters_since_dev"] = p["qidx"] - p["last_dev_qidx"]
    p = p.drop(columns=["_last"])

    # ---- base-rate predictors (S-028 B0 family) -----------------------------
    cum = p.groupby(ENTS, observed=True)["n_device"].cumsum()
    expo = (p["exposure_q"] + 1).clip(lower=1)
    p["pair_base_rate"] = cum / expo
    comp = p.groupby("company_key", observed=True)["n_device"].transform("cumsum") / p.groupby(
        "company_key", observed=True
    )["exposure_q"].transform(lambda s: np.minimum.accumulate((s + 1).to_numpy()))
    # simpler, robust company/track base rate: cumulative events / cumulative entity-quarters
    p["_one"] = 1.0
    for name, col in (("company_base_rate", "company_key"), ("track_base_rate", "track_id")):
        ev_c = p.groupby(col, observed=True)["n_device"].transform("cumsum")
        nq_c = p.groupby(col, observed=True)["_one"].transform("cumsum")
        p[name] = ev_c / nq_c.clip(lower=1)
    p = p.drop(columns=["_one"])

    # ---- entry features (S-028 ENTRY family analogue) -----------------------
    trk = p.groupby(["track_id", "quarter"], observed=True)["n_device"].transform("sum")
    p["track_rate"] = trk
    first_in_track = p.groupby(ENTS, observed=True)["quarter"].transform("min") == p["quarter"]
    p["cell_first_quarter"] = first_in_track.astype(float)
    p["track_new_entrants_4q"] = (
        p[p["cell_first_quarter"] > 0]
        .groupby(["track_id", "quarter"], observed=True)
        .size()
        .rename("ne")
        .reset_index()
        .pipe(lambda d: p[["track_id", "quarter"]].merge(d, on=["track_id", "quarter"], how="left"))
        .groupby("track_id", observed=True)["ne"]
        .transform(lambda s: s.fillna(0).rolling(4, min_periods=1).sum())
        .to_numpy()
    )
    p["exposure_q"] = p["exposure_q"].astype(float)
    p["log_exposure"] = np.log1p(p["exposure_q"])
    return p


B1_COLS = [
    "f_n_device_sum1", "f_n_device_sum4", "f_n_device_sum8", "f_n_device_sum12",
    "f_n_device_cum", "f_n_device_mean4", "f_n_device_std8", "f_n_device_accel",
    "f_n_510k_sum4", "f_n_pma_sum4", "log_exposure",
]
B2_EXTRA = ["pair_base_rate", "track_rate", "track_new_entrants_4q", "cell_first_quarter", "company_base_rate"]


def run(p: pd.DataFrame) -> dict:
    res: dict = {"lag_scenario": "L090", "entities": ENTS, "model_family": "logistic C=1.0 L2"}
    cache: dict[int, tuple] = {}
    rows_all = []
    for fold in pc.walk_forward_folds(first_test_year=2020, last_test_year=2025):
        tr = p[(p["quarter"] >= fold.train_origins[0]) & (p["quarter"] <= fold.train_origins[1])].copy()
        te = p[(p["quarter"] >= fold.test_origins[0]) & (p["quarter"] <= fold.test_origins[1])].copy()
        for d in (tr, te):
            pass
        # risk sets. S-028 requires the cell to be *observable* (it has had at
        # least one device event by t) AND quiescent for the previous 36 months.
        # Requiring observability is the faithful reading of their protocol.
        tr_q = tr[tr["quarters_since_dev"].notna() & (tr["quarters_since_dev"] > 12)]
        te_q = te[te["quarters_since_dev"].notna() & (te["quarters_since_dev"] > 12)]
        tr_q = tr_q.dropna(subset=["y"])
        te_q = te_q.dropna(subset=["y"])
        if len(tr_q) < 200 or len(te_q) < 30 or tr_q["y"].sum() < 5 or te_q["y"].sum() < 2:
            rows_all.append({"year": fold.test_year, "status": "insufficient"})
            continue
        y_tr, y_te = tr_q["y"].to_numpy(), te_q["y"].to_numpy()
        out = {"year": fold.test_year, "n_train": int(len(tr_q)), "n_test": int(len(te_q)),
               "prev_train": float(y_tr.mean()), "prev_test": float(y_te.mean()),
               "n_pos_test": int(y_te.sum())}
        # B0 arms
        out["ap_constant"] = pc.average_precision(y_te, np.full(len(y_te), y_tr.mean()))
        for col in ("company_base_rate", "track_base_rate", "pair_base_rate"):
            out[f"ap_{col}"] = pc.average_precision(y_te, te_q[col].to_numpy())
        # learners
        for name, cols in (("B1_history11", B1_COLS), ("B2_spec16", B1_COLS + B2_EXTRA)):
            m = pc.LogisticModel(name=name).fit(tr_q[cols].to_numpy(float), y_tr)
            out[f"ap_{name}"] = pc.average_precision(y_te, m.predict_score(te_q[cols].to_numpy(float)))
        m = pc.GradientBoostingModel(name="B2g_hgb").fit(
            tr_q[B1_COLS + B2_EXTRA].to_numpy(float), y_tr
        )
        out["ap_B2g_hgb"] = pc.average_precision(
            y_te, m.predict_score(te_q[B1_COLS + B2_EXTRA].to_numpy(float))
        )
        out["status"] = "ok"
        rows_all.append(out)

    df = pd.DataFrame(rows_all)
    ok = df[df["status"] == "ok"]
    res["folds"] = rows_all
    # pooled across folds: weight by test n
    pooled = {}
    for c in [c for c in df.columns if c.startswith("ap_")]:
        if "n_test" in ok and len(ok):
            pooled[c] = float(np.average(ok[c], weights=ok["n_test"]))
    res["pooled"] = pooled
    res["pooled_prev"] = float(np.average(ok["prev_test"], weights=ok["n_test"])) if len(ok) else None
    res["n_test_total"] = int(ok["n_test"].sum()) if len(ok) else 0
    res["n_pos_total"] = int(ok["n_pos_test"].sum()) if len(ok) else 0
    res["published_s028_reference"] = PUBLISHED
    mapping = {
        "ap_constant": "constant_training_prevalence",
        "ap_company_base_rate": "company_base_rate",
        "ap_track_base_rate": "track_base_rate",
        "ap_pair_base_rate": "pair_base_rate",
        "ap_B1_history11": "B1_history10_logistic",
        "ap_B2_spec16": "B2_spec16_logistic",
        "ap_B2g_hgb": "B2g_hgb_spec16",
    }
    res["comparison_vs_published"] = {
        pub: {
            "phoenix_bridge": pooled.get(key),
            "s028_published": PUBLISHED[pub],
            "delta": (pooled.get(key) - PUBLISHED[pub]) if pooled.get(key) is not None else None,
        }
        for key, pub in mapping.items()
    }
    return res


def main() -> int:
    t0 = time.time()
    rep = {"protocol_version": pc.PROTOCOL_VERSION, "db_sha256": pc.DB_SHA256_EXPECTED,
           "command": "python experiments/phoenix/baseline_bridge/run_bridge.py"}
    p = build()
    observable = p["quarters_since_dev"].notna()
    rep["panel"] = {
        "rows_total": int(len(p)),
        "rows_observable": int(observable.sum()),
        "rows_after_quiescence": int((observable & (p["quarters_since_dev"] > 12)).sum()),
        "quiescence_years": 3,
    }
    rep.update(run(p))
    rep["elapsed_sec"] = round(time.time() - t0, 1)
    pc.save_json(rep, OUT)
    print(json_dump(rep))
    print("written:", OUT)
    return 0


def json_dump(o):
    import json
    def _d(x):
        if isinstance(x, (np.integer,)): return int(x)
        if isinstance(x, (np.floating,)): return float(x)
        if isinstance(x, np.bool_): return bool(x)
        if isinstance(x, pd.Period): return str(x)
        return str(x)
    return json.dumps(o, indent=2, ensure_ascii=False, default=_d)


if __name__ == "__main__":
    raise SystemExit(main())
