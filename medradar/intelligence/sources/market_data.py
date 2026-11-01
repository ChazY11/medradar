"""Point-in-time daily market bars imported offline from MedRadar's price table.

Why this module exists
----------------------
The Market-to-R&D layer needs a *market* input that is demonstrably known at the
forecast cutoff. MedRadar's base repository already stores a daily US-equity
lane in its ``prices`` table, fetched once from Yahoo Finance's public chart
endpoint (see the base repository's ``medradar/prices.py``). This module copies
those bars for the curated device companies plus two benchmarks into the
intelligence database; it performs **no network calls** itself.

Provenance and caveats (read this before using the numbers):

* Source lane: Yahoo Finance daily chart data, ``prices(ticker, date, open,
  high, low, close, adj_close, volume)``. ``adj_close`` is the split- and
  dividend-adjusted close; every feature in ``features/market_features.py``
  uses ``adj_close`` only so a split never becomes a fake return.
* Imported offline: this module only reads the local SQLite file. The original
  fetch time of each bar is not stored in ``prices``, so ``retrieved_at`` on
  every imported row records the *local import* moment, not a vendor
  publication timestamp. Knowledge time for features is the trading date: a bar
  dated ``d`` is treated as known at the end of ``d``.
* Survivorship: the table is a current snapshot of tickers a previous collection
  run asked for. Delisted/acquired tickers are absent unless they were fetched
  while listed, and a company that changed ticker keeps only the tickers that
  were requested. Matched tickers are therefore *not* a random sample.
* Coverage is incomplete: 44 of the curated 51 device companies have a ticker
  and 38 of those tickers exist in the local table. Foreign listings
  (``SHL.DE``, ``AMBU-B.CO``, ADRs such as ``PHG``/``OCPNY``) are only present
  when the base lane fetched them; ADRs are also a different instrument from
  the local shares.
* This is a research import, **not** a licensed market-data feed. Do not
  redistribute raw bars; ``data/`` is gitignored and only aggregates are
  committed.

The table written here is::

    market_bars(ticker, date, open, high, low, close, adj_close, volume,
                source, retrieved_at)

with primary key ``(ticker, date)``. Re-running :func:`collect` replaces the
imported rows for the requested tickers, so the operation is idempotent apart
from the ``retrieved_at`` timestamp.

Scope boundary: market capitalisation and valuation multiples are **not**
implemented. They need shares-outstanding / price-to-book inputs that this
database does not contain, and silently approximating them from price alone
would fabricate a fundamental factor.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote

from ...util import iso, utc_now_iso

#: Benchmarks used by the market feature group (market and biotech proxies).
DEFAULT_BENCHMARKS: tuple[str, ...] = ("SPY", "XBI")
#: ``source`` value stored on every imported bar: the base repo's Yahoo daily lane.
PRICE_SOURCE = "yahoo_finance_daily"
#: Column order of :data:`MARKET_BARS_COLUMNS`, reused by the INSERT below.
MARKET_BARS_COLUMNS = (
    "ticker", "date", "open", "high", "low", "close", "adj_close", "volume",
    "source", "retrieved_at",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_bars (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    adj_close REAL,
    volume INTEGER,
    source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_market_bars_date ON market_bars(date);
CREATE INDEX IF NOT EXISTS idx_market_bars_ticker_date ON market_bars(ticker, date);
"""

_INSERT_SQL = (
    "INSERT OR REPLACE INTO market_bars(" + ", ".join(MARKET_BARS_COLUMNS) + ")"
    " VALUES (" + ", ".join("?" for _ in MARKET_BARS_COLUMNS) + ")"
)


# --------------------------------------------------------------------------- helpers
def normalise_ticker(value: Any) -> str:
    """Upper-case a ticker symbol and drop blanks (keeps dots/dashes as-is)."""
    return str(value or "").strip().upper()


def _company_entries(companies: Any) -> list[dict[str, Any]]:
    """Best-effort ``[{"key", "ticker"}]`` view of the supported companies input.

    Accepts a :class:`medradar.config.CompanyRegistry` (``.all()``), a JSON-style
    list of company dicts (the ``config/companies_device.json`` shape), a mapping
    ``key -> ticker`` (or ``key -> company dict``), or an iterable of bare keys.
    """
    if companies is None:
        return []
    if hasattr(companies, "all") and callable(getattr(companies, "all")):
        try:
            source = list(companies.all())  # type: ignore[union-attr]
        except TypeError:  # pragma: no cover - defensive
            source = []
        entries = []
        for item in source:
            if isinstance(item, Mapping):
                entries.append({"key": str(item.get("key") or ""), "ticker": normalise_ticker(item.get("ticker"))})
        return [entry for entry in entries if entry["key"]]
    if isinstance(companies, Mapping):
        entries = []
        for key, value in companies.items():
            ticker = value.get("ticker") if isinstance(value, Mapping) else value
            entries.append({"key": str(key), "ticker": normalise_ticker(ticker)})
        return entries
    entries = []
    for item in companies:
        if isinstance(item, Mapping):
            entries.append({"key": str(item.get("key") or ""), "ticker": normalise_ticker(item.get("ticker"))})
        else:
            entries.append({"key": str(item), "ticker": ""})
    return [entry for entry in entries if entry["key"]]


def company_ticker_map(companies: Any, tickers: Any = None) -> dict[str, str]:
    """Return the ``company_key -> ticker`` map used by collection and features.

    ``companies`` is the curated registry (list of dicts, a ``CompanyRegistry``,
    a ``{key: ticker}`` mapping, or an iterable of keys). ``tickers`` is an
    optional authoritative override:

    * a mapping ``company_key -> ticker`` **replaces** the derived map;
    * any other iterable is treated as an allow-list of ticker symbols applied to
      the derived map.
    """
    if tickers is not None and isinstance(tickers, Mapping):
        explicit = {
            str(key): normalise_ticker(value)
            for key, value in tickers.items()
            if normalise_ticker(value)
        }
        return explicit
    derived = {entry["key"]: entry["ticker"] for entry in _company_entries(companies) if entry["ticker"]}
    if tickers is not None:
        allowed = {normalise_ticker(value) for value in tickers if normalise_ticker(value)}
        derived = {key: ticker for key, ticker in derived.items() if ticker in allowed}
    return derived


def _benchmark_list(benchmarks: Any) -> list[str]:
    if benchmarks is None:
        benchmarks = DEFAULT_BENCHMARKS
    seen: list[str] = []
    for value in benchmarks:
        ticker = normalise_ticker(value)
        if ticker and ticker not in seen:
            seen.append(ticker)
    return seen


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # drop NaN


def _volume(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def ensure_schema(store: Any) -> None:
    """Create the ``market_bars`` table/indexes in an open intelligence store."""
    store.conn.executescript(SCHEMA)
    store.conn.commit()


def open_prices_db_readonly(path: str | Path) -> sqlite3.Connection:
    """Open the base MedRadar database strictly read-only (SQLite ``mode=ro``).

    A write attempted through the returned connection raises
    :class:`sqlite3.OperationalError`, so the source database can never be
    modified by an import. The connection is also marked ``query_only`` as a
    second, belt-and-braces guard.
    """
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"price database not found: {target}")
    uri = "file:" + quote(target.resolve().as_posix(), safe="/:") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


# --------------------------------------------------------------------------- collect
def collect(store: Any, prices_db_path: str | Path, companies: Any,
            benchmarks: Iterable[str] | None = DEFAULT_BENCHMARKS,
            tickers: Any = None) -> dict[str, Any]:
    """Copy mapped company tickers + benchmark bars into ``market_bars``.

    Parameters
    ----------
    store:
        Open :class:`~medradar.intelligence.storage.IntelligenceStore`. The
        ``market_bars`` table is created if missing.
    prices_db_path:
        Path to the base MedRadar SQLite file that holds ``prices``. Opened
        read-only; the file is never written.
    companies:
        Curated company registry (list of dicts / ``CompanyRegistry`` / mapping).
    benchmarks:
        Symbols always imported for benchmark-relative features. ``None`` keeps
        the defaults ``("SPY", "XBI")``; pass ``()`` to import none.
    tickers:
        Optional explicit ``company_key -> ticker`` override (or ticker
        allow-list) — see :func:`company_ticker_map`.

    Returns
    -------
    dict
        Counts and coverage: ``tickers`` (requested company tickers),
        ``tickers_imported``, ``benchmarks``, ``benchmarks_imported``, ``rows``,
        ``date_min``, ``date_max``, ``missing_tickers`` (requested symbols with
        no bars in the source), ``unmapped_companies`` (curated companies
        without a ticker), ``per_ticker_rows`` and ``rows_in_table``.
    """
    mapping = company_ticker_map(companies, tickers)
    benchmark_symbols = _benchmark_list(benchmarks)
    requested = sorted(set(mapping.values()) | set(benchmark_symbols))
    unmapped = sorted(entry["key"] for entry in _company_entries(companies) if not entry["ticker"])

    source = open_prices_db_readonly(prices_db_path)
    try:
        tables = {
            str(row[0])
            for row in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "prices" not in tables:
            raise ValueError(f"{prices_db_path} has no 'prices' table")
        ensure_schema(store)
        retrieved_at = utc_now_iso()
        per_ticker_rows: dict[str, int] = {}
        missing_tickers: list[str] = []
        pending: list[tuple[Any, ...]] = []
        date_min: str | None = None
        date_max: str | None = None
        for ticker in requested:
            fetched = source.execute(
                "SELECT date, open, high, low, close, adj_close, volume FROM prices"
                " WHERE ticker = ? ORDER BY date",
                (ticker,),
            ).fetchall()
            bars: list[tuple[Any, ...]] = []
            for raw in fetched:
                day = iso(raw[0])
                if not day:
                    continue
                bars.append((
                    ticker, day, _number(raw[1]), _number(raw[2]), _number(raw[3]),
                    _number(raw[4]), _number(raw[5]), _volume(raw[6]),
                    PRICE_SOURCE, retrieved_at,
                ))
            per_ticker_rows[ticker] = len(bars)
            if not bars:
                missing_tickers.append(ticker)
                continue
            pending.extend(bars)
            first, last = bars[0][1], bars[-1][1]
            date_min = first if date_min is None or first < date_min else date_min
            date_max = last if date_max is None or last > date_max else date_max

        try:
            # Replace, do not merge: a re-run must reproduce the source exactly
            # for the requested tickers instead of keeping stale bars.
            for ticker in requested:
                store.conn.execute("DELETE FROM market_bars WHERE ticker = ?", (ticker,))
            store.conn.executemany(_INSERT_SQL, pending)
            store.conn.commit()
        except Exception:
            store.conn.rollback()
            raise
        rows_in_table = int(store.conn.execute("SELECT COUNT(*) FROM market_bars").fetchone()[0])
    finally:
        source.close()

    return {
        "source": PRICE_SOURCE,
        "prices_db": str(prices_db_path),
        "retrieved_at": retrieved_at,
        "companies": len(mapping),
        "tickers": len(mapping),
        "tickers_imported": sum(1 for ticker in mapping.values() if per_ticker_rows.get(ticker, 0) > 0),
        "benchmarks": len(benchmark_symbols),
        "benchmarks_imported": sum(1 for ticker in benchmark_symbols if per_ticker_rows.get(ticker, 0) > 0),
        "rows": len(pending),
        "rows_in_table": rows_in_table,
        "date_min": date_min,
        "date_max": date_max,
        "missing_tickers": missing_tickers,
        "unmapped_companies": unmapped,
        "per_ticker_rows": per_ticker_rows,
    }
