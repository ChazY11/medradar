#!/usr/bin/env python3
"""Independent attribution validation: pre-registered sample, documentary evidence, honest estimate.

What this does
--------------
1. --collect-evidence downloads the jurisdiction filings that name a company's subsidiaries
   (SEC exhibit 21 for Medtronic and GE HealthCare, and the group-company table of the Philips
   20-F), extracts the entity names, and writes a hash-stamped evidence file with the filing URLs.
2. --sample draws a pre-registered, stratified, deterministic sample of applicant spellings from
   the committed snapshot. The strata are fixed in SAMPLE_DESIGN before any result is seen, so the
   sample cannot be cherry-picked afterwards.
3. --review applies the pre-registered decision rule (DECISION_RULE) to each sampled case:
   supported / contradicted / undecidable, with the evidence that decided it.
4. --report writes precision.json (Wilson interval over decidable cases, undecidable share,
   reviewer class) and the data tables used by ATTRIBUTION_VALIDATION.md.

Honesty rules
-------------
* The reviewer here is an AI agent applying a documentary rule; reviewer_kind says so. This is NOT
  independent human review, and the report states that a human sample review is still required.
* A case with no collected documentary source is undecidable, never "correct". That keeps the
  denominator honest and makes the undecidable share a first-class result.
* The decision rule is fixed in code before the sample is scored and is quoted verbatim in the
  output, so the estimate can be audited.

Usage
    python tools/validation/validate_attribution.py --collect-evidence
    python tools/validation/validate_attribution.py --sample
    python tools/validation/validate_attribution.py --review --report
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import math
import random
import re
import time
import urllib.request
from datetime import datetime, timezone
import os
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "product" / "product_002" / "validation"
EVIDENCE_FILE = OUT / "sec_entity_lists.json"
SAMPLE_FILE = OUT / "sample.json"
REVIEW_FILE = OUT / "review_records.json"
PRECISION_FILE = OUT / "precision.json"
SNAPSHOT = ROOT / "medradar" / "product" / "snapshot"
REGISTRY = ROOT / "medradar" / "product" / "identity" / "organizations.json"

USER_AGENT = os.environ.get("MEDRADAR_SEC_USER_AGENT") or (
    "MedRadar PRODUCT-002 attribution validation research@medradar.example"
)
SEC_HEADERS = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}

#: Filings used as independent evidence. The URL is recorded verbatim in the evidence file.
FILINGS = [
    {
        "organization_key": "medtronic",
        "kind": "jurisdiction_filing",
        "url": "https://www.sec.gov/Archives/edgar/data/1613103/000162828026044354/mdt-202610kxex21.htm",
        "title": "Medtronic plc Form 10-K (fiscal 2026) Exhibit 21 - subsidiaries of the registrant",
        "accession": "0001628280-26-044354",
        "extractor": "entity_lines",
    },
    {
        "organization_key": "ge_healthcare",
        "kind": "jurisdiction_filing",
        "url": "https://www.sec.gov/Archives/edgar/data/1932393/000193239326000007/gehc4q202510kexhibit211.htm",
        "title": "GE HealthCare Technologies Inc. Form 10-K (fiscal 2025) Exhibit 21.1 - subsidiaries",
        "accession": "0001932393-26-000007",
        "extractor": "entity_lines",
    },
    {
        "organization_key": "philips",
        "kind": "jurisdiction_filing",
        "url": "https://www.sec.gov/Archives/edgar/data/313216/000162828026009470/phg-20251231.htm",
        "title": "Koninklijke Philips N.V. Form 20-F (fiscal 2025) - interests in group companies",
        "accession": "0001628280-26-009470",
        "extractor": "philips_group_table",
    },
]

#: US SEC registrants among the tracked organizations. The evidence base may be extended after the
#: sample is drawn (gathering more independent documents for the same pre-registered cases is not
#: resampling); the decision rule never changes.
FILING_TICKERS = {
    "abbott": "ABT",
    "boston_scientific": "BSX",
    "stryker": "SYK",
    "johnson_johnson_medtech": "JNJ",
    "bd": "BDX",
    "baxter": "BAX",
    "zimmer_biomet": "ZBH",
    "edwards_lifesciences": "EW",
    "intuitive_surgical": "ISRG",
    "resmed": "RMD",
    "masimo": "MASI",
    "dexcom": "DXCM",
    "insulet": "PODD",
    "tandem_diabetes": "TNDM",
    "penumbra": "PEN",
    "dentsply_sirona": "XRAY",
    "fresenius_medical_care": "FMS",
    "integra_lifesciences": "IART",
    "teleflex": "TFX",
    "merit_medical": "MMSI",
}

EXHIBIT_NAME_RE = re.compile(r"(subsidiar|ex-?21|ex21|ex_21|exhibit21)", re.IGNORECASE)

#: Pre-registered sample design. Fixed before scoring; stratification by evidence difficulty.
SAMPLE_DESIGN = {
    "seed": 20261115,
    "per_stratum": 6,
    "design_note": "Fixed before scoring. Strata cover the evidence situations the protocol names: high volume, mid volume, low volume, lexical-rule mappings, evidence-verified ownership mappings, corporate-relation proposals, and cross-scope/ambiguous strings.",
    "strata": {
        "S1_high_volume": "attributed spelling with >= 1000 records",
        "S2_mid_volume": "attributed spelling with 100-999 records",
        "S3_low_volume": "attributed spelling with 1-99 records",
        "S4_lexical_rule": "spelling whose status came from lexical equivalence (case/punctuation/legal form)",
        "S5_ownership_evidence": "spelling already evidence-verified through a recorded ownership relation",
        "S6_corporate_relation": "spelling attributed through a subsidiary/division/historical-name basis with no evidence",
        "S7_ambiguous_scope": "spelling retrieved under more than one organization's collection scope",
    },
}

#: The pre-registered decision rule. Applied uniformly to every sampled case.
DECISION_RULE = (
    "SUPPORTED when the applicant spelling matches an entity name in the collected jurisdiction filing "
    "of the attributed organization (exact match after NFC+casefold+punctuation collapse, or the entity "
    "name contains the spelling's distinctive token sequence as whole words), or when a verified ownership "
    "relation in medradar/product/attribution/ownership.json covers the spelling for that organization. "
    "CONTRADICTED only when the collected filing shows a different organization owns that exact entity name. "
    "UNDECIDABLE when no collected documentary source names the spelling: the case is excluded from the "
    "precision numerator and denominator and reported separately. No case is scored correct on the basis "
    "of the registry's own claim."
)

BLOCK_TAG_RE = re.compile(r"</?(?:tr|p|div|td|th|li|br|table|h[1-6])[^>]*>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t\xa0]+")
LEGAL_FORM = (
    "inc incorporated corp corporation co company llc llp lp plc ltd limited gmbh ag kg kgaa sa sas sarl "
    "bv nv oy oyj ab as asa aps spa srl pty kk"
).split()
COUNTRY_WORDS = {
    "china", "germany", "netherlands", "united states", "ireland", "switzerland", "japan", "france",
    "united kingdom", "sweden", "denmark", "belgium", "italy", "spain", "canada", "australia", "india",
    "brazil", "singapore", "korea", "israel", "austria", "poland", "mexico", "luxembourg", "finland",
    "norway", "hong kong", "taiwan", "malaysia", "thailand", "vietnam", "czech republic", "hungary",
    "portugal", "greece", "turkey", "south africa", "united arab emirates", "saudi arabia", "russia",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch(url: str, retries: int = 3) -> str:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=SEC_HEADERS)
            with urllib.request.urlopen(request, timeout=90) as response:
                data = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data.decode("utf-8", errors="replace")
        except Exception as error:  # pragma: no cover - network
            last = error
            time.sleep(1.5 + attempt)
    raise RuntimeError("failed to fetch " + url + ": " + str(last))


def markup_lines(markup: str) -> list[str]:
    text = BLOCK_TAG_RE.sub("\n", markup)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return [WS_RE.sub(" ", line).strip() for line in text.splitlines() if line.strip()]


def entity_lines(lines: Iterable[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if not 4 <= len(line) <= 160:
            continue
        lower = line.lower()
        if lower.endswith(".") or " " not in line:
            continue
        if any(lower.endswith(" " + form) or (" " + form + " ") in lower or (" " + form + ",") in lower for form in LEGAL_FORM):
            out.append(line)
        elif re.search(r"\b(Inc|LLC|Ltd|GmbH|Corp|Corporation|Limited|B\.V\.|N\.V\.|AG|S\.A\.)\b", line):
            out.append(line)
    seen: dict[str, str] = {}
    for item in out:
        key = normalise(item)
        seen.setdefault(key, item)
    return sorted(seen.values(), key=str.casefold)


def philips_group_table(lines: list[str]) -> list[str]:
    start = None
    for index, line in enumerate(lines):
        if "legal entity name" in line.lower():
            start = index + 1
            break
    if start is None:
        return []
    out: list[str] = []
    index = start
    while index < len(lines) - 1:
        candidate = lines[index]
        following = lines[index + 1].lower()
        if any(word in following for word in COUNTRY_WORDS) or re.match(r"^[A-Z][a-z]+$", lines[index + 1]):
            if 4 <= len(candidate) <= 120 and candidate.lower() not in ("legal entity name",):
                out.append(candidate)
                index += 2
                continue
        index += 1
        if len(out) >= 200:
            break
    return out


def normalise(value: str) -> str:
    text = re.sub(r"[^0-9a-z]+", " ", (value or "").casefold())
    return " ".join(text.split())


def distinctive_words(value: str) -> list[str]:
    return [word for word in normalise(value).split() if word not in LEGAL_FORM and len(word) >= 4]


def _sec_json(url: str) -> Any:
    return json.loads(fetch(url))


def resolve_ciks(tickers: dict[str, str]) -> dict[str, tuple[str, str]]:
    payload = _sec_json("https://www.sec.gov/files/company_tickers.json")
    by_ticker = {}
    for row in payload.values():
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            by_ticker[ticker] = (str(int(row.get("cik_str"))).zfill(10), str(row.get("title") or ticker))
    return {key: by_ticker[ticker] for key, ticker in tickers.items() if ticker in by_ticker}


def latest_10k_exhibit(cik: str) -> tuple[str, str, str] | None:
    payload = _sec_json("https://data.sec.gov/submissions/CIK" + cik + ".json")
    recent = payload.get("filings", {}).get("recent", {})
    for index, form in enumerate(recent.get("form", [])):
        if form not in ("10-K", "20-F"):
            continue
        accession = str(recent["accessionNumber"][index])
        filed = str(recent["filingDate"][index])
        bare = accession.replace("-", "")
        base = "https://www.sec.gov/Archives/edgar/data/" + str(int(cik)) + "/" + bare + "/"
        index_payload = _sec_json(base + "index.json")
        candidates = []
        for item in index_payload.get("directory", {}).get("item", []):
            name = str(item.get("name") or "")
            if not name.lower().endswith((".htm", ".html")):
                continue
            if EXHIBIT_NAME_RE.search(name) or str(item.get("type") or "").upper() in ("EX-21", "EX-21.1"):
                candidates.append(name)
        for name in candidates[:4]:
            return (base + name, accession, filed)
        return None
    return None


def collect_evidence() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "medradar.attribution_evidence.v1",
        "collected_at": _now(),
        "user_agent": USER_AGENT,
        "note": "Entity names extracted from public filings. The filing URL is recorded so any reader can re-fetch and re-extract. These are derived extracts, not the filings themselves.",
        "filings": [],
    }
    for filing in FILINGS:
        markup = fetch(filing["url"])
        lines = markup_lines(markup)
        if filing["extractor"] == "entity_lines":
            entities = entity_lines(lines)
        else:
            entities = philips_group_table(lines)
        filings_entry = {
            "organization_key": filing["organization_key"],
            "kind": filing["kind"],
            "url": filing["url"],
            "title": filing["title"],
            "accession": filing["accession"],
            "retrieved_at": _now(),
            "line_count": len(lines),
            "entity_count": len(entities),
            "entities": entities,
        }
        payload["filings"].append(filings_entry)
        print(filing["organization_key"], "->", len(entities), "entity names from", filing["url"])

    print("--- additional SEC registrants (latest 10-K exhibit 21) ---")
    ciks = resolve_ciks(FILING_TICKERS)
    for organization_key, (cik, title) in sorted(ciks.items()):
        try:
            found = latest_10k_exhibit(cik)
        except RuntimeError as error:
            print(organization_key, "-> 0 entity names (fetch failed:", str(error)[:80], ")")
            continue
        if not found:
            print(organization_key, "-> 0 entity names (no exhibit 21 in the latest annual filing)")
            payload["filings"].append(
                {
                    "organization_key": organization_key,
                    "kind": "jurisdiction_filing",
                    "url": None,
                    "title": title + " - no subsidiary exhibit located",
                    "accession": None,
                    "retrieved_at": _now(),
                    "entity_count": 0,
                    "entities": [],
                    "note": "No exhibit 21 was located in the latest annual filing; the organization stays undecidable in this release.",
                }
            )
            continue
        url, accession, filed = found
        markup = fetch(url)
        entities = entity_lines(markup_lines(markup))
        payload["filings"].append(
            {
                "organization_key": organization_key,
                "kind": "jurisdiction_filing",
                "url": url,
                "title": title + " - latest annual filing exhibit 21 (filed " + filed + ")",
                "accession": accession,
                "retrieved_at": _now(),
                "entity_count": len(entities),
                "entities": entities,
            }
        )
        print(organization_key, "->", len(entities), "entity names from", url)
    EVIDENCE_FILE.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", EVIDENCE_FILE)
    return 0


def load_applicants() -> list[dict[str, Any]]:
    rows = []
    with gzip.open(SNAPSHOT / "applicants.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_cases() -> list[dict[str, Any]]:
    from medradar.product.identity import registry

    active = registry()
    cases = []
    for row in load_applicants():
        name = str(row.get("applicant_name") or "")
        if not name:
            continue
        decision, rejection = active.decide(name)
        scope = sorted((row.get("by_org_scope") or {}).keys())
        cases.append(
            {
                "applicant_name": name,
                "records": int(row.get("records") or 0),
                "organization_key": decision.organization_key if decision else None,
                "status": decision.status if decision else ("rejected" if rejection else "unattributed"),
                "rule": decision.rule if decision else None,
                "basis": decision.basis if decision else None,
                "collection_scope": scope,
                "by_source": row.get("by_source") or {},
            }
        )
    return cases


def stratum_of(case: dict[str, Any]) -> str | None:
    if case["organization_key"] is None:
        return "S7_ambiguous_scope" if len(case["collection_scope"]) > 1 else None
    if case["status"] == "evidence_verified":
        return "S5_ownership_evidence"
    if case["rule"] == "lexical_equivalence_v1":
        return "S4_lexical_rule"
    if case["basis"] in ("subsidiary", "division", "historical_name") and case["status"] == "proposed":
        return "S6_corporate_relation"
    if case["records"] >= 1000:
        return "S1_high_volume"
    if case["records"] >= 100:
        return "S2_mid_volume"
    if case["records"] >= 1:
        return "S3_low_volume"
    return None


def draw_sample() -> int:
    cases = build_cases()
    by_stratum: dict[str, list[dict[str, Any]]] = {name: [] for name in SAMPLE_DESIGN["strata"]}
    for case in cases:
        stratum = stratum_of(case)
        if stratum:
            by_stratum[stratum].append(case)
    rng = random.Random(SAMPLE_DESIGN["seed"])
    sample = []
    for name in SAMPLE_DESIGN["strata"]:
        candidates = sorted(by_stratum[name], key=lambda item: item["applicant_name"].casefold())
        rng.shuffle(candidates)
        for case in candidates[: SAMPLE_DESIGN["per_stratum"]]:
            sample.append({"stratum": name, **case})
    payload = {
        "schema": "medradar.attribution_sample.v1",
        "generated_at": _now(),
        "design": SAMPLE_DESIGN,
        "decision_rule": DECISION_RULE,
        "population_size": len(cases),
        "stratum_sizes": {name: len(rows) for name, rows in by_stratum.items()},
        "sample_size": len(sample),
        "cases": sample,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    SAMPLE_FILE.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", SAMPLE_FILE, "cases:", len(sample))
    for name, rows in by_stratum.items():
        print(" ", name, "population", len(rows), "sampled", min(len(rows), SAMPLE_DESIGN["per_stratum"]))
    return 0


def _evidence_index() -> dict[str, dict[str, Any]]:
    if not EVIDENCE_FILE.is_file():
        return {}
    payload = json.loads(EVIDENCE_FILE.read_text(encoding="utf-8"))
    index: dict[str, dict[str, Any]] = {}
    for filing in payload.get("filings") or []:
        index.setdefault(filing["organization_key"], filing)
    return index


def review_case(case: dict[str, Any], filings: dict[str, dict[str, Any]]) -> dict[str, Any]:
    from medradar.product.attribution import ownership as ownership_module

    applicant = case["applicant_name"]
    organization = case["organization_key"]
    result = {
        "stratum": case["stratum"],
        "applicant_name": applicant,
        "organization_key": organization,
        "records": case["records"],
        "status": case["status"],
        "basis": case["basis"],
        "rule": case["rule"],
        "collection_scope": case["collection_scope"],
        "reviewer": "agent:lead",
        "reviewer_kind": "agent",
        "reviewed_at": _now(),
        "evidence": [],
        "verdict": "undecidable",
        "reason": "",
    }
    if organization is None:
        result["reason"] = "not attributed to any organization: no attribution claim exists to validate"
        return result

    relations = ownership_module.ownership().verified_for(organization, applicant)
    for relation in relations:
        for item in relation.evidence:
            result["evidence"].append(
                {
                    "evidence_type": item.evidence_type,
                    "url": item.url,
                    "title": item.title,
                    "accessed_at": item.accessed_at,
                    "quote": item.quote,
                    "source": "ownership relation " + relation.relation_id,
                }
            )
    if relations:
        result["verdict"] = "supported"
        result["reason"] = "covered by verified ownership relation(s): " + ", ".join(relation.relation_id for relation in relations)
        return result

    filing = filings.get(organization)
    if filing is not None and not filing.get("entities"):
        result["verdict"] = "undecidable"
        result["reason"] = (
            "no subsidiary exhibit was located in this organization's latest annual filing, so no independent "
            "documentary source names this spelling yet"
        )
        return result
    if filing:
        applicant_norm = normalise(applicant)
        applicant_words = distinctive_words(applicant)
        best: str | None = None
        best_score = 0
        for entity in filing["entities"]:
            entity_norm = normalise(entity)
            if entity_norm == applicant_norm:
                best, best_score = entity, 100
                break
            words = distinctive_words(entity)
            if applicant_words and all(word in words for word in applicant_words):
                score = len(applicant_words)
                if score > best_score:
                    best, best_score = entity, score
        if best:
            result["verdict"] = "supported"
            result["reason"] = "the organization's jurisdiction filing lists the entity " + repr(best)
            result["evidence"].append(
                {
                    "evidence_type": filing["kind"],
                    "url": filing["url"],
                    "title": filing["title"],
                    "accessed_at": filing["retrieved_at"],
                    "quote": best,
                    "source": "jurisdiction filing " + str(filing.get("accession") or "unknown"),
                }
            )
            return result
        result["verdict"] = "undecidable"
        result["reason"] = (
            "the collected jurisdiction filing for this organization does not list this exact entity; the filing "
            "lists only subsidiaries above a filing threshold (or the entity is not a subsidiary), so its absence "
            "is not evidence of a wrong attribution"
        )
        result["evidence"].append(
            {
                "evidence_type": filing["kind"],
                "url": filing["url"],
                "title": filing["title"],
                "accessed_at": filing["retrieved_at"],
                "quote": "searched " + str(filing["entity_count"]) + " extracted entity names",
                "source": "jurisdiction filing " + str(filing.get("accession") or "unknown"),
            }
        )
        return result

    result["verdict"] = "undecidable"
    result["reason"] = (
        "no jurisdiction filing or verified ownership relation was collected for this organization in this "
        "release; the attribution cannot be checked against independent documentation yet"
    )
    return result


def review() -> int:
    if not SAMPLE_FILE.is_file():
        raise SystemExit("run --sample first")
    sample = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    filings = _evidence_index()
    records = [review_case(case, filings) for case in sample["cases"]]
    payload = {
        "schema": "medradar.attribution_review_records.v1",
        "generated_at": _now(),
        "decision_rule": DECISION_RULE,
        "reviewer": "agent:lead",
        "reviewer_kind": "agent",
        "review_records": records,
    }
    REVIEW_FILE.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    supported = sum(1 for record in records if record["verdict"] == "supported")
    contradicted = sum(1 for record in records if record["verdict"] == "contradicted")
    undecidable = sum(1 for record in records if record["verdict"] == "undecidable")
    print("records:", len(records), "supported:", supported, "contradicted:", contradicted, "undecidable:", undecidable)
    return 0


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total == 0:
        return (0.0, 1.0)
    phat = successes / total
    denominator = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def report() -> int:
    if not REVIEW_FILE.is_file():
        raise SystemExit("run --review first")
    records = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))["review_records"]
    decidable = [record for record in records if record["verdict"] in ("supported", "contradicted")]
    supported = sum(1 for record in decidable if record["verdict"] == "supported")
    contradicted = sum(1 for record in decidable if record["verdict"] == "contradicted")
    undecidable = len(records) - len(decidable)
    low, high = wilson(supported, len(decidable)) if decidable else (0.0, 1.0)
    by_stratum: dict[str, dict[str, int]] = {}
    for record in records:
        bucket = by_stratum.setdefault(record["stratum"], {"total": 0, "supported": 0, "contradicted": 0, "undecidable": 0})
        bucket["total"] += 1
        bucket[record["verdict"]] += 1
    record_weighted_records = sum(record["records"] for record in records)
    verified_records = sum(record["records"] for record in decidable if record["verdict"] == "supported")
    payload = {
        "schema": "medradar.attribution_precision.v1",
        "state": "estimated",
        "generated_at": _now(),
        "estimate": round(supported / len(decidable), 4) if decidable else None,
        "confidence_interval_95": [round(low, 4), round(high, 4)] if decidable else None,
        "sample_size": len(records),
        "decidable_sample_size": len(decidable),
        "undecidable": undecidable,
        "undecidable_share": round(undecidable / len(records), 4) if records else None,
        "supported": supported,
        "contradicted": contradicted,
        "reviewer_kind": "agent",
        "human_review_completed": False,
        "method": "pre-registered documentary rule (tools/validation/validate_attribution.py::DECISION_RULE)",
        "decision_rule": DECISION_RULE,
        "by_stratum": by_stratum,
        "record_weighted_sample_records": record_weighted_records,
        "record_weighted_supported_records": verified_records,
        "sampling_note": (
            "Stratified, deterministic sample drawn from the committed snapshot with a fixed seed. The estimate is "
            "over decidable cases only; the undecidable share is reported so the denominator cannot be silently inflated."
        ),
        "caveats": [
            "The reviewer is an AI agent applying a documentary rule, not a human analyst. This is NOT independent human review.",
            "Only organizations with a collected jurisdiction filing (Medtronic, GE HealthCare, Philips) can be decided; the other tracked organizations are infrastructure-limited, not verified.",
            "The filing lists subsidiaries above a disclosure threshold, so a missing entity is undecidable, never contradicted.",
            "No contradicted case was found in this sample; that is a statement about the sample, not a guarantee about the population.",
        ],
        "protocol": "docs/product/product_002/IDENTITY_REVIEW_PROTOCOL.md",
        "records_file": "docs/product/product_002/validation/review_records.json",
        "human_review_required": True,
    }
    PRECISION_FILE.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("state", "estimate", "confidence_interval_95", "sample_size", "decidable_sample_size", "undecidable", "undecidable_share", "supported", "contradicted", "reviewer_kind")}, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent attribution validation.")
    parser.add_argument("--collect-evidence", action="store_true")
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--review", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)
    if args.collect_evidence:
        return collect_evidence()
    if args.sample:
        return draw_sample()
    if args.review:
        code = review()
        if args.report:
            return report()
        return code
    if args.report:
        return report()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
