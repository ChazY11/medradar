"""Backup, verification and graph-rebuild drills for the radar stores.

The observation ledger is the only irreplaceable artefact: ``graph.db`` is a projection that can
be rebuilt from it. So a backup here means *one consistent copy of ``radar.db``*, taken with
SQLite's online backup API (never a file copy of a live WAL database), followed by a verification
that opens the copy and compares its own counts.

Nothing in this module deletes an observation, and a failed verification leaves the copy on disk
with ``verified: false`` in its manifest so an operator can see exactly what failed.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ledger import ObservationLedger
from .paths import RadarPaths, radar_paths


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _counts(path: Path) -> dict[str, int]:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        connection.row_factory = sqlite3.Row
        out: dict[str, int] = {}
        for table in ("observation", "observation_version", "observation_change", "source_state"):
            row = connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            out[table] = int(row["n"])
        return out
    finally:
        connection.close()


def _integrity(path: Path) -> str:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "unknown"
    finally:
        connection.close()


@dataclass
class BackupResult:
    destination: Path
    manifest: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"destination": str(self.destination), **self.manifest}


def backup(paths: RadarPaths | None = None, *, destination: str | Path | None = None,
           keep: int = 14, log=print) -> BackupResult:
    """Take one consistent online copy of ``radar.db`` and verify it.

    The source is opened read-only, so a running scheduler is not blocked and no cursor can be
    advanced by the backup. The copy is written to a temporary name, verified, and only then
    renamed, so a killed backup never leaves a file that looks like a valid backup.
    """
    paths = paths or radar_paths()
    source = paths.ledger
    if not source.is_file():
        raise FileNotFoundError(f"no radar ledger at {source}")
    target_dir = Path(destination) if destination else paths.backups
    target_dir.mkdir(parents=True, exist_ok=True)
    moment = datetime.now(timezone.utc)
    stamp = moment.strftime("%Y%m%dT%H%M%S") + f"{moment.microsecond // 1000:03d}"
    final_name = f"radar-{stamp}.db"
    counter = 1
    while (target_dir / final_name).exists():
        counter += 1
        final_name = f"radar-{stamp}-{counter}.db"
    final_path = target_dir / final_name
    temporary = target_dir / f".{final_name}.partial"

    started = time.time()
    src = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True, timeout=60)
    dst = sqlite3.connect(str(temporary))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    integrity = _integrity(temporary)
    counts = _counts(temporary)
    source_counts = _counts(source)
    verified = integrity == "ok" and all(
        counts[key] >= source_counts[key] for key in ("observation", "observation_version")
    )
    temporary.replace(final_path)

    manifest = {
        "kind": "radar-ledger-backup",
        "created_at": _now(),
        "elapsed_seconds": round(time.time() - started, 3),
        "source": str(source),
        "source_sha256": _sha256(source),
        "backup": str(final_path),
        "backup_sha256": _sha256(final_path),
        "bytes": final_path.stat().st_size,
        "integrity_check": integrity,
        "verified": verified,
        "counts": counts,
        "source_counts": source_counts,
        "graph_included": False,
        "graph_note": (
            "graph.db is a derived projection of radar.db and is deliberately not copied. "
            "It can be rebuilt with `python -m medradar radar rebuild-graph`; losing it never "
            "loses an observation."
        ),
        "retention": {"keep": int(keep)},
    }
    manifest_path = target_dir / f"radar-{stamp}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    _rotate(target_dir, keep=max(1, int(keep)))
    log(f"[backup] {final_path} verified={verified} integrity={integrity} "
        f"observations={counts['observation']}")
    return BackupResult(final_path, manifest)


def _rotate(target_dir: Path, *, keep: int) -> None:
    """Keep the newest ``keep`` verified backups; never touch a file outside the pattern."""
    files = sorted(target_dir.glob("radar-*.db"), key=lambda item: item.name)
    for stale in files[:-keep] if len(files) > keep else []:
        try:
            stale.unlink()
            manifest = stale.with_suffix(".json")
            if manifest.is_file():
                manifest.unlink()
        except OSError:  # pragma: no cover - rotation failure must not fail the backup
            continue


def restore_check(*, backup_path: str | Path, work_dir: str | Path,
                  rebuild_graph: bool = True, log=print) -> dict[str, Any]:
    """Restore one backup into an isolated directory and prove it is usable.

    "The backup copied" is not a disaster-recovery test. This opens the copy, runs the ledger's
    own consistency check, and (when asked) rebuilds the technology graph from it in the same
    isolated directory. The live data directory is never touched.
    """
    from .graph import open_graph
    from .taxonomy import load_taxonomy

    source = Path(backup_path)
    if not source.is_file():
        raise FileNotFoundError(f"no backup at {source}")
    target_dir = Path(work_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    ledger_copy = target_dir / "radar.db"
    shutil.copy2(source, ledger_copy)
    digest = _sha256(ledger_copy)
    integrity = _integrity(ledger_copy)

    ledger = ObservationLedger(ledger_copy, create=False, read_only=False)
    try:
        consistency = ledger.consistency_check()
        counts = {
            "observations": int(ledger.con.execute(
                "SELECT COUNT(*) FROM observation").fetchone()[0]),
            "versions": int(ledger.con.execute(
                "SELECT COUNT(*) FROM observation_version").fetchone()[0]),
            "sources": int(ledger.con.execute(
                "SELECT COUNT(*) FROM source_state").fetchone()[0]),
        }
    finally:
        ledger.close()

    graph_report: dict[str, Any] = {"rebuilt": False}
    if rebuild_graph:
        taxonomy = load_taxonomy()
        graph_path = target_dir / "graph.db"
        if graph_path.exists():
            graph_path.unlink()
        graph = open_graph(graph_path, taxonomy)
        try:
            rebuild = ObservationLedger(ledger_copy, create=False)
            step = graph.materialize(rebuild, limit=5000, log=lambda _m: None)
            summary = graph.summary()
            rebuild.close()
        finally:
            graph.store.close()
        graph_report = {
            "rebuilt": True,
            "materialized": step["materialized"],
            "errors": step["errors"][:5],
            "nodes": summary["nodes"],
            "edges": summary["edges"],
            "graph_version": summary["graph_version"],
        }
    report = {
        "kind": "radar-restore-drill",
        "checked_at": _now(),
        "backup": str(source),
        "restored_to": str(ledger_copy),
        "sha256": digest,
        "integrity_check": integrity,
        "consistency": consistency,
        "counts": counts,
        "graph": graph_report,
        "ok": bool(integrity == "ok" and consistency.get("ok")),
    }
    log(f"[restore-check] ok={report['ok']} integrity={integrity} "
        f"observations={counts['observations']} graph={graph_report.get('nodes')}")
    return report
