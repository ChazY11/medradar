"""S-029 step 11 — cross-source verification (OpenAlex, Crossref, ROR).

RQ3 asks whether the same entity can be linked reliably *across* databases. That can
only be measured against a second index, so this step takes the publications already
collected from Europe PMC and asks OpenAlex and Crossref about the same DOIs.

Three measurements:

1. **DOI-level agreement.** Is the DOI present in OpenAlex, and does Crossref return
   the same title/year? A cross-source claim rests on the identifier, so identifier
   agreement is the precondition.
2. **Institution-level agreement.** For papers with structured OpenAlex authorships,
   compare the set of institution ROR ids OpenAlex reports with the set this study
   derived by parsing Europe PMC affiliation text. This is a direct, honest measure
   of how much of our "institution" layer is an artefact of text parsing.
3. **Company funding.** Crossref's Funder Registry gives a persistent id to funders;
   OpenAlex grants carry funder ids. Where a company is a registered funder, a
   funding relation can be checked against a second source instead of trusted.

Budget discipline: OpenAlex is used on a shared unauthenticated budget
($0.10/day at $0.001/request), so DOIs are batched (50 per request, OR filter) and
the request count is capped and reported. Crossref is used politely with a mailto.

Run:  python research/studies/relation_network_s029/code/s029_11_crosssource.py
Writes: data/crosssource.jsonl, artifacts/crosssource.json
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s029_common import (ARTIFACT_DIR, DATA_DIR, ProvenanceHTTP, HttpFailure, norm_name,
                         read_jsonl, stable_seed, utcnow_iso, write_json, write_jsonl)

OPENALEX = "https://api.openalex.org/works"
CROSSREF_WORKS = "https://api.crossref.org/works"
CROSSREF_FUNDERS = "https://api.crossref.org/funders"
MAILTO = "medradar.research@proton.me"
BATCH = 50
MAX_OPENALEX_REQUESTS = 16

COMPANY_FUNDER_QUERIES = {
    "medtronic": "Medtronic",
    "ge_healthcare": "GE Healthcare",
    "philips": "Philips",
    "draeger": "Draeger",
    "mindray": "Mindray",
}


def main() -> None:
    pubs = [p for p in read_jsonl(DATA_DIR / "epmc_pubs.jsonl")
            if p.get("doi") and p.get("source_db") != "PAT"]
    institutions = list(read_jsonl(DATA_DIR / "institutions.jsonl"))
    our_ror_by_pub: dict[str, set] = defaultdict(set)
    inst_by_cand = {i["candidate_id"]: i for i in institutions}
    for ic in institutions:
        if ic["family"] != "publication_affiliation":
            continue
        ror = (ic.get("ror") or {})
        if ror.get("status") in ("EXACT", "FUZZY") and ror.get("ror_id"):
            for pk in ic["example_records"]:
                our_ror_by_pub[pk].add(ror["ror_id"])

    oa = ProvenanceHTTP("openalex", delay_s=1.0, timeout=60)
    cr = ProvenanceHTTP("crossref", delay_s=0.3, timeout=45)

    # ---------------------------------------------------------------
    # 1. OpenAlex batch lookup by DOI
    # ---------------------------------------------------------------
    by_doi = {}
    for p in pubs:
        by_doi[p["doi"].lower()] = p
    dois = sorted(by_doi)
    batches = [dois[i:i + BATCH] for i in range(0, len(dois), BATCH)][:MAX_OPENALEX_REQUESTS]
    oa_works: dict[str, dict] = {}
    oa_requests = []
    for bi, batch in enumerate(batches):
        filt = "doi:" + "|".join(batch)
        # No `select`: OpenAlex rejects a select list containing `grants`, and grants are
        # needed for the funder cross-check. Full records for 50 DOIs per request are within
        # the request budget; the payload size is a local cost, not a budget cost.
        params = {"filter": filt, "per-page": BATCH, "mailto": MAILTO}
        try:
            body, rec = oa.get(OPENALEX, params=params, note=f"openalex:doi-batch:{bi}")
            payload = json.loads(body)
            oa_requests.append({"batch": bi, "n_dois": len(batch),
                                "n_results": len(payload.get("results") or []),
                                "url": rec.url, "retrieved_at": rec.retrieved_at,
                                "payload_sha256": rec.body_sha256})
            for w in payload.get("results") or []:
                d = (w.get("doi") or "").replace("https://doi.org/", "").lower()
                if d:
                    oa_works[d] = w
        except HttpFailure as exc:
            oa_requests.append({"batch": bi, "error": str(exc)})
        print(f"[openalex] batch {bi + 1}/{len(batches)} results={len(oa_works)}", flush=True)

    # ---------------------------------------------------------------
    # 2. Crossref DOI verification on a deterministic sample
    # ---------------------------------------------------------------
    rng = random.Random(stable_seed("s029", "crossref-sample"))
    sample = sorted(rng.sample(dois, min(60, len(dois))))
    cr_rows = []
    for doi in sample:
        try:
            body, rec = cr.get(f"{CROSSREF_WORKS}/{doi}", note=f"crossref:doi:{doi}")
            msg = (json.loads(body) or {}).get("message") or {}
            title = (msg.get("title") or [""])[0]
            issued = ((msg.get("issued") or {}).get("date-parts") or [[None]])[0]
            our = by_doi[doi]
            our_title = (our.get("title") or "")
            cr_rows.append({
                "doi": doi,
                "crossref_status": rec.status,
                "crossref_title": title,
                "title_agreement": norm_name(title) == norm_name(our_title)
                if title and our_title else None,
                "crossref_issued": "-".join(str(x) for x in issued if x) or None,
                "crossref_created": ((msg.get("created") or {}).get("date-time")),
                "europepmc_first_publication_date": our.get("first_publication_date"),
                "europepmc_first_index_date": our.get("first_index_date"),
                "crossref_funders": [{"name": f.get("name"), "doi": f.get("DOI"),
                                      "award": f.get("award")}
                                     for f in (msg.get("funder") or [])],
                "url": rec.url, "retrieved_at": rec.retrieved_at,
                "payload_sha256": rec.body_sha256})
        except HttpFailure as exc:
            cr_rows.append({"doi": doi, "crossref_status": None, "error": str(exc)})
        if len(cr_rows) % 20 == 0:
            print(f"[crossref] verified {len(cr_rows)}/{len(sample)}", flush=True)

    # ---------------------------------------------------------------
    # 3. Funder Registry identity for the five companies
    # ---------------------------------------------------------------
    funder_ids = {}
    for ck, q in COMPANY_FUNDER_QUERIES.items():
        try:
            body, rec = cr.get(CROSSREF_FUNDERS, params={"query": q, "rows": 5, "mailto": MAILTO},
                               note=f"crossref:funders:{ck}")
            items = ((json.loads(body) or {}).get("message") or {}).get("items") or []
            funder_ids[ck] = {
                "query": q,
                "candidates": [{"doi": it.get("DOI"), "name": it.get("name"),
                                "country": it.get("country"), "alt_names": (it.get("alt-names") or [])[:4]}
                               for it in items],
                "url": rec.url, "retrieved_at": rec.retrieved_at,
                "payload_sha256": rec.body_sha256}
        except HttpFailure as exc:
            funder_ids[ck] = {"query": q, "error": str(exc)}
        print(f"[crossref] funders {ck}: {len(funder_ids[ck].get('candidates') or [])} candidates", flush=True)

    # ---------------------------------------------------------------
    # 4. Agreement measurements
    # ---------------------------------------------------------------
    rows = []
    inst_agree = Counter()
    for doi, p in by_doi.items():
        w = oa_works.get(doi)
        row = {"doi": doi, "pub_key": p["pub_key"], "in_openalex": bool(w)}
        if w:
            oa_rors = set()
            for au in w.get("authorships") or []:
                for inst in au.get("institutions") or []:
                    if inst.get("ror"):
                        oa_rors.add(inst["ror"])
            ours = our_ror_by_pub.get(p["pub_key"], set())
            row.update({
                "openalex_id": w.get("id"),
                "openalex_publication_date": w.get("publication_date"),
                "openalex_created_date": w.get("created_date"),
                "openalex_updated_date": w.get("updated_date"),
                "openalex_type": w.get("type"),
                "n_openalex_institutions": len(oa_rors),
                "n_our_institutions": len(ours),
                "ror_overlap": len(oa_rors & ours),
                "oa_only": sorted(oa_rors - ours)[:6],
                "our_only": sorted(ours - oa_rors)[:6],
                "openalex_grant_funders": [{"id": g.get("funder"), "name": g.get("funder_display_name")}
                                           for g in (w.get("grants") or [])][:6],
            })
            if oa_rors or ours:
                if oa_rors & ours:
                    inst_agree["overlap"] += 1
                elif ours and oa_rors:
                    inst_agree["disjoint"] += 1
                elif ours:
                    inst_agree["ours_only"] += 1
                else:
                    inst_agree["openalex_only"] += 1
        rows.append(row)
    rows.sort(key=lambda r: r["pub_key"])
    write_jsonl(DATA_DIR / "crosssource.jsonl", rows)

    n = len(rows)
    n_oa = sum(1 for r in rows if r["in_openalex"])
    title_agree = [r for r in cr_rows if r.get("title_agreement") is not None]
    report = {
        "generated_at": utcnow_iso(),
        "sample": {"publications_with_doi": n, "crossref_sample": len(cr_rows),
                   "openalex_batch_requests": len(oa_requests)},
        "openalex": {
            "found": n_oa,
            "doi_match_rate": round(n_oa / n, 4) if n else None,
            "requests": oa_requests,
            "note": "OpenAlex is queried on the shared unauthenticated budget; request "
                    "count is capped and reported",
        },
        "institution_agreement": dict(inst_agree),
        "institution_agreement_rates": {
            k: round(v / max(sum(inst_agree.values()), 1), 4) for k, v in inst_agree.items()},
        "crossref": {
            "n_verified": len(title_agree),
            "title_agreement_rate": round(sum(1 for r in title_agree if r["title_agreement"])
                                          / max(len(title_agree), 1), 4),
            "n_with_funders": sum(1 for r in cr_rows if r.get("crossref_funders")),
        },
        "crossref_funder_registry": funder_ids,
        "n_http_calls": {"openalex": oa.calls, "crossref": cr.calls},
    }
    write_json(ARTIFACT_DIR / "crosssource.json", report)
    print(json.dumps({k: report[k] for k in ("sample", "openalex", "institution_agreement",
                                             "institution_agreement_rates", "crossref")},
                     indent=2, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
