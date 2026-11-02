"""Paired, entity-clustered inference for the detection benchmark.

Why this exists. The benchmark injects each (cell, onset, magnitude) trial once and
then scores every detector on the *same* injected series, because the injection seed
depends only on the cell/onset/magnitude, never on the detector. That is common random
numbers: the comparison between two detectors is paired trial-by-trial, which is far
more powerful than comparing two independent detection rates.

Trials from the same entity are not independent (one firm's streams share its filing
behaviour), so uncertainty is estimated by resampling **entities**, not trials.

A difference whose interval includes zero is not a difference.
"""
from __future__ import annotations

import random
from typing import Any, Iterable, Sequence


def _cluster_groups(rows: Sequence[dict[str, Any]]) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        groups.setdefault(str(row["entity"]), []).append(index)
    return groups


def _draw_indices(groups: dict[str, list[int]], rng: random.Random,
                  n_trials: int) -> list[int]:
    keys = list(groups)
    sampled: list[int] = []
    for _ in range(len(keys)):
        cluster = groups[keys[rng.randrange(len(keys))]]
        sampled.extend(cluster)
    return sampled


def percentile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        return float("nan")
    index = min(len(sorted_values) - 1, max(0, int(q * len(sorted_values))))
    return sorted_values[index]


def cluster_bootstrap_rate(rows: Sequence[dict[str, Any]], flag: str, *,
                           resamples: int = 2000, seed: int = 7,
                           confidence: float = 0.95) -> dict[str, Any]:
    """Detection probability with an entity-clustered percentile interval."""
    n = len(rows)
    if not n:
        return {"n": 0, "rate": None}
    observed = sum(1 for row in rows if row[flag]) / n
    groups = _cluster_groups(rows)
    rng = random.Random(seed)
    draws = []
    for _ in range(resamples):
        indices = _draw_indices(groups, rng, n)
        if not indices:
            continue
        draws.append(sum(1 for index in indices if rows[index][flag]) / len(indices))
    draws.sort()
    low = percentile(draws, (1 - confidence) / 2)
    high = percentile(draws, (1 + confidence) / 2)
    return {"n": n, "rate": observed, "ci_low": low, "ci_high": high,
            "clusters": len(groups), "resamples": len(draws), "seed": seed,
            "confidence": confidence}


def cluster_bootstrap_paired_difference(
        rows_a: Sequence[dict[str, Any]], rows_b: Sequence[dict[str, Any]], *,
        flag: str = "detected", resamples: int = 2000, seed: int = 7,
        confidence: float = 0.95) -> dict[str, Any]:
    """Paired difference rate(a) - rate(b) with an entity-clustered interval.

    ``rows_a`` and ``rows_b`` must be aligned trial-by-trial (same injected series,
    different detector). The pairing is preserved inside every resample.
    """
    if len(rows_a) != len(rows_b):
        raise ValueError("paired comparison needs aligned trials")
    n = len(rows_a)
    if not n:
        return {"n": 0, "difference": None}
    groups = _cluster_groups(rows_a)
    rng = random.Random(seed)
    point = (sum(1 for row in rows_a if row[flag]) / n
             - sum(1 for row in rows_b if row[flag]) / n)
    draws = []
    for _ in range(resamples):
        indices = _draw_indices(groups, rng, n)
        if not indices:
            continue
        a = sum(1 for index in indices if rows_a[index][flag]) / len(indices)
        b = sum(1 for index in indices if rows_b[index][flag]) / len(indices)
        draws.append(a - b)
    draws.sort()
    low = percentile(draws, (1 - confidence) / 2)
    high = percentile(draws, (1 + confidence) / 2)
    return {
        "n": n,
        "difference": point,
        "ci_low": low,
        "ci_high": high,
        "excludes_zero": bool(low > 0 or high < 0),
        "clusters": len(groups),
        "resamples": len(draws),
        "seed": seed,
        "confidence": confidence,
        "interpretation": ("entity-clustered paired percentile interval; the comparison is "
                           "paired trial-by-trial because every detector sees the identical "
                           "injected series"),
    }


def by_stratum(rows: Sequence[dict[str, Any]], field: str,
               flag: str = "detected") -> dict[str, Any]:
    """Detection rate per level of ``field`` (entity-clustered intervals)."""
    levels = sorted({str(row.get(field)) for row in rows})
    out = {}
    for level in levels:
        subset = [row for row in rows if str(row.get(field)) == level]
        out[level] = cluster_bootstrap_rate(subset, flag)
    return out
