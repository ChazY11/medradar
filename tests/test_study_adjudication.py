"""Tests for the agent pre-adjudication rubric (no database, no store)."""
from __future__ import annotations

import unittest

from medradar.studies.adjudication import (
    CONFIRMED,
    FALSE_SIGNAL,
    NOT_ASSESSABLE,
    RUBRIC_VERSION,
    ROUTINE,
    TIER,
    UNCERTAIN,
    device_relevance,
    preliminary_label,
    summarise,
    taxonomy_consistency,
    third_source_strength,
)

KEYWORDS = ["MECHANICAL VENTILATION", "VENTILATOR", "RESPIRATORY FAILURE"]


class RelevanceTest(unittest.TestCase):
    def test_full_phrase_is_strong(self):
        result = device_relevance("A study of mechanical ventilation in neonates", KEYWORDS)
        self.assertEqual(result["score"], "STRONG")
        self.assertIn("MECHANICAL VENTILATION", result["matched_theses"])

    def test_single_token_is_weak(self):
        # a token of a multi-word keyword appears, but no full keyword phrase: "ventilation" without "mechanical"
        result = device_relevance("Non-invasive ventilation strategies review",
                                  ["MECHANICAL VENTILATION", "RESPIRATORY FAILURE"])
        self.assertEqual(result["score"], "WEAK")

    def test_unrelated_text_is_none(self):
        self.assertEqual(device_relevance("Oncology chemotherapy dosing", KEYWORDS)["score"], "NONE")

    def test_empty_text_is_none(self):
        self.assertEqual(device_relevance("", KEYWORDS)["score"], "NONE")


class ConsistencyTest(unittest.TestCase):
    def test_matching_mapping(self):
        self.assertEqual(taxonomy_consistency("respiratory", "respiratory"), "CONSISTENT")

    def test_mismatched_mapping(self):
        self.assertEqual(taxonomy_consistency("respiratory", "cardiac_rhythm"), "INCONSISTENT")

    def test_missing_mapping_is_unknown(self):
        self.assertEqual(taxonomy_consistency("respiratory", None), "UNKNOWN")


class ThirdSourceTest(unittest.TestCase):
    def test_near_support(self):
        self.assertEqual(third_source_strength({"status": "SUPPORTED_BEFORE", "distance_class": "NEAR"}),
                         "NEAR_SUPPORT")

    def test_distant_support_is_not_near(self):
        self.assertEqual(third_source_strength({"status": "SUPPORTED_BEFORE", "distance_class": "DISTANT"}),
                         "DISTANT_SUPPORT")

    def test_after_and_absent(self):
        self.assertEqual(third_source_strength({"status": "AFTER_CLEARANCE"}), "AFTER")
        self.assertEqual(third_source_strength(None), "NOT_CHECKED")


class RuleTableTest(unittest.TestCase):
    def strong(self):
        return {"score": "STRONG"}

    def test_confirmed_requires_near_third_source(self):
        result = preliminary_label(relevance=self.strong(), consistency="CONSISTENT",
                                   third_source="NEAR_SUPPORT")
        self.assertEqual(result["label"], CONFIRMED)

    def test_strong_but_no_near_source_is_uncertain(self):
        result = preliminary_label(relevance=self.strong(), consistency="CONSISTENT",
                                   third_source="DISTANT_SUPPORT")
        self.assertEqual(result["label"], UNCERTAIN)

    def test_taxonomy_mismatch_is_false_signal(self):
        result = preliminary_label(relevance=self.strong(), consistency="INCONSISTENT",
                                   third_source="NOT_CHECKED")
        self.assertEqual(result["label"], FALSE_SIGNAL)

    def test_no_relevance_is_false_signal(self):
        result = preliminary_label(relevance={"score": "NONE"}, consistency="CONSISTENT",
                                   third_source="NOT_CHECKED")
        self.assertEqual(result["label"], FALSE_SIGNAL)

    def test_routine_stratum_is_routine_iteration(self):
        result = preliminary_label(relevance=self.strong(), consistency="CONSISTENT",
                                   third_source="NOT_CHECKED", stratum="routine")
        self.assertEqual(result["label"], ROUTINE)

    def test_unknown_mapping_with_strong_relevance_is_uncertain(self):
        result = preliminary_label(relevance=self.strong(), consistency="UNKNOWN",
                                   third_source="NOT_CHECKED")
        self.assertEqual(result["label"], UNCERTAIN)

    def test_unmatched_case_is_marked_not_assessable(self):
        result = preliminary_label(relevance={"score": "WEAK"}, consistency="INCONSISTENT",
                                   third_source="NOT_CHECKED")
        self.assertIn(result["label"], (UNCERTAIN, NOT_ASSESSABLE))


class ContractTest(unittest.TestCase):
    def test_rubric_version_and_tier_are_stated(self):
        self.assertEqual(RUBRIC_VERSION, "agent_rubric_v1")
        self.assertEqual(TIER, "AGENT_PRE_ADJUDICATION")

    def test_summary_counts_labels_and_rules(self):
        rows = [{"label": CONFIRMED, "rule": "a"}, {"label": UNCERTAIN, "rule": "b"},
                {"label": UNCERTAIN, "rule": "b"}]
        result = summarise(rows)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["counts"][UNCERTAIN], 2)
        self.assertEqual(result["rules"]["b"], 2)


if __name__ == "__main__":
    unittest.main()
