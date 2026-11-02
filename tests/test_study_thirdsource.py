"""Tests for the Europe PMC third-source cross-check logic (no network)."""
from __future__ import annotations

import unittest
from datetime import date

from medradar.studies.thirdsource import (
    build_query,
    classify,
    is_independent,
    keyword_terms,
    lead_days,
    lead_quarters,
    parse_date,
)


class QueryTest(unittest.TestCase):
    def test_query_contains_affiliation_and_keywords(self):
        built = build_query("philips", ["MECHANICAL VENTILATION", "VENTILATOR"])
        self.assertIn('AFF:"Philips"', built["query"])
        self.assertIn('"MECHANICAL VENTILATION"', built["query"])
        self.assertIn(" AND ", built["query"])

    def test_unknown_company_is_refused(self):
        with self.assertRaises(ValueError):
            build_query("unknown_firm", ["VENTILATOR"])

    def test_empty_keywords_are_refused(self):
        with self.assertRaises(ValueError):
            build_query("philips", [])

    def test_keyword_terms_are_capped_and_normalised(self):
        terms = keyword_terms(["a b c d", "SHORT", "x-y/z"])
        self.assertLessEqual(len(terms), 3)
        self.assertEqual(terms[0], "a b c d")

    def test_ge_healthcare_has_two_affiliation_terms(self):
        built = build_query("ge_healthcare", ["PATIENT MONITORING"])
        self.assertEqual(len(built["affiliation_terms"]), 2)


class DateTest(unittest.TestCase):
    def test_parse_date_accepts_iso_prefix(self):
        self.assertEqual(parse_date("2020-03-01T10:00:00Z"), date(2020, 3, 1))

    def test_parse_date_rejects_junk(self):
        for value in (None, "", "not a date", "2020-13-40"):
            self.assertIsNone(parse_date(value))

    def test_lead_is_positive_when_publication_precedes(self):
        self.assertEqual(lead_days(date(2020, 1, 1), date(2020, 7, 1)), 182)
        self.assertGreater(lead_quarters(182), 1.9)


class IndependenceTest(unittest.TestCase):
    def test_trial_report_is_not_independent(self):
        self.assertFalse(is_independent({"title": "Results of NCT01234567 in heart failure"}))

    def test_ordinary_paper_is_independent(self):
        self.assertTrue(is_independent({"title": "A novel ventilator algorithm"}))


class ClassifyTest(unittest.TestCase):
    CLEARANCE = date(2021, 1, 15)

    def test_supported_before_uses_the_earliest_record(self):
        records = [{"title": "later", "firstPublicationDate": "2020-12-01"},
                   {"title": "earlier", "firstPublicationDate": "2019-06-01"}]
        result = classify(records, clearance_date=self.CLEARANCE)
        self.assertEqual(result["status"], "SUPPORTED_BEFORE")
        self.assertEqual(result["earliest_date"], "2019-06-01")
        self.assertGreater(result["lead_days"], 0)

    def test_no_records_is_no_record(self):
        self.assertEqual(classify([], clearance_date=self.CLEARANCE)["status"], "NO_RECORD")

    def test_only_after_clearance(self):
        records = [{"title": "x", "firstPublicationDate": "2021-06-01"}]
        result = classify(records, clearance_date=self.CLEARANCE)
        self.assertEqual(result["status"], "AFTER_CLEARANCE")
        self.assertLess(result["lead_days"], 0)

    def test_trial_reports_alone_are_ambiguous(self):
        records = [{"title": "NCT01234567 results", "firstPublicationDate": "2020-01-01"}]
        self.assertEqual(classify(records, clearance_date=self.CLEARANCE)["status"], "AMBIGUOUS")

    def test_undated_records_are_ambiguous(self):
        records = [{"title": "no date"}]
        self.assertEqual(classify(records, clearance_date=self.CLEARANCE)["status"], "AMBIGUOUS")


if __name__ == "__main__":
    unittest.main()
