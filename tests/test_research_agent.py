"""Offline tests for the deterministic evidence-grounded research agent.

The fixture builds a small synthetic research database and a synthetic canonical
forecast registry. Nothing here touches the network: the data is generated
deterministically below, and the agent must not import any network or LLM
module.
"""
from __future__ import annotations

import json
import io
import re
import socket
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from medradar import research_agent as agent
from medradar.db import DB, make_event_id
from medradar.forecast_registry import SCHEMA as REGISTRY_SCHEMA
from medradar.intelligence.sources.publications import PUBLICATION_COUNTS_DDL
from medradar.intelligence.storage import IntelligenceStore

AS_OF = "2023-01-01"
COMPANY, TRACK = "medtronic", "spine"
REQUIRED_KEYS = ("question", "template", "as_of", "company", "track", "plan", "steps", "evidence",
                 "conflicts", "hypothesis", "counter_evidence", "statistical_validation",
                 "uncertainty", "synthesis", "citations", "limitations", "log", "stop_condition")
SHA = "a" * 64


# ------------------------------------------------------------------ fixtures
def _business_days(start: date, end: date) -> list[date]:
    days, current = [], start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _event(store: IntelligenceStore, key: str, day: str, company: str, track: str, *,
           available: str | None = None, kind: str = "510k", payload: dict | None = None) -> None:
    store.db.upsert_events([{
        "event_id": make_event_id("agent-test", kind, key), "source": "agent-test", "kind": kind,
        "event_date": day, "available_at": available or day, "company_key": company,
        "track_id": track, "product_code": "ABC", "payload": payload or {},
    }])


def _financial_fact(store: IntelligenceStore, fact_id: str, tag: str, value: float,
                    period_start: str, period_end: str, available: str, year: int) -> None:
    store.upsert_financial_facts([{
        "fact_id": fact_id, "company_key": COMPANY, "cik": "0000000001", "tag": tag, "unit": "USD",
        "value": value, "period_start": period_start, "period_end": period_end,
        "available_at": available, "retrieved_at": "2026-11-01", "accession": fact_id,
        "fiscal_year": year,
    }])


def _bars(store: IntelligenceStore, ticker: str, closes: list[float]) -> None:
    days = _business_days(date(2019, 1, 1), date(2022, 12, 30))
    rows = []
    for day, close in zip(days, closes):
        rows.append((ticker, day.isoformat(), close, close, close, close, close, 1000,
                     "agent-test", "2026-11-01T00:00:00Z"))
    store.conn.executemany(
        "INSERT OR REPLACE INTO market_bars VALUES (?,?,?,?,?,?,?,?,?,?)", rows)


def _example(version: str, key: str, cutoff: str, label: int, company: str, track: str) -> dict:
    return {
        "example_id": make_event_id("agent-test", "example", key), "cutoff": cutoff,
        "horizon_months": 12, "company_key": company, "track_id": track,
        "features": {"rd_count_12m": float(label)}, "feature_available_at": cutoff,
        "label": label, "first_target_event_date": None, "target_event_count": None,
        "maturity": "mature",
    }


def _forecast_row(store: IntelligenceStore, forecast_id: str, created: str, p: float) -> None:
    store.upsert_forecast({
        "forecast_id": forecast_id, "target_company": COMPANY, "technology_track": TRACK,
        "forecast_creation_time": created, "historical_information_cutoff": "2022-10-01",
        "forecast_horizon_months": 12, "horizon_end": "2023-10-01", "model_version": "test-model",
        "predicted_probability": p,
        "uncertainty": {"note": "test spread", "temporal_ensemble_std": 0.02},
        "supporting_evidence": [], "contradictory_evidence": [], "verification_condition": {},
        "baseline_probability": 0.5, "status": "pending",
    })


def _registry(path: Path, *, include_forecast: bool = True) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(REGISTRY_SCHEMA)
    if include_forecast:
        conn.execute(
            "INSERT INTO forecasts (prediction_id, generated_at, record_kind, information_cutoff,"
            " information_cutoff_precision, target_type, target_id, target_attrs, horizon_months,"
            " window_start, window_end, model_version, feature_version, snapshot_sha256,"
            " snapshot_verification, provenance, source_locator, evidence_sha256, evidence_kind, p,"
            " idempotency_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("pred-visible", "2022-12-01T00:00:00.000000Z", "forecast",
             "2022-10-01T00:00:00.000000Z", "datetime", "company_track_pair", f"{COMPANY}:{TRACK}",
             "{}", 12, "2022-12-01T00:00:00.000000Z", "2023-12-01T00:00:00.000000Z",
             "test-model", "test-features", SHA, "declared",
             json.dumps([{"source_locator": "test:snapshot", "evidence_sha256": SHA}]),
             "test:evidence", SHA, "source_observed", 0.9, "key-visible"))
        conn.execute(
            "INSERT INTO forecasts (prediction_id, generated_at, record_kind, information_cutoff,"
            " information_cutoff_precision, target_type, target_id, target_attrs, horizon_months,"
            " window_start, window_end, model_version, feature_version, snapshot_sha256,"
            " snapshot_verification, provenance, source_locator, evidence_sha256, evidence_kind, p,"
            " idempotency_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("pred-future", "2023-02-01T00:00:00.000000Z", "forecast",
             "2023-01-15T00:00:00.000000Z", "datetime", "company_track_pair", f"{COMPANY}|{TRACK}",
             json.dumps({"company": COMPANY, "track": TRACK}), 12,
             "2023-02-01T00:00:00.000000Z", "2024-02-01T00:00:00.000000Z",
             "test-model", "test-features", SHA, "declared",
             json.dumps([{"source_locator": "test:snapshot", "evidence_sha256": SHA}]),
             "test:evidence", SHA, "source_observed", 0.1, "key-future"))
        conn.execute(
            "INSERT INTO resolutions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("pred-visible", 1, "outcome", 0, None, None, "2023-06-01T00:00:00.000000Z", 1,
             "test:resolution", "b" * 64, "source_observed", "test outcome"))
        conn.execute(
            "INSERT INTO forecasts (prediction_id, generated_at, record_kind, information_cutoff,"
            " information_cutoff_precision, target_type, target_id, target_attrs, horizon_months,"
            " window_start, window_end, model_version, feature_version, snapshot_sha256,"
            " snapshot_verification, provenance, source_locator, evidence_sha256, evidence_kind, p,"
            " idempotency_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("pred-other", "2022-12-01T00:00:00.000000Z", "forecast",
             "2022-10-01T00:00:00.000000Z", "datetime", "company_track_pair", "abbott:dental",
             "{}", 12, "2022-12-01T00:00:00.000000Z", "2023-12-01T00:00:00.000000Z",
             "test-model", "test-features", SHA, "declared",
             json.dumps([{"source_locator": "test:snapshot", "evidence_sha256": SHA}]),
             "test:evidence", SHA, "source_observed", 0.5, "key-other"))
    conn.commit()
    conn.close()
    return path


def _build_fixture(root: Path) -> tuple[Path, Path, Path]:
    db_path = root / "research.sqlite"
    with IntelligenceStore(DB(db_path)) as store:
        store.conn.executescript(PUBLICATION_COUNTS_DDL)
        # Pair under study: active in 2020-2022, one not-yet-public event.
        _event(store, "spine-1", "2020-01-15", COMPANY, TRACK)
        _event(store, "spine-2", "2021-03-01", COMPANY, TRACK)
        _event(store, "spine-3", "2022-02-01", COMPANY, TRACK)
        _event(store, "spine-late", "2022-06-01", COMPANY, TRACK, available="2023-06-01")
        _event(store, "spine-future", "2023-06-01", COMPANY, TRACK)
        # Dormant pair for the entry template.
        _event(store, "dental-1", "2018-01-01", COMPANY, "dental")
        # Track activity by another company: triggers the dormancy conflict.
        for index in range(12):
            _event(store, f"other-{index}", f"2022-{(index % 11) + 1:02d}-{10 + index:02d}",
                   "stryker", TRACK)
        # A second dormant pair whose track is busy with other companies: the
        # entry template must surface track activity versus company dormancy.
        _event(store, "rhythm-1", "2018-06-01", COMPANY, "cardiac_rhythm")
        for index in range(12):
            _event(store, f"rhythm-other-{index}", f"2022-{(index % 11) + 1:02d}-{10 + index:02d}",
                   "stryker", "cardiac_rhythm")
        # Financials: revenue and R&D both declining (negative fundamentals).
        _financial_fact(store, "rev-2019", "Revenues", 100.0, "2019-01-01", "2019-12-31", "2020-02-15", 2019)
        _financial_fact(store, "rev-2020", "Revenues", 90.0, "2020-01-01", "2020-12-31", "2021-02-15", 2020)
        _financial_fact(store, "rev-2021", "Revenues", 80.0, "2021-01-01", "2021-12-31", "2022-02-15", 2021)
        _financial_fact(store, "rd-2019", "ResearchAndDevelopmentExpense", 10.0,
                        "2019-01-01", "2019-12-31", "2020-02-15", 2019)
        _financial_fact(store, "rd-2020", "ResearchAndDevelopmentExpense", 9.0,
                        "2020-01-01", "2020-12-31", "2021-02-15", 2020)
        _financial_fact(store, "rd-2021", "ResearchAndDevelopmentExpense", 8.0,
                        "2021-01-01", "2021-12-31", "2022-02-15", 2021)
        # Market: a rising company series and flat benchmarks.
        days = len(_business_days(date(2019, 1, 1), date(2022, 12, 30)))
        _bars(store, "MDT", [100.0 * (1 + 0.0008 * index) for index in range(days)])
        _bars(store, "SPY", [100.0 * (1 + 0.0002 * index) for index in range(days)])
        _bars(store, "XBI", [100.0 * (1 + 0.0001 * index) for index in range(days)])
        store.conn.executemany(
            "INSERT OR REPLACE INTO publication_counts VALUES (?,?,?,?,?)",
            [(COMPANY, 2019, 10, "test", "2026-11-01T00:00:00Z"),
             (COMPANY, 2020, 12, "test", "2026-11-01T00:00:00Z"),
             (COMPANY, 2021, 8, "test", "2026-11-01T00:00:00Z")])
        # Continuation examples: two matured purged rows, labels 0 and 0 (low base rate).
        store.replace_examples("reverse_rd_v1", [
            _example("reverse_rd_v1", "cont-1", "2021-10-01", 0, COMPANY, TRACK),
            _example("reverse_rd_v1", "cont-2", "2022-01-01", 0, COMPANY, TRACK),
            _example("reverse_rd_v1", "cont-3", "2022-04-01", 1, COMPANY, TRACK),
            _example("reverse_rd_v1", "cont-global", "2022-01-01", 1, "abbott", "dental"),
        ])
        # Entry examples for the dormant pair.
        store.replace_examples("first_entry_v1", [
            _example("first_entry_v1", "entry-1", "2021-10-01", 0, COMPANY, "dental"),
            _example("first_entry_v1", "entry-2", "2022-01-01", 0, COMPANY, "dental"),
            _example("first_entry_v1", "entry-3", "2021-10-01", 1, COMPANY, "cardiac_rhythm"),
            _example("first_entry_v1", "entry-4", "2022-01-01", 0, COMPANY, "cardiac_rhythm"),
        ])
        # Frozen model forecast: visible at AS_OF.
        _forecast_row(store, "hf-visible", "2022-11-01T00:00:00Z", 0.6)
        # Frozen model forecast: created after AS_OF (must stay invisible).
        _forecast_row(store, "hf-future", "2023-02-01T00:00:00Z", 0.99)
        store.conn.commit()
    return (db_path, _registry(root / "registry.sqlite"), root)


def _strip_timestamps(value):
    if isinstance(value, dict):
        return {key: _strip_timestamps(item) for key, item in value.items()
                if key not in ("at", "generated_at")}
    if isinstance(value, list):
        return [_strip_timestamps(item) for item in value]
    return value


def _citation_exists(db_path: Path, registry: Path | None, citation: dict) -> bool:
    kind, locator = citation["kind"], citation["locator"]
    conn = sqlite3.connect(db_path)
    try:
        if kind == "event":
            return conn.execute("SELECT 1 FROM events WHERE event_id = ?", (locator,)).fetchone() is not None
        if kind == "financial_fact":
            return conn.execute("SELECT 1 FROM financial_facts WHERE fact_id = ?", (locator,)).fetchone() is not None
        if kind == "example":
            return conn.execute("SELECT 1 FROM forecast_examples WHERE example_id = ?", (locator,)).fetchone() is not None
        if kind == "horizon_forecast":
            return conn.execute("SELECT 1 FROM horizon_forecasts WHERE forecast_id = ?", (locator,)).fetchone() is not None
        if kind == "market_bar":
            ticker, day = locator.rsplit(":", 1)
            return conn.execute("SELECT 1 FROM market_bars WHERE ticker = ? AND date = ?",
                                (ticker, day)).fetchone() is not None
        if kind == "publication_count":
            company, year = locator.rsplit(":", 1)
            return conn.execute("SELECT 1 FROM publication_counts WHERE company_key = ? AND year = ?",
                                (company, int(year))).fetchone() is not None
    finally:
        conn.close()
    if kind == "registry_forecast":
        if registry is None or not Path(registry).exists():
            return False
        conn = sqlite3.connect(registry)
        try:
            return conn.execute("SELECT 1 FROM forecasts WHERE prediction_id = ?",
                                (locator,)).fetchone() is not None
        finally:
            conn.close()
    return False  # tkg_assertion is exercised by its own graph test


class AgentFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.db, self.registry, _ = _build_fixture(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, **overrides):
        kwargs = {"template": "entry_forecast", "as_of": AS_OF, "db": self.db,
                  "registry": self.registry}
        kwargs.update(overrides)
        return agent.run_agent(kwargs.pop("company", COMPANY), kwargs.pop("track", TRACK), **kwargs)

    # ---------------------------------------------------------- workflow shape
    def test_every_template_runs_with_required_keys(self) -> None:
        for template in sorted(agent.TEMPLATES):
            with self.subTest(template=template):
                document = self._run(template=template)
                for key in REQUIRED_KEYS:
                    self.assertIn(key, document)
                self.assertEqual(document["template"], template)
                self.assertTrue(document["plan"])
                self.assertEqual(len(document["steps"]), len(document["plan"]))
                self.assertEqual(document["stop_condition"]["reached"], True)
                self.assertEqual(document["stop_condition"]["planned_steps"], len(document["plan"]))
                self.assertTrue(document["hypothesis"]["statement"])
                self.assertIn("not a causal finding", document["hypothesis"]["label"])
                self.assertTrue(document["log"])
                self.assertTrue(document["limitations"])

    def test_each_template_has_a_template_focus_block(self) -> None:
        focus_keys = {
            "entry_forecast": "dormancy",
            "market_leading_indicator": "market_vs_rd_history",
            "early_signal": "signal_density",
            "strategic_shift": "track_shift",
            "cross_source_validation": "source_agreement",
        }
        for template, focus_key in focus_keys.items():
            with self.subTest(template=template):
                document = self._run(template=template)
                self.assertIn(focus_key, document["template_focus"])

    # ------------------------------------------------------------ citations
    def test_every_observed_or_derived_claim_has_a_real_citation(self) -> None:
        for template in sorted(agent.TEMPLATES):
            with self.subTest(template=template):
                document = self._run(template=template)
                claims = {claim["claim_id"]: claim for claim in document["evidence"]}
                self.assertTrue(claims)
                for claim in document["evidence"]:
                    if claim["evidence_status"] in ("observed", "derived"):
                        self.assertTrue(claim["citations"],
                                        f"{claim['claim_id']} has no citation")
                        for citation in claim["citations"]:
                            self.assertTrue(_citation_exists(self.db, self.registry, citation),
                                            f"missing citation {citation} for {claim['claim_id']}")
                for statement in document["synthesis"]:
                    for claim_id in statement["claim_ids"]:
                        self.assertIn(claim_id, claims)
                    for missing in statement["missing_claims"]:
                        self.assertNotIn(missing, claims)
                    if statement["evidence_status"] in ("observed", "derived"):
                        self.assertTrue(statement["citations"])
                for conflict in document["conflicts"]:
                    for claim_id in conflict["claims"]:
                        self.assertIn(claim_id, claims)
                for claim_id in document["hypothesis"]["supported_by_claims"]:
                    self.assertIn(claim_id, claims)

    # -------------------------------------------------------- determinism
    def test_output_is_deterministic_excluding_log_timestamps(self) -> None:
        first = self._run()
        second = self._run()
        self.assertEqual(_strip_timestamps(first), _strip_timestamps(second))

    # ----------------------------------------------------- conflict rules
    def test_conflict_detection_triggers_on_constructed_conflicts(self) -> None:
        # Continuation target: registry p=0.9 vs pair base rate 0.0 while the
        # market is rising and revenue/R&D/publications are declining.
        document = self._run(template="cross_source_validation")
        rules = {conflict["rule"] for conflict in document["conflicts"]}
        self.assertIn("model_high_vs_base_rate_low", rules)
        self.assertIn("market_positive_vs_fundamentals_negative", rules)
        self.assertIn("market_positive_vs_publication_negative", rules)
        for conflict in document["conflicts"]:
            self.assertTrue(conflict["description"])
            self.assertTrue(conflict["citations"])
        # The forward-looking (post-as-of) registry row must not be used.
        forecast = next(claim for claim in document["evidence"]
                        if claim["claim_id"] == "forecast_evidence")
        self.assertEqual(forecast["values"]["matched"], 2)
        self.assertEqual(forecast["values"]["visible"], 1)
        self.assertEqual(forecast["values"]["forecasts"][0]["visible_at_as_of"], True)

    def test_track_activity_vs_dormancy_conflict(self) -> None:
        # medtronic/cardiac_rhythm: pair dormant since 2018 while stryker has 12
        # material events in the same track in the trailing 12 months.
        document = self._run(template="entry_forecast", track="cardiac_rhythm")
        rules = {conflict["rule"] for conflict in document["conflicts"]}
        self.assertIn("track_activity_vs_company_dormancy", rules)

    # ------------------------------------------------ empty registry degradation
    def test_empty_registry_degrades_honestly(self) -> None:
        missing = self.root / "no-registry.sqlite"
        document = self._run(registry=missing)
        self.assertTrue(document["degraded"])
        self.assertTrue(any(failure["tool"] == "forecast_evidence" for failure in document["failures"]))
        forecast_claim = next(claim for claim in document["evidence"]
                              if claim["claim_id"] == "forecast_evidence")
        self.assertEqual(forecast_claim["evidence_status"], "not_available")
        validation = document["statistical_validation"]
        self.assertEqual(validation["calibration_status"], "insufficient_verified_forecasts")
        self.assertIsNone(validation["model_probability"])
        self.assertIsNone(validation["delta"])
        self.assertIn("canonical forecast registry: absent",
                      " ".join(document["uncertainty"]["missing_sources"]))
        statement = " ".join(entry["statement"] for entry in document["synthesis"])
        self.assertIn("No model or registered probability", statement)

    def test_registry_without_matching_forecast_is_honest(self) -> None:
        document = self._run(registry=_registry(self.root / "overly-specific.sqlite",
                                                include_forecast=False))
        forecast_claim = next(claim for claim in document["evidence"]
                              if claim["claim_id"] == "forecast_evidence")
        self.assertEqual(forecast_claim["evidence_status"], "not_available")
        self.assertIn("no_registered_forecast", forecast_claim["statement"])

    # --------------------------------------------------------- PIT behaviour
    def test_event_and_market_history_are_point_in_time(self) -> None:
        history = agent.event_history(self.db, COMPANY, TRACK, AS_OF)
        self.assertEqual(history["values"]["total"], 3)  # late and future events excluded
        self.assertEqual(history["values"]["last_event_date"], "2022-02-01")
        market = agent.market_context(self.db, COMPANY, AS_OF,
                                      tickers={COMPANY: "MDT"})
        self.assertLessEqual(market["values"]["last_bar_date"], AS_OF)
        # A bar dated exactly on as_of is visible; one day later is not.
        conn = sqlite3.connect(self.db)
        conn.execute("INSERT INTO market_bars VALUES (?,?,?,?,?,?,?,?,?,?)",
                     ("MDT", "2023-01-02", 1.0, 1.0, 1.0, 1.0, 1.0, 1, "test", "2026-11-01"))
        conn.commit()
        conn.close()
        market_after = agent.market_context(self.db, COMPANY, AS_OF, tickers={COMPANY: "MDT"})
        self.assertEqual(market_after["values"]["last_bar_date"], market["values"]["last_bar_date"])

    def test_forecast_visibility_uses_creation_time(self) -> None:
        baseline = agent.baseline_comparison(
            self.db, COMPANY, TRACK, AS_OF, target="continuation",
            registry=self.root / "absent.sqlite")
        self.assertEqual(baseline["values"]["model"]["p"], 0.6)  # hf-future is invisible
        self.assertEqual(baseline["values"]["model"]["source"], "frozen_model_forecasts")
        self.assertEqual(baseline["values"]["pair_purged_rows"], 2)
        self.assertEqual(baseline["values"]["pair_base_rate"], 0.0)

    def test_registry_forecast_is_preferred_over_frozen_table(self) -> None:
        baseline = agent.baseline_comparison(self.db, COMPANY, TRACK, AS_OF,
                                             target="continuation", registry=self.registry)
        self.assertEqual(baseline["values"]["model"]["source"], "canonical_registry")
        self.assertEqual(baseline["values"]["model"]["p"], 0.9)

    # ----------------------------------------------------------- graph tool
    def test_graph_context_reports_soft_dependency_states(self) -> None:
        not_requested = agent.graph_context(None, COMPANY, TRACK, AS_OF)
        self.assertEqual(not_requested["status"], "not_requested")
        missing = agent.graph_context(self.root / "missing-tkg.sqlite", COMPANY, TRACK, AS_OF)
        self.assertEqual(missing["status"], "unavailable")
        # A minimal TKG-shaped file exercises the read-only raw fallback.
        tkg_path = self.root / "tkg.sqlite"
        conn = sqlite3.connect(tkg_path)
        conn.execute("CREATE TABLE nodes (assertion_id TEXT, node_type TEXT, node_id TEXT,"
                     " recorded_at TEXT)")
        conn.execute("CREATE TABLE edges (assertion_id TEXT, edge_type TEXT, src_id TEXT,"
                     " dst_id TEXT, recorded_at TEXT)")
        conn.execute("INSERT INTO nodes VALUES ('assert-1', 'Company', ?,"
                     " '2022-01-01T00:00:00.000000Z')", (COMPANY,))
        conn.commit()
        conn.close()
        graph = agent.graph_context(tkg_path, COMPANY, TRACK, AS_OF)
        self.assertEqual(graph["status"], "ok")
        self.assertTrue(graph["citations"])
        self.assertEqual(graph["citations"][0]["kind"], "tkg_assertion")

    # --------------------------------------------------- unavailable evidence
    def test_unknown_pair_degrades_without_crashing(self) -> None:
        document = agent.run_agent("nobody", "nowhere", template="entry_forecast",
                                   as_of=AS_OF, db=self.db, registry=self.registry)
        statuses = {step["tool"]: step["status"] for step in document["steps"]}
        self.assertEqual(statuses["event_history"], "no_events")
        self.assertEqual(statuses["financial_context"], "no_financial_facts")
        self.assertIn(statuses["market_context"], ("no_ticker", "no_market_data"))
        self.assertEqual(statuses["publication_context"], "no_publication_data")
        self.assertEqual(statuses["baseline_comparison"], "no_examples")
        self.assertTrue(document["degraded"])
        self.assertIsNone(document["statistical_validation"]["pair_base_rate"])
        self.assertIsNone(document["hypothesis"]["model_probability"])

    # ------------------------------------------------------------ invariants
    def test_no_network_or_llm_imports(self) -> None:
        source = Path(agent.__file__).read_text(encoding="utf-8")
        forbidden = re.findall(
            r"(?m)^\s*(?:import|from)\s+(requests|urllib|urllib3|httpx|aiohttp|socket|openai|"
            r"anthropic|medradar\.llm|\.llm)\b", source)
        self.assertEqual(forbidden, [], f"forbidden imports: {forbidden}")
        with patch.object(socket, "socket", side_effect=AssertionError("network access attempted")):
            document = self._run()
        self.assertIn("evidence", document)
        self.assertNotIn("llm", {key.lower() for key in document})

    def test_markdown_renderer_contains_sections_and_citations(self) -> None:
        document = self._run()
        markdown = agent.render_markdown(document)
        for heading in ("# Research agent", "## Hypothesis", "## Evidence table", "## Conflicts",
                        "## Counter-evidence", "## Statistical validation", "## Synthesis",
                        "## Uncertainty", "## Research log", "## Stop condition", "## Limitations"):
            self.assertIn(heading, markdown)
        self.assertIn("event:", markdown)

    def test_counter_evidence_always_lists_checks(self) -> None:
        document = self._run()
        items = document["counter_evidence"]["items"]
        self.assertGreaterEqual(len(items), 3)
        checks = {item["check"] for item in items}
        self.assertIn("track_activity_by_other_companies", checks)
        self.assertIn("company_activity_in_other_tracks", checks)
        self.assertIn("market_regime", checks)
        self.assertIn("peer_financial_trend", checks)
        for item in items:
            self.assertTrue(item["finding"])
            self.assertIn(item["evidence_status"], ("observed", "derived", "not_available", "insufficient"))


class AgentCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.db, self.registry, _ = _build_fixture(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_list_templates(self) -> None:
        with patch("sys.stdout", new_callable=lambda: __import__("io").StringIO()) as output:
            self.assertEqual(agent.main(["--list-templates"]), 0)
            payload = json.loads(output.getvalue())
        self.assertEqual([entry["name"] for entry in payload], sorted(agent.TEMPLATES))

    def test_ask_writes_json_and_markdown(self) -> None:
        out = self.root / "out" / "document.json"
        code = agent.main(["ask", "--company", COMPANY, "--track", TRACK, "--template",
                           "entry_forecast", "--as-of", AS_OF, "--db", str(self.db),
                           "--registry", str(self.registry), "--out", str(out)])
        self.assertEqual(code, 0)
        document = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(document["template"], "entry_forecast")
        self.assertTrue(document["citations"])
        markdown_path = self.root / "out" / "document.md"
        code = agent.main(["ask", "--company", COMPANY, "--track", TRACK, "--template",
                           "cross_source_validation", "--as-of", AS_OF, "--db", str(self.db),
                           "--registry", str(self.registry), "--format", "markdown",
                           "--out", str(markdown_path)])
        self.assertEqual(code, 0)
        self.assertIn("## Evidence table", markdown_path.read_text(encoding="utf-8"))

    def test_unknown_template_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            agent.main(["ask", "--company", COMPANY, "--track", TRACK,
                        "--template", "not-a-template", "--db", str(self.db)])


class StdioEncodingTests(unittest.TestCase):
    """Windows consoles use a legacy codepage; the CLI must not crash on →."""

    def test_configure_stdio_requests_utf8_and_tolerates_plain_streams(self) -> None:
        class Dummy:
            def __init__(self) -> None:
                self.kwargs = None

            def reconfigure(self, **kwargs) -> None:
                self.kwargs = kwargs

        out, err = Dummy(), Dummy()
        with patch.object(agent.sys, "stdout", out), patch.object(agent.sys, "stderr", err):
            agent._configure_stdio()
        self.assertEqual(out.kwargs, {"encoding": "utf-8", "errors": "replace"})
        self.assertEqual(err.kwargs, {"encoding": "utf-8", "errors": "replace"})
        # Streams without ``reconfigure`` (StringIO) must be left alone, not fail.
        with patch.object(agent.sys, "stdout", io.StringIO()), patch.object(agent.sys, "stderr", io.StringIO()):
            agent._configure_stdio()


if __name__ == "__main__":
    unittest.main()
