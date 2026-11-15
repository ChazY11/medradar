"""Resolve the active immutable product data directory.

The product historically shipped one snapshot inside the package. DATA-001 introduces a
pipeline that publishes immutable snapshot directories and switches a small, atomically
replaced ``active.json`` pointer. This module is the single resolution rule shared by the
dataset loader and the data pipeline, so a process can never accidentally read a
half-written snapshot directory.

Resolution order for a supplied path:

1. ``path/snapshot.json`` exists: the path is itself a snapshot directory.
2. ``path/active.json`` exists: read the pointer, require a relative path that stays under
   ``path``, require the target manifest to exist, and return the target.
3. Otherwise the path is returned unchanged so the caller can produce its normal
   "snapshot missing" error.

The pointer carries the snapshot id, content hash and previous snapshot id. It is written
with ``os.replace`` by the publisher; readers therefore see either the complete old pointer
or the complete new one, never a partial JSON document.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ACTIVE_SCHEMA = "medradar.pipeline.active.v1"


class ActivePointerError(ValueError):
    """The active pointer exists but is not safe or not usable."""


def read_active_pointer(root: Path | str) -> dict[str, Any] | None:
    base = Path(root)
    pointer = base / "active.json"
    if not pointer.is_file():
        return None
    try:
        payload = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ActivePointerError("cannot read active pointer " + str(pointer) + ": " + str(error)) from error
    if not isinstance(payload, dict) or payload.get("schema") != ACTIVE_SCHEMA:
        raise ActivePointerError("active pointer has an unsupported schema: " + str(pointer))
    snapshot_id = str(payload.get("snapshot_id") or "")
    relative = str(payload.get("path") or "")
    if not snapshot_id or not relative:
        raise ActivePointerError("active pointer is missing snapshot_id or path: " + str(pointer))
    target = (base / relative).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError as error:
        raise ActivePointerError("active pointer escapes its data root") from error
    manifest = target / "snapshot.json"
    if not manifest.is_file():
        raise ActivePointerError("active pointer target has no snapshot.json: " + str(target))
    try:
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ActivePointerError("cannot read active snapshot manifest: " + str(error)) from error
    if str(manifest_payload.get("id") or "") != snapshot_id:
        raise ActivePointerError(
            "active pointer snapshot_id does not match the target manifest: "
            + snapshot_id
            + " != "
            + str(manifest_payload.get("id"))
        )
    return payload


def resolve_snapshot_dir(path: Path | str) -> Path:
    """Return the immutable snapshot directory for a data root or snapshot path."""
    base = Path(path)
    if (base / "snapshot.json").is_file():
        return base
    pointer = read_active_pointer(base)
    if pointer is not None:
        return (base / str(pointer["path"])).resolve()
    return base
