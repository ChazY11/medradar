"""Phenom People career-site collector (GE HealthCare, Philips).

What this reads, and why it is lawful
-------------------------------------
A Phenom CareerConnect site is a public web application. Every posting it publishes has
three public, unauthenticated representations, and this collector uses only those:

  * ``robots.txt``
      - GE HealthCare publishes one (``text/plain``) that *advertises* the sitemap and
        disallows only application/cart/chatbot paths (``*/apply``, ``*/jobcart``,
        ``*/chatbot``, ...). Posting and sitemap paths are unrestricted.
      - Philips does **not** publish a ``robots.txt``: the host answers ``/robots.txt``
        with the SPA HTML shell (``text/html``, no REP directives). That is recorded
        verbatim, and the RFC 9309 "unavailable robots" rule is applied explicitly —
        not silently. See ``interpret_robots`` and the collection report.
  * the XML sitemap index (``<locale>/sitemap_index.xml``) advertised by GE HealthCare's
    robots.txt and present on Philips' host; each sub-sitemap lists posting URLs with a
    ``<lastmod>``.
  * each posting page — a public HTML page carrying a schema.org ``JobPosting`` JSON-LD
    block (``identifier``, ``datePosted``, ``title``, ``description``, ``jobLocation``).

No login, captcha, paywall or anti-bot mechanism is bypassed; no candidate data is read;
requests are throttled per host and capped per run (``CollectionPolicy``). A posting whose
detail page returns an error (e.g. ``410 Gone`` for a stale sitemap entry) is *kept* as a
``DETAIL_FAILED`` observation rather than dropped, because a fetch failure is not evidence
that the posting does not exist.

Date discipline
---------------
Phenom publishes ``datePosted`` either as a plain date (``2026-09-07``) or as a
timezone-qualified timestamp that is exactly midnight (``2026-11-04T00:00:00.000+0000``).
Both are recorded verbatim with the quality they actually have; the midnight form is
flagged as a date carrying a rendering placeholder, never turned into a different day and
never used to invent a first-seen time.
"""
from __future__ import annotations

import html as html_mod
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..http import Fetcher, HttpError
from . import records as rec
from .politeness import CollectionPolicy, parse_robots, robots_allows
from .workday import html_to_text

_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$")
_MIDNIGHT = re.compile(r"T00:00:00(?:\.0+)?(?:Z|[+-]\d{2}:?\d{2})?$")
_JOB_PATH = re.compile(r"/job/", re.I)
_URL_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_URL_BLOCK = re.compile(r"<url>\s*(.*?)\s*</url>", re.S | re.I)


def looks_like_html(text: str | None) -> bool:
    head = (text or "").lstrip()[:400].lower()
    return head.startswith("<!doctype html") or head.startswith("<html") or "<head" in head[:200]


# ---------------------------------------------------------------------- json-ld
def jsonld_script_bodies(html: str | None) -> list[str]:
    """The raw text of every ``application/ld+json`` script block on a page."""
    return [m.group(1).strip() for m in _JSONLD_RE.finditer(html or "")]


def jsonld_nodes(html: str | None) -> list[dict[str, Any]]:
    """Flatten every JSON-LD block on the page into a list of dict nodes.

    A malformed block is skipped (it is not evidence of a posting); the collector records
    ``jsonld_present`` separately so a parse failure is visible in the report rather than
    silently read as "no posting".
    """
    nodes: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            nodes.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for body in jsonld_script_bodies(html):
        try:
            walk(json.loads(body))
        except json.JSONDecodeError:
            continue
    return nodes


def _types(node: dict[str, Any]) -> list[str]:
    value = node.get("@type")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def find_jobposting(html: str | None) -> dict[str, Any] | None:
    """The schema.org ``JobPosting`` node of a posting page, or ``None``."""
    for node in jsonld_nodes(html):
        if any(t.lower() == "jobposting" for t in _types(node)):
            return node
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _address_text(place: Any) -> str | None:
    if not isinstance(place, dict):
        return None
    address = place.get("address") if isinstance(place.get("address"), dict) else place
    if not isinstance(address, dict):
        return None
    parts = [address.get("addressLocality"), address.get("addressRegion"),
             address.get("addressCountry")]
    text = ", ".join(str(p).strip() for p in parts if p not in (None, ""))
    return text or None


def jobposting_locations(jp: dict[str, Any]) -> tuple[str | None, list[str], list[dict[str, Any]]]:
    """Primary location text, extra location texts, and the raw ``jobLocation`` value."""
    raw = jp.get("jobLocation")
    places = _as_list(raw)
    texts = [t for t in (_address_text(p) for p in places) if t]
    # jobLocation may also be a bare string on some renders
    if not texts and isinstance(raw, str) and raw.strip():
        texts = [raw.strip()]
    primary = texts[0] if texts else None
    return primary, texts[1:], places


def description_to_text(raw: str | None) -> str:
    """Turn a JSON-LD ``description`` into readable text.

    Phenom emits the description HTML *escaped inside the JSON string*
    (``"description": "&lt;h1&gt;..."``), so it is unescaped once before tag stripping;
    a source that emits unescaped HTML is handled by the same path.
    """
    if not raw:
        return ""
    return html_to_text(html_mod.unescape(raw))


# ------------------------------------------------------------------- time fields
def source_time_from_jobposting(jp: dict[str, Any]) -> dict[str, Any]:
    """The source's own publication time, with the precision it actually published.

    ``datePosted`` is the field. A plain ISO date keeps ``SOURCE_DATE`` precision; a
    timestamp keeps ``SOURCE_DATETIME``. If the timestamp's time-of-day is exactly
    midnight (Phenom renders some postings that way), the value is kept verbatim and
    flagged in ``raw_note`` — the meaningful precision is the day, not the second.
    Nothing is converted, and a missing field yields ``QUALITY_NONE``.
    """
    posted = jp.get("datePosted")
    if isinstance(posted, str) and posted.strip():
        value = posted.strip()
        if _ISO_DATE.match(value):
            return {"source_posted_at": value, "quality": rec.QUALITY_SOURCE_DATE,
                    "raw": value, "field": "datePosted", "raw_note": None}
        if _DATETIME.match(value):
            note = None
            if _MIDNIGHT.search(value):
                note = ("datePosted carries a time of exactly midnight, so the source "
                        "publishes day precision while rendering a timestamp")
            return {"source_posted_at": value, "quality": rec.QUALITY_SOURCE_DATETIME,
                    "raw": value, "field": "datePosted", "raw_note": note}
    return {"source_posted_at": None, "quality": rec.QUALITY_NONE, "raw": posted,
            "field": None, "raw_note": None}


def jobposting_identifier(jp: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """The source's posting identity: ``(value, name, field)``.

    Phenom puts the requisition id in ``identifier`` as a schema.org ``PropertyValue``
    (GE HealthCare ``R4045928``, Philips ``594302``). The URL token is kept only as a
    fallback, because the slug embeds the title and a retitled posting would then look
    like a new job.
    """
    identifier = jp.get("identifier")
    if isinstance(identifier, dict):
        value = identifier.get("value")
        if value not in (None, ""):
            return str(value).strip(), (str(identifier.get("name")).strip()
                                        if identifier.get("name") else None), "identifier.value"
    if isinstance(identifier, str) and identifier.strip():
        return identifier.strip(), None, "identifier"
    return None, None, None


def posting_id_from_url(url: str) -> str | None:
    """The source URL's own posting token (fallback identity when JSON-LD is unreadable)."""
    path = url.split("?", 1)[0].rstrip("/")
    match = re.search(r"/job/([^/]+)/", path + "/", re.I)
    if match:
        return match.group(1)
    tail = path.rsplit("/", 1)[-1]
    return tail or None


# ---------------------------------------------------------------------- sources
@dataclass(frozen=True)
class PhenomSource:
    company_key: str
    label: str
    base_url: str                 # e.g. https://careers.gehealthcare.com
    locale_root: str              # e.g. /global/en
    #: the legal entity, when the career site itself states it (Phenom does not)
    legal_entity: str | None = None
    #: "required": robots.txt must exist and allow; "unavailable_allowed": the host does
    #: not publish robots.txt (recorded verbatim) and RFC 9309's unavailable rule applies.
    robots_policy: str = "required"

    @property
    def host(self) -> str:
        return self.base_url.split("://", 1)[-1].rstrip("/")

    @property
    def robots_url(self) -> str:
        return f"{self.base_url}/robots.txt"

    @property
    def sitemap_index_url(self) -> str:
        return f"{self.base_url}{self.locale_root}/sitemap_index.xml"

    @property
    def listing_path(self) -> str:
        return f"{self.locale_root}/sitemap_index.xml"

    def page_url(self, job_url: str) -> str:
        return job_url if job_url.startswith("http") else f"{self.base_url}{job_url}"


#: Sources established by the Phase-4 source-discovery probe
#: (experiments/innovation_signals_observatory/docs/SOURCE_DISCOVERY_EXTRAS.md).
SOURCES: dict[str, PhenomSource] = {
    "ge_healthcare": PhenomSource(
        company_key="ge_healthcare",
        label="GE HealthCare",
        base_url="https://careers.gehealthcare.com",
        locale_root="/global/en",
    ),
    "philips": PhenomSource(
        company_key="philips",
        label="Philips",
        base_url="https://www.careers.philips.com",
        locale_root="/global/en",
        # recorded verbatim from GET https://www.careers.philips.com/robots.txt
        robots_policy="unavailable_allowed",
    ),
}

#: Phenom tenant ids seen in the pages the probe recorded (evidence, not used in requests).
TENANTS = {"ge_healthcare": "GEVGHLGLOBAL", "philips": "PHILUS"}


# --------------------------------------------------------------------- collection
@dataclass
class CollectionReport:
    company_key: str
    source_label: str
    started_at: str = ""
    finished_at: str = ""
    listing_total_reported: int | None = None
    sitemaps_read: int = 0
    sitemap_urls_seen: int = 0
    job_urls_seen: int = 0
    details_requested: int = 0
    details_ok: int = 0
    details_failed: int = 0
    detail_failures: list[dict[str, Any]] = None  # type: ignore[assignment]
    skipped_robots_disallowed: int = 0
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
            "listing_total_reported": self.listing_total_reported,
            "sitemaps_read": self.sitemaps_read,
            "sitemap_urls_seen": self.sitemap_urls_seen,
            "job_urls_seen": self.job_urls_seen,
            "details_requested": self.details_requested,
            "details_ok": self.details_ok,
            "details_failed": self.details_failed,
            "detail_failures": self.detail_failures[:50],
            "skipped_robots_disallowed": self.skipped_robots_disallowed,
            "truncated_at_ceiling": self.truncated_at_ceiling,
            "robots": {k: {"robots_url": v.get("robots_url"), "status": v.get("status"),
                           "n_groups": v.get("n_groups"), "is_robots_file": v.get("is_robots_file")}
                       for k, v in self.robots.items()},
            "robots_interpretation": self.robots_interpretation,
            "request_stats": self.request_stats,
            "collector_version": rec.COLLECTOR_VERSION,
        }


def interpret_robots(source: PhenomSource, status: int | None, text: str,
                     policy: CollectionPolicy) -> dict[str, Any]:
    """Record robots.txt and decide — explicitly — whether collection may proceed.

    Three outcomes:

    * a real robots.txt that allows the sitemap path → proceed;
    * a real robots.txt that disallows it → ``PermissionError`` (refuse the run);
    * no robots.txt (HTTP 404, unreadable, or the host's SPA shell served with
      ``text/html``) → RFC 9309 §2.3.1.3's "unavailable" case: collection is allowed, and
      the absence is written into the report instead of being assumed away.
    """
    is_file = bool(text) and not looks_like_html(text) and status == 200
    evidence = policy.record_robots(source.robots_url, status, text)
    evidence["is_robots_file"] = is_file
    evidence["content_type_checked"] = True
    interpretation: dict[str, Any] = {
        "robots_url": source.robots_url,
        "status": status,
        "published": is_file,
        "mode": "required" if source.robots_policy == "required" else "unavailable_allowed",
    }
    if is_file:
        decision = policy.assert_allowed(source.robots_url, source.listing_path)
        interpretation["listing_path_decision"] = decision
        interpretation["basis"] = "robots.txt rule (longest match)"
        return interpretation
    if source.robots_policy == "required":
        raise PermissionError(
            f"robots.txt unreadable or not a Robots Exclusion Protocol file for "
            f"{source.host} (status={status}); refusing to collect")
    # The host does not publish robots.txt. RFC 9309 §2.3.1.3: a crawler MAY access any
    # resource when robots.txt is unavailable. We still verify that the (empty) rules do
    # not disallow the path, and record the exact reason.
    decision = robots_allows(evidence["groups"], source.listing_path)
    if not decision["allowed"]:
        raise PermissionError(f"robots.txt disallows {source.listing_path} on {source.host}: "
                             f"{decision['reason']}")
    interpretation["listing_path_decision"] = decision
    interpretation["basis"] = (
        "robots.txt is not published (GET returned the SPA HTML shell, no REP directives); "
        "RFC 9309 treats an unavailable robots.txt as unrestricted, and none of the "
        "published site's own meta robots directives forbid indexing")
    return interpretation


def check_robots(fetcher: Fetcher, source: PhenomSource,
                 policy: CollectionPolicy) -> dict[str, Any]:
    """Fetch robots.txt and assert the sitemap/detail paths are permitted to this client."""
    status: int | None = None
    text = ""
    try:
        # get_text has no way to see the status code, so a 404 raises; that is the signal.
        text = fetcher.get_text(source.robots_url)
        status = 200
    except HttpError as exc:
        status = exc.status
    except Exception as exc:  # noqa: BLE001 - unreadable robots blocks/records, never guessed
        status = getattr(exc, "status", None)
        text = ""
    interpretation = interpret_robots(source, status, text, policy)
    policy.notes.append(f"robots: {interpretation['basis']}")
    return interpretation


def iter_sitemap_job_urls(fetcher: Fetcher, source: PhenomSource, policy: CollectionPolicy,
                          report: CollectionReport,
                          *, max_sitemaps: int = 4) -> Iterable[dict[str, Any]]:
    """Yield ``{"url", "lastmod", "sitemap"}`` for each posting listed in the sitemaps.

    The sitemap index is read first and each sub-sitemap is parsed for ``<url>`` blocks;
    postings (paths containing ``/job/``) are ordered by ``lastmod`` descending so a
    bounded run prefers the currently-active postings. The count of every stage is kept
    in the report, so a truncated or stale sitemap is visible rather than implied.
    """
    index_text = fetcher.get_text(source.sitemap_index_url)
    sub_sitemaps = _URL_LOC.findall(index_text)
    report.sitemaps_read += 1
    if not sub_sitemaps:
        # some renders publish a single urlset at the index path
        sub_sitemaps = [source.sitemap_index_url]
    rows: list[dict[str, Any]] = []
    for sitemap_url in sub_sitemaps[:max_sitemaps]:
        if sitemap_url == source.sitemap_index_url and report.sitemaps_read > 1:
            break
        text = index_text if sitemap_url == source.sitemap_index_url else fetcher.get_text(sitemap_url)
        report.sitemaps_read += 1
        for block in _URL_BLOCK.findall(text):
            loc = re.search(r"<loc>\s*([^<\s]+)\s*</loc>", block, re.I)
            if not loc:
                continue
            report.sitemap_urls_seen += 1
            url = loc.group(1)
            if not _JOB_PATH.search(url):
                continue
            lastmod = re.search(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", block, re.I)
            rows.append({"url": url, "lastmod": lastmod.group(1) if lastmod else None,
                         "sitemap": sitemap_url})
    # dedupe (a posting can appear in more than one sitemap) while keeping first sighting
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        if row["url"] in seen:
            continue
        seen.add(row["url"])
        unique.append(row)
    unique.sort(key=lambda r: r["lastmod"] or "", reverse=True)
    report.job_urls_seen = len(unique)
    # NOTE: a sitemap does not "report a total" the way a paged API does; the number of
    # URLs it listed is recorded in ``job_urls_seen`` and ``listing_total_reported`` stays
    # None so nobody can read a sitemap size as the employer's own vacancy count.
    yield from unique


def build_observation(source: PhenomSource, jobposting: dict[str, Any], url: str,
                      *, fetched_at: str) -> rec.JobObservation:
    """One posting page → one ``JobObservation`` (identity/time/description preserved)."""
    identifier, identifier_name, identifier_field = jobposting_identifier(jobposting)
    url_token = posting_id_from_url(url)
    posting_id = identifier or url_token
    identity_kind = identifier_field or ("url_token" if url_token else None)
    if not posting_id:
        raise ValueError(f"no source posting identity on {url}")
    title = jobposting.get("title")
    if isinstance(title, str):
        title = title.strip() or None
    description = description_to_text(jobposting.get("description"))
    primary, additional, _ = jobposting_locations(jobposting)
    t = source_time_from_jobposting(jobposting)
    organization = jobposting.get("hiringOrganization")
    organization_name = (organization.get("name") if isinstance(organization, dict) else
                         (organization if isinstance(organization, str) else None))
    status = rec.STATUS_COMPLETE if description else rec.STATUS_NO_DESCRIPTION
    obs = rec.JobObservation(
        company_key=source.company_key,
        legal_entity=source.legal_entity,
        entity_resolution_status=(rec.ENTITY_STATUS_CANONICAL if source.legal_entity
                                  else rec.ENTITY_STATUS_COMPANY_KEY),
        entity_resolution_note=(
            None if source.legal_entity else
            "Phenom career site publishes the corporate brand only; the registered legal "
            "entity that employs the role is not stated on the posting"),
        posting_id=str(posting_id),
        job_title=title,
        job_description=description,
        job_location=primary,
        additional_locations=additional[:20],
        source_url=url,
        source_platform=rec.PLATFORM_PHENOM,
        source_posted_at=t["source_posted_at"],
        source_posted_quality=t["quality"],
        source_posted_raw=t.get("raw"),
        source_updated_at=None,
        first_seen_at=fetched_at,
        fetched_at=fetched_at,
        collection_status=status,
        raw={
            "posting_id_kind": identity_kind,
            "identifier_name": identifier_name,
            "url_token": url_token,
            "date_field": t.get("field"),
            "date_note": t.get("raw_note"),
            "valid_through": jobposting.get("validThrough"),
            "employment_type": jobposting.get("employmentType"),
            "hiring_organization": organization_name,
            "direct_apply": jobposting.get("directApply"),
            "occupational_category": jobposting.get("occupationalCategory"),
            "industry": jobposting.get("industry"),
            "work_hours": jobposting.get("workHours"),
            "job_location_raw": jobposting.get("jobLocation"),
            "description_chars_html": len(jobposting.get("description") or ""),
        },
    )
    return obs.finalise(fetched_at=fetched_at)


def collect(source: PhenomSource, policy: CollectionPolicy, fetcher: Fetcher,
            *, limit_postings: int | None = None) -> tuple[list[rec.JobObservation], CollectionReport]:
    """Collect one bounded snapshot of a Phenom careers site.

    A posting whose detail request fails (``404``/``410``/network) is kept as a
    ``DETAIL_FAILED`` observation with its listing URL and a recorded HTTP status; it is
    never dropped, and it is never confused with a posting that has no description.
    """
    report = CollectionReport(company_key=source.company_key, source_label=source.label,
                              started_at=rec.utc_now_iso())
    report.robots_interpretation = check_robots(fetcher, source, policy)
    report.robots = policy.robots_evidence
    ceiling = limit_postings if limit_postings is not None else policy.max_postings
    old_max = policy.max_postings
    policy.max_postings = ceiling
    observations: list[rec.JobObservation] = []
    try:
        for row in iter_sitemap_job_urls(fetcher, source, policy, report):
            if len(observations) >= ceiling:
                report.truncated_at_ceiling = True
                break
            url = row["url"]
            fetched_at = rec.utc_now_iso()
            # robots is checked per path as well as per host, so an unexpected disallow
            # can never be read as "the posting vanished".
            try:
                policy.assert_allowed(url, url.split(source.host, 1)[-1])
            except PermissionError:
                report.skipped_robots_disallowed += 1
                continue
            report.details_requested += 1
            try:
                page = fetcher.get_text(url)
                jobposting = find_jobposting(page)
                if jobposting is None:
                    raise ValueError("page carried no schema.org JobPosting JSON-LD")
                obs = build_observation(source, jobposting, url, fetched_at=fetched_at)
                report.details_ok += 1
            except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
                status = getattr(exc, "status", None)
                report.details_failed += 1
                report.detail_failures.append({
                    "url": url, "http_status": status,
                    "error": f"{type(exc).__name__}: {exc}"[:300]})
                token = posting_id_from_url(url)
                if not token:
                    # without any source token there is no lawful identity to record
                    continue
                obs = rec.JobObservation(
                    company_key=source.company_key,
                    posting_id=token,
                    source_platform=rec.PLATFORM_PHENOM,
                    source_url=url,
                    source_posted_at=None,
                    source_posted_quality=rec.QUALITY_NONE,
                    first_seen_at=fetched_at,
                    fetched_at=fetched_at,
                    collection_status=rec.STATUS_DETAIL_FAILED,
                    entity_resolution_status=rec.ENTITY_STATUS_COMPANY_KEY,
                    entity_resolution_note=("detail fetch failed; company-level attribution only"),
                    raw={"posting_id_kind": "url_token", "detail_fetch_failed": True,
                         "http_status": status,
                         "sitemap_lastmod": row.get("lastmod"),
                         "sitemap": row.get("sitemap")},
                ).finalise(fetched_at=fetched_at)
            observations.append(obs)
    finally:
        policy.max_postings = old_max
    report.finished_at = rec.utc_now_iso()
    report.request_stats = dict(getattr(fetcher, "stats", {}))
    return observations, report
