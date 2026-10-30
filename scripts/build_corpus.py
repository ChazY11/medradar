"""Build the EDGAR 8-K catalyst corpus (2019-01-01 .. 2026-10-31).

Pipeline (three resumable stages, all artefacts under ``data/edgar_corpus/``):

1. **search** - EDGAR full-text search for every quarter x phrase bucket::

       efts.sec.gov/LATEST/search-index?q=<phrase>&forms=8-K
           &dateRange=custom&startdt=<q_start>&enddt=<q_end>&hits=100

   Phrases are **unquoted** (the task's finding: quoting breaks the custom date
   filter). Hits are normalised, filtered to healthcare filers (name markers or
   SEC SIC), and written to ``candidates.jsonl`` (de-duplicated by accession,
   bucket evidence unioned).

2. **fetch** - one HTTP request per filing for the matched document (direct
   Archives URL; ``index.json`` fallback when the document is unreadable).
   HTML is cleaned to plain text and capped at 24 000 characters. Progress is
   appended to ``filings.jsonl``, so an interrupted crawl resumes where it
   stopped (the HTTP layer caches every response too).

3. **build** - join candidates + texts, classify, and write ``corpus.jsonl`` +
   ``manifest.json`` (:mod:`medradar.corpus` owns all of that logic).

Usage
-----
::

    python scripts/build_corpus.py all                # search + fetch + build
    python scripts/build_corpus.py search --refresh   # re-query EDGAR
    python scripts/build_corpus.py fetch --limit 500  # fetch at most 500 new texts
    python scripts/build_corpus.py build              # rebuild from local files
    python scripts/build_corpus.py status             # what do we have?

Politeness: SIC ``User-Agent`` with contact (``MEDRADAR_SEC_UA`` overrides), one
request at a time, default ``--min-interval 0.125`` (<= 8 requests/second), and a
hard ``--max-requests`` budget per run. Failures are recorded, never hidden.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # allow `python scripts/build_corpus.py`
    sys.path.insert(0, str(REPO_ROOT))

from medradar import corpus  # noqa: E402
from medradar.config import DATA_DIR, load_companies  # noqa: E402
from medradar.http import Fetcher  # noqa: E402
from medradar.live import EDGAR_FTS, EDGAR_TICKERS, SEC_UA  # noqa: E402
from medradar.util import ensure_dir, read_json, utc_now_iso, write_json  # noqa: E402

DEFAULT_OUT = DATA_DIR / "edgar_corpus"
DEFAULT_CACHE = DATA_DIR / "cache"
START = "2019-01-01"
END = "2026-10-31"
HITS_PER_QUERY = 100
MIN_TEXT_CHARS = 200
SHORT_TEXT_CHARS = 3_500
FETCH_RETRIES = 2
DEFAULT_LIMIT = 0

#: The seven phrase buckets, in the task's order (see corpus.BUCKET_ORDER).
BUCKETS: tuple[str, ...] = corpus.BUCKET_ORDER

ARCHIVES_BASE = corpus.ARCHIVES_BASE


# --------------------------------------------------------------------------- io
def _out_dir(args: argparse.Namespace) -> Path:
    return ensure_dir(Path(args.out))


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _make_fetcher(args: argparse.Namespace) -> Fetcher:
    return Fetcher(
        cache_dir=Path(args.cache),
        offline=bool(getattr(args, "offline", False)),
        min_interval=float(args.min_interval),
        timeout=float(args.timeout),
        max_requests=int(args.max_requests),
        ua=SEC_UA,
    )


# ------------------------------------------------------------------ windows
def quarter_windows(start: str, end: str) -> list[dict[str, str]]:
    """Inclusive quarterly windows clipped to ``[start, end]`` (ISO dates).

    ``2019-01-01 .. 2026-10-31`` yields 2019Q1 .. 2026Q3 fully plus a clipped
    2026Q4 (2026-10-01 .. 2026-10-31). A quarter is the unit because EDGAR FTS
    caps a custom range implicitly and a one-quarter window keeps every query
    under the ``hits=100`` sampling ceiling with reasonable recall.
    """
    start_day = date.fromisoformat(str(start))
    end_day = date.fromisoformat(str(end))
    if end_day < start_day:
        raise ValueError("end must not precede start")
    windows: list[dict[str, str]] = []
    cursor = date(start_day.year, ((start_day.month - 1) // 3) * 3 + 1, 1)
    while cursor <= end_day:
        quarter_end = date(cursor.year, cursor.month + 2, 1) + timedelta(days=31)
        quarter_end = date(quarter_end.year, quarter_end.month, 1) - timedelta(days=1)
        window_start = max(cursor, start_day)
        window_end = min(quarter_end, end_day)
        windows.append(
            {
                "label": f"{cursor.year}Q{(cursor.month - 1) // 3 + 1}",
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
            }
        )
        cursor = date(cursor.year + (cursor.month + 2) // 12, (cursor.month + 2) % 12 + 1, 1)
    return windows


# ---------------------------------------------------------------- reference
def load_ticker_map(fetcher: Fetcher, args: argparse.Namespace) -> dict[int, str]:
    """SEC ``company_tickers.json`` -> ``{cik: ticker}`` (cached by the fetcher)."""
    mapping: dict[int, str] = {}
    try:
        payload = fetcher.get_json(EDGAR_TICKERS, refresh=bool(args.refresh))
    except Exception as exc:  # missing tickers must not kill the crawl
        print(f"[corpus] ticker map unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return mapping
    if not isinstance(payload, Mapping):
        return mapping
    for entry in payload.values():
        if not isinstance(entry, Mapping):
            continue
        try:
            mapping[int(entry.get("cik_str"))] = str(entry.get("ticker") or "").upper()
        except (TypeError, ValueError):
            continue
    return mapping


class CompanyResolver:
    """Resolve a filing company name to a curated ``company_key`` + ticker.

    Reuses :class:`medradar.config.CompanyRegistry` for both device and drug
    universes (the repo's curated alias lists); a name that resolves to nothing
    stays unmatched on purpose - false positives poison downstream metrics.
    """

    def __init__(self) -> None:
        self.device = load_companies("device")
        self.drug = load_companies("drug")
        self._device_tickers = self.device.tickers()
        self._drug_tickers = self.drug.tickers()

    def resolve(self, name: str) -> tuple[str, str]:
        for registry, tickers in (
            (self.device, self._device_tickers),
            (self.drug, self._drug_tickers),
        ):
            key, confidence, _alias = registry.resolve(name)
            if key and confidence >= 0.82:
                return key, str(tickers.get(key) or "").upper()
        return "", ""


# ------------------------------------------------------------------- search
def _search_key(window: str, bucket: str) -> str:
    return f"{window}|{bucket}"


def cmd_search(args: argparse.Namespace) -> dict[str, Any]:
    """Stage 1: query EDGAR FTS and write candidates.jsonl."""
    out = _out_dir(args)
    fetcher = _make_fetcher(args)
    raw_path = out / "search_hits.jsonl"
    searches_path = out / "searches.jsonl"
    done: set[str] = set()
    if args.refresh and not getattr(args, "offline", False):
        # a refresh re-queries everything: stale hit/progress files would otherwise
        # be appended to and the query count in the manifest would double
        for stale in (raw_path, searches_path):
            if stale.exists():
                stale.unlink()
    if not args.refresh:
        for row in corpus.read_jsonl(searches_path):
            done.add(_search_key(str(row.get("window") or ""), str(row.get("bucket") or "")))
    windows = quarter_windows(args.start, args.end)
    print(
        f"[corpus] search: {len(windows)} quarter windows x {len(BUCKETS)} buckets"
        f" ({len(done)} already done)",
        file=sys.stderr,
    )
    started = time.perf_counter()
    for window in windows:
        for bucket in BUCKETS:
            key = _search_key(window["label"], bucket)
            if key in done:
                continue
            params = {
                "q": bucket,
                "forms": "8-K",
                "dateRange": "custom",
                "startdt": window["start"],
                "enddt": window["end"],
                "hits": HITS_PER_QUERY,
            }
            try:
                payload = fetcher.get_json(EDGAR_FTS, params, refresh=bool(args.refresh))
            except Exception as exc:
                row = {
                    **window,
                    "bucket": bucket,
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "total_hits": None,
                    "returned": 0,
                    "healthcare_hits": 0,
                    "fetched_at": utc_now_iso(),
                }
                _append_jsonl(searches_path, row)
                print(f"[corpus]   {key}: FAILED {type(exc).__name__}", file=sys.stderr)
                done.add(key)
                continue
            hits_block = (payload.get("hits") or {}) if isinstance(payload, Mapping) else {}
            total = (hits_block.get("total") or {}).get("value") if isinstance(hits_block, Mapping) else None
            hits = hits_block.get("hits") or [] if isinstance(hits_block, Mapping) else []
            healthcare = 0
            for hit in hits:
                candidate = corpus.parse_fts_hit(hit, bucket, window["label"])
                if candidate is None:
                    continue
                healthcare += 1
                _append_jsonl(raw_path, candidate)
            row = {
                **window,
                "bucket": bucket,
                "status": "ok",
                "total_hits": total,
                "returned": len(hits),
                "healthcare_hits": healthcare,
                "fetched_at": utc_now_iso(),
            }
            _append_jsonl(searches_path, row)
            done.add(key)
            print(
                f"[corpus]   {key}: total={total} returned={len(hits)} healthcare={healthcare}",
                file=sys.stderr,
            )

    candidates = corpus.merge_candidates(corpus.read_jsonl(raw_path))
    _write_candidates(out, candidates)
    searches = corpus.read_jsonl(searches_path)
    summary = _search_summary(searches, candidates, fetcher, time.perf_counter() - started)
    write_json(out / "search_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary


def _write_candidates(out: Path, candidates: Sequence[Mapping[str, Any]]) -> None:
    path = out / "candidates.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(json.dumps(candidate, ensure_ascii=False, default=str) + "\n")


def _search_summary(
    searches: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    fetcher: Fetcher,
    elapsed: float,
) -> dict[str, Any]:
    errors = [row for row in searches if row.get("status") == "error"]
    starts = [str(row["start"]) for row in searches if row.get("start")]
    ends = [str(row["end"]) for row in searches if row.get("end")]
    return {
        "stage": "search",
        "generated_at": utc_now_iso(),
        "window": {
            "start": min(starts) if starts else None,
            "end": max(ends) if ends else None,
        },
        "buckets": list(BUCKETS),
        "queries": len(searches),
        "queries_failed": len(errors),
        "total_hits_available": sum(int(row.get("total_hits") or 0) for row in searches),
        "hits_returned": sum(int(row.get("returned") or 0) for row in searches),
        "healthcare_hits": sum(int(row.get("healthcare_hits") or 0) for row in searches),
        "candidates_unique": len(candidates),
        "by_bucket_candidates": {
            bucket: sum(1 for item in candidates if bucket in (item.get("buckets") or []))
            for bucket in BUCKETS
        },
        "per_window": {
            label: sum(
                int(row.get("healthcare_hits") or 0)
                for row in searches
                if row.get("label") == label
            )
            for label in dict.fromkeys(str(row.get("label")) for row in searches)
        },
        "requests": fetcher.stats,
        "elapsed_s": round(elapsed, 1),
    }


# -------------------------------------------------------------------- fetch
def _primary_document_url(cik: Any, accession: str) -> str:
    accession_nodash = str(accession or "").replace("-", "")
    cik_text = "".join(ch for ch in str(cik or "") if ch.isdigit()).lstrip("0") or "0"
    return f"{ARCHIVES_BASE}/{cik_text}/{accession_nodash}/index.json"


def _pick_document(index_payload: Mapping[str, Any]) -> str | None:
    """Pick the announcement document from an EDGAR ``index.json`` listing.

    Preference order (catalyst corpus, not a legal archive):

    1. **EX-99.x press release** (by the filing's own ``type`` field first, then
       by filename) - the announcement prose lives here;
    2. **primary 8-K document** - contains Items 1.01/2.02/8.01 and the exhibit
       index, sometimes without the full press release;
    3. the largest HTML/TXT file - last resort for unusual filings.

    ``EX-10``/``EX-4`` agreements often mention "FDA approval" in a license or
    credit agreement; they match the FTS query but are not the announcement, so
    they rank last on purpose.
    """
    items = ((index_payload.get("directory") or {}).get("item") or [])
    docs = [
        item
        for item in items
        if isinstance(item, Mapping)
        and str(item.get("name", "")).lower().endswith((".htm", ".html", ".txt"))
        and "index" not in str(item.get("name", "")).lower()
    ]
    if not docs:
        return None

    def rank(item: Mapping[str, Any]) -> tuple[int, int]:
        declared = str(item.get("type") or "").upper()
        normalized = "".join(ch for ch in str(item.get("name", "")).lower() if ch.isalnum())
        if "EX-99" in declared or "ex99" in normalized or "exhibit99" in normalized:
            tier = 0
        elif declared.startswith("8-K") or "8k" in normalized:
            tier = 1
        else:
            tier = 2
        return tier, -int(item.get("size") or 0)

    docs.sort(key=rank)
    return str(docs[0].get("name"))


def _looks_like_announcement(document: str) -> bool:
    """True when the document name suggests press release / 8-K body (not an exhibit contract)."""
    normalized = "".join(ch for ch in str(document or "").lower() if ch.isalnum())
    return "ex99" in normalized or "exhibit99" in normalized or "8k" in normalized


def fetch_filing_text(
    fetcher: Fetcher, candidate: Mapping[str, Any]
) -> dict[str, Any]:
    """Fetch one filing document and return a ``filings.jsonl`` row.

    Strategy:

    1. If the FTS-matched document looks like the announcement (EX-99.x press
       release or the primary 8-K), fetch it directly - it is the document that
       actually contains the catalyst wording.
    2. If it looks like an agreement/other exhibit (``EX-10``, ``EX-4`` ...),
       fetch ``index.json`` first and use the preferred announcement document;
       the matched document is kept only as a last resort.
    3. If the direct document is unreadable or yields almost no text (scanned
       image, ``.jpg``, XBRL-only shell), fall back to ``index.json``.

    Never raises: every outcome becomes ``fetch_status`` ``ok`` / ``fallback`` /
    ``failed`` plus an error string, so a crawl can finish with a visible tail of
    failures instead of stopping.
    """
    accession = str(candidate.get("accession") or "")
    cik = candidate.get("cik")
    matched_url = str(candidate.get("url") or "")
    matched_document = str(candidate.get("document") or "")
    attempts = 0
    errors: list[str] = []

    def fetch_text(url: str) -> str:
        nonlocal attempts
        attempts += 1
        raw = fetcher.get_text(url, retries=FETCH_RETRIES)
        return corpus.clean_html(raw)

    def index_document_url() -> str | None:
        nonlocal attempts
        attempts += 1
        index_payload = fetcher.get_json(
            _primary_document_url(cik, accession), retries=FETCH_RETRIES
        )
        document = _pick_document(index_payload) if isinstance(index_payload, Mapping) else None
        if not document:
            return None
        return corpus.filing_url(cik, accession, document)

    plan: list[tuple[str, str]] = []
    if matched_url and _looks_like_announcement(matched_document):
        plan.append((matched_url, "ok"))
        plan.append(("__index__", "fallback"))
    else:
        plan.append(("__index__", "fallback"))
        if matched_url:
            plan.append((matched_url, "ok"))

    best: dict[str, Any] | None = None
    for url, status in plan:
        actual_url = url
        if url == "__index__":
            try:
                resolved = index_document_url()
            except Exception as exc:
                errors.append(f"index:{type(exc).__name__}")
                continue
            if not resolved:
                errors.append("no_candidate_document")
                continue
            actual_url = resolved
        try:
            text = fetch_text(actual_url)
        except Exception as exc:
            errors.append(f"text:{type(exc).__name__}")
            continue
        if len(text) < MIN_TEXT_CHARS:
            errors.append("short_text")
            continue
        result = {
            "accession": accession,
            "document": actual_url.rsplit("/", 1)[-1],
            "fetch_url": actual_url,
            "matched_document": matched_document,
            "fetch_status": status,
            "raw_chars": len(text),
            "text": text,
            "fetched_at": utc_now_iso(),
            "attempts": attempts,
            "error": "",
        }
        if best is None or len(text) > int(best.get("raw_chars") or 0):
            best = result
        if len(text) >= SHORT_TEXT_CHARS:
            return result
    if best is not None:
        return best
    return {
        "accession": accession,
        "document": matched_document,
        "fetch_url": matched_url,
        "matched_document": matched_document,
        "fetch_status": "failed",
        "raw_chars": 0,
        "text": "",
        "fetched_at": utc_now_iso(),
        "attempts": attempts,
        "error": "|".join(errors)[:300] or "unknown",
    }


def cmd_fetch(args: argparse.Namespace) -> dict[str, Any]:
    """Stage 2: fetch filing texts, resumably, with a politeness rate limit."""
    out = _out_dir(args)
    fetcher = _make_fetcher(args)
    candidates = corpus.read_jsonl(out / "candidates.jsonl")
    if not candidates:
        print("[corpus] fetch: no candidates.jsonl - run `search` first", file=sys.stderr)
        return {"stage": "fetch", "status": "no_candidates", "attempted": 0}
    filings_path = out / "filings.jsonl"
    existing = {str(row.get("accession")): row for row in corpus.read_jsonl(filings_path)}
    ok_accessions = {
        accession
        for accession, row in existing.items()
        if row.get("fetch_status") in ("ok", "fallback") and row.get("text")
    }
    retry_failed = bool(getattr(args, "retry_failed", False))
    retry_short = bool(getattr(args, "retry_short", False))
    short_accessions = {
        accession
        for accession, row in existing.items()
        if row.get("fetch_status") in ("ok", "fallback")
        and 0 < int(row.get("raw_chars") or 0) < SHORT_TEXT_CHARS
    }
    pending = [
        candidate
        for candidate in candidates
        if str(candidate.get("accession")) not in ok_accessions
        and (retry_failed or str(candidate.get("accession")) not in existing)
    ]
    if retry_short:
        # exclusive mode: only the suspiciously-short recordings are retried, so a
        # repair run cannot silently turn into a second full crawl
        pending = [
            candidate
            for candidate in candidates
            if str(candidate.get("accession")) in short_accessions
        ]
    limit = int(getattr(args, "limit", DEFAULT_LIMIT) or 0)
    if limit > 0:
        # year-stratified sample: fetching the first N candidates would bias the
        # corpus toward 2019-2021 (candidates are sorted by filing date)
        pending = list(corpus.stratified_subset(pending, limit))
    print(
        f"[corpus] fetch: candidates={len(candidates)} have={len(ok_accessions)} "
        f"pending={len(pending)} (limit={limit or 'none'})",
        file=sys.stderr,
    )
    started = time.perf_counter()
    attempted = 0
    counts = {"ok": 0, "fallback": 0, "failed": 0}
    for index, candidate in enumerate(pending, start=1):
        row = fetch_filing_text(fetcher, candidate)
        _append_jsonl(filings_path, row)
        attempted += 1
        counts[row["fetch_status"]] = counts.get(row["fetch_status"], 0) + 1
        if index % 50 == 0 or index == len(pending):
            elapsed = time.perf_counter() - started
            rate = attempted / elapsed if elapsed else 0.0
            print(
                f"[corpus]   fetched {index}/{len(pending)} "
                f"ok={counts['ok']} fallback={counts['fallback']} failed={counts['failed']} "
                f"({rate:.1f} req/s)",
                file=sys.stderr,
            )
    summary = _fetch_summary(out, counts, attempted, fetcher, time.perf_counter() - started)
    write_json(out / "fetch_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary


def _fetch_summary(
    out: Path,
    counts: Mapping[str, int],
    attempted: int,
    fetcher: Fetcher,
    elapsed: float,
) -> dict[str, Any]:
    rows = corpus.read_jsonl(out / "filings.jsonl")
    ok_rows = [row for row in rows if row.get("fetch_status") in ("ok", "fallback") and row.get("text")]
    failed_rows = [row for row in rows if row.get("fetch_status") == "failed"]
    candidates = corpus.read_jsonl(out / "candidates.jsonl")
    total = len(candidates)
    return {
        "stage": "fetch",
        "generated_at": utc_now_iso(),
        "attempted_this_run": attempted,
        "ok_this_run": int(counts.get("ok", 0)),
        "fallback_this_run": int(counts.get("fallback", 0)),
        "failed_this_run": int(counts.get("failed", 0)),
        "candidates": total,
        "texts_available": len(ok_rows),
        "failed_total": len(failed_rows),
        "failure_rate": round(len(failed_rows) / total, 4) if total else None,
        "text_chars_total": sum(int(row.get("raw_chars") or 0) for row in ok_rows),
        "failed_sample": [
            {"accession": row.get("accession"), "error": row.get("error")}
            for row in failed_rows[:20]
        ],
        "requests": fetcher.stats,
        "elapsed_s": round(elapsed, 1),
    }


# -------------------------------------------------------------------- build
def cmd_build(args: argparse.Namespace) -> dict[str, Any]:
    """Stage 3: join candidates + texts into corpus.jsonl + manifest.json."""
    out = _out_dir(args)
    candidates = corpus.read_jsonl(out / "candidates.jsonl")
    filings = {str(row.get("accession")): row for row in corpus.read_jsonl(out / "filings.jsonl")}
    if not candidates:
        print("[corpus] build: no candidates - run search first", file=sys.stderr)
        return {"stage": "build", "status": "no_candidates", "n": 0}
    resolver = CompanyResolver()
    tickers = load_ticker_map(_make_fetcher(args), args)
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    not_fetched = 0
    failed = 0
    for candidate in candidates:
        accession = str(candidate.get("accession") or "")
        filing = filings.get(accession)
        if not filing:
            not_fetched += 1
            continue
        if filing.get("fetch_status") == "failed" or not filing.get("text"):
            failed += 1
            failures.append(
                {
                    "accession": accession,
                    "company": candidate.get("company"),
                    "filed": candidate.get("filed"),
                    "error": filing.get("error") or "no_text",
                }
            )
            continue
        company_key, ticker = resolver.resolve(str(candidate.get("company") or ""))
        ticker = ticker or tickers.get(int(candidate.get("cik") or 0), "") or str(
            candidate.get("ticker") or ""
        )
        record = corpus.build_record(
            candidate,
            filing["text"],
            fetched_at=filing.get("fetched_at"),
            raw_chars=filing.get("raw_chars"),
            fetch_status=str(filing.get("fetch_status")),
            company_key=company_key,
            extra={
                "ticker": ticker,
                "fetch_url": filing.get("fetch_url", ""),
                "attempts": filing.get("attempts"),
            },
        )
        records.append(record)
    written = corpus.write_corpus(records, out)
    search_summary = read_json(out / "search_summary.json", {}) or {}
    fetch_summary = read_json(out / "fetch_summary.json", {}) or {}
    attempted = len(records) + failed
    manifest = corpus.build_manifest(
        records,
        search=search_summary,
        fetch={
            **fetch_summary,
            "candidates": len(candidates),
            "attempted": attempted,
            "texts_available": len(records),
            "failed": failed,
            "not_fetched": not_fetched,
            "failure_rate": round(failed / attempted, 4) if attempted else None,
            "coverage": round(len(records) / len(candidates), 4) if candidates else None,
        },
        window={"start": args.start, "end": args.end},
        buckets=BUCKETS,
        user_agent=SEC_UA,
        extra={
            "rate_limit": {
                "min_interval_s": float(args.min_interval),
                "max_requests_per_s": round(1.0 / float(args.min_interval), 2)
                if float(args.min_interval) > 0
                else None,
                "serial_requests": True,
            },
            "failures_path": str(out / "failures.json"),
            "corpus_path": written["path"],
            "records": len(records),
            "classified_company_keys": sum(1 for record in records if record.get("company_key")),
            "fetch_failure_rate_definition": (
                "failed / attempted fetches (candidates not fetched yet are counted "
                "separately as not_fetched, never as failures)"
            ),
        },
    )
    write_json(out / "manifest.json", manifest)
    write_json(out / "failures.json", {"n": len(failures), "failures": failures})
    summary = {
        "stage": "build",
        "status": "ok",
        "n": written["n"],
        "sha1": written["sha1"],
        "by_category": manifest["corpus"]["by_category"],
        "by_year": manifest["corpus"]["by_year"],
        "by_bucket": manifest["corpus"]["by_bucket"],
        "date_range": manifest["corpus"]["date_range"],
        "avg_text_chars": manifest["corpus"]["avg_text_chars"],
        "candidates": len(candidates),
        "failed": failed,
        "not_fetched": not_fetched,
        "failure_rate": manifest["fetch"]["failure_rate"],
        "coverage": manifest["fetch"]["coverage"],
        "paths": {
            "corpus": written["path"],
            "manifest": str(out / "manifest.json"),
            "failures": str(out / "failures.json"),
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary


# ------------------------------------------------------------------- status
def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    out = _out_dir(args)
    candidates = corpus.read_jsonl(out / "candidates.jsonl")
    filings = corpus.read_jsonl(out / "filings.jsonl")
    records = corpus.load_corpus(out / "corpus.jsonl")
    summary = corpus.summarize(records, read_json(out / "manifest.json", {}) or {})
    payload = {
        "out": str(out),
        "candidates": len(candidates),
        "filings_rows": len(filings),
        "texts_available": sum(
            1 for row in filings if row.get("fetch_status") in ("ok", "fallback") and row.get("text")
        ),
        "failed": sum(1 for row in filings if row.get("fetch_status") == "failed"),
        "corpus": {key: summary[key] for key in ("n", "by_category", "by_year", "date_range")},
        "manifest": str(out / "manifest.json") if (out / "manifest.json").exists() else None,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    return payload


# ---------------------------------------------------------------------- CLI
def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="artefact directory")
    parser.add_argument("--cache", default=str(DEFAULT_CACHE), help="HTTP cache directory")
    parser.add_argument("--start", default=START, help="corpus start date (inclusive)")
    parser.add_argument("--end", default=END, help="corpus end date (inclusive)")
    parser.add_argument("--min-interval", type=float, default=0.125,
                        help="seconds between requests (default 0.125 = 8 req/s)")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--max-requests", type=int, default=30_000)
    parser.add_argument("--refresh", action="store_true", help="ignore the HTTP cache")
    parser.add_argument("--offline", action="store_true", help="replay the cache only (no network)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_corpus.py",
        description="Build the EDGAR 8-K catalyst corpus (2019-2026).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="query EDGAR FTS -> candidates.jsonl")
    _add_common(search)
    search.add_argument("--hits", type=int, default=HITS_PER_QUERY)

    fetch = sub.add_parser("fetch", help="download filing texts -> filings.jsonl")
    _add_common(fetch)
    fetch.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                       help="fetch at most N new texts this run (0 = all)")
    fetch.add_argument("--retry-failed", action="store_true",
                       help="retry accessions recorded as failed")
    fetch.add_argument("--retry-short", action="store_true",
                       help="re-fetch accessions whose stored text is suspiciously short "
                            "(e.g. an 8-K cover page instead of the press release)")

    build = sub.add_parser("build", help="join + classify -> corpus.jsonl + manifest.json")
    _add_common(build)

    status = sub.add_parser("status", help="show crawl/corpus state")
    _add_common(status)

    all_ = sub.add_parser("all", help="search + fetch + build")
    _add_common(all_)
    all_.add_argument("--hits", type=int, default=HITS_PER_QUERY)
    all_.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    all_.add_argument("--retry-failed", action="store_true")
    all_.add_argument("--retry-short", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "search":
        cmd_search(args)
    elif args.command == "fetch":
        cmd_fetch(args)
    elif args.command == "build":
        cmd_build(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "all":
        cmd_search(args)
        cmd_fetch(args)
        cmd_build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
