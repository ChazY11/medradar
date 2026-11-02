"""Tests for the point-process detection logic (Phase 1D)."""
from __future__ import annotations

import unittest

from medradar.studies.pointprocess import (
    calibrate_null,
    delay_days,
    detect_first_after,
    inject_rate_change,
    paired_bootstrap_median,
    quarterly_counts,
    quarterly_zscore_detector,
    rate_change_lr,
    times_from_intervals,
)


class LikelihoodRatioTest(unittest.TestCase):
    def test_homogeneous_sequence_has_small_statistic(self):
        times = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]
        self.assertLess(rate_change_lr(times)["statistic"], 6.0)

    def test_rate_increase_is_detected(self):
        times = [10.0, 20.0, 30.0, 40.0, 50.0, 51.0, 52.0, 53.0, 54.0, 55.0]
        result = rate_change_lr(times)
        self.assertGreater(result["statistic"], 6.0)
        self.assertIsNotNone(result["cut_index"])

    def test_mild_rate_increase_is_smaller_but_positive(self):
        times = [10.0, 20.0, 30.0, 40.0, 50.0, 53.0, 56.0, 59.0, 62.0, 65.0]
        self.assertGreater(rate_change_lr(times)["statistic"], 2.5)

    def test_too_short_sequence_is_safe(self):
        result = rate_change_lr([1.0, 2.0])
        self.assertEqual(result["statistic"], 0.0)
        self.assertIsNone(result["cut_index"])

    def test_flat_duplicate_times_do_not_crash(self):
        self.assertIsInstance(rate_change_lr([0.0, 0.0, 0.0, 0.0])["statistic"], float)


class CalibrationTest(unittest.TestCase):
    def test_threshold_is_positive_and_monotone_in_budget(self):
        loose = calibrate_null(40, 1000.0, false_alarm_per_run=0.20, simulations=400)
        strict = calibrate_null(40, 1000.0, false_alarm_per_run=0.05, simulations=400)
        self.assertGreater(loose["threshold"], 0)
        self.assertGreater(strict["threshold"], loose["threshold"])

    def test_short_sequence_has_no_threshold(self):
        self.assertIsNone(calibrate_null(3, 100.0)["threshold"])


class InjectionTest(unittest.TestCase):
    def test_injection_compresses_only_the_tail(self):
        intervals = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0]
        injected = inject_rate_change(intervals, change_index=3, multiplier=2.0)
        self.assertEqual(injected[:3], intervals[:3])
        self.assertEqual(injected[3:], [5.0, 5.0, 5.0])

    def test_times_are_cumulative(self):
        self.assertEqual(times_from_intervals([1.0, 2.0, 3.0]), [1.0, 3.0, 6.0])


class DetectionTest(unittest.TestCase):
    def test_detect_first_after_returns_a_time(self):
        times = [10.0, 20.0, 30.0, 40.0, 50.0, 53.0, 56.0, 59.0, 62.0, 65.0]
        detected = detect_first_after(times, threshold=3.0)
        self.assertIsNotNone(detected)

    def test_no_detection_returns_none(self):
        self.assertIsNone(detect_first_after([10.0, 20.0, 30.0], threshold=100.0))

    def test_delay_helpers(self):
        self.assertFalse(delay_days(None, 10.0, 100.0, 0)["detected"])
        result = delay_days(30.0, 10.0, 100.0, 4)
        self.assertEqual(result["delay_days"], 20.0)
        self.assertFalse(result["late_negative"])


class QuarterlyTest(unittest.TestCase):
    def test_counts_bin_into_quarters(self):
        counts = quarterly_counts([10.0, 20.0, 60.0, 90.0], 100.0, quarters=4)
        self.assertEqual(sum(counts), 4)

    def test_detector_finds_a_jump(self):
        counts = [1, 1, 1, 1, 1, 1, 1, 1, 9]
        self.assertEqual(quarterly_zscore_detector(counts)["alert_bin"], 8)

    def test_detector_reports_none_without_a_jump(self):
        self.assertIsNone(quarterly_zscore_detector([1] * 9)["alert_bin"])


class BootstrapTest(unittest.TestCase):
    def test_paired_bootstrap_uses_shared_cells(self):
        result = paired_bootstrap_median({"a": 10.0, "b": 20.0}, {"a": 5.0, "b": 25.0},
                                         resamples=200)
        self.assertEqual(result["cells"], 2)
        self.assertEqual(result["median_difference"], 0.0)

    def test_no_shared_cells(self):
        self.assertIsNone(paired_bootstrap_median({"a": 1.0}, {"b": 2.0})["median_difference"])


if __name__ == "__main__":
    unittest.main()


class EmpiricalThresholdTest(unittest.TestCase):
    def test_ties_do_not_inflate_the_rate(self):
        from medradar.studies.pointprocess import empirical_threshold, rate_above
        values = [0.0] * 90 + [5.0] * 10
        threshold = empirical_threshold(values, false_alarm_per_run=0.10)
        self.assertIsNotNone(threshold)
        self.assertLessEqual(rate_above(values, threshold), 0.10)

    def test_all_zero_statistics_are_safe(self):
        from medradar.studies.pointprocess import empirical_threshold
        self.assertEqual(empirical_threshold([0.0] * 20, false_alarm_per_run=0.10), 0.0)

    def test_empty_values_return_none(self):
        from medradar.studies.pointprocess import empirical_threshold
        self.assertIsNone(empirical_threshold([]))
