"""Herfindahl-Hirschman Index (HHI) and bootstrap inference.

Independent re-implementation of the concentration analysis described in
Lee & Youn (2026), J Med Internet Res 28:e103040, doi:10.2196/103040
(audited as method M6 in docs/phoenix/audits/A06_fda_ai_device_longitudinal.md).

Definition taken verbatim from that paper's Methods:
    "The Herfindahl-Hirschman Index (HHI), defined as the sum of squared
     specialty share fractions, was calculated for each era to quantify
     specialty concentration (range: 0-1; higher values indicate greater
     concentration), with 95% CIs obtained from 2000 bootstrap resamples."
and, for the change test:
    "...drawing 2000 independent bootstrap resamples of the device sets within
     each of the 2 eras, computing the difference in HHI for each pair of
     resamples, and calculating the 2-sided P value as twice the proportion of
     resampled differences less than or equal to zero."

Scope / honesty note: this module re-implements *method logic only*. It is not
the authors' code (none was published) and it reproduces none of their results;
it is exercised on synthetic data in selftest_synthetic.py, plus one arithmetic
check against the published Table 1 counts of that paper.

Base-of-shares note (important, and a known ambiguity in the source):
The HHI is computed over the *shares of authorisations* partitioned by specialty
within an era. It is NOT computed over firms and NOT over product codes. The
number of categories included in the partition materially changes the value when
the era denominator is small; see share_base_sensitivity().
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

import numpy as np


# --------------------------------------------------------------------------- #
# Core index
# --------------------------------------------------------------------------- #
def shares(counts: Iterable[float]) -> np.ndarray:
    """Normalise non-negative counts to shares that sum to 1."""
    arr = np.asarray([c for c in counts], dtype=float)
    if arr.size == 0:
        raise ValueError("empty count vector")
    if np.any(arr < 0):
        raise ValueError("counts must be non-negative")
    total = arr.sum()
    if total <= 0:
        raise ValueError("counts sum to zero")
    return arr / total


def hhi(counts: Iterable[float]) -> float:
    """HHI = sum of squared share fractions. Range (1/k, 1]; 1 = pure monopoly.

    Zero-count categories contribute nothing, so passing a full category list
    (including categories that are absent in this period) or a reduced list of
    observed categories yields the same value. That is a property of the index,
    and is why the *aggregation of small categories into an "Other" bucket* --
    not the presence of empty categories -- is what changes the number.
    """
    s = shares(counts)
    return float(np.sum(s**2))


def effective_number_of_categories(counts: Iterable[float]) -> float:
    """1/HHI: an interpretable 'effective number of specialties'."""
    return 1.0 / hhi(counts)


# --------------------------------------------------------------------------- #
# Bootstrap resampling of the device set
# --------------------------------------------------------------------------- #
def bootstrap_counts(counts: Sequence[float], n_boot: int = 2000, seed: int = 0) -> np.ndarray:
    """Resample the underlying *devices* and re-count.

    Equivalent to drawing n devices with replacement from the observed share
    vector, i.e. counts ~ Multinomial(n, shares). Returned shape (n_boot, k).
    """
    arr = np.asarray(counts, dtype=float)
    n = int(arr.sum())
    p = shares(arr)
    rng = np.random.default_rng(seed)
    return rng.multinomial(n, p, size=n_boot).astype(float)


def hhi_ci(
    counts: Sequence[float],
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> dict:
    """Percentile bootstrap CI for HHI (the paper reports 95% CIs, 2000 reps)."""
    point = hhi(counts)
    draws = bootstrap_counts(counts, n_boot=n_boot, seed=seed)
    boot = np.array([hhi(row) for row in draws])
    lo, hi = np.quantile(boot, [alpha / 2, 1 - alpha / 2])
    return {
        "hhi": point,
        "ci_low": float(lo),
        "ci_high": float(hi),
        "n_boot": n_boot,
        "boot_mean": float(boot.mean()),
        "boot_sd": float(boot.std(ddof=1)),
    }


def hhi_difference_test(
    counts_a: Sequence[float],
    counts_b: Sequence[float],
    n_boot: int = 2000,
    seed: int = 0,
    two_sided: str = "paper",
) -> dict:
    """Bootstrap test for HHI(b) - HHI(a) with independent resamples per era.

    `two_sided="paper"` reproduces the rule stated in the source: twice the
    proportion of resampled differences <= 0. That rule presumes the *a priori*
    expectation of a decline (b < a); it is one-sided in disguise, because a
    difference in the opposite direction would return p >= 1 and be clipped to 1.
    `two_sided="symmetric"` uses 2 * min(P(diff<=0), P(diff>=0)) instead, which is
    the conventional symmetric two-sided bootstrap p-value. Both are returned so
    the choice is explicit rather than hidden.
    """
    if len(counts_a) != len(counts_b):
        raise ValueError(
            "the two eras must be laid out over the same category vector; "
            "pad absent categories with 0"
        )
    a = np.asarray(counts_a, dtype=float)
    b = np.asarray(counts_b, dtype=float)
    la = np.array([hhi(row) for row in bootstrap_counts(a, n_boot, seed)])
    lb = np.array([hhi(row) for row in bootstrap_counts(b, n_boot, seed + 1)])
    signed = lb - la  # positive == concentration increased from a to b

    # The source's stated rule ("twice the proportion of resampled differences
    # less than or equal to zero") is only well defined once the sign convention is
    # fixed, and it is written for a HHI *decline*. Taken literally with the
    # difference defined as (HHI_a - HHI_b), positive values are declines and
    # "<= 0" is the no-decline null:
    #     p = 2 * P( HHI_a - HHI_b <= 0 )
    # The consequence is explicit and deliberate: the rule can certify a decline but
    # cannot certify an *increase* (it returns p >= 1, clipped to 1). p_symmetric
    # is provided as the conventional alternative.
    decrease = la - lb  # positive == concentration fell from a to b
    p_paper = min(1.0, 2.0 * float(np.mean(decrease <= 0.0)))
    p_sym = 2.0 * min(float(np.mean(signed <= 0.0)), float(np.mean(signed >= 0.0)))
    p_sym = min(1.0, p_sym)
    return {
        "hhi_a": hhi(a),
        "hhi_b": hhi(b),
        "observed_diff": hhi(b) - hhi(a),
        "ci_diff_low": float(np.quantile(signed, 0.025)),
        "ci_diff_high": float(np.quantile(signed, 0.975)),
        "p_paper_rule_decline": p_paper,
        "p_symmetric": p_sym,
        "n_boot": n_boot,
        "frac_boot_negative": float(np.mean(signed <= 0.0)),
    }


# --------------------------------------------------------------------------- #
# Share-base sensitivity: this is the audit-relevant part
# --------------------------------------------------------------------------- #
def share_base_sensitivity(
    aggregated: Mapping[str, float],
    disaggregated: Mapping[str, float],
) -> dict:
    """Compare HHI computed on a coarse partition vs a fine partition.

    `aggregated` are counts for the published category rows (small categories
    pooled into one "Other" row); `disaggregated` splits that pooled row into its
    constituent categories. Both must have the same grand total. The difference
    shows how much of the reported index is an artefact of category granularity
    when the period denominator is small.
    """
    ta, td = sum(aggregated.values()), sum(disaggregated.values())
    if ta != td:
        raise ValueError(f"totals differ: aggregated={ta} disaggregated={td}")
    return {
        "n": ta,
        "hhi_aggregated": hhi(aggregated.values()),
        "hhi_disaggregated": hhi(disaggregated.values()),
        "delta": hhi(disaggregated.values()) - hhi(aggregated.values()),
        "k_aggregated": len(aggregated),
        "k_disaggregated": len(disaggregated),
    }


def era_table_hhi(
    rows: Mapping[str, Sequence[float]],
    eras: Sequence[str] | None = None,
) -> list[dict]:
    """Compute HHI per era from a {category: (count_era1, count_era2, ...)} table.

    This mirrors the layout of the published Table 1 of the M6 paper, so the
    published counts can be fed straight in (see selftest_synthetic.py).
    """
    first = next(iter(rows.values()))
    n_eras = len(first)
    if eras is None:
        eras = [f"era{i + 1}" for i in range(n_eras)]
    out = []
    for j, name in enumerate(eras):
        counts = [rows[k][j] for k in rows]
        out.append(
            {
                "era": name,
                "n": int(sum(counts)),
                "hhi": hhi(counts),
                "active_categories": int(sum(1 for c in counts if c > 0)),
            }
        )
    return out


if __name__ == "__main__":  # tiny smoke test
    print(hhi([100]))
    print(hhi([25, 25, 25, 25]))
    print(hhi_ci([614, 62, 45, 18, 19, 5, 4, 6, 19]))
