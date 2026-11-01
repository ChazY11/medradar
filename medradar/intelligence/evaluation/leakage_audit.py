"""Temporal leakage checks for persisted examples and source facts.

The old audit only re-read the stored ``feature_available_at`` declaration, which
the feature builder sets to the cutoff unconditionally — so any injected
future-derived feature passed. This module now independently replays every
stored example's features from the source tables with SQL restricted to rows
whose availability is at or before the cutoff, and compares the result with the
stored feature JSON.

Honesty note: this is an *as-of replay / consistency* audit. It can detect a
stored feature value that could not be produced from information known at the
cutoff. It cannot prove the absence of semantic leakage (for example a current
product-code mapping applied to historical events); see docs/REVERSE_RD.md.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from ...util import parse_date
from ..features.financial_features import (
    FEATURES as FINANCIAL_FEATURE_NAMES,
    FLOW_TAGS,
    RD_TAGS,
    REVENUE_TAGS,
)
from ..features.research_features import BASE_FEATURES

TOLERANCE = 1e-9
MAX_REPORTED_MISMATCHES = 25
INSTANT_TAGS = {"CashAndCashEquivalentsAtCarryingValue", "InventoryNet"}

# Replayed independently from the feature builder. Only the feature-name tuples
# and the XBRL tag vocabulary are shared; every filter/aggregation below is a
# separate SQL + Python implementation.
_EVENTS_AS_OF_SQL = """
SELECT kind, event_date, available_at, company_key, track_id, payload
FROM events
WHERE kind IN ('510k', 'pma')
  AND company_key IS NOT NULL AND track_id IS NOT NULL
  AND substr(event_date, 1, 10) <= ?
  AND (available_at IS NULL OR substr(available_at, 1, 10) <= ?)
"""
_FINANCIAL_PERIODS_SQL = """
SELECT tag, period_start, period_end, fiscal_year, value, available_at, accession
FROM (
    SELECT tag, unit, value, period_start, period_end, available_at, accession, fiscal_year,
           ROW_NUMBER() OVER (
               PARTITION BY tag, period_start, period_end
               ORDER BY available_at DESC, COALESCE(accession, '') DESC
           ) AS row_number
    FROM financial_facts
    WHERE company_key = ? AND unit = 'USD'
      AND available_at IS NOT NULL AND period_end IS NOT NULL
      AND substr(available_at, 1, 10) <= ?
      AND substr(period_end, 1, 10) <= ?
) WHERE row_number = 1
"""


# ----------------------------------------------------------------- map-based helpers
def _material_pma(payload: Any) -> bool:
    try:
        row = json.loads(payload or "{}")
    except (TypeError, ValueError):
        return False
    supplement = str(row.get("supplement_number") or "").strip().upper()
    kind = str(row.get("supplement_type") or "").strip().upper()
    return supplement in ("", "0", "S0") or "PANEL TRACK" in kind


def _same(stored: Any, replayed: Any) -> bool:
    if stored is None or replayed is None:
        return stored is None and replayed is None
    try:
        left, right = float(stored), float(replayed)
    except (TypeError, ValueError):
        return stored == replayed
    if not (math.isfinite(left) and math.isfinite(right)):
        return left == right
    return math.isclose(left, right, rel_tol=TOLERANCE, abs_tol=TOLERANCE)


def _replay_base_features(history: list[Any], pairs: set[tuple[str, str]],
                          cutoff_day: date) -> dict[tuple[str, str], dict[str, float | None]]:
    """Recompute the ten R&D-history features from the as-of event rows."""
    by_pair: dict[tuple[str, str], list[date]] = defaultdict(list)
    by_company: Counter[str] = Counter()
    by_company36: Counter[str] = Counter()
    by_track: Counter[str] = Counter()
    for row in history:
        if row["kind"] == "pma" and not _material_pma(row["payload"]):
            continue
        day = parse_date(row["event_date"])
        if day is None or day > cutoff_day:
            continue
        company, track = row["company_key"], row["track_id"]
        by_pair[(company, track)].append(day)
        if cutoff_day - timedelta(days=1095) < day <= cutoff_day:
            by_company36[company] += 1
        if cutoff_day - timedelta(days=365) < day <= cutoff_day:
            by_company[company] += 1
            by_track[track] += 1
    result: dict[tuple[str, str], dict[str, float | None]] = {}
    for pair in pairs:
        days = by_pair.get(pair)
        if not days:
            continue  # builder only emits examples for already-active pairs
        company, track = pair
        recent = sum(1 for day in days if cutoff_day - timedelta(days=365) < day <= cutoff_day)
        previous = sum(1 for day in days if cutoff_day - timedelta(days=730) < day <= cutoff_day - timedelta(days=365))
        trailing36 = sum(1 for day in days if cutoff_day - timedelta(days=1095) < day <= cutoff_day)
        first_day = min(days)
        result[pair] = {
            "rd_count_12m": float(recent),
            "rd_count_previous_12m": float(previous),
            "rd_momentum": math.log1p(recent) - math.log1p(previous),
            "rd_count_36m": float(trailing36),
            "rd_recency_years": min(20.0, max(0.0, (cutoff_day - max(days)).days / 365.25)),
            "rd_company_count_12m": float(by_company[company]),
            "rd_track_count_12m": float(by_track[track]),
            "rd_company_track_share": recent / max(by_company[company], 1),
            "rd_pair_active_years": max(0.0, (cutoff_day - first_day).days / 365.25),
            "rd_company_total_36m": float(by_company36[company]),
        }
    return result


# -------------------------------------------------------------- financial replay
def _annual_series(period_rows: list[Any], tag: str, cutoff_day: date) -> dict[str, float]:
    """Latest filed annual observation per fiscal year, restricted to the cutoff."""
    annual: dict[str, tuple[date, str, float]] = {}
    for row in period_rows:
        if row["tag"] != tag:
            continue
        end = parse_date(row["period_end"])
        if end is None or end > cutoff_day:
            continue
        if tag in FLOW_TAGS:
            start = parse_date(row["period_start"])
            if not start or not 300 <= (end - start).days <= 450:
                continue
        year_key = str(row["fiscal_year"] or end.year)
        candidate = (end, str(row["accession"] or ""), float(row["value"]))
        current = annual.get(year_key)
        if current is None or candidate[:2] > current[:2]:
            annual[year_key] = candidate
    return {year: value for year, (_end, _accession, value) in annual.items()}


def _growth(series: dict[str, float]) -> float | None:
    years = sorted(series)
    if len(years) < 2:
        return None
    previous, current = series[years[-2]], series[years[-1]]
    return (current - previous) / max(abs(previous), 1.0) if previous != 0 else None


def _latest(series: dict[str, float]) -> float | None:
    return series[sorted(series)[-1]] if series else None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / max(abs(denominator), 1.0)


def _replay_financial(store: Any, company: str, cutoff: str, cutoff_day: date,
                      cache: dict[tuple[str, str], dict[str, float | None]],
                      company_has_facts: dict[str, bool]) -> dict[str, float | None]:
    key = (company, cutoff)
    if key in cache:
        return cache[key]
    if company not in company_has_facts:
        company_has_facts[company] = store.conn.execute(
            "SELECT 1 FROM financial_facts WHERE company_key = ? LIMIT 1", (company,)).fetchone() is not None
    if not company_has_facts[company]:
        # The builder emits null financial features for companies without any facts.
        result = {name: None for name in FINANCIAL_FEATURE_NAMES}
        cache[key] = result
        return result
    period_rows = [dict(row) for row in store.conn.execute(
        _FINANCIAL_PERIODS_SQL, (company, cutoff, cutoff))]
    series = {tag: _annual_series(period_rows, tag, cutoff_day)
              for tag in set(FLOW_TAGS) | set(REVENUE_TAGS) | INSTANT_TAGS}
    revenue = next((series[tag] for tag in REVENUE_TAGS if series[tag]), {})
    rd = next((series[tag] for tag in RD_TAGS if series[tag]), {})
    rd_now, rev_now = _latest(rd), _latest(revenue)
    rd_previous = rd[sorted(rd)[-2]] if len(rd) >= 2 else None
    rev_previous = revenue[sorted(revenue)[-2]] if len(revenue) >= 2 else None
    intensity = _ratio(rd_now, rev_now)
    previous_intensity = _ratio(rd_previous, rev_previous)
    facts_available = store.conn.execute(
        "SELECT COUNT(*) FROM financial_facts WHERE company_key = ? AND available_at IS NOT NULL "
        "AND substr(available_at, 1, 10) <= ?", (company, cutoff)).fetchone()[0]
    result = {
        "fin_revenue_growth": _growth(revenue),
        "fin_rd_growth": _growth(rd),
        "fin_rd_intensity": intensity,
        "fin_rd_intensity_delta": (intensity - previous_intensity
                                   if intensity is not None and previous_intensity is not None else None),
        "fin_operating_margin": _ratio(_latest(series["OperatingIncomeLoss"]), rev_now),
        "fin_cash_to_rd": _ratio(_latest(series["CashAndCashEquivalentsAtCarryingValue"]), rd_now),
        "fin_ocf_to_rd": _ratio(_latest(series["NetCashProvidedByUsedInOperatingActivities"]), rd_now),
        "fin_capex_intensity": _ratio(_latest(series["PaymentsToAcquirePropertyPlantAndEquipment"]), rev_now),
        "fin_acquisition_to_revenue": _ratio(_latest(series["PaymentsToAcquireBusinessesNetOfCashAcquired"]), rev_now),
        "fin_inventory_growth": _growth(series["InventoryNet"]),
        "fin_facts_available": float(facts_available),
    }
    cache[key] = result
    return result


# ------------------------------------------------------------------------ audit
def audit_examples(store: Any, dataset_version: str) -> dict[str, Any]:
    rows = [dict(row) for row in store.conn.execute(
        "SELECT * FROM forecast_examples WHERE dataset_version = ?", (dataset_version,))]
    violations: list[dict[str, Any]] = []
    for row in rows:
        cutoff = parse_date(row["cutoff"])
        available = parse_date(row["feature_available_at"])
        if not cutoff or not available or available > cutoff:
            violations.append({"example_id": row["example_id"], "reason": "feature availability after cutoff"})
        if row["label"] is not None and row["maturity"] != "mature":
            violations.append({"example_id": row["example_id"], "reason": "label on immature origin"})
    procurement = store.conn.execute(
        "SELECT COUNT(*) FROM procurement_awards WHERE pit_usable=1 AND data_quality LIKE '%first_publication_unknown%'"
    ).fetchone()[0]
    if procurement:
        violations.append({"reason": "snapshot procurement incorrectly marked point-in-time usable", "rows": procurement})

    feature_names = list(BASE_FEATURES) + list(FINANCIAL_FEATURE_NAMES)
    per_feature: dict[str, int] = {name: 0 for name in feature_names}
    mismatches: list[dict[str, Any]] = []
    mismatch_count = 0
    checked_values = 0
    unreplayable = 0
    financial_cache: dict[tuple[str, str], dict[str, float | None]] = {}
    company_has_facts: dict[str, bool] = {}
    by_cutoff: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cutoff[str(row["cutoff"])].append(row)
    for cutoff, group in sorted(by_cutoff.items()):
        cutoff_day = parse_date(cutoff)
        if cutoff_day is None:
            for row in group:
                violations.append({"example_id": row["example_id"], "reason": "unparsable cutoff"})
            continue
        history = store.conn.execute(_EVENTS_AS_OF_SQL, (cutoff, cutoff)).fetchall()
        pairs = {(row["company_key"], row["track_id"]) for row in group}
        replayed_base = _replay_base_features(history, pairs, cutoff_day)
        for row in group:
            pair = (row["company_key"], row["track_id"])
            expected = replayed_base.get(pair)
            if expected is None:
                unreplayable += 1
                if len(mismatches) < MAX_REPORTED_MISMATCHES:
                    mismatches.append({"example_id": row["example_id"], "cutoff": cutoff,
                                       "reason": "no as-of event history reproduced for an existing example"})
                continue
            expected.update(_replay_financial(
                store, row["company_key"], cutoff, cutoff_day, financial_cache, company_has_facts))
            try:
                stored = json.loads(row["features"])
            except (TypeError, ValueError):
                stored = None
            if not isinstance(stored, dict):
                mismatch_count += 1
                if len(mismatches) < MAX_REPORTED_MISMATCHES:
                    mismatches.append({"example_id": row["example_id"], "cutoff": cutoff,
                                       "reason": "stored feature payload is not a JSON object"})
                continue
            for name in feature_names:
                checked_values += 1
                if not _same(stored.get(name), expected.get(name)):
                    proxy = name
                    per_feature[proxy] += 1
                    mismatch_count += 1
                    if len(mismatches) < MAX_REPORTED_MISMATCHES:
                        mismatches.append({
                            "example_id": row["example_id"], "cutoff": cutoff, "feature": name,
                            "stored": stored.get(name), "replayed": expected.get(name)})
            for name in sorted(set(stored) - set(feature_names)):
                mismatch_count += 1
                if len(mismatches) < MAX_REPORTED_MISMATCHES:
                    mismatches.append({"example_id": row["example_id"], "cutoff": cutoff, "feature": name,
                                       "reason": "feature cannot be replayed by this audit"})
    violations.extend(mismatches)
    return {
        "method": "independent_as_of_replay",
        "method_detail": (
            "For every stored example the features are re-derived directly from the events and financial_facts "
            "tables with SQL restricted to rows whose availability is at or before the cutoff "
            "(events: event_date<=cutoff AND available_at<=cutoff; financials: available_at<=cutoff AND "
            "period_end<=cutoff, latest filed row per period), then compared with the stored feature JSON. "
            "The builder's filtering code is not called."),
        "declared_field_checks": ["feature_available_at<=cutoff", "label only on mature origins",
                                  "snapshot procurement is not pit_usable"],
        "tolerance": {"absolute": TOLERANCE, "relative": TOLERANCE},
        "checked_examples": len(rows),
        "checked_cutoffs": len(by_cutoff),
        "checked_feature_values": checked_values,
        "unreplayable_examples": unreplayable,
        "per_feature_mismatches": per_feature,
        "mismatch_count": mismatch_count,
        "mismatches": mismatches,
        "violations": violations[:MAX_REPORTED_MISMATCHES],
        "violation_count": len(violations),
        "ok": not violations,
        "limitations": (
            "As-of replay/consistency audit, not a proof of absence of semantic leakage: unversioned current "
            "product-code mappings, company aliases or target-definition choices applied to history cannot be "
            "detected this way. It also cannot re-verify provenance of dates themselves."),
    }
