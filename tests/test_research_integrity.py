"""Regression tests for regulatory semantics and point-in-time research integrity."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from medradar.analyze import build_metrics
from medradar.cases import event_study_summary
from medradar.corpus import classify_detail
from medradar.db import DB
from medradar.eventstudy import load_signals
from medradar.replay import _resolve_available_at


class RegulatoryTaxonomyTests(unittest.TestCase):
    def test_regulatory_events_are_not_crl_synonyms(self) -> None:
        self.assertEqual(classify_detail("The FDA placed the study on clinical hold.")["category"], "clinical_hold")
        self.assertEqual(classify_detail("The company received a refuse to file letter.")["category"], "refuse_to_file")
        self.assertEqual(classify_detail("The company received a complete response letter.")["category"], "crl")

    def test_designation_is_not_approval(self) -> None:
        detail = classify_detail("Breakthrough Device Designation granted for novel monitor.")
        self.assertEqual(detail["category"], "designation")
        self.assertEqual(detail["direction"], 0)

    def test_pre_submission_for_approval_is_not_approval(self) -> None:
        detail = classify_detail(
            "BioCardia Announces Revised De Novo Pre-Submission for FDA Approval",
            ["fda approval", "pre-submission"],
        )
        self.assertEqual(detail["category"], "pre_submission")
        self.assertEqual(detail["direction"], 0)
        self.assertEqual(detail["scores"]["approval"], 0)

    def test_actual_approval_still_positive(self) -> None:
        detail = classify_detail("Company Receives FDA Approval for CardioPulse System")
        self.assertEqual(detail["category"], "approval")
        self.assertEqual(detail["direction"], 1)


class ExtremeReturnAuditTests(unittest.TestCase):
    def test_extreme_case_is_listed_and_excluded_from_inference(self) -> None:
        selected = []
        for index, value in enumerate((0.02, -0.01, 0.03, 0.01)):
            selected.append({
                "case_id": f"normal-{index}", "ticker": "AAA", "date": f"2024-0{index + 1}-10",
                "category": "approval", "direction": 1, "price_20d": value,
            })
        selected.append({
            "case_id": "broken-price", "ticker": "BAD", "date": "2024-05-10",
            "category": "approval", "direction": 1, "price_20d": 45.2, "raw_20d": 46.0,
        })
        result = event_study_summary({"selected": selected}, horizons=(20,))
        row = result["by_horizon"]["20"]["categories"]["approval"]
        self.assertEqual(row["raw_n"], 5)
        self.assertEqual(row["n"], 4)
        self.assertEqual(row["extreme_n"], 1)
        self.assertEqual(row["excluded_n"], 1)
        self.assertGreater(row["unfiltered_raw_mean"], 9)
        self.assertLess(row["raw_mean"], 0.1)
        self.assertEqual(result["audit"]["flagged_observations"], 1)
        self.assertEqual(result["audit"]["excluded_from_inference"], 1)
        self.assertEqual(result["audit"]["flagged_cases"][0]["case_id"], "broken-price")
        self.assertIn("corporate actions", result["audit"]["flagged_cases"][0]["review"])


class PublicTimestampTests(unittest.TestCase):
    def test_event_date_is_not_silently_promoted_to_public_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with DB(Path(tmp) / "test.sqlite") as db:
                db.upsert_events([{
                    "event_id": "historical-decision", "source": "openfda", "kind": "510k",
                    "event_date": "2020-01-02", "company_key": "medtronic",
                    "track_id": "spine", "product_code": "NKB",
                }])
                row = db.query("SELECT * FROM events")[0]
                self.assertEqual(row["event_date"], "2020-01-02")
                self.assertIsNone(row["published_at"])
                self.assertIsNone(row["available_at"])
                self.assertEqual(row["timestamp_quality"], "unknown")
                metrics = build_metrics(db, today=date(2020, 1, 10))
                self.assertEqual(metrics["signals"], [])
                self.assertEqual(metrics["timestamps"]["excluded_from_trading"], 1)

    def test_real_public_date_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with DB(Path(tmp) / "test.sqlite") as db:
                db.upsert_events([
                    {
                        "event_id": "public-filing", "source": "sec", "kind": "8k_catalyst",
                        "event_date": "2024-01-02", "published_at": "2024-01-02",
                    },
                    {
                        "event_id": "available-only", "source": "sec", "kind": "8k_catalyst",
                        "event_date": "2024-01-03", "available_at": "2024-01-03",
                    },
                ])
                row = db.query("SELECT * FROM events WHERE event_id = 'public-filing'")[0]
                self.assertTrue(row["available_at"].startswith("2024-01-02"))
                self.assertEqual(row["timestamp_quality"], "date")
                available_only = db.query("SELECT * FROM events WHERE event_id = 'available-only'")[0]
                self.assertTrue(available_only["available_at"].startswith("2024-01-03"))
                self.assertEqual(available_only["timestamp_quality"], "date")

    def test_iso_public_datetime_can_generate_a_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with DB(Path(tmp) / "test.sqlite") as db:
                db.upsert_events([{
                    "event_id": "timed-clearance", "source": "openfda", "kind": "510k",
                    "event_date": "2020-01-02", "published_at": "2020-01-02T16:05:00Z",
                    "company_key": "medtronic", "track_id": "spine", "product_code": "NKB",
                }])
                row = db.query("SELECT * FROM events")[0]
                self.assertEqual(row["timestamp_quality"], "datetime")
                metrics = build_metrics(db, today=date(2020, 1, 10))
                self.assertEqual(len(metrics["signals"]), 1)
                self.assertEqual(metrics["signals"][0]["signal_date"], "2020-01-03")

    def test_replay_rejects_event_date_fallback_and_estimates(self) -> None:
        moment, quality = _resolve_available_at({"event_date": "2020-01-02"})
        self.assertIsNone(moment)
        self.assertEqual(quality, "unknown")
        moment, quality = _resolve_available_at({
            "event_date": "2020-01-02", "available_at": "2020-01-02",
            "timestamp_quality": "estimated",
        })
        self.assertEqual(quality, "unknown")

    def test_estimated_signal_cannot_enter_event_study(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with DB(Path(tmp) / "test.sqlite") as db:
                db.upsert_signals([{
                    "signal_id": "estimated", "ticker": "AAA", "signal_date": "2024-01-02",
                    "available_at": "2024-01-02", "timestamp_quality": "estimated",
                }])
                signals, skipped = load_signals(db, None)
                self.assertEqual(signals, [])
                self.assertEqual(skipped["estimated_timestamp"], 1)


if __name__ == "__main__":
    unittest.main()
