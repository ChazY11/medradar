"""SQLite storage: one unified ``events`` table plus registry and trading tables.

A single normalized event table keeps the analysis code source-agnostic - a
510(k) clearance, an NDA approval, a trial registration and an NMPA
registration all become rows with ``kind``, ``event_date``, ``company_key``,
``track_id``. That is what makes "谁的哪个方向在升温" a simple group-by.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Mapping

from .util import ensure_dir, iso, iso_moment, utc_now_iso
from .evidence_core.ledger import (
    content_hash,
    latest_revision,
    reconcile,
    revisions_for,
)
from .evidence_core.migrations import ensure_schema

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
    fetched_at TEXT,
    -- Research-grade timing. ``event_date`` is kept for backwards compatibility
    -- and is the date the event happened; these four columns state *when the
    -- information became usable*, which is what a backtest must consume.
    published_at TEXT,          -- when the source made the record public
    first_seen_at TEXT,         -- when MedRadar first ingested it
    available_at TEXT,          -- the timestamp the backtest is allowed to use
    timestamp_quality TEXT DEFAULT 'date'  -- datetime | date | estimated | unknown
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
    available_at TEXT,
    timestamp_quality TEXT DEFAULT 'date',
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

-- Orders that passed every *news-side* check but could not fill yet (market
-- closed, quote missing, quote older than the filing). They are retried on the
-- next cycle instead of being silently dropped.
CREATE TABLE IF NOT EXISTS live_pending (
    alert_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    created_at TEXT,
    attempts INTEGER DEFAULT 0,
    last_attempt_at TEXT,
    last_reason TEXT,
    status TEXT DEFAULT 'pending'
);

-- One row per skipped candidate, with a machine-readable reason. "Every skip
-- has a reason" is a product requirement, not just a debugging aid.
CREATE TABLE IF NOT EXISTS live_skips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    alert_id TEXT,
    ticker TEXT,
    reason TEXT
);

-- LLM judge cache: same filing text never costs tokens twice.
CREATE TABLE IF NOT EXISTS llm_verdicts (
    content_hash TEXT PRIMARY KEY,
    model TEXT,
    verdict TEXT,
    created_at TEXT
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
    "published_at",
    "first_seen_at",
    "available_at",
    "timestamp_quality",
)

TIMESTAMP_QUALITIES = ("datetime", "date", "estimated", "unknown")
TRADING_TIMESTAMP_QUALITIES = ("datetime", "date")


def trading_timestamp_ok(available_at: Any, quality: Any) -> bool:
    """Whether a public timestamp is reliable enough for a return study.

    ``estimated`` remains useful for descriptive industry counts, but it is not
    evidence that the market could have observed the event at that time.
    """
    return bool(iso_moment(available_at)) and str(quality or "unknown").lower() in TRADING_TIMESTAMP_QUALITIES


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
        self._migrate()
        self.conn.commit()
        # Evidence Core v1: schema_version + event_revision + guards + legacy
        # baseline seeding. Idempotent; a migrated database is a cheap no-op.
        self.evidence_core_report = ensure_schema(self.conn)
        self.conn.commit()

    def _migrate(self) -> None:
        """Forward-migrate an existing database without losing data.

        Older databases predate the research-grade timing columns; add them and
        backfill from the best available proxy. ``timestamp_quality='estimated'``
        marks rows whose availability was inferred rather than observed.
        """
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(events)")}
        additions = {
            "published_at": "TEXT",
            "first_seen_at": "TEXT",
            "available_at": "TEXT",
            "timestamp_quality": "TEXT DEFAULT 'date'",
        }
        for column, decl in additions.items():
            if column not in existing:
                self.conn.execute(f"ALTER TABLE events ADD COLUMN {column} {decl}")
        if any(column not in existing for column in additions):
            self.conn.execute(
                "UPDATE events SET"
                " published_at = COALESCE(NULLIF(published_at, ''), event_date),"
                " first_seen_at = COALESCE(NULLIF(first_seen_at, ''), as_of, fetched_at),"
                " available_at = COALESCE(NULLIF(available_at, ''), NULLIF(published_at, ''), event_date),"
                " timestamp_quality = COALESCE(NULLIF(timestamp_quality, ''), 'estimated')"
                " WHERE available_at IS NULL OR available_at = ''"
            )
        signal_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(signals)")}
        for column, decl in {"available_at": "TEXT", "timestamp_quality": "TEXT DEFAULT 'date'"}.items():
            if column not in signal_columns:
                self.conn.execute(f"ALTER TABLE signals ADD COLUMN {column} {decl}")

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

    def meta_set(self, key: str, value: Any, commit: bool = True) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        if commit:
            self.conn.commit()

    @contextmanager
    def transaction(self):
        """Run several writes atomically (fills must never be half-applied).

        SQLite's implicit transaction is not enough here: `meta_set` commits by
        default, so a crash between the cash update and the order insert would
        leave cash debited with no trade record. This context manager uses an
        explicit ``BEGIN IMMEDIATE`` and rolls everything back on exception.
        """
        started = False
        if not self.conn.in_transaction:
            self.conn.execute("BEGIN IMMEDIATE")
            started = True
        try:
            yield self
        except Exception:
            if started:
                self.conn.rollback()
            raise
        else:
            if started:
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
    def _normalise_event(self, event: Mapping[str, Any], stamp: str) -> dict[str, Any]:
        """One ``events`` row, normalised exactly as the pre-ledger write path did.

        Kept as a method (not a free function) so the existing date/quality
        contract in this module remains the single source of truth.
        """
        payload = event.get("payload")
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, ensure_ascii=False)
        event_date = iso(event.get("event_date"))
        as_of = iso(event.get("as_of")) or stamp[:10]
        raw_published_at = str(event.get("published_at") or "")
        raw_available_at = str(event.get("available_at") or "")
        published_at = iso_moment(raw_published_at) or None
        first_seen_at = iso_moment(event.get("first_seen_at")) or stamp
        available_at = iso_moment(raw_available_at) or published_at
        raw_public_time = raw_available_at or raw_published_at
        default_quality = (
            "datetime" if "T" in raw_public_time
            else "date" if available_at
            else "unknown"
        )
        quality = str(event.get("timestamp_quality") or default_quality).lower()
        if quality not in TIMESTAMP_QUALITIES or not available_at:
            quality = "unknown"
        return {
            "event_id": event["event_id"],
            "source": event["source"],
            "kind": event["kind"],
            "event_date": event_date,
            "as_of": as_of,
            "company_key": event.get("company_key"),
            "applicant_raw": event.get("applicant_raw", ""),
            "country": event.get("country", "US"),
            "track_id": event.get("track_id"),
            "product_code": str(event.get("product_code") or "") or None,
            "title": event.get("title", ""),
            "summary": event.get("summary", ""),
            "url": event.get("url", ""),
            "payload": payload or "",
            "fetched_at": event.get("fetched_at") or stamp,
            "published_at": published_at,
            "first_seen_at": first_seen_at,
            "available_at": available_at,
            "timestamp_quality": quality,
        }

    @staticmethod
    def _min_first_seen(left: Any, right: Any) -> str:
        """Lexicographic MIN of two ISO date/datetime strings (never later).

        Mixed precision is safe here because the prefix date is fixed-width:
        ``2024-01-05`` sorts before ``2024-01-05T16:00:00Z``, which is the
        correct "same day, earlier is better" answer.
        """
        first = str(left or "").strip()
        second = str(right or "").strip()
        if not first:
            return second
        if not second:
            return first
        return first if first <= second else second

    @staticmethod
    def _snapshot(values: Mapping[str, Any]) -> dict[str, Any]:
        return {field: values.get(field) for field in EVENT_FIELDS}

    def _insert_event_row(self, values: Mapping[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO events(event_id, source, kind, event_date, as_of,"
            " company_key, applicant_raw, country, track_id, product_code, title,"
            " summary, url, payload, fetched_at, published_at, first_seen_at,"
            " available_at, timestamp_quality)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(values.get(field) for field in EVENT_FIELDS),
        )

    def _write_event_with_revision(self, values: dict[str, Any], stamp: str) -> str:
        """Write the head row and exactly one ledger revision on content change.

        Returns ``"inserted" | "unchanged" | "revised" | "adopted"``.
        Must be called inside a transaction: a failure rolls back both the head
        row and the revision.
        """
        from .evidence_core.ledger import append_revision

        event_id = str(values["event_id"])
        new_hash = content_hash(values)
        existing = self.conn.execute(
            "SELECT first_seen_at FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if existing is None:
            self._insert_event_row(values)
            append_revision(
                self.conn,
                event_id=event_id,
                version=1,
                snapshot=self._snapshot(values),
                revision_reason="insert",
                origin="live",
                history_completeness="complete",
                recorded_at=stamp,
            )
            return "inserted"

        first_seen = self._min_first_seen(existing["first_seen_at"], values["first_seen_at"])
        latest = latest_revision(self.conn, event_id)
        if latest is not None and latest["content_hash"] == new_hash:
            # Idempotent re-import: no new revision. Only the monotonic
            # first_seen_at may move (earlier), and only on the head row; the
            # immutable ledger keeps what it recorded at each revision.
            if first_seen != str(existing["first_seen_at"] or ""):
                self.conn.execute(
                    "UPDATE events SET first_seen_at = ? WHERE event_id = ?",
                    (first_seen, event_id),
                )
            return "unchanged"

        snapshot = self._snapshot(values)
        snapshot["first_seen_at"] = first_seen
        if latest is None:
            # Defensive: an events row somehow predates the ledger (migrations
            # bypassed). Seal it as an adopted row, never as real history.
            append_revision(
                self.conn,
                event_id=event_id,
                version=1,
                snapshot=snapshot,
                revision_reason="adopted_existing_row",
                origin="live",
                history_completeness="partial_before_ledger",
                recorded_at=stamp,
            )
            self._insert_event_row(snapshot)
            return "adopted"

        completeness = (
            "complete"
            if latest["origin"] == "live" and latest["history_completeness"] == "complete"
            else "partial_before_ledger"
        )
        append_revision(
            self.conn,
            event_id=event_id,
            version=int(latest["version"]) + 1,
            snapshot=snapshot,
            revision_reason="update",
            origin="live",
            history_completeness=completeness,
            recorded_at=stamp,
            prev_content_hash=latest["content_hash"],
        )
        self._insert_event_row(snapshot)
        return "revised"

    def upsert_events(self, events: Iterable[Mapping[str, Any]]) -> int:
        """Insert/update events, appending an immutable revision per content change.

        Behaviour contract (Evidence Core v1):

        * first insert → head row + revision v1 (``origin='live'``);
        * identical re-import (same content hash) → **no** new revision and the
          earlier ``first_seen_at`` is preserved (MIN, never later);
        * changed re-import → head row updated, revision vN appended with the
          old values already in the ledger. The batch is one transaction.

        Read behaviour is unchanged: every existing query still reads ``events``.
        """
        stamp = utc_now_iso()
        # Normalise before opening the transaction: an invalid row must fail
        # fast without writing anything.
        rows = [self._normalise_event(event, stamp) for event in events]
        if not rows:
            return 0
        with self.transaction():
            for values in rows:
                self._write_event_with_revision(values, stamp)
        return len(rows)

    # --------------------------------------------------------- evidence ledger
    def event_history(self, event_id: str) -> list[dict[str, Any]]:
        """Every recorded revision for one event, oldest first."""
        return revisions_for(self.conn, event_id)

    def event_revision_count(self, event_id: str | None = None) -> int:
        if event_id is None:
            return int(self.scalar("SELECT COUNT(*) FROM event_revision", default=0) or 0)
        return int(
            self.scalar(
                "SELECT COUNT(*) FROM event_revision WHERE event_id = ?",
                (event_id,),
                default=0,
            )
            or 0
        )

    def reconcile_ledger(self) -> dict[str, Any]:
        """Detect head rows that no longer match their latest revision.

        Catches direct SQL / ``INSERT OR REPLACE`` on ``events`` and missing
        revisions. Does not catch dropped triggers or whole-file replacement
        (see the bypass matrix in the Phase 2 document).
        """
        return reconcile(self.conn)

    def ensure_evidence_core(self) -> dict[str, Any]:
        """Re-run the idempotent migration runner (e.g. after restoring a file)."""
        report = ensure_schema(self.conn)
        self.conn.commit()
        self.evidence_core_report = report
        return report

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
                iso(signal.get("available_at")),
                str(signal.get("timestamp_quality") or "date").lower(),
                stamp,
            )
            for signal in signals
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO signals(signal_id, event_id, company_key, ticker,"
            " signal_date, kind, direction, score, track_id, reason_zh, available_at,"
            " timestamp_quality, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
