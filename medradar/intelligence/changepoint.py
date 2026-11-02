"""Change-point detectors for the OBSERVE layer: has a cell's activity rate changed?

A *stream* is a list of ``(date_iso_string, count)`` pairs in ascending monthly
order (``count >= 0``, integer-valued).  A *detection* is a plain ``dict`` with the
keys documented in :func:`_detection`; every detector returns a list holding at
most one detection (the first declaration) and ``[]`` otherwise.

The four detectors
==================

``detect_naive_threshold``
    The baseline comparator: trailing ``NAIVE_OBSERVED_WINDOW``-month rate versus
    the rate over *all* months before that window.  Declares when the trailing
    rate exceeds ``multiplier`` times the baseline rate.  It has no notion of
    persistence, uncertainty or window length: it is the straw man a real
    detector must beat, kept because the harness needs the comparison.

``detect_rolling_zscore``
    Normal approximation to the count distribution: the last ``window`` months are
    compared with the preceding ``window`` months.  The z-score is the
    variance-stabilised (Anscombe) one,
    ``z = (2 sqrt(C + 3/8) - 2 sqrt(R + 3/8)) / sqrt(2)``, where ``C`` and ``R``
    are the observed and reference-window event totals.  Two-sided: it can
    declare ``"down"`` as well as ``"up"``.  The plain Poisson z
    ``(C - R) / sqrt(R)`` was measured on the real corpus to alarm on ~70% of
    uninjected cells at the default threshold (its normal approximation is far
    too optimistic at 0-3 events/month); the Anscombe form alarms on ~12% and
    keeps a coherent "N standard deviations" reading of the same threshold.

``detect_poisson_cusum``
    Page's one-sided CUSUM in log-likelihood-ratio form for a Poisson rate increase.
    The baseline rate ``mu0`` is estimated at every candidate change point from the
    ``baseline_window`` months before it (re-estimated locally, so slow drift does
    not poison the reference).  The target rate is
    ``mu1 = mu0 + max(drift, drift * mu0)``: a 50% increase for dense cells and at
    least an absolute ``drift`` events/month floor for sparse ones (see
    :func:`_cusum_target`).  Increments are
    ``x * ln(mu1 / mu0) - (mu1 - mu0)`` accumulated with a ``max(0, .)`` floor;
    the first month whose CUSUM statistic crosses ``threshold`` is the alarm.

``detect_poisson_bayes_factor``
    Bayesian Poisson rate-change statistic.  At every month it compares
    *"the rate changed at some point in the last ``baseline_window`` months"*
    (two Poisson-Gamma segments split at ``tau``, ``Gamma(prior_shape, prior_rate)``
    prior on each rate) with *"the rate is constant"* (one segment).  The log Bayes
    factor is averaged over the candidate change points ``tau`` (uniform mixture,
    log-sum-exp) rather than maximised, which penalises a split that only one
    month supports.  The declared index is the *latest* ``tau`` whose single-split
    log Bayes factor is within ``BAYES_INDEX_TOLERANCE`` nats of the best one: when
    the evidence cannot separate neighbouring change points the detector reports
    the later one, so it never claims the change began earlier than the data force
    it to.  Two-sided: a decrease is declared ``"down"``.

Common design decisions
=======================

* **Causal declaration.**  A detector only ever uses months up to the month it
  alarms on, so ``index`` can be later than the true onset and never earlier.
  ``index`` is the alarm month for the naive, z-score and CUSUM detectors, and the
  reported change point for the Bayes factor.  ``date`` is
  ``stream[index][0]`` verbatim; dates are never parsed, re-sorted or invented.
* **Reporting fields.**  ``baseline_rate`` is the mean count over **all months
  before** ``index`` and ``observed_rate`` is the mean count over **all months at
  or after** ``index`` (the look-ahead the contract allows).  These fields are
  descriptive, not the triggering statistic: ``observed_rate`` on a
  spike-then-revert stream is diluted by the reversion, which is exactly the
  signal that the elevation did not persist.  The triggering value is
  ``statistic``.
* **Determinism.**  No randomness, no clock, no hash ordering, no floating-point
  order dependence that matters: identical input gives an identical list, and the
  input stream is never mutated.
* **Degenerate input returns ``[]`` and never raises.**  This covers an empty or
  one-point stream, malformed rows (non-string date, negative/non-integer count),
  an all-zero stream, a stream that has not yet accumulated
  ``min_baseline_events`` events, histories shorter than the detector's minimum,
  and invalid parameters (non-positive thresholds, ``window < 2``, ...).  Treating
  bad input as "nothing to report" is deliberate: the OBSERVE harness must not
  crash on odd cells.
* **At most one detection per stream.**  There is no ``warm_start`` parameter; the
  harness wants the first declaration only.
* **Defaults.**  The keyword defaults are the contract's and are deliberately
  conservative for one-detection-per-stream use; the sensitivity knobs are meant to
  be calibrated per detector.  Measured false-alarm and detection behaviour on the
  real 120-month corpus, the threshold sweeps and the operational caveats are in
  ``docs/research/CHANGEPOINT.md``.

What these detectors assume (and therefore what they do not see)
================================================================

1. **Constant exposure.**  The count is assumed to be a Poisson draw with a
   monthly rate that is constant between change points.  The stream is monthly
   *calendar* data with no offset, so a change in the population of filings
   (a new regulatory pathway, a resumed collection feed, a product-line
   reclassification) produces a rate change indistinguishable from a real
   activity change.  A detection is a statement about the *rate of observed
   public regulatory events in a cell*, never about intent, capability, internal
   R&D or future performance.
2. **No seasonality.**  None of the detectors removes a monthly or quarterly
   pattern.  A cell whose filings cluster around a recurring cycle (budget
   months, advisory-committee calendar, fiscal-year end) can look like a change
   every year; the z-score detector is the most exposed to this because one
   window is compared with the previous one.
3. **Sparse counts.**  Most MedRadar cells are extremely sparse (median ~98
   zero-months out of 120 for eligible real cells).  At these rates the normal
   approximation in ``detect_rolling_zscore`` is weak and a *single* filing can
   be a large relative change.  The minimum-event guards exist for exactly this
   reason; they are ceilings on false alarms, not guarantees.
4. **Clustered events.**  Regulatory filings arrive in bursts (one product
   family, one submission campaign).  A burst is a real short-run rate increase
   but not a regime change; all four detectors can declare one if it is large
   enough.  The Bayes factor is the most resistant (it must fit a sustained
   two-segment split against a slightly informative ``Gamma(1, 1)`` prior), the
   naive comparator and the CUSUM are the least resistant.
5. **Single change point.**  The detectors search for one change in a fixed
   window; two changes close together, a slow ramp, or a mean-reverting pulse are
   all collapsed into "one change" or missed.

A detection is a statistical statement about an event rate.  It is not evidence
of intent, strategy or capability, and it is not a forecast.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

__all__ = [
    "DETECTORS",
    "detect_naive_threshold",
    "detect_rolling_zscore",
    "detect_poisson_cusum",
    "detect_poisson_bayes_factor",
    "MIN_BASELINE_MONTHS",
    "NAIVE_OBSERVED_WINDOW",
    "NAIVE_MIN_OBSERVED_EVENTS",
    "BAYES_MIN_POST_MONTHS",
    "BAYES_INDEX_TOLERANCE",
]

#: Shortest history (months) any detector may declare a change with.
MIN_BASELINE_MONTHS = 3

#: Shortest stream (months) worth scanning at all.
MIN_STREAM_MONTHS = 2

#: Trailing window of the naive comparator, in months.  Three months is the
#: shortest window in which a rate can exceed a sparse baseline without a single
#: month deciding the answer (one event/month would otherwise fire constantly).
NAIVE_OBSERVED_WINDOW = 3

#: Minimum events inside the naive comparator's trailing window.  A rate ratio
#: is meaningless when it is estimated from one or two events, and a cluster of
#: two or three filings is the normal texture of a sparse cell; six events in
#: three months is a level the corpus only reaches during a sustained burst.
NAIVE_MIN_OBSERVED_EVENTS = 6

#: Minimum months of post-change data a Bayes-factor candidate split must have.
#: Without it the mixture would spend its evidence budget on the last month or
#: two of a stream and a single spike would dominate.
BAYES_MIN_POST_MONTHS = 3

#: How many natural-log units from the best single-split Bayes factor a change
#: point may be and still be reported.  Among such near-indistinguishable splits
#: the latest is reported, so a declaration never dates the change earlier than
#: the evidence requires (a one-month burst is not localisable to a month).
BAYES_INDEX_TOLERANCE = 2.0


# --------------------------------------------------------------------- validation
def _coerce_count(value: Any) -> int | None:
    """Return the count as a non-negative ``int`` or ``None`` if unusable."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return None
        return int(value)
    return None


def _prepare(stream: Any) -> tuple[list[str], list[int]] | None:
    """Coerce a stream to ``(dates, counts)``; ``None`` means "return []".

    Malformed input is a degenerate stream, not an exception: the OBSERVE layer
    runs over thousands of cells and one odd row must not abort a run.
    """
    try:
        rows = list(stream)
    except TypeError:
        return None
    dates: list[str] = []
    counts: list[int] = []
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            return None
        date, raw_count = row
        if not isinstance(date, str):
            return None
        count = _coerce_count(raw_count)
        if count is None or count < 0:
            return None
        dates.append(date)
        counts.append(count)
    if len(counts) < MIN_STREAM_MONTHS:
        return None
    if max(counts) <= 0:  # all-zero stream: there is no rate to compare
        return None
    return dates, counts


def _is_positive(value: Any) -> bool:
    """True for a finite, strictly positive real (used for parameter guards)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0.0


def _positive_int(value: Any) -> int | None:
    """Coerce a parameter to an ``int >= 1``; ``None`` when invalid."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 1 else None


# ----------------------------------------------------------------------- reporting
def _reported_rates(counts: Sequence[int], index: int) -> tuple[float, float]:
    """Events/month before ``index`` and at/after ``index`` (see module docstring)."""
    baseline = counts[:index]
    observed = counts[index:]
    baseline_rate = (sum(baseline) / len(baseline)) if baseline else 0.0
    observed_rate = (sum(observed) / len(observed)) if observed else 0.0
    return float(baseline_rate), float(observed_rate)


def _detection(dates: Sequence[str], counts: Sequence[int], index: int, direction: str,
               statistic: float, threshold: float) -> dict[str, Any]:
    """Build the one detection dict the harness consumes.

    Keys (contract): ``index`` (position in the stream where the change is
    declared), ``date`` (``stream[index][0]``), ``direction`` (``"up"``/``"down"``),
    ``statistic`` (the detector's value at declaration), ``threshold`` (the value
    it crossed), ``baseline_rate`` (events/month before ``index``) and
    ``observed_rate`` (events/month at/after ``index``).
    """
    baseline_rate, observed_rate = _reported_rates(counts, index)
    return {
        "index": int(index),
        "date": dates[index],
        "direction": direction,
        "statistic": float(statistic),
        "threshold": float(threshold),
        "baseline_rate": baseline_rate,
        "observed_rate": observed_rate,
    }


# ----------------------------------------------------------------- 1. naive
def detect_naive_threshold(stream: Sequence[Sequence[Any]], *, multiplier: float = 3.0,
                           min_baseline_events: int = 3) -> list[dict[str, Any]]:
    """Declare when the trailing rate exceeds ``multiplier`` x the earlier rate.

    The baseline is every month before the trailing ``NAIVE_OBSERVED_WINDOW``-month
    observation window; the statistic is the ratio of the two rates.  Two guards
    keep it from firing on sparse noise: the baseline must contain at least
    ``min_baseline_events`` events (a ratio against a rate estimated from one or
    two events is meaningless) and the observation window must contain at least
    ``NAIVE_MIN_OBSERVED_EVENTS`` events.

    One-sided ("up" only) and deliberately naive: it has no notion of
    persistence, so a single large spike is declared a change.  It is the
    baseline every other detector must beat, not the detector to trust.
    """
    if not _is_positive(multiplier):
        return []
    minimum_baseline = _positive_int(min_baseline_events)
    if minimum_baseline is None:
        return []
    prepared = _prepare(stream)
    if prepared is None:
        return []
    dates, counts = prepared
    n = len(counts)
    for alarm in range(MIN_BASELINE_MONTHS + NAIVE_OBSERVED_WINDOW - 1, n):
        start = alarm - NAIVE_OBSERVED_WINDOW + 1
        baseline = counts[:start]
        if len(baseline) < MIN_BASELINE_MONTHS:
            continue
        baseline_total = sum(baseline)
        if baseline_total < minimum_baseline:
            continue
        baseline_rate = baseline_total / len(baseline)
        if baseline_rate <= 0.0:
            continue
        window = counts[start:alarm + 1]
        window_total = sum(window)
        if window_total < NAIVE_MIN_OBSERVED_EVENTS:
            continue
        ratio = (window_total / len(window)) / baseline_rate
        if ratio > multiplier:
            return [_detection(dates, counts, alarm, "up", ratio, multiplier)]
    return []


# ---------------------------------------------------------------- 2. z-score
def detect_rolling_zscore(stream: Sequence[Sequence[Any]], *, window: int = 12,
                          min_window_events: int = 5,
                          threshold: float = 3.0) -> list[dict[str, Any]]:
    """Rolling two-window z-score on the Poisson normal approximation.

    The last ``window`` months (total ``C`` events) are compared with the
    ``window`` months immediately before them (total ``R`` events) with the
    variance-stabilised score ``z = (2 sqrt(C + 3/8) - 2 sqrt(R + 3/8)) / sqrt(2)``.
    Declares when ``|z| > threshold``: ``"up"`` when ``z > 0`` and ``"down"`` when
    ``z < 0``.

    ``min_window_events`` guards the approximation.  For an upward declaration the
    *observed* window must contain at least that many events; for a downward one
    the *reference* window must (an observed count of zero is a legitimate
    decrease, so the floor cannot live on the observed side).  Needs at least
    ``2 * window`` months of stream before it can say anything.

    A single large spike inside the observed window is declared: the window, not
    the month, is the unit of this detector.  A 12-vs-12 comparison is also the
    most false-alarm-prone of the four on sparse counts, because one year is a
    short reference and real filings are bursty.
    """
    if not _is_positive(threshold):
        return []
    window_months = _positive_int(window)
    if window_months is None or window_months < 2:
        return []
    minimum_events = _positive_int(min_window_events)
    if minimum_events is None:
        return []
    prepared = _prepare(stream)
    if prepared is None:
        return []
    dates, counts = prepared
    n = len(counts)
    if n < 2 * window_months:
        return []
    for alarm in range(2 * window_months - 1, n):
        observed = counts[alarm - window_months + 1:alarm + 1]
        reference = counts[alarm - 2 * window_months + 1:alarm - window_months + 1]
        reference_total = sum(reference)
        if reference_total <= 0:
            continue
        observed_total = sum(observed)
        # Anscombe variance-stabilised difference of two Poisson totals.
        z_score = (2.0 * math.sqrt(observed_total + 0.375)
                   - 2.0 * math.sqrt(reference_total + 0.375)) / math.sqrt(2.0)
        if z_score > threshold and observed_total >= minimum_events:
            return [_detection(dates, counts, alarm, "up", z_score, threshold)]
        if z_score < -threshold and reference_total >= minimum_events:
            return [_detection(dates, counts, alarm, "down", z_score, threshold)]
    return []


# ------------------------------------------------------------------ 3. CUSUM
def _cusum_target(baseline_rate: float, drift: float) -> float:
    """Rate the CUSUM is designed to detect: ``mu0 + max(drift, drift * mu0)``.

    A purely relative target would chase a +0.05 events/month shift in a cell that
    fires 0.1 times a month, which is noise at these counts; a purely absolute one
    would miss a doubling of a dense cell.  The floor ``drift`` events/month is the
    smallest shift that monthly sparse data can resolve, above which a ``drift``
    fraction of the baseline is used.
    """
    return baseline_rate + max(drift, drift * baseline_rate)


def detect_poisson_cusum(stream: Sequence[Sequence[Any]], *, baseline_window: int = 24,
                         threshold: float = 5.0, drift: float = 0.5,
                         min_baseline_events: int = 3) -> list[dict[str, Any]]:
    """One-sided Poisson CUSUM for a rate increase (log-likelihood-ratio form).

    Every month from ``MIN_BASELINE_MONTHS`` on is treated as a candidate change
    point ``s``: ``mu0`` is re-estimated from the ``baseline_window`` months before
    ``s`` (a local reference, so slow drift does not poison it), the target rate
    ``mu1`` comes from :func:`_cusum_target`, and the CUSUM increments
    ``x * ln(mu1 / mu0) - (mu1 - mu0)`` are accumulated with a zero floor over
    ``counts[s:]``.  The earliest alarm month ``t`` across all candidates is
    declared; ties go to the longest baseline (smallest ``s``).  The declared
    ``index`` is ``t``, so it can never precede the true onset.

    One-sided ("up" only).  A single very large spike is enough to cross the
    threshold: CUSUM has no persistence requirement.
    """
    if not _is_positive(threshold) or not _is_positive(drift):
        return []
    window_months = _positive_int(baseline_window)
    if window_months is None:
        return []
    minimum_baseline = _positive_int(min_baseline_events)
    if minimum_baseline is None:
        return []
    prepared = _prepare(stream)
    if prepared is None:
        return []
    dates, counts = prepared
    n = len(counts)
    best: tuple[int, int, float] | None = None
    for change in range(MIN_BASELINE_MONTHS, n - 1):
        start = max(0, change - window_months)
        baseline = counts[start:change]
        if len(baseline) < 2:
            continue
        baseline_total = sum(baseline)
        if baseline_total < minimum_baseline:
            continue
        mu0 = baseline_total / len(baseline)
        if mu0 <= 0.0:
            continue
        mu1 = _cusum_target(mu0, drift)
        log_ratio = math.log(mu1 / mu0)
        offset = mu1 - mu0
        statistic = 0.0
        for alarm in range(change, n):
            statistic = statistic + counts[alarm] * log_ratio - offset
            if statistic < 0.0:
                statistic = 0.0
            if statistic > threshold:
                if best is None or alarm < best[0]:
                    best = (alarm, change, statistic)
                break
    if best is None:
        return []
    alarm, _change, statistic = best
    return [_detection(dates, counts, alarm, "up", statistic, threshold)]


# ------------------------------------------------------------ 4. Bayes factor
def detect_poisson_bayes_factor(stream: Sequence[Sequence[Any]], *, baseline_window: int = 24,
                                threshold: float = 10.0, prior_shape: float = 1.0,
                                prior_rate: float = 1.0,
                                min_baseline_events: int = 3) -> list[dict[str, Any]]:
    """Bayesian Poisson rate-change detector (log Bayes factor, natural log).

    At every month ``t`` and every candidate change point
    ``tau in [t - baseline_window + 1, t - BAYES_MIN_POST_MONTHS + 1]`` the
    log Bayes factor compares a two-segment Poisson-Gamma model (independent
    ``Gamma(prior_shape, prior_rate)`` priors on the pre- and post-change rates)
    with a single-rate model on the same data.  The marginal likelihood of a
    segment with total ``S`` over ``L`` months is closed-form::

        log p(data | Gamma(a, b)) = a ln b - ln Gamma(a)
                                   + ln Gamma(a + S) - (a + S) ln(b + L)

    (the ``prod 1 / x_i!`` factors cancel between the two models).  The candidate
    log Bayes factors are averaged with a uniform prior over ``tau`` using the
    log-sum-exp identity, so the statistic is the evidence for *some* change in the
    window rather than the best single split.  Declares when the average natural-log
    Bayes factor exceeds ``threshold`` and reports the ``tau`` with the largest
    single-split log Bayes factor as ``index``.

    Two-sided: a sustained decrease is declared ``"down"``.  The
    ``Gamma(1, 1)`` prior (mean rate 1 event/month, but very flat) regularises
    sparse segments and is what makes short bursts fail to reach the threshold.
    It is not tuned to the whole corpus: it is the pre-declared default and the
    harness is expected to calibrate ``threshold``.
    """
    if not _is_positive(threshold) or not _is_positive(prior_shape) or not _is_positive(prior_rate):
        return []
    window_months = _positive_int(baseline_window)
    if window_months is None:
        return []
    minimum_baseline = _positive_int(min_baseline_events)
    if minimum_baseline is None:
        return []
    prepared = _prepare(stream)
    if prepared is None:
        return []
    dates, counts = prepared
    n = len(counts)

    shape = float(prior_shape)
    rate = float(prior_rate)
    prior_constant = shape * math.log(rate) - math.lgamma(shape)

    def log_marginal(total: int, length: int) -> float:
        """Marginal log-likelihood of one Poisson-Gamma segment (up to a constant)."""
        return (prior_constant + math.lgamma(shape + total)
                - (shape + total) * math.log(rate + length))

    totals = [0] * (n + 1)
    for position, count in enumerate(counts):
        totals[position + 1] = totals[position] + count

    for alarm in range(MIN_STREAM_MONTHS, n):
        last_change = alarm - BAYES_MIN_POST_MONTHS + 1
        first_change = max(MIN_BASELINE_MONTHS, alarm - window_months + 1)
        if last_change < first_change:
            continue
        total_all = totals[alarm + 1]
        length_all = alarm + 1
        log_null = log_marginal(total_all, length_all)
        log_factors: list[tuple[int, float]] = []
        for change in range(first_change, last_change + 1):
            pre_total = totals[change]
            if pre_total < minimum_baseline:
                continue
            post_total = total_all - pre_total
            log_factor = (log_marginal(pre_total, change)
                          + log_marginal(post_total, length_all - change)
                          - log_null)
            log_factors.append((change, log_factor))
        if not log_factors:
            continue
        peak = max(log_factor for _change, log_factor in log_factors)
        average = peak + math.log(sum(math.exp(log_factor - peak)
                                      for _change, log_factor in log_factors))
        average -= math.log(len(log_factors))
        if average > threshold:
            # Latest change point the evidence cannot separate from the best one.
            change = max(candidate for candidate, log_factor in log_factors
                         if log_factor >= peak - BAYES_INDEX_TOLERANCE)
            baseline_rate, observed_rate = _reported_rates(counts, change)
            direction = "up" if observed_rate >= baseline_rate else "down"
            return [_detection(dates, counts, change, direction, average, threshold)]
    return []


# --------------------------------------------------------------------- registry
#: Stable detector names used by the OBSERVE evaluation harness.  Keys are part
#: of the contract; the values are the pure functions above.
DETECTORS: dict[str, Any] = {
    "naive_multiplier": detect_naive_threshold,
    "rolling_zscore": detect_rolling_zscore,
    "poisson_cusum": detect_poisson_cusum,
    "poisson_bayes_factor": detect_poisson_bayes_factor,
}
