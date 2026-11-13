#!/usr/bin/env python
"""Derive per-dimension source ratings from the register, using explicit rules.

Every rating is produced by a named rule that fires on structured register
fields (``connection_status``, ``authentication``, ``timestamp_fields``,
``entity_identifiers``, ``known_limitations``, ``update_frequency``,
``historical_coverage``).  Nothing is scored on record volume — the rubric's
first anti-gaming rule.

A small override table exists for the cases where a rule is demonstrably wrong;
each override must carry a ``why`` and is listed in the output so a reviewer can
see exactly where human judgement replaced the rule.

    python research/data_expansion/tools/derive_scores.py --check
    python research/data_expansion/tools/derive_scores.py --write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

REGISTER = ROOT / "GLOBAL_DATA_SOURCE_REGISTER.json"
RUBRIC = ROOT / "registry" / "SOURCE_SCORING_RUBRIC.json"
OUT = ROOT / "registry" / "source_scores.json"

VERIFIED = {"VERIFIED_API", "VERIFIED_BULK_DOWNLOAD", "VERIFIED_PUBLIC_QUERY"}

#: Human overrides.  Each entry needs a `why` for every dimension it touches.
OVERRIDES: dict[str, dict[str, Any]] = {
    "accessgudid": {
        "complementarity": (4, "GUDID is the upstream UDI authority; openFDA /device/udi is a mirror of it, so this is the primary identity anchor for products rather than a duplicate"),
        "product_linkage": (4, "DI is a globally unique device identifier and is the join key to any other UDI-based registry"),
        "entity_linkage": (4, "manufacturer DUNS + structured manufacturer name are authoritative"),
    },
    "openfda_device_510k": {
        "complementarity": (1, "already collected by medradar/collect_device.py on main; adds no new upstream authority"),
    },
    "openfda_device_pma": {
        "complementarity": (1, "already collected on main"),
    },
    "openfda_device_recall": {
        "complementarity": (1, "already collected on main"),
    },
    "openfda_device_maude": {
        "complementarity": (3, "MAUDE is NOT collected on main; it is a genuinely new post-market channel, but its counts are reporting behaviour, not incidence"),
        "early_evidence_potential": (0, "structurally post-market: an adverse event cannot precede the clearance it follows"),
    },
    "clinicaltrials_gov": {
        "complementarity": (1, "already collected on main"),
    },
    "europepmc": {
        "time_credibility": (4, "firstPublicationDate plus firstIndexDate are both exposed, so the publication clock and the metadata clock are separable"),
    },
    "openalex": {
        "time_credibility": (3, "publication_date is usable, but created_date is an ingestion clock that often post-dates publication by years; the source does not label the distinction, so the user must"),
    },
    "crossref": {
        "time_credibility": (3, "published/issued vs deposited are separable but the field semantics vary by publisher"),
    },
    "uk_find_a_tender": {
        "time_credibility": (4, "release.date (publication), contracts[0].dateSigned (signature) and awards[0].date (null in practice) are separate fields; the distinction is documented in the connector"),
        "entity_linkage": (4, "supplier name plus an OCDS organisation identifier (GB-FTS-...) is the only procurement source here that gives both"),
        "product_linkage": (1, "CPV codes are categories, not products; no device identifier exists in the data"),
    },
    "usaspending": {
        "time_credibility": (1, "no public-visibility date exists at all: only action, signature and performance dates. The connector deliberately leaves source_public_at empty rather than substituting a performance date"),
        "product_linkage": (0, "no device product identifier anywhere in the award records"),
    },
    "eu_ted": {
        "entity_linkage": (1, "winner-name / winner-partname return null even for 2024 medical-device award notices, so the award cannot be tied to a supplier"),
        "product_linkage": (1, "CPV category only"),
    },
    "greenhouse": {
        "entity_linkage": (2, "the platform is verified, but none of the five target firms has a board; the entity linkage is only available for whatever org does have one"),
        "complementarity": (1, "no coverage of the target firms, so the practical increment for this project is zero"),
    },
    "lever": {
        "entity_linkage": (2, "platform verified against control boards; none of the five target firms is present"),
        "complementarity": (1, "no coverage of the target firms"),
    },
    "un_comtrade": {
        "entity_linkage": (0, "country-level aggregates only: no company, no shipment"),
        "product_linkage": (1, "HS chapter-level commodity codes, not device identifiers"),
        "complementarity": (2, "macro demand background; not a substitute for company-level trade data"),
    },
    "uk_hmrc_trade": {
        "entity_linkage": (3, "a named UK trader plus an HS code is the only verified company-identifiable trade channel; no value, quantity or partner"),
        "product_linkage": (1, "CN8 commodity code, not a device identifier"),
        "complementarity": (3, "the only company-identifiable trade source that was verified without registration, so it is genuinely additive despite its thin fields"),
    },
    "europepmc_dup_check": {},
    "epo_ops": {
        "complementarity": (4, "patents are entirely missing from main; if access were obtained this would be the single largest capability gap it fills"),
    },
}

MONTHS_RE = re.compile(r"(19|20)\d{2}")


def _clamp(value: int) -> int:
    return max(0, min(4, value))


def _has_any(text: str, needles: list[str]) -> bool:
    lowered = text.lower()
    return any(n.lower() in lowered for n in needles)


def accessibility(record: dict) -> tuple[int, str]:
    status = record.get("connection_status", "NOT_TESTED")
    auth = str(record.get("authentication", ""))
    keyless = "none" in auth.lower() or auth.upper() == "UNKNOWN" and status == "VERIFIED_API"
    if status in {"VERIFIED_API", "VERIFIED_BULK_DOWNLOAD"}:
        return (4 if keyless else 3), f"rule: {status} with authentication={auth[:40]!r}"
    if status == "VERIFIED_PUBLIC_QUERY":
        return 2, "rule: public query page parsed, no stable machine interface"
    if status == "REQUIRES_REGISTRATION":
        return 1, "rule: real access exists but requires an account/key"
    if status == "PAID_ONLY":
        return 1, "rule: only commercial access"
    return 0, f"rule: {status} — no working programmatic access"


def time_credibility(record: dict) -> tuple[int, str]:
    fields = " ".join(str(f) for f in record.get("timestamp_fields", []) or [])
    limitations = " ".join(str(x) for x in record.get("known_limitations", []) or [])
    score = 2
    reason = ["baseline 2"]
    event_terms = ["decision_date", "event_date", "eventDate", "dateSigned", "startDate", "start_date", "dateOfEvent"]
    public_terms = ["publishDate", "publication_date", "firstPublicationDate", "published", "release.date", "date_posted"]
    if _has_any(fields, event_terms):
        score += 1
        reason.append("event-date field documented")
    if _has_any(fields, public_terms):
        score += 1
        reason.append("publication-date field documented")
    if _has_any(limitations, ["no published_at", "no publication", "no public-visibility", "coarse", "no published date"]):
        score -= 1
        reason.append("register records an explicit publication-clock defect")
    if _has_any(limitations, ["created_date", "deposited", "ingestion clock", "metadata clock"]):
        score -= 1
        reason.append("register warns that a metadata clock is not a publication clock")
    if record.get("connection_status") in {"UNAVAILABLE", "PAID_ONLY", "BLOCKED_BY_POLICY", "REQUIRES_REGISTRATION"}:
        score = min(score, 2)
        reason.append("capped at 2 because the source could not be exercised")
    return _clamp(score), "rule: " + "; ".join(reason)


def entity_linkage(record: dict) -> tuple[int, str]:
    blob = " ".join(
        [str(i) for i in record.get("entity_identifiers", []) or []]
        + [str(record.get("research_value", ""))]
        + [str(record.get("known_limitations", ""))]
    )
    strong = ["CIK", "LEI", "DUNS", "OCDS", "organisation identifier", "organization id", "trader", "applicant", "manufacturer", "sponsor", "recipient", "ROR", "company number"]
    if _has_any(blob, strong):
        score = 3
        if _has_any(blob, ["CIK", "LEI", "DUNS", "GB-FTS"]) and record.get("connection_status") in VERIFIED:
            score = 4
        return score, "rule: structured company identifier/field documented"
    if _has_any(blob, ["company", "firm", "organization", "organisation", "institution"]):
        return 1, "rule: company appears only as free text"
    return 0, "rule: no company-attributable field"


def product_linkage(record: dict) -> tuple[int, str]:
    ids = " ".join(str(i) for i in record.get("entity_identifiers", []) or [])
    blob = ids + " " + " ".join(str(f) for f in record.get("timestamp_fields", []) or [])
    if _has_any(ids, ["UDI", "DI ", " DI", "510(k)", "PMA", "NCT", "DOI", "patent", "OCID", "ndc"]):
        return 3, "rule: an authoritative product/document identifier is documented"
    if _has_any(ids, ["model", "catalog", "product code", "CPV", "HS", "CN8"]):
        return 1, "rule: category/model-level only, not a device identifier"
    return 0, "rule: no product-level identifier"


def licence_and_cost(record: dict) -> tuple[int, str]:
    status = record.get("connection_status")
    redistribution = str(record.get("redistribution_allowed", "UNKNOWN")).upper()
    licence = str(record.get("licence", "")).lower()
    if status == "PAID_ONLY":
        # Rubric band 0 is "paid and price not public, or use prohibited";
        # band 1 is "paid with a public, expensive price list".  The distinction
        # matters because a public price is a decision the project can make.
        blob = " ".join(
            [str(record.get("cost_notes", "")), str(record.get("free_tier", "")), str(record.get("licence", ""))]
        )
        if "$" in blob or "price" in blob.lower() or "per month" in blob.lower():
            return 1, "rule: paid, public price list (rubric band 1)"
        return 0, "rule: paid, price not public / institutional quote (rubric band 0)"
    if redistribution == "YES" and _has_any(licence, ["public domain", "cc0", "cc by", "open"]):
        return 4, "rule: open licence and redistribution allowed"
    if redistribution == "YES":
        return 3, "rule: free to use, redistribution allowed but licence not clearly open"
    if redistribution == "PARTIAL":
        return 3, "rule: free to use, partial redistribution"
    if status == "REQUIRES_REGISTRATION":
        return 2, "rule: free but requires registration"
    return 1, "rule: licence/redistribution UNKNOWN — treated as restrictive"


def historical_coverage(record: dict) -> tuple[int, str]:
    text = str(record.get("historical_coverage", ""))
    matches = [int(m.group(0)) for m in MONTHS_RE.finditer(text)]
    if not matches:
        return 1, "rule: coverage not quantified"
    earliest = min(matches)
    if earliest <= 1970:
        return 4, f"rule: coverage reaches {earliest}"
    if earliest <= 2000:
        return 3, f"rule: coverage reaches {earliest}"
    if earliest <= 2015:
        return 2, f"rule: coverage reaches {earliest}"
    return 1, f"rule: coverage only from {earliest}"


def update_stability(record: dict) -> tuple[int, str]:
    text = str(record.get("update_frequency", "")).lower()
    if "daily" in text or "continuous" in text or "real-time" in text:
        return 4, "rule: daily/continuous update"
    if "month" in text:
        return 3, "rule: monthly update"
    if "quarter" in text or "annual" in text or "year" in text:
        return 2, "rule: quarterly/annual update"
    return 1, "rule: update cadence not documented"


def complementarity(record: dict) -> tuple[int, str]:
    source_id = str(record.get("source_id", ""))
    if source_id.startswith("openfda_") or source_id in {"clinicaltrials_gov"}:
        return 1, "rule: already collected by main; only new fields would add value"
    if record.get("connection_status") not in VERIFIED:
        return 2, "rule: cannot be assessed as additive until it is exercised"
    return 3, "rule: a different upstream authority or a channel main does not collect"


def early_evidence_potential(record: dict) -> tuple[int, str]:
    domain = str(record.get("domain", ""))
    kind = str(record.get("category", "")).lower()
    if _has_any(str(record.get("known_limitations", "")), ["structurally", "post-market", "postmarket"]):
        return 0, "rule: structurally post-event"
    if domain in {"C", "D", "H"}:
        return 3, "rule: pre-regulatory research activity by construction, with datable publication clocks"
    if domain in {"B", "G"}:
        return 2, "rule: theoretically earlier than regulatory action, no case evidence this round"
    if domain in {"F", "E"}:
        return 2, "rule: procurement/trade activity can precede approval but the link to a technology is weak"
    return 1, "rule: regulatory-domain source; publication follows the event"


def maintenance_cost(record: dict) -> tuple[int, str]:
    status = record.get("connection_status")
    if status in {"VERIFIED_API", "VERIFIED_BULK_DOWNLOAD"}:
        return 4, "rule: stable machine interface"
    if status == "VERIFIED_PUBLIC_QUERY":
        return 1, "rule: HTML/undocumented endpoint, will break on redesign"
    if status in {"REQUIRES_REGISTRATION", "PAID_ONLY"}:
        return 3, "rule: credential/contract maintenance only"
    return 2, "rule: not exercised, cost unknown"


RULES = {
    "accessibility": accessibility,
    "licence_and_cost": licence_and_cost,
    "time_credibility": time_credibility,
    "entity_linkage": entity_linkage,
    "product_linkage": product_linkage,
    "historical_coverage": historical_coverage,
    "update_stability": update_stability,
    "complementarity": complementarity,
    "early_evidence_potential": early_evidence_potential,
    "maintenance_cost": maintenance_cost,
}


def build(register: dict, rubric: dict) -> dict:
    entries: dict[str, Any] = {}
    for record in register.get("sources", []):
        source_id = record["source_id"]
        ratings: dict[str, Any] = {}
        for dim in rubric["dimensions"]:
            key = dim["id"]
            score, why = RULES[key](record)
            override = OVERRIDES.get(source_id, {}).get(key)
            if override:
                score, why = override
                why = "OVERRIDE: " + why
            ratings[key] = {"score": score, "why": why}
        entries[source_id] = {
            "connection_status": record.get("connection_status"),
            "domain": record.get("domain"),
            "ratings": ratings,
        }
    return {
        "schema": "medradar.external.source_scores.v1",
        "derived_from": "GLOBAL_DATA_SOURCE_REGISTER.json + named rules in tools/derive_scores.py",
        "note": "Ratings are rule-derived; every OVERRIDE carries a written justification. No dimension uses record volume.",
        "n_sources": len(entries),
        "sources": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if not REGISTER.exists():
        print("run build_register.py first", file=sys.stderr)
        return 1
    register = json.loads(REGISTER.read_text(encoding="utf-8"))
    rubric = json.loads(RUBRIC.read_text(encoding="utf-8"))
    payload = build(register, rubric)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.write:
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT} with {payload['n_sources']} source ratings")
    else:
        print(f"would write {payload['n_sources']} source ratings")
    # report the weight sum so a rubric edit cannot silently break normalisation
    total = sum(d["weight"] for d in rubric["dimensions"])
    print(f"rubric weight sum = {total:.6f}")
    return 0 if abs(total - 1.0) < 1e-9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
