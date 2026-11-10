"""openFDA Device UDI connector (the U.S. GUDID record, searched by company).

Why this source first
---------------------
openFDA's UDI endpoint is a *queryable* projection of GUDID.  GUDID's own
AccessGUDID API can only be looked up by DI, so openFDA is the only official
way to ask "which UDI records does this company have?" without downloading the
full GUDID release.

Date semantics
--------------
``publish_date`` is the per-record first-publication date -> ``source_public_at``
with ``quality="day"``.  ``public_version_date`` is a version stamp and is kept
in ``normalized`` only, never promoted to a clock.

Identity
--------
``identifiers[].id`` is a UDI-DI.  A GUDID record legitimately has several
identifiers (primary DI + package DIs); ATLAS stores all of them but only the
**primary** DI is used for device identity.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..evidence.timeq import build_time, utc_iso
from ..identity.normalize import build_identifier
from .base import Connector, Provenance, clean, provenance_of

SOURCE_ID = "openfda_device_udi"
ENDPOINT = "https://api.fda.gov/device/udi.json"


def _identifiers(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in result.get("identifiers") or []:
        out.append(
            build_identifier(
                "di", row.get("id"), is_primary=str(row.get("type", "")).lower() == "primary",
                note=clean(row.get("issuing_agency")),
            )
        )
    return [i for i in out if i]


def normalize(result: Mapping[str, Any]) -> dict[str, Any]:
    codes = sorted({clean(c.get("code")) for c in result.get("product_codes") or [] if c.get("code")})
    gmdn = sorted({clean(g.get("code")) for g in result.get("gmdn_terms") or [] if g.get("code")})
    return {
        "public_device_record_key": clean(result.get("public_device_record_key")),
        "company_name": clean(result.get("company_name")),
        "brand_name": clean(result.get("brand_name")),
        "version_or_model_number": clean(result.get("version_or_model_number")),
        "catalog_number": clean(result.get("catalog_number")),
        "device_description": clean(result.get("device_description")),
        "device_class": clean(
            ((result.get("product_codes") or [{}])[0].get("openfda") or {}).get("device_class")
        ),
        "product_codes": codes,
        "gmdn_codes": gmdn,
        "labeler_duns_number": clean(result.get("labeler_duns_number")),
        "publish_date": clean(result.get("publish_date")),
        "public_version_date": clean(result.get("public_version_date")),
        "record_status": clean(result.get("record_status")),
        "commercial_distribution_status": clean(result.get("commercial_distribution_status")),
        "country": "US",
    }


class OpenFdaUdiConnector(Connector):
    connector_id = "openfda_device_udi@1"
    source_id = SOURCE_ID
    evidence_type = "device_registration"
    rate_limit = "240 requests/minute"

    def __init__(self, client: Any) -> None:
        super().__init__(client)
        self.provenance = provenance_of(SOURCE_ID)

    def fetch(
        self,
        *,
        search: str,
        limit: int = 100,
        skip: int = 0,
        run_id: str = "",
    ) -> dict[str, Any]:
        """One bounded openFDA page.  Raises on a failed request (a failure is not zero records)."""
        result = self.client.get(
            ENDPOINT, params={"search": search, "limit": max(1, min(100, int(limit))), "skip": int(skip)}
        )
        if not result.ok:
            raise RuntimeError(f"openFDA UDI request failed: {result.summary()}")
        payload = result.json()
        payload["_fetched_at"] = utc_iso()
        return payload

    def to_evidence(
        self, result: Mapping[str, Any], *, fetched_at: str, run_id: str
    ) -> dict[str, Any]:
        normalized = normalize(result)
        di = ""
        for ident in _identifiers(result):
            if ident["is_primary"]:
                di = ident["value"]
                break
        record_key = normalized["public_device_record_key"] or di
        if not record_key:
            raise ValueError("openFDA UDI record without record key or DI")
        time_block = build_time(
            event_at=None,
            source_public_at=normalized["publish_date"],
            fetched_at=fetched_at,
            quality="day",
            notes="publish_date is GUDID's per-record first-publication date; "
                  "public_version_date is a version stamp and is not used as a clock",
        )
        return self.evidence(
            result,
            normalized,
            source_record_id=record_key,
            source_url=f"{ENDPOINT}?search=identifiers.id:{di}" if di else ENDPOINT,
            identifiers=_identifiers(result),
            time_block=time_block,
            collection_run_id=run_id,
            company_name=normalized["company_name"],
            relation_status="asserted_by_source",
        )

    def collect(
        self,
        *,
        search: str,
        limit: int = 100,
        run_id: str = "",
    ) -> list[dict[str, Any]]:
        page = self.fetch(search=search, limit=limit, run_id=run_id)
        fetched_at = page["_fetched_at"]
        out = []
        for result in page.get("results", []) or []:
            out.append(self.to_evidence(result, fetched_at=fetched_at, run_id=run_id))
        return out


def lookup_identifiers(
    client: Any,
    dis: Iterable[str],
    *,
    batch: int = 25,
    stats: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Resolve many DIs in as few requests as possible (identity bridge helper).

    openFDA returns **404** when a valid search matches nothing.  That is a
    no-match result, not a transport failure, so it is counted separately from
    real errors instead of being silently treated as "no records exist".
    """
    ids = [d for d in dis if d]
    found: list[dict[str, Any]] = []
    counts = stats if stats is not None else {}
    counts.setdefault("batches", 0)
    counts.setdefault("no_match_batches", 0)
    counts.setdefault("failed_batches", 0)
    for start in range(0, len(ids), batch):
        chunk = ids[start : start + batch]
        search = "identifiers.id:(" + " OR ".join(chunk) + ")"
        result = client.get(
            ENDPOINT, params={"search": search, "limit": min(100, len(chunk) * 2)}
        )
        counts["batches"] += 1
        if result.status == 404:
            counts["no_match_batches"] += 1
            continue
        if not result.ok:
            counts["failed_batches"] += 1
            continue
        try:
            payload = result.json()
        except ValueError:
            counts["failed_batches"] += 1
            continue
        found.extend(payload.get("results", []) or [])
    return found


__all__ = ["ENDPOINT", "OpenFdaUdiConnector", "SOURCE_ID", "lookup_identifiers", "normalize"]
