"""S-029 step 03 — Europe PMC collection of publication–affiliation evidence.

Why this source and what it can support
---------------------------------------
Europe PMC is the public *index* of biomedical literature. A record states: these
authors, with these affiliations, published this paper, indexed on this date. That
supports Relation B (author -> publication, author -> institution) and, when one
paper carries both a company affiliation and an institutional affiliation, a
**co-affiliation** claim.

Co-affiliation is a fact about one paper. It is NOT collaboration, and it is NOT
knowledge transfer in any direction. The ontology (RELATION_ONTOLOGY.md §2,
Relation B) forbids that interpretation and this collector does not create it.

What "time" means here
----------------------
* ``firstPublicationDate`` -> publication date (event_at for the paper).
* ``firstIndexDate``       -> when the record entered the index (published_at).
* ``dateOfCreation`` / ``dateOfRevision`` -> record metadata events (source_updated_at).
These are stored separately and never substituted for one another. ``first_seen_at``
is the collector's real wall clock.

Sampling (and why it is a sample, not a census)
-----------------------------------------------
A company-name affiliation search returns thousands of records (Philips: 18,636 at
probe time). A laptop study cannot and should not take a census of that. This
collector takes a **year-stratified sample** (<= N_PER_YEAR per company per year)
while recording the full per-year ``hitCount``, so that the report can state both
the sampled evidence and the population it was drawn from. Sampling is uniform in
the sense of "newest N within each year", which is a stated, reproducible rule, not
a haphazard pick.

Former/subsidiary name strings are sampled separately (<= N_PER_VARIANT newest
records each) so that the historical-identity problem is measurable instead of
being invisible.

Run:  python research/studies/relation_network_s029/code/s029_03_collect_epmc.py
Writes: data/raw/epmc_*.json.gz, artifacts/epmc_manifest.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s029_common import (ARTIFACT_DIR, ProvenanceHTTP, HttpFailure, save_raw_envelope,
                         utcnow_iso, write_json)

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
YEARS = list(range(2010, 2027))
N_PER_YEAR = 10
N_PER_VARIANT = 10

CANONICAL = {
    "medtronic": "Medtronic",
    "ge_healthcare": "GE HealthCare",
    "philips": "Philips",
    "draeger": "Draeger",          # ASCII spelling: the diacritic form returns 45 records vs 975
    "mindray": "Mindray",
}

OTHER_VARIANTS = {
    "medtronic": ["Medtronic Vascular", "Medtronic MiniMed", "Covidien", "Tyco Healthcare"],
    "ge_healthcare": ["GE Medical Systems", "General Electric"],
    "philips": ["Philips Healthcare", "Philips Respironics", "Respironics"],
    "draeger": ["Dräger", "Drägerwerk"],
    "mindray": ["Shenzhen Mindray", "Datascope"],
}


def slug(s: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "_" for c in s)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")


FIELD_SET = None  # Europe PMC core payload is kept whole: no field selection exists.


def search(client: ProvenanceHTTP, query: str, page_size: int, result_type: str,
           sort: str | None = None) -> tuple[dict, dict]:
    params = {"query": query, "format": "json", "pageSize": page_size,
              "resultType": result_type}
    if sort:
        params["sort"] = sort
    body, rec = client.get(API, params=params, note=f"epmc:{query}:n={page_size}")
    payload = json.loads(body)
    provenance = {"url": rec.url, "retrieved_at": rec.retrieved_at,
                  "status": rec.status, "payload_sha256": rec.body_sha256}
    return payload, provenance


def collect_year(client: ProvenanceHTTP, company: str, year: int) -> dict:
    query = f'AFF:"{CANONICAL[company]}" AND (FIRST_PDATE:[{year}-01-01 TO {year}-12-31])'
    hits_payload, hits_prov = search(client, query, 1, "idlist")
    hit_count = hits_payload.get("hitCount")
    records: list[dict] = []
    fetch_prov = None
    stop = "exhausted"
    if hit_count:
        payload, fetch_prov = search(client, query, min(N_PER_YEAR, 100), "core",
                                     sort="P_PDATE_D desc")
        records = (payload.get("resultList") or {}).get("result") or []
        if hit_count > len(records):
            stop = f"sampled:{len(records)}_of_{hit_count}"
    envelope = {
        "source": "europepmc",
        "api_url": API,
        "query_string": query,
        "query_family": "year_stratified",
        "company_key": company,
        "year": year,
        "hit_count": hit_count,
        "n_records": len(records),
        "sampling_rule": f"newest {N_PER_YEAR} by P_PDATE_D within the year (deterministic sort)",
        "stop_reason": stop,
        "hit_query_provenance": hits_prov,
        "fetch_query_provenance": fetch_prov,
        "collected_at": utcnow_iso(),
        "records": records,
    }
    stem = f"epmc_{company}_y{year}"
    save_raw_envelope(stem, envelope)
    return {"year": year, "hit_count": hit_count, "n_records": len(records),
            "stop_reason": stop, "raw_file": f"data/raw/{stem}.json.gz"}


def collect_variant(client: ProvenanceHTTP, company: str, variant: str) -> dict:
    query = f'AFF:"{variant}"'
    payload, prov = search(client, query, N_PER_VARIANT, "core", sort="P_PDATE_D desc")
    records = (payload.get("resultList") or {}).get("result") or []
    hit_count = payload.get("hitCount")
    envelope = {
        "source": "europepmc",
        "api_url": API,
        "query_string": query,
        "query_family": "name_variant",
        "company_key": company,
        "variant": variant,
        "hit_count": hit_count,
        "n_records": len(records),
        "sampling_rule": f"newest {N_PER_VARIANT} by P_PDATE_D",
        "stop_reason": f"sampled:{len(records)}_of_{hit_count}",
        "fetch_query_provenance": prov,
        "collected_at": utcnow_iso(),
        "records": records,
    }
    stem = f"epmc_{company}_var_{slug(variant)}"
    save_raw_envelope(stem, envelope)
    return {"variant": variant, "hit_count": hit_count, "n_records": len(records),
            "raw_file": f"data/raw/{stem}.json.gz"}


def main() -> None:
    client = ProvenanceHTTP("europepmc", delay_s=0.40)
    manifest: dict = {"source": "europepmc", "collected_at": utcnow_iso(),
                      "years": [YEARS[0], YEARS[-1]], "n_per_year": N_PER_YEAR,
                      "n_per_variant": N_PER_VARIANT, "companies": {}}

    for company in CANONICAL:
        entry = {"canonical": CANONICAL[company], "per_year": [], "variants": []}
        total_hits = 0
        for year in YEARS:
            try:
                row = collect_year(client, company, year)
            except HttpFailure as exc:
                row = {"year": year, "error": str(exc)}
            entry["per_year"].append(row)
            total_hits += row.get("hit_count") or 0
            print(f"[epmc] {company:14s} {year} hits={row.get('hit_count')!s:>7} "
                  f"kept={row.get('n_records')}", flush=True)
        entry["total_hits_in_window"] = total_hits
        for variant in OTHER_VARIANTS.get(company, []):
            try:
                row = collect_variant(client, company, variant)
            except HttpFailure as exc:
                row = {"variant": variant, "error": str(exc)}
            entry["variants"].append(row)
            print(f"[epmc] {company:14s} variant={variant:28s} hits={row.get('hit_count')!s:>7} "
                  f"kept={row.get('n_records')}", flush=True)
        manifest["companies"][company] = entry

    manifest["n_http_calls"] = client.calls
    write_json(ARTIFACT_DIR / "epmc_manifest.json", manifest)
    print(f"\nwrote {ARTIFACT_DIR / 'epmc_manifest.json'} http_calls={client.calls}")


if __name__ == "__main__":
    main()
