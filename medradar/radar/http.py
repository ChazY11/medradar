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
import http.client
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

#: A 403 is not always a policy decision. Measured on 2026-11-21 against api.fda.gov:
#: ``limit=1000`` without an API key answers 403 with
#: ``{"error": {"code": "API_KEY_MISSING"}}``, while ``limit=999`` on the same endpoint
#: answers 200. The source is not refusing automated access - it is telling the caller to
#: ask for fewer rows or to identify itself.
#:
#: The distinction is made from the *error body*, never by retrying. A plain 403 stays a
#: terminal refusal on the first observation: this project does not retry past a refusal, and
#: ``tests/test_radar_core.py::test_a_refusal_is_terminal_and_never_retried`` holds that
#: contract. Reading the body costs nothing and is the only thing that separates the two
#: cases, which is why it is done here rather than in a retry loop.
OPENFDA_MAX_LIMIT_WITHOUT_KEY = 999

#: openFDA refuses to page deep: ``skip`` above this returns
#: ``400 {"error":{"code":"BAD_REQUEST","message":"Skip value must 25000 or less."}}``.
#: Measured 2026-11-21: skip 25,000 answers 200, skip 25,001 answers 400. One query window can
#: therefore reach at most ``OPENFDA_MAX_SKIP + OPENFDA_MAX_LIMIT_WITHOUT_KEY`` records, and a
#: larger set has to be partitioned by a search field - see
#: ``fda_corpus.collect_510k_index``, which splits by calendar year and then by month.
OPENFDA_MAX_SKIP = 25_000

#: The most rows one window can yield: 25,000 skipped plus one full last page.
OPENFDA_MAX_RECORDS_PER_WINDOW = OPENFDA_MAX_SKIP + OPENFDA_MAX_LIMIT_WITHOUT_KEY

#: An openFDA error body that names a documented capability limit rather than a refusal.
#: Classifying these as ACCESS_REFUSED would tell the operator "this site blocks us" about a
#: site that had just answered a slightly smaller request successfully.
CAPABILITY_LIMIT_CODES = frozenset({
    "API_KEY_MISSING",
    "OVER_LIMIT",
    "TOO_MANY_REQUESTS",
    "INVALID_LIMIT",
    "LIMIT_EXCEEDED",
})

ENV_OPENFDA_API_KEY = "OPENFDA_API_KEY"


def openfda_api_key() -> str | None:
    """The openFDA key, when one is configured. Never required, never invented.

    With a key openFDA allows 120,000 requests/day and the full page size, which is the
    difference between a 5,182-page UDI sweep being possible today and being a 6-day job.
    """
    import os

    value = str(os.environ.get(ENV_OPENFDA_API_KEY) or "").strip()
    return value or None


def with_openfda_key(params: Mapping[str, Any]) -> dict[str, Any]:
    """Inject ``api_key`` only when the environment actually has one.

    A placeholder empty key is worse than no key: openFDA answers 400 for ``api_key=`` and
    the caller cannot tell that apart from a malformed query.
    """
    merged = dict(params)
    key = openfda_api_key()
    if key:
        merged["api_key"] = key
    return merged


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


class CapabilityLimit(FetchError):
    """A documented capability limit, not a refusal.

    openFDA answers ``403`` with ``{"error": {"code": "API_KEY_MISSING"}}`` when the caller
    asks for more rows than an unidentified client may page. That is the source telling the
    caller to ask for less or to identify itself - it is emphatically not the operator
    refusing automated access, and recording it as one would put a false access restriction
    in front of a user and disable a public-domain source for ever.
    """

    retryable = False
    kind = "CAPABILITY_LIMIT"


class CredentialRequired(FetchError):
    """HTTP 401: the route exists and wants a credential the caller did not supply.

    Distinguished from :class:`Refused` because the fix is a configuration change, not an
    access policy. Measured on ``api.uspto.gov``: every real route answers
    ``401 {"message":"Unauthorized"}`` without a key, and reporting that as "the operator
    refuses automated access" would be both wrong and unactionable.
    """

    retryable = False
    kind = "CREDENTIAL_REQUIRED"


class RouteAbsent(FetchError):
    """HTTP 403 whose body is AWS API Gateway's "Missing Authentication Token".

    Counter-intuitively that message almost never means a missing token: API Gateway returns
    it for a path that has no route at all. Measured on ``api.uspto.gov``: the two live routes
    answer 401, while ``/api/v1/patent/assignments/search`` and every other guessed path answer
    403 with this exact body. Treating it as a refusal would tell a reader the operator blocked
    us, when the truth is that the endpoint does not exist.
    """

    retryable = False
    kind = "ROUTE_ABSENT"


class CredentialRejected(FetchError):
    """HTTP 403 carrying a machine error envelope ``{"message": "Forbidden"}``.

    Measured on ``api.uspto.gov``, the three cases are cleanly distinguishable and each needs a
    different fix:

    * no credential      -> ``401 {"message":"Unauthorized"}``
    * **bad credential** -> **``403 {"message":"Forbidden"}``**
    * no such route      -> ``403 {"message":"Missing Authentication Token"}``

    Reporting a rejected key as "the operator refuses automated access" would send a reader
    looking for a policy problem when the answer is "your key is wrong or expired". The
    detection is deliberately narrow - a JSON object with a ``message`` field whose value is
    exactly ``Forbidden`` - so an HTML error page from some other host never matches.
    """

    retryable = False
    kind = "CREDENTIAL_REJECTED"


#: Body text that identifies each of the cases above, matched case-insensitively.
_BODY_CREDENTIAL = ("UNAUTHORIZED", "AUTHENTICATION REQUIRED")
_BODY_ROUTE_ABSENT = ("MISSING AUTHENTICATION TOKEN",)
_BODY_CREDENTIAL_REJECTED = ("FORBIDDEN",)


class RateLimited(FetchError):
    retryable = True
    kind = "RATE_LIMITED"


class NotFound(FetchError):
    """The path does not exist. Not a refusal and not a transient failure."""

    retryable = False
    kind = "NOT_FOUND"


def _error_body_snippet(error: object, *, limit: int = 200) -> str:
    """The start of an error response body, for the failure record.

    Never raises: a body that cannot be read is worth less than the status code that already arrived.
    """
    try:
        raw = error.read()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - no body, no snippet
        return ""
    if not raw:
        return ""
    if isinstance(raw, bytes):
        text = raw[:limit].decode("utf-8", "replace")
    else:
        text = str(raw)[:limit]
    text = " ".join(text.split())
    return f" | body: {text}" if text else ""


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
    """One completed request. ``body`` is decoded; ``raw_bytes`` is the byte count.

    ``payload`` carries the transport-decoded bytes for a binary document (a PDF, a zip).
    Exactly one of ``body`` and ``payload`` is filled: a text request leaves ``payload``
    empty, a binary request leaves ``body`` empty. A caller can therefore tell "empty
    document" from "document I did not decode" without counting bytes.
    """

    url: str
    status: int
    content_type: str | None
    body: str
    raw_bytes: int
    elapsed_ms: float
    headers: Mapping[str, str] = field(default_factory=dict)
    payload: bytes = b""


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
                                      "rate_limited": 0, "not_found": 0, "failures": 0,
                                      "capability_limits": 0}
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

    def _decompress(self, raw: bytes, headers: Mapping[str, str]) -> bytes:
        """Undo the transport content-encoding. Never validates the payload type.

        Kept separate from charset decoding because a PDF is not text: it needs the
        transport layer undone and nothing else. A caller that decoded a PDF as UTF-8 and
        then parsed it would corrupt every byte above 0x7f and could not tell.
        """
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
        return raw

    def _decode(self, raw: bytes, headers: Mapping[str, str]) -> str:
        raw = self._decompress(raw, headers)
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

    def _read_error_body(self, error: urllib.error.HTTPError
                         ) -> tuple[str | None, str, bool]:
        """Read the error body once and return ``(documented code, raw text, has_message)``.

        The body can only be read once, so the capability-limit test, the refusal
        classification and the "this is a machine error envelope" test all share this read.
        ``has_message`` is true only when the body is a JSON object carrying a ``message``
        field, which is what separates an API's own error from an HTML error page.
        """
        try:
            raw = error.read(4000)
        except (OSError, ValueError):
            return None, "", False
        if not raw:
            return None, "", False
        text = raw.decode("utf-8", "replace")
        code = None
        try:
            payload = json.loads(text)
        except ValueError:
            return None, text, False
        has_message = False
        if isinstance(payload, dict):
            has_message = isinstance(payload.get("message"), str)
            inner = payload.get("error")
            if isinstance(inner, dict):
                code = str(inner.get("code") or "").strip().upper() or None
            elif isinstance(inner, str):
                code = inner.strip().upper() or None
        return code, text, has_message

    def _capability_limit_code(self, error: urllib.error.HTTPError) -> str | None:
        """Backward-compatible single-purpose view used by older call sites."""
        code, _, _ = self._read_error_body(error)
        return code if code in CAPABILITY_LIMIT_CODES else None

    # -------------------------------------------------------------------- fetch
    def get_text(self, url: str, *, headers: Mapping[str, str] | None = None,
                 allow_not_found: bool = False) -> FetchResult:
        return self._request(url, headers=headers, allow_not_found=allow_not_found)

    def post_form(self, url: str, payload: Mapping[str, Any], *,
                  headers: Mapping[str, str] | None = None,
                  allow_not_found: bool = False) -> Any:
        """POST an ``application/x-www-form-urlencoded`` body and return the parsed JSON.

        OAuth token endpoints speak this and nothing else: EPO's ``/auth/accesstoken`` wants
        ``grant_type=client_credentials`` as a form field, and sending the JSON body that
        ``post_json`` produces is rejected without explaining why. Like ``post_json`` this shares
        ``_request``, so pacing, budget, refusal and retry semantics stay identical to every other
        call rather than acquiring a private set.
        """
        body = urllib.parse.urlencode(dict(payload)).encode("utf-8")
        merged = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
        merged.update(headers or {})
        result = self._request(url, headers=merged, allow_not_found=allow_not_found, body=body)
        if result.status == 404 and not result.body:
            return None
        try:
            return json.loads(result.body)
        except ValueError as error:
            raise ParseFailure(f"invalid JSON from {url}: {error}", url=url) from error

    def post_json(self, url: str, payload: Mapping[str, Any], *,
                  headers: Mapping[str, str] | None = None,
                  allow_not_found: bool = False) -> Any:
        """POST a JSON body and return the parsed response.

        Needed because NIH RePORTER v2 exposes ``POST /v2/projects/search`` and nothing else:
        its criteria tree (fiscal years, text operators, field selection, paging) does not fit
        in a query string. Sharing ``_request`` rather than writing a second HTTP client is the
        point - pacing, budget, refusal and capability-limit handling stay in one place, so a
        POST cannot quietly acquire different retry semantics from a GET.
        """
        body = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True).encode("utf-8")
        merged = {"Content-Type": "application/json", "Accept": "application/json"}
        merged.update(headers or {})
        result = self._request(url, headers=merged, allow_not_found=allow_not_found, body=body)
        if result.status == 404 and not result.body:
            return None
        try:
            return json.loads(result.body)
        except ValueError as error:
            raise ParseFailure(f"invalid JSON from {url}: {error}", url=url) from error

    def get_bytes(self, url: str, *, headers: Mapping[str, str] | None = None,
                  allow_not_found: bool = False) -> FetchResult:
        """Fetch a binary document and return the transport-decoded bytes.

        ``FetchResult.payload`` holds the bytes and ``body`` is deliberately empty: a PDF
        decoded as text is already corrupt, and a caller that reads ``body`` first would
        never find out. Retry, pacing, refusal and budget behaviour is identical to
        ``get_text`` because it is the same code path, not a copy of it.
        """
        return self._request(url, headers=headers, allow_not_found=allow_not_found, binary=True)

    def _request(self, url: str, *, headers: Mapping[str, str] | None = None,
                 allow_not_found: bool = False, binary: bool = False,
                 body: bytes | None = None) -> FetchResult:
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
            request = urllib.request.Request(
                url, data=body, headers=request_headers,
                method="POST" if body is not None else "GET",
            )
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
                    code, message, message_field = self._read_error_body(error)
                    if code and code in CAPABILITY_LIMIT_CODES:
                        self.stats["capability_limits"] += 1
                        raise CapabilityLimit(
                            f"{status} {error.reason}: documented capability limit "
                            f"{code}; the source is not refusing access, the request "
                            "must ask for fewer rows or identify itself",
                            url=url, status=status,
                        ) from error
                    upper = (message or "").upper()
                    if status == 401 or any(marker in upper for marker in _BODY_CREDENTIAL):
                        raise CredentialRequired(
                            f"{status} {error.reason}: the route exists and needs a credential; "
                            "configure it rather than treating this as an access refusal",
                            url=url, status=status,
                        ) from error
                    if status == 403 and any(marker in upper for marker in _BODY_ROUTE_ABSENT):
                        raise RouteAbsent(
                            f"{status} {error.reason}: no such route on this host "
                            "(API Gateway signals an unknown path this way)",
                            url=url, status=status,
                        ) from error
                    if (status == 403 and message_field
                            and any(marker in upper for marker in _BODY_CREDENTIAL_REJECTED)):
                        raise CredentialRejected(
                            f"{status} {error.reason}: the credential was rejected; the key is "
                            "wrong, expired or not enabled for this route",
                            url=url, status=status,
                        ) from error
                    raise Refused(
                        f"{status} {error.reason}: the source refused automated access; "
                        "MedRadar records the refusal and does not attempt to bypass it",
                        url=url, status=status,
                    ) from error
                elif status == 404:
                    self.stats["not_found"] += 1
                    if allow_not_found:
                        return FetchResult(url=url, status=404, content_type=None, body="",
                                           raw_bytes=0, elapsed_ms=0.0, headers={})
                    raise NotFound(f"404 {error.reason}", url=url, status=status) from error
                elif status == 429:
                    self.stats["rate_limited"] += 1
                    retry_after = self._retry_after(response_headers)
                    last_error = RateLimited("429 Too Many Requests", url=url, status=status,
                                             retry_after=retry_after)
                elif status in RETRYABLE_STATUSES:
                    # Keep what the server actually said. Measured 2026-11-28: europepmc answered a
                    # single request 200 while the scheduler's burst was recorded as "503 " with no body,
                    # which left the two observations impossible to reconcile. The first 200 bytes and
                    # the attempt number now travel with the failure.
                    snippet = _error_body_snippet(error)
                    last_error = TransientHttpError(
                        f"{status} {error.reason}{snippet} [attempt {attempt}]" +
                        (f" {url}" if url else ""),
                        url=url, status=status)
                else:
                    raise FetchError(f"{status} {error.reason}", url=url, status=status) from error
            except (urllib.error.URLError, TimeoutError, OSError,
                    http.client.IncompleteRead, http.client.HTTPException) as error:
                # IncompleteRead is the interesting one: the status line said 200 and the body
                # stopped early. It is a transient transport failure, not a refusal, and it is NOT
                # an OSError - http.client.HTTPException inherits straight from Exception, so it
                # used to escape this handler entirely. Measured on a 999-row MAUDE page (~9 MB):
                # 5,209,171 bytes arrived, 3,643,358 were missing, and the sweep died on it.
                self.log.append({"url": url, "status": None, "attempt": attempt, "error": str(error)})
                last_error = NetworkFailure(f"{type(error).__name__}: {error}", url=url)
            else:
                elapsed = round((time.perf_counter() - started) * 1000.0, 1)
                self.stats["bytes"] += len(raw)
                body = "" if binary else self._decode(raw, response_headers)
                payload = self._decompress(raw, response_headers) if binary else b""
                self.log.append({"url": url, "status": status, "bytes": len(raw), "attempt": attempt})
                return FetchResult(
                    url=url, status=status,
                    content_type=response_headers.get("Content-Type"),
                    body=body, raw_bytes=len(raw), elapsed_ms=elapsed,
                    headers=response_headers, payload=payload,
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
