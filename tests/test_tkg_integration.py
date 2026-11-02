"""Offline integration tests: real-schema events -> bitemporal TKG -> PIT context.

These tests are synthetic (a throwaway events SQLite database, no network) but
they use exactly the production path that ``scripts/tkg_import_research.py``
drives on ``data/research.sqlite``:

* :func:`medradar.tkg.adapter.import_events` (source opened ``mode=ro``),
* :func:`medradar.tkg.export.export_snapshot` determinism,
* :mod:`medradar.intelligence.graph_context` read-only as-of helpers.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from medradar.intelligence.graph_context import counts, graph_context, timeline
from medradar.tkg import TKGStore, export_snapshot, import_events, normalize_moment
from medradar.tkg.adapter import ADAPTER_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
LATE = "2999-01-01T00:00:00Z"
EARLY = "2000-01-01T00:00:00Z"

#: Same column set the adapter SELECTs from the real ``events`` table.
_EVENT_COLUMNS = (
    "event_id", "source", "kind", "event_date", "company_key", "track_id",
    "product_code", "title", "url", "payload", "first_seen_at", "available_at",
    "timestamp_quality",
)

_BASE_EVENT = {
    "event_id": "evt-0",
    "source": "openfda_device_510k_bulk",
    "kind": "510k",
    "event_date": "2021-05-14",
    "company_key": "medtronic",
    "track_id": "cardiac_rhythm",
    "product_code": "GCM",
    "title": "synthetic clearance",
    "url": "https://example.test/510k/K000000",
    "payload": "{}",
    "first_seen_at": "2026-11-01",
    "available_at": "2021-05-28T00:00:00Z",
    "timestamp_quality": "date",
}


def _source_db(path: Path, rows: list[dict]) -> Path:
    """Build a throwaway events DB with the real schema subset."""
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE events (event_id TEXT PRIMARY KEY, source TEXT NOT NULL,"
            " kind TEXT NOT NULL, event_date TEXT, company_key TEXT, track_id TEXT,"
            " product_code TEXT, title TEXT, url TEXT, payload TEXT, first_seen_at TEXT,"
            " available_at TEXT, timestamp_quality TEXT)"
        )
        for index, override in enumerate(rows):
            row = {**_BASE_EVENT, **override}
            row.setdefault("event_id", f"evt-{index}")
            conn.execute(
                f"INSERT INTO events ({','.join(_EVENT_COLUMNS)}) VALUES ({','.join('?' * len(_EVENT_COLUMNS))})",
                tuple(row[column] for column in _EVENT_COLUMNS),
            )
        conn.commit()
    finally:
        conn.close()
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


class ImportIntegrationTests(unittest.TestCase):
    def test_import_real_schema_keeps_source_readonly_and_counts_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = _source_db(tmp_path / "events.sqlite", [
                {},
                {"event_id": "evt-1", "event_date": "2024-02-01", "company_key": "abbott",
                 "track_id": "cardiac_rhythm", "product_code": "DXY"},
                {"event_id": "evt-2", "event_date": "2025-03-01", "company_key": None,
                 "track_id": None, "product_code": None},
                {"event_id": "evt-3", "event_date": "2025-04-01", "available_at": "not-a-timestamp"},
                {"event_id": "evt-4", "event_date": None},
            ])
            before = _sha256(source)
            store = TKGStore(tmp_path / "tkg.sqlite")
            try:
                report = import_events(source, store)
                counters = report["counters"]
                self.assertEqual(report["adapter_version"], ADAPTER_VERSION)
                self.assertEqual(report["source_mode"], "ro")
                self.assertEqual(counters["rows_seen"], 5)
                self.assertEqual(counters["skipped_missing_event_date"], 1)
                self.assertEqual(counters["invalid_public_time_dropped"], 1)
                self.assertEqual(counters["skipped_invalid_row"], 0)
                self.assertGreater(store.count("nodes"), 0)
                self.assertGreater(store.count("edges"), 0)
                # recorded_at is the store clock (now), never event_date/first_seen_at.
                rows = store.raw("SELECT recorded_at, valid_from, attrs FROM nodes WHERE node_type='event'")
                now_prefix = normalize_moment(datetime.now(timezone.utc), "now")[0][:13]
                self.assertTrue(all(row["recorded_at"].startswith(now_prefix) for row in rows), rows)
                self.assertTrue(all(row["valid_from"] != row["recorded_at"] for row in rows))
            finally:
                store.close()
            self.assertEqual(_sha256(source), before, "the events adapter must never modify the source DB")

    def test_snapshot_is_deterministic_and_reexport_is_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = _source_db(tmp_path / "events.sqlite", [
                {}, {"event_id": "evt-1", "event_date": "2024-02-01", "product_code": "DXY"},
            ])
            # An injected clock is only allowed on the in-memory store; it makes
            # the "later write must not change a historical export" check exact.
            clock = _Clock(datetime(2024, 1, 1, tzinfo=timezone.utc))
            store = TKGStore(":memory:", clock=clock)
            try:
                import_events(source, store)
                first = export_snapshot(store, known_at="2024-01-01T12:00:00Z", valid_at=LATE)
                second = export_snapshot(store, known_at="2024-01-01T12:00:00Z", valid_at=LATE)
                self.assertEqual(first["manifest"]["snapshot_sha256"], second["manifest"]["snapshot_sha256"])
                self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
                self.assertEqual(first["manifest"]["counts"]["nodes"], store.count("nodes"))
                self.assertEqual(first["manifest"]["counts"]["edges"], store.count("edges"))
                # ... and a write recorded later must not change that historical export.
                clock.now = datetime(2024, 1, 2, tzinfo=timezone.utc)
                store.add_node("company", "late-co", {}, valid_from="1970-01-01",
                               idempotency_key="late-co", source_locator="synthetic://test",
                               evidence_kind="source_observed", confidence=1.0)
                again = export_snapshot(store, known_at="2024-01-01T12:00:00Z", valid_at=LATE)
                self.assertEqual(again["manifest"]["snapshot_sha256"], first["manifest"]["snapshot_sha256"])
                # ... while a cutoff after the write does include it.
                later = export_snapshot(store, known_at="2024-01-03T00:00:00Z", valid_at=LATE)
                self.assertGreater(later["manifest"]["counts"]["nodes"], first["manifest"]["counts"]["nodes"])
            finally:
                store.close()

    def test_reimport_is_idempotent_and_does_not_grow_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = _source_db(tmp_path / "events.sqlite", [
                {}, {"event_id": "evt-1", "company_key": "abbott", "track_id": "structural_heart"},
            ])
            store = TKGStore(tmp_path / "tkg.sqlite")
            try:
                first = import_events(source, store)
                counts_before = {t: store.count(t) for t in ("nodes", "edges", "entities", "idempotency")}
                hash_before = export_snapshot(store, known_at=LATE)["manifest"]["snapshot_sha256"]
                second = import_events(source, store)
                counts_after = {t: store.count(t) for t in ("nodes", "edges", "entities", "idempotency")}
                hash_after = export_snapshot(store, known_at=LATE)["manifest"]["snapshot_sha256"]
                self.assertGreater(first["counters"]["assertions_created"], 0)
                self.assertEqual(second["counters"]["assertions_created"], 0)
                self.assertEqual(second["counters"]["idempotent_duplicates"],
                                 first["counters"]["assertions_created"] + first["counters"]["idempotent_duplicates"])
                self.assertEqual(counts_before, counts_after)
                self.assertEqual(hash_before, hash_after)
            finally:
                store.close()

    def test_import_script_cli_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = _source_db(tmp_path / "events.sqlite", [
                {}, {"event_id": "evt-1", "company_key": "abbott"},
            ])
            tkg = tmp_path / "tkg.sqlite"
            report_path = tmp_path / "report.json"
            command = [
                sys.executable, str(REPO_ROOT / "scripts" / "tkg_import_research.py"),
                "--db", str(source), "--tkg", str(tkg),
                "--known-at", LATE, "--no-write-export",
                "--report-out", str(report_path),
            ]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=180, cwd=str(REPO_ROOT))
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            report = json.loads(completed.stdout)
            self.assertTrue(report["checks"]["passed"], report["failures"])
            self.assertTrue(report["source"]["unchanged"])
            self.assertTrue(report["checks"]["reimport_idempotent"])
            self.assertEqual(report["snapshot"]["snapshot_sha256"], report["snapshot"]["reexport_sha256"])
            self.assertEqual(report["import"]["counters"]["rows_seen"], 2)
            self.assertTrue(report_path.is_file())
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["checks"]["passed"], True)
            # Re-running the whole script on the same store is still a no-op import.
            rerun = subprocess.run(command, capture_output=True, text=True, timeout=180, cwd=str(REPO_ROOT))
            self.assertEqual(rerun.returncode, 0, rerun.stderr or rerun.stdout)
            rerun_report = json.loads(rerun.stdout)
            self.assertEqual(rerun_report["import"]["counters"]["assertions_created"], 0)
            self.assertEqual(rerun_report["snapshot"]["snapshot_sha256"],
                             report["snapshot"]["snapshot_sha256"])


class KnowledgeTimeTests(unittest.TestCase):
    def test_known_at_gates_rows_imported_later(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first_source = _source_db(tmp_path / "events_first.sqlite", [{}])
            second_source = _source_db(tmp_path / "events_second.sqlite", [
                {}, {"event_id": "evt-1", "event_date": "2024-02-01", "company_key": "medtronic"},
            ])
            clock = _Clock(datetime(2022, 1, 1, tzinfo=timezone.utc))
            memory = TKGStore(":memory:", clock=clock)
            try:
                import_events(first_source, memory)
                first_known = memory.raw("SELECT MAX(recorded_at) AS m FROM nodes")[0]["m"]
                clock.now = datetime(2024, 6, 1, tzinfo=timezone.utc)
                import_events(second_source, memory)
                second_known = memory.raw("SELECT MAX(recorded_at) AS m FROM nodes")[0]["m"]
                self.assertLess(first_known, second_known)
                early = export_snapshot(memory, known_at=first_known)
                late = export_snapshot(memory, known_at=second_known)
                self.assertGreater(late["manifest"]["counts"]["nodes"], early["manifest"]["counts"]["nodes"])
                self.assertGreater(late["manifest"]["counts"]["edges"], early["manifest"]["counts"]["edges"])
                # Snapshot at the first knowledge time must not contain the later event.
                early_ids = {node["node_id"] for node in early["nodes"] if node["node_type"] == "event"}
                late_ids = {node["node_id"] for node in late["nodes"] if node["node_type"] == "event"}
                self.assertIn("evt-0", early_ids)
                self.assertNotIn("evt-1", early_ids)
                self.assertIn("evt-1", late_ids)
                # Persist the in-memory store to a file for the read-only helpers.
                target = tmp_path / "tkg.sqlite"
                memory.conn.execute("VACUUM INTO ?", (str(target),))
                early_context = graph_context(target, company_key="medtronic", track_id="cardiac_rhythm",
                                              known_at=first_known)
                late_context = graph_context(target, company_key="medtronic", track_id="cardiac_rhythm",
                                             known_at=second_known)
                self.assertEqual(early_context["status"], "ok")
                self.assertEqual(early_context["counts"]["events"], 1)
                self.assertEqual(late_context["counts"]["events"], 2)
                early_counts = counts(target, known_at=first_known)
                self.assertEqual(early_counts["nodes"]["total"], early["manifest"]["counts"]["nodes"])
            finally:
                memory.close()


class GraphContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.source = _source_db(self.tmp_path / "events.sqlite", [
            {"event_id": "evt-a", "event_date": "2020-01-10", "company_key": "medtronic",
             "track_id": "cardiac_rhythm", "product_code": "P1"},
            {"event_id": "evt-b", "event_date": "2024-05-20", "company_key": "medtronic",
             "track_id": "cardiac_rhythm", "product_code": "P2"},
            {"event_id": "evt-c", "event_date": "2024-06-01", "company_key": "medtronic",
             "track_id": "neurostimulation", "product_code": "P1"},
            {"event_id": "evt-d", "event_date": "2024-07-01", "company_key": "abbott",
             "track_id": "cardiac_rhythm", "product_code": "P1"},
        ])
        self.tkg = self.tmp_path / "tkg.sqlite"
        store = TKGStore(self.tkg)
        try:
            self.report = import_events(self.source, store)
        finally:
            store.close()
        self.sha_before = _sha256(self.tkg)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_pair_context_contains_both_observed_events_and_products(self) -> None:
        context = graph_context(self.tkg, company_key="medtronic", track_id="cardiac_rhythm", known_at=LATE)
        self.assertEqual(context["status"], "ok")
        self.assertEqual(context["company"]["node_id"], "medtronic")
        self.assertEqual(context["track"]["node_id"], "cardiac_rhythm")
        event_ids = [node["node_id"] for node in context["events"]]
        self.assertEqual(event_ids, ["evt-a", "evt-b"])
        self.assertEqual([node["node_id"] for node in context["products"]], ["P1", "P2"])
        self.assertEqual(context["counts"]["events"], 2)
        self.assertEqual(context["counts"]["products"], 2)
        self.assertEqual(context["counts"]["edges"], 6)  # 2 company + 2 track + 2 code edges
        # every node/edge carries assertion identity + valid interval + provenance
        for row in (*context["nodes"], *context["edges"]):
            self.assertTrue(row["assertion_id"].startswith("sha256:"))
            self.assertIn("valid_from", row)
            self.assertTrue(row["source_locator"])
            self.assertEqual(row["evidence_kind"], "source_observed")
        # `evt-d` belongs to abbott and must not leak into medtronic context.
        self.assertNotIn("evt-d", event_ids)
        # an event without the pair (other track) is excluded too
        self.assertNotIn("evt-c", event_ids)

    def test_timeline_is_sorted_by_event_time(self) -> None:
        result = timeline(self.tkg, company_key="medtronic", track_id="cardiac_rhythm", known_at=LATE)
        self.assertEqual(result["status"], "ok")
        self.assertEqual([row["event_id"] for row in result["events"]], ["evt-a", "evt-b"])
        self.assertEqual(result["events"][0]["valid_from"], "2020-01-10T00:00:00.000000Z")
        self.assertLess(result["events"][0]["valid_from"], result["events"][1]["valid_from"])
        self.assertLessEqual(result["events"][0]["recorded_at"], result["events"][1]["recorded_at"])

    def test_empty_and_unknown_pairs_report_explicit_status(self) -> None:
        unknown_company = graph_context(self.tkg, company_key="no-such-company",
                                        track_id="cardiac_rhythm", known_at=LATE)
        self.assertEqual(unknown_company["status"], "empty")
        self.assertIn("company identity not visible", unknown_company["reason"])
        self.assertEqual(unknown_company["nodes"], [])
        self.assertEqual(unknown_company["edges"], [])
        # both identities exist, but no event links this company to that track
        no_shared = graph_context(self.tkg, company_key="abbott", track_id="neurostimulation", known_at=LATE)
        self.assertEqual(no_shared["status"], "empty")
        self.assertIn("no observed events", no_shared["reason"])
        self.assertEqual(no_shared["counts"]["events"], 0)
        with self.assertRaises(ValueError):
            graph_context(self.tkg, company_key="", track_id="cardiac_rhythm", known_at=LATE)

    def test_known_at_and_valid_at_are_independent(self) -> None:
        # valid_at before the 2024 events: only the 2020 event is valid.
        early_valid = graph_context(self.tkg, company_key="medtronic", track_id="cardiac_rhythm",
                                    known_at=LATE, valid_at="2022-01-01T00:00:00Z")
        self.assertEqual(early_valid["counts"]["events"], 1)
        self.assertEqual(early_valid["events"][0]["node_id"], "evt-a")
        # valid_at after everything: both events.
        late_valid = graph_context(self.tkg, company_key="medtronic", track_id="cardiac_rhythm",
                                   known_at=LATE, valid_at="2025-01-01T00:00:00Z")
        self.assertEqual(late_valid["counts"]["events"], 2)
        # knowledge cutoff before the import: nothing is visible, explicitly.
        early_known = graph_context(self.tkg, company_key="medtronic", track_id="cardiac_rhythm",
                                    known_at=EARLY)
        self.assertEqual(early_known["status"], "empty")
        self.assertIn("not visible", early_known["reason"])

    def test_counts_match_snapshot_and_are_cutoff_sensitive(self) -> None:
        store = TKGStore(self.tkg)
        try:
            late_snapshot = export_snapshot(store, known_at=LATE, valid_at="2025-01-01T00:00:00Z")
            early_snapshot = export_snapshot(store, known_at=LATE, valid_at="2022-01-01T00:00:00Z")
        finally:
            store.close()
        late_counts = counts(self.tkg, known_at=LATE, valid_at="2025-01-01T00:00:00Z")
        early_counts = counts(self.tkg, known_at=LATE, valid_at="2022-01-01T00:00:00Z")
        self.assertEqual(late_counts["nodes"]["total"], late_snapshot["manifest"]["counts"]["nodes"])
        self.assertEqual(late_counts["edges"]["total"], late_snapshot["manifest"]["counts"]["edges"])
        self.assertEqual(early_counts["nodes"]["total"], early_snapshot["manifest"]["counts"]["nodes"])
        self.assertEqual(early_counts["edges"]["total"], early_snapshot["manifest"]["counts"]["edges"])
        self.assertLess(early_counts["nodes"]["total"], late_counts["nodes"]["total"])
        self.assertEqual(early_counts["nodes"]["company"], 2)
        self.assertEqual(late_counts["nodes"]["event"], 4)

    def test_helpers_are_read_only_and_deterministic(self) -> None:
        first = graph_context(self.tkg, company_key="medtronic", track_id="cardiac_rhythm", known_at=LATE)
        timeline_first = timeline(self.tkg, company_key="medtronic", track_id="cardiac_rhythm", known_at=LATE)
        counts_first = counts(self.tkg, known_at=LATE)
        second = graph_context(self.tkg, company_key="medtronic", track_id="cardiac_rhythm", known_at=LATE)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(json.dumps(timeline_first, sort_keys=True),
                         json.dumps(timeline(self.tkg, company_key="medtronic", track_id="cardiac_rhythm",
                                             known_at=LATE), sort_keys=True))
        self.assertEqual(json.dumps(counts_first, sort_keys=True),
                         json.dumps(counts(self.tkg, known_at=LATE), sort_keys=True))
        self.assertEqual(_sha256(self.tkg), self.sha_before, "read-only helpers must not modify the TKG store")
        with self.assertRaises(FileNotFoundError):
            graph_context(self.tmp_path / "missing.sqlite", company_key="medtronic",
                          track_id="cardiac_rhythm", known_at=LATE)


if __name__ == "__main__":
    unittest.main()
