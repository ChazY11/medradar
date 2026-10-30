"""Look-ahead-free event study around MedRadar signals.

Method (also mirrored in ``docs/SCHEMA.md`` and the return payload)
-------------------------------------------------------------------
* **Entry is the open of the first trading day strictly after ``signal_date``.**
  Using the signal-day close (or the signal-day open) would silently leak the
  reaction to the news into the entry price. Signals dated on a weekend or
  holiday simply enter on the next session.
* **Exit is the close of entry + ``h`` trading days** on the benchmark calendar.
  A horizon whose exit bar does not exist yet (signal too recent, ticker
  delisted) is reported missing instead of guessed.
* ``AR = stock return - benchmark return`` over the exact same window, using
  dividend/split adjusted prices (see :mod:`medradar.prices`). A ``direction``
  of ``-1`` flips the sign, so ``mean`` always has the meaning "return of the
  signal's direction"; the v1 paper trader stays long-only, but the signal
  validation itself is symmetric.
* The event-time curve is the mean cumulative abnormal return from the entry
  open. Two conventions are emitted: ``curve`` is indexed relative to the
  **entry day** (``0`` = entry session) and ``curve_signal_relative`` is indexed
  relative to the **signal date** (``0`` = the day the news became public,
  ``1`` = entry session), which is what the report renders.

Everything is computed from data available at or before the exit bar; there is
no rolling statistic that uses future prices.
"""

from __future__ import annotations

import bisect
from typing import Any, Iterable, Mapping, Sequence

from .prices import load_series
from .util import bootstrap_ci, iso, summarize, t_stat

DEFAULT_HORIZONS: tuple[int, ...] = (1, 5, 20, 60)
CURVE_START = -5
CURVE_END = 60
MIN_EVENTS = 3


# --------------------------------------------------------------------------- helpers
def normalize_signal_kinds(signal_kind: Any) -> tuple[str, ...] | None:
    """Normalise ``signal_kind`` to a tuple of kinds (``None`` = everything)."""
    if signal_kind is None:
        return None
    if isinstance(signal_kind, str):
        items = [part.strip() for part in signal_kind.split(",")]
    else:
        items = [str(part).strip() for part in signal_kind]
    kinds = tuple(dict.fromkeys(item for item in items if item))
    if not kinds or kinds == ("all",):
        return None
    return kinds


def _direction(value: Any) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        number = 0
    if number == 0:
        return 1  # unknown direction is treated as a long candidate
    return -1 if number < 0 else 1


def _insufficient(reason: str, counts: Mapping[str, Any] | None = None, benchmark: str = "SPY") -> dict[str, Any]:
    return {
        "status": "insufficient_data",
        "reason": reason,
        "benchmark": benchmark,
        "counts": dict(counts or {}),
    }


def load_signals(db, kinds: tuple[str, ...] | None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Read and normalise the ``signals`` table (shared with :mod:`medradar.paper`).

    Signals whose public timestamp quality is ``unknown`` are excluded from any
    trading study: they may still appear in the industry analysis, but they
    cannot support a claim about returns.
    """
    rows = db.query(
        "SELECT signal_id, ticker, signal_date, kind, direction, track_id, score,"
        " available_at, timestamp_quality"
        " FROM signals"
    )
    signals: list[dict[str, Any]] = []
    skipped = {"filtered_kind": 0, "no_ticker": 0, "no_date": 0, "unknown_timestamp": 0}
    for row in rows:
        kind = str(row.get("kind") or "")
        if kinds is not None and kind not in kinds:
            skipped["filtered_kind"] += 1
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        signal_date = iso(row.get("signal_date"))
        if not ticker:
            skipped["no_ticker"] += 1
            continue
        if not signal_date:
            skipped["no_date"] += 1
            continue
        if str(row.get("timestamp_quality") or "date").lower() == "unknown":
            skipped["unknown_timestamp"] += 1
            continue
        signals.append(
            {
                "signal_id": row.get("signal_id") or "",
                "ticker": ticker,
                "signal_date": signal_date,
                "kind": kind or "unknown",
                "direction": _direction(row.get("direction")),
                "track_id": row.get("track_id") or "",
                "score": float(row.get("score") or 0.0),
                "available_at": iso(row.get("available_at")),
                "timestamp_quality": str(row.get("timestamp_quality") or "date").lower(),
            }
        )
    return signals, skipped


def ingest_signals(db, signals: Iterable[Mapping[str, Any]]) -> int:
    """Persist analysis-stage signal dicts (SCHEMA §5) into the ``signals`` table.

    ``analyze`` produces the signals inside ``out/metrics.json``; the trading
    stage reads SQLite, so the integration step can bridge the two with::

        ingest_signals(db, metrics["signals"])

    Returns the number of rows written. Invalid rows (missing id/ticker/date)
    are skipped rather than silently stored with broken keys.
    """
    rows: list[dict[str, Any]] = []
    for signal in signals or []:
        signal_id = str(signal.get("signal_id") or "").strip()
        ticker = str(signal.get("ticker") or "").strip().upper()
        signal_date = iso(signal.get("signal_date"))
        if not signal_id or not ticker or not signal_date:
            continue
        quality = str(signal.get("timestamp_quality") or "date").lower()
        if quality == "unknown":
            continue  # cannot be traded or evaluated: no reliable public time
        rows.append(
            {
                "signal_id": signal_id,
                "event_id": signal.get("event_id"),
                "company_key": signal.get("company_key"),
                "ticker": ticker,
                "signal_date": signal_date,
                "kind": signal.get("kind") or "unknown",
                "direction": _direction(signal.get("direction")),
                "score": float(signal.get("score") or 0.0),
                "track_id": signal.get("track_id"),
                "reason_zh": signal.get("reason_zh", ""),
                "available_at": iso(signal.get("available_at")) or signal_date,
                "timestamp_quality": quality,
            }
        )
    return int(db.upsert_signals(rows)) if rows else 0


def _entry(
    series, benchmark, signal_date: str
) -> tuple[int, str, float, float] | None:
    """First session strictly after ``signal_date`` where both legs are priced."""
    start = bisect.bisect_right(benchmark.dates, signal_date)
    for index in range(start, len(benchmark.dates)):
        day = benchmark.dates[index]
        stock_open = series.open(day)
        if stock_open is None or stock_open <= 0:
            continue
        benchmark_entry = benchmark.open(day)
        if benchmark_entry is None or benchmark_entry <= 0:
            benchmark_entry = benchmark.close(day)
        if benchmark_entry is None or benchmark_entry <= 0:
            continue
        return index, day, stock_open, benchmark_entry
    return None


def _ar(
    series, benchmark, entry_index: int, entry_open: float, benchmark_entry: float, horizon: int
) -> float | None:
    exit_index = entry_index + int(horizon)
    if exit_index >= len(benchmark.dates):
        return None
    day = benchmark.dates[exit_index]
    stock_close = series.close(day)
    benchmark_close = benchmark.close(day)
    if stock_close is None or benchmark_close is None:
        return None
    return (stock_close / entry_open - 1.0) - (benchmark_close / benchmark_entry - 1.0)


def _curve(
    series,
    benchmark,
    entry_index: int,
    entry_open: float,
    benchmark_entry: float,
    direction: int,
    first_day: int,
    last_day: int,
) -> dict[int, float | None]:
    values: dict[int, float | None] = {}
    for offset in range(first_day, last_day + 1):
        index = entry_index + offset
        if index < 0 or index >= len(benchmark.dates):
            values[offset] = None
            continue
        day = benchmark.dates[index]
        stock_close = series.close(day)
        benchmark_close = benchmark.close(day)
        if stock_close is None or benchmark_close is None:
            values[offset] = None
            continue
        values[offset] = direction * (
            (stock_close / entry_open - 1.0) - (benchmark_close / benchmark_entry - 1.0)
        )
    return values


def _horizon_stats(values: Sequence[float | None]) -> dict[str, Any]:
    clean = [float(v) for v in values if v is not None]
    summary = summarize(clean)
    ci = bootstrap_ci(clean) if len(clean) >= 3 else None
    return {
        "n": summary["n"],
        "mean": summary["mean"],
        "median": summary["median"],
        "std": summary["std"],
        "t": t_stat(clean),
        "ci95": ci,
        "hit_rate": (sum(1 for value in clean if value > 0) / len(clean)) if clean else None,
    }


def _mean_curve(events: Sequence[Mapping[str, Any]], offsets: Sequence[int], key: str) -> tuple[list[float | None], list[int]]:
    means: list[float | None] = []
    counts: list[int] = []
    for offset in offsets:
        values = [
            event["curve"][offset]
            for event in events
            if event["curve"].get(offset) is not None
        ]
        means.append(sum(values) / len(values) if values else None)
        counts.append(len(values))
    return means, counts


# --------------------------------------------------------------------------- study
def run_event_study(
    db,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    benchmark: str = "SPY",
    signal_kind: Any = None,
    min_events: int = MIN_EVENTS,
) -> dict[str, Any]:
    """Run the abnormal-return study on every signal in the SQLite store.

    Returns a rich dict with ``status="ok"`` or ``{"status": "insufficient_data",
    "reason": ..., "counts": {...}}`` when there is not enough usable data.
    ``signal_kind`` optionally restricts the sample (``None`` / ``"all"`` = all
    kinds) so the paper trader can embed a study over exactly its own sample.
    """
    horizons = sorted({int(h) for h in horizons if int(h) > 0})
    benchmark = str(benchmark or "SPY").strip().upper() or "SPY"
    kinds = normalize_signal_kinds(signal_kind)
    if not horizons:
        return _insufficient("no_horizons", benchmark=benchmark)

    signals, skipped = load_signals(db, kinds)
    counts: dict[str, Any] = {"signals": len(signals), **skipped}
    if not signals:
        return _insufficient("no_signals", counts, benchmark=benchmark)

    benchmark_series = load_series(db, benchmark)
    if benchmark_series is None:
        return _insufficient("benchmark_missing", counts, benchmark=benchmark)

    series_cache: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    for signal in signals:
        ticker = signal["ticker"]
        if ticker not in series_cache:
            series_cache[ticker] = load_series(db, ticker)
        series = series_cache[ticker]
        if series is None:
            skipped["no_prices"] = skipped.get("no_prices", 0) + 1
            continue
        entry = _entry(series, benchmark_series, signal["signal_date"])
        if entry is None:
            skipped["no_entry_bar"] = skipped.get("no_entry_bar", 0) + 1
            continue
        entry_index, entry_day, entry_open, benchmark_entry = entry
        direction = signal["direction"]
        abnormal: dict[int, float | None] = {}
        for horizon in horizons:
            raw = _ar(series, benchmark_series, entry_index, entry_open, benchmark_entry, horizon)
            abnormal[horizon] = None if raw is None else direction * raw
        native_curve = _curve(
            series,
            benchmark_series,
            entry_index,
            entry_open,
            benchmark_entry,
            direction,
            CURVE_START - 1,  # one extra pre-entry bar so the signal-relative curve reaches -5
            CURVE_END,
        )
        events.append(
            {
                **signal,
                "entry_date": entry_day,
                "entry_price": entry_open,
                "abnormal": abnormal,
                "curve": native_curve,
            }
        )

    usable_by_horizon = {
        str(horizon): sum(1 for event in events if event["abnormal"].get(horizon) is not None)
        for horizon in horizons
    }
    counts.update(
        {
            "usable": len(events),
            "usable_by_horizon": usable_by_horizon,
            **skipped,
        }
    )
    if len(events) < max(1, int(min_events)):
        return _insufficient("too_few_events", counts, benchmark=benchmark)
    if not any(usable_by_horizon.values()):
        return _insufficient("no_horizon_data", counts, benchmark=benchmark)

    kinds_present = sorted({event["kind"] for event in events})
    by_kind: dict[str, dict[str, dict[str, Any]]] = {}
    for kind in kinds_present:
        subset = [event for event in events if event["kind"] == kind]
        by_kind[kind] = {
            str(horizon): _horizon_stats([event["abnormal"].get(horizon) for event in subset])
            for horizon in horizons
        }
    all_stats = {
        str(horizon): _horizon_stats([event["abnormal"].get(horizon) for event in events])
        for horizon in horizons
    }

    entry_days = list(range(CURVE_START, CURVE_END + 1))
    entry_means, entry_counts = _mean_curve(events, entry_days, "curve")
    curve = {
        "origin": "entry_day",
        "days": entry_days,
        "all": entry_means,
        "n": entry_counts,
        "by_kind": {
            kind: _mean_curve([event for event in events if event["kind"] == kind], entry_days, "curve")[0]
            for kind in kinds_present
        },
    }

    # Signal-relative view: entry session is trading day +1 after the signal date.
    signal_days = list(range(CURVE_START, CURVE_END + 1))
    signal_offsets = [day - 1 for day in signal_days]
    signal_means, signal_counts = _mean_curve(events, signal_offsets, "curve")
    curve_signal = {
        "origin": "signal_date",
        "days": signal_days,
        "all": signal_means,
        "n": signal_counts,
        "by_kind": {
            kind: _mean_curve(
                [event for event in events if event["kind"] == kind], signal_offsets, "curve"
            )[0]
            for kind in kinds_present
        },
    }

    return {
        "status": "ok",
        "benchmark": benchmark,
        "horizons": horizons,
        "entry": "open of the first trading day strictly after signal_date",
        "ar": "stock total return minus benchmark total return over the same window; direction=-1 flips sign",
        "n_signals": len(signals),
        "n_events": len(events),
        "by_kind": by_kind,
        "all": all_stats,
        "curve": curve,
        "curve_signal_relative": curve_signal,
        "skipped": dict(skipped),
        "counts": counts,
    }
