"""PubMed E-utilities connector.

Two calls, both bounded and recorded:

1. ``esearch.fcgi`` with ``d1[doi] OR d2[doi] ...`` resolves the anchor DOIs to a
   PMID list.
2. ``efetch.fcgi`` returns the PubMed XML for those PMIDs, whose
   ``ArticleIdList`` is the only place PubMed itself exposes the DOI/PMCID
   cross-identifiers.

The XML also carries ``<ArticleDate>`` (electronic) and ``<PubDate>`` (issue),
which is exactly the date-disagreement surface EXP-H1 and EXP-H3 need.

    python CONNECTORS/scholarly/pubmed_eutils.py
    python CONNECTORS/scholarly/pubmed_eutils.py --parse
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse
import xml.etree.ElementTree as ET

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hz.schema import build_record, write_jsonl  # noqa: E402
from hz.timeq import now_utc  # noqa: E402

from CONNECTORS.scholarly import _util as U  # noqa: E402

SOURCE_ID = "pubmed_eutils"
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
DOI_CHUNK = 20
LICENCE_STATUS = "open_no_explicit_licence"
LICENCE_NOTE = (
    "PubMed abstracts and citation data are made available by NLM for public use; "
    "the E-utilities usage policy (https://www.ncbi.nlm.nih.gov/books/NBK25497/) "
    "grants access without a key at <=3 requests/second and asks that tool/email "
    "parameters identify the client. NLM does not attach an explicit blanket "
    "content licence to the citation metadata, and copyright in abstracts "
    "remains with the publisher, so this is recorded as open_no_explicit_licence."
)


def collect() -> dict:
    dois = U.anchor_dois()
    # DOIs must be *double quoted* before the [doi] field tag. Unquoted, PubMed's
    # query parser splits on the embedded "/" and "(" and silently under-matches:
    # an unquoted 60-DOI query returned 10 hits where 37 anchors carry a PMID.
    chunks = [dois[i:i + DOI_CHUNK] for i in range(0, len(dois), DOI_CHUNK)]
    with U.make_client(
        "scholarly_pubmed", max_requests=4 + len(chunks),
        max_bytes_per_response=8_000_000, max_total_bytes=20_000_000, rps=1.0,
    ) as client:
        pmids: list[str] = []
        es_records: list[dict] = []
        seen: set[str] = set()
        for ci, chunk in enumerate(chunks, 1):
            term = " OR ".join(f'"{d}"[doi]' for d in chunk)
            es_url = ESEARCH + "?" + urllib.parse.urlencode({
                "db": "pubmed", "term": term, "retmode": "json", "retmax": 200,
                "tool": "MedRadar-HORIZON-001", "email": U.CONTACT,
            })
            res = client.get(es_url)
            prov = U.save_fetch(
                SOURCE_ID, f"esearch_{ci:02d}.json", res,
                note=(f"EXP-H1 quoted DOI->PMID resolution, chunk {ci}/{len(chunks)}, "
                      f"{len(chunk)} DOIs"),
            )
            count = None
            got: list[str] = []
            if res.ok:
                try:
                    d = res.json()
                    got = (d.get("esearchresult") or {}).get("idlist") or []
                    count = (d.get("esearchresult") or {}).get("count")
                except Exception:
                    pass
            for p in got:
                if p not in seen:
                    seen.add(p)
                    pmids.append(p)
            es_records.append({
                "chunk": ci, "status": res.status, "raw": prov["path"],
                "dois_requested": chunk, "count": count, "pmids": got,
                "term_chars": len(term),
            })
            print(f"    esearch chunk {ci}/{len(chunks)}: status={res.status} "
                  f"count={count} pmids={len(got)}")
        print(f"    esearch total distinct PMIDs: {len(pmids)} / {len(dois)} anchor DOIs")

        fetch_result = None
        if pmids:
            ef_url = EFETCH + "?" + urllib.parse.urlencode({
                "db": "pubmed", "id": ",".join(pmids), "retmode": "xml",
                "tool": "MedRadar-HORIZON-001", "email": U.CONTACT,
            })
            ef_res = client.get(ef_url)
            prov = U.save_fetch(SOURCE_ID, "efetch.xml", ef_res,
                                note=f"EXP-H1 efetch for {len(pmids)} PMIDs")
            fetch_result = {"status": ef_res.status, "raw": prov["path"],
                            "pmid_count": len(pmids)}
            print(f"    efetch: status={ef_res.status} bytes={len(ef_res.body)}")
        budget = client.budget_report()
    doc = {
        "source_id": SOURCE_ID, "generated_at": now_utc(),
        "endpoints": {"esearch": ESEARCH, "efetch": EFETCH},
        "anchor_count": len(dois),
        "doi_chunk_size": DOI_CHUNK, "chunk_count": len(chunks),
        "esearch": {"chunks": es_records, "distinct_pmids": len(pmids), "pmids": pmids},
        "efetch": fetch_result,
        "budget": budget,
    }
    U.write_json(os.path.join(U.DATASETS, SOURCE_ID, "PUBMED_INDEX.json"), doc)
    print("  budget:", budget)
    return doc


def _text(node, path: str) -> str | None:
    if node is None:
        return None
    el = node.find(path)
    if el is None or el.text is None:
        return None
    return el.text.strip() or None


def parse_efetch_xml(xml_path: str) -> list[dict]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    out = []
    for art in root.findall(".//PubmedArticle"):
        pmid = _text(art, ".//MedlineCitation/PMID")
        ids: dict[str, str] = {}
        for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId"):
            t = (aid.get("IdType") or "").strip()
            if t and aid.text:
                ids.setdefault(t, aid.text.strip())
        art_dates = []
        for ad in art.findall(".//Article/ArticleDate"):
            y, m, d = _text(ad, "Year"), _text(ad, "Month"), _text(ad, "Day")
            if y:
                art_dates.append(f"{int(y):04d}-{int(m or 1):02d}-{int(d or 1):02d}")
        pub_date = None
        pd = art.find(".//Article/Journal/JournalIssue/PubDate")
        if pd is not None:
            y = _text(pd, "Year")
            m = _text(pd, "Month")
            d = _text(pd, "Day")
            med = _text(pd, "MedlineDate")
            if y:
                mm = m or "1"
                # PubMed months may be names ("Sep"); keep the raw form too
                try:
                    mm = f"{int(mm):02d}"
                except ValueError:
                    mm = {"jan": "01", "feb": "02", "mar": "03", "apr": "04",
                          "may": "05", "jun": "06", "jul": "07", "aug": "08",
                          "sep": "09", "oct": "10", "nov": "11", "dec": "12"
                          }.get(str(mm)[:3].lower(), "01")
                dd = d or "01"
                try:
                    dd = f"{int(dd):02d}"
                except ValueError:
                    dd = "01"
                pub_date = f"{int(y):04d}-{mm}-{dd}"
            elif med:
                pub_date = med
        grant_list = []
        for g in art.findall(".//MedlineCitation/Article/GrantList/Grant"):
            grant_list.append({
                "grant_id": _text(g, "GrantID"),
                "agency": _text(g, "Agency"),
                "acronym": _text(g, "Acronym"),
                "country": _text(g, "Country"),
            })
        authors = []
        for a in art.findall(".//Article/AuthorList/Author"):
            authors.append({
                "last": _text(a, "LastName"),
                "fore": _text(a, "ForeName"),
                "collective": _text(a, "CollectiveName"),
            })
        out.append({
            "pmid": pmid,
            "ids": ids,
            "title": _text(art, ".//Article/ArticleTitle"),
            "journal_title": _text(art, ".//Article/Journal/Title"),
            "journal_iso": _text(art, ".//Article/Journal/ISOAbbreviation"),
            "article_dates": art_dates,
            "pub_date": pub_date,
            "pub_date_raw": {
                "year": _text(pd, "Year") if pd is not None else None,
                "month": _text(pd, "Month") if pd is not None else None,
                "day": _text(pd, "Day") if pd is not None else None,
                "medline_date": _text(pd, "MedlineDate") if pd is not None else None,
            },
            "grant_list": grant_list,
            "authors": authors,
            "author_count": len(authors),
            "pub_types": [pt.text for pt in art.findall(".//Article/PublicationTypeList/PublicationType") if pt.text],
            "abstract_present": art.find(".//Article/Abstract/AbstractText") is not None,
            "abstract_text": " ".join(
                (el.text or "") for el in art.findall(".//Article/Abstract/AbstractText")
            ).strip() or None,
        })
    return out


def parse(index: dict | None = None) -> list:
    idx = index or U.read_json(os.path.join(U.DATASETS, SOURCE_ID, "PUBMED_INDEX.json"))
    ef = idx.get("efetch")
    articles = []
    if ef and ef.get("raw"):
        xml_path = os.path.join(U.ROOT, ef["raw"].replace("/", os.sep))
        articles = parse_efetch_xml(xml_path)
    fetched_at = now_utc()
    recs = []
    for a in articles:
        identifiers = []
        if a.get("pmid"):
            identifiers.append({"scheme": "pmid", "value": a["pmid"],
                                "issuing_authority": "NLM", "is_primary": True})
        if a["ids"].get("doi"):
            identifiers.append({"scheme": "doi", "value": U.norm_doi(a["ids"]["doi"])})
        if a["ids"].get("pmc"):
            identifiers.append({"scheme": "pmcid", "value": a["ids"]["pmc"]})
        if a["ids"].get("mid"):
            identifiers.append({"scheme": "pubmed_mid", "value": a["ids"]["mid"]})
        flags = []
        if not a.get("pub_date"):
            flags.append("MISSING_PUBLICATION_DATE")
        if not identifiers:
            flags.append("MISSING_IDENTIFIER")
        electronic = a["article_dates"][0] if a["article_dates"] else None
        recs.append(build_record(
            source_id=SOURCE_ID,
            source_record_id=a["pmid"] or "",
            entity_type="publication",
            original_name=U.norm_ws(a.get("title")) or (a.get("pmid") or ""),
            identifiers=identifiers,
            attributes={
                "title": a.get("title"),
                "journal_title": a.get("journal_title"),
                "journal_iso": a.get("journal_iso"),
                "article_ids": a["ids"],
                "dates": {
                    "article_date_electronic": electronic,
                    "pub_date": a.get("pub_date"),
                    "pub_date_raw": a.get("pub_date_raw"),
                },
                "author_count": a["author_count"],
                "first_author_family": (a["authors"][0]["last"] if a["authors"] else None),
                "last_author_family": (a["authors"][-1]["last"] if a["authors"] else None),
                "grant_list": a["grant_list"],
                "hasGrantMetadata": bool(a["grant_list"]),
                "pub_types": a["pub_types"],
                "abstract_present": a["abstract_present"],
                "abstract_text": a["abstract_text"],
            },
            event_at=a.get("pub_date"),
            source_public_at=electronic or a.get("pub_date"),
            first_observed_at=None,
            fetched_at=fetched_at,
            source_url=f"https://pubmed.ncbi.nlm.nih.gov/{a['pmid']}/" if a.get("pmid") else ESEARCH,
            licence_status=LICENCE_STATUS,
            licence_note=LICENCE_NOTE,
            identity_status="UNKNOWN",
            evidence_status="CANDIDATE",
            quality_flags=flags,
            notes=(
                "PubMed exposes NO record-creation timestamp in efetch output, so "
                "first_observed_at is left None rather than guessed."
            ),
        ))
    return recs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parse", action="store_true")
    args = ap.parse_args(argv)
    idx_path = os.path.join(U.DATASETS, SOURCE_ID, "PUBMED_INDEX.json")
    idx = U.read_json(idx_path) if args.parse else collect()
    out = os.path.join(U.DATASETS, SOURCE_ID, "records.jsonl")
    n = write_jsonl(out, parse(idx))
    print(f"  {n} records -> {U.rel(out)}")
    raws = [{"path": c["raw"], "role": f"esearch_chunk_{c['chunk']}"}
            for c in idx["esearch"]["chunks"]]
    if idx.get("efetch"):
        raws.append({"path": idx["efetch"]["raw"], "role": "efetch"})
    U.write_provenance(
        SOURCE_ID, raws,
        extra={
            "endpoints": {"esearch": ESEARCH, "efetch": EFETCH},
            "rate_policy": "NCBI: <=3 requests/second without an API key",
            "licence_status": LICENCE_STATUS, "licence_note": LICENCE_NOTE,
            "records_file": U.rel(out), "record_count": n,
            "index_file": U.rel(idx_path),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
