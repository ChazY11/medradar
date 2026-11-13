"""Crossref REST connector (``publication``).

Timestamp rule
--------------
``source_public_at`` = ``published-online`` when present, else ``published-print``
or ``issued`` (first public visibility of the DOI record).  ``event_at`` = the
print/issue date, which is what most downstream studies mean by "publication
date".  ``created`` and ``deposited`` are **DOI registration clocks** and are
recorded only as ``metadata_clock_fields``.

Company attribution
-------------------
* ``funder[].name`` -> ``tier="funder"``;
* ``author[].affiliation[].name`` -> ``tier="author_affiliation"``.

Grant linking
-------------
``funder[].award[]`` is the structured award list; each award string is surfaced
as ``normalized.grant_numbers`` so :mod:`linking` can match it against grant
records.  No award number is derived from a free-text field.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from .. import identity, schema
from . import _common

SOURCE_ID = "crossref"
KIND = "publication"
LICENCE_STATUS = "open_licence"
SOURCE_NAME = "Crossref"
ATTRIBUTION = "Crossref REST API"
BASE_URL = "https://api.crossref.org/works"
MAILTO = "medradar.research@example.org"
DEFAULT_QUERY = "medical device"


def _date_from_parts(value: Any) -> tuple[str, str]:
    """Crossref ``date-parts`` -> ``(iso_date, quality)`` without inflating precision."""
    if not isinstance(value, Mapping):
        return "", "unknown"
    parts = value.get("date-parts") or []
    if not parts or not isinstance(parts[0], Sequence) or not parts[0]:
        return "", "unknown"
    numbers = list(parts[0])
    try:
        year = int(numbers[0])
    except (TypeError, ValueError):
        return "", "unknown"
    if len(numbers) >= 3:
        return f"{year:04d}-{int(numbers[1]):02d}-{int(numbers[2]):02d}", "day"
    if len(numbers) == 2:
        return f"{year:04d}-{int(numbers[1]):02d}-01", "coarse"
    return f"{year:04d}-01-01", "coarse"


def _identifiers(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    doi = identity.build_identifier("doi", item.get("DOI"), is_primary=True)
    if doi:
        out.append(doi)
    return out


def _titles(item: Mapping[str, Any]) -> str:
    titles = item.get("title") or []
    if isinstance(titles, list) and titles:
        return str(titles[0])
    return str(titles) if titles else ""


def _funder_entries(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for funder in item.get("funder") or []:
        if not isinstance(funder, Mapping):
            continue
        name = str(funder.get("name") or "").strip()
        award = funder.get("award") or []
        if isinstance(award, str):
            award = [award]
        for award_id in award:
            award_id = str(award_id or "").strip()
            if award_id:
                out.append(
                    {"value": award_id, "funder": name, "field": "funder[].award"}
                )
    return out


def _funder_names(item: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for funder in item.get("funder") or []:
        if not isinstance(funder, Mapping):
            continue
        name = str(funder.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _affiliations(item: Mapping[str, Any]) -> list[str]:
    strings: list[str] = []
    for author in item.get("author") or []:
        if not isinstance(author, Mapping):
            continue
        for affiliation in author.get("affiliation") or []:
            name = str(affiliation.get("name") or "").strip() if isinstance(affiliation, Mapping) else ""
            if name and name not in strings:
                strings.append(name)
    return strings


def _trial_ids(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    relation = item.get("relation")
    if not relation:
        return []
    found = _common.nct_ids_in_text(json.dumps(relation, ensure_ascii=False))
    return [{"value": nct, "field": "relation"} for nct in found]


def to_evidence(raw_item: Mapping[str, Any], *, fetched_at: Any = None) -> dict[str, Any]:
    """One Crossref work -> one ``publication`` evidence record."""
    item = dict(raw_item)
    fetched = _common.as_datetime(fetched_at)
    doi = str(item.get("DOI") or "").strip()
    if not doi:
        raise ValueError("crossref item without DOI")
    online_date, online_quality = _date_from_parts(item.get("published-online"))
    print_date, _ = _date_from_parts(item.get("published-print"))
    issued_date, _ = _date_from_parts(item.get("issued"))
    public_date = online_date or print_date or issued_date
    if online_date:
        public_quality = online_quality
    else:
        public_quality = _common.coerce_date(public_date)[1]
    normalized = {
        "title": _titles(item),
        "type": item.get("type"),
        "container_title": (item.get("container-title") or [None])[0]
        if isinstance(item.get("container-title"), list)
        else item.get("container-title"),
        "publisher": item.get("publisher"),
        "published_online": online_date,
        "published_print": print_date,
        "issued": issued_date,
        "doi": doi,
        "url": item.get("URL"),
        "funder_names": _funder_names(item),
        "grant_numbers": _funder_entries(item),
        "author_affiliations": _affiliations(item),
        "trial_ids": _trial_ids(item),
        "subject_count": len(item.get("subject") or []),
        "metadata_clock_fields": _common.metadata_clock_fields(
            ("created", (item.get("created") or {}).get("date-time")),
            ("deposited", (item.get("deposited") or {}).get("date-time")),
            ("indexed", (item.get("indexed") or {}).get("date-time")),
        ),
    }
    refs = _common.company_refs(_funder_names(item), tier="funder") + _common.company_refs(
        _affiliations(item), tier="author_affiliation"
    )
    return schema.make_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=doi,
        source_url=str(item.get("URL") or f"https://doi.org/{doi}"),
        normalized=normalized,
        raw=_common.raw_block(item),
        time=_common.time_block(
            event_at=print_date or issued_date,
            source_public_at=public_date,
            fetched_at=fetched,
            notes="published-online preferred for the public clock; created/deposited are registration clocks and are not used",
        ),
        identifiers=_identifiers(item),
        entity_refs=refs,
        provenance=_common.provenance(
            source_name=SOURCE_NAME,
            licence_status=LICENCE_STATUS,
            attribution=ATTRIBUTION,
            redistribution="metadata openly available; per-record licence[] varies",
            evidence_reference=f"https://doi.org/{doi}",
            quality=public_quality,
        ),
        fetched_at=fetched.isoformat(),
    )


def fetch_items(
    client: Any,
    *,
    limit: int = 50,
    query: str = DEFAULT_QUERY,
    rows: int = 25,
    max_pages: int = 2,
    mailto: str = MAILTO,
    extra_filter: str = "",
) -> list[dict[str, Any]]:
    """Bounded cursor pagination over ``/works``; returns raw work dicts."""
    if limit <= 0:
        return []
    size = max(1, min(int(rows), 1000, limit))
    cursor = "*"
    seen: dict[str, dict[str, Any]] = {}
    pages = 0
    while pages < max(1, int(max_pages)) and len(seen) < limit and cursor:
        params: dict[str, Any] = {
            "query": query,
            "rows": size,
            "cursor": cursor,
            "mailto": mailto,
        }
        if extra_filter:
            params["filter"] = extra_filter
        result = client.get(BASE_URL, params=params)
        pages += 1
        if not result.ok:
            break
        payload = result.json()
        message = payload.get("message") or {}
        for item in message.get("items") or []:
            if isinstance(item, Mapping) and item.get("DOI"):
                seen.setdefault(str(item["DOI"]).lower(), dict(item))
        next_cursor = str(message.get("next-cursor") or "")
        cursor = next_cursor if next_cursor and next_cursor != cursor else ""
        if not message.get("items"):
            break
    return list(seen.values())[:limit]


def collect(
    client: Any,
    *,
    limit: int = 50,
    query: str = DEFAULT_QUERY,
    rows: int = 25,
    max_pages: int = 2,
    mailto: str = MAILTO,
    extra_filter: str = "",
) -> list[dict[str, Any]]:
    """Fetch up to ``limit`` works and return schema-valid evidence records."""
    fetched = _common.as_datetime(None)
    items = fetch_items(
        client,
        limit=limit,
        query=query,
        rows=rows,
        max_pages=max_pages,
        mailto=mailto,
        extra_filter=extra_filter,
    )
    return [to_evidence(item, fetched_at=fetched) for item in items]


__all__ = ["SOURCE_ID", "KIND", "LICENCE_STATUS", "collect", "fetch_items", "to_evidence"]
