"""Canonical snapshot/hash helpers + revision queries for the evidence ledger.

This module is deliberately independent of :mod:`medradar.db` so that
``medradar.db`` can import it without a cycle. It never writes anything except
:func:`append_revision` (which the DB write path calls inside its transaction).

Two different hashes exist on purpose:

``content_hash``
    sha256 over the *content fields* of the snapshot, i.e. everything that
    constitutes what the source asserted. Volatile bookkeeping columns
    (``first_seen_at``, ``fetched_at``, ``as_of``) are excluded, otherwise an
    identical re-import would always look like a change and idempotency would
    be impossible.

``snapshot``
    canonical JSON of the **full** event row as written, including the volatile
    columns. This is what an auditor reads to recover the old values; its hash
    is *not* the content hash.

Both are deterministic for the same input dict (sorted keys, compact
separators, ``allow_nan=False``, UTF-8).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Iterable, Mapping

#: All columns of one ``events`` row (``medradar.db.EVENT_FIELDS`` duplicated
#: here so this module stays importable without ``medradar.db``).
EVENT_SNAPSHOT_FIELDS: tuple[str, ...] = (
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

#: Fields excluded from the identity hash: they change on every fetch/retry and
#: must not make an identical re-import look like a content revision.
VOLATILE_FIELDS: frozenset[str] = frozenset({"first_seen_at", "fetched_at", "as_of"})

EVENT_CONTENT_FIELDS: tuple[str, ...] = tuple(
    field for field in EVENT_SNAPSHOT_FIELDS if field not in VOLATILE_FIELDS
)

HISTORY_COMPLETENESS = (
    "complete",              # event created after the ledger existed
    "partial_before_ledger",  # live revision of an event whose v1 is a legacy baseline
    "baseline_only",         # the single legacy snapshot seeded at migration
)
ORIGINS = ("live", "legacy_baseline")


def canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, compact separators, no NaN/Infinity."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot_of_row(row: Any, fields: Iterable[str] = EVENT_SNAPSHOT_FIELDS) -> dict[str, Any]:
    """Project a mapping or ``sqlite3.Row`` onto the snapshot fields."""
    if isinstance(row, sqlite3.Row):
        available = set(row.keys())
        return {field: (row[field] if field in available else None) for field in fields}
    return {field: row.get(field) for field in fields}


def content_hash(snapshot: Mapping[str, Any]) -> str:
    """Identity hash of the content fields of one event snapshot."""
    content = {field: snapshot.get(field) for field in EVENT_CONTENT_FIELDS}
    return sha256_hex(canonical_json(content))


def snapshot_json(snapshot: Mapping[str, Any]) -> str:
    return canonical_json({field: snapshot.get(field) for field in EVENT_SNAPSHOT_FIELDS})


def append_revision(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    version: int,
    snapshot: Mapping[str, Any],
    revision_reason: str,
    origin: str,
    history_completeness: str,
    recorded_at: str,
    prev_content_hash: str | None = None,
) -> dict[str, Any]:
    """Append one immutable revision. Must run inside the caller's transaction.

    The primary key ``(event_id, version)`` plus the resubmit trigger make a
    duplicate append a hard ``sqlite3.IntegrityError``/abort instead of a
    silent overwrite.
    """
    if origin not in ORIGINS:
        raise ValueError(f"origin must be one of {ORIGINS}, got {origin!r}")
    if history_completeness not in HISTORY_COMPLETENESS:
        raise ValueError(
            f"history_completeness must be one of {HISTORY_COMPLETENESS}, got {history_completeness!r}"
        )
    digest = content_hash(snapshot)
    conn.execute(
        "INSERT INTO event_revision("
        " event_id, version, snapshot, content_hash, prev_content_hash, revision_reason,"
        " source, origin, history_completeness, recorded_at, first_seen_at, available_at,"
        " timestamp_quality) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            event_id,
            version,
            snapshot_json(snapshot),
            digest,
            prev_content_hash,
            revision_reason,
            str(snapshot.get("source") or ""),
            origin,
            history_completeness,
            recorded_at,
            snapshot.get("first_seen_at") or "",
            snapshot.get("available_at"),
            snapshot.get("timestamp_quality"),
        ),
    )
    return {"event_id": event_id, "version": version, "content_hash": digest}


def _decode(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    record = dict(row)
    snapshot = record.get("snapshot")
    if isinstance(snapshot, str):
        record["snapshot"] = json.loads(snapshot)
    return record


def latest_revision(conn: sqlite3.Connection, event_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM event_revision WHERE event_id=? ORDER BY version DESC LIMIT 1",
        (event_id,),
    ).fetchone()
    return _decode(row) if row is not None else None


def revisions_for(conn: sqlite3.Connection, event_id: str) -> list[dict[str, Any]]:
    return [
        _decode(row)
        for row in conn.execute(
            "SELECT * FROM event_revision WHERE event_id=? ORDER BY version ASC", (event_id,)
        )
    ]


def revision_count(conn: sqlite3.Connection, event_id: str | None = None) -> int:
    if event_id is None:
        return int(conn.execute("SELECT COUNT(*) FROM event_revision").fetchone()[0])
    return int(
        conn.execute("SELECT COUNT(*) FROM event_revision WHERE event_id=?", (event_id,)).fetchone()[0]
    )


def reconcile(conn: sqlite3.Connection, limit: int = 20) -> dict[str, Any]:
    """Compare the ``events`` head rows with their latest ledger revision.

    Detects (a) a head row changed by direct SQL/``INSERT OR REPLACE`` while the
    ledger kept the old hash and (b) rows present in ``events`` with no
    revision. Orphan revisions (ledger row with no head) are reported too.

    It does **not** detect a dropped trigger followed by a ledger rewrite, nor a
    whole-file replacement: those leave a self-consistent (forged) file.
    """
    mismatched: list[dict[str, Any]] = []
    missing: list[str] = []
    latest: dict[str, dict[str, Any]] = {}
    # Latest revision per event, without decoding the full snapshot: a whole-
    # database reconcile (375k events) must stay memory-bounded.
    for row in conn.execute(
        "SELECT event_id, version, content_hash, origin, history_completeness FROM ("
        "  SELECT event_id, version, content_hash, origin, history_completeness,"
        "         ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY version DESC) AS rn"
        "  FROM event_revision"
        ") WHERE rn = 1"
    ):
        latest[str(row["event_id"])] = {
            "event_id": str(row["event_id"]),
            "version": int(row["version"]),
            "content_hash": str(row["content_hash"]),
            "origin": str(row["origin"]),
            "history_completeness": str(row["history_completeness"]),
        }
    for row in conn.execute("SELECT * FROM events"):
        event_id = str(row["event_id"])
        revision = latest.get(event_id)
        if revision is None:
            missing.append(event_id)
            continue
        head_hash = content_hash(snapshot_of_row(row))
        if head_hash != revision["content_hash"]:
            mismatched.append({
                "event_id": event_id,
                "head_content_hash": head_hash,
                "ledger_content_hash": revision["content_hash"],
                "ledger_version": revision["version"],
                "ledger_origin": revision["origin"],
            })
    head_ids = {str(row[0]) for row in conn.execute("SELECT event_id FROM events")}
    orphans = sorted(set(latest) - head_ids)
    return {
        "events_rows": len(head_ids),
        "revisioned_events": len(latest),
        "head_mismatch_count": len(mismatched),
        "missing_revision_count": len(missing),
        "orphan_revision_count": len(orphans),
        "head_mismatch_sample": mismatched[:limit],
        "missing_revision_sample": missing[:limit],
        "orphan_revision_sample": orphans[:limit],
        "ok": not mismatched and not missing and not orphans,
    }
