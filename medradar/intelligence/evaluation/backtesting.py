"""Expanding-window, rolling-origin evaluation with one final time holdout.

Training labels are purged by default: an example may only train an origin when
its whole label window has closed before the test window opens. The old
(unpurged) specification is retained as an explicitly labelled diagnostic so the
size of the previous bias is measured instead of hidden.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Iterable

from ...util import add_months, parse_date
from ..models.baseline import LogisticBaseline
from .metrics import evaluate, paired_bootstrap_delta_ap, pr_auc, stability

DEFAULT_HORIZON_MONTHS = 12
PURGE_RULE = (
    "A training example may only be used at origin t when its label window has "
    "matured: cutoff + horizon_months <= t. Otherwise the label encodes events "
    "inside (t, t+horizon], i.e. the test window."
)


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


def label_window_end(cutoff: Any, horizon_months: int = DEFAULT_HORIZON_MONTHS):
    """End of the label window opened at ``cutoff`` (exclusive upper bound)."""
    day = parse_date(cutoff)
    return add_months(day, horizon_months) if day else None


def matured_by(cutoff: Any, origin: Any, horizon_months: int = DEFAULT_HORIZON_MONTHS) -> bool:
    """True when a label opened at ``cutoff`` is fully observed by ``origin``."""
    end = label_window_end(cutoff, horizon_months)
    day = parse_date(origin)
    return bool(end and day and end <= day)


def eligible_training_rows(examples: Iterable[dict[str, Any]], origin: Any, *,
                           purge: bool = True,
                           horizon_months: int = DEFAULT_HORIZON_MONTHS) -> list[dict[str, Any]]:
    """Rows a model may train on at ``origin``.

    With ``purge=True`` (default) only rows whose label window matured by the
    origin are admitted. ``purge=False`` reproduces the previous, biased
    specification for the diagnostic block only.
    """
    origin_day = parse_date(origin)
    if origin_day is None:
        return []
    rows = []
    for row in examples:
        day = parse_date(row.get("cutoff"))
        if day is None or day >= origin_day:
            continue
        if purge and not matured_by(day, origin_day, horizon_months):
            continue
        rows.append(row)
    return rows


def _rate(key_fn: Callable[[dict[str, Any]], Any], training: list[dict[str, Any]],
          test: list[dict[str, Any]], prevalence: float) -> tuple[list[float], int]:
    history: dict[Any, list[int]] = defaultdict(list)
    for row in training:
        history[key_fn(row)].append(int(row["label"]))
    probabilities = []
    seen = 0
    for row in test:
        key = key_fn(row)
        values = history.get(key)
        if values:
            seen += 1
            probabilities.append(sum(values) / len(values))
        else:
            probabilities.append(prevalence)
    return probabilities, seen


def _persistence_baselines(mature: list[dict[str, Any]], origin: str, *,
                           purge: bool = True,
                           horizon_months: int = DEFAULT_HORIZON_MONTHS) -> dict[str, Any]:
    """No-feature, point-in-time base-rate predictors on the same holdout rows."""
    training = eligible_training_rows(mature, origin, purge=purge, horizon_months=horizon_months)
    test = [row for row in mature if row["cutoff"] == origin]
    if not training or not test:
        return {"holdout": origin, "training_rows": len(training), "holdout_rows": len(test),
                "predictors": {}, "pair_coverage": None}
    prevalence = sum(int(row["label"]) for row in training) / len(training)
    specifications = [
        ("constant_training_prevalence", lambda row: None,
         "Same probability for every holdout row: positive rate over eligible training origins."),
        ("company_base_rate", lambda row: row.get("company_key"),
         "Positive rate of the company over eligible training origins; training prevalence for unseen companies."),
        ("track_base_rate", lambda row: row.get("track_id"),
         "Positive rate of the technology track over eligible training origins; training prevalence for unseen tracks."),
        ("pair_base_rate", lambda row: (row.get("company_key"), row.get("track_id")),
         "Positive rate of the exact company-track pair over eligible training origins; training prevalence for "
         "pairs without matured history. This one-parameter persistence benchmark is the honest comparator for "
         "the headline PR-AUC."),
    ]
    predictors: dict[str, Any] = {}
    for name, key_fn, description in specifications:
        probabilities, seen = _rate(key_fn, training, test, prevalence)
        entry = {"description": description, "training_rows_seen": seen,
                 "unseen_fallback": "constant training prevalence", **_metrics(test, probabilities)}
        if name == "constant_training_prevalence":
            entry["training_rows_seen"] = len(test)
            entry["unseen_fallback"] = "not applicable (single constant)"
        predictors[name] = entry
    pair_coverage = (predictors["pair_base_rate"]["training_rows_seen"] / len(test)) if test else None
    return {
        "holdout": origin,
        "training_rows": len(training),
        "training_origins": sorted({row["cutoff"] for row in training}),
        "holdout_rows": len(test),
        "training_prevalence": prevalence,
        "pair_base_rate_coverage": pair_coverage,
        "predictors": predictors,
        "lead_times": "Same target lead times as the model metrics, so only the probability columns differ.",
    }


def _evaluate_specs(mature: list[dict[str, Any]], origins: list[str],
                    specifications: list[tuple[str, str, list[str]]], *,
                    min_train_origins: int, purge: bool,
                    horizon_months: int) -> tuple[list[dict[str, Any]], dict[str, tuple[list[dict[str, Any]], list[float]]]]:
    holdout = origins[-1]
    models: list[dict[str, Any]] = []
    holdout_predictions: dict[str, tuple[list[dict[str, Any]], list[float]]] = {}
    for model_name, description, features in specifications:
        origin_rows: list[dict[str, Any]] = []
        development_rows: list[dict[str, Any]] = []
        development_probabilities: list[float] = []
        holdout_metrics: dict[str, Any] | None = None
        holdout_rows: list[dict[str, Any]] = []
        holdout_probabilities: list[float] = []
        for index in range(min_train_origins, len(origins)):
            cutoff = origins[index]
            train = eligible_training_rows(mature, cutoff, purge=purge, horizon_months=horizon_months)
            test = [row for row in mature if row["cutoff"] == cutoff]
            if not train or not test or len({row["label"] for row in train}) < 2:
                continue
            model = LogisticBaseline(features).fit(
                [row["features"] for row in train], [int(row["label"]) for row in train])
            probabilities = model.predict_proba([row["features"] for row in test])
            metrics = _metrics(test, probabilities)
            origin_rows.append({"cutoff": cutoff, "is_holdout": cutoff == holdout, **metrics})
            if cutoff != holdout:
                development_rows.extend(test)
                development_probabilities.extend(probabilities)
            else:
                holdout_metrics = metrics
                holdout_rows, holdout_probabilities = test, probabilities
        holdout_predictions[model_name] = (holdout_rows, holdout_probabilities)
        models.append({
            "name": model_name, "description": description, "features": features,
            "training_label_policy": "matured_by_origin" if purge else "leaky_overlap_diagnostic_only",
            "development_metrics": _metrics(development_rows, development_probabilities),
            "holdout_metrics": holdout_metrics,
            "holdout_subgroups": {
                "company": _subgroups(holdout_rows, holdout_probabilities, "company_key"),
                "track": _subgroups(holdout_rows, holdout_probabilities, "track_id"),
            },
            "origin_metrics": origin_rows, "forecast_horizon_stability": stability(origin_rows[:-1]),
        })
    return models, holdout_predictions


def run_backtest(examples: list[dict[str, Any]], base_features: list[str],
                 financial_features: list[str], *, min_train_origins: int = 3,
                 horizon_months: int = DEFAULT_HORIZON_MONTHS,
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
    models, predictions = _evaluate_specs(
        mature, origins, specifications, min_train_origins=min_train_origins,
        purge=True, horizon_months=horizon_months)
    report: dict[str, Any] = {
        "experiment": "reverse_rd_v1", "target_horizon_months": horizon_months,
        "evaluation": (
            "expanding-window rolling-origin with matured-label purge; final chronological origin is the holdout. "
            "Training at origin t only uses examples whose label window closed at or before t."),
        "purge": {
            "default": True,
            "rule": PURGE_RULE,
            "horizon_months": horizon_months,
            "description": (
                "Purged/embargoed rolling origin. The league result below is the purged one; the old "
                "overlapping-label variant is reported separately under leaky_labels_diagnostic."),
            "training_rows_by_origin": [
                {"cutoff": cutoff,
                 "purged_training_rows": len(eligible_training_rows(
                     mature, cutoff, purge=True, horizon_months=horizon_months)),
                 "leaky_training_rows": len(eligible_training_rows(
                     mature, cutoff, purge=False, horizon_months=horizon_months))}
                for cutoff in origins[min_train_origins:]
            ],
        },
        "min_train_origins": min_train_origins, "origins": origins, "holdout": holdout,
        "models": models, "data_provenance": data_provenance or {},
        "constraints": [
            "No random temporal split.", "Identical rows, algorithm and hyperparameters across ablations.",
            "Training labels must mature before the evaluation origin (purge/embargo); the unpurged variant is "
            "diagnostic only.",
            "Current-snapshot procurement is excluded from historical gain claims.",
            "Consolidated company revenue is not product- or segment-level device sales.",
        ],
    }
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
        report["financial_marginal_value"]["interpretation"] = (
            "Positive PR-AUC/Precision@K and negative Brier/ECE are improvements; one holdout is not proof of a "
            "stable causal effect.")

    # ------------------------------------------------------------------ F2 baselines
    baselines = _persistence_baselines(mature, holdout, purge=True, horizon_months=horizon_months)
    report["baselines"] = baselines
    holdout_labels = [int(row["label"]) for row in predictions[report["models"][0]["name"]][0]]
    pair_predictions = _rate(
        lambda row: (row.get("company_key"), row.get("track_id")),
        eligible_training_rows(mature, holdout, purge=True, horizon_months=horizon_months),
        [row for row in mature if row["cutoff"] == holdout],
        baselines.get("training_prevalence", 0.0))[0]
    constant = baselines.get("predictors", {}).get("constant_training_prevalence", {}).get("pr_auc")
    pair_ap = baselines.get("predictors", {}).get("pair_base_rate", {}).get("pr_auc")
    comparison: dict[str, Any] = {
        "comparison": (
            "Paired bootstrap (rows resampled with replacement, identical rows for both predictors) of "
            "PR-AUC(model) - PR-AUC(pair_base_rate) on the untouched holdout."),
        "resamples": 2000, "seed": 7, "confidence_level": 0.95,
        "pair_baseline_pr_auc": pair_ap,
        "model_scores": {},
        "interpretation": (
            "If the interval includes zero, the ten R&D features add no statistically detectable ranking value "
            "beyond stable per-pair activity persistence on this single holdout."),
    }
    for model in report["models"]:
        name = model["name"]
        rows, probabilities = predictions[name]
        model_labels = [int(row["label"]) for row in rows]
        point = (pr_auc(model_labels, probabilities) - pr_auc(model_labels, pair_predictions)
                 if pr_auc(model_labels, probabilities) is not None and pr_auc(model_labels, pair_predictions) is not None
                 else None)
        entry = {
            "model_pr_auc": pr_auc(model_labels, probabilities),
            "pair_baseline_pr_auc": pr_auc(model_labels, pair_predictions),
            "delta": point,
            **paired_bootstrap_delta_ap(model_labels, probabilities, pair_predictions, resamples=2000, seed=7),
        }
        model_ap = entry["model_pr_auc"]
        if model_ap is not None and pair_ap is not None and constant and model_ap != constant:
            entry["persistence_share_of_lift_over_constant_prevalence"] = (
                (pair_ap - constant) / (model_ap - constant))
        comparison["model_scores"][name] = entry
    comparison["holdout_rows"] = len(holdout_labels)
    report["model_vs_pair_baseline"] = comparison

    # ------------------------------------------------- F1 diagnostic: leaky labels
    leaky_models, _ = _evaluate_specs(
        mature, origins, specifications, min_train_origins=min_train_origins,
        purge=False, horizon_months=horizon_months)
    diagnostic: dict[str, Any] = {
        "purge": False,
        "role": "diagnostic_only",
        "warning": (
            "NOT the headline result. Training rows here may have label windows overlapping the test window "
            "(up to horizon_months-3 months of overlap). Reported only to quantify the optimism of the "
            "previously published numbers."),
        "models": [
            {"name": model["name"],
             "development_metrics": model["development_metrics"],
             "holdout_metrics": model["holdout_metrics"],
             "origin_pr_auc": [{"cutoff": row["cutoff"], "pr_auc": row["pr_auc"]}
                               for row in model["origin_metrics"]]}
            for model in leaky_models
        ],
        "delta_purged_minus_leaky": {},
    }
    for purged_model, leaky_model in zip(report["models"], leaky_models):
        delta = {}
        for metric in ("pr_auc", "brier", "ece", "false_positive_rate", "precision_at_k"):
            old = leaky_model["holdout_metrics"].get(metric)
            new = purged_model["holdout_metrics"].get(metric)
            delta[metric] = (new - old) if old is not None and new is not None else None
        delta["development_pr_auc"] = (
            purged_model["development_metrics"].get("pr_auc") - leaky_model["development_metrics"].get("pr_auc")
            if purged_model["development_metrics"].get("pr_auc") is not None
            and leaky_model["development_metrics"].get("pr_auc") is not None else None)
        diagnostic["delta_purged_minus_leaky"][purged_model["name"]] = delta
    diagnostic["interpretation"] = (
        "deltas are purged minus leaky: positive PR-AUC means the purged model ranks better, positive Brier/ECE/FPR "
        "means the leaky numbers were optimistic (lower is better).")
    report["leaky_labels_diagnostic"] = diagnostic
    return report
