"""Offline acceptance tests for the temporal knowledge graph (TKG) MVP.

Covers the Director-approved contract: strict system-knowledge queries with
independent ``known_at``/``valid_at`` cutoffs, append-only immutable history,
store-assigned monotonic UTC clocks, explicit idempotency, evidence
validation, atomic batches, deterministic PIT export, and a read-only events
adapter. Everything is synthetic; no network, no production databases.
"""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from medradar.tkg import (
    ClockRegressionError,
    IdempotencyConflict,
    TKGError,
    TKGQuery,
    TKGStore,
    TKGValidationError,
    export_snapshot,
    import_events,
    open_source,
    write_export,
)
from medradar.tkg.store import canonical_json

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def make_clock(*stamps: datetime):
    queue = iter(stamps)
    return lambda: next(queue)


def step_clock(start: datetime = T0, step: timedelta = timedelta(days=1)):
    """Unbounded monotonic clock for tests that write an unknown number of batches."""
    state = {"t": start}

    def tick() -> datetime:
        value = state["t"]
        state["t"] = value + step
        return value

    return tick


def dt(day: int, hour: int = 0) -> datetime:
    return T0 + timedelta(days=day, hours=hour)


def stamp(day: int, hour: int = 0) -> str:
    return dt(day, hour).strftime("%Y-%m-%dT%H:%M:%SZ")


EVIDENCE = {
    "source_locator": "synthetic://test",
    "evidence_kind": "source_observed",
    "confidence": 1.0,
}


def node_spec(node_id: str, attrs: dict, key: str, valid_from: str = "2020-01-01",
              valid_to: str | None = None, **extra) -> dict:
    return {
        "record": "node", "node_type": "company", "node_id": node_id,
        "attrs": attrs, "valid_from": valid_from, "valid_to": valid_to,
        "idempotency_key": key, **EVIDENCE, **extra,
    }


class StoreWriteTests(unittest.TestCase):
    def test_recorded_at_assigned_by_store_not_caller(self) -> None:
        # Missing input knowledge time is fine for a NEW observation: the
        # store stamps it. The caller has no recorded_at parameter at all.
        store = TKGStore(":memory:", clock=make_clock(dt(0)))
        result = store.add_node("company", "ACME", {"a": 1}, valid_from="2020-06-01",
                                **EVIDENCE, idempotency_key="k1")
        self.assertEqual(result["recorded_at"], stamp(0))

    def test_clock_timezone_strictness(self) -> None:
        store = TKGStore(":memory:", clock=make_clock(dt(0), dt(1)))
        # Non-UTC offset input is normalized to UTC.
        store.add_node("company", "ACME", {}, valid_from="2024-06-01T20:00:00+08:00",
                       **EVIDENCE, idempotency_key="k1")
        row = store.raw("SELECT valid_from FROM nodes")[0]
        self.assertEqual(row["valid_from"], "2024-06-01T12:00:00Z")
        self.assertTrue(row["valid_from"].endswith("Z"))
        # Naive datetimes are rejected, never guessed.
        with self.assertRaises(TKGValidationError):
            store.add_node("company", "ACME2", {}, valid_from=datetime(2024, 6, 1),
                           **EVIDENCE, idempotency_key="k2")
        with self.assertRaises(TKGValidationError):
            store.add_node("company", "ACME3", {}, valid_from="2024-06-01T10:00:00",
                           **EVIDENCE, idempotency_key="k3")

    def test_valid_interval_must_be_non_empty_half_open(self) -> None:
        store = TKGStore(":memory:", clock=make_clock(dt(0)))
        with self.assertRaises(TKGValidationError):
            store.add_node("company", "ACME", {}, valid_from="2024-01-10",
                           valid_to="2024-01-10", **EVIDENCE, idempotency_key="k1")
        with self.assertRaises(TKGValidationError):
            store.add_node("company", "ACME", {}, valid_from="2024-01-10",
                           valid_to="2024-01-01", **EVIDENCE, idempotency_key="k2")
        # valid_to == None (open) is legal.
        store.add_node("company", "ACME", {}, valid_from="2024-01-10",
                       **EVIDENCE, idempotency_key="k3")
        self.assertEqual(store.count("nodes"), 1)

    def test_confidence_and_evidence_validation(self) -> None:
        store = TKGStore(":memory:", clock=make_clock(*[dt(i) for i in range(8)]))
        bad = [
            ({**EVIDENCE, "confidence": float("nan")}, "nan"),
            ({**EVIDENCE, "confidence": float("inf")}, "inf"),
            ({**EVIDENCE, "confidence": 1.5}, "above 1"),
            ({**EVIDENCE, "confidence": -0.1}, "below 0"),
            ({**EVIDENCE, "evidence_kind": "rumor"}, "bad kind"),
            ({k: v for k, v in EVIDENCE.items() if k != "source_locator"}, "no locator"),
        ]
        for spec, label in bad:
            with self.assertRaises(TKGValidationError, msg=label):
                store.add_node("company", "ACME", {}, valid_from="2024-01-01",
                               idempotency_key=f"bad-{label}", **spec)
        # NaN inside attrs must not serialize into the store either.
        with self.assertRaises(TKGValidationError):
            store.add_node("company", "ACME", {"x": float("nan")}, valid_from="2024-01-01",
                           **EVIDENCE, idempotency_key="nan-attrs")
        self.assertEqual(store.count("nodes"), 0)

    def test_batch_is_atomic_rollback(self) -> None:
        store = TKGStore(":memory:", clock=make_clock(dt(0)))
        batch = [
            node_spec("GOOD1", {}, "g1"),
            node_spec("GOOD2", {}, "g2"),
            node_spec("BAD", {}, "g3", valid_to="2019-01-01"),  # invalid interval
        ]
        with self.assertRaises(TKGValidationError):
            store.apply(batch)
        self.assertEqual(store.count("nodes"), 0)
        self.assertEqual(store.count("idempotency"), 0)

    def test_orphan_edge_fails_and_rolls_back(self) -> None:
        store = TKGStore(":memory:", clock=make_clock(dt(0)))
        batch = [
            node_spec("ACME", {}, "g1"),
            {"record": "edge", "edge_type": "supplies", "src_type": "company",
             "src_id": "GHOST", "dst_type": "company", "dst_id": "ACME",
             "attrs": {}, "valid_from": "2024-01-01", "idempotency_key": "e1", **EVIDENCE},
        ]
        with self.assertRaises(TKGValidationError):
            store.apply(batch)
        self.assertEqual(store.count("nodes"), 0)
        self.assertEqual(store.count("edges"), 0)

    def test_immutable_history_sql_guards(self) -> None:
        store = TKGStore(":memory:", clock=make_clock(dt(0)))
        store.add_node("company", "ACME", {"v": 1}, valid_from="2020-01-01",
                       **EVIDENCE, idempotency_key="k1")
        with self.assertRaises(sqlite3.IntegrityError):
            store.conn.execute("UPDATE nodes SET attrs = '{\"v\":2}'")
        with self.assertRaises(sqlite3.IntegrityError):
            store.conn.execute("DELETE FROM nodes")
        row = store.raw("SELECT attrs FROM nodes")[0]
        self.assertEqual(json.loads(row["attrs"]), {"v": 1})

    def test_clock_regression_rejected_and_equal_timestamps_sequenced(self) -> None:
        # Equal timestamps get deterministic seq 1,2; a backwards clock fails.
        store = TKGStore(":memory:", clock=make_clock(dt(0), dt(0), dt(-1)))
        r1 = store.add_node("company", "ACME", {"v": 1}, valid_from="2020-01-01",
                            **EVIDENCE, idempotency_key="k1")
        r2 = store.add_node("company", "ACME", {"v": 2}, valid_from="2020-01-01",
                            **EVIDENCE, idempotency_key="k2")
        self.assertEqual((r1["recorded_at"], r1["seq"]), (stamp(0), 1))
        self.assertEqual((r2["recorded_at"], r2["seq"]), (stamp(0), 2))
        with self.assertRaises(ClockRegressionError):
            store.add_node("company", "ACME", {"v": 3}, valid_from="2020-01-01",
                           **EVIDENCE, idempotency_key="k3")

    def test_test_clock_rejected_on_persistent_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(TKGError):
                TKGStore(Path(tmp) / "tkg.sqlite", clock=make_clock(dt(0)))

    def test_production_clock_does_not_regress_across_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tkg.sqlite"
            store = TKGStore(path)
            store.add_node("company", "ACME", {}, valid_from="2020-01-01",
                           **EVIDENCE, idempotency_key="k1")
            store.close()
            # A persistent store persists its monotonic anchor; an injected
            # clock is still rejected even for simulation.
            with self.assertRaises(TKGError):
                TKGStore(path, clock=make_clock(dt(0)))
            store2 = TKGStore(path)
            self.assertEqual(store2.raw("SELECT COUNT(*) AS n FROM nodes")[0]["n"], 1)
            store2.close()


class IdempotencyTests(unittest.TestCase):
    def test_identical_retry_returns_original_unchanged(self) -> None:
        store = TKGStore(":memory:", clock=make_clock(dt(0), dt(1)))
        first = store.add_node("company", "ACME", {"v": 1}, valid_from="2020-01-01",
                               **EVIDENCE, idempotency_key="k1")
        retry = store.add_node("company", "ACME", {"v": 1}, valid_from="2020-01-01",
                               **EVIDENCE, idempotency_key="k1")
        self.assertEqual(retry["status"], "duplicate")
        self.assertEqual(retry["assertion_id"], first["assertion_id"])
        self.assertEqual(retry["recorded_at"], first["recorded_at"])
        self.assertEqual(retry["seq"], first["seq"])
        self.assertEqual(store.count("nodes"), 1)  # no new history on retry

    def test_conflicting_reuse_of_key_fails(self) -> None:
        store = TKGStore(":memory:", clock=make_clock(dt(0), dt(1)))
        store.add_node("company", "ACME", {"v": 1}, valid_from="2020-01-01",
                       **EVIDENCE, idempotency_key="k1")
        with self.assertRaises(IdempotencyConflict):
            store.add_node("company", "ACME", {"v": 2}, valid_from="2020-01-01",
                           **EVIDENCE, idempotency_key="k1")

    def test_different_keys_permit_later_revisions(self) -> None:
        store = TKGStore(":memory:", clock=make_clock(dt(0), dt(1)))
        store.add_node("company", "ACME", {"v": 1}, valid_from="2020-01-01",
                       **EVIDENCE, idempotency_key="k1")
        later = store.add_node("company", "ACME", {"v": 2}, valid_from="2020-01-01",
                               **EVIDENCE, idempotency_key="k2")
        self.assertEqual(later["status"], "created")
        self.assertEqual(store.count("nodes"), 2)


class QuerySemanticsTests(unittest.TestCase):
    """A1-A4: late arrival, corrections, retractions, latest-before-valid."""

    def _history(self) -> TKGStore:
        # T0: ACME private; T1: GLOBEX private; T2: ACME correction;
        # T3: GLOBEX retraction (closes validity); T4: SPINE late arrival.
        store = TKGStore(":memory:", clock=make_clock(dt(0), dt(1), dt(2), dt(3), dt(4)))
        store.apply([
            node_spec("ACME", {"stage": "private"}, "acme-r1"),
            node_spec("GLOBEX", {"stage": "private"}, "globex-r1"),
        ])
        store.apply([node_spec("ACME", {"stage": "ipo-filed"}, "acme-r2")])
        store.apply([node_spec("GLOBEX", {"stage": "private"}, "globex-r2",
                               valid_to="2024-06-01")])
        store.apply([node_spec("OTHER", {"stage": "n/a"}, "other-r1")])
        store.apply([node_spec("SPINE", {"stage": "cleared"}, "spine-r1")])
        return store

    def test_revision_cannot_alter_history(self) -> None:
        store = self._history()
        # Between r1 (recorded T0) and r2 (recorded T1): the original value.
        past = TKGQuery(store).snapshot(known_at=stamp(0, 12))
        acme = [n for n in past["nodes"] if n["node_id"] == "ACME"][0]
        self.assertEqual(acme["attrs"], {"stage": "private"})

    def test_late_arrival_gated_on_recorded_at(self) -> None:
        store = self._history()
        # SPINE's assertion is valid from 2020 but only recorded at T4.
        early = TKGQuery(store).snapshot(known_at=stamp(3))
        self.assertNotIn("SPINE", [n["node_id"] for n in early["nodes"]])
        late = TKGQuery(store).snapshot(known_at=stamp(4))
        self.assertIn("SPINE", [n["node_id"] for n in late["nodes"]])
        # Without a valid filter it is visible at any known_at >= T4.
        novalid = TKGQuery(store).latest_node_revisions(stamp(4), valid_at=None)
        self.assertIn("SPINE", [n["node_id"] for n in novalid])

    def test_retraction_never_resurrects_older_revision(self) -> None:
        store = self._history()
        # Before the retraction was recorded: GLOBEX visible via r1.
        before = TKGQuery(store).snapshot(known_at=stamp(2), valid_at="2021-01-01")
        self.assertIn("GLOBEX", [n["node_id"] for n in before["nodes"]])
        # After the retraction (r2 closes validity at 2024-06-01): at any
        # validity date from then on GLOBEX is gone...
        after = TKGQuery(store).snapshot(known_at=stamp(3), valid_at="2024-07-01")
        self.assertNotIn("GLOBEX", [n["node_id"] for n in after["nodes"]])
        # ...and at earlier validity dates the selected revision is r2 (the
        # retraction), never a resurrection of r1.
        mid = TKGQuery(store).snapshot(known_at=stamp(3), valid_at="2021-01-01")
        globex = [n for n in mid["nodes"] if n["node_id"] == "GLOBEX"]
        self.assertEqual(len(globex), 1)
        r1_id = store.raw("SELECT assertion_id FROM nodes WHERE idempotency_key = 'globex-r1'")[0]["assertion_id"]
        self.assertNotEqual(globex[0]["assertion_id"], r1_id)

    def test_latest_before_valid_filtering(self) -> None:
        # Trap: old revision has a LONGER valid interval than the correction.
        store = TKGStore(":memory:", clock=make_clock(dt(0), dt(1), dt(2)))
        store.apply([node_spec("ACME", {"v": "old"}, "r1", valid_from="2019-01-01")])
        store.apply([node_spec("ACME", {"v": "new"}, "r2",
                               valid_from="2023-01-01", valid_to="2023-06-01")])
        query = TKGQuery(store)
        # Latest revision (r2) selected first; at a validity date where r2 is
        # closed the entity is absent - r1 is NOT revived.
        snap = query.snapshot(known_at=stamp(2), valid_at="2024-01-01")
        self.assertNotIn("ACME", [n["node_id"] for n in snap["nodes"]])
        # Inside r2's window the new value shows.
        snap = query.snapshot(known_at=stamp(2), valid_at="2023-03-01")
        acme = [n for n in snap["nodes"] if n["node_id"] == "ACME"][0]
        self.assertEqual(acme["attrs"], {"v": "new"})

    def test_entity_has_many_relations_versioned_by_assertion(self) -> None:
        # One entity, many edges: each relation is its own assertion lineage.
        store = TKGStore(":memory:", clock=make_clock(dt(0), dt(1)))
        store.apply([
            node_spec("ACME", {}, "n1"),
            node_spec("GLOBEX", {}, "n2"),
            node_spec("SPINE", {}, "n3"),
        ])
        store.apply([
            {"record": "edge", "edge_type": "supplies", "src_type": "company",
             "src_id": "ACME", "dst_type": "company", "dst_id": "GLOBEX",
             "attrs": {}, "valid_from": "2020-01-01", "idempotency_key": "e1", **EVIDENCE},
            {"record": "edge", "edge_type": "competes", "src_type": "company",
             "src_id": "ACME", "dst_type": "company", "dst_id": "SPINE",
             "attrs": {}, "valid_from": "2020-01-01", "idempotency_key": "e2", **EVIDENCE},
        ])
        edges = TKGQuery(store).latest_edge_revisions(stamp(1))
        self.assertEqual(len(edges), 2)
        types = {(e["edge_type"], e["dst"]["node_id"]) for e in edges}
        self.assertEqual(types, {("supplies", "GLOBEX"), ("competes", "SPINE")})

    def test_public_time_is_metadata_never_clock(self) -> None:
        # public_time earlier than recorded_at is legal and stored as metadata.
        store = TKGStore(":memory:", clock=make_clock(dt(0), dt(1)))
        store.add_node("company", "ACME", {}, valid_from="2020-01-01",
                       idempotency_key="k1", public_time="2019-12-01T00:00:00Z",
                       public_time_basis="observed", **EVIDENCE)
        row = store.raw("SELECT public_time, public_time_basis, recorded_at FROM nodes")[0]
        self.assertEqual(row["public_time"], "2019-12-01T00:00:00Z")
        self.assertEqual(row["recorded_at"], stamp(0))  # store clock, not public_time
        # naive public metadata is rejected just like any naive timestamp
        with self.assertRaises(TKGValidationError):
            store.add_node("company", "B", {}, valid_from="2020-01-01",
                           **EVIDENCE, idempotency_key="k2", public_time="2019-12-01T10:00:00",
                           public_time_basis="observed")


class ExportTests(unittest.TestCase):
    def _store(self) -> TKGStore:
        store = TKGStore(":memory:", clock=step_clock())
        store.apply([
            node_spec("ACME", {"stage": "private"}, "r1"),
            node_spec("GLOBEX", {}, "g0"),  # stub entity exists before the edge
            {"record": "edge", "edge_type": "supplies", "src_type": "company",
             "src_id": "ACME", "dst_type": "company", "dst_id": "GLOBEX",
             "attrs": {}, "valid_from": "2020-01-01", "idempotency_key": "e1", **EVIDENCE},
        ])
        # GLOBEX's metadata lands AFTER the edge referencing it was recorded.
        store.apply([node_spec("GLOBEX", {"stage": "private"}, "g1")])
        store.apply([node_spec("ACME", {"stage": "ipo-filed", "extra": "future"}, "r2")])
        return store

    def test_snapshot_stability_after_later_writes(self) -> None:
        store = self._store()
        before = export_snapshot(store, known_at=stamp(1))
        before_hash = before["manifest"]["snapshot_sha256"]
        before_text = canonical_json(before)
        # Writes recorded after the cutoff must not change the export.
        store.apply([node_spec("ACME", {"stage": "changed-again"}, "r3")])
        after = export_snapshot(store, known_at=stamp(1))
        self.assertEqual(after["manifest"]["snapshot_sha256"], before_hash)
        self.assertEqual(canonical_json(after), before_text)

    def test_export_is_byte_deterministic_and_cutoff_sensitive(self) -> None:
        store = self._store()
        a = export_snapshot(store, known_at=stamp(1))
        b = export_snapshot(store, known_at=stamp(1))
        self.assertEqual(canonical_json(a), canonical_json(b))
        c = export_snapshot(store, known_at=stamp(2))
        self.assertNotEqual(c["manifest"]["snapshot_sha256"],
                            a["manifest"]["snapshot_sha256"])
        # No wall-clock generation time anywhere in the manifest.
        self.assertNotIn("generated_at", a["manifest"])

    def test_edge_export_does_not_leak_future_node_metadata(self) -> None:
        store = self._store()
        snap = export_snapshot(store, known_at=stamp(0, 12))
        # Between the stub (T0) and the metadata revision (T1) the endpoint
        # exists only as an empty stub; the edge must not fabricate or leak
        # node metadata for it.
        edge = snap["edges"][0]
        self.assertEqual(edge["dst"], {"node_type": "company", "node_id": "GLOBEX"})
        self.assertNotIn("attrs", edge["dst"])
        globex = [n for n in snap["nodes"] if n["node_id"] == "GLOBEX"][0]
        self.assertEqual(globex["attrs"], {})
        # ACME's later "future" attrs must not appear at this cutoff.
        acme = [n for n in snap["nodes"] if n["node_id"] == "ACME"][0]
        self.assertEqual(acme["attrs"], {"stage": "private"})

    def test_manifest_carries_cutoffs_versions_and_provenance(self) -> None:
        store = self._store()
        doc = export_snapshot(store, known_at=stamp(2), valid_at="2021-01-01",
                              adapter_version="events-adapter-1")
        manifest = doc["manifest"]
        self.assertEqual(manifest["known_at"], stamp(2))
        self.assertEqual(manifest["valid_at"], "2021-01-01T00:00:00Z")
        self.assertEqual(manifest["adapter_version"], "events-adapter-1")
        self.assertTrue(manifest["code_version"].startswith("medradar-"))
        self.assertTrue(manifest["schema_version"])
        self.assertEqual(manifest["counts"]["nodes"], 2)
        prov = manifest["evidence_provenance"]
        self.assertTrue(all(p["source_locator"] for p in prov))
        self.assertTrue(all(p["evidence_sha256"] for p in prov))
        # The embedded hash matches an independent canonical re-hash.
        stripped = {k: v for k, v in manifest.items() if k != "snapshot_sha256"}
        doc_wo = dict(doc, manifest=stripped)
        digest = hashlib.sha256(canonical_json(doc_wo).encode("utf-8")).hexdigest()
        self.assertEqual(manifest["snapshot_sha256"], digest)

    def test_write_export_json_and_jsonl(self) -> None:
        store = self._store()
        doc = export_snapshot(store, known_at=stamp(2))
        with tempfile.TemporaryDirectory() as tmp:
            files = write_export(doc, Path(tmp))
            self.assertIn("snapshot.json", files)
            again = json.loads(files["snapshot.json"].read_text(encoding="utf-8"))
            self.assertEqual(again["manifest"]["snapshot_sha256"],
                             doc["manifest"]["snapshot_sha256"])
            files = write_export(doc, Path(tmp) / "jsonl", jsonl=True)
            self.assertEqual(sorted(files), ["edges.jsonl", "manifest.json", "nodes.jsonl"])
            node_lines = files["nodes.jsonl"].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(node_lines), doc["manifest"]["counts"]["nodes"])
            for line in node_lines:  # each line is canonical JSON
                self.assertEqual(line, canonical_json(json.loads(line)))


class _source_db:
    """Synthetic temporary source events DB (never a production database)."""

    def __init__(self, tmp: str, rows: list[dict]) -> None:
        self.path = Path(tmp) / "source.sqlite"
        conn = sqlite3.connect(self.path)
        conn.execute(
            "CREATE TABLE events (event_id TEXT, source TEXT, kind TEXT, event_date TEXT,"
            " company_key TEXT, track_id TEXT, product_code TEXT, title TEXT, url TEXT,"
            " payload TEXT, fetched_at TEXT, published_at TEXT, first_seen_at TEXT,"
            " available_at TEXT, timestamp_quality TEXT)"
        )
        base = {"event_id": "evt-1", "source": "openfda", "kind": "510k",
                "event_date": "2024-02-01", "company_key": "acme", "track_id": "robotics",
                "product_code": "MJY", "title": "Clearance", "url": "https://example.test/1",
                "payload": "{}", "fetched_at": "2024-02-02", "published_at": "2024-02-01",
                "first_seen_at": "2024-02-02", "available_at": "2024-02-01",
                "timestamp_quality": "date"}
        for i, override in enumerate(rows):
            row = {**base, **override}
            if "event_id" not in override:
                row["event_id"] = f"evt-{i}"
            conn.execute(
                "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(row[k] for k in ("event_id", "source", "kind", "event_date",
                                       "company_key", "track_id", "product_code", "title",
                                       "url", "payload", "fetched_at", "published_at",
                                       "first_seen_at", "available_at", "timestamp_quality")),
            )
        conn.commit()
        conn.close()
        self.before_hash = hashlib.sha256(self.path.read_bytes()).hexdigest()


class AdapterTests(unittest.TestCase):
    def test_import_uses_observation_time_and_keeps_source_readonly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _source_db(tmp, [{}])
            store = TKGStore(":memory:", clock=make_clock(dt(10)))
            report = import_events(src.path, store)
            self.assertEqual(report["source_mode"], "ro")
            self.assertEqual(report["counters"]["rows_seen"], 1)
            self.assertGreater(report["counters"]["assertions_created"], 0)
            # recorded_at = actual import observation time, NOT first_seen_at
            # and NOT event_date / available_at.
            node = [r for r in store.raw("SELECT * FROM nodes") if r["node_type"] == "event"][0]
            self.assertEqual(node["recorded_at"], stamp(10))
            self.assertNotEqual(node["recorded_at"], "2024-02-02T00:00:00Z")
            self.assertEqual(node["public_time"], "2024-02-01T00:00:00Z")
            self.assertEqual(node["public_time_basis"], "inferred")
            provenance = json.loads(node["attrs"])
            self.assertEqual(provenance["first_seen_at"], "2024-02-02")
            # Source database untouched, byte for byte.
            self.assertEqual(hashlib.sha256(src.path.read_bytes()).hexdigest(),
                             src.before_hash)

    def test_source_is_opened_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _source_db(tmp, [{}])
            conn = open_source(src.path)
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("CREATE TABLE should_fail (x INTEGER)")
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("DELETE FROM events")
            conn.close()

    def test_missing_and_invalid_provenance_counted_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _source_db(tmp, [
                {"event_id": None},
                {"event_date": None},
                {"available_at": "not-a-date"},
                {},  # healthy row
            ])
            store = TKGStore(":memory:", clock=make_clock(dt(0)))
            report = import_events(src.path, store)
            counters = report["counters"]
            self.assertEqual(counters["rows_seen"], 4)
            self.assertEqual(counters["skipped_missing_event_id"], 1)
            self.assertEqual(counters["skipped_missing_event_date"], 1)
            self.assertEqual(counters["invalid_public_time_dropped"], 1)
            reasons = {e["reason"] for e in report["errors"]}
            self.assertEqual(reasons,
                             {"missing_event_id", "missing_event_date", "invalid_available_at"})
            # Two rows import (invalid available_at only drops the public
            # metadata, not the row): 7 assertions each, but the healthy row's
            # three entity stubs are idempotent duplicates of the first row's.
            self.assertEqual(counters["assertions_created"], 11)
            self.assertEqual(counters["idempotent_duplicates"], 3)

    def test_reimport_is_idempotent_no_new_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _source_db(tmp, [{}])
            store = TKGStore(":memory:", clock=make_clock(dt(0), dt(1)))
            first = import_events(src.path, store)
            nodes_after_first = store.count("nodes")
            second = import_events(src.path, store)
            self.assertEqual(store.count("nodes"), nodes_after_first)
            self.assertGreater(second["counters"]["idempotent_duplicates"], 0)
            self.assertEqual(second["counters"]["assertions_created"], 0)
            self.assertEqual(first["counters"]["assertions_created"], 7)  # 1 event + 3 stubs + 3 edges
            self.assertEqual(nodes_after_first, 4)

    def test_source_correction_becomes_new_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _source_db(tmp, [{"title": "Original title"}])
            store = TKGStore(":memory:", clock=make_clock(dt(0), dt(1)))
            import_events(src.path, store)
            conn = sqlite3.connect(src.path)  # test-side fixture mutation only
            conn.execute("UPDATE events SET title = 'Corrected title' WHERE event_id = 'evt-0'")
            conn.commit()
            conn.close()
            import_events(src.path, store)
            event_node = [r for r in store.raw(
                "SELECT * FROM nodes WHERE node_type = 'event'")]
            self.assertEqual(len(event_node), 2)  # two revisions of one assertion
            titles = {json.loads(r["attrs"])["title"] for r in event_node}
            self.assertEqual(titles, {"Original title", "Corrected title"})
            # The old revision remains addressable at the earlier cutoff.
            old = TKGQuery(store).latest_node_revisions(known_at=stamp(0))
            old_event = [n for n in old if n["node_type"] == "event"][0]
            self.assertEqual(old_event["attrs"]["title"], "Original title")


class CliTests(unittest.TestCase):
    def test_demo_cli_end_to_end_offline(self) -> None:
        from medradar.tkg.__main__ import main

        with tempfile.TemporaryDirectory() as tmp:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["demo", "--out-dir", str(Path(tmp) / "demo")])
            self.assertEqual(code, 0)
            early = Path(tmp) / "demo" / "early" / "snapshot.json"
            final = Path(tmp) / "demo" / "final" / "snapshot.json"
            early_doc = json.loads(early.read_text(encoding="utf-8"))
            final_doc = json.loads(final.read_text(encoding="utf-8"))
            self.assertNotEqual(early_doc["manifest"]["snapshot_sha256"],
                                final_doc["manifest"]["snapshot_sha256"])
            # Retraction visible: GLOBEX absent from the final validity window.
            final_ids = {n["node_id"] for n in final_doc["nodes"]}
            self.assertIn("ACME", final_ids)
            self.assertIn("SPINE-X", final_ids)
            self.assertNotIn("GLOBEX", final_ids)

    def test_import_export_cli_roundtrip(self) -> None:
        from medradar.tkg.__main__ import main

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = _source_db(tmp, [{}])
            tkg_db = tmp_path / "tkg.sqlite"
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(main(["import", "--db", str(src.path), "--tkg", str(tkg_db)]), 0)
            out_dir = tmp_path / "export"
            with redirect_stdout(buf):
                self.assertEqual(main([
                    "export", "--tkg", str(tkg_db),
                    "--known-at", "2999-01-01T00:00:00Z",
                    "--out-dir", str(out_dir),
                ]), 0)
            doc = json.loads((out_dir / "snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["manifest"]["counts"]["nodes"], 4)


if __name__ == "__main__":
    unittest.main()
