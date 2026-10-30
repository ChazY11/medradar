"""Offline unit tests for the event replay engine (:mod:`medradar.replay`).

Everything here is synthetic and deterministic: **no test touches the network**.
The only on-disk fixture is a synthetic Yahoo 1-minute chart payload with the
real response shape (epoch timestamps + parallel quote arrays), used to prove
the 1m parser and the "first bar after the public moment" rule.

Covered acceptance criteria:

* fill price selection on both branches (1m: first bar *after* available_at;
  daily: open of the next trading session);
* cost monotonicity and the exact PnL arithmetic per tier;
* look-ahead rejection (future public time; fill must be later than available_at);
* graceful degradation when prices (or the 1m feed) are missing;
* duplicate-signal de-duplication and timestamp-quality exclusion;
* a fully self-contained HTML page with no external resource references.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from medradar import replay
from medradar.db import DB
from medradar.replay import build_replay, fetch_intraday, parse_intraday_chart

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "replay"
ONE_MIN_FIXTURE = FIXTURE_DIR / "yahoo_chart_MDT_1m_sample.json"

NOW_DEFAULT = datetime(2024, 3, 10, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- helpers
def business_days(start: date, count: int) -> list[str]:
    days: list[str] = []
    cursor = start
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return days


def add_prices(db: DB, ticker: str, days: list[str], opens, closes=None, adj=None) -> None:
    closes = closes if closes is not None else opens
    adj = adj if adj is not None else closes
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
                "adj_close": float(adj[index]),
                "volume": 1_000_000,
            }
        )
    db.upsert_prices(rows)


def intraday_payload(entries: list[tuple[str, float]]) -> dict:
    """Build a Yahoo ``interval=1m`` shaped payload from (UTC ISO, open) pairs."""
    stamps = [int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()) for ts, _ in entries]
    opens = [float(price) for _, price in entries]
    return {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": "TEST", "dataGranularity": "1m", "range": "7d"},
                    "timestamp": stamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": opens,
                                "high": [price + 0.2 for price in opens],
                                "low": [price - 0.2 for price in opens],
                                "close": [price + 0.1 for price in opens],
                                "volume": [1000 for _ in opens],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


class FakeFetcher:
    """Minimal stand-in for :class:`medradar.http.Fetcher` (never hits network)."""

    def __init__(self, intraday=None, daily=None, fail_intervals=()) -> None:
        self.intraday = dict(intraday or {})
        self.daily = dict(daily or {})
        self.fail_intervals = set(fail_intervals)
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "errors": 0}
        self.calls: list[tuple[str, dict]] = []

    def get_json(self, url, params=None, retries=3, backoff=2.0, refresh=False):
        params = dict(params or {})
        ticker = url.rsplit("/", 1)[-1]
        self.calls.append((ticker, params))
        self.stats["requests"] += 1
        interval = params.get("interval")
        if interval in self.fail_intervals:
            raise RuntimeError(f"simulated {interval} failure")
        table = self.intraday if interval == "1m" else self.daily
        if ticker not in table:
            raise RuntimeError(f"no payload for {ticker}")
        return table[ticker]

    def calls_for(self, interval: str) -> list[tuple[str, dict]]:
        return [(ticker, params) for ticker, params in self.calls if params.get("interval") == interval]


# --------------------------------------------------------------------------- base
class ReplayTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._temp.name)
        self.db = DB(self.tmp / "medradar.sqlite")
        self.out_dir = self.tmp / "out"
        self.days = business_days(date(2024, 1, 1), 60)
        self.count = len(self.days)
        self.spy_closes = [100.0] * self.count
        add_prices(self.db, "SPY", self.days, self.spy_closes, self.spy_closes)
        self.aaa_opens = [100.0 + index for index in range(self.count)]
        self.aaa_closes = [101.0 + index for index in range(self.count)]
        add_prices(self.db, "AAA", self.days, self.aaa_opens, self.aaa_closes)

    def tearDown(self) -> None:
        self.db.close()
        self._temp.cleanup()

    # ------------------------------------------------------------------ seeding
    def add_event(
        self,
        event_id: str = "evt-1",
        *,
        event_date: str = "2024-01-03",
        available_at: str | None = None,
        quality: str = "date",
        kind: str = "510k",
        title: str = "测试事件：AAA 510(k) 清关",
        url: str = "https://www.fda.gov/medical-devices/510k/K240001",
        company_key: str = "acme",
        first_seen_at: str = "2024-01-05",
    ) -> None:
        self.db.upsert_events(
            [
                {
                    "event_id": event_id,
                    "source": "openfda_device_510k",
                    "kind": kind,
                    "event_date": event_date,
                    "as_of": "2024-01-05",
                    "company_key": company_key,
                    "track_id": "track_a",
                    "title": title,
                    "summary": "unit test event",
                    "url": url,
                    "available_at": available_at if available_at is not None else event_date,
                    "timestamp_quality": quality,
                    "first_seen_at": first_seen_at,
                    "payload": {},
                }
            ]
        )

    def set_available_timestamp(self, event_id: str, timestamp: str) -> None:
        """``db.upsert_events`` normalises dates; force a minute timestamp."""
        self.db.execute(
            "UPDATE events SET available_at = ?, timestamp_quality = 'datetime' WHERE event_id = ?",
            (timestamp, event_id),
        )
        self.db.commit()

    def add_signal(
        self,
        signal_id: str = "sig-1",
        *,
        event_id: str = "evt-1",
        ticker: str = "AAA",
        signal_date: str = "2024-01-04",
        kind: str = "device_novel_code",
        direction: int = 1,
        score: float = 0.8,
    ) -> None:
        self.db.upsert_signals(
            [
                {
                    "signal_id": signal_id,
                    "event_id": event_id,
                    "company_key": "acme",
                    "ticker": ticker,
                    "signal_date": signal_date,
                    "kind": kind,
                    "direction": direction,
                    "score": score,
                    "track_id": "track_a",
                    "reason_zh": "unit test signal",
                }
            ]
        )

    def seed_default(self, **event_kwargs) -> None:
        self.add_event(**event_kwargs)
        self.add_signal()

    # ------------------------------------------------------------------ build
    def build(self, **kwargs):
        params = {
            "capital": 100000,
            "out_dir": self.out_dir,
            "offline": True,
            "now": NOW_DEFAULT,
        }
        params.update(kwargs)
        start = params.pop("start", "2024-01-01")
        end = params.pop("end", "2024-02-29")
        return build_replay(self.db, start, end, **params)

    def html(self) -> str:
        return (self.out_dir / "index.html").read_text(encoding="utf-8")

    def json_payload(self) -> dict:
        return json.loads((self.out_dir / "replay.json").read_text(encoding="utf-8"))

    # --------------------------------------------------------------- shortcuts
    def steps_for(self, payload: dict, ticker: str = "AAA") -> list[dict]:
        return [step for step in payload["steps"] if step.get("ticker") == ticker]


# --------------------------------------------------------------------------- parser
class IntradayParserTests(unittest.TestCase):
    def test_parse_synthetic_yahoo_1m_fixture(self) -> None:
        payload = json.loads(ONE_MIN_FIXTURE.read_text(encoding="utf-8"))
        bars = parse_intraday_chart(payload, "MDT")
        self.assertEqual(len(bars), 5)
        self.assertEqual(bars[0]["ticker"], "MDT")
        self.assertEqual(bars[0]["open"], 101.0)
        self.assertEqual(bars[-1]["open"], 101.3)
        self.assertLess(bars[0]["ts"], bars[-1]["ts"])
        self.assertEqual(bars[0]["time"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M"), "2026-10-29T13:30")
        self.assertTrue(all(bar["open"] > 0 for bar in bars))

    def test_parse_rejects_error_and_empty_payloads(self) -> None:
        with self.assertRaises(ValueError):
            parse_intraday_chart({"chart": {"result": [], "error": {"code": "x"}}}, "X")
        with self.assertRaises(ValueError):
            parse_intraday_chart({"chart": {"error": None, "result": [{"timestamp": [], "indicators": {}}]}}, "X")
        with self.assertRaises(ValueError):
            parse_intraday_chart({"chart": {"result": [{"timestamp": [1], "indicators": {"quote": [{"open": [None]}]}}]}}, "X")

    def test_fetch_intraday_uses_budgeted_get_json(self) -> None:
        payload = json.loads(ONE_MIN_FIXTURE.read_text(encoding="utf-8"))
        fetcher = FakeFetcher(intraday={"MDT": payload})
        bars = fetch_intraday(fetcher, "MDT")
        self.assertEqual(len(bars), 5)
        ticker, params = fetcher.calls[0]
        self.assertEqual(ticker, "MDT")
        self.assertEqual(params["range"], "7d")
        self.assertEqual(params["interval"], "1m")


# --------------------------------------------------------------------------- fills / look-ahead
class FillSelectionTests(ReplayTestCase):
    def test_daily_fill_is_next_session_open_not_event_day_open(self) -> None:
        self.seed_default()
        payload = self.build()
        self.assertEqual(payload["status"], "ok")
        steps = self.steps_for(payload)
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertEqual(step["decision"], "BUY")
        self.assertEqual(step["price_source"], "daily")
        # 2024-01-03 is a trading day in the synthetic calendar: the fill must be
        # the NEXT session (2024-01-04) and must not use the event-day open.
        anchor = self.days.index("2024-01-04")
        self.assertEqual(step["fill_date"], self.days[anchor])
        self.assertAlmostEqual(step["fill_price"], self.aaa_opens[anchor], places=6)
        self.assertNotEqual(step["fill_date"], "2024-01-03")
        self.assertGreater(step["fill_date"], "2024-01-03")
        # Time-of-day: 09:30 US/Eastern in January.
        self.assertIn("T09:30:00-05:00", step["fill_time"])

    def test_daily_outcomes_are_measured_from_the_fill_price(self) -> None:
        self.seed_default()
        payload = self.build()
        step = self.steps_for(payload)[0]
        anchor = self.days.index(step["fill_date"])
        entry = step["fill_price"]
        expected_1d = self.aaa_closes[anchor + 1] / entry - 1.0
        expected_20d = self.aaa_closes[anchor + 20] / entry - 1.0
        self.assertAlmostEqual(step["outcome_1d"], expected_1d, places=5)
        self.assertAlmostEqual(step["outcome_20d"], expected_20d, places=5)
        self.assertAlmostEqual(step["gross_return"], expected_20d, places=5)
        self.assertEqual(step["holding_days"], 20)
        self.assertEqual(step["exit_date"], self.days[anchor + 20])

    def test_intraday_fill_is_first_bar_after_public_moment(self) -> None:
        self.add_event(quality="datetime")
        self.set_available_timestamp("evt-1", "2024-01-03T15:00:00Z")
        self.add_signal()
        payload_bars = intraday_payload(
            [
                ("2024-01-03T13:30:00Z", 101.0),  # before the public moment: forbidden
                ("2024-01-03T14:30:00Z", 102.0),  # still before: forbidden
                ("2024-01-03T15:30:00Z", 103.5),  # first bar strictly after: THE fill
                ("2024-01-03T16:00:00Z", 104.0),
            ]
        )
        fetcher = FakeFetcher(intraday={"AAA": payload_bars})
        payload = self.build(
            offline=False,
            fetcher=fetcher,
            now=datetime(2024, 1, 5, 23, 0, tzinfo=timezone.utc),
        )
        step = self.steps_for(payload)[0]
        self.assertEqual(step["decision"], "BUY")
        self.assertEqual(step["price_source"], "1m")
        self.assertEqual(step["fill_date"], "2024-01-03")
        self.assertAlmostEqual(step["fill_price"], 103.5, places=6)
        self.assertIn("T10:30:00-05:00", step["fill_time"])
        # the bar before the public moment must never be used
        self.assertNotAlmostEqual(step["fill_price"], 101.0, places=6)
        self.assertNotAlmostEqual(step["fill_price"], 102.0, places=6)
        # the fill happens strictly after the public timestamp
        fill_moment, _ = replay._parse_moment(step["fill_time"])
        available_moment, _ = replay._parse_moment(step["available_at_utc"])
        self.assertIsNotNone(fill_moment)
        self.assertIsNotNone(available_moment)
        assert fill_moment is not None and available_moment is not None
        self.assertGreater(fill_moment, available_moment)
        # only the 1-minute endpoint was requested (daily bars come from SQLite)
        self.assertEqual(fetcher.calls_for("1d"), [])
        self.assertEqual(len(fetcher.calls_for("1m")), 1)

    def test_intraday_branch_not_used_outside_the_seven_day_window(self) -> None:
        self.add_event(quality="datetime")
        self.set_available_timestamp("evt-1", "2024-01-03T15:00:00Z")
        self.add_signal()
        fetcher = FakeFetcher(intraday={"AAA": intraday_payload([("2024-01-03T15:30:00Z", 103.5)])})
        payload = self.build(
            offline=False,
            fetcher=fetcher,
            now=datetime(2024, 2, 20, tzinfo=timezone.utc),  # > 7 days after the event
        )
        step = self.steps_for(payload)[0]
        self.assertEqual(step["price_source"], "daily")
        self.assertAlmostEqual(step["fill_price"], self.aaa_opens[self.days.index("2024-01-04")], places=6)
        self.assertEqual(fetcher.calls, [], "1m endpoint must not be requested for stale events")

    def test_intraday_failure_falls_back_to_daily_and_records_reason(self) -> None:
        self.add_event(quality="datetime")
        self.set_available_timestamp("evt-1", "2024-01-03T15:00:00Z")
        self.add_signal()
        fetcher = FakeFetcher(intraday={"AAA": intraday_payload([("2024-01-03T15:30:00Z", 103.5)])}, fail_intervals=("1m",))
        payload = self.build(
            offline=False,
            fetcher=fetcher,
            now=datetime(2024, 1, 5, 23, 0, tzinfo=timezone.utc),
        )
        step = self.steps_for(payload)[0]
        self.assertEqual(step["decision"], "BUY")
        self.assertEqual(step["price_source"], "daily")
        self.assertIn("RuntimeError", step["intraday_fallback"])
        self.assertAlmostEqual(step["fill_price"], self.aaa_opens[self.days.index("2024-01-04")], places=6)

    def test_future_public_time_is_rejected(self) -> None:
        self.seed_default(event_date="2024-04-01", available_at="2024-04-01")
        payload = self.build()
        steps = self.steps_for(payload)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["decision"], "SKIP")
        self.assertEqual(steps[0]["skip_reason"], "not_yet_public")
        self.assertIsNone(steps[0]["fill_price"])
        self.assertEqual(payload["status"], "insufficient_data")
        self.assertEqual(payload["trades"], [])
        self.assertEqual(payload["audit"]["lookahead_rejected"], 0)

    def test_weekend_public_date_fills_on_next_monday(self) -> None:
        # 2024-01-06 is a Saturday; the next session is Monday 2024-01-08.
        self.seed_default(event_date="2024-01-06", available_at="2024-01-06")
        self.add_signal(signal_id="sig-2", signal_date="2024-01-07")
        # replace the default signal to keep one event
        self.db.execute("DELETE FROM signals WHERE signal_id = 'sig-1'")
        self.db.commit()
        payload = self.build()
        step = self.steps_for(payload)[0]
        self.assertEqual(step["fill_date"], "2024-01-08")
        self.assertGreater(step["fill_date"], "2024-01-06")


# --------------------------------------------------------------------------- costs
class CostTests(ReplayTestCase):
    def test_cost_tiers_are_strictly_monotone_and_arithmetic_is_exact(self) -> None:
        self.seed_default()
        payload = self.build()
        summary = payload["summary_by_cost"]
        self.assertEqual(list(summary.keys()), ["10", "25", "50"])
        returns = [summary[key]["total_return"] for key in ("10", "25", "50")]
        self.assertGreater(returns[0], returns[1])
        self.assertGreater(returns[1], returns[2])
        # exact arithmetic: cost is charged per side, so the round trip is 2x bps.
        step = self.steps_for(payload)[0]
        anchor = self.days.index(step["fill_date"])
        gross = self.aaa_closes[anchor + 20] / self.aaa_opens[anchor] - 1.0
        notional = 100000.0 * 0.20 * 0.8  # capital * position_pct * score
        self.assertAlmostEqual(step["notional"], notional, places=2)
        for key, bps in (("10", 10.0), ("25", 25.0), ("50", 50.0)):
            expected_ret = gross - 2.0 * bps / 10000.0
            self.assertAlmostEqual(step["net_by_cost"][key], expected_ret, places=5)
            self.assertAlmostEqual(step["pnl_by_cost"][key], notional * expected_ret, places=1)
            self.assertAlmostEqual(summary[key]["total_pnl"], notional * expected_ret, places=1)
            self.assertAlmostEqual(summary[key]["final_equity"], 100000.0 + notional * expected_ret, places=1)
        gap = summary["10"]["total_return"] - summary["25"]["total_return"]
        self.assertAlmostEqual(gap, notional * 2.0 * 15.0 / 10000.0 / 100000.0, places=6)
        self.assertEqual(summary["10"]["trades"], 1)
        self.assertEqual(summary["10"]["n_trades"], 1)
        self.assertEqual(summary["10"]["avg_holding_days"], 20.0)

    def test_event_study_horizons_match_step_outcomes(self) -> None:
        self.seed_default()
        payload = self.build()
        step = self.steps_for(payload)[0]
        horizons = payload["event_study"]["horizons"]
        self.assertEqual(horizons["1"]["n"], 1)
        self.assertAlmostEqual(horizons["1"]["mean"], step["outcome_1d"], places=6)
        self.assertAlmostEqual(horizons["20"]["mean"], step["outcome_20d"], places=6)
        self.assertIn("10", horizons["20"]["mean_net_by_cost"])


# --------------------------------------------------------------------------- data quality
class DataQualityTests(ReplayTestCase):
    def test_duplicate_signals_are_deduped(self) -> None:
        self.seed_default()
        # second analysis run produced a new signal_id for the same event
        self.add_signal(signal_id="sig-1-again", score=0.9)
        payload = self.build()
        self.assertEqual(payload["meta"]["counts"]["signals_raw"], 2)
        self.assertEqual(payload["meta"]["counts"]["duplicates_removed"], 1)
        self.assertEqual(payload["meta"]["counts"]["signals_unique"], 1)
        self.assertEqual(len(self.steps_for(payload)), 1)
        self.assertEqual(payload["summary_by_cost"]["10"]["trades"], 1)
        self.assertAlmostEqual(self.steps_for(payload)[0]["score"], 0.9, places=6)

    def test_unknown_timestamp_quality_is_excluded(self) -> None:
        self.seed_default(quality="unknown")
        payload = self.build()
        self.assertEqual(payload["steps"], [])
        self.assertEqual(payload["meta"]["counts"]["low_quality_excluded"], 1)
        self.assertEqual(payload["quality"]["excluded"], 1)
        self.assertEqual(payload["status"], "insufficient_data")
        self.assertTrue((self.out_dir / "index.html").exists())

    def test_missing_prices_degrade_gracefully(self) -> None:
        self.add_event()
        self.add_signal(ticker="ZZZ")
        payload = self.build()
        self.assertEqual(payload["status"], "insufficient_data")
        self.assertEqual(payload["reason"], "no_prices")
        steps = self.steps_for(payload, "ZZZ")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["decision"], "SKIP")
        self.assertEqual(steps[0]["skip_reason"], "no_price")
        self.assertEqual(payload["trades"], [])
        # the page is still rendered for inspection
        self.assertTrue((self.out_dir / "index.html").exists())
        self.assertGreater((self.out_dir / "index.html").stat().st_size, 500)

    def test_empty_database_reports_insufficient_without_raising(self) -> None:
        payload = self.build()
        self.assertEqual(payload["status"], "insufficient_data")
        self.assertEqual(payload["reason"], "no_signals")
        self.assertEqual(payload["steps"], [])
        self.assertTrue((self.out_dir / "replay.json").exists())

    def test_window_filter_and_short_signals(self) -> None:
        self.add_event(company_key="acme")
        self.add_signal(signal_id="long", signal_date="2024-01-04")
        self.add_signal(signal_id="short", direction=-1, signal_date="2024-01-04")
        payload = self.build()
        decisions = {step["signal_id"]: step["decision"] for step in payload["steps"]}
        self.assertEqual(decisions["long"], "BUY")
        self.assertEqual(decisions["short"], "SKIP")
        short_step = next(step for step in payload["steps"] if step["signal_id"] == "short")
        self.assertEqual(short_step["skip_reason"], "short_not_supported")
        # outside the window neither signal is replayed
        outside = self.build(start="2024-03-01", end="2024-03-31")
        self.assertEqual(outside["steps"], [])
        self.assertEqual(outside["reason"], "no_signals_in_window")

    def test_allow_short_marks_the_unmodelled_borrow_assumption(self) -> None:
        self.add_event()
        self.add_signal(direction=-1)
        payload = self.build(allow_short=True)
        step = payload["steps"][0]
        self.assertEqual(step["decision"], "SHORT")
        self.assertEqual(payload["method"]["long_only"], False)
        self.assertIn("借券费", payload["disclaimer_zh"])


# --------------------------------------------------------------------------- HTML contract
class HtmlContractTests(ReplayTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.seed_default()
        self.payload = self.build()

    def test_schema_11_contract_keys(self) -> None:
        payload = self.payload
        for key in ("status", "window", "steps", "summary_by_cost", "assumptions_url"):
            self.assertIn(key, payload)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["window"]["start"], "2024-01-01")
        self.assertEqual(payload["window"]["end"], "2024-02-29")
        self.assertEqual(payload["assumptions_url"], "docs/ASSUMPTIONS.md")
        self.assertEqual(set(payload["summary_by_cost"]), {"10", "25", "50"})
        first = payload["summary_by_cost"]["10"]
        for key in ("total_return", "max_drawdown", "win_rate", "trades", "avg_holding_days"):
            self.assertIn(key, first)
        step = payload["steps"][0]
        for key in ("t", "ticker", "event_zh", "decision", "fill_price", "shares", "outcome_1d", "outcome_5d", "outcome_20d", "url"):
            self.assertIn(key, step)
        self.assertIn(step["decision"], {"BUY", "SKIP"})
        self.assertLessEqual(payload["summary_by_cost"]["10"]["max_drawdown"], 0.0)

    def test_replay_json_matches_payload(self) -> None:
        written = self.json_payload()
        self.assertEqual(written["status"], self.payload["status"])
        self.assertEqual(len(written["steps"]), len(self.payload["steps"]))
        self.assertEqual(set(written["summary_by_cost"]), {"10", "25", "50"})
        self.assertTrue(written["files"]["json"].endswith("replay.json"))
        self.assertTrue(written["files"]["html"].endswith("index.html"))

    def test_html_is_self_contained_and_has_no_external_resources(self) -> None:
        html = self.html()
        # banner must state all three free-data limits
        self.assertIn("1 分钟数据仅最近 ~7 天", html)
        self.assertIn("无 bid/ask", html)
        self.assertIn("无借券费", html)
        # inline assets only
        self.assertIn("<style>", html)
        self.assertIn("<script>", html)
        self.assertIn("<svg", html)
        # no external resource reference of any kind (the scheme is entity-encoded
        # on the per-event source anchors so citations stay clickable but the page
        # never loads a remote resource).
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        for pattern in (r"<link\b", r"<script[^>]+src\s*=", r"<img\b", r"@import"):
            self.assertIsNone(re.search(pattern, html, re.I), pattern)
        # each event still links back to the original filing
        anchors = re.findall(r'<a class="src" href="https[^"]*"', html)
        self.assertGreaterEqual(len(anchors), 1)
        self.assertIn('target="_blank"', html)
        self.assertIn("假设登记表", html)

    def test_html_timeline_contains_event_decision_fill_and_outcomes(self) -> None:
        html = self.html()
        self.assertIn("时间轴：事件 → 判定 → 成交 → 后续", html)
        self.assertIn("后续 1 / 5 / 20 日", html)
        self.assertIn("只看成交", html)
        self.assertIn("成本敏感性", html)
        self.assertIn('data-decision="buy"', html)
        # the fill in the HTML is the same number as the JSON
        step = self.payload["steps"][0]
        self.assertIn(f'{step["fill_price"]:,.2f}', html)


# --------------------------------------------------------------------------- misc
class BuildApiTests(ReplayTestCase):
    def test_accepts_a_database_path_and_custom_output_directory(self) -> None:
        self.seed_default()
        target = self.tmp / "custom-out"
        payload = build_replay(
            self.db.path,
            "2024-01-01",
            "2024-02-29",
            out_dir=target,
            offline=True,
            now=NOW_DEFAULT,
        )
        self.assertEqual(payload["status"], "ok")
        self.assertTrue((target / "replay.json").exists())
        self.assertTrue((target / "index.html").exists())

    def test_invalid_inputs_raise_clear_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.build(start="not-a-date")
        with self.assertRaises(ValueError):
            self.build(capital=0)

    def test_request_budget_is_respected(self) -> None:
        self.add_event(quality="datetime")
        self.set_available_timestamp("evt-1", "2024-01-03T15:00:00Z")
        self.add_signal()
        fetcher = FakeFetcher(intraday={"AAA": intraday_payload([("2024-01-03T15:30:00Z", 103.5)])})
        payload = self.build(
            offline=False,
            fetcher=fetcher,
            now=datetime(2024, 1, 5, 23, 0, tzinfo=timezone.utc),
            max_requests=0,
        )
        step = self.steps_for(payload)[0]
        self.assertEqual(step["price_source"], "daily")
        self.assertIn("budget", (step["intraday_fallback"] or "").lower())
        self.assertEqual(fetcher.stats["requests"], 0)
        self.assertEqual(payload["meta"]["request_stats"]["budget_used"], 0)


if __name__ == "__main__":
    unittest.main()
