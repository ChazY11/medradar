"""``python -m medradar.integration`` — the runnable integration surface.

Commands
--------
``init``    create the isolated staging database and print its path
``import``  read a HORIZON export, verify it, convert and append it
``graph``   rebuild cross-source relations for the latest import run
``stats``   print database statistics
``query``   run one of the six demonstration queries
``check``   run the contract self-checks (no database needed)

Every command is offline and reads only local files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from medradar.atlas.evidence.timeq import utc_iso

from . import demo
from .adapter import HorizonToAtlasAdapter
from .contract import CONTRACT_ID, CONTRACT_VERSION
from .graph import build_graph
from .licence import LicencePolicy
from .staging import ConvergenceStore

REPO_ROOT = Path(__file__).resolve().parents[2]


def _default_db() -> Path:
    return REPO_ROOT / "research/convergence/staging/convergence.sqlite"


def _json_out(payload: object, *, path: str = "") -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")
        print(f"wrote {path} ({len(text)} bytes)")
    else:
        print(text)


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.db) if args.db else _default_db()
    with ConvergenceStore(path) as store:
        stats = store.stats()
    print(f"initialised staging database at {path}")
    print(json.dumps({"path": str(path), "evidence": stats.get("evidence_ids", 0)}, indent=1))
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    # Delegate to the end-to-end pipeline so there is exactly one import path.
    from tools.convergence.run_integration import main as pipeline_main

    argv = ["--export-dir", args.export_dir] if args.export_dir else []
    if args.db:
        argv += ["--db", args.db]
    if args.run_id:
        argv += ["--run-id", args.run_id]
    if args.fresh:
        argv.append("--fresh")
    if args.limit:
        argv += ["--limit", str(args.limit)]
    if args.no_graph:
        argv.append("--no-graph")
    if args.policy:
        argv += ["--policy", args.policy]
    return pipeline_main(argv)


def cmd_graph(args: argparse.Namespace) -> int:
    path = Path(args.db) if args.db else _default_db()
    with ConvergenceStore(path) as store:
        runs = [r for r in store.runs() if r.get("status") == "complete"]
        if not runs:
            print("no completed import run; run `import` first", file=sys.stderr)
            return 2
        run_id = runs[-1]["run_id"]
        summary = build_graph(store, run_id=run_id)
    _json_out(summary, path=args.out)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    path = Path(args.db) if args.db else _default_db()
    if not path.exists():
        print(f"no staging database at {path}", file=sys.stderr)
        return 2
    with ConvergenceStore(path) as store:
        stats = store.stats()
    _json_out(stats, path=args.out)
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    path = Path(args.db) if args.db else _default_db()
    with ConvergenceStore(path) as store:
        if args.name == "all":
            payload = demo.run_all(
                store,
                firm=args.firm,
                keyword=args.keyword,
                as_of=args.as_of,
            )
        elif args.name == "q1":
            payload = demo.q1_company_product_regulatory(store, args.firm)
        elif args.name == "q2":
            payload = demo.q2_company_patent_publication(store, args.firm)
        elif args.name == "q3":
            payload = demo.q3_product_trial_or_paper(store, args.keyword)
        elif args.name == "q4":
            payload = demo.q4_historical_subsidiary(store, args.firm)
        elif args.name == "q5":
            payload = demo.q5_technology_theme_independent_evidence(
                store, args.scheme, args.value
            )
        elif args.name == "q6":
            payload = demo.q6_as_of(store, args.as_of)
        else:  # pragma: no cover - argparse restricts the choices
            print(f"unknown query {args.name}", file=sys.stderr)
            return 2
    _json_out(payload, path=args.out)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Contract self-checks that need no database."""
    from .contract import classify_identifier, is_gtin14

    failures: list[str] = []
    vectors = {
        "00885074528007": True,   # valid GS1 GTIN-14
        "00195278070265": True,
        "00885074528008": False,  # corrupted check digit
        "6102F-PA00017": False,   # MDALL catalogue token
        "1234567890123": False,   # 13 digits, not GTIN-14
    }
    for value, expected in vectors.items():
        actual = is_gtin14(value)
        if actual != expected:
            failures.append(f"gtin14({value}) -> {actual}, expected {expected}")
    promoted, note = classify_identifier("hc_mdall_device_identifier", "00885074528007")
    if promoted != "di":
        failures.append("valid GTIN-14 MDALL identifier was not promoted to 'di'")
    not_promoted, _ = classify_identifier("hc_mdall_device_identifier", "6102F-PA00017")
    if not_promoted != "hc_device_identifier":
        failures.append("MDALL catalogue token must not be promoted to 'di'")
    bad_digit, note2 = classify_identifier("hc_mdall_device_identifier", "00885074528008")
    if bad_digit != "hc_device_identifier" or not note2.get("derivation"):
        failures.append("GTIN-shaped value with invalid check digit must not be promoted")

    payload = {
        "contract": {"id": CONTRACT_ID, "version": CONTRACT_VERSION},
        "checks": len(vectors) + 3,
        "failures": failures,
        "ok": not failures,
        "generated_at": utc_iso(),
    }
    _json_out(payload, path=args.out)
    return 0 if not failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m medradar.integration",
        description="CONVERGENCE: HORIZON evidence → ATLAS substrate",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create the isolated staging database")
    init.add_argument("--db", default="")
    init.set_defaults(func=cmd_init)

    imp = sub.add_parser("import", help="import a HORIZON export into staging")
    imp.add_argument("--export-dir", default="")
    imp.add_argument("--db", default="")
    imp.add_argument("--run-id", default="")
    imp.add_argument("--fresh", action="store_true")
    imp.add_argument("--limit", type=int, default=0)
    imp.add_argument("--no-graph", action="store_true")
    imp.add_argument("--policy", default="")
    imp.set_defaults(func=cmd_import)

    graph = sub.add_parser("graph", help="rebuild cross-source relations")
    graph.add_argument("--db", default="")
    graph.add_argument("--out", default="")
    graph.set_defaults(func=cmd_graph)

    stats = sub.add_parser("stats", help="database statistics")
    stats.add_argument("--db", default="")
    stats.add_argument("--out", default="")
    stats.set_defaults(func=cmd_stats)

    query = sub.add_parser("query", help="run a demonstration query")
    query.add_argument("name", choices=["all", "q1", "q2", "q3", "q4", "q5", "q6"])
    query.add_argument("--db", default="")
    query.add_argument("--firm", default="medtronic")
    query.add_argument("--keyword", default="infusion")
    query.add_argument("--scheme", default="fda_product_code")
    query.add_argument("--value", default="FRN")
    query.add_argument("--as-of", default="2020-01-01")
    query.add_argument("--out", default="")
    query.set_defaults(func=cmd_query)

    check = sub.add_parser("check", help="contract self-checks (no database)")
    check.add_argument("--out", default="")
    check.set_defaults(func=cmd_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
