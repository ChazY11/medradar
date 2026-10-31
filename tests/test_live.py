"""Offline tests for the live event lane and the simulated broker.

No network: pollers are patched, quotes are injected, and the EDGAR Atom fixture
is a verbatim fragment of the real feed.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from medradar import live
from medradar.db import DB

ATOM_FIXTURE = """<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
<title>8-K - Acme Therapeutics, Inc. (0001234567) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/0001234567-26-000001-index.htm"/>
<summary type="html">
 &lt;b&gt;Filed:&lt;/b&gt; 2026-10-30 &lt;b&gt;AccNo:&lt;/b&gt; 0001234567-26-000001 &lt;b&gt;Size:&lt;/b&gt; 2 MB
&lt;br&gt;Item 8.01: Other Events
</summary>
<updated>2026-10-30T13:45:32-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
<id>urn:tag:sec.gov,2008:accession-number=0001234567-26-000001</id>
</entry>
</feed>
"""


class EdgarParseTests(unittest.TestCase):
    def test_parses_title_cik_accession_items_and_time(self) -> None:
        entries = live.parse_edgar_atom(ATOM_FIXTURE)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["cik"], 1234567)
        self.assertEqual(entry["accession"], "0001234567-26-000001")
        self.assertIn("8.01", entry["items"])
        self.assertIn("Acme Therapeutics", entry["company_name"])
        self.assertEqual(entry["event_time"], "2026-10-30T13:45:32-04:00")


class ClassifierTests(unittest.TestCase):
    def test_negative_catalyst(self) -> None:
        direction, score, matched = live.classify_text(
            "The Company received a Complete Response Letter from the FDA."
        )
        self.assertEqual(direction, -1)
        self.assertGreater(score, 0.4)
        self.assertIn("complete response letter", " ".join(matched))

    def test_positive_catalyst(self) -> None:
        direction, score, _ = live.classify_text(
            "The FDA has approved the product and the trial met the primary endpoint."
        )
        self.assertEqual(direction, 1)
        self.assertGreater(score, 0.5)

    def test_neutral_text(self) -> None:
        direction, score, matched = live.classify_text("Annual meeting results and governance update.")
        self.assertEqual(direction, 0)
        self.assertEqual(score, 0.0)
        self.assertEqual(matched, [])


class SizingTests(unittest.TestCase):
    def test_position_cap_and_track_cap(self) -> None:
        params = live.LiveParams(max_position=0.05, max_track=0.25)
        # 5% of 100k at $100 = 50 shares
        self.assertAlmostEqual(live.size_order(100_000, 100_000, 100.0, 0.0, params), 50.0)
        # track already at 24k -> only 1k room left = 10 shares
        self.assertAlmostEqual(live.size_order(100_000, 100_000, 100.0, 24_000.0, params), 10.0)
        # no cash
        self.assertEqual(live.size_order(0, 100_000, 100.0, 0.0, params), 0.0)

    def test_slippage_hurts_both_sides(self) -> None:
        self.assertGreater(live.fill_price(100.0, "buy", 10.0), 100.0)
        self.assertLess(live.fill_price(100.0, "sell", 10.0), 100.0)


class RunOnceTests(unittest.TestCase):
    def _cycle(self, db_path: Path, quote_price: float, alerts, params=None, quote_payload=None):
        fetcher = mock.Mock()
        payload = quote_payload if quote_payload is not None else {
            "price": quote_price,
            "quote_time": datetime.now(timezone.utc).isoformat(),
            "market_state": "REGULAR",
        }
        quote_fn = lambda _fetcher, ticker: dict(payload)
        with mock.patch.object(live, "poll_edgar", return_value=alerts), \
             mock.patch.object(live, "poll_edgar_fts", return_value=[]), \
             mock.patch.object(live, "poll_fda_rss", return_value=[]), \
             mock.patch.object(live, "poll_trials", return_value=[]), \
             mock.patch.object(live, "_watchlist", return_value={1234567: ("acme", "ACME")}), \
             mock.patch.object(live, "notify", return_value=None):
            return live.run_once(db_path, params or live.LiveParams(capital=100_000), fetcher=fetcher, quote_fn=quote_fn)

    def _alert(self, alert_id: str = "edgar-1", **overrides):
        alert = {
            "alert_id": alert_id,
            "source": "sec_edgar",
            "kind": "8k_catalyst",
            "ticker": "ACME",
            "company_key": "acme",
            "direction": 1,
            "score": 0.6,
            "materiality": 1.0,
            "catalyst_type": "approval",
            "headline": "FDA approval",
            "url": "",
            "event_time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            "payload": {},
        }
        alert.update(overrides)
        return alert

    def test_buy_creates_position_and_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            db = DB(db_path)
            db.upsert_companies([{"key": "acme", "name_zh": "Acme", "ticker": "ACME", "sector": "device"}])
            db.close()
            alert = {
                "alert_id": "edgar-1",
                "source": "sec_edgar",
                "kind": "8k_catalyst",
                "ticker": "ACME",
                "company_key": "acme",
                "direction": 1,
                "score": 0.6,
                "headline": "FDA approval",
                "url": "",
                "event_time": "2026-10-30T20:00:00Z",
                "payload": {},
            }
            result = self._cycle(db_path, 100.0, [alert])
            self.assertEqual(result["alerts_new"], 1)
            self.assertEqual(len(result["orders"]), 1)
            order = result["orders"][0]
            self.assertEqual(order["side"], "buy")
            # sized on the slipped fill price (100.01), not the raw quote: 5000/100.01
            self.assertAlmostEqual(order["qty"], 49.95, places=4)
            self.assertGreater(order["fill_price"], 100.0)  # slippage applied
            with DB(db_path) as check:
                self.assertEqual(check.scalar("SELECT COUNT(*) FROM positions"), 1)
                self.assertEqual(check.scalar("SELECT status FROM positions"), "open")

    def test_alert_dedup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            alert = {
                "alert_id": "dup-1", "source": "fda_press", "kind": "fda_press", "ticker": "",
                "company_key": "", "direction": 1, "score": 0.5, "headline": "x", "url": "",
                "event_time": "", "payload": {},
            }
            first = self._cycle(db_path, 100.0, [alert])
            second = self._cycle(db_path, 100.0, [alert])
            self.assertEqual(first["alerts_new"], 1)
            self.assertEqual(second["alerts_new"], 0)

    def test_stop_loss_exits_position(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            with DB(db_path) as db:
                db.upsert_companies([{"key": "acme", "ticker": "ACME", "sector": "device"}])
                db.meta_set("live.cash", 95_000.0)
                db.meta_set("live.seeded", True)
                db.execute(
                    "INSERT INTO positions(ticker, qty, avg_price, opened_at, track_id, last_price,"
                    " market_value, unrealized_pnl, status) VALUES (?,?,?,?,?,?,?,?, 'open')",
                    ("ACME", 50.0, 100.0, datetime.now(timezone.utc).isoformat(), "device", 100.0, 5_000.0, 0.0),
                )
                db.conn.commit()
            result = self._cycle(db_path, 70.0, [])
            sides = [order["side"] for order in result["orders"]]
            self.assertIn("sell", sides)
            with DB(db_path) as db:
                self.assertEqual(db.scalar("SELECT status FROM positions WHERE ticker='ACME'"), "closed")

    def test_mark_to_market_equity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            with DB(db_path) as db:
                db.upsert_companies([{"key": "acme", "ticker": "ACME", "sector": "device"}])
                db.meta_set("live.cash", 95_000.0)
                db.meta_set("live.seeded", True)
                db.execute(
                    "INSERT INTO positions(ticker, qty, avg_price, opened_at, track_id, last_price,"
                    " market_value, unrealized_pnl, status) VALUES (?,?,?,?,?,?,?,?, 'open')",
                    ("ACME", 50.0, 100.0, datetime.now(timezone.utc).isoformat(), "device", 100.0, 5_000.0, 0.0),
                )
                db.conn.commit()
            result = self._cycle(db_path, 110.0, [])
            self.assertAlmostEqual(result["book"]["equity"], 95_000.0 + 50.0 * 110.0, places=2)
            self.assertGreater(result["book"]["n_positions"], 0)

    # --------------------------------------------------- trust / execution guards
    def test_no_trade_freezes_exits_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            with DB(db_path) as db:
                db.upsert_companies([{"key": "acme", "ticker": "ACME", "sector": "device"}])
                db.meta_set("live.cash", 95_000.0)
                db.meta_set("live.seeded", True)
                db.execute(
                    "INSERT INTO positions(ticker, qty, avg_price, opened_at, track_id, last_price,"
                    " market_value, unrealized_pnl, status) VALUES (?,?,?,?,?,?,?,?, 'open')",
                    ("ACME", 50.0, 100.0, datetime.now(timezone.utc).isoformat(), "device", 100.0, 5_000.0, 0.0),
                )
                db.conn.commit()
            result = self._cycle(db_path, 70.0, [], params=live.LiveParams(no_trade=True))
            self.assertEqual(result["orders"], [])
            with DB(db_path) as db:
                self.assertEqual(db.scalar("SELECT status FROM positions WHERE ticker='ACME'"), "open")

    def test_cash_never_negative_after_slippage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            with DB(db_path) as db:
                db.upsert_companies([{"key": "acme", "ticker": "ACME", "sector": "device"}])
                db.meta_set("live.cash", 5_000.0)
            alert = {
                "alert_id": "small-cash-1", "source": "sec_edgar", "kind": "8k_catalyst",
                "ticker": "ACME", "company_key": "acme", "direction": 1, "score": 0.8,
                "materiality": 1.0, "catalyst_type": "approval", "headline": "x", "url": "",
                "event_time": "", "payload": {},
            }
            params = live.LiveParams(capital=5_000.0, max_position=1.0, slippage_bps=10.0)
            result = self._cycle(db_path, 100.0, [alert], params=params)
            self.assertEqual(len(result["orders"]), 1)
            with DB(db_path) as db:
                cash = float(db.meta_get("live.cash"))
            self.assertGreaterEqual(cash, -1e-6)

    def test_stale_quote_blocks_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            with DB(db_path) as db:
                db.upsert_companies([{"key": "acme", "ticker": "ACME", "sector": "device"}])
            alert = {
                "alert_id": "stale-1", "source": "sec_edgar", "kind": "8k_catalyst",
                "ticker": "ACME", "company_key": "acme", "direction": 1, "score": 0.8,
                "materiality": 0.9, "catalyst_type": "approval", "headline": "x", "url": "",
                "event_time": "", "payload": {},
            }
            payload = {
                "price": 100.0,
                "quote_time": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                "market_state": "REGULAR",
                "stale": True,
            }
            result = self._cycle(db_path, 100.0, [alert], quote_payload=payload)
            self.assertEqual(result["orders"], [])
            self.assertEqual(result["skipped"].get("stale_quote"), 1)
            with DB(db_path) as db:
                self.assertEqual(db.table_count("positions"), 0)

    # ------------------------------------------------- cash conservation & retries
    def test_buy_debits_cash_and_conserves_equity(self) -> None:
        """The release-blocking bug: a buy must reduce cash by exactly qty × fill."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            with DB(db_path) as db:
                db.upsert_companies([{"key": "acme", "ticker": "ACME", "sector": "device"}])
            result = self._cycle(db_path, 100.0, [self._alert()])
            self.assertEqual(len(result["orders"]), 1)
            order = result["orders"][0]
            with DB(db_path) as db:
                cash = float(db.meta_get("live.cash"))
                position = db.query("SELECT * FROM positions")[0]
            expected_cash = 100_000.0 - order["qty"] * order["fill_price"]
            self.assertAlmostEqual(cash, expected_cash, places=6)
            self.assertLess(cash, 100_000.0)
            # equity = cash + holdings, and only the slippage may be lost
            equity = cash + position["qty"] * position["last_price"]
            self.assertAlmostEqual(equity, result["book"]["equity"], places=2)
            slippage_cost = order["qty"] * (order["fill_price"] - 100.0)
            self.assertAlmostEqual(equity, 100_000.0 - slippage_cost, places=2)

    def test_market_closed_queues_then_fills_on_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            with DB(db_path) as db:
                db.upsert_companies([{"key": "acme", "ticker": "ACME", "sector": "device"}])
            closed = {
                "price": 100.0,
                "quote_time": datetime.now(timezone.utc).isoformat(),
                "market_state": "CLOSED",
            }
            first = self._cycle(db_path, 100.0, [self._alert()], quote_payload=closed)
            self.assertEqual(first["orders"], [])
            self.assertEqual(first["skipped"].get("market_closed"), 1)
            with DB(db_path) as db:
                self.assertEqual(db.scalar("SELECT status FROM live_pending"), "pending")
                self.assertEqual(db.scalar("SELECT reason FROM live_skips"), "market_closed")

            reopened = {
                "price": 100.0,
                "quote_time": datetime.now(timezone.utc).isoformat(),
                "market_state": "REGULAR",
            }
            second = self._cycle(db_path, 100.0, [], quote_payload=reopened)
            self.assertEqual(len(second["orders"]), 1)
            with DB(db_path) as db:
                self.assertEqual(db.table_count("positions"), 1)
                self.assertEqual(db.scalar("SELECT status FROM live_pending"), "done")
                self.assertLess(float(db.meta_get("live.cash")), 100_000.0)

            third = self._cycle(db_path, 100.0, [], quote_payload=reopened)
            self.assertEqual(third["orders"], [])  # no duplicate fill

    def test_quote_before_news_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            with DB(db_path) as db:
                db.upsert_companies([{"key": "acme", "ticker": "ACME", "sector": "device"}])
            alert = self._alert(event_time=datetime.now(timezone.utc).isoformat())
            payload = {
                "price": 100.0,
                "quote_time": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
                "market_state": "REGULAR",
            }
            result = self._cycle(db_path, 100.0, [alert], quote_payload=payload)
            self.assertEqual(result["orders"], [])
            self.assertEqual(result["skipped"].get("quote_before_news"), 1)
            with DB(db_path) as db:
                self.assertEqual(db.table_count("positions"), 0)

    def test_quote_time_missing_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            with DB(db_path) as db:
                db.upsert_companies([{"key": "acme", "ticker": "ACME", "sector": "device"}])
            payload = {"price": 100.0, "market_state": "REGULAR"}
            result = self._cycle(db_path, 100.0, [self._alert()], quote_payload=payload)
            self.assertEqual(result["orders"], [])
            self.assertEqual(result["skipped"].get("quote_time_missing"), 1)

    def test_missing_price_queues_and_retries_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            with DB(db_path) as db:
                db.upsert_companies([{"key": "acme", "ticker": "ACME", "sector": "device"}])
            empty = {}
            first = self._cycle(db_path, 100.0, [self._alert()], quote_payload=empty)
            self.assertEqual(first["orders"], [])
            self.assertEqual(first["skipped"].get("no_price"), 1)
            ok = {
                "price": 100.0,
                "quote_time": datetime.now(timezone.utc).isoformat(),
                "market_state": "REGULAR",
            }
            second = self._cycle(db_path, 100.0, [], quote_payload=ok)
            self.assertEqual(len(second["orders"]), 1)
            with DB(db_path) as db:
                self.assertEqual(db.scalar("SELECT COUNT(*) FROM paper_orders"), 1)

    def test_pending_expiry_uses_first_queued_time(self) -> None:
        """A pending order must expire by news age, not by retry time."""
        from datetime import timedelta as _td

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            with DB(db_path) as db:
                db.upsert_companies([{"key": "acme", "ticker": "ACME", "sector": "device"}])
                old = (datetime.now(timezone.utc) - _td(hours=48)).isoformat()
                now = datetime.now(timezone.utc).isoformat()
                db.execute(
                    "INSERT INTO live_pending(alert_id, ticker, created_at, attempts, last_attempt_at,"
                    " last_reason, status) VALUES ('old-1','ACME',?,3,?,'market_closed','pending')",
                    (old, now),
                )
                db.conn.commit()
                live._expire_pending(db, datetime.now(timezone.utc))
                status = db.scalar("SELECT status FROM live_pending WHERE alert_id='old-1'")
            self.assertEqual(status, "expired")

    def test_interrupted_fill_rolls_back_and_is_not_masked(self) -> None:
        """A crash inside the fill must not leave cash debited or mark the book seeded."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            with DB(db_path) as db:
                db.upsert_companies([{"key": "acme", "ticker": "ACME", "sector": "device"}])
            original = live._record_order

            def boom(*args, **kwargs):
                raise RuntimeError("simulated order write failure")

            with mock.patch.object(live, "_record_order", side_effect=boom):
                with self.assertRaises(RuntimeError):
                    self._cycle(db_path, 100.0, [self._alert()])
            with DB(db_path) as db:
                self.assertAlmostEqual(float(db.meta_get("live.cash")), 100_000.0, places=6)
                self.assertEqual(db.table_count("positions"), 0)
                self.assertEqual(db.table_count("paper_orders"), 0)
                self.assertIsNone(db.meta_get("live.seeded"))
                self.assertEqual(db.scalar("SELECT status FROM live_pending"), "pending")
            # Recovery: the queued alert fills once, and the invariant accepts it.
            with mock.patch.object(live, "_record_order", original):
                recovered = self._cycle(db_path, 100.0, [], quote_payload={
                    "price": 100.0,
                    "quote_time": datetime.now(timezone.utc).isoformat(),
                    "market_state": "REGULAR",
                })
            self.assertEqual(len(recovered["orders"]), 1)
            with DB(db_path) as db:
                self.assertEqual(db.table_count("positions"), 1)
                self.assertLess(float(db.meta_get("live.cash")), 100_000.0)

    def test_cross_source_duplicate_is_collapsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            with DB(db_path) as db:
                db.upsert_companies([{"key": "acme", "ticker": "ACME", "sector": "device"}])
            base = {
                "kind": "8k_catalyst", "ticker": "ACME", "company_key": "acme",
                "direction": 1, "score": 0.8, "materiality": 0.9, "catalyst_type": "approval",
                "headline": "FDA approval", "url": "", "event_time": "2026-10-30T13:00:00-04:00",
                "payload": {},
            }
            first = dict(base, alert_id="feed-1", source="sec_edgar")
            second = dict(base, alert_id="fts-1", source="sec_edgar_fts")
            result = self._cycle(db_path, 100.0, [first, second], params=live.LiveParams(no_trade=True))
            self.assertEqual(result["alerts_new"], 1)

    def test_non_tradeable_source_is_alert_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "live.sqlite"
            with DB(db_path) as db:
                db.upsert_companies([{"key": "acme", "ticker": "ACME", "sector": "device"}])
            alert = {
                "alert_id": "rss-1", "source": "fda_press", "kind": "fda_press",
                "ticker": "ACME", "company_key": "acme", "direction": 1, "score": 0.9,
                "materiality": 0.9, "catalyst_type": "approval", "headline": "x", "url": "",
                "event_time": "", "payload": {},
            }
            result = self._cycle(db_path, 100.0, [alert])
            self.assertEqual(result["orders"], [])
            self.assertEqual(result["alerts_new"], 1)


if __name__ == "__main__":
    unittest.main()
