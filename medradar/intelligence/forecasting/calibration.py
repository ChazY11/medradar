"""Future forecast calibration from verified registry rows."""
from __future__ import annotations

import json
from typing import Any

from ..evaluation.metrics import brier, ece, pr_auc


def calibration_report(store: Any) -> dict[str, Any]:
    rows = [dict(row) for row in store.conn.execute(
        "SELECT predicted_probability, outcome, model_version FROM horizon_forecasts WHERE status='verified'")]
    labels = [int(row["outcome"]) for row in rows]
    probabilities = [float(row["predicted_probability"]) for row in rows]
    return {
        "verified_forecasts": len(rows),
        "pr_auc": pr_auc(labels, probabilities),
        "brier": brier(labels, probabilities),
        "ece": ece(labels, probabilities),
        "status": "insufficient_verified_forecasts" if len(rows) < 20 else "evaluated",
        "note": "No recalibration is fitted before a sufficient verified sample exists.",
    }
