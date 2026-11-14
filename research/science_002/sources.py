"""Cached, provenance-preserving HTTP for SCIENCE-002 (SEC EDGAR + openFDA).

Same rationale as `research/science_001/edgar.py`: a point-in-time study must be
able to say, separately, (a) what a source *published*, (b) when the source
server says the bytes existed, and (c) when *we* collected them. The cache
therefore stores one body plus one JSON sidecar per URL, and every derived
artifact records the SHA-256 of the exact bytes it was built from.

Network policy
--------------
* one real User-Agent naming the study and a contact address;
* a configurable inter-request delay (SEC: 0.35 s, openFDA: 0.30 s);
* a per-run request budget so a runaway loop cannot hammer a public API;
* every response cached, so re-runs and `--offline` replays never refetch.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STUDY_DIR = Path(__file__).resolve().parent
CACHE_DIR = Path(os.environ.get("MEDRADAR_S2_CACHE", str(STUDY_DIR / "data" / "cache")))

SEC_CONTACT = os.environ.get("MEDRADAR_SEC_CONTACT") or "admin@medradar.example"
SEC_UA = os.environ.get("MEDRADAR_SEC_UA") or ("MedRadar-Research science-002 " + SEC_CONTACT)
FDA_UA = os.environ.get("MEDRADAR_FDA_UA") or "MedRadar-Research science-002 (openFDA bulk export)"

DEFAULT_DELAY_SEC = 0.34
MAX_RUN_REQUESTS = 4000


class SourceError(RuntimeError):
    pass


class BudgetExceeded(SourceError):
    pass


class OfflineMiss(SourceError):
    pass


def utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


@dataclass
class Response:
    url: str
    status: int
    body: bytes
    headers: dict[str, str]
    fetched_at_utc: str
    from_cache: bool
    sha256: str

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


@dataclass
class Cache:
    """One body + one provenance sidecar per URL, plus a per-run request budget."""

    root: Path = CACHE_DIR
    offline: bool = False
    delay: float = DEFAULT_DELAY_SEC
    budget: int = MAX_RUN_REQUESTS
    _used: int = field(default=0, init=False)
    _last: float = field(default=0.0, init=False)

    def _paths(self, url: str) -> tuple[Path, Path]:
        key = _cache_key(url)
        return self.root / (key + ".bin"), self.root / (key + ".json")

    def get(self, url: str, *, ua: str = SEC_UA, accept: str | None = None,
            refresh: bool = False) -> Response:
        body_path, meta_path = self._paths(url)
        if body_path.exists() and meta_path.exists() and not refresh:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            body = body_path.read_bytes()
            digest = sha256_bytes(body)
            if digest != meta.get("sha256"):
                raise SourceError(f"cache corruption for {url}: hash mismatch")
            return Response(url, int(meta["status"]), body, meta.get("headers", {}),
                            meta["fetched_at_utc"], True, digest)

        if self.offline:
            raise OfflineMiss(f"offline and not cached: {url}")
        if self._used >= self.budget:
            raise BudgetExceeded(f"request budget {self.budget} exhausted")

        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        headers = {"User-Agent": ua, "Accept-Encoding": "identity"}
        if accept:
            headers["Accept"] = accept
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=90) as raw:
                status = int(getattr(raw, "status", 200))
                body = raw.read()
                hdrs = {k.lower(): v for k, v in raw.headers.items()}
        except urllib.error.HTTPError as exc:  # record the status, do not hide it
            status = int(exc.code)
            body = exc.read()
            hdrs = {k.lower(): v for k, v in (exc.headers or {}).items()}
        self._last = time.monotonic()
        self._used += 1

        if 300 <= status < 400:
            raise SourceError(f"redirect (unexpected) status={status} for {url}")
        if status >= 400:
            raise SourceError(f"HTTP {status} for {url}: {body[:200]!r}")

        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_bytes(body)
        digest = sha256_bytes(body)
        meta = {
            "url": url,
            "status": status,
            "headers": hdrs,
            "fetched_at_utc": utc_now(),
            "sha256": digest,
            "bytes": len(body),
        }
        meta_path.write_text(json.dumps(meta, indent=1), encoding="utf-8")
        return Response(url, status, body, hdrs, meta["fetched_at_utc"], False, digest)

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self.get(url, **kwargs).json()

    def download(self, url: str, target: Path, *, ua: str = FDA_UA,
                 refresh: bool = False) -> dict[str, Any]:
        """Resumable large-file download with a verification sidecar.

        Kept separate from `get` because a 200+ MB ZIP must not be read into
        memory. Resumption uses a `.part` file and an HTTP Range request; a
        server that ignores Range is detected and the part file is restarted.
        """
        target.parent.mkdir(parents=True, exist_ok=True)
        meta_path = target.with_suffix(target.suffix + ".json")
        if target.exists() and not refresh:
            digest = sha256_bytes(target.read_bytes())
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("sha256") in (None, digest):
                    return {**meta, "sha256": digest, "from_cache": True}
            return {"url": url, "bytes": target.stat().st_size, "sha256": digest,
                    "from_cache": True, "fetched_at_utc": None}
        if self.offline:
            raise OfflineMiss(f"offline and not downloaded: {url}")

        part = target.with_suffix(target.suffix + ".part")
        offset = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": ua}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=180) as raw:
            status = int(getattr(raw, "status", 200))
            append = bool(offset and status == 206)
            mode = "ab" if append else "wb"
            with part.open(mode) as handle:
                while True:
                    block = raw.read(4 * 1024 * 1024)
                    if not block:
                        break
                    handle.write(block)
        part.replace(target)
        digest = sha256_bytes(target.read_bytes())
        meta = {"url": url, "bytes": target.stat().st_size, "sha256": digest,
                "fetched_at_utc": utc_now(), "from_cache": False}
        meta_path.write_text(json.dumps(meta, indent=1), encoding="utf-8")
        return meta