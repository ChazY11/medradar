"""Orchestrator: run every stage in order, offline, and record a manifest of hashes.

    python experiments/phoenix003/code/run_pipeline.py --db data/medradar.sqlite

Stages: freeze_vocab -> a1_anchors -> b_links -> b2_novelty -> c_controls -> d_leadtime.
Extra arguments are forwarded to the stage scripts (``--db`` plus anything after ``--``).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phoenix003_common as pc

STAGES = [
    ("freeze_vocab", "freeze_vocab.py"),
    ("freeze_epmc_df", "freeze_epmc_df.py"),
    ("a1_anchors", "a1_anchors.py"),
    ("b_links", "b_links.py"),
    ("b2_novelty", "b2_novelty.py"),
    ("c_controls", "c_controls.py"),
    ("d_leadtime", "d_leadtime.py"),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("MEDRADAR_DB", "data/medradar.sqlite"))
    ap.add_argument("--only", default=None, help="comma-separated stage names")
    args, rest = ap.parse_known_args(argv)

    only = set(args.only.split(",")) if args.only else None
    code_dir = Path(__file__).resolve().parent
    log_lines = []
    started = time.time()
    results = {}

    for name, script in STAGES:
        if only and name not in only:
            continue
        cmd = [sys.executable, str(code_dir / script), "--db", args.db] + rest
        t0 = time.time()
        print(f"\n=== stage {name} ===", flush=True)
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        dt = time.time() - t0
        log_lines.append(f"=== {name} ({dt:.1f}s) rc={proc.returncode}")
        log_lines.append(proc.stdout.rstrip())
        if proc.stderr.strip():
            log_lines.append("--- stderr ---")
            log_lines.append(proc.stderr.rstrip())
        print(proc.stdout.rstrip())
        if proc.returncode != 0:
            print(proc.stderr.rstrip(), file=sys.stderr)
            (pc.RESULTS / "pipeline.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
            print(f"stage {name} failed", file=sys.stderr)
            return proc.returncode
        results[name] = {"seconds": round(dt, 2), "returncode": proc.returncode}

    # ---------------------------------------------------------------- manifest
    watched = [
        pc.EXPERIMENT_DIR / "FROZEN_RULES.json",
        pc.DATASET / "firm_lineage.json",
        pc.DATASET / "frozen_vocab.json",
        pc.DATASET / "name_stoplist_extra.txt",
        pc.DATASET / "epmc_rare_tokens.txt",
        pc.DATASET / "epmc_df_meta.json",
        pc.EXPERIMENT_DIR / "REGULATORY_ANCHORS.jsonl",
        pc.EXPERIMENT_DIR / "EVIDENCE_LINKS.jsonl",
    ]
    watched += sorted(pc.DATASET.glob("*_compact.jsonl.gz"))
    watched += [p for p in sorted(pc.RESULTS.glob("*.json"))
                if p.name != "manifest.json"]  # never hash itself: the hash would lag the write
    manifest = {
        "generated_at": pc.utc_now_iso(),
        "db": args.db,
        "stages": results,
        "total_seconds": round(time.time() - started, 2),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "files": [],
    }
    for p in watched:
        if not p.exists():
            continue
        manifest["files"].append({
            "path": str(p.relative_to(pc.REPO_ROOT)).replace("\\", "/"),
            "bytes": p.stat().st_size,
            "sha256": pc.sha256_file(p),
        })
    pc.write_json(pc.RESULTS / "manifest.json", manifest)
    (pc.RESULTS / "pipeline.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print(json.dumps({"stages": results, "total_seconds": manifest["total_seconds"],
                      "files": len(manifest["files"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
