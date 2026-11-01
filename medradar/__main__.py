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

from .config import CACHE_DIR, DEFAULT_DB, DEFAULT_METRICS, DOCS_DIR, OUT_DIR


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
    "adcom": ("medradar.adcom", "collect"),
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
def _rewrite_published_links(path: Path) -> None:
    """Point the assumptions link at the sibling file after publishing.

    Generators write artefacts for ``out/``, where ``docs/ASSUMPTIONS.md`` is the
    correct relative path. Once copied into ``docs/`` the same link must become
    the sibling ``ASSUMPTIONS.md``. The old ``docs/docs/ASSUMPTIONS.md``
    duplicate only existed to paper over this; it has been removed (audit A3).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    updated = text.replace("../../docs/ASSUMPTIONS.md", "ASSUMPTIONS.md")
    updated = updated.replace("docs/ASSUMPTIONS.md", "ASSUMPTIONS.md")
    if updated != text:
        path.write_text(updated, encoding="utf-8")


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
    for name in ("report_zh.md", "report_en.md", "summary.csv", "index.html", "frontier.json", "frontier.md"):
        source = out_dir / name
        if source.exists():
            shutil.copyfile(source, DOCS_DIR / name)
            copied.append(name)
            if name.endswith((".html", ".md")):
                _rewrite_published_links(DOCS_DIR / name)
    metrics_source = Path(args.metrics)
    if metrics_source.exists():
        shutil.copyfile(metrics_source, DOCS_DIR / "metrics.json")
        copied.append("metrics.json")
    replay_html = out_dir / "replay" / "index.html"
    if replay_html.exists():
        shutil.copyfile(replay_html, DOCS_DIR / "replay.html")
        copied.append("replay.html")
        _rewrite_published_links(DOCS_DIR / "replay.html")
    return {"docs_dir": str(DOCS_DIR), "files": copied}


def _ship_assumptions(out_dir: Path, docs_dir: Path) -> list[str]:
    """Place ``ASSUMPTIONS.md`` where the report's relative links expect it.

    Report pages generated under ``out/`` link to ``docs/ASSUMPTIONS.md``; copying
    the register into ``out/docs`` and ``out/replay/docs`` keeps those offline
    links alive. Published copies in ``docs/`` are rewritten to the sibling
    ``ASSUMPTIONS.md`` by :func:`_rewrite_published_links`, so no
    ``docs/docs/ASSUMPTIONS.md`` duplicate is recreated.
    """
    import shutil

    from .config import ROOT
    from .util import ensure_dir

    source = ROOT / "docs" / "ASSUMPTIONS.md"
    if not source.is_file():
        return []
    copied: list[str] = []
    for base in (out_dir / "docs", out_dir / "replay" / "docs"):
        ensure_dir(base)
        shutil.copyfile(source, base / "ASSUMPTIONS.md")
        copied.append(str(base / "ASSUMPTIONS.md"))
    return copied


def cmd_report(args: argparse.Namespace) -> int:
    from .config import DOCS_DIR
    from .report import build_report

    result = build_report(metrics_path=args.metrics, out_dir=args.out_dir)
    result["published"] = _publish_docs(args)
    result["assumptions_copied"] = _ship_assumptions(Path(args.out_dir), Path(DOCS_DIR))
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


# ----------------------------------------------------------------------- frontier
def cmd_frontier(args: argparse.Namespace) -> int:
    from .db import DB
    from .frontier import build_frontier, write_frontier

    with DB(args.db) as db:
        payload = build_frontier(db, limit=args.limit)
    files = write_frontier(payload, args.out_dir)
    _emit({
        "status": payload.get("status"),
        "events": payload.get("summary", {}).get("events", 0),
        "domains": len(payload.get("summary", {}).get("by_domain") or []),
        "files": files,
        "pending_510k_pma_monitoring": False,
    })
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
    args.sources = "device,drug,trials,adcom,nmpa"
    # `run` names the metrics path --out; the individual sub-commands call it --metrics.
    args.metrics = args.out
    if not args.skip_collect:
        code = cmd_collect(args)
        if code != 0:
            print("[warn] some collectors failed; continuing with whatever data exists", file=sys.stderr)

    if not args.skip_analyze:
        cmd_analyze(args)

    # Trading and replay run before analyze so metrics.json can embed their output.
    if args.with_trade:
        prices = _ensure_prices(args)
        if prices.get("status") != "failed":
            _ingest_signals(args)
            cmd_trade(args)

    if args.with_replay:
        from datetime import date, timedelta

        end = date.today().isoformat()
        start = (date.today() - timedelta(days=args.replay_days)).isoformat()
        args.costs = args.replay_costs
        try:
            payload = _replay_payload(args, start, end)
            print(
                json.dumps(
                    {"replay": payload.get("status"), "files": payload.get("files")},
                    ensure_ascii=False,
                )
            )
        except Exception as exc:  # replay must never block the report
            print(f"[warn] replay failed: {type(exc).__name__}: {exc}", file=sys.stderr)

    if args.with_cases:
        try:
            from .cases import build_cases, write_cases
            from .db import DB

            with DB(args.db) as db:
                result = build_cases(db, max_cases=args.cases_limit)
            files = write_cases(result, Path(args.out_dir) / "cases")
            print(json.dumps({"cases": result.get("status"), "files": files}, ensure_ascii=False))
        except Exception as exc:
            print(f"[warn] cases failed: {type(exc).__name__}: {exc}", file=sys.stderr)

    if args.with_dashboard:
        try:
            from .dashboard import build_dashboard

            build_dashboard(
                metrics_path=args.metrics,
                cases_path=Path(args.out_dir) / "cases" / "cases.json",
                replay_path=Path(args.out_dir) / "replay" / "replay.json",
                out_path=DOCS_DIR / "dashboard.html",
            )
            print(json.dumps({"dashboard": "ok", "path": str(DOCS_DIR / "dashboard.html")}, ensure_ascii=False))
        except Exception as exc:
            print(f"[warn] dashboard failed: {type(exc).__name__}: {exc}", file=sys.stderr)

    if not args.skip_analyze:
        cmd_analyze(args)
        args.limit = args.limit or 500
        cmd_frontier(args)

    if not args.skip_report:
        cmd_report(args)
    return 0


# ------------------------------------------------------------------------- judge
def cmd_judge(args: argparse.Namespace) -> int:
    """Run the LLM judge on one filing text (manual inspection / calibration)."""
    from .db import DB
    from .llm import JudgeConfig, make_judge

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    elif args.url:
        from .config import CACHE_DIR
        from .http import Fetcher
        from .live import SEC_UA

        fetcher = Fetcher(cache_dir=CACHE_DIR, min_interval=0.4, max_requests=5, ua=SEC_UA)
        text = fetcher.get_text(args.url)
    else:
        text = sys.stdin.read()
    config = JudgeConfig.from_env()
    with DB(args.db) as db:
        judge = make_judge(db, use_llm=not args.no_llm, budget=args.llm_budget)
        verdict = judge.judge_filing(args.headline, text)
    _emit(
        {
            "headline": args.headline,
            "llm_configured": config.enabled,
            "model": config.model if config.enabled else "heuristic",
            "verdict": verdict,
            "input_chars": len(text),
        }
    )
    return 0


# -------------------------------------------------------------------------- live
def cmd_live(args: argparse.Namespace) -> int:
    import time as _time

    from .live import LiveParams, reset, run_once

    if args.reset:
        _emit(reset(args.db))
        return 0
    params = LiveParams(
        capital=args.capital,
        max_position=args.max_position,
        max_track=args.max_track,
        slippage_bps=args.slippage_bps,
        max_buys=args.max_buys,
        max_hold_days=args.max_hold_days,
        stop_loss=args.stop_loss,
        since_hours=args.since_hours,
        backfill_days=args.backfill_days,
        no_trade=args.no_trade,
        fetch_text=not args.no_text,
        use_llm=not args.no_llm,
        llm_budget=args.llm_budget,
        webhook=args.webhook,
    )
    if args.interval and not args.once:
        print(f"[live] loop every {args.interval}s, Ctrl+C to stop")
        while True:
            try:
                run_once(args.db, params)
            except KeyboardInterrupt:
                return 0
            except Exception as exc:
                print(f"[live] cycle failed: {type(exc).__name__}: {exc}")
            _time.sleep(args.interval)
    result = run_once(args.db, params)
    _emit(result)
    return 0


# -------------------------------------------------------------------- onboarding
def cmd_demo(args: argparse.Namespace) -> int:
    from .onboarding import run_demo

    result = run_demo(out_dir=args.out_dir, metrics_path=args.metrics)
    _emit(result)
    return 0 if result.get("status", "ok") in ("ok", "degraded") else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    from .onboarding import run_doctor

    report = run_doctor(
        config_dir=args.config_dir,
        home=args.home,
        network=not args.no_network,
    )
    _emit(report)
    return 0 if report.get("ok", True) else 1


def cmd_watchlist(args: argparse.Namespace) -> int:
    from .onboarding import watchlist_add, watchlist_list, watchlist_remove

    if args.remove:
        _emit(watchlist_remove(args.remove))
        return 0
    if args.add:
        _emit(
            watchlist_add(
                args.add,
                name_en=args.name_en,
                name_zh=args.name_zh,
                ticker=args.ticker,
                aliases=args.alias or None,
            )
        )
        return 0
    _emit({"companies": watchlist_list()})
    return 0


# ------------------------------------------------------------------------- replay
def _replay_payload(args: argparse.Namespace, start: str, end: str) -> dict:
    from .db import DB
    from .replay import build_replay

    costs = tuple(float(part) for part in str(args.costs or "10,25,50").split(",") if part.strip())
    out_dir = getattr(args, "out_dir", None)
    if out_dir:
        # `run --out-dir` points at the report directory; the replay artefacts
        # live in a `replay/` subfolder so they never overwrite out/index.html.
        candidate = Path(out_dir)
        out_dir = candidate if candidate.name == "replay" else candidate / "replay"
    with DB(args.db) as db:
        return build_replay(
            db,
            start,
            end,
            capital=args.capital,
            costs_bps=costs,
            intraday_days=getattr(args, "intraday_days", 7),
            out_dir=out_dir,
            offline=getattr(args, "offline", False),
            hold_days=getattr(args, "hold_days", 20),
            allow_short=getattr(args, "allow_short", False),
            max_requests=getattr(args, "budget", 60),
            source=getattr(args, "source", "auto"),
            max_steps=getattr(args, "max_steps", None),
            per_kind_limit=getattr(args, "per_kind_limit", 150),
        )


def cmd_replay(args: argparse.Namespace) -> int:
    from datetime import date, timedelta

    end = args.end or date.today().isoformat()
    start = args.start or (date.fromisoformat(end) - timedelta(days=args.days)).isoformat()
    payload = _replay_payload(args, start, end)
    _emit(
        {
            "status": payload.get("status"),
            "window": payload.get("window"),
            "files": payload.get("files"),
            "summary_by_cost": payload.get("summary_by_cost"),
            "skipped": payload.get("skipped"),
        }
    )
    return 0 if payload.get("status") != "failed" else 1


# ----------------------------------------------------------------------- products
def cmd_products(args: argparse.Namespace) -> int:
    import csv

    from .db import DB
    from .products import company_portfolio, family_stats, new_products

    with DB(args.db) as db:
        families = family_stats(db, window_quarters=args.window)
        news = new_products(db, days=args.news_days, max_items=args.news_limit)
        portfolio = company_portfolio(db, window_quarters=args.window)

    rows = families[: args.limit]
    if args.csv:
        target = Path(args.csv)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ["family_id", "name_zh", "name_en", "category", "recent", "thi", "prob_up",
                 "companies", "new_entrants_12m", "first_seen", "top_product"]
            )
            for row in families:
                writer.writerow(
                    [row.get("family_id"), row.get("name_zh"), row.get("name_en"), row.get("category"),
                     row.get("recent"), row.get("thi"), row.get("prob_up"), row.get("companies"),
                     row.get("new_entrants_12m"), row.get("first_seen"), row.get("top_product")]
                )
        print(json.dumps({"csv": str(target), "rows": len(families)}, ensure_ascii=False))
        return 0

    _emit(
        {
            "families": rows,
            "coverage": {"families": len(families)},
            "new_products": news[:20],
            "new_products_total": len(news),
            "companies": [
                {
                    "company_zh": value.get("name_zh"),
                    "recent": value.get("recent"),
                    "family_count": value.get("family_count"),
                    "js": value.get("js"),
                }
                for value in list(portfolio.values())[:20]
            ],
        }
    )
    return 0


# -------------------------------------------------------------------------- cases
def cmd_cases(args: argparse.Namespace) -> int:
    from .cases import (
        build_cases,
        cik_ticker_map,
        corpus_tickers,
        enrich_items,
        load_corpus,
        write_cases,
        write_corpus,
    )
    from .db import DB

    corpus_path = args.corpus
    if args.enrich:
        items = load_corpus(corpus_path)
        if items:
            enriched = enrich_items(items, cik_ticker_map())
            corpus_path = str(write_corpus(enriched, Path(args.out_dir or "out/cases") / "corpus_enriched.jsonl"))
            print(json.dumps({"enriched": len(enriched), "corpus": corpus_path}, ensure_ascii=False))

    tickers = corpus_tickers(corpus_path) if args.fetch_prices else []
    if tickers:
        from .config import CACHE_DIR
        from .http import Fetcher
        from .prices import fetch_prices

        with DB(args.db) as db:
            result = fetch_prices(
                db,
                Fetcher(cache_dir=CACHE_DIR, min_interval=0.5, max_requests=args.price_budget),
                tickers[: args.max_tickers],
            )
        print(json.dumps({"prices": {"ok": len(result.get("ok") or []), "failed": len(result.get("failed") or [])}}))

    with DB(args.db) as db:
        result = build_cases(
            db,
            corpus_path=corpus_path,
            max_cases=args.limit,
            benchmark=args.benchmark,
            per_company=getattr(args, "per_company", 3),
            per_month=getattr(args, "per_month", 8),
        )
    files = write_cases(result, args.out_dir or "out/cases")
    _emit(
        {
            "status": result.get("status"),
            "files": files,
            "stats": result.get("stats"),
            "selected": len(result.get("selected") or []),
            "negative_examples": len(result.get("negative_examples") or []),
        }
    )
    return 0 if result.get("status") == "ok" else 1


# -------------------------------------------------------------------------- audit
def cmd_audit(args: argparse.Namespace) -> int:
    from .audit import render_audit_markdown, run_audit
    from .db import DB
    from .util import write_text

    with DB(args.db) as db:
        audit = run_audit(db, stale_days=args.stale_days)
    if args.markdown:
        write_text(args.markdown, render_audit_markdown(audit))
    _emit(audit)
    return 0 if audit.get("status") != "fail" else 1


# -------------------------------------------------------------------------- stats
def cmd_stats(args: argparse.Namespace) -> int:
    from .db import DB
    from .stats_cmd import data_stats, update_stats_markdown

    with DB(args.db) as db:
        stats = data_stats(db)
    if args.markdown:
        update_stats_markdown(stats, args.markdown)
    _emit(stats)
    return 0


# ---------------------------------------------------------------------- dashboard
def cmd_dashboard(args: argparse.Namespace) -> int:
    from .dashboard import build_dashboard

    result = build_dashboard(
        metrics_path=args.metrics,
        cases_path=args.cases,
        replay_path=args.replay,
        out_path=args.out,
        audit_path=args.audit,
    )
    _emit(result)
    return 0 if result.get("status") == "ok" else 1


# ------------------------------------------------------------------------- corpus
def cmd_corpus(args: argparse.Namespace) -> int:
    from .cases import cik_ticker_map, enrich_items, load_corpus
    from .db import DB, make_event_id
    from .util import truncate, utc_now_iso

    items = load_corpus(args.path)
    if not items:
        _emit({"status": "missing", "path": args.path})
        return 1
    if args.enrich:
        items = enrich_items(items, cik_ticker_map())
    if not args.ingest:
        _emit({"status": "ok", "items": len(items), "sample": items[0] if items else None})
        return 0

    now = utc_now_iso()
    events = []
    for item in items:
        accession = str(item.get("accession") or "").strip()
        filed = str(item.get("filed") or "").strip()
        if not accession or not filed:
            continue
        events.append(
            {
                "event_id": make_event_id("sec_edgar_corpus", "8k_catalyst", accession),
                "source": "sec_edgar_corpus",
                "kind": "8k_catalyst",
                "event_date": filed,
                "published_at": filed,
                "available_at": filed,
                "timestamp_quality": "date",
                "company_key": item.get("company_key") or None,
                "applicant_raw": item.get("company") or "",
                "track_id": None,
                "title": truncate(item.get("headline") or item.get("company") or "", 300),
                "summary": truncate(item.get("text") or "", 400),
                "url": item.get("url") or item.get("fetch_url") or "",
                "payload": {
                    "category": item.get("category") or "",
                    "buckets": item.get("buckets") or [],
                    "cik": item.get("cik") or "",
                    "accession": accession,
                    "raw_chars": item.get("raw_chars") or 0,
                },
                "fetched_at": now,
            }
        )
    with DB(args.db) as db:
        written = db.upsert_events(events)
    _emit({"status": "ok", "ingested": written, "source": "sec_edgar_corpus"})
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
    collect.add_argument("--sources", default="device,drug,trials,adcom,nmpa")
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

    frontier = sub.add_parser("frontier", help="build the domain-aware pre-decision device intelligence feed")
    frontier.add_argument("--out-dir", default=str(OUT_DIR))
    frontier.add_argument("--limit", type=int, default=500)
    frontier.add_argument("--db", default=str(DEFAULT_DB))
    frontier.set_defaults(func=cmd_frontier)

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
    run.add_argument("--with-replay", action="store_true", help="also build the replay timeline")
    run.add_argument("--with-cases", action="store_true", help="also build the case library")
    run.add_argument("--with-dashboard", action="store_true", help="also build the interactive dashboard")
    run.add_argument("--cases-limit", type=int, default=120)
    run.add_argument("--replay-days", type=int, default=180)
    run.add_argument("--replay-costs", default="10,25,50")
    run.add_argument("--refresh-prices", action="store_true", help="re-download price bars even if cached")
    add_db_options(run)
    run.set_defaults(func=cmd_run)

    status = sub.add_parser("status", help="show what has been collected")
    status.add_argument("--db", default=str(DEFAULT_DB))
    status.set_defaults(func=cmd_status)

    demo = sub.add_parser("demo", help="offline demo report from the committed snapshot")
    demo.add_argument("--out-dir", default=None)
    demo.add_argument("--metrics", default=None, help="snapshot metrics.json (default: docs/metrics.json)")
    demo.set_defaults(func=cmd_demo)

    doctor = sub.add_parser("doctor", help="environment self-check (config, data dir, DB, network)")
    doctor.add_argument("--no-network", action="store_true")
    doctor.add_argument("--offline", action="store_true", help="alias for --no-network")
    doctor.add_argument("--config-dir", default=None)
    doctor.add_argument("--home", default=None)
    doctor.set_defaults(func=cmd_doctor)

    watch = sub.add_parser("watchlist", help="manage the device watchlist without editing JSON")
    group = watch.add_mutually_exclusive_group()
    group.add_argument("--add", metavar="KEY", default=None)
    group.add_argument("--remove", metavar="KEY", default=None)
    watch.add_argument("--name-en", default=None)
    watch.add_argument("--name-zh", default=None)
    watch.add_argument("--ticker", default=None)
    watch.add_argument("--alias", action="append", default=None)
    watch.set_defaults(func=cmd_watchlist)

    live = sub.add_parser("live", help="event alerts + simulated real-time US paper trading")
    live.add_argument("--db", default=str(DEFAULT_DB))
    live.add_argument("--once", action="store_true", help="run exactly one cycle (cron mode)")
    live.add_argument("--interval", type=int, default=0, help="seconds between cycles (0 = one cycle)")
    live.add_argument("--since-hours", type=float, default=24.0, help="first poll look-back window")
    live.add_argument("--backfill-days", type=float, default=0.0, help="seed alerts from EDGAR full-text search (never traded)")
    live.add_argument("--capital", type=float, default=100_000.0)
    live.add_argument("--max-position", type=float, default=0.05, help="max fraction of equity per name")
    live.add_argument("--max-track", type=float, default=0.25, help="max fraction of equity per track")
    live.add_argument("--slippage-bps", type=float, default=10.0)
    live.add_argument("--max-buys", type=int, default=5, help="new positions per cycle")
    live.add_argument("--max-hold-days", type=int, default=84)
    live.add_argument("--stop-loss", type=float, default=-0.20)
    live.add_argument("--no-trade", action="store_true", help="alerts only, no simulated orders")
    live.add_argument("--no-text", action="store_true", help="skip fetching 8-K full text")
    live.add_argument("--no-llm", action="store_true", help="use the keyword judge only")
    live.add_argument("--llm-budget", type=int, default=4, help="max LLM calls per cycle")
    live.add_argument("--webhook", default=None, help="POST each cycle summary to this URL")
    live.add_argument("--reset", action="store_true", help="wipe the simulated book and exit")
    live.set_defaults(func=cmd_live)

    judge = sub.add_parser("judge", help="score one 8-K filing text with the LLM judge")
    judge.add_argument("--file", default=None, help="path to filing text/HTML")
    judge.add_argument("--url", default=None, help="fetch the filing text from a URL")
    judge.add_argument("--headline", default="8-K filing")
    judge.add_argument("--db", default=str(DEFAULT_DB))
    judge.add_argument("--no-llm", action="store_true")
    judge.add_argument("--llm-budget", type=int, default=1)
    judge.set_defaults(func=cmd_judge)

    replay = sub.add_parser("replay", help="build the event-to-fill replay timeline")
    replay.add_argument("--start", default=None)
    replay.add_argument("--end", default=None)
    replay.add_argument("--days", type=int, default=30)
    replay.add_argument("--capital", type=float, default=100_000.0)
    replay.add_argument("--costs", default="10,25,50", help="comma separated bps tiers")
    replay.add_argument("--hold-days", type=int, default=20)
    replay.add_argument("--allow-short", action="store_true")
    replay.add_argument("--source", choices=["auto", "signals", "events"], default="auto")
    replay.add_argument("--max-steps", type=int, default=None)
    replay.add_argument("--per-kind-limit", type=int, default=150)
    replay.add_argument("--offline", action="store_true", help="use cached bars only")
    replay.add_argument("--out-dir", default=None)
    replay.add_argument("--db", default=str(DEFAULT_DB))
    replay.add_argument("--budget", type=int, default=60)
    replay.set_defaults(func=cmd_replay)

    products = sub.add_parser("products", help="product-family intelligence for medical devices")
    products.add_argument("--db", default=str(DEFAULT_DB))
    products.add_argument("--window", type=int, default=8, help="window in quarters")
    products.add_argument("--limit", type=int, default=25)
    products.add_argument("--news-days", type=int, default=90)
    products.add_argument("--news-limit", type=int, default=100)
    products.add_argument("--csv", default=None, help="export the full family table to this CSV")
    products.set_defaults(func=cmd_products)

    cases = sub.add_parser("cases", help="build the traceable case library from the EDGAR corpus")
    cases.add_argument("--db", default=str(DEFAULT_DB))
    cases.add_argument("--corpus", default=None, help="path to corpus.jsonl")
    cases.add_argument("--enrich", action="store_true", help="fill ticker/category from CIK and bucket")
    cases.add_argument("--limit", type=int, default=120)
    cases.add_argument("--benchmark", default="SPY")
    cases.add_argument("--out-dir", default=None)
    cases.add_argument("--fetch-prices", action="store_true", help="download daily bars for corpus tickers")
    cases.add_argument("--max-tickers", type=int, default=150)
    cases.add_argument("--price-budget", type=int, default=200)
    cases.add_argument("--per-company", type=int, default=3, help="max cases per ticker")
    cases.add_argument("--per-month", type=int, default=8, help="max cases per calendar month")
    cases.set_defaults(func=cmd_cases)

    corpus = sub.add_parser("corpus", help="inspect or ingest the EDGAR historical catalyst corpus")
    corpus.add_argument("--path", default="data/edgar_corpus/corpus.jsonl")
    corpus.add_argument("--enrich", action="store_true", help="fill ticker/category/company_key")
    corpus.add_argument("--ingest", action="store_true", help="write corpus filings into the events table")
    corpus.add_argument("--db", default=str(DEFAULT_DB))
    corpus.set_defaults(func=cmd_corpus)

    dashboard = sub.add_parser("dashboard", help="build the interactive zero-dependency dashboard")
    dashboard.add_argument("--metrics", default=str(OUT_DIR / "metrics.json"))
    dashboard.add_argument("--cases", default=str(OUT_DIR / "cases" / "cases.json"))
    dashboard.add_argument("--replay", default=str(OUT_DIR / "replay" / "replay.json"))
    dashboard.add_argument("--out", default=str(DOCS_DIR / "dashboard.html"))
    dashboard.add_argument("--audit", default=None)
    dashboard.set_defaults(func=cmd_dashboard)

    audit = sub.add_parser("audit", help="data-quality audit (dates, matches, prices, freshness)")
    audit.add_argument("--db", default=str(DEFAULT_DB))
    audit.add_argument("--stale-days", type=int, default=30)
    audit.add_argument("--markdown", default=None, help="also write a Markdown report")
    audit.set_defaults(func=cmd_audit)

    stats = sub.add_parser("stats", help="dataset scale and distribution report")
    stats.add_argument("--db", default=str(DEFAULT_DB))
    stats.add_argument("--markdown", default=None, help="update the generated block in this Markdown file")
    stats.set_defaults(func=cmd_stats)

    selftest = sub.add_parser("selftest", help="run the offline test suite")
    selftest.set_defaults(func=cmd_selftest)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "offline", False):
        args.no_network = True
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
