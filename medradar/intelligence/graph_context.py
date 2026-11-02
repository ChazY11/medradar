"""Read-only graph-context helpers over the bitemporal TKG store.

Purpose: let research code ask "what did the system know, and what was true,
about the observed relations around a (company, track) pair at time T" without
touching the append-only store.

Scope (deliberately conservative, mirroring :mod:`medradar.tkg.adapter`):

* only **observed containment** facts are returned - ``company_event`` (a
  source row lists this company), ``event_in_track`` (the row is filed under
  this track) and ``event_has_code`` (the row names this product code);
* no ownership / technology / competition / investment edges are inferred
  here, and none are fabricated when data is missing;
* the pair context is the set of events that have *both* a ``company_event``
  edge from ``company_key`` and an ``event_in_track`` edge into ``track_id``
  under the same cutoffs, plus the product codes those events name.  Edges are
  only emitted when both endpoints are visible (same endpoint contract as
  :meth:`medradar.tkg.query.TKGQuery.snapshot`).

Semantics: both cutoffs are independent. ``known_at`` gates ``recorded_at``
(system knowledge time); ``valid_at`` gates the half-open valid interval
``[valid_from, valid_to)`` (source event time). ``valid_at=None`` defaults to
``known_at``, exactly like ``TKGQuery.snapshot``. The selection primitives are
reused from :mod:`medradar.tkg.query` so these helpers cannot drift from the
store's snapshot semantics.

Read-only: the store file is opened with ``mode=ro`` and ``PRAGMA query_only``;
no write API is exposed here and the store is never stamped, created or
modified. A missing store file raises :class:`FileNotFoundError`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

from medradar.tkg.query import (  # shared selection primitives (same module family)
    _decode,
    _latest_by_identity,
    _valid_at_cut,
)
from medradar.tkg.store import normalize_moment

__all__ = ["graph_context", "timeline", "counts"]

#: Observed containment relations written by ``medradar.tkg.adapter``.
RELATION_TYPES = ("company_event", "event_in_track", "event_has_code")

_NODE_IDENTITY = ("node_type", "node_id")
_EDGE_IDENTITY = ("edge_type", "src_type", "src_id", "dst_type", "dst_id")
_IN_CHUNK = 400  # stay well under SQLite's bound-parameter limit


class _ReadOnlyStore:
    """Minimal read-only stand-in for :class:`medradar.tkg.store.TKGStore`.

    ``TKGQuery`` only needs ``.raw(sql, params)``; opening the file with
    ``mode=ro`` + ``PRAGMA query_only`` guarantees the helpers cannot mutate it
    even if a future refactor adds a write by mistake.
    """

    def __init__(self, path: str | Path) -> None:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"TKG store not found: {resolved}")
        uri = f"file:{resolved.as_posix()}?mode=ro"
        self.path = resolved
        self.conn = sqlite3.connect(uri, uri=True, timeout=60)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA query_only = ON")

    def raw(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute(sql, tuple(params)).fetchall()]

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "_ReadOnlyStore":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def _select_nodes(
    store: _ReadOnlyStore,
    identities: Iterable[tuple[str, str]],
    known: str,
    valid: str,
) -> list[dict[str, Any]]:
    """Latest revision of each requested node identity visible under the cutoffs."""
    rows: list[dict[str, Any]] = []
    for node_type, node_id in sorted(set(identities)):
        rows.extend(
            store.raw(
                "SELECT * FROM nodes WHERE node_type = ? AND node_id = ? AND recorded_at <= ?",
                (node_type, node_id, known),
            )
        )
    latest = _latest_by_identity(rows, _NODE_IDENTITY)
    latest = {key: row for key, row in latest.items() if _valid_at_cut(row, valid)}
    nodes = [_decode(row, {"node_type": row["node_type"], "node_id": row["node_id"]})
             for row in latest.values()]
    nodes.sort(key=lambda node: (node["node_type"], node["node_id"]))
    return nodes


def _select_edges(
    store: _ReadOnlyStore,
    sql: str,
    params: Sequence[Any],
    known: str,
    valid: str,
) -> list[dict[str, Any]]:
    """Latest revision of a scoped edge query, then the validity filter."""
    rows = store.raw(sql + " AND recorded_at <= ?", (*params, known))
    latest = _latest_by_identity(rows, _EDGE_IDENTITY)
    latest = {key: row for key, row in latest.items() if _valid_at_cut(row, valid)}
    edges = [
        _decode(
            row,
            {
                "edge_type": row["edge_type"],
                "src": {"node_type": row["src_type"], "node_id": row["src_id"]},
                "dst": {"node_type": row["dst_type"], "node_id": row["dst_id"]},
            },
        )
        for row in latest.values()
    ]
    edges.sort(
        key=lambda edge: (
            edge["edge_type"], edge["src"]["node_type"], edge["src"]["node_id"],
            edge["dst"]["node_type"], edge["dst"]["node_id"],
        )
    )
    return edges


def _company_edges(store: _ReadOnlyStore, company_key: str, known: str, valid: str) -> list[dict[str, Any]]:
    # PK prefix (edge_type, src_type, src_id) is indexed.
    return _select_edges(
        store,
        "SELECT * FROM edges WHERE edge_type = 'company_event' AND src_type = 'company' AND src_id = ?",
        (company_key,), known, valid,
    )


def _track_edges(store: _ReadOnlyStore, track_id: str, known: str, valid: str) -> list[dict[str, Any]]:
    # PK prefix (edge_type, src_type) is indexed; dst is a cheap scan of one relation type.
    return _select_edges(
        store,
        "SELECT * FROM edges WHERE edge_type = 'event_in_track' AND src_type = 'event'"
        " AND dst_type = 'track' AND dst_id = ?",
        (track_id,), known, valid,
    )


def _code_edges(store: _ReadOnlyStore, event_ids: Sequence[str], known: str, valid: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ordered = sorted(set(event_ids))
    for start in range(0, len(ordered), _IN_CHUNK):
        chunk = ordered[start:start + _IN_CHUNK]
        placeholders = ",".join("?" * len(chunk))
        rows.extend(
            store.raw(
                f"SELECT * FROM edges WHERE edge_type = 'event_has_code' AND src_type = 'event'"
                f" AND src_id IN ({placeholders}) AND recorded_at <= ?",
                (*chunk, known),
            )
        )
    latest = _latest_by_identity(rows, _EDGE_IDENTITY)
    latest = {key: row for key, row in latest.items() if _valid_at_cut(row, valid)}
    edges = [
        _decode(
            row,
            {
                "edge_type": row["edge_type"],
                "src": {"node_type": row["src_type"], "node_id": row["src_id"]},
                "dst": {"node_type": row["dst_type"], "node_id": row["dst_id"]},
            },
        )
        for row in latest.values()
    ]
    edges.sort(key=lambda edge: (edge["src"]["node_id"], edge["dst"]["node_id"]))
    return edges


def _count_by(rows: Iterable[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row[field]] = counts.get(row[field], 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _collect(store: _ReadOnlyStore, *, company_key: str, track_id: str,
             known: str, valid: str) -> dict[str, Any]:
    company_nodes = _select_nodes(store, [("company", company_key)], known, valid)
    track_nodes = _select_nodes(store, [("track", track_id)], known, valid)
    context: dict[str, Any] = {
        "status": "empty",
        "reason": None,
        "company_key": company_key,
        "track_key": track_id,
        "known_at": known,
        "valid_at": valid,
        "company": company_nodes[0] if company_nodes else None,
        "track": track_nodes[0] if track_nodes else None,
        "nodes": [],
        "edges": [],
        "events": [],
        "products": [],
        "counts": {"nodes": 0, "edges": 0, "events": 0, "products": 0,
                   "by_node_type": {}, "by_edge_type": {}},
    }
    if not company_nodes:
        context["reason"] = "company identity not visible under the cutoffs"
        return context
    if not track_nodes:
        context["reason"] = "track identity not visible under the cutoffs"
        return context

    company_edges = _company_edges(store, company_key, known, valid)
    track_edges = _track_edges(store, track_id, known, valid)
    # company_event edges point company -> event (event is the dst endpoint);
    # event_in_track edges point event -> track (event is the src endpoint).
    pair_event_ids = sorted(
        {edge["dst"]["node_id"] for edge in company_edges}
        & {edge["src"]["node_id"] for edge in track_edges}
    )
    event_nodes = _select_nodes(store, [("event", event_id) for event_id in pair_event_ids], known, valid)
    visible_event_ids = {node["node_id"] for node in event_nodes}
    code_edges = _code_edges(store, visible_event_ids, known, valid) if visible_event_ids else []
    product_ids = sorted({edge["dst"]["node_id"] for edge in code_edges})
    product_nodes = _select_nodes(store, [("product_code", product_id) for product_id in product_ids], known, valid)

    nodes = [*company_nodes, *track_nodes, *event_nodes, *product_nodes]
    nodes.sort(key=lambda node: (node["node_type"], node["node_id"]))
    visible = {(node["node_type"], node["node_id"]) for node in nodes}
    edges = [
        edge for edge in (*company_edges, *track_edges, *code_edges)
        if (edge["src"]["node_type"], edge["src"]["node_id"]) in visible
        and (edge["dst"]["node_type"], edge["dst"]["node_id"]) in visible
    ]
    edges.sort(
        key=lambda edge: (
            edge["edge_type"], edge["src"]["node_type"], edge["src"]["node_id"],
            edge["dst"]["node_type"], edge["dst"]["node_id"],
        )
    )
    context["nodes"] = nodes
    context["edges"] = edges
    context["events"] = event_nodes
    context["products"] = product_nodes
    context["status"] = "ok" if event_nodes else "empty"
    if not event_nodes:
        context["reason"] = "no observed events link this company and this track under the cutoffs"
    context["counts"] = {
        "nodes": len(nodes),
        "edges": len(edges),
        "events": len(event_nodes),
        "products": len(product_nodes),
        "by_node_type": _count_by(nodes, "node_type"),
        "by_edge_type": _count_by(edges, "edge_type"),
    }
    return context


def _cutoffs(known_at: Any, valid_at: Any) -> tuple[str, str]:
    known, _ = normalize_moment(known_at, "known_at")
    effective_valid = normalize_moment(valid_at, "valid_at")[0] if valid_at is not None else known
    return known, effective_valid


def graph_context(
    tkg_path: str | Path,
    *,
    company_key: str,
    track_id: str,
    known_at: Any,
    valid_at: Any = None,
) -> dict[str, Any]:
    """Read-only as-of context for one observed (company, track) pair.

    Returns matching company/track/event/product nodes and the containment
    edges between them, each with ``assertion_id``, valid interval, recorded
    time and evidence provenance. ``status`` is ``"ok"`` when at least one
    event links the pair under the cutoffs, else ``"empty"`` with an explicit
    ``reason``. Deterministic: nodes and edges are sorted by identity.
    """
    company_key = str(company_key or "").strip()
    track_id = str(track_id or "").strip()
    if not company_key or not track_id:
        raise ValueError("company_key and track_id are required (non-empty)")
    known, valid = _cutoffs(known_at, valid_at)
    with _ReadOnlyStore(tkg_path) as store:
        return _collect(store, company_key=company_key, track_id=track_id, known=known, valid=valid)


def timeline(
    tkg_path: str | Path,
    *,
    company_key: str,
    track_id: str,
    known_at: Any,
    valid_at: Any = None,
) -> dict[str, Any]:
    """Sorted event assertions that link the pair, with provenance.

    Timeline order is ``(valid_from, event_id)`` - source event time first, not
    knowledge time - so a later-discovered older event sorts by when it
    happened, while ``recorded_at`` remains visible per row.
    """
    context = graph_context(
        tkg_path, company_key=company_key, track_id=track_id, known_at=known_at, valid_at=valid_at,
    )
    events = sorted(context.get("events", []), key=lambda node: (node["valid_from"], node["node_id"]))
    rows = [
        {
            "event_id": node["node_id"],
            "valid_from": node["valid_from"],
            "valid_to": node["valid_to"],
            "recorded_at": node["recorded_at"],
            "seq": node["seq"],
            "assertion_id": node["assertion_id"],
            "source_locator": node["source_locator"],
            "evidence_sha256": node["evidence_sha256"],
            "evidence_kind": node["evidence_kind"],
            "confidence": node["confidence"],
            "attrs": node["attrs"],
        }
        for node in events
    ]
    return {
        "status": context["status"],
        "reason": context["reason"],
        "company_key": context["company_key"],
        "track_key": context["track_key"],
        "known_at": context["known_at"],
        "valid_at": context["valid_at"],
        "count": len(rows),
        "events": rows,
    }


_NODE_COUNT_SQL = (
    "SELECT node_type, COUNT(*) AS visible FROM ("
    "  SELECT node_type, node_id, valid_from, valid_to,"
    "         ROW_NUMBER() OVER (PARTITION BY node_type, node_id"
    "                            ORDER BY recorded_at DESC, seq DESC) AS rn"
    "  FROM nodes WHERE recorded_at <= ?"
    ") WHERE rn = 1 AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"
    " GROUP BY node_type ORDER BY node_type"
)
_EDGE_COUNT_SQL = (
    "SELECT edge_type, COUNT(*) AS visible FROM ("
    "  SELECT edge_type, src_type, src_id, dst_type, dst_id, valid_from, valid_to,"
    "         ROW_NUMBER() OVER (PARTITION BY edge_type, src_type, src_id, dst_type, dst_id"
    "                            ORDER BY recorded_at DESC, seq DESC) AS rn"
    "  FROM edges WHERE recorded_at <= ?"
    ") WHERE rn = 1 AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"
    " GROUP BY edge_type ORDER BY edge_type"
)


def counts(tkg_path: str | Path, *, known_at: Any, valid_at: Any = None) -> dict[str, Any]:
    """Visible-node/edge summary of the whole store under independent cutoffs.

    Counts use the same latest-revision-then-validity rule as the snapshot path
    (SQL window functions, no full-graph materialisation), so
    ``counts(...)["nodes"]["total"]`` equals ``len(snapshot(...)["nodes"])``.
    ``revisions`` reports how many stored assertion revisions existed by
    ``known_at`` (history size, not visible identities).
    """
    known, valid = _cutoffs(known_at, valid_at)
    with _ReadOnlyStore(tkg_path) as store:
        node_rows = store.raw(_NODE_COUNT_SQL, (known, valid, valid))
        edge_rows = store.raw(_EDGE_COUNT_SQL, (known, valid, valid))
        node_revisions = store.raw("SELECT COUNT(*) AS n FROM nodes WHERE recorded_at <= ?", (known,))[0]["n"]
        edge_revisions = store.raw("SELECT COUNT(*) AS n FROM edges WHERE recorded_at <= ?", (known,))[0]["n"]
    nodes = {row["node_type"]: int(row["visible"]) for row in node_rows}
    edges = {row["edge_type"]: int(row["visible"]) for row in edge_rows}
    return {
        "status": "ok",
        "known_at": known,
        "valid_at": valid,
        "nodes": {**nodes, "total": sum(nodes.values())},
        "edges": {**edges, "total": sum(edges.values())},
        "revisions": {"nodes": int(node_revisions), "edges": int(edge_revisions)},
        "relations": list(RELATION_TYPES),
    }
