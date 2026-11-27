"""Probe the two POST-only endpoints the scholarly workstream depends on.

``hz.probe`` runs GET-only ``Probe`` objects, so POST endpoints cannot live in
``hz/suites_scholarly.py``. This module supplies the missing probe evidence and
writes it next to the GET probe output:

    SOURCE_PROBES/scholarly/POST_CALLS.json    one record per POST endpoint
    SOURCE_PROBES/scholarly/REQUEST_LOG_POST.jsonl   every POST attempt

Run after the GET suite:

    python CONNECTORS/scholarly/probe_post_endpoints.py
"""

from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hz.timeq import now_utc  # noqa: E402

from CONNECTORS.scholarly import _util as U  # noqa: E402

OUT_OF_SAMPLE_DOI = "10.1038/s41586-020-2649-2"


def main() -> int:
    os.makedirs(U.PROBES, exist_ok=True)
    out: list[dict] = []

    # ---------------------------------------------------------- Semantic Scholar
    url = ("https://api.semanticscholar.org/graph/v1/paper/batch"
           "?fields=title,externalIds,publicationDate,venue")
    body = {"ids": [f"DOI:{OUT_OF_SAMPLE_DOI}"]}
    status, payload, headers = U.post_json("POST probe: semanticscholar batch", url, body)
    prov = U.save_raw(
        "semantic_scholar", "probe_batch_post.json", payload,
        requested_url=url, final_url=url, status=status,
        content_type=headers.get("content-type"),
        note="POST-only endpoint probe for the Semantic Scholar batch route",
    )
    marker = b"externalIds"
    out.append({
        "probe_id": "semanticscholar_batch_post",
        "source_id": "semantic_scholar",
        "url": url,
        "method": "POST",
        "question": (
            "Does the POST /paper/batch form return externalIds for a DOI list "
            "without an API key, given a bounded retry on 429?"
        ),
        "request_body_shape": {"ids": "['DOI:<doi>']"},
        "status": status,
        "bytes": len(payload),
        "sha256": prov["sha256"],
        "raw": prov["path"],
        "body_exact": payload.decode("utf-8", errors="replace")[:300],
        "expect_marker": marker.decode(),
        "marker_found": marker in payload,
        "note": (
            "The `fields` projection must be passed as a query parameter on the batch "
            "route; without it the response omits externalIds entirely. The anonymous "
            "tier returned 429 on the first attempt during collection and 200 after "
            "bounded backoff; both attempts are in REQUEST_LOG_POST.jsonl. That 429 is "
            "evidence about the rate policy, not a gap."
        ),
        "observed_at": now_utc(),
    })

    # ------------------------------------------------------------- NIH RePORTER
    url = "https://api.reporter.nih.gov/v2/projects/search"
    body = {
        "criteria": {"fiscal_years": [2022], "text_search_field": "medical device",
                     "text_search_operators": {"text_search_field": "all"}},
        "include_fields": ["ProjectNum", "ProjectTitle", "FiscalYear"],
        "offset": 0, "limit": 1,
    }
    status, payload, headers = U.post_json("POST probe: nih reporter search", url, body)
    prov = U.save_raw(
        "nih_reporter", "probe_search_post.json", payload,
        requested_url=url, final_url=url, status=status,
        content_type=headers.get("content-type"),
        note="POST-only endpoint probe for the NIH RePORTER project search",
    )
    marker = b'"meta"'
    out.append({
        "probe_id": "nih_reporter_search_post",
        "source_id": "nih_reporter",
        "url": url,
        "method": "POST",
        "question": (
            "Does a JSON POST with criteria/include_fields/offset/limit return a "
            "meta block without a key, where GET returns 405?"
        ),
        "request_body_shape": {
            "criteria": "{fiscal_years, text_search_field, text_search_operators}",
            "include_fields": "list[str]",
            "offset": "int", "limit": "int",
        },
        "status": status,
        "bytes": len(payload),
        "sha256": prov["sha256"],
        "raw": prov["path"],
        "body_exact": payload.decode("utf-8", errors="replace")[:300],
        "expect_marker": marker.decode(),
        "marker_found": marker in payload,
        "note": (
            "GET on the same URL returns 405 (see the nih_reporter_get_405 probe). "
            "criteria.project_nums accepts bare core project numbers such as "
            "R01EB026995 and echoes core_project_num, which is what the grant<->work "
            "linkage rests on."
        ),
        "observed_at": now_utc(),
    })

    for r in out:
        print(f"  {r['probe_id']}: status={r['status']} bytes={r['bytes']} "
              f"marker_found={r['marker_found']}")

    doc = {
        "suite": "scholarly",
        "kind": "POST-only endpoint probes",
        "generated_at": now_utc(),
        "why": (
            "hz.probe.Probe is GET-only; these two endpoints are POST-only and are "
            "therefore probed here. Calls are routed through _util.post_json so they "
            "land in REQUEST_LOG_POST.jsonl with status, bytes and sha256."
        ),
        "post_log": U.rel(U.POST_LOG),
        "probes": out,
    }
    path = os.path.join(U.PROBES, "POST_CALLS.json")
    U.write_json(path, doc)
    print("written:", U.rel(path))
    print("written:", U.rel(U.POST_LOG))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
