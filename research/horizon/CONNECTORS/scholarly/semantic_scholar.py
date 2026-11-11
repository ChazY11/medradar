"""Semantic Scholar connector.

The Graph API's batch lookup is POST-only, so it is called through
``_util.post_json`` which records the call in
``SOURCE_PROBES/scholarly/REQUEST_LOG_POST.jsonl`` exactly as the GET client
records its own calls.

    python CONNECTORS/scholarly/semantic_scholar.py
    python CONNECTORS/scholarly/semantic_scholar.py --parse
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

SOURCE_ID = "semantic_scholar"
BASE = "https://api.semanticscholar.org/graph/v1/paper/batch"
FIELDS = "title,externalIds,publicationDate,venue,year,authors,publicationTypes,journal"
BATCH = 100   # documented cap is 500 ids; we stay far below it
LICENCE_STATUS = "open_no_explicit_licence"
LICENCE_NOTE = (
    "The Semantic Scholar Graph API is free for research use and the Semantic "
    "Scholar Open Research Corpus is released under ODC-BY, but the API terms "
    "(https://www.semanticscholar.org/product/api/license) restrict bulk "
    "redistribution and require attribution. Recorded as "
    "open_no_explicit_licence rather than open_licence because the API-level "
    "terms, not a content licence, govern reuse of these responses."
)


def collect() -> dict:
    dois = U.anchor_dois()
    # The batch route takes the field projection as a QUERY parameter, not in the
    # JSON body. Sending the body alone returns only {paperId, title} with HTTP
    # 200 -- a silent partial response, not an error.
    url = BASE + "?" + urllib.parse.urlencode({"fields": FIELDS})
    results: list[dict] = []
    raw_records: list[dict] = []
    for bi in range(0, len(dois), BATCH):
        chunk = dois[bi:bi + BATCH]
        body = {"ids": [f"DOI:{d}" for d in chunk]}
        status, payload, headers = U.post_json(
            f"EXP-H1 semanticscholar batch {bi // BATCH + 1}", url, body
        )
        prov = U.save_raw(
            SOURCE_ID, f"batch_{bi // BATCH + 1:02d}.json", payload,
            requested_url=url, final_url=url, status=status,
            content_type=headers.get("content-type"),
            note=(f"EXP-H1 S2 batch lookup, {len(chunk)} DOIs, "
                  f"fields passed as query parameter"),
        )
        prov["dois_requested"] = chunk
        raw_records.append(prov)
        hits = []
        if 200 <= status < 300:
            try:
                hits = json.loads(payload.decode("utf-8"))
            except Exception:
                hits = []
        results.append({"status": status, "raw": prov["path"],
                        "dois_requested": chunk,
                        "returned": len(hits) if isinstance(hits, list) else 0,
                        "results": hits if isinstance(hits, list) else []})
        found = sum(1 for h in hits if h) if isinstance(hits, list) else 0
        with_date = sum(1 for h in hits
                        if isinstance(h, dict) and h.get("publicationDate")) \
            if isinstance(hits, list) else 0
        print(f"    semanticscholar batch {bi // BATCH + 1}: status={status} "
              f"returned={len(hits) if isinstance(hits, list) else 0} found={found} "
              f"with_publicationDate={with_date}")
    doc = {
        "source_id": SOURCE_ID, "generated_at": now_utc(), "endpoint": BASE,
        "method": "POST", "fields": FIELDS, "fields_param_location": "query string",
        "batch_size": BATCH,
        "anchor_count": len(dois), "raw_files": raw_records, "batches": results,
    }
    U.write_json(os.path.join(U.DATASETS, SOURCE_ID, "S2_INDEX.json"), doc)
    return doc


def parse(index: dict | None = None) -> list:
    idx = index or U.read_json(os.path.join(U.DATASETS, SOURCE_ID, "S2_INDEX.json"))
    fetched_at = now_utc()
    recs = []
    for b in idx["batches"]:
        requested = b["dois_requested"]
        # the batch API returns a positional array aligned with the request,
        # with null for unresolvable ids
        for pos, hit in enumerate(b["results"]):
            if not hit:
                continue
            doi = U.norm_doi((hit.get("externalIds") or {}).get("DOI")) or (
                requested[pos] if pos < len(requested) else None)
            ext = hit.get("externalIds") or {}
            identifiers = []
            if doi:
                identifiers.append({"scheme": "doi", "value": doi, "is_primary": True})
            if ext.get("PubMed"):
                identifiers.append({"scheme": "pmid", "value": str(ext["PubMed"])})
            if ext.get("PubMedCentral"):
                identifiers.append({"scheme": "pmcid", "value": f"PMC{ext['PubMedCentral']}"})
            if ext.get("ArXiv"):
                identifiers.append({"scheme": "arxiv", "value": ext["ArXiv"]})
            if ext.get("MAG"):
                identifiers.append({"scheme": "mag", "value": str(ext["MAG"])})
            if ext.get("CorpusId"):
                identifiers.append({"scheme": "s2_corpus_id", "value": str(ext["CorpusId"])})
            flags = []
            if not hit.get("publicationDate"):
                flags.append("MISSING_PUBLICATION_DATE")
            if not identifiers:
                flags.append("MISSING_IDENTIFIER")
            flags.append("SNAPSHOT_ONLY")   # S2 exposes no record-creation timestamp
            authors = hit.get("authors") or []
            recs.append(build_record(
                source_id=SOURCE_ID,
                source_record_id=hit.get("paperId") or (doi or ""),
                entity_type="publication",
                original_name=U.norm_ws(hit.get("title")) or (doi or ""),
                identifiers=identifiers,
                attributes={
                    "title": hit.get("title"),
                    "venue": hit.get("venue"),
                    "year": hit.get("year"),
                    "journal": hit.get("journal"),
                    "publicationTypes": hit.get("publicationTypes"),
                    "author_count": len(authors),
                    "first_author_family": (
                        str((authors[0] or {}).get("name") or "").split()[-1]
                        if authors else None
                    ),
                    "last_author_family": (
                        str((authors[-1] or {}).get("name") or "").split()[-1]
                        if authors else None
                    ),
                    "externalIds": ext,
                    "dates": {"publicationDate": hit.get("publicationDate")},
                },
                event_at=hit.get("publicationDate"),
                source_public_at=hit.get("publicationDate"),
                first_observed_at=None,
                fetched_at=fetched_at,
                source_url=(
                    f"https://www.semanticscholar.org/paper/{hit.get('paperId')}"
                    if hit.get("paperId") else BASE
                ),
                licence_status=LICENCE_STATUS,
                licence_note=LICENCE_NOTE,
                identity_status="UNKNOWN",
                evidence_status="CANDIDATE",
                quality_flags=flags,
                notes=(
                    "No record-creation or last-update timestamp is exposed by the "
                    "Graph API, so this source can only ever supply a current-snapshot "
                    "date. That is itself an EXP-H3 measurement."
                ),
            ))
    return recs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parse", action="store_true")
    args = ap.parse_args(argv)
    idx_path = os.path.join(U.DATASETS, SOURCE_ID, "S2_INDEX.json")
    idx = U.read_json(idx_path) if args.parse else collect()
    out = os.path.join(U.DATASETS, SOURCE_ID, "records.jsonl")
    n = write_jsonl(out, parse(idx))
    print(f"  {n} records -> {U.rel(out)}")
    U.write_provenance(
        SOURCE_ID, idx["raw_files"],
        extra={
            "endpoint": BASE, "method": "POST", "fields": idx.get("fields"),
            "licence_status": LICENCE_STATUS, "licence_note": LICENCE_NOTE,
            "records_file": U.rel(out), "record_count": n,
            "index_file": U.rel(idx_path),
            "post_call_log": U.rel(U.POST_LOG),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
