"""HMRC UK Trade Info connector — the only *company-level* open trade channel found.

Probed 2026-11-09 against ``https://api.uktradeinfo.com/`` (an open OData v4
service, no key): the ``Trader`` entity exposes ``CompanyName`` and
``PostCode``; ``Trade``/``YearlyTrade`` join ``TraderId x CommodityId (CN8) x
Month``.

What this is, precisely
-----------------------
It is **company-level presence**, not a bill of lading: there are **no values,
no quantities, no partners and no consignment identity** at trader level.  A
record here says "this named trader traded this CN8 code in these months of this
year" — nothing more.  Everything else in the service (the ``OTS`` entity) is a
national aggregate and is emitted as ``trade_aggregate`` instead.

The distinction matters: a presence record is firm evidence, an OTS row is a
country statistic, and neither is a shipment value.
"""

from __future__ import annotations

import calendar
import re
from typing import Any, Iterable, Mapping, Sequence

from .. import base, identity, schema, timeq

SOURCE_ID = "uk_hmrc_trade"
KIND = "trade_by_trader"  # named trader + HS code + period; NOT a shipment
LICENCE_STATUS = "open_no_explicit_licence"  # HMRC published trade data, presumed OGL v3.0 (unverified)
REDISTRIBUTION = "unknown"

BASE_URL = "https://api.uktradeinfo.com"

#: Company-name fragments probed successfully on 2026-11-09.
TRADER_FRAGMENTS: tuple[str, ...] = ("MEDTRONIC", "PHILIPS", "DRAEGER", "MINDRAY", "GE HEALTHCARE")

#: Trade-specific demotions.  These strings appear inside names that the shared
#: alias table would otherwise resolve as a *confirmed* link to a target firm,
#: but which are a different business (Philips Lighting/consumer spin-offs,
#: Dräger's industrial safety division).  A hit demotes the link to ``candidate``
#: — it is never dropped, and never counted as confirmed.
NON_MEDICAL_TRADE_GUARDS: tuple[str, ...] = (
    "LIGHTING",
    "CONSUMER LIFESTYLE",
    "LUMILEDS",
    "SIGNIFY",
    "SAFETY",
)

PAGE_SELECT = "TraderId,CompanyName,PostCode"

_MONTH_LOOKUP = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}


def parse_month_list(value: Any) -> list[int]:
    """``"December 2023,October 2023"`` -> ``[12, 10]`` (sorted, de-duplicated).

    Unparseable fragments are skipped rather than guessed.
    """
    if not value:
        return []
    months: set[int] = set()
    for part in str(value).split(","):
        match = re.match(r"^\s*([A-Za-z]+)\s+(\d{4})\s*$", part)
        if not match:
            continue
        number = _MONTH_LOOKUP.get(match.group(1).lower())
        if number:
            months.add(number)
    return sorted(months, reverse=True)


def normalize_trader_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """One ``Trader`` row -> the fields we keep, without invention."""
    return {
        "trader_id": str(row.get("TraderId") or ""),
        "company_name": str(row.get("CompanyName") or "").strip(),
        "postcode": str(row.get("PostCode") or "").strip(),
        "is_hmrc_placeholder_address": str(row.get("PostCode") or "").strip().upper() == "AB10 1ZP",
    }


def link_company(company_index: identity.CompanyIndex, company_name: str) -> dict[str, Any]:
    """Resolve a declarant string, applying the trade-specific demotions."""
    resolution = dict(company_index.resolve(company_name))
    normalized = identity.normalize_name(company_name)
    if resolution.get("method") in schema.CONFIRMED_METHODS:
        for guard in NON_MEDICAL_TRADE_GUARDS:
            if guard in normalized:
                evidence = dict(resolution.get("evidence") or {})
                evidence["trade_demotion_guard"] = guard
                resolution.update(
                    method="candidate",
                    confidence=0.55,
                    evidence=evidence,
                    note=(
                        "alias matched but the declarant name indicates a non-medical division "
                        f"({guard}); kept as a candidate only"
                    ),
                )
                break
    return resolution


def normalize_presence(
    trader: Mapping[str, Any], presence: Mapping[str, Any]
) -> dict[str, Any]:
    """One (trader, yearly trade row) pair -> a flat presence observation."""
    import_months = parse_month_list(presence.get("ImportMonths"))
    export_months = parse_month_list(presence.get("ExportMonths"))
    normalized_trader = normalize_trader_row(trader)
    return {
        "data_class": "company_level_presence",
        "record_type": "trader_commodity_year_presence",
        "trader_id": normalized_trader["trader_id"],
        "company_name": normalized_trader["company_name"],
        "postcode": normalized_trader["postcode"],
        "is_hmrc_placeholder_address": normalized_trader["is_hmrc_placeholder_address"],
        "cn8_code": str(presence.get("CommodityId") or ""),
        "year": int(presence["Year"]) if str(presence.get("Year", "")).isdigit() else None,
        "import_months": import_months,
        "export_months": export_months,
        "has_import": bool(import_months),
        "has_export": bool(export_months),
        # The absence of these is a property of the source, not of the record.
        "value_available": False,
        "quantity_available": False,
        "partner_available": False,
        "consignment_available": False,
    }


def normalize_ots_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """One ``OTS`` row -> a national aggregate observation (has values)."""
    month = str(row.get("MonthId") or "")
    return {
        "data_class": "country_level_aggregate",
        "record_type": "ots_month_aggregate",
        "month_id": month,
        "year": int(month[:4]) if len(month) >= 4 and month[:4].isdigit() else None,
        "flow_type_id": row.get("FlowTypeId"),
        "commodity_id": str(row.get("CommodityId") or ""),
        "country_id": row.get("CountryId"),
        "port_id": row.get("PortId"),
        "value_gbp": row.get("Value"),
        "net_mass_kg": row.get("NetMass"),
        "supplementary_unit": row.get("SuppUnit"),
        "suppression_index": row.get("SuppressionIndex"),
    }


def presence_record_id(normalized: Mapping[str, Any]) -> str:
    return (
        f"trader={normalized.get('trader_id')}"
        f":cn8={normalized.get('cn8_code')}"
        f":year={normalized.get('year')}"
    )


def _time_block(anchor: str | None, fetched: Any, note: str) -> dict[str, Any]:
    return timeq.build_time(
        event_at=anchor,
        source_public_at=None,
        quality="unknown",
        fetched_at=fetched,
        notes=note,
    )


def to_evidence(
    raw_item: Mapping[str, Any],
    *,
    fetched_at: Any = None,
    company_index: identity.CompanyIndex | None = None,
) -> dict[str, Any]:
    """One normalised HMRC record -> schema-v1 evidence.

    ``raw_item`` shape::

        {"record_type": "trader_commodity_year_presence",
         "trader": {"TraderId": ..., "CompanyName": ..., "PostCode": ...},
         "presence": {"CommodityId": ..., "Year": ..., "ImportMonths": ..., "ExportMonths": ...}}

    or ``{"record_type": "ots_month_aggregate", "aggregate": {...}}``.
    """
    record_type = str(raw_item.get("record_type") or "")
    fetched = timeq.parse_datetime(fetched_at) if fetched_at else None
    payload = dict(raw_item)

    if record_type == "ots_month_aggregate":
        normalized = normalize_ots_row(raw_item.get("aggregate") or {})
        month = normalized.get("month_id") or ""
        anchor = f"{month[:4]}-{month[4:6]}-01" if len(month) == 6 else None
        return schema.make_evidence(
            source_id=SOURCE_ID,
            kind="trade_aggregate",
            source_record_id=(
                f"ots:{normalized.get('month_id')}:{normalized.get('flow_type_id')}"
                f":{normalized.get('commodity_id')}:{normalized.get('country_id')}"
                f":{normalized.get('port_id')}"
            ),
            source_url=f"{BASE_URL}/OTS",
            normalized=normalized,
            raw={
                "content_hash": schema.sha256_json(payload),
                "bytes": len(schema.canonical_json(payload).encode("utf-8")),
            },
            time=_time_block(
                anchor,
                fetched,
                "OTS national aggregate by month; event_at is a derived month anchor and no publication "
                "clock is exposed, so source_public_at is UNKNOWN. It identifies no company.",
            ),
            identifiers=(),
            entity_refs=(),  # an aggregate cannot be linked to a company
            provenance={
                "source_name": "HMRC UK Trade Info (OTS)",
                "licence_status": LICENCE_STATUS,
                "redistribution": REDISTRIBUTION,
                "attribution": "Source: HMRC UK Trade Info",
                "evidence_reference": "see research/data_expansion/probes/uk_hmrc_trade/",
                "source_time_quality": "unknown (month only)",
            },
            fetched_at=timeq.iso(fetched) if fetched else "",
        )

    if record_type != "trader_commodity_year_presence":
        raise schema.EvidenceError(f"unknown HMRC record_type: {record_type!r}")

    trader = raw_item.get("trader") or {}
    presence = raw_item.get("presence") or {}
    normalized = normalize_presence(trader, presence)
    year = normalized.get("year")
    anchor = f"{year}-12-31" if year else None

    index = company_index or identity.CompanyIndex.from_config()
    resolution = link_company(index, normalized.get("company_name") or "")
    entity_refs = [resolution] if resolution.get("method") not in (None, "none") else []

    identifiers = [
        identity.build_identifier("hmrc_trader_id", normalized.get("trader_id")),
        identity.build_identifier("cn8", normalized.get("cn8_code")),
    ]

    return schema.make_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=presence_record_id(normalized),
        source_url=f"{BASE_URL}/YearlyTrade",
        normalized=normalized,
        raw={
            "content_hash": schema.sha256_json(payload),
            "bytes": len(schema.canonical_json(payload).encode("utf-8")),
        },
        time=_time_block(
            anchor,
            fetched,
            "company-level PRESENCE for a calendar year, not a shipment and not a value. event_at is a "
            "derived year anchor; HMRC exposes no publication date for a trader record, so "
            "source_public_at is UNKNOWN and this record must not be used for lead-time claims.",
        ),
        identifiers=[ident for ident in identifiers if ident],
        entity_refs=entity_refs,
        provenance={
            "source_name": "HMRC UK Trade Info (Trader / YearlyTrade)",
            "licence_status": LICENCE_STATUS,
            "redistribution": REDISTRIBUTION,
            "attribution": "Source: HMRC UK Trade Info",
            "evidence_reference": "see research/data_expansion/probes/uk_hmrc_trade/",
            "source_time_quality": "unknown (year only)",
        },
        fetched_at=timeq.iso(fetched) if fetched else "",
    )


def collect(
    client: base.HttpClient,
    *,
    fragments: Sequence[str] = TRADER_FRAGMENTS,
    year: int = 2023,
    limit: int = 50,
    max_traders_per_fragment: int = 1,
    company_index: identity.CompanyIndex | None = None,
) -> list[dict[str, Any]]:
    """Fetch at most ``limit`` company-level presence records.

    Request budget is bounded by ``len(fragments) * (1 + max_traders_per_fragment)``.
    A source budget exhaustion stops collection and returns what was gathered.
    """
    if limit <= 0:
        return []
    index = company_index or identity.CompanyIndex.from_config()
    records: list[dict[str, Any]] = []
    for fragment in fragments:
        if len(records) >= limit:
            break
        try:
            traders = client.get(
                f"{BASE_URL}/Trader",
                params={
                    "$filter": f"contains(CompanyName,'{fragment}')",
                    "$top": max_traders_per_fragment,
                    "$select": PAGE_SELECT,
                },
            )
        except base.BudgetExceeded:
            break
        if not traders.ok:
            continue
        try:
            rows: Iterable[Mapping[str, Any]] = traders.json().get("value") or []
        except ValueError:
            continue
        for trader in rows:
            if len(records) >= limit:
                break
            trader_id = trader.get("TraderId")
            if trader_id is None:
                continue
            try:
                presence_result = client.get(
                    f"{BASE_URL}/YearlyTrade",
                    params={
                        "$filter": f"TraderId eq {trader_id} and Year eq {year}",
                        "$top": 10,
                    },
                )
            except base.BudgetExceeded:
                return records
            if not presence_result.ok:
                continue
            try:
                presence_rows = presence_result.json().get("value") or []
            except ValueError:
                continue
            for presence in presence_rows:
                if len(records) >= limit:
                    break
                records.append(
                    to_evidence(
                        {
                            "record_type": "trader_commodity_year_presence",
                            "trader": dict(trader),
                            "presence": dict(presence),
                        },
                        fetched_at=base.utc_iso(),
                        company_index=index,
                    )
                )
    return records
