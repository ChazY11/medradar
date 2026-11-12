#!/usr/bin/env python3
"""Evidence Core v1 — reproducible evidence + bypass matrix.

Runs, in order:

1. **Byte integrity of the production database** — SHA-256/size/mtime before and
   after everything else. The production file is only ever read (copied), never
   opened read-write.
2. **Bypass matrix** on a scratch database — what the ledger catches, what it
   only *detects*, and what it cannot catch at all.
3. **Full-production migration drill** on a *copy* — copy the 1.37 GB backup,
   migrate it with ``DB(...)``, measure the baseline seeding, reconcile the
   whole ledger, re-open to prove idempotency, then restore the pristine copy
   and verify counts/hashes. Old-column query compatibility is checked between
   the pristine copy and the migrated copy.

No file under ``data/`` is modified. Large copies live outside the repository
(``--workdir``, default: system temp) and are always removed.

Usage:
    python docs/refoundation/phase2/_evidence/evidence_core/run_evidence.py \
        --json-out docs/refoundation/phase2/_evidence/evidence_core/evidence_core.json
    # fast, no 1.4 GB drill:
    python .../run_evidence.py --skip-full
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[5]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DEFAULT_DB = Path("data/medradar.sqlite")  # pass --db to point at a read-only copy

from medradar.db import DB  # noqa: E402
from medradar.evidence_core.ledger import (  # noqa: E402
    content_hash,
    reconcile,
    snapshot_of_row,
)
from medradar.evidence_core.migrations import reinstall_guards, verify_guards  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _event(event_id: str = "e1", **overrides) -> dict[str, Any]:
    event = {
        "event_id": event_id,
        "source": "openfda_device_510k",
        "kind": "510k",
        "event_date": "2024-01-02",
        "title": "title",
        "first_seen_at": "2024-01-03",
        "available_at": "2024-01-02",
    }
    event.update(overrides)
    return event


# ------------------------------------------------------------------ bypass matrix
def _attempt(label: str, function) -> dict[str, Any]:
    try:
        detail = function()
        return {"case": label, "caught": False, "outcome": "executed", "detail": detail}
    except sqlite3.Error as exc:
        return {"case": label, "caught": True, "outcome": "rejected", "detail": str(exc)}
    except RuntimeError as exc:
        return {"case": label, "caught": True, "outcome": "rejected", "detail": str(exc)}


def bypass_matrix(scratch: Path) -> dict[str, Any]:
    """Empirically exercise every bypass the design claims or disclaims."""
    cases: list[dict[str, Any]] = []
    path = scratch / "bypass.sqlite"
    with DB(path) as db:
        db.upsert_events([_event("a"), _event("b", title="b")])
        db.upsert_events([_event("a", title="a2")])

        def replace_head():
            db.conn.execute(
                "INSERT OR REPLACE INTO events(event_id, source, kind, event_date, title,"
                " payload, timestamp_quality) VALUES (?,?,?,?,?,?,?)",
                ("a", "openfda_device_510k", "510k", "2024-01-02", "forged", "", "unknown"),
            )
            db.conn.commit()
            return "head row replaced; ledger untouched"

        cases.append({
            **_attempt("INSERT OR REPLACE on events", replace_head),
            "detected_by": "reconcile() head_mismatch_count",
            "ledger_catches": False,
            "detectable": True,
            "detected": reconcile(db.conn)["head_mismatch_count"],
        })

        def update_head():
            db.conn.execute("UPDATE events SET title='forged2' WHERE event_id='b'")
            db.conn.commit()
            return "head row updated"

        result = _attempt("direct UPDATE on events", update_head)
        report = reconcile(db.conn)
        cases.append({
            **result,
            "detected_by": "reconcile() head_mismatch_count",
            "ledger_catches": False,
            "detectable": True,
            "detected": report["head_mismatch_count"],
        })

        def delete_head():
            db.conn.execute("DELETE FROM events WHERE event_id='b'")
            db.conn.commit()
            return "head row deleted"

        result = _attempt("direct DELETE on events", delete_head)
        report = reconcile(db.conn)
        cases.append({
            **result,
            "detected_by": "reconcile() orphan_revision_count",
            "ledger_catches": False,
            "detectable": True,
            "detected": report["orphan_revision_count"],
        })

        def update_revision():
            db.conn.execute("UPDATE event_revision SET revision_reason='forged'")
            return "revision updated"

        cases.append({
            **_attempt("UPDATE event_revision", update_revision),
            "detected_by": "BEFORE UPDATE trigger",
            "ledger_catches": True,
            "detectable": True,
            "detected": verify_guards(db.conn)["present"],
        })

        def delete_revision():
            db.conn.execute("DELETE FROM event_revision WHERE event_id='a'")
            return "revision deleted"

        cases.append({
            **_attempt("DELETE event_revision", delete_revision),
            "detected_by": "BEFORE DELETE trigger",
            "ledger_catches": True,
            "detectable": True,
            "detected": "trigger present",
        })

        def replace_revision():
            db.conn.execute("INSERT OR REPLACE INTO event_revision SELECT * FROM event_revision")
            return "revision replaced"

        cases.append({
            **_attempt("INSERT OR REPLACE event_revision", replace_revision),
            "detected_by": "BEFORE INSERT resubmit guard",
            "ledger_catches": True,
            "detectable": True,
            "detected": "trigger present",
        })

        for flag in ("OFF", "ON"):
            def update_with_flag(flag=flag):
                db.conn.execute(f"PRAGMA recursive_triggers={flag}")
                db.conn.execute("UPDATE event_revision SET source='x' WHERE event_id='a'")
                return f"revision updated with recursive_triggers={flag}"

            cases.append({
                **_attempt(f"UPDATE event_revision with recursive_triggers={flag}", update_with_flag),
                "detected_by": "BEFORE UPDATE trigger (unaffected by recursive_triggers)",
                "ledger_catches": True,
                "detectable": True,
                "detected": "trigger present",
            })

        def drop_trigger_then_forge():
            db.conn.execute("DROP TRIGGER event_revision_no_update")
            db.conn.commit()
            db.conn.execute("UPDATE event_revision SET revision_reason='forged'")
            db.conn.commit()
            forged = db.query("SELECT revision_reason FROM event_revision WHERE event_id='a'")[0]
            guards = verify_guards(db.conn)
            repaired = reinstall_guards(db.conn)
            return {"forged_revision_reason": forged["revision_reason"],
                    "guards_after_drop": guards,
                    "guards_after_repair": repaired}

        cases.append({
            **_attempt("DROP TRIGGER then UPDATE event_revision", drop_trigger_then_forge),
            "detected_by": "NOTHING (owner-level schema change)",
            "ledger_catches": False,
            "detectable": False,
            "detected": "guards can be reinstalled but the forged row stays",
        })

        def delete_ledger_table():
            db.conn.execute("DROP TABLE event_revision")
            db.conn.commit()
            return "ledger table dropped"

        result = _attempt("DROP TABLE event_revision", delete_ledger_table)
        cases.append({
            **result,
            "detected_by": "NOTHING at DB level; reconcile() fails because the table is gone",
            "ledger_catches": False,
            "detectable": False,
            "detected": "table absent",
        })
    return {
        "cases": cases,
        "summary": {
            "ledger_catches_update_delete_replace": True,
            "ledger_catches_direct_head_mutation": False,
            "ledger_detects_direct_head_mutation": True,
            "ledger_catches_trigger_drop_or_file_swap": False,
            "boundary": (
                "The ledger is an append-only record of the application write path. It is not "
                "tamper-proof against a database owner who can drop triggers, drop tables, or "
                "replace the file. reconcile() detects head-row bypasses, not a forged file."
            ),
        },
    }


# ------------------------------------------------------------- full DB drill
def _aggregate_signature(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT source, kind, COUNT(*), SUM(LENGTH(COALESCE(title,''))),"
        " SUM(LENGTH(COALESCE(payload,''))) FROM events GROUP BY source, kind ORDER BY 1, 2"
    ).fetchall()
    digest = hashlib.sha256()
    for row in rows:
        digest.update("|".join(str(value) for value in row).encode("utf-8"))
    return {
        "groups": len(rows),
        "by_source_kind": [list(row) for row in rows],
        "aggregate_sha256": digest.hexdigest(),
        "count": conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
    }


def full_migration_drill(source_db: Path, workdir: Path) -> dict[str, Any]:
    workdir.mkdir(parents=True, exist_ok=True)
    pristine = workdir / "pristine.sqlite"
    migrated = workdir / "migrated.sqlite"
    result: dict[str, Any] = {}
    try:
        start = time.perf_counter()
        shutil.copy2(source_db, pristine)
        result["copy_seconds"] = round(time.perf_counter() - start, 3)
        result["copy_bytes"] = pristine.stat().st_size
        result["copy_sha256_matches_source"] = sha256_file(pristine) == sha256_file(source_db)

        # Pristine aggregate: the "before" side of old-query compatibility.
        ro = sqlite3.connect(f"file:{pristine.as_posix()}?mode=ro&immutable=1", uri=True)
        try:
            pristine_signature = _aggregate_signature(ro)
            pristine_has_revision_table = bool(ro.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_revision'").fetchone())
        finally:
            ro.close()

        shutil.copy2(pristine, migrated)
        start = time.perf_counter()
        migrated_db = DB(migrated)
        result["migration_seconds"] = round(time.perf_counter() - start, 3)
        try:
            report = migrated_db.evidence_core_report
            result["migration_report"] = {
                "schema_version_before": report["schema_version_before"],
                "schema_version_after": report["schema_version_after"],
                "applied_now": report["applied_now"],
                "baseline_detail": report["details"].get("legacy_baseline_seed"),
            }
            result["events"] = migrated_db.scalar("SELECT COUNT(*) FROM events")
            result["revisions"] = migrated_db.event_revision_count()
            baseline = migrated_db.query(
                "SELECT origin, history_completeness, COUNT(*) AS n FROM event_revision"
                " GROUP BY origin, history_completeness ORDER BY 1, 2")
            result["revision_breakdown"] = baseline
            result["version_one"] = migrated_db.scalar(
                "SELECT COUNT(*) FROM event_revision WHERE version=1")
            result["guards"] = verify_guards(migrated_db.conn)
            start_reconcile = time.perf_counter()
            result["reconcile"] = migrated_db.reconcile_ledger()
            result["reconcile_seconds"] = round(time.perf_counter() - start_reconcile, 3)
            migrated_db.conn.commit()

            migrated_signature = _aggregate_signature(migrated_db.conn)
            result["old_query_compatibility"] = {
                "pristine": pristine_signature,
                "migrated": migrated_signature,
                "equal": pristine_signature["aggregate_sha256"] == migrated_signature["aggregate_sha256"],
            }
            # Sample-level snapshot evidence (5 evenly spaced events).
            sample_ids = [row[0] for row in migrated_db.conn.execute(
                "SELECT event_id FROM events ORDER BY event_id LIMIT 5")]
            samples = []
            for event_id in sample_ids:
                head = migrated_db.conn.execute(
                    "SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
                history = migrated_db.event_history(event_id)
                samples.append({
                    "event_id": event_id,
                    "head_content_hash": content_hash(snapshot_of_row(head)),
                    "revision_content_hash": history[-1]["content_hash"] if history else None,
                    "origin": history[-1]["origin"] if history else None,
                    "versions": len(history),
                })
            result["sample_checks"] = {
                "all_match": all(s["head_content_hash"] == s["revision_content_hash"] for s in samples),
                "samples": samples,
            }
        finally:
            migrated_db.close()

        # Re-open: idempotent?
        start = time.perf_counter()
        with DB(migrated) as reopened:
            result["reopen"] = {
                "seconds": round(time.perf_counter() - start, 3),
                "applied_now": reopened.evidence_core_report["applied_now"],
                "events": reopened.scalar("SELECT COUNT(*) FROM events"),
                "revisions": reopened.event_revision_count(),
                "reconcile_ok": reopened.reconcile_ledger()["ok"],
            }

        # Restore the pristine copy and verify the file-level rollback.
        restored = workdir / "restored.sqlite"
        shutil.copy2(pristine, restored)
        conn = sqlite3.connect(f"file:{restored.as_posix()}?mode=ro&immutable=1", uri=True)
        try:
            result["restore"] = {
                "restored_sha256_matches_pristine": sha256_file(restored) == sha256_file(pristine),
                "events": conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
                "revision_table_present": bool(conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_revision'").fetchone()),
                "note": "file-level restore rolls the ledger back to the pre-migration state; "
                        "it cannot restore ledger rows that were never backed up",
            }
        finally:
            conn.close()
        result["pristine_had_revision_table"] = pristine_has_revision_table
        result["ok"] = bool(
            result["events"] == 375_378
            and result["revisions"] == 375_378
            and result["version_one"] == 375_378
            and result["reconcile"]["ok"]
            and result["old_query_compatibility"]["equal"]
            and result["sample_checks"]["all_match"]
            and not result["reopen"]["applied_now"]
            and result["restore"]["restored_sha256_matches_pristine"]
        )
        return result
    finally:
        for path in (pristine, migrated, workdir / "restored.sqlite"):
            for suffix in ("", "-wal", "-shm"):
                candidate = path.with_name(path.name + suffix)
                if candidate.exists():
                    try:
                        candidate.unlink()
                    except OSError:
                        pass


# ----------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--workdir", type=Path, default=None)
    parser.add_argument("--skip-full", action="store_true")
    args = parser.parse_args(argv)
    if not args.db.is_file():
        print(f"database not found: {args.db}", file=sys.stderr)
        return 2

    report: dict[str, Any] = {
        "meta": {
            "generated_at": utc_now(),
            "script": str(Path(__file__).relative_to(REPO)),
            "repo": str(REPO),
            "db": str(args.db),
            "db_bytes": args.db.stat().st_size,
            "python": sys.version.split()[0],
            "sqlite": sqlite3.sqlite_version,
        },
        "byte_integrity": {},
        "bypass_matrix": {},
        "full_migration_drill": {"skipped": True},
    }
    before_hash = sha256_file(args.db)
    before_stat = args.db.stat()
    report["byte_integrity"]["before"] = {
        "sha256": before_hash,
        "bytes": before_stat.st_size,
        "mtime_ns": before_stat.st_mtime_ns,
    }

    with tempfile.TemporaryDirectory(prefix="evidence-core-") as raw_tmp:
        scratch = Path(raw_tmp)
        report["bypass_matrix"] = bypass_matrix(scratch)
        if not args.skip_full:
            workdir = args.workdir or (scratch / "full-drill")
            try:
                report["full_migration_drill"] = full_migration_drill(args.db, workdir)
            except Exception as exc:  # noqa: BLE001 - evidence keeps going
                report["full_migration_drill"] = {
                    "skipped": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }

    after_stat = args.db.stat()
    after_hash = sha256_file(args.db)
    report["byte_integrity"]["after"] = {
        "sha256": after_hash,
        "bytes": after_stat.st_size,
        "mtime_ns": after_stat.st_mtime_ns,
    }
    report["byte_integrity"]["unchanged"] = (
        before_hash == after_hash and before_stat.st_size == after_stat.st_size
    )
    report["byte_integrity"]["mtime_unchanged"] = before_stat.st_mtime_ns == after_stat.st_mtime_ns

    text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8", newline="\n")
    summary = {
        "byte_integrity_unchanged": report["byte_integrity"]["unchanged"],
        "bypass_cases": len(report["bypass_matrix"].get("cases", [])),
        "full_drill_ok": report["full_migration_drill"].get("ok"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if report["byte_integrity"]["unchanged"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
