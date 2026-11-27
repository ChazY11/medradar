"""Shared helpers for the SCHOLARLY workstream connectors.

Three rules are enforced here rather than documented:

1. every kept byte is exactly what the server sent, plus a PROVENANCE.json that
   lets a third party re-fetch and re-hash it;
2. every request goes through ``hz.http.BoundedClient`` (or, for the two POST
   endpoints, through a recorded ``requests.post`` call that lands in the same
   JSONL request-log format);
3. a source that returned nothing is recorded as ABSENT with its HTTP evidence,
   never promoted to "not applicable" and never filled in from another source.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

from hz.http import BoundedClient

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # research/horizon
DATASETS = os.path.join(ROOT, "DATASETS", "scholarly")
PROBES = os.path.join(ROOT, "SOURCE_PROBES", "scholarly")
EXPERIMENTS = os.path.join(ROOT, "experiments", "scholarly")
PROBE_LOG = os.path.join(PROBES, "REQUEST_LOG.jsonl")
POST_LOG = os.path.join(PROBES, "REQUEST_LOG_POST.jsonl")

CONTACT = "medradar-research@proton.me"
USER_AGENT = (
    "MedRadar-HORIZON-001/1.0 (academic data-frontier research; bounded sampling; "
    f"contact: {CONTACT})"
)

# ---------------------------------------------------------------- EXP-H1 sample
# Frozen in experiments/scholarly/EXP_H1_SELECTION_RULE.md. Do not edit here
# without amending that document.
FIRMS: list[dict[str, Any]] = [
    {"firm": "Medtronic", "term": "medtronic", "fallback_terms": []},
    {"firm": "GE HealthCare", "term": "ge healthcare", "fallback_terms": ["ge healthcare"]},
    {"firm": "Philips", "term": "philips", "fallback_terms": []},
    {"firm": "Draeger", "term": "dräger", "fallback_terms": ["draeger"]},
    {"firm": "Mindray", "term": "mindray", "fallback_terms": []},
]
PER_FIRM = 12
WINDOW_FROM = "2020-01-01"
WINDOW_TO = "2022-12-31"
TIERS = [
    ("A", ',title_and_abstract.search:"medical device"'),
    ("B", ",title_and_abstract.search:device"),
    ("C", ""),
]
OPENALEX_SELECT = (
    "id,doi,ids,display_name,publication_date,created_date,updated_date,type,"
    "type_crossref,authorships,primary_location,awards,funders"
)


# --------------------------------------------------------------------- plumbing
def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_client(
    name: str,
    *,
    max_requests: int,
    max_bytes_per_response: int = 8_000_000,
    max_total_bytes: int = 24_000_000,
    rps: float = 1.5,
) -> BoundedClient:
    os.makedirs(PROBES, exist_ok=True)
    return BoundedClient(
        name=name,
        user_agent=USER_AGENT,
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


def rel(path: str) -> str:
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def save_raw(source_id: str, name: str, body: bytes, *, requested_url: str,
             final_url: str, status: int, content_type: str | None,
             note: str = "") -> dict[str, Any]:
    """Write a response body verbatim and return its provenance record."""
    path = os.path.join(raw_dir(source_id), name)
    with open(path, "wb") as fh:
        fh.write(body)
    return {
        "path": rel(path),
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
        source_id,
        name,
        res.body,
        requested_url=res.url,
        final_url=res.final_url,
        status=res.status,
        content_type=res.headers.get("content-type"),
        note=note,
    )


def write_provenance(source_id: str, records: list[dict[str, Any]],
                     extra: dict[str, Any] | None = None) -> str:
    d = os.path.join(DATASETS, source_id)
    os.makedirs(d, exist_ok=True)
    doc: dict[str, Any] = {
        "source_id": source_id,
        "workstream": "scholarly",
        "experiment": "EXP-H1 / EXP-H3 (fixed anchor sample)",
        "selection_rule": rel(os.path.join(EXPERIMENTS, "EXP_H1_SELECTION_RULE.md")),
        "contact": CONTACT,
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


def write_json(path: str, doc: Any) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def write_jsonl(path: str, rows: list[dict]) -> int:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------------ POST calls
def post_json(
    label: str,
    url: str,
    body: Any,
    *,
    timeout: float = 45.0,
    extra_headers: dict[str, str] | None = None,
    max_attempts: int = 4,
    max_sleep_s: float = 30.0,
) -> tuple[int, bytes, dict[str, str]]:
    """POST a JSON body and record every attempt in the scholarly POST log.

    ``hz.http.BoundedClient`` is GET-only, and two of the endpoints this
    workstream needs are POST-only (Semantic Scholar batch, NIH RePORTER search).
    The project brief explicitly allows a direct ``requests.post`` for the
    RePORTER call provided the call is recorded; the same recorded wrapper is
    used for both so the budget stays auditable.

    Retries are bounded (``max_attempts``) and only for 429 / 5xx, honouring
    ``Retry-After`` up to ``max_sleep_s``. Every attempt -- including the ones
    that fail -- is appended to the log, so a 429 is evidence rather than a gap.

    Returns ``(status, body_bytes, headers)``. Never raises for an HTTP error
    status: a 4xx/5xx is data about the endpoint, not an exception to swallow.
    """
    import random

    import requests

    os.makedirs(PROBES, exist_ok=True)
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")

    last: tuple[int, bytes, dict[str, str]] | None = None
    for attempt in range(1, max_attempts + 1):
        started = time.monotonic()
        try:
            resp = requests.post(url, data=payload, headers=headers, timeout=timeout)
        except Exception as exc:  # transport
            elapsed_ms = int((time.monotonic() - started) * 1000)
            with open(POST_LOG, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps({
                    "client": "scholarly_post", "label": label, "method": "POST",
                    "url": url, "outcome": "TRANSPORT_ERROR", "attempt": attempt,
                    "error": f"{type(exc).__name__}: {exc}"[:400],
                    "elapsed_ms": elapsed_ms, "fetched_at": utc_now(),
                }, ensure_ascii=False) + "\n")
            if attempt >= max_attempts:
                raise
            time.sleep(min(2.0 ** attempt + random.uniform(0, 0.5), max_sleep_s))
            continue

        elapsed_ms = int((time.monotonic() - started) * 1000)
        hdrs = {k.lower(): v for k, v in resp.headers.items()}
        with open(POST_LOG, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({
                "client": "scholarly_post", "label": label, "method": "POST",
                "url": url, "status": resp.status_code,
                "outcome": "OK" if 200 <= resp.status_code < 300 else "HTTP_ERROR",
                "request_bytes": len(payload), "bytes": len(resp.content),
                "sha256": hashlib.sha256(resp.content).hexdigest(),
                "attempt": attempt, "elapsed_ms": elapsed_ms,
                "retry_after": hdrs.get("retry-after"),
                "fetched_at": utc_now(),
            }, ensure_ascii=False) + "\n")
        last = (resp.status_code, resp.content, hdrs)
        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            if attempt < max_attempts:
                sleep_s = 2.0 ** attempt + random.uniform(0, 0.5)
                ra = hdrs.get("retry-after")
                if ra:
                    try:
                        sleep_s = float(ra)
                    except ValueError:
                        pass
                time.sleep(min(sleep_s, max_sleep_s))
                continue
        return last

    assert last is not None
    return last


def read_raw(source_id: str, name: str) -> Any:
    with open(os.path.join(raw_dir(source_id), name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def raw_text(source_id: str, name: str) -> str:
    with open(os.path.join(raw_dir(source_id), name), "r", encoding="utf-8") as fh:
        return fh.read()


# ----------------------------------------------------------------- identifiers
_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
                 "http://dx.doi.org/", "doi:", "DOI:")


def norm_doi(value: str | None) -> str | None:
    """Casefold a DOI and strip resolvable prefixes. Nothing else is changed."""
    if not value:
        return None
    v = str(value).strip()
    for p in _DOI_PREFIXES:
        if v.lower().startswith(p.lower()):
            v = v[len(p):]
            break
    v = v.strip().rstrip(".")
    return v.lower() or None


def norm_ws(s: str | None) -> str:
    return " ".join((s or "").split())


_ISO_DATE_RE = None


def iso_date_or_none(value: str | None) -> str | None:
    """Return ``value`` only if it is a full ISO ``YYYY-MM-DD`` date, else None.

    The horizon schema forbids partial dates in ``event_at``/``source_public_at``.
    Sources such as ClinicalTrials.gov routinely publish ``YYYY-MM`` (month
    precision) and sometimes just ``YYYY``. Inventing a day would be fabricated
    data, so a partial date stays out of the clock fields, is kept verbatim in
    ``attributes``, and the record gets the matching ``MISSING_*_DATE`` flag.
    """
    global _ISO_DATE_RE
    if _ISO_DATE_RE is None:
        import re
        _ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    if not value:
        return None
    v = str(value).strip()[:10]
    return v if _ISO_DATE_RE.match(v) else None


def date_precision(value: str | None) -> str:
    """Classify a raw date string's precision without inventing anything."""
    if not value:
        return "absent"
    v = str(value).strip()
    if len(v) >= 10 and v[4] == "-" and v[7] == "-":
        return "day"
    if len(v) == 7 and v[4] == "-":
        return "month"
    if len(v) == 4 and v.isdigit():
        return "year"
    return "other"


# -------------------------------------------------------------------- anchors
ANCHORS_PATH = os.path.join(DATASETS, "openalex", "ANCHORS.json")


def load_anchors() -> dict[str, Any]:
    if not os.path.isfile(ANCHORS_PATH):
        raise FileNotFoundError(
            f"{ANCHORS_PATH} missing: run CONNECTORS/scholarly/openalex.py first"
        )
    return read_json(ANCHORS_PATH)


def anchor_dois() -> list[str]:
    doc = load_anchors()
    out = []
    for a in doc["anchors"]:
        if a.get("doi"):
            out.append(a["doi"])
    return out
