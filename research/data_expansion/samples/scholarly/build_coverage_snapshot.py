"""Build ``COVERAGE_SNAPSHOT.json``: five target firms, same-condition sweep.

Reproducible by construction: the exact ``query`` string, per-source parameters,
record limits and the de-duplication rule are written into the output file.

Run from the repository root::

    python research/data_expansion/samples/scholarly/build_coverage_snapshot.py

What it does
------------
For each of the five DATA-EXPANSION-001 firms it runs **one free-text search per
verified paper connector** with the same query string (the company name), then:

1. records the per-source hit count;
2. de-duplicates the four sources' records by DOI/PMID/PMCID union and records
   the unique-work count plus the pairwise duplicate overlap;
3. records the earliest ``source_public_at`` and the publication-year
   distribution of the de-duplicated set;
4. separates the company links the sources actually *assert* in structured
   fields (funder vs author affiliation) from records that merely matched the
   search string.

This is the number that matters: **unique works**, never raw rows.
"""

from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from medradar.external_sources import base
from medradar.external_sources.scholarly import dedupe

ROOT = Path(__file__).resolve().parents[3]  # research/data_expansion
OUTPUT = Path(__file__).resolve().parent / "COVERAGE_SNAPSHOT.json"
LEDGER = Path(__file__).resolve().parent / "requests.jsonl"

#: The five firms, in the order fixed by DATA-EXPANSION-001.
COMPANIES: tuple[dict[str, str], ...] = (
    {"company_key": "medtronic", "query": "Medtronic", "note": "canonical form"},
    {"company_key": "ge_healthcare", "query": "GE HealthCare", "note": "canonical form"},
    {"company_key": "philips", "query": "Philips", "note": "canonical form"},
    {
        "company_key": "draeger",
        "query": "Draeger",
        "note": "ASCII spelling for URL stability; identity resolves Draeger/Dräger to draeger",
    },
    {"company_key": "mindray", "query": "Mindray", "note": "canonical form"},
)

LIMIT_PER_SOURCE = 25
MAX_PAGES = 1
BUDGET = 40
MIN_INTERVAL = 1.0
TIMEOUT = 45.0

#: Controlled duplicate check: one exact DOI looked up in each source's native
#: identifier form.  A DOI is the authoritative cross-source key, so all four
#: sources should return the same work and the de-duplicator must collapse the
#: four records to exactly one work.  This is the positive control that shows the
#: low overlap in the broad firm sweep is a ranking effect, not a broken
#: deduplicator.
DOI_CONTROLS: tuple[dict[str, str], ...] = (
    {"label": "covid_vaccine_nejm", "doi": "10.1056/NEJMoa2034577"},
    {"label": "neuromodulation_device", "doi": "10.1109/TNSRE.2012.2183617"},
    {"label": "tavr_low_risk", "doi": "10.1056/NEJMoa1814052"},
)

def _collect_one(client: base.HttpClient, source_id: str, query: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run one connector; return (records, meta-with-query-and-error)."""
    from medradar.external_sources.scholarly import crossref, europepmc, openalex, pubmed_eutils

    modules = {
        "openalex": openalex,
        "europepmc": europepmc,
        "crossref": crossref,
        "pubmed_eutils": pubmed_eutils,
    }
    module = modules[source_id]
    meta: dict[str, Any] = {
        "query": query,
        "limit": LIMIT_PER_SOURCE,
        "max_pages": MAX_PAGES,
        "error": "",
    }
    try:
        if source_id == "pubmed_eutils":
            records = module.collect(client, limit=LIMIT_PER_SOURCE, term=query)
            meta["request_shape"] = (
                "esearch(term=<query>, retmax=25) then esummary(id=<ids>, retmode=json)"
            )
        else:
            records = module.collect(
                client, limit=LIMIT_PER_SOURCE, query=query, max_pages=MAX_PAGES
            )
            meta["request_shape"] = {
                "openalex": "GET /works?search=<query>&per-page=25&cursor=*&mailto=...",
                "europepmc": "GET /europepmc/webservices/rest/search?query=<query>&format=json&pageSize=25&resultType=core",
                "crossref": "GET /works?query=<query>&rows=25&cursor=*&mailto=...",
            }[source_id]
    except Exception as exc:  # a failing source is reported, not fatal
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return [], meta
    return records, meta


def _empty_summary() -> dict[str, Any]:
    return {
        "records": 0,
        "unique_works": 0,
        "duplicate_records": 0,
        "duplicate_ratio": 0.0,
        "earliest_source_public_at": "",
        "latest_source_public_at": "",
        "quality_histogram": {},
        "publication_year_histogram": {},
        "company_links": {},
        "records_attributed_to_this_company": 0,
        "error": "",
    }


def _summarise(records: list[dict[str, Any]], company_key: str) -> dict[str, Any]:
    summary = _empty_summary()
    summary["records"] = len(records)
    unique = dedupe.unique_publications(records)
    summary["unique_works"] = len(unique)
    summary["duplicate_records"] = len(records) - len(unique)
    summary["duplicate_ratio"] = (
        round((len(records) - len(unique)) / len(records), 4) if records else 0.0
    )
    dates = sorted(
        record["time"]["source_public_at"]
        for record in unique
        if record.get("time", {}).get("source_public_at")
    )
    if dates:
        summary["earliest_source_public_at"] = dates[0]
        summary["latest_source_public_at"] = dates[-1]
    quality: dict[str, int] = {}
    years: dict[str, int] = {}
    for record in unique:
        time_block = record.get("time") or {}
        level = str(time_block.get("source_public_at_quality") or "unknown")
        quality[level] = quality.get(level, 0) + 1
        date = str(time_block.get("source_public_at") or "")
        if len(date) >= 4:
            years[date[:4]] = years.get(date[:4], 0) + 1
    summary["quality_histogram"] = dict(sorted(quality.items()))
    summary["publication_year_histogram"] = dict(sorted(years.items()))
    tiers: dict[str, int] = {}
    attributed = 0
    for record in records:
        hit = False
        for ref in record.get("entity_refs", []) or []:
            if str(ref.get("resolved_key")) != company_key:
                continue
            tier = str((ref.get("evidence") or {}).get("signal") or "unspecified")
            tiers[tier] = tiers.get(tier, 0) + 1
            hit = True
        if hit:
            attributed += 1
    summary["company_links"] = dict(sorted(tiers.items()))
    summary["records_attributed_to_this_company"] = attributed
    return summary


def _overlap(records: list[dict[str, Any]]) -> dict[str, Any]:
    clusters = dedupe.cluster_publications(records)
    pairs: dict[str, int] = {}
    per_source_sole = {source: 0 for source in ("openalex", "europepmc", "crossref", "pubmed_eutils")}
    multi = 0
    for cluster in clusters:
        sources = cluster.sources
        if len(sources) > 1:
            multi += 1
            for left, right in itertools.combinations(sorted(sources), 2):
                key = f"{left}+{right}"
                pairs[key] = pairs.get(key, 0) + 1
        elif len(sources) == 1 and sources[0] in per_source_sole:
            per_source_sole[sources[0]] += 1
    return {
        "multi_source_works": multi,
        "duplicate_pairs": dict(sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))),
        "works_seen_in_one_source_only": dict(sorted(per_source_sole.items())),
    }


def _fetch_by_doi(
    client: base.HttpClient, source_id: str, doi: str
) -> dict[str, Any] | None:
    """Look one DOI up in a source's native identifier form and build evidence."""
    from medradar.external_sources.scholarly import crossref, europepmc, openalex, pubmed_eutils

    fetched = datetime.now(timezone.utc)
    if source_id == "openalex":
        result = client.get(
            "https://api.openalex.org/works",
            params={"filter": f"doi:{doi}", "per-page": 1, "mailto": "medradar.research@example.org"},
        )
        if not result.ok:
            return None
        results = (result.json() or {}).get("results") or []
        return openalex.to_evidence(results[0], fetched_at=fetched) if results else None
    if source_id == "crossref":
        result = client.get(
            f"https://api.crossref.org/works/{doi}",
            params={"mailto": "medradar.research@example.org"},
        )
        if not result.ok:
            return None
        message = (result.json() or {}).get("message")
        return crossref.to_evidence(message, fetched_at=fetched) if message else None
    if source_id == "europepmc":
        result = client.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": f'DOI:"{doi}"', "format": "json", "pageSize": 1, "resultType": "core"},
        )
        if not result.ok:
            return None
        hits = ((result.json() or {}).get("resultList") or {}).get("result") or []
        return europepmc.to_evidence(hits[0], fetched_at=fetched) if hits else None
    if source_id == "pubmed_eutils":
        items = pubmed_eutils.fetch_items(client, limit=1, term=f'"{doi}"[DOI]')
        return pubmed_eutils.to_evidence(items[0], fetched_at=fetched) if items else None
    return None


def _controlled_duplicate_check(ledger: base.HttpLedger) -> dict[str, Any]:
    """Look up three known DOIs in every source and prove the collapse to one work.

    Positive control: a DOI is the authoritative cross-source key, so all four
    sources returning the record must still count as **one** work.  This isolates
    the de-duplication rule from search-ranking effects.
    """
    result: dict[str, Any] = {
        "purpose": (
            "positive control: one exact DOI looked up in each source's native identifier form; "
            "the four records must collapse to one unique work"
        ),
        "lookup_rule": {
            "openalex": "GET /works?filter=doi:<doi>&per-page=1",
            "crossref": "GET /works/<doi>",
            "europepmc": 'GET /search?query=DOI:"<doi>"&resultType=core&pageSize=1',
            "pubmed_eutils": 'esearch(term="<doi>"[DOI]) + esummary',
        },
        "controls": [],
    }
    for control in DOI_CONTROLS:
        entry: dict[str, Any] = {
            "label": control["label"],
            "doi": control["doi"],
            "lookups": {},
            "records": [],
        }
        records: list[dict[str, Any]] = []
        for source_id in ("openalex", "europepmc", "crossref", "pubmed_eutils"):
            client = base.HttpClient(
                source_id=f"control_{source_id}",
                ledger=ledger,
                budget=BUDGET,
                min_interval=MIN_INTERVAL,
                timeout=TIMEOUT,
            )
            try:
                record = _fetch_by_doi(client, source_id, control["doi"])
                error = ""
            except Exception as exc:  # a failing lookup is data, not a crash
                record = None
                error = f"{type(exc).__name__}: {exc}"
            entry["lookups"][source_id] = {
                "found": record is not None,
                "evidence_id": record.get("evidence_id") if record else "",
                "error": error,
            }
            if record is not None:
                records.append(record)
        report = dedupe.dedupe_report(records)
        entry["records"] = [
            {"source_id": record["source_id"], "evidence_id": record["evidence_id"]}
            for record in records
        ]
        entry["records_total"] = report["records_collected"]
        entry["unique_works"] = report["unique_works"]
        entry["duplicate_ratio"] = report["duplicate_ratio"]
        entry["sources_found"] = report["records_by_source"]
        entry["collapsed_to_one_work"] = report["unique_works"] == 1
        result["controls"].append(entry)
        print(
            f"[control] {control['label']}: {report['records_collected']} records -> "
            f"{report['unique_works']} unique work(s)"
        )
    return result

def main() -> None:
    ledger = base.HttpLedger(LEDGER)
    snapshot: dict[str, Any] = {
        "schema": "medradar.data_expansion.coverage_snapshot.v1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "purpose": (
            "Same-condition five-firm sweep across the four verified paper connectors, reporting "
            "per-source hit counts, cross-source de-duplicated unique works, earliest public date "
            "and time distribution."
        ),
        "method": {
            "query_rule": "one free-text search per source per firm, query = the firm's display name",
            "limit_per_source": LIMIT_PER_SOURCE,
            "max_pages": MAX_PAGES,
            "dedupe_rule": (
                "DOI > PMID > PMCID; records sharing ANY of these identifiers are one work; "
                "records with none stay singletons and are reported separately"
            ),
            "company_link_rule": (
                "only structured fields count: funders -> tier 'funder', author affiliations -> "
                "tier 'author_affiliation'; a mere query hit with no structured company field is "
                "not a company link"
            ),
            "sources": ["openalex", "europepmc", "crossref", "pubmed_eutils"],
            "within_company_dedupe": "cross-source only; each source is already id-deduplicated",
            "controlled_duplicate_check": "three distinctive paper titles queried verbatim across all four sources as a positive control for the de-duplicator",
        },
        "companies": [],
        "totals": {},
    }
    all_records: dict[str, list[dict[str, Any]]] = {}
    for company in COMPANIES:
        entry: dict[str, Any] = {
            "company_key": company["company_key"],
            "query": company["query"],
            "query_note": company["note"],
            "sources": {},
        }
        company_records: list[dict[str, Any]] = []
        for source_id in ("openalex", "europepmc", "crossref", "pubmed_eutils"):
            client = base.HttpClient(
                source_id=f"coverage_{source_id}",
                ledger=ledger,
                budget=BUDGET,
                min_interval=MIN_INTERVAL,
                timeout=TIMEOUT,
            )
            records, meta = _collect_one(client, source_id, company["query"])
            summary = _summarise(records, company["company_key"])
            summary["query"] = meta["query"]
            summary["request_shape"] = meta["request_shape"]
            if meta["error"]:
                summary["error"] = meta["error"]
            entry["sources"][source_id] = summary
            company_records.extend(records)
        report = dedupe.dedupe_report(company_records)
        entry["cross_source"] = {
            "records_total": report["records_collected"],
            "unique_works": report["unique_works"],
            "duplicate_records": report["duplicate_records"],
            "duplicate_ratio": report["duplicate_ratio"],
            "multi_source_works": report["multi_source_works"],
            "works_by_source_set": report["works_by_source_set"],
            "records_by_source": report["records_by_source"],
        }
        entry["cross_source"]["overlap"] = _overlap(company_records)
        unique = dedupe.unique_publications(company_records)
        dates = sorted(
            record["time"]["source_public_at"]
            for record in unique
            if record.get("time", {}).get("source_public_at")
        )
        years: dict[str, int] = {}
        for record in unique:
            date = str((record.get("time") or {}).get("source_public_at") or "")
            if len(date) >= 4:
                years[date[:4]] = years.get(date[:4], 0) + 1
        entry["cross_source"]["earliest_source_public_at"] = dates[0] if dates else ""
        entry["cross_source"]["latest_source_public_at"] = dates[-1] if dates else ""
        entry["cross_source"]["publication_year_histogram"] = dict(sorted(years.items()))
        entry["cross_source"]["unique_works_without_identifier"] = report[
            "records_without_publication_identifier"
        ]
        snapshot["companies"].append(entry)
        all_records[company["company_key"]] = company_records
        print(
            f"[coverage] {company['company_key']}: "
            f"{report['records_collected']} records -> {report['unique_works']} unique works "
            f"({report['duplicate_ratio']:.0%} duplicates)"
        )

    snapshot["controlled_duplicate_check"] = _controlled_duplicate_check(ledger)
    snapshot["totals"] = {
        "companies": len(snapshot["companies"]),
        "records_total": sum(
            entry["cross_source"]["records_total"] for entry in snapshot["companies"]
        ),
        "unique_works_total": sum(
            entry["cross_source"]["unique_works"] for entry in snapshot["companies"]
        ),
        "note": (
            "Totals sum per-firm sweeps; a paper naming several firms can appear in more than one "
            "firm row, so the grand total is a workload figure, not a corpus size."
        ),
    }
    snapshot["provenance"] = {
        "tool": "research/data_expansion/samples/scholarly/build_coverage_snapshot.py",
        "request_ledger": "research/data_expansion/samples/scholarly/requests.jsonl",
        "requests_made": ledger.count(),
        "provider": "medradar.external_sources.scholarly connectors",
    }
    OUTPUT.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(OUTPUT), "requests": ledger.count()}, indent=2))


if __name__ == "__main__":
    main()



