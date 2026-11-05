"""Synthetic tier — recruitment observation contract (Phase 4).

Everything here runs offline. Nothing here proves that a career site works; that is
what `scripts/collect_recruitment.py` and the archived collection manifests are for.
This file proves the *scientific guarantees* hold mechanically:

* a relative "Posted N Days Ago" string is never turned into a date;
* a source date implies a dated quality and vice versa;
* `first_seen_at` is write-once;
* the workday enumeration does not stop after the first page just because the API
  reports ``total`` only once (a real defect found on 2026-11-04 — see the regression
  test at the bottom);
* robots.txt can actually block the collector.
"""
from __future__ import annotations

import json

import pytest

from medradar.recruitment import records as rec
from medradar.recruitment.politeness import CollectionPolicy, parse_robots, robots_allows
from medradar.recruitment.workday import (
    CollectionReport,
    WorkdaySource,
    build_observation,
    check_robots,
    collect,
    html_to_text,
    iter_listings,
    poster_id,
    source_time,
)


# --------------------------------------------------------------------- records
def test_relative_posted_is_never_converted_to_a_date():
    rel = rec.parse_relative_posted("Posted 29 Days Ago")
    assert rel["quality"] == rec.QUALITY_RELATIVE_ONLY
    assert rel["bucket"] == "days"
    assert rel["value_days"] == 29
    # the whole point: no date is produced anywhere in the record
    assert "source_posted_at" not in rel
    detail = source_time({"postedOn": "Posted 29 Days Ago"}, {})
    assert detail["source_posted_at"] is None
    assert detail["quality"] == rec.QUALITY_RELATIVE_ONLY
    assert detail["raw"] == "Posted 29 Days Ago"


def test_today_and_thirty_plus_buckets():
    assert rec.parse_relative_posted("Posted Today")["bucket"] == "same_day"
    assert rec.parse_relative_posted("Posted Yesterday")["bucket"] == "previous_day"
    plus = rec.parse_relative_posted("Posted 30+ Days Ago")
    assert plus["bucket"] == "thirty_plus_days"
    assert plus["value_days"] is None
    assert rec.parse_relative_posted("")["quality"] == rec.QUALITY_NONE
    assert rec.parse_relative_posted("reposted")["quality"] == rec.QUALITY_NONE


def test_absolute_source_dates_keep_their_precision():
    assert source_time({"startDate": "2026-10-06", "postedOn": "Posted 29 Days Ago"}, {}) == {
        "source_posted_at": "2026-10-06",
        "quality": rec.QUALITY_SOURCE_DATE,
        "raw": "Posted 29 Days Ago",
        "field": "startDate",
    }
    dt = source_time({"startDate": "2026-10-06T08:30:00+02:00"}, {})
    assert dt["quality"] == rec.QUALITY_SOURCE_DATETIME
    assert dt["source_posted_at"].startswith("2026-10-06T08:30:00")


def test_content_hash_ignores_whitespace_but_not_meaning():
    a = rec.content_hash(title="R&D Engineer", location="Galway", description="Design catheters.\n\nTest them.")
    b = rec.content_hash(title="R&D  Engineer", location="Galway", description="Design catheters.  Test them.")
    assert a == b
    c = rec.content_hash(title="R&D Engineer", location="Galway", description="Design catheters.")
    assert a != c


def test_observation_validation_rejects_a_contradictory_time_state():
    obs = rec.JobObservation(company_key="medtronic", posting_id="x", source_platform=rec.PLATFORM_WORKDAY,
                             source_url="https://example.invalid/x",
                             source_posted_at="2026-10-06",
                             source_posted_quality=rec.QUALITY_RELATIVE_ONLY)
    with pytest.raises(ValueError, match="quality says it is not a date"):
        obs.validate()
    obs2 = rec.JobObservation(company_key="medtronic", posting_id="x", source_platform=rec.PLATFORM_WORKDAY,
                              source_url="https://example.invalid/x",
                              source_posted_at=None,
                              source_posted_quality=rec.QUALITY_SOURCE_DATE)
    with pytest.raises(ValueError, match="source_posted_at is empty"):
        obs2.validate()


def test_posting_id_is_mandatory_because_a_synthetic_id_is_not_an_identity():
    obs = rec.JobObservation(company_key="medtronic", posting_id="", source_platform=rec.PLATFORM_WORKDAY,
                             source_url="https://example.invalid/x")
    with pytest.raises(ValueError, match="posting_id is required"):
        obs.validate()


def test_first_seen_at_is_write_once():
    obs = rec.JobObservation(company_key="medtronic", posting_id="p1", source_platform=rec.PLATFORM_WORKDAY,
                             source_url="https://example.invalid/p1")
    obs.finalise(fetched_at="2026-11-04T10:00:00+00:00")
    assert obs.first_seen_at == "2026-11-04T10:00:00+00:00"
    # a later observation of the same posting must not move first_seen_at
    obs.finalise(fetched_at="2026-11-05T10:00:00+00:00", first_seen_at="2026-11-04T10:00:00+00:00")
    assert obs.first_seen_at == "2026-11-04T10:00:00+00:00"
    assert obs.fetched_at == "2026-11-05T10:00:00+00:00"


def test_availability_counts_report_the_rate_not_just_the_count():
    a = rec.JobObservation(company_key="medtronic", posting_id="a", source_platform=rec.PLATFORM_WORKDAY,
                           source_url="u", job_title="t", job_description="d", source_posted_at="2026-10-06",
                           source_posted_quality=rec.QUALITY_SOURCE_DATE).finalise(fetched_at="2026-11-04T10:00:00+00:00")
    b = rec.JobObservation(company_key="medtronic", posting_id="b", source_platform=rec.PLATFORM_WORKDAY,
                           source_url="u", job_title="t2", job_description=None,
                           source_posted_quality=rec.QUALITY_RELATIVE_ONLY,
                           collection_status=rec.STATUS_NO_DESCRIPTION).finalise(fetched_at="2026-11-04T10:00:00+00:00")
    counts = rec.availability_counts([a, b])
    assert counts["n"] == 2 and counts["distinct_postings"] == 2
    assert counts["rates"]["description_nonempty"] == 0.5
    assert counts["rates"]["source_date"] == 0.5
    assert counts["by_quality"][rec.QUALITY_RELATIVE_ONLY] == 1


# --------------------------------------------------------------------- robots
def test_robots_longest_match_and_wildcards():
    text = """
    User-agent: *
    Allow: /MedtronicCareers/
    Disallow: /wday/
    Disallow: /private/*.json$
    """
    groups = parse_robots(text)
    assert robots_allows(groups, "/MedtronicCareers/job/x")["allowed"] is True
    assert robots_allows(groups, "/wday/cxs/tenant/site/jobs")["allowed"] is False
    assert robots_allows(groups, "/private/secret.json")["allowed"] is False
    assert robots_allows(groups, "/private/public.html")["allowed"] is True
    # no matching rule means the path is unrestricted, which is not the same as "allowed by a rule"
    assert robots_allows(groups, "/something/else")["rule"] is None


def test_collector_refuses_when_robots_disallows_the_needed_path():
    source = WorkdaySource(company_key="medtronic", tenant="t", site="S",
                           base_url="https://example.invalid", label="T")
    policy = CollectionPolicy()
    fetcher = _FakeFetcher(robots="User-agent: *\nDisallow: /wday/\n")
    with pytest.raises(PermissionError, match="disallows"):
        check_robots(fetcher, source, policy)


# --------------------------------------------------------------------- workday
class _FakeFetcher:
    """Stand-in for medradar.http.Fetcher; records the calls it receives."""

    def __init__(self, robots="User-agent: *\nAllow: /\n", listing_pages=None, detail=None, fail_detail=()):
        self.robots = robots
        self.listing_pages = listing_pages or []
        self.detail = detail or {}
        self.fail_detail = set(fail_detail)
        self.calls = []
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "errors": 0}
        self.max_requests = 1000

    def get_text(self, url, params=None, retries=3, backoff=2.0, refresh=False):
        self.calls.append(("GET", url))
        self.stats["requests"] += 1
        return self.robots

    def post_json(self, url, payload, retries=3, backoff=2.0, refresh=False):
        self.calls.append(("POST", url, payload.get("offset")))
        self.stats["requests"] += 1
        offset = payload.get("offset", 0)
        return self.listing_pages.get(offset, {"total": 0, "jobPostings": []})

    def get_json(self, url, params=None, retries=3, backoff=2.0, refresh=False):
        self.calls.append(("GET", url))
        self.stats["requests"] += 1
        for marker in self.fail_detail:
            if marker in url:
                raise RuntimeError("simulated detail failure")
        return self.detail


def _listing(title, path, req="R1", posted="Posted 2 Days Ago"):
    return {"title": title, "externalPath": path, "locationsText": "Galway, Ireland",
            "postedOn": posted, "bulletFields": [req]}


def _detail(**over):
    base = {
        "id": "opaque-1",
        "jobPostingId": "R-D-Engineer-I_R77874-1",
        "jobReqId": "R77874",
        "title": "R&D Engineer I",
        "location": "Geleen, Limburg, Netherlands",
        "startDate": "2026-11-04",
        "postedOn": "Posted Today",
        "timeType": "Full time",
        "jobDescription": "<p>Design <b>catheter</b> systems.</p><p>Validate them.</p>",
    }
    base.update(over)
    return {"jobPostingInfo": base}


def test_html_to_text_keeps_paragraph_structure_and_drops_tags():
    text = html_to_text("<p>Design <b>catheter</b> systems.</p><p>Validate &amp; test them.</p>")
    assert "catheter" in text and "<" not in text and "&amp;" not in text
    assert "\n" in text


def test_poster_id_prefers_the_opaque_id_over_the_title_bearing_slug():
    pid, kind = poster_id({}, {"id": "opaque-9", "jobPostingId": "Some-Title_R77-1", "jobReqId": "R77"})
    assert (pid, kind) == ("opaque-9", "id")
    pid2, kind2 = poster_id({}, {"jobPostingId": "Some-Title_R77-1", "jobReqId": "R77"})
    assert (pid2, kind2) == ("Some-Title_R77-1", "jobPostingId_slug")


def test_build_observation_unwraps_the_detail_envelope():
    source = WorkdaySource(company_key="medtronic", tenant="t", site="S", base_url="https://example.invalid",
                           label="T")
    obs = build_observation(source, _listing("R&D Engineer I", "/job/x_R1-1"), _detail(),
                            fetched_at="2026-11-04T12:00:00+00:00")
    assert obs.posting_id == "opaque-1"
    assert obs.job_title == "R&D Engineer I"
    assert obs.source_posted_at == "2026-11-04"
    assert obs.source_posted_quality == rec.QUALITY_SOURCE_DATE
    assert obs.collection_status == rec.STATUS_COMPLETE
    assert obs.first_seen_at == "2026-11-04T12:00:00+00:00"
    assert obs.raw["job_req_id"] == "R77874"
    assert obs.entity_resolution_status == rec.ENTITY_STATUS_COMPANY_KEY
    assert obs.legal_entity is None  # never guessed


def test_listing_pagination_does_not_stop_when_total_is_only_reported_once():
    """Regression: a real defect found on 2026-11-04.

    Workday reports ``total`` only on the first page; later pages say ``total: 0`` while
    still returning postings. A collector that trusts ``total`` on every page stops at
    page 1 and reports a company's posting population as one page — the exact
    undercount this test forbids.
    """
    source = WorkdaySource(company_key="medtronic", tenant="t", site="S", base_url="https://example.invalid",
                           label="T")
    pages = {
        0: {"total": 4, "jobPostings": [_listing(f"Job {i}", f"/job/j{i}_R{i}-1", req=f"R{i}") for i in range(2)]},
        2: {"total": 0, "jobPostings": [_listing(f"Job {i}", f"/job/j{i}_R{i}-1", req=f"R{i}") for i in range(2, 4)]},
    }
    fetcher = _FakeFetcher(listing_pages=pages)
    policy = CollectionPolicy(max_postings=10)
    report = CollectionReport(company_key="medtronic", source_label="T")
    rows = list(iter_listings(fetcher, source, policy, report))
    assert len(rows) == 4
    assert report.listing_total_reported == 4
    assert report.listing_pages == 2


def test_detail_failure_is_recorded_as_an_observation_not_dropped():
    source = WorkdaySource(company_key="medtronic", tenant="t", site="S", base_url="https://example.invalid",
                           label="T")
    pages = {0: {"total": 2, "jobPostings": [
        _listing("R&D Engineer I", "/job/a_R1-1", req="R1"),
        _listing("Buyer/Planner", "/job/b_R2-1", req="R2"),
    ]}}
    fetcher = _FakeFetcher(listing_pages=pages, detail=_detail(), fail_detail={"/job/b_R2-1"})
    observations, report = collect(source, CollectionPolicy(max_postings=10), fetcher, limit_postings=10)
    assert len(observations) == 2
    assert report.details_failed == 1 and report.details_ok == 1
    failed = [o for o in observations if o.collection_status == rec.STATUS_DETAIL_FAILED]
    assert len(failed) == 1
    assert failed[0].job_title == "Buyer/Planner"       # the listing row survives the failure
    assert failed[0].job_description is None            # and is not confused with "no description"
    assert report.detail_failures[0]["external_path"] == "/job/b_R2-1"


def test_a_posting_without_any_source_time_is_not_given_one():
    source = WorkdaySource(company_key="medtronic", tenant="t", site="S", base_url="https://example.invalid",
                           label="T")
    obs = build_observation(source, _listing("Job X", "/job/x_R9-1", posted=None),
                            _detail(startDate=None, postedOn=None),
                            fetched_at="2026-11-04T12:00:00+00:00")
    assert obs.source_posted_at is None
    assert obs.source_posted_quality == rec.QUALITY_NONE
    assert obs.first_seen_at == "2026-11-04T12:00:00+00:00"


def test_serialisation_round_trip_preserves_time_semantics(tmp_path):
    source = WorkdaySource(company_key="medtronic", tenant="t", site="S", base_url="https://example.invalid",
                           label="T")
    obs = build_observation(source, _listing("Job X", "/job/x_R9-1", posted="Posted 5 Days Ago"),
                            _detail(startDate=None), fetched_at="2026-11-04T12:00:00+00:00")
    payload = obs.to_dict()
    path = tmp_path / "obs.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    loaded = rec.JobObservation.from_dict(json.loads(path.read_text(encoding="utf-8")))
    assert loaded.source_posted_at is None
    assert loaded.source_posted_quality == rec.QUALITY_RELATIVE_ONLY
    assert loaded.first_seen_at == "2026-11-04T12:00:00+00:00"
    assert loaded.obs_id == obs.obs_id
