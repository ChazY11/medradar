"""Declarative source probes.

A *probe* answers one falsifiable question about one endpoint:
"can this URL be fetched, at what cost, with what licence, and does the body
actually contain the field we claim it contains?"

Probing is separate from collection on purpose. A probe result states ACCESS,
never DATA or RESEARCH success. The distinction is what prevents this project
from confusing "the endpoint answered" with "we have usable evidence".
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

from .http import BoundedClient, BudgetExceeded, ResponseTooLarge

OUTCOMES = {
    "OK",                    # 2xx and the expected content marker was found
    "OK_NO_MARKER",          # 2xx but the expected content marker was absent
    "BLOCKED_AUTH",          # 401/403 — key or account required
    "BLOCKED_WAF",           # anti-automation challenge / interstitials
    "NOT_FOUND",             # 404 / retired endpoint
    "SERVER_ERROR",          # 5xx
    "RATE_LIMITED",          # 429
    "TOO_LARGE",             # exceeded our own cap
    "TRANSPORT_ERROR",       # DNS/TLS/connection
    "BUDGET_EXCEEDED",       # we stopped ourselves
    "SKIPPED",               # not attempted (documented reason)
}


@dataclass
class Probe:
    probe_id: str
    source_id: str
    url: str
    question: str
    expect_status: tuple[int, ...] = (200,)
    expect_marker: str | None = None      # substring that must appear in body
    params: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    note: str = ""
    auth_required: bool = False


@dataclass
class ProbeResult:
    probe_id: str
    source_id: str
    url: str
    question: str
    status: int | None
    outcome: str
    elapsed_ms: int
    bytes: int
    sha256: str | None
    content_type: str | None
    marker_found: bool | None
    retry_after: str | None
    error: str | None
    note: str = ""
    observed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run_probe(client: BoundedClient, p: Probe) -> ProbeResult:
    started = time.monotonic()
    try:
        res = client.get(p.url, params=p.params, headers=p.headers)
    except BudgetExceeded as exc:
        return ProbeResult(
            probe_id=p.probe_id, source_id=p.source_id, url=p.url, question=p.question,
            status=None, outcome="BUDGET_EXCEEDED", elapsed_ms=0, bytes=0, sha256=None,
            content_type=None, marker_found=None, retry_after=None, error=str(exc),
            note=p.note, observed_at=_utc_now(),
        )
    except ResponseTooLarge as exc:
        return ProbeResult(
            probe_id=p.probe_id, source_id=p.source_id, url=p.url, question=p.question,
            status=None, outcome="TOO_LARGE", elapsed_ms=0, bytes=0, sha256=None,
            content_type=None, marker_found=None, retry_after=None, error=str(exc),
            note=p.note, observed_at=_utc_now(),
        )
    except Exception as exc:  # transport
        return ProbeResult(
            probe_id=p.probe_id, source_id=p.source_id, url=p.url, question=p.question,
            status=None, outcome="TRANSPORT_ERROR", elapsed_ms=0, bytes=0, sha256=None,
            content_type=None, marker_found=None, retry_after=None,
            error=f"{type(exc).__name__}: {exc}"[:400], note=p.note,
            observed_at=_utc_now(),
        )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    body_text = res.text()
    marker_found: bool | None = None
    if p.expect_marker is not None:
        marker_found = p.expect_marker.lower() in body_text.lower()

    status = res.status
    if 200 <= status < 300:
        outcome = "OK" if (marker_found is not False) else "OK_NO_MARKER"
    elif status in (401, 403):
        # 403 from a WAF challenge page is a different failure from a real auth
        # wall; the marker/page shape is what tells them apart.
        low = body_text.lower()
        waf_markers = ("awswaf", "captcha", "challenge.js", "cf-chl", "just a moment")
        outcome = "BLOCKED_WAF" if any(m in low for m in waf_markers) else "BLOCKED_AUTH"
    elif status == 404:
        outcome = "NOT_FOUND"
    elif status == 429:
        outcome = "RATE_LIMITED"
    elif 500 <= status < 600:
        outcome = "SERVER_ERROR"
    else:
        outcome = "OK" if res.ok else "OK_NO_MARKER"

    return ProbeResult(
        probe_id=p.probe_id,
        source_id=p.source_id,
        url=res.final_url or p.url,
        question=p.question,
        status=status,
        outcome=outcome,
        elapsed_ms=elapsed_ms,
        bytes=len(res.body),
        sha256=res.content_hash,
        content_type=res.headers.get("content-type"),
        marker_found=marker_found,
        retry_after=res.headers.get("retry-after"),
        error=None,
        note=p.note,
        observed_at=_utc_now(),
    )


def run_probes(
    probes: list[Probe],
    *,
    out_dir: str,
    client_name: str,
    max_requests: int = 40,
    max_bytes_per_response: int = 6_000_000,
) -> dict[str, Any]:
    """Run a probe suite and persist PROBES.json + REQUEST_LOG.jsonl."""
    os.makedirs(out_dir, exist_ok=True)
    log_path = os.path.join(out_dir, "REQUEST_LOG.jsonl")
    results: list[ProbeResult] = []
    with BoundedClient(
        name=client_name,
        max_requests=max_requests,
        max_bytes_per_response=max_bytes_per_response,
        log_path=log_path,
    ) as client:
        for p in probes:
            results.append(run_probe(client, p))
        budget = client.budget_report()

    summary: dict[str, int] = {}
    for r in results:
        summary[r.outcome] = summary.get(r.outcome, 0) + 1

    doc = {
        "suite": client_name,
        "generated_at": _utc_now(),
        "outcomes": summary,
        "budget": budget,
        "probes": [r.to_dict() for r in results],
    }
    with open(os.path.join(out_dir, "PROBES.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return doc
