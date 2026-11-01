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
from medradar.intelligence.evaluation.backtesting import run_backtest
from medradar.intelligence.evaluation.leakage_audit import audit_examples
from medradar.intelligence.evaluation.metrics import evaluate, pr_auc
from medradar.intelligence.features.financial_features import financial_features
from medradar.intelligence.features.research_features import build_examples
from medradar.intelligence.models.baseline import LogisticBaseline
from medradar.intelligence.sources.procurement_us import normalize_award
from medradar.intelligence.sources.sec_financials import normalize_companyfacts, ticker_cik_map
from medradar.intelligence.storage import IntelligenceStore


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
    def _store(self, path: Path) -> IntelligenceStore:
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

    def test_dataset_excludes_unavailable_history_and_uses_future_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self._store(Path(tmp) / "x.sqlite") as store:
                data = build_examples(store, cutoffs=["2023-01-01"], horizon_months=12)
                row = data["examples"][0]
                self.assertEqual(row["features"]["rd_count_12m"], 1.0)  # not the late-publication row
                self.assertEqual(row["label"], 1)
                self.assertEqual(row["first_target_event_date"], "2023-06-01")
                store.replace_examples("reverse_rd_v1", data["examples"])
                self.assertTrue(audit_examples(store, "reverse_rd_v1")["ok"])

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
        examples = []
        for origin_index, cutoff in enumerate(("2020-01-01", "2020-04-01", "2020-07-01", "2020-10-01", "2021-01-01", "2021-04-01")):
            for index in range(12):
                label = int((index + origin_index) % 3 == 0)
                examples.append({
                    "cutoff": cutoff, "label": label, "maturity": "mature",
                    "first_target_event_date": "2021-06-01" if label else None,
                    "features": {"rd": float(index % 4), "fin": float(index % 2)},
                })
        report = run_backtest(examples, ["rd"], ["fin"], min_train_origins=3,
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
