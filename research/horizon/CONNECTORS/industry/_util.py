"""Shared helpers for the INDUSTRY / TRADE / PROCUREMENT connectors.

Non-negotiable rules enforced here rather than documented:

* raw evidence is stored byte-for-byte and described by ``PROVENANCE.json`` so a
  third party can re-fetch and re-hash it;
* every request — GET *and* POST — lands in
  ``SOURCE_PROBES/industry/REQUEST_LOG.jsonl``; POST calls are logged manually
  because ``hz.http.BoundedClient`` is GET-only by contract;
* HS scope is always carried in the record itself, never only in a report;
* a trade flow record states, in its own attributes, that it is an aggregate
  that identifies no firm.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

import requests

from hz.http import BoundedClient, DEFAULT_UA

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # research/horizon
DATASETS = os.path.join(ROOT, "DATASETS", "industry")
PROBE_LOG = os.path.join(ROOT, "SOURCE_PROBES", "industry", "REQUEST_LOG.jsonl")

WORKSTREAM = "industry"


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_client(name: str, *, max_requests: int, max_bytes_per_response: int = 8_000_000,
                max_total_bytes: int = 25_000_000, rps: float = 1.5) -> BoundedClient:
    os.makedirs(os.path.dirname(PROBE_LOG), exist_ok=True)
    return BoundedClient(
        name=name,
        max_requests=max_requests,
        max_bytes_per_response=max_bytes_per_response,
        max_total_bytes=max_total_bytes,
        requests_per_second=rps,
        log_path=PROBE_LOG,
    )


def raw_dir(source_id: str) -> str:
    d = os.path.join(DATASETS, source_id, "raw")
    os.makedirs(d, exist_ok=True)
    return d


def save_raw(source_id: str, name: str, body: bytes, *, requested_url: str,
             final_url: str, status: int, content_type: str | None,
             note: str = "") -> dict[str, Any]:
    """Store bytes verbatim; return the provenance stanza for them."""
    d = raw_dir(source_id)
    path = os.path.join(d, name)
    with open(path, "wb") as fh:
        fh.write(body)
    return {
        "path": os.path.relpath(path, ROOT).replace(os.sep, "/"),
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "requested_url": requested_url,
        "final_url": final_url,
        "status": status,
        "content_type": content_type,
        "fetched_at": utc_now(),
        "note": note,
    }


def save_fetch(source_id: str, name: str, res, *, note: str = "") -> dict[str, Any]:
    return save_raw(
        source_id, name, res.body,
        requested_url=res.url, final_url=res.final_url, status=res.status,
        content_type=res.headers.get("content-type"), note=note,
    )


def post_json(source_id: str, url: str, payload: dict[str, Any], *,
              name: str, note: str = "", timeout_s: float = 60.0) -> tuple[dict[str, Any], Any]:
    """POST JSON, log it manually, save the response verbatim.

    Returns ``(provenance, parsed_json)``. Raises on transport failure; a
    non-2xx response is returned (not raised) so the caller can record the
    failure as evidence.
    """
    session = requests.Session()
    session.headers.update(
        {"User-Agent": DEFAULT_UA, "Content-Type": "application/json", "Accept": "application/json"}
    )
    started = time.monotonic()
    resp = session.post(url, json=payload, timeout=timeout_s)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    body = resp.content
    session.close()

    body_meta = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    entry = {
        "client": f"{WORKSTREAM}_{source_id}",
        "method": "POST",
        "url": url,
        "status": resp.status_code,
        "outcome": "OK" if 200 <= resp.status_code < 300 else "HTTP_ERROR",
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "request_body_sha256": hashlib.sha256(body_meta.encode("utf-8")).hexdigest(),
        "request_body_bytes": len(body_meta.encode("utf-8")),
        "elapsed_ms": elapsed_ms,
        "logged_at": utc_now(),
        "note": note,
    }
    os.makedirs(os.path.dirname(PROBE_LOG), exist_ok=True)
    with open(PROBE_LOG, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    prov = save_raw(
        source_id, name, body,
        requested_url=url, final_url=resp.url, status=resp.status_code,
        content_type=resp.headers.get("content-type"),
        note=note or "POST " + body_meta[:200],
    )
    try:
        parsed = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        parsed = None
    return prov, parsed


def write_provenance(source_id: str, records: list[dict[str, Any]],
                     extra: dict[str, Any] | None = None) -> str:
    d = os.path.join(DATASETS, source_id)
    os.makedirs(d, exist_ok=True)
    doc: dict[str, Any] = {
        "source_id": source_id,
        "workstream": WORKSTREAM,
        "generated_at": utc_now(),
        "raw_files": records,
        "aggregation_disclaimer": (
            "Trade-flow records are national/regional aggregates. They carry no "
            "firm-level revenue, R&D or market-share attribution. Procurement "
            "records name a recipient as published by the awarding body; they do "
            "not identify the manufacturer of any device unless the award text "
            "names a concrete device or model."
        ),
    }
    if extra:
        doc.update(extra)
    path = os.path.join(d, "PROVENANCE.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def write_json(source_id: str, name: str, doc: Any) -> str:
    d = os.path.join(DATASETS, source_id)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def evidence_dir() -> str:
    d = os.path.join(ROOT, "experiments", WORKSTREAM, "evidence")
    os.makedirs(d, exist_ok=True)
    return d


def write_records(source_id: str, records: list) -> str:
    """Write ``horizon.evidence.v1`` JSONL for one source."""
    from hz.schema import write_jsonl

    d = evidence_dir()
    path = os.path.join(d, f"{source_id}.jsonl")
    n = write_jsonl(path, records)
    return path if n >= 0 else path


def ascii_safe(v: Any) -> str:
    return "" if v is None else str(v).strip()
