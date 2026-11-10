"""Health Canada MDALL connector.

Three facts that drive the design
---------------------------------
1. The ``licence`` and ``deviceidentifier`` **listing** endpoints return the
   entire table (21 MB and ~220 MB respectively) and ignore ``limit``.  A
   connector that paginates them politely does not exist; ATLAS streams the
   identifier table once under a hard byte cap and uses ``?id=`` lookups for
   individual licences/companies.
2. MDALL publishes **no per-record publication date**.  ``first_licence_dt`` and
   ``first_licence_status_dt`` are event clocks; ``last_refresh_dt`` is a
   database refresh stamp and ``end_date`` is a cancellation date.  ATLAS sets
   ``source_public_at`` from the licence date with ``quality="derived"`` and a
   note, so it can never support a lead-time claim by accident.
3. ``device_identifier`` is **usually a manufacturer model/catalogue number**,
   not a UDI-DI.  Measured on the 2026-11-10 active table: 5,477 of 1,673,926
   rows (0.33%) are GTIN-14 shaped.  ATLAS therefore treats a 14-digit value as
   a UDI-DI candidate and everything else as a model string; it does not claim
   that a Canadian licence identifies a UDI device when the identifier field
   holds a model number.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from ..evidence.timeq import build_time, iso, parse_date
from ..identity.normalize import build_identifier, is_gtin_like, normalize_di
from .base import Connector, clean, provenance_of

SOURCE_ID = "canada_mdall"
BASE = "https://health-products.canada.ca/api/medical-devices"
SOURCE_URL = "https://health-products.canada.ca/mdall-limh/"
TABLE_URL = f"{BASE}/deviceidentifier/"

_DERIVED_NOTE = (
    "MDALL publishes no per-record publication date; source_public_at is derived from the "
    "licence date. last_refresh_dt is a database refresh stamp and end_date is a cancellation "
    "date - neither may be used as a first-publication date"
)


def iter_json_array(path: Path, *, chunk_size: int = 1 << 20) -> Iterator[dict[str, Any]]:
    """Iterate a large JSON array of flat objects without loading it all.

    The 220 MB MDALL identifier table would cost >1 GB as Python dicts if loaded
    at once.  ``raw_decode`` over a sliding buffer keeps peak memory near the
    chunk size.  Malformed trailing data ends iteration silently only when the
    array itself ended; otherwise the error propagates.
    """
    decoder = json.JSONDecoder()
    with Path(path).open("r", encoding="utf-8", errors="replace") as fh:
        buf = fh.read(chunk_size)
        pos = 0
        while True:
            while pos < len(buf) and buf[pos] in " \t\r\n,[":
                pos += 1
            if pos >= len(buf):
                more = fh.read(chunk_size)
                if not more:
                    return
                buf = buf[pos:] + more
                pos = 0
                continue
            if buf[pos] == "]":
                return
            try:
                obj, end = decoder.raw_decode(buf, pos)
            except ValueError:
                more = fh.read(chunk_size)
                if not more:
                    raise
                buf = buf[pos:] + more
                pos = 0
                continue
            pos = end
            if isinstance(obj, dict):
                yield obj


def normalise_licence(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "licence_number": clean(row.get("original_licence_no")),
        "licence_status": clean(row.get("licence_status")),
        "licence_name": clean(row.get("licence_name")),
        "licence_type": clean(row.get("licence_type_desc")),
        "risk_class": row.get("appl_risk_class"),
        "company_id": clean(row.get("company_id")),
        "first_licence_status_dt": clean(row.get("first_licence_status_dt")),
        "last_refresh_dt": clean(row.get("last_refresh_dt")),
        "end_date": clean(row.get("end_date")),
        "country": "CA",
    }


def normalise_identifier(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = clean(row.get("device_identifier"))
    return {
        "device_identifier_raw": raw,
        "device_identifier_is_gtin": is_gtin_like(raw),
        "device_identifier_normalised": normalize_di(raw),
        "licence_number": clean(row.get("original_licence_no")),
        "mdall_device_id": clean(row.get("device_id")),
        "first_licence_dt": clean(row.get("first_licence_dt")),
        "end_date": clean(row.get("end_date")),
        "country": "CA",
    }


class CanadaMdallConnector(Connector):
    connector_id = "canada_mdall@1"
    source_id = SOURCE_ID
    evidence_type = "device_registration"
    rate_limit = "not published; ATLAS uses >=1s interval and one bounded stream"

    def __init__(self, client: Any) -> None:
        super().__init__(client)
        self.provenance = provenance_of(SOURCE_ID)

    # ------------------------------------------------------------------ fetch
    def fetch_licence(self, licence_number: str, *, run_id: str = "") -> dict[str, Any] | None:
        result = self.client.get(
            f"{BASE}/licence/",
            params={"id": licence_number, "lang": "en", "type": "json"},
        )
        if not result.ok:
            return None
        try:
            payload = result.json()
        except ValueError:
            return None
        if isinstance(payload, list):
            return dict(payload[0]) if payload else None
        return dict(payload) if isinstance(payload, Mapping) else None

    def fetch_company(self, company_id: str, *, run_id: str = "") -> dict[str, Any] | None:
        result = self.client.get(
            f"{BASE}/company/", params={"id": company_id, "lang": "en", "type": "json"}
        )
        if not result.ok:
            return None
        try:
            payload = result.json()
        except ValueError:
            return None
        if isinstance(payload, list):
            return dict(payload[0]) if payload else None
        return dict(payload) if isinstance(payload, Mapping) else None

    def download_identifier_table(
        self, cache_path: Path, *, max_bytes: int = 400 * 1024 * 1024
    ) -> dict[str, Any]:
        """One bounded stream of the active identifier table (official open data)."""
        return self.client.stream_to_file(
            TABLE_URL,
            cache_path,
            max_bytes=max_bytes,
            params={"state": "active", "type": "json"},
        )

    # --------------------------------------------------------------- evidence
    def licence_evidence(
        self,
        licence: Mapping[str, Any],
        *,
        company: Mapping[str, Any] | None,
        fetched_at: str,
        run_id: str,
    ) -> dict[str, Any]:
        normalized = normalise_licence(licence)
        company_name = clean((company or {}).get("company_name"))
        licence_no = normalized["licence_number"]
        if not licence_no:
            raise ValueError("MDALL licence record without original_licence_no")
        time_block = build_time(
            event_at=normalized["first_licence_status_dt"],
            source_public_at=normalized["first_licence_status_dt"],
            fetched_at=fetched_at,
            quality="derived",
            notes=_DERIVED_NOTE,
        )
        idents = [
            build_identifier("licence_no", licence_no, is_primary=True),
            build_identifier("mdall_company_id", normalized["company_id"]),
        ]
        return self.evidence(
            licence,
            normalized,
            source_record_id=licence_no,
            source_url=f"{BASE}/licence/?id={licence_no}&lang=en&type=json",
            identifiers=[i for i in idents if i],
            time_block=time_block,
            collection_run_id=run_id,
            company_name=company_name,
            relation_status="asserted_by_source",
        )

    def identifier_evidence(
        self, row: Mapping[str, Any], *, fetched_at: str, run_id: str
    ) -> dict[str, Any]:
        normalized = normalise_identifier(row)
        licence_no = normalized["licence_number"]
        device_id = normalized["mdall_device_id"]
        raw_ident = normalized["device_identifier_raw"]
        if not licence_no or not raw_ident:
            raise ValueError("MDALL identifier row without licence/device identifier")
        time_block = build_time(
            event_at=normalized["first_licence_dt"],
            source_public_at=normalized["first_licence_dt"],
            fetched_at=fetched_at,
            quality="derived",
            notes=_DERIVED_NOTE,
        )
        idents = [build_identifier("licence_no", licence_no, is_primary=False),
                  build_identifier("mdall_device_id", device_id)]
        if normalized["device_identifier_is_gtin"]:
            idents.insert(0, build_identifier("di", raw_ident, is_primary=True,
                                             note="GTIN-14-shaped MDALL device_identifier"))
        return self.evidence(
            row,
            normalized,
            source_record_id=f"{licence_no}:{device_id}:{raw_ident}",
            source_url=f"{TABLE_URL}?state=active&type=json (licence {licence_no})",
            identifiers=[i for i in idents if i],
            time_block=time_block,
            collection_run_id=run_id,
            relation_status="asserted_by_source",
            quality_flags=() if normalized["device_identifier_is_gtin"] else ("missing_primary_identifier",),
        )

    # ------------------------------------------------------------- table scan
    def scan_identifier_table(
        self,
        table_path: Path,
        *,
        keep_if,
        fetched_at: str,
        run_id: str,
        limit: int | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Stream the table, keep only rows matching ``keep_if`` (bounded)."""
        kept: list[dict[str, Any]] = []
        scanned = 0
        for row in iter_json_array(table_path):
            scanned += 1
            if keep_if(row):
                kept.append(self.identifier_evidence(row, fetched_at=fetched_at, run_id=run_id))
                if limit is not None and len(kept) >= limit:
                    break
        return kept, {"rows_scanned": scanned, "rows_kept": len(kept)}


__all__ = [
    "BASE",
    "CanadaMdallConnector",
    "SOURCE_ID",
    "TABLE_URL",
    "iter_json_array",
    "normalise_identifier",
    "normalise_licence",
]
