"""Offline tests for the OpenAlex publication and USPTO patent adapters.

All JSON below is a *synthetic fixture shaped like a recorded API response*; no
test in this file makes a network request. The fixture is deliberately small and
is labelled synthetic so it can never be mistaken for collected data.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from medradar.db import DB
from medradar.intelligence.features.publication_features import (
    PATENT_FEATURES,
    PUBLICATION_FEATURES,
    attach_patent_features,
    attach_publication_features,
    patent_feature_coverage,
    patent_features,
    publication_features,
    publication_feature_coverage,
    publication_knowledge_date,
    usable_publication_years,
)
from medradar.intelligence.sources import patents, publications
from medradar.intelligence.storage import IntelligenceStore

# SYNTHETIC fixture (not recorded data): 8 annual groups 2018-2025.
SYNTHETIC_GROUPED = {
    "meta": {"count": 1234, "groups_count": 8, "cost_usd": 0.001, "notice": "synthetic fixture"},
    "group_by": [
        {"key": "2025", "count": 12},
        {"key": "2024", "count": 500},
        {"key": "2023", "count": 300},
        {"key": "2022", "count": 200},
        {"key": "2021", "count": 100},
        {"key": "2020", "count": 80},
        {"key": "2019", "count": 54},
        {"key": "2018", "count": 0},
        {"key": "unknown", "count": 1},
    ],
}

SYNTHETIC_COMPANIES = [
    {"key": "acme", "name_en": "Acme Devices", "aliases": ["ACME DEVICES", "ACME"]},
    {"key": "beta", "name_en": "Beta Medical", "aliases": ["BETA MEDICAL"]},
]


def _open_store(tmp: str) -> IntelligenceStore:
    return IntelligenceStore(DB(Path(tmp) / "publications.sqlite"))


class PublicationCollectionTests(unittest.TestCase):
    def test_grouped_response_parse_and_partial_years(self) -> None:
        parsed = publications.parse_grouped_counts(SYNTHETIC_GROUPED)
        self.assertEqual(parsed["counts"], {2018: 0, 2019: 54, 2020: 80, 2021: 100,
                                            2022: 200, 2023: 300, 2024: 500, 2025: 12})
        self.assertEqual(parsed["total_works"], 1234)
        self.assertEqual(parsed["cost_usd"], 0.001)
        # invalid group keys are dropped, not guessed
        self.assertNotIn("unknown", parsed["counts"])

    def test_query_shape_is_one_grouped_request_per_company(self) -> None:
        company = SYNTHETIC_COMPANIES[0]
        alias = publications.preferred_alias(company)
        self.assertEqual(alias, "ACME DEVICES")
        query = publications.build_query(alias, start_year=2014)
        self.assertEqual(query["group_by"], "publication_year")
        self.assertIn("raw_affiliation_strings.search:ACME DEVICES", query["filter"])
        self.assertIn("from_publication_date:2014-01-01", query["filter"])
        self.assertEqual(publications.preferred_alias({"key": "x", "name_en": "X Corp", "aliases": []}),
                         "X Corp")

    def test_collect_persists_counts_and_replays_offline_from_cache(self) -> None:
        def fake_request(fetcher, url, retries, backoff, body=None):
            fetcher.stats["requests"] += 1
            return SYNTHETIC_GROUPED

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            with _open_store(tmp) as store:
                with patch.object(publications.Fetcher, "_request_json", autospec=True,
                                  side_effect=fake_request):
                    live_fetcher = publications.Fetcher(cache_dir=cache, min_interval=0)
                    live = publications.collect(store, SYNTHETIC_COMPANIES, fetcher=live_fetcher,
                                                cache_dir=cache)
                self.assertEqual(live["companies_requested"], 2)
                self.assertEqual(live["companies_with_data"], 2)
                self.assertEqual(live["companies_failed"], 0)
                self.assertEqual(live["request_stats"]["requests"], 2)
                self.assertIn("ACME DEVICES", live["per_company"]["acme"]["query"])
                self.assertEqual(live["per_company"]["acme"]["alias"], "ACME DEVICES")
                self.assertEqual(live["per_company"]["acme"]["years"][2024], 500)
                self.assertEqual(publications.load_counts(store)["acme"][2024], 500)
                # exact one request per company
                self.assertEqual(len(live_fetcher.stats), 4)
                self.assertEqual(live_fetcher.stats["requests"], 2)

                offline_fetcher = publications.Fetcher(cache_dir=cache, offline=True, min_interval=0)
                replay = publications.collect(store, SYNTHETIC_COMPANIES, fetcher=offline_fetcher,
                                              cache_dir=cache, offline=True)
                self.assertEqual(replay["companies_with_data"], 2)
                self.assertEqual(replay["companies_failed"], 0)
                self.assertEqual(replay["live_requests_this_run"], 0)
                self.assertEqual(replay["request_stats"], live["request_stats"])
                for key in ("acme", "beta"):
                    self.assertEqual(replay["per_company"][key]["years"],
                                     live["per_company"][key]["years"])
                    self.assertEqual(replay["per_company"][key]["retrieved_at"],
                                     live["per_company"][key]["retrieved_at"])
                self.assertEqual(publications.load_counts(store)["acme"], live["per_company"]["acme"]["years"])

    def test_offline_miss_is_reported_not_fabricated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "empty-cache"
            with _open_store(tmp) as store:
                fetcher = publications.Fetcher(cache_dir=cache, offline=True, min_interval=0)
                result = publications.collect(store, SYNTHETIC_COMPANIES, fetcher=fetcher,
                                              cache_dir=cache, offline=True)
            self.assertEqual(result["companies_failed"], 2)
            self.assertEqual(result["companies_with_data"], 0)
            self.assertEqual(result["total_works"], 0)


class PublicationFeatureTests(unittest.TestCase):
    def test_knowledge_date_and_usable_years(self) -> None:
        self.assertEqual(publication_knowledge_date(2024).isoformat(), "2025-02-15")
        # A 2024 annual count is not known at a 2024-10-01 cutoff.
        self.assertEqual(usable_publication_years("2024-10-01")[-1], 2023)
        # Neither at 2025-01-01 (February lag), but it is known by 2025-03-01.
        self.assertEqual(usable_publication_years("2025-01-01")[-1], 2023)
        self.assertEqual(usable_publication_years("2025-03-01")[-1], 2024)

    def test_features_never_use_partial_or_future_years(self) -> None:
        counts = {2021: 10, 2022: 20, 2023: 30, 2024: 40, 2025: 999}
        early = publication_features(counts, "2024-10-01")
        self.assertEqual(early["pub_count_prev_year"], 30.0)   # 2023, not 2024
        self.assertEqual(early["pub_count_3y"], 60.0)          # 2021+2022+2023
        self.assertEqual(early["pub_missing"], 0.0)
        later = publication_features(counts, "2025-03-01")
        self.assertEqual(later["pub_count_prev_year"], 40.0)   # 2024 now known
        self.assertEqual(later["pub_count_3y"], 90.0)          # 2022+2023+2024
        # The 2025 partial year is never used even though it is stored.
        self.assertNotIn(999.0, [later["pub_count_prev_year"], later["pub_count_3y"]])

    def test_growth_and_intensity_math_is_none_safe(self) -> None:
        features = publication_features({2021: 10, 2022: 20, 2023: 30}, "2024-10-01")
        self.assertAlmostEqual(features["pub_growth_prev_year"], 0.5)       # 30 vs 20
        self.assertAlmostEqual(features["pub_intensity_vs_company"], 1.5)   # 30 / (60/3)
        flat = publication_features({2022: 0, 2023: 5}, "2024-10-01")
        self.assertIsNone(flat["pub_growth_prev_year"])                     # no divide by zero
        self.assertAlmostEqual(flat["pub_intensity_vs_company"], 3.0)       # 5 / max(5/3, 1)
        no_data = publication_features({}, "2024-10-01")
        self.assertEqual(no_data, {name: None for name in PUBLICATION_FEATURES} | {"pub_missing": 1.0})

    def test_attach_features_to_examples_and_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _open_store(tmp) as store:
                publications.ensure_publication_table(store)
                store.conn.executemany(
                    "INSERT OR REPLACE INTO publication_counts (company_key, year, works, source, retrieved_at) "
                    "VALUES (?,?,?,?,?)",
                    [("acme", 2023, 30, publications.SOURCE, "2026-11-02T00:00:00Z"),
                     ("acme", 2022, 20, publications.SOURCE, "2026-11-02T00:00:00Z"),
                     ("acme", 2021, 10, publications.SOURCE, "2026-11-02T00:00:00Z")])
                store.conn.commit()
                examples = [
                    {"company_key": "acme", "cutoff": "2024-10-01", "features": {"rd_count_12m": 1.0}},
                    {"company_key": "missing_co", "cutoff": "2024-10-01", "features": {}},
                ]
                attach_publication_features(store, examples)
                self.assertEqual(examples[0]["features"]["pub_count_prev_year"], 30.0)
                self.assertEqual(examples[0]["features"]["rd_count_12m"], 1.0)  # untouched
                self.assertEqual(examples[1]["features"]["pub_count_prev_year"], None)
                self.assertEqual(examples[1]["features"]["pub_missing"], 1.0)
                coverage = publication_feature_coverage(examples)
                self.assertEqual(coverage["examples"], 2)
                self.assertEqual(coverage["examples_with_publication_data"], 1)
                self.assertEqual(coverage["companies_with_publication_data"], 1)


class PatentAdapterTests(unittest.TestCase):
    def test_missing_api_key_returns_unavailable_and_zero_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _open_store(tmp) as store:
                with patch.dict(os.environ, {patents.USPTO_API_KEY_ENV: ""}):
                    result = patents.collect(store, SYNTHETIC_COMPANIES)
                self.assertEqual(result["status"], "unavailable_missing_api_key")
                self.assertEqual(result["rows"], 0)
                self.assertFalse(result["evaluated"])
                self.assertIn("USPTO_ODP_API_KEY", result["warning"])
                self.assertIn("no patent rows were collected", result["warning"].lower())
                tables = {row[0] for row in store.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertNotIn("patent_applications", tables)

    def test_jsonl_import_parses_only_valid_rows(self) -> None:
        rows = [
            {"application_id": "A1", "company_key": "acme", "assignee": "ACME DEVICES",
             "filing_date": "2023-01-15", "publication_date": "2024-06-01", "title": "Synthetic device"},
            {"application_id": "A2", "company_key": "acme", "assignee": "ACME DEVICES",
             "filing_date": "2022-02-02", "publication_date": None, "title": "Synthetic unpublished"},
            {"company_key": "acme", "title": "no application id"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "patents.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\nnot-json\n", encoding="utf-8")
            with _open_store(tmp) as store:
                imported = patents.collect_from_jsonl(path, store, retrieved_at="2026-11-02T00:00:00Z")
                self.assertEqual(imported["status"], "ok")
                self.assertEqual(imported["rows"], 2)   # the row without an id is skipped
                self.assertEqual(imported["skipped"], 2)  # one invalid id + one non-JSON line
                publications_dates = patents.load_publications(store)
                self.assertEqual(list(publications_dates), ["acme"])
                self.assertEqual([day.isoformat() for day in publications_dates["acme"]], ["2024-06-01"])

    def test_pit_ignores_unpublished_applications(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _open_store(tmp) as store:
                patents.ensure_patent_table(store)
                store.conn.executemany(
                    "INSERT OR REPLACE INTO patent_applications VALUES (?,?,?,?,?,?,?,?)",
                    [("A1", "acme", "ACME", "2023-01-15", "2024-06-01", "published", "jsonl", "x"),
                     ("A2", "acme", "ACME", "2023-06-01", "2025-06-01", "unpublished", "jsonl", "x")])
                store.conn.commit()
                loaded = patents.load_publications(store)
                # only the published application is known at the cutoff
                before = patent_features(loaded["acme"], "2024-10-01")
                self.assertEqual(before["pat_apps_pub_12m"], 1.0)
                self.assertEqual(before["pat_missing"], 0.0)
                after = patent_features(loaded["acme"], "2025-07-01")
                self.assertEqual(after["pat_apps_pub_12m"], 1.0)   # 2025-06-01 is in the last 12m
                self.assertEqual(after["pat_apps_pub_3y"], 2.0)
                examples = [{"company_key": "acme", "cutoff": "2024-10-01", "features": {}}]
                attach_patent_features(store, examples)
                self.assertEqual(examples[0]["features"]["pat_apps_pub_12m"], 1.0)
                self.assertEqual(set(PATENT_FEATURES).issubset(examples[0]["features"].keys()), True)
                coverage = patent_feature_coverage(examples)
                self.assertEqual(coverage["examples_with_patent_data"], 1)
                self.assertFalse(coverage["evaluated"])

    def test_no_patent_data_means_missing_flag_not_zero_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _open_store(tmp) as store:
                examples = [{"company_key": "acme", "cutoff": "2024-10-01", "features": {}}]
                attach_patent_features(store, examples)
                features = examples[0]["features"]
                for name in PATENT_FEATURES[:-1]:
                    self.assertIsNone(features[name])
                self.assertEqual(features["pat_missing"], 1.0)


if __name__ == "__main__":
    unittest.main()
