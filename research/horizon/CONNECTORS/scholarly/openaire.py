"""OpenAIRE Graph connector.

One bounded ``/researchProducts?pid={bare DOI}`` lookup per anchor. The bare-DOI
form is the only one that resolves: ``pid=doi:10.x`` and ``pid=doi|10.x`` both
return ``numFound=0`` (recorded as a probe).

    python CONNECTORS/scholarly/openaire.py
    python CONNECTORS/scholarly/openaire.py --parse
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

SOURCE_ID = "openaire"
BASE = "https://api.openaire.eu/graph/v1/researchProducts"
LICENCE_STATUS = "open_licence"
LICENCE_NOTE = (
    "The OpenAIRE Graph is published as open data. OpenAIRE states the graph dump "
    "is available under CC-BY 4.0 and the Graph API is free to query "
    "(https://graph.openaire.eu/docs/ ; https://www.openaire.eu/privacy-policy). "
    "Per-record `bestAccessRight` and `instances[].license` are preserved, because "
    "the *publication* rights differ from the *metadata* rights."
)


def collect() -> dict:
    dois = U.anchor_dois()
    out: list[dict] = []
    raw_records: list[dict] = []
    with U.make_client(
        "scholarly_openaire", max_requests=len(dois) + 3,
        max_bytes_per_response=2_000_000, max_total_bytes=24_000_000, rps=1.5,
    ) as client:
        for i, doi in enumerate(dois, 1):
            url = BASE + "?" + urllib.parse.urlencode({"pid": doi, "pageSize": 5})
            try:
                res = client.get(url)
            except Exception as exc:
                out.append({"doi": doi, "status": None,
                            "error": f"{type(exc).__name__}: {exc}"[:200],
                            "raw": None, "results": []})
                continue
            prov = U.save_fetch(SOURCE_ID, f"pid_{i:02d}.json", res,
                                note=f"EXP-H1 OpenAIRE pid lookup doi={doi}")
            prov["doi"] = doi
            raw_records.append(prov)
            hits = []
            num_found = None
            if res.ok:
                try:
                    d = res.json()
                    num_found = (d.get("header") or {}).get("numFound")
                    hits = d.get("results") or []
                except Exception:
                    pass
            out.append({"doi": doi, "status": res.status, "raw": prov["path"],
                        "numFound": num_found, "results": hits})
            if i % 15 == 0:
                print(f"    openaire {i}/{len(dois)}")
        budget = client.budget_report()
    doc = {
        "source_id": SOURCE_ID, "generated_at": now_utc(), "endpoint": BASE,
        "anchor_count": len(dois),
        "found": sum(1 for r in out if r.get("results")),
        "absent": sum(1 for r in out if r.get("numFound") == 0),
        "errors": sum(1 for r in out if r.get("status") not in (200,)),
        "budget": budget, "raw_files": raw_records, "results": out,
    }
    U.write_json(os.path.join(U.DATASETS, SOURCE_ID, "OPENAIRE_INDEX.json"), doc)
    print("  budget:", budget)
    print(f"  found={doc['found']} absent={doc['absent']} errors={doc['errors']}")
    return doc


def _pids(obj) -> list[dict]:
    out = []
    for p in (obj or []):
        if isinstance(p, dict):
            out.append({"scheme": p.get("scheme"), "value": p.get("value")})
    return out


def parse(index: dict | None = None) -> list:
    idx = index or U.read_json(os.path.join(U.DATASETS, SOURCE_ID, "OPENAIRE_INDEX.json"))
    fetched_at = now_utc()
    recs = []
    for r in idx["results"]:
        queried = U.norm_doi(r.get("doi"))
        for hit in (r.get("results") or []):
            # OpenAIRE's deduplicated research products can carry SEVERAL DOIs:
            # the record's own `pids` plus its `originalIds` (e.g. a preprint DOI
            # alongside the version-of-record DOI). Taking "the first DOI in the
            # list" therefore mis-assigns the work. The *queried* DOI is placed
            # first and marked primary; every other DOI stays in the record as an
            # additional identifier and in `doi_values_all`.
            all_dois: list[tuple[str, str]] = []          # (doi, where)
            for p in _pids(hit.get("pids")):
                if (p.get("scheme") or "").lower() == "doi" and p.get("value"):
                    all_dois.append((U.norm_doi(p["value"]), "pids"))
            for p in _pids(hit.get("originalIds")):
                if (p.get("scheme") or "").lower() == "doi" and p.get("value"):
                    all_dois.append((U.norm_doi(p["value"]), "originalIds"))
            queried_present = any(d == queried for d, _ in all_dois)
            ordered: list[tuple[str, str]] = []
            if queried and queried_present:
                ordered.append((queried, "queried_pid"))
            for d, where in all_dois:
                if d and d != queried and not any(d == x for x, _ in ordered):
                    ordered.append((d, where))
            if queried and not any(d == queried for d, _ in ordered):
                ordered.insert(0, (queried, "queried_pid"))

            identifiers = []
            for idx_i, (d, where) in enumerate(ordered):
                identifiers.append({
                    "scheme": "doi", "value": d,
                    "is_primary": idx_i == 0,
                    "scope": where,
                })
            for p in _pids(hit.get("pids")):
                scheme = (p.get("scheme") or "").lower()
                if scheme in ("pmid", "pmcid", "arxiv", "handle", "url") and p.get("value"):
                    identifiers.append({"scheme": scheme, "value": p.get("value")})
            for p in _pids(hit.get("originalIds")):
                scheme = (p.get("scheme") or "").lower()
                if scheme in ("pmid", "pmcid") and p.get("value") and not any(
                        i["scheme"] == scheme and i["value"] == p.get("value")
                        for i in identifiers):
                    identifiers.append({"scheme": scheme, "value": p.get("value")})
            inst = hit.get("instances") or []
            authors = hit.get("authors") or []
            flags = []
            if not hit.get("publicationDate"):
                flags.append("MISSING_PUBLICATION_DATE")
            flags.append("SNAPSHOT_ONLY")
            primary_doi = ordered[0][0] if ordered else None
            recs.append(build_record(
                source_id=SOURCE_ID,
                source_record_id=str(hit.get("id") or primary_doi or ""),
                entity_type="publication",
                original_name=U.norm_ws(hit.get("mainTitle")) or (primary_doi or ""),
                identifiers=identifiers,
                attributes={
                    "mainTitle": hit.get("mainTitle"),
                    "subTitle": hit.get("subTitle"),
                    "type": hit.get("type"),
                    "publisher": hit.get("publisher"),
                    "publicationDate": hit.get("publicationDate"),
                    "lastUpdateTimeStamp": hit.get("lastUpdateTimeStamp"),
                    "bestAccessRight": hit.get("bestAccessRight"),
                    "openAccessColor": hit.get("openAccessColor"),
                    "isGreen": hit.get("isGreen"),
                    "publiclyFunded": hit.get("publiclyFunded"),
                    "author_count": len(authors),
                    "container": hit.get("container"),
                    "instances": [
                        {"type": (x or {}).get("type"),
                         "license": (x or {}).get("license"),
                         "publicationDate": (x or {}).get("publicationDate"),
                         "pids": _pids((x or {}).get("pids")),
                         "urls": (x or {}).get("urls")}
                        for x in inst
                    ],
                    "pids": _pids(hit.get("pids")),
                    "originalIds": _pids(hit.get("originalIds")),
                    "doi_values_all": [{"doi": d, "where": w} for d, w in ordered],
                    "primary_doi": primary_doi,
                    "dates": {"publicationDate": hit.get("publicationDate"),
                              "lastUpdateTimeStamp": hit.get("lastUpdateTimeStamp")},
                    "queried_pid": r.get("doi"),
                },
                event_at=hit.get("publicationDate"),
                source_public_at=hit.get("publicationDate"),
                first_observed_at=None,
                fetched_at=fetched_at,
                source_url=(
                    f"https://api.openaire.eu/graph/v1/researchProducts?pid={r.get('doi')}"
                ),
                licence_status=LICENCE_STATUS,
                licence_note=LICENCE_NOTE,
                identity_status="UNKNOWN",
                evidence_status="CANDIDATE",
                quality_flags=flags,
                notes=(
                    "`lastUpdateTimeStamp` is a mutable snapshot marker, not a creation "
                    "date; no record-creation timestamp is exposed by the Graph API."
                ),
            ))
    return recs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parse", action="store_true")
    args = ap.parse_args(argv)
    idx_path = os.path.join(U.DATASETS, SOURCE_ID, "OPENAIRE_INDEX.json")
    idx = U.read_json(idx_path) if args.parse else collect()
    out = os.path.join(U.DATASETS, SOURCE_ID, "records.jsonl")
    n = write_jsonl(out, parse(idx))
    print(f"  {n} records -> {U.rel(out)}")
    U.write_provenance(
        SOURCE_ID, idx.get("raw_files") or [],
        extra={
            "endpoint": BASE, "method": "GET", "param_form": "pid=<bare DOI>",
            "licence_status": LICENCE_STATUS, "licence_note": LICENCE_NOTE,
            "records_file": U.rel(out), "record_count": n,
            "index_file": U.rel(idx_path),
            "found": idx.get("found"), "absent": idx.get("absent"),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
