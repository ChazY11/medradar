"""Small, auditable openFDA HTTP client.

No background thread, no async dependency and no implicit retry storm. The client:

* spends from a persistent per-day request budget before each network attempt;
* applies a conservative client-side rate limit;
* retries 429/5xx/network failures with bounded exponential backoff and honours
  ``Retry-After`` for 429;
* treats a 404 as an empty search result only when a search filter was explicitly
  supplied and the error body is openFDA's ``NOT_FOUND`` response;
* records the request URL without credentials and never logs the API key.
"""
from __future__ import annotations

import base64
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .config import Settings
from .db import StateStore
from .model import SourceSpec, iso_now


class OpenFDAError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, url: str | None = None,
                 evidence: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.url = url
        self.evidence = evidence or {}


class RequestBudgetExceeded(OpenFDAError):
    pass


@dataclass
class FetchResult:
    data: dict[str, Any]
    http_status: int
    url: str
    bytes: int
    elapsed_ms: float
    empty: bool = False


def build_url(base: str, path: str, params: list[tuple[str, str]] | dict[str, Any] | None = None) -> str:
    if params is None:
        query = ""
    else:
        items = params.items() if isinstance(params, dict) else params
        query = urllib.parse.urlencode(list(items), doseq=True)
    return base.rstrip("/") + path + (("?" + query) if query else "")


class OpenFDAClient:
    def __init__(
        self,
        settings: Settings,
        store: StateStore,
        *,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.store = store
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep
        self._clock = clock
        self._last_request = 0.0
        self._min_interval = 60.0 / max(1, settings.requests_per_minute)

    # ------------------------------------------------------------------ internals
    def _day(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _authorization_header(self) -> dict[str, str]:
        if not self.settings.api_key:
            return {}
        token = base64.b64encode((self.settings.api_key + ":").encode("utf-8")).decode("ascii")
        return {"Authorization": "Basic " + token}

    def _spend(self, source_id: str, count: int = 1) -> None:
        limit = int(self.settings.daily_request_limit or 900)
        if not self.store.consume_request_budget(self._day(), source_id, limit, count=count):
            raise RequestBudgetExceeded(
                "openFDA daily request budget exhausted for " + self._day()
                + " (limit " + str(limit) + "); no data was changed",
                evidence={"day": self._day(), "limit": limit},
            )

    def _add_bytes(self, source_id: str, byte_count: int) -> None:
        self.store.consume_request_budget(self._day(), source_id, 10**12, count=0, response_bytes=byte_count)

    def _pace(self) -> None:
        elapsed = self._clock() - self._last_request
        wait = self._min_interval - elapsed
        if wait > 0:
            self._sleep(wait)

    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": self.settings.user_agent,
            "Accept": "application/json",
        }
        headers.update(self._authorization_header())
        return headers

    def _read_error(self, error: urllib.error.HTTPError) -> tuple[str, dict[str, Any]]:
        raw = b""
        try:
            raw = error.read()
        except Exception:
            pass
        text = raw.decode("utf-8", "replace")
        payload: dict[str, Any] = {}
        try:
            payload = json.loads(text)
        except ValueError:
            pass
        return text[:1000], payload

    # ------------------------------------------------------------------ public
    def fetch(
        self,
        path: str,
        params: list[tuple[str, str]] | dict[str, Any] | None,
        *,
        source_id: str,
        allow_empty: bool = False,
        context: str = "",
    ) -> FetchResult:
        url = build_url(self.settings.api_base, path, params)
        search_supplied = bool(isinstance(params, dict) and params.get("search")) or bool(
            not isinstance(params, dict) and params and any(key == "search" for key, _ in params)
        )
        last_error: Exception | None = None
        for attempt in range(1, int(self.settings.retries) + 2):
            self._spend(source_id)
            self._pace()
            started = time.perf_counter()
            request = urllib.request.Request(url, headers=self._headers())
            try:
                with self._opener(request, timeout=self.settings.timeout_seconds) as response:
                    raw = response.read()
                    status = int(getattr(response, "status", 200))
                self._last_request = self._clock()
                elapsed = (time.perf_counter() - started) * 1000.0
                self._add_bytes(source_id, len(raw))
                try:
                    data = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, ValueError) as error:
                    raise OpenFDAError(
                        "openFDA returned invalid JSON for " + context,
                        status=status,
                        url=url,
                        evidence={"url": url, "status": status, "bytes": len(raw)},
                    ) from error
                if not isinstance(data, dict):
                    raise OpenFDAError("openFDA returned a non-object JSON document", status=status, url=url)
                return FetchResult(
                    data=data, http_status=status, url=url, bytes=len(raw),
                    elapsed_ms=elapsed, empty=bool(data.get("error")),
                )
            except urllib.error.HTTPError as error:
                self._last_request = self._clock()
                elapsed = (time.perf_counter() - started) * 1000.0
                body, payload = self._read_error(error)
                code = str((payload.get("error") or {}).get("code") or "")
                message = str((payload.get("error") or {}).get("message") or "")
                if error.code == 404 and allow_empty and search_supplied:
                    if code in ("NOT_FOUND", "NO_MATCHES") or "no matches" in message.casefold():
                        return FetchResult(
                            data={"meta": {"results": {"total": 0, "skip": 0, "limit": 0}}, "results": []},
                            http_status=404, url=url, bytes=len(body), elapsed_ms=elapsed, empty=True,
                        )
                evidence = {
                    "url": url,
                    "context": context,
                    "status": error.code,
                    "attempt": attempt,
                    "body": body[:500],
                }
                if error.code == 429:
                    retry_after = error.headers.get("Retry-After") if error.headers else None
                    wait = min(120.0, float(retry_after) if retry_after and retry_after.isdigit() else 2.0 ** attempt)
                    self._sleep(wait)
                    last_error = OpenFDAError("openFDA rate limit (429) for " + context, status=429, url=url, evidence=evidence)
                    continue
                if error.code in (500, 502, 503, 504) and attempt <= int(self.settings.retries):
                    wait = min(60.0, 2.0 ** attempt + random.random() * 0.5)
                    self._sleep(wait)
                    last_error = OpenFDAError(
                        "openFDA server error " + str(error.code) + " for " + context,
                        status=error.code, url=url, evidence=evidence,
                    )
                    continue
                raise OpenFDAError(
                    "openFDA HTTP " + str(error.code) + " for " + context,
                    status=error.code, url=url, evidence=evidence,
                ) from error
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                self._last_request = self._clock()
                evidence = {"url": url, "context": context, "status": "network", "attempt": attempt, "error": str(error)}
                last_error = OpenFDAError("openFDA network failure for " + context, url=url, evidence=evidence)
                if attempt <= int(self.settings.retries):
                    self._sleep(min(60.0, 2.0 ** attempt + random.random() * 0.5))
                    continue
                raise last_error from error
        if last_error is not None:
            raise last_error
        raise OpenFDAError("openFDA request failed for " + context, url=url)

    def fetch_page(
        self,
        path: str,
        params: list[tuple[str, str]] | dict[str, Any],
        *,
        source_id: str,
        context: str,
    ) -> FetchResult:
        return self.fetch(path, params, source_id=source_id, allow_empty=True, context=context)

    # ------------------------------------------------------------------ probes
    def probe(self, source: SourceSpec) -> dict[str, Any]:
        result = self.fetch(
            source.endpoint,
            {"limit": 1},
            source_id=source.source_id,
            allow_empty=False,
            context="source probe " + source.source_id,
        )
        meta = result.data.get("meta") or {}
        results = meta.get("results") or {}
        total = results.get("total")
        last_updated = meta.get("last_updated")
        if total is None:
            raise OpenFDAError(
                "openFDA probe for " + source.source_id + " did not include meta.results.total",
                status=result.http_status,
                url=result.url,
                evidence={"url": result.url, "meta": meta},
            )
        try:
            total_int = int(total)
        except (TypeError, ValueError) as error:
            raise OpenFDAError(
                "openFDA probe for " + source.source_id + " returned a non-numeric total",
                status=result.http_status,
                url=result.url,
                evidence={"url": result.url, "meta": meta},
            ) from error
        return {
            "source_id": source.source_id,
            "checked_at": iso_now(),
            "http_status": result.http_status,
            "url": result.url,
            "bytes": result.bytes,
            "elapsed_ms": result.elapsed_ms,
            "last_updated": str(last_updated) if last_updated else None,
            "total": total_int,
            "meta": {
                "last_updated": last_updated,
                "disclaimer": meta.get("disclaimer"),
                "terms": meta.get("terms"),
                "license": meta.get("license"),
            },
        }
