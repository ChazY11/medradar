"""Health Canada MDALL connector (device licences, devices, UDI identifiers).

Documented JSON API, no key: ``company`` -> ``licence`` -> ``device`` ->
``deviceidentifier``.  The ``deviceidentifier`` endpoint accepts a real UDI-DI,
which makes MDALL the one market where an official endpoint resolves a DI to a
national product licence.

Date semantics
--------------
MDALL publishes **no** per-record first-publication date.  This is exactly the
trap the collection protocol names:

* ``last_refresh_dt`` is a database refresh stamp - using it would make every
  licence look freshly published;
* ``end_date`` is a cancellation/expiry date - never a first-publication date;
* ``first_licence_status_dt`` (licence) and ``first_licence_dt`` (device) are the
  only defensible dates.  They are an **event** clock, so ``source_public_at``
  is derived from them and flagged ``quality="derived"``.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .. import identity
from . import _common

SOURCE_ID = "canada_mdall"
KIND = "device_registration"
LICENCE_STATUS = "open_licence"

BASE = "https://health-products.canada.ca/api/medical-devices"
SOURCE_URL = "https://health-products.canada.ca/mdall-limh/"
DOC_URL = "https://health-products.canada.ca/api/documentation/mdall-documentation-en.html"

PROVENANCE: dict[str, Any] = {
    "source_name": "Health Canada - Medical Devices Active Licence Listing (MDALL)",
    "licence_status": "open_licence",
    "redistribution": "allowed",
    "attribution": "Contains information licensed under the Open Government Licence - Canada",
    "evidence_reference": "https://open.canada.ca/data/en/dataset/c801a084-210b-4cd2-8513-26a00b66eb6f",
    "source_time_quality": "derived",
}

_DERIVED_NOTE = (
    "MDALL publishes no per-record publication date; source_public_at is derived from the licence "
    "issue date. last_refresh_dt is a database refresh stamp and end_date is a cancellation date - "
    "neither may be used as a first-publication date"
)


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        return [payload]
    return []


def normalize_licence(record: Mapping[str, Any]) -> dict[str, Any]:
    """Project one MDALL licence row onto the fields we store."""
    return {
        "licence_number": _common.clean(record.get("original_licence_no")),
        "licence_status": _common.clean(record.get("licence_status")),
        "licence_name": _common.clean(record.get("licence_name")),
        "licence_type_cd": _common.clean(record.get("licence_type_cd")),
        "licence_type_desc": _common.clean(record.get("licence_type_desc")),
        "application_id": _common.clean(record.get("application_id")),
        "appl_risk_class": record.get("appl_risk_class"),
        "company_id": record.get("company_id"),
        "first_licence_status_dt": _common.clean(record.get("first_licence_status_dt")),
        "last_refresh_dt": _common.clean(record.get("last_refresh_dt")),
        "end_date": _common.clean(record.get("end_date")),
    }


def normalize_device(record: Mapping[str, Any]) -> dict[str, Any]:
    """Project one MDALL device row (a device inside a licence)."""
    return {
        "device_id": record.get("device_id"),
        "licence_number": _common.clean(record.get("original_licence_no")),
        "trade_name": _common.clean(record.get("trade_name")),
        "first_licence_dt": _common.clean(record.get("first_licence_dt")),
        "end_date": _common.clean(record.get("end_date")),
    }


def to_evidence(
    raw_item: Mapping[str, Any],
    *,
    devices: Sequence[Mapping[str, Any]] = (),
    company_name: str = "",
    fetched_at: str = "",
    collection_run_id: str = "",
) -> dict[str, Any]:
    """One licence row -> one evidence record (devices folded in as trade names)."""
    normalized = normalize_licence(raw_item)
    number = normalized["licence_number"]
    if not number:
        raise ValueError("MDALL licence record without original_licence_no")
    normalized["devices"] = [normalize_device(row) for row in devices]
    normalized["company_name"] = company_name
    normalized["device_count"] = len(normalized["devices"])
    idents = _common.identifiers(
        [
            identity.build_identifier("licence_no", number, is_primary=True),
            identity.build_identifier("company_id", normalized["company_id"]),
        ]
    )
    time_block = _common.build_time(
        event_at=normalized["first_licence_status_dt"],
        source_public_at=normalized["first_licence_status_dt"],
        fetched_at=fetched_at,
        quality="derived",
        note=_DERIVED_NOTE,
    )
    return _common.openfda_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=number,
        source_url=f"{BASE}/licence/?id={number}&lang=en&type=json",
        normalized=normalized,
        item=raw_item,
        time_block=time_block,
        identifiers=idents,
        entity_refs=_common.company_refs(company_name or normalized["licence_name"]),
        fetched_at=fetched_at,
        collection_run_id=collection_run_id,
        provenance=PROVENANCE,
    )


# ------------------------------------------------------------------ API helpers
def companies(client: Any, name: str) -> list[dict[str, Any]]:
    """``/company/?company_name=`` - a %LIKE% match, so expect subsidiaries and noise."""
    result = client.get(f"{BASE}/company/", params={"company_name": name, "type": "json"})
    if not result.ok:
        return []
    try:
        return _rows(result.json())
    except ValueError:
        return []


def licences(client: Any, *, company_id: Any = None, state: str = "active") -> list[dict[str, Any]]:
    params: dict[str, Any] = {"state": state, "lang": "en", "type": "json"}
    if company_id is not None:
        params["company_id"] = company_id
    result = client.get(f"{BASE}/licence/", params=params)
    if not result.ok:
        return []
    try:
        return _rows(result.json())
    except ValueError:
        return []


def devices(client: Any, licence_number: Any) -> list[dict[str, Any]]:
    result = client.get(
        f"{BASE}/device/", params={"licence_number": licence_number, "type": "json"}
    )
    if not result.ok:
        return []
    try:
        return _rows(result.json())
    except ValueError:
        return []


def device_identifiers(client: Any, di: str, *, state: str = "active") -> list[dict[str, Any]]:
    """Official DI bridge: MDALL rows for a real UDI-DI (empty when Canada never licensed it)."""
    result = client.get(
        f"{BASE}/deviceidentifier/",
        params={"device_identifier": identity.normalize_di(di), "state": state, "type": "json"},
    )
    if not result.ok:
        return []
    try:
        return _rows(result.json())
    except ValueError:
        return []


def collect(
    client: Any,
    *,
    company_name: str = "",
    company_id: Any = None,
    max_licences: int = 20,
    with_devices: bool = False,
    fetched_at: str = "",
    collection_run_id: str = "",
) -> list[dict[str, Any]]:
    """Bounded licence collection for one company (or one explicit ``company_id``).

    Company lookup goes through the API's %LIKE% search, so ``company_name`` is a
    *hint*: the caller should pass a ``company_id`` once the alias index has
    picked the right entity.  ``max_licences`` bounds the work explicitly.
    """
    resolved_name = company_name
    if company_id is None:
        if not company_name:
            raise ValueError("collect() needs company_name or company_id")
        candidates = companies(client, company_name)
        for row in candidates:
            raw = _common.clean(row.get("company_name"))
            resolution = identity.CompanyIndex.from_config().resolve(raw)
            if resolution.get("method") in {"exact_alias", "multi_field"}:
                company_id = row.get("company_id")
                resolved_name = raw
                break
        if company_id is None and candidates:
            company_id = candidates[0].get("company_id")
            resolved_name = _common.clean(candidates[0].get("company_name"))
    rows = licences(client, company_id=company_id)[: max(0, int(max_licences))]
    out: list[dict[str, Any]] = []
    for row in rows:
        device_rows: list[dict[str, Any]] = []
        if with_devices:
            number = _common.clean(row.get("original_licence_no"))
            if number:
                device_rows = devices(client, number)
        out.append(
            to_evidence(
                row,
                devices=device_rows,
                company_name=resolved_name,
                fetched_at=fetched_at,
                collection_run_id=collection_run_id,
            )
        )
    return out
