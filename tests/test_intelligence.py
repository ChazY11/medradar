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
from medradar.intelligence.features.research_features import build_examples
from medradar.intelligence.models.baseline import LogisticBaseline
from medradar.intelligence.sources.procurement_us import normalize_award
from medradar.intelligence.sources.sec_financials import normalize_companyfacts, ticker_cik_map
from medradar.intelligence.storage import IntelligenceStore


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
