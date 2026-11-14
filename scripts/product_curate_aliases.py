#!/usr/bin/env python3
"""Curate observed openFDA applicant spellings into the organization registry.

Why this exists
---------------
The research roster (config/companies_device.json) lists *brand-level* aliases such as
"MEDTRONIC" or "BIO-MEDICAL". Real openFDA records store legal-entity strings such as
"Medtronic Cardiac Rhythm Disease Management" or "Fujifilm Sonosite, Inc.". Exact matching
against brand aliases alone therefore leaves most records unattributed.

This script proposes the missing spellings using one narrow, auditable rule:

    a spelling observed inside an organization's own collection scope is accepted only when it
    contains one of that organization's distinctive search tokens as a whole-word sequence,
    and does not contain an explicit exclusion token for that organization.

It never uses fuzzy matching, edit distance or substring-without-boundary matching. Every
proposal is written as review="pending_review" with its evidence, and the product labels
those attributions as provisional until a human reviews them.

Usage::

    python scripts/product_curate_aliases.py            # report only
    python scripts/product_curate_aliases.py --apply    # write proposals into the registry
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "medradar" / "product" / "identity" / "organizations.json"
SNAPSHOT_APPLICANTS = ROOT / "data" / "product" / "applicants.jsonl.gz"

#: Tokens that must never be used for automatic acceptance, even if they appear in the scope.
WEAK_TOKENS = {"USA", "INC", "CORP", "CORPORATION", "MEDICAL", "SYSTEMS", "HEALTH", "GROUP", "LAB", "LABS", "COMPANY"}

#: Strings that contain a brand token but belong to a different business. Documented per case.
EXCLUSIONS = {
    "fresenius_medical_care": {
        "KABI": "Fresenius Kabi is a separate listed business inside the Fresenius group; it is not Fresenius Medical Care.",
    },
    "draeger": {
        "SAFETY": "Dräger Safety (gas detection) is not the medical business; rejected explicitly in the reviewed alias set.",
    },
    "philips": {
        "LIGHTING": "Philips Lighting became Signify; lighting records are not medical devices.",
        "SIGNIFY": "Signify is a separate listed company after the lighting spin-off.",
    },
    "siemens_healthineers": {
        "ENERGY": "Siemens Energy is a separate listed company.",
        "MOBILITY": "Siemens Mobility is a separate business unit, not medical technology.",
        "INDUSTRY": "Siemens Industry is not medical technology.",
    },
    "ge_healthcare": {
        "AVIATION": "GE Aerospace is a separate listed company.",
        "POWER": "GE Vernova is a separate listed company.",
        "CAPITAL": "GE Capital is not the medical device business.",
    },
    "bd": {
        "BARD COLLEGE": "Bard College is an unrelated institution.",
    },
    "medtronic": {
        "FOUNDATION": "Charitable foundation records are not device submissions.",
    },
}

MIN_TOKEN_CHARS = 4  # brand tokens shorter than this are too generic to auto-accept (e.g. "BD")


def words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


def contains_sequence(haystack: list[str], needle: list[str]) -> bool:
    if not needle:
        return False
    limit = len(haystack) - len(needle)
    for start in range(limit + 1):
        if haystack[start : start + len(needle)] == needle:
            return True
    return False


def load_applicants(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit("missing " + str(path) + "; run scripts/product_collect.py first")
    import gzip

    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Propose observed applicant spellings for the registry.")
    parser.add_argument("--apply", action="store_true", help="write proposals into the registry")
    parser.add_argument("--snapshot-applicants", default=str(SNAPSHOT_APPLICANTS))
    args = parser.parse_args(argv)

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    applicants = load_applicants(Path(args.snapshot_applicants))

    existing: dict[str, str] = {}
    for org in registry["organizations"]:
        for item in org.get("accept_exact") or []:
            existing[" ".join(item["value"].casefold().split())] = org["key"]

    proposals: dict[str, list[dict]] = defaultdict(list)
    conflicts: list[dict] = []
    unresolved: dict[str, list[dict]] = defaultdict(list)
    rejected_proposals: list[dict] = []

    for org in registry["organizations"]:
        key = org["key"]
        token_phrases = []
        for token in org.get("search_tokens") or []:
            token_words = words(token)
            if len(token_words) == 1 and len(token_words[0]) < MIN_TOKEN_CHARS:
                continue
            if all(word in WEAK_TOKENS for word in token_words):
                continue
            token_phrases.append(token_words)
        exclusions = EXCLUSIONS.get(key, {})
        for row in applicants:
            name = row.get("applicant_name") or ""
            scopes = row.get("by_org_scope") or {}
            if key not in scopes:
                continue
            normalised = " ".join(name.casefold().split())
            if normalised in existing:
                continue
            name_words = words(name)
            matched = [phrase for phrase in token_phrases if contains_sequence(name_words, phrase)]
            if not matched:
                unresolved[key].append({"applicant_name": name, "records": int(row.get("records") or 0)})
                continue
            excluded = [token for token in exclusions if contains_sequence(name_words, words(token))]
            if excluded:
                rejected_proposals.append({
                    "organization_key": key,
                    "applicant_name": name,
                    "records": int(row.get("records") or 0),
                    "reason": exclusions[excluded[0]],
                })
                continue
            # A string that matches two organizations' tokens is not auto-accepted.
            other_matches = []
            for other in registry["organizations"]:
                if other["key"] == key:
                    continue
                other_phrases = []
                for token in other.get("search_tokens") or []:
                    token_words = words(token)
                    if len(token_words) == 1 and len(token_words[0]) < MIN_TOKEN_CHARS:
                        continue
                    if all(word in WEAK_TOKENS for word in token_words):
                        continue
                    other_phrases.append(token_words)
                if any(contains_sequence(name_words, phrase) for phrase in other_phrases):
                    other_matches.append(other["key"])
            if other_matches:
                conflicts.append({
                    "applicant_name": name,
                    "proposed": key,
                    "also_matches": other_matches,
                    "records": int(row.get("records") or 0),
                })
                continue
            proposals[key].append({
                "value": name,
                "basis": "brand",
                "review": "pending_review",
                "source": "openfda_observed_spelling (auto-proposed by scripts/product_curate_aliases.py; human review pending)",
                "matched_token": " / ".join(" ".join(phrase) for phrase in matched[:2]),
                "records": int(row.get("records") or 0),
            })

    total_proposed = 0
    for key in sorted(proposals):
        entries = sorted(proposals[key], key=lambda item: -item["records"])
        total_proposed += len(entries)
        print("== " + key + ": " + str(len(entries)) + " proposed spelling(s)")
        for entry in entries[:6]:
            print("   + " + str(entry["records"]).rjust(6) + "  " + entry["value"])
        if len(entries) > 6:
            print("   ... " + str(len(entries) - 6) + " more")

    print()
    print("proposed=" + str(total_proposed) + " conflicts=" + str(len(conflicts)) + " rejected=" + str(len(rejected_proposals)))
    if conflicts:
        print()
        print("conflicts (NOT auto-accepted, need a human decision):")
        for item in conflicts[:20]:
            print("   " + item["applicant_name"] + " -> " + item["proposed"] + " vs " + ",".join(item["also_matches"]))
    unresolved_total = sum(len(values) for values in unresolved.values())
    print()
    print("observed in scope but not attributable by rule: " + str(unresolved_total))
    for key in sorted(unresolved, key=lambda item: -sum(row["records"] for row in unresolved[item])):
        rows = sorted(unresolved[key], key=lambda item: -item["records"])[:5]
        if not rows:
            continue
        print("   " + key + ": " + ", ".join(row["applicant_name"] + "(" + str(row["records"]) + ")" for row in rows))

    if not args.apply:
        print()
        print("dry run; pass --apply to write these proposals into the registry")
        return 0

    written = 0
    for org in registry["organizations"]:
        key = org["key"]
        additions = proposals.get(key) or []
        if not additions:
            continue
        have = {" ".join(item["value"].casefold().split()) for item in org.get("accept_exact") or []}
        for entry in additions:
            normalised = " ".join(entry["value"].casefold().split())
            if normalised in have:
                continue
            have.add(normalised)
            org.setdefault("accept_exact", []).append({
                "value": entry["value"],
                "basis": entry["basis"],
                "review": entry["review"],
                "source": entry["source"],
            })
            written += 1
        for entry in rejected_proposals:
            if entry["organization_key"] != key:
                continue
            if any(" ".join(item["value"].casefold().split()) == " ".join(entry["applicant_name"].casefold().split()) for item in org.get("reject_exact") or []):
                continue
            org.setdefault("reject_exact", []).append({"value": entry["applicant_name"], "reason": entry["reason"]})

    registry["updated_at"] = "2026-11-15"
    registry["curation_note"] = (
        "Observed openFDA applicant spellings were added by scripts/product_curate_aliases.py under a "
        "whole-word token rule inside each organization's own collection scope. They are review=pending_review "
        "until a human signs them off; the product must label them as provisional."
    )
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote " + str(written) + " spelling(s) into " + str(REGISTRY))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
