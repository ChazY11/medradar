"""Step 3 — finalise patent records without re-fetching.

Two corrections that must be applied to the raw server output before it becomes
an evidence asset, and that are cheaper and safer to apply offline than by
re-hitting the source:

1. **Document role.** EP publication kinds are not interchangeable:
   ``A1``/``A2`` = application with/without search report (a technical
   disclosure), ``A3`` = search report published *separately* for an earlier
   application (NOT a new disclosure), ``B1``/``B2`` = granted specification,
   ``B8``/``B9`` = corrected title page / corrected specification.
   Treating an A3 as an independent publication inflates the corpus and
   double-counts the same technical content. Every record therefore gets a
   ``document_role``, and A3/B8 get an explicit quality flag.

2. **Content hash.** Adding an attribute changes the canonical content key, so the
   hash is recomputed rather than left stale.

    python tools/finalize_patent_records.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from hz.schema import SCHEMA_VERSION, dedupe_key, read_jsonl  # noqa: E402
from hz.timeq import now_utc  # noqa: E402

import hashlib  # noqa: E402

EPO_RAW = os.path.join(ROOT, "DATASETS", "patents", "epo_publication_server", "RECORDS.raw.jsonl")
EPO_OUT = os.path.join(ROOT, "DATASETS", "patents", "epo_publication_server", "RECORDS.jsonl")
CIPO_RAW = os.path.join(ROOT, "DATASETS", "patents", "cipo_canada", "RECORDS.raw.jsonl")
CIPO_OUT = os.path.join(ROOT, "DATASETS", "patents", "cipo_canada", "RECORDS.jsonl")

ROLE_BY_KIND = {
    "A1": ("application_publication", True),
    "A2": ("application_publication_no_search_report", True),
    "A3": ("search_report", False),
    "A4": ("supplementary_search_report", False),
    "B1": ("granted_specification", True),
    "B2": ("granted_specification_amended", True),
    "B3": ("granted_specification_limited", True),
    "B8": ("corrected_title_page", False),
    "B9": ("corrected_specification", False),
}


def _rehash(rec: dict) -> str:
    key = {
        "schema_version": rec["schema_version"],
        "source_id": rec["source_id"],
        "source_record_id": rec["source_record_id"],
        "entity_type": rec["entity_type"],
        "original_name": rec["original_name"],
        "identifiers": sorted(
            ({"scheme": i["scheme"], "value": i["value"]} for i in rec.get("identifiers", [])),
            key=lambda d: (d["scheme"], d["value"]),
        ),
        "manufacturer": rec.get("manufacturer"),
        "attributes": rec.get("attributes") or {},
        "event_at": rec.get("event_at"),
        "source_public_at": rec.get("source_public_at"),
        "source_url": rec.get("source_url"),
    }
    payload = json.dumps(key, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def finalize_epo() -> dict:
    recs = read_jsonl(EPO_RAW)
    roles = Counter()
    for r in recs:
        kind = ((r.get("attributes") or {}).get("kind") or "").upper()
        role, is_disclosure = ROLE_BY_KIND.get(kind, ("unknown_kind", None))
        r["attributes"]["document_role"] = role
        r["attributes"]["is_independent_disclosure"] = is_disclosure
        roles[role] += 1
        flags = set(r.get("quality_flags") or [])
        if kind == "A3" or kind == "A4":
            flags.add("DOCUMENT_IS_SEARCH_REPORT")
        if kind in ("B8", "B9"):
            flags.add("DOCUMENT_IS_CORRECTION")
        r["quality_flags"] = sorted(flags)
        r["content_hash"] = _rehash(r)
    with open(EPO_OUT, "w", encoding="utf-8", newline="\n") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_indep = sum(1 for r in recs if r["attributes"]["is_independent_disclosure"])
    return {
        "source_id": "epo_publication_server",
        "records": len(recs),
        "independent_disclosures": n_indep,
        "by_document_role": dict(sorted(roles.items())),
        "unique_dedupe_keys": len({dedupe_key(r) for r in recs}),
        "finalized_at": now_utc(),
    }


def finalize_cipo() -> dict:
    if not os.path.isfile(CIPO_RAW):
        return {"source_id": "cipo_canada", "records": 0, "note": "no raw records yet"}
    recs = read_jsonl(CIPO_RAW)
    for r in recs:
        r["attributes"]["document_role"] = "granted_or_published_patent"
        r["attributes"]["is_independent_disclosure"] = True
        flags = set(r.get("quality_flags") or [])
        if r.get("identity_status") == "CANDIDATE":
            flags.add("NAME_MATCH_ONLY")
        r["quality_flags"] = sorted(flags)
        r["content_hash"] = _rehash(r)
    with open(CIPO_OUT, "w", encoding="utf-8", newline="\n") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {
        "source_id": "cipo_canada",
        "records": len(recs),
        "unique_dedupe_keys": len({dedupe_key(r) for r in recs}),
        "finalized_at": now_utc(),
    }


def main() -> int:
    out = {"schema_version": SCHEMA_VERSION, "epo": finalize_epo()}
    out["cipo"] = finalize_cipo()
    print(json.dumps(out, indent=2, ensure_ascii=False))
    with open(
        os.path.join(ROOT, "DATASETS", "patents", "FINALIZE_SUMMARY.json"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
