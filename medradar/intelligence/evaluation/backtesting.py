"""Expanding-window, rolling-origin evaluation with one final time holdout."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from ...util import parse_date
from ..models.baseline import LogisticBaseline
from .metrics import evaluate, stability


def _lead(row: dict[str, Any]) -> int | None:
    if not row.get("label") or not row.get("first_target_event_date"):
        return None
    start, end = parse_date(row["cutoff"]), parse_date(row["first_target_event_date"])
    return (end - start).days if start and end else None


def _metrics(rows: list[dict[str, Any]], probabilities: list[float]) -> dict[str, Any]:
    return evaluate([int(row["label"]) for row in rows], probabilities,
                    lead_times=[_lead(row) for row in rows])


def _subgroups(rows: list[dict[str, Any]], probabilities: list[float], field: str,
               min_n: int = 10) -> dict[str, Any]:
    result = {}
    for value in sorted({row.get(field) for row in rows if row.get(field) is not None}):
        members = [(row, probability) for row, probability in zip(rows, probabilities) if row.get(field) == value]
        if len(members) < min_n:
            continue
        result[value] = _metrics([row for row, _ in members], [probability for _, probability in members])
    return result


def run_backtest(examples: list[dict[str, Any]], base_features: list[str],
                 financial_features: list[str], *, min_train_origins: int = 3,
                 data_provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    mature = [row for row in examples if row["maturity"] == "mature" and row["label"] is not None]
    origins = sorted({row["cutoff"] for row in mature})
    if len(origins) < min_train_origins + 2:
        raise ValueError(f"Need at least {min_train_origins + 2} mature origins, got {len(origins)}")
    holdout = origins[-1]
    specifications = [
        ("rd_only", "A: R&D history only", base_features),
        ("rd_financial", "B: R&D + consolidated SEC financials", base_features + financial_features),
    ]
    report: dict[str, Any] = {
        "experiment": "reverse_rd_v1", "target_horizon_months": 12,
        "evaluation": "expanding-window rolling-origin; final chronological origin untouched until model/config freeze",
        "min_train_origins": min_train_origins, "origins": origins, "holdout": holdout,
        "models": [], "data_provenance": data_provenance or {},
        "constraints": [
            "No random temporal split.", "Identical rows, algorithm and hyperparameters across ablations.",
            "Current-snapshot procurement is excluded from historical gain claims.",
            "Consolidated company revenue is not product- or segment-level device sales.",
        ],
    }
    for model_name, description, features in specifications:
        origin_rows = []
        development_rows: list[dict[str, Any]] = []
        development_probabilities: list[float] = []
        for index in range(min_train_origins, len(origins)):
            cutoff = origins[index]
            train_origins = set(origins[:index])
            train = [row for row in mature if row["cutoff"] in train_origins]
            test = [row for row in mature if row["cutoff"] == cutoff]
            if not train or not test or len({row["label"] for row in train}) < 2:
                continue
            model = LogisticBaseline(features).fit([row["features"] for row in train], [int(row["label"]) for row in train])
            probabilities = model.predict_proba([row["features"] for row in test])
            metrics = _metrics(test, probabilities)
            origin_rows.append({"cutoff": cutoff, "is_holdout": cutoff == holdout, **metrics})
            if cutoff != holdout:
                development_rows.extend(test)
                development_probabilities.extend(probabilities)
            if cutoff == holdout:
                holdout_metrics = metrics
                holdout_rows, holdout_probabilities = test, probabilities
        report["models"].append({
            "name": model_name, "description": description, "features": features,
            "development_metrics": _metrics(development_rows, development_probabilities),
            "holdout_metrics": holdout_metrics,
            "holdout_subgroups": {
                "company": _subgroups(holdout_rows, holdout_probabilities, "company_key"),
                "track": _subgroups(holdout_rows, holdout_probabilities, "track_id"),
            },
            "origin_metrics": origin_rows, "forecast_horizon_stability": stability(origin_rows[:-1]),
        })
    if len(report["models"]) == 2:
        first, second = report["models"]
        report["financial_marginal_value"] = {
            metric: ((second["holdout_metrics"].get(metric) - first["holdout_metrics"].get(metric))
                     if first["holdout_metrics"].get(metric) is not None and second["holdout_metrics"].get(metric) is not None else None)
            for metric in ("pr_auc", "brier", "ece", "false_positive_rate", "precision_at_k")
        }
        subgroup_delta = {}
        for field in ("company", "track"):
            deltas = []
            first_groups = first["holdout_subgroups"][field]
            second_groups = second["holdout_subgroups"][field]
            for key in sorted(set(first_groups) & set(second_groups)):
                old, new = first_groups[key].get("pr_auc"), second_groups[key].get("pr_auc")
                if old is not None and new is not None:
                    deltas.append({"id": key, "n": first_groups[key]["n"], "pr_auc_delta": new - old})
            subgroup_delta[field] = {
                "largest_gains": sorted(deltas, key=lambda row: row["pr_auc_delta"], reverse=True)[:5],
                "largest_losses": sorted(deltas, key=lambda row: row["pr_auc_delta"])[:5],
                "minimum_n": 10,
            }
        report["financial_marginal_value"]["subgroups"] = subgroup_delta
        report["financial_marginal_value"]["interpretation"] = "Positive PR-AUC/Precision@K and negative Brier/ECE are improvements; one holdout is not proof of a stable causal effect."
    return report
