"""SEC EDGAR XBRL Company Facts collector with filing-time semantics.

Company Facts contains consolidated entity facts, not reliable product/segment
revenue. We therefore never relabel Revenue as device sales and store the scope
limitation on every row. Historical features select only filings whose ``filed``
date is on or before the information cutoff.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from ...config import load_companies
from ...http import Fetcher
from ...util import sha1, utc_now_iso
from ..storage import IntelligenceStore

SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "GrossProfit",
    "OperatingIncomeLoss",
    "ResearchAndDevelopmentExpense",
    "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "CashAndCashEquivalentsAtCarryingValue",
    "NetCashProvidedByUsedInOperatingActivities",
    "InventoryNet",
    "PaymentsToAcquireBusinessesNetOfCashAcquired",
)


def ticker_cik_map(payload: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in payload.values():
        if isinstance(row, Mapping) and row.get("ticker") and row.get("cik_str") is not None:
            result[str(row["ticker"]).upper()] = f"{int(row['cik_str']):010d}"
    return result


def normalize_companyfacts(company_key: str, cik: str, payload: Mapping[str, Any],
                           retrieved_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    facts = payload.get("facts") or {}
    for taxonomy in ("us-gaap",):
        for tag in TAGS:
            units = ((facts.get(taxonomy) or {}).get(tag) or {}).get("units") or {}
            for unit, observations in units.items():
                for fact in observations:
                    if fact.get("val") is None or not fact.get("end") or not fact.get("filed"):
                        continue
                    accession = str(fact.get("accn") or "")
                    identity = (company_key, cik, taxonomy, tag, unit, str(fact.get("start") or ""),
                                str(fact["end"]), accession, str(fact["filed"]), str(fact["val"]))
                    rows.append({
                        "fact_id": sha1("|".join(identity))[:32],
                        "company_key": company_key,
                        "cik": cik,
                        "taxonomy": taxonomy,
                        "tag": tag,
                        "unit": unit,
                        "value": float(fact["val"]),
                        "period_start": fact.get("start"),
                        "period_end": fact["end"],
                        "available_at": fact["filed"],
                        "form": fact.get("form"),
                        "fiscal_year": fact.get("fy"),
                        "fiscal_period": fact.get("fp"),
                        "accession": accession,
                        "frame": fact.get("frame"),
                        "retrieved_at": retrieved_at,
                        "payload": {k: fact.get(k) for k in ("start", "end", "val", "accn", "fy", "fp", "form", "filed", "frame")},
                    })
    return rows


def collect(store: IntelligenceStore, fetcher: Fetcher, *, companies: Iterable[str] | None = None,
            limit: int = 0) -> dict[str, Any]:
    registry = load_companies("device")
    selected = set(companies or registry.keys())
    retrieved_at = utc_now_iso()
    ticker_payload = fetcher.get_json(SEC_TICKERS)
    mapping = ticker_cik_map(ticker_payload)
    stats: dict[str, Any] = {"retrieved_at": retrieved_at, "companies": {}, "warnings": []}
    attempted = 0
    for company in registry.all():
        key = company["key"]
        ticker = str(company.get("ticker") or "").upper()
        if key not in selected or not ticker or ticker not in mapping:
            continue
        if limit and attempted >= limit:
            break
        attempted += 1
        cik = mapping[ticker]
        try:
            payload = fetcher.get_json(SEC_COMPANY_FACTS.format(cik=cik))
            rows = normalize_companyfacts(key, cik, payload, retrieved_at)
            store.upsert_financial_facts(rows)
            store.link_identifier({
                "company_key": key, "scheme": "SEC_CIK", "identifier": cik,
                "source": "sec_company_tickers", "available_at": retrieved_at,
                "confidence": 1.0, "evidence": f"ticker={ticker}",
            })
            store.add_observed_edge(
                subject=key, relation="COMPANY_FILES_FINANCIAL_FACT", object=cik,
                valid_time=None, available_at=retrieved_at, source="sec_company_tickers",
                evidence_id=f"{ticker}:{cik}", object_type="FinancialFiling",
            )
            store.conn.commit()
            stats["companies"][key] = {"cik": cik, "facts": len(rows), "tags": dict(Counter(r["tag"] for r in rows))}
        except Exception as exc:
            stats["companies"][key] = {"cik": cik, "error": f"{type(exc).__name__}: {exc}"}
            stats["warnings"].append(f"{key}: {type(exc).__name__}: {exc}")
    stats["facts"] = sum(v.get("facts", 0) for v in stats["companies"].values())
    stats["resolved_companies"] = sum(1 for v in stats["companies"].values() if v.get("facts"))
    return stats
