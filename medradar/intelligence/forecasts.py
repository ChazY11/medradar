"""Frozen prospective forecasts: register predictions now, score them when the data matures.

The programme's rule is that a prediction not written down before the outcome is not a test. This module makes
registration and scoring mechanical:

  * a forecast is keyed by (company, track, alert quarter) and states **one probability** — that activity in the
    outcome window stays at or above the alert-time baseline;
  * the outcome window is fixed at the four quarters after the two-quarter confirmation window (alert at *q* →
    outcome covers *q+3 … q+6*, maturing when data through *q+6* exists);
  * the probabilities are not invented: they are the end-to-end pipeline rates measured in D-065
    (promoted alerts persisted 0.800, unpromoted 0.667), which is why the two groups differ so little — that is
    the honest state of knowledge and it is what the forecast should encode.

`score()` computes Brier, log loss and accuracy over resolved forecasts only, and reports the pending count so a
partially matured set can never be summarised as if complete.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

FORECAST_SCHEMA = "forecast_set_v1"
CONFIRMATION_QUARTERS = 2
OUTCOME_QUARTERS = 4
BASELINE_QUARTERS = 8

#: end-to-end pipeline persistence rates by promotion decision (D-065); these are measurements, not preferences
PROBABILITY_BY_DECISION = {"promoted": 0.800, "not_promoted": 0.667}


def quarter_to_index(label: str) -> int:
    """'2025-Q3' -> absolute quarter index."""
    text = str(label).strip().upper()
    if "-Q" not in text:
        raise ValueError(f"not a quarter label: {label!r}")
    year_text, quarter_text = text.split("-Q", 1)
    year, quarter = int(year_text), int(quarter_text)
    if not 1 <= quarter <= 4:
        raise ValueError(f"quarter out of range: {label!r}")
    return year * 4 + (quarter - 1)


def index_to_quarter(index: int) -> str:
    year, quarter = divmod(index, 4)
    return f"{year:04d}-Q{quarter + 1}"


def windows(alert_quarter: str) -> dict[str, str]:
    """Fixed windows relative to the alert quarter."""
    origin = quarter_to_index(alert_quarter)
    return {
        "confirmation": f"{index_to_quarter(origin + 1)}..{index_to_quarter(origin + CONFIRMATION_QUARTERS)}",
        "outcome": f"{index_to_quarter(origin + CONFIRMATION_QUARTERS + 1)}.."
                   f"{index_to_quarter(origin + CONFIRMATION_QUARTERS + OUTCOME_QUARTERS)}",
        "matures_when_data_through": index_to_quarter(origin + CONFIRMATION_QUARTERS + OUTCOME_QUARTERS),
    }


def build_forecast(*, company: str, track: str, alert_quarter: str, promoted: bool,
                   policy_version: str, shape: str) -> dict[str, Any]:
    decision = "promoted" if promoted else "not_promoted"
    return {
        "id": f"{company}|{track}|{alert_quarter}",
        "company": company,
        "track": track,
        "alert_quarter": alert_quarter,
        "decision": decision,
        "shape": shape,
        "policy_version": policy_version,
        "probability_persisted": PROBABILITY_BY_DECISION[decision],
        "question": "mean quarterly activity in the outcome window is at or above the alert-time baseline",
        "windows": windows(alert_quarter),
        "source": "experiments/b027/snapshots/2026-11-03-policy-v2",
    }


def validate_forecast_set(payload: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    if payload.get("schema") != FORECAST_SCHEMA:
        problems.append(f"unexpected schema {payload.get('schema')!r}")
    records = payload.get("forecasts") or []
    if not records:
        problems.append("no forecasts registered")
    seen = set()
    for record in records:
        forecast_id = record.get("id")
        if forecast_id in seen:
            problems.append(f"duplicate forecast id {forecast_id!r}")
        seen.add(forecast_id)
        probability = record.get("probability_persisted")
        if not isinstance(probability, (int, float)) or not 0.0 <= probability <= 1.0:
            problems.append(f"{forecast_id}: probability out of range")
        if not record.get("windows", {}).get("matures_when_data_through"):
            problems.append(f"{forecast_id}: no maturation quarter")
    return problems


def score(forecasts: Sequence[Mapping[str, Any]],
          observed: Mapping[str, bool]) -> dict[str, Any]:
    """Score only the forecasts whose outcome is known; everything else is reported as pending."""
    resolved, pending = [], []
    for record in forecasts:
        forecast_id = record["id"]
        if forecast_id not in observed:
            pending.append(forecast_id)
            continue
        outcome = bool(observed[forecast_id])
        probability = float(record["probability_persisted"])
        resolved.append({
            "id": forecast_id,
            "decision": record.get("decision"),
            "probability": probability,
            "outcome": outcome,
            "brier": (probability - (1.0 if outcome else 0.0)) ** 2,
            "log_loss": -math.log(probability if outcome else 1.0 - probability),
            "correct": (probability >= 0.5) == outcome,
        })
    if not resolved:
        return {"resolved": 0, "pending": len(pending), "brier": None, "log_loss": None,
                "accuracy": None, "by_decision": {}, "status": "nothing matured yet"}
    def mean(values: Iterable[float]) -> float | None:
        values = list(values)
        return sum(values) / len(values) if values else None
    by_decision: dict[str, dict[str, Any]] = {}
    for decision in sorted({row["decision"] for row in resolved}):
        rows = [row for row in resolved if row["decision"] == decision]
        by_decision[decision] = {
            "n": len(rows),
            "mean_probability": mean(row["probability"] for row in rows),
            "mean_outcome": mean(1.0 if row["outcome"] else 0.0 for row in rows),
            "brier": mean(row["brier"] for row in rows),
        }
    return {
        "resolved": len(resolved),
        "pending": len(pending),
        "brier": mean(row["brier"] for row in resolved),
        "log_loss": mean(row["log_loss"] for row in resolved),
        "accuracy": mean(1.0 if row["correct"] else 0.0 for row in resolved),
        "by_decision": by_decision,
        "status": "partially matured" if pending else "fully matured",
    }
