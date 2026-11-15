"""Consistent backup and isolated restore for pipeline state.

A same-host backup is useful for operational recovery, but it is not a complete disaster
recovery strategy. The manifest states that limitation explicitly. The pipeline database is
copied with SQLite's backup API (not a file copy), and every restored snapshot is revalidated
before the restore is reported as successful.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .config import PIPELINE_VERSION, Settings
from .lock import PipelineLock
from .validator import validate_snapshot

BACKUP_SCHEMA = "medradar.data_backup.v1"
MANIFEST = "backup.json"


class BackupError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_copy(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_uri = source.resolve().as_uri() + "?mode=ro"
    src = sqlite3.connect(source_uri, uri=True, timeout=30)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
        dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        dst.close()
        src.close()
    if integrity != "ok":
        raise BackupError("SQLite backup failed integrity check: " + str(integrity))
    return {"sha256": _sha256(destination), "bytes": destination.stat().st_size, "integrity": integrity}


def _copy_tree(source: Path, destination: Path, files: list[dict[str, Any]], prefix: str = "") -> None:
    if not source.is_dir():
        return
    for path in sorted(source.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        files.append({
            "path": (prefix + "/" + relative.as_posix()).lstrip("/"),
            "sha256": _sha256(target),
            "bytes": target.stat().st_size,
        })


def backup(
    settings: Settings,
    destination: Path | str,
    *,
    review_db: Path | str | None = None,
    include_all_snapshots: bool = True,
) -> dict[str, Any]:
    """Create a timestamped, self-describing backup directory.

    The pipeline lock is held while the active pointer and database are captured, so a
    concurrent publish cannot produce a pointer/DB pair from different generations.
    """
    settings.ensure()
    destination_root = Path(destination)
    destination_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = destination_root / ("data-backup-" + stamp + "-" + uuid.uuid4().hex[:6])
    archive.mkdir()
    files: list[dict[str, Any]] = []
    lock = PipelineLock(settings.lock_path, timeout_seconds=60)
    try:
        with lock:
            pointer_path = settings.active_pointer
            pointer_payload = None
            if pointer_path.is_file():
                pointer_payload = json.loads(pointer_path.read_text(encoding="utf-8"))
                target = archive / "active.json"
                shutil.copy2(pointer_path, target)
                files.append({"path": "active.json", "sha256": _sha256(target), "bytes": target.stat().st_size})

            db_info = None
            if settings.state_db.is_file():
                db_info = _sqlite_copy(settings.state_db, archive / "pipeline.db")
                files.append({"path": "pipeline.db", **db_info})

            snapshots_dir = archive / "snapshots"
            snapshot_ids: list[str] = []
            if settings.snapshots_dir.is_dir():
                for snapshot in sorted(settings.snapshots_dir.iterdir()):
                    if not snapshot.is_dir():
                        continue
                    if not include_all_snapshots:
                        active_id = str((pointer_payload or {}).get("snapshot_id") or "")
                        if snapshot.name != active_id:
                            continue
                    _copy_tree(snapshot, snapshots_dir / snapshot.name, files, "snapshots/" + snapshot.name)
                    snapshot_ids.append(snapshot.name)

            review_path = Path(review_db) if review_db is not None else settings.review_db
            review_info = None
            if review_path is not None and Path(review_path).is_file():
                review_info = _sqlite_copy(Path(review_path), archive / "review.db")
                files.append({"path": "review.db", **review_info})

            manifest = {
                "schema": BACKUP_SCHEMA,
                "backup_id": archive.name,
                "created_at": _now(),
                "pipeline_version": PIPELINE_VERSION,
                "source_root": str(settings.root),
                "active_pointer": pointer_payload,
                "active_snapshot_id": (pointer_payload or {}).get("snapshot_id"),
                "snapshot_ids": snapshot_ids,
                "pipeline_db": db_info,
                "review_db": review_info,
                "files": sorted(files, key=lambda row: row["path"]),
                "limitations": [
                    "This is a same-host operational backup, not off-host disaster recovery.",
                    "A copy on the same disk cannot survive loss of the host or the cloud volume.",
                    "Restore is verified in an isolated directory before use; it is not performed automatically.",
                ],
            }
            (archive / MANIFEST).write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            return {"backup": str(archive), "manifest": manifest}
    except Exception:
        shutil.rmtree(archive, ignore_errors=True)
        raise


def _verify_file(root: Path, row: dict[str, Any]) -> None:
    path = root / row["path"]
    if not path.is_file():
        raise BackupError("backup file is missing: " + row["path"])
    if path.stat().st_size != int(row.get("bytes") or -1):
        raise BackupError("backup file size mismatch: " + row["path"])
    if _sha256(path) != row.get("sha256"):
        raise BackupError("backup file hash mismatch: " + row["path"])


def restore(
    archive: Path | str,
    destination: Path | str,
    *,
    review_db_destination: Path | str | None = None,
) -> dict[str, Any]:
    """Restore into an empty directory, then validate the restored active snapshot."""
    source = Path(archive)
    manifest_path = source / MANIFEST
    if not manifest_path.is_file():
        raise BackupError("backup has no " + MANIFEST)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != BACKUP_SCHEMA:
        raise BackupError("unsupported backup schema: " + str(manifest.get("schema")))
    target_root = Path(destination)
    if target_root.exists() and any(target_root.iterdir()):
        raise BackupError("restore destination must be empty: " + str(target_root))
    target_root.mkdir(parents=True, exist_ok=True)
    for row in manifest.get("files") or []:
        _verify_file(source, row)
        destination_file = target_root / row["path"]
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / row["path"], destination_file)
    if (target_root / "pipeline.db").is_file():
        check = sqlite3.connect(target_root / "pipeline.db")
        try:
            integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            check.close()
        if integrity != "ok":
            raise BackupError("restored pipeline DB integrity check failed: " + str(integrity))
    if manifest.get("review_db") and (target_root / "review.db").is_file() and review_db_destination:
        review_target = Path(review_db_destination)
        review_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_root / "review.db", review_target)
    active_id = str((manifest.get("active_pointer") or {}).get("snapshot_id") or "")
    active_dir = target_root / "snapshots" / active_id
    if not active_id or not (active_dir / "snapshot.json").is_file():
        raise BackupError("restored active snapshot is missing: " + active_id)
    restored_settings = Settings(root=target_root)
    restored_settings.review_db = Path(review_db_destination) if review_db_destination else None
    report = validate_snapshot(
        active_dir, settings=restored_settings, previous_dir=None, validate_product=True
    )
    if not report.ok:
        raise BackupError("restored snapshot failed validation: " + json.dumps(report.to_public()["errors"][:5]))
    if (target_root / "pipeline.db").is_file():
        db = sqlite3.connect(target_root / "pipeline.db")
        try:
            row = db.execute(
                "SELECT snapshot_id FROM snapshots WHERE is_active = 1 ORDER BY published_at DESC LIMIT 1"
            ).fetchone()
        finally:
            db.close()
        if row is None or str(row[0]) != active_id:
            raise BackupError("restored active pointer and DB active snapshot disagree")
    return {
        "restored_to": str(target_root),
        "active_snapshot_id": active_id,
        "snapshot_ids": manifest.get("snapshot_ids") or [],
        "validation": report.to_public(),
        "manifest": manifest,
    }
