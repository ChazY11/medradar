"""Competitive comparison over attributed regulatory records.

Comparison output is deliberately conservative:

* it never ranks organizations, and always carries the records-are-not-innovation disclaimer;
* it reports coverage per organization per source, because a difference in records can be a
  difference in coverage;
* it warns when pathway mix, category mapping or attribution review state differ enough to make
  a raw count misleading;
* rates are computed per complete calendar year only.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Sequence

from .dataset import (
    EVENT_TYPE_LABELS,
    EVENT_TYPE_ORDER,
    SOURCES_ORDER,
    Dataset,
    Event,
    aggregate,
)

MAX_ORGS = 4
MIN_ORGS = 2

DISCLAIMER = (
    "Counts are regulatory records attributed to each organization by exact applicant spelling. "
    "They are not a measure of innovation, product quality or market share, and counts of different "
    "event types are not comparable with each other. Where source coverage differs between "
    "organizations, part of any difference is a data-coverage difference."
)


def _latest_complete_year(dataset: Dataset) -> int:
    latest = dataset.manifest.get("coverage", {}).get("max_event_date")
    if not latest:
        return date.today().year - 1
    try:
        moment = date.fromisoformat(str(latest)[:10])
    except ValueError:
        return date.today().year - 1
    # a year is complete only if the snapshot's latest record is at or beyond its 31 December
    if moment.month == 12 and moment.day == 31:
        return moment.year
    return moment.year - 1


def default_window(dataset: Dataset, years: int = 5) -> tuple[str, str, list[str]]:
    latest = _latest_complete_year(dataset)
    first = latest - years + 1
    return f"{first}-01-01", f"{latest}-12-31", [str(year) for year in range(first, latest + 1)]


def complete_years(date_from: str, date_to: str) -> list[str]:
    try:
        start = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
    except ValueError:
        return []
    years = []
    year = start.year
    while year <= end.year:
        if start <= date(year, 1, 1) and end >= date(year, 12, 31):
            years.append(str(year))
        year += 1
    return years


def _partial_years(date_from: str, date_to: str, years: Sequence[str]) -> list[str]:
    complete = set(years)
    partial = []
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    for year in range(start.year, end.year + 1):
        if str(year) not in complete:
            partial.append(str(year))
    return partial


def build_compare(
    dataset: Dataset,
    org_keys: Sequence[str],
    date_from: str | None = None,
    date_to: str | None = None,
    event_types: Sequence[str] | None = None,
) -> dict[str, Any]:
    keys = [key for key in dict.fromkeys(org_keys) if key]
    if len(keys) < MIN_ORGS:
        raise ValueError("compare needs at least " + str(MIN_ORGS) + " organizations")
    if len(keys) > MAX_ORGS:
        raise ValueError("compare accepts at most " + str(MAX_ORGS) + " organizations")
    for key in keys:
        if dataset.organization(key) is None:
            raise KeyError(key)

    default_from, default_to, default_years = default_window(dataset)
    start = date_from or default_from
    end = date_to or default_to
    if date_from or date_to:
        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
        except ValueError as error:
            raise ValueError("invalid date bound: " + str(error)) from error
        if start_date > end_date:
            raise ValueError("from must not be after to")
    years = complete_years(start, end)
    partial = _partial_years(start, end, years)
    types = [item for item in (event_types or EVENT_TYPE_ORDER) if item in EVENT_TYPE_ORDER]

    window = {"from": start, "to": end}
    sides = []
    all_tracked_in_window: list[Event] = []
    for key in keys:
        org = dataset.organization(key)
        events = dataset.filter_events(org_keys=[key], event_types=types, date_from=start, date_to=end)
        side = _side(dataset, key, events, window, years)
        sides.append(side)
    # denominator for shares: every tracked organization's attributed records in the same window
    for org in dataset.registry.organizations:
        all_tracked_in_window.extend(dataset.filter_events(org_keys=[org.key], event_types=types, date_from=start, date_to=end))
    denominator: dict[str, int] = {event_type: 0 for event_type in EVENT_TYPE_ORDER}
    for event in all_tracked_in_window:
        denominator[event.event_type] = denominator.get(event.event_type, 0) + 1
    for side in sides:
        for event_type in EVENT_TYPE_ORDER:
            total = denominator.get(event_type, 0)
            side["share_of_all_tracked"][event_type] = round(side["counts_by_type"].get(event_type, 0) / total, 6) if total else 0.0

    totals_by_type = []
    for event_type in EVENT_TYPE_ORDER:
        values = [{"org_key": side["key"], "count": side["counts_by_type"].get(event_type, 0)} for side in sides]
        totals_by_type.append({
            "event_type": event_type,
            "label": EVENT_TYPE_LABELS[event_type],
            "values": values,
            "note": "records in the effective window" if not partial else "records in the effective window; partial calendar years are shown but excluded from per-year rates",
        })

    category_matrix = _matrix(sides, "categories")
    class_matrix = _matrix(sides, "classes")
    for row in class_matrix:
        row["device_class"] = row["id"]

    warnings = _warnings(dataset, sides, partial, types, denominator)
    return {
        "organizations": [
            {
                "key": side["key"],
                "display_name": side["display_name"],
                "legal_name": side["legal_name"],
                "ticker": side["ticker"],
                "country": side["country"],
                "counts": side["counts"],
                "counts_by_type": side["counts_by_type"],
                "coverage": side["coverage"],
                "aggregations": side["aggregations"],
                "per_year_totals": side["per_year_totals"],
                "share_of_all_tracked": side["share_of_all_tracked"],
            }
            for side in sides
        ],
        "window": {
            "requested": {"from": date_from, "to": date_to},
            "effective": window,
            "complete_years": years,
            "note": "Per-year rates use complete calendar years only; partial years at the window edges are shown but excluded from rates.",
        },
        "totals_by_type": totals_by_type,
        "category_matrix": category_matrix,
        "class_matrix": class_matrix,
        "warnings": warnings,
        "disclaimer": DISCLAIMER,
        "basis": dataset.basis([], event_types=types, window=window, rule="Count of attributed regulatory records inside the effective window; shares use all tracked organizations in the same window as the denominator."),
        "snapshot": dataset.snapshot_ref(),
        "freshness": dataset.freshness(),
    }


def _side(dataset: Dataset, key: str, events: list[Event], window: dict[str, Any], years: Sequence[str]) -> dict[str, Any]:
    org = dataset.organization(key)
    counts = dataset.counts(events)
    by_type: dict[str, int] = {event_type: 0 for event_type in EVENT_TYPE_ORDER}
    for event in events:
        by_type[event.event_type] = by_type.get(event.event_type, 0) + 1
    years_rows = []
    year_index = {row["year"]: row for row in aggregate(events)["by_year"]}
    for year in years:
        row = year_index.get(year)
        years_rows.append({
            "year": year,
            "total": row["total"] if row else 0,
            "by_type": row["counts"] if row else {event_type: 0 for event_type in EVENT_TYPE_ORDER},
        })
    sources = []
    for source_id in SOURCES_ORDER:
        source_events = [event for event in events if event.source_id == source_id]
        dates = [event.event_date for event in source_events if event.event_date]
        sources.append({
            "source_id": source_id,
            "name": {
                "openfda_510k": "FDA 510(k)",
                "openfda_pma": "FDA PMA",
                "openfda_recall": "FDA recalls",
            }[source_id],
            "records": len(source_events),
            "min_event_date": min(dates) if dates else None,
            "max_event_date": max(dates) if dates else None,
        })
    aggregations = aggregate(events)
    return {
        "key": key,
        "display_name": org.display_name,
        "legal_name": org.legal_name,
        "ticker": org.ticker,
        "country": org.country,
        "counts": counts,
        "counts_by_type": by_type,
        "coverage": {
            "window": window,
            "sources": sources,
            "unmapped_category": counts["unmapped_category"],
            "pending_review": counts["pending_review"],
        },
        "aggregations": aggregations,
        "per_year_totals": years_rows,
        "share_of_all_tracked": {},
        "categories": aggregations["by_category"],
        "classes": aggregations["by_class"],
        "total": counts["records"],
    }


def _matrix(sides: Sequence[dict[str, Any]], attr: str) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for side in sides:
        for row in side[attr]:
            key = row.get("id") or row.get("device_class")
            label = row.get("label") or ("Class " + str(row.get("device_class")) if row.get("device_class") != "unknown" else "Class unknown")
            bucket = rows.setdefault(str(key), {"id": str(key), "label": label, "values": {}})
            bucket["values"][side["key"]] = row.get("total") if "total" in row else row.get("count", 0)
    out = []
    for bucket in rows.values():
        values = [{"org_key": side["key"], "count": int(bucket["values"].get(side["key"], 0))} for side in sides]
        total = sum(item["count"] for item in values)
        if total == 0:
            continue
        out.append({"id": bucket["id"], "label": bucket["label"], "values": values,
                    "note": "records by category" if attr == "categories" else "records by device class"})
    out.sort(key=lambda row: -sum(item["count"] for item in row["values"]))
    return out


def _warnings(
    dataset: Dataset,
    sides: Sequence[dict[str, Any]],
    partial: Sequence[str],
    types: Sequence[str],
    denominator: dict[str, int],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if partial:
        warnings.append({
            "code": "partial_year_excluded",
            "severity": "warning",
            "message": "The requested window includes partial calendar year(s) " + ", ".join(partial) + ". They are shown but excluded from per-year rates.",
            "org_keys": [side["key"] for side in sides],
        })
    source_sets = []
    for side in sides:
        present = {row["source_id"] for row in side["coverage"]["sources"] if row["records"]}
        source_sets.append(present)
    if len({frozenset(item) for item in source_sets}) > 1:
        warnings.append({
            "code": "coverage_mismatch",
            "severity": "warning",
            "message": "Source coverage differs between organizations: "
            + "; ".join(side["display_name"] + " has " + (", ".join(sorted(sources)) if sources else "no source with records") for side, sources in zip(sides, source_sets))
            + ". Part of any difference is a coverage difference, not an activity difference.",
            "org_keys": [side["key"] for side in sides],
        })
    if any(side["counts"]["unmapped_category"] for side in sides):
        warnings.append({
            "code": "unmapped_category_present",
            "severity": "info",
            "message": "Some records use product codes absent from the FDA classification dictionary; they are counted in totals but grouped as unclassified.",
            "org_keys": [side["key"] for side in sides if side["counts"]["unmapped_category"]],
        })
    if any(side["counts"]["pending_review"] for side in sides):
        warnings.append({
            "code": "pending_review_present",
            "severity": "warning",
            "message": "Some attributed records come from applicant spellings whose attribution is pending human review. Treat those counts as provisional.",
            "org_keys": [side["key"] for side in sides if side["counts"]["pending_review"]],
        })
    shares = []
    for side in sides:
        pma = side["counts_by_type"].get("pma", 0) + side["counts_by_type"].get("pma_supplement", 0)
        total = side["total"] or 1
        shares.append(pma / total)
    if shares and (max(shares) - min(shares)) >= 0.30:
        warnings.append({
            "code": "pathway_mix",
            "severity": "warning",
            "message": "The PMA share of records differs by at least 30 percentage points between organizations. Totals across different regulatory pathways are not directly comparable.",
            "org_keys": [side["key"] for side in sides],
        })
    for side in sides:
        total = side["total"] or 0
        recall = side["counts_by_type"].get("recall", 0)
        if total >= 10 and recall / total >= 0.5:
            warnings.append({
                "code": "recall_share",
                "severity": "info",
                "message": side["display_name"] + ": recalls make up " + str(round(100 * recall / total)) + "% of records in this window. Recalls are safety actions, not product launches.",
                "org_keys": [side["key"]],
            })
    for side in sides:
        named = [event_type for event_type in types if side["counts_by_type"].get(event_type, 0) > 0]
        if sum(side["counts_by_type"].get(event_type, 0) for event_type in named) < 10:
            warnings.append({
                "code": "low_volume",
                "severity": "info",
                "message": side["display_name"] + " has fewer than 10 attributed records in this window. Percentages on such a base are unstable.",
                "org_keys": [side["key"]],
            })
    return warnings
