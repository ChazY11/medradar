"""Snapshot manifests: make "what did we believe on date X" auditable.

A frozen snapshot is only worth something if it can be verified later. This module builds and checks
manifests: canonical JSON for every artifact, a SHA-256 per artifact, a SHA-256 per input source, the
as-of date and the window. It is pure computation (no filesystem, no database), so the hashing rules
are unit-tested and the scripts that do I/O stay trivial.

    manifest = build_manifest(as_of="2026-11-03", window=("2016-11", "2026-09"),
                              artifacts={"profiles": payload},
                              sources={"data/research.sqlite": sha256_of_file},
                              notes=("...",))
    problems = verify_manifest(manifest, artifacts={"profiles": payload})
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

MANIFEST_SCHEMA = "snapshot_manifest_v1"


def canonical_json(value: Any) -> str:
    """Canonical JSON: sorted keys, no insignificant whitespace, UTF-8 safe."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def content_hash(value: Any) -> str:
    """SHA-256 of the canonical JSON encoding of ``value``."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_manifest(*, as_of: str, window: Sequence[str],
                   artifacts: Mapping[str, Any],
                   sources: Mapping[str, str] | None = None,
                   notes: Sequence[str] = ()) -> dict[str, Any]:
    """Assemble a manifest describing every artifact and input source of the snapshot.

    ``sources`` maps a source name to its SHA-256 (computed by the caller, which owns the file I/O).
    The manifest deliberately records *hashes*, not contents: it is a witness, not a copy.
    """
    if not as_of or len(str(as_of)) < 10:
        raise ValueError("as_of must be an ISO date (YYYY-MM-DD)")
    if len(window) != 2 or not all(window):
        raise ValueError("window must be (start, end)")
    if not artifacts:
        raise ValueError("a snapshot needs at least one artifact")
    artifact_hashes = {name: content_hash(value) for name, value in sorted(artifacts.items())}
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "as_of": str(as_of),
        "window": {"start": window[0], "end": window[1]},
        "artifacts": artifact_hashes,
        "artifact_sizes": {name: len(canonical_json(value)) for name, value in
                           sorted(artifacts.items())},
        "sources": dict(sorted((sources or {}).items())),
        "notes": list(notes),
        "artifact_count": len(artifact_hashes),
    }
    manifest["manifest_hash"] = content_hash(manifest)
    return manifest


def verify_manifest(manifest: Mapping[str, Any],
                    *, artifacts: Mapping[str, Any]) -> list[str]:
    """Recompute hashes and return every mismatch; an empty list means the snapshot verifies."""
    problems: list[str] = []
    if manifest.get("schema") != MANIFEST_SCHEMA:
        problems.append(f"unexpected manifest schema: {manifest.get('schema')!r}")
    recorded = manifest.get("artifacts") or {}
    for name, value in artifacts.items():
        actual = content_hash(value)
        expected = recorded.get(name)
        if expected is None:
            problems.append(f"artifact not recorded in manifest: {name}")
        elif actual != expected:
            problems.append(f"artifact hash mismatch for {name}")
    for name in recorded:
        if name not in artifacts:
            problems.append(f"manifest lists an artifact that is missing: {name}")
    body = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if manifest.get("manifest_hash") != content_hash(body):
        problems.append("manifest hash does not match its own content")
    if not manifest.get("sources"):
        problems.append("manifest records no input source hashes")
    return problems


def is_iso_date(value: str) -> bool:
    """Cheap structural check for YYYY-MM-DD (no calendar validation, deliberately)."""
    if len(value) != 10 or value[4] != "-" or value[7] != "-":
        return False
    return value[:4].isdigit() and value[5:7].isdigit() and value[8:10].isdigit()
