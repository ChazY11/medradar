"""Europe PMC REST connector (``publication``).

Timestamp rule
--------------
``source_public_at`` = ``firstPublicationDate`` — Europe PMC's own definition of
the first online publication, whichever of electronic/print came first.  The
journal issue date (``journalInfo.dateOfPublication``, often "2020 Dec", i.e.
coarse) is kept as ``event_at``.  ``firstIndexDate`` and ``dateOfCreation`` are
ingestion clocks and are recorded only under ``metadata_clock_fields``.

Company attribution
-------------------
* ``grantsList.grant[].agency`` -> ``tier="funder"``;
* ``authorList.author[].affiliation`` -> ``tier="author_affiliation"``.

Trial linking
-------------
If the record carries database cross-references, any ``NCT`` identifier found in
that structured block is surfaced as ``normalized.trial_ids``; nothing is
extracted from titles or abstracts.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from .. import identity, schema
from . import _common

SOURCE_ID = "europepmc"
KIND = "publication"
LICENCE_STATUS = "open_licence"
SOURCE_NAME = "Europe PMC"
ATTRIBUTION = "Europe PMC / EMBL-EBI"
BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
DEFAULT_QUERY = "medical device"
RESULT_TYPE = "core"
PAGE_SIZE_MAX = 100


def _identifiers(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    doi = identity.build_identifier("doi", item.get("doi"), is_primary=True)
    if doi:
        out.append(doi)
    pmid = identity.build_identifier("pmid", item.get("pmid"))
    if pmid:
        out.append(pmid)
    pmcid = identity.build_identifier("pmcid", item.get("pmcid"))
    if pmcid:
        out.append(pmcid)
    return out


def _affiliations(item: Mapping[str, Any]) -> list[str]:
    strings: list[str] = []
    authors = ((item.get("authorList") or {}).get("author")) or []
    for author in authors:
        for key in ("affiliation", "authorAffiliationDetailsList"):
            value = author.get(key) if isinstance(author, Mapping) else None
            if isinstance(value, str):
                text = value.strip()
            elif isinstance(value, Mapping):
                text = str(value.get("affiliation") or "").strip()
            else:
                text = ""
            if text and text not in strings:
                strings.append(text)
    top = str(item.get("affiliation") or "").strip()
    if top and top not in strings:
        strings.append(top)
    return strings


def _grants(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    grants = ((item.get("grantsList") or {}).get("grant")) or []
    for grant in grants:
        if not isinstance(grant, Mapping):
            continue
        agency = str(grant.get("agency") or "").strip()
        grant_id = str(grant.get("grantId") or "").strip()
        if grant_id:
            out.append(
                {"value": grant_id, "funder": agency, "field": "grantsList.grant[].grantId"}
            )
    return out


def _funder_names(item: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for grant in ((item.get("grantsList") or {}).get("grant")) or []:
        if isinstance(grant, Mapping):
            agency = str(grant.get("agency") or "").strip()
            if agency and agency not in names:
                names.append(agency)
    return names


def _trial_ids(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    """NCT ids found inside the structured cross-reference block only."""
    block = item.get("dbCrossReferenceList")
    if not block:
        return []
    found: list[str] = _common.nct_ids_in_text(json.dumps(block, ensure_ascii=False))
    return [{"value": nct, "field": "dbCrossReferenceList"} for nct in found]


def to_evidence(raw_item: Mapping[str, Any], *, fetched_at: Any = None) -> dict[str, Any]:
    """One Europe PMC record -> one ``publication`` evidence record."""
    item = dict(raw_item)
    fetched = _common.as_datetime(fetched_at)
    record_id = str(item.get("id") or item.get("pmid") or item.get("doi") or "").strip()
    if not record_id:
        raise ValueError("europepmc item without id/pmid/doi")
    journal_info = item.get("journalInfo") or {}
    public_at = item.get("firstPublicationDate") or item.get("electronicPublicationDate")
    event_at = journal_info.get("dateOfPublication") or item.get("electronicPublicationDate")
    refs = _common.company_refs(_funder_names(item), tier="funder") + _common.company_refs(
        _affiliations(item), tier="author_affiliation"
    )
    normalized = {
        "title": item.get("title"),
        "journal": (journal_info.get("journal") or {}).get("title"),
        "pub_year": item.get("pubYear"),
        "first_publication_date": item.get("firstPublicationDate"),
        "electronic_publication_date": item.get("electronicPublicationDate"),
        "journal_date_of_publication": journal_info.get("dateOfPublication"),
        "doi": item.get("doi"),
        "pmid": item.get("pmid"),
        "pmcid": item.get("pmcid"),
        "publication_status": item.get("publicationStatus"),
        "is_open_access": item.get("isOpenAccess"),
        "author_affiliations": _affiliations(item),
        "funders": _funder_names(item),
        "grant_numbers": _grants(item),
        "trial_ids": _trial_ids(item),
        "metadata_clock_fields": _common.metadata_clock_fields(
            ("firstIndexDate", item.get("firstIndexDate")),
            ("dateOfCreation", item.get("dateOfCreation")),
            ("dateOfRevision", item.get("dateOfRevision")),
        ),
    }
    return schema.make_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=record_id,
        source_url=f"https://europepmc.org/article/{item.get('source') or 'MED'}/{record_id}",
        normalized=normalized,
        raw=_common.raw_block(item),
        time=_common.time_block(
            event_at=event_at,
            source_public_at=public_at,
            fetched_at=fetched,
            notes="firstPublicationDate is the public clock; firstIndexDate/dateOfCreation are ingestion clocks",
        ),
        identifiers=_identifiers(item),
        entity_refs=refs,
        provenance=_common.provenance(
            source_name=SOURCE_NAME,
            licence_status=LICENCE_STATUS,
            attribution=ATTRIBUTION,
            redistribution="record-level licences vary",
            evidence_reference=str(item.get("id") or ""),
            quality=_common.coerce_date(public_at)[1],
        ),
        fetched_at=fetched.isoformat(),
    )


def fetch_items(
    client: Any,
    *,
    limit: int = 50,
    query: str = DEFAULT_QUERY,
    page_size: int = 25,
    max_pages: int = 2,
    result_type: str = RESULT_TYPE,
) -> list[dict[str, Any]]:
    """Bounded cursorMark pagination over ``search``; returns raw result dicts."""
    if limit <= 0:
        return []
    size = max(1, min(int(page_size), PAGE_SIZE_MAX, limit))
    cursor = "*"
    seen: dict[str, dict[str, Any]] = {}
    pages = 0
    while pages < max(1, int(max_pages)) and len(seen) < limit and cursor:
        result = client.get(
            BASE_URL,
            params={
                "query": query,
                "format": "json",
                "pageSize": size,
                "resultType": result_type,
                "cursorMark": cursor,
            },
        )
        pages += 1
        if not result.ok:
            break
        payload = result.json()
        batch = (payload.get("resultList") or {}).get("result") or []
        for item in batch:
            if isinstance(item, Mapping):
                key = str(item.get("id") or item.get("pmid") or item.get("doi") or "")
                if key:
                    seen.setdefault(key, dict(item))
        next_cursor = str(payload.get("nextCursorMark") or "")
        cursor = next_cursor if next_cursor and next_cursor != cursor else ""
        if not batch:
            break
    return list(seen.values())[:limit]


def collect(
    client: Any,
    *,
    limit: int = 50,
    query: str = DEFAULT_QUERY,
    page_size: int = 25,
    max_pages: int = 2,
) -> list[dict[str, Any]]:
    """Fetch up to ``limit`` records and return schema-valid evidence records."""
    fetched = _common.as_datetime(None)
    items = fetch_items(
        client, limit=limit, query=query, page_size=page_size, max_pages=max_pages
    )
    return [to_evidence(item, fetched_at=fetched) for item in items]


__all__ = ["SOURCE_ID", "KIND", "LICENCE_STATUS", "collect", "fetch_items", "to_evidence"]
