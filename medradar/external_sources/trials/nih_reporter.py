"""NIH RePORTER v2 connector (``grant``).

The API is POST-only: ``POST /v2/projects/search`` with a ``criteria`` object.
``HttpClient.post_json`` is used, so the request still goes through the bounded,
ledgered client.

Timestamp rule
--------------
``event_at`` = ``project_start_date`` (when the funded work starts).
``source_public_at`` = ``award_notice_date`` (when the award record became
public).  When ``award_notice_date`` is absent the public clock is left empty with
quality ``unknown`` — it is never back-filled from the project start date, because
that would fabricate public visibility.

Company attribution
-------------------
``organization.org_name`` is a structured field -> ``tier="grantee"``.  The
matching is exact-string based on the source side, so ``MEDTRONIC`` and
``MEDTRONIC INC`` return different sets; that limitation is recorded in the
register rather than smoothed over.
"""

from __future__ import annotations

from typing import Any, Mapping

from .. import identity, schema
from . import _common

SOURCE_ID = "nih_reporter"
KIND = "grant"
LICENCE_STATUS = "public_domain"
SOURCE_NAME = "NIH RePORTER"
ATTRIBUTION = "NIH RePORTER (US HHS)"
BASE_URL = "https://api.reporter.nih.gov/v2/projects/search"
INCLUDE_FIELDS = [
    "ProjectNum",
    "CoreProjectNum",
    "ProjectTitle",
    "FiscalYear",
    "ProjectStartDate",
    "ProjectEndDate",
    "AwardNoticeDate",
    "AwardAmount",
    "Organization",
    "PrincipalInvestigators",
    "AgencyIcAdmin",
    "ActivityCode",
]
DEFAULT_CRITERIA: dict[str, Any] = {"fiscal_years": [2023]}


def _identifiers(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    award = identity.build_identifier(
        "award_id",
        item.get("core_project_num") or item.get("project_num"),
        is_primary=True,
    )
    if award:
        out.append(award)
    project_num = identity.build_identifier("award_id", item.get("project_num"))
    if project_num and project_num["value"] != (award or {}).get("value"):
        out.append(project_num)
    return out


def to_evidence(raw_item: Mapping[str, Any], *, fetched_at: Any = None) -> dict[str, Any]:
    """One RePORTER project row -> one ``grant`` evidence record."""
    item = dict(raw_item)
    fetched = _common.as_datetime(fetched_at)
    record_id = str(item.get("core_project_num") or item.get("project_num") or "").strip()
    if not record_id:
        raise ValueError("nih_reporter item without project number")
    organization = item.get("organization") or {}
    org_name = str(organization.get("org_name") or "").strip()
    agency = item.get("agency_ic_admin") or {}
    start_date = item.get("project_start_date")
    notice_date = item.get("award_notice_date")
    refs = _common.company_refs([org_name], tier="grantee")
    normalized = {
        "project_num": item.get("project_num"),
        "core_project_num": item.get("core_project_num"),
        "project_title": item.get("project_title"),
        "fiscal_year": item.get("fiscal_year"),
        "award_amount": item.get("award_amount"),
        "activity_code": item.get("activity_code"),
        "project_start_date": start_date,
        "project_end_date": item.get("project_end_date"),
        "award_notice_date": notice_date,
        "organization": {
            "name": org_name,
            "city": organization.get("org_city"),
            "country": organization.get("org_country"),
            "state": organization.get("org_state"),
            "uei": (organization.get("org_ueis") or [None])[0],
        },
        "agency": agency.get("abbreviation") or agency.get("code"),
        "principal_investigators": [
            pi.get("full_name")
            for pi in item.get("principal_investigators") or []
            if isinstance(pi, Mapping)
        ],
        "grant_numbers": [
            {
                "value": str(item.get("project_num") or record_id),
                "funder": "NIH",
                "field": "project_num",
            }
        ],
        "trial_ids": [],
        "metadata_clock_fields": _common.metadata_clock_fields(
            ("fiscal_year", item.get("fiscal_year")),
        ),
    }
    return schema.make_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=record_id,
        source_url=f"https://reporter.nih.gov/project-details/{record_id}",
        normalized=normalized,
        raw=_common.raw_block(item),
        time=_common.time_block(
            event_at=start_date,
            source_public_at=notice_date,
            fetched_at=fetched,
            notes="project_start_date is the event clock; award_notice_date is the public clock and is left empty when absent",
        ),
        identifiers=_identifiers(item),
        entity_refs=refs,
        provenance=_common.provenance(
            source_name=SOURCE_NAME,
            licence_status=LICENCE_STATUS,
            attribution=ATTRIBUTION,
            redistribution="allowed (US government work)",
            evidence_reference=f"https://reporter.nih.gov/project-details/{record_id}",
            quality=_common.coerce_date(notice_date)[1],
        ),
        fetched_at=fetched.isoformat(),
    )


def fetch_items(
    client: Any,
    *,
    limit: int = 50,
    criteria: Mapping[str, Any] | None = None,
    offset: int = 0,
    page_size: int = 25,
    max_pages: int = 2,
) -> list[dict[str, Any]]:
    """Bounded offset pagination over the POST search endpoint."""
    if limit <= 0:
        return []
    size = max(1, min(int(page_size), 500, limit))
    start = max(0, int(offset))
    seen: dict[str, dict[str, Any]] = {}
    pages = 0
    while pages < max(1, int(max_pages)) and len(seen) < limit:
        payload = {
            "criteria": dict(criteria or DEFAULT_CRITERIA),
            "include_fields": list(INCLUDE_FIELDS),
            "offset": start,
            "limit": size,
        }
        result = client.post_json(BASE_URL, payload)
        pages += 1
        if not result.ok:
            break
        body = result.json()
        batch = body.get("results") or []
        for item in batch:
            if not isinstance(item, Mapping):
                continue
            key = str(item.get("core_project_num") or item.get("project_num") or "")
            if key:
                seen.setdefault(key, dict(item))
        total = (body.get("meta") or {}).get("total")
        start += size
        if not batch or (isinstance(total, int) and start >= total):
            break
    return list(seen.values())[:limit]


def collect(
    client: Any,
    *,
    limit: int = 50,
    criteria: Mapping[str, Any] | None = None,
    offset: int = 0,
    page_size: int = 25,
    max_pages: int = 2,
) -> list[dict[str, Any]]:
    """Fetch up to ``limit`` project rows and return schema-valid evidence records."""
    fetched = _common.as_datetime(None)
    items = fetch_items(
        client,
        limit=limit,
        criteria=criteria,
        offset=offset,
        page_size=page_size,
        max_pages=max_pages,
    )
    return [to_evidence(item, fetched_at=fetched) for item in items]


__all__ = ["SOURCE_ID", "KIND", "LICENCE_STATUS", "collect", "fetch_items", "to_evidence"]
