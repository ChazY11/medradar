"""As-of queries over the append-only bitemporal store.

Query semantics (system-knowledge clock only in this MVP):

1. ``known_at`` gates ``recorded_at``: only revisions the system had recorded
   at ``known_at`` are candidates.
2. Per assertion identity (a node, or one directed edge), the **latest**
   revision visible at ``known_at`` is selected first - by
   ``(recorded_at, seq)``.
3. Only then is the optional ``valid_at`` cutoff applied to the *selected*
   revision's half-open valid interval ``[valid_from, valid_to)``.

The order matters: applying the valid filter before picking the latest
revision would resurrect old revisions that a later correction or retraction
had already superseded (a later retraction never brings an older revision
back to life).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .store import TKGStore, normalize_moment


def _latest_by_identity(rows: Iterable[Mapping[str, Any]], key_fields: tuple[str, ...]) -> dict[tuple, dict[str, Any]]:
    """Keep, per identity, the revision with the greatest (recorded_at, seq)."""
    latest: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        key = tuple(row[field] for field in key_fields)
        current = latest.get(key)
        if current is None or (row["recorded_at"], row["seq"]) > (current["recorded_at"], current["seq"]):
            latest[key] = dict(row)
    return latest


def _valid_at_cut(row: Mapping[str, Any], valid_at: str) -> bool:
    if row["valid_from"] > valid_at:
        return False
    return row["valid_to"] is None or row["valid_to"] > valid_at


def _decode(row: Mapping[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    import json

    return {
        **identity,
        "attrs": json.loads(row["attrs"]),
        "valid_from": row["valid_from"],
        "valid_to": row["valid_to"],
        "valid_precision": row["valid_precision"],
        "recorded_at": row["recorded_at"],
        "seq": row["seq"],
        "assertion_id": row["assertion_id"],
        "source_locator": row["source_locator"],
        "evidence_sha256": row["evidence_sha256"],
        "evidence_kind": row["evidence_kind"],
        "confidence": row["confidence"],
        "public_time": row["public_time"],
        "public_time_basis": row["public_time_basis"],
    }


class TKGQuery:
    """Read-only as-of access to a :class:`TKGStore`."""

    def __init__(self, store: TKGStore) -> None:
        self.store = store

    # ------------------------------------------------------------------ nodes
    def _node_rows(self, known_at: str) -> list[dict[str, Any]]:
        return self.store.raw("SELECT * FROM nodes WHERE recorded_at <= ?", (known_at,))

    def latest_node_revisions(self, known_at: Any, valid_at: Any = None) -> list[dict[str, Any]]:
        """The revision of every node assertion visible at ``known_at``.

        With ``valid_at`` set, only revisions whose valid interval covers
        ``valid_at`` survive; with ``valid_at=None`` every latest revision is
        returned regardless of validity.
        """
        known, _ = normalize_moment(known_at, "known_at")
        latest = _latest_by_identity(self._node_rows(known), ("node_type", "node_id"))
        if valid_at is None:
            selected = latest.values()
        else:
            valid, _ = normalize_moment(valid_at, "valid_at")
            selected = [row for row in latest.values() if _valid_at_cut(row, valid)]
        nodes = [
            _decode(row, {"node_type": row["node_type"], "node_id": row["node_id"]})
            for row in selected
        ]
        nodes.sort(key=lambda n: (n["node_type"], n["node_id"]))
        return nodes

    # ------------------------------------------------------------------ edges
    def _edge_rows(self, known_at: str) -> list[dict[str, Any]]:
        return self.store.raw("SELECT * FROM edges WHERE recorded_at <= ?", (known_at,))

    def latest_edge_revisions(self, known_at: Any, valid_at: Any = None) -> list[dict[str, Any]]:
        """Latest revision of every directed edge assertion visible at ``known_at``.

        Edge rows reference their endpoint nodes; node metadata is *never*
        joined here, so an edge view cannot leak node attributes from revisions
        recorded after ``known_at`` (see the exporter, which pairs edges with
        the node revisions selected under the same cutoffs).
        """
        known, _ = normalize_moment(known_at, "known_at")
        identity = ("edge_type", "src_type", "src_id", "dst_type", "dst_id")
        latest = _latest_by_identity(self._edge_rows(known), identity)
        if valid_at is None:
            selected = latest.values()
        else:
            valid, _ = normalize_moment(valid_at, "valid_at")
            selected = [row for row in latest.values() if _valid_at_cut(row, valid)]
        edges = [
            _decode(
                row,
                {
                    "edge_type": row["edge_type"],
                    "src": {"node_type": row["src_type"], "node_id": row["src_id"]},
                    "dst": {"node_type": row["dst_type"], "node_id": row["dst_id"]},
                },
            )
            for row in selected
        ]
        edges.sort(
            key=lambda e: (
                e["edge_type"], e["src"]["node_type"], e["src"]["node_id"],
                e["dst"]["node_type"], e["dst"]["node_id"],
            )
        )
        return edges

    # --------------------------------------------------------------- snapshot
    def snapshot(self, known_at: Any = None, valid_at: Any = None) -> dict[str, Any]:
        """Full as-of snapshot: one selected revision per node and per edge.

        ``known_at=None`` means "everything recorded so far" (now). ``valid_at``
        defaults to ``known_at`` - the intuitive "what was true and known at T"
        reading - but the two cutoffs are independent inputs everywhere else.

        **Endpoint contract**: an edge is emitted only if *both* endpoints are
        visible among the nodes selected under the same ``(known_at, valid_at)``
        cutoffs. Nodes and edges are versioned as separate assertion lineages,
        so an edge's own selected revision can survive while an endpoint's does
        not (retraction, not-yet-valid window, endpoint never recorded under
        this cutoff). Such an edge is *excluded* - never emitted with a
        dangling reference, never patched with future node metadata, and the
        node is never resurrected just to justify the edge.
        """
        if known_at is None:
            known_at = datetime.now(timezone.utc)
        known, _ = normalize_moment(known_at, "known_at")
        effective_valid = valid_at if valid_at is not None else known
        nodes = self.latest_node_revisions(known, effective_valid)
        node_keys = {(n["node_type"], n["node_id"]) for n in nodes}
        edges = [
            e for e in self.latest_edge_revisions(known, effective_valid)
            if (e["src"]["node_type"], e["src"]["node_id"]) in node_keys
            and (e["dst"]["node_type"], e["dst"]["node_id"]) in node_keys
        ]
        return {
            "known_at": known,
            "valid_at": normalize_moment(effective_valid, "valid_at")[0] if effective_valid else None,
            "nodes": nodes,
            "edges": edges,
        }
