"""S-029 step 01 — query-recall probe (RQ1: what is observable at all?).

Before collecting anything, this probe measures the **search recall** of each
data source for each company's candidate name variants. The point is RQ1, not
convenience: a relation that the search cannot find is not the same as a relation
that does not exist. Every number here is a *hit count of a specific query*, and
the script records the exact query string so the recall statement is falsifiable.

Two distinct quantities are measured per variant:

* ``hits``  — how many records the source returns for that literal query;
* afterwards, in step 04, how many of those records survive entity mapping.

Nothing here asserts that a variant belongs to a company. Variant identity is
established separately by the entity register with primary sources; this probe
only tests *string* reachability.

Run:  python research/studies/relation_network_s029/code/s029_01_query_recall_probe.py
Writes: data/raw/request_log.jsonl, artifacts/query_recall_probe.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s029_common import (ARTIFACT_DIR, ProvenanceHTTP, HttpFailure, q, utcnow_iso,
                         write_json)

# ---------------------------------------------------------------------------
# Candidate name variants.  These are *search strings*, deliberately including
# former/subsidiary names and orthographic variants, because the recall gap they
# expose is one of the study's measurements.  Whether a variant is in fact the
# same legal entity is decided by the entity register (ENTITY_HISTORY_REGISTER.md),
# never by this list.
# ---------------------------------------------------------------------------
VARIANTS: dict[str, list[str]] = {
    "Medtronic": [
        "Medtronic",
        "Medtronic Sofamor Danek",
        "Medtronic Vascular",
        "Medtronic MiniMed",
        "MiniMed",
        "Covidien",
        "Tyco Healthcare",
    ],
    "GE HealthCare": [
        "GE HealthCare",
        "GE Healthcare",
        "GE Medical Systems",
        "General Electric",
        "GE Healthcare Technologies",
    ],
    "Philips": [
        "Philips",
        "Koninklijke Philips",
        "Philips Healthcare",
        "Philips Medical Systems",
        "Philips Respironics",
        "Respironics",
    ],
    "Dräger": [
        "Dräger",
        "Draeger",
        "Draegerwerk",
        "Drägerwerk",
        "Dräger Medical",
    ],
    "Mindray": [
        "Mindray",
        "Shenzhen Mindray",
        "Mindray Medical",
        "Datascope",
        "Zonare",
    ],
}


def ctgov_hits(client: ProvenanceHTTP, param: str, value: str) -> dict:
    url = "https://clinicaltrials.gov/api/v2/studies"
    params = {param: value, "pageSize": 1, "countTotal": "true", "format": "json"}
    try:
        body, rec = client.get(url, params=params, note=f"ctgov-count:{param}={value}")
        payload = json.loads(body)
        return {"hits": payload.get("totalCount"), "query": rec.url,
                "retrieved_at": rec.retrieved_at, "status": rec.status,
                "payload_sha256": rec.body_sha256, "error": None}
    except HttpFailure as exc:
        return {"hits": None, "query": url, "retrieved_at": utcnow_iso(),
                "status": None, "payload_sha256": None, "error": str(exc)}


def epmc_hits(client: ProvenanceHTTP, value: str) -> dict:
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    query = f'AFF:"{value}"'
    params = {"query": query, "format": "json", "pageSize": 1, "resultType": "idlist"}
    try:
        body, rec = client.get(url, params=params, note=f"epmc-count:AFF={value}")
        payload = json.loads(body)
        return {"hits": payload.get("hitCount"), "query_string": query,
                "query": rec.url, "retrieved_at": rec.retrieved_at,
                "status": rec.status, "payload_sha256": rec.body_sha256,
                "error": None}
    except HttpFailure as exc:
        return {"hits": None, "query_string": query, "query": url,
                "retrieved_at": utcnow_iso(), "status": None,
                "payload_sha256": None, "error": str(exc)}


def main() -> None:
    ctgov = ProvenanceHTTP("clinicaltrials_gov", delay_s=0.40)
    epmc = ProvenanceHTTP("europepmc", delay_s=0.40)

    out: dict = {
        "probe_name": "s029_query_recall_probe",
        "generated_at": utcnow_iso(),
        "purpose": "RQ1 search-recall measurement; hit counts only, no identity claim",
        "ctgov_query_parameter_semantics": {
            "query.spons": "sponsor OR collaborator name token match (verified by probe: "
                           "'Medtronic Vascular' is found by 'Medtronic')",
            "query.lead": "lead-sponsor name token match",
        },
        "companies": {},
    }

    for company, variants in VARIANTS.items():
        entry = {"variants": []}
        canonical = variants[0]
        # Two CT.gov search modes for the canonical name: sponsor field and
        # lead-sponsor field.  Their difference measures how many records only
        # have the company as collaborator rather than lead sponsor.
        entry["ctgov_canonical_by_mode"] = {
            "query.spons": ctgov_hits(ctgov, "query.spons", canonical),
            "query.lead": ctgov_hits(ctgov, "query.lead", canonical),
        }
        for v in variants:
            row = {
                "variant": v,
                "is_canonical": v == canonical,
                "ctgov_query_spons": ctgov_hits(ctgov, "query.spons", v),
                "europepmc_aff": epmc_hits(epmc, v),
            }
            entry["variants"].append(row)
            print(f"[{company}] {v:32s} ctgov.spons={row['ctgov_query_spons']['hits']!s:>7}"
                  f"  epmc.AFF={row['europepmc_aff']['hits']!s:>7}", flush=True)
        out["companies"][company] = entry

    # Post-processing: recall gap of the canonical-only search, per source.
    for company, entry in out["companies"].items():
        canon = next(r for r in entry["variants"] if r["is_canonical"])
        for src, key in (("ctgov", "ctgov_query_spons"), ("europepmc", "europepmc_aff")):
            counts = {r["variant"]: r[key]["hits"] for r in entry["variants"]}
            base = canon[key]["hits"] or 0
            union_upper = sum(v for v in counts.values() if isinstance(v, int))
            extra = max(union_upper - base, 0)
            entry[f"recall_gap_{src}"] = {
                "canonical_hits": base,
                "sum_of_variant_hits": union_upper,
                "upper_bound_extra_hits_from_variants": extra,
                "ratio_variants_over_canonical": (union_upper / base) if base else None,
                "note": "sum of per-variant hit counts is an UPPER bound: variants overlap, "
                        "so the true increment after de-duplication is measured in step 04",
            }

    write_json(ARTIFACT_DIR / "query_recall_probe.json", out)
    print(f"\nwrote {ARTIFACT_DIR / 'query_recall_probe.json'}")
    print(f"HTTP calls: ctgov={ctgov.calls} epmc={epmc.calls}")


if __name__ == "__main__":
    main()
