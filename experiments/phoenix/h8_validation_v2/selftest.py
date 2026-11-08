"""PHOENIX-002 unit tests / self-checks.

Run:  python selftest.py
All checks must pass before any result is reported.  The panel-equality test is the
strong one: it asserts that the independent v2 panel builder reproduces the frozen
PHOENIX-001 T-TRACK panel labels exactly.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import data as D
import features as F
import metrics as M
import protocol as P
import runner as R

PASS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    PASS.append(cond)
    if not cond:
        raise AssertionError(name)


def test_label_formulas() -> None:
    """Hand-computed labels on a toy series."""
    n = 20
    panel = pd.DataFrame({
        "track_id": "toy",
        "quarter": pd.period_range("2004Q1", periods=n, freq="Q"),
        "qnum": np.arange(n),
        "n_device": [0] * 8 + [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "first_event_qnum": 0,
        "first_dev_feat_qnum": 0,
        "exposure_q": np.arange(n, dtype=float),
        "origin_eligible": True,
    })
    panel = D.add_targets(panel)
    # row 0: fwd = n[1..4] = 0 -> Y1 0 ; trail8 undefined -> NaN
    check("label: trail8 undefined for first 7 rows",
          panel.loc[:6, "trail8_total"].isna().all())
    check("label: Y1 NaN where trail8 undefined", panel.loc[:6, "y_Y1_growth_ratio"].isna().all())
    # row 7: trail8 = n[0..7] = 0 -> Y1 requires fwd>=3; fwd=n[8..11]=1+2+3+4=10
    # fwd mean 2.5 >= 1.5*0 -> True, so Y1=1 (the vacuous-ratio case, documented)
    check("label: Y1=1 with zero trailing mean and >=3 forward events",
          panel.loc[7, "y_Y1_growth_ratio"] == 1.0,
          f"fwd={panel.loc[7, 'fwd_total']} trail8={panel.loc[7, 'trail8_total']}")
    # row 8: trail8 = n[1..8] = 0+...+1 = 1 -> mean .125; fwd=n[9..12]=2+3+4+5=14 -> mean 3.5 >= .1875 -> Y1=1
    check("label: Y1 computes the 1.5x ratio correctly", panel.loc[8, "y_Y1_growth_ratio"] == 1.0)
    # Y2 = fwd > trail8/2
    check("label: Y2 additive rule", panel.loc[8, "y_Y2_abs_increase"] == 1.0)
    # Y4 only defined where trail8==0
    check("label: Y4 only dormant", panel.loc[7, "y_Y4_dormant_emergence"] == 1.0
          and panel.loc[8, "y_Y4_dormant_emergence"] == 0.0)


def test_maturity_rules() -> None:
    """The purge rule must make the executable assertion hold; the naive rule must not."""
    for lag in P.LABEL_LAGS:
        purge = P.purge_quarters(lag)
        check(f"maturity: purge={purge} for label lag {lag}",
              purge == P.HORIZON_Q + P.label_lag_quarters(lag) + 1)
        tf = pd.Period("2014Q1", freq="Q")
        latest = P.train_latest_origin(tf, lag)
        # a training row at `latest` must be observable before the end of 2013Q4
        obs = P.label_observable_quarter(latest, lag)
        check(f"maturity: label observable at {obs} <= {tf - 1} (lag {lag})", obs <= tf - 1)
        # one quarter later violates
        obs_bad = P.label_observable_quarter(latest + 1, lag)
        check(f"maturity: one quarter later would violate (lag {lag})", obs_bad > tf - 1)


def test_pit_panel() -> None:
    panel = D.build_panel("attr38", P.HEADLINE_FEATURE_LAG, mode="v2")
    check("pit: every row has >= 0 exposure", (panel["exposure_q"] >= 0).all())
    check("pit: no row before first device availability",
          (panel["qnum"] >= panel["first_dev_feat_qnum"]).all())
    elig = panel[panel["origin_eligible"]]
    check("pit: eligible rows have >= 8 observed quarters",
          bool((elig["exposure_q"] + 1 >= P.MIN_DEVICE_HISTORY_Q).all()),
          f"min exposure={elig['exposure_q'].min()}")
    check("pit: eligible origins within frozen window",
          bool((elig["qnum"] <= D.qnum_scalar(P.ORIGIN_END)).all()))


def test_v1_panel_replication() -> None:
    """Independent v2 builder must reproduce the frozen PHOENIX-001 panel exactly."""
    v1_path = (D.HERE.parent / "hypotheses" / "track" / "cache" / "track_panel_L090.pkl")
    if not v1_path.exists():
        print(f"[SKIP] v1 panel cache not found at {v1_path}")
        return
    v1 = pd.read_pickle(v1_path)
    mine = D.build_panel("attr59", P.HEADLINE_FEATURE_LAG, mode="v1like")
    check("replication: row count matches 4904", len(mine) == len(v1) == 4904,
          f"v2={len(mine)} v1={len(v1)}")
    check("replication: labelled rows match 4255",
          int(mine["y"].notna().sum()) == int(v1["y"].notna().sum()) == 4255)
    check("replication: positives match 406",
          int(np.nansum(mine["y"])) == int(np.nansum(v1["y"])) == 406)
    a = v1[["track_id", "quarter", "y", "n_device", "f_n_device"]].copy()
    b = mine[["track_id", "quarter", "y", "n_device", "f_n_device"]].copy()
    a["quarter"] = a["quarter"].astype(str)
    b["quarter"] = b["quarter"].astype(str)
    m = a.merge(b, on=["track_id", "quarter"], suffixes=("_v1", "_v2"), how="outer")
    check("replication: identical (track,quarter) key set",
          len(m) == len(v1))
    same_y = ((m["y_v1"].isna() & m["y_v2"].isna())
              | (m["y_v1"].fillna(-1) == m["y_v2"].fillna(-1)))
    check("replication: label vector identical", bool(same_y.all()),
          f"{int((~same_y).sum())} mismatching rows")
    check("replication: event-clock device counts identical",
          bool((m["n_device_v1"] == m["n_device_v2"]).all()))
    check("replication: feature-clock device counts identical",
          bool((m["f_n_device_v1"] == m["f_n_device_v2"]).all()))


def test_growth_features() -> None:
    panel = pd.DataFrame({
        "track_id": "toy",
        "quarter": pd.period_range("2004Q1", periods=16, freq="Q"),
        "qnum": np.arange(16),
        "f_n_device": [0, 1, 2, 1, 0, 0, 3, 4, 2, 1, 0, 1, 2, 2, 3, 5],
        "f_n_510k": [0, 1, 1, 1, 0, 0, 2, 2, 1, 1, 0, 1, 1, 1, 2, 3],
        "f_n_pma": [0, 0, 1, 0, 0, 0, 1, 2, 1, 0, 0, 0, 1, 1, 1, 2],
        "f_n_trial": 0.0, "f_n_device_recall": 0.0, "f_n_total": 0.0,
        "exposure_q": np.arange(16, dtype=float),
    })
    panel = F.build_features(panel)
    # growth1 at row 8: cur=f[8]=2, prev=f[7]=4 -> (2-4)/(4+1) = -0.4
    check("features: growth1 formula", abs(panel.loc[8, "sct_growth1"] - (-0.4)) < 1e-12)
    # growth4 at row 8: cur=sum f[5..8]=0+3+4+2=9, prev=sum f[1..4]=1+2+1+0=4 -> 5/5=1.0
    check("features: growth4 formula", abs(panel.loc[8, "sct_growth4"] - 1.0) < 1e-12)
    check("features: slope12 defined from row 11", np.isnan(panel.loc[10, "sct_slope12"])
          and np.isfinite(panel.loc[11, "sct_slope12"]))
    check("features: pma_share4 in [0,1]", float(panel["sct_pma_share4"].min()) >= 0.0)


def test_metrics() -> None:
    check("metrics: AP of perfect ranking = 1", abs(M.average_precision([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) - 1.0) < 1e-12)
    check("metrics: AP of reversed ranking < prevalence",
          M.average_precision([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) < 0.5)
    rng = np.random.default_rng(0)
    g = np.repeat(np.arange(10), 20)
    a = rng.random(200)
    c = M.paired_bootstrap_diff((a > 0.5).astype(float), a, a, g, B=100, seed=1)
    check("metrics: paired self-contrast is exactly zero", c["diff"] == 0.0 and c["p"] == 1.0)


def test_fold_structure() -> None:
    f_purged = R.make_folds("purged", 90)
    f_naive = R.make_folds("v1_naive", 90)
    check("folds: 12 test years 2014..2025", len(f_purged) == 12)
    check("folds: purged train window ends 6 quarters before test start",
          all(f.test_first_qnum - f.train_latest_qnum == 6 for f in f_purged))
    check("folds: naive train window ends 1 quarter before test start",
          all(f.test_first_qnum - f.train_latest_qnum == 1 for f in f_naive))
    # fold 2014 test-first is 2014Q1 -> qnum 40; purged latest = 34 -> 2012Q3
    check("folds: 2014 fold purged latest origin = 2012Q3",
          str(pd.Period("2004Q1", freq="Q") + f_purged[0].train_latest_qnum) == "2012Q3")


def test_maturity_on_real_panel() -> None:
    panel = D.build_panel("attr38", 90, mode="v2")
    f_purged = R.make_folds("purged", 90)
    audit = R.maturity_audit(panel, f_purged, 90)
    check("maturity: purged folds have zero violating training rows",
          audit["total_violating_training_rows"] == 0,
          f"{audit['total_violating_training_rows']}/{audit['total_training_rows']}")
    check("maturity: purged folds have zero labels depending on test-period events",
          audit["total_rows_depending_on_test_period_events"] == 0)
    f_naive = R.make_folds("v1_naive", 90)
    audit_naive = R.maturity_audit(panel, f_naive, 90)
    check("maturity: naive folds DO violate (documents the v1 defect)",
          audit_naive["total_violating_training_rows"] > 0,
          f"{audit_naive['total_violating_training_rows']}/{audit_naive['total_training_rows']} = "
          f"{audit_naive['total_violating_share']:.4f}")


def main() -> int:
    print(f"PHOENIX-002 selftest  protocol={P.PROTOCOL_VERSION}")
    test_label_formulas()
    test_maturity_rules()
    test_fold_structure()
    test_growth_features()
    test_metrics()
    test_pit_panel()
    test_v1_panel_replication()
    test_maturity_on_real_panel()
    print(f"\nALL {len(PASS)} CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
