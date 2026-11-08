#!/usr/bin/env python3
"""PHOENIX-003 — extension-stratum external-source harvest (eight pre-registered firms).

The protocol's extension rule fired (fewer than five core firms had >= 5 anchors), so the
sample is extended to eight already-registered device firms.  This script harvests BOTH
external sources for those eight firms and writes records that are **schema-compatible
with the core harvest contract in ``FETCH_SPEC.md``** (the same linker consumes them),
plus an extra key ``stratum: "extension"``.

Outputs (full run):
    experiments/phoenix003/dataset/ctgov_ext_compact.jsonl.gz
    experiments/phoenix003/dataset/epmc_ext_compact.jsonl.gz
    experiments/phoenix003/fetch/EXT_FETCH_MANIFEST.json
    experiments/phoenix003/fetch/fetch_ext_run.log        (full stdout of the run)

Smoke run (``--smoke``) writes the same artefacts under ``_smoke_`` names and never
touches the real files:
    experiments/phoenix003/dataset/_smoke_ctgov_ext_compact.jsonl.gz
    experiments/phoenix003/dataset/_smoke_epmc_ext_compact.jsonl.gz
    experiments/phoenix003/fetch/_smoke_EXT_FETCH_MANIFEST.json
    experiments/phoenix003/fetch/_smoke_fetch_ext_run.log

Usage:
    python fetch_ext.py                                  # full harvest, both sources
    python fetch_ext.py --smoke                          # 1 page per query -> _smoke_* files
    python fetch_ext.py --smoke --limit-pages 2          # 2 pages per query -> _smoke_* files
    python fetch_ext.py --firms abbott,bd                # restrict firms (debug / partial smoke)

Contract (frozen in FETCH_SPEC.md, not to be changed here):
  * ClinicalTrials.gov API v2, ``query.spons``, pageSize=1000, nextPageToken, countTotal=true
    on the first request, and the frozen list of 25 ``fields``.
  * Europe PMC REST search, format=json, resultType=core, pageSize=1000, cursorMark
    pagination, query suffix `` AND (FIRST_PDATE:[2012-01-01 TO 2025-12-31])``.
  * User-Agent ``MedRadar-PHOENIX003/1.0 (research; contact ...)``, >= 0.35 s between
    request starts, 3 retries with 1/2/4 s backoff, abort loudly instead of writing a
    partial file.
  * CT.gov: client-side ``first_posted`` window [2010-01-01, 2025-12-31], null retained.
  * EPMC: date fallback ``firstPublicationDate`` -> ``electronicPublicationDate`` ->
    ``firstIndexDate`` -> ``pubYear + "-01-01"`` recorded in ``date_basis``; abstract
    whitespace-collapsed and truncated to 2000 chars with ``abstract_truncated``.
  * Dedup CT.gov by ``nct_id`` and EPMC by ``(source, id)``; the first record wins, with
    ``api_query`` joined by ``" | "`` and ``source_firm`` joined by ``"+"`` (sorted).

Standard library only; Python 3.12; deterministic given identical upstream bytes
(``fetched_at`` is the only wall-clock field; gzip is written with mtime=0).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import socket
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------------------
# paths and frozen constants
# --------------------------------------------------------------------------------------

SCRIPT_PATH = Path(__file__).resolve()
FETCH_DIR = SCRIPT_PATH.parent                 # experiments/phoenix003/fetch
BASE_DIR = FETCH_DIR.parent                    # experiments/phoenix003
DATASET_DIR = BASE_DIR / "dataset"             # experiments/phoenix003/dataset
REPO_ROOT = BASE_DIR.parent.parent             # worktree root

USER_AGENT = (
    "MedRadar-PHOENIX003/1.0 "
    "(research; contact chazy11@users.noreply.github.com)"
)

CT_ENDPOINT = "https://clinicaltrials.gov/api/v2/studies"
EPMC_ENDPOINT = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

CT_PAGE_SIZE = 1000
EPMC_PAGE_SIZE = 1000
CT_TIMEOUT_S = 120.0
EPMC_TIMEOUT_S = 180.0                 # a 1000-record core page can take 60-90 s
MIN_DELAY_S = 0.35                     # minimum gap between request starts
RETRY_BACKOFF_S = (1.0, 2.0, 4.0)      # 3 retries
RETRYABLE_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})
HIT_COUNT_ALERT = 15000                # report instead of paging forever
ABSTRACT_MAX_CHARS = 2000
STRATUM = "extension"

# Europe PMC frozen window (appended to every AFF: clause, exactly as specified).
EPMC_WINDOW_CLAUSE = "FIRST_PDATE:[2012-01-01 TO 2025-12-31]"
EPMC_QUERY_SUFFIX = " AND (" + EPMC_WINDOW_CLAUSE + ")"

# ClinicalTrials.gov client-side first_posted window.
CT_WINDOW_START = (2010, 1, 1)
CT_WINDOW_END = (2025, 12, 31)

# The frozen 25 fields, byte-identical to the core harvest (order and spelling matter
# to the API; ``StudyFirstSubmitDate`` is the plain-string field, not ``...Struct``).
CT_FIELDS = (
    "NCTId,BriefTitle,OfficialTitle,Acronym,OverallStatus,StudyType,Phase,Condition,"
    "InterventionName,InterventionType,InterventionDescription,LeadSponsorName,"
    "CollaboratorName,EnrollmentCount,StartDate,PrimaryCompletionDate,CompletionDate,"
    "StudyFirstPostDate,LastUpdatePostDate,StudyFirstSubmitDate,ResultsFirstPostDate,"
    "HasResults,LocationCountry,OrgStudyId,SecondaryId"
)
CT_FIELD_NAMES = tuple(CT_FIELDS.split(","))

# Frozen query terms, exactly as pre-registered for the extension stratum.
FIRMS = (
    {
        "key": "abbott",
        "display": "Abbott",
        "ctgov_queries": ("Abbott",),
        "epmc_query": 'AFF:"Abbott"',
        "aff_terms": ("Abbott",),
    },
    {
        "key": "baxter",
        "display": "Baxter",
        "ctgov_queries": ("Baxter",),
        "epmc_query": 'AFF:"Baxter"',
        "aff_terms": ("Baxter",),
    },
    {
        "key": "bd",
        "display": "Becton Dickinson (BD)",
        "ctgov_queries": ("Becton Dickinson", "BD"),
        "epmc_query": '(AFF:"Becton Dickinson" OR AFF:"BD")',
        "aff_terms": ("Becton Dickinson", "BD"),
    },
    {
        "key": "boston_scientific",
        "display": "Boston Scientific",
        "ctgov_queries": ("Boston Scientific",),
        "epmc_query": 'AFF:"Boston Scientific"',
        "aff_terms": ("Boston Scientific",),
    },
    {
        "key": "edwards_lifesciences",
        "display": "Edwards Lifesciences",
        "ctgov_queries": ("Edwards Lifesciences",),
        "epmc_query": 'AFF:"Edwards Lifesciences"',
        "aff_terms": ("Edwards Lifesciences",),
    },
    {
        "key": "stryker",
        "display": "Stryker",
        "ctgov_queries": ("Stryker",),
        "epmc_query": 'AFF:"Stryker"',
        "aff_terms": ("Stryker",),
    },
    {
        "key": "siemens_healthineers",
        "display": "Siemens Healthineers",
        "ctgov_queries": ("Siemens Healthineers",),
        "epmc_query": 'AFF:"Siemens Healthineers"',
        "aff_terms": ("Siemens Healthineers",),
    },
    {
        "key": "zimmer_biomet",
        "display": "Zimmer Biomet",
        "ctgov_queries": ("Zimmer Biomet",),
        "epmc_query": 'AFF:"Zimmer Biomet"',
        "aff_terms": ("Zimmer Biomet",),
    },
)
FIRM_BY_KEY = {firm["key"]: firm for firm in FIRMS}
FIRM_ORDER = tuple(firm["key"] for firm in FIRMS)

# EPMC affiliation filter: word-token equality, never a bare substring, so that ``BD``
# does not match French "Bd" (boulevard) or fragments inside other words.  Matching
# affiliation strings are kept verbatim in ``firm_affiliations``.
AFF_REGEX = {
    firm["key"]: tuple(
        re.compile(
            r"(?<![A-Za-z0-9])"
            + r"\s+".join(re.escape(part) for part in term.split())
            + r"(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        for term in firm["aff_terms"]
    )
    for firm in FIRMS
}


def utc_now_iso() -> str:
    """Wall-clock timestamp, the only non-deterministic value in the artefacts."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------------------
# output paths
# --------------------------------------------------------------------------------------

def output_paths(smoke: bool) -> dict:
    if smoke:
        return {
            "ctgov": DATASET_DIR / "_smoke_ctgov_ext_compact.jsonl.gz",
            "epmc": DATASET_DIR / "_smoke_epmc_ext_compact.jsonl.gz",
            "manifest": FETCH_DIR / "_smoke_EXT_FETCH_MANIFEST.json",
            "log": FETCH_DIR / "_smoke_fetch_ext_run.log",
        }
    return {
        "ctgov": DATASET_DIR / "ctgov_ext_compact.jsonl.gz",
        "epmc": DATASET_DIR / "epmc_ext_compact.jsonl.gz",
        "manifest": FETCH_DIR / "EXT_FETCH_MANIFEST.json",
        "log": FETCH_DIR / "fetch_ext_run.log",
    }


# --------------------------------------------------------------------------------------
# logging (stdout + log file, so the log is the full stdout of the run)
# --------------------------------------------------------------------------------------

class _Tee:
    def __init__(self, path: Path) -> None:
        self._terminal = sys.stdout
        self._file = open(path, "w", encoding="utf-8", newline="\n")

    def write(self, text: str) -> int:
        self._terminal.write(text)
        self._file.write(text)
        return len(text)

    def flush(self) -> None:
        self._terminal.flush()
        self._file.flush()

    def isatty(self) -> bool:  # pragma: no cover - cosmetic
        return False

    def close_log(self) -> None:
        try:
            self._file.flush()
        finally:
            self._file.close()


def log(message: str = "") -> None:
    print(message, flush=True)


# --------------------------------------------------------------------------------------
# HTTP with politeness + retries
# --------------------------------------------------------------------------------------

class HarvestError(RuntimeError):
    """Raised when the harvest cannot continue; the run must abort loudly."""


class RateLimiter:
    """Enforce the frozen minimum gap between request starts (retries included)."""

    def __init__(self, min_delay: float = MIN_DELAY_S) -> None:
        self.min_delay = min_delay
        self._last_start: float | None = None

    def before_request(self) -> None:
        if self._last_start is not None:
            wait = self.min_delay - (time.monotonic() - self._last_start)
            if wait > 0:
                time.sleep(wait)
        self._last_start = time.monotonic()


def http_get_json(
    url: str,
    params: dict,
    timeout_s: float,
    limiter: RateLimiter,
    label: str,
) -> tuple[int, dict, float, int]:
    """GET ``url`` with ``params``; return ``(http_status, parsed_json, elapsed_s, attempts)``.

    Retries up to 3 times with 1/2/4 s backoff on transient HTTP/network failures and
    raises :class:`HarvestError` on permanent failure.  ``attempts`` counts HTTP attempts
    including retries, which is what the manifest's ``requests`` field means.
    """
    full_url = url + "?" + urllib.parse.urlencode(params)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    attempts = 0
    while True:
        attempts += 1
        limiter.before_request()
        request = urllib.request.Request(full_url, headers=headers)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                status = int(getattr(response, "status", 200))
                payload = response.read()
            elapsed = time.monotonic() - started
            try:
                data = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise HarvestError(
                    f"{label}: unparseable JSON response "
                    f"(HTTP {status}, {len(payload)} bytes)"
                ) from exc
            return status, data, elapsed, attempts
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read()[:400].decode("utf-8", "replace")
            except Exception:  # noqa: BLE001 - diagnostic only
                detail = "<no body>"
            if exc.code in RETRYABLE_HTTP and attempts <= len(RETRY_BACKOFF_S):
                delay = RETRY_BACKOFF_S[attempts - 1]
                log(f"  retry {attempts}/{len(RETRY_BACKOFF_S)}: HTTP {exc.code} "
                    f"(sleep {delay:.1f}s) {label}")
                time.sleep(delay)
                continue
            raise HarvestError(
                f"{label}: HTTP {exc.code} after {attempts} attempt(s): {detail}"
            ) from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            if attempts <= len(RETRY_BACKOFF_S):
                delay = RETRY_BACKOFF_S[attempts - 1]
                log(f"  retry {attempts}/{len(RETRY_BACKOFF_S)}: "
                    f"{type(exc).__name__}: {exc} (sleep {delay:.1f}s) {label}")
                time.sleep(delay)
                continue
            raise HarvestError(
                f"{label}: network failure after {attempts} attempt(s): "
                f"{type(exc).__name__}: {exc}"
            ) from exc


# --------------------------------------------------------------------------------------
# ClinicalTrials.gov mapping helpers
# --------------------------------------------------------------------------------------

def _ct_date(module: dict, key: str):
    """Read a CT.gov date that is either ``{key: {"date": ...}}`` or a plain string."""
    value = module.get(key)
    if isinstance(value, dict):
        return value.get("date")
    return value


def _ct_interventions(arms_module: dict) -> list:
    out = []
    for item in arms_module.get("interventions") or []:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "type": item.get("type"),
                "name": item.get("name"),
                "description": item.get("description"),
            }
        )
    return out


def _ct_countries(contacts_module: dict) -> list:
    out = []
    for location in contacts_module.get("locations") or []:
        if not isinstance(location, dict):
            continue
        country = location.get("country")
        if country and country not in out:
            out.append(country)
    return out


def _ct_names(items) -> list:
    out = []
    for item in items or []:
        if isinstance(item, dict):
            name = item.get("name")
            if name:
                out.append(name)
        elif isinstance(item, str) and item:
            out.append(item)
    return out


def _ct_secondary_ids(ident_module: dict) -> list:
    out = []
    for item in ident_module.get("secondaryIdInfos") or []:
        value = item.get("id") if isinstance(item, dict) else item
        if value:
            out.append(value)
    return out


def compact_ctgov(study: dict, fetched_at: str) -> dict:
    """Map one CT.gov v2 study (25 frozen fields) to the frozen compact schema."""
    protocol = study.get("protocolSection") or {}
    ident = protocol.get("identificationModule") or {}
    status = protocol.get("statusModule") or {}
    sponsors = protocol.get("sponsorCollaboratorsModule") or {}
    design = protocol.get("designModule") or {}
    conditions = protocol.get("conditionsModule") or {}
    arms = protocol.get("armsInterventionsModule") or {}
    contacts = protocol.get("contactsLocationsModule") or {}

    enrollment_info = design.get("enrollmentInfo") or {}
    return {
        "nct_id": ident.get("nctId"),
        "source_firm": None,   # filled in after cross-query dedup
        "api_query": None,     # filled in after cross-query dedup
        "brief_title": ident.get("briefTitle"),
        "official_title": ident.get("officialTitle"),
        "acronym": ident.get("acronym"),
        "overall_status": status.get("overallStatus"),
        "study_type": design.get("studyType"),
        "phases": design.get("phases") or [],
        "conditions": conditions.get("conditions") or [],
        "interventions": _ct_interventions(arms),
        "lead_sponsor": (sponsors.get("leadSponsor") or {}).get("name"),
        "collaborators": _ct_names(sponsors.get("collaborators")),
        "enrollment": enrollment_info.get("count"),
        "start_date": _ct_date(status, "startDateStruct"),
        "primary_completion_date": _ct_date(status, "primaryCompletionDateStruct"),
        "completion_date": _ct_date(status, "completionDateStruct"),
        "first_posted": _ct_date(status, "studyFirstPostDateStruct"),
        "last_update_posted": _ct_date(status, "lastUpdatePostDateStruct"),
        "study_first_submitted": _ct_date(status, "studyFirstSubmitDate"),
        "results_first_posted": _ct_date(status, "resultsFirstPostDateStruct"),
        "has_results": study.get("hasResults"),
        "countries": _ct_countries(contacts),
        "org_study_id": (ident.get("orgStudyIdInfo") or {}).get("id"),
        "secondary_ids": _ct_secondary_ids(ident),
        "fetched_at": fetched_at,
        "stratum": STRATUM,
    }


_DATE_RE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$")


def ct_first_posted_in_window(value) -> bool | None:
    """True if ``first_posted`` falls in [2010-01-01, 2025-12-31] (null is retained).

    Returns ``None`` when a non-null value cannot be parsed, so the caller can count it.
    Upstream date strings are kept verbatim (YYYY-MM-DD or YYYY-MM); no day invented.
    """
    if value is None:
        return True
    if not isinstance(value, str):
        return None
    match = _DATE_RE.match(value.strip())
    if not match:
        return None
    parts = (int(match.group(1)), int(match.group(2)), int(match.group(3) or 1))
    return CT_WINDOW_START <= parts <= CT_WINDOW_END


# --------------------------------------------------------------------------------------
# ClinicalTrials.gov harvest
# --------------------------------------------------------------------------------------

def harvest_ctgov(firms, limiter: RateLimiter, limit_pages: int | None):
    """Harvest the CT.gov sponsor queries; return (retained records, stats, query stats)."""
    records: dict[str, dict] = {}
    record_firms: dict[str, list[str]] = {}
    record_queries: dict[str, list[str]] = {}
    query_ids: dict[tuple[str, str], list[str]] = {}
    query_stats: list[dict] = []
    skipped_queries: list[dict] = []

    for firm in firms:
        for query in firm["ctgov_queries"]:
            label = f"ctgov {firm['key']} q={query!r}"
            started_at = utc_now_iso()
            log(f"[ctgov] {firm['key']:<20} q={query!r} starting")
            page = 0
            token = None
            requests_total = 0
            returned = 0
            reported_total = None
            status_last = None
            ids_this_query: list[str] = []
            skipped = False

            while True:
                page += 1
                params = {
                    "query.spons": query,
                    "pageSize": str(CT_PAGE_SIZE),
                    "fields": CT_FIELDS,
                }
                if page == 1:
                    params["countTotal"] = "true"
                if token:
                    params["pageToken"] = token

                status, data, elapsed, attempts = http_get_json(
                    CT_ENDPOINT, params, CT_TIMEOUT_S, limiter, f"{label} page={page}"
                )
                requests_total += attempts
                status_last = status
                studies = data.get("studies") or []
                if reported_total is None:
                    reported_total = data.get("totalCount")

                # Pathological-volume rule: report instead of paging forever.
                if page == 1 and reported_total is not None and reported_total > HIT_COUNT_ALERT:
                    log(f"  ALERT {label}: reported hit count {reported_total} > "
                        f"{HIT_COUNT_ALERT}; query NOT paged (reported, not harvested)")
                    skipped_queries.append(
                        {
                            "source": "ctgov",
                            "firm": firm["key"],
                            "api_query": query,
                            "reported_hit_count": reported_total,
                        }
                    )
                    skipped = True
                    break

                fetched_at = utc_now_iso()
                for study in studies:
                    record = compact_ctgov(study, fetched_at)
                    nct_id = record["nct_id"]
                    if not nct_id:
                        continue
                    ids_this_query.append(nct_id)
                    if nct_id not in records:
                        records[nct_id] = record
                        record_firms[nct_id] = [firm["key"]]
                        record_queries[nct_id] = [query]
                    else:
                        if firm["key"] not in record_firms[nct_id]:
                            record_firms[nct_id].append(firm["key"])
                        if query not in record_queries[nct_id]:
                            record_queries[nct_id].append(query)

                returned += len(studies)
                next_token = data.get("nextPageToken")
                log(f"  page={page} http={status} got={len(studies)} "
                    f"total={reported_total} cum={returned} t={elapsed:.1f}s")
                if limit_pages is not None and page >= limit_pages:
                    if next_token:
                        log(f"  --limit-pages={limit_pages} reached; more pages exist (smoke)")
                    break
                if not next_token:
                    break
                token = next_token

            finished_at = utc_now_iso()
            if not skipped:
                query_ids[(firm["key"], query)] = ids_this_query
            query_stats.append(
                {
                    "source": "ctgov",
                    "firm": firm["key"],
                    "api_query": query,
                    "http_status": status_last,
                    "requests": requests_total,
                    "pages": page,
                    "reported_hit_count": reported_total,
                    "records_returned": returned,
                    "records_retained": 0,  # filled in after the window filter
                    "started_at": started_at,
                    "finished_at": finished_at,
                }
            )
            log(f"[ctgov] {firm['key']:<20} q={query!r} done: pages={page} "
                f"returned={returned} reported_total={reported_total}")

    # Resolve dedup provenance (first record wins; provenance joined).
    raw_records = []
    for nct_id, record in records.items():
        record["source_firm"] = "+".join(sorted(record_firms[nct_id]))
        record["api_query"] = " | ".join(dict.fromkeys(record_queries[nct_id]))
        raw_records.append(record)

    # Frozen client-side window on first_posted.
    retained = []
    dropped = 0
    unparseable_dates = 0
    first_owner: dict[str, int] = {}
    membership: dict[str, int] = {}
    for record in raw_records:
        in_window = ct_first_posted_in_window(record["first_posted"])
        if in_window is True:
            retained.append(record)
            owner = record_firms[record["nct_id"]][0]
            first_owner[owner] = first_owner.get(owner, 0) + 1
            for firm_key in record["source_firm"].split("+"):
                membership[firm_key] = membership.get(firm_key, 0) + 1
        else:
            if in_window is None:
                unparseable_dates += 1
                log(f"  WARNING unparseable first_posted {record['first_posted']!r} "
                    f"for {record['nct_id']}; dropped")
            dropped += 1

    retained_ids = {record["nct_id"] for record in retained}
    for entry in query_stats:
        ids = query_ids.get((entry["firm"], entry["api_query"]), [])
        entry["records_retained"] = sum(1 for nct_id in ids if nct_id in retained_ids)

    stats = {
        "records_fetched_all_queries": sum(
            entry["records_returned"] for entry in query_stats
        ),
        "records_total": len(records),
        "records_retained": len(retained),
        "records_dropped_first_posted_window": dropped,
        "records_unparseable_first_posted": unparseable_dates,
        "records_retained_null_first_posted": sum(
            1 for record in retained if record["first_posted"] is None
        ),
        "records_retained_with_device_intervention": sum(
            1
            for record in retained
            if any(
                isinstance(item.get("type"), str)
                and item["type"].upper() == "DEVICE"
                for item in record["interventions"]
            )
        ),
        "distinct_nct_multi_query": sum(
            1 for nct_id in retained_ids if len(record_queries[nct_id]) > 1
        ),
        "distinct_nct_multi_firm": sum(
            1 for nct_id in retained_ids if len(record_firms[nct_id]) > 1
        ),
        "per_firm": dict(sorted(first_owner.items())),
        "per_firm_membership": dict(sorted(membership.items())),
        "per_field_nulls": _ct_null_counts(retained),
        "skipped_queries": skipped_queries,
    }
    return retained, stats, query_stats


def _ct_null_counts(records) -> dict:
    list_fields = {
        "phases", "conditions", "interventions", "collaborators", "countries", "secondary_ids",
    }
    fields = (
        "brief_title", "official_title", "acronym", "overall_status", "study_type",
        "lead_sponsor", "enrollment", "start_date", "primary_completion_date",
        "completion_date", "first_posted", "last_update_posted", "study_first_submitted",
        "results_first_posted", "has_results", "org_study_id", "phases", "conditions",
        "interventions", "collaborators", "countries", "secondary_ids",
    )
    counts = {}
    for field in fields:
        if field in list_fields:
            counts[field] = sum(1 for record in records if not record.get(field))
        else:
            counts[field] = sum(1 for record in records if record.get(field) is None)
    return counts


# --------------------------------------------------------------------------------------
# Europe PMC mapping helpers
# --------------------------------------------------------------------------------------

def _epmc_raw_affiliations(result: dict) -> list:
    out = []
    top = result.get("affiliation")
    if isinstance(top, str):
        out.append(top)
    author_list = result.get("authorList") or {}
    for author in author_list.get("author") or []:
        if not isinstance(author, dict):
            continue
        details = author.get("authorAffiliationDetailsList") or {}
        for item in details.get("authorAffiliation") or []:
            value = item.get("affiliation") if isinstance(item, dict) else item
            if isinstance(value, str):
                out.append(value)
    return out


def _match_affiliations(raw_values, firm_key: str) -> list:
    regexes = AFF_REGEX[firm_key]
    matched: list[str] = []
    for value in raw_values:
        if not value or not value.strip():
            continue
        if any(regex.search(value) for regex in regexes) and value not in matched:
            matched.append(value)
    return matched


def _string_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str) and item:
                out.append(item)
        return out
    return []


def compact_epmc(result: dict, firm_key: str, api_query: str, fetched_at: str) -> dict | None:
    """Map one Europe PMC core record to the frozen compact schema (minus firm provenance)."""
    record_id = result.get("id")
    if record_id in (None, ""):
        return None

    first_publication_date = result.get("firstPublicationDate")
    electronic_publication_date = result.get("electronicPublicationDate")
    first_index_date = result.get("firstIndexDate")
    pub_year = result.get("pubYear")

    # Frozen fallback order, recording which source was used.
    if first_publication_date:
        public_date = first_publication_date
        date_basis = "firstPublicationDate"
    elif electronic_publication_date:
        public_date = electronic_publication_date
        date_basis = "electronicPublicationDate"
    elif first_index_date:
        public_date = first_index_date
        date_basis = "firstIndexDate"
    elif pub_year not in (None, ""):
        public_date = f"{pub_year}-01-01"
        date_basis = "pubYear"
    else:
        public_date = None
        date_basis = "none"

    journal_info = result.get("journalInfo") or {}
    journal_title = (
        (journal_info.get("journal") or {}).get("title")
        or journal_info.get("journalTitle")
        or result.get("journalTitle")
    )

    raw_abstract = result.get("abstractText")
    if raw_abstract is None or not str(raw_abstract).strip():
        abstract = None
        abstract_truncated = False
    else:
        abstract = " ".join(str(raw_abstract).split())
        abstract_truncated = len(abstract) > ABSTRACT_MAX_CHARS
        if abstract_truncated:
            abstract = abstract[:ABSTRACT_MAX_CHARS]

    raw_open_access = result.get("isOpenAccess")
    if raw_open_access is None:
        is_open_access = None
    else:
        is_open_access = str(raw_open_access).strip().upper() in ("Y", "YES", "TRUE")

    raw_cited_by = result.get("citedByCount")
    if raw_cited_by is None:
        cited_by_count = None
    else:
        try:
            cited_by_count = int(raw_cited_by)
        except (TypeError, ValueError):
            cited_by_count = None

    mesh_terms = []
    mesh_list = (result.get("meshHeadingList") or {}).get("meshHeading") or []
    for heading in mesh_list:
        if isinstance(heading, dict):
            name = heading.get("descriptorName")
            if name:
                mesh_terms.append(name)
        elif isinstance(heading, str) and heading:
            mesh_terms.append(heading)

    return {
        "source_firm": None,   # filled in after cross-query dedup
        "api_query": api_query,
        "id": record_id,
        "source": result.get("source"),
        "pmid": result.get("pmid"),
        "pmcid": result.get("pmcid"),
        "doi": result.get("doi"),
        "title": result.get("title"),
        "author_string": result.get("authorString"),
        "journal_title": journal_title,
        "pub_year": pub_year,
        "first_publication_date": public_date,
        "electronic_publication_date": electronic_publication_date,
        "first_index_date": first_index_date,
        "date_basis": date_basis,
        "pub_types": _string_list((result.get("pubTypeList") or {}).get("pubType")),
        "is_open_access": is_open_access,
        "cited_by_count": cited_by_count,
        "firm_affiliations": _match_affiliations(
            _epmc_raw_affiliations(result), firm_key
        ),
        "abstract": abstract,
        "abstract_truncated": abstract_truncated,
        "keywords": _string_list((result.get("keywordList") or {}).get("keyword")),
        "mesh_terms": mesh_terms,
        "fetched_at": fetched_at,
        "stratum": STRATUM,
    }


# --------------------------------------------------------------------------------------
# Europe PMC harvest
# --------------------------------------------------------------------------------------

def harvest_epmc(firms, limiter: RateLimiter, limit_pages: int | None):
    """Harvest the Europe PMC AFF: queries; return (records, stats, query stats)."""
    records: dict[tuple, dict] = {}
    record_firms: dict[tuple, list[str]] = {}
    record_queries: dict[tuple, list[str]] = {}
    query_keys: dict[tuple[str, str], list[tuple]] = {}
    query_stats: list[dict] = []
    skipped_queries: list[dict] = []
    skipped_missing_id = 0

    for firm in firms:
        clause = firm["epmc_query"]
        full_query = clause + EPMC_QUERY_SUFFIX
        label = f"epmc {firm['key']}"
        started_at = utc_now_iso()
        log(f"[epmc]  {firm['key']:<20} clause={clause!r} starting")
        cursor = "*"
        page = 0
        returned = 0
        reported_hit = None
        status_last = None
        requests_total = 0
        keys_this_query: list[tuple] = []
        skipped = False

        while True:
            page += 1
            params = {
                "query": full_query,
                "format": "json",
                "resultType": "core",
                "pageSize": str(EPMC_PAGE_SIZE),
                "cursorMark": cursor,
            }
            status, data, elapsed, attempts = http_get_json(
                EPMC_ENDPOINT, params, EPMC_TIMEOUT_S, limiter, f"{label} page={page}"
            )
            requests_total += attempts
            status_last = status
            results = (data.get("resultList") or {}).get("result") or []

            if page == 1:
                reported_hit = data.get("hitCount")
                if reported_hit is not None and reported_hit > HIT_COUNT_ALERT:
                    log(f"  ALERT {label}: reported hit count {reported_hit} > "
                        f"{HIT_COUNT_ALERT}; query NOT paged (reported, not harvested)")
                    skipped_queries.append(
                        {
                            "source": "epmc",
                            "firm": firm["key"],
                            "api_query": full_query,
                            "reported_hit_count": reported_hit,
                        }
                    )
                    skipped = True
                    break

            fetched_at = utc_now_iso()
            for result in results:
                record = compact_epmc(result, firm["key"], full_query, fetched_at)
                if record is None:
                    skipped_missing_id += 1
                    continue
                key = (record["source"], record["id"])
                keys_this_query.append(key)
                if key not in records:
                    records[key] = record
                    record_firms[key] = [firm["key"]]
                    record_queries[key] = [full_query]
                else:
                    if firm["key"] not in record_firms[key]:
                        record_firms[key].append(firm["key"])
                    if full_query not in record_queries[key]:
                        record_queries[key].append(full_query)

            returned += len(results)
            next_cursor = data.get("nextCursorMark")
            log(f"  page={page} http={status} got={len(results)} hit={reported_hit} "
                f"cum={returned} t={elapsed:.1f}s")
            if limit_pages is not None and page >= limit_pages:
                if next_cursor and next_cursor != cursor:
                    log(f"  --limit-pages={limit_pages} reached; more pages exist (smoke)")
                break
            if not next_cursor or next_cursor == cursor or not results:
                if reported_hit is not None and returned < reported_hit:
                    log(f"  WARNING {label}: pagination ended after {returned} of "
                        f"hitCount={reported_hit} records; shortfall recorded in manifest")
                break
            cursor = next_cursor

        finished_at = utc_now_iso()
        if not skipped:
            query_keys[(firm["key"], full_query)] = keys_this_query
        query_stats.append(
            {
                "source": "epmc",
                "firm": firm["key"],
                "api_query": full_query,
                "http_status": status_last,
                "requests": requests_total,
                "pages": page,
                "reported_hit_count": reported_hit,
                "records_returned": returned,
                "records_retained": 0,  # filled in below
                "started_at": started_at,
                "finished_at": finished_at,
            }
        )
        log(f"[epmc]  {firm['key']:<20} done: pages={page} returned={returned} "
            f"reported_total={reported_hit}")

    # Resolve dedup provenance (first record wins; provenance joined).
    retained = []
    first_owner: dict[str, int] = {}
    membership: dict[str, int] = {}
    for key, record in records.items():
        record["source_firm"] = "+".join(sorted(record_firms[key]))
        record["api_query"] = " | ".join(dict.fromkeys(record_queries[key]))
        retained.append(record)
        owner = record_firms[key][0]
        first_owner[owner] = first_owner.get(owner, 0) + 1
        for firm_key in record["source_firm"].split("+"):
            membership[firm_key] = membership.get(firm_key, 0) + 1

    retained_keys = set(records)
    for entry in query_stats:
        keys = query_keys.get((entry["firm"], entry["api_query"]), [])
        entry["records_retained"] = sum(1 for key in keys if key in retained_keys)

    date_basis_counts: dict[str, int] = {}
    per_firm_date_basis: dict[str, dict] = {}
    for record in retained:
        basis = record["date_basis"]
        date_basis_counts[basis] = date_basis_counts.get(basis, 0) + 1
        bucket = per_firm_date_basis.setdefault(record["source_firm"], {})
        bucket[basis] = bucket.get(basis, 0) + 1
    for bucket in per_firm_date_basis.values():
        bucket_sorted = dict(sorted(bucket.items()))
        bucket.clear()
        bucket.update(bucket_sorted)

    stats = {
        "records_fetched_all_queries": sum(
            entry["records_returned"] for entry in query_stats
        ),
        "records_total": len(records),
        "records_retained": len(retained),
        "records_skipped_missing_id": skipped_missing_id,
        "records_with_abstract": sum(1 for record in retained if record["abstract"]),
        "records_abstract_truncated": sum(
            1 for record in retained if record["abstract_truncated"]
        ),
        "records_with_firm_affiliations": sum(
            1 for record in retained if record["firm_affiliations"]
        ),
        "records_without_firm_affiliations": sum(
            1 for record in retained if not record["firm_affiliations"]
        ),
        "records_null_publication_date": sum(
            1 for record in retained if record["first_publication_date"] is None
        ),
        "date_basis_counts": dict(sorted(date_basis_counts.items())),
        "per_firm_date_basis": dict(sorted(per_firm_date_basis.items())),
        "per_firm": dict(sorted(first_owner.items())),
        "per_firm_membership": dict(sorted(membership.items())),
        "per_field_nulls": _epmc_null_counts(retained),
        "skipped_queries": skipped_queries,
    }
    return retained, stats, query_stats


def _epmc_null_counts(records) -> dict:
    list_fields = {"pub_types", "firm_affiliations", "keywords", "mesh_terms"}
    fields = (
        "pmid", "pmcid", "doi", "title", "author_string", "journal_title", "pub_year",
        "first_publication_date", "electronic_publication_date", "first_index_date",
        "pub_types", "is_open_access", "cited_by_count", "firm_affiliations",
        "abstract", "keywords", "mesh_terms",
    )
    counts = {}
    for field in fields:
        if field in list_fields:
            counts[field] = sum(1 for record in records if not record.get(field))
        else:
            counts[field] = sum(1 for record in records if record.get(field) is None)
    return counts


# --------------------------------------------------------------------------------------
# artefact writing / verification
# --------------------------------------------------------------------------------------

def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:  # pragma: no cover - defensive
        return str(path)


def file_fingerprint(path: Path) -> dict:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"path": repo_relative(path), "bytes": size, "sha256": digest.hexdigest()}


def write_jsonl_gz(path: Path, records) -> dict:
    """Atomically write records as gzip JSONL (mtime=0, deterministic bytes)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as gz:
            for record in records:
                line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                gz.write((line + "\n").encode("utf-8"))
    os.replace(tmp_path, path)
    return file_fingerprint(path)


def verify_jsonl_gz(path: Path, expected_lines: int) -> int:
    """Read the gzip back and prove line count and per-line JSON validity."""
    lines = 0
    with gzip.open(path, "rb") as handle:
        for line in handle:
            lines += 1
            try:
                json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise HarvestError(
                    f"read-back verification failed: {path} line {lines} is not valid JSON"
                ) from exc
    if lines != expected_lines:
        raise HarvestError(
            f"read-back verification failed: {path} has {lines} lines, "
            f"expected {expected_lines}"
        )
    return lines


def write_json(path: Path, payload: dict) -> dict:
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)
    return file_fingerprint(path)


# --------------------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------------------

def build_manifest(
    *,
    mode: str,
    firms,
    limit_pages: int | None,
    ct_stats: dict,
    epmc_stats: dict,
    ct_query_stats: list,
    epmc_query_stats: list,
    ct_file: dict,
    epmc_file: dict,
    ct_lines: int,
    epmc_lines: int,
) -> dict:
    queries = ct_query_stats + epmc_query_stats
    per_field_nulls = {}
    for field, count in ct_stats["per_field_nulls"].items():
        per_field_nulls[f"ctgov.{field}"] = count
    for field, count in epmc_stats["per_field_nulls"].items():
        per_field_nulls[f"epmc.{field}"] = count

    def per_query_retained(query_stats):
        return {
            f"{entry['firm']}:{entry['api_query']}": entry["records_retained"]
            for entry in query_stats
        }

    ct_counts = {
        "records_fetched_all_queries": ct_stats["records_fetched_all_queries"],
        "records_total": ct_stats["records_total"],
        "records_retained": ct_stats["records_retained"],
        "records_dropped_first_posted_window": ct_stats["records_dropped_first_posted_window"],
        "records_unparseable_first_posted": ct_stats["records_unparseable_first_posted"],
        "records_retained_null_first_posted": ct_stats["records_retained_null_first_posted"],
        "records_retained_with_device_intervention":
            ct_stats["records_retained_with_device_intervention"],
        "distinct_nct_multi_query": ct_stats["distinct_nct_multi_query"],
        "distinct_nct_multi_firm": ct_stats["distinct_nct_multi_firm"],
        "per_firm": ct_stats["per_firm"],
        "per_firm_membership": ct_stats["per_firm_membership"],
        "per_query_retained": per_query_retained(ct_query_stats),
        "per_field_nulls": ct_stats["per_field_nulls"],
        "skipped_queries": ct_stats["skipped_queries"],
    }
    epmc_counts = {
        "records_fetched_all_queries": epmc_stats["records_fetched_all_queries"],
        "records_total": epmc_stats["records_total"],
        "records_retained": epmc_stats["records_retained"],
        "records_skipped_missing_id": epmc_stats["records_skipped_missing_id"],
        "records_with_abstract": epmc_stats["records_with_abstract"],
        "records_abstract_truncated": epmc_stats["records_abstract_truncated"],
        "records_with_firm_affiliations": epmc_stats["records_with_firm_affiliations"],
        "records_without_firm_affiliations":
            epmc_stats["records_without_firm_affiliations"],
        "records_null_publication_date": epmc_stats["records_null_publication_date"],
        "date_basis_counts": epmc_stats["date_basis_counts"],
        "per_firm_date_basis": epmc_stats["per_firm_date_basis"],
        "per_firm": epmc_stats["per_firm"],
        "per_firm_membership": epmc_stats["per_firm_membership"],
        "per_query_retained": per_query_retained(epmc_query_stats),
        "per_field_nulls": epmc_stats["per_field_nulls"],
        "skipped_queries": epmc_stats["skipped_queries"],
    }

    limitations = [
        "EXTENSION STRATUM ONLY: these records cover the eight pre-registered extension "
        "firms (abbott, baxter, bd, boston_scientific, edwards_lifesciences, stryker, "
        "siemens_healthineers, zimmer_biomet) and carry stratum='extension'. They are a "
        "separate sample and must never be pooled with the core five in headline numbers.",
        "Record schema is the frozen FETCH_SPEC.md compact schema plus 'stratum'. CT.gov "
        "rows use exactly the frozen list of 25 fields=; the compact file drops nothing "
        "else from the study object.",
        "Harvest is firm-anchored (CT.gov query.spons / Europe PMC AFF:) and independent of "
        "any regulatory record; no milestone-dependent filter was used.",
        "CT.gov date window is applied client-side to first_posted in "
        "[2010-01-01, 2025-12-31]; rows with null first_posted are retained. Upstream date "
        "strings are kept verbatim (YYYY-MM-DD or YYYY-MM); no day is invented.",
        "Europe PMC date window is server-side, FIRST_PDATE:[2012-01-01 TO 2025-12-31], "
        "exactly as frozen.",
        "CT.gov dedup is by nct_id: the first query that returned a study owns the record; "
        "additional query strings are appended to api_query joined by ' | ', and a study "
        "returned under different firms has its firm keys joined by '+' (sorted).",
        "Europe PMC dedup is by (source, id): first record wins, api_query and source_firm "
        "joined with ' | ' and '+' respectively. firm_affiliations comes from the first "
        "record and is filtered with the first owning firm's terms only; the (rare) "
        "multi-firm rows are counted in counts.by_source.epmc.per_firm_membership.",
        "firm_affiliations matching is word-token equality (case-insensitive), not a bare "
        "substring: this is what keeps 'BD' from matching French 'Bd' (boulevard) or "
        "fragments inside other words. Matching affiliation strings are kept verbatim and "
        "de-duplicated in first-seen order. An empty list means the retrieved record's "
        "affiliations did not carry a frozen firm term (counted).",
        "abstract is whitespace-collapsed (no day/HTML invention, HTML entities left as "
        "upstream) and truncated to 2000 characters; abstract_truncated marks truncation.",
        "date basis for Europe PMC follows the frozen order firstPublicationDate -> "
        "electronicPublicationDate -> firstIndexDate -> pubYear + '-01-01'; date_basis "
        "records the source used and 'none' when no date component exists.",
        "Pathological-volume rule: a query whose reported hit count exceeds 15000 is "
        "reported and NOT paged (it would otherwise emit a silently partial stratum).",
        "Politeness: User-Agent 'MedRadar-PHOENIX003/1.0 (research; contact "
        "chazy11@users.noreply.github.com)', >= 0.35 s between request starts, 3 retries "
        "with (1.0, 2.0, 4.0)s backoff; the harvest aborts loudly instead of writing a "
        "partial file.",
        "fetched_at is wall-clock time at page retrieval and is the only non-deterministic "
        "field; everything else is deterministic given identical upstream bytes. Gzip is "
        "written with mtime=0.",
        "queried records_returned is the count returned by the API for that query "
        "(pre-filter, pre-dedup); records_retained is the count of that query's ids present "
        "in the final retained file, so a record returned by several queries counts under "
        "each of them. requests counts HTTP attempts including retries; pages counts "
        "successfully processed pages.",
        "Read-back verification: the gzip files were reopened after writing; line count "
        "equals retained record count and every line parses as JSON.",
    ]
    if mode == "smoke":
        limitations.insert(
            0,
            f"SMOKE RUN: pages per query were capped with --limit-pages={limit_pages}, so "
            "these files are deliberately incomplete and are NOT the analysis artefacts.",
        )

    return {
        "generated_at": utc_now_iso(),
        "experiment": "PHOENIX-003",
        "dataset_kind": "extension_stratum_external_sources",
        "stratum": STRATUM,
        "mode": mode,
        "endpoint": f"{CT_ENDPOINT} + {EPMC_ENDPOINT}",
        "endpoints": {"ctgov": CT_ENDPOINT, "epmc": EPMC_ENDPOINT},
        "user_agent": USER_AGENT,
        "window": {
            "ctgov_client_side_first_posted": ["2010-01-01", "2025-12-31"],
            "epmc_server_side_first_pdate": EPMC_WINDOW_CLAUSE,
        },
        "firms": [
            {
                "key": firm["key"],
                "display": firm["display"],
                "stratum": STRATUM,
                "ctgov_queries": list(firm["ctgov_queries"]),
                "epmc_query": firm["epmc_query"] + EPMC_QUERY_SUFFIX,
            }
            for firm in firms
        ],
        "queries": queries,
        "counts": {
            "records_total": ct_stats["records_total"] + epmc_stats["records_total"],
            "records_retained":
                ct_stats["records_retained"] + epmc_stats["records_retained"],
            "per_field_nulls": per_field_nulls,
            "by_source": {"ctgov": ct_counts, "epmc": epmc_counts},
        },
        "files": [
            {**ct_file, "lines": ct_lines},
            {**epmc_file, "lines": epmc_lines},
        ],
        "limitations": limitations,
    }


# --------------------------------------------------------------------------------------
# summary
# --------------------------------------------------------------------------------------

def print_summary(ct_stats, epmc_stats, ct_file, epmc_file, ct_lines, epmc_lines) -> None:
    log("")
    log("=== harvest summary (extension stratum) ===")
    log(f"ctgov  retained records : {ct_stats['records_retained']} "
        f"(unique raw {ct_stats['records_total']}, "
        f"dropped out-of-window {ct_stats['records_dropped_first_posted_window']})")
    log(f"ctgov  per firm        : {ct_stats['per_firm']}")
    log(f"ctgov  per firm (membership): {ct_stats['per_firm_membership']}")
    log(f"ctgov  first_posted null: {ct_stats['records_retained_null_first_posted']}")
    log(f"ctgov  DEVICE intervention records: "
        f"{ct_stats['records_retained_with_device_intervention']}")
    log(f"ctgov  nct_id multi-query / multi-firm: "
        f"{ct_stats['distinct_nct_multi_query']} / {ct_stats['distinct_nct_multi_firm']}")
    log(f"epmc   retained records : {epmc_stats['records_retained']} "
        f"(fetched {epmc_stats['records_fetched_all_queries']})")
    log(f"epmc   per firm        : {epmc_stats['per_firm']}")
    log(f"epmc   per firm (membership): {epmc_stats['per_firm_membership']}")
    log(f"epmc   date_basis       : {epmc_stats['date_basis_counts']}")
    log(f"epmc   null publication date: {epmc_stats['records_null_publication_date']}")
    log(f"epmc   with abstract: {epmc_stats['records_with_abstract']} "
        f"(truncated {epmc_stats['records_abstract_truncated']})")
    log(f"epmc   firm_affiliations empty: "
        f"{epmc_stats['records_without_firm_affiliations']} "
        f"(non-empty {epmc_stats['records_with_firm_affiliations']})")
    log("")
    log(f"ctgov dataset : {ct_file['path']} "
        f"({ct_file['bytes']} bytes, sha256={ct_file['sha256']}, lines={ct_lines})")
    log(f"epmc  dataset : {epmc_file['path']} "
        f"({epmc_file['bytes']} bytes, sha256={epmc_file['sha256']}, lines={epmc_lines})")


# --------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------

def parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PHOENIX-003 extension-stratum external-source harvest (CT.gov + EPMC)."
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="write _smoke_* artefacts and cap pages per query (default 1)",
    )
    parser.add_argument(
        "--limit-pages",
        type=int,
        default=None,
        metavar="N",
        help="maximum pages per query (smoke/debug); default: all pages",
    )
    parser.add_argument(
        "--firms",
        default="",
        metavar="KEYS",
        help="comma-separated subset of firm keys (debug/partial smoke); default: all eight",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.limit_pages is not None and args.limit_pages < 1:
        print("--limit-pages must be >= 1", file=sys.stderr)
        return 2

    selected_keys = [key.strip() for key in args.firms.split(",") if key.strip()]
    unknown = [key for key in selected_keys if key not in FIRM_BY_KEY]
    if unknown:
        print(f"unknown firm key(s): {unknown}; valid: {list(FIRM_ORDER)}", file=sys.stderr)
        return 2
    firms = [FIRM_BY_KEY[key] for key in selected_keys] if selected_keys else list(FIRMS)

    smoke = args.smoke
    limit_pages = args.limit_pages
    if smoke and limit_pages is None:
        limit_pages = 1
    paths = output_paths(smoke)
    mode = "smoke" if smoke else "full"

    tee = _Tee(paths["log"])
    sys.stdout = tee
    try:
        log(f"PHOENIX-003 extension-stratum harvest starting: mode={mode} "
            f"limit_pages={limit_pages} firms={len(firms)}/{len(FIRMS)}")
        log(f"  ctgov endpoint  {CT_ENDPOINT}")
        log(f"  epmc  endpoint  {EPMC_ENDPOINT}")
        log(f"  ctgov dataset   {paths['ctgov']}")
        log(f"  epmc  dataset   {paths['epmc']}")
        log(f"  manifest        {paths['manifest']}")
        log(f"  fields          {len(CT_FIELD_NAMES)} requested: {CT_FIELDS}")
        log(f"  politeness      min_delay={MIN_DELAY_S}s retries={len(RETRY_BACKOFF_S)} "
            f"backoff={RETRY_BACKOFF_S} timeouts=({CT_TIMEOUT_S:.0f}s, {EPMC_TIMEOUT_S:.0f}s)")
        log("")

        limiter = RateLimiter()
        started_run = time.monotonic()

        ct_records, ct_stats, ct_query_stats = harvest_ctgov(firms, limiter, limit_pages)
        log("")
        epmc_records, epmc_stats, epmc_query_stats = harvest_epmc(firms, limiter, limit_pages)
        elapsed_run = time.monotonic() - started_run
        log("")
        log(f"harvest complete in {elapsed_run:.1f}s: "
            f"ctgov {len(ct_records)} retained, epmc {len(epmc_records)} retained")
        log("")

        ct_file = write_jsonl_gz(paths["ctgov"], ct_records)
        epmc_file = write_jsonl_gz(paths["epmc"], epmc_records)
        ct_lines = verify_jsonl_gz(paths["ctgov"], len(ct_records))
        epmc_lines = verify_jsonl_gz(paths["epmc"], len(epmc_records))
        log(f"verified read-back: {ct_lines} ctgov gzip lines == {len(ct_records)} "
            f"retained records; {epmc_lines} epmc gzip lines == {len(epmc_records)} "
            f"retained records; all lines parse as JSON")

        manifest = build_manifest(
            mode=mode,
            firms=firms,
            limit_pages=limit_pages,
            ct_stats=ct_stats,
            epmc_stats=epmc_stats,
            ct_query_stats=ct_query_stats,
            epmc_query_stats=epmc_query_stats,
            ct_file=ct_file,
            epmc_file=epmc_file,
            ct_lines=ct_lines,
            epmc_lines=epmc_lines,
        )
        manifest_file = write_json(paths["manifest"], manifest)

        print_summary(ct_stats, epmc_stats, ct_file, epmc_file, ct_lines, epmc_lines)
        log(f"manifest      : {manifest_file['path']} "
            f"({manifest_file['bytes']} bytes, sha256={manifest_file['sha256']})")
        log("")
        log("=== query detail ===")
        for entry in ct_query_stats + epmc_query_stats:
            log(f"  {entry['source']:<5} {entry['firm']:<20} "
                f"{entry['api_query']!r:<70} http={entry['http_status']} "
                f"pages={entry['pages']} returned={entry['records_returned']} "
                f"retained={entry['records_retained']} "
                f"reported_total={entry['reported_hit_count']}")
        return 0
    except HarvestError as exc:
        log("")
        log(f"ABORT: {exc}")
        log("No dataset file was written (atomic write happens only after a clean harvest).")
        return 2
    except KeyboardInterrupt:
        log("")
        log("ABORT: interrupted")
        return 130
    except Exception:  # noqa: BLE001 - loud failure is the contract
        log("")
        log("ABORT: unexpected error, traceback follows")
        log(traceback.format_exc())
        return 3
    finally:
        try:
            sys.stdout.flush()
        finally:
            sys.stdout = tee._terminal
            tee.close_log()


if __name__ == "__main__":
    sys.exit(main())
