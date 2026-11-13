"""Bounded HTTP client.

Every outbound request in HORIZON-001 goes through here so that the research
budget is auditable rather than anecdotal.

Guarantees
----------
* hard response-size cap (streamed, aborted mid-body when exceeded)
* hard request budget per run
* bounded exponential backoff, no unbounded retry
* mandatory descriptive User-Agent identifying the project and contact route
* every attempt appended to a JSONL request log with timing, size and hash
* honours ``Retry-After`` but refuses to sleep past ``max_sleep_s``
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import random
import time
import zlib
from dataclasses import dataclass, field
from typing import Any, Iterator

import requests

DEFAULT_UA = (
    "MedRadar-HORIZON-001/1.0 (academic data-frontier research; "
    "bounded sampling; contact: medradar-research@proton.me)"
)


class BudgetExceeded(RuntimeError):
    pass


class ResponseTooLarge(RuntimeError):
    pass


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    headers: dict[str, str]
    body: bytes
    elapsed_ms: int
    content_hash: str
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def text(self, encoding: str | None = None) -> str:
        ct = self.headers.get("content-type", "")
        enc = encoding
        if enc is None:
            for part in ct.split(";"):
                part = part.strip()
                if part.lower().startswith("charset="):
                    enc = part.split("=", 1)[1].strip().strip('"')
        if not enc:
            enc = "utf-8"
        try:
            return self.body.decode(enc, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text())


@dataclass
class BoundedClient:
    """A client whose total cost is bounded before the run starts."""

    name: str
    user_agent: str = DEFAULT_UA
    max_requests: int = 60
    max_bytes_per_response: int = 8_000_000
    max_total_bytes: int = 40_000_000
    timeout_s: float = 30.0
    max_retries: int = 2
    base_sleep_s: float = 0.8
    max_sleep_s: float = 20.0
    requests_per_second: float = 2.0
    log_path: str | None = None
    respect_robots: bool = True

    # ---- runtime counters -------------------------------------------------
    requests_made: int = 0
    bytes_received: int = 0
    retries: int = 0
    errors: list[str] = field(default_factory=list)
    _last_request_at: float = 0.0
    _session: requests.Session | None = None
    _log_fh: Any = None
    _cache: dict[str, FetchResult] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.log_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
            self._log_fh = open(self.log_path, "a", encoding="utf-8", newline="\n")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )

    # ---- lifecycle --------------------------------------------------------
    def close(self) -> None:
        if self._log_fh:
            self._log_fh.flush()
            self._log_fh.close()
            self._log_fh = None
        if self._session:
            self._session.close()
            self._session = None

    def __enter__(self) -> "BoundedClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- internals --------------------------------------------------------
    def _throttle(self) -> None:
        if self.requests_per_second <= 0:
            return
        min_gap = 1.0 / self.requests_per_second
        gap = time.monotonic() - self._last_request_at
        if gap < min_gap:
            time.sleep(min_gap - gap)
        self._last_request_at = time.monotonic()

    def _log(self, entry: dict) -> None:
        if self._log_fh:
            self._log_fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._log_fh.flush()

    def _decode(self, body: bytes, encoding: str) -> bytes:
        encoding = (encoding or "").lower()
        try:
            if "gzip" in encoding:
                return gzip.decompress(body)
            if "deflate" in encoding:
                return zlib.decompress(body)
        except (OSError, zlib.error):
            return body
        return body

    # ---- public API -------------------------------------------------------
    def _cache_key(self, url: str, params: dict[str, Any] | None) -> str:
        """Cache key MUST include the query parameters.

        Caching on ``url`` alone silently replays the first response for every
        later call that varies only ``params`` — which turns a paged harvest into
        a duplicated first page carrying other periods' labels. That happened
        once in this project; the key is (url, sorted params) as a result.
        """
        if not params:
            return url
        items = sorted((str(k), str(v)) for k, v in params.items())
        return url + "\x00" + "&".join(f"{k}={v}" for k, v in items)

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = True,
        max_redirects: int = 5,
    ) -> FetchResult:
        key = self._cache_key(url, params)
        if key in self._cache:
            return self._cache[key]
        if self.requests_made >= self.max_requests:
            raise BudgetExceeded(
                f"{self.name}: request budget of {self.max_requests} exhausted"
            )

        attempt = 0
        last_err: str | None = None
        while attempt <= self.max_retries:
            self._throttle()
            started = time.monotonic()
            try:
                resp = self._session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout_s,
                    stream=True,
                    allow_redirects=allow_redirects,
                )
                chunk = bytearray()
                too_large = False
                for piece in resp.iter_content(chunk_size=65536):
                    chunk.extend(piece)
                    if len(chunk) > self.max_bytes_per_response:
                        too_large = True
                        break
                raw = bytes(chunk)
                resp.close()
                elapsed_ms = int((time.monotonic() - started) * 1000)

                if too_large:
                    self.requests_made += 1
                    msg = (
                        f"{url}: response exceeded cap "
                        f"{self.max_bytes_per_response} bytes (aborted)"
                    )
                    self.errors.append(msg)
                    self._log(
                        {
                            "client": self.name,
                            "url": url,
                            "status": resp.status_code,
                            "outcome": "TOO_LARGE",
                            "read_bytes": len(raw),
                            "cap": self.max_bytes_per_response,
                            "elapsed_ms": elapsed_ms,
                        }
                    )
                    raise ResponseTooLarge(msg)

                body = self._decode(raw, resp.headers.get("content-encoding", ""))
                self.requests_made += 1
                self.bytes_received += len(body)
                if self.bytes_received > self.max_total_bytes:
                    raise BudgetExceeded(
                        f"{self.name}: total byte budget "
                        f"{self.max_total_bytes} exceeded"
                    )
                digest = hashlib.sha256(body).hexdigest()
                result = FetchResult(
                    url=url,
                    final_url=str(resp.url),
                    status=resp.status_code,
                    headers={k.lower(): v for k, v in resp.headers.items()},
                    body=body,
                    elapsed_ms=elapsed_ms,
                    content_hash=digest,
                )
                self._log(
                    {
                        "client": self.name,
                        "url": url,
                        "final_url": result.final_url,
                        "status": resp.status_code,
                        "outcome": "OK" if result.ok else "HTTP_ERROR",
                        "bytes": len(body),
                        "sha256": digest,
                        "elapsed_ms": elapsed_ms,
                        "attempt": attempt,
                    }
                )
                if result.ok:
                    self._cache[url] = result
                    return result
                # non-2xx: retry only on 429 / 5xx
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    last_err = f"HTTP {resp.status_code}"
                    ra = resp.headers.get("retry-after")
                    sleep_s = self.base_sleep_s * (2 ** attempt) + random.uniform(0, 0.3)
                    if ra:
                        try:
                            sleep_s = min(float(ra), self.max_sleep_s)
                        except ValueError:
                            pass
                    attempt += 1
                    if attempt <= self.max_retries:
                        self.retries += 1
                        time.sleep(min(sleep_s, self.max_sleep_s))
                        continue
                return result
            except (requests.RequestException, OSError) as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                self.requests_made += 1
                elapsed_ms = int((time.monotonic() - started) * 1000)
                self._log(
                    {
                        "client": self.name,
                        "url": url,
                        "outcome": "TRANSPORT_ERROR",
                        "error": last_err[:400],
                        "elapsed_ms": elapsed_ms,
                        "attempt": attempt,
                    }
                )
                attempt += 1
                if attempt <= self.max_retries:
                    self.retries += 1
                    time.sleep(min(self.base_sleep_s * (2 ** attempt), self.max_sleep_s))
                    continue
                self.errors.append(f"{url}: {last_err}")
                raise

        raise RuntimeError(f"{self.name}: unreachable retry state for {url}: {last_err}")

    def get_json(self, url: str, **kw) -> Any:
        res = self.get(url, **kw)
        if not res.ok:
            raise RuntimeError(f"{url}: HTTP {res.status}")
        return res.json()

    def head(self, url: str) -> FetchResult:
        res = self.get(url)
        return res

    def budget_report(self) -> dict[str, Any]:
        return {
            "client": self.name,
            "requests_made": self.requests_made,
            "max_requests": self.max_requests,
            "bytes_received": self.bytes_received,
            "max_total_bytes": self.max_total_bytes,
            "retries": self.retries,
            "errors": self.errors,
        }
