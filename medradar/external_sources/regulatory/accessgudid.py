"""AccessGUDID (NLM) connector - GUDID device lookup by UDI-DI.

AccessGUDID and openFDA ``device/udi.json`` publish the *same* GUDID record: the
probe showed the same DI returning the same ``publicDeviceRecordKey`` on both
interfaces.  They are therefore one evidence item, not two sources, so this
connector uses the ``di`` identifier scheme and lets
:func:`schema.canonical_key` collapse the two to a single canonical key.

Date semantics
--------------
``devicePublishDate`` is a genuine per-record first-publication date -> it is the
``source_public_at`` with ``quality="day"``.
``publicVersionDate`` is a version stamp.  Using it as a publication date makes
every record look freshly published, so it is kept in ``normalized`` and
explicitly flagged, never promoted to a clock.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .. import identity, timeq
from . import _common

SOURCE_ID = "accessgudid"
KIND = "device_registration"
LICENCE_STATUS = "open_licence"

LOOKUP_URL = "https://accessgudid.nlm.nih.gov/api/v3/devices/lookup"
SOURCE_URL = "https://accessgudid.nlm.nih.gov/"

PROVENANCE: dict[str, Any] = {
    "source_name": "AccessGUDID (U.S. National Library of Medicine / FDA GUDID)",
    "licence_status": "open_licence",
    "redistribution": "allowed",
    "attribution": "GUDID data, U.S. Food and Drug Administration / NLM AccessGUDID",
    "evidence_reference": "https://accessgudid.nlm.nih.gov/download",
    "source_time_quality": "day",
}


def _identifiers_of(device: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    block = device.get("identifiers") or {}
    rows = block.get("identifier") or [] if isinstance(block, Mapping) else block
    if isinstance(rows, Mapping):
        rows = [rows]
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        di = row.get("deviceId")
        out.append(
            identity.build_identifier(
                "di",
                di,
                is_primary=str(row.get("deviceIdType", "")).lower() == "primary",
                note=_common.clean(row.get("deviceIdIssuingAgency")),
            )
        )
    return _common.identifiers(out)


def normalize(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Project one AccessGUDID ``lookup`` response onto the fields we store."""
    gudid = payload.get("gudid") or {}
    device = gudid.get("device") or {}
    if not isinstance(device, Mapping):
        device = {}
    return {
        "public_device_record_key": _common.clean(device.get("publicDeviceRecordKey")),
        "public_version_status": _common.clean(device.get("publicVersionStatus")),
        "device_record_status": _common.clean(device.get("deviceRecordStatus")),
        "public_version_number": device.get("publicVersionNumber"),
        "public_version_date": _common.clean(device.get("publicVersionDate")),
        "device_publish_date": _common.clean(device.get("devicePublishDate")),
        "device_comm_distribution_status": _common.clean(
            device.get("deviceCommDistributionStatus")
        ),
        "device_comm_distribution_end_date": _common.clean(
            device.get("deviceCommDistributionEndDate")
        ),
        "brand_name": _common.clean(device.get("brandName")),
        "company_name": _common.clean(device.get("companyName")),
        "version_or_model_number": _common.clean(device.get("versionOrModelNumber")),
        "gmdn_terms": _common.clean(device.get("gmdnTerms")),
    }


def primary_di(normalized: Mapping[str, Any]) -> str:
    for ident in normalized.get("identifiers", []):  # pragma: no cover - defensive
        if ident.get("scheme") == "di" and ident.get("is_primary"):
            return str(ident.get("value", ""))
    return ""


def to_evidence(
    raw_item: Mapping[str, Any], *, fetched_at: str = "", collection_run_id: str = ""
) -> dict[str, Any]:
    """One ``lookup`` response -> one evidence record."""
    normalized = normalize(raw_item)
    idents = _identifiers_of((raw_item.get("gudid") or {}).get("device") or {})
    if not idents:
        raise ValueError("AccessGUDID record without any device identifier")
    key = normalized["public_device_record_key"] or idents[0]["value"]
    time_block = _common.build_time(
        event_at=None,
        source_public_at=normalized["device_publish_date"],
        fetched_at=fetched_at,
        quality="day",
        note=(
            "devicePublishDate is GUDID's per-record first-publication date; publicVersionDate is "
            "a version stamp and is deliberately NOT used as a clock"
        ),
    )
    return _common.openfda_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=key,
        source_url=f"{LOOKUP_URL}?di={idents[0]['value']}",
        normalized=normalized,
        item=raw_item,
        time_block=time_block,
        identifiers=idents,
        entity_refs=_common.company_refs(normalized["company_name"]),
        fetched_at=fetched_at,
        collection_run_id=collection_run_id,
        provenance=PROVENANCE,
    )


def lookup(client: Any, di: str) -> dict[str, Any] | None:
    """One DI -> its GUDID record, or ``None`` when GUDID does not know the DI."""
    result = client.get(LOOKUP_URL, params={"di": identity.normalize_di(di)})
    if not result.ok:
        return None
    try:
        payload = result.json()
    except ValueError:
        return None
    if not isinstance(payload, Mapping) or not payload.get("gudid"):
        return None
    return payload


def collect(
    client: Any,
    *,
    dis: Sequence[str] = (),
    limit: int = 20,
    fetched_at: str = "",
    collection_run_id: str = "",
) -> list[dict[str, Any]]:
    """Resolve an explicit, bounded list of DIs.

    There is no documented bulk enumeration on this endpoint (a full mirror has
    to come from the GUDID release files), so the caller must supply the DIs.
    """
    out: list[dict[str, Any]] = []
    for di in list(dis)[: max(0, int(limit))]:
        payload = lookup(client, di)
        if payload is None:
            continue
        out.append(
            to_evidence(payload, fetched_at=fetched_at, collection_run_id=collection_run_id)
        )
    return out


__all__ = [
    "SOURCE_ID",
    "KIND",
    "LICENCE_STATUS",
    "LOOKUP_URL",
    "collect",
    "lookup",
    "normalize",
    "to_evidence",
    "timeq",
]
