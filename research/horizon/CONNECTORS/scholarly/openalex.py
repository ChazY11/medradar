"""OpenAlex connector + EXP-H1 anchor selector.

Two jobs:

1. **Select the fixed anchor sample** exactly as frozen in
   ``experiments/scholarly/EXP_H1_SELECTION_RULE.md`` (deterministic tier ladder,
   12 works per firm, 60 works total) and write ``DATASETS/scholarly/openalex/
   ANCHORS.json``. Every raw API response used for the selection is kept verbatim
   under ``raw/`` so the sample can be re-derived byte for byte.
2. **Parse** the saved responses into ``horizon.evidence.v1`` records.

Runnable and bounded:

    python CONNECTORS/scholarly/openalex.py            # select + parse
    python CONNECTORS/scholarly/openalex.py --parse    # parse only, offline
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

SOURCE_ID = "openalex"
BASE = "https://api.openalex.org/works"
LICENCE_STATUS = "open_licence"   # OpenAlex data is CC0
LICENCE_NOTE = (
    "OpenAlex is published under CC0 1.0 Universal; the API documentation states "
    "'All data from OpenAlex is free and open... released under CC0 1.0'. "
    "https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication and "
    "https://openalex.org/licenses"
)


# --------------------------------------------------------------------- selection
def _filter_for(term: str, tier_filter: str) -> str:
    return (
        f"raw_affiliation_strings.search:{term},"
        f"from_publication_date:{U.WINDOW_FROM},"
        f"to_publication_date:{U.WINDOW_TO},"
        f"has_doi:true"
        f"{tier_filter}"
    )


def _url_for(term: str, tier_filter: str, per_page: int = 25) -> str:
    params = {
        "filter": _filter_for(term, tier_filter),
        "per-page": per_page,
        "sort": "publication_date:desc",
        "select": U.OPENALEX_SELECT,
        "mailto": U.CONTACT,
    }
    return BASE + "?" + urllib.parse.urlencode(params)


def _order(results: list[dict]) -> list[dict]:
    """Deterministic: publication_date DESC, then OpenAlex work id ASC.

    Works without a publication_date are placed last rather than dropped, so the
    ordering is total and reproducible.
    """
    return sorted(
        results,
        key=lambda w: (
            str(w.get("publication_date") or "9999-99-99"),
            w.get("id") or "",
        ),
    )


def select_anchors(*, offline: bool = False) -> dict:
    """Run the frozen selection rule. Saves every raw response."""
    anchors: list[dict] = []
    steps: list[dict] = []
    raw_records: list[dict] = []
    taken_ids: set[str] = set()

    client = None
    if not offline:
        client = U.make_client(
            "scholarly_openalex_selection", max_requests=16,
            max_bytes_per_response=8_000_000, max_total_bytes=24_000_000, rps=1.0,
        )

    try:
        for firm_spec in U.FIRMS:
            firm = firm_spec["firm"]
            terms = [firm_spec["term"]] + list(firm_spec["fallback_terms"])
            selected: list[dict] = []
            per_firm: list[dict] = []

            for tier_name, tier_filter in U.TIERS:
                if len(selected) >= U.PER_FIRM:
                    break
                for term_i, term in enumerate(terms):
                    if len(selected) >= U.PER_FIRM:
                        break
                    url = _url_for(term, tier_filter)
                    # The filename must be unique per (firm, tier, term). Naively
                    # replacing 'ä' with 'ae' made 'dräger' and its ASCII fallback
                    # 'draeger' collide, so one raw response overwrote the other and
                    # the sample could no longer be re-derived from the saved bytes.
                    slug = "".join(c if c.isalnum() else "_" for c in term)
                    fname = (
                        f"works_{firm.lower().replace(' ', '_')}"
                        f"__tier{tier_name}__t{term_i}__{slug}.json"
                    )
                    if offline:
                        path = os.path.join(U.raw_dir(SOURCE_ID), fname)
                        if not os.path.isfile(path):
                            continue
                        with open(path, "r", encoding="utf-8") as fh:
                            doc = json.load(fh)
                        prov = {"path": U.rel(path), "note": "offline re-parse"}
                    else:
                        assert client is not None
                        res = client.get(url)
                        prov = U.save_fetch(
                            SOURCE_ID, fname, res,
                            note=f"EXP-H1 anchor selection firm={firm} tier={tier_name} term={term}",
                        )
                        prov["requested_url_with_params"] = url
                        raw_records.append(prov)
                        if not res.ok:
                            per_firm.append({"tier": tier_name, "term": term,
                                             "status": res.status, "used": 0})
                            steps.append({"firm": firm, "tier": tier_name, "term": term,
                                          "status": res.status, "raw": prov["path"]})
                            continue
                        doc = res.json()

                    results = _order(doc.get("results") or [])
                    used = 0
                    for w in results:
                        if len(selected) >= U.PER_FIRM:
                            break
                        wid = w.get("id")
                        if not wid or wid in taken_ids:
                            continue
                        doi = U.norm_doi(w.get("doi"))
                        if not doi:            # has_doi:true should prevent this
                            continue
                        taken_ids.add(wid)
                        selected.append(_to_anchor(w, firm, term, tier_name, doi, len(selected) + 1))
                        used += 1
                    per_firm.append({
                        "tier": tier_name, "term": term,
                        "status": 200, "returned": len(results),
                        "total_count": (doc.get("meta") or {}).get("count"),
                        "used": used, "raw": prov["path"],
                    })
                    steps.append({"firm": firm, "tier": tier_name, "term": term,
                                  "status": 200, "used": used, "raw": prov["path"],
                                  "total_count": (doc.get("meta") or {}).get("count")})

            # renumber rank within firm
            for i, a in enumerate(selected, 1):
                a["rank_in_firm"] = i
            anchors.extend(selected)
            print(f"  {firm:14s} selected {len(selected):2d} anchors")

        for i, a in enumerate(anchors, 1):
            a["anchor_no"] = i
    finally:
        if client is not None:
            budget = client.budget_report()
            client.close()
            print("  openalex budget:", json.dumps(budget))

    doc = {
        "selection_rule": "experiments/scholarly/EXP_H1_SELECTION_RULE.md",
        "frozen_at": "2026-11-10",
        "generated_at": now_utc(),
        "per_firm_target": U.PER_FIRM,
        "window": {"from": U.WINDOW_FROM, "to": U.WINDOW_TO},
        "firms": U.FIRMS,
        "tier_ladder": [t[0] for t in U.TIERS],
        "anchor_count": len(anchors),
        "raw_files": raw_records,
        "steps": steps,
        "anchors": anchors,
    }
    path = os.path.join(U.DATASETS, SOURCE_ID, "ANCHORS.json")
    U.write_json(path, doc)
    print(f"  anchors -> {U.rel(path)}  ({len(anchors)})")
    return doc


def _to_anchor(w: dict, firm: str, term: str, tier: str, doi: str, rank: int) -> dict:
    ids = w.get("ids") or {}
    affils: list[str] = []
    matched: list[str] = []
    for a in w.get("authorships") or []:
        for s in a.get("raw_affiliation_strings") or []:
            s = str(s).strip()
            if not s:
                continue
            if s not in affils:
                affils.append(s)
            if term.lower() in s.lower() and s not in matched:
                matched.append(s)
    loc = w.get("primary_location") or {}
    src = (loc.get("source") or {})
    return {
        "anchor_no": 0,
        "rank_in_firm": rank,
        "firm": firm,
        "firm_term": term,
        "tier": tier,
        "openalex_id": w.get("id"),
        "doi": doi,
        "title": w.get("display_name") or w.get("title") or "",
        "publication_date": w.get("publication_date"),
        "created_date": w.get("created_date"),
        "updated_date": w.get("updated_date"),
        "type": w.get("type"),
        "type_crossref": w.get("type_crossref"),
        "ids": {k: ids.get(k) for k in ("doi", "pmid", "pmcid", "mag", "openalex") if ids.get(k)},
        "journal": src.get("display_name"),
        "affiliation_strings": affils,
        "matched_affiliation_strings": matched,
        "award_count": len(w.get("awards") or []),
        "funders": [
            {"id": (f or {}).get("id"), "name": (f or {}).get("display_name")}
            for f in (w.get("funders") or []) if isinstance(f, dict)
        ],
        "awards": [
            {"id": (x or {}).get("id"), "name": (x or {}).get("display_name"),
             "funder": (x or {}).get("funder_award_id"),
             "doi": (x or {}).get("doi")}
            for x in (w.get("awards") or []) if isinstance(x, dict)
        ],
        # declared contamination flag from the pre-registration, section 7
        "AFFILIATION_MAY_NOT_BE_FIRM": not matched,
    }


# ------------------------------------------------------------------------ parse
def parse(anchors_doc: dict | None = None) -> list:
    """Anchors -> horizon.evidence.v1 records. One record per anchor."""
    doc = anchors_doc or U.read_json(U.ANCHORS_PATH)
    fetched_at = now_utc()
    out = []
    for a in doc["anchors"]:
        ids = a.get("ids") or {}
        identifiers = []
        if a.get("doi"):
            identifiers.append({"scheme": "doi", "value": a["doi"], "is_primary": True})
        oid = (a.get("openalex_id") or "").rsplit("/", 1)[-1]
        if oid:
            identifiers.append({"scheme": "openalex_id", "value": oid})
        if ids.get("pmid"):
            identifiers.append({"scheme": "pmid", "value": str(ids["pmid"]).rsplit("/", 1)[-1]})
        if ids.get("pmcid"):
            identifiers.append({"scheme": "pmcid", "value": str(ids["pmcid"]).rsplit("/", 1)[-1]})
        flags = ["SNAPSHOT_ONLY"] if not a.get("created_date") else []
        if not a.get("publication_date"):
            flags.append("MISSING_PUBLICATION_DATE")
        if a.get("AFFILIATION_MAY_NOT_BE_FIRM"):
            flags.append("MISSING_MANUFACTURER")
        out.append(build_record(
            source_id=SOURCE_ID,
            source_record_id=oid or a["doi"],
            entity_type="publication",
            original_name=a.get("title") or a["doi"],
            identifiers=identifiers,
            manufacturer=None,   # affiliation != company; see selection rule s7
            attributes={
                "anchor_no": a["anchor_no"],
                "firm_affiliation_term": a["firm_term"],
                "firm_label": a["firm"],
                "tier": a["tier"],
                "publication_date": a.get("publication_date"),
                "created_date": a.get("created_date"),
                "updated_date": a.get("updated_date"),
                "type": a.get("type"),
                "type_crossref": a.get("type_crossref"),
                "journal": a.get("journal"),
                "affiliation_strings": a.get("affiliation_strings"),
                "matched_affiliation_strings": a.get("matched_affiliation_strings"),
                "awards": a.get("awards"),
                "funders": a.get("funders"),
                "tier_note": "tier A/B = title/abstract device term; tier C = affiliation only",
            },
            event_at=a.get("publication_date"),
            source_public_at=a.get("publication_date"),
            first_observed_at=a.get("created_date"),
            fetched_at=fetched_at,
            source_url=a.get("openalex_id") or "",
            licence_status=LICENCE_STATUS,
            licence_note=LICENCE_NOTE,
            identity_status="UNKNOWN",
            evidence_status="CANDIDATE",
            quality_flags=flags,
            notes=(
                "Affiliation string match only: this record does NOT assert that the "
                "work is by, for, or about the firm. See EXP_H1_SELECTION_RULE.md s7."
            ),
        ))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parse", action="store_true", help="parse saved raw only, no network")
    args = ap.parse_args(argv)

    if args.parse:
        doc = U.read_json(U.ANCHORS_PATH)
    else:
        print("selecting anchors (frozen rule)...")
        doc = select_anchors()

    recs = parse(doc)
    out_path = os.path.join(U.DATASETS, SOURCE_ID, "records.jsonl")
    from hz.schema import write_jsonl
    n = write_jsonl(out_path, recs)
    print(f"  {n} records -> {U.rel(out_path)}")

    prov = U.write_provenance(
        SOURCE_ID,
        doc.get("raw_files") or [],
        extra={
            "endpoint": BASE,
            "access": "keyless; anonymous daily budget noted in PROBES.json",
            "licence_status": LICENCE_STATUS,
            "licence_note": LICENCE_NOTE,
            "anchors_file": U.rel(U.ANCHORS_PATH),
            "records_file": U.rel(out_path),
            "record_count": n,
        },
    )
    print("  provenance ->", U.rel(prov))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
