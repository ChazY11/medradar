"""Read-only adapter: existing ``events`` table -> TKG assertion store.

MVP contract (Director overrides):

* the source database is opened ``mode=ro`` (+ ``PRAGMA query_only``) and is
  never modified - no migration, no new tables, no writes;
* ``recorded_at`` (knowledge time) is **unconditionally** the actual import
  observation time assigned by the store clock. ``first_seen_at`` and
  ``available_at`` are preserved only as provenance-grade metadata inside the
  event node's ``attrs`` / as optional ``public_time`` - they are not evidence
  of when the system knew anything, and this adapter does **not** claim that a
  source fingerprint proves ``first_seen_at`` was never overwritten;
* a source row missing its identifier or carrying an unparseable
  ``available_at`` is skipped with an explicit counter/error, never guessed;
* entity IDs are the identifiers that already exist in the source
  (``event_id``, ``company_key``, ``track_id``, ``product_code``); relation
  types are conservative containment facts from existing columns only. No
  ownership, technology or competition relations are invented here.

Coverage boundary: this adapter imports *which source rows exist and what
they claim* (existence + stated fields + stated containment). It does not
interpret, deduplicate against the world, or certify public availability.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .store import TKGStore, TKGValidationError, canonical_json, sha256_hex

ADAPTER_VERSION = "events-adapter-1"

_EVENT_COLUMNS = (
    "event_id, source, kind, event_date, company_key, track_id, product_code,"
    " title, url, payload, first_seen_at, available_at, timestamp_quality"
)

# timestamp_quality -> how trustworthy available_at is as *public* metadata.
# Per KIMI_AUDIT H1, batch sources collapse available_at to event_date, so
# anything except a true datetime observation stays "inferred".
_PUBLIC_BASIS = {"datetime": "observed"}


class SourceReadOnlyError(Exception):
    """The adapter attempted anything but a read on the source database."""


def _readonly_uri(path: str | Path) -> str:
    resolved = Path(path).resolve()
    return f"file:{resolved.as_posix()}?mode=ro"


def open_source(path: str | Path) -> sqlite3.Connection:
    """Open a source events database strictly read-only."""
    conn = sqlite3.connect(_readonly_uri(path), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def import_events(
    source: str | Path,
    store: TKGStore,
    kinds: Iterable[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Import events rows from a read-only source into ``store``.

    Returns a report with explicit counters; nothing is written to the source.
    The store assigns ``recorded_at`` at import observation time.
    """
    conn = open_source(source)
    started = datetime.now(timezone.utc)
    counters: dict[str, int] = {
        "rows_seen": 0,
        "assertions_created": 0,
        "idempotent_duplicates": 0,
        "skipped_missing_event_id": 0,
        "skipped_missing_event_date": 0,
        "invalid_public_time_dropped": 0,
        "skipped_invalid_row": 0,
    }
    errors: list[dict[str, str]] = []
    specs: list[dict[str, Any]] = []
    try:
        sql = f"SELECT {_EVENT_COLUMNS} FROM events"
        params: tuple[Any, ...] = ()
        kind_list = [k for k in (kinds or []) if k]
        if kind_list:
            sql += f" WHERE kind IN ({','.join('?' * len(kind_list))})"
            params = tuple(kind_list)
        if limit:
            sql += " LIMIT ?"
            params = (*params, int(limit))
        rows = conn.execute(sql, params).fetchall()

        for row in rows:
            counters["rows_seen"] += 1
            event_id = str(row["event_id"] or "").strip()
            if not event_id:
                counters["skipped_missing_event_id"] += 1
                errors.append({"reason": "missing_event_id", "row": repr(dict(row))[:200]})
                continue
            if not row["event_date"]:
                counters["skipped_missing_event_date"] += 1
                errors.append({"reason": "missing_event_date", "event_id": event_id})
                continue
            public_time, public_basis = _public_metadata(row, counters, errors, event_id)
            locator = str(row["url"] or "").strip() or f"sqlite://events/{event_id}"
            base = {
                "source_locator": locator,
                "evidence_kind": "source_observed",
                "confidence": 1.0,
                "public_time": public_time,
                "public_time_basis": public_basis,
            }
            attrs = {
                "source": row["source"],
                "kind": row["kind"],
                "event_date": row["event_date"],
                "title": row["title"],
                # provenance only: when the source row claims it first saw /
                # made the record available. Not used as a clock, not proof.
                "first_seen_at": row["first_seen_at"],
                "available_at": row["available_at"],
                "timestamp_quality": row["timestamp_quality"],
            }
            # Content-addressed idempotency keys: an identical retry replays
            # the same key (duplicate, no new history), while a source-side
            # correction changes the content hash and becomes a legitimate
            # new revision of the same assertion identity.
            attrs_digest = sha256_hex(canonical_json(attrs))[:12]
            specs.append({
                "record": "node", "node_type": "event", "node_id": event_id,
                "attrs": attrs, "valid_from": row["event_date"],
                "idempotency_key": f"event:{event_id}#{attrs_digest}", **base,
            })
            # Entity stubs assert only "this identifier exists in the source
            # registry" - content is stable across events so re-imports of the
            # same identifier are idempotent duplicates.
            for node_type, node_id in (
                ("company", row["company_key"]),
                ("track", row["track_id"]),
                ("product_code", row["product_code"]),
            ):
                if not node_id:
                    continue
                specs.append({
                    "record": "node", "node_type": node_type, "node_id": str(node_id),
                    "attrs": {}, "valid_from": "1970-01-01",
                    "idempotency_key": f"entity:{node_type}:{node_id}",
                    "source_locator": "sqlite://events-registry",
                    "evidence_kind": "source_observed",
                    "confidence": 1.0,
                })
            if row["company_key"]:
                specs.append(_edge_spec("company_event", "company", row["company_key"],
                                        "event", event_id, row, base))
            if row["track_id"]:
                specs.append(_edge_spec("event_in_track", "event", event_id,
                                        "track", str(row["track_id"]), row, base))
            if row["product_code"]:
                specs.append(_edge_spec("event_has_code", "event", event_id,
                                        "product_code", str(row["product_code"]), row, base))

        # One atomic batch per import: any invalid row rolls back everything.
        results = store.apply(specs)
        for result in results:
            if result["status"] == "created":
                counters["assertions_created"] += 1
            else:
                counters["idempotent_duplicates"] += 1
    except sqlite3.DatabaseError as exc:
        raise SourceReadOnlyError(f"source database must be opened read-only: {exc}") from exc
    finally:
        conn.close()
    return {
        "adapter_version": ADAPTER_VERSION,
        "source_path": str(Path(source).resolve()),
        "source_mode": "ro",
        "imported_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counters": counters,
        "errors": errors,
    }


def _public_metadata(
    row: Mapping[str, Any],
    counters: dict[str, int],
    errors: list[dict[str, str]],
    event_id: str,
) -> tuple[str | None, str | None]:
    """Map ``available_at`` to optional public-time source metadata."""
    raw = str(row["available_at"] or "").strip()
    if not raw:
        return None, None
    try:
        from .store import normalize_moment

        normalized, _ = normalize_moment(raw, "available_at")
    except TKGValidationError:
        counters["invalid_public_time_dropped"] += 1
        errors.append({"reason": "invalid_available_at", "event_id": event_id, "value": raw})
        return None, None
    quality = str(row["timestamp_quality"] or "").strip()
    return normalized, _PUBLIC_BASIS.get(quality, "inferred")


def _edge_spec(
    edge_type: str,
    src_type: str,
    src_id: Any,
    dst_type: str,
    dst_id: Any,
    row: Mapping[str, Any],
    base: Mapping[str, Any],
) -> dict[str, Any]:
    attrs = {"event_date": row["event_date"]}
    digest = sha256_hex(canonical_json({"attrs": attrs, "locator": base["source_locator"]}))[:12]
    return {
        "record": "edge",
        "edge_type": edge_type,
        "src_type": src_type, "src_id": str(src_id),
        "dst_type": dst_type, "dst_id": str(dst_id),
        "attrs": attrs,
        "valid_from": row["event_date"],
        "idempotency_key": f"edge:{edge_type}:{src_type}:{src_id}->{dst_type}:{dst_id}#{digest}",
        **base,
    }
