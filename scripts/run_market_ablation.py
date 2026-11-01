"""Real-data incremental-value ablation for the Phase-2 market feature group.

This script is fully offline. It

1. imports the curated companies' daily bars and the ``SPY``/``XBI`` benchmarks
   from the base repository's local ``prices`` table (Yahoo daily lane) into the
   research database's ``market_bars`` table — no network calls;
2. loads the frozen v1 continuation examples (``reverse_rd_v1``) from the
   research database and attaches point-in-time market features at each
   example cutoff;
3. runs the *existing* purged rolling-origin backtest at the frozen final
   holdout for four feature sets on identical rows: ``rd_only``,
   ``rd_financial``, ``rd_market`` and ``rd_financial_market``;
4. writes ``experiments/reverse_rd_v2/market_metrics.json`` with the protocol,
   coverage, per-model metrics, marginal-value deltas, a v1 reproduction check
   and a strictly factual interpretation.

Reproduce (same machine, same research DB)::

    python scripts/run_market_ablation.py

The price database defaults to ``D:/DEPPSKK/medradar/data/medradar.sqlite`` and
can be overridden with ``MEDRADAR_PRICES_DB`` or ``--prices-db``. The script
never writes to the price database (it is opened read-only) and never claims
causality: a single chronological holdout is a directional check, not proof.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # allow `python scripts/run_market_ablation.py`
    sys.path.insert(0, str(ROOT))

from medradar.config import load_config  # noqa: E402
from medradar.db import DB  # noqa: E402
from medradar.intelligence.evaluation.backtesting import run_backtest  # noqa: E402
from medradar.intelligence.features.financial_features import FEATURES as FINANCIAL_FEATURES  # noqa: E402
from medradar.intelligence.features.market_features import (  # noqa: E402
    FEATURES as MARKET_FEATURES,
    MISSING_KEY as MARKET_MISSING_KEY,
    attach_market_features,
)
from medradar.intelligence.features.research_features import BASE_FEATURES, DATASET_VERSION  # noqa: E402
from medradar.intelligence.sources import market_data  # noqa: E402
from medradar.intelligence.storage import IntelligenceStore  # noqa: E402
from medradar.util import read_json, write_json  # noqa: E402

DEFAULT_PRICES_DB = "D:/DEPPSKK/medradar/data/medradar.sqlite"
DEFAULT_OUT = ROOT / "experiments" / "reverse_rd_v2" / "market_metrics.json"
DEFAULT_RESEARCH_DB = ROOT / "data" / "medradar.sqlite"
HORIZON_MONTHS = 12
MIN_TRAIN_ORIGINS = 3
HOLDOUTS_AVAILABLE_CHECK = 3
REPORT_METRICS = ("pr_auc", "brier", "ece", "false_positive_rate", "precision_at_k")
TARGET = (
    "Any material public FDA 510(k)/original-or-panel-track PMA activity for an "
    "already-active company-track pair in the next 12 months"
)
LIMITATIONS = [
    "One chronological holdout (2025-10-01, 307 rows / 129 positives): point estimates only, no significance claim.",
    "Market bars are the base repo's Yahoo Finance daily lane imported offline; not a licensed market-data feed.",
    "Survivorship: delisted/acquired tickers and tickers never fetched are absent; 38 of 51 curated companies matched.",
    "6 companies have a ticker that is absent from the local price table and 7 have no ticker at all; "
    "their market features are null and the model falls back to training-median imputation with a missing indicator.",
    "ADRs (PHG, TRUMY, OJPNY/FUJIY) and foreign listings are a different instrument from the local shares.",
    "The research database's stored v1 examples were reused unchanged; only market features were added.",
    "No market cap, valuation multiple or fundamental market factor is implemented (no shares-outstanding data).",
    "Stock returns are not a measure of technological capability and no causal market-to-R&D claim is made.",
    "The multi-holdout protocol was not available in this worktree; see evaluation_protocol.multi_holdout.",
]


# --------------------------------------------------------------------------- inputs
def load_companies() -> list[dict[str, Any]]:
    payload = load_config("companies_device", {"companies": []})
    companies = payload.get("companies") if isinstance(payload, dict) else None
    if not companies:
        raise RuntimeError("config/companies_device.json has no companies list")
    return list(companies)


def load_examples(store: IntelligenceStore, dataset_version: str) -> list[dict[str, Any]]:
    rows = []
    cursor = store.conn.execute(
        "SELECT * FROM forecast_examples WHERE dataset_version = ?"
        " ORDER BY cutoff, company_key, track_id",
        (dataset_version,),
    )
    for raw in cursor:
        row = dict(raw)
        try:
            row["features"] = json.loads(row["features"])
        except (TypeError, ValueError):
            row["features"] = {}
        rows.append(row)
    if not rows:
        raise RuntimeError(
            f"no stored examples for dataset_version={dataset_version!r}; "
            "run the v1 research pipeline first")
    return rows


# --------------------------------------------------------------------------- results
def _model_block(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "description": model.get("description"),
        "features": list(model.get("features") or []),
        "training_label_policy": model.get("training_label_policy"),
        "holdout_metrics": model.get("holdout_metrics"),
        "development_metrics": model.get("development_metrics"),
        "origin_pr_auc": [
            {"cutoff": row.get("cutoff"), "pr_auc": row.get("pr_auc")}
            for row in model.get("origin_metrics") or []
        ],
        "forecast_horizon_stability": model.get("forecast_horizon_stability"),
    }


def _delta(first: dict[str, Any], second: dict[str, Any]) -> dict[str, float | None]:
    """``second - first`` per reported metric (positive PR-AUC/Precision is better)."""
    values: dict[str, float | None] = {}
    for metric in REPORT_METRICS:
        left = (first.get("holdout_metrics") or {}).get(metric)
        right = (second.get("holdout_metrics") or {}).get(metric)
        values[metric] = (right - left) if left is not None and right is not None else None
    return values


def _multi_holdout(examples: list[dict[str, Any]], base_features: list[str],
                   market_features: list[str], financial_features: list[str]) -> dict[str, Any]:
    """Run the last N origins when the harness supports it; otherwise say so.

    The multi-holdout protocol lives in a separate worktree at the time of this
    experiment. Rather than inventing an API, this checks the installed
    ``run_backtest`` signature and only attempts the call when a ``holdouts``
    parameter exists; any failure is reported honestly instead of hidden.
    """
    result: dict[str, Any] = {
        "requested_origins": HOLDOUTS_AVAILABLE_CHECK,
        "available": False,
        "reason": None,
        "results": None,
    }
    try:
        parameters = inspect.signature(run_backtest).parameters
    except (TypeError, ValueError):  # pragma: no cover - defensive
        parameters = {}
    if "holdouts" not in parameters:
        result["reason"] = (
            "the run_backtest installed in this worktree has no 'holdouts' parameter "
            "(multi-holdout support is owned by a separate worktree); the frozen single "
            "final holdout was used instead")
        return result
    origins = sorted({row["cutoff"] for row in examples if row.get("maturity") == "mature"})
    try:
        report = run_backtest(
            examples, base_features + market_features, financial_features,
            horizon_months=HORIZON_MONTHS, min_train_origins=MIN_TRAIN_ORIGINS,
            holdouts=origins[-HOLDOUTS_AVAILABLE_CHECK:])
    except (TypeError, ValueError) as exc:
        result["reason"] = f"'holdouts' is present but unsupported here: {type(exc).__name__}: {exc}"
        return result
    result.update({"available": True, "results": {key: value for key, value in report.items()
                                                  if key in ("models", "holdouts", "holdout", "origins")}})
    return result


def _v1_reproduction(models: dict[str, Any]) -> dict[str, Any]:
    """Compare recomputed rd_only/rd_financial holdout metrics with committed v1."""
    committed_path = ROOT / "experiments" / "reverse_rd_v1" / "metrics.json"
    committed = read_json(committed_path, {})
    by_name = {entry.get("name"): entry for entry in (committed or {}).get("models", [])}
    checks: dict[str, Any] = {}
    for name in ("rd_only", "rd_financial"):
        reference = (by_name.get(name) or {}).get("holdout_metrics") or {}
        recomputed = models[name]["holdout_metrics"] or {}
        metrics: dict[str, Any] = {}
        for metric in REPORT_METRICS:
            expected = reference.get(metric)
            actual = recomputed.get(metric)
            metrics[metric] = {
                "committed_v1": expected,
                "recomputed": actual,
                "delta": (actual - expected) if expected is not None and actual is not None else None,
            }
        checks[name] = metrics
    return {
        "reference": str(committed_path),
        "note": ("The v1 examples are reused unchanged; identical metrics confirm that the "
                 "reference block and the market ablations share the same rows and protocol."),
        "checks": checks,
    }


def _coverage(store: IntelligenceStore, collect_result: dict[str, Any],
              companies: list[dict[str, Any]], mapping: dict[str, str],
              examples: list[dict[str, Any]], attach_summary: dict[str, Any],
              holdout: str) -> dict[str, Any]:
    bar_stats = {
        str(row[0]): {"bars": int(row[1]), "date_min": row[2], "date_max": row[3]}
        for row in store.conn.execute(
            "SELECT ticker, COUNT(*), MIN(date), MAX(date) FROM market_bars GROUP BY ticker")
    }
    example_counts: dict[str, int] = {}
    for example in examples:
        key = str(example.get("company_key") or "")
        example_counts[key] = example_counts.get(key, 0) + 1
    per_company = []
    for company in companies:
        key = str(company.get("key") or "")
        ticker = mapping.get(key) or market_data.normalise_ticker(company.get("ticker"))
        stats = bar_stats.get(ticker or "", {})
        per_company.append({
            "company_key": key,
            "ticker": ticker or None,
            "bars": stats.get("bars", 0),
            "date_min": stats.get("date_min"),
            "date_max": stats.get("date_max"),
            "examples": example_counts.get(key, 0),
            "has_market_data": bool(stats.get("bars")),
        })
    holdout_rows = [row for row in examples if row.get("cutoff") == holdout]
    holdout_missing = sum(1 for row in holdout_rows
                          if int((row["features"] or {}).get(MARKET_MISSING_KEY, 1) or 0))
    holdout_non_null = {
        name: sum(1 for row in holdout_rows if (row["features"] or {}).get(name) is not None)
        for name in MARKET_FEATURES
    }
    by_cutoff = []
    for cutoff in sorted({str(row.get("cutoff")) for row in examples}):
        members = [row for row in examples if str(row.get("cutoff")) == cutoff]
        missing = sum(1 for row in members if int((row["features"] or {}).get(MARKET_MISSING_KEY, 1) or 0))
        by_cutoff.append({"cutoff": cutoff, "examples": len(members), "market_missing": missing})
    with_ticker = sum(1 for company in companies
                      if market_data.normalise_ticker(company.get("ticker")))
    return {
        "companies_total": len(companies),
        "companies_with_ticker": with_ticker,
        "companies_without_ticker": len(companies) - with_ticker,
        "company_tickers_requested": collect_result["tickers"],
        "company_tickers_matched": collect_result["tickers_imported"],
        "benchmarks_requested": collect_result["benchmarks"],
        "benchmarks_matched": collect_result["benchmarks_imported"],
        "price_source": collect_result["source"],
        "bars_imported": collect_result["rows"],
        "bars_in_table": collect_result["rows_in_table"],
        "bars_date_min": collect_result["date_min"],
        "bars_date_max": collect_result["date_max"],
        "missing_tickers": collect_result["missing_tickers"],
        "unmapped_companies": collect_result["unmapped_companies"],
        "examples_total": len(examples),
        "examples_with_market_features": attach_summary["with_market_data"],
        "examples_missing_market_features": attach_summary["missing"],
        "examples_company_without_ticker": attach_summary["no_ticker"],
        "examples_cutoff_min": min(str(row.get("cutoff")) for row in examples),
        "examples_cutoff_max": max(str(row.get("cutoff")) for row in examples),
        "holdout_examples": len(holdout_rows),
        "holdout_market_missing": holdout_missing,
        "holdout_non_null_by_feature": holdout_non_null,
        "attach_non_null_by_feature": attach_summary["non_null_by_feature"],
        "examples_by_cutoff": by_cutoff,
        "per_company": per_company,
    }


def _interpretation(models: dict[str, Any], marginal: dict[str, Any],
                    coverage: dict[str, Any], holdout: str) -> str:
    holdout_metrics = {name: value["holdout_metrics"] or {} for name, value in models.items()}
    n = holdout_metrics["rd_only"].get("n")
    positives = holdout_metrics["rd_only"].get("positives")
    market_delta = (marginal["rd_market_minus_rd_only"] or {}).get("pr_auc")
    financial_delta = (marginal["rd_financial_minus_rd_only"] or {}).get("pr_auc")
    market_on_financial = (marginal["rd_financial_market_minus_rd_financial"] or {}).get("pr_auc")
    brier_delta = (marginal["rd_market_minus_rd_only"] or {}).get("brier")
    covered = coverage["examples_with_market_features"]
    total = coverage["examples_total"]
    parts = [
        f"On the single chronological holdout {holdout} ({n} examples, {positives} positives), "
        f"market features were available for {covered} of {total} stored examples "
        f"({100.0 * covered / total:.1f}%; {coverage['company_tickers_matched']} of "
        f"{coverage['companies_total']} companies have price bars).",
        f"rd_only PR-AUC {holdout_metrics['rd_only'].get('pr_auc')!r} -> "
        f"rd_market {holdout_metrics['rd_market'].get('pr_auc')!r} "
        f"(delta {market_delta:+.6f}); adding market features to R&D+financial moves PR-AUC from "
        f"{holdout_metrics['rd_financial'].get('pr_auc')!r} to "
        f"{holdout_metrics['rd_financial_market'].get('pr_auc')!r} "
        f"(delta {market_on_financial:+.6f}).",
        "The financial block's own holdout PR-AUC delta versus rd_only is "
        f"{financial_delta:+.6f} and the market-vs-R&D Brier delta is {brier_delta:+.6f} "
        "(negative Brier is better calibration).",
        "These are one-holdout point estimates with no significance test; a positive delta is a "
        "directional ranking improvement, not evidence that market prices cause or predict R&D "
        "capability, and a non-positive delta means the market group added no measurable "
        "incremental ranking value on this holdout.",
    ]
    return " ".join(parts)


# --------------------------------------------------------------------------- main
def run(db_path: Path, prices_db: Path, out_path: Path,
        dataset_version: str = DATASET_VERSION) -> dict[str, Any]:
    companies = load_companies()
    mapping = market_data.company_ticker_map(companies)
    with IntelligenceStore(DB(db_path)) as store:
        collect_result = market_data.collect(store, prices_db, companies)
        examples = load_examples(store, dataset_version)
        attach_summary = attach_market_features(store, examples, companies, mapping)
        base_features = list(BASE_FEATURES)
        financial_features = list(FINANCIAL_FEATURES)
        market_features = list(MARKET_FEATURES)

        # Call 1: the frozen v1 reference specifications.
        reference = run_backtest(
            examples, base_features, financial_features,
            min_train_origins=MIN_TRAIN_ORIGINS, horizon_months=HORIZON_MONTHS)
        # Call 2: identical rows/protocol, market features appended to each block.
        with_market = run_backtest(
            examples, base_features + market_features, financial_features,
            min_train_origins=MIN_TRAIN_ORIGINS, horizon_months=HORIZON_MONTHS)

        models = {
            "rd_only": _model_block(reference["models"][0]),
            "rd_financial": _model_block(reference["models"][1]),
            "rd_market": _model_block(with_market["models"][0]),
            "rd_financial_market": _model_block(with_market["models"][1]),
        }
        models["rd_market"]["description"] = "C: R&D history + point-in-time market features"
        models["rd_market"]["features"] = base_features + market_features
        models["rd_financial_market"]["description"] = (
            "D: R&D history + consolidated SEC financials + point-in-time market features")
        models["rd_financial_market"]["features"] = base_features + financial_features + market_features

        holdout = reference["holdout"]
        marginal = {
            "notation": "delta = second - first on the same holdout rows; positive PR-AUC/Precision "
                        "and negative Brier/ECE/FPR are improvements.",
            "rd_market_minus_rd_only": _delta(models["rd_only"], models["rd_market"]),
            "rd_financial_minus_rd_only": _delta(models["rd_only"], models["rd_financial"]),
            "rd_financial_market_minus_rd_financial": _delta(
                models["rd_financial"], models["rd_financial_market"]),
            "rd_financial_market_minus_rd_only": _delta(models["rd_only"], models["rd_financial_market"]),
        }
        baselines = reference.get("baselines") or {}
        comparison = reference.get("model_vs_pair_baseline") or {}
        coverage = _coverage(store, collect_result, companies, mapping, examples,
                             attach_summary, holdout)
        multi_holdout = _multi_holdout(examples, base_features, market_features, financial_features)

    protocol = {
        "name": "reverse_rd_v2_market_ablation",
        "target": TARGET,
        "target_horizon_months": HORIZON_MONTHS,
        "mode": "expanding-window rolling-origin with matured-label purge; the final "
                "chronological origin is the single untouched holdout",
        "purge_rule": "a training example may be used at origin t only when "
                      "cutoff + horizon_months <= t",
        "purge_used": True,
        "holdout": holdout,
        "origins": list(reference.get("origins") or []),
        "min_train_origins": MIN_TRAIN_ORIGINS,
        "algorithm": "LogisticBaseline (deterministic batch-gradient logistic regression, "
                     "180 epochs, learning rate 0.15, l2 1.0, training-only median imputation "
                     "with missing indicators)",
        "rows_identical_across_feature_sets": True,
        "features": {
            "base": base_features,
            "financial": financial_features,
            "market": market_features,
        },
        "multi_holdout": multi_holdout,
        "metrics": list(REPORT_METRICS),
        "positive_class": "continue: at least one material public FDA 510(k)/PMA event for the "
                          "already-active company-track pair inside the 12-month label window",
        "reproduce": "python scripts/run_market_ablation.py",
    }

    report = {
        "experiment": "reverse_rd_v2_market_ablation",
        "dataset_version": dataset_version,
        "generated_by": "scripts/run_market_ablation.py",
        "python_version": sys.version.split()[0],
        "evaluation_protocol": protocol,
        "coverage": coverage,
        "models": models,
        "marginal_value": marginal,
        "baselines": baselines,
        "model_vs_pair_baseline": {
            "resamples": comparison.get("resamples"),
            "seed": comparison.get("seed"),
            "confidence_level": comparison.get("confidence_level"),
            "pair_baseline_pr_auc": comparison.get("pair_baseline_pr_auc"),
            "holdout_rows": comparison.get("holdout_rows"),
            "model_scores": {
                name: {key: value for key, value in entry.items()
                       if key in ("model_pr_auc", "pair_baseline_pr_auc", "delta",
                                  "valid_resamples", "ci_low", "ci_high", "p_delta_le_zero")}
                for name, entry in (comparison.get("model_scores") or {}).items()
            },
        },
        "v1_reproduction": _v1_reproduction(models),
        "interpretation": _interpretation(models, marginal, coverage, holdout),
        "limitations": LIMITATIONS,
    }
    write_json(out_path, report)
    return report


def _summary(report: dict[str, Any], out_path: Path | None = None) -> dict[str, Any]:
    models = report["models"]
    return {
        "experiment": report["experiment"],
        "holdout": report["evaluation_protocol"]["holdout"],
        "coverage": {
            "companies_total": report["coverage"]["companies_total"],
            "companies_with_ticker": report["coverage"]["company_tickers_requested"],
            "companies_matched": report["coverage"]["company_tickers_matched"],
            "bars": report["coverage"]["bars_imported"],
            "date_range": [report["coverage"]["bars_date_min"], report["coverage"]["bars_date_max"]],
            "examples_with_market_features": report["coverage"]["examples_with_market_features"],
            "examples_total": report["coverage"]["examples_total"],
        },
        "holdout_metrics": {
            name: {metric: (value["holdout_metrics"] or {}).get(metric) for metric in ("pr_auc", "brier", "ece")}
            for name, value in models.items()
        },
        "marginal_value": report["marginal_value"],
        "interpretation": report["interpretation"],
        "output": str(out_path or DEFAULT_OUT),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase-2 market feature incremental-value ablation")
    parser.add_argument("--db", type=Path, default=DEFAULT_RESEARCH_DB,
                        help="research database with stored v1 examples (and market_bars target)")
    parser.add_argument("--prices-db", type=Path,
                        default=Path(os.environ.get("MEDRADAR_PRICES_DB") or DEFAULT_PRICES_DB),
                        help="base MedRadar database with the prices table (opened read-only)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dataset-version", default=DATASET_VERSION)
    args = parser.parse_args(argv)
    if not args.db.is_file():
        raise SystemExit(f"research database not found: {args.db}")
    if not args.prices_db.is_file():
        raise SystemExit(
            f"price database not found: {args.prices_db} (set MEDRADAR_PRICES_DB or --prices-db)")
    report = run(args.db, args.prices_db, args.out, dataset_version=args.dataset_version)
    print(json.dumps(_summary(report, args.out), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
