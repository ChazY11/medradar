"""Synthetic tier — Beisen (zhiye.com) career-portal collector (Phase 4, WP2a).

Everything here runs offline. Nothing here proves that a portal works; that is what
``scripts/collect_recruitment_beisen.py`` and the archived ``source_probe_mindray.json`` /
``collection_mindray.json`` artifacts are for. This file proves the scientific guarantees:

* identity is the posting's own ``Id`` (the GUID the portal uses in its public detail URL),
  never a synthetic id and never the display title;
* ``PostDateInt`` (epoch milliseconds) becomes a UTC instant exactly once, the tenant-local
  rendering is kept verbatim, and their agreement is recorded;
* a missing epoch is *not* converted into a date from the local wall-clock string;
* pagination does not trust the reported ``Count`` to decide when to stop, so an
  under-reported total cannot silently shrink the population;
* a row that cannot be parsed is counted in the run report, not silently dropped;
* robots.txt can actually block the collector.
"""
from __future__ import annotations

import pytest

from medradar.recruitment import records as rec
from medradar.recruitment.beisen import (
    BeisenSource,
    CollectionReport,
    build_observation,
    check_robots,
    collect,
    iter_listings,
    source_time,
)
from medradar.recruitment.politeness import CollectionPolicy

_SOURCE = BeisenSource(company_key="mindray", label="Mindray",
                       base_url="https://example.invalid")


def _row(**over):
    base = {
        "Id": "7fa91977-3d17-4adc-9324-acef1fbbcdfa",
        "JobAdId": 351625350,
        "JobAdName": "销售工程师（体外诊断产品）(J19282)",
        "PostDateInt": 1793778574000,      # 2026-11-04T07:49:34Z
        "PostDate": "2026-11-04T15:49:34",  # same instant in UTC+8
        "JobAdName_en": None,
        "LocNames": ["福建省·福州市"],
        "Category": "社会招聘",
        "CategoryId": "1",
        "Kind": "全职",
        "Status": 1,
        "ChangeDate": "2026-11-04T15:49:34",
        "EndTime": "0001-01-01T00:00:00",
        "Duty": "1、负责所属区域内体外诊断专项产品的销售工作；",
        "Require": "1、本科以上学历，医学检验技术及医学类相关专业背景优先。",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------- time
def test_epoch_is_converted_once_and_rendering_is_kept_verbatim():
    t = source_time(_row())
    assert t["source_posted_at"] == "2026-11-04T07:49:34+00:00"
    assert t["quality"] == rec.QUALITY_SOURCE_DATETIME
    assert t["raw"] == "2026-11-04T15:49:34"
    assert t["consistency"] == "epoch_matches_utc+8_rendering"


def test_missing_epoch_is_not_derived_from_the_local_wall_clock():
    t = source_time(_row(PostDateInt=0))
    assert t["source_posted_at"] is None
    assert t["quality"] == rec.QUALITY_NONE
    assert t["raw"] == "2026-11-04T15:49:34"      # kept, never converted


def test_disagreeing_rendering_is_recorded_as_a_conflict():
    t = source_time(_row(PostDate="2026-11-04T00:00:00"))
    assert t["source_posted_at"] == "2026-11-04T07:49:34+00:00"  # epoch wins
    assert "does_not_match" in (t["consistency"] or "")


# ---------------------------------------------------------------- observation
def test_build_observation_maps_the_portal_fields():
    obs = build_observation(_SOURCE, _row(), fetched_at="2026-11-04T12:00:00+00:00")
    assert obs.posting_id == "7fa91977-3d17-4adc-9324-acef1fbbcdfa"
    assert obs.company_key == "mindray"
    assert obs.source_platform == rec.PLATFORM_BEISEN
    assert obs.job_title == "销售工程师（体外诊断产品）(J19282)"
    assert obs.job_location == "福建省·福州市"
    assert obs.source_url == ("https://example.invalid/social/detail?jobAdId="
                              "7fa91977-3d17-4adc-9324-acef1fbbcdfa")
    assert obs.source_posted_at == "2026-11-04T07:49:34+00:00"
    assert obs.source_posted_quality == rec.QUALITY_SOURCE_DATETIME
    assert obs.source_posted_raw == "2026-11-04T15:49:34"
    assert obs.source_updated_at == "2026-11-04T15:49:34"
    assert obs.collection_status == rec.STATUS_COMPLETE
    assert obs.legal_entity is None                     # never guessed
    assert obs.entity_resolution_status == rec.ENTITY_STATUS_COMPANY_KEY
    assert "负责所属区域" in obs.job_description
    assert "本科以上学历" in obs.job_description
    assert obs.raw["posting_id_kind"] == "Id"
    assert obs.raw["job_ad_id"] == 351625350
    assert obs.raw["post_date_consistency"] == "epoch_matches_utc+8_rendering"
    assert "listing_api" in obs.raw["description_source"]


def test_empty_description_is_not_complete():
    obs = build_observation(_SOURCE, _row(Duty="", Require=""),
                            fetched_at="2026-11-04T12:00:00+00:00")
    assert obs.job_description is None
    assert obs.collection_status == rec.STATUS_NO_DESCRIPTION


def test_a_row_without_identity_is_rejected():
    with pytest.raises(ValueError):
        build_observation(_SOURCE, _row(Id=""), fetched_at="2026-11-04T12:00:00+00:00")


# ------------------------------------------------------------------ pagination
class _FakeFetcher:
    def __init__(self, robots="User-agent: *\nAllow: /\n", pages=None):
        self.robots = robots
        self.pages = pages or {}
        self.calls = []
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "errors": 0}

    def get_text(self, url, params=None, retries=3, backoff=2.0, refresh=False):
        self.calls.append(("GET", url))
        self.stats["requests"] += 1
        return self.robots

    def post_json(self, url, payload, retries=3, backoff=2.0, refresh=False):
        self.calls.append(("POST", url, payload.get("PageIndex")))
        self.stats["requests"] += 1
        return self.pages.get(payload.get("PageIndex"), {"Code": 200, "Count": 0, "Data": []})


def test_pagination_does_not_stop_when_the_reported_total_is_too_small():
    """A source that under-reports ``Count`` must not shrink the collected population."""
    pages = {
        0: {"Code": 200, "Count": 2, "Data": [_row(Id="id-a"), _row(Id="id-b")]},
        1: {"Code": 200, "Count": 0, "Data": [_row(Id="id-c"), _row(Id="id-d")]},
        2: {"Code": 200, "Count": 0, "Data": []},
    }
    fetcher = _FakeFetcher(pages=pages)
    report = CollectionReport(company_key="mindray", source_label="Mindray")
    rows = list(iter_listings(fetcher, _SOURCE, CollectionPolicy(max_postings=10), report))
    assert len(rows) == 4
    assert report.listing_total_reported == 2      # the report states what the source claimed
    assert report.listing_pages == 3


def test_posting_ceiling_is_honoured_and_recorded():
    pages = {0: {"Code": 200, "Count": 50, "Data": [_row(Id=f"id-{i}") for i in range(20)]}}
    fetcher = _FakeFetcher(pages=pages)
    report = CollectionReport(company_key="mindray", source_label="Mindray")
    rows = list(iter_listings(fetcher, _SOURCE, CollectionPolicy(max_postings=5), report))
    assert len(rows) == 5
    assert report.truncated_at_ceiling is True


# ---------------------------------------------------------------------- robots
def test_robots_that_disallows_the_api_blocks_the_run():
    fetcher = _FakeFetcher(robots="User-agent: *\nDisallow: /api/\n")
    with pytest.raises(PermissionError, match="disallows"):
        check_robots(fetcher, _SOURCE, CollectionPolicy())


# --------------------------------------------------------------------- collect
def test_collect_records_unparseable_rows_and_keeps_the_rest():
    pages = {0: {"Code": 200, "Count": 2,
                 "Data": [_row(Id="good-1"), _row(Id="")]}}
    fetcher = _FakeFetcher(pages=pages)
    observations, report = collect(_SOURCE, CollectionPolicy(max_postings=10), fetcher,
                                   limit_postings=10)
    assert [o.posting_id for o in observations] == ["good-1"]
    assert report.rows_parsed == 1
    assert report.rows_failed == 1
    assert report.detail_failures and report.detail_failures[0]["posting_id"] == ""
    assert report.details_requested == 0        # no per-posting detail request was made
