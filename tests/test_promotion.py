"""Tests for the promotion policy (policy as code, human sign-off, confirmed rule)."""
from __future__ import annotations

import json
import unittest

from medradar.intelligence.promotion import (
    DEFAULT_POLICY,
    POLICY_VERSION,
    PROMOTION_COLUMNS,
    STATEMENT,
    build_promotion_record,
    classify_shape,
    decide_promotion,
    render_policy,
    render_promotion_row,
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


class DensityFloorTest(unittest.TestCase):
    """Below the measured density floor the ramp label is not supported (D-061)."""

    @staticmethod
    def alert(baseline_mean):
        return {"track": "insulin_delivery", "quarter": "2025-Q3", "events": 2,
                "baseline_mean": baseline_mean, "z": 3.5, "detector": "rolling_zscore",
                "resolution_months": 3, "threshold": 3.5, "false_alarm_rate": 0.0179}

    def test_sparse_cell_ramp_is_relabelled_unresolved(self):
        # 0.25 events per quarter = 0.083 per month, far below the 1.0 floor
        decision = decide_promotion(self.alert(0.25), [3, 4])
        self.assertEqual(decision["shape"], "sustained_unresolved")
        self.assertIn("below the 1/month floor", decision["shape_reason"])
        # promotion itself is unaffected: the binary decision only needs "sustained"
        self.assertEqual(decision["verdict"], "promote_pending_signoff")

    def test_dense_cell_keeps_the_ramp_label(self):
        # 6 events per quarter = 2.0 per month, above the floor; following quarters rise above baseline
        decision = decide_promotion(self.alert(6.0), [10, 12])
        self.assertEqual(decision["shape"], "ramp")

    def test_floor_is_per_month_not_per_quarter(self):
        # 2.7 per quarter = 0.9 per month: still below the floor; following quarters rise markedly
        decision = decide_promotion(self.alert(2.7), [5, 7])
        self.assertEqual(decision["shape"], "sustained_unresolved")


class PromotionLedgerTest(unittest.TestCase):
    """A promotion must be attributable, or it must not be written at all."""

    @staticmethod
    def decision(**overrides):
        base = {"verdict": "promote_pending_signoff", "track": "insulin_delivery",
                "quarter": "2025-Q3", "shape": "ramp", "relative_post_rate": 6.0,
                "policy_version": "promotion_policy_v1"}
        base.update(overrides)
        return base

    def build(self, **overrides):
        kwargs = {"company": "medtronic", "signer": "Dr Example",
                  "justification": "two quarters elevated and rising",
                  "signed_at_utc": "2026-11-03T12:00:00+00:00"}
        kwargs.update(overrides)
        return build_promotion_record(self.decision(), **kwargs)

    def test_record_carries_signer_and_statement(self):
        record = self.build()
        self.assertEqual(record["signer"], "Dr Example")
        self.assertEqual(record["verdict"], "promoted")
        self.assertIn("PUBLIC FILING RATE", record["statement"])

    def test_missing_signer_is_refused(self):
        with self.assertRaises(ValueError):
            self.build(signer="  ")

    def test_missing_justification_is_refused(self):
        with self.assertRaises(ValueError):
            self.build(justification="")

    def test_missing_timestamp_is_refused(self):
        with self.assertRaises(ValueError):
            self.build(signed_at_utc="")

    def test_non_promotable_decision_is_refused(self):
        with self.assertRaises(ValueError):
            build_promotion_record(self.decision(verdict="reject"), company="medtronic",
                                   signer="Dr Example", justification="x",
                                   signed_at_utc="2026-11-03T12:00:00+00:00")

    def test_row_has_every_column_in_order(self):
        record = self.build()
        row = render_promotion_row(record)
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        self.assertEqual(len(cells), len(PROMOTION_COLUMNS))
        self.assertEqual(cells[0], record["id"])

    def test_column_order_is_stable(self):
        self.assertEqual(PROMOTION_COLUMNS[0], "id")
        self.assertIn("signer", PROMOTION_COLUMNS)
        self.assertEqual(PROMOTION_COLUMNS[-1], "justification")


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
