"""Descriptive current-snapshot procurement demand features (not backtest inputs)."""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def procurement_summary(store: Any, *, top_n: int = 25) -> dict[str, Any]:
    rows = [dict(row) for row in store.conn.execute(
        "SELECT company_key,buyer,product_category,naics_code,contract_value,period_start,"
        "pit_usable,data_quality FROM procurement_awards")]
    by_company: dict[str, dict[str, Any]] = defaultdict(lambda: {"awards": 0, "obligation_usd": 0.0, "buyers": set()})
    by_category: dict[str, dict[str, Any]] = defaultdict(lambda: {"awards": 0, "obligation_usd": 0.0, "suppliers": set()})
    by_year: dict[str, dict[str, Any]] = defaultdict(lambda: {"awards": 0, "obligation_usd": 0.0})
    for row in rows:
        value = float(row.get("contract_value") or 0.0)
        company = row.get("company_key") or "__unmatched__"
        category = row.get("naics_code") or row.get("product_category") or "unknown"
        year = str(row.get("period_start") or "unknown")[:4]
        by_company[company]["awards"] += 1
        by_company[company]["obligation_usd"] += value
        if row.get("buyer"):
            by_company[company]["buyers"].add(row["buyer"])
        by_category[category]["awards"] += 1
        by_category[category]["obligation_usd"] += value
        if row.get("company_key"):
            by_category[category]["suppliers"].add(row["company_key"])
        by_year[year]["awards"] += 1
        by_year[year]["obligation_usd"] += value
    companies = [{"company_key": key, **{k: (sorted(v) if isinstance(v, set) else v) for k, v in data.items()}}
                 for key, data in by_company.items()]
    categories = [{"category": key, **{k: (sorted(v) if isinstance(v, set) else v) for k, v in data.items()}}
                  for key, data in by_category.items()]
    companies.sort(key=lambda row: row["obligation_usd"], reverse=True)
    categories.sort(key=lambda row: row["obligation_usd"], reverse=True)
    return {
        "status": "descriptive_current_snapshot_not_point_in_time",
        "award_amount_meaning": "contract obligation; not tender budget, delivery or recognized revenue",
        "awards": len(rows), "pit_usable_awards": sum(int(row["pit_usable"]) for row in rows),
        "companies": companies[:top_n], "categories": categories,
        "performance_start_year": [{"year": year, **by_year[year]} for year in sorted(by_year)],
        "coverage_warning": "Recipient search and NAICS filters limit coverage; zero results do not establish zero demand.",
    }
