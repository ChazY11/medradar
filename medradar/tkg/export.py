"""Deterministic point-in-time dataset export.

An export is a **dataset snapshot**, not a predictive benchmark. Given the
same store, cutoffs and versions it is byte-for-byte reproducible:

* nodes and edges are sorted by identity and serialized as canonical JSON
  (sorted keys, compact separators, ``\\n`` line endings, UTF-8, no NaN);
* the manifest carries both cutoffs, the schema/adapter/code versions, the
  selected evidence provenance and the content hash - but **no wall-clock
  generation time**;
* ``snapshot_sha256`` hashes the canonical content, so writes recorded after
  ``known_at`` cannot change a historical export's hash (a whole-live-DB
  fingerprint is deliberately not part of the manifest).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import medradar

from .store import SCHEMA_VERSION, TKGStore, canonical_json, sha256_hex

FORMAT = "medradar-tkg-snapshot"
FORMAT_VERSION = 1


def code_version() -> str:
    return f"medradar-{medradar.__version__}"


def export_snapshot(
    store: TKGStore,
    known_at: Any,
    valid_at: Any = None,
    adapter_version: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic export document for a knowledge cutoff.

    ``known_at`` and ``valid_at`` are independent cutoffs (see
    :class:`medradar.tkg.query.TKGQuery`); ``valid_at=None`` means "no
    valid-time filter". Edge rows carry only node references - node metadata
    in this document comes exclusively from node revisions selected under the
    same cutoffs, so future node attribute writes can never leak into an
    older export.
    """
    from .query import TKGQuery

    snap = TKGQuery(store).snapshot(known_at=known_at, valid_at=valid_at)
    document: dict[str, Any] = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "manifest": {
            "known_at": snap["known_at"],
            "valid_at": snap["valid_at"],
            "schema_version": SCHEMA_VERSION,
            "code_version": code_version(),
            "adapter_version": adapter_version,
            "counts": {"nodes": len(snap["nodes"]), "edges": len(snap["edges"])},
            "evidence_provenance": _evidence_provenance(snap),
        },
        "nodes": snap["nodes"],
        "edges": snap["edges"],
    }
    document["manifest"]["snapshot_sha256"] = sha256_hex(canonical_json(document))
    return document


def _evidence_provenance(snap: dict[str, Any]) -> list[dict[str, Any]]:
    seen: dict[tuple, dict[str, Any]] = {}
    for row in (*snap["nodes"], *snap["edges"]):
        key = (row["assertion_id"], row["source_locator"], row["evidence_sha256"])
        seen[key] = {
            "assertion_id": row["assertion_id"],
            "source_locator": row["source_locator"],
            "evidence_sha256": row["evidence_sha256"],
            "evidence_kind": row["evidence_kind"],
        }
    return [seen[key] for key in sorted(seen)]


def render_json(document: dict[str, Any]) -> str:
    """Stable pretty JSON: sorted keys, two-space indent, trailing newline."""
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def render_jsonl(document: dict[str, Any]) -> dict[str, str]:
    """Canonical JSONL renderings keyed by output file name."""
    lines = {
        "nodes.jsonl": "".join(canonical_json(node) + "\n" for node in document["nodes"]),
        "edges.jsonl": "".join(canonical_json(edge) + "\n" for edge in document["edges"]),
        "manifest.json": json.dumps(
            {
                "format": document["format"],
                "format_version": document["format_version"],
                "manifest": document["manifest"],
            },
            sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False,
        ) + "\n",
    }
    return lines


def write_export(document: dict[str, Any], out_dir: str | Path, jsonl: bool = False) -> dict[str, Path]:
    """Write the export to ``out_dir`` and return the written paths."""
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    if jsonl:
        for name, text in render_jsonl(document).items():
            path = target / name
            path.write_text(text, encoding="utf-8", newline="\n")
            written[name] = path
    else:
        path = target / "snapshot.json"
        path.write_text(render_json(document), encoding="utf-8", newline="\n")
        written["snapshot.json"] = path
    return written
