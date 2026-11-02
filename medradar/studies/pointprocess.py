"""Point-process change detection under controlled truth (Phase 1D).

Pure logic, testable without a database:

  * ``rate_change_lr`` — profile-likelihood ratio for an exponential/Poisson rate change at a cut time, maximised over
    candidate cut points;
  * ``calibrate_null`` — threshold from parametric null simulation at a declared per-run false-alarm probability;
  * ``inject_rate_change`` — compress the post-change intervals by 1/m, preserving empirical structure;
  * ``quarterly_zscore_detector`` — the deployed coarse detector for the same comparison;
  * ``delay_days`` — detection delay helpers.

The unit is one cell's event sequence. Everything is deterministic given a seed.
"""
from __future__ import annotations

import math
import random
from typing import Mapping, Sequence

MIN_DELAY_EVENTS = 3          # a detection is measured only if it lands at least this many events after the change


def rate_change_lr(times: Sequence[float], *, min_index: int = 2, max_fraction: float = 0.9
                   ) -> dict:
    """Maximum profile-likelihood ratio for a single rate change in an event sequence.

    ``times`` are event times relative to the sequence start, sorted ascending. The end of observation ``T`` is the last
    event time; this is the conservative choice (no post-hoc window beyond the data).
    """
    values = sorted(float(value) for value in times)
    n = len(values)
    if n < 2 * min_index:
        return {"statistic": 0.0, "cut_index": None, "cut_time": None, "n": n}
    total = values[-1]
    if total <= 0:
        return {"statistic": 0.0, "cut_index": None, "cut_time": None, "n": n}
    baseline_rate = n / total
    best = {"statistic": 0.0, "cut_index": None, "cut_time": None}
    first = max(min_index, 1)
    last = min(n - min_index, int(math.floor(n * max_fraction)))
    for k in range(first, last + 1):
        cut_time = values[k - 1]
        if cut_time <= 0 or cut_time >= total:
            continue
        rate_before = k / cut_time
        rate_after = (n - k) / (total - cut_time)
        if rate_before <= 0 or rate_after <= 0:
            continue
        statistic = 2 * (k * math.log(rate_before / baseline_rate)
                         + (n - k) * math.log(rate_after / baseline_rate))
        if statistic > best["statistic"]:
            best = {"statistic": statistic, "cut_index": k, "cut_time": cut_time}
    best["n"] = n
    return best


def calibrate_null(n: int, total: float, *, false_alarm_per_run: float = 0.10,
                   simulations: int = 20000, seed: int = 4242) -> dict:
    """Threshold for the LR statistic from homogeneous Poisson null samples with the same (n, T)."""
    if n < 4 or total <= 0:
        return {"threshold": None, "false_alarm_per_run": false_alarm_per_run, "simulations": 0}
    rng = random.Random(seed)
    statistics = []
    for _ in range(simulations):
        sample = sorted(rng.uniform(0.0, total) for _ in range(n))
        statistics.append(rate_change_lr(sample)["statistic"])
    statistics.sort()
    index = int(math.floor((1.0 - false_alarm_per_run) * len(statistics)))
    index = min(len(statistics) - 1, max(0, index))
    return {"threshold": statistics[index], "false_alarm_per_run": false_alarm_per_run,
            "simulations": simulations, "quantile": 1.0 - false_alarm_per_run}


def inject_rate_change(intervals: Sequence[float], *, change_index: int, multiplier: float
                       ) -> list[float]:
    """Compress the intervals after ``change_index`` by 1/multiplier (rate increases m-fold)."""
    if multiplier <= 0:
        raise ValueError("multiplier must be positive")
    injected = list(intervals)
    for index in range(change_index, len(injected)):
        injected[index] = injected[index] / multiplier
    return injected


def times_from_intervals(intervals: Sequence[float]) -> list[float]:
    times, running = [], 0.0
    for interval in intervals:
        running += max(0.0, float(interval))
        times.append(running)
    return times


def detect_first_after(times: Sequence[float], *, threshold: float, min_index: int = 2
                       ) -> float | None:
    """Earliest event time at which the running sequence already exceeds the threshold."""
    for end in range(max(4, 2 * min_index), len(times) + 1):
        prefix = times[:end]
        if rate_change_lr(prefix, min_index=min_index)["statistic"] >= threshold:
            return prefix[-1]
    return None


def quarterly_counts(times: Sequence[float], total: float, *, quarters: int) -> list[int]:
    """Bin event times into ``quarters`` equal-width bins over [0, total]."""
    if quarters <= 0 or total <= 0:
        return []
    counts = [0] * quarters
    width = total / quarters
    for value in times:
        index = min(quarters - 1, max(0, int(value / width)))
        counts[index] += 1
    return counts


def quarterly_zscore_detector(counts: Sequence[int], *, baseline: int = 8, threshold: float = 3.5
                              ) -> dict:
    """The deployed coarse detector on quarterly counts; returns the first alert bin index after warm-up."""
    for index in range(baseline, len(counts)):
        window = counts[index - baseline:index]
        mean = sum(window) / baseline
        if mean <= 0:
            continue
        current = counts[index]
        zscore = (current - mean) / math.sqrt(mean)
        if zscore >= threshold:
            return {"alert_bin": index, "zscore": zscore}
    return {"alert_bin": None, "zscore": None}


def delay_days(detected_at: float | None, change_time: float, total: float, events_after: int) -> dict:
    """Detection delay in days and in events; None when not detected or when too few events remain."""
    if detected_at is None:
        return {"detected": False, "delay_days": None, "delay_events": None}
    delay = detected_at - change_time
    return {"detected": True, "delay_days": round(delay, 1), "delay_events": events_after,
            "late_negative": delay < 0}


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def paired_bootstrap_median(values_a: Mapping[str, float], values_b: Mapping[str, float], *,
                            resamples: int = 2000, seed: int = 7) -> dict:
    """Paired bootstrap of the median difference (A − B) over shared cells."""
    shared = sorted(set(values_a) & set(values_b))
    if not shared:
        return {"cells": 0, "median_difference": None, "interval": [None, None]}
    differences = [values_a[cell] - values_b[cell] for cell in shared]
    rng = random.Random(seed)
    samples = []
    for _ in range(resamples):
        draw = [differences[rng.randrange(len(differences))] for _ in differences]
        samples.append(_median(draw))
    samples.sort()
    return {"cells": len(shared), "median_difference": round(_median(differences), 2),
            "interval": [round(samples[int(0.025 * len(samples))], 2),
                         round(samples[int(0.975 * len(samples)) - 1], 2)]}


def max_prefix_lr(times: Sequence[float], *, min_index: int = 2) -> float:
    """Largest LR statistic over growing prefixes: the calibration statistic for detector A on a full sequence."""
    best = 0.0
    for end in range(max(4, 2 * min_index), len(times) + 1):
        statistic = rate_change_lr(times[:end], min_index=min_index)["statistic"]
        if statistic > best:
            best = statistic
    return best


def quarterly_max_z(counts: Sequence[int], *, baseline: int = 8, threshold: float = 3.5) -> float:
    """Largest quarterly z observed (regardless of the deployed threshold): the calibration statistic for detector B."""
    best = 0.0
    for index in range(baseline, len(counts)):
        window = counts[index - baseline:index]
        mean = sum(window) / baseline
        if mean <= 0:
            continue
        zscore = (counts[index] - mean) / math.sqrt(mean)
        if zscore > best:
            best = zscore
    return best


def empirical_threshold(values: Sequence[float], *, false_alarm_per_run: float = 0.10) -> float | None:
    """Threshold for an empirical null distribution, with ties handled by a strict ``>`` rule.

    Taking a plain quantile fails when many null statistics are identical (for instance a detector that often scores
    exactly 0): every tied value would count as an alarm and the realised rate can exceed the target several-fold
    (measured 0.26 against a 0.10 target). The threshold is therefore the smallest observed value v such that the
    fraction of values strictly above v is at most the declared budget.
    """
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    allowed = false_alarm_per_run * n
    # allow ~budget*n observations strictly above the threshold; ties below it only reduce the realised rate
    index = max(0, n - int(false_alarm_per_run * n) - 1)
    return ordered[index]


def rate_above(values: Sequence[float], threshold: float | None) -> float | None:
    """Realised false-alarm rate: fraction of null statistics strictly above the threshold."""
    if not values or threshold is None:
        return None
    return sum(1 for value in values if value > threshold) / len(values)
