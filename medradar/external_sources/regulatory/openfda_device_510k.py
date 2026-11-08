"""openFDA device 510(k) connector.

One 510(k) record = one clearance decision (``regulatory_clearance``).

Date semantics
--------------
``decision_date`` is the clearance decision - an **event** clock.  FDA does not
publish a per-record first-publication timestamp for 510(k), so
``source_public_at`` is derived from the decision date and flagged
``quality="derived"``: it may be described but never used for a lead-time claim.
"""

from __future__ import annotations

from typing import Any, Mapping

from .. import identity, timeq
from . import _common

SOURCE_ID = "openfda_device_510k"
KIND = "regulatory_clearance"
LICENCE_STATUS = "public_domain"

ENDPOINT = "device/510k.json"
DATE_FIELD = "decision_date"
SOURCE_URL = "https://open.fda.gov/apis/device/510k/"

_DERIVED_NOTE = (
    "FDA publishes no per-record first-publication timestamp for 510(k); source_public_at is "
    "derived from decision_date and must be treated as derived/coarse evidence, never as a "
    "published-on date"
)


def normalize(record: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten one 510(k) record into the fields MedRadar actually reads."""
    return {
        "k_number": _common.clean(record.get("k_number")),
        "device_name": _common.clean(record.get("device_name")),
        "applicant": _common.clean(record.get("applicant")),
        "product_code": _common.clean(record.get("product_code")),
        "decision_date": _common.clean(record.get("decision_date")),
        "date_received": _common.clean(record.get("date_received")),
        "decision_code": _common.clean(record.get("decision_code")),
        "decision_description": _common.clean(record.get("decision_description")),
        "clearance_type": _common.clean(record.get("clearance_type")),
        "advisory_committee_description": _common.clean(
            record.get("advisory_committee_description")
        ),
        "statement_or_summary": _common.clean(record.get("statement_or_summary")),
        "country_code": _common.clean(record.get("country_code")),
    }


def to_evidence(
    raw_item: Mapping[str, Any], *, fetched_at: str = "", collection_run_id: str = ""
) -> dict[str, Any]:
    """One ``device/510k`` record -> one v1 evidence record."""
    normalized = normalize(raw_item)
    k_number = normalized["k_number"]
    if not k_number:
        raise ValueError("510(k) record without k_number")
    time_block = _common.build_time(
        event_at=normalized["decision_date"],
        source_public_at=normalized["decision_date"],
        fetched_at=fetched_at,
        quality="derived",
        note=_DERIVED_NOTE,
    )
    ident = _common.identifiers(
        [
            identity.build_identifier("510k", k_number, is_primary=True),
            identity.build_identifier("product_code", normalized["product_code"], note="FDA product code"),
        ]
    )
    return _common.openfda_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=k_number,
        source_url=f"{SOURCE_URL}?search=k_number:{k_number}",
        normalized=normalized,
        item=raw_item,
        time_block=time_block,
        identifiers=ident,
        entity_refs=_common.company_refs(normalized["applicant"]),
        fetched_at=fetched_at,
        collection_run_id=collection_run_id,
    )


def collect(
    client: Any,
    *,
    limit: int = 50,
    search: str = "",
    page_size: int = 1000,
    max_pages: int = 2,
    fetched_at: str = "",
    collection_run_id: str = "",
) -> list[dict[str, Any]]:
    """Bounded collection of real 510(k) records.

    ``search`` defaults to the trailing 12 months of ``decision_date`` so the
    default call is a small recent slice rather than a full-history crawl.
    """
    if not search:
        today = timeq.utc_now().date()
        start = today.replace(year=today.year - 1)
        search = f"{DATE_FIELD}:[{start.isoformat()} TO {today.isoformat()}]"
    items = _common.openfda_search(
        client, ENDPOINT, search=search, limit=limit, page_size=page_size, max_pages=max_pages
    )
    return [to_evidence(item, fetched_at=fetched_at, collection_run_id=collection_run_id) for item in items]
