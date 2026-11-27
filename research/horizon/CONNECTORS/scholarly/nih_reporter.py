"""NIH RePORTER v2 connector (POST).

The v2 project-search endpoint is POST-only: a GET returns 405, which is
recorded as probe evidence in ``SOURCE_PROBES/scholarly/PROBES.json``
(``nih_reporter_get_405``). The working call is a JSON POST to
``https://api.reporter.nih.gov/v2/projects/search``, made here through
``_util.post_json`` so the call is logged in
``SOURCE_PROBES/scholarly/REQUEST_LOG_POST.jsonl``.

What this connector produces is the *grant side* of the grant<->work relation:
for each NIH core project number that a publication's own funding metadata
declares, the RePORTER project record(s) that carry it. Nothing is linked that
the publication did not itself declare.

    python CONNECTORS/scholarly/nih_reporter.py
    python CONNECTORS/scholarly/nih_reporter.py --parse
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hz.schema import build_record, write_jsonl  # noqa: E402
from hz.timeq import now_utc  # noqa: E402

from CONNECTORS.scholarly import _util as U  # noqa: E402

SOURCE_ID = "nih_reporter"
BASE = "https://api.reporter.nih.gov/v2/projects/search"
INCLUDE_FIELDS = [
    "ProjectNum", "CoreProjectNum", "ProjectTitle", "FiscalYear", "AwardAmount",
    "Organization", "PrincipalInvestigators", "ProjectStartDate", "ProjectEndDate",
    "AgencyIcAdmin", "AgencyIcFundings", "AwardNoticeDate", "ProjectSerialNum",
    "CongDist", "ProjectDetailUrl",
]
BATCH = 25
PAGE_SIZE = 50          # "per-page/rows at most 50"
MAX_PAGES = 6           # hard bound: at most 6 * 50 = 300 rows per core batch
LICENCE_STATUS = "public_domain"
LICENCE_NOTE = (
    "NIH RePORTER is a US federal government database; the data is in the public "
    "domain and free of copyright restrictions in the United States "
    "(https://reporter.nih.gov/faq, 'Is the data copyrighted?' -> No). Recorded as "
    "public_domain."
)

# NIH core project number: activity code (1-3 letters) + institute (2 letters) +
# serial (6 alphanumeric) + optional support year / suffix. Normalisation removes
# only whitespace, hyphens, en/em dashes and non-breaking hyphens that publishers
# insert; nothing is added.
_HYPHENS = "\u2010\u2011\u2012\u2013\u2014\u2212\u00ad"
_NIH_CORE_RE = re.compile(r"^([A-Z]{1,3})(\d{2})([A-Z]{2})(\d{6}|[A-Z0-9]{5,7})$")


def normalise_grant_id(raw: str | None) -> str | None:
    """Space/hyphen-stripped uppercase form of a grant id, or None."""
    if not raw:
        return None
    v = str(raw)
    for h in _HYPHENS:
        v = v.replace(h, "-")
    v = re.sub(r"\s+", "", v).strip("-,").upper()
    return v or None


def nih_core(raw: str | None) -> str | None:
    """Return the NIH core project number (e.g. ``R01EB026995``) or None.

    The rule is deliberately strict: activity code (1-3 letters) + 2-digit
    institute sequence + 2-letter institute code + **exactly six digits**.

    A looser rule (allowing a 5-7 character alphanumeric serial) accepted
    ``JP22fk0210090``, a Japan AMED grant number, as an NIH core. Tightening the
    serial to six digits rejects it while keeping every real NIH number seen in
    the sample (``F32EB030411``, ``R01EB026995``, ``P41EB017183``, ``U01EB029826``,
    ``R01CA212148``, ``R01CA218187``, ``R01CA249893``, ``R01EB009055``,
    ``P41EB015891``). Rejected candidates are logged by the caller.
    """
    v = normalise_grant_id(raw)
    if not v:
        return None
    if re.match(r"^[A-Z]{1,3}\d{2}[A-Z]{2}\d{6}$", v):
        return v
    # support-year-prefixed form, e.g. 5R01EB026995-02 -> 5R01EB02699502
    m = re.match(r"^\d([A-Z]{1,3}\d{2}[A-Z]{2}\d{6})(?:\d{2}|A\d)?$", v)
    return m.group(1) if m else None


def _record_rows(path: str) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def extract_declared_grants() -> list[dict]:
    """Every grant id that an anchor publication's own funding metadata declares.

    Sources of the declaration, all preserved with their exact field path:
    * Europe PMC ``grantsList.grant[].grantId``
    * PubMed ``GrantList.Grant.GrantID``
    * Crossref ``funder[].award[]``
    """
    out: list[dict] = []
    for src in ("europepmc", "pubmed_eutils", "crossref"):
        path = os.path.join(U.DATASETS, src, "records.jsonl")
        if not os.path.isfile(path):
            continue
        for r in _record_rows(path):
            a = r.get("attributes") or {}
            if src == "europepmc":
                for g in a.get("grants") or []:
                    out.append({
                        "declared_by_source": src,
                        "declared_field": "grantsList.grant[].grantId",
                        "grant_id_raw": g.get("grantId"),
                        "agency": g.get("agency"),
                        "work_doi": _doi_of(r),
                        "work_source_record_id": r.get("source_record_id"),
                    })
            elif src == "pubmed_eutils":
                for g in a.get("grant_list") or []:
                    out.append({
                        "declared_by_source": src,
                        "declared_field": "GrantList.Grant.GrantID",
                        "grant_id_raw": g.get("grant_id"),
                        "agency": g.get("agency"),
                        "work_doi": _doi_of(r),
                        "work_source_record_id": r.get("source_record_id"),
                    })
            else:
                for f in a.get("funders") or []:
                    for award in f.get("awards") or []:
                        out.append({
                            "declared_by_source": src,
                            "declared_field": "funder[].award[]",
                            "grant_id_raw": award,
                            "agency": f.get("name"),
                            "funder_doi": f.get("doi"),
                            "work_doi": _doi_of(r),
                            "work_source_record_id": r.get("source_record_id"),
                        })
    for row in out:
        row["grant_id_normalised"] = normalise_grant_id(row["grant_id_raw"])
        row["nih_core"] = nih_core(row["grant_id_raw"])
    return out


def _doi_of(rec: dict) -> str | None:
    for i in rec.get("identifiers") or []:
        if i.get("scheme") == "doi":
            return i.get("value")
    return None


def collect() -> dict:
    declared = extract_declared_grants()
    cores = sorted({d["nih_core"] for d in declared if d["nih_core"]})
    batches = [cores[i:i + BATCH] for i in range(0, len(cores), BATCH)]
    print(f"    declared grant rows: {len(declared)}; distinct NIH core numbers: {len(cores)}")

    raw_records: list[dict] = []
    results: list[dict] = []

    # (a) one bounded discovery search, so the endpoint's device coverage is
    #     demonstrated rather than asserted
    body = {
        "criteria": {"fiscal_years": [2022], "text_search_field": "medical device",
                     "text_search_operators": {"text_search_field": "all"}},
        "include_fields": INCLUDE_FIELDS, "offset": 0, "limit": 10,
    }
    status, payload, headers = U.post_json("nih_reporter discovery: medical device", BASE, body)
    prov = U.save_raw(SOURCE_ID, "discovery_medical_device.json", payload,
                      requested_url=BASE, final_url=BASE, status=status,
                      content_type=headers.get("content-type"),
                      note="bounded discovery search, limit=10")
    raw_records.append(prov)
    disc = json.loads(payload.decode("utf-8")) if 200 <= status < 300 else {}
    results.append({"kind": "discovery", "status": status, "raw": prov["path"],
                    "meta": disc.get("meta"), "results": disc.get("results") or []})
    print(f"    discovery: status={status} total={((disc.get('meta') or {}).get('total'))}")

    # (b) resolve the declared grant numbers, page-bounded
    for bi, batch in enumerate(batches, 1):
        offset = 0
        total = None
        rows: list[dict] = []
        pages: list[dict] = []
        for page in range(MAX_PAGES):
            body = {
                "criteria": {"project_nums": batch},
                "include_fields": INCLUDE_FIELDS,
                "offset": offset, "limit": PAGE_SIZE,
            }
            status, payload, headers = U.post_json(
                f"nih_reporter project_nums batch {bi} page {page + 1}", BASE, body)
            prov = U.save_raw(
                SOURCE_ID, f"project_nums_{bi:02d}_p{page + 1}.json", payload,
                requested_url=BASE, final_url=BASE, status=status,
                content_type=headers.get("content-type"),
                note=(f"declared-core lookup batch {bi}, page {page + 1}, "
                      f"offset {offset}, {len(batch)} cores"),
            )
            prov["cores_requested"] = batch
            raw_records.append(prov)
            doc = json.loads(payload.decode("utf-8")) if 200 <= status < 300 else {}
            meta = doc.get("meta") or {}
            total = meta.get("total", total)
            got = doc.get("results") or []
            rows.extend(got)
            pages.append({"page": page + 1, "offset": offset, "status": status,
                          "returned": len(got), "meta": meta, "raw": prov["path"]})
            offset += PAGE_SIZE
            if len(got) < PAGE_SIZE or (total is not None and offset >= total):
                break
        complete = total is not None and len(rows) >= total
        results.append({"kind": "project_nums", "batch": bi, "status": pages[-1]["status"],
                        "raw": pages[-1]["raw"], "pages": pages,
                        "cores_requested": batch, "meta": pages[-1]["meta"],
                        "total": total, "collected": len(rows),
                        "complete": complete,
                        "PARTIAL_PAGE": not complete,
                        "results": rows})
        print(f"    project_nums batch {bi}: total={total} collected={len(rows)} "
              f"pages={len(pages)} complete={complete}")

    doc = {
        "source_id": SOURCE_ID, "generated_at": now_utc(), "endpoint": BASE,
        "method": "POST", "include_fields": INCLUDE_FIELDS,
        "batch_size": BATCH, "page_size": PAGE_SIZE, "max_pages": MAX_PAGES,
        "raw_files": raw_records,
        "declared_grant_rows": declared,
        "declared_nih_cores": cores,
        "rejected_candidates": [
            {"grant_id_raw": d["grant_id_raw"], "normalised": d["grant_id_normalised"]}
            for d in declared
            if d["grant_id_normalised"] and not d["nih_core"]
        ],
        "results": results,
    }
    U.write_json(os.path.join(U.DATASETS, SOURCE_ID, "REPORTER_INDEX.json"), doc)
    return doc


def parse(index: dict | None = None) -> list:
    idx = index or U.read_json(os.path.join(U.DATASETS, SOURCE_ID, "REPORTER_INDEX.json"))
    fetched_at = now_utc()
    recs = []
    seen: set[str] = set()
    for block in idx["results"]:
        if block["kind"] != "project_nums":
            continue
        partial = bool(block.get("PARTIAL_PAGE"))
        for p in block["results"]:
            core = p.get("core_project_num") or p.get("project_num")
            # RePORTER returns one row per award notice and project_num alone is
            # NOT unique; appl_id is. Dedupe on appl_id, falling back to the
            # project/year pair only when appl_id is absent.
            key = str(p.get("appl_id") or f"{p.get('project_num')}|{p.get('fiscal_year')}")
            if key in seen:
                continue
            seen.add(key)
            identifiers = []
            if core:
                identifiers.append({"scheme": "nih_core_project_num", "value": core,
                                    "issuing_authority": "NIH", "is_primary": True})
            if p.get("project_num"):
                identifiers.append({"scheme": "nih_project_num", "value": p["project_num"]})
            if p.get("appl_id"):
                identifiers.append({"scheme": "nih_appl_id", "value": str(p["appl_id"])})
            ic = p.get("agency_ic_admin") or {}
            org = p.get("organization") or {}
            pis = p.get("principal_investigators") or []
            flags = []
            if partial:
                flags.append("PARTIAL_PAGE")
            if not p.get("project_start_date"):
                flags.append("MISSING_FILING_DATE")
            else:
                from datetime import date
                try:
                    if date.fromisoformat(str(p["project_start_date"])[:10]) < date(2008, 1, 1):
                        flags.append("RETROSPECTIVE_FIELD")
                except ValueError:
                    pass
            recs.append(build_record(
                source_id=SOURCE_ID,
                source_record_id=str(p.get("appl_id") or p.get("project_num")),
                entity_type="grant",
                original_name=U.norm_ws(p.get("project_title")) or str(p.get("project_num")),
                identifiers=identifiers,
                manufacturer=None,
                attributes={
                    "project_num": p.get("project_num"),
                    "core_project_num": p.get("core_project_num"),
                    "project_title": p.get("project_title"),
                    "fiscal_year": p.get("fiscal_year"),
                    "award_amount": p.get("award_amount"),
                    "award_notice_date": p.get("award_notice_date"),
                    "project_start_date": p.get("project_start_date"),
                    "project_end_date": p.get("project_end_date"),
                    "agency_ic_admin": ic,
                    "agency_ic_fundings": p.get("agency_ic_fundings"),
                    "organization": {
                        "org_name": org.get("org_name"), "org_city": org.get("org_city"),
                        "org_state": org.get("org_state"), "org_country": org.get("org_country"),
                        "org_ueis": org.get("org_ueis"),
                    },
                    "principal_investigators": [
                        {"full_name": x.get("full_name"), "profile_id": x.get("profile_id")}
                        for x in pis
                    ],
                    "project_detail_url": p.get("project_detail_url"),
                },
                event_at=U.iso_date_or_none(p.get("project_start_date")),
                source_public_at=U.iso_date_or_none(p.get("award_notice_date")),
                first_observed_at=None,
                fetched_at=fetched_at,
                source_url=f"https://reporter.nih.gov/project-details/{p.get('appl_id')}"
                if p.get("appl_id") else BASE,
                licence_status=LICENCE_STATUS,
                licence_note=LICENCE_NOTE,
                identity_status="UNKNOWN",
                evidence_status="CANDIDATE",
                quality_flags=flags,
                notes=(
                    "event_at = project start date (when the award began). "
                    "source_public_at = award notice date (when RePORTER made the "
                    "award visible). These are different clocks on purpose."
                ),
            ))
    return recs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parse", action="store_true")
    args = ap.parse_args(argv)
    idx_path = os.path.join(U.DATASETS, SOURCE_ID, "REPORTER_INDEX.json")
    idx = U.read_json(idx_path) if args.parse else collect()
    out = os.path.join(U.DATASETS, SOURCE_ID, "records.jsonl")
    n = write_jsonl(out, parse(idx))
    print(f"  {n} records -> {U.rel(out)}")
    U.write_provenance(
        SOURCE_ID, idx.get("raw_files") or [],
        extra={
            "endpoint": BASE, "method": "POST",
            "get_outcome": "405 Method Not Allowed (recorded in PROBES.json)",
            "licence_status": LICENCE_STATUS, "licence_note": LICENCE_NOTE,
            "records_file": U.rel(out), "record_count": n,
            "index_file": U.rel(idx_path),
            "post_call_log": U.rel(U.POST_LOG),
            "declared_nih_cores": idx.get("declared_nih_cores"),
            "declared_grant_row_count": len(idx.get("declared_grant_rows") or []),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
