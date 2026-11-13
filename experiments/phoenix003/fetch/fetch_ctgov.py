#!/usr/bin/env python3
"""PHOENIX-003 ClinicalTrials.gov harvester (frozen contract: FETCH_SPEC.md).

Firm-anchored harvest of the whole ClinicalTrials.gov corpus available per query,
written to `experiments/phoenix003/dataset/ctgov_compact.jsonl.gz` with the frozen
compact schema, plus `experiments/phoenix003/fetch/CTgov_FETCH_MANIFEST.json`.

Python 3.12, standard library only.

Usage:
    python fetch_ctgov.py --smoke                  # 1 page per query -> _smoke_* artefacts
    python fetch_ctgov.py                          # full harvest -> real artefacts
    python fetch_ctgov.py --smoke --limit-pages 2  # 2 pages per query -> _smoke_* artefacts

Only `--smoke` writes to the `_smoke_*` paths; a partial non-smoke run is refused
unless `--allow-partial` is passed explicitly (the real artefacts must never be a
silently truncated harvest).

The harvest is deterministic given the same upstream bytes: fixed query order, fixed
output order (first-seen nct_id), gzip with mtime=0. `fetched_at` is the only
wall-clock field.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# -- frozen constants from FETCH_SPEC.md -------------------------------------

API_ENDPOINT = "https://clinicaltrials.gov/api/v2/studies"
USER_AGENT = (
    "MedRadar-PHOENIX003/1.0 (research; contact chazy11@users.noreply.github.com)"
)
FIELDS = [
    "NCTId",
    "BriefTitle",
    "OfficialTitle",
    "Acronym",
    "OverallStatus",
    "StudyType",
    "Phase",
    "Condition",
    "InterventionName",
    "InterventionType",
    "InterventionDescription",
    "LeadSponsorName",
    "CollaboratorName",
    "EnrollmentCount",
    "StartDate",
    "PrimaryCompletionDate",
    "CompletionDate",
    "StudyFirstPostDate",
    "LastUpdatePostDate",
    "StudyFirstSubmitDate",
    "ResultsFirstPostDate",
    "HasResults",
    "LocationCountry",
    "OrgStudyId",
    "SecondaryId",
]
FIELDS_PARAM = ",".join(FIELDS)

# Firm order and query.spons strings exactly as in the spec table (8 queries, 5 firms).
FIRMS: list[tuple[str, list[str]]] = [
    ("medtronic", ["Medtronic"]),
    (
        "ge_healthcare",
        ["GE HealthCare", "GE Medical Systems", "General Electric Medical Systems"],
    ),
    ("philips", ["Philips"]),
    ("draeger", ["Draeger", "Dr\u00e4ger"]),
    ("mindray", ["Mindray"]),
]

PAGE_SIZE = 1000
MIN_DELAY_S = 0.35
MAX_RETRIES = 3
BACKOFF_S = (1.0, 2.0, 4.0)
DATE_MIN = (2010, 1, 1)
DATE_MAX = (2025, 12, 31)
MAX_PAGES_PER_QUERY = 1000  # sanity guard against a token loop

SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parents[3]  # <worktree>/experiments/phoenix003/fetch/fetch_ctgov.py
DATASET_DIR = ROOT / "experiments" / "phoenix003" / "dataset"
FETCH_DIR = ROOT / "experiments" / "phoenix003" / "fetch"

FULL_DATASET = DATASET_DIR / "ctgov_compact.jsonl.gz"
FULL_MANIFEST = FETCH_DIR / "CTgov_FETCH_MANIFEST.json"
SMOKE_DATASET = DATASET_DIR / "_smoke_ctgov_compact.jsonl.gz"
SMOKE_MANIFEST = FETCH_DIR / "_smoke_CTgov_FETCH_MANIFEST.json"


class FetchError(RuntimeError):
    """Raised when the harvest must abort loudly (no partial file written)."""


# -- small helpers -----------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dig(obj, *keys, default=None):
    cur = obj
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def clean(value):
    """Normalise upstream empty/blank strings to None; everything else verbatim."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


def date_struct(module, key: str):
    """`XxxDateStruct.date` verbatim (YYYY-MM-DD or YYYY-MM) or None."""
    return clean(dig(module, key, "date"))


def parse_date_key(value: str):
    """Return comparable (y, m, d) key, or None when unparseable.

    Upstream dates are YYYY-MM-DD or YYYY-MM. For YYYY-MM we compare with day=1
    **only for the window test**; the stored string is always kept verbatim.
    """
    try:
        if len(value) == 10:
            y, m, d = int(value[0:4]), int(value[5:7]), int(value[8:10])
            if value[4] != "-" or value[7] != "-":
                return None
            return (y, m, d)
        if len(value) == 7:
            if value[4] != "-":
                return None
            return (int(value[0:4]), int(value[5:7]), 1)
    except (TypeError, ValueError):
        return None
    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_atomic(path: Path, payload: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


# -- HTTP layer --------------------------------------------------------------

_last_attempt_monotonic = 0.0


def _throttle() -> None:
    """Enforce >= MIN_DELAY_S between successive HTTP attempt starts."""
    global _last_attempt_monotonic
    wait = MIN_DELAY_S - (time.monotonic() - _last_attempt_monotonic)
    if wait > 0:
        time.sleep(wait)
    _last_attempt_monotonic = time.monotonic()


def fetch_page(
    params: dict[str, str], context: str, timeout: float
) -> tuple[int, dict, int, int]:
    """GET one page. Returns (http_status, json_body, body_bytes, attempts).

    Retries transient failures (network errors, timeouts, 408/425/429/5xx, bad
    JSON) up to MAX_RETRIES times with 1 s / 2 s / 4 s backoff. A non-retryable
    HTTP status aborts the whole harvest.
    """
    url = API_ENDPOINT + "?" + urllib.parse.urlencode(params)
    last_error = "unknown"
    for attempt in range(1, MAX_RETRIES + 2):  # initial attempt + 3 retries
        if attempt > 1:
            delay = BACKOFF_S[attempt - 2]
            print(
                f"  ! retry {attempt - 1}/{MAX_RETRIES} {context} "
                f"after: {last_error} (sleep {delay:.0f}s)",
                flush=True,
            )
            time.sleep(delay)
        _throttle()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                raw = resp.read()
        except urllib.error.HTTPError as exc:  # 4xx/5xx
            body = b""
            try:
                body = exc.read()[:400]
            except Exception:  # pragma: no cover - defensive
                pass
            last_error = f"HTTP {exc.code} {body.decode('utf-8', 'replace')!r}"
            retryable = exc.code in (408, 425, 429) or 500 <= exc.code <= 599
            if not retryable:
                raise FetchError(f"{context}: non-retryable {last_error}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        else:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                last_error = f"invalid JSON ({exc}); {len(raw)} bytes"
            else:
                if not isinstance(data, dict) or "studies" not in data:
                    last_error = f"unexpected payload keys {sorted(data)[:8]!r}"
                else:
                    return status, data, len(raw), attempt
    raise FetchError(
        f"{context}: gave up after {MAX_RETRIES + 1} attempts; last error: {last_error}"
    )


# -- record transformation ---------------------------------------------------


def build_record(study: dict, firm: str, query: str, fetched_at: str) -> dict:
    ps = study.get("protocolSection") or {}
    idm = ps.get("identificationModule") or {}
    stm = ps.get("statusModule") or {}
    scm = ps.get("sponsorCollaboratorsModule") or {}
    cm = ps.get("conditionsModule") or {}
    dm = ps.get("designModule") or {}
    aim = ps.get("armsInterventionsModule") or {}
    clm = ps.get("contactsLocationsModule") or {}

    interventions = []
    for item in aim.get("interventions") or []:
        if not isinstance(item, dict):
            continue
        interventions.append(
            {
                "type": item.get("type"),
                "name": item.get("name"),
                "description": item.get("description"),
            }
        )

    collaborators = []
    for item in scm.get("collaborators") or []:
        if isinstance(item, dict) and item.get("name") is not None:
            collaborators.append(item["name"])

    countries = sorted(
        {
            loc["country"]
            for loc in (clm.get("locations") or [])
            if isinstance(loc, dict) and clean(loc.get("country"))
        }
    )

    secondary_ids = []
    for item in idm.get("secondaryIdInfos") or []:
        if isinstance(item, dict) and item.get("id") is not None:
            secondary_ids.append(item["id"])

    has_results = study.get("hasResults")
    if not isinstance(has_results, bool):
        has_results = None

    return {
        "nct_id": clean(idm.get("nctId")),
        "source_firm": firm,
        "api_query": [query],
        "brief_title": clean(idm.get("briefTitle")),
        "official_title": clean(idm.get("officialTitle")),
        "acronym": clean(idm.get("acronym")),
        "overall_status": clean(stm.get("overallStatus")),
        "study_type": clean(dm.get("studyType")),
        "phases": dm.get("phases") or [],
        "conditions": cm.get("conditions") or [],
        "interventions": interventions,
        "lead_sponsor": clean(dig(scm, "leadSponsor", "name")),
        "collaborators": collaborators,
        "enrollment": dig(dm, "enrollmentInfo", "count"),
        "start_date": date_struct(stm, "startDateStruct"),
        "primary_completion_date": date_struct(stm, "primaryCompletionDateStruct"),
        "completion_date": date_struct(stm, "completionDateStruct"),
        "first_posted": date_struct(stm, "studyFirstPostDateStruct"),
        "last_update_posted": date_struct(stm, "lastUpdatePostDateStruct"),
        "study_first_submitted": clean(stm.get("studyFirstSubmitDate")),
        "results_first_posted": date_struct(stm, "resultsFirstPostDateStruct"),
        "has_results": has_results,
        "countries": countries,
        "org_study_id": clean(dig(idm, "orgStudyIdInfo", "id")),
        "secondary_ids": secondary_ids,
        "fetched_at": fetched_at,
    }


# -- harvest -----------------------------------------------------------------


def harvest(limit_pages: int | None, timeout: float) -> tuple[list[dict], list[dict], list[str]]:
    """Run all queries. Returns (unique_raw_records, query_manifest_entries, notes)."""
    unique: dict[str, dict] = {}
    query_entries: list[dict] = []
    notes: list[str] = []
    n_queries = sum(len(qs) for _, qs in FIRMS)
    q_index = 0

    for firm, queries in FIRMS:
        for query in queries:
            q_index += 1
            started_at = utc_now_iso()
            params_base = {
                "query.spons": query,
                "fields": FIELDS_PARAM,
                "pageSize": str(PAGE_SIZE),
                "countTotal": "true",
            }
            token: str | None = None
            page = 0
            records_returned = 0
            requests = 0
            pages = 0
            reported_total: int | None = None
            query_nct_ids: list[str] = []
            status: int = 0
            t0 = time.monotonic()

            while True:
                page += 1
                params = dict(params_base)
                if token:
                    params.pop("countTotal", None)  # spec: countTotal on the first request
                    params["pageToken"] = token
                context = f"[{q_index:02d}/{n_queries:02d}] firm={firm} q={query!r} page={page}"
                try:
                    status, data, body_bytes, attempts = fetch_page(
                        params, context, timeout
                    )
                except FetchError as exc:
                    raise FetchError(
                        f"{context}: {exc}. Aborting harvest; no output file was written."
                    ) from exc
                requests += attempts
                pages += 1
                studies = data.get("studies") or []
                if reported_total is None and isinstance(data.get("totalCount"), int):
                    reported_total = data["totalCount"]
                fetched_at = utc_now_iso()
                for study in studies:
                    if not isinstance(study, dict):
                        continue
                    rec = build_record(study, firm, query, fetched_at)
                    nct = rec["nct_id"]
                    if not nct:
                        notes.append(
                            f"record without nctId skipped from query {query!r} "
                            f"({firm}); {len(studies)} studies on page {page}"
                        )
                        continue
                    query_nct_ids.append(nct)
                    if nct in unique:
                        if query not in unique[nct]["api_query"]:
                            unique[nct]["api_query"].append(query)
                    else:
                        unique[nct] = rec
                records_returned += len(studies)
                print(
                    f"[{q_index:02d}/{n_queries:02d}] {firm:<12} q={query!r} page={page} "
                    f"http={status} got={len(studies)} total={reported_total} "
                    f"cum_fetched={records_returned} cum_unique={len(unique)} "
                    f"bytes={body_bytes} t={time.monotonic() - t0:.1f}s",
                    flush=True,
                )

                token = data.get("nextPageToken")
                if not token or not studies:
                    break
                if limit_pages is not None and page >= limit_pages:
                    notes.append(
                        f"page limit {limit_pages} reached for query {query!r} ({firm}); "
                        f"{reported_total if reported_total is not None else '?'} reported, "
                        f"{records_returned} fetched"
                    )
                    break
                if reported_total is not None and records_returned >= reported_total:
                    break
                if page >= MAX_PAGES_PER_QUERY:
                    raise FetchError(
                        f"{context}: exceeded hard page guard {MAX_PAGES_PER_QUERY}; "
                        "refusing to write a possibly truncated harvest"
                    )

            if reported_total is not None and records_returned < reported_total:
                notes.append(
                    f"query {query!r} ({firm}): API reported totalCount="
                    f"{reported_total} but only {records_returned} studies were returned"
                )

            entry = {
                "firm": firm,
                "api_query": query,
                "http_status": status,
                "requests": requests,
                "pages": pages,
                "reported_hit_count": reported_total,
                "records_returned": records_returned,
                "records_retained": 0,  # filled in after dedupe/filter
                "started_at": started_at,
                "finished_at": utc_now_iso(),
            }
            entry["_nct_ids"] = query_nct_ids  # stripped before writing the manifest
            query_entries.append(entry)

    return list(unique.values()), query_entries, notes


# -- dataset writing / verification ------------------------------------------


def gzip_bytes(payload: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(payload)
    return buf.getvalue()


def serialise_records(records: list[dict]) -> bytes:
    out = io.StringIO()
    for rec in records:
        rec = dict(rec)
        rec["api_query"] = " | ".join(rec["api_query"])
        out.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
        out.write("\n")
    return out.getvalue().encode("utf-8")


def verify_dataset(path: Path, expected_lines: int) -> tuple[int, list[str]]:
    """Read the gz back; returns (line_count, problems)."""
    problems: list[str] = []
    lines = 0
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                lines += 1
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    problems.append(f"line {lineno}: invalid JSON: {exc}")
                    continue
                if not isinstance(obj, dict):
                    problems.append(f"line {lineno}: not a JSON object")
    except (OSError, EOFError) as exc:
        problems.append(f"gzip read failed: {exc}")
    if lines != expected_lines:
        problems.append(
            f"line count {lines} != retained record count {expected_lines}"
        )
    return lines, problems


def field_null_counts(records: list[dict]) -> dict[str, int]:
    scalar_fields = [
        "brief_title",
        "official_title",
        "acronym",
        "overall_status",
        "study_type",
        "lead_sponsor",
        "enrollment",
        "start_date",
        "primary_completion_date",
        "completion_date",
        "first_posted",
        "last_update_posted",
        "study_first_submitted",
        "results_first_posted",
        "has_results",
        "org_study_id",
    ]
    list_fields = [
        "phases",
        "conditions",
        "interventions",
        "collaborators",
        "countries",
        "secondary_ids",
    ]
    counts = {name: 0 for name in [*scalar_fields, *list_fields]}
    for rec in records:
        for name in scalar_fields:
            if rec.get(name) is None:
                counts[name] += 1
        for name in list_fields:
            if not rec.get(name):
                counts[name] += 1
    return counts


# -- main --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PHOENIX-003 ClinicalTrials.gov firm-anchored harvest (frozen spec)."
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="one page per query, writes _smoke_* artefacts only",
    )
    parser.add_argument(
        "--limit-pages",
        type=int,
        default=None,
        metavar="N",
        help="stop after N pages per query (implies --smoke; real artefacts stay untouched)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        metavar="S",
        help="per-request socket timeout in seconds (default 120)",
    )
    args = parser.parse_args(argv)

    # Any page-limited run is a smoke run and writes only the _smoke_* artefacts,
    # so a truncated harvest can never masquerade as the real dataset.
    smoke = args.smoke or args.limit_pages is not None
    if args.limit_pages is not None:
        if args.limit_pages < 1:
            print("--limit-pages must be >= 1", file=sys.stderr)
            return 2
        limit_pages: int | None = args.limit_pages
    else:
        limit_pages = 1 if args.smoke else None

    dataset_path = SMOKE_DATASET if smoke else FULL_DATASET
    manifest_path = SMOKE_MANIFEST if smoke else FULL_MANIFEST
    mode = "SMOKE" if smoke else "FULL"

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    FETCH_DIR.mkdir(parents=True, exist_ok=True)

    print(
        f"PHOENIX-003 CTgov harvest starting: mode={mode} "
        f"limit_pages={limit_pages} timeout={args.timeout}s",
        flush=True,
    )
    print(f"  endpoint  {API_ENDPOINT}", flush=True)
    print(f"  dataset   {dataset_path.relative_to(ROOT).as_posix()}", flush=True)
    print(f"  manifest  {manifest_path.relative_to(ROOT).as_posix()}", flush=True)
    print(
        f"  fields    {len(FIELDS)} requested: {FIELDS_PARAM}",
        flush=True,
    )
    print(
        f"  politeness min_delay={MIN_DELAY_S}s retries={MAX_RETRIES} "
        f"backoff={BACKOFF_S}s",
        flush=True,
    )

    t_harvest = time.monotonic()
    try:
        unique_records, query_entries, notes = harvest(limit_pages, args.timeout)
    except FetchError as exc:
        print(f"ABORT: {exc}", file=sys.stderr, flush=True)
        return 3
    print(
        f"harvest complete: {len(unique_records)} unique raw records "
        f"from {len(query_entries)} queries in {time.monotonic() - t_harvest:.1f}s",
        flush=True,
    )

    # Client-side first_posted window filter (rows with null first_posted are kept).
    retained: list[dict] = []
    dropped: list[dict] = []
    unparseable: list[dict] = []
    for rec in unique_records:
        fp = rec["first_posted"]
        if fp is None:
            retained.append(rec)
            continue
        key = parse_date_key(fp)
        if key is None:
            unparseable.append(rec)
            retained.append(rec)
            continue
        if DATE_MIN <= key <= DATE_MAX:
            retained.append(rec)
        else:
            dropped.append(rec)

    retained_ids = {rec["nct_id"] for rec in retained}
    for entry in query_entries:
        ids = entry.pop("_nct_ids")
        entry["records_retained"] = sum(1 for nct in ids if nct in retained_ids)

    # Per-firm retained counts: firm that first returned the retained study.
    per_firm: dict[str, int] = {firm: 0 for firm, _ in FIRMS}
    for rec in retained:
        per_firm[rec["source_firm"]] = per_firm.get(rec["source_firm"], 0) + 1

    multi_query = [rec["nct_id"] for rec in retained if len(rec["api_query"]) > 1]
    device_records = sum(
        1
        for rec in retained
        if any(
            (iv.get("type") or "").upper() == "DEVICE" for iv in rec["interventions"]
        )
    )
    first_posted_null = sum(1 for rec in retained if rec["first_posted"] is None)

    # Write dataset atomically.
    payload = serialise_records(retained)
    gz_payload = gzip_bytes(payload)
    write_atomic(dataset_path, gz_payload)
    dataset_bytes = dataset_path.stat().st_size
    dataset_sha = sha256_file(dataset_path)

    lines, problems = verify_dataset(dataset_path, len(retained))
    if problems:
        for problem in problems:
            print(f"VERIFY PROBLEM: {problem}", file=sys.stderr, flush=True)
        raise FetchError(
            "dataset verification failed; artefact left in place for inspection, "
            "manifest NOT written — investigate before re-running"
        )
    print(
        f"verified read-back: {lines} gzip lines == {len(retained)} retained records; "
        f"all lines parse as JSON",
        flush=True,
    )

    nulls = field_null_counts(retained)
    now = utc_now_iso()

    limitations = [
        "Harvest is firm-anchored (query.spons) and independent of any regulatory record; "
        "no server-side date filter was used.",
        f"fields= requested exactly the frozen list of {len(FIELDS)} fields; "
        "compact file drops nothing else from the study object.",
        f"Date window filter applied client-side to first_posted in "
        f"[{DATE_MIN[0]:04d}-{DATE_MIN[1]:02d}-{DATE_MIN[2]:02d}, "
        f"{DATE_MAX[0]:04d}-{DATE_MAX[1]:02d}-{DATE_MAX[2]:02d}]; rows with null "
        "first_posted are retained. Upstream date strings are kept verbatim "
        "(YYYY-MM-DD or YYYY-MM); no day is invented.",
        "Dedup by nct_id: the first query that returned a study owns the record; "
        "additional query strings are appended to api_query joined by ' | '. "
        "Records returned by more than one query therefore keep the first record's "
        "source_firm and fetched_at.",
        f"Raw unique records before the window filter: {len(unique_records)}; "
        f"dropped as out-of-window: {len(dropped)}; retained: {len(retained)}.",
        f"Retained records: {len(retained)}; per firm (first-owner attribution): "
        + ", ".join(f"{firm}={count}" for firm, count in per_firm.items())
        + ".",
        f"Retained records with first_posted == null: {first_posted_null}.",
        f"Retained records with at least one interventions[] entry of type DEVICE: "
        f"{device_records}.",
        f"Distinct nct_id returned by more than one query (retained set): "
        f"{len(multi_query)}.",
        "per_field_nulls counts records whose value is null; for list-valued fields "
        "(phases, conditions, interventions, collaborators, countries, secondary_ids) "
        "an empty list is counted as null.",
        f"queried records_returned is the count of studies returned by the API for that "
        f"query (pre-filter, pre-dedup); records_retained is the count of that query's "
        f"nct_ids present in the final retained file, so a study returned by several "
        f"queries counts under each of them. requests counts HTTP attempts including "
        f"retries; pages counts successfully processed pages.",
        "fetched_at is wall-clock time at page retrieval and is the only "
        "non-deterministic field; everything else is deterministic given identical "
        "upstream bytes. Gzip is written with mtime=0.",
        f"Politeness: '{USER_AGENT}', >= {MIN_DELAY_S}s between request starts, "
        f"{MAX_RETRIES} retries with {BACKOFF_S}s backoff; the harvest aborts loudly "
        f"instead of writing a partial file.",
    ]
    if unparseable:
        limitations.append(
            f"{len(unparseable)} retained records have an unparseable first_posted "
            f"string; kept with a warning: "
            f"{sorted({rec['first_posted'] for rec in unparseable})[:5]}"
        )
    if mode == "SMOKE":
        limitations.append(
            f"SMOKE RUN: at most {limit_pages} page(s) per query, so the corpus is "
            f"partial by construction and these artefacts must not be used as data."
        )
    limitations.extend(notes)

    files = [
        {
            "path": dataset_path.relative_to(ROOT).as_posix(),
            "bytes": dataset_bytes,
            "sha256": dataset_sha,
            "lines": lines,
        }
    ]

    counts = {
        "records_total": len(unique_records),
        "records_retained": len(retained),
        "per_field_nulls": nulls,
        "records_fetched_all_queries": sum(
            entry["records_returned"] for entry in query_entries
        ),
        "records_dropped_first_posted_window": len(dropped),
        "records_retained_null_first_posted": first_posted_null,
        "records_retained_with_device_intervention": device_records,
        "distinct_nct_multi_query": len(multi_query),
        "per_firm": per_firm,
        "per_query_retained": {
            f'{entry["firm"]}:{entry["api_query"]}': entry["records_retained"]
            for entry in query_entries
        },
    }

    manifest = {
        "generated_at": now,
        "endpoint": API_ENDPOINT,
        "queries": [
            {k: v for k, v in entry.items() if not k.startswith("_")}
            for entry in query_entries
        ],
        "counts": counts,
        "files": files,
        "limitations": limitations,
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    write_atomic(manifest_path, manifest_bytes)
    manifest_bytes_on_disk = manifest_path.stat().st_size
    manifest_sha = sha256_file(manifest_path)

    print("", flush=True)
    print("=== harvest summary ===", flush=True)
    print(f"retained records      : {len(retained)}", flush=True)
    print(f"per firm              : {per_firm}", flush=True)
    print(f"first_posted null     : {first_posted_null}", flush=True)
    print(f"DEVICE interventions  : {device_records}", flush=True)
    print(f"multi-query nct_ids   : {len(multi_query)}", flush=True)
    print(f"dropped out-of-window : {len(dropped)}", flush=True)
    print(
        f"dataset               : {dataset_path} "
        f"({dataset_bytes} bytes, sha256={dataset_sha}, lines={lines})",
        flush=True,
    )
    print(
        f"manifest              : {manifest_path} "
        f"({manifest_bytes_on_disk} bytes, sha256={manifest_sha})",
        flush=True,
    )
    for entry in query_entries:
        print(
            f"  {entry['firm']:<12} {entry['api_query']!r:<40} "
            f"http={entry['http_status']} pages={entry['pages']} "
            f"returned={entry['records_returned']} retained={entry['records_retained']} "
            f"reported_total={entry['reported_hit_count']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130)
    except FetchError as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        raise SystemExit(3)
