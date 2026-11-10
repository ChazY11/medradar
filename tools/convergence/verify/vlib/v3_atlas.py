"""V3 — the ATLAS 934 cross-market device bridge, re-derived from the database.

Everything here is recomputed with plain SQL against a read-only connection plus
the documented hash/identifier rules. identity_pilot.json is treated as a claim,
not as evidence.
"""

from __future__ import annotations

import collections
import json
import os
import sqlite3

from . import common as C

REL_TYPE = "SAME_DEVICE_IDENTITY"


def _connect(path):
    return sqlite3.connect("file:" + path.replace("\\", "/") + "?mode=ro", uri=True)


def _json(path):
    if not os.path.exists(path):
        return None
    try:
        return C.read_json(path)
    except ValueError:
        return None


def _mdall_cache_counts(cache_path):
    """Stream the 220 MB MDALL identifier cache and recount the GTIN subset.

    The document's rule is "normalised to a 14-digit DI when separators were
    removed". Three readings are computed; only the hyphen+space reading
    reproduces the published 5,512 / 5,005 exactly, so that is the rule the
    claim is tested against and the other two are reported as sensitivity.
    """
    rows = 0
    bare14 = 0
    digits_only = [0, set()]
    hyphen_space = [0, set()]
    all_non_alnum = [0, set()]
    for obj in C.iter_json_array(cache_path):
        rows += 1
        value = obj.get("device_identifier")
        if not isinstance(value, str):
            continue
        if len(value) == 14 and value.isdigit():
            bare14 += 1
        candidates = {
            "digits_only": "".join(ch for ch in value if ch.isdigit()),
            "hyphen_space": value.replace("-", "").replace(" ", ""),
            "all_non_alnum": "".join(ch for ch in value if ch.isalnum()),
        }
        for name, candidate in candidates.items():
            if len(candidate) == 14 and candidate.isdigit():
                if name == "digits_only":
                    digits_only[0] += 1
                    digits_only[1].add(candidate)
                elif name == "hyphen_space":
                    hyphen_space[0] += 1
                    hyphen_space[1].add(candidate)
                else:
                    all_non_alnum[0] += 1
                    all_non_alnum[1].add(candidate)
    return {
        "rows": rows,
        "bare_14_digit": bare14,
        "normalised_rows": hyphen_space[0],
        "unique_normalised": len(hyphen_space[1]),
        "normalised_values": hyphen_space[1],
        "sensitivity": {
            "hyphen_space": {"rows": hyphen_space[0], "unique": len(hyphen_space[1])},
            "digits_only": {"rows": digits_only[0], "unique": len(digits_only[1])},
            "all_non_alnum": {"rows": all_non_alnum[0], "unique": len(all_non_alnum[1])},
        },
    }


def run(ctx):
    group = "V3"
    checks = []
    db_path = ctx["atlas_db"]
    atlas_root = ctx["atlas_root"]
    reports = os.path.join(atlas_root, "research", "atlas", "reports")
    pilot = _json(os.path.join(reports, "identity_pilot.json"))
    baseline = _json(os.path.join(reports, "identity_baseline_eval.json"))

    if not os.path.exists(db_path):
        return [C.unverifiable("v3.relation_count", group, "ATLAS database readable",
                               "934 CONFIRMED SAME_DEVICE_IDENTITY relations", db_path,
                               "read-only original database not reachable")], {}

    con = _connect(db_path)
    con.row_factory = sqlite3.Row

    rels = con.execute(
        "SELECT * FROM entity_relations WHERE relation_type=?", (REL_TYPE,)
    ).fetchall()
    bases = [json.loads(r["basis_json"]) for r in rels]
    shared = [b.get("shared_identifier") for b in bases]
    pairs = [(r["from_ref"], r["to_ref"]) for r in rels]

    # ------------------------------------------------------------------ count
    checks.append(C.compare(
        "v3.relation_count", group, "Count of CONFIRMED SAME_DEVICE_IDENTITY relations",
        "ATLAS holds 934 confirmed same-device identity relations across US and Canadian registries.",
        "docs/atlas/RESEARCH_VALIDATION.md:69; identity_pilot.json counts.bridge_pairs",
        expected=934, actual=len(rels),
        detail="SELECT COUNT(*) FROM entity_relations WHERE relation_type='SAME_DEVICE_IDENTITY' AND status='CONFIRMED'",
    ))

    status_bad = [r["relation_id"] for r in rels if r["status"] != "CONFIRMED"]
    method_odd = collections.Counter((r["method"], r["authority"], r["confidence"]) for r in rels)
    checks.append(C.Check(
        "v3.relation_status_method", group,
        "Every relation is CONFIRMED and derived from an official identifier",
        "934 relations are method=official_identifier, authority=source_declared, confidence 0.99.",
        "identity_pilot.json counts.bridge_confirmed_identity; RESEARCH_VALIDATION.md:69",
        C.PASS if not status_bad and set(method_odd) == {("official_identifier", "source_declared", 0.99)} else C.FAIL,
        expected={"status": "CONFIRMED", "method_authority_confidence": [["official_identifier", "source_declared", 0.99]]},
        actual={"non_confirmed": status_bad,
                "method_authority_confidence": [[m, a, c] for (m, a, c) in sorted(method_odd)]},
    ))

    # -------------------------------------------------------------- uniqueness
    dup_pairs = len(pairs) - len(set(pairs))
    dup_ids = len(rels) - len({r["relation_id"] for r in rels})
    checks.append(C.compare(
        "v3.pair_uniqueness", group,
        "Relation rows and (from_ref, to_ref) pairs are unique",
        "The 934 is a count of pairs, not of duplicated rows.",
        "task brief (duplicate check)", expected={"duplicate_pairs": 0, "duplicate_relation_ids": 0},
        actual={"duplicate_pairs": dup_pairs, "duplicate_relation_ids": dup_ids},
        detail="rows=%d distinct_pairs=%d distinct_from=%d distinct_to=%d"
               % (len(rels), len(set(pairs)),
                  len({p[0] for p in pairs}), len({p[1] for p in pairs})),
    ))

    # ------------------------------------------------------- shared identifier
    null_shared = sum(1 for s in shared if not s)
    distinct_shared = len(set(shared))
    per_id = collections.Counter(shared)
    many = {k: v for k, v in per_id.items() if v > 1}
    checks.append(C.Check(
        "v3.shared_identifier_distinct", group,
        "934 relations carry 934 distinct shared identifiers (one GTIN -> one pair)",
        "Each relation's basis records the shared DI; a single GTIN must not fan out into many pairs.",
        "task brief (one GTIN -> many pairs)", 
        C.PASS if null_shared == 0 and distinct_shared == len(rels) else C.FAIL,
        expected={"distinct": len(rels), "null": 0, "gtins_with_multiple_pairs": 0},
        actual={"distinct": distinct_shared, "null": null_shared,
                "gtins_with_multiple_pairs": len(many),
                "max_pairs_per_gtin": max(per_id.values()) if per_id else 0},
        evidence={"max_pairs_per_gtin": max(per_id.values()) if per_id else 0},
    ))

    # ------------------------------------------------------------- GTIN valid
    bad_gtin = []
    for s in sorted(set(shared)):
        if not s or not s.startswith("di:"):
            bad_gtin.append({"value": s, "reason": "not a di: identifier"})
            continue
        value = s[3:]
        if len(value) != 14:
            bad_gtin.append({"value": s, "reason": "length %d" % len(value)})
        elif not value.isdigit():
            bad_gtin.append({"value": s, "reason": "non-numeric"})
        elif not C.is_gtin14(value):
            bad_gtin.append({"value": s, "reason": "mod-10 check digit"})
    checks.append(C.compare(
        "v3.gtin14_valid", group,
        "Every shared identifier is a GTIN-14 with a correct Mod-10 check digit",
        "The bridge label is 'MDALL GTIN-14 identifier equals GUDID UDI-DI'.",
        "docs/atlas/RESEARCH_VALIDATION.md:14,31", expected=[], actual=bad_gtin,
        detail="validated %d distinct di values; independent GS1 Mod-10 implementation" % len(set(shared)),
    ))

    # ------------------------------------------------------------- revocation
    revoked = [r["relation_id"] for r in rels if (r["revoked_at"] or "").strip()]
    revoked_any = con.execute(
        "SELECT COUNT(*) FROM entity_relations WHERE (revoked_at IS NOT NULL AND TRIM(revoked_at)<>'')"
    ).fetchone()[0]
    checks.append(C.compare(
        "v3.revocation", group,
        "No bridge relation has been revoked",
        "The confirmed set is final, not a superseded intermediate.",
        "identity_pilot.json counts.bridge_contradicted=0", expected={"bridge_revoked": 0, "any_revoked": 0},
        actual={"bridge_revoked": len(revoked), "any_revoked": revoked_any},
    ))

    # --------------------------------------------------- duplication across runs
    by_run = collections.Counter(r["run_id"] for r in rels)
    checks.append(C.Check(
        "v3.duplication_across_runs", group,
        "All 934 relations come from a single bridge run",
        "Re-running the bridge must not duplicate relations.",
        "entity_relations.run_id",
        C.PASS if len(by_run) == 1 else C.FAIL,
        expected={"runs": 1},
        actual={"runs": len(by_run), "by_run": dict(by_run)},
    ))

    # ------------------------------------------- shared id present on both sides
    hit_ev = hit_dev = 0
    for (from_ref, to_ref), s in zip(pairs, shared):
        value = (s or "")[3:]
        if con.execute(
            "SELECT 1 FROM evidence_identifiers WHERE evidence_id=? AND scheme='di' AND value=? LIMIT 1",
            (from_ref, value)).fetchone():
            hit_ev += 1
        if con.execute(
            "SELECT 1 FROM device_identifiers WHERE device_id=? AND scheme='di' AND value=? LIMIT 1",
            (to_ref, value)).fetchone():
            hit_dev += 1
    checks.append(C.compare(
        "v3.shared_id_present_both_sides", group,
        "The shared DI is physically present on both records of every pair",
        "A SAME_DEVICE_IDENTITY claim is only substantiated if the identifier is stored on both sides.",
        "task brief (re-derive the bridge)", expected={"evidence_side": len(rels), "device_side": len(rels)},
        actual={"evidence_side": hit_ev, "device_side": hit_dev},
    ))

    # ------------------------------------------------------------- CA-side scope
    src_counter = collections.Counter()
    for from_ref, _ in pairs:
        row = con.execute("SELECT source_id FROM evidence WHERE evidence_id=?", (from_ref,)).fetchone()
        src_counter[row[0] if row else "MISSING"] += 1
    to_schemes = collections.Counter()
    markets = collections.Counter()
    for _, to_ref in pairs:
        schemes = {r[0] for r in con.execute(
            "SELECT DISTINCT scheme FROM device_identifiers WHERE device_id=?", (to_ref,))}
        for s in schemes:
            to_schemes[s] += 1
        row = con.execute("SELECT markets_json FROM devices WHERE device_id=?", (to_ref,)).fetchone()
        markets[row[0] if row else "MISSING"] += 1
    checks.append(C.Check(
        "v3.cross_market_scope", group,
        "Each pair really spans a US record and a Canadian record",
        "The 934 are described as cross-market (U.S. GUDID <-> Canadian MDALL).",
        "docs/atlas/RESEARCH_VALIDATION.md:69",
        C.PASS if src_counter.get("openfda_device_udi") == len(rels)
        and to_schemes.get("licence_no") == len(rels) else C.FAIL,
        expected={"us_side_source": "openfda_device_udi", "ca_side_scheme": "licence_no"},
        actual={"us_side_sources": dict(src_counter),
                "ca_side_schemes": {k: v for k, v in to_schemes.items()},
                "ca_device_markets": dict(markets)},
    ))

    # -------------------------------------------------------- referential integrity
    missing = []
    for from_ref, to_ref in pairs:
        if not con.execute("SELECT 1 FROM evidence WHERE evidence_id=?", (from_ref,)).fetchone():
            missing.append({"from_ref": from_ref, "issue": "evidence missing"})
        if not con.execute("SELECT 1 FROM devices WHERE device_id=?", (to_ref,)).fetchone():
            missing.append({"to_ref": to_ref, "issue": "device missing"})
    checks.append(C.compare(
        "v3.referential_integrity", group,
        "Both endpoints of every relation exist",
        "A relation pointing at a missing row would be a phantom confirmation.",
        "task brief", expected=[], actual=missing[:20],
        detail="dangling endpoints=%d" % len(missing),
    ))

    # ------------------------------------------------ evidence id / hash recompute
    ev_rows = con.execute(
        "SELECT evidence_id, version, content_hash, evidence_type, source_id, source_record_id, "
        "canonical_key, payload_json FROM evidence").fetchall()
    id_bad = []
    hash_bad = []
    key_bad = []
    for row in ev_rows:
        expected_id = C.atlas_make_evidence_id(row["source_id"], row["evidence_type"], row["source_record_id"])
        if expected_id != row["evidence_id"]:
            id_bad.append({"declared": row["evidence_id"], "recomputed": expected_id,
                           "source_id": row["source_id"], "source_record_id": row["source_record_id"]})
        try:
            payload = json.loads(row["payload_json"])
        except ValueError:
            payload = None
        if payload is not None:
            normalized = payload.get("normalized") if isinstance(payload, dict) else None
            if isinstance(normalized, dict):
                recomputed = C.sha256_json(normalized)
                if recomputed != row["content_hash"]:
                    hash_bad.append({"evidence_id": row["evidence_id"],
                                     "declared": row["content_hash"], "recomputed": recomputed})
        ids = [{"scheme": r["scheme"], "value": r["value"], "is_primary": bool(r["is_primary"])}
               for r in con.execute(
                   "SELECT scheme, value, is_primary FROM evidence_identifiers WHERE evidence_id=? AND version=?",
                   (row["evidence_id"], row["version"]))]
        recomputed_key = C.atlas_canonical_key(ids) or ""
        if recomputed_key != (row["canonical_key"] or ""):
            key_bad.append({"evidence_id": row["evidence_id"],
                            "declared": row["canonical_key"], "recomputed": recomputed_key})
    checks.append(C.compare(
        "v3.evidence_id_recompute", group,
        "Every evidence_id recomputes from (source_id, evidence_type, source_record_id)",
        "ev_ = first 32 hex of sha256('source_id|evidence_type|source_record_id').",
        "medradar/atlas/evidence/schema.py:105-113", expected=[], actual=id_bad[:20],
        detail="mismatches=%d of %d" % (len(id_bad), len(ev_rows)),
    ))
    checks.append(C.compare(
        "v3.content_hash_recompute", group,
        "Every content_hash recomputes from its stored payload",
        "content_hash = sha256(canonical json of the normalized payload).",
        "medradar/atlas/evidence/schema.py:97-102,186,223", expected=[], actual=hash_bad[:20],
        detail="mismatches=%d of %d" % (len(hash_bad), len(ev_rows)),
    ))
    checks.append(C.compare(
        "v3.canonical_key_recompute", group,
        "Every canonical_key recomputes from its stored identifiers",
        "canonical_key follows the documented scheme priority with primary-DI preference.",
        "medradar/atlas/evidence/schema.py:116-144", expected=[], actual=key_bad[:20],
        detail="mismatches=%d of %d" % (len(key_bad), len(ev_rows)),
    ))

    # ---------------------------------------------------------- relation census
    census = {}
    for row in con.execute("SELECT relation_type, status, COUNT(*) n FROM entity_relations GROUP BY 1,2"):
        census["%s/%s" % (row["relation_type"], row["status"])] = row["n"]
    expected_census = {
        "SAME_DEVICE_IDENTITY/CONFIRMED": 934,
        "SAME_PRODUCT_FAMILY/CONFIRMED": 192,
        "SAME_MODEL/CONFIRMED": 2,
        "POSSIBLE_MATCH/CANDIDATE": 59,
        "RELATED_TECHNOLOGY/CANDIDATE": 10,
        "UNRELATED/REJECTED": 1087,
        "MANUFACTURED_BY/CONFIRMED": 772,
        "MANUFACTURED_BY/CANDIDATE": 10,
        "REGISTERED_AS/CONFIRMED": 5544,
    }
    diffs = [{"key": k, "declared": v, "recomputed": census.get(k)} for k, v in expected_census.items()
             if census.get(k) != v]
    checks.append(C.compare(
        "v3.relation_census", group,
        "The published relation census matches the database",
        "934 identity + 192 family + 2 model + 59 possible + 10 related + 1087 unrelated; "
        "782 MANUFACTURED_BY and 5544 REGISTERED_AS.",
        "docs/atlas/RESEARCH_VALIDATION.md:69-78",
        expected=[], actual=diffs, evidence={"census": census},
    ))

    findings = con.execute("SELECT severity, COUNT(*) n FROM quality_findings GROUP BY 1").fetchall()
    sev = {r[0]: r[1] for r in findings}
    checks.append(C.Check(
        "v3.quality_findings", group,
        "54 quality findings with zero errors",
        "The final run reports 54 quality findings and no error-severity findings.",
        "docs/atlas/FOUNDATION_AUDIT.md:206-208",
        C.PASS if sum(sev.values()) == 54 and sev.get("error", 0) == 0 else C.FAIL,
        expected={"total": 54, "errors": 0},
        actual={"total": sum(sev.values()), "by_severity": sev},
    ))

    # ---------------------------------------------------- bridge resolution math
    ev_by_run = dict(con.execute(
        "SELECT run_id, COUNT(*) FROM evidence WHERE source_id='openfda_device_udi' GROUP BY 1").fetchall())
    bridge_run = next((k for k in ev_by_run if k.startswith("bridge_")), None)
    from_run = collections.Counter()
    for from_ref, _ in pairs:
        row = con.execute("SELECT run_id FROM evidence WHERE evidence_id=?", (from_ref,)).fetchone()
        from_run[row[0] if row else "MISSING"] += 1
    us_total = con.execute("SELECT COUNT(*) FROM evidence WHERE source_id='openfda_device_udi'").fetchone()[0]
    checks.append(C.Check(
        "v3.bridge_resolution_math", group,
        "942 resolved -> 934 paired is representable in the database",
        "1,200 sampled GTIN rows resolved to 942 openFDA records, of which 934 formed a pair "
        "(8 resolved records were package-level DIs absent from the Canadian table).",
        "docs/atlas/DATA_SOURCE_INTEGRATION.md:31-33; RESEARCH_VALIDATION.md:32",
        C.UNVERIFIABLE,
        expected={"queried": 1200, "resolved": 942, "paired": 934},
        actual={"paired": len(rels), "us_evidence_rows": us_total,
                "us_evidence_by_run": ev_by_run, "pair_from_run": dict(from_run)},
        detail="the 1,200-row deterministic sample and the 942 resolutions cannot be replayed "
               "offline (the sampling rule lives in the ATLAS connector); the database does show "
               "%d US evidence rows = 500 pilot + %s bridge additions, consistent with 942 resolved "
               "of which 2 were already present" % (us_total, ev_by_run.get(bridge_run, 0)),
    ))

    # ------------------------------------------------- "508 unique U.S. records"
    distinct_keys = con.execute(
        "SELECT COUNT(DISTINCT canonical_key) FROM evidence WHERE source_id='openfda_device_udi'").fetchone()[0]
    checks.append(C.Check(
        "v3.us_record_count_claim", group,
        "The stated number of unique U.S. records matches the database",
        "'500 company-page records ... + 8 additional records resolved during the bridge = 508 unique U.S. records'.",
        "docs/atlas/RESEARCH_VALIDATION.md:28",
        C.PASS if distinct_keys == 508 else C.FAIL,
        expected={"unique_us_records": 508},
        actual={"unique_us_records": distinct_keys, "rows": us_total,
                "by_run": ev_by_run},
        detail="the bridge added %s records, not 8; 500 + 8 does not describe the final corpus"
               % ev_by_run.get(bridge_run, 0),
    ))

    # --------------------------------------------------------------- pilot agreement
    if pilot:
        counts = pilot.get("counts", {})
        # bridge_candidate is bridge-scoped in the pilot (0), not a census of POSSIBLE_MATCH rows
        wanted = {
            "bridge_confirmed_identity": len(rels),
            "bridge_pairs": len(set(pairs)),
            "evidence_ids": con.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
            "unique_devices": con.execute("SELECT COUNT(*) FROM devices").fetchone()[0],
            "device_identifiers": con.execute("SELECT COUNT(*) FROM device_identifiers").fetchone()[0],
        }
        declared = {k: counts.get(k) for k in wanted}
        diffs = [{"field": k, "declared": declared[k], "recomputed": wanted[k]}
                 for k in wanted if declared[k] != wanted[k]]
        checks.append(C.compare(
            "v3.pilot_agreement", group,
            "identity_pilot.json counts match the database",
            "The published pilot numbers are the numbers the database holds.",
            "research/atlas/reports/identity_pilot.json counts", expected=[], actual=diffs,
            evidence={"recomputed": wanted, "declared": declared},
        ))
    else:
        checks.append(C.unverifiable("v3.pilot_agreement", group,
                                     "identity_pilot.json counts match the database",
                                     "pilot counts", "identity_pilot.json", "pilot not readable"))

    if baseline:
        metrics = baseline.get("metrics", {})
        ident = metrics.get("identity", {})
        labels = baseline.get("positives", 0) + baseline.get("negatives", 0)
        arithmetic_ok = (
            ident.get("labelled_pairs") == labels
            and ident.get("tp", 0) + ident.get("fn", 0) == baseline.get("positives", 0)
            and ident.get("fp", 0) + ident.get("tn", 0) == baseline.get("negatives", 0)
        )
        checks.append(C.Check(
            "v3.baseline_arithmetic", group,
            "The identity/baseline confusion matrices add up",
            "tp 934 + fn 0 = 934 positives; fp 0 + tn 400 = 400 negatives; 1,334 labelled pairs.",
            "research/atlas/reports/identity_baseline_eval.json; RESEARCH_VALIDATION.md:40-41",
            C.PASS if arithmetic_ok else C.FAIL,
            expected={"labelled_pairs": labels, "positives": baseline.get("positives"),
                      "negatives": baseline.get("negatives")},
            actual={"labelled_pairs": ident.get("labelled_pairs"),
                    "tp": ident.get("tp"), "fn": ident.get("fn"),
                    "fp": ident.get("fp"), "tn": ident.get("tn")},
            detail="arithmetic is consistent; note that tp == positives makes recall 1.0 by "
                   "construction and fp == 0 is definitional for a DI-equality rule",
        ))
        checks.append(C.unverifiable(
            "v3.baseline_labels_enumerated", group,
            "The 400 sampled negatives are recoverable as an artifact",
            "The pinned claim of 400 true negatives requires the negative pair list.",
            "identity_baseline_eval.json", 
            "no artifact enumerates the 400 negative pairs; the metric cannot be re-derived, only re-added",
            expected={"negatives": 400}, actual={"negatives_artifact": None},
        ))

    # ------------------------------------------------------------ MDALL cache
    cache = ctx.get("mdall_cache")
    if ctx.get("heavy") and cache and os.path.exists(cache):
        got = _mdall_cache_counts(cache)
        distinct = got.pop("normalised_values")
        sensitivity = got.pop("sensitivity")
        bridge_gtins = {s[3:] for s in set(shared) if s and s.startswith("di:")}
        checks.append(C.Check(
            "v3.mdall_cache_counts", group,
            "MDALL active identifier table counts recompute",
            "1,673,926 active rows; 5,477 bare 14-digit values; 5,512 normalised to a 14-digit DI "
            "with separators removed; 5,005 unique DI values (0.33 % of the table).",
            "docs/atlas/DATA_SOURCE_INTEGRATION.md:28-30; RESEARCH_VALIDATION.md:31",
            C.PASS if got["rows"] == 1673926 and got["normalised_rows"] == 5512
            and got["unique_normalised"] == 5005 and got["bare_14_digit"] == 5477 else C.FAIL,
            expected={"rows": 1673926, "bare_14_digit": 5477, "normalised_rows": 5512,
                      "unique_normalised": 5005, "share": 0.003293},
            actual={"rows": got["rows"], "bare_14_digit": got["bare_14_digit"],
                    "normalised_rows": got["normalised_rows"],
                    "unique_normalised": got["unique_normalised"],
                    "share": round(got["normalised_rows"] / got["rows"], 6) if got["rows"] else None,
                    "normalisation_rule": "remove '-' and ' ' only",
                    "sensitivity_to_rule": sensitivity},
            detail="the exact separator set is not documented; removing only hyphens and spaces "
                   "reproduces 5,512/5,005 exactly, while a digits-only reading gives 7,919/7,303 "
                   "and an alphanumeric-only reading gives 5,517/5,009",
        ))
        missing = sorted(bridge_gtins - distinct)
        checks.append(C.compare(
            "v3.bridge_gtins_subset_mdall", group,
            "Every bridged GTIN really occurs in the Canadian identifier table",
            "The Canadian side of the bridge must be a value Health Canada publishes.",
            "docs/atlas/DATA_SOURCE_INTEGRATION.md:31-33", expected=[], actual=missing[:20],
            detail="%d bridge GTINs, %d absent from the MDALL cache" % (len(bridge_gtins), len(missing)),
        ))
        # V4 needs the GTIN universe; pass it through facts
        ctx["_mdall_distinct_gtins"] = distinct
    else:
        checks.append(C.unverifiable(
            "v3.mdall_cache_counts", group,
            "MDALL active identifier table counts recompute",
            "1,673,926 rows / 5,512 normalised / 5,005 unique",
            "docs/atlas/DATA_SOURCE_INTEGRATION.md:28-30",
            "220 MB MDALL cache not read (heavy checks disabled or path missing)",
            expected={"rows": 1673926, "normalised_rows": 5512, "unique_normalised": 5005},
            actual=None,
        ))
        checks.append(C.unverifiable(
            "v3.bridge_gtins_subset_mdall", group,
            "Every bridged GTIN really occurs in the Canadian identifier table",
            "bridge GTINs subset of MDALL values",
            "docs/atlas/DATA_SOURCE_INTEGRATION.md:31-33",
            "MDALL cache not read",
        ))

    facts = {
        "relations": len(rels),
        "shared_identifiers": sorted(set(shared)),
        "bridge_gtins": sorted({s[3:] for s in set(shared) if s and s.startswith("di:")}),
        "census": census,
        "us_evidence_by_run": ev_by_run,
    }
    con.close()
    return checks, facts
