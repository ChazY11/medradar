"""Unit tests for the frozen b103 cross-source lead/lag implementation.

Standard library only; no network; no repository data files.  Every fixture is
synthetic and in memory.  Run with::

    python -m unittest tests.test_leadlag -v

Coverage required by the task leaf:
* hand-checked z-score / correlation / lag alignment, and a known synthetic
  *leading* series recovering ``k* > 0``;
* circular-shift rotation-null determinism;
* exclusion counts (no-data and short series companies excluded and counted);
* no numpy / pandas / scipy imports anywhere in the committed module.
"""

from __future__ import annotations

import importlib.util
import json
import math
import random
import re
import unittest
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "experiments" / "b103_leadlag" / "leadlag.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("b103_leadlag", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = _load_module()


def _pattern(seed: int = 1234, length: int = 36) -> list[float]:
    """Deterministic, non-periodic-looking series used by the lag fixtures."""
    rng = random.Random(seed)
    return [rng.uniform(-1.0, 1.0) for _ in range(length)]


def _shift(values: list[float], offset: int) -> list[float]:
    """``out[t] = values[(t + offset) % T]`` (source at t equals milestone at t+offset)."""
    length = len(values)
    return [values[(t + offset) % length] for t in range(length)]


def _synthetic_panel(companies: int = 3, length: int = 36) -> dict:
    """Minimal hist_v1-shaped panel covering the frozen analysis window."""
    quarters = B.quarter_labels("1976-Q1", "2026-Q2")
    first = quarters.index(B.WINDOW_START)
    final = quarters.index(B.WINDOW_END)
    pattern = _pattern(seed=7, length=length)
    panel_companies = []
    pairs = []
    for index in range(companies):
        key = f"company_{index}"
        counts = [max(1, int(round(abs(value) * 10))) for value in pattern]
        panel_companies.append({"key": key, "display_name": key, "cohort": "roster",
                                "total_material_events": sum(counts),
                                "first_event_qidx": first, "last_event_qidx": final})
        pairs.append({
            "company_key": key,
            "track_id": f"track_{index}",
            "event_qidx": [first + position for position in range(length)],
            "event_counts": counts,
            "n_510k": sum(counts),
            "n_pma": 0,
        })
    return {
        "schema": "hist_v1.panel.v1",
        "quarters": quarters,
        "companies": panel_companies,
        "tracks": [],
        "pairs": pairs,
        "pairs_no_acquired": pairs,
    }


class GridTests(unittest.TestCase):
    def test_window_is_36_quarters(self) -> None:
        self.assertEqual(len(B.WINDOW), 36)
        self.assertEqual(B.WINDOW[0], "2017-Q1")
        self.assertEqual(B.WINDOW[-1], "2025-Q4")
        self.assertEqual(B.WINDOW[8], "2019-Q1")

    def test_quarter_boundaries(self) -> None:
        self.assertEqual(B.quarter_end("2017-Q1"), date(2017, 3, 31))
        self.assertEqual(B.quarter_end("2025-Q4"), date(2025, 12, 31))
        self.assertEqual(B.previous_quarter_end("2017-Q1"), date(2016, 12, 31))
        self.assertEqual(B.previous_quarter_end("2024-Q3"), date(2024, 6, 30))

    def test_publication_knowledge_rule(self) -> None:
        # A complete year y is usable only from 15 February of y+1.
        self.assertEqual(B.latest_known_publication_year(date(2017, 2, 14)), 2015)
        self.assertEqual(B.latest_known_publication_year(date(2017, 2, 15)), 2016)
        self.assertEqual(B.latest_known_publication_year(date(2017, 3, 31)), 2016)
        self.assertEqual(B.latest_known_publication_year(date(2018, 1, 31)), 2016)
        self.assertEqual(B.latest_known_publication_year(date(2018, 2, 15)), 2017)


class ZScoreAndCorrelationTests(unittest.TestCase):
    def test_zscore_hand_checked(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0]
        expected_sd = math.sqrt(5.0 / 3.0)
        expected = [(value - 2.5) / expected_sd for value in values]
        observed = B.zscore(values)
        self.assertIsNotNone(observed)
        for got, want in zip(observed, expected):
            self.assertAlmostEqual(got, want, places=12)

    def test_zscore_preserves_missing_and_rejects_constant(self) -> None:
        self.assertEqual(B.zscore([1.0, None, 2.0]), [None, None, None])  # <3 observed
        self.assertEqual(B.zscore([5.0] * 6), [None] * 6)                 # constant
        zipped = B.zscore([1.0, None, 2.0, 3.0, 4.0])
        self.assertIsNone(zipped[1])
        self.assertEqual(sum(value is None for value in zipped), 1)

    def test_zscore_is_company_level_and_scale_invariant(self) -> None:
        # The protocol's stated purpose: company level/scale must not drive r.
        base = [1.0, 2.0, 4.0, 8.0, 16.0]
        scaled = [1000.0 * value + 500.0 for value in base]
        for got, want in zip(B.zscore(scaled), B.zscore(base)):
            self.assertAlmostEqual(got, want, places=12)

    def test_correlation_hand_checked(self) -> None:
        self.assertAlmostEqual(B.correlation([1, 2, 3], [2, 4, 6]), 1.0, places=12)
        self.assertAlmostEqual(B.correlation([1, 2, 3], [6, 4, 2]), -1.0, places=12)
        self.assertIsNone(B.correlation([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]))
        self.assertIsNone(B.correlation([1.0], [2.0]))

    def test_correlation_from_moments_matches_direct(self) -> None:
        rng = random.Random(11)
        xs = [rng.uniform(-2, 2) for _ in range(40)]
        ys = [rng.uniform(-2, 2) for _ in range(40)]
        direct = B.correlation(xs, ys)
        moments = (len(xs), math.fsum(xs), math.fsum(ys),
                   math.fsum(x * x for x in xs), math.fsum(y * y for y in ys),
                   math.fsum(x * y for x, y in zip(xs, ys)))
        self.assertAlmostEqual(direct, B.correlation_from_moments(*moments), places=12)

    def test_percentile_linear_interpolation(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertAlmostEqual(B.percentile(values, 0.0), 1.0)
        self.assertAlmostEqual(B.percentile(values, 1.0), 5.0)
        self.assertAlmostEqual(B.percentile(values, 0.5), 3.0)
        self.assertAlmostEqual(B.percentile(values, 0.25), 2.0)


class LagAlignmentTests(unittest.TestCase):
    """The ``k*`` sign convention and the synthetic leading series."""

    def test_profile_from_blocks_matches_direct_pooled_correlation(self) -> None:
        rng = random.Random(2026)
        source = [rng.uniform(-2, 2) for _ in range(36)]
        event = [rng.uniform(-2, 2) for _ in range(36)]
        zsource = B.zscore(source)
        zevent = B.zscore(event)
        blocks = B.blocks_for_company(zsource, zevent, B.LAGS, 36)
        profile = B.profile_from_blocks([blocks], B.LAGS)
        for lag in (-3, 0, 4):
            xs, ys = [], []
            for t in range(max(0, lag), min(36, 36 + lag)):
                i = t - lag
                if zsource[i] is not None and zevent[t] is not None:
                    xs.append(zsource[i])
                    ys.append(zevent[t])
            self.assertAlmostEqual(profile[lag], B.correlation(xs, ys), places=12)

    def test_leading_series_recovers_positive_k_star(self) -> None:
        # Source at t equals the milestone at t+2 => the source precedes events by
        # 2 quarters, so the frozen statistic must select k* = +2.
        pattern = _pattern(seed=99, length=36)
        companies = [f"c{index}" for index in range(8)]
        event_series = {company: list(pattern) for company in companies}
        source_series = {
            company: [value * (index + 1) + index for value in _shift(pattern, 2)]
            for index, company in enumerate(companies)}
        record = B.analyse_source(
            source_id="financial_rd", label="synthetic lead",
            raw_series=source_series, event_series=event_series,
            universe=companies, bootstrap_reps=50, permutation_reps=50)
        self.assertTrue(record["evaluable"])
        self.assertEqual(record["primary"]["k_star"], 2)
        self.assertGreater(record["primary"]["r_k_star"], 0.999)
        self.assertGreater(record["primary"]["abs_r_k_star"], 0.999)
        self.assertGreater(record["primary"]["k_star"], 0)

    def test_lagging_series_peaks_at_negative_k(self) -> None:
        # Source at t equals the milestone at t-3 => lag -3 has the peak.
        pattern = _pattern(seed=101, length=36)
        companies = [f"c{index}" for index in range(4)]
        event_series = {company: list(pattern) for company in companies}
        source_series = {company: _shift(pattern, -3) for company in companies}
        zsource = {company: B.zscore(values) for company, values in source_series.items()}
        zevent = {company: B.zscore(values) for company, values in event_series.items()}
        blocks = [B.blocks_for_company(zsource[company], zevent[company], B.LAGS, 36)
                  for company in companies]
        profile = B.profile_from_blocks(blocks, B.LAGS)
        best_lag = max(B.LAGS, key=lambda lag: abs(profile[lag] or 0.0))
        self.assertEqual(best_lag, -3)
        self.assertGreater(profile[-3], 0.999)

    def test_lead_choice_restricted_to_positive_lags(self) -> None:
        profile = {lag: 0.0 for lag in B.LAGS}
        profile[-8] = 0.9   # strongest overall, but not a lead window candidate
        profile[5] = 0.3
        profile[2] = -0.4
        k_star, magnitude = B.lead_choice(profile)
        self.assertEqual(k_star, 2)
        self.assertAlmostEqual(magnitude, 0.4)


class RotationAndBootstrapTests(unittest.TestCase):
    def test_rotate_circular(self) -> None:
        self.assertEqual(B.rotate_circular([1, 2, 3, 4], 1), [4, 1, 2, 3])
        self.assertEqual(B.rotate_circular([1, 2, 3, 4], 0), [1, 2, 3, 4])
        self.assertEqual(B.rotate_circular([1, 2, 3, 4], 4), [1, 2, 3, 4])
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        rotated = B.rotate_circular(values, 2)
        self.assertEqual(sorted(rotated), sorted(values))  # marginals preserved

    def test_rotation_null_is_deterministic(self) -> None:
        rng = random.Random(31)
        companies = [f"c{index}" for index in range(6)]
        zsource = {company: B.zscore([rng.uniform(-2, 2) for _ in range(36)])
                   for company in companies}
        zevent = {company: B.zscore([rng.uniform(-2, 2) for _ in range(36)])
                  for company in companies}
        first = B.permutation_null(companies, zsource, zevent, reps=40,
                                   rng=random.Random(B.SEED), observed_max=0.05,
                                   length=36)
        second = B.permutation_null(companies, zsource, zevent, reps=40,
                                    rng=random.Random(B.SEED), observed_max=0.05,
                                    length=36)
        self.assertEqual(first, second)
        self.assertEqual(first["reps_valid"], 40)
        self.assertIsNotNone(first["p_value"])
        self.assertTrue(0.0 <= first["p_value"] <= 1.0)
        self.assertGreaterEqual(first["n_null_ge_observed"], 0)

    def test_rotation_null_with_different_seed_differs(self) -> None:
        rng = random.Random(33)
        companies = [f"c{index}" for index in range(4)]
        zsource = {company: B.zscore([rng.uniform(-2, 2) for _ in range(36)])
                   for company in companies}
        zevent = {company: B.zscore([rng.uniform(-2, 2) for _ in range(36)])
                  for company in companies}
        first = B.permutation_null(companies, zsource, zevent, reps=30,
                                   rng=random.Random(1), observed_max=0.05, length=36)
        second = B.permutation_null(companies, zsource, zevent, reps=30,
                                    rng=random.Random(2), observed_max=0.05, length=36)
        # A different seed draws a different rotation sequence; the continuous
        # median of the null maxima is an exact tie only with probability ~0.
        self.assertNotEqual(first["null_max_median"], second["null_max_median"])

    def test_bootstrap_is_deterministic(self) -> None:
        rng = random.Random(41)
        companies = [f"c{index}" for index in range(5)]
        blocks = {}
        for company in companies:
            zsource = B.zscore([rng.uniform(-2, 2) for _ in range(36)])
            zevent = B.zscore([rng.uniform(-2, 2) for _ in range(36)])
            blocks[company] = B.blocks_for_company(zsource, zevent, B.LAGS, 36)
        first = B.bootstrap_profile(companies, blocks, B.LAGS, 60, random.Random(B.SEED))
        second = B.bootstrap_profile(companies, blocks, B.LAGS, 60, random.Random(B.SEED))
        self.assertEqual(first, second)
        self.assertIsNotNone(first["max_lead_sd"])
        self.assertEqual(first["reps_with_max_lead"], 60)
        self.assertIsNotNone(first["intervals"][0]["ci_low"])

    def test_era_correlation_restricted_range(self) -> None:
        rng = random.Random(51)
        companies = ["c0"]
        zsource = {"c0": B.zscore([rng.uniform(-2, 2) for _ in range(36)])}
        zevent = {"c0": B.zscore([rng.uniform(-2, 2) for _ in range(36)])}
        value, pairs = B.era_correlation(companies, zsource, zevent, lag=1,
                                         first_index=20, last_index=35, length=36)
        xs, ys = [], []
        for t in range(20, 36):
            if zsource["c0"][t - 1] is not None and zevent["c0"][t] is not None:
                xs.append(zsource["c0"][t - 1])
                ys.append(zevent["c0"][t])
        self.assertEqual(pairs, len(xs))
        self.assertAlmostEqual(value, B.correlation(xs, ys), places=12)


class InferenceTests(unittest.TestCase):
    def test_holm_hand_checked(self) -> None:
        adjusted = B.holm_adjust({"a": 0.01, "b": 0.04, "c": 0.03})
        self.assertAlmostEqual(adjusted["a"], 0.03)
        self.assertAlmostEqual(adjusted["c"], 0.06)
        self.assertAlmostEqual(adjusted["b"], 0.06)

    def test_holm_monotone_and_capped(self) -> None:
        adjusted = B.holm_adjust({"a": 0.9, "b": 0.95, "c": 0.99})
        self.assertTrue(all(value <= 1.0 for value in adjusted.values()))
        values = [adjusted[key] for key in ("a", "b", "c")]
        self.assertEqual(values, sorted(values))

    def test_mde_formula(self) -> None:
        expected = (1.959963984540054 + 0.8416212335729143) * 0.05
        self.assertAlmostEqual(B.minimum_detectable_effect(0.05), expected, places=12)
        self.assertIsNone(B.minimum_detectable_effect(None))


class CoverageAndExclusionTests(unittest.TestCase):
    def _series(self, length: int = 36, value: float = 1.0) -> list[float]:
        return [value + 0.1 * index for index in range(length)]

    def test_no_data_and_short_companies_excluded_and_counted(self) -> None:
        length = 36
        companies = ["full_a", "full_b", "short", "constant", "absent"]
        rng = random.Random(7)
        event_series = {
            company: [rng.uniform(0, 5) for _ in range(length)] for company in companies}
        raw_series = {
            "full_a": self._series(length),
            "full_b": [rng.uniform(-1, 1) for _ in range(length)],
            "short": [1.0, 2.0, 3.0, 4.0, 5.0] + [None] * (length - 5),
            "constant": [2.0] * length,
        }
        record = B.analyse_source(
            source_id="financial_rd", label="coverage fixture",
            raw_series=raw_series, event_series=event_series,
            universe=companies, bootstrap_reps=20, permutation_reps=20)
        coverage = record["coverage"]
        self.assertEqual(coverage["companies_included"], 2)
        self.assertEqual(coverage["companies_excluded"], 3)
        self.assertEqual(coverage["companies_excluded_no_source_data"], 1)
        reasons = {entry["company_key"]: entry["reason"]
                   for entry in coverage["exclusions"]}
        self.assertEqual(reasons["absent"], "no_source_data")
        self.assertEqual(reasons["short"], f"fewer_than_{B.MIN_QUARTERS}_quarters")
        self.assertEqual(reasons["constant"], "constant_source_series")
        self.assertEqual(coverage["included_companies"], ["full_a", "full_b"])
        self.assertEqual(coverage["panel_companies"], 5)
        self.assertEqual(coverage["companies_with_source_data"], 4)

    def test_empty_source_is_not_evaluable_with_measured_coverage(self) -> None:
        companies = ["a", "b"]
        event_series = {company: [1.0 + index for index in range(36)]
                        for company in companies}
        record = B.analyse_source(
            source_id="publication", label="empty fixture",
            raw_series={}, event_series=event_series, universe=companies,
            bootstrap_reps=10, permutation_reps=10)
        self.assertFalse(record["evaluable"])
        self.assertEqual(record["decision"]["label"], "NOT_EVALUABLE")
        self.assertEqual(record["coverage"]["companies_excluded_no_source_data"], 2)
        self.assertEqual(record["coverage"]["companies_included"], 0)
        self.assertIsNone(record["permutation"]["p_value"])


class SeriesBuilderTests(unittest.TestCase):
    def test_financial_series_knowledge_time_and_carry_forward(self) -> None:
        rows = [
            # annual (trailing-4-quarter) fact, filed 2024-02-16, FY2023 = 1000
            ("acme", "2023-01-01", "2023-12-31", 1000.0, "2024-02-16", "f1"),
            # a quarterly fact must be ignored (reported period ~90 days)
            ("acme", "2023-10-01", "2023-12-31", 250.0, "2024-02-16", "f2"),
            # duplicate FY2023 known earlier with another value: earliest knowledge wins
            ("acme", "2023-01-01", "2023-12-31", 999.0, "2024-02-20", "f3"),
        ]
        series, notes = B.financial_series(rows, ["2023-Q4", "2024-Q1", "2024-Q2"])
        self.assertIsNone(series["acme"][0])          # nothing known before 2024-02-16
        self.assertAlmostEqual(series["acme"][1], math.log(1000.0))
        self.assertAlmostEqual(series["acme"][2], math.log(1000.0))  # carried forward
        self.assertEqual(notes["duration_rejected_rows"], 1)
        self.assertEqual(notes["rows_read"], 3)

    def test_publication_series_uses_declared_knowledge_rule(self) -> None:
        rows = [("acme", 2016, 40), ("acme", 2017, 80)]
        window = ["2017-Q1", "2017-Q4", "2018-Q1", "2018-Q2"]
        series, _ = B.publication_series(rows, window)
        self.assertEqual(series["acme"], [10.0, 10.0, 20.0, 20.0])
        # A year without a persisted row is missing, never zero-filled.
        missing, _ = B.publication_series([("acme", 2016, 40)], ["2018-Q1"])
        self.assertEqual(missing["acme"], [None])

    def test_market_series_return_and_volatility(self) -> None:
        rows = [
            ("ACME", "2016-12-30", 100.0),
            ("ACME", "2017-01-03", 101.0),
            ("ACME", "2017-03-30", 110.0),
        ]
        returns, volatility, _ = B.market_series(rows, {"acme": "ACME"}, ["2017-Q1"])
        self.assertAlmostEqual(returns["acme"][0], 0.10, places=12)
        expected = [math.log(101.0 / 100.0), math.log(110.0 / 101.0)]
        self.assertAlmostEqual(volatility["acme"][0], B.sample_sd(expected), places=12)
        # No ticker => no rows => the company is simply absent from the source.
        empty_returns, _, _ = B.market_series(rows, {"other": "NOPE"}, ["2017-Q1"])
        self.assertEqual(empty_returns, {})

    def test_procurement_status_is_measured_not_proxied(self) -> None:
        status = B.procurement_status([(None, 0), (None, 0)])
        self.assertEqual(status["status"], "NOT_EVALUABLE")
        self.assertEqual(status["rows"], 2)
        self.assertFalse(status["proxy_substituted"])
        usable = B.procurement_status([("2024-01-02", 1)])
        self.assertEqual(usable["status"], "EVALUABLE")

    def test_panel_event_series_aggregates_pairs_by_company_quarter(self) -> None:
        panel = _synthetic_panel(companies=2)
        events = B.panel_event_series(panel, B.WINDOW)
        self.assertEqual(len(events), 2)
        for values in events.values():
            self.assertEqual(len(values), 36)
            self.assertGreater(sum(values), 0.0)


class EndToEndReportTests(unittest.TestCase):
    def test_payload_builds_and_report_is_generated_from_json_only(self) -> None:
        panel = _synthetic_panel(companies=3)
        raw = {
            "tickers": {},
            "rnd_rows": [],
            "market_rows": [],
            "publication_rows": [],
            "procurement_rows": [(None, 0)],
        }
        payload = B.build_payload(
            panel, raw,
            panel_path="synthetic-panel.json", panel_sha256="0" * 64,
            db_path="synthetic.sqlite", db_sha256="1" * 64,
            protocol_path=B.PROTOCOL_REL, protocol_sha256="2" * 64,
            bootstrap_reps=10, permutation_reps=10, seed=B.SEED)
        # The payload must be JSON round-trippable and the report must consume it.
        text = json.dumps(payload, sort_keys=True)
        reloaded = json.loads(text)
        report = B.report_markdown(reloaded)
        self.assertIn("# b103", report)
        self.assertIn("Decision summary", report)
        self.assertIn("NOT_EVALUABLE", report)
        self.assertEqual(report, B.report_markdown(reloaded))
        self.assertEqual(payload["schema"], "b103.leadlag.v1")
        self.assertEqual(payload["analysis_window"]["n_quarters"], 36)

    def test_no_numpy_pandas_scipy_imports_in_module(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        imports = re.findall(r"^\s*(?:import|from)\s+([A-Za-z_][\w.]*)", source,
                             flags=re.MULTILINE)
        top_level = {name.split(".")[0] for name in imports}
        for forbidden in ("numpy", "pandas", "scipy"):
            self.assertNotIn(forbidden, top_level)
            self.assertNotIn(f"import {forbidden}", source)
        self.assertNotIn("import numpy", source)
        self.assertNotIn("import pandas", source)
        self.assertNotIn("import scipy", source)


if __name__ == "__main__":
    unittest.main()
