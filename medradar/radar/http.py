"""Polite HTTP transport shared by every radar adapter.

One implementation, because the failure semantics must be identical for PubMed, Crossref,
openFDA and a vendor site: a refusal is never retried, a rate limit is honoured, a
transient failure backs off, and a budget can stop the run without pretending it succeeded.

Design points that matter for correctness:

* **A refusal is terminal.** HTTP 401/402/403/407/451 raise :class:`Refused` immediately.
  The adapter records a failure and does not advance its cursor. Nothing here spoofs a
  browser identity, replays a cookie or changes a header to get past an access decision.
* **429 is a rate limit, not a transport error.** ``Retry-After`` is honoured when the
  source sends it; otherwise the retry uses exponential backoff with jitter.
* **Backoff is bounded.** A run gives up after ``max_attempts`` and reports a failure; the
  scheduler retries the source later. A single failed request never advances a watermark.
* **The budget is a hard stop.** Exceeding the per-run request budget raises
  :class:`BudgetExceeded`, which the runner records as ``PARTIAL`` - never as ``OK``.
* **One request every N seconds per host.** A vendor site is not an API; the per-host
  interval comes from ``config/radar/sources.json``.
"""

from __future__ import annotations

import gzip
import io
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

DEFAULT_USER_AGENT = (
    "MedRadarBot/0.1 (+https://github.com/ChazY11/medradar; research; "
    "contact: repository owner) Python-urllib"
)
REFUSAL_STATUSES = frozenset({401, 402, 403, 407, 451})
RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504, 522, 524})


class FetchError(RuntimeError):
    """Base class for a transport failure."""

    retryable = True
    kind = "FETCH_ERROR"

    def __init__(self, message: str, *, url: str | None = None, status: int | None = None,
                 retry_after: float | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.status = status
        self.retry_after = retry_after


class Refused(FetchError):
    """The operator refused automated access. Terminal: never retried, never bypassed."""

    retryable = False
    kind = "ACCESS_REFUSED"


class RateLimited(FetchError):
    retryable = True
    kind = "RATE_LIMITED"


class NotFound(FetchError):
    """The path does not exist. Not a refusal and not a transient failure."""

    retryable = False
    kind = "NOT_FOUND"


class TransientHttpError(FetchError):
    retryable = True
    kind = "HTTP_ERROR"


class NetworkFailure(FetchError):
    retryable = True
    kind = "NETWORK_ERROR"


class ParseFailure(FetchError):
    retryable = False
    kind = "PARSE_ERROR"


class BudgetExceeded(FetchError):
    retryable = False
    kind = "BUDGET"


@dataclass
class FetchResult:
    """One completed request. ``body`` is decoded; ``raw_bytes`` is the byte count."""

    url: str
    status: int
    content_type: str | None
    body: str
    raw_bytes: int
    elapsed_ms: float
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass
class HostPolicy:
    requests_per_second: float = 1.0
    timeout_seconds: float = 30.0
    max_attempts: int = 3
    backoff_base_seconds: float = 2.0
    backoff_cap_seconds: float = 30.0

    @property
    def min_interval(self) -> float:
        return 1.0 / max(0.05, self.requests_per_second)


class PoliteFetcher:
    """Host-aware, budgeted, retrying HTTP GET."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        policies: Mapping[str, HostPolicy] | None = None,
        default_policy: HostPolicy | None = None,
        max_requests: int = 400,
        sleep: Callable[[float], None] = time.sleep,
        opener: Callable[..., Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.policies = dict(policies or {})
        self.default_policy = default_policy or HostPolicy()
        self.max_requests = int(max_requests)
        self._sleep = sleep
        self._opener = opener or urllib.request.urlopen
        self._clock = clock
        self._extra_headers = dict(extra_headers or {})
        self._last_request_at: dict[str, float] = {}
        self.stats: dict[str, Any] = {"requests": 0, "bytes": 0, "retries": 0, "refusals": 0,
                                      "rate_limited": 0, "not_found": 0, "failures": 0}
        self.log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ helpers
    def policy_for(self, url: str) -> HostPolicy:
        host = urllib.parse.urlsplit(url).netloc.lower()
        return self.policies.get(host, self.default_policy)

    @property
    def requests_remaining(self) -> int:
        return max(0, self.max_requests - int(self.stats["requests"]))

    def _pace(self, policy: HostPolicy, url: str) -> None:
        host = urllib.parse.urlsplit(url).netloc.lower()
        last = self._last_request_at.get(host)
        if last is not None:
            wait = policy.min_interval - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)

    def _decode(self, raw: bytes, headers: Mapping[str, str]) -> str:
        encoding = (headers.get("Content-Encoding") or "").lower()
        if "gzip" in encoding:
            try:
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            except OSError:
                pass
        elif "deflate" in encoding:
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                pass
        charset = "utf-8"
        content_type = headers.get("Content-Type") or ""
        if "charset=" in content_type.lower():
            charset = content_type.lower().split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
        return raw.decode(charset, "replace")

    def _retry_after(self, headers: Mapping[str, str]) -> float | None:
        raw = headers.get("Retry-After")
        if not raw:
            return None
        text = str(raw).strip()
        if text.isdigit():
            return float(text)
        try:
            moment = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return max(0.0, (moment - datetime.now(timezone.utc)).total_seconds())

    # -------------------------------------------------------------------- fetch
    def get_text(self, url: str, *, headers: Mapping[str, str] | None = None,
                 allow_not_found: bool = False) -> FetchResult:
        policy = self.policy_for(url)
        attempts = max(1, int(policy.max_attempts))
        last_error: FetchError | None = None
        for attempt in range(1, attempts + 1):
            if self.requests_remaining <= 0:
                raise BudgetExceeded(
                    f"request budget exhausted ({self.max_requests}) before {url}", url=url
                )
            self._pace(policy, url)
            request_headers = {"User-Agent": self.user_agent, "Accept": "*/*"}
            request_headers.update(self._extra_headers)
            request_headers.update(headers or {})
            request = urllib.request.Request(url, headers=request_headers)
            started = time.perf_counter()
            self.stats["requests"] += 1
            self._last_request_at[urllib.parse.urlsplit(url).netloc.lower()] = self._clock()
            try:
                with self._opener(request, timeout=policy.timeout_seconds) as response:
                    raw = response.read()
                    status = int(getattr(response, "status", 200))
                    response_headers = {k: v for k, v in (response.headers or {}).items()}
            except urllib.error.HTTPError as error:
                status = int(error.code)
                response_headers = {k: v for k, v in (error.headers or {}).items()}
                self.log.append({"url": url, "status": status, "attempt": attempt})
                if status in REFUSAL_STATUSES:
                    self.stats["refusals"] += 1
                    raise Refused(
                        f"{status} {error.reason}: the source refused automated access; "
                        "MedRadar records the refusal and does not attempt to bypass it",
                        url=url, status=status,
                    ) from error
                if status == 404:
                    self.stats["not_found"] += 1
                    if allow_not_found:
                        return FetchResult(url=url, status=404, content_type=None, body="",
                                           raw_bytes=0, elapsed_ms=0.0, headers={})
                    raise NotFound(f"404 {error.reason}", url=url, status=status) from error
                if status == 429:
                    self.stats["rate_limited"] += 1
                    retry_after = self._retry_after(response_headers)
                    last_error = RateLimited("429 Too Many Requests", url=url, status=status,
                                             retry_after=retry_after)
                elif status in RETRYABLE_STATUSES:
                    last_error = TransientHttpError(f"{status} {error.reason}", url=url, status=status)
                else:
                    raise FetchError(f"{status} {error.reason}", url=url, status=status) from error
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                self.log.append({"url": url, "status": None, "attempt": attempt, "error": str(error)})
                last_error = NetworkFailure(f"{type(error).__name__}: {error}", url=url)
            else:
                elapsed = round((time.perf_counter() - started) * 1000.0, 1)
                self.stats["bytes"] += len(raw)
                text = self._decode(raw, response_headers)
                self.log.append({"url": url, "status": status, "bytes": len(raw), "attempt": attempt})
                return FetchResult(
                    url=url, status=status,
                    content_type=response_headers.get("Content-Type"),
                    body=text, raw_bytes=len(raw), elapsed_ms=elapsed,
                    headers=response_headers,
                )
            if attempt < attempts:
                delay = last_error.retry_after if isinstance(last_error, RateLimited) and last_error.retry_after else None
                if delay is None:
                    delay = min(policy.backoff_cap_seconds,
                                policy.backoff_base_seconds * (2 ** (attempt - 1)))
                    delay += random.uniform(0, 0.25 * delay)
                delay = min(delay, policy.backoff_cap_seconds)
                self.stats["retries"] += 1
                self._sleep(delay)
        self.stats["failures"] += 1
        assert last_error is not None
        raise last_error

    def get_json(self, url: str, *, params: Mapping[str, Any] | None = None,
                 headers: Mapping[str, str] | None = None,
                 allow_not_found: bool = False) -> Any:
        target = url
        if params:
            separator = "&" if "?" in url else "?"
            target = url + separator + urllib.parse.urlencode(dict(params), doseq=True)
        result = self.get_text(target, headers=headers, allow_not_found=allow_not_found)
        if result.status == 404 and not result.body:
            return None
        try:
            return json.loads(result.body)
        except ValueError as error:
            raise ParseFailure(f"invalid JSON from {target}: {error}", url=target) from error

    def get_xml(self, url: str, *, headers: Mapping[str, str] | None = None) -> str:
        return self.get_text(url, headers=headers).body
