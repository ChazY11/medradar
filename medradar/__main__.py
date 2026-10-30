"""Command line entry point: ``python -m medradar <command>``.

Commands are intentionally boring and composable so the GitHub Action can run
``python -m medradar run --all`` once a week:

    collect -> analyze -> report -> trade

Every stage is resumable: collectors cache HTTP responses, and ``analyze`` only
reads the SQLite facts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import CACHE_DIR, DEFAULT_DB, DEFAULT_METRICS, OUT_DIR


def _emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))


def _make_fetcher(args: argparse.Namespace):
    from .http import Fetcher

    return Fetcher(
        cache_dir=None if getattr(args, "no_cache", False) else CACHE_DIR,
        fixtures_dir=getattr(args, "fixtures", None),
        offline=getattr(args, "offline", False),
        min_interval=getattr(args, "min_interval", 0.3),
        max_requests=getattr(args, "budget", 900),
    )


# --------------------------------------------------------------------- collectors
COLLECTORS = {
    "device": ("medradar.collect_device", "collect"),
    "drug": ("medradar.collect_drug", "collect"),
    "trials": ("medradar.clinical", "collect_trials"),
    "nmpa": ("medradar.nmpa", "collect"),
}


def cmd_collect(args: argparse.Namespace) -> int:
    import importlib

    from .db import DB

    sources = [name.strip() for name in args.sources.split(",") if name.strip()]
    fetcher = _make_fetcher(args)
    summary: dict[str, object] = {"sources": {}, "request_stats": None}
    with DB(args.db) as db:
        for name in sources:
            if name not in COLLECTORS:
                summary["sources"][name] = f"unknown source (known: {sorted(COLLECTORS)})"
                continue
            module_name, function_name = COLLECTORS[name]
            try:
                module = importlib.import_module(module_name)
                function = getattr(module, function_name)
            except (ImportError, AttributeError) as exc:
                summary["sources"][name] = f"not installed yet: {exc}"
                continue
            try:
                summary["sources"][name] = function(
                    db,
                    fetcher,
                    months=args.months,
                    limit=args.limit,
                )
            except Exception as exc:  # keep going: one broken source must not kill the run
                summary["sources"][name] = f"FAILED: {type(exc).__name__}: {exc}"
        summary["request_stats"] = fetcher.stats
        summary["db_counts"] = {
            table: db.table_count(table)
            for table in ("events", "companies", "tracks", "product_codes")
        }
    _emit(summary)
    failed = [k for k, v in summary["sources"].items() if isinstance(v, str) and v.startswith("FAILED")]
    return 1 if failed else 0


# ----------------------------------------------------------------------- analyze
def cmd_analyze(args: argparse.Namespace) -> int:
    from .analyze import build_metrics
    from .db import DB
    from .util import write_json

    with DB(args.db) as db:
        metrics = build_metrics(
            db,
            window_quarters=args.window_quarters,
            baseline_quarters=args.baseline_quarters,
        )
    write_json(args.out, metrics)
    _emit(
        {
            "metrics": str(args.out),
            "window": metrics["meta"]["window"],
            "device_tracks": len(metrics["device"]["tracks"]),
            "device_companies": len(metrics["device"]["companies"]),
            "drug_approvals": len(metrics["drug"]["approvals"]),
            "signals": len(metrics["signals"]),
            "cn_gap_status": metrics["meta"]["data_status"].get("nmpa"),
        }
    )
    return 0


# ------------------------------------------------------------------------ report
def _publish_docs(args: argparse.Namespace) -> dict:
    """Mirror generated artefacts into ``docs/`` so GitHub Pages serves them.

    Pages is configured to deploy from the ``main`` branch ``/docs`` folder, so
    the weekly Action only needs to commit that directory.
    """
    import shutil

    from .config import DOCS_DIR
    from .util import ensure_dir

    out_dir = Path(args.out_dir)
    ensure_dir(DOCS_DIR)
    copied: list[str] = []
    for name in ("report_zh.md", "report_en.md", "summary.csv", "index.html"):
        source = out_dir / name
        if source.exists():
            shutil.copyfile(source, DOCS_DIR / name)
            copied.append(name)
    metrics_source = Path(args.metrics)
    if metrics_source.exists():
        shutil.copyfile(metrics_source, DOCS_DIR / "metrics.json")
        copied.append("metrics.json")
    return {"docs_dir": str(DOCS_DIR), "files": copied}


def cmd_report(args: argparse.Namespace) -> int:
    from .report import build_report

    result = build_report(metrics_path=args.metrics, out_dir=args.out_dir)
    result["published"] = _publish_docs(args)
    _emit(result)
    return 0


# ------------------------------------------------------------------------- trade
def _ingest_signals(args: argparse.Namespace) -> dict:
    """Persist ``metrics["signals"]`` into the ``signals`` table.

    ``analyze`` produces signals inside metrics.json; the trading engine reads
    them from SQLite so it stays a pure offline function of (signals, prices).
    """
    from .db import DB
    from .eventstudy import ingest_signals
    from .util import read_json

    metrics = read_json(args.out)
    if not metrics:
        return {"status": "skipped", "reason": "no metrics.json - run analyze first"}
    signals = metrics.get("signals") or []
    with DB(args.db) as db:
        written = ingest_signals(db, signals)
    # helpers may return None or a count; normalise for the CLI summary
    count = written if isinstance(written, int) else len(signals)
    print(json.dumps({"signals_ingested": count}, ensure_ascii=False))
    return {"status": "ok", "count": count}


def cmd_trade(args: argparse.Namespace) -> int:
    from .paper import run_paper

    _ingest_signals(args)
    result = run_paper(
        db_path=args.db,
        capital=args.capital,
        out_dir=args.out_dir,
        signal_kind=None if args.kinds == "all" else args.kinds.split(","),
    )
    _emit(result)
    return 0


# --------------------------------------------------------------------------- run
def _ensure_prices(args: argparse.Namespace) -> dict:
    """Fetch free daily bars for the watchlist before the trading study.

    Kept out of ``paper.run_paper`` on purpose: the trading engine must stay a
    pure offline function of (signals, prices), so a backtest can be re-run
    without any network access.
    """
    from .config import load_companies
    from .db import DB
    from .prices import fetch_prices

    tickers: set[str] = set()
    for kind in ("device", "drug"):
        tickers.update(ticker for ticker in load_companies(kind).tickers().values() if ticker)
    if not tickers:
        return {"status": "skipped", "reason": "no tickers configured"}
    try:
        fetcher = _make_fetcher(args)
        with DB(args.db) as db:
            if db.table_count("prices") > 0 and not args.refresh_prices:
                return {"status": "skipped", "reason": "prices already cached"}
            result = fetch_prices(db, fetcher, sorted(tickers))
        print(json.dumps({"prices": result}, ensure_ascii=False, default=str))
        return result
    except Exception as exc:  # never let a price feed failure kill the report
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}


def cmd_run(args: argparse.Namespace) -> int:
    args.sources = "device,drug,trials,nmpa"
    if not args.skip_collect:
        code = cmd_collect(args)
        if code != 0:
            print("[warn] some collectors failed; continuing with whatever data exists", file=sys.stderr)

    if not args.skip_analyze:
        cmd_analyze(args)

    # Trading needs three things in order: cached prices, signals in SQLite, and
    # signals computed from the current facts. ``analyze`` above produced them,
    # so ingest + trade now, then re-run analyze once so metrics.json carries the
    # fresh trading block (report also falls back to out/trading.json).
    if args.with_trade:
        prices = _ensure_prices(args)
        if prices.get("status") != "failed":
            _ingest_signals(args)
            cmd_trade(args)
            if not args.skip_analyze:
                cmd_analyze(args)

    if not args.skip_report:
        cmd_report(args)
    return 0


# ------------------------------------------------------------------------ status
def cmd_status(args: argparse.Namespace) -> int:
    from .db import DB

    if not Path(args.db).exists():
        _emit({"db": args.db, "exists": False, "hint": "run: python -m medradar run"})
        return 0
    with DB(args.db) as db:
        payload = {
            "db": str(args.db),
            "tables": {
                table: db.table_count(table)
                for table in ("events", "companies", "tracks", "product_codes", "prices", "signals")
            },
            "events_by_kind": {
                row["kind"]: row["n"]
                for row in db.query("SELECT kind, COUNT(*) AS n FROM events GROUP BY kind")
            },
            "last_run": db.query("SELECT * FROM runs ORDER BY finished_at DESC LIMIT 1"),
        }
    _emit(payload)
    return 0


# ---------------------------------------------------------------------- selftest
def cmd_selftest(args: argparse.Namespace) -> int:
    import unittest

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(Path(__file__).resolve().parents[1] / "tests"), top_level_dir=str(Path(__file__).resolve().parents[1]))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


# ---------------------------------------------------------------------- argparse
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="medradar",
        description="FDA device & drug industry radar with China-gap comparison and a paper-trading study.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_db_options(target: argparse.ArgumentParser) -> None:
        target.add_argument("--db", default=str(DEFAULT_DB), help="SQLite store (default: data/medradar.sqlite)")
        target.add_argument("--offline", action="store_true", help="replay cached responses only")
        target.add_argument("--no-cache", action="store_true", help="do not read/write the response cache")
        target.add_argument("--fixtures", default=None, help="directory with offline fixtures")
        target.add_argument("--min-interval", type=float, default=0.3, help="seconds between HTTP requests")
        target.add_argument("--budget", type=int, default=900, help="max HTTP requests for this run")

    collect = sub.add_parser("collect", help="fetch public data into SQLite")
    collect.add_argument("--sources", default="device,drug,trials,nmpa")
    collect.add_argument("--months", type=int, default=120, help="history window to backfill")
    collect.add_argument("--limit", type=int, default=0, help="cap records per source (0 = no cap)")
    add_db_options(collect)
    collect.set_defaults(func=cmd_collect)

    analyze = sub.add_parser("analyze", help="compute metrics JSON")
    analyze.add_argument("--out", default=str(DEFAULT_METRICS))
    analyze.add_argument("--window-quarters", type=int, default=8)
    analyze.add_argument("--baseline-quarters", type=int, default=20)
    add_db_options(analyze)
    analyze.set_defaults(func=cmd_analyze)

    report = sub.add_parser("report", help="render Chinese report + HTML dashboard")
    report.add_argument("--metrics", default=str(DEFAULT_METRICS))
    report.add_argument("--out-dir", default=str(OUT_DIR))
    report.set_defaults(func=cmd_report)

    trade = sub.add_parser("trade", help="run the simulated equity study")
    trade.add_argument("--capital", type=float, default=100_000.0)
    trade.add_argument("--kinds", default="all", help="comma separated signal kinds, or 'all'")
    trade.add_argument("--out-dir", default=str(OUT_DIR))
    trade.add_argument("--out", default=str(DEFAULT_METRICS), help="metrics.json used to seed signals")
    add_db_options(trade)
    trade.set_defaults(func=cmd_trade)

    run = sub.add_parser("run", help="collect + analyze + report (+ trade)")
    run.add_argument("--months", type=int, default=120)
    run.add_argument("--limit", type=int, default=0)
    run.add_argument("--out", default=str(DEFAULT_METRICS))
    run.add_argument("--out-dir", default=str(OUT_DIR))
    run.add_argument("--window-quarters", type=int, default=8)
    run.add_argument("--baseline-quarters", type=int, default=20)
    run.add_argument("--capital", type=float, default=100_000.0)
    run.add_argument("--kinds", default="all")
    run.add_argument("--skip-collect", action="store_true")
    run.add_argument("--skip-analyze", action="store_true")
    run.add_argument("--skip-report", action="store_true")
    run.add_argument("--with-trade", action="store_true", help="also run the paper-trading study")
    run.add_argument("--refresh-prices", action="store_true", help="re-download price bars even if cached")
    add_db_options(run)
    run.set_defaults(func=cmd_run)

    status = sub.add_parser("status", help="show what has been collected")
    status.add_argument("--db", default=str(DEFAULT_DB))
    status.set_defaults(func=cmd_status)

    selftest = sub.add_parser("selftest", help="run the offline test suite")
    selftest.set_defaults(func=cmd_selftest)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
