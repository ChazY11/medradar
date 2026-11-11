#!/usr/bin/env python
"""CONVERGENCE-001 end-to-end integration run.

    python tools/convergence/run_integration.py --fresh

Steps, in order, and each one is allowed to *fail the run*:

1. Read the HORIZON export manifest and verify every declared file's SHA-256,
   byte length and record count against the bytes on disk.
2. Apply the licence policy: a source that may not be ingested is skipped, and a
   source that may not be redistributed is flagged rather than silently included.
3. Convert every permitted record with ``HorizonToAtlasAdapter`` and append it to
   a **new, isolated** staging database (ATLAS's append-only store at a new path).
4. Build the cross-source graph from authoritative identifiers only.
5. Measure the four dedupe layers.
6. Write a versioned conversion manifest and a machine summary.

Exit code is non-zero if integrity fails or if any record is rejected without a
recorded reason.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from medradar.atlas.evidence.timeq import utc_iso  # noqa: E402
from medradar.integration.adapter import HorizonToAtlasAdapter  # noqa: E402
from medradar.integration.contract import CONTRACT_ID, CONTRACT_VERSION  # noqa: E402
from medradar.integration.dedupe import dedupe_report  # noqa: E402
from medradar.integration.graph import build_graph  # noqa: E402
from medradar.integration.licence import LicencePolicy  # noqa: E402
from medradar.integration.staging import DEFAULT_STAGING_DB, ConvergenceStore  # noqa: E402

DEFAULT_EXPORT = REPO_ROOT / "research/horizon/exports/horizon-2026-11-10"
REPORTS_DIR = REPO_ROOT / "research/convergence/reports"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_export(export_dir: Path, policy: LicencePolicy) -> dict:
    """Check the export against its own manifest.  Never trust the manifest alone."""
    manifest_path = export_dir / "MANIFEST.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    licence_by_source = dict(manifest.get("licence_summary") or {})
    quarantined = policy.quarantined_sources()
    rows = []
    problems = []
    totals = collections.Counter()
    for entry in manifest["files"]:
        path = export_dir / entry["path"]
        source_id = entry["source_id"]
        licence_status = str(licence_by_source.get(source_id, "unknown"))
        row = {
            "source_id": source_id,
            "path": entry["path"],
            "declared_bytes": entry["bytes"],
            "declared_records": entry["records"],
            "declared_sha256": entry["sha256"],
            "licence_status": licence_status,
            "state": "unknown",
        }
        if source_id in quarantined or not policy.may_ingest(source_id, licence_status):
            # Not allowed into this integration artefact.  If the payload is also
            # absent, that is the expected state, not a missing-file failure.
            if not path.exists():
                row["state"] = "quarantined_absent"
                totals["quarantined"] += 1
                rows.append(row)
                continue
            row["state"] = "blocked_present"
            problems.append(
                f"{entry['path']}: licence policy forbids ingestion but the payload is present"
            )
            totals["blocked_present"] += 1
            rows.append(row)
            continue
        if not path.exists():
            row["state"] = "missing"
            problems.append(f"{entry['path']}: declared but absent")
            totals["missing"] += 1
            rows.append(row)
            continue
        actual_bytes = path.stat().st_size
        actual_hash = sha256_file(path)
        actual_records = sum(1 for line in path.open("rb") if line.strip())
        row.update(
            {
                "actual_bytes": actual_bytes,
                "actual_records": actual_records,
                "actual_sha256": actual_hash,
            }
        )
        mismatches = []
        if actual_bytes != entry["bytes"]:
            mismatches.append(f"bytes {actual_bytes} != {entry['bytes']}")
        if actual_hash != entry["sha256"]:
            mismatches.append("sha256 mismatch")
        if actual_records != entry["records"]:
            mismatches.append(f"records {actual_records} != {entry['records']}")
        if mismatches:
            row["state"] = "mismatch"
            row["mismatches"] = mismatches
            problems.append(f"{entry['path']}: " + "; ".join(mismatches))
            totals["mismatch"] += 1
        else:
            row["state"] = "verified"
            totals["verified"] += 1
        rows.append(row)

    declared_total = manifest["totals"]["records"]
    verified_records = sum(r.get("actual_records", 0) for r in rows if r["state"] == "verified")
    return {
        "export_id": manifest.get("export_id"),
        "schema_version": manifest.get("schema_version"),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "declared_sources": manifest["totals"]["sources"],
        "declared_records": declared_total,
        "declared_bytes": manifest["totals"]["bytes"],
        "verified_records": verified_records,
        "state_counts": dict(totals),
        "files": rows,
        "problems": problems,
    }


def iter_export_records(export_dir: Path, manifest: dict, policy: LicencePolicy):
    """Yield (source_id, record, raw_line) for every record we are allowed to read."""
    for entry in manifest["files"]:
        source_id = entry["source_id"]
        path = export_dir / entry["path"]
        if source_id in policy.quarantined_sources() or not path.exists():
            continue
        with path.open("rb") as handle:
            for line in handle:
                if not line.strip():
                    continue
                yield source_id, json.loads(line), line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CONVERGENCE-001 end-to-end integration")
    parser.add_argument("--export-dir", default=str(DEFAULT_EXPORT))
    parser.add_argument("--db", default=str(REPO_ROOT / DEFAULT_STAGING_DB))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--fresh", action="store_true", help="delete and rebuild the staging DB")
    parser.add_argument("--limit", type=int, default=0, help="debug: stop after N records")
    parser.add_argument("--no-graph", action="store_true")
    parser.add_argument("--policy", default="", help="path to licence_policy.json")
    parser.add_argument("--reports-dir", default="", help="where to write the machine report")
    args = parser.parse_args(argv)

    export_dir = Path(args.export_dir)
    db_path = Path(args.db)
    run_id = args.run_id or f"conv_{utc_iso().replace(':', '').replace('-', '')}"
    policy = LicencePolicy.load(args.policy or None)

    print(f"[convergence] run_id={run_id}")
    print(f"[convergence] export={export_dir}")
    print(f"[convergence] db={db_path}")
    print(f"[convergence] policy={policy.summary()['policy_id']} ({policy.origin})")

    if args.fresh and db_path.exists():
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(db_path) + suffix)
            if candidate.exists():
                candidate.unlink()
        print("[convergence] removed existing staging database")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    integrity = verify_export(export_dir, policy)
    print(
        f"[convergence] integrity: verified={integrity['state_counts'].get('verified', 0)} "
        f"quarantined={integrity['state_counts'].get('quarantined', 0)} "
        f"mismatch={integrity['state_counts'].get('mismatch', 0)} "
        f"missing={integrity['state_counts'].get('missing', 0)}"
    )
    if integrity["problems"]:
        for problem in integrity["problems"]:
            print(f"[convergence] INTEGRITY PROBLEM: {problem}")

    manifest = json.loads((export_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    adapter = HorizonToAtlasAdapter(policy)
    store = ConvergenceStore(db_path)
    store.begin_run(
        run_id=run_id,
        export_id=str(integrity["export_id"]),
        manifest_sha256=integrity["manifest_sha256"],
        contract_version=f"{CONTRACT_ID}@{CONTRACT_VERSION}",
        mapping_version=adapter.mapping_version,
        policy_id=str(policy.summary()["policy_id"]),
    )

    records = []
    raw_lines = []
    for source_id, record, line in iter_export_records(export_dir, manifest, policy):
        records.append(record)
        raw_lines.append(line)
        if args.limit and len(records) >= args.limit:
            break
    print(f"[convergence] importing {len(records)} permitted records")

    summary = store.import_records(
        records, adapter=adapter, run_id=run_id, raw_lines=raw_lines
    )
    print(
        f"[convergence] imported: converted={summary['converted']} "
        f"degraded={summary['degraded']} rejected={summary['rejected']} "
        f"inserted={summary['evidence_inserted']} noop={summary['evidence_noop']} "
        f"conflicts={summary['conflicts']}"
    )

    graph = {} if args.no_graph else build_graph(store, run_id=run_id)
    if graph:
        print(
            f"[convergence] graph: authoritative_links="
            f"{graph['authoritative_links']['created']} company_links="
            f"{graph['company_links']['links']} atlas_relations="
            f"{graph['atlas_relations_total']}"
        )

    evidence = list(store.atlas.iter_evidence())
    relation_rows = store.atlas.query(
        "SELECT relation_id, from_ref, to_ref, relation_type, status, method"
        " FROM entity_relations WHERE revoked_at=''"
    )
    dedupe = dedupe_report(
        [
            {
                "evidence_id": record["evidence_id"],
                "source_id": record["source_id"],
                "evidence_type": record["evidence_type"],
                "canonical_key": record.get("canonical_key"),
                "source_content_hash": record.get("source_content_hash"),
                "identifiers": record.get("identifiers"),
                "normalized": record.get("normalized"),
            }
            for record in evidence
        ],
        relations=relation_rows,
    )
    store.close_run(run_id, status="complete")

    run_summary = store.run_summary(run_id)
    report = {
        "generated_at": utc_iso(),
        "run_id": run_id,
        "contract": {"id": CONTRACT_ID, "version": CONTRACT_VERSION},
        "adapter_mapping_version": adapter.mapping_version,
        "policy": policy.summary(),
        "integrity": integrity,
        "import": summary,
        "run": run_summary,
        "graph": graph,
        "dedupe": dedupe,
        "stats": store.stats(),
    }
    store.close()

    reports_dir = Path(args.reports_dir) if args.reports_dir else REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"integration_{run_id}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[convergence] wrote {report_path}")
    print(f"[convergence] report is {report_path.stat().st_size} bytes")

    failures = []
    if integrity["problems"]:
        failures.append("export_integrity_problems")
    if summary["rejected"]:
        # Rejections are allowed, but every one must carry a reason in the DB.
        failures.append(f"rejected_records={summary['rejected']}")
    if failures:
        print(f"[convergence] FAIL: {', '.join(failures)}")
        print(json.dumps({"run_id": run_id, "failures": failures}, indent=1))
        return 1
    print("[convergence] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
