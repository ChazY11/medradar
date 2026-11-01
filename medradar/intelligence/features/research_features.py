"""Temporal company–track examples for future public FDA activity."""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Iterable

from ...util import add_months, iso, parse_date, quarter_index, quarter_start, sha1
from .financial_features import FEATURES as FINANCIAL_FEATURES, features_by_company

BASE_FEATURES = (
    "rd_count_12m", "rd_count_previous_12m", "rd_momentum", "rd_count_36m",
    "rd_recency_years", "rd_company_count_12m", "rd_track_count_12m",
    "rd_company_track_share", "rd_pair_active_years", "rd_company_total_36m",
)
DATASET_VERSION = "reverse_rd_v1"


def _material_pma(payload: str) -> bool:
    try:
        row = json.loads(payload or "{}")
    except (TypeError, ValueError):
        return False
    supplement = str(row.get("supplement_number") or "").strip().upper()
    kind = str(row.get("supplement_type") or "").strip().upper()
    return supplement in ("", "0", "S0") or "PANEL TRACK" in kind


def load_rd_events(store: Any) -> list[dict[str, Any]]:
    rows = store.conn.execute(
        "SELECT event_id, kind, event_date, available_at, company_key, track_id, payload "
        "FROM events WHERE kind IN ('510k','pma') AND company_key IS NOT NULL "
        "AND track_id IS NOT NULL AND event_date IS NOT NULL"
    ).fetchall()
    events = []
    for row in rows:
        item = dict(row)
        if item["kind"] == "pma" and not _material_pma(item.get("payload") or ""):
            continue
        item["day"] = parse_date(item["event_date"])
        # SQLite may preserve an ISO datetime; util.parse_date intentionally
        # handles date-only source formats, so normalize the prefix explicitly.
        item["available"] = parse_date(str(item.get("available_at") or "")[:10]) or item["day"]
        if item["day"] and item["available"]:
            events.append(item)
    return events


def quarterly_cutoffs(events: list[dict[str, Any]], horizon_months: int = 12,
                      min_history_years: int = 3) -> tuple[list[date], date]:
    first = min(event["day"] for event in events)
    last = max(event["day"] for event in events)
    start = quarter_start(quarter_index(add_months(first, min_history_years * 12)))
    final_mature = quarter_start(quarter_index(add_months(last, -horizon_months)))
    cutoffs = []
    current = start
    while current <= final_mature:
        cutoffs.append(current)
        current = add_months(current, 3)
    return cutoffs, last


def _recency(events: list[dict[str, Any]], cutoff: date) -> float:
    if not events:
        return 20.0
    return min(20.0, max(0.0, (cutoff - max(e["day"] for e in events)).days / 365.25))


def build_examples(store: Any, *, horizon_months: int = 12,
                   cutoffs: Iterable[str | date] | None = None,
                   include_unmatured: bool = False) -> dict[str, Any]:
    events = load_rd_events(store)
    if not events:
        raise ValueError("No resolved FDA activity events; collect device data first")
    default_cutoffs, coverage_end = quarterly_cutoffs(events, horizon_months)
    cutoff_days = [parse_date(value) for value in cutoffs] if cutoffs is not None else default_cutoffs
    cutoff_days = [day for day in cutoff_days if day]
    cutoff_strings = [iso(day) for day in cutoff_days]
    financial_rows = [dict(row) for row in store.conn.execute("SELECT * FROM financial_facts")]
    financial = features_by_company(financial_rows, cutoff_strings)
    companies = sorted({event["company_key"] for event in events})
    pairs = sorted({(event["company_key"], event["track_id"]) for event in events})
    examples: list[dict[str, Any]] = []
    skipped_immature = 0
    for cutoff in cutoff_days:
        horizon_end = add_months(cutoff, horizon_months)
        history = [e for e in events if e["day"] <= cutoff and e["available"] <= cutoff]
        future = [e for e in events if cutoff < e["day"] <= horizon_end]
        by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        by_company: Counter[str] = Counter()
        by_company36: Counter[str] = Counter()
        by_track: Counter[str] = Counter()
        for event in history:
            by_pair[(event["company_key"], event["track_id"])].append(event)
            if cutoff - timedelta(days=1095) < event["day"] <= cutoff:
                by_company36[event["company_key"]] += 1
            if cutoff - timedelta(days=365) < event["day"] <= cutoff:
                by_company[event["company_key"]] += 1
                by_track[event["track_id"]] += 1
        future_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for event in future:
            future_by_pair[(event["company_key"], event["track_id"])].append(event)
        for company, track in pairs:
            pair_history = by_pair.get((company, track), [])
            if not pair_history:
                continue  # first-entry prediction is a separate, left-censored task
            recent = [e for e in pair_history if cutoff - timedelta(days=365) < e["day"] <= cutoff]
            previous = [e for e in pair_history if cutoff - timedelta(days=730) < e["day"] <= cutoff - timedelta(days=365)]
            trailing36 = [e for e in pair_history if cutoff - timedelta(days=1095) < e["day"] <= cutoff]
            company36 = by_company36[company]
            first_day = min(e["day"] for e in pair_history)
            features: dict[str, float | None] = {
                "rd_count_12m": float(len(recent)),
                "rd_count_previous_12m": float(len(previous)),
                "rd_momentum": math.log1p(len(recent)) - math.log1p(len(previous)),
                "rd_count_36m": float(len(trailing36)),
                "rd_recency_years": _recency(pair_history, cutoff),
                "rd_company_count_12m": float(by_company[company]),
                "rd_track_count_12m": float(by_track[track]),
                "rd_company_track_share": len(recent) / max(by_company[company], 1),
                "rd_pair_active_years": max(0.0, (cutoff - first_day).days / 365.25),
                "rd_company_total_36m": float(company36),
            }
            features.update(financial.get((company, iso(cutoff)), {name: None for name in FINANCIAL_FEATURES}))
            targets = future_by_pair.get((company, track), [])
            mature = horizon_end <= coverage_end
            if not mature and not include_unmatured:
                skipped_immature += 1
                continue
            first_target = min((e["day"] for e in targets), default=None)
            example = {
                "example_id": sha1(f"{DATASET_VERSION}|{iso(cutoff)}|{horizon_months}|{company}|{track}")[:32],
                "cutoff": iso(cutoff), "horizon_months": horizon_months,
                "company_key": company, "track_id": track, "features": features,
                "feature_available_at": iso(cutoff),
                "label": int(bool(targets)) if mature else None,
                "first_target_event_date": iso(first_target) if first_target else None,
                "target_event_count": len(targets) if mature else None,
                "maturity": "mature" if mature else "pending",
            }
            examples.append(example)
    return {
        "dataset_version": DATASET_VERSION, "examples": examples, "cutoffs": cutoff_strings,
        "coverage_end": iso(coverage_end), "event_count": len(events),
        "company_count": len(companies), "pair_count": len(pairs),
        "base_features": list(BASE_FEATURES), "financial_features": list(FINANCIAL_FEATURES),
        "skipped_immature": skipped_immature,
        "target": "Any material public FDA 510(k)/original-or-panel-track PMA activity for an already-active company-track pair in the next 12 months",
        "timing": "Features require event_date<=cutoff and available_at<=cutoff; targets use future event_date; financial facts require filed<=cutoff",
    }
