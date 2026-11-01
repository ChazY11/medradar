"""Probability, ranking, error and lead-time metrics with explicit empty cases."""
from __future__ import annotations

import math
from datetime import date
from typing import Any


def pr_auc(labels: list[int], probabilities: list[float]) -> float | None:
    positives = sum(labels)
    if not positives or positives == len(labels):
        return None
    ordered = sorted(zip(probabilities, labels), key=lambda pair: pair[0], reverse=True)
    tp = fp = 0
    previous_recall = 0.0
    area = 0.0
    index = 0
    # Evaluate a tied score block as one threshold; row order must never change
    # the metric or reward an arbitrary sorting of equal predictions.
    while index < len(ordered):
        score = ordered[index][0]
        while index < len(ordered) and ordered[index][0] == score:
            if ordered[index][1]:
                tp += 1
            else:
                fp += 1
            index += 1
        recall = tp / positives
        precision = tp / max(tp + fp, 1)
        area += (recall - previous_recall) * precision
        previous_recall = recall
    return area


def brier(labels: list[int], probabilities: list[float]) -> float | None:
    return sum((p - y) ** 2 for p, y in zip(probabilities, labels)) / len(labels) if labels else None


def ece(labels: list[int], probabilities: list[float], bins: int = 10) -> float | None:
    if not labels:
        return None
    error = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [(p, y) for p, y in zip(probabilities, labels) if low <= p < high or (index == bins - 1 and p == 1)]
        if members:
            confidence = sum(p for p, _ in members) / len(members)
            accuracy = sum(y for _, y in members) / len(members)
            error += len(members) / len(labels) * abs(confidence - accuracy)
    return error


def evaluate(labels: list[int], probabilities: list[float], *, lead_times: list[int | None] | None = None,
             threshold: float = 0.5, k_fraction: float = 0.1) -> dict[str, Any]:
    if not labels or len(labels) != len(probabilities):
        return {"n": len(labels), "positives": sum(labels), "pr_auc": None, "brier": None,
                "ece": None, "false_positive_rate": None, "precision_at_k": None,
                "mean_lead_time_days": None, "k": 0}
    negatives = len(labels) - sum(labels)
    false_positives = sum(1 for y, p in zip(labels, probabilities) if not y and p >= threshold)
    k = max(1, math.ceil(len(labels) * k_fraction))
    top = sorted(zip(probabilities, labels), key=lambda pair: pair[0], reverse=True)[:k]
    observed_leads = [value for value in (lead_times or []) if value is not None]
    return {
        "n": len(labels), "positives": sum(labels), "prevalence": sum(labels) / len(labels),
        "pr_auc": pr_auc(labels, probabilities), "brier": brier(labels, probabilities),
        "ece": ece(labels, probabilities),
        "false_positive_rate": false_positives / negatives if negatives else None,
        "precision_at_k": sum(label for _, label in top) / k,
        "k": k,
        "mean_lead_time_days": sum(observed_leads) / len(observed_leads) if observed_leads else None,
        "lead_time_n": len(observed_leads), "threshold": threshold,
    }


def stability(origin_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row["pr_auc"] for row in origin_metrics if row.get("pr_auc") is not None]
    if not values:
        return {"origins": 0, "pr_auc_mean": None, "pr_auc_std": None, "pr_auc_min": None, "pr_auc_max": None}
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {"origins": len(values), "pr_auc_mean": mean, "pr_auc_std": math.sqrt(variance),
            "pr_auc_min": min(values), "pr_auc_max": max(values)}
