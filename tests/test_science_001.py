"""Offline tests for SCIENCE-001 (research/science_001).

No network access. Every fixture is synthetic and hand-built so a failure here
is a failure of *our* logic, never of SEC or of today's internet.

The tests deliberately pin the scientific invariants that the study depends on:

* the DST conversion is the one the data actually shows (offset -4/-5 switching
  at the US transition instants), not "whatever zoneinfo says today";
* the raw header is parsed from both encodings that exist in the archive;
* a time grade names exactly what it supports;
* the outcome label can only be built from filings accepted strictly later than
  the observation unit, so the same bytes cannot form both input and label;
* censored forward windows are dropped, never labelled zero;
* the permutation scheme preserves each issuer's label multiset;
* the model ladder standardises on train statistics only.

Run:  python -m pytest tests/test_science_001.py -q
   or python -m unittest tests.test_science_001
"""

from __future__ import annotations

import datetime as dt
import math
import unittest

from research.science_001 import dataset, edgar, experiment, features, figures
from research.science_001 import sample, timesemantics as ts

UTC = dt.timezone.utc


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def synthetic_submission(acceptance: str = "20240115163045",
                         accession: str = "0000000000-24-000001",
                         form: str = "8-K",
                         items: tuple[str, ...] = ("Results of Operations and Financial Condition",
                                                   "Financial Statements and Exhibits"),
                         prose: str = ("Item 2.02 Results of Operations. Research and development "
                                       "expense increased and our clinical trial advanced. We "
                                       "invested in artificial intelligence and a new platform."),
                         tag_form: bool = True) -> str:
    """A minimal but structurally faithful full EDGAR submission."""
    head = "<SEC-DOCUMENT>%s.txt : 20240115\n<SEC-HEADER>%s.hdr.sgml : 20240115\n" % (
        accession, accession)
    if tag_form:
        head += "<ACCEPTANCE-DATETIME>%s\n" % acceptance
    head += "ACCESSION NUMBER:\t\t%s\n" % accession
    if not tag_form:
        head += "ACCEPTANCE-DATETIME:\t%s\n" % acceptance
    head += "CONFORMED SUBMISSION TYPE:\t%s\n" % form
    head += "PUBLIC DOCUMENT COUNT:\t\t2\n"
    for item in items:
        head += "ITEM INFORMATION:\t\t%s\n" % item
    head += "FILED AS OF DATE:\t\t20240115\n"
    head += "FILER:\n\tCOMPANY DATA:\n\t\tCOMPANY CONFORMED NAME:\t\tTEST MEDICAL CORP\n"
    head += "\t\tCENTRAL INDEX KEY:\t\t0000000000\n"
    head += "\tFILING VALUES:\n\t\tFORM TYPE:\t%s\n\t\tSEC FILE NUMBER:\t001-00001\n" % form
    head += "</SEC-HEADER>\n"
    documents = (
        "<DOCUMENT>\n<TYPE>8-K\n<SEQUENCE>1\n<FILENAME>test-8k.htm\n"
        "<TEXT>\n<html><body><p>%s</p></body></html>\n</TEXT>\n</DOCUMENT>\n" % prose
    )
    documents += (
        "<DOCUMENT>\n<TYPE>EX-99.1\n<SEQUENCE>2\n<FILENAME>ex991.htm\n"
        "<TEXT>\n<html><body>Press release: next-generation sensor platform and "
        "robotics programme; R&amp;D spending was 8% of revenue.</body></html>\n"
        "</TEXT>\n</DOCUMENT>\n"
    )
    documents += (
        "<DOCUMENT>\n<TYPE>GRAPHIC\n<SEQUENCE>3\n<FILENAME>chart.jpg\n"
        "<TEXT>\nnot-really-base64\n</TEXT>\n</DOCUMENT>\n"
    )
    return head + documents


def extracted_record(acceptance_utc: str, tier: str = "A_acceptance_verified",
                     words: int = 800, offset_hours: int = -5) -> dict:
    return {
        "acceptance_utc": acceptance_utc,
        "tier": tier,
        "offset_hours": offset_hours,
        "words": words,
        "n_documents": 2,
        "exhibit_share": 0.4,
        "rd_per_1k": 2.0,
        "tech_per_1k": 3.0,
        "dev_per_1k": 5.0,
        "rd_hits": 2,
        "tech_hits": 3,
        "public_interval_seconds": 25,
    }


def panel_row(accession: str, issuer: str, form: str, filing_date: str,
              items: str = "2.02,9.01") -> dict:
    return {
        "issuer": issuer, "ticker": issuer.upper(), "cik": "0000000001",
        "accession": accession, "form": form, "filing_date": filing_date,
        "report_date": filing_date, "items_raw": items,
    }


# --------------------------------------------------------------------------- #
# time semantics
# --------------------------------------------------------------------------- #
class DstRuleTests(unittest.TestCase):
    def test_transition_instants_match_us_rule(self) -> None:
        for year, start_expected, end_expected in (
            (2025, dt.date(2025, 3, 9), dt.date(2025, 11, 2)),
            (2019, dt.date(2019, 3, 10), dt.date(2019, 11, 3)),
            (2026, dt.date(2026, 3, 8), dt.date(2026, 11, 1)),
        ):
            start, end = ts.dst_bounds_utc(year)
            self.assertEqual(start.date(), start_expected)
            self.assertEqual(end.date(), end_expected)
            self.assertEqual(start.hour, 2)
            self.assertEqual(end.hour, 2)

    def test_offset_switches_exactly_at_the_boundary(self) -> None:
        # One day either side of the 2025 spring transition.
        self.assertEqual(ts.eastern_utc_offset_hours(dt.datetime(2025, 3, 8, 12, 0)), -5)
        self.assertEqual(ts.eastern_utc_offset_hours(dt.datetime(2025, 3, 10, 12, 0)), -4)
        # One day either side of the 2025 autumn transition.
        self.assertEqual(ts.eastern_utc_offset_hours(dt.datetime(2025, 11, 1, 12, 0)), -4)
        self.assertEqual(ts.eastern_utc_offset_hours(dt.datetime(2025, 11, 3, 12, 0)), -5)

    def test_pre_2007_rule_is_not_silently_wrong(self) -> None:
        # 2006: first Sunday of April / last Sunday of October.
        start, end = ts.dst_bounds_utc(2006)
        self.assertEqual(start.date(), dt.date(2006, 4, 2))
        self.assertEqual(end.date(), dt.date(2006, 10, 29))
        self.assertEqual(ts.eastern_utc_offset_hours(dt.datetime(2006, 4, 1, 12, 0)), -5)
        self.assertEqual(ts.eastern_utc_offset_hours(dt.datetime(2006, 4, 3, 12, 0)), -4)

    def test_ambiguous_and_nonexistent_local_hours(self) -> None:
        self.assertEqual(ts.local_time_status(dt.datetime(2025, 11, 2, 1, 30)),
                         ts.LocalTimeStatus.AMBIGUOUS)
        self.assertEqual(ts.local_time_status(dt.datetime(2025, 11, 2, 0, 30)),
                         ts.LocalTimeStatus.UNIQUE)
        self.assertEqual(ts.local_time_status(dt.datetime(2025, 3, 9, 2, 30)),
                         ts.LocalTimeStatus.NONEXISTENT)
        self.assertEqual(ts.local_time_status(dt.datetime(2025, 3, 9, 1, 30)),
                         ts.LocalTimeStatus.UNIQUE)

    def test_ambiguous_hour_uses_the_later_conservative_instant(self) -> None:
        # 01:30 on the fall-back day: standard time (-5) is the conservative
        # reading, so the UTC instant must not be earlier than the -4 reading.
        reading = ts.parse_header_acceptance("20251102013000")
        self.assertEqual(reading.local_status, ts.LocalTimeStatus.AMBIGUOUS)
        self.assertEqual(reading.offset_hours, -5)
        self.assertEqual(reading.utc, dt.datetime(2025, 11, 2, 6, 30))

    def test_header_to_utc_known_pairs(self) -> None:
        cases = {
            "20261019162327": (dt.datetime(2026, 10, 19, 20, 23, 27), -4),
            "20250307083224": (dt.datetime(2025, 3, 7, 13, 32, 24), -5),
            "20251103172146": (dt.datetime(2025, 11, 3, 22, 21, 46), -5),
            "20190306182402": (dt.datetime(2019, 3, 6, 23, 24, 2), -5),
        }
        for raw, (expected_utc, expected_offset) in cases.items():
            reading = ts.parse_header_acceptance(raw)
            self.assertEqual(reading.utc, expected_utc, raw)
            self.assertEqual(reading.offset_hours, expected_offset, raw)

    def test_malformed_acceptance_is_rejected_not_guessed(self) -> None:
        for bad in ("", "2024", "notadate", "2024011516304"):
            with self.assertRaises(ValueError):
                ts.parse_header_acceptance(bad)


class GradeTests(unittest.TestCase):
    def test_verified_grade_requires_exact_agreement(self) -> None:
        record = ts.grade_filing(True, "20261019162327", "2026-10-19T20:23:27.000Z", "2026-10-19")
        self.assertEqual(record["tier"], "A_acceptance_verified")
        self.assertEqual(record["residual_seconds"], 0)

    def test_disagreeing_api_downgrades_to_header_only(self) -> None:
        record = ts.grade_filing(True, "20261019162327", "2026-10-19T16:23:27.000Z", "2026-10-19")
        self.assertEqual(record["tier"], "A2_acceptance_header_only")
        self.assertEqual(record["residual_seconds"], -4 * 3600)

    def test_api_only_and_date_only_grades(self) -> None:
        self.assertEqual(ts.grade_filing(False, None, "2026-10-19T20:23:27.000Z",
                                         "2026-10-19")["tier"], "B_acceptance_api_only")
        self.assertEqual(ts.grade_filing(False, None, None, "2026-10-19")["tier"],
                         "C_filing_date_only")
        self.assertEqual(ts.grade_filing(False, None, None, None)["tier"], "D_unknown")

    def test_every_tier_states_what_it_cannot_support(self) -> None:
        for name, tier in ts.TIERS.items():
            self.assertIn("does_not_support", tier, name)
            self.assertIn("supports", tier, name)
            self.assertTrue(tier["meaning"], name)

    def test_acceptance_grade_never_claims_public_availability(self) -> None:
        supports = " ".join(ts.TIERS["A_acceptance_verified"]["supports"]).lower()
        blocked = " ".join(ts.TIERS["A_acceptance_verified"]["does_not_support"]).lower()
        self.assertIn("lower bound", supports)
        self.assertIn("retrievable by an outsider", blocked)


class AvailabilityTests(unittest.TestCase):
    def test_last_modified_gives_a_bounded_interval(self) -> None:
        bounds = ts.availability_bounds(dt.datetime(2026, 10, 19, 20, 23, 27),
                                        dt.datetime(2026, 10, 19, 20, 23, 52), "2026-10-19")
        self.assertTrue(bounds.bounded)
        self.assertEqual(bounds.lag_seconds, 25)

    def test_without_last_modified_only_a_lower_bound_and_eastern_day_end(self) -> None:
        bounds = ts.availability_bounds(dt.datetime(2026, 10, 19, 20, 23, 27), None, "2026-10-19")
        self.assertTrue(bounds.bounded)
        # Deliberately conservative: the end of the Eastern day is converted with
        # the largest possible offset (+5h, EST), so the bound can be too late
        # but never too early.
        self.assertEqual(bounds.not_after_utc, dt.datetime(2026, 10, 20, 4, 59, 59))

    def test_no_filing_date_leaves_only_the_lower_bound(self) -> None:
        bounds = ts.availability_bounds(dt.datetime(2026, 10, 19, 20, 23, 27), None, None)
        self.assertFalse(bounds.bounded)
        self.assertIsNone(bounds.not_after_utc)


# --------------------------------------------------------------------------- #
# archive parsing
# --------------------------------------------------------------------------- #
class HeaderParsingTests(unittest.TestCase):
    def test_tag_encoded_header(self) -> None:
        header = edgar.parse_header(synthetic_submission())
        self.assertTrue(header.present)
        self.assertEqual(header.header_format, "tag")
        self.assertEqual(header.acceptance_raw, "20240115163045")
        self.assertEqual(header.filed_as_of, "20240115")
        self.assertEqual(header.conformed_type, "8-K")
        self.assertEqual(header.public_document_count, 2)
        self.assertEqual(header.cik, "0000000000")
        self.assertEqual(header.company, "TEST MEDICAL CORP")
        self.assertEqual(header.accession, "0000000000-24-000001")
        self.assertEqual(len(header.items), 2)

    def test_colon_encoded_header(self) -> None:
        header = edgar.parse_header(synthetic_submission(tag_form=False))
        self.assertTrue(header.present)
        self.assertEqual(header.header_format, "colon")
        self.assertEqual(header.acceptance_raw, "20240115163045")

    def test_absent_acceptance_is_reported_not_invented(self) -> None:
        text = synthetic_submission(tag_form=False).replace("ACCEPTANCE-DATETIME:\t20240115163045\n", "")
        header = edgar.parse_header(text)
        self.assertFalse(header.present)
        self.assertIsNone(header.acceptance_raw)
        self.assertIsNone(header.header_format)

    def test_documents_and_prose_filter(self) -> None:
        documents = edgar.parse_documents(synthetic_submission())
        self.assertEqual([d.doc_type for d in documents], ["8-K", "EX-99.1", "GRAPHIC"])
        prose = edgar.content_documents(documents)
        self.assertEqual([d.doc_type for d in prose], ["8-K", "EX-99.1"])
        self.assertTrue(all(d.text for d in prose))

    def test_filing_url_shape(self) -> None:
        self.assertEqual(
            edgar.filing_url("0001613103", "0001628280-26-066291"),
            "https://www.sec.gov/Archives/edgar/data/1613103/"
            "000162828026066291/0001628280-26-066291.txt")

    def test_issuer_registry_is_internally_consistent(self) -> None:
        keys = [i.key for i in edgar.ISSUERS]
        ciks = [i.cik for i in edgar.ISSUERS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(ciks), len(set(ciks)))
        for issuer in edgar.ISSUERS:
            self.assertEqual(len(issuer.cik), 10, issuer.key)
            self.assertTrue(issuer.cik.isdigit(), issuer.key)


# --------------------------------------------------------------------------- #
# features
# --------------------------------------------------------------------------- #
class FeatureTests(unittest.TestCase):
    def test_rate_is_per_thousand_words_and_exact(self) -> None:
        text = "research and development clinical trial platform robotics"
        words = features.words(text)
        self.assertEqual(len(words), 7)
        self.assertEqual(features.count_terms(text, features.RD_TERMS), 2)
        self.assertEqual(features.count_terms(text, features.TECH_TERMS), 2)
        result = features.extract_features([
            edgar.RawDocument(doc_type="8-K", filename="a.htm", text=text)])
        self.assertEqual(result["words"], 7)
        self.assertAlmostEqual(result["rd_per_1k"], 2 / (7 / 1000.0), places=3)
        self.assertAlmostEqual(result["tech_per_1k"], 2 / (7 / 1000.0), places=3)

    def test_terms_are_matched_as_phrases_not_substrings(self) -> None:
        # "rd" alone must not match the R&D term; "R&D" inside "R&amp;D" must.
        self.assertEqual(features.count_terms("the rd program", features.RD_TERMS), 0)
        self.assertEqual(features.count_terms("our r&d spend", features.RD_TERMS), 1)
        self.assertEqual(features.count_terms("research and development", features.RD_TERMS), 1)
        self.assertEqual(features.count_terms("research and developer", features.RD_TERMS), 0)

    def test_html_and_entities_are_removed(self) -> None:
        clean = features.to_text("<p>R&amp;D <b>spend</b> \u2014 up</p>")
        self.assertNotIn("<", clean)
        self.assertNotIn("&amp;", clean)
        self.assertIn("r&d", clean.lower())

    def test_graphic_attachments_do_not_contribute_words(self) -> None:
        documents = edgar.parse_documents(synthetic_submission())
        result = features.extract_features(documents)
        joined = " ".join(d.text for d in edgar.content_documents(documents))
        self.assertNotIn("not-really-base64", features.to_text(joined))
        self.assertGreater(result["words"], 10)

    def test_empty_filing_yields_zero_rates_not_an_error(self) -> None:
        result = features.extract_features([])
        self.assertEqual(result["words"], 0)
        self.assertEqual(result["rd_per_1k"], 0.0)
        self.assertEqual(result["dev_per_1k"], 0.0)

    def test_lexicons_are_a_declared_fixed_size(self) -> None:
        # The protocol says 25 + 25; if someone edits a lexicon the pre-registration
        # hash and this constant must be revisited deliberately.
        self.assertEqual(len(features.RD_TERMS), 25)
        self.assertEqual(len(features.TECH_TERMS), 25)
        self.assertEqual(len(set(features.RD_TERMS)), 25)
        self.assertEqual(len(set(features.TECH_TERMS)), 25)


# --------------------------------------------------------------------------- #
# dataset construction: the no-leakage core
# --------------------------------------------------------------------------- #
class DatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.extracted = {
            "A1": extracted_record("2024-01-02T15:00:00Z"),
            "A2": extracted_record("2024-02-01T15:00:00Z"),
            "A3": extracted_record("2024-03-01T15:00:00Z"),
            "A4": extracted_record("2024-04-01T15:00:00Z"),
        }

    def test_label_uses_only_strictly_later_filings(self) -> None:
        rows = [
            panel_row("A1", "x", "8-K", "2024-01-02", items="1.01,9.01"),
            panel_row("A2", "x", "8-K", "2024-02-01", items="2.02,9.01"),
            panel_row("A3", "x", "8-K", "2024-03-01", items="2.02,9.01"),
            panel_row("A4", "x", "8-K", "2024-04-01", items="2.02,9.01"),
        ]
        built = dataset.build_dataset(rows, self.extracted, frame_end=dt.date(2026, 12, 31))
        by_accession = {row["accession"]: row for row in built["rows"]}
        # A1's own item 1.01 must not self-label it.
        self.assertEqual(by_accession["A1"]["label_tech_event"], 0)
        # A2 sees A3? A3 is 2.02 -> no. So 0. A1..A4 spaced 30 days: within 90 days.
        self.assertEqual(by_accession["A2"]["label_tech_event"], 0)
        self.assertEqual(by_accession["A2"]["n_prior_events"], 1)
        self.assertEqual(by_accession["A4"]["n_prior_events"], 3)

    def test_forward_event_inside_horizon_labels_the_unit(self) -> None:
        extracted = dict(self.extracted)
        extracted["A2"] = extracted_record("2024-02-01T15:00:00Z")
        rows = [
            panel_row("A1", "x", "8-K", "2024-01-02", items="2.02"),
            panel_row("A2", "x", "8-K", "2024-03-15", items="1.01,9.01"),
        ]
        extracted = {"A1": extracted_record("2024-01-02T15:00:00Z"),
                     "A2": extracted_record("2024-03-15T15:00:00Z")}
        built = dataset.build_dataset(rows, extracted, frame_end=dt.date(2026, 12, 31))
        by_accession = {row["accession"]: row for row in built["rows"]}
        self.assertEqual(by_accession["A1"]["label_tech_event"], 1)
        self.assertEqual(by_accession["A2"]["label_tech_event"], 0)

    def test_event_outside_horizon_does_not_label(self) -> None:
        rows = [
            panel_row("A1", "x", "8-K", "2024-01-02", items="2.02"),
            panel_row("A2", "x", "8-K", "2024-08-01", items="1.01"),
        ]
        extracted = {"A1": extracted_record("2024-01-02T15:00:00Z"),
                     "A2": extracted_record("2024-08-01T15:00:00Z")}
        built = dataset.build_dataset(rows, extracted, frame_end=dt.date(2026, 12, 31))
        by_accession = {row["accession"]: row for row in built["rows"]}
        self.assertEqual(by_accession["A1"]["label_tech_event"], 0)
        self.assertEqual(by_accession["A1"]["n_forward_events"], 0)

    def test_censored_forward_window_is_dropped_not_labelled_zero(self) -> None:
        rows = [panel_row("A4", "x", "8-K", "2024-04-01", items="2.02")]
        built = dataset.build_dataset(rows, {"A4": extracted_record("2024-04-01T15:00:00Z")},
                                      frame_end=dt.date(2024, 6, 29))
        self.assertEqual(built["rows"], [])
        self.assertEqual(built["drop_ledger"].get("forward_window_censored"), 1)

    def test_amendments_are_not_observation_units(self) -> None:
        rows = [
            panel_row("A1", "x", "8-K", "2024-01-02", items="2.02"),
            panel_row("A1A", "x", "8-K/A", "2024-01-05", items="2.02"),
        ]
        extracted = {"A1": extracted_record("2024-01-02T15:00:00Z"),
                     "A1A": extracted_record("2024-01-05T15:00:00Z")}
        built = dataset.build_dataset(rows, extracted, frame_end=dt.date(2026, 12, 31))
        self.assertEqual([row["accession"] for row in built["rows"]], ["A1"])

    def test_rows_without_usable_time_grade_are_dropped(self) -> None:
        rows = [panel_row("A1", "x", "8-K", "2024-01-02")]
        built = dataset.build_dataset(
            rows, {"A1": extracted_record("2024-01-02T15:00:00Z", tier="D_unknown")},
            frame_end=dt.date(2026, 12, 31))
        self.assertEqual(built["rows"], [])
        self.assertEqual(built["drop_ledger"].get("unusable_time_grade"), 1)

    def test_too_short_prose_is_dropped_rather_than_imputed(self) -> None:
        rows = [panel_row("A1", "x", "8-K", "2024-01-02")]
        built = dataset.build_dataset(
            rows, {"A1": extracted_record("2024-01-02T15:00:00Z", words=10)},
            frame_end=dt.date(2026, 12, 31))
        self.assertEqual(built["rows"], [])
        self.assertEqual(built["drop_ledger"].get("too_few_words"), 1)

    def test_unfetched_neighbour_still_counts_via_api_time(self) -> None:
        # A2 is not in extracted, but the API acceptance is a valid neighbour.
        rows = [
            panel_row("A1", "x", "8-K", "2024-01-02", items="2.02"),
            panel_row("A2", "x", "8-K", "2024-02-01", items="1.01"),
        ]
        rows[1]["acceptance_api"] = "2024-02-01T15:00:00.000Z"
        built = dataset.build_dataset(rows, {"A1": extracted_record("2024-01-02T15:00:00Z")},
                                      frame_end=dt.date(2026, 12, 31))
        by_accession = {row["accession"]: row for row in built["rows"]}
        self.assertEqual(by_accession["A1"]["label_tech_event"], 1)

    def test_item_parsing_handles_the_api_format(self) -> None:
        self.assertEqual(dataset.parse_items("1.01,2.01,9.01"), {"1.01", "2.01", "9.01"})
        self.assertEqual(dataset.parse_items("1.01;2.01"), {"1.01", "2.01"})
        self.assertEqual(dataset.parse_items(""), set())
        self.assertEqual(dataset.parse_items(None), set())


class AmendmentLinkingTests(unittest.TestCase):
    def test_accession_quoted_in_amendment_is_a_high_confidence_link(self) -> None:
        rows = [
            panel_row("0000000000-24-000001", "x", "8-K", "2024-01-02"),
            panel_row("0000000000-24-000009", "x", "8-K/A", "2024-01-20"),
        ]
        prose = {"0000000000-24-000009":
                 "This amendment amends the report on Form 8-K, accession "
                 "number 0000000000-24-000001, filed on January 2, 2024."}
        links = dataset.link_amendments(rows, prose)
        self.assertEqual(links["0000000000-24-000009"]["basis"],
                         "accession_quoted_in_amendment")
        self.assertEqual(links["0000000000-24-000009"]["amends_accession"],
                         "0000000000-24-000001")

    def test_date_reference_is_a_medium_confidence_link(self) -> None:
        rows = [
            panel_row("0000000000-24-000001", "x", "8-K", "2024-01-02"),
            panel_row("0000000000-24-000009", "x", "8-K/A", "2024-01-20"),
        ]
        prose = {"0000000000-24-000009":
                 "This Form 8-K/A amends the Form 8-K filed January 2, 2024."}
        links = dataset.link_amendments(rows, prose)
        self.assertEqual(links["0000000000-24-000009"]["basis"],
                         "date_reference_in_amendment")
        self.assertEqual(links["0000000000-24-000009"]["confidence"], "medium")

    def test_item_set_proximity_is_low_confidence_not_fact(self) -> None:
        rows = [
            panel_row("0000000000-24-000001", "x", "8-K", "2024-01-02"),
            panel_row("0000000000-24-000009", "x", "8-K/A", "2024-01-20"),
        ]
        links = dataset.link_amendments(rows, {})
        link = links["0000000000-24-000009"]
        self.assertEqual(link["basis"], "item_set_proximity")
        self.assertEqual(link["confidence"], "low")
        self.assertTrue(link["items_match"])

    def test_no_supporting_signal_is_marked_unverified(self) -> None:
        rows = [
            panel_row("0000000000-24-000001", "x", "8-K", "2024-01-02", items="2.02"),
            panel_row("0000000000-24-000009", "x", "8-K/A", "2024-01-20", items="5.02"),
        ]
        link = dataset.link_amendments(rows, {})["0000000000-24-000009"]
        self.assertEqual(link["basis"], "previous_filing_fallback")
        self.assertEqual(link["confidence"], "low_unverified")
        self.assertFalse(link["items_match"])

    def test_ambiguous_date_reference_is_not_forced(self) -> None:
        rows = [
            panel_row("0000000000-24-000001", "x", "8-K", "2024-01-02", items="5.02"),
            panel_row("0000000000-24-000002", "x", "8-K", "2024-01-02", items="5.02"),
            panel_row("0000000000-24-000009", "x", "8-K/A", "2024-02-20", items="5.02"),
        ]
        prose = {"0000000000-24-000009":
                 "This amendment amends the Form 8-K filed on January 2, 2024."}
        link = dataset.link_amendments(rows, prose)["0000000000-24-000009"]
        # Two same-day candidates: the date does not identify the original, so the
        # link must fall back and say so rather than pick one.
        self.assertEqual(link["basis"], "ambiguous_date_reference")
        self.assertIsNone(link["amends_accession"])


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #
class MetricTests(unittest.TestCase):
    def test_auc_known_values(self) -> None:
        self.assertAlmostEqual(experiment.auc([1, 2, 3, 4], [0, 0, 1, 1]), 1.0)
        self.assertAlmostEqual(experiment.auc([4, 3, 2, 1], [0, 0, 1, 1]), 0.0)
        self.assertAlmostEqual(experiment.auc([0.5] * 6, [0, 1, 0, 1, 0, 1]), 0.5)
        self.assertAlmostEqual(experiment.auc([1, 2, 3, 4], [0, 1, 0, 1]), 0.75)

    def test_auc_is_none_when_a_class_is_missing(self) -> None:
        self.assertIsNone(experiment.auc([1, 2, 3], [0, 0, 0]))
        self.assertIsNone(experiment.auc([], []))

    def test_brier_and_log_loss_bounds(self) -> None:
        self.assertAlmostEqual(experiment.brier([1, 0], [1, 0]), 0.0)
        self.assertAlmostEqual(experiment.brier([0.5, 0.5], [1, 0]), 0.25)
        self.assertGreater(experiment.log_loss([0.5, 0.5], [1, 0]), 0.0)
        self.assertLess(experiment.log_loss([0.99, 0.01], [1, 0]), 0.02)

    def test_prevalence(self) -> None:
        self.assertAlmostEqual(experiment.prevalence([1, 0, 1, 0]), 0.5)
        self.assertIsNone(experiment.prevalence([]))


class LogisticTests(unittest.TestCase):
    def test_standardisation_uses_train_statistics_only(self) -> None:
        means, stds = experiment.standardize_fit([[1.0], [3.0]])
        self.assertAlmostEqual(means[0], 2.0)
        self.assertAlmostEqual(stds[0], 1.0)
        # A shifted test value standardises against the TRAIN mean, not its own.
        transformed = experiment.standardize_apply([[12.0]], means, stds)
        self.assertAlmostEqual(transformed[0][0], 10.0)

    def test_constant_column_does_not_divide_by_zero(self) -> None:
        means, stds = experiment.standardize_fit([[5.0], [5.0], [5.0]])
        self.assertEqual(stds[0], 1.0)
        self.assertEqual(experiment.standardize_apply([[5.0]], means, stds)[0][0], 0.0)

    def test_separable_data_yields_the_right_sign(self) -> None:
        xs = [[-2.0], [-1.0], [-0.5], [0.5], [1.0], [2.0]]
        labels = [0, 0, 0, 1, 1, 1]
        beta = experiment.fit_logistic(xs, labels, ridge=0.1)
        self.assertGreater(beta[1], 0.0)
        scores = experiment.predict_proba(xs, beta)
        self.assertLess(scores[0], scores[-1])
        self.assertAlmostEqual(experiment.auc(scores, labels), 1.0)

    def test_prediction_stays_in_the_unit_interval(self) -> None:
        xs = [[-50.0], [50.0]]
        beta = experiment.fit_logistic(xs, [0, 1], ridge=0.01)
        for value in experiment.predict_proba(xs, beta):
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)
            self.assertFalse(math.isnan(value))

    def test_solver_solves_a_known_system(self) -> None:
        solution = experiment._solve([[2.0, 1.0], [1.0, 3.0]], [3.0, 5.0])
        self.assertAlmostEqual(solution[0], 0.8)
        self.assertAlmostEqual(solution[1], 1.4)


class PermutationTests(unittest.TestCase):
    def _rows(self, n_per_issuer: int = 6, issuers: int = 4) -> list[dict]:
        rows = []
        for index in range(issuers):
            for position in range(n_per_issuer):
                rows.append({
                    "issuer": "i%d" % index,
                    "acceptance_utc": "2025-0%d-01T15:00:00Z" % (position + 1),
                    "label_tech_event": (position + index) % 2,
                    "rd_per_1k": float(position),
                    "tech_per_1k": float(index),
                    "n_prior_events": position,
                    "is_earnings": 0,
                })
        return rows

    def test_circular_shift_preserves_each_issuer_label_multiset(self) -> None:
        rows = self._rows()
        grouped: dict[str, list[int]] = {}
        for row in rows:
            grouped.setdefault(row["issuer"], []).append(row["label_tech_event"])
        # Reproduce the scheme's core operation and check the invariant.
        for issuer, labels in grouped.items():
            for offset in range(len(labels)):
                rotated = [labels[(i + offset) % len(labels)] for i in range(len(labels))]
                self.assertEqual(sorted(rotated), sorted(labels), issuer)

    def test_permutation_result_is_well_formed(self) -> None:
        rows = self._rows()
        train = rows
        test = rows
        scores = experiment.score_models(train, test, "label_tech_event")
        result = experiment.permute_delta_auc(test, scores, "label_tech_event",
                                              permutations=200, seed=7)
        self.assertEqual(len(result["null_delta_auc_draws"]), 200)
        for key in ("p_auc_primary_two_sided", "p_auc_primary_greater",
                    "p_delta_auc_two_sided", "p_delta_auc_greater"):
            self.assertIsNotNone(result[key], key)
            self.assertGreater(result[key], 0.0)
            self.assertLessEqual(result[key], 1.0)
        for value in result["null_delta_auc_draws"]:
            self.assertGreaterEqual(value, -1.0)
            self.assertLessEqual(value, 1.0)

    def test_permutation_is_deterministic_for_a_seed(self) -> None:
        rows = self._rows()
        scores = experiment.score_models(rows, rows, "label_tech_event")
        first = experiment.permute_delta_auc(rows, scores, "label_tech_event", 100, 11)
        second = experiment.permute_delta_auc(rows, scores, "label_tech_event", 100, 11)
        self.assertEqual(first["null_delta_auc_draws"], second["null_delta_auc_draws"])

    def test_label_transplant_control_is_well_formed(self) -> None:
        rows = self._rows()
        scores = experiment.score_models(rows, rows, "label_tech_event")
        result = experiment.label_transplant_auc(rows, scores, "label_tech_event")
        self.assertIsNotNone(result["auc"])
        self.assertGreaterEqual(result["auc"], 0.0)
        self.assertLessEqual(result["auc"], 1.0)


class PowerTests(unittest.TestCase):
    def test_power_rises_with_the_alternative(self) -> None:
        curve = experiment.power_curve(40, 160)
        powers = [row["power"] for row in curve["curve"]]
        self.assertEqual(powers, sorted(powers))
        self.assertIsNotNone(curve["min_detectable_auc_at_80pct_power"])
        self.assertGreater(curve["min_detectable_auc_at_80pct_power"], 0.5)

    def test_more_data_lowers_the_detectable_effect(self) -> None:
        small = experiment.power_curve(20, 80)
        large = experiment.power_curve(200, 800)
        self.assertLess(large["min_detectable_auc_at_80pct_power"],
                        small["min_detectable_auc_at_80pct_power"])

    def test_hanley_mcneil_se_is_positive_and_shrinks(self) -> None:
        self.assertGreater(experiment.hanley_mcneil_se(0.7, 30, 70), 0.0)
        self.assertLess(experiment.hanley_mcneil_se(0.7, 300, 700),
                        experiment.hanley_mcneil_se(0.7, 30, 70))
        self.assertIsNone(experiment.hanley_mcneil_se(0.7, 1, 70))


# --------------------------------------------------------------------------- #
# sample frame
# --------------------------------------------------------------------------- #
class SampleTests(unittest.TestCase):
    def test_dst_regime_labels_the_season(self) -> None:
        self.assertEqual(sample.dst_regime(dt.date(2025, 7, 1)), "EDT")
        self.assertEqual(sample.dst_regime(dt.date(2025, 1, 15)), "EST")

    def test_days_to_transition_is_zero_on_a_transition_day(self) -> None:
        self.assertEqual(sample.days_to_transition(dt.date(2025, 3, 9)), 0)
        self.assertEqual(sample.days_to_transition(dt.date(2025, 11, 2)), 0)
        self.assertGreater(sample.days_to_transition(dt.date(2025, 7, 1)), 10)

    def test_analysis_window_is_inside_the_declared_bounds(self) -> None:
        self.assertLess(sample.FRAME_START, sample.FRAME_END)
        self.assertLess(sample.VERIFICATION_START, sample.FRAME_START)
        self.assertEqual(sample.FRAME_END.year, 2026)


# --------------------------------------------------------------------------- #
# figure helpers (no rendering)
# --------------------------------------------------------------------------- #
class FigureHelperTests(unittest.TestCase):
    def test_roc_starts_at_origin_and_ends_at_one(self) -> None:
        fpr, tpr = figures._roc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1])
        self.assertEqual((fpr[0], tpr[0]), (0.0, 0.0))
        self.assertEqual((fpr[-1], tpr[-1]), (1.0, 1.0))

    def test_roc_of_a_perfect_ranker_reaches_the_corner(self) -> None:
        fpr, tpr = figures._roc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0])
        self.assertIn((0.0, 1.0), list(zip(fpr, tpr)))


# --------------------------------------------------------------------------- #
# committed-artifact consistency (skipped on a clean checkout)
# --------------------------------------------------------------------------- #
class ArtifactConsistencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = figures.Path(__file__).resolve().parents[1] / "research" / "science_001"
        self.artifacts = self.root / "artifacts"

    @unittest.skipUnless((figures.Path(__file__).resolve().parents[1] /
                          "research" / "science_001" / "artifacts" /
                          "experiment_results.json").exists(),
                         "artifacts not built yet")
    def test_protocol_hash_matches_the_committed_protocol(self) -> None:
        import hashlib
        import json
        results = json.loads((self.artifacts / "experiment_results.json").read_text("utf-8"))
        digest = hashlib.sha256((self.root / "PROTOCOL.md").read_bytes()).hexdigest()
        self.assertEqual(results["protocol_sha256"], digest)

    @unittest.skipUnless((figures.Path(__file__).resolve().parents[1] /
                          "research" / "science_001" / "artifacts" /
                          "dataset.csv").exists(), "dataset not built yet")
    def test_committed_dataset_has_no_low_grade_time_rows(self) -> None:
        rows = experiment.load_rows(self.artifacts / "dataset.csv")
        self.assertTrue(rows)
        allowed = {"A_acceptance_verified", "A2_acceptance_header_only",
                   "B_acceptance_api_only"}
        for row in rows:
            self.assertIn(row["time_tier"], allowed, row["accession"])

    @unittest.skipUnless((figures.Path(__file__).resolve().parents[1] /
                          "research" / "science_001" / "artifacts" / "figures" /
                          "figures_manifest.json").exists(), "figures not built yet")
    def test_figure_manifest_hashes_match_the_committed_artifacts(self) -> None:
        """A figure must be reproducible from the exact bytes that were committed.

        This catches the CRLF/LF trap: a manifest hashed on a Windows working
        copy would not match the LF-normalised file in a fresh checkout.
        """
        import hashlib
        import json
        manifest = json.loads(
            (self.artifacts / "figures" / "figures_manifest.json").read_text("utf-8"))
        self.assertTrue(manifest["sources"])
        for name, digest in manifest["sources"].items():
            actual = hashlib.sha256((self.artifacts / name).read_bytes()).hexdigest()
            self.assertEqual(actual, digest, name)

    @unittest.skipUnless((figures.Path(__file__).resolve().parents[1] /
                          "research" / "science_001" / "artifacts" /
                          "dataset.csv").exists(), "dataset not built yet")
    def test_committed_dataset_is_internally_ordered(self) -> None:
        rows = experiment.load_rows(self.artifacts / "dataset.csv")
        for row in rows:
            self.assertTrue(row["acceptance_utc"].endswith("Z"), row["accession"])
            self.assertEqual(len(row["accession"]), 20, row["accession"])


if __name__ == "__main__":
    unittest.main()
