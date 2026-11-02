"""Offline tests for the continuous forecasting cycle (Phase 3).

Everything runs on a synthetic research DB and an in-memory registry with a
fixed clock, so the cycle is deterministic and touches neither the real
``data/research.sqlite`` nor the network.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from medradar.db import DB
from medradar.forecast_registry import ForecastRegistry
from medradar.intelligence.features.financial_features import FEATURES as FINANCIAL_FEATURES
from medradar.intelligence.features.research_features import BASE_FEATURES, DATASET_VERSION
from medradar.intelligence.forecasting import horizon
from medradar.intelligence.forecasting.cycle import run_cycle, summary
from medradar.intelligence.forecasting.registry_adapter import to_registry_spec
from medradar.intelligence.storage import IntelligenceStore

CLOCK = datetime(2025, 2, 1, tzinfo=timezone.utc)  # inside [2025-01-01, 2026-01-01)


class FixedClock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment


def _features(seed: float) -> dict[str, float]:
    return {name: float(seed) for name in list(BASE_FEATURES) + list(FINANCIAL_FEATURES)}


def _add_event(store: IntelligenceStore, event_id: str, company: str, track: str, day: str) -> None:
    store.conn.execute(
        "INSERT INTO events (event_id, source, kind, event_date, company_key, track_id,"
        " payload, available_at, timestamp_quality) VALUES (?,?,?,?,?,?,?,?,'date')",
        (event_id, "synthetic", "510k", day, company, track, "{}", day + "T00:00:00"),
    )
    store.conn.commit()


def _build_research_db(path: Path) -> None:
    """A miniature research DB: mature training examples + pending candidates."""
    with IntelligenceStore(DB(path)) as store:
        for index, (company, track, day) in enumerate((
            ("acme", "cardio", "2024-01-01"),
            ("acme", "cardio", "2024-03-01"),
            ("acme", "neuro", "2024-02-01"),
            ("beta", "cardio", "2024-04-01"),
            ("beta", "ortho", "2024-06-01"),
        )):
            _add_event(store, f"evt-{index}", company, track, day)
        mature = []
        for index, (cutoff, label, company, track) in enumerate((
            ("2023-01-01", 0, "acme", "cardio"),
            ("2023-01-01", 1, "beta", "cardio"),
            ("2023-04-01", 0, "acme", "neuro"),
            ("2023-04-01", 1, "beta", "ortho"),
        )):
            mature.append({
                "example_id": f"example-{index}",
                "cutoff": cutoff,
                "horizon_months": 12,
                "company_key": company,
                "track_id": track,
                "features": _features(seed=float(index + 1)),
                "feature_available_at": cutoff,
                "label": label,
                "first_target_event_date": None,
                "target_event_count": 1 if label else 0,
                "maturity": "mature",
            })
        store.replace_examples(DATASET_VERSION, mature)


def _cycle_kwargs(tmp: str) -> dict:
    return {
        "db_path": Path(tmp) / "research.sqlite",
        "out_dir": Path(tmp) / "out",
        "coverage_end": "2025-01-15",
        "top_n": 2,
        "horizon_months": 12,
    }


class ForecastCycleTests(unittest.TestCase):
    def test_cycle_registers_nowcasts_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.sqlite"
            _build_research_db(db)
            registry = ForecastRegistry(":memory:", clock=FixedClock(CLOCK))
            first = run_cycle(**_cycle_kwargs(tmp), registry=registry)
            self.assertEqual(first["counts"]["horizon_records"], 2)
            self.assertEqual(first["counts"]["registered"], 2)
            self.assertEqual(first["counts"]["idempotent"], 0)
            self.assertEqual(first["counts"]["rejected"], 0)
            self.assertEqual(first["counts"]["verified"], 0)
            self.assertEqual(first["counts"]["pending"], 2)  # windows end 2026-01-01
            self.assertEqual(first["registry"]["by_record_kind"], {"nowcast": 2})
            self.assertEqual(first["calibration"]["status"], "insufficient_matured_forecasts")
            artifact_path = Path(first["artifact"]["path"])
            self.assertTrue(artifact_path.is_file())
            self.assertTrue((Path(tmp) / "out" / "cycle.json").is_file())
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(len(artifact["nowcasts"]), 2)
            self.assertEqual(artifact["manifest"]["counts_by_record_kind"],
                             {"forecast": 0, "nowcast": 2, "retrospective_fixture": 0})
            logged = json.loads((Path(tmp) / "out" / "cycle.json").read_text(encoding="utf-8"))
            self.assertEqual(logged["run_id"], first["run_id"])
            self.assertEqual(logged["counts"]["registered"], 2)

            # every registered nowcast is a real model probability, not a constant
            probabilities = [registry.get_forecast(pid)["p"] for pid in first["registration"]["prediction_ids"]]
            self.assertTrue(all(0.0 <= p <= 1.0 for p in probabilities))
            self.assertEqual(len(set(probabilities)), len(probabilities))
            # the registered rows are nowcasts with an open window at generated_at
            rows = registry.raw("SELECT record_kind, window_start, generated_at, window_end FROM forecasts")
            for row in rows:
                self.assertEqual(row["record_kind"], "nowcast")
                self.assertLessEqual(row["window_start"], row["generated_at"])
                self.assertLess(row["generated_at"], row["window_end"])

            # second identical run: zero new history, same deterministic output
            second = run_cycle(**_cycle_kwargs(tmp), registry=registry)
            self.assertEqual(second["counts"]["registered"], 0)
            self.assertEqual(second["counts"]["idempotent"], 2)
            self.assertEqual(registry.count("forecasts"), 2)
            self.assertEqual(second["run_id"], first["run_id"])
            self.assertEqual(second["artifact"]["sha256"], first["artifact"]["sha256"])

    def test_cycle_is_deterministic_across_fresh_registries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.sqlite"
            _build_research_db(db)
            first = run_cycle(**_cycle_kwargs(tmp),
                              registry=ForecastRegistry(":memory:", clock=FixedClock(CLOCK)))
            second = run_cycle(**_cycle_kwargs(tmp),
                               registry=ForecastRegistry(":memory:", clock=FixedClock(CLOCK)))
            self.assertEqual(first["registration"]["prediction_ids"],
                             second["registration"]["prediction_ids"])
            self.assertEqual(first["artifact"]["sha256"], second["artifact"]["sha256"])
            self.assertEqual(first["run_id"], second["run_id"])

    def test_cycle_trains_only_on_the_continuation_dataset(self) -> None:
        # A mature entry-target example with the same feature names must not be
        # mixed into the continuation model: edit the DB to add one and check the
        # resulting probabilities are unchanged.
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.sqlite"
            _build_research_db(db)
            baseline = run_cycle(**_cycle_kwargs(tmp),
                                 registry=ForecastRegistry(":memory:", clock=FixedClock(CLOCK)))
            with IntelligenceStore(DB(db)) as store:
                store.replace_examples("first_entry_v1", [{
                    "example_id": "entry-only", "cutoff": "2023-01-01", "horizon_months": 12,
                    "company_key": "acme", "track_id": "cardio", "features": _features(999.0),
                    "feature_available_at": "2023-01-01", "label": 0,
                    "first_target_event_date": None, "target_event_count": 0, "maturity": "mature",
                }])
            with_entry = run_cycle(**_cycle_kwargs(tmp), registry=ForecastRegistry(
                ":memory:", clock=FixedClock(CLOCK)))
            self.assertEqual(baseline["registration"]["prediction_ids"],
                             with_entry["registration"]["prediction_ids"])
            self.assertEqual(baseline["artifact"]["sha256"], with_entry["artifact"]["sha256"])

    def test_build_forecasts_matches_registered_probabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.sqlite"
            _build_research_db(db)
            with IntelligenceStore(DB(db)) as store:
                records = horizon.build_forecasts(
                    store, base_features=list(BASE_FEATURES),
                    financial_features=list(FINANCIAL_FEATURES),
                    coverage_end="2025-01-15", horizon_months=12, top_n=2,
                    dataset_version=DATASET_VERSION)
            self.assertEqual(len(records), 2)
            self.assertEqual({record["historical_information_cutoff"] for record in records},
                             {"2025-01-01"})
            registry = ForecastRegistry(":memory:", clock=FixedClock(CLOCK))
            log = run_cycle(**_cycle_kwargs(tmp), registry=registry)
            # the cycle mapped exactly these records with the same provenance
            fresh = ForecastRegistry(":memory:", clock=FixedClock(CLOCK))
            expected_ids = sorted(
                fresh.register(to_registry_spec(
                    record, data_provenance=log["inputs"]["provenance"],
                    feature_version=log["inputs"]["feature_version"]))["prediction_id"]
                for record in records
            )
            self.assertEqual(sorted(log["registration"]["prediction_ids"]), expected_ids)
            # p is carried verbatim from the model, never fabricated
            registered_p = sorted(registry.get_forecast(pid)["p"]
                                  for pid in log["registration"]["prediction_ids"])
            self.assertEqual(registered_p, sorted(record["predicted_probability"] for record in records))

    def test_cycle_with_no_candidates_registers_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.sqlite"
            _build_research_db(db)
            # cutoff 2023-01-01 is before every event -> no candidates, no records
            log = run_cycle(
                db_path=db, out_dir=Path(tmp) / "out", coverage_end="2023-01-15",
                top_n=2, registry=ForecastRegistry(":memory:", clock=FixedClock(CLOCK)))
            self.assertEqual(log["counts"]["horizon_records"], 0)
            self.assertEqual(log["counts"]["registered"], 0)
            self.assertEqual(log["counts"]["idempotent"], 0)
            self.assertEqual(log["registry"]["forecasts_total"], 0)
            self.assertTrue(Path(log["artifact"]["path"]).is_file())
            self.assertEqual(summary(log)["horizon_records"], 0)


if __name__ == "__main__":
    unittest.main()
