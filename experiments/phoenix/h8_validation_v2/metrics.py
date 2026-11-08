"""PHOENIX-002 evaluation metrics and uncertainty machinery.

Everything is deterministic given SEED.  Clusters are tracks (the unit of dependence);
all paired contrasts use identical rows and the same bootstrap resamples for both arms.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

import protocol as P


# ------------------------------------------------------------------------ metrics
def average_precision(y, score) -> float:
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    ok = np.isfinite(y) & np.isfinite(s)
    if ok.sum() < 2 or len(np.unique(y[ok])) < 2:
        return float("nan")
    return float(average_precision_score(y[ok], s[ok]))


def roc_auc(y, score) -> float:
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    ok = np.isfinite(y) & np.isfinite(s)
    if ok.sum() < 2 or len(np.unique(y[ok])) < 2:
        return float("nan")
    return float(roc_auc_score(y[ok], s[ok]))


def brier(y, score) -> float:
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    ok = np.isfinite(y) & np.isfinite(s)
    return float(np.mean((s[ok] - y[ok]) ** 2)) if ok.any() else float("nan")


def calibration_slope(y, score) -> float:
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    ok = np.isfinite(y) & np.isfinite(s)
    if ok.sum() < 10:
        return float("nan")
    y, s = y[ok], s[ok]
    if np.std(s) == 0:
        return float("nan")
    return float(np.cov(s, y)[0, 1] / np.var(s))


def precision_at_frac(y, score, frac: float) -> float:
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    ok = np.isfinite(y) & np.isfinite(s)
    y, s = y[ok], s[ok]
    if len(y) == 0:
        return float("nan")
    k = max(1, int(round(len(y) * frac)))
    return float(np.mean(y[np.argsort(-s)[:k]]))


def recall_at_frac(y, score, frac: float) -> float:
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    ok = np.isfinite(y) & np.isfinite(s)
    y, s = y[ok], s[ok]
    if len(y) == 0 or y.sum() == 0:
        return float("nan")
    k = max(1, int(round(len(y) * frac)))
    return float(y[np.argsort(-s)[:k]].sum() / y.sum())


def lift_at_frac(y, score, frac: float) -> float:
    p = float(np.nanmean(np.asarray(y, dtype=float)))
    if not np.isfinite(p) or p == 0:
        return float("nan")
    return precision_at_frac(y, score, frac) / p


def alert_precision_topk(d: pd.DataFrame, score_col: str, k: int = P.ALERT_BUDGET_TOP) -> dict:
    """Fixed per-quarter alert budget: precision among the top-k scored tracks."""
    d = d.dropna(subset=["y", score_col])
    if d.empty:
        return {"k": k, "mean_precision": float("nan"), "n_quarters": 0}
    precs, hits, alarms = [], 0, 0
    for _, g in d.groupby("quarter", observed=True):
        s = g[score_col].to_numpy(dtype=float)
        y = g["y"].to_numpy(dtype=float)
        idx = np.argsort(-s)[: min(k, len(s))]
        if len(idx):
            precs.append(float(y[idx].mean()))
            hits += int(y[idx].sum())
            alarms += int(len(idx))
    precs = np.asarray(precs, dtype=float)
    return {
        "k": int(k),
        "mean_precision": float(precs.mean()) if len(precs) else float("nan"),
        "n_quarters": int(len(precs)),
        "true_positives_alerted": int(hits),
        "alerts_issued": int(alarms),
        "false_alerts_per_quarter": float((alarms - hits) / len(precs)) if len(precs) else float("nan"),
        "base_rate_in_alert_pool": float(d["y"].mean()),
    }


# ---------------------------------------------------------------------- bootstrap
def _clusters(groups: np.ndarray):
    uniq = np.unique(groups)
    return uniq, {g: np.flatnonzero(groups == g) for g in uniq}


def cluster_bootstrap_ci(y, score, groups, B: int = P.B_BOOT, seed: int = P.SEED,
                         alpha: float = 0.05, stat=average_precision) -> tuple[float, float, float]:
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    groups = np.asarray(groups)
    ok = np.isfinite(y) & np.isfinite(s)
    y, s, groups = y[ok], s[ok], groups[ok]
    point = stat(y, s)
    uniq, idx_by = _clusters(groups)
    if len(uniq) < 3:
        return point, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by[g] for g in pick])
        v = stat(y[idx], s[idx])
        if np.isfinite(v):
            vals.append(v)
    if len(vals) < 20:
        return point, float("nan"), float("nan")
    lo, hi = np.quantile(vals, [alpha / 2, 1 - alpha / 2])
    return float(point), float(lo), float(hi)


def paired_bootstrap_diff(y, a, b, groups, B: int = P.B_BOOT, seed: int = P.SEED,
                          alpha: float = 0.05, stat=average_precision) -> dict:
    """stat(a) - stat(b) on identical rows, paired cluster bootstrap."""
    y = np.asarray(y, dtype=float)
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    groups = np.asarray(groups)
    ok = np.isfinite(y) & np.isfinite(a) & np.isfinite(b)
    y, a, b, groups = y[ok], a[ok], b[ok], groups[ok]
    point = stat(y, a) - stat(y, b)
    uniq, idx_by = _clusters(groups)
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(B):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by[g] for g in pick])
        d = stat(y[idx], a[idx]) - stat(y[idx], b[idx])
        if np.isfinite(d):
            diffs.append(d)
    diffs = np.asarray(diffs)
    if len(diffs) < 20:
        return {"diff": float(point), "lo": float("nan"), "hi": float("nan"),
                "p": float("nan"), "n": int(len(y)), "n_pos": int(np.nansum(y)),
                "n_boot": int(len(diffs))}
    lo, hi = np.quantile(diffs, [alpha / 2, 1 - alpha / 2])
    p = 2 * min(float((diffs <= 0).mean()), float((diffs >= 0).mean()))
    return {
        "diff": float(point), "lo": float(lo), "hi": float(hi),
        "p": float(min(1.0, p)),
        "ap_a": float(stat(y, a)), "ap_b": float(stat(y, b)),
        "n": int(len(y)), "n_pos": int(np.nansum(y)),
        "n_boot": int(len(diffs)),
        "ci_width": float(hi - lo),
    }


# ------------------------------------------------------------------ metric bundles
def evaluate_arm(d: pd.DataFrame, score_col: str, name: str,
                 with_ci: bool = True, B: int = P.B_BOOT, seed: int = P.SEED) -> dict:
    d = d.dropna(subset=["y", score_col])
    if d.empty or d["y"].nunique() < 2:
        return {"model": name, "n": int(len(d)), "status": "NO_VARIATION"}
    y = d["y"].to_numpy(dtype=float)
    s = d[score_col].to_numpy(dtype=float)
    out = {
        "model": name,
        "n": int(len(d)),
        "n_pos": int(y.sum()),
        "prevalence": float(y.mean()),
        "ap": average_precision(y, s),
        "roc_auc": roc_auc(y, s),
        "brier": brier(y, s),
        "calibration_slope": calibration_slope(y, s),
    }
    if with_ci:
        point, lo, hi = cluster_bootstrap_ci(y, s, d["track_id"].to_numpy(), B=B, seed=seed)
        out["ap_ci95"] = [float(lo), float(hi)]
    for frac in (0.05, 0.10, 0.20):
        tag = f"{int(round(frac * 100))}pct"
        out[f"precision_at_{tag}"] = precision_at_frac(y, s, frac)
        out[f"recall_at_{tag}"] = recall_at_frac(y, s, frac)
        out[f"lift_at_{tag}"] = lift_at_frac(y, s, frac)
    out["alert_top10_per_quarter"] = alert_precision_topk(d, score_col, k=P.ALERT_BUDGET_TOP)
    return out


def metrics_by_group(d: pd.DataFrame, score_col: str, group_col: str,
                     min_n: int = 30, min_pos: int = 3, with_ci: bool = False,
                     B: int = P.B_BOOT_SECONDARY) -> dict:
    out = {}
    for key, g in d.groupby(group_col, observed=True):
        g = g.dropna(subset=["y", score_col])
        if len(g) < min_n or g["y"].sum() < min_pos:
            out[str(key)] = {"n": int(len(g)), "n_pos": int(g["y"].sum()),
                             "status": "TOO_SMALL"}
            continue
        y = g["y"].to_numpy(dtype=float)
        s = g[score_col].to_numpy(dtype=float)
        rec = {"n": int(len(g)), "n_pos": int(g["y"].sum()),
               "prevalence": float(y.mean()), "ap": average_precision(y, s)}
        if with_ci:
            point, lo, hi = cluster_bootstrap_ci(y, s, g["track_id"].to_numpy(), B=B)
            rec["ap_ci95"] = [float(lo), float(hi)]
        out[str(key)] = rec
    return out


def contrast(d: pd.DataFrame, a: str, b: str, B: int = P.B_BOOT,
             seed: int = P.SEED) -> dict:
    res = paired_bootstrap_diff(d["y"].to_numpy(dtype=float),
                                d[a].to_numpy(dtype=float),
                                d[b].to_numpy(dtype=float),
                                d["track_id"].to_numpy(), B=B, seed=seed)
    res["a"], res["b"] = a, b
    return res


def holm_adjust(pvals: dict[str, float]) -> dict[str, float]:
    items = [(k, v) for k, v in pvals.items() if v is not None and np.isfinite(v)]
    m = len(items)
    ordered = sorted(items, key=lambda kv: kv[1])
    adj = {k: float("nan") for k in pvals}
    prev = 0.0
    for i, (k, p) in enumerate(ordered):
        prev = max(prev, min(1.0, (m - i) * p))
        adj[k] = prev
    return adj


def verdict_from_contrast(c: dict, tau: float = P.TAU_AP,
                          min_pos: int = P.GATE_MIN_POSITIVES) -> str:
    """Mechanical pre-registered verdict for one primary contrast."""
    d, lo, hi, p = c.get("diff"), c.get("lo"), c.get("hi"), c.get("p")
    if not all(np.isfinite(v) for v in (d, lo, hi, p)):
        return "INCONCLUSIVE"
    if c.get("n_pos", 0) < min_pos:
        return "INCONCLUSIVE"
    if d >= tau and lo > 0 and p < P.GATE_PRIMARY["p_max"]:
        return "MEETS_TAU"
    if lo > 0 and d > 0:
        return "POSITIVE_BELOW_TAU"
    if hi < tau:
        return "RULES_OUT_TAU"
    return "INCONCLUSIVE"
