"""Daily US-equity prices from Yahoo Finance's public chart endpoint.

Why this module exists
----------------------
The trading study is *academic signal validation*, so the price layer has to be
boring and reproducible:

* **Adjusted returns only.** Yahoo ships raw OHLC plus an ``adjclose`` series.
  Downstream code must never mix the two, otherwise a single split or dividend
  turns into a fake return. :func:`adjusted_close` and :func:`adjusted_open`
  scale every price onto the adjusted-close basis so a return computed from an
  entry *open* and an exit *close* is split/dividend safe.
* **No API key, polite by default.** One request per ticker, at least
  ``MIN_REQUEST_GAP`` seconds apart, and every response goes through the shared
  :class:`medradar.http.Fetcher` cache. A failed ticker never breaks the batch.
* **Two URL shapes.** ``range=10y&interval=1d`` is the fast path; if Yahoo
  rejects it we fall back to explicit ``period1``/``period2`` epochs (this also
  works for non-standard horizons such as ``years=3``).

The function :func:`fetch_prices` is deliberately callable on its own::

    from medradar.db import DB
    from medradar.http import Fetcher
    from medradar.prices import fetch_prices

    with DB("data/medradar.sqlite") as db:
        stats = fetch_prices(db, Fetcher(cache_dir="data/cache"), ["MDT", "LLY"])

It writes the ``prices`` table and also fetches the ``SPY`` (market) and ``XBI``
(biotech) benchmarks used by the event study.
"""

from __future__ import annotations

import bisect
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

from .http import NotFound
from .util import iso

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
DEFAULT_BENCHMARKS: tuple[str, ...] = ("SPY", "XBI")
MIN_REQUEST_GAP = 0.5
_RANGE_BY_YEARS = {1: "1y", 2: "2y", 5: "5y", 10: "10y"}


# --------------------------------------------------------------------------- values
def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def adjusted_close(row: Mapping[str, Any]) -> float | None:
    """Total-return close: ``adj_close`` when available, else the raw close."""
    adjusted = _as_float(row.get("adj_close"))
    if adjusted is not None:
        return adjusted
    return _as_float(row.get("close"))


def adjusted_open(row: Mapping[str, Any]) -> float | None:
    """Open rescaled onto the adjusted-close basis.

    ``adj_open = open * adj_close / close`` keeps a trade that enters at the
    open and exits at an adjusted close consistent even when a split or a large
    dividend happens inside the holding window.
    """
    raw_open = _as_float(row.get("open"))
    if raw_open is None:
        return None
    raw_close = _as_float(row.get("close"))
    adjusted = _as_float(row.get("adj_close"))
    if raw_close and adjusted is not None and raw_close != 0:
        return raw_open * (adjusted / raw_close)
    return raw_open


# --------------------------------------------------------------------------- series
class PriceSeries:
    """Date-indexed adjusted prices for one ticker.

    Dates are ISO strings so lexicographic order equals chronological order.
    Rows without a usable close are dropped; rows with a missing open are kept
    (``open(day)`` simply returns ``None`` for them).
    """

    def __init__(self, rows: Iterable[Mapping[str, Any]]) -> None:
        close_map: dict[str, float] = {}
        open_map: dict[str, float | None] = {}
        raw_close: dict[str, float | None] = {}
        for row in rows:
            day = iso(row.get("date"))
            if not day:
                continue
            close = adjusted_close(row)
            if close is None:
                continue
            close_map[day] = close
            open_map[day] = adjusted_open(row)
            raw_close[day] = _as_float(row.get("close"))
        self.dates: list[str] = sorted(close_map)
        self._close = close_map
        self._open = open_map
        self._raw_close = raw_close
        self.by_date = {day: {"close": close_map[day], "open": open_map[day]} for day in self.dates}

    def __len__(self) -> int:
        return len(self.dates)

    def __bool__(self) -> bool:
        return bool(self.dates)

    def open(self, day: str) -> float | None:
        return self._open.get(day)

    def close(self, day: str) -> float | None:
        return self._close.get(day)

    def raw_close(self, day: str) -> float | None:
        return self._raw_close.get(day)

    def last_close_on_or_before(self, day: str | None) -> tuple[float | None, str | None]:
        """Return ``(adjusted close, date)`` at or before ``day`` (stale mark)."""
        if not day:
            return None, None
        index = bisect.bisect_right(self.dates, day) - 1
        if index < 0:
            return None, None
        found = self.dates[index]
        return self._close[found], found


def load_series(db, ticker: str) -> PriceSeries | None:
    """Load one ticker's prices from SQLite (``None`` when nothing usable)."""
    series = PriceSeries(db.prices_for(str(ticker)))
    return series if series.dates else None


# --------------------------------------------------------------------------- parser
def _timestamp_to_date(value: Any) -> str | None:
    try:
        stamp = int(value)
    except (TypeError, ValueError):
        return None
    if stamp <= 0:
        return None
    try:
        return datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat()
    except (OSError, OverflowError, ValueError):  # pragma: no cover - defensive
        return None


def parse_chart(payload: Any, ticker: str) -> list[dict[str, Any]]:
    """Turn a Yahoo ``chart`` payload into ``prices`` rows.

    Raises :class:`ValueError` for an error payload or an empty result so the
    caller can try the ``period1``/``period2`` fallback. Rows are sorted by date
    and rows without a close are skipped (Yahoo emits a null bar for a trading
    day that is still in progress).
    """
    if not isinstance(payload, Mapping):
        raise ValueError("payload is not an object")
    chart = payload.get("chart")
    if not isinstance(chart, Mapping):
        raise ValueError("payload has no chart object")
    error = chart.get("error")
    if error:
        raise ValueError(f"yahoo error: {error}")
    results = chart.get("result") or []
    if not results:
        raise ValueError("yahoo returned no result")
    result = results[0] or {}
    timestamps: Sequence[Any] = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or []
    quote_block = quotes[0] if quotes else {}
    adj_blocks = indicators.get("adjclose") or []
    adj_values: Sequence[Any] = (adj_blocks[0].get("adjclose") or []) if adj_blocks else []

    def _series(key: str) -> Sequence[Any]:
        values = quote_block.get(key) or []
        return values

    series_open, series_high = _series("open"), _series("high")
    series_low, series_close, series_volume = _series("low"), _series("close"), _series("volume")

    rows: list[dict[str, Any]] = []
    for index, stamp in enumerate(timestamps):
        day = _timestamp_to_date(stamp)
        if not day:
            continue
        close = _as_float(series_close[index]) if index < len(series_close) else None
        if close is None:
            continue
        volume = series_volume[index] if index < len(series_volume) else None
        rows.append(
            {
                "ticker": str(ticker).strip().upper(),
                "date": day,
                "open": _as_float(series_open[index]) if index < len(series_open) else None,
                "high": _as_float(series_high[index]) if index < len(series_high) else None,
                "low": _as_float(series_low[index]) if index < len(series_low) else None,
                "close": close,
                "adj_close": _as_float(adj_values[index]) if index < len(adj_values) else None,
                "volume": int(volume) if volume is not None else None,
            }
        )
    if not rows:
        raise ValueError("yahoo payload contains no usable daily bars")
    rows.sort(key=lambda row: row["date"])
    return rows


# --------------------------------------------------------------------------- fetcher
class _Pacer:
    """Enforce a minimum gap between *network* requests (cache hits are free)."""

    def __init__(self, gap: float) -> None:
        self.gap = max(0.0, float(gap))
        self._last_network = 0.0

    def wait(self) -> None:
        if self.gap <= 0:
            return
        remaining = self.gap - (time.monotonic() - self._last_network)
        if remaining > 0:
            time.sleep(remaining)

    def mark(self) -> None:
        self._last_network = time.monotonic()


def _get_json(fetcher, ticker: str, params: Mapping[str, Any], refresh: bool, pacer: _Pacer) -> Any:
    pacer.wait()
    before = int(fetcher.stats.get("requests", 0))
    payload = fetcher.get_json(
        CHART_URL.format(ticker=quote(str(ticker), safe="")),
        params=dict(params),
        refresh=refresh,
    )
    if int(fetcher.stats.get("requests", 0)) > before:
        pacer.mark()
    return payload


def fetch_ticker_rows(
    fetcher,
    ticker: str,
    years: int = 10,
    refresh: bool = False,
    pacer: _Pacer | None = None,
    min_request_gap: float = MIN_REQUEST_GAP,
) -> list[dict[str, Any]]:
    """Fetch one ticker's daily bars, trying ``range=`` then ``period1/period2``."""
    ticker = str(ticker).strip().upper()
    if not ticker:
        raise ValueError("empty ticker")
    pacer = pacer or _Pacer(min_request_gap)
    years = max(1, int(years or 1))
    attempts: list[dict[str, Any]] = []
    if years in _RANGE_BY_YEARS:
        attempts.append({"range": _RANGE_BY_YEARS[years], "interval": "1d"})
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(round(365.25 * years)))
    attempts.append(
        {
            "period1": int(start.timestamp()),
            "period2": int(end.timestamp()),
            "interval": "1d",
            "includeAdjustedClose": "true",
        }
    )
    errors: list[str] = []
    for params in attempts:
        try:
            payload = _get_json(fetcher, ticker, params, refresh, pacer)
            rows = parse_chart(payload, ticker)
            if rows:
                return rows
            errors.append(f"{params}: empty result")
        except NotFound:
            # The symbol itself does not exist - the fallback URL cannot help.
            raise
        except Exception as exc:  # one shape may be rejected; try the next one
            errors.append(f"{params}: {type(exc).__name__}: {exc}")
    raise RuntimeError("; ".join(errors))


def _normalize_tickers(values: Iterable[Any] | None) -> list[str]:
    seen: dict[str, None] = {}
    for value in values or []:
        ticker = str(value or "").strip().upper()
        if ticker:
            seen.setdefault(ticker, None)
    return list(seen)


def fetch_prices(
    db,
    fetcher,
    tickers: Iterable[str],
    years: int = 10,
    benchmarks: Iterable[str] | None = DEFAULT_BENCHMARKS,
    refresh: bool = False,
    min_request_gap: float = MIN_REQUEST_GAP,
) -> dict[str, Any]:
    """Fetch daily bars for ``tickers`` + benchmarks and upsert them.

    Returns ``{"ok": [...], "failed": [{"ticker", "error"}], "rows": n,
    "requests": n, "cache_hits": n, "benchmarks": [...], "years": 10}``.
    ``requests`` counts the HTTP calls actually made during this call (cache
    hits are reported separately), and a single failing ticker is isolated.
    """
    bench_list = _normalize_tickers(benchmarks)
    wanted = _normalize_tickers([*bench_list, *list(tickers or [])])
    requests_before = int(fetcher.stats.get("requests", 0))
    cache_before = int(fetcher.stats.get("cache_hits", 0))
    pacer = _Pacer(min_request_gap)
    ok: list[str] = []
    failed: list[dict[str, str]] = []
    rows_total = 0
    for ticker in wanted:
        try:
            rows = fetch_ticker_rows(
                fetcher,
                ticker,
                years=years,
                refresh=refresh,
                pacer=pacer,
                min_request_gap=min_request_gap,
            )
            written = db.upsert_prices(rows)
        except Exception as exc:  # isolate per-ticker failures on purpose
            failed.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
            continue
        ok.append(ticker)
        rows_total += int(written or 0)
    return {
        "ok": ok,
        "failed": failed,
        "rows": rows_total,
        "requests": int(fetcher.stats.get("requests", 0)) - requests_before,
        "cache_hits": int(fetcher.stats.get("cache_hits", 0)) - cache_before,
        "benchmarks": bench_list,
        "years": int(years),
    }
