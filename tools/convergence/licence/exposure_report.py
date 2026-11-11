#!/usr/bin/env python
"""Quantify the Git-history exposure of quarantined payloads.

Read-only. Answers, for an explicit list of paths:

  * which commits introduced them, on which refs;
  * the blob object id(s) and byte size of each;
  * the total distinct bytes;
  * whether the blobs are reachable from a given set of refs (e.g. the integration
    branch), and which branches contain the introducing commit.

This produces the exact list an owner would need if they chose to purge history.
It performs no rewriting and never touches the object database.

Usage
    python tools/convergence/licence/exposure_report.py \
        --repo D:/path/to/repo \
        --payload-ref research/horizon-001 \
        --check-ref integration/convergence-001 \
        --paths-from config/convergence/licence_policy.json \
        --out research/convergence/licence/pr29_exposure.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys


def git(repo: str, *args: str) -> str:
    proc = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: "
                           f"{proc.stderr.decode('utf-8', 'replace')[:300]}")
    return proc.stdout.decode("utf-8", "replace")


def run(repo: str, *args: str) -> str:
    proc = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    return proc.stdout.decode("utf-8", "replace").strip()


def tree_blobs(repo: str, ref: str) -> dict[str, tuple[str, int]]:
    out = git(repo, "ls-tree", "-r", "-l", "-z", ref)
    mapping = {}
    for entry in out.split("\x00"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) < 4 or parts[1] != "blob":
            continue
        mapping[path] = (parts[2], int(parts[3]))
    return mapping


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--payload-ref", required=True,
                    help="ref that still contains the payload (e.g. the PR branch)")
    ap.add_argument("--check-ref", action="append", default=[],
                    help="ref that must NOT contain the payload; repeatable")
    ap.add_argument("--paths-from", required=True,
                    help="policy JSON; reads quarantine.paths")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    with open(args.paths_from, encoding="utf-8") as fh:
        policy = json.load(fh)
    paths = [p.replace("\\", "/") for p in policy["quarantine"]["paths"]]

    payload_tree = tree_blobs(args.repo, args.payload_ref)
    check_trees = {r: tree_blobs(args.repo, r) for r in args.check_ref}

    rows = []
    total_bytes = 0
    for path in paths:
        oid, size = payload_tree.get(path, (None, None))
        if oid:
            total_bytes += size
        adding = [ln for ln in run(args.repo, "log", "--all", "--diff-filter=A",
                                   "--format=%H %ad %s", "--date=iso-strict",
                                   "--", path).splitlines() if ln]
        branches = run(args.repo, "branch", "-a", "--contains", adding[0].split()[0]
                       ).splitlines() if adding else []
        rows.append({
            "path": path,
            "present_on_payload_ref": oid is not None,
            "blob_oid": oid,
            "bytes": size,
            "added_by": adding,
            "refs_containing_adding_commit": [b.strip("+ ").strip() for b in branches],
            "present_on_check_refs": {
                ref: path in tree for ref, tree in check_trees.items()
            },
        })

    unique_blobs = {r["blob_oid"] for r in rows if r["blob_oid"]}
    report = {
        "tool": "exposure_report",
        "repo": run(args.repo, "rev-parse", "--absolute-git-dir"),
        "payload_ref": args.payload_ref,
        "payload_ref_head": run(args.repo, "rev-parse", args.payload_ref),
        "check_refs": {r: run(args.repo, "rev-parse", r) for r in args.check_ref},
        "paths_checked": len(paths),
        "paths_present_on_payload_ref": sum(1 for r in rows if r["present_on_payload_ref"]),
        "distinct_blobs": len(unique_blobs),
        "total_payload_bytes": total_bytes,
        "quarantine_paths_present_on_check_refs": {
            ref: [r["path"] for r in rows if r["present_on_check_refs"].get(ref)]
            for ref in args.check_ref
        },
        "paths": rows,
        "note": ("Read-only git inspection. Byte sizes are blob sizes as stored, i.e. "
                 "the uncompressed content length; pack size on the wire is smaller."),
    }

    import os
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
        fh.write("\n")

    print(f"payload ref : {args.payload_ref} @ {report['payload_ref_head'][:12]}")
    print(f"paths       : {report['paths_checked']} checked, "
          f"{report['paths_present_on_payload_ref']} present")
    print(f"distinct    : {report['distinct_blobs']} blobs, "
          f"{report['total_payload_bytes']:,} bytes")
    for ref in args.check_ref:
        hits = report["quarantine_paths_present_on_check_refs"][ref]
        print(f"check ref   : {ref} @ {report['check_refs'][ref][:12]} -> "
              f"{len(hits)} quarantined path(s) present")
    print(f"wrote {args.out}")
    return 0 if not any(report["quarantine_paths_present_on_check_refs"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
