"""Offline tests for the foundation layer and the metrics engine.

No network access anywhere: the metrics test builds a synthetic SQLite database
whose rows have exactly the shape the collectors produce. That keeps CI fast and
deterministic while still exercising the real analysis code path.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from medradar.analyze import build_metrics
from medradar.config import CompanyRegistry, TrackRegistry, load_companies, load_tracks
from medradar.db import DB, make_event_id
from medradar.util import (
    bootstrap_ci,
    gamma_poisson,
    js_divergence,
    parse_date,
    prob_rate_above,
    quarter_index,
    quarter_label,
)


class UtilTests(unittest.TestCase):
    def test_parse_date_accepts_fda_and_trial_shapes(self) -> None:
        self.assertEqual(parse_date("20240115"), date(2024, 1, 15))
        self.assertEqual(parse_date("2024-01-15"), date(2024, 1, 15))
        self.assertEqual(parse_date("2024/01/15"), date(2024, 1, 15))
        self.assertEqual(parse_date("Jan 15, 2024"), date(2024, 1, 15))
        self.assertEqual(parse_date("2024-01"), date(2024, 1, 1))
        self.assertIsNone(parse_date(""))
        self.assertIsNone(parse_date("not-a-date"))

    def test_quarter_helpers(self) -> None:
        self.assertEqual(quarter_label(quarter_index("2026-10-31")), "2026Q4")
        self.assertEqual(quarter_index("2026-01-01"), quarter_index("2026-03-31"))

    def test_gamma_poisson_identity_when_rate_matches_prior(self) -> None:
        # 6 events over 2 quarters = 3.0/quarter == prior rate -> posterior == 3.0
        posterior = gamma_poisson(6, 2.0, 3.0, 3.0)
        self.assertAlmostEqual(posterior["mean"], 3.0, places=9)
        self.assertLess(posterior["lo"], posterior["mean"])
        self.assertGreater(posterior["hi"], posterior["mean"])

    def test_prob_rate_above_is_about_half_at_baseline(self) -> None:
        probability = prob_rate_above(10, 2.0, 5.0, 3.0, 5.0)
        self.assertGreater(probability, 0.3)
        self.assertLess(probability, 0.7)

    def test_js_divergence_self_is_zero_and_bounded(self) -> None:
        self.assertAlmostEqual(js_divergence({"a": 1, "b": 2}, {"a": 1, "b": 2}), 0.0, places=9)
        shifted = js_divergence({"a": 1, "b": 2}, {"a": 5, "b": 0.1})
        self.assertGreater(shifted, 0.0)

    def test_bootstrap_ci_brackets_the_point(self) -> None:
        result = bootstrap_ci([1, 2, 3, 4, 5])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertLessEqual(result["lo"], result["point"])
        self.assertGreaterEqual(result["hi"], result["point"])


class RegistryTests(unittest.TestCase):
    def test_subsidiaries_resolve_to_one_parent(self) -> None:
        registry = load_companies("device")
        for applicant in (
            "MEDTRONIC MINIMED",
            "Covidien (Part of Medtronic)",
            "MEDTRONIC SOFAMOR DANEK USA, INC.",
        ):
            key, confidence, _ = registry.resolve(applicant)
            self.assertEqual(key, "medtronic", applicant)
            self.assertGreater(confidence, 0.9)
        for applicant in ("DEPUY SYNTHES", "ETHICON ENDO SURGERY", "BIOSENSE WEBSTER"):
            key, _, _ = registry.resolve(applicant)
            self.assertEqual(key, "johnson_johnson_medtech", applicant)

    def test_unknown_applicant_stays_unmatched(self) -> None:
        registry = load_companies("device")
        key, confidence, _ = registry.resolve("ACME TOOL WORKS")
        self.assertIsNone(key)
        self.assertLess(confidence, 0.8)

    def test_track_matching_prefers_longest_keyword(self) -> None:
        tracks = load_tracks("device")
        self.assertEqual(tracks.match_text("SPINAL CORD STIMULATOR"), "neurostimulation")
        self.assertEqual(tracks.match_text("PULSED FIELD ABLATION SYSTEM"), "ep_pfa")
        self.assertEqual(tracks.match_text("CONTINUOUS GLUCOSE MONITOR"), "diabetes_cgm")
        self.assertIsNone(tracks.match_text("TOTALLY UNRELATED DEVICE"))

    def test_registries_are_non_empty(self) -> None:
        self.assertGreater(len(load_companies("device").all()), 20)
        self.assertGreater(len(load_companies("drug").all()), 20)
        self.assertGreater(len(load_tracks("device").all()), 20)


class DBTests(unittest.TestCase):
    def test_upsert_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with DB(Path(tmp) / "test.sqlite") as db:
                event = {
                    "event_id": make_event_id("openfda_device_510k", "510k", "K240001"),
                    "source": "openfda_device_510k",
                    "kind": "510k",
                    "event_date": "2024-05-01",
                    "company_key": "medtronic",
                    "track_id": "spine",
                    "product_code": "NKB",
                    "title": "Test",
                    "payload": {"k_number": "K240001"},
                }
                self.assertEqual(db.upsert_events([event]), 1)
                self.assertEqual(db.upsert_events([event]), 1)
                self.assertEqual(db.table_count("events"), 1)
                row = db.query("SELECT * FROM events")[0]
                self.assertEqual(row["event_date"], "2024-05-01")
                self.assertIn("K240001", row["payload"])

    def test_prices_and_meta_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with DB(Path(tmp) / "test.sqlite") as db:
                db.upsert_prices(
                    [{"ticker": "MDT", "date": "2026-01-02", "open": 1.0, "close": 2.0}]
                )
                self.assertEqual(db.table_count("prices"), 1)
                self.assertEqual(db.prices_for("MDT")[0]["close"], 2.0)
                db.meta_set("last_run", {"rows": 3})
                self.assertEqual(db.meta_get("last_run"), {"rows": 3})


class AnalyzeTests(unittest.TestCase):
    """Build a synthetic fact table and assert the analysis contract holds."""

    def _build_db(self, path: Path, with_nmpa: bool) -> DB:
        db = DB(path)
        events = []

        def add(kind, day, company, track=None, code=None, payload=None, source=None, title=""):
            events.append(
                {
                    "event_id": make_event_id(source or kind, kind, company, day, track, code),
                    "source": source or f"openfda_{kind}",
                    "kind": kind,
                    "event_date": day,
                    "company_key": company,
                    "applicant_raw": company or "",
                    "track_id": track,
                    "product_code": code,
                    "title": title,
                    "payload": payload or {},
                }
            )

        # Baseline: 2025-11 / 2026-02 ; recent: 2026-05 / 2026-08
        for day in ("2025-11-10", "2026-02-10"):
            for index in range(2):
                add("510k", day, "medtronic", "spine", f"NKB{index}")
                add("510k", day, "stryker", "trauma", f"KTT{index}")
            add("510k", day, None, "surgical_robotics", "ROB1", source="openfda_device_510k")
        for day in ("2026-05-10", "2026-08-10"):
            for index in range(10):
                add("510k", day, "medtronic", "spine", f"NKB{index}")
                add("510k", day, "stryker", "trauma", f"KTT{index}")
            add("510k", day, None, "surgical_robotics", f"ROB{day}")
        add("pma", "2026-06-01", "medtronic", "heart_failure", "DQK")
        add("device_recall", "2026-08-01", "philips", "imaging_us", payload={"reason_for_recall": "Software"})
        add("device_recall", "2026-08-15", "philips", "imaging_us", payload={"reason_for_recall": "Software"})
        add(
            "drug_approval",
            "2026-07-01",
            "lilly",
            payload={"submission_class_code": "TYPE 1"},
            title="Tirzepatide",
            source="openfda_drug_drugsfda",
        )
        add(
            "trial",
            "2026-06-01",
            "lilly",
            "t_cardiometabolic",
            payload={"phase": ["PHASE3"], "conditions": ["Obesity"]},
            source="ctgov",
        )
        add(
            "trial",
            "2025-12-01",
            "lilly",
            "t_cardiometabolic",
            payload={"phase": ["PHASE2"], "conditions": ["Obesity"]},
            source="ctgov",
        )
        if with_nmpa:
            add("nmpa_registration", "2026-03-01", None, "spine", payload={"demo": True}, source="nmpa_demo")
        db.upsert_events(events)
        db.upsert_companies(
            [
                {"key": "medtronic", "name_zh": "美敦力", "ticker": "MDT", "is_major": 1},
                {"key": "stryker", "name_zh": "史赛克", "ticker": "SYK", "is_major": 1},
                {"key": "philips", "name_zh": "飞利浦", "ticker": "PHG", "is_major": 1},
                {"key": "lilly", "name_zh": "礼来", "ticker": "LLY", "is_major": 1},
            ]
        )
        return db

    def test_metrics_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = self._build_db(Path(tmp) / "facts.sqlite", with_nmpa=False)
            metrics = build_metrics(db, window_quarters=2, baseline_quarters=2, today=date(2026, 10, 31))
            db.close()

            for key in ("meta", "device", "drug", "cn_gap", "signals", "alerts"):
                self.assertIn(key, metrics)
            for key in ("window", "baseline", "counts", "data_status"):
                self.assertIn(key, metrics["meta"])
            self.assertEqual(metrics["meta"]["data_status"]["nmpa"], "unavailable")
            self.assertGreaterEqual(len(metrics["device"]["tracks"]), 2)
            track = metrics["device"]["tracks"][0]
            for field in ("track_id", "name_zh", "recent", "thi", "prob_up", "ci", "emerging"):
                self.assertIn(field, track)
            # 5x the baseline rate must survive the shrinkage and come out clearly high
            spine = next(row for row in metrics["device"]["tracks"] if row["track_id"] == "spine")
            self.assertGreater(spine["thi"], 2.0)
            self.assertGreater(spine["prob_up"], 0.9)
            # China gap must be null-valued, never 0, when no CN data is loaded
            gap_row = metrics["cn_gap"][0]
            self.assertIsNone(gap_row["cn_count"])
            self.assertIsNone(gap_row["gap_index"])
            self.assertEqual(gap_row["cn_data_status"], "unavailable")
            # recall cluster becomes a negative-direction signal
            self.assertTrue(any(s["direction"] == -1 for s in metrics["signals"]))
            # JSON-serialisable without NaN
            json.dumps(metrics, ensure_ascii=False, allow_nan=False)

    def test_metrics_with_demo_nmpa_reports_demo_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = self._build_db(Path(tmp) / "facts.sqlite", with_nmpa=True)
            metrics = build_metrics(db, window_quarters=2, baseline_quarters=2, today=date(2026, 10, 31))
            db.close()
            self.assertEqual(metrics["meta"]["data_status"]["nmpa"], "demo")
            self.assertTrue(all(row["cn_data_status"] == "demo" for row in metrics["cn_gap"]))
            spine = next(row for row in metrics["cn_gap"] if row["track_id"] == "spine")
            self.assertEqual(spine["cn_count"], 1)
            self.assertIsNotNone(spine["gap_index"])


if __name__ == "__main__":
    unittest.main()
