"""PHOENIX-002 model arms (baselines + candidate).

Deliberately simple and small: the point of the round is validation, not model search.
Every arm is fitted on the fold's training rows only and scored out-of-fold.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import protocol as P


class ConstModel:
    def __init__(self, value: float):
        self.value = float(value)

    def predict(self, X):
        return np.full(len(X), self.value, dtype=float)


class LogitModel:
    def __init__(self, C: float = 1.0, max_iter: int = 2000):
        self.C = C
        self.max_iter = max_iter

    def fit_predict(self, Xtr, ytr, Xte):
        if len(np.unique(ytr)) < 2:
            return np.full(len(Xte), float(np.mean(ytr)))
        pipe = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(C=self.C, max_iter=self.max_iter, solver="lbfgs"),
        )
        pipe.fit(np.asarray(Xtr, dtype=float), np.asarray(ytr, dtype=float))
        return pipe.predict_proba(np.asarray(Xte, dtype=float))[:, 1]


class HGBModel:
    """Lightweight non-linear reference (deliberately small: no tuning)."""

    def __init__(self, max_iter: int = 150, max_depth: int = 4):
        self.max_iter = max_iter
        self.max_depth = max_depth

    def fit_predict(self, Xtr, ytr, Xte):
        if len(np.unique(ytr)) < 2:
            return np.full(len(Xte), float(np.mean(ytr)))
        m = HistGradientBoostingClassifier(
            max_iter=self.max_iter, max_depth=self.max_depth, learning_rate=0.06,
            min_samples_leaf=40, l2_regularization=1.0, random_state=P.SEED,
        )
        m.fit(np.asarray(Xtr, dtype=float), np.asarray(ytr, dtype=float))
        return m.predict_proba(np.asarray(Xte, dtype=float))[:, 1]


def fit_arm(arm: str, Xtr: np.ndarray, ytr: np.ndarray, Xte: np.ndarray,
            feature_names: list[str] | None = None) -> tuple[np.ndarray, dict]:
    """Fit one arm on a fold and return out-of-fold scores plus a compact fit record."""
    ytr = np.asarray(ytr, dtype=float)
    if arm == "M0_prevalence":
        return np.full(len(Xte), float(np.mean(ytr))), {"kind": "constant",
                                                        "train_prevalence": float(np.mean(ytr))}
    # drop features that are useless in this fold (all-missing or zero-variance)
    Xtr = np.asarray(Xtr, dtype=float)
    Xte = np.asarray(Xte, dtype=float)
    keep = []
    for j in range(Xtr.shape[1]):
        col = Xtr[:, j]
        finite = np.isfinite(col)
        if finite.sum() < 5:
            continue
        if np.nanstd(col[finite]) == 0:
            continue
        keep.append(j)
    if not keep:
        return np.full(len(Xte), float(np.mean(ytr))), {"kind": "fallback_const"}
    Xtr, Xte = Xtr[:, keep], Xte[:, keep]
    used = [feature_names[j] for j in keep] if feature_names else keep
    if arm == "M6_hgb":
        scores = HGBModel().fit_predict(Xtr, ytr, Xte)
        kind = "hist_gradient_boosting"
    elif arm == "M5_full_regularised":
        scores = LogitModel(C=0.5).fit_predict(Xtr, ytr, Xte)
        kind = "logit_L2_C0.5"
    else:
        scores = LogitModel(C=1.0).fit_predict(Xtr, ytr, Xte)
        kind = "logit_L2_C1"
    return np.asarray(scores, dtype=float), {"kind": kind, "n_features_used": len(used),
                                             "features_used": used}
