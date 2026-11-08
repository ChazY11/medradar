"""openFDA device PMA connector.

A PMA *supplement* is a separate regulatory record, not a re-publication of the
parent approval.  It is given its own ``source_record_id`` (``P123456/007``) and
its own ``pma_supplement`` identifier; because
:func:`schema.canonical_key` prefers a ``pma`` scheme when one is present, a
supplement record deliberately carries **no** plain ``pma`` identifier - adding
one would collapse every supplement of an approval into a single de-duplicated
canonical key and silently under-count post-approval activity.

``decision_date`` is an event clock; ``source_public_at`` is derived from it and
flagged ``quality="derived"`` (FDA publishes no per-record publication date).
"""

from __future__ import annotations

from typing import Any, Mapping

from .. import identity, timeq
from . import _common

SOURCE_ID = "openfda_device_pma"
KIND = "regulatory_clearance"
LICENCE_STATUS = "public_domain"

ENDPOINT = "device/pma.json"
DATE_FIELD = "decision_date"
SOURCE_URL = "https://open.fda.gov/apis/device/pma/"

_DERIVED_NOTE = (
    "FDA publishes no per-record first-publication timestamp for PMA; source_public_at is "
    "derived from decision_date and must be treated as derived evidence, never as published-on"
)


def normalize(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "pma_number": _common.clean(record.get("pma_number")),
        "supplement_number": _common.clean(record.get("supplement_number")),
        "applicant": _common.clean(record.get("applicant")),
        "trade_name": _common.clean(record.get("trade_name")),
        "generic_name": _common.clean(record.get("generic_name")),
        "product_code": _common.clean(record.get("product_code")),
        "decision_date": _common.clean(record.get("decision_date")),
        "date_received": _common.clean(record.get("date_received")),
        "decision_code": _common.clean(record.get("decision_code")),
        "supplement_type": _common.clean(record.get("supplement_type")),
        "supplement_reason": _common.clean(record.get("supplement_reason")),
        "expedited_review_flag": _common.clean(record.get("expedited_review_flag")),
    }


def is_supplement(normalized: Mapping[str, Any]) -> bool:
    number = str(normalized.get("supplement_number", "")).strip()
    return bool(number) and number.lstrip("0") != ""


def record_key(normalized: Mapping[str, Any]) -> str:
    """Stable record identity: ``P123456`` for an original, ``P123456/007`` for a supplement."""
    pma = str(normalized.get("pma_number", "")).strip()
    if not pma:
        raise ValueError("PMA record without pma_number")
    if not is_supplement(normalized):
        return pma
    number = str(normalized.get("supplement_number", "")).strip()
    return f"{pma}/{number.zfill(3) if number.isdigit() else number}"


def to_evidence(
    raw_item: Mapping[str, Any], *, fetched_at: str = "", collection_run_id: str = ""
) -> dict[str, Any]:
    normalized = normalize(raw_item)
    key = record_key(normalized)
    time_block = _common.build_time(
        event_at=normalized["decision_date"],
        source_public_at=normalized["decision_date"],
        fetched_at=fetched_at,
        quality="derived",
        note=_DERIVED_NOTE,
    )
    if is_supplement(normalized):
        ident = [
            identity.build_identifier(
                "pma_supplement", key, is_primary=True, note="PMA supplement, separate decision"
            )
        ]
    else:
        ident = [identity.build_identifier("pma", key, is_primary=True)]
    ident = _common.identifiers(
        ident
        + [
            identity.build_identifier("product_code", normalized["product_code"]),
        ]
    )
    normalized_out = dict(normalized)
    normalized_out["supplement_record"] = is_supplement(normalized)
    return _common.openfda_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=key,
        source_url=f"{SOURCE_URL}?search=pma_number:{normalized['pma_number']}",
        normalized=normalized_out,
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
    if not search:
        today = timeq.utc_now().date()
        start = today.replace(year=today.year - 1)
        search = f"{DATE_FIELD}:[{start.isoformat()} TO {today.isoformat()}]"
    items = _common.openfda_search(
        client, ENDPOINT, search=search, limit=limit, page_size=page_size, max_pages=max_pages
    )
    return [to_evidence(item, fetched_at=fetched_at, collection_run_id=collection_run_id) for item in items]
