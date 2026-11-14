"""P0 audit: what does '8.8% coverage' actually measure, and what is recall?

Four different quantities have been conflated in the SCIENCE-002 write-up:

  C1  UNIVERSE SHARE - of all cleared 510(k)s in the study window, the share that
      is attributable to the 48 universe firms. This is a property of the universe,
      not of the firms.
  C2  RECALL - of the 48 firms' own true FDA clearance activity, the share the
      name-based mapping captures. This has NO denominator in the current evidence
      and is reported as unknown. The audit only bounds the misses it can see.
  C3  PRECISION - of the accepted links, the share that do not contradict an
      independent FDA statement about the same establishment. The 2026
      owner/operator record is the only such statement available, so the test is:
      does a T_A (exact registrant-name) applicant belong, per FDA, to a *different*
      firm?
  C4  AMBIGUITY - accepted links whose applicant string is also a plausible match
      for another universe firm.

The audit also records a measured negative result that matters for SCIENCE-003:
the openfda registration_number / fei_number fields on a 510(k) record are
product-code level aggregates, not the establishment that filed the submission, so
they cannot carry a filing-level parent attribution.
"""

from __future__ import annotations

import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from research.science_002 import fda, pipeline, universe
from research.science_002.entity import normalise_name
from research.science_002.sources import Cache

from . import common

WINDOW_START = "2015-01-01"
WINDOW_END = "2026-08-31"

#: Tokens that describe a sector rather than a company. A miss found through one of
#: these is noise, so they are excluded from the brand-token search.
STOP = {"MEDICAL", "SYSTEMS", "SYSTEM", "TECHNOLOGY", "TECHNOLOGIES", "HEALTH",
        "HEALTHCARE", "DEVICES", "DEVICE", "GROUP", "INTERNATIONAL", "SCIENTIFIC",
        "LABORATORIES", "LABORATORY", "PRODUCTS", "SERVICES", "INNOVATIONS",
        "ULTRASOUND", "SURGICAL", "DIAGNOSTICS", "PHARMACEUTICALS", "INDUSTRIES",
        "CARE", "THERAPEUTICS", "VASCULAR", "ORTHOPAEDICS", "ORTHOPEDICS", "DENTAL",
        "GENERAL", "AMERICAN", "NATIONAL", "GLOBAL", "ADVANCED", "INTEGRATED",
        "UNITED", "SURGERY", "SPINE", "CARDIAC", "NEURO", "OPHTHALMIC", "BIO",
        "SIGHT", "CONCEPTS", "SOLUTIONS", "TECH", "SCIENCE", "PARTNERS", "DIABETES",
        "SHOULDER", "AESTHETICS", "INFORMATION", "ENERGY", "COILS", "ADVANCED",
        "MANAGEMENT", "RESEARCH", "ASSOCIATES", "HOLDINGS"}
SHORT_BRANDS = {"GE", "3M", "SI", "BD", "EW", "AB"}


def _distinctive_tokens(firm: Any) -> list[str]:
    """The brand tokens of a registrant: leading tokens that are not sector words.

    Only the first two meaningful tokens are used, because later tokens describe the
    product line rather than the company and generate spurious matches.
    """
    out = []
    for token in normalise_name(firm.sec_title).split():
        if token in STOP:
            continue
        if len(token) >= 4 or token in SHORT_BRANDS:
            out.append(token)
        if len(out) == 2:
            break
    return out


def _owner_by_registration_root(path: Path) -> dict[str, set[str]]:
    owners: dict[str, set[str]] = defaultdict(set)
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            reg_root = normalise_name(row["registration_name"])
            own_root = normalise_name(row["owner_firm"])
            if reg_root and own_root:
                owners[reg_root].add(own_root)
    return owners


def name_space_misses(build: Any, applicants: Mapping[str, int],
                      accepted_roots: Mapping[str, str]) -> list[dict[str, Any]]:
    misses: list[dict[str, Any]] = []
    for firm in build.included:
        for token in _distinctive_tokens(firm):
            for root, n in applicants.items():
                if root in accepted_roots:
                    continue
                if token not in root.split():
                    continue
                misses.append({"ticker": firm.ticker, "token": token,
                               "applicant_root": root, "clearances_window": n})
    seen = set()
    out = []
    for row in sorted(misses, key=lambda r: -r["clearances_window"]):
        key = (row["ticker"], row["applicant_root"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def tier_conflicts(build: Any, owners: Mapping[str, set[str]],
                   firm_roots: Mapping[str, str]):
    conflicts = []
    clean = []
    for firm in build.included:
        former = {normalise_name(n) for n, _a, _b in firm.former_names}
        for match in firm.applicants:
            root = str(match["applicant_root"])
            tier = str(match["tier"])
            owner_roots = owners.get(root, set())
            if not owner_roots:
                clean.append({"ticker": firm.ticker, "applicant_root": root,
                              "tier": tier, "reason": "no registration record"})
                continue
            foreign = {o for o in owner_roots
                       if o != normalise_name(firm.sec_title) and o not in former}
            if foreign:
                conflicts.append({
                    "ticker": firm.ticker, "applicant_root": root, "tier": tier,
                    "fda_owner_roots": sorted(foreign),
                    "fda_owner_is_other_universe_firm": sorted(
                        {firm_roots[o] for o in foreign if o in firm_roots}),
                    "n_window_clearances": int(match["n_window_clearances"]),
                })
            else:
                clean.append({"ticker": firm.ticker, "applicant_root": root,
                              "tier": tier, "reason": "owner matches"})
    return conflicts, clean


def establishment_field_shape(links_path: Path) -> dict[str, Any]:
    counts: list[int] = []
    sets: dict[str, set[str]] = defaultdict(set)
    rows = 0
    with Path(links_path).open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            n = int(row["n_registration_numbers"] or 0)
            counts.append(n)
            if row["registration_numbers"]:
                sets[row["registration_numbers"]].add(row["applicant"].upper())
    shared = sum(1 for apps in sets.values() if len(apps) > 1)
    return {
        "rows": rows,
        "share_with_any_registration_number": sum(1 for n in counts if n > 0) / rows,
        "share_with_exactly_one": sum(1 for n in counts if n == 1) / rows,
        "median_registration_numbers_per_record": statistics.median(counts),
        "p90": sorted(counts)[int(0.9 * len(counts))],
        "max": max(counts),
        "distinct_registration_sets": len(sets),
        "sets_shared_by_more_than_one_applicant": shared,
        "largest_shared_set_applicants": max((len(a) for a in sets.values()), default=0),
        "interpretation": (
            "The identifiers are a product-code-level aggregate inherited from device "
            "listing, not the establishment that filed the submission: the median "
            "record carries 104 registration numbers, only 0.7% carry one, and 3,282 "
            "of 4,049 distinct sets are shared across different applicants."),
    }


def run(cache: Cache, verbose: bool = True) -> dict[str, Any]:
    build = pipeline.build_universe(cache, verbose=False, cache_dir=common.CACHE_RAW)
    records = fda.read_records_csv(common.raw("fda_510k_records.csv"))
    counts = universe.window_clearance_counts(records)

    accepted_roots: dict[str, str] = {}
    for firm in build.included:
        for match in firm.applicants:
            accepted_roots[str(match["applicant_root"])] = firm.ticker

    total_clearances = sum(
        1 for row in records
        if (row.get("decision_code") or "") in fda.CLEARED_DECISION_CODES
        and WINDOW_START <= (row.get("decision_date") or "") <= WINDOW_END)
    attributed = sum(counts[root] for root in accepted_roots)
    distinct_applicants = len({normalise_name(row.get("applicant") or "")
                               for row in records
                               if (row.get("decision_code") or "") in fda.CLEARED_DECISION_CODES
                               and WINDOW_START <= (row.get("decision_date") or "") <= WINDOW_END})

    owners = _owner_by_registration_root(common.raw("fda_registration_owner_map.csv"))
    firm_roots = {normalise_name(f.sec_title): f.ticker for f in build.included}
    conflicts, clean = tier_conflicts(build, owners, firm_roots)
    misses = name_space_misses(build, counts, accepted_roots)
    establish = establishment_field_shape(common.DATA_R / "510k_establishment_links.csv")

    by_tier = Counter(str(m["tier"]) for firm in build.included for m in firm.applicants)
    tier_clearances = Counter()
    for firm in build.included:
        for m in firm.applicants:
            tier_clearances[str(m["tier"])] += int(m["n_window_clearances"])

    out = {
        "meta": {"window": [WINDOW_START, WINDOW_END], "n_firms": len(build.included)},
        "C1_universe_share": {
            "numerator_attributed_clearances": attributed,
            "denominator_all_cleared_510k_in_window": total_clearances,
            "share": attributed / total_clearances if total_clearances else None,
            "distinct_applicants_in_window": distinct_applicants,
            "note": "a property of the universe, not a recall of the firms",
        },
        "C2_recall": {
            "value": "unknown",
            "denominator": "the firms' true total FDA clearance activity is not published "
                           "at the legal-entity level, so no recall can be computed from "
                           "public evidence",
            "candidate_misses_found": len(misses),
            "candidate_miss_clearances": sum(m["clearances_window"] for m in misses),
            "candidate_misses_unadjudicated": True,
            "top_candidate_misses": misses[:25],
            "interpretation": (
                "These are applicant strings that carry a registrant's brand token but "
                "were not attributed. They are unadjudicated: some are genuinely the "
                "same group (a 'dba' name that never appears as an FDA registration, so "
                "the owner/operator hop cannot see it), others belong to a different "
                "company that shares a word. The count is therefore evidence of a "
                "structural blind spot in the name channel, not a measurement of recall."),
        },
        "C3_precision": {
            "n_links": sum(by_tier.values()),
            "n_links_with_fda_owner_conflict": len(conflicts),
            "links_with_owner_conflict": conflicts,
            "n_links_without_registration_record": sum(
                1 for row in clean if row["reason"] == "no registration record"),
            "note": "the only independent FDA statement about an establishment is the "
                    "2026 owner/operator record; a conflict means FDA attributes that "
                    "establishment to a different firm, not that the 510(k) belonged "
                    "to a different firm",
        },
        "C4_links_by_tier": dict(by_tier),
        "C4_clearances_by_tier": dict(tier_clearances),
        "establishment_identifiers": establish,
    }
    if verbose:
        print("C1", out["C1_universe_share"]["share"], "links", sum(by_tier.values()),
              "conflicts", len(conflicts), "misses", len(misses), flush=True)
    return out