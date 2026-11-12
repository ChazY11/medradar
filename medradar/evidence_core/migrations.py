"""Versioned, idempotent, transactional migrations for Evidence Core v1.

``schema_version`` is the application schema ledger (not SQLite's internal
``PRAGMA schema_version`` cookie): one row per applied migration with its name,
checksum and ``applied_at``. The runner:

1. bootstraps ``schema_version`` if missing;
2. refuses to continue when an already-applied migration's checksum changed
   (editing history is an error, not a silent divergence);
3. applies each pending migration in its own transaction — a failing migration
   leaves no partial DDL/data and is not recorded;
4. is re-runnable: a second call on a migrated database is a no-op.

Migration 2 is a Python data migration (baseline seeding) because SQLite has no
``sha256``. Its checksum is therefore derived from its stable identity
(version + name) and the SQL migration checksum covers the exact DDL text.

Boundary: this is schema/data versioning, not tamper-proofing. A database owner
can delete ``schema_version`` rows or the whole file; the runner cannot stop it.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from .ledger import (
    EVENT_SNAPSHOT_FIELDS,
    content_hash,
    snapshot_of_row,
)

SCHEMA_TABLE = "schema_version"

GUARD_TRIGGERS = (
    "event_revision_no_update",
    "event_revision_no_delete",
    "event_revision_no_resubmit",
)

_TRIGGER_SQL = (
    """
    CREATE TRIGGER IF NOT EXISTS event_revision_no_update
    BEFORE UPDATE ON event_revision
    BEGIN
        SELECT RAISE(ABORT, 'event_revision is append-only: UPDATE rejected');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS event_revision_no_delete
    BEFORE DELETE ON event_revision
    BEGIN
        SELECT RAISE(ABORT, 'event_revision is append-only: DELETE rejected');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS event_revision_no_resubmit
    BEFORE INSERT ON event_revision
    WHEN EXISTS (
        SELECT 1 FROM event_revision
        WHERE event_id = NEW.event_id AND version = NEW.version
    )
    BEGIN
        SELECT RAISE(ABORT, 'event_revision is append-only: revision already recorded');
    END
    """,
)

_V1_SQL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS event_revision (
        event_id           TEXT    NOT NULL,
        version            INTEGER NOT NULL CHECK (version >= 1),
        snapshot           TEXT    NOT NULL,            -- canonical JSON of the full events row
        content_hash       TEXT    NOT NULL,            -- sha256 over content fields (not volatile)
        prev_content_hash  TEXT,                        -- NULL for version 1
        revision_reason    TEXT    NOT NULL,
        source             TEXT    NOT NULL,
        origin             TEXT    NOT NULL CHECK (origin IN ('live', 'legacy_baseline')),
        history_completeness TEXT  NOT NULL CHECK (history_completeness IN
                                   ('complete', 'partial_before_ledger', 'baseline_only')),
        recorded_at        TEXT    NOT NULL,            -- when this revision was recorded (UTC)
        first_seen_at      TEXT    NOT NULL,            -- MIN first_seen_at known at this revision
        available_at       TEXT,
        timestamp_quality  TEXT,
        PRIMARY KEY (event_id, version)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_event_revision_recorded_at ON event_revision(recorded_at)",
    "CREATE INDEX IF NOT EXISTS idx_event_revision_source ON event_revision(source)",
    "CREATE INDEX IF NOT EXISTS idx_events_available_at ON events(available_at)",
    *_TRIGGER_SQL,
)


def _utc_moment() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: tuple[str, ...] = ()
    apply: Callable[[sqlite3.Connection], dict[str, Any]] | None = field(default=None, compare=False)

    @property
    def checksum(self) -> str:
        if self.sql:
            return hashlib.sha256("\n".join(self.sql).encode("utf-8")).hexdigest()
        return hashlib.sha256(f"{self.version}:{self.name}:python-callable".encode("utf-8")).hexdigest()


BASELINE_REASON = "legacy baseline: one snapshot at migration time; pre-ledger history unavailable"


def _seed_legacy_baseline(conn: sqlite3.Connection) -> dict[str, Any]:
    """Seed exactly one ``origin='legacy_baseline'`` revision per existing event.

    Rows that already have any revision are left alone (re-run safety). The
    baseline snapshot is the *current* row; ``recorded_at`` is the migration
    moment, and ``history_completeness='baseline_only'`` states that no earlier
    history exists. Nothing is back-dated, nothing is invented.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    if "event_id" not in columns:
        return {"events_scanned": 0, "baseline_inserted": 0, "already_revisioned": 0,
                "note": "events table absent"}
    existing = {str(row[0]) for row in conn.execute("SELECT DISTINCT event_id FROM event_revision")}
    recorded_at = _utc_moment()
    inserted = 0
    scanned = 0
    for row in conn.execute("SELECT * FROM events ORDER BY event_id"):
        scanned += 1
        event_id = str(row["event_id"])
        if event_id in existing:
            continue
        snapshot = snapshot_of_row(row, EVENT_SNAPSHOT_FIELDS)
        # The row may predate some timing columns (the DB forward-migration runs
        # first); absent columns stay null rather than being guessed.
        digest = content_hash(snapshot)
        conn.execute(
            "INSERT INTO event_revision("
            " event_id, version, snapshot, content_hash, prev_content_hash, revision_reason,"
            " source, origin, history_completeness, recorded_at, first_seen_at, available_at,"
            " timestamp_quality) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                event_id, 1, json.dumps(
                    {field: snapshot.get(field) for field in EVENT_SNAPSHOT_FIELDS},
                    sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
                ),
                digest, None, BASELINE_REASON, str(snapshot.get("source") or ""),
                "legacy_baseline", "baseline_only", recorded_at,
                snapshot.get("first_seen_at") or "",
                snapshot.get("available_at"), snapshot.get("timestamp_quality"),
            ),
        )
        inserted += 1
    return {"events_scanned": scanned, "baseline_inserted": inserted,
            "already_revisioned": len(existing), "recorded_at": recorded_at}


MIGRATIONS: tuple[Migration, ...] = (
    Migration(version=1, name="evidence_core_init", sql=_V1_SQL),
    Migration(version=2, name="legacy_baseline_seed", apply=_seed_legacy_baseline),
)

LATEST_VERSION = max(migration.version for migration in MIGRATIONS)


@contextmanager
def _transaction(conn: sqlite3.Connection, label: str) -> Iterator[None]:
    """Use a savepoint when the caller already opened a transaction."""
    if conn.in_transaction:
        conn.execute(f"SAVEPOINT {label}")
        try:
            yield
        except Exception:
            conn.execute(f"ROLLBACK TO {label}")
            conn.execute(f"RELEASE {label}")
            raise
        else:
            conn.execute(f"RELEASE {label}")
    else:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()


def _bootstrap(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA_TABLE} (
            version    INTEGER PRIMARY KEY,
            name       TEXT    NOT NULL,
            checksum   TEXT    NOT NULL,
            applied_at TEXT    NOT NULL
        )
        """
    )


def current_version(conn: sqlite3.Connection) -> int:
    _bootstrap(conn)
    row = conn.execute(f"SELECT MAX(version) FROM {SCHEMA_TABLE}").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def applied_migrations(conn: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    _bootstrap(conn)
    return {
        int(row["version"]): dict(row)
        for row in conn.execute(
            f"SELECT version, name, checksum, applied_at FROM {SCHEMA_TABLE} ORDER BY version"
        )
    }


def ensure_schema(conn: sqlite3.Connection) -> dict[str, Any]:
    """Apply pending migrations. Idempotent, transactional and re-runnable."""
    _bootstrap(conn)
    applied = applied_migrations(conn)
    report: dict[str, Any] = {
        "schema_version_before": max(applied) if applied else 0,
        "schema_version_after": max(applied) if applied else 0,
        "applied_now": [],
        "skipped": [],
        "details": {},
    }
    for known_version, row in sorted(applied.items()):
        migration = next((m for m in MIGRATIONS if m.version == known_version), None)
        if migration is None:
            raise RuntimeError(
                f"{SCHEMA_TABLE} records unknown migration {known_version} ({row['name']}); "
                "this build cannot safely continue"
            )
        if row["checksum"] != migration.checksum:
            raise RuntimeError(
                f"migration {known_version} ({migration.name}) checksum mismatch: "
                f"applied={row['checksum'][:16]}… expected={migration.checksum[:16]}…; "
                "editing an applied migration is an error"
            )
        report["skipped"].append(known_version)

    pending = [m for m in MIGRATIONS if m.version not in applied]
    for migration in pending:
        with _transaction(conn, f"evidence_core_v{migration.version}"):
            detail: dict[str, Any] = {}
            for statement in migration.sql:
                conn.execute(statement)
            if migration.apply is not None:
                detail = migration.apply(conn) or {}
            conn.execute(
                f"INSERT INTO {SCHEMA_TABLE}(version, name, checksum, applied_at) VALUES (?,?,?,?)",
                (migration.version, migration.name, migration.checksum, _utc_moment()),
            )
        report["applied_now"].append(migration.version)
        report["details"][migration.name] = detail
    report["schema_version_after"] = current_version(conn)
    return report


def verify_guards(conn: sqlite3.Connection) -> dict[str, Any]:
    """Report which append-only triggers are present (read-only)."""
    present = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
    }
    missing = [name for name in GUARD_TRIGGERS if name not in present]
    return {"present": sorted(name for name in GUARD_TRIGGERS if name in present),
            "missing": missing, "ok": not missing}


def reinstall_guards(conn: sqlite3.Connection) -> dict[str, Any]:
    """Recreate dropped append-only triggers (no-op when present).

    Exposed because the migration runner will not re-run migration 1 after a
    trigger is dropped; an operator who suspects tampering must be able to
    restore the guards explicitly. This cannot prove they were never dropped.
    """
    for statement in _TRIGGER_SQL:
        conn.execute(statement)
    conn.commit()
    return verify_guards(conn)
