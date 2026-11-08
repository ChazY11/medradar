"""SciTrends (ddofer/Trends) — independent method-logic reimplementation and test.

WHAT THIS IS
------------
This is MY OWN reimplementation, written from the paper (Heliyon 2023, 10:e23781,
doi:10.1016/j.heliyon.2023.e23781) and from reading the authors' published notebook
`plot trend pred + CV-V2023.ipynb`. It is NOT copied code and it does NOT import
anything from the upstream repository. No third-party code is executed.

It re-runs the paper's *pipeline logic* on the authors' own released derived
feature table (`trends_v6.csv.gz`, committed to their repo), because the upstream
raw inputs (PubMed-by-Year scrapes + PatentsView patent counts) are not required
to rebuild the features that table already contains.

WHAT THIS IS NOT
----------------
It is NOT a reproduction of the paper's headline numbers. The paper's model is
CatBoost (gradient boosting with ordered target statistics and a categorical
`variable` feature). CatBoost is not installed in this audit environment and a
~100 MB wheel download was deliberately avoided, so the boosting model is a
substituted sklearn HistGradientBoostingRegressor. Numbers are therefore expected
to differ from Table 1; only the *ordering of conclusions* and the *leakage
properties* are claimed.

PAPER PROTOCOL REPRODUCED (from plot trend pred + CV-V2023.ipynb)
-----------------------------------------------------------------
  target_5[t]  = y_raw[t+5]                     (groupby('variable').shift(-5))
  if DIFF_TARGET: target_5 -= lag5  where lag5 = y_raw[t-5]   <-- see NOTE below
  rows kept:    Year > start, year_num >= 1979, topic must have > 6 rows
  features:     reviews, patent_count, patent_frac, patent_yearly_total, year_num,
                y_raw, lag5_pct_new, pct_diff_lag5, research_review_diff,
                research_review_ratio, pct_diff, review_research_ratio_2,
                review_research_diff_2, pat_div_research, y_diff, y_pct_diff
  CV:           sklearn TimeSeriesSplit(n_splits=30) over rows sorted by (Year, variable)
  baselines:    RidgeCV on [y_raw] only ("naive lag model")
                RidgeCV on all numeric features ("linear model")
  metrics:      R2, MAE, median AE, RMSE

NOTE (verified from the released data, see verify_lags.py): lag5 == y_raw[t-5].
So with DIFF_TARGET=True the delta target is y_raw[t+5] - y_raw[t-5], i.e. a
10-YEAR change (t-5 -> t+5), whereas the paper text describes a 5-year change
"relative to the present". Both variants are reported here so the ambiguity is
visible rather than hidden.

USAGE
-----
    python sci_repro.py --data-dir D:/DEPPSKK/phoenix-external/scitrends --out sci_results.json
Exit code 0 on success, non-zero on any failed stage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, median_absolute_error, r2_score
from sklearn.model_selection import TimeSeriesSplit

# Columns the paper notebook drops before modelling (Cell 3 of the CV notebook).
DROP_COLS = ["y_pct_bins", "lag1", "lag2", "lag3", "lag4"]
# Exact feature list from Cell 24 of plot trend pred + CV-V2023.ipynb.
FEATURE_COLS = [
    "reviews", "patent_count", "patent_frac", "patent_yearly_total", "year_num",
    "y_raw", "lag5_pct_new", "pct_diff_lag5", "research_review_diff",
    "research_review_ratio", "pct_diff", "review_research_ratio_2",
    "review_research_diff_2", "pat_div_research", "y_diff", "y_pct_diff",
]

RESULTS: dict = {}


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_frame(data_dir: str, target: str):
    """Rebuild the paper's modelling table. Mirrors notebook Cells 3, 6, 24.

    target:
      'level' -> y(t+5)                     (Table 1 block 1: "Y - popularity")
      'diff'  -> y(t+5) - y(t-5)            (absolute delta, DIFF_TARGET=True)
      'pct'   -> 100*(y(t+5)-y(t-5))/y(t)   (DIFF_TARGET_PCT=True; this is the target
                 whose R2/MAE/MSE reproduce Table 1 block 2, per the notebook's own
                 recorded outputs: "pct change, without categorical, with DL, 30 folds:
                 r2 0.447 MAE 48.291 median 15.114 RMSE 216.043")
    """
    src = os.path.join(data_dir, "trends_v6.csv.gz")
    df = pd.read_csv(src, parse_dates=["Year", "first", "start"])

    # Cell 3: "#### NEW! Sort by date!" — the paper DOES sort by year before CV.
    df = df.sort_values(["Year", "variable"]).reset_index(drop=True)
    df["target_5"] = df.groupby("variable")["y_raw"].shift(-5)
    df = df.loc[(df["Year"] > df["start"]) & (df["year_num"] >= 1979)]
    df = df.drop(columns=DROP_COLS, errors="ignore")
    df["lag5_pct_new"] = 100 * df["diff_lag5"].div(df["y_raw"])
    df = df.reset_index(drop=True)

    # Cell 6: drop topics with <= 6 rows after filtering.
    df = df[df.groupby("variable")["variable"].transform("count") > 6]
    df = df.reset_index(drop=True)

    if target == "diff":
        # Cell 6 DIFF_TARGET branch. lag5 = y_raw[t-5] (verified).
        df["target_5"] = df["target_5"].sub(df["lag5"])
    elif target == "pct":
        # Cell 6 DIFF_TARGET_PCT branch.
        df["target_5"] = (100 * df["target_5"].sub(df["lag5"]).div(df["y_raw"])).round(4)
    elif target != "level":
        raise ValueError(target)
    # Upstream ran with pd.set_option('mode.use_inf_as_na', True): the pct target
    # divides by y_raw, which is 0 for topics with no publications that year.
    df["target_5"] = df["target_5"].replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=["target_5"]).reset_index(drop=True)

    keep = ["variable", "Year"] + FEATURE_COLS + ["target_5", "lag5"]
    keep = list(dict.fromkeys(keep))  # FEATURE_COLS already contains year_num
    df = df[keep]
    assert not df.columns.duplicated().any(), df.columns[df.columns.duplicated()].tolist()
    return df


def metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {
        "n": int(len(y_true)),
        "r2": round(float(r2_score(y_true, y_pred)), 6),
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "median_ae": round(float(median_absolute_error(y_true, y_pred)), 4),
        "rmse": round(float(np.sqrt(np.mean((y_true - y_pred) ** 2))), 4),
    }


def make_model(kind: str, n_rows: int):
    if kind == "ridge_lag":       # "naive lag model": RidgeCV on y_raw alone
        return RidgeCV(alphas=np.logspace(-3, 3, 25))
    if kind == "ridge_all":
        return RidgeCV(alphas=np.logspace(-3, 3, 25))
    if kind == "hist_gbm":        # stand-in for CatBoostRegressor
        return HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.1, max_leaf_nodes=31,
            min_samples_leaf=20, l2_regularization=0.0, random_state=42,
        )
    raise ValueError(kind)


def run_cv(df: pd.DataFrame, feature_cols: list[str], model_kind: str,
           n_splits: int, order: str) -> dict:
    """TimeSeriesSplit over rows in file order ('year_sorted') or topic-block order."""
    if order == "year_sorted":
        work = df.sort_values(["Year", "variable"]).reset_index(drop=True)
    elif order == "topic_block":     # what happens if you forget the Year sort
        work = df.sort_values(["variable", "Year"]).reset_index(drop=True)
    else:
        raise ValueError(order)

    num = work[feature_cols].select_dtypes(include=[np.number]).copy()
    # The paper's notebooks ran with pd.set_option('mode.use_inf_as_na', True),
    # which pandas 3.x removed. lag5_pct_new = 100*diff_lag5/y_raw can divide by
    # zero, so inf must be treated as missing explicitly.
    num = num.replace([np.inf, -np.inf], np.nan)
    y = work["target_5"].to_numpy(dtype=float)

    if model_kind == "ridge_lag":
        X = num[["y_raw"]].copy()
    else:
        X = num.copy()
    if model_kind in ("ridge_all", "ridge_lag"):
        X = X.fillna(X.mean())

    preds = np.full(len(work), np.nan)
    tscv = TimeSeriesSplit(n_splits=n_splits)
    for fit_idx, test_idx in tscv.split(X):
        model = make_model(model_kind, len(work))
        model.fit(X.iloc[fit_idx], y[fit_idx])
        preds[test_idx] = model.predict(X.iloc[test_idx])

    mask = ~np.isnan(preds)
    out = metrics(y[mask], preds[mask])
    out["test_years"] = [int(work.loc[mask, "year_num"].min()), int(work.loc[mask, "year_num"].max())]
    out["n_total_rows"] = int(len(work))
    return out


def persistence_baseline(df: pd.DataFrame, target: str) -> dict:
    """The honest 'nothing changes' forecasts, on the same rows as the models.

    level: predict y(t+5) = y_raw(t)                       (last observed value)
    diff : predict 0, which here means y(t+5) = y(t-5)     (10-year persistence)
           and also the 5-year persistence expectation y(t)-y(t-5)
    pct  : predict 0, meaning no change from the t-5 anchor (i.e. y(t+5)=y(t-5))
    """
    y = df["target_5"].to_numpy(dtype=float)
    if target == "level":
        return {"level_persistence_(y_t)": metrics(y, df["y_raw"].to_numpy(dtype=float))}
    if target == "diff":
        five = (df["y_raw"] - df["lag5"]).to_numpy(dtype=float)
        return {"delta_zero_change": metrics(y, np.zeros_like(y)),
                "delta_persistence_5y_(y_t-y_tm5)": metrics(y, five)}
    if target == "pct":
        # pct target = 100*(y(t+5)-y(t-5))/y(t); "no change" => 0
        return {"pct_zero_change": metrics(y, np.zeros_like(y))}
    raise ValueError(target)


def leakage_probe(df: pd.DataFrame, n_splits: int) -> dict:
    """Positive control: if the future value leaked into the features, R2 -> 1.

    We append y(t+5) itself as a feature and fit an ordinary least-squares model
    (NOT a binned tree — histogram binning caps a tree at <=255 quantile bins per
    feature, which alone would keep R2 below 1 and make the control ambiguous).
    A sound harness must report R2 ~ 1.0 here; the real feature runs above can then
    be read as "no such leak present".
    """
    from sklearn.linear_model import LinearRegression

    work = df.sort_values(["Year", "variable"]).reset_index(drop=True)
    raw = pd.read_csv(os.path.join(RESULTS["data_dir"], "trends_v6.csv.gz"),
                      parse_dates=["Year", "first", "start"])
    raw = raw.sort_values(["Year", "variable"]).reset_index(drop=True)
    raw["future"] = raw.groupby("variable")["y_raw"].shift(-5)
    fut = (raw.set_index(["Year", "variable"])["future"]
           .reindex(pd.MultiIndex.from_frame(work[["Year", "variable"]])).to_numpy())
    ok = ~np.isnan(fut)
    work = work.loc[ok].reset_index(drop=True)
    y = fut[ok]

    X = work[["y_raw"]].copy()
    X["y_future_leak"] = y
    preds = np.full(len(X), np.nan)
    for fit_idx, test_idx in TimeSeriesSplit(n_splits=n_splits).split(X):
        m = LinearRegression().fit(X.iloc[fit_idx], y[fit_idx])
        preds[test_idx] = m.predict(X.iloc[test_idx])
    mask = ~np.isnan(preds)
    out = metrics(y[mask], preds[mask])
    out["control"] = "y(t+5) appended as a feature"
    out["expected"] = "R2 ~ 1.0 (proves the harness would detect real leakage)"
    out["detected"] = bool(out["r2"] > 0.999)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", default="sci_results.json")
    ap.add_argument("--splits", type=int, default=30)
    args = ap.parse_args()

    RESULTS["data_dir"] = args.data_dir
    t0 = time.time()

    src = os.path.join(args.data_dir, "trends_v6.csv.gz")
    if not os.path.exists(src):
        print(f"FAIL: missing {src}", file=sys.stderr)
        return 2

    RESULTS["input"] = {
        "file": "trends_v6.csv.gz",
        "sha256": sha256(src),
        "bytes": os.path.getsize(src),
        "source_repo": "https://github.com/ddofer/Trends",
        "raw_inputs_used": False,
    }
    RESULTS["environment"] = {
        "python": sys.version.split()[0],
        "pandas": pd.__version__, "numpy": np.__version__,
        "sklearn": __import__("sklearn").__version__,
        "catboost": "NOT INSTALLED (substituted HistGradientBoostingRegressor)",
        "sentence_transformers": "NOT INSTALLED (embedding-augmented variant not run)",
    }

    stages: list[dict] = []
    RESULTS["frames"] = {}
    RESULTS["persistence"] = {}

    # Three targets, matching the three table blocks / code switches in the notebooks.
    for target, label in [("level", "Y - popularity y(t+5)"),
                          ("diff", "dY absolute y(t+5)-y(t-5)  [DIFF_TARGET=True]"),
                          ("pct", "dY percent 100*(y(t+5)-y(t-5))/y(t)  [DIFF_TARGET_PCT=True]")]:
        frame = build_frame(args.data_dir, target)
        RESULTS["frames"][target] = {
            "rows": int(len(frame)), "topics": int(frame.variable.nunique()),
            "years": [int(frame.year_num.min()), int(frame.year_num.max())],
        }
        RESULTS["persistence"][target] = persistence_baseline(frame, target)
        for kind in ["ridge_lag", "ridge_all", "hist_gbm"]:
            stages.append({"target": label, "target_key": target, "model": kind,
                           "result": run_cv(frame, FEATURE_COLS, kind, args.splits,
                                            "year_sorted")})

    # ---- ablation: forgetting the Year sort (topic-block fold order) ----
    pct_frame = build_frame(args.data_dir, "pct")
    abl = run_cv(pct_frame, FEATURE_COLS, "hist_gbm", args.splits, "topic_block")
    RESULTS["ablation_topic_block_order"] = {
        "target": "pct", "model": "hist_gbm", "order": "topic_block",
        "result": abl,
        "interpretation": ("folds become TOPIC groups, not time windows; the reported "
                           "metric is no longer a temporal generalisation estimate. "
                           "Compare with the year_sorted run of the same target/model."),
    }

    RESULTS["leakage_positive_control"] = leakage_probe(build_frame(args.data_dir, "level"),
                                                        args.splits)
    RESULTS["stages"] = stages
    RESULTS["elapsed_s"] = round(time.time() - t0, 1)
    RESULTS["status"] = "ok"

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, indent=2)

    print(json.dumps({k: RESULTS[k] for k in
                      ["frames", "persistence",
                       "ablation_topic_block_order", "leakage_positive_control",
                       "elapsed_s", "status"]}, indent=2))
    print("\n--- per-stage metrics ---")
    for s in stages:
        r = s["result"]
        print(f"{s['target_key']:5s} {s['model']:10s} R2={r['r2']:+.4f} "
              f"MAE={r['mae']:9.3f} medAE={r['median_ae']:8.3f} RMSE={r['rmse']:10.3f} n={r['n']}")
    print(f"\nwrote {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        RESULTS["status"] = "failed"
        sys.exit(1)
