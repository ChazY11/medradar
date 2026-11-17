"""Append-only intelligence observation ledger for RADAR-001.

The ledger is the system of record for *what a source said and when MedRadar first saw it*.
It is deliberately split into two kinds of storage:

**Append-only history** (never updated, never deleted; enforced by SQL triggers)

* ``observation_version`` - one row per payload version, including the canonical payload,
  its hash and the fields that changed;
* ``observation_change`` - one row per visible change event (``NEW``, ``UPDATED``,
  ``REMOVED_OR_UNAVAILABLE``, ``FETCH_FAILED``);
* ``observation_status_history`` - active/removed transitions;
* ``observation_mapping`` - one row per classification pass, so a re-classification is
  visible as history rather than as a silent rewrite;
* ``ai_candidate`` - every model proposal with its validation verdict;
* ``source_failure`` - every recorded failure, never overwritten by a later success.

**Mutable projection** (rebuildable, never the source of truth)

* ``observation`` - the head row: identity, immutable ``first_observed_at``, mutable
  ``last_checked_at``/current state;
* ``observation_facet`` - the current organisation/product/topic projection used by feed
  filters (rebuildable from ``observation_mapping``);
* ``processing_queue`` / ``graph_materialization`` - work state;
* ``source_state`` / ``sync_run`` / ``sync_checkpoint`` / ``runtime_state`` - the cursor and
  health state.

Invariants this module enforces in code *and* in SQL:

1. ``first_observed_at`` can never be rewritten. A backfilled record must declare
   ``origin=BACKFILLED`` and a reason; the ledger refuses the insert otherwise.
2. A failed fetch never advances the watermark and never marks a record unchanged.
3. ``UNCHANGED`` is never written as a change row.
4. A re-observed identical payload is idempotent: no new version, no new change row.
5. ``(source, source_record_id)`` is the identity. Two sources never collide.

Adapted from the Live Observatory ledger (PR #13/#14, ``medradar/observatory/ledger.py``)
with the RADAR-001 intelligence fields added. The single-writer lock is the DATA-003
``PipelineLock``, reused rather than re-implemented.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from ..data_pipeline.lock import PipelineLock, PipelineLocked  # reused single-writer lock
from .records import (
    ALL_CHANGE_STATES,
    CHANGE_FETCH_FAILED,
    CHANGE_NEW,
    CHANGE_REMOVED,
    CHANGE_UNCHANGED,
    CHANGE_UPDATED,
    CHANGE_STATES,
    MAPPING_VERSION,
    ORIGIN_BACKFILLED,
    ORIGIN_LIVE,
    ORIGINS,
    PHASE_BACKFILL,
    PHASE_INCREMENTAL,
    PHASE_INITIAL,
    PHASES,
    PROC_RAW,
    PROCESSING_STATES,
    STATUS_ACTIVE,
    STATUS_REMOVED,
    canonical_json,
    changed_fields,
    content_hash,
    observation_id as make_observation_id,
    standard_identifiers,
    utc_now_iso,
    version_id as make_version_id,
)
from .records import MappingResult, RawRecord, RecordOutcome

SCHEMA_VERSION = "radar-ledger-v2"
RadarLocked = PipelineLocked

#: v1 keyed status history by ``(observation_id, changed_at)`` at second precision, so two
#: transitions inside one second collided. v2 uses a surrogate key. The migration below copies
#: every existing row forward; nothing is dropped and the append-only triggers still hold.
_LEGACY_STATUS_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS observation_status_history (
    observation_id TEXT NOT NULL,
    changed_at     TEXT NOT NULL,
    status         TEXT NOT NULL,
    run_id         TEXT,
    note           TEXT,
    PRIMARY KEY (observation_id, changed_at)
);
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- ---------------------------------------------------------------- append-only history
CREATE TABLE IF NOT EXISTS observation_version (
    version_id      TEXT PRIMARY KEY,
    observation_id  TEXT NOT NULL,
    version_seq     INTEGER NOT NULL,
    captured_at     TEXT NOT NULL,
    change_state    TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    payload         TEXT NOT NULL,
    payload_bytes   INTEGER NOT NULL,
    changed_fields  TEXT,
    source_updated_at TEXT,
    run_id          TEXT,
    adapter_version TEXT NOT NULL,
    UNIQUE (observation_id, content_hash)
);
CREATE INDEX IF NOT EXISTS ix_version_obs ON observation_version(observation_id, version_seq);

CREATE TABLE IF NOT EXISTS observation_change (
    change_id       TEXT PRIMARY KEY,
    observation_id  TEXT NOT NULL,
    source          TEXT NOT NULL,
    change_state    TEXT NOT NULL,
    observed_at     TEXT NOT NULL,
    version_id      TEXT,
    previous_version_id TEXT,
    changed_fields  TEXT,
    first_observed_at TEXT NOT NULL,
    event_at        TEXT,
    event_at_precision TEXT,
    published_at    TEXT,
    published_at_precision TEXT,
    record_type     TEXT NOT NULL,
    title           TEXT NOT NULL,
    url             TEXT,
    run_id          TEXT,
    discovery_phase TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_change_observed ON observation_change(observed_at);
CREATE INDEX IF NOT EXISTS ix_change_state ON observation_change(change_state);
CREATE INDEX IF NOT EXISTS ix_change_source ON observation_change(source);

CREATE TABLE IF NOT EXISTS observation_status_history (
    history_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id TEXT NOT NULL,
    changed_at     TEXT NOT NULL,
    status         TEXT NOT NULL,
    run_id         TEXT,
    note           TEXT
);
CREATE INDEX IF NOT EXISTS ix_status_obs ON observation_status_history(observation_id, changed_at);

CREATE TABLE IF NOT EXISTS observation_mapping (
    mapping_id     TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL,
    mapped_at      TEXT NOT NULL,
    mapping_version TEXT NOT NULL,
    organization_candidates TEXT NOT NULL,
    product_candidates TEXT NOT NULL,
    technology_topics TEXT NOT NULL,
    note           TEXT
);
CREATE INDEX IF NOT EXISTS ix_mapping_obs ON observation_mapping(observation_id, mapped_at);

CREATE TABLE IF NOT EXISTS ai_candidate (
    candidate_id   TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL,
    version_id     TEXT,
    model_id       TEXT NOT NULL,
    model_version  TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    payload        TEXT NOT NULL,
    validation     TEXT NOT NULL,
    validation_state TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ai_obs ON ai_candidate(observation_id);

CREATE TABLE IF NOT EXISTS source_failure (
    failure_id     TEXT PRIMARY KEY,
    source         TEXT NOT NULL,
    run_id         TEXT,
    kind           TEXT NOT NULL,
    message        TEXT NOT NULL,
    occurred_at    TEXT NOT NULL,
    retryable      INTEGER NOT NULL,
    retry_after_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_failure_source ON source_failure(source, occurred_at);

-- ------------------------------------------------------------ mutable projection
CREATE TABLE IF NOT EXISTS observation (
    observation_id TEXT PRIMARY KEY,
    source         TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    record_type    TEXT NOT NULL,
    official_identifier TEXT,
    title          TEXT NOT NULL,
    source_url     TEXT,
    first_observed_at TEXT NOT NULL,
    ingested_at    TEXT NOT NULL,
    observation_origin TEXT NOT NULL,
    backfill_reason TEXT,
    discovery_phase TEXT NOT NULL,
    event_at       TEXT,
    event_at_precision TEXT,
    published_at   TEXT,
    published_at_precision TEXT,
    source_updated_at TEXT,
    source_updated_at_precision TEXT,
    last_checked_at TEXT NOT NULL,
    last_checked_run_id TEXT,
    content_hash   TEXT NOT NULL,
    latest_version_id TEXT NOT NULL,
    version_count  INTEGER NOT NULL,
    observation_status TEXT NOT NULL,
    current_change_state TEXT,
    last_change_at TEXT,
    first_seen_run_id TEXT,
    processing_state TEXT NOT NULL,
    processing_updated_at TEXT,
    site_domain    TEXT,
    UNIQUE (source, source_record_id)
);
CREATE INDEX IF NOT EXISTS ix_obs_source ON observation(source);
CREATE INDEX IF NOT EXISTS ix_obs_first_observed ON observation(first_observed_at);
CREATE INDEX IF NOT EXISTS ix_obs_published ON observation(published_at);
CREATE INDEX IF NOT EXISTS ix_obs_event ON observation(event_at);
CREATE INDEX IF NOT EXISTS ix_obs_state ON observation(current_change_state);
CREATE INDEX IF NOT EXISTS ix_obs_processing ON observation(processing_state);
CREATE INDEX IF NOT EXISTS ix_obs_phase ON observation(discovery_phase);
CREATE INDEX IF NOT EXISTS ix_obs_record_type ON observation(record_type);
-- Cross-source identity joins (OFFICIAL_IDENTIFIER_MATCH) look a record up by this column on
-- every materialisation. Without the index that lookup is a full scan of the ledger.
CREATE INDEX IF NOT EXISTS ix_obs_official ON observation(official_identifier);

CREATE TABLE IF NOT EXISTS observation_facet (
    observation_id TEXT NOT NULL,
    kind           TEXT NOT NULL,          -- organization | product | topic
    value          TEXT NOT NULL,
    confirmation   TEXT NOT NULL,
    method         TEXT NOT NULL,
    confidence     REAL,
    PRIMARY KEY (observation_id, kind, value)
);
CREATE INDEX IF NOT EXISTS ix_facet_lookup ON observation_facet(kind, value, confirmation);

CREATE TABLE IF NOT EXISTS source_state (
    source_id      TEXT PRIMARY KEY,
    label          TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    cadence_hours  REAL NOT NULL,
    access_state   TEXT NOT NULL DEFAULT 'UNVERIFIED',
    access_reason  TEXT,
    enabled        INTEGER NOT NULL DEFAULT 1,
    watermark      TEXT,
    cursor_json    TEXT,
    structure_signature TEXT,
    first_success_at TEXT,
    first_successful_run_id TEXT,
    last_checked_at TEXT,
    last_success_check_at TEXT,
    last_failure_at TEXT,
    last_failure_message TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_observed_update_at TEXT,
    last_run_outcome TEXT,
    observations_total INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_run (
    run_id         TEXT PRIMARY KEY,
    source         TEXT NOT NULL,
    trigger        TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    status         TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    counters_json  TEXT,
    errors_json    TEXT,
    watermark_before TEXT,
    watermark_after TEXT,
    pid            INTEGER,
    host           TEXT
);
CREATE INDEX IF NOT EXISTS ix_run_source ON sync_run(source, started_at);

CREATE TABLE IF NOT EXISTS sync_checkpoint (
    source         TEXT NOT NULL,
    run_id         TEXT NOT NULL,
    scope_id       TEXT NOT NULL,
    cursor         TEXT,
    records_seen   INTEGER NOT NULL DEFAULT 0,
    saved_at       TEXT NOT NULL,
    PRIMARY KEY (source, run_id, scope_id)
);

CREATE TABLE IF NOT EXISTS processing_queue (
    task_id        TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL,
    version_id     TEXT,
    kind           TEXT NOT NULL,
    state          TEXT NOT NULL,       -- PENDING | RUNNING | DONE | FAILED | DEFERRED
    attempts       INTEGER NOT NULL DEFAULT 0,
    priority       INTEGER NOT NULL DEFAULT 100,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    claimed_at     TEXT,
    finished_at    TEXT,
    last_error     TEXT,
    next_attempt_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_queue_state ON processing_queue(state, priority, created_at);
CREATE INDEX IF NOT EXISTS ix_queue_obs ON processing_queue(observation_id);

CREATE TABLE IF NOT EXISTS graph_materialization (
    observation_id TEXT PRIMARY KEY,
    version_id     TEXT NOT NULL,
    graph_version  TEXT NOT NULL,
    assertions     INTEGER NOT NULL,
    materialized_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Normalised official identifiers (PMID, DOI) attached to an observation.
-- A row here is a statement the *source* made, not an inference: the DOI parser only accepts
-- the 10.<registrant>/<suffix> shape and lowercases it. Two rows with the same (kind, value)
-- from different sources are the verifiable basis of a cross-source work match.
CREATE TABLE IF NOT EXISTS observation_identifier (
    observation_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT,
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (observation_id, kind, value)
);
CREATE INDEX IF NOT EXISTS ix_ident_lookup ON observation_identifier(kind, value);

-- --------------------------------------------------------------- append-only guards
CREATE TRIGGER IF NOT EXISTS trg_version_no_update BEFORE UPDATE ON observation_version
BEGIN SELECT RAISE(ABORT, 'observation_version is append-only: UPDATE rejected'); END;
CREATE TRIGGER IF NOT EXISTS trg_version_no_delete BEFORE DELETE ON observation_version
BEGIN SELECT RAISE(ABORT, 'observation_version is append-only: DELETE rejected'); END;
CREATE TRIGGER IF NOT EXISTS trg_change_no_update BEFORE UPDATE ON observation_change
BEGIN SELECT RAISE(ABORT, 'observation_change is append-only: UPDATE rejected'); END;
CREATE TRIGGER IF NOT EXISTS trg_change_no_delete BEFORE DELETE ON observation_change
BEGIN SELECT RAISE(ABORT, 'observation_change is append-only: DELETE rejected'); END;
CREATE TRIGGER IF NOT EXISTS trg_status_no_update BEFORE UPDATE ON observation_status_history
BEGIN SELECT RAISE(ABORT, 'observation_status_history is append-only: UPDATE rejected'); END;
CREATE TRIGGER IF NOT EXISTS trg_status_no_delete BEFORE DELETE ON observation_status_history
BEGIN SELECT RAISE(ABORT, 'observation_status_history is append-only: DELETE rejected'); END;
CREATE TRIGGER IF NOT EXISTS trg_mapping_no_update BEFORE UPDATE ON observation_mapping
BEGIN SELECT RAISE(ABORT, 'observation_mapping is append-only: UPDATE rejected'); END;
CREATE TRIGGER IF NOT EXISTS trg_mapping_no_delete BEFORE DELETE ON observation_mapping
BEGIN SELECT RAISE(ABORT, 'observation_mapping is append-only: DELETE rejected'); END;
CREATE TRIGGER IF NOT EXISTS trg_ai_no_update BEFORE UPDATE ON ai_candidate
BEGIN SELECT RAISE(ABORT, 'ai_candidate is append-only: UPDATE rejected'); END;
CREATE TRIGGER IF NOT EXISTS trg_ai_no_delete BEFORE DELETE ON ai_candidate
BEGIN SELECT RAISE(ABORT, 'ai_candidate is append-only: DELETE rejected'); END;
CREATE TRIGGER IF NOT EXISTS trg_failure_no_update BEFORE UPDATE ON source_failure
BEGIN SELECT RAISE(ABORT, 'source_failure is append-only: UPDATE rejected'); END;
CREATE TRIGGER IF NOT EXISTS trg_failure_no_delete BEFORE DELETE ON source_failure
BEGIN SELECT RAISE(ABORT, 'source_failure is append-only: DELETE rejected'); END;

-- first_observed_at and the identity of an observation are immutable.
CREATE TRIGGER IF NOT EXISTS trg_obs_identity_immutable
BEFORE UPDATE OF observation_id, source, source_record_id, first_observed_at, ingested_at,
                 observation_origin ON observation
BEGIN
    SELECT RAISE(ABORT, 'observation identity and first_observed_at are immutable');
END;
CREATE TRIGGER IF NOT EXISTS trg_obs_no_delete BEFORE DELETE ON observation
BEGIN SELECT RAISE(ABORT, 'observations are not deleted; mark them removed instead'); END;

-- UNCHANGED is a check result, not a change event.
CREATE TRIGGER IF NOT EXISTS trg_change_states BEFORE INSERT ON observation_change
WHEN NEW.change_state NOT IN ('NEW','UPDATED','REMOVED_OR_UNAVAILABLE','FETCH_FAILED')
BEGIN SELECT RAISE(ABORT, 'observation_change: only NEW/UPDATED/REMOVED_OR_UNAVAILABLE/FETCH_FAILED may be stored'); END;

-- A backfilled observation must carry a reason.
CREATE TRIGGER IF NOT EXISTS trg_backfill_reason BEFORE INSERT ON observation
WHEN NEW.observation_origin = 'BACKFILLED' AND (NEW.backfill_reason IS NULL OR NEW.backfill_reason = '')
BEGIN SELECT RAISE(ABORT, 'a BACKFILLED observation requires a reason'); END;
"""


def _json(value: Any) -> str:
    return canonical_json(value)


def _parse_json(text: str | None, default: Any = None) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def _counters() -> dict[str, int]:
    return {
        "requests": 0,
        "pages": 0,
        "records_seen": 0,
        "records_new": 0,
        "records_updated": 0,
        "records_unchanged": 0,
        "records_removed": 0,
        "records_failed": 0,
        "records_skipped": 0,
    }


@dataclass(frozen=True)
class LedgerCounts:
    observations: int
    sources: int
    change_events: int
    versions: int
    ai_candidates: int
    queue_pending: int
    graph_materialized: int


class ObservationLedger:
    """One SQLite database, two kinds of storage, enforced invariants."""

    def __init__(self, path: str | Path, *, create: bool = True, read_only: bool = False) -> None:
        self.path = Path(path)
        self.read_only = bool(read_only)
        self._lock = threading.RLock()
        self._closed = False
        if self.path != Path(":memory:") and not self.read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        if not create and not self.exists:
            raise FileNotFoundError(f"no radar ledger at {self.path}")
        if self.read_only:
            resolved = self.path.resolve()
            self.con = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True,
                                       timeout=60, isolation_level=None)
        else:
            self.con = sqlite3.connect(str(self.path), timeout=60, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        if not self.read_only:
            self.con.execute("PRAGMA journal_mode=WAL")
            self.con.execute("PRAGMA synchronous=NORMAL")
        self.con.execute("PRAGMA foreign_keys=ON")
        self._ensure_schema()

    # ---------------------------------------------------------------- lifecycle
    @property
    def exists(self) -> bool:
        return str(self.path) == ":memory:" or self.path.is_file()

    def _ensure_schema(self) -> None:
        tables = {row[0] for row in self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not tables:
            self.con.executescript(SCHEMA)
            self._set_meta("schema_version", SCHEMA_VERSION)
            self._set_meta("created_at", utc_now_iso())
            return
        found = self._get_meta("schema_version")
        if found == "radar-ledger-v1":
            if self.read_only:
                self.con.close()
                raise RuntimeError(
                    f"{self.path}: this ledger is {found!r} and needs the one-way v1->v2 status-history "
                    "migration, which a read-only handle cannot perform. Run any radar command once "
                    "with write access."
                )
            self._migrate_status_history_key()
            self._set_meta("schema_version", SCHEMA_VERSION)
            found = SCHEMA_VERSION
        if found != SCHEMA_VERSION:
            self.con.close()
            raise RuntimeError(
                f"{self.path}: unsupported radar ledger schema {found!r} (this build requires "
                f"{SCHEMA_VERSION!r}). There is no automatic migration from that version and no data "
                "was modified; rebuild the radar store from source, or point MEDRADAR_RADAR_DIR at a "
                "new directory."
            )
        if self.read_only:
            return
        self.con.executescript(SCHEMA)  # idempotent: adds any table missing from an older build

    def _migrate_status_history_key(self) -> None:
        """v1 -> v2: replace the second-precision composite key with a surrogate key.

        Every existing row is copied forward. The append-only triggers are rebuilt by the
        schema script that runs right after this, so the history stays append-only.
        """
        columns = [row[1] for row in self.con.execute("PRAGMA table_info(observation_status_history)")]
        if "history_id" in columns or not columns:
            return
        self.con.executescript(
            """
            ALTER TABLE observation_status_history RENAME TO observation_status_history_v1;
            CREATE TABLE observation_status_history (
                history_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                observation_id TEXT NOT NULL,
                changed_at     TEXT NOT NULL,
                status         TEXT NOT NULL,
                run_id         TEXT,
                note           TEXT
            );
            INSERT INTO observation_status_history(observation_id, changed_at, status, run_id, note)
                SELECT observation_id, changed_at, status, run_id, note
                FROM observation_status_history_v1 ORDER BY changed_at, observation_id;
            DROP TABLE observation_status_history_v1;
            """
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.con.close()
        except sqlite3.Error:  # pragma: no cover - closing a broken handle must not raise
            pass

    def __enter__(self) -> "ObservationLedger":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def size_bytes(self) -> int:
        return self.path.stat().st_size if self.path.is_file() else 0

    # ------------------------------------------------------------------- meta
    def _get_meta(self, key: str) -> str | None:
        row = self.con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self.con.execute(
            "INSERT INTO meta(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def meta(self, key: str, default: Any = None) -> Any:
        row = self.con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        text = row[0]
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return text

    def set_meta(self, key: str, value: Any) -> None:
        with self._transaction():
            self._set_meta(key, value if isinstance(value, str) else canonical_json(value))

    def get_runtime(self, key: str, default: Any = None) -> Any:
        row = self.con.execute("SELECT value FROM runtime_state WHERE key=?", (key,)).fetchone()
        return _parse_json(row[0], default) if row else default

    def set_runtime(self, key: str, value: Any) -> None:
        with self._transaction():
            self.con.execute(
                "INSERT INTO runtime_state(key, value, updated_at) VALUES(?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, canonical_json(value), utc_now_iso()),
            )

    # -------------------------------------------------------------- transaction
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

    def raw(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self.con.execute(sql, tuple(params)).fetchall()]

    def one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        row = self.con.execute(sql, tuple(params)).fetchone()
        return dict(row) if row is not None else None

    # ------------------------------------------------------------------ runs
    def recover_interrupted_runs(self) -> int:
        """A run left RUNNING by a killed process becomes INTERRUPTED, never 'succeeded'."""
        with self._transaction():
            cursor = self.con.execute(
                "UPDATE sync_run SET status='INTERRUPTED', finished_at=? WHERE status='RUNNING'",
                (utc_now_iso(),),
            )
            return int(cursor.rowcount or 0)

    def start_run(self, source: str, *, trigger: str = "manual", adapter_version: str,
                  host: str | None = None) -> str:
        import os
        import socket

        # Microsecond precision plus the pid: two runs started inside the same second (a fast
        # scheduler cycle, or two threads in a test) must not collide on the run identity.
        run_id = (
            f"{source}:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}:{os.getpid()}"
        )
        state = self.get_source_state(source) or {}
        with self._transaction():
            self.con.execute(
                "INSERT INTO sync_run(run_id, source, trigger, adapter_version, status, started_at,"
                " watermark_before, pid, host) VALUES(?,?,?,?,'RUNNING',?,?,?,?)",
                (run_id, source, trigger, adapter_version, utc_now_iso(),
                 state.get("watermark"), os.getpid(),
                 host or socket.gethostname()),
            )
        return run_id

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        counters: Mapping[str, int] | None = None,
        errors: Iterable[Mapping[str, Any]] = (),
        watermark_after: str | None = None,
    ) -> None:
        with self._transaction():
            row = self.con.execute("SELECT * FROM sync_run WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown run: {run_id}")
            self.con.execute(
                "UPDATE sync_run SET status=?, finished_at=?, counters_json=?, errors_json=?,"
                " watermark_after=? WHERE run_id=?",
                (status, utc_now_iso(), _json(dict(counters or {})), _json(list(errors)),
                 watermark_after, run_id),
            )
            self.con.execute(
                "UPDATE source_state SET last_run_outcome=?, updated_at=? WHERE source_id=?",
                (status, utc_now_iso(), row["source"]),
            )

    def run_row(self, run_id: str) -> dict[str, Any] | None:
        row = self.one("SELECT * FROM sync_run WHERE run_id=?", (run_id,))
        if row is None:
            return None
        row["counters"] = _parse_json(row.pop("counters_json", None), {})
        row["errors"] = _parse_json(row.pop("errors_json", None), [])
        return row

    def recent_runs(self, limit: int = 20, *, source: str | None = None) -> list[dict[str, Any]]:
        if source:
            rows = self.raw(
                "SELECT * FROM sync_run WHERE source=? ORDER BY started_at DESC LIMIT ?",
                (source, int(limit)),
            )
        else:
            rows = self.raw("SELECT * FROM sync_run ORDER BY started_at DESC LIMIT ?", (int(limit),))
        for row in rows:
            row["counters"] = _parse_json(row.pop("counters_json", None), {})
            row["errors"] = _parse_json(row.pop("errors_json", None), [])
        return rows

    def last_resumable_run(self, source: str) -> dict[str, Any] | None:
        return self.one(
            "SELECT * FROM sync_run WHERE source=? AND status IN ('INTERRUPTED','PARTIAL','FAILED')"
            " ORDER BY started_at DESC LIMIT 1",
            (source,),
        )

    def save_checkpoint(self, source: str, run_id: str, scope_id: str, cursor: str | None,
                        records_seen: int = 0) -> None:
        with self._transaction():
            self.con.execute(
                "INSERT INTO sync_checkpoint(source, run_id, scope_id, cursor, records_seen, saved_at)"
                " VALUES(?,?,?,?,?,?)"
                " ON CONFLICT(source, run_id, scope_id) DO UPDATE SET"
                " cursor=excluded.cursor, records_seen=excluded.records_seen, saved_at=excluded.saved_at",
                (source, run_id, scope_id, cursor, int(records_seen), utc_now_iso()),
            )

    def load_checkpoints(self, source: str, run_id: str) -> dict[str, dict[str, Any]]:
        rows = self.raw(
            "SELECT scope_id, cursor, records_seen FROM sync_checkpoint WHERE source=? AND run_id=?",
            (source, run_id),
        )
        return {row["scope_id"]: row for row in rows}

    # ------------------------------------------------------------- source state
    def ensure_source(self, source_id: str, *, label: str, adapter_version: str,
                      cadence_hours: float, access_state: str = "UNVERIFIED",
                      access_reason: str | None = None, enabled: bool = True) -> dict[str, Any]:
        now = utc_now_iso()
        with self._transaction():
            self.con.execute(
                "INSERT INTO source_state(source_id, label, adapter_version, cadence_hours,"
                " access_state, access_reason, enabled, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(source_id) DO UPDATE SET"
                " label=excluded.label, adapter_version=excluded.adapter_version,"
                " cadence_hours=excluded.cadence_hours, access_state=excluded.access_state,"
                " access_reason=excluded.access_reason, enabled=excluded.enabled,"
                " updated_at=excluded.updated_at",
                (source_id, label, adapter_version, float(cadence_hours), access_state,
                 access_reason, 1 if enabled else 0, now, now),
            )
        return self.get_source_state(source_id) or {}

    def get_source_state(self, source_id: str) -> dict[str, Any] | None:
        row = self.one("SELECT * FROM source_state WHERE source_id=?", (source_id,))
        if row is not None:
            row["cursor"] = _parse_json(row.pop("cursor_json", None), {})
        return row

    def list_sources(self) -> list[dict[str, Any]]:
        rows = self.raw("SELECT * FROM source_state ORDER BY source_id")
        for row in rows:
            row["cursor"] = _parse_json(row.pop("cursor_json", None), {})
        return rows

    def set_watermark(self, source_id: str, watermark: Any, cursor: Mapping[str, Any] | None = None) -> None:
        with self._transaction():
            self.con.execute(
                "UPDATE source_state SET watermark=?, cursor_json=?, updated_at=? WHERE source_id=?",
                (None if watermark is None else str(watermark),
                 None if cursor is None else _json(dict(cursor)), utc_now_iso(), source_id),
            )

    def note_source_success(self, source_id: str, *, run_id: str, observed_update: bool = False) -> None:
        now = utc_now_iso()
        with self._transaction():
            self.con.execute(
                "UPDATE source_state SET last_checked_at=?, last_success_check_at=?,"
                " consecutive_failures=0, first_success_at=COALESCE(first_success_at, ?),"
                " first_successful_run_id=COALESCE(first_successful_run_id, ?),"
                " last_observed_update_at=CASE WHEN ? THEN ? ELSE last_observed_update_at END,"
                " updated_at=? WHERE source_id=?",
                (now, now, now, run_id, 1 if observed_update else 0, now, now, source_id),
            )

    def note_source_failure(self, source_id: str, *, run_id: str | None, message: str,
                            kind: str = "FETCH_FAILED", retryable: bool = True,
                            retry_after_at: str | None = None) -> None:
        import hashlib

        now = utc_now_iso()
        failure_id = hashlib.sha256(f"{source_id}|{run_id}|{now}|{message[:120]}".encode()).hexdigest()[:32]
        with self._transaction():
            self.con.execute(
                "INSERT INTO source_failure(failure_id, source, run_id, kind, message, occurred_at,"
                " retryable, retry_after_at) VALUES(?,?,?,?,?,?,?,?)",
                (failure_id, source_id, run_id, kind, message[:2000], now, 1 if retryable else 0,
                 retry_after_at),
            )
            self.con.execute(
                "UPDATE source_state SET last_failure_at=?, last_failure_message=?,"
                " consecutive_failures=consecutive_failures+1, last_checked_at=?, updated_at=?"
                " WHERE source_id=?",
                (now, message[:500], now, now, source_id),
            )

    def failures(self, *, source: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        if source:
            return self.raw(
                "SELECT * FROM source_failure WHERE source=? ORDER BY occurred_at DESC LIMIT ?",
                (source, int(limit)),
            )
        return self.raw("SELECT * FROM source_failure ORDER BY occurred_at DESC LIMIT ?", (int(limit),))

    # ------------------------------------------------------------ observations
    def _phase_for(self, source: str) -> str:
        state = self.get_source_state(source) or {}
        return PHASE_INCREMENTAL if state.get("first_successful_run_id") else PHASE_INITIAL

    def record_observation(
        self,
        record: RawRecord,
        mapping: MappingResult,
        *,
        run_id: str,
        adapter_version: str,
        mapping_version: str = MAPPING_VERSION,
        seen_at: str | None = None,
        origin: str = ORIGIN_LIVE,
        backfill_reason: str | None = None,
        phase: str | None = None,
    ) -> RecordOutcome:
        """Insert or reconcile one observation. Idempotent by construction."""
        if origin not in ORIGINS:
            raise ValueError(f"bad observation origin: {origin!r}")
        if origin == ORIGIN_BACKFILLED and not backfill_reason:
            raise ValueError("a BACKFILLED observation requires a reason; first_observed_at is not faked")
        seen = seen_at or utc_now_iso()
        obs_id = make_observation_id(record.source, record.source_record_id)
        digest = record.payload_hash
        payload_text = canonical_json(record.payload)
        discovered_phase = phase or (PHASE_BACKFILL if origin == ORIGIN_BACKFILLED else self._phase_for(record.source))
        if discovered_phase not in PHASES:
            raise ValueError(f"bad discovery phase: {discovered_phase!r}")
        existing = self.one("SELECT * FROM observation WHERE observation_id=?", (obs_id,))
        site_domain = _domain_of(record.url)

        if existing is None:
            version = make_version_id(obs_id, digest)
            with self._transaction():
                self.con.execute(
                    "INSERT INTO observation(observation_id, source, source_record_id, record_type,"
                    " official_identifier, title, source_url, first_observed_at, ingested_at,"
                    " observation_origin, backfill_reason, discovery_phase, event_at,"
                    " event_at_precision, published_at, published_at_precision, source_updated_at,"
                    " source_updated_at_precision, last_checked_at, last_checked_run_id, content_hash,"
                    " latest_version_id, version_count, observation_status, current_change_state,"
                    " last_change_at, first_seen_run_id, processing_state, processing_updated_at,"
                    " site_domain)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (obs_id, record.source, record.source_record_id, record.record_type,
                     record.official_identifier or record.source_record_id, record.title,
                     record.url, seen, seen, origin,
                     backfill_reason, discovered_phase, record.event_at, record.event_at_precision,
                     record.published_at, record.published_at_precision, record.source_updated_at,
                     record.source_updated_at_precision, seen, run_id, digest, version, 1,
                     STATUS_ACTIVE, CHANGE_NEW, seen, run_id, PROC_RAW, seen, site_domain),
                )
                self.con.execute(
                    "INSERT INTO observation_version(version_id, observation_id, version_seq,"
                    " captured_at, change_state, content_hash, payload, payload_bytes, changed_fields,"
                    " source_updated_at, run_id, adapter_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (version, obs_id, 1, seen, CHANGE_NEW, digest, payload_text,
                     len(payload_text.encode("utf-8")), None, record.source_updated_at, run_id,
                     adapter_version),
                )
                self.con.execute(
                    "INSERT INTO observation_status_history(observation_id, changed_at, status,"
                    " run_id, note) VALUES(?,?,?,?,?)",
                    (obs_id, seen, STATUS_ACTIVE, run_id, "first observation"),
                )
                self._insert_change(obs_id, record.source, CHANGE_NEW, seen, version, None, None,
                                    seen, record, run_id, discovered_phase)
                self._write_mapping(obs_id, mapping, mapping_version, seen, run_id)
                self._write_identifiers(obs_id, record, seen)
            return RecordOutcome(obs_id, CHANGE_NEW, version, None, (), seen, discovered_phase)

        previous_payload = self._latest_payload(obs_id)
        previous_version = existing["latest_version_id"]
        was_removed = existing["observation_status"] == STATUS_REMOVED

        if existing["content_hash"] == digest and not was_removed:
            with self._transaction():
                self.con.execute(
                    "UPDATE observation SET last_checked_at=?, last_checked_run_id=? WHERE observation_id=?",
                    (seen, run_id, obs_id),
                )
                self._write_mapping(obs_id, mapping, mapping_version, seen, run_id)
                self._write_identifiers(obs_id, record, seen)
            return RecordOutcome(obs_id, CHANGE_UNCHANGED, previous_version, previous_version, (),
                                 existing["first_observed_at"], existing["discovery_phase"])

        fields = changed_fields(previous_payload, dict(record.payload))
        if was_removed and not fields:
            # The record reappeared byte-identical: a status restoration, not a new version.
            with self._transaction():
                self.con.execute(
                    "UPDATE observation SET observation_status=?, current_change_state=?,"
                    " last_change_at=?, last_checked_at=?, last_checked_run_id=?, title=?, source_url=?"
                    " WHERE observation_id=?",
                    (STATUS_ACTIVE, CHANGE_UPDATED, seen, seen, run_id, record.title, record.url, obs_id),
                )
                self.con.execute(
                    "INSERT INTO observation_status_history(observation_id, changed_at, status,"
                    " run_id, note) VALUES(?,?,?,?,?)",
                    (obs_id, seen, STATUS_ACTIVE, run_id, "record re-appeared at source"),
                )
                self._insert_change(obs_id, record.source, CHANGE_UPDATED, seen, previous_version,
                                    previous_version, ["status"], existing["first_observed_at"],
                                    record, run_id, existing["discovery_phase"])
                self._write_mapping(obs_id, mapping, mapping_version, seen, run_id)
                self._write_identifiers(obs_id, record, seen)
            return RecordOutcome(obs_id, CHANGE_UPDATED, previous_version, previous_version,
                                 ("status",), existing["first_observed_at"], existing["discovery_phase"])

        fields = fields or (["status"] if was_removed else [])
        version = make_version_id(obs_id, digest)
        seq = int(existing["version_count"]) + 1
        with self._transaction():
            self.con.execute(
                "INSERT INTO observation_version(version_id, observation_id, version_seq,"
                " captured_at, change_state, content_hash, payload, payload_bytes, changed_fields,"
                " source_updated_at, run_id, adapter_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (version, obs_id, seq, seen, CHANGE_UPDATED, digest, payload_text,
                 len(payload_text.encode("utf-8")), _json(fields), record.source_updated_at,
                 run_id, adapter_version),
            )
            self.con.execute(
                "UPDATE observation SET content_hash=?, latest_version_id=?, version_count=?,"
                " observation_status=?, current_change_state=?, last_change_at=?, last_checked_at=?,"
                " last_checked_run_id=?, event_at=?, event_at_precision=?, published_at=?,"
                " published_at_precision=?, source_updated_at=?, source_updated_at_precision=?,"
                " title=?, source_url=?, processing_state=?, site_domain=? WHERE observation_id=?",
                (digest, version, seq, STATUS_ACTIVE, CHANGE_UPDATED, seen, seen, run_id,
                 record.event_at, record.event_at_precision, record.published_at,
                 record.published_at_precision, record.source_updated_at,
                 record.source_updated_at_precision, record.title, record.url, PROC_RAW,
                 site_domain, obs_id),
            )
            if was_removed:
                self.con.execute(
                    "INSERT INTO observation_status_history(observation_id, changed_at, status,"
                    " run_id, note) VALUES(?,?,?,?,?)",
                    (obs_id, seen, STATUS_ACTIVE, run_id, "record re-appeared at source"),
                )
            self._insert_change(obs_id, record.source, CHANGE_UPDATED, seen, version,
                                previous_version, fields, existing["first_observed_at"], record,
                                run_id, existing["discovery_phase"])
            self._write_mapping(obs_id, mapping, mapping_version, seen, run_id)
            self._write_identifiers(obs_id, record, seen)
        return RecordOutcome(obs_id, CHANGE_UPDATED, version, previous_version, tuple(fields),
                             existing["first_observed_at"], existing["discovery_phase"])

    def mark_removed(self, obs_id: str, *, run_id: str, note: str,
                     seen_at: str | None = None) -> bool:
        """Record that the source no longer serves this record - not that it vanished."""
        seen = seen_at or utc_now_iso()
        row = self.one("SELECT * FROM observation WHERE observation_id=?", (obs_id,))
        if row is None:
            raise KeyError(f"unknown observation: {obs_id}")
        if row["observation_status"] == STATUS_REMOVED:
            with self._transaction():
                self.con.execute(
                    "UPDATE observation SET last_checked_at=?, last_checked_run_id=? WHERE observation_id=?",
                    (seen, run_id, obs_id),
                )
            return False
        with self._transaction():
            self.con.execute(
                "UPDATE observation SET observation_status=?, current_change_state=?, last_change_at=?,"
                " last_checked_at=?, last_checked_run_id=? WHERE observation_id=?",
                (STATUS_REMOVED, CHANGE_REMOVED, seen, seen, run_id, obs_id),
            )
            self.con.execute(
                "INSERT INTO observation_status_history(observation_id, changed_at, status, run_id, note)"
                " VALUES(?,?,?,?,?)",
                (obs_id, seen, STATUS_REMOVED, run_id, note),
            )
            self.con.execute(
                "INSERT INTO observation_change(change_id, observation_id, source, change_state,"
                " observed_at, version_id, previous_version_id, changed_fields, first_observed_at,"
                " event_at, event_at_precision, published_at, published_at_precision, record_type,"
                " title, url, run_id, discovery_phase) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (_change_id(obs_id, CHANGE_REMOVED, seen), obs_id, row["source"], CHANGE_REMOVED,
                 seen, None, row["latest_version_id"], _json(["status"]), row["first_observed_at"],
                 row["event_at"], row["event_at_precision"], row["published_at"],
                 row["published_at_precision"], row["record_type"], row["title"], row["source_url"],
                 run_id, row["discovery_phase"]),
            )
        return True

    def mark_fetch_failed(self, obs_id: str, *, run_id: str, message: str,
                          seen_at: str | None = None) -> None:
        """A failed re-check is not evidence of no change; it is its own state."""
        seen = seen_at or utc_now_iso()
        row = self.one("SELECT * FROM observation WHERE observation_id=?", (obs_id,))
        if row is None:
            raise KeyError(f"unknown observation: {obs_id}")
        with self._transaction():
            self.con.execute(
                "INSERT INTO observation_change(change_id, observation_id, source, change_state,"
                " observed_at, version_id, previous_version_id, changed_fields, first_observed_at,"
                " event_at, event_at_precision, published_at, published_at_precision, record_type,"
                " title, url, run_id, discovery_phase) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (_change_id(obs_id, CHANGE_FETCH_FAILED, seen), obs_id, row["source"],
                 CHANGE_FETCH_FAILED, seen, None, row["latest_version_id"], None,
                 row["first_observed_at"], row["event_at"], row["event_at_precision"],
                 row["published_at"], row["published_at_precision"], row["record_type"],
                 row["title"], row["source_url"], run_id, row["discovery_phase"]),
            )
            self.con.execute(
                "UPDATE observation SET last_checked_at=?, last_checked_run_id=? WHERE observation_id=?",
                (seen, run_id, obs_id),
            )

    def touch_checked(self, obs_id: str, *, run_id: str, checked_at: str | None = None) -> None:
        with self._transaction():
            self.con.execute(
                "UPDATE observation SET last_checked_at=?, last_checked_run_id=? WHERE observation_id=?",
                (checked_at or utc_now_iso(), run_id, obs_id),
            )

    # ------------------------------------------------------------------ internals
    def _insert_change(self, obs_id: str, source: str, state: str, observed_at: str,
                       version: str | None, previous: str | None, fields: Sequence[str] | None,
                       first_observed: str, record: RawRecord, run_id: str, phase: str) -> None:
        self.con.execute(
            "INSERT INTO observation_change(change_id, observation_id, source, change_state,"
            " observed_at, version_id, previous_version_id, changed_fields, first_observed_at,"
            " event_at, event_at_precision, published_at, published_at_precision, record_type,"
            " title, url, run_id, discovery_phase) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_change_id(obs_id, state, observed_at), obs_id, source, state, observed_at, version,
             previous, None if fields is None else _json(list(fields)), first_observed,
             record.event_at, record.event_at_precision, record.published_at,
             record.published_at_precision, record.record_type, record.title, record.url, run_id,
             phase),
        )

    def _latest_payload(self, obs_id: str) -> dict[str, Any] | None:
        row = self.con.execute(
            "SELECT payload FROM observation_version WHERE observation_id=?"
            " ORDER BY version_seq DESC LIMIT 1",
            (obs_id,),
        ).fetchone()
        return _parse_json(row[0]) if row else None

    def _write_identifiers(self, obs_id: str, record: RawRecord, seen: str) -> None:
        """Record the official identifiers this observation states.

        Append-only on purpose: a DOI that appeared in a later version stays attached, because
        the earlier version did not become wrong. ``INSERT OR IGNORE`` keeps ``first_seen_at``
        honest - it is the moment MedRadar first read that identifier, not the moment of the
        last check.
        """
        for kind, value in standard_identifiers(record):
            self.con.execute(
                "INSERT OR IGNORE INTO observation_identifier(observation_id, kind, value, source,"
                " first_seen_at) VALUES(?,?,?,?,?)",
                (obs_id, kind, value, record.source, seen),
            )

    def _write_mapping(self, obs_id: str, mapping: MappingResult, mapping_version: str,
                       mapped_at: str, run_id: str | None) -> None:
        # A re-classification that produces byte-identical output is not history worth
        # growing the ledger for; the facet projection is already right.
        latest = self.con.execute(
            "SELECT mapping_version, organization_candidates, product_candidates, technology_topics"
            " FROM observation_mapping WHERE observation_id=? ORDER BY mapped_at DESC LIMIT 1",
            (obs_id,),
        ).fetchone()
        if latest is not None:
            unchanged = (
                latest["mapping_version"] == mapping_version
                and latest["organization_candidates"] == _json(list(mapping.organization_candidates))
                and latest["product_candidates"] == _json(list(mapping.product_candidates))
                and latest["technology_topics"] == _json(list(mapping.technology_topics))
            )
            if unchanged:
                return
        mapping_id = make_version_id(obs_id, f"{mapping_version}|{mapped_at}|{mapping.as_dict()}")
        self.con.execute(
            "INSERT OR IGNORE INTO observation_mapping(mapping_id, observation_id, mapped_at,"
            " mapping_version, organization_candidates, product_candidates, technology_topics, note)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (mapping_id, obs_id, mapped_at, mapping_version,
             _json(list(mapping.organization_candidates)), _json(list(mapping.product_candidates)),
             _json(list(mapping.technology_topics)), mapping.note),
        )
        self.con.execute("DELETE FROM observation_facet WHERE observation_id=?", (obs_id,))
        rows: list[tuple[Any, ...]] = []
        for kind, items in (
            ("organization", mapping.organization_candidates),
            ("product", mapping.product_candidates),
            ("topic", mapping.technology_topics),
        ):
            for item in items:
                value = (
                    item.get("organization_id") or item.get("product_key") or item.get("topic_id")
                )
                if not value:
                    continue
                rows.append((obs_id, kind, str(value), str(item.get("confirmation") or "UNKNOWN"),
                             str(item.get("method") or ""), item.get("confidence")))
        if rows:
            self.con.executemany(
                "INSERT OR REPLACE INTO observation_facet(observation_id, kind, value, confirmation,"
                " method, confidence) VALUES(?,?,?,?,?,?)",
                rows,
            )

    # -------------------------------------------------------------------- reads
    def observation_row(self, obs_id: str) -> dict[str, Any] | None:
        row = self.one("SELECT * FROM observation WHERE observation_id=?", (obs_id,))
        if row is not None:
            row["facets"] = self.facets_for(obs_id)
        return row

    def facets_for(self, obs_id: str) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {"organization": [], "product": [], "topic": []}
        for row in self.raw(
            "SELECT kind, value, confirmation, method, confidence FROM observation_facet"
            " WHERE observation_id=? ORDER BY kind, value",
            (obs_id,),
        ):
            out.setdefault(row["kind"], []).append({
                "value": row["value"],
                "confirmation": row["confirmation"],
                "method": row["method"],
                "confidence": row["confidence"],
            })
        return out

    def identifiers(self, obs_id: str) -> list[dict[str, Any]]:
        """The normalised official identifiers this observation states (PMID, DOI)."""
        return self.raw(
            "SELECT kind, value, source, first_seen_at FROM observation_identifier"
            " WHERE observation_id=? ORDER BY kind, value",
            (obs_id,),
        )

    def identifier_peers(self, kind: str, value: str, *, exclude: str,
                         limit: int = 8) -> list[dict[str, Any]]:
        """Other observations stating the same official identifier.

        This is exact string equality on a *normalised* identifier. It is not a fuzzy match
        and it never consults the title, so title similarity can never create the relation.
        """
        return self.raw(
            "SELECT i.observation_id, i.source, i.first_seen_at FROM observation_identifier i"
            " JOIN observation o ON o.observation_id = i.observation_id"
            " WHERE i.kind=? AND i.value=? AND i.observation_id<>?"
            " ORDER BY i.observation_id LIMIT ?",
            (kind, value, exclude, int(limit)),
        )

    def versions(self, obs_id: str) -> list[dict[str, Any]]:
        rows = self.raw(
            "SELECT version_id, version_seq, captured_at, change_state, content_hash, changed_fields,"
            " payload, adapter_version, run_id FROM observation_version WHERE observation_id=?"
            " ORDER BY version_seq",
            (obs_id,),
        )
        for row in rows:
            row["changed_fields"] = _parse_json(row.get("changed_fields"), [])
            row["payload"] = _parse_json(row.get("payload"), {})
        return rows

    def changes_for(self, obs_id: str) -> list[dict[str, Any]]:
        rows = self.raw(
            "SELECT * FROM observation_change WHERE observation_id=? ORDER BY observed_at",
            (obs_id,),
        )
        for row in rows:
            row["changed_fields"] = _parse_json(row.get("changed_fields"), [])
        return rows

    def mapping_history(self, obs_id: str) -> list[dict[str, Any]]:
        rows = self.raw(
            "SELECT * FROM observation_mapping WHERE observation_id=? ORDER BY mapped_at",
            (obs_id,),
        )
        for row in rows:
            for key in ("organization_candidates", "product_candidates", "technology_topics"):
                row[key] = _parse_json(row.get(key), [])
        return rows

    # --------------------------------------------------------------------- feed
    def feed(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        sources: Sequence[str] | None = None,
        organizations: Sequence[str] | None = None,
        topics: Sequence[str] | None = None,
        change_states: Sequence[str] | None = None,
        confirmations: Sequence[str] | None = None,
        published_from: str | None = None,
        published_to: str | None = None,
        observed_from: str | None = None,
        observed_to: str | None = None,
        record_types: Sequence[str] | None = None,
        phases: Sequence[str] | None = None,
        search: str | None = None,
        order: str = "observed",
    ) -> tuple[list[dict[str, Any]], int]:
        where: list[str] = []
        params: list[Any] = []
        joins: list[str] = []
        if sources:
            where.append(f"o.source IN ({','.join('?' * len(sources))})")
            params.extend(sources)
        if record_types:
            where.append(f"o.record_type IN ({','.join('?' * len(record_types))})")
            params.extend(record_types)
        if change_states:
            where.append(f"o.current_change_state IN ({','.join('?' * len(change_states))})")
            params.extend(change_states)
        if phases:
            where.append(f"o.discovery_phase IN ({','.join('?' * len(phases))})")
            params.extend(phases)
        if published_from:
            where.append("COALESCE(o.published_at, o.event_at, '') >= ?")
            params.append(published_from)
        if published_to:
            where.append("COALESCE(o.published_at, o.event_at, '') <= ?")
            params.append(published_to)
        if observed_from:
            where.append("o.first_observed_at >= ?")
            params.append(observed_from)
        if observed_to:
            where.append("o.first_observed_at <= ?")
            params.append(observed_to)
        if search:
            where.append("(o.title LIKE ? OR o.official_identifier LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        facet_conditions: list[str] = []
        if organizations:
            joins.append("JOIN observation_facet f_org ON f_org.observation_id = o.observation_id AND f_org.kind='organization'")
            facet_conditions.append(f"f_org.value IN ({','.join('?' * len(organizations))})")
            params.extend(organizations)
        if topics:
            joins.append("JOIN observation_facet f_topic ON f_topic.observation_id = o.observation_id AND f_topic.kind='topic'")
            facet_conditions.append(f"f_topic.value IN ({','.join('?' * len(topics))})")
            params.extend(topics)
        if confirmations:
            placeholders = ",".join("?" * len(confirmations))
            if organizations and topics:
                facet_conditions.append(
                    f"(f_org.confirmation IN ({placeholders}) OR f_topic.confirmation IN ({placeholders}))"
                )
            elif organizations:
                facet_conditions.append(f"f_org.confirmation IN ({placeholders})")
            elif topics:
                facet_conditions.append(f"f_topic.confirmation IN ({placeholders})")
            else:
                joins.append("JOIN observation_facet f_any ON f_any.observation_id = o.observation_id")
                facet_conditions.append(f"f_any.confirmation IN ({placeholders})")
            params.extend(confirmations)
            if organizations and topics:
                params.extend(confirmations)
        where.extend(facet_conditions)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        join_sql = " ".join(joins)
        order_sql = {
            "observed": "o.first_observed_at DESC, o.observation_id",
            "published": "COALESCE(o.published_at, o.event_at) DESC, o.observation_id",
            "event": "COALESCE(o.event_at, o.published_at) DESC, o.observation_id",
        }.get(order, "o.first_observed_at DESC, o.observation_id")
        base = f"FROM observation o {join_sql}{clause}"
        total = int(self.con.execute(f"SELECT COUNT(DISTINCT o.observation_id) {base}", tuple(params)).fetchone()[0])
        rows = self.raw(
            f"SELECT DISTINCT o.* {base} ORDER BY {order_sql} LIMIT ? OFFSET ?",
            (*params, int(limit), int(offset)),
        )
        for row in rows:
            row["facets"] = self.facets_for(row["observation_id"])
            row["latest_version_changed_fields"] = self._latest_changed_fields(row["observation_id"])
        return rows, total

    def _latest_changed_fields(self, obs_id: str) -> list[str]:
        row = self.con.execute(
            "SELECT changed_fields FROM observation_version WHERE observation_id=?"
            " ORDER BY version_seq DESC LIMIT 1",
            (obs_id,),
        ).fetchone()
        return _parse_json(row[0], []) if row else []

    def existing_record_ids(self, source: str, record_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Map ``source_record_id`` -> a small head projection, for the ids that exist.

        Adapters use this to avoid re-requesting a page they already hold. It reads only the
        mutable head table and never creates an observation.
        """
        ids = [str(value) for value in record_ids if value]
        if not ids:
            return {}
        found: dict[str, dict[str, Any]] = {}
        chunk = 400
        for start in range(0, len(ids), chunk):
            batch = ids[start:start + chunk]
            rows = self.raw(
                "SELECT observation_id, source_record_id, first_observed_at, source_updated_at,"
                " content_hash, observation_status FROM observation WHERE source=?"
                f" AND source_record_id IN ({','.join('?' * len(batch))})",
                (source, *batch),
            )
            for row in rows:
                found[row["source_record_id"]] = row
        return found

    def known_source_records(self, source: str, *, limit: int = 5000) -> dict[str, dict[str, Any]]:
        rows = self.raw(
            "SELECT observation_id, source_record_id, source_updated_at, first_observed_at,"
            " content_hash, observation_status FROM observation WHERE source=? LIMIT ?",
            (source, int(limit)),
        )
        return {row["source_record_id"]: row for row in rows}

    def feed_facets(self, *, limit: int = 40) -> dict[str, Any]:
        orgs = self.raw(
            "SELECT f.value AS organization_id, f.confirmation, COUNT(*) AS n"
            " FROM observation_facet f WHERE f.kind='organization'"
            " GROUP BY f.value, f.confirmation ORDER BY n DESC LIMIT ?",
            (int(limit),),
        )
        topics = self.raw(
            "SELECT f.value AS topic_id, f.confirmation, COUNT(*) AS n"
            " FROM observation_facet f WHERE f.kind='topic'"
            " GROUP BY f.value, f.confirmation ORDER BY n DESC LIMIT ?",
            (int(limit),),
        )
        sources = self.raw(
            "SELECT source, COUNT(*) AS n, MAX(first_observed_at) AS newest"
            " FROM observation GROUP BY source ORDER BY n DESC",
        )
        return {"organizations": orgs, "topics": topics, "sources": sources}

    def counts(self) -> LedgerCounts:
        def scalar(sql: str) -> int:
            return int(self.con.execute(sql).fetchone()[0])

        return LedgerCounts(
            observations=scalar("SELECT COUNT(*) FROM observation"),
            sources=scalar("SELECT COUNT(*) FROM source_state"),
            change_events=scalar("SELECT COUNT(*) FROM observation_change"),
            versions=scalar("SELECT COUNT(*) FROM observation_version"),
            ai_candidates=scalar("SELECT COUNT(*) FROM ai_candidate"),
            queue_pending=scalar("SELECT COUNT(*) FROM processing_queue WHERE state='PENDING'"),
            graph_materialized=scalar("SELECT COUNT(*) FROM graph_materialization"),
        )

    def change_counts(self) -> dict[str, int]:
        return {
            row["change_state"]: int(row["n"])
            for row in self.raw(
                "SELECT change_state, COUNT(*) AS n FROM observation_change GROUP BY change_state"
            )
        }

    def recent_changes(self, limit: int = 20, *, states: Sequence[str] | None = None) -> list[dict[str, Any]]:
        states = states or list(CHANGE_STATES)
        rows = self.raw(
            f"SELECT * FROM observation_change WHERE change_state IN ({','.join('?' * len(states))})"
            " ORDER BY observed_at DESC, change_id LIMIT ?",
            (*states, int(limit)),
        )
        for row in rows:
            row["changed_fields"] = _parse_json(row.get("changed_fields"), [])
        return rows

    # -------------------------------------------------------------- processing
    def set_processing_state(self, obs_id: str, state: str) -> None:
        if state not in PROCESSING_STATES:
            raise ValueError(f"bad processing state: {state!r}")
        with self._transaction():
            self.con.execute(
                "UPDATE observation SET processing_state=?, processing_updated_at=? WHERE observation_id=?",
                (state, utc_now_iso(), obs_id),
            )

    def observations_needing_mapping(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.raw(
            "SELECT o.observation_id, o.source, o.record_type, o.title, o.first_observed_at,"
            " o.latest_version_id, o.processing_state FROM observation o"
            " WHERE o.processing_state IN ('RAW','CLASSIFIED') ORDER BY o.first_observed_at LIMIT ?",
            (int(limit),),
        )

    def observations_with_stale_mapping(self, rules_version: str,
                                        limit: int = 200) -> list[dict[str, Any]]:
        """Observations whose latest classification predates the current rule version.

        This is what makes a rule edit a *version change*: the next ``advance`` re-derives the
        mapping for every affected record, whatever its processing state, and invalidates the
        derived graph projection for it.
        """
        return self.raw(
            "SELECT o.observation_id, o.source, o.record_type, o.title, o.first_observed_at,"
            " o.latest_version_id, o.processing_state FROM observation o"
            " WHERE COALESCE((SELECT m.mapping_version FROM observation_mapping m"
            "   WHERE m.observation_id = o.observation_id"
            "   ORDER BY m.mapped_at DESC LIMIT 1), '') <> ?"
            " ORDER BY o.first_observed_at LIMIT ?",
            (str(rules_version), int(limit)),
        )

    def pending_ai(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.raw(
            "SELECT observation_id, title, record_type, source FROM observation"
            " WHERE processing_state='AI_PENDING' ORDER BY first_observed_at LIMIT ?",
            (int(limit),),
        )

    # -------------------------------------------------------------- AI backlog
    def enqueue_task(self, observation_id: str, *, version_id: str | None, kind: str,
                     priority: int = 100) -> str:
        import hashlib

        task_id = hashlib.sha256(f"{observation_id}|{kind}|{version_id or ''}".encode()).hexdigest()[:32]
        now = utc_now_iso()
        with self._transaction():
            self.con.execute(
                "INSERT INTO processing_queue(task_id, observation_id, version_id, kind, state,"
                " attempts, priority, created_at, updated_at) VALUES(?,?,?,?, 'PENDING',0,?,?,?)"
                " ON CONFLICT(task_id) DO UPDATE SET updated_at=excluded.updated_at",
                (task_id, observation_id, version_id, kind, int(priority), now, now),
            )
        return task_id

    def claim_tasks(self, *, kind: str = "ai_enrichment", limit: int = 8) -> list[dict[str, Any]]:
        """Atomically claim a batch. A crashed claim is recoverable via ``release_stale_claims``."""
        now = utc_now_iso()
        with self._transaction():
            rows = self.raw(
                "SELECT task_id, observation_id, version_id, attempts FROM processing_queue"
                " WHERE state='PENDING' AND kind=? AND (next_attempt_at IS NULL OR next_attempt_at<=?)"
                " ORDER BY priority, created_at LIMIT ?",
                (kind, now, int(limit)),
            )
            for row in rows:
                self.con.execute(
                    "UPDATE processing_queue SET state='RUNNING', claimed_at=?, updated_at=?,"
                    " attempts=attempts+1 WHERE task_id=?",
                    (now, now, row["task_id"]),
                )
        return rows

    def release_stale_claims(self, *, older_than_seconds: int = 1800) -> int:
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        with self._transaction():
            cursor = self.con.execute(
                "UPDATE processing_queue SET state='PENDING', claimed_at=NULL, updated_at=?,"
                " last_error=COALESCE(last_error,'claim expired without a result')"
                " WHERE state='RUNNING' AND claimed_at IS NOT NULL AND claimed_at < ?",
                (utc_now_iso(), cutoff),
            )
            return int(cursor.rowcount or 0)

    def finish_task(self, task_id: str, *, state: str = "DONE", error: str | None = None,
                    retry_after_at: str | None = None) -> None:
        with self._transaction():
            self.con.execute(
                "UPDATE processing_queue SET state=?, finished_at=?, updated_at=?, last_error=?,"
                " next_attempt_at=? WHERE task_id=?",
                (state, utc_now_iso(), utc_now_iso(), error, retry_after_at, task_id),
            )

    def defer_task(self, task_id: str, *, reason: str, retry_after_at: str | None) -> None:
        with self._transaction():
            self.con.execute(
                "UPDATE processing_queue SET state='DEFERRED', updated_at=?, last_error=?,"
                " next_attempt_at=? WHERE task_id=?",
                (utc_now_iso(), reason, retry_after_at, task_id),
            )

    def queue_summary(self) -> dict[str, Any]:
        rows = self.raw("SELECT state, COUNT(*) AS n FROM processing_queue GROUP BY state")
        by_state = {row["state"]: int(row["n"]) for row in rows}
        pending = int(self.con.execute(
            "SELECT COUNT(*) FROM processing_queue WHERE state IN ('PENDING','DEFERRED')"
        ).fetchone()[0])
        running = int(self.con.execute(
            "SELECT COUNT(*) FROM processing_queue WHERE state='RUNNING'"
        ).fetchone()[0])
        return {
            "by_state": by_state,
            "backlog": pending,
            "running": running,
            "total": sum(by_state.values()),
        }

    def record_ai_candidate(self, *, observation_id: str, version_id: str | None, model_id: str,
                            model_version: str, prompt_version: str, payload: Mapping[str, Any],
                            validation: Mapping[str, Any], validation_state: str) -> str:
        import hashlib

        candidate_id = hashlib.sha256(
            canonical_json([observation_id, version_id, model_id, payload]).encode()
        ).hexdigest()[:32]
        with self._transaction():
            self.con.execute(
                "INSERT OR IGNORE INTO ai_candidate(candidate_id, observation_id, version_id,"
                " model_id, model_version, prompt_version, created_at, payload, validation,"
                " validation_state) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (candidate_id, observation_id, version_id, model_id, model_version, prompt_version,
                 utc_now_iso(), _json(dict(payload)), _json(dict(validation)), validation_state),
            )
        return candidate_id

    def ai_candidates(self, *, observation_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if observation_id:
            rows = self.raw(
                "SELECT * FROM ai_candidate WHERE observation_id=? ORDER BY created_at DESC LIMIT ?",
                (observation_id, int(limit)),
            )
        else:
            rows = self.raw("SELECT * FROM ai_candidate ORDER BY created_at DESC LIMIT ?", (int(limit),))
        for row in rows:
            row["payload"] = _parse_json(row.get("payload"), {})
            row["validation"] = _parse_json(row.get("validation"), {})
        return rows

    def ai_stats(self) -> dict[str, Any]:
        total = int(self.con.execute("SELECT COUNT(*) FROM ai_candidate").fetchone()[0])
        states = {
            row["validation_state"]: int(row["n"])
            for row in self.raw(
                "SELECT validation_state, COUNT(*) AS n FROM ai_candidate GROUP BY validation_state"
            )
        }
        return {"candidates": total, "by_validation_state": states}

    # ----------------------------------------------------------------- graph sync
    def graph_pending(self, *, graph_version: str, limit: int = 500) -> list[dict[str, Any]]:
        return self.raw(
            "SELECT o.observation_id, o.latest_version_id, o.source, o.record_type, o.title,"
            " o.source_url, o.first_observed_at, o.event_at, o.published_at, o.observation_status,"
            " o.official_identifier, o.content_hash"
            " FROM observation o LEFT JOIN graph_materialization g"
            "   ON g.observation_id = o.observation_id"
            " WHERE g.observation_id IS NULL OR g.version_id <> o.latest_version_id"
            " ORDER BY o.first_observed_at LIMIT ?",
            (int(limit),),
        )

    def mark_graph_materialized(self, observation_id: str, *, version_id: str, graph_version: str,
                                assertions: int) -> None:
        with self._transaction():
            self.con.execute(
                "INSERT INTO graph_materialization(observation_id, version_id, graph_version,"
                " assertions, materialized_at) VALUES(?,?,?,?,?)"
                " ON CONFLICT(observation_id) DO UPDATE SET version_id=excluded.version_id,"
                " graph_version=excluded.graph_version, assertions=excluded.assertions,"
                " materialized_at=excluded.materialized_at",
                (observation_id, version_id, graph_version, int(assertions), utc_now_iso()),
            )

    def invalidate_graph(self, observation_id: str) -> None:
        """Mark the graph projection of one observation stale.

        Called when the rule layer changes: the graph is a derived projection, so re-running
        ``advance`` must be able to re-materialise an observation whose payload did not change.
        """
        with self._transaction():
            self.con.execute("DELETE FROM graph_materialization WHERE observation_id=?",
                             (observation_id,))

    def graph_summary(self) -> dict[str, Any]:
        return {
            "materialized": int(self.con.execute("SELECT COUNT(*) FROM graph_materialization").fetchone()[0]),
            "assertions": int(self.con.execute(
                "SELECT COALESCE(SUM(assertions),0) FROM graph_materialization"
            ).fetchone()[0]),
            "latest_materialization": self.one(
                "SELECT MAX(materialized_at) AS at FROM graph_materialization"
            ),
        }

    # ------------------------------------------------------------------- health
    def consistency_check(self) -> dict[str, Any]:
        problems: list[dict[str, Any]] = []
        orphan_versions = int(self.con.execute(
            "SELECT COUNT(*) FROM observation_version v LEFT JOIN observation o"
            " ON o.observation_id = v.observation_id WHERE o.observation_id IS NULL"
        ).fetchone()[0])
        if orphan_versions:
            problems.append({"kind": "orphan_versions", "count": orphan_versions})
        orphan_changes = int(self.con.execute(
            "SELECT COUNT(*) FROM observation_change c LEFT JOIN observation o"
            " ON o.observation_id = c.observation_id WHERE o.observation_id IS NULL"
        ).fetchone()[0])
        if orphan_changes:
            problems.append({"kind": "orphan_changes", "count": orphan_changes})
        broken_chain = int(self.con.execute(
            "SELECT COUNT(*) FROM observation o WHERE o.latest_version_id NOT IN"
            " (SELECT version_id FROM observation_version WHERE observation_id = o.observation_id)"
        ).fetchone()[0])
        if broken_chain:
            problems.append({"kind": "latest_version_missing", "count": broken_chain})
        changed_first_observed = int(self.con.execute(
            "SELECT COUNT(*) FROM observation o JOIN observation_version v"
            " ON v.observation_id = o.observation_id AND v.version_seq = 1"
            " WHERE v.captured_at <> o.first_observed_at"
        ).fetchone()[0])
        if changed_first_observed:
            problems.append({"kind": "first_observed_at_drift", "count": changed_first_observed})
        unchanged_rows = int(self.con.execute(
            "SELECT COUNT(*) FROM observation_change WHERE change_state='UNCHANGED'"
        ).fetchone()[0])
        if unchanged_rows:
            problems.append({"kind": "unchanged_stored_as_change", "count": unchanged_rows})
        backfill_without_reason = int(self.con.execute(
            "SELECT COUNT(*) FROM observation WHERE observation_origin='BACKFILLED'"
            " AND (backfill_reason IS NULL OR backfill_reason='')"
        ).fetchone()[0])
        if backfill_without_reason:
            problems.append({"kind": "backfill_without_reason", "count": backfill_without_reason})
        watermark_ahead = int(self.con.execute(
            "SELECT COUNT(*) FROM source_state s WHERE s.watermark IS NOT NULL AND NOT EXISTS ("
            "  SELECT 1 FROM sync_run r WHERE r.source = s.source_id AND r.status IN ('OK','PARTIAL')"
            " )"
        ).fetchone()[0])
        if watermark_ahead:
            problems.append({"kind": "watermark_without_successful_run", "count": watermark_ahead})
        return {
            "ok": not problems,
            "problems": problems,
            "counts": {
                "observations": int(self.con.execute("SELECT COUNT(*) FROM observation").fetchone()[0]),
                "versions": int(self.con.execute("SELECT COUNT(*) FROM observation_version").fetchone()[0]),
                "changes": int(self.con.execute("SELECT COUNT(*) FROM observation_change").fetchone()[0]),
                "mappings": int(self.con.execute("SELECT COUNT(*) FROM observation_mapping").fetchone()[0]),
            },
        }

    # ---------------------------------------------------------------------- lock
    def lock(self, *, timeout_seconds: float = 0.0) -> PipelineLock:
        return PipelineLock(self.path.with_suffix(self.path.suffix + ".lock"),
                            timeout_seconds=timeout_seconds)


def _change_id(obs_id: str, state: str, observed_at: str) -> str:
    import hashlib

    return hashlib.sha256(f"{obs_id}|{state}|{observed_at}".encode()).hexdigest()[:32]


def _domain_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        from urllib.parse import urlsplit

        host = urlsplit(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:  # pragma: no cover - malformed URL must not break an ingest
        return None
