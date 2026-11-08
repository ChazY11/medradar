"""Isolated staging store for external evidence.

This is **not** MedRadar's research database.  It lives under
``research/data_expansion/staging/`` (git-ignored), it is created from scratch
by a re-run, and nothing in the existing MedRadar runtime reads it.  That
isolation is the point: DATA-EXPANSION-001 must be able to fail, be re-run and
be deleted without touching a frozen research asset.

Schema
------
``collection_runs``   one row per connector run
``raw_objects``       immutable raw response bodies, addressed by sha256
``evidence``          one row per (evidence_id, content_hash) *version*
``evidence_head``     one row per evidence_id: first/last observed, duplicate_of
``entity_refs``       company/entity links, deterministic and candidate apart
``identifiers``       authoritative identifiers per evidence version
``request_log``       per-request accounting for the run

Idempotency
-----------
Re-running a connector does not duplicate evidence: the version row is keyed by
``(evidence_id, content_hash)`` and ``evidence_head`` keeps the earliest
``first_observed_at`` across re-fetches.  A changed upstream record becomes a
new version under the same evidence id, which is exactly the bitemporal
behaviour the study needs.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from . import schema as ev_schema

DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS collection_runs (
    run_id          TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'running',
    requests        INTEGER NOT NULL DEFAULT 0,
    records         INTEGER NOT NULL DEFAULT 0,
    raw_bytes       INTEGER NOT NULL DEFAULT 0,
    producer        TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS raw_objects (
    content_hash  TEXT PRIMARY KEY,
    source_id     TEXT NOT NULL,
    source_url    TEXT NOT NULL DEFAULT '',
    media_type    TEXT NOT NULL DEFAULT 'application/json',
    bytes         INTEGER NOT NULL,
    fetched_at    TEXT NOT NULL,
    storage_path  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id        TEXT NOT NULL,
    content_hash       TEXT NOT NULL,
    kind               TEXT NOT NULL,
    source_id          TEXT NOT NULL,
    source_record_id   TEXT NOT NULL,
    source_url         TEXT NOT NULL DEFAULT '',
    canonical_key      TEXT,
    first_observed_at  TEXT NOT NULL,
    fetched_at         TEXT NOT NULL,
    event_at           TEXT NOT NULL DEFAULT '',
    source_public_at   TEXT NOT NULL DEFAULT '',
    time_quality       TEXT NOT NULL DEFAULT 'unknown',
    payload_json       TEXT NOT NULL,
    PRIMARY KEY (evidence_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_evidence_kind ON evidence(kind);
CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source_id);
CREATE INDEX IF NOT EXISTS idx_evidence_key ON evidence(canonical_key);

CREATE TABLE IF NOT EXISTS evidence_head (
    evidence_id      TEXT PRIMARY KEY,
    kind             TEXT NOT NULL,
    source_id        TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    canonical_key    TEXT,
    first_observed_at TEXT NOT NULL,
    latest_fetched_at TEXT NOT NULL,
    latest_hash      TEXT NOT NULL,
    versions         INTEGER NOT NULL DEFAULT 1,
    duplicate_of     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS entity_refs (
    evidence_id  TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    entity_type  TEXT NOT NULL,
    name_raw     TEXT NOT NULL DEFAULT '',
    resolved_key TEXT,
    method       TEXT NOT NULL,
    confidence   REAL NOT NULL DEFAULT 0.0,
    note         TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (evidence_id, content_hash, entity_type, name_raw, method)
);

CREATE TABLE IF NOT EXISTS identifiers (
    evidence_id  TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    scheme       TEXT NOT NULL,
    value        TEXT NOT NULL,
    is_primary   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (evidence_id, content_hash, scheme, value)
);

CREATE TABLE IF NOT EXISTS request_log (
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

CREATE INDEX IF NOT EXISTS idx_request_run ON request_log(run_id);
"""


def sha256_bytes(payload: bytes) -> str:
    return ev_schema.sha256_bytes(payload)


class StagingStore:
    """Thin, explicit SQLite wrapper.  No ORM, no hidden writes."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    # --------------------------------------------------------------- lifecycle
    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(str(self.path))
            conn.row_factory = sqlite3.Row
            conn.executescript(DDL)
            self._conn = conn
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "StagingStore":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # -------------------------------------------------------------------- runs
    def start_run(self, run_id: str, source_id: str, started_at: str, producer: str = "") -> None:
        conn = self.connect()
        conn.execute(
            "INSERT OR REPLACE INTO collection_runs(run_id, source_id, started_at, status, producer)"
            " VALUES (?, ?, ?, 'running', ?)",
            (run_id, source_id, started_at, producer),
        )
        conn.commit()

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        finished_at: str,
        requests: int = 0,
        records: int = 0,
        raw_bytes: int = 0,
        notes: str = "",
    ) -> None:
        conn = self.connect()
        conn.execute(
            "UPDATE collection_runs SET status=?, finished_at=?, requests=?, records=?,"
            " raw_bytes=?, notes=? WHERE run_id=?",
            (status, finished_at, requests, records, raw_bytes, notes, run_id),
        )
        conn.commit()

    # -------------------------------------------------------------------- raw
    def put_raw(
        self,
        body: bytes,
        *,
        source_id: str,
        source_url: str,
        fetched_at: str,
        media_type: str = "application/json",
    ) -> dict[str, Any]:
        digest = sha256_bytes(body)
        conn = self.connect()
        conn.execute(
            "INSERT OR IGNORE INTO raw_objects(content_hash, source_id, source_url, media_type,"
            " bytes, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
            (digest, source_id, source_url[:2000], media_type, len(body), fetched_at),
        )
        conn.commit()
        return {"content_hash": digest, "bytes": len(body)}

    # --------------------------------------------------------------- evidence
    def upsert_evidence(self, record: Mapping[str, Any], *, duplicate_of: str = "") -> dict[str, Any]:
        """Insert one evidence version.  Returns ``{"inserted": bool, "evidence_id": ...}``."""
        problems = ev_schema.validate_evidence(record)
        if problems:
            raise ev_schema.EvidenceError(f"{record.get('evidence_id')}: {'; '.join(problems)}")

        eid = str(record["evidence_id"])
        chash = str(record["content_hash"])
        time_block = record["time"]
        conn = self.connect()
        cur = conn.execute(
            "SELECT 1 FROM evidence WHERE evidence_id=? AND content_hash=?", (eid, chash)
        )
        exists = cur.fetchone() is not None
        conn.execute(
            "INSERT OR IGNORE INTO evidence(evidence_id, content_hash, kind, source_id,"
            " source_record_id, source_url, canonical_key, first_observed_at, fetched_at,"
            " event_at, source_public_at, time_quality, payload_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                eid,
                chash,
                record["kind"],
                record["source_id"],
                record["source_record_id"],
                str(record.get("source_url", ""))[:2000],
                record.get("canonical_key"),
                time_block["first_observed_at"],
                time_block["fetched_at"],
                time_block.get("event_at", ""),
                time_block.get("source_public_at", ""),
                time_block.get("source_public_at_quality", "unknown"),
                json.dumps(record, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.execute(
            "INSERT INTO evidence_head(evidence_id, kind, source_id, source_record_id,"
            " canonical_key, first_observed_at, latest_fetched_at, latest_hash, versions,"
            " duplicate_of) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)"
            " ON CONFLICT(evidence_id) DO UPDATE SET"
            "  latest_fetched_at=excluded.latest_fetched_at,"
            "  latest_hash=excluded.latest_hash,"
            "  versions=evidence_head.versions + (CASE WHEN evidence_head.latest_hash <>"
            "    excluded.latest_hash THEN 1 ELSE 0 END),"
            "  duplicate_of=CASE WHEN excluded.duplicate_of <> '' THEN excluded.duplicate_of"
            "    ELSE evidence_head.duplicate_of END",
            (
                eid,
                record["kind"],
                record["source_id"],
                record["source_record_id"],
                record.get("canonical_key"),
                time_block["first_observed_at"],
                time_block["fetched_at"],
                chash,
                duplicate_of,
            ),
        )
        for ref in record.get("entity_refs", []) or []:
            conn.execute(
                "INSERT OR REPLACE INTO entity_refs(evidence_id, content_hash, entity_type,"
                " name_raw, resolved_key, method, confidence, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    eid,
                    chash,
                    str(ref.get("entity_type", "")),
                    str(ref.get("name_raw", ""))[:500],
                    ref.get("resolved_key"),
                    str(ref.get("method", "none")),
                    float(ref.get("confidence", 0.0)),
                    str(ref.get("note", ""))[:500],
                ),
            )
        for ident in record.get("identifiers", []) or []:
            conn.execute(
                "INSERT OR REPLACE INTO identifiers(evidence_id, content_hash, scheme, value,"
                " is_primary) VALUES (?, ?, ?, ?, ?)",
                (
                    eid,
                    chash,
                    str(ident.get("scheme", "")),
                    str(ident.get("value", "")),
                    1 if ident.get("is_primary") else 0,
                ),
            )
        conn.commit()
        return {"inserted": not exists, "evidence_id": eid, "content_hash": chash}

    def find_by_canonical_key(self, key: str) -> list[sqlite3.Row]:
        conn = self.connect()
        return list(
            conn.execute(
                "SELECT evidence_id, source_id, kind FROM evidence_head WHERE canonical_key=?",
                (key,),
            )
        )

    # ------------------------------------------------------------------- query
    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return list(self.connect().execute(sql, params))

    def table_count(self, table: str) -> int:
        row = self.connect().execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        return int(row["n"]) if row else 0

    def stats(self) -> dict[str, Any]:
        conn = self.connect()
        by_kind = {
            row["kind"]: row["n"]
            for row in conn.execute("SELECT kind, COUNT(*) AS n FROM evidence_head GROUP BY kind")
        }
        by_source = {
            row["source_id"]: row["n"]
            for row in conn.execute(
                "SELECT source_id, COUNT(*) AS n FROM evidence_head GROUP BY source_id"
            )
        }
        versions = conn.execute("SELECT COALESCE(SUM(versions), 0) AS n FROM evidence_head").fetchone()
        dupes = conn.execute(
            "SELECT COUNT(*) AS n FROM evidence_head WHERE duplicate_of <> ''"
        ).fetchone()
        confirmed = conn.execute(
            "SELECT COUNT(*) AS n FROM entity_refs WHERE method IN ('official_id','exact_alias','multi_field')"
        ).fetchone()
        candidates = conn.execute(
            "SELECT COUNT(*) AS n FROM entity_refs WHERE method='candidate'"
        ).fetchone()
        return {
            "evidence_ids": self.table_count("evidence_head"),
            "evidence_versions": int(versions["n"]) if versions else 0,
            "raw_objects": self.table_count("raw_objects"),
            "collection_runs": self.table_count("collection_runs"),
            "request_log": self.table_count("request_log"),
            "duplicate_of": int(dupes["n"]) if dupes else 0,
            "confirmed_entity_links": int(confirmed["n"]) if confirmed else 0,
            "candidate_entity_links": int(candidates["n"]) if candidates else 0,
            "by_kind": by_kind,
            "by_source": by_source,
        }

    def log_requests(self, run_id: str, source_id: str, entries: Iterable[Mapping[str, Any]]) -> int:
        conn = self.connect()
        rows = [
            (
                run_id,
                source_id,
                str(e.get("logged_at", "")),
                str(e.get("url", ""))[:2000],
                e.get("status"),
                int(e.get("bytes", 0) or 0),
                int(e.get("elapsed_ms", 0) or 0),
                int(e.get("attempts", 1) or 1),
                str(e.get("error", ""))[:500],
                str(e.get("note", ""))[:500],
            )
            for e in entries
        ]
        if rows:
            conn.executemany(
                "INSERT INTO request_log(run_id, source_id, logged_at, url, status, bytes,"
                " elapsed_ms, attempts, error, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        return len(rows)


def new_run_id(source_id: str, when: str) -> str:
    """Deterministic-per-minute run id (no uuid, so re-runs are comparable)."""
    stamp = when.replace("-", "").replace(":", "").replace("T", "").split(".")[0]
    return f"run_{source_id}_{stamp}Z"
