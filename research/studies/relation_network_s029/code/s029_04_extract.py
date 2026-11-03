"""S-029 step 04 — extract source-stated facts from raw payloads.

This step performs **no identity resolution**. It converts the committed raw
retrievals into flat, auditable tables of what each source record literally says,
with the string preserved exactly as returned. Every row carries the evidence id
(sha256 of the payload it came from) and the exact JSON location of the statement,
so that a reviewer can walk from a claim back to the bytes.

Outputs (all JSONL, sorted, re-runnable):
  data/ctgov_trials.jsonl  one row per unique NCT id, with every role-bearing string
  data/ctgov_sites.jsonl   one row per (NCT id, facility) from the location sub-sample
  data/epmc_pubs.jsonl     one row per publication record, with per-author affiliations

Run:  python research/studies/relation_network_s029/code/s029_04_extract.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s029_common import (ARTIFACT_DIR, DATA_DIR, RAW_DIR, load_raw_envelope, sha256_text,
                         utcnow_iso, write_json, write_jsonl)

EXTRACTION_VERSION = "s029-1.0.0"


# ---------------------------------------------------------------------------
# ClinicalTrials.gov
# ---------------------------------------------------------------------------

def _struct(module: dict, key: str) -> dict:
    s = module.get(key) or {}
    return {"date": s.get("date"), "type": s.get("type")}


def extract_ctgov() -> tuple[list[dict], list[dict], dict]:
    trials: dict[str, dict] = {}
    stats = {"raw_files": 0, "records_seen": 0, "unique_trials": 0,
             "records_without_nct": 0, "by_company": {}}

    for path in sorted(RAW_DIR.glob("ctgov_*.json.gz")):
        if "locations" in path.name:
            continue
        env = load_raw_envelope(path)
        if env.get("source") != "clinicaltrials_gov_api_v2":
            continue
        stats["raw_files"] += 1
        company = env["company_key"]
        query_value = env["query_value"]
        stats["by_company"].setdefault(company, {"queries": 0, "records": 0})
        stats["by_company"][company]["queries"] += 1
        # Evidence id: hash of the raw file bytes' content identity. The gzip file
        # is deterministic given the envelope, so hashing the envelope text is a
        # stable content address.
        evidence_id = "ev:" + sha256_text(json.dumps(env, ensure_ascii=False, sort_keys=True))
        fp = env.get("fetch_query_provenance") or env.get("hit_query_provenance") or {}
        first_seen_at = fp.get("retrieved_at") or env.get("collected_at")
        source_url = fp.get("url")
        page_times = [p.get("retrieved_at") for p in (env.get("pages") or [])
                      if p.get("retrieved_at")]
        first_seen_at = max(page_times) if page_times else env.get("collected_at")
        source_url = (env.get("pages") or [{}])[0].get("url")
        for rec in env.get("records") or []:
            stats["records_seen"] += 1
            stats["by_company"][company]["records"] += 1
            p = rec.get("protocolSection") or {}
            ident = p.get("identificationModule") or {}
            nct = ident.get("nctId")
            if not nct:
                stats["records_without_nct"] += 1
                continue
            if nct in trials:
                trials[nct]["discovered_by"].append(
                    {"company_key": company, "query_value": query_value,
                     "evidence_id": evidence_id})
                continue
            status = p.get("statusModule") or {}
            sponsor = p.get("sponsorCollaboratorsModule") or {}
            oversight = p.get("oversightModule") or {}
            design = p.get("designModule") or {}
            conditions = p.get("conditionsModule") or {}
            arms = p.get("armsInterventionsModule") or {}
            refs = p.get("referencesModule") or {}

            lead = sponsor.get("leadSponsor") or {}
            collaborators = [{"name": c.get("name"), "class": c.get("class")}
                             for c in (sponsor.get("collaborators") or [])]
            rp = sponsor.get("responsibleParty") or {}
            interventions = [{"name": i.get("name"), "type": i.get("type"),
                              "other_names": i.get("otherNames")}
                             for i in (arms.get("interventions") or [])]
            references = [{"pmid": r.get("pmid"), "type": r.get("type"),
                           "citation": r.get("citation")}
                          for r in (refs.get("references") or [])]
            trials[nct] = {
                "nct_id": nct,
                "brief_title": ident.get("briefTitle"),
                "official_title": ident.get("officialTitle"),
                "acronym": ident.get("acronym"),
                "org_study_id": ident.get("orgStudyId"),
                "secondary_ids": ident.get("secondaryIdInfos"),
                "overall_status": status.get("overallStatus"),
                "start_date": _struct(status, "startDateStruct"),
                "primary_completion_date": _struct(status, "primaryCompletionDateStruct"),
                "completion_date": _struct(status, "completionDateStruct"),
                "study_first_post_date": _struct(status, "studyFirstPostDateStruct"),
                "last_update_post_date": _struct(status, "lastUpdatePostDateStruct"),
                "results_first_post_date": _struct(status, "resultsFirstPostDateStruct"),
                "study_first_submit_date": status.get("studyFirstSubmitDate"),
                "last_update_submit_date": status.get("lastUpdateSubmitDate"),
                "status_verified_date": status.get("statusVerifiedDate"),
                "lead_sponsor": {"name": lead.get("name"), "class": lead.get("class")},
                "collaborators": collaborators,
                "responsible_party": {"type": rp.get("type"),
                                      "investigator_affiliation": rp.get("investigatorAffiliation"),
                                      "investigator_full_name": rp.get("investigatorFullName")},
                "has_dmc": oversight.get("oversightHasDmc"),
                "is_fda_regulated_device": oversight.get("isFdaRegulatedDevice"),
                "study_type": design.get("studyType"),
                "phases": design.get("phases"),
                "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
                "primary_purpose": (design.get("designInfo") or {}).get("primaryPurpose"),
                "conditions": conditions.get("conditions"),
                "condition_mesh_terms": conditions.get("conditionMeshTerms"),
                "interventions": interventions,
                "references": references,
                "discovered_by": [{"company_key": company, "query_value": query_value,
                                   "evidence_id": evidence_id}],
                "evidence_id": evidence_id,
                "source_url": source_url,
                "first_seen_at": first_seen_at,
                "raw_file": path.name,
                "extracted_at": utcnow_iso(),
                "extraction_version": EXTRACTION_VERSION,
            }

    # Location sub-sample
    sites: list[dict] = []
    for path in sorted(RAW_DIR.glob("ctgov_locations_*.json.gz")):
        env = load_raw_envelope(path)
        evidence_id = "ev:" + sha256_text(json.dumps(env, ensure_ascii=False, sort_keys=True))
        fp = env.get("fetch_query_provenance") or env.get("hit_query_provenance") or {}
        first_seen_at = fp.get("retrieved_at") or env.get("collected_at")
        source_url = fp.get("url")
        company = path.stem.replace("ctgov_locations_", "")
        for rec in env.get("records") or []:
            nct = rec.get("nct_id")
            payload = rec.get("payload") or {}
            locations = ((payload.get("protocolSection") or {})
                         .get("contactsLocationsModule") or {}).get("locations") or []
            for loc in locations:
                sites.append({
                    "nct_id": nct,
                    "facility": loc.get("facility"),
                    "city": loc.get("city"),
                    "state": loc.get("state"),
                    "zip": loc.get("zip"),
                    "country": loc.get("country"),
                    "site_status": loc.get("status"),
                    "sampled_for_company": company,
                    "evidence_id": evidence_id,
                    "raw_file": path.name,
                    "payload_sha256": rec.get("payload_sha256"),
                    "extracted_at": utcnow_iso(),
                    "extraction_version": EXTRACTION_VERSION,
                })

    stats["unique_trials"] = len(trials)
    stats["site_rows"] = len(sites)
    return sorted(trials.values(), key=lambda r: r["nct_id"]), sites, stats


# ---------------------------------------------------------------------------
# Europe PMC
# ---------------------------------------------------------------------------

def extract_epmc() -> tuple[list[dict], dict]:
    pubs: dict[str, dict] = {}
    stats = {"raw_files": 0, "records_seen": 0, "unique_publications": 0,
             "records_without_id": 0, "by_company": {}, "by_source_db": {}}

    def pub_key(r: dict) -> str | None:
        doi = (r.get("doi") or "").lower().strip()
        pmid = r.get("pmid")
        if doi:
            return "doi:" + doi
        if pmid:
            return "pmid:" + str(pmid)
        ident = r.get("id")
        return f"{r.get('source')}:{ident}" if ident else None

    for path in sorted(RAW_DIR.glob("epmc_*.json.gz")):
        env = load_raw_envelope(path)
        if env.get("source") != "europepmc":
            continue
        stats["raw_files"] += 1
        company = env["company_key"]
        fam = env.get("query_family")
        label = env.get("variant") if fam == "name_variant" else f"year:{env.get('year')}"
        evidence_id = "ev:" + sha256_text(json.dumps(env, ensure_ascii=False, sort_keys=True))
        fp = env.get("fetch_query_provenance") or env.get("hit_query_provenance") or {}
        first_seen_at = fp.get("retrieved_at") or env.get("collected_at")
        source_url = fp.get("url")
        stats["by_company"].setdefault(company, {"queries": 0, "records": 0})
        stats["by_company"][company]["queries"] += 1
        for r in env.get("records") or []:
            stats["records_seen"] += 1
            stats["by_company"][company]["records"] += 1
            key = pub_key(r)
            if not key:
                stats["records_without_id"] += 1
                continue
            src_db = r.get("source") or "UNKNOWN"
            stats["by_source_db"][src_db] = stats["by_source_db"].get(src_db, 0) + 1
            if key in pubs:
                pubs[key]["discovered_by"].append(
                    {"company_key": company, "query_family": fam, "label": label,
                     "evidence_id": evidence_id})
                continue
            ji = r.get("journalInfo") or {}
            journal = ((ji.get("journal") or {}).get("title"))
            authors = []
            for a in ((r.get("authorList") or {}).get("author") or []):
                affs = []
                for det in ((a.get("authorAffiliationDetailsList") or {})
                            .get("authorAffiliation") or []):
                    if det.get("affiliation"):
                        affs.append(det["affiliation"])
                if not affs and a.get("affiliation"):
                    affs.append(a["affiliation"])
                authors.append({
                    "full_name": a.get("fullName"),
                    "first_name": a.get("firstName"),
                    "last_name": a.get("lastName"),
                    "initials": a.get("initials"),
                    "affiliations": affs,
                })
            grants = []
            for g in ((r.get("grantsList") or {}).get("grant") or []):
                grants.append({"grant_id": g.get("grantId"), "agency": g.get("agency"),
                               "funder": g.get("funder")})
            mesh = []
            for m in ((r.get("meshHeadingList") or {}).get("meshHeading") or []):
                mesh.append({"descriptor": m.get("descriptorName"),
                             "ui": m.get("descriptorName") and m.get("ui") or m.get("ui")})
            pubs[key] = {
                "pub_key": key,
                "source_db": src_db,
                "source_id": r.get("id"),
                "pmid": r.get("pmid"),
                "pmcid": r.get("pmcid"),
                "doi": r.get("doi"),
                "title": r.get("title"),
                "author_string": r.get("authorString"),
                "journal": journal,
                "pub_year": r.get("pubYear"),
                "first_publication_date": r.get("firstPublicationDate"),
                "first_index_date": r.get("firstIndexDate"),
                "electronic_publication_date": r.get("electronicPublicationDate"),
                "date_of_creation": r.get("dateOfCreation"),
                "date_of_revision": r.get("dateOfRevision"),
                "pub_types": [t for t in (r.get("pubTypeList") or {}).get("pubType") or []
                              if isinstance(t, str)],
                "is_open_access": r.get("isOpenAccess"),
                "author_count": len(authors),
                "authors_with_affiliation": sum(1 for a in authors if a["affiliations"]),
                "authors": authors,
                "grants": grants,
                "mesh_terms": mesh,
                "discovered_by": [{"company_key": company, "query_family": fam,
                                   "label": label, "evidence_id": evidence_id}],
                "evidence_id": evidence_id,
                "source_url": source_url,
                "first_seen_at": first_seen_at,
                "raw_file": path.name,
                "extracted_at": utcnow_iso(),
                "extraction_version": EXTRACTION_VERSION,
            }

    stats["unique_publications"] = len(pubs)
    return sorted(pubs.values(), key=lambda r: r["pub_key"]), stats


def main() -> None:
    trials, sites, ctg_stats = extract_ctgov()
    pubs, epmc_stats = extract_epmc()

    n1 = write_jsonl(DATA_DIR / "ctgov_trials.jsonl", trials)
    n2 = write_jsonl(DATA_DIR / "ctgov_sites.jsonl", sites)
    n3 = write_jsonl(DATA_DIR / "epmc_pubs.jsonl", pubs)

    report = {
        "generated_at": utcnow_iso(),
        "extraction_version": EXTRACTION_VERSION,
        "ctgov": ctg_stats,
        "ctgov_rows": {"trials": n1, "sites": n2},
        "europepmc": epmc_stats,
        "epmc_rows": n3,
    }
    write_json(ARTIFACT_DIR / "extract_report.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
