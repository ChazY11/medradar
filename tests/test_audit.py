"""Offline tests for the data-quality audit."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from medradar.audit import (
    legacy_timestamp_promotions,
    render_audit_markdown,
    run_audit,
)
from medradar.db import DB, make_event_id
from medradar.util import iso, today_utc


class AuditTests(unittest.TestCase):
    def _db(self, tmp: str) -> DB:
        db = DB(Path(tmp) / "audit.sqlite")
        db.upsert_events(
            [
                {
                    "event_id": make_event_id("openfda_device_510k", "510k", "K1"),
                    "source": "openfda_device_510k",
                    "kind": "510k",
                    "event_date": "2026-09-01",
                    "available_at": "2026-09-01",
                    "company_key": "medtronic",
                    "track_id": "spine",
                },
                {
                    "event_id": make_event_id("ctgov", "trial", "NCT1"),
                    "source": "ctgov",
                    "kind": "trial",
                    "event_date": "2026-09-02",
                    "available_at": "2026-09-02",
                    "company_key": None,
                    "track_id": None,
                },
            ]
        )
        db.upsert_prices(
            [
                {"ticker": "MDT", "date": "2026-09-01", "open": 1, "close": 1, "adj_close": 1},
                {"ticker": "MDT", "date": "2026-09-02", "open": 1, "close": 2, "adj_close": 2},
            ]
        )
        return db

    def test_audit_shape_and_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self._db(tmp) as db:
                audit = run_audit(db)
            self.assertEqual(audit["events"]["total"], 2)
            self.assertEqual(audit["events"]["by_kind"]["510k"], 1)
            self.assertEqual(audit["prices"]["tickers"], 1)
            self.assertEqual(audit["prices"]["rows"], 2)
            self.assertIn("checks", audit)
            self.assertIn("events", audit)
            self.assertIn("data_fresh", [check["name"] for check in audit["checks"]])

    def test_company_match_rate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self._db(tmp) as db:
                audit = run_audit(db)
            rate = audit["companies"]["rates_by_kind"]["510k"]
            self.assertEqual(rate["rate"], 1.0)
            trial = audit["companies"]["rates_by_kind"]["trial"]
            self.assertEqual(trial["rate"], 0.0)

    def test_empty_db_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with DB(Path(tmp) / "empty.sqlite") as db:
                audit = run_audit(db)
            self.assertEqual(audit["events"]["total"], 0)
            self.assertEqual(audit["prices"]["tickers"], 0)
            self.assertIn(audit["status"], ("ok", "warn", "fail"))

    def test_markdown_renders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self._db(tmp) as db:
                markdown = render_audit_markdown(run_audit(db))
            self.assertIn("数据质量审计", markdown)
            self.assertIn("| 检查 |", markdown)

    def test_legacy_timestamp_promotions_are_counted_read_only(self) -> None:
        today = iso(today_utc())
        with tempfile.TemporaryDirectory() as tmp:
            with DB(Path(tmp) / "legacy.sqlite") as db:
                db.upsert_events([
                    {
                        # Old-ingest shape: public time inferred from the decision date.
                        "event_id": make_event_id("openfda_device_510k", "510k", "K-legacy"),
                        "source": "openfda_device_510k", "kind": "510k",
                        "event_date": today, "published_at": today,
                        "available_at": today, "timestamp_quality": "date",
                    },
                    {
                        # A real first-posted timestamp is not a demotion candidate.
                        "event_id": make_event_id("ctgov", "trial", "NCT-legacy"),
                        "source": "ctgov", "kind": "trial",
                        "event_date": today, "published_at": today + "T14:00:00Z",
                        "available_at": today + "T14:00:00Z", "timestamp_quality": "datetime",
                    },
                ])
                block = legacy_timestamp_promotions(db)
                audit = run_audit(db)
            self.assertEqual(block["total"], 1)
            self.assertEqual(block["by_source"], {"openfda_device_510k": 1})
            self.assertEqual(audit["legacy_timestamp_promotions"]["total"], 1)
            names = [check["name"] for check in audit["checks"]]
            self.assertIn("legacy_timestamp_promotions_demoted", names)


if __name__ == "__main__":
    unittest.main()
