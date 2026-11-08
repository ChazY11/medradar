#!/usr/bin/env python
"""Freeze / verify the pre-registration hashes.

The experiment design and the scoring rubric are committed *before* any result
exists.  Freezing their hashes makes a later silent weight change detectable.

    python research/data_expansion/tools/pre_registration.py --freeze
    python research/data_expansion/tools/pre_registration.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN_AT = "2026-11-09T05:40:00Z"
TARGETS = ("EXPERIMENT_DESIGN.md", "registry/SOURCE_SCORING_RUBRIC.json")
RECORD = ROOT / "experiments" / "pre_registration.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_record() -> dict:
    files = {}
    for rel in TARGETS:
        path = ROOT / rel
        if not path.exists():
            raise SystemExit(f"missing pre-registered file: {path}")
        files[rel] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    return {
        "schema": "medradar.external.pre_registration.v1",
        "frozen_at": FROZEN_AT,
        "frozen_by": "DATA-EXPANSION-001 lead, before any experiment number existed",
        "files": files,
        "rules": {
            "anchor_rule": "per firm, per calendar year 2017-2024, first openFDA 510(k)/PMA decision by (decision_date, official number)",
            "exp_a_decision": "INCREMENTAL iff coverage_any >= 0.10 and duplicate_rate <= 0.50; INSUFFICIENT_EVIDENCE below 20 real records",
            "exp_c_decision": "detectable lead iff T1 median lead vs placebo one-sided permutation p < 0.05 AND confirmed_link_rate >= 0.7",
            "exp_b_scope": "no population precision/recall/F1; only error rate on the authoritative-identifier subset, refusal rate, candidate volume, decoy control",
            "lead_time_quality_gate": "only source_public_at_quality in {exact, day} may enter lead-time statistics",
        },
        "amendment_policy": "append-only; corrections must be recorded in SOURCE_INCREMENT_EXPERIMENT.md section '偏离预注册'",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--freeze", action="store_true", help="write/refresh the hash record")
    group.add_argument("--check", action="store_true", help="verify the frozen hashes still match")
    args = parser.parse_args(argv)

    record = build_record()
    if args.freeze:
        RECORD.parent.mkdir(parents=True, exist_ok=True)
        RECORD.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"frozen {len(record['files'])} files at {record['frozen_at']} -> {RECORD}")
        for rel, meta in record["files"].items():
            print(f"  {rel}  sha256={meta['sha256'][:16]}…  {meta['bytes']} B")
        return 0

    if not RECORD.exists():
        print("no pre-registration record; run --freeze first", file=sys.stderr)
        return 1
    frozen = json.loads(RECORD.read_text(encoding="utf-8"))
    bad = 0
    for rel, meta in frozen["files"].items():
        path = ROOT / rel
        if not path.exists():
            print(f"MISSING  {rel}", file=sys.stderr)
            bad += 1
            continue
        actual = sha256_file(path)
        if actual != meta["sha256"]:
            print(f"CHANGED  {rel}\n  frozen {meta['sha256']}\n  now    {actual}", file=sys.stderr)
            bad += 1
        else:
            print(f"OK       {rel}")
    if bad:
        print(f"\n{bad} pre-registered file(s) changed after freezing.", file=sys.stderr)
        print("If this was intentional, record the deviation in SOURCE_INCREMENT_EXPERIMENT.md.", file=sys.stderr)
        return 1
    print(f"\npre-registration verified ({frozen['frozen_at']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
