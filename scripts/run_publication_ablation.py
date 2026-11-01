"""Publication (OpenAlex) ablation on the real Market-to-R&D dataset.

Protocol (identical to the v1 headline evaluation apart from the added features):

* examples: ``research_features.build_examples`` (continuation target, 12-month
  horizon, quarterly origins, final chronological origin 2025-10-01 as holdout);
* training: purged/embargoed rolling origin -- an example may only train an
  origin once its label window has matured (``cutoff + 12m <= origin``);
* models: ``rd_only`` (10 R&D features), ``rd_publications`` (the same plus the
  five point-in-time OpenAlex features) and ``rd_financial_publications`` (also
  including the eleven consolidated SEC features);
* holdout metrics: PR-AUC/AP, Brier, ECE-10, FPR@0.5, Precision@10%, plus a
  deterministic paired bootstrap (2,000 resamples, seed 7) of the PR-AUC delta.

The script is re-runnable offline from the OpenAlex cache
(``data/cache/openalex``) once the collection has run: pass no ``--live`` flag
and the cached grouped responses are replayed with no network calls. Patent
features are attached but NOT evaluated: USPTO ODP needs an API key and none is
available, so no patent ablation numbers are produced or fabricated.

Usage::

    python scripts/run_publication_ablation.py --live          # first run, fetches + caches
    python scripts/run_publication_ablation.py                 # offline replay from cache
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medradar.config import CACHE_DIR, DEFAULT_DB  # noqa: E402
from medradar.db import DB  # noqa: E402
from medradar.intelligence.evaluation.backtesting import eligible_training_rows  # noqa: E402
from medradar.intelligence.evaluation.metrics import (  # noqa: E402
    evaluate,
    paired_bootstrap_delta_ap,
)
from medradar.intelligence.features.publication_features import (  # noqa: E402
    PATENT_FEATURES,
    PUBLICATION_FEATURES,
    attach_patent_features,
    attach_publication_features,
    patent_feature_coverage,
    publication_feature_coverage,
)
from medradar.intelligence.features.research_features import build_examples  # noqa: E402
from medradar.intelligence.models.baseline import LogisticBaseline  # noqa: E402
from medradar.intelligence.sources import patents, publications  # noqa: E402
from medradar.intelligence.storage import IntelligenceStore  # noqa: E402
from medradar.util import parse_date, read_json, write_json  # noqa: E402

EXPERIMENT = "reverse_rd_v2_publications"
HOLDOUT = "2025-10-01"
HORIZON_MONTHS = 12
MIN_TRAIN_ORIGINS = 3
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 7


def load_company_rows(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path, {})
    if isinstance(payload, dict):
        return [dict(row) for row in payload.get("companies") or []]
    return [dict(row) for row in payload or []]


def _lead_time(row: dict[str, Any]) -> int | None:
    if not row.get("label") or not row.get("first_target_event_date"):
        return None
    start, end = parse_date(row["cutoff"]), parse_date(row["first_target_event_date"])
    return (end - start).days if start and end else None


def _stability(origin_rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row["pr_auc"] for row in origin_rows if not row.get("is_holdout") and row.get("pr_auc") is not None]
    if not values:
        return {"origins": 0, "pr_auc_mean": None, "pr_auc_std": None,
                "pr_auc_min": None, "pr_auc_max": None}
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {"origins": len(values), "pr_auc_mean": mean, "pr_auc_std": variance ** 0.5,
            "pr_auc_min": min(values), "pr_auc_max": max(values)}


def evaluate_specification(examples: list[dict[str, Any]], features: list[str], *,
                           horizon_months: int = HORIZON_MONTHS,
                           min_train_origins: int = MIN_TRAIN_ORIGINS) -> dict[str, Any]:
    mature = [row for row in examples if row["maturity"] == "mature" and row["label"] is not None]
    origins = sorted({row["cutoff"] for row in mature})
    holdout = origins[-1]
    origin_rows: list[dict[str, Any]] = []
    development_rows: list[dict[str, Any]] = []
    development_probabilities: list[float] = []
    holdout_metrics: dict[str, Any] | None = None
    holdout_rows: list[dict[str, Any]] = []
    holdout_probabilities: list[float] = []
    for index in range(min_train_origins, len(origins)):
        cutoff = origins[index]
        train = eligible_training_rows(mature, cutoff, purge=True, horizon_months=horizon_months)
        test = [row for row in mature if row["cutoff"] == cutoff]
        if not train or not test or len({row["label"] for row in train}) < 2:
            continue
        model = LogisticBaseline(features).fit(
            [row["features"] for row in train], [int(row["label"]) for row in train])
        probabilities = model.predict_proba([row["features"] for row in test])
        metrics = evaluate([int(row["label"]) for row in test], probabilities,
                           lead_times=[_lead_time(row) for row in test])
        origin_rows.append({"cutoff": cutoff, "is_holdout": cutoff == holdout, **metrics})
        if cutoff == holdout:
            holdout_metrics = metrics
            holdout_rows, holdout_probabilities = test, probabilities
        else:
            development_rows.extend(test)
            development_probabilities.extend(probabilities)
    return {
        "features": list(features),
        "feature_count": len(features),
        "training_label_policy": "purged_matured_by_origin",
        "development_metrics": evaluate(
            [int(row["label"]) for row in development_rows], development_probabilities,
            lead_times=[_lead_time(row) for row in development_rows]),
        "holdout_metrics": holdout_metrics,
        "forecast_horizon_stability": _stability(origin_rows),
        "origin_metrics": origin_rows,
        "_holdout_rows": holdout_rows,
        "_holdout_probabilities": holdout_probabilities,
    }


def metric_delta(new: dict[str, Any], old: dict[str, Any], metric: str) -> float | None:
    if not new or not old:
        return None
    left, right = new.get(metric), old.get(metric)
    return float(left) - float(right) if left is not None and right is not None else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reverse R&D v2 publication ablation (OpenAlex)")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--companies-config", default=str(ROOT / "config" / "companies_device.json"))
    parser.add_argument("--out", default=str(ROOT / "experiments" / "reverse_rd_v2"))
    parser.add_argument("--cache-dir", default=str(Path(CACHE_DIR) / "openalex"))
    parser.add_argument("--horizon", type=int, default=HORIZON_MONTHS)
    parser.add_argument("--min-train-origins", type=int, default=MIN_TRAIN_ORIGINS)
    parser.add_argument("--live", action="store_true",
                        help="make live OpenAlex requests (default: replay the on-disk cache offline)")
    parser.add_argument("--refresh", action="store_true", help="with --live, ignore the cache and refetch")
    parser.add_argument("--max-requests", type=int, default=60,
                        help="hard live OpenAlex request budget for this run (default 60)")
    args = parser.parse_args(argv)

    companies = load_company_rows(Path(args.companies_config))
    if not companies:
        print(json.dumps({"error": f"no companies parsed from {args.companies_config}"}))
        return 2
    out_dir = Path(args.out)
    store = IntelligenceStore(DB(args.db))
    try:
        collection = publications.collect(
            store, companies, cache_dir=args.cache_dir, offline=not args.live,
            refresh=bool(args.refresh and args.live), max_requests=args.max_requests)
        if collection["companies_with_data"] == 0:
            print(json.dumps({
                "error": "no OpenAlex data available offline; run with --live once to populate the cache",
                "cache_dir": args.cache_dir,
                "failures": collection["failures"][:5],
            }))
            return 2

        dataset = build_examples(store, horizon_months=args.horizon)
        examples = dataset["examples"]
        attach_publication_features(store, examples)
        patent_collection = patents.collect(store, companies)
        attach_patent_features(store, examples)

        base_features = list(dataset["base_features"])
        financial_features = list(dataset["financial_features"])
        specifications = {
            "rd_only": base_features,
            "rd_publications": base_features + list(PUBLICATION_FEATURES),
            "rd_financial_publications": base_features + financial_features + list(PUBLICATION_FEATURES),
        }
        results = {name: evaluate_specification(
            examples, features, horizon_months=args.horizon,
            min_train_origins=args.min_train_origins) for name, features in specifications.items()}

        holdout_rows = results["rd_only"]["_holdout_rows"]
        predictions = {name: result.pop("_holdout_probabilities") for name, result in results.items()}
        for result in results.values():
            result.pop("_holdout_rows", None)
        holdout_labels = [int(row["label"]) for row in holdout_rows]

        comparisons = {
            "rd_publications_minus_rd_only": ("rd_publications", "rd_only"),
            "rd_financial_publications_minus_rd_publications": (
                "rd_financial_publications", "rd_publications"),
        }
        bootstrap: dict[str, Any] = {}
        deltas: dict[str, Any] = {}
        for label, (new, old) in comparisons.items():
            deltas[label] = {
                metric: metric_delta(results[new]["holdout_metrics"], results[old]["holdout_metrics"], metric)
                for metric in ("pr_auc", "brier", "ece", "false_positive_rate", "precision_at_k")}
            deltas[label]["development_pr_auc"] = metric_delta(
                results[new]["development_metrics"], results[old]["development_metrics"], "pr_auc")
            bootstrap[label] = paired_bootstrap_delta_ap(
                holdout_labels, predictions[new], predictions[old],
                resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED)

        v1_metrics = read_json(ROOT / "experiments" / "reverse_rd_v1" / "metrics.json", {}) or {}
        v1_rd_only = next((model["holdout_metrics"] for model in (v1_metrics.get("models") or [])
                           if model.get("name") == "rd_only"), {})
        anchor = {}
        for metric in ("pr_auc", "brier", "ece", "false_positive_rate", "precision_at_k",
                       "n", "positives"):
            reproduced = results["rd_only"]["holdout_metrics"].get(metric)
            expected = v1_rd_only.get(metric)
            absolute = (abs(float(reproduced) - float(expected))
                        if isinstance(reproduced, (int, float)) and isinstance(expected, (int, float)) else None)
            anchor[metric] = {"v1": expected, "reproduced": reproduced, "abs_delta": absolute}
        numeric_deltas = [entry["abs_delta"] for entry in anchor.values() if entry["abs_delta"] is not None]
        anchor["matches_v1_rd_only"] = bool(numeric_deltas) and max(numeric_deltas) <= 1e-12
        anchor["max_abs_delta"] = max(numeric_deltas) if numeric_deltas else None

        publication_coverage = publication_feature_coverage(examples)
        publication_coverage.update({
            "companies_requested": collection["companies_requested"],
            "companies_with_data": collection["companies_with_data"],
            "companies_zero_works": collection["companies_zero_works"],
            "companies_failed": collection["companies_failed"],
            "total_works": collection["total_works"],
            "year_range": collection["year_range"],
            "examples_in_holdout": len(holdout_rows),
            "holdout_examples_with_publication_data": sum(
                1 for row in holdout_rows if (row.get("features") or {}).get("pub_missing") == 0.0),
        })

        holdout_deltas = {name: result["holdout_metrics"] for name, result in results.items()}
        metrics_payload = {
            "experiment": EXPERIMENT,
            "generated_from": {
                "db": str(Path(args.db).name),
                "companies_config": str(Path(args.companies_config).name),
                "collection_mode": "live" if args.live else "offline_cache_replay",
            },
            "protocol": {
                "target": dataset["target"],
                "horizon_months": args.horizon,
                "cutoff_frequency": "quarterly",
                "split": "purged expanding-window rolling origin; final chronological origin holdout",
                "purge_rule": "training example cutoff + horizon_months <= origin",
                "min_train_origins": args.min_train_origins,
                "holdout": HOLDOUT,
                "origins": dataset["cutoffs"],
                "model": {"algorithm": "logistic_regression_batch_gd", "epochs": 180,
                          "learning_rate": 0.15, "l2": 1.0,
                          "standardization": "training origins only",
                          "missing_values": "training median plus missing indicator"},
                "same_protocol_as": "experiments/reverse_rd_v1 (purged default)",
            },
            "dataset": {key: value for key, value in dataset.items() if key != "examples"},
            "publication_features": list(PUBLICATION_FEATURES),
            "patent_features": list(PATENT_FEATURES),
            "publication_coverage": publication_coverage,
            "patent_coverage": patent_feature_coverage(examples),
            "patents": patent_collection,
            "models": results,
            "deltas": deltas,
            "paired_bootstrap": bootstrap,
            "v1_anchor": anchor,
            "interpretation": (
                "Deltas are new minus old on the untouched holdout; positive PR-AUC/Precision@K and "
                "negative Brier/ECE/FPR are improvements. A bootstrap interval that includes zero means "
                "no statistically detectable incremental value on this single holdout. Patents are NOT "
                "evaluated because no USPTO API key is available; no patent numbers are reported."),
        }
        provenance_payload = {
            "experiment": EXPERIMENT,
            "collected_at": collection.get("collected_at"),
            "companies_config": str(Path(args.companies_config).name),
            "publications": collection,
            "patents": patent_collection,
        }
        output = out_dir
        write_json(output / "publication_metrics.json", metrics_payload)
        write_json(output / "publication_provenance.json", provenance_payload)
        summary = {
            "out": str(output),
            "publication_coverage": publication_coverage,
            "holdout": {name: {"n": entry.get("n"), "positives": entry.get("positives"),
                               "pr_auc": entry.get("pr_auc"), "brier": entry.get("brier"),
                               "ece": entry.get("ece"), "false_positive_rate": entry.get("false_positive_rate"),
                               "precision_at_k": entry.get("precision_at_k")}
                        for name, entry in holdout_deltas.items()},
            "deltas": deltas,
            "bootstrap": {name: {key: entry[key] for key in ("mean_delta", "ci_low", "ci_high", "p_delta_le_zero")}
                          for name, entry in bootstrap.items()},
            "v1_anchor_matches": anchor["matches_v1_rd_only"],
            "patents": patent_collection["status"],
            "requests": collection["request_stats"],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
