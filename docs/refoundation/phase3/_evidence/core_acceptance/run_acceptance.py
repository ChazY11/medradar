#!/usr/bin/env python3
"""REFOUNDATION-003 — independent production acceptance for Evidence Core v1.

This is an *acceptance* harness, not the author's drill: it re-derives every
claim with its own queries/assertions against a **fresh copy** of the production
backup, and records PASS/FAIL per acceptance item plus timings and storage cost.

The original database is only read (copied + hashed). All migrations, writes,
mutations and restores happen on copies under ``--workdir`` (default: a temp dir
outside the repository). Everything is removed afterwards.

Usage:
    python docs/refoundation/phase3/_evidence/core_acceptance/run_acceptance.py \
        --json-out docs/refoundation/phase3/_evidence/core_acceptance/acceptance.json
    # skip the pytest subprocess (faster; run pytest separately)
    python ... --skip-pytest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[5]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DEFAULT_DB = Path(r"D:\DEPPSKK\refoundation-002-backups\data\medradar.sqlite")
EXPECTED_ORIGINAL_SHA = "445807cab60df66e0f0853c973aaf0dae6065e72b6c9807d5dd5265097002c92"
EXPECTED_EVENTS = 375_378

from medradar.db import DB  # noqa: E402
from medradar.evidence_core import ledger as ledger_mod  # noqa: E402
from medradar.evidence_core import migrations as migrations_mod  # noqa: E402
from medradar.evidence_core.migrations import (  # noqa: E402
    MIGRATIONS,
    ensure_schema,
    reinstall_guards,
    verify_guards,
)

CHECKS: list[dict[str, Any]] = []


def check(item: str, passed: bool, measured: Any = None, expected: Any = None,
          detail: str = "") -> bool:
    CHECKS.append({"item": item, "pass": bool(passed), "measured": measured,
                   "expected": expected, "detail": detail})
    return bool(passed)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_bytes(path: Path) -> int:
    total = 0
    for suffix in ("", "-wal", "-shm"):
        candidate = path.with_name(path.name + suffix)
        if candidate.exists():
            total += candidate.stat().st_size
    return total


def checkpoint_and_size(path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    finally:
        conn.close()
    main = path.stat().st_size
    wal = path.with_name(path.name + "-wal")
    shm = path.with_name(path.name + "-shm")
    return {
        "main_bytes": main,
        "wal_bytes": wal.stat().st_size if wal.exists() else 0,
        "shm_bytes": shm.stat().st_size if shm.exists() else 0,
        "total_bytes": main + (wal.stat().st_size if wal.exists() else 0),
        "page_count": sqlite3.connect(str(path)).execute("PRAGMA page_count").fetchone()[0],
        "page_size": sqlite3.connect(str(path)).execute("PRAGMA page_size").fetchone()[0],
    }


def open_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)


def timed(conn: sqlite3.Connection, sql: str, params: tuple = (), runs: int = 3) -> float:
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        conn.execute(sql, params).fetchall()
        samples.append((time.perf_counter() - start) * 1000)
    return round(sorted(samples)[len(samples) // 2], 2)


def aggregate_signature(conn: sqlite3.Connection) -> dict[str, Any]:
    """Content fingerprint of the columns every old reader depends on."""
    queries = {
        "by_source_kind": (
            "SELECT source, kind, COUNT(*), SUM(LENGTH(COALESCE(title,''))),"
            " SUM(LENGTH(COALESCE(payload,''))) FROM events GROUP BY source, kind ORDER BY 1,2"
        ),
        "by_company": (
            "SELECT COALESCE(company_key,''), COUNT(*) FROM events"
            " GROUP BY 1 ORDER BY 1"
        ),
        "by_quality": (
            "SELECT COALESCE(timestamp_quality,''), COUNT(*) FROM events GROUP BY 1 ORDER BY 1"
        ),
        "dated": (
            "SELECT COUNT(*), SUM(LENGTH(COALESCE(event_date,''))) FROM events"
        ),
    }
    out: dict[str, Any] = {"queries": {}}
    for name, sql in queries.items():
        rows = conn.execute(sql).fetchall()
        digest = hashlib.sha256()
        for row in rows:
            digest.update("|".join(str(value) for value in row).encode("utf-8"))
        out["queries"][name] = {
            "rows": [list(row) for row in rows][:10],
            "groups": len(rows),
            "sha256": digest.hexdigest(),
        }
    return out


LEGACY_PREDICATE = """
SELECT COUNT(*) FROM events
WHERE timestamp_quality='date' AND event_date<>''
  AND date(published_at)=event_date AND date(available_at)=event_date
  AND source IN ('openfda_device_510k','openfda_device_pma',
                 'openfda_device_recall','openfda_drug_drugsfda')
"""


OLD_COLUMNS = (
    "event_id", "source", "kind", "event_date", "as_of", "company_key", "applicant_raw",
    "country", "track_id", "product_code", "title", "summary", "url", "payload",
    "fetched_at", "published_at", "first_seen_at", "available_at", "timestamp_quality",
)


def sample_rows(conn: sqlite3.Connection, limit: int = 200) -> list[tuple]:
    columns = ",".join(OLD_COLUMNS)
    return conn.execute(
        f"SELECT {columns} FROM events ORDER BY event_id LIMIT ?", (limit,)
    ).fetchall()


def make_legacy_db(path: Path, rows: int = 3) -> None:
    """A pre-ledger database **after** the legacy timing forward-migration.

    Evidence Core expects ``medradar.db.DB.__init__`` to have added the four
    timing columns already (that is the production shape of the backup), so the
    synthetic fixture includes them; what it does not include is
    ``event_revision`` / ``schema_version``.
    """
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            CREATE TABLE events (
                event_id TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL,
                event_date TEXT, as_of TEXT, company_key TEXT, applicant_raw TEXT,
                country TEXT DEFAULT 'US', track_id TEXT, product_code TEXT, title TEXT,
                summary TEXT, url TEXT, payload TEXT, fetched_at TEXT,
                published_at TEXT, first_seen_at TEXT, available_at TEXT,
                timestamp_quality TEXT DEFAULT 'date'
            );
            """
        )
        for index in range(rows):
            conn.execute(
                "INSERT INTO events(event_id, source, kind, event_date, title, payload,"
                " fetched_at, published_at, first_seen_at, available_at, timestamp_quality)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (f"legacy-{index}", "openfda_device_510k", "510k", "2010-01-0%d" % (index + 1),
                 f"legacy {index}", "{}", "2026-10-30T00:00:00Z", "2010-01-0%d" % (index + 1),
                 "2026-10-30", "2010-01-0%d" % (index + 1), "date"),
            )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------- stages
def stage_migration(original: Path, work: Path) -> dict[str, Any]:
    pristine = work / "pristine.sqlite"
    migrated = work / "migrated.sqlite"
    result: dict[str, Any] = {}

    start = time.perf_counter()
    shutil.copy2(original, pristine)
    result["copy_seconds"] = round(time.perf_counter() - start, 3)
    result["pristine_sha256"] = sha256_file(pristine)
    result["pristine_bytes"] = pristine.stat().st_size

    ro = open_ro(pristine)
    try:
        result["pristine_signature"] = aggregate_signature(ro)
        result["pristine_legacy_promotions"] = ro.execute(LEGACY_PREDICATE).fetchone()[0]
        result["pristine_sample_rows"] = sample_rows(ro)
        result["pristine_available_at_ms"] = timed(
            ro, "SELECT COUNT(*) FROM events WHERE available_at >= ?", ("2020-01-01",))
        result["pristine_plan"] = [list(row) for row in ro.execute(
            "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM events WHERE available_at >= ?",
            ("2020-01-01",))]
        result["pristine_has_revision"] = bool(ro.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_revision'").fetchone())
        result["pristine_has_schema_version"] = bool(ro.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone())
    finally:
        ro.close()

    shutil.copy2(pristine, migrated)
    start = time.perf_counter()
    db = DB(migrated)
    result["migration_seconds"] = round(time.perf_counter() - start, 3)
    try:
        report = db.evidence_core_report
        result["report"] = report
        result["schema_version_rows"] = db.query(
            "SELECT version, name, checksum, applied_at FROM schema_version ORDER BY version")
        result["event_count"] = db.scalar("SELECT COUNT(*) FROM events")
        result["revision_count"] = db.event_revision_count()
        result["indexes"] = sorted(
            row[0] for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")
            if row[0] == "idx_events_available_at" or row[0].startswith("idx_event_revision"))
        result["triggers"] = verify_guards(db.conn)
    finally:
        db.close()

    result["migrated_size_before_mutations"] = checkpoint_and_size(migrated)
    perf_conn = sqlite3.connect(f"file:{migrated.as_posix()}?mode=ro", uri=True)
    try:
        result["migrated_available_at_ms"] = timed(
            perf_conn, "SELECT COUNT(*) FROM events WHERE available_at >= ?", ("2020-01-01",))
        result["migrated_plan"] = [list(row) for row in perf_conn.execute(
            "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM events WHERE available_at >= ?",
            ("2020-01-01",))]
    finally:
        perf_conn.close()

    # ---- acceptance checks: migration
    expected_checksums = {m.version: m.checksum for m in MIGRATIONS}
    rows = result["schema_version_rows"]
    check("1.1 fresh copy byte-identical to original",
          result["pristine_sha256"] == EXPECTED_ORIGINAL_SHA and result["pristine_bytes"] == original.stat().st_size,
          {"sha256": result["pristine_sha256"], "bytes": result["pristine_bytes"]},
          {"sha256": EXPECTED_ORIGINAL_SHA})
    check("1.2 migration applied exactly 2 versions in order",
          [row["version"] for row in rows] == [1, 2]
          and result["report"]["schema_version_after"] == 2,
          [row["version"] for row in rows], [1, 2])
    check("1.3 stored checksums equal code checksums",
          all(row["checksum"] == expected_checksums[row["version"]] for row in rows)
          and all(re.fullmatch(r"[0-9a-f]{64}", row["checksum"]) for row in rows),
          {row["version"]: row["checksum"][:12] for row in rows})
    check("1.4 applied_at parses and is after 2026-01-01",
          all(row["applied_at"] > "2026-01-01" for row in rows), rows and rows[-1]["applied_at"])
    check("1.5 event count unchanged by migration",
          result["event_count"] == EXPECTED_EVENTS, result["event_count"], EXPECTED_EVENTS)
    check("1.6 one baseline revision per event",
          result["revision_count"] == EXPECTED_EVENTS, result["revision_count"], EXPECTED_EVENTS)
    check("1.7 available_at index created", "idx_events_available_at" in result["indexes"],
          result["indexes"])
    check("1.8 all three guards present", result["triggers"]["ok"], result["triggers"])
    return result


def stage_idempotency_and_tamper(migrated: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    start = time.perf_counter()
    with DB(migrated) as db:
        out["reopen"] = {
            "seconds": round(time.perf_counter() - start, 3),
            "applied_now": db.evidence_core_report["applied_now"],
            "schema_version_after": db.evidence_core_report["schema_version_after"],
            "events": db.scalar("SELECT COUNT(*) FROM events"),
            "revisions": db.event_revision_count(),
            "version_rows": db.scalar("SELECT COUNT(*) FROM schema_version"),
        }
        # Tamper: edit an applied checksum, expect a hard refusal, then restore.
        original_checksum = db.scalar("SELECT checksum FROM schema_version WHERE version=1")
        db.execute("UPDATE schema_version SET checksum=? WHERE version=1", ("0" * 64,))
        db.conn.commit()
        try:
            ensure_schema(db.conn)
            out["tamper"] = {"raised": False, "error": None}
        except RuntimeError as exc:
            out["tamper"] = {"raised": True, "error": str(exc)[:200]}
        db.execute("UPDATE schema_version SET checksum=? WHERE version=1", (original_checksum,))
        db.conn.commit()
        out["tamper"]["restored_ok"] = ensure_schema(db.conn)["applied_now"] == []
        # Unknown future version must also be refused.
        db.execute(
            "INSERT INTO schema_version(version, name, checksum, applied_at)"
            " VALUES (99, 'future', 'x', '2030-01-01T00:00:00.000000Z')")
        db.conn.commit()
        try:
            ensure_schema(db.conn)
            out["unknown_version"] = {"raised": False}
        except RuntimeError as exc:
            out["unknown_version"] = {"raised": True, "error": str(exc)[:200]}
        db.execute("DELETE FROM schema_version WHERE version=99")
        db.conn.commit()
    out["checksum_restored"] = True
    check("2.1 second open applies nothing", out["reopen"]["applied_now"] == []
          and out["reopen"]["schema_version_after"] == 2, out["reopen"])
    check("2.2 second open leaves events/revisions unchanged",
          out["reopen"]["events"] == EXPECTED_EVENTS and out["reopen"]["revisions"] == EXPECTED_EVENTS,
          {k: out["reopen"][k] for k in ("events", "revisions")})
    check("2.3 tampered checksum refused with explicit message",
          out["tamper"]["raised"] and "checksum mismatch" in (out["tamper"]["error"] or ""),
          out["tamper"])
    check("2.4 unknown applied version refused", out["unknown_version"]["raised"],
          out["unknown_version"])
    return out


def stage_ledger_consistency(migrated: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    conn = sqlite3.connect(f"file:{migrated.as_posix()}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        out["events"] = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        out["revisions"] = conn.execute("SELECT COUNT(*) FROM event_revision").fetchone()[0]
        out["events_without_revision"] = conn.execute(
            "SELECT COUNT(*) FROM events e WHERE NOT EXISTS"
            " (SELECT 1 FROM event_revision r WHERE r.event_id=e.event_id)").fetchone()[0]
        out["orphan_revisions"] = conn.execute(
            "SELECT COUNT(*) FROM event_revision r WHERE NOT EXISTS"
            " (SELECT 1 FROM events e WHERE e.event_id=r.event_id)").fetchone()[0]
        out["version_gaps"] = conn.execute(
            "SELECT COUNT(*) FROM (SELECT event_id, COUNT(*) AS n, MIN(version) AS mn,"
            " MAX(version) AS mx FROM event_revision GROUP BY event_id"
            " HAVING n<>mx OR mn<>1)").fetchone()[0]
        out["duplicate_pk"] = conn.execute(
            "SELECT COUNT(*)-COUNT(DISTINCT event_id || '#' || version) FROM event_revision"
        ).fetchone()[0]
        out["by_origin"] = [dict(zip(("origin", "n"), row)) for row in conn.execute(
            "SELECT origin, COUNT(*) FROM event_revision GROUP BY origin ORDER BY 1")]
        out["by_completeness"] = [dict(zip(("history_completeness", "n"), row)) for row in conn.execute(
            "SELECT history_completeness, COUNT(*) FROM event_revision GROUP BY 1 ORDER BY 1")]
        out["version_min"] = conn.execute("SELECT MIN(version), MAX(version) FROM event_revision").fetchone()
        out["baseline_recorded_at"] = dict(zip(
            ("distinct_recorded_at", "min_recorded_at", "max_recorded_at"),
            conn.execute("SELECT COUNT(DISTINCT recorded_at), MIN(recorded_at), MAX(recorded_at)"
                         " FROM event_revision").fetchone()))
        out["revisions_before_2026"] = conn.execute(
            "SELECT COUNT(*) FROM event_revision WHERE recorded_at < '2026-01-01'").fetchone()[0]
        # latest revision per event must equal the head row content hash
        latest: dict[str, dict[str, Any]] = {}
        for row in conn.execute(
            "SELECT event_id, version, content_hash FROM (SELECT event_id, version, content_hash,"
            " ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY version DESC) rn"
            " FROM event_revision) WHERE rn=1"):
            latest[row[0]] = {"version": row[1], "content_hash": row[2]}
        mismatched = 0
        missing = 0
        for row in conn.execute("SELECT * FROM events"):
            event_id = str(row["event_id"])
            revision = latest.get(event_id)
            if revision is None:
                missing += 1
                continue
            head = {field: row[field] for field in ledger_mod.EVENT_SNAPSHOT_FIELDS
                    if field in set(row.keys())}
            if ledger_mod.content_hash(head) != revision["content_hash"]:
                mismatched += 1
        out["head_mismatch"] = mismatched
        out["missing_latest"] = missing
        # first_seen preserved from the pre-ledger row (baseline snapshot == event row)
        out["first_seen_mismatch"] = conn.execute(
            "SELECT COUNT(*) FROM events e JOIN event_revision r"
            " ON r.event_id=e.event_id AND r.version=1"
            " WHERE COALESCE(e.first_seen_at,'') <> COALESCE(r.first_seen_at,'')").fetchone()[0]
        out["v1_snapshot_first_seen_mismatch"] = conn.execute(
            "SELECT COUNT(*) FROM events e JOIN event_revision r"
            " ON r.event_id=e.event_id AND r.version=1"
            " WHERE COALESCE(json_extract(r.snapshot, '$.first_seen_at'),'')"
            "     <> COALESCE(e.first_seen_at,'')").fetchone()[0]
    finally:
        conn.close()

    start = time.perf_counter()
    with DB(migrated) as db:
        reconcile = db.reconcile_ledger()
    out["reconcile"] = reconcile
    out["reconcile_seconds"] = round(time.perf_counter() - start, 3)

    check("3.1 every event has at least one revision", out["events_without_revision"] == 0,
          out["events_without_revision"])
    check("3.2 exactly one current revision per event (no gaps, v starts at 1)",
          out["version_gaps"] == 0 and out["duplicate_pk"] == 0 and out["missing_latest"] == 0,
          {"version_gaps": out["version_gaps"], "duplicate_pk": out["duplicate_pk"],
           "missing_latest": out["missing_latest"]})
    check("3.3 no orphan revisions", out["orphan_revisions"] == 0, out["orphan_revisions"])
    check("3.4 all revisions are legacy_baseline/baseline_only",
          out["by_origin"] == [{"origin": "legacy_baseline", "n": EXPECTED_EVENTS}]
          and out["by_completeness"] == [{"history_completeness": "baseline_only", "n": EXPECTED_EVENTS}],
          {"origin": out["by_origin"], "completeness": out["by_completeness"]})
    check("3.5 only version 1 exists after clean migration",
          tuple(out["version_min"]) == (1, 1), out["version_min"])
    check("3.6 reconcile reports zero mismatches",
          out["reconcile"]["ok"] and out["reconcile"]["head_mismatch_count"] == 0
          and out["reconcile"]["orphan_revision_count"] == 0,
          {k: out["reconcile"][k] for k in
           ("events_rows", "revisioned_events", "head_mismatch_count",
            "missing_revision_count", "orphan_revision_count", "ok")})
    check("3.7 no fabricated observation time (single migration moment, none before 2026)",
          out["baseline_recorded_at"]["distinct_recorded_at"] == 1
          and out["revisions_before_2026"] == 0,
          out["baseline_recorded_at"])
    check("3.8 first_seen_at preserved from pre-ledger rows",
          out["first_seen_mismatch"] == 0 and out["v1_snapshot_first_seen_mismatch"] == 0,
          {"revision_column": out["first_seen_mismatch"],
           "snapshot": out["v1_snapshot_first_seen_mismatch"]})
    return out


def stage_history_retention(migrated: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"events": []}
    with DB(migrated) as db:
        targets = [row[0] for row in db.conn.execute(
            "SELECT event_id FROM events ORDER BY event_id LIMIT 3")]
        for event_id in targets:
            head = dict(db.query("SELECT * FROM events WHERE event_id=?", (event_id,))[0])
            before = db.event_history(event_id)
            old_title = head["title"]
            changed = dict(head, title=(old_title or "") + " [acceptance-change]")
            db.upsert_events([changed])
            after = db.event_history(event_id)
            entry: dict[str, Any] = {
                "event_id": event_id,
                "versions_before": len(before),
                "versions_after": len(after),
                "old_title": old_title,
                "new_title": changed["title"],
                "old_value_in_v1": after[0]["snapshot"]["title"],
                "latest_reason": after[-1]["revision_reason"],
                "prev_hash_chain_ok": after[-1]["prev_content_hash"] == after[-2]["content_hash"],
                "head_title": db.query("SELECT title FROM events WHERE event_id=?", (event_id,))[0]["title"],
            }
            # Identical rewrite: no new revision, first_seen preserved.
            first_seen_before = db.query(
                "SELECT first_seen_at FROM events WHERE event_id=?", (event_id,))[0]["first_seen_at"]
            db.upsert_events([changed])
            entry["versions_after_identical"] = db.event_revision_count(event_id)
            first_seen_after = db.query(
                "SELECT first_seen_at FROM events WHERE event_id=?", (event_id,))[0]["first_seen_at"]
            entry["first_seen_preserved"] = first_seen_before == first_seen_after
            # Earlier first-seen: head only (no revision).
            earlier = dict(fetched_head := db.query(
                "SELECT * FROM events WHERE event_id=?", (event_id,))[0])
            earlier["first_seen_at"] = "2000-01-01"
            db.upsert_events([earlier])
            entry["versions_after_earlier_first_seen"] = db.event_revision_count(event_id)
            entry["head_first_seen_after_earlier"] = db.query(
                "SELECT first_seen_at FROM events WHERE event_id=?", (event_id,))[0]["first_seen_at"]
            out["events"].append(entry)
    ok = all(
        e["versions_after"] == e["versions_before"] + 1
        and e["old_value_in_v1"] == e["old_title"]
        and e["head_title"] == e["new_title"]
        and e["prev_hash_chain_ok"]
        and e["latest_reason"] == "update"
        and e["versions_after_identical"] == e["versions_after"]
        and e["first_seen_preserved"]
        and e["versions_after_earlier_first_seen"] == e["versions_after"]
        and e["head_first_seen_after_earlier"].startswith("2000-01-01")
        for e in out["events"]
    )
    out["ok"] = ok
    check("4.1 change appends revision and old value is retrievable", ok,
          [{k: e[k] for k in ("versions_before", "versions_after", "old_value_in_v1",
                              "prev_hash_chain_ok", "latest_reason")} for e in out["events"]])
    return out


def stage_detection(migrated: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    with DB(migrated) as db:
        event_id = db.scalar("SELECT event_id FROM events ORDER BY event_id LIMIT 1")
        second = db.scalar(
            "SELECT event_id FROM events WHERE event_id<>? ORDER BY event_id LIMIT 1", (event_id,))
        revision_before = db.event_revision_count()

        # 5a direct UPDATE
        db.conn.execute("SAVEPOINT accept_update")
        db.conn.execute("UPDATE events SET title='acceptance-forged' WHERE event_id=?", (event_id,))
        out["update_detected"] = db.reconcile_ledger()
        db.conn.execute("ROLLBACK TO accept_update")
        db.conn.execute("RELEASE accept_update")

        # 5b direct DELETE
        db.conn.execute("SAVEPOINT accept_delete")
        db.conn.execute("DELETE FROM events WHERE event_id=?", (second,))
        out["delete_detected"] = db.reconcile_ledger()
        db.conn.execute("ROLLBACK TO accept_delete")
        db.conn.execute("RELEASE accept_delete")

        # 5c INSERT OR REPLACE
        db.conn.execute("SAVEPOINT accept_replace")
        db.conn.execute(
            "INSERT OR REPLACE INTO events(event_id, source, kind, event_date, title,"
            " payload, timestamp_quality) VALUES (?,?,?,?,?,?,?)",
            (event_id, "acceptance", "forged", "2024-01-01", "replaced", "", "unknown"))
        out["replace_detected"] = db.reconcile_ledger()
        db.conn.execute("ROLLBACK TO accept_replace")
        db.conn.execute("RELEASE accept_replace")

        # 5d ledger writes must be rejected
        rejects = {}
        for label, sql in (
            ("update", "UPDATE event_revision SET revision_reason='forged'"),
            ("delete", "DELETE FROM event_revision"),
            ("replace", "INSERT OR REPLACE INTO event_revision SELECT * FROM event_revision"),
        ):
            try:
                db.conn.execute(sql)
                rejects[label] = "ACCEPTED"
            except sqlite3.Error as exc:
                rejects[label] = f"rejected: {exc}"
        out["ledger_write_attempts"] = rejects

        # 5e dropped trigger: forgery succeeds, guards report it, rollback restores
        db.conn.execute("SAVEPOINT accept_drop")
        db.conn.execute("DROP TRIGGER event_revision_no_update")
        db.conn.execute("UPDATE event_revision SET revision_reason='forged' WHERE event_id=?", (event_id,))
        out["dropped_trigger"] = {
            "forged_visible": db.query(
                "SELECT revision_reason FROM event_revision WHERE event_id=?", (event_id,))[0]["revision_reason"],
            "guards": verify_guards(db.conn),
            "reconcile": db.reconcile_ledger(),
        }
        db.conn.execute("ROLLBACK TO accept_drop")
        db.conn.execute("RELEASE accept_drop")
        out["guards_after_rollback"] = verify_guards(db.conn)
        out["revision_count_after_rollbacks"] = db.event_revision_count()

    check("5.1 raw UPDATE events detected by reconcile",
          out["update_detected"]["head_mismatch_count"] >= 1, out["update_detected"]["head_mismatch_count"])
    check("5.2 raw DELETE events detected as orphan",
          out["delete_detected"]["orphan_revision_count"] >= 1,
          out["delete_detected"]["orphan_revision_count"])
    check("5.3 INSERT OR REPLACE events detected by reconcile",
          out["replace_detected"]["head_mismatch_count"] >= 1,
          out["replace_detected"]["head_mismatch_count"])
    check("5.4 ledger UPDATE/DELETE/REPLACE rejected by triggers",
          all(value.startswith("rejected") for value in out["ledger_write_attempts"].values()),
          out["ledger_write_attempts"])
    check("5.5 dropped trigger is NOT caught (documented limit) but guards report it and tx rollback restores",
          out["dropped_trigger"]["forged_visible"] == "forged"
          and out["dropped_trigger"]["guards"]["ok"] is False
          and out["guards_after_rollback"]["ok"] is True,
          {"forged_visible": out["dropped_trigger"]["forged_visible"],
           "guards_after_drop": out["dropped_trigger"]["guards"]["missing"],
           "guards_after_rollback": out["guards_after_rollback"]})
    check("5.6 rollback restores revision count",
          out["revision_count_after_rollbacks"] == revision_before,
          out["revision_count_after_rollbacks"])
    return out


def stage_rollback(work: Path, migrated: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}

    # 6a write-batch rollback on the migrated copy.
    with DB(migrated) as db:
        before = (db.scalar("SELECT COUNT(*) FROM events"), db.event_revision_count())
        original_append = ledger_mod.append_revision

        def explode(conn, **kwargs):
            if kwargs["event_id"] == "acceptance-rollback-b":
                raise RuntimeError("forced revision failure")
            return original_append(conn, **kwargs)

        from unittest import mock
        with mock.patch("medradar.evidence_core.ledger.append_revision", side_effect=explode):
            try:
                db.upsert_events([
                    {"event_id": "acceptance-rollback-a", "source": "s", "kind": "k",
                     "event_date": "2024-01-01", "title": "a"},
                    {"event_id": "acceptance-rollback-b", "source": "s", "kind": "k",
                     "event_date": "2024-01-01", "title": "b"},
                ])
                out["batch_rollback"] = {"raised": False}
            except RuntimeError as exc:
                out["batch_rollback"] = {"raised": True, "error": str(exc)}
        after = (db.scalar("SELECT COUNT(*) FROM events"), db.event_revision_count())
        out["batch_rollback"].update({"before": before, "after": after})
        out["batch_rollback"]["first_row_written_before_rollback"] = (
            db.scalar("SELECT COUNT(*) FROM events WHERE event_id='acceptance-rollback-a'") == 0
        )

    # 6b-0 robustness probe: documented runner on a *plain* sqlite3 connection.
    plain = work / "legacy-plain.sqlite"
    for suffix in ("", "-wal", "-shm"):
        candidate = plain.with_name(plain.name + suffix)
        if candidate.exists():
            candidate.unlink()
    make_legacy_db(plain)
    plain_conn = sqlite3.connect(str(plain))
    try:
        try:
            ensure_schema(plain_conn)
            plain_outcome = "ok"
        except TypeError as exc:
            plain_outcome = f"TypeError: {exc}"
        plain_versions = [row[0] for row in plain_conn.execute(
            "SELECT version FROM schema_version ORDER BY version")]
        plain_rows = plain_conn.execute("SELECT COUNT(*) FROM event_revision").fetchone()[0]
    finally:
        plain_conn.close()
    out["plain_connection_probe"] = {
        "outcome": plain_outcome,
        "schema_versions": plain_versions,
        "revision_rows": plain_rows,
        "note": "DB.__init__ sets sqlite3.Row, so the production path is unaffected; the "
                "runner is not callable on a plain connection without that row factory.",
    }

    # 6b migration rollback: force migration 2 to fail after partial writes.
    legacy = work / "legacy-rollback.sqlite"
    for suffix in ("", "-wal", "-shm"):
        candidate = legacy.with_name(legacy.name + suffix)
        if candidate.exists():
            candidate.unlink()
    make_legacy_db(legacy)
    checks: dict[str, Any] = {}
    conn = sqlite3.connect(str(legacy))
    conn.row_factory = sqlite3.Row
    original_seed = migrations_mod._seed_legacy_baseline
    def exploding_seed(connection):
        original_seed(connection)
        raise RuntimeError("forced baseline failure")

    # The migration dataclass holds a direct reference to the function, so the
    # tuple used by ensure_schema must be replaced, not just the module attr.
    patched = (
        MIGRATIONS[0],
        migrations_mod.Migration(version=2, name="legacy_baseline_seed", apply=exploding_seed),
    )
    original_migrations = migrations_mod.MIGRATIONS
    migrations_mod.MIGRATIONS = patched
    try:
        try:
            ensure_schema(conn)
            checks["raised"] = False
        except RuntimeError as exc:
            checks["raised"] = True
            checks["error"] = str(exc)
        finally:
            migrations_mod.MIGRATIONS = original_migrations
            migrations_mod._seed_legacy_baseline = original_seed
        checks["schema_versions"] = [row[0] for row in conn.execute(
            "SELECT version FROM schema_version ORDER BY version")]
        checks["revision_rows"] = conn.execute("SELECT COUNT(*) FROM event_revision").fetchone()[0]
        # unpatched re-run must complete cleanly
        migrations_mod.MIGRATIONS = original_migrations
        checks["rerun"] = ensure_schema(conn)
        checks["revision_rows_after_rerun"] = conn.execute(
            "SELECT COUNT(*) FROM event_revision").fetchone()[0]
    finally:
        migrations_mod.MIGRATIONS = original_migrations
        conn.close()
    out["migration_rollback"] = checks

    check("6.1 partial batch failure rolls back head rows AND revisions",
          out["batch_rollback"]["raised"] and out["batch_rollback"]["before"] == out["batch_rollback"]["after"],
          out["batch_rollback"])
    check("6.2 failed migration records no version and no data; unpatched re-run succeeds",
          checks["raised"] and checks["schema_versions"] == [1] and checks["revision_rows"] == 0
          and checks["rerun"]["applied_now"] == [2] and checks["revision_rows_after_rerun"] == 3,
          {"schema_versions": checks["schema_versions"], "revision_rows": checks["revision_rows"],
           "rerun_applied": checks["rerun"]["applied_now"],
           "after": checks["revision_rows_after_rerun"]})
    plain = out["plain_connection_probe"]
    check("6.3 finding: runner requires sqlite3.Row on the caller's connection "
          "(plain connection fails safely with TypeError, no partial state)",
          plain["outcome"].startswith("TypeError") and plain["revision_rows"] == 0,
          plain, detail="LOW: production path (DB) sets sqlite3.Row; document the precondition "
                        "or make the seed defensive")
    return out


def stage_readers_and_perf(migrated: Path, pristine_sig: dict[str, Any],
                           pristine_rows: list[tuple], pristine_ms: float,
                           pristine_legacy: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    conn = sqlite3.connect(f"file:{migrated.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        migrated_sig = aggregate_signature(conn)
        migrated_rows = sample_rows(conn)
        out["legacy_promotions"] = conn.execute(LEGACY_PREDICATE).fetchone()[0]
        out["migrated_available_at_ms"] = timed(
            conn, "SELECT COUNT(*) FROM events WHERE available_at >= ?", ("2020-01-01",))
        out["migrated_plan"] = [list(row) for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM events WHERE available_at >= ?",
            ("2020-01-01",))]
    finally:
        conn.close()
    out["aggregate_equal"] = all(
        migrated_sig["queries"][name]["sha256"] == pristine_sig["queries"][name]["sha256"]
        for name in pristine_sig["queries"]
    )
    out["sample_rows_equal"] = pristine_rows == migrated_rows
    out["pristine_ms"] = pristine_ms
    with DB(migrated) as db:
        audit_db = db
        from medradar.audit import legacy_timestamp_promotions
        out["legacy_timestamp_promotions_fn"] = legacy_timestamp_promotions(audit_db)["total"]
    check("7.1 aggregate fingerprints identical before/after migration", out["aggregate_equal"])
    check("7.2 200-row sample (all 19 old columns) identical", out["sample_rows_equal"])
    check("7.3 old audit predicate still returns 298,810",
          out["legacy_promotions"] == pristine_legacy == 298_810
          and out["legacy_timestamp_promotions_fn"] == 298_810,
          {"sql": out["legacy_promotions"], "fn": out["legacy_timestamp_promotions_fn"]})
    return out


def stage_restore(work: Path, pristine: Path, original: Path) -> dict[str, Any]:
    restored = work / "restored.sqlite"
    shutil.copy2(pristine, restored)
    result = {
        "restored_sha256": sha256_file(restored),
        "pristine_sha256": sha256_file(pristine),
        "original_sha256": sha256_file(original),
        "bytes": restored.stat().st_size,
    }
    conn = open_ro(restored)
    try:
        result["events"] = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        result["has_event_revision"] = bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_revision'").fetchone())
        result["has_schema_version"] = bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone())
    finally:
        conn.close()
    check("8.1 restored copy is byte-identical to the pre-migration copy",
          result["restored_sha256"] == result["pristine_sha256"] == result["original_sha256"],
          {"restored": result["restored_sha256"][:16], "original": result["original_sha256"][:16]})
    check("8.2 restore removes the ledger/schema_version tables (true rollback)",
          not result["has_event_revision"] and not result["has_schema_version"]
          and result["events"] == EXPECTED_EVENTS, result)
    return result


def stage_pytest() -> dict[str, Any]:
    start = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-o", "addopts="],
        cwd=REPO, capture_output=True, text=True, timeout=900,
    )
    elapsed = round(time.perf_counter() - start, 1)
    tail = [line for line in completed.stdout.strip().splitlines() if line.strip()][-1] if completed.stdout else ""
    match = re.search(r"(\d+) passed", tail)
    passed = int(match.group(1)) if match else 0
    failed_match = re.search(r"(\d+) failed", tail)
    failed = int(failed_match.group(1)) if failed_match else 0
    check("9.1 full pytest suite green (zero failures, baseline tests included)",
          completed.returncode == 0 and failed == 0 and passed >= 1_071,
          {"passed": passed, "failed": failed, "returncode": completed.returncode, "tail": tail})
    return {"seconds": elapsed, "passed": passed, "failed": failed,
            "returncode": completed.returncode, "tail": tail}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--workdir", type=Path, default=None)
    parser.add_argument("--skip-pytest", action="store_true")
    args = parser.parse_args(argv)
    if not args.db.is_file():
        print(f"database not found: {args.db}", file=sys.stderr)
        return 2

    report: dict[str, Any] = {
        "meta": {
            "generated_at": utc_now(),
            "script": str(Path(__file__).relative_to(REPO)),
            "db": str(args.db),
            "python": sys.version.split()[0],
            "sqlite": sqlite3.sqlite_version,
            "expected_original_sha256": EXPECTED_ORIGINAL_SHA,
        },
        "original_before": {},
        "original_after": {},
    }
    before_stat = args.db.stat()
    report["original_before"] = {
        "sha256": sha256_file(args.db), "bytes": before_stat.st_size,
        "mtime_ns": before_stat.st_mtime_ns,
    }

    work = args.workdir or Path(tempfile.mkdtemp(prefix="core-accept-"))
    work.mkdir(parents=True, exist_ok=True)
    try:
        pristine = work / "pristine.sqlite"
        migrated = work / "migrated.sqlite"
        report["migration"] = stage_migration(args.db, work)
        pristine_rows = report["migration"].pop("pristine_sample_rows")  # large; compared, not serialised
        report["idempotency_and_tamper"] = stage_idempotency_and_tamper(migrated)
        report["ledger_consistency"] = stage_ledger_consistency(migrated)
        # Reader compatibility and latency are measured on the freshly migrated
        # copy, BEFORE any history/mutation stage writes to it.
        report["readers_and_perf"] = stage_readers_and_perf(
            migrated,
            report["migration"]["pristine_signature"],
            pristine_rows,
            report["migration"]["pristine_available_at_ms"],
            report["migration"]["pristine_legacy_promotions"],
        )
        report["history_retention"] = stage_history_retention(migrated)
        report["detection"] = stage_detection(migrated)
        report["rollback"] = stage_rollback(work, migrated)
        report["restore"] = stage_restore(work, pristine, args.db)
        report["pytest"] = {"skipped": True} if args.skip_pytest else stage_pytest()

        source = report["migration"]["pristine_bytes"]
        migrated_size = report["migration"]["migrated_size_before_mutations"]
        report["storage"] = {
            "source_bytes": source,
            "migrated_bytes": migrated_size["total_bytes"],
            "growth_bytes": migrated_size["total_bytes"] - source,
            "growth_pct": round(100.0 * (migrated_size["total_bytes"] - source) / source, 3),
            "migrated_main_bytes": migrated_size["main_bytes"],
            "migrated_page_count": migrated_size["page_count"],
            "source_page_count": source // 4096,
            "note": "revision table stores one full 19-column snapshot per event; growth is the "
                    "honest cost of append-only history, not compression",
        }
        with DB(migrated) as db:
            report["storage"]["revision_payload_bytes"] = db.scalar(
                "SELECT SUM(LENGTH(snapshot)+LENGTH(content_hash)+LENGTH(IFNULL(prev_content_hash,''))"
                "+LENGTH(revision_reason)+LENGTH(source)+LENGTH(origin)+LENGTH(history_completeness)"
                "+LENGTH(recorded_at)+LENGTH(first_seen_at)+LENGTH(IFNULL(available_at,''))"
                "+LENGTH(IFNULL(timestamp_quality,''))) FROM event_revision")
        report["timings"] = {
            "copy_seconds": report["migration"]["copy_seconds"],
            "migration_seconds": report["migration"]["migration_seconds"],
            "reopen_seconds": report["idempotency_and_tamper"]["reopen"]["seconds"],
            "reconcile_seconds": report["ledger_consistency"]["reconcile_seconds"],
            "available_at_ms_before": report["migration"]["pristine_available_at_ms"],
            "available_at_ms_after": report["readers_and_perf"]["migrated_available_at_ms"],
            "pytest_seconds": report["pytest"].get("seconds"),
        }
    finally:
        try:
            shutil.rmtree(work, ignore_errors=True)
        except OSError:
            pass

    after_stat = args.db.stat()
    report["original_after"] = {
        "sha256": sha256_file(args.db), "bytes": after_stat.st_size,
        "mtime_ns": after_stat.st_mtime_ns,
    }
    integrity_ok = (
        report["original_before"]["sha256"] == report["original_after"]["sha256"] == EXPECTED_ORIGINAL_SHA
        and report["original_before"]["bytes"] == report["original_after"]["bytes"]
        and report["original_before"]["mtime_ns"] == report["original_after"]["mtime_ns"]
    )
    check("0.1 original database byte-identical after acceptance",
          integrity_ok, {"before": report["original_before"], "after": report["original_after"]})
    report["checks"] = CHECKS
    report["summary"] = {
        "total": len(CHECKS),
        "passed": sum(1 for item in CHECKS if item["pass"]),
        "failed": [item["item"] for item in CHECKS if not item["pass"]],
        "verdict": "PASS" if all(item["pass"] for item in CHECKS) else "FAIL",
    }
    text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0 if report["summary"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
