"""Workday career-site collector (Medtronic, and any other Workday-hosted site).

What this reads, and why it is lawful
-------------------------------------
A Workday career site is a public web application. Its own front end loads postings
from two public, unauthenticated endpoints on the same host:

  * ``POST /wday/cxs/{tenant}/{site}/jobs``            — the paged listing
  * ``GET  /wday/cxs/{tenant}/{site}{externalPath}``   — one posting's detail

Both are the requests a browser makes when a human clicks through the site; no
login, no captcha, no access control is bypassed, and the pages themselves are
published for indexing (``robots.txt`` advertises the siteMap, and each posting
page carries schema.org ``JobPosting`` JSON-LD). The collector additionally:

  * fetches ``robots.txt`` first and refuses the run if the path is disallowed
    (``medradar.recruitment.politeness``);
  * throttles per host, caps requests and postings per run;
  * never touches candidate data — only the employer's public advert.

`Fetcher` (``medradar.http``) supplies the polite retry/caching layer, so a
re-run replays from cache instead of hammering the source, and an interrupted run
can resume without duplicating requests.
"""
from __future__ import annotations

import html as html_mod
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from ..http import Fetcher
from . import records as rec
from .politeness import CollectionPolicy, DEFAULT_UA

_FIXED_TZ = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_BLOCK = re.compile(r"</?(?:p|div|br|li|tr|h[1-6]|ul|ol|table|section)\b[^>]*>", re.I)
_ANY_TAG = re.compile(r"<[^>]+>")


def html_to_text(raw: str | None) -> str:
    """Extract readable text from a job-description HTML fragment.

    Block-level tags become newlines (paragraph structure matters for quoting
    evidence later); every other tag is dropped; entities are unescaped. The
    output is whitespace-normalised but keeps paragraph breaks.
    """
    if not raw:
        return ""
    text = _TAG.sub(" ", raw)
    text = _BLOCK.sub("\n", text)
    text = _ANY_TAG.sub("", text)
    text = html_mod.unescape(text)
    return rec.normalise_text(text)


@dataclass(frozen=True)
class WorkdaySource:
    company_key: str
    tenant: str
    site: str
    base_url: str
    label: str
    #: the legal entity, when the career site itself states it (usually it does not)
    legal_entity: str | None = None

    @property
    def host(self) -> str:
        return self.base_url.split("://", 1)[-1].rstrip("/")

    @property
    def listing_url(self) -> str:
        return f"{self.base_url}/wday/cxs/{self.tenant}/{self.site}/jobs"

    def detail_url(self, external_path: str) -> str:
        path = external_path if external_path.startswith("/") else "/" + external_path
        return f"{self.base_url}/wday/cxs/{self.tenant}/{self.site}{path}"

    def page_url(self, external_path: str) -> str:
        return f"{self.base_url}/{self.site}{external_path}"


#: Sources identified by the Phase-4 source-discovery probe (see docs/SOURCE_DISCOVERY.md).
SOURCES: dict[str, WorkdaySource] = {
    "medtronic": WorkdaySource(
        company_key="medtronic",
        tenant="medtronic",
        site="MedtronicCareers",
        base_url="https://medtronic.wd1.myworkdayjobs.com",
        label="Medtronic",
    ),
}


# --------------------------------------------------------------------- collection
@dataclass
class CollectionReport:
    company_key: str
    source_label: str
    started_at: str = ""
    finished_at: str = ""
    listing_total_reported: int | None = None
    listing_pages: int = 0
    listings_seen: int = 0
    details_requested: int = 0
    details_ok: int = 0
    details_failed: int = 0
    detail_failures: list[dict[str, str]] = None  # type: ignore[assignment]
    truncated_at_ceiling: bool = False
    duplicate_listing_rows: int = 0
    robots: dict[str, Any] = None  # type: ignore[assignment]
    request_stats: dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.detail_failures = self.detail_failures or []
        self.robots = self.robots or {}
        self.request_stats = self.request_stats or {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "company_key": self.company_key,
            "source_label": self.source_label,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "listing_total_reported": self.listing_total_reported,
            "listing_pages": self.listing_pages,
            "listings_seen": self.listings_seen,
            "details_requested": self.details_requested,
            "details_ok": self.details_ok,
            "details_failed": self.details_failed,
            "detail_failures": self.detail_failures[:50],
            "truncated_at_ceiling": self.truncated_at_ceiling,
            "duplicate_listing_rows": self.duplicate_listing_rows,
            "robots": {k: {"robots_url": v.get("robots_url"), "status": v.get("status"),
                           "n_groups": v.get("n_groups")} for k, v in self.robots.items()},
            "request_stats": self.request_stats,
            "collector_version": rec.COLLECTOR_VERSION,
        }


def check_robots(fetcher: Fetcher, source: WorkdaySource, policy: CollectionPolicy) -> dict[str, Any]:
    """Fetch and store robots.txt, then assert that this source's paths are allowed."""
    robots_url = f"{source.base_url}/robots.txt"
    status: int | None = None
    text = ""
    try:
        text = fetcher.get_text(robots_url)
        status = 200
    except Exception as exc:  # noqa: BLE001 - a robots fetch failure blocks collection, it is reported
        status = getattr(exc, "status", None)
        text = ""
    evidence = policy.record_robots(robots_url, status, text)
    if status != 200:
        raise PermissionError(f"robots.txt unreadable for {source.host} (status={status}); refusing to collect")
    listing_path = f"/wday/cxs/{source.tenant}/{source.site}/jobs"
    policy.assert_allowed(robots_url, listing_path)
    # the detail endpoint shares the same /wday/cxs/ prefix as the listing
    return evidence


def iter_listings(fetcher: Fetcher, source: WorkdaySource, policy: CollectionPolicy,
                  report: CollectionReport, *, page_size: int = 20,
                  refresh: bool = True) -> Iterable[dict[str, Any]]:
    """Yield listing rows until the total is exhausted or the posting ceiling is hit.

    Workday quirk measured on 2026-11-04: the paged listing reports ``total`` **only
    on the first page** (offset=0); later pages carry ``total: 0`` while still
    returning 20 postings each, and ``limit`` above 20 is rejected with HTTP 400.
    Trusting ``total`` on every page would stop the enumeration after one page and
    silently undercount the population — the exact failure mode that would make a
    company look like it posts fewer technical roles than it does.
    """
    offset = 0
    seen = 0
    declared_total: int | None = None
    while True:
        payload = {"appliedFacets": {}, "limit": page_size, "offset": offset}
        data = fetcher.post_json(source.listing_url, payload, refresh=refresh)
        report.listing_pages += 1
        posts = data.get("jobPostings") or []
        total = data.get("total")
        if offset == 0 and isinstance(total, int) and total > 0:
            declared_total = total
            report.listing_total_reported = total
        if not posts:
            break
        for post in posts:
            if seen >= policy.max_postings:
                report.truncated_at_ceiling = True
                return
            yield post
            seen += 1
            report.listings_seen += 1
        offset += len(posts)
        if declared_total is not None and offset >= declared_total:
            break
        if report.listing_pages > 200:  # safety valve, recorded rather than silent
            report.truncated_at_ceiling = True
            return


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if mapping.get(key) not in (None, ""):
            return mapping[key]
    return None


def source_time(detail: dict[str, Any], listing: dict[str, Any]) -> dict[str, Any]:
    """Derive the source publication time, with its quality, without inventing one.

    Workday detail exposes ``startDate`` (an ISO date, the posting's start date) and
    ``postedOn`` (a *relative* string such as "Posted 29 Days Ago"). The absolute
    field wins; the relative string is retained verbatim as an ordering hint. If the
    absolute field is missing, the posting has no source date — not an estimated one.
    """
    start = detail.get("startDate")
    posted_on = detail.get("postedOn") or listing.get("postedOn")
    if isinstance(start, str) and _FIXED_TZ.match(start):
        return {"source_posted_at": start, "quality": rec.QUALITY_SOURCE_DATETIME,
                "raw": str(posted_on or start), "field": "startDate"}
    if isinstance(start, str) and _ISO_DATE.match(start):
        return {"source_posted_at": start, "quality": rec.QUALITY_SOURCE_DATE,
                "raw": str(posted_on or start), "field": "startDate"}
    rel = rec.parse_relative_posted(posted_on)
    quality = rel["quality"]
    return {"source_posted_at": None, "quality": quality, "raw": posted_on,
            "field": None if quality == rec.QUALITY_NONE else "postedOn_relative",
            "relative_bucket": rel.get("bucket"), "relative_days": rel.get("value_days")}


def poster_id(listing: dict[str, Any], detail: dict[str, Any]) -> tuple[str, str]:
    """The source's own stable posting identity, and which field supplied it.

    Identity is the *opaque* id, not the URL slug, because a Workday slug embeds the
    job title (``R-D-Engineer-I_R77874-1``): retitling the same posting changes the
    slug, and using the slug as identity would report an edit as a brand-new job.
    ``jobPostingId`` (the slug) and ``jobReqId`` (the requisition) are kept as
    *secondary* keys for duplicate detection, not as identity.
    """
    opaque = detail.get("id")
    if isinstance(opaque, str) and opaque.strip():
        return opaque.strip(), "id"
    slug = detail.get("jobPostingId")
    if isinstance(slug, str) and slug.strip():
        return slug.strip(), "jobPostingId_slug"
    req = detail.get("jobReqId") or (listing.get("bulletFields") or [None])[0]
    if req:
        return str(req), "jobReqId"
    external_path = listing.get("externalPath") or ""
    return str(external_path), "externalPath_slug"


def build_observation(source: WorkdaySource, listing: dict[str, Any], detail: dict[str, Any],
                      *, fetched_at: str) -> rec.JobObservation:
    # The detail endpoint nests the posting under `jobPostingInfo` (with a sibling
    # `hiringOrganization`); accept either shape so a provider change cannot be
    # silently read as "no description".
    wrapper = detail or {}
    info = wrapper.get("jobPostingInfo") if isinstance(wrapper.get("jobPostingInfo"), dict) else wrapper
    detail = info
    external_path = listing.get("externalPath") or detail.get("externalPath") or ""
    pid, identity_kind = poster_id(listing, detail)
    if not pid:
        pid = external_path
        identity_kind = "externalPath_slug"
    title = _first(detail, "title") or _first(listing, "title")
    description = html_to_text(detail.get("jobDescription"))
    location = _first(detail, "location") or _first(listing, "locationsText")
    t = source_time(detail, listing)
    status = rec.STATUS_COMPLETE if description else rec.STATUS_NO_DESCRIPTION
    obs = rec.JobObservation(
        company_key=source.company_key,
        legal_entity=source.legal_entity,
        entity_resolution_status=(rec.ENTITY_STATUS_CANONICAL if source.legal_entity
                                  else rec.ENTITY_STATUS_COMPANY_KEY),
        entity_resolution_note=(
            None if source.legal_entity else
            "career site states the corporate brand only; the registered legal entity that employs "
            "the role is not published on the posting"
        ),
        posting_id=pid,
        job_title=title,
        job_description=description,
        job_location=location,
        additional_locations=[str(x) for x in (detail.get("additionalLocations") or [])][:20],
        source_url=source.page_url(external_path) if external_path else source.base_url,
        source_platform=rec.PLATFORM_WORKDAY,
        source_posted_at=t["source_posted_at"],
        source_posted_quality=t["quality"],
        source_posted_raw=t.get("raw"),
        source_updated_at=None,
        first_seen_at=fetched_at,
        fetched_at=fetched_at,
        collection_status=status,
        raw={
            "external_path": external_path,
            "job_req_id": detail.get("jobReqId"),
            "job_posting_id_slug": detail.get("jobPostingId"),
            "opaque_posting_id": detail.get("id"),
            "posting_id_kind": identity_kind,
            "posted_on_relative": detail.get("postedOn") or listing.get("postedOn"),
            "time_type": detail.get("timeType"),
            "remote_type": detail.get("remoteType"),
            "start_date_raw": detail.get("startDate"),
            "job_posting_end_date": detail.get("jobPostingEndDateAsText") or detail.get("endDate"),
            "external_url": detail.get("externalUrl"),
            "source_time_field": t.get("field"),
            "listing_locations_text": listing.get("locationsText"),
            "description_chars_html": len(detail.get("jobDescription") or ""),
            "detail_fields_present": sorted(k for k, v in detail.items() if v not in (None, "", [])),
        },
    )
    return obs.finalise(fetched_at=fetched_at)


def collect(source: WorkdaySource, policy: CollectionPolicy, fetcher: Fetcher,
            *, limit_postings: int | None = None,
            refresh: bool = True) -> tuple[list[rec.JobObservation], CollectionReport]:
    """Collect one bounded snapshot of a Workday careers site.

    A posting whose detail request fails is *kept* as a listing-only observation with
    ``DETAIL_FAILED``; dropping it would turn a fetch failure into "no such job".
    """
    report = CollectionReport(company_key=source.company_key, source_label=source.label,
                              started_at=rec.utc_now_iso())
    check_robots(fetcher, source, policy)
    report.robots = policy.robots_evidence
    ceiling = limit_postings if limit_postings is not None else policy.max_postings
    old_max = policy.max_postings
    policy.max_postings = ceiling
    observations: list[rec.JobObservation] = []
    try:
        for listing in iter_listings(fetcher, source, policy, report, refresh=refresh):
            fetched_at = rec.utc_now_iso()
            external_path = listing.get("externalPath") or ""
            report.details_requested += 1
            try:
                detail = fetcher.get_json(source.detail_url(external_path), refresh=refresh) if external_path else {}
                report.details_ok += 1
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                report.details_failed += 1
                report.detail_failures.append({"external_path": external_path,
                                               "error": f"{type(exc).__name__}: {exc}"[:300]})
                detail = {}
                status = rec.STATUS_DETAIL_FAILED
            if detail:
                obs = build_observation(source, listing, detail, fetched_at=fetched_at)
            else:
                obs = rec.JobObservation(
                    company_key=source.company_key,
                    posting_id=(listing.get("bulletFields") or [""])[0] or external_path,
                    source_platform=rec.PLATFORM_WORKDAY,
                    source_url=source.page_url(external_path),
                    job_title=listing.get("title"),
                    job_location=listing.get("locationsText"),
                    source_posted_at=None,
                    source_posted_quality=rec.QUALITY_RELATIVE_ONLY if listing.get("postedOn") else rec.QUALITY_NONE,
                    source_posted_raw=listing.get("postedOn"),
                    first_seen_at=fetched_at,
                    collection_status=status,
                    entity_resolution_status=rec.ENTITY_STATUS_COMPANY_KEY,
                    entity_resolution_note="detail fetch failed; company-level attribution only",
                    raw={"external_path": external_path, "detail_fetch_failed": True,
                         "posted_on_relative": listing.get("postedOn")},
                ).finalise(fetched_at=fetched_at)
            observations.append(obs)
    finally:
        policy.max_postings = old_max
    report.finished_at = rec.utc_now_iso()
    report.request_stats = dict(getattr(fetcher, "stats", {}))
    # Offset pagination is not a snapshot: if the source changes mid-run a posting can
    # be returned twice (or missed). Duplicates are counted here and resolved by the
    # identity rules, never silently dropped at collection time.
    ids = [o.obs_id for o in observations]
    report.duplicate_listing_rows = len(ids) - len(set(ids))
    return observations, report
