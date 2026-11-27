"""EU CTIS connector — a recorded BLOCKED outcome, not a stub.

Established by probe (``SOURCE_PROBES/scholarly/PROBES.json``):

* ``GET https://euclinicaltrials.eu/ctis-public-api/search?...`` -> **HTTP 403**,
  body exactly ``{"message":"Missing Authentication Token"}``. That is an AWS API
  Gateway authorizer response: the route exists but requires a credential.
  Re-sending with a dummy ``X-API-KEY`` header returned the same 403, so it is not
  a simple shared key.
* ``GET .../retrieve/<CT number>`` -> **HTTP 200 with a 2-byte ``{}`` body**. A
  success status carrying no record: the exact shape that a naive connector
  reports as "found".
* ``GET .../api-docs`` -> the 66 KB single-page-application HTML shell, not an
  OpenAPI document, so the contract is not discoverable from the site.

Because CTIS is the EU's trial registry and ``eu_ctis`` is in this workstream's
source list, the honest deliverable is: ACCESS attempted, BLOCKED at the
credential gate, blocker recorded with exact HTTP evidence, unlock route named.
No trial record is emitted, because none was received.

    python CONNECTORS/scholarly/eu_ctis.py
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hz.timeq import now_utc  # noqa: E402

from CONNECTORS.scholarly import _util as U  # noqa: E402

SOURCE_ID = "eu_ctis"
BASE = "https://euclinicaltrials.eu/ctis-public-api"
LICENCE_STATUS = "unknown"
LICENCE_NOTE = (
    "No reuse licence could be established: the public API returned 403 before any "
    "content was served, and the site's api-docs path serves the application shell "
    "rather than a contract. Recorded as unknown rather than assumed permissive."
)
UNLOCK_ROUTE = (
    "Register for CTIS public-API access with EMA: the CTIS public website "
    "(https://euclinicaltrials.eu/) documents a public API whose search route is "
    "behind an AWS API Gateway authorizer. Request credentials through the EMA "
    "CTIS service desk / the 'CTIS for sponsors and authorities' contact route at "
    "https://euclinicaltrials.eu/contact/ ; there is no anonymous tier. "
    "Alternative with no credential: ClinicalTrials.gov API v2 (already used) and "
    "the EU CTR results summary on the CTIS public web pages."
)


def probe_blocker() -> dict:
    attempts = []
    with U.make_client(
        "scholarly_ctis", max_requests=4,
        max_bytes_per_response=1_000_000, max_total_bytes=3_000_000, rps=1.0,
    ) as client:
        targets = [
            ("search", BASE + "/search?" + urllib.parse.urlencode(
                {"pagination.page": 1, "pagination.size": 5}),
             "anonymous search - expected 403 AWS authorizer"),
            # NOTE: the URL must differ from the previous one. BoundedClient
            # memoises on (url, params) and headers are NOT part of the cache key,
            # so reusing the same URL with only an extra header would be served from
            # cache and would prove nothing about the header. A different page size
            # makes this a genuinely independent request to the same route.
            ("search_with_dummy_key", BASE + "/search?" + urllib.parse.urlencode(
                {"pagination.page": 2, "pagination.size": 6}),
             "same route, different params, plus a dummy X-API-KEY header: tests "
             "whether the gate is a shared static key"),
            ("retrieve", BASE + "/retrieve/2024-511234-12-00",
             "detail route - tests whether a 200 means data"),
        ]
        for i, (name, url, why) in enumerate(targets, 1):
            headers = {"X-API-KEY": "test"} if name.endswith("dummy_key") else None
            try:
                res = client.get(url, headers=headers)
            except Exception as exc:
                attempts.append({"name": name, "error": f"{type(exc).__name__}: {exc}"[:200]})
                continue
            prov = U.save_fetch(SOURCE_ID, f"probe_{i:02d}_{name}.json", res, note=why)
            body = res.text()
            attempts.append({
                "name": name, "why": why, "url": url,
                "status": res.status, "bytes": len(res.body),
                "body_exact": body if len(body) <= 200 else body[:200],
                "raw": prov["path"], "sha256": prov["sha256"],
            })
            print(f"    ctis {name}: status={res.status} bytes={len(res.body)} "
                  f"body={body[:80]!r}")
        budget = client.budget_report()
    return {"attempts": attempts, "budget": budget,
            "unlock_route": UNLOCK_ROUTE}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parse", action="store_true")
    args = ap.parse_args(argv)
    idx_path = os.path.join(U.DATASETS, SOURCE_ID, "CTIS_BLOCKER.json")
    if args.parse and os.path.isfile(idx_path):
        doc = U.read_json(idx_path)
    else:
        print("probing the EU CTIS public API gate...")
        doc = {
            "source_id": SOURCE_ID, "generated_at": now_utc(),
            "endpoint": BASE, "access_state": "BLOCKED_TECHNICAL",
            "reason": "AWS API Gateway authorizer rejects anonymous requests with "
                      "HTTP 403 {'message':'Missing Authentication Token'}",
            "auth_required": True,
            "licence_status": LICENCE_STATUS,
            "licence_note": LICENCE_NOTE,
            **probe_blocker(),
        }
        U.write_json(idx_path, doc)
    out = os.path.join(U.DATASETS, SOURCE_ID, "records.jsonl")
    U.write_jsonl(out, [])
    print(f"  0 records -> {U.rel(out)} (no CTIS record was ever received)")
    U.write_provenance(
        SOURCE_ID,
        [{"path": a["raw"], "note": a["why"]} for a in doc["attempts"] if a.get("raw")],
        extra={
            "endpoint": BASE, "access_state": doc["access_state"],
            "auth_required": True, "licence_status": LICENCE_STATUS,
            "licence_note": LICENCE_NOTE,
            "blockers": [doc["reason"]],
            "unlock_route": doc["unlock_route"],
            "records_file": U.rel(out), "record_count": 0,
            "negative_result": (
                "Zero records by design: the API gate returned 403 before serving any "
                "content, and the retrieve route returns HTTP 200 with an empty {} "
                "body. Emitting nothing is the correct outcome."
            ),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
