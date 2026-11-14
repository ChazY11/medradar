"""Offline tests for the SCIENCE-002R audit.

No network and no dependency on the raw 330 MB cache: every fixture is synthetic, so
a failure here is a failure of the audit's own logic.

Run:  python -m pytest tests/test_science_002r.py -q
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from research.science_002r import common, entity_audit, internal_consistency, selection
from research.science_002r import stats_review

UTC = dt.timezone.utc


def d(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


class SelectionRuleTests(unittest.TestCase):
    def test_counts_are_windowed_at_the_start_and_the_cutoff(self):
        dates = [d("2014-12-31"), d("2015-01-01"), d("2020-12-31"), d("2021-01-01")]
        self.assertEqual(selection.counts_at(dates, "2020-12-31"), 2)
        self.assertEqual(selection.counts_at(dates, "2026-08-31"), 3)

    def test_strict_rule_can_only_remove_firms_never_add(self):
        # the mathematical property the audit relies on: pre-cutoff <= full window
        dates = [d("2019-06-01"), d("2022-06-01"), d("2024-06-01")]
        for cutoff in ("2019-12-31", "2023-12-31", "2026-08-31"):
            self.assertLessEqual(selection.counts_at(dates, cutoff),
                                 selection.counts_at(dates, "2026-08-31"))


class StatisticTests(unittest.TestCase):
    def test_paired_delta_matches_the_frozen_implementation(self):
        from research.science_002 import experiment
        labels = [1, 0, 1, 0, 1, 1, 0, 0]
        groups = ["a", "a", "a", "a", "b", "b", "b", "b"]
        scores = {"B3c": [0.9, 0.1, 0.8, 0.2, 0.4, 0.6, 0.3, 0.7],
                  "B2c": [0.5, 0.5, 0.6, 0.4, 0.6, 0.4, 0.7, 0.3]}
        mine = stats_review.paired_delta(labels, scores, groups, "B3c", "B2c")
        theirs = experiment.paired_delta(labels, scores, groups, "B3c", "B2c")
        self.assertAlmostEqual(mine, theirs, places=12)

    def test_label_autocorrelation_recovers_a_known_cycle(self):
        rows = []
        pattern = [1, 0, 1, 0, 1, 0]
        for i, value in enumerate(pattern * 4):
            rows.append(type("R", (), {"key": "a", "label": value,
                                       "month_end": dt.date(2024, 1, 1) + dt.timedelta(days=31 * i)})())
        out = stats_review.label_autocorrelation(rows)
        self.assertLess(out["lag_1"]["correlation"], 0.0)
        self.assertGreater(out["lag_2"]["correlation"], 0.9)

    def test_quarterly_filter_keeps_non_overlapping_months(self):
        from research.science_002 import panel
        rows = [type("R", (), {"month_end": m})() for m in panel.month_ends(d("2021-01-01"), d("2021-12-01"))]
        kept = [r.month_end.isoformat() for r in stats_review.quarterly_filter(rows)]
        self.assertEqual(kept, ["2021-01-31", "2021-04-30", "2021-07-31", "2021-10-31"])

    def test_group_index_is_a_plain_partition(self):
        out = stats_review.group_index(["a", "b", "a"])
        self.assertEqual(out, {"a": [0, 2], "b": [1]})


class EntityRuleTests(unittest.TestCase):
    def test_distinctive_tokens_drop_sector_words_and_keep_short_brands(self):
        firm = type("F", (), {"sec_title": "GENERAL ELECTRIC CO"})()
        tokens = entity_audit._distinctive_tokens(firm)
        self.assertNotIn("GENERAL", tokens)
        firm2 = type("F", (), {"sec_title": "3M CO"})()
        self.assertIn("3M", entity_audit._distinctive_tokens(firm2))

    def test_establishment_shape_measures_the_aggregation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "links.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["k_number", "decision_date",
                                                            "applicant", "decision_code",
                                                            "n_registration_numbers",
                                                            "registration_numbers",
                                                            "n_fei", "fei_numbers"])
                writer.writeheader()
                # two records share one set across different applicants -> aggregate
                writer.writerow({"k_number": "K1", "applicant": "A", "n_registration_numbers": 2,
                                 "registration_numbers": "1|2"})
                writer.writerow({"k_number": "K2", "applicant": "B", "n_registration_numbers": 2,
                                 "registration_numbers": "1|2"})
                writer.writerow({"k_number": "K3", "applicant": "C", "n_registration_numbers": 1,
                                 "registration_numbers": "3"})
            out = entity_audit.establishment_field_shape(path)
        self.assertEqual(out["rows"], 3)
        self.assertAlmostEqual(out["share_with_exactly_one"], 1 / 3)
        self.assertEqual(out["median_registration_numbers_per_record"], 2)
        self.assertEqual(out["sets_shared_by_more_than_one_applicant"], 1)


class InternalConsistencyTests(unittest.TestCase):
    def _fixture(self, root: Path, panel_rows: int = 6, complete: int = 4) -> None:
        root.mkdir(parents=True, exist_ok=True)
        with (root / "universe.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["key", "cik", "ticker", "sec_title",
                                                        "sic", "sic_description", "tiers",
                                                        "n_window_clearances", "applicants"])
            writer.writeheader()
            writer.writerow({"key": "a", "cik": "1", "ticker": "A", "sec_title": "A",
                             "sic": "3841", "sic_description": "x", "tiers": "T_A",
                             "n_window_clearances": "8", "applicants": "A"})
        with (root / "entity_matches.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["cik", "sec_title", "tier",
                                                        "applicant_root", "owner_root",
                                                        "evidence", "n_window_clearances"])
            writer.writeheader()
            writer.writerow({"cik": "1", "sec_title": "A", "tier": "T_A",
                             "applicant_root": "A", "owner_root": "A", "evidence": "e",
                             "n_window_clearances": "8"})
        with (root / "entity_exclusions.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["key"])
            writer.writeheader()
        with (root / "panel.csv").open("w", encoding="utf-8", newline="") as handle:
            fields = ["key", "ticker", "month_end", "split", "label", "n_events_in_window",
                      "label_507", "label_any8k", "rd_ttm_log", "rd_yoy", "rd_to_sales",
                      "rd_growth_vol"]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for i in range(panel_rows):
                row = {"key": "a", "ticker": "A", "month_end": "2025-01-31",
                       "split": "holdout", "label": str(i % 2), "n_events_in_window": "0",
                       "label_507": "0", "label_any8k": "1"}
                if i < complete:
                    row.update({"rd_ttm_log": "1", "rd_yoy": "0.1",
                                "rd_to_sales": "0.2", "rd_growth_vol": "0.01"})
                writer.writerow(row)
        (root / "universe_summary.json").write_text(json.dumps({"n_included": 1,
                                                               "n_candidate_ciks": 1,
                                                               "n_clearances_total": 8}),
                                                    encoding="utf-8")
        (root / "panel_summary.json").write_text(json.dumps({"n_rows": panel_rows,
                                                            "n_missing_rd_feature_rows": 0,
                                                            "n_rows_dropped_sec_coverage": 0}),
                                                 encoding="utf-8")
        (root / "experiment_results.json").write_text(json.dumps({
            "meta": {"n_rows_complete_case": complete, "n_train": 0, "n_holdout": complete,
                     "prevalence_holdout": 0.5},
            "pooled": {"B1": 0.82, "B3": 0.83},
            "conditional": {"B2c": {"n_firms": 1}, "B3c": {"value": 0.45}},
            "primary": {"delta_stratified_auc_B3c_minus_B2c": -0.03},
            "permutation": {"p_two_sided": 0.1}}), encoding="utf-8")

    def test_planted_mismatch_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root, panel_rows=6, complete=4)
            out = internal_consistency.run(root)
        names = [row["claim"] for row in out["mismatches"]]
        # the fixture deliberately has 4 complete rows, not the 2,554 the doc claims
        self.assertIn("complete-case rows (B0..B3 features present)", names)

    def test_clean_fixture_still_reports_the_known_numeric_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root, panel_rows=6, complete=6)
            out = internal_consistency.run(root)
        gap = [row for row in out["claims"] if row["claim"] == "rows dropped from 2,771 to 2,554"]
        self.assertTrue(gap)
        self.assertFalse(gap[0]["match"])


class PathTests(unittest.TestCase):
    def test_repository_paths_resolve_inside_the_checkout(self):
        self.assertTrue(str(common.REPO).endswith("science-002r"))
        self.assertIn("science_002", str(common.CACHE_RAW))
        self.assertIn("science_002", str(internal_consistency.FROZEN))
