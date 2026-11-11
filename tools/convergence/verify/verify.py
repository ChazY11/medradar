"""Independent verification of MedRadar CONVERGENCE-001.

Recomputes every headline number from raw bytes, raw SQLite pages and the two
published schemas. It imports no application code: the only imports are the
verifier's own ``vlib``.

Usage
-----
    python tools/convergence/verify/verify.py --json research/convergence/verification/verification_summary.json

Exit status is 1 if any check FAILs, 0 otherwise. UNVERIFIABLE checks do not
affect the exit status but are counted and listed.

Determinism: the report contains no wall-clock timestamps and no paths outside
the workspace root, so the same inputs produce byte-identical JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from vlib import common as C  # noqa: E402
from vlib import v1_export, v2_h2, v3_atlas, v4_crosssource, v5_time, v6_licence, v7_adapter  # noqa: E402

DEFAULT_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def build_context(args):
    root = os.path.abspath(args.root)
    export_dir = args.export_dir or os.path.join(
        root, "research", "horizon", "exports", "horizon-2026-11-10")
    horizon_root = args.horizon_root
    if horizon_root is None:
        sibling = os.path.join(os.path.dirname(root), "horizon-001")
        horizon_root = sibling if os.path.isdir(sibling) else root
    atlas_root = args.atlas_root
    if atlas_root is None:
        sibling = os.path.join(os.path.dirname(root), "atlas-001")
        atlas_root = sibling if os.path.isdir(sibling) else root
    atlas_db = args.atlas_db or os.path.join(
        atlas_root, "research", "atlas", "staging", "atlas.sqlite")
    mdall_cache = args.mdall_cache or os.path.join(
        atlas_root, "research", "atlas", "cache", "mdall_active_deviceidentifier.json")
    staging = args.staging_snapshot or os.path.join(
        root, "research", "convergence", "verification", "snapshots",
        "convergence_staging_snapshot.sqlite")
    readable = False
    if os.path.exists(atlas_db):
        try:
            con = sqlite3.connect("file:" + atlas_db.replace("\\", "/") + "?mode=ro", uri=True)
            con.execute("SELECT 1 FROM evidence LIMIT 1")
            con.close()
            readable = True
        except sqlite3.Error:
            readable = False
    return {
        "root": root,
        "export_dir": export_dir,
        "horizon_root": os.path.abspath(horizon_root),
        "atlas_root": os.path.abspath(atlas_root),
        "atlas_db": atlas_db,
        "mdall_cache": mdall_cache,
        "staging_snapshot": staging,
        "atlas_db_readable": readable,
        "heavy": not args.skip_heavy,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="independent verification harness")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="integration worktree root")
    parser.add_argument("--export-dir", default=None)
    parser.add_argument("--horizon-root", default=None, help="HORIZON-001 worktree (origin of the export)")
    parser.add_argument("--atlas-root", default=None, help="read-only ATLAS-001 worktree")
    parser.add_argument("--atlas-db", default=None)
    parser.add_argument("--mdall-cache", default=None)
    parser.add_argument("--staging-snapshot", default=None)
    parser.add_argument("--json", default=None, help="write the machine-readable report here")
    parser.add_argument("--skip-heavy", action="store_true",
                        help="skip the 220 MB MDALL cache recount")
    parser.add_argument("--groups", default=None,
                        help="comma-separated subset of groups to run, e.g. V1,V2,V6")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    ctx = build_context(args)
    wanted = None
    if args.groups:
        wanted = {g.strip().upper() for g in args.groups.split(",") if g.strip()}

    relevant = {"root": ctx["root"], "export_dir": ctx["export_dir"],
                "horizon_root": ctx["horizon_root"], "atlas_root": ctx["atlas_root"]}
    checks = []
    facts = {}

    def keep(group_checks):
        if wanted is None or group_checks[0].group in wanted or not group_checks:
            checks.extend(group_checks)

    if wanted is None or "V1" in wanted:
        got, export_facts = v1_export.run(ctx)
        facts["v1"] = {"scans": export_facts["scans"], "counters": export_facts["counters"],
                       "dedupe": export_facts["dedupe"]}
        keep(got)
    else:
        export_facts = _minimal_export_facts(ctx)

    if wanted is None or "V2" in wanted:
        got, h2_facts = v2_h2.run(ctx, export_facts)
        facts["v2"] = {"pairs_total": (h2_facts.get("recomputed") or {}).get("pairs_total"),
                       "verdicts": (h2_facts.get("recomputed") or {}).get("verdicts"),
                       "construction_rules": (h2_facts.get("recomputed") or {}).get("by_construction_rule")}
        keep(got)

    atlas_facts = {}
    if wanted is None or "V3" in wanted:
        got, atlas_facts = v3_atlas.run(ctx)
        facts["v3"] = {"relations": atlas_facts.get("relations"),
                       "distinct_shared_identifiers": len(atlas_facts.get("bridge_gtins") or []),
                       "census": atlas_facts.get("census")}
        keep(got)

    if wanted is None or "V4" in wanted:
        got, v4facts = v4_crosssource.run(ctx, export_facts, atlas_facts)
        facts["v4"] = v4facts
        keep(got)

    if wanted is None or "V5" in wanted:
        got, v5facts = v5_time.run(ctx, export_facts)
        facts["v5"] = {"totals": v5facts.get("horizon_totals"),
                       "atlas": v5facts.get("atlas"),
                       "licence_vocabulary_unrepresentable": v5facts.get("licence_vocabulary_unrepresentable")}
        keep(got)

    if wanted is None or "V6" in wanted:
        got, v6facts = v6_licence.run(ctx, export_facts)
        facts["v6"] = {"content_scan": v6facts.get("content_scan"),
                       "present_unclear": v6facts.get("present_unclear"),
                       "comtrade_named_files": v6facts.get("comtrade_named_files")}
        keep(got)

    if wanted is None or "V7" in wanted:
        got, v7facts = v7_adapter.run(ctx, export_facts)
        facts["v7"] = {k: v for k, v in v7facts.items() if k != "snapshot"}
        keep(got)

    ordered = sorted(checks, key=lambda c: c.check_id)
    summary = {"PASS": 0, "FAIL": 0, "UNVERIFIABLE": 0}
    for check in ordered:
        summary[check.status] = summary.get(check.status, 0) + 1

    report = {
        "verifier": "tools/convergence/verify/verify.py",
        "contract": "independent recomputation; no application code imported",
        "inputs": {
            "export_dir": C.contextualise(ctx["export_dir"], ctx["root"]),
            "horizon_root": os.path.basename(ctx["horizon_root"]),
            "atlas_root": os.path.basename(ctx["atlas_root"]),
            "heavy_checks": ctx["heavy"],
        },
        "summary": {"total": len(ordered), **summary,
                    "verdict": "FAIL" if summary.get("FAIL") else "PASS"},
        "checks": [c.to_dict() for c in ordered],
        "facts": facts,
    }

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(report, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")

    if not args.quiet:
        width = max(len(c.check_id) for c in ordered) + 2
        group = None
        for check in ordered:
            if check.group != group:
                group = check.group
                print("\n%s" % ("=" * 92))
                print("%s" % group)
                print("=" * 92)
            print("%-*s %-12s %s" % (width, check.check_id, check.status, check.title))
            if check.status != C.PASS and check.detail:
                print("%-*s   %s" % (width, "", check.detail[:160]))
        print("\n%s" % ("-" * 92))
        fails = [c for c in ordered if c.status == C.FAIL]
        unv = [c for c in ordered if c.status == C.UNVERIFIABLE]
        print("PASS %d  FAIL %d  UNVERIFIABLE %d  (total %d)"
              % (summary["PASS"], summary["FAIL"], summary["UNVERIFIABLE"], len(ordered)))
        if fails:
            print("\nFAILED:")
            for check in fails:
                print("  - %s: %s" % (check.check_id, check.title))
        if unv:
            print("\nNOT VERIFIABLE OFFLINE:")
            for check in unv:
                print("  - %s: %s" % (check.check_id, check.title))
        if args.json:
            print("\nreport: %s" % args.json)

    return 1 if summary["FAIL"] else 0


def _minimal_export_facts(ctx):
    """Load just enough of the export for V2/V4/V5/V6 when V1 is filtered out."""
    export_dir = ctx["export_dir"]
    manifest = C.read_json(os.path.join(export_dir, "MANIFEST.json"))
    records = {}
    counts = {}
    for entry in manifest["files"]:
        path = os.path.join(export_dir, entry["path"])
        if not os.path.exists(path):
            continue
        rows = C.load_jsonl(path)
        records[entry["source_id"]] = rows
        counts[entry["source_id"]] = {
            "records": len(rows),
            "records_with_identifiers": sum(1 for r in rows if r.get("identifiers")),
            "records_with_source_public_at": sum(1 for r in rows if r.get("source_public_at")),
            "records_with_event_at": sum(1 for r in rows if r.get("event_at")),
        }
    dedupe = {sid: len({C.horizon_dedupe_key(r) for r in rows}) for sid, rows in records.items()}
    return {"manifest": manifest, "records_by_source": records,
            "counters": counts, "dedupe": dedupe,
            "per_source": {p["source_id"]: p for p in manifest["per_source"]}}


if __name__ == "__main__":
    sys.exit(main())
