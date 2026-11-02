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

# Entry (dormant -> active) target. The label asks whether an *already active*
# company will register its first material public event in a technology track it
# has not touched for at least ``dormancy_months``. This is intentionally a
# harder, more decision-relevant question than v1 continuation, and it is
# left-censored: the bulk window starts 2016-11-01, so "dormant" only means
# "no observed event inside the bulk window", never "provably inactive before
# 2016" and never "never active at all".
ENTRY_DATASET_VERSION = "first_entry_v1"
DEFAULT_DORMANCY_MONTHS = 36
# Months since the last observed pair event is capped at the length of the
# observable bulk window (ten years). Pairs that were never observed inside the
# window receive the cap: they are *at least* this dormant, not exactly this old.
ENTRY_INACTIVE_MONTHS_CAP = 120.0
MONTH_LENGTH_DAYS = 365.25 / 12.0
ENTRY_FEATURES = (
    "rd_pair_inactive_months",
    "rd_company_active_tracks_12m",
    "rd_company_active_tracks_delta",
    "rd_track_active_companies_12m",
    "rd_track_active_companies_delta",
    "rd_company_track_novelty_share",
)
# The frozen openFDA bulk lane used by the v1/v2 experiments ends 2026-10-15.
COVERAGE_END_REFERENCE = "2026-10-15"
COVERAGE_END_TOLERANCE_DAYS = 45


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


def _pair_history_features(pair_days: list[date], cutoff: date, *, company: str, track: str,
                           by_company: Counter[str], by_track: Counter[str],
                           by_company36: Counter[str]) -> dict[str, float]:
    """The ten v1 R&D-history features, shared by the continuation and entry targets.

    ``pair_days`` may be empty for the entry target: a pair that was never
    observed inside the bulk window is a valid candidate whose ``rd_count_*``
    values are zero, whose recency is the top-code and whose observable active
    period is zero. For the v1 continuation target the caller only passes
    non-empty histories, so the shared computation is bit-for-bit unchanged.
    """
    recent = [day for day in pair_days if cutoff - timedelta(days=365) < day <= cutoff]
    previous = [day for day in pair_days
                if cutoff - timedelta(days=730) < day <= cutoff - timedelta(days=365)]
    trailing36 = [day for day in pair_days if cutoff - timedelta(days=1095) < day <= cutoff]
    first_day = min(pair_days) if pair_days else None
    return {
        "rd_count_12m": float(len(recent)),
        "rd_count_previous_12m": float(len(previous)),
        "rd_momentum": math.log1p(len(recent)) - math.log1p(len(previous)),
        "rd_count_36m": float(len(trailing36)),
        "rd_recency_years": (_recency([], cutoff) if not pair_days
                             else min(20.0, max(0.0, (cutoff - max(pair_days)).days / 365.25))),
        "rd_company_count_12m": float(by_company[company]),
        "rd_track_count_12m": float(by_track[track]),
        "rd_company_track_share": len(recent) / max(by_company[company], 1),
        "rd_pair_active_years": max(0.0, (cutoff - first_day).days / 365.25) if first_day else 0.0,
        "rd_company_total_36m": float(by_company36[company]),
    }


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
            features: dict[str, float | None] = _pair_history_features(
                [event["day"] for event in pair_history], cutoff, company=company, track=track,
                by_company=by_company, by_track=by_track, by_company36=by_company36)
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


# --------------------------------------------------------------- entry target
def material_event_coverage(events: list[dict[str, Any]]) -> tuple[date, date]:
    """Observed first/last material-event day inside the loaded bulk window."""
    if not events:
        raise ValueError("No material events; cannot derive coverage")
    return min(event["day"] for event in events), max(event["day"] for event in events)


def _coverage_check(coverage_end: date, expected: str | None, tolerance_days: int) -> dict[str, Any]:
    """Fail loudly when the label horizon would leave the observed coverage.

    The 2026-10-15 reference is the documented end of the frozen openFDA bulk
    lane. A different database must pass ``expected_coverage_end=None`` (or its
    own reference) instead of silently producing immature labels.
    """
    reference = parse_date(expected)
    detail: dict[str, Any] = {
        "expected_coverage_end": iso(reference) if reference else None,
        "observed_coverage_end": iso(coverage_end),
        "tolerance_days": tolerance_days,
        "checked": reference is not None,
    }
    if reference is None:
        detail["ok"] = True
        return detail
    delta = abs((coverage_end - reference).days)
    detail["delta_days"] = delta
    detail["ok"] = delta <= tolerance_days
    if not detail["ok"]:
        raise ValueError(
            f"Material-event coverage ends {iso(coverage_end)}, expected {iso(reference)} "
            f"+/-{tolerance_days} days. Refusing to build an entry dataset whose label "
            f"window would silently exit the observed coverage.")
    return detail


def entry_origins(events: list[dict[str, Any]], *, dormancy_months: int = DEFAULT_DORMANCY_MONTHS,
                  horizon_months: int = 12, coverage_start: date | None = None,
                  coverage_end: date | None = None) -> list[date]:
    """Quarter-start origins that survive both coverage constraints.

    ``t - dormancy_months >= coverage_start`` (the dormancy window is fully
    inside observed history) and ``t + horizon_months <= coverage_end`` (the
    label window is fully observed). The dormancy condition uses exact calendar
    months via :func:`add_months`, so the 36-month boundary is not approximated
    with 1095 days.
    """
    first = coverage_start or material_event_coverage(events)[0]
    last = coverage_end or material_event_coverage(events)[1]
    earliest = add_months(first, dormancy_months)
    index = quarter_index(earliest)
    if index is None:
        return []
    current = quarter_start(index)
    if current < earliest:
        current = quarter_start(index + 1)
    cutoffs: list[date] = []
    while add_months(current, horizon_months) <= last:
        cutoffs.append(current)
        current = add_months(current, 3)
    return cutoffs


def build_entry_examples(store: Any, *, dormancy_months: int = DEFAULT_DORMANCY_MONTHS,
                         horizon_months: int = 12,
                         cutoffs: Iterable[str | date] | None = None,
                         include_unmatured: bool = False,
                         expected_coverage_end: str | None = COVERAGE_END_REFERENCE,
                         coverage_end_tolerance_days: int = COVERAGE_END_TOLERANCE_DAYS) -> dict[str, Any]:
    """Dormant -> active track-entry examples with explicit left-censoring.

    Candidate at quarterly cutoff ``t``: a ``(company_key, track_id)`` pair where
    the company already has at least one material event with ``event_date <= t``
    (it is an *active company*), ``track_id`` is non-null, and the pair has ZERO
    material events in ``(t - dormancy_months, t]``. The candidate universe is
    the cross product of active companies and tracks observed by ``t``, so pairs
    that were never observed at all are candidates too; their
    ``rd_pair_inactive_months`` receives the observation-window cap.

    Label: 1 iff a material event exists in ``(t, t + horizon_months]`` for the
    same pair. ``maturity`` is ``mature`` iff ``t + horizon_months <=
    coverage_end``; otherwise the label is ``None`` (``pending``) unless
    ``include_unmatured`` is requested.

    Left-censoring: the bulk window begins at ``coverage_start`` (2016-11-01 in
    the frozen data). "Dormant" therefore means "no event observed inside the
    bulk window", not "provably inactive"; a pair first observed in 2018 may
    have had unobserved pre-2016 activity. The target is first *observed*
    public entry, not internal R&D start.

    Features are strictly point-in-time: every aggregate uses only rows with
    ``event_date <= t`` AND ``available_at <= t``; financial features require
    ``filed/available_at <= t`` exactly as in :func:`build_examples`.
    """
    events = load_rd_events(store)
    if not events:
        raise ValueError("No resolved FDA activity events; collect device data first")
    coverage_start, coverage_end = material_event_coverage(events)
    coverage = _coverage_check(coverage_end, expected_coverage_end, coverage_end_tolerance_days)
    if cutoffs is not None:
        cutoff_days = [day for day in (parse_date(value) for value in cutoffs) if day]
    else:
        cutoff_days = entry_origins(events, dormancy_months=dormancy_months,
                                    horizon_months=horizon_months,
                                    coverage_start=coverage_start, coverage_end=coverage_end)
    cutoff_strings = [iso(day) for day in cutoff_days]
    financial_rows = [dict(row) for row in store.conn.execute("SELECT * FROM financial_facts")]
    financial = features_by_company(financial_rows, cutoff_strings)
    companies = sorted({event["company_key"] for event in events})
    observed_pairs = sorted({(event["company_key"], event["track_id"]) for event in events})
    examples: list[dict[str, Any]] = []
    skipped_pending = 0
    candidates_by_origin: dict[str, int] = {}
    positives_by_origin: dict[str, int] = {}
    used_cutoffs: list[str] = []
    for cutoff in cutoff_days:
        horizon_end = add_months(cutoff, horizon_months)
        mature = horizon_end <= coverage_end
        history = [event for event in events
                   if event["day"] <= cutoff and event["available"] <= cutoff]
        if not history:
            continue
        active_companies = sorted({event["company_key"] for event in history})
        tracks = sorted({event["track_id"] for event in history})
        future = [event for event in events if cutoff < event["day"] <= horizon_end]
        day_12 = cutoff - timedelta(days=365)
        day_24 = cutoff - timedelta(days=730)
        day_36 = cutoff - timedelta(days=1095)
        dormancy_cut = add_months(cutoff, -dormancy_months)
        by_pair: dict[tuple[str, str], list[date]] = defaultdict(list)
        by_company: Counter[str] = Counter()
        by_company_previous: Counter[str] = Counter()
        by_company36: Counter[str] = Counter()
        by_track: Counter[str] = Counter()
        by_track_previous: Counter[str] = Counter()
        company_tracks: dict[str, set[str]] = defaultdict(set)
        company_tracks_previous: dict[str, set[str]] = defaultdict(set)
        track_companies: dict[str, set[str]] = defaultdict(set)
        track_companies_previous: dict[str, set[str]] = defaultdict(set)
        company_events24: Counter[str] = Counter()
        for event in history:
            company, track, day = event["company_key"], event["track_id"], event["day"]
            by_pair[(company, track)].append(day)
            if day_12 < day <= cutoff:
                by_company[company] += 1
                by_track[track] += 1
                company_tracks[company].add(track)
                track_companies[track].add(company)
            elif day_24 < day <= day_12:
                by_company_previous[company] += 1
                by_track_previous[track] += 1
                company_tracks_previous[company].add(track)
                track_companies_previous[track].add(company)
            if day_36 < day <= cutoff:
                by_company36[company] += 1
            if day_24 < day <= cutoff:
                company_events24[company] += 1
        pair_first = {pair: min(days) for pair, days in by_pair.items()}
        novel_events24: Counter[str] = Counter()
        for event in history:
            if day_24 < event["day"] <= cutoff:
                pair = (event["company_key"], event["track_id"])
                if pair_first[pair] > day_24:
                    novel_events24[event["company_key"]] += 1
        future_by_pair: dict[tuple[str, str], list[date]] = defaultdict(list)
        for event in future:
            future_by_pair[(event["company_key"], event["track_id"])].append(event["day"])
        # Dormant candidates: active company x observed track, zero events in
        # the exact calendar dormancy window (t - dormancy, t].
        candidates = [(company, track) for company in active_companies for track in tracks
                      if not by_pair.get((company, track))
                      or max(by_pair[(company, track)]) <= dormancy_cut]
        candidates_by_origin[iso(cutoff)] = len(candidates)
        if not mature and not include_unmatured:
            skipped_pending += len(candidates)
            continue
        used_cutoffs.append(iso(cutoff))
        positives = 0
        for company, track in candidates:
            pair_days = by_pair.get((company, track), [])
            features: dict[str, float | None] = _pair_history_features(
                pair_days, cutoff, company=company, track=track,
                by_company=by_company, by_track=by_track, by_company36=by_company36)
            last_day = max(pair_days) if pair_days else None
            features["rd_pair_inactive_months"] = (
                min(ENTRY_INACTIVE_MONTHS_CAP, (cutoff - last_day).days / MONTH_LENGTH_DAYS)
                if last_day else ENTRY_INACTIVE_MONTHS_CAP)
            features["rd_company_active_tracks_12m"] = float(len(company_tracks[company]))
            features["rd_company_active_tracks_delta"] = float(
                len(company_tracks[company]) - len(company_tracks_previous[company]))
            features["rd_track_active_companies_12m"] = float(len(track_companies[track]))
            features["rd_track_active_companies_delta"] = float(
                len(track_companies[track]) - len(track_companies_previous[track]))
            total24 = company_events24[company]
            features["rd_company_track_novelty_share"] = (
                novel_events24[company] / total24 if total24 else 0.0)
            features.update(financial.get((company, iso(cutoff)),
                                          {name: None for name in FINANCIAL_FEATURES}))
            targets = future_by_pair.get((company, track), [])
            label = int(bool(targets)) if mature else None
            if mature and targets:
                positives += 1
            examples.append({
                "example_id": sha1(
                    f"{ENTRY_DATASET_VERSION}|{iso(cutoff)}|{horizon_months}|{company}|{track}")[:32],
                "cutoff": iso(cutoff), "horizon_months": horizon_months,
                "company_key": company, "track_id": track, "features": features,
                "feature_available_at": iso(cutoff), "label": label,
                "first_target_event_date": iso(min(targets)) if targets else None,
                "target_event_count": len(targets) if mature else None,
                "maturity": "mature" if mature else "pending",
            })
        positives_by_origin[iso(cutoff)] = positives
    return {
        "dataset_version": ENTRY_DATASET_VERSION, "examples": examples,
        "cutoffs": used_cutoffs, "coverage_start": iso(coverage_start),
        "coverage_end": iso(coverage_end), "coverage_check": coverage,
        "dormancy_months": dormancy_months, "horizon_months": horizon_months,
        "event_count": len(events), "company_count": len(companies),
        "track_count": len({event["track_id"] for event in events}),
        "observed_pair_count": len(observed_pairs),
        "candidate_universe": "cross product of companies with >=1 material event by t and tracks observed by t",
        "base_features": list(BASE_FEATURES), "entry_features": list(ENTRY_FEATURES),
        "financial_features": list(FINANCIAL_FEATURES),
        "skipped_pending_examples": skipped_pending,
        "candidates_by_origin": candidates_by_origin,
        "positives_by_origin": positives_by_origin,
        "target": ("First material public FDA 510(k)/original-or-panel-track PMA activity in a technology "
                   "track the company had not touched for >= dormancy_months before the cutoff"),
        "left_censoring": ("The bulk window starts 2016-11-01; 'dormant' means no observed event inside the "
                           "observed window, not provably inactive before it. Event dates are decision dates "
                           "with availability estimated as decision_date+14d."),
        "timing": ("Features require event_date<=cutoff AND available_at<=cutoff; labels use future event_date; "
                   "financial facts require filed/available_at<=cutoff; dormancy uses exact calendar months"),
    }
