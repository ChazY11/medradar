"""Snapshot the technology map so the page can answer in milliseconds.

Why a snapshot
--------------
The map page called `/api/radar/technology-map` in-process. Measured on the production graph
(122,849 nodes, 107,115 edges): the first call after a restart took longer than two minutes, and a
page that makes a reader wait two minutes is not a page. The answer itself changes at most once per
scheduler cycle (300 s), so computing it per request is also simply wasted work.

This writes the payload to a file; the page reads the file. Refreshed by the nightly job.

    python3 tools/build_map.py --out /srv/medradar/data/radar/map_page.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_OUT = "/srv/medradar/data/radar/map_page.json"
DEFAULT_RADAR = "/srv/medradar/data/radar"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--radar", default=DEFAULT_RADAR)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--max-products", type=int, default=8)
    parser.add_argument("--max-evidence", type=int, default=3)
    parser.add_argument("--timeout-note", default="")
    args = parser.parse_args()

    from medradar.radar.api import RadarService, build_router

    service = RadarService(args.radar)
    endpoints = {route.path: route.endpoint for route in build_router(service).routes}
    endpoint = endpoints.get("/api/radar/technology-map")
    if endpoint is None:
        print("the technology-map endpoint is not registered", file=sys.stderr)
        return 2
    payload = endpoint(mode="public", max_products=args.max_products,
                       max_evidence=args.max_evidence,
                       product_offset=0, evidence_offset=0)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    # Atomic replace: a reader must never see half a snapshot.
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out)
    topics = len(payload.get("topics") or [])
    print(json.dumps({"written": str(out), "topics": topics,
                      "bytes": out.stat().st_size}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
