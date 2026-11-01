"""Offline tests for FDA AdCom collection and domain-aware frontier output."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from medradar.adcom import (
    CALENDAR_URL,
    collect,
    content_current_as_of,
    is_device_meeting,
    parse_calendar,
    parse_document_links,
)
from medradar.config import load_tracks
from medradar.db import DB
from medradar.frontier import build_frontier, render_markdown

FIXTURES = Path(__file__).parent / "fixtures"


class FakeFetcher:
    def __init__(self) -> None:
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "errors": 0}

    def get_text(self, url: str) -> str:
        if url == CALENDAR_URL:
            return (FIXTURES / "adcom_calendar.html").read_text(encoding="utf-8")
        if url.endswith("example-neural"):
            return (FIXTURES / "adcom_detail.html").read_text(encoding="utf-8")
        raise RuntimeError("missing offline detail fixture")


class AdComTests(unittest.TestCase):
    def test_deterministic_calendar_parser(self) -> None:
        html = (FIXTURES / "adcom_calendar.html").read_text(encoding="utf-8")
        rows = parse_calendar(html)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["start_date"], "2026-11-18")
        self.assertEqual(rows[1]["end_date"], "2026-12-04")
        self.assertTrue(is_device_meeting(rows[0]))
        self.assertTrue(is_device_meeting(rows[1]))
        self.assertFalse(is_device_meeting(rows[2]))
        self.assertEqual(content_current_as_of(html), "2026-10-30")
        self.assertEqual(rows[1]["links"][1]["text"], "FDA Briefing Document")

    def test_detail_documents(self) -> None:
        links = parse_document_links(
            (FIXTURES / "adcom_detail.html").read_text(encoding="utf-8"),
            "https://www.fda.gov/advisory-committees/example-neural",
        )
        self.assertEqual(len(links), 3)
        self.assertTrue(all(link["url"].startswith("https://www.fda.gov/media/") for link in links))

    def test_collect_writes_estimated_public_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with DB(Path(tmp) / "radar.sqlite") as db:
                stats = collect(db, FakeFetcher(), months=1200, limit=10)
                self.assertEqual(stats["events"], 2)
                self.assertEqual(stats["documents"], 4)
                rows = db.query("SELECT * FROM events ORDER BY event_date")
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]["kind"], "advisory_committee")
                self.assertEqual(rows[0]["track_id"], "brain_computer")
                self.assertEqual(rows[0]["timestamp_quality"], "estimated")
                self.assertIn("not confidential", rows[0]["payload"])


class FrontierTests(unittest.TestCase):
    def test_registry_has_hierarchical_frontier_domains(self) -> None:
        registry = load_tracks("device")
        self.assertGreaterEqual(len(registry.all()), 50)
        self.assertEqual(registry.match_frontier_text("ECMO and extracorporeal life support"), "ecmo")
        self.assertEqual(registry.match_frontier_text("ctDNA liquid biopsy for MRD"), "ivd_liquid_biopsy")
        self.assertEqual(registry.domain("ivd_mrd")["id"], "ivd")
        self.assertEqual(registry.domain("brain_computer")["id"], "brain_computer")
        self.assertEqual(registry.domain("resuscitation")["id"], "life_support")

    def test_frontier_feed_is_machine_readable_and_honest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with DB(Path(tmp) / "radar.sqlite") as db:
                collect(db, FakeFetcher(), months=1200, limit=10)
                db.upsert_events([{
                    "event_id": "designation-bci", "source": "sec_edgar_8k", "kind": "8k_catalyst",
                    "event_date": "2026-10-20", "published_at": "2026-10-20",
                    "title": "Brain-computer interface receives Breakthrough Device Designation",
                    "payload": {"category": "designation"},
                }, {
                    "event_id": "trial-life-support", "source": "clinicaltrials_gov", "kind": "trial",
                    "event_date": "2026-10-21", "published_at": "2026-10-21",
                    "title": "Trial of high flow nasal oxygen therapy and respiratory support",
                    "payload": {"raw": {"protocolSection": {"armsInterventionsModule": {"interventions": [
                        {"type": "DEVICE", "name": "high flow nasal oxygen therapy"}
                    ]}}}},
                }, {
                    "event_id": "trial-drug-only", "source": "clinicaltrials_gov", "kind": "trial",
                    "event_date": "2026-10-21", "published_at": "2026-10-21",
                    "title": "Drug trial with oxygen therapy as a background condition",
                    "track_id": "t_cardiometabolic",
                    "payload": {"raw": {"protocolSection": {"armsInterventionsModule": {"interventions": [
                        {"type": "DRUG", "name": "investigational medicine"}
                    ]}}}},
                }, {
                    "event_id": "ordinary-approval", "source": "sec_edgar_8k", "kind": "8k_catalyst",
                    "event_date": "2026-10-22", "published_at": "2026-10-22",
                    "title": "Ordinary approval", "payload": {"category": "approval"},
                }])
                payload = build_frontier(db)
                self.assertEqual(payload["summary"]["events"], 4)
                self.assertEqual(payload["summary"]["by_stage"]["advisory_committee"], 2)
                self.assertEqual(payload["summary"]["by_stage"]["designation"], 1)
                self.assertEqual(payload["skipped"]["non_device_trial"], 1)
                domains = {row["domain"] for row in payload["summary"]["by_domain"]}
                self.assertIn("brain_computer", domains)
                self.assertIn("ivd", domains)
                self.assertIn("life_support", domains)
                self.assertFalse(payload["capabilities"]["pending_510k_pma_monitoring"])
                markdown = render_markdown(payload)
                self.assertIn("不宣称监测保密的 pending 510(k)/PMA", markdown)
                self.assertIn("生命支持", markdown)


if __name__ == "__main__":
    unittest.main()
