"""S-029 step 06 — institution extraction and ROR resolution (RQ3).

Institutions are the second half of every relation in this study. Unlike companies,
they have no curated register inside this project, so identity has to be established
against the Research Organization Registry (ROR), which assigns a persistent id to
research organisations and publishes their names, aliases, acronyms and country.

What is measured, not assumed
-----------------------------
1. **Extraction is a real error source.** Affiliations are free text; one string can
   name thirty organisations (observed: a single hypertension paper lists ~30
   institutions with initials). The extractor splits on structural separators and
   keeps the raw span so every extracted candidate is traceable, and the report
   counts how many strings were multi-organisation.
2. **Matching is a decision, not a lookup.** ROR's search is fuzzy: "Mayo Clinic"
   returns 441 results. A candidate is only `EXACT` if the normalised name equals a
   ROR display name/alias/acronym; token-overlap matches are `FUZZY` and remain
   `CANDIDATE` claims; everything else is `UNMAPPED`. The chosen ROR id, the field
   it matched on and the runner-up are all stored.
3. **Who does not resolve is as important as who does.** The unmapped list is the
   main recall limit for cross-source linkage and is reported per source family.

Run:  python research/studies/relation_network_s029/code/s029_06_institutions.py
Writes: data/institution_candidates.jsonl, data/institutions.jsonl,
        data/ror_cache.json, artifacts/ror_resolution.json
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s029_common import (ARTIFACT_DIR, DATA_DIR, ProvenanceHTTP, HttpFailure, norm_name,
                         read_json, read_jsonl, utcnow_iso, write_json, write_jsonl)

ROR_API = "https://api.ror.org/organizations"
CACHE_PATH = DATA_DIR / "ror_cache.json.gz"  # committed gzipped: it is a cache, not evidence

ORG_KW = re.compile(
    r"univers|hospital|clinic|institut|college|school|centre|center|foundation|academy|"
    r"akademi|laborator|klinik|krankenhaus|trust|faculty|fakult|department|ministry|"
    r"council|agency|health system|medical center|medical centre|nhs|va medical|"
    r"national|federal|office|bureau|board|society|association|cooperative|"
    r"gesundheit|krebs|charite|charité|hôpital|hopital|ospedale|ospedal|"
    r"universidad|universidade|università|universita|szpital|szpit|bolnica|"
    r"medical school|school of medicine|research institute|science center", re.I)
DEPT_PREFIX = re.compile(
    r"^(dept\.?|department|division|unit|section|institute of|institut für|klinik für|"
    r"course of|faculty of|school of|centre for|center for|group of|programme|program)\b", re.I)
MULTI_SPLIT = re.compile(r"[;]")
LOCATION_TAIL = re.compile(
    r",\s*(?:[A-Z]{2}\s+\d{5}(?:-\d{4})?|\d{4,6}\s+[A-Za-z]|[A-Z][a-z]+,\s*[A-Z][a-z]+|"
    r"\d[\d\s]{2,}[A-Za-z]?)\s*$")


def split_affiliation_organisations(aff: str) -> list[str]:
    """Return the organisation-bearing segments of one affiliation string."""
    if not aff:
        return []
    out: list[str] = []
    # Semicolon-separated organisations; within each, the organisation is usually the
    # head of the string before the city/postcode, or the segment carrying an org keyword.
    for chunk in MULTI_SPLIT.split(aff):
        c = chunk.strip().strip(".")
        if not c:
            continue
        parts = [p.strip() for p in c.split(",") if p.strip()]
        if not parts:
            continue
        # drop a leading department/division phrase
        while parts and DEPT_PREFIX.match(parts[0]):
            parts = parts[1:]
        if not parts:
            continue
        # candidate: the first 1-2 parts, stopping before a pure location part
        cand_parts = [parts[0]]
        if len(parts) > 1 and ORG_KW.search(parts[0] + " " + parts[1]) and \
                not re.fullmatch(r"[A-Z]{2}|\d{4,6}", parts[1]):
            cand_parts.append(parts[1])
        cand = ", ".join(cand_parts)
        cand = re.sub(r"\([A-Z.\s&]{2,12}\)", "", cand).strip(" ,.")
        if not cand or len(cand) < 4:
            continue
        if not ORG_KW.search(cand) and not ORG_KW.search(c):
            # keep it only when the whole chunk is short (likely a bare organisation name)
            if len(c) > 90:
                continue
            cand = c.split(",")[0].strip()
        out.append(cand[:220])
    # de-duplicate while preserving order
    seen = set()
    uniq = []
    for c in out:
        k = norm_name(c)
        if k and k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq


def ror_lookup(client: ProvenanceHTTP, query: str, cache: dict) -> dict:
    key = norm_name(query)
    if key in cache:
        return cache[key]
    params = {"query": query}
    try:
        body, rec = client.get(ROR_API, params=params, note=f"ror:{query[:60]}")
        payload = json.loads(body)
        items = payload.get("items") or []
        result = {"query": query, "retrieved_at": rec.retrieved_at, "n_results": len(items),
                  "candidates": [{"ror_id": it.get("id"),
                                  "names": [n.get("value") for n in (it.get("names") or [])],
                                  "name_types": [[t for t in n.get("types") or []]
                                                 for n in (it.get("names") or [])],
                                  "country": ((it.get("locations") or [{}])[0]
                                              .get("geonames_details") or {}).get("country_code"),
                                  "types": it.get("types"),
                                  "external_ids": it.get("external_ids")}
                                 for it in items[:8]]}
    except HttpFailure as exc:
        result = {"query": query, "retrieved_at": utcnow_iso(), "error": str(exc),
                  "candidates": []}
    cache[key] = result
    return result


def score_match(query: str, result: dict) -> dict:
    """Deterministic match classification against ROR candidates."""
    nq = norm_name(query)
    if not nq or not result.get("candidates"):
        return {"status": "UNMAPPED", "confidence": 0.0, "ror_id": None,
                "matched_name": None, "matched_field": None, "reason": "no ROR candidates"}
    best = None
    for cand in result["candidates"]:
        for nm, types in zip(cand["names"], cand["name_types"]):
            nn = norm_name(nm)
            if not nn:
                continue
            if nn == nq:
                field = "ror_display" if "ror_display" in (types or []) else \
                    ("alias" if "alias" in (types or []) else
                     ("acronym" if "acronym" in (types or []) else "label"))
                return {"status": "EXACT", "confidence": 1.0 if field == "ror_display" else 0.92,
                        "ror_id": cand["ror_id"], "matched_name": nm,
                        "matched_field": field, "country": cand["country"],
                        "reason": "normalised equality with a ROR name"}
            # token containment: all query tokens present in candidate name or vice versa
            tq, tc = set(nq.split()), set(nn.split())
            if tq and tc:
                jac = len(tq & tc) / len(tq | tc)
                if jac >= 0.55:
                    score = {"status": "FUZZY", "confidence": round(min(0.5 + jac / 2, 0.85), 3),
                             "ror_id": cand["ror_id"], "matched_name": nm,
                             "matched_field": "token_overlap", "country": cand["country"],
                             "jaccard": round(jac, 3),
                             "reason": f"token overlap jaccard={jac:.2f}"}
                    if best is None or score["confidence"] > best["confidence"]:
                        best = score
    if best:
        return best
    return {"status": "UNMAPPED", "confidence": 0.0, "ror_id": None, "matched_name": None,
            "matched_field": None, "reason": "no candidate passed the equality/overlap rule",
            "n_candidates_considered": result.get("n_results")}


def load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        with gzip.open(CACHE_PATH, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_cache(cache: dict) -> None:
    tmp = CACHE_PATH.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as fh:
        json.dump(cache, fh, ensure_ascii=False, sort_keys=True)
    tmp.replace(CACHE_PATH)


def main() -> None:
    mentions = list(read_jsonl(DATA_DIR / "company_mentions.jsonl"))
    trials = list(read_jsonl(DATA_DIR / "ctgov_trials.jsonl"))
    sites = list(read_jsonl(DATA_DIR / "ctgov_sites.jsonl"))
    pubs = list(read_jsonl(DATA_DIR / "epmc_pubs.jsonl"))

    company_strings = {m["raw_string"] for m in mentions if m.get("company_key")}
    accepted_company_pubs = {m["record_id"] for m in mentions
                             if m["record_kind"] == "publication"
                             and m["mapping_status"] in ("ORG_TEXT", "ORG_EMAIL")}

    candidates: dict[tuple[str, str], dict] = {}

    def add_candidate(text: str, family: str, context: str, record_id: str) -> None:
        t = (text or "").strip()
        if not t or len(t) < 3:
            return
        if t in company_strings:
            return
        key = (family, norm_name(t))
        if key in candidates:
            candidates[key]["occurrences"] += 1
            if len(candidates[key]["example_records"]) < 3:
                candidates[key]["example_records"].append(record_id)
            return
        candidates[key] = {"candidate_id": f"icand:{family}:{abs(hash(key)) % 10**10}",
                           "raw_string": t, "family": family, "context": context,
                           "occurrences": 1, "example_records": [record_id]}

    # family 1: trial organisation fields (sponsor / collaborator)
    for t in trials:
        for role, raw in [("lead_sponsor", t["lead_sponsor"]["name"])] + \
                [("collaborator", c["name"]) for c in t["collaborators"]]:
            if raw:
                add_candidate(raw, "trial_organisation", role, t["nct_id"])
    # family 2: trial sites
    for s in sites:
        if s["facility"]:
            add_candidate(s["facility"], "trial_site_facility", "site_facility", s["nct_id"])
    # family 3: publication affiliations (only papers with an accepted company mention,
    # i.e. the papers that can carry a co-affiliation claim)
    multi_org_strings = 0
    affiliation_strings = 0
    for p in pubs:
        if p["pub_key"] not in accepted_company_pubs:
            continue
        for au in p["authors"]:
            for aff in au["affiliations"]:
                affiliation_strings += 1
                orgs = split_affiliation_organisations(aff)
                if len(orgs) > 1:
                    multi_org_strings += 1
                for org in orgs:
                    add_candidate(org, "publication_affiliation", "author_affiliation",
                                  p["pub_key"])

    cand_list = sorted(candidates.values(), key=lambda c: (-c["occurrences"], c["raw_string"]))
    write_jsonl(DATA_DIR / "institution_candidates.jsonl", cand_list)
    print(f"unique institution candidates: {len(cand_list)}")
    print("by family:", dict(Counter(c["family"] for c in cand_list)))

    client = ProvenanceHTTP("ror", delay_s=0.25, timeout=45)
    cache = load_cache()

    institutions = []
    stats = defaultdict(Counter)
    first_attempt = defaultdict(Counter)

    def alt_spans(raw: str) -> list[str]:
        """Alternative organisation spans inside one messy affiliation string.

        Department-first strings ("Medical Imaging Centre, Uppsala University Hospital")
        fail a whole-string ROR lookup; the institution is a sub-span. Trying the
        comma/semicolon segments is the smallest honest fix, and the before/after rates
        are both reported so the parser's contribution is visible.
        """
        out = []
        for sep in (";", ","):
            parts = [x.strip(" .;,") for x in raw.split(sep)]
            for part in parts:
                if len(part) > 6 and part != raw and part not in out:
                    out.append(part)
            for i in range(len(parts) - 1):
                combo = f"{parts[i]}, {parts[i + 1]}"
                if len(combo) > 8 and combo != raw and combo not in out:
                    out.append(combo)
        return out[:6]

    for i, c in enumerate(cand_list):
        res = ror_lookup(client, c["raw_string"], cache)
        m = score_match(c["raw_string"], res)
        first_attempt[c["family"]][m["status"]] += 1
        attempts = [{"query": c["raw_string"], "status": m["status"],
                     "ror_id": m.get("ror_id")}]
        if m["status"] == "UNMAPPED":
            best = m
            for alt in alt_spans(c["raw_string"]):
                ares = ror_lookup(client, alt, cache)
                am = score_match(alt, ares)
                attempts.append({"query": alt, "status": am["status"], "ror_id": am.get("ror_id")})
                if am["status"] == "EXACT":
                    best = am
                    break
                if am["status"] == "FUZZY" and best["status"] != "FUZZY":
                    best = am
            if best["status"] != "UNMAPPED":
                best = dict(best)
                best["recovered_by"] = "alternative_organisation_span"
            m = best
        stats[c["family"]][m["status"]] += 1
        institutions.append({**c, "ror": m, "resolution_attempts": attempts,
                             "resolved_at": utcnow_iso()})
        if (i + 1) % 150 == 0:
            print(f"  resolved {i + 1}/{len(cand_list)}  ror_calls={client.calls}", flush=True)
            save_cache(cache)

    save_cache(cache)
    institutions.sort(key=lambda r: r["candidate_id"])
    write_jsonl(DATA_DIR / "institutions.jsonl", institutions)

    report = {
        "generated_at": utcnow_iso(),
        "ror_api": ROR_API,
        "n_candidates": len(cand_list),
        "by_family": dict(Counter(c["family"] for c in cand_list)),
        "match_status_by_family": {k: dict(v) for k, v in stats.items()},
        "first_attempt_status_by_family": {k: dict(v) for k, v in first_attempt.items()},
        "recovered_by_alternative_span": sum(
            1 for r in institutions
            if (r.get("ror") or {}).get("recovered_by") == "alternative_organisation_span"),
        "match_status_overall": dict(Counter(r["ror"]["status"] for r in institutions)),
        "multi_organisation_affiliation_strings": multi_org_strings,
        "affiliation_strings_scanned": affiliation_strings,
        "n_ror_http_calls": client.calls,
        "cache_entries": len(cache),
        "notes": [
            "Only publications with at least one accepted company affiliation were scanned for "
            "institutions, because only those papers can produce a co-affiliation claim. The "
            "denominator is therefore stated, not the whole literature.",
            "EXACT = normalised equality with a ROR display name or alias; FUZZY = token overlap "
            ">= 0.55 and stays a CANDIDATE claim; UNMAPPED = no acceptable candidate.",
        ],
    }
    write_json(ARTIFACT_DIR / "ror_resolution.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main()
