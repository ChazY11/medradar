"""USAspending — US federal contract awards (verified 2026-11-09, no API key).

Endpoint
--------
``POST https://api.usaspending.gov/api/v2/search/spending_by_award/``

It is POST-only and takes JSON; :meth:`HttpClient.post_json` exists in
``external_sources.base`` for exactly this shape of official API, so this
connector still goes through the bounded, ledgered client rather than
``requests``.

What this connector deliberately does NOT do
--------------------------------------------
* It does **not** pretend to know when an award became public.  USAspending
  publishes action / signature / performance dates, not a publication date, so
  ``source_public_at`` is left empty with quality ``unknown``.  Substituting
  ``Start Date`` (the period-of-performance start) would fabricate look-ahead,
  which is why :func:`to_evidence` refuses to.
* It does **not** treat ``recipient_search_text`` hits as the firm.  Each
  recipient name is resolved through ``identity.CompanyIndex``; anything that is
  not ``exact_alias`` / ``multi_field`` / ``official_id`` stays a candidate.
* It does **not** infer a device from the free-text description.  There is no
  UDI, model or product code in this schema; a keyword hit is stored as text and
  nothing more.

Field semantics worth knowing
-----------------------------
``Start Date``  period-of-performance start (``event_at`` candidate)
``End Date``    period-of-performance end
``Award Amount`` federal **obligation**, not supplier revenue
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from medradar.external_sources import base as ev_base
from medradar.external_sources import identity as ev_identity
from medradar.external_sources.procurement import common

SOURCE_ID = "usaspending"
SOURCE_NAME = "USAspending (US federal award data)"
KIND = "procurement_award"
LICENCE_STATUS = "public_domain"
ATTRIBUTION = "USAspending.gov, U.S. Department of the Treasury (US federal government work)"
REDISTRIBUTION = "yes"

SEARCH_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
AWARD_DETAIL_URL = "https://api.usaspending.gov/api/v2/awards/{award_id}/"

#: Contract-type codes: BPA call, purchase order, delivery order, definitive contract.
DEFAULT_AWARD_TYPES = ("A", "B", "C", "D")

#: Fields requested from the award search.  ``Description`` is included on
#: purpose: it is the only free-text field and the evidence that no product
#: identifier exists.
DEFAULT_FIELDS = (
    "Award ID",
    "Recipient Name",
    "Award Amount",
    "Start Date",
    "End Date",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Contract Award Type",
    "Description",
    "generated_internal_id",
)

TIME_NOTE = (
    "source_public_at is EMPTY: USAspending publishes no 'first public visibility' "
    "date, only action/signature/performance dates. event_at = period-of-performance "
    "start ('Start Date'), which is an event date and must never be used as a "
    "publication date. first_observed_at is the fetch clock."
)


def build_search_payload(
    *,
    keywords: Iterable[str] | None = None,
    recipient: str | None = None,
    award_types: Iterable[str] = DEFAULT_AWARD_TYPES,
    fields: Iterable[str] = DEFAULT_FIELDS,
    limit: int = 25,
    page: int = 1,
    order: str = "desc",
) -> dict[str, Any]:
    """Build the exact POST body for one award-search page (pure function)."""
    filters: dict[str, Any] = {"award_type_codes": list(award_types)}
    if keywords:
        filters["keywords"] = [str(k) for k in keywords if str(k).strip()]
    if recipient:
        filters["recipient_search_text"] = [str(recipient)]
    return {
        "filters": filters,
        "fields": list(fields),
        "limit": int(limit),
        "page": int(page),
        "sort": "Award Amount",
        "order": order,
    }


def award_record_id(item: Mapping[str, Any]) -> str:
    """Stable record id: ``generated_internal_id`` when present, else Award ID."""
    internal = common.clip(item.get("generated_internal_id"), 200)
    if internal:
        return internal
    award_id = common.clip(item.get("Award ID"), 200)
    if award_id:
        return award_id
    # last resort: a digest of the identifying fields, never a clock
    return "award_" + common.digest(item.get("Award ID"), item.get("Recipient Name"), item.get("Start Date"))


def to_evidence(
    raw_item: Mapping[str, Any],
    *,
    fetched_at: str = "",
    company_index: ev_identity.CompanyIndex | None = None,
    collection_run_id: str = "",
) -> dict[str, Any]:
    """One award row -> one ``procurement_award`` evidence record."""
    fetched = fetched_at or common.utc_iso()
    record_id = award_record_id(raw_item)
    recipient = common.clip(raw_item.get("Recipient Name"), 300)

    start = common.clip(raw_item.get("Start Date"), 40)
    end = common.clip(raw_item.get("End Date"), 40)

    amount = raw_item.get("Award Amount")
    if not isinstance(amount, (int, float)):
        amount = None

    normalized = {
        "award_id": common.clip(raw_item.get("Award ID"), 200),
        "generated_internal_id": common.clip(raw_item.get("generated_internal_id"), 200),
        "recipient_name": recipient,
        "award_amount_usd": amount,
        "amount_semantics": "federal obligation, not supplier revenue",
        "period_of_performance_start": start,
        "period_of_performance_end": end,
        "awarding_agency": common.clip(raw_item.get("Awarding Agency"), 300),
        "awarding_sub_agency": common.clip(raw_item.get("Awarding Sub Agency"), 300),
        "contract_award_type": common.clip(raw_item.get("Contract Award Type"), 100),
        "description": common.clip(raw_item.get("Description"), 1200),
        "product_link": "none - no UDI/model/product code exists in this schema; description is free text",
        "record_type": "award",
        "procurement_stage": "award (post-award action); this source has no tender/notice stage",
    }

    raw_body = common.canonical_json_line(
        {key: (raw_item.get(key) if key in raw_item else None) for key in DEFAULT_FIELDS}
    ).encode("utf-8")
    raw = common.raw_block(raw_body, path=f"{SEARCH_URL}#award:{record_id}")

    identifiers = common.identifier_list(
        ("award_id", raw_item.get("Award ID"), {"is_primary": True, "note": "agency PIID, not globally unique"}),
        ("generated_internal_id", raw_item.get("generated_internal_id"), {}),
    )

    time_block = common.clock_block(
        event_at=start,
        source_public_at=None,
        fetched_at=fetched,
        quality="unknown",
        notes=TIME_NOTE,
    )

    return common.evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=record_id,
        source_url=SEARCH_URL,
        normalized=normalized,
        raw=raw,
        time_block=time_block,
        identifiers=identifiers,
        entity_refs=[common.resolve_company(company_index, recipient, country="US")] if recipient else [],
        source_name=SOURCE_NAME,
        licence_status=LICENCE_STATUS,
        attribution=ATTRIBUTION,
        redistribution=REDISTRIBUTION,
        fetched_at=fetched,
        collection_run_id=collection_run_id,
    )


def collect(
    client: Any,
    *,
    limit: int = 50,
    keywords: Iterable[str] | None = None,
    recipient: str | None = None,
    page_size: int = 25,
    max_pages: int = 3,
    company_index: ev_identity.CompanyIndex | None = None,
    fetched_at: str = "",
    collection_run_id: str = "",
) -> list[dict[str, Any]]:
    """Collect at most ``limit`` award records, walking at most ``max_pages`` pages.

    Both the record count and the page count are bounded, so a caller cannot turn
    this into an unbounded crawl by passing a large ``limit``.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    fetched = fetched_at or ev_base.utc_iso()
    size = max(1, min(int(page_size), 100, limit))
    remaining = int(limit)
    records: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        if remaining <= 0:
            break
        requested = max(1, min(size, remaining))
        payload = build_search_payload(
            keywords=keywords, recipient=recipient, limit=requested, page=page
        )
        result = client.post_json(SEARCH_URL, payload)
        if not result.ok:
            break
        try:
            body = result.json() or {}
        except Exception:
            break
        rows = body.get("results") or []
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            if remaining <= 0:
                break
            if not isinstance(row, dict):
                continue
            records.append(
                to_evidence(
                    row,
                    fetched_at=fetched,
                    company_index=company_index,
                    collection_run_id=collection_run_id,
                )
            )
            remaining -= 1
        # a short page means the result set is exhausted; do not ask for more
        if len(rows) < requested:
            break
    return records


def fetch_award_detail(client: Any, award_generated_id: str) -> dict[str, Any] | None:
    """Award detail (the only place ``date_signed`` is published).  One request."""
    if not award_generated_id:
        return None
    result = client.get(AWARD_DETAIL_URL.format(award_id=award_generated_id))
    if not result.ok:
        return None
    try:
        return result.json()
    except Exception:
        return None


def signature_date_mismatch(detail: Mapping[str, Any]) -> dict[str, Any]:
    """Compare the signature date with the performance start, without conflating them.

    Returns both, plus the gap in days.  A gap is normal (a contract can be signed
    before performance starts); collapsing the two fields into one date is what
    this helper exists to prevent.
    """
    signed = common.clip((detail or {}).get("date_signed"), 40)
    pop = detail.get("period_of_performance") or {}
    start = common.clip(pop.get("start_date"), 40) if isinstance(pop, Mapping) else ""
    from medradar.external_sources import timeq  # local import keeps module import clock-free

    gap = timeq.lead_time_days(signed, start)
    return {
        "date_signed": signed,
        "period_of_performance_start": start,
        "days_between_signature_and_performance_start": gap,
        "note": "date_signed and performance start are different facts; neither is a publication date",
    }


__all__ = [
    "ATTRIBUTION",
    "AWARD_DETAIL_URL",
    "DEFAULT_AWARD_TYPES",
    "DEFAULT_FIELDS",
    "KIND",
    "LICENCE_STATUS",
    "SEARCH_URL",
    "SOURCE_ID",
    "SOURCE_NAME",
    "TIME_NOTE",
    "award_record_id",
    "build_search_payload",
    "collect",
    "fetch_award_detail",
    "signature_date_mismatch",
    "to_evidence",
]
