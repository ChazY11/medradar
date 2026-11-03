"""Tests for the B-017 a/k/a b102 fixed-cohort sensitivity run.

The point of this harness is that the entity cohort is *exactly* the committed
artefact's 200 keys: no recomputation, no near-name acceptance and no fuzzy
matching anywhere in the restriction step.  These tests pin that boundary, the
deterministic behaviour of the report, and the old-vs-new comparison logic.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments" / "b102_cohort_sensitivity" / "run_fixed_cohort.py"
COHORT = ROOT / "config" / "universe_v1.json"
CYCLE2 = ROOT / "experiments" / "cycle2_coverage"


def load_module():
    spec = importlib.util.spec_from_file_location("b102_fixed_cohort", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def json_dump(payload) -> str:
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False)


def prediction_payload(rows_per_window: list[list[dict]]) -> dict:
    windows = []
    for index, rows in enumerate(rows_per_window):
        windows.append({
            "origin": f"2025-{index + 1:02d}-01",
            "training_rows": 100,
            "rows": rows,
            "metrics": {},
        })
    return {
        "panel": "p2_fixed_cohort",
        "dataset_version": "first_entry_entity_v1",
        "specification": {"name": "rd_plus_entry_history", "features": []},
        "holdout_origins": [window["origin"] for window in windows],
        "window_count": len(windows),
        "windows": windows,
    }


def prediction_row(entity: str, track: str, label: int, probability: float,
                   baseline: float) -> dict:
    return {
        "entity": entity,
        "track": track,
        "label": label,
        "probability": probability,
        "baseline_probability": baseline,
        "lead_days": 90 if label else None,
        "target_date": "2025-06-01" if label else None,
    }


class ModuleTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="b102-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


# ------------------------------------------------------------------- cohort file
class CohortArtifactTests(ModuleTestCase):
    def test_loads_exactly_200_unique_keys(self) -> None:
        cohort = self.module.load_artifact_cohort(COHORT)
        self.assertEqual(cohort["count"], 200)
        self.assertEqual(len(cohort["key_set"]), 200)
        self.assertEqual(len(cohort["sha256"]), 64)
        self.assertIn("entity_keys", cohort)
        self.assertEqual(len(cohort["entity_keys"]), 200)

    def test_metadata_is_preserved_without_keys(self) -> None:
        cohort = self.module.load_artifact_cohort(COHORT)
        self.assertNotIn("entity_keys", cohort["metadata"])
        self.assertEqual(cohort["metadata"]["max_entities"], 200)

    def test_rejects_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.module.load_artifact_cohort(self.tmp / "absent.json")

    def test_rejects_duplicate_keys(self) -> None:
        path = self.tmp / "dupes.json"
        path.write_text(json.dumps({"cohort": {"entity_keys": ["a", "a"], "max_entities": 2}}),
                        encoding="utf-8")
        with self.assertRaises(ValueError):
            self.module.load_artifact_cohort(path)

    def test_rejects_size_mismatch(self) -> None:
        path = self.tmp / "short.json"
        path.write_text(json.dumps({"cohort": {"entity_keys": ["a", "b"], "max_entities": 3}}),
                        encoding="utf-8")
        with self.assertRaises(ValueError):
            self.module.load_artifact_cohort(path)


# -------------------------------------------------------------- exact restriction
class ExactKeyRestrictionTests(ModuleTestCase):
    def test_keeps_only_exact_key_matches(self) -> None:
        events = [
            {"entity": "medtronic-4bdceace", "event_id": "e1"},
            {"entity": "MEDTRONIC", "event_id": "e2"},
            {"entity": "medtronic", "event_id": "e3"},
            {"entity": "medtronic-4bdceace-extra", "event_id": "e4"},
            {"entity": "medtronic-4bdceac", "event_id": "e5"},
            {"entity": "", "event_id": "e6"},
            {"entity": None, "event_id": "e7"},
        ]
        kept, missing = self.module.restrict_events_to_cohort(
            events, {"medtronic-4bdceace", "abbott"})
        self.assertEqual([event["event_id"] for event in kept], ["e1"])
        self.assertEqual(missing, ["abbott"])

    def test_no_fuzzy_matching_in_restriction(self) -> None:
        cohort = {"abbott", "siemens-healthineers"}
        near_misses = [
            {"entity": "abbott-laboratories"},
            {"entity": "siemens-healthineers-usa"},
            {"entity": "SIEMENS HEALTHINEERS"},
            {"entity": "siemens"},
        ]
        kept, missing = self.module.restrict_events_to_cohort(near_misses, cohort)
        self.assertEqual(kept, [])
        self.assertEqual(missing, ["abbott", "siemens-healthineers"])

    def test_preserves_event_order_and_copies_rows(self) -> None:
        source = [{"entity": "a", "event_id": "e1"}, {"entity": "b", "event_id": "e2"}]
        kept, _ = self.module.restrict_events_to_cohort(source, {"a", "b"})
        self.assertEqual([event["event_id"] for event in kept], ["e1", "e2"])
        kept[0]["event_id"] = "mutated"
        self.assertEqual(source[0]["event_id"], "e1")

    def test_missing_keys_are_sorted_and_complete(self) -> None:
        kept, missing = self.module.restrict_events_to_cohort(
            [{"entity": "b"}], {"a", "b", "c"})
        self.assertEqual(len(kept), 1)
        self.assertEqual(missing, ["a", "c"])


# ------------------------------------------------------------------- gap effects
class GapTests(ModuleTestCase):
    def test_gap_impact_attributes_rows_to_swapped_keys(self) -> None:
        fixed_panel = {"examples": [
            {"company_key": "art-1", "label": 1},
            {"company_key": "art-1", "label": 0},
            {"company_key": "common", "label": 0},
        ]}
        gap = {
            "only_in_artifact": ["art-1"],
            "only_computed": ["comp-1"],
            "examples_by_key": {"comp-1": {"rows": 5, "positives": 2},
                                "common": {"rows": 1, "positives": 0}},
        }
        impact = self.module.gap_impact({"panel": {}}, gap, fixed_panel)
        self.assertEqual(impact["fixed_panel_rows_from_artifact_only_keys"], 2)
        self.assertEqual(impact["fixed_panel_positives_from_artifact_only_keys"], 1)
        self.assertEqual(impact["computed_panel_rows_from_computed_only_keys"], 5)
        self.assertEqual(impact["computed_panel_positives_from_computed_only_keys"], 2)

    def test_gap_impact_is_zero_when_no_swapped_keys(self) -> None:
        impact = self.module.gap_impact(
            {"panel": {}},
            {"only_in_artifact": [], "only_computed": [], "examples_by_key": {}},
            {"examples": [{"company_key": "x", "label": 1}]},
        )
        self.assertEqual(impact["fixed_panel_rows_from_artifact_only_keys"], 0)
        self.assertEqual(impact["computed_panel_rows_from_computed_only_keys"], 0)


# ------------------------------------------------------------------ comparison
def synthetic_old_analysis(pooled_delta: float = 0.0973, mde: float = 0.0877,
                           windows_excluding: tuple[int, int] = (3, 3)) -> dict:
    per_window = [
        {"origin": "2025-04-01", "delta_ap": 0.05816534587660598,
         "ci_entity": {"ci_low": 0.00148}, "ci_pair": {"ci_low": 0.00941},
         "excludes_zero_entity": windows_excluding[0] > 0,
         "excludes_zero_pair": windows_excluding[1] > 0},
        {"origin": "2025-07-01", "delta_ap": 0.1189314470628156,
         "ci_entity": {"ci_low": 0.0386}, "ci_pair": {"ci_low": 0.05},
         "excludes_zero_entity": windows_excluding[0] > 1,
         "excludes_zero_pair": windows_excluding[1] > 1},
        {"origin": "2025-10-01", "delta_ap": 0.1492651130381278,
         "ci_entity": {"ci_low": 0.07}, "ci_pair": {"ci_low": 0.08},
         "excludes_zero_entity": windows_excluding[0] > 2,
         "excludes_zero_pair": windows_excluding[1] > 2},
    ]
    return {"panels": {"p2": {
        "windows": [
            {"origin": "2025-04-01", "rows": 6890, "positives": 41,
             "model_pr_auc": 0.08325239981694461, "baseline_pr_auc": 0.02508705394033863,
             "delta_ap": 0.05816534587660598},
        ],
        "inference": {"pooled": {"rows": 20671, "positives": 140,
                                 "model_pr_auc": 0.12918907441536331,
                                 "baseline_pr_auc": 0.031868463565008075},
                      "clustered_bootstrap": {"entity": {"ci_low": 0.03},
                                               "pair": {"ci_low": 0.04}},
                      "mde": {"observed_from_entity_cluster_se":
                              {"mde_delta_ap": mde}}},
        "per_window_inference": per_window,
        "decision_inputs": {
            "per_window_majority": {
                "entity": {"windows_excluding_zero": windows_excluding[0],
                           "deltas": [0.058165, 0.118931, 0.149265],
                           "sign_stable_positive": True},
                "pair": {"windows_excluding_zero": windows_excluding[1],
                         "deltas": [0.058165, 0.118931, 0.149265],
                         "sign_stable_positive": True},
            },
            "pooled_delta": pooled_delta,
            "rule_satisfied": windows_excluding == (3, 3),
        },
    }}}


def synthetic_new_analysis(delta: float = 0.0973, windows_excluding: tuple[int, int] = (3, 3)) -> dict:
    return {
        "per_window_inference": [
            {"origin": "2025-04-01", "delta_ap": 0.058, "ci_entity": {"ci_low": 0.001},
             "ci_pair": {"ci_low": 0.01},
             "excludes_zero_entity": windows_excluding[0] > 0,
             "excludes_zero_pair": windows_excluding[1] > 0},
            {"origin": "2025-07-01", "delta_ap": 0.119, "ci_entity": {"ci_low": 0.038},
             "ci_pair": {"ci_low": 0.05},
             "excludes_zero_entity": windows_excluding[0] > 1,
             "excludes_zero_pair": windows_excluding[1] > 1},
            {"origin": "2025-10-01", "delta_ap": 0.149, "ci_entity": {"ci_low": 0.07},
             "ci_pair": {"ci_low": 0.08},
             "excludes_zero_entity": windows_excluding[0] > 2,
             "excludes_zero_pair": windows_excluding[1] > 2},
        ],
        "inference": {
            "pooled": {"rows": 20600, "positives": 140,
                       "model_pr_auc": 0.129, "baseline_pr_auc": 0.0317},
            "clustered_bootstrap": {"entity": {"ci_low": 0.031}, "pair": {"ci_low": 0.041}},
            "mde": {"observed_from_entity_cluster_se": {"mde_delta_ap": 0.0877}},
        },
        "decision_inputs": {
            "per_window_majority": {
                "entity": {"windows_excluding_zero": windows_excluding[0],
                           "deltas": [0.058, 0.119, 0.149],
                           "sign_stable_positive": True},
                "pair": {"windows_excluding_zero": windows_excluding[1],
                         "deltas": [0.058, 0.119, 0.149],
                         "sign_stable_positive": True},
            },
            "pooled_delta": delta,
            "rule_satisfied": windows_excluding == (3, 3),
        },
    }


class ComparisonTests(ModuleTestCase):
    def test_conclusion_unchanged_when_direction_magnitude_and_rule_hold(self) -> None:
        windows = [{"origin": "2025-04-01", "rows": 6890, "positives": 41,
                    "model_pr_auc": 0.0833, "baseline_pr_auc": 0.0251,
                    "delta_ap": 0.0582}]
        comparison = self.module.build_comparison(
            synthetic_old_analysis(), windows, synthetic_new_analysis())
        self.assertTrue(comparison["verdict"]["direction_unchanged"])
        self.assertTrue(comparison["verdict"]["conclusion_unchanged"])
        self.assertTrue(comparison["verdict"]["windows_excluding_zero_unchanged"])
        self.assertAlmostEqual(comparison["verdict"]["magnitude_retained"], 1.0, places=2)
        self.assertEqual(comparison["headline_new"]["windows_excluding_zero_entity"], 3)

    def test_flipped_direction_is_detected(self) -> None:
        comparison = self.module.build_comparison(
            synthetic_old_analysis(),
            [{"origin": "2025-04-01", "rows": 10, "positives": 1,
              "model_pr_auc": 0.01, "baseline_pr_auc": 0.02, "delta_ap": -0.01}],
            synthetic_new_analysis(delta=-0.01))
        self.assertFalse(comparison["verdict"]["direction_unchanged"])
        self.assertFalse(comparison["verdict"]["conclusion_unchanged"])

    def test_fewer_windows_excluding_zero_breaks_unchanged_verdict(self) -> None:
        comparison = self.module.build_comparison(
            synthetic_old_analysis(),
            [{"origin": "2025-04-01", "rows": 10, "positives": 1,
              "model_pr_auc": 0.05, "baseline_pr_auc": 0.02, "delta_ap": 0.03}],
            synthetic_new_analysis(windows_excluding=(1, 0)))
        self.assertFalse(comparison["verdict"]["windows_excluding_zero_unchanged"])
        self.assertFalse(comparison["verdict"]["conclusion_unchanged"])

    def test_comparison_is_deterministic(self) -> None:
        windows = [{"origin": "2025-04-01", "rows": 10, "positives": 1,
                    "model_pr_auc": 0.05, "baseline_pr_auc": 0.02, "delta_ap": 0.03}]
        first = self.module.build_comparison(
            synthetic_old_analysis(), windows, synthetic_new_analysis())
        second = self.module.build_comparison(
            synthetic_old_analysis(), windows, synthetic_new_analysis())
        self.assertEqual(json_dump(first), json_dump(second))


# ----------------------------------------------------------------- predictions
class PredictionInferenceTests(ModuleTestCase):
    def rows(self) -> list[list[dict]]:
        return [[
            prediction_row("e1", "t1", 1, 0.9, 0.3),
            prediction_row("e2", "t1", 0, 0.2, 0.1),
            prediction_row("e3", "t2", 1, 0.7, 0.2),
            prediction_row("e4", "t2", 0, 0.1, 0.1),
            prediction_row("e5", "t1", 0, 0.3, 0.4),
            prediction_row("e6", "t2", 0, 0.4, 0.2),
        ], [
            prediction_row("e1", "t1", 1, 0.8, 0.3),
            prediction_row("e2", "t1", 0, 0.25, 0.1),
            prediction_row("e3", "t2", 1, 0.6, 0.2),
            prediction_row("e4", "t2", 0, 0.15, 0.1),
            prediction_row("e5", "t1", 0, 0.35, 0.4),
            prediction_row("e6", "t2", 0, 0.45, 0.2),
        ]]

    def test_analysis_is_deterministic(self) -> None:
        payload = prediction_payload(self.rows())
        first = self.module.analyze_predictions(payload)
        second = self.module.analyze_predictions(payload)
        self.assertEqual(json_dump(first), json_dump(second))
        self.assertEqual(first["prediction_rows"], 12)
        self.assertIn("clustered_bootstrap", first["inference"])

    def test_rows_without_baseline_are_dropped_to_keep_pairing_exact(self) -> None:
        payload = prediction_payload(self.rows())
        payload["windows"][0]["rows"][0]["baseline_probability"] = None
        analysis = self.module.analyze_predictions(payload)
        self.assertEqual(analysis["prediction_rows"], 11)

    def test_decision_inputs_are_reported(self) -> None:
        analysis = self.module.analyze_predictions(prediction_payload(self.rows()))
        decision = analysis["decision_inputs"]
        self.assertEqual(decision["per_window_majority"]["entity"]["windows_total"], 2)
        self.assertIn("rule_satisfied", decision)
        self.assertIsNotNone(decision["pooled_delta"])


# ------------------------------------------------------------------- end-to-end
class EndToEndTests(ModuleTestCase):
    def make_fixtures(self) -> dict[str, Path]:
        cycle2 = self.tmp / "cycle2"
        cycle2.mkdir()
        (cycle2 / "analysis.json").write_text(
            json.dumps(synthetic_old_analysis()), encoding="utf-8")
        (cycle2 / "panel_p2.json").write_text(json.dumps({"panel": {
            "n_examples": 161636, "n_positives": 1082, "entity_count": 193,
            "track_count": 38, "observed_pair_count": 634, "event_count": 5842,
            "origins": 24, "coverage_start": "2016-11-01", "coverage_end": "2026-10-16",
        }}), encoding="utf-8")
        cohort = self.tmp / "cohort.json"
        cohort.write_text(json.dumps({"cohort": {
            "entity_keys": ["art-1", "art-2"], "max_entities": 2}}), encoding="utf-8")
        db = self.tmp / "db.sqlite"
        db.write_bytes(b"")
        return {"cycle2": cycle2, "cohort": cohort, "db": db}

    def patch_heavy_paths(self, module) -> None:
        module.build_fixed_panel = lambda db_path, cohort: (
            {"examples": [{"company_key": "art-1", "label": 1},
                          {"company_key": "art-2", "label": 0}],
             "cutoffs": ["2025-04-01"], "dataset_version": "first_entry_entity_v1"},
            {"panel": {"n_examples": 2, "n_positives": 1, "entity_count": 2,
                       "track_count": 1, "observed_pair_count": 2, "event_count": 2,
                       "origins": 1, "coverage_start": "2016-11-01",
                       "coverage_end": "2026-10-16", "cutoffs": ["2025-04-01"]},
             "cohort_key_count": 2,
             "cohort_keys_without_material_events": [],
             "cohort_keys_without_usable_panel_events": []},
        )
        module.recomputed_cohort_gap = lambda db_path, keys: {
            "artifact_keys": 2, "computed_keys": 2, "intersection": 2,
            "only_in_artifact": [], "only_computed": [], "symmetric_difference": 0,
            "artifact_crosscheck": {}, "computed_panel_n_examples": 2,
            "computed_panel_n_positives": 1, "examples_by_key": {},
        }
        module.build_prediction_windows = lambda panel, holdouts=3: prediction_payload(
            PredictionInferenceTests().rows())

    def test_report_is_written_and_deterministic(self) -> None:
        fixtures = self.make_fixtures()
        self.patch_heavy_paths(self.module)
        first = self.tmp / "report-1.json"
        second = self.tmp / "report-2.json"
        exit_code = self.module.main([
            "--db", str(fixtures["db"]), "--cohort", str(fixtures["cohort"]),
            "--cycle2-dir", str(fixtures["cycle2"]), "--skip-backtest",
            "--out-dir", str(self.tmp), "--report", str(first), "--backtest-out", str(self.tmp / "bt.json"),
        ])
        self.assertEqual(exit_code, 0)
        report = json.loads(first.read_text(encoding="utf-8"))
        self.assertEqual(report["schema"], "b102.fixed_cohort_report.v1")
        self.assertEqual(report["cohort_gap"]["artifact_keys"], 2)
        self.assertEqual(report["spec"]["n_features"], 16)
        self.assertFalse(report["backtest"]["run"])
        self.assertIn("comparison", report)
        self.patch_heavy_paths(self.module)
        exit_code = self.module.main([
            "--db", str(fixtures["db"]), "--cohort", str(fixtures["cohort"]),
            "--cycle2-dir", str(fixtures["cycle2"]), "--skip-backtest",
            "--out-dir", str(self.tmp), "--report", str(second), "--backtest-out", str(self.tmp / "bt2.json"),
        ])
        self.assertEqual(exit_code, 0)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_missing_cohort_exits_two(self) -> None:
        self.assertEqual(self.module.main([
            "--db", str(self.tmp / "db.sqlite"),
            "--cohort", str(self.tmp / "absent.json"),
            "--cycle2-dir", str(self.tmp),
            "--report", str(self.tmp / "r.json"),
        ]), 2)


if __name__ == "__main__":
    unittest.main()
