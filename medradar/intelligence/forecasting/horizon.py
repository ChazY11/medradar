"""Horizon Forecasting System: trained probabilities and future verification."""
from __future__ import annotations

import json
import math
from datetime import date
from typing import Any

from ...util import add_months, iso, parse_date, quarter_index, quarter_start, sha1, utc_now_iso
from ..features.research_features import build_examples
from ..models.baseline import LogisticBaseline
from ..storage import IntelligenceStore

MODEL_VERSION = "reverse-rd-logistic-v1"


def _train(examples: list[dict[str, Any]], features: list[str]) -> LogisticBaseline:
    mature = [row for row in examples if row["maturity"] == "mature" and row["label"] is not None]
    return LogisticBaseline(features).fit([row["features"] for row in mature], [int(row["label"]) for row in mature])


def create_forecasts(store: IntelligenceStore, *, base_features: list[str],
                     financial_features: list[str], coverage_end: str,
                     horizon_months: int = 12, top_n: int = 25) -> list[dict[str, Any]]:
    coverage = parse_date(coverage_end)
    if not coverage:
        raise ValueError("invalid coverage end")
    cutoff = quarter_start(quarter_index(coverage))
    current = build_examples(store, horizon_months=horizon_months, cutoffs=[cutoff], include_unmatured=True)
    candidates = [row for row in current["examples"] if row["maturity"] == "pending"]
    mature = [row for row in store.conn.execute(
        "SELECT * FROM forecast_examples WHERE maturity='mature' ORDER BY cutoff")]
    examples = []
    for row in mature:
        item = dict(row)
        item["features"] = json.loads(item["features"])
        examples.append(item)
    if not candidates or not examples:
        return []
    features = base_features + financial_features
    model = _train(examples, features)
    baseline = _train(examples, base_features)
    probabilities = model.predict_proba([row["features"] for row in candidates])
    baseline_probabilities = baseline.predict_proba([row["features"] for row in candidates])
    # Three expanding temporal fits measure model instability without treating
    # coefficient covariance as a causal confidence interval.
    origins = sorted({row["cutoff"] for row in examples})
    ensemble = []
    for count in range(max(2, len(origins) - 2), len(origins) + 1):
        subset = [row for row in examples if row["cutoff"] in origins[:count]]
        if len({row["label"] for row in subset}) == 2:
            ensemble.append(LogisticBaseline(features).fit(
                [row["features"] for row in subset], [int(row["label"]) for row in subset]))
    ensemble_predictions = [member.predict_proba([row["features"] for row in candidates]) for member in ensemble]
    created = utc_now_iso()
    horizon_end = add_months(cutoff, horizon_months)
    ranked = sorted(range(len(candidates)), key=lambda index: probabilities[index], reverse=True)[:top_n]
    results = []
    for index in ranked:
        row = candidates[index]
        company, track = row["company_key"], row["track_id"]
        forecast_id = sha1(f"{MODEL_VERSION}|{iso(cutoff)}|{horizon_months}|{company}|{track}")[:32]
        contributions = model.contributions(row["features"])
        supporting = [item for item in contributions if item["contribution"] > 0][:3]
        contradictory = [item for item in contributions if item["contribution"] < 0][:3]
        spread = [values[index] for values in ensemble_predictions]
        mean = sum(spread) / len(spread)
        std = math.sqrt(sum((value - mean) ** 2 for value in spread) / len(spread)) if spread else None
        record = {
            "forecast_id": forecast_id, "target_company": company, "technology_track": track,
            "forecast_creation_time": created, "historical_information_cutoff": iso(cutoff),
            "forecast_horizon_months": horizon_months, "horizon_end": iso(horizon_end),
            "model_version": MODEL_VERSION, "predicted_probability": probabilities[index],
            "uncertainty": {"temporal_ensemble_std": std, "ensemble_min": min(spread) if spread else None,
                            "ensemble_max": max(spread) if spread else None,
                            "note": "Model instability across expanding time windows; not a causal confidence interval."},
            "supporting_evidence": supporting, "contradictory_evidence": contradictory,
            "baseline_probability": baseline_probabilities[index],
            "verification_condition": {
                "table": "events", "company_key": company, "track_id": track,
                "kinds": ["510k", "pma"], "material_pma_only": True,
                "event_date_after": iso(cutoff), "event_date_on_or_before": iso(horizon_end),
                "minimum_coverage_end": iso(horizon_end),
            },
            "status": "pending",
        }
        store.upsert_forecast(record)
        results.append(record)
    return results


def verify_forecasts(store: IntelligenceStore, *, coverage_end: str,
                     as_of: str | date | None = None) -> dict[str, int]:
    coverage = parse_date(coverage_end)
    today = parse_date(as_of) or date.today()
    if not coverage:
        raise ValueError("invalid coverage end")
    verified = positives = pending = 0
    rows = [dict(row) for row in store.conn.execute("SELECT * FROM horizon_forecasts WHERE status='pending'")]
    for row in rows:
        condition = json.loads(row["verification_condition"])
        horizon_end = parse_date(row["horizon_end"])
        if not horizon_end or today <= horizon_end or coverage < horizon_end:
            pending += 1
            continue
        events = store.conn.execute(
            "SELECT event_id, kind, payload, event_date FROM events WHERE company_key=? AND track_id=? "
            "AND kind IN ('510k','pma') AND event_date>? AND event_date<=? ORDER BY event_date",
            (row["target_company"], row["technology_track"], condition["event_date_after"], row["horizon_end"]),
        ).fetchall()
        material = []
        for event in events:
            if event["kind"] == "510k":
                material.append(event)
            else:
                try:
                    payload = json.loads(event["payload"] or "{}")
                except (TypeError, ValueError):
                    payload = {}
                supplement = str(payload.get("supplement_number") or "").upper()
                if supplement in ("", "0", "S0") or "PANEL TRACK" in str(payload.get("supplement_type") or "").upper():
                    material.append(event)
        outcome = int(bool(material))
        verified_at = utc_now_iso()
        store.conn.execute(
            "UPDATE horizon_forecasts SET status='verified', outcome=?, verified_at=?, verification_event_id=? WHERE forecast_id=?",
            (outcome, verified_at, material[0]["event_id"] if material else None, row["forecast_id"]),
        )
        verified += 1
        positives += outcome
    store.conn.commit()
    return {"verified": verified, "positives": positives, "pending": pending}
