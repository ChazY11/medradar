#!/usr/bin/env python3
"""PHOENIX-003 - Europe PMC harvest (frozen contract: FETCH_SPEC.md).

Writes, relative to experiments/phoenix003/:
    dataset/epmc_compact.jsonl.gz          (full run)
    fetch/EPMC_FETCH_MANIFEST.json         (full run)
and, for a smoke / --limit-pages run:
    dataset/_smoke_epmc_compact.jsonl.gz
    fetch/_smoke_EPMC_FETCH_MANIFEST.json

Python 3.12, standard library only.  Deterministic given the same upstream bytes:
records are written in harvest order (firm order from FETCH_SPEC.md, then cursorMark
page order), gzip members carry mtime=0, and JSON keys follow the frozen schema.

Nothing is written outside experiments/phoenix003/{dataset,fetch}/.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --- frozen constants (FETCH_SPEC.md "Endpoints and politeness") ------------------

ENDPOINT = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
USER_AGENT = ("MedRadar-PHOENIX003/1.0 (research; "
              "contact chazy11@users.noreply.github.com)")
WINDOW = "FIRST_PDATE:[2012-01-01 TO 2025-12-31]"
PAGE_SIZE = 1000
SOCKET_TIMEOUT = 180  # a full resultType=core page of 1000 can take 30-90 s (or more)
MIN_INTER_REQUEST_DELAY = 0.35
RETRY_DELAYS = (1, 2, 4)  # 1 s, 2 s, 4 s after the first attempt
MAX_PAGES_SAFETY = 500

# Firm keys, Europe PMC AFF: clause, and the lowercase affiliation terms that the
# frozen spec table assigns to each firm.  Terms are matched case-insensitively as
# substrings against affiliation strings only (never titles/abstracts).
FIRMS: list[tuple[str, str, tuple[str, ...]]] = [
    ("medtronic", 'AFF:"Medtronic"',
     ("medtronic",)),
    ("ge_healthcare",
     '(AFF:"GE HealthCare" OR AFF:"GE Healthcare" OR AFF:"GE Medical Systems" '
     'OR AFF:"General Electric Medical Systems")',
     ("ge healthcare", "ge medical systems", "general electric medical systems")),
    ("philips",
     '(AFF:"Philips" OR AFF:"Philips Healthcare" OR AFF:"Philips Medical Systems")',
     ("philips",)),
    ("draeger",
     '(AFF:"Draeger" OR AFF:"Dräger" OR AFF:"Draegerwerk")',
     ("draeger", "dräger", "draegerwerk")),
    ("mindray",
     '(AFF:"Mindray" OR AFF:"Shenzhen Mindray")',
     ("mindray",)),
]

COMPACT_KEYS = [
    "source_firm", "api_query", "id", "source", "pmid", "pmcid", "doi", "title",
    "author_string", "journal_title", "pub_year", "first_publication_date",
    "electronic_publication_date", "first_index_date", "pub_types",
    "is_open_access", "cited_by_count", "firm_affiliations", "abstract",
    "keywords", "mesh_terms", "fetched_at", "date_basis", "abstract_truncated",
]

# --- paths ------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent          # experiments/phoenix003/fetch
EXP_DIR = HERE.parent                            # experiments/phoenix003
REPO_ROOT = EXP_DIR.parent.parent                # worktree root
DATASET_DIR = EXP_DIR / "dataset"
FETCH_DIR = HERE


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


# --- small helpers ----------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    print(msg, flush=True)


def as_list(value) -> list:
    """Normalise Europe PMC's single-object-or-list JSON idiom to a list."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str) and value:
        return [value]
    return []


def opt_str(value) -> str | None:
    return value if isinstance(value, str) and value else None


# --- HTTP -------------------------------------------------------------------------

_last_request_end = 0.0


class HarvestError(RuntimeError):
    """Raised when a request keeps failing; the whole harvest aborts unwritten."""


def _polite_delay() -> None:
    global _last_request_end
    if _last_request_end:
        wait = MIN_INTER_REQUEST_DELAY - (time.monotonic() - _last_request_end)
        if wait > 0:
            time.sleep(wait)


def fetch_page(query: str, cursor_mark: str | None, stats: dict) -> tuple[int, dict, float]:
    """One search page. Retries 3x with 1/2/4 s backoff, then aborts the harvest."""
    global _last_request_end
    params = {
        "query": query,
        "format": "json",
        "resultType": "core",
        "pageSize": str(PAGE_SIZE),
    }
    if cursor_mark:
        params["cursorMark"] = cursor_mark
    url = ENDPOINT + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)

    last_err: object = None
    for attempt, delay in enumerate((0,) + RETRY_DELAYS):
        if attempt:
            time.sleep(delay)
        _polite_delay()
        stats["requests"] += 1
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=SOCKET_TIMEOUT) as resp:
                status = resp.status
                raw = resp.read()
            elapsed = time.monotonic() - t0
            data = json.loads(raw)
            return status, data, elapsed
        except Exception as exc:  # noqa: BLE001 - any transport/JSON failure is retried
            elapsed = time.monotonic() - t0
            last_err = exc
            code = getattr(exc, "code", None)
            log(f"  ! request failed after {elapsed:.1f}s "
                f"(attempt {attempt + 1}/{len(RETRY_DELAYS) + 1}): "
                f"{type(exc).__name__}: {exc}")
            # A definitive 4xx (other than 429) will not become valid on retry.
            if isinstance(exc, urllib.error.HTTPError) and 400 <= code < 500 and code != 429:
                break
        finally:
            _last_request_end = time.monotonic()

    raise HarvestError(f"Europe PMC request failed after retries: {last_err!r} :: {url}")


# --- record mapping ---------------------------------------------------------------

def build_record(raw: dict, terms: tuple[str, ...], fetched_at: str) -> dict:
    """Map one Europe PMC core record to the frozen compact schema (minus firm attribution)."""
    source = opt_str(raw.get("source"))
    rid = raw.get("id")
    rid = str(rid) if rid is not None and str(rid) != "" else None
    pmid = raw.get("pmid")
    pmid = str(pmid) if pmid is not None and str(pmid) != "" else None
    pmcid = opt_str(raw.get("pmcid"))
    doi = opt_str(raw.get("doi"))
    title = opt_str(raw.get("title"))
    author_string = opt_str(raw.get("authorString"))

    journal_info = raw.get("journalInfo")
    journal_title = None
    if isinstance(journal_info, dict):
        journal = journal_info.get("journal")
        if isinstance(journal, dict):
            journal_title = opt_str(journal.get("title"))

    pub_year_raw = raw.get("pubYear")
    pub_year = None
    if isinstance(pub_year_raw, int):
        pub_year = pub_year_raw
    elif isinstance(pub_year_raw, str) and pub_year_raw.strip().isdigit():
        pub_year = int(pub_year_raw.strip())

    fpd = opt_str(raw.get("firstPublicationDate"))
    epd = opt_str(raw.get("electronicPublicationDate"))
    fid = opt_str(raw.get("firstIndexDate"))

    # Frozen fallback order (FETCH_SPEC.md).  Upstream values are kept verbatim
    # (YYYY-MM-DD or YYYY-MM); only the pubYear fallback is synthesised.
    if fpd:
        first_date, date_basis = fpd, "firstPublicationDate"
    elif epd:
        first_date, date_basis = epd, "electronicPublicationDate"
    elif fid:
        first_date, date_basis = fid, "firstIndexDate"
    elif pub_year is not None:
        first_date, date_basis = f"{pub_year:04d}-01-01", "pubYear"
    else:
        first_date, date_basis = None, "none"

    pub_type_list = raw.get("pubTypeList")
    pub_types = []
    if isinstance(pub_type_list, dict):
        pub_types = [p for p in as_list(pub_type_list.get("pubType")) if isinstance(p, str)]

    oa_raw = raw.get("isOpenAccess")
    if oa_raw == "Y":
        is_open_access = True
    elif oa_raw == "N":
        is_open_access = False
    else:
        is_open_access = None

    cited_raw = raw.get("citedByCount")
    cited_by_count = cited_raw if isinstance(cited_raw, int) else None

    # --- firm affiliations ---------------------------------------------------------
    # (a) every author affiliation string, then (b) the record-level `affiliation`
    # field, both verbatim and in upstream order; keep only strings whose lowercase
    # form contains one of this firm's own terms; de-duplicate preserving order.
    affiliation_strings: list[str] = []
    author_list = raw.get("authorList")
    if isinstance(author_list, dict):
        for author in as_list(author_list.get("author")):
            if not isinstance(author, dict):
                continue
            details = author.get("authorAffiliationDetailsList")
            if not isinstance(details, dict):
                continue
            for affiliation in as_list(details.get("authorAffiliation")):
                if isinstance(affiliation, dict):
                    text = affiliation.get("affiliation")
                    if isinstance(text, str) and text:
                        affiliation_strings.append(text)
    record_affiliation = raw.get("affiliation")
    if isinstance(record_affiliation, str) and record_affiliation:
        affiliation_strings.append(record_affiliation)

    firm_affiliations: list[str] = []
    seen_affiliations: set[str] = set()
    for text in affiliation_strings:
        # Match on a whitespace-normalised copy only: upstream routinely uses
        # non-breaking spaces (U+00A0) inside corporate names ("GE\xa0Healthcare",
        # "Philips\xa0Healthcare"), which a literal "ge healthcare" would miss.
        # str.split() splits on every Unicode whitespace character; the retained
        # string is still the verbatim upstream text.
        match_text = " ".join(text.lower().split())
        if not any(term in match_text for term in terms):
            continue
        if text in seen_affiliations:
            continue
        seen_affiliations.add(text)
        firm_affiliations.append(text)

    # --- abstract -----------------------------------------------------------------
    abstract_raw = raw.get("abstractText")
    abstract = None
    abstract_truncated = False
    if isinstance(abstract_raw, str) and abstract_raw.strip():
        collapsed = re.sub(r"\s+", " ", abstract_raw).strip()
        if len(collapsed) > 2000:
            abstract = collapsed[:2000]
            abstract_truncated = True
        else:
            abstract = collapsed

    keyword_list = raw.get("keywordList")
    keywords = []
    if isinstance(keyword_list, dict):
        keywords = [k for k in as_list(keyword_list.get("keyword")) if isinstance(k, str)]

    mesh_heading_list = raw.get("meshHeadingList")
    mesh_terms = []
    if isinstance(mesh_heading_list, dict):
        for heading in as_list(mesh_heading_list.get("meshHeading")):
            if isinstance(heading, dict):
                name = heading.get("descriptorName")
                if isinstance(name, str) and name:
                    mesh_terms.append(name)

    # Stable de-duplication identity: (source, id).  A record without an id (not
    # observed in practice) is keyed by a content hash so it is still retained once.
    if rid is not None:
        key = (source or "", rid)
    else:
        blob = json.dumps(raw, sort_keys=True, ensure_ascii=False).encode("utf-8")
        key = (source or "", "@" + hashlib.sha256(blob).hexdigest()[:16])

    return {
        "_key": key,
        "id": rid,
        "source": source,
        "pmid": pmid,
        "pmcid": pmcid,
        "doi": doi,
        "title": title,
        "author_string": author_string,
        "journal_title": journal_title,
        "pub_year": pub_year,
        "first_publication_date": first_date,
        "electronic_publication_date": epd,
        "first_index_date": fid,
        "pub_types": pub_types,
        "is_open_access": is_open_access,
        "cited_by_count": cited_by_count,
        "firm_affiliations": firm_affiliations,
        "abstract": abstract,
        "keywords": keywords,
        "mesh_terms": mesh_terms,
        "fetched_at": fetched_at,
        "date_basis": date_basis,
        "abstract_truncated": abstract_truncated,
    }


def finalize(entry: dict) -> dict:
    """Emit the frozen key order; source_firm/api_query are derived from the merge."""
    firms_queries = entry["_firms"]  # list of (firm_key, api_query), harvest order
    query_by_firm = dict(firms_queries)
    firms_sorted = sorted(query_by_firm)
    record = {
        "source_firm": "+".join(firms_sorted),
        "api_query": " | ".join(query_by_firm[f] for f in firms_sorted),
    }
    for key in COMPACT_KEYS[2:]:
        record[key] = entry[key]
    return record


# --- harvest ----------------------------------------------------------------------

def harvest(limit_pages: int | None) -> tuple[list[dict], list[dict], list[str]]:
    """Run all five firm queries, merge/deduplicate, return (records, query_stats, limitations_fragments)."""
    merged: dict[tuple, dict] = {}
    order: list[tuple] = []
    queries: list[dict] = []

    for firm_key, aff_clause, terms in FIRMS:
        api_query = f"{aff_clause} AND ({WINDOW})"
        # Reject accidental divergence from the frozen spec table.
        assert aff_clause in FETCH_SPEC_CLAUSES, firm_key

        stats = {"requests": 0}
        started_at = now_iso()
        mark: str | None = None
        page = 0
        raw_returned = 0
        http_status = None
        reported_hit_count = None
        firm_raw_records: list[dict] = []

        while True:
            if limit_pages is not None and page >= limit_pages:
                break
            if page >= MAX_PAGES_SAFETY:
                raise HarvestError(f"page safety cap reached for {firm_key}")
            status, data, elapsed = fetch_page(api_query, mark, stats)
            if http_status is None:
                http_status = status
            if reported_hit_count is None:
                reported_hit_count = data.get("hitCount")
            result_list = data.get("resultList")
            page_records = []
            if isinstance(result_list, dict):
                page_records = as_list(result_list.get("result"))
            page_records = [r for r in page_records if isinstance(r, dict)]
            page += 1
            raw_returned += len(page_records)
            firm_raw_records.extend(page_records)
            log(f"[{firm_key}] page {page}: +{len(page_records)} records, "
                f"{raw_returned} this query so far (hitCount {reported_hit_count}) "
                f"{elapsed:.1f}s -> unique records so far: {len(merged)}")

            next_mark = data.get("nextCursorMark")
            if not page_records:
                break
            if not next_mark or next_mark == mark:
                break
            mark = next_mark

        finished_at = now_iso()
        fetched_at = finished_at
        log(f"[{firm_key}] done: {raw_returned} raw records in {page} page(s), "
            f"{stats['requests']} request(s), hitCount {reported_hit_count}")

        for raw in firm_raw_records:
            built = build_record(raw, terms, fetched_at)
            key = built.pop("_key")
            existing = merged.get(key)
            if existing is None:
                built["_firms"] = [(firm_key, api_query)]
                merged[key] = built
                order.append(key)
                continue
            # Same (source, id) from another firm query: merge attribution.
            known_firms = {f for f, _ in existing["_firms"]}
            if firm_key not in known_firms:
                existing["_firms"].append((firm_key, api_query))
            # Union the firm-affiliation strings, first occurrence wins -> "upstream order".
            have = set(existing["firm_affiliations"])
            for text in built["firm_affiliations"]:
                if text not in have:
                    have.add(text)
                    existing["firm_affiliations"].append(text)

        # Per-query statistics.  records_retained counts final records whose
        # source_firm contains this firm (it double-counts merged records; the
        # per-firm numbers therefore sum to more than records_retained).
        queries.append({
            "firm": firm_key,
            "api_query": api_query,
            "http_status": http_status,
            "requests": stats["requests"],
            "pages": page,
            "reported_hit_count": reported_hit_count,
            "records_returned": raw_returned,
            "records_retained": sum(
                1 for k in order
                if firm_key in {f for f, _ in merged[k]["_firms"]}),
            "started_at": started_at,
            "finished_at": finished_at,
        })

    records = [finalize(merged[k]) for k in order]

    # Fix up per-query retained counts after all merges are known.
    for q in queries:
        q["records_retained"] = sum(
            1 for k in order if q["firm"] in {f for f, _ in merged[k]["_firms"]})

    fragments: list[str] = []
    if limit_pages is not None:
        fragments.append(
            f"PARTIAL RUN: --limit-pages {limit_pages} ({limit_pages} page(s) per query). "
            "This artefact is a smoke/preview file and must not be used as the "
            "published dataset.")
    return records, queries, fragments


# Frozen AFF clauses copied verbatim from FETCH_SPEC.md, used only as an assertion.
FETCH_SPEC_CLAUSES = {
    'AFF:"Medtronic"',
    '(AFF:"GE HealthCare" OR AFF:"GE Healthcare" OR AFF:"GE Medical Systems" '
    'OR AFF:"General Electric Medical Systems")',
    '(AFF:"Philips" OR AFF:"Philips Healthcare" OR AFF:"Philips Medical Systems")',
    '(AFF:"Draeger" OR AFF:"Dräger" OR AFF:"Draegerwerk")',
    '(AFF:"Mindray" OR AFF:"Shenzhen Mindray")',
}


# --- writing & verification -------------------------------------------------------

def write_gz_atomic(path: Path, records: list[dict]) -> dict:
    """Write gzip atomically (mtime=0), verify it reads back, replace into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as handle:
        with gzip.GzipFile(fileobj=handle, mode="wb", compresslevel=9, mtime=0) as gz:
            for record in records:
                gz.write(json.dumps(record, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8"))
                gz.write(b"\n")

    lines, parse_errors, truncation_errors, key_errors = verify_gz(tmp)
    if parse_errors or truncation_errors or key_errors:
        tmp.unlink(missing_ok=True)
        raise HarvestError(
            f"verification failed for {path.name}: parse_errors={parse_errors} "
            f"truncation_errors={truncation_errors} key_errors={key_errors}")
    if lines != len(records):
        tmp.unlink(missing_ok=True)
        raise HarvestError(
            f"verification failed for {path.name}: {lines} lines != {len(records)} records")

    digest = hashlib.sha256()
    with open(tmp, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    size = tmp.stat().st_size
    os.replace(tmp, path)
    return {"path": rel(path), "bytes": size, "sha256": digest.hexdigest(), "lines": lines}


def verify_gz(path: Path) -> tuple[int, int, int, int]:
    """Re-read a gzip JSONL file: (lines, parse_errors, truncation_errors, key_errors)."""
    lines = parse_errors = truncation_errors = key_errors = 0
    expected_keys = list(COMPACT_KEYS)
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            lines += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            if list(obj.keys()) != expected_keys:
                key_errors += 1
            abstract = obj.get("abstract")
            if obj.get("abstract_truncated") and (
                    not isinstance(abstract, str) or len(abstract) != 2000):
                truncation_errors += 1
    return lines, parse_errors, truncation_errors, key_errors


def write_manifest_atomic(path: Path, manifest: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    size = tmp.stat().st_size
    os.replace(tmp, path)
    return {"path": rel(path), "bytes": size, "sha256": digest, "lines": None}


def summarise(records: list[dict], queries: list[dict], partial_fragments: list[str]) -> dict:
    """Compute the frozen counts block plus the sanity checks requested for the run log."""
    null_fields = [
        "pmid", "pmcid", "doi", "title", "author_string", "journal_title",
        "pub_year", "first_publication_date", "electronic_publication_date",
        "first_index_date", "abstract", "is_open_access", "cited_by_count",
    ]
    per_field_nulls = {
        field: sum(1 for r in records if r.get(field) is None) for field in null_fields
    }

    date_basis_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    per_firm: dict[str, int] = {}
    for record in records:
        date_basis_counts[record["date_basis"]] = date_basis_counts.get(record["date_basis"], 0) + 1
        source = record["source"] or "UNKNOWN"
        source_counts[source] = source_counts.get(source, 0) + 1
        for firm in record["source_firm"].split("+"):
            per_firm[firm] = per_firm.get(firm, 0) + 1

    multi_firm = sum(1 for r in records if "+" in r["source_firm"])
    empty_affiliations = sum(1 for r in records if not r["firm_affiliations"])
    # The frozen window is server-side only (FIRST_PDATE).  Europe PMC's FIRST_PDATE
    # index is not exactly the shipped firstPublicationDate for every source type, so
    # a few returned records carry a firstPublicationDate outside the window; they are
    # retained (no client-side filter is specified for Europe PMC) and counted here.
    out_of_window = [
        r["first_publication_date"] for r in records
        if r["first_publication_date"] is not None
        and not ("2012-01-01" <= r["first_publication_date"] <= "2025-12-31")
    ]
    with_abstract = [r["abstract"] for r in records if r["abstract"] is not None]
    truncated = sum(1 for r in records if r["abstract_truncated"])
    mean_abstract_length = (
        round(sum(len(a) for a in with_abstract) / len(with_abstract), 2)
        if with_abstract else None)

    counts = {
        "records_total": sum(q["records_returned"] for q in queries),
        "records_retained": len(records),
        "per_field_nulls": per_field_nulls,
        # --- sanity block (additive; the frozen keys above are unchanged) ---
        "records_returned_by_multiple_firm_queries": multi_firm,
        "records_with_empty_firm_affiliations": empty_affiliations,
        "records_first_publication_date_outside_window": len(out_of_window),
        "first_publication_date_outside_window_examples": sorted(out_of_window)[:10],
        "per_firm_retained": {firm: per_firm.get(firm, 0) for firm, _, _ in FIRMS},
        "date_basis_counts": date_basis_counts,
        "source_counts": source_counts,
        "abstract": {
            "records_with_abstract": len(with_abstract),
            "records_without_abstract": len(records) - len(with_abstract),
            "mean_length_chars": mean_abstract_length,
            "truncated_to_2000": truncated,
        },
        "is_open_access_counts": {
            "true": sum(1 for r in records if r["is_open_access"] is True),
            "false": sum(1 for r in records if r["is_open_access"] is False),
            "null": sum(1 for r in records if r["is_open_access"] is None),
        },
        "records_with_empty_keywords": sum(1 for r in records if not r["keywords"]),
        "records_with_empty_mesh_terms": sum(1 for r in records if not r["mesh_terms"]),
        "records_with_empty_pub_types": sum(1 for r in records if not r["pub_types"]),
    }
    return counts


def limitations_for(records: list[dict], queries: list[dict], counts: dict,
                    partial_fragments: list[str]) -> list[str]:
    lines: list[str] = list(partial_fragments)
    lines.append(
        "Query is the frozen FETCH_SPEC.md query executed verbatim "
        "(AFF clause AND FIRST_PDATE window). HAS_ABS:Y and SRC:MED were "
        "deliberately NOT added: HAS_ABS:Y returns 0 hits for this corpus and "
        "SRC:MED would drop preprint (PPR), patent (PAT) and PMC-only records.")
    lines.append(
        "Pagination: resultType=core&pageSize=1000, cursorMark; each query stops when "
        "nextCursorMark is absent or repeats. reported_hit_count is the hitCount of the "
        "first page of that query.")
    lines.append(
        "firm_affiliations is a case-insensitive substring test of the frozen firm AFF "
        "terms against (a) authorList[].authorAffiliationDetailsList[].authorAffiliation[].affiliation "
        "and (b) the record-level affiliation field only. Strings are kept verbatim, "
        "de-duplicated, in upstream order. Titles/abstracts are never scanned. Matching "
        "normalises whitespace only (upstream uses U+00A0 inside names such as "
        "\"GE\\xa0Healthcare\"); retained strings are not altered.")
    lines.append(
        f"Records returned by more than one firm query: "
        f"{counts['records_returned_by_multiple_firm_queries']} "
        f"(source_firm is the sorted '+'-joined list). The per-firm retained counts "
        f"therefore sum to "
        f"{sum(counts['per_firm_retained'].values())} > records_retained "
        f"{counts['records_retained']}.")
    lines.append(
        f"Records with empty firm_affiliations: "
        f"{counts['records_with_empty_firm_affiliations']} of "
        f"{counts['records_retained']} - retrieved by the AFF query but no shipped "
        f"affiliation string matches the firm's own terms; kept in the corpus per spec "
        f"and counted here rather than silently dropped.")
    nulls = counts["per_field_nulls"]
    lines.append(
        f"first_publication_date null: {nulls['first_publication_date']}; "
        f"date_basis breakdown: {json.dumps(counts['date_basis_counts'], sort_keys=True)} "
        f"(frozen fallback order firstPublicationDate -> electronicPublicationDate -> "
        f"firstIndexDate -> pubYear + '-01-01'). Upstream date strings are kept verbatim "
        f"(YYYY-MM-DD or YYYY-MM).")
    lines.append(
        f"abstract present: {counts['abstract']['records_with_abstract']} of "
        f"{counts['records_retained']} (mean collapsed length "
        f"{counts['abstract']['mean_length_chars']} chars); truncated to 2000 chars: "
        f"{counts['abstract']['truncated_to_2000']}.")
    lines.append(
        f"source distribution: {json.dumps(counts['source_counts'], sort_keys=True)} "
        f"- no SRC:MED filter was applied, so preprints/patents/PMC-only records are "
        f"retained.")
    lines.append(
        f"first_publication_date outside the frozen window despite the server-side "
        f"FIRST_PDATE filter: "
        f"{counts['records_first_publication_date_outside_window']} record(s), examples "
        f"{counts['first_publication_date_outside_window_examples']}. The frozen window "
        f"is server-side only and no client-side date filter is specified for Europe PMC, "
        f"so these records are retained and counted. Cause observed: Europe PMC's "
        f"FIRST_PDATE index is not exactly the shipped firstPublicationDate for every "
        f"source type (the smoke sample showed a patent record, id WO2006028934, with "
        f"firstPublicationDate 2005-08-30).")
    lines.append(
        "gz verification on write: line count equals records_retained; every line "
        "parses as JSON; every record carries exactly the frozen key set; "
        "0 records have abstract_truncated=true with an abstract length != 2000.")
    lines.append(
        "Observed hit counts (this run): "
        + "; ".join(
            f"{q['firm']} reported_hit_count={q['reported_hit_count']} "
            f"(returned {q['records_returned']}, retained {q['records_retained']})"
            for q in queries)
        + ". After the frozen window is applied, draeger and mindray are far below the "
          "informal pre-run estimates (~600 and ~400): AFF:\"Draeger\" without the window "
          "returns 975 records whose top-100 sample is 86% PAT records matching personal "
          "surnames (e.g. 'Schumm-Draeger'), inside the frozen window it returns 19, and "
          "the frozen three-spelling union returns the value above. The frozen query was "
          "not altered to chase the estimate.")
    lines.append(
        "AFF:\"Philips\" also retrieves non-medical Philips (lighting, semiconductors in "
        "early years); that contamination is measured later in DATA_INTEGRITY_AUDIT.md, "
        "not repaired here.")
    return lines


# --- main -------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Harvest the frozen PHOENIX-003 Europe PMC corpus.")
    parser.add_argument("--smoke", action="store_true",
                        help="one page (pageSize=1000) per query; writes _smoke_* artefacts")
    parser.add_argument("--limit-pages", type=int, default=None,
                        help="stop after N pages per query (implies _smoke_* artefact names)")
    args = parser.parse_args(argv)

    partial = args.smoke or args.limit_pages is not None
    limit_pages = args.limit_pages if args.limit_pages is not None else (1 if args.smoke else None)
    if limit_pages is not None and limit_pages < 1:
        parser.error("--limit-pages must be >= 1")

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except (AttributeError, ValueError):
        pass

    if partial:
        dataset_path = DATASET_DIR / "_smoke_epmc_compact.jsonl.gz"
        manifest_path = FETCH_DIR / "_smoke_EPMC_FETCH_MANIFEST.json"
    else:
        dataset_path = DATASET_DIR / "epmc_compact.jsonl.gz"
        manifest_path = FETCH_DIR / "EPMC_FETCH_MANIFEST.json"

    mode = "SMOKE/PARTIAL" if partial else "FULL"
    log(f"PHOENIX-003 Europe PMC harvest ({mode})")
    log(f"  endpoint : {ENDPOINT}")
    log(f"  window   : {WINDOW}")
    log(f"  pageSize : {PAGE_SIZE}  socket timeout: {SOCKET_TIMEOUT}s  "
        f"min delay: {MIN_INTER_REQUEST_DELAY}s  retries: {list(RETRY_DELAYS)}")
    log(f"  outputs  : {rel(dataset_path)} / {rel(manifest_path)}")
    log("")

    generated_at = now_iso()
    records, queries, partial_fragments = harvest(limit_pages)

    counts = summarise(records, queries, partial_fragments)
    log("")
    log(f"retained {counts['records_retained']} unique records from "
        f"{counts['records_total']} returned (multi-firm: "
        f"{counts['records_returned_by_multiple_firm_queries']})")
    log(f"per-firm retained: {counts['per_firm_retained']}")
    log(f"date_basis: {counts['date_basis_counts']}")
    log(f"source: {counts['source_counts']}")
    log(f"empty firm_affiliations: {counts['records_with_empty_firm_affiliations']}")

    log("")
    log(f"writing {rel(dataset_path)} ...")
    file_info = write_gz_atomic(dataset_path, records)
    log(f"  wrote {file_info['lines']} lines, {file_info['bytes']} bytes, "
        f"sha256 {file_info['sha256']}")

    manifest = {
        "generated_at": generated_at,
        "endpoint": ENDPOINT,
        "queries": queries,
        "counts": counts,
        "files": [file_info],
        "limitations": limitations_for(records, queries, counts, partial_fragments),
    }
    log(f"writing {rel(manifest_path)} ...")
    manifest_info = write_manifest_atomic(manifest_path, manifest)
    log(f"  wrote {manifest_info['bytes']} bytes, sha256 {manifest_info['sha256']}")
    log("")
    log(f"DONE ({mode}): {rel(dataset_path)} sha256={file_info['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
