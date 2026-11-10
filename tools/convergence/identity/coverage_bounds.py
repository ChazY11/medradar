#!/usr/bin/env python
"""P0-B / task-2: coverage ceilings, generalisation bound and attribution summary.

Reads the frozen intermediate artefacts only (no new scan of the raw table):

  research/convergence/identity/MDALL_CACHE_ANALYSIS.json
  research/convergence/identity/ATLAS_BRIDGE_934.json
  research/convergence/identity/UNIFIED_SAMPLE_RESULTS.json
  research/atlas/reports/identity_pilot.json

Writes research/convergence/identity/COVERAGE_AND_ATTRIBUTION.json

The point of this file is to keep the conclusion honest: the official-identifier
bridge is real, but it is bounded to a very thin slice of MDALL, it is dominated
by a handful of manufacturers, and its Canada-side corporate identity is mostly
unknown in the frozen data.

Run:
    python tools/convergence/identity/coverage_bounds.py
"""

from __future__ import annotations

import collections
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

WT = Path(r"D:\DEPPSKK\worktrees\convergence-001")
ID = WT / "research" / "convergence" / "identity"
CACHE_ANALYSIS = ID / "MDALL_CACHE_ANALYSIS.json"
BRIDGE = ID / "ATLAS_BRIDGE_934.json"
UNIFIED = ID / "UNIFIED_SAMPLE_RESULTS.json"
PILOT = WT / "research/atlas/reports/identity_pilot.json"
OUT = ID / "COVERAGE_AND_ATTRIBUTION.json"


def sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def frac(num: int, den: int) -> float:
    return round(num / den, 8) if den else 0.0


def main() -> int:
    cache = json.loads(CACHE_ANALYSIS.read_text(encoding="utf-8"))
    bridge = json.loads(BRIDGE.read_text(encoding="utf-8"))
    unified = json.loads(UNIFIED.read_text(encoding="utf-8"))
    pilot = json.loads(PILOT.read_text(encoding="utf-8"))

    rows = cache["totals"]["rows"]
    distinct_identifiers = cache["totals"]["distinct_device_identifier_values_raw"]
    licences = cache["totals"]["distinct_licences"]
    device_ids = cache["totals"]["distinct_device_ids"]
    cls = cache["identifier_classes"]
    reach = cache["reach_denominators"]

    gtin_rows = cls["atlas_gtin_class_rows"]
    gtin_distinct = cls["atlas_gtin_class_distinct_values"]
    gtin_valid_rows = cls["gtin14_check_digit_valid_rows"]
    gtin_valid_distinct = cls["gtin14_check_digit_valid_distinct_values"]
    gtin_licences = reach["distinct_licences_with_at_least_one_gtin_class_row"]
    gtin_device_ids = reach["distinct_device_ids_with_at_least_one_gtin_class_row"]

    queried = pilot["counts"]["bridge_queried"]
    resolved = pilot["counts"]["bridge_fda_records_resolved"]
    confirmed = pilot["counts"]["bridge_confirmed_identity"]
    pairs = bridge["pairs"]
    labelers = collections.Counter((p["fda_company_name"] or "").strip() for p in pairs)
    lic_counter = collections.Counter(p["mdall_licence"] for p in pairs)

    ceiling = {
        "of_mdall_identifier_rows": frac(gtin_rows, rows),
        "of_mdall_distinct_identifier_values": frac(gtin_distinct, distinct_identifiers),
        "of_mdall_licences": frac(gtin_licences, licences),
        "of_mdall_device_lines": frac(gtin_device_ids, device_ids),
        "note": (
            "A UDI bridge can only ever touch rows whose device_identifier is a GTIN-14. "
            "That is the hard ceiling, before any matching happens."
        ),
        "rows_number": gtin_rows,
        "licences_number": gtin_licences,
        "device_lines_number": gtin_device_ids,
        "total_rows": rows,
        "total_licences": licences,
        "total_device_lines": device_ids,
    }

    confirmed_vs = {
        "confirmed_pairs": confirmed,
        "of_all_mdall_rows": frac(confirmed, rows),
        "of_all_mdall_distinct_identifier_values": frac(confirmed, distinct_identifiers),
        "of_mdall_gtin_class_rows": frac(confirmed, gtin_rows),
        "of_mdall_gtin_class_distinct_values": frac(confirmed, gtin_distinct),
        "of_mdall_licences": frac(len(lic_counter), licences),
        "of_mdall_gtin_class_licences": frac(len(lic_counter), gtin_licences),
        "of_query_sample": frac(confirmed, queried),
        "of_all_gtin_class_distinct_values": frac(confirmed, gtin_distinct),
        "note": (
            "934 is a confirmed count on a systematic 1200-of-5005 subsample. It is a lower bound "
            "on what this method could confirm (3805 GTIN-class values were never queried) and an "
            "upper bound on nothing: it is not a population estimate and must not be scaled up."
        ),
    }

    sampling = {
        "gtin_class_distinct_values": gtin_distinct,
        "queried_gtin_values": queried,
        "queried_share_of_gtin_class": frac(queried, gtin_distinct),
        "unqueried_gtin_values": gtin_distinct - queried,
        "resolved_records": resolved,
        "confirmed_pairs_published": confirmed,
        "primary_di_anchored_pairs_on_same_records": unified["anchor_sensitivity"][
            "primary_di_anchored_on_same_records"],
        "unpaired_returned_records": unified["anchor_sensitivity"]["unpaired_total"],
        "subsample_rule": (
            "sorted(MDALL GTIN-class raw keys); take index int(i * 5005/1200) for i in range(1200). "
            "This is a systematic sample, not a random sample; reproduced exactly in this work."
        ),
    }

    concentration = {
        "distinct_us_labelers": len(labelers),
        "largest_labeler": labelers.most_common(1)[0][0],
        "largest_labeler_pairs": labelers.most_common(1)[0][1],
        "largest_labeler_share": frac(labelers.most_common(1)[0][1], confirmed),
        "top4_labelers_pairs": sum(n for _, n in labelers.most_common(4)),
        "top4_labelers_share": frac(sum(n for _, n in labelers.most_common(4)), confirmed),
        "distinct_ca_licences": len(lic_counter),
        "largest_licence": lic_counter.most_common(1)[0][0],
        "largest_licence_pairs": lic_counter.most_common(1)[0][1],
        "largest_licence_share": frac(lic_counter.most_common(1)[0][1], confirmed),
        "distinct_mdall_device_ids": len({p["mdall_device_id"] for p in pairs}),
        "top_labelers": [{"company": c, "pairs": n} for c, n in labelers.most_common(8)],
        "top_licences": [{"licence": c, "pairs": n} for c, n in lic_counter.most_common(8)],
        "five_firm_register_pairs_strict_alias": bridge["firm_attribution"][
            "us_side_inside_five_firm_register_pairs"],
        "five_firm_register_pairs_atlas_stored": sum(
            1 for p in pairs if p["fda_firm_key_stored"]),
        "ca_side_pairs_any_company_attribution": bridge["firm_attribution"][
            "ca_side_pairs_with_any_company_link"],
        "ca_side_pairs_fully_unattributable": bridge["firm_attribution"][
            "ca_side_pairs_unattributable"],
    }

    # What would falsify the reconciliation, and its current status.
    falsifiers = [
        {
            "claim": "MDALL's device_identifier field contains a GTIN-14 minority as well as model/catalogue tokens.",
            "falsifier": "a full scan of the frozen table finds no 14-digit values, or none with valid Mod-10 check digits.",
            "status": "survives: 5,512 / 1,673,926 rows are 14-digit; 5,434 rows (4,927 distinct) have valid check digits; 78 distinct invalid-check 14-digit values exist too.",
        },
        {
            "claim": "The 934 ATLAS pairs are exact GTIN-14 equalities, not string coincidence.",
            "falsifier": "any of the 934 shared identifiers is not 14 digits or fails the Mod-10 check.",
            "status": "survives: 934/934 are 14-digit and 934/934 pass the Mod-10 check; 0 blank, 0 duplicate.",
        },
        {
            "claim": "The Canada side of each pair is re-derivable from the raw frozen MDALL table.",
            "falsifier": "a shared identifier is absent from the raw table, or its licence/device_id does not match.",
            "status": "survives: 934/934 present in the raw cache; 934/934 licence match; 934/934 MDALL device_id match.",
        },
        {
            "claim": "HORIZON's 0 is a coverage result, not a refutation.",
            "falsifier": "HORIZON's Canada slice contains a GTIN-14 identifier, or its US slice shares a DI with ATLAS's 934.",
            "status": "survives: 0/49 HORIZON identifier values are 14-digit; 0/934 ATLAS DIs appear in HORIZON's 320 DI slice; 0 shared CA licences.",
        },
        {
            "claim": "The two methods are the same rule under different field typing.",
            "falsifier": "on the unified 1,660-pair sample, the ATLAS bridge confirms pairs H2's namespace-typing variant does not, or vice versa.",
            "status": "survives: namespace-typing confusion is 934/934 both-confirmed and 726/726 neither; native-typing gives 934 ATLAS-only.",
        },
        {
            "claim": "The bridge generalises to a cross-border identity solution.",
            "falsifier": "the bridge reaches a large share of MDALL rows, or is spread across manufacturers and licences.",
            "status": "REFUTED: ceiling 0.33% of rows / 0.63% of licences; 81.4% of confirmations come from one licence and one US labeler; 92.8% from the top four labelers.",
        },
        {
            "claim": "The confirmed pairs are corporately coherent on both sides.",
            "falsifier": "Canada-side corporate identity cannot be established, or contradicts the US side.",
            "status": "not established: 925/934 (99.0%) pairs have no Canada-side company in the frozen data; the 9 that do are GE-only name-alias links.",
        },
    ]

    out = {
        "schema": "medradar.convergence.coverage_and_attribution.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "tools/convergence/identity/coverage_bounds.py",
        "network_used": False,
        "inputs": {
            "mdall_cache_analysis": {"path": str(CACHE_ANALYSIS), "sha256": sha256_file(CACHE_ANALYSIS)},
            "atlas_bridge_934": {"path": str(BRIDGE), "sha256": sha256_file(BRIDGE)},
            "unified_sample_results": {"path": str(UNIFIED), "sha256": sha256_file(UNIFIED)},
            "atlas_identity_pilot": {"path": str(PILOT), "sha256": sha256_file(PILOT)},
            "mdall_cache_sha256": cache["input"]["sha256"],
        },
        "denominators": {
            "mdall_rows": rows,
            "mdall_distinct_identifier_values": distinct_identifiers,
            "mdall_licences": licences,
            "mdall_device_lines": device_ids,
            "mdall_gtin_class_rows": gtin_rows,
            "mdall_gtin_class_distinct": gtin_distinct,
            "mdall_gtin_class_check_digit_valid_rows": gtin_valid_rows,
            "mdall_gtin_class_check_digit_valid_distinct": gtin_valid_distinct,
        },
        "joinable_ceiling": ceiling,
        "confirmed_against_denominators": confirmed_vs,
        "sampling": sampling,
        "concentration": concentration,
        "generalisation_statement": (
            f"At most {gtin_rows}/{rows} = {frac(gtin_rows, rows) * 100:.3f}% of MDALL active "
            f"identifier rows, {gtin_licences}/{licences} = {frac(gtin_licences, licences) * 100:.2f}% "
            f"of MDALL licences and {gtin_device_ids}/{device_ids} = "
            f"{frac(gtin_device_ids, device_ids) * 100:.2f}% of MDALL device lines can ever be joined "
            f"by an official UDI. ATLAS confirmed {confirmed} of them "
            f"({frac(confirmed, rows) * 100:.4f}% of all MDALL rows). This is a real but thin official "
            "bridge, concentrated in a few manufacturers; it is not a solution to global device identity."
        ),
        "falsifiers": falsifiers,
    }
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in (
        "joinable_ceiling", "confirmed_against_denominators", "sampling",
        "concentration", "generalisation_statement")}, indent=2))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
