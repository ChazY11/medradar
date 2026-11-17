"""Operator CLI: ``python -m medradar radar <command>``.

Every command reports what it actually did. ``run`` prints the per-source outcome including
"no change", which is a real result; ``status`` prints measured values and explicit unknowns;
``verify`` fails loudly on an integrity problem instead of printing a green light.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .engine import advance, ingest
from .graph import open_graph
from .health import detection_latency, source_status, system_status
from .ledger import ObservationLedger
from .paths import radar_paths
from .records import PHASE_LABELS_EN
from .scheduler import RadarScheduler, build_fetcher
from .taxonomy import TaxonomyError, load_taxonomy


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _table(rows: list[list[str]], header: list[str]) -> str:
    widths = [len(item) for item in header]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    lines = ["  ".join(str(cell).ljust(widths[index]) for index, cell in enumerate(header))]
    lines.append("  ".join("-" * width for width in widths))
    for row in rows:
        lines.append("  ".join(str(cell).ljust(widths[index]) for index, cell in enumerate(row)))
    return "\n".join(lines)


def _open(args) -> tuple[Any, ObservationLedger, Any]:
    taxonomy = load_taxonomy()
    paths = radar_paths(args.data_dir).ensure()
    ledger = ObservationLedger(paths.ledger)
    graph = open_graph(paths.graph, taxonomy)
    return paths, ledger, graph


# ---------------------------------------------------------------------- commands
def cmd_init(args) -> int:
    taxonomy = load_taxonomy()
    paths = radar_paths(args.data_dir).ensure()
    ledger = ObservationLedger(paths.ledger)
    from .graph import open_graph as _open

    graph = _open(paths.graph, taxonomy)
    print(f"radar data directory : {paths.root}")
    print(f"observation ledger   : {paths.ledger}")
    print(f"technology graph     : {paths.graph}")
    print(f"taxonomy             : {taxonomy.version} (fingerprint {taxonomy.fingerprint[:16]})")
    print(f"topics               : {len(taxonomy.topics)}")
    print(f"organizations        : {', '.join(org.id for org in taxonomy.organizations)}")
    rows = []
    for source in taxonomy.sources():
        access = (source.get("access") or {})
        rows.append([
            source.get("id"), "yes" if source.get("enabled") else "no",
            access.get("verification"), str(source.get("cadence_hours")),
        ])
    print()
    print(_table(rows, ["source", "enabled", "access", "cadence_h"]))
    print()
    print("A disabled source is listed on purpose: 'not monitored' must be distinguishable")
    print("from 'nothing found'.")
    graph.store.close()
    ledger.close()
    return 0


def cmd_run(args) -> int:
    taxonomy = load_taxonomy()
    paths, ledger, graph = _open(args)
    try:
        from .adapters import build_adapters

        sources = args.source.split(",") if args.source else None
        adapters = build_adapters(taxonomy, sources)
        fetcher = build_fetcher(taxonomy, max_requests=args.max_requests)
        report = ingest(adapters, ledger, taxonomy, fetcher=fetcher, trigger="cli",
                        limit=args.limit, dry_run=args.dry_run, log=print)
        print()
        rows = []
        for item in report.sources:
            counters = item.get("counters") or {}
            rows.append([
                item.get("source"), item.get("status"), item.get("outcome") or "",
                counters.get("records_new", 0), counters.get("records_updated", 0),
                counters.get("records_unchanged", 0), counters.get("records_failed", 0),
                counters.get("requests", 0),
            ])
        print(_table(rows, ["source", "status", "outcome", "new", "upd", "same", "fail", "req"]))
        print()
        print(report.as_dict()["statement"])
        if args.dry_run:
            print("(dry run: nothing was written)")
            return 0
        advanced = advance(ledger, graph, taxonomy, log=print)
        print()
        print("pipeline: " + json.dumps(advanced, ensure_ascii=False))
        if args.json:
            _print_json({"ingest": report.as_dict(), "advance": advanced})
        return 0
    finally:
        graph.store.close()
        ledger.close()


def cmd_advance(args) -> int:
    taxonomy = load_taxonomy()
    paths, ledger, graph = _open(args)
    try:
        result = advance(ledger, graph, taxonomy, limit=args.limit, log=print)
        _print_json(result)
        return 0
    finally:
        graph.store.close()
        ledger.close()


def cmd_status(args) -> int:
    taxonomy = load_taxonomy()
    paths = radar_paths(args.data_dir)
    if not paths.ledger.is_file():
        print(f"No radar ledger at {paths.ledger}. Run: python -m medradar radar run")
        return 1
    ledger = ObservationLedger(paths.ledger, create=False, read_only=True)
    graph = open_graph(paths.graph, taxonomy) if paths.graph.is_file() else None
    try:
        payload = system_status(ledger, graph, taxonomy, data_dir=str(paths.root))
    finally:
        ledger.close()
        if graph is not None:
            graph.store.close()
    if args.json:
        _print_json(payload)
        return 0
    print(f"state          : {payload['state']}")
    counts = payload["counts"]
    print(f"observations   : {counts['observations']} ({counts['versions']} versions, "
          f"{counts['change_events']} change events)")
    queue = payload["backlog"]
    print(f"ai backlog     : {queue['backlog']} pending / {queue['running']} running")
    resources = payload["resources"]
    print(f"memory avail   : {resources['available_mb']} MB of {resources['total_mb']} MB "
          f"({resources['cpus']} cpus)")
    print()
    rows = []
    for source in payload["sources"]:
        latency = source["detection_latency"]
        rows.append([
            source["source_id"], source["status"], source["access_state"],
            source["last_checked_at"] or "never",
            source["last_observed_update_at"] or "-",
            source["watermark"] or "-", source["consecutive_failures"],
            source["backlog"], latency["exact_median_hours"] if latency["exact_median_hours"] is not None else "-",
        ])
    print(_table(rows, ["source", "status", "access", "last_checked", "last_update",
                        "watermark", "fails", "backlog", "latency_h"]))
    if payload.get("graph"):
        graph_info = payload["graph"]
        print()
        print(f"graph          : {graph_info['nodes']} nodes, {graph_info['edges']} edges "
              f"({graph_info['graph_version']}, taxonomy {graph_info['taxonomy_version']})")
    if payload["blocked_sources"]:
        print()
        print("Blocked sources: " + ", ".join(payload["blocked_sources"]))
        print(payload.get("blocked_explanation", ""))
    consistency = payload["consistency"]
    print()
    print("integrity      : " + ("ok" if consistency["ok"] else json.dumps(consistency["problems"])))
    return 0


def cmd_feed(args) -> int:
    paths = radar_paths(args.data_dir)
    if not paths.ledger.is_file():
        print(f"No radar ledger at {paths.ledger}. Run: python -m medradar radar run")
        return 1
    ledger = ObservationLedger(paths.ledger, create=False, read_only=True)
    try:
        rows, total = ledger.feed(
            limit=args.limit,
            sources=args.source.split(",") if args.source else None,
            organizations=args.organization.split(",") if args.organization else None,
            topics=args.topic.split(",") if args.topic else None,
        )
    finally:
        ledger.close()
    if args.json:
        _print_json({"total": total, "items": rows})
        return 0
    print(f"{total} observation(s); showing {len(rows)}")
    for row in rows:
        topics = ",".join(candidate["value"] for candidate in row["facets"].get("topic", [])) or "-"
        orgs = ",".join(candidate["value"] for candidate in row["facets"].get("organization", [])) or "-"
        print(f"- [{row['source']}] {row['title'][:88]}")
        print(f"    change={row['current_change_state']} phase={PHASE_LABELS_EN.get(row['discovery_phase'], row['discovery_phase'])}")
        print(f"    published={row['published_at'] or row['event_at'] or 'unknown'} "
              f"first_observed={row['first_observed_at']}")
        print(f"    orgs={orgs} topics={topics}")
        print(f"    evidence={row['source_url']}")
    return 0


def cmd_map(args) -> int:
    taxonomy = load_taxonomy()
    paths = radar_paths(args.data_dir)
    if not paths.graph.is_file():
        print(f"No technology graph at {paths.graph}. Run: python -m medradar radar advance")
        return 1
    graph = open_graph(paths.graph, taxonomy)
    try:
        known_at, valid_at = (args.at, None) if args.mode == "knowledge" else (None, args.at)
        payload = graph.technology_map(
            companies=args.company.split(",") if args.company else None,
            known_at=known_at, valid_at=valid_at,
        )
    finally:
        graph.store.close()
    if args.json:
        _print_json(payload)
        return 0
    print(f"mode: {payload['mode']}  known_at={payload['known_at']}  valid_at={payload['valid_at']}")
    print(payload["time_semantics"]["statement"])
    print()
    if not payload["topics"]:
        print("No technology branch has evidence in this view.")
        print("That is an evidence statement, not a capability statement.")
        return 0
    for topic in payload["topics"]:
        print(f"* {topic['topic_id']}  [{topic['family']}]  {topic['label_en']}")
        for company in topic["companies"]:
            products = ", ".join(product["name"] for product in company["products"][:3]) or "-"
            print(f"    {company['display_name']:<16} products={len(company['products'])} "
                  f"evidence={len(company['evidence'])} earliest={company['earliest_evidence'] or '-'}")
            print(f"        {products[:110]}")
    return 0


def cmd_compare(args) -> int:
    taxonomy = load_taxonomy()
    paths = radar_paths(args.data_dir)
    if not paths.graph.is_file():
        print(f"No technology graph at {paths.graph}. Run: python -m medradar radar advance")
        return 1
    graph = open_graph(paths.graph, taxonomy)
    try:
        known_at, valid_at = (args.at, None) if args.mode == "knowledge" else (None, args.at)
        payload = graph.company_compare(
            companies=args.company.split(",") if args.company else None,
            known_at=known_at, valid_at=valid_at,
        )
    finally:
        graph.store.close()
    if args.json:
        _print_json(payload)
        return 0
    companies = [cell["display_name"] for cell in payload["rows"][0]["cells"]] if payload["rows"] else []
    print(f"mode: {payload['mode']}  companies: {', '.join(companies)}")
    print()
    header = ["topic"] + companies
    rows = []
    for row in payload["rows"]:
        cells = []
        for cell in row["cells"]:
            cells.append(
                f"{cell['state'][:12]} c{cell['reported_capability_evidence']} "
                f"r{cell['regulatory_topic_evidence']} p{cell['publication_topic_evidence']}"
            )
        rows.append([row["topic_id"]] + cells)
    print(_table(rows, header))
    print()
    print("c = official reported capability, r = regulatory records, p = affiliated publications")
    print(payload["no_evidence_means"])
    print(payload["not_comparable_warning"])
    return 0


def cmd_backup(args) -> int:
    from .backup import backup

    paths = radar_paths(args.data_dir)
    result = backup(paths, destination=args.destination, keep=args.keep, log=print)
    if args.json:
        _print_json(result.as_dict())
    return 0 if result.manifest.get("verified") else 2


def cmd_restore_check(args) -> int:
    from .backup import restore_check

    report = restore_check(backup_path=args.backup, work_dir=args.work_dir,
                           rebuild_graph=not args.no_graph, log=print)
    if args.json:
        _print_json(report)
    return 0 if report["ok"] else 2


def cmd_rebuild_graph(args) -> int:
    """Rebuild graph.db from radar.db into a new file, then swap it in atomically.

    Deleting the derived graph is never deleting intelligence: the observation ledger is the
    record, and this command proves the graph is a projection of it.
    """
    import os

    taxonomy = load_taxonomy()
    paths = radar_paths(args.data_dir)
    if not paths.ledger.is_file():
        print(f"No radar ledger at {paths.ledger}")
        return 1
    staged = paths.root / "graph.db.rebuild"
    if staged.exists():
        staged.unlink()
    graph = open_graph(staged, taxonomy)
    ledger = ObservationLedger(paths.ledger, create=False)
    try:
        step = graph.materialize(ledger, limit=args.limit, log=print)
        summary = graph.summary()
    finally:
        ledger.close()
        graph.store.close()
    if paths.graph.exists():
        os.replace(paths.graph, paths.root / "graph.db.previous")
    os.replace(staged, paths.graph)
    payload = {"materialized": step, "nodes": summary["nodes"], "edges": summary["edges"],
               "graph": str(paths.graph)}
    if args.json:
        _print_json(payload)
    else:
        print(f"rebuilt {paths.graph}: {summary['nodes']} nodes / {summary['edges']} edges")
    return 0


def cmd_watch(args) -> int:
    taxonomy = load_taxonomy()
    paths, ledger, graph = _open(args)
    scheduler = RadarScheduler(paths, ledger, graph, taxonomy,
                               sources=args.source.split(",") if args.source else None,
                               ai_enabled=not args.no_ai)
    try:
        result = scheduler.watch(interval_seconds=args.interval, max_cycles=args.cycles)
    finally:
        graph.store.close()
        ledger.close()
    print(json.dumps({"cycles": result["cycles"], "stopped": result["stopped"]}, indent=2))
    return 0


def cmd_verify(args) -> int:
    taxonomy = load_taxonomy()
    paths = radar_paths(args.data_dir)
    if not paths.ledger.is_file():
        print(f"No radar ledger at {paths.ledger}")
        return 1
    ledger = ObservationLedger(paths.ledger, create=False, read_only=True)
    try:
        consistency = ledger.consistency_check()
        latency = detection_latency(ledger)
        counts = ledger.counts().__dict__ if hasattr(ledger.counts(), "__dict__") else {}
    finally:
        ledger.close()
    graph_info = None
    if paths.graph.is_file():
        graph = open_graph(paths.graph, taxonomy)
        try:
            graph_info = graph.summary()
        finally:
            graph.store.close()
    payload = {"consistency": consistency, "latency": latency, "counts": counts,
               "graph": graph_info}
    if args.json:
        _print_json(payload)
    else:
        print("integrity: " + ("OK" if consistency["ok"] else "FAILED"))
        for problem in consistency["problems"]:
            print(f"  - {problem}")
        print(f"counts: {consistency['counts']}")
        print(f"latency exact median: {latency['exact_median_hours']} h "
              f"({latency['exact_samples']} exact samples, {latency['approximate_samples']} approximate)")
        if graph_info:
            print(f"graph: {graph_info['nodes']} nodes / {graph_info['edges']} edges")
            print(f"confirmations: {graph_info['confirmations']}")
    return 0 if consistency["ok"] else 2


def cmd_ai(args) -> int:
    from . import ai as ai_package

    taxonomy = load_taxonomy()
    paths = radar_paths(args.data_dir)
    if args.action == "status":
        ledger = ObservationLedger(paths.ledger, create=False, read_only=True) if paths.ledger.is_file() else None
        if ledger is None:
            print("No radar ledger yet.")
            return 1
        try:
            payload = {
                "queue": ledger.queue_summary(),
                "ai_state": ledger.get_runtime("ai_state", {}),
                "candidates": ledger.ai_stats(),
                "model_path": str(ai_package.default_model_path() or "not found"),
            }
        finally:
            ledger.close()
        _print_json(payload)
        return 0
    if args.action == "candidates":
        ledger = ObservationLedger(paths.ledger, create=False, read_only=True)
        try:
            from .ai.evaluate import build_candidate_set

            _print_json(build_candidate_set(ledger, limit=args.limit))
        finally:
            ledger.close()
        return 0
    if args.action == "run":
        ledger = ObservationLedger(paths.ledger)
        try:
            result = ai_package.run_batch(ledger, taxonomy, limit=args.limit, model_path=args.model)
            ledger.set_runtime("ai_state", result)
        finally:
            ledger.close()
        _print_json({key: value for key, value in result.items() if key != "results"})
        return 0
    if args.action == "eval":
        ledger = ObservationLedger(paths.ledger, create=False, read_only=True)
        try:
            from .ai.evaluate import load_eval_set, run_evaluation

            eval_path = args.eval_set or str(Path(__file__).resolve().parents[2] /
                                             "config" / "radar" / "ai_eval_set.json")
            report = run_evaluation(ledger, taxonomy, load_eval_set(eval_path), model_path=args.model)
        finally:
            ledger.close()
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                      encoding="utf-8")
            print(f"wrote {args.out}")
        _print_json({key: value for key, value in report.items() if key != "items"})
        return 0
    raise SystemExit(f"unknown ai action {args.action!r}")


def cmd_export(args) -> int:
    taxonomy = load_taxonomy()
    paths = radar_paths(args.data_dir)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"generated_at": None, "root": str(paths.root)}
    if paths.graph.is_file():
        graph = open_graph(paths.graph, taxonomy)
        try:
            payload["technology_map"] = graph.technology_map()
            payload["compare"] = graph.company_compare()
            payload["graph_summary"] = graph.summary()
        finally:
            graph.store.close()
    if paths.ledger.is_file():
        ledger = ObservationLedger(paths.ledger, create=False, read_only=True)
        try:
            rows, total = ledger.feed(limit=args.limit)
            payload["feed"] = {"total": total, "items": rows}
            payload["health"] = system_status(ledger, None, taxonomy)
        finally:
            ledger.close()
    import datetime

    payload["generated_at"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    target = output / "radar_export.json"
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
                      encoding="utf-8")
    print(f"wrote {target}")
    return 0


# ------------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="medradar radar",
                                     description="RADAR-001 live intelligence and technology graph.")
    parser.add_argument("--data-dir", default=None, help="radar data directory")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create the radar store and print the active registry")
    init.set_defaults(func=cmd_init)

    run = sub.add_parser("run", help="perform a real incremental check of the sources")
    run.add_argument("--source", default=None, help="comma-separated source ids")
    run.add_argument("--limit", type=int, default=0)
    run.add_argument("--max-requests", type=int, default=400)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)

    adv = sub.add_parser("advance", help="resolve, link and publish pending observations")
    adv.add_argument("--limit", type=int, default=400)
    adv.set_defaults(func=cmd_advance)

    status = sub.add_parser("status", help="source status, latency, backlog and integrity")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    feed = sub.add_parser("feed", help="print the latest intelligence events")
    feed.add_argument("--limit", type=int, default=10)
    feed.add_argument("--source", default=None)
    feed.add_argument("--organization", default=None)
    feed.add_argument("--topic", default=None)
    feed.add_argument("--json", action="store_true")
    feed.set_defaults(func=cmd_feed)

    techmap = sub.add_parser("map", help="print the company technology tree")
    techmap.add_argument("--company", default=None)
    techmap.add_argument("--mode", choices=["public", "knowledge"], default="public")
    techmap.add_argument("--at", default=None)
    techmap.add_argument("--json", action="store_true")
    techmap.set_defaults(func=cmd_map)

    compare = sub.add_parser("compare", help="compare evidence coverage across companies")
    compare.add_argument("--company", default=None)
    compare.add_argument("--mode", choices=["public", "knowledge"], default="public")
    compare.add_argument("--at", default=None)
    compare.add_argument("--json", action="store_true")
    compare.set_defaults(func=cmd_compare)

    watch = sub.add_parser("watch", help="run the scheduler loop")
    watch.add_argument("--interval", type=float, default=300.0)
    watch.add_argument("--cycles", type=int, default=None)
    watch.add_argument("--source", default=None)
    watch.add_argument("--no-ai", action="store_true")
    watch.set_defaults(func=cmd_watch)

    backup_cmd = sub.add_parser("backup", help="consistent online backup of radar.db, verified")
    backup_cmd.add_argument("--destination", default=None)
    backup_cmd.add_argument("--keep", type=int, default=14)
    backup_cmd.add_argument("--json", action="store_true")
    backup_cmd.set_defaults(func=cmd_backup)

    restore = sub.add_parser("restore-check",
                             help="restore a backup into an isolated directory and rebuild the graph")
    restore.add_argument("--backup", required=True)
    restore.add_argument("--work-dir", required=True)
    restore.add_argument("--no-graph", action="store_true")
    restore.add_argument("--json", action="store_true")
    restore.set_defaults(func=cmd_restore_check)

    rebuild = sub.add_parser("rebuild-graph", help="rebuild graph.db from radar.db atomically")
    rebuild.add_argument("--limit", type=int, default=5000)
    rebuild.add_argument("--json", action="store_true")
    rebuild.set_defaults(func=cmd_rebuild_graph)

    verify = sub.add_parser("verify", help="integrity, latency and graph audit")
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(func=cmd_verify)

    ai = sub.add_parser("ai", help="local enrichment worker")
    ai.add_argument("action", choices=["run", "status", "eval", "candidates"])
    ai.add_argument("--limit", type=int, default=8)
    ai.add_argument("--model", default=None)
    ai.add_argument("--eval-set", default=None)
    ai.add_argument("--out", default=None)
    ai.set_defaults(func=cmd_ai)

    export = sub.add_parser("export", help="export a JSON snapshot for review")
    export.add_argument("--out", default="out/radar")
    export.add_argument("--limit", type=int, default=100)
    export.set_defaults(func=cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except TaxonomyError as error:
        print(f"radar configuration error: {error}", file=sys.stderr)
        return 2
    except FileNotFoundError as error:
        print(f"radar data error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
