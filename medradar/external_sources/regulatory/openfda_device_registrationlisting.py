"""openFDA device registration & listing connector.

Establishment-level: one record says *who may distribute what*, so it must never
be counted as a second clearance record.  ``source_record_id`` is the FDA
establishment registration number.

**No date semantics are claimed.**  The probe verified the top-level record keys
only (``establishment_type``, ``k_number``, ``pma_number``, ``products``,
``proprietary_name``, ``registration``); the ``registration`` object's own date
fields were not enumerated, so both clocks stay empty and quality is
``"unknown"`` instead of guessing ``registration_expiration_date``.
"""

from __future__ import annotations

from typing import Any, Mapping

from .. import identity
from . import _common

SOURCE_ID = "openfda_device_registrationlisting"
KIND = "device_registration"
LICENCE_STATUS = "public_domain"

ENDPOINT = "device/registrationlisting.json"
SOURCE_URL = "https://open.fda.gov/apis/device/registrationlisting/"

_NO_CLOCK_NOTE = (
    "the probe enumerated the top-level record keys only; the establishment object's own date "
    "fields were not verified, so no clock is claimed for this source"
)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize(record: Mapping[str, Any]) -> dict[str, Any]:
    registration = record.get("registration") or {}
    if not isinstance(registration, Mapping):
        registration = {}
    products = [p for p in _as_list(record.get("products")) if isinstance(p, Mapping)]
    return {
        "registration_number": _common.clean(registration.get("registration_number")),
        "fei_number": _common.clean(registration.get("fei_number")),
        "registrant_name": _common.clean(registration.get("name")),
        "establishment_type": [str(t) for t in _as_list(record.get("establishment_type"))],
        "k_numbers": [str(k) for k in _as_list(record.get("k_number"))],
        "pma_numbers": [str(p) for p in _as_list(record.get("pma_number"))],
        "proprietary_names": [str(n) for n in _as_list(record.get("proprietary_name"))],
        "product_codes": sorted(
            {
                _common.clean(p.get("product_code"))
                for p in products
                if _common.clean(p.get("product_code"))
            }
        ),
    }


def record_key(normalized: Mapping[str, Any]) -> str:
    key = str(normalized.get("registration_number", "")).strip() or str(
        normalized.get("fei_number", "")
    ).strip()
    if not key:
        raise ValueError("registration/listing record without registration_number or fei_number")
    return key


def to_evidence(
    raw_item: Mapping[str, Any], *, fetched_at: str = "", collection_run_id: str = ""
) -> dict[str, Any]:
    normalized = normalize(raw_item)
    key = record_key(normalized)
    ident = _common.identifiers(
        [
            identity.build_identifier(
                "registration_number", normalized["registration_number"], is_primary=True
            ),
            identity.build_identifier("fei", normalized["fei_number"]),
        ]
        + [identity.build_identifier("510k", k) for k in normalized["k_numbers"]]
        + [identity.build_identifier("pma", p) for p in normalized["pma_numbers"]]
        + [
            identity.build_identifier("product_code", code)
            for code in normalized["product_codes"]
        ]
    )
    return _common.openfda_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=key,
        source_url=f"{SOURCE_URL}?search=registration.registration_number:{key}",
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
        entity_refs=_common.company_refs(normalized["registrant_name"]),
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
    items = _common.openfda_search(
        client, ENDPOINT, search=search, limit=limit, page_size=page_size, max_pages=max_pages
    )
    return [to_evidence(item, fetched_at=fetched_at, collection_run_id=collection_run_id) for item in items]
