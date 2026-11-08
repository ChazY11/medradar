"""Change-point / anomaly detectors for the H7 semi-synthetic benchmark.

No third-party change-point library is used (protocol §9: `ruptures` is forbidden).
Everything here is numpy.

Detectors
---------
pelt_cps(y, penalty, min_size=2)
    Exact PELT (Killick et al.) with a Poisson segment cost, implemented from the
    recursion
        F[t] = min_s  F[s] + C(s, t) + beta
        C(s, t) = -S*log(S/L) + S,   S = sum(y[s:t]), L = t - s   (Poisson NLL up to
                  a segment-independent constant), beta = lam * log(n) is the
                  BIC-style penalty.
    The PELT pruning rule (drop s once F[s] + C(s,t) > F[t]) is applied; with
    n = 86 the full O(n^2) DP would be trivial anyway.

cusum_alarms(y, k=0.5, h=..., r=...)
    Standardised CUSUM: z_t = (y_t - m_t) / sd_t with m_t the trailing-8Q mean
    (excluding t) and sd_t^2 = m_t + m_t^2 / r (negative-binomial variance at the
    known size r; r = inf gives Poisson). S_t = max(0, S_{t-1} + z_t - k), alarm
    when S_t > h, then S is reset to 0.

fixed_threshold_ratio(y), growth_rate(y)
    The two "non-change-point" comparators from protocol §6 H7. Both use Laplace
    smoothing (+1 events) on the trailing means so that a zero trailing mean does
    not make the statistic infinite and the threshold stays tunable on sparse
    tracks. The unsmoothed protocol-literal form is recovered at large counts.

All "alarm" index conventions are 0-based positions in the 86-quarter series; the
evaluation window is indices 8..85 (needs 8 quarters of history).
"""
from __future__ import annotations

import math

import numpy as np

EVAL_MIN = 8


# ------------------------------------------------------------------------- PELT
def pelt_cps(y, penalty: float, min_size: int = 2) -> list[int]:
    """Exact PELT. Returns the estimated change-point positions (1..n-1).

    Pure-Python inner loop: the PELT pruning rule keeps the candidate set small at
    n=86, which makes this ~30x faster than dispatching numpy per time step while
    remaining the exact recursion (no approximation, no segment-count cap).
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    cs = [0.0] * (n + 1)
    acc = 0.0
    for i in range(n):
        acc += float(y[i])
        cs[i + 1] = acc
    INF = float("inf")
    F = [INF] * (n + 1)
    F[0] = -penalty
    prev = [0] * (n + 1)
    R = [0]
    log = math.log
    for t in range(1, n + 1):
        best = INF
        bi = 0
        ct = cs[t]
        vals = []
        for s in R:
            L = t - s
            if L < min_size:
                vals.append((s, None))
                continue
            S = ct - cs[s]
            cost = (-S * log(S / L) + S) if S > 0 else 0.0
            v = F[s] + cost
            vals.append((s, v))
            if v < best:
                best = v
                bi = s
        if best < INF:
            F[t] = best + penalty
            prev[t] = bi
            thr = F[t]
            R = [s for s, v in vals if v is None or v <= thr]
        else:
            R = [s for s, _ in vals]
        R.append(t)
    cps: list[int] = []
    t = n
    while t > 0:
        s = prev[t]
        if s > 0:
            cps.append(s)
        t = s
    return sorted(cps)


def pelt_penalty(lam: float, n: int) -> float:
    """BIC-style penalty: lam * log(n)."""
    return float(lam * np.log(n))


# ------------------------------------------------------------------------ CUSUM
def _trailing_mean_excl(y: np.ndarray, w: int) -> np.ndarray:
    """m_t = mean(y[t-w : t]) (excludes t); NaN where t < w."""
    n = y.size
    out = np.full(n, np.nan)
    if n > w:
        c = np.concatenate(([0.0], np.cumsum(y)))
        out[w:] = (c[w:n] - c[0:n - w]) / w
    return out


def cusum_alarms(y, k: float = 0.5, h: float = 5.0, r: float | np.inf = np.inf) -> list[int]:
    y = np.asarray(y, dtype=float)
    n = y.size
    m = _trailing_mean_excl(y, 8)
    alarms: list[int] = []
    S = 0.0
    r_is_inf = not np.isfinite(r)
    for t in range(n):
        mt = m[t]
        if not np.isfinite(mt):
            continue
        if r_is_inf:
            var = mt
        else:
            var = mt + mt * mt / r
        sd = float(np.sqrt(max(var, 1.0)))
        z = (y[t] - mt) / sd
        S = max(0.0, S + z - k)
        if S > h:
            alarms.append(t)
            S = 0.0
    return alarms


# ------------------------------------------------------------ simple comparators
def fixed_threshold_ratio(y) -> np.ndarray:
    """ratio_t = y_t / smoothed trailing-8Q mean. NaN before index 8."""
    y = np.asarray(y, dtype=float)
    n = y.size
    out = np.full(n, np.nan)
    if n > 8:
        c = np.concatenate(([0.0], np.cumsum(y)))
        s8 = c[8:n] - c[0:n - 8]
        out[8:] = y[8:] / ((s8 + 1.0) / 9.0)
    return out


def growth_rate(y) -> np.ndarray:
    """r_t = (sum of last 4Q + 1) / (sum of the 4Q before + 1) - 1."""
    y = np.asarray(y, dtype=float)
    n = y.size
    out = np.full(n, np.nan)
    if n < 8:
        return out
    c = np.concatenate(([0.0], np.cumsum(y)))
    for t in range(8, n):
        last4 = c[t + 1] - c[t - 3]
        prev4 = c[t - 3] - c[t - 7]
        out[t] = (last4 + 1.0) / (prev4 + 1.0) - 1.0
    return out


# --------------------------------------------------------------- shared helpers
def detection_from_alarms(alarms, tau: int, win: int = 2) -> tuple[bool, float]:
    """Detected if any alarm lies in [tau-win, tau+win]; delay = first alarm - tau."""
    cand = [int(a) for a in alarms if abs(int(a) - tau) <= win]
    if not cand:
        return False, float("nan")
    return True, float(min(cand) - tau)


def false_alarm_rate(alarms_list, n_series: int, eval_min: int = EVAL_MIN, n: int = 86) -> float:
    n_eval = n - eval_min
    total = sum(sum(1 for a in alarms if eval_min <= int(a) < n) for alarms in alarms_list)
    return float(total / (n_series * n_eval))


def detection_rate(flags) -> float:
    flags = np.asarray(flags, dtype=float)
    return float(np.nanmean(flags)) if flags.size else float("nan")
