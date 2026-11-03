"""Append-only Observation Ledger.

What this module guarantees, in SQLite rather than in a README:

* ``first_seen_at`` is written once and can never be updated (trigger).
* Payload history is append-only; a version row can never be rewritten or
  deleted (triggers), so "what did we store at time T" is always answerable.
* Re-collecting an identical payload creates no version and no change row — the
  same batch can be replayed forever without inflating the record.
* Removed/unavailable and failed-fetch events are recorded as their own states,
  never inferred from absence.
* Mapping decisions are their own append-only history: a better entity mapping
  changes attribution, not the source evidence.

The ledger lives in its own SQLite file (``data/observatory/observatory.sqlite``
by default). The legacy 1.37 GB research database is never written here.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from ..config import DATA_DIR
from .records import (
    CHANGE_FETCH_FAILED,
    CHANGE_NEW,
    CHANGE_REMOVED,
    CHANGE_UNCHANGED,
    CHANGE_UPDATED,
    ENTITY_MAPPED,
    ENTITY_PENDING_REVIEW,
    ENTITY_UNMAPPED,
    ORIGIN_BACKFILLED,
    ORIGIN_LIVE,
    PRECISION_UNKNOWN,
    RUN_FAILED,
    RUN_INTERRUPTED,
    RUN_OK,
    RUN_PARTIAL,
    RUN_RUNNING,
    SCHEMA_VERSION,
    SOURCE_STATUS_DEGRADED,
    SOURCE_STATUS_FAILED,
    SOURCE_STATUS_NEVER_RUN,
    SOURCE_STATUS_OK,
    STATUS_ACTIVE,
    STATUS_REMOVED,
    MappingResult,
    RawRecord,
    RecordOutcome,
    canonical_json,
    changed_fields,
    observation_id as make_observation_id,
    payload_hash,
    utc_now,
    utc_now_iso,
    version_id as make_version_id,
)

DEFAULT_LEDGER_RELATIVE = Path("observatory") / "observatory.sqlite"


def default_ledger_path() -> Path:
    override = os.environ.get("MEDRADAR_OBSERVATORY_DB")
    if override:
        return Path(override).expanduser()
    return Path(DATA_DIR) / DEFAULT_LEDGER_RELATIVE


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS observation (
    observation_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    observation_origin TEXT NOT NULL,
    backfill_reason TEXT,
    event_at TEXT,
    event_at_precision TEXT NOT NULL DEFAULT 'unknown',
    published_at TEXT,
    published_at_precision TEXT NOT NULL DEFAULT 'unknown',
    source_updated_at TEXT,
    source_updated_at_precision TEXT NOT NULL DEFAULT 'unknown',
    last_checked_at TEXT NOT NULL,
    source_payload_hash TEXT NOT NULL,
    latest_version_id TEXT,
    version_count INTEGER NOT NULL DEFAULT 1,
    observation_status TEXT NOT NULL,
    current_change_state TEXT NOT NULL,
    last_change_at TEXT NOT NULL,
    first_seen_run_id TEXT NOT NULL,
    last_checked_run_id TEXT NOT NULL,
    title TEXT,
    original_url TEXT,
    UNIQUE(source, source_record_id)
);

CREATE TABLE IF NOT EXISTS observation_version (
    version_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL,
    version_seq INTEGER NOT NULL,
    captured_at TEXT NOT NULL,
    change_state TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload TEXT NOT NULL,
    payload_bytes INTEGER NOT NULL,
    changed_fields TEXT,
    source_updated_at TEXT,
    run_id TEXT NOT NULL,
    collector_version TEXT NOT NULL,
    UNIQUE(observation_id, version_seq),
    UNIQUE(observation_id, payload_hash)
);

CREATE TABLE IF NOT EXISTS observation_change (
    change_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL,
    source TEXT NOT NULL,
    change_state TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    version_id TEXT,
    previous_version_id TEXT,
    changed_fields TEXT,
    first_seen_at TEXT NOT NULL,
    event_at TEXT,
    event_at_precision TEXT NOT NULL DEFAULT 'unknown',
    published_at TEXT,
    published_at_precision TEXT NOT NULL DEFAULT 'unknown',
    record_type TEXT NOT NULL,
    title TEXT,
    url TEXT,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_status_history (
    observation_id TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    run_id TEXT NOT NULL,
    note TEXT,
    PRIMARY KEY (observation_id, changed_at)
);

CREATE TABLE IF NOT EXISTS observation_mapping (
    observation_id TEXT NOT NULL,
    mapped_at TEXT NOT NULL,
    mapping_version TEXT NOT NULL,
    entity_id TEXT,
    entity_status TEXT NOT NULL,
    entity_method TEXT,
    entity_confidence REAL,
    track_id TEXT,
    track_status TEXT NOT NULL,
    track_method TEXT,
    note_zh TEXT,
    PRIMARY KEY (observation_id, mapped_at)
);

CREATE TABLE IF NOT EXISTS source_state (
    source TEXT PRIMARY KEY,
    label_zh TEXT,
    adapter_version TEXT,
    declared_cadence_zh TEXT,
    status TEXT NOT NULL,
    last_attempt_at TEXT,
    last_success_at TEXT,
    last_failure_at TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    watermark TEXT,
    watermark_updated_at TEXT,
    last_run_id TEXT,
    last_status_message TEXT,
    last_outcome TEXT,
    last_new_records INTEGER,
    last_updated_records INTEGER,
    last_finished_at TEXT,
    structure_signature TEXT,
    structure_changed_at TEXT,
    structure_note_zh TEXT,
    entity_coverage TEXT
);

CREATE TABLE IF NOT EXISTS sync_run (
    run_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    trigger TEXT NOT NULL,
    host TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    collector_version TEXT,
    requests INTEGER NOT NULL DEFAULT 0,
    pages INTEGER NOT NULL DEFAULT 0,
    records_seen INTEGER NOT NULL DEFAULT 0,
    records_new INTEGER NOT NULL DEFAULT 0,
    records_updated INTEGER NOT NULL DEFAULT 0,
    records_unchanged INTEGER NOT NULL DEFAULT 0,
    records_removed INTEGER NOT NULL DEFAULT 0,
    records_failed INTEGER NOT NULL DEFAULT 0,
    watermark_before TEXT,
    watermark_after TEXT,
    error_detail TEXT,
    notes_zh TEXT
);

CREATE TABLE IF NOT EXISTS sync_checkpoint (
    source TEXT NOT NULL,
    run_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    cursor TEXT,
    records_seen INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (source, run_id, scope)
);

CREATE TABLE IF NOT EXISTS source_failure (
    failure_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    run_id TEXT,
    occurred_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    url TEXT,
    http_status INTEGER,
    message TEXT,
    retryable INTEGER,
    attempt INTEGER
);

CREATE TABLE IF NOT EXISTS runtime_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);

-- Acquisition phase history: append-only metadata, never a rewrite of the ledger.
CREATE TABLE IF NOT EXISTS observation_phase (
    observation_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    run_id TEXT,
    method TEXT NOT NULL,
    note_zh TEXT,
    PRIMARY KEY (observation_id, assigned_at)
);

-- Operational metrics (storage growth, daily snapshots). Not research evidence.
CREATE TABLE IF NOT EXISTS ops_metric (
    metric TEXT NOT NULL,
    day TEXT NOT NULL,
    value TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (metric, day)
);

CREATE INDEX IF NOT EXISTS ix_obs_source ON observation(source);
CREATE INDEX IF NOT EXISTS ix_obs_first_seen ON observation(first_seen_at);
CREATE INDEX IF NOT EXISTS ix_change_observed ON observation_change(observed_at);
CREATE INDEX IF NOT EXISTS ix_change_state ON observation_change(change_state);
CREATE INDEX IF NOT EXISTS ix_change_source ON observation_change(source);
CREATE INDEX IF NOT EXISTS ix_version_obs ON observation_version(observation_id);
CREATE INDEX IF NOT EXISTS ix_mapping_obs ON observation_mapping(observation_id);
CREATE INDEX IF NOT EXISTS ix_status_obs ON observation_status_history(observation_id);
CREATE INDEX IF NOT EXISTS ix_run_source ON sync_run(source, started_at);
CREATE INDEX IF NOT EXISTS ix_phase_obs ON observation_phase(observation_id);
CREATE INDEX IF NOT EXISTS ix_phase_phase ON observation_phase(phase);

-- 1. first_seen_at is immutable ------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_observation_first_seen_immutable
BEFORE UPDATE OF first_seen_at ON observation
WHEN OLD.first_seen_at IS NOT NEW.first_seen_at
BEGIN
    SELECT RAISE(ABORT, 'first_seen_at is immutable: it records the real first observation');
END;

CREATE TRIGGER IF NOT EXISTS trg_observation_identity_immutable
BEFORE UPDATE OF observation_id, source, source_record_id, observation_origin ON observation
WHEN OLD.observation_id IS NOT NEW.observation_id
  OR OLD.source IS NOT NEW.source
  OR OLD.source_record_id IS NOT NEW.source_record_id
  OR OLD.observation_origin IS NOT NEW.observation_origin
BEGIN
    SELECT RAISE(ABORT, 'observation identity/origin is immutable');
END;

-- 2. payload history is append-only -------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_version_no_update
BEFORE UPDATE ON observation_version
BEGIN
    SELECT RAISE(ABORT, 'observation_version is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_version_no_delete
BEFORE DELETE ON observation_version
BEGIN
    SELECT RAISE(ABORT, 'observation_version is append-only');
END;

-- 3. change / status / mapping / failure logs are append-only ------------------
CREATE TRIGGER IF NOT EXISTS trg_change_no_update
BEFORE UPDATE ON observation_change
BEGIN SELECT RAISE(ABORT, 'observation_change is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_change_no_delete
BEFORE DELETE ON observation_change
BEGIN SELECT RAISE(ABORT, 'observation_change is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_status_no_update
BEFORE UPDATE ON observation_status_history
BEGIN SELECT RAISE(ABORT, 'observation_status_history is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_status_no_delete
BEFORE DELETE ON observation_status_history
BEGIN SELECT RAISE(ABORT, 'observation_status_history is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_mapping_no_update
BEFORE UPDATE ON observation_mapping
BEGIN SELECT RAISE(ABORT, 'observation_mapping is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_mapping_no_delete
BEFORE DELETE ON observation_mapping
BEGIN SELECT RAISE(ABORT, 'observation_mapping is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_phase_no_update
BEFORE UPDATE ON observation_phase
BEGIN SELECT RAISE(ABORT, 'observation_phase is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_phase_no_delete
BEFORE DELETE ON observation_phase
BEGIN SELECT RAISE(ABORT, 'observation_phase is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_failure_no_update
BEFORE UPDATE ON source_failure
BEGIN SELECT RAISE(ABORT, 'source_failure is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_failure_no_delete
BEFORE DELETE ON source_failure
BEGIN SELECT RAISE(ABORT, 'source_failure is append-only'); END;

-- 4. no observation may disappear; history is not deletable --------------------
CREATE TRIGGER IF NOT EXISTS trg_observation_no_delete
BEFORE DELETE ON observation
BEGIN SELECT RAISE(ABORT, 'observations are never deleted; mark them removed instead'); END;

-- 5. a run may only be finalised once, and its identity never changes ----------
CREATE TRIGGER IF NOT EXISTS trg_run_identity_immutable
BEFORE UPDATE OF run_id, source, trigger, started_at ON sync_run
WHEN OLD.run_id IS NOT NEW.run_id
  OR OLD.source IS NOT NEW.source
  OR OLD.trigger IS NOT NEW.trigger
  OR OLD.started_at IS NOT NEW.started_at
BEGIN SELECT RAISE(ABORT, 'sync_run identity is immutable'); END;

CREATE TRIGGER IF NOT EXISTS trg_run_no_delete
BEFORE DELETE ON sync_run
BEGIN SELECT RAISE(ABORT, 'sync_run is append-only'); END;
"""


class LedgerLocked(RuntimeError):
    """A second writer tried to use the ledger while another run holds it."""


def _hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:  # pragma: no cover - exotic environment
        return "unknown"


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return canonical_json(value)


def _canonical_moment(value: str | None) -> str | None:
    """Store instants in one lexicographically comparable form (``+00:00``).

    The ledger historically received ``…Z`` values from one code path and
    ``…+00:00`` from another; both are valid ISO-8601 UTC, but SQLite compares
    text lexicographically and ``Z`` sorts after ``+``. Normalising on write and
    comparing through ``_norm_expr`` keeps "same instant" equal regardless of the
    original spelling (the immutable rows are never rewritten).
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        return text[:-1] + "+00:00"
    return text


def _norm_expr(expression: str) -> str:
    """SQL expression: normalise a stored timestamp for text comparison."""
    return f"replace({expression}, 'Z', '+00:00')"


class ObservationLedger:
    """SQLite-backed, append-only observation store."""

    def __init__(self, path: str | Path | None = None, *, create: bool = True,
                 read_only: bool = False) -> None:
        self.path = Path(path) if path is not None else default_ledger_path()
        self.path = self.path.expanduser()
        self._lock = threading.RLock()
        self._con: sqlite3.Connection | None = None
        self.created_schema = False
        self.read_only = bool(read_only)
        if self.read_only:
            if not self.path.exists():
                raise FileNotFoundError(f"observation ledger not found: {self.path}")
            self._connect(read_only=True)
            return
        if not create and not self.path.exists():
            raise FileNotFoundError(f"observation ledger not found: {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connect()
        self._ensure_schema()

    # ------------------------------------------------------------------ plumbing
    def _connect(self, read_only: bool = False) -> None:
        if read_only:
            uri = f"file:{self.path.as_posix()}?mode=ro"
            con = sqlite3.connect(uri, timeout=45.0, isolation_level=None, uri=True)
            con.execute("PRAGMA query_only=ON")
            con.execute("PRAGMA busy_timeout=45000")
        else:
            con = sqlite3.connect(str(self.path), timeout=45.0, isolation_level=None)
            con.execute("PRAGMA journal_mode=WAL")
            # FULL, not NORMAL: a research observation that survives a power cut is
            # the entire point of this subsystem.
            con.execute("PRAGMA synchronous=FULL")
            con.execute("PRAGMA foreign_keys=OFF")
            con.execute("PRAGMA busy_timeout=45000")
        con.row_factory = sqlite3.Row
        self._con = con

    @property
    def con(self) -> sqlite3.Connection:
        if self._con is None:
            self._connect(read_only=getattr(self, "read_only", False))
            assert self._con is not None
        return self._con

    def _ensure_schema(self) -> None:
        self.con.executescript(SCHEMA)
        self._migrate()
        self.created_schema = self._meta("schema_version") is None
        self._set_meta("schema_version", SCHEMA_VERSION)
        self._set_meta("created_at", self._meta("created_at") or utc_now_iso())
        self._set_meta("path", str(self.path))

    #: Columns added after the first release. They are operational state (not
    #: research evidence), so an additive migration is safe and honest.
    _SOURCE_STATE_COLUMNS = {
        "last_outcome": "TEXT",
        "last_new_records": "INTEGER",
        "last_updated_records": "INTEGER",
        "last_finished_at": "TEXT",
    }

    def _migrate(self) -> None:
        if getattr(self, "read_only", False):
            return
        existing = {
            row["name"]
            for row in self.con.execute("PRAGMA table_info(source_state)").fetchall()
        }
        for column, sql_type in self._SOURCE_STATE_COLUMNS.items():
            if column not in existing:
                self.con.execute(f"ALTER TABLE source_state ADD COLUMN {column} {sql_type}")
        self.con.execute(
            "INSERT INTO meta(key, value) VALUES('schema_epoch', '2026-11-reliability')"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        self.con.commit()

    def close(self) -> None:
        if self._con is not None:
            try:
                self._con.commit()
            finally:
                self._con.close()
                self._con = None

    def __enter__(self) -> "ObservationLedger":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def size_bytes(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def _meta(self, key: str) -> str | None:
        row = self.con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self.con.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def _exec(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.con.execute(sql, params)

    # ----------------------------------------------------------------- run control
    def recover_interrupted_runs(self) -> int:
        """A RUNNING row with no live process means the process died mid-run.

        Marking those INTENTIONALLY (not FAILED) is what lets the next run resume
        from its checkpoint instead of pretending the interrupted pages were
        "no change".
        """
        now = utc_now_iso()
        rows = self.con.execute(
            "SELECT run_id, source, started_at FROM sync_run WHERE status=?", (RUN_RUNNING,)
        ).fetchall()
        count = 0
        for row in rows:
            self.con.execute(
                "UPDATE sync_run SET status=?, finished_at=?, error_detail=? WHERE run_id=?",
                (
                    RUN_INTERRUPTED,
                    now,
                    "process ended before the run finished; resumable from sync_checkpoint",
                    row["run_id"],
                ),
            )
            count += 1
        if count:
            self.con.commit()
        return count

    def start_run(self, source: str, *, trigger: str = "manual", collector_version: str | None = None,
                  run_id: str | None = None, host: str | None = None) -> str:
        run_id = run_id or f"{source}-{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{os.urandom(3).hex()}"
        started = _canonical_moment(utc_now_iso())
        state = self.get_source_state(source)
        watermark_before = state.get("watermark") if state else None
        self.con.execute(
            "INSERT INTO sync_run(run_id, source, trigger, host, started_at, status, collector_version, watermark_before)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (
                run_id,
                source,
                trigger,
                host or _hostname(),
                started,
                RUN_RUNNING,
                collector_version or "",
                watermark_before,
            ),
        )
        self.con.execute(
            "UPDATE source_state SET last_attempt_at=?, last_run_id=? WHERE source=?",
            (started, run_id, source),
        )
        self.con.commit()
        return run_id

    def finish_run(self, run_id: str, *, status: str, counters: Mapping[str, int] | None = None,
                   error_detail: str | None = None, watermark_after: str | None = None,
                   notes_zh: str | None = None) -> None:
        counters = counters or {}
        self.con.execute(
            "UPDATE sync_run SET status=?, finished_at=?, requests=?, pages=?, records_seen=?,"
            " records_new=?, records_updated=?, records_unchanged=?, records_removed=?,"
            " records_failed=?, watermark_after=?, error_detail=?, notes_zh=? WHERE run_id=?",
            (
                status,
                utc_now_iso(),
                int(counters.get("requests", 0)),
                int(counters.get("pages", 0)),
                int(counters.get("records_seen", 0)),
                int(counters.get("records_new", 0)),
                int(counters.get("records_updated", 0)),
                int(counters.get("records_unchanged", 0)),
                int(counters.get("records_removed", 0)),
                int(counters.get("records_failed", 0)),
                watermark_after,
                error_detail,
                notes_zh,
                run_id,
            ),
        )
        self.con.commit()

    def run_row(self, run_id: str) -> dict[str, Any] | None:
        row = self.con.execute("SELECT * FROM sync_run WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def last_resumable_run(self, source: str) -> dict[str, Any] | None:
        row = self.con.execute(
            "SELECT * FROM sync_run WHERE source=? AND status IN (?,?,?,?)"
            " ORDER BY started_at DESC LIMIT 1",
            (source, RUN_RUNNING, RUN_INTERRUPTED, RUN_PARTIAL, RUN_FAILED),
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------- checkpoints
    def save_checkpoint(self, source: str, run_id: str, scope: str, cursor: str | None,
                        records_seen: int = 0) -> None:
        self.con.execute(
            "INSERT INTO sync_checkpoint(source, run_id, scope, cursor, records_seen, updated_at)"
            " VALUES(?,?,?,?,?,?)"
            " ON CONFLICT(source, run_id, scope) DO UPDATE SET cursor=excluded.cursor,"
            " records_seen=excluded.records_seen, updated_at=excluded.updated_at",
            (source, run_id, scope, cursor, int(records_seen), utc_now_iso()),
        )
        self.con.commit()

    def load_checkpoints(self, source: str, run_id: str) -> dict[str, str | None]:
        rows = self.con.execute(
            "SELECT scope, cursor FROM sync_checkpoint WHERE source=? AND run_id=?", (source, run_id)
        ).fetchall()
        return {row["scope"]: row["cursor"] for row in rows}

    # -------------------------------------------------------------- source state
    def ensure_source(self, source: str, *, label_zh: str, adapter_version: str,
                      declared_cadence_zh: str) -> None:
        self.con.execute(
            "INSERT INTO source_state(source, label_zh, adapter_version, declared_cadence_zh, status)"
            " VALUES(?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET"
            " label_zh=excluded.label_zh, adapter_version=excluded.adapter_version,"
            " declared_cadence_zh=excluded.declared_cadence_zh",
            (source, label_zh, adapter_version, declared_cadence_zh, SOURCE_STATUS_NEVER_RUN),
        )
        self.con.commit()

    def get_source_state(self, source: str) -> dict[str, Any] | None:
        row = self.con.execute("SELECT * FROM source_state WHERE source=?", (source,)).fetchone()
        return dict(row) if row else None

    def note_source_success(self, source: str, *, run_id: str, status: str = SOURCE_STATUS_OK,
                            message: str | None = None) -> None:
        now = utc_now_iso()
        self.con.execute(
            "UPDATE source_state SET status=?, last_success_at=?, last_run_id=?,"
            " consecutive_failures=0, last_status_message=? WHERE source=?",
            (status, now, run_id, message, source),
        )
        self.con.commit()

    def note_source_finish_without_requests(self, source: str, *, run_id: str,
                                            message: str) -> None:
        """Close out a resumed run that made no requests without faking freshness.

        ``last_success_at`` means "the source was actually contacted successfully".
        Finishing an interrupted run from its checkpoints is useful bookkeeping, but
        it must not be presented as a new successful sync.
        """
        self.con.execute(
            "UPDATE source_state SET last_run_id=?, last_status_message=? WHERE source=?",
            (run_id, message, source),
        )
        self.con.commit()

    def note_source_failure(self, source: str, *, run_id: str, message: str,
                            degraded: bool = False) -> None:
        state = self.get_source_state(source) or {}
        failures = int(state.get("consecutive_failures") or 0) + 1
        now = utc_now_iso()
        status = SOURCE_STATUS_DEGRADED if degraded else SOURCE_STATUS_FAILED
        self.con.execute(
            "UPDATE source_state SET status=?, last_failure_at=?, last_run_id=?,"
            " consecutive_failures=?, last_status_message=? WHERE source=?",
            (status, now, run_id, failures, message, source),
        )
        self.con.commit()

    def set_watermark(self, source: str, watermark: Any) -> None:
        self.con.execute(
            "UPDATE source_state SET watermark=?, watermark_updated_at=? WHERE source=?",
            (_json(watermark), utc_now_iso(), source),
        )
        self.con.commit()

    def set_structure(self, source: str, signature: str, changed: bool, note_zh: str | None) -> None:
        state = self.get_source_state(source) or {}
        previous = state.get("structure_signature")
        if changed and previous and previous != signature:
            self.con.execute(
                "UPDATE source_state SET structure_signature=?, structure_changed_at=?,"
                " structure_note_zh=? WHERE source=?",
                (signature, utc_now_iso(), note_zh, source),
            )
        else:
            self.con.execute(
                "UPDATE source_state SET structure_signature=? WHERE source=?", (signature, source)
            )
        self.con.commit()

    def set_entity_coverage(self, source: str, coverage: Any) -> None:
        self.con.execute(
            "UPDATE source_state SET entity_coverage=? WHERE source=?", (_json(coverage), source)
        )
        self.con.commit()

    # ---------------------------------------------------------------- failures
    def record_failure(self, source: str, *, kind: str, message: str, run_id: str | None = None,
                       url: str | None = None, http_status: int | None = None,
                       retryable: bool = True, attempt: int | None = None) -> str:
        import hashlib

        occurred = utc_now_iso()
        raw = f"{source}|{run_id}|{occurred}|{kind}|{url}|{message[:120]}"
        failure_id = hashlib.sha1(raw.encode("utf-8")).hexdigest()
        self.con.execute(
            "INSERT OR IGNORE INTO source_failure(failure_id, source, run_id, occurred_at, kind,"
            " url, http_status, message, retryable, attempt) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (failure_id, source, run_id, occurred, kind, url, http_status, message[:800],
             int(bool(retryable)), attempt),
        )
        self.con.commit()
        return failure_id

    # ------------------------------------------------------- record observations
    def record_observation(
        self,
        record: RawRecord,
        mapping: MappingResult,
        *,
        run_id: str,
        collector_version: str,
        mapping_version: str,
        seen_at: str | None = None,
        origin: str = ORIGIN_LIVE,
        backfill_reason: str | None = None,
    ) -> RecordOutcome:
        """Insert or reconcile one observation. Idempotent by construction."""
        if origin not in (ORIGIN_LIVE, ORIGIN_BACKFILLED):
            raise ValueError(f"bad observation origin: {origin}")
        if origin == ORIGIN_BACKFILLED and not backfill_reason:
            raise ValueError("BACKFILLED observations require a reason; do not fake first_seen_at")
        seen_at = _canonical_moment(seen_at or utc_now_iso())
        obs_id = make_observation_id(record.source, record.source_record_id)
        digest = payload_hash(record.payload)
        payload_text = canonical_json(record.payload)
        existing = self.con.execute(
            "SELECT * FROM observation WHERE observation_id=?", (obs_id,)
        ).fetchone()

        if existing is None:
            version = make_version_id(obs_id, digest)
            with self._transaction():
                self.con.execute(
                    "INSERT INTO observation(observation_id, source, source_record_id, record_type,"
                    " first_seen_at, ingested_at, observation_origin, backfill_reason, event_at,"
                    " event_at_precision, published_at, published_at_precision, source_updated_at,"
                    " source_updated_at_precision, last_checked_at, source_payload_hash,"
                    " latest_version_id, version_count, observation_status, current_change_state,"
                    " last_change_at, first_seen_run_id, last_checked_run_id, title, original_url)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        obs_id, record.source, record.source_record_id, record.record_type,
                        seen_at, seen_at, origin, backfill_reason, record.event_at,
                        record.event_at_precision, record.published_at,
                        record.published_at_precision, record.source_updated_at,
                        record.source_updated_at_precision, seen_at, digest, version, 1,
                        STATUS_ACTIVE, CHANGE_NEW, seen_at, run_id, run_id, record.title,
                        record.url,
                    ),
                )
                self.con.execute(
                    "INSERT INTO observation_version(version_id, observation_id, version_seq,"
                    " captured_at, change_state, payload_hash, payload, payload_bytes,"
                    " changed_fields, source_updated_at, run_id, collector_version)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (version, obs_id, 1, seen_at, CHANGE_NEW, digest, payload_text,
                     len(payload_text.encode("utf-8")), None, record.source_updated_at,
                     run_id, collector_version),
                )
                self.con.execute(
                    "INSERT INTO observation_status_history(observation_id, changed_at, status,"
                    " run_id, note) VALUES(?,?,?,?,?)",
                    (obs_id, seen_at, STATUS_ACTIVE, run_id, "first observation"),
                )
                self._insert_change(
                    obs_id=obs_id, source=record.source, change_state=CHANGE_NEW,
                    observed_at=seen_at, version=version, previous_version=None,
                    changed=None, first_seen_at=seen_at, record=record, run_id=run_id,
                )
                self._write_mapping(obs_id, mapping, mapping_version, seen_at)
            return RecordOutcome(obs_id, CHANGE_NEW, version, None, (), seen_at)

        # ----- existing observation: unchanged / updated / restored
        previous_payload = self._latest_payload(obs_id)
        previous_version = existing["latest_version_id"]
        was_removed = existing["observation_status"] == STATUS_REMOVED
        if existing["source_payload_hash"] == digest and not was_removed:
            with self._transaction():
                self.con.execute(
                    "UPDATE observation SET last_checked_at=?, last_checked_run_id=?"
                    " WHERE observation_id=?",
                    (seen_at, run_id, obs_id),
                )
                self._write_mapping(obs_id, mapping, mapping_version, seen_at)
            return RecordOutcome(
                obs_id, CHANGE_UNCHANGED, previous_version, previous_version, (),
                existing["first_seen_at"],
            )

        fields = changed_fields(previous_payload, dict(record.payload))
        if was_removed and not fields:
            # The record re-appeared with byte-identical content: that is a status
            # restoration, not a new payload version. Reusing the version keeps the
            # append-only payload chain honest (and the UNIQUE hash constraint).
            with self._transaction():
                self.con.execute(
                    "UPDATE observation SET observation_status=?, current_change_state=?,"
                    " last_change_at=?, last_checked_at=?, last_checked_run_id=?, title=?,"
                    " original_url=? WHERE observation_id=?",
                    (STATUS_ACTIVE, CHANGE_UPDATED, seen_at, seen_at, run_id, record.title,
                     record.url, obs_id),
                )
                self.con.execute(
                    "INSERT INTO observation_status_history(observation_id, changed_at, status,"
                    " run_id, note) VALUES(?,?,?,?,?)",
                    (obs_id, seen_at, STATUS_ACTIVE, run_id, "record re-appeared at source"),
                )
                self._insert_change(
                    obs_id=obs_id, source=record.source, change_state=CHANGE_UPDATED,
                    observed_at=seen_at, version=previous_version,
                    previous_version=previous_version, changed=["status"],
                    first_seen_at=existing["first_seen_at"], record=record, run_id=run_id,
                )
                self._write_mapping(obs_id, mapping, mapping_version, seen_at)
            return RecordOutcome(
                obs_id, CHANGE_UPDATED, previous_version, previous_version, ("status",),
                existing["first_seen_at"],
            )

        fields = fields or (["status"] if was_removed else [])
        version = make_version_id(obs_id, digest)
        seq = int(existing["version_count"]) + 1
        with self._transaction():
            self.con.execute(
                "INSERT INTO observation_version(version_id, observation_id, version_seq,"
                " captured_at, change_state, payload_hash, payload, payload_bytes,"
                " changed_fields, source_updated_at, run_id, collector_version)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (version, obs_id, seq, seen_at, CHANGE_UPDATED, digest, payload_text,
                 len(payload_text.encode("utf-8")), _json(fields),
                 record.source_updated_at, run_id, collector_version),
            )
            self.con.execute(
                "UPDATE observation SET source_payload_hash=?, latest_version_id=?,"
                " version_count=?, observation_status=?, current_change_state=?,"
                " last_change_at=?, last_checked_at=?, last_checked_run_id=?,"
                " event_at=?, event_at_precision=?, published_at=?, published_at_precision=?,"
                " source_updated_at=?, source_updated_at_precision=?, title=?, original_url=?"
                " WHERE observation_id=?",
                (
                    digest, version, seq, STATUS_ACTIVE, CHANGE_UPDATED, seen_at, seen_at,
                    run_id, record.event_at, record.event_at_precision, record.published_at,
                    record.published_at_precision, record.source_updated_at,
                    record.source_updated_at_precision, record.title, record.url, obs_id,
                ),
            )
            if was_removed:
                self.con.execute(
                    "INSERT INTO observation_status_history(observation_id, changed_at, status,"
                    " run_id, note) VALUES(?,?,?,?,?)",
                    (obs_id, seen_at, STATUS_ACTIVE, run_id, "record re-appeared at source"),
                )
            self._insert_change(
                obs_id=obs_id, source=record.source, change_state=CHANGE_UPDATED,
                observed_at=seen_at, version=version, previous_version=previous_version,
                changed=fields, first_seen_at=existing["first_seen_at"], record=record,
                run_id=run_id,
            )
            self._write_mapping(obs_id, mapping, mapping_version, seen_at)
        return RecordOutcome(
            obs_id, CHANGE_UPDATED, version, previous_version, tuple(fields),
            existing["first_seen_at"],
        )

    def mark_removed(self, obs_id: str, *, run_id: str, note_zh: str,
                     seen_at: str | None = None) -> bool:
        """Record that the source no longer serves this record (not that it vanished)."""
        seen_at = _canonical_moment(seen_at or utc_now_iso())
        row = self.con.execute(
            "SELECT * FROM observation WHERE observation_id=?", (obs_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown observation: {obs_id}")
        if row["observation_status"] == STATUS_REMOVED:
            with self._transaction():
                self.con.execute(
                    "UPDATE observation SET last_checked_at=?, last_checked_run_id=?"
                    " WHERE observation_id=?",
                    (seen_at, run_id, obs_id),
                )
            return False
        with self._transaction():
            self.con.execute(
                "UPDATE observation SET observation_status=?, current_change_state=?,"
                " last_change_at=?, last_checked_at=?, last_checked_run_id=?"
                " WHERE observation_id=?",
                (STATUS_REMOVED, CHANGE_REMOVED, seen_at, seen_at, run_id, obs_id),
            )
            self.con.execute(
                "INSERT INTO observation_status_history(observation_id, changed_at, status,"
                " run_id, note) VALUES(?,?,?,?,?)",
                (obs_id, seen_at, STATUS_REMOVED, run_id, note_zh),
            )
            self.con.execute(
                "INSERT INTO observation_change(change_id, observation_id, source, change_state,"
                " observed_at, version_id, previous_version_id, changed_fields, first_seen_at,"
                " event_at, event_at_precision, published_at, published_at_precision, record_type,"
                " title, url, run_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    _change_id(obs_id, CHANGE_REMOVED, None, seen_at), obs_id, row["source"],
                    CHANGE_REMOVED, seen_at, None, row["latest_version_id"], _json(["status"]),
                    row["first_seen_at"], row["event_at"], row["event_at_precision"],
                    row["published_at"], row["published_at_precision"], row["record_type"],
                    row["title"], row["original_url"], run_id,
                ),
            )
        return True

    def mark_fetch_failed(self, obs_id: str, *, run_id: str, message: str,
                          seen_at: str | None = None) -> None:
        """A failed re-check is not evidence of no change; it is its own state."""
        seen_at = _canonical_moment(seen_at or utc_now_iso())
        row = self.con.execute(
            "SELECT * FROM observation WHERE observation_id=?", (obs_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown observation: {obs_id}")
        with self._transaction():
            self.con.execute(
                "INSERT INTO observation_change(change_id, observation_id, source, change_state,"
                " observed_at, version_id, previous_version_id, changed_fields, first_seen_at,"
                " event_at, event_at_precision, published_at, published_at_precision, record_type,"
                " title, url, run_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    _change_id(obs_id, CHANGE_FETCH_FAILED, None, seen_at), obs_id,
                    row["source"], CHANGE_FETCH_FAILED, seen_at, None,
                    row["latest_version_id"], None, row["first_seen_at"], row["event_at"],
                    row["event_at_precision"], row["published_at"],
                    row["published_at_precision"], row["record_type"], row["title"],
                    row["original_url"], run_id,
                ),
            )

    def touch_checked(self, obs_id: str, *, run_id: str, checked_at: str | None = None) -> None:
        checked_at = _canonical_moment(checked_at or utc_now_iso())
        self.con.execute(
            "UPDATE observation SET last_checked_at=?, last_checked_run_id=? WHERE observation_id=?",
            (checked_at, run_id, obs_id),
        )

    # ------------------------------------------------------------------ internals
    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            self.con.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.con.commit()
            except Exception:
                self.con.rollback()
                raise

    def _latest_payload(self, obs_id: str) -> dict[str, Any] | None:
        row = self.con.execute(
            "SELECT payload FROM observation_version WHERE observation_id=?"
            " ORDER BY version_seq DESC LIMIT 1",
            (obs_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["payload"])
        except (TypeError, ValueError):  # pragma: no cover - corrupted row
            return None

    def _insert_change(self, *, obs_id: str, source: str, change_state: str, observed_at: str,
                       version: str | None, previous_version: str | None,
                       changed: Sequence[str] | None, first_seen_at: str, record: RawRecord,
                       run_id: str) -> None:
        self.con.execute(
            "INSERT INTO observation_change(change_id, observation_id, source, change_state,"
            " observed_at, version_id, previous_version_id, changed_fields, first_seen_at,"
            " event_at, event_at_precision, published_at, published_at_precision, record_type,"
            " title, url, run_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                _change_id(obs_id, change_state, version, observed_at), obs_id, source,
                change_state, observed_at, version, previous_version, _json(list(changed or [])),
                first_seen_at, record.event_at, record.event_at_precision, record.published_at,
                record.published_at_precision, record.record_type, record.title, record.url,
                run_id,
            ),
        )

    def _write_mapping(self, obs_id: str, mapping: MappingResult, mapping_version: str,
                       mapped_at: str) -> None:
        latest = self.con.execute(
            "SELECT * FROM observation_mapping WHERE observation_id=?"
            " ORDER BY mapped_at DESC LIMIT 1",
            (obs_id,),
        ).fetchone()
        same = (
            latest is not None
            and latest["entity_id"] == mapping.entity_id
            and latest["entity_status"] == mapping.entity_status
            and latest["track_id"] == mapping.track_id
            and latest["track_status"] == mapping.track_status
            and latest["mapping_version"] == mapping_version
        )
        if same:
            return
        # microsecond precision keeps append-only mapping history strictly ordered;
        # a same-microsecond collision is bumped so the history can never lose a row
        stamp = datetime.now(timezone.utc).isoformat()
        if latest is not None and stamp <= str(latest["mapped_at"]):
            previous = datetime.fromisoformat(str(latest["mapped_at"]))
            stamp = (previous + timedelta(microseconds=1)).isoformat()
        self.con.execute(
            "INSERT OR IGNORE INTO observation_mapping(observation_id, mapped_at, mapping_version,"
            " entity_id, entity_status, entity_method, entity_confidence, track_id, track_status,"
            " track_method, note_zh) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                obs_id, stamp, mapping_version, mapping.entity_id, mapping.entity_status,
                mapping.entity_method, mapping.entity_confidence, mapping.track_id,
                mapping.track_status, mapping.track_method, mapping.note_zh,
            ),
        )

    # -------------------------------------------------------------------- queries
    def current_mapping_sql(self, alias: str = "o") -> tuple[str, list[Any]]:
        """JOIN fragment selecting the latest mapping row (append-only history)."""
        sql = (
            f" LEFT JOIN observation_mapping m ON m.observation_id = {alias}.observation_id"
            f" AND m.mapped_at = (SELECT MAX(m2.mapped_at) FROM observation_mapping m2"
            f" WHERE m2.observation_id = {alias}.observation_id)"
        )
        return sql, []

    def observation_row(self, obs_id: str) -> dict[str, Any] | None:
        join, _ = self.current_mapping_sql("o")
        row = self.con.execute(
            "SELECT o.*, m.entity_id, m.entity_status, m.entity_method, m.entity_confidence,"
            " m.track_id, m.track_status, m.track_method, m.note_zh AS mapping_note_zh"
            f" FROM observation o{join} WHERE o.observation_id=?",
            (obs_id,),
        ).fetchone()
        return dict(row) if row else None

    def versions(self, obs_id: str) -> list[dict[str, Any]]:
        rows = self.con.execute(
            "SELECT * FROM observation_version WHERE observation_id=? ORDER BY version_seq",
            (obs_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def changes_for(self, obs_id: str) -> list[dict[str, Any]]:
        rows = self.con.execute(
            "SELECT * FROM observation_change WHERE observation_id=?"
            " ORDER BY replace(observed_at,'Z','+00:00'), change_id",
            (obs_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def mapping_history(self, obs_id: str) -> list[dict[str, Any]]:
        rows = self.con.execute(
            "SELECT * FROM observation_mapping WHERE observation_id=? ORDER BY mapped_at",
            (obs_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def status_history(self, obs_id: str) -> list[dict[str, Any]]:
        rows = self.con.execute(
            "SELECT * FROM observation_status_history WHERE observation_id=? ORDER BY changed_at",
            (obs_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def counts(self) -> dict[str, Any]:
        one = lambda sql, params=(): self.con.execute(sql, params).fetchone()[0]  # noqa: E731
        display_path = _display_path(self.path)
        return {
            "observations": int(one("SELECT COUNT(*) FROM observation")),
            "versions": int(one("SELECT COUNT(*) FROM observation_version")),
            "changes": int(one("SELECT COUNT(*) FROM observation_change")),
            "live_observations": int(
                one("SELECT COUNT(*) FROM observation WHERE observation_origin='LIVE'")
            ),
            "backfilled_observations": int(
                one("SELECT COUNT(*) FROM observation WHERE observation_origin='BACKFILLED'")
            ),
            "removed_observations": int(
                one("SELECT COUNT(*) FROM observation WHERE observation_status=?", (STATUS_REMOVED,))
            ),
            "sources": int(one("SELECT COUNT(*) FROM source_state")),
            "runs": int(one("SELECT COUNT(*) FROM sync_run")),
            "failures": int(one("SELECT COUNT(*) FROM source_failure")),
            "first_observation_at": one("SELECT MIN(first_seen_at) FROM observation"),
            "last_observation_at": one("SELECT MAX(first_seen_at) FROM observation"),
            "first_run_at": one("SELECT MIN(started_at) FROM sync_run"),
            "last_run_at": one("SELECT MAX(started_at) FROM sync_run"),
            "schema_version": self._meta("schema_version"),
            "created_at": self._meta("created_at"),
            "db_bytes": self.size_bytes(),
            "path": display_path,
        }

    def window_counts(self, hours: int, *, source: str | None = None,
                      entity_id: str | None = None, track_id: str | None = None,
                      query: str | None = None) -> dict[str, int]:
        since = (utc_now() - timedelta(hours=hours)).replace(microsecond=0).isoformat()
        where, params = self._change_filters(source, entity_id, track_id, query)
        sql = (
            "SELECT c.change_state AS state, COUNT(*) AS n FROM observation_change c"
            " JOIN observation o ON o.observation_id=c.observation_id"
            + self.current_mapping_sql("o")[0]
            + " WHERE replace(c.observed_at,'Z','+00:00') >= ?" + where + " GROUP BY c.change_state"
        )
        rows = self.con.execute(sql, [since, *params]).fetchall()
        found = {row["state"]: int(row["n"]) for row in rows}
        return {
            "new": found.get(CHANGE_NEW, 0),
            "updated": found.get(CHANGE_UPDATED, 0),
            "removed": found.get(CHANGE_REMOVED, 0),
            "failed": found.get(CHANGE_FETCH_FAILED, 0),
            "total": sum(found.values()),
        }

    def window_span(self, hours: int) -> dict[str, Any]:
        end = utc_now().replace(microsecond=0)
        start = end - timedelta(hours=hours)
        return {"start": start.isoformat(), "end": end.isoformat(), "hours": hours}

    def _change_filters(self, source: str | None, entity_id: str | None,
                        track_id: str | None, query: str | None) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if source:
            clauses.append("c.source = ?")
            params.append(source)
        if entity_id:
            if entity_id == "__unmapped__":
                clauses.append("(m.entity_id IS NULL OR m.entity_status != 'MAPPED')")
            else:
                clauses.append("m.entity_id = ?")
                params.append(entity_id)
        if track_id:
            if track_id == "__unmapped__":
                clauses.append("(m.track_id IS NULL OR m.track_status != 'MAPPED')")
            else:
                clauses.append("m.track_id = ?")
                params.append(track_id)
        if query:
            clauses.append("(o.title LIKE ? OR c.title LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like])
        suffix = (" AND " + " AND ".join(clauses)) if clauses else ""
        return suffix, params

    def change_rows(self, *, hours: int | None = None, states: Sequence[str] | None = None,
                    source: str | None = None, entity_id: str | None = None,
                    track_id: str | None = None, query: str | None = None,
                    limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        clauses: list[str] = []
        params: list[Any] = []
        if hours is not None:
            since = (utc_now() - timedelta(hours=hours)).replace(microsecond=0).isoformat()
            clauses.append("replace(c.observed_at,'Z','+00:00') >= ?")
            params.append(since)
        if states:
            clauses.append("c.change_state IN (" + ",".join("?" for _ in states) + ")")
            params.extend(states)
        suffix, extra = self._change_filters(source, entity_id, track_id, query)
        where = ""
        if clauses:
            where = " WHERE " + " AND ".join(clauses)
        where += suffix
        params.extend(extra)
        join, _ = self.current_mapping_sql("o")
        base = (
            "SELECT c.*, o.observation_id AS oid, o.source_record_id, o.first_seen_at AS o_first_seen_at,"
            " o.version_count, o.observation_status, o.observation_origin, o.ingested_at,"
            " o.event_at AS o_event_at, o.event_at_precision AS o_event_precision,"
            " o.published_at AS o_published_at,"
            " o.published_at_precision AS o_published_precision,"
            " o.source_updated_at AS o_source_updated_at, o.last_checked_at,"
            " m.entity_id, m.entity_status, m.entity_method, m.track_id, m.track_status,"
            " m.track_method, m.note_zh AS mapping_note_zh"
            f" FROM observation_change c JOIN observation o ON o.observation_id=c.observation_id{join}"
            + where
        )
        total = self.con.execute(
            "SELECT COUNT(*) FROM observation_change c JOIN observation o ON o.observation_id=c.observation_id"
            + join + where,
            params,
        ).fetchone()[0]
        rows = self.con.execute(
            base + " ORDER BY c.observed_at DESC, c.change_id DESC LIMIT ? OFFSET ?",
            [*params, int(limit), int(offset)],
        ).fetchall()
        return [dict(row) for row in rows], int(total)

    def change_facets(self, *, hours: int | None = None, source: str | None = None,
                      entity_id: str | None = None, track_id: str | None = None,
                      query: str | None = None) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if hours is not None:
            since = (utc_now() - timedelta(hours=hours)).replace(microsecond=0).isoformat()
            clauses.append("replace(c.observed_at,'Z','+00:00') >= ?")
            params.append(since)
        suffix, extra = self._change_filters(source, entity_id, track_id, query)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        where += suffix
        params.extend(extra)
        join, _ = self.current_mapping_sql("o")
        base = (
            " FROM observation_change c JOIN observation o ON o.observation_id=c.observation_id"
            + join + where
        )
        sources = self.con.execute(
            "SELECT c.source, COUNT(*) AS n" + base + " GROUP BY c.source ORDER BY n DESC", params
        ).fetchall()
        changes = self.con.execute(
            "SELECT c.change_state, COUNT(*) AS n" + base + " GROUP BY c.change_state", params
        ).fetchall()
        companies = self.con.execute(
            "SELECT COALESCE(m.entity_id,'__unmapped__') AS entity_id, m.entity_status, COUNT(*) AS n"
            + base + " GROUP BY entity_id, m.entity_status ORDER BY n DESC",
            params,
        ).fetchall()
        tracks = self.con.execute(
            "SELECT COALESCE(m.track_id,'__unmapped__') AS track_id, m.track_status, COUNT(*) AS n"
            + base + " GROUP BY track_id, m.track_status ORDER BY n DESC",
            params,
        ).fetchall()
        return {
            "sources": [dict(row) for row in sources],
            "changes": [dict(row) for row in changes],
            "companies": [dict(row) for row in companies],
            "tracks": [dict(row) for row in tracks],
        }

    def summary_by_source(self, hours: int) -> list[dict[str, Any]]:
        since = (utc_now() - timedelta(hours=hours)).replace(microsecond=0).isoformat()
        rows = self.con.execute(
            "SELECT source, change_state, COUNT(*) AS n FROM observation_change"
            " WHERE replace(observed_at,'Z','+00:00') >= ? GROUP BY source, change_state",
            (since,),
        ).fetchall()
        return [dict(row) for row in rows]

    def summary_by_entity(self, hours: int) -> list[dict[str, Any]]:
        since = (utc_now() - timedelta(hours=hours)).replace(microsecond=0).isoformat()
        join, _ = self.current_mapping_sql("o")
        rows = self.con.execute(
            "SELECT COALESCE(m.entity_id,'__unmapped__') AS entity_id, m.entity_status,"
            " c.change_state, COUNT(*) AS n FROM observation_change c"
            " JOIN observation o ON o.observation_id=c.observation_id" + join +
            " WHERE replace(c.observed_at,'Z','+00:00') >= ? GROUP BY entity_id, m.entity_status, c.change_state",
            (since,),
        ).fetchall()
        return [dict(row) for row in rows]

    def summary_by_track(self, hours: int) -> list[dict[str, Any]]:
        since = (utc_now() - timedelta(hours=hours)).replace(microsecond=0).isoformat()
        join, _ = self.current_mapping_sql("o")
        rows = self.con.execute(
            "SELECT COALESCE(m.track_id,'__unmapped__') AS track_id, m.track_status,"
            " c.change_state, COUNT(*) AS n FROM observation_change c"
            " JOIN observation o ON o.observation_id=c.observation_id" + join +
            " WHERE replace(c.observed_at,'Z','+00:00') >= ? GROUP BY track_id, m.track_status, c.change_state",
            (since,),
        ).fetchall()
        return [dict(row) for row in rows]

    def observation_ids_for(self, source: str, source_record_ids: Iterable[str]) -> dict[str, str]:
        """Map source record ids → observation ids (used to mark FETCH_FAILED)."""
        ids = [str(item) for item in source_record_ids if item]
        found: dict[str, str] = {}
        for start in range(0, len(ids), 400):
            chunk = ids[start : start + 400]
            placeholders = ",".join("?" for _ in chunk)
            rows = self.con.execute(
                f"SELECT source_record_id, observation_id FROM observation"
                f" WHERE source=? AND source_record_id IN ({placeholders})",
                [source, *chunk],
            ).fetchall()
            for row in rows:
                found[row["source_record_id"]] = row["observation_id"]
        return found

    def entity_totals(self) -> dict[str, dict[str, Any]]:
        join, _ = self.current_mapping_sql("o")
        rows = self.con.execute(
            "SELECT m.entity_id, m.entity_status, COUNT(*) AS n FROM observation o" + join +
            " GROUP BY m.entity_id, m.entity_status"
        ).fetchall()
        return {row["entity_id"] or "__unmapped__": dict(row) for row in rows}

    def unmapped_counts(self) -> dict[str, int]:
        join, _ = self.current_mapping_sql("o")
        row = self.con.execute(
            "SELECT SUM(CASE WHEN m.entity_id IS NULL THEN 1 ELSE 0 END) AS unmapped_company,"
            " SUM(CASE WHEN m.track_id IS NULL THEN 1 ELSE 0 END) AS unmapped_track,"
            " COUNT(*) AS total FROM observation o" + join
        ).fetchone()
        return {
            "company": int(row["unmapped_company"] or 0),
            "track": int(row["unmapped_track"] or 0),
            "total": int(row["total"] or 0),
        }

    # --------------------------------------------------------- point-in-time replay
    def snapshot(self, as_of: str, *, source: str | None = None,
                 limit: int | None = None) -> dict[str, Any]:
        """What the ledger *knew* at ``as_of`` — later discoveries are excluded.

        The filter is on ``first_seen_at <= as_of`` (system knowledge), not on
        ``event_at`` (when the event happened). A record whose event is old but
        which MedRadar discovered later must not appear in a historical replay.
        """
        moment = _normalize_as_of(as_of)
        clauses = ["replace(o.first_seen_at,'Z','+00:00') <= ?"]
        params: list[Any] = [moment]
        if source:
            clauses.append("o.source = ?")
            params.append(source)
        where = " WHERE " + " AND ".join(clauses)
        discovered_later = self.con.execute(
            "SELECT COUNT(*) FROM observation o WHERE replace(o.first_seen_at,'Z','+00:00') > ?"
            + (" AND o.source = ?" if source else ""),
            [moment, *([source] if source else [])],
        ).fetchone()[0]
        sql = (
            "SELECT o.observation_id, o.source, o.source_record_id, o.record_type, o.title,"
            " o.original_url, o.first_seen_at, o.event_at, o.event_at_precision, o.published_at,"
            " o.published_at_precision, o.observation_origin,"
            " v.version_id, v.version_seq, v.captured_at, v.payload_hash, v.payload,"
            " (SELECT sh.status FROM observation_status_history sh"
            "  WHERE sh.observation_id=o.observation_id"
            "    AND replace(sh.changed_at,'Z','+00:00') <= ?"
            "  ORDER BY sh.changed_at DESC LIMIT 1) AS status_at,"
            " (SELECT COUNT(*) FROM observation_version v2"
            "  WHERE v2.observation_id=o.observation_id"
            "    AND replace(v2.captured_at,'Z','+00:00') <= ?) AS versions_at"
            f" FROM observation o JOIN observation_version v ON v.observation_id=o.observation_id"
            " AND v.version_seq = (SELECT MAX(v3.version_seq) FROM observation_version v3"
            "   WHERE v3.observation_id=o.observation_id"
            "     AND replace(v3.captured_at,'Z','+00:00') <= ?)"
            + where +
            " ORDER BY replace(o.first_seen_at,'Z','+00:00') DESC, o.observation_id"
        )
        args: list[Any] = [moment, moment, moment, *params]
        if limit:
            sql += " LIMIT ?"
            args.append(int(limit))
        rows = self.con.execute(sql, args).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item["payload"]) if item["payload"] else None
            except (TypeError, ValueError):
                pass
            items.append(item)
        return {
            "as_of": moment,
            "policy_zh": (
                "只包含在 as_of 之前已被 MedRadar 实际观察到的记录（first_seen_at <= as_of）；"
                "之后才发现的历史记录一律排除，即使其事件日期更早。"
            ),
            "total": len(items),
            "excluded_discovered_later": int(discovered_later),
            "items": items,
        }

    # ------------------------------------------------------------ consistency
    def consistency_check(self) -> dict[str, Any]:
        """Data-consistency audit. Any non-empty list is a real defect."""
        issues: dict[str, list[dict[str, Any]]] = {}

        def collect(name: str, sql: str) -> None:
            rows = self.con.execute(sql).fetchall()
            if rows:
                issues[name] = [dict(row) for row in rows[:50]]

        collect(
            "version_count_mismatch",
            "SELECT o.observation_id, o.version_count, COUNT(v.version_id) AS actual"
            " FROM observation o LEFT JOIN observation_version v ON v.observation_id=o.observation_id"
            " GROUP BY o.observation_id HAVING o.version_count != COUNT(v.version_id)",
        )
        collect(
            "first_version_not_new",
            "SELECT v.observation_id, v.change_state FROM observation_version v WHERE v.version_seq=1"
            " AND v.change_state != 'NEW'",
        )
        collect(
            "first_seen_after_first_version",
            "SELECT o.observation_id, o.first_seen_at, v.captured_at FROM observation o"
            " JOIN observation_version v ON v.observation_id=o.observation_id AND v.version_seq=1"
            " WHERE replace(o.first_seen_at,'Z','+00:00')"
            "     > replace(v.captured_at,'Z','+00:00')",
        )
        collect(
            "version_seq_gap",
            "SELECT observation_id, COUNT(*) AS n, MAX(version_seq) AS max_seq FROM observation_version"
            " GROUP BY observation_id HAVING COUNT(*) != MAX(version_seq)",
        )
        collect(
            "orphan_versions",
            "SELECT v.observation_id FROM observation_version v LEFT JOIN observation o"
            " ON o.observation_id=v.observation_id WHERE o.observation_id IS NULL",
        )
        collect(
            "orphan_changes",
            "SELECT c.observation_id FROM observation_change c LEFT JOIN observation o"
            " ON o.observation_id=c.observation_id WHERE o.observation_id IS NULL",
        )
        collect(
            "changes_after_first_seen",
            "SELECT c.change_id, c.observed_at, c.first_seen_at FROM observation_change c"
            " WHERE replace(c.observed_at,'Z','+00:00')"
            "     < replace(c.first_seen_at,'Z','+00:00')",
        )
        collect(
            "running_runs_stale",
            "SELECT run_id, source, started_at FROM sync_run WHERE status='RUNNING'",
        )
        collect(
            "backfill_without_reason",
            "SELECT observation_id FROM observation WHERE observation_origin='BACKFILLED'"
            " AND (backfill_reason IS NULL OR backfill_reason='')",
        )
        collect(
            "missing_mapping",
            "SELECT o.observation_id FROM observation o LEFT JOIN observation_mapping m"
            " ON m.observation_id=o.observation_id WHERE m.observation_id IS NULL",
        )
        collect(
            "missing_status_history",
            "SELECT o.observation_id FROM observation o LEFT JOIN observation_status_history s"
            " ON s.observation_id=o.observation_id WHERE s.observation_id IS NULL",
        )
        return {
            "ok": not issues,
            "issues": issues,
            "issue_count": sum(len(v) for v in issues.values()),
            "checked_at": utc_now_iso(),
        }

    # --------------------------------------------------- acquisition phase history
    def table_exists(self, name: str) -> bool:
        row = self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return row is not None

    def assign_phase(self, observation_id: str, phase: str, *, run_id: str | None = None,
                     method: str = "collector_assigned", note_zh: str | None = None,
                     assigned_at: str | None = None) -> bool:
        """Append an acquisition-phase label. Never updates an existing label."""
        from .records import PHASES

        if phase not in PHASES:
            raise ValueError(f"bad acquisition phase: {phase}")
        stamp = datetime.now(timezone.utc).isoformat()
        if assigned_at is not None:
            stamp = assigned_at
        current = self.con.execute(
            "SELECT phase, method FROM observation_phase WHERE observation_id=?"
            " ORDER BY assigned_at DESC LIMIT 1",
            (observation_id,),
        ).fetchone()
        if current is not None and current["phase"] == phase and current["method"] == method:
            return False
        with self._transaction():
            self.con.execute(
                "INSERT OR IGNORE INTO observation_phase(observation_id, phase, assigned_at,"
                " run_id, method, note_zh) VALUES(?,?,?,?,?,?)",
                (observation_id, phase, stamp, run_id, method, note_zh),
            )
        return True

    def latest_phase_sql(self, alias: str = "o") -> str:
        return (
            f" LEFT JOIN observation_phase p ON p.observation_id = {alias}.observation_id"
            f" AND p.assigned_at = (SELECT MAX(p2.assigned_at) FROM observation_phase p2"
            f" WHERE p2.observation_id = {alias}.observation_id)"
        )

    def phases_for(self, observation_ids: Iterable[str]) -> dict[str, str]:
        ids = [str(item) for item in observation_ids if item]
        found: dict[str, str] = {}
        for start in range(0, len(ids), 400):
            chunk = ids[start : start + 400]
            placeholders = ",".join("?" for _ in chunk)
            rows = self.con.execute(
                f"SELECT observation_id, phase FROM observation_phase WHERE observation_id IN ({placeholders})"
                " AND assigned_at = (SELECT MAX(p2.assigned_at) FROM observation_phase p2"
                "  WHERE p2.observation_id = observation_phase.observation_id)",
                chunk,
            ).fetchall()
            for row in rows:
                found[row["observation_id"]] = row["phase"]
        return found

    def phase_counts(self) -> dict[str, int]:
        if not self.table_exists("observation_phase"):
            return {}
        join = self.latest_phase_sql("o")
        rows = self.con.execute(
            "SELECT COALESCE(p.phase, '__unlabelled__') AS phase, COUNT(*) AS n"
            " FROM observation o" + join + " GROUP BY phase"
        ).fetchall()
        return {row["phase"]: int(row["n"]) for row in rows}

    def source_has_observations(self, source: str) -> bool:
        row = self.con.execute(
            "SELECT 1 FROM observation WHERE source=? LIMIT 1", (source,)
        ).fetchone()
        return row is not None

    def first_observation_run(self, source: str) -> str | None:
        """Run id of the source's first run that actually recorded observations."""
        row = self.con.execute(
            "SELECT first_seen_run_id FROM observation WHERE source=?"
            " ORDER BY first_seen_at, observation_id LIMIT 1",
            (source,),
        ).fetchone()
        if row is None:
            return None
        return str(row["first_seen_run_id"]) if row["first_seen_run_id"] else None

    def reconstruct_phases(self, *, assigned_at: str | None = None) -> dict[str, Any]:
        """Label pre-existing observations from run history (append-only metadata).

        A record is INITIAL_DISCOVERY when it was first observed by its source's
        first observation-producing run, INCREMENTAL_DISCOVERY when a later run
        observed it, and HISTORICAL_BACKFILL when it was ingested as a backfill.
        This never rewrites the immutable observation rows.
        """
        from .records import PHASE_BACKFILL, PHASE_INCREMENTAL, PHASE_INITIAL, ORIGIN_BACKFILLED

        stamp = assigned_at or datetime.now(timezone.utc).isoformat()
        rows = self.con.execute(
            "SELECT o.observation_id, o.source, o.first_seen_run_id, o.observation_origin"
            " FROM observation o WHERE NOT EXISTS ("
            "  SELECT 1 FROM observation_phase p WHERE p.observation_id=o.observation_id)"
        ).fetchall()
        first_runs = {
            row["source"]: row["run_id"]
            for row in self.con.execute(
                "SELECT source, first_seen_run_id AS run_id FROM observation"
                " GROUP BY source"
            ).fetchall()
        }
        counts = {PHASE_INITIAL: 0, PHASE_INCREMENTAL: 0, PHASE_BACKFILL: 0}
        for row in rows:
            obs_id = row["observation_id"]
            if row["observation_origin"] == ORIGIN_BACKFILLED:
                phase = PHASE_BACKFILL
                note = "由 observation_origin=BACKFILLED 推导"
            elif row["first_seen_run_id"] and row["first_seen_run_id"] == first_runs.get(row["source"]):
                phase = PHASE_INITIAL
                note = "首次观察所属运行即该来源的首个观察产岀运行"
            else:
                phase = PHASE_INCREMENTAL
                note = "首次观察发生在该来源首轮之后的运行"
            self.assign_phase(
                obs_id,
                phase,
                run_id=row["first_seen_run_id"],
                method="reconstructed_from_run_history",
                note_zh=note,
                assigned_at=stamp,
            )
            counts[phase] = counts.get(phase, 0) + 1
        return {"labelled": len(rows), "counts": counts, "assigned_at": stamp}

    def phase_summary(self) -> dict[str, Any]:
        counts = self.phase_counts()
        return {
            "counts": counts,
            "labels_zh": {
                "INITIAL_DISCOVERY": "初次上线发现（既有公开记录）",
                "INCREMENTAL_DISCOVERY": "持续监测新发现（增量）",
                "HISTORICAL_BACKFILL": "历史回填",
            },
            "unlabelled": counts.get("__unlabelled__", 0),
        }

    # ------------------------------------------------------------- run outcomes
    def record_outcome(self, source: str, run_id: str, outcome: str, *,
                       new: int = 0, updated: int = 0,
                       finished_at: str | None = None) -> None:
        """Store what the last run actually produced for this source.

        ``NO_NEW_RECORDS`` is a normal result and is reported as such; it is never
        conflated with ``FETCH_FAILED``.
        """
        from .records import OUTCOMES

        if outcome not in OUTCOMES:
            raise ValueError(f"bad run outcome: {outcome}")
        self.con.execute(
            "UPDATE source_state SET last_outcome=?, last_new_records=?,"
            " last_updated_records=?, last_finished_at=?, last_run_id=? WHERE source=?",
            (outcome, int(new), int(updated), finished_at or utc_now_iso(), run_id, source),
        )
        self.con.commit()

    # ------------------------------------------------- deployment / validation state
    def set_deployment(self, payload: Mapping[str, Any]) -> None:
        self.set_runtime("deployment", dict(payload))

    def get_deployment(self) -> dict[str, Any]:
        value = self.get_runtime("deployment", {})
        return value if isinstance(value, dict) else {}

    def set_validation(self, payload: Mapping[str, Any]) -> None:
        self.set_runtime("validation", dict(payload))

    def get_validation(self) -> dict[str, Any]:
        value = self.get_runtime("validation", {})
        return value if isinstance(value, dict) else {}

    def record_ops_metric(self, metric: str, value: Any, *, day: str | None = None) -> None:
        import hashlib

        stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        day_key = day or stamp[:10]
        self.con.execute(
            "INSERT INTO ops_metric(metric, day, value, recorded_at) VALUES(?,?,?,?)"
            " ON CONFLICT(metric, day) DO UPDATE SET value=excluded.value,"
            " recorded_at=excluded.recorded_at",
            (metric, day_key, _json(value), stamp),
        )
        self.con.commit()

    def ops_metric_series(self, metric: str, *, days: int = 30) -> list[dict[str, Any]]:
        rows = self.con.execute(
            "SELECT metric, day, value, recorded_at FROM ops_metric WHERE metric=?"
            " ORDER BY day DESC LIMIT ?",
            (metric, max(1, int(days))),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["value"] = json.loads(item["value"])
            except (TypeError, ValueError):
                pass
            result.append(item)
        return result

    def observation_stats(self) -> dict[str, Any]:
        row = self.con.execute(
            "SELECT COUNT(*) AS n, MIN(first_seen_at) AS first, MAX(first_seen_at) AS last"
            " FROM observation"
        ).fetchone()
        by_source = {
            r["source"]: int(r["n"])
            for r in self.con.execute(
                "SELECT source, COUNT(*) AS n FROM observation GROUP BY source"
            ).fetchall()
        }
        return {
            "observations": int(row["n"]),
            "first_seen_at": row["first"],
            "last_first_seen_at": row["last"],
            "by_source": by_source,
            "phase": self.phase_counts(),
        }

    # -------------------------------------------------------------- runtime state
    def set_runtime(self, key: str, value: Any) -> None:
        self.con.execute(
            "INSERT INTO runtime_state(key, value, updated_at) VALUES(?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, _json(value), utc_now_iso()),
        )
        self.con.commit()

    def get_runtime(self, key: str, default: Any = None) -> Any:
        row = self.con.execute("SELECT value FROM runtime_state WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, ValueError):
            return row["value"]

    def pause(self, reason: str) -> None:
        self.set_runtime("paused", {"paused": True, "reason": reason, "at": utc_now_iso()})

    def resume(self) -> None:
        self.set_runtime("paused", {"paused": False, "at": utc_now_iso()})

    def is_paused(self) -> bool:
        state = self.get_runtime("paused", {})
        return bool(isinstance(state, dict) and state.get("paused"))

    def heartbeat(self, payload: Mapping[str, Any]) -> None:
        self.set_runtime("heartbeat", {**payload, "at": utc_now_iso()})


# ----------------------------------------------------------------------- helpers
def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _display_path(path: Path) -> str:
    """Relative path when the ledger lives under the current checkout, else its name."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def _change_id(obs_id: str, state: str, version: str | None, observed_at: str) -> str:
    import hashlib

    raw = f"{obs_id}|{state}|{version or '-'}|{observed_at}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _normalize_as_of(value: Any) -> str:
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    text = str(value or "").strip()
    if not text:
        raise ValueError("as_of is required (ISO 8601)")
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"as_of must be ISO 8601, got {text!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def use_ledger(path: str | Path) -> Iterator[ObservationLedger]:
    """Point this process at a throwaway ledger (tests, acceptance runs)."""
    previous = os.environ.get("MEDRADAR_OBSERVATORY_DB")
    os.environ["MEDRADAR_OBSERVATORY_DB"] = str(path)
    ledger = ObservationLedger(path)
    try:
        yield ledger
    finally:
        ledger.close()
        if previous is None:
            os.environ.pop("MEDRADAR_OBSERVATORY_DB", None)
        else:
            os.environ["MEDRADAR_OBSERVATORY_DB"] = previous


def open_ledger(path: str | Path | None = None, *, create: bool = True,
                read_only: bool = False) -> ObservationLedger:
    return ObservationLedger(path, create=create, read_only=read_only)


def open_ledger_readonly(path: str | Path | None = None) -> ObservationLedger:
    """Read-only handle for the product layer; raises FileNotFoundError if absent."""
    return ObservationLedger(path, read_only=True)
