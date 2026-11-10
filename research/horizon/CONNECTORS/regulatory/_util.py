"""Shared helpers for the REGULATORY workstream connectors.

Everything here exists to enforce two rules mechanically:

* every byte we keep is exactly the bytes the server sent (no reformatting),
  plus a PROVENANCE.json that lets a third party re-hash and re-fetch it;
* every request goes through ``hz.http.BoundedClient`` so the budget is
  auditable in ``SOURCE_PROBES/regulatory/REQUEST_LOG.jsonl``.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

from hz.http import BoundedClient

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # research/horizon

DATASETS = os.path.join(ROOT, "DATASETS", "regulatory")
PROBE_LOG = os.path.join(ROOT, "SOURCE_PROBES", "regulatory", "REQUEST_LOG.jsonl")
FETCHED_AT = ""


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_client(name: str, *, max_requests: int, max_bytes_per_response: int = 8_000_000,
                max_total_bytes: int = 30_000_000, rps: float = 1.5) -> BoundedClient:
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


def save_raw(source_id: str, name: str, res, *, url_note: str = "") -> dict[str, Any]:
    """Store a response verbatim and return its provenance record."""
    d = raw_dir(source_id)
    path = os.path.join(d, name)
    with open(path, "wb") as fh:
        fh.write(res.body)
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    rec = {
        "path": rel,
        "bytes": len(res.body),
        "sha256": hashlib.sha256(res.body).hexdigest(),
        "requested_url": res.url,
        "final_url": res.final_url,
        "status": res.status,
        "content_type": res.headers.get("content-type"),
        "fetched_at": utc_now(),
        "note": url_note,
    }
    return rec


def write_provenance(source_id: str, records: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> str:
    d = os.path.join(DATASETS, source_id)
    os.makedirs(d, exist_ok=True)
    doc = {
        "source_id": source_id,
        "workstream": "regulatory",
        "generated_at": utc_now(),
        "raw_files": records,
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


def fetch_or_load(client: BoundedClient, source_id: str, name: str, url: str,
                  note: str = "") -> tuple[dict[str, Any], bytes]:
    """Return (provenance, body) — reusing the on-disk raw copy when present.

    Re-running a connector must not re-spend the network budget, and the raw
    bytes on disk are already the verbatim response with a recorded sha256.
    """
    path = os.path.join(DATASETS, source_id, "raw", name)
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            body = fh.read()
        return (
            {
                "path": os.path.relpath(path, ROOT).replace(os.sep, "/"),
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                "requested_url": url,
                "final_url": url,
                "status": 200,
                "content_type": None,
                "fetched_at": utc_now(),
                "note": note + " [loaded from disk; original fetch is in REQUEST_LOG.jsonl]",
                "from_disk": True,
            },
            body,
        )
    res = client.get(url)
    return save_raw(source_id, name, res, url_note=note), res.body


def probe_size(client: BoundedClient, url: str) -> dict[str, Any]:
    """Ask for 1 KiB via Range and report the total size — costs one request.

    A server that ignores Range answers 200 with the whole body, which the
    client's byte cap turns into ResponseTooLarge; that outcome is recorded as
    "size unknown / range unsupported" rather than guessed.
    """
    out: dict[str, Any] = {"url": url}
    try:
        res = client.get(url, headers={"Range": "bytes=0-1023"})
    except Exception as exc:  # noqa: BLE001
        out["outcome"] = type(exc).__name__
        out["error"] = str(exc)[:200]
        return out
    out["status"] = res.status
    out["bytes_read"] = len(res.body)
    cr = res.headers.get("content-range")
    out["content_range"] = cr
    if cr and "/" in cr:
        try:
            out["total_bytes"] = int(cr.rsplit("/", 1)[1])
        except ValueError:
            out["total_bytes"] = None
    else:
        out["total_bytes"] = None
    out["accept_ranges"] = res.headers.get("accept-ranges")
    return out


def ascii_safe(s: Any) -> str:
    return "" if s is None else str(s).strip()


def first_present(d: dict, keys: list[str]) -> Any:
    """Return the first non-empty value among ``keys``; never invent one."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return None
