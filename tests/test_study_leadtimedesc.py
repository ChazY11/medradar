"""Tests for the nine-event lead-time description logic (frozen protocol: no intervals, conservative choice)."""
from __future__ import annotations

import unittest

from medradar.studies.leadtimedesc import (
    describe_leads,
    group_by_later,
    packet,
    representative,
    underpowered_statement,
    upper_bound,
)

PAIRS = [
    {"earlier_id": "t1", "earlier_date": "2020-01-01", "later_id": "c1", "lead_quarters": 4.0,
     "lead_days": 360},
    {"earlier_id": "t2", "earlier_date": "2020-06-01", "later_id": "c1", "lead_quarters": 2.0,
     "lead_days": 180},
    {"earlier_id": "t3", "earlier_date": "2020-10-01", "later_id": "c2", "lead_quarters": 1.0,
     "lead_days": 90},
]


class GroupingTest(unittest.TestCase):
    def test_pairs_collapse_to_distinct_later_events(self):
        grouped = group_by_later(PAIRS)
        self.assertEqual(len(grouped), 2)
        self.assertEqual(len(grouped["c1"]), 2)


class RepresentativeTest(unittest.TestCase):
    def test_representative_is_the_latest_trial(self):
        grouped = group_by_later(PAIRS)
        self.assertEqual(representative(grouped["c1"])["earlier_id"], "t2")

    def test_upper_bound_is_the_earliest_trial(self):
        grouped = group_by_later(PAIRS)
        self.assertEqual(upper_bound(grouped["c1"])["earlier_id"], "t1")


class DescribeTest(unittest.TestCase):
    def test_median_iqr_and_shares(self):
        summary = describe_leads([2.0, 1.0, 5.0])
        self.assertEqual(summary["n"], 3)
        self.assertEqual(summary["median"], 2.0)
        self.assertEqual(summary["range"], [1.0, 5.0])
        self.assertEqual(summary["share_ge_2q"], round(2 / 3, 3))

    def test_empty_summary_has_no_invented_numbers(self):
        summary = describe_leads([])
        self.assertIsNone(summary["median"])
        self.assertIsNone(summary["share_ge_1q"])


class StatementTest(unittest.TestCase):
    def test_statement_carries_count_and_floor(self):
        text = underpowered_statement(9)
        self.assertIn("n = 9", text)
        self.assertIn("floor of 10", text)
        self.assertIn("not a lead-time estimate", text)


class PacketTest(unittest.TestCase):
    def test_packet_is_unlabelled_and_asks_the_review_questions(self):
        grouped = group_by_later(PAIRS)
        entry = packet(event_id="E1", company="philips", track="respiratory", clearance_id="c1",
                       clearance_date="2021-01-01", clearance_kind="510k",
                       representative_pair=representative(grouped["c1"]),
                       candidates=grouped["c1"], matched_keywords=["VENTILATOR"])
        self.assertEqual(entry["human_review_status"], "PENDING_HUMAN_REVIEW")
        self.assertIsNone(entry["final_label"])
        self.assertEqual(entry["candidate_trials"], 2)
        self.assertEqual(entry["lead_quarters"], 2.0)
        self.assertEqual(len(entry["review_questions"]), 4)


if __name__ == "__main__":
    unittest.main()
