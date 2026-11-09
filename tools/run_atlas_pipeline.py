#!/usr/bin/env python3
"""One-command ATLAS-001 pipeline: collect → graph → queries → verify.

This is the exact sequence used to produce the committed reports.  Every step is
the same CLI a reviewer would run by hand; the script only fixes the order.

    python tools/run_atlas_pipeline.py                # full, bounded network run
    python tools/run_atlas_pipeline.py --skip-collect # rebuild reports/queries from an existing DB

The collection step is bounded by the pilot defaults: five firms, 100 UDI
records each, 1,200 MDALL GTIN candidates, 40 Canadian licences, and a hard
HTTP budget of 400 requests.  It downloads MDALL's public identifier table once
(~220 MB) into a git-ignored cache.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "research" / "atlas" / "staging" / "atlas.sqlite"
EXAMPLES = ROOT / "research" / "atlas" / "reports" / "examples"


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(args), flush=True)
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, check=check, env={"PYTHONPATH": ".", **__import__("os").environ}
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-collect", action="store_true")
    parser.add_argument("--no-network", action="store_true")
    args = parser.parse_args(argv)
    EXAMPLES.mkdir(parents=True, exist_ok=True)

    run("-m", "medradar.atlas", "--db", str(DB), "init")
    if not args.skip_collect:
        run("-m", "medradar.atlas", "--db", str(DB), "pilot",
            *(["--no-network"] if args.no_network else []))
    run("-m", "medradar.atlas", "--db", str(DB), "graph", "build",
        "--out", str(EXAMPLES / "graph_build.json"))
    run("-m", "medradar.atlas", "--db", str(DB), "quality", "--write-report")
    for name, extra in (
        ("query_company_medtronic.json", ("query", "company", "--key", "medtronic")),
        ("query_path_medtronic.json", ("query", "path", "--key", "medtronic")),
        ("query_tech_IYN.json", ("query", "tech", "--key", "IYN")),
        ("query_rejections.json", ("query", "rejections", "--limit", "10")),
        ("as_of_observed_2026-11-10.json", ("as-of", "--at", "2026-11-10T00:00:00Z", "--basis", "observed")),
        ("as_of_public_2019-01-01.json", ("as-of", "--at", "2019-01-01T00:00:00Z", "--basis", "public_inferred")),
        ("prospective_register.json", ("prospective", "register", "--limit", "500")),
        ("prospective_list.json", ("prospective", "list")),
    ):
        run("-m", "medradar.atlas", "--db", str(DB), *extra, "--out", str(EXAMPLES / name))

    # One complete relation, chosen from the database rather than hard-coded.
    import sqlite3

    with sqlite3.connect(str(DB)) as conn:
        row = conn.execute(
            "SELECT relation_id FROM entity_relations"
            " WHERE relation_type='SAME_DEVICE_IDENTITY' AND status='CONFIRMED' LIMIT 1"
        ).fetchone()
    if row:
        run("-m", "medradar.atlas", "--db", str(DB), "query", "relation",
            "--key", row[0], "--out", str(EXAMPLES / "query_relation_confirmed.json"))
    with sqlite3.connect(str(DB)) as conn:
        device = conn.execute("SELECT device_id FROM devices ORDER BY device_id LIMIT 1").fetchone()
    if device:
        run("-m", "medradar.atlas", "--db", str(DB), "query", "research",
            "--key", device[0], "--out", str(EXAMPLES / "query_research_candidates.json"))

    run(str(ROOT / "tools" / "verify_atlas.py"), "--db", str(DB),
        "--out", str(ROOT / "research" / "atlas" / "reports" / "verification.json"))
    print("\nATLAS pipeline complete. See research/atlas/reports/ and docs/atlas/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
