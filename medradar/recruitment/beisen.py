"""Beisen (北森) zhiye.com career-portal collector (Mindray / 迈瑞医疗).

What this reads, and why it is lawful
-------------------------------------
``mindray.zhiye.com`` is Mindray's public recruitment portal, served by Beisen's
``ux-recruitment-portal-2022`` front end. The portal's own JavaScript calls three public
JSON endpoints on the same host — the same requests a browser makes when a human opens
the vacancy list — and this collector uses only those:

  * ``POST /api/Jobad/GetJobAdPageList``  — paged listing (title, id, locations, category,
    ``PostDate``/``PostDateInt``, and the ``Duty`` + ``Require`` text);
  * ``GET  /api/JobAd/GetJobAdInfo``      — one posting's record (same fields, one object);
  * the public posting page ``/social/detail?jobAdId=<id>``.

No login, captcha, paywall or access control is touched; the portal's ``robots.txt`` is
``User-agent: * / Allow: /`` and is fetched and asserted before any collection request;
requests are throttled per host and capped per run (``CollectionPolicy``).

Identity, time and description semantics
----------------------------------------
* Identity is the posting's own ``Id`` (the GUID the portal uses in its public detail URL);
  the integer ``JobAdId`` and ``JobAdName`` are kept as secondary keys, never as identity.
* ``PostDateInt`` is an epoch-millisecond timestamp whose local rendering (``PostDate``)
  is UTC+8. The collector stores the UTC instant derived from ``PostDateInt`` and keeps
  ``PostDate`` verbatim as ``source_posted_raw``; it records whether the two agree.
* The description is the source's ``Duty`` (responsibilities) + ``Require`` (requirements)
  fields, concatenated in source order without invented headings. Because the listing
  endpoint already carries both, no per-posting detail request is needed; the record says
  so in ``raw.description_source`` rather than implying a detail page was read.
"""
from __future__ import annotations

import html as html_mod
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from ..http import Fetcher, HttpError
from . import records as rec
from .politeness import CollectionPolicy
from .workday import html_to_text

#: The portal's tenant-local clock is UTC+8; ``PostDate`` renders in it, ``PostDateInt``
#: is the authoritative epoch. Both are recorded; only the epoch is converted.
TENANT_TZ_OFFSET = timedelta(hours=8)


@dataclass(frozen=True)
class BeisenSource:
    company_key: str
    label: str
    base_url: str                  # e.g. https://mindray.zhiye.com
    #: the portal category this collector reads: "1" is 社会招聘 (experienced/social hires)
    category: str = "1"
    category_label: str = "社会招聘"
    page_size: int = 20
    #: the legal entity, when the portal itself states it (it does not, per posting)
    legal_entity: str | None = None

    @property
    def host(self) -> str:
        return self.base_url.split("://", 1)[-1].rstrip("/")

    @property
    def robots_url(self) -> str:
        return f"{self.base_url}/robots.txt"

    @property
    def listing_url(self) -> str:
        return f"{self.base_url}/api/Jobad/GetJobAdPageList"

    @property
    def detail_url(self) -> str:
        return f"{self.base_url}/api/JobAd/GetJobAdInfo"

    @property
    def catalog_url(self) -> str:
        return f"{self.base_url}/social/jobs"

    def page_url(self, posting_id: str) -> str:
        return f"{self.base_url}/social/detail?jobAdId={urllib.parse.quote(str(posting_id))}"


#: Sources established by the Phase-4 source-discovery probe
#: (experiments/innovation_signals_observatory/docs/SOURCE_DISCOVERY_EXTRAS.md).
SOURCES: dict[str, BeisenSource] = {
    "mindray": BeisenSource(
        company_key="mindray",
        label="Mindray",
        base_url="https://mindray.zhiye.com",
    ),
}

#: Listing payload as the portal's own front end sends it (captured 2026-11-04).
LISTING_DISPLAY_FIELDS = ["Category", "Kind", "LocId", "PostDate", "WorkWeChatQrCode"]
DETAIL_DISPLAY_FIELDS = ["jobAdName", "Duty", "Require", "Category", "Kind", "LocId",
                         "PostDate", "WorkWeChatQrCode"]


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
    rows_parsed: int = 0
    rows_failed: int = 0
    #: this collector reads the description from the listing endpoint, so it makes no
    #: per-posting detail request; these stay 0 for the honest reason, not by omission
    details_requested: int = 0
    details_ok: int = 0
    details_failed: int = 0
    detail_failures: list[dict[str, Any]] = None  # type: ignore[assignment]
    truncated_at_ceiling: bool = False
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
            "rows_parsed": self.rows_parsed,
            "rows_failed": self.rows_failed,
            "details_requested": self.details_requested,
            "details_ok": self.details_ok,
            "details_failed": self.details_failed,
            "detail_failures": self.detail_failures[:50],
            "truncated_at_ceiling": self.truncated_at_ceiling,
            "robots": {k: {"robots_url": v.get("robots_url"), "status": v.get("status"),
                           "n_groups": v.get("n_groups")} for k, v in self.robots.items()},
            "request_stats": self.request_stats,
            "collector_version": rec.COLLECTOR_VERSION,
        }


def check_robots(fetcher: Fetcher, source: BeisenSource,
                 policy: CollectionPolicy) -> dict[str, Any]:
    """Fetch and record robots.txt, then assert the listing path is permitted."""
    status: int | None = None
    text = ""
    try:
        text = fetcher.get_text(source.robots_url)
        status = 200
    except HttpError as exc:
        status = exc.status
    except Exception as exc:  # noqa: BLE001 - a robots fetch failure blocks collection
        status = getattr(exc, "status", None)
    evidence = policy.record_robots(source.robots_url, status, text)
    evidence["is_robots_file"] = bool(text) and status == 200
    if status != 200 or not text:
        raise PermissionError(f"robots.txt unreadable for {source.host} (status={status}); "
                              f"refusing to collect")
    listing_path = urllib.parse.urlsplit(source.listing_url).path
    policy.assert_allowed(source.robots_url, listing_path)
    detail_path = urllib.parse.urlsplit(source.page_url("example")).path
    policy.assert_allowed(source.robots_url, detail_path)
    policy.notes.append(f"robots.txt for {source.host} grants the host: "
                        f"{' '.join(text.split())[:120]!r}")
    return evidence


def listing_payload(source: BeisenSource, page: int) -> dict[str, Any]:
    """The exact JSON body the portal's own front end posts for the vacancy list."""
    return {
        "PageIndex": page,
        "PageSize": source.page_size,
        "Category": [source.category],
        "KeyWords": "",
        "SpecialType": 0,
        "PortalId": "",
        "DisplayFields": list(LISTING_DISPLAY_FIELDS),
    }


def iter_listings(fetcher: Fetcher, source: BeisenSource, policy: CollectionPolicy,
                  report: CollectionReport) -> Iterable[dict[str, Any]]:
    """Yield listing rows page by page, bounded by the posting ceiling.

    Pagination deliberately does **not** trust ``Count`` to decide when to stop: it keeps
    requesting until a page comes back empty or the ceiling is hit, recording the total the
    source reported. A source that under-reports ``Count`` must not silently shrink the
    population (the lesson of the Workday total-only-on-first-page defect).
    """
    page = 0
    seen = 0
    while True:
        data = fetcher.post_json(source.listing_url, listing_payload(source, page))
        report.listing_pages += 1
        if not isinstance(data, dict) or data.get("Code") not in (200, "200", None):
            raise RuntimeError(f"portal answered Code={data.get('Code') if isinstance(data, dict) else data!r} "
                               f"Message={data.get('Message') if isinstance(data, dict) else ''!r}")
        rows = data.get("Data") or []
        total = data.get("Count")
        if isinstance(total, int) and report.listing_total_reported is None:
            report.listing_total_reported = total
        if not rows:
            break
        for row in rows:
            if seen >= policy.max_postings:
                report.truncated_at_ceiling = True
                return
            seen += 1
            report.listings_seen += 1
            yield row
        page += 1
        if page > 200:  # safety valve, recorded rather than silent
            report.truncated_at_ceiling = True
            return


# ------------------------------------------------------------------------ parsing
def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) not in (None, "", []):
            return row[key]
    return None


def _clean_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = html_to_text(str(value)) if "<" in str(value) else rec.normalise_text(str(value))
    return text or None


def source_time(row: dict[str, Any]) -> dict[str, Any]:
    """Derive the publication time from ``PostDateInt`` (epoch ms), never from ``PostDate``.

    ``PostDateInt`` is the authoritative instant; ``PostDate`` is the same instant rendered
    in the tenant's UTC+8 clock and is kept verbatim as the raw string. If the epoch is
    missing the posting gets ``QUALITY_NONE`` — the local wall-clock string without an
    offset is not converted into an instant.
    """
    raw_local = row.get("PostDate")
    epoch_ms = row.get("PostDateInt")
    if isinstance(epoch_ms, (int, float)) and epoch_ms > 0:
        moment = datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc)
        moment = moment.replace(microsecond=0)
        consistency = None
        if isinstance(raw_local, str) and raw_local:
            local_clock = (moment + TENANT_TZ_OFFSET).strftime("%Y-%m-%dT%H:%M:%S")
            consistency = "epoch_matches_utc+8_rendering" if local_clock == raw_local.strip() \
                else f"epoch_does_not_match_rendering:post_date={raw_local[:40]}"
        return {"source_posted_at": moment.isoformat(), "quality": rec.QUALITY_SOURCE_DATETIME,
                "raw": raw_local, "field": "PostDateInt", "consistency": consistency}
    return {"source_posted_at": None, "quality": rec.QUALITY_NONE, "raw": raw_local,
            "field": None, "consistency": None}


def build_observation(source: BeisenSource, row: dict[str, Any], *,
                      fetched_at: str) -> rec.JobObservation:
    """One listing row → one ``JobObservation``."""
    posting_id = _first(row, "Id")
    if not posting_id:
        raise ValueError("listing row carries no posting id (Id)")
    title = _first(row, "JobAdName")
    duty = _clean_text(row.get("Duty"))
    require = _clean_text(row.get("Require"))
    description = "\n\n".join(part for part in (duty, require) if part) or None
    locations = row.get("LocNames") or []
    location = "; ".join(str(x) for x in locations if x) or None
    t = source_time(row)
    status = rec.STATUS_COMPLETE if description else rec.STATUS_NO_DESCRIPTION
    obs = rec.JobObservation(
        company_key=source.company_key,
        legal_entity=source.legal_entity,
        entity_resolution_status=(rec.ENTITY_STATUS_CANONICAL if source.legal_entity
                                  else rec.ENTITY_STATUS_COMPANY_KEY),
        entity_resolution_note=(
            None if source.legal_entity else
            "the Beisen portal publishes the employer brand only; the registered legal "
            "entity that employs the role is not stated on the posting"),
        posting_id=str(posting_id),
        job_title=str(title) if title else None,
        job_description=description,
        job_location=location,
        additional_locations=[str(x) for x in locations[1:] if x][:20],
        source_url=source.page_url(str(posting_id)),
        source_platform=rec.PLATFORM_BEISEN,
        source_posted_at=t["source_posted_at"],
        source_posted_quality=t["quality"],
        source_posted_raw=t.get("raw"),
        source_updated_at=(str(row["ChangeDate"]) if row.get("ChangeDate") else None),
        first_seen_at=fetched_at,
        fetched_at=fetched_at,
        collection_status=status,
        raw={
            "posting_id_kind": "Id",
            "job_ad_id": row.get("JobAdId"),
            "category": row.get("Category"),
            "category_id": row.get("CategoryId"),
            "kind": row.get("Kind"),
            "status": row.get("Status"),
            "location_names": locations,
            "post_date_int": row.get("PostDateInt"),
            "post_date_rendered": row.get("PostDate"),
            "post_date_consistency": t.get("consistency"),
            "change_date": row.get("ChangeDate"),
            "end_time": row.get("EndTime"),
            "duty_chars": len(row.get("Duty") or ""),
            "require_chars": len(row.get("Require") or ""),
            "description_source": "listing_api:Jobad/GetJobAdPageList (Duty + Require)",
        },
    )
    return obs.finalise(fetched_at=fetched_at)


def fetch_detail(fetcher: Fetcher, source: BeisenSource, posting_id: str) -> dict[str, Any]:
    """Read one posting from the portal's own detail endpoint (used by the probe/tests)."""
    query = urllib.parse.urlencode({"jobAdId": posting_id, "category": source.category,
                                    "displayFields": str(DETAIL_DISPLAY_FIELDS).replace("'", '"')})
    data = fetcher.get_json(f"{source.detail_url}?{query}")
    if not isinstance(data, dict) or data.get("Code") not in (200, "200"):
        raise RuntimeError(f"detail endpoint answered Code={data.get('Code') if isinstance(data, dict) else data!r}")
    return data.get("Data") or {}


def build_observation_from_detail(source: BeisenSource, detail: dict[str, Any], *,
                                  fetched_at: str) -> rec.JobObservation:
    """A detail-endpoint record and a listing row share a shape; reuse the same builder."""
    return build_observation(source, detail, fetched_at=fetched_at)


def collect(source: BeisenSource, policy: CollectionPolicy, fetcher: Fetcher,
            *, limit_postings: int | None = None) -> tuple[list[rec.JobObservation], CollectionReport]:
    """Collect one bounded snapshot of a Beisen career portal."""
    report = CollectionReport(company_key=source.company_key, source_label=source.label,
                              started_at=rec.utc_now_iso())
    check_robots(fetcher, source, policy)
    report.robots = policy.robots_evidence
    ceiling = limit_postings if limit_postings is not None else policy.max_postings
    old_max = policy.max_postings
    policy.max_postings = ceiling
    observations: list[rec.JobObservation] = []
    try:
        for row in iter_listings(fetcher, source, policy, report):
            fetched_at = rec.utc_now_iso()
            try:
                obs = build_observation(source, row, fetched_at=fetched_at)
                report.rows_parsed += 1
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                report.rows_failed += 1
                report.detail_failures.append({
                    "posting_id": row.get("Id"),
                    "error": f"{type(exc).__name__}: {exc}"[:300]})
                continue
            observations.append(obs)
    finally:
        policy.max_postings = old_max
    report.finished_at = rec.utc_now_iso()
    report.request_stats = dict(getattr(fetcher, "stats", {}))
    return observations, report
