"""Bounded, logged HTTP access for ATLAS connectors.

Every network call in ATLAS goes through :class:`HttpClient`.  It exists so a
collector cannot become an accidental crawler:

* hard per-run request budget,
* minimum interval between requests,
* bounded retries, only for retryable failures, honouring ``Retry-After``,
* every attempt (success and failure) appended to a JSONL ledger that is later
  copied into the database's ``request_log``,
* a failure is returned as data, never raised past the connector boundary.

Ported and trimmed from ``medradar.external_sources.base``
(DATA-EXPANSION-001, ``origin/research/data-expansion-001``); the probe-runner
machinery was dropped because ATLAS records runs in SQLite instead.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_USER_AGENT = (
    "MedRadar-ATLAS/0.1 (academic research; open data only; "
    "https://github.com/ChazY11/medradar)"
)


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class BudgetExceeded(RuntimeError):
    """Raised when a connector would exceed its own request budget."""


@dataclass
class HttpResult:
    """One logical request's outcome.  A failure is data, not an exception."""

    url: str
    method: str
    status: int | None
    body: bytes
    headers: dict[str, str]
    elapsed_ms: int
    attempts: int
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300 and not self.error

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)

    def summary(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "method": self.method,
            "status": self.status,
            "bytes": len(self.body),
            "elapsed_ms": self.elapsed_ms,
            "attempts": self.attempts,
            "error": self.error,
        }


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
    """Append-only JSONL record of every request a connector makes."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.entries: list[dict[str, Any]] = []

    def append(self, entry: Mapping[str, Any]) -> None:
        row = dict(entry)
        row.setdefault("logged_at", utc_iso())
        self.entries.append(row)
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def count(self) -> int:
        return len(self.entries)


@dataclass
class HttpClient:
    source_id: str
    ledger: HttpLedger
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = 45.0
    max_retries: int = 2
    min_interval: float = 1.0
    budget: int = 50
    max_body_bytes: int = 16 * 1024 * 1024
    allow_network: bool = True
    _requests_made: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._limiter = RateLimiter(self.min_interval)

    def requests_made(self) -> int:
        return self._requests_made

    def remaining(self) -> int:
        return max(0, self.budget - self._requests_made)

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
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        merged = {"Content-Type": "application/json"}
        if headers:
            merged.update({str(k): str(v) for k, v in headers.items()})
        return self._request("POST", url, params=params, headers=merged, accept=accept, body=body)

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
        full_url = with_params(url, params)
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
            "Accept-Encoding": "gzip",
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
                    truncated = len(raw) > self.max_body_bytes
                    if truncated:
                        raw = raw[: self.max_body_bytes]
                    if (resp.headers.get("Content-Encoding") or "").lower() == "gzip" and raw:
                        try:
                            raw = gzip.decompress(raw)
                        except OSError:
                            pass
                    elapsed = int((time.monotonic() - started) * 1000)
                    result = HttpResult(
                        full_url, method, resp.status, raw,
                        {k.lower(): v for k, v in resp.headers.items()}, elapsed, attempt,
                        error="response exceeded max_body_bytes" if truncated else "",
                    )
                    return self._record(result)
            except urllib.error.HTTPError as exc:
                try:
                    err_body = exc.read(self.max_body_bytes)
                except Exception:  # pragma: no cover - defensive
                    err_body = b""
                elapsed = int((time.monotonic() - started) * 1000)
                retry_after = retry_after_seconds(exc.headers)
                last = HttpResult(
                    full_url, method, exc.code, err_body,
                    {k.lower(): v for k, v in (exc.headers or {}).items()}, elapsed, attempt,
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
                    full_url, method, None, b"", {}, elapsed, attempt,
                    error=f"{type(exc).__name__}: {str(exc)[:200]}",
                )
                if attempt <= self.max_retries:
                    self._record(last, note="retrying after transport error")
                    time.sleep(min(8.0, 1.5**attempt))
                    continue
                return self._record(last)
        assert last is not None
        return self._record(last)

    def stream_to_file(
        self,
        url: str,
        path: Path,
        *,
        max_bytes: int,
        params: Mapping[str, Any] | None = None,
        chunk_size: int = 1 << 20,
    ) -> dict[str, Any]:
        """Download one large official file under a hard byte cap.

        Used only for sources whose listing endpoints return the whole table
        (Health Canada MDALL: ~220 MB).  The ledger records bytes, hash and
        truncation status exactly as for a normal request.
        """
        full_url = with_params(url, params)
        if self._requests_made >= self.budget:
            raise BudgetExceeded(f"{self.source_id}: request budget exhausted (url={url})")
        if not self.allow_network:
            self._requests_made += 1
            raise RuntimeError("network disabled by caller")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._limiter.wait()
        self._requests_made += 1
        started = time.monotonic()
        digest = hashlib.sha256()
        total = 0
        truncated = False
        status: int | None = None
        error = ""
        try:
            req = urllib.request.Request(
                full_url, headers={"User-Agent": self.user_agent, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp, path.open("wb") as fh:
                status = resp.status
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    if total + len(chunk) > max_bytes:
                        chunk = chunk[: max_bytes - total]
                        truncated = True
                    fh.write(chunk)
                    digest.update(chunk)
                    total += len(chunk)
                    if truncated:
                        break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            error = f"{type(exc).__name__}: {str(exc)[:200]}"
        elapsed = int((time.monotonic() - started) * 1000)
        entry = {
            "url": full_url,
            "method": "GET",
            "status": status,
            "bytes": total,
            "elapsed_ms": elapsed,
            "attempts": 1,
            "error": error,
            "sha256": digest.hexdigest(),
            "truncated": truncated,
            "path": str(path),
            "source_id": self.source_id,
            "note": "streamed to file",
        }
        self.ledger.append(entry)
        return entry

    def _record(self, result: HttpResult, note: str = "") -> HttpResult:
        self.ledger.append({**result.summary(), "source_id": self.source_id, "note": note})
        return result


def with_params(url: str, params: Mapping[str, Any] | None) -> str:
    if not params:
        return url
    pairs = [(str(k), str(v)) for k, v in params.items() if v is not None]
    if not pairs:
        return url
    sep = "&" if urllib.parse.urlparse(url).query else "?"
    return url + sep + urllib.parse.urlencode(pairs)


def retry_after_seconds(headers: Mapping[str, str] | None) -> float:
    if not headers:
        return 2.0
    value = headers.get("Retry-After") or headers.get("retry-after")
    if not value:
        return 2.0
    try:
        return max(1.0, min(30.0, float(value)))
    except (TypeError, ValueError):
        return 2.0


__all__ = [
    "BudgetExceeded",
    "DEFAULT_USER_AGENT",
    "HttpClient",
    "HttpLedger",
    "HttpResult",
    "RateLimiter",
    "retry_after_seconds",
    "sha256_bytes",
    "utc_iso",
    "with_params",
]
