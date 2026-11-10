"""AccessGUDID connector: official GUDID lookup by UDI-DI.

AccessGUDID and openFDA ``device/udi.json`` publish the *same* GUDID record.
ATLAS therefore records the shared upstream authority
(``fda_gudid``) so that a matching DI from the two interfaces is a
**duplicate**, not two independent confirmations.  This is exactly the trap
that inflates naive "cross-source corroboration" counts.

Date semantics
--------------
``devicePublishDate`` is the per-record first-publication date (day quality).
``publicVersionDate`` is a version stamp and is deliberately not used as a clock.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..evidence.timeq import build_time
from ..identity.normalize import build_identifier, normalize_di
from .base import Connector, clean, provenance_of

SOURCE_ID = "accessgudid"
LOOKUP_URL = "https://accessgudid.nlm.nih.gov/api/v3/devices/lookup.json"


def _rows(value: Any) -> list[JSONDict]:
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    return []


JSONDict = Mapping[str, Any]


def identifiers_of(device: Mapping[str, Any]) -> list[dict[str, Any]]:
    block = device.get("identifiers") or {}
    rows = _rows(block.get("identifier")) if isinstance(block, Mapping) else _rows(block)
    out = []
    for row in rows:
        out.append(
            build_identifier(
                "di", row.get("deviceId"),
                is_primary=str(row.get("deviceIdType", "")).lower() == "primary",
                note=clean(row.get("deviceIdIssuingAgency")),
            )
        )
    return [i for i in out if i]


def normalize(payload: Mapping[str, Any]) -> dict[str, Any]:
    gudid = payload.get("gudid") or {}
    device = gudid.get("device") or {}
    codes = [
        clean(c.get("productCode"))
        for c in _rows((device.get("productCodes") or {}).get("fdaProductCode"))
        if c.get("productCode")
    ]
    return {
        "public_device_record_key": clean(device.get("publicDeviceRecordKey")),
        "public_version_status": clean(device.get("publicVersionStatus")),
        "device_record_status": clean(device.get("deviceRecordStatus")),
        "public_version_number": device.get("publicVersionNumber"),
        "public_version_date": clean(device.get("publicVersionDate")),
        "device_publish_date": clean(device.get("devicePublishDate")),
        "commercial_distribution_status": clean(device.get("deviceCommDistributionStatus")),
        "brand_name": clean(device.get("brandName")),
        "company_name": clean(device.get("companyName")),
        "version_or_model_number": clean(device.get("versionOrModelNumber")),
        "catalog_number": clean(device.get("catalogNumber")),
        "device_description": clean(device.get("deviceDescription")),
        "duns_number": clean(device.get("dunsNumber")),
        "product_codes": sorted(c for c in codes if c),
        "gmdn_terms": sorted(
            clean(g.get("gmdnPTName"))
            for g in _rows((device.get("gmdnTerms") or {}).get("gmdn"))
            if g.get("gmdnPTName")
        ),
        "country": "US",
    }


class AccessGudidConnector(Connector):
    connector_id = "accessgudid@1"
    source_id = SOURCE_ID
    evidence_type = "device_registration"
    rate_limit = "not published; 1 request/second"

    def __init__(self, client: Any) -> None:
        super().__init__(client)
        self.provenance = provenance_of(SOURCE_ID)

    def fetch(self, di: str, *, run_id: str = "") -> dict[str, Any] | None:
        result = self.client.get(LOOKUP_URL, params={"di": normalize_di(di)})
        if not result.ok:
            return None
        try:
            payload = result.json()
        except ValueError:
            return None
        if not isinstance(payload, Mapping) or not payload.get("gudid"):
            return None
        return dict(payload)

    def to_evidence(
        self, payload: Mapping[str, Any], *, fetched_at: str, run_id: str
    ) -> dict[str, Any] | None:
        normalized = normalize(payload)
        idents = identifiers_of((payload.get("gudid") or {}).get("device") or {})
        if not idents:
            return None
        primary = next((i["value"] for i in idents if i["is_primary"]), idents[0]["value"])
        time_block = build_time(
            event_at=None,
            source_public_at=normalized["device_publish_date"],
            fetched_at=fetched_at,
            quality="day",
            notes="devicePublishDate is GUDID's per-record first-publication date; "
                  "publicVersionDate is a version stamp and is not used as a clock",
        )
        return self.evidence(
            payload,
            normalized,
            source_record_id=normalized["public_device_record_key"] or primary,
            source_url=f"{LOOKUP_URL}?di={primary}",
            identifiers=idents,
            time_block=time_block,
            collection_run_id=run_id,
            company_name=normalized["company_name"],
            relation_status="asserted_by_source",
        )


__all__ = ["AccessGudidConnector", "LOOKUP_URL", "SOURCE_ID", "identifiers_of", "normalize"]
