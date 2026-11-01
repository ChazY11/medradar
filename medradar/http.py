"""Polite HTTP layer: rate limiting, retries, on-disk cache and offline replay.

Design goals
------------
* Never hammer a public API. One request at a time, configurable minimum
  interval, and a hard per-run request budget (openFDA without an API key
  allows 240 requests/minute and 1,000/day per IP).
* Every response is cached under ``data/cache/`` keyed by URL, which makes runs
  resumable and gives us a reproducible data snapshot for the write-up.
* ``offline=True`` replays a fixture/cache directory so tests and CI never
  need network access.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .util import ensure_dir, read_json, write_json

DEFAULT_UA = (
    "medradar/0.1 (open-source FDA industry radar; "
    "+https://github.com/medradar/medradar)"
)


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, body: str = "") -> None:
        super().__init__(f"HTTP {status or 'ERR'} for {url[:200]}")
        self.status = status
        self.url = url
        self.body = body


class NotFound(HttpError):
    """openFDA answers 404 when a search matches zero documents."""


class OfflineMiss(RuntimeError):
    """Offline mode was requested but no cached response exists for this URL."""


class BudgetExceeded(RuntimeError):
    """The per-run request budget is exhausted; resume in a later run."""


class Fetcher:
    def __init__(
        self,
        cache_dir: str | Path | None = None,
        fixtures_dir: str | Path | None = None,
        offline: bool = False,
        min_interval: float = 0.25,
        timeout: float = 45.0,
        max_requests: int = 1200,
        ua: str = DEFAULT_UA,
    ) -> None:
        self.cache_dir = ensure_dir(cache_dir) if cache_dir else None
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else None
        self.offline = offline
        self.min_interval = max(0.0, float(min_interval))
        self.timeout = float(timeout)
        self.max_requests = int(max_requests)
        self.ua = ua
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "errors": 0}
        self._last_request = 0.0

    # ------------------------------------------------------------------ public
    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        retries: int = 3,
        backoff: float = 2.0,
        refresh: bool = False,
    ) -> Any:
        full = self._with_params(url, params)
        key = self._key(full)
        if self.offline:
            payload = self._read_cached(key)
            if payload is None:
                raise OfflineMiss(full)
            self.stats["cache_hits"] += 1
            return payload
        if not refresh:
            payload = self._read_cached(key)
            if payload is not None:
                self.stats["cache_hits"] += 1
                return payload
        payload = self._request_json(full, retries=retries, backoff=backoff)
        if self.cache_dir:
            write_json(self.cache_dir / f"{key}.json", payload, indent=0)
        return payload

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        retries: int = 3,
        backoff: float = 2.0,
        refresh: bool = False,
    ) -> Any:
        """POST JSON with the same cache, throttle and retry contract as GET.

        The request body participates in the cache key, so two award searches
        can never replay each other's results.
        """
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        full = url + "#body=" + hashlib.sha1(body).hexdigest()
        key = self._key(full)
        if self.offline:
            cached = self._read_cached(key)
            if cached is None:
                raise OfflineMiss(full)
            self.stats["cache_hits"] += 1
            return cached
        if not refresh:
            cached = self._read_cached(key)
            if cached is not None:
                self.stats["cache_hits"] += 1
                return cached
        result = self._request_json(full, retries=retries, backoff=backoff, body=body)
        if self.cache_dir:
            write_json(self.cache_dir / f"{key}.json", result, indent=0)
        return result

    def get_text(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        retries: int = 3,
        backoff: float = 2.0,
        refresh: bool = False,
    ) -> str:
        full = self._with_params(url, params)
        key = self._key(full)
        path_candidates = []
        if self.fixtures_dir:
            path_candidates.append(self.fixtures_dir / f"{key}.txt")
        if self.cache_dir:
            path_candidates.append(self.cache_dir / f"{key}.txt")
        if self.offline or not refresh:
            for candidate in path_candidates:
                if candidate.exists():
                    self.stats["cache_hits"] += 1
                    return candidate.read_text(encoding="utf-8", errors="replace")
            if self.offline:
                raise OfflineMiss(full)
        text = self._request_text(full, retries=retries, backoff=backoff)
        if self.cache_dir:
            (self.cache_dir / f"{key}.txt").write_text(text, encoding="utf-8")
        return text

    # ---------------------------------------------------------------- internals
    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha1(url.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _with_params(url: str, params: dict[str, Any] | None) -> str:
        if not params:
            return url
        encoded = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None},
            quote_via=urllib.parse.quote,
            safe="",
        )
        joiner = "&" if "?" in url else "?"
        return f"{url}{joiner}{encoded}"

    def _read_cached(self, key: str) -> Any:
        for base in (self.fixtures_dir, self.cache_dir):
            if not base:
                continue
            path = base / f"{key}.json"
            if path.exists():
                return read_json(path)
        return None

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _charge(self) -> None:
        if self.stats["requests"] >= self.max_requests:
            raise BudgetExceeded(
                f"request budget {self.max_requests} exhausted; re-run later to resume"
            )
        self.stats["requests"] += 1

    @staticmethod
    def _retry_delay(error: urllib.error.HTTPError | None, attempt: int, backoff: float) -> float:
        if error is not None:
            retry_after = error.headers.get("Retry-After") if error.headers else None
            if retry_after:
                try:
                    return min(60.0, float(retry_after))
                except ValueError:
                    pass
        return min(30.0, backoff ** attempt) + 0.1 * attempt

    def _request_json(self, url: str, retries: int, backoff: float, body: bytes | None = None) -> Any:
        last_error: Exception | None = None
        # POST cache keys carry a URL fragment for identity only; fragments are
        # never sent over HTTP and must be stripped from the actual request.
        request_url = url.split("#body=", 1)[0]
        for attempt in range(retries + 1):
            self._throttle()
            self._charge()
            headers = {"User-Agent": self.ua, "Accept": "application/json, */*"}
            if body is not None:
                headers["Content-Type"] = "application/json"
            request = urllib.request.Request(
                request_url,
                data=body,
                headers=headers,
                method="POST" if body is not None else "GET",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                try:
                    return json.loads(raw.decode("utf-8", errors="replace"))
                except json.JSONDecodeError as exc:
                    raise HttpError(0, url, f"invalid JSON: {exc}") from exc
            except urllib.error.HTTPError as exc:
                error_body = ""
                try:
                    error_body = exc.read().decode("utf-8", errors="replace")[:2000]
                except Exception:  # pragma: no cover - defensive
                    pass
                last_error = exc
                if exc.code == 404:
                    raise NotFound(404, url, error_body) from exc
                if exc.code == 429 or 500 <= exc.code < 600:
                    self.stats["retries"] += 1
                    time.sleep(self._retry_delay(exc, attempt, backoff))
                    continue
                self.stats["errors"] += 1
                raise HttpError(exc.code, url, error_body) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                self.stats["retries"] += 1
                time.sleep(self._retry_delay(None, attempt, backoff))
                continue
        self.stats["errors"] += 1
        raise HttpError(0, url, f"retries exhausted: {last_error}")

    def _request_text(self, url: str, retries: int, backoff: float) -> str:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            self._throttle()
            self._charge()
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                error_body = ""
                try:
                    error_body = exc.read().decode("utf-8", errors="replace")[:2000]
                except Exception:  # pragma: no cover - defensive
                    pass
                last_error = exc
                if exc.code == 404:
                    raise NotFound(404, url, error_body) from exc
                if exc.code == 429 or 500 <= exc.code < 600:
                    self.stats["retries"] += 1
                    time.sleep(self._retry_delay(exc, attempt, backoff))
                    continue
                self.stats["errors"] += 1
                raise HttpError(exc.code, url, error_body) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                self.stats["retries"] += 1
                time.sleep(self._retry_delay(None, attempt, backoff))
                continue
        self.stats["errors"] += 1
        raise HttpError(0, url, f"retries exhausted: {last_error}")
