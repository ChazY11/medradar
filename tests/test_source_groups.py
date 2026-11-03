"""Tests for the B-018 / b105 source-group re-test on the P2 entity panel.

The load-bearing properties: the entity -> company join is exact (never a name
proxy), the source groups are attached through the frozen point-in-time builders
with missingness preserved, the pre-declared verdict rule cannot emit an
unqualified null, and the analysis is deterministic.  A hand-computed AP and a
hand-computed MDE pin the statistics helpers.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "experiments" / "b105_source_groups" / "build_entity_panel_with_sources.py"
ANALYSIS = ROOT / "experiments" / "b105_source_groups" / "run_analysis.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ModuleTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.build = load_module("b105_build", BUILD)
        cls.analysis = load_module("b105_analysis", ANALYSIS)

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="b105-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


# --------------------------------------------------------------- feature lists
class SpecificationTests(ModuleTestCase):
    def test_reference_is_the_frozen_sixteen(self) -> None:
        self.assertEqual(len(self.build.BASE_PANEL_FEATURES), 16)

    def test_group_specs_have_expected_sizes(self) -> None:
        self.assertEqual(len(self.analysis.spec_features(None)), 16)
        self.assertEqual(len(self.analysis.spec_features("financial")), 16 + 11)
        self.assertEqual(len(self.analysis.spec_features("market")), 16 + 8)
        self.assertEqual(len(self.analysis.spec_features("publication")), 16 + 5)

    def test_no_numpy_or_pandas_import(self) -> None:
        for path in (BUILD, ANALYSIS):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("import numpy", text, path.name)
            self.assertNotIn("import pandas", text, path.name)
            self.assertNotIn("from numpy", text, path.name)
            self.assertNotIn("from pandas", text, path.name)


# ------------------------------------------------------------------ entity join
class EntityJoinTests(ModuleTestCase):
    def make_db(self) -> sqlite3.Connection:
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE events (kind TEXT, company_key TEXT, applicant_raw TEXT)")
        return connection

    def test_exact_unique_link_maps_entity(self) -> None:
        connection = self.make_db()
        connection.executemany(
            "INSERT INTO events(kind, company_key, applicant_raw) VALUES (?,?,?)",
            [
                ("510k", "medtronic", "MEDTRONIC"),
                ("pma", "medtronic", "Medtronic, Inc."),
                ("510k", "", "ACME DEVICES"),
            ])
        mapped, stats = self.build.entity_parent_map(connection)
        self.assertEqual(stats["entities_mapped_to_one_company"], 1)
        self.assertEqual(list(mapped.values()), ["medtronic"])
        self.assertEqual(stats["entities_ambiguous"], 0)

    def test_conflicting_company_keys_are_ambiguous_and_excluded(self) -> None:
        connection = self.make_db()
        connection.executemany(
            "INSERT INTO events(kind, company_key, applicant_raw) VALUES (?,?,?)",
            [("510k", "abbott", "SAME APPLICANT"),
             ("510k", "medtronic", "SAME APPLICANT")])
        mapped, stats = self.build.entity_parent_map(connection)
        self.assertEqual(mapped, {})
        self.assertEqual(stats["entities_ambiguous"], 1)

    def test_no_name_matching_occurs(self) -> None:
        connection = self.make_db()
        # The applicant string equals a roster name but the store carries no link.
        connection.execute(
            "INSERT INTO events(kind, company_key, applicant_raw) VALUES ('510k','', 'MEDTRONIC')")
        mapped, _stats = self.build.entity_parent_map(connection)
        self.assertEqual(mapped, {})

    def test_non_regulatory_kinds_are_ignored(self) -> None:
        connection = self.make_db()
        connection.execute(
            "INSERT INTO events(kind, company_key, applicant_raw) VALUES ('recall','medtronic','MEDTRONIC')")
        mapped, _stats = self.build.entity_parent_map(connection)
        self.assertEqual(mapped, {})


# --------------------------------------------------------------- feature attach
class AttachTests(ModuleTestCase):
    def example(self, entity: str, cutoff: str = "2024-10-01") -> dict:
        return {"example_id": f"{entity}|{cutoff}", "cutoff": cutoff, "company_key": entity,
                "track_id": "t", "label": 1, "features": {},
                "parent_company": "", "source_available": {}}

    def test_attaches_group_values_and_keeps_missingness(self) -> None:
        examples = [self.example("mapped"), self.example("unmapped")]
        parent_map = {"mapped": "medtronic"}
        financial = {("medtronic", "2024-10-01"): {
            **{name: float(index) for index, name in enumerate(self.build.FINANCIAL_FEATURES)},
            "fin_facts_available": 5.0}}
        market = {("medtronic", "2024-10-01"): {
            **{name: 0.5 for name in self.build.MARKET_FEATURES}, "mkt_missing": 0.0}}
        publication = {("medtronic", "2024-10-01"): {
            **{name: 1.0 for name in self.build.PUBLICATION_FEATURES}, "pub_missing": 0.0}}
        counters = self.build.attach_source_groups(
            examples, parent_map, financial, market, publication)
        mapped, unmapped = examples
        self.assertTrue(all(mapped["source_available"].values()))
        self.assertEqual(mapped["parent_company"], "medtronic")
        self.assertEqual(unmapped["parent_company"], "")
        self.assertFalse(any(unmapped["source_available"].values()))
        self.assertEqual(unmapped["features"]["mkt_missing"], 1.0)
        self.assertEqual(unmapped["features"]["pub_missing"], 1.0)
        self.assertEqual(unmapped["features"]["fin_facts_available"], 0.0)
        self.assertEqual(counters["market"]["no_parent"], 1)

    def test_attachment_is_deterministic(self) -> None:
        def run() -> str:
            examples = [self.example("mapped"), self.example("unmapped")]
            self.build.attach_source_groups(
                examples,
                {"mapped": "medtronic"},
                {("medtronic", "2024-10-01"): {"fin_facts_available": 1.0}},
                {("medtronic", "2024-10-01"): {"mkt_missing": 0.0,
                                               **{name: 0.0 for name in self.build.MARKET_FEATURES}}},
                {("medtronic", "2024-10-01"): {"pub_missing": 0.0,
                                               **{name: 0.0 for name in self.build.PUBLICATION_FEATURES}}},
            )
            return json.dumps(examples, sort_keys=True)
        self.assertEqual(run(), run())


# ------------------------------------------------------------------ coverage
class CoverageTests(ModuleTestCase):
    def pooled(self, flags: list[bool], labels: list[int]) -> dict:
        return {
            "labels": labels,
            "availability": {"financial": flags, "market": flags, "publication": flags},
        }

    def test_coverage_counts(self) -> None:
        pooled = self.pooled([True, True, False, False], [1, 0, 1, 0])
        coverage = self.analysis.coverage_for("financial", pooled)
        self.assertEqual(coverage["holdout_rows_with_group"], 2)
        self.assertEqual(coverage["holdout_row_coverage"], 0.5)
        self.assertEqual(coverage["holdout_positives_with_group"], 1)
        self.assertEqual(coverage["holdout_positive_coverage"], 0.5)

    def test_below_floor_is_not_evaluable(self) -> None:
        coverage = {"holdout_rows": 100, "holdout_rows_with_group": 10,
                    "holdout_row_coverage": 0.10, "holdout_positives": 50,
                    "holdout_positives_with_group": 5,
                    "holdout_positive_coverage": 0.10}
        verdict = self.analysis.classify("financial", coverage, {}, {}, 0.001)
        self.assertFalse(verdict["evaluable"])
        self.assertEqual(verdict["verdict"], "NOT_EVALUABLE")
        self.assertIn("no proxy substituted", verdict["statement"])

    def test_underpowered_is_not_an_unqualified_null(self) -> None:
        coverage = {"holdout_rows": 100, "holdout_rows_with_group": 50,
                    "holdout_row_coverage": 0.5, "holdout_positives": 40,
                    "holdout_positives_with_group": 20,
                    "holdout_positive_coverage": 0.5}
        verdict = self.analysis.classify(
            "market", coverage, {"ci_low": -0.02}, {"mde_delta_ap": 0.09}, -0.003)
        self.assertEqual(verdict["verdict"], "underpowered")
        self.assertIn("not evidence of no effect", verdict["statement"])

    def test_well_powered_negative_requires_mde_at_most_two_points(self) -> None:
        coverage = {"holdout_rows": 100, "holdout_rows_with_group": 50,
                    "holdout_row_coverage": 0.5, "holdout_positives": 40,
                    "holdout_positives_with_group": 20,
                    "holdout_positive_coverage": 0.5}
        powered = self.analysis.classify(
            "publication", coverage, {"ci_low": -0.01}, {"mde_delta_ap": 0.02}, 0.001)
        self.assertEqual(powered["verdict"], "well-powered negative")
        borderline = self.analysis.classify(
            "publication", coverage, {"ci_low": -0.01}, {"mde_delta_ap": 0.0200001}, 0.001)
        self.assertEqual(borderline["verdict"], "underpowered")

    def test_positive_ci_is_never_called_a_null(self) -> None:
        coverage = {"holdout_rows": 100, "holdout_rows_with_group": 80,
                    "holdout_row_coverage": 0.8, "holdout_positives": 40,
                    "holdout_positives_with_group": 30,
                    "holdout_positive_coverage": 0.75}
        verdict = self.analysis.classify(
            "market", coverage, {"ci_low": 0.01}, {"mde_delta_ap": 0.05}, 0.03)
        self.assertEqual(verdict["verdict"], "positive_association")

    def test_negative_ci_is_never_called_a_null(self) -> None:
        coverage = {"holdout_rows": 100, "holdout_rows_with_group": 50,
                    "holdout_row_coverage": 0.5, "holdout_positives": 40,
                    "holdout_positives_with_group": 20,
                    "holdout_positive_coverage": 0.5}
        verdict = self.analysis.classify(
            "market", coverage, {"ci_low": -0.03, "ci_high": -0.000002},
            {"mde_delta_ap": 0.024}, -0.013)
        self.assertEqual(verdict["verdict"], "negative_association")
        self.assertIn("not a null", verdict["statement"])


# --------------------------------------------------------------- statistics
class StatisticsTests(ModuleTestCase):
    def test_hand_checked_average_precision(self) -> None:
        # positives at ranks 1 and 3 -> AP = (1/1 + 2/3) / 2 = 5/6
        self.assertAlmostEqual(
            self.analysis.pr_auc([1, 0, 1, 0], [0.9, 0.8, 0.7, 0.6]), 5 / 6, places=12)
        # perfect ranking -> AP = 1
        self.assertAlmostEqual(
            self.analysis.pr_auc([1, 1, 0, 0], [0.9, 0.8, 0.7, 0.6]), 1.0, places=12)

    def test_hand_checked_mde_from_se(self) -> None:
        # MDE = (z_0.975 + z_0.8) * SE for alpha=0.05, power=0.8
        expected = (1.9599639845400816 + 0.8416212336014723) * 0.01
        from medradar.intelligence import evalstats

        result = evalstats.mde_from_se(0.01)
        self.assertAlmostEqual(result["mde_delta_ap"], expected, places=12)
        self.assertAlmostEqual(result["mde_delta_ap"], 0.028015852, places=6)

    def test_mde_grows_with_se(self) -> None:
        from medradar.intelligence import evalstats

        self.assertLess(evalstats.mde_from_se(0.01)["mde_delta_ap"],
                        evalstats.mde_from_se(0.05)["mde_delta_ap"])


# ------------------------------------------------------------- analysis plumbing
class AnalysisPlumbingTests(ModuleTestCase):
    def synthetic_rows(self) -> list[dict]:
        rows = []
        features = {name: 0.1 * (index + 1) for index, name in enumerate(self.build.BASE_PANEL_FEATURES)}
        cutoffs = [f"{year}-{month:02d}-01" for year in (2022, 2023, 2024)
                   for month in (1, 4, 7, 10)]
        for cutoff_index, cutoff in enumerate(cutoffs):
            for index in range(6):
                entity = f"entity-{index}"
                row = {
                    "example_id": f"{cutoff}|{entity}",
                    "cutoff": cutoff,
                    "entity": entity,
                    "parent_company": f"company-{index % 3}",
                    "track": "track-1",
                    "label": 1 if (index + cutoff_index) % 3 == 0 else 0,
                    "first_target_event_date": cutoff,
                    "features": dict(features, **{name: None for name in
                                                  self.build.SOURCE_GROUPS["financial"]}),
                    "source_available": {"financial": False, "market": False,
                                         "publication": False},
                }
                rows.append(row)
        return rows

    def test_holdout_origins_are_the_last_three_evaluable(self) -> None:
        rows = self.synthetic_rows()
        origins, holds = self.analysis.holdout_origins(rows, holdouts=3)
        self.assertEqual(len(holds), 3)
        self.assertEqual(holds, origins[-3:])

    def test_prediction_windows_are_deterministic(self) -> None:
        rows = self.synthetic_rows()
        _origins, holds = self.analysis.holdout_origins(rows, holdouts=3)
        features = self.analysis.spec_features(None)
        first = self.analysis.predict_windows(rows, holds, features)
        second = self.analysis.predict_windows(rows, holds, features)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(len(first["windows"]), 3)
        self.assertTrue(all(window["rows"] for window in first["windows"]))

    def test_pooled_clusters_use_parent_company_and_entity_fallback(self) -> None:
        rows = self.synthetic_rows()
        _origins, holds = self.analysis.holdout_origins(rows, holdouts=3)
        for row in rows:
            if str(row["cutoff"]) == holds[0]:
                row["parent_company"] = ""
                break
        predictions = self.analysis.predict_windows(
            rows, holds, self.analysis.spec_features(None))
        pooled = self.analysis.pooled_rows(predictions)
        self.assertTrue(any(cluster.startswith("C:company-") for cluster in pooled["clusters"]))
        self.assertTrue(any(cluster.startswith("E:entity-") for cluster in pooled["clusters"]))

    def test_reference_validation_detects_committed_metrics(self) -> None:
        committed = self.tmp / "analysis.json"
        committed.write_text(json.dumps({"panels": {"p2": {
            "windows": [{"origin": "2025-04-01", "rows": 1, "positives": 1,
                         "model_pr_auc": 0.5}],
            "inference": {"pooled": {"model_pr_auc": 0.5}},
        }}}), encoding="utf-8")
        loaded = self.analysis.load_committed_reference(committed)
        self.assertTrue(loaded["available"])
        self.assertEqual(loaded["windows"][0]["pr_auc"], 0.5)

    def test_parent_marginals_are_extracted_from_the_committed_ablation(self) -> None:
        ablation = self.tmp / "ablation_metrics.json"
        ablation.write_text(json.dumps({"protocol": {"holdouts": 3}, "targets": {"entry": {
            "reference_spec": "D",
            "specs": {
                "C": {"holdout_metrics": {"pr_auc": 0.10}},
                "D": {"holdout_metrics": {"pr_auc": 0.11}},
                "E": {"holdout_metrics": {"pr_auc": 0.09}},
                "F": {"holdout_metrics": {"pr_auc": 0.13}},
            },
            "marginal_deltas": {
                "C": {"delta": {"pr_auc": -0.01}},
                "E": {"delta": {"pr_auc": -0.02}},
                "F": {"delta": {"pr_auc": 0.02}},
            },
        }}}), encoding="utf-8")
        parent = self.analysis.parent_marginals(ablation)
        self.assertTrue(parent["available"])
        self.assertAlmostEqual(parent["marginals"]["financial"]["delta_ap"], 0.01)
        self.assertAlmostEqual(parent["marginals"]["market"]["delta_ap"], -0.02)
        self.assertAlmostEqual(parent["marginals"]["publication"]["delta_ap"], 0.02)

    def test_compare_with_parent_reports_sign_agreement(self) -> None:
        parent = {"available": True, "marginals": {
            "financial": {"delta_ap": 0.01},
            "market": {"delta_ap": -0.02},
            "publication": {"delta_ap": 0.02},
        }}
        comparison = self.analysis.compare_with_parent(
            {"financial": {"delta_ap": 0.005}, "market": {"delta_ap": 0.001},
             "publication": {"delta_ap": -0.004}}, parent)
        table = comparison["table"]
        self.assertTrue(table["financial"]["same_sign"])
        self.assertFalse(table["market"]["same_sign"])
        self.assertFalse(table["publication"]["same_sign"])
        self.assertAlmostEqual(table["financial"]["delta_of_deltas"], -0.005)


if __name__ == "__main__":
    unittest.main()
