"""Offline tests for the research statistics layer and the calibration harness.

Two rules for this file:

* **No network.** The calibration tests replay committed fixtures
  (``tests/fixtures/calibration``); the HTTP path is exercised with a mocked
  ``urlopen``.
* **Behaviour, not constants.** Where a number is asserted it is either derived
  by hand in the test or quoted from the published table in
  ``docs/CALIBRATION.md`` §2 - and then the fixture must reproduce it exactly,
  which is what makes the published calibration reproducible at all.

The statistical tests check the properties the report relies on: block bootstrap
brackets the point and widens under intra-day correlation, Holm adjusted p-values
are monotone and never worse than Bonferroni, a time split never shares an event
day between phases, and replay is idempotent.
"""

from __future__ import annotations

import json
import random
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from medradar import stats
from medradar.calibration import (
    HttpJudgeRecorder,
    ReplayJudge,
    ReplayMiss,
    call_judge,
    confusion_matrix,
    direction_confusion,
    evaluate,
    export_fixtures,
    filing_fingerprint,
    headline_for,
    high_materiality_prf,
    legacy_summary,
    metrics_sha1,
    read_labels,
    run_calibration,
)
from medradar.llm import JudgeConfig, parse_verdict
from medradar.util import read_json

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "calibration"
LABELS = ROOT / "docs" / "calibration" / "ground_truth.csv"
FILINGS = FIXTURES / "filings"


# ---------------------------------------------------------------- shared data
def _events(seed: int = 3, days: int = 12, per_day: int = 2) -> list[dict]:
    """Synthetic event-study rows with two correlated observations per day."""
    rng = random.Random(seed)
    rows = []
    for day in range(days):
        shock = rng.gauss(0.0, 0.02)
        for rep in range(per_day):
            rows.append(
                {
                    "event_id": f"e{day}-{rep}",
                    "event_date": f"2025-01-{day + 1:02d}",
                    "kind": "kind_a" if day % 2 == 0 else "kind_b",
                    "ticker": "AAA" if day % 2 == 0 else "BBB",
                    "ar": {
                        "1": shock + rng.gauss(0.01, 0.02),
                        "5": shock + rng.gauss(0.02, 0.04),
                        "20": shock + rng.gauss(0.00, 0.08),
                        "60": None,
                    },
                }
            )
    return rows


def _block_correlated(seed: int, n_blocks: int = 24, per_block: int = 5):
    """Zero-mean data with a shared within-block shock (true mean is exactly 0)."""
    rng = random.Random(seed)
    values: list[float] = []
    blocks: list[int] = []
    for block in range(n_blocks):
        shock = rng.gauss(0.0, 0.03)
        for _ in range(per_block):
            values.append(shock + rng.gauss(0.0, 0.01))
            blocks.append(block)
    return values, blocks


def _write_labels(path: Path, ids: list[str]) -> None:
    path.write_text(
        "id,company,filed,gt_type,gt_direction,gt_materiality,gt_note\n"
        + "".join(
            f"{identifier},Company {identifier},2025-01-01,approval,1,0.6,note\n"
            for identifier in ids
        ),
        encoding="utf-8",
    )


_PUBLISHED_CACHE: dict[str, dict] = {}


def _published_run(suite: str) -> dict:
    """Run the committed fixture through the harness once per test process."""
    if suite not in _PUBLISHED_CACHE:
        out = Path(tempfile.mkdtemp(prefix=f"medradar-cal-{suite}-"))
        judge = ReplayJudge.from_fixtures(FIXTURES, suite=suite)
        result = run_calibration(FILINGS, LABELS, judge, out)
        result["_out"] = str(out)
        _PUBLISHED_CACHE[suite] = result
    return _PUBLISHED_CACHE[suite]


def tearDownModule() -> None:  # pragma: no cover - cleanup
    for result in _PUBLISHED_CACHE.values():
        shutil.rmtree(result.get("_out", ""), ignore_errors=True)


# ------------------------------------------------------------------ statistics
class BasicStatsTests(unittest.TestCase):
    def test_mean_median_stdev_ignore_missing_and_non_numeric(self) -> None:
        values = [1.0, 2.0, None, 3.0, "x", 4.0]
        self.assertAlmostEqual(stats.mean(values), 2.5)
        self.assertAlmostEqual(stats.median([4.0, 1.0, 3.0, 2.0]), 2.5)
        self.assertAlmostEqual(stats.median([3.0]), 3.0)
        self.assertIsNone(stats.mean([]))
        self.assertAlmostEqual(stats.stdev([2.0, 4.0]), 2.0 ** 0.5)  # sample sd, ddof=1

    def test_t_stat_known_value_and_degenerate_inputs(self) -> None:
        # mean 3, deviations [-2,0,0,0,2] -> sample var 8/4 = 2, t = 3/(sqrt(2)/sqrt(5))
        values = [1.0, 3.0, 3.0, 3.0, 5.0]
        self.assertAlmostEqual(stats.t_stat(values), 3.0 * (5 / 2) ** 0.5, places=9)
        self.assertIsNone(stats.t_stat([1.0]))
        self.assertIsNone(stats.t_stat([2.0, 2.0, 2.0]))  # no variance -> None, never inf

    def test_ranks_use_midranks_for_ties(self) -> None:
        self.assertEqual(stats.ranks([10, 20, 20, 30]), [1.0, 2.5, 2.5, 4.0])

    def test_pearson_spearman_and_mae(self) -> None:
        self.assertAlmostEqual(stats.pearson([1, 2, 3], [2, 4, 6]), 1.0, places=9)
        self.assertAlmostEqual(stats.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0, places=9)
        # monotone but non-linear: Spearman 1, Pearson < 1
        self.assertAlmostEqual(stats.spearman([1, 2, 3, 4], [1, 4, 9, 16]), 1.0, places=9)
        self.assertLess(stats.pearson([1, 2, 3, 4], [1, 4, 9, 16]), 1.0)
        self.assertAlmostEqual(stats.mae([0.2, 0.4], [0.3, 0.1]), 0.2)
        self.assertIsNone(stats.pearson([1.0], [1.0]))
        self.assertIsNone(stats.pearson([1.0, 1.0], [2.0, 3.0]))  # zero variance

    def test_normal_and_t_quantiles(self) -> None:
        self.assertAlmostEqual(stats.normal_ppf(0.975), 1.959964, places=5)
        self.assertAlmostEqual(stats.normal_ppf(0.5), 0.0, places=9)
        self.assertAlmostEqual(stats.normal_cdf(0.0), 0.5, places=12)
        # classic table value: t_{0.025, 10} = 2.228 -> two-sided p = 0.05
        self.assertAlmostEqual(stats.t_p_value(2.228, 10), 0.05, places=4)
        self.assertAlmostEqual(stats.t_p_value(0.0, 10), 1.0, places=12)
        self.assertIsNone(stats.t_p_value(1.0, 0))
        self.assertIsNone(stats.normal_ppf(0.0))


class BlockBootstrapTests(unittest.TestCase):
    def test_brackets_the_point_and_is_deterministic(self) -> None:
        values = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06]
        blocks = ["d1", "d1", "d2", "d2", "d3", "d3"]
        first = stats.block_bootstrap_ci(values, blocks, n_boot=400, seed=11)
        second = stats.block_bootstrap_ci(values, blocks, n_boot=400, seed=11)
        self.assertEqual(first, second)
        self.assertAlmostEqual(first["point"], 0.035)
        self.assertLessEqual(first["lo"], first["point"])
        self.assertGreaterEqual(first["hi"], first["point"])
        self.assertEqual(first["n_blocks"], 3)
        self.assertEqual(first["method"], "block_bootstrap")

    def test_no_interval_when_fewer_than_two_blocks(self) -> None:
        result = stats.block_bootstrap_ci([0.01, 0.02, 0.03], ["d1", "d1", "d1"])
        self.assertIsNone(result["lo"])
        self.assertIsNone(result["hi"])
        self.assertIn("note_zh", result)

    def test_rejects_misaligned_blocks_and_weights(self) -> None:
        with self.assertRaises(ValueError):
            stats.block_bootstrap_ci([1.0, 2.0], ["a"])
        with self.assertRaises(ValueError):
            stats.block_bootstrap_ci([1.0, 2.0], ["a", "b"], weights=[1.0])

    def test_iid_mode_and_weighted_mode(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0]
        iid = stats.block_bootstrap_ci(values, None, n_boot=200, seed=3)
        self.assertEqual(iid["method"], "iid_bootstrap")
        self.assertEqual(iid["n_blocks"], 4)
        weighted = stats.block_bootstrap_ci(
            values, ["a", "b", "c", "d"], weights=[1.0, 1.0, 2.0, 2.0], n_boot=200, seed=3
        )
        self.assertAlmostEqual(weighted["point"], (1 + 2 + 6 + 8) / 6.0)
        self.assertTrue(weighted["weighted"])

    def test_block_interval_is_wider_under_intra_block_correlation(self) -> None:
        widths_block = []
        widths_iid = []
        for seed in range(12):
            values, blocks = _block_correlated(seed)
            block_ci = stats.block_bootstrap_ci(values, blocks, n_boot=250, seed=seed)
            iid_ci = stats.block_bootstrap_ci(values, None, n_boot=250, seed=seed)
            widths_block.append(block_ci["hi"] - block_ci["lo"])
            widths_iid.append(iid_ci["hi"] - iid_ci["lo"])
        mean_block = sum(widths_block) / len(widths_block)
        mean_iid = sum(widths_iid) / len(widths_iid)
        # within-day shocks are ~3x the idiosyncratic noise, so ignoring the block
        # structure understates the interval by a visible margin
        self.assertGreater(mean_block, 1.3 * mean_iid)

    def test_coverage_of_the_truth_is_close_to_nominal(self) -> None:
        """True mean is 0 by construction; a 90% interval should cover it ~90% of runs."""
        covered = 0
        replications = 24
        for seed in range(replications):
            values, blocks = _block_correlated(seed + 100)
            ci = stats.block_bootstrap_ci(
                values, blocks, n_boot=250, alpha=0.10, seed=seed
            )
            if ci["lo"] <= 0.0 <= ci["hi"]:
                covered += 1
        coverage = covered / replications
        self.assertGreaterEqual(coverage, 0.70, f"coverage {coverage:.2f} too low")
        self.assertLessEqual(coverage, 1.0)


class MultipleTestingTests(unittest.TestCase):
    def test_bonferroni_scales_by_number_of_tests(self) -> None:
        result = stats.bonferroni([0.01, 0.04, 0.03], alpha=0.05)
        self.assertEqual(result["adjusted_p_values"], [0.03, 0.12, 0.09])
        self.assertEqual(result["rejected"], 1)
        self.assertEqual(result["m"], 3)

    def test_holm_matches_worked_example(self) -> None:
        # sorted p = 0.01, 0.03, 0.04 with m=3:
        # 3*0.01=0.03, 2*0.03=0.06, 1*0.04=0.04 -> running max 0.03, 0.06, 0.06
        result = stats.holm([0.01, 0.04, 0.03], alpha=0.05)
        self.assertEqual(result["adjusted_p_values"], [0.03, 0.06, 0.06])
        self.assertEqual(result["rejected"], 1)

    def test_adjusted_table_shape_is_report_ready(self) -> None:
        """``adjusted`` is what the report renders: dicts sorted by adjusted p."""
        result = stats.holm([0.20, 0.01, 0.04], alpha=0.05)
        self.assertTrue(all(isinstance(item, dict) for item in result["adjusted"]))
        first = result["adjusted"][0]
        for key in ("key", "raw_p", "adjusted_p", "significant"):
            self.assertIn(key, first)
        self.assertEqual(first["key"], "test_1")
        self.assertAlmostEqual(first["raw_p"], 0.01)
        self.assertTrue(first["significant"])
        self.assertEqual(result["n_significant"], result["rejected"])
        self.assertEqual(result["n_rejected"], result["rejected"])
        self.assertEqual(result["significant"], result["rejected"])
        for left, right in zip(result["adjusted"], result["adjusted"][1:]):
            self.assertLessEqual(left["adjusted_p"], right["adjusted_p"])

    def test_holm_is_monotone_and_never_worse_than_bonferroni(self) -> None:
        rng = random.Random(5)
        for _ in range(40):
            p_values = [rng.random() for _ in range(rng.randint(2, 12))]
            holm = stats.holm(p_values, alpha=0.05)
            bonferroni = stats.bonferroni(p_values, alpha=0.05)
            ordered_holm = [test["adjusted_p"] for test in holm["ordered"]]
            for left, right in zip(ordered_holm, ordered_holm[1:]):
                self.assertLessEqual(left, right + 1e-15)
            for raw, adjusted in zip(holm["tests"], holm["adjusted_p_values"]):
                self.assertGreaterEqual(adjusted + 1e-15, raw["p"])
                self.assertLessEqual(adjusted, 1.0)
            for holm_p, bonf_p in zip(holm["adjusted_p_values"], bonferroni["adjusted_p_values"]):
                self.assertLessEqual(holm_p + 1e-15, bonf_p + 1e-15)
            if bonferroni["rejected"]:
                self.assertGreaterEqual(holm["rejected"], bonferroni["rejected"])

    def test_dispatcher_and_empty_input(self) -> None:
        self.assertEqual(stats.multiple_testing([0.2], method="bonferroni")["method"], "bonferroni")
        self.assertEqual(stats.multiple_testing([0.2], method="holm")["method"], "holm")
        with self.assertRaises(ValueError):
            stats.multiple_testing([0.2], method="magic")
        empty = stats.holm([])
        self.assertEqual(empty["m"], 0)
        self.assertEqual(empty["rejected"], 0)

    def test_labels_are_carried_through(self) -> None:
        result = stats.holm([0.001, 0.5], labels=["a@1", "b@5"])
        by_label = {test["label"]: test for test in result["tests"]}
        self.assertTrue(by_label["a@1"]["reject"])
        self.assertFalse(by_label["b@5"]["reject"])


class AggregateEventStudyTests(unittest.TestCase):
    def test_hand_computed_aggregates(self) -> None:
        events = [
            {"event_date": "2025-01-01", "kind": "a", "ar": {"1": 0.10, "5": 0.02}},
            {"event_date": "2025-01-01", "kind": "a", "ar": {"1": -0.02, "5": 0.02}},
            {"event_date": "2025-01-02", "kind": "b", "ar": {"1": 0.04, "5": -0.02}},
            {"event_date": "2025-01-02", "kind": "b", "ar": {"1": 0.00, "5": -0.02}},
            {"event_date": "2025-01-03", "kind": "b", "ar": {"1": 0.08, "5": 0.02}},
        ]
        result = stats.aggregate_event_study(events, horizons=(1, 5), n_boot=300, seed=1)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["n_events"], 5)
        self.assertEqual(result["n_blocks"], 3)
        horizon_1 = result["all"]["1"]
        self.assertAlmostEqual(horizon_1["mean"], (0.10 - 0.02 + 0.04 + 0.00 + 0.08) / 5)
        self.assertAlmostEqual(horizon_1["median"], 0.04)
        self.assertAlmostEqual(horizon_1["hit_rate"], 3 / 5)
        self.assertEqual(horizon_1["n_blocks"], 3)
        self.assertLessEqual(horizon_1["ci95"]["lo"], horizon_1["mean"])
        self.assertGreaterEqual(horizon_1["ci95"]["hi"], horizon_1["mean"])
        self.assertIn("a", result["by_kind"])
        self.assertEqual(result["by_kind"]["a"]["1"]["n"], 2)
        self.assertEqual(result["by_kind"]["a"]["5"]["n"], 2)

    def test_missing_horizon_is_not_zero(self) -> None:
        events = _events()
        result = stats.aggregate_event_study(events, horizons=(1, 60), n_boot=200, seed=1)
        self.assertEqual(result["all"]["60"]["n"], 0)
        self.assertIsNone(result["all"]["60"]["mean"])
        self.assertEqual(result["all"]["1"]["n"], len(events))

    def test_multiple_testing_covers_kind_times_horizon(self) -> None:
        result = stats.aggregate_event_study(_events(), n_boot=200, seed=1)
        self.assertEqual(result["multiple_testing"]["method"], "holm")
        self.assertGreaterEqual(result["multiple_testing"]["m"], 4)
        self.assertIn("multiple_testing_method", result["meta"])

    def test_weighted_mean_and_absent_t_statistic(self) -> None:
        events = [
            {"event_date": "2025-01-01", "kind": "a", "weight": 1.0, "ar": {"1": 1.0}},
            {"event_date": "2025-01-02", "kind": "a", "weight": 1.0, "ar": {"1": 2.0}},
            {"event_date": "2025-01-03", "kind": "a", "weight": 2.0, "ar": {"1": 3.0}},
        ]
        result = stats.aggregate_event_study(events, horizons=(1,), n_boot=200, seed=1)
        self.assertEqual(result["weighting"], "weighted")
        self.assertAlmostEqual(result["all"]["1"]["mean"], (1 + 2 + 6) / 4.0)
        self.assertIsNone(result["all"]["1"]["t"])

    def test_accepts_abnormal_key_and_insufficient_data(self) -> None:
        events = [
            {"event_date": "2025-01-01", "kind": "a", "abnormal": {"1": 0.01}},
            {"event_date": "2025-01-02", "kind": "a", "abnormal": {"1": 0.02}},
            {"event_date": "2025-01-03", "kind": "a", "abnormal": {"1": 0.03}},
        ]
        result = stats.aggregate_event_study(events, horizons=(1,), n_boot=200, seed=1)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["all"]["1"]["n"], 3)
        too_small = stats.aggregate_event_study(events[:1])
        self.assertEqual(too_small["status"], "insufficient_data")
        self.assertEqual(too_small["reason"], "too_few_events")


class TimeSplitTests(unittest.TestCase):
    def test_fractional_split_is_disjoint_and_ordered(self) -> None:
        rows = [{"event_date": f"2025-{month:02d}-{day:02d}"} for month in range(1, 6) for day in range(1, 6)]
        result = stats.time_split(rows, return_items=True)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["no_overlap"])
        sizes = [len(result["items"][label]) for label in result["labels"]]
        self.assertEqual(sum(sizes), len(rows))
        self.assertEqual(sizes, [15, 5, 5])
        flattened = [item for label in result["labels"] for item in result["items"][label]]
        self.assertEqual(flattened, rows)  # already sorted
        dev_days = {item["event_date"] for item in result["items"]["dev"]}
        holdout_days = {item["event_date"] for item in result["items"]["holdout"]}
        self.assertFalse(dev_days & holdout_days)
        self.assertLessEqual(
            result["bounds"]["dev"]["end"], result["bounds"]["validation"]["start"]
        )

    def test_a_day_is_never_shared_between_phases(self) -> None:
        rows = [
            {"event_date": f"2025-01-{day:02d}"}
            for day in range(1, 11)
            for _ in range(2)  # two events on every day
        ]
        result = stats.time_split(rows, return_items=True)
        self.assertTrue(result["no_overlap"])
        days_by_phase = {
            label: {item["event_date"] for item in result["items"][label]}
            for label in result["labels"]
        }
        self.assertFalse(days_by_phase["dev"] & days_by_phase["validation"])
        self.assertFalse(days_by_phase["dev"] & days_by_phase["holdout"])
        self.assertFalse(days_by_phase["validation"] & days_by_phase["holdout"])

    def test_explicit_cut_dates(self) -> None:
        rows = [{"event_date": day} for day in ("2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01")]
        result = stats.time_split_by_dates(rows, "2025-02-01", "2025-03-01", return_items=True)
        self.assertEqual([item["event_date"] for item in result["items"]["dev"]], ["2025-01-01", "2025-02-01"])
        self.assertEqual([item["event_date"] for item in result["items"]["validation"]], ["2025-03-01"])
        self.assertEqual([item["event_date"] for item in result["items"]["holdout"]], ["2025-04-01"])
        with self.assertRaises(ValueError):
            stats.time_split(rows, dev_end="2025-02-01")

    def test_small_and_degenerate_samples(self) -> None:
        self.assertEqual(stats.time_split([])["status"], "empty")
        small = stats.time_split([{"event_date": "2025-01-01"}], return_items=True)
        self.assertEqual(small["status"], "too_small")
        self.assertEqual(len(small["items"]["dev"]), 1)
        same_day = stats.time_split(
            [{"event_date": "2025-01-01"} for _ in range(30)]
        )
        self.assertEqual(same_day["status"], "degenerate")
        self.assertEqual(same_day["bounds"]["dev"]["n"], 30)
        self.assertNotIn("items", same_day)  # compact by default

    def test_default_payload_is_compact(self) -> None:
        rows = [{"event_date": f"2025-01-{day:02d}"} for day in range(1, 11)]
        payload = stats.time_split(rows)
        self.assertNotIn("items", payload)
        self.assertIn("bounds", payload)
        self.assertIn("sample_fractions", payload)


class WeightTests(unittest.TestCase):
    def test_equal_weights_sum_to_one(self) -> None:
        weights = stats.equal_weights(["a", "b", "c"])
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertEqual(weights["b"], 1 / 3)
        self.assertEqual(stats.equal_weights([]), {})

    def test_market_cap_weights_are_proportional_and_capped(self) -> None:
        weights = stats.market_cap_weights({"a": 100, "b": 50, "c": 50})
        self.assertAlmostEqual(weights["a"], 0.5)
        self.assertAlmostEqual(weights["b"], 0.25)
        capped = stats.market_cap_weights({"a": 100, "b": 5, "c": 5}, cap=0.40)
        self.assertAlmostEqual(sum(capped.values()), 1.0, places=9)
        for weight in capped.values():
            self.assertLessEqual(weight, 0.40 + 1e-12)
        self.assertAlmostEqual(capped["a"], 0.40)

    def test_infeasible_cap_and_missing_caps(self) -> None:
        uniform = stats.market_cap_weights({"a": 10, "b": 10, "c": 10}, cap=0.10)
        for weight in uniform.values():
            self.assertAlmostEqual(weight, 1 / 3)
        zeros = stats.market_cap_weights({"a": 0, "b": None})
        self.assertEqual(zeros, {"a": 0.0, "b": 0.0})
        self.assertEqual(stats.normalize_weights({"a": 1, "b": 1}), {"a": 0.5, "b": 0.5})

    def test_weighted_mean(self) -> None:
        self.assertAlmostEqual(stats.weighted_mean([1.0, 2.0, 3.0], {0: 1, 1: 1, 2: 2}), 2.25)
        self.assertIsNone(stats.weighted_mean([1.0], {0: 0}))
        self.assertIsNone(stats.weighted_mean([], {}))


class SurvivorshipAndPowerTests(unittest.TestCase):
    def test_survivorship_reasons(self) -> None:
        entities = [
            {"key": "ok", "ticker": "OK"},
            {"key": "no_price", "ticker": "GONE"},
            {"key": "no_ticker"},
            {"key": "delisted", "ticker": "DEAD"},
        ]
        result = stats.survivorship_flags(
            entities,
            price_tickers={"OK", "DEAD"},
            delisted={"DEAD"},
            listed_until={"DEAD": "2020-01-01"},
            window_end="2026-10-31",
        )
        self.assertEqual(result["total"], 4)
        self.assertEqual(result["flagged"], 3)  # numeric: this is what the report prints
        self.assertEqual(result["flagged_count"], 3)
        self.assertEqual(result["clean_count"], 1)
        reasons = {row["key"]: row["reasons"] for row in result["flagged_entities"]}
        self.assertEqual(reasons["no_price"], ["no_prices"])
        self.assertEqual(reasons["no_ticker"], ["no_ticker"])
        self.assertEqual(reasons["delisted"], ["delisted_before_window_end"])
        self.assertAlmostEqual(result["coverage"], 0.25)
        empty = stats.survivorship_flags([])
        self.assertEqual(empty["flagged_count"], 0)
        self.assertIsNone(empty["coverage"])

    def test_mde_and_required_n_move_in_the_right_direction(self) -> None:
        self.assertGreater(stats.mde(5, sd=0.1), stats.mde(50, sd=0.1))
        self.assertIsNone(stats.mde(1))
        required = stats.required_n(0.05, sd=0.1)
        self.assertEqual(required, 32)
        self.assertGreaterEqual(required, stats.required_n(0.10, sd=0.1))
        self.assertIsNone(stats.required_n(0.0))

    def test_power_hint_flags_underpowered_samples(self) -> None:
        hint = stats.power_hint(25, sd=0.1, observed_effect=0.05)
        self.assertTrue(hint["underpowered"])
        self.assertIn("功效不足", hint["verdict_zh"])
        strong = stats.power_hint(200, sd=0.1, observed_effect=0.05)
        self.assertFalse(strong["underpowered"])
        tiny = stats.power_hint(1)
        self.assertIn("样本量不足", tiny["verdict_zh"])


class ResearchBlockTests(unittest.TestCase):
    def test_block_shape_matches_schema(self) -> None:
        events = _events()
        block = stats.research_block(
            events,
            n_boot=200,
            price_tickers={"AAA"},
            universe=[{"key": "AAA", "ticker": "AAA"}, {"key": "BBB", "ticker": "BBB"}],
        )
        for key in ("sample_split", "multiple_testing", "survivorship", "event_study", "power"):
            self.assertIn(key, block)
        self.assertEqual(block["multiple_testing"]["method"], "holm")
        self.assertEqual(block["survivorship"]["flagged_count"], 1)
        self.assertEqual(block["event_study"]["status"], "ok")
        self.assertTrue(block["sample_split_rule"]["no_day_shared_between_phases"])
        self.assertEqual(block["meta"]["schema"], "SCHEMA.md §research")

    def test_empty_input_degrades_gracefully(self) -> None:
        block = stats.research_block([])
        self.assertEqual(block["event_study"]["status"], "insufficient_data")
        self.assertEqual(sorted(block["sample_split"]), ["dev", "holdout", "validation"])
        self.assertEqual(block["survivorship"]["total"], 0)
        self.assertEqual(block["multiple_testing"]["m"], 0)
        self.assertEqual(stats.time_split([])["bounds"]["dev"]["n"], 0)


# ----------------------------------------------------------------- calibration
class LabelAndFingerprintTests(unittest.TestCase):
    def test_read_labels_parses_types(self) -> None:
        rows = read_labels(LABELS)
        self.assertEqual(len(rows), 25)
        first = {row["id"]: row for row in rows}["cal-02"]
        self.assertEqual(first["company"], "Verona Pharma")
        self.assertEqual(first["gt_type"], "approval")
        self.assertEqual(first["gt_direction"], 1)
        self.assertAlmostEqual(first["gt_materiality"], 0.80)

    def test_direction_is_normalised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            path.write_text(
                "id,company,filed,gt_type,gt_direction,gt_materiality,gt_note\n"
                "a,A,2025-01-01,crl,-3,0.5,note\n",
                encoding="utf-8",
            )
            self.assertEqual(read_labels(path)[0]["gt_direction"], -1)

    def test_fingerprint_is_stable_and_headline_sensitive(self) -> None:
        text = "The company announced FDA approval."
        first = filing_fingerprint("Acme 8-K", text)
        self.assertEqual(first, filing_fingerprint("Acme 8-K", text))
        self.assertNotEqual(first, filing_fingerprint("Acme Corp 8-K", text))
        self.assertNotEqual(first, filing_fingerprint("Acme 8-K", text + " more"))
        self.assertEqual(headline_for("Acme"), "Acme 8-K")
        self.assertEqual(headline_for("", "{company} filing"), "Unknown filing")


class ReplayJudgeTests(unittest.TestCase):
    def test_replay_is_idempotent_and_matches_archived_verdict(self) -> None:
        judge = ReplayJudge.from_fixtures(FIXTURES, suite="llm")
        headline = headline_for("Verona Pharma")
        text = (FILINGS / "cal-02.txt").read_text(encoding="utf-8")
        first_raw, first_verdict = judge.judge_with_raw(headline, text)
        second_raw, second_verdict = judge.judge_with_raw(headline, text)
        self.assertEqual(first_raw, second_raw)
        self.assertEqual(first_verdict, second_verdict)
        self.assertEqual(first_verdict["catalyst_type"], "approval")
        self.assertAlmostEqual(first_verdict["materiality"], 0.90)
        self.assertEqual(judge.calls, 2)
        self.assertEqual(judge.misses, 0)

    def test_lookup_is_order_independent(self) -> None:
        forward = ReplayJudge.from_fixtures(FIXTURES, suite="llm")
        backward = ReplayJudge.from_fixtures(FIXTURES, suite="llm")
        ids = ["cal-02", "cal-15", "cal-41"]
        texts = {identifier: (FILINGS / f"{identifier}.txt").read_text(encoding="utf-8") for identifier in ids}
        heads = {
            "cal-02": headline_for("Verona Pharma"),
            "cal-15": headline_for("Abeona Therapeutics"),
            "cal-41": headline_for("Aerovate Therapeutics"),
        }
        for identifier in ids:
            forward.judge(heads[identifier], texts[identifier])
        for identifier in reversed(ids):
            self.assertEqual(
                backward.judge(heads[identifier], texts[identifier]),
                forward.judge(heads[identifier], texts[identifier]),
            )

    def test_missing_recording_raises_instead_of_fabricating(self) -> None:
        judge = ReplayJudge.from_fixtures(FIXTURES, suite="llm")
        with self.assertRaises(ReplayMiss):
            judge.judge("Unknown 8-K", "a filing that was never judged")
        self.assertEqual(judge.misses, 1)
        self.assertEqual(judge.calls, 0)

    def test_fixture_fingerprints_match_the_shipped_filings(self) -> None:
        """Guards against silently swapping a filing text under a recording."""
        for suite in ("llm", "heuristic"):
            payload = read_json(FIXTURES / suite / "responses.json")
            self.assertIsNotNone(payload)
            for entry in payload["responses"]:
                text = (FILINGS / f"{entry['id']}.txt").read_text(encoding="utf-8")
                self.assertEqual(
                    entry["fingerprint"], filing_fingerprint(entry["headline"], text)
                )
                self.assertEqual(len(entry["raw"]) > 0, True)
                self.assertTrue(entry["raw_source"])

    def test_manifest_records_provenance(self) -> None:
        manifest = read_json(FIXTURES / "manifest.json")
        self.assertIsNotNone(manifest)
        self.assertIn("suites", manifest)
        self.assertIn("note_zh", manifest)
        for suite in ("llm", "heuristic"):
            info = manifest["suites"][suite]
            self.assertTrue(info["recorded_at"])
            self.assertTrue(info["source"])
            self.assertEqual(info["raw_source"], "reconstructed_from_parsed_verdict")
            self.assertEqual(info["n"], 25)
        self.assertEqual(
            manifest["labels_csv"]["sha1"],
            __import__("hashlib").sha1(LABELS.read_text(encoding="utf-8-sig").encode()).hexdigest(),
        )


class PurityAndContractTests(unittest.TestCase):
    def test_confusion_matrix_counts_and_undefined_ratios(self) -> None:
        result = confusion_matrix(
            ["approval", "approval", "crl"], ["approval", "crl", "crl"], ["approval", "crl"]
        )
        self.assertEqual(result["matrix"], [[1, 1], [0, 1]])
        self.assertAlmostEqual(result["accuracy"], 2 / 3)
        self.assertAlmostEqual(result["by_label"]["approval"]["recall"], 0.5)
        self.assertAlmostEqual(result["by_label"]["approval"]["precision"], 1.0)
        missing = confusion_matrix(["approval"], ["approval"], ["approval", "crl"])
        self.assertIsNone(missing["by_label"]["crl"]["precision"])
        self.assertIsNone(missing["by_label"]["crl"]["recall"])
        self.assertIsNone(missing["by_label"]["crl"]["f1"])

    def test_direction_confusion(self) -> None:
        result = direction_confusion([1, -1, 0], [1, -1, 1])
        self.assertEqual(result["labels"], [-1, 0, 1])
        self.assertAlmostEqual(result["accuracy"], 2 / 3)
        self.assertEqual(result["matrix"][2][2], 1)  # +1 -> +1

    def test_high_materiality_prf(self) -> None:
        result = high_materiality_prf([0.9, 0.8, 0.1, 0.2], [0.85, 0.2, 0.1, 0.7])
        self.assertEqual((result["tp"], result["fp"], result["fn"], result["tn"]), (1, 1, 1, 1))
        self.assertAlmostEqual(result["precision"], 0.5)
        self.assertAlmostEqual(result["recall"], 0.5)
        self.assertAlmostEqual(result["f1"], 0.5)
        self.assertIsNone(high_materiality_prf([0.1], [0.1])["precision"])

    def test_evaluate_excludes_errors_from_denominators(self) -> None:
        records = [
            {
                "id": "a",
                "gt_type": "approval",
                "gt_direction": 1,
                "gt_materiality": 0.8,
                "verdict": {"direction": 1, "materiality": 0.9, "catalyst_type": "approval"},
            },
            {
                "id": "b",
                "gt_type": "crl",
                "gt_direction": -1,
                "gt_materiality": 0.6,
                "verdict": None,
                "error": "missing_filing",
            },
        ]
        metrics = evaluate(records)
        self.assertEqual(metrics["status"], "ok")
        self.assertEqual(metrics["n"], 1)
        self.assertEqual(metrics["n_errors"], 1)
        self.assertEqual(metrics["type"]["accuracy"], 1.0)
        empty = evaluate(records[1:])
        self.assertEqual(empty["status"], "insufficient_data")

    def test_legacy_summary_has_published_keys(self) -> None:
        metrics = _published_run("llm")["metrics"]
        summary = legacy_summary(metrics)
        for key in ("type_acc", "dir_acc", "dir_acc_sign", "spearman", "mae", "hi_p", "hi_r", "hi_f1"):
            self.assertIn(key, summary)

    def test_http_recorder_captures_the_raw_content(self) -> None:
        raw = json.dumps(
            {
                "direction": 1,
                "materiality": 0.7,
                "confidence": 0.9,
                "catalyst_type": "approval",
                "evidence_quotes": ["verbatim"],
            }
        )

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({"choices": [{"message": {"content": raw}}]}).encode()

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            recorder = HttpJudgeRecorder(JudgeConfig(api_key="k", model="m"))
            verdict, captured, source = call_judge(recorder, "h", "text")
        self.assertEqual(captured, raw)
        self.assertEqual(source, "http_chat_completions_content")
        self.assertEqual(verdict["catalyst_type"], "approval")

    def test_call_judge_falls_back_to_reserialised_verdict(self) -> None:
        class PlainJudge:
            def judge(self, headline, text):
                return {"direction": 1, "materiality": 0.5, "catalyst_type": "approval"}

        verdict, raw, source = call_judge(PlainJudge(), "h", "t")
        self.assertEqual(source, "verdict_json_reserialised")
        self.assertEqual(parse_verdict(raw)["catalyst_type"], "approval")
        self.assertEqual(verdict["direction"], 1)


class HarnessTests(unittest.TestCase):
    def test_replay_run_reproduces_the_published_table(self) -> None:
        llm = legacy_summary(_published_run("llm")["metrics"])
        heuristic = legacy_summary(_published_run("heuristic")["metrics"])
        expected_llm = (1.0, 0.92, 0.7997714534915624, 0.1464, 0.9375, 0.9375, 0.9375)
        self.assertAlmostEqual(llm["type_acc"], expected_llm[0], places=12)
        self.assertAlmostEqual(llm["dir_acc"], expected_llm[1], places=12)
        self.assertAlmostEqual(llm["spearman"], expected_llm[2], places=12)
        self.assertAlmostEqual(llm["mae"], expected_llm[3], places=12)
        self.assertAlmostEqual(llm["hi_p"], expected_llm[4], places=12)
        self.assertAlmostEqual(llm["hi_r"], expected_llm[5], places=12)
        self.assertAlmostEqual(llm["hi_f1"], expected_llm[6], places=12)
        expected_heuristic = (0.6, 0.72, 0.5822613129549279, 0.184, 1.0, 0.5, 0.6666666666666666)
        self.assertAlmostEqual(heuristic["type_acc"], expected_heuristic[0], places=12)
        self.assertAlmostEqual(heuristic["dir_acc"], expected_heuristic[1], places=12)
        self.assertAlmostEqual(heuristic["spearman"], expected_heuristic[2], places=12)
        self.assertAlmostEqual(heuristic["mae"], expected_heuristic[3], places=12)
        self.assertAlmostEqual(heuristic["hi_p"], expected_heuristic[4], places=12)
        self.assertAlmostEqual(heuristic["hi_r"], expected_heuristic[5], places=12)
        self.assertAlmostEqual(heuristic["hi_f1"], expected_heuristic[6], places=12)

    def test_confusion_matrices_match_the_published_tables(self) -> None:
        llm = _published_run("llm")["metrics"]
        heuristic = _published_run("heuristic")["metrics"]
        self.assertEqual(
            llm["type"]["matrix"], [[6, 0, 0, 0], [0, 5, 0, 0], [0, 0, 9, 0], [0, 0, 0, 5]]
        )
        self.assertEqual(
            heuristic["type"]["matrix"], [[5, 1, 0, 0], [0, 5, 0, 0], [4, 0, 5, 0], [5, 0, 0, 0]]
        )
        self.assertEqual(llm["direction"]["matrix"], [[10, 0, 0], [0, 3, 2], [0, 0, 10]])
        self.assertEqual(heuristic["direction"]["matrix"], [[3, 5, 2], [0, 5, 0], [0, 0, 10]])
        self.assertAlmostEqual(llm["materiality"]["bias"], 0.1232, places=9)
        self.assertAlmostEqual(heuristic["materiality"]["bias"], -0.16, places=9)

    def test_two_runs_are_byte_identical_apart_from_timestamps(self) -> None:
        first = _published_run("llm")
        with tempfile.TemporaryDirectory() as tmp:
            judge = ReplayJudge.from_fixtures(FIXTURES, suite="llm")
            second = run_calibration(FILINGS, LABELS, judge, tmp)
            self.assertEqual(first["metrics_sha1"], second["metrics_sha1"])
            self.assertEqual(
                legacy_summary(first["metrics"]), legacy_summary(second["metrics"])
            )
            # only wall-clock fields may differ; the scored numbers are identical
            self.assertEqual(metrics_sha1(first["metrics"]), metrics_sha1(second["metrics"]))
            self.assertIn("generated_at", first["metrics"]["meta"])
            self.assertIn("total_elapsed_ms", first["metrics"]["meta"])

    def test_artefacts_are_written(self) -> None:
        result = _published_run("llm")
        out = Path(result["_out"])
        self.assertTrue((out / "metrics.json").exists())
        self.assertTrue((out / "manifest.json").exists())
        self.assertTrue((out / "verdicts.jsonl").exists())
        raw_files = sorted((out / "raw_responses").glob("*.txt"))
        self.assertEqual(len(raw_files), 25)
        raw_text = (out / "raw_responses" / "cal-02.txt").read_text(encoding="utf-8")
        self.assertEqual(parse_verdict(raw_text)["catalyst_type"], "approval")
        manifest = read_json(out / "manifest.json")
        self.assertEqual(manifest["n_records"], 25)
        self.assertEqual(manifest["judge"], "replay:llm")
        self.assertEqual(manifest["prompt_version"], "8k-v1")
        self.assertEqual(manifest["n_errors"], 0)
        lines = (out / "verdicts.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 25)
        record = json.loads(lines[0])
        for key in ("id", "headline", "verdict", "raw_response", "raw_source", "started_at", "elapsed_ms"):
            self.assertIn(key, record)
        self.assertGreaterEqual(record["elapsed_ms"], 0.0)

    def test_heuristic_fixture_matches_live_heuristic_judge(self) -> None:
        """The keyword baseline fixture must equal what the current code computes.

        If ``HeuristicJudge`` or the filing texts change, the recorded baseline
        would silently describe a judge that no longer exists. This test re-runs
        the live judge and compares the published metrics, not the raw strings.
        """
        from medradar.llm import HeuristicJudge

        with tempfile.TemporaryDirectory() as tmp:
            live = run_calibration(FILINGS, LABELS, HeuristicJudge(), tmp)
        recorded = _published_run("heuristic")
        live_summary = legacy_summary(live["metrics"])
        recorded_summary = legacy_summary(recorded["metrics"])
        for key in ("type_acc", "dir_acc", "spearman", "mae", "hi_p", "hi_r", "hi_f1"):
            self.assertAlmostEqual(
                live_summary[key], recorded_summary[key], places=12, msg=key
            )

    def test_missing_filing_is_reported_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            filings = Path(tmp) / "filings"
            filings.mkdir()
            shutil.copyfile(FILINGS / "cal-02.txt", filings / "cal-02.txt")
            real = {row["id"]: row for row in read_labels(LABELS)}["cal-02"]
            labels = Path(tmp) / "labels.csv"
            labels.write_text(
                "id,company,filed,gt_type,gt_direction,gt_materiality,gt_note\n"
                f"cal-02,{real['company']},{real['filed']},{real['gt_type']},1,"
                f"{real['gt_materiality']},note\n"
                "cal-99,Nowhere Inc,2025-01-01,approval,1,0.6,note\n",
                encoding="utf-8",
            )
            judge = ReplayJudge.from_fixtures(FIXTURES, suite="llm")
            result = run_calibration(filings, labels, judge, Path(tmp) / "out")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["n"], 1)
        self.assertEqual(result["n_errors"], 1)
        self.assertEqual(result["metrics"]["errors"][0]["id"], "cal-99")
        self.assertEqual(result["metrics"]["errors"][0]["error"], "missing_filing")

    def test_all_missing_filings_yield_insufficient_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            filings = Path(tmp) / "filings"
            filings.mkdir()
            labels = Path(tmp) / "labels.csv"
            _write_labels(labels, ["cal-99"])
            judge = ReplayJudge.from_fixtures(FIXTURES, suite="llm")
            result = run_calibration(filings, labels, judge, Path(tmp) / "out")
        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(result["n"], 0)

    def test_records_split_by_filing_date(self) -> None:
        """The protocol's calibration split is pure composition - no extra code."""
        out = Path(_published_run("llm")["_out"])
        records = [
            json.loads(line)
            for line in (out / "verdicts.jsonl").read_text(encoding="utf-8").strip().splitlines()
        ]
        self.assertEqual(len(records), 25)
        split = stats.time_split_by_dates(
            records,
            dev_end="2024-12-31",
            validation_end="2025-12-31",
            key="filed",
            return_items=True,
        )
        self.assertTrue(split["no_overlap"])
        counts = {label: len(split["items"][label]) for label in split["labels"]}
        self.assertEqual(counts, {"dev": 18, "validation": 5, "holdout": 2})
        self.assertEqual(sum(counts.values()), 25)
        self.assertEqual(split["bounds"]["holdout"]["start"], "2026-02-13")
        for label in split["labels"]:
            phase = evaluate(split["items"][label])
            self.assertEqual(phase["status"], "ok")

    def test_no_verdicts_are_hardcoded_in_the_harness(self) -> None:
        """The bug this module exists to kill: parsed verdict literals in source."""
        sources = [
            ROOT / "medradar" / "calibration.py",
            ROOT / "docs" / "calibration" / "score.py",
        ]
        for source in sources:
            text = source.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"cal-\d\d", text),
                f"{source.name} must not hardcode filing ids / verdicts",
            )
            self.assertNotIn("0.90, \"approval\"", text)

    def test_export_fixtures_roundtrip(self) -> None:
        """A freshly exported fixture must replay to the same verdicts."""
        with tempfile.TemporaryDirectory() as tmp:
            export_fixtures(
                FILINGS,
                LABELS,
                ROOT / "docs" / "calibration" / "llm_verdicts.json",
                Path(tmp),
                suite="llm",
                source_note="test roundtrip",
                recording_date="2026-10-31",
            )
            fresh = ReplayJudge.from_fixtures(Path(tmp), suite="llm")
            original = ReplayJudge.from_fixtures(FIXTURES, suite="llm")
            for identifier in ("cal-02", "cal-15", "cal-41"):
                company = {row["id"]: row["company"] for row in read_labels(LABELS)}[identifier]
                headline = headline_for(company)
                text = (FILINGS / f"{identifier}.txt").read_text(encoding="utf-8")
                self.assertEqual(
                    original.judge(headline, text), fresh.judge(headline, text)
                )
            manifest = read_json(Path(tmp) / "manifest.json")
            self.assertIn("test roundtrip", manifest["suites"]["llm"]["source"])


if __name__ == "__main__":
    unittest.main()
