"""HORIZON-001 CLI.

    python -m hz.cli probe   --suite epo_publication_server
    python -m hz.cli register --index
    python -m hz.cli verify
    python -m hz.cli sources

Everything is offline-safe except ``probe`` and the per-connector collect
commands, which are bounded by explicit budgets.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # research/horizon


def cmd_sources(_args) -> int:
    from .registry import index

    doc = index(ROOT)
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def cmd_probe(args) -> int:
    from .suites import SUITES
    from .probe import run_probes

    if args.suite not in SUITES:
        sys.stderr.write(
            f"unknown suite {args.suite!r}; known: {', '.join(sorted(SUITES))}\n"
        )
        return 2
    probes = SUITES[args.suite]()
    out_dir = os.path.join(ROOT, "SOURCE_PROBES", args.suite)
    doc = run_probes(
        probes,
        out_dir=out_dir,
        client_name=args.suite,
        max_requests=args.max_requests,
    )
    print(json.dumps(doc["outcomes"], indent=2))
    print(f"written: {out_dir}")
    return 0


def cmd_verify(_args) -> int:
    """Offline self-check: schema, exports, registry consistency."""
    from .verify import run_all

    report = run_all(ROOT)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hz", description="HORIZON-001 data tooling")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("sources", help="print the source register index")
    ps.set_defaults(func=cmd_sources)

    pp = sub.add_parser("probe", help="run a declared probe suite")
    pp.add_argument("--suite", required=True)
    pp.add_argument("--max-requests", type=int, default=40)
    pp.set_defaults(func=cmd_probe)

    pv = sub.add_parser("verify", help="offline integrity self-check")
    pv.set_defaults(func=cmd_verify)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
