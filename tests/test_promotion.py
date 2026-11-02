"""Tests for the promotion policy (policy as code, human sign-off, confirmed rule)."""
from __future__ import annotations

import json
import unittest

from medradar.intelligence.promotion import (
    DEFAULT_POLICY,
    POLICY_VERSION,
    STATEMENT,
    classify_shape,
    decide_promotion,
    render_policy,
)


def alert(**overrides):
    base = {"track": "coronary", "quarter": "2026-Q3", "events": 2, "baseline_mean": 0.25,
            "z": 3.5, "detector": "rolling_zscore", "resolution_months": 3, "threshold": 3.5,
            "false_alarm_rate": 0.0179}
    base.update(overrides)
    return base


class ClassifyShapeTest(unittest.TestCase):
    def test_falls_back_to_baseline_is_a_spike(self):
        result = classify_shape([0, 1], baseline_rate=0.5)
        self.assertEqual(result["shape"], "spike")

    def test_elevated_and_flat_is_a_level_shift(self):
        result = classify_shape([3, 3], baseline_rate=0.5)
        self.assertEqual(result["shape"], "level")

    def test_elevated_and_rising_is_a_ramp(self):
        result = classify_shape([2, 4], baseline_rate=0.5)
        self.assertEqual(result["shape"], "ramp")

    def test_no_quarters_is_unknown(self):
        self.assertEqual(classify_shape([], baseline_rate=0.5)["shape"], "unknown")

    def test_zero_baseline_is_unknown(self):
        self.assertEqual(classify_shape([2, 2], baseline_rate=0.0)["shape"], "unknown")


class DecidePromotionTest(unittest.TestCase):
    def test_sustained_alert_is_promotable_but_requires_signoff(self):
        decision = decide_promotion(alert(), [3, 3])
        self.assertEqual(decision["verdict"], "promote_pending_signoff")
        self.assertTrue(decision["requires_signoff"])
        self.assertEqual(decision["gate_failures"], [])
        self.assertIn("PUBLIC FILING RATE", decision["statement"])

    def test_spike_is_rejected(self):
        decision = decide_promotion(alert(), [0, 0])
        self.assertEqual(decision["verdict"], "reject")
        self.assertTrue(any("spike" in failure for failure in decision["gate_failures"]))

    def test_missing_confirmation_window_is_rejected(self):
        decision = decide_promotion(alert(), None)
        self.assertEqual(decision["verdict"], "reject")

    def test_wrong_detector_is_rejected(self):
        decision = decide_promotion(alert(detector="naive_multiplier"), [3, 3])
        self.assertEqual(decision["verdict"], "reject")
        self.assertTrue(any("detector" in failure for failure in decision["gate_failures"]))

    def test_wrong_resolution_is_rejected(self):
        decision = decide_promotion(alert(resolution_months=1), [3, 3])
        self.assertEqual(decision["verdict"], "reject")

    def test_wrong_threshold_is_rejected(self):
        decision = decide_promotion(alert(threshold=1.0), [3, 3])
        self.assertEqual(decision["verdict"], "reject")

    def test_alert_below_own_threshold_is_rejected(self):
        decision = decide_promotion(alert(z=2.0), [3, 3])
        self.assertEqual(decision["verdict"], "reject")

    def test_decision_carries_detector_provenance(self):
        decision = decide_promotion(alert(), [3, 3])
        provenance = decision["detector_provenance"]
        self.assertEqual(provenance["detector"], "rolling_zscore")
        self.assertEqual(provenance["resolution_months"], 3)
        self.assertEqual(provenance["threshold"], 3.5)

    def test_no_automated_path_exists(self):
        # the only route to promotion is a pending sign-off; there is no "promote" verdict
        for following in ([3, 3], [5, 9], [0, 0]):
            verdicts = {decide_promotion(alert(), following)["verdict"]}
            self.assertNotIn("promote", verdicts)
            self.assertNotIn("auto_promote", verdicts)


class PolicyDocumentTest(unittest.TestCase):
    def test_policy_states_no_automation(self):
        self.assertFalse(DEFAULT_POLICY["automated_promotion_allowed"])
        self.assertTrue(DEFAULT_POLICY["human_signoff_required"])

    def test_render_mentions_every_gate(self):
        text = render_policy()
        for gate in ("calibrated_alert", "confirmation_window", "contradiction_check", "human_signoff"):
            self.assertIn(gate, text)

    def test_policy_is_json_serialisable(self):
        self.assertIsInstance(json.dumps(DEFAULT_POLICY), str)

    def test_version_is_stamped(self):
        self.assertEqual(DEFAULT_POLICY["version"], POLICY_VERSION)


if __name__ == "__main__":
    unittest.main()
