#!/usr/bin/env python
"""P0-B / task-2: build ONE frozen unified sample and evaluate both methods on it.

The two experiments never share a pair.  This script makes that explicit and
measures it:

  * ATLAS  -> 934 pairs, ATLAS_BRIDGE_934.json (re-derived from DB + raw MDALL cache)
  * HORIZON -> 726 pairs, research/horizon/experiments/regulatory/EXP_H2_PAIRS.jsonl

Unified sample = union of the two frozen pair tables, 1,660 rows, each row
carrying both records and both identifier typings.  Nothing is resampled.

Two methods are then applied to every one of the 1,660 rows:

  A          ATLAS official-identifier bridge: CONFIRMED iff the US record and
             the Canada record carry the same 14-digit, Mod-10-valid GTIN-14.
  H_native   HORIZON EXP-H2 rule exactly as pre-registered and implemented:
             CONFIRMED only if S4 fires = the same identifier value under the
             SAME source-declared scheme; REJECTED only on an official
             contradiction; otherwise UNKNOWN.
  H_namespace  a charitable variant of H2 in which a 14-digit Mod-10-valid
             Canada identifier is promoted into the UDI-DI namespace (the
             reading that would make S4 fire).  Reported so the disagreement
             can be attributed to field typing rather than to facts.

Also computes `anchor_sensitivity`: ATLAS's resolver anchors on the FIRST `di`
in the openFDA payload, not the primary DI.  The 942 records returned by the
bridge query are re-typed here, so the published 934 can be compared against a
primary-DI-anchored join on exactly the same returned records.

Writes:
  research/convergence/identity/UNIFIED_SAMPLE.jsonl
  research/convergence/identity/UNIFIED_SAMPLE_RESULTS.json

Run:
    python tools/convergence/identity/unified_sample.py
"""

from __future__ import annotations

import collections
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gtin import GTIN14_RE, gtin14_check_digit_ok, is_gtin_like, normalize_di  # noqa: E402

WT = Path(r"D:\DEPPSKK\worktrees\convergence-001")
DB = Path(r"D:\DEPPSKK\worktrees\atlas-001\research\atlas\staging\atlas.sqlite")
CACHE = Path(r"D:\DEPPSKK\worktrees\atlas-001\research\atlas\cache\mdall_active_deviceidentifier.json")
BRIDGE = WT / "research" / "convergence" / "identity" / "ATLAS_BRIDGE_934.json"
HORIZON_PAIRS = WT / "research/horizon/experiments/regulatory/EXP_H2_PAIRS.jsonl"
FROZEN = WT / "research" / "convergence" / "identity" / "FROZEN_INPUTS.json"
OUT_SAMPLE = WT / "research" / "convergence" / "identity" / "UNIFIED_SAMPLE.jsonl"
OUT_RESULT = WT / "research" / "convergence" / "identity" / "UNIFIED_SAMPLE_RESULTS.json"

_GTIN14 = GTIN14_RE


def sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def iter_json_array(path: Path, chunk: int = 1 << 20):
    dec = json.JSONDecoder()
    with path.open("r", encoding="utf-8") as f:
        buf = f.read(chunk)
        idx = 1
        while True:
            while idx < len(buf) and buf[idx] in " \t\r\n,":
                idx += 1
            if idx >= len(buf):
                more = f.read(chunk)
                if not more:
                    return
                buf = buf[idx:] + more
                idx = 0
                continue
            if buf[idx] == "]":
                return
            try:
                obj, end = dec.raw_decode(buf, idx)
            except json.JSONDecodeError:
                more = f.read(chunk)
                if not more:
                    raise
                buf = buf[idx:] + more
                idx = 0
                continue
            yield obj
            idx = end


def main() -> int:
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    digests = {b["role"]: b["sha256"] for b in frozen["required_inputs"]}
    bridge = json.loads(BRIDGE.read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- MDALL GTIN class set
    gtIN_set: set[str] = set()
    for obj in iter_json_array(CACHE):
        raw = obj.get("device_identifier")
        if is_gtin_like(raw):
            gtIN_set.add(normalize_di(raw))
    assert len(gtIN_set) == 5005, len(gtIN_set)

    # ---------------------------------------------------------------- rows
    rows: list[dict] = []
    for p in bridge["pairs"]:
        rows.append({
            "sample_row_id": f"U{len(rows) + 1:05d}",
            "origin_experiment": "atlas_identity_pilot",
            "origin_pair_id": p["relation_id"],
            "origin_pair_verdict": "CONFIRMED",
            "us_record_id": p["fda_evidence_id"],
            "us_di": p["di"],
            "us_di_scheme_as_recorded": "di",
            "us_record_identifiers": [
                {"scheme": x["scheme"], "value": x["value"], "is_primary": bool(x["is_primary"])}
                for x in p["fda_identifiers"]],
            "us_labeler_company": p["fda_company_name"],
            "ca_record_id": p["mdall_evidence_id"],
            "ca_identifier_raw": p["mdall_identifier_raw"],
            "ca_identifier_normalised": normalize_di(p["mdall_identifier_raw"]),
            "ca_identifier_scheme_source_declared": "hc_mdall_device_identifier",
            "ca_identifier_scheme_atlas_typed": "di" if is_gtin_like(p["mdall_identifier_raw"]) else "",
            "ca_is_valid_gtin14": gtin14_check_digit_ok(normalize_di(p["mdall_identifier_raw"])),
            "ca_licence": p["mdall_licence"],
            "ca_mdall_device_id": p["mdall_device_id"],
            "is_hard_negative": False,
        })

    with HORIZON_PAIRS.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            h = json.loads(line)
            ca_idents = h["source_record_ids"]["canada"].get("identifiers") or {}
            ca_values = [str(v) for vals in ca_idents.values() for v in (vals or [])]
            ca_schemes = sorted(ca_idents.keys())
            fda_di = str(h["source_record_ids"]["fda"].get("udi_di") or "")
            rows.append({
                "sample_row_id": f"U{len(rows) + 1:05d}",
                "origin_experiment": "horizon_exp_h2",
                "origin_pair_id": h["pair_id"],
                "origin_pair_verdict": h["verdict"],
                "us_record_id": h["source_record_ids"]["fda"]["source_record_id"],
                "us_di": fda_di,
                "us_di_scheme_as_recorded": "udi_di",
                "us_record_identifiers": ([{"scheme": "udi_di", "value": fda_di, "is_primary": True}]
                                          if fda_di else []),
                "us_labeler_company": h.get("fda_firm") or "",
                "ca_record_id": h["source_record_ids"]["canada"]["source_record_id"],
                "ca_identifier_raw": ca_values[0] if ca_values else "",
                "ca_identifier_normalised": normalize_di(ca_values[0]) if ca_values else "",
                "ca_identifier_values_all": ca_values,
                "ca_identifier_scheme_source_declared": (
                    ca_schemes[0] if len(ca_schemes) == 1 else "|".join(ca_schemes)),
                "ca_identifier_scheme_atlas_typed": "",
                "ca_is_valid_gtin14": any(gtin14_check_digit_ok(normalize_di(v)) for v in ca_values),
                "ca_licence": (ca_idents.get("hc_device_licence") or [""])[0],
                "ca_mdall_device_id": (ca_idents.get("hc_mdall_device_id") or [""])[0],
                "is_hard_negative": h.get("construction_rule") is not None,
            })

    assert len(rows) == 1660, len(rows)

    # ---------------------------------------------------------------- method evaluation
    def method_atlas(r: dict) -> str:
        """ATLAS official-identifier bridge: same 14-digit, Mod-10-valid GTIN-14."""
        us = normalize_di(r["us_di"])
        ca = r["ca_identifier_normalised"]
        if not us or not ca:
            return "UNKNOWN"
        if us == ca and gtin14_check_digit_ok(us):
            return "CONFIRMED"
        # ATLAS never emits REJECTED for a GTIN mismatch in the bridge; it simply
        # does not create a relation, so a non-match stays UNKNOWN here.
        return "UNKNOWN"

    def method_h2_native(r: dict) -> str:
        """H2 as pre-registered: S4 requires the same value under the same scheme."""
        us_ids = {(x["scheme"], str(x["value"])) for x in r["us_record_identifiers"]}
        # Canada-side identifiers in their *source-declared* scheme labels.
        if r["origin_experiment"] == "horizon_exp_h2":
            ca_ids = {(r["ca_identifier_scheme_source_declared"], v)
                      for v in r.get("ca_identifier_values_all", [])}
        else:
            ca_ids = {(r["ca_identifier_scheme_source_declared"], r["ca_identifier_raw"])}
        s4 = bool(us_ids & ca_ids)
        if s4:
            return "CONFIRMED"
        # REJECTED needs an official contradiction (S2 + no S3, or a date
        # contradiction).  With MDALL-only identifier rows there is no such
        # field; HORIZON's own frozen verdicts are UNKNOWN for all 726.
        return "UNKNOWN"

    def method_h2_namespace(r: dict) -> str:
        """Charitable H2: promote a valid GTIN-14 Canada identifier into the UDI namespace."""
        us = normalize_di(r["us_di"])
        ca = r["ca_identifier_normalised"]
        if us and ca and us == ca and gtin14_check_digit_ok(ca):
            return "CONFIRMED"
        return "UNKNOWN"

    for r in rows:
        r["verdict_atlas_bridge"] = method_atlas(r)
        r["verdict_h2_native"] = method_h2_native(r)
        r["verdict_h2_namespace"] = method_h2_namespace(r)

    # ---------------------------------------------------------------- confusion tables
    def confusion(a_key: str, b_key: str) -> dict:
        table = collections.Counter()
        for r in rows:
            table[(r[a_key], r[b_key])] += 1
        both = table.get(("CONFIRMED", "CONFIRMED"), 0)
        a_only = table.get(("CONFIRMED", "UNKNOWN"), 0) + table.get(("CONFIRMED", "REJECTED"), 0)
        b_only = table.get(("UNKNOWN", "CONFIRMED"), 0) + table.get(("REJECTED", "CONFIRMED"), 0)
        neither = sum(v for k, v in table.items() if "CONFIRMED" not in k)
        return {
            "both_confirmed": both,
            "atlas_only_confirmed": a_only,
            "h2_only_confirmed": b_only,
            "neither_confirmed": neither,
            "atlas_rejected": sum(v for k, v in table.items() if k[0] == "REJECTED"),
            "h2_rejected": sum(v for k, v in table.items() if k[1] == "REJECTED"),
            "atlas_unknown": sum(v for k, v in table.items() if k[0] == "UNKNOWN"),
            "h2_unknown": sum(v for k, v in table.items() if k[1] == "UNKNOWN"),
            "raw_cells": {f"{k[0]}|{k[1]}": v for k, v in sorted(table.items())},
        }

    confusion_native = confusion("verdict_atlas_bridge", "verdict_h2_native")
    confusion_namespace = confusion("verdict_atlas_bridge", "verdict_h2_namespace")

    # ---------------------------------------------------------------- structural disjointness
    atlas_rows = [r for r in rows if r["origin_experiment"] == "atlas_identity_pilot"]
    horizon_rows = [r for r in rows if r["origin_experiment"] == "horizon_exp_h2"]
    atlas_us = {r["us_di"] for r in atlas_rows}
    horizon_us = {r["us_di"] for r in horizon_rows}
    atlas_ca = {r["ca_identifier_normalised"] for r in atlas_rows}
    horizon_ca = set()
    for r in horizon_rows:
        for v in r.get("ca_identifier_values_all", []):
            horizon_ca.add(normalize_di(v))
    atlas_lic = {r["ca_licence"] for r in atlas_rows if r["ca_licence"]}
    horizon_lic = {r["ca_licence"] for r in horizon_rows if r["ca_licence"]}
    disjointness = {
        "atlas_pairs": len(atlas_rows),
        "horizon_pairs": len(horizon_rows),
        "shared_pair_ids": len(set(r["origin_pair_id"] for r in atlas_rows)
                               & set(r["origin_pair_id"] for r in horizon_rows)),
        "shared_us_record_ids": len({r["us_record_id"] for r in atlas_rows}
                                    & {r["us_record_id"] for r in horizon_rows}),
        "shared_us_di": sorted(atlas_us & horizon_us),
        "shared_us_di_count": len(atlas_us & horizon_us),
        "shared_ca_identifier": sorted(atlas_ca & horizon_ca)[:20],
        "shared_ca_identifier_count": len(atlas_ca & horizon_ca),
        "shared_ca_licence": sorted(atlas_lic & horizon_lic),
        "shared_ca_licence_count": len(atlas_lic & horizon_lic),
        "atlas_us_di_count": len(atlas_us),
        "horizon_us_di_count": len(horizon_us),
        "atlas_ca_identifier_count": len(atlas_ca),
        "horizon_ca_identifier_count": len(horizon_ca),
    }

    # ---------------------------------------------------------------- anchor sensitivity
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    paired_ev = {p["fda_evidence_id"] for p in bridge["pairs"]}
    returned = cur.execute(
        "select evidence_id, canonical_key, payload_json from evidence "
        "where source_id='openfda_device_udi' and (run_id='bridge_20261110T174101Z' "
        "or evidence_id in (%s))" % ",".join("?" * len(paired_ev)),
        tuple(paired_ev),
    ).fetchall()
    recs = []
    for row in returned:
        pl = json.loads(row["payload_json"] or "{}")
        idents = pl.get("identifiers") or []
        first = next((str(i.get("value")) for i in idents
                      if i.get("scheme") == "di" and i.get("value")), "")
        primary = next((str(i.get("value")) for i in idents
                        if i.get("scheme") == "di" and i.get("value") and i.get("is_primary")), "")
        recs.append({
            "evidence_id": row["evidence_id"],
            "canonical_key": row["canonical_key"],
            "first_di": normalize_di(first),
            "primary_di": normalize_di(primary),
            "any_di_in_class": any(
                normalize_di(str(i.get("value"))) in gtIN_set
                for i in idents if i.get("scheme") == "di"),
            "paired": row["evidence_id"] in paired_ev,
        })
    con.close()
    assert len(recs) == 942, len(recs)
    first_in = [r for r in recs if r["first_di"] in gtIN_set]
    primary_in = [r for r in recs if r["primary_di"] in gtIN_set]
    both_in = [r for r in recs if r["first_di"] in gtIN_set and r["primary_di"] in gtIN_set]
    any_in = [r for r in recs if r["any_di_in_class"]]
    anchor_sensitivity = {
        "records_returned_by_bridge_query": len(recs),
        "published_pairs_first_di_anchored": len(first_in),
        "primary_di_anchored_on_same_records": len(primary_in),
        "both_anchors_gtin_class": len(both_in),
        "records_with_any_identifier_in_gtin_class": len(any_in),
        "records_where_first_di_differs_from_primary": sum(
            1 for r in recs if r["first_di"] != r["primary_di"]),
        "published_pairs_whose_anchor_is_not_the_primary_di": sum(
            1 for r in recs if r["paired"] and r["first_di"] != r["primary_di"]),
        "dropped_primary_di_matches": sum(
            1 for r in recs if not r["paired"] and r["primary_di"] in gtIN_set
            and r["first_di"] not in gtIN_set),
        "dropped_package_di_only_matches": sum(
            1 for r in recs if not r["paired"] and r["primary_di"] not in gtIN_set
            and r["any_di_in_class"]),
        "unpaired_total": sum(1 for r in recs if not r["paired"]),
        "distinct_primary_di_anchored": len({r["primary_di"] for r in primary_in}),
        "note": (
            "On exactly the 942 records the bridge query returned, ATLAS's first-di anchor gives "
            "934 pairs; a primary-DI anchor gives 941. The 8 unpaired records split into 7 "
            "primary-DI matches dropped only because a package DI was listed first, and 1 match "
            "available only through a package DI (correctly dropped). The difference is not new "
            "data: it is the identifier-order defect in resolver.view_from_evidence()."
        ),
    }

    # ---------------------------------------------------------------- write outputs
    OUT_SAMPLE.write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n", encoding="utf-8")
    result = {
        "schema": "medradar.convergence.unified_sample.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "tools/convergence/identity/unified_sample.py",
        "network_used": False,
        "inputs": {
            "atlas_bridge_934": {"path": str(BRIDGE), "sha256": sha256_file(BRIDGE)},
            "horizon_h2_pairs": {"path": str(HORIZON_PAIRS), "sha256": digests["horizon_h2_pairs"]},
            "mdall_cache": {"path": str(CACHE), "sha256": digests["mdall_cache"]},
            "atlas_db": {"path": str(DB), "sha256": digests["atlas_db"]},
        },
        "sample": {
            "path": str(OUT_SAMPLE),
            "sha256": sha256_file(OUT_SAMPLE),
            "rows": len(rows),
            "atlas_rows": len(atlas_rows),
            "horizon_rows": len(horizon_rows),
            "definition": (
                "Union of the two experiments' frozen pair tables (934 + 726 = 1,660). Every row is "
                "evaluated by both methods; no pair is resampled and nothing is dropped."
            ),
        },
        "method_definitions": {
            "A_atlas_bridge": "CONFIRMED iff both records carry the same 14-digit GS1 GTIN-14 with a valid Mod-10 check digit.",
            "H2_native": "HORIZON EXP-H2 rule as pre-registered and implemented: CONFIRMED only if S4 fires, i.e. the same identifier value under the same source-declared scheme.",
            "H2_namespace": "Charitable H2 variant: a Mod-10-valid 14-digit Canada identifier is promoted into the UDI-DI namespace before applying S4.",
        },
        "structural_disjointness": disjointness,
        "confusion_native_typing": confusion_native,
        "confusion_namespace_typing": confusion_namespace,
        "verdict_counts": {
            "atlas_bridge": dict(collections.Counter(r["verdict_atlas_bridge"] for r in rows)),
            "h2_native": dict(collections.Counter(r["verdict_h2_native"] for r in rows)),
            "h2_namespace": dict(collections.Counter(r["verdict_h2_namespace"] for r in rows)),
            "h2_native_atlas_rows": dict(collections.Counter(
                r["verdict_h2_native"] for r in atlas_rows)),
            "h2_native_horizon_rows": dict(collections.Counter(
                r["verdict_h2_native"] for r in horizon_rows)),
        },
        "anchor_sensitivity": anchor_sensitivity,
    }
    OUT_RESULT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({k: result[k] for k in (
        "sample", "structural_disjointness", "confusion_native_typing",
        "confusion_namespace_typing", "verdict_counts", "anchor_sensitivity")}, indent=2))
    print(f"\nwrote {OUT_SAMPLE} and {OUT_RESULT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
