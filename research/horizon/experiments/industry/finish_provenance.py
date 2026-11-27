"""Fill in ``DATASETS/industry/<source_id>/PROVENANCE.json`` for every source.

The six collecting sources write their own PROVENANCE.json from the connector
(it records the request URLs and the coverage limits). The remaining sources
yielded no records — four are paywalled/terms-blocked, one is keyed, one has no
machine interface — but they still have raw bytes on disk (robots.txt, terms
pages, docs pages). This module hashes those files and states explicitly that
the record count is zero and why, so "no data" can never be mistaken for
"not attempted".

Run:

    python experiments/industry/finish_provenance.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

DATASETS = os.path.join(ROOT, "DATASETS", "industry")
NOW = __import__("hz.timeq", fromlist=["now_utc"]).now_utc()

#: Why each source produced no records. Kept here so the reason travels with the
#: directory instead of living only in a report.
NO_RECORDS_REASON = {
    "us_census_trade": (
        "REQUIRES_REGISTRATION: the HS time-series endpoint answers HTTP 200 but "
        "redirects to /data/missing_key.html. Only the keyless variable dictionary "
        "was stored. No trade values were collected."
    ),
    "sam_gov": (
        "REQUIRES_REGISTRATION: api.sam.gov returns HTTP 404 with a zero-byte body "
        "for its documented paths; the open.gsa.gov docs page states that an "
        "individual account and API key are required. No entity data was collected."
    ),
    "usitc_dataweb": (
        "BLOCKED_TECHNICAL: the site is a JavaScript single-page app with no "
        "documented public API; /login returns the identical shell. No data was "
        "collected."
    ),
    "importyeti": (
        "BLOCKED_LEGAL: robots.txt allows pages but disallows /api/addresses and "
        "/api/ep, which are the data endpoints. No shipment data was collected."
    ),
    "importgenius": (
        "BLOCKED_LEGAL / REQUIRES_LICENCE: the terms of use prohibit reuse of "
        "Content and the data API is enterprise-licensed. No data was collected."
    ),
    "panjiva": (
        "REQUIRES_LICENCE: commercial S&P Global platform; the terms page returns "
        "HTTP 403 to an automated client, so the licence text is unverified. No "
        "data was collected."
    ),
    "descartes_datamyne": (
        "REQUIRES_LICENCE: governed by Online Subscription Terms / EULA. No data "
        "was collected."
    ),
}


def sha256_file(path: str) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def main() -> int:
    written = 0
    for source_id in sorted(os.listdir(DATASETS)):
        d = os.path.join(DATASETS, source_id)
        if not os.path.isdir(d):
            continue
        prov_path = os.path.join(d, "PROVENANCE.json")
        if os.path.isfile(prov_path):
            continue
        raw = os.path.join(d, "raw")
        files = []
        if os.path.isdir(raw):
            for fn in sorted(os.listdir(raw)):
                p = os.path.join(raw, fn)
                if not os.path.isfile(p):
                    continue
                digest, size = sha256_file(p)
                files.append({
                    "path": os.path.relpath(p, ROOT).replace(os.sep, "/"),
                    "bytes": size,
                    "sha256": digest,
                    "note": "supporting page retained verbatim (no records from this source)",
                })
        doc = {
            "source_id": source_id,
            "workstream": "industry",
            "generated_at": NOW,
            "records_collected": 0,
            "raw_files": files,
            "why_zero_records": NO_RECORDS_REASON.get(
                source_id, "no records were produced by this source"
            ),
            "aggregation_disclaimer": (
                "Trade-flow records are national/regional aggregates and carry no "
                "firm-level attribution. Procurement records name a supplier as "
                "published by the awarding body; they do not identify the "
                "manufacturer of any device."
            ),
        }
        with open(prov_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        written += 1
        print(f"wrote {prov_path} ({len(files)} raw files, 0 records)")
    print(f"{written} provenance files written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
