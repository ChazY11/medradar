"""openFDA Device 510(k) connector.

One 510(k) record = one clearance decision.  It is a *regulatory* identity: a
510(k) number groups the products cleared under it, and it is not a device
identifier.  ATLAS therefore never promotes "same 510(k)" to
``SAME_DEVICE_IDENTITY``; it is at most ``SAME_PRODUCT_FAMILY``.

Date semantics: ``decision_date`` is an event clock.  FDA publishes no
per-record publication timestamp for 510(k), so ``source_public_at`` is derived
from it and flagged ``quality="derived"``.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..evidence.timeq import build_time, utc_iso
from ..identity.normalize import build_identifier
from .base import Connector, clean, provenance_of

SOURCE_ID = "openfda_device_510k"
ENDPOINT = "https://api.fda.gov/device/510k.json"

_DERIVED_NOTE = (
    "FDA publishes no per-record first-publication timestamp for 510(k); source_public_at is "
    "derived from decision_date and must never be used for a lead-time claim"
)


def normalize(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "k_number": clean(record.get("k_number")),
        "device_name": clean(record.get("device_name")),
        "applicant": clean(record.get("applicant")),
        "product_code": clean(record.get("product_code")),
        "decision_date": clean(record.get("decision_date")),
        "date_received": clean(record.get("date_received")),
        "decision_code": clean(record.get("decision_code")),
        "decision_description": clean(record.get("decision_description")),
        "clearance_type": clean(record.get("clearance_type")),
        "advisory_committee_description": clean(record.get("advisory_committee_description")),
        "statement_or_summary": clean(record.get("statement_or_summary")),
        "country_code": clean(record.get("country_code")),
        "country": clean(record.get("country_code")) or "US",
    }


class OpenFda510kConnector(Connector):
    connector_id = "openfda_device_510k@1"
    source_id = SOURCE_ID
    evidence_type = "regulatory_clearance"
    rate_limit = "240 requests/minute"

    def __init__(self, client: Any) -> None:
        super().__init__(client)
        self.provenance = provenance_of(SOURCE_ID)

    def fetch(self, *, search: str, limit: int = 100, skip: int = 0) -> dict[str, Any]:
        result = self.client.get(
            ENDPOINT, params={"search": search, "limit": max(1, min(100, limit)), "skip": skip}
        )
        if not result.ok:
            raise RuntimeError(f"openFDA 510(k) request failed: {result.summary()}")
        payload = result.json()
        payload["_fetched_at"] = utc_iso()
        return payload

    def to_evidence(self, record: Mapping[str, Any], *, fetched_at: str, run_id: str) -> dict[str, Any]:
        normalized = normalize(record)
        k_number = normalized["k_number"]
        if not k_number:
            raise ValueError("510(k) record without k_number")
        time_block = build_time(
            event_at=normalized["decision_date"],
            source_public_at=normalized["decision_date"],
            fetched_at=fetched_at,
            quality="derived",
            notes=_DERIVED_NOTE,
        )
        idents = [
            build_identifier("510k", k_number, is_primary=True),
            build_identifier("product_code", normalized["product_code"], note="FDA product code"),
        ]
        return self.evidence(
            record,
            normalized,
            source_record_id=k_number,
            source_url=f"{ENDPOINT}?search=k_number:{k_number}",
            identifiers=[i for i in idents if i],
            time_block=time_block,
            collection_run_id=run_id,
            company_name=normalized["applicant"],
            relation_status="asserted_by_source",
        )

    def collect(self, *, search: str, limit: int = 100, run_id: str = "") -> list[dict[str, Any]]:
        page = self.fetch(search=search, limit=limit)
        fetched_at = page["_fetched_at"]
        return [self.to_evidence(r, fetched_at=fetched_at, run_id=run_id) for r in page.get("results", [])]


__all__ = ["ENDPOINT", "OpenFda510kConnector", "SOURCE_ID", "normalize"]
