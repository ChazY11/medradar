"""Offline unit tests for the quant layer (prices / event study / paper trading).

Everything here is synthetic and deterministic: **no test touches the network**.
The only on-disk fixture is a trimmed *real* Yahoo response
(``tests/fixtures/prices/yahoo_chart_MDT_1y_trimmed.json``) used to prove the
parser handles the actual payload shape (null bars, adjusted closes, epoch
timestamps) without needing a live request.
"""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from medradar.db import DB
from medradar.eventstudy import run_event_study
from medradar.paper import (
    COST_BPS,
    COST_FIXED,
    EQUITY_CSV_FIELDS,
    HOLD_DAYS,
    MAX_POSITION_PCT,
    MAX_TRACK_PCT,
    TRADE_CSV_FIELDS,
    run_paper,
)
from medradar.prices import (
    PriceSeries,
    adjusted_close,
    adjusted_open,
    fetch_prices,
    parse_chart,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "prices"


# --------------------------------------------------------------------------- helpers
def business_days(start: date, count: int) -> list[str]:
    days: list[str] = []
    cursor = start
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return days


def add_prices(db: DB, ticker: str, days: list[str], opens, closes, adj=None) -> None:
    rows = []
    for index, day in enumerate(days):
        open_price = float(opens[index])
        close_price = float(closes[index])
        rows.append(
            {
                "ticker": ticker,
                "date": day,
                "open": open_price,
                "high": max(open_price, close_price),
                "low": min(open_price, close_price),
                "close": close_price,
                "adj_close": float(adj[index]) if adj is not None else close_price,
                "volume": 1_000_000,
            }
        )
    db.upsert_prices(rows)


def add_signal(
    db: DB,
    signal_id: str,
    ticker: str,
    signal_date: str,
    kind: str = "device_new_track",
    direction: int = 1,
    track_id: str = "track_a",
    score: float = 0.8,
) -> None:
    db.upsert_signals(
        [
            {
                "signal_id": signal_id,
                "event_id": f"event-{signal_id}",
                "company_key": f"company-{ticker.lower()}",
                "ticker": ticker,
                "signal_date": signal_date,
                "kind": kind,
                "direction": direction,
                "score": score,
                "track_id": track_id,
                "reason_zh": "unit test",
            }
        ]
    )


def chart_payload(ticker: str, days: list[str], closes, opens=None, adj=None) -> dict:
    """Build a synthetic payload with the same shape as Yahoo's chart endpoint."""
    opens = opens if opens is not None else closes
    adj = adj if adj is not None else closes
    timestamps = [
        int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        for day in days
    ]
    return {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": ticker, "currency": "USD", "exchangeName": "NMS"},
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": [float(v) for v in opens],
                                "high": [float(v) for v in closes],
                                "low": [float(v) for v in closes],
                                "close": [float(v) for v in closes],
                                "volume": [1000000 for _ in closes],
                            }
                        ],
                        "adjclose": [{"adjclose": [float(v) for v in adj]}],
                    },
                }
            ],
            "error": None,
        }
    }


class FakeFetcher:
    """Minimal stand-in for :class:`medradar.http.Fetcher` (never hits network)."""

    def __init__(self, payloads: dict, fail_range: bool = False) -> None:
        self.payloads = payloads
        self.fail_range = fail_range
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "errors": 0}
        self.calls: list[tuple[str, dict]] = []

    def get_json(self, url, params=None, retries=3, backoff=2.0, refresh=False):
        params = dict(params or {})
        self.calls.append((url, params))
        if self.fail_range and "range" in params:
            self.stats["requests"] += 1
            raise RuntimeError("range endpoint rejected")
        ticker = url.rsplit("/", 1)[-1]
        payload = self.payloads.get(ticker)
        self.stats["requests"] += 1
        if payload is None:
            raise RuntimeError(f"no payload for {ticker}")
        return payload


class QuantTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._temp.name)
        self.db_path = self.tmp / "medradar.sqlite"
        self.db = DB(self.db_path)
        self.out_dir = self.tmp / "out"

    def tearDown(self) -> None:
        self.db.close()
        self._temp.cleanup()

    def read_trading(self) -> dict:
        return json.loads((self.out_dir / "trading.json").read_text(encoding="utf-8"))

    def csv_rows(self, name: str) -> list[dict]:
        with open(self.out_dir / name, "r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))


# --------------------------------------------------------------------------- prices
class PriceLayerTests(QuantTestCase):
    def test_parse_real_yahoo_fixture(self) -> None:
        payload = json.loads((FIXTURE_DIR / "yahoo_chart_MDT_1y_trimmed.json").read_text(encoding="utf-8"))
        rows = parse_chart(payload, "MDT")
        self.assertEqual(len(rows), 60)
        self.assertEqual(rows[0]["ticker"], "MDT")
        self.assertEqual(rows[0]["date"], "2025-10-30")
        self.assertLess(rows[0]["date"], rows[-1]["date"])
        for row in rows:
            self.assertIsNotNone(row["close"])
            self.assertGreater(row["close"], 0)
            self.assertIsNotNone(row["adj_close"])
            self.assertIn("open", row)
            self.assertIsInstance(row["volume"], int)
        # adjusted open must be rescaled onto the adjusted-close basis
        first = rows[0]
        expected = first["open"] * first["adj_close"] / first["close"]
        self.assertAlmostEqual(adjusted_open(first), expected, places=10)
        self.assertAlmostEqual(adjusted_close(first), first["adj_close"], places=10)

    def test_parse_error_payload_raises(self) -> None:
        payload = json.loads((FIXTURE_DIR / "yahoo_chart_error.json").read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            parse_chart(payload, "NOPE")
        with self.assertRaises(ValueError):
            parse_chart({"chart": {"result": [], "error": None}}, "NOPE")

    def test_price_series_adjusted_math(self) -> None:
        series = PriceSeries(
            [
                {
                    "ticker": "X",
                    "date": "2024-01-02",
                    "open": 100.0,
                    "close": 110.0,
                    "adj_close": 55.0,
                },
                {
                    "ticker": "X",
                    "date": "2024-01-03",
                    "open": 120.0,
                    "close": 120.0,
                    "adj_close": 60.0,
                },
            ]
        )
        self.assertAlmostEqual(series.open("2024-01-02"), 50.0, places=10)
        self.assertAlmostEqual(series.close("2024-01-02"), 55.0, places=10)
        self.assertAlmostEqual(series.open("2024-01-03"), 60.0, places=10)
        self.assertIsNone(series.open("2024-01-01"))
        self.assertEqual(series.last_close_on_or_before("2024-01-02"), (55.0, "2024-01-02"))
        self.assertEqual(series.last_close_on_or_before("2024-01-04"), (60.0, "2024-01-03"))
        self.assertEqual(series.last_close_on_or_before("2024-01-01"), (None, None))

    def test_fetch_prices_isolates_failures(self) -> None:
        days = business_days(date(2024, 1, 1), 8)
        payloads = {
            "SPY": chart_payload("SPY", days, [100.0] * len(days)),
            "AAA": chart_payload("AAA", days, [50.0] * len(days)),
            # XBI intentionally missing -> must be reported as failed, not fatal
        }
        fetcher = FakeFetcher(payloads)
        stats = fetch_prices(self.db, fetcher, ["AAA"], min_request_gap=0.0)
        self.assertEqual(stats["ok"], ["SPY", "AAA"])
        self.assertEqual([item["ticker"] for item in stats["failed"]], ["XBI"])
        self.assertEqual(stats["rows"], 16)
        self.assertGreater(stats["requests"], 0)
        self.assertEqual(len(self.db.prices_for("AAA")), len(days))
        self.assertEqual(len(self.db.prices_for("SPY")), len(days))

    def test_fetch_prices_period_fallback(self) -> None:
        days = business_days(date(2024, 1, 1), 8)
        fetcher = FakeFetcher({"AAA": chart_payload("AAA", days, [50.0] * len(days))}, fail_range=True)
        stats = fetch_prices(
            self.db, fetcher, ["AAA"], benchmarks=None, min_request_gap=0.0
        )
        self.assertEqual(stats["ok"], ["AAA"])
        self.assertTrue(any("period1" in params for _, params in fetcher.calls))
        self.assertTrue(any("range" in params for _, params in fetcher.calls))


# --------------------------------------------------------------------------- event study
class EventStudyTests(QuantTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.days = business_days(date(2024, 1, 1), 130)
        count = len(self.days)
        add_prices(self.db, "SPY", self.days, [100.0] * count, [100.0] * count)
        for ticker, growth in (("AAA", 1.01), ("BBB", 1.02), ("CCC", 1.03)):
            closes = [100.0 * growth**index for index in range(count)]
            add_prices(self.db, ticker, self.days, closes, closes)
        opens = [100.0 * 1.01**index for index in range(count)]
        closes = [price * 1.001 for price in opens]  # intraday drift -> entry must use the open
        add_prices(self.db, "DDD", self.days, opens, closes)

    def _seed_signals(self) -> None:
        add_signal(self.db, "s1", "AAA", self.days[0], kind="k_long")
        add_signal(self.db, "s2", "BBB", self.days[0], kind="k_long")
        add_signal(self.db, "s3", "CCC", self.days[0], kind="k_long")
        add_signal(self.db, "s4", "AAA", self.days[0], kind="k_short", direction=-1)
        add_signal(self.db, "s5", "BBB", self.days[4], kind="k_long_friday")  # Friday -> Monday open
        add_signal(self.db, "s6", "DDD", self.days[0], kind="k_open")

    def test_ar_is_exact_and_curve_matches_horizons(self) -> None:
        self._seed_signals()
        study = run_event_study(self.db)
        self.assertEqual(study["status"], "ok")
        self.assertEqual(study["n_signals"], 6)
        self.assertEqual(study["n_events"], 6)
        self.assertEqual(study["horizons"], [1, 5, 20, 60])

        for horizon in (1, 5, 20, 60):
            expected = [
                1.01**horizon - 1.0,
                1.02**horizon - 1.0,
                1.03**horizon - 1.0,
                -(1.01**horizon - 1.0),  # short direction flips the AR
                1.02**horizon - 1.0,  # Friday signal, Monday entry
                1.001 * 1.01**horizon - 1.0,  # open entry to close exit
            ]
            stats = study["all"][str(horizon)]
            self.assertEqual(stats["n"], 6)
            self.assertAlmostEqual(stats["mean"], sum(expected) / len(expected), places=10)
            ordered = sorted(expected)
            self.assertAlmostEqual(stats["median"], (ordered[2] + ordered[3]) / 2.0, places=10)
            # the short candidate loses in a rising market: 5 of the 6 signals "hit"
            self.assertAlmostEqual(stats["hit_rate"], 5.0 / 6.0, places=12)
            self.assertIsNotNone(stats["t"])
            self.assertIsNotNone(stats["ci95"])
            self.assertEqual(stats["ci95"]["n"], 6)

        long_only = study["by_kind"]["k_long"]
        self.assertEqual(long_only["20"]["n"], 3)
        self.assertAlmostEqual(
            long_only["20"]["mean"],
            (1.01**20 - 1 + 1.02**20 - 1 + 1.03**20 - 1) / 3,
            places=10,
        )
        self.assertAlmostEqual(
            study["by_kind"]["k_short"]["20"]["mean"], -(1.01**20 - 1.0), places=10
        )

        # Entry-relative curve: curve day h equals the h-day mean AR exactly.
        entry_curve = study["curve"]
        self.assertEqual(entry_curve["origin"], "entry_day")
        self.assertEqual(entry_curve["days"], list(range(-5, 61)))
        for horizon in (1, 5, 20, 60):
            point = entry_curve["all"][horizon + 5]
            self.assertAlmostEqual(point, study["all"][str(horizon)]["mean"], places=10)

        # Signal-relative curve: entry session sits at t=1, so horizon h is t=h+1.
        # (t only runs to +60, so the 60-day horizon itself is just off the curve.)
        signal_curve = study["curve_signal_relative"]
        self.assertEqual(signal_curve["days"], list(range(-5, 61)))
        for horizon in (1, 5, 20):
            point = signal_curve["all"][horizon + 1 + 5]
            self.assertAlmostEqual(point, study["all"][str(horizon)]["mean"], places=10)

    def test_signal_day_close_is_not_used_as_entry(self) -> None:
        """A signal-day-close entry would produce g^(h+1)-1; we must see g^h-1."""
        self._seed_signals()
        study = run_event_study(self.db)
        stats = study["by_kind"]["k_long"]["5"]
        self.assertAlmostEqual(stats["mean"], (1.01**5 - 1 + 1.02**5 - 1 + 1.03**5 - 1) / 3, places=10)
        self.assertNotAlmostEqual(stats["mean"], (1.01**6 - 1 + 1.02**6 - 1 + 1.03**6 - 1) / 3, places=6)

    def test_ingest_signals_bridges_metrics_to_db(self) -> None:
        """analyze.py puts signals in metrics.json; the trading stage reads SQLite."""
        from medradar.eventstudy import ingest_signals

        written = ingest_signals(
            self.db,
            [
                {
                    "signal_id": f"sig-{index}",
                    "event_id": f"event-{index}",
                    "company_key": f"company-{ticker.lower()}",
                    "ticker": ticker,
                    "signal_date": self.days[0],
                    "kind": "device_new_track",
                    "direction": 1,
                    "score": 0.5,
                    "track_id": f"track-{index}",
                    "reason_zh": "from metrics",
                }
                for index, ticker in enumerate(("AAA", "BBB", "CCC"))
            ],
        )
        self.assertEqual(written, 3)
        self.assertEqual(self.db.table_count("signals"), 3)
        # malformed rows are skipped instead of poisoning the table
        self.assertEqual(ingest_signals(self.db, [{"signal_id": "broken"}]), 0)
        study = run_event_study(self.db)
        self.assertEqual(study["status"], "ok")
        self.assertEqual(study["n_events"], 3)

    def test_insufficient_no_signals(self) -> None:
        study = run_event_study(self.db)
        self.assertEqual(study["status"], "insufficient_data")
        self.assertEqual(study["reason"], "no_signals")

    def test_insufficient_benchmark_missing(self) -> None:
        add_signal(self.db, "s1", "AAA", self.days[0])
        self.db.execute("DELETE FROM prices WHERE ticker = 'SPY'")
        self.db.commit()
        study = run_event_study(self.db)
        self.assertEqual(study["status"], "insufficient_data")
        self.assertEqual(study["reason"], "benchmark_missing")

    def test_insufficient_too_few_events(self) -> None:
        add_signal(self.db, "s1", "AAA", self.days[0])
        add_signal(self.db, "s2", "BBB", self.days[0])
        study = run_event_study(self.db)
        self.assertEqual(study["status"], "insufficient_data")
        self.assertEqual(study["reason"], "too_few_events")
        self.assertEqual(study["counts"]["usable"], 2)


# --------------------------------------------------------------------------- paper trading
class PaperTradingTests(QuantTestCase):
    def test_stop_loss_costs_and_drawdown_exact(self) -> None:
        days = business_days(date(2024, 1, 1), 12)
        add_prices(self.db, "SPY", days, [100.0] * len(days), [100.0] * len(days))
        opens = [100.0, 100.0, 90.0] + [79.0] * 9
        closes = [100.0, 100.0, 79.0] + [79.0] * 9
        add_prices(self.db, "T", days, opens, closes)
        add_signal(self.db, "s1", "T", days[0], kind="k", track_id="t1")

        result = run_paper(self.db_path, capital=100000.0, out_dir=self.out_dir)
        self.assertEqual(result["status"], "ok")
        payload = self.read_trading()

        # 5% of 100k = 5000 notional -> 50 shares at 100.
        entry_notional = MAX_POSITION_PCT * 100000.0
        shares = entry_notional / 100.0
        entry_cost = COST_FIXED + COST_BPS / 10000.0 * entry_notional
        exit_notional = shares * 79.0
        exit_cost = COST_FIXED + COST_BPS / 10000.0 * exit_notional
        expected_pnl = exit_notional - entry_notional - entry_cost - exit_cost
        expected_ret = expected_pnl / entry_notional
        expected_equity = 100000.0 + expected_pnl

        self.assertEqual(len(payload["trades"]), 1)
        trade = payload["trades"][0]
        self.assertEqual(trade["ticker"], "T")
        self.assertEqual(trade["entry_date"], days[1])
        self.assertEqual(trade["entry_price"], 100.0)
        self.assertEqual(trade["exit_date"], days[2])
        self.assertEqual(trade["exit_price"], 79.0)
        self.assertEqual(trade["reason"], "stop")
        self.assertAlmostEqual(trade["pnl"], expected_pnl, places=8)
        self.assertAlmostEqual(trade["ret"], expected_ret, places=12)
        self.assertAlmostEqual(expected_pnl, -1069.9, places=8)

        summary = payload["summary"]
        self.assertAlmostEqual(summary["final_equity"], expected_equity, places=8)
        self.assertAlmostEqual(summary["total_return"], expected_pnl / 100000.0, places=12)
        self.assertAlmostEqual(summary["avg_trade_return"], expected_ret, places=12)
        self.assertEqual(summary["win_rate"], 0.0)
        self.assertEqual(summary["n_trades"], 1)
        self.assertEqual(summary["trades"], 1)
        self.assertEqual(summary["benchmark"], "SPY")
        # entry cost drag on day 1, then the stop: max drawdown is the stop day
        self.assertAlmostEqual(summary["max_drawdown"], expected_equity / 100000.0 - 1.0, places=12)

        curve = payload["equity_curve"]
        self.assertEqual(curve[0], {"date": days[1], "equity": 100000.0 - entry_notional - entry_cost + entry_notional})
        self.assertEqual(curve[-1], {"date": days[2], "equity": expected_equity})
        self.assertEqual(summary["start"], days[1])
        self.assertEqual(summary["end"], days[2])

        rows = self.csv_rows("paper_trades.csv")
        self.assertEqual(set(rows[0].keys()), set(TRADE_CSV_FIELDS))
        self.assertAlmostEqual(float(rows[0]["costs"]), entry_cost + exit_cost, places=8)
        self.assertAlmostEqual(float(rows[0]["pnl"]), expected_pnl, places=8)
        self.assertEqual(int(rows[0]["holding_days"]), 1)
        equity_rows = self.csv_rows("paper_equity.csv")
        self.assertEqual(list(equity_rows[0].keys()), list(EQUITY_CSV_FIELDS))
        self.assertGreaterEqual(len(equity_rows), 2)
        self.assertEqual(self.db.table_count("paper_trades"), 1)
        self.assertGreater(self.db.table_count("paper_equity"), 0)

        meta = payload["meta"]
        for key in ("generated_at", "capital", "signal_kind", "engine", "disclaimer_zh"):
            self.assertIn(key, meta)
        self.assertIn("未建模做空借券费与并购逼平", payload["disclaimer_zh"])
        self.assertIn("非投资建议", payload["disclaimer_zh"])
        self.assertEqual(payload["status"], "ok")

    def test_time_exit_after_60_trading_days(self) -> None:
        days = business_days(date(2024, 1, 1), 80)
        count = len(days)
        add_prices(self.db, "SPY", days, [100.0] * count, [100.0] * count)
        growth = 1.01
        closes = [100.0 * growth**index for index in range(count)]
        add_prices(self.db, "G", days, closes, closes)
        add_signal(self.db, "s1", "G", days[0], kind="k", track_id="t1")

        run_paper(self.db_path, capital=100000.0, out_dir=self.out_dir)
        payload = self.read_trading()
        trade = payload["trades"][0]

        entry_price = 100.0 * growth
        entry_notional = MAX_POSITION_PCT * 100000.0
        shares = entry_notional / entry_price
        exit_notional = shares * 100.0 * growth**61
        entry_cost = COST_FIXED + COST_BPS / 10000.0 * entry_notional
        exit_cost = COST_FIXED + COST_BPS / 10000.0 * exit_notional
        expected_pnl = exit_notional - entry_notional - entry_cost - exit_cost

        self.assertEqual(trade["reason"], "time_exit")
        self.assertEqual(trade["entry_date"], days[1])
        self.assertEqual(trade["exit_date"], days[1 + HOLD_DAYS])
        self.assertAlmostEqual(trade["pnl"], expected_pnl, places=6)
        self.assertAlmostEqual(payload["summary"]["final_equity"], 100000.0 + expected_pnl, places=6)
        # only the entry cost causes a dip below the starting capital
        self.assertAlmostEqual(payload["summary"]["max_drawdown"], -entry_cost / 100000.0, places=12)
        self.assertIsNotNone(payload["summary"]["sharpe"])

    def test_position_and_track_caps(self) -> None:
        days = business_days(date(2024, 1, 1), 10)
        add_prices(self.db, "SPY", days, [100.0] * len(days), [100.0] * len(days))
        for index in range(1, 7):
            ticker = f"T{index}"
            add_prices(self.db, ticker, days, [100.0] * len(days), [100.0] * len(days))
            add_signal(self.db, f"s{index}", ticker, days[0], kind="k", track_id="same_track")

        run_paper(self.db_path, capital=100000.0, out_dir=self.out_dir)
        payload = self.read_trading()

        # five 5% positions saturate the 25% track budget; the sixth is rejected.
        self.assertEqual(payload["summary"]["n_trades"], 5)
        self.assertEqual(payload["meta"]["skipped"]["no_capacity"], 1)
        self.assertEqual(payload["attribution"][0]["trades"], 5)
        self.assertAlmostEqual(payload["by_kind"]["k"]["win_rate"], 0.0)
        self.assertAlmostEqual(payload["summary"]["final_equity"], 100000.0 - 5 * 22.0, places=8)
        self.assertLessEqual(abs(payload["by_kind"]["k"]["total_pnl"]), MAX_TRACK_PCT * 100000.0)

    def test_trading_json_contract(self) -> None:
        days = business_days(date(2024, 1, 1), 80)
        count = len(days)
        add_prices(self.db, "SPY", days, [100.0] * count, [100.0] * count)
        for ticker, growth in (("AAA", 1.01), ("BBB", 1.02), ("CCC", 1.03)):
            closes = [100.0 * growth**index for index in range(count)]
            add_prices(self.db, ticker, days, closes, closes)
            # signals mid-sample so the curve has pre-signal history (-5 needs 6 bars)
            add_signal(self.db, f"s-{ticker}", ticker, days[5], kind="k1", track_id=f"track-{ticker}")

        result = run_paper(self.db_path, capital=100000.0, out_dir=self.out_dir)
        self.assertEqual(result["status"], "ok")
        payload = self.read_trading()

        required = {
            "status",
            "as_of",
            "meta",
            "method",
            "summary",
            "equity_curve",
            "by_kind",
            "attribution",
            "event_study",
            "trades",
            "benchmark",
            "disclaimer_zh",
        }
        self.assertTrue(required.issubset(payload.keys()), required - set(payload.keys()))
        summary_keys = {
            "total_return",
            "final_equity",
            "max_drawdown",
            "win_rate",
            "avg_trade_return",
            "sharpe",
            "n_trades",
            "n_signals",
            "benchmark",
            "start",
            "end",
            "trades",
        }
        self.assertTrue(summary_keys.issubset(payload["summary"].keys()))
        self.assertEqual(payload["summary"]["n_trades"], payload["summary"]["trades"])
        self.assertLessEqual(payload["summary"]["max_drawdown"], 0.0)
        self.assertEqual(payload["meta"]["engine"], "long_only_v1")
        self.assertEqual(payload["benchmark"]["ticker"], "SPY")
        self.assertIn("signal_kind", payload["meta"])

        event_study = payload["event_study"]
        self.assertEqual(set(event_study.keys()), {"benchmark", "horizons", "curve"})
        self.assertEqual(event_study["benchmark"], "SPY")
        self.assertEqual(set(event_study["horizons"].keys()), {"1", "5", "20", "60"})
        for key, stats in event_study["horizons"].items():
            self.assertEqual(
                set(stats.keys()), {"n", "mean_ar", "median_ar", "t", "ci95", "hit_rate"}
            )
            self.assertEqual(stats["n"], 3)
            self.assertIsNotNone(stats["mean_ar"])
            self.assertIsNotNone(stats["median_ar"])
            self.assertIsNotNone(stats["hit_rate"])
        curve = event_study["curve"]
        self.assertGreater(len(curve), 0)
        self.assertTrue(all(set(point.keys()) == {"t", "ar"} for point in curve))
        self.assertTrue(all(isinstance(point["t"], int) for point in curve))
        self.assertLessEqual(curve[0]["t"], -5)

        # equity_curve: ascending, first/last present, exactly date+equity keys
        equity_curve = payload["equity_curve"]
        self.assertTrue(all(set(point.keys()) == {"date", "equity"} for point in equity_curve))
        dates = [point["date"] for point in equity_curve]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(equity_curve[0]["date"], payload["summary"]["start"])
        self.assertEqual(equity_curve[-1]["date"], payload["summary"]["end"])
        db_equity_rows = self.db.table_count("paper_equity")
        self.assertGreater(db_equity_rows, len(equity_curve))  # weekly sampling only in JSON
        self.assertAlmostEqual(equity_curve[-1]["equity"], payload["summary"]["final_equity"], places=8)

        for trade in payload["trades"]:
            self.assertEqual(
                set(trade.keys()),
                {
                    "ticker",
                    "entry_date",
                    "entry_price",
                    "exit_date",
                    "exit_price",
                    "ret",
                    "pnl",
                    "reason",
                },
            )
            self.assertIn(trade["reason"], {"time_exit", "stop", "end"})
        self.assertTrue(all(item["kind"] == "k1" for item in payload["attribution"]))

    def test_signal_kind_filter(self) -> None:
        days = business_days(date(2024, 1, 1), 80)
        count = len(days)
        add_prices(self.db, "SPY", days, [100.0] * count, [100.0] * count)
        closes = [100.0 * 1.01**index for index in range(count)]
        add_prices(self.db, "AAA", days, closes, closes)
        add_signal(self.db, "s1", "AAA", days[0], kind="k1", track_id="t1")
        add_signal(self.db, "s2", "AAA", days[0], kind="k2", track_id="t2")

        run_paper(self.db_path, capital=100000.0, out_dir=self.out_dir, signal_kind="k1")
        payload = self.read_trading()
        self.assertEqual(payload["meta"]["signal_kind"], ["k1"])
        self.assertEqual(payload["summary"]["n_signals"], 1)
        self.assertEqual(payload["attribution"][0]["kind"], "k1")

    def test_no_benchmark_still_simulates(self) -> None:
        days = business_days(date(2024, 1, 1), 70)
        closes = [100.0 * 1.01**index for index in range(len(days))]
        add_prices(self.db, "AAA", days, closes, closes)
        add_signal(self.db, "s1", "AAA", days[0], kind="k", track_id="t1")

        result = run_paper(self.db_path, capital=100000.0, out_dir=self.out_dir)
        self.assertEqual(result["status"], "ok")
        payload = self.read_trading()
        self.assertEqual(payload["event_study"]["horizons"], {})
        self.assertEqual(payload["event_study"]["curve"], [])
        self.assertIsNone(payload["benchmark"]["total_return"])
        self.assertEqual(len(payload["trades"]), 1)

    def test_short_only_signals_are_skipped(self) -> None:
        days = business_days(date(2024, 1, 1), 70)
        closes = [100.0] * len(days)
        add_prices(self.db, "AAA", days, closes, closes)
        add_signal(self.db, "s1", "AAA", days[0], kind="k", direction=-1)

        result = run_paper(self.db_path, capital=100000.0, out_dir=self.out_dir)
        self.assertEqual(result["status"], "insufficient_data")
        payload = self.read_trading()
        self.assertEqual(payload["status"], "insufficient_data")
        self.assertEqual(payload["meta"]["skipped"]["short_not_supported"], 1)
        self.assertEqual(payload["trades"], [])

    def test_insufficient_data_writes_trading_json(self) -> None:
        # 1) missing database
        missing = self.tmp / "does-not-exist.sqlite"
        result = run_paper(missing, capital=100000.0, out_dir=self.out_dir)
        self.assertEqual(result["status"], "insufficient_data")
        payload = self.read_trading()
        self.assertEqual(payload["status"], "insufficient_data")
        self.assertEqual(payload["summary"]["total_return"], None)
        self.assertEqual(payload["summary"]["n_trades"], None)
        self.assertEqual(payload["equity_curve"], [])
        self.assertEqual(payload["trades"], [])
        self.assertEqual(payload["reason"], "db_missing")
        self.assertFalse(missing.exists())  # must not invent a database file

        # 2) signals but no prices
        add_signal(self.db, "s1", "AAA", business_days(date(2024, 1, 1), 1)[0])
        result = run_paper(self.db_path, capital=100000.0, out_dir=self.out_dir)
        self.assertEqual(result["status"], "insufficient_data")
        payload = self.read_trading()
        self.assertEqual(payload["reason"], "no_prices")
        self.assertEqual(payload["summary"]["win_rate"], None)
        self.assertEqual(self.db.table_count("paper_trades"), 0)


if __name__ == "__main__":
    unittest.main()
