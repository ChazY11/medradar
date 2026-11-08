"""PHOENIX-002 feature builders.

Definitions are copied from the frozen PHOENIX-001 implementation (same windows, same
denominators) so that the replication arm is comparable and the H8 arm is not silently
redesigned.  Everything uses the FEATURE clock columns (`f_n_*`) only; no label-clock
column is ever read here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import protocol as P

HISTORY_COLS_FULL = ("f_n_510k", "f_n_pma", "f_n_trial", "f_n_device_recall",
                     "f_n_device", "f_n_total")
WINDOWS = (1, 2, 4, 8, 12)
GROWTH_COLS = ("sct_growth1", "sct_growth2", "sct_growth4", "sct_growth8",
               "sct_slope12", "sct_pma_share4", "sct_volatility8")


def hcols(prefix: str) -> list[str]:
    """The 10 trailing-history columns add_history_features() creates per count col."""
    out = []
    for w in WINDOWS:
        out.append(f"{prefix}_sum{w}")
    out += [f"{prefix}_cum", f"{prefix}_mean4", f"{prefix}_std8",
            f"{prefix}_accel", f"{prefix}_log4"]
    return out


def add_history_features(panel: pd.DataFrame, cols: tuple[str, ...] = HISTORY_COLS_FULL) -> pd.DataFrame:
    panel = panel.sort_values(["track_id", "qnum"]).copy()
    g = panel.groupby("track_id", observed=True)
    for col in cols:
        if col not in panel.columns:
            continue
        for w in WINDOWS:
            panel[f"{col}_sum{w}"] = g[col].transform(
                lambda s, w=w: s.rolling(w, min_periods=0).sum())
        panel[f"{col}_cum"] = g[col].transform(lambda s: s.cumsum())
        panel[f"{col}_mean4"] = g[col].transform(
            lambda s: s.rolling(4, min_periods=1).mean())
        panel[f"{col}_std8"] = g[col].transform(
            lambda s: s.rolling(8, min_periods=3).std())
        recent = g[col].transform(lambda s: s.rolling(2, min_periods=1).sum())
        prior = g[col].transform(lambda s: s.shift(2).rolling(4, min_periods=1).sum())
        panel[f"{col}_accel"] = (recent - prior) / prior.clip(lower=1.0)
        panel[f"{col}_log4"] = np.log1p(panel[f"{col}_sum4"].to_numpy(dtype=float))
    panel["exposure_q"] = panel["exposure_q"].astype(float)
    panel["log_exposure"] = np.log1p(panel["exposure_q"])
    return panel


def add_growth_features(panel: pd.DataFrame) -> pd.DataFrame:
    """SciTrends-style growth features (PHOENIX-001 H8), same formulas."""
    panel = panel.sort_values(["track_id", "qnum"]).copy()
    g = panel.groupby("track_id", observed=True)
    for w in (1, 2, 4, 8):
        cur = g["f_n_device"].transform(lambda s, w=w: s.rolling(w, min_periods=1).sum())
        prev = g["f_n_device"].transform(
            lambda s, w=w: s.shift(w).rolling(w, min_periods=1).sum())
        panel[f"sct_growth{w}"] = (cur - prev) / (prev + 1.0)

    slope = np.full(len(panel), np.nan)
    x = np.arange(12.0)
    xc = x - x.mean()
    denom = float((xc ** 2).sum())
    vals = panel["f_n_device"].to_numpy(dtype=float)
    qn = panel["qnum"].to_numpy()
    for _, idx in panel.groupby("track_id", observed=True).indices.items():
        idx = np.sort(np.asarray(idx))
        v = vals[idx]
        # only a contiguous 12-quarter window is a valid trailing-12Q slope
        for i in range(11, len(v)):
            if qn[idx[i]] - qn[idx[i - 11]] != 11:
                continue
            seg = np.log1p(v[i - 11:i + 1])
            slope[idx[i]] = float((xc * seg).sum() / denom)
    panel["sct_slope12"] = slope
    panel["sct_pma_share4"] = (panel["f_n_pma_sum4"].to_numpy(dtype=float)
                               / (panel["f_n_device_sum4"].to_numpy(dtype=float) + 1.0))
    panel["sct_volatility8"] = (panel["f_n_device_std8"].to_numpy(dtype=float)
                                / (panel["f_n_device_mean4"].to_numpy(dtype=float) + 1.0))
    return panel


def add_trend_score(panel: pd.DataFrame) -> pd.DataFrame:
    """PHOENIX-001 B2: OLS forecast of the next 4 quarters / trailing mean."""
    panel = panel.sort_values(["track_id", "qnum"]).copy()
    out = np.full(len(panel), np.nan)
    vals = panel["f_n_device"].to_numpy(dtype=float)
    qn = panel["qnum"].to_numpy()
    for _, idx in panel.groupby("track_id", observed=True).indices.items():
        idx = np.sort(np.asarray(idx))
        v = vals[idx]
        q = qn[idx]
        for i in range(len(idx)):
            j0 = i
            while j0 > 0 and q[i] - q[j0 - 1] <= 7 and i - j0 < 7:
                j0 -= 1
            w = v[j0:i + 1]
            if len(w) < 4:
                out[idx[i]] = v[i]
                continue
            x = np.arange(len(w), dtype=float)
            xc = x - x.mean()
            b = float((xc * (w - w.mean())).sum() / max((xc ** 2).sum(), 1e-9))
            fwd = w.mean() + b * np.mean(np.arange(len(w), len(w) + 4, dtype=float))
            out[idx[i]] = max(fwd, 0.0) / (w.mean() + 1.0)
    panel["b2_trend_score"] = out
    return panel


def build_features(panel: pd.DataFrame) -> pd.DataFrame:
    panel = add_history_features(panel)
    panel = add_growth_features(panel)
    panel = add_trend_score(panel)
    return panel.sort_values(["track_id", "qnum"]).reset_index(drop=True)


# --------------------------------------------------------------- feature sets (arms)
B1_FEATS = hcols("f_n_device") + ["exposure_q", "log_exposure"]
GROWTH_FEATS = list(GROWTH_COLS)
LEVEL_FEATS = ["f_n_device_sum4", "f_n_device_sum8", "f_n_device_sum12",
               "f_n_device_mean4", "f_n_device_log4", "exposure_q", "log_exposure"]
TREND_FEATS = ["sct_slope12", "b2_trend_score", "f_n_device_accel"]
MA_FEATS = ["f_n_device_sum4", "f_n_device_sum8", "f_n_device_mean4", "log_exposure"]

M5_FEATS = (B1_FEATS + GROWTH_FEATS
            + [c for col in ("f_n_510k", "f_n_pma", "f_n_trial", "f_n_device_recall", "f_n_total")
               for c in hcols(col)])

FEATURE_SETS = {
    "M1_persistence": B1_FEATS,
    "M2_ma_level": MA_FEATS,
    "M3_trend": TREND_FEATS,
    "M4_h8_growth": B1_FEATS + GROWTH_FEATS,
    "M5_full_regularised": M5_FEATS,
    "M6_hgb": B1_FEATS + GROWTH_FEATS,
    "M7_mean_reversion": LEVEL_FEATS,
}


def available_features(panel: pd.DataFrame, cols: list[str]) -> list[str]:
    return [c for c in cols if c in panel.columns]
