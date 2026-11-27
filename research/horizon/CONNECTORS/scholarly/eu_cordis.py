"""EU CORDIS connector — partial, with the blocker recorded rather than papered over.

What was actually established (see ``SOURCE_PROBES/scholarly/PROBES.json``):

* ``/api/``, ``/api/v1/projects``, ``/api/v1/search``, ``/api/search`` all return
  the 404 single-page-application HTML shell: there is **no published CORDIS
  JSON API contract** at the documented-looking paths.
* ``https://cordis.europa.eu/api/search/results?q=contenttype='project' AND
  <text>&num=N`` does return JSON with ``payload.total`` and
  ``payload.results[]``, including ``rcn``, ``reference``, ``acronym``,
  ``programme[]``, ``startDate``, ``endDate``. That is an **undocumented**
  endpoint, so the licence posture is ``open_no_explicit_licence``.
* ``contenttype='publication'`` fails with
  ``index_not_found_exception: no such index [publication]``. CORDIS keeps
  project / result / article indices but **no publication index**.

Consequence, stated plainly: CORDIS cannot supply an EU grant->publication link,
because it does not carry publications. ``RELATIONS_GRANT_WORK.jsonl`` therefore
contains no EU-CORDIS-derived rows, and that absence is a measured negative, not
an omission.

    python CONNECTORS/scholarly/eu_cordis.py
    python CONNECTORS/scholarly/eu_cordis.py --parse
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hz.schema import build_record, write_jsonl  # noqa: E402
from hz.timeq import now_utc  # noqa: E402

from CONNECTORS.scholarly import _util as U  # noqa: E402

SOURCE_ID = "eu_cordis"
BASE = "https://cordis.europa.eu/api/search/results"
LICENCE_STATUS = "open_no_explicit_licence"
LICENCE_NOTE = (
    "CORDIS content is published by the European Commission; the site legal notice "
    "permits reuse of Commission documents with attribution "
    "(https://commission.europa.eu/legal-notice_en) but the ``/api/search/results`` "
    "endpoint used here is UNDOCUMENTED -- no published API contract, no stated "
    "machine-interface licence. Recorded as open_no_explicit_licence, not "
    "open_licence."
)

QUERIES = [
    ("medical device", "broad European project coverage for the device domain"),
    ("pacemaker", "implantable-device sub-domain"),
    ("ventilator", "another device sub-domain, to check the query works generally"),
    ("Horizon 2020 medical device", "programme-scoped variant"),
]


def _search_url(q: str, num: int) -> str:
    full = f"contenttype='project' AND {q}"
    return BASE + "?" + urllib.parse.urlencode({"q": full, "num": num})


def collect() -> dict:
    raw_records: list[dict] = []
    queries: list[dict] = []
    projects: list[dict] = []
    with U.make_client(
        "scholarly_cordis", max_requests=len(QUERIES) + 3,
        max_bytes_per_response=2_000_000, max_total_bytes=8_000_000, rps=1.0,
    ) as client:
        for qi, (q, why) in enumerate(QUERIES, 1):
            url = _search_url(q, 20)
            res = client.get(url)
            prov = U.save_fetch(SOURCE_ID, f"search_{qi:02d}.json", res,
                                note=f"CORDIS project search q={q!r} ({why})")
            prov["query"] = q
            raw_records.append(prov)
            payload = {}
            if res.ok:
                try:
                    payload = (res.json() or {}).get("payload") or {}
                except Exception:
                    payload = {}
            got = payload.get("results") or []
            for p in got:
                p["_query"] = q
            projects.extend(got)
            queries.append({
                "query": q, "why": why, "status": res.status,
                "raw": prov["path"], "total": payload.get("total"),
                "returned": len(got),
            })
            print(f"    cordis q={q!r}: status={res.status} "
                  f"total={payload.get('total')} returned={len(got)}")
        budget = client.budget_report()
    doc = {
        "source_id": SOURCE_ID, "generated_at": now_utc(), "endpoint": BASE,
        "documented": False, "budget": budget, "raw_files": raw_records,
        "queries": queries, "project_count": len(projects), "projects": projects,
        "blockers": [
            "no publication index: contenttype='publication' -> HTTP 500 "
            "index_not_found_exception: no such index [publication]",
            "no published API contract: /api/, /api/v1/projects, /api/v1/search, "
            "/api/search all return the 404 SPA HTML shell",
            "therefore EU grant -> publication linkage is NOT buildable from CORDIS",
        ],
    }
    U.write_json(os.path.join(U.DATASETS, SOURCE_ID, "CORDIS_INDEX.json"), doc)
    print("  budget:", budget)
    return doc


def parse(index: dict | None = None) -> list:
    idx = index or U.read_json(os.path.join(U.DATASETS, SOURCE_ID, "CORDIS_INDEX.json"))
    fetched_at = now_utc()
    recs = []
    seen: set[str] = set()
    for p in idx["projects"]:
        rcn = p.get("rcn") or p.get("id") or p.get("reference")
        if not rcn or str(rcn) in seen:
            continue
        seen.add(str(rcn))
        identifiers = [{"scheme": "cordis_rcn", "value": str(rcn),
                        "issuing_authority": "European Commission", "is_primary": True}]
        if p.get("reference"):
            identifiers.append({"scheme": "cordis_grant_agreement_id",
                                "value": str(p["reference"])})
        prog = p.get("programme") or []
        flags = ["SNAPSHOT_ONLY"]   # CORDIS exposes lastUpdateDate only, no creation date
        flags.append("PARSED_FROM_HTML") if False else None
        recs.append(build_record(
            source_id=SOURCE_ID,
            source_record_id=str(rcn),
            entity_type="grant",
            original_name=U.norm_ws(p.get("title")) or str(rcn),
            identifiers=identifiers,
            manufacturer=None,
            attributes={
                "rcn": str(rcn),
                "reference": p.get("reference"),
                "acronym": p.get("acronym"),
                "title": p.get("title"),
                "teaser": p.get("teaser"),
                "programme": prog,
                "coordinated_in": p.get("coordinatedIn"),
                "start_date_raw": p.get("startDate"),
                "end_date_raw": p.get("endDate"),
                "last_update_date_raw": p.get("lastUpdateDate"),
                "content_type": p.get("contentType"),
                "query": p.get("_query"),
                "date_fields_note": (
                    "startDate/endDate/lastUpdateDate arrive as human strings such as "
                    "'1 {{month_08}} 2014'; the month name is a CORDIS template token, "
                    "so no ISO date is invented and event_at/source_public_at stay None."
                ),
            },
            event_at=None,
            source_public_at=None,
            first_observed_at=None,
            fetched_at=fetched_at,
            source_url=f"https://cordis.europa.eu/project/id/{rcn}",
            licence_status=LICENCE_STATUS,
            licence_note=LICENCE_NOTE,
            identity_status="UNKNOWN",
            evidence_status="CANDIDATE",
            quality_flags=flags,
            notes=(
                "CORDIS date strings are unauthored template tokens and are NOT "
                "converted to ISO dates. This connector therefore contributes "
                "project identity but no usable clocks."
            ),
        ))
    return recs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parse", action="store_true")
    args = ap.parse_args(argv)
    idx_path = os.path.join(U.DATASETS, SOURCE_ID, "CORDIS_INDEX.json")
    idx = U.read_json(idx_path) if args.parse else collect()
    out = os.path.join(U.DATASETS, SOURCE_ID, "records.jsonl")
    n = write_jsonl(out, parse(idx))
    print(f"  {n} records -> {U.rel(out)}")
    U.write_provenance(
        SOURCE_ID, idx["raw_files"],
        extra={
            "endpoint": BASE, "method": "GET", "documented": False,
            "licence_status": LICENCE_STATUS, "licence_note": LICENCE_NOTE,
            "records_file": U.rel(out), "record_count": n,
            "index_file": U.rel(idx_path),
            "blockers": idx.get("blockers"),
            "access_state": "OPEN (undocumented endpoint)",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
