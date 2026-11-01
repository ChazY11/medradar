"""Point-in-time market features for the R&D continuation task.

Every value is computed from ``market_bars`` rows whose trading date is at or
before the example cutoff. A daily close is treated as known at the end of its
own trading day, so a bar dated exactly ``cutoff`` is included and every later
bar is invisible. This is the same dual-time discipline as the R&D and financial
feature groups; it does not know when a vendor published the bar, only the
trading date (see ``sources/market_data.py`` for the provenance caveat).

Feature group (``FEATURES``):

======================  =========================================================
``mkt_ret_12m``         Adjusted-close total return over the trailing 12 months.
``mkt_vol_12m``         Annualised stdev of daily log returns, trailing 12m.
``mkt_max_drawdown_12m`` Worst peak-to-trough drawdown in the trailing 12m
                        (negative number; 0.0 means no drawdown observed).
``mkt_rel_spy_12m``     ``mkt_ret_12m`` minus SPY's 12m return (excess return).
``mkt_rel_xbi_12m``     ``mkt_ret_12m`` minus XBI's 12m return (biotech excess).
``mkt_volume_z_3m``     z-score of the last 3 months' mean daily volume against
                        the earlier 9 months of the 12m window.
``mkt_regime_spy_above_200d``  1 when SPY's adjusted close is above its own
                        200-trading-day simple moving average at the cutoff, else 0.
``mkt_days_since_12m_high``   Trading bars since the highest adjusted close in
                        the trailing 12m window (0 = the high is the last bar).
``mkt_missing``         1 when any market feature could not be computed
                        (unknown ticker, too little bar history, missing
                        benchmark/volume coverage); 0 otherwise.
======================  =========================================================

``mkt_missing``/partial-null rows are left for the model's training-only median
imputation with a missing indicator — never filled in here. ``attach_market_features``
only adds these keys; it never overwrites the R&D or financial base features.

These are *market* signals, not measures of technological capability. A falling
stock price is not evidence that a company stopped doing R&D, and an excess
return is not evidence of research productivity.
"""
from __future__ import annotations

import math
import sqlite3
from bisect import bisect_right
from datetime import date, timedelta
from typing import Any, Iterable, Mapping

from ...util import iso, parse_date
from ..sources.market_data import company_ticker_map, normalise_ticker

#: Market features added to an example's ``features`` mapping.
FEATURES = (
    "mkt_ret_12m",
    "mkt_vol_12m",
    "mkt_max_drawdown_12m",
    "mkt_rel_spy_12m",
    "mkt_rel_xbi_12m",
    "mkt_volume_z_3m",
    "mkt_regime_spy_above_200d",
    "mkt_days_since_12m_high",
)
#: Flag set to 1 whenever at least one :data:`FEATURES` value is unavailable.
MISSING_KEY = "mkt_missing"

SPY = "SPY"
XBI = "XBI"
TRADING_DAYS = 252
RETURN_WINDOW_DAYS = 365
VOLUME_RECENT_DAYS = 91
MIN_WINDOW_BARS = 200
MIN_VOLUME_RECENT_BARS = 10
MIN_VOLUME_BASELINE_BARS = 30
REGIME_MA_BARS = 200
BENCHMARKS = (SPY, XBI)


# --------------------------------------------------------------------------- series
def load_series(store: Any, ticker: str, *, cache: dict[Any, Any] | None = None) -> dict[str, list[Any]] | None:
    """Load one ticker's adjusted-close series ordered by date (``None`` if empty).

    Rows without a finite positive ``adj_close`` are dropped, so a split- or
    dividend-unadjusted price never enters a return. ``cache`` (optional) is a
    per-run memo keyed by ``("series", ticker)``; it is never persisted.
    """
    symbol = normalise_ticker(ticker)
    if not symbol:
        return None
    key = ("series", symbol)
    if cache is not None and key in cache:
        return cache[key]
    try:
        rows = store.conn.execute(
            "SELECT date, adj_close, volume FROM market_bars"
            " WHERE ticker = ? AND adj_close IS NOT NULL ORDER BY date",
            (symbol,),
        ).fetchall()
    except sqlite3.OperationalError:
        # No market_bars table yet: treat as "no market data", not an error.
        rows = []
    dates: list[str] = []
    closes: list[float] = []
    volumes: list[float | None] = []
    for row in rows:
        day = iso(row[0])
        try:
            close = float(row[1])
        except (TypeError, ValueError):
            continue
        if not day or not math.isfinite(close) or close <= 0:
            continue
        try:
            volume = float(row[2]) if row[2] is not None else None
        except (TypeError, ValueError):
            volume = None
        if volume is not None and (not math.isfinite(volume) or volume < 0):
            volume = None
        dates.append(day)
        closes.append(close)
        volumes.append(volume)
    series = {"dates": dates, "closes": closes, "volumes": volumes} if dates else None
    if cache is not None:
        cache[key] = series
    return series


def _last_index(dates: list[str], cutoff_iso: str) -> int | None:
    index = bisect_right(dates, cutoff_iso) - 1
    return index if index >= 0 else None


def _window(series: dict[str, list[Any]] | None, cutoff_day: date) -> tuple[int, int] | None:
    """Return ``(base_index, last_index)`` for the trailing 12m, or ``None``.

    ``base_index`` is the last bar at or before ``cutoff - 365 days``; window bars
    are ``base_index + 1 .. last_index`` (i.e. dates strictly after the window
    start and at or before the cutoff). A 12m return therefore needs a bar
    that predates the window start; a recently listed company is reported as
    missing rather than given a shorter-horizon proxy.
    """
    if not series or not series["dates"]:
        return None
    dates = series["dates"]
    last = _last_index(dates, cutoff_day.isoformat())
    if last is None:
        return None
    start_iso = (cutoff_day - timedelta(days=RETURN_WINDOW_DAYS)).isoformat()
    base = _last_index(dates, start_iso)
    if base is None or last - base < MIN_WINDOW_BARS:
        return None
    return base, last


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _stdev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    average = _mean(values)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _window_return(series: dict[str, list[Any]] | None, cutoff_day: date) -> float | None:
    window = _window(series, cutoff_day)
    if window is None or series is None:
        return None
    base, last = window
    return series["closes"][last] / series["closes"][base] - 1.0


def _volume_z(series: dict[str, list[Any]], base: int, last: int,
              cutoff_day: date) -> float | None:
    recent_start = (cutoff_day - timedelta(days=VOLUME_RECENT_DAYS)).isoformat()
    dates, volumes = series["dates"], series["volumes"]
    recent = [volumes[index] for index in range(base, last + 1)
              if dates[index] > recent_start and volumes[index] is not None]
    baseline = [volumes[index] for index in range(base, last + 1)
                if dates[index] <= recent_start and volumes[index] is not None]
    if len(recent) < MIN_VOLUME_RECENT_BARS or len(baseline) < MIN_VOLUME_BASELINE_BARS:
        return None
    spread = _stdev(baseline)  # type: ignore[arg-type]
    if spread is None or spread <= 0:
        return None
    return (_mean(recent) - _mean(baseline)) / spread  # type: ignore[arg-type]


def _regime_spy_above_200d(spy: dict[str, list[Any]] | None, cutoff_day: date) -> int | None:
    if not spy or not spy["dates"]:
        return None
    index = _last_index(spy["dates"], cutoff_day.isoformat())
    if index is None or index < REGIME_MA_BARS - 1:
        return None
    closes = spy["closes"]
    average = _mean(closes[index - REGIME_MA_BARS + 1:index + 1])
    # A flat series is not "above" its own average; require a strict excess.
    return 1 if closes[index] > average else 0


# --------------------------------------------------------------------------- features
def _company_features(series: dict[str, list[Any]] | None,
                      cutoff_day: date) -> dict[str, float | int | None] | None:
    window = _window(series, cutoff_day)
    if window is None or series is None:
        return None
    base, last = window
    closes = series["closes"]
    values = closes[base:last + 1]
    window_closes = closes[base + 1:last + 1]
    returns = [math.log(values[index] / values[index - 1]) for index in range(1, len(values))]
    spread = _stdev(returns)
    peak = values[0]
    drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = min(drawdown, value / peak - 1.0)
    highest = max(range(len(window_closes)), key=lambda index: (window_closes[index], index))
    high_index = base + 1 + highest
    volume_z = _volume_z(series, base, last, cutoff_day)
    return {
        "mkt_ret_12m": values[-1] / values[0] - 1.0,
        "mkt_vol_12m": spread * math.sqrt(TRADING_DAYS) if spread is not None else None,
        "mkt_max_drawdown_12m": drawdown,
        "mkt_volume_z_3m": volume_z,
        "mkt_days_since_12m_high": float(last - high_index),
    }


def _resolve_ticker(company_key: Any, tickers: Any) -> str | None:
    """Resolve the ticker for one company; see :func:`market_features`."""
    key = str(company_key or "").strip()
    if tickers is None:
        return normalise_ticker(key) or None
    if isinstance(tickers, Mapping):
        symbol = normalise_ticker(tickers.get(key))
        return symbol or None
    if isinstance(tickers, str):
        return normalise_ticker(tickers) or None
    allowed = {normalise_ticker(value) for value in tickers if normalise_ticker(value)}
    symbol = normalise_ticker(key)
    return symbol if symbol in allowed else None


def market_features(store: Any, company_key: Any, cutoff: Any, tickers: Any,
                    *, cache: dict[Any, Any] | None = None) -> dict[str, float | int | None]:
    """Point-in-time market features for one company at one cutoff.

    Parameters
    ----------
    store:
        Open intelligence store (``market_bars`` may be absent — then every
        feature is ``None`` and ``mkt_missing`` is 1).
    company_key:
        Curated company key (for example ``"medtronic"``).
    cutoff:
        Any date shape accepted by :func:`medradar.util.parse_date`.
    tickers:
        ``{company_key: ticker}`` mapping (see
        :func:`market_data.company_ticker_map`), a single ticker string, or an
        iterable of allowed symbols. ``None`` treats ``company_key`` as the
        ticker, which is convenient for isolated tests.
    cache:
        Optional per-run memo for loaded series (pass the same dict across calls).

    Returns
    -------
    dict
        All keys in :data:`FEATURES` plus :data:`MISSING_KEY`. Unavailable
        values are ``None`` (never imputed, never a fabricated 0); the flag is 1
        whenever at least one feature is unavailable.
    """
    result: dict[str, float | int | None] = {name: None for name in FEATURES}
    result[MISSING_KEY] = 1
    cutoff_day = parse_date(cutoff)
    if cutoff_day is None:
        return result
    ticker = _resolve_ticker(company_key, tickers)
    if not ticker:
        return result
    series = load_series(store, ticker, cache=cache)
    company = _company_features(series, cutoff_day)
    if company is None:
        return result
    result.update(company)

    spy = load_series(store, SPY, cache=cache)
    xbi = load_series(store, XBI, cache=cache)
    spy_return = _window_return(spy, cutoff_day)
    xbi_return = _window_return(xbi, cutoff_day)
    if spy_return is not None:
        result["mkt_rel_spy_12m"] = float(result["mkt_ret_12m"]) - spy_return
    if xbi_return is not None:
        result["mkt_rel_xbi_12m"] = float(result["mkt_ret_12m"]) - xbi_return
    result["mkt_regime_spy_above_200d"] = _regime_spy_above_200d(spy, cutoff_day)
    result[MISSING_KEY] = 0 if all(result[name] is not None for name in FEATURES) else 1
    return result


def attach_market_features(store: Any, examples: Iterable[dict[str, Any]], companies: Any,
                           tickers: Any = None) -> dict[str, Any]:
    """Add the market feature group to every example in place.

    Only the :data:`FEATURES`/``mkt_missing`` keys are written; base R&D and
    financial features are never removed or overwritten, and examples whose
    company has no usable market data simply receive ``None`` values plus
    ``mkt_missing=1``. Returns a small coverage summary for reporting.
    """
    mapping = company_ticker_map(companies, tickers)
    cache: dict[Any, Any] = {}
    summary: dict[str, Any] = {
        "examples": 0,
        "with_market_data": 0,
        "missing": 0,
        "no_ticker": 0,
        "non_null_by_feature": {name: 0 for name in FEATURES},
    }
    for example in examples:
        features = example.get("features")
        if not isinstance(features, dict):
            features = {}
            example["features"] = features
        values = market_features(store, example.get("company_key"), example.get("cutoff"),
                                 mapping, cache=cache)
        features.update(values)
        summary["examples"] += 1
        company_key = str(example.get("company_key") or "")
        if not mapping.get(company_key):
            summary["no_ticker"] += 1
        if int(values[MISSING_KEY]):  # type: ignore[arg-type]
            summary["missing"] += 1
        else:
            summary["with_market_data"] += 1
        for name in FEATURES:
            if values[name] is not None:
                summary["non_null_by_feature"][name] += 1
    return summary
