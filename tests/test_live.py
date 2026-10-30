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
    def _cycle(self, db_path: Path, quote_price: float, alerts, params=None):
        fetcher = mock.Mock()
        quote_fn = lambda _fetcher, ticker: {"price": quote_price, "quote_time": "2026-10-30T20:00:00Z"}
        with mock.patch.object(live, "poll_edgar", return_value=alerts), \
             mock.patch.object(live, "poll_fda_rss", return_value=[]), \
             mock.patch.object(live, "poll_trials", return_value=[]), \
             mock.patch.object(live, "_watchlist", return_value={1234567: ("acme", "ACME")}), \
             mock.patch.object(live, "notify", return_value=None):
            return live.run_once(db_path, params or live.LiveParams(capital=100_000), fetcher=fetcher, quote_fn=quote_fn)

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
            self.assertAlmostEqual(order["qty"], 50.0, places=4)
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
                db.execute(
                    "INSERT INTO positions(ticker, qty, avg_price, opened_at, track_id, last_price,"
                    " market_value, unrealized_pnl, status) VALUES (?,?,?,?,?,?,?,?, 'open')",
                    ("ACME", 50.0, 100.0, datetime.now(timezone.utc).isoformat(), "device", 100.0, 5_000.0, 0.0),
                )
                db.conn.commit()
            result = self._cycle(db_path, 110.0, [])
            self.assertAlmostEqual(result["book"]["equity"], 95_000.0 + 50.0 * 110.0, places=2)
            self.assertGreater(result["book"]["n_positions"], 0)


if __name__ == "__main__":
    unittest.main()
