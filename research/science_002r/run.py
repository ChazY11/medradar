"""Command entry point for the SCIENCE-002R audit.

    python -m research.science_002r.run selection     # H1: selection-bias rebuilds
    python -m research.science_002r.run stats         # H2/H3/H5: dependence, interval, leakage
    python -m research.science_002r.run entity        # H4: attribution and coverage
    python -m research.science_002r.run consistency   # H6: recompute every reported number
    python -m research.science_002r.run establishments # extract the establishment link tables
    python -m research.science_002r.run all

The raw cache is read, never written. Set MEDRADAR_S2_CACHE to the cache produced by
the original SCIENCE-002 run; nothing here downloads.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import common

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def cmd_selection(args: argparse.Namespace) -> int:
    from research.science_002.sources import Cache
    from . import selection
    cache = Cache(offline=True)
    out = selection.run(cache, seed=args.seed, n_perm=args.n_perm, n_boot=args.n_boot)
    common.write_json(common.ARTIFACTS_R / "selection_bias.json", out)
    print(json.dumps(out["summary"], indent=1))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    from research.science_002.sources import Cache
    from . import stats_review
    cache = Cache(offline=True)
    out = stats_review.run(cache, seed=args.seed, n_perm=args.n_perm)
    common.write_json(common.ARTIFACTS_R / "stats_review.json", out)
    print(json.dumps({k: out[k] for k in ("meta", "block_permutation", "jackknife",
                                          "quarterly", "leakage")}, indent=1))
    return 0


def cmd_entity(args: argparse.Namespace) -> int:
    from research.science_002.sources import Cache
    from . import entity_audit
    cache = Cache(offline=True)
    out = entity_audit.run(cache)
    common.write_json(common.ARTIFACTS_R / "entity_audit.json", out)
    print(json.dumps({k: out[k] for k in ("C1_universe_share", "C3_precision",
                                          "establishment_identifiers")}, indent=1)[:2000])
    return 0


def cmd_consistency(args: argparse.Namespace) -> int:
    from . import internal_consistency
    out = internal_consistency.run()
    common.write_json(common.ARTIFACTS_R / "internal_consistency.json", out)
    print("claims", out["meta"]["n_claims"], "mismatches", out["meta"]["n_mismatch"])
    for row in out["mismatches"]:
        print("  MISMATCH:", row["claim"], row["reported"], "->", row["recomputed"])
    return 0


def cmd_establishments(args: argparse.Namespace) -> int:
    from . import establishments
    out = {"links": establishments.extract_510k_links(),
           "registrations": establishments.extract_registration_owners()}
    common.write_json(common.ARTIFACTS_R / "establishment_extract.json", out)
    print(json.dumps(out, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["selection", "stats", "entity", "consistency",
                                            "establishments", "all"])
    parser.add_argument("--seed", type=int, default=20261114)
    parser.add_argument("--n-perm", type=int, default=2000)
    parser.add_argument("--n-boot", type=int, default=2000)
    args = parser.parse_args(argv)
    if args.command == "all":
        for step in (cmd_consistency, cmd_stats, cmd_entity, cmd_selection):
            code = step(args)
            if code:
                return code
        return 0
    handler = {"selection": cmd_selection, "stats": cmd_stats, "entity": cmd_entity,
               "consistency": cmd_consistency,
               "establishments": cmd_establishments}[args.command]
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
