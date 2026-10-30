"""SQLite storage: one unified ``events`` table plus registry and trading tables.

A single normalized event table keeps the analysis code source-agnostic - a
510(k) clearance, an NDA approval, a trial registration and an NMPA
registration all become rows with ``kind``, ``event_date``, ``company_key``,
``track_id``. That is what makes "谁的哪个方向在升温" a simple group-by.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

from .util import ensure_dir, iso, utc_now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS companies (
    key TEXT PRIMARY KEY,
    name_en TEXT,
    name_zh TEXT,
    ticker TEXT,
    cik TEXT,
    sector TEXT,
    country TEXT DEFAULT 'US',
    is_major INTEGER DEFAULT 0,
    aliases TEXT DEFAULT '[]',
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    name_zh TEXT,
    name_en TEXT,
    category TEXT,
    keywords TEXT DEFAULT '[]',
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS product_codes (
    product_code TEXT PRIMARY KEY,
    track_id TEXT,
    device_name TEXT,
    definition TEXT,
    specialty TEXT,
    regulation_number TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    event_date TEXT,
    as_of TEXT,
    company_key TEXT,
    applicant_raw TEXT,
    country TEXT DEFAULT 'US',
    track_id TEXT,
    product_code TEXT,
    title TEXT,
    summary TEXT,
    url TEXT,
    payload TEXT,
    fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_kind_date ON events(kind, event_date);
CREATE INDEX IF NOT EXISTS idx_events_company ON events(company_key, event_date);
CREATE INDEX IF NOT EXISTS idx_events_track ON events(track_id, event_date);
CREATE INDEX IF NOT EXISTS idx_events_code ON events(product_code, event_date);

CREATE TABLE IF NOT EXISTS prices (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    adj_close REAL,
    volume INTEGER,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    event_id TEXT,
    company_key TEXT,
    ticker TEXT,
    signal_date TEXT,
    kind TEXT,
    direction INTEGER,
    score REAL,
    track_id TEXT,
    reason_zh TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(signal_date);
CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker, signal_date);

CREATE TABLE IF NOT EXISTS paper_trades (
    trade_id TEXT PRIMARY KEY,
    signal_id TEXT,
    ticker TEXT,
    side TEXT,
    entry_date TEXT,
    entry_price REAL,
    exit_date TEXT,
    exit_price REAL,
    shares REAL,
    pnl REAL,
    ret REAL,
    reason TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS paper_equity (
    date TEXT PRIMARY KEY,
    equity REAL,
    cash REAL,
    exposure REAL,
    drawdown REAL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT,
    finished_at TEXT,
    stage TEXT,
    stats TEXT
);

-- Live event lane: near-real-time catalysts and the simulated orders they trigger.
CREATE TABLE IF NOT EXISTS live_alerts (
    alert_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    ticker TEXT,
    company_key TEXT,
    direction INTEGER DEFAULT 0,
    score REAL DEFAULT 0,
    headline TEXT,
    url TEXT,
    event_time TEXT,
    detected_at TEXT,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_live_alerts_time ON live_alerts(event_time);

CREATE TABLE IF NOT EXISTS paper_orders (
    order_id TEXT PRIMARY KEY,
    alert_id TEXT,
    ticker TEXT,
    side TEXT,
    qty REAL,
    fill_price REAL,
    fill_time TEXT,
    quote_time TEXT,
    slippage_bps REAL,
    status TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    ticker TEXT PRIMARY KEY,
    qty REAL,
    avg_price REAL,
    opened_at TEXT,
    track_id TEXT,
    last_price REAL,
    last_quote_time TEXT,
    market_value REAL,
    unrealized_pnl REAL,
    status TEXT DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS live_equity (
    ts TEXT PRIMARY KEY,
    cash REAL,
    market_value REAL,
    equity REAL,
    n_positions INTEGER,
    note TEXT
);
"""

EVENT_FIELDS = (
    "event_id",
    "source",
    "kind",
    "event_date",
    "as_of",
    "company_key",
    "applicant_raw",
    "country",
    "track_id",
    "product_code",
    "title",
    "summary",
    "url",
    "payload",
    "fetched_at",
)


def make_event_id(source: str, kind: str, *parts: Any) -> str:
    from .util import sha1

    joined = "|".join([source, kind] + [str(p) for p in parts if p is not None])
    return sha1(joined)[:32]


class DB:
    def __init__(self, path: str | Path = "data/medradar.sqlite") -> None:
        self.path = Path(path)
        ensure_dir(self.path.parent)
        self.conn = sqlite3.connect(self.path, timeout=60)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------------ basics
    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, tuple(params))

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> sqlite3.Cursor:
        return self.conn.executemany(sql, [tuple(r) for r in rows])

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute(sql, tuple(params)).fetchall()]

    def scalar(self, sql: str, params: Iterable[Any] = (), default: Any = None) -> Any:
        row = self.conn.execute(sql, tuple(params)).fetchone()
        return row[0] if row is not None else default

    def table_count(self, table: str) -> int:
        if table not in {
            "events",
            "companies",
            "tracks",
            "product_codes",
            "prices",
            "signals",
            "paper_trades",
            "paper_equity",
            "live_alerts",
            "paper_orders",
            "positions",
            "live_equity",
        }:
            raise ValueError(f"unknown table {table!r}")
        return int(self.scalar(f"SELECT COUNT(*) FROM {table}", default=0) or 0)

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.commit()
        finally:
            self.conn.close()

    def __enter__(self) -> "DB":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # ------------------------------------------------------------------- meta
    def meta_get(self, key: str, default: Any = None) -> Any:
        raw = self.scalar("SELECT value FROM meta WHERE key = ?", (key,))
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return raw

    def meta_set(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self.conn.commit()

    # -------------------------------------------------------------- registries
    def upsert_companies(self, companies: Iterable[Mapping[str, Any]]) -> int:
        rows, stamp = [], utc_now_iso()
        for company in companies:
            rows.append(
                (
                    company["key"],
                    company.get("name_en", ""),
                    company.get("name_zh", ""),
                    company.get("ticker", ""),
                    company.get("cik", ""),
                    company.get("sector", ""),
                    company.get("country", "US"),
                    int(bool(company.get("is_major", 0))),
                    json.dumps(company.get("aliases", []), ensure_ascii=False),
                    stamp,
                )
            )
        self.conn.executemany(
            "INSERT INTO companies(key, name_en, name_zh, ticker, cik, sector, country,"
            " is_major, aliases, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET name_en=excluded.name_en,"
            " name_zh=excluded.name_zh, ticker=excluded.ticker, cik=excluded.cik,"
            " sector=excluded.sector, country=excluded.country,"
            " is_major=excluded.is_major, aliases=excluded.aliases,"
            " updated_at=excluded.updated_at",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def upsert_tracks(self, tracks: Iterable[Mapping[str, Any]]) -> int:
        rows, stamp = [], utc_now_iso()
        for track in tracks:
            rows.append(
                (
                    track["id"],
                    track.get("name_zh", ""),
                    track.get("name_en", ""),
                    track.get("category", ""),
                    json.dumps(track.get("keywords", []), ensure_ascii=False),
                    stamp,
                )
            )
        self.conn.executemany(
            "INSERT INTO tracks(id, name_zh, name_en, category, keywords, updated_at)"
            " VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET"
            " name_zh=excluded.name_zh, name_en=excluded.name_en,"
            " category=excluded.category, keywords=excluded.keywords,"
            " updated_at=excluded.updated_at",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def upsert_product_codes(self, codes: Iterable[Mapping[str, Any]]) -> int:
        rows, stamp = [], utc_now_iso()
        for code in codes:
            rows.append(
                (
                    str(code["product_code"]),
                    code.get("track_id"),
                    code.get("device_name", ""),
                    code.get("definition", ""),
                    code.get("specialty", ""),
                    code.get("regulation_number", ""),
                    stamp,
                )
            )
        self.conn.executemany(
            "INSERT INTO product_codes(product_code, track_id, device_name, definition,"
            " specialty, regulation_number, updated_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(product_code) DO UPDATE SET track_id=excluded.track_id,"
            " device_name=excluded.device_name, definition=excluded.definition,"
            " specialty=excluded.specialty,"
            " regulation_number=excluded.regulation_number,"
            " updated_at=excluded.updated_at",
            rows,
        )
        self.conn.commit()
        return len(rows)

    # ------------------------------------------------------------------ events
    def upsert_events(self, events: Iterable[Mapping[str, Any]]) -> int:
        stamp = utc_now_iso()
        rows = []
        for event in events:
            payload = event.get("payload")
            if isinstance(payload, (dict, list)):
                payload = json.dumps(payload, ensure_ascii=False)
            rows.append(
                (
                    event["event_id"],
                    event["source"],
                    event["kind"],
                    iso(event.get("event_date")),
                    iso(event.get("as_of")) or stamp[:10],
                    event.get("company_key"),
                    event.get("applicant_raw", ""),
                    event.get("country", "US"),
                    event.get("track_id"),
                    str(event.get("product_code") or "") or None,
                    event.get("title", ""),
                    event.get("summary", ""),
                    event.get("url", ""),
                    payload or "",
                    event.get("fetched_at") or stamp,
                )
            )
        self.conn.executemany(
            "INSERT OR REPLACE INTO events(event_id, source, kind, event_date, as_of,"
            " company_key, applicant_raw, country, track_id, product_code, title,"
            " summary, url, payload, fetched_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        self.conn.commit()
        return len(rows)

    # ------------------------------------------------------------------ prices
    def upsert_prices(self, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = [
            (
                row["ticker"],
                iso(row["date"]),
                row.get("open"),
                row.get("high"),
                row.get("low"),
                row.get("close"),
                row.get("adj_close"),
                row.get("volume"),
            )
            for row in rows
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO prices(ticker, date, open, high, low, close,"
            " adj_close, volume) VALUES (?,?,?,?,?,?,?,?)",
            payload,
        )
        self.conn.commit()
        return len(payload)

    def prices_for(self, ticker: str, start: str | None = None) -> list[dict[str, Any]]:
        if start:
            return self.query(
                "SELECT * FROM prices WHERE ticker = ? AND date >= ? ORDER BY date",
                (ticker, start),
            )
        return self.query("SELECT * FROM prices WHERE ticker = ? ORDER BY date", (ticker,))

    # ----------------------------------------------------------------- signals
    def upsert_signals(self, signals: Iterable[Mapping[str, Any]]) -> int:
        stamp = utc_now_iso()
        rows = [
            (
                signal["signal_id"],
                signal.get("event_id"),
                signal.get("company_key"),
                signal.get("ticker", ""),
                iso(signal.get("signal_date")),
                signal.get("kind", ""),
                int(signal.get("direction", 0)),
                float(signal.get("score") or 0.0),
                signal.get("track_id"),
                signal.get("reason_zh", ""),
                stamp,
            )
            for signal in signals
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO signals(signal_id, event_id, company_key, ticker,"
            " signal_date, kind, direction, score, track_id, reason_zh, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        self.conn.commit()
        return len(rows)

    # -------------------------------------------------------------------- runs
    def log_run(self, stage: str, stats: Mapping[str, Any], started: str | None = None) -> None:
        from .util import sha1

        stamp = utc_now_iso()
        self.conn.execute(
            "INSERT OR REPLACE INTO runs(run_id, started_at, finished_at, stage, stats)"
            " VALUES (?,?,?,?,?)",
            (
                sha1(f"{stage}|{stamp}")[:16],
                started or stamp,
                stamp,
                stage,
                json.dumps(stats, ensure_ascii=False, default=str),
            ),
        )
        self.conn.commit()
