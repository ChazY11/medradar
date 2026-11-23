"""Build the 510(k) Summary corpus: from 176,683 identifiers to structured text.

The moat, stated plainly
------------------------
A 510(k) clearance row says: this applicant, this device name, this product code, this date.
It does not say what the device does, which predicate it claimed equivalence to, which bench
tests were run or how they were judged. That is in the **510(k) Summary PDF**, one per filing,
and:

* it is public (accessdata.fda.gov serves it anonymously, measured at 6/6 in 0.36 s);
* it is unparsed — no audited platform structures it;
* it is the only public place a manufacturer states its own engineering rationale.

So this module is deliberately boring: enumerate the identifiers, fetch each document, extract
the text layer, split the sections, keep the text, drop the PDF. The interesting part is the
discipline — a resumable store, an honest status per filing, and a report that separates "FDA
published no summary" from "we failed to read it".

Storage budget, measured rather than assumed
--------------------------------------------
A summary PDF is 0.3–2.6 MB, so keeping 176,683 of them is ~170 GB for content we can hold as
text. Extracted text is 12–70 K characters, which is about 3–6 GB for the whole corpus. The
store therefore keeps the text and the metadata and never the PDF.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from .documents import DocumentRecord, DocumentStore, fetch_510k_summary
from .http import OPENFDA_MAX_RECORDS_PER_WINDOW

ENDPOINT = "https://api.fda.gov/device/510k.json"
#: openFDA refuses limit=1000 from an unidentified client; see radar.http.
PAGE_SIZE = 999

#: accessdata.fda.gov answered six consecutive PDF requests in 0.36 s without complaint, so the
#: host is not fragile — but "it did not complain" is not permission to hammer a public
#: document server. Four requests/second is fast enough to finish the obtainable corpus in a
#: few hours and slow enough to stay a polite client.
DEFAULT_REQUESTS_PER_SECOND = 4.0

#: The earliest decision date whose 510(k) Summary is actually **digitised**.
#:
#: openFDA flags a much larger set: 94,291 filings carry ``statement_or_summary == "Summary"``,
#: going back to 1990. Those flags are real, and the documents behind half of them are not on
#: the web. Measured 2026-11-21 by taking five real filings per year and requesting the derived
#: URL:
#:
#: ====== ========= =====
#: year   URL 200   note
#: ====== ========= =====
#: 1998    0/5
#: 1999    0/5
#: 2000    0/5
#: 2001    0/5
#: 2002    0/5
#: 2003    0/5
#: 2004    0/5
#: 2005    0/5
#: 2006    0/5
#: 2007    0/5
#: 2008    0/5
#: 2009    0/5
#: 2010    2/5      April onward; 4/4 from July
#: 2011    5/5
#: 2012+   5/5
#: ====== ========= =====
#:
#: Five alternative path shapes were tried for K002182 and K093456 (``pdf/``, ``pdf2/``,
#: ``pdf2000/``, upper-case extension) and all answer 404, so this is not a URL rule that needs
#: fixing — the scans do not exist publicly.
#:
#: Consequence, and it is the number that matters: the obtainable corpus is **~40,000 flagged
#: filings from 2010-06 onwards, about 37,000 of which resolve**, not 94,291 and not 176,683.
#: A crawl that starts at 1976 spends its first ten hours on certain 404s.
SUMMARY_PDF_FLOOR = "2010-06-01"


def summary_pdf_available(k_number: str) -> bool:
    """Whether a filing's decision year is at or after the digitisation floor.

    Uses the K number's own year rather than a stored date so a caller that has only the
    identifier can still avoid a guaranteed 404.
    """
    text = str(k_number or "").strip().upper()
    match = re.match(r"^K(\d{2})\d{4}$", text)
    if not match:
        return True                      # unknown shape: do not pre-judge it
    return int("20" + match.group(1)) >= int(SUMMARY_PDF_FLOOR[:4])


@dataclass
class CorpusStats:
    """Coverage of one batch. Every field is a count, none is an estimate."""

    attempted: int = 0
    with_text: int = 0
    no_text_layer: int = 0
    not_published: int = 0
    failed: int = 0
    errored: int = 0
    skipped_cached: int = 0
    skipped_pre_digitisation: int = 0
    chars_total: int = 0
    sections_total: int = 0
    by_section: dict[str, int] = field(default_factory=dict)
    last_error: str | None = None
    elapsed_seconds: float = 0.0
    stop_reason: str | None = None

    def record(self, document: DocumentRecord) -> None:
        self.attempted += 1
        if document.from_cache:
            self.skipped_cached += 1
        if document.status == "text":
            self.with_text += 1
            self.chars_total += len(document.text)
            self.sections_total += len(document.sections)
            for key in document.sections:
                self.by_section[key] = self.by_section.get(key, 0) + 1
        elif document.status == "no_text_layer":
            self.no_text_layer += 1
        elif document.status == "not_published":
            self.not_published += 1
        else:
            self.failed += 1

    @property
    def text_rate(self) -> float:
        """Share of *attempted* filings that yielded readable text."""
        return round(self.with_text / self.attempted, 4) if self.attempted else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "with_text": self.with_text,
            "no_text_layer": self.no_text_layer,
            "not_published": self.not_published,
            "failed": self.failed,
            "errored": self.errored,
            "skipped_cached": self.skipped_cached,
            "skipped_pre_digitisation": self.skipped_pre_digitisation,
            "chars_total": self.chars_total,
            "sections_total": self.sections_total,
            "text_rate": self.text_rate,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "by_section": dict(sorted(self.by_section.items(), key=lambda kv: -kv[1])),
            "last_error": self.last_error,
            "stop_reason": self.stop_reason,
        }


# ------------------------------------------------------------------------ index
#: openFDA refuses ``skip`` above 25,000, so one query window can hold at most 25,999 records.
#: Measured 2026-11-21: skip 25,000 -> 200, skip 25,001 -> 400
#: ``{"error":{"code":"BAD_REQUEST","message":"Skip value must 25000 or less."}}``.
#: An earlier version of this module walked 67,718 filings with one plain ``skip`` loop and died
#: at record ~20,000 with that 400. Deep paging is not available, so the index is **partitioned**
#: by decision date instead: a window per calendar year, and per month only where a year
#: overflows. That is 24 requests of counting plus normal paging, versus an unreachable crawl.
WINDOW_CAPACITY = OPENFDA_MAX_RECORDS_PER_WINDOW


def _count(fetcher, clauses: list[str], since: str, until: str) -> int:
    from .http import with_openfda_key

    search = " AND ".join(clauses + [f"decision_date:[{since} TO {until}]"])
    data = fetcher.get_json(
        ENDPOINT, params=with_openfda_key({"search": search, "limit": 1}),
        allow_not_found=True) or {}
    return int(((data.get("meta") or {}).get("results") or {}).get("total") or 0)


def _year_spans(since: str, until: str):
    start = date.fromisoformat(since)
    end = date.fromisoformat(until)
    for year in range(start.year, end.year + 1):
        yield (max(date(year, 1, 1), start).isoformat(),
               min(date(year, 12, 31), end).isoformat())


def _month_spans(since: str, until: str):
    start = date.fromisoformat(since)
    end = date.fromisoformat(until)
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        next_month = (date(cursor.year + 1, 1, 1) if cursor.month == 12
                      else date(cursor.year, cursor.month + 1, 1))
        yield (max(cursor, start).isoformat(),
               min(next_month - timedelta(days=1), end).isoformat())
        cursor = next_month


def _windows(fetcher, clauses: list[str], since: str, until: str,
             *, emit: Callable[[str], None] | None = None):
    """Partition ``[since, until]`` into ranges that one page-walk can enumerate."""
    if _count(fetcher, clauses, since, until) <= WINDOW_CAPACITY:
        yield since, until
        return
    for year_since, year_until in _year_spans(since, until):
        if _count(fetcher, clauses, year_since, year_until) <= WINDOW_CAPACITY:
            if emit:
                emit(f"   window {year_since[:4]}")
            yield year_since, year_until
            continue
        for month_since, month_until in _month_spans(year_since, year_until):
            month_total = _count(fetcher, clauses, month_since, month_until)
            if month_total > WINDOW_CAPACITY:
                raise ValueError(
                    f"{month_since}..{month_until} holds {month_total:,} filings, more than "
                    f"one window ({WINDOW_CAPACITY:,}) can enumerate; narrow the query "
                    "(for example by product code) rather than silently truncating it"
                )
            if emit:
                emit(f"   window {month_since[:7]}")
            yield month_since, month_until


def _collect_window(fetcher, clauses: list[str], since: str, until: str, *,
                    page_size: int, progress) -> list[dict[str, Any]]:
    from .http import OPENFDA_MAX_SKIP, with_openfda_key

    search = " AND ".join(clauses + [f"decision_date:[{since} TO {until}]"])
    rows: list[dict[str, Any]] = []
    skip = 0
    total = 0
    while True:
        if skip > OPENFDA_MAX_SKIP:
            # Cannot happen with a fitting window; raise rather than loop into a 400.
            raise ValueError(f"window {since}..{until} exceeded the skip ceiling")
        params: dict[str, Any] = {"search": search, "limit": min(page_size, PAGE_SIZE),
                                  "skip": skip, "sort": "decision_date:desc"}
        data = fetcher.get_json(ENDPOINT, params=with_openfda_key(params),
                                allow_not_found=True)
        if not data:
            break
        meta = (data.get("meta") or {}).get("results") or {}
        total = int(meta.get("total") or 0)
        page = [row for row in (data.get("results") or []) if isinstance(row, dict)]
        if not page:
            break
        for row in page:
            k_number = str(row.get("k_number") or "").strip().upper()
            if not k_number:
                continue
            rows.append({
                "k_number": k_number,
                "applicant": " ".join(str(row.get("applicant") or "").split()),
                "device_name": " ".join(str(row.get("device_name") or "").split()),
                "product_code": str(row.get("product_code") or "").strip(),
                "decision_date": str(row.get("decision_date") or "").strip(),
                "statement_or_summary": str(row.get("statement_or_summary") or "").strip(),
            })
        skip += len(page)
        if progress:
            progress(skip, total)
        if len(page) < min(page_size, PAGE_SIZE) or (total and skip >= total):
            break
    return rows


def collect_510k_index(fetcher, *, product_codes: Sequence[str] | None = None,
                       since: str | None = None, until: str | None = None,
                       only_published_summary: bool = True,
                       limit: int | None = None, page_size: int = PAGE_SIZE,
                       progress: Callable[[int, int], None] | None = None,
                       emit: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
    """Enumerate 510(k) filings from openFDA, partitioned so deep paging is never needed.

    Returns the identifiers plus the fields needed to align a document with the register:
    applicant, product code and decision date.

    ``only_published_summary`` is on by default because it is worth real time. Measured on the
    120 newest filings without it: 58 of 120 (48 %) returned 404 at the derived URL, i.e. FDA
    published no summary document for them. Filtering the index by the source's own
    ``statement_or_summary`` field stops the batch spending half its requests on filings that
    cannot produce a document.

    The real size of the corpus is therefore not 176,683. Measured 2026-11-21:

    =========== ======= ========= ======
    period      filings summaries  share
    =========== ======= ========= ======
    1976-1989    47,440      ~0      0 %
    1990-1999    44,082   17,778   40.3 %
    2000-2009    32,942   27,562   83.7 %
    2010-2019    30,476   28,381   93.1 %
    2020-2026    21,743   20,570   94.6 %
    =========== ======= ========= ======

    which totals **94,291 documents**, three quarters of them from 2000 onwards.
    """
    clauses: list[str] = []
    if only_published_summary:
        clauses.append('statement_or_summary:"Summary"')
    if product_codes:
        clauses.append("(" + " OR ".join(f'product_code:"{code}"' for code in product_codes) + ")")

    start = since or "1976-01-01"
    end = until or date.today().isoformat()
    rows: list[dict[str, Any]] = []
    for window_since, window_until in _windows(fetcher, clauses, start, end, emit=emit):
        rows.extend(_collect_window(fetcher, clauses, window_since, window_until,
                                    page_size=page_size, progress=progress))
        if limit is not None and len(rows) >= limit:
            return rows[:limit]
    return rows


# ---------------------------------------------------------------------- corpus
def build_corpus(fetcher, store: DocumentStore, index: Iterable[Mapping[str, Any]], *,
                 limit: int | None = None, refresh: bool = False,
                 progress: Callable[[CorpusStats, Mapping[str, Any]], None] | None = None,
                 emit: Callable[[str], None] | None = None) -> CorpusStats:
    """Fetch, extract and store the summary for each filing in ``index``.

    Never raises for one bad document: a sweep must survive the filings FDA never published.
    The per-filing outcome is stored, so the report below can distinguish the three failure
    modes instead of collapsing them into a count.
    """
    stats = CorpusStats()
    started = time.perf_counter()
    for position, entry in enumerate(index):
        if limit is not None and stats.attempted >= limit:
            stats.stop_reason = f"batch limit {limit} reached"
            break
        k_number = str(entry.get("k_number") or "").strip().upper()
        if not k_number:
            continue
        if not summary_pdf_available(k_number):
            # Guaranteed 404: the filing predates digitisation. Counting it as "not published"
            # would blur a known-before-requesting absence into a discovered one, so it gets its
            # own counter and costs no request.
            stats.skipped_pre_digitisation += 1
            continue
        try:
            document = fetch_510k_summary(fetcher, k_number, store=store, refresh=refresh)
        except Exception as error:  # noqa: BLE001 - a long sweep must survive one bad response
            # Measured need: an unsupervised run of this loop died silently at 600 documents
            # because a single transport error propagated out of the batch. One failed filing
            # must cost one filing, so the exception is recorded and the sweep continues. The
            # error text is kept (not just the count) because "how many" cannot be acted on.
            stats.attempted += 1
            stats.failed += 1
            stats.errored += 1
            stats.last_error = f"{k_number}: {type(error).__name__}: {error}"
            if emit:
                emit(f"error on {k_number}: {type(error).__name__}: {error}")
            continue
        stats.record(document)
        if progress:
            progress(stats, entry)
        if emit and stats.attempted % 50 == 0:
            emit(
                f"{stats.attempted} attempted · {stats.with_text} with text · "
                f"{stats.no_text_layer} no text layer · {stats.not_published} not published · "
                f"{stats.failed} failed"
            )
    stats.elapsed_seconds = time.perf_counter() - started
    return stats


def corpus_report(store: DocumentStore) -> dict[str, Any]:
    """Read the store back and report what the corpus actually contains."""
    coverage = store.coverage()
    by_section: dict[str, int] = {}
    chars = 0
    documents = 0
    for meta_path in sorted(store.root.glob("*.json")):
        try:
            import json

            payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        documents += 1
        chars += int(payload.get("text_chars") or 0)
        for key in (payload.get("sections") or {}):
            by_section[key] = by_section.get(key, 0) + 1
    return {
        "documents": documents,
        "with_text": coverage.get("with_text", 0),
        "chars_total": chars,
        "mean_chars": round(chars / documents, 1) if documents else 0.0,
        "by_section": dict(sorted(by_section.items(), key=lambda kv: -kv[1])),
        "coverage": coverage,
    }


__all__ = [
    "CorpusStats",
    "DEFAULT_REQUESTS_PER_SECOND",
    "ENDPOINT",
    "SUMMARY_PDF_FLOOR",
    "summary_pdf_available",
    "build_corpus",
    "collect_510k_index",
    "corpus_report",
]
