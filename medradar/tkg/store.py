"""Append-only bitemporal knowledge store (TKG MVP).

Facts are stored as **assertion revisions**, not as one mutable row per entity:

* every row is one version of one assertion about one node or one directed edge;
* ``recorded_at`` (knowledge time) is assigned **inside the store** from the
  store clock at commit time - callers cannot backdate or future-date a write;
* history is physically append-only: SQL ``UPDATE``/``DELETE`` on version
  tables raise via triggers, so a later correction or retraction can never
  rewrite or resurrect-remove an earlier revision;
* retries are safe by explicit ``idempotency_key``: an identical retry returns
  the original revision unchanged, a conflicting reuse of the key fails loudly;
* the write clock is monotonic per store and timestamps are strict
  timezone-aware UTC; an injected test clock is accepted **only** on the
  in-memory store (``":memory:"``) and rejected on persistent production paths.

Only the **system-knowledge clock** exists in this MVP. Public availability
times may ride along as optional, provenance-grade source metadata
(``public_time`` + ``public_time_basis``) but are never used as a clock.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

SCHEMA_VERSION = "tkg-schema-1"

EVIDENCE_KINDS = ("source_observed", "inferred", "reconstructed")
PUBLIC_TIME_BASES = ("observed", "inferred", "unknown")

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TKGError(Exception):
    """Base error for the temporal knowledge graph store."""


class TKGValidationError(TKGError):
    """A record failed content/endpoint/evidence validation."""


class IdempotencyConflict(TKGError):
    """An idempotency key was reused with different content."""


class ClockRegressionError(TKGError):
    """The store clock moved backwards; writes would reorder history."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Monotonicity anchor: the highest recorded_at ever assigned by this store.
CREATE TABLE IF NOT EXISTS clock_guard (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_recorded_at TEXT NOT NULL
);

-- Logical entities: every node/edge identity must exist here (FK target),
-- which makes orphan references a hard foreign-key failure, not silent drift.
CREATE TABLE IF NOT EXISTS entities (
    node_type TEXT NOT NULL,
    node_id   TEXT NOT NULL,
    PRIMARY KEY (node_type, node_id)
);

CREATE TABLE IF NOT EXISTS nodes (
    node_type      TEXT NOT NULL,
    node_id        TEXT NOT NULL,
    attrs          TEXT NOT NULL,
    valid_from     TEXT NOT NULL,
    valid_to       TEXT,
    valid_precision TEXT NOT NULL DEFAULT 'datetime',
    recorded_at    TEXT NOT NULL,
    seq            INTEGER NOT NULL,
    assertion_id   TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    evidence_sha256 TEXT NOT NULL,
    evidence_kind  TEXT NOT NULL,
    confidence     REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    public_time    TEXT,
    public_time_basis TEXT,
    PRIMARY KEY (node_type, node_id, recorded_at, seq),
    FOREIGN KEY (node_type, node_id) REFERENCES entities(node_type, node_id)
);
CREATE INDEX IF NOT EXISTS idx_nodes_recorded ON nodes(recorded_at);

CREATE TABLE IF NOT EXISTS edges (
    edge_type      TEXT NOT NULL,
    src_type       TEXT NOT NULL,
    src_id         TEXT NOT NULL,
    dst_type       TEXT NOT NULL,
    dst_id         TEXT NOT NULL,
    attrs          TEXT NOT NULL,
    valid_from     TEXT NOT NULL,
    valid_to       TEXT,
    valid_precision TEXT NOT NULL DEFAULT 'datetime',
    recorded_at    TEXT NOT NULL,
    seq            INTEGER NOT NULL,
    assertion_id   TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    evidence_sha256 TEXT NOT NULL,
    evidence_kind  TEXT NOT NULL,
    confidence     REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    public_time    TEXT,
    public_time_basis TEXT,
    PRIMARY KEY (edge_type, src_type, src_id, dst_type, dst_id, recorded_at, seq),
    FOREIGN KEY (src_type, src_id) REFERENCES entities(node_type, node_id),
    FOREIGN KEY (dst_type, dst_id) REFERENCES entities(node_type, node_id)
);
CREATE INDEX IF NOT EXISTS idx_edges_recorded ON edges(recorded_at);

CREATE TABLE IF NOT EXISTS idempotency (
    idempotency_key TEXT PRIMARY KEY,
    assertion_id    TEXT NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('node', 'edge')),
    status          TEXT NOT NULL
);

-- ---------------------------------------------------------------- append-only
-- The API never exposes UPDATE/DELETE; these triggers make the invariant
-- physical: even a stray raw SQL session cannot alter recorded history.
CREATE TRIGGER IF NOT EXISTS nodes_no_update BEFORE UPDATE ON nodes
BEGIN SELECT RAISE(ABORT, 'TKG history is append-only: UPDATE rejected'); END;
CREATE TRIGGER IF NOT EXISTS nodes_no_delete BEFORE DELETE ON nodes
BEGIN SELECT RAISE(ABORT, 'TKG history is append-only: DELETE rejected'); END;
CREATE TRIGGER IF NOT EXISTS edges_no_update BEFORE UPDATE ON edges
BEGIN SELECT RAISE(ABORT, 'TKG history is append-only: UPDATE rejected'); END;
CREATE TRIGGER IF NOT EXISTS edges_no_delete BEFORE DELETE ON edges
BEGIN SELECT RAISE(ABORT, 'TKG history is append-only: DELETE rejected'); END;
"""


# --------------------------------------------------------------------- helpers
def canonical_json(obj: Any) -> str:
    """Deterministic serialization: sorted keys, compact separators, no NaN.

    ``allow_nan=False`` makes non-finite floats a hard error - a requirement,
    because NaN/Infinity would break both hashing and JSON round-tripping.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_moment(value: Any, field: str) -> tuple[str, str]:
    """Normalize a time input to strict UTC ISO-8601.

    Returns ``(iso_string, precision)`` where precision is ``"date"`` for
    date-only input (explicitly widened to ``T00:00:00Z``) and ``"datetime"``
    otherwise. Naive datetimes are rejected outright - the caller must state a
    timezone; we never guess one.
    """
    if isinstance(value, datetime):
        moment, precision = value, "datetime"
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise TKGValidationError(f"{field}: naive datetime without timezone is rejected")
    elif isinstance(value, date):
        return value.isoformat() + "T00:00:00Z", "date"
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise TKGValidationError(f"{field}: empty timestamp")
        if _DATE_ONLY.match(text):
            return text + "T00:00:00Z", "date"
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise TKGValidationError(f"{field}: unparseable timestamp {value!r}") from exc
        precision = "datetime"
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise TKGValidationError(f"{field}: naive timestamp without timezone is rejected")
    else:
        raise TKGValidationError(f"{field}: unsupported timestamp type {type(value).__name__}")
    utc = moment.astimezone(timezone.utc)
    rendered = utc.isoformat().replace("+00:00", "Z")
    return rendered, precision


def _validate_confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TKGValidationError(f"confidence must be a finite float in [0,1], got {value!r}")
    confidence = float(value)
    if not math.isfinite(confidence) or confidence < 0.0 or confidence > 1.0:
        raise TKGValidationError(f"confidence must be finite and within [0,1], got {value!r}")
    return confidence


def _validate_attrs(attrs: Any) -> str:
    if not isinstance(attrs, Mapping):
        raise TKGValidationError(f"attrs must be a JSON object, got {type(attrs).__name__}")
    try:
        return canonical_json(dict(attrs))
    except ValueError as exc:
        raise TKGValidationError(f"attrs are not canonically serializable: {exc}") from exc


def _validate_evidence(source_locator: Any, evidence_kind: Any) -> tuple[str, str]:
    locator = str(source_locator or "").strip()
    if not locator:
        raise TKGValidationError("source_locator is required evidence (got empty)")
    kind = str(evidence_kind or "").strip()
    if kind not in EVIDENCE_KINDS:
        raise TKGValidationError(f"evidence_kind must be one of {EVIDENCE_KINDS}, got {evidence_kind!r}")
    return locator, kind


def _validate_public_time(public_time: Any, public_time_basis: Any) -> tuple[str | None, str | None]:
    if public_time is None:
        if public_time_basis not in (None, ""):
            raise TKGValidationError("public_time_basis given without public_time")
        return None, None
    normalized, _ = normalize_moment(public_time, "public_time")
    basis = str(public_time_basis or "").strip()
    if basis not in PUBLIC_TIME_BASES:
        raise TKGValidationError(
            f"public_time_basis must be one of {PUBLIC_TIME_BASES}, got {public_time_basis!r}"
        )
    return normalized, basis


# ----------------------------------------------------------------------- store
class TKGStore:
    """Append-only bitemporal assertion store.

    ``clock`` is an optional callable returning a timezone-aware UTC datetime.
    It exists **only** so tests can build deterministic histories on the
    in-memory store; passing a clock for a persistent (file-backed) path is
    rejected, so production writes always use the real system clock.
    """

    def __init__(
        self,
        path: str | Path = ":memory:",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = str(path)
        if clock is not None and self.path != ":memory:":
            raise TKGError("injected test clock is only allowed on the in-memory store (':memory:')")
        self._clock = clock
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=60)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------------ clock
    def _next_recorded_at(self) -> str:
        if self._clock is not None:
            raw = self._clock()
            if not isinstance(raw, datetime):
                raise ClockRegressionError(f"clock must return datetime, got {type(raw).__name__}")
            candidate, _ = normalize_moment(raw, "clock")
        else:
            candidate, _ = normalize_moment(datetime.now(timezone.utc), "clock")
        row = self.conn.execute("SELECT last_recorded_at FROM clock_guard WHERE id = 1").fetchone()
        last = row[0] if row else None
        if last is not None and candidate < last:
            raise ClockRegressionError(f"store clock regressed: {candidate} < {last}")
        if last != candidate:
            self.conn.execute(
                "INSERT INTO clock_guard (id, last_recorded_at) VALUES (1, ?)"
                " ON CONFLICT(id) DO UPDATE SET last_recorded_at = excluded.last_recorded_at",
                (candidate,),
            )
        return candidate

    # --------------------------------------------------------------- internals
    def _assertion_content(
        self,
        record: str,
        identity: Mapping[str, Any],
        attrs: Mapping[str, Any],
        valid_from: str,
        valid_to: str | None,
        source_locator: str,
        evidence_kind: str,
        confidence: float,
        public_time: str | None,
        public_time_basis: str | None,
    ) -> dict[str, Any]:
        return {
            "record": record,
            **identity,
            "attrs": attrs,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "source_locator": source_locator,
            "evidence_kind": evidence_kind,
            "confidence": confidence,
            "public_time": public_time,
            "public_time_basis": public_time_basis,
        }

    def _check_idempotency(self, key: str, assertion_id: str, kind: str) -> str:
        """Return 'created' or 'duplicate'; raise IdempotencyConflict on mismatch."""
        row = self.conn.execute(
            "SELECT assertion_id, kind FROM idempotency WHERE idempotency_key = ?", (key,)
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO idempotency (idempotency_key, assertion_id, kind, status)"
                " VALUES (?, ?, ?, 'ok')",
                (key, assertion_id, kind),
            )
            return "created"
        if row["assertion_id"] == assertion_id and row["kind"] == kind:
            return "duplicate"
        raise IdempotencyConflict(
            f"idempotency key {key!r} already used for assertion {row['assertion_id']}"
            f" (new content hashes to {assertion_id})"
        )

    def _prepare(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        """Validate one spec and precompute everything the insert needs.

        Runs before any clock read or transaction, so an invalid batch fails
        fast without consuming the write clock.
        """
        record = spec["record"]
        if record not in ("node", "edge"):
            raise TKGValidationError(f"record must be 'node' or 'edge', got {record!r}")
        locator, evidence_kind = _validate_evidence(spec.get("source_locator"), spec.get("evidence_kind"))
        confidence = _validate_confidence(spec.get("confidence"))
        attrs_text = _validate_attrs(spec.get("attrs", {}))
        valid_from, precision = normalize_moment(spec.get("valid_from"), "valid_from")
        valid_to: str | None = None
        if spec.get("valid_to") is not None:
            valid_to, _ = normalize_moment(spec["valid_to"], "valid_to")
            if valid_to <= valid_from:
                raise TKGValidationError(
                    f"valid interval must be non-empty half-open [from, to) with to > from;"
                    f" got [{valid_from}, {valid_to})"
                )
        public_time, public_time_basis = _validate_public_time(
            spec.get("public_time"), spec.get("public_time_basis")
        )
        key = str(spec.get("idempotency_key") or "").strip()
        if not key:
            raise TKGValidationError("idempotency_key is required")

        if record == "node":
            node_type = str(spec.get("node_type") or "").strip()
            node_id = str(spec.get("node_id") or "").strip()
            if not node_type or not node_id:
                raise TKGValidationError("node_type and node_id are required")
            identity = {"node_type": node_type, "node_id": node_id}
            table, kind = "nodes", "node"
        else:
            src_type = str(spec.get("src_type") or "").strip()
            src_id = str(spec.get("src_id") or "").strip()
            dst_type = str(spec.get("dst_type") or "").strip()
            dst_id = str(spec.get("dst_id") or "").strip()
            edge_type = str(spec.get("edge_type") or "").strip()
            if not (src_type and src_id and dst_type and dst_id and edge_type):
                raise TKGValidationError("edge_type, src and dst identities are required")
            identity = {
                "edge_type": edge_type,
                "src_type": src_type,
                "src_id": src_id,
                "dst_type": dst_type,
                "dst_id": dst_id,
            }
            table, kind = "edges", "edge"

        content = self._assertion_content(
            record, identity, dict(spec.get("attrs", {})),
            valid_from, valid_to, locator, evidence_kind, confidence,
            public_time, public_time_basis,
        )
        evidence_sha256 = sha256_hex(canonical_json(content))
        return {
            "record": record, "kind": kind, "table": table, "identity": identity,
            "attrs_text": attrs_text, "valid_from": valid_from, "valid_to": valid_to,
            "precision": precision, "key": key, "locator": locator,
            "evidence_kind": evidence_kind, "confidence": confidence,
            "public_time": public_time, "public_time_basis": public_time_basis,
            "evidence_sha256": evidence_sha256,
            "assertion_id": "sha256:" + evidence_sha256,
        }

    def _apply_prepared(self, prepared: Mapping[str, Any], recorded_at: str) -> dict[str, Any]:
        kind = prepared["kind"]
        table = prepared["table"]
        assertion_id = prepared["assertion_id"]
        status = self._check_idempotency(prepared["key"], assertion_id, kind)
        if status == "duplicate":
            # Identical retry: return the original revision, write nothing new.
            row = self.conn.execute(
                f"SELECT recorded_at, seq FROM {table} WHERE assertion_id = ?", (assertion_id,)
            ).fetchone()
            return {
                "status": "duplicate", "kind": kind, "assertion_id": assertion_id,
                "recorded_at": row["recorded_at"], "seq": row["seq"],
            }

        identity = prepared["identity"]
        try:
            if prepared["record"] == "node":
                seq = self._insert_node(
                    identity, prepared["attrs_text"], prepared["valid_from"],
                    prepared["valid_to"], prepared["precision"], recorded_at, assertion_id,
                    prepared["key"], prepared["locator"], prepared["evidence_sha256"],
                    prepared["evidence_kind"], prepared["confidence"],
                    prepared["public_time"], prepared["public_time_basis"],
                )
            else:
                seq = self._insert_edge(
                    identity, prepared["attrs_text"], prepared["valid_from"],
                    prepared["valid_to"], prepared["precision"], recorded_at, assertion_id,
                    prepared["key"], prepared["locator"], prepared["evidence_sha256"],
                    prepared["evidence_kind"], prepared["confidence"],
                    prepared["public_time"], prepared["public_time_basis"],
                )
        except sqlite3.IntegrityError as exc:
            raise TKGValidationError(f"{kind} insert failed integrity checks: {exc}") from exc
        return {
            "status": "created", "kind": kind, "assertion_id": assertion_id,
            "recorded_at": recorded_at, "seq": seq,
        }

    def _insert_node(self, identity: Mapping[str, str], attrs_text: str, valid_from: str,
                     valid_to: str | None, precision: str, recorded_at: str,
                     assertion_id: str, key: str, locator: str, evidence_sha256: str,
                     evidence_kind: str, confidence: float, public_time: str | None,
                     public_time_basis: str | None) -> int:
        self.conn.execute(
            "INSERT OR IGNORE INTO entities (node_type, node_id) VALUES (?, ?)",
            (identity["node_type"], identity["node_id"]),
        )
        seq = self._next_seq("nodes", "node_type = ? AND node_id = ?", recorded_at,
                             (identity["node_type"], identity["node_id"]))
        columns = (
            "node_type, node_id, attrs, valid_from, valid_to, valid_precision,"
            " recorded_at, seq, assertion_id, idempotency_key, source_locator,"
            " evidence_sha256, evidence_kind, confidence, public_time, public_time_basis"
        )
        self.conn.execute(
            f"INSERT INTO nodes ({columns}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                identity["node_type"], identity["node_id"], attrs_text, valid_from, valid_to,
                precision, recorded_at, seq, assertion_id, key, locator, evidence_sha256,
                evidence_kind, confidence, public_time, public_time_basis,
            ),
        )
        return seq

    def _insert_edge(self, identity: Mapping[str, str], attrs_text: str, valid_from: str,
                     valid_to: str | None, precision: str, recorded_at: str,
                     assertion_id: str, key: str, locator: str, evidence_sha256: str,
                     evidence_kind: str, confidence: float, public_time: str | None,
                     public_time_basis: str | None) -> int:
        seq = self._next_seq(
            "edges",
            "edge_type = ? AND src_type = ? AND src_id = ? AND dst_type = ? AND dst_id = ?",
            recorded_at,
            (identity["edge_type"], identity["src_type"], identity["src_id"],
             identity["dst_type"], identity["dst_id"]),
        )
        columns = (
            "edge_type, src_type, src_id, dst_type, dst_id, attrs, valid_from, valid_to,"
            " valid_precision, recorded_at, seq, assertion_id, idempotency_key,"
            " source_locator, evidence_sha256, evidence_kind, confidence, public_time,"
            " public_time_basis"
        )
        self.conn.execute(
            f"INSERT INTO edges ({columns}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                identity["edge_type"], identity["src_type"], identity["src_id"],
                identity["dst_type"], identity["dst_id"], attrs_text, valid_from, valid_to,
                precision, recorded_at, seq, assertion_id, key, locator, evidence_sha256,
                evidence_kind, confidence, public_time, public_time_basis,
            ),
        )
        return seq

    def _next_seq(self, table: str, where: str, recorded_at: str, params: tuple[Any, ...]) -> int:
        row = self.conn.execute(
            f"SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM {table}"
            f" WHERE {where} AND recorded_at = ?",
            (*params, recorded_at),
        ).fetchone()
        return int(row[0])

    # ------------------------------------------------------------------ writes
    def add_node(self, node_type: str, node_id: str, attrs: Mapping[str, Any] | None = None,
                 **spec: Any) -> dict[str, Any]:
        """Version one node assertion. ``recorded_at`` is assigned by the store."""
        return self.apply([{"record": "node", "node_type": node_type, "node_id": node_id,
                            "attrs": attrs or {}, **spec}])[0]

    def add_edge(self, edge_type: str, src_type: str, src_id: str, dst_type: str, dst_id: str,
                 attrs: Mapping[str, Any] | None = None, **spec: Any) -> dict[str, Any]:
        """Version one directed edge assertion (src -> dst)."""
        return self.apply([{
            "record": "edge", "edge_type": edge_type,
            "src_type": src_type, "src_id": src_id,
            "dst_type": dst_type, "dst_id": dst_id,
            "attrs": attrs or {}, **spec,
        }])[0]

    def apply(self, specs: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Apply a batch atomically: any failure rolls back the whole batch.

        A single ``recorded_at`` is assigned per batch, so a batch is a
        consistent knowledge-time slice; equal timestamps across batches are
        disambiguated by the deterministic ``seq`` column.
        """
        specs = list(specs)
        # Validate everything before touching the clock or the transaction:
        # an invalid batch must fail fast, not consume the write clock.
        prepared = [self._prepare(spec) for spec in specs]
        try:
            self.conn.execute("BEGIN")
            recorded_at = self._next_recorded_at()
            results = [self._apply_prepared(item, recorded_at) for item in prepared]
            self.conn.commit()
            return results
        except Exception:
            self.conn.rollback()
            raise

    # ------------------------------------------------------------------- reads
    def raw(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute(sql, tuple(params)).fetchall()]

    def count(self, table: str) -> int:
        if table not in {"nodes", "edges", "entities", "idempotency"}:
            raise ValueError(f"unknown table {table!r}")
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def meta_get(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def meta_set(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "TKGStore":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
