"""SQLite state, source registry, change ledger and publication journal.

The database is deliberately small and boring. It is not a replacement for the immutable
snapshot files: it records *what MedRadar observed and decided*, while the snapshots hold
the data itself. Change rows are written as ``staged`` and become visible through the API
only when the matching snapshot pointer has been published.

Append-only history matters here. A correction appends a new ``UPDATED`` row; it never
rewrites an older row. The only updates to change rows are lifecycle flags
(staged -> published), never their content.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

SCHEMA_VERSION = 1

SCHEMA_STATEMENTS = [
    "CREATE TABLE IF NOT EXISTS pipeline_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS sources ("
    " source_id TEXT PRIMARY KEY,"
    " endpoint TEXT NOT NULL,"
    " display_name TEXT NOT NULL,"
    " official_last_updated TEXT,"
    " official_total INTEGER,"
    " official_export_date TEXT,"
    " last_checked_at TEXT,"
    " last_check_status TEXT,"
    " last_check_message TEXT,"
    " last_check_http_status INTEGER,"
    " last_check_evidence_json TEXT,"
    " last_success_check_at TEXT,"
    " last_success_sync_at TEXT,"
    " last_success_official_last_updated TEXT,"
    " last_success_official_total INTEGER,"
    " last_failed_at TEXT,"
    " consecutive_failures INTEGER NOT NULL DEFAULT 0,"
    " active_snapshot_id TEXT,"
    " last_full_reconciliation_at TEXT,"
    " last_full_reconciliation_snapshot_id TEXT,"
    " update_available INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS sync_runs ("
    " run_id TEXT PRIMARY KEY,"
    " started_at TEXT NOT NULL,"
    " finished_at TEXT,"
    " status TEXT NOT NULL,"
    " requested_sources_json TEXT NOT NULL,"
    " active_before TEXT,"
    " candidate_after TEXT,"
    " counts_json TEXT,"
    " error TEXT,"
    " metrics_json TEXT)",
    "CREATE TABLE IF NOT EXISTS snapshots ("
    " snapshot_id TEXT PRIMARY KEY,"
    " path TEXT NOT NULL,"
    " content_hash TEXT NOT NULL,"
    " created_at TEXT NOT NULL,"
    " published_at TEXT,"
    " status TEXT NOT NULL,"
    " parent_snapshot_id TEXT,"
    " source_versions_json TEXT,"
    " counts_json TEXT,"
    " manifest_sha256 TEXT,"
    " validation_json TEXT,"
    " is_active INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS changes ("
    " change_id TEXT PRIMARY KEY,"
    " run_id TEXT NOT NULL,"
    " source_id TEXT NOT NULL,"
    " official_record_id TEXT NOT NULL,"
    " event_id TEXT NOT NULL,"
    " change_type TEXT NOT NULL,"
    " detected_at TEXT NOT NULL,"
    " source_updated_at TEXT,"
    " previous_content_hash TEXT,"
    " new_content_hash TEXT,"
    " previous_snapshot_id TEXT,"
    " candidate_snapshot_id TEXT NOT NULL,"
    " changed_fields_json TEXT NOT NULL,"
    " evidence_json TEXT NOT NULL,"
    " organization_key TEXT,"
    " applicant_name TEXT,"
    " event_type TEXT,"
    " event_date TEXT,"
    " record_json TEXT,"
    " status TEXT NOT NULL DEFAULT 'staged',"
    " published_at TEXT)",
    "CREATE INDEX IF NOT EXISTS changes_published ON changes(status, candidate_snapshot_id, detected_at)",
    "CREATE INDEX IF NOT EXISTS changes_source ON changes(source_id, change_type, detected_at)",
    "CREATE INDEX IF NOT EXISTS changes_event ON changes(event_id, detected_at)",
    "CREATE TABLE IF NOT EXISTS record_observations ("
    " source_id TEXT NOT NULL,"
    " event_id TEXT NOT NULL,"
    " official_record_id TEXT NOT NULL,"
    " first_observed_at TEXT NOT NULL,"
    " last_seen_at TEXT NOT NULL,"
    " last_seen_snapshot_id TEXT,"
    " last_content_hash TEXT NOT NULL,"
    " state TEXT NOT NULL,"
    " missing_count INTEGER NOT NULL DEFAULT 0,"
    " last_missing_at TEXT,"
    " organization_key TEXT,"
    " applicant_name TEXT,"
    " event_type TEXT,"
    " event_date TEXT,"
    " PRIMARY KEY (source_id, event_id))",
    "CREATE TABLE IF NOT EXISTS publications ("
    " publication_id TEXT PRIMARY KEY,"
    " snapshot_id TEXT NOT NULL,"
    " previous_snapshot_id TEXT,"
    " published_at TEXT NOT NULL,"
    " action TEXT NOT NULL,"
    " actor TEXT NOT NULL,"
    " note TEXT)",
    "CREATE TABLE IF NOT EXISTS request_usage ("
    " day TEXT NOT NULL,"
    " source_id TEXT NOT NULL,"
    " requests INTEGER NOT NULL DEFAULT 0,"
    " response_bytes INTEGER NOT NULL DEFAULT 0,"
    " PRIMARY KEY (day, source_id))",
    "CREATE TABLE IF NOT EXISTS incidents ("
    " incident_id TEXT PRIMARY KEY,"
    " at TEXT NOT NULL,"
    " kind TEXT NOT NULL,"
    " detail_json TEXT NOT NULL)",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except ValueError:
        return fallback


class StateStore:
    def __init__(self, path: Path | str, *, read_only: bool = False) -> None:
        self.path = Path(path)
        self.read_only = read_only
        if not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.initialize()

    def _connect(self) -> sqlite3.Connection:
        if self.read_only:
            # Health/status must not run schema setup or mutate pipeline rows. SQLite still
            # needs to open the WAL sidecar, so this is a query_only connection rather than a
            # URI mode=ro connection (which cannot create a missing -shm file).
            connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA busy_timeout=30000")
            return connection
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._conn() as connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            columns = {
                str(row["name"]) for row in connection.execute("PRAGMA table_info(sources)").fetchall()
            }
            for name, ddl in (
                ("last_full_reconciliation_at", "TEXT"),
                ("last_full_reconciliation_snapshot_id", "TEXT"),
                ("last_success_official_last_updated", "TEXT"),
                ("last_success_official_total", "INTEGER"),
            ):
                if name not in columns:
                    connection.execute("ALTER TABLE sources ADD COLUMN " + name + " " + ddl)
            current = connection.execute("SELECT value FROM pipeline_meta WHERE key = 'schema_version'").fetchone()
            if current is None:
                connection.execute(
                    "INSERT INTO pipeline_meta(key, value) VALUES('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            elif int(current["value"]) > SCHEMA_VERSION:
                raise RuntimeError(
                    "pipeline database schema is newer than this code: "
                    + str(current["value"])
                    + " > "
                    + str(SCHEMA_VERSION)
                )

    # ------------------------------------------------------------------ sources
    def get_source(self, source_id: str) -> dict[str, Any] | None:
        with self._conn() as connection:
            row = connection.execute("SELECT * FROM sources WHERE source_id = ?", (source_id,)).fetchone()
        return dict(row) if row else None

    def list_sources(self) -> list[dict[str, Any]]:
        with self._conn() as connection:
            rows = connection.execute("SELECT * FROM sources ORDER BY source_id").fetchall()
        return [dict(row) for row in rows]

    def record_check(
        self,
        *,
        source_id: str,
        endpoint: str,
        display_name: str,
        status: str,
        message: str,
        checked_at: str,
        http_status: int | None,
        evidence: dict[str, Any],
        official_last_updated: str | None,
        official_total: int | None,
        official_export_date: str | None,
        update_available: bool,
        active_snapshot_id: str | None,
        consecutive_failures: int,
        last_success_check_at: str | None,
        last_failed_at: str | None,
    ) -> None:
        with self._conn() as connection:
            connection.execute(
                "INSERT INTO sources("
                " source_id, endpoint, display_name, official_last_updated, official_total, official_export_date,"
                " last_checked_at, last_check_status, last_check_message, last_check_http_status,"
                " last_check_evidence_json, last_success_check_at, last_failed_at, consecutive_failures,"
                " active_snapshot_id, update_available"
                ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(source_id) DO UPDATE SET"
                " endpoint=excluded.endpoint, display_name=excluded.display_name,"
                " official_last_updated=excluded.official_last_updated, official_total=excluded.official_total,"
                " official_export_date=excluded.official_export_date, last_checked_at=excluded.last_checked_at,"
                " last_check_status=excluded.last_check_status, last_check_message=excluded.last_check_message,"
                " last_check_http_status=excluded.last_check_http_status,"
                " last_check_evidence_json=excluded.last_check_evidence_json,"
                " last_success_check_at=excluded.last_success_check_at, last_failed_at=excluded.last_failed_at,"
                " consecutive_failures=excluded.consecutive_failures, active_snapshot_id=excluded.active_snapshot_id,"
                " update_available=excluded.update_available",
                (
                    source_id,
                    endpoint,
                    display_name,
                    official_last_updated,
                    official_total,
                    official_export_date,
                    checked_at,
                    status,
                    message,
                    http_status,
                    _json(evidence),
                    last_success_check_at,
                    last_failed_at,
                    consecutive_failures,
                    active_snapshot_id,
                    1 if update_available else 0,
                ),
            )

    def mark_source_synced(
        self, source_id: str, snapshot_id: str, synced_at: str, official_last_updated: str | None,
        official_total: int | None,
    ) -> None:
        with self._conn() as connection:
            connection.execute(
                "UPDATE sources SET last_success_sync_at = ?, active_snapshot_id = ?,"
                " update_available = 0, last_check_status = 'NO_CHANGE',"
                " last_check_message = 'official version reconciled and published',"
                " last_success_check_at = COALESCE(last_success_check_at, ?),"
                " last_success_official_last_updated = COALESCE(?, last_success_official_last_updated),"
                " last_success_official_total = COALESCE(?, last_success_official_total),"
                " official_last_updated = COALESCE(?, official_last_updated),"
                " official_total = COALESCE(?, official_total) WHERE source_id = ?",
                (synced_at, snapshot_id, synced_at, official_last_updated, official_total,
                 official_last_updated, official_total, source_id),
            )

    def mark_source_full_reconciled(self, source_id: str, snapshot_id: str, reconciled_at: str) -> None:
        with self._conn() as connection:
            connection.execute(
                "UPDATE sources SET last_full_reconciliation_at = ?,"
                " last_full_reconciliation_snapshot_id = ? WHERE source_id = ?",
                (reconciled_at, snapshot_id, source_id),
            )

    def mark_source_attempt_failed(self, source_id: str, message: str, failed_at: str) -> None:
        """Record a collection/validation failure without pretending the source synced.

        The previous successful official version and event data stay in place, but the
        source becomes due for an hourly retry and stays visibly failed.
        """
        with self._conn() as connection:
            connection.execute(
                "UPDATE sources SET last_check_status = 'CHECK_FAILED',"
                " last_check_message = ?, last_failed_at = ?,"
                " consecutive_failures = consecutive_failures + 1 WHERE source_id = ?",
                (message, failed_at, source_id),
            )

    def set_source_active_snapshot(self, snapshot_id: str | None) -> None:
        with self._conn() as connection:
            connection.execute("UPDATE sources SET active_snapshot_id = ?", (snapshot_id,))

    # ------------------------------------------------------------------ runs
    def begin_run(self, requested_sources: Sequence[str], active_before: str | None) -> str:
        run_id = "run_" + uuid.uuid4().hex
        with self._conn() as connection:
            connection.execute(
                "INSERT INTO sync_runs(run_id, started_at, status, requested_sources_json, active_before)"
                " VALUES(?,?,?,?,?)",
                (run_id, _now(), "RUNNING", _json(list(requested_sources)), active_before),
            )
        return run_id

    def finish_run(
        self, run_id: str, status: str, *, candidate_after: str | None = None,
        counts: dict[str, Any] | None = None, error: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        with self._conn() as connection:
            connection.execute(
                "UPDATE sync_runs SET finished_at = ?, status = ?, candidate_after = ?, counts_json = ?,"
                " error = ?, metrics_json = ? WHERE run_id = ?",
                (_now(), status, candidate_after, _json(counts or {}), error, _json(metrics or {}), run_id),
            )

    def recent_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as connection:
            rows = connection.execute(
                "SELECT * FROM sync_runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["requested_sources"] = _loads(item.pop("requested_sources_json", None), [])
            item["counts"] = _loads(item.pop("counts_json", None), {})
            item["metrics"] = _loads(item.pop("metrics_json", None), {})
            result.append(item)
        return result

    # ------------------------------------------------------------------ snapshots
    def register_snapshot(
        self, *, snapshot_id: str, path: str, content_hash: str, created_at: str,
        status: str, parent_snapshot_id: str | None, source_versions: dict[str, Any],
        counts: dict[str, Any], manifest_sha256: str, validation: dict[str, Any],
    ) -> None:
        with self._conn() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO snapshots("
                " snapshot_id, path, content_hash, created_at, status, parent_snapshot_id,"
                " source_versions_json, counts_json, manifest_sha256, validation_json, is_active"
                ") VALUES(?,?,?,?,?,?,?,?,?,?,0)",
                (
                    snapshot_id, path, content_hash, created_at, status, parent_snapshot_id,
                    _json(source_versions), _json(counts), manifest_sha256, _json(validation),
                ),
            )

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        with self._conn() as connection:
            row = connection.execute("SELECT * FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
        return self._snapshot_row(row) if row else None

    def get_active_snapshot(self) -> dict[str, Any] | None:
        with self._conn() as connection:
            row = connection.execute(
                "SELECT * FROM snapshots WHERE is_active = 1 ORDER BY published_at DESC LIMIT 1"
            ).fetchone()
        return self._snapshot_row(row) if row else None

    def list_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as connection:
            rows = connection.execute(
                "SELECT * FROM snapshots ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._snapshot_row(row) for row in rows]

    @staticmethod
    def _snapshot_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["source_versions"] = _loads(item.pop("source_versions_json", None), {})
        item["counts"] = _loads(item.pop("counts_json", None), {})
        item["validation"] = _loads(item.pop("validation_json", None), {})
        item["is_active"] = bool(item.get("is_active"))
        return item

    def add_changes(self, run_id: str, snapshot_id: str, changes: Iterable[dict[str, Any]]) -> int:
        inserted = 0
        with self.transaction() as connection:
            for change in changes:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO changes("
                    " change_id, run_id, source_id, official_record_id, event_id, change_type,"
                    " detected_at, source_updated_at, previous_content_hash, new_content_hash,"
                    " previous_snapshot_id, candidate_snapshot_id, changed_fields_json, evidence_json,"
                    " organization_key, applicant_name, event_type, event_date, record_json, status"
                    ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'staged')",
                    (
                        change["change_id"], run_id, change["source_id"], change["official_record_id"],
                        change["event_id"], change["change_type"], change["detected_at"],
                        change.get("source_updated_at"), change.get("previous_content_hash"),
                        change.get("new_content_hash"), change.get("previous_snapshot_id"), snapshot_id,
                        _json(change.get("changed_fields") or {}),
                        _json(change.get("evidence") or {}),
                        change.get("organization_key"), change.get("applicant_name"),
                        change.get("event_type"), change.get("event_date"),
                        _json(change.get("record")) if change.get("record") else None,
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def publish_changes(self, run_id: str, snapshot_id: str, published_at: str) -> None:
        with self._conn() as connection:
            connection.execute(
                "UPDATE changes SET status = 'published', published_at = ?"
                " WHERE run_id = ? AND candidate_snapshot_id = ? AND status = 'staged'",
                (published_at, run_id, snapshot_id),
            )

    def discard_staged_changes(self, run_id: str) -> None:
        with self._conn() as connection:
            connection.execute("DELETE FROM changes WHERE run_id = ? AND status = 'staged'", (run_id,))

    def record_publication(
        self, snapshot_id: str, previous_snapshot_id: str | None, published_at: str,
        action: str, actor: str, note: str | None = None,
    ) -> None:
        with self._conn() as connection:
            connection.execute(
                "INSERT INTO publications(publication_id, snapshot_id, previous_snapshot_id,"
                " published_at, action, actor, note) VALUES(?,?,?,?,?,?,?)",
                ("pub_" + uuid.uuid4().hex, snapshot_id, previous_snapshot_id, published_at, action, actor, note),
            )

    def latest_publication(self) -> dict[str, Any] | None:
        with self._conn() as connection:
            row = connection.execute(
                "SELECT * FROM publications ORDER BY published_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------ observations
    def get_observation(self, source_id: str, event_id: str) -> dict[str, Any] | None:
        with self._conn() as connection:
            row = connection.execute(
                "SELECT * FROM record_observations WHERE source_id = ? AND event_id = ?",
                (source_id, event_id),
            ).fetchone()
        return dict(row) if row else None

    def observations_for_sources(self, source_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        if not source_ids:
            return {}
        placeholders = ",".join("?" for _ in source_ids)
        with self._conn() as connection:
            rows = connection.execute(
                "SELECT * FROM record_observations WHERE source_id IN (" + placeholders + ")",
                list(source_ids),
            ).fetchall()
        return {str(row["event_id"]): dict(row) for row in rows}

    def upsert_observations(self, rows: Iterable[dict[str, Any]]) -> None:
        with self.transaction() as connection:
            for row in rows:
                connection.execute(
                    "INSERT INTO record_observations("
                    " source_id, event_id, official_record_id, first_observed_at, last_seen_at,"
                    " last_seen_snapshot_id, last_content_hash, state, missing_count, last_missing_at,"
                    " organization_key, applicant_name, event_type, event_date"
                    ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(source_id, event_id) DO UPDATE SET"
                    " official_record_id=excluded.official_record_id, last_seen_at=excluded.last_seen_at,"
                    " last_seen_snapshot_id=excluded.last_seen_snapshot_id, last_content_hash=excluded.last_content_hash,"
                    " state=excluded.state, missing_count=excluded.missing_count, last_missing_at=excluded.last_missing_at,"
                    " organization_key=excluded.organization_key, applicant_name=excluded.applicant_name,"
                    " event_type=excluded.event_type, event_date=excluded.event_date",
                    (
                        row["source_id"], row["event_id"], row["official_record_id"],
                        row["first_observed_at"], row["last_seen_at"], row.get("last_seen_snapshot_id"),
                        row["last_content_hash"], row["state"], int(row.get("missing_count") or 0),
                        row.get("last_missing_at"), row.get("organization_key"), row.get("applicant_name"),
                        row.get("event_type"), row.get("event_date"),
                    ),
                )

    def set_snapshot_active_flag(self, snapshot_id: str) -> None:
        with self._conn() as connection:
            connection.execute("UPDATE snapshots SET is_active = 0")
            connection.execute("UPDATE snapshots SET is_active = 1 WHERE snapshot_id = ?", (snapshot_id,))

    # ------------------------------------------------------------------ changes
    def change_counts(self, snapshot_id: str | None = None) -> dict[str, int]:
        query = "SELECT change_type, COUNT(*) AS n FROM changes WHERE status = 'published'"
        params: list[Any] = []
        if snapshot_id:
            query += " AND candidate_snapshot_id = ?"
            params.append(snapshot_id)
        query += " GROUP BY change_type"
        with self._conn() as connection:
            rows = connection.execute(query, params).fetchall()
        return {str(row["change_type"]): int(row["n"]) for row in rows}

    def change_counts_by_source(self, snapshot_id: str) -> dict[str, dict[str, int]]:
        with self._conn() as connection:
            rows = connection.execute(
                "SELECT source_id, change_type, COUNT(*) AS n FROM changes"
                " WHERE status = 'published' AND candidate_snapshot_id = ?"
                " GROUP BY source_id, change_type",
                (snapshot_id,),
            ).fetchall()
        result: dict[str, dict[str, int]] = {}
        for row in rows:
            result.setdefault(row["source_id"], {})[row["change_type"]] = int(row["n"])
        return result

    def list_changes(
        self, *, source_id: str | None = None, change_type: str | None = None,
        organization_key: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        clauses = ["status = 'published'"]
        params: list[Any] = []
        if source_id:
            clauses.append("source_id = ?")
            params.append(source_id)
        if change_type:
            clauses.append("change_type = ?")
            params.append(change_type)
        if organization_key:
            clauses.append("organization_key = ?")
            params.append(organization_key)
        where = " AND ".join(clauses)
        with self._conn() as connection:
            total = int(connection.execute("SELECT COUNT(*) AS n FROM changes WHERE " + where, params).fetchone()["n"])
            rows = connection.execute(
                "SELECT * FROM changes WHERE " + where + " ORDER BY detected_at DESC, change_id LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["changed_fields"] = _loads(item.pop("changed_fields_json", None), {})
            item["evidence"] = _loads(item.pop("evidence_json", None), {})
            item["record"] = _loads(item.pop("record_json", None), None)
            items.append(item)
        return items, total

    # ------------------------------------------------------------------ request budget
    def consume_request_budget(
        self, day: str, source_id: str, limit: int, count: int = 1, response_bytes: int = 0
    ) -> bool:
        with self.transaction() as connection:
            rows = connection.execute("SELECT COALESCE(SUM(requests), 0) AS n FROM request_usage WHERE day = ?", (day,)).fetchone()
            used = int(rows["n"])
            if used + count > limit:
                return False
            connection.execute(
                "INSERT INTO request_usage(day, source_id, requests, response_bytes) VALUES(?,?,?,?)"
                " ON CONFLICT(day, source_id) DO UPDATE SET requests = requests + excluded.requests,"
                " response_bytes = response_bytes + excluded.response_bytes",
                (day, source_id, count, response_bytes),
            )
            return True

    def request_usage(self, day: str) -> dict[str, Any]:
        with self._conn() as connection:
            rows = connection.execute(
                "SELECT source_id, requests, response_bytes FROM request_usage WHERE day = ?", (day,)
            ).fetchall()
        return {
            "day": day,
            "total_requests": sum(int(row["requests"]) for row in rows),
            "by_source": {row["source_id"]: int(row["requests"]) for row in rows},
            "response_bytes": sum(int(row["response_bytes"]) for row in rows),
        }

    # ------------------------------------------------------------------ incidents
    def record_incident(self, kind: str, detail: dict[str, Any]) -> str:
        incident_id = "inc_" + uuid.uuid4().hex
        with self._conn() as connection:
            connection.execute(
                "INSERT INTO incidents(incident_id, at, kind, detail_json) VALUES(?,?,?,?)",
                (incident_id, _now(), kind, _json(detail)),
            )
        return incident_id

    def incidents(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as connection:
            rows = connection.execute("SELECT * FROM incidents ORDER BY at DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["detail"] = _loads(item.pop("detail_json", None), {})
            result.append(item)
        return result
