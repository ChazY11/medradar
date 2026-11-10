"""ATLAS command-line interface.

Every command prints deterministic JSON to stdout, so a shell pipeline or an
independent verifier can consume the same output a human reads.

Examples
--------
``python -m medradar.atlas init``
``python -m medradar.atlas pilot --fda-per-firm 100``
``python -m medradar.atlas quality --write-report``
``python -m medradar.atlas graph build``
``python -m medradar.atlas query company --key medtronic``
``python -m medradar.atlas query path --key medtronic``
``python -m medradar.atlas as-of --at 2026-11-01T00:00:00Z --basis observed``
``python -m medradar.atlas prospective list``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__, config
from .db import SCHEMA_VERSION, current_version, migrate
from .graph import (
    build_source_declared_relations,
    company_devices,
    device_identity,
    device_research_candidates,
    evidence_path,
    rejected_relations,
    relation_evidence,
    technology_companies,
)
from .identity.pilot import PilotConfig, run_pilot
from .quality import run_checks
from .research import (
    as_of,
    candidate_summary,
    evidence_history,
    register_cross_market_candidates,
)
from .store import AtlasStore


def _emit(payload: Any, *, out: str = "") -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        print(json.dumps({"written": str(path), "schema": payload.get("schema") if isinstance(payload, dict) else None}))
    else:
        print(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="medradar.atlas", description=__doc__)
    parser.add_argument("--db", default="", help="ATLAS database path (default: research/atlas/staging/atlas.sqlite)")
    parser.add_argument("--version", action="version", version=f"medradar.atlas {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="create/migrate the ATLAS database")
    p_init.add_argument("--out", default="")

    p_pilot = sub.add_parser("pilot", help="run the bounded cross-source identity pilot")
    for name, default, help_text in (
        ("fda-per-firm", 100, "openFDA UDI records per firm"),
        ("accessgudid-sample", 12, "AccessGUDID re-reads"),
        ("k510-limit", 50, "510(k) records per firm"),
        ("mdall-gtin-limit", 6000, "MDALL GTIN-14 rows to retain"),
        ("mdall-bridge-limit", 1200, "MDALL DIs to resolve against openFDA"),
        ("mdall-licence-limit", 40, "MDALL licences to detail"),
        ("pair-sample", 250, "same-firm pairs per firm"),
    ):
        p_pilot.add_argument(f"--{name}", type=int, default=default, help=help_text)
    p_pilot.add_argument("--no-network", action="store_true", help="offline mode: every request is refused and recorded")
    p_pilot.add_argument("--out", default="")

    p_quality = sub.add_parser("quality", help="run data-quality checks")
    p_quality.add_argument("--write-report", action="store_true")
    p_quality.add_argument("--out", default="")

    p_graph = sub.add_parser("graph", help="graph build/query operations")
    graph_sub = p_graph.add_subparsers(dest="graph_command", required=True)
    p_build = graph_sub.add_parser("build", help="create source-declared graph relations")
    p_build.add_argument("--out", default="")

    p_query = sub.add_parser("query", help="run an evidence-bearing query")
    query_sub = p_query.add_subparsers(dest="query_command", required=True)
    for name, help_text in (
        ("company", "company -> evidence-backed devices"),
        ("device", "device -> identifiers, relations and evidence"),
        ("path", "company -> device -> official identity -> regulatory record"),
        ("tech", "FDA product code -> companies"),
        ("relation", "one relation -> evidence and history"),
        ("rejections", "rejected relations with reasons"),
        ("research", "device -> research candidates (honest empty default)"),
    ):
        p = query_sub.add_parser(name, help=help_text)
        p.add_argument(
            "--key", required=(name != "rejections"),
            help="company key, device ref, product code or relation id",
        )
        p.add_argument("--limit", type=int, default=20)
        p.add_argument("--out", default="")

    p_asof = sub.add_parser("as-of", help="historical-state query")
    p_asof.add_argument("--at", required=True)
    p_asof.add_argument("--basis", choices=["observed", "public_inferred"], default="observed")
    p_asof.add_argument("--out", default="")

    p_history = sub.add_parser("history", help="append-only evidence history")
    p_history.add_argument("--evidence-id", required=True)
    p_history.add_argument("--out", default="")

    p_pro = sub.add_parser("prospective", help="prospective candidate registry")
    pro_sub = p_pro.add_subparsers(dest="prospective_command", required=True)
    p_reg = pro_sub.add_parser("register", help="register single-market candidates")
    p_reg.add_argument("--limit", type=int, default=500)
    p_reg.add_argument("--out", default="")
    p_list = pro_sub.add_parser("list", help="list registered candidates")
    p_list.add_argument("--out", default="")

    p_sources = sub.add_parser("sources", help="source register and access posture")
    p_sources.add_argument("--out", default="")

    p_stats = sub.add_parser("stats", help="database statistics")
    p_stats.add_argument("--out", default="")
    return parser


def _store(args: argparse.Namespace) -> AtlasStore:
    path = Path(args.db) if args.db else config.DEFAULT_DB
    return AtlasStore(path)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config.ensure_dirs()

    if args.command == "init":
        path = Path(args.db) if args.db else config.DEFAULT_DB
        report = migrate(path)
        report["schema_target"] = SCHEMA_VERSION
        report["schema_current"] = current_version(path)
        _emit(report, out=args.out)
        return 0

    if args.command == "sources":
        sources = config.load_sources()
        _emit(
            {
                "schema": "medradar.atlas.sources_view.v1",
                "count": len(sources),
                "verified": sorted(k for k, v in sources.items() if str(v.get("verified_status", "")).startswith("VERIFIED")),
                "not_tested": sorted(k for k, v in sources.items() if v.get("verified_status") == "NOT_TESTED_IN_ATLAS_001"),
                "needs_project_owner": sorted(k for k, v in sources.items() if v.get("verified_status") == "REQUIRES_REGISTRATION"),
                "sources": sources,
            },
            out=args.out,
        )
        return 0

    with _store(args) as store:
        if args.command == "pilot":
            cfg = PilotConfig(
                fda_per_firm=args.fda_per_firm,
                accessgudid_sample=args.accessgudid_sample,
                k510_limit_per_firm=args.k510_limit,
                mdall_gtin_limit=args.mdall_gtin_limit,
                mdall_bridge_limit=args.mdall_bridge_limit,
                mdall_licence_limit=args.mdall_licence_limit,
                pair_sample_per_firm=args.pair_sample,
                allow_network=not args.no_network,
            )
            report = run_pilot(db_path=store.path, cfg=cfg)
            _emit(
                {
                    "schema": report["schema"],
                    "counts": report["counts"],
                    "relations": report["relations"],
                    "stages": report["stages"],
                    "coverage": report["coverage"],
                    "db_stats": report["db_stats"],
                },
                out=args.out,
            )
            return 0

        if args.command == "quality":
            report = run_checks(store)
            if args.write_report:
                out_path = config.REPORTS_DIR / "quality_report.json"
                out_path.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                report["written"] = config.relative(out_path)
            _emit(report, out=args.out)
            return 0

        if args.command == "graph":
            counts = build_source_declared_relations(store)
            _emit({"schema": "medradar.atlas.graph_build.v1", "relations_created": counts,
                   "db": config.relative(store.path)}, out=args.out)
            return 0

        if args.command == "query":
            command = args.query_command
            if command == "company":
                payload = company_devices(store, args.key)
            elif command == "device":
                payload = device_identity(store, args.key)
            elif command == "path":
                payload = evidence_path(store, args.key)
            elif command == "tech":
                payload = technology_companies(store, args.key)
            elif command == "relation":
                payload = relation_evidence(store, args.key)
            elif command == "rejections":
                payload = rejected_relations(store, limit=args.limit)
            else:
                payload = device_research_candidates(store, args.key)
            _emit(payload, out=args.out)
            return 0

        if args.command == "as-of":
            _emit(as_of(store, args.at, basis=args.basis), out=args.out)
            return 0

        if args.command == "history":
            _emit(evidence_history(store, args.evidence_id), out=args.out)
            return 0

        if args.command == "prospective":
            if args.prospective_command == "register":
                _emit(register_cross_market_candidates(store, limit=args.limit), out=args.out)
            else:
                _emit(candidate_summary(store), out=args.out)
            return 0

        if args.command == "stats":
            _emit(store.stats(), out=args.out)
            return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
