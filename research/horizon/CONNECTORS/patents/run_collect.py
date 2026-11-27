"""Run the bounded EPO patent collection and write raw evidence + records.

Usage (from research/horizon):
    python CONNECTORS/patents/run_collect.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # research/horizon
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import epo_publication_server as E                     # noqa: E402
from hz.schema import write_jsonl                      # noqa: E402

OUT_DIR = os.path.join(ROOT, "DATASETS", "patents", "epo_publication_server")
LOG = os.path.join(OUT_DIR, "REQUEST_LOG.jsonl")

WEEKS = [
    "2005-06-01",
    "2010-01-13",
    "2013-05-08",
    "2016-09-07",
    "2019-03-06",
    "2021-11-10",
    "2023-03-08",
    "2024-06-05",
    "2025-01-08",
    "2026-06-03",
]
DENSE = {"2025-01-08": 90, "2024-06-05": 90}


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(LOG):
        os.remove(LOG)
    res = E.collect(
        weeks_wanted=WEEKS,
        max_weeks=len(WEEKS),
        max_front_pages=235,
        max_requests=300,
        max_total_bytes=95_000_000,
        week_caps=DENSE,
        sparse_per_week=6,
        out_dir=OUT_DIR,
        log_path=LOG,
    )
    recs = res["records"]
    write_jsonl(os.path.join(OUT_DIR, "RECORDS.raw.jsonl"), recs)
    prov = {
        "source_id": E.SOURCE_ID,
        "licence_status": E.LICENCE_STATUS,
        "licence_url": E.LICENCE_URL,
        "robots_url": E.ROBOTS_URL,
        "sitemap_index": E.SITEMAP_INDEX,
        "generated_at": res["generated_at"],
        "weeks_used": res["weeks_used"],
        "publication_refs_considered": res["publication_refs_considered"],
        "front_pages_attempted": res["front_pages_attempted"],
        "records": len(recs),
        "budget": res["budget"],
        "access_note": (
            "No credential used. Sitemap index is advertised in the operator's own "
            "robots.txt. Bounded sample: 10 weekly sitemaps, <=235 front pages. "
            "No crawling, no index construction, no mirroring."
        ),
    }
    with open(os.path.join(OUT_DIR, "PROVENANCE.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(prov, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(json.dumps({k: prov[k] for k in ("records", "publication_refs_considered", "front_pages_attempted")}, indent=2))
    print("budget:", json.dumps(res["budget"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
