"""Cycle-2 panel construction: curated-parent panel (P1) and legal-entity panel (P2).

The scientific claim of cycle 2 is a comparison between two entity definitions on
an otherwise identical protocol. That claim is only trustworthy if this module
provably reproduces the frozen cycle-1 panel when given the frozen entity key.
The self-check in :func:`build_panel` enforces exactly that.

Design constraints (see research/CYCLE2_DESIGN.md and research/PREDICTION_PROTOCOL.md):

* Material-event rule, dormancy rule (36 calendar months), 12-month label and
  quarterly origins are imported from the frozen builder, never re-implemented.
* Features are computed by the frozen ``_pair_history_features`` helper so P1 and
  P2 cannot drift in what a feature means.
* No fuzzy entity matching: P2 groups events by the deterministic normalised
  applicant string from ``medradar.intelligence.universe``.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from medradar.util import add_months, iso, parse_date, sha1
from medradar.intelligence.features.research_features import (
    BASE_FEATURES,
    ENTRY_FEATURES,
    ENTRY_INACTIVE_MONTHS_CAP,
    MONTH_LENGTH_DAYS,
    _material_pma,
    _pair_history_features,
    entry_origins,
)

DORMANCY_MONTHS = 36
HORIZON_MONTHS = 12
P2_DATASET_VERSION = "first_entry_entity_v1"
P1_DATASET_VERSION = "first_entry_v1"  # frozen identifier; must reproduce exactly


# --------------------------------------------------------------------- loading
def load_regulatory_events(db_path: Path) -> list[dict[str, Any]]:
    """Load every 510(k)/PMA row with the fields the panel needs.

    Read-only. No filtering beyond kind: entity assignment happens later so the
    same load feeds both panels and the two panels cannot see different rows.
    """
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT event_id, kind, event_date, available_at, company_key, "
            "track_id, applicant_raw, source, payload "
            "FROM events WHERE kind IN ('510k','pma')"
        ).fetchall()
    finally:
        con.close()
    events: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        day = parse_date(item.get("event_date"))
        available = parse_date(str(item.get("available_at") or "")[:10]) or day
        if not day or not available:
            continue
        if item["kind"] == "pma" and not _material_pma(item.get("payload") or ""):
            continue
        item["day"] = day
        item["available"] = available
        events.append(item)
    events.sort(key=lambda event: (event["day"], event["event_id"]))
    return events


def assign_entity(events: Iterable[Mapping[str, Any]], normaliser: Callable[[str | None], str],
                  keyer: Callable[[str], str] | None = None) -> list[dict[str, Any]]:
    """Return copies of ``events`` with a deterministic ``entity`` field added."""
    out: list[dict[str, Any]] = []
    for event in events:
        normalised = normaliser(event.get("applicant_raw"))
        entity = keyer(normalised) if keyer and normalised else normalised
        item = dict(event)
        item["entity"] = entity
        out.append(item)
    return out


# --------------------------------------------------------------------- panels
def build_entry_panel(
    events: list[dict[str, Any]],
    *,
    entity_field: str,
    dataset_version: str,
    coverage_end_reference: str | None = None,
    coverage_end_tolerance_days: int = 45,
) -> dict[str, Any]:
    """Dormant -> active entry examples grouped by ``entity_field``.

    This is a field-parametric reimplementation of the frozen
    ``build_entry_examples`` loop. Every rule is imported from the frozen module;
    only the grouping key is variable. :func:`self_check_p1` proves that when
    ``entity_field='company_key'`` the output reproduces the frozen counts.
    """
    def usable(event: Mapping[str, Any]) -> bool:
        return bool(event.get(entity_field)) and bool(event.get("track_id"))

    panel_events = [event for event in events if usable(event)]
    if not panel_events:
        raise ValueError(f"no events usable for entity_field={entity_field}")
    coverage_start = min(event["day"] for event in panel_events)
    coverage_end = max(event["day"] for event in panel_events)
    coverage_check: dict[str, Any] = {
        "expected_coverage_end": coverage_end_reference,
        "observed_coverage_end": iso(coverage_end),
        "tolerance_days": coverage_end_tolerance_days,
        "checked": coverage_end_reference is not None,
        "ok": True,
    }
    if coverage_end_reference is not None:
        reference = parse_date(coverage_end_reference)
        delta = abs((coverage_end - reference).days) if reference else None
        coverage_check["delta_days"] = delta
        coverage_check["ok"] = delta is not None and delta <= coverage_end_tolerance_days
        if not coverage_check["ok"]:
            raise ValueError(
                f"coverage ends {iso(coverage_end)}, expected {coverage_end_reference} "
                f"+/-{coverage_end_tolerance_days}d; refusing to build labels outside coverage")

    cutoff_days = entry_origins(panel_events, dormancy_months=DORMANCY_MONTHS,
                                horizon_months=HORIZON_MONTHS,
                                coverage_start=coverage_start, coverage_end=coverage_end)

    examples: list[dict[str, Any]] = []
    candidates_by_origin: dict[str, int] = {}
    positives_by_origin: dict[str, int] = {}
    used_cutoffs: list[str] = []
    skipped_pending = 0
    for cutoff in cutoff_days:
        horizon_end = add_months(cutoff, HORIZON_MONTHS)
        mature = horizon_end <= coverage_end
        history = [event for event in panel_events
                   if event["day"] <= cutoff and event["available"] <= cutoff]
        if not history:
            continue
        active_entities = sorted({event[entity_field] for event in history})
        tracks = sorted({event["track_id"] for event in history})
        future = [event for event in panel_events if cutoff < event["day"] <= horizon_end]
        day_12 = cutoff - timedelta(days=365)
        day_24 = cutoff - timedelta(days=730)
        day_36 = cutoff - timedelta(days=1095)
        dormancy_cut = add_months(cutoff, -DORMANCY_MONTHS)
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
            entity, track, day = event[entity_field], event["track_id"], event["day"]
            by_pair[(entity, track)].append(day)
            if day_12 < day <= cutoff:
                by_company[entity] += 1
                by_track[track] += 1
                company_tracks[entity].add(track)
                track_companies[track].add(entity)
            elif day_24 < day <= day_12:
                by_company_previous[entity] += 1
                by_track_previous[track] += 1
                company_tracks_previous[entity].add(track)
                track_companies_previous[track].add(entity)
            if day_36 < day <= cutoff:
                by_company36[entity] += 1
            if day_24 < day <= cutoff:
                company_events24[entity] += 1
        pair_first = {pair: min(days) for pair, days in by_pair.items()}
        novel_events24: Counter[str] = Counter()
        for event in history:
            if day_24 < event["day"] <= cutoff:
                pair = (event[entity_field], event["track_id"])
                if pair_first[pair] > day_24:
                    novel_events24[event[entity_field]] += 1
        future_by_pair: dict[tuple[str, str], list[date]] = defaultdict(list)
        for event in future:
            future_by_pair[(event[entity_field], event["track_id"])].append(event["day"])

        candidates = [
            (entity, track)
            for entity in active_entities
            for track in tracks
            if not by_pair.get((entity, track)) or max(by_pair[(entity, track)]) <= dormancy_cut
        ]
        candidates_by_origin[iso(cutoff)] = len(candidates)
        if not mature:
            skipped_pending += len(candidates)
            continue
        used_cutoffs.append(iso(cutoff))
        positives = 0
        for entity, track in candidates:
            pair_days = by_pair.get((entity, track), [])
            features: dict[str, float | None] = _pair_history_features(
                pair_days, cutoff, company=entity, track=track,
                by_company=by_company, by_track=by_track, by_company36=by_company36)
            last_day = max(pair_days) if pair_days else None
            features["rd_pair_inactive_months"] = (
                min(ENTRY_INACTIVE_MONTHS_CAP, (cutoff - last_day).days / MONTH_LENGTH_DAYS)
                if last_day else ENTRY_INACTIVE_MONTHS_CAP)
            features["rd_company_active_tracks_12m"] = float(len(company_tracks[entity]))
            features["rd_company_active_tracks_delta"] = float(
                len(company_tracks[entity]) - len(company_tracks_previous[entity]))
            features["rd_track_active_companies_12m"] = float(len(track_companies[track]))
            features["rd_track_active_companies_delta"] = float(
                len(track_companies[track]) - len(track_companies_previous[track]))
            total24 = company_events24[entity]
            features["rd_company_track_novelty_share"] = (
                novel_events24[entity] / total24 if total24 else 0.0)
            targets = future_by_pair.get((entity, track), [])
            if targets:
                positives += 1
            examples.append({
                "example_id": sha1(
                    f"{dataset_version}|{iso(cutoff)}|{HORIZON_MONTHS}|{entity}|{track}")[:32],
                "cutoff": iso(cutoff), "horizon_months": HORIZON_MONTHS,
                "company_key": entity, "track_id": track,
                "entity_field": entity_field,
                "features": features,
                "feature_available_at": iso(cutoff),
                "label": int(bool(targets)),
                "first_target_event_date": iso(min(targets)) if targets else None,
                "target_event_count": len(targets),
                "maturity": "mature",
            })
        positives_by_origin[iso(cutoff)] = positives

    return {
        "dataset_version": dataset_version,
        "entity_field": entity_field,
        "examples": examples,
        "cutoffs": used_cutoffs,
        "coverage_start": iso(coverage_start),
        "coverage_end": iso(coverage_end),
        "coverage_check": coverage_check,
        "dormancy_months": DORMANCY_MONTHS,
        "horizon_months": HORIZON_MONTHS,
        "event_count": len(panel_events),
        "entity_count": len({event[entity_field] for event in panel_events}),
        "track_count": len({event["track_id"] for event in panel_events}),
        "observed_pair_count": len({(event[entity_field], event["track_id"])
                                    for event in panel_events}),
        "base_features": list(BASE_FEATURES),
        "entry_features": list(ENTRY_FEATURES),
        "skipped_pending_examples": skipped_pending,
        "candidates_by_origin": candidates_by_origin,
        "positives_by_origin": positives_by_origin,
        "n_examples": len(examples),
        "n_positives": sum(int(row["label"]) for row in examples),
    }


# ------------------------------------------------------------------ self-check
def self_check_p1(panel: dict[str, Any], frozen: dict[str, Any]) -> dict[str, Any]:
    """Prove the parametric builder reproduces the frozen cycle-1 panel.

    Compares example count, positive count, origins, and the per-origin
    candidate/positive counts. A mismatch means the harness is wrong and no P2
    result may be reported (see CYCLE2_DESIGN.md, falsification section).
    """
    frozen_examples = frozen["examples"]
    mine = panel["examples"]
    checks: list[dict[str, Any]] = []

    def check(name: str, expected: Any, observed: Any) -> None:
        checks.append({"check": name, "expected": expected, "observed": observed,
                       "ok": expected == observed})

    check("n_examples", len(frozen_examples), len(mine))
    check("n_positives",
          sum(int(row["label"]) for row in frozen_examples),
          sum(int(row["label"]) for row in mine))
    check("origins", frozen["cutoffs"], panel["cutoffs"])
    check("candidates_by_origin", frozen["candidates_by_origin"], panel["candidates_by_origin"])
    check("positives_by_origin", frozen["positives_by_origin"], panel["positives_by_origin"])
    check("coverage_start", frozen["coverage_start"], panel["coverage_start"])
    check("coverage_end", frozen["coverage_end"], panel["coverage_end"])

    frozen_by_id = {row["example_id"]: row for row in frozen_examples}
    mismatched = []
    for row in mine:
        other = frozen_by_id.get(row["example_id"])
        if other is None:
            mismatched.append({"example_id": row["example_id"], "issue": "missing in frozen"})
            continue
        for key, value in row["features"].items():
            if other["features"].get(key) != value:
                mismatched.append({"example_id": row["example_id"], "feature": key,
                                   "mine": value, "frozen": other["features"].get(key)})
                break
    checks.append({"check": "feature_mismatches", "expected": 0, "observed": len(mismatched),
                   "ok": not mismatched})
    return {"ok": all(entry["ok"] for entry in checks), "checks": checks,
            "examples_compared": min(len(mine), len(frozen_examples)),
            "mismatch_sample": mismatched[:5]}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
