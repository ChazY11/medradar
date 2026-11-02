"""Tests for the lead/lag pairing logic (Phase 1 A2)."""
from __future__ import annotations

import unittest
from datetime import date

from medradar.studies.pairing import (
    describe_leads,
    gate,
    lead_quarters,
    pair_first_subsequent,
)


def record(day: str, identifier: str = "e") -> dict:
    return {"date": date.fromisoformat(day), "event_id": identifier}


class LeadQuartersTest(unittest.TestCase):
    def test_one_quarter(self):
        self.assertAlmostEqual(lead_quarters(date(2021, 4, 1), date(2021, 1, 1)), 0.99, places=2)

    def test_zero_and_negative(self):
        self.assertEqual(lead_quarters(date(2021, 1, 1), date(2021, 1, 1)), 0.0)
        self.assertLess(lead_quarters(date(2020, 12, 1), date(2021, 1, 1)), 0)


class PairingTest(unittest.TestCase):
    def test_first_subsequent_event_is_used(self):
        result = pair_first_subsequent([record("2020-01-01")],
                                       [record("2020-12-01", "a"), record("2020-09-01", "b")])
        self.assertEqual(result["n_pairs"], 1)
        self.assertEqual(result["pairs"][0]["later_id"], "b")

    def test_multiplicity_is_reported_not_hidden(self):
        result = pair_first_subsequent([record("2020-01-01")],
                                       [record("2020-09-01", "a"), record("2020-10-01", "b"),
                                        record("2020-11-01", "c")])
        self.assertEqual(result["multiplicity_skipped"], 2)

    def test_lead_shorter_than_the_floor_goes_to_below_threshold(self):
        result = pair_first_subsequent([record("2020-01-01")], [record("2020-02-01")])
        self.assertEqual(result["n_pairs"], 0)
        self.assertEqual(result["n_below_threshold"], 1)

    def test_no_later_event_is_unpaired_not_a_false_negative(self):
        result = pair_first_subsequent([record("2020-01-01")], [record("2019-01-01")])
        self.assertEqual(result["n_pairs"], 0)
        self.assertEqual(result["n_below_threshold"], 0)
        self.assertEqual(result["n_unpaired"], 1)

    def test_lag_shift_can_remove_a_pair(self):
        earlier, later = [record("2020-01-01")], [record("2020-09-01")]
        self.assertEqual(pair_first_subsequent(earlier, later, lag_days=0)["n_pairs"], 1)
        shifted = pair_first_subsequent(earlier, later, lag_days=250)
        self.assertEqual(shifted["n_pairs"], 0)
        self.assertEqual(shifted["n_unpaired"], 1)

    def test_empty_scope_is_handled(self):
        result = pair_first_subsequent([], [])
        self.assertEqual(result["n_pairs"], 0)
        self.assertEqual(result["n_unpaired"], 0)


class DescribeTest(unittest.TestCase):
    def test_quartiles_of_a_small_set(self):
        summary = describe_leads([{"lead_quarters": 2.0}, {"lead_quarters": 4.0},
                                  {"lead_quarters": 6.0}])
        self.assertEqual(summary["n"], 3)
        self.assertEqual(summary["median"], 4.0)
        self.assertEqual(summary["min"], 2.0)
        self.assertEqual(summary["max"], 6.0)

    def test_empty_summary_has_no_fake_median(self):
        self.assertIsNone(describe_leads([])["median"])


class GateTest(unittest.TestCase):
    def test_go_requires_both_pairs_and_firms(self):
        self.assertEqual(gate({"0": 12}, {"0": ["a", "b"]})["verdict"], "GO")

    def test_too_few_pairs_is_no_go(self):
        self.assertEqual(gate({"0": 3}, {"0": ["a", "b"]})["verdict"], "NO-GO")

    def test_too_few_firms_is_no_go(self):
        self.assertEqual(gate({"0": 12}, {"0": ["a"]})["verdict"], "NO-GO")

    def test_zero_pairs_is_not_evaluable(self):
        self.assertEqual(gate({"0": 0}, {"0": []})["verdict"], "NOT_EVALUABLE")


if __name__ == "__main__":
    unittest.main()
