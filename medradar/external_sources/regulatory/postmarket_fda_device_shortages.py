"""FDA medical device shortages / discontinuances — connector for ``fda_device_shortages``.

There is **no openFDA endpoint** for device shortages (probed 2026-11-09: the
``/device/shortage`` path does not exist; only 510k, pma, classification,
registrationlisting, recall, event, udi, surveil, postmarket are documented).
The public data is an HTML page with two real tables:

1. *Medical Device Shortages List* — 6 columns, one row per product code in
   shortage, with ``Date (YYYY/MM/DD)`` giving the initial / reverified date.
2. *Medical Device Discontinuance List* — 6 columns, one row per discontinued
   device with ``Manufacturer Name`` and ``Date Posted``.

Both tables are server-rendered in the page source (no JS/XHR needed), which is
why this source can be verified as ``VERIFIED_PUBLIC_QUERY`` with real parsed
records rather than "the browser opens it".

Time semantics
--------------
The page publishes a **listing date** (initial/reverified for shortages;
``Date Posted`` for discontinuances) and no event date.  Therefore
``source_public_at`` = that listing date and ``event_at`` is left ``null`` — the
actual shortage start date is not published and is never invented here.

Coverage
--------
These are *current* lists, not an archive.  Nothing before the current snapshot
can be reconstructed, and disappearance of an entry is not recorded.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from medradar.external_sources import identity as ev_identity
from medradar.external_sources.regulatory import postmarket_common as common

SOURCE_ID = "fda_device_shortages"
SOURCE_NAME = "FDA medical device shortages"
KIND = "shortage"
LICENCE_STATUS = "public_domain"
PAGE_URL = (
    "https://www.fda.gov/medical-devices/medical-device-supply-chain-and-shortages/"
    "medical-device-shortages-list"
)
ATTRIBUTION = "U.S. Food and Drug Administration, Medical Device Shortages List (public domain)"

SHORTAGE_TABLE_HEADERS = ("Category", "Product Code", "Date")
DISCONTINUANCE_TABLE_HEADERS = ("Date Posted", "Category", "Manufacturer Name")

INTERPRETATION_WARNING = common.SHORTAGE_WARNING

_PRODUCT_CODE_RE = re.compile(r"^(?P<code>[A-Z0-9]{3})\s*[(](?P<desc>.*)[)]\s*$")
_BARE_CODE_RE = re.compile(r"^[A-Z0-9]{3}$")
_DATE_TOKEN_RE = re.compile(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{4}")


def _date_token(value: Any) -> str:
    match = _DATE_TOKEN_RE.search(str(value or ""))
    return match.group(0) if match else ""


def parse_product_code(value: Any) -> tuple[str, str]:
    """``"GKZ  (COUNTER, DIFFERENTIAL CELL)"`` -> ``("GKZ", "COUNTER, DIFFERENTIAL CELL")``.

    A bare three-character token is a code with no description; anything else is
    returned unchanged as the description with an empty code (never guessed).
    """
    text = common.clip(value, 400)
    match = _PRODUCT_CODE_RE.match(text)
    if match:
        return match.group("code").strip(), common.clip(match.group("desc"), 300)
    if _BARE_CODE_RE.match(text):
        return text, ""
    return "", text


def parse_shortages_page(html: str) -> dict[str, Any]:
    """Pure parser: split the page's real tables into shortage / discontinuance rows."""
    tables = common.html_tables(html)
    shortage_table = common.find_table(tables, SHORTAGE_TABLE_HEADERS)
    discontinuance_table = common.find_table(tables, DISCONTINUANCE_TABLE_HEADERS)
    shortages: list[dict[str, Any]] = []
    discontinuances: list[dict[str, Any]] = []
    if shortage_table:
        headers = [str(h).strip() for h in shortage_table["headers"]]
        for row in shortage_table["rows"]:
            cells = row["cells"]
            if len(cells) < 5:
                continue
            item = dict(zip(headers, cells))
            code, description = parse_product_code(item.get(headers[1], ""))
            raw_date = item.get(headers[5], "") if len(headers) > 5 else ""
            shortages.append(
                {
                    "category": common.clip(item.get("Category", ""), 300),
                    "product_code": code,
                    "product_code_description": description,
                    "availability": common.clip(item.get("Availability and Estimated Shortage Duration", ""), 300),
                    "additional_information": common.clip(item.get("Additional Information", ""), 1500),
                    "reason_for_interruption": common.clip(item.get("Reason for Interruption (per 506J)", ""), 800),
                    "date_text": common.clip(raw_date, 200),
                    "date_posted": _date_token(raw_date),
                    "row": dict(zip(headers, [common.clip(cell, 300) for cell in cells])),
                }
            )
    if discontinuance_table:
        headers = [str(h).strip() for h in discontinuance_table["headers"]]
        for row in discontinuance_table["rows"]:
            cells = row["cells"]
            if len(cells) < 5:
                continue
            item = dict(zip(headers, cells))
            code, description = parse_product_code(item.get("Product Code", ""))
            discontinuances.append(
                {
                    "date_posted": _date_token(item.get(headers[0], "")),
                    "category": common.clip(item.get("Category", ""), 300),
                    "product_code": code,
                    "product_code_description": description,
                    "manufacturer_name": common.clip(item.get("Manufacturer Name", ""), 300),
                    "device_trade_name": common.clip(item.get("Device Trade Name", ""), 500),
                    "reason_for_discontinuance": common.clip(item.get("Reason for Discontinuance", ""), 600),
                    "row": dict(zip(headers, [common.clip(cell, 300) for cell in cells])),
                }
            )
    return {
        "page_url": PAGE_URL,
        "table_count": len(tables),
        "table_headers": [[str(h) for h in table["headers"]] for table in tables],
        "shortages": shortages,
        "discontinuances": discontinuances,
    }


def _shortage_record_id(item: Mapping[str, Any]) -> str:
    return "shortage_" + common.record_digest(
        "shortage", item.get("category"), item.get("product_code"), item.get("date_text")
    )


def _discontinuance_record_id(item: Mapping[str, Any]) -> str:
    return "discontinuance_" + common.record_digest(
        "discontinuance",
        item.get("date_posted"),
        item.get("product_code"),
        item.get("manufacturer_name"),
        item.get("device_trade_name"),
    )


def to_evidence(
    item: Mapping[str, Any],
    *,
    record_type: str,
    page_body: bytes,
    fetched_at: str,
    company_index: ev_identity.CompanyIndex | None = None,
) -> dict[str, Any]:
    """One shortage or discontinuance row -> one schema-v1 evidence record."""
    if record_type == "shortage":
        record_id = _shortage_record_id(item)
        source_public_at = item.get("date_posted") or item.get("date_text")
        normalized = {
            "record_type": "shortage",
            "category": item.get("category", ""),
            "product_code": item.get("product_code", ""),
            "product_code_description": item.get("product_code_description", ""),
            "availability_and_estimated_shortage_duration": item.get("availability", ""),
            "additional_information": item.get("additional_information", ""),
            "reason_for_interruption_506j": item.get("reason_for_interruption", ""),
            "date_text": item.get("date_text", ""),
            "interpretation_warning": INTERPRETATION_WARNING,
        }
        entity_refs: list[dict[str, Any]] = []
        identifiers = []
    else:
        record_id = _discontinuance_record_id(item)
        source_public_at = item.get("date_posted")
        normalized = {
            "record_type": "discontinuance",
            "category": item.get("category", ""),
            "product_code": item.get("product_code", ""),
            "product_code_description": item.get("product_code_description", ""),
            "manufacturer_name": item.get("manufacturer_name", ""),
            "device_trade_name": item.get("device_trade_name", ""),
            "reason_for_discontinuance": item.get("reason_for_discontinuance", ""),
            "date_posted": item.get("date_posted", ""),
            "interpretation_warning": INTERPRETATION_WARNING,
        }
        resolver = company_index or ev_identity.CompanyIndex.from_config()
        entity_refs = [common.resolve_company(resolver, item.get("manufacturer_name"), country="US")]
        identifiers = []
    code = item.get("product_code", "")
    if code:
        identifiers = [{"scheme": "product_code", "value": code, "raw_value": code, "is_primary": True, "note": "FDA device product code"}]
    time_block = common.clock_block(
        event_at=None,
        source_public_at=common.us_date_iso(source_public_at),
        quality=common.date_quality(source_public_at),
        fetched_at=fetched_at,
        notes=(
            "event_at is null: the page publishes only a listing date (initial/reverified or "
            "Date Posted), not the date the shortage/discontinuance started. source_public_at = "
            "that listing date."
        ),
    )
    return common.make_postmarket_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=record_id,
        source_url=PAGE_URL,
        normalized=normalized,
        raw=common.raw_block_from_page(
            page_body,
            path=f"{PAGE_URL}#{record_type}:{record_id}",
            media_type="text/html",
        ),
        time=time_block,
        identifiers=identifiers,
        entity_refs=entity_refs,
        source_name=SOURCE_NAME,
        licence_status=LICENCE_STATUS,
        attribution=ATTRIBUTION,
        fetched_at=fetched_at,
    )


def parse_to_evidence(
    page_body: bytes,
    *,
    fetched_at: str,
    company_index: ev_identity.CompanyIndex | None = None,
) -> list[dict[str, Any]]:
    """Whole page -> evidence records (shortages first, then discontinuances)."""
    parsed = parse_shortages_page(page_body.decode("utf-8", errors="replace"))
    out: list[dict[str, Any]] = []
    for item in parsed["shortages"]:
        out.append(
            to_evidence(
                item,
                record_type="shortage",
                page_body=page_body,
                fetched_at=fetched_at,
                company_index=company_index,
            )
        )
    for item in parsed["discontinuances"]:
        out.append(
            to_evidence(
                item,
                record_type="discontinuance",
                page_body=page_body,
                fetched_at=fetched_at,
                company_index=company_index,
            )
        )
    return out


def collect(
    client: Any,
    *,
    fetched_at: str = "",
    company_index: ev_identity.CompanyIndex | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch the single real page and normalise both tables.  One request."""
    from medradar.external_sources import base as ev_base

    fetched = fetched_at or ev_base.utc_iso()
    result = client.get(PAGE_URL, accept="text/html")
    meta: dict[str, Any] = {"url": result.url, "status": result.status, "bytes": len(result.body), "error": result.error}
    if not result.ok:
        return [], meta
    parsed = parse_shortages_page(result.text)
    records = parse_to_evidence(result.body, fetched_at=fetched, company_index=company_index)
    meta.update(
        {
            "tables": parsed["table_count"],
            "table_headers": parsed["table_headers"],
            "shortage_rows": len(parsed["shortages"]),
            "discontinuance_rows": len(parsed["discontinuances"]),
            "records": len(records),
        }
    )
    return records, meta


__all__ = [
    "DISCONTINUANCE_TABLE_HEADERS",
    "INTERPRETATION_WARNING",
    "KIND",
    "LICENCE_STATUS",
    "PAGE_URL",
    "SHORTAGE_TABLE_HEADERS",
    "SOURCE_ID",
    "SOURCE_NAME",
    "collect",
    "parse_product_code",
    "parse_shortages_page",
    "parse_to_evidence",
    "to_evidence",
]
