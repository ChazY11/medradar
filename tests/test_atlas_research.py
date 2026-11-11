"""ATLAS research-layer tests: as-of labels, unprovable time, prospective registry."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from medradar.atlas.evidence import schema as ev
from medradar.atlas.evidence.timeq import build_time
from medradar.atlas.research import as_of, candidate_summary, evidence_history, register_cross_market_candidates
from medradar.atlas.store import AtlasStore


def record(
    *, record_id: str, public: str, quality: str, fetched: str = "2026-11-10T00:00:00Z",
    brand: str = ""
) -> dict:
    return ev.make_evidence(
        source_id="openfda_device_udi",
        source_record_id=record_id,
        evidence_type="device_registration",
        source_url=f"https://example.test/{record_id}",
        raw_content_hash=ev.sha256_text(record_id),
        raw_bytes=4,
        normalized={"brand_name": brand or record_id},
        time=build_time(
            event_at=None, source_public_at=public, fetched_at=fetched, quality=quality
        ),
        identifiers=[{"scheme": "di", "value": f"0000000000000{record_id[-1]}", "is_primary": True}],
        entity_refs=[
            {
                "entity_type": "company", "name_raw": "MEDTRONIC",
                "firm_key": "medtronic", "method": "exact_alias", "confidence": 0.95,
                "matched_alias": "MEDTRONIC",
            }
        ],
        licence_status="public_domain",
        identity_resolution_status="confirmed",
    )


class AsOfTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AtlasStore(Path(self.tmp.name) / "atlas.sqlite")
        self.store.append_evidence(record(record_id="r1", public="2020-01-01", quality="day"))
        self.store.append_evidence(record(record_id="r2", public="", quality="unknown"))
        self.store.append_evidence(record(record_id="r3", public="2019-06-01", quality="derived"))

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_before_capture_boundary_returns_capture_boundary(self) -> None:
        payload = as_of(self.store, "2021-01-01T00:00:00Z", basis="observed")
        self.assertEqual(payload["counts"]["observed"], 0)
        self.assertTrue(any("capture boundary" in c for c in payload["caveats"]))

    def test_observed_after_fetch_sees_records(self) -> None:
        payload = as_of(self.store, "2026-11-10T00:00:00Z", basis="observed")
        self.assertEqual(payload["counts"]["observed"], 3)

    def test_public_inferred_is_separate_and_excludes_derived(self) -> None:
        payload = as_of(self.store, "2020-06-01T00:00:00Z", basis="public_inferred")
        self.assertEqual(payload["counts"]["public_inferred"], 1)
        self.assertGreaterEqual(payload["counts"]["unprovable"], 2)

    def test_unknown_public_date_is_never_promoted(self) -> None:
        payload = as_of(self.store, "2026-11-10T00:00:00Z", basis="public_inferred")
        sample_ids = {row["evidence_id"] for row in payload["sample"]}
        unknown = ev.make_evidence_id("openfda_device_udi", "r2", "device_registration")
        self.assertNotIn(unknown, sample_ids)


class HistoryTests(unittest.TestCase):
    def test_versions_are_listed_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AtlasStore(Path(tmp) / "a.sqlite")
            first = record(record_id="r9", public="2020-01-01", quality="day")
            store.append_evidence(first)
            changed = record(record_id="r9", public="2020-01-01", quality="day", brand="CHANGED")
            store.append_evidence(changed)
            history = evidence_history(store, first["evidence_id"])
            self.assertEqual(history["versions"], 2)
            self.assertEqual([v["version"] for v in history["timeline"]], [1, 2])
            store.close()


class ProspectiveTests(unittest.TestCase):
    def test_candidates_registered_once_and_versioned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AtlasStore(Path(tmp) / "a.sqlite")
            store.append_evidence(record(record_id="r5", public="2020-01-01", quality="day"))
            first = register_cross_market_candidates(store)
            self.assertEqual(first["registered"], 1)
            second = register_cross_market_candidates(store)
            summary = candidate_summary(store)
            self.assertEqual(summary["count"], 1)
            self.assertEqual(second["registered"], 1)
            self.assertEqual(summary["candidates"][0]["version"], 2)
            store.close()


if __name__ == "__main__":
    unittest.main()
