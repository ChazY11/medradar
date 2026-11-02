#!/usr/bin/env python3
"""Regenerate the frozen reverse_rd_v2 experiment (Phase 1 scientific hardening).

Two targets on the same real database, both evaluated with the shared purged
rolling-origin protocol and ``holdouts=3``:

1. continuation (``reverse_rd_v1``): v1's already-active-pair target, recomputed so
   the multi-window numbers are reproducible from this repository state;
2. entry (``first_entry_v1``): the new dormant -> active track-entry target with
   explicit left-censoring.

No network access. Inputs: an existing MedRadar SQLite database with the openFDA
bulk lane, SEC Company Facts and (for continuation provenance only) USAspending
awards. Outputs: ``config.json``, ``data_provenance.json``,
``continuation_metrics.json``, ``entry_metrics.json`` and a console summary.

Usage (from the repository root):

    python experiments/reverse_rd_v2/run_v2.py --db data/medradar.sqlite

The 208 MB database and the HTTP cache are gitignored; only the small aggregate
artifacts next to this script are committed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medradar.db import DB  # noqa: E402
from medradar.intelligence.evaluation.backtesting import (  # noqa: E402
    DEFAULT_HORIZON_MONTHS,
    PURGE_RULE,
    eligible_training_rows,
    run_backtest,
)
from medradar.intelligence.evaluation.leakage_audit import audit_examples  # noqa: E402
from medradar.intelligence.features.research_features import (  # noqa: E402
    COVERAGE_END_REFERENCE,
    DATASET_VERSION,
    DEFAULT_DORMANCY_MONTHS,
    ENTRY_DATASET_VERSION,
    ENTRY_FEATURES,
    ENTRY_INACTIVE_MONTHS_CAP,
    build_entry_examples,
    build_examples,
)
from medradar.intelligence.storage import IntelligenceStore  # noqa: E402
from medradar.util import iso, read_json, utc_now_iso, write_json  # noqa: E402


def _compact_audit(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": audit["method"],
        "dataset_version": audit["dataset_version"],
        "entry_target": audit["entry_target"],
        "checked_examples": audit["checked_examples"],
        "checked_cutoffs": audit["checked_cutoffs"],
        "checked_feature_values": audit["checked_feature_values"],
        "mismatch_count": audit["mismatch_count"],
        "unreplayable_examples": audit["unreplayable_examples"],
        "per_feature_mismatches": {name: count for name, count in audit["per_feature_mismatches"].items() if count},
        "violation_count": audit["violation_count"],
        "ok": audit["ok"],
        "limitations": audit["limitations"],
    }


def _dataset_block(dataset: dict[str, Any], examples: list[dict[str, Any]],
                   min_train_origins: int) -> dict[str, Any]:
    mature = [row for row in examples if row["maturity"] == "mature"]
    origins = sorted({row["cutoff"] for row in mature})
    positives = sum(int(row["label"]) for row in mature)
    leaky_ok = [origin for origin in origins
                if eligible_training_rows(mature, origin, purge=False)]
    evaluable = [origin for origin in origins
                 if eligible_training_rows(mature, origin, purge=True)]
    block = {
        "dataset_version": dataset["dataset_version"],
        "examples_total": len(examples),
        "examples_mature": len(mature),
        "positives_mature": positives,
        "base_rate_mature": positives / len(mature) if mature else None,
        "negatives_mature": len(mature) - positives,
        "origins": len(origins), "origin_first": origins[0] if origins else None,
        "origin_last": origins[-1] if origins else None,
        "min_train_origins": min_train_origins,
        "evaluable_origins": len(evaluable),
        "leaky_training_origins": len(leaky_ok),
        "cutoffs": origins,
        "base_features": dataset["base_features"],
        "financial_features": dataset["financial_features"],
    }
    if "entry_features" in dataset:
        block["entry_features"] = dataset["entry_features"]
        block.update({
            "dormancy_months": dataset["dormancy_months"],
            "horizon_months": dataset["horizon_months"],
            "coverage_start": dataset["coverage_start"],
            "coverage_end": dataset["coverage_end"],
            "coverage_check": dataset["coverage_check"],
            "event_count": dataset["event_count"],
            "company_count": dataset["company_count"],
            "track_count": dataset["track_count"],
            "observed_pair_count": dataset["observed_pair_count"],
            "candidate_universe": dataset["candidate_universe"],
            "skipped_pending_examples": dataset["skipped_pending_examples"],
            "candidates_by_origin": dataset["candidates_by_origin"],
            "positives_by_origin": dataset["positives_by_origin"],
            "left_censoring": dataset["left_censoring"],
        })
    else:
        block["coverage_end"] = dataset["coverage_end"]
        block["event_count"] = dataset["event_count"]
        block["company_count"] = dataset["company_count"]
        block["pair_count"] = dataset["pair_count"]
        block["skipped_immature"] = dataset["skipped_immature"]
    return block


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data" / "medradar.sqlite"))
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--holdouts", type=int, default=3)
    parser.add_argument("--dormancy", type=int, default=DEFAULT_DORMANCY_MONTHS)
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON_MONTHS)
    parser.add_argument("--min-train-origins", type=int, default=3)
    parser.add_argument("--coverage-end", default=COVERAGE_END_REFERENCE)
    args = parser.parse_args(argv)
    out = Path(args.out)
    generated_at = utc_now_iso()
    timings: dict[str, Any] = {}

    with IntelligenceStore(DB(args.db)) as store:
        # ---------------------------------------------------------- datasets
        started = time.time()
        continuation = build_examples(store, horizon_months=args.horizon)
        timings["build_continuation_seconds"] = round(time.time() - started, 1)
        started = time.time()
        entry = build_entry_examples(store, dormancy_months=args.dormancy,
                                     horizon_months=args.horizon,
                                     expected_coverage_end=args.coverage_end)
        timings["build_entry_seconds"] = round(time.time() - started, 1)

        continuation_stored = store.conn.execute(
            "SELECT COUNT(*) FROM forecast_examples WHERE dataset_version = ?",
            (DATASET_VERSION,)).fetchone()[0]
        stored_entry = store.replace_examples(ENTRY_DATASET_VERSION, entry["examples"])

        started = time.time()
        continuation_audit = audit_examples(store, DATASET_VERSION)
        timings["audit_continuation_seconds"] = round(time.time() - started, 1)
        started = time.time()
        entry_audit = audit_examples(store, ENTRY_DATASET_VERSION)
        timings["audit_entry_seconds"] = round(time.time() - started, 1)
        if not continuation_audit["ok"]:
            raise SystemExit(f"continuation leakage audit failed: {continuation_audit['violations'][:3]}")
        if not entry_audit["ok"]:
            raise SystemExit(f"entry leakage audit failed: {entry_audit['violations'][:3]}")

        counts = {
            "financial_fact_rows": store.conn.execute(
                "SELECT COUNT(*) FROM financial_facts").fetchone()[0],
            "procurement_award_rows": store.conn.execute(
                "SELECT COUNT(*) FROM procurement_awards").fetchone()[0],
            "procurement_pit_rows": store.conn.execute(
                "SELECT COUNT(*) FROM procurement_awards WHERE pit_usable=1").fetchone()[0],
        }

        # --------------------------------------------------------- backtests
        started = time.time()
        continuation_report = run_backtest(
            continuation["examples"], continuation["base_features"], continuation["financial_features"],
            min_train_origins=args.min_train_origins, horizon_months=args.horizon,
            holdouts=args.holdouts, experiment="reverse_rd_v2_continuation")
        timings["backtest_continuation_seconds"] = round(time.time() - started, 1)
        started = time.time()
        entry_report = run_backtest(
            entry["examples"], entry["base_features"], entry["financial_features"],
            min_train_origins=args.min_train_origins, horizon_months=args.horizon,
            holdouts=args.holdouts, experiment="reverse_rd_v2_entry")
        timings["backtest_entry_seconds"] = round(time.time() - started, 1)

    continuation_report["dataset"] = _dataset_block(
        continuation, continuation["examples"], args.min_train_origins)
    continuation_report["dataset"]["stored_examples"] = continuation_stored
    continuation_report["leakage_audit"] = _compact_audit(continuation_audit)
    entry_report["dataset"] = _dataset_block(entry, entry["examples"], args.min_train_origins)
    entry_report["dataset"]["stored_examples"] = stored_entry
    entry_report["leakage_audit"] = _compact_audit(entry_audit)

    # ------------------------------------------------------------- provenance
    provenance = dict(read_json(ROOT / "experiments" / "reverse_rd_v1" / "data_provenance.json", {}) or {})
    provenance["retrieved_at"] = provenance.get("retrieved_at") or utc_now_iso()
    provenance["regenerated_at"] = generated_at
    provenance["source_experiment"] = "experiments/reverse_rd_v1/data_provenance.json (copied, collection unchanged)"
    provenance["fda_event_count"] = entry["event_count"]
    provenance["fda_coverage_start"] = entry["coverage_start"]
    provenance["fda_coverage_end"] = entry["coverage_end"]
    provenance.update(counts)
    provenance["material_event_rules"] = (
        "Any resolved-company 510(k); PMA only when supplement_number is empty/0/S0 or supplement_type "
        "contains 'PANEL TRACK' (identical to reverse_rd_v1).")
    provenance["entry_target"] = {
        "dataset_version": ENTRY_DATASET_VERSION,
        "coverage_start": entry["coverage_start"],
        "coverage_end": entry["coverage_end"],
        "coverage_check": entry["coverage_check"],
        "event_count": entry["event_count"],
        "company_count": entry["company_count"],
        "track_count": entry["track_count"],
        "observed_pair_count": entry["observed_pair_count"],
        "dormancy_months": args.dormancy,
        "horizon_months": args.horizon,
        "candidate_universe": entry["candidate_universe"],
        "examples_total": len(entry["examples"]),
        "examples_stored": stored_entry,
        "candidates_by_origin": entry["candidates_by_origin"],
        "positives_by_origin": entry["positives_by_origin"],
        "skipped_pending_examples": entry["skipped_pending_examples"],
        "left_censoring": entry["left_censoring"],
    }
    provenance["continuation_dataset"] = {
        "dataset_version": continuation["dataset_version"],
        "examples_total": len(continuation["examples"]),
        "examples_stored": continuation_stored,
        "origins": len(continuation["cutoffs"]),
        "coverage_end": continuation["coverage_end"],
    }
    provenance["leakage_audit"] = {
        "continuation": _compact_audit(continuation_audit),
        "entry": _compact_audit(entry_audit),
    }
    provenance["known_environment_note"] = (
        "This regeneration reuses the frozen research database copied from the v1 collection (no network); "
        "collection-side provenance blocks above are unchanged. The product-catalog tests in tests/test_products.py "
        "compare config/*.json against data/medradar.sqlite and fail when that file is replaced by this reduced "
        "research database (55,090 device events only); they are unrelated to the intelligence layer.")

    # ---------------------------------------------------------------- config
    config = {
        "experiment": "reverse_rd_v2",
        "purpose": "Phase 1 scientific hardening: harder entry target + multi-window expanding-origin evaluation",
        "frozen_before_holdout": "2026-11-02",
        "generated_at": generated_at,
        "cutoff_frequency": "quarterly quarter-start",
        "horizon_months": args.horizon,
        "min_train_origins": args.min_train_origins,
        "holdouts": args.holdouts,
        "holdout_origin_rule": (
            "last K origins with at least one purged training example; for these quarterly origins that is also "
            "the last K chronological origins"),
        "purge": {"default": True, "rule": PURGE_RULE, "horizon_months": args.horizon},
        "split": "expanding-window rolling-origin, no random temporal split",
        "algorithm": {
            "name": "logistic_regression_batch_gd",
            "epochs": 180, "learning_rate": 0.15, "l2": 1.0,
            "standardization": "training origins only",
            "missing_values": "training median plus missing indicator",
            "note": "identical algorithm and hyperparameters in every window and ablation",
        },
        "targets": {
            "continuation": {
                "dataset_version": DATASET_VERSION,
                "definition": continuation["target"],
                "origins": continuation["cutoffs"],
                "holdout_origins": continuation_report["holdout_origins"],
            },
            "entry": {
                "dataset_version": ENTRY_DATASET_VERSION,
                "definition": entry["target"],
                "dormancy_months": args.dormancy,
                "horizon_months": args.horizon,
                "candidate_universe": entry["candidate_universe"],
                "coverage_start": entry["coverage_start"],
                "coverage_end": entry["coverage_end"],
                "coverage_check": entry["coverage_check"],
                "left_censoring": entry["left_censoring"],
                "origins": entry["cutoffs"],
                "holdout_origins": entry_report["holdout_origins"],
                "inactive_months_cap": ENTRY_INACTIVE_MONTHS_CAP,
                "features": {
                    "shared": entry["base_features"],
                    "financial": entry["financial_features"],
                    "entry_specific": ENTRY_FEATURES,
                },
            },
        },
        "ablations": {
            "rd_only": "shared R&D/regulatory history features (plus entry-specific features for the entry target)",
            "rd_financial": "the same features plus eleven consolidated SEC Company Facts features",
        },
        "baselines": ["constant_training_prevalence", "company_base_rate", "track_base_rate",
                      "pair_base_rate (degenerate for never-observed entry candidates)"],
        "metrics": ["PR-AUC", "Brier", "ECE-10", "FPR@0.5", "Precision@ceil(10%N)",
                    "mean lead time among positive targets", "per-window mean/std across the last K origins",
                    "paired bootstrap AP(model)-AP(pair base rate) per window"],
        "excluded_from_historical_gain": {
            "procurement": "USAspending current snapshot cannot reconstruct first-publication time",
            "market": "not in v2", "patent": "not in v2", "publications": "not in v2", "jobs": "not in v2",
        },
        "notes": (
            "A public regulatory milestone is a lagging R&D proxy. The continuation target is not first entry; "
            "the entry target is first *observed* entry inside the 2016-11-01..2026-10-15 bulk window and is "
            "left-censored. Neither target measures internal R&D start, product revenue or a causal market->R&D "
            "effect."),
    }

    # -------------------------------------------------------------- artifacts
    write_json(out / "config.json", config)
    write_json(out / "data_provenance.json", provenance)
    write_json(out / "continuation_metrics.json", continuation_report)
    write_json(out / "entry_metrics.json", entry_report)
    write_json(out / "run_timings.json", {"generated_at": generated_at, "timings": timings})

    summary = {
        "generated_at": generated_at,
        "timings": timings,
        "continuation": {
            "dataset": continuation_report["dataset"],
            "holdout_origins": continuation_report["holdout_origins"],
            "window_summary_pr_auc": {
                name: continuation_report["holdout_window_summary"]["models"][name]["pr_auc"]
                for name in ("rd_only", "rd_financial")},
            "holdout_metrics": {model["name"]: model["holdout_metrics"]
                                for model in continuation_report["models"]},
        },
        "entry": {
            "dataset": entry_report["dataset"],
            "holdout_origins": entry_report["holdout_origins"],
            "window_summary_pr_auc": {
                name: entry_report["holdout_window_summary"]["models"][name]["pr_auc"]
                for name in ("rd_only", "rd_financial")},
            "holdout_metrics": {model["name"]: model["holdout_metrics"]
                                for model in entry_report["models"]},
        },
        "leakage_audit": {"continuation": provenance["leakage_audit"]["continuation"],
                          "entry": provenance["leakage_audit"]["entry"]},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
