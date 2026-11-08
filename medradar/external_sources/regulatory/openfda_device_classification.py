"""openFDA device classification (product-code dictionary) connector.

The dictionary is small (~7,097 codes) and is the join key that turns a 510(k) or
PMA ``product_code`` into a device family, a risk class and a 21 CFR regulation.

**No event clock exists.**  FDA publishes the *current* value of a code with no
effective date, so this connector sets ``event_at`` and ``source_public_at`` to
``""`` and ``source_public_at_quality`` to ``"unknown"``.  Dating a
classification with the fetch day would fabricate a history the source does not
have: a code's class must never be attributed to a past clearance date.

``kind`` is ``device_registration`` because the schema's kind vocabulary has no
"classification dictionary" member; the record is still a documented regulatory
fact about one product code.
"""

from __future__ import annotations

from typing import Any, Mapping

from .. import identity, timeq
from . import _common

SOURCE_ID = "openfda_device_classification"
KIND = "device_registration"
LICENCE_STATUS = "public_domain"

ENDPOINT = "device/classification.json"
SOURCE_URL = "https://open.fda.gov/apis/device/classification/"

_NO_CLOCK_NOTE = (
    "the classification dictionary is a live snapshot: FDA publishes no effective date and no "
    "publication date per product code, so both clocks stay empty rather than being back-filled "
    "with the fetch day"
)


def normalize(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "product_code": _common.clean(record.get("product_code")),
        "device_name": _common.clean(record.get("device_name")),
        "device_class": _common.clean(record.get("device_class")),
        "regulation_number": _common.clean(record.get("regulation_number")),
        "medical_specialty_description": _common.clean(
            record.get("medical_specialty_description")
        ),
        "definition": _common.clean(record.get("definition")),
        "implant_flag": _common.clean(record.get("implant_flag")),
        "life_sustain_support_flag": _common.clean(record.get("life_sustain_support_flag")),
        "gmp_exempt_flag": _common.clean(record.get("gmp_exempt_flag")),
        "submission_type_id": _common.clean(record.get("submission_type_id")),
    }


def to_evidence(
    raw_item: Mapping[str, Any], *, fetched_at: str = "", collection_run_id: str = ""
) -> dict[str, Any]:
    normalized = normalize(raw_item)
    code = normalized["product_code"]
    if not code:
        raise ValueError("classification record without product_code")
    ident = _common.identifiers(
        [
            identity.build_identifier("product_code", code, is_primary=True),
            identity.build_identifier(
                "regulation_number", normalized["regulation_number"], note="21 CFR citation"
            ),
        ]
    )
    return _common.openfda_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=code,
        source_url=f"{SOURCE_URL}?search=product_code:%22{code}%22",
        normalized=normalized,
        item=raw_item,
        time_block=_common.build_time(
            event_at=None,
            source_public_at=None,
            fetched_at=fetched_at,
            quality="unknown",
            note=_NO_CLOCK_NOTE,
        ),
        identifiers=ident,
        entity_refs=(),
        fetched_at=fetched_at,
        collection_run_id=collection_run_id,
    )


def collect(
    client: Any,
    *,
    limit: int = 2000,
    search: str = "",
    page_size: int = 1000,
    max_pages: int = 8,
    fetched_at: str = "",
    collection_run_id: str = "",
) -> list[dict[str, Any]]:
    """Pull up to ``limit`` product codes; the whole dictionary is ~7,097 rows."""
    items = _common.openfda_search(
        client, ENDPOINT, search=search, limit=limit, page_size=page_size, max_pages=max_pages
    )
    return [to_evidence(item, fetched_at=fetched_at, collection_run_id=collection_run_id) for item in items]


__all__ = ["SOURCE_ID", "KIND", "LICENCE_STATUS", "collect", "normalize", "to_evidence", "timeq"]
