"""USAspending contract-award collector.

Award amounts are obligations, not delivery or recognized revenue. The API is a
current snapshot and does not expose first-publication history, so imported rows
are ``pit_usable=0`` even though performance and modification dates are kept.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

from ...config import load_companies
from ...http import Fetcher
from ...util import iso, utc_now_iso
from ..storage import IntelligenceStore

SEARCH_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
AWARD_URL = "https://www.usaspending.gov/award/{internal_id}"
NAICS = ("334510", "334517", "339112", "339113", "339114", "339115")
FIELDS = (
    "Award ID", "Recipient Name", "Start Date", "End Date", "Award Amount",
    "Awarding Agency", "Awarding Sub Agency", "Contract Award Type", "NAICS",
    "Last Modified Date",
)


def normalize_award(record: dict[str, Any], registry: Any, retrieved_at: str) -> dict[str, Any]:
    supplier = str(record.get("Recipient Name") or "").strip()
    company_key, confidence, alias = registry.resolve(supplier)
    naics = record.get("NAICS") if isinstance(record.get("NAICS"), dict) else {}
    identity = str(record.get("generated_internal_id") or record.get("internal_id") or record.get("Award ID"))
    return {
        "procurement_id": identity,
        "buyer": record.get("Awarding Agency"),
        "buyer_subagency": record.get("Awarding Sub Agency"),
        "supplier": supplier,
        "company_key": company_key,
        "product_category": naics.get("description") or record.get("Contract Award Type"),
        "naics_code": naics.get("code"),
        "contract_value": record.get("Award Amount"),
        "currency": "USD",
        "announcement_date": None,
        "award_date": None,  # search response exposes performance dates, not signed date
        "period_start": iso(record.get("Start Date")) or None,
        "period_end": iso(record.get("End Date")) or None,
        "country": "US",
        "original_source": "usaspending_api_v2_spending_by_award",
        "source_url": AWARD_URL.format(internal_id=record.get("internal_id") or identity),
        "available_at": retrieved_at,
        "retrieved_at": retrieved_at,
        "pit_usable": False,
        "data_quality": "current_snapshot_obligation_not_revenue_first_publication_unknown",
        "match_confidence": confidence,
        "matched_alias": alias,
        "payload": {
            "award_id": record.get("Award ID"),
            "contract_award_type": record.get("Contract Award Type"),
            "last_modified_date": record.get("Last Modified Date"),
            "internal_id": record.get("internal_id"),
            "generated_internal_id": record.get("generated_internal_id"),
        },
    }


def collect(store: IntelligenceStore, fetcher: Fetcher, *, companies: Iterable[str] | None = None,
            start_date: str = "2016-01-01", end_date: str | None = None,
            max_pages_per_company: int = 2, page_size: int = 100) -> dict[str, Any]:
    registry = load_companies("device")
    selected = set(companies or registry.major_keys())
    end_date = end_date or date.today().isoformat()
    retrieved_at = utc_now_iso()
    stats: dict[str, Any] = {
        "retrieved_at": retrieved_at, "start_date": start_date, "end_date": end_date,
        "companies": {}, "warnings": [
            "Current USAspending snapshot: unavailable for historical point-in-time predictive claims.",
            "Award Amount is a contract obligation, not delivery or recognized revenue.",
        ],
    }
    total = matched = 0
    for company in registry.all():
        key = company["key"]
        if key not in selected:
            continue
        name = company.get("name_en") or key
        rows: list[dict[str, Any]] = []
        try:
            for page in range(1, max(1, max_pages_per_company) + 1):
                request = {
                    "filters": {
                        "time_period": [{"start_date": start_date, "end_date": end_date}],
                        "award_type_codes": ["A", "B", "C", "D"],
                        "recipient_search_text": [name],
                        "naics_codes": list(NAICS),
                    },
                    "fields": list(FIELDS), "page": page, "limit": page_size,
                    "sort": "Award Amount", "order": "desc", "subawards": False,
                }
                response = fetcher.post_json(SEARCH_URL, request)
                results = response.get("results") or []
                rows.extend(normalize_award(record, registry, retrieved_at) for record in results)
                if not (response.get("page_metadata") or {}).get("hasNext") or not results:
                    break
            store.upsert_procurement(rows)
            for row in rows:
                if row["company_key"]:
                    store.add_observed_edge(
                        subject=row["company_key"], relation="COMPANY_WINS_CONTRACT",
                        object=row["procurement_id"], valid_time=row["period_start"],
                        available_at=retrieved_at, source=row["original_source"],
                        evidence_id=row["procurement_id"], confidence=row["match_confidence"] or 0,
                        object_type="ProcurementContract",
                    )
            store.conn.commit()
            total += len(rows)
            matched += sum(1 for row in rows if row["company_key"])
            stats["companies"][key] = {
                "query": name, "awards": len(rows),
                "resolved": sum(1 for row in rows if row["company_key"]),
                "obligation_usd": sum(float(row["contract_value"] or 0) for row in rows),
            }
        except Exception as exc:
            stats["companies"][key] = {"query": name, "error": f"{type(exc).__name__}: {exc}"}
            stats["warnings"].append(f"{key}: {type(exc).__name__}: {exc}")
    stats["awards"] = total
    stats["resolved_awards"] = matched
    return stats
