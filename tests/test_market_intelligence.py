"""Offline tests for the Point-in-time market source and feature group.

The fixture writes a small SQLite database with the base repository's ``prices``
schema. It contains no real market data; every expected value is derived from
the deterministic synthetic series generated below.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from medradar.db import DB
from medradar.intelligence.features.market_features import (
    FEATURES,
    MISSING_KEY,
    attach_market_features,
    load_series,
    market_features,
)
from medradar.intelligence.sources import market_data
from medradar.intelligence.storage import IntelligenceStore

START = date(2020, 1, 1)
END = date(2023, 12, 31)
CUTOFF = "2023-06-30"
WINDOW_START = "2022-06-30"  # exactly CUTOFF - 365 days, a Thursday
TICKERS = ("SPY", "XBI", "AAA", "BBB", "JUMP", "SPLIT", "THIN")
TICKER_KEYS = {
    "acme": "AAA",
    "beta": "BBB",
    "jump": "JUMP",
    "split": "SPLIT",
    "thin": "THIN",
    "cash": "",
    "ghost": "GHOST",
}


def _business_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


DAYS = _business_days(START, END)
CUTOFF_INDEX = DAYS.index(date.fromisoformat(CUTOFF))
THIN_DAYS = DAYS[-40:-10]  # 30 bars that end before the cutoff


def _volume(index: int) -> int:
    return 1000 + (index * 37) % 211


def _series() -> dict[str, list[dict[str, object]]]:
    """Deterministic synthetic bars; no real prices, fully reproducible."""
    rows: dict[str, list[dict[str, object]]] = {ticker: [] for ticker in TICKERS}
    for index, day in enumerate(DAYS):
        stamp = day.isoformat()
        spy = 100.0 * 1.0004 ** index
        xbi = 100.0 + 0.01 * index
        aaa = 100.0 * 1.0009 ** index
        bbb = 100.0 * 0.9996 ** index
        split = 100.0 * 1.0005 ** index
        jump = 120.0 if index == CUTOFF_INDEX else (1000.0 if index > CUTOFF_INDEX else 100.0)
        rows["SPY"].append({"ticker": "SPY", "date": stamp, "adj_close": spy, "volume": _volume(index)})
        rows["XBI"].append({"ticker": "XBI", "date": stamp, "adj_close": xbi, "volume": _volume(index)})
        aaa_volume = 5000 + (index * 13) % 97 if index >= CUTOFF_INDEX - 59 else _volume(index)
        rows["AAA"].append({"ticker": "AAA", "date": stamp, "adj_close": aaa, "volume": aaa_volume})
        rows["BBB"].append({"ticker": "BBB", "date": stamp, "adj_close": bbb, "volume": _volume(index + 5)})
        # Raw close halves at day 500 (a 2:1 split proxy); adjusted close is smooth.
        raw_close = split if index < 500 else split / 2.0
        rows["SPLIT"].append({"ticker": "SPLIT", "date": stamp, "adj_close": split,
                              "close": raw_close, "volume": _volume(index)})
        rows["JUMP"].append({"ticker": "JUMP", "date": stamp, "adj_close": jump, "volume": 1000})
    for day in THIN_DAYS:
        rows["THIN"].append({"ticker": "THIN", "date": day.isoformat(),
                             "adj_close": 50.0, "volume": 1000})
    return rows


SERIES = _series()


def _write_prices_db(path: Path, series: dict[str, list[dict[str, object]]] | None = None) -> Path:
    rows = series or SERIES
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE prices (ticker TEXT NOT NULL, date TEXT NOT NULL, open REAL, high REAL,"
        " low REAL, close REAL, adj_close REAL, volume INTEGER, PRIMARY KEY (ticker, date))")
    payload = []
    for ticker, bars in rows.items():
        for bar in bars:
            payload.append((bar["ticker"], bar["date"], bar.get("open"), bar.get("high"),
                            bar.get("low"), bar.get("close", bar["adj_close"]),
                            bar["adj_close"], bar.get("volume")))
    conn.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?,?)", payload)
    conn.commit()
    conn.close()
    return path


def _companies() -> list[dict[str, object]]:
    return [{"key": key, "ticker": ticker} for key, ticker in TICKER_KEYS.items()]


def _collected(tmp: Path) -> tuple[IntelligenceStore, Path]:
    tmp.mkdir(parents=True, exist_ok=True)
    prices = _write_prices_db(tmp / "prices.sqlite")
    store = IntelligenceStore(DB(tmp / "intel.sqlite"))
    return store, prices


def _adj_close(rows: list[dict[str, object]], day: str) -> float:
    for row in rows:
        if row["date"] == day:
            return float(row["adj_close"])
    raise AssertionError(f"no fixture bar on {day}")


class CollectTests(unittest.TestCase):
    def test_collect_copies_mapped_tickers_and_benchmarks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, prices = _collected(Path(tmp))
            with store:
                result = market_data.collect(store, prices, _companies())
                self.assertEqual(result["tickers"], 6)  # six non-empty config tickers
                self.assertEqual(result["tickers_imported"], 5)  # GHOST is absent
                self.assertEqual(result["benchmarks"], 2)
                self.assertEqual(result["benchmarks_imported"], 2)
                self.assertEqual(result["missing_tickers"], ["GHOST"])
                self.assertEqual(result["unmapped_companies"], ["cash"])
                self.assertEqual(result["date_min"], DAYS[0].isoformat())
                self.assertEqual(result["date_max"], DAYS[-1].isoformat())
                expected = sum(len(bars) for ticker, bars in SERIES.items()
                               if ticker in {"AAA", "BBB", "JUMP", "SPLIT", "THIN", "SPY", "XBI"})
                self.assertEqual(result["rows"], expected)
                self.assertEqual(result["rows_in_table"], expected)
                tickers = {row[0] for row in store.conn.execute(
                    "SELECT DISTINCT ticker FROM market_bars")}
                self.assertIn("SPY", tickers)
                self.assertIn("XBI", tickers)
                self.assertIn("AAA", tickers)
                # Deterministic ordering: rows are stored ticker, then date.
                rows = [tuple(row) for row in store.conn.execute(
                    "SELECT ticker, date FROM market_bars").fetchall()]
                self.assertEqual(rows, sorted(rows))
                self.assertEqual(
                    [tuple(row) for row in store.conn.execute(
                        "SELECT source FROM market_bars GROUP BY source").fetchall()],
                    [("yahoo_finance_daily",)])

    def test_collect_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, prices = _collected(Path(tmp))
            with store:
                first = market_data.collect(store, prices, _companies())
                before = store.conn.execute(
                    "SELECT ticker, date, adj_close, volume FROM market_bars ORDER BY ticker, date").fetchall()
                second = market_data.collect(store, prices, _companies())
                after = store.conn.execute(
                    "SELECT ticker, date, adj_close, volume FROM market_bars ORDER BY ticker, date").fetchall()
                self.assertEqual(first["rows"], second["rows"])
                self.assertEqual(first["rows_in_table"], second["rows_in_table"])
                self.assertEqual(first["date_min"], second["date_min"])
                self.assertEqual(first["date_max"], second["date_max"])
                self.assertEqual(first["missing_tickers"], second["missing_tickers"])
                self.assertEqual(before, after)

    def test_source_database_is_never_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, prices = _collected(Path(tmp))
            digest = prices.stat().st_size, prices.read_bytes()
            with store:
                market_data.collect(store, prices, _companies())
            self.assertEqual((prices.stat().st_size, prices.read_bytes()), digest)
            conn = market_data.open_prices_db_readonly(prices)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute("INSERT INTO prices VALUES ('X', '2020-01-01', 1, 1, 1, 1, 1, 1)")
            finally:
                conn.close()
            with self.assertRaises(FileNotFoundError):
                market_data.open_prices_db_readonly(Path(tmp) / "missing.sqlite")

    def test_collect_rejects_database_without_prices_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.sqlite"
            conn = sqlite3.connect(empty)
            conn.execute("CREATE TABLE other (x INTEGER)")
            conn.commit()
            conn.close()
            store = IntelligenceStore(DB(Path(tmp) / "intel.sqlite"))
            with store:
                with self.assertRaises(ValueError):
                    market_data.collect(store, empty, _companies())

    def test_ticker_override_and_allow_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, prices = _collected(Path(tmp))
            with store:
                override = market_data.collect(
                    store, prices, _companies(), tickers={"acme": "AAA"})
                self.assertEqual(override["tickers"], 1)
                self.assertEqual(override["rows_in_table"], len(SERIES["AAA"]) + len(SERIES["SPY"]) + len(SERIES["XBI"]))
                allow = market_data.collect(
                    store, prices, [{"key": "acme", "ticker": "AAA"}, {"key": "beta", "ticker": "BBB"}],
                    benchmarks=(), tickers=["BBB"])
                self.assertEqual(allow["tickers"], 1)
                self.assertEqual(allow["benchmarks"], 0)
                self.assertEqual(allow["rows"], len(SERIES["BBB"]))
            self.assertEqual(market_data.company_ticker_map({"acme": "AAA"}), {"acme": "AAA"})
            self.assertEqual(market_data.company_ticker_map([{"key": "acme", "ticker": "AAA"}]),
                             {"acme": "AAA"})


class FeatureTests(unittest.TestCase):
    def _features(self, tmp: Path, company: str, cutoff: str = CUTOFF) -> dict:
        store, prices = _collected(tmp)
        with store:
            market_data.collect(store, prices, _companies())
            return market_features(store, company, cutoff, None)

    def test_feature_group_is_complete_and_typed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            features = self._features(Path(tmp), "AAA")
            self.assertEqual(set(features), set(FEATURES) | {MISSING_KEY})
            self.assertEqual(features[MISSING_KEY], 0)
            for name in FEATURES:
                self.assertIsNotNone(features[name], name)
            for name in ("mkt_ret_12m", "mkt_vol_12m", "mkt_max_drawdown_12m",
                         "mkt_rel_spy_12m", "mkt_rel_xbi_12m", "mkt_volume_z_3m"):
                self.assertIsInstance(features[name], float)
            self.assertIn(features["mkt_regime_spy_above_200d"], (0, 1))
            self.assertEqual(features["mkt_days_since_12m_high"], float(int(features["mkt_days_since_12m_high"])))

    def test_exactly_at_cutoff_bar_is_included(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with_cutoff = self._features(Path(tmp), "JUMP", "2023-06-30")
            self.assertAlmostEqual(with_cutoff["mkt_ret_12m"], 0.2, places=6)
            with tempfile.TemporaryDirectory() as tmp:
                before = self._features(Path(tmp), "JUMP", "2023-06-29")
                self.assertAlmostEqual(before["mkt_ret_12m"], 0.0, places=6)

    def test_future_bars_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, prices = _collected(Path(tmp))
            with store:
                market_data.collect(store, prices, _companies())
                first = market_features(store, "AAA", CUTOFF, None)
                # Inject an extreme future bar: it must not change any feature.
                store.conn.execute(
                    "INSERT OR REPLACE INTO market_bars(ticker, date, adj_close, volume, source, retrieved_at)"
                    " VALUES ('AAA', '2023-07-05', 1000000.0, 999999, 'test', '2026-01-01')")
                store.conn.commit()
                second = market_features(store, "AAA", CUTOFF, None)
                self.assertEqual(first, second)
                # And the 12m return is exactly the base-to-cutoff ratio.
                self.assertAlmostEqual(
                    first["mkt_ret_12m"],
                    _adj_close(SERIES["AAA"], CUTOFF) / _adj_close(SERIES["AAA"], WINDOW_START) - 1.0,
                    places=12)

    def test_insufficient_history_sets_missing_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            features = self._features(Path(tmp) / "thin", "THIN")
            self.assertEqual(features[MISSING_KEY], 1)
            for name in FEATURES:
                self.assertIsNone(features[name], name)
            unknown = self._features(Path(tmp) / "ghost", "GHOST")
            self.assertEqual(unknown[MISSING_KEY], 1)
            self.assertTrue(all(unknown[name] is None for name in FEATURES))

    def test_benchmark_relative_signs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            strong = self._features(Path(tmp) / "strong", "AAA")
            weak = self._features(Path(tmp) / "weak", "BBB")
            spy_return = _adj_close(SERIES["SPY"], CUTOFF) / _adj_close(SERIES["SPY"], WINDOW_START) - 1.0
            expected_relative = strong["mkt_ret_12m"] - spy_return
            self.assertAlmostEqual(strong["mkt_rel_spy_12m"], expected_relative, places=12)
            self.assertGreater(strong["mkt_rel_spy_12m"], 0.0)
            self.assertGreater(strong["mkt_rel_xbi_12m"], 0.0)
            self.assertLess(weak["mkt_rel_spy_12m"], 0.0)
            self.assertGreater(strong["mkt_ret_12m"], weak["mkt_ret_12m"])
            xbi_return = _adj_close(SERIES["XBI"], CUTOFF) / _adj_close(SERIES["XBI"], WINDOW_START) - 1.0
            self.assertAlmostEqual(weak["mkt_rel_xbi_12m"], weak["mkt_ret_12m"] - xbi_return, places=12)

    def test_drawdown_and_high_recency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rising = self._features(Path(tmp) / "rising", "AAA")
            falling = self._features(Path(tmp) / "falling", "BBB")
            self.assertLessEqual(rising["mkt_max_drawdown_12m"], 0.0)
            self.assertEqual(rising["mkt_days_since_12m_high"], 0.0)  # rising series: high is today
            self.assertLess(falling["mkt_max_drawdown_12m"], -0.05)
            self.assertGreater(falling["mkt_days_since_12m_high"], 200.0)

    def test_volume_z_uses_recent_against_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            features = self._features(Path(tmp), "AAA")
            self.assertGreater(features["mkt_volume_z_3m"], 5.0)

    def test_split_adjusted_close_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # The raw close halves at day 500; only adj_close is split-safe.
            features = self._features(Path(tmp), "SPLIT")
            self.assertGreater(features["mkt_ret_12m"], 0.10)
            self.assertLess(features["mkt_vol_12m"], 0.05)

    def test_regime_flag_tracks_spy_trend(self) -> None:
        flat_spy = [{"ticker": "SPY", "date": day.isoformat(), "adj_close": 100.0,
                     "volume": _volume(0)} for day in DAYS]
        flat_rows = {**SERIES, "SPY": flat_spy}
        with tempfile.TemporaryDirectory() as tmp:
            flat = self._features_from(Path(tmp), flat_rows, "AAA")
            self.assertEqual(flat["mkt_regime_spy_above_200d"], 0)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._features(Path(tmp), "AAA")["mkt_regime_spy_above_200d"], 1)

    def _features_from(self, tmp: Path, rows: dict, company: str) -> dict:
        prices = _write_prices_db(tmp / "prices.sqlite", rows)
        store = IntelligenceStore(DB(tmp / "intel.sqlite"))
        with store:
            market_data.collect(store, prices, _companies())
            return market_features(store, company, CUTOFF, None)

    def test_missing_benchmarks_are_flagged_not_fabricated(self) -> None:
        rows = {ticker: bars for ticker, bars in SERIES.items() if ticker not in ("SPY", "XBI")}
        with tempfile.TemporaryDirectory() as tmp:
            features = self._features_from(Path(tmp), rows, "AAA")
            self.assertIsNotNone(features["mkt_ret_12m"])
            self.assertIsNone(features["mkt_rel_spy_12m"])
            self.assertIsNone(features["mkt_rel_xbi_12m"])
            self.assertIsNone(features["mkt_regime_spy_above_200d"])
            self.assertEqual(features[MISSING_KEY], 1)

    def test_features_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, prices = _collected(Path(tmp))
            with store:
                market_data.collect(store, prices, _companies())
                first = market_features(store, "AAA", CUTOFF, None)
                second = market_features(store, "AAA", CUTOFF, None)
                self.assertEqual(first, second)
                self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_load_series_requires_adjusted_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, prices = _collected(Path(tmp))
            with store:
                market_data.collect(store, prices, _companies())
                series = load_series(store, "AAA")
                self.assertIsNotNone(series)
                self.assertEqual(len(series["dates"]), len(SERIES["AAA"]))
                self.assertEqual(series["dates"], sorted(series["dates"]))
                self.assertIsNone(load_series(store, "GHOST"))


class AttachTests(unittest.TestCase):
    def test_attach_adds_market_keys_and_keeps_base_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, prices = _collected(Path(tmp))
            with store:
                market_data.collect(store, prices, _companies())
                examples = [
                    {"company_key": "acme", "cutoff": CUTOFF,
                     "features": {"rd_count_12m": 3.0, "fin_rd_intensity": None}},
                    {"company_key": "ghost", "cutoff": CUTOFF,
                     "features": {"rd_count_12m": 1.0}},
                    {"company_key": "cash", "cutoff": CUTOFF,
                     "features": {"rd_count_12m": 0.0}},
                ]
                summary = attach_market_features(store, examples, _companies())
                first, second, third = examples
                self.assertEqual(first["features"]["rd_count_12m"], 3.0)
                self.assertEqual(first["features"]["fin_rd_intensity"], None)
                self.assertEqual(first["features"][MISSING_KEY], 0)
                self.assertIsNotNone(first["features"]["mkt_ret_12m"])
                self.assertEqual(second["features"]["rd_count_12m"], 1.0)
                self.assertEqual(second["features"][MISSING_KEY], 1)
                self.assertTrue(all(second["features"][name] is None for name in FEATURES))
                self.assertEqual(third["features"]["rd_count_12m"], 0.0)
                self.assertEqual(third["features"][MISSING_KEY], 1)
                self.assertEqual(summary["examples"], 3)
                self.assertEqual(summary["with_market_data"], 1)
                self.assertEqual(summary["missing"], 2)
                self.assertEqual(summary["no_ticker"], 1)
                self.assertEqual(summary["non_null_by_feature"]["mkt_ret_12m"], 1)
                # Deterministic: attaching again changes nothing.
                before = json.dumps(first["features"], sort_keys=True)
                attach_market_features(store, examples, _companies())
                self.assertEqual(json.dumps(first["features"], sort_keys=True), before)

    def test_attach_without_market_data_is_null_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = IntelligenceStore(DB(Path(tmp) / "intel.sqlite"))
            with store:
                examples = [{"company_key": "acme", "cutoff": CUTOFF,
                             "features": {"rd_count_12m": 2.0}}]
                summary = attach_market_features(store, examples, _companies())
                features = examples[0]["features"]
                self.assertEqual(features["rd_count_12m"], 2.0)
                self.assertEqual(features[MISSING_KEY], 1)
                self.assertTrue(all(features[name] is None for name in FEATURES))
                self.assertEqual(summary["with_market_data"], 0)


class AblationHelperTests(unittest.TestCase):
    @staticmethod
    def _script():
        import importlib.util

        path = Path(__file__).resolve().parents[1] / "scripts" / "run_market_ablation.py"
        spec = importlib.util.spec_from_file_location("run_market_ablation", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_delta_orientation(self) -> None:
        module = self._script()
        first = {"holdout_metrics": {"pr_auc": 0.5, "brier": 0.2, "ece": 0.1,
                                     "false_positive_rate": 0.3, "precision_at_k": 0.6}}
        second = {"holdout_metrics": {"pr_auc": 0.6, "brier": 0.1, "ece": 0.05,
                                      "false_positive_rate": 0.2, "precision_at_k": 0.7}}
        delta = module._delta(first, second)
        self.assertAlmostEqual(delta["pr_auc"], 0.1)
        self.assertAlmostEqual(delta["brier"], -0.1)
        self.assertAlmostEqual(delta["ece"], -0.05)
        self.assertIsNone(module._delta(first, {"holdout_metrics": {}})["pr_auc"])

    def test_v1_reproduction_block_reports_zero_delta_on_committed_values(self) -> None:
        module = self._script()
        committed = json.loads(
            (Path(__file__).resolve().parents[1] / "experiments" / "reverse_rd_v1" / "metrics.json")
            .read_text(encoding="utf-8"))
        models = {}
        for entry in committed["models"]:
            models[entry["name"]] = {"holdout_metrics": entry["holdout_metrics"]}
        reproduction = module._v1_reproduction(models)
        for name in ("rd_only", "rd_financial"):
            for metric, check in reproduction["checks"][name].items():
                self.assertIsNotNone(check["committed_v1"], metric)
                self.assertAlmostEqual(check["delta"], 0.0, places=12)


class GuardTests(unittest.TestCase):
    def test_feature_names_are_stable(self) -> None:
        self.assertEqual(len(FEATURES), 8)
        self.assertEqual(MISSING_KEY, "mkt_missing")
        self.assertEqual(len(set(FEATURES)), len(FEATURES))
        self.assertTrue(all(name.startswith("mkt_") for name in FEATURES))

    def test_no_real_market_data_is_required_for_import(self) -> None:
        # The module must import without any database or network access.
        self.assertTrue(hasattr(market_data, "collect"))
        self.assertEqual(market_data.PRICE_SOURCE, "yahoo_finance_daily")


if __name__ == "__main__":
    unittest.main()
