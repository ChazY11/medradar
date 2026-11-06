#!/usr/bin/env python3
"""Run a reviewed subset of SciTrends' official modelling notebook.

The cell allowlist deliberately excludes downloads, SHAP, future forecasts and all
file-writing cells. The no-DL configuration is an author-provided branch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import sklearn
from sklearn import metrics
from sklearn.model_selection import TimeSeriesSplit


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regression_metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {
        "rows": int(len(y_true)),
        "r2": float(metrics.r2_score(y_true, y_pred)),
        "mae": float(metrics.mean_absolute_error(y_true, y_pred)),
        "median_absolute_error": float(metrics.median_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(metrics.mean_squared_error(y_true, y_pred))),
        "explained_variance": float(metrics.explained_variance_score(y_true, y_pred)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_repo", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.source_repo.resolve()
    output_path = args.output.resolve()
    notebook_path = repo / "plot trend pred + CV-V2023.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    allowlist = [1, 2, 3, 5, 6, 8, 30, 33, 34, 35, 36, 39, 40, 44, 45]
    namespace = {"display": lambda *a, **k: None, "__name__": "__main__"}
    os.chdir(repo)
    observed = {}
    final_predictions = None
    for index in allowlist:
        cell = notebook["cells"][index]
        assert cell["cell_type"] == "code"
        source = "".join(cell.get("source", []))
        if index == 2:
            old = "GET_DL_EMBEDS = True#False"
            assert old in source
            source = source.replace(old, "GET_DL_EMBEDS = False# reproduction: no model download")
        source = "\n".join(line for line in source.splitlines()
                           if not line.lstrip().startswith(("%", "!")))
        source = source.replace("np.NaN", "np.nan")  # NumPy 2.x compatibility only.
        exec(compile(source, f"{notebook_path.name}:cell-{index}", "exec"), namespace)
        names = {33: "ridge_y_raw", 34: "ridge_full_mean_imputed",
                 35: "ridge_complete_columns", 36: "catboost_all_features"}
        if index in names:
            observed[names[index]] = regression_metrics(namespace["y_true_base"], namespace["y_pred_base"])
        if index == 36:
            final_predictions = (np.asarray(namespace["y_true_base"], dtype=float),
                                 np.asarray(namespace["y_pred_base"], dtype=float))
        if index in (44, 45):
            observed[f"cell_{index}_baseline"] = regression_metrics(namespace["y_true_base"], namespace["y_pred_base"])

    X = namespace["X"]
    splits = []
    for fold, (train, test) in enumerate(TimeSeriesSplit(namespace["NUM_CV_FOLDS"]).split(X), start=1):
        train_years = set(X.iloc[train]["year_num"].unique())
        test_years = X.iloc[test]["year_num"]
        overlap = sorted(int(year) for year in train_years & set(test_years.unique()))
        splits.append({
            "fold": fold,
            "train_rows": int(len(train)), "test_rows": int(len(test)),
            "shared_years": overlap,
            "test_rows_in_year_already_trained": int(test_years.isin(train_years).sum()),
        })
    result_mask = namespace["df_lagged"]["preds"].notna()
    result_rows = namespace["df_lagged"].loc[result_mask]
    assert final_predictions is not None
    y_true, y_pred = final_predictions
    binary = {
        "true_decline_rate": float(np.mean(y_true < 0)),
        "predicted_decline_rate": float(np.mean(y_pred < 0)),
        "accuracy": float(metrics.accuracy_score(y_true < 0, y_pred < 0)),
        "f1": float(metrics.f1_score(y_true < 0, y_pred < 0)),
    }
    payload = {
        "status": "completed_author_no_dl_core",
        "source_repository": "https://github.com/ddofer/Trends",
        "source_notebook": notebook_path.name,
        "source_commit": os.popen("git rev-parse HEAD").read().strip(),
        "notebook_sha256": sha256(notebook_path),
        "data_sha256": {name: sha256(repo / name) for name in ("trends_v6.csv.gz",)},
        "cell_allowlist": allowlist,
        "deviations": [
            "GET_DL_EMBEDS=False, an existing author configuration; no SentenceTransformer download or SHAP was run.",
            "Jupyter magics and display calls were removed; no forecasting or file-writing cells were executed.",
            "np.NaN was changed to np.nan for NumPy 2.x compatibility; model semantics were unchanged.",
            "CatBoost 1.2.10 was pinned by PHOENIX because upstream has no dependency lock.",
        ],
        "configuration": {key: namespace[key] for key in
                          ("FILTER_GROUP_SIZES", "DIFF_TARGET", "DIFF_TARGET_PCT", "NUM_CV_FOLDS", "GET_DL_EMBEDS")},
        "dataset": {
            "input_rows": int(len(namespace["df_targets"])),
            "model_X_rows": int(len(X)), "topics": int(X["variable"].nunique()),
            "prediction_years": sorted(int(v) for v in X["year_num"].unique()),
            "evaluated_rows": int(len(result_rows)), "evaluated_topics": int(result_rows["variable"].nunique()),
        },
        "metrics": observed,
        "final_model_decline_classification": binary,
        "temporal_audit": {
            "method": "Upstream row-wise TimeSeriesSplit on rows sorted by Year then variable.",
            "folds_with_shared_train_test_years": sum(bool(row["shared_years"]) for row in splits),
            "folds": splits,
            "warning": "Row-wise splitting can place different topics from the same year on both sides; it is not a clean public-time cutoff.",
            "full_data_preprocessing_warning": "Cell 34 imputes with means computed over all X before CV; this is a separate leakage channel.",
        },
        "versions": {"python": sys.version, "pandas": pd.__version__, "numpy": np.__version__, "sklearn": sklearn.__version__},
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "dataset": payload["dataset"],
                      "metrics": observed, "binary": binary,
                      "folds_with_shared_train_test_years": payload["temporal_audit"]["folds_with_shared_train_test_years"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
