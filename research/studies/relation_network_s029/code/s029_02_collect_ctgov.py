"""S-029 step 02 — ClinicalTrials.gov v2 collection for the five pilot companies.

What is collected and why
-------------------------
ClinicalTrials.gov is the only source in this study where a *company* appears in a
structured, role-bearing field of a registered study. That makes Relation A
(company -> clinical trial) observable rather than inferred. But the registry is
evidence of *registration*, not of research collaboration:

* ``leadSponsor``   = the organisation that registered and takes responsibility
                      for the study  -> a registrable sponsorship relation;
* ``collaborator``  = an organisation the sponsor names as participating
                      -> a relation asserted by the sponsor, weaker than lead;
* ``locations``     = where participants are enrolled -> a *site* relation, which
                      is NOT evidence of an R&D partnership with the sponsor.

These three are collected as three different relation roles and are never merged.

Search semantics that bound recall (measured, not assumed)
----------------------------------------------------------
The API searches the sponsor/collaborator *name string*, token-wise. A study
registered under a name the search does not reach is invisible to us, and its
absence must never be reported as evidence that the relation does not exist. The
probe in step 01 already showed the canonical spelling of one company returns 2
records while the ASCII spelling returns 8. This script therefore queries a
declared list of variants and records, per record, which queries reached it.

Time fields (never substituted for one another)
-----------------------------------------------
``StartDate``            -> event_at      (when the study began)
``StudyFirstPostDate``   -> published_at  (when the registration became public)
``LastUpdatePostDate``   -> source_updated_at
``PrimaryCompletionDate``-> event_at (completion)
The struct ``type`` (ACTUAL / ESTIMATED) is preserved: an ESTIMATED start date is
not a fact about the past. ``first_seen_at`` is added at collection time and is
the real wall clock of this run.

Run:  python research/studies/relation_network_s029/code/s029_02_collect_ctgov.py
Writes: data/raw/ctgov_*.json.gz, artifacts/ctgov_manifest.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s029_common import (ARTIFACT_DIR, RAW_DIR, ProvenanceHTTP, HttpFailure, save_raw_envelope,
                         utcnow_iso, write_json)

API = "https://clinicaltrials.gov/api/v2/studies"
PAGE_SIZE = 200
MAX_RECORDS_PER_QUERY = 3000  # explicit ceiling; any stop is recorded in the envelope

# Fields verified individually against the live API (invalid names return HTTP 400).
FIELDS = ",".join([
    "NCTId", "BriefTitle", "OfficialTitle", "Acronym", "OrgStudyId", "SecondaryId",
    "OverallStatus", "StartDate", "PrimaryCompletionDate", "CompletionDate",
    "StudyFirstPostDate", "LastUpdatePostDate", "ResultsFirstPostDate",
    "StudyFirstSubmitDate", "LastUpdateSubmitDate", "StatusVerifiedDate",
    "LeadSponsorName", "LeadSponsorClass", "CollaboratorName", "CollaboratorClass",
    "ResponsiblePartyType", "ResponsiblePartyInvestigatorAffiliation",
    "Condition", "ConditionMeshTerm", "InterventionName", "InterventionType",
    "DesignPrimaryPurpose", "Phase", "EnrollmentCount", "StudyType", "HasResults",
    "ReferencePMID", "ReferenceType", "ReferenceCitation",
])

# Query set per company.  The first string is the canonical search label; the rest
# are variant/former/subsidiary strings whose reach we measure.  No identity claim
# is encoded here (see ENTITY_HISTORY_REGISTER.md for verified corporate history).
QUERIES: dict[str, list[str]] = {
    "medtronic": ["Medtronic", "Medtronic Sofamor Danek", "Medtronic Vascular",
                  "Medtronic MiniMed", "MiniMed", "Covidien", "Tyco Healthcare"],
    "ge_healthcare": ["GE HealthCare", "GE Medical Systems", "General Electric",
                      "GE Healthcare Technologies"],
    "philips": ["Philips", "Koninklijke Philips", "Philips Healthcare",
                "Philips Medical Systems", "Philips Respironics", "Respironics"],
    "draeger": ["Dräger", "Draeger", "Draegerwerk", "Drägerwerk", "Dräger Medical"],
    "mindray": ["Mindray", "Shenzhen Mindray", "Mindray Medical", "Datascope", "Zonare"],
}

LOCATION_FIELDS = ",".join([
    "NCTId", "LocationFacility", "LocationCity", "LocationState", "LocationZip",
    "LocationCountry",
])


def slug(s: str) -> str:
    keep = [c.lower() if c.isalnum() else "_" for c in s]
    out = "".join(keep)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")


def collect_query(client: ProvenanceHTTP, company: str, variant: str) -> dict:
    """Fetch every page for one query, returning a raw envelope (no truncation)."""
    pages: list[dict] = []
    records: list[dict] = []
    page_token = None
    total = None
    stop_reason = "exhausted"
    while True:
        params = {"query.spons": variant, "pageSize": PAGE_SIZE, "fields": FIELDS,
                  "format": "json"}
        if page_token:
            params["pageToken"] = page_token
        try:
            body, rec = client.get(API, params=params,
                                   note=f"ctgov:{company}:{variant}:page{len(pages) + 1}")
        except HttpFailure as exc:
            stop_reason = f"http_failure: {exc}"
            break
        payload = json.loads(body)
        total = payload.get("totalCount", total)
        studies = payload.get("studies") or []
        pages.append({"retrieved_at": rec.retrieved_at, "status": rec.status,
                      "url": rec.url, "body_sha256": rec.body_sha256,
                      "n_studies": len(studies),
                      "next_page_token": payload.get("nextPageToken")})
        records.extend(studies)
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
        if len(records) >= MAX_RECORDS_PER_QUERY:
            stop_reason = f"page_ceiling:{MAX_RECORDS_PER_QUERY}"
            break
    envelope = {
        "source": "clinicaltrials_gov_api_v2",
        "api_url": API,
        "query_parameter": "query.spons",
        "query_value": variant,
        "company_key": company,
        "total_count_reported": total,
        "pages": pages,
        "n_records": len(records),
        "stop_reason": stop_reason,
        "collected_at": utcnow_iso(),
        "fields": FIELDS,
        "records": records,
    }
    stem = f"ctgov_{company}_{slug(variant)}"
    save_raw_envelope(stem, envelope)
    return {"variant": variant, "n_records": len(records),
            "total_count_reported": total, "pages": len(pages),
            "stop_reason": stop_reason, "raw_file": f"data/raw/{stem}.json.gz",
            "retrieved_at": pages[0]["retrieved_at"] if pages else None}


def collect_locations(client: ProvenanceHTTP, nct_ids: list[str], company: str) -> dict:
    """Second pass: site facilities for a bounded sample of studies."""
    out: list[dict] = []
    failures: list[dict] = []
    for i, nct in enumerate(nct_ids):
        url = f"{API}/{nct}"
        try:
            body, rec = client.get(url, params={"fields": LOCATION_FIELDS, "format": "json"},
                                   note=f"ctgov-locations:{nct}")
            out.append({"nct_id": nct, "retrieved_at": rec.retrieved_at,
                        "url": rec.url, "payload_sha256": rec.body_sha256,
                        "payload": json.loads(body)})
        except HttpFailure as exc:
            failures.append({"nct_id": nct, "error": str(exc)})
        if i and i % 50 == 0:
            print(f"    locations {i}/{len(nct_ids)}", flush=True)
    stem = f"ctgov_locations_{company}"
    save_raw_envelope(stem, {
        "source": "clinicaltrials_gov_api_v2",
        "fields": LOCATION_FIELDS,
        "collected_at": utcnow_iso(),
        "records": out,
        "failures": failures,
    })
    return {"company": company, "n_requested": len(nct_ids), "n_records": len(out),
            "n_failures": len(failures), "raw_file": f"data/raw/{stem}.json.gz"}


def main() -> None:
    client = ProvenanceHTTP("clinicaltrials_gov", delay_s=0.35)
    manifest: dict = {"source": "clinicaltrials_gov_api_v2", "collected_at": utcnow_iso(),
                      "fields": FIELDS, "queries": []}
    per_company_records: dict[str, list[dict]] = {}

    for company, variants in QUERIES.items():
        per_company_records[company] = []
        for variant in variants:
            info = collect_query(client, company, variant)
            manifest["queries"].append(info)
            print(f"[ctgov] {company:14s} {variant:28s} records={info['n_records']:5d} "
                  f"reported_total={info['total_count_reported']} stop={info['stop_reason']}",
                  flush=True)

    # De-duplicate by NCT id for the location sub-sample, stratifying by company.
    for company, variants in QUERIES.items():
        seen: dict[str, dict] = {}
        for variant in variants:
            path = RAW_DIR / f"ctgov_{company}_{slug(variant)}.json.gz"
            if not path.exists():
                continue
            from s029_common import load_raw_envelope
            env = load_raw_envelope(path)
            for rec in env["records"]:
                p = rec.get("protocolSection", {})
                nct = p.get("identificationModule", {}).get("nctId")
                if nct and nct not in seen:
                    seen[nct] = rec
        per_company_records[company] = list(seen.values())

    # Location sub-sample: up to 60 studies per company, spread over study-first-post years.
    LOC_PER_COMPANY = 60
    loc_manifest = []
    for company, recs in per_company_records.items():
        by_year: dict[str, list[str]] = {}
        for rec in recs:
            nct = rec["protocolSection"]["identificationModule"]["nctId"]
            date = (rec["protocolSection"].get("statusModule", {})
                    .get("studyFirstPostDateStruct", {}).get("date") or "unknown")
            year = date[:4]
            by_year.setdefault(year, []).append(nct)
        picked: list[str] = []
        years = sorted(by_year)
        i = 0
        while len(picked) < LOC_PER_COMPANY and years:
            y = years[i % len(years)]
            bucket = by_year[y]
            if bucket:
                picked.append(bucket.pop(0))
            i += 1
            if i > 10000:
                break
        info = collect_locations(client, picked, company)
        loc_manifest.append(info)
        print(f"[ctgov] locations {company}: {info['n_records']} studies", flush=True)

    manifest["location_subsample"] = loc_manifest
    manifest["n_http_calls"] = client.calls
    manifest["dedup_counts"] = {c: len(r) for c, r in per_company_records.items()}
    write_json(ARTIFACT_DIR / "ctgov_manifest.json", manifest)
    print(f"\nwrote {ARTIFACT_DIR / 'ctgov_manifest.json'}  http_calls={client.calls}")


if __name__ == "__main__":
    main()
