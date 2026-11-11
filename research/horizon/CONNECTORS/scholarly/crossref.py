"""Crossref connector.

Fetches one ``/works/{doi}`` record per anchor DOI and parses it into
``horizon.evidence.v1``.

    python CONNECTORS/scholarly/crossref.py            # fetch + parse
    python CONNECTORS/scholarly/crossref.py --parse    # offline re-parse
"""

from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hz.schema import build_record, write_jsonl  # noqa: E402
from hz.timeq import now_utc  # noqa: E402

from CONNECTORS.scholarly import _util as U  # noqa: E402

SOURCE_ID = "crossref"
BASE = "https://api.crossref.org/works"
LICENCE_STATUS = "open_no_explicit_licence"
LICENCE_NOTE = (
    "Crossref makes metadata openly available and asks only that the "
    "'mailto'/'User-Agent' contact be supplied for the polite pool; there is no "
    "single blanket reuse licence on the metadata itself. Crossref's terms "
    "(https://www.crossref.org/operations-and-sustainability/accessibility/) do "
    "not grant an explicit content licence, so this is recorded as "
    "open_no_explicit_licence rather than open_licence. The per-record "
    "`license[]` array is preserved in attributes for downstream filtering."
)


def fetch_one(client, doi: str, name: str) -> dict | None:
    url = f"{BASE}/{doi}"
    res = client.get(url, headers={"User-Agent": U.USER_AGENT})
    prov = U.save_fetch(SOURCE_ID, name, res, note=f"EXP-H1 anchor doi={doi}")
    prov["doi"] = doi
    if not res.ok:
        return {"doi": doi, "status": res.status, "raw": prov["path"], "record": None}
    try:
        doc = res.json()
    except Exception:
        return {"doi": doi, "status": res.status, "raw": prov["path"], "record": None}
    return {"doi": doi, "status": res.status, "raw": prov["path"], "record": doc.get("message")}


def collect() -> dict:
    dois = U.anchor_dois()
    out = []
    with U.make_client(
        "scholarly_crossref", max_requests=len(dois) + 4,
        max_bytes_per_response=4_000_000, max_total_bytes=24_000_000, rps=2.0,
    ) as client:
        for i, doi in enumerate(dois, 1):
            name = f"works_{i:02d}.json"
            try:
                r = fetch_one(client, doi, name)
            except Exception as exc:
                r = {"doi": doi, "status": None, "error": f"{type(exc).__name__}: {exc}"[:200],
                     "raw": None, "record": None}
            out.append(r)
            if i % 10 == 0:
                print(f"    crossref {i}/{len(dois)}")
        budget = client.budget_report()
    doc = {
        "source_id": SOURCE_ID, "generated_at": now_utc(), "endpoint": BASE,
        "anchor_count": len(dois),
        "found": sum(1 for r in out if r.get("record")),
        "absent": sum(1 for r in out if r.get("status") == 404),
        "errors": sum(1 for r in out if not r.get("record") and r.get("status") not in (404,)),
        "budget": budget, "results": out,
    }
    U.write_json(os.path.join(U.DATASETS, SOURCE_ID, "CROSSREF_INDEX.json"), doc)
    print("  budget:", budget)
    print(f"  found={doc['found']} absent={doc['absent']} errors={doc['errors']}")
    return doc


def _date_parts(obj) -> str | None:
    if not isinstance(obj, dict):
        return None
    parts = obj.get("date-parts") or []
    if not parts or not parts[0]:
        return None
    p = list(parts[0]) + [1, 1]
    try:
        return f"{int(p[0]):04d}-{int(p[1]):02d}-{int(p[2]):02d}"
    except (TypeError, ValueError):
        return None


def _created(o) -> str | None:
    if not isinstance(o, dict):
        return None
    dt = o.get("date-time")
    if isinstance(dt, str) and len(dt) >= 10:
        return dt[:10]
    return _date_parts(o)


def parse(index: dict | None = None) -> list:
    idx = index or U.read_json(os.path.join(U.DATASETS, SOURCE_ID, "CROSSREF_INDEX.json"))
    fetched_at = now_utc()
    recs = []
    for r in idx["results"]:
        m = r.get("record")
        if not m:
            continue
        doi = U.norm_doi(m.get("DOI") or r.get("doi"))
        title = U.norm_ws((m.get("title") or [""])[0])
        authors = m.get("author") or []
        funders = []
        for f in (m.get("funder") or []):
            funders.append({
                "name": f.get("name"),
                "doi": f.get("DOI"),
                "awards": f.get("award") or [],
            })
        issued = _date_parts(m.get("issued")) or _date_parts(m.get("published"))
        identifiers = [{"scheme": "doi", "value": doi, "issuing_authority": "Crossref",
                        "is_primary": True}] if doi else []
        flags = []
        if not issued:
            flags.append("MISSING_PUBLICATION_DATE")
        if not identifiers:
            flags.append("MISSING_IDENTIFIER")
        recs.append(build_record(
            source_id=SOURCE_ID,
            source_record_id=doi or "",
            entity_type="publication",
            original_name=title or doi or "",
            identifiers=identifiers,
            attributes={
                "title": title,
                "subtitle": m.get("subtitle"),
                "container_title": m.get("container-title"),
                "publisher": m.get("publisher"),
                "type": m.get("type"),
                "author_count": len(authors),
                "first_author_family": ((authors[0] or {}).get("family") if authors else None),
                "last_author_family": ((authors[-1] or {}).get("family") if authors else None),
                "dates": {
                    "created": _created(m.get("created")),
                    "created_datetime": (m.get("created") or {}).get("date-time"),
                    "deposited": _created(m.get("deposited")),
                    "indexed": _created(m.get("indexed")),
                    "issued": _date_parts(m.get("issued")),
                    "published": _date_parts(m.get("published")),
                    "published_print": _date_parts(m.get("published-print")),
                    "published_online": _date_parts(m.get("published-online")),
                },
                "alternative_ids": m.get("alternative-id"),
                "relation": m.get("relation"),
                "funders": funders,
                "licenses": m.get("license"),
                "reference_count": m.get("references-count"),
            },
            event_at=issued,
            source_public_at=_created(m.get("created")) or issued,
            first_observed_at=_created(m.get("created")),
            fetched_at=fetched_at,
            source_url=f"https://api.crossref.org/works/{doi}" if doi else "",
            licence_status=LICENCE_STATUS,
            licence_note=LICENCE_NOTE,
            identity_status="UNKNOWN",
            evidence_status="CANDIDATE",
            quality_flags=flags,
            notes=(
                "source_public_at uses Crossref `created` (the deposit timestamp) where "
                "present: that is when the record became visible through Crossref, NOT "
                "the publication date."
            ),
        ))
    return recs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parse", action="store_true")
    args = ap.parse_args(argv)
    idx_path = os.path.join(U.DATASETS, SOURCE_ID, "CROSSREF_INDEX.json")
    idx = U.read_json(idx_path) if args.parse else collect()
    out = os.path.join(U.DATASETS, SOURCE_ID, "records.jsonl")
    n = write_jsonl(out, parse(idx))
    print(f"  {n} records -> {U.rel(out)}")
    U.write_provenance(
        SOURCE_ID,
        [{"path": r["raw"], "doi": r["doi"], "status": r["status"]}
         for r in idx["results"] if r.get("raw")],
        extra={
            "endpoint": BASE,
            "rate_policy": "polite pool via User-Agent contact; no explicit rate limit documented",
            "licence_status": LICENCE_STATUS,
            "licence_note": LICENCE_NOTE,
            "index_file": U.rel(idx_path),
            "records_file": U.rel(out),
            "record_count": n,
            "found": idx.get("found"),
            "absent_404": idx.get("absent"),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
