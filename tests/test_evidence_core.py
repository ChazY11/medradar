"""Evidence Core v1 — migration runner, legacy baseline and restore-drill tests.

The synthetic legacy databases here are built with the *pre-ledger* shape
(no ``published_at``/``first_seen_at``/``available_at`` columns) so the real
forward-migration path in ``medradar.db.DB.__init__`` is exercised, not mocked.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from medradar.db import DB
from medradar.evidence_core.ledger import content_hash
from medradar.evidence_core.migrations import (
    MIGRATIONS,
    ensure_schema,
    verify_guards,
)

LEGACY_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    event_date TEXT,
    as_of TEXT,
    company_key TEXT,
    applicant_raw TEXT,
    country TEXT DEFAULT 'US',
    track_id TEXT,
    product_code TEXT,
    title TEXT,
    summary TEXT,
    url TEXT,
    payload TEXT,
    fetched_at TEXT
);
"""


def _make_legacy_db(path: Path, rows: list[dict]) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(LEGACY_EVENTS_DDL)
        for row in rows:
            conn.execute(
                "INSERT INTO events(event_id, source, kind, event_date, as_of, company_key,"
                " applicant_raw, country, track_id, product_code, title, summary, url, payload,"
                " fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["event_id"], row["source"], row["kind"], row.get("event_date"),
                    row.get("as_of", "2026-10-30"), row.get("company_key"),
                    row.get("applicant_raw", ""), "US", row.get("track_id"),
                    row.get("product_code"), row.get("title", ""), row.get("summary", ""),
                    row.get("url", ""), row.get("payload", ""),
                    row.get("fetched_at", "2026-10-30T19:00:00Z"),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _legacy_rows() -> list[dict]:
    return [
        {"event_id": "legacy-1", "source": "openfda_device_510k", "kind": "510k",
         "event_date": "2001-02-03", "company_key": "medtronic", "track_id": "spine",
         "product_code": "NKB", "title": "one", "payload": '{"k_number":"K010001"}'},
        {"event_id": "legacy-2", "source": "ctgov", "kind": "trial",
         "event_date": "2010-05-06", "applicant_raw": "Some Sponsor", "title": "two",
         "payload": '{"nct_id":"NCT00000002"}'},
        {"event_id": "legacy-3", "source": "sec_edgar_corpus", "kind": "8k_catalyst",
         "event_date": "2015-01-02", "title": "three", "payload": ""},
    ]


class MigrationRunnerTests(unittest.TestCase):
    def test_fresh_db_gets_schema_version_ledger_and_guards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "fresh.sqlite") as db:
            report = db.evidence_core_report
            self.assertEqual(report["schema_version_before"], 0)
            self.assertEqual(report["schema_version_after"], 2)
            self.assertEqual(report["applied_now"], [1, 2])
            rows = db.query("SELECT version, name, checksum, applied_at FROM schema_version ORDER BY version")
            self.assertEqual([row["version"] for row in rows], [1, 2])
            self.assertTrue(all(row["checksum"] for row in rows))
            self.assertTrue(all(row["applied_at"] for row in rows))
            self.assertEqual(verify_guards(db.conn)["ok"], True)
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM event_revision"), 0)
            self.assertIn("idx_events_available_at",
                          {row[0] for row in db.conn.execute(
                              "SELECT name FROM sqlite_master WHERE type='index'")})

    def test_reopen_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reopen.sqlite"
            with DB(path) as db:
                db.upsert_events([_event("e1")])
                revisions = db.event_revision_count()
            with DB(path) as db:
                self.assertEqual(db.evidence_core_report["applied_now"], [])
                self.assertEqual(db.evidence_core_report["schema_version_after"], 2)
                self.assertEqual(db.event_revision_count(), revisions)
                self.assertEqual(db.ensure_evidence_core()["applied_now"], [])

    def test_checksum_tamper_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "tamper.sqlite") as db:
            db.execute("UPDATE schema_version SET checksum='deadbeef' WHERE version=1")
            db.conn.commit()
            with self.assertRaises(RuntimeError) as ctx:
                ensure_schema(db.conn)
            self.assertIn("checksum mismatch", str(ctx.exception))

    def test_unknown_applied_migration_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "unknown.sqlite") as db:
            db.execute(
                "INSERT INTO schema_version(version, name, checksum, applied_at)"
                " VALUES (99, 'future', 'x', '2030-01-01T00:00:00.000000Z')"
            )
            db.conn.commit()
            with self.assertRaises(RuntimeError):
                ensure_schema(db.conn)


class LegacyBaselineTests(unittest.TestCase):
    def test_migration_seeds_exactly_one_marked_baseline_per_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.sqlite"
            _make_legacy_db(path, _legacy_rows())
            with DB(path) as db:
                self.assertEqual(db.scalar("SELECT COUNT(*) FROM events"), 3)
                self.assertEqual(db.scalar("SELECT COUNT(*) FROM event_revision"), 3)
                detail = db.evidence_core_report["details"]["legacy_baseline_seed"]
                self.assertEqual(detail["baseline_inserted"], 3)
                self.assertEqual(detail["already_revisioned"], 0)
                revisions = db.query(
                    "SELECT event_id, version, origin, history_completeness, revision_reason,"
                    " recorded_at, first_seen_at, available_at, timestamp_quality, snapshot"
                    " FROM event_revision ORDER BY event_id"
                )
                self.assertEqual([row["event_id"] for row in revisions], ["legacy-1", "legacy-2", "legacy-3"])
                for row in revisions:
                    self.assertEqual(row["version"], 1)
                    self.assertEqual(row["origin"], "legacy_baseline")
                    self.assertEqual(row["history_completeness"], "baseline_only")
                    self.assertIn("baseline", row["revision_reason"])
                    self.assertIn("history unavailable", row["revision_reason"])
                    self.assertTrue(row["recorded_at"].endswith("Z"))
                    snapshot = json.loads(row["snapshot"])
                    self.assertEqual(snapshot["event_id"], row["event_id"])
                    # The legacy forward-migration backfilled the timing columns;
                    # the baseline records the post-migration row, not invented data.
                    # ALTER TABLE ADD COLUMN ... DEFAULT 'date' fills pre-existing
                    # rows with 'date', so the later COALESCE('estimated') branch is
                    # not reached for this schema shape.
                    self.assertEqual(snapshot["published_at"], snapshot["event_date"])
                    self.assertEqual(snapshot["timestamp_quality"], "date")
                self.assertEqual(db.reconcile_ledger()["head_mismatch_count"], 0)

    def test_reopen_does_not_reseed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy2.sqlite"
            _make_legacy_db(path, _legacy_rows())
            with DB(path) as db:
                first = db.event_revision_count()
            with DB(path) as db:
                self.assertEqual(db.evidence_core_report["applied_now"], [])
                self.assertEqual(db.event_revision_count(), first)

    def test_change_after_baseline_marks_history_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy3.sqlite"
            _make_legacy_db(path, _legacy_rows()[:1])
            with DB(path) as db:
                db.upsert_events([_event("legacy-1", title="changed after migration")])
                history = db.event_history("legacy-1")
                self.assertEqual([h["version"] for h in history], [1, 2])
                self.assertEqual(history[0]["origin"], "legacy_baseline")
                self.assertEqual(history[1]["origin"], "live")
                self.assertEqual(history[1]["history_completeness"], "partial_before_ledger")
                self.assertEqual(history[0]["snapshot"]["title"], "one")
                self.assertEqual(history[1]["snapshot"]["title"], "changed after migration")
                self.assertEqual(db.reconcile_ledger()["ok"], True)

    def test_old_queries_return_the_same_rows_after_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy4.sqlite"
            _make_legacy_db(path, _legacy_rows())
            query = ("SELECT event_id, source, kind, event_date, company_key, track_id,"
                     " product_code, title, summary, url, payload FROM events ORDER BY event_id")
            conn = sqlite3.connect(str(path))
            try:
                before = [tuple(row) for row in conn.execute(query)]
            finally:
                conn.close()
            with DB(path) as db:
                after = [tuple(row) for row in db.conn.execute(query)]
                # A representative existing reader still sees identical rows.
                self.assertEqual(before, after)
                self.assertEqual(db.scalar("SELECT COUNT(*) FROM events"), len(before))


class BackupRestoreDrillTests(unittest.TestCase):
    def test_migrate_backup_corrupt_restore_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "live.sqlite"
            backup = Path(tmp) / "backup.sqlite"
            with DB(live) as db:
                db.upsert_events([_event("e1"), _event("e2", title="two")])
                db.upsert_events([_event("e1", title="one-v2")])
                counts = (db.scalar("SELECT COUNT(*) FROM events"), db.event_revision_count())
                latest_hash = db.event_history("e1")[-1]["content_hash"]
            shutil.copy2(live, backup)

            # Corrupt the live database through a documented bypass, then restore.
            with DB(live) as db:
                db.conn.execute("UPDATE events SET title='corrupted' WHERE event_id='e1'")
                db.conn.commit()
                self.assertEqual(db.reconcile_ledger()["head_mismatch_count"], 1)
            shutil.copy2(backup, live)
            for suffix in ("-wal", "-shm"):
                sidecar = live.with_name(live.name + suffix)
                if sidecar.exists():
                    sidecar.unlink()

            with DB(live) as db:
                self.assertEqual(
                    (db.scalar("SELECT COUNT(*) FROM events"), db.event_revision_count()), counts
                )
                self.assertEqual(db.event_history("e1")[-1]["content_hash"], latest_hash)
                self.assertEqual(db.reconcile_ledger()["ok"], True)
                self.assertEqual(verify_guards(db.conn)["ok"], True)

    def test_backup_file_hash_is_stable_after_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stable.sqlite"
            with DB(path) as db:
                db.upsert_events([_event("e1")])
            first = hashlib.sha256(path.read_bytes()).hexdigest()
            with DB(path) as db:
                self.assertEqual(db.event_revision_count(), 1)
            second = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(first, second)


def _event(event_id: str = "e1", **overrides) -> dict:
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


if __name__ == "__main__":
    unittest.main()
