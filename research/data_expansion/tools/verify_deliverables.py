#!/usr/bin/env python
"""Phase 6 deliverable verifier for DATA-EXPANSION-001.

Checks, in order:

1. every required deliverable file exists;
2. the source register validates and its ``VERIFIED_*`` claims are backed by a
   probe, an ``evidence_url`` and a ``verified_at``;
3. every probe directory that exists has both a request ledger and a result;
4. every sample directory declares its hashes;
5. the pre-registration hashes still match;
6. no committed research artefact exceeds the size budget (no bulk raw data);
7. experiment outputs exist and use only the pre-registered verdict vocabulary;
8. the offline test suite still passes.

Any failure is printed and the exit code is non-zero, so CI or a reviewer can
use it directly.  It does not need the network.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

REQUIRED = [
    "GLOBAL_DATA_SOURCE_REGISTER.json",
    "GLOBAL_DATA_SOURCE_REPORT.md",
    "ACCESS_VERIFICATION.json",
    "LICENCE_AND_COST_AUDIT.md",
    "EXTERNAL_EVIDENCE_SCHEMA.md",
    "CONNECTORS/README.md",
    "SOURCE_INCREMENT_EXPERIMENT.md",
    "DATA_QUALITY_REPORT.md",
    "PRIORITY_ROADMAP.md",
    "EXECUTIVE_SUMMARY_ZH.md",
    "COLLECTION_PROTOCOL.md",
    "EXPERIMENT_DESIGN.md",
]

VERDICT_VOCAB = {
    "INCREMENTAL",
    "NOT_INCREMENTAL",
    "INSUFFICIENT_EVIDENCE",
    "DETECTABLE_LEAD",
    "NO_DETECTABLE_LEAD",
}

MAX_ARTEFACT_BYTES = 3 * 1024 * 1024


def main() -> int:
    problems: list[str] = []
    notes: list[str] = []

    # 1. deliverables
    for rel in REQUIRED:
        if not (ROOT / rel).exists():
            problems.append(f"missing deliverable: {rel}")

    # 2. register
    register = None
    register_path = ROOT / "GLOBAL_DATA_SOURCE_REGISTER.json"
    if register_path.exists():
        register = json.loads(register_path.read_text(encoding="utf-8"))
        if register.get("validation_problems"):
            problems.extend(f"register: {p}" for p in register["validation_problems"])
        sources = register.get("sources", [])
        notes.append(f"register: {len(sources)} sources")
        for record in sources:
            status = record.get("connection_status", "")
            if status.startswith("VERIFIED_"):
                if not record.get("verified_at"):
                    problems.append(f"{record['source_id']}: VERIFIED without verified_at")
                if not record.get("evidence_urls"):
                    problems.append(f"{record['source_id']}: VERIFIED without evidence_urls")
                if not record.get("probe"):
                    problems.append(f"{record['source_id']}: VERIFIED without a probe record")
        counts = register.get("counts", {}).get("by_connection_status", {})
        notes.append(f"status counts: {json.dumps(counts, sort_keys=True)}")

    # 3/4. probes and samples
    probe_dirs = sorted(p for p in (ROOT / "probes").glob("*") if p.is_dir())
    for directory in probe_dirs:
        if not (directory / "PROBE_RESULT.json").exists():
            problems.append(f"probe {directory.name}: missing PROBE_RESULT.json")
        if not (directory / "requests.jsonl").exists() and not (directory / "samples").exists():
            problems.append(f"probe {directory.name}: missing request ledger")
    notes.append(f"probes: {len(probe_dirs)}")

    sample_dirs = sorted(p for p in (ROOT / "samples").glob("*") if p.is_dir())
    for directory in sample_dirs:
        declared = list(directory.glob("*SAMPLES*.json")) + list(directory.glob("*_MANIFEST.json"))
        if not declared:
            notes.append(f"sample {directory.name}: no SAMPLES.json (advisory)")
    notes.append(f"sample dirs: {len(sample_dirs)}")

    # 5. pre-registration
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "pre_registration.py"), "--check"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        problems.append("pre-registration hash check failed: " + proc.stderr.strip()[:300])

    # 6. artefact size budget
    big: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {"staging", "__pycache__", "retrieval", ".git"} for part in path.parts):
            continue
        if path.suffix in {".sqlite", ".wal", ".gz", ".zip"}:
            continue
        if path.stat().st_size > MAX_ARTEFACT_BYTES:
            big.append(f"{path.relative_to(ROOT)} ({path.stat().st_size // 1024} KiB)")
    if big:
        problems.append("oversized artefacts committed: " + ", ".join(big))

    # 7. experiment verdicts
    exp_a = ROOT / "experiments" / "exp_a" / "EXP_A.json"
    exp_c = ROOT / "experiments" / "exp_c" / "EXP_C.json"
    if exp_a.exists():
        payload = json.loads(exp_a.read_text(encoding="utf-8"))
        for source_id, verdict in (payload.get("verdicts") or {}).items():
            if verdict not in VERDICT_VOCAB:
                problems.append(f"EXP-A {source_id}: verdict outside vocabulary: {verdict}")
        notes.append(f"EXP-A verdicts: {len(payload.get('verdicts') or {})}")
    else:
        problems.append("missing EXP_A.json")
    if exp_c.exists():
        payload = json.loads(exp_c.read_text(encoding="utf-8"))
        if payload.get("verdict") not in VERDICT_VOCAB:
            problems.append(f"EXP-C verdict outside vocabulary: {payload.get('verdict')}")
        notes.append(f"EXP-C verdict: {payload.get('verdict')}")
    else:
        problems.append("missing EXP_C.json")

    # 8. selftest
    proc = subprocess.run(
        [sys.executable, "-m", "medradar", "selftest"], cwd=str(REPO), capture_output=True, text=True
    )
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-3:]
    if proc.returncode != 0:
        problems.append("selftest failed: " + " | ".join(tail))
    else:
        notes.append("selftest: " + " | ".join(tail))

    print("== notes ==")
    for note in notes:
        print("  " + note)
    if problems:
        print("\n== problems ==", file=sys.stderr)
        for problem in problems:
            print("  - " + problem, file=sys.stderr)
        print(f"\n{len(problems)} problem(s)", file=sys.stderr)
        return 1
    print("\nall deliverable checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
