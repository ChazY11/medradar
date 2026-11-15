"""Atomic publication and rollback.

The only switch users observe is ``active.json``. It is replaced atomically, so a reader
sees either the complete old pointer or the complete new pointer. Snapshot directories are
content-addressed and are never edited after publication.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from medradar.product.data_dir import ACTIVE_SCHEMA, read_active_pointer

from .config import Settings
from .db import StateStore


class PublicationError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass


def active_snapshot(settings: Settings) -> tuple[Path, dict[str, Any], dict[str, Any]] | None:
    pointer = read_active_pointer(settings.root)
    if pointer is None:
        return None
    path = (settings.root / str(pointer["path"])).resolve()
    manifest = json.loads((path / "snapshot.json").read_text(encoding="utf-8"))
    return path, manifest, pointer


def write_active_pointer(
    settings: Settings,
    snapshot_dir: Path,
    manifest: dict[str, Any],
    *,
    previous_snapshot_id: str | None,
    action: str,
    actor: str,
) -> dict[str, Any]:
    base = settings.root.resolve()
    target = snapshot_dir.resolve()
    try:
        relative = target.relative_to(base)
    except ValueError as error:
        raise PublicationError("snapshot directory is outside the pipeline root") from error
    if not (target / "snapshot.json").is_file():
        raise PublicationError("snapshot has no manifest: " + str(target))
    pointer = {
        "schema": ACTIVE_SCHEMA,
        "snapshot_id": str(manifest.get("id") or ""),
        "path": str(relative),
        "content_hash": (manifest.get("lineage") or {}).get("content_hash"),
        "previous_snapshot_id": previous_snapshot_id,
        "published_at": _now(),
        "published_by": actor,
        "action": action,
    }
    temporary = settings.active_pointer.with_name("active.json.tmp")
    payload = (json.dumps(pointer, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, settings.active_pointer)
    _fsync_dir(settings.root)
    return pointer


def commit_publication(
    store: StateStore,
    settings: Settings,
    *,
    snapshot_dir: Path,
    manifest: dict[str, Any],
    run_id: str | None,
    previous_snapshot_id: str | None,
    action: str,
    actor: str,
    note: str | None = None,
    published_at: str | None = None,
) -> dict[str, Any]:
    """Switch the pointer first, then commit the database journal.

    A crash between those two steps leaves the new pointer active while the DB still says
    staged. ``recover_publication`` notices this on the next operation and completes the
    database side. The reverse order is never used: the API would otherwise report a
    publication that users cannot see.
    """
    snapshot_id = str(manifest.get("id") or "")
    pointer = write_active_pointer(
        settings, snapshot_dir, manifest,
        previous_snapshot_id=previous_snapshot_id, action=action, actor=actor,
    )
    moment = published_at or pointer["published_at"]
    try:
        with store.transaction() as connection:
            previous = connection.execute(
                "SELECT snapshot_id FROM snapshots WHERE is_active = 1 AND snapshot_id != ?",
                (snapshot_id,),
            ).fetchall()
            connection.execute("UPDATE snapshots SET is_active = 0")
            connection.execute(
                "UPDATE snapshots SET status = 'published', is_active = 1,"
                " published_at = COALESCE(published_at, ?) WHERE snapshot_id = ?",
                (moment, snapshot_id),
            )
            for row in previous:
                connection.execute(
                    "UPDATE snapshots SET status = 'superseded' WHERE snapshot_id = ?",
                    (row["snapshot_id"],),
                )
            if run_id:
                connection.execute(
                    "UPDATE changes SET status = 'published', published_at = ?"
                    " WHERE run_id = ? AND candidate_snapshot_id = ? AND status = 'staged'",
                    (moment, run_id, snapshot_id),
                )
            connection.execute(
                "UPDATE sources SET active_snapshot_id = ?", (snapshot_id,)
            )
            connection.execute(
                "INSERT INTO publications(publication_id, snapshot_id, previous_snapshot_id,"
                " published_at, action, actor, note) VALUES(?,?,?,?,?,?,?)",
                ("pub_" + uuid.uuid4().hex, snapshot_id, previous_snapshot_id,
                 moment, action, actor, note),
            )
    except Exception:
        # The pointer is already new. Leave a recovery marker in the DB for the next run.
        try:
            store.record_incident("publication_db_commit_failed", {
                "snapshot_id": snapshot_id,
                "previous_snapshot_id": previous_snapshot_id,
                "action": action,
                "pointer_written": True,
            })
        except Exception:
            pass
        raise
    return pointer


def recover_publication(store: StateStore, settings: Settings) -> dict[str, Any] | None:
    """Finish a DB commit that was interrupted after the pointer switch."""
    active = active_snapshot(settings)
    if active is None:
        return None
    path, manifest, pointer = active
    snapshot_id = str(manifest.get("id") or "")
    record = store.get_snapshot(snapshot_id)
    if record is None:
        return None
    if record.get("status") == "published" and record.get("is_active"):
        return None
    moment = str(pointer.get("published_at") or _now())
    with store.transaction() as connection:
        previous = connection.execute(
            "SELECT snapshot_id FROM snapshots WHERE is_active = 1 AND snapshot_id != ?",
            (snapshot_id,),
        ).fetchall()
        connection.execute("UPDATE snapshots SET is_active = 0")
        connection.execute(
            "UPDATE snapshots SET status = 'published', is_active = 1,"
            " published_at = COALESCE(published_at, ?) WHERE snapshot_id = ?",
            (moment, snapshot_id),
        )
        for row in previous:
            connection.execute("UPDATE snapshots SET status = 'superseded' WHERE snapshot_id = ?", (row["snapshot_id"],))
        connection.execute("UPDATE changes SET status = 'published', published_at = ? WHERE candidate_snapshot_id = ? AND status = 'staged'", (moment, snapshot_id))
        connection.execute("UPDATE sources SET active_snapshot_id = ?", (snapshot_id,))
        connection.execute(
            "INSERT INTO publications(publication_id, snapshot_id, previous_snapshot_id,"
            " published_at, action, actor, note) VALUES(?,?,?,?,?,?,?)",
            ("pub_" + uuid.uuid4().hex, snapshot_id, pointer.get("previous_snapshot_id"),
             moment, "recovery", "pipeline", "completed after interrupted publication"),
        )
    return {"recovered": True, "snapshot_id": snapshot_id}


def rollback(store: StateStore, settings: Settings, target_snapshot_id: str, *, actor: str,
             note: str | None = None, validate: bool = True) -> dict[str, Any]:
    from .validator import validate_snapshot

    target = settings.snapshots_dir / target_snapshot_id
    manifest_path = target / "snapshot.json"
    if not manifest_path.is_file():
        raise PublicationError("rollback target does not exist: " + target_snapshot_id)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if str(manifest.get("id") or "") != target_snapshot_id:
        raise PublicationError("rollback target manifest id does not match the requested id")
    if validate:
        report = validate_snapshot(target, settings=settings, previous_dir=None, validate_product=True)
        if not report.ok:
            raise PublicationError("rollback target failed validation: " + json.dumps(report.to_public()["errors"][:5]))
    current = active_snapshot(settings)
    previous_id = str((current[1].get("id") if current else None) or "")
    pointer = commit_publication(
        store, settings, snapshot_dir=target, manifest=manifest, run_id=None,
        previous_snapshot_id=previous_id or None, action="rollback", actor=actor,
        note=note, published_at=_now(),
    )
    return {"rollback": True, "snapshot_id": target_snapshot_id, "previous_snapshot_id": previous_id or None, "pointer": pointer}
