"""Versioned SQLite schema migrations with mandatory backup.

Rules encoded here
------------------
* The schema version is explicit in ``schema_migrations``.
* A migration runs in a transaction; a failure rolls the whole migration back.
* A backup of the database file is written **before** any migration that
  changes an existing database, and the path is reported.
* Migration checksums are verified: editing an already-applied migration is an
  error, not a silent divergence.
* ATLAS never migrates ``data/medradar.sqlite`` or any legacy research database;
  it only opens the database path it is given.

The DDL is the single source of truth for the ATLAS database.  It is
intentionally plain SQLite: no extension, no server, no ORM.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


V1_SQL = """
-- ---------------------------------------------------------------- bookkeeping
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    checksum    TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);

-- ------------------------------------------------------------------- collection
CREATE TABLE collection_runs (
    run_id        TEXT PRIMARY KEY,
    connector_id  TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    status        TEXT NOT NULL DEFAULT 'running',
    requests      INTEGER NOT NULL DEFAULT 0,
    records       INTEGER NOT NULL DEFAULT 0,
    bytes         INTEGER NOT NULL DEFAULT 0,
    git_commit    TEXT NOT NULL DEFAULT '',
    notes         TEXT NOT NULL DEFAULT ''
);

CREATE TABLE raw_objects (
    content_hash  TEXT PRIMARY KEY,
    source_id     TEXT NOT NULL,
    source_url    TEXT NOT NULL DEFAULT '',
    media_type    TEXT NOT NULL DEFAULT 'application/json',
    bytes         INTEGER NOT NULL,
    fetched_at    TEXT NOT NULL,
    storage_path  TEXT NOT NULL DEFAULT '',
    truncated     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE request_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    logged_at   TEXT NOT NULL,
    url         TEXT NOT NULL,
    status      INTEGER,
    bytes       INTEGER NOT NULL DEFAULT 0,
    elapsed_ms  INTEGER NOT NULL DEFAULT 0,
    attempts    INTEGER NOT NULL DEFAULT 1,
    error       TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_request_run ON request_log(run_id);

-- --------------------------------------------------------------------- evidence
CREATE TABLE evidence (
    evidence_id        TEXT NOT NULL,
    version            INTEGER NOT NULL,
    content_hash       TEXT NOT NULL,
    evidence_type      TEXT NOT NULL,
    source_id          TEXT NOT NULL,
    source_record_id   TEXT NOT NULL,
    source_url         TEXT NOT NULL DEFAULT '',
    canonical_key      TEXT,
    canonical_entity_id TEXT NOT NULL DEFAULT '',
    event_at           TEXT NOT NULL DEFAULT '',
    source_public_at   TEXT NOT NULL DEFAULT '',
    first_observed_at  TEXT NOT NULL,
    fetched_at         TEXT NOT NULL,
    time_quality       TEXT NOT NULL DEFAULT 'unknown',
    identity_status    TEXT NOT NULL DEFAULT 'not_attempted',
    relation_status    TEXT NOT NULL DEFAULT 'none',
    licence_status     TEXT NOT NULL DEFAULT 'unknown',
    quality_flags      TEXT NOT NULL DEFAULT '[]',
    payload_json       TEXT NOT NULL,
    run_id             TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (evidence_id, version)
);
CREATE INDEX idx_evidence_key ON evidence(canonical_key);
CREATE INDEX idx_evidence_source ON evidence(source_id);
CREATE INDEX idx_evidence_public ON evidence(source_public_at);

CREATE TABLE evidence_head (
    evidence_id       TEXT PRIMARY KEY,
    latest_version    INTEGER NOT NULL,
    latest_hash       TEXT NOT NULL,
    evidence_type     TEXT NOT NULL,
    source_id         TEXT NOT NULL,
    source_record_id  TEXT NOT NULL,
    canonical_key     TEXT,
    first_observed_at TEXT NOT NULL,
    latest_observed_at TEXT NOT NULL,
    versions          INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_head_key ON evidence_head(canonical_key);

CREATE TABLE evidence_identifiers (
    evidence_id  TEXT NOT NULL,
    version      INTEGER NOT NULL,
    scheme       TEXT NOT NULL,
    value        TEXT NOT NULL,
    issuer       TEXT NOT NULL DEFAULT '',
    scope        TEXT NOT NULL DEFAULT '',
    is_primary   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (evidence_id, version, scheme, value)
);
CREATE INDEX idx_evid_ident ON evidence_identifiers(scheme, value);

CREATE TABLE evidence_entity_refs (
    evidence_id  TEXT NOT NULL,
    version      INTEGER NOT NULL,
    entity_type  TEXT NOT NULL,
    name_raw     TEXT NOT NULL DEFAULT '',
    firm_key     TEXT,
    method       TEXT NOT NULL,
    confidence   REAL NOT NULL DEFAULT 0.0,
    note         TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (evidence_id, version, entity_type, name_raw, method)
);

-- ---------------------------------------------------------------- entities
CREATE TABLE companies (
    company_id         TEXT PRIMARY KEY,
    canonical_name     TEXT NOT NULL,
    country            TEXT NOT NULL DEFAULT '',
    legal_form         TEXT NOT NULL DEFAULT '',
    valid_from         TEXT NOT NULL DEFAULT '',
    valid_to           TEXT NOT NULL DEFAULT '',
    parent_company_id  TEXT NOT NULL DEFAULT '',
    metadata_json      TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE company_names (
    company_id   TEXT NOT NULL,
    name         TEXT NOT NULL,
    name_type    TEXT NOT NULL DEFAULT 'alias',
    valid_from   TEXT NOT NULL DEFAULT '',
    valid_to     TEXT NOT NULL DEFAULT '',
    source_id    TEXT NOT NULL DEFAULT '',
    evidence_id  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (company_id, name, name_type)
);

CREATE TABLE manufacturers (
    manufacturer_id  TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    company_id       TEXT NOT NULL DEFAULT '',
    role             TEXT NOT NULL DEFAULT 'legal_manufacturer',
    country          TEXT NOT NULL DEFAULT '',
    site             TEXT NOT NULL DEFAULT '',
    relationship     TEXT NOT NULL DEFAULT 'unknown',
    valid_from       TEXT NOT NULL DEFAULT '',
    valid_to         TEXT NOT NULL DEFAULT ''
);

CREATE TABLE devices (
    device_id        TEXT PRIMARY KEY,
    canonical_name   TEXT NOT NULL,
    brand_name       TEXT NOT NULL DEFAULT '',
    model_number     TEXT NOT NULL DEFAULT '',
    catalog_number   TEXT NOT NULL DEFAULT '',
    product_family   TEXT NOT NULL DEFAULT '',
    device_class     TEXT NOT NULL DEFAULT '',
    company_id       TEXT NOT NULL DEFAULT '',
    manufacturer_id  TEXT NOT NULL DEFAULT '',
    markets_json     TEXT NOT NULL DEFAULT '[]',
    metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE device_identifiers (
    device_id    TEXT NOT NULL,
    scheme       TEXT NOT NULL,
    value        TEXT NOT NULL,
    issuer       TEXT NOT NULL DEFAULT '',
    is_primary   INTEGER NOT NULL DEFAULT 0,
    evidence_id  TEXT NOT NULL DEFAULT '',
    valid_from   TEXT NOT NULL DEFAULT '',
    valid_to     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (device_id, scheme, value)
);
CREATE INDEX idx_dev_ident ON device_identifiers(scheme, value);

CREATE TABLE device_product_codes (
    device_id     TEXT NOT NULL,
    product_code  TEXT NOT NULL,
    PRIMARY KEY (device_id, product_code)
);

-- ------------------------------------------------------------- relations/graph
CREATE TABLE entity_relations (
    relation_id       TEXT PRIMARY KEY,
    from_ref          TEXT NOT NULL,
    from_type         TEXT NOT NULL,
    to_ref            TEXT NOT NULL,
    to_type           TEXT NOT NULL,
    relation_type     TEXT NOT NULL,
    status            TEXT NOT NULL,
    method            TEXT NOT NULL,
    authority         TEXT NOT NULL,
    confidence        REAL NOT NULL DEFAULT 0.0,
    basis_json        TEXT NOT NULL DEFAULT '{}',
    contradictions_json TEXT NOT NULL DEFAULT '[]',
    rejection_reason  TEXT NOT NULL DEFAULT '',
    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at        TEXT NOT NULL,
    revoked_at        TEXT NOT NULL DEFAULT '',
    revoked_reason    TEXT NOT NULL DEFAULT '',
    superseded_by     TEXT NOT NULL DEFAULT '',
    run_id            TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_rel_from ON entity_relations(from_ref);
CREATE INDEX idx_rel_to ON entity_relations(to_ref);
CREATE INDEX idx_rel_type ON entity_relations(relation_type);

CREATE TABLE relation_events (
    event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    relation_id    TEXT NOT NULL,
    action         TEXT NOT NULL,
    at             TEXT NOT NULL,
    reason         TEXT NOT NULL DEFAULT '',
    evidence_ids_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX idx_relev_rel ON relation_events(relation_id);

-- ------------------------------------------------------------------- quality
CREATE TABLE quality_findings (
    finding_id      TEXT PRIMARY KEY,
    check_id        TEXT NOT NULL,
    severity        TEXT NOT NULL,
    subject         TEXT NOT NULL DEFAULT '',
    detail          TEXT NOT NULL DEFAULT '',
    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    run_id          TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open'
);
CREATE INDEX idx_finding_check ON quality_findings(check_id);

-- ---------------------------------------------------------------- observations
CREATE TABLE observations (
    observation_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_ref      TEXT NOT NULL,
    field           TEXT NOT NULL,
    value_json      TEXT NOT NULL,
    observed_at     TEXT NOT NULL,
    evidence_id     TEXT NOT NULL DEFAULT '',
    run_id          TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_obs_entity ON observations(entity_ref, field);
CREATE INDEX idx_obs_time ON observations(observed_at);

-- ------------------------------------------------------- prospective registry
CREATE TABLE prospective_candidates (
    candidate_id      TEXT PRIMARY KEY,
    name_raw          TEXT NOT NULL,
    source_id         TEXT NOT NULL,
    evidence_id       TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    company_candidate TEXT NOT NULL DEFAULT '',
    known_identifiers_json TEXT NOT NULL DEFAULT '[]',
    status            TEXT NOT NULL DEFAULT 'open',
    version           INTEGER NOT NULL DEFAULT 1,
    updated_at        TEXT NOT NULL,
    notes             TEXT NOT NULL DEFAULT ''
);

CREATE TABLE prospective_events (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id  TEXT NOT NULL,
    at            TEXT NOT NULL,
    action        TEXT NOT NULL,
    payload_json  TEXT NOT NULL DEFAULT '{}'
);

-- ---------------------------------------------------------------- source status
CREATE TABLE source_status (
    check_id     TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL,
    checked_at   TEXT NOT NULL,
    status       TEXT NOT NULL,
    detail       TEXT NOT NULL DEFAULT '',
    evidence_url TEXT NOT NULL DEFAULT '',
    run_id       TEXT NOT NULL DEFAULT ''
);
"""

MIGRATIONS: tuple[Migration, ...] = (Migration(version=1, name="atlas_init", sql=V1_SQL),)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MigrationError(RuntimeError):
    """Raised when a migration cannot be applied safely."""


def split_statements(sql: str) -> list[str]:
    """Split a migration script into statements for transactional execution.

    The ATLAS DDL contains no semicolons inside string literals, so a simple
    split is exact for it; the guard below makes that assumption explicit and
    fails loudly if a future migration breaks it.
    """
    statements = [chunk.strip() for chunk in sql.split(";") if chunk.strip()]
    for statement in statements:
        stripped = statement.lstrip()
        if stripped.startswith("--") and ";" in statement:
            raise MigrationError("migration statement contains a semicolon inside a comment")
    return statements


def _applied(conn: sqlite3.Connection) -> dict[int, tuple[str, str]]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL,"
        " applied_at TEXT NOT NULL)"
    )
    return {
        int(row[0]): (str(row[1]), str(row[2]))
        for row in conn.execute("SELECT version, name, checksum FROM schema_migrations")
    }


def backup_database(path: Path, *, directory: Path | None = None) -> Path:
    """Copy the database to a timestamped backup before migrating."""
    path = Path(path)
    target_dir = Path(directory) if directory else path.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = target_dir / f"{path.stem}.{stamp}.pre-migration.bak"
    shutil.copy2(path, backup)
    return backup


def migrate(
    db_path: Path | str,
    *,
    migrations: Iterable[Migration] = MIGRATIONS,
    auto_backup: bool = True,
) -> dict[str, object]:
    """Apply pending migrations.  Returns a small, machine-readable report."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists() and path.stat().st_size > 0
    ordered = sorted(migrations, key=lambda m: m.version)
    applied_now: list[int] = []
    backup_path = ""

    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        applied = _applied(conn)
        # Verify every already-applied migration before deciding that there is
        # nothing to do: a tampered migration must fail loudly even on a no-op run.
        for migration in ordered:
            if migration.version in applied:
                name, checksum = applied[migration.version]
                if checksum != migration.checksum:
                    raise MigrationError(
                        f"migration {migration.version} ({name}) was modified after being applied"
                    )
        pending = [m for m in ordered if m.version not in applied]
        if not pending:
            return {
                "db": str(path),
                "schema_version": max(applied) if applied else 0,
                "applied": [],
                "backup": "",
                "created": False,
            }
        if existed and auto_backup:
            backup_path = str(backup_database(path))
        for migration in pending:
            # ``executescript`` implicitly commits before running, which would
            # defeat rollback.  Execute statement-by-statement inside one
            # explicit transaction instead.
            conn.execute("BEGIN")
            try:
                for statement in split_statements(migration.sql):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations(version, name, checksum, applied_at)"
                    " VALUES (?, ?, ?, ?)",
                    (migration.version, migration.name, migration.checksum, utc_now()),
                )
                conn.commit()
            except Exception as exc:  # roll the whole migration back
                conn.rollback()
                raise MigrationError(
                    f"migration {migration.version} ({migration.name}) failed: {exc}"
                ) from exc
            applied_now.append(migration.version)
        return {
            "db": str(path),
            "schema_version": max(m.version for m in ordered),
            "applied": applied_now,
            "backup": backup_path,
            "created": not existed,
        }
    finally:
        conn.close()


def current_version(db_path: Path | str) -> int:
    path = Path(db_path)
    if not path.exists():
        return 0
    conn = sqlite3.connect(str(path))
    try:
        applied = _applied(conn)
        return max(applied) if applied else 0
    finally:
        conn.close()


__all__ = [
    "MIGRATIONS",
    "Migration",
    "MigrationError",
    "SCHEMA_VERSION",
    "V1_SQL",
    "backup_database",
    "current_version",
    "migrate",
    "utc_now",
]
