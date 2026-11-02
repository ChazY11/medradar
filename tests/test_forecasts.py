"""Tests for frozen prospective forecasts: registration, windows, scoring, partial maturation."""
from __future__ import annotations

import json
import unittest

from medradar.intelligence.forecasts import (
    FORECAST_SCHEMA,
    PROBABILITY_BY_DECISION,
    build_forecast,
    index_to_quarter,
    quarter_to_index,
    score,
    validate_forecast_set,
    windows,
)


def forecast(**overrides):
    base = {"company": "medtronic", "track": "insulin_delivery", "alert_quarter": "2025-Q3",
            "promoted": True, "policy_version": "promotion_policy_v2", "shape": "level"}
    base.update(overrides)
    return build_forecast(**base)


class QuarterTest(unittest.TestCase):
    def test_round_trip(self):
        for label in ("2019-Q1", "2025-Q3", "2028-Q4"):
            self.assertEqual(index_to_quarter(quarter_to_index(label)), label)

    def test_rejects_bad_labels(self):
        for label in ("2025", "2025-Q5", "Q3-2025", ""):
            with self.assertRaises(ValueError):
                quarter_to_index(label)

    def test_ordering(self):
        self.assertLess(quarter_to_index("2024-Q4"), quarter_to_index("2025-Q1"))


class WindowTest(unittest.TestCase):
    def test_windows_are_fixed_relative_to_the_alert(self):
        result = windows("2025-Q3")
        self.assertEqual(result["confirmation"], "2025-Q4..2026-Q1")
        self.assertEqual(result["outcome"], "2026-Q2..2027-Q1")
        self.assertEqual(result["matures_when_data_through"], "2027-Q1")

    def test_windows_cross_year_boundaries(self):
        result = windows("2024-Q4")
        self.assertEqual(result["confirmation"], "2025-Q1..2025-Q2")
        self.assertEqual(result["outcome"], "2025-Q3..2026-Q2")


class BuildForecastTest(unittest.TestCase):
    def test_promoted_and_unpromoted_have_different_probabilities(self):
        promoted = forecast(promoted=True)
        unpromoted = forecast(promoted=False)
        self.assertEqual(promoted["probability_persisted"], PROBABILITY_BY_DECISION["promoted"])
        self.assertEqual(unpromoted["probability_persisted"], PROBABILITY_BY_DECISION["not_promoted"])
        self.assertLess(unpromoted["probability_persisted"], promoted["probability_persisted"])

    def test_forecast_is_json_serialisable_and_identified(self):
        record = forecast()
        self.assertEqual(record["id"], "medtronic|insulin_delivery|2025-Q3")
        self.assertIsInstance(json.dumps(record), str)

    def test_maturation_quarter_is_present(self):
        self.assertEqual(forecast()["windows"]["matures_when_data_through"], "2027-Q1")


class ValidateTest(unittest.TestCase):
    def payload(self, records):
        return {"schema": FORECAST_SCHEMA, "forecasts": records}

    def test_valid_set_has_no_problems(self):
        self.assertEqual(validate_forecast_set(self.payload([forecast()])), [])

    def test_empty_set_is_rejected(self):
        self.assertTrue(any("no forecasts" in problem
                            for problem in validate_forecast_set(self.payload([]))))

    def test_duplicate_ids_are_rejected(self):
        problems = validate_forecast_set(self.payload([forecast(), forecast()]))
        self.assertTrue(any("duplicate" in problem for problem in problems))

    def test_out_of_range_probability_is_rejected(self):
        record = forecast()
        record["probability_persisted"] = 1.4
        self.assertTrue(any("out of range" in problem
                            for problem in validate_forecast_set(self.payload([record]))))

    def test_missing_maturation_is_rejected(self):
        record = forecast()
        record["windows"] = {}
        self.assertTrue(any("maturation" in problem
                            for problem in validate_forecast_set(self.payload([record]))))


class ScoreTest(unittest.TestCase):
    def test_nothing_matured_is_reported_as_pending(self):
        result = score([forecast()], {})
        self.assertEqual(result["resolved"], 0)
        self.assertEqual(result["pending"], 1)
        self.assertIsNone(result["brier"])
        self.assertEqual(result["status"], "nothing matured yet")

    def test_partial_maturation_flags_remaining(self):
        records = [forecast(), forecast(alert_quarter="2025-Q2", track="coronary")]
        result = score(records, {"medtronic|insulin_delivery|2025-Q3": True})
        self.assertEqual(result["resolved"], 1)
        self.assertEqual(result["pending"], 1)
        self.assertEqual(result["status"], "partially matured")

    def test_brier_maths(self):
        records = [forecast()]
        hit = score(records, {records[0]["id"]: True})
        miss = score(records, {records[0]["id"]: False})
        self.assertAlmostEqual(hit["brier"], (0.800 - 1.0) ** 2)
        self.assertAlmostEqual(miss["brier"], (0.800 - 0.0) ** 2)
        self.assertLess(hit["brier"], miss["brier"])

    def test_accuracy_uses_the_half_threshold(self):
        records = [forecast()]
        self.assertEqual(score(records, {records[0]["id"]: True})["accuracy"], 1.0)
        self.assertEqual(score(records, {records[0]["id"]: False})["accuracy"], 0.0)

    def test_per_decision_breakdown(self):
        promoted = forecast()
        unpromoted = forecast(promoted=False, track="coronary")
        result = score([promoted, unpromoted], {promoted["id"]: True, unpromoted["id"]: False})
        self.assertEqual(set(result["by_decision"]), {"promoted", "not_promoted"})
        self.assertEqual(result["by_decision"]["promoted"]["n"], 1)


if __name__ == "__main__":
    unittest.main()
