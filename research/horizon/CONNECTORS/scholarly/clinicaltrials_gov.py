"""ClinicalTrials.gov API v2 connector.

Keyless, verified. Two jobs:

1. **Trial records** — bounded sponsor-scoped searches for the five target firms,
   parsed into ``horizon.evidence.v1`` ``clinical_trial`` records with the status
   module's four posting dates kept separate from the study dates.
2. **Trial -> publication linkage inputs** — the raw ``referencesModule``
   reference list (``pmid``, ``type``, ``citation``) is preserved verbatim so that
   ``link_trials.py`` can build ``RELATIONS_TRIAL_PAPER.jsonl`` from a literal
   field rather than from topic similarity.

    python CONNECTORS/scholarly/clinicaltrials_gov.py
    python CONNECTORS/scholarly/clinicaltrials_gov.py --parse
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hz.schema import build_record, write_jsonl  # noqa: E402
from hz.timeq import now_utc  # noqa: E402

from CONNECTORS.scholarly import _util as U  # noqa: E402

SOURCE_ID = "clinicaltrials_gov"
BASE = "https://clinicaltrials.gov/api/v2/studies"
PAGE_SIZE = 50          # "per-page/rows at most 50"
LICENCE_STATUS = "public_domain"
LICENCE_NOTE = (
    "ClinicalTrials.gov terms state that the data is available for public use and "
    "is not subject to copyright restrictions in the United States "
    "(https://clinicaltrials.gov/about-site/terms-conditions). Recorded as "
    "public_domain."
)

# sponsor search strings; the query.spons parameter does substring matching
FIRM_QUERIES = ["Medtronic", "GE HealthCare", "Philips", "Draeger", "Mindray"]


def collect() -> dict:
    studies: list[dict] = []
    raw_records: list[dict] = []
    queries: list[dict] = []
    with U.make_client(
        "scholarly_ctgov", max_requests=len(FIRM_QUERIES) + 3,
        max_bytes_per_response=8_000_000, max_total_bytes=20_000_000, rps=1.2,
    ) as client:
        for qi, firm in enumerate(FIRM_QUERIES, 1):
            url = BASE + "?" + urllib.parse.urlencode({
                "query.spons": firm, "pageSize": PAGE_SIZE, "countTotal": "true",
            })
            res = client.get(url)
            prov = U.save_fetch(
                SOURCE_ID, f"studies_spons_{qi:02d}.json", res,
                note=f"EXP-H2 trial collection: query.spons={firm}, pageSize={PAGE_SIZE}",
            )
            prov["firm_query"] = firm
            raw_records.append(prov)
            got: list[dict] = []
            total = None
            next_token = None
            if res.ok:
                try:
                    d = res.json()
                    got = d.get("studies") or []
                    total = d.get("totalCount")
                    next_token = d.get("nextPageToken")
                except Exception:
                    pass
            for st in got:
                st["_firm_query"] = firm
            studies.extend(got)
            queries.append({
                "firm_query": firm, "status": res.status, "raw": prov["path"],
                "returned": len(got), "totalCount": total,
                "has_more_pages": bool(next_token),
                "page_bounded_note": (
                    f"one page of {PAGE_SIZE} only; totalCount is the server's count for "
                    "the whole query and is NOT the number we collected"),
            })
            print(f"    ctgov spons={firm}: status={res.status} returned={len(got)} "
                  f"totalCount={total}")
        budget = client.budget_report()
    doc = {
        "source_id": SOURCE_ID, "generated_at": now_utc(), "endpoint": BASE,
        "page_size": PAGE_SIZE, "firm_queries": FIRM_QUERIES,
        "queries": queries, "study_count": len(studies),
        "budget": budget, "raw_files": raw_records, "studies": studies,
    }
    U.write_json(os.path.join(U.DATASETS, SOURCE_ID, "CTGOV_INDEX.json"), doc)
    print("  budget:", budget)
    print(f"  {len(studies)} study records")
    return doc


def parse(index: dict | None = None) -> list:
    idx = index or U.read_json(os.path.join(U.DATASETS, SOURCE_ID, "CTGOV_INDEX.json"))
    fetched_at = now_utc()
    recs = []
    for st in idx["studies"]:
        p = st.get("protocolSection") or {}
        ident = p.get("identificationModule") or {}
        nct = ident.get("nctId")
        if not nct:
            continue
        status = p.get("statusModule") or {}
        sponsor = p.get("sponsorCollaboratorsModule") or {}
        design = p.get("designModule") or {}
        arms = p.get("armsInterventionsModule") or {}
        refs = ((p.get("referencesModule") or {}).get("references")) or []
        ids = [{"scheme": "nct", "value": nct,
                "issuing_authority": "ClinicalTrials.gov", "is_primary": True}]
        for s in ident.get("secondaryIdInfo") or []:
            if s.get("id"):
                ids.append({"scheme": f"secondary:{s.get('type','other')}",
                            "value": str(s["id"])})
        lead = sponsor.get("leadSponsor") or {}
        start_raw = (status.get("startDateStruct") or {}).get("date")
        post_raw = (status.get("studyFirstPostDateStruct") or {}).get("date")
        flags = []
        if not U.iso_date_or_none(post_raw):
            flags.append("MISSING_PUBLICATION_DATE")
        if not U.iso_date_or_none(start_raw):
            flags.append("MISSING_FILING_DATE")
        recs.append(build_record(
            source_id=SOURCE_ID,
            source_record_id=nct,
            entity_type="clinical_trial",
            original_name=U.norm_ws(ident.get("briefTitle")) or nct,
            identifiers=ids,
            manufacturer=lead.get("name") if lead.get("class") == "INDUSTRY" else None,
            attributes={
                "brief_title": ident.get("briefTitle"),
                "official_title": ident.get("officialTitle"),
                "org_study_id": (ident.get("orgStudyIdInfo") or {}).get("id"),
                "organization": (ident.get("organization") or {}).get("fullName"),
                "secondary_ids": ident.get("secondaryIdInfo"),
                "lead_sponsor": lead,
                "collaborators": sponsor.get("collaborators"),
                "overall_status": status.get("overallStatus"),
                "study_type": design.get("studyType"),
                "phases": design.get("phases"),
                "enrollment": design.get("enrollmentInfo"),
                "interventions": [
                    {"type": x.get("type"), "name": x.get("name")}
                    for x in (arms.get("interventions") or [])
                ],
                "conditions": (p.get("conditionsModule") or {}).get("conditions"),
                "dates": {
                    "start_date": (status.get("startDateStruct") or {}).get("date"),
                    "primary_completion_date": (
                        status.get("primaryCompletionDateStruct") or {}).get("date"),
                    "completion_date": (status.get("completionDateStruct") or {}).get("date"),
                    "study_first_submit_date": status.get("studyFirstSubmitDate"),
                    "study_first_submit_qc_date": status.get("studyFirstSubmitQcDate"),
                    "study_first_post_date": (
                        status.get("studyFirstPostDateStruct") or {}).get("date"),
                    "last_update_submit_date": status.get("lastUpdateSubmitDate"),
                    "last_update_post_date": (
                        status.get("lastUpdatePostDateStruct") or {}).get("date"),
                    "status_verified_date": status.get("statusVerifiedDate"),
                },
                "references": refs,
                "reference_count": len(refs),
                "reference_pmids": sorted({str(r["pmid"]) for r in refs if r.get("pmid")}),
                "has_results": st.get("hasResults"),
                "firm_query": st.get("_firm_query"),
                "derived_misc": (st.get("derivedSection") or {}).get("miscInfoModule"),
                "date_precision": {
                    "start_date": U.date_precision(start_raw),
                    "study_first_post_date": U.date_precision(post_raw),
                },
            },
            event_at=U.iso_date_or_none(start_raw),
            source_public_at=U.iso_date_or_none(post_raw),
            first_observed_at=None,
            fetched_at=fetched_at,
            source_url=f"https://clinicaltrials.gov/study/{nct}",
            licence_status=LICENCE_STATUS,
            licence_note=LICENCE_NOTE,
            identity_status=(
                "CANDIDATE" if lead.get("class") == "INDUSTRY" else "UNKNOWN"
            ),
            evidence_status="CANDIDATE",
            quality_flags=flags,
            notes=(
                "event_at is the trial start date; source_public_at is the first-post "
                "date. sponsor_class=INDUSTRY is what raises identity_status to "
                "CANDIDATE, not a name match."
            ),
        ))
    return recs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parse", action="store_true")
    args = ap.parse_args(argv)
    idx_path = os.path.join(U.DATASETS, SOURCE_ID, "CTGOV_INDEX.json")
    idx = U.read_json(idx_path) if args.parse else collect()
    out = os.path.join(U.DATASETS, SOURCE_ID, "records.jsonl")
    n = write_jsonl(out, parse(idx))
    print(f"  {n} records -> {U.rel(out)}")
    U.write_provenance(
        SOURCE_ID, idx["raw_files"],
        extra={
            "endpoint": BASE, "method": "GET", "page_size": idx.get("page_size"),
            "queries": idx.get("queries"),
            "licence_status": LICENCE_STATUS, "licence_note": LICENCE_NOTE,
            "records_file": U.rel(out), "record_count": n,
            "index_file": U.rel(idx_path),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
