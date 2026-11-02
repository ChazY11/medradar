"""Cluster-aware evaluation statistics for evidence-grounded forecasting.

The frozen reverse-R&D benchmark evaluates a 1.2% base-rate entry target on
41,003 rows that are *not independent*: rows repeat companies (51) and
company x track pairs (~1,900) across quarterly origins.  Two consequences
motivate this module:

1. **Rows are not i.i.d.**  A row bootstrap understates the uncertainty of an
   average-precision (AP) difference.  ``clustered_bootstrap_delta_ap``
   resamples whole clusters (company, or company x track) with replacement,
   with a fixed seed, and reports the cluster counts used.
2. **A null is not "no effect".**  With ~25 positives per holdout window the
   paired bootstrap cannot resolve small AP differences.  ``mde_from_se``
   converts an *observed* bootstrap standard error into the smallest
   detectable effect at a chosen power; ``average_precision_mde`` gives a
   design-stage estimate when only the row/positive counts are known.
3. **The benchmark requires lead time at a matched false-alarm rate.**  The
   existing evaluation code has no matched-FAR metric; ``matched_far_lead_time``
   implements it and reports undetected/censored positives instead of dropping
   them.

Canonical metric definitions live in :mod:`medradar.intelligence.evaluation.metrics`
(``pr_auc``, ``brier``, ``ece``).  This module **re-exports** ``pr_auc`` as
``average_precision`` and never redefines it: the bootstrap engine evaluates the
identical tie-aware step formula on the resampled row multiset, and
:func:`average_precision_weighted` is proven equal to ``pr_auc`` on duplicated
rows in the tests.

Everything here is pure Python (standard library + this package), deterministic
under an explicit seed, and returns plain ``dict``/``list``/``float``/``None``
values that are JSON-ready.  There is no I/O.  Nothing here is a causal claim:
the intervals describe sampling variability of a metric on the data at hand.
"""
from __future__ import annotations

import math
import random
from typing import Any, Iterable, Mapping, Sequence

from ..stats import normal_cdf, normal_ppf
from ..util import parse_date
from .evaluation.metrics import brier, ece, pr_auc

# The one canonical average-precision implementation, re-exported (not forked).
average_precision = pr_auc

DEFAULT_SEED = 7
DEFAULT_RESAMPLES = 2000
DEFAULT_CONFIDENCE = 0.95
DEFAULT_ALPHA = 0.05
DEFAULT_POWER = 0.8

__all__ = [
    "average_precision",
    "average_precision_weighted",
    "clustered_bootstrap_delta_ap",
    "clustered_bootstrap_metric_ci",
    "clustered_bootstrap_ece_ci",
    "clustered_bootstrap_brier_ci",
    "mde_from_se",
    "power_at_delta",
    "average_precision_mde",
    "ap_mde_calibration",
    "matched_far_lead_time",
    # Stable integration names used by the cycle-2 analysis stage (see bottom).
    "cluster_bootstrap_delta_ap",
    "minimum_detectable_delta_ap",
    "lead_time_at_matched_false_alarm",
    "bootstrap_ci_metric",
]


# --------------------------------------------------------------------- helpers
def _as_vectors(labels: Sequence[Any], probabilities: Sequence[Any]) -> tuple[list[int], list[float]]:
    """Validate/coerce a label vector and a probability vector."""
    label_list = list(labels)
    probability_list = list(probabilities)
    if len(label_list) != len(probability_list):
        raise ValueError("labels and probabilities must be aligned")
    clean_labels: list[int] = []
    clean_probabilities: list[float] = []
    for index, (label, probability) in enumerate(zip(label_list, probability_list)):
        if isinstance(label, bool):
            clean_label = int(label)
        elif isinstance(label, (int, float)) and int(label) == label:
            clean_label = int(label)
        else:
            raise ValueError(f"label at row {index} is not 0/1: {label!r}")
        if clean_label not in (0, 1):
            raise ValueError(f"label at row {index} is not 0/1: {label!r}")
        try:
            value = float(probability)
        except (TypeError, ValueError) as error:
            raise ValueError(f"probability at row {index} is not numeric: {probability!r}") from error
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"probability at row {index} is not finite: {probability!r}")
        clean_labels.append(clean_label)
        clean_probabilities.append(value)
    return clean_labels, clean_probabilities


def _cluster_index(clusters: Sequence[Any] | None, n: int) -> tuple[list[int], int, str]:
    """Map every row to a cluster index; cluster ids are canonicalised by repr.

    ``clusters=None`` makes every row its own cluster (the classic i.i.d.
    bootstrap) *and says so* in the returned method string, so a report never
    silently claims a cluster-robust interval it did not compute.
    """
    if clusters is None:
        return list(range(n)), n, "iid_row"
    values = list(clusters)
    if len(values) != n:
        raise ValueError("clusters must align with labels (one cluster id per row)")
    mapping: dict[tuple[str, str], int] = {}
    row_cluster: list[int] = []
    for value in values:
        key = (type(value).__name__, repr(value))
        if key not in mapping:
            mapping[key] = len(mapping)
        row_cluster.append(mapping[key])
    return row_cluster, len(mapping), "cluster"


def _percentile(sorted_draws: Sequence[float], index: int) -> float:
    return sorted_draws[min(len(sorted_draws) - 1, max(0, index))]


def _interval(sorted_draws: Sequence[float], confidence: float) -> tuple[float, float]:
    """Percentile interval using the repo's existing ``int(q * size)`` convention.

    This matches :func:`medradar.intelligence.evaluation.metrics.paired_bootstrap_delta_ap`
    and :func:`medradar.util.bootstrap_ci` so a report can mix the three without
    re-explaining the endpoints.
    """
    size = len(sorted_draws)
    low = _percentile(sorted_draws, int((1.0 - confidence) / 2.0 * size))
    high = _percentile(sorted_draws, int((1.0 + confidence) / 2.0 * size))
    return low, high


def _draw_weights(cluster_index: Sequence[int], n_clusters: int, rng: random.Random) -> list[int]:
    """Cluster-bootstrap multiplicities: draw ``n_clusters`` clusters with replacement."""
    multiplicities = [0] * n_clusters
    for _ in range(n_clusters):
        multiplicities[rng.randrange(n_clusters)] += 1
    return multiplicities


# -------------------------------------------------------------- average precision
def average_precision_weighted(
    labels: Sequence[Any],
    probabilities: Sequence[Any],
    weights: Sequence[Any],
) -> float | None:
    """Average precision of ``(labels, probabilities)`` with integer row weights.

    This is the resampling engine's definition of the same statistic as
    :func:`medradar.intelligence.evaluation.metrics.pr_auc`: duplicates a row
    ``weights[i]`` times, ranks by score descending, treats equal scores as one
    threshold, and accumulates ``(recall increment) x (precision at threshold)``.
    The tests assert it equals ``pr_auc`` on materialised duplicates.  Returns
    ``None`` when the weighted sample has one label class only (matching
    ``pr_auc``'s empty/precision-undefined convention), and raises on negative
    or non-integer weights.
    """
    label_list, probability_list = _as_vectors(labels, probabilities)
    weight_list = list(weights)
    if len(weight_list) != len(label_list):
        raise ValueError("weights must align with labels")
    for index, weight in enumerate(weight_list):
        if isinstance(weight, bool) or not isinstance(weight, int) or weight < 0:
            raise ValueError(f"weight at row {index} must be a non-negative integer: {weight!r}")
    total = sum(weight_list)
    if total == 0:
        return None
    positives = sum(label * weight for label, weight in zip(label_list, weight_list))
    if positives == 0 or positives == total:
        return None
    order = sorted(range(len(label_list)), key=lambda i: (-probability_list[i], i))
    ordered_labels = [label_list[index] for index in order]
    ordered_weights = [weight_list[index] for index in order]
    # Tie-block ends: a block is the maximal run of equal scores.
    block_ends = [True] * len(order)
    for position in range(len(order) - 1):
        block_ends[position] = probability_list[order[position]] != probability_list[order[position + 1]]
    return _ap_from_ordered(ordered_labels, ordered_weights, block_ends, positives_override=positives)


def _ap_from_ordered(
    ordered_labels: Sequence[int],
    ordered_weights: Sequence[int],
    block_ends: Sequence[bool],
    *,
    positives_override: int | None = None,
) -> float | None:
    """Evaluate the tie-aware step AP on an already-ranked weighted row multiset."""
    true_positives = 0
    false_positives = 0
    positives = 0
    rows = 0
    area = 0.0
    block_true = 0
    block_false = 0
    for label, weight, end in zip(ordered_labels, ordered_weights, block_ends):
        if weight:
            rows += weight
            if label:
                block_true += weight
            else:
                block_false += weight
        if end:
            if block_true or block_false:
                true_positives += block_true
                false_positives += block_false
                positives += block_true
                if block_true:
                    area += block_true * (true_positives / (true_positives + false_positives))
            block_true = 0
            block_false = 0
    if rows == 0:
        return None
    expected_positives = positives if positives_override is None else positives_override
    if expected_positives == 0 or expected_positives >= rows:
        return None
    return area / expected_positives


def _prepare_metric(probabilities: Sequence[float], labels: Sequence[int], metric: str) -> dict[str, Any]:
    """Precompute the arrays a resampled metric evaluation needs."""
    n = len(probabilities)
    if metric == "average_precision":
        order = sorted(range(n), key=lambda i: (-probabilities[i], i))
        block_ends = [True] * n
        for position in range(n - 1):
            block_ends[position] = probabilities[order[position]] != probabilities[order[position + 1]]
        return {
            "kind": "rank",
            "order": order,
            "ordered_labels": [labels[index] for index in order],
            "ordered_probabilities": [probabilities[index] for index in order],
            "block_ends": block_ends,
        }
    if metric == "brier":
        return {"kind": "brier", "lots": [(p - y) ** 2 for p, y in zip(probabilities, labels)]}
    if metric == "ece":
        bins = 10
        bin_of = []
        for p in probabilities:
            if p == 1.0:
                bin_of.append(bins - 1)
            else:
                index = int(p * bins)
                bin_of.append(min(bins - 1, max(0, index)))
        return {"kind": "ece", "bin_of": bin_of, "probabilities": list(probabilities),
                "labels": list(labels), "bins": bins}
    raise ValueError(f"unknown metric: {metric!r}")


def _metric_on_clusters(prepared: Mapping[str, Any], cluster_index: Sequence[int],
                        multiplicities: Sequence[int], metric: str) -> float | None:
    """Compute one metric on the row multiset defined by cluster multiplicities."""
    weights = [multiplicities[cluster] for cluster in cluster_index]
    rows = sum(weights)
    if rows == 0:
        return None
    if prepared["kind"] == "rank":
        ordered_weights = [weights[index] for index in prepared["order"]]
        return _ap_from_ordered(prepared["ordered_labels"], ordered_weights, prepared["block_ends"])
    if prepared["kind"] == "brier":
        total = 0.0
        for weight, lot in zip(weights, prepared["lots"]):
            if weight:
                total += weight * lot
        return total / rows
    if prepared["kind"] == "ece":
        bins = prepared["bins"]
        counts = [0] * bins
        probability_sums = [0.0] * bins
        label_sums = [0] * bins
        for weight, bin_index, probability, label in zip(
                weights, prepared["bin_of"], prepared["probabilities"], prepared["labels"]):
            if weight:
                counts[bin_index] += weight
                probability_sums[bin_index] += weight * probability
                label_sums[bin_index] += weight * label
        error = 0.0
        for count, probability_sum, label_sum in zip(counts, probability_sums, label_sums):
            if count:
                confidence = probability_sum / count
                accuracy = label_sum / count
                error += count / rows * abs(confidence - accuracy)
        return error
    raise ValueError(f"unknown prepared metric kind: {prepared['kind']!r}")


# ------------------------------------------------------------ cluster bootstrap
def clustered_bootstrap_delta_ap(
    labels: Sequence[Any],
    probabilities_a: Sequence[Any],
    probabilities_b: Sequence[Any],
    clusters: Sequence[Any] | None = None,
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    confidence: float = DEFAULT_CONFIDENCE,
) -> dict[str, Any]:
    """Cluster-bootstrap percentile CI for ``AP(a) - AP(b)`` on paired rows.

    The pairing is preserved: every resampled row is scored by *both* predictors,
    and whole clusters (company, or company x track) are drawn with replacement.
    A resample whose labels are all positive or all negative has undefined AP and
    is skipped (the point metric returns ``None`` there too); the number skipped
    is reported rather than silently changing the denominator.

    Sampling model: rows inside a cluster are correlated, clusters are treated as
    exchangeable and independent.  Validity is asymptotic in the number of
    **clusters**, so fewer than two clusters (or no valid resample) returns
    ``ci_low = ci_high = None`` instead of a fake interval.  Passing
    ``clusters=None`` degenerates to the i.i.d. row bootstrap and the payload says
    ``cluster_method = "iid_row"`` -- it is not cluster-robust.

    Deterministic: same inputs + ``seed`` -> byte-identical output.  The interval
    is a percentile interval (not a Bayesian posterior and not bias-corrected).
    Cost is O(resamples x n_rows); see docs/research/EVALSTATS.md for measured
    runtimes on the 41,003-row entry dataset.
    """
    if resamples <= 0:
        raise ValueError("resamples must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    label_list, probs_a = _as_vectors(labels, probabilities_a)
    label_list_b, probs_b = _as_vectors(labels, probabilities_b)
    if len(label_list) != len(label_list_b):
        raise ValueError("labels and both probability lists must be aligned")
    n = len(label_list)
    cluster_index, n_clusters, cluster_method = _cluster_index(clusters, n)
    point_first = pr_auc(label_list, probs_a)
    point_second = pr_auc(label_list, probs_b)
    point_delta = (point_first - point_second
                   if point_first is not None and point_second is not None else None)
    result: dict[str, Any] = {
        "metric": "average_precision_delta",
        "cluster_method": cluster_method,
        "n_rows": n,
        "n_positives": sum(label_list),
        "n_clusters": n_clusters,
        "resamples": int(resamples),
        "valid_resamples": 0,
        "skipped_resamples": 0,
        "seed": int(seed),
        "confidence_level": confidence,
        "interval": "percentile",
        "delta": point_delta,
        "point_delta": point_delta,
        "mean_delta": None,
        "se_delta": None,
        "ci_low": None,
        "ci_high": None,
        "p_delta_le_zero": None,
    }
    if n == 0:
        result["note"] = "empty input: no rows to resample"
        return result
    if n_clusters < 2:
        result["note"] = "fewer than 2 clusters: no cluster-robust interval is reported"
        return result
    prepared_a = _prepare_metric(probs_a, label_list, "average_precision")
    prepared_b = _prepare_metric(probs_b, label_list, "average_precision")
    rng = random.Random(seed)
    draws: list[float] = []
    skipped = 0
    for _ in range(int(resamples)):
        multiplicities = _draw_weights(cluster_index, n_clusters, rng)
        first = _metric_on_clusters(prepared_a, cluster_index, multiplicities, "average_precision")
        second = _metric_on_clusters(prepared_b, cluster_index, multiplicities, "average_precision")
        if first is None or second is None:
            skipped += 1
            continue
        draws.append(first - second)
    result["valid_resamples"] = len(draws)
    result["skipped_resamples"] = skipped
    if not draws:
        result["note"] = "every resample had a single label class: interval undefined"
        return result
    draws.sort()
    size = len(draws)
    mean = sum(draws) / size
    variance = sum((value - mean) ** 2 for value in draws) / size
    result["mean_delta"] = mean
    result["se_delta"] = math.sqrt(variance)
    result["ci_low"], result["ci_high"] = _interval(draws, confidence)
    result["p_delta_le_zero"] = sum(1 for value in draws if value <= 0.0) / size
    return result


def clustered_bootstrap_metric_ci(
    labels: Sequence[Any],
    probabilities: Sequence[Any],
    clusters: Sequence[Any] | None = None,
    *,
    metric: str = "brier",
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    confidence: float = DEFAULT_CONFIDENCE,
) -> dict[str, Any]:
    """Cluster-bootstrap percentile CI for one metric (``"brier"`` or ``"ece"``).

    The point value is computed with the canonical implementation
    (:func:`medradar.intelligence.evaluation.metrics.brier` /
    ``ece``) and the resampled values use the identical formula on the row
    multiset; the two agree on the observed data by construction.  Cluster
    semantics, determinism and degenerate-case behaviour match
    :func:`clustered_bootstrap_delta_ap`: fewer than two clusters -> no interval.
    """
    if metric not in ("brier", "ece"):
        raise ValueError("metric must be 'brier' or 'ece' (use clustered_bootstrap_delta_ap for AP)")
    if resamples <= 0:
        raise ValueError("resamples must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    label_list, probability_list = _as_vectors(labels, probabilities)
    n = len(label_list)
    cluster_index, n_clusters, cluster_method = _cluster_index(clusters, n)
    point = brier(label_list, probability_list) if metric == "brier" else ece(label_list, probability_list)
    result: dict[str, Any] = {
        "metric": metric,
        "cluster_method": cluster_method,
        "n_rows": n,
        "n_positives": sum(label_list),
        "n_clusters": n_clusters,
        "resamples": int(resamples),
        "valid_resamples": 0,
        "skipped_resamples": 0,
        "seed": int(seed),
        "confidence_level": confidence,
        "interval": "percentile",
        "point": point,
        "mean": None,
        "se": None,
        "ci_low": None,
        "ci_high": None,
    }
    if n == 0:
        result["note"] = "empty input: no rows to resample"
        return result
    if n_clusters < 2:
        result["note"] = "fewer than 2 clusters: no cluster-robust interval is reported"
        return result
    prepared = _prepare_metric(probability_list, label_list, metric)
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(int(resamples)):
        multiplicities = _draw_weights(cluster_index, n_clusters, rng)
        value = _metric_on_clusters(prepared, cluster_index, multiplicities, metric)
        if value is not None:
            draws.append(value)
    result["valid_resamples"] = len(draws)
    result["skipped_resamples"] = int(resamples) - len(draws)
    if not draws:
        result["note"] = "no valid resample"
        return result
    draws.sort()
    size = len(draws)
    mean = sum(draws) / size
    result["mean"] = mean
    result["se"] = math.sqrt(sum((value - mean) ** 2 for value in draws) / size)
    result["ci_low"], result["ci_high"] = _interval(draws, confidence)
    result["note"] = "percentile cluster bootstrap; not bias-corrected"
    return result


def clustered_bootstrap_ece_ci(
    labels: Sequence[Any],
    probabilities: Sequence[Any],
    clusters: Sequence[Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Cluster-bootstrap CI for expected calibration error (10 equal-width bins)."""
    return clustered_bootstrap_metric_ci(labels, probabilities, clusters, metric="ece", **kwargs)


def clustered_bootstrap_brier_ci(
    labels: Sequence[Any],
    probabilities: Sequence[Any],
    clusters: Sequence[Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Cluster-bootstrap CI for the Brier score."""
    return clustered_bootstrap_metric_ci(labels, probabilities, clusters, metric="brier", **kwargs)


# ------------------------------------------------------------------- power / MDE
def _z_pair(alpha: float, power: float) -> tuple[float, float]:
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    if not 0.0 < power < 1.0:
        raise ValueError("power must be in (0, 1)")
    z_alpha = normal_ppf(1.0 - alpha / 2.0)
    z_power = normal_ppf(power)
    if z_alpha is None or z_power is None:
        raise ValueError("alpha/power outside the normal quantile range")
    return z_alpha, z_power


def power_at_delta(
    delta: float,
    se_delta_ap: float,
    *,
    alpha: float = DEFAULT_ALPHA,
) -> float | None:
    """Two-sided normal-approximation power to detect ``|delta|`` given its SE.

    ``power = Phi(|delta|/SE - z_{1-alpha/2}) + Phi(-|delta|/SE - z_{1-alpha/2})``.
    Approximate: assumes a symmetric, roughly normal bootstrap distribution of the
    AP difference with the supplied standard error.
    """
    z_alpha, _ = _z_pair(alpha, 0.5)
    if se_delta_ap is None or se_delta_ap <= 0 or delta is None:
        return None
    ratio = abs(float(delta)) / float(se_delta_ap)
    return normal_cdf(ratio - z_alpha) + normal_cdf(-ratio - z_alpha)


def mde_from_se(
    se_delta_ap: float,
    *,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
) -> dict[str, Any]:
    """Minimum detectable AP difference from an observed bootstrap SE.

    ``MDE = (z_{1-alpha/2} + z_{power}) * SE`` (two-sided test, normal
    approximation).  This is the **preferred** route: feed it
    ``clustered_bootstrap_delta_ap(...)["se_delta"]`` from the actual holdout, so
    the design effect of the real score distribution is included.  The formula
    assumes the delta-AP sampling distribution is approximately normal and
    symmetric; the bootstrap interval it is paired with should be inspected.
    """
    if se_delta_ap is None or not math.isfinite(float(se_delta_ap)) or float(se_delta_ap) <= 0:
        raise ValueError("se_delta_ap must be a positive finite number")
    z_alpha, z_power = _z_pair(alpha, power)
    se = float(se_delta_ap)
    return {
        "se_delta_ap": se,
        "mde_delta_ap": (z_alpha + z_power) * se,
        "alpha": float(alpha),
        "power": float(power),
        "z_alpha": z_alpha,
        "z_power": z_power,
        "approximation": "normal_two_sided",
        "exact": False,
        "notes": [
            "MDE assumes the bootstrap distribution of the AP difference is roughly normal and symmetric.",
            "The SE must come from the same clustered resampling model as the interval that is reported.",
        ],
    }


def _ap_from_positive_ranks(ranks: Sequence[int]) -> float:
    """AP when the positives occupy the given 1-based ranks (1 = highest score).

    With continuous (tie-free) scores, ``pr_auc`` equals
    ``(1/k) * sum_j j / r_j`` over the sorted positive ranks ``r_1 < ... < r_k``:
    at the j-th positive the threshold contains ``j`` positives and ``r_j - j``
    negatives, so precision is ``j / r_j`` and the recall increment is ``1/k``.
    This is the same tie-aware step formula as ``pr_auc`` in the tie-free case and
    lets the null simulation cost O(k log k) instead of O(n log n).
    """
    ordered = sorted(ranks)
    total = 0.0
    for position, rank in enumerate(ordered, start=1):
        total += position / rank
    return total / len(ordered)


def _null_delta_ap_draws(
    n_rows: int,
    n_positives: int,
    scorer_rank_correlation: float,
    trials: int,
    seed: int,
) -> list[float]:
    """Monte-Carlo null draws of AP(a) - AP(b) for label-independent scores.

    When the two scorers are independent (``scorer_rank_correlation == 0``, the
    default) the score ranks are two independent uniform ``n_positives``-subsets
    of ``{1..n_rows}`` and the AP difference is simulated exactly and cheaply in
    rank space: ``O(trials * n_positives log n_positives)``.

    For a positive correlation the scores are drawn from a Gaussian copula with
    Pearson correlation ``scorer_rank_correlation`` (not exactly the rank
    correlation), which costs ``O(trials * n_rows log n_rows)``; both scores stay
    independent of the labels, so the labels are fixed.
    """
    if scorer_rank_correlation == 0.0:
        rng = random.Random(seed)
        population = range(1, n_rows + 1)
        draws: list[float] = []
        for _ in range(int(trials)):
            ranks_a = rng.sample(population, n_positives)
            ranks_b = rng.sample(population, n_positives)
            draws.append(_ap_from_positive_ranks(ranks_a) - _ap_from_positive_ranks(ranks_b))
        return draws
    rng = random.Random(seed)
    labels = [1] * n_positives + [0] * (n_rows - n_positives)
    root = math.sqrt(scorer_rank_correlation)
    noise = math.sqrt(max(0.0, 1.0 - scorer_rank_correlation))
    draws = []
    for _ in range(int(trials)):
        shared = [rng.gauss(0.0, 1.0) for _ in range(n_rows)]
        scores_a = [root * shared[index] + noise * rng.gauss(0.0, 1.0) for index in range(n_rows)]
        scores_b = [root * shared[index] + noise * rng.gauss(0.0, 1.0) for index in range(n_rows)]
        first = pr_auc(labels, scores_a)
        second = pr_auc(labels, scores_b)
        if first is not None and second is not None:
            draws.append(first - second)
    return draws


def average_precision_mde(
    n_rows: int,
    n_positives: int,
    *,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    assumed_ap: float | None = None,
    scorer_correlation: float = 0.0,
    observed_delta: float | None = None,
    resamples: int = 1000,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Design-stage minimum detectable AP difference (analytic approximation).

    Approximation (labelled ``approximate``, not exact)::

        Var(AP)          ~= m (1 - m) / n_positives        [plug-in binomial-style]
        Var(AP_a - AP_b) ~= 2 (1 - rho) Var(AP)            [paired, correlation rho]
        SE               = sqrt(Var(delta))
        MDE              = (z_{1-alpha/2} + z_{power}) * SE

    ``m`` is ``assumed_ap`` when supplied.  Otherwise ``m = 0.5``, which maximises
    ``m(1-m)`` and therefore returns a **conservative planning bound**: the
    headline ``mde`` is an upper bound on the smallest detectable difference, so an
    observed delta below it is consistent with an underpowered study and must not
    be read as proof of no effect.  ``scorer_correlation`` defaults to 0 (the
    conservative choice for positively correlated scorers).

    Why a conservative analytic bound and not only the no-skill simulation: an AP
    difference is much less variable when both scorers are near-random than when
    they carry real, heterogeneous ranking skill (an empirical fact demonstrated by
    :func:`ap_mde_calibration`).  The cheap exact-within-model null simulation is
    still reported as ``se_delta_ap_null_simulation`` /
    ``mde_delta_ap_null_simulation`` and is a **lower bound**; it must not be used
    as the planning MDE because it overstates power.  The authoritative route is
    :func:`mde_from_se` with the observed clustered bootstrap SE from
    ``clustered_bootstrap_delta_ap(...)["se_delta"]``.

    Monotone: with ``assumed_ap`` fixed, ``mde`` decreases strictly in
    ``n_positives`` (``1/sqrt(n_positives)``).  Deterministic.
    """
    if not isinstance(n_rows, int) or isinstance(n_rows, bool) or n_rows < 2:
        raise ValueError("n_rows must be an integer >= 2")
    if not isinstance(n_positives, int) or isinstance(n_positives, bool):
        raise ValueError("n_positives must be an integer")
    if not 0 < n_positives < n_rows:
        raise ValueError("need 0 < n_positives < n_rows for a defined average precision")
    if not 0.0 <= scorer_correlation < 1.0:
        raise ValueError("scorer_correlation must be in [0, 1)")
    if assumed_ap is not None and not 0.0 < float(assumed_ap) < 1.0:
        raise ValueError("assumed_ap must be in (0, 1) when supplied")
    if resamples < 2:
        raise ValueError("resamples must be >= 2")
    z_alpha, z_power = _z_pair(alpha, power)
    chosen_ap = 0.5 if assumed_ap is None else float(assumed_ap)
    variance_ap = chosen_ap * (1.0 - chosen_ap) / n_positives
    variance_delta = 2.0 * (1.0 - scorer_correlation) * variance_ap
    se = math.sqrt(variance_delta)
    mde = (z_alpha + z_power) * se
    null_draws = _null_delta_ap_draws(n_rows, n_positives, 0.0, resamples, seed)
    null_se = None
    null_mde = None
    if len(null_draws) >= 2:
        mean_null = sum(null_draws) / len(null_draws)
        null_variance = sum((value - mean_null) ** 2 for value in null_draws) / (len(null_draws) - 1)
        null_se = math.sqrt(null_variance)
        null_mde = (z_alpha + z_power) * null_se
    return {
        "model": "plug_in_binomial_ap_variance",
        "n_rows": n_rows,
        "n_positives": n_positives,
        "base_rate": n_positives / n_rows,
        "alpha": float(alpha),
        "power": float(power),
        "z_alpha": z_alpha,
        "z_power": z_power,
        "mde": mde,
        "mde_delta_ap": mde,
        "se": se,
        "se_delta_ap": se,
        "assumed_ap": chosen_ap,
        "assumed_ap_is_worst_case": assumed_ap is None,
        "scorer_correlation": float(scorer_correlation),
        "variance_ap_approximation": variance_ap,
        "variance_delta_approximation": variance_delta,
        "se_delta_ap_null_simulation": null_se,
        "mde_delta_ap_null_simulation": null_mde,
        "null_simulation_resamples": int(resamples),
        "null_simulation_seed": int(seed),
        "power_at_observed_delta": (
            power_at_delta(observed_delta, se, alpha=alpha) if observed_delta is not None else None),
        "approximation": "plug_in_binomial_ap_variance",
        "exact": False,
        "conservative": assumed_ap is None or scorer_correlation == 0.0,
        "limitations": [
            "AP is not a binomial proportion; Var(AP) ~= m(1-m)/n_positives is a plug-in approximation, "
            "not an exact variance. With m = 0.5 it is a conservative upper bound on m(1-m).",
            "Real skill usually makes the bootstrap SE larger than the no-skill simulation (reported separately "
            "as the optimistic lower bound), which is why the analytic bound defaults to the m = 0.5 worst case.",
            "The paired correlation is assumed (default 0); positively correlated scorers have a smaller SE.",
            "The authoritative MDE uses mde_from_se(clustered_bootstrap_delta_ap(...)['se_delta']) on the "
            "actual holdout, not this design value.",
        ],
    }


def _mean_delta_ap_for_skill(
    labels: Sequence[int],
    skill: float,
    reps: int,
    rng: random.Random,
) -> float:
    """Population AP(a) - AP(b) for score_a = skill*label + noise, score_b = noise."""
    total = 0.0
    n = len(labels)
    for _ in range(int(reps)):
        scores_a = [skill * labels[index] + rng.gauss(0.0, 1.0) for index in range(n)]
        scores_b = [rng.gauss(0.0, 1.0) for _ in range(n)]
        total += pr_auc(labels, scores_a) - pr_auc(labels, scores_b)
    return total / reps


def ap_mde_calibration(
    n_rows: int,
    n_positives: int,
    *,
    assumed_ap: float | None = None,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    scorer_correlation: float = 0.0,
    reps: int = 40,
    bootstrap_resamples: int = 100,
    search_reps: int = 20,
    search_steps: int = 7,
    null_trials: int = 500,
    null_reps: int = 200,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Empirical calibration check of the design MDE on synthetic data.

    Two checks, both deterministic under ``seed``:

    1. **Null-simulation check.**  ``null_se_ratio`` compares the rank-space null
       SE reported by :func:`average_precision_mde`
       (``se_delta_ap_null_simulation``) with the Monte-Carlo SD of the AP
       difference across ``reps`` fresh no-skill datasets.  A ratio near 1 says the
       cheap null simulation is correct within its model.
    2. **Known-effect power check.**  Simulate paired scores with a *known* ranking
       skill (score_a = ``skill`` * label + noise, score_b = noise) and calibrate
       ``skill`` by bisection so the population AP difference equals the MDE
       reported by :func:`average_precision_mde`.  The achieved power is the
       fraction of ``reps`` replicates whose 95% paired-bootstrap interval excludes
       zero; it is compared with the nominal ``power`` and with the normal-
       approximation power predicted from the median replicate bootstrap SE.
       ``consistent`` is true when the reported MDE is detected at least at
       ``power - 0.15`` and the achieved/predicted powers agree within 0.2.

    This is a synthetic self-check of the formulas, not calibration on real data.
    The known effect size is measured (the mean AP difference the calibrated skill
    produces), not imposed.  Cost is O(reps x bootstrap_resamples x n_rows) plus
    the bisection search; typical test-scale settings run in well under a second.
    """
    if reps < 2 or bootstrap_resamples < 10 or search_reps < 2 or search_steps < 1:
        raise ValueError("need reps >= 2, bootstrap_resamples >= 10, search_reps >= 2, search_steps >= 1")
    if null_reps < 2:
        raise ValueError("null_reps must be >= 2")
    design = average_precision_mde(
        n_rows, n_positives, alpha=alpha, power=power, assumed_ap=assumed_ap,
        scorer_correlation=scorer_correlation, resamples=null_trials, seed=seed)
    z_alpha, z_power = _z_pair(alpha, power)
    labels = [1] * n_positives + [0] * (n_rows - n_positives)
    base_rate = n_positives / n_rows

    # Check 1: the rank-space null simulation matches a full Gaussian null MC.
    rng_null = random.Random(seed + 101)
    null_deltas: list[float] = []
    for _ in range(int(null_reps)):
        scores_a = [rng_null.gauss(0.0, 1.0) for _ in range(n_rows)]
        scores_b = [rng_null.gauss(0.0, 1.0) for _ in range(n_rows)]
        first, second = pr_auc(labels, scores_a), pr_auc(labels, scores_b)
        if first is not None and second is not None:
            null_deltas.append(first - second)
    null_mc_sd = None
    null_se_ratio = None
    if len(null_deltas) > 1:
        mean_null = sum(null_deltas) / len(null_deltas)
        null_mc_sd = math.sqrt(sum((value - mean_null) ** 2 for value in null_deltas)
                               / (len(null_deltas) - 1))
        simulated = design["se_delta_ap_null_simulation"]
        if simulated is not None and null_mc_sd:
            null_se_ratio = simulated / null_mc_sd

    # Check 2a: calibrate the skill knob so the known effect equals the reported MDE.
    target = design["mde_delta_ap"]
    rng_search = random.Random(seed + 202)
    low, high = 0.0, 8.0
    for _ in range(int(search_steps)):
        middle = 0.5 * (low + high)
        observed = _mean_delta_ap_for_skill(labels, middle, search_reps, rng_search)
        if observed < target:
            low = middle
        else:
            high = middle
    calibrated_skill = 0.5 * (low + high)
    realized_delta = _mean_delta_ap_for_skill(labels, calibrated_skill, max(reps, search_reps), rng_search)

    # Check 2b: power of the paired bootstrap at that known effect.
    rng_power = random.Random(seed + 303)
    deltas: list[float] = []
    bootstrap_ses: list[float] = []
    rejections = 0
    for replicate in range(int(reps)):
        scores_a = [calibrated_skill * labels[index] + rng_power.gauss(0.0, 1.0)
                    for index in range(n_rows)]
        scores_b = [rng_power.gauss(0.0, 1.0) for _ in range(n_rows)]
        point = pr_auc(labels, scores_a) - pr_auc(labels, scores_b)
        deltas.append(point)
        boot = clustered_bootstrap_delta_ap(
            labels, scores_a, scores_b, None,
            resamples=bootstrap_resamples, seed=seed + replicate, confidence=1.0 - alpha)
        bootstrap_ses.append(boot["se_delta"] if boot["se_delta"] is not None else 0.0)
        if boot["ci_low"] is not None and (boot["ci_low"] > 0.0 or boot["ci_high"] < 0.0):
            rejections += 1
    mean_delta = sum(deltas) / len(deltas)
    ordered_ses = sorted(bootstrap_ses)
    median_boot_se = ordered_ses[len(ordered_ses) // 2] if ordered_ses else 0.0
    empirical_mde = (z_alpha + z_power) * median_boot_se if median_boot_se > 0 else None
    predicted_power = (power_at_delta(mean_delta, median_boot_se, alpha=alpha)
                       if median_boot_se > 0 else None)
    achieved_power = rejections / len(deltas)
    power_check_ok = achieved_power >= float(power) - 0.15
    formula_check_ok = (predicted_power is not None
                        and abs(achieved_power - predicted_power) <= 0.2)
    return {
        "model": "synthetic_known_effect_with_skill",
        "n_rows": n_rows,
        "n_positives": n_positives,
        "base_rate": base_rate,
        "alpha": float(alpha),
        "target_power": float(power),
        "assumed_ap": design["assumed_ap"],
        "scorer_correlation": float(scorer_correlation),
        "design_mde_delta_ap": target,
        "design_se_delta_ap": design["se_delta_ap"],
        "design_mde_null_simulation": design["mde_delta_ap_null_simulation"],
        "null_mc_sd_delta_ap": null_mc_sd,
        "null_se_ratio": null_se_ratio,
        "calibrated_skill": calibrated_skill,
        "known_effect_mean_delta_ap": mean_delta,
        "realized_delta_ap": realized_delta,
        "target_effect_reached": abs(mean_delta - target) <= max(0.03, 0.20 * abs(target)),
        "median_bootstrap_se": median_boot_se,
        "empirical_mde_delta_ap": empirical_mde,
        "empirical_over_design_mde": (
            empirical_mde / target if empirical_mde is not None and target else None),
        "achieved_power": achieved_power,
        "predicted_power_from_bootstrap_se": predicted_power,
        "power_check_ok": power_check_ok,
        "formula_check_ok": formula_check_ok,
        "consistent": bool(power_check_ok and formula_check_ok),
        "reps": int(reps),
        "bootstrap_resamples": int(bootstrap_resamples),
        "null_trials": int(null_trials),
        "null_reps": int(null_reps),
        "seed": int(seed),
        "checks": {
            "null_simulation": "null_se_ratio near 1 validates the cheap rank-space null simulation",
            "known_effect_power": "achieved_power >= target_power - 0.15 validates that the reported MDE is detectable",
            "normal_formula": "achieved vs predicted power within 0.2 validates the normal-approximation conversion",
        },
        "limitations": [
            "Synthetic Gaussian-noise scores; real score distributions can change the variance.",
            "The known effect is realized by one data-generating family (skill * label + noise); other "
            "effect geometries can have different bootstrap variance at the same population delta AP.",
        ],
    }


# -------------------------------------------------------- matched-FAR lead time
def _lead_records(
    units: Sequence[Mapping[str, Any]],
    *,
    scores: Sequence[str],
    label_key: str,
    event_date_key: str,
    origin_date_key: str,
    censor_date_key: str | None,
    unit_id_key: str | None,
) -> dict[str, Any]:
    """Validate and normalise per-unit records; returns parsed parallel arrays."""
    n = len(units)
    if n == 0:
        raise ValueError("matched_far_lead_time needs at least one unit")
    labels: list[int] = []
    score_vectors: dict[str, list[float]] = {name: [] for name in scores}
    event_dates: list[Any] = []
    origin_dates: list[Any] = []
    censor_dates: list[Any] = []
    ids: list[str] = []
    for index, unit in enumerate(units):
        if not isinstance(unit, Mapping):
            raise ValueError(f"unit {index} is not a mapping")
        if label_key not in unit:
            raise ValueError(f"unit {index} is missing {label_key!r}")
        raw_label = unit[label_key]
        if isinstance(raw_label, bool):
            label = int(raw_label)
        elif isinstance(raw_label, (int, float)) and int(raw_label) == raw_label:
            label = int(raw_label)
        else:
            raise ValueError(f"unit {index} label is not 0/1: {raw_label!r}")
        if label not in (0, 1):
            raise ValueError(f"unit {index} label is not 0/1: {raw_label!r}")
        labels.append(label)
        for name in scores:
            if name not in unit:
                raise ValueError(f"unit {index} is missing score field {name!r}")
            try:
                score_vectors[name].append(float(unit[name]))
            except (TypeError, ValueError) as error:
                raise ValueError(f"unit {index} score {name!r} is not numeric") from error
        event_dates.append(parse_date(unit.get(event_date_key)))
        origin = parse_date(unit.get(origin_date_key))
        if origin is None:
            raise ValueError(f"unit {index} is missing/unparseable {origin_date_key!r}")
        origin_dates.append(origin)
        censor = parse_date(unit.get(censor_date_key)) if censor_date_key else None
        censor_dates.append(censor)
        if unit_id_key and unit.get(unit_id_key) is not None:
            ids.append(str(unit[unit_id_key]))
        else:
            ids.append(str(index))
    return {
        "labels": labels,
        "scores": score_vectors,
        "event_dates": event_dates,
        "origin_dates": origin_dates,
        "censor_dates": censor_dates,
        "ids": ids,
    }


def _select_at_false_positive_budget(
    scores: Sequence[float],
    labels: Sequence[int],
    ids: Sequence[str],
    false_positive_budget: int,
) -> dict[str, Any]:
    """Detect positives scoring above the threshold set by an FP budget.

    Rule (explicit, symmetric across scorers): the ``m`` highest-scoring negative
    units are the ensured false alarms; a positive is *detected* iff its score is
    strictly greater than the score of the ``m``-th highest negative.  Negative
    ties at the threshold are broken by unit id so exactly ``m`` false positives
    are selected.  For ``m = 0`` the threshold is the highest negative score and
    no negative is selected.  This makes the false-positive *count* identical for
    every scorer by construction.
    """
    negatives = [(scores[index], ids[index], index) for index in range(len(labels)) if labels[index] == 0]
    if not negatives:
        raise ValueError("matched FAR is undefined: there is not a single negative unit")
    negatives.sort(key=lambda item: (-item[0], item[1], item[2]))
    m = max(0, min(int(false_positive_budget), len(negatives)))
    threshold = negatives[0][0] if m == 0 else negatives[m - 1][0]
    selected_positives = [index for index in range(len(labels))
                          if labels[index] == 1 and scores[index] > threshold]
    return {
        "threshold": threshold,
        "false_positives": m,
        "selected_positives": selected_positives,
        "selected_units": len(selected_positives) + m,
        "rule": ("threshold = m-th highest negative score (or the highest negative score when m = 0); "
                 "a positive is detected iff its score is strictly greater"),
    }


def _lead_summary(
    selected_positives: Sequence[int],
    event_dates: Sequence[Any],
    origin_dates: Sequence[Any],
    censor_dates: Sequence[Any],
) -> dict[str, Any]:
    """Lead-time summary that reports censoring instead of dropping it."""
    leads: list[int] = []
    censored = 0
    negative_lead = 0
    for index in selected_positives:
        event = event_dates[index]
        origin = origin_dates[index]
        censor = censor_dates[index]
        if event is None:
            censored += 1
            continue
        if censor is not None and event > censor:
            censored += 1
            continue
        lead = (event - origin).days
        if lead < 0:
            negative_lead += 1
            continue
        leads.append(lead)
    leads.sort()
    if leads:
        mean = sum(leads) / len(leads)
        middle = len(leads) // 2
        median = leads[middle] if len(leads) % 2 else 0.5 * (leads[middle - 1] + leads[middle])
        minimum, maximum = leads[0], leads[-1]
    else:
        mean = median = minimum = maximum = None
    return {
        "mean_lead_time_days": mean,
        "median_lead_time_days": median,
        "min_lead_time_days": minimum,
        "max_lead_time_days": maximum,
        "observed_leads": len(leads),
        "censored_detected_positives": censored,
        "negative_lead_positives": negative_lead,
    }


def matched_far_lead_time(
    units: Sequence[Mapping[str, Any]],
    *,
    scores: Sequence[str] = ("score_a", "score_b"),
    label_key: str = "label",
    event_date_key: str = "event_date",
    origin_date_key: str = "origin_date",
    censor_date_key: str | None = "censor_date",
    unit_id_key: str | None = "unit_id",
    far: float = 0.10,
    curve_fars: Iterable[float] | None = (0.01, 0.02, 0.05, 0.10, 0.20),
) -> dict[str, Any]:
    """Mean lead time at a **matched false-alarm rate** for two scorers.

    ``units`` is one mapping per candidate unit.  Required keys: the two score
    fields (default ``score_a``/``score_b``), ``label`` (1 = the target event is a
    true positive, 0 = negative), ``origin_date`` (the scoring date the lead is
    measured from), and for positives ``event_date`` (the observed target date).
    Optional: ``censor_date`` (end of follow-up) and ``unit_id`` (deterministic
    tie-break).  Dates accept anything :func:`medradar.util.parse_date` accepts.

    Matching rule: the false-alarm budget is ``m = floor(far * n_negatives)``
    false positives for **both** scorers, so their empirical false-positive rate
    is identical by construction.  A positive is detected iff it scores strictly
    above the score of the ``m``-th highest negative (see
    :func:`_select_at_false_positive_budget`).  The metric is therefore not
    "mean lead at each scorer's own threshold": the selection budgets differ, the
    false-alarm counts do not.

    Censoring is explicit.  A positive selected by a scorer contributes to the
    lead-time mean only when its event date exists and is not after
    ``censor_date``.  Selected positives that are censored (never detected within
    the follow-up) are counted in ``censored_detected_positives``; positives with
    an event *before* the origin are counted as ``negative_lead_positives``
    (look-ahead/label errors) and excluded from the mean rather than used as a
    negative lead.  Missed positives are reported as
    ``undetected_positives``; the data-level ceiling on detection is exposed as
    ``positives_without_observable_lead`` so a recall number is never read as
    100% when the follow-up cannot see every event.

    Also returns a probability-of-detection (POD) curve over ``curve_fars``: for
    each false-alarm rate, the detection probability (recall), precision and mean
    lead time of both scorers.
    """
    score_keys = list(scores)
    if len(score_keys) != 2:
        raise ValueError("scores must name exactly two per-unit score fields")
    if not 0.0 <= far <= 1.0:
        raise ValueError("far must be in [0, 1]")
    records = _lead_records(
        units, scores=score_keys, label_key=label_key, event_date_key=event_date_key,
        origin_date_key=origin_date_key, censor_date_key=censor_date_key, unit_id_key=unit_id_key)
    labels = records["labels"]
    n_positives = sum(labels)
    n_negatives = len(labels) - n_positives
    if n_negatives == 0:
        raise ValueError("matched FAR is undefined: there is not a single negative unit")
    false_positive_budget = int(math.floor(far * n_negatives + 1e-9))

    # Data-level censoring: positives with no observable event by the follow-up end.
    positives_without_observable_lead = 0
    positive_negative_lead = 0
    for index, label in enumerate(labels):
        if not label:
            continue
        event = records["event_dates"][index]
        censor = records["censor_dates"][index]
        if event is None or (censor is not None and event > censor):
            positives_without_observable_lead += 1
        elif (event - records["origin_dates"][index]).days < 0:
            positive_negative_lead += 1

    def scorer_summary(name: str, budget: int) -> dict[str, Any]:
        selection = _select_at_false_positive_budget(
            records["scores"][name], labels, records["ids"], budget)
        detected = len(selection["selected_positives"])
        lead = _lead_summary(
            selection["selected_positives"], records["event_dates"],
            records["origin_dates"], records["censor_dates"])
        selected_units = selection["selected_units"]
        return {
            "score_field": name,
            "selected_units": selected_units,
            "true_positives": detected,
            "false_positives": selection["false_positives"],
            "false_alarm_rate": (selection["false_positives"] / n_negatives
                                 if n_negatives else None),
            "precision": (detected / selected_units if selected_units else None),
            "detection_probability": (detected / n_positives if n_positives else None),
            "undetected_positives": n_positives - detected,
            "threshold": selection["threshold"],
            "threshold_rule": selection["rule"],
            "lead_time": lead,
        }

    scorer_a = scorer_summary(score_keys[0], false_positive_budget)
    scorer_b = scorer_summary(score_keys[1], false_positive_budget)

    def difference(field: str) -> float | None:
        first = scorer_a["lead_time"][field]
        second = scorer_b["lead_time"][field]
        return (first - second) if first is not None and second is not None else None

    curve: list[dict[str, Any]] = []
    for curve_far in ([] if curve_fars is None else list(curve_fars)):
        if not 0.0 <= float(curve_far) <= 1.0:
            raise ValueError(f"curve_fars value out of [0, 1]: {curve_far!r}")
        budget = int(math.floor(float(curve_far) * n_negatives + 1e-9))
        curve.append({
            "far_target": float(curve_far),
            "false_positive_budget": budget,
            score_keys[0]: scorer_summary(score_keys[0], budget),
            score_keys[1]: scorer_summary(score_keys[1], budget),
        })

    return {
        "metric": "mean_lead_time_days_at_matched_false_alarm_rate",
        "far_target": float(far),
        "matched_false_positive_count": false_positive_budget,
        "matched_false_alarm_rate": false_positive_budget / n_negatives,
        "n_units": len(labels),
        "n_positives": n_positives,
        "n_negatives": n_negatives,
        "origin_date_field": origin_date_key,
        "event_date_field": event_date_key,
        "censor_date_field": censor_date_key,
        "positives_without_observable_lead": positives_without_observable_lead,
        "positives_with_negative_lead": positive_negative_lead,
        "max_detection_probability": (
            (n_positives - positives_without_observable_lead) / n_positives if n_positives else None),
        "scorers": {score_keys[0]: scorer_a, score_keys[1]: scorer_b},
        "delta": {
            "mean_lead_time_days": difference("mean_lead_time_days"),
            "median_lead_time_days": difference("median_lead_time_days"),
            "detection_probability": (
                (scorer_a["detection_probability"] - scorer_b["detection_probability"])
                if scorer_a["detection_probability"] is not None
                and scorer_b["detection_probability"] is not None else None),
            "observed_leads": scorer_a["lead_time"]["observed_leads"] - scorer_b["lead_time"]["observed_leads"],
        },
        "pod_curve": curve,
        "notes": [
            "False positives are matched by count (floor(far * n_negatives)) for both scorers.",
            "Mean lead time is conditional on an observed, non-negative lead; censored leads are counted separately.",
            "Never-detected positives are reported as negatives of the detection metric, not silently dropped.",
        ],
    }


# ------------------------------------------------- cycle-2 integration adapters
# These names are the stable surface consumed by the cycle-2 analysis stage.  They
# are thin adapters over the functions above (no second metric definition) so an
# experiment driver never has to know the internal names.
def cluster_bootstrap_delta_ap(
    labels: Sequence[Any],
    probabilities_a: Sequence[Any],
    probabilities_b: Sequence[Any],
    clusters: Sequence[Any],
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    confidence: float = DEFAULT_CONFIDENCE,
) -> dict[str, Any]:
    """Cluster-bootstrap CI for ``AP(a) - AP(b)`` (cycle-2 integration name).

    Identical to :func:`clustered_bootstrap_delta_ap`; ``clusters`` is required
    and is a parallel list of hashable cluster ids (rows sharing an id are
    resampled together).  Returned keys include ``delta`` (= AP(a) - AP(b)),
    ``ci_low``, ``ci_high``, ``valid_resamples``, ``n_clusters``,
    ``n_positives`` and ``p_delta_le_zero``.
    """
    if clusters is None:
        raise ValueError("cluster_bootstrap_delta_ap requires a clusters list "
                         "(use clustered_bootstrap_delta_ap for the i.i.d. variant)")
    return clustered_bootstrap_delta_ap(
        labels, probabilities_a, probabilities_b, clusters,
        resamples=resamples, seed=seed, confidence=confidence)


def minimum_detectable_delta_ap(
    n_rows: int,
    n_positives: int,
    *,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    assumed_ap: float | None = None,
    scorer_correlation: float = 0.0,
    resamples: int = 1000,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Design-stage minimum detectable AP difference (cycle-2 integration name).

    ``resamples`` is the number of Monte-Carlo null draws used for the reported
    optimistic lower bound (``mde_delta_ap_null_simulation``).  The headline
    ``mde`` is the conservative analytic plug-in bound from
    :func:`average_precision_mde` (``assumed_ap = 0.5`` worst case unless
    ``assumed_ap`` is supplied), together with ``se``, ``method`` and the
    approximation metadata.

    Monotonicity: ``mde`` decreases strictly in ``n_positives`` for a fixed
    ``assumed_ap`` (proportional ``1/sqrt(n_positives)``), independent of
    ``n_rows``.  The no-skill simulated lower bound is *not* monotone when
    ``n_rows`` is held fixed while the base rate changes; prefer the headline
    ``mde`` for design comparisons.
    """
    result = average_precision_mde(
        n_rows, n_positives, alpha=alpha, power=power, assumed_ap=assumed_ap,
        scorer_correlation=scorer_correlation, resamples=resamples, seed=seed)
    result["mde"] = result["mde_delta_ap"]
    result["se"] = result["se_delta_ap"]
    result["method"] = result["approximation"]
    result["resamples"] = int(resamples)
    result["monotonicity"] = ("headline mde decreases strictly in n_positives at fixed assumed_ap; "
                              "the no-skill simulated lower bound is design-scaling dependent.")
    return result


def bootstrap_ci_metric(
    metric_fn: Any,
    labels: Sequence[Any],
    probabilities: Sequence[Any],
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    confidence: float = DEFAULT_CONFIDENCE,
) -> dict[str, Any]:
    """I.i.d. row-bootstrap percentile CI for an arbitrary metric function.

    ``metric_fn(labels, probabilities) -> float | None``; ``None`` draws are
    skipped and counted.  Intended for Brier/ECE (e.g.
    ``bootstrap_ci_metric(metrics.ece, y, p)``).  This is *not* cluster-robust:
    use :func:`clustered_bootstrap_metric_ci` when rows repeat companies/pairs.
    """
    if not callable(metric_fn):
        raise ValueError("metric_fn must be callable")
    if resamples <= 0:
        raise ValueError("resamples must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    label_list, probability_list = _as_vectors(labels, probabilities)
    n = len(label_list)
    point = metric_fn(label_list, probability_list) if n else None
    result: dict[str, Any] = {
        "metric": getattr(metric_fn, "__name__", "metric_fn"),
        "cluster_method": "iid_row",
        "n": n,
        "resamples": int(resamples),
        "valid_resamples": 0,
        "seed": int(seed),
        "confidence_level": confidence,
        "interval": "percentile",
        "point": point,
        "mean": None,
        "se": None,
        "ci_low": None,
        "ci_high": None,
    }
    if n == 0:
        result["note"] = "empty input: no rows to resample"
        return result
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(int(resamples)):
        indices = [rng.randrange(n) for _ in range(n)]
        value = metric_fn([label_list[index] for index in indices],
                          [probability_list[index] for index in indices])
        if value is None:
            continue
        value = float(value)
        if math.isfinite(value):
            draws.append(value)
    result["valid_resamples"] = len(draws)
    result["skipped_resamples"] = int(resamples) - len(draws)
    if not draws:
        result["note"] = "every resample returned an undefined metric"
        return result
    draws.sort()
    size = len(draws)
    mean = sum(draws) / size
    result["mean"] = mean
    result["se"] = math.sqrt(sum((value - mean) ** 2 for value in draws) / size)
    result["ci_low"], result["ci_high"] = _interval(draws, confidence)
    return result


def lead_time_at_matched_false_alarm(
    scores_a: Sequence[Any],
    scores_b: Sequence[Any],
    labels: Sequence[Any],
    lead_days: Sequence[Any],
    *,
    k: int | None = None,
    far: float = 0.10,
) -> dict[str, Any]:
    """Mean lead time for both scorers at the **same top-k selection size**.

    Cycle-2 integration shape (parallel arrays, no dates): ``lead_days[i]`` is the
    lead in days for a true positive and ``None`` when the unit was never detected
    within the follow-up window (censored).  ``k`` selects the same number of units
    for both scorers; by default ``k`` is read off scorer A at the pre-specified
    false-alarm rate ``far`` (the top-k cut at which scorer A accumulates
    ``floor(far * n_negatives)`` false positives).  Because the selection size is
    matched instead of the false-positive count, the two empirical FAR values can
    differ slightly; both are reported.

    Never-detected positives are counted, not dropped: selected positives with
    ``lead_days is None`` enter ``n_censored`` and are excluded from the mean lead
    (which is conditional on an observed lead), while positives never selected are
    reported as ``n_undetected``.  ``mean_lead_days`` is ``None`` when no detected
    positive has an observed lead.
    """
    if not 0.0 <= far <= 1.0:
        raise ValueError("far must be in [0, 1]")
    labels_list = list(labels)
    scores_a_list = [float(value) for value in scores_a]
    scores_b_list = [float(value) for value in scores_b]
    lead_list = list(lead_days)
    n = len(labels_list)
    if not (len(scores_a_list) == len(scores_b_list) == len(lead_list) == n):
        raise ValueError("scores_a, scores_b, labels and lead_days must be aligned")
    clean_labels: list[int] = []
    for index, label in enumerate(labels_list):
        value = int(label)
        if value not in (0, 1):
            raise ValueError(f"label at row {index} is not 0/1: {label!r}")
        clean_labels.append(value)
    clean_leads: list[int | None] = []
    for index, value in enumerate(lead_list):
        if value is None:
            clean_leads.append(None)
            continue
        clean_leads.append(int(value))
    n_positives = sum(clean_labels)
    n_negatives = n - n_positives
    if n_negatives == 0:
        raise ValueError("matched false-alarm rate is undefined: there is not a single negative unit")
    if n == 0:
        raise ValueError("lead_time_at_matched_false_alarm needs at least one unit")

    order_a = sorted(range(n), key=lambda i: (-scores_a_list[i], i))
    if k is None:
        target_fp = int(math.floor(far * n_negatives + 1e-9))
        chosen_k = 0
        false_positives = 0
        if target_fp <= 0:
            for index in order_a:
                if clean_labels[index]:
                    chosen_k += 1
                else:
                    break
        else:
            for index in order_a:
                chosen_k += 1
                if not clean_labels[index]:
                    false_positives += 1
                    if false_positives >= target_fp:
                        break
        k = chosen_k
    if not isinstance(k, int) or isinstance(k, bool) or k < 0 or k > n:
        raise ValueError("k must be an integer in [0, n]")

    def summary(scores: Sequence[float], name: str) -> dict[str, Any]:
        order = sorted(range(n), key=lambda i: (-scores[i], i))
        selected = order[:k]
        detected = [index for index in selected if clean_labels[index]]
        censored = sum(1 for index in detected if clean_leads[index] is None)
        observed = [clean_leads[index] for index in detected if clean_leads[index] is not None]
        mean_lead = sum(observed) / len(observed) if observed else None
        false_positives = k - len(detected)
        return {
            "score_field": name,
            "k": k,
            "n_detected": len(detected),
            "n_censored": censored,
            "n_undetected": n_positives - len(detected),
            "false_positives": false_positives,
            "far": false_positives / n_negatives,
            "mean_lead_days": mean_lead,
            "observed_leads": len(observed),
        }

    result_a = summary(scores_a_list, "scores_a")
    result_b = summary(scores_b_list, "scores_b")
    delta_lead = (result_a["mean_lead_days"] - result_b["mean_lead_days"]
                  if result_a["mean_lead_days"] is not None
                  and result_b["mean_lead_days"] is not None else None)
    return {
        "metric": "mean_lead_days_at_same_top_k",
        "k": k,
        "far_target": float(far),
        "n_units": n,
        "n_positives": n_positives,
        "n_negatives": n_negatives,
        "positives_without_lead": sum(1 for label, lead in zip(clean_labels, clean_leads)
                                      if label and lead is None),
        "scores_a": result_a,
        "scores_b": result_b,
        "mean_lead_days_a": result_a["mean_lead_days"],
        "mean_lead_days_b": result_b["mean_lead_days"],
        "n_detected_a": result_a["n_detected"],
        "n_detected_b": result_b["n_detected"],
        "n_censored_a": result_a["n_censored"],
        "n_censored_b": result_b["n_censored"],
        "far_a": result_a["far"],
        "far_b": result_b["far"],
        "difference": {
            "mean_lead_days": delta_lead,
            "n_detected": result_a["n_detected"] - result_b["n_detected"],
            "n_censored": result_a["n_censored"] - result_b["n_censored"],
        },
        "notes": [
            "Selection size k is matched; false-positive counts (far) may differ slightly between scorers.",
            "Mean lead is conditional on an observed lead; selected positives without one are counted as censored.",
            "Positives outside top-k are undetected, not dropped.",
        ],
    }
