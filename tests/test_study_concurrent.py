"""Tests for the O1 concurrent-detection logic (PHASE1B_PROTOCOL.md)."""
from __future__ import annotations

import unittest

from medradar.studies.concurrent import (
    calibrate_threshold,
    counts_by_quarter,
    evaluate,
    fuse,
    quarter_index,
    quarter_label,
    rolling_zscore,
    split_window,
    sustained_onsets,
    wilson_interval,
)


def quarters(start: str, count: int) -> list[str]:
    first = quarter_index(start)
    return [quarter_label(first + offset) for offset in range(count)]


def series(start: str, values: list[int]) -> dict[str, int]:
    return dict(zip(quarters(start, len(values)), values))


class QuarterTest(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(quarter_label(quarter_index("2024-Q3")), "2024-Q3")

    def test_ordering(self):
        self.assertLess(quarter_index("2021-Q4"), quarter_index("2022-Q1"))

    def test_quarters_helper_is_contiguous(self):
        self.assertEqual(quarters("2020-Q4", 3), ["2020-Q4", "2021-Q1", "2021-Q2"])


class OnsetTest(unittest.TestCase):
    def test_two_events_after_silence_is_an_onset(self):
        # 2019 one event, then silence through 2020, then a two-event episode inside 2021; the 2022 marker makes
        # the 2021 episode window fully observed (otherwise it is censored, not negative)
        data = {"2019-Q1": 1, "2021-Q1": 1, "2021-Q3": 1, "2022-Q2": 0}
        result = sustained_onsets(data)
        self.assertIn("2021-Q1", result["onsets"])

    def test_single_event_is_not_an_onset(self):
        data = {"2019-Q1": 1, "2021-Q1": 1}
        self.assertEqual(sustained_onsets(data)["onsets"], [])

    def test_activity_just_before_the_window_blocks_an_onset(self):
        # one event every quarter means the track was never silent
        data = series("2020-Q1", [1] * 8)
        self.assertEqual(sustained_onsets(data)["onsets"], [])

    def test_immature_episode_is_censored_not_negative(self):
        data = {"2019-Q1": 1, "2021-Q4": 1, "2022-Q1": 1}
        result = sustained_onsets(data)
        self.assertTrue(result["censored"])

    def test_episode_consumes_its_window(self):
        data = {"2019-Q1": 1, "2021-Q1": 1, "2021-Q2": 1, "2023-Q1": 1, "2023-Q2": 1}
        result = sustained_onsets(data)
        self.assertEqual(result["onsets"], ["2021-Q1"])


class ZScoreTest(unittest.TestCase):
    def test_flat_series_has_no_signal(self):
        scores = rolling_zscore(series("2018-Q1", [1] * 12))
        self.assertTrue(scores)
        self.assertTrue(all(abs(value) < 1e-9 for value in scores.values()))

    def test_jump_is_detected(self):
        scores = rolling_zscore(series("2018-Q1", [1] * 8 + [9]))
        last = quarters("2018-Q1", 9)[-1]
        self.assertGreater(scores[last], 3.0)

    def test_zero_baseline_is_infinite_not_fabricated(self):
        scores = rolling_zscore(series("2018-Q1", [0] * 8 + [1]))
        last = quarters("2018-Q1", 9)[-1]
        self.assertEqual(scores[last], float("inf"))


class CalibrationTest(unittest.TestCase):
    def test_threshold_meets_the_budget(self):
        scores = {"2020-Q1": 5.0, "2020-Q2": 0.0, "2020-Q3": 0.0}
        result = calibrate_threshold(scores, ["2020-Q1"], positives=1, negatives=2, years=1.0,
                                     budget_per_company_year=2.0)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["calibration_false_alerts"], 0)

    def test_unreachable_budget_is_not_evaluable(self):
        scores = {"2020-Q1": 5.0, "2020-Q2": 5.0, "2020-Q3": 5.0}
        result = calibrate_threshold(scores, ["2020-Q1"], positives=1, negatives=2, years=0.1,
                                     budget_per_company_year=0.1)
        self.assertEqual(result["status"], "NOT_EVALUABLE")
        self.assertIsNone(result["threshold"])


class EvaluateTest(unittest.TestCase):
    def test_alert_on_the_onset_quarter_is_a_hit(self):
        result = evaluate({"2022-Q1": 4.0, "2022-Q2": 0.0}, ["2022-Q1"], threshold=3.0, years=1.0)
        self.assertEqual(result["hits"], 1)
        self.assertEqual(result["false_alerts"], 0)
        self.assertAlmostEqual(result["recall"], 1.0)

    def test_alert_one_quarter_late_still_counts(self):
        result = evaluate({"2022-Q2": 4.0}, ["2022-Q1"], threshold=3.0, years=1.0, slack=1)
        self.assertEqual(result["hits"], 1)

    def test_alert_two_quarters_late_is_a_false_alert(self):
        result = evaluate({"2022-Q3": 4.0}, ["2022-Q1"], threshold=3.0, years=1.0, slack=1)
        self.assertEqual(result["hits"], 0)
        self.assertEqual(result["false_alerts"], 1)

    def test_recall_is_none_without_positives(self):
        self.assertIsNone(evaluate({"2022-Q1": 4.0}, [], threshold=3.0, years=1.0)["recall"])


class WilsonTest(unittest.TestCase):
    def test_interval_contains_the_point_estimate(self):
        low, high = wilson_interval(3, 10)
        self.assertLessEqual(low, 0.3)
        self.assertGreaterEqual(high, 0.3)

    def test_zero_total_is_maximally_uncertain(self):
        self.assertEqual(wilson_interval(0, 0), [0.0, 1.0])


class FusionTest(unittest.TestCase):
    def test_takes_the_maximum(self):
        fused = fuse({"2022-Q1": 1.0, "2022-Q2": 5.0}, {"2022-Q1": 4.0})
        self.assertEqual(fused["2022-Q1"], 4.0)
        self.assertEqual(fused["2022-Q2"], 5.0)

    def test_infinite_signal_propagates(self):
        self.assertEqual(fuse({"2022-Q1": float("inf")}, {})["2022-Q1"], float("inf"))


class SplitTest(unittest.TestCase):
    def test_split_is_by_quarter_label(self):
        result = split_window(["2021-Q4", "2022-Q1"], split="2022-Q1")
        self.assertEqual(result["calibration"], ["2021-Q4"])
        self.assertEqual(result["evaluation"], ["2022-Q1"])


class CountsTest(unittest.TestCase):
    def test_counts_aggregate_by_quarter(self):
        rows = [{"quarter": "2022-Q1"}, {"quarter": "2022-Q1"}, {"quarter": "2022-Q2"}]
        self.assertEqual(counts_by_quarter(rows), {"2022-Q1": 2, "2022-Q2": 1})


if __name__ == "__main__":
    unittest.main()


class SignAndHolmTest(unittest.TestCase):
    def test_sign_test_unanimous_small_sample(self):
        from medradar.studies.concurrent import sign_test_p
        self.assertAlmostEqual(sign_test_p(4, 0), 0.125, places=3)

    def test_sign_test_ties_are_caller_excluded(self):
        from medradar.studies.concurrent import sign_test_p
        self.assertEqual(sign_test_p(0, 0), 1.0)

    def test_holm_orders_and_caps(self):
        from medradar.studies.concurrent import holm
        result = holm({"a": 0.001, "b": 0.02, "c": 0.9})
        self.assertTrue(result["a"]["reject"])
        self.assertFalse(result["c"]["reject"])
        self.assertGreaterEqual(result["b"]["adjusted_p"], result["a"]["adjusted_p"])

    def test_holm_never_exceeds_one(self):
        from medradar.studies.concurrent import holm
        result = holm({"a": 0.9, "b": 0.95})
        self.assertTrue(all(entry["adjusted_p"] <= 1.0 for entry in result.values()))
