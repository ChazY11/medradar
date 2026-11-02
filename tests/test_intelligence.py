"""Offline tests for Market-to-R&D ingestion, timing, models and registry."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import patch

from medradar.config import load_companies
from medradar.db import DB, make_event_id
from medradar.http import Fetcher
from medradar.intelligence.evaluation.backtesting import (
    eligible_training_rows,
    label_window_end,
    matured_by,
    run_backtest,
)
from medradar.intelligence.evaluation.leakage_audit import audit_examples
from medradar.intelligence.evaluation.metrics import evaluate, paired_bootstrap_delta_ap, pr_auc
from medradar.intelligence.features.financial_features import financial_features
from medradar.intelligence.features.research_features import (
    ENTRY_DATASET_VERSION,
    ENTRY_FEATURES,
    build_entry_examples,
    build_examples,
)
from medradar.intelligence.models.baseline import LogisticBaseline
from medradar.intelligence.sources.procurement_us import normalize_award
from medradar.intelligence.sources.sec_financials import normalize_companyfacts, ticker_cik_map
from medradar.intelligence.storage import IntelligenceStore
from medradar.util import add_months, parse_date


def _timeline_store(path: Path) -> IntelligenceStore:
    store = IntelligenceStore(DB(path))
    events = []
    for index, day in enumerate(("2020-01-01", "2021-01-01", "2022-01-01", "2022-06-01", "2023-06-01", "2024-06-01")):
        events.append({
            "event_id": make_event_id("test", "510k", index), "source": "test", "kind": "510k",
            "event_date": day, "available_at": day, "company_key": "medtronic", "track_id": "spine",
            "product_code": "ABC", "payload": {},
        })
    # Decision was in history but only became public after the cutoff.
    events.append({
        "event_id": make_event_id("test", "510k", "late"), "source": "test", "kind": "510k",
        "event_date": "2022-11-01", "available_at": "2023-02-01", "company_key": "medtronic",
        "track_id": "spine", "product_code": "ABC", "payload": {},
    })
    store.db.upsert_events(events)
    return store


def _backtest_examples() -> list[dict]:
    examples = []
    for origin_index, cutoff in enumerate(("2020-01-01", "2020-04-01", "2020-07-01", "2020-10-01",
                                           "2021-01-01", "2021-04-01")):
        for index in range(12):
            label = int((index + origin_index) % 3 == 0)
            examples.append({
                "cutoff": cutoff, "label": label, "maturity": "mature",
                "company_key": f"c{index % 3}", "track_id": f"t{index % 2}",
                "first_target_event_date": "2021-06-01" if label else None,
                "features": {"rd": float(index % 4), "fin": float(index % 2)},
            })
    return examples


def _entry_store(path: Path, timeline: list[tuple[str, str, str, str]]) -> IntelligenceStore:
    """Synthetic store for the entry target.

    ``timeline`` rows are ``(event_date, available_at, company_key, track_id)``.
    """
    store = IntelligenceStore(DB(path))
    store.db.upsert_events([
        {"event_id": make_event_id("test", "510k", index), "source": "test", "kind": "510k",
         "event_date": day, "available_at": available, "company_key": company,
         "track_id": track, "product_code": "ABC", "payload": {}}
        for index, (day, available, company, track) in enumerate(timeline)])
    return store


def _entry_examples(data: dict) -> dict[tuple[str, str], dict]:
    return {(row["company_key"], row["track_id"]): row for row in data["examples"]}


def _quarterly_backtest_examples(count: int = 10) -> list[dict]:
    """Synthetic quarterly origins; needs >4 origins before purged training exists."""
    examples = []
    start = date(2020, 1, 1)
    for origin_index in range(count):
        cutoff = add_months(start, origin_index * 3).isoformat()
        for index in range(12):
            label = int((index + origin_index) % 3 == 0)
            examples.append({
                "cutoff": cutoff, "label": label, "maturity": "mature",
                "company_key": f"c{index % 3}", "track_id": f"t{index % 2}",
                "first_target_event_date": "2021-06-01" if label else None,
                "features": {"rd": float(index % 4), "fin": float(index % 2)},
            })
    return examples



class SourceTests(unittest.TestCase):
    def test_sec_mapping_and_facts_keep_knowledge_time(self) -> None:
        mapping = ticker_cik_map({"0": {"ticker": "MDT", "cik_str": 1613103}})
        self.assertEqual(mapping["MDT"], "0001613103")
        payload = {"facts": {"us-gaap": {"ResearchAndDevelopmentExpense": {"units": {"USD": [{
            "start": "2023-01-01", "end": "2023-12-31", "val": 10, "accn": "a1",
            "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"
        }]}}}}}
        rows = normalize_companyfacts("medtronic", "0001613103", payload, "2026-11-01")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["available_at"], "2024-02-01")
        self.assertEqual(rows[0]["period_end"], "2023-12-31")

    def test_financial_amendment_after_cutoff_is_invisible(self) -> None:
        common = {"company_key": "medtronic", "unit": "USD", "fiscal_year": 2023,
                  "period_start": "2023-01-01", "period_end": "2023-12-31", "accession": "a"}
        rows = [
            {**common, "tag": "Revenues", "value": 100.0, "available_at": "2024-02-01"},
            {**common, "tag": "ResearchAndDevelopmentExpense", "value": 10.0, "available_at": "2024-02-01"},
            {**common, "tag": "ResearchAndDevelopmentExpense", "value": 90.0, "available_at": "2024-03-01"},
        ]
        before = financial_features(rows, "2024-02-15")
        after = financial_features(rows, "2024-03-15")
        self.assertAlmostEqual(before["fin_rd_intensity"], 0.1)
        self.assertAlmostEqual(after["fin_rd_intensity"], 0.9)
        rows.append({**common, "tag": "ResearchAndDevelopmentExpense", "value": 900.0, "available_at": "2025-01-01"})
        self.assertEqual(financial_features(rows, "2024-02-15"), before)

    def test_post_retry_preserves_method_and_body(self) -> None:
        requests = []

        def respond(request, timeout):
            requests.append(request)
            if len(requests) == 1:
                raise urllib.error.HTTPError(request.full_url, 500, "retry", {}, io.BytesIO(b"error"))

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return None

                def read(self):
                    return b'{"ok": true}'

            return Response()

        with patch("medradar.http.urllib.request.urlopen", side_effect=respond):
            result = Fetcher(min_interval=0).post_json(
                "https://example.test/awards", {"x": 1}, retries=1, backoff=0,
            )
        self.assertEqual(result, {"ok": True})
        self.assertEqual([request.method for request in requests], ["POST", "POST"])
        self.assertTrue(requests[0].data)
        self.assertEqual(requests[1].data, requests[0].data)

    def test_procurement_is_not_revenue_or_pit(self) -> None:
        row = normalize_award({
            "Award ID": "A1", "Recipient Name": "MEDTRONIC MINIMED", "Award Amount": 123.0,
            "Start Date": "2024-01-01", "End Date": "2024-12-31", "Awarding Agency": "VA",
            "NAICS": {"code": "339112", "description": "Medical instruments"},
            "generated_internal_id": "CONT_AWD_A1", "internal_id": 7,
        }, load_companies("device"), "2026-11-01T00:00:00Z")
        self.assertEqual(row["company_key"], "medtronic")
        self.assertEqual(row["contract_value"], 123.0)
        self.assertFalse(row["pit_usable"])
        self.assertIsNone(row["award_date"])
        self.assertIn("not_revenue", row["data_quality"])


class TimingAndModelTests(unittest.TestCase):
    def test_dataset_excludes_unavailable_history_and_uses_future_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _timeline_store(Path(tmp) / "x.sqlite") as store:
                data = build_examples(store, cutoffs=["2023-01-01"], horizon_months=12)
                row = data["examples"][0]
                self.assertEqual(row["features"]["rd_count_12m"], 1.0)  # not the late-publication row
                self.assertEqual(row["label"], 1)
                self.assertEqual(row["first_target_event_date"], "2023-06-01")
                store.replace_examples("reverse_rd_v1", data["examples"])
                audit = audit_examples(store, "reverse_rd_v1")
                self.assertTrue(audit["ok"])
                self.assertEqual(audit["method"], "independent_as_of_replay")
                self.assertEqual(audit["checked_examples"], 1)
                self.assertEqual(audit["mismatch_count"], 0)

    def test_purge_rule_requires_matured_label_windows(self) -> None:
        examples = [
            {"cutoff": "2020-01-01", "label": 1, "features": {}},
            {"cutoff": "2020-07-01", "label": 1, "features": {}},
            {"cutoff": "2020-10-01", "label": 0, "features": {}},
            {"cutoff": "2021-01-01", "label": 1, "features": {}},
            {"cutoff": "2021-04-01", "label": 0, "features": {}},
        ]
        self.assertEqual(label_window_end("2020-01-01").isoformat(), "2021-01-01")
        self.assertTrue(matured_by("2020-01-01", "2021-01-01"))
        self.assertFalse(matured_by("2020-07-01", "2021-01-01"))
        purged = eligible_training_rows(examples, "2021-01-01", purge=True)
        self.assertEqual([row["cutoff"] for row in purged], ["2020-01-01"])
        leaky = eligible_training_rows(examples, "2021-01-01", purge=False)
        self.assertEqual([row["cutoff"] for row in leaky], ["2020-01-01", "2020-07-01", "2020-10-01"])
        self.assertEqual(eligible_training_rows(examples, "2021-01-01", purge=True, horizon_months=6),
                         [examples[0], examples[1]])

    def test_backtest_default_is_purged_and_reports_leaky_diagnostic(self) -> None:
        report = run_backtest(_backtest_examples(), ["rd"], ["fin"], min_train_origins=3,
                              data_provenance={"retrieved_at": "2026-11-01"})
        self.assertTrue(report["purge"]["default"])
        for model in report["models"]:
            self.assertEqual(model["training_label_policy"], "matured_by_origin")
        rows = report["purge"]["training_rows_by_origin"]
        self.assertTrue(rows)
        for row in rows:
            self.assertLessEqual(row["purged_training_rows"], row["leaky_training_rows"])
        self.assertTrue(any(row["purged_training_rows"] < row["leaky_training_rows"] for row in rows))
        diagnostic = report["leaky_labels_diagnostic"]
        self.assertEqual(diagnostic["role"], "diagnostic_only")
        self.assertFalse(diagnostic["purge"])
        self.assertIn("test window", diagnostic["warning"])
        self.assertEqual([model["name"] for model in diagnostic["models"]], ["rd_only", "rd_financial"])
        for name in ("rd_only", "rd_financial"):
            delta = diagnostic["delta_purged_minus_leaky"][name]
            self.assertIn("pr_auc", delta)
            self.assertIn("development_pr_auc", delta)

    def test_persistence_baselines_and_paired_bootstrap_are_deterministic(self) -> None:
        report = run_backtest(_backtest_examples(), ["rd"], ["fin"], min_train_origins=3)
        baselines = report["baselines"]
        for name in ("constant_training_prevalence", "company_base_rate",
                     "track_base_rate", "pair_base_rate"):
            entry = baselines["predictors"][name]
            self.assertIn("pr_auc", entry)
            self.assertIn("brier", entry)
            self.assertEqual(entry["n"], baselines["holdout_rows"])
        self.assertGreater(baselines["training_rows"], 0)
        self.assertGreaterEqual(baselines["pair_base_rate_coverage"], 0.0)
        self.assertLessEqual(baselines["pair_base_rate_coverage"], 1.0)
        comparison = report["model_vs_pair_baseline"]
        self.assertEqual(comparison["resamples"], 2000)
        self.assertEqual(comparison["seed"], 7)
        for name in ("rd_only", "rd_financial"):
            entry = comparison["model_scores"][name]
            self.assertIn("delta", entry)
            self.assertGreater(entry["valid_resamples"], 0)
            self.assertLessEqual(entry["ci_low"], entry["ci_high"])
            self.assertGreaterEqual(entry["p_delta_le_zero"], 0.0)
            self.assertLessEqual(entry["p_delta_le_zero"], 1.0)
        labels = [0, 1, 1, 0, 1, 0, 1, 1]
        first = paired_bootstrap_delta_ap(labels, [0.9, 0.8, 0.7, 0.3, 0.6, 0.2, 0.55, 0.65],
                                          [0.5] * len(labels), resamples=50, seed=7)
        second = paired_bootstrap_delta_ap(labels, [0.9, 0.8, 0.7, 0.3, 0.6, 0.2, 0.55, 0.65],
                                           [0.5] * len(labels), resamples=50, seed=7)
        self.assertEqual(first, second)

    def test_leakage_audit_rejects_future_derived_feature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _timeline_store(Path(tmp) / "x.sqlite") as store:
                early = build_examples(store, cutoffs=["2023-01-01"], horizon_months=12)["examples"][0]
                later = build_examples(store, cutoffs=["2023-06-01"], horizon_months=12)["examples"][0]
                self.assertNotEqual(early["features"]["rd_recency_years"],
                                    later["features"]["rd_recency_years"])
                # Simulate injected future-derived features: the stored values are
                # computed with a later cutoff but the declared availability is unchanged.
                leaked = dict(early)
                leaked["features"] = dict(later["features"])
                store.replace_examples("reverse_rd_v1", [leaked])
                result = audit_examples(store, "reverse_rd_v1")
                self.assertFalse(result["ok"])
                self.assertGreater(result["mismatch_count"], 0)
                self.assertGreater(result["per_feature_mismatches"]["rd_recency_years"], 0)
                self.assertIn("replayed", result["mismatches"][0])

    def test_leakage_audit_rejects_tampered_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _timeline_store(Path(tmp) / "x.sqlite") as store:
                data = build_examples(store, cutoffs=["2023-01-01"], horizon_months=12)
                tampered = dict(data["examples"][0])
                tampered["feature_available_at"] = "2023-01-02"
                store.replace_examples("reverse_rd_v1", [tampered])
                result = audit_examples(store, "reverse_rd_v1")
                self.assertFalse(result["ok"])
                reasons = [entry.get("reason", "") for entry in result["violations"]]
                self.assertTrue(any("feature availability after cutoff" in reason for reason in reasons))

    def test_leakage_audit_accepts_as_of_consistent_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _timeline_store(Path(tmp) / "x.sqlite") as store:
                data = build_examples(store, cutoffs=["2023-01-01", "2023-06-01"], horizon_months=12)
                store.replace_examples("reverse_rd_v1", data["examples"])
                result = audit_examples(store, "reverse_rd_v1")
                self.assertTrue(result["ok"], result["mismatches"][:3])
                self.assertEqual(result["checked_examples"], len(data["examples"]))
                self.assertEqual(result["mismatch_count"], 0)
                self.assertEqual(result["unreplayable_examples"], 0)
                self.assertGreater(result["checked_feature_values"], 0)

    def test_forecast_evidence_separates_raw_and_standardized_values(self) -> None:
        rows = [{"x": float(value), "y": float(value % 3)} for value in range(12)]
        labels = [int(value >= 6) for value in range(12)]
        model = LogisticBaseline(["x", "y"], epochs=50).fit(rows, labels)
        evidence = {item["feature"]: item for item in model.contributions({"x": 0.0, "y": None})}
        self.assertTrue(evidence["y"]["median_imputed"])
        self.assertIsNone(evidence["y"]["raw_value"])
        self.assertIsNone(evidence["y"]["value"])  # backward-compatible alias
        self.assertFalse(evidence["x"]["median_imputed"])
        self.assertAlmostEqual(evidence["x"]["raw_value"], 0.0)
        self.assertAlmostEqual(evidence["x"]["standardized_value"],
                               (0.0 - model.means[0]) / model.scales[0])
        self.assertAlmostEqual(evidence["y"]["standardized_value"],
                               (model.medians["y"] - model.means[1]) / model.scales[1])
        for item in evidence.values():
            self.assertAlmostEqual(item["contribution"], item["coefficient"] * item["standardized_value"])

    def test_logistic_and_metrics(self) -> None:
        rows = [{"x": float(value)} for value in range(20)]
        labels = [int(value >= 10) for value in range(20)]
        model = LogisticBaseline(["x"], epochs=200).fit(rows, labels)
        probabilities = model.predict_proba(rows)
        self.assertGreater(probabilities[-1], probabilities[0])
        metrics = evaluate(labels, probabilities, lead_times=[30 if y else None for y in labels])
        for key in ("pr_auc", "brier", "ece", "false_positive_rate", "precision_at_k", "mean_lead_time_days"):
            self.assertIn(key, metrics)
        self.assertEqual(metrics["mean_lead_time_days"], 30)

    def test_pr_auc_is_invariant_to_tied_row_order(self) -> None:
        first = pr_auc([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5])
        second = pr_auc([1, 0, 1, 0], [0.5, 0.5, 0.5, 0.5])
        self.assertEqual(first, second)

    def test_backtest_has_chronological_holdout(self) -> None:
        report = run_backtest(_backtest_examples(), ["rd"], ["fin"], min_train_origins=3,
                              data_provenance={"retrieved_at": "2026-11-01"})
        self.assertEqual(report["holdout"], "2021-04-01")
        self.assertEqual(len(report["models"]), 2)
        for model in report["models"]:
            self.assertTrue(model["holdout_metrics"]["n"] > 0)
            self.assertTrue(all(row["cutoff"] < report["holdout"] for row in model["origin_metrics"] if not row["is_holdout"]))


class MultiWindowBacktestTests(unittest.TestCase):
    def test_holdouts_default_preserves_single_holdout_contract(self) -> None:
        report = run_backtest(_backtest_examples(), ["rd"], ["fin"], min_train_origins=3)
        self.assertEqual(report["holdouts"], 1)
        self.assertEqual(report["holdout"], "2021-04-01")
        self.assertEqual(report["holdout_origins"], ["2021-04-01"])
        self.assertEqual(len(report["holdout_windows"]), 1)
        window = report["holdout_windows"][0]
        for model in report["models"]:
            self.assertEqual(window["model_metrics"][model["name"]], model["holdout_metrics"])
            self.assertEqual(model["holdout_window_metrics"][0]["cutoff"], report["holdout"])
            self.assertEqual(model["holdout_window_summary"],
                             report["holdout_window_summary"]["models"][model["name"]])
        # Legacy (v1) keys stay in place; the multi-window block is additive only.
        for key in ("baselines", "model_vs_pair_baseline", "leaky_labels_diagnostic",
                    "financial_marginal_value", "purge", "models", "origins", "holdout"):
            self.assertIn(key, report)
        self.assertIn("by_window", report["model_vs_pair_baseline"])
        for metric in ("pr_auc", "brier", "ece"):
            self.assertEqual(report["holdout_window_summary"]["models"]["rd_only"][metric]["std"], 0.0)

    def test_holdouts_three_are_chronological_and_purged_per_window(self) -> None:
        examples = _quarterly_backtest_examples(10)
        report = run_backtest(examples, ["rd"], ["fin"], min_train_origins=3, holdouts=3)
        self.assertEqual(report["holdouts"], 3)
        self.assertEqual(report["holdout_origins"], ["2021-10-01", "2022-01-01", "2022-04-01"])
        self.assertEqual([window["origin"] for window in report["holdout_windows"]],
                         report["holdout_origins"])
        self.assertEqual(len({window["origin"] for window in report["holdout_windows"]}), 3)
        training_sizes = []
        for window in report["holdout_windows"]:
            origin = parse_date(window["origin"])
            self.assertTrue(window["training_origins"])
            for cutoff in window["training_origins"]:
                cutoff_day = parse_date(cutoff)
                self.assertLess(cutoff_day, origin)
                # Purge rule per window: the label window closed at or before the origin.
                self.assertLessEqual(add_months(cutoff_day, report["target_horizon_months"]), origin)
            self.assertEqual(window["rows"], 12)  # one example per synthetic pair at that origin
            training_sizes.append(window["training_rows"])
        self.assertEqual(training_sizes, sorted(training_sizes))  # expanding origin
        for model in report["models"]:
            self.assertEqual(len(model["holdout_window_metrics"]), 3)
            self.assertEqual({row["cutoff"] for row in model["holdout_window_metrics"]},
                             set(report["holdout_origins"]))
            self.assertIn("pr_auc", model["holdout_window_summary"])
            self.assertEqual(model["holdout_window_summary"]["pr_auc"]["windows"], 3)
        comparison = report["model_vs_pair_baseline"]
        self.assertEqual([entry["origin"] for entry in comparison["by_window"]], report["holdout_origins"])
        for name in ("rd_only", "rd_financial"):
            self.assertIn(name, comparison["window_mean_delta"])
            for entry in comparison["by_window"]:
                self.assertIn(name, entry["models"])

    def test_holdouts_validation(self) -> None:
        with self.assertRaises(ValueError):
            run_backtest(_quarterly_backtest_examples(10), ["rd"], ["fin"], holdouts=0)
        with self.assertRaises(ValueError):
            run_backtest(_quarterly_backtest_examples(10), ["rd"], ["fin"], holdouts=7)


class EntryTargetTests(unittest.TestCase):
    def test_active_pair_excluded_and_dormant_pairs_included(self) -> None:
        timeline = [
            ("2016-06-01", "2016-06-01", "acme", "x"),      # (acme, x) last seen 2016 -> dormant
            ("2020-06-01", "2020-06-01", "acme", "y"),      # (acme, y) active inside dormancy -> excluded
            ("2016-07-01", "2016-07-01", "other", "z"),     # second active company + third track
            ("2021-07-01", "2021-07-01", "acme", "z"),      # future entry for a dormant pair
            ("2022-06-01", "2022-06-01", "acme", "x"),      # coverage anchor after the horizon
        ]
        with tempfile.TemporaryDirectory() as tmp:
            with _entry_store(Path(tmp) / "x.sqlite", timeline) as store:
                data = build_entry_examples(store, cutoffs=["2021-01-01"], expected_coverage_end=None)
        rows = _entry_examples(data)
        self.assertNotIn(("acme", "y"), rows)
        self.assertIn(("acme", "x"), rows)
        # active companies {acme, other} x tracks {x, y, z} = 6; only (acme, y) is non-dormant
        self.assertEqual(data["candidates_by_origin"]["2021-01-01"], 5)
        self.assertEqual(len(data["examples"]), 5)
        self.assertEqual(data["positives_by_origin"]["2021-01-01"], 1)
        self.assertEqual(rows[("acme", "z")]["label"], 1)
        self.assertEqual(rows[("acme", "z")]["first_target_event_date"], "2021-07-01")
        self.assertEqual(rows[("acme", "x")]["label"], 0)

    def test_dormancy_boundary_uses_exact_calendar_months(self) -> None:
        timeline = [
            ("2018-01-01", "2018-01-01", "acme", "boundary"),    # exactly t - 36 months -> dormant
            ("2018-01-02", "2018-01-02", "acme", "just_active"),  # one day later -> not dormant
            ("2022-06-01", "2022-06-01", "acme", "anchor"),       # coverage anchor
        ]
        with tempfile.TemporaryDirectory() as tmp:
            with _entry_store(Path(tmp) / "x.sqlite", timeline) as store:
                data = build_entry_examples(store, cutoffs=["2021-01-01"], expected_coverage_end=None)
        rows = _entry_examples(data)
        self.assertEqual(add_months(parse_date("2021-01-01"), -36).isoformat(), "2018-01-01")
        self.assertIn(("acme", "boundary"), rows)
        self.assertNotIn(("acme", "just_active"), rows)

    def test_label_horizon_is_inclusive_at_t_plus_horizon(self) -> None:
        timeline = [
            ("2016-01-01", "2016-01-01", "acme", "inside"),
            ("2016-01-02", "2016-01-02", "acme", "boundary"),
            ("2016-01-03", "2016-01-03", "acme", "after"),
            ("2021-07-01", "2021-07-01", "acme", "inside"),     # inside (t, t+12m] -> label 1
            ("2022-01-01", "2022-01-01", "acme", "boundary"),   # exactly t+12m -> label 1
            ("2022-01-02", "2022-01-02", "acme", "after"),      # one day after the horizon -> label 0
        ]
        with tempfile.TemporaryDirectory() as tmp:
            with _entry_store(Path(tmp) / "x.sqlite", timeline) as store:
                data = build_entry_examples(store, cutoffs=["2021-01-01"], expected_coverage_end=None)
        rows = _entry_examples(data)
        self.assertEqual(rows[("acme", "inside")]["label"], 1)
        self.assertEqual(rows[("acme", "inside")]["first_target_event_date"], "2021-07-01")
        self.assertEqual(rows[("acme", "boundary")]["label"], 1)
        self.assertEqual(rows[("acme", "after")]["label"], 0)
        self.assertIsNone(rows[("acme", "after")]["first_target_event_date"])

    def test_immature_origin_is_pending_or_excluded(self) -> None:
        timeline = [("2016-01-01", "2016-01-01", "acme", "a"),
                    ("2021-06-01", "2021-06-01", "acme", "b")]
        with tempfile.TemporaryDirectory() as tmp:
            with _entry_store(Path(tmp) / "x.sqlite", timeline) as store:
                # horizon_end 2022-01-01 > coverage_end 2021-06-01 -> pending
                excluded = build_entry_examples(store, cutoffs=["2021-01-01"], expected_coverage_end=None)
                included = build_entry_examples(store, cutoffs=["2021-01-01"], expected_coverage_end=None,
                                                include_unmatured=True)
        self.assertEqual(excluded["examples"], [])
        self.assertEqual(excluded["cutoffs"], [])
        self.assertGreater(excluded["skipped_pending_examples"], 0)
        self.assertTrue(included["examples"])
        for row in included["examples"]:
            self.assertEqual(row["maturity"], "pending")
            self.assertIsNone(row["label"])
            self.assertIsNone(row["target_event_count"])

    def test_coverage_end_assertion_rejects_wrong_window(self) -> None:
        timeline = [("2016-01-01", "2016-01-01", "acme", "a"),
                    ("2022-06-01", "2022-06-01", "acme", "b")]
        with tempfile.TemporaryDirectory() as tmp:
            with _entry_store(Path(tmp) / "x.sqlite", timeline) as store:
                accepted = build_entry_examples(store, cutoffs=["2021-01-01"],
                                                expected_coverage_end="2022-06-01")
                self.assertTrue(accepted["coverage_check"]["ok"])
                with self.assertRaises(ValueError):
                    build_entry_examples(store, cutoffs=["2021-01-01"],
                                         expected_coverage_end="2029-01-01")

    def test_entry_features_are_point_in_time(self) -> None:
        base_timeline = [
            ("2016-01-01", "2016-01-01", "acme", "dormant"),
            ("2020-06-01", "2020-06-01", "acme", "recent"),
            ("2020-09-01", "2020-09-01", "other", "c"),
            ("2026-01-01", "2026-01-01", "other", "anchor"),  # stabilise coverage_end
        ]
        with tempfile.TemporaryDirectory() as tmp:
            with _entry_store(Path(tmp) / "x.sqlite", base_timeline) as store:
                store.upsert_financial_facts([{
                    "fact_id": "f-old", "company_key": "acme", "cik": "0000000001", "tag": "Revenues",
                    "unit": "USD", "value": 500.0, "period_start": "2019-01-01",
                    "period_end": "2019-12-31", "available_at": "2020-02-01",
                    "retrieved_at": "2026-11-01", "accession": "f-old", "fiscal_year": 2019,
                }])
                first = build_entry_examples(store, cutoffs=["2021-01-01"], expected_coverage_end=None)
                before = _entry_examples(first)[("acme", "dormant")]["features"]
                label_before = _entry_examples(first)[("acme", "dormant")]["label"]
                # (a) decision before the cutoff but only public after it; (b) genuinely
                # future event; (c) SEC amendment filed after the cutoff.
                store.db.upsert_events([
                    {"event_id": make_event_id("test", "late", 1), "source": "test", "kind": "510k",
                     "event_date": "2020-11-01", "available_at": "2021-06-01", "company_key": "acme",
                     "track_id": "recent", "product_code": "ABC", "payload": {}},
                    {"event_id": make_event_id("test", "future", 2), "source": "test", "kind": "510k",
                     "event_date": "2021-06-01", "available_at": "2021-06-01", "company_key": "acme",
                     "track_id": "dormant", "product_code": "ABC", "payload": {}},
                ])
                store.upsert_financial_facts([{
                    "fact_id": "f-amended", "company_key": "acme", "cik": "0000000001", "tag": "Revenues",
                    "unit": "USD", "value": 9000.0, "period_start": "2019-01-01",
                    "period_end": "2019-12-31", "available_at": "2021-06-01",
                    "retrieved_at": "2026-11-01", "accession": "f-amended", "fiscal_year": 2019,
                }])
                leaky = build_entry_examples(store, cutoffs=["2021-01-01"], expected_coverage_end=None)
                after = _entry_examples(leaky)[("acme", "dormant")]
                self.assertEqual(after["features"], before)
                self.assertEqual(after["label"], 1)  # the future event does change the label ...
                self.assertEqual(label_before, 0)     # ... but not the features
                # A fact that was already public at the cutoff does change the feature row,
                # proving the financial path is live rather than the comparison being vacuous.
                store.upsert_financial_facts([{
                    "fact_id": "f-new", "company_key": "acme", "cik": "0000000001", "tag": "Revenues",
                    "unit": "USD", "value": 700.0, "period_start": "2020-01-01",
                    "period_end": "2020-12-31", "available_at": "2020-12-01",
                    "retrieved_at": "2026-11-01", "accession": "f-new", "fiscal_year": 2020,
                }])
                sensitive = build_entry_examples(store, cutoffs=["2021-01-01"], expected_coverage_end=None)
                self.assertNotEqual(_entry_examples(sensitive)[("acme", "dormant")]["features"], after["features"])

    def test_entry_audit_replays_entry_features_and_catches_tampering(self) -> None:
        timeline = [
            ("2016-01-01", "2016-01-01", "acme", "a"),
            ("2020-06-01", "2020-06-01", "acme", "b"),
            ("2020-09-01", "2020-09-01", "other", "c"),
            ("2026-01-01", "2026-01-01", "other", "anchor"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            with _entry_store(Path(tmp) / "x.sqlite", timeline) as store:
                data = build_entry_examples(store, cutoffs=["2021-01-01"], expected_coverage_end=None)
                store.replace_examples(ENTRY_DATASET_VERSION, data["examples"])
                audit = audit_examples(store, ENTRY_DATASET_VERSION)
                self.assertTrue(audit["ok"], audit["mismatches"][:3])
                self.assertTrue(audit["entry_target"])
                self.assertEqual(audit["checked_examples"], len(data["examples"]))
                self.assertEqual(audit["mismatch_count"], 0)
                for name in ENTRY_FEATURES:
                    self.assertIn(name, audit["replayed_features"])
                tampered = json.loads(json.dumps(data["examples"]))
                tampered[0]["features"]["rd_company_active_tracks_12m"] += 1.0
                store.replace_examples(ENTRY_DATASET_VERSION, tampered)
                result = audit_examples(store, ENTRY_DATASET_VERSION)
                self.assertFalse(result["ok"])
                self.assertGreater(result["per_feature_mismatches"]["rd_company_active_tracks_12m"], 0)


class AblationSpecificationTests(unittest.TestCase):
    """Custom feature-group specifications used by the Phase 2 ablation driver."""

    def test_custom_specifications_are_evaluated_once_and_named(self) -> None:
        examples = _quarterly_backtest_examples(12)
        report = run_backtest(
            examples, ["rd"], [], holdouts=1,
            specifications=[("custom", "custom group", ["rd", "fin"])],
            experiment="custom_spec_test")
        self.assertEqual([model["name"] for model in report["models"]], ["custom"])
        self.assertIn("holdout_metrics", report["models"][0])
        self.assertIn("holdout_window_metrics", report["models"][0])
        # The two-spec financial ledger is only meaningful for the default shape.
        self.assertNotIn("financial_marginal_value", report)
        self.assertEqual(report["experiment"], "custom_spec_test")

    def test_default_specifications_unchanged(self) -> None:
        examples = _quarterly_backtest_examples(12)
        report = run_backtest(examples, ["rd"], ["fin"], holdouts=1)
        self.assertEqual([model["name"] for model in report["models"]], ["rd_only", "rd_financial"])
        self.assertIn("financial_marginal_value", report)


class StorageTests(unittest.TestCase):
    def test_financial_procurement_and_forecast_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with IntelligenceStore(DB(Path(tmp) / "x.sqlite")) as store:
                store.upsert_procurement([{
                    "procurement_id": "p1", "supplier": "ACME", "available_at": "2026-11-01",
                    "retrieved_at": "2026-11-01", "data_quality": "current_snapshot_first_publication_unknown",
                }])
                store.upsert_forecast({
                    "forecast_id": "f1", "target_company": "medtronic", "technology_track": "spine",
                    "forecast_creation_time": "2026-11-01", "historical_information_cutoff": "2026-10-01",
                    "forecast_horizon_months": 12, "horizon_end": "2027-10-01", "model_version": "v1",
                    "predicted_probability": 0.4, "uncertainty": {}, "supporting_evidence": [],
                    "contradictory_evidence": [], "verification_condition": {}, "status": "pending",
                })
                row = store.conn.execute("SELECT * FROM horizon_forecasts").fetchone()
                self.assertEqual(row["forecast_id"], "f1")
                self.assertEqual(row["outcome"], None)


if __name__ == "__main__":
    unittest.main()
