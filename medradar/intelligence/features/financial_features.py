"""Point-in-time consolidated financial features from filed XBRL facts."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Iterable

from ...util import parse_date

FLOW_TAGS = {
    "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
    "GrossProfit", "OperatingIncomeLoss", "ResearchAndDevelopmentExpense",
    "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
    "PaymentsToAcquirePropertyPlantAndEquipment", "NetCashProvidedByUsedInOperatingActivities",
    "PaymentsToAcquireBusinessesNetOfCashAcquired",
}
REVENUE_TAGS = ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet")
RD_TAGS = ("ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost")
FEATURES = (
    "fin_revenue_growth", "fin_rd_growth", "fin_rd_intensity", "fin_rd_intensity_delta",
    "fin_operating_margin", "fin_cash_to_rd", "fin_ocf_to_rd", "fin_capex_intensity",
    "fin_acquisition_to_revenue", "fin_inventory_growth", "fin_facts_available",
)


def _annual_series(rows: Iterable[dict[str, Any]], tag: str, cutoff: date) -> dict[str, float]:
    """Latest filed value per period, then latest annual period per fiscal year.

    Amendments filed after ``cutoff`` are invisible. Duration facts outside
    300–450 days are excluded so quarterly values are never mixed with annual
    growth. Instant facts (cash, inventory) use their period end directly.
    """
    by_period: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if row["tag"] != tag or row["unit"] != "USD" or not row.get("available_at"):
            continue
        available = parse_date(row["available_at"])
        end = parse_date(row["period_end"])
        if not available or not end or available > cutoff or end > cutoff:
            continue
        key = (str(row.get("period_start") or ""), str(row["period_end"]))
        if key not in by_period or (available, str(row.get("accession") or "")) > (
            parse_date(by_period[key]["available_at"]), str(by_period[key].get("accession") or "")
        ):
            by_period[key] = row
    annual: dict[str, tuple[date, float]] = {}
    for (start_raw, end_raw), row in by_period.items():
        end = parse_date(end_raw)
        if end is None:
            continue
        if tag in FLOW_TAGS:
            start = parse_date(start_raw)
            if not start or not 300 <= (end - start).days <= 450:
                continue
        # A company can file duplicate annual facts under different forms. The
        # latest public filing at the cutoff wins, deterministically.
        year_key = str(row.get("fiscal_year") or end.year)
        candidate = (end, float(row["value"]))
        if year_key not in annual or (end, str(row.get("accession") or "")) > (
            annual[year_key][0], str(row.get("accession") or "")
        ):
            annual[year_key] = candidate
    return {year: value for year, (_end, value) in annual.items()}


def _growth(series: dict[str, float]) -> float | None:
    years = sorted(series)
    if len(years) < 2:
        return None
    previous, current = series[years[-2]], series[years[-1]]
    if previous == 0:
        return None
    return (current - previous) / max(abs(previous), 1.0)


def _latest(series: dict[str, float]) -> float | None:
    return series[sorted(series)[-1]] if series else None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / max(abs(denominator), 1.0)


def financial_features(rows: list[dict[str, Any]], cutoff: str | date) -> dict[str, float | None]:
    cutoff_day = parse_date(cutoff)
    if cutoff_day is None:
        raise ValueError(f"invalid cutoff {cutoff!r}")
    series = {tag: _annual_series(rows, tag, cutoff_day) for tag in set(FLOW_TAGS) | set(REVENUE_TAGS) | {
        "CashAndCashEquivalentsAtCarryingValue", "InventoryNet"
    }}
    revenue = next((series[tag] for tag in REVENUE_TAGS if series[tag]), {})
    rd = next((series[tag] for tag in RD_TAGS if series[tag]), {})
    rd_now, rev_now = _latest(rd), _latest(revenue)
    rd_previous = rd[sorted(rd)[-2]] if len(rd) >= 2 else None
    rev_previous = revenue[sorted(revenue)[-2]] if len(revenue) >= 2 else None
    intensity = _ratio(rd_now, rev_now)
    previous_intensity = _ratio(rd_previous, rev_previous)
    values: dict[str, float | None] = {
        "fin_revenue_growth": _growth(revenue),
        "fin_rd_growth": _growth(rd),
        "fin_rd_intensity": intensity,
        "fin_rd_intensity_delta": intensity - previous_intensity if intensity is not None and previous_intensity is not None else None,
        "fin_operating_margin": _ratio(_latest(series["OperatingIncomeLoss"]), rev_now),
        "fin_cash_to_rd": _ratio(_latest(series["CashAndCashEquivalentsAtCarryingValue"]), rd_now),
        "fin_ocf_to_rd": _ratio(_latest(series["NetCashProvidedByUsedInOperatingActivities"]), rd_now),
        "fin_capex_intensity": _ratio(_latest(series["PaymentsToAcquirePropertyPlantAndEquipment"]), rev_now),
        "fin_acquisition_to_revenue": _ratio(_latest(series["PaymentsToAcquireBusinessesNetOfCashAcquired"]), rev_now),
        "fin_inventory_growth": _growth(series["InventoryNet"]),
        "fin_facts_available": float(sum(1 for row in rows if parse_date(row.get("available_at")) and parse_date(row["available_at"]) <= cutoff_day)),
    }
    return values


def features_by_company(rows: list[dict[str, Any]], cutoffs: Iterable[str]) -> dict[tuple[str, str], dict[str, float | None]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["company_key"]].append(row)
    return {(company, cutoff): financial_features(company_rows, cutoff)
            for company, company_rows in grouped.items() for cutoff in cutoffs}
