"""Reproducible Market-to-R&D ingestion and research pipeline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..config import CACHE_DIR, DEFAULT_DB, OUT_DIR, load_companies
from ..db import DB
from ..http import Fetcher
from ..live import SEC_UA
from ..util import read_json, utc_now_iso, write_json
from .evaluation.backtesting import run_backtest
from .evaluation.leakage_audit import audit_examples
from .entities.technology_mapping import materialize_regulatory_edges
from .features.demand_features import procurement_summary
from .features.market_features import attach_market_features
from .features.publication_features import attach_publication_features
from .features.research_features import DATASET_VERSION, build_examples
from .forecasting.calibration import calibration_report
from .forecasting.horizon import create_forecasts, verify_forecasts
from .sources import market_data, openfda_bulk, patents, procurement_us, publications, sec_financials
from .storage import IntelligenceStore


def _companies() -> list[dict[str, Any]]:
    """Device company registry as plain dicts (key/name_en/aliases/ticker)."""
    return [dict(row) for row in load_companies("device").all()]


def _store(path: str | Path) -> IntelligenceStore:
    return IntelligenceStore(DB(path))


def _fetcher(offline: bool = False) -> Fetcher:
    return Fetcher(cache_dir=CACHE_DIR, offline=offline, min_interval=0.35, max_requests=500, ua=SEC_UA)


def _examples(store: IntelligenceStore) -> list[dict[str, Any]]:
    rows = []
    for raw in store.conn.execute("SELECT * FROM forecast_examples WHERE dataset_version=? ORDER BY cutoff", (DATASET_VERSION,)):
        row = dict(raw)
        row["features"] = json.loads(row["features"])
        rows.append(row)
    return rows


def collect(args: argparse.Namespace) -> dict[str, Any]:
    companies = args.companies.split(",") if args.companies else None
    with _store(args.db) as store:
        fetcher = _fetcher(args.offline)
        previous = read_json(args.out, {})
        result: dict[str, Any] = {"retrieved_at": utc_now_iso(),
                                  "sources": dict((previous or {}).get("sources") or {})}
        if args.source in ("fda",):
            result["sources"]["openfda_bulk"] = openfda_bulk.collect(store, fetcher, months=args.months)
        if args.source in ("sec", "all"):
            result["sources"]["sec_financials"] = sec_financials.collect(
                store, fetcher, companies=companies, limit=args.limit)
        if args.source in ("procurement", "all"):
            result["sources"]["procurement_us"] = procurement_us.collect(
                store, fetcher, companies=companies, start_date=args.start_date,
                end_date=args.end_date, max_pages_per_company=args.max_pages)
        if args.source in ("market", "all"):
            if not args.prices_db:
                raise SystemExit("--prices-db is required for --source market (base MedRadar prices table)")
            result["sources"]["market_data"] = market_data.collect(
                store, args.prices_db, _companies())
        if args.source in ("publications", "all"):
            result["sources"]["publications"] = publications.collect(
                store, _companies(), offline=args.offline,
                max_requests=args.max_publication_requests)
        if args.source in ("patents", "all"):
            result["sources"]["patents"] = patents.collect(
                store, _companies(), fetcher=fetcher if not args.offline else None)
        result["request_stats"] = fetcher.stats
    write_json(args.out, result)
    return result


def research(args: argparse.Namespace) -> dict[str, Any]:
    with _store(args.db) as store:
        dataset = build_examples(store, horizon_months=args.horizon)
        stored = store.replace_examples(DATASET_VERSION, dataset["examples"])
        leakage = audit_examples(store, DATASET_VERSION)
        if not leakage["ok"]:
            raise RuntimeError(f"Temporal leakage audit failed: {leakage['violations'][:3]}")
        provenance = read_json(args.provenance, {}) if args.provenance else {}
        provenance.update({
            "retrieved_at": provenance.get("retrieved_at") or utc_now_iso(),
            "fda_event_count": dataset["event_count"], "fda_coverage_end": dataset["coverage_end"],
            "financial_fact_rows": store.conn.execute("SELECT COUNT(*) FROM financial_facts").fetchone()[0],
            "procurement_award_rows": store.conn.execute("SELECT COUNT(*) FROM procurement_awards").fetchone()[0],
            "procurement_pit_rows": store.conn.execute("SELECT COUNT(*) FROM procurement_awards WHERE pit_usable=1").fetchone()[0],
        })
        examples = _examples(store)
        report = run_backtest(examples, dataset["base_features"], dataset["financial_features"],
                              horizon_months=args.horizon,
                              data_provenance=provenance)
        report["dataset"] = {key: value for key, value in dataset.items() if key != "examples"}
        report["dataset"]["stored_examples"] = stored
        report["temporal_graph"] = {"regulatory_edges_materialized": materialize_regulatory_edges(store),
                                    "inferred_investment_edges": 0}
        report["leakage_audit"] = leakage
        forecasts = create_forecasts(
            store, base_features=dataset["base_features"], financial_features=dataset["financial_features"],
            coverage_end=dataset["coverage_end"], horizon_months=args.horizon, top_n=args.top_n)
        verification = verify_forecasts(store, coverage_end=dataset["coverage_end"])
        report["forecast_registry"] = {"created_or_updated": len(forecasts), **verification,
                                       "calibration": calibration_report(store)}
        procurement = procurement_summary(store)
        report["procurement_descriptive"] = {key: value for key, value in procurement.items()
                                             if key not in ("companies", "categories", "performance_start_year")}
        write_json(args.out / "procurement_summary.json", procurement)
        write_json(args.out / "metrics.json", report)
        write_json(args.out / "forecasts.json", forecasts)
        write_json(args.out / "dataset_summary.json", report["dataset"])
        if args.publish_experiment:
            publish = Path(args.publish_experiment)
            write_json(publish / "metrics.json", report)
            write_json(publish / "forecasts.json", forecasts)
            write_json(publish / "procurement_summary.json", procurement)
            write_json(publish / "data_provenance.json", provenance)
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MedRadar Market-to-R&D research pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    collector = sub.add_parser("collect", help="collect SEC financials and/or USAspending awards")
    collector.add_argument("--source", choices=("fda", "sec", "procurement", "market",
                                                "publications", "patents", "all"), default="all")
    collector.add_argument("--db", default=str(DEFAULT_DB))
    collector.add_argument("--months", type=int, default=120, help="FDA bulk history window")
    collector.add_argument("--companies", help="comma-separated company keys; default is the supported registry")
    collector.add_argument("--limit", type=int, default=0, help="maximum SEC companies, 0=all")
    collector.add_argument("--prices-db", default=None,
                           help="base MedRadar SQLite file holding the `prices` table (market import, read-only)")
    collector.add_argument("--max-publication-requests", type=int, default=None,
                           help="cap OpenAlex requests (default: all companies)")
    collector.add_argument("--start-date", default="2016-01-01")
    collector.add_argument("--end-date", default=None)
    collector.add_argument("--max-pages", type=int, default=2)
    collector.add_argument("--offline", action="store_true")
    collector.add_argument("--out", type=Path, default=OUT_DIR / "reverse_rd" / "data_provenance.json")
    run = sub.add_parser("research", help="build dataset, backtest, audit and register forecasts")
    run.add_argument("--db", default=str(DEFAULT_DB))
    run.add_argument("--horizon", type=int, default=12)
    run.add_argument("--top-n", type=int, default=25)
    run.add_argument("--provenance", type=Path, default=OUT_DIR / "reverse_rd" / "data_provenance.json")
    run.add_argument("--out", type=Path, default=OUT_DIR / "reverse_rd")
    run.add_argument("--publish-experiment", default=str(Path("experiments/reverse_rd_v1")))
    args = parser.parse_args(argv)
    result = collect(args) if args.command == "collect" else research(args)
    summary = result if args.command == "collect" else {
        "dataset": result["dataset"]["stored_examples"], "origins": len(result["origins"]),
        "holdout": result["holdout"], "models": [
            {"name": model["name"], "holdout": model["holdout_metrics"]} for model in result["models"]],
        "forecasts": result["forecast_registry"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
