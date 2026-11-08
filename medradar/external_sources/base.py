"""Bounded HTTP access and probe evidence for external sources.

Everything that touches the network in this package goes through
:class:`HttpClient`.  It exists so that a probe cannot accidentally become a
crawler:

* hard per-run request budget,
* minimum interval between requests,
* bounded retries with exponential backoff, and only for retryable failures,
* ``Retry-After`` is honoured,
* every request (success **and** failure) is appended to a JSONL ledger,
* a failure is recorded and returned, never retried forever, never raised
  past the probe boundary.

:func:`run_probe` wraps a source's probe function, records the outcome as a
``PROBE_RESULT.json`` next to the request ledger, and returns a typed result
that the source register merges in later.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

#: Access states accepted by the global source register.
#:
#: ``VERIFIED_API``            — an official machine interface returned real records
#: ``VERIFIED_BULK_DOWNLOAD``  — an official bulk file downloaded and parsed
#: ``VERIFIED_PUBLIC_QUERY``   — a public query endpoint returned real records (HTML/JSON)
#: ``REQUIRES_REGISTRATION``   — real access exists but needs an account / key
#: ``PAID_ONLY``               — access exists only commercially
#: ``BLOCKED_BY_POLICY``       — access is technically possible but not permitted
#: ``UNAVAILABLE``             — no working access found
#: ``NOT_TESTED``              — not probed (time, scope, or priority)
PROBE_STATUSES: frozenset[str] = frozenset(
    {
        "VERIFIED_API",
        "VERIFIED_BULK_DOWNLOAD",
        "VERIFIED_PUBLIC_QUERY",
        "REQUIRES_REGISTRATION",
        "PAID_ONLY",
        "BLOCKED_BY_POLICY",
        "UNAVAILABLE",
        "NOT_TESTED",
    }
)

DEFAULT_USER_AGENT = (
    "MedRadar-Research/1.0 (DATA-EXPANSION-001; academic, non-commercial; "
    "contact: medradar.research@example.org)"
)


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class HttpResult:
    """One attempt's outcome.  A failure is data, not an exception."""

    url: str
    method: str
    status: int | None
    body: bytes
    headers: dict[str, str]
    elapsed_ms: int
    attempts: int
    error: str = ""
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300 and not self.error

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)

    def truncated_text(self, limit: int = 400) -> str:
        return self.text[:limit]

    def summary(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "method": self.method,
            "status": self.status,
            "bytes": len(self.body),
            "elapsed_ms": self.elapsed_ms,
            "attempts": self.attempts,
            "error": self.error,
            "from_cache": self.from_cache,
        }


class BudgetExceeded(RuntimeError):
    """Raised when a probe would exceed its own request budget."""


class RateLimiter:
    """Serial minimum-interval limiter (one process, one host at a time)."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = max(0.0, float(min_interval))
        self._last = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        delta = time.monotonic() - self._last
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last = time.monotonic()


class HttpLedger:
    """Append-only JSONL record of every request a probe makes."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.entries: list[dict[str, Any]] = []

    def append(self, entry: Mapping[str, Any]) -> None:
        row = dict(entry)
        row.setdefault("logged_at", utc_iso())
        self.entries.append(row)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def count(self) -> int:
        return len(self.entries)


@dataclass
class HttpClient:
    """A deliberately small HTTP client: GET only, bounded, and logged."""

    source_id: str
    ledger: HttpLedger
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = 30.0
    max_retries: int = 2
    min_interval: float = 1.0
    budget: int = 20
    max_body_bytes: int = 8 * 1024 * 1024
    accept_gzip: bool = True
    allow_network: bool = True
    _requests_made: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._limiter = RateLimiter(self.min_interval)

    # ------------------------------------------------------------- accounting
    def requests_made(self) -> int:
        return self._requests_made

    def remaining(self) -> int:
        return max(0, self.budget - self._requests_made)

    # ---------------------------------------------------------------- request
    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        accept: str = "application/json",
    ) -> HttpResult:
        return self._request("GET", url, params=params, headers=headers, accept=accept)

    def post_json(
        self,
        url: str,
        payload: Mapping[str, Any] | Sequence[Any],
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        accept: str = "application/json",
    ) -> HttpResult:
        """JSON POST, for the few official APIs that only accept POST (NIH RePORTER,
        USAspending award search).  Same budget, ledger and retry policy as GET."""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        merged = {"Content-Type": "application/json"}
        if headers:
            merged.update({str(k): str(v) for k, v in headers.items()})
        return self._request(
            "POST", url, params=params, headers=merged, accept=accept, body=body
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        accept: str = "application/json",
        body: bytes | None = None,
    ) -> HttpResult:
        full_url = _with_params(url, params)
        if self._requests_made >= self.budget:
            raise BudgetExceeded(
                f"{self.source_id}: request budget {self.budget} exhausted (url={url})"
            )
        if not self.allow_network:
            self._requests_made += 1
            return self._record(
                HttpResult(full_url, method, None, b"", {}, 0, 0, error="network disabled by caller")
            )

        request_headers = {
            "User-Agent": self.user_agent,
            "Accept": accept,
            "Accept-Encoding": "gzip" if self.accept_gzip else "identity",
        }
        if headers:
            request_headers.update({str(k): str(v) for k, v in headers.items()})

        last: HttpResult | None = None
        for attempt in range(1, self.max_retries + 2):
            self._limiter.wait()
            self._requests_made += 1
            started = time.monotonic()
            try:
                req = urllib.request.Request(
                    full_url, data=body, headers=request_headers, method=method
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read(self.max_body_bytes + 1)
                    if len(raw) > self.max_body_bytes:
                        raw = raw[: self.max_body_bytes]
                    encoding = (resp.headers.get("Content-Encoding") or "").lower()
                    if encoding == "gzip" and raw:
                        try:
                            raw = gzip.decompress(raw)
                        except OSError:
                            pass
                    elapsed = int((time.monotonic() - started) * 1000)
                    result = HttpResult(
                        full_url,
                        method,
                        resp.status,
                        raw,
                        {k.lower(): v for k, v in resp.headers.items()},
                        elapsed,
                        attempt,
                    )
                    return self._record(result)
            except urllib.error.HTTPError as exc:
                body = b""
                try:
                    body = exc.read(self.max_body_bytes)
                except Exception:  # pragma: no cover - defensive
                    body = b""
                elapsed = int((time.monotonic() - started) * 1000)
                retry_after = _retry_after_seconds(exc.headers)
                last = HttpResult(
                    full_url,
                    method,
                    exc.code,
                    body,
                    {k.lower(): v for k, v in (exc.headers or {}).items()},
                    elapsed,
                    attempt,
                    error=f"HTTP {exc.code} {exc.reason}",
                )
                if exc.code in {429, 500, 502, 503, 504} and attempt <= self.max_retries:
                    self._record(last, note=f"retrying after {retry_after:.1f}s")
                    time.sleep(retry_after)
                    continue
                return self._record(last)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                elapsed = int((time.monotonic() - started) * 1000)
                last = HttpResult(
                    full_url,
                    method,
                    None,
                    b"",
                    {},
                    elapsed,
                    attempt,
                    error=f"{type(exc).__name__}: {str(exc)[:200]}",
                )
                if attempt <= self.max_retries:
                    self._record(last, note="retrying after transport error")
                    time.sleep(min(8.0, 1.5**attempt))
                    continue
                return self._record(last)
        assert last is not None
        return self._record(last)

    # --------------------------------------------------------------- internal
    def _record(self, result: HttpResult, note: str = "") -> HttpResult:
        self.ledger.append({**result.summary(), "source_id": self.source_id, "note": note})
        return result


def _with_params(url: str, params: Mapping[str, Any] | None) -> str:
    if not params:
        return url
    pairs = [(str(k), str(v)) for k, v in params.items() if v is not None]
    if not pairs:
        return url
    sep = "&" if urllib.parse.urlparse(url).query else "?"
    return url + sep + urllib.parse.urlencode(pairs)


def _retry_after_seconds(headers: Mapping[str, str] | None) -> float:
    if not headers:
        return 2.0
    value = headers.get("Retry-After") or headers.get("retry-after")
    if not value:
        return 2.0
    try:
        return max(1.0, min(30.0, float(value)))
    except (TypeError, ValueError):
        return 2.0


# --------------------------------------------------------------------------
def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_sample(
    sample_dir: Path,
    name: str,
    body: bytes,
    *,
    max_inline_bytes: int = 512 * 1024,
) -> dict[str, Any]:
    """Persist a *bounded* real sample and describe it truthfully.

    The full-response hash is always of the complete bytes received.  If the
    body is larger than ``max_inline_bytes`` only the head is written, and the
    descriptor says ``stored_bytes`` < ``total_bytes`` so nobody mistakes the
    sample for the whole response.
    """
    sample_dir = Path(sample_dir)
    sample_dir.mkdir(parents=True, exist_ok=True)
    total = len(body)
    truncated = total > max_inline_bytes
    stored = body[:max_inline_bytes] if truncated else body
    target = sample_dir / name
    target.write_bytes(stored)
    return {
        "path": str(target),
        "name": name,
        "total_bytes": total,
        "stored_bytes": len(stored),
        "truncated": truncated,
        "sha256_full": sha256_bytes(body),
        "sha256_stored": sha256_bytes(stored),
    }


def json_shape(payload: Any, *, depth: int = 0, max_depth: int = 3) -> Any:
    """Describe a JSON payload's structure without copying its values."""
    if depth >= max_depth:
        return type(payload).__name__
    if isinstance(payload, dict):
        return {
            "__type__": "object",
            "keys": sorted(str(k) for k in payload.keys())[:40],
            "sample": {
                str(k): json_shape(payload[k], depth=depth + 1, max_depth=max_depth)
                for k in list(payload.keys())[:12]
            },
        }
    if isinstance(payload, list):
        return {
            "__type__": "array",
            "len": len(payload),
            "item": json_shape(payload[0], depth=depth + 1, max_depth=max_depth) if payload else None,
        }
    if isinstance(payload, str):
        return {"__type__": "string", "max_len": len(payload)}
    return {"__type__": type(payload).__name__}


@dataclass
class ProbeOutcome:
    source_id: str
    status: str
    probes: list[dict[str, Any]]
    requests: int
    evidence_urls: list[str]
    notes: str = ""
    verified_at: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "medradar.external.probe.v1",
            "source_id": self.source_id,
            "status": self.status,
            "verified_at": self.verified_at or utc_iso(),
            "requests": self.requests,
            "evidence_urls": self.evidence_urls,
            "notes": self.notes,
            "error": self.error,
            "probes": self.probes,
        }


def probe_dir(root: Path, source_id: str) -> Path:
    path = Path(root) / "probes" / source_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_probe(
    source_id: str,
    root: Path,
    fn: Callable[[HttpClient, Path], ProbeOutcome],
    *,
    budget: int,
    min_interval: float = 1.0,
    timeout: float = 30.0,
    max_retries: int = 2,
    allow_network: bool = True,
) -> ProbeOutcome:
    """Run one source probe, persist its evidence, and never raise on network failure."""
    root = Path(root)
    directory = probe_dir(root, source_id)
    ledger = HttpLedger(directory / "requests.jsonl")
    client = HttpClient(
        source_id=source_id,
        ledger=ledger,
        budget=budget,
        min_interval=min_interval,
        timeout=timeout,
        max_retries=max_retries,
        allow_network=allow_network,
    )
    try:
        outcome = fn(client, directory)
    except Exception as exc:  # a probe failure is evidence, not a crash
        outcome = ProbeOutcome(
            source_id=source_id,
            status="UNAVAILABLE",
            probes=[],
            requests=client.requests_made(),
            evidence_urls=[],
            notes="probe aborted",
            error=f"{type(exc).__name__}: {exc}",
        )
    if outcome.status not in PROBE_STATUSES:
        raise ValueError(f"probe status not in allowed set: {outcome.status!r}")
    outcome.requests = client.requests_made()
    payload = outcome.to_dict()
    (directory / "PROBE_RESULT.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return outcome
