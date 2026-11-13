"""Shared plumbing for the regulatory connectors.

Everything here is pure or takes an explicit ``HttpClient``; importing this
module never touches the network.

Two conventions that matter for the schema and are applied everywhere below:

``raw`` block
    A connector works on one *source record* that arrived inside a paginated
    page.  The page bytes are hashed and stored by the probe pass
    (``samples/<source_id>/``); per evidence record we hash the canonical JSON
    of that single record.  That keeps ``raw.content_hash`` reproducible and
    keeps one evidence item bound to one record, which is what the contract
    promises.

``source_public_at``
    Several device sources publish only an *event* date (a clearance decision,
    a licence issue date) and no per-record publication date.  Those
    connectors set ``source_public_at`` to the event date but pass
    ``quality="derived"`` and a note, so
    :func:`timeq.quality_allows_lead_time` refuses to use it for lead-time
    claims.  ``quality="derived"`` is never used for a date the source really
    published (GUDID's ``devicePublishDate`` gets ``quality="day"``).
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Sequence

from .. import identity, schema, timeq

OPENFDA = "https://api.fda.gov"

OPENFDA_PROVENANCE: dict[str, Any] = {
    "source_name": "openFDA (U.S. Food and Drug Administration)",
    "licence_status": "public_domain",
    "redistribution": "allowed",
    "attribution": "Data provided by the U.S. Food and Drug Administration (open.fda.gov), CC0 1.0",
    "evidence_reference": "https://open.fda.gov/license/",
    "source_time_quality": "day",
}


def raw_block(item: Mapping[str, Any], *, path: str = "") -> dict[str, Any]:
    """Deterministic raw descriptor for one source record."""
    payload = json.dumps(dict(item), ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {"content_hash": schema.sha256_bytes(payload), "bytes": len(payload), "path": path}


def company_refs(
    name: Any, *, country: str = "", extra_note: str = ""
) -> list[dict[str, Any]]:
    """Resolve one source company string through the shared alias index.

    A ``candidate`` result is returned unchanged (confidence < 0.9) - the
    caller must not promote it.  ``none`` results are dropped: an unresolved
    string is not evidence of a link.
    """
    resolution = identity.CompanyIndex.from_config().resolve(name, country=country)
    if resolution.get("method") == "none":
        return []
    resolution = dict(resolution)
    if extra_note:
        resolution["note"] = (str(resolution.get("note", "")) + " " + extra_note).strip()
    return [resolution]


def build_time(
    *,
    event_at: Any,
    source_public_at: Any,
    fetched_at: str,
    quality: str,
    note: str,
) -> dict[str, Any]:
    """Four-clock block with an explicit publication-quality decision."""
    return timeq.build_time(
        event_at=event_at,
        source_public_at=source_public_at,
        quality=quality,
        fetched_at=timeq.parse_datetime(fetched_at) or timeq.utc_now(),
        notes=note,
    )


def openfda_search(
    client: Any,
    endpoint: str,
    *,
    search: str,
    limit: int,
    page_size: int = 1000,
    max_pages: int = 5,
) -> list[dict[str, Any]]:
    """Bounded ``skip``-pagination over one openFDA endpoint.

    openFDA caps ``skip`` at 25,000, so this also refuses to page past that
    ceiling instead of silently asking for a 404.
    """
    limit = max(0, int(limit))
    page_size = max(1, min(int(page_size), 1000))
    collected: list[dict[str, Any]] = []
    skip = 0
    for _ in range(max(0, int(max_pages))):
        want = min(page_size, limit - len(collected))
        if want <= 0 or skip >= 25_000:
            break
        result = client.get(
            f"{OPENFDA}/{endpoint}", params={"search": search, "limit": want, "skip": skip}
        )
        if not result.ok:
            break
        try:
            payload = result.json()
        except ValueError:
            break
        items = payload.get("results") or []
        if not items:
            break
        collected.extend(item for item in items if isinstance(item, dict))
        skip += len(items)
        if len(items) < want:
            break
    return collected[:limit]


def openfda_evidence(
    *,
    source_id: str,
    kind: str,
    source_record_id: str,
    source_url: str,
    normalized: Mapping[str, Any],
    item: Mapping[str, Any],
    time_block: Mapping[str, Any],
    identifiers: Iterable[Mapping[str, Any]],
    entity_refs: Iterable[Mapping[str, Any]] = (),
    fetched_at: str,
    collection_run_id: str = "",
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return schema.make_evidence(
        source_id=source_id,
        kind=kind,
        source_record_id=source_record_id,
        source_url=source_url,
        normalized=normalized,
        raw=raw_block(item),
        time=time_block,
        identifiers=list(identifiers),
        entity_refs=list(entity_refs),
        provenance=dict(provenance or OPENFDA_PROVENANCE),
        collection_run_id=collection_run_id,
        fetched_at=fetched_at,
    )


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def identifiers(items: Sequence[Any]) -> list[dict[str, Any]]:
    """Drop ``None`` entries produced by :func:`identity.build_identifier`."""
    return [item for item in items if item]


def require_valid(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate every record; raise on the first contract violation."""
    out: list[dict[str, Any]] = []
    for record in records:
        schema.require_valid(record)
        out.append(dict(record))
    return out
