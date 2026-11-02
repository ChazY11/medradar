"""Offline tests for the Horizon -> canonical-registry adapter (Phase 3)."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from medradar.db import DB
from medradar.forecast_registry import (
    ForecastRegistry,
    IdempotencyConflict,
    canonical_json,
    sha256_hex,
)
from medradar.intelligence.forecasting.registry_adapter import (
    FEATURE_VERSION,
    register_horizon_forecasts,
    to_registry_spec,
    verify_registered_forecasts,
)
from medradar.intelligence.storage import IntelligenceStore

T0 = datetime(2026, 11, 2, tzinfo=timezone.utc)
COVERAGE_END = "2026-10-15"


class MutableClock:
    """Registry clock a test can move forward explicitly."""

    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def set(self, moment: datetime) -> None:
        self.moment = moment


def horizon_record(**overrides) -> dict:
    record = {
        "forecast_id": "abc123def456",
        "target_company": "acme",
        "technology_track": "cardio",
        "forecast_creation_time": "2026-11-02T00:00:00Z",
        "historical_information_cutoff": "2026-10-01",
        "forecast_horizon_months": 12,
        "horizon_end": "2027-10-01",
        "model_version": "reverse-rd-logistic-v1",
        "predicted_probability": 0.42,
        "uncertainty": {"temporal_ensemble_std": 0.01},
        "supporting_evidence": [],
        "contradictory_evidence": [],
        "verification_condition": {"table": "events", "kinds": ["510k", "pma"]},
        "baseline_probability": 0.3,
        "status": "pending",
    }
    record.update(overrides)
    return record


PROVENANCE = {
    "entries": [{
        "source": "experiments/reverse_rd_v2/data_provenance.json",
        "sha256": "a" * 64,
        "retrieved_at": "2026-11-01T04:34:49Z",
        "note": "frozen provenance",
    }]
}


def _event_ts(day: str) -> str:
    return day + "T00:00:00"


def _add_event(store: IntelligenceStore, event_id: str, kind: str, day: str,
               company: str = "acme", track: str = "cardio", payload: dict | None = None) -> None:
    store.conn.execute(
        "INSERT INTO events (event_id, source, kind, event_date, company_key, track_id,"
        " payload, available_at, timestamp_quality) VALUES (?,?,?,?,?,?,?,?,'date')",
        (event_id, "synthetic", kind, day, company, track, json.dumps(payload or {}),
         _event_ts(day)),
    )
    store.conn.commit()


class MappingTests(unittest.TestCase):
    def test_to_registry_spec_maps_every_field(self) -> None:
        spec = to_registry_spec(horizon_record(), data_provenance=PROVENANCE,
                                feature_version=FEATURE_VERSION)
        self.assertEqual(spec["idempotency_key"],
                         "horizon:abc123def456:reverse-rd-logistic-v1")
        self.assertEqual(spec["record_kind"], "nowcast")
        self.assertEqual(spec["target"]["type"], "company_track")
        self.assertEqual(spec["target"]["id"], "acme/cardio")
        self.assertEqual(spec["target"]["attrs"], {
            "company": "acme", "track": "cardio",
            "event_kinds": ["510k", "pma"], "material_pma_only": True,
        })
        self.assertEqual(spec["p"], 0.42)
        self.assertEqual(spec["horizon_months"], 12)
        self.assertEqual(spec["information_cutoff"], "2026-10-01")
        self.assertEqual(spec["window_start"], "2026-10-01")
        self.assertEqual(spec["window_end"], "2027-10-01")
        self.assertEqual(spec["model_version"], "reverse-rd-logistic-v1")
        self.assertEqual(spec["feature_version"], FEATURE_VERSION)
        # provenance is mapped to registry-shaped locator+hash pairs
        evidence = spec["evidence"]
        self.assertEqual(evidence["source_locator"], PROVENANCE["entries"][0]["source"])
        self.assertEqual(evidence["evidence_kind"], "source_observed")
        self.assertEqual(evidence["provenance"], [{
            "source_locator": PROVENANCE["entries"][0]["source"],
            "evidence_sha256": "a" * 64,
        }])
        expected_evidence = sha256_hex(canonical_json([
            {"source": PROVENANCE["entries"][0]["source"],
             "retrieved_at": PROVENANCE["entries"][0]["retrieved_at"],
             "note": PROVENANCE["entries"][0]["note"]},
        ]))
        self.assertEqual(evidence["evidence_sha256"], expected_evidence)
        self.assertNotIn("snapshot", spec)  # no snapshot file supplied -> omitted

    def test_mapping_is_deterministic_and_snapshot_verifies_locally(self) -> None:
        first = to_registry_spec(horizon_record(), data_provenance=PROVENANCE,
                                 feature_version=FEATURE_VERSION)
        second = to_registry_spec(horizon_record(), data_provenance=PROVENANCE,
                                  feature_version=FEATURE_VERSION)
        self.assertEqual(canonical_json(first), canonical_json(second))
        with tempfile.TemporaryDirectory() as tmp:
            document = {
                "format": "medradar-tkg-snapshot", "format_version": 1,
                "manifest": {"known_at": "2024-01-01T00:00:00.000000Z", "valid_at": None,
                             "schema_version": "tkg-schema-2", "code_version": "medradar-test",
                             "adapter_version": None, "counts": {"nodes": 0, "edges": 0},
                             "evidence_provenance": []},
                "nodes": [], "edges": [],
            }
            digest = sha256_hex(canonical_json(document))
            document["manifest"]["snapshot_sha256"] = digest
            snapshot = Path(tmp) / "snapshot.json"
            snapshot.write_text(json.dumps(document), encoding="utf-8")
            registry = ForecastRegistry(":memory:", clock=lambda: T0)
            spec = to_registry_spec(horizon_record(), data_provenance=PROVENANCE,
                                    feature_version=FEATURE_VERSION, snapshot_path=snapshot)
            result = registry.register(spec)
            self.assertEqual(result["snapshot"]["verification"], "verified_local")
            self.assertEqual(result["snapshot"]["sha256"], digest)


class RegistrationTests(unittest.TestCase):
    def _registry(self) -> ForecastRegistry:
        return ForecastRegistry(":memory:", clock=lambda: T0)

    def test_register_create_then_exact_retry_is_idempotent(self) -> None:
        registry = self._registry()
        first = register_horizon_forecasts(
            registry, [horizon_record()],
            data_provenance=PROVENANCE, feature_version=FEATURE_VERSION)
        self.assertEqual(first["registered"], 1)
        self.assertEqual(first["idempotent"], 0)
        self.assertEqual(first["rejected"], [])
        self.assertEqual(len(first["prediction_ids"]), 1)
        self.assertEqual(registry.count("forecasts"), 1)
        self.assertEqual(registry.get_forecast(first["prediction_ids"][0])["record_kind"], "nowcast")
        # exact retry - deterministic mapping, store clock not consumed
        second = register_horizon_forecasts(
            registry, [horizon_record()],
            data_provenance=PROVENANCE, feature_version=FEATURE_VERSION)
        self.assertEqual(second["registered"], 0)
        self.assertEqual(second["idempotent"], 1)
        self.assertEqual(second["prediction_ids"], first["prediction_ids"])
        self.assertEqual(registry.count("forecasts"), 1)

    def test_same_key_different_probability_raises_idempotency_conflict(self) -> None:
        registry = self._registry()
        register_horizon_forecasts(registry, [horizon_record(predicted_probability=0.42)],
                                   data_provenance=PROVENANCE, feature_version=FEATURE_VERSION)
        with self.assertRaises(IdempotencyConflict):
            register_horizon_forecasts(
                registry, [horizon_record(predicted_probability=0.9)],
                data_provenance=PROVENANCE, feature_version=FEATURE_VERSION)
        self.assertEqual(registry.count("forecasts"), 1)
        # the original p is untouched - no silent overwrite
        self.assertEqual(registry.raw("SELECT p FROM forecasts")[0]["p"], 0.42)

    def test_invalid_records_are_counted_as_rejected(self) -> None:
        registry = self._registry()
        bad = [
            horizon_record(forecast_id="bad-horizon", horizon_end="2028-01-01"),  # mismatch
            horizon_record(forecast_id="bad-company", target_company=""),
            horizon_record(forecast_id="bad-p", predicted_probability=1.5),
            horizon_record(forecast_id="bad-cutoff", historical_information_cutoff=None),
        ]
        counts = register_horizon_forecasts(registry, bad,
                                            data_provenance=PROVENANCE,
                                            feature_version=FEATURE_VERSION)
        self.assertEqual(counts["registered"], 0)
        self.assertEqual(len(counts["rejected"]), 4)
        self.assertEqual({item["forecast_id"] for item in counts["rejected"]},
                         {"bad-horizon", "bad-company", "bad-p", "bad-cutoff"})
        self.assertEqual(registry.count("forecasts"), 0)


class VerificationTests(unittest.TestCase):
    """resolve matured registered nowcasts from the real events table."""

    def _setup(self, tmp: str):
        store = IntelligenceStore(DB(Path(tmp) / "research.sqlite"))
        clock = MutableClock(datetime(2024, 6, 1, tzinfo=timezone.utc))
        registry = ForecastRegistry(":memory:", clock=clock)
        return store, registry, clock

    def _register(self, registry: ForecastRegistry, forecast_id: str = "mature-nowcast",
                  company: str = "acme", track: str = "cardio") -> str:
        # registered 2024-06-01 while [2024-01-01, 2025-01-01) is open
        record = horizon_record(
            forecast_id=forecast_id, target_company=company, technology_track=track,
            historical_information_cutoff="2024-01-01", horizon_end="2025-01-01",
        )
        counts = register_horizon_forecasts(
            registry, [record], data_provenance={"entries": [{"source": "synthetic://events"}]},
            feature_version=FEATURE_VERSION)
        self.assertEqual(counts["registered"], 1, counts)
        return counts["prediction_ids"][0]

    def test_positive_verification_uses_first_material_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, registry, clock = self._setup(tmp)
            prediction_id = self._register(registry)
            _add_event(store, "e1", "510k", "2024-08-01")
            _add_event(store, "e2", "510k", "2024-09-01")
            clock.set(datetime(2025, 1, 2, tzinfo=timezone.utc))
            result = verify_registered_forecasts(registry, store, "2025-01-10", as_of="2025-01-10")
            self.assertEqual(result, {"checked": 1, "verified": 1, "positives": 1, "pending": 0,
                                      "errors": 0, "error_details": []})
            resolution = registry.raw("SELECT * FROM resolutions")[0]
            self.assertEqual(resolution["outcome"], 1)
            self.assertEqual(resolution["event_time"], "2024-08-01T00:00:00.000000Z")
            self.assertIn("e1", resolution["source_locator"])
            # second pass: already resolved, nothing left to verify
            again = verify_registered_forecasts(registry, store, "2025-01-10", as_of="2025-01-10")
            self.assertEqual(again["verified"], 0)
            self.assertEqual(again["pending"], 0)
            store.close()

    def test_negative_verification_when_no_material_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, registry, clock = self._setup(tmp)
            self._register(registry)
            # a non-material PMA supplement does not count
            _add_event(store, "p1", "pma", "2024-08-01",
                       payload={"supplement_number": "S123", "supplement_type": "30-day notice"})
            # a 510(k) outside the window does not count either
            _add_event(store, "e-old", "510k", "2023-12-01")
            _add_event(store, "e-new", "510k", "2025-03-01")
            clock.set(datetime(2025, 1, 2, tzinfo=timezone.utc))
            result = verify_registered_forecasts(registry, store, "2025-01-10", as_of="2025-01-10")
            self.assertEqual(result["verified"], 1)
            self.assertEqual(result["positives"], 0)
            resolution = registry.raw("SELECT * FROM resolutions")[0]
            self.assertEqual(resolution["outcome"], 0)
            self.assertIsNone(resolution["event_time"])
            store.close()

    def test_material_pma_supplement_counts_as_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, registry, clock = self._setup(tmp)
            self._register(registry)
            _add_event(store, "p-panel", "pma", "2024-07-01",
                       payload={"supplement_number": "", "supplement_type": "PANEL TRACK"})
            clock.set(datetime(2025, 1, 2, tzinfo=timezone.utc))
            result = verify_registered_forecasts(registry, store, "2025-01-10", as_of="2025-01-10")
            self.assertEqual(result["positives"], 1)
            store.close()

    def test_incomplete_coverage_leaves_forecast_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, registry, clock = self._setup(tmp)
            self._register(registry)
            _add_event(store, "e1", "510k", "2024-08-01")
            clock.set(datetime(2025, 1, 2, tzinfo=timezone.utc))
            result = verify_registered_forecasts(registry, store, "2024-12-01", as_of="2025-01-10")
            self.assertEqual(result["verified"], 0)
            self.assertEqual(result["pending"], 1)
            self.assertEqual(registry.count("resolutions"), 0)
            store.close()

    def test_events_not_public_by_coverage_end_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, registry, clock = self._setup(tmp)
            self._register(registry)
            store.conn.execute(
                "INSERT INTO events (event_id, source, kind, event_date, company_key, track_id,"
                " payload, available_at, timestamp_quality) VALUES (?,?,?,?,?,?,?,?,'date')",
                ("late", "synthetic", "510k", "2024-08-01", "acme", "cardio", "{}",
                 "2025-01-09T00:00:00"),  # available after coverage end 2025-01-05
            )
            store.conn.commit()
            clock.set(datetime(2025, 1, 10, tzinfo=timezone.utc))
            result = verify_registered_forecasts(registry, store, "2025-01-05", as_of="2025-01-10")
            self.assertEqual(result["positives"], 0)  # not public inside coverage
            store.close()

    def test_unresolved_immature_nowcast_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = IntelligenceStore(DB(Path(tmp) / "research.sqlite"))
            registry = ForecastRegistry(":memory:", clock=lambda: T0)  # 2026-11-02
            # this nowcast's window ends 2027-10-01, after the frozen coverage
            counts = register_horizon_forecasts(
                registry, [horizon_record()],
                data_provenance=PROVENANCE, feature_version=FEATURE_VERSION)
            self.assertEqual(counts["registered"], 1)
            result = verify_registered_forecasts(registry, store, COVERAGE_END, as_of=COVERAGE_END)
            self.assertEqual(result["checked"], 1)
            self.assertEqual(result["pending"], 1)
            self.assertEqual(result["verified"], 0)
            store.close()


if __name__ == "__main__":
    unittest.main()
