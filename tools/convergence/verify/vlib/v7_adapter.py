"""V7 — adapter fidelity, verified from the adapter's OUTPUT, never its code.

The integration staging database is a moving target while the adapter is being
built, so every verdict here is bound to a frozen snapshot digest and the digest
is printed in the report.

Record-level fidelity is checked by invariants that do not depend on the
adapter's mapping table:

* the four clocks must survive with the same values ('' and None are the same
  absence);
* the multiset of identifier *values* must be conserved (scheme names are
  legitimately renamed, values are not);
* a licence may never become more permissive on import;
* an identity status may never be promoted to ``confirmed`` on import;
* a record that carried quality flags may not arrive with none.
"""

from __future__ import annotations

import collections
import json
import os
import sqlite3

from . import common as C

QUARANTINED_RECORDS = 608
CLOCKS = ("event_at", "source_public_at", "first_observed_at", "fetched_at")

# permissiveness order for the no-upgrade invariant; -1 = unknown (never "more permissive")
LICENCE_RANK = {
    "restricted": 0,
    "terms_restricted": 0,
    "requires_licence": 0,
    "requires_registration": 1,
    "open_no_explicit_licence": 2,
    "open_licence": 3,
    "public_domain": 3,
    "unknown": -1,
}


def _snapshot_digest(path):
    return C.sha256_file(path) if os.path.exists(path) else None


def _connect(path):
    con = sqlite3.connect("file:" + path.replace("\\", "/") + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _norm(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _norm_clock(value):
    """Absence, date and midnight-UTC are the same instant at day resolution.

    The importer widens a plain date to ``YYYY-MM-DDT00:00:00Z``; that is a
    representation change, not a value change, and it is counted separately.
    """
    text = _norm(value)
    if text is None:
        return None
    if len(text) >= 19 and text.endswith("Z") and text[11:19] == "00:00:00":
        return text[:10]
    if len(text) >= 19 and text[11:19] == "00:00:00" and text[19:25] in ("+00:00", "-00:00"):
        return text[:10]
    return text


def _discover_report(root, run_id):
    """Newest integration report for the run under verification."""
    reports_dir = os.path.join(root, "research", "convergence", "reports")
    if not os.path.isdir(reports_dir):
        return None, None
    candidates = []
    for name in os.listdir(reports_dir):
        if not (name.startswith("integration_") and name.endswith(".json")):
            continue
        path = os.path.join(reports_dir, name)
        try:
            payload = C.read_json(path)
        except (ValueError, OSError):
            continue
        if payload.get("run_id") == run_id:
            candidates.append((os.path.getmtime(path), path, payload))
    if not candidates:
        return None, None
    candidates.sort()
    _, path, payload = candidates[-1]
    return os.path.relpath(path, root).replace("\\", "/"), payload


def _same_work_pairs(records_by_source):
    """Recompute DOI-shared cross-source pairs: the graph's SAME_WORK claim."""
    by_doi = collections.defaultdict(set)
    for sid, rows in records_by_source.items():
        for rec in rows:
            for ident in rec.get("identifiers") or []:
                if ident.get("scheme") == "doi" and ident.get("value"):
                    by_doi[ident["value"].strip().lower()].add((sid, rec.get("source_record_id")))
    pairs = 0
    dois = 0
    for _, members in by_doi.items():
        if len({m[0] for m in members}) > 1:
            dois += 1
            pairs += sum(1 for a in members for b in members
                         if a[0] < b[0] or (a[0] == b[0] and a[1] < b[1]))
    return pairs, dois


def _fidelity(con, records, max_examples=10):
    """Compare every export record against the evidence rows it became."""
    evidence = collections.defaultdict(list)
    for row in con.execute(
            "SELECT evidence_id, version, source_id, source_record_id, event_at, source_public_at, "
            "first_observed_at, fetched_at, licence_status, identity_status, quality_flags "
            "FROM evidence"):
        evidence[(row["source_id"], row["source_record_id"])].append(dict(row))
    identifiers = collections.defaultdict(list)
    for row in con.execute("SELECT evidence_id, version, scheme, value FROM evidence_identifiers"):
        identifiers[(row["evidence_id"], row["version"])].append(
            (row["scheme"], str(row["value"])))

    export_keys = set()
    clock_bad, id_bad, licence_bad, identity_bad, flag_bad = [], [], [], [], []
    missing = []
    compared = 0
    for sid, rows in records.items():
        groups = collections.defaultdict(list)
        for rec in rows:
            groups[rec.get("source_record_id")].append(rec)
            export_keys.add((sid, rec.get("source_record_id")))
        for record_id, recs in groups.items():
            key = (sid, record_id)
            versions = evidence.get(key)
            if not versions:
                missing.append(key)
                continue
            compared += len(recs)
            # multisets, so the collapse of N distinct records into N versions is compared
            # as a multiset rather than by occurrence order
            export_clocks = sorted(tuple(_norm_clock(r.get(c)) for c in CLOCKS) for r in recs)
            got_clocks = sorted(tuple(_norm_clock(v.get(c)) for c in CLOCKS) for v in versions)
            widened = sum(1 for r in recs for c in CLOCKS
                          if _norm(r.get(c)) and _norm_clock(r.get(c)) != _norm(r.get(c)))
            if export_clocks != got_clocks:
                clock_bad.append({"source_id": sid, "source_record_id": record_id,
                                  "export": [dict(zip(CLOCKS, c)) for c in export_clocks][:4],
                                  "import": [dict(zip(CLOCKS, c)) for c in got_clocks][:4]})
            export_ids = sorted(str(i.get("value")) for r in recs
                                for i in (r.get("identifiers") or []))
            got_ids = sorted(str(v) for ver in versions
                             for (_, v) in identifiers.get((ver["evidence_id"], ver["version"]), []))
            if export_ids != got_ids:
                id_bad.append({"source_id": sid, "source_record_id": record_id,
                               "export_values": export_ids, "import_values": got_ids})
            for rec, ver in zip(sorted(recs, key=lambda r: _norm(r.get("fetched_at")) or ""),
                                sorted(versions, key=lambda v: (v["evidence_id"], v["version"]))):
                lic_export = rec.get("licence_status")
                lic_import = ver["licence_status"]
                if (LICENCE_RANK.get(lic_import, -1) > LICENCE_RANK.get(lic_export, -1)
                        and LICENCE_RANK.get(lic_export, -1) >= 0):
                    licence_bad.append({"source_id": sid, "source_record_id": record_id,
                                        "export": lic_export, "import": lic_import})
                if (ver["identity_status"] == "confirmed"
                        and rec.get("identity_status") != "CONFIRMED"):
                    identity_bad.append({"source_id": sid, "source_record_id": record_id,
                                         "export": rec.get("identity_status"),
                                         "import": ver["identity_status"]})
                try:
                    flags = json.loads(ver["quality_flags"] or "[]")
                except ValueError:
                    flags = []
                if rec.get("quality_flags") and not flags:
                    flag_bad.append({"source_id": sid, "source_record_id": record_id,
                                     "export_flags": rec.get("quality_flags"), "import_flags": []})
    invented = sorted(k for k in evidence if k not in export_keys)
    collapsed = {k: len(v) for k, v in evidence.items() if len(v) > 1}
    return {
        "export_records": sum(len(v) for v in records.values()),
        "distinct_record_identities": len(export_keys),
        "evidence_versions": sum(len(v) for v in evidence.values()),
        "evidence_identities": len(evidence),
        "missing_from_import": missing[:max_examples],
        "n_missing_from_import": len(missing),
        "invented_in_import": invented[:max_examples],
        "n_invented_in_import": len(invented),
        "compared": compared,
        "clock_mismatches": clock_bad[:max_examples],
        "n_clock_mismatches": len(clock_bad),
        "identifier_mismatches": id_bad[:max_examples],
        "n_identifier_mismatches": len(id_bad),
        "licence_upgrades": licence_bad[:max_examples],
        "n_licence_upgrades": len(licence_bad),
        "identity_upgrades": identity_bad[:max_examples],
        "n_identity_upgrades": len(identity_bad),
        "flags_dropped": flag_bad[:max_examples],
        "n_flags_dropped": len(flag_bad),
        "collapsed_identities": {("%s|%s" % k): v for k, v in list(collapsed.items())[:10]},
        "n_collapsed_identities": len(collapsed),
    }


def run(ctx, export_facts):
    group = "V7"
    checks = []
    root = ctx["root"]
    records = export_facts["records_by_source"]
    manifest = export_facts["manifest"]
    module_dir = os.path.join(root, "medradar", "integration")
    modules = []
    if os.path.isdir(module_dir):
        modules = sorted(f[:-3] for f in os.listdir(module_dir)
                         if f.endswith(".py") and f != "__init__.py")
    checks.append(C.Check(
        "v7.adapter_present", group,
        "The integration adapter exists (phase gate)",
        "V7 runs only after medradar/integration/ exists.",
        "task brief V7", C.PASS if modules else C.UNVERIFIABLE,
        expected=None, actual={"modules": modules},
        detail="V7 verifies output data only; no adapter module is imported",
    ))
    if not modules:
        return checks, {}

    snap_dir = os.path.join(root, "research", "convergence", "verification", "snapshots")
    snap = ctx.get("staging_snapshot") or os.path.join(snap_dir, "convergence_staging_snapshot.sqlite")
    rejected_snap = os.path.join(snap_dir, "convergence_staging_snapshot_rejected.sqlite")
    digest = _snapshot_digest(snap)
    rejected_digest = _snapshot_digest(rejected_snap)
    report_path = os.path.join(root, "research", "convergence", "reports",
                               "integration_conv_smoke_001.json")
    report = C.read_json(report_path) if os.path.exists(report_path) else None
    expected_records = sum(e["records"] for e in manifest["files"]) - QUARANTINED_RECORDS

    # ------------------------------------------------ manifest digest integrity
    actual_manifest = C.sha256_file(os.path.join(ctx["export_dir"], "MANIFEST.json"))
    recorded = report.get("integrity", {}).get("manifest_sha256") if report else None
    checks.append(C.compare(
        "v7.manifest_digest", group,
        "The adapter records the manifest digest it actually consumed",
        "conv report integrity.manifest_sha256 must be the digest of MANIFEST.json.",
        "research/convergence/reports/integration_conv_smoke_001.json integrity",
        expected=actual_manifest, actual=recorded,
        detail="integration snapshot digest=%s" % digest,
    ))

    if digest is None:
        checks.append(C.unverifiable(
            "v7.run_state", group, "The import run produced evidence records",
            "an import must convert, not silently drop, the frozen export",
            "staging database", "no frozen snapshot of the staging database available"))
        return checks, {}

    con = _connect(snap)
    runs = [dict(r) for r in con.execute("SELECT * FROM conv_runs")]
    evidence_rows = con.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    head_rows = con.execute("SELECT COUNT(*) FROM evidence_head").fetchone()[0]
    version_rows = con.execute("SELECT COUNT(*) FROM evidence WHERE version>1").fetchone()[0]
    conversions = {r["status"]: r["n"] for r in con.execute(
        "SELECT status, COUNT(*) n FROM conv_conversions GROUP BY 1")}
    reasons = {r["reason"]: r["n"] for r in con.execute(
        "SELECT reason, COUNT(*) n FROM conv_conversions GROUP BY 1 ORDER BY 2 DESC")}
    rejections = con.execute("SELECT COUNT(*) FROM conv_rejections").fetchone()[0]
    relations = {r["relation_type"]: r["n"] for r in con.execute(
        "SELECT relation_type, COUNT(*) n FROM entity_relations GROUP BY 1")}
    rejected_total = sum(r.get("rejected") or 0 for r in runs)

    checks.append(C.Check(
        "v7.run_state", group,
        "The import run produced evidence records from the frozen export",
        "An adapter that rejects 100% of a valid export has not integrated it.",
        "research/convergence/staging/convergence.sqlite (frozen snapshot %s)" % digest,
        C.PASS if evidence_rows == expected_records else C.FAIL,
        expected={"records_seen": expected_records, "evidence_rows": expected_records},
        actual={"runs": [{k: r[k] for k in ("run_id", "status", "records_seen", "converted",
                                            "degraded", "rejected", "evidence_inserted",
                                            "evidence_noop", "policy_id")} for r in runs],
                "evidence_rows": evidence_rows, "evidence_head_rows": head_rows,
                "evidence_versions_beyond_first": version_rows,
                "conversions": conversions, "conversion_reasons": reasons,
                "conv_rejections": rejections},
        detail="snapshot holds %d evidence versions / %d identities for %d importable records; "
               "%d rejected" % (evidence_rows, head_rows, expected_records, rejected_total),
    ))

    logging_ok = rejections == rejected_total
    checks.append(C.Check(
        "v7.rejections_logged", group,
        "Rejected records are logged with their reason, not dropped",
        "task brief V7: rejected records must be logged.",
        "conv_rejections vs conv_runs.rejected",
        C.PASS if logging_ok else C.FAIL,
        expected={"rejections": rejected_total},
        actual={"conv_rejections": rejections, "conv_runs_rejected": rejected_total},
    ))

    # the earlier all-reject state, kept as evidence rather than as the current verdict
    if rejected_digest:
        rcon = _connect(rejected_snap)
        r_runs = [dict(r) for r in rcon.execute("SELECT * FROM conv_runs")]
        r_evidence = rcon.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
        r_rejections = rcon.execute("SELECT COUNT(*) FROM conv_rejections").fetchone()[0]
        rcon.close()
        checks.append(C.Check(
            "v7.rejected_state_observed", group,
            "A missing licence policy was observed rejecting the entire export as 'complete'",
            "A fail-closed policy must abort, not report a successful run that imported nothing.",
            "archived snapshot research/convergence/verification/snapshots/"
            "convergence_staging_snapshot_rejected.sqlite (%s)" % rejected_digest,
            C.FAIL if (r_evidence == 0 and r_runs and r_runs[0].get("rejected") == expected_records) else C.PASS,
            expected={"evidence_rows": expected_records},
            actual={"runs": [{k: r[k] for k in ("run_id", "status", "records_seen", "converted",
                                                "rejected", "evidence_inserted", "policy_id")}
                             for r in r_runs],
                    "evidence_rows": r_evidence, "conv_rejections": r_rejections},
            detail="kept because it is a reproducible failure mode of the licence gate: every "
                   "class was blocked, including public_domain, and the run status was 'complete'",
        ))

    # ---------------------------------------------------- record-level fidelity
    fidelity = _fidelity(con, records) if evidence_rows else None
    if fidelity:
        checks.append(C.Check(
            "v7.coverage_one_to_one", group,
            "Every export record maps to an evidence row and no evidence row is invented",
            "Import must be a bijection on records modulo the declared identity collapse.",
            "staging evidence vs frozen export",
            C.PASS if (fidelity["n_missing_from_import"] == 0
                       and fidelity["n_invented_in_import"] == 0) else C.FAIL,
            expected={"missing": 0, "invented": 0,
                      "evidence_versions": fidelity["export_records"]},
            actual={"missing": fidelity["n_missing_from_import"],
                    "invented": fidelity["n_invented_in_import"],
                    "evidence_versions": fidelity["evidence_versions"],
                    "evidence_identities": fidelity["evidence_identities"],
                    "distinct_export_record_identities": fidelity["distinct_record_identities"]},
            detail="%d collapsed identities hold more than one version: %s"
                   % (fidelity["n_collapsed_identities"], json.dumps(fidelity["collapsed_identities"])),
        ))
        checks.append(C.Check(
            "v7.four_clocks_preserved", group,
            "All four clocks survive import with the same values",
            "task brief V7: the four clocks must be preserved record by record.",
            "staging evidence.* vs export record clocks",
            C.PASS if fidelity["n_clock_mismatches"] == 0 else C.FAIL,
            expected={"mismatches": 0},
            actual={"mismatches": fidelity["n_clock_mismatches"],
                    "compared": fidelity["compared"],
                    "examples": fidelity["clock_mismatches"]},
        ))
        checks.append(C.Check(
            "v7.identifiers_preserved", group,
            "The identifier value set survives import unchanged",
            "task brief V7: source identifiers must be preserved (scheme names may be renamed).",
            "staging evidence_identifiers vs export identifiers",
            C.PASS if fidelity["n_identifier_mismatches"] == 0 else C.FAIL,
            expected={"mismatches": 0},
            actual={"mismatches": fidelity["n_identifier_mismatches"],
                    "examples": fidelity["identifier_mismatches"]},
        ))
        checks.append(C.Check(
            "v7.licence_not_upgraded", group,
            "No record's licence becomes more permissive on import",
            "task brief V7: licence status must not be silently weakened.",
            "staging evidence.licence_status vs export licence_status",
            C.PASS if fidelity["n_licence_upgrades"] == 0 else C.FAIL,
            expected={"upgrades": 0},
            actual={"upgrades": fidelity["n_licence_upgrades"],
                    "examples": fidelity["licence_upgrades"]},
        ))
        checks.append(C.Check(
            "v7.no_identity_upgrade", group,
            "No record's identity status was promoted to confirmed on import",
            "task brief V7: nothing may be silently promoted from UNKNOWN/candidate to confirmed.",
            "staging evidence.identity_status vs export identity_status",
            C.PASS if fidelity["n_identity_upgrades"] == 0 else C.FAIL,
            expected={"upgrades": 0},
            actual={"upgrades": fidelity["n_identity_upgrades"],
                    "examples": fidelity["identity_upgrades"],
                    "import_identity_status": {r["identity_status"]: r["n"] for r in con.execute(
                        "SELECT identity_status, COUNT(*) n FROM evidence GROUP BY 1")}},
            detail="HORIZON records with identity_status=CONFIRMED are source-asserted entity "
                   "identities; the importer maps all of them to not_attempted, which is a "
                   "downgrade of the label and a loss of the source's own assertion",
        ))
        checks.append(C.Check(
            "v7.quality_flags_not_dropped", group,
            "A record that carried quality flags does not arrive with none",
            "task brief V7: quality flags must be preserved or explicitly degraded.",
            "staging evidence.quality_flags vs export quality_flags",
            C.PASS if fidelity["n_flags_dropped"] == 0 else C.FAIL,
            expected={"records_with_flags_imported_flagless": 0},
            actual={"records_with_flags_imported_flagless": fidelity["n_flags_dropped"],
                    "examples": fidelity["flags_dropped"]},
        ))
    else:
        for check_id, title in (
            ("v7.coverage_one_to_one", "Every export record maps to an evidence row"),
            ("v7.four_clocks_preserved", "All four clocks survive import with the same values"),
            ("v7.identifiers_preserved", "The identifier value set survives import unchanged"),
            ("v7.licence_not_upgraded", "No record's licence becomes more permissive on import"),
            ("v7.no_identity_upgrade", "No identity status was promoted to confirmed"),
            ("v7.quality_flags_not_dropped", "Quality flags survive import"),
        ):
            checks.append(C.unverifiable(check_id, group, title, "task brief V7",
                                         "staging database",
                                         "the frozen snapshot holds no evidence rows"))

    # ------------------------------------------- report arithmetic (smoke run)
    if report:
        imp = report.get("import", {})
        run_block = report.get("run", {})
        consistent = (imp.get("seen") == run_block.get("records_seen")
                      and imp.get("degraded") == run_block.get("degraded"))
        checks.append(C.Check(
            "v7.smoke_report_internal_consistency", group,
            "The import report states one set of run counters",
            "A report whose own blocks disagree cannot support any downstream number.",
            "research/convergence/reports/integration_conv_smoke_001.json import vs run",
            C.PASS if consistent else C.FAIL,
            expected={"seen": expected_records},
            actual={"import_block": {k: imp.get(k) for k in ("seen", "converted", "degraded", "rejected")},
                    "run_block": {k: run_block.get(k) for k in ("records_seen", "converted", "degraded", "rejected")}},
            detail="the difference is exactly the record-identity collisions: the two blocks count "
                   "different units (records vs distinct evidence identities) under the same names",
        ))
        checks.append(C.compare(
            "v7.smoke_report_seen", group,
            "The smoke report's record count equals the export minus the quarantine",
            "6,492 declared - 608 quarantined UN Comtrade records = 5,884 importable records.",
            "MANIFEST.json totals; integration report", expected=expected_records,
            actual=imp.get("seen"),
            detail="run block says %s, import block says %s" % (run_block.get("records_seen"), imp.get("seen")),
        ))
        recomputed_ids = {}
        for entry in manifest["files"]:
            sid = entry["source_id"]
            rows = records.get(sid)
            if rows is None:
                continue
            recomputed_ids[sid] = len({(r.get("source_id"), r.get("entity_type"), r.get("source_record_id"))
                                       for r in rows})
        claimed_ids = report.get("stats", {}).get("evidence_by_source", {})
        diff = [{"source_id": sid, "report": claimed_ids.get(sid), "recomputed": n}
                for sid, n in recomputed_ids.items() if claimed_ids.get(sid) != n]
        checks.append(C.compare(
            "v7.smoke_report_evidence_ids", group,
            "Per-source evidence counts equal distinct (source_id, entity_type, source_record_id)",
            "The adapter's evidence id is defined on that triple, so its per-source counts are "
            "forced by it.",
            "report stats.evidence_by_source vs recomputed triples",
            expected=[], actual=diff,
            evidence={"recomputed": recomputed_ids, "claimed": claimed_ids},
        ))
        dist = collections.Counter()
        per_source_licence = {p["source_id"]: p["licence_status"] for p in manifest["per_source"]}
        for entry in manifest["files"]:
            sid = entry["source_id"]
            rows = records.get(sid)
            if rows is None:
                continue
            triples = {(r.get("source_id"), r.get("entity_type"), r.get("source_record_id")) for r in rows}
            dist[per_source_licence[sid]] += len(triples)
        claimed_dist = report.get("stats", {}).get("conv_licence_status", {})
        ldiff = [{"status": k, "report": claimed_dist.get(k), "recomputed": v}
                 for k, v in dist.items() if claimed_dist.get(k) != v]
        checks.append(C.compare(
            "v7.smoke_report_licence_distribution", group,
            "The imported licence distribution preserves the export's licences",
            "No record may change licence class on import (no 'restricted' may become 'open').",
            "report stats.conv_licence_status", expected=[], actual=ldiff,
            evidence={"recomputed": dict(dist), "claimed": claimed_dist},
        ))
    else:
        for check_id, title in (
            ("v7.smoke_report_internal_consistency", "The import report states one set of run counters"),
            ("v7.smoke_report_seen", "The smoke report's record count equals the export minus quarantine"),
            ("v7.smoke_report_evidence_ids", "Per-source evidence counts equal distinct record identities"),
            ("v7.smoke_report_licence_distribution", "The imported licence distribution is preserved"),
        ):
            checks.append(C.unverifiable(check_id, group, title, "import report",
                                         report_path, "report not present"))

    # ---------------------------------------- record-identity collisions upstream
    collisions = []
    for entry in manifest["files"]:
        sid = entry["source_id"]
        rows = records.get(sid)
        if not rows:
            continue
        counter = collections.Counter((r.get("entity_type"), r.get("source_record_id")) for r in rows)
        extra = sum(v - 1 for v in counter.values() if v > 1)
        if extra:
            example = next(k for k, v in counter.items() if v > 1)
            sample = [r for r in rows if (r.get("entity_type"), r.get("source_record_id")) == example]
            collisions.append({"source_id": sid, "records": len(rows),
                               "distinct_record_identities": len(counter),
                               "extra_records_sharing_an_id": extra,
                               "example_id": example[1],
                               "example_distinct_content_hashes": len({r.get("content_hash") for r in sample})})
    total_extra = sum(c["extra_records_sharing_an_id"] for c in collisions)
    checks.append(C.Check(
        "v7.record_identity_collisions", group,
        "Record identity is preserved: distinct records do not collapse into one evidence id",
        "ATLAS evidence_id = f(source_id, evidence_type, source_record_id). If source_record_id "
        "is not unique, distinct records silently become versions of one record.",
        "medradar/atlas/evidence/schema.py:105-113 vs HORIZON export",
        C.PASS if total_extra == 0 else C.FAIL,
        expected={"records_sharing_an_id": 0},
        actual={"total_extra_records_sharing_an_id": total_extra,
                "sources": collisions,
                "adapter_as_duplicate_versions": version_rows,
                "adapter_head_rows": head_rows},
        detail="the collided rows are not duplicates: one PMA number carries several supplements "
               "(S514/S136/S413/S837) with distinct content hashes, and one registration number "
               "carries several establishment-type rows; stored as versions they vanish from "
               "evidence_head",
    ))

    # -------------------------------------------------------- SAME_WORK pairs
    pairs, dois = _same_work_pairs(records)
    claimed = (report or {}).get("graph", {}).get("authoritative_links", {}).get("created")
    checks.append(C.compare(
        "v7.same_work_recompute", group,
        "Cross-source DOI pairs recompute to the claimed SAME_WORK relation count",
        "The graph adds 672 SAME_WORK relations from 672 cross-source DOI matches.",
        "report graph.authoritative_links", expected=claimed, actual=pairs,
        detail="recomputed on %d shared DOI values across sources" % dois,
        evidence={"cross_source_dois": dois},
    ))

    # ------------------------------------------------------------ not verifiable
    for check_id, title, why in (
        ("v7.idempotency", "Importing twice produces no duplicate logical records",
         "the snapshot holds one run; idempotency needs two completed runs "
         "(evidence_noop=%s, versions beyond first=%s are collisions, not re-imports)"
         % ([r.get("evidence_noop") for r in runs], version_rows)),
        ("v7.atlas_bridge_carried", "ATLAS's 934 confirmed relations are carried into the store",
         "staging entity_relations holds only %s; the ATLAS bridge was not imported" % json.dumps(relations)),
    ):
        checks.append(C.unverifiable(check_id, group, title, "task brief V7", "staging database", why))

    con.close()
    facts = {"snapshot": snap, "snapshot_sha256": digest,
             "rejected_snapshot_sha256": rejected_digest,
             "runs": runs, "evidence_rows": evidence_rows, "head_rows": head_rows,
             "version_rows": version_rows, "relations": relations,
             "collisions": collisions, "fidelity": fidelity}
    return checks, facts
