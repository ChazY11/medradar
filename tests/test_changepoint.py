"""Offline, deterministic tests for the OBSERVE-layer change-point detectors.

Everything here is synthetic and hand-written: no database, no ``data/`` file, no
network, no clock and no random seed.  The streams mirror the shape of the real
MedRadar cells (monthly counts, 120 months, ~78% zero months) so that a test
failure means the detector itself is wrong, not the fixture.

These are not smoke tests.  Between them the cases pin down the properties that
break in practice:

* a detector that returns ``[]`` unconditionally passes every "no detection"
  test and fails the step-change test;
* a detector that always declares passes the step-change test and fails the
  degenerate, sparse and stable-stream tests;
* a detector that ignores its threshold/multiplier/window fails the guard tests;
* a detector that looks ahead and declares a change *before* the onset fails
  ``test_declaration_never_precedes_onset`` (this is the single most tempting
  bug in a retrospective harness);
* a detector that flags a 3x one-month bump as a regime change fails
  ``test_moderate_spike_is_absorbed``;
* a detector that misses the difference between a sustained shift and a
  one-month burst fails one of the two spike tests.

A detection is a statistical statement about the rate of public regulatory
events in a cell; nothing here is a claim about intent or capability.
"""
from __future__ import annotations

import math
import unittest

from medradar.intelligence import changepoint

# --------------------------------------------------------------------- fixtures
BASELINE_RATE = 2          # events/month before the step
ONSET = 48                 # first month of the step
POST_RATE = 10             # events/month after the step (+5x)
POST_MONTHS = 12


def month_labels(count: int) -> list[str]:
    """Consecutive ``YYYY-MM`` labels starting 2016-11 (same shape as the corpus)."""
    labels = []
    for offset in range(count):
        total = 2016 * 12 + 10 + offset
        labels.append(f"{total // 12:04d}-{total % 12 + 1:02d}")
    return labels


def stream_of(counts: list[int]) -> list[tuple[str, int]]:
    return list(zip(month_labels(len(counts)), counts))


def step_counts(baseline: int = BASELINE_RATE, onset: int = ONSET,
                post: int = POST_RATE, after: int = POST_MONTHS) -> list[int]:
    """A clean +5x level shift: flat baseline, flat post-change level, no noise."""
    return [baseline] * onset + [post] * after


STEP_STREAM = stream_of(step_counts())
STEP_COUNTS = [count for _date, count in STEP_STREAM]

#: 120-month sparse cell: 17 isolated single filings, no two in a row.  This is
#: the shape of a real eligible cell (median 24 events over 120 months).
SPARSE_COUNTS = [0] * 120
for _index in (3, 11, 18, 26, 31, 39, 47, 52, 60, 67, 74, 81, 88, 95, 103, 110, 117):
    SPARSE_COUNTS[_index] = 1
SPARSE_STREAM = stream_of(SPARSE_COUNTS)

#: Same cell with one three-filing month: a burst, not a regime change.
BURST_COUNTS = list(SPARSE_COUNTS)
BURST_COUNTS[60] = 3
BURST_STREAM = stream_of(BURST_COUNTS)

#: Hand-written stationary stream around 3 events/month; no trend, no change.
STABLE_COUNTS = [
    2, 3, 4, 2, 3, 3, 2, 4, 3, 3, 2, 3, 4, 3, 2, 3, 3, 4, 2, 3,
    3, 3, 2, 4, 3, 3, 2, 3, 4, 3, 3, 2, 3, 3, 4, 2, 3, 3, 3, 2,
    4, 3, 3, 2, 3, 4, 3, 3, 2, 3, 3, 4, 3, 2, 3, 3, 3, 4, 2, 3,
]
STABLE_STREAM = stream_of(STABLE_COUNTS)

#: Downward step: 2 events/month for 48 months, then nothing.
DOWN_STREAM = stream_of([BASELINE_RATE] * ONSET + [0] * POST_MONTHS)

#: One single-month spike of 30 events at the onset, baseline 1/month.
SPIKE_STREAM = stream_of([1] * ONSET + [30] + [1] * (POST_MONTHS - 1))

#: One single-month spike of 3x the baseline: below any sensible resolution.
MODERATE_SPIKE_STREAM = stream_of([1] * ONSET + [3] + [1] * (POST_MONTHS - 1))

#: A very short stream whose clean pre-jump history has one event, then a jump.
SHORT_BASELINE_STREAM = stream_of([0, 0, 1, 0, 0, 0, 0, 0, 20, 20])

DETECTORS = changepoint.DETECTORS

UP_ONLY = ("naive_multiplier", "poisson_cusum")
TWO_SIDED = ("rolling_zscore", "poisson_bayes_factor")


def rates_before_and_after(stream: list[tuple[str, int]], index: int) -> tuple[float, float]:
    """The contract definition of the reporting fields, computed independently."""
    counts = [count for _date, count in stream]
    before = counts[:index]
    after = counts[index:]
    before_rate = (sum(before) / len(before)) if before else 0.0
    after_rate = (sum(after) / len(after)) if after else 0.0
    return before_rate, after_rate


def all_detections(stream: list[tuple[str, int]], **kwargs):
    """``(name, detection-list)`` for every registered detector."""
    return [(name, function(stream, **kwargs)) for name, function in DETECTORS.items()]


# ------------------------------------------------------------------- registry
class TestDetectorRegistry(unittest.TestCase):
    def test_exact_detector_names(self):
        self.assertEqual(
            sorted(DETECTORS),
            ["naive_multiplier", "poisson_bayes_factor", "poisson_cusum", "rolling_zscore"],
        )

    def test_registry_maps_to_the_documented_functions(self):
        self.assertIs(DETECTORS["naive_multiplier"], changepoint.detect_naive_threshold)
        self.assertIs(DETECTORS["rolling_zscore"], changepoint.detect_rolling_zscore)
        self.assertIs(DETECTORS["poisson_cusum"], changepoint.detect_poisson_cusum)
        self.assertIs(DETECTORS["poisson_bayes_factor"],
                      changepoint.detect_poisson_bayes_factor)
        for name, function in DETECTORS.items():
            self.assertTrue(callable(function), name)


# -------------------------------------------------------------------- degenerate
class TestDegenerateInputs(unittest.TestCase):
    def test_empty_stream(self):
        for name, detections in all_detections([]):
            self.assertEqual(detections, [], name)

    def test_single_point(self):
        for name, detections in all_detections([("2016-11", 5)]):
            self.assertEqual(detections, [], name)

    def test_two_points(self):
        for name, detections in all_detections(stream_of([3, 4])):
            self.assertEqual(detections, [], name)

    def test_all_zero_stream(self):
        # No rate exists to compare: every detector must stay silent, not raise.
        for name, detections in all_detections(stream_of([0] * 120)):
            self.assertEqual(detections, [], name)

    def test_malformed_rows_return_empty_not_exception(self):
        bad_streams = {
            "negative count": [("2016-11", 1), ("2016-12", -1)],
            "fractional count": [("2016-11", 1), ("2016-12", 1.5)],
            "non-numeric count": [("2016-11", 1), ("2016-12", "many")],
            "non-string date": [(2016, 1), (2017, 2)],
            "wrong row length": [("2016-11", 1, 2), ("2016-12", 2)],
            "not a pair": [("2016-11", 1), 5],
            "none stream": None,
            "all zero and malformed": [("2016-11", 0), ("2016-12", -2)],
        }
        for label, bad in bad_streams.items():
            for name, function in DETECTORS.items():
                with self.subTest(case=label, detector=name):
                    self.assertEqual(function(bad), [])

    def test_stream_with_too_few_total_events(self):
        # 100 months, two events in total: no detector may call that a baseline.
        counts = [0] * 100
        counts[20], counts[90] = 1, 1
        for name, detections in all_detections(stream_of(counts)):
            self.assertEqual(detections, [], name)

    def test_short_baseline_returns_no_detection(self):
        # Explicit contract case: only one event of clean history before a jump.
        for name, detections in all_detections(SHORT_BASELINE_STREAM):
            self.assertEqual(detections, [], name)

    def test_invalid_parameters_return_empty(self):
        cases = {
            "naive_multiplier": (changepoint.detect_naive_threshold, {"multiplier": 0.0}),
            "naive_min_baseline": (changepoint.detect_naive_threshold,
                                   {"min_baseline_events": 0}),
            "zscore_threshold": (changepoint.detect_rolling_zscore, {"threshold": 0.0}),
            "zscore_window": (changepoint.detect_rolling_zscore, {"window": 1}),
            "zscore_events": (changepoint.detect_rolling_zscore, {"min_window_events": 0}),
            "cusum_threshold": (changepoint.detect_poisson_cusum, {"threshold": -1.0}),
            "cusum_drift": (changepoint.detect_poisson_cusum, {"drift": 0.0}),
            "cusum_window": (changepoint.detect_poisson_cusum, {"baseline_window": 0}),
            "bayes_threshold": (changepoint.detect_poisson_bayes_factor, {"threshold": 0.0}),
            "bayes_prior_shape": (changepoint.detect_poisson_bayes_factor,
                                  {"prior_shape": 0.0}),
            "bayes_prior_rate": (changepoint.detect_poisson_bayes_factor,
                                 {"prior_rate": -2.0}),
            "bayes_baseline_events": (changepoint.detect_poisson_bayes_factor,
                                      {"min_baseline_events": 0}),
        }
        for label, (function, kwargs) in cases.items():
            with self.subTest(case=label):
                self.assertEqual(function(STEP_STREAM, **kwargs), [])


# ----------------------------------------------------------------------- sparse
class TestSparseStreams(unittest.TestCase):
    def test_realistic_sparse_stream_produces_no_detection(self):
        # Required case: mostly zeros with occasional 1s, exactly the real corpus
        # shape.  A detector that fires here would fire on most of the company x
        # track grid, which is useless.
        self.assertEqual(sum(SPARSE_COUNTS), 17)
        for name, detections in all_detections(SPARSE_STREAM):
            self.assertEqual(detections, [], name)

    def test_isolated_burst_in_sparse_stream_produces_no_detection(self):
        # A single three-filing month in an otherwise quiet cell is a burst, not
        # a regime change; all four detectors must absorb it.
        for name, detections in all_detections(BURST_STREAM):
            self.assertEqual(detections, [], name)

    def test_dry_spell_after_activity_is_not_an_up_change(self):
        # A cell that stops filing for two years and then files once: the
        # two-sided detectors may (correctly) call the cessation a *decrease*,
        # but a single filing after the lull must never be called an increase.
        counts = list(STABLE_COUNTS[:30]) + [0] * 24 + [1] + [0] * 5
        for name, detections in all_detections(stream_of(counts)):
            with self.subTest(detector=name):
                for detection in detections:
                    self.assertNotEqual(detection["direction"], "up")


# ----------------------------------------------------------------------- stable
class TestStableStreams(unittest.TestCase):
    def test_stable_high_rate_stream_produces_no_detection(self):
        self.assertLess(abs(sum(STABLE_COUNTS) / len(STABLE_COUNTS) - 3.0), 0.2)
        for name, detections in all_detections(STABLE_STREAM):
            self.assertEqual(detections, [], name)

    def test_modest_rate_increase_is_not_declared(self):
        # +50% and +100% sustained shifts are real but small; at the default
        # thresholds the naive comparator and the Bayes factor must not claim
        # them (the CUSUM's whole purpose is to be sensitive to ~+50% shifts, so
        # it is allowed to detect the +100% case -- not asserted either way).
        for shift_board in ([3] * POST_MONTHS, [4] * POST_MONTHS):
            for name in ("naive_multiplier", "poisson_bayes_factor"):
                with self.subTest(post_rate=shift_board[0], detector=name):
                    detections = DETECTORS[name](stream_of([BASELINE_RATE] * ONSET + shift_board))
                    self.assertEqual(detections, [], name)


# ------------------------------------------------------------------ step change
class TestStepChange(unittest.TestCase):
    def test_every_detector_declares_an_upward_change(self):
        for name, detections in all_detections(STEP_STREAM):
            self.assertEqual(len(detections), 1, name)
            self.assertEqual(detections[0]["direction"], "up", name)

    def test_declaration_never_precedes_the_onset(self):
        # The single most important property for a retrospective harness: a
        # detector must not look ahead and date the change before it happened.
        for name, detections in all_detections(STEP_STREAM):
            self.assertGreaterEqual(detections[0]["index"], ONSET, name)

    def test_latency_is_a_few_months(self):
        for name, detections in all_detections(STEP_STREAM):
            delay = detections[0]["index"] - ONSET
            self.assertLessEqual(delay, 4, f"{name} delay={delay}")

    def test_statistic_crosses_the_declared_threshold(self):
        for name, detections in all_detections(STEP_STREAM):
            detection = detections[0]
            self.assertIsInstance(detection["statistic"], float, name)
            self.assertIsInstance(detection["threshold"], float, name)
            if name in TWO_SIDED:
                self.assertGreater(abs(detection["statistic"]), detection["threshold"], name)
            else:
                self.assertGreater(detection["statistic"], detection["threshold"], name)

    def test_three_and_a_half_x_shift_is_detected_by_the_naive_comparator(self):
        # Sanity that the six-event floor is not so high that ordinary sustained
        # shifts disappear: 2 -> 7 events/month is a 3.5x step, above the
        # multiplier-3 rule the comparator implements.
        detections = DETECTORS["naive_multiplier"](
            stream_of([BASELINE_RATE] * ONSET + [7] * POST_MONTHS))
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0]["direction"], "up")


# -------------------------------------------------------------- downward change
class TestDownwardChange(unittest.TestCase):
    def test_one_sided_detectors_stay_silent(self):
        # Documented behaviour: the naive comparator and the CUSUM are one-sided
        # rate-increase detectors, so a decrease is not their business.
        for name in UP_ONLY:
            self.assertEqual(DETECTORS[name](DOWN_STREAM), [], name)

    def test_two_sided_detectors_declare_a_downward_change(self):
        for name in TWO_SIDED:
            detections = DETECTORS[name](DOWN_STREAM)
            self.assertEqual(len(detections), 1, name)
            self.assertEqual(detections[0]["direction"], "down", name)
            self.assertGreaterEqual(detections[0]["index"], ONSET, name)

    def test_no_detector_claims_an_upward_change(self):
        for name, detections in all_detections(DOWN_STREAM):
            for detection in detections:
                self.assertNotEqual(detection["direction"], "up", name)


# --------------------------------------------------------------- spike behaviour
class TestSingleMonthSpike(unittest.TestCase):
    def test_large_spike_is_flagged_by_every_detector(self):
        # Documented false-positive case: a 30x one-month burst *is* a real
        # short-run rate increase, and every rate detector sees it.  This is a
        # limitation, not a bug -- persistence should be checked before acting.
        for name, detections in all_detections(SPIKE_STREAM):
            self.assertEqual(len(detections), 1, name)
            self.assertEqual(detections[0]["direction"], "up", name)

    def test_naive_zscore_cusum_localise_the_burst_to_its_month(self):
        for name in ("naive_multiplier", "rolling_zscore", "poisson_cusum"):
            self.assertEqual(DETECTORS[name](SPIKE_STREAM)[0]["index"], ONSET, name)

    def test_bayes_factor_change_point_cannot_localise_a_burst(self):
        # A one-month burst is not identifiable in a two-segment model: the
        # evidence is spread over the months before it, so the reported change
        # point can sit up to BAYES_INDEX_TOLERANCE months early.  Asserted so
        # the limitation is visible instead of discovered downstream.
        index = DETECTORS["poisson_bayes_factor"](SPIKE_STREAM)[0]["index"]
        self.assertGreaterEqual(index, ONSET - 3)
        self.assertLessEqual(index, ONSET)

    def test_moderate_spike_is_absorbed(self):
        for name, detections in all_detections(MODERATE_SPIKE_STREAM):
            self.assertEqual(detections, [], name)

    def test_observed_rate_is_diluted_by_the_reversion(self):
        # Reporting semantics: observed_rate is the mean at/after index, so a
        # transient spike reports a rate far below the spike itself.  This is how
        # a consumer can tell "sustained change" from "one bad month".
        detection = DETECTORS["naive_multiplier"](SPIKE_STREAM)[0]
        self.assertLess(detection["observed_rate"], 5.0)
        self.assertGreater(detection["observed_rate"], detection["baseline_rate"])


# ------------------------------------------------------------------------ scaling
class TestCountScaling(unittest.TestCase):
    def test_tenfold_count_scaling_preserves_detection(self):
        # Monotone scaling of a detected stream must not make the change vanish
        # (guards against accidental absolute-count thresholds).
        scaled = stream_of([10 * count for count in STEP_COUNTS])
        for name, detections in all_detections(scaled):
            self.assertEqual(len(detections), 1, name)
            self.assertEqual(detections[0]["direction"], "up", name)
            self.assertGreaterEqual(detections[0]["index"], ONSET - 1, name)


# ---------------------------------------------------------------------- reporting
class TestDetectionContract(unittest.TestCase):
    REQUIRED_KEYS = {"index", "date", "direction", "statistic", "threshold",
                     "baseline_rate", "observed_rate"}

    def test_keys_and_types(self):
        for name, detections in all_detections(STEP_STREAM):
            detection = detections[0]
            with self.subTest(detector=name):
                self.assertLessEqual(self.REQUIRED_KEYS, set(detection))
                self.assertIsInstance(detection["index"], int)
                self.assertIsInstance(detection["date"], str)
                self.assertIn(detection["direction"], {"up", "down"})
                for key in ("statistic", "threshold", "baseline_rate", "observed_rate"):
                    self.assertIsInstance(detection[key], float, key)
                    self.assertTrue(math.isfinite(detection[key]), key)
                self.assertGreaterEqual(detection["baseline_rate"], 0.0)
                self.assertGreaterEqual(detection["observed_rate"], 0.0)

    def test_index_date_and_rates_are_consistent(self):
        for name, detections in all_detections(STEP_STREAM):
            detection = detections[0]
            index = detection["index"]
            with self.subTest(detector=name):
                self.assertGreaterEqual(index, changepoint.MIN_BASELINE_MONTHS)
                self.assertLess(index, len(STEP_STREAM))
                self.assertEqual(detection["date"], STEP_STREAM[index][0])
                before, after = rates_before_and_after(STEP_STREAM, index)
                self.assertAlmostEqual(detection["baseline_rate"], before, places=12)
                self.assertAlmostEqual(detection["observed_rate"], after, places=12)
                self.assertGreater(detection["observed_rate"], detection["baseline_rate"])

    def test_at_most_one_detection_per_stream(self):
        for label, stream in (("step", STEP_STREAM), ("spike", SPIKE_STREAM),
                              ("down", DOWN_STREAM), ("stable", STABLE_STREAM)):
            for name, detections in all_detections(stream):
                with self.subTest(stream=label, detector=name):
                    self.assertLessEqual(len(detections), 1)


# ------------------------------------------------------------------ determinism
class TestDeterminismAndPurity(unittest.TestCase):
    def test_same_input_gives_identical_output(self):
        for name, function in DETECTORS.items():
            with self.subTest(detector=name):
                first = function(STEP_STREAM)
                second = function(STEP_STREAM)
                self.assertEqual(first, second)
                self.assertEqual(function(SPIKE_STREAM), function(SPIKE_STREAM))

    def test_input_stream_is_not_mutated(self):
        for name, function in DETECTORS.items():
            counts = step_counts()
            stream = stream_of(counts)
            snapshot = [(date, count) for date, count in stream]
            with self.subTest(detector=name):
                function(stream)
                self.assertEqual(stream, snapshot)
                self.assertEqual([count for _d, count in stream], counts)

    def test_accepts_a_tuple_of_tuples(self):
        # The contract says "list", the harness may hand over tuples; both are
        # read-only sequences and must behave identically.
        tuple_stream = tuple(STEP_STREAM)
        for name, function in DETECTORS.items():
            with self.subTest(detector=name):
                self.assertEqual(function(tuple_stream), function(STEP_STREAM))

    def test_integer_valued_float_counts_are_accepted(self):
        float_stream = [(date, float(count)) for date, count in STEP_STREAM]
        for name, function in DETECTORS.items():
            with self.subTest(detector=name):
                self.assertEqual(function(float_stream), function(STEP_STREAM))


# ------------------------------------------------------------------- guard rails
class TestParameterGuards(unittest.TestCase):
    def test_naive_multiplier_is_used(self):
        # A 1e9 multiplier cannot be crossed: proves the parameter is not ignored.
        self.assertEqual(
            changepoint.detect_naive_threshold(STEP_STREAM, multiplier=1e9), [])

    def test_zscore_threshold_is_used(self):
        self.assertEqual(
            changepoint.detect_rolling_zscore(STEP_STREAM, threshold=50.0), [])

    def test_cusum_threshold_is_used(self):
        self.assertEqual(
            changepoint.detect_poisson_cusum(STEP_STREAM, threshold=100.0), [])

    def test_bayes_threshold_is_used(self):
        self.assertEqual(
            changepoint.detect_poisson_bayes_factor(STEP_STREAM, threshold=100.0), [])

    def test_zscore_needs_two_full_windows(self):
        # 60-month step stream with a 40-month window: fewer than 2 full windows.
        self.assertEqual(
            changepoint.detect_rolling_zscore(STEP_STREAM, window=40), [])

    def test_naive_baseline_guard_is_used(self):
        self.assertEqual(
            changepoint.detect_naive_threshold(STEP_STREAM, min_baseline_events=1000), [])

    def test_cusum_baseline_window_below_two_months_gives_nothing(self):
        self.assertEqual(
            changepoint.detect_poisson_cusum(STEP_STREAM, baseline_window=1), [])

    def test_bayes_baseline_guard_is_used(self):
        self.assertEqual(
            changepoint.detect_poisson_bayes_factor(STEP_STREAM, min_baseline_events=1000), [])


if __name__ == "__main__":
    unittest.main()
