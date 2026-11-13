"""Polite, provenance-preserving SEC EDGAR client for SCIENCE-001.

Why this module does not simply call medradar.http.Fetcher
----------------------------------------------------------
Fetcher caches response *bodies*. A point-in-time study needs the response
*headers* too: the archival Last-Modified of a document is the only
server-side evidence of when that document was actually written into EDGAR's
public archive, and it is the strongest available bound on public
dissemination. It also needs the collection time of every request stored
beside the body, so "when we fetched it" can never leak into "when the world
could see it".

So this module keeps one body file plus one provenance sidecar per URL. It
re-uses medradar.util for hashing and timestamps and nothing else from the
package, which keeps the research code independently reviewable.

Network policy (SEC developer / fair-access terms)
--------------------------------------------------
* a real User-Agent that names the study and a contact URL;
* at most ~3 requests/second (default 0.35 s spacing, well under SEC's 10/s);
* every response cached on disk, so re-runs and offline replays never refetch;
* a hard per-run request budget, so a runaway loop cannot hammer sec.gov.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # allow: python research/science_001/cli.py
    sys.path.insert(0, str(_ROOT))

from medradar.util import ensure_dir, utc_now_iso  # noqa: E402

#: SEC's edge rejects a User-Agent that embeds a URL (observed: HTTP 403 for
#: every variant containing "+https://..."), and requires a contact address.
#: Keep this string email-shaped and URL-free. Override with MEDRADAR_SEC_CONTACT
#: when running from a real deployment.
SEC_CONTACT = os.environ.get("MEDRADAR_SEC_CONTACT") or "admin@medradar.example"
USER_AGENT = os.environ.get("MEDRADAR_SEC_UA") or (
    "MedRadar-Research science-001 " + SEC_CONTACT)

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/{accession}.txt"
ARCHIVE_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/index.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


class EdgarError(RuntimeError):
    pass


class BudgetExceeded(EdgarError):
    pass


class OfflineMiss(EdgarError):
    pass


# --------------------------------------------------------------------------- #
# issuer registry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Issuer:
    """One listed medical-technology / medical-device issuer.

    identity_basis is recorded, never inferred: the ticker->CIK mapping comes
    from SEC's own company_tickers.json and the CIK->name/SIC from the
    submissions endpoint, both captured at fetch time.
    """

    key: str
    ticker: str
    cik: str
    segment: str
    panel: bool = True
    note: str = ""


#: Twelve issuers covering large-cap medical devices, diagnostics, imaging and
#: surgical robotics. panel=False issuers are foreign private issuers filing
#: 20-F/6-K rather than 8-K; they stay in the timezone-verification strata (a
#: different form family must still obey the same clock) but are excluded from
#: the 8-K panel so the observation unit stays comparable.
ISSUERS: tuple[Issuer, ...] = (
    Issuer("mdt", "MDT", "0001613103", "cardiovascular / neuro / diabetes devices",
           note="Medtronic plc (Irish domicile, US 8-K filer)"),
    Issuer("gehc", "GEHC", "0001932393", "medical imaging",
           note="GE HealthCare Technologies; first 8-K 2022-07, spun out 2023-01"),
    Issuer("bax", "BAX", "0000010456", "hospital products / renal"),
    Issuer("syk", "SYK", "0000310764", "orthopaedics / surgical"),
    Issuer("bsx", "BSX", "0000885725", "interventional cardiology"),
    Issuer("abt", "ABT", "0000001800", "diagnostics / devices / nutrition"),
    Issuer("ew", "EW", "0001099800", "structural heart"),
    Issuer("zbh", "ZBH", "0001136869", "orthopaedics"),
    Issuer("isrg", "ISRG", "0001035267", "surgical robotics"),
    Issuer("dxcm", "DXCM", "0001093557", "diabetes sensing"),
    Issuer("rmd", "RMD", "0000943819", "sleep apnoea devices"),
    Issuer("phg", "PHG", "0000313216", "imaging / monitoring (foreign private issuer)",
           panel=False, note="files 20-F/6-K, not 8-K; time-semantics strata only"),
)

ISSUER_BY_KEY = {i.key: i for i in ISSUERS}

#: Forms that constitute one disclosure event in the panel.
PANEL_FORMS: tuple[str, ...] = ("8-K", "8-K/A")


# --------------------------------------------------------------------------- #
# response cache with provenance
# --------------------------------------------------------------------------- #
@dataclass
class Response:
    url: str
    status: int
    body: bytes
    headers: dict[str, str]
    fetched_at_utc: str
    from_cache: bool
    sha256: str
    attempts: int = 1

    def text(self) -> str:
        # EDGAR archives mix latin-1 and utf-8; replacement keeps the call total
        # while never silently raising on one bad byte.
        return self.body.decode("utf-8", errors="replace")

    def last_modified(self) -> str | None:
        for key, value in self.headers.items():
            if key.lower() == "last-modified":
                return value
        return None


class EdgarClient:
    """GET with on-disk cache, per-request provenance, throttling and budget."""

    def __init__(
        self,
        cache_dir: str | Path,
        offline: bool = False,
        min_interval: float = 0.35,
        timeout: float = 60.0,
        max_requests: int = 4000,
        ua: str = USER_AGENT,
        retries: int = 3,
    ) -> None:
        self.cache_dir = ensure_dir(cache_dir)
        self.offline = bool(offline)
        self.min_interval = float(min_interval)
        self.timeout = float(timeout)
        self.max_requests = int(max_requests)
        self.ua = ua
        self.retries = int(retries)
        self.stats = {"requests": 0, "cache_hits": 0, "errors": 0, "retries": 0}
        self._last = 0.0

    # -- public ------------------------------------------------------------
    def get(self, url: str, refresh: bool = False) -> Response:
        body_path, meta_path = self._paths(url)
        if not refresh and body_path.exists() and meta_path.exists():
            self.stats["cache_hits"] += 1
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return Response(
                url=url,
                status=int(meta["status"]),
                body=body_path.read_bytes(),
                headers=dict(meta.get("headers") or {}),
                fetched_at_utc=meta["fetched_at_utc"],
                from_cache=True,
                sha256=meta["sha256"],
            )
        if self.offline:
            raise OfflineMiss("no cached response and offline=True: " + url)
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            self._throttle()
            self._charge()
            try:
                request = urllib.request.Request(url, headers={
                    "User-Agent": self.ua,
                    "Accept": "text/html,application/xhtml+xml,application/json,text/plain,*/*",
                    "Accept-Encoding": "gzip",
                })
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    if "gzip" in (response.headers.get("Content-Encoding") or ""):
                        raw = gzip.decompress(raw)
                    headers = {k: v for k, v in response.headers.items()
                               if k.lower() in ("content-type", "last-modified", "date",
                                                "etag", "content-length")}
                    status = int(response.status)
                sha = hashlib.sha256(raw).hexdigest()
                fetched = utc_now_iso()
                body_path.write_bytes(raw)
                meta_path.write_text(json.dumps({
                    "url": url,
                    "status": status,
                    "headers": headers,
                    "fetched_at_utc": fetched,
                    "sha256": sha,
                    "bytes": len(raw),
                    "attempts": attempt,
                }, indent=1, sort_keys=True), encoding="utf-8")
                return Response(url, status, raw, headers, fetched, False, sha, attempt)
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code == 404:
                    self.stats["errors"] += 1
                    raise EdgarError("HTTP 404 for " + url) from exc
                if exc.code == 429 or 500 <= exc.code < 600:
                    self.stats["retries"] += 1
                    time.sleep(min(30.0, 2.0 ** attempt))
                    continue
                self.stats["errors"] += 1
                raise EdgarError("HTTP %d for %s" % (exc.code, url)) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                self.stats["retries"] += 1
                time.sleep(min(30.0, 2.0 ** attempt))
        self.stats["errors"] += 1
        raise EdgarError("retries exhausted for %s: %r" % (url, last_error))

    def json(self, url: str, refresh: bool = False) -> Any:
        response = self.get(url, refresh=refresh)
        try:
            return json.loads(response.body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise EdgarError("invalid JSON from " + url) from exc

    # -- conveniences ------------------------------------------------------
    def submissions(self, issuer: Issuer) -> dict[str, Any]:
        return self.json(SUBMISSIONS_URL.format(cik=issuer.cik))

    def submission_rows(self, issuer: Issuer, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten filings.recent into one dict per filing (as delivered)."""
        recent = ((payload.get("filings") or {}).get("recent") or {})
        fields = list(recent.keys())
        if not fields:
            return []
        rows: list[dict[str, Any]] = []
        for index in range(len(recent[fields[0]])):
            row = {name: recent[name][index] for name in fields}
            row["issuer"] = issuer.key
            row["cik"] = issuer.cik
            rows.append(row)
        return rows

    def full_submission(self, issuer: Issuer, accession: str,
                        refresh: bool = False) -> Response:
        return self.get(filing_url(issuer.cik, accession), refresh=refresh)

    # -- internals ---------------------------------------------------------
    def _paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        return self.cache_dir / (key + ".bin"), self.cache_dir / (key + ".meta.json")

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def _charge(self) -> None:
        if self.stats["requests"] >= self.max_requests:
            raise BudgetExceeded(
                "request budget %d exhausted; re-run to resume" % self.max_requests)
        self.stats["requests"] += 1


# --------------------------------------------------------------------------- #
# raw submission parsing
# --------------------------------------------------------------------------- #
_ACC_TAG = re.compile(r"<ACCEPTANCE-DATETIME>\s*(\d{14})")
_ACC_COLON = re.compile(r"ACCEPTANCE-DATETIME:\s*(\d{14})")
_FILED_AS_OF = re.compile(r"FILED AS OF DATE:\s*(\d{8})")
_CONFORMED_TYPE = re.compile(r"CONFORMED SUBMISSION TYPE:\s*([^\r\n]+)")
_ITEM_INFO = re.compile(r"ITEM INFORMATION:\s*([^\r\n]+)")
_PUBLIC_DOC_COUNT = re.compile(r"PUBLIC DOCUMENT COUNT:\s*(\d+)")
_ACCESSION_NO = re.compile(r"ACCESSION NUMBER:\s*(\S+)")
_CENTRAL_INDEX = re.compile(r"CENTRAL INDEX KEY:\s*(\d+)")
_COMPANY_NAME = re.compile(r"COMPANY CONFORMED NAME:\s*([^\r\n]+)")
_SEC_DOCUMENT_STAMP = re.compile(r"<SEC-DOCUMENT>\S+\s*:\s*(\d{8})")
_FILE_NUMBER = re.compile(r"SEC FILE NUMBER:\s*(\S+)")

_DOCUMENT_BLOCK = re.compile(r"<DOCUMENT>(.*?)</DOCUMENT>", re.S)
_DOC_TYPE = re.compile(r"<TYPE>([^\r\n<]+)")
_DOC_FILENAME = re.compile(r"<FILENAME>([^\r\n<]+)")
_DOC_TEXT = re.compile(r"<TEXT>(.*?)</TEXT>", re.S)


@dataclass
class SubmissionHeader:
    """Everything the primitive EDGAR header asserts about one filing."""

    accession: str | None
    acceptance_raw: str | None      # YYYYMMDDHHMMSS, US/Eastern wall clock
    filed_as_of: str | None         # YYYYMMDD
    conformed_type: str | None
    items: list[str] = field(default_factory=list)
    public_document_count: int | None = None
    cik: str | None = None
    company: str | None = None
    file_number: str | None = None
    sec_document_stamp: str | None = None
    header_format: str | None = None   # "tag" | "colon"
    present: bool = False


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def parse_header(text: str) -> SubmissionHeader:
    """Parse the SEC-HEADER block of a full EDGAR submission.

    Two encodings exist in the wild: the SGML-ish ACCEPTANCE-DATETIME tag used
    by the archive .txt files, and the older key form. Both are accepted and the
    observed encoding is recorded, because which primitive field we actually
    read is part of the evidence.
    """
    tag = _ACC_TAG.search(text)
    colon = _ACC_COLON.search(text) if tag is None else None
    raw = tag.group(1) if tag else (colon.group(1) if colon else None)
    count = _first(_PUBLIC_DOC_COUNT, text)
    items = [value.strip() for value in _ITEM_INFO.findall(text)]
    return SubmissionHeader(
        accession=_first(_ACCESSION_NO, text),
        acceptance_raw=raw,
        filed_as_of=_first(_FILED_AS_OF, text),
        conformed_type=_first(_CONFORMED_TYPE, text),
        items=sorted(set(items)),
        public_document_count=int(count) if count and count.isdigit() else None,
        cik=_first(_CENTRAL_INDEX, text),
        company=_first(_COMPANY_NAME, text),
        file_number=_first(_FILE_NUMBER, text),
        sec_document_stamp=_first(_SEC_DOCUMENT_STAMP, text),
        header_format="tag" if tag else ("colon" if colon else None),
        present=raw is not None,
    )


@dataclass
class RawDocument:
    doc_type: str
    filename: str
    text: str

    @property
    def is_text_like(self) -> bool:
        return self.filename.lower().endswith((".htm", ".html", ".txt", ".xml"))


def parse_documents(text: str) -> list[RawDocument]:
    """Split a full submission into its DOCUMENT parts (header excluded)."""
    documents: list[RawDocument] = []
    for block in _DOCUMENT_BLOCK.findall(text):
        doc_type = (_first(_DOC_TYPE, block) or "").strip()
        filename = (_first(_DOC_FILENAME, block) or "").strip()
        body = _DOC_TEXT.search(block)
        documents.append(RawDocument(doc_type=doc_type, filename=filename,
                                     text=body.group(1) if body else ""))
    return documents


#: Document types that can carry prose and therefore a word count.
_PROSE_TYPES = ("8-K", "EX-99", "EX-10")


def content_documents(documents: Iterable[RawDocument]) -> list[RawDocument]:
    """Documents that carry prose: the 8-K body and its EX-99/EX-10 exhibits.

    Non-text attachments (GRAPHIC, ZIP, PDF, EXCEL, XML) are skipped: they are
    binary or base64 inside the archive and carry no word counts.
    """
    keep: list[RawDocument] = []
    for document in documents:
        kind = document.doc_type.upper()
        if kind.startswith("GRAPHIC") or kind in ("ZIP", "PDF", "EXCEL", "XML"):
            continue
        if kind.startswith(_PROSE_TYPES) and document.text.strip():
            keep.append(document)
    return keep


def filing_url(cik: str, accession: str) -> str:
    return ARCHIVE_DOC_URL.format(cik=int(cik), accn=accession.replace("-", ""),
                                  accession=accession)
