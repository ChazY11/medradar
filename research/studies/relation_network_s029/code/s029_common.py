"""S-029 shared infrastructure: paths, hashing, polite HTTP, JSONL I/O.

Design rules encoded here (they are scientific requirements, not style):

* every HTTP response is recorded in ``data/raw/request_log.jsonl`` with URL,
  retrieval UTC timestamp, HTTP status and body sha256, so that any number in the
  study can be traced back to a specific retrieval;
* raw payloads are stored gzip-compressed exactly as received, so a
  ``payload_hash`` in the evidence table can be re-verified;
* nothing in this module infers, completes or normalises a date. Datetime
  handling is explicit and precision-preserving (see ``parse_date_fields``);
* the collector refuses to silently truncate: paging stops are written into the
  raw envelope.

All timestamps are UTC. The study runs from a single laptop; no cloud, no GPU.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import quote

import requests

# --------------------------------------------------------------------------
# Paths.  The study lives inside the repository worktree; no file is written
# outside research/studies/relation_network_s029/.
# --------------------------------------------------------------------------
STUDY_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = STUDY_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
ARTIFACT_DIR = STUDY_DIR / "artifacts"
for _p in (DATA_DIR, RAW_DIR, ARTIFACT_DIR):
    _p.mkdir(parents=True, exist_ok=True)

EXTRACTION_VERSION = "s029-1.0.0"
CONTACT = "medradar.research@proton.me"

# --------------------------------------------------------------------------
# Hashing / time helpers
# --------------------------------------------------------------------------


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode("utf-8"))


def utcnow_iso() -> str:
    """Real wall clock at the moment of the call. Never a synthesised time."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def utcnow_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# JSONL helpers
# --------------------------------------------------------------------------


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# Polite HTTP client with full provenance logging
# --------------------------------------------------------------------------


@dataclass
class HttpRecord:
    url: str
    retrieved_at: str
    status: int
    body_sha256: str
    n_bytes: int
    source: str
    note: str = ""
    attempts: int = 1


class ProvenanceHTTP:
    """Thin requests wrapper: delay, retry, and a durable request log.

    ``session`` is reused so TLS handshakes are not repeated. The client never
    hides an error: a non-2xx after retries raises ``HttpFailure`` which callers
    are expected to record, not to swallow.
    """

    def __init__(self, source: str, delay_s: float = 0.4, timeout: int = 60,
                 log_path: Path | None = None, user_agent: str | None = None):
        self.source = source
        self.delay_s = delay_s
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or f"medradar-s029/1.0 (research; {CONTACT})",
            "Accept": "application/json",
        })
        self.log_path = log_path or (DATA_DIR / "request_log.jsonl")
        self.calls = 0

    def get(self, url: str, params: dict | None = None, *, note: str = "",
            accept: str | None = None) -> tuple[bytes, HttpRecord]:
        headers = {"Accept": accept} if accept else None
        last_err: Exception | None = None
        for attempt in range(1, 5):
            t0 = time.time()
            if self.calls:
                time.sleep(self.delay_s)
            self.calls += 1
            try:
                resp = self.session.get(url, params=params, headers=headers,
                                        timeout=self.timeout)
                body = resp.content
                rec = HttpRecord(
                    url=resp.url, retrieved_at=utcnow_iso(), status=resp.status_code,
                    body_sha256=sha256_bytes(body), n_bytes=len(body),
                    source=self.source, note=note, attempts=attempt)
                self._log(rec)
                if resp.status_code == 200:
                    return body, rec
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_err = requests.HTTPError(f"HTTP {resp.status_code}")
                    time.sleep(2.0 * attempt + random.random())
                    continue
                raise HttpFailure(f"HTTP {resp.status_code} for {resp.url}: "
                                  f"{body[:300]!r}", rec)
            except requests.RequestException as exc:  # network-layer failure
                last_err = exc
                time.sleep(2.0 * attempt + random.random())
        raise HttpFailure(f"giving up on {url}: {last_err}", None)

    def _log(self, rec: HttpRecord) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(rec.__dict__, ensure_ascii=False, sort_keys=True) + "\n")


class HttpFailure(RuntimeError):
    def __init__(self, msg: str, rec: HttpRecord | None):
        super().__init__(msg)
        self.rec = rec


# --------------------------------------------------------------------------
# Raw payload envelopes: one gzip file per query, content-addressed
# --------------------------------------------------------------------------


def save_raw_envelope(stem: str, envelope: dict) -> Path:
    """Persist a raw retrieval envelope as gzip JSON.

    The envelope must contain the exact source payload plus the retrieval
    provenance. The file name embeds no timestamp so that re-running the
    collector produces a stable, diffable artefact; the retrieval time lives
    inside the envelope.
    """
    path = RAW_DIR / f"{stem}.json.gz"
    blob = json.dumps(envelope, ensure_ascii=False, sort_keys=True).encode("utf-8")
    with gzip.open(path, "wb", compresslevel=9) as fh:
        fh.write(blob)
    return path


def load_raw_envelope(path: Path) -> dict:
    with gzip.open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


# --------------------------------------------------------------------------
# Date handling — precision preserving, never imputing
# --------------------------------------------------------------------------


def classify_date_precision(value: str | None) -> str:
    """Return DAY / MONTH / YEAR / UNKNOWN for an ISO-ish source date string.

    ClinicalTrials.gov publishes struct type information itself; this helper is
    used when only the string is available (e.g. Europe PMC).
    """
    if not value:
        return "UNKNOWN"
    v = value.strip()
    if len(v) >= 10 and v[4] == "-" and v[7] == "-":
        return "DAY"
    if len(v) == 7 and v[4] == "-":
        return "MONTH"
    if len(v) == 4 and v.isdigit():
        return "YEAR"
    return "UNKNOWN"


def norm_name(s: str) -> str:
    """Conservative name normalisation used only for *matching*, never for output.

    Lowercase, strip punctuation to spaces, collapse whitespace, strip a small
    set of legal suffixes that carry no identity information. Accents are folded
    so that Draeger == Dräger for matching; the raw string is always preserved
    alongside the normalised one so the fold can be audited.
    """
    import re
    import unicodedata

    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for suffix in ("inc", "incorporated", "ltd", "limited", "llc", "plc", "corp",
                   "corporation", "co", "company", "gmbh", "ag", "nv", "sa",
                   "kgaa", "bv", "ab", "as", "oy", "spa", "sarl"):
        if s.endswith(" " + suffix):
            s = s[: -(len(suffix) + 1)].strip()
    return s


def q(s: str) -> str:
    return quote(s, safe="")


# --------------------------------------------------------------------------
# Small determinism guard: the study must be reproducible from seeds
# --------------------------------------------------------------------------


def stable_seed(*parts: str) -> int:
    return int(sha256_text("|".join(parts))[:12], 16)
