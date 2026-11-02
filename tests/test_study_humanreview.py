"""Tests for the human review vocabulary, validation and agreement statistics."""
from __future__ import annotations

import unittest

from medradar.studies.humanreview import (
    ALLOWED_LABELS,
    CONFIRMED,
    FALSE_SIGNAL,
    INSUFFICIENT,
    ROUTINE,
    UNCERTAIN,
    agreement,
    normalise_label,
    summarise_review,
    validate_row,
    validate_rows,
)


def row(**overrides):
    base = {"packet_id": "ES5-001", "human_label": CONFIRMED, "reviewer": "A. Reviewer",
            "human_reason": "clearance matches the trial direction",
            "independent_confirmation": "Europe PMC PMID 1234567, 2020-02-01",
            "agent_preliminary_label": CONFIRMED + " (agent-preliminary)"}
    base.update(overrides)
    return base


class VocabularyTest(unittest.TestCase):
    def test_five_labels_only(self):
        self.assertEqual(len(ALLOWED_LABELS), 5)
        self.assertIn(INSUFFICIENT, ALLOWED_LABELS)

    def test_alias_is_normalised(self):
        self.assertEqual(normalise_label("confirmed"), CONFIRMED)
        self.assertEqual(normalise_label("  Routine Iteration "), ROUTINE)

    def test_unknown_value_is_preserved_for_the_error_message(self):
        self.assertEqual(normalise_label("probably a shift"), "probably a shift")


class ValidationTest(unittest.TestCase):
    def test_complete_row_is_valid(self):
        self.assertEqual(validate_row(row()), [])

    def test_missing_label_is_reported(self):
        self.assertTrue(any("human_label is empty" in problem for problem in validate_row(row(human_label=""))))

    def test_out_of_vocabulary_label_is_reported(self):
        problems = validate_row(row(human_label="looks good"))
        self.assertTrue(any("not one of the five labels" in problem for problem in problems))

    def test_reviewer_is_required(self):
        self.assertTrue(any("reviewer name is required" in problem
                            for problem in validate_row(row(reviewer="  "))))

    def test_reason_is_required(self):
        self.assertTrue(any("human_reason is required" in problem
                            for problem in validate_row(row(human_reason=""))))

    def test_confirmed_shift_needs_independence(self):
        problems = validate_row(row(independent_confirmation=""))
        self.assertTrue(any("independent confirmation" in problem for problem in problems))

    def test_uncertain_does_not_need_independence(self):
        self.assertEqual(validate_row(row(human_label=UNCERTAIN, independent_confirmation="")), [])

    def test_false_signal_needs_no_independence(self):
        self.assertEqual(validate_row(row(human_label=FALSE_SIGNAL, independent_confirmation="")), [])


class RowsTest(unittest.TestCase):
    def test_duplicate_packets_are_rejected(self):
        result = validate_rows([row(), row()])
        self.assertFalse(result["valid"])
        self.assertTrue(any("duplicate" in problem for problem in result["problems"]))

    def test_valid_set_passes(self):
        result = validate_rows([row(), row(packet_id="ES5-002", human_label=ROUTINE,
                                           independent_confirmation="")])
        self.assertTrue(result["valid"])


class SummaryTest(unittest.TestCase):
    def test_counts_and_reviewers(self):
        summary = summarise_review([row(), row(packet_id="B", human_label=UNCERTAIN,
                                               reviewer="B. Reviewer")])
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["counts"][CONFIRMED], 1)
        self.assertEqual(summary["reviewers"], ["A. Reviewer", "B. Reviewer"])

    def test_agreement_is_descriptive(self):
        result = agreement([row(), row(packet_id="B", human_label=UNCERTAIN,
                                       agent_preliminary_label="Uncertain (agent-preliminary)")])
        self.assertEqual(result["compared"], 2)
        self.assertEqual(result["same"], 2)
        self.assertEqual(result["agreement"], 1.0)
        self.assertIn("must not be tuned", result["note"])


if __name__ == "__main__":
    unittest.main()
