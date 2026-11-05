"""Synthetic tier — Phenom career-site collector (Phase 4, WP2a).

Everything here runs offline. Nothing here proves that a career site works; that is what
``scripts/collect_recruitment_phenom.py`` and the archived ``source_probe_*.json`` /
``collection_*.json`` artifacts are for. This file proves the *scientific guarantees* hold
mechanically:

* a posting's identity comes from the source's own ``identifier.value``, not from the
  title-bearing URL slug;
* ``datePosted`` keeps the precision the source published (date vs timestamp), and a
  midnight timestamp is flagged as date precision rather than silently shifted;
* an escaped-HTML description becomes readable text, never raw tags;
* a posting page that returns 410/404 becomes a recorded ``DETAIL_FAILED`` observation,
  not a silent drop and not "this posting has no description";
* a real robots.txt that disallows the sitemap path blocks the run;
* a host that publishes no robots.txt is recorded as such (not assumed away), and the
  collection is allowed only through the explicit RFC 9309 "unavailable" path;
* sitemap postings are ordered by ``lastmod`` so a bounded run sees active postings first.
"""
from __future__ import annotations

import json

import pytest

from medradar.recruitment import records as rec
from medradar.recruitment.phenom import (
    CollectionReport,
    PhenomSource,
    build_observation,
    check_robots,
    collect,
    description_to_text,
    find_jobposting,
    interpret_robots,
    iter_sitemap_job_urls,
    jobposting_identifier,
    jobposting_locations,
    posting_id_from_url,
    source_time_from_jobposting,
)
from medradar.recruitment.politeness import CollectionPolicy

_GEHC = PhenomSource(company_key="ge_healthcare", label="GE HealthCare",
                     base_url="https://example.invalid", locale_root="/global/en")
_PHILIPS = PhenomSource(company_key="philips", label="Philips",
                        base_url="https://example.invalid", locale_root="/global/en",
                        robots_policy="unavailable_allowed")


def _page(jobposting: dict, extra_nodes: list | None = None) -> str:
    blocks = [{"@context": "https://schema.org", "@type": "WebPage", "name": "careers"}]
    blocks.append(jobposting)
    blocks.extend(extra_nodes or [])
    scripts = "\n".join(
        f'<script type="application/ld+json">{json.dumps(b)}</script>' for b in blocks)
    return f"<!doctype html><html><head>{scripts}</head><body>page</body></html>"


def _jobposting(**over):
    base = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "identifier": {"@type": "PropertyValue", "name": "GE HEALTHCARE", "value": "R4045928"},
        "title": "Algorithm Software Engineer",
        "datePosted": "2026-09-07",
        "description": ("&lt;h1&gt;Job Description Summary&lt;/h1&gt;"
                        "&lt;p&gt;Build &amp;amp; test image reconstruction software.&lt;/p&gt;"),
        "jobLocation": [{"@type": "Place", "address": {
            "@type": "PostalAddress", "addressLocality": "Haifa",
            "addressRegion": "Haifa District", "addressCountry": "Israel"}}],
        "hiringOrganization": {"@type": "Organization", "name": "GE HEALTHCARE"},
        "employmentType": ["OTHER"],
    }
    base.update(over)
    return base


# ------------------------------------------------------------------- json-ld
def test_find_jobposting_ignores_non_posting_nodes():
    page = _page(_jobposting(), extra_nodes=[{"@type": "BreadcrumbList"}])
    jp = find_jobposting(page)
    assert jp is not None and jp["@type"] == "JobPosting"
    assert find_jobposting("<html>no json-ld here</html>") is None


def test_identity_prefers_the_source_identifier_over_the_title_bearing_slug():
    jp = _jobposting()
    value, name, field = jobposting_identifier(jp)
    assert (value, name, field) == ("R4045928", "GE HEALTHCARE", "identifier.value")
    # the URL slug is only a fallback and is never the identity when identifier is present
    assert posting_id_from_url(
        "https://careers.gehealthcare.com/global/en/job/GEVGHLGLOBALR4045928EXTERNALENGLOBAL/Algorithm-Software-Engineer"
    ) == "GEVGHLGLOBALR4045928EXTERNALENGLOBAL"
    assert posting_id_from_url(
        "https://www.careers.philips.com/global/en/job/594302/People-Operations-Coordinator") == "594302"


def test_description_escaped_html_becomes_text_not_tags():
    jp = _jobposting()
    text = description_to_text(jp["description"])
    assert "<h1>" not in text and "&lt;" not in text
    assert "Job Description Summary" in text
    assert "Build & test image reconstruction software." in text


# ---------------------------------------------------------------------- time
def test_plain_date_keeps_date_precision():
    t = source_time_from_jobposting(_jobposting())
    assert t["source_posted_at"] == "2026-09-07"
    assert t["quality"] == rec.QUALITY_SOURCE_DATE
    assert t["field"] == "datePosted"


def test_midnight_timestamp_is_kept_verbatim_and_flagged_not_shifted():
    jp = _jobposting(datePosted="2026-11-04T00:00:00.000+0000")
    t = source_time_from_jobposting(jp)
    assert t["quality"] == rec.QUALITY_SOURCE_DATETIME
    assert t["source_posted_at"] == "2026-11-04T00:00:00.000+0000"  # verbatim
    assert "midnight" in (t["raw_note"] or "")


def test_missing_date_is_not_invented():
    t = source_time_from_jobposting(_jobposting(datePosted=None))
    assert t["source_posted_at"] is None
    assert t["quality"] == rec.QUALITY_NONE


# ---------------------------------------------------------------- observation
def test_build_observation_maps_the_source_fields():
    obs = build_observation(_GEHC, _jobposting(),
                            "https://careers.gehealthcare.com/global/en/job/x/Algorithm",
                            fetched_at="2026-11-04T12:00:00+00:00")
    assert obs.posting_id == "R4045928"
    assert obs.company_key == "ge_healthcare"
    assert obs.source_platform == rec.PLATFORM_PHENOM
    assert obs.job_title == "Algorithm Software Engineer"
    assert obs.job_location == "Haifa, Haifa District, Israel"
    assert obs.additional_locations == []
    assert obs.source_posted_at == "2026-09-07"
    assert obs.source_posted_quality == rec.QUALITY_SOURCE_DATE
    assert obs.collection_status == rec.STATUS_COMPLETE
    assert obs.legal_entity is None                      # never guessed
    assert obs.entity_resolution_status == rec.ENTITY_STATUS_COMPANY_KEY
    assert obs.raw["hiring_organization"] == "GE HEALTHCARE"   # preserved as a claim
    assert obs.raw["posting_id_kind"] == "identifier.value"
    assert obs.first_seen_at == "2026-11-04T12:00:00+00:00"


def test_multiple_locations_are_separated():
    jp = _jobposting(jobLocation=[
        {"@type": "Place", "address": {"addressLocality": "Krakow", "addressCountry": "Poland"}},
        {"@type": "Place", "address": {"addressLocality": "Warsaw", "addressCountry": "Poland"}},
    ])
    primary, additional, _ = jobposting_locations(jp)
    assert primary == "Krakow, Poland"
    assert additional == ["Warsaw, Poland"]


def test_posting_without_description_is_not_complete():
    jp = _jobposting(description="")
    obs = build_observation(_GEHC, jp, "https://x/job/1/slug",
                            fetched_at="2026-11-04T12:00:00+00:00")
    assert obs.job_description == ""
    assert obs.collection_status == rec.STATUS_NO_DESCRIPTION


# ------------------------------------------------------------------- sitemaps
_SITEMAP_INDEX = """<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.invalid/global/en/sitemap1.xml</loc></sitemap>
</sitemapindex>"""

_SITEMAP = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.invalid/global/en/job/OLD/old-title</loc>
       <lastmod>2025-01-01T00:00:00+00:00</lastmod></url>
  <url><loc>https://example.invalid/global/en/job/NEW/new-title</loc>
       <lastmod>2026-11-04T00:00:00+00:00</lastmod></url>
  <url><loc>https://example.invalid/global/en/culture</loc></url>
</urlset>"""


class _FakeFetcher:
    """Stand-in for medradar.http.Fetcher; serves canned bodies by URL fragment."""

    def __init__(self, robots="User-agent: *\nAllow: /\n", pages=None, fail_urls=()):
        self.robots = robots
        self.pages = pages or {}
        self.fail_urls = set(fail_urls)
        self.calls = []
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "errors": 0}

    def get_text(self, url, params=None, retries=3, backoff=2.0, refresh=False):
        self.calls.append(("GET", url))
        self.stats["requests"] += 1
        if url.endswith("/robots.txt") or "robots.txt" in url:
            return self.robots
        for fragment, body in self.pages.items():
            if fragment in url:
                return body
        raise AssertionError(f"unexpected URL in fake fetcher: {url}")


def test_sitemap_job_urls_are_ordered_by_lastmod():
    fetcher = _FakeFetcher(pages={"/sitemap_index.xml": _SITEMAP_INDEX,
                                  "/sitemap1.xml": _SITEMAP})
    report = CollectionReport(company_key="ge_healthcare", source_label="GE HealthCare")
    rows = list(iter_sitemap_job_urls(fetcher, _GEHC, CollectionPolicy(), report))
    assert [r["url"].rsplit("/", 1)[-1] for r in rows] == ["new-title", "old-title"]
    assert report.job_urls_seen == 2
    assert report.sitemap_urls_seen == 3          # includes the non-posting culture URL


# ---------------------------------------------------------------------- robots
def test_robots_that_disallows_the_sitemap_blocks_the_run():
    robots = "User-agent: *\nDisallow: /global/en/sitemap_index.xml\n"
    fetcher = _FakeFetcher(robots=robots)
    with pytest.raises(PermissionError, match="disallows"):
        check_robots(fetcher, _GEHC, CollectionPolicy())


def test_missing_robots_is_recorded_and_rfc9309_applied_explicitly():
    html_shell = "<!doctype html><html><head><title>Careers</title></head></html>"
    policy = CollectionPolicy()
    interpretation = interpret_robots(_PHILIPS, 200, html_shell, policy)
    assert interpretation["published"] is False
    assert "RFC 9309" in interpretation["basis"]
    assert "SPA HTML shell" in interpretation["basis"]
    # the evidence next to the data says exactly what the host answered
    evidence = policy.robots_evidence[_PHILIPS.host]
    assert evidence["status"] == 200
    assert evidence["is_robots_file"] is False
    assert "SPA HTML shell" in interpretation["basis"] or "<!doctype" in evidence["raw_head"]


def test_required_robots_policy_refuses_a_host_that_publishes_none():
    html_shell = "<!doctype html><html></html>"
    with pytest.raises(PermissionError, match="refusing to collect"):
        interpret_robots(_GEHC, 200, html_shell, CollectionPolicy())


# ------------------------------------------------------------------- collect
def test_collect_keeps_a_410_posting_as_detail_failed():
    from medradar.http import HttpError

    index = _SITEMAP_INDEX.replace("example.invalid", "careers.gehealthcare.com")
    sitemap = _SITEMAP.replace("example.invalid", "careers.gehealthcare.com")
    good_url = "https://careers.gehealthcare.com/global/en/job/NEW/new-title"

    class _FailingFetcher(_FakeFetcher):
        def get_text(self, url, params=None, retries=3, backoff=2.0, refresh=False):
            if url == good_url:
                self.calls.append(("GET", url))
                self.stats["requests"] += 1
                raise HttpError(410, url, "gone")
            return super().get_text(url, params, retries, backoff, refresh)

    fetcher = _FailingFetcher(pages={"/sitemap_index.xml": index, "/sitemap1.xml": sitemap,
                                     "/job/OLD/": _page(_jobposting())})
    source = PhenomSource(company_key="ge_healthcare", label="GE HealthCare",
                          base_url="https://careers.gehealthcare.com", locale_root="/global/en")
    observations, report = collect(source, CollectionPolicy(max_postings=5), fetcher,
                                   limit_postings=5)
    statuses = {(o.source_url.rsplit("/", 1)[-1], o.collection_status) for o in observations}
    assert ("new-title", rec.STATUS_DETAIL_FAILED) in statuses
    assert report.details_failed == 1 and report.details_ok == 1
    assert report.detail_failures and report.detail_failures[0]["http_status"] == 410
    # the failed observation still carries a source-derived identity and no invented date
    failed = [o for o in observations if o.collection_status == rec.STATUS_DETAIL_FAILED][0]
    assert failed.posting_id is not None
    assert failed.source_posted_at is None
    assert failed.source_posted_quality == rec.QUALITY_NONE
    assert failed.job_description is None      # not confused with "no description"


def test_collect_builds_complete_observations_from_sitemap_and_pages():
    index = _SITEMAP_INDEX.replace("example.invalid", "careers.gehealthcare.com")
    sitemap = _SITEMAP.replace("example.invalid", "careers.gehealthcare.com")
    page = _page(_jobposting())
    fetcher = _FakeFetcher(pages={"/sitemap_index.xml": index, "/sitemap1.xml": sitemap,
                                  "/job/": page})
    source = PhenomSource(company_key="ge_healthcare", label="GE HealthCare",
                          base_url="https://careers.gehealthcare.com", locale_root="/global/en")
    observations, report = collect(source, CollectionPolicy(max_postings=5), fetcher,
                                   limit_postings=5)
    assert len(observations) == 2
    assert all(o.collection_status == rec.STATUS_COMPLETE for o in observations)
    assert all(o.posting_id == "R4045928" for o in observations)
    assert report.details_ok == 2 and report.details_failed == 0
    assert report.robots["careers.gehealthcare.com"]["is_robots_file"] is True
