"""Research statistics: dependency-free, deterministic, and documented.

Why this module exists
----------------------
The metric engine (``analyze``), the event study (``eventstudy``) and the paper
trader (``paper``) all quote "the mean abnormal return was +X%". A mean without a
valid interval is a rumour. This module is the single place where the numbers get
their uncertainty, and it is deliberately **pure**: no I/O, no network, no
globals, no third-party imports (standard library only), every random draw behind
an explicit seed. That makes each function unit-testable and re-runnable to the
last digit.

The four statistical problems this repo actually has
----------------------------------------------------
1. **Overlapping windows.** A 20-day abnormal return and the next 20-day abnormal
   return overlap by 19 days. Observations are therefore *not* independent: the
   effective sample size is the number of event days, not the number of events.
   An i.i.d. bootstrap (``util.bootstrap_ci``) understates the interval width.
   :func:`block_bootstrap_ci` resamples **whole event days** and is the default
   for every event-study interval in this repo.
2. **Many looks.** 5 signal kinds x 4 horizons = 20 one-sided-ish tests. A t of 2
   is not evidence after 20 looks. :func:`bonferroni` and :func:`holm` adjust for
   this; :func:`aggregate_event_study` reports Holm-adjusted p-values by default.
3. **Time-dependent structure.** Anything tuned on the full history is in-sample
   by construction. :func:`time_split` cuts dev/validation/holdout by *event day*
   so a day is never shared between phases (which would leak through exactly the
   block structure used above).
4. **Missing the losers.** Free price data drops delisted/acquired tickers, which
   flatters any long-only book. :func:`survivorship_flags` marks the entities we
   cannot price instead of quietly excluding them.

Conventions
-----------
* Returns are **fractions**: ``0.01`` means +1%.
* ``p`` values are two-sided; ``alpha`` is the family-wise threshold.
* Bootstrap intervals are **percentile** intervals with the same index convention
  as :func:`medradar.util.bootstrap_ci` (so a report can mix both without
  re-explaining the endpoints).
* Every function returns plain ``dict``/``list``/``float``/``None`` - JSON ready.

Math notes are inline in each docstring. Nothing here is fitted to returns: the
module is descriptive machinery, not a strategy.
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable, Iterable, Mapping, Sequence

DEFAULT_SEED = 7
DEFAULT_ALPHA = 0.05
DEFAULT_N_BOOT = 2000

__all__ = [
    # descriptive
    "mean",
    "median",
    "stdev",
    "t_stat",
    "ranks",
    "pearson",
    "spearman",
    "mae",
    # distributions
    "normal_cdf",
    "normal_ppf",
    "student_t_sf",
    "t_p_value",
    # multiplicity
    "bonferroni",
    "holm",
    "multiple_testing",
    # resampling
    "block_bootstrap_ci",
    "aggregate_event_study",
    # design
    "time_split",
    "time_split_by_dates",
    "equal_weights",
    "market_cap_weights",
    "normalize_weights",
    "weighted_mean",
    "survivorship_flags",
    "mde",
    "required_n",
    "power_hint",
    "research_block",
]


# ----------------------------------------------------------------------- numbers
def _num(value: Any) -> float | None:
    """Coerce to ``float``; ``None`` for missing / non-numeric / NaN / inf."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def mean(values: Sequence[float] | Iterable[float]) -> float | None:
    """Arithmetic mean; ``None`` when the sequence is empty."""
    clean = [v for v in (_num(x) for x in values) if v is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def median(values: Sequence[float] | Iterable[float]) -> float | None:
    """Median (average of the two middle values for even n)."""
    clean = sorted(v for v in (_num(x) for x in values) if v is not None)
    n = len(clean)
    if not n:
        return None
    mid = n // 2
    return clean[mid] if n % 2 else 0.5 * (clean[mid - 1] + clean[mid])


def stdev(values: Sequence[float] | Iterable[float], ddof: int = 1) -> float | None:
    """Sample standard deviation (``ddof=1`` by default); ``None`` when undefined.

    ``s^2 = sum((x_i - x_bar)^2) / (n - ddof)``
    """
    clean = [v for v in (_num(x) for x in values) if v is not None]
    n = len(clean)
    if n <= ddof:
        return None
    mu = sum(clean) / n
    return math.sqrt(sum((x - mu) ** 2 for x in clean) / (n - ddof))


def t_stat(values: Sequence[float] | Iterable[float]) -> float | None:
    """One-sample t statistic against zero: ``t = x_bar / (s / sqrt(n))``.

    ``None`` when ``n < 2`` or the sample has no variance (all values equal),
    because the ratio has no meaning then - this repo reports ``None`` rather
    than the ``inf`` that would poison a table.
    """
    clean = [v for v in (_num(x) for x in values) if v is not None]
    n = len(clean)
    if n < 2:
        return None
    mu = sum(clean) / n
    var = sum((x - mu) ** 2 for x in clean) / (n - 1)
    if var <= 0:
        return None
    return mu / math.sqrt(var / n)


# ------------------------------------------------------------------------- ranks
def ranks(values: Sequence[float]) -> list[float]:
    """Average ("mid") ranks, 1-based, ties share the mean of their positions.

    Needed for Spearman: ``rho = pearson(rank(x), rank(y))``. Average ranks keep
    the correlation well defined when the materiality rubric produces ties.
    """
    clean = [float(v) for v in values]
    order = sorted(range(len(clean)), key=lambda i: clean[i])
    out = [0.0] * len(clean)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and clean[order[j + 1]] == clean[order[i]]:
            j += 1
        average_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = average_rank
        i = j + 1
    return out


def pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Pearson product-moment correlation; ``None`` if undefined or zero variance."""
    if len(x) != len(y) or not x:
        return None
    a = [float(v) for v in x]
    b = [float(v) for v in y]
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((p - ma) * (q - mb) for p, q in zip(a, b))
    da = math.sqrt(sum((p - ma) ** 2 for p in a))
    db = math.sqrt(sum((q - mb) ** 2 for q in b))
    if da == 0 or db == 0:
        return None
    return num / (da * db)


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Spearman rank correlation: Pearson correlation of the average ranks.

    Robust to the monotone-but-nonlinear judgement of a human rubric, which is
    how materiality is actually recorded (0.15/0.2/0.5 as anchors, not a metric
    scale). ``rho = 1 - 6*sum(d_i^2)/(n(n^2-1))`` is the tie-free shortcut;
    this implementation uses average ranks so ties are handled correctly.
    """
    if len(x) != len(y) or not x:
        return None
    return pearson(ranks(x), ranks(y))


def mae(truth: Sequence[float], prediction: Sequence[float]) -> float | None:
    """Mean absolute error: ``(1/n) * sum(|truth_i - prediction_i|)``."""
    if len(truth) != len(prediction) or not truth:
        return None
    total = sum(abs(float(a) - float(b)) for a, b in zip(truth, prediction))
    return total / len(truth)


# ------------------------------------------------------------------ distribution
def normal_cdf(z: float) -> float:
    """Standard normal CDF ``Phi(z) = 0.5 * erfc(-z / sqrt(2))``."""
    return 0.5 * math.erfc(-float(z) / math.sqrt(2.0))


def normal_ppf(p: float) -> float | None:
    """Inverse standard normal CDF (quantile), by bisection on :func:`normal_cdf`.

    Tails are clipped to ``[1e-12, 1-1e-12]`` so the search never diverges; the
    1e-10 absolute tolerance is far below anything a returns table can resolve.
    """
    p = float(p)
    if not (0.0 < p < 1.0):
        return None
    low, high = -12.0, 12.0
    for _ in range(200):
        mid = 0.5 * (low + high)
        if normal_cdf(mid) < p:
            low = mid
        else:
            high = mid
        if high - low < 1e-10:
            break
    return 0.5 * (low + high)


_FPMIN = 1e-300
_BETA_EPS = 3e-12
_BETA_MAX_ITER = 300


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method).

    This is the classic Numerical-Recipes ``betacf``; it converges in a few dozen
    iterations for the ``a, b`` values a t-distribution needs.
    """
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _FPMIN:
        d = _FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, _BETA_MAX_ITER + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _BETA_EPS:
            break
    return h


def _incomplete_beta(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta ``I_x(a,b)`` in ``[0, 1]``."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    front = math.exp(log_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_sf(t: float, df: float) -> float | None:
    """Upper tail ``P(T > t)`` of Student's t with ``df`` degrees of freedom.

    ``P(T > t) = 0.5 * I_{df/(df+t^2)}(df/2, 1/2)`` for ``t >= 0`` and the mirror
    for ``t < 0``. We need it only to turn a t statistic into a p-value for the
    multiple-testing step; ``None`` for ``df <= 0``.
    """
    if df is None or df <= 0:
        return None
    t = float(t)
    x = df / (df + t * t)
    tail = 0.5 * _incomplete_beta(df / 2.0, 0.5, x)
    return tail if t >= 0 else 1.0 - tail


def t_p_value(t: float, df: float) -> float | None:
    """Two-sided p-value for a t statistic: ``2 * P(T > |t|)``."""
    sf = student_t_sf(abs(float(t)), df)
    return None if sf is None else min(1.0, 2.0 * sf)


# --------------------------------------------------------------- multiplicity
def _clean_p_values(p_values: Sequence[float]) -> tuple[list[float], list[int]]:
    cleaned: list[float] = []
    positions: list[int] = []
    for index, raw in enumerate(p_values):
        value = _num(raw)
        if value is None:
            continue
        cleaned.append(min(1.0, max(0.0, value)))
        positions.append(index)
    return cleaned, positions


def _assemble(
    method: str,
    p_values: Sequence[float],
    cleaned: Sequence[float],
    positions: Sequence[int],
    adjusted: Sequence[float],
    alpha: float,
    labels: Sequence[str] | None,
) -> dict[str, Any]:
    tests: list[dict[str, Any]] = []
    for raw_index, p, adj in zip(positions, cleaned, adjusted):
        label = (
            str(labels[raw_index])
            if labels is not None and 0 <= raw_index < len(labels)
            else f"test_{raw_index}"
        )
        tests.append(
            {
                "label": label,
                "index": raw_index,
                "p": p,
                "adjusted_p": min(1.0, adj),
                "reject": bool(adj <= alpha),
            }
        )
    ordered = sorted(tests, key=lambda item: (item["adjusted_p"], item["label"]))
    rejected = sum(1 for item in tests if item["reject"])
    # `adjusted` is the report-facing table (docs/SCHEMA.md §research): a list of
    # dicts so a renderer can label columns. `adjusted_p_values` keeps the raw
    # numeric order (same order as the input p-values) for programmatic joins.
    adjusted_rows = [
        {
            "key": item["label"],
            "raw_p": item["p"],
            "adjusted_p": item["adjusted_p"],
            "significant": item["reject"],
        }
        for item in ordered
    ]
    return {
        "method": method,
        "alpha": alpha,
        "m": len(tests),
        "tests": tests,
        "ordered": ordered,
        "rejected": rejected,
        "n_rejected": rejected,
        "n_significant": rejected,
        "significant": rejected,
        "rejected_labels": [item["label"] for item in ordered if item["reject"]],
        "adjusted": adjusted_rows,
        "adjusted_p_values": [item["adjusted_p"] for item in tests],
        "note_zh": (
            "family-wise error rate 控制在 alpha 之下；adjusted_p 是可直接与 alpha 比较的"
            "校正后 p 值。adjusted_p_values 与输入 p 值一一对应。"
        ),
    }


def bonferroni(p_values: Sequence[float], alpha: float = DEFAULT_ALPHA,
               labels: Sequence[str] | None = None) -> dict[str, Any]:
    """Bonferroni correction: ``p_adj_i = min(1, m * p_i)``.

    Controls the family-wise error rate at ``alpha`` under any dependence
    structure (union bound), at the cost of low power: with ``m = 20`` and
    ``alpha = 0.05`` a raw p must be below 0.0025. Reported for transparency and
    as the conservative bound that Holm can only improve on.
    """
    cleaned, positions = _clean_p_values(p_values)
    m = len(cleaned)
    adjusted = [m * p for p in cleaned]
    return _assemble("bonferroni", p_values, cleaned, positions, adjusted, alpha, labels)


def holm(p_values: Sequence[float], alpha: float = DEFAULT_ALPHA,
         labels: Sequence[str] | None = None) -> dict[str, Any]:
    """Holm step-down (Holm-Bonferroni) adjustment.

    Sort p-values ascending ``p_(1) <= ... <= p_(m)``; then::

        p_adj_(k) = max_{j <= k} min(1, (m - j + 1) * p_(j))

    The running maximum enforces the monotonicity ``p_adj_(1) <= ... <= p_adj_(m)``
    that makes the **step-down** procedure valid: you may reject the first ``k``
    hypotheses exactly when ``p_adj_(k) <= alpha`` (equivalently, reject while
    ``p_(j) <= alpha / (m - j + 1)``). Holm is uniformly at least as powerful as
    Bonferroni and controls the same family-wise error rate without assuming
    independence.
    """
    cleaned, positions = _clean_p_values(p_values)
    m = len(cleaned)
    if m == 0:
        return _assemble("holm", p_values, cleaned, positions, [], alpha, labels)
    order = sorted(range(m), key=lambda i: (cleaned[i], positions[i]))
    adjusted_sorted: list[float] = []
    running = 0.0
    for step, idx in enumerate(order, start=1):
        candidate = (m - step + 1) * cleaned[idx]
        running = max(running, min(1.0, candidate))
        adjusted_sorted.append(running)
    adjusted = [0.0] * m
    for idx, value in zip(order, adjusted_sorted):
        adjusted[idx] = value
    return _assemble("holm", p_values, cleaned, positions, adjusted, alpha, labels)


def multiple_testing(p_values: Sequence[float], method: str = "holm",
                     alpha: float = DEFAULT_ALPHA,
                     labels: Sequence[str] | None = None) -> dict[str, Any]:
    """Dispatch to :func:`holm` (default) or :func:`bonferroni`.

    Unknown methods raise ``ValueError`` instead of silently doing nothing - a
    silent fallback here would turn an unadjusted table into a "corrected" one.
    """
    name = str(method or "holm").strip().lower()
    if name in ("holm", "holm-bonferroni", "holm_bonferroni"):
        return holm(p_values, alpha=alpha, labels=labels)
    if name in ("bonferroni", "bonf"):
        return bonferroni(p_values, alpha=alpha, labels=labels)
    raise ValueError(f"unknown multiple_testing method: {method!r}")


# --------------------------------------------------------------------- resample
def _percentile(sorted_values: Sequence[float], q: float) -> float | None:
    n = len(sorted_values)
    if not n:
        return None
    if n == 1:
        return sorted_values[0]
    position = q * (n - 1)
    low = int(math.floor(position))
    high = min(n - 1, low + 1)
    weight = position - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def block_bootstrap_ci(
    values: Sequence[float],
    blocks: Sequence[Any] | None = None,
    *,
    weights: Sequence[float] | None = None,
    stat_fn: Callable[[Sequence[float]], float] | None = None,
    stat_name: str = "mean",
    n_boot: int = DEFAULT_N_BOOT,
    alpha: float = DEFAULT_ALPHA,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Percentile confidence interval from a **cluster (block) bootstrap**.

    Model. Observations are grouped into ``G`` blocks (in this repo: event days).
    Returns inside a block share overlapping holding windows, so they are
    correlated; draws from different blocks are treated as independent.

    Algorithm (Cameron-Gelbach-Miller cluster bootstrap):

    1. put each observation into its block ``g(i)``;
    2. draw ``G`` blocks with replacement, uniform on ``{1..G}``;
    3. concatenate every observation of the drawn blocks;
    4. compute the statistic; repeat ``n_boot`` times;
    5. interval = percentiles ``[alpha/2, 1-alpha/2]`` of the draws.

    Validity is asymptotic in the number of **blocks**, not observations: with
    ``G < 2`` no interval is returned (``lo``/``hi`` are ``None``) rather than a
    fake one. ``blocks=None`` degenerates to the classic i.i.d. percentile
    bootstrap (each observation is its own block).

    The function is deterministic: same inputs + seed -> byte-identical output.
    """
    raw = list(values)
    if blocks is not None and len(blocks) != len(raw):
        raise ValueError("blocks must align with values (one block id per observation)")
    if weights is not None and len(weights) != len(raw):
        raise ValueError("weights must align with values (one weight per observation)")
    pairs: list[tuple[float, float]] = []
    group_of: list[str] = []
    for index, raw_value in enumerate(raw):
        value = _num(raw_value)
        if value is None:
            continue
        weight = 1.0 if weights is None else (_num(weights[index]) or 0.0)
        pairs.append((value, weight))
        group_of.append(str(blocks[index]) if blocks is not None else str(index))
    n = len(pairs)
    weighted = weights is not None

    def fn(sample: Sequence[tuple[float, float]]) -> float:
        if stat_fn is not None:
            return float(stat_fn([value for value, _ in sample]))
        if weighted:
            total = sum(weight for _, weight in sample)
            if total > 0:
                return sum(value * weight for value, weight in sample) / total
            return sum(value for value, _ in sample) / len(sample) if sample else 0.0
        return sum(value for value, _ in sample) / len(sample) if sample else 0.0

    groups: dict[str, list[tuple[float, float]]] = {}
    for pair, group in zip(pairs, group_of):
        groups.setdefault(group, []).append(pair)
    n_blocks = len(groups)
    point = fn(pairs) if pairs else None
    payload: dict[str, Any] = {
        "method": "block_bootstrap" if blocks is not None else "iid_bootstrap",
        "stat": stat_name,
        "point": point,
        "lo": None,
        "hi": None,
        "n": n,
        "n_blocks": n_blocks,
        "n_boot": int(n_boot),
        "alpha": float(alpha),
        "seed": int(seed),
        "interval": "percentile",
        "weighted": weighted,
    }
    if n < 2 or n_blocks < 2 or not pairs:
        payload["note_zh"] = "观测或分块不足（<2 块），不报告区间，避免给出虚假精度。"
        return payload
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must be in (0, 1)")
    ordered_blocks = sorted(groups, key=str)
    rng = random.Random(seed)
    draws: list[float] = []
    m = len(ordered_blocks)
    for _ in range(int(n_boot)):
        sample: list[tuple[float, float]] = []
        for _ in range(m):
            sample.extend(groups[ordered_blocks[rng.randrange(m)]])
        draws.append(fn(sample))
    draws.sort()
    payload["lo"] = _percentile(draws, alpha / 2.0)
    payload["hi"] = _percentile(draws, 1.0 - alpha / 2.0)
    payload["n_draws"] = len(draws)
    return payload


# ------------------------------------------------------------ event study table
def _returns_of(event: Mapping[str, Any], returns_key: str) -> Mapping[str, Any] | None:
    """Find the per-horizon return mapping on an event row (forgiving lookup).

    Accepts ``returns_key`` first, then the canonical keys used elsewhere in the
    repo (``ar`` from an event-study row, ``abnormal`` from
    ``eventstudy.run_event_study``), so callers do not need a translation layer.
    """
    for key in (returns_key, "ar", "abnormal", "returns"):
        value = event.get(key)
        if isinstance(value, Mapping):
            return value
    return None


def _horizon_value(returns: Mapping[str, Any], horizon: int) -> float | None:
    for key in (horizon, str(horizon)):
        if key in returns:
            return _num(returns.get(key))
    return None


def _stats_block(
    values: Sequence[float],
    blocks: Sequence[Any],
    weights: Sequence[float],
    *,
    n_boot: int,
    alpha: float,
    seed: int,
    min_events: int,
) -> dict[str, Any]:
    n = len(values)
    weighted = any(abs(w - 1.0) > 1e-12 for w in weights)
    sd = stdev(values)
    t_value = None if weighted else t_stat(values)
    p_value = t_p_value(t_value, n - 1) if t_value is not None and n >= 3 else None
    ci = block_bootstrap_ci(
        values,
        blocks,
        weights=list(weights) if weighted else None,
        stat_name="weighted_mean" if weighted else "mean",
        n_boot=n_boot,
        alpha=alpha,
        seed=seed,
    )
    avg = ci["point"]
    hit_values = [1.0 if value > 0 else 0.0 for value in values]
    hit = sum(hit_values) / n if n else None
    hit_ci = block_bootstrap_ci(
        hit_values, blocks, stat_name="hit_rate", n_boot=n_boot, alpha=alpha, seed=seed
    )
    return {
        "n": n,
        "n_blocks": len(set(str(b) for b in blocks)),
        "mean": avg,
        "median": median(values),
        "std": sd,
        "t": t_value,
        "df": (n - 1) if n >= 2 else None,
        "p_value": p_value,
        "ci95": {"lo": ci["lo"], "hi": ci["hi"], "level": 1.0 - alpha,
                 "method": ci["method"], "n_blocks": ci["n_blocks"]},
        "hit_rate": hit,
        "hit_rate_ci": {"lo": hit_ci["lo"], "hi": hit_ci["hi"], "level": 1.0 - alpha,
                        "method": hit_ci["method"]},
        "weighted": weighted,
        "mde": mde(n, sd=sd if sd else 1.0, alpha=alpha),
        "sufficient": n >= min_events,
        "effect_units": "fraction (0.01 = +1%)",
    }


def aggregate_event_study(
    events: Sequence[Mapping[str, Any]],
    horizons: Sequence[int] = (1, 5, 20, 60),
    *,
    returns_key: str = "ar",
    block_key: str = "event_date",
    kind_key: str = "kind",
    weight_key: str = "weight",
    n_boot: int = DEFAULT_N_BOOT,
    alpha: float = DEFAULT_ALPHA,
    seed: int = DEFAULT_SEED,
    min_events: int = 3,
    method: str = "holm",
) -> dict[str, Any]:
    """Aggregate abnormal returns into mean/median/t/CI/hit-rate per kind.

    Parameters
    ----------
    events:
        Rows with at least ``event_date``, ``kind`` and a per-horizon mapping
        under ``ar`` (or ``abnormal``), e.g.::

            {"event_date": "2025-03-03", "kind": "drug_approval", "ticker": "X",
             "ar": {"1": 0.012, "5": 0.004, "20": None, "60": -0.01}}

        ``None`` values are treated as missing, never as zero. Each row may carry
        an optional numeric ``weight`` (see :func:`market_cap_weights`); when any
        weight differs from 1 the mean becomes weighted and the exact t-test is
        replaced by the bootstrap interval (``t = None``), because a weighted mean
        of non-i.i.d. observations has no clean closed-form t.
    horizons:
        Trading-day horizons to aggregate; rows missing a horizon are dropped for
        that horizon only.
    block_key:
        Correlation block (default ``event_date``): all events on the same day
        are resampled together, which is what makes the interval honest when
        holding windows overlap.
    method:
        Multiplicity correction across the reported tests (kind x horizon).

    Returns
    -------
    ``{"status": "ok", "all": {"1": {...}, ...}, "by_kind": {...},
    "multiple_testing": {...}, "power": {...}, "meta": {...}}``; or
    ``{"status": "insufficient_data", "reason": ...}`` when fewer than
    ``min_events`` usable rows exist. Every horizon block documents ``n``,
    ``n_blocks``, ``ci95`` (block bootstrap), ``hit_rate`` (+ bootstrap CI),
    ``t``/``p_value`` (equal weights only) and ``mde``.
    """
    horizon_list = sorted({int(h) for h in horizons if int(h) > 0})
    if not horizon_list:
        return {"status": "insufficient_data", "reason": "no_horizons"}

    rows: list[dict[str, Any]] = []
    for event in events or []:
        returns = _returns_of(event, returns_key)
        if returns is None:
            continue
        block = str(event.get(block_key) or "")
        if not block:
            continue
        kind = str(event.get(kind_key) or "unknown")
        weight = _num(event.get(weight_key))
        rows.append(
            {
                "block": block,
                "kind": kind,
                "returns": returns,
                "weight": 1.0 if weight is None else weight,
            }
        )
    if not rows:
        return {"status": "insufficient_data", "reason": "no_events_with_returns"}

    kinds_present = sorted({row["kind"] for row in rows})
    all_stats: dict[str, Any] = {}
    by_kind: dict[str, dict[str, Any]] = {}
    p_values: list[float] = []
    test_labels: list[str] = []
    for horizon in horizon_list:
        values, blocks, weights = [], [], []
        for row in rows:
            value = _horizon_value(row["returns"], horizon)
            if value is None:
                continue
            values.append(value)
            blocks.append(row["block"])
            weights.append(row["weight"])
        if len(values) < 2:
            all_stats[str(horizon)] = {
                "n": len(values), "n_blocks": 0, "mean": None, "median": None,
                "std": None, "t": None, "p_value": None, "ci95": None,
                "hit_rate": None, "hit_rate_ci": None, "weighted": False,
                "mde": None, "sufficient": False,
            }
            continue
        block_stats = _stats_block(
            values, blocks, weights, n_boot=n_boot, alpha=alpha, seed=seed,
            min_events=min_events,
        )
        all_stats[str(horizon)] = block_stats
        if block_stats["sufficient"] and block_stats["p_value"] is not None:
            p_values.append(block_stats["p_value"])
            test_labels.append(f"all@{horizon}")
        for kind in kinds_present:
            kind_values, kind_blocks, kind_weights = [], [], []
            for row in rows:
                if row["kind"] != kind:
                    continue
                value = _horizon_value(row["returns"], horizon)
                if value is None:
                    continue
                kind_values.append(value)
                kind_blocks.append(row["block"])
                kind_weights.append(row["weight"])
            kind_stats = _stats_block(
                kind_values, kind_blocks, kind_weights, n_boot=n_boot, alpha=alpha,
                seed=seed, min_events=min_events,
            )
            by_kind.setdefault(kind, {})[str(horizon)] = kind_stats
            if kind_stats["sufficient"] and kind_stats["p_value"] is not None:
                p_values.append(kind_stats["p_value"])
                test_labels.append(f"{kind}@{horizon}")

    if len(rows) < max(1, int(min_events)):
        return {
            "status": "insufficient_data",
            "reason": "too_few_events",
            "counts": {"events": len(rows), "min_events": int(min_events)},
        }
    if not any(block.get("n", 0) >= 2 for block in all_stats.values()):
        return {
            "status": "insufficient_data",
            "reason": "no_horizon_data",
            "counts": {"events": len(rows)},
        }

    tests = multiple_testing(p_values, method=method, alpha=alpha, labels=test_labels)
    reference = next(
        (all_stats[str(h)] for h in horizon_list if all_stats.get(str(h), {}).get("n", 0) >= 2),
        None,
    )
    power = power_hint(
        reference["n"] if reference else len(rows),
        sd=reference["std"] if reference and reference.get("std") else 0.05,
        alpha=alpha,
        observed_effect=reference["mean"] if reference else None,
    )
    return {
        "status": "ok",
        "n_events": len(rows),
        "n_blocks": len({row["block"] for row in rows}),
        "horizons": horizon_list,
        "kinds": kinds_present,
        "all": all_stats,
        "by_kind": by_kind,
        "multiple_testing": tests,
        "power": power,
        "weighting": "weighted" if any(abs(r["weight"] - 1.0) > 1e-12 for r in rows) else "equal",
        "meta": {
            "entry": "return measured from the first trading day strictly after the signal date",
            "bootstrap": {
                "method": "block (cluster) bootstrap",
                "block": block_key,
                "n_boot": int(n_boot),
                "alpha": alpha,
                "seed": seed,
                "why": "重叠持有期使同日事件相关；按事件日整体重采样才不低估方差",
            },
            "multiple_testing_method": tests["method"],
            "note_zh": "缺失 horizon 记为 missing，不按 0 处理；无效或过期数据不进入均值。",
        },
    }


# ---------------------------------------------------------------------- design
def time_split(
    items: Sequence[Mapping[str, Any]],
    *,
    key: str = "event_date",
    fractions: Sequence[float] = (0.6, 0.2, 0.2),
    labels: Sequence[str] = ("dev", "validation", "holdout"),
    dev_end: str | None = None,
    validation_end: str | None = None,
    return_items: bool = False,
) -> dict[str, Any]:
    """Chronological dev / validation / holdout split that never breaks a day.

    Two rules make this usable as a protocol rather than a convenience:

    1. **Ordering is by event day** (``key``, ISO strings), never by event id -
       any other order leaks the future into dev.
    2. **A day belongs to exactly one phase.** Cut points are snapped forward to
       the next day boundary, so no event date can appear in two phases. This is
       the same block used by :func:`block_bootstrap_ci`; splitting a block would
       leak through the correlation we are trying to model.

    Defaults are 60/20/20. With ``n=25`` that is 15/5/5 - small, which is why the
    report must call holdout results "exploratory at this n" (see
    :func:`power_hint`). Explicit ``dev_end`` / ``validation_end`` dates override
    the fractions (ISO ``YYYY-MM-DD``, inclusive).

    Returns ``{"status","n","labels","fractions","bounds","sample_fractions",
    "no_overlap"}`` with ``bounds[label] = {"start","end","n","n_days"}``. The
    per-phase lists are **not** copied into the payload by default (a metrics
    JSON that duplicates every event is a memory bill, not information); pass
    ``return_items=True`` to get them under ``"items"``.
    """
    label_list = [str(label) for label in labels]
    if len(label_list) != 3:
        raise ValueError("time_split expects exactly three phase labels")
    ordered = sorted(items or [], key=lambda item: str(item.get(key) or ""))
    n = len(ordered)
    phases: dict[str, list[Mapping[str, Any]]] = {label: [] for label in label_list}
    payload: dict[str, Any] = {
        "status": "ok",
        "n": n,
        "labels": label_list,
        "key": key,
        "fractions": [float(f) for f in fractions],
        "bounds": {},
        "no_overlap": True,
    }

    def finish() -> dict[str, Any]:
        for label in label_list:
            payload["bounds"][label] = _bounds(phases[label], key)
        seen: dict[str, str] = {}
        for label in label_list:
            for item in phases[label]:
                day = str(item.get(key) or "")
                if day in seen and seen[day] != label:
                    payload["no_overlap"] = False
                seen[day] = label
        payload["sample_fractions"] = {
            label: (len(phases[label]) / n if n else 0.0) for label in label_list
        }
        if return_items:
            payload["items"] = {label: list(phases[label]) for label in label_list}
        return payload

    if n == 0:
        payload["status"] = "empty"
        return finish()
    if n < 3:
        payload["status"] = "too_small"
        phases[label_list[0]] = list(ordered)
        return finish()

    def day_of(item: Mapping[str, Any]) -> str:
        return str(item.get(key) or "")

    if dev_end or validation_end:
        if not dev_end or not validation_end:
            raise ValueError("both dev_end and validation_end are required when cutting by date")
        if str(validation_end) < str(dev_end):
            raise ValueError("validation_end must not precede dev_end")
        for item in ordered:
            day = day_of(item)
            if day <= str(dev_end):
                phases[label_list[0]].append(item)
            elif day <= str(validation_end):
                phases[label_list[1]].append(item)
            else:
                phases[label_list[2]].append(item)
        return finish()

    total = sum(float(f) for f in fractions)
    if total <= 0:
        raise ValueError("fractions must sum to a positive number")
    normalised = [float(f) / total for f in fractions]
    first = int(round(n * normalised[0]))
    second = int(round(n * (normalised[0] + normalised[1])))
    first = min(max(first, 1), n - 2)
    second = min(max(second, first + 1), n - 1)
    # snap forward so a group of identical event days is never split
    first = _snap_forward(ordered, first, key)
    second = _snap_forward(ordered, max(second, first), key)
    if second <= first:
        second = min(n - 1, first + 1)
    if first >= n - 1 or second <= first:
        payload["status"] = "degenerate"
        payload["note_zh"] = (
            "事件日过度集中（同一天占满可用样本），无法在不拆散相关块的前提下切成三段；"
            "请改用显式日期切分或扩大样本窗口。"
        )
        phases[label_list[0]] = list(ordered)
        return finish()
    phases[label_list[0]] = list(ordered[:first])
    phases[label_list[1]] = list(ordered[first:second])
    phases[label_list[2]] = list(ordered[second:])
    return finish()


def _snap_forward(ordered: Sequence[Mapping[str, Any]], cut: int, key: str) -> int:
    """Move ``cut`` forward until it does not split a group with the same day."""
    n = len(ordered)
    cut = min(max(cut, 1), n - 1)
    while cut < n and str(ordered[cut].get(key) or "") == str(ordered[cut - 1].get(key) or ""):
        cut += 1
    return min(cut, n - 1) if cut < n else n


def _bounds(items: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    if not items:
        return {"start": None, "end": None, "n": 0, "n_days": 0}
    days = sorted(str(item.get(key) or "") for item in items)
    return {
        "start": days[0],
        "end": days[-1],
        "n": len(items),
        "n_days": len(set(days)),
    }


def time_split_by_dates(
    items: Sequence[Mapping[str, Any]],
    dev_end: str,
    validation_end: str,
    *,
    key: str = "event_date",
    return_items: bool = False,
) -> dict[str, Any]:
    """Thin wrapper over :func:`time_split` with explicit ISO cut dates."""
    return time_split(
        items,
        key=key,
        dev_end=dev_end,
        validation_end=validation_end,
        return_items=return_items,
    )


# --------------------------------------------------------------------- weights
def normalize_weights(weights: Mapping[Any, float]) -> dict[Any, float]:
    """Scale non-negative weights to sum to 1 (all-zero input stays all-zero)."""
    cleaned = {key: max(0.0, _num(value) or 0.0) for key, value in weights.items()}
    total = sum(cleaned.values())
    if total <= 0:
        return {key: 0.0 for key in cleaned}
    return {key: value / total for key, value in cleaned.items()}


def equal_weights(keys: Iterable[Any]) -> dict[Any, float]:
    """Equal weighting: every member gets ``1/n``.

    The default for event studies: it is the only weighting that needs no extra
    data and cannot encode a market-cap look-ahead (using *today's* market cap to
    weight a 2019 event is a subtle survivorship/look-ahead error).
    """
    key_list = list(keys)
    if not key_list:
        return {}
    weight = 1.0 / len(key_list)
    return {key: weight for key in key_list}


def weighted_mean(values: Sequence[float], weights: Mapping[Any, float]) -> float | None:
    """Weighted mean ``sum(w_i x_i) / sum(w_i)`` (pairs aligned by integer index)."""
    clean = [v for v in (_num(x) for x in values) if v is not None]
    if not clean:
        return None
    pairs = [(value, _num(weights.get(index)) or 0.0) for index, value in enumerate(values)]
    pairs = [(value, weight) for value, weight in pairs if _num(value) is not None]
    total = sum(weight for _, weight in pairs)
    if total <= 0:
        return None
    return sum(value * weight for value, weight in pairs) / total


def market_cap_weights(
    market_caps: Mapping[Any, float],
    *,
    cap: float | None = None,
    max_iterations: int = 100,
) -> dict[Any, float]:
    """Market-cap weights with an optional single-name cap.

    ``w_i ∝ cap_i`` (cap-weighted index convention). When ``cap`` is given
    (e.g. ``0.05`` for the paper book's 5% single-name limit) the standard
    iterative capping is applied: clamp names above the limit, redistribute the
    excess pro-rata to the uncapped names, repeat until no name exceeds the cap.
    If the cap is infeasible (``cap < 1/n``) the result is uniform ``1/n`` and
    ``feasible`` cannot be met - callers get a warning key instead of an error.

    Missing / non-positive market caps are treated as unknown and get weight 0
    (they are *not* silently made equal-weight), so callers must check
    ``coverage``-style sums themselves.
    """
    base = {key: max(0.0, _num(value) or 0.0) for key, value in market_caps.items()}
    total = sum(base.values())
    if total <= 0:
        return {key: 0.0 for key in base}
    weights = normalize_weights(base)
    if cap is None:
        return weights
    cap = float(cap)
    n = len(weights)
    if n and cap * n < 1.0 - 1e-12:
        uniform = 1.0 / n
        return {key: uniform for key in weights}
    capped: set[Any] = set()
    for _ in range(max_iterations):
        over = [key for key, weight in weights.items() if weight > cap + 1e-12]
        if not over:
            break
        for key in over:
            capped.add(key)
            weights[key] = cap
        residual = 1.0 - cap * len(capped)
        free = {key: base[key] for key in weights if key not in capped}
        free_total = sum(free.values())
        if free_total <= 0:
            break
        for key, weight in free.items():
            weights[key] = max(0.0, residual) * weight / free_total
    # normalise away floating point drift; keep the cap as the binding constraint
    total_after = sum(weights.values())
    if total_after > 0:
        weights = {key: weight / total_after for key, weight in weights.items()}
    return weights


# ---------------------------------------------------------------- survivorship
def survivorship_flags(
    entities: Sequence[Mapping[str, Any]],
    *,
    price_tickers: Iterable[str] | None = None,
    delisted: Iterable[str] | None = None,
    listed_until: Mapping[str, str] | None = None,
    window_end: str | None = None,
    key: str = "key",
    ticker: str = "ticker",
) -> dict[str, Any]:
    """Flag entities whose absence from the sample would flatter a long-only book.

    Three mechanical reasons (no judgement calls):

    * ``no_ticker`` - the entity has no tradable ticker, so it can never appear
      in a return study;
    * ``no_prices`` - a ticker was expected but the price layer has no data
      (Yahoo drops many delisted/AIM/OTC names);
    * ``delisted_before_window_end`` - explicitly listed as delisted, or a
      ``listed_until`` date earlier than ``window_end``.

    Returns ``{"total","flagged","flagged_count","clean_count","flagged_entities",
    "reasons":{reason:count},"coverage","note_zh"}`` where ``flagged`` is the
    **count** (what the report prints) and ``flagged_entities`` the audit rows.
    The report shows ``flagged`` next to the trading numbers instead of hiding
    the hole.
    """
    prices = {str(t).strip().upper() for t in (price_tickers or []) if str(t).strip()}
    gone = {str(t).strip().upper() for t in (delisted or []) if str(t).strip()}
    until = {str(k): str(v) for k, v in (listed_until or {}).items()}
    flagged: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}
    for entity in entities or []:
        entity_key = str(entity.get(key) or entity.get("key") or "")
        entity_ticker = str(entity.get(ticker) or entity.get("ticker") or "").strip().upper()
        found: list[str] = []
        if not entity_ticker:
            found.append("no_ticker")
        else:
            if entity_ticker in gone:
                found.append("delisted_before_window_end")
            if window_end and entity_ticker in until and until[entity_ticker] < str(window_end):
                found.append("delisted_before_window_end")
            if price_tickers is not None and entity_ticker not in prices:
                found.append("no_prices")
        for reason in found:
            reasons[reason] = reasons.get(reason, 0) + 1
        if found:
            flagged.append(
                {"key": entity_key, "ticker": entity_ticker,
                 "reasons": sorted(set(found))}
            )
    total = len(entities or [])
    clean = total - len(flagged)
    return {
        "total": total,
        "flagged": len(flagged),
        "flagged_count": len(flagged),
        "clean_count": clean,
        "flagged_entities": flagged,
        "reasons": reasons,
        "coverage": (clean / total) if total else None,
        "method": "missing-ticker / missing-price / delisted-before-window-end",
        "note_zh": (
            "被标记的标的不是坏数据，而是'因为我们拿不到它的价格，所以它不在结果里'；"
            "报告必须显示这个数字，否则做多组合会被生存偏差美化。"
        ),
    }


# ------------------------------------------------------------------------ power
def mde(
    n: int,
    sd: float = 1.0,
    alpha: float = DEFAULT_ALPHA,
    power: float = 0.8,
) -> float | None:
    """Minimum detectable effect (normal approximation, one-sample, two-sided).

    ::

        MDE = (z_{1-alpha/2} + z_{power}) * sd / sqrt(n)

    The usual approximation ignores the t degrees of freedom; at ``n >= 20`` the
    difference is small, and the number exists to warn ("n=5 cannot detect a 2%
    move"), not to certify power. Returns ``None`` for ``n < 2``.
    """
    if not n or int(n) < 2 or sd is None or sd <= 0:
        return None
    z_alpha = normal_ppf(1.0 - alpha / 2.0)
    z_power = normal_ppf(power)
    if z_alpha is None or z_power is None:
        return None
    return (z_alpha + z_power) * float(sd) / math.sqrt(int(n))


def required_n(
    effect: float,
    sd: float = 1.0,
    alpha: float = DEFAULT_ALPHA,
    power: float = 0.8,
) -> int | None:
    """Smallest ``n`` whose MDE is at most ``|effect|``.

    ::

        n = ceil( ((z_{1-alpha/2} + z_{power}) * sd / |effect|)^2 )

    ``None`` for a zero effect (no finite sample detects it).
    """
    effect = abs(float(effect or 0.0))
    if effect <= 0 or sd is None or sd <= 0:
        return None
    z_alpha = normal_ppf(1.0 - alpha / 2.0)
    z_power = normal_ppf(power)
    if z_alpha is None or z_power is None:
        return None
    return max(2, int(math.ceil(((z_alpha + z_power) * float(sd) / effect) ** 2)))


def power_hint(
    n: int,
    sd: float = 1.0,
    alpha: float = DEFAULT_ALPHA,
    power: float = 0.8,
    observed_effect: float | None = None,
) -> dict[str, Any]:
    """Sample-size / power sanity check meant for the report footer.

    Reports the MDE at the current ``n``; when ``observed_effect`` is supplied it
    also says how many observations that effect *would* need, and whether the
    current sample is below half of that (``underpowered``). Wording is Chinese
    because it is rendered directly into ``report_zh.md``.
    """
    n = int(n or 0)
    sd_value = float(sd) if sd is not None and sd > 0 else 1.0
    detectable = mde(n, sd=sd_value, alpha=alpha, power=power)
    needed = (
        required_n(observed_effect, sd=sd_value, alpha=alpha, power=power)
        if observed_effect
        else None
    )
    underpowered = bool(needed is not None and n < needed)
    if n < 2 or detectable is None:
        verdict = "样本量不足以计算区间；只能作为案例描述，不能作为证据。"
    elif underpowered:
        verdict = (
            f"n={n} 时最小可检测效应约 {detectable:.4f}（sd={sd_value:.4f}，power={power:.0%}）；"
            f"要检出观测到的 {abs(observed_effect):.4f} 大约需要 n={needed}。当前样本功效不足，"
            "结论只能作为假设，不能对外宣称有效。"
        )
    else:
        verdict = (
            f"n={n} 时最小可检测效应约 {detectable:.4f}（sd={sd_value:.4f}，power={power:.0%}），"
            "观测效应高于该门槛，但仍需多重检验校正后再判断显著性。"
        )
    return {
        "n": n,
        "sd": sd_value,
        "alpha": alpha,
        "target_power": power,
        "mde": detectable,
        "observed_effect": observed_effect,
        "required_n_for_observed": needed,
        "underpowered": underpowered,
        "verdict_zh": verdict,
    }


# ------------------------------------------------------------------ aggregator
def research_block(
    events: Sequence[Mapping[str, Any]],
    *,
    horizons: Sequence[int] = (1, 5, 20, 60),
    returns_key: str = "abnormal",
    block_key: str = "event_date",
    kind_key: str = "kind",
    fractions: Sequence[float] = (0.6, 0.2, 0.2),
    n_boot: int = DEFAULT_N_BOOT,
    alpha: float = DEFAULT_ALPHA,
    seed: int = DEFAULT_SEED,
    method: str = "holm",
    price_tickers: Iterable[str] | None = None,
    delisted: Iterable[str] | None = None,
    listed_until: Mapping[str, str] | None = None,
    universe: Sequence[Mapping[str, Any]] | None = None,
    window_end: str | None = None,
) -> dict[str, Any]:
    """Assemble the ``metrics["research"]`` block used by the report (SCHEMA §research).

    One call, three questions the report must answer:

    * ``sample_split`` - which event days are dev / validation / holdout, so a
      reader can tell whether a number was tuned in-sample;
    * ``multiple_testing`` - Holm-adjusted p-values for every kind x horizon test;
    * ``survivorship`` - how many entities are missing from the return sample.

    Returned shape::

        {"sample_split": {label: {"start","end","n"}},
         "multiple_testing": {"method","alpha","m","rejected","tests":[...]},
         "survivorship": {"flagged","total","coverage","reasons"},
         "event_study": {...},   # aggregate_event_study output
         "power": {...},
         "meta": {...}}

    ``events`` are event-study rows (see :func:`aggregate_event_study`). The
    ``universe`` argument is the list of entities whose prices the study *needed*
    (defaults to the distinct tickers in ``events``), so survivorship is measured
    against intent, not against what happened to be priced.
    """
    study = aggregate_event_study(
        events,
        horizons=horizons,
        returns_key=returns_key,
        block_key=block_key,
        kind_key=kind_key,
        n_boot=n_boot,
        alpha=alpha,
        seed=seed,
        method=method,
    )
    split = time_split(events, key=block_key, fractions=fractions)
    if universe is None:
        tickers = sorted(
            {str(event.get("ticker") or "").strip().upper() for event in events or []}
            - {""}
        )
        universe = [{"key": ticker, "ticker": ticker} for ticker in tickers]
    survivorship = survivorship_flags(
        universe,
        price_tickers=price_tickers,
        delisted=delisted,
        listed_until=listed_until,
        window_end=window_end,
    )
    return {
        "sample_split": {
            str(label): {
                "start": split["bounds"][label]["start"],
                "end": split["bounds"][label]["end"],
                "n": split["bounds"][label]["n"],
                "n_days": split["bounds"][label]["n_days"],
            }
            for label in split["labels"]
        },
        "sample_split_rule": {
            "order": f"{block_key} ascending",
            "fractions": [float(f) for f in fractions],
            "no_day_shared_between_phases": split["no_overlap"],
        },
        "multiple_testing": study.get("multiple_testing")
        or {"method": method, "alpha": alpha, "m": 0, "tests": [], "rejected": 0},
        "survivorship": survivorship,
        "event_study": study,
        "power": study.get("power")
        or power_hint(0),
        "meta": {
            "schema": "SCHEMA.md §research",
            "generated_by": "medradar.stats.research_block",
            "alpha": alpha,
            "seed": seed,
            "note_zh": (
                "研究元信息：样本划分、多重检验、生存偏差。任何对外数字都必须能回指到这里。"
            ),
        },
    }
