"""Europe PMC connector.

Resolves the anchor DOIs with ``DOI:"..."`` OR-queries in bounded batches and
parses ``resultType=core`` results into ``horizon.evidence.v1``. Core results are
the only Europe PMC shape that carries ``grantsList`` and both publication dates,
which is why EXP-H1 and the grant linkage depend on them.

    python CONNECTORS/scholarly/europepmc.py
    python CONNECTORS/scholarly/europepmc.py --parse
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

SOURCE_ID = "europepmc"
BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
BATCH = 15           # DOIs per OR-query; keeps the query string short and stable
LICENCE_STATUS = "open_licence"
LICENCE_NOTE = (
    "Europe PMC content is available under the Europe PMC terms of use; the REST "
    "service is free and unrestricted. Individual records carry their own licence "
    "in `license` and full-text licence in `fullTextUrlList`. Metadata reuse is "
    "permitted with attribution (https://europepmc.org/help#termsandconditions, "
    "'Europe PMC is an ELIXIR Core Data Resource ... content is available under "
    "the Creative Commons Attribution licence where the source permits'). "
    "Recorded as open_licence at the metadata level; per-record `license` kept."
)


def build_query(dois: list[str]) -> str:
    return " OR ".join(f'DOI:"{d}"' for d in dois)


def collect() -> dict:
    dois = U.anchor_dois()
    batches = [dois[i:i + BATCH] for i in range(0, len(dois), BATCH)]
    results: list[dict] = []
    with U.make_client(
        "scholarly_europepmc", max_requests=len(batches) + 4,
        max_bytes_per_response=8_000_000, max_total_bytes=24_000_000, rps=1.5,
    ) as client:
        for bi, batch in enumerate(batches, 1):
            q = build_query(batch)
            url = BASE + "?" + urllib.parse.urlencode({
                "query": q, "format": "json", "resultType": "core",
                "pageSize": 100, "synonym": "false",
            })
            res = client.get(url)
            prov = U.save_fetch(
                SOURCE_ID, f"search_batch_{bi:02d}.json", res,
                note=f"EXP-H1 DOIs batch {bi}/{len(batches)} ({len(batch)} DOIs)",
            )
            prov["dois_requested"] = batch
            hits = []
            hit_count = None
            if res.ok:
                try:
                    doc = res.json()
                    hit_count = doc.get("hitCount")
                    hits = (doc.get("resultList") or {}).get("result") or []
                except Exception:
                    pass
            results.append({
                "batch": bi, "status": res.status, "raw": prov["path"],
                "hitCount": hit_count, "returned": len(hits),
                "dois_requested": batch,
                "results": hits,
            })
            print(f"    europepmc batch {bi}/{len(batches)}: {len(hits)} records")
        budget = client.budget_report()
    doc = {
        "source_id": SOURCE_ID, "generated_at": now_utc(), "endpoint": BASE,
        "batch_size": BATCH, "batch_count": len(batches),
        "anchor_count": len(dois), "budget": budget, "batches": results,
    }
    U.write_json(os.path.join(U.DATASETS, SOURCE_ID, "EUROPEPMC_INDEX.json"), doc)
    print("  budget:", budget)
    return doc


def _journal(j: dict | None) -> dict | None:
    if not j:
        return None
    return {
        "dateOfPublication": j.get("dateOfPublication"),
        "yearOfPublication": j.get("yearOfPublication"),
        "journal_title": ((j.get("journal") or {}).get("title")),
        "medline_abbreviation": ((j.get("journal") or {}).get("medlineAbbreviation")),
        "volume": j.get("volume"), "issue": j.get("issue"),
    }


def parse(index: dict | None = None) -> list:
    idx = index or U.read_json(os.path.join(U.DATASETS, SOURCE_ID, "EUROPEPMC_INDEX.json"))
    fetched_at = now_utc()
    recs = []
    for b in idx["batches"]:
        for r in b["results"]:
            doi = U.norm_doi(r.get("doi"))
            pmid = r.get("pmid")
            pmcid = r.get("pmcid")
            identifiers = []
            if doi:
                identifiers.append({"scheme": "doi", "value": doi, "is_primary": True})
            if pmid:
                identifiers.append({"scheme": "pmid", "value": str(pmid)})
            if pmcid:
                identifiers.append({"scheme": "pmcid", "value": str(pmcid)})
            ft = ((r.get("fullTextIdList") or {}).get("fullTextId")) or []
            grants = []
            for g in (r.get("grantsList") or {}).get("grant") or []:
                grants.append({
                    "grantId": g.get("grantId"),
                    "agency": g.get("agency"),
                    "acronym": g.get("acronym"),
                    "orderIn": g.get("orderIn"),
                })
            authors = ((r.get("authorList") or {}).get("author")) or []
            first_pub = r.get("firstPublicationDate")
            epmc_elec = r.get("electronicPublicationDate")
            flags = []
            if not first_pub:
                flags.append("MISSING_PUBLICATION_DATE")
            if not identifiers:
                flags.append("MISSING_IDENTIFIER")
            recs.append(build_record(
                source_id=SOURCE_ID,
                source_record_id=str(r.get("id") or pmid or doi or ""),
                entity_type="publication",
                original_name=U.norm_ws(r.get("title")) or (doi or ""),
                identifiers=identifiers,
                attributes={
                    "source": r.get("source"),
                    "inEPMC": r.get("inEPMC"),
                    "inPMC": r.get("inPMC"),
                    "isOpenAccess": r.get("isOpenAccess"),
                    "title": r.get("title"),
                    "authorString": r.get("authorString"),
                    "author_count": len(authors),
                    "first_author_family": (authors[0].get("lastName") if authors else None),
                    "last_author_family": (authors[-1].get("lastName") if authors else None),
                    "journalInfo": _journal(r.get("journalInfo")),
                    "pubTypeList": (r.get("pubTypeList") or {}).get("pubType"),
                    "dates": {
                        "firstPublicationDate": first_pub,
                        "electronicPublicationDate": epmc_elec,
                        "publicationDate": r.get("publicationDate"),
                        "firstIndexDate": r.get("firstIndexDate"),
                        "dateOfCreation": r.get("dateOfCreation"),
                        "dateOfRevision": r.get("dateOfRevision"),
                        "fullTextReceivedDate": r.get("fullTextReceivedDate"),
                        "pubYear": r.get("pubYear"),
                    },
                    "fullTextIds": ft,
                    "grants": grants,
                    "hasGrantMetadata": bool(grants),
                    "license": r.get("license"),
                    "citedByCount": r.get("citedByCount"),
                    # kept verbatim so trial-identifier and funding statements can be
                    # quoted exactly rather than paraphrased
                    "abstractText": r.get("abstractText"),
                },
                event_at=first_pub,
                source_public_at=first_pub,
                first_observed_at=r.get("firstIndexDate") or r.get("dateOfCreation"),
                fetched_at=fetched_at,
                source_url=(
                    f"https://europepmc.org/article/{r.get('source')}/{r.get('id')}"
                    if r.get("id") else BASE
                ),
                licence_status=LICENCE_STATUS,
                licence_note=LICENCE_NOTE,
                identity_status="UNKNOWN",
                evidence_status="CANDIDATE",
                quality_flags=flags,
                notes=(
                    "event_at/source_public_at use firstPublicationDate, Europe PMC's "
                    "declared earliest public publication date. firstIndexDate and "
                    "dateOfCreation are retained separately as indexing history."
                ),
            ))
    return recs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parse", action="store_true")
    args = ap.parse_args(argv)
    idx_path = os.path.join(U.DATASETS, SOURCE_ID, "EUROPEPMC_INDEX.json")
    idx = U.read_json(idx_path) if args.parse else collect()
    out = os.path.join(U.DATASETS, SOURCE_ID, "records.jsonl")
    n = write_jsonl(out, parse(idx))
    print(f"  {n} records -> {U.rel(out)}")
    U.write_provenance(
        SOURCE_ID,
        [{"path": b["raw"], "status": b["status"], "batch": b["batch"],
          "dois_requested": b["dois_requested"]} for b in idx["batches"]],
        extra={
            "endpoint": BASE, "batch_size": idx.get("batch_size"),
            "licence_status": LICENCE_STATUS, "licence_note": LICENCE_NOTE,
            "records_file": U.rel(out), "record_count": n,
            "index_file": U.rel(idx_path),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
