#!/usr/bin/env python
"""Export-directory licence gate.

For a HORIZON evidence export directory:

  1. read ``MANIFEST.json`` (the export's own declaration of what it contains);
  2. load the authoritative licence policy (``config/convergence/licence_policy.json``);
  3. classify **every declared file** against the policy;
  4. report ALLOW / QUARANTINE / MISSING-EXPECTED / VIOLATION / UNKNOWN-SOURCE;
  5. optionally check the policy's explicit quarantine paths anywhere in the repo.

Classification
--------------
ALLOW            source may be redistributed and the file is present
QUARANTINE       source may NOT be redistributed and the file is correctly absent
VIOLATION        source may NOT be redistributed but the file IS present
MISSING-EXPECTED source may be redistributed but the file is absent
UNKNOWN-SOURCE   the manifest declares a source the policy does not classify

Exit codes
----------
0  clean: no VIOLATION, no UNKNOWN-SOURCE, no MISSING-EXPECTED
1  VIOLATION: a quarantined payload is present (hard failure)
2  MISSING-EXPECTED: a redistributable payload is declared but absent
3  UNKNOWN-SOURCE / configuration error

`MISSING-EXPECTED` is deliberately a distinct non-zero code: for an export whose
restricted payload was *intentionally removed*, the manifest overshoots what is on
disk, so CI must be told which condition it is looking at.

Usage
-----
    python tools/convergence/licence/licence_gate.py \
        --export-dir research/horizon/exports/horizon-2026-11-10 \
        --policy config/convergence/licence_policy.json \
        --repo . \
        --json-out research/convergence/licence/gate_report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

ALLOW = "ALLOW"
QUARANTINE = "QUARANTINE"
VIOLATION = "VIOLATION"
MISSING_EXPECTED = "MISSING-EXPECTED"
UNKNOWN_SOURCE = "UNKNOWN-SOURCE"

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_MISSING = 2
EXIT_CONFIG = 3


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_policy(policy_path: str) -> dict:
    with open(policy_path, encoding="utf-8") as fh:
        policy = json.load(fh)
    if "sources" not in policy:
        raise ValueError(f"{policy_path}: not a licence policy (no 'sources')")
    return policy


def classify_declared_file(entry: dict, export_dir: str, sources: dict) -> dict:
    """Classify one MANIFEST.files[] entry."""
    sid = entry.get("source_id")
    rel = entry.get("path") or ""
    abs_path = os.path.join(export_dir, rel)
    present = os.path.isfile(abs_path)
    src = sources.get(sid)

    row = {
        "source_id": sid,
        "path": rel,
        "declared_records": entry.get("records"),
        "declared_bytes": entry.get("bytes"),
        "declared_sha256": entry.get("sha256"),
        "present": present,
        "actual_bytes": os.path.getsize(abs_path) if present else None,
        "integrity": None,
    }

    if src is None:
        row["status"] = UNKNOWN_SOURCE
        row["may_redistribute"] = None
        row["licence_status"] = None
        row["reason"] = "source is not classified by the policy"
        return row

    may_redis = bool(src.get("may_redistribute"))
    row["may_redistribute"] = may_redis
    row["licence_status"] = src.get("licence_status")
    row["redistribution_condition"] = src.get("redistribution_condition")

    if present and entry.get("sha256"):
        row["integrity"] = "ok" if _sha256(abs_path) == entry["sha256"] else "sha256-mismatch"

    if may_redis:
        if present:
            row["status"] = ALLOW
            row["reason"] = "source is redistributable and the payload is present"
        else:
            row["status"] = MISSING_EXPECTED
            row["reason"] = ("source is redistributable and the manifest declares this "
                             "file, but it is absent from the export directory")
    else:
        if present:
            row["status"] = VIOLATION
            row["reason"] = ("source is NOT redistributable "
                             f"(licence_status={src.get('licence_status')}) but its "
                             "payload is present in the export directory")
        else:
            row["status"] = QUARANTINE
            row["reason"] = ("source is NOT redistributable and the payload is correctly "
                             "absent (intentionally quarantined)")
    return row


def check_export(export_dir: str, policy_path: str, repo: str | None = None) -> dict:
    """Classify an export directory against the licence policy.

    Returns a report dict.  Never raises on findings; raises only on unusable input.
    """
    export_dir = os.path.abspath(export_dir)
    manifest_path = os.path.join(export_dir, "MANIFEST.json")
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(f"no MANIFEST.json in {export_dir}")
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    policy = load_policy(policy_path)
    sources = policy["sources"]

    declared = manifest.get("files") or []
    rows = [classify_declared_file(e, export_dir, sources) for e in declared]

    # Files on disk that the manifest does not declare: a quarantined payload could
    # be smuggled in that way, so report anything undeclared that matches a
    # quarantine path fragment.
    declared_paths = {r["path"] for r in rows}
    undeclared = []
    for root, _dirs, names in os.walk(export_dir):
        for name in names:
            rel = os.path.relpath(os.path.join(root, name), export_dir).replace("\\", "/")
            if rel in declared_paths or rel == "MANIFEST.json":
                continue
            undeclared.append(rel)

    quarantine_paths = [p.replace("\\", "/")
                        for p in policy.get("quarantine", {}).get("paths", [])]
    quarantine_hits = []
    if repo:
        repo_abs = os.path.abspath(repo)
        for rel in quarantine_paths:
            abs_p = os.path.join(repo_abs, *rel.split("/"))
            if os.path.isfile(abs_p):
                quarantine_hits.append({
                    "path": rel,
                    "present": True,
                    "bytes": os.path.getsize(abs_p),
                })

    summary = {ALLOW: 0, QUARANTINE: 0, VIOLATION: 0,
               MISSING_EXPECTED: 0, UNKNOWN_SOURCE: 0}
    for r in rows:
        summary[r["status"]] += 1

    integrity_mismatches = [r for r in rows if r.get("integrity") == "sha256-mismatch"]

    if summary[VIOLATION] or quarantine_hits:
        verdict = "FAIL"
        exit_code = EXIT_VIOLATION
    elif summary[UNKNOWN_SOURCE]:
        verdict = "FAIL"
        exit_code = EXIT_CONFIG
    elif summary[MISSING_EXPECTED]:
        verdict = "INCOMPLETE"
        exit_code = EXIT_MISSING
    else:
        verdict = "PASS"
        exit_code = EXIT_OK

    return {
        "tool": "licence_gate",
        "tool_version": "1.0.0",
        "export_dir": export_dir,
        "policy_path": os.path.abspath(policy_path),
        "policy_version": policy.get("policy_version"),
        "manifest_export_id": manifest.get("export_id"),
        "manifest_schema": manifest.get("schema_version"),
        "manifest_totals": manifest.get("totals"),
        "declared_files": len(declared),
        "summary": summary,
        "verdict": verdict,
        "exit_code": exit_code,
        "integrity_mismatches": [r["path"] for r in integrity_mismatches],
        "undeclared_files": sorted(undeclared),
        "quarantine_path_hits": quarantine_hits,
        "files": rows,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export-dir", required=True, help="HORIZON export directory")
    ap.add_argument("--policy", required=True, help="path to licence_policy.json")
    ap.add_argument("--repo", default=None,
                    help="repository root; enables the explicit quarantine-path check")
    ap.add_argument("--json-out", default=None, help="write the full report as JSON")
    ap.add_argument("--quiet", action="store_true", help="only print the verdict line")
    args = ap.parse_args(argv)

    try:
        report = check_export(args.export_dir, args.policy, args.repo)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if not args.quiet:
        print(f"export:   {report['manifest_export_id']}  ({report['export_dir']})")
        print(f"policy:   {report['policy_path']} v{report['policy_version']}")
        print(f"declared: {report['declared_files']} files")
        print()
        for r in report["files"]:
            flag = "!!" if r["status"] in (VIOLATION, UNKNOWN_SOURCE) else "  "
            integ = f"  integrity={r['integrity']}" if r.get("integrity") else ""
            print(f"{flag} {r['status']:17s} {r['source_id']:42s} "
                  f"{(r['path'] or ''):50s}{integ}")
        if report["undeclared_files"]:
            print(f"\nundeclared files present: {report['undeclared_files']}")
        if report["quarantine_path_hits"]:
            print("\nquarantine paths PRESENT in repo:")
            for h in report["quarantine_path_hits"]:
                print(f"  !! {h['path']}  ({h['bytes']} B)")
        if report["integrity_mismatches"]:
            print(f"\nsha256 mismatches: {report['integrity_mismatches']}")
        print()

    print(f"VERDICT {report['verdict']}  {report['summary']}  exit={report['exit_code']}")

    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1, sort_keys=False)
            fh.write("\n")
        if not args.quiet:
            print(f"wrote {args.json_out}")

    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
