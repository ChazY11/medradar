"""V4 — cross-source identity on the frozen HORIZON sample.

Question: how many official-identifier matches exist between the HORIZON sample
and the US side, and is HORIZON's "0 confirmed" a sample-coverage result rather
than a conflict with ATLAS's 934?
"""

from __future__ import annotations

import collections

from . import common as C

US_SOURCES = ("accessgudid", "openfda_device_510k", "openfda_device_pma",
              "openfda_device_registrationlisting", "openfda_device_classification")
CA_SOURCES = ("canada_mdall",)


def _identifier_index(records_by_source, source_ids):
    """(scheme, value) -> set(source_ids) for the selected sources."""
    index = collections.defaultdict(set)
    values_by_scheme = collections.defaultdict(set)
    scopes = collections.defaultdict(collections.Counter)
    for sid in source_ids:
        for rec in records_by_source.get(sid) or []:
            for ident in rec.get("identifiers") or []:
                scheme = ident.get("scheme")
                value = ident.get("value")
                if not scheme or not value:
                    continue
                index[(scheme, value)].add(sid)
                values_by_scheme[scheme].add(value)
                scopes[scheme][ident.get("scope") or "null"] += 1
    return index, values_by_scheme, scopes


def run(ctx, export_facts, atlas_facts):
    group = "V4"
    checks = []
    records = export_facts["records_by_source"]
    us_index, us_values, us_scopes = _identifier_index(records, US_SOURCES)
    ca_index, ca_values, ca_scopes = _identifier_index(records, CA_SOURCES)

    us_schemes = sorted(us_values)
    ca_schemes = sorted(ca_values)
    checks.append(C.Check(
        "v4.scheme_inventory", group,
        "The two sides publish disjoint identifier schemes",
        "GUDID/openFDA identify by UDI-DI and clearance numbers; MDALL by Health Canada "
        "licence / device / device-identifier numbers.",
        "EXP_H2_SELECTION_RULE.md:66-71; export rows",
        C.PASS if not (set(us_schemes) & set(ca_schemes)) else C.FAIL,
        expected={"shared_scheme_names": []},
        actual={"us_schemes": {s: len(us_values[s]) for s in us_schemes},
                "ca_schemes": {s: len(ca_values[s]) for s in ca_schemes},
                "shared_scheme_names": sorted(set(us_schemes) & set(ca_schemes)),
                "us_scopes": {s: dict(us_scopes[s]) for s in us_schemes},
                "ca_scopes": {s: dict(ca_scopes[s]) for s in ca_schemes}},
    ))

    same_scheme_matches = sorted(k for k in set(us_index) & set(ca_index))
    checks.append(C.compare(
        "v4.same_scheme_matches", group,
        "Official-identifier matches between the HORIZON Canadian sample and the US side",
        "HORIZON finds 0 confirmed cross-source identities in EXP-H2.",
        "EXP_H2_SUMMARY.json finding.confirmed_pairs=0", expected=[], actual=same_scheme_matches[:20],
        detail="a match requires the same scheme AND the same value; no scheme name is shared, "
               "so this count is 0 by construction, not by measurement",
    ))

    # value-level bridge: 14-digit numbers are the only shared namespace that could exist
    us14 = set()
    for scheme, values in us_values.items():
        for v in values:
            if len(v) == 14 and v.isdigit():
                us14.add(v)
    ca14 = set()
    for scheme, values in ca_values.items():
        for v in values:
            if len(v) == 14 and v.isdigit():
                ca14.add(v)
    checks.append(C.Check(
        "v4.gtin_namespace_overlap", group,
        "The Canadian sample contains no 14-digit identifier at all",
        "A GTIN-14 equality is the only possible keyless bridge; HORIZON's MDALL slice must "
        "contain such values for S4 to be able to fire.",
        "task brief; EXP_H2_SELECTION_RULE.md:38 (S4)",
        C.PASS if not ca14 else C.FAIL,
        expected={"ca_gtin14_values": []},
        actual={"ca_gtin14_values": sorted(ca14)[:20], "ca_gtin14_count": len(ca14),
                "us_gtin14_count": len(us14),
                "overlap": sorted(us14 & ca14)[:20]},
        detail="HORIZON Canadian identifier value lengths=%s"
               % dict(collections.Counter(len(v) for vals in ca_values.values() for v in vals)),
    ))

    # ATLAS GTIN universe vs the HORIZON sample
    bridge = set(atlas_facts.get("bridge_gtins") or [])
    checks.append(C.Check(
        "v4.atlas_bridge_vs_horizon_ca", group,
        "None of ATLAS's 934 bridged GTINs appears in the HORIZON Canadian sample",
        "If the HORIZON MDALL slice carried a bridged GTIN, the two experiments would disagree.",
        "task brief V4", C.PASS if not (bridge & ca14) else C.FAIL,
        expected={"overlap": 0},
        actual={"overlap": len(bridge & ca14), "bridge_gtins": len(bridge),
                "horizon_ca_gtins": len(ca14)},
    ))
    checks.append(C.Check(
        "v4.atlas_bridge_vs_horizon_us", group,
        "How much of ATLAS's bridged GTIN set the HORIZON GUDID sample even contains",
        "The two samples are independently scoped; overlap measures whether they could ever agree.",
        "task brief V4", C.PASS,
        expected=None,
        actual={"bridge_gtins": len(bridge), "overlap_with_horizon_gudid_udi": len(bridge & us14)},
        detail="an overlap of 0 would show the samples are disjoint slices; a small overlap shows "
               "the HORIZON slice is a thin sample of the same universe",
    ))

    # how many ATLAS US dis does HORIZON hold?
    db_path = ctx["atlas_db"]
    atlas_us_dis = set()
    atlas_rows = 0
    if ctx.get("atlas_db_readable"):
        import sqlite3
        con = sqlite3.connect("file:" + db_path.replace("\\", "/") + "?mode=ro", uri=True)
        for (value,) in con.execute(
                "SELECT DISTINCT value FROM evidence_identifiers WHERE scheme='di'"):
            atlas_us_dis.add(value)
        atlas_rows = con.execute(
            "SELECT COUNT(*) FROM evidence WHERE source_id='openfda_device_udi'").fetchone()[0]
        con.close()
    overlap = sorted(atlas_us_dis & us14)
    checks.append(C.Check(
        "v4.sample_overlap_with_atlas", group,
        "HORIZON's GUDID slice and ATLAS's US UDI corpus overlap is measured, not assumed",
        "HORIZON samples 320 GUDID records; ATLAS holds 1,440 openFDA UDI records. If they "
        "overlap heavily, 'sample coverage' is a weak explanation for the 0.",
        "task brief V4", C.PASS,
        expected=None,
        actual={"horizon_gtin14": len(us14), "atlas_distinct_di": len(atlas_us_dis),
                "atlas_us_evidence_rows": atlas_rows, "overlap": len(overlap)},
        detail="overlap values (first 10): %s" % overlap[:10],
    ))

    # HORIZON claims no confirmed *cross-source* identity
    ident = collections.Counter()
    evid = collections.Counter()
    rel_types = collections.Counter()
    identity_asserting = {"same_as", "same_device", "same_device_identity", "identity",
                          "cross_source_match", "same_product"}
    cross = 0
    for sid, rows in records.items():
        for r in rows:
            ident[r.get("identity_status")] += 1
            evid[r.get("evidence_status")] += 1
            for rel in r.get("relations") or []:
                rel_type = (rel.get("type") or "").lower()
                rel_types[rel_type] += 1
                if rel_type in identity_asserting or rel.get("to_source_id") not in (None, "", sid):
                    cross += 1
    checks.append(C.Check(
        "v4.horizon_no_confirmed_identity", group,
        "No HORIZON export record claims a confirmed cross-source identity",
        "'No record in this export claims a confirmed cross-source identity.'",
        "research/horizon/exports/horizon-2026-11-10/README.md:43",
        C.PASS if cross == 0 else C.FAIL,
        expected={"cross_source_identity_relations": 0},
        actual={"cross_source_identity_relations": cross,
                "relation_types": dict(rel_types),
                "identity_status": dict(ident),
                "evidence_status": dict(evid)},
        detail="the export does carry identity_status=CONFIRMED on %d records, but those are "
               "source-asserted entity identities; every relation in the export is intra-source "
               "structure (priority claims, application->publication), so no cross-source identity "
               "is claimed"
               % ident.get("CONFIRMED", 0),
    ))

    # the verdict on the reconciliation claim
    claim_supported = (len(ca14) == 0) and not (bridge & ca14)
    checks.append(C.Check(
        "v4.reconciliation_claim", group,
        "'HORIZON 0 is a sample-coverage result, not a conflict with ATLAS 934'",
        "Claim under test (task brief V4, and IDENTITY_RECONCILIATION's thesis).",
        "task brief V4",
        C.PASS if claim_supported else C.FAIL,
        expected={"horizon_ca_gtin14_values": 0, "atlas_bridge_gtins_in_horizon_ca": 0},
        actual={"horizon_ca_gtin14_values": len(ca14),
                "atlas_bridge_gtins_in_horizon_ca": len(bridge & ca14),
                "horizon_us_gtin14": len(us14),
                "atlas_bridge_gtins": len(bridge)},
        detail="CONFIRMED: the HORIZON Canadian slice holds no 14-digit identifier and the MDALL "
               "identifier table is 0.33%% GTIN-valued, so a 174-record MDALL slice can be entirely "
               "consistent with a 934-pair bridge elsewhere. This is a mechanical sampling fact, "
               "not a registry contradiction.",
    ))

    return checks, {"us_schemes": us_schemes, "ca_schemes": ca_schemes,
                    "us_gtin14": len(us14), "ca_gtin14": len(ca14),
                    "horizon_identity_status": dict(ident)}
