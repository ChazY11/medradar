"""Expanding-window, rolling-origin evaluation with one final time holdout.

Training labels are purged by default: an example may only train an origin when
its whole label window has closed before the test window opens. The old
(unpurged) specification is retained as an explicitly labelled diagnostic so the
size of the previous bias is measured instead of hidden.

With ``holdouts=K`` the last K chronological origins are reported as sequential
holdout windows, each evaluated with its own expanding purged training set. The
test rows are disjoint by construction (one origin each); the 12-month label
windows of different origins overlap, which is documented rather than hidden.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Callable, Iterable

from ...util import add_months, parse_date
from ..models.baseline import LogisticBaseline
from .metrics import evaluate, paired_bootstrap_delta_ap, pr_auc, stability

DEFAULT_HORIZON_MONTHS = 12
WINDOW_METRICS = ("n", "positives", "prevalence", "pr_auc", "brier", "ece",
                  "false_positive_rate", "precision_at_k", "mean_lead_time_days")
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


def _window_stats(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Mean/std/min/max of a metric across holdout windows (population std)."""
    result: dict[str, dict[str, Any]] = {}
    for metric in WINDOW_METRICS:
        values = [entry[metric] for entry in entries
                  if isinstance(entry.get(metric), (int, float)) and not isinstance(entry.get(metric), bool)]
        if not values:
            continue
        mean = sum(values) / len(values)
        spread = (math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
                  if len(values) > 1 else 0.0)
        result[metric] = {"mean": mean, "std": spread, "min": min(values),
                          "max": max(values), "windows": len(values)}
    return result


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
                    min_train_origins: int, purge: bool, horizon_months: int,
                    window_origins: Iterable[str] | None = None
                    ) -> tuple[list[dict[str, Any]],
                               dict[str, dict[str, tuple[list[dict[str, Any]], list[float]]]]]:
    holdout = origins[-1]
    wanted = set(window_origins) if window_origins is not None else {holdout}
    models: list[dict[str, Any]] = []
    window_predictions: dict[str, dict[str, tuple[list[dict[str, Any]], list[float]]]] = {}
    for model_name, description, features in specifications:
        origin_rows: list[dict[str, Any]] = []
        development_rows: list[dict[str, Any]] = []
        development_probabilities: list[float] = []
        holdout_metrics: dict[str, Any] | None = None
        holdout_rows: list[dict[str, Any]] = []
        holdout_probabilities: list[float] = []
        window_predictions[model_name] = {}
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
            if cutoff in wanted:
                window_predictions[model_name][cutoff] = (test, probabilities)
            if cutoff != holdout:
                development_rows.extend(test)
                development_probabilities.extend(probabilities)
            else:
                holdout_metrics = metrics
                holdout_rows, holdout_probabilities = test, probabilities
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
        if holdout not in window_predictions[model_name]:
            # Degenerate case: the holdout origin had no usable training rows or a
            # single label class. Keep the key present and empty so the report can
            # state "not evaluable" instead of raising.
            window_predictions[model_name][holdout] = ([], [])
    return models, window_predictions


def run_backtest(examples: list[dict[str, Any]], base_features: list[str],
                 financial_features: list[str], *, min_train_origins: int = 3,
                 horizon_months: int = DEFAULT_HORIZON_MONTHS, holdouts: int = 1,
                 specifications: list[tuple[str, str, list[str]]] | None = None,
                 experiment: str = "reverse_rd_v1",
                 data_provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    mature = [row for row in examples if row["maturity"] == "mature" and row["label"] is not None]
    origins = sorted({row["cutoff"] for row in mature})
    if len(origins) < min_train_origins + 2:
        raise ValueError(f"Need at least {min_train_origins + 2} mature origins, got {len(origins)}")
    if holdouts < 1:
        raise ValueError(f"holdouts must be >= 1, got {holdouts}")
    # An origin can only be a holdout window when it has a purged training set:
    # with quarterly origins and a 12-month horizon the first four origins have
    # no matured training examples yet. The last K *evaluable* origins are used,
    # which for the frozen experiments is also the last K chronological origins.
    evaluable = [cutoff for cutoff in origins
                 if eligible_training_rows(mature, cutoff, purge=True, horizon_months=horizon_months)]
    if holdouts > len(evaluable):
        raise ValueError(
            f"holdouts={holdouts} exceeds the {len(evaluable)} origins with a purged training set "
            f"(origins={len(origins)}, min_train_origins={min_train_origins})")
    holdout_origins = evaluable[-holdouts:]
    holdout = holdout_origins[-1]
    # A feature-group ablation passes an explicit specification list; the default
    # two-spec shape (A: R&D only, B: R&D + financials) is what v1/v2 artefacts use.
    default_specifications = specifications is None
    if specifications is None:
        specifications = [
            ("rd_only", "A: R&D history only", base_features),
            ("rd_financial", "B: R&D + consolidated SEC financials", base_features + financial_features),
        ]
    models, predictions = _evaluate_specs(
        mature, origins, specifications, min_train_origins=min_train_origins,
        purge=True, horizon_months=horizon_months, window_origins=holdout_origins)
    report: dict[str, Any] = {
        "experiment": experiment, "target_horizon_months": horizon_months,
        "evaluation": (
            "expanding-window rolling-origin with matured-label purge; the last chronological origin is the "
            "primary holdout. Training at origin t only uses examples whose label window closed at or before t. "
            "With holdouts=K the last K origins are reported as sequential holdout windows; their test rows are "
            "disjoint (one origin each) while their 12-month label windows overlap."),
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
        "holdouts": holdouts, "holdout_origins": holdout_origins,
        "holdout_origin_rule": (
            "The last K origins that have at least one purged training example. With quarterly origins and a "
            "12-month horizon the first four origins have no matured training examples, so this equals the last "
            "K chronological origins."),
        "models": models, "data_provenance": data_provenance or {},
        "constraints": [
            "No random temporal split.", "Identical rows, algorithm and hyperparameters across ablations.",
            "Training labels must mature before the evaluation origin (purge/embargo); the unpurged variant is "
            "diagnostic only.",
            "Current-snapshot procurement is excluded from historical gain claims.",
            "Consolidated company revenue is not product- or segment-level device sales.",
            "Multi-window holdouts are separate origins, so their test rows never overlap; their label windows do.",
        ],
    }

    # ------------------------------------------- multi-window holdout evaluation
    window_baselines = {origin: _persistence_baselines(
        mature, origin, purge=True, horizon_months=horizon_months) for origin in holdout_origins}
    windows: list[dict[str, Any]] = []
    for origin in holdout_origins:
        window_rows = [row for row in mature if row["cutoff"] == origin]
        baseline = window_baselines[origin]
        entry = {
            "origin": origin,
            "rows": len(window_rows),
            "positives": sum(int(row["label"]) for row in window_rows),
            "prevalence": (sum(int(row["label"]) for row in window_rows) / len(window_rows)
                           if window_rows else None),
            "training_rows": baseline.get("training_rows"),
            "training_origins": baseline.get("training_origins"),
            "model_metrics": {},
            "baseline_predictors": baseline.get("predictors", {}),
            "pair_base_rate_coverage": baseline.get("pair_base_rate_coverage"),
        }
        for model in models:
            name = model["name"]
            rows, probabilities = predictions[name].get(origin, ([], []))
            entry["model_metrics"][name] = _metrics(rows, probabilities) if rows else {}
        windows.append(entry)
    report["holdout_windows"] = windows
    report["holdout_window_summary"] = {
        "rule": ("Per-window metrics are computed at each origin; mean/std/min/max aggregate the "
                 "holdouts=K windows. std is the population standard deviation across windows, not a "
                 "confidence interval."),
        "models": {model["name"]: _window_stats([window["model_metrics"][model["name"]]
                                                 for window in windows])
                   for model in models},
        "baselines": {
            predictor: _window_stats([window["baseline_predictors"].get(predictor, {})
                                      for window in windows])
            for predictor in ("constant_training_prevalence", "company_base_rate",
                              "track_base_rate", "pair_base_rate")
        },
    }
    for model in models:
        model["holdout_window_metrics"] = [
            {"cutoff": window["origin"], **window["model_metrics"][model["name"]]} for window in windows]
        model["holdout_window_summary"] = report["holdout_window_summary"]["models"][model["name"]]

    if default_specifications and len(report["models"]) == 2:
        first, second = report["models"]
        report["financial_marginal_value"] = {
            metric: ((second["holdout_metrics"].get(metric) - first["holdout_metrics"].get(metric))
                     if first["holdout_metrics"].get(metric) is not None and second["holdout_metrics"].get(metric) is not None else None)
            for metric in ("pr_auc", "brier", "ece", "false_positive_rate", "precision_at_k")
        }
        window_deltas = []
        for window in windows:
            first_metrics, second_metrics = window["model_metrics"]["rd_only"], window["model_metrics"]["rd_financial"]
            metrics = {}
            for metric in ("pr_auc", "brier", "ece", "false_positive_rate", "precision_at_k"):
                old, new = first_metrics.get(metric), second_metrics.get(metric)
                metrics[metric] = (new - old) if old is not None and new is not None else None
            window_deltas.append({"origin": window["origin"], **metrics})
        report["financial_marginal_value"]["by_window"] = window_deltas
        report["financial_marginal_value"]["window_mean_delta"] = {
            metric: (sum(row[metric] for row in window_deltas if row[metric] is not None)
                     / len([row for row in window_deltas if row[metric] is not None])
                     if any(row[metric] is not None for row in window_deltas) else None)
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
    baselines = window_baselines[holdout]
    report["baselines"] = baselines
    holdout_labels = [int(row["label"]) for row in predictions[report["models"][0]["name"]].get(holdout, ([], []))[0]]
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
            "PR-AUC(model) - PR-AUC(pair_base_rate) on the untouched holdout, repeated for every holdout window."),
        "resamples": 2000, "seed": 7, "confidence_level": 0.95,
        "pair_baseline_pr_auc": pair_ap,
        "model_scores": {},
        "interpretation": (
            "If the interval includes zero, the R&D features add no statistically detectable ranking value "
            "beyond stable per-pair activity persistence on that holdout window. A per-pair base rate is "
            "degenerate when most holdout pairs have no matured training history (never-observed entry "
            "candidates), in which case it collapses towards constant training prevalence."),
    }
    for model in report["models"]:
        name = model["name"]
        rows, probabilities = predictions[name].get(holdout, ([], []))
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

    # Per-window version of the same paired comparison: the window table is what
    # lets a reader check whether a single-window delta is stable.
    by_window = []
    for window in windows:
        origin = window["origin"]
        window_rows = [row for row in mature if row["cutoff"] == origin]
        window_training = eligible_training_rows(
            mature, origin, purge=True, horizon_months=horizon_months)
        window_pair_predictions = _rate(
            lambda row: (row.get("company_key"), row.get("track_id")),
            window_training, window_rows,
            window_baselines[origin].get("training_prevalence", 0.0))[0]
        window_labels = [int(row["label"]) for row in window_rows]
        window_entry: dict[str, Any] = {
            "origin": origin, "holdout_rows": len(window_rows),
            "training_rows": len(window_training),
            "pair_base_rate_coverage": window_baselines[origin].get("pair_base_rate_coverage"),
            "models": {},
        }
        for model in report["models"]:
            name = model["name"]
            rows, probabilities = predictions[name].get(origin, ([], []))
            point = (pr_auc(window_labels, probabilities) - pr_auc(window_labels, window_pair_predictions)
                     if pr_auc(window_labels, probabilities) is not None
                     and pr_auc(window_labels, window_pair_predictions) is not None else None)
            window_entry["models"][name] = {
                "model_pr_auc": pr_auc(window_labels, probabilities),
                "pair_baseline_pr_auc": pr_auc(window_labels, window_pair_predictions),
                "delta": point,
                **paired_bootstrap_delta_ap(
                    window_labels, probabilities, window_pair_predictions, resamples=2000, seed=7),
            }
        by_window.append(window_entry)
    comparison["by_window"] = by_window
    comparison["window_mean_delta"] = {
        model["name"]: (sum(entry["models"][model["name"]]["delta"] for entry in by_window
                            if entry["models"][model["name"]]["delta"] is not None)
                        / len([entry for entry in by_window
                               if entry["models"][model["name"]]["delta"] is not None])
                        if any(entry["models"][model["name"]]["delta"] is not None for entry in by_window)
                        else None)
        for model in report["models"]
    }
    comparison["windows_with_ci_excluding_zero"] = {
        model["name"]: [entry["origin"] for entry in by_window
                        if entry["models"][model["name"]]["ci_low"] is not None
                        and (entry["models"][model["name"]]["ci_low"] > 0
                             or entry["models"][model["name"]]["ci_high"] < 0)]
        for model in report["models"]
    }
    report["model_vs_pair_baseline"] = comparison

    # ------------------------------------------------- F1 diagnostic: leaky labels
    leaky_models, _ = _evaluate_specs(
        mature, origins, specifications, min_train_origins=min_train_origins,
        purge=False, horizon_months=horizon_months, window_origins=holdout_origins)
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
