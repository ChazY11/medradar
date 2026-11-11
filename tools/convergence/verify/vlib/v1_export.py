"""V1 — export integrity, recomputed from bytes only.

Gate for everything else: if the published bytes are not the bytes the manifest
describes, no downstream number is meaningful.
"""

from __future__ import annotations

import os

from . import common as C

MANIFEST_NAME = "MANIFEST.json"
README_NAME = "README.md"
QUARANTINED = ("un_comtrade.jsonl",)

# horizon.evidence.v1 controlled vocabularies, transcribed from
# research/horizon/hz/schema.py:28-79 rather than imported.
ENTITY_TYPES = {
    "patent_publication", "regulatory_listing", "regulatory_clearance",
    "product_identifier", "publication", "clinical_trial", "grant",
    "procurement_award", "trade_flow", "organisation", "postmarket_event", "recall",
}
IDENTITY_STATUS = {"UNKNOWN", "CANDIDATE", "CONFIRMED"}
EVIDENCE_STATUS = {"CANDIDATE", "CONFIRMED", "REJECTED"}
LICENCE_STATUS = {
    "open_licence", "public_domain", "open_no_explicit_licence", "terms_restricted",
    "requires_registration", "requires_licence", "unknown",
}
QUALITY_FLAGS = {
    "MISSING_PUBLICATION_DATE", "MISSING_FILING_DATE", "MISSING_PRIORITY_DATE",
    "MISSING_IDENTIFIER", "MISSING_MANUFACTURER", "MISSING_TITLE",
    "MISSING_CLASSIFICATION", "NOT_MEDTECH_ON_FRONT_PAGE", "SITEMAP_ONLY",
    "DOCUMENT_IS_SEARCH_REPORT", "DOCUMENT_IS_CORRECTION", "NAME_MATCH_ONLY",
    "IDENTIFIER_SELF_ASSIGNED", "SNAPSHOT_ONLY", "RETROSPECTIVE_FIELD",
    "TRUNCATED_RESPONSE", "PARSED_FROM_PDF", "PARSED_FROM_HTML",
    "DUPLICATE_OF_OTHER_SOURCE", "LICENCE_UNCLEAR", "RATE_LIMITED", "PARTIAL_PAGE",
}
SCHEMA_VERSION = "horizon.evidence.v1"


def _schema_errors(rec):
    errs = []
    if rec.get("schema_version") != SCHEMA_VERSION:
        errs.append("schema_version")
    for field in ("source_id", "source_record_id", "entity_type", "original_name", "source_url"):
        if not rec.get(field):
            errs.append("%s missing" % field)
    if rec.get("entity_type") and rec["entity_type"] not in ENTITY_TYPES:
        errs.append("entity_type")
    if rec.get("identity_status") not in IDENTITY_STATUS:
        errs.append("identity_status")
    if rec.get("evidence_status") not in EVIDENCE_STATUS:
        errs.append("evidence_status")
    if rec.get("licence_status") not in LICENCE_STATUS:
        errs.append("licence_status")
    for field in ("event_at", "source_public_at"):
        value = rec.get(field)
        if value is not None and not C.is_iso(value):
            errs.append("%s not ISO" % field)
    unknown = set(rec.get("quality_flags") or []) - QUALITY_FLAGS
    if unknown:
        errs.append("unknown quality_flags %s" % sorted(unknown))
    if not rec.get("identifiers"):
        if "MISSING_IDENTIFIER" not in (rec.get("quality_flags") or []):
            errs.append("no identifiers without MISSING_IDENTIFIER")
    return errs


def _parse_readme_table(text):
    """Parse the per-source markdown table in the export README."""
    rows = {}
    header = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if header is None:
            if cells and cells[0].lower().startswith("source"):
                header = [c.lower() for c in cells]
            continue
        if not cells or set(cells[0]) <= set("-: "):
            continue
        if cells[0].startswith("`"):
            cells[0] = cells[0].strip("`")
        if len(cells) != len(header):
            continue
        rows[cells[0]] = dict(zip(header, cells))
    return rows


def run(ctx):
    checks = []
    export_dir = ctx["export_dir"]
    manifest_path = os.path.join(export_dir, MANIFEST_NAME)
    manifest = C.read_json(manifest_path)
    files = manifest["files"]

    records_by_source = {}
    scans = {}
    heavy_ok = True

    # ---------------------------------------------------------------- presence
    declared = [f["path"] for f in files]
    absent = [p for p in declared if not os.path.exists(os.path.join(export_dir, p))]
    present = [p for p in declared if p not in absent]
    checks.append(C.compare(
        "v1.declared_files_present", "V1",
        "Every manifest-declared file exists (quarantine excepted)",
        "MANIFEST.json.files declares 24 source files; only un_comtrade.jsonl is quarantined.",
        "research/horizon/exports/horizon-2026-11-10/MANIFEST.json:7-176",
        expected=sorted(QUARANTINED), actual=sorted(absent),
        detail="declared=%d present=%d absent=%d" % (len(declared), len(present), len(absent)),
    ))

    # sidecar absence must match the payload absence exactly
    sidecar_of = {p: p + ".sha256" for p in declared}
    absent_sidecars = [sidecar_of[p] for p in declared
                       if not os.path.exists(os.path.join(export_dir, sidecar_of[p]))]
    checks.append(C.compare(
        "v1.quarantine_set_exact", "V1",
        "Absent set is exactly {un_comtrade.jsonl, un_comtrade.jsonl.sha256}",
        "Quarantining UN Comtrade must remove payload and sidecar and nothing else.",
        "task brief; MANIFEST.json:162-168",
        expected=sorted([QUARANTINED[0], QUARANTINED[0] + ".sha256"]),
        actual=sorted(absent + absent_sidecars),
    ))

    # undeclared extras in the export directory
    expected_extras = {MANIFEST_NAME, README_NAME}
    for p in declared:
        expected_extras.add(p)
        expected_extras.add(sidecar_of[p])
    on_disk = {n for n in os.listdir(export_dir)
               if os.path.isfile(os.path.join(export_dir, n))}
    unexpected = sorted(on_disk - expected_extras)
    checks.append(C.compare(
        "v1.no_undeclared_files", "V1",
        "Export directory holds no file the manifest does not account for",
        "The export is a closed set: 24 payloads + 24 sidecars + MANIFEST.json + README.md.",
        "research/horizon/exports/horizon-2026-11-10/",
        expected=[], actual=unexpected,
        detail="files_on_disk=%d" % len(on_disk),
    ))

    # ------------------------------------------------------- bytes / digest / rows
    byte_mismatch, hash_mismatch, record_mismatch, unparseable = [], [], [], []
    totals = {"sources": 0, "records": 0, "bytes": 0}
    for entry in files:
        path = os.path.join(export_dir, entry["path"])
        totals["sources"] += 1
        totals["records"] += entry["records"]
        totals["bytes"] += entry["bytes"]
        if not os.path.exists(path):
            continue
        scan = C.scan_jsonl(path)
        scans[entry["source_id"]] = scan
        if scan["bytes"] != entry["bytes"]:
            byte_mismatch.append({"path": entry["path"], "expected": entry["bytes"], "actual": scan["bytes"]})
        digest = C.sha256_file(path)
        if digest != entry["sha256"]:
            hash_mismatch.append({"path": entry["path"], "expected": entry["sha256"], "actual": digest})
        if scan["lines_nonempty"] != entry["records"]:
            record_mismatch.append({"path": entry["path"], "expected": entry["records"], "actual": scan["lines_nonempty"]})
        if scan["unparseable_lines"]:
            unparseable.append({"path": entry["path"], "n": scan["unparseable_lines"]})
        records_by_source[entry["source_id"]] = C.load_jsonl(path)

    checks.append(C.compare(
        "v1.bytes", "V1", "Every present file's byte length equals the manifest",
        "MANIFEST.json.files[].bytes is the exact byte length of the named file.",
        "MANIFEST.json:12 etc.", expected=[], actual=byte_mismatch,
        detail="checked %d present files" % len(present),
    ))
    checks.append(C.compare(
        "v1.sha256", "V1", "Every present file's SHA-256 equals the manifest",
        "MANIFEST.json.files[].sha256 is the digest of the named file.",
        "MANIFEST.json:11 etc.", expected=[], actual=hash_mismatch,
    ))
    checks.append(C.compare(
        "v1.records", "V1", "Record counts equal non-empty line counts",
        "MANIFEST.json.files[].records equals the number of non-empty lines in the jsonl.",
        "MANIFEST.json:13 etc.", expected=[], actual=record_mismatch,
        evidence={"unparseable_json_lines": unparseable,
                  "total_nonempty_lines": sum(s["lines_nonempty"] for s in scans.values())},
    ))
    checks.append(C.compare(
        "v1.totals", "V1", "MANIFEST.totals sums correctly from per-file facts",
        "totals = {sources: 24, records: 6492, bytes: 20335003} and equals the sums of files[].",
        "MANIFEST.json:395-399",
        expected={"sources": 24, "records": 6492, "bytes": 20335003},
        actual=totals,
        detail="sum over %d declared entries including the quarantined one" % len(files),
    ))

    # --------------------------------------------------------------- sidecars
    bad_sidecars = []
    for entry in files:
        side = os.path.join(export_dir, entry["path"] + ".sha256")
        if not os.path.exists(side):
            continue  # covered by v1.quarantine_set_exact
        text = C.read_text(side).strip()
        parts = text.split()
        digest = parts[0] if parts else ""
        named = parts[1] if len(parts) > 1 else ""
        actual_digest = C.sha256_file(os.path.join(export_dir, entry["path"]))
        if digest != actual_digest or named != entry["path"] or digest != entry["sha256"]:
            bad_sidecars.append({"sidecar": entry["path"] + ".sha256", "declared": digest,
                                 "actual": actual_digest, "named": named})
    checks.append(C.compare(
        "v1.sha256_sidecars", "V1", "Each .sha256 sidecar matches its own bytes and the manifest",
        "The per-file sidecar is a second, independent copy of the digest claim.",
        "research/horizon/exports/horizon-2026-11-10/*.sha256", expected=[], actual=bad_sidecars,
        detail="checked %d sidecars" % (len(files) - len(absent_sidecars)),
    ))

    # --------------------------------------------------- record-level hashing
    hash_bad = []
    for entry in files:
        rows = records_by_source.get(entry["source_id"])
        if rows is None:
            continue
        for row in rows:
            recomputed = C.horizon_content_hash(row)
            if recomputed != row.get("content_hash"):
                hash_bad.append({
                    "source_id": entry["source_id"],
                    "source_record_id": row.get("source_record_id"),
                    "declared": row.get("content_hash"),
                    "recomputed": recomputed,
                })
    checks.append(C.compare(
        "v1.content_hash", "V1", "Each record's content_hash recomputes from its own content",
        "content_hash = sha256(canonical subset) over schema_version, source identity, "
        "original_name, identifiers(scheme,value), manufacturer, attributes, event_at, "
        "source_public_at, source_url.",
        "research/horizon/hz/schema.py:146-173", expected=[], actual=hash_bad[:50],
        detail="mismatches=%d over %d records; first 50 shown"
               % (len(hash_bad), sum(len(r) for r in records_by_source.values())),
    ))

    # ------------------------------------------------------ schema conformance
    schema_bad = []
    for entry in files:
        rows = records_by_source.get(entry["source_id"]) or []
        for row in rows:
            errs = _schema_errors(row)
            if errs:
                schema_bad.append({"source_id": entry["source_id"],
                                   "source_record_id": row.get("source_record_id"),
                                   "errors": errs})
    checks.append(C.compare(
        "v1.schema_conformance", "V1", "Every record satisfies horizon.evidence.v1",
        "Every row validates against research/horizon/hz/schema.py (closed vocabularies, "
        "ISO clocks, declared identifiers).",
        "research/horizon/exports/horizon-2026-11-10/README.md:14", expected=[], actual=schema_bad[:50],
        detail="violations=%d" % len(schema_bad),
    ))

    # ------------------------------------------------------------ per_source
    per_source = {p["source_id"]: p for p in manifest["per_source"]}
    rec_bad = []
    for entry in files:
        declared_n = entry["records"]
        ps = per_source.get(entry["source_id"])
        if ps is None:
            rec_bad.append({"source_id": entry["source_id"], "issue": "absent from per_source"})
            continue
        if ps["records"] != declared_n:
            rec_bad.append({"source_id": entry["source_id"], "files": declared_n, "per_source": ps["records"]})
    checks.append(C.compare(
        "v1.per_source_records", "V1", "per_source[].records agrees with files[].records",
        "The two manifest views count the same records.", "MANIFEST.json:177-394",
        expected=[], actual=rec_bad,
    ))

    counter_bad = []
    counters = {}
    for entry in files:
        sid = entry["source_id"]
        rows = records_by_source.get(sid)
        if rows is None:
            continue
        computed = {
            "records": len(rows),
            "records_with_identifiers": sum(1 for r in rows if r.get("identifiers")),
            "records_with_source_public_at": sum(1 for r in rows if r.get("source_public_at")),
            "records_with_event_at": sum(1 for r in rows if r.get("event_at")),
            "records_with_first_observed_at": sum(1 for r in rows if r.get("first_observed_at")),
            "records_with_fetched_at": sum(1 for r in rows if r.get("fetched_at")),
        }
        counters[sid] = computed
        ps = per_source[sid]
        for field in ("records", "records_with_identifiers", "records_with_source_public_at", "records_with_event_at"):
            if ps[field] != computed[field]:
                counter_bad.append({"source_id": sid, "field": field,
                                    "declared": ps[field], "recomputed": computed[field]})
    checks.append(C.compare(
        "v1.per_source_counters", "V1", "per_source identifier/clock counters recompute",
        "records_with_identifiers / _source_public_at / _event_at are reproducible from the rows.",
        "MANIFEST.json:177-394", expected=[], actual=counter_bad,
        evidence={"recomputed": counters},
    ))

    dedupe_bad = []
    dedupe_actual = {}
    for entry in files:
        sid = entry["source_id"]
        rows = records_by_source.get(sid)
        if rows is None:
            continue
        n = len({C.horizon_dedupe_key(r) for r in rows})
        dedupe_actual[sid] = n
        if per_source[sid]["unique_dedupe_keys"] != n:
            dedupe_bad.append({"source_id": sid,
                               "declared": per_source[sid]["unique_dedupe_keys"], "recomputed": n})
    checks.append(C.compare(
        "v1.per_source_dedupe", "V1", "per_source unique_dedupe_keys recompute",
        "unique_dedupe_keys is the distinct count of the documented dedupe_key() per source.",
        "MANIFEST.json:181 etc.; research/horizon/hz/schema.py:232-258",
        expected=[], actual=dedupe_bad, evidence={"recomputed": dedupe_actual},
    ))

    # --------------------------------------------------------------- licence
    licence_bad = []
    for entry in files:
        sid = entry["source_id"]
        declared = per_source[sid]["licence_status"]
        summary = manifest["licence_summary"].get(sid)
        registry = manifest.get("extra", {}).get("registry_snapshot", {}).get(sid, {}).get("licence_status")
        rows = records_by_source.get(sid)
        record_values = sorted({r.get("licence_status") for r in rows}) if rows else None
        if summary != declared or registry != declared:
            licence_bad.append({"source_id": sid, "per_source": declared,
                                "licence_summary": summary, "registry_snapshot": registry})
        if record_values is not None and record_values != [declared]:
            licence_bad.append({"source_id": sid, "per_source": declared, "record_values": record_values})
    checks.append(C.compare(
        "v1.licence_agreement", "V1", "Licence status agrees across manifest views and rows",
        "per_source[].licence_status == licence_summary[] == extra.registry_snapshot[] "
        "== every record's licence_status.",
        "MANIFEST.json:177-425; records", expected=[], actual=licence_bad,
    ))

    # ----------------------------------------------------------- README table
    readme = C.read_text(os.path.join(export_dir, README_NAME))
    table = _parse_readme_table(readme)
    readme_bad = []
    for entry in files:
        sid = entry["source_id"]
        row = table.get(sid)
        if row is None:
            readme_bad.append({"source_id": sid, "issue": "absent from README table"})
            continue
        if sid not in counters:
            continue  # quarantined: no bytes to recompute against
        want = {
            "records": str(counters[sid]["records"]),
            "unique keys": str(dedupe_actual[sid]),
            "with id": str(counters[sid]["records_with_identifiers"]),
            "with public date": str(counters[sid]["records_with_source_public_at"]),
            "licence": per_source[sid]["licence_status"],
        }
        for col, expected in want.items():
            if row.get(col) != expected:
                readme_bad.append({"source_id": sid, "column": col,
                                   "readme": row.get(col), "recomputed": expected})
    checks.append(C.compare(
        "v1.readme_table", "V1", "README per-source table recomputes",
        "The human-readable table states the same counts as the machine artifact.",
        "research/horizon/exports/horizon-2026-11-10/README.md:56-81",
        expected=[], actual=readme_bad,
    ))

    # -------------------------------------------------- record identity unique
    content_bad = []
    identity_bad = []
    identity_extra = 0
    for entry in files:
        sid = entry["source_id"]
        rows = records_by_source.get(sid)
        if not rows:
            continue
        hashes = [r.get("content_hash") for r in rows]
        if len(hashes) != len(set(hashes)):
            content_bad.append({"source_id": sid, "duplicate_content_hashes": len(hashes) - len(set(hashes))})
        counter = {}
        for r in rows:
            counter[r.get("source_record_id")] = counter.get(r.get("source_record_id"), 0) + 1
        dupes = {k: v for k, v in counter.items() if v > 1}
        if dupes:
            identity_extra += sum(v - 1 for v in dupes.values())
            identity_bad.append({"source_id": sid, "records": len(rows),
                                 "distinct_source_record_ids": len(counter),
                                 "extra_rows_sharing_an_id": sum(v - 1 for v in dupes.values()),
                                 "duplicated_ids": dupes})
    checks.append(C.compare(
        "v1.record_content_unique", "V1",
        "No two rows in a source have the same content hash",
        "Rows are deduplicated within a source: identical content must appear once.",
        "research/horizon/exports/horizon-2026-11-10/README.md:14", expected=[], actual=content_bad,
    ))
    checks.append(C.Check(
        "v1.record_identity_key_unique", "V1",
        "source_record_id is unique within a source, so it can be used as a record key",
        "ATLAS's evidence id is a function of (source_id, evidence_type, source_record_id); "
        "a non-unique source_record_id merges distinct records.",
        "medradar/atlas/evidence/schema.py:105-113 vs HORIZON export",
        C.PASS if identity_extra == 0 else C.FAIL,
        expected={"extra_rows_sharing_an_id": 0},
        actual={"extra_rows_sharing_an_id": identity_extra, "sources": identity_bad},
        detail="the shared ids are not duplicates: one PMA number carries several supplements "
               "(distinct content hashes) and one registration number carries several "
               "establishment-type rows; README:14's 'deduplicated within a source' does not "
               "make the id unique",
    ))

    # --------------------------------------------------- quarantine provenance
    horizon_root = ctx.get("horizon_root")
    upstream = os.path.join(horizon_root, "research", "horizon", "exports",
                            "horizon-2026-11-10", QUARANTINED[0]) if horizon_root else None
    if upstream and os.path.exists(upstream):
        entry = next(f for f in files if f["path"] == QUARANTINED[0])
        digest = C.sha256_file(upstream)
        size = os.path.getsize(upstream)
        scan = C.scan_jsonl(upstream)
        checks.append(C.compare(
            "v1.quarantine_provenance", "V1",
            "The quarantined file still matches its manifest entry upstream",
            "Quarantine must withhold a file whose digest is the one the manifest declares, "
            "not a different or truncated file.",
            "MANIFEST.json:162-168 vs worktrees/horizon-001",
            expected={"sha256": entry["sha256"], "bytes": entry["bytes"], "records": entry["records"]},
            actual={"sha256": digest, "bytes": size, "records": scan["lines_nonempty"]},
        ))
    else:
        checks.append(C.unverifiable(
            "v1.quarantine_provenance", "V1",
            "The quarantined file still matches its manifest entry upstream",
            "Quarantine must withhold a file whose digest is the one the manifest declares.",
            "MANIFEST.json:162-168", "upstream horizon-001 export not reachable from this host",
        ))

    facts = {
        "manifest": manifest,
        "records_by_source": records_by_source,
        "scans": scans,
        "counters": counters,
        "dedupe": dedupe_actual,
        "per_source": per_source,
    }
    return checks, facts
