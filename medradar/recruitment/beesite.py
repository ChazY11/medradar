"""Beesite career-portal collector (Dräger's official e-recruitment portal).

What this reads, and why it is lawful
-------------------------------------
Dräger's job board is a **Beesite** front end:
``erecruitment.draeger.com`` (posting pages with schema.org ``JobPosting`` JSON-LD) in
front of a public search API on ``draeger-beesite-production-gjb.app.beesite.de``. The
portal's own JavaScript calls that search endpoint; this collector uses only:

  * ``GET  /search/?data=<url-encoded JSON>``   — current postings as JSON (id, title,
    publication date, employing organisation, location, category). No auth;
  * ``GET  https://erecruitment.draeger.com/index.php?ac=jobad&id=<id>`` — the public
    posting page, whose JSON-LD carries the full description and ``datePosted``.

No login, captcha, paywall or access control is touched; both hosts answer scripted
unauthenticated requests normally. The corporate marketing host (``www.draeger.com``) is
Akamai-bot-managed and is deliberately **not** used — it is not the job board.

Robots
------
``erecruitment.draeger.com/robots.txt`` is a bare ``Sitemap:`` line with no rules. The
Beesite host publishes **no** ``robots.txt`` at all (``GET /robots.txt`` → HTTP 404 with a
JSON error body); RFC 9309 §2.3.1.3 treats an unavailable robots.txt as unrestricted. Both
answers are recorded verbatim in the run report, and the collector asserts the exact paths
it reads before the first data request.

Identity / time / description semantics
---------------------------------------
* Identity is the portal's own posting id (the ``id`` in the public job-ad URL); the
  JSON-LD ``identifier.value`` (``J000019717``) is kept as an alternate key.
* ``datePosted`` (JSON-LD, plain ISO date) is the source's publication time. When the
  posting page cannot be read, the search API's ``PublicationStartDate`` is kept instead —
  also a plain date from the source, never an estimate.
* Both fields exist: identity/date/title/entity/location come from the search API,
  description from the posting page; a page failure is recorded as ``DETAIL_FAILED`` with
  the listing fields intact, never dropped and never written as "no description".
* ``ParentOrganizationName`` is stated by the source per posting (``Drägerwerk AG & Co.
  KGaA``, ``Dräger Safety AG & Co. KGaA``, …). It is recorded as ``legal_entity`` but left
  at ``COMPANY_KEY_ONLY`` because it has not been resolved to a universe entity key.
"""
from __future__ import annotations

import html as html_mod
import json
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any

from ..http import Fetcher, HttpError
from . import records as rec
from .phenom import (
    description_to_text,
    find_jobposting,
    jobposting_identifier,
    jobposting_locations,
    source_time_from_jobposting,
)
from .politeness import CollectionPolicy

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: fields requested from the search API (the same names the portal's own front end asks for)
LIST_FIELDS = [
    "ID", "PositionTitle", "PositionURI", "PositionLocation.CountryName",
    "PositionLocation.CountrySubDivisionName", "PositionLocation.CityName",
    "JobCategory.Name", "CareerLevel.Name", "PositionSchedule.Name", "MobileWork.Name",
    "PositionIndustry.Name", "PublicationStartDate", "ParentOrganizationName",
    "OrganizationShortName",
]


@dataclass(frozen=True)
class BeesiteSource:
    company_key: str
    label: str
    search_base: str        # e.g. https://draeger-beesite-production-gjb.app.beesite.de
    portal_base: str        # e.g. https://erecruitment.draeger.com
    channel: str = "12"     # the employer's publication channel in the Beesite tenant
    language: str = "DE"
    #: the legal entity, when the portal states no per-posting organisation (it does here)
    legal_entity: str | None = None

    @property
    def search_path(self) -> str:
        return "/search/"

    def search_url(self, limit: int) -> str:
        payload = {
            "LanguageCode": self.language,
            "SearchParameters": {
                "CountItem": max(1, min(limit, 500)),
                "Sort": [{"Criterion": "PublicationStartDate", "Direction": "DESC"}],
                "MatchedObjectDescriptor": list(LIST_FIELDS),
            },
            "SearchCriteria": [{"CriterionName": "PublicationChannel.Code",
                                "CriterionValue": [self.channel]}],
        }
        return (f"{self.search_base}{self.search_path}?data="
                + urllib.parse.quote(json.dumps(payload, separators=(",", ":"))))

    def jobad_url(self, posting_id: str) -> str:
        return f"{self.portal_base}/index.php?ac=jobad&id={posting_id}"

    @property
    def robots_urls(self) -> tuple[str, ...]:
        return (f"{self.search_base}/robots.txt", f"{self.portal_base}/robots.txt")


#: Sources established by the Phase-4 source-discovery probe
#: (experiments/innovation_signals_observatory/docs/SOURCE_DISCOVERY_EXTRAS.md).
SOURCES: dict[str, BeesiteSource] = {
    "draeger": BeesiteSource(
        company_key="draeger",
        label="Dräger",
        search_base="https://draeger-beesite-production-gjb.app.beesite.de",
        portal_base="https://erecruitment.draeger.com",
    ),
}


# --------------------------------------------------------------------- collection
@dataclass
class CollectionReport:
    company_key: str
    source_label: str
    started_at: str = ""
    finished_at: str = ""
    search_result_count: int | None = None
    search_result_count_all: int | None = None
    items_returned: int = 0
    details_requested: int = 0
    details_ok: int = 0
    details_failed: int = 0
    detail_failures: list[dict[str, Any]] = None  # type: ignore[assignment]
    truncated_at_ceiling: bool = False
    robots: dict[str, Any] = None  # type: ignore[assignment]
    robots_interpretation: dict[str, Any] = None  # type: ignore[assignment]
    request_stats: dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.detail_failures = self.detail_failures or []
        self.robots = self.robots or {}
        self.robots_interpretation = self.robots_interpretation or {}
        self.request_stats = self.request_stats or {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "company_key": self.company_key,
            "source_label": self.source_label,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "search_result_count": self.search_result_count,
            "search_result_count_all": self.search_result_count_all,
            "items_returned": self.items_returned,
            "details_requested": self.details_requested,
            "details_ok": self.details_ok,
            "details_failed": self.details_failed,
            "detail_failures": self.detail_failures[:50],
            "truncated_at_ceiling": self.truncated_at_ceiling,
            "robots": {k: {"robots_url": v.get("robots_url"), "status": v.get("status"),
                           "is_robots_file": v.get("is_robots_file"),
                           "n_groups": v.get("n_groups")} for k, v in self.robots.items()},
            "robots_interpretation": self.robots_interpretation,
            "request_stats": self.request_stats,
            "collector_version": rec.COLLECTOR_VERSION,
        }


def _fetch_robots(fetcher: Fetcher, policy: CollectionPolicy, url: str) -> dict[str, Any]:
    status: int | None = None
    text = ""
    try:
        text = fetcher.get_text(url)
        status = 200
    except HttpError as exc:
        status = exc.status
        text = exc.body or ""
    except Exception as exc:  # noqa: BLE001 - recorded, never guessed
        status = getattr(exc, "status", None)
    evidence = policy.record_robots(url, status, text)
    head = (text or "").lstrip()
    is_file = bool(text) and status == 200 and not head.startswith("<") and not head.startswith("{")
    evidence["is_robots_file"] = is_file
    return {"robots_url": url, "status": status, "is_robots_file": is_file,
            "raw_head": (text or "")[:700]}


def check_robots(fetcher: Fetcher, source: BeesiteSource,
                 policy: CollectionPolicy) -> dict[str, Any]:
    """Record both hosts' robots.txt and authorise the exact paths this run reads."""
    evidence: dict[str, Any] = {}
    search_host = urllib.parse.urlsplit(source.search_base).netloc.lower()
    portal_host = urllib.parse.urlsplit(source.portal_base).netloc.lower()
    for url in source.robots_urls:
        item = _fetch_robots(fetcher, policy, url)
        evidence[urllib.parse.urlsplit(url).netloc.lower()] = item
    interpretation: dict[str, Any] = {}
    # Beesite host: no robots.txt published -> RFC 9309 unavailable rule, recorded.
    search_evidence = evidence[search_host]
    if not search_evidence["is_robots_file"]:
        decision = policy.assert_allowed(source.search_base + source.search_path,
                                         source.search_path)
        interpretation[search_host] = {
            "published": False,
            "status": search_evidence["status"],
            "basis": ("no robots.txt is published (GET returned a non-REP response); RFC 9309 "
                      "treats an unavailable robots.txt as unrestricted"),
            "decision": decision,
        }
    else:
        interpretation[search_host] = {
            "published": True,
            "decision": policy.assert_allowed(source.search_base + source.search_path,
                                              source.search_path),
        }
    # Portal host: robots rules apply verbatim (a bare Sitemap: line restricts nothing).
    portal_path = urllib.parse.urlsplit(source.portal_base + "/index.php").path
    portal_decision = policy.assert_allowed(source.portal_base + "/index.php", portal_path)
    interpretation[portal_host] = {"published": evidence[portal_host]["is_robots_file"],
                                   "decision": portal_decision}
    return {"evidence": evidence, "interpretation": interpretation}


def _item_row(item: dict[str, Any]) -> dict[str, Any]:
    d = item.get("MatchedObjectDescriptor") or {}
    locations = d.get("PositionLocation") or []
    return {
        "posting_id": str(d.get("ID") or item.get("MatchedObjectId") or "").strip(),
        "job_title": d.get("PositionTitle"),
        "publication_start_date": d.get("PublicationStartDate"),
        "parent_organization_name": d.get("ParentOrganizationName"),
        "organization_short_name": d.get("OrganizationShortName"),
        "position_uri": d.get("PositionURI"),
        "cities": [loc.get("CityName") for loc in locations if loc.get("CityName")],
        "countries": [loc.get("CountryName") for loc in locations if loc.get("CountryName")],
        "job_category": ((d.get("JobCategory") or [{}])[0]).get("Name"),
        "career_level": ((d.get("CareerLevel") or [{}])[0]).get("Name"),
        "schedule": ((d.get("PositionSchedule") or [{}])[0]).get("Name"),
        "mobile_work": ((d.get("MobileWork") or [{}])[0]).get("Name"),
        "industries": [x.get("Name") for x in (d.get("PositionIndustry") or []) if x.get("Name")],
        "published_entries": len(d.get("PublicationChannel") or []),
    }


def _listing_time(row: dict[str, Any]) -> dict[str, Any]:
    """Fallback source time from the search API when the posting page is unreadable."""
    day = row.get("publication_start_date")
    if isinstance(day, str) and _ISO_DATE_RE.match(day.strip()):
        return {"source_posted_at": day.strip(), "quality": rec.QUALITY_SOURCE_DATE,
                "raw": day}
    return {"source_posted_at": None, "quality": rec.QUALITY_NONE, "raw": day}


def _text(value: Any) -> str | None:
    """A JSON-LD/list text field, unescaped once (Dräger's titles contain ``&amp;``)."""
    if value in (None, ""):
        return None
    text = html_mod.unescape(str(value)).strip()
    return text or None


def build_observation(source: BeesiteSource, row: dict[str, Any], jobposting: dict[str, Any],
                      *, fetched_at: str) -> rec.JobObservation:
    """One search-API row + its posting page's JSON-LD → one ``JobObservation``."""
    if not row.get("posting_id"):
        raise ValueError("search row carries no posting id (ID)")
    posted = source_time_from_jobposting(jobposting)
    time_fell_back = not posted["source_posted_at"]
    if time_fell_back:
        posted = _listing_time(row)
    identifier, identifier_name, _ = jobposting_identifier(jobposting)
    primary, additional, _ = jobposting_locations(jobposting)
    description = description_to_text(jobposting.get("description"))
    title = _text(jobposting.get("title")) or _text(row.get("job_title"))
    location = primary or (", ".join(row.get("cities") or []) or None)
    organization = _text(row.get("parent_organization_name")) or source.legal_entity
    status = rec.STATUS_COMPLETE if description else rec.STATUS_NO_DESCRIPTION
    obs = rec.JobObservation(
        company_key=source.company_key,
        legal_entity=organization,
        entity_resolution_status=rec.ENTITY_STATUS_COMPANY_KEY,
        entity_resolution_note=(
            "ParentOrganizationName is stated by the source's own search API per posting; "
            "recorded as the source's claim, not resolved to a universe entity key"
            if organization else
            "the portal states no employing legal entity per posting"),
        posting_id=str(row["posting_id"]),
        job_title=title,
        job_description=description or None,
        job_location=location,
        additional_locations=additional[:20],
        source_url=row.get("position_uri") or source.jobad_url(str(row["posting_id"])),
        source_platform=rec.PLATFORM_BEESITE,
        source_posted_at=posted["source_posted_at"],
        source_posted_quality=posted["quality"],
        source_posted_raw=posted.get("raw"),
        source_updated_at=None,
        first_seen_at=fetched_at,
        fetched_at=fetched_at,
        collection_status=status,
        raw={
            "posting_id_kind": "ID (portal job-ad URL id)",
            "posting_id_alt": identifier,
            "posting_id_alt_name": _text(identifier_name),
            "date_field": posted.get("field") or ("PublicationStartDate"
                                                  if time_fell_back else None),
            "date_from_list_api_fallback": time_fell_back,
            "date_note": posted.get("raw_note"),
            "parent_organization_name": organization,
            "organization_short_name": row.get("organization_short_name"),
            "publication_start_date_list_api": row.get("publication_start_date"),
            "job_category": row.get("job_category"),
            "career_level": row.get("career_level"),
            "schedule": row.get("schedule"),
            "mobile_work": row.get("mobile_work"),
            "industries": row.get("industries"),
            "cities": row.get("cities"),
            "countries": row.get("countries"),
            "description_chars_html": len(jobposting.get("description") or ""),
        },
    )
    return obs.finalise(fetched_at=fetched_at)


def collect(source: BeesiteSource, policy: CollectionPolicy, fetcher: Fetcher,
            *, limit_postings: int | None = None) -> tuple[list[rec.JobObservation], CollectionReport]:
    """Collect one bounded snapshot of a Beesite job board (list API + posting pages)."""
    report = CollectionReport(company_key=source.company_key, source_label=source.label,
                              started_at=rec.utc_now_iso())
    robots = check_robots(fetcher, source, policy)
    report.robots = robots["evidence"]
    report.robots_interpretation = robots["interpretation"]
    ceiling = limit_postings if limit_postings is not None else policy.max_postings
    data = fetcher.get_json(source.search_url(ceiling))
    result = (data or {}).get("SearchResult") or {}
    items = list(result.get("SearchResultItems") or [])
    report.search_result_count = result.get("SearchResultCount")
    report.search_result_count_all = result.get("SearchResultCountAll")
    report.items_returned = len(items)
    if len(items) >= ceiling:
        report.truncated_at_ceiling = True

    observations: list[rec.JobObservation] = []
    for item in items[:ceiling]:
        fetched_at = rec.utc_now_iso()
        row = _item_row(item)
        if not row["posting_id"]:
            report.detail_failures.append({"error": "search item carried no ID"})
            continue
        report.details_requested += 1
        page_url = source.jobad_url(row["posting_id"])
        try:
            html = fetcher.get_text(page_url)
            jobposting = find_jobposting(html)
            if jobposting is None:
                raise ValueError("job-ad page carried no schema.org JobPosting JSON-LD")
            obs = build_observation(source, row, jobposting, fetched_at=fetched_at)
            report.details_ok += 1
        except Exception as exc:  # noqa: BLE001 - recorded, not dropped
            status = getattr(exc, "status", None)
            report.details_failed += 1
            t = _listing_time(row)
            report.detail_failures.append({"posting_id": row["posting_id"], "url": page_url,
                                           "http_status": status,
                                           "error": f"{type(exc).__name__}: {exc}"[:300]})
            obs = rec.JobObservation(
                company_key=source.company_key,
                legal_entity=row.get("parent_organization_name"),
                entity_resolution_status=rec.ENTITY_STATUS_COMPANY_KEY,
                entity_resolution_note=("detail fetch failed; the source's own search-API "
                                        "employing organisation is kept, company-level only"),
                posting_id=row["posting_id"],
                job_title=row.get("job_title"),
                job_location=(", ".join(row.get("cities") or []) or None),
                source_url=row.get("position_uri") or page_url,
                source_platform=rec.PLATFORM_BEESITE,
                source_posted_at=t["source_posted_at"],
                source_posted_quality=t["quality"],
                source_posted_raw=t.get("raw"),
                first_seen_at=fetched_at,
                fetched_at=fetched_at,
                collection_status=rec.STATUS_DETAIL_FAILED,
                raw={"posting_id_kind": "ID (portal job-ad URL id)",
                     "detail_fetch_failed": True, "http_status": status,
                     "parent_organization_name": row.get("parent_organization_name"),
                     "publication_start_date_list_api": row.get("publication_start_date")},
            ).finalise(fetched_at=fetched_at)
        observations.append(obs)
    report.finished_at = rec.utc_now_iso()
    report.request_stats = dict(getattr(fetcher, "stats", {}))
    return observations, report
