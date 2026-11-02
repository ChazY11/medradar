"""Offline, deterministic tests for the cluster-aware evaluation statistics.

Every fixture is synthetic and seeded: no test touches the network, a database or
``data/*.sqlite``.  The pathological cases the mission cares about (one positive,
all-tied scores, empty selection, a single cluster) are explicit tests rather than
untested branches.
"""
from __future__ import annotations

import math
import random
import unittest
from datetime import date

from medradar.intelligence import evalstats
from medradar.intelligence.evaluation.metrics import brier, ece, pr_auc
from medradar.stats import normal_ppf


def _clustered_fixture(n_clusters: int = 8, per_cluster: int = 6, seed: int = 3):
    """Rows that repeat company clusters; scorer A is informative, B is noise."""
    rng = random.Random(seed)
    labels: list[int] = []
    probs_a: list[float] = []
    probs_b: list[float] = []
    clusters: list[str] = []
    for cluster in range(n_clusters):
        company = f"company-{cluster}"
        for _ in range(per_cluster):
            label = 1 if rng.random() < 0.5 else 0
            labels.append(label)
            probs_a.append(min(0.999, max(0.001, 0.5 + 0.35 * (label - 0.5) + rng.gauss(0, 0.15))))
            probs_b.append(min(0.999, max(0.001, 0.5 + rng.gauss(0, 0.15))))
            clusters.append(company)
    return labels, probs_a, probs_b, clusters


def _lead_units() -> list[dict]:
    """Ten negatives plus five positives, including one never-detected unit."""
    units = []
    for index in range(10):
        units.append({
            "unit_id": f"n{index:02d}",
            "score_a": 0.10 + 0.05 * index,
            "score_b": 0.10 + 0.05 * index,
            "label": 0,
            "origin_date": "2025-01-01",
        })
    units.append({"unit_id": "p1", "score_a": 0.95, "score_b": 0.40, "label": 1,
                  "origin_date": "2025-01-01", "event_date": "2025-12-01"})
    units.append({"unit_id": "p2", "score_a": 0.90, "score_b": 0.65, "label": 1,
                  "origin_date": "2025-01-01", "event_date": "2025-04-01"})
    units.append({"unit_id": "p3", "score_a": 0.60, "score_b": 0.90, "label": 1,
                  "origin_date": "2025-01-01", "event_date": "2025-02-01"})
    units.append({"unit_id": "p4", "score_a": 0.85, "score_b": 0.30, "label": 1,
                  "origin_date": "2025-01-01", "event_date": None})
    units.append({"unit_id": "p5", "score_a": 0.80, "score_b": 0.20, "label": 1,
                  "origin_date": "2025-01-01", "event_date": "2025-06-01",
                  "censor_date": "2025-03-01"})
    return units


class AveragePrecisionDefinitionTests(unittest.TestCase):
    def test_reexports_the_canonical_implementation(self):
        # One definition only: the module aliases metrics.pr_auc, it does not fork it.
        self.assertIs(evalstats.average_precision, pr_auc)
        self.assertIs(evalstats.__dict__["average_precision"], pr_auc)

    def test_perfect_ranking_is_one(self):
        labels = [1, 1, 1, 0, 0, 0]
        probabilities = [0.99, 0.90, 0.80, 0.79, 0.50, 0.10]
        self.assertEqual(evalstats.average_precision(labels, probabilities), 1.0)
        self.assertEqual(
            evalstats.average_precision_weighted(labels, probabilities, [1] * len(labels)), 1.0)

    def test_random_scores_are_near_prevalence(self):
        rng = random.Random(11)
        n, positives = 2000, 200
        labels = [1] * positives + [0] * (n - positives)
        probabilities = [rng.random() for _ in range(n)]
        value = evalstats.average_precision(labels, probabilities)
        self.assertAlmostEqual(value, positives / n, delta=0.05)

    def test_all_tied_scores_give_prevalence(self):
        labels = [1, 0, 1, 0, 0, 1, 0, 0]
        probabilities = [0.5] * len(labels)
        self.assertAlmostEqual(evalstats.average_precision(labels, probabilities),
                               sum(labels) / len(labels))

    def test_one_positive_is_defined(self):
        rng = random.Random(5)
        labels = [0] * 19 + [1]
        probabilities = [rng.random() for _ in range(20)]
        value = evalstats.average_precision(labels, probabilities)
        self.assertIsNotNone(value)
        self.assertTrue(0.0 <= value <= 1.0)
        self.assertAlmostEqual(
            evalstats.average_precision_weighted(labels, probabilities, [1] * 20), value)

    def test_weighted_matches_materialised_duplicates(self):
        rng = random.Random(17)
        labels = [int(rng.random() < 0.4) for _ in range(30)]
        labels[3] = labels[4] = 1  # guarantee both classes and some ties
        probabilities = [round(rng.random(), 1) for _ in range(30)]  # deliberate ties
        weights = [rng.choice([0, 1, 2, 3]) for _ in range(30)]
        if not any(weights):
            weights[0] = 1
        materialised_labels: list[int] = []
        materialised_probabilities: list[float] = []
        for label, probability, weight in zip(labels, probabilities, weights):
            materialised_labels.extend([label] * weight)
            materialised_probabilities.extend([probability] * weight)
        expected = evalstats.average_precision(materialised_labels, materialised_probabilities)
        self.assertAlmostEqual(
            evalstats.average_precision_weighted(labels, probabilities, weights), expected, places=12)

    def test_zero_weights_and_undefined_classes(self):
        self.assertIsNone(evalstats.average_precision_weighted([0, 1], [0.2, 0.8], [0, 0]))
        self.assertIsNone(evalstats.average_precision_weighted([0, 0], [0.2, 0.8], [1, 1]))
        with self.assertRaises(ValueError):
            evalstats.average_precision_weighted([0, 1], [0.2, 0.8], [1, -1])


class ClusterBootstrapDeltaApTests(unittest.TestCase):
    def test_reproducible_under_fixed_seed(self):
        labels, probs_a, probs_b, clusters = _clustered_fixture()
        first = evalstats.clustered_bootstrap_delta_ap(
            labels, probs_a, probs_b, clusters, resamples=300, seed=7)
        second = evalstats.clustered_bootstrap_delta_ap(
            labels, probs_a, probs_b, clusters, resamples=300, seed=7)
        self.assertEqual(first, second)
        self.assertEqual(first["n_clusters"], 8)
        self.assertEqual(first["n_positives"], sum(labels))
        self.assertGreater(first["valid_resamples"], 0)
        self.assertLessEqual(first["ci_low"], first["ci_high"])
        self.assertAlmostEqual(first["delta"], pr_auc(labels, probs_a) - pr_auc(labels, probs_b))

    def test_clusters_are_the_sampling_unit(self):
        labels, probs_a, probs_b, clusters = _clustered_fixture()
        clustered = evalstats.clustered_bootstrap_delta_ap(
            labels, probs_a, probs_b, clusters, resamples=300, seed=7)
        iid = evalstats.clustered_bootstrap_delta_ap(
            labels, probs_a, probs_b, None, resamples=300, seed=7)
        self.assertEqual(clustered["cluster_method"], "cluster")
        self.assertEqual(iid["cluster_method"], "iid_row")
        self.assertEqual(iid["n_clusters"], len(labels))
        self.assertLess(clustered["n_clusters"], iid["n_clusters"])

    def test_different_seed_changes_the_interval(self):
        labels, probs_a, probs_b, clusters = _clustered_fixture()
        first = evalstats.clustered_bootstrap_delta_ap(
            labels, probs_a, probs_b, clusters, resamples=500, seed=1)
        second = evalstats.clustered_bootstrap_delta_ap(
            labels, probs_a, probs_b, clusters, resamples=500, seed=2)
        self.assertNotEqual((first["ci_low"], first["ci_high"]),
                            (second["ci_low"], second["ci_high"]))

    def test_single_cluster_has_no_interval(self):
        labels = [1, 0, 1, 0, 1, 0]
        probs_a = [0.9, 0.8, 0.7, 0.6, 0.4, 0.2]
        probs_b = [0.5] * 6
        result = evalstats.clustered_bootstrap_delta_ap(
            labels, probs_a, probs_b, ["only"] * 6, resamples=50, seed=7)
        self.assertEqual(result["n_clusters"], 1)
        self.assertIsNone(result["ci_low"])
        self.assertIsNone(result["ci_high"])
        self.assertIn("note", result)
        self.assertIsNotNone(result["delta"])

    def test_all_tied_scores_give_a_zero_delta(self):
        labels = [1, 0, 1, 0, 1, 0, 1, 0]
        tied = [0.5] * len(labels)
        result = evalstats.clustered_bootstrap_delta_ap(
            labels, tied, tied, ["a", "a", "b", "b", "c", "c", "d", "d"], resamples=100, seed=7)
        self.assertEqual(result["delta"], 0.0)
        self.assertEqual(result["ci_low"], 0.0)
        self.assertEqual(result["ci_high"], 0.0)

    def test_empty_input(self):
        result = evalstats.clustered_bootstrap_delta_ap([], [], [], [], resamples=50, seed=7)
        self.assertEqual(result["n_rows"], 0)
        self.assertIsNone(result["delta"])
        self.assertIsNone(result["ci_low"])
        self.assertIn("note", result)

    def test_one_positive(self):
        labels = [1, 0, 0, 0, 0, 0, 0, 0]
        probs_a = [0.9, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        probs_b = [0.1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]
        result = evalstats.clustered_bootstrap_delta_ap(
            labels, probs_a, probs_b, ["a", "a", "b", "b", "c", "c", "d", "d"], resamples=100, seed=7)
        self.assertIsNotNone(result["delta"])
        self.assertLessEqual(result["ci_low"], result["ci_high"])

    def test_integration_alias_requires_clusters_and_returns_delta(self):
        labels, probs_a, probs_b, clusters = _clustered_fixture()
        with self.assertRaises(ValueError):
            evalstats.cluster_bootstrap_delta_ap(labels, probs_a, probs_b, None)
        result = evalstats.cluster_bootstrap_delta_ap(
            labels, probs_a, probs_b, clusters, resamples=200, seed=7)
        for key in ("delta", "ci_low", "ci_high", "valid_resamples", "n_clusters",
                    "n_positives", "p_delta_le_zero"):
            self.assertIn(key, result)
        self.assertEqual(
            result,
            evalstats.clustered_bootstrap_delta_ap(
                labels, probs_a, probs_b, clusters, resamples=200, seed=7))


class MetricBootstrapTests(unittest.TestCase):
    def test_brier_ci_matches_canonical_point(self):
        labels, probs_a, _, clusters = _clustered_fixture()
        result = evalstats.clustered_bootstrap_brier_ci(labels, probs_a, clusters, resamples=200, seed=7)
        self.assertAlmostEqual(result["point"], brier(labels, probs_a))
        self.assertEqual(result["metric"], "brier")
        self.assertLessEqual(result["ci_low"], result["ci_high"])
        self.assertEqual(result, evalstats.clustered_bootstrap_brier_ci(
            labels, probs_a, clusters, resamples=200, seed=7))

    def test_ece_ci_matches_canonical_point(self):
        labels, probs_a, _, clusters = _clustered_fixture()
        result = evalstats.clustered_bootstrap_ece_ci(labels, probs_a, clusters, resamples=200, seed=7)
        self.assertAlmostEqual(result["point"], ece(labels, probs_a))
        self.assertEqual(result["metric"], "ece")
        self.assertLessEqual(result["ci_low"], result["ci_high"])

    def test_single_cluster_metric_ci_has_no_interval(self):
        labels = [1, 0, 1, 0]
        probabilities = [0.9, 0.8, 0.2, 0.1]
        result = evalstats.clustered_bootstrap_metric_ci(
            labels, probabilities, ["only"] * 4, metric="brier", resamples=50, seed=7)
        self.assertIsNone(result["ci_low"])
        self.assertIsNone(result["ci_high"])
        self.assertIn("note", result)

    def test_generic_bootstrap_ci_metric(self):
        labels, probs_a, _, _ = _clustered_fixture()
        result = evalstats.bootstrap_ci_metric(brier, labels, probs_a, resamples=200, seed=7)
        self.assertAlmostEqual(result["point"], brier(labels, probs_a))
        self.assertLessEqual(result["ci_low"], result["ci_high"])
        self.assertEqual(result, evalstats.bootstrap_ci_metric(brier, labels, probs_a, resamples=200, seed=7))


class MinimumDetectableEffectTests(unittest.TestCase):
    def test_monotone_decreasing_in_positives_at_fixed_base_rate(self):
        # Same base rate, more positives and proportionally more rows.
        values = [evalstats.minimum_detectable_delta_ap(1000, 20, resamples=100, seed=7)["mde"],
                  evalstats.minimum_detectable_delta_ap(2000, 40, resamples=100, seed=7)["mde"],
                  evalstats.minimum_detectable_delta_ap(4000, 80, resamples=100, seed=7)["mde"],
                  evalstats.minimum_detectable_delta_ap(8000, 160, resamples=100, seed=7)["mde"]]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertGreater(values[0], values[-1])

    def test_analytic_formula_matches_plug_in_variance(self):
        result = evalstats.average_precision_mde(1000, 40, assumed_ap=0.2)
        expected_se = math.sqrt(2.0 * 0.2 * 0.8 / 40)
        self.assertAlmostEqual(result["se_delta_ap"], expected_se)
        z_alpha = normal_ppf(0.975)
        z_power = normal_ppf(0.8)
        self.assertAlmostEqual(result["mde_delta_ap"], (z_alpha + z_power) * expected_se)
        self.assertAlmostEqual(
            evalstats.mde_from_se(result["se_delta_ap"])["mde_delta_ap"], result["mde_delta_ap"])

    def test_mde_has_eighty_percent_power_by_design(self):
        result = evalstats.minimum_detectable_delta_ap(2000, 40, resamples=100)
        power = evalstats.power_at_delta(result["mde"], result["se"])
        self.assertAlmostEqual(power, 0.8, delta=1e-4)

    def test_conservative_bound_is_not_below_the_null_simulation(self):
        result = evalstats.average_precision_mde(41003, 503, resamples=200)
        self.assertIsNotNone(result["mde_delta_ap_null_simulation"])
        self.assertGreaterEqual(result["mde_delta_ap"], result["mde_delta_ap_null_simulation"])
        self.assertTrue(result["conservative"])

    def test_deterministic(self):
        first = evalstats.minimum_detectable_delta_ap(5000, 60, resamples=200, seed=7)
        second = evalstats.minimum_detectable_delta_ap(5000, 60, resamples=200, seed=7)
        self.assertEqual(first, second)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            evalstats.average_precision_mde(100, 0)
        with self.assertRaises(ValueError):
            evalstats.average_precision_mde(100, 100)
        with self.assertRaises(ValueError):
            evalstats.average_precision_mde(100, 10, assumed_ap=1.0)
        with self.assertRaises(ValueError):
            evalstats.average_precision_mde(100, 10, alpha=1.0)
        with self.assertRaises(ValueError):
            evalstats.mde_from_se(0.0)

    def test_synthetic_calibration_is_consistent(self):
        calibration = evalstats.ap_mde_calibration(
            240, 20, reps=40, bootstrap_resamples=100, search_reps=12, search_steps=6, seed=7)
        self.assertLess(calibration["null_se_ratio"], 2.0)
        self.assertGreater(calibration["null_se_ratio"], 0.5)
        self.assertTrue(calibration["target_effect_reached"])
        self.assertGreaterEqual(calibration["achieved_power"], calibration["target_power"] - 0.15)
        self.assertTrue(calibration["consistent"], calibration)


class MatchedFalseAlarmLeadTimeTests(unittest.TestCase):
    def test_matched_false_positive_count_and_rate(self):
        result = evalstats.matched_far_lead_time(_lead_units(), far=0.2)
        self.assertEqual(result["matched_false_positive_count"], 2)
        self.assertAlmostEqual(result["matched_false_alarm_rate"], 0.2)
        for name in ("score_a", "score_b"):
            self.assertEqual(result["scorers"][name]["false_positives"], 2)
            self.assertAlmostEqual(result["scorers"][name]["false_alarm_rate"], 0.2)

    def test_better_scorer_detects_more_and_earlier(self):
        result = evalstats.matched_far_lead_time(_lead_units(), far=0.2)
        scorer_a, scorer_b = result["scorers"]["score_a"], result["scorers"]["score_b"]
        self.assertEqual(scorer_a["true_positives"], 5)
        self.assertEqual(scorer_b["true_positives"], 2)
        self.assertGreater(scorer_a["detection_probability"], scorer_b["detection_probability"])
        self.assertGreater(scorer_a["lead_time"]["mean_lead_time_days"],
                           scorer_b["lead_time"]["mean_lead_time_days"])
        self.assertGreater(result["delta"]["mean_lead_time_days"], 0.0)
        self.assertGreater(result["delta"]["detection_probability"], 0.0)

    def test_censored_positives_are_reported_not_dropped(self):
        result = evalstats.matched_far_lead_time(_lead_units(), far=0.2)
        scorer_a = result["scorers"]["score_a"]
        # p4 has no event date and p5's event is after its censor date.
        self.assertEqual(result["positives_without_observable_lead"], 2)
        self.assertEqual(scorer_a["lead_time"]["censored_detected_positives"], 2)
        self.assertEqual(scorer_a["lead_time"]["observed_leads"], 3)
        self.assertAlmostEqual(scorer_a["lead_time"]["mean_lead_time_days"],
                               (334 + 90 + 31) / 3)
        self.assertAlmostEqual(result["max_detection_probability"], 0.6)

    def test_negative_lead_is_flagged(self):
        units = [
            {"unit_id": "n1", "score_a": 0.1, "score_b": 0.1, "label": 0,
             "origin_date": "2025-01-01"},
            {"unit_id": "n2", "score_a": 0.2, "score_b": 0.2, "label": 0,
             "origin_date": "2025-01-01"},
            {"unit_id": "p1", "score_a": 0.9, "score_b": 0.9, "label": 1,
             "origin_date": "2025-06-01", "event_date": "2025-01-01"},
        ]
        result = evalstats.matched_far_lead_time(units, far=0.0)
        self.assertEqual(result["scorers"]["score_a"]["lead_time"]["negative_lead_positives"], 1)
        self.assertEqual(result["scorers"]["score_a"]["lead_time"]["observed_leads"], 0)
        self.assertIsNone(result["scorers"]["score_a"]["lead_time"]["mean_lead_time_days"])

    def test_empty_selection(self):
        units = [
            {"unit_id": f"u{index}", "score_a": 0.5, "score_b": 0.5,
             "label": 1 if index == 0 else 0, "origin_date": "2025-01-01",
             "event_date": "2025-05-01" if index == 0 else None}
            for index in range(6)
        ]
        result = evalstats.matched_far_lead_time(units, far=0.0)
        scorer = result["scorers"]["score_a"]
        self.assertEqual(scorer["selected_units"], 0)
        self.assertEqual(scorer["false_positives"], 0)
        self.assertIsNone(scorer["precision"])
        self.assertEqual(scorer["lead_time"]["observed_leads"], 0)
        self.assertIsNone(scorer["lead_time"]["mean_lead_time_days"])

    def test_single_positive(self):
        units = [
            {"unit_id": f"n{index}", "score_a": 0.1 * index, "score_b": 0.9 - 0.1 * index,
             "label": 0, "origin_date": "2025-01-01"}
            for index in range(6)
        ]
        units.append({"unit_id": "p", "score_a": 0.95, "score_b": 0.05, "label": 1,
                      "origin_date": "2025-01-01", "event_date": "2025-03-01"})
        result = evalstats.matched_far_lead_time(units, far=0.0)
        self.assertEqual(result["n_positives"], 1)
        self.assertEqual(result["scorers"]["score_a"]["detection_probability"], 1.0)
        self.assertEqual(result["scorers"]["score_b"]["detection_probability"], 0.0)
        self.assertEqual(result["scorers"]["score_a"]["lead_time"]["mean_lead_time_days"], 59)

    def test_probability_of_detection_curve_is_monotone(self):
        result = evalstats.matched_far_lead_time(
            _lead_units(), far=0.2, curve_fars=(0.0, 0.1, 0.2, 0.5, 1.0))
        curve = result["pod_curve"]
        self.assertEqual([entry["far_target"] for entry in curve], [0.0, 0.1, 0.2, 0.5, 1.0])
        for name in ("score_a", "score_b"):
            probabilities = [entry[name]["detection_probability"] for entry in curve]
            self.assertEqual(probabilities, sorted(probabilities))
        self.assertAlmostEqual(curve[-1]["score_b"]["false_alarm_rate"], 1.0)

    def test_no_negatives_raises(self):
        units = [{"unit_id": "p", "score_a": 0.9, "score_b": 0.8, "label": 1,
                  "origin_date": "2025-01-01", "event_date": "2025-03-01"}]
        with self.assertRaises(ValueError):
            evalstats.matched_far_lead_time(units, far=0.1)


class IntegrationLeadTimeTests(unittest.TestCase):
    @staticmethod
    def _lead_days(units: list[dict]) -> list[int | None]:
        values: list[int | None] = []
        for unit in units:
            event = unit.get("event_date")
            if event is None:
                values.append(None)
                continue
            values.append((date.fromisoformat(event) - date.fromisoformat(unit["origin_date"])).days)
        return values

    def test_same_top_k_for_both_scorers(self):
        units = _lead_units()
        scores_b = [unit["score_b"] for unit in units]
        # Make scorer B clearly worse: its positives rank below the negative pack.
        scores_b[10:] = [0.45, 0.40, 0.35, 0.30, 0.25]
        result = evalstats.lead_time_at_matched_false_alarm(
            [unit["score_a"] for unit in units],
            scores_b,
            [unit["label"] for unit in units],
            self._lead_days(units),
            far=0.2)
        self.assertEqual(result["scores_a"]["k"], result["scores_b"]["k"])
        self.assertEqual(result["scores_a"]["k"], result["k"])
        self.assertEqual(result["k"], 7)
        self.assertAlmostEqual(result["far_a"], 0.2)
        self.assertGreater(result["far_b"], result["far_a"])
        self.assertEqual(result["mean_lead_days_a"], result["scores_a"]["mean_lead_days"])
        self.assertEqual(result["n_detected_a"], 5)
        self.assertEqual(result["n_detected_b"], 2)
        # p4 has no observed lead; p5's censor date is not part of this adapter's inputs.
        self.assertEqual(result["n_censored_a"], 1)
        self.assertEqual(result["difference"]["n_detected"], 3)

    def test_explicit_k_is_respected(self):
        units = _lead_units()
        result = evalstats.lead_time_at_matched_false_alarm(
            [unit["score_a"] for unit in units],
            [unit["score_b"] for unit in units],
            [unit["label"] for unit in units],
            [None if unit.get("event_date") is None else 10 for unit in units],
            k=3)
        self.assertEqual(result["k"], 3)
        self.assertEqual(result["scores_a"]["k"], 3)
        self.assertEqual(result["scores_b"]["k"], 3)

    def test_never_detected_counted(self):
        result = evalstats.lead_time_at_matched_false_alarm(
            [0.9, 0.8, 0.7, 0.1, 0.2, 0.3],
            [0.85, 0.7, 0.6, 0.15, 0.25, 0.35],
            [1, 1, 1, 0, 0, 0],
            [None, 10, None, None, None, None],
            k=4)
        self.assertEqual(result["positives_without_lead"], 2)
        self.assertEqual(result["n_censored_a"], 2)
        self.assertEqual(result["n_detected_a"], 3)
        self.assertEqual(result["mean_lead_days_a"], 10.0)


if __name__ == "__main__":
    unittest.main()
