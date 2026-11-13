"""Evidence Core v1 — write-path, ledger immutability and bypass tests.

Offline, no network, temporary SQLite files only. These tests exercise the real
``medradar.db.DB`` write path (not a reimplementation) plus the deliberate
bypasses documented in ``docs/refoundation/phase2/EVIDENCE_CORE_V1.md``.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from medradar.db import DB
from medradar.evidence_core.ledger import (
    EVENT_CONTENT_FIELDS,
    canonical_json,
    content_hash,
    latest_revision,
    reconcile,
    revisions_for,
)
from medradar.evidence_core.migrations import reinstall_guards, verify_guards


def _event(event_id: str = "e1", **overrides) -> dict:
    event = {
        "event_id": event_id,
        "source": "openfda_device_510k",
        "kind": "510k",
        "event_date": "2024-01-02",
        "title": "first title",
        "summary": "summary",
        "url": "https://example.test/1",
        "company_key": "medtronic",
        "track_id": "spine",
        "product_code": "NKB",
        "first_seen_at": "2024-01-03",
        "available_at": "2024-01-02",
    }
    event.update(overrides)
    return event


class RevisionWritePathTests(unittest.TestCase):
    def test_insert_creates_one_live_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "x.sqlite") as db:
            self.assertEqual(db.upsert_events([_event()]), 1)
            history = db.event_history("e1")
            self.assertEqual(len(history), 1)
            revision = history[0]
            self.assertEqual(revision["version"], 1)
            self.assertEqual(revision["origin"], "live")
            self.assertEqual(revision["history_completeness"], "complete")
            self.assertEqual(revision["revision_reason"], "insert")
            snapshot = revision["snapshot"]
            self.assertEqual(snapshot["title"], "first title")
            self.assertEqual(revision["content_hash"], content_hash(snapshot))
            self.assertEqual(db.reconcile_ledger()["ok"], True)

    def test_identical_reimport_adds_no_revision_and_preserves_first_seen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "x.sqlite") as db:
            db.upsert_events([_event(first_seen_at="2024-02-01")])
            before = db.query("SELECT * FROM events WHERE event_id='e1'")[0]
            # Same content, later first_seen: no revision, first_seen does not move.
            db.upsert_events([_event(first_seen_at="2025-06-01")])
            after = db.query("SELECT * FROM events WHERE event_id='e1'")[0]
            self.assertEqual(db.event_revision_count("e1"), 1)
            self.assertEqual(after["first_seen_at"], before["first_seen_at"])
            self.assertEqual(after["fetched_at"], before["fetched_at"])

    def test_earlier_first_seen_moves_head_only_never_creates_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "x.sqlite") as db:
            db.upsert_events([_event(first_seen_at="2024-05-05")])
            db.upsert_events([_event(first_seen_at="2024-01-01")])
            row = db.query("SELECT first_seen_at FROM events WHERE event_id='e1'")[0]
            self.assertEqual(row["first_seen_at"].startswith("2024-01-01"), True)
            self.assertEqual(db.event_revision_count("e1"), 1)
            # The immutable v1 keeps the value it recorded; the next real change
            # carries the MIN forward.
            events_v1 = db.event_history("e1")[0]
            self.assertTrue(events_v1["first_seen_at"].startswith("2024-05-05"))
            db.upsert_events([_event(first_seen_at="2024-01-01", title="second title")])
            history = db.event_history("e1")
            self.assertEqual(len(history), 2)
            self.assertTrue(history[1]["first_seen_at"].startswith("2024-01-01"))

    def test_changed_import_appends_revision_keeping_old_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "x.sqlite") as db:
            db.upsert_events([_event()])
            db.upsert_events([_event(title="second title", summary="changed")])
            history = db.event_history("e1")
            self.assertEqual([h["version"] for h in history], [1, 2])
            self.assertEqual(history[0]["snapshot"]["title"], "first title")
            self.assertEqual(history[1]["snapshot"]["title"], "second title")
            self.assertEqual(history[1]["revision_reason"], "update")
            self.assertEqual(history[1]["prev_content_hash"], history[0]["content_hash"])
            head = db.query("SELECT title FROM events WHERE event_id='e1'")[0]
            self.assertEqual(head["title"], "second title")
            self.assertEqual(db.reconcile_ledger()["ok"], True)

    def test_content_hash_is_deterministic_and_ignores_volatile_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "x.sqlite") as db:
            db.upsert_events([_event(first_seen_at="2024-01-03", fetched_at="2024-01-03T10:00:00Z")])
            revision = db.event_history("e1")[0]
            first = revision["content_hash"]
            # Re-serialise with shuffled key order: canonical JSON must agree.
            snapshot = dict(revision["snapshot"])
            shuffled = {key: snapshot[key] for key in reversed(list(snapshot))}
            self.assertEqual(content_hash(shuffled), content_hash(snapshot))
            self.assertEqual(content_hash(snapshot), first)
            self.assertNotIn("first_seen_at", EVENT_CONTENT_FIELDS)
            self.assertNotIn("fetched_at", EVENT_CONTENT_FIELDS)
            # A volatile-only change must not become a revision.
            db.upsert_events([_event(first_seen_at="2024-01-03", fetched_at="2030-01-01T00:00:00Z")])
            self.assertEqual(db.event_revision_count("e1"), 1)

    def test_batch_is_one_transaction_and_rolls_back_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "x.sqlite") as db:
            with mock.patch(
                "medradar.evidence_core.ledger.append_revision",
                side_effect=lambda conn, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
                if kw["event_id"] == "b" else _append(conn, **kw),
            ):
                with self.assertRaises(RuntimeError):
                    db.upsert_events([_event("a"), _event("b")])
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM events"), 0)
            self.assertEqual(db.event_revision_count(), 0)

    def test_empty_batch_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "x.sqlite") as db:
            self.assertEqual(db.upsert_events([]), 0)
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM events"), 0)
            self.assertEqual(db.event_revision_count(), 0)

    def test_mixed_batch_insert_then_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "x.sqlite") as db:
            db.upsert_events([_event("a"), _event("b", title="b-title")])
            db.upsert_events([
                _event("a", title="a-v2"),
                _event("b", title="b-title"),  # identical -> no revision
                _event("c"),
            ])
            self.assertEqual(db.event_revision_count("a"), 2)
            self.assertEqual(db.event_revision_count("b"), 1)
            self.assertEqual(db.event_revision_count("c"), 1)
            self.assertEqual(db.reconcile_ledger()["head_mismatch_count"], 0)


def _append(conn, **kwargs):
    from medradar.evidence_core import ledger

    return ledger.append_revision(conn, **kwargs)


class ImmutabilityTriggerTests(unittest.TestCase):
    def _db(self, tmp: str) -> DB:
        db = DB(Path(tmp) / "triggers.sqlite")
        db.upsert_events([_event()])
        return db

    def test_guards_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self._db(tmp) as db:
            guards = verify_guards(db.conn)
            self.assertEqual(guards["ok"], True)
            self.assertEqual(len(guards["present"]), 3)

    def test_update_revision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self._db(tmp) as db:
            with self.assertRaises(sqlite3.Error):
                db.conn.execute("UPDATE event_revision SET revision_reason='forged'")
            self.assertEqual(db.event_history("e1")[0]["revision_reason"], "insert")

    def test_delete_revision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self._db(tmp) as db:
            with self.assertRaises(sqlite3.Error):
                db.conn.execute("DELETE FROM event_revision")
            self.assertEqual(db.event_revision_count(), 1)

    def test_insert_or_replace_revision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self._db(tmp) as db:
            with self.assertRaises(sqlite3.Error):
                db.conn.execute(
                    "INSERT OR REPLACE INTO event_revision SELECT * FROM event_revision"
                )
            self.assertEqual(db.event_revision_count(), 1)

    def test_recursive_triggers_flag_does_not_weaken_guards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self._db(tmp) as db:
            for flag in ("ON", "OFF"):
                db.conn.execute(f"PRAGMA recursive_triggers={flag}")
                with self.assertRaises(sqlite3.Error):
                    db.conn.execute("UPDATE event_revision SET source='x'")
            self.assertEqual(db.event_revision_count(), 1)


class BypassMatrixTests(unittest.TestCase):
    """The ledger deliberately does not make ``events`` immutable."""

    def test_insert_or_replace_on_events_is_not_caught_by_trigger_but_reconcile_finds_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "bypass.sqlite") as db:
            db.upsert_events([_event()])
            # Exactly what the pre-ledger write path did: REPLACE the head row.
            db.conn.execute(
                "INSERT OR REPLACE INTO events(event_id, source, kind, event_date, title,"
                " payload, timestamp_quality) VALUES (?,?,?,?,?,?,?)",
                ("e1", "openfda_device_510k", "510k", "2024-01-02", "forged title", "", "unknown"),
            )
            db.conn.commit()
            self.assertEqual(db.event_revision_count("e1"), 1)  # no revision appended
            report = reconcile(db.conn)
            self.assertEqual(report["head_mismatch_count"], 1)
            self.assertEqual(report["ok"], False)

    def test_direct_update_on_events_is_detected_by_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "bypass2.sqlite") as db:
            db.upsert_events([_event()])
            db.conn.execute("UPDATE events SET title='forged' WHERE event_id='e1'")
            db.conn.commit()
            report = db.reconcile_ledger()
            self.assertEqual(report["head_mismatch_count"], 1)

    def test_delete_on_events_leaves_orphan_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "bypass3.sqlite") as db:
            db.upsert_events([_event()])
            db.conn.execute("DELETE FROM events WHERE event_id='e1'")
            db.conn.commit()
            report = db.reconcile_ledger()
            self.assertEqual(report["orphan_revision_count"], 1)
            self.assertEqual(report["ok"], False)

    def test_dropped_trigger_permits_forgery_and_can_be_reinstalled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, DB(Path(tmp) / "bypass4.sqlite") as db:
            db.upsert_events([_event()])
            db.conn.execute("DROP TRIGGER event_revision_no_update")
            db.conn.commit()
            self.assertFalse(verify_guards(db.conn)["ok"])
            # Not caught: the append-only promise is gone while the trigger is gone.
            db.conn.execute("UPDATE event_revision SET revision_reason='forged'")
            db.conn.commit()
            self.assertEqual(db.event_history("e1")[0]["revision_reason"], "forged")
            # Reinstalling guards does NOT repair the forged row; it only restores
            # future protection. Reconcile cannot see it (hash fields untouched).
            guards = reinstall_guards(db.conn)
            self.assertTrue(guards["ok"])
            with self.assertRaises(sqlite3.Error):
                db.conn.execute("UPDATE event_revision SET revision_reason='again'")

    def test_whole_file_replacement_is_outside_the_threat_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "a.sqlite"
            forged = Path(tmp) / "b.sqlite"
            with DB(source) as db:
                db.upsert_events([_event()])
            with DB(forged) as db:
                db.upsert_events([_event(event_id="different")])
            # Use SQLite's backup API so the comparison is of a checkpointed single
            # file, not of a main file plus a WAL sidecar.
            original = _single_file_bytes(source, Path(tmp) / "a_clean.sqlite")
            replacement = _single_file_bytes(forged, Path(tmp) / "b_clean.sqlite")
            self.assertNotEqual(hashlib.sha256(original).hexdigest(),
                                hashlib.sha256(replacement).hexdigest())
            # Replacing the file is invisible to every DB-level guard: the DB
            # that opens next sees a self-consistent, different history.
            for suffix in ("-wal", "-shm"):
                sidecar = source.with_name(source.name + suffix)
                if sidecar.exists():
                    sidecar.unlink()
            source.write_bytes(replacement)
            with DB(source) as db:
                self.assertEqual(db.scalar("SELECT COUNT(*) FROM events"), 1)
                self.assertEqual(db.event_history("different")[0]["version"], 1)


def _single_file_bytes(path: Path, out: Path) -> bytes:
    import sqlite3 as _sqlite3

    source = _sqlite3.connect(str(path))
    target = _sqlite3.connect(str(out))
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()
    return out.read_bytes()


if __name__ == "__main__":
    unittest.main()
