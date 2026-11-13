"""OpenAlex works connector (``publication``).

Timestamp rule
--------------
``publication_date`` is used for both ``event_at`` and ``source_public_at``
because it is the only publication clock OpenAlex publishes.  ``created_date``
is the *metadata-ingestion* clock: it is preserved in ``normalized`` under
``metadata_clock_fields`` precisely so a reviewer can see it was considered and
rejected.  It is never passed to the time block.

Company attribution
-------------------
Two structured hooks, reported at different evidence tiers:

* ``funders[].display_name`` / ``awards[].funder`` -> ``tier="funder"``;
* ``institutions[].display_name`` and ``authorships[].raw_affiliation_strings``
  -> ``tier="author_affiliation"``.

Neither is a full-text keyword hit, so neither is reported as a text mention.
"""

from __future__ import annotations

from typing import Any, Mapping

from .. import identity, schema
from . import _common

SOURCE_ID = "openalex"
KIND = "publication"
LICENCE_STATUS = "open_licence"
SOURCE_NAME = "OpenAlex"
ATTRIBUTION = "OpenAlex (CC0 1.0)"
BASE_URL = "https://api.openalex.org/works"
#: Mail address placed in ``mailto`` to enter the polite pool.
MAILTO = "medradar.research@example.org"
DEFAULT_QUERY = "medical device"
PER_PAGE_MAX = 200


def _tail(url: Any) -> str:
    text = str(url or "").strip()
    return text.rsplit("/", 1)[-1] if text else ""


def _identifiers(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    ids = item.get("ids") or {}
    out: list[dict[str, Any]] = []
    doi = identity.build_identifier("doi", ids.get("doi") or item.get("doi"), is_primary=True)
    if doi:
        out.append(doi)
    pmid = identity.build_identifier("pmid", _tail(ids.get("pmid")))
    if pmid:
        out.append(pmid)
    openalex_id = identity.build_identifier("openalex", _tail(item.get("id")))
    if openalex_id:
        out.append(openalex_id)
    return out


def _institution_names(item: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for institution in item.get("institutions") or []:
        name = str(institution.get("display_name") or "").strip()
        if name and name not in names:
            names.append(name)
    for authorship in item.get("authorships") or []:
        for institution in authorship.get("institutions") or []:
            name = str(institution.get("display_name") or "").strip()
            if name and name not in names:
                names.append(name)
    return names


def _affiliation_strings(item: Mapping[str, Any]) -> list[str]:
    strings: list[str] = []
    for authorship in item.get("authorships") or []:
        for text in authorship.get("raw_affiliation_strings") or []:
            text = str(text or "").strip()
            if text and text not in strings:
                strings.append(text)
    return strings


def _funder_names(item: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for funder in item.get("funders") or []:
        name = str(funder.get("display_name") or "").strip()
        if name and name not in names:
            names.append(name)
    for award in item.get("awards") or []:
        funder = award.get("funder") or {}
        name = str(funder.get("display_name") or "").strip() if isinstance(funder, Mapping) else ""
        if name and name not in names:
            names.append(name)
    return names


def _grant_numbers(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for award in item.get("awards") or []:
        award_id = str(award.get("funder_award_id") or "").strip()
        if not award_id:
            continue
        funder = award.get("funder") or {}
        out.append(
            {
                "value": award_id,
                "funder": str(funder.get("display_name") or "")
                if isinstance(funder, Mapping)
                else "",
                "field": "awards[].funder_award_id",
            }
        )
    for funder in item.get("funders") or []:
        for award_id in funder.get("award_ids") or []:
            award_id = str(award_id or "").strip()
            if award_id:
                out.append(
                    {
                        "value": award_id,
                        "funder": str(funder.get("display_name") or ""),
                        "field": "funders[].award_ids",
                    }
                )
    return out


def to_evidence(raw_item: Mapping[str, Any], *, fetched_at: Any = None) -> dict[str, Any]:
    """One OpenAlex work -> one ``publication`` evidence record."""
    item = dict(raw_item)
    fetched = _common.as_datetime(fetched_at)
    ids = item.get("ids") or {}
    work_id = _tail(item.get("id")) or _tail(ids.get("doi"))
    if not work_id:
        raise ValueError("openalex item without id/doi")
    publication_date = item.get("publication_date")
    refs = _common.company_refs(_funder_names(item), tier="funder") + _common.company_refs(
        _institution_names(item) + _affiliation_strings(item),
        tier="author_affiliation",
    )
    normalized = {
        "title": item.get("title") or item.get("display_name"),
        "type": item.get("type"),
        "publication_year": item.get("publication_year"),
        "publication_date": publication_date,
        "doi": ids.get("doi") or item.get("doi"),
        "pmid": _tail(ids.get("pmid")),
        "journal": ((item.get("primary_location") or {}).get("source") or {}).get("display_name"),
        "is_open_access": (item.get("open_access") or {}).get("is_oa"),
        "cited_by_count": item.get("cited_by_count"),
        "authors_count": len(item.get("authorships") or []),
        "institution_names": _institution_names(item),
        "author_affiliations": _affiliation_strings(item),
        "funders": _funder_names(item),
        "grant_numbers": _grant_numbers(item),
        "trial_ids": [],
        "metadata_clock_fields": _common.metadata_clock_fields(
            ("created_date", item.get("created_date")),
            ("updated_date", item.get("updated_date")),
        ),
    }
    return schema.make_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=work_id,
        source_url=str(item.get("id") or f"https://openalex.org/works/{work_id}"),
        normalized=normalized,
        raw=_common.raw_block(item),
        time=_common.time_block(
            event_at=publication_date,
            source_public_at=publication_date,
            fetched_at=fetched,
            notes="publication_date used for both clocks; created_date is an ingestion clock and is not used",
        ),
        identifiers=_identifiers(item),
        entity_refs=refs,
        provenance={
            "source_name": SOURCE_NAME,
            "licence_status": LICENCE_STATUS,
            "redistribution": "allowed (CC0 1.0)",
            "attribution": ATTRIBUTION,
            "evidence_reference": str(item.get("id") or ""),
            "source_time_quality": _common.coerce_date(publication_date)[1],
        },
        fetched_at=fetched.isoformat(),
    )


def fetch_items(
    client: Any,
    *,
    limit: int = 50,
    query: str = DEFAULT_QUERY,
    per_page: int = 25,
    max_pages: int = 2,
    mailto: str = MAILTO,
) -> list[dict[str, Any]]:
    """Bounded cursor pagination; returns raw work dicts (never more than ``limit``)."""
    if limit <= 0:
        return []
    size = max(1, min(int(per_page), PER_PAGE_MAX, limit))
    cursor = "*"
    seen: dict[str, dict[str, Any]] = {}
    pages = 0
    while pages < max(1, int(max_pages)) and len(seen) < limit and cursor:
        result = client.get(
            BASE_URL,
            params={"search": query, "per-page": size, "cursor": cursor, "mailto": mailto},
        )
        pages += 1
        if not result.ok:
            break
        payload = result.json()
        batch = payload.get("results") or []
        for item in batch:
            if isinstance(item, Mapping) and item.get("id"):
                seen.setdefault(str(item["id"]), dict(item))
        cursor = str((payload.get("meta") or {}).get("next_cursor") or "")
        if not batch:
            break
    return list(seen.values())[:limit]


def collect(
    client: Any,
    *,
    limit: int = 50,
    query: str = DEFAULT_QUERY,
    per_page: int = 25,
    max_pages: int = 2,
    mailto: str = MAILTO,
) -> list[dict[str, Any]]:
    """Fetch up to ``limit`` works and return schema-valid evidence records."""
    fetched = _common.as_datetime(None)
    items = fetch_items(
        client, limit=limit, query=query, per_page=per_page, max_pages=max_pages, mailto=mailto
    )
    return [to_evidence(item, fetched_at=fetched) for item in items]


__all__ = [
    "SOURCE_ID",
    "KIND",
    "LICENCE_STATUS",
    "collect",
    "fetch_items",
    "to_evidence",
]
