#!/usr/bin/env python3
"""Continuous forecast cycle CLI (offline, deterministic apart from timestamps).

    python scripts/forecast_cycle.py --db data/research.sqlite \
        --registry data/registry.sqlite --out out/forecast_cycle \
        --horizon 12 --top-n 25 --coverage-end 2026-10-15

Steps: train on the frozen continuation examples -> score the current quarter's
candidates -> create Horizon records -> register them as canonical ``nowcast``
rows (idempotent) -> verify matured registered nowcasts from real events with
coverage guards -> export the deterministic evaluation artifact + a cycle JSON
log. A second identical run registers nothing new.

Offline by design: the cycle itself performs no network I/O (``--offline``
states that explicitly). Data collection is a separate step
(``python -m medradar.intelligence.pipeline collect ...``), which is what the
weekly GitHub workflow does before calling this script.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medradar.intelligence.forecasting.cycle import run_cycle, summary  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forecast_cycle",
        description="Continuous forecasting cycle: train -> score -> register -> verify -> export",
    )
    parser.add_argument("--db", default=str(ROOT / "data" / "research.sqlite"),
                        help="research SQLite database (events + forecast_examples)")
    parser.add_argument("--registry", default=str(ROOT / "data" / "registry.sqlite"),
                        help="canonical Forecast Registry SQLite file (created if absent)")
    parser.add_argument("--out", default=str(ROOT / "out" / "forecast_cycle"),
                        help="output directory for evaluation.json + cycle.json")
    parser.add_argument("--horizon", type=int, default=12, help="forecast horizon in months")
    parser.add_argument("--top-n", type=int, default=25,
                        help="number of highest-probability candidates to register")
    parser.add_argument("--coverage-end", default=None,
                        help="observed-coverage end date (YYYY-MM-DD); default: max event_date in the DB")
    parser.add_argument("--provenance", default=str(ROOT / "experiments" / "reverse_rd_v2" / "data_provenance.json"),
                        help="frozen collection provenance JSON recorded in the registry evidence")
    parser.add_argument("--snapshot", default=None,
                        help="optional local medradar-tkg snapshot.json for verified-local snapshot provenance")
    parser.add_argument("--as-of", default=None,
                        help="evaluation cutoff (default: the registry store clock at the end of the run)")
    parser.add_argument("--offline", action="store_true",
                        help="assert the offline mode (the cycle never performs network I/O)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log = run_cycle(
        db_path=Path(args.db),
        registry_db=Path(args.registry),
        out_dir=Path(args.out),
        horizon_months=args.horizon,
        top_n=args.top_n,
        coverage_end=args.coverage_end,
        provenance_path=Path(args.provenance) if args.provenance else None,
        snapshot_path=Path(args.snapshot) if args.snapshot else None,
        as_of=args.as_of,
        offline=args.offline,
    )
    print(json.dumps(summary(log), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
