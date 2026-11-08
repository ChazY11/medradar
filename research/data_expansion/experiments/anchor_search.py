"""Per-anchor, hindsight-free retrieval for EXP-A / EXP-B / EXP-C.

Why this module exists
----------------------
The generic connectors answer "give me N records from source X".  EXP-A needs a
different question: "for *this* 2019 Draeger milestone, what could a fixed,
hindsight-free query have retrieved *before* 2019-08-28?"  That requires

* a query built only from the anchor's own public fields (device name, product
  code generic name) — never from knowledge of the evidence we later found;
* a date bound applied at the source where the source supports it, and locally
  otherwise;
* one retrieval file per (source, anchor) so a reviewer can re-run any single cell.

Query construction rules (frozen)
---------------------------------
1. Start from the anchor's ``device_name`` and the openFDA generic name of its
   product code.
2. Drop generic tokens (the product-code generic name, a fixed stoplist) and
   tokens shorter than 4 characters.
3. Use at most the two most distinctive remaining tokens as a quoted phrase.
   If nothing survives, the anchor is recorded as ``no_query`` for that source —
   **not** silently skipped and not replaced by a broader query.
4. Never use the eventual evidence, the firm name, or a date from after the
   anchor to build a query.  (The firm name is deliberately *not* in the query:
   including it would make the search an entity search rather than a
   product-specificity test, and it is the confound PHOENIX-003 F4 identified.)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import base, timeq  # noqa: E402

CACHE = ROOT / "experiments" / "retrieval"
PRODUCT_CODE_CACHE = ROOT / "experiments" / "anchors" / "PRODUCT_CODES.json"

#: Tokens that carry no product identity.  Kept deliberately short and
#: inspectable; a longer list would start silently deciding results.
GENERIC_STOPWORDS = {
    "system", "systems", "device", "devices", "medical", "plus", "with", "without",
    "series", "model", "digital", "software", "platform", "solution", "solutions",
    "monitor", "monitoring", "care", "acute", "patient", "hospital", "clinical",
    "the", "and", "for", "new", "advanced", "next", "generation", "version",
    "infusion", "pump", "analyzer", "catheter", "stent", "sensor", "probe",
    "kit", "set", "unit", "module", "interface", "controller", "display",
    "inc", "llc", "ltd", "corp", "corporation", "gmbh", "company",
}

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]{2,}")


def load_anchors(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or (ROOT / "experiments" / "anchors" / "ANCHORS.json")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload["anchors"]


def load_product_codes(path: Path | None = None) -> dict[str, dict[str, str]]:
    path = path or PRODUCT_CODE_CACHE
    if not Path(path).exists():
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload.get("codes", {})


def fetch_product_codes(codes: list[str], *, min_interval: float = 0.6, allow_network: bool = True) -> dict:
    """Fetch openFDA classification names for the anchor product codes (one request)."""
    PRODUCT_CODE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ledger = base.HttpLedger(PRODUCT_CODE_CACHE.parent / "requests_product_codes.jsonl")
    client = base.HttpClient(
        "product_codes", ledger, budget=4, min_interval=min_interval, timeout=45.0, allow_network=allow_network
    )
    codes = sorted({c for c in codes if c})
    payload: dict[str, Any] = {"schema": "medradar.external.product_codes.v1", "fetched_at": timeq.utc_iso(), "codes": {}}
    if not codes:
        return payload
    query = " OR ".join(f'"{c}"' for c in codes)
    result = client.get(
        "https://api.fda.gov/device/classification.json",
        params={"search": f"product_code:({query})", "limit": min(1000, 5 * len(codes) + 10)},
    )
    payload["request"] = {"url": result.url, "status": result.status, "error": result.error}
    if result.ok:
        payload["request"]["sha256"] = base.sha256_bytes(result.body)
        for item in result.json().get("results", []):
            code = str(item.get("product_code") or "")
            if code:
                payload["codes"][code] = {
                    "generic_name": str(item.get("device_name") or ""),
                    "regulation_number": str(item.get("regulation_number") or ""),
                    "class": str(item.get("medical_specialty_description") or ""),
                }
    PRODUCT_CODE_CACHE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def distinctive_terms(anchor: Mapping[str, Any], product_codes: Mapping[str, Mapping[str, str]]) -> list[str]:
    generic_name = (product_codes.get(anchor.get("product_code", ""), {}) or {}).get("generic_name", "")
    generic_tokens = {t.lower() for t in _TOKEN_RE.findall(generic_name)}
    blocked = generic_tokens | GENERIC_STOPWORDS
    terms: list[str] = []
    for token in _TOKEN_RE.findall(str(anchor.get("device_name", ""))):
        lowered = token.lower()
        if lowered in blocked or len(lowered) < 4:
            continue
        if lowered.isdigit():
            continue
        terms.append(token)
    # Prefer tokens with letters+digits or unusual length: they are the brand signs.
    terms.sort(key=lambda t: (-(any(ch.isdigit() for ch in t)), -len(t)))
    seen: list[str] = []
    for term in terms:
        if term.lower() not in {s.lower() for s in seen}:
            seen.append(term)
    return seen[:2]


def query_text(anchor: Mapping[str, Any], product_codes: Mapping[str, Mapping[str, str]]) -> str:
    return " ".join(distinctive_terms(anchor, product_codes))


# --------------------------------------------------------------- source queries
# Each adapter receives (client, anchor, query, product_codes) and returns a list
# of retrieval hits: {"source_record_id", "title", "public_at", "raw_date_field",
# "url", "extra"}.  No adapter may filter on the anchor's date in a way that
# discards a record it retrieved; the date bound is recorded in `bound` so the
# analysis can re-apply it and the reviewer can see what was retrieved.

Hit = dict[str, Any]


def _hits_from(payload: Any, extract: Callable[[Any], list[Hit]]) -> tuple[list[Hit], str]:
    try:
        return extract(payload), ""
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc}"


def q_openalex(client, anchor, query, pcs) -> dict[str, Any]:
    bound = str(anchor["decision_date"])
    r = client.get(
        "https://api.openalex.org/works",
        params={"search": query, "filter": f"publication_date:<{bound}", "per-page": 25, "mailto": "medradar.research@example.org"},
    )
    out: dict[str, Any] = {"source_id": "openalex", "query": query, "bound": bound, "url": r.url, "status": r.status}
    if not r.ok:
        out["error"] = r.error
        return out

    def extract(payload):
        hits = []
        for work in payload.get("results", []):
            hits.append(
                {
                    "source_record_id": str(work.get("id", "")),
                    "title": str(work.get("title") or "")[:300],
                    "public_at": str(work.get("publication_date") or ""),
                    "raw_date_field": "publication_date",
                    "url": str(work.get("doi") or work.get("id") or ""),
                    "extra": {
                        "doi": str(work.get("doi") or ""),
                        "type": str(work.get("type") or ""),
                        "institutions": [
                            inst.get("display_name", "")
                            for auth in (work.get("authorships") or [])[:5]
                            for inst in (auth.get("institutions") or [])
                        ][:8],
                    },
                }
            )
        return hits

    out["hits"], out["extract_error"] = _hits_from(r.json(), extract)
    return out


def q_europepmc(client, anchor, query, pcs) -> dict[str, Any]:
    bound = str(anchor["decision_date"]).replace("-", "")
    r = client.get(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        params={"query": f'"{query}" AND FIRST_PDATE:[1900-01-01 TO {anchor["decision_date"]}]', "format": "json", "pageSize": 25},
    )
    out: dict[str, Any] = {"source_id": "europepmc", "query": query, "bound": bound, "url": r.url, "status": r.status}
    if not r.ok:
        out["error"] = r.error
        return out

    def extract(payload):
        hits = []
        for item in (payload.get("resultList") or {}).get("result", []):
            hits.append(
                {
                    "source_record_id": str(item.get("id") or item.get("pmid") or ""),
                    "title": str(item.get("title") or "")[:300],
                    "public_at": str(item.get("firstPublicationDate") or item.get("firstIndexDate") or ""),
                    "raw_date_field": "firstPublicationDate",
                    "url": f"https://europepmc.org/article/{item.get('source','MED')}/{item.get('id','')}",
                    "extra": {"doi": str(item.get("doi") or ""), "pmid": str(item.get("pmid") or "")},
                }
            )
        return hits

    out["hits"], out["extract_error"] = _hits_from(r.json(), extract)
    return out


def q_crossref(client, anchor, query, pcs) -> dict[str, Any]:
    bound = str(anchor["decision_date"])
    r = client.get(
        "https://api.crossref.org/works",
        params={
            "query.bibliographic": query,
            "filter": f"from-pub-date:1900-01-01,until-pub-date:{bound}",
            "rows": 25,
            "select": "DOI,title,published,issued,type,author",
            "mailto": "medradar.research@example.org",
        },
    )
    out: dict[str, Any] = {"source_id": "crossref", "query": query, "bound": bound, "url": r.url, "status": r.status}
    if not r.ok:
        out["error"] = r.error
        return out

    def extract(payload):
        hits = []
        for item in (payload.get("message") or {}).get("items", []):
            date_parts = ((item.get("published") or item.get("issued") or {}).get("date-parts") or [[None]])[0]
            stamp = "-".join(str(p) for p in date_parts if p) if date_parts and date_parts[0] else ""
            hits.append(
                {
                    "source_record_id": str(item.get("DOI") or ""),
                    "title": (item.get("title") or [""])[0][:300],
                    "public_at": stamp,
                    "raw_date_field": "published.date-parts",
                    "url": f"https://doi.org/{item.get('DOI','')}",
                    "extra": {"doi": str(item.get("DOI") or ""), "type": str(item.get("type") or "")},
                }
            )
        return hits

    out["hits"], out["extract_error"] = _hits_from(r.json(), extract)
    return out


def q_pubmed(client, anchor, query, pcs) -> dict[str, Any]:
    bound = str(anchor["decision_date"])
    search = client.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={
            "db": "pubmed",
            "term": f'"{query}"[Title/Abstract] AND ("1900/01/01"[PDAT] : "{bound}"[PDAT])',
            "retmode": "json",
            "retmax": 25,
            "tool": "medradar-research",
            "email": "medradar.research@example.org",
        },
    )
    out: dict[str, Any] = {"source_id": "pubmed_eutils", "query": query, "bound": bound, "url": search.url, "status": search.status}
    if not search.ok:
        out["error"] = search.error
        return out
    ids = ((search.json().get("esearchresult") or {}).get("idlist") or [])[:25]
    out["hits"] = []
    if not ids:
        return out
    summary = client.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        params={"db": "pubmed", "id": ",".join(ids), "retmode": "json", "tool": "medradar-research", "email": "medradar.research@example.org"},
    )
    if not summary.ok:
        out["error"] = summary.error
        return out
    result = summary.json().get("result") or {}
    for pmid in result.get("uids", []):
        item = result.get(pmid) or {}
        out["hits"].append(
            {
                "source_record_id": str(pmid),
                "title": str(item.get("title") or "")[:300],
                "public_at": str(item.get("pubdate") or item.get("epubdate") or ""),
                "raw_date_field": "pubdate/epubdate",
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "extra": {"journal": str(item.get("fulljournalname") or "")},
            }
        )
    return out


def q_semantic_scholar(client, anchor, query, pcs) -> dict[str, Any]:
    bound = str(anchor["decision_date"])
    r = client.get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={"query": query, "limit": 20, "fields": "title,year,publicationDate,externalIds"},
    )
    out: dict[str, Any] = {"source_id": "semantic_scholar", "query": query, "bound": bound, "url": r.url, "status": r.status}
    if not r.ok:
        out["error"] = r.error
        return out

    def extract(payload):
        hits = []
        for item in payload.get("data", []):
            pub = str(item.get("publicationDate") or item.get("year") or "")
            hits.append(
                {
                    "source_record_id": str(item.get("paperId") or ""),
                    "title": str(item.get("title") or "")[:300],
                    "public_at": pub,
                    "raw_date_field": "publicationDate/year",
                    "url": f"https://www.semanticscholar.org/paper/{item.get('paperId','')}",
                    "extra": {"externalIds": item.get("externalIds") or {}},
                }
            )
        return hits

    out["hits"], out["extract_error"] = _hits_from(r.json(), extract)
    return out


def q_ctgov(client, anchor, query, pcs) -> dict[str, Any]:
    bound = str(anchor["decision_date"])
    r = client.get(
        "https://clinicaltrials.gov/api/v2/studies",
        params={
            "query.term": query,
            "filter.advanced": f"AREA[StudyFirstPostDate]RANGE[1900-01-01,{bound}]",
            "pageSize": 20,
            "fields": "NCTId,BriefTitle,StudyFirstPostDate,LeadSponsorName,InterventionName",
        },
    )
    out: dict[str, Any] = {"source_id": "clinicaltrials_gov", "query": query, "bound": bound, "url": r.url, "status": r.status}
    if not r.ok:
        out["error"] = r.error
        return out

    def extract(payload):
        hits = []
        for study in payload.get("studies", []):
            proto = (study.get("protocolSection") or {})
            ident = proto.get("identificationModule") or {}
            status = proto.get("statusModule") or {}
            sponsor = (proto.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}
            arms = (proto.get("armsInterventionsModule") or {}).get("interventions") or []
            hits.append(
                {
                    "source_record_id": str(ident.get("nctId") or ""),
                    "title": str(ident.get("briefTitle") or "")[:300],
                    "public_at": str(status.get("studyFirstPostDateStruct", {}).get("date") or ""),
                    "raw_date_field": "studyFirstPostDate",
                    "url": f"https://clinicaltrials.gov/study/{ident.get('nctId','')}",
                    "extra": {
                        "lead_sponsor": str(sponsor.get("name") or ""),
                        "interventions": [a.get("name", "") for a in arms][:5],
                    },
                }
            )
        return hits

    out["hits"], out["extract_error"] = _hits_from(r.json(), extract)
    return out


def q_nih_reporter(client, anchor, query, pcs) -> dict[str, Any]:
    bound = str(anchor["decision_date"])
    fiscal_years = list(range(2010, int(anchor["decision_year"])))
    r = client.post_json(
        "https://api.reporter.nih.gov/v2/projects/search",
        {
            "criteria": {"text_search": query, "fiscal_years": fiscal_years or [int(anchor["decision_year"])]},
            "include_fields": ["ProjectNum", "ProjectTitle", "FiscalYear", "ProjectStartDate", "Organization"],
            "offset": 0,
            "limit": 20,
        },
    )
    out: dict[str, Any] = {"source_id": "nih_reporter", "query": query, "bound": bound, "url": r.url, "status": r.status}
    if not r.ok:
        out["error"] = r.error
        return out

    def extract(payload):
        hits = []
        for item in payload.get("results", []):
            org = (item.get("organization") or {}).get("orgName", "")
            hits.append(
                {
                    "source_record_id": str(item.get("project_num") or ""),
                    "title": str(item.get("project_title") or "")[:300],
                    "public_at": str(item.get("project_start_date") or ""),
                    "raw_date_field": "project_start_date",
                    "url": f"https://reporter.nih.gov/project-details/{item.get('appl_id','')}",
                    "extra": {"organization": str(org), "fiscal_year": item.get("fiscal_year")},
                }
            )
        return hits

    out["hits"], out["extract_error"] = _hits_from(r.json(), extract)
    return out


def q_usaspending(client, anchor, query, pcs) -> dict[str, Any]:
    bound = str(anchor["decision_date"])
    r = client.post_json(
        "https://api.usaspending.gov/api/v2/search/spending_by_award/",
        {
            "filters": {
                "award_type_codes": ["A", "B", "C", "D"],
                "keywords": [query],
                "time_period": [{"start_date": "2008-01-01", "end_date": bound}],
            },
            "fields": ["Award ID", "Recipient Name", "Award Amount", "Start Date", "Description"],
            "limit": 20,
            "page": 1,
        },
    )
    out: dict[str, Any] = {"source_id": "usaspending", "query": query, "bound": bound, "url": r.url, "status": r.status}
    if not r.ok:
        out["error"] = r.error
        return out

    def extract(payload):
        hits = []
        for item in payload.get("results", []):
            hits.append(
                {
                    "source_record_id": str(item.get("Award ID") or item.get("generated_internal_id") or ""),
                    "title": str(item.get("Description") or "")[:300],
                    "public_at": str(item.get("Start Date") or ""),
                    "raw_date_field": "Start Date",
                    "url": "https://www.usaspending.gov/search",
                    "extra": {"recipient": str(item.get("Recipient Name") or ""), "amount": item.get("Award Amount")},
                }
            )
        return hits

    out["hits"], out["extract_error"] = _hits_from(r.json(), extract)
    return out


ADAPTERS: dict[str, Callable[..., dict[str, Any]]] = {
    "openalex": q_openalex,
    "europepmc": q_europepmc,
    "crossref": q_crossref,
    "pubmed_eutils": q_pubmed,
    "semantic_scholar": q_semantic_scholar,
    "clinicaltrials_gov": q_ctgov,
    "nih_reporter": q_nih_reporter,
    "usaspending": q_usaspending,
}


def run_queries(
    sources: list[str],
    anchors: list[dict[str, Any]],
    *,
    min_interval: float = 0.7,
    budget_per_source: int | None = None,
    allow_network: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Run every (source, anchor) query, caching one JSON file per cell."""
    CACHE.mkdir(parents=True, exist_ok=True)
    pcs = load_product_codes()
    summary: dict[str, Any] = {"schema": "medradar.external.retrieval.v1", "ran_at": timeq.utc_iso(), "sources": {}}
    for source_id in sources:
        adapter = ADAPTERS.get(source_id)
        if adapter is None:
            summary["sources"][source_id] = {"skipped": "no hindsight-free adapter implemented"}
            continue
        directory = CACHE / source_id
        directory.mkdir(parents=True, exist_ok=True)
        ledger = base.HttpLedger(directory / "requests.jsonl")
        client = base.HttpClient(
            source_id,
            ledger,
            budget=budget_per_source or (4 * len(anchors) + 5),
            min_interval=min_interval,
            timeout=45.0,
            allow_network=allow_network,
        )
        cells: dict[str, Any] = {}
        no_query = 0
        for anchor in anchors:
            target = directory / f"{anchor['anchor_id'].replace(':','_')}.json"
            if target.exists() and not force:
                cells[anchor["anchor_id"]] = json.loads(target.read_text(encoding="utf-8"))
                continue
            text = query_text(anchor, pcs)
            if not text:
                no_query += 1
                cells[anchor["anchor_id"]] = {
                    "source_id": source_id,
                    "anchor_id": anchor["anchor_id"],
                    "query": "",
                    "skipped": "no distinctive term survived the generic-token filter",
                    "hits": [],
                }
            else:
                try:
                    cell = adapter(client, anchor, text, pcs)
                except Exception as exc:  # noqa: BLE001
                    cell = {"source_id": source_id, "anchor_id": anchor["anchor_id"], "query": text, "error": f"{type(exc).__name__}: {exc}", "hits": []}
                cell["anchor_id"] = anchor["anchor_id"]
                cell["fetched_at"] = timeq.utc_iso()
                cells[anchor["anchor_id"]] = cell
            target.write_text(json.dumps(cells[anchor["anchor_id"]], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        n_hits = sum(len(c.get("hits", []) or []) for c in cells.values())
        summary["sources"][source_id] = {
            "cells": len(cells),
            "hits": n_hits,
            "no_query": no_query,
            "requests": client.requests_made(),
            "errors": sum(1 for c in cells.values() if c.get("error")),
        }
    summary_path = CACHE / "RETRIEVAL_SUMMARY.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def load_cells(sources: list[str]) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for source_id in sources:
        directory = CACHE / source_id
        if not directory.is_dir():
            continue
        out[source_id] = {}
        for path in sorted(directory.glob("*.json")):
            if path.name.startswith("requests") or path.name.startswith("RETRIEVAL"):
                continue
            cell = json.loads(path.read_text(encoding="utf-8"))
            out[source_id][path.stem] = cell
    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="product-code cache + anchor query smoke test")
    parser.add_argument("--fetch-product-codes", action="store_true")
    parser.add_argument("--run", nargs="*", default=None, help="sources to run")
    parser.add_argument("--limit-anchors", type=int, default=0)
    args = parser.parse_args()
    anchors = load_anchors()
    if args.fetch_product_codes:
        payload = fetch_product_codes([a["product_code"] for a in anchors])
        print(f"product codes cached: {len(payload.get('codes', {}))}")
    if args.run is not None:
        selected = args.run or list(ADAPTERS)
        subset = anchors[: args.limit_anchors] if args.limit_anchors else anchors
        summary = run_queries(selected, subset)
        print(json.dumps(summary["sources"], indent=2))
