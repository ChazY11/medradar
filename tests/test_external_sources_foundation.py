"""Offline tests for the external-source integration layer (DATA-EXPANSION-001).

No network, no keys, no fixtures from disk other than the shipped company
registry.  These tests are picked up by ``python -m medradar selftest``.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from medradar.external_sources import base, identity, schema, store, timeq

FIXED = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)


def _record(**overrides):
    payload = {
        "source_id": "test_source",
        "kind": "device_registration",
        "source_record_id": "REC-1",
        "source_url": "https://example.test/rec/1",
        "normalized": {"brand": "INVOS", "model": "X1"},
        "raw": {"content_hash": "a" * 64, "bytes": 128, "path": "samples/test/REC-1.json"},
        "time": timeq.build_time(
            event_at="2024-01-15",
            source_public_at="2024-02-01",
            fetched_at=FIXED,
        ),
        "identifiers": [
            identity.build_identifier("di", "0081 2345 6789 01", is_primary=True),
            identity.build_identifier("510k", "k123456"),
        ],
        "entity_refs": [
            {
                "entity_type": "company",
                "name_raw": "Medtronic MiniMed",
                "resolved_key": "medtronic",
                "method": "exact_alias",
                "confidence": 0.95,
                "evidence": {"matched_alias": "MEDTRONIC MINIMED"},
                "note": "",
            }
        ],
        "provenance": {"source_name": "Test Source", "licence_status": "public_domain"},
        "fetched_at": timeq.iso(FIXED),
    }
    payload.update(overrides)
    return schema.make_evidence(**payload)


class SchemaTests(unittest.TestCase):
    def test_valid_record_passes(self):
        record = _record()
        self.assertEqual(schema.validate_evidence(record), [])
        self.assertEqual(record["schema"], schema.SCHEMA_ID)
        self.assertEqual(record["canonical_key"], "di:00812345678901")

    def test_evidence_id_is_stable_and_content_independent(self):
        first = _record(normalized={"brand": "A"})
        second = _record(normalized={"brand": "B"})
        self.assertEqual(first["evidence_id"], second["evidence_id"])
        self.assertNotEqual(first["content_hash"], second["content_hash"])

    def test_missing_clock_is_rejected(self):
        record = _record()
        del record["time"]["source_public_at"]
        problems = schema.validate_evidence(record)
        self.assertTrue(any("source_public_at" in p for p in problems))

    def test_unknown_time_quality_is_rejected(self):
        record = _record()
        record["time"]["source_public_at_quality"] = "probably"
        self.assertTrue(schema.validate_evidence(record))

    def test_bad_raw_hash_is_rejected(self):
        bad = _record()
        bad["raw"]["content_hash"] = "not-a-hash"
        self.assertTrue(any("sha256" in p for p in schema.validate_evidence(bad)))

    def test_candidate_link_cannot_look_confirmed(self):
        record = _record()
        record["entity_refs"][0]["method"] = "candidate"
        record["entity_refs"][0]["confidence"] = 0.99
        self.assertTrue(schema.validate_evidence(record))

    def test_confirmed_link_requires_evidence(self):
        record = _record()
        record["entity_refs"][0]["evidence"] = {}
        self.assertTrue(schema.validate_evidence(record))

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(schema.EvidenceError):
            _record(kind="rumour")

    def test_canonical_key_prefers_official_identifier(self):
        ids = [
            identity.build_identifier("patent_no", "US 10,123,456 B2"),
            identity.build_identifier("doi", "10.1000/ABC"),
        ]
        self.assertEqual(schema.canonical_key([i for i in ids if i]), "doi:10.1000/abc")

    def test_canonical_key_none_without_authoritative_id(self):
        self.assertIsNone(schema.canonical_key([]))
        self.assertIsNone(
            schema.canonical_key([{"scheme": "name", "value": "Medtronic"}])
        )

    def test_aggregator_duplicate_is_not_independent(self):
        a = _record()
        b = _record(source_id="other_aggregator", source_record_id="X-9")
        self.assertFalse(schema.is_independent(a, b))
        c = _record(
            source_id="archive",
            source_record_id="Y-1",
            identifiers=[identity.build_identifier("di", "99999999999999")],
        )
        self.assertTrue(schema.is_independent(a, c))


class TimeTests(unittest.TestCase):
    def test_four_clocks_present(self):
        block = timeq.build_time(
            event_at="2024-01-15", source_public_at="2024-02-01", fetched_at=FIXED
        )
        for clock in ("event_at", "source_public_at", "first_observed_at", "fetched_at"):
            self.assertTrue(block[clock])
        self.assertEqual(block["first_observed_at"], block["fetched_at"])
        self.assertEqual(block["source_public_at_quality"], "day")

    def test_first_observed_is_not_backdated_to_publication(self):
        block = timeq.build_time(source_public_at="2016-01-01", fetched_at=FIXED)
        self.assertEqual(block["first_observed_at"], timeq.iso(FIXED))
        self.assertNotEqual(block["first_observed_at"], block["source_public_at"])

    def test_quality_inference_does_not_inflate(self):
        self.assertEqual(timeq.implied_quality("2024-06"), "coarse")
        self.assertEqual(timeq.implied_quality("2024"), "coarse")
        self.assertEqual(timeq.implied_quality("2024-06-01"), "day")
        self.assertEqual(timeq.implied_quality("2024-06-01T10:00:00Z"), "exact")
        self.assertEqual(timeq.implied_quality(""), "unknown")

    def test_lead_time_and_buckets(self):
        self.assertEqual(timeq.lead_time_days("2024-01-01", "2024-04-01"), 91)
        self.assertEqual(timeq.bucket_lead_time(91), "91-180d")
        self.assertEqual(timeq.bucket_lead_time(-3), "after_event")
        self.assertEqual(timeq.bucket_lead_time(None), "undatable")

    def test_coarse_dates_cannot_support_lead_time_claim(self):
        self.assertFalse(timeq.quality_allows_lead_time("coarse"))
        self.assertFalse(timeq.quality_allows_lead_time("derived"))
        self.assertTrue(timeq.quality_allows_lead_time("day"))

    def test_ordering_problems_detected(self):
        block = timeq.build_time(source_public_at="2030-01-01", fetched_at=FIXED)
        self.assertTrue(timeq.check_ordering(block))


class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = identity.CompanyIndex.from_config()

    def test_exact_alias_resolves_confirmed(self):
        for raw, key in [
            ("MEDTRONIC MINIMED", "medtronic"),
            ("Covidien LP", "medtronic"),
            ("GE Medical Systems Ultrasound & Primary Care Diagnostics", "ge_healthcare"),
            ("Koninklijke Philips N.V.", "philips"),
            ("Draeger Medical Systems, Inc.", "draeger"),
            ("Shenzhen Mindray Bio-Medical Electronics Co., Ltd.", "mindray"),
        ]:
            result = self.index.resolve(raw)
            self.assertEqual(result["resolved_key"], key, raw)
            self.assertIn(result["method"], {"exact_alias", "multi_field"}, raw)

    def test_negative_guard_demotes_to_candidate(self):
        result = self.index.resolve("Philips Lighting B.V.")
        self.assertEqual(result["method"], "candidate")
        self.assertLess(result["confidence"], 0.9)
        self.assertIn("negative_guard", result["evidence"])

    def test_unrelated_company_is_not_linked(self):
        for raw in ("Stryker Corporation", "Becton Dickinson", "Siemens Healthineers"):
            result = self.index.resolve(raw)
            self.assertNotIn(result["resolved_key"], identity.TARGET_FIRM_KEYS, raw)

    def test_single_token_never_becomes_candidate(self):
        result = self.index.resolve("PHILIPS")
        self.assertIn(result["method"], {"exact_alias", "multi_field"})
        other = self.index.resolve("RANDOM MEDICAL HOLDINGS")
        self.assertEqual(other["method"], "none")

    def test_multi_field_promotion(self):
        base_result = self.index.resolve("Philips Medical Systems")
        promoted = identity.multi_field_link(base_result, agreeing_fields=["country=NL"])
        self.assertEqual(promoted["method"], "multi_field")
        self.assertIn("agreeing_fields", promoted["evidence"])

    def test_product_identifiers_normalised(self):
        self.assertEqual(identity.normalize_di("0081 2345 6789 01"), "00812345678901")
        self.assertEqual(identity.normalize_regulatory_number("k123456"), "K123456")
        self.assertEqual(identity.normalize_doi("https://doi.org/10.1000/ABC"), "10.1000/abc")
        self.assertEqual(identity.normalize_patent_number("US 10,123,456 B2"), "US10123456")


class StoreTests(unittest.TestCase):
    def test_upsert_is_idempotent_and_versions_content_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with store.StagingStore(Path(tmp) / "staging.sqlite") as db:
                first = _record()
                inserted = db.upsert_evidence(first)
                self.assertTrue(inserted["inserted"])
                again = db.upsert_evidence(first)
                self.assertFalse(again["inserted"])
                changed = _record(normalized={"brand": "INVOS", "model": "X2"})
                third = db.upsert_evidence(changed)
                self.assertTrue(third["inserted"])
                head = db.query("SELECT * FROM evidence_head")[0]
                self.assertEqual(head["versions"], 2)
                self.assertEqual(db.table_count("evidence"), 2)
                self.assertEqual(head["first_observed_at"], first["time"]["first_observed_at"])

    def test_invalid_record_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            with store.StagingStore(Path(tmp) / "staging.sqlite") as db:
                broken = _record()
                broken["time"]["source_public_at_quality"] = "guess"
                with self.assertRaises(schema.EvidenceError):
                    db.upsert_evidence(broken)
                self.assertEqual(db.table_count("evidence"), 0)

    def test_stats_separates_confirmed_from_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            with store.StagingStore(Path(tmp) / "staging.sqlite") as db:
                db.upsert_evidence(_record())
                candidate = _record(source_record_id="REC-2")
                candidate["entity_refs"][0]["method"] = "candidate"
                candidate["entity_refs"][0]["confidence"] = 0.5
                db.upsert_evidence(candidate)
                stats = db.stats()
                self.assertEqual(stats["confirmed_entity_links"], 1)
                self.assertEqual(stats["candidate_entity_links"], 1)


class RegistryTests(unittest.TestCase):
    def _write(self, root: Path, source_id: str, **overrides):
        record = blueprint = {
            "source_id": source_id,
            "source_name": source_id.upper(),
            "official_url": "https://example.test",
            "country_or_region": "GLOBAL",
            "category": "regulatory",
            "official_or_commercial": "official",
            "api_available": "YES",
            "bulk_download_available": "UNKNOWN",
            "authentication": "none",
            "free_tier": "yes",
            "rate_limits": "UNKNOWN",
            "licence": "public domain",
            "redistribution_allowed": "YES",
            "update_frequency": "daily",
            "historical_coverage": "2013-",
            "entity_identifiers": [],
            "timestamp_fields": ["publication_date"],
            "known_limitations": [],
            "connection_status": "NOT_TESTED",
            "research_value": "high",
            "evidence_urls": ["https://example.test/docs"],
            "verified_at": "2026-11-09",
            "domain": "A",
        }
        record.update(overrides)
        (root / "registry" / "sources").mkdir(parents=True, exist_ok=True)
        (root / "registry" / "sources" / f"{source_id}.json").write_text(
            json.dumps(record), encoding="utf-8"
        )

    def test_documentation_alone_never_yields_verified_status(self):
        from medradar.external_sources import registry as reg

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "demo_source")
            merged = reg.build_register(root)
            self.assertEqual(merged["sources"][0]["connection_status"], "NOT_TESTED")
            self.assertEqual(merged["sources"][0]["verified_by"], "documentation_only")

    def test_probe_overrides_status_and_keeps_documentation_claim(self):
        from medradar.external_sources import registry as reg

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "demo_source")
            probe_dir = root / "probes" / "demo_source"
            probe_dir.mkdir(parents=True)
            (probe_dir / "PROBE_RESULT.json").write_text(
                json.dumps(
                    {
                        "source_id": "demo_source",
                        "status": "VERIFIED_API",
                        "verified_at": "2026-11-09T00:00:00Z",
                        "requests": 3,
                        "evidence_urls": ["https://example.test/api?limit=1"],
                        "notes": "ok",
                        "error": "",
                        "probes": [{"name": "basic"}],
                    }
                ),
                encoding="utf-8",
            )
            merged = reg.build_register(root)
            record = merged["sources"][0]
            self.assertEqual(record["connection_status"], "VERIFIED_API")
            self.assertEqual(record["verified_by"], "live_probe")
            self.assertEqual(record["documentation_claim"]["api_available"], "YES")
            self.assertIn("https://example.test/api?limit=1", record["evidence_urls"])
            self.assertEqual(merged["validation_problems"], [])

    def test_negative_probe_is_recorded_honestly(self):
        from medradar.external_sources import registry as reg

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "gated_source")
            probe_dir = root / "probes" / "gated_source"
            probe_dir.mkdir(parents=True)
            (probe_dir / "PROBE_RESULT.json").write_text(
                json.dumps(
                    {
                        "source_id": "gated_source",
                        "status": "REQUIRES_REGISTRATION",
                        "verified_at": "2026-11-09T00:00:00Z",
                        "requests": 1,
                        "evidence_urls": ["https://example.test/api"],
                        "notes": "401 without key",
                        "error": "",
                        "probes": [],
                    }
                ),
                encoding="utf-8",
            )
            record = reg.build_register(root)["sources"][0]
            self.assertEqual(record["connection_status"], "REQUIRES_REGISTRATION")
            self.assertEqual(record["verified_by"], "live_probe_negative")

    def test_invalid_status_is_a_validation_problem(self):
        from medradar.external_sources import registry as reg

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "bad_source", connection_status="PROBABLY_FINE")
            merged = reg.build_register(root)
            self.assertTrue(merged["validation_problems"])


class BaseTests(unittest.TestCase):
    def test_write_sample_reports_truncation_truthfully(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = b"x" * 100
            kept = base.write_sample(Path(tmp), "full.bin", body, max_inline_bytes=200)
            self.assertFalse(kept["truncated"])
            self.assertEqual(kept["sha256_full"], kept["sha256_stored"])
            clipped = base.write_sample(Path(tmp), "part.bin", body, max_inline_bytes=10)
            self.assertTrue(clipped["truncated"])
            self.assertEqual(clipped["stored_bytes"], 10)
            self.assertEqual(clipped["total_bytes"], 100)
            self.assertNotEqual(clipped["sha256_full"], clipped["sha256_stored"])

    def test_ledger_appends_every_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = base.HttpLedger(Path(tmp) / "requests.jsonl")
            ledger.append({"url": "https://example.test", "status": 200})
            ledger.append({"url": "https://example.test", "status": 503, "error": "HTTP 503"})
            self.assertEqual(ledger.count(), 2)
            lines = (Path(tmp) / "requests.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[1])["status"], 503)

    def test_offline_client_never_opens_a_socket(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = base.HttpLedger(Path(tmp) / "requests.jsonl")
            client = base.HttpClient("x", ledger, allow_network=False, budget=1)
            result = client.get("https://example.test/api")
            self.assertFalse(result.ok)
            self.assertIn("network disabled", result.error)
            self.assertEqual(ledger.count(), 1)

    def test_budget_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = base.HttpLedger(Path(tmp) / "requests.jsonl")
            client = base.HttpClient("x", ledger, allow_network=False, budget=0)
            with self.assertRaises(base.BudgetExceeded):
                client.get("https://example.test/api")

    def test_run_probe_persists_result_even_on_failure(self):
        def boom(client, directory):
            raise RuntimeError("probe bug")

        with tempfile.TemporaryDirectory() as tmp:
            outcome = base.run_probe("broken", Path(tmp), boom, budget=1, allow_network=False)
            self.assertEqual(outcome.status, "UNAVAILABLE")
            written = json.loads((Path(tmp) / "probes" / "broken" / "PROBE_RESULT.json").read_text())
            self.assertEqual(written["status"], "UNAVAILABLE")
            self.assertIn("probe bug", written["error"])

    def test_json_shape_does_not_copy_values(self):
        shape = base.json_shape({"token": "SECRET-VALUE", "n": 3})
        self.assertNotIn("SECRET-VALUE", json.dumps(shape))


if __name__ == "__main__":
    unittest.main()
