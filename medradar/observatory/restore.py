"""Verified restore and end-to-end restore drill for Observatory backup bundles.

The restore path is deliberately paranoid:

* the bundle is hash-verified with :func:`medradar.observatory.backup.verify_backup`
  **before** a single byte is restored; a mismatch or a missing artifact refuses
  the restore instead of producing a plausible-looking but wrong ledger;
* ``first_seen_at`` is never regenerated — the SQLite file is copied, so the rows
  keep the exact moments they were really first observed;
* ``verify_restored`` re-derives counts, first_seen min/max, per-source counts,
  version/change counts, run counts and source watermarks from the restored
  ledger and compares them with the manifest; any mismatch is a failure;
* ``run_restore_drill`` performs the whole loop in an isolated temporary
  directory (fresh backup → verify → restore → verify → continuity write) and
  records the outcome in ``runtime_state["last_restore_drill"]`` of the real
  ledger.  The drill writes only inside its work directory plus that operational
  runtime_state record; the production ledger data is read-only to it.

Nothing here touches the network, and no credentials are ever written.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from ..config import OUT_DIR
from .backup import (
    LEDGER_NAME,
    MANIFEST_NAME,
    PROSPECTIVE_DIR,
    RAW_CACHE_DIR,
    _atomic_copy_file,
    _integrity_check,
    _write_json_atomic,
    record_runtime_state,
    sha256_file,
    verify_backup,
)
from .ledger import ObservationLedger, default_ledger_path
from .records import (
    MappingResult,
    RawRecord,
    utc_now_iso,
)

RESTORE_REPORT_NAME = "RESTORE_REPORT.json"
RESTORED_LEDGER_NAME = "observatory.sqlite"
RESTORE_SCHEMA = "medradar-observatory-restore-report-1"
RESTORED_RAW_CACHE_DIR = "cache"
RESTORED_PROSPECTIVE_DIR = "prospective"

_COMPARE_COUNT_KEYS = (
    "observations",
    "versions",
    "changes",
    "runs",
    "failures",
    "sources",
    "live_observations",
    "backfilled_observations",
    "removed_observations",
)


class DrillFailure(RuntimeError):
    """One drill step failed; the report keeps the checks performed so far."""


def _check(checks: list[dict[str, Any]], check_id: str, ok: bool, detail: Any) -> bool:
    checks.append({"id": check_id, "ok": bool(ok), "detail": str(detail)})
    return bool(ok)


def _require(
    checks: list[dict[str, Any]], check_id: str, ok: bool, detail: Any
) -> None:
    if not _check(checks, check_id, ok, detail):
        raise DrillFailure(f"{check_id} failed: {detail}")


# ------------------------------------------------------------------- verification
def verify_restored(
    restored_ledger_path: str | Path, manifest: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Audit a restored ledger against the backup manifest.  Any mismatch fails."""
    path = Path(restored_ledger_path)
    checks: list[dict[str, Any]] = []
    problems: list[str] = []
    result: dict[str, Any] = {
        "restored_ledger": str(path),
        "checked_at": utc_now_iso(),
        "ok": False,
        "status": "UNVERIFIED",
        "checks": checks,
        "problems": problems,
        "counts": None,
        "first_seen": None,
    }
    if not isinstance(manifest, Mapping) or not manifest:
        problems.append("backup manifest is missing; cannot verify the restore")
        _check(checks, "manifest_present", False, "manifest is missing")
        return result
    _check(checks, "manifest_present", True, "manifest loaded")
    if not path.is_file():
        problems.append(f"restored ledger not found: {path}")
        _check(checks, "ledger_exists", False, f"not found: {path}")
        return result
    _check(checks, "ledger_exists", True, str(path))

    integrity = _integrity_check(path)
    _check(checks, "sqlite_integrity", integrity == "ok", integrity)
    if integrity != "ok":
        problems.append(f"sqlite integrity_check failed: {integrity}")

    try:
        ledger = ObservationLedger(path, read_only=True)
    except (sqlite3.Error, OSError) as exc:
        problems.append(f"could not open the restored ledger: {exc}")
        _check(checks, "ledger_opened", False, exc)
        return result
    _check(checks, "ledger_opened", True, "opened read-only")
    try:
        counts = ledger.counts()
        expected_counts = manifest.get("counts") or {}
        for key in _COMPARE_COUNT_KEYS:
            if key not in expected_counts:
                continue
            expected = int(expected_counts.get(key) or 0)
            actual = int(counts.get(key) or 0)
            ok = expected == actual
            _check(checks, f"counts.{key}", ok, f"manifest={expected} restored={actual}")
            if not ok:
                problems.append(f"count {key} mismatch: manifest={expected} restored={actual}")

        row = ledger.con.execute(
            "SELECT MIN(first_seen_at) AS minimum, MAX(first_seen_at) AS maximum"
            " FROM observation"
        ).fetchone()
        first_seen = {
            "min": row["minimum"] if row else None,
            "max": row["maximum"] if row else None,
        }
        expected_first_seen = manifest.get("first_seen") or {}
        for key in ("min", "max"):
            expected = expected_first_seen.get(key)
            actual = first_seen.get(key)
            ok = expected == actual
            _check(
                checks,
                f"first_seen.{key}",
                ok,
                f"manifest={expected!r} restored={actual!r}",
            )
            if not ok:
                problems.append(
                    f"first_seen.{key} mismatch: manifest={expected!r} restored={actual!r}"
                )

        per_source = {
            str(item["source"]): int(item["n"])
            for item in ledger.con.execute(
                "SELECT source, COUNT(*) AS n FROM observation"
                " GROUP BY source ORDER BY source"
            ).fetchall()
        }
        expected_per_source = manifest.get("per_source_observation_counts") or {}
        ok = {str(k): int(v) for k, v in expected_per_source.items()} == per_source
        _check(
            checks,
            "per_source_observation_counts",
            ok,
            f"manifest={dict(expected_per_source)} restored={per_source}",
        )
        if not ok:
            problems.append(
                "per-source observation counts mismatch: "
                f"manifest={dict(expected_per_source)} restored={per_source}"
            )

        watermarks: dict[str, Any] = {}
        for item in ledger.con.execute(
            "SELECT source, status, last_attempt_at, last_success_at, watermark,"
            " watermark_updated_at, adapter_version FROM source_state ORDER BY source"
        ).fetchall():
            watermarks[str(item["source"])] = {
                "status": item["status"],
                "last_attempt_at": item["last_attempt_at"],
                "last_success_at": item["last_success_at"],
                "watermark": item["watermark"],
                "watermark_updated_at": item["watermark_updated_at"],
                "adapter_version": item["adapter_version"],
            }
        expected_watermarks = manifest.get("source_watermarks") or {}
        ok = dict(expected_watermarks) == watermarks
        _check(
            checks,
            "source_watermarks",
            ok,
            f"{len(watermarks)} source(s) compared; "
            f"mismatched={sorted(set(expected_watermarks) | set(watermarks)) if not ok else []}",
        )
        if not ok:
            problems.append("source watermarks differ from the manifest")

        chain_row = ledger.con.execute(
            "SELECT COALESCE(MAX(version_count), 0) AS maximum,"
            " COALESCE(SUM(CASE WHEN version_count > 1 THEN 1 ELSE 0 END), 0) AS multi,"
            " COALESCE(SUM(CASE WHEN version_count > 0 THEN 1 ELSE 0 END), 0) AS with_versions"
            " FROM observation"
        ).fetchone()
        chain = {
            "max_version_count": int(chain_row["maximum"] or 0),
            "multi_version_observations": int(chain_row["multi"] or 0),
            "observations_with_versions": int(chain_row["with_versions"] or 0),
        }
        for key, expected in (manifest.get("version_chain") or {}).items():
            actual = int(chain.get(key) or 0)
            ok = int(expected or 0) == actual
            _check(checks, f"version_chain.{key}", ok, f"manifest={expected} restored={actual}")
            if not ok:
                problems.append(
                    f"version_chain.{key} mismatch: manifest={expected} restored={actual}"
                )

        expected_schema = (manifest.get("ledger") or {}).get("schema_version")
        actual_schema = counts.get("schema_version")
        if expected_schema is not None:
            ok = expected_schema == actual_schema
            _check(
                checks, "schema_version", ok,
                f"manifest={expected_schema} restored={actual_schema}",
            )
            if not ok:
                problems.append(
                    f"schema_version mismatch: manifest={expected_schema} "
                    f"restored={actual_schema}"
                )

        consistency = ledger.consistency_check()
        _check(
            checks,
            "consistency_check",
            consistency["ok"],
            "clean" if consistency["ok"] else f"issues={sorted(consistency['issues'])}",
        )
        if not consistency["ok"]:
            problems.append(
                "restored ledger consistency_check failed: "
                + ", ".join(sorted(consistency["issues"]))
            )
        result["counts"] = {
            key: counts.get(key) for key in _COMPARE_COUNT_KEYS
        }
        result["first_seen"] = first_seen
    finally:
        ledger.close()

    result["ok"] = not problems
    result["status"] = "OK" if result["ok"] else "FAILED"
    return result


# ----------------------------------------------------------------------- restore
def restore_backup(
    bundle_path: str | Path,
    target_dir: str | Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Restore a verified bundle into ``target_dir``.

    The manifest is verified *before* restoring.  On ``overwrite=True`` an
    existing restored ledger is renamed aside (never deleted), so a mistaken
    restore can never destroy the only copy of a ledger.
    """
    bundle = Path(bundle_path)
    target = Path(target_dir)
    at = utc_now_iso()
    result: dict[str, Any] = {
        "at": at,
        "bundle": str(bundle),
        "target": str(target),
        "ok": False,
        "status": "REFUSED",
        "problems": [],
        "ledger": None,
        "verification": None,
        "restored_verification": None,
        "report_path": None,
        "preserved_previous_ledger": None,
    }
    if not bundle.is_dir():
        result["problems"].append(f"backup bundle not found: {bundle}")
        return result
    if target.exists() and not target.is_dir():
        result["problems"].append(f"restore target is not a directory: {target}")
        return result
    try:
        if target.resolve() == bundle.resolve():
            result["problems"].append("restore target must differ from the backup bundle")
            return result
    except OSError:
        result["problems"].append(f"could not resolve restore target: {target}")
        return result

    verification = verify_backup(bundle)
    result["verification"] = verification
    if not verification["ok"]:
        problems = [f"backup verification failed: {item}" for item in verification.get("problems") or []]
        result["problems"].extend(problems or ["backup verification failed"])
        result["status"] = "REFUSED"
        return result
    manifest = verification["manifest"] or {}

    if target.exists():
        entries = list(target.iterdir())
        if entries and not overwrite:
            result["problems"].append(
                "restore target is not empty; pass overwrite=True to restore over it"
            )
            return result
    target.mkdir(parents=True, exist_ok=True)

    ledger_destination = target / RESTORED_LEDGER_NAME
    if ledger_destination.exists() and not overwrite:
        result["problems"].append(
            f"restored ledger already exists: {ledger_destination}; pass overwrite=True"
        )
        return result

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        if ledger_destination.exists():
            preserved = target / f"{RESTORED_LEDGER_NAME}.before-restore-{stamp}"
            os.replace(ledger_destination, preserved)
            result["preserved_previous_ledger"] = str(preserved)
        _atomic_copy_file(bundle / LEDGER_NAME, ledger_destination)
        if (bundle / RAW_CACHE_DIR).is_dir():
            shutil.copytree(
                bundle / RAW_CACHE_DIR,
                target / RESTORED_RAW_CACHE_DIR,
                dirs_exist_ok=True,
            )
        if (bundle / PROSPECTIVE_DIR).is_dir():
            shutil.copytree(
                bundle / PROSPECTIVE_DIR,
                target / RESTORED_PROSPECTIVE_DIR,
                dirs_exist_ok=True,
            )
    except OSError as exc:
        result["status"] = "FAILED"
        result["problems"].append(f"restore failed while copying files: {exc}")
        return result

    restored_verification = verify_restored(ledger_destination, manifest)
    result["restored_verification"] = restored_verification
    result["ledger"] = str(ledger_destination)
    result["raw_cache_restored"] = bool((bundle / RAW_CACHE_DIR).is_dir())
    result["prospective_restored"] = bool((bundle / PROSPECTIVE_DIR).is_dir())

    manifest_path = bundle / MANIFEST_NAME
    report = {
        "schema": RESTORE_SCHEMA,
        "restored_at": at,
        "bundle": {
            "path": str(bundle),
            "name": bundle.name,
            "manifest_sha256": sha256_file(manifest_path) if manifest_path.is_file() else None,
        },
        "manifest_verified_before_restore": True,
        "manifest": {
            "name": manifest.get("name"),
            "created_at": manifest.get("created_at"),
            "counts": manifest.get("counts"),
            "first_seen": manifest.get("first_seen"),
            "schema": manifest.get("schema"),
        },
        "restored": {
            "ledger": str(ledger_destination),
            "raw_cache": result["raw_cache_restored"],
            "prospective": result["prospective_restored"],
            "preserved_previous_ledger": result["preserved_previous_ledger"],
        },
        "policy": {
            "first_seen_at": "copied from the backup; never regenerated by a restore",
            "verification": "manifest sha256 verified before any file was restored",
            "overwrite": bool(overwrite),
        },
        "verification": restored_verification,
        "ok": restored_verification["ok"],
    }
    report_path = target / RESTORE_REPORT_NAME
    try:
        _write_json_atomic(report_path, report)
    except OSError as exc:  # pragma: no cover - target became unwritable
        result["problems"].append(f"could not write {RESTORE_REPORT_NAME}: {exc}")
    result["report_path"] = str(report_path) if report_path.is_file() else None

    result["ok"] = bool(restored_verification["ok"])
    result["status"] = "OK" if result["ok"] else "FAILED"
    if not result["ok"]:
        result["problems"].extend(restored_verification.get("problems") or [])
    return result


# -------------------------------------------------------------------- restore drill
def run_restore_drill(
    ledger_path: str | Path | None = None,
    work_dir: str | Path | None = None,
    include_raw_cache: bool = True,
) -> dict[str, Any]:
    """End-to-end backup → verify → restore → verify → continuity drill.

    The drill runs in an isolated temporary directory under ``work_dir``.  It
    reads the real ledger read-only and writes only ``runtime_state`` records
    (``last_backup`` via the backup step and ``last_restore_drill`` here) plus its
    own files under ``work_dir``.
    """
    from .backup import create_backup  # local import keeps module import order simple

    started = time.monotonic()
    at = utc_now_iso()
    source = Path(ledger_path) if ledger_path is not None else default_ledger_path()
    source = source.expanduser()
    work = Path(work_dir) if work_dir is not None else Path(OUT_DIR) / "reliability_drill"
    checks: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "at": at,
        "status": "FAILED",
        "ok": False,
        "ledger": str(source),
        "work_dir": str(work),
        "drill_dir": None,
        "bundle": None,
        "bundle_path": None,
        "restored_ledger": None,
        "restore_report": None,
        "backup": None,
        "checks": checks,
        "counts": {},
        "first_seen_max": None,
        "original_first_seen_max": None,
        "synthetic_observation_id": None,
        "synthetic_first_seen_at": None,
        "runtime_state_recorded": False,
        "runtime_state_error": None,
        "duration_ms": 0,
        "error": None,
    }
    try:
        if not source.is_file():
            raise FileNotFoundError(f"observation ledger not found: {source}")
        work.mkdir(parents=True, exist_ok=True)
        drill_root = Path(tempfile.mkdtemp(prefix="observatory-drill-", dir=str(work)))
        report["drill_dir"] = str(drill_root)

        # 1) Read the original ledger (read-only): first_seen_at is immutable.
        original = ObservationLedger(source, read_only=True)
        try:
            original_counts = original.counts()
            original_rows = {
                str(row["observation_id"]): row["first_seen_at"]
                for row in original.con.execute(
                    "SELECT observation_id, first_seen_at FROM observation"
                ).fetchall()
            }
        finally:
            original.close()
        report["counts"] = {
            key: original_counts.get(key)
            for key in ("observations", "versions", "changes", "runs", "failures", "sources")
        }
        report["original_first_seen_max"] = original_counts.get("last_observation_at")
        _check(
            checks,
            "original_ledger_read",
            True,
            f"observations={original_counts.get('observations')} "
            f"versions={original_counts.get('versions')} "
            f"changes={original_counts.get('changes')}",
        )

        # 2) Fresh backup into the isolated drill directory. It must NOT overwrite
        #    the ledger's "last production backup" record: a drill bundle lives in a
        #    throwaway work directory and only the drill outcome is recorded.
        backup_result = create_backup(
            ledger_path=source,
            dest_dir=drill_root / "backups",
            include_raw_cache=include_raw_cache,
            include_prospective=True,
            label="drill",
            record_last_backup=False,
        )
        report["backup"] = {
            key: backup_result.get(key)
            for key in (
                "status",
                "bundle",
                "path",
                "sha256_manifest",
                "verified",
                "bytes",
                "error",
            )
        }
        _require(
            checks,
            "backup_created",
            backup_result.get("status") == "OK" and bool(backup_result.get("ok")),
            f"status={backup_result.get('status')} error={backup_result.get('error')}",
        )
        bundle = Path(str(backup_result["path"]))
        report["bundle"] = backup_result.get("bundle")
        report["bundle_path"] = str(bundle)

        # 3) Independent verification of the published bundle.
        verification = verify_backup(bundle)
        _require(
            checks,
            "backup_verified",
            bool(verification.get("ok")),
            f"problems={verification.get('problems')}",
        )
        manifest = verification.get("manifest") or {}
        report["first_seen_max"] = (manifest.get("first_seen") or {}).get(
            "max"
        ) or report["original_first_seen_max"]
        report["counts"] = manifest.get("counts") or report["counts"]

        # 4) Restore into an isolated directory.
        restore_result = restore_backup(bundle, drill_root / "restored")
        _require(
            checks,
            "restore_completed",
            bool(restore_result.get("ok")),
            f"status={restore_result.get('status')} problems={restore_result.get('problems')}",
        )
        restored_ledger_path = Path(str(restore_result.get("ledger")))
        report["restored_ledger"] = str(restored_ledger_path)
        report["restore_report"] = restore_result.get("report_path")
        restored_verification = restore_result.get(
            "restored_verification"
        ) or verify_restored(restored_ledger_path, manifest)
        _require(
            checks,
            "restored_verified",
            bool(restored_verification.get("ok")),
            f"problems={restored_verification.get('problems')}",
        )

        # 5) Identity: the restored rows are byte-for-byte the backup's rows.
        restored = ObservationLedger(restored_ledger_path, read_only=True)
        try:
            restored_rows = {
                str(row["observation_id"]): row["first_seen_at"]
                for row in restored.con.execute(
                    "SELECT observation_id, first_seen_at FROM observation"
                ).fetchall()
            }
            restored_consistency = restored.consistency_check()
        finally:
            restored.close()
        compared = {oid: restored_rows.get(oid) for oid in original_rows}
        _require(
            checks,
            "first_seen_identity",
            compared == original_rows,
            f"{len(original_rows)} first_seen_at row(s) compared; "
            f"{sum(1 for oid, value in original_rows.items() if restored_rows.get(oid) != value)}"
            " mismatch(es)",
        )
        _require(
            checks,
            "restored_consistency",
            bool(restored_consistency["ok"]),
            "clean" if restored_consistency["ok"] else str(restored_consistency["issues"]),
        )

        # 6) Continuity: write one real synthetic observation into the restored
        #    ledger, then prove old first_seen_at values are unchanged and the new
        #    row received a genuinely fresh first_seen_at.
        write_started_at = utc_now_iso()
        synthetic_id: str | None = None
        new_state: str | None = None
        restored_writable = ObservationLedger(restored_ledger_path)
        try:
            run_id = restored_writable.start_run(
                "drill_continuity",
                trigger="restore_drill",
                collector_version="restore-drill/1.0",
            )
            record = RawRecord(
                source="drill_continuity",
                source_record_id=f"drill-{uuid4().hex[:12]}",
                record_type="drill_record",
                title="restore drill synthetic observation",
                payload={"drill": True, "purpose": "restore continuity check"},
            )
            outcome = restored_writable.record_observation(
                record,
                MappingResult(),
                run_id=run_id,
                collector_version="restore-drill/1.0",
                mapping_version="obs-mapping-v1",
            )
            restored_writable.finish_run(
                run_id, status="OK", counters={"records_new": 1}
            )
            synthetic_id = record.observation_id
            new_state = outcome.state
        finally:
            restored_writable.close()

        after = ObservationLedger(restored_ledger_path, read_only=True)
        try:
            new_row = after.observation_row(synthetic_id) if synthetic_id else None
            after_rows = {
                str(row["observation_id"]): row["first_seen_at"]
                for row in after.con.execute(
                    "SELECT observation_id, first_seen_at FROM observation"
                ).fetchall()
            }
            new_versions = after.versions(synthetic_id) if synthetic_id else []
            after_consistency = after.consistency_check()
        finally:
            after.close()
        new_first_seen = (new_row or {}).get("first_seen_at")
        old_rows_after = {oid: after_rows.get(oid) for oid in original_rows}
        _require(
            checks,
            "continuity_new_row_fresh",
            bool(new_row)
            and new_state == "NEW"
            and new_first_seen is not None
            and new_first_seen >= write_started_at
            and new_first_seen not in set(original_rows.values()),
            f"state={new_state} first_seen_at={new_first_seen} "
            f"write_started_at={write_started_at}",
        )
        _require(
            checks,
            "continuity_old_rows_unchanged",
            old_rows_after == original_rows,
            f"{len(original_rows)} pre-existing first_seen_at value(s) compared",
        )
        _require(
            checks,
            "continuity_version_chain",
            len(new_versions) == 1
            and new_versions[0].get("version_seq") == 1
            and new_versions[0].get("captured_at") == new_first_seen,
            f"versions={len(new_versions)}",
        )
        _require(
            checks,
            "post_write_consistency",
            bool(after_consistency["ok"]),
            "clean" if after_consistency["ok"] else str(after_consistency["issues"]),
        )
        report["synthetic_observation_id"] = synthetic_id
        report["synthetic_first_seen_at"] = new_first_seen
        report["status"] = "OK" if all(item["ok"] for item in checks) else "FAILED"
    except DrillFailure as exc:
        report["status"] = "FAILED"
        report["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 - the drill reports failure, never crashes
        report["status"] = "FAILED"
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if not all(item["ok"] for item in checks):
            report["status"] = "FAILED"
        report["ok"] = report["status"] == "OK"
        report["duration_ms"] = int((time.monotonic() - started) * 1000)
        runtime_record = {
            "at": report["at"],
            "status": report["status"],
            "ok": report["ok"],
            "bundle": report.get("bundle"),
            "bundle_path": report.get("bundle_path"),
            "checks": report["checks"],
            "first_seen_max": report.get("first_seen_max"),
            "counts": report.get("counts"),
            "error": report.get("error"),
            "duration_ms": report["duration_ms"],
            "ledger": str(source),
            "restored_ledger": report.get("restored_ledger"),
            "synthetic_observation_id": report.get("synthetic_observation_id"),
            "synthetic_first_seen_at": report.get("synthetic_first_seen_at"),
        }
        recorded, record_error = record_runtime_state(
            source, "last_restore_drill", runtime_record
        )
        report["runtime_state_recorded"] = recorded
        report["runtime_state_error"] = record_error
    return report


__all__ = [
    "RESTORE_REPORT_NAME",
    "RESTORED_LEDGER_NAME",
    "RESTORE_SCHEMA",
    "restore_backup",
    "verify_restored",
    "run_restore_drill",
]
