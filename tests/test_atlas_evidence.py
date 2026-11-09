"""ATLAS evidence-contract tests: four clocks, immutability, dedupe semantics."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from medradar.atlas.evidence import schema as ev
from medradar.atlas.evidence.timeq import build_time, iso, parse_date
from medradar.atlas.store import AtlasStore


def record(
    *,
    source_id: str = "openfda_device_udi",
    source_record_id: str = "rec-1",
    normalized: dict | None = None,
    public: str = "2020-01-02",
    quality: str = "day",
    identifier: tuple[str, str] = ("di", "08717648200274"),
    fetched: str = "2026-11-10T00:00:00Z",
) -> dict:
    time_block = build_time(
        event_at=None, source_public_at=public, fetched_at=fetched, quality=quality
    )
    return ev.make_evidence(
        source_id=source_id,
        source_record_id=source_record_id,
        evidence_type="device_registration",
        source_url="https://example.test/record",
        raw_content_hash=ev.sha256_json({"id": source_record_id}),
        raw_bytes=2,
        normalized=normalized or {"brand_name": "XIENCE", "company_name": "ABBOTT"},
        time=time_block,
        identifiers=[{"scheme": identifier[0], "value": identifier[1], "is_primary": True}],
        entity_refs=[
            {
                "entity_type": "company",
                "name_raw": "ABBOTT",
                "firm_key": "medtronic",
                "method": "exact_alias",
                "confidence": 0.95,
                "matched_alias": "MEDTRONIC",
            }
        ],
        licence_status="public_domain",
        identity_resolution_status="confirmed",
    )


class ContractTests(unittest.TestCase):
    def test_valid_record_passes(self) -> None:
        self.assertEqual(ev.validate_evidence(record()), [])

    def test_missing_public_clock_is_explicit_not_invented(self) -> None:
        rec = record(public="", quality="unknown")
        self.assertEqual(rec["time"]["source_public_at"], "")
        self.assertEqual(rec["time"]["source_public_at_quality"], "unknown")
        self.assertNotEqual(rec["time"]["first_observed_at"], "")

    def test_quality_derived_is_preserved(self) -> None:
        rec = record(public="2019-05-01", quality="derived")
        self.assertEqual(rec["time"]["source_public_at_quality"], "derived")

    def test_candidate_cannot_carry_confirmed_confidence(self) -> None:
        rec = record()
        rec["entity_refs"][0].update({"method": "candidate", "confidence": 0.99})
        problems = ev.validate_evidence(rec)
        self.assertTrue(any("candidate links" in p for p in problems))

    def test_confirmed_link_requires_basis(self) -> None:
        rec = record()
        rec["entity_refs"][0].pop("matched_alias")
        rec["entity_refs"][0].pop("firm_key")
        problems = ev.validate_evidence(rec)
        self.assertTrue(any("must record its basis" in p for p in problems))

    def test_unknown_quality_flag_rejected(self) -> None:
        rec = record()
        rec["quality_flags"] = ["made_up_flag"]
        self.assertTrue(any("unknown quality flags" in p for p in ev.validate_evidence(rec)))

    def test_canonical_key_prefers_di(self) -> None:
        key = ev.canonical_key(
            [
                {"scheme": "510k", "value": "K123456"},
                {"scheme": "di", "value": "08717648200274"},
            ]
        )
        self.assertEqual(key, "di:08717648200274")

    def test_records_sharing_canonical_key_are_not_independent(self) -> None:
        a = record(source_id="openfda_device_udi")
        b = record(source_id="accessgudid")
        self.assertFalse(ev.is_independent(a, b))


class ClockTests(unittest.TestCase):
    def test_iso_accepts_date(self) -> None:
        self.assertEqual(iso(parse_date("2024-06-01")), "2024-06-01")

    def test_first_observed_is_fetch_not_public(self) -> None:
        block = build_time(
            event_at="2010-01-01", source_public_at="2010-01-01",
            fetched_at="2026-11-10T00:00:00Z", quality="derived",
        )
        self.assertEqual(block["first_observed_at"], "2026-11-10T00:00:00Z")
        self.assertNotEqual(block["first_observed_at"], block["source_public_at"])


class StoreImmutabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AtlasStore(Path(self.tmp.name) / "atlas.sqlite")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_append_is_idempotent(self) -> None:
        first = self.store.append_evidence(record())
        second = self.store.append_evidence(record())
        self.assertTrue(first["inserted"])
        self.assertFalse(second["inserted"])
        self.assertEqual(self.store.stats()["evidence_versions"], 1)

    def test_changed_content_creates_new_version(self) -> None:
        self.store.append_evidence(record())
        changed = record(normalized={"brand_name": "XIENCE ALPINE", "company_name": "ABBOTT"})
        result = self.store.append_evidence(changed)
        self.assertTrue(result["inserted"])
        self.assertEqual(result["version"], 2)
        self.assertEqual(self.store.stats()["evidence_versions"], 2)
        # older version still retrievable unchanged
        old = self.store.get_evidence(record()["evidence_id"], 1)
        self.assertEqual(old["normalized"]["brand_name"], "XIENCE")

    def test_first_observed_is_preserved_across_refetch(self) -> None:
        self.store.append_evidence(record(fetched="2026-11-10T00:00:00Z"))
        self.store.append_evidence(
            record(normalized={"brand_name": "X2"}, fetched="2027-01-01T00:00:00Z")
        )
        head = self.store.query("SELECT first_observed_at FROM evidence_head")[0]
        self.assertEqual(head["first_observed_at"], "2026-11-10T00:00:00Z")

    def test_invalid_record_is_refused(self) -> None:
        bad = record()
        bad["time"].pop("fetched_at")
        with self.assertRaises(ev.EvidenceError):
            self.store.append_evidence(bad)


if __name__ == "__main__":
    unittest.main()
