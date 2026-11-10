"""ATLAS database tests: migrations, backups, version history, graph revocation."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from medradar.atlas.db.migrations import (
    MIGRATIONS,
    Migration,
    MigrationError,
    backup_database,
    current_version,
    migrate,
    split_statements,
)
from medradar.atlas.evidence import schema as ev
from medradar.atlas.evidence.timeq import build_time
from medradar.atlas.graph import build_source_declared_relations, company_devices
from medradar.atlas.identity.resolver import (
    CONFIRMED,
    SAME_DEVICE_IDENTITY,
    MatchDecision,
)
from medradar.atlas.store import AtlasStore


def evidence_record() -> dict:
    return ev.make_evidence(
        source_id="openfda_device_udi",
        source_record_id="rec-graph-1",
        evidence_type="device_registration",
        source_url="https://example.test/1",
        raw_content_hash=ev.sha256_text("raw-1"),
        raw_bytes=5,
        normalized={"brand_name": "XIENCE", "company_name": "MEDTRONIC, INC."},
        time=build_time(
            event_at=None, source_public_at="2015-05-08",
            fetched_at="2026-11-10T00:00:00Z", quality="day",
        ),
        identifiers=[
            {"scheme": "di", "value": "08717648200274", "is_primary": True},
            {"scheme": "510k", "value": "K123456", "is_primary": False},
        ],
        entity_refs=[
            {
                "entity_type": "company", "name_raw": "MEDTRONIC, INC.",
                "firm_key": "medtronic", "method": "exact_alias", "confidence": 0.95,
                "matched_alias": "MEDTRONIC",
            }
        ],
        licence_status="public_domain",
        identity_resolution_status="confirmed",
    )


class MigrationTests(unittest.TestCase):
    def test_fresh_database_reaches_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.sqlite"
            report = migrate(path)
            self.assertEqual(report["applied"], [1])
            self.assertEqual(current_version(path), 1)
            conn = sqlite3.connect(path)
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            conn.close()
            for table in ("evidence", "evidence_head", "entity_relations", "prospective_candidates"):
                self.assertIn(table, tables)

    def test_modified_migration_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.sqlite"
            migrate(path, migrations=(MIGRATIONS[0],))
            tampered = Migration(version=1, name=MIGRATIONS[0].name, sql=MIGRATIONS[0].sql + "\n-- changed")
            with self.assertRaises(MigrationError):
                migrate(path, migrations=(tampered,))

    def test_backup_written_before_pending_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.sqlite"
            migrate(path)
            v2 = Migration(version=2, name="extra", sql="CREATE TABLE extra_table (id INTEGER);")
            report = migrate(path, migrations=(*MIGRATIONS, v2))
            self.assertTrue(report["backup"])
            self.assertEqual(report["applied"], [2])
            self.assertTrue(Path(report["backup"]).exists())

    def test_split_statements_ignores_empty_chunks(self) -> None:
        self.assertEqual(len(split_statements("CREATE TABLE a (x); CREATE TABLE b (y);")), 2)


class GraphHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AtlasStore(Path(self.tmp.name) / "atlas.sqlite")
        self.record = evidence_record()
        self.store.append_evidence(self.record)
        self.store.upsert_company(
            company_id=ev.deterministic_id("co", "firm", "medtronic"),
            canonical_name="Medtronic plc",
            country="IE",
            aliases=["MEDTRONIC", "MEDTRONIC, INC."],
        )
        self.store.upsert_device(
            device_id="dev_test",
            canonical_name="XIENCE",
            brand_name="XIENCE",
            model_number="M1",
            company_id=ev.deterministic_id("co", "firm", "medtronic"),
            product_codes=["NIQ"],
            identifiers=[{"scheme": "di", "value": "08717648200274", "is_primary": True}],
            evidence_id=self.record["evidence_id"],
        )

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_source_declared_relations_are_created(self) -> None:
        counts = build_source_declared_relations(self.store)
        self.assertGreaterEqual(counts.get("MANUFACTURED_BY", 0), 1)
        self.assertGreaterEqual(counts.get("REGISTERED_AS", 0), 1)

    def test_company_query_returns_evidence_backed_device(self) -> None:
        payload = company_devices(self.store, "medtronic")
        self.assertEqual(payload["count"], 1)
        device = payload["devices"][0]
        self.assertTrue(device["identifiers"])
        self.assertEqual(device["evidence"]["evidence_id"], self.record["evidence_id"])

    def test_revoked_relation_keeps_history(self) -> None:
        decision = MatchDecision(
            left_ref="dev_a", right_ref="dev_b",
            relation_type=SAME_DEVICE_IDENTITY, status=CONFIRMED,
            method="official_identifier", authority="source_declared", confidence=0.99,
        )
        relation_id = self.store.add_relation(decision, evidence_ids=[self.record["evidence_id"]])
        self.assertTrue(self.store.revoke_relation(relation_id, reason="contradicted by recall record"))
        self.assertFalse(self.store.revoke_relation("missing", reason="no-op"))
        rows = self.store.query("SELECT revoked_at, revoked_reason FROM entity_relations WHERE relation_id=?", (relation_id,))
        self.assertTrue(rows[0]["revoked_at"])
        self.assertIn("contradicted", rows[0]["revoked_reason"])
        events = self.store.query(
            "SELECT action FROM relation_events WHERE relation_id=? ORDER BY event_id", (relation_id,)
        )
        self.assertEqual([e["action"] for e in events], ["created", "revoked"])
        # revoked relations disappear from the default listing but remain in the table
        self.assertEqual(self.store.list_relations(), [])
        self.assertEqual(len(self.store.list_relations(include_revoked=True)), 1)


if __name__ == "__main__":
    unittest.main()
