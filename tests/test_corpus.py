"""Offline tests for the EDGAR 8-K catalyst corpus (`medradar/corpus.py`).

No network, no SQLite: every test builds its own synthetic EDGAR hit / HTML /
corpus rows. The shapes are copied from the real responses (a live FTS hit is
embedded verbatim below) so a change in EDGAR's payload would break these tests
before it breaks a crawl.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from medradar import corpus
from medradar.util import sha1

#: One real ``hits.hits[]`` element from
#: ``https://efts.sec.gov/LATEST/search-index?q=fda+approval&forms=8-K...``
#: (2024-02-13, Immunome Inc.). Kept verbatim as the shape fixture.
REAL_FTS_HIT = {
    "_index": "edgar_file",
    "_id": "0001104659-24-019883:tm245878d1_ex99-1.htm",
    "_score": 13.278824,
    "_source": {
        "ciks": ["0001472012"],
        "period_ending": "2024-02-13",
        "file_num": ["001-39580"],
        "display_names": ["Immunome Inc.  (IMNM)  (CIK 0001472012)"],
        "xsl": None,
        "sequence": 2,
        "root_forms": ["8-K"],
        "file_date": "2024-02-13",
        "biz_states": ["PA"],
        "sics": ["2834"],
        "form": "8-K",
        "adsh": "0001104659-24-019883",
        "film_num": ["24625936"],
        "biz_locations": ["Exton, PA"],
        "file_type": "EX-99.1",
        "file_description": "EXHIBIT 99.1",
        "inc_states": ["DE"],
        "items": ["2.02", "8.01", "9.01"],
    },
}

HTML_DOC = """<html><head><title>t</title>
<style>.x { color: red; }</style>
<script>var x = "fda approval";</script>
<!-- a comment with words -->
</head><body>
<p>Acme Therapeutics Announces FDA Approval of ZYX</p>
<br/>
Third Quarter Financial Results
<div>the drug was approved by the FDA</div>
&nbsp; &#38;#8217;quoted&#38;#8217;
</body></html>"""


def _hit(
    accession: str = "0001104659-24-019883",
    document: str = "tm245878d1_ex99-1.htm",
    company: str = "Immunome Inc.",
    ticker: str = "IMNM",
    cik: str = "0001472012",
    filed: str = "2024-02-13",
    file_type: str = "EX-99.1",
    sics: tuple[str, ...] = ("2834",),
    form: str = "8-K",
    items: tuple[str, ...] = ("8.01", "9.01"),
) -> dict:
    display = f"{company}  ({ticker})  (CIK {cik})" if ticker else f"{company}  (CIK {cik})"
    return {
        "_id": f"{accession}:{document}",
        "_source": {
            "ciks": [cik],
            "display_names": [display],
            "file_date": filed,
            "form": form,
            "sics": list(sics),
            "file_type": file_type,
            "sequence": 2,
            "root_forms": ["8-K"],
            "items": list(items),
        },
    }


def _candidate(accession: str = "0001104659-24-019883", **kwargs) -> dict:
    hit = _hit(accession=accession, **kwargs)
    candidate = corpus.parse_fts_hit(hit, bucket="fda approval", window="2024Q1")
    assert candidate is not None
    return candidate


def _record(**overrides) -> dict:
    base = {
        "accession": "0001104659-24-019883",
        "cik": 1472012,
        "company": "Immunome Inc.",
        "ticker": "IMNM",
        "company_key": "",
        "filed": "2024-02-13",
        "form": "8-K",
        "document": "tm245878d1_ex99-1.htm",
        "url": corpus.filing_url(1472012, "0001104659-24-019883", "tm245878d1_ex99-1.htm"),
        "buckets": ["fda approval"],
        "windows": ["2024Q1"],
        "items": ["8.01", "9.01"],
        "category": "approval",
        "direction": 1,
        "classification": {"reasons": ["bucket:fda approval"], "confidence": 0.6, "scores": {}},
        "text": "Acme announces FDA approval of ZYX.",
        "text_chars": 37,
        "raw_chars": 1000,
        "fetched_at": "2026-10-31T03:00:00Z",
        "fetch_status": "ok",
        "source": corpus.SOURCE,
        "corpus_version": corpus.CORPUS_VERSION,
    }
    base.update(overrides)
    return base


class CleanHtmlTests(unittest.TestCase):
    def test_strips_scripts_styles_comments_and_tags(self) -> None:
        text = corpus.clean_html(HTML_DOC)
        self.assertNotIn("<", text)
        self.assertNotIn("var x", text)  # script body is not prose
        self.assertNotIn("color: red", text)
        self.assertNotIn("a comment with words", text)
        self.assertIn("Acme Therapeutics Announces FDA Approval of ZYX", text)
        self.assertIn("approved by the FDA", text)

    def test_block_tags_become_newlines(self) -> None:
        text = corpus.clean_html("<p>one</p><p>two</p><br/>three")
        self.assertEqual(text, "one\ntwo\nthree")

    def test_double_encoded_entities_are_decoded(self) -> None:
        text = corpus.clean_html("&#38;#8217;the drug&#38;#8217; &amp;nbsp; end")
        self.assertIn("\u2019the drug\u2019", text)
        self.assertNotIn("&#38;", text)
        self.assertNotIn("&amp;", text)

    def test_empty_and_plain_input(self) -> None:
        self.assertEqual(corpus.clean_html(""), "")
        self.assertEqual(corpus.clean_html("plain text"), "plain text")

    def test_truncate_text_caps_storage(self) -> None:
        stored = corpus.truncate_text("x" * 50_000)
        self.assertEqual(len(stored), corpus.MAX_TEXT_CHARS)
        self.assertTrue(stored.endswith("\u2026"))
        self.assertEqual(corpus.truncate_text("short"), "short")


class CompanyTests(unittest.TestCase):
    def test_parse_display_name_with_ticker_and_cik(self) -> None:
        parsed = corpus.parse_display_name("Immunome Inc.  (IMNM)  (CIK 0001472012)")
        self.assertEqual(parsed["name"], "Immunome Inc.")
        self.assertEqual(parsed["ticker"], "IMNM")
        self.assertEqual(parsed["cik"], 1472012)

    def test_parse_display_name_without_ticker(self) -> None:
        parsed = corpus.parse_display_name("Acme Therapeutics (CIK 0001234567)")
        self.assertEqual(parsed["name"], "Acme Therapeutics")
        self.assertEqual(parsed["ticker"], "")
        self.assertEqual(parsed["cik"], 1234567)

    def test_parse_display_name_bare(self) -> None:
        parsed = corpus.parse_display_name("  Some   Company  ")
        self.assertEqual(parsed["name"], "Some Company")
        self.assertIsNone(parsed["cik"])

    def test_healthcare_name_markers(self) -> None:
        for name in ("Acme Therapeutics", "BioNova Inc.", "Genomics Co", "Oncology Partners",
                     "Canopy Health", "Immunome Inc.", "Derma Sciences"):
            self.assertTrue(corpus.is_healthcare_company(name), name)
        self.assertFalse(corpus.is_healthcare_company("Aehr Test Systems"))
        self.assertFalse(corpus.is_healthcare_company(""))
        # markers are case-insensitive
        self.assertTrue(corpus.is_healthcare_company("acme therapeutics"))

    def test_healthcare_sic_fallback(self) -> None:
        # an opaque legal name with no healthcare marker is only rescued by SIC
        self.assertFalse(corpus.is_healthcare_company("Zevra Corp"))
        self.assertTrue(corpus.is_healthcare_company("Zevra Corp", ("2834",)))
        self.assertTrue(corpus.is_healthcare_company("Opaque Corp", ["3841"]))
        self.assertFalse(corpus.is_healthcare_company("Opaque Corp", ("7372",)))


class FtsHitTests(unittest.TestCase):
    def test_filing_url(self) -> None:
        url = corpus.filing_url(1472012, "0001104659-24-019883", "doc.htm")
        self.assertEqual(
            url,
            "https://www.sec.gov/Archives/edgar/data/1472012/"
            "000110465924019883/doc.htm",
        )
        # zero-padded CIKs collapse to the canonical Archives form
        self.assertEqual(
            corpus.filing_url("0001472012", "0001-01-000001", "a"),
            "https://www.sec.gov/Archives/edgar/data/1472012/000101000001/a",
        )

    def test_parse_real_hit(self) -> None:
        candidate = corpus.parse_fts_hit(REAL_FTS_HIT, "fda approval", "2024Q1")
        assert candidate is not None
        self.assertEqual(candidate["accession"], "0001104659-24-019883")
        self.assertEqual(candidate["cik"], 1472012)
        self.assertEqual(candidate["company"], "Immunome Inc.")
        self.assertEqual(candidate["ticker"], "IMNM")
        self.assertEqual(candidate["filed"], "2024-02-13")
        self.assertEqual(candidate["buckets"], ["fda approval"])
        self.assertEqual(candidate["windows"], ["2024Q1"])
        self.assertEqual(candidate["items"], ["2.02", "8.01", "9.01"])
        self.assertTrue(candidate["url"].endswith("/tm245878d1_ex99-1.htm"))

    def test_parse_rejects_malformed_ids(self) -> None:
        self.assertIsNone(corpus.parse_fts_hit({"_id": "nocolon", "_source": {}}, "fda approval"))
        self.assertIsNone(corpus.parse_fts_hit({"_source": {}}, "fda approval"))
        self.assertIsNone(corpus.parse_fts_hit({"not": "a hit"}, "fda approval"))

    def test_parse_rejects_bad_accession_and_forms(self) -> None:
        bad_accession = _hit(accession="12345")
        self.assertIsNone(corpus.parse_fts_hit(bad_accession, "fda approval"))
        ten_k = _hit(form="10-K")
        self.assertIsNone(corpus.parse_fts_hit(ten_k, "fda approval"))
        amendment = _hit(form="8-K/A")
        self.assertIsNotNone(corpus.parse_fts_hit(amendment, "fda approval"))

    def test_parse_rejects_non_healthcare(self) -> None:
        hit = _hit(company="Aehr Test Systems", ticker="AEHR", sics=("7372",))
        self.assertIsNone(corpus.parse_fts_hit(hit, "fda approval", "2024Q1"))
        # ... but a healthcare SIC rescues an opaque name
        rescued = _hit(company="Immunome Inc.", ticker="IMNM", sics=("2834",))
        self.assertIsNotNone(corpus.parse_fts_hit(rescued, "fda approval"))


class MergeCandidatesTests(unittest.TestCase):
    def test_dedupes_by_accession_and_unions_buckets(self) -> None:
        first = _candidate(document="cover.htm", file_type="EX-99.1")
        second = _candidate(document="press.htm", file_type="EX-99.1")
        second["buckets"] = ["financial results"]
        second["windows"] = ["2024Q2"]
        merged = corpus.merge_candidates([first, second])
        self.assertEqual(len(merged), 1)
        self.assertEqual(
            merged[0]["buckets"], ["fda approval", "financial results"]
        )
        self.assertEqual(merged[0]["windows"], ["2024Q1", "2024Q2"])

    def test_higher_priority_bucket_replaces_document(self) -> None:
        low = _candidate(accession="0001104659-24-000001", document="earnings.htm")
        low["buckets"] = ["financial results"]
        high = _candidate(accession="0001104659-24-000001", document="crl.htm")
        high["buckets"] = ["complete response letter"]
        merged = corpus.merge_candidates([low, high])
        self.assertEqual(merged[0]["document"], "crl.htm")

    def test_sorted_by_filed_then_accession(self) -> None:
        a = _candidate(accession="0001104659-24-000002", filed="2024-02-01")
        b = _candidate(accession="0001104659-24-000001", filed="2024-02-01")
        c = _candidate(accession="0001104659-24-000003", filed="2023-12-31")
        merged = corpus.merge_candidates([a, b, c])
        self.assertEqual([row["accession"] for row in merged],
                         ["0001104659-24-000003", "0001104659-24-000001", "0001104659-24-000002"])

    def test_empty(self) -> None:
        self.assertEqual(corpus.merge_candidates([]), [])


class ClassifyTests(unittest.TestCase):
    def test_crl_wins(self) -> None:
        detail = corpus.classify_detail(
            "The Company received a Complete Response Letter from the U.S. FDA.",
            ["complete response letter"],
        )
        self.assertEqual(detail["category"], "crl")
        self.assertEqual(detail["direction"], -1)
        self.assertEqual(detail["confidence"], 1.0)

    def test_trial_miss_is_negative(self) -> None:
        detail = corpus.classify_detail(
            "The Phase 3 trial did not meet the primary endpoint.", ["did not meet"]
        )
        self.assertEqual(detail["category"], "trial_result")
        self.assertEqual(detail["direction"], -1)

    def test_trial_hit_is_positive(self) -> None:
        detail = corpus.classify_detail(
            "Announces positive topline results: the study met the primary endpoint.",
            ["met the primary endpoint"],
        )
        self.assertEqual(detail["category"], "trial_result")
        self.assertEqual(detail["direction"], 1)

    def test_approval(self) -> None:
        detail = corpus.classify_detail(
            "FDA approval of ZYX was granted today.", ["fda approval"]
        )
        self.assertEqual(detail["category"], "approval")
        self.assertEqual(detail["direction"], 1)

    def test_earnings_beats_boilerplate_approval_mention(self) -> None:
        detail = corpus.classify_detail(
            "Reports Third Quarter 2024 Financial Results. Following FDA approval in March, "
            "revenue of $10 million was recorded.",
            ["financial results"],
        )
        self.assertEqual(detail["category"], "earnings")
        self.assertEqual(detail["direction"], 0)

    def test_approval_beats_boilerplate_earnings_mention(self) -> None:
        detail = corpus.classify_detail(
            "Announces FDA approval of ZYX. The company will report financial results next month.",
            ["fda approval", "financial results"],
        )
        self.assertEqual(detail["category"], "approval")

    def test_bucket_only_evidence(self) -> None:
        detail = corpus.classify_detail("The company announced today.", ["fda approval"])
        self.assertEqual(detail["category"], "approval")
        self.assertEqual(detail["confidence"], 0.4)  # body-level bucket mention only
        self.assertIn("bucket:fda approval", detail["reasons"])

    def test_item_202_is_authoritative_earnings(self) -> None:
        # EDGAR metadata wins over keywords: Item 2.02 == results of operations
        detail = corpus.classify_detail("The company filed this report.", [], ["2.02", "9.01"])
        self.assertEqual(detail["category"], "earnings")
        self.assertEqual(detail["confidence"], 0.8)
        self.assertIn("item:2.02", detail["reasons"])

    def test_financing_release_is_other(self) -> None:
        """A debt-facility 8-K that mentions FDA approval in the body is not a catalyst."""
        text = (
            "Acme Therapeutics Enters into a $400 Million Debt Facility with Oxford Finance. "
            "The facility strengthens financial flexibility and follows the FDA approval of ZYX."
        )
        detail = corpus.classify_detail(text, ["receives fda approval"])
        self.assertEqual(detail["category"], "other")

    def test_presentation_is_other(self) -> None:
        text = (
            "CORPORATE PRESENTATION Acme Therapeutics. This deck reviews the Phase 3 "
            "program that met the primary endpoint last year."
        )
        detail = corpus.classify_detail(text, ["met the primary endpoint"])
        self.assertEqual(detail["category"], "other")

    def test_lead_evidence_beats_body_evidence(self) -> None:
        """Trial language buried after 2k chars of boilerplate is weak evidence."""
        body_only = "Acme Therapeutics filed this report. " + "x" * 2000 + " The trial did not meet the primary endpoint."
        detail = corpus.classify_detail(body_only, [])
        self.assertEqual(detail["category"], "trial_result")
        self.assertEqual(detail["direction"], -1)
        self.assertEqual(detail["confidence"], 0.4)  # body evidence only
        financing = (
            "Acme Therapeutics Enters into a $400 Million Debt Facility. " + "x" * 100
            + " The trial did not meet the primary endpoint."
        )
        self.assertEqual(corpus.classify(financing, []), "other")

    def test_unknown_text_is_other(self) -> None:
        detail = corpus.classify_detail("Nothing of note happened.", [])
        self.assertEqual(detail["category"], "other")
        self.assertEqual(detail["direction"], 0)
        self.assertEqual(detail["confidence"], 0.0)
        self.assertEqual(corpus.classify("nothing", []), "other")

    def test_direction_zero_when_trial_result_has_no_polarity(self) -> None:
        detail = corpus.classify_detail("Topline data are coming.", ["did not meet"])
        self.assertEqual(detail["category"], "trial_result")
        # only the bucket matched; no text polarity -> unknown direction, not +1
        self.assertEqual(detail["direction"], 0)


class RecordTests(unittest.TestCase):
    def test_build_record_fields_and_truncation(self) -> None:
        candidate = _candidate()
        record = corpus.build_record(
            candidate, "x" * 30_000, raw_chars=40_000, fetched_at="2026-10-31T03:00:00Z"
        )
        self.assertEqual(record["accession"], candidate["accession"])
        self.assertEqual(record["source"], corpus.SOURCE)
        self.assertEqual(record["corpus_version"], corpus.CORPUS_VERSION)
        self.assertEqual(record["text_chars"], corpus.MAX_TEXT_CHARS)
        self.assertEqual(len(record["text"]), corpus.MAX_TEXT_CHARS)
        self.assertEqual(record["raw_chars"], 40_000)
        self.assertEqual(record["category"], "approval")
        self.assertEqual(record["buckets"], ["fda approval"])

    def test_build_record_orders_buckets_and_merges_extra(self) -> None:
        candidate = _candidate()
        candidate["buckets"] = ["financial results", "fda approval"]
        record = corpus.build_record(candidate, "financial results", extra={"company_key": "acme"})
        self.assertEqual(record["buckets"], ["fda approval", "financial results"])
        self.assertEqual(record["company_key"], "acme")
        self.assertEqual(record["items"], ["8.01", "9.01"])

    def test_build_record_item_override(self) -> None:
        candidate = _candidate()
        candidate["items"] = []
        without = corpus.build_record(candidate, "The company filed this report.")
        self.assertEqual(without["category"], "approval")  # bucket evidence only
        with_item = corpus.build_record(
            candidate, "The company filed this report.", items=["2.02"]
        )
        self.assertEqual(with_item["category"], "earnings")
        self.assertEqual(with_item["items"], ["2.02"])

    def test_corpus_sha1_is_stable_and_ignores_fetch_time(self) -> None:
        one = _record(fetched_at="2026-01-01T00:00:00Z")
        two = _record(fetched_at="2026-10-31T00:00:00Z")
        self.assertEqual(corpus.corpus_sha1([one]), corpus.corpus_sha1([two]))
        changed = _record(text="different text", text_chars=14)
        self.assertNotEqual(corpus.corpus_sha1([one]), corpus.corpus_sha1([changed]))
        # order does not matter
        other = _record(accession="0001104659-24-000009", filed="2023-01-01")
        self.assertEqual(
            corpus.corpus_sha1([one, other]), corpus.corpus_sha1([other, one])
        )


class IoAndSummaryTests(unittest.TestCase):
    def test_write_and_load_roundtrip(self) -> None:
        rows = [
            _record(accession="0001104659-24-000002", filed="2024-02-01"),
            _record(accession="0001104659-24-000001", filed="2024-01-01"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            written = corpus.write_corpus(rows, tmp)
            self.assertEqual(written["n"], 2)
            self.assertEqual(written["sha1"], corpus.corpus_sha1(rows))
            path = Path(written["path"])
            self.assertTrue(path.exists())
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            first = json.loads(lines[0])
            self.assertEqual(first["accession"], "0001104659-24-000001")  # sorted by filed
            loaded = corpus.load_corpus(path)
            self.assertEqual([row["accession"] for row in loaded],
                             ["0001104659-24-000001", "0001104659-24-000002"])

    def test_load_corpus_missing_is_empty(self) -> None:
        self.assertEqual(corpus.load_corpus(Path("does-not-exist.jsonl")), [])

    def test_read_jsonl_skips_blank_and_bad_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.jsonl"
            path.write_text('{"a": 1}\n\nnot json\n{"b": 2}\n', encoding="utf-8")
            self.assertEqual(corpus.read_jsonl(path), [{"a": 1}, {"b": 2}])

    def test_summarize_distributions(self) -> None:
        rows = [
            _record(accession="a1", filed="2024-02-13", category="approval",
                    buckets=["fda approval"], direction=1),
            _record(accession="a2", filed="2024-05-01", category="crl",
                    buckets=["complete response letter"], direction=-1),
            _record(accession="a3", filed="2025-01-02", category="earnings",
                    buckets=["financial results"], direction=0),
        ]
        summary = corpus.summarize(rows)
        self.assertEqual(summary["n"], 3)
        self.assertEqual(summary["unique_accessions"], 3)
        self.assertEqual(summary["by_category"]["approval"], 1)
        self.assertEqual(summary["by_category"]["crl"], 1)
        self.assertEqual(summary["by_category"]["trial_result"], 0)
        self.assertEqual(summary["by_year"], {"2024": 2, "2025": 1})
        self.assertEqual(summary["by_direction"], {"-1": 1, "0": 1, "1": 1})
        self.assertEqual(summary["date_range"], {"start": "2024-02-13", "end": "2025-01-02"})
        self.assertEqual(summary["with_text"], 3)
        self.assertGreater(summary["avg_text_chars"], 0)
        self.assertEqual(summary["by_bucket"]["fda approval"], 1)

    def test_summarize_empty(self) -> None:
        summary = corpus.summarize([])
        self.assertEqual(summary["n"], 0)
        self.assertEqual(summary["by_category"], {c: 0 for c in corpus.CATEGORIES})
        self.assertIsNone(summary["date_range"]["start"])
        self.assertEqual(summary["avg_text_chars"], 0.0)

    def test_summarize_copies_failure_rate_from_manifest(self) -> None:
        manifest = {"fetch": {"failed": 7, "failure_rate": 0.07}}
        summary = corpus.summarize([_record()], manifest=manifest)
        self.assertEqual(summary["fetch_failures"], 7)
        self.assertAlmostEqual(summary["failure_rate"], 0.07)

    def test_build_manifest(self) -> None:
        rows = [_record(), _record(accession="0001104659-24-000009", filed="2023-01-01",
                                   category="earnings", buckets=["financial results"])]
        manifest = corpus.build_manifest(
            rows,
            search={"queries": 224, "candidates_unique": 2},
            fetch={"attempted": 2, "ok": 2, "failed": 0},
            window={"start": "2019-01-01", "end": "2026-10-31"},
            user_agent="test-agent",
        )
        self.assertEqual(manifest["schema"], "edgar-corpus-manifest-v1")
        self.assertEqual(manifest["corpus"]["n"], 2)
        self.assertEqual(manifest["corpus"]["sha1"], corpus.corpus_sha1(rows))
        self.assertEqual(manifest["corpus"]["by_year"], {"2023": 1, "2024": 1})
        self.assertEqual(manifest["search"]["queries"], 224)
        self.assertEqual(manifest["source"]["forms"], "8-K")
        self.assertEqual(manifest["source"]["user_agent"], "test-agent")
        self.assertTrue(manifest["notes_zh"])
        self.assertEqual(manifest["window"]["start"], "2019-01-01")


class StratifiedSubsetTests(unittest.TestCase):
    def _rows(self, per_year: int = 10, years: tuple[str, ...] = ("2019", "2020", "2021", "2022")) -> list[dict]:
        rows = []
        for year in years:
            for index in range(per_year):
                rows.append(
                    {
                        "accession": f"{year}-{index:03d}",
                        "filed": f"{year}-01-{(index % 28) + 1:02d}",
                    }
                )
        return rows

    def test_returns_everything_when_limit_is_large(self) -> None:
        rows = self._rows(per_year=3)
        self.assertEqual(corpus.stratified_subset(rows, 0), rows)
        self.assertEqual(len(corpus.stratified_subset(rows, 999)), len(rows))

    def test_stratifies_across_years(self) -> None:
        rows = self._rows(per_year=10)
        subset = corpus.stratified_subset(rows, 20)
        self.assertEqual(len(subset), 20)
        years = {row["filed"][:4] for row in subset}
        self.assertEqual(years, {"2019", "2020", "2021", "2022"})
        # deterministic regardless of input order
        shuffled = list(reversed(rows))
        self.assertEqual(subset, corpus.stratified_subset(shuffled, 20))
        # every picked row comes from the input
        self.assertTrue({row["accession"] for row in subset} <= {row["accession"] for row in rows})

    def test_budget_smaller_than_year_count(self) -> None:
        rows = self._rows(per_year=5)
        subset = corpus.stratified_subset(rows, 2)
        self.assertEqual(len(subset), 2)
        self.assertEqual({row["filed"][:4] for row in subset}, {"2019", "2020"})

    def test_single_year_is_trimmed_evenly(self) -> None:
        rows = self._rows(per_year=20, years=("2024",))
        subset = corpus.stratified_subset(rows, 5)
        self.assertEqual(len(subset), 5)
        self.assertTrue(all(row["filed"].startswith("2024") for row in subset))


class V2BucketTests(unittest.TestCase):
    NEW_BUCKETS = (
        "fda approves",
        "phase 3 results",
        "topline data",
        "clinical hold",
        "refuse to file",
        "breakthrough therapy",
        "priority review",
        "label expansion",
        "accelerated approval",
    )

    def test_v2_bucket_set_is_the_v1_set_plus_nine(self) -> None:
        self.assertEqual(len(corpus.BUCKETS_V2), 16)
        self.assertEqual(corpus.BUCKETS_V2[:7], corpus.BUCKET_ORDER)
        for bucket in self.NEW_BUCKETS:
            self.assertIn(bucket, corpus.BUCKETS_V2)
            self.assertNotIn(bucket, corpus.BUCKET_ORDER)
            self.assertIn(bucket, corpus.BUCKET_CATEGORY)

    def test_v2_buckets_map_to_the_five_known_categories(self) -> None:
        for bucket in corpus.BUCKETS_V2:
            self.assertIn(corpus.BUCKET_CATEGORY[bucket], corpus.CATEGORIES)
        self.assertEqual(corpus.BUCKET_CATEGORY["fda approves"], "approval")
        self.assertEqual(corpus.BUCKET_CATEGORY["phase 3 results"], "trial_result")
        self.assertEqual(corpus.BUCKET_CATEGORY["topline data"], "trial_result")
        self.assertEqual(corpus.BUCKET_CATEGORY["clinical hold"], "crl")
        self.assertEqual(corpus.BUCKET_CATEGORY["refuse to file"], "crl")
        self.assertEqual(corpus.BUCKET_CATEGORY["breakthrough therapy"], "other")
        self.assertEqual(corpus.BUCKET_CATEGORY["priority review"], "other")
        self.assertEqual(corpus.BUCKET_CATEGORY["label expansion"], "approval")
        self.assertEqual(corpus.BUCKET_CATEGORY["accelerated approval"], "approval")

    def test_classify_new_buckets(self) -> None:
        self.assertEqual(corpus.classify("filed today", ["phase 3 results"]), "trial_result")
        hold = corpus.classify_detail("The program is paused.", ["clinical hold"])
        self.assertEqual(hold["category"], "crl")
        self.assertEqual(hold["direction"], -1)
        rtf = corpus.classify_detail("The application was rejected.", ["refuse to file"])
        self.assertEqual(rtf["category"], "crl")
        self.assertEqual(rtf["direction"], -1)
        breakthrough = corpus.classify_detail("Designation granted.", ["breakthrough therapy"])
        self.assertEqual(breakthrough["category"], "other")
        self.assertEqual(breakthrough["direction"], 0)
        label = corpus.classify_detail("New indication approved.", ["label expansion"])
        self.assertEqual(label["category"], "approval")

    def test_parse_carries_new_buckets(self) -> None:
        candidate = corpus.parse_fts_hit(_hit(), "clinical hold", "2016H1")
        assert candidate is not None
        self.assertEqual(candidate["buckets"], ["clinical hold"])
        self.assertEqual(candidate["windows"], ["2016H1"])

    def test_merge_preserves_new_buckets_with_v2_order(self) -> None:
        one = _candidate(accession="0001104659-24-000010")
        one["buckets"] = ["priority review"]
        two = _candidate(accession="0001104659-24-000010", document="crl.htm")
        two["buckets"] = ["refuse to file"]
        merged = corpus.merge_candidates([one, two], bucket_order=corpus.BUCKETS_V2)
        self.assertEqual(merged[0]["buckets"], ["refuse to file", "priority review"])
        self.assertEqual(merged[0]["document"], "crl.htm")

    def test_build_record_uses_v2_bucket_order(self) -> None:
        candidate = _candidate()
        candidate["buckets"] = ["accelerated approval", "fda approval"]
        record = corpus.build_record(candidate, "fda approval", bucket_order=corpus.BUCKETS_V2)
        self.assertEqual(record["buckets"], ["fda approval", "accelerated approval"])

    def test_summarize_reports_all_v2_buckets(self) -> None:
        rows = [
            _record(buckets=["clinical hold"], accession="a1", filed="2016-02-01"),
            _record(buckets=["priority review"], accession="a2", filed="2024-02-01"),
        ]
        summary = corpus.summarize(rows, bucket_order=corpus.BUCKETS_V2)
        self.assertEqual(len(summary["by_bucket"]), 16)
        self.assertEqual(summary["by_bucket"]["clinical hold"], 1)
        self.assertEqual(summary["by_bucket"]["priority review"], 1)
        manifest = corpus.build_manifest(
            rows, buckets=corpus.BUCKETS_V2, bucket_order=corpus.BUCKETS_V2
        )
        self.assertEqual(len(manifest["corpus"]["by_bucket"]), 16)
        self.assertEqual(len(manifest["buckets"]), 16)


class MergeCorporaTests(unittest.TestCase):
    def test_union_by_accession_and_longest_text_wins(self) -> None:
        v1 = [_record(accession="a1", text="short", text_chars=5, buckets=["fda approval"], windows=[]),
              _record(accession="a2", text="v1 only", text_chars=7, windows=[])]
        v2 = [_record(accession="a1", text="a much longer announcement text", text_chars=30,
                      buckets=["clinical hold"], windows=["2016H1"]),
              _record(accession="a3", text="new in v2", text_chars=11)]
        merged = corpus.merge_corpora([v1, v2], bucket_order=corpus.BUCKETS_V2)
        self.assertEqual({row["accession"] for row in merged}, {"a1", "a2", "a3"})
        a1 = next(row for row in merged if row["accession"] == "a1")
        self.assertEqual(a1["text_chars"], 30)
        self.assertEqual(a1["buckets"], ["fda approval", "clinical hold"])
        self.assertEqual(a1["windows"], ["2016H1"])

    def test_keeps_current_record_when_text_is_not_longer(self) -> None:
        first = [_record(accession="a1", text="longer text", text_chars=20,
                         buckets=["fda approval"], windows=[])]
        second = [_record(accession="a1", text="short", text_chars=5,
                          buckets=["priority review"], windows=["2016H1"])]
        merged = corpus.merge_corpora([first, second], bucket_order=corpus.BUCKETS_V2)
        self.assertEqual(merged[0]["text_chars"], 20)
        self.assertEqual(merged[0]["buckets"], ["fda approval", "priority review"])
        self.assertEqual(merged[0]["windows"], ["2016H1"])

    def test_sorted_and_empty(self) -> None:
        rows = corpus.merge_corpora([[ _record(accession="b", filed="2024-01-02"),
                                      _record(accession="a", filed="2023-01-02") ]])
        self.assertEqual([row["accession"] for row in rows], ["a", "b"])
        self.assertEqual(corpus.merge_corpora([]), [])
        self.assertEqual(corpus.merge_corpora([[], []]), [])

    def test_unknown_buckets_are_preserved(self) -> None:
        rows = corpus.merge_corpora([[_record(buckets=["fda approval", "made up bucket"])]])
        self.assertEqual(rows[0]["buckets"], ["fda approval", "made up bucket"])


class EventMappingTests(unittest.TestCase):
    def test_to_events_shape_and_deterministic_ids(self) -> None:
        rows = [_record(company_key="acme")]
        first = corpus.to_events(rows)
        second = corpus.to_events(rows)
        self.assertEqual(first, second)
        event = first[0]
        self.assertEqual(event["source"], corpus.SOURCE)
        self.assertEqual(event["kind"], corpus.KIND)
        self.assertEqual(event["event_date"], "2024-02-13")
        self.assertEqual(event["company_key"], "acme")
        self.assertEqual(event["ticker"], "IMNM")
        self.assertEqual(
            event["event_id"], sha1("|".join([corpus.SOURCE, corpus.KIND,
                                               "0001104659-24-019883"]))[:32]
        )
        self.assertIn("accession", event["payload"])
        self.assertEqual(event["payload"]["category"], "approval")
        self.assertIn("获批", event["title"])

    def test_to_events_unknown_company_key_and_skips(self) -> None:
        rows = [
            _record(company_key=""),
            _record(accession=""),                     # no id -> skipped
            _record(accession="a5", filed=""),         # no date -> skipped
        ]
        events = corpus.to_events(rows)
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0]["company_key"])

    def test_event_ids_are_unique_across_accessions(self) -> None:
        events = corpus.to_events([
            _record(accession="0001104659-24-000001"),
            _record(accession="0001104659-24-000002"),
        ])
        self.assertEqual(len({event["event_id"] for event in events}), 2)


if __name__ == "__main__":
    unittest.main()
