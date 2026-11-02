"""Tests for Phase 0 study logic: source tiering, quarter arithmetic, coverage aggregation, evaluability."""
from __future__ import annotations

import unittest

from medradar.studies.coverage import (
    DOMAINS,
    aggregate_coverage,
    classify_source,
    evaluability,
    quarter_of,
    quarters_between,
)

FULL_TIME_COLUMNS = ("event_id", "event_date", "published_at", "available_at", "first_seen_at")


class TierTest(unittest.TestCase):
    def test_absent_source_is_tier_d(self):
        result = classify_source(present=False, columns=FULL_TIME_COLUMNS)
        self.assertEqual(result["tier"], "D")

    def test_publication_columns_make_tier_a(self):
        result = classify_source(present=True, columns=FULL_TIME_COLUMNS)
        self.assertEqual(result["tier"], "A")

    def test_event_date_only_is_tier_b(self):
        result = classify_source(present=True, columns=("event_id", "event_date"))
        self.assertEqual(result["tier"], "B")

    def test_collection_time_first_seen_does_not_promote_a_source(self):
        result = classify_source(present=True,
                                 columns=("event_id", "event_date", "first_seen_at"),
                                 first_seen_is_fetch=True)
        self.assertEqual(result["tier"], "B")
        self.assertTrue(any("collection date" in reason for reason in result["reasons"]))

    def test_independent_first_seen_can_promote(self):
        result = classify_source(present=True,
                                 columns=("event_id", "event_date", "first_seen_at"),
                                 first_seen_is_fetch=False)
        self.assertEqual(result["tier"], "A")

    def test_no_dates_is_tier_c_only_when_present(self):
        result = classify_source(present=True, columns=("event_id", "value"))
        self.assertEqual(result["tier"], "C")


class QuarterTest(unittest.TestCase):
    def test_quarter_of_parses_iso_dates(self):
        self.assertEqual(quarter_of("2024-01-01"), "2024-Q1")
        self.assertEqual(quarter_of("2024-12-31T23:59:59"), "2024-Q4")

    def test_quarter_of_rejects_junk(self):
        for value in ("", None, "not-a-date", "2024-13-01", "20240101"):
            self.assertIsNone(quarter_of(value))

    def test_quarters_between_is_inclusive_across_years(self):
        self.assertEqual(quarters_between("2024-07-01", "2025-04-01"),
                         ["2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2"])

    def test_quarters_between_handles_single_quarter(self):
        self.assertEqual(quarters_between("2024-02-01", "2024-03-31"), ["2024-Q1"])


class AggregationTest(unittest.TestCase):
    def test_counts_only_observations_inside_the_window(self):
        observations = [
            {"company": "medtronic", "track": "patient_monitoring", "date": "2020-05-01", "source": "s1"},
            {"company": "medtronic", "track": "patient_monitoring", "date": "2024-05-01", "source": "s1"},
            {"company": "medtronic", "track": "patient_monitoring", "date": "2010-05-01", "source": "s1"},
        ]
        result = aggregate_coverage(observations, window=("2018-01-01", "2025-12-31"))
        cell = next(row for row in result["matrix"]
                    if row["company"] == "medtronic" and row["domain"] == "patient_monitoring")
        self.assertEqual(cell["observations_in_window"], 2)
        self.assertEqual(cell["outside_window"], 1)
        self.assertEqual(cell["quarters_with_observation"], 2)

    def test_unknown_track_is_counted_not_silently_dropped(self):
        observations = [{"company": "medtronic", "track": "unmapped_track", "date": "2020-01-01",
                         "source": "s1"}]
        result = aggregate_coverage(observations, window=("2018-01-01", "2025-12-31"))
        self.assertEqual(result["unassigned"]["unknown_track"], 1)

    def test_every_firm_domain_cell_exists_even_when_empty(self):
        result = aggregate_coverage([], window=("2018-01-01", "2025-12-31"))
        self.assertEqual(len(result["matrix"]), len(DOMAINS) * 5)
        self.assertTrue(all(row["observations_in_window"] == 0 for row in result["matrix"]))

    def test_sources_are_summarised_per_cell(self):
        observations = [
            {"company": "philips", "track": "imaging_us", "date": "2020-01-01", "source": "a"},
            {"company": "philips", "track": "imaging_us", "date": "2021-01-01", "source": "b"},
        ]
        result = aggregate_coverage(observations, window=("2018-01-01", "2025-12-31"))
        cell = next(row for row in result["matrix"]
                    if row["company"] == "philips" and row["domain"] == "ultrasound_imaging")
        self.assertEqual(cell["sources"], {"a": 1, "b": 1})

    def test_per_firm_totals_match_the_matrix(self):
        observations = [
            {"company": "philips", "track": "imaging_us", "date": "2020-01-01", "source": "a"},
            {"company": "medtronic", "track": "medical_ai", "date": "2020-01-01", "source": "a"},
        ]
        result = aggregate_coverage(observations, window=("2018-01-01", "2025-12-31"))
        self.assertEqual(result["per_firm"]["philips"]["observations"], 1)
        self.assertEqual(result["per_firm"]["medtronic"]["observations"], 1)
        self.assertEqual(result["per_firm"]["draeger"]["observations"], 0)


class EvaluabilityTest(unittest.TestCase):
    def matrix(self, observations, quarters):
        return [{"company": "x", "domain": "d", "observations_in_window": observations,
                 "quarters_with_observation": quarters}]

    def test_cell_above_both_floors_is_evaluable(self):
        result = evaluability(self.matrix(50, 20), min_observations=40, min_quarters=12)
        self.assertEqual(result["counts"]["evaluable"], 1)

    def test_cell_below_one_floor_is_not_evaluable_with_a_reason(self):
        result = evaluability(self.matrix(50, 3), min_observations=40, min_quarters=12)
        self.assertEqual(result["counts"]["evaluable"], 0)
        self.assertIn("below floors", result["not_evaluable"][0]["reason"])

    def test_empty_cell_reports_no_observations(self):
        result = evaluability(self.matrix(0, 0), min_observations=40, min_quarters=12)
        self.assertIn("no observations", result["not_evaluable"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
