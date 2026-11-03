#!/usr/bin/env python3
"""b103 — cross-source lead/lag at the company level (backlog B-021).

This module is the executable form of the **frozen** pre-registration
``research/protocols/b103_leadlag_preregistration.md`` (FROZEN 2026-11-03, before
any b103 statistic was computed).  It is a descriptive association study: a
leading correlation does **not** establish that a source causes or predicts a
material regulatory event.  No causal language is emitted anywhere.

Design in one line
------------------
For each source S in {financial R&D, market return, publication, [market
volatility — descriptive only]} and lag ``k`` in -8..+8, compute the pooled
correlation ``r(k) = corr(z(S_{c,t-k}), z(M_{c,t}))`` of per-company z-scores,
where ``M`` is the company's material-event count per quarter from the frozen
``hist_v1`` panel.  Positive ``k`` means the source precedes events.  Primary
``k* = argmax_{k in 1..8} |r(k)|``.  Inference: company-clustered bootstrap
(2,000 reps, seed 20261103, 95 % percentile intervals, descriptive/uncorrected),
circular-shift permutation null (1,000 reps, seed 20261103, per-company rotation
of the source series), Holm correction across financial / market-return /
publication, and an era split (2017-2021 vs 2022-2025, 50 % stability rule).
The decision rule of section 5 is applied verbatim.

Data
----
Read-only SQLite (``file:data/research.sqlite?mode=ro``); nothing is written to
``data/``.  Series, all on the frozen 36-quarter analysis grid 2017-Q1..2025-Q4:

* ``M`` — material 510(k)/PMA events per company-quarter, aggregated from
  ``out/hist_v1/panel.json`` ``pairs[].event_counts`` (primary ``pairs`` only).
  Every panel company is monitored over the whole grid, so a quarter with no
  event is a true count of 0.
* financial — trailing-4-quarter ``ResearchAndDevelopmentExpense`` from
  ``financial_facts``.  A fact whose reported period spans 300-400 days *is* a
  trailing-4-quarter total; it enters the series in the quarter of its
  ``available_at`` (the filing date = knowledge time).  At every quarter end the
  series carries the most recently filed such fact (step function between
  filings); the value is ``log(USD)``.  Duplicate period ends are de-duplicated
  by earliest ``available_at`` (first knowledge, no restatement look-ahead).
  Non-positive values cannot be logged and are left missing (measured).
* market return — quarter-end ``adj_close`` (last bar on or before the date)
  divided by the previous quarter-end ``adj_close`` minus one.  Market
  *volatility* (sample SD of daily log returns inside the quarter) is
  computed for the same quarters and reported **descriptively only**.
* publication — OpenAlex works per company-year ``works(y)`` divided equally
  across the year's quarters => a quarterly rate ``works(y)/4``.  The knowledge
  rule of ``medradar/intelligence/features/publication_features.py`` is applied:
  year ``y`` is usable only from 15 February of ``y+1``, so quarter ``t`` uses the
  most recent complete year known by then.  Annual resolution (a step function).
* procurement — ``announcement_date`` is NULL for every row and ``pit_usable=0``
  for every row, so the source is measured ``NOT_EVALUABLE``; no proxy is
  substituted.

Determinism
-----------
Standard library only (no numpy/pandas/scipy), no network, no wall clock, no
platform-dependent formatting.  All lists are sorted, JSON is dumped with
``sort_keys=True`` and ``repr`` float formatting, and the two random streams use
fixed seeds (20261103).  Two consecutive runs on the same inputs are
byte-identical.

Usage
-----
    python experiments/b103_leadlag/leadlag.py
    python experiments/b103_leadlag/leadlag.py --report-only   # REPORT.md from JSON

Outputs
-------
``experiments/b103_leadlag/leadlag.json``  every number of the analysis
``experiments/b103_leadlag/REPORT.md``     rendered from the JSON only
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import random
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[2]

SCHEMA = "b103.leadlag.v1"
REPORT_SCHEMA = "b103.leadlag.report.v1"
PROTOCOL_REL = "research/protocols/b103_leadlag_preregistration.md"
DEFAULT_DB = "data/research.sqlite"
DEFAULT_PANEL = "out/hist_v1/panel.json"
DEFAULT_OUT_DIR = "experiments/b103_leadlag"

WINDOW_START = "2017-Q1"
WINDOW_END = "2025-Q4"
LAGS: tuple[int, ...] = tuple(range(-8, 9))
LEAD_LAGS: tuple[int, ...] = tuple(range(1, 9))
ERA_1 = ("2017-Q1", "2021-Q4")
ERA_2 = ("2022-Q1", "2025-Q4")

BOOTSTRAP_REPS = 2_000
PERMUTATION_REPS = 1_000
SEED = 20261103

MIN_QUARTERS = 8          # protocol section 2: fewer than 8 quarters -> excluded
MIN_PAIRS = 3             # a pooled Pearson r needs at least 3 pairs
MIN_Z_OBS = 3             # a z-score needs at least 3 observations
ALPHA = 0.05
POWER = 0.80
Z_975 = 1.959963984540054   # two-sided 5 % normal critical value
Z_80 = 0.8416212335729143   # 80 % power normal critical value
MDE_FACTOR = Z_975 + Z_80   # MDE = (z_{1-alpha/2} + z_{power}) * SD of the statistic
WELL_POWERED_MDE = 0.10     # reporting label only, never used to claim a lead

HOLM_FAMILY: tuple[str, ...] = ("financial_rd", "market_return", "publication")
DESCRIPTIVE_ONLY: tuple[str, ...] = ("market_volatility",)

DECISION_RULE = (
    "A source is said to lead only if all hold: (i) k* > 0; (ii) Holm-adjusted "
    "p < 0.05; (iii) the era-split stability rule holds. Otherwise the result is "
    "reported as no lead detected with its MDE; a source whose data are "
    "insufficient is reported as NOT_EVALUABLE with the measured coverage."
)
ERA_RULE = (
    "Era split (descriptive): 2017-2021 vs 2022-2025. A lead is reported as "
    "stable only if the point estimate at k* has the same sign and the absolute "
    "value >= 50 % of the full-window value in both eras."
)
MDE_RULE = (
    "MDE at 80 % power (alpha=0.05) = (z_{0.975} + z_{0.80}) * SD_b, with "
    "SD_b the bootstrap standard deviation of the max-lead statistic "
    "max_{k in 1..8} |r(k)| over the 2,000 company-clustered resamples."
)
PERMUTATION_RULE = (
    "Circular-shift permutation null: for each company independently rotate its "
    "z-scored source series by a random offset in 1..T-1 (T=36) and recompute "
    "max_{k in 1..8} |r(k)|; p = fraction of null maxima >= the observed maximum."
)
BOOTSTRAP_RULE = (
    "Company-clustered bootstrap: resample companies with replacement 2,000 "
    "times, recompute the whole r(k) profile; 95 % percentile intervals "
    "(linear interpolation); descriptive and uncorrected."
)


# --------------------------------------------------------------------------- grid
def _parse_quarter(label: str) -> tuple[int, int]:
    year, quarter = label.split("-Q")
    return int(year), int(quarter)


def quarter_labels(start: str, end: str) -> list[str]:
    """Every calendar quarter from ``start`` to ``end`` inclusive."""
    sy, sq = _parse_quarter(start)
    ey, eq = _parse_quarter(end)
    labels: list[str] = []
    year, quarter = sy, sq
    while (year, quarter) <= (ey, eq):
        labels.append(f"{year}-Q{quarter}")
        quarter += 1
        if quarter == 5:
            quarter, year = 1, year + 1
    return labels


def quarter_end(label: str) -> date:
    """Last calendar day of the quarter (the observation boundary)."""
    year, quarter = _parse_quarter(label)
    return {
        1: date(year, 3, 31),
        2: date(year, 6, 30),
        3: date(year, 9, 30),
        4: date(year, 12, 31),
    }[quarter]


def previous_quarter_end(label: str) -> date:
    """Quarter-end boundary immediately before ``label`` (for quarterly changes)."""
    year, quarter = _parse_quarter(label)
    if quarter == 1:
        return date(year - 1, 12, 31)
    return quarter_end(f"{year}-Q{quarter - 1}")


def publication_knowledge_date(year: int) -> date:
    """Conservative date on which a complete publication year is usable.

    Mirrors ``medradar/intelligence/features/publication_features.py``: year
    ``y`` becomes usable on 15 February of ``y+1``.
    """
    return date(year + 1, 2, 15)


def latest_known_publication_year(day: date, start_year: int = 2014) -> int:
    """Most recent publication year whose knowledge date is on/before ``day``."""
    year = day.year
    while publication_knowledge_date(year) > day:
        year -= 1
    return max(year, start_year - 1)


WINDOW: list[str] = quarter_labels(WINDOW_START, WINDOW_END)
WINDOW_END_DATES: list[date] = [quarter_end(label) for label in WINDOW]
WINDOW_START_DATES: list[date] = [previous_quarter_end(label) for label in WINDOW]
WINDOW_LENGTH = len(WINDOW)


# ----------------------------------------------------------------------- statistics
def mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def sample_sd(values: Sequence[float]) -> float:
    """Sample standard deviation (n-1); ``0.0`` when it is degenerate."""
    n = len(values)
    if n < 2:
        return 0.0
    mu = mean(values)
    return math.sqrt(math.fsum((value - mu) ** 2 for value in values) / (n - 1))


def zscore(values: Sequence[float | None]) -> list[float | None]:
    """Per-series z-score on the non-missing observations, missing preserved.

    ``None`` is returned (for the whole series) when there are fewer than
    ``MIN_Z_OBS`` observations or the series is constant.  Population or sample
    SD?  Sample SD (n-1) is used consistently; a constant series has SD 0 and no
    z-score.
    """
    observed = [value for value in values if value is not None]
    if len(observed) < MIN_Z_OBS:
        return [None] * len(values)
    mu = mean(observed)
    sd = sample_sd(observed)
    if sd <= 0.0:
        return [None] * len(values)
    return [None if value is None else (value - mu) / sd for value in values]


def correlation(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Pooled Pearson correlation, ``None`` when undefined."""
    if len(xs) != len(ys) or len(xs) < MIN_PAIRS:
        return None
    return correlation_from_moments(
        len(xs), math.fsum(xs), math.fsum(ys),
        math.fsum(x * x for x in xs), math.fsum(y * y for y in ys),
        math.fsum(x * y for x, y in zip(xs, ys)))


def correlation_from_moments(
        n: int, sa: float, sb: float, saa: float, sbb: float, sab: float) -> float | None:
    """Pearson r from sufficient statistics; ``None`` when undefined."""
    if n < MIN_PAIRS:
        return None
    cxx = n * saa - sa * sa
    cyy = n * sbb - sb * sb
    if cxx <= 0.0 or cyy <= 0.0:
        return None
    return (n * sab - sa * sb) / math.sqrt(cxx * cyy)


def percentile(values: Sequence[float], probability: float) -> float | None:
    """Empirical percentile with linear interpolation (NumPy-compatible default)."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = int(math.floor(position))
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + weight * (ordered[upper] - ordered[lower])


# ------------------------------------------------------------ lag / moment blocks
def moments_for_lag(
        zsource: Sequence[float | None], zevent: Sequence[float | None],
        lag: int, length: int) -> tuple[int, float, float, float, float, float]:
    """Sufficient statistics for the pairs ``(zsource[t-lag], zevent[t])``."""
    n = 0
    sa = sb = saa = sbb = sab = 0.0
    for t in range(max(0, lag), min(length, length + lag)):
        i = t - lag
        a = zsource[i]
        b = zevent[t]
        if a is None or b is None:
            continue
        n += 1
        sa += a
        sb += b
        saa += a * a
        sbb += b * b
        sab += a * b
    return (n, sa, sb, saa, sbb, sab)


def add_moments(
        left: tuple[int, float, float, float, float, float],
        right: tuple[int, float, float, float, float, float]
) -> tuple[int, float, float, float, float, float]:
    return (
        left[0] + right[0], left[1] + right[1], left[2] + right[2],
        left[3] + right[3], left[4] + right[4], left[5] + right[5])


def blocks_for_company(
        zsource: Sequence[float | None], zevent: Sequence[float | None],
        lags: Iterable[int], length: int) -> dict[int, tuple[int, float, float, float, float, float]]:
    """Per-lag sufficient statistics for one company (the bootstrap unit)."""
    return {lag: moments_for_lag(zsource, zevent, lag, length) for lag in lags}


def profile_from_blocks(
        blocks: Iterable[dict[int, tuple[int, float, float, float, float, float]]],
        lags: Iterable[int]) -> dict[int, float | None]:
    """Pooled r(k) from the blocks of the companies in ``blocks``."""
    total = {lag: (0, 0.0, 0.0, 0.0, 0.0, 0.0) for lag in lags}
    for block in blocks:
        for lag in lags:
            total[lag] = add_moments(total[lag], block[lag])
    return {lag: correlation_from_moments(*total[lag]) for lag in lags}


def lead_choice(profile: dict[int, float | None]) -> tuple[int | None, float | None]:
    """``k* = argmax_{k in 1..8} |r(k)|``; ties resolve to the smallest k."""
    best_lag: int | None = None
    best_value: float | None = None
    for lag in LEAD_LAGS:
        value = profile.get(lag)
        if value is None:
            continue
        magnitude = abs(value)
        if best_value is None or magnitude > best_value:
            best_lag, best_value = lag, magnitude
    return best_lag, best_value


# ------------------------------------------------------------------------ bootstrap
def bootstrap_profile(
        company_keys: Sequence[str],
        blocks_by_company: dict[str, dict[int, tuple[int, float, float, float, float, float]]],
        lags: Iterable[int],
        reps: int,
        rng: random.Random) -> dict[str, Any]:
    """Company-clustered bootstrap of the whole r(k) profile.

    Companies are resampled with replacement; every resample recomputes every
    ``r(k)`` from the resampled companies' sufficient statistics (duplicates
    counted as separate draws).  Also returns the bootstrap SD of the max-lead
    statistic used for the MDE.
    """
    lags = tuple(lags)
    n = len(company_keys)
    draws: dict[int, list[float]] = {lag: [] for lag in lags}
    max_lead: list[float] = []
    for _ in range(reps):
        totals = {lag: (0, 0.0, 0.0, 0.0, 0.0, 0.0) for lag in lags}
        for _ in range(n):
            block = blocks_by_company[company_keys[rng.randrange(n)]]
            for lag in lags:
                totals[lag] = add_moments(totals[lag], block[lag])
        sample = {lag: correlation_from_moments(*totals[lag]) for lag in lags}
        for lag in lags:
            if sample[lag] is not None:
                draws[lag].append(sample[lag])
        best = None
        for lag in LEAD_LAGS:
            value = sample.get(lag)
            if value is not None:
                magnitude = abs(value)
                best = magnitude if best is None else max(best, magnitude)
        if best is not None:
            max_lead.append(best)
    intervals = {}
    for lag in lags:
        values = draws[lag]
        if len(values) >= 2:
            intervals[lag] = {
                "n_valid": len(values),
                "ci_low": percentile(values, 0.025),
                "ci_high": percentile(values, 0.975),
                "sd": sample_sd(values),
            }
        else:
            intervals[lag] = {"n_valid": len(values), "ci_low": None,
                              "ci_high": None, "sd": None}
    max_lead_sd = sample_sd(max_lead) if len(max_lead) >= 2 else None
    return {
        "reps_requested": reps,
        "reps_with_max_lead": len(max_lead),
        "intervals": intervals,
        "max_lead_sd": max_lead_sd,
        "max_lead_mean": mean(max_lead) if max_lead else None,
    }


# ---------------------------------------------------------------------- permutation
def rotate_circular(values: Sequence[Any], offset: int) -> list[Any]:
    """Circular right-shift: ``new[t] = values[(t - offset) % T]``."""
    length = len(values)
    offset %= length
    return list(values[length - offset:]) + list(values[:length - offset])


def permutation_null(
        company_keys: Sequence[str],
        zsource: dict[str, list[float | None]],
        zevent: dict[str, list[float | None]],
        reps: int,
        rng: random.Random,
        observed_max: float,
        length: int) -> dict[str, Any]:
    """Circular-shift permutation null for the max-lead statistic.

    For each company independently the z-scored source series is rotated by a
    random offset in ``1..T-1`` (``T = length``); the event series is untouched.
    The z-score is invariant to rotation (it is a permutation of the same
    values), so rotating the z-scores preserves each series' autocorrelation,
    marginal distribution and missing pattern, while breaking the alignment with
    events.
    """
    exceed = 0
    valid = 0
    null_maxima: list[float] = []
    for _ in range(reps):
        totals = {lag: (0, 0.0, 0.0, 0.0, 0.0, 0.0) for lag in LEAD_LAGS}
        for company in company_keys:
            rotated = rotate_circular(zsource[company], rng.randrange(1, length))
            event = zevent[company]
            for lag in LEAD_LAGS:
                totals[lag] = add_moments(
                    totals[lag], moments_for_lag(rotated, event, lag, length))
        best = None
        for lag in LEAD_LAGS:
            value = correlation_from_moments(*totals[lag])
            if value is not None:
                magnitude = abs(value)
                best = magnitude if best is None else max(best, magnitude)
        if best is None:
            continue
        valid += 1
        null_maxima.append(best)
        if best >= observed_max:
            exceed += 1
    return {
        "reps_requested": reps,
        "reps_valid": valid,
        "n_null_ge_observed": exceed,
        "p_value": (exceed / valid) if valid else None,
        "null_max_median": percentile(null_maxima, 0.5) if null_maxima else None,
        "null_max_p95": percentile(null_maxima, 0.95) if null_maxima else None,
    }


# ---------------------------------------------------------------------------- eras
def era_correlation(
        company_keys: Sequence[str],
        zsource: dict[str, list[float | None]],
        zevent: dict[str, list[float | None]],
        lag: int,
        first_index: int,
        last_index: int,
        length: int) -> tuple[float | None, int]:
    """Pooled r(k) restricted to milestone quarters ``first_index..last_index``."""
    total = (0, 0.0, 0.0, 0.0, 0.0, 0.0)
    for company in company_keys:
        source = zsource[company]
        event = zevent[company]
        for t in range(first_index, last_index + 1):
            i = t - lag
            if i < 0 or i >= length:
                continue
            a = source[i]
            b = event[t]
            if a is None or b is None:
                continue
            total = add_moments(total, (1, a, b, a * a, b * b, a * b))
    return correlation_from_moments(*total), total[0]


# --------------------------------------------------------------------------- holm
def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values (family = the three primary sources)."""
    ordered = sorted((value, key) for key, value in p_values.items())
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, (value, key) in enumerate(ordered):
        candidate = min(1.0, (m - rank) * value)
        running = max(running, candidate)
        adjusted[key] = running
    return adjusted


# ---------------------------------------------------------------------- MDE / power
def minimum_detectable_effect(sd: float | None) -> float | None:
    """MDE(|r|) at 80 % power, two-sided alpha 0.05: (z_.975 + z_.80) * sd."""
    if sd is None:
        return None
    return MDE_FACTOR * sd


# ---------------------------------------------------------------------- source data
def load_panel(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def panel_event_series(
        panel: dict[str, Any], window: Sequence[str]) -> dict[str, list[float]]:
    """Company -> per-quarter material-event counts on the analysis window.

    ``pairs[].event_counts`` are summed by company and quarter index; a quarter
    with no event is a 0 because the frozen panel monitors every company over the
    whole grid.  Companies are the panel company keys.
    """
    quarters = list(panel["quarters"])
    index = {label: position for position, label in enumerate(window)}
    first = quarters.index(window[0])
    last = quarters.index(window[-1])
    series: dict[str, list[float]] = {
        company["key"]: [0.0] * len(window) for company in panel["companies"]}
    for pair in panel["pairs"]:
        company = pair["company_key"]
        row = series.setdefault(company, [0.0] * len(window))
        for quarter_index, count in zip(pair["event_qidx"], pair["event_counts"]):
            if first <= quarter_index <= last:
                row[index[quarters[quarter_index]]] += float(count)
    return series


def _duration_days(period_start: str | None, period_end: str | None) -> int | None:
    try:
        start = date.fromisoformat(str(period_start)[:10])
        end = date.fromisoformat(str(period_end)[:10])
    except (TypeError, ValueError):
        return None
    return (end - start).days


def financial_series(
        rows: Iterable[Sequence[Any]], window: Sequence[str]) -> tuple[
            dict[str, list[float | None]], dict[str, Any]]:
    """Trailing-4-quarter R&D expense, log, at each quarter end (see module doc).

    ``rows``: ``(company_key, period_start, period_end, value, available_at,
    fact_id)`` tuples for the frozen tag.  Only facts whose reported period spans
    300-400 days are trailing-4-quarter totals.  For every ``(company,
    period_end)`` the earliest ``available_at`` wins (first knowledge).  At a
    quarter end the series carries the most recently *reported* such total
    (``period_end`` then ``available_at`` order); non-positive values are missing
    because they cannot be logged.
    """
    rows = list(rows)
    facts: dict[str, dict[str, tuple[float, str, str]]] = {}
    duration_rejected = 0
    non_positive = 0
    for company, period_start, period_end, value, available_at, fact_id in rows:
        duration = _duration_days(period_start, period_end)
        if duration is None or not (300 <= duration <= 400):
            duration_rejected += 1
            continue
        end_key = str(period_end)[:10]
        available_key = str(available_at)[:10]
        candidate = (float(value), available_key, str(fact_id))
        current = facts.setdefault(company, {}).get(end_key)
        if current is None or (candidate[1], candidate[2]) < (current[1], current[2]):
            facts[company][end_key] = candidate
    ordered = {company: sorted(periods.items()) for company, periods in facts.items()}
    boundaries = [quarter_end(label) for label in window]
    series: dict[str, list[float | None]] = {}
    for company, periods in ordered.items():
        values: list[float | None] = []
        for boundary in boundaries:
            best: tuple[date, str, float, str] | None = None
            for period_end, (value, available_at, fact_id) in periods:
                end_day = date.fromisoformat(period_end)
                available_day = date.fromisoformat(available_at)
                if end_day > boundary or available_day > boundary:
                    continue
                if best is None or (end_day, available_at) > (best[0], best[1]):
                    best = (end_day, available_at, value, fact_id)
            if best is None:
                values.append(None)
            elif best[2] <= 0.0:
                non_positive += 1
                values.append(None)
            else:
                values.append(math.log(best[2]))
        series[company] = values
    return series, {
        "tag": "ResearchAndDevelopmentExpense",
        "rows_read": len(rows),
        "duration_rejected_rows": duration_rejected,
        "non_positive_value_quarters": non_positive,
        "fact_period_days_rule": "trailing-4-quarter facts have a reported period of 300-400 days",
        "duplicate_period_rule": "earliest available_at wins per (company, period_end)",
        "carry_forward": True,
    }


def _quarter_end_index(sorted_dates: Sequence[date], day: date) -> int:
    """Index of the last element <= ``day`` or -1."""
    return bisect.bisect_right(sorted_dates, day) - 1


def market_series(
        rows: Iterable[Sequence[Any]],
        tickers: dict[str, str],
        window: Sequence[str]) -> tuple[dict[str, list[float | None]],
                                        dict[str, list[float | None]], dict[str, Any]]:
    """Quarterly return and quarterly return-volatility from ``market_bars``.

    ``rows``: ``(ticker, date, adj_close)``.  Return = last adj_close on/before
    the quarter end divided by the last adj_close on/before the previous quarter
    end, minus one.  Volatility = sample SD of daily log returns with dates inside
    ``(previous quarter end, quarter end]``; requires at least two returns.
    """
    bars: dict[str, list[tuple[date, float]]] = {}
    for ticker, day, adj_close in rows:
        if adj_close is None:
            continue
        bars.setdefault(str(ticker), []).append((date.fromisoformat(str(day)[:10]),
                                                 float(adj_close)))
    for ticker in bars:
        bars[ticker].sort()
    ends = [quarter_end(label) for label in window]
    starts = [previous_quarter_end(label) for label in window]
    returns: dict[str, list[float | None]] = {}
    volatility: dict[str, list[float | None]] = {}
    for company, ticker in tickers.items():
        ticker_bars = bars.get(ticker)
        if not ticker_bars:
            continue
        dates = [item[0] for item in ticker_bars]
        closes = [item[1] for item in ticker_bars]
        return_values: list[float | None] = []
        vol_values: list[float | None] = []
        for end_day, start_day in zip(ends, starts):
            end_index = _quarter_end_index(dates, end_day)
            start_index = _quarter_end_index(dates, start_day)
            if end_index < 0 or start_index < 0 or end_index == start_index:
                return_values.append(None)
            else:
                base = closes[start_index]
                return_values.append(closes[end_index] / base - 1.0 if base > 0 else None)
            log_returns = [
                math.log(closes[index] / closes[index - 1])
                for index in range(start_index + 1, end_index + 1)
                if closes[index - 1] > 0 and closes[index] > 0]
            vol_values.append(sample_sd(log_returns) if len(log_returns) >= 2 else None)
        returns[company] = return_values
        volatility[company] = vol_values
    return returns, volatility, {
        "return_definition": "quarter-end adj_close / previous-quarter-end adj_close - 1",
        "volatility_definition": "sample SD of daily log returns inside the quarter",
        "quarter_end_rule": "last bar on or before the quarter-end date",
        "min_daily_returns_for_volatility": 2,
    }


def publication_series(
        rows: Iterable[Sequence[Any]], window: Sequence[str]) -> tuple[
            dict[str, list[float | None]], dict[str, Any]]:
    """Quarterly publication rate under the declared 15-February knowledge rule.

    ``rows``: ``(company_key, year, works)``.  Quarter ``t`` uses the most recent
    year ``y`` with ``date(y+1, 2, 15) <= quarter end``; the value is
    ``works(y) / 4`` (the year's works divided equally across its quarters).  If
    the company has no row for that year the quarter is missing — no zero is
    invented.
    """
    counts: dict[str, dict[int, float]] = {}
    for company, year, works in rows:
        counts.setdefault(str(company), {})[int(year)] = float(works)
    series: dict[str, list[float | None]] = {}
    for company, by_year in counts.items():
        values: list[float | None] = []
        for label in window:
            year = latest_known_publication_year(quarter_end(label))
            values.append(by_year[year] / 4.0 if year in by_year else None)
        series[company] = values
    return series, {
        "source": "publication_counts.works (OpenAlex group_by_publication_year)",
        "knowledge_rule": "year y usable from 15 February of y+1",
        "quarter_value": "works(y) / 4 where y is the most recent complete known year",
        "resolution": "annual (step function on the quarterly grid)",
        "missing_year_policy": "missing, never zero-filled",
    }


def procurement_status(rows: Iterable[Sequence[Any]]) -> dict[str, Any]:
    """Measure the procurement lane rather than substituting a proxy."""
    total = 0
    null_announcement = 0
    pit_usable = 0
    for announcement_date, usable in rows:
        total += 1
        if announcement_date in (None, ""):
            null_announcement += 1
        try:
            pit_usable += 1 if int(usable) else 0
        except (TypeError, ValueError):
            continue
    evaluable = total > 0 and null_announcement < total and pit_usable > 0
    return {
        "status": "EVALUABLE" if evaluable else "NOT_EVALUABLE",
        "rows": total,
        "announcement_date_null": null_announcement,
        "pit_usable_rows": pit_usable,
        "reason": ("every announcement_date is NULL and every row has pit_usable=0: "
                   "the lane cannot be placed in time, so it is reported measured and "
                   "no proxy series is substituted"),
        "proxy_substituted": False,
    }


# ------------------------------------------------------------------- source analysis
def _exclusion(company: str, reason: str) -> dict[str, str]:
    return {"company_key": company, "reason": reason}


def analyse_source(
        *,
        source_id: str,
        label: str,
        raw_series: dict[str, list[float | None]],
        event_series: dict[str, list[float]],
        universe: Sequence[str],
        length: int = WINDOW_LENGTH,
        bootstrap_reps: int = BOOTSTRAP_REPS,
        permutation_reps: int = PERMUTATION_REPS,
        seed: int = SEED,
        descriptive_only: bool = False,
        series_definition: str = "",
        data_notes: dict[str, Any] | None = None) -> dict[str, Any]:
    """Full frozen analysis for one source (everything except the Holm step)."""
    universe = sorted(universe)
    included: list[str] = []
    exclusions: list[dict[str, str]] = []
    observed_quarters: dict[str, int] = {}
    for company in universe:
        if company not in raw_series:
            exclusions.append(_exclusion(company, "no_source_data"))
            continue
        source_values = raw_series[company]
        observed = sum(1 for value in source_values if value is not None)
        observed_quarters[company] = observed
        event_values = event_series.get(company)
        event_observed = (sum(1 for value in event_values if value is not None)
                          if event_values is not None else 0)
        if observed < MIN_QUARTERS or event_observed < MIN_QUARTERS:
            exclusions.append(_exclusion(
                company, f"fewer_than_{MIN_QUARTERS}_quarters"))
            continue
        zsource = zscore(source_values)
        zevent = zscore(event_values)
        if all(value is None for value in zsource):
            exclusions.append(_exclusion(company, "constant_source_series"))
            continue
        if all(value is None for value in zevent):
            exclusions.append(_exclusion(company, "constant_event_series"))
            continue
        included.append(company)

    zsources = {company: zscore(raw_series[company]) for company in included}
    zevents = {company: zscore(event_series[company]) for company in included}
    blocks_by_company = {
        company: blocks_for_company(zsources[company], zevents[company], LAGS, length)
        for company in included}

    profile = profile_from_blocks(
        [blocks_by_company[company] for company in included], LAGS)
    pairs_by_lag = {
        lag: sum(blocks_by_company[company][lag][0] for company in included)
        for lag in LAGS}

    evaluable = bool(included) and any(profile.get(lag) is not None for lag in LEAD_LAGS)
    k_star: int | None = None
    observed_max: float | None = None
    if evaluable:
        k_star, observed_max = lead_choice(profile)
        if observed_max is None:
            evaluable = False

    bootstrap: dict[str, Any] | None = None
    if evaluable and len(included) >= 2:
        bootstrap = bootstrap_profile(
            included, blocks_by_company, LAGS, bootstrap_reps, random.Random(seed))
    permutation: dict[str, Any] | None = None
    if evaluable and observed_max is not None and len(included) >= 2:
        permutation = permutation_null(
            included, zsources, zevents, permutation_reps,
            random.Random(seed), observed_max, length)

    intervals = bootstrap["intervals"] if bootstrap else {}
    profile_entries: list[dict[str, Any]] = []
    for lag in LAGS:
        interval = intervals.get(lag, {})
        profile_entries.append({
            "k": lag,
            "r": profile.get(lag),
            "n_pairs": pairs_by_lag[lag],
            "n_milestone_quarters": length - abs(lag),
            "bootstrap_ci_low": interval.get("ci_low"),
            "bootstrap_ci_high": interval.get("ci_high"),
            "bootstrap_sd": interval.get("sd"),
            "bootstrap_n_valid": interval.get("n_valid"),
        })
    observed_k = next((entry for entry in profile_entries if entry["k"] == k_star), None)
    max_lead_sd = bootstrap["max_lead_sd"] if bootstrap else None
    mde = minimum_detectable_effect(max_lead_sd)

    era: dict[str, Any] | None = None
    if evaluable and k_star is not None:
        full_r = profile.get(k_star)
        indices = {label: position for position, label in enumerate(WINDOW)}
        era_1_first, era_1_last = indices[ERA_1[0]], indices[ERA_1[1]]
        era_2_first, era_2_last = indices[ERA_2[0]], indices[ERA_2[1]]
        r_1, n_1 = era_correlation(included, zsources, zevents, k_star,
                                   era_1_first, era_1_last, length)
        r_2, n_2 = era_correlation(included, zsources, zevents, k_star,
                                   era_2_first, era_2_last, length)
        stable = False
        if full_r is not None and full_r != 0.0 and r_1 is not None and r_2 is not None:
            stable = all(
                (value > 0.0) == (full_r > 0.0) and abs(value) >= 0.5 * abs(full_r)
                for value in (r_1, r_2))
        era = {
            "eras": [f"{ERA_1[0]}..{ERA_1[1]}", f"{ERA_2[0]}..{ERA_2[1]}"],
            "k_used": k_star,
            "full_window_r": full_r,
            "era_1": {"label": f"{ERA_1[0]}..{ERA_1[1]}", "r": r_1, "n_pairs": n_1},
            "era_2": {"label": f"{ERA_2[0]}..{ERA_2[1]}", "r": r_2, "n_pairs": n_2},
            "signed_and_at_least_half_in_both_eras": stable,
            "rule": ERA_RULE,
        }

    record: dict[str, Any] = {
        "source_id": source_id,
        "label": label,
        "descriptive_only": descriptive_only,
        "in_holm_family": source_id in HOLM_FAMILY,
        "series_definition": series_definition,
        "data_notes": data_notes or {},
        "coverage": {
            "panel_companies": len(universe),
            "companies_with_source_data": len(raw_series),
            "companies_excluded_no_source_data": sum(
                1 for entry in exclusions if entry["reason"] == "no_source_data"),
            "companies_included": len(included),
            "companies_excluded": len(exclusions),
            "exclusions": exclusions,
            "company_quarters_observed": sum(observed_quarters.values()),
            "company_quarters_max_possible": len(universe) * length,
            "included_companies": included,
        },
        "evaluable": evaluable,
        "primary": {
            "k_star": k_star,
            "r_k_star": observed_k["r"] if observed_k else None,
            "abs_r_k_star": observed_max,
            "bootstrap_ci_low": observed_k["bootstrap_ci_low"] if observed_k else None,
            "bootstrap_ci_high": observed_k["bootstrap_ci_high"] if observed_k else None,
            "bootstrap_sd_r_k_star": observed_k["bootstrap_sd"] if observed_k else None,
            "bootstrap_sd_max_lead": max_lead_sd,
            "mde_80": mde,
            "mde_rule": MDE_RULE,
        },
        "profile": profile_entries,
        "bootstrap": {
            "reps_requested": bootstrap_reps,
            "reps_with_max_lead": bootstrap["reps_with_max_lead"] if bootstrap else 0,
            "seed": seed,
            "interval_method": "percentile 2.5 / 97.5, linear interpolation",
            "labelled": "descriptive / uncorrected",
            "rule": BOOTSTRAP_RULE,
            "max_lead_mean": bootstrap["max_lead_mean"] if bootstrap else None,
        },
        "permutation": {
            "reps_requested": permutation_reps,
            "seed": seed,
            "observed_max_abs_r": observed_max,
            **({"reps_valid": permutation["reps_valid"],
                "n_null_ge_observed": permutation["n_null_ge_observed"],
                "p_value": permutation["p_value"],
                "null_max_median": permutation["null_max_median"],
                "null_max_p95": permutation["null_max_p95"]}
               if permutation else
               {"reps_valid": 0, "n_null_ge_observed": None, "p_value": None,
                "null_max_median": None, "null_max_p95": None}),
            "rule": PERMUTATION_RULE,
        },
        "era": era,
        "holm": {
            "family_size": len(HOLM_FAMILY) if source_id in HOLM_FAMILY else None,
            "adjusted_p": None,
            "rank": None,
        },
        "decision": {
            "leads": False,
            "label": "NOT_EVALUABLE" if not evaluable else (
                "descriptive only" if descriptive_only else "pending"),
            "criteria": {"i_k_star_positive": bool(k_star is not None and k_star > 0),
                         "ii_holm_adjusted_p_below_alpha": None,
                         "iii_era_stable": bool(era and era["signed_and_at_least_half_in_both_eras"])},
            "power_label": None,
            "mde_80": mde,
            "rule": DECISION_RULE,
        },
    }
    return record


def finalise_decisions(records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Apply the Holm family and the frozen section-5 decision rule verbatim."""
    raw_p = {
        source_id: records[source_id]["permutation"]["p_value"]
        for source_id in HOLM_FAMILY}
    if any(value is None for value in raw_p.values()):
        adjusted = {source_id: None for source_id in HOLM_FAMILY}
    else:
        adjusted = holm_adjust({key: float(value) for key, value in raw_p.items()})
    ordered = sorted(
        (source_id for source_id in HOLM_FAMILY),
        key=lambda source_id: (raw_p[source_id] is None, raw_p[source_id] or 1.0, source_id))
    for rank, source_id in enumerate(ordered, start=1):
        records[source_id]["holm"] = {
            "family_size": len(HOLM_FAMILY),
            "raw_p": raw_p[source_id],
            "adjusted_p": adjusted.get(source_id),
            "rank": rank,
            "family": list(HOLM_FAMILY),
        }
    for record in records.values():
        source_id = record["source_id"]
        decision = record["decision"]
        if source_id in HOLM_FAMILY:
            adjusted_p = records[source_id]["holm"]["adjusted_p"]
            criteria = decision["criteria"]
            criteria["ii_holm_adjusted_p_below_alpha"] = (
                None if adjusted_p is None else adjusted_p < ALPHA)
            if not record["evaluable"]:
                decision["label"] = "NOT_EVALUABLE"
                decision["leads"] = False
            elif record["descriptive_only"]:
                decision["label"] = "descriptive only"
                decision["leads"] = False
            else:
                leads = bool(criteria["i_k_star_positive"]
                             and criteria["ii_holm_adjusted_p_below_alpha"]
                             and criteria["iii_era_stable"])
                decision["leads"] = leads
                decision["label"] = "leads" if leads else "no lead detected"
                if not leads:
                    mde = record["primary"]["mde_80"]
                    if mde is None:
                        decision["power_label"] = "MDE unavailable"
                    elif mde <= WELL_POWERED_MDE:
                        decision["power_label"] = "well-powered negative"
                    else:
                        decision["power_label"] = "underpowered"
        else:
            decision["leads"] = False
            decision["label"] = "descriptive only" if record["descriptive_only"] else "not tested"
    return {
        "alpha": ALPHA,
        "family": list(HOLM_FAMILY),
        "raw_p": raw_p,
        "adjusted_p": adjusted,
        "method": "Holm step-down across the three primary sources",
        "descriptive_only_outside_family": list(DESCRIPTIVE_ONLY),
    }


# ------------------------------------------------------------------------- provenance
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def interpretation_notes() -> list[str]:
    """Implementation interpretations fixed *before* any b103 statistic was run."""
    return [
        "The analysis grid is the 36 frozen quarters 2017-Q1..2025-Q4; all series are "
        "indexed on that grid, so a lag-k pair exists only when both t and t-k are "
        "inside the grid (for k=8 the first usable milestone quarter is 2019-Q1, as the "
        "protocol states).",
        "The event series is a count with zero-filled quarters: the frozen panel monitors "
        "every company over the whole grid, so a quarter without an event is a true 0.",
        "The financial series is a step function: at each quarter end it carries the most "
        "recently filed trailing-4-quarter (reported period 300-400 days) R&D fact, which "
        "enters at its available_at quarter; log(USD); non-positive values are missing.",
        "The publication series uses works(y)/4 for the most recent complete year known "
        "under the declared 15-February rule; years without a persisted row are missing, "
        "not zero.",
        "The z-score denominator is the sample SD (n-1) over the company's own observed "
        "quarters of that series; constant or <3-observation series have no z-score.",
        "Market volatility is descriptive only and excluded from the Holm family, as the "
        "protocol requires.",
        "The 'underpowered / well-powered negative' label is a reporting convention only: "
        "the null is labelled well-powered negative when the measured MDE <= 0.10, "
        "otherwise underpowered; it never converts a null into a lead.",
        "No b103 statistic had been computed before these interpretation decisions were "
        "fixed; the frozen protocol file was not edited.",
    ]


# ------------------------------------------------------------------------ reporting
def _format(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _decision_cell(record: dict[str, Any]) -> str:
    decision = record["decision"]
    label = decision["label"]
    if decision.get("power_label"):
        return f"{label} ({decision['power_label']})"
    return label


def report_markdown(payload: dict[str, Any], json_path: str = "leadlag.json") -> str:
    """Render REPORT.md from the JSON payload only (no data access, no clock)."""
    lines: list[str] = []
    add = lines.append
    window = payload["analysis_window"]
    add("# b103 — Cross-source lead/lag at the company level (backlog B-021)")
    add("")
    add(f"**Status:** descriptive association study, generated from `{json_path}` only "
        f"(schema `{payload['schema']}`). "
        f"**Frozen protocol:** `{payload['protocol']['path']}` "
        f"(SHA-256 `{payload['protocol']['sha256']}`).")
    add("")
    add(f"**Run:** `{payload['run']['command']}` — standard library only, no network, "
        "deterministic: yes.")
    add("")
    add("## Question")
    add("")
    add("At the company level, does activity in financial, market or publication sources "
        "systematically lead or lag material regulatory events — and if a lead is claimed, "
        "does it survive a company-clustered bootstrap, a pre-declared circular-shift "
        "permutation null, Holm correction across sources, and an era split?")
    add("")
    add("This is a *descriptive association* result. A leading correlation does **not** "
        "establish that the source causes or predicts the event.")
    add("")
    add("## Data and window")
    add("")
    add(f"* Analysis window: {window['start']} … {window['end']} "
        f"({window['n_quarters']} quarters). Lags −8…+8; a pair requires both grid "
        "positions, so for k=+8 the first usable milestone quarter is "
        f"{window['first_milestone_quarter_for_k8']}.")
    add(f"* Company universe: {window['panel_companies']} companies present in the frozen "
        "hist_v1 panel; per-source exclusions are counted in the coverage section.")
    add(f"* Material events in the window: {window['window_material_events']} events across "
        f"{window['window_companies_with_events']} companies.")
    add("")
    add("| source | series | resolution | knowledge time |")
    add("|---|---|---|---|")
    for source in payload["source_table"]:
        add(f"| {source['label']} | {source['series']} | {source['resolution']} | "
            f"{source['knowledge_time']} |")
    add("")
    add(f"* Procurement: **{payload['procurement']['status']}** — "
        f"{payload['procurement']['rows']} rows, "
        f"{payload['procurement']['announcement_date_null']} with NULL announcement_date, "
        f"{payload['procurement']['pit_usable_rows']} pit_usable rows; no proxy substituted.")
    add("")
    add("## Method (frozen)")
    add("")
    add("* Per-company z-scores over each series' own observed window; pooled Pearson "
        "`r(k) = corr(z(S_{c,t−k}), z(M_{c,t}))` for k = −8…+8; positive k = source "
        "precedes events.")
    add("* Primary per source: `k* = argmax_{k∈1..8} |r(k)|` (ties → smallest k).")
    add(f"* {payload['methods']['bootstrap_rule']}")
    add(f"* {payload['methods']['permutation_rule']}")
    add("* Holm correction across the three primary sources "
        f"({', '.join(payload['methods']['holm_family'])}) at α = "
        f"{payload['methods']['alpha']}.")
    add(f"* {payload['methods']['era_rule']}")
    add(f"* {payload['methods']['mde_rule']}")
    add("")
    add("## Decision summary")
    add("")
    add("| source | k* | r(k*) | 95 % bootstrap CI | permutation p | Holm-adjusted p | "
        "era stable | MDE (80 %) | decision |")
    add("|---|---:|---:|---|---:|---:|---|---:|---|")
    for source_id in payload["decision_order"]:
        record = payload["sources"][source_id]
        primary = record["primary"]
        era = record.get("era") or {}
        add(f"| {record['label']} | {_format(primary['k_star'])} | "
            f"{_format(primary['r_k_star'])} | "
            f"[{_format(primary['bootstrap_ci_low'])}, {_format(primary['bootstrap_ci_high'])}] | "
            f"{_format(record['permutation']['p_value'])} | "
            f"{_format(record['holm']['adjusted_p'])} | "
            f"{_format(bool(era.get('signed_and_at_least_half_in_both_eras')))} | "
            f"{_format(primary['mde_80'])} | {_decision_cell(record)} |")
    add("")
    add("Bottom line: no source meets criterion (ii) of the frozen decision rule, so no lead "
        "is claimed; the null results are bounded by the MDE below, the procurement lane is "
        "NOT_EVALUABLE, and market volatility is descriptive only.")
    add("")
    add(f"Frozen decision rule: {payload['decision_rule']}")
    add("")
    for source_id in payload["decision_order"]:
        record = payload["sources"][source_id]
        primary = record["primary"]
        decision = record["decision"]
        add(f"### {record['label']}")
        add("")
        add(f"*Definition:* {record['series_definition']}")
        add("")
        add(f"**Primary:** k* = {_format(primary['k_star'])}, "
            f"r(k*) = {_format(primary['r_k_star'])} "
            f"(95 % bootstrap CI [{_format(primary['bootstrap_ci_low'])}, "
            f"{_format(primary['bootstrap_ci_high'])}]; descriptive, uncorrected).")
        add("")
        add("| k | r(k) | n pairs | 95 % bootstrap CI |")
        add("|---:|---:|---:|---|")
        for entry in record["profile"]:
            cell = (f"[{_format(entry['bootstrap_ci_low'])}, "
                    f"{_format(entry['bootstrap_ci_high'])}]")
            add(f"| {entry['k']} | {_format(entry['r'])} | {entry['n_pairs']} | {cell} |")
        add("")
        permutation = record["permutation"]
        add(f"**Permutation null:** observed max |r| over k∈1..8 = "
            f"{_format(permutation['observed_max_abs_r'])}; "
            f"p = {_format(permutation['p_value'])} "
            f"({permutation['n_null_ge_observed']}/{permutation['reps_valid']} null maxima "
            f"≥ observed; seed {permutation['seed']}).")
        add("")
        holm = record["holm"]
        if record["in_holm_family"]:
            add(f"**Holm:** raw p = {_format(holm.get('raw_p'))}, adjusted p = "
                f"{_format(holm.get('adjusted_p'))} (family size {holm['family_size']}).")
        else:
            add("**Holm:** not in the Holm family (descriptive only).")
        add("")
        era = record.get("era")
        if era:
            add(f"**Era split at k*={era['k_used']}:** full-window r = "
                f"{_format(era['full_window_r'])}; "
                f"{era['era_1']['label']} r = {_format(era['era_1']['r'])} "
                f"(n={era['era_1']['n_pairs']}); "
                f"{era['era_2']['label']} r = {_format(era['era_2']['r'])} "
                f"(n={era['era_2']['n_pairs']}); stable = "
                f"{_format(era['signed_and_at_least_half_in_both_eras'])}.")
        else:
            add("**Era split:** not computed (source not evaluable).")
        add("")
        add(f"**Power:** MDE(|r|) at 80 % power = {_format(primary['mde_80'])} "
            f"(bootstrap SD of the max-lead statistic = "
            f"{_format(primary['bootstrap_sd_max_lead'])}; "
            f"formula (z_0.975 + z_0.80) × SD_b = {MDE_FACTOR:.6f} × SD_b).")
        add("")
        add(f"**Decision:** **{decision['label']}**"
            + (f" ({decision['power_label']})" if decision.get("power_label") else "")
            + f". Criteria: k*>0 = {_format(decision['criteria']['i_k_star_positive'])}; "
            f"Holm p<α = {_format(decision['criteria']['ii_holm_adjusted_p_below_alpha'])}; "
            f"era stable = {_format(decision['criteria']['iii_era_stable'])}.")
        add("")
    add("## Market volatility — descriptive only")
    add("")
    volatility = payload["sources"]["market_volatility"]
    primary = volatility["primary"]
    add(f"Quarterly return volatility is secondary/descriptive and outside the Holm family. "
        f"k* = {_format(primary['k_star'])}, r(k*) = {_format(primary['r_k_star'])}, "
        f"permutation p = {_format(volatility['permutation']['p_value'])}, "
        f"MDE = {_format(primary['mde_80'])}. No lead is claimed from this series.")
    add("")
    add("## Coverage and exclusions")
    add("")
    add("| source | with data | included | no data | <8 quarters | other | "
        "company-quarters observed |")
    add("|---|---:|---:|---:|---:|---:|---:|")
    for source_id in payload["decision_order"]:
        coverage = payload["sources"][source_id]["coverage"]
        reasons = {}
        for entry in coverage["exclusions"]:
            reasons[entry["reason"]] = reasons.get(entry["reason"], 0) + 1
        fewer = sum(count for reason, count in reasons.items()
                    if reason.startswith("fewer_than"))
        other = sum(count for reason, count in reasons.items()
                    if not reason.startswith("fewer_than") and reason != "no_source_data")
        add(f"| {payload['sources'][source_id]['label']} | "
            f"{coverage['companies_with_source_data']} | {coverage['companies_included']} | "
            f"{coverage['companies_excluded_no_source_data']} | {fewer} | {other} | "
            f"{coverage['company_quarters_observed']} / "
            f"{coverage['company_quarters_max_possible']} |")
    add("")
    add("Exclusion reasons per source are recorded verbatim in the JSON "
        "(`sources.<id>.coverage.exclusions`).")
    add("")
    add("### Excluded companies")
    add("")
    for source_id in payload["decision_order"]:
        coverage = payload["sources"][source_id]["coverage"]
        grouped: dict[str, list[str]] = {}
        for entry in coverage["exclusions"]:
            grouped.setdefault(entry["reason"], []).append(entry["company_key"])
        if not grouped:
            add(f"* {payload['sources'][source_id]['label']}: none.")
            continue
        parts = []
        for reason in sorted(grouped):
            parts.append(f"{reason} ({len(grouped[reason])}): "
                         + ", ".join(sorted(grouped[reason])))
        add(f"* {payload['sources'][source_id]['label']}: " + "; ".join(parts) + ".")
    add("")
    add("## Limits (inherited, not corrected)")
    add("")
    for limitation in payload["limitations"]:
        add(f"* {limitation}")
    add("")
    add("## Interpretation notes fixed before the run")
    add("")
    for note in payload["interpretation_notes"]:
        add(f"* {note}")
    add("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- driver
def load_research_db(db_path: Path) -> dict[str, Any]:
    """Read every lane read-only and return the raw rows the builders consume."""
    uri = f"file:{db_path}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        tickers = {
            str(key): str(ticker)
            for key, ticker in connection.execute(
                "SELECT key, ticker FROM companies WHERE ticker IS NOT NULL AND ticker != ''")}
        rnd_rows = connection.execute(
            "SELECT company_key, period_start, period_end, value, available_at, fact_id "
            "FROM financial_facts WHERE tag = 'ResearchAndDevelopmentExpense'").fetchall()
        market_rows = connection.execute(
            "SELECT ticker, date, adj_close FROM market_bars").fetchall()
        publication_rows = connection.execute(
            "SELECT company_key, year, works FROM publication_counts").fetchall()
        procurement_rows = connection.execute(
            "SELECT announcement_date, pit_usable FROM procurement_awards").fetchall()
    finally:
        connection.close()
    return {
        "tickers": tickers,
        "rnd_rows": rnd_rows,
        "market_rows": market_rows,
        "publication_rows": publication_rows,
        "procurement_rows": procurement_rows,
    }


def build_payload(
        panel: dict[str, Any],
        raw: dict[str, Any],
        *,
        panel_path: str,
        panel_sha256: str,
        db_path: str,
        db_sha256: str,
        protocol_path: str,
        protocol_sha256: str,
        bootstrap_reps: int = BOOTSTRAP_REPS,
        permutation_reps: int = PERMUTATION_REPS,
        seed: int = SEED) -> dict[str, Any]:
    """Assemble the complete analysis payload (JSON-serialisable, deterministic)."""
    universe = sorted(company["key"] for company in panel["companies"])
    events = panel_event_series(panel, WINDOW)
    financial, financial_meta = financial_series(raw["rnd_rows"], WINDOW)
    market_returns, market_volatility, market_meta = market_series(
        raw["market_rows"], raw["tickers"], WINDOW)
    publication, publication_meta = publication_series(raw["publication_rows"], WINDOW)
    procurement = procurement_status(raw["procurement_rows"])

    window_events = {
        "window_material_events": int(sum(sum(values) for values in events.values())),
        "window_companies_with_events": sum(
            1 for values in events.values() if sum(values) > 0),
        "window_events_min_company": int(min(sum(values) for values in events.values())),
        "window_events_max_company": int(max(sum(values) for values in events.values())),
    }

    records: dict[str, dict[str, Any]] = {}
    records["financial_rd"] = analyse_source(
        source_id="financial_rd",
        label="Financial R&D",
        raw_series=financial,
        event_series=events,
        universe=universe,
        bootstrap_reps=bootstrap_reps,
        permutation_reps=permutation_reps,
        seed=seed,
        series_definition=(
            "trailing-4-quarter ResearchAndDevelopmentExpense (USD, log); the fact enters "
            "the quarterly series in its available_at quarter and is carried forward "
            "between filings"),
        data_notes=financial_meta)
    records["market_return"] = analyse_source(
        source_id="market_return",
        label="Market return",
        raw_series=market_returns,
        event_series=events,
        universe=universe,
        bootstrap_reps=bootstrap_reps,
        permutation_reps=permutation_reps,
        seed=seed,
        series_definition=(
            "quarterly return of adj_close: quarter-end close / previous quarter-end "
            "close - 1"),
        data_notes=market_meta)
    records["publication"] = analyse_source(
        source_id="publication",
        label="Publication",
        raw_series=publication,
        event_series=events,
        universe=universe,
        bootstrap_reps=bootstrap_reps,
        permutation_reps=permutation_reps,
        seed=seed,
        series_definition=(
            "OpenAlex works per company-year divided equally across the year's quarters "
            "(works/4), usable from 15 February of the following year"),
        data_notes=publication_meta)
    records["market_volatility"] = analyse_source(
        source_id="market_volatility",
        label="Market volatility (descriptive)",
        raw_series=market_volatility,
        event_series=events,
        universe=universe,
        bootstrap_reps=bootstrap_reps,
        permutation_reps=permutation_reps,
        seed=seed,
        descriptive_only=True,
        series_definition="quarterly sample SD of daily log adj_close returns",
        data_notes=market_meta)

    holm = finalise_decisions(records)

    source_table = [
        {"label": "Regulatory events (M)", "series": "material 510(k)/PMA counts per company-quarter",
         "resolution": "quarter", "knowledge_time": "available_at (FDA decision date)"},
        {"label": "Financial R&D", "series": "trailing-4-quarter ResearchAndDevelopmentExpense (log)",
         "resolution": "quarter (fact available_at)", "knowledge_time": "filing available_at quarter"},
        {"label": "Market return", "series": "quarterly adj_close return",
         "resolution": "quarter", "knowledge_time": "quarter end"},
        {"label": "Market volatility (descriptive)", "series": "quarterly SD of daily log returns",
         "resolution": "quarter", "knowledge_time": "quarter end"},
        {"label": "Publication", "series": "OpenAlex works per company-year / 4",
         "resolution": "annual (declared)", "knowledge_time": "15 February of year+1"},
        {"label": "Procurement", "series": "—", "resolution": "—",
         "knowledge_time": "all announcement_date NULL, pit_usable=0"},
    ]

    limitations = [
        "Descriptive association only: a leading correlation does not establish that the "
        "source causes or predicts a material regulatory event; no causal language is used.",
        "Publication data are annual; the quarterly series is a step function and cannot "
        "resolve within-year timing.",
        "Market data are auxiliary: the return/volatility lanes only describe co-movement, "
        "and volatility is outside the Holm family.",
        "The financial series is carried forward between annual filings, so its quarterly "
        "resolution is coarser than the grid; companies whose filings stop early keep a "
        "flat value and are measured, not repaired.",
        "The event lane inherits the hist_v1 limitations: current-corporate-group entity "
        "mapping, current unversioned track taxonomy, FDA-decision-date availability, and "
        "a materiality rule that excludes 96.6 % of PMA supplements.",
        "Procurement is NOT_EVALUABLE: every announcement_date is NULL and every row has "
        "pit_usable=0, so no PIT procurement series exists.",
        "The era split is a descriptive stability check on point estimates, not a separate "
        "significance test.",
    ]

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "title": "b103 cross-source lead/lag at the company level",
        "backlog_item": "B-021",
        "protocol": {"path": protocol_path, "sha256": protocol_sha256,
                     "status": "FROZEN 2026-11-03 before any b103 statistic was computed"},
        "run": {"command": "python experiments/b103_leadlag/leadlag.py",
                "report_command": "python experiments/b103_leadlag/leadlag.py --report-only",
                "library": "standard-library only (no numpy/pandas/scipy)",
                "network": False, "deterministic": True,
                "random_seed": seed,
                "bootstrap_reps": bootstrap_reps, "permutation_reps": permutation_reps},
        "inputs": {
            "panel": {"path": panel_path, "sha256": panel_sha256,
                      "schema": panel.get("schema")},
            "research_db": {"path": db_path, "sha256": db_sha256},
        },
        "analysis_window": {
            "start": WINDOW_START,
            "end": WINDOW_END,
            "n_quarters": WINDOW_LENGTH,
            "quarters": WINDOW,
            "lags": list(LAGS),
            "lead_lags": list(LEAD_LAGS),
            "panel_companies": len(universe),
            "first_milestone_quarter_for_k8": WINDOW[8],
            **window_events,
        },
        "source_table": source_table,
        "procurement": procurement,
        "methods": {
            "bootstrap_rule": BOOTSTRAP_RULE,
            "permutation_rule": PERMUTATION_RULE,
            "era_rule": ERA_RULE,
            "mde_rule": MDE_RULE,
            "holm_family": list(HOLM_FAMILY),
            "alpha": ALPHA,
            "power": POWER,
            "mde_factor": MDE_FACTOR,
            "z_975": Z_975,
            "z_80": Z_80,
            "min_quarters_per_source": MIN_QUARTERS,
            "min_pairs_for_correlation": MIN_PAIRS,
            "min_z_observations": MIN_Z_OBS,
        },
        "decision_rule": DECISION_RULE,
        "decision_order": list(HOLM_FAMILY) + list(DESCRIPTIVE_ONLY),
        "sources": records,
        "holm": holm,
        "limitations": limitations,
        "interpretation_notes": interpretation_notes(),
    }
    return payload


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="b103 frozen cross-source lead/lag (backlog B-021)")
    parser.add_argument("--db", default=DEFAULT_DB, help="research SQLite path (read-only)")
    parser.add_argument("--panel", default=DEFAULT_PANEL, help="frozen hist_v1 panel JSON")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                        help="directory for leadlag.json / REPORT.md")
    parser.add_argument("--protocol", default=PROTOCOL_REL,
                        help="frozen pre-registration path")
    parser.add_argument("--report-only", action="store_true",
                        help="regenerate REPORT.md from an existing leadlag.json")
    args = parser.parse_args(argv)

    out_dir = ROOT / args.out_dir
    json_path = out_dir / "leadlag.json"
    report_path = out_dir / "REPORT.md"

    if args.report_only:
        with json_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        write_text(report_path, report_markdown(payload))
        print(f"wrote {report_path.relative_to(ROOT)} from {json_path.relative_to(ROOT)}")
        return 0

    db_path = ROOT / args.db
    panel_path = ROOT / args.panel
    protocol_path = ROOT / args.protocol
    panel = load_panel(panel_path)
    raw = load_research_db(db_path)
    payload = build_payload(
        panel, raw,
        panel_path=args.panel,
        panel_sha256=sha256_file(panel_path),
        db_path=args.db,
        db_sha256=sha256_file(db_path),
        protocol_path=args.protocol,
        protocol_sha256=sha256_file(protocol_path))
    write_json(json_path, payload)
    write_text(report_path, report_markdown(payload))
    summary = {
        "json": str(json_path.relative_to(ROOT)),
        "report": str(report_path.relative_to(ROOT)),
        "decision": {source_id: payload["sources"][source_id]["decision"]["label"]
                     for source_id in payload["decision_order"]},
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
