"""Statistical tests described in the M6 methods audit (Lee & Youn 2026).

Independent re-implementation of the *test logic* stated in
doi:10.2196/103040 Methods ("Statistical Analysis"):

  * Cochran-Armitage test for linear trend in a proportion across ordered groups,
    with the source's specification: "the 4 eras were coded as equally spaced
    ordinal scores (1-4) in chronological order; the test therefore evaluates
    ordered change in specialty share across successive eras rather than change
    per calendar year".
  * 2-proportion z test (used for the Era 3 -> Era 4 radiology share).
  * Wilson score interval (the paper's Figure 3B uses Wilson 95% CIs).
  * Pearson chi-square with Cramer's V, plus a Monte Carlo permutation p-value
    (the paper: "checked with a Monte Carlo permutation test (10,000 replicates)")
    because 51/68 cells of the 17x4 table had expected counts < 5.
  * Bonferroni correction across the 17 advisory-committee panels.

No original code was available; this is method logic only, validated on synthetic
data in selftest_synthetic.py. Nothing here reproduces the paper's estimates.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
from scipy import stats


# --------------------------------------------------------------------------- #
# Proportion trends
# --------------------------------------------------------------------------- #
def cochran_armitage(
    counts: Sequence[float],
    totals: Sequence[float],
    scores: Sequence[float] | None = None,
) -> dict:
    """Cochran-Armitage trend test for a binary outcome over ordered groups.

    counts[i] = number of 'successes' (e.g. devices in this specialty) in group i
    totals[i] = number of devices in group i
    scores[i] = ordinal score for group i (default 1..k, matching the paper)

    z > 0 means the proportion increases with the score.
    Returns both one-sided (increasing) and two-sided p-values; the paper reports
    Z with uncorrected and Bonferroni-adjusted p-values, and reads the sign.
    """
    c = np.asarray(counts, dtype=float)
    n = np.asarray(totals, dtype=float)
    if c.shape != n.shape:
        raise ValueError("counts and totals must have the same length")
    k = len(c)
    if scores is None:
        t = np.arange(1, k + 1, dtype=float)
    else:
        t = np.asarray(scores, dtype=float)
    N = n.sum()
    R = c.sum()
    p = R / N
    if p <= 0 or p >= 1:
        raise ValueError("no variation in the outcome; test undefined")

    num = float(np.sum(t * (c - n * p)))
    den = p * (1 - p) * (float(np.sum(n * t**2)) - float(np.sum(n * t)) ** 2 / N)
    if den <= 0:
        raise ValueError("degenerate score/denominator")
    z = num / np.sqrt(den)
    p_one = float(stats.norm.sf(z))          # increasing trend
    p_two = float(2 * stats.norm.sf(abs(z)))
    return {"z": float(z), "p_one_sided_increasing": p_one, "p_two_sided": p_two}


def bonferroni(p_values: Iterable[float], m: int | None = None) -> list[float]:
    """Bonferroni-adjusted p-values, clipped at 1 (paper corrects over 17 panels)."""
    pv = np.asarray(list(p_values), dtype=float)
    if m is None:
        m = pv.size
    return np.clip(pv * m, 0.0, 1.0).tolist()


def two_proportion_z(k1: int, n1: int, k2: int, n2: int) -> dict:
    """Pooled two-proportion z test (Era-3 vs Era-4 radiology share in the paper)."""
    p1, p2 = k1 / n1, k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        raise ValueError("zero standard error")
    z = (p2 - p1) / se
    return {
        "p1": p1,
        "p2": p2,
        "diff": p2 - p1,
        "z": float(z),
        "p_two_sided": float(2 * stats.norm.sf(abs(z))),
    }


def wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (no continuity correction)."""
    if n <= 0:
        raise ValueError("n must be positive")
    z = stats.norm.ppf(1 - alpha / 2)
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return float(centre - half), float(centre + half)


def wilson_ci_overdispersed(k: int, n: int, design_effect: float = 1.0, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson interval with the effective sample size divided by a design effect.

    Included deliberately: in MedRadar the unit is an authorisation and several
    authorisations can come from one firm, so the effective n is smaller than the
    nominal n. design_effect=1 recovers the ordinary Wilson interval exactly.

    The interval is built from the point estimate p = k/n and the effective size
    n_eff = n / design_effect, so it widens as the design effect grows without
    requiring n_eff >= k.
    """
    if design_effect <= 0:
        raise ValueError("design_effect must be > 0")
    if n <= 0:
        raise ValueError("n must be positive")
    z = stats.norm.ppf(1 - alpha / 2)
    p = k / n
    n_eff = n / design_effect
    denom = 1 + z**2 / n_eff
    centre = (p + z**2 / (2 * n_eff)) / denom
    half = z * np.sqrt(p * (1 - p) / n_eff + z**2 / (4 * n_eff**2)) / denom
    return float(max(0.0, centre - half)), float(min(1.0, centre + half))


# --------------------------------------------------------------------------- #
# Contingency tables
# --------------------------------------------------------------------------- #
def cramers_v(table: Sequence[Sequence[float]]) -> float:
    """Cramer's V for an r x c contingency table."""
    obs = np.asarray(table, dtype=float)
    chi2 = stats.chi2_contingency(obs, correction=False)[0]
    n = obs.sum()
    return float(np.sqrt(chi2 / (n * (min(obs.shape) - 1))))


def chi2_with_permutation(
    table: Sequence[Sequence[float]],
    n_perm: int = 10000,
    seed: int = 0,
) -> dict:
    """Pearson chi-square plus a Monte Carlo permutation p-value.

    The permutation null fixes both margins and permutes the group labels, which
    is the appropriate reference distribution when expected counts are small
    (51 of 68 cells < 5 in the source paper's 17x4 table). Implemented by
    resampling table entries from the independence model; for fixed margins the
    chi-square statistic only depends on the observed arrangement, so a
    random-permutation of labels is emulated by drawing from the multivariate
    hypergeometric via repeated margin-conditioned shuffles.
    """
    obs = np.asarray(table, dtype=float)
    chi2_obs, _, _, expected = stats.chi2_contingency(obs, correction=False)
    row = obs.sum(axis=1)
    col = obs.sum(axis=0)
    n = obs.sum()
    exp = np.outer(row, col) / n
    rng = np.random.default_rng(seed)
    # Margin-conditioned permutation of a contingency table with integer counts.
    obs_int = np.rint(obs).astype(int)
    n_exceed = 0
    for _ in range(n_perm):
        perm = _permute_table(obs_int, rng)
        e = np.outer(perm.sum(axis=1), perm.sum(axis=0)) / n
        with np.errstate(divide="ignore", invalid="ignore"):
            stat = np.nansum((perm - e) ** 2 / np.where(e == 0, np.nan, e))
        if stat >= chi2_obs - 1e-12:
            n_exceed += 1
    return {
        "chi2": float(chi2_obs),
        "dof": int((obs.shape[0] - 1) * (obs.shape[1] - 1)),
        "p_asymptotic": float(stats.chi2.sf(chi2_obs, (obs.shape[0] - 1) * (obs.shape[1] - 1))),
        "p_permutation": (n_exceed + 1) / (n_perm + 1),
        "cramers_v": cramers_v(obs),
        "min_expected": float(exp.min()),
        "frac_cells_expected_lt5": float(np.mean(exp < 5)),
        "n_perm": n_perm,
    }


def _permute_table(obs: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Shuffle a contingency table keeping its margins (Fisher-Yates on atomic units).

    Small tables only: builds a vector of column labels with the observed
    multiplicities, shuffles it, and re-bins by row sizes. Exact to the margins.
    """
    row = obs.sum(axis=1)
    col_labels = np.repeat(np.arange(obs.shape[1]), obs.sum(axis=0))
    rng.shuffle(col_labels)
    out = np.zeros_like(obs)
    start = 0
    for i, r in enumerate(row):
        chunk = col_labels[start : start + r]
        start += r
        vals, cnts = np.unique(chunk, return_counts=True)
        for v, c in zip(vals, cnts):
            out[i, v] = c
    return out


def annual_rate(count: int, years: float) -> float:
    """Mean annual authorisations (the paper's Era 3/Era 4 rate ratios)."""
    if years <= 0:
        raise ValueError("years must be positive")
    return count / years


def rate_ratio(c_a: int, y_a: float, c_b: int, y_b: float) -> float | None:
    """Ratio of mean annual rates, or None when the denominator is zero."""
    ra, rb = annual_rate(c_a, y_a), annual_rate(c_b, y_b)
    if ra == 0:
        return None
    return rb / ra


if __name__ == "__main__":
    print(cochran_armitage([15, 118, 347, 614], [42, 190, 406, 792]))
    print(two_proportion_z(347, 406, 614, 792))
    print(wilson_ci(614, 792))
