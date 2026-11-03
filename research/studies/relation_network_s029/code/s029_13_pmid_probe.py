"""S-029 step 13 — is a trial's referenced PMID actually resolvable in Europe PMC?

The pre-registered cross-source condition (T5) asks whether trial-referenced publication
identifiers are *resolvable* in a second source. Matching them only against the 770
publications this study happened to sample would answer a different and much stricter
question, and would understate cross-source linkage as a sampling artefact. So this probe
takes a deterministic sample of the PMIDs named in ClinicalTrials.gov reference lists and
asks Europe PMC directly whether the record exists, and whether it carries a DOI.

This is a genuine external check: the answer does not depend on our own collection.

Run:  python research/studies/relation_network_s029/code/s029_13_pmid_probe.py
Writes: artifacts/pmid_probe.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s029_common import (ARTIFACT_DIR, DATA_DIR, ProvenanceHTTP, HttpFailure, read_jsonl,
                         stable_seed, utcnow_iso, write_json)

import random

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
SAMPLE = 150
DOI_IN_CITATION = re.compile(r"doi:\s*(10\.\d{4,9}/[^\s,;)\]]+)", re.I)


def main() -> None:
    trials = list(read_jsonl(DATA_DIR / "ctgov_trials.jsonl"))
    pmids: dict[str, dict] = {}
    for t in trials:
        for ref in t.get("references") or []:
            pmid = (ref.get("pmid") or "").strip()
            if pmid and pmid not in pmids:
                m = DOI_IN_CITATION.search(ref.get("citation") or "")
                pmids[pmid] = {"pmid": pmid, "nct_id": t["nct_id"],
                               "citation": (ref.get("citation") or "")[:400],
                               "citation_doi": m.group(1).rstrip(".") if m else None,
                               "ref_type": ref.get("type")}
    all_pmids = sorted(pmids)
    rng = random.Random(stable_seed("s029", "pmid-probe", "v1"))
    sample = rng.sample(all_pmids, min(SAMPLE, len(all_pmids)))

    client = ProvenanceHTTP("europepmc", delay_s=0.40)
    rows = []
    for i, pmid in enumerate(sample):
        params = {"query": f"EXT_ID:{pmid}", "format": "json", "pageSize": 1,
                  "resultType": "core"}
        try:
            body, rec = client.get(API, params=params, note=f"epmc-extid:{pmid}")
            payload = json.loads(body)
            res = (payload.get("resultList") or {}).get("result") or []
            hit = payload.get("hitCount") or 0
            first = res[0] if res else {}
            rows.append({**pmids[pmid], "exists": bool(hit),
                         "hit_count": hit,
                         "europepmc_doi": first.get("doi"),
                         "europepmc_title": (first.get("title") or "")[:300],
                         "europepmc_pub_year": first.get("pubYear"),
                         "doi_matches_citation": (
                             (first.get("doi") or "").lower()
                             == (pmids[pmid]["citation_doi"] or "").lower()
                             if pmids[pmid]["citation_doi"] and first.get("doi") else None),
                         "url": rec.url, "retrieved_at": rec.retrieved_at,
                         "payload_sha256": rec.body_sha256})
        except HttpFailure as exc:
            rows.append({**pmids[pmid], "exists": None, "error": str(exc)})
        if (i + 1) % 50 == 0:
            print(f"  probed {i + 1}/{len(sample)}", flush=True)

    exists = sum(1 for r in rows if r.get("exists"))
    doi_match = [r for r in rows if r.get("doi_matches_citation") is not None]
    out = {
        "generated_at": utcnow_iso(),
        "distinct_pmids_in_registry_references": len(all_pmids),
        "sample_size": len(rows),
        "sample_seed": stable_seed("s029", "pmid-probe", "v1"),
        "resolvable_in_europepmc": exists,
        "resolution_rate_pct": round(100.0 * exists / max(len(rows), 1), 2),
        "carries_doi": sum(1 for r in rows if r.get("europepmc_doi")),
        "doi_agreement_with_citation": {
            "compared": len(doi_match),
            "agree": sum(1 for r in doi_match if r["doi_matches_citation"])},
        "ref_type_distribution": dict(Counter(r.get("ref_type") for r in rows)),
        "rows": rows,
        "n_http_calls": client.calls,
        "interpretation": "resolution here means the PMID exists as a Europe PMC record; it is a "
                          "statement about identifier interoperability, not about collaboration",
    }
    write_json(ARTIFACT_DIR / "pmid_probe.json", out)
    print(json.dumps({k: out[k] for k in ("distinct_pmids_in_registry_references", "sample_size",
                                          "resolvable_in_europepmc", "resolution_rate_pct",
                                          "carries_doi", "doi_agreement_with_citation",
                                          "n_http_calls")}, indent=2))


if __name__ == "__main__":
    main()
