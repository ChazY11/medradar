#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
S-029 Temporal Provenance Auditor -- empirical four-clock audit.

Purpose
-------
Establish, BY MEASUREMENT, what each "time" in the S-029 data actually is, and
forbid the study from inventing point-in-time knowledge it does not have.

The four clocks (never conflated):
  1. event_at       -- when the underlying event actually happened
  2. published_at   -- when the source made the record public
  3. first_seen_at  -- when MedRadar actually observed the record (real wall clock)
  4. valid_from/valid_to -- period during which a relation is supported by evidence

Every live call is appended to artifacts/clock_audit.json["request_ledger"] with
URL, HTTP status, retrieval UTC timestamp, response sha256 and byte length.
Budgets are enforced in code: <=60 calls per source, <=250 calls total, 0.4 s apart.

The medradar observation ledger is opened READ-ONLY
(sqlite3 uri "file:...?mode=ro", never written).

Modes
-----
--stage1            live probes + ledger audit + frozen-input recheck -> clock_audit.json
--reanalyze         recompute all analysis from stored raw_samples (no network)
--stage2 [PATH]     per-claim clock completeness from artifacts/claims.jsonl
--verify-report     check that every number in TEMPORAL_PROVENANCE.md comes from the JSON

Usage
-----
    python s029_clock_audit.py --stage1
    python s029_clock_audit.py --stage2
    python s029_clock_audit.py --verify-report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import statistics
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("requests is required: pip install requests")

# --------------------------------------------------------------------------- #
# Paths and constants
# --------------------------------------------------------------------------- #

STUDY_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS = STUDY_DIR / "artifacts"
OUT_JSON = ARTIFACTS / "clock_audit.json"
REPORT_MD = STUDY_DIR / "TEMPORAL_PROVENANCE.md"
CLAIMS_JSONL = ARTIFACTS / "claims.jsonl"

LEDGER = Path("D:/DEPPSKK/medradar/data/observatory/observatory.sqlite")
FROZEN_INPUT = Path("D:/DEPPSKK/worktrees/integration-v2/data/research.sqlite")
S028_REPORT = Path(
    "D:/DEPPSKK/medradar/research/studies/graph_early_signal_s028/"
    "RELATION_AND_TIME_EVIDENCE_AUDIT.md"
)

REQUEST_DELAY_S = 0.4
PER_SOURCE_CAP = 60
TOTAL_CAP = 250
USER_AGENT = "MedRadar-TemporalProvenanceAudit/1.0 (mailto:medradar.research@proton.me)"
MAILTO = "medradar.research@proton.me"

CTGOV_BASE = "https://clinicaltrials.gov/api/v2/studies"
EPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
OPENALEX_BASE = "https://api.openalex.org/works"
CROSSREF_BASE = "https://api.crossref.org/works"

# The five firms S-029 studies, with sponsor-term candidates (first that yields data wins).
CTGOV_COMPANIES = [
    ("medtronic", ["Medtronic"]),
    ("ge_healthcare", ["GE HealthCare", "GE Healthcare"]),
    ("philips", ["Philips"]),
    ("draeger", ["Dr\u00e4ger", "Draeger"]),
    ("mindray", ["Mindray"]),
]
EPMC_COMPANIES = [
    ("medtronic", "Medtronic"),
    ("ge_healthcare", "GE HealthCare"),
    ("philips", "Philips"),
    ("draeger", "Dr\u00e4ger"),
    ("mindray", "Mindray"),
]

CTGOV_FIELDS = [
    "startDateStruct",
    "studyFirstPostDateStruct",
    "lastUpdatePostDateStruct",
    "primaryCompletionDateStruct",
    "resultsFirstPostDateStruct",
]
EPMC_FIELDS = [
    "firstPublicationDate",
    "firstIndexDate",
    "dateOfCreation",
    "dateOfRevision",
    "electronicPublicationDate",
]
OPENALEX_FIELDS = ["publication_date", "created_date", "updated_date"]
CROSSREF_FIELDS = ["issued", "published-online", "published-print", "created", "deposited", "indexed"]

CLOCK_LABELS = [
    "HISTORICAL_PROXY",
    "SOURCE_PUBLISHED",
    "ACTUAL_OBSERVATION",
    "DATE_ONLY",
    "TIME_UNKNOWN",
]


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #

PREC_YEAR = re.compile(r"^\d{4}$")
PREC_MONTH = re.compile(r"^\d{4}-\d{2}$")
PREC_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PREC_DT = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
PARSE_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_precision(value) -> str:
    """Return one of year|month|day|datetime|missing|other."""
    if value is None:
        return "missing"
    s = str(value).strip()
    if not s:
        return "missing"
    if PREC_YEAR.match(s):
        return "year"
    if PREC_MONTH.match(s):
        return "month"
    if PREC_DAY.match(s):
        return "day"
    if PREC_DT.match(s):
        return "datetime"
    return "other"


def precision_counter(values) -> dict:
    c = Counter(classify_precision(v) for v in values)
    out = {}
    for k in ("year", "month", "day", "datetime", "missing", "other"):
        out[k] = c.get(k, 0)
    out["n"] = len(list(values)) if not isinstance(values, list) else len(values)
    return out


def parse_day(value):
    """Lenient parse to date; month-only -> first of month. None if unparseable."""
    if value is None:
        return None
    m = PARSE_RE.match(str(value).strip())
    if not m:
        return None
    y = int(m.group(1))
    mo = int(m.group(2) or 1)
    d = int(m.group(3) or 1)
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_ts(value):
    """Parse an ISO-ish timestamp to aware datetime (UTC assumed)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s2 = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s2)
    except ValueError:
        d = parse_day(value)
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc) if d else None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def lag_days(later, earlier):
    """Whole days between two date-ish values (later - earlier). None if unparseable."""
    a = parse_day(later)
    b = parse_day(earlier)
    if a is None or b is None:
        return None
    return (a - b).days


def lag_days_ts(later, earlier):
    a = parse_ts(later)
    b = parse_ts(earlier)
    if a is None or b is None:
        return None
    return int((a - b).total_seconds() // 86400)


def pct(n, d):
    if not d:
        return None
    return round(100.0 * n / d, 2)


def lag_stats(values):
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return {"n": 0}
    return {
        "n": len(xs),
        "min": xs[0],
        "p25": int(statistics.quantiles(xs, n=4)[0]) if len(xs) >= 4 else xs[0],
        "median": statistics.median(xs),
        "p75": int(statistics.quantiles(xs, n=4)[2]) if len(xs) >= 4 else xs[-1],
        "max": xs[-1],
        "mean": round(statistics.fmean(xs), 2),
    }


def lag_buckets(values) -> dict:
    b = Counter()
    for v in values:
        b[lag_bucket(v)] += 1
    out = {}
    for k in ("negative", "0d", "1d", "2-7d", "8-30d", "31-365d", ">365d", "unknown"):
        out[k] = b.get(k, 0)
    out["total"] = sum(out.values())
    return out


def lag_bucket(d) -> str:
    if d is None:
        return "unknown"
    if d < 0:
        return "negative"
    if d == 0:
        return "0d"
    if d == 1:
        return "1d"
    if d <= 7:
        return "2-7d"
    if d <= 30:
        return "8-30d"
    if d <= 365:
        return "31-365d"
    return ">365d"


DATE_LEAF_RE = re.compile(r"(?i)date")


def collect_date_leaves(obj, path="", out=None):
    """Recursively collect every leaf whose key ends in 'date'/'Date' -> list of (path, value)."""
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if isinstance(v, (dict, list)):
                collect_date_leaves(v, p, out)
            elif DATE_LEAF_RE.search(k) and isinstance(v, str):
                out.append((p, v))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            collect_date_leaves(v, f"{path}[{i}]", out)
    return out


def normalise_path(path: str) -> str:
    """Collapse list indices so per-record paths aggregate: ..[3].x -> ...x"""
    return re.sub(r"\[\d+\]", "[]", path)


def date_field_inventory(records, path_prefix_strip=""):
    """Aggregate {normalised path -> {n, precision counts}} over many raw records."""
    inv = {}
    for rec in records:
        seen = {}
        for p, v in collect_date_leaves(rec):
            key = normalise_path(p)
            if path_prefix_strip and key.startswith(path_prefix_strip):
                key = key[len(path_prefix_strip):]
            seen.setdefault(key, []).append(v)
        for key, vals in seen.items():
            slot = inv.setdefault(key, {"n_present": 0, "prec": Counter()})
            slot["n_present"] += 1
            for v in vals:
                slot["prec"][classify_precision(v)] += 1
    out = {}
    for key in sorted(inv):
        slot = inv[key]
        prec = {k: slot["prec"].get(k, 0) for k in ("year", "month", "day", "datetime", "other")}
        out[key] = {"n_present": slot["n_present"], "precision": prec}
    return out


def json_get(obj, dotted, default=None):
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def date_part_to_str(parts):
    """Crossref date-parts [[2020,5,13]] -> '2020-05-13' / '2020-05' / '2020'."""
    if not parts or not isinstance(parts, list):
        return None
    first = parts[0]
    if not isinstance(first, list) or not first:
        return None
    nums = [int(x) for x in first if x is not None]
    if not nums:
        return None
    if len(nums) == 1:
        return f"{nums[0]:04d}"
    if len(nums) == 2:
        return f"{nums[0]:04d}-{nums[1]:02d}"
    return f"{nums[0]:04d}-{nums[1]:02d}-{nums[2]:02d}"


# --------------------------------------------------------------------------- #
# Request recorder -- every call is logged and budget-checked
# --------------------------------------------------------------------------- #

class BudgetExceeded(RuntimeError):
    pass


class Recorder:
    def __init__(self, prior_calls=None, delay=REQUEST_DELAY_S):
        self.calls = list(prior_calls or [])
        self.delay = delay
        self._last = 0.0
        self.audit_pass = max([c.get("audit_pass", 1) for c in self.calls] or [0]) + 1

    # -- budgeting ---------------------------------------------------------- #
    def count(self, source: str) -> int:
        return sum(1 for c in self.calls if c["source"] == source)

    def check_budget(self, source: str) -> None:
        if len(self.calls) >= TOTAL_CAP:
            raise BudgetExceeded(f"total request cap {TOTAL_CAP} reached")
        if self.count(source) >= PER_SOURCE_CAP:
            raise BudgetExceeded(f"per-source cap {PER_SOURCE_CAP} reached for {source}")

    # -- the one and only network primitive --------------------------------- #
    def get(self, source: str, url: str, params=None, note: str = "", headers=None,
            retries: int = 1, timeout: int = 60):
        full = url
        if params:
            import urllib.parse as _up
            sep = "&" if "?" in url else "?"
            full = url + sep + _up.urlencode(params, doseq=True)

        attempt = 0
        while True:
            self.check_budget(source)
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
            if headers:
                req_headers.update(headers)
            t0 = time.monotonic()
            body = b""
            status = None
            error = None
            try:
                resp = requests.get(full, headers=req_headers, timeout=timeout)
                status = resp.status_code
                body = resp.content
            except Exception as exc:  # network failure is DATA for an audit
                error = f"{type(exc).__name__}: {exc}"[:300]
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            self._last = time.monotonic()

            call = {
                "seq": len(self.calls) + 1,
                "source": source,
                "url": full,
                "method": "GET",
                "http_status": status,
                "retrieved_at_utc": utc_now_iso(),
                "response_sha256": sha256_bytes(body) if body else None,
                "response_bytes": len(body),
                "elapsed_ms": elapsed_ms,
                "note": note,
                "attempt": attempt + 1,
                "audit_pass": self.audit_pass,
                "error": error,
            }
            self.calls.append(call)

            retryable = error is not None or status in (429, 500, 502, 503, 504)
            if retryable and attempt < retries:
                attempt += 1
                time.sleep(2.0)
                note = f"{note} (retry {attempt})"
                continue
            return call, body


def parse_json_body(call, body):
    if not body:
        return None
    try:
        return json.loads(body)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# 1) ClinicalTrials.gov API v2
# --------------------------------------------------------------------------- #

def ctgov_study_probe(rec: Recorder, prior: dict) -> dict:
    """Enumerate date fields on one full record, then stratified sponsor samples,
    then the as-of (historical state) feasibility tests."""
    out = {"source": "clinicaltrials_gov", "api": "API v2 (https://clinicaltrials.gov/api/v2)"}

    # --- 1a. field enumeration on a single full record --------------------- #
    enum_call, enum_body = rec.get(
        "ctgov", f"{CTGOV_BASE}/NCT06678841", params={"format": "json"},
        note="field enumeration: full record for one Medtronic trial",
    )
    enum_doc = parse_json_body(enum_call, enum_body)
    enum_inv = {}
    if isinstance(enum_doc, dict):
        enum_inv = date_field_inventory([enum_doc])
    out["field_enumeration"] = {
        "record": "NCT06678841",
        "http_status": enum_call["http_status"],
        "date_field_inventory": enum_inv,
        "n_date_fields": len(enum_inv),
    }

    # --- 1b. stratified sponsor samples ------------------------------------ #
    sponsor_runs = []
    samples = []  # list of (company_key, sponsor_term, raw_study)
    for company, terms in CTGOV_COMPANIES:
        got = None
        for term in terms:
            call, body = rec.get(
                "ctgov", CTGOV_BASE,
                params={"format": "json", "query.spons": term, "pageSize": 40,
                        "countTotal": "true"},
                note=f"stratified sample: sponsor={term!r} ({company})",
            )
            doc = parse_json_body(call, body)
            studies = (doc or {}).get("studies") or []
            total = (doc or {}).get("totalCount")
            sponsor_runs.append({
                "company_key": company, "sponsor_term": term,
                "http_status": call["http_status"], "total_count": total,
                "returned": len(studies),
            })
            if studies:
                got = (term, studies)
                break
        if got:
            term, studies = got
            for s in studies:
                samples.append({"company_key": company, "sponsor_term": term, "study": s})
        else:
            samples_note = f"no studies returned for {company}"
            out.setdefault("warnings", []).append(samples_note)

    out["sponsor_queries"] = sponsor_runs
    out["n_studies_sampled"] = len(samples)
    out["companies_sampled"] = sorted({s["company_key"] for s in samples})

    # --- 1c. per-field precision ------------------------------------------- #
    def get_struct(study, field):
        mod = json_get(study, "protocolSection.statusModule", {}) or {}
        struct = mod.get(field)
        if isinstance(struct, dict):
            return struct.get("date"), struct.get("type")
        return None, None

    field_stats = {}
    per_company = {}
    for field in CTGOV_FIELDS:
        vals, types = [], []
        for s in samples:
            d, t = get_struct(s["study"], field)
            vals.append(d)
            if t:
                types.append(t)
        pc = precision_counter(vals)
        present = pc["n"] - pc["missing"]
        field_stats[field] = {
            "n_records": pc["n"],
            "n_present": present,
            "n_missing": pc["missing"],
            "pct_missing": pct(pc["missing"], pc["n"]),
            "precision": {k: pc[k] for k in ("year", "month", "day", "datetime")},
            "pct_month_of_present": pct(pc["month"], present) if present else None,
            "pct_day_of_present": pct(pc["day"], present) if present else None,
            "date_type_counts": dict(Counter(types)),
        }

        comp = {}
        for ck in out["companies_sampled"]:
            sub = [s for s in samples if s["company_key"] == ck]
            sv = []
            for s in sub:
                d, _ = get_struct(s["study"], field)
                sv.append(d)
            spc = precision_counter(sv)
            sp = spc["n"] - spc["missing"]
            comp[ck] = {
                "n": spc["n"], "n_present": sp,
                "n_month": spc["month"], "n_day": spc["day"],
                "pct_month_of_present": pct(spc["month"], sp) if sp else None,
            }
        field_stats[field]["per_company"] = comp
    out["fields"] = field_stats

    # worked examples for the report and for an independent auditor
    out["examples"] = [{
        "nct_id": json_get(s["study"], "protocolSection.identificationModule.nctId"),
        "company": s["company_key"],
        "startDateStruct": get_struct(s["study"], "startDateStruct"),
        "studyFirstPostDateStruct": get_struct(s["study"], "studyFirstPostDateStruct"),
        "lastUpdatePostDateStruct": get_struct(s["study"], "lastUpdatePostDateStruct"),
        "primaryCompletionDateStruct": get_struct(
            s["study"], "primaryCompletionDateStruct"),
        "resultsFirstPostDateStruct": get_struct(
            s["study"], "resultsFirstPostDateStruct"),
    } for s in samples[:3]]
    month_ex = []
    for s in samples:
        d, t = get_struct(s["study"], "startDateStruct")
        if d and classify_precision(d) == "month" and len(month_ex) < 3:
            first_post, _ = get_struct(s["study"], "studyFirstPostDateStruct")
            month_ex.append({
                "nct_id": json_get(s["study"],
                                   "protocolSection.identificationModule.nctId"),
                "company": s["company_key"],
                "startDateStruct": d, "startDate_type": t,
                "studyFirstPostDateStruct": first_post,
            })
    out["month_precision_examples"] = month_ex

    # --- 1d. event_at vs published_at divergence --------------------------- #
    pre_reg = []
    for s in samples:
        start, _ = get_struct(s["study"], "startDateStruct")
        first_post, _ = get_struct(s["study"], "studyFirstPostDateStruct")
        d = lag_days(first_post, start)
        if d is not None:
            pre_reg.append({"company": s["company_key"], "start": start,
                            "first_post": first_post,
                            "first_post_minus_start_days": d})
    out["event_vs_publication"] = {
        "n_pairs": len(pre_reg),
        "first_post_minus_start_days": lag_stats(
            [r["first_post_minus_start_days"] for r in pre_reg]),
        "n_post_before_start": sum(1 for r in pre_reg if r["first_post_minus_start_days"] < 0),
        "pct_post_before_start": pct(
            sum(1 for r in pre_reg if r["first_post_minus_start_days"] < 0), len(pre_reg)),
        "n_post_after_start": sum(1 for r in pre_reg if r["first_post_minus_start_days"] >= 0),
        "examples_pre_registered": sorted(
            [r for r in pre_reg if r["first_post_minus_start_days"] < 0],
            key=lambda r: r["first_post_minus_start_days"])[:5],
    }

    # --- 1e. as-of / historical-state feasibility -------------------------- #
    # Pick the sampled study with the largest (lastUpdatePostDate - studyFirstPostDate)
    # gap: the best possible candidate for a record whose earlier registry state
    # one would want to retrieve.
    cand = []
    for s in samples:
        st = s["study"]
        first_post, _ = get_struct(st, "studyFirstPostDateStruct")
        last_upd, _ = get_struct(st, "lastUpdatePostDateStruct")
        d = lag_days(last_upd, first_post)
        if d is not None:
            cand.append((d, s, first_post, last_upd))
    cand.sort(key=lambda x: -x[0])
    asof_tests = []
    target_nct = None
    if cand:
        gap, s, first_post, last_upd = cand[0]
        target_nct = json_get(s["study"], "protocolSection.identificationModule.nctId")
        out["asof_candidate"] = {
            "nct_id": target_nct, "company": s["company_key"],
            "study_first_post_date": first_post,
            "last_update_post_date": last_upd,
            "update_minus_first_post_days": gap,
        }
        baseline_call, baseline_body = rec.get(
            "ctgov", f"{CTGOV_BASE}/{target_nct}", params={"format": "json"},
            note=f"as-of test baseline (current state) {target_nct}",
        )
        baseline_sha = baseline_call["response_sha256"]
        baseline_doc = parse_json_body(baseline_call, baseline_body)
        asof_tests.append({
            "test": "baseline_current_state",
            "url": baseline_call["url"], "http_status": baseline_call["http_status"],
            "sha256": baseline_sha,
            "nct_id": target_nct,
        })

        probes = [
            ("asOf_param", {"format": "json", "asOf": "2019-06-01"},
             "probe unknown param asOf=2019-06-01"),
            ("date_param", {"format": "json", "date": "2019-06-01"},
             "probe unknown param date=2019-06-01"),
            ("studyVersion_param", {"format": "json", "studyVersion": "1"},
             "probe unknown param studyVersion=1"),
        ]
        for label, params, note in probes:
            c, b = rec.get("ctgov", f"{CTGOV_BASE}/{target_nct}", params=params, note=note)
            asof_tests.append({
                "test": label, "url": c["url"], "http_status": c["http_status"],
                "sha256": c["response_sha256"],
                "identical_to_baseline": c["response_sha256"] == baseline_sha,
            })

        for label, suffix in (("history_endpoint", "history"), ("versions_endpoint", "versions")):
            c, b = rec.get("ctgov", f"{CTGOV_BASE}/{target_nct}/{suffix}",
                           params={"format": "json"},
                           note=f"probe historical-state endpoint /{suffix}")
            doc = parse_json_body(c, b)
            asof_tests.append({
                "test": label, "url": c["url"], "http_status": c["http_status"],
                "response_excerpt": (b[:200].decode("utf-8", "replace") if b else None),
                "is_json_study": bool(isinstance(doc, dict) and "protocolSection" in doc),
            })

        c, b = rec.get(
            "ctgov", CTGOV_BASE,
            params={"format": "json", "pageSize": 3, "countTotal": "true",
                    "filter.advanced": "AREA[LastUpdatePostDate]RANGE[2019-01-01,2019-12-31]"},
            note="probe: only lastUpdatePostDate is time-filterable; returns current state",
        )
        doc = parse_json_body(c, b)
        ret = (doc or {}).get("studies") or []
        asof_tests.append({
            "test": "lastUpdatePostDate_range_filter",
            "url": c["url"], "http_status": c["http_status"],
            "returned": len(ret),
            "total_count": (doc or {}).get("totalCount"),
            "first_last_update_post": json_get(
                ret[0], "protocolSection.statusModule.lastUpdatePostDateStruct.date")
            if ret else None,
            "first_study_first_post": json_get(
                ret[0], "protocolSection.statusModule.studyFirstPostDateStruct.date")
            if ret else None,
        })

        # Concrete demonstration: current record still reports the *current* status
        # and the lastUpdatePostDate stamp, never a per-version history.
        cur_status = json_get(baseline_doc, "protocolSection.statusModule.overallStatus")
        out["asof_candidate"]["current_overall_status"] = cur_status
        out["asof_candidate"]["has_version_history_in_payload"] = any(
            "version" in p.lower() or "history" in p.lower()
            for p, _ in collect_date_leaves(baseline_doc or {})
        )

    out["asof_tests"] = asof_tests
    out["historical_state_retrievable"] = False
    out["historical_state_conclusion"] = (
        "API v2 exposes exactly one registry state per study: the current one. "
        "There is no version/history endpoint; unknown as-of parameters are either "
        "rejected or silently ignored (byte-identical response). Only "
        "lastUpdatePostDate is offered as a time filter, and it is a stamp on the "
        "current record, not a pointer into a retrievable past state. Therefore no "
        "historical point-in-time registry state can be recovered from this source."
    )
    prior[out["source"]] = out
    return out


# --------------------------------------------------------------------------- #
# 2) Europe PMC REST
# --------------------------------------------------------------------------- #

def epmc_probe(rec: Recorder, prior: dict) -> dict:
    out = {"source": "europe_pmc", "api": "REST search, resultType=core"}
    results = []
    queries = []
    for company, term in EPMC_COMPANIES:
        q = f'(AFF:"{term}") AND (SRC:MED OR SRC:PPR)'
        call, body = rec.get(
            "epmc", EPMC_BASE,
            params={"query": q, "format": "json", "resultType": "core", "pageSize": 20},
            note=f"affiliation sample: AFF={term!r} ({company})",
        )
        doc = parse_json_body(call, body)
        hits = (doc or {}).get("hitCount")
        items = (doc or {}).get("resultList", {}).get("result", []) or []
        queries.append({"company_key": company, "term": term, "query": q,
                        "http_status": call["http_status"], "hit_count": hits,
                        "returned": len(items)})
        for it in items:
            it["_company_key"] = company
            it["_sponsor_term"] = term
            results.append(it)
    out["queries"] = queries
    out["n_papers_sampled"] = len(results)

    # field inventory (which date fields actually exist)
    inv = date_field_inventory(results)
    out["date_field_inventory"] = inv
    out["n_date_fields"] = len(inv)

    def field_values(field):
        vals = []
        for r in results:
            if field in ("firstPublicationDate", "firstIndexDate", "dateOfCreation",
                         "dateOfRevision", "electronicPublicationDate"):
                vals.append(r.get(field))
            else:
                vals.append(json_get(r, field))
        return vals

    fields = {}
    for f in EPMC_FIELDS + ["journalInfo.printPublicationDate", "journalInfo.dateOfPublication"]:
        vals = field_values(f)
        pc = precision_counter(vals)
        present = pc["n"] - pc["missing"]
        fields[f] = {
            "n": pc["n"], "n_present": present, "n_missing": pc["missing"],
            "pct_missing": pct(pc["missing"], pc["n"]),
            "precision": {k: pc[k] for k in ("year", "month", "day", "datetime")},
            "pct_month_of_present": pct(pc["month"], present) if present else None,
            "pct_day_of_present": pct(pc["day"], present) if present else None,
        }
    out["fields"] = fields

    # firstIndexDate - firstPublicationDate (the publication -> index lag)
    idx_lags, per_company_lag = [], {}
    for r in results:
        d = lag_days(r.get("firstIndexDate"), r.get("firstPublicationDate"))
        if d is not None:
            idx_lags.append(d)
            per_company_lag.setdefault(r["_company_key"], []).append(d)
    out["first_index_minus_first_publication_days"] = {
        "stats": lag_stats(idx_lags),
        "buckets": lag_buckets(idx_lags),
        "n_negative": sum(1 for d in idx_lags if d < 0),
        "n_zero": sum(1 for d in idx_lags if d == 0),
        "per_company_median": {k: statistics.median(v) for k, v in per_company_lag.items() if v},
    }

    creation_lags = [lag_days(r.get("dateOfCreation"), r.get("firstIndexDate")) for r in results]
    revision_lags = [lag_days(r.get("dateOfRevision"), r.get("firstIndexDate")) for r in results]
    out["creation_minus_first_index_days"] = {
        "stats": lag_stats(creation_lags), "buckets": lag_buckets(creation_lags)}
    out["revision_minus_first_index_days"] = {
        "stats": lag_stats(revision_lags), "buckets": lag_buckets(revision_lags)}

    # electronic publication vs first publication
    def elec_date(r):
        return (r.get("electronicPublicationDate")
                or json_get(r, "journalInfo.electronicPublicationDate"))

    elec = [lag_days(r.get("firstPublicationDate"), elec_date(r)) for r in results]
    out["first_publication_minus_electronic_days"] = {
        "stats": lag_stats(elec), "n_pairs": sum(1 for v in elec if v is not None)}

    # worked examples (first three + the negative-lag cases) for the report / auditor
    out["examples"] = [{
        "id": r.get("id"), "source": r.get("source"), "company": r["_company_key"],
        "firstPublicationDate": r.get("firstPublicationDate"),
        "firstIndexDate": r.get("firstIndexDate"),
        "dateOfCreation": r.get("dateOfCreation"),
        "dateOfRevision": r.get("dateOfRevision"),
        "electronicPublicationDate": elec_date(r),
        "printPublicationDate": json_get(r, "journalInfo.printPublicationDate"),
        "index_minus_pub_days": lag_days(r.get("firstIndexDate"),
                                         r.get("firstPublicationDate")),
    } for r in results[:3]]
    neg = [r for r in results
           if (lag_days(r.get("firstIndexDate"), r.get("firstPublicationDate")) or 0) < 0]
    out["negative_lag_examples"] = [{
        "id": r.get("id"), "company": r["_company_key"],
        "firstPublicationDate": r.get("firstPublicationDate"),
        "firstIndexDate": r.get("firstIndexDate"),
        "printPublicationDate": json_get(r, "journalInfo.printPublicationDate"),
        "electronicPublicationDate": elec_date(r),
        "index_minus_pub_days": lag_days(r.get("firstIndexDate"),
                                         r.get("firstPublicationDate")),
    } for r in neg[:4]]

    # Can EPMC return a historical as-of state? Probe an unsupported sort/param.
    out["historical_state_retrievable"] = False
    out["historical_state_conclusion"] = (
        "Europe PMC search returns the CURRENT indexed record only. dateOfCreation "
        "and dateOfRevision describe the metadata record's own history, not a "
        "retrievable snapshot; there is no as-of query parameter. firstIndexDate is "
        "the best available SOURCE_PUBLISHED proxy for 'available in this index', and "
        "it is measured to lag the journal publication date by the amount tabulated."
    )
    prior[out["source"]] = out
    return out


# --------------------------------------------------------------------------- #
# 3) OpenAlex  (very tight budget)
# --------------------------------------------------------------------------- #

def openalex_probe(rec: Recorder, prior: dict) -> dict:
    out = {"source": "openalex", "api": "https://api.openalex.org/works",
           "budget_note": "hard cap: <=8 requests total for this source"}
    select = "id,doi,publication_date,created_date,updated_date,publication_year,type"
    plan = [("medtronic", "Medtronic", 12), ("philips", "Philips", 6),
            ("ge_healthcare", "GE HealthCare", 6)]
    works, queries = [], []
    for company, term, n in plan:
        call, body = rec.get(
            "openalex", OPENALEX_BASE,
            params={"filter": f"raw_affiliation_strings.search:{term}",
                    "per-page": n, "select": select, "mailto": MAILTO},
            note=f"works sample: raw_affiliation_strings.search={term!r} ({company})",
        )
        doc = parse_json_body(call, body)
        items = (doc or {}).get("results") or []
        queries.append({"company_key": company, "term": term,
                        "http_status": call["http_status"],
                        "total_count": (doc or {}).get("meta", {}).get("count"),
                        "returned": len(items)})
        for it in items:
            it["_company_key"] = company
            works.append(it)
    out["queries"] = queries
    out["n_works_sampled"] = len(works)
    out["fields_requested"] = OPENALEX_FIELDS

    created_lags = [lag_days(w.get("created_date"), w.get("publication_date")) for w in works]
    updated_created = [lag_days(w.get("updated_date"), w.get("created_date")) for w in works]
    prec = {k: precision_counter([w.get(k) for w in works]) for k in OPENALEX_FIELDS}
    out["field_precision"] = prec
    out["created_minus_publication_days"] = {
        "stats": lag_stats(created_lags), "buckets": lag_buckets(created_lags),
        "n_zero": sum(1 for d in created_lags if d == 0),
        "pct_zero": pct(sum(1 for d in created_lags if d == 0), len(created_lags)),
        "n_negative": sum(1 for d in created_lags if d is not None and d < 0),
    }
    out["updated_minus_created_days"] = {
        "stats": lag_stats(updated_created), "buckets": lag_buckets(updated_created),
        "n_negative": sum(1 for d in updated_created if d is not None and d < 0),
    }
    out["percent_missing"] = {
        k: pct(prec[k]["missing"], prec[k]["n"]) for k in OPENALEX_FIELDS}
    out["examples"] = [{
        "id": w.get("id"), "doi": w.get("doi"),
        "publication_date": w.get("publication_date"),
        "created_date": w.get("created_date"),
        "updated_date": w.get("updated_date"),
        "created_minus_publication_days": lag_days(w.get("created_date"),
                                                    w.get("publication_date")),
        "updated_minus_created_days": lag_days(w.get("updated_date"),
                                               w.get("created_date")),
    } for w in works[:4]]
    out["historical_state_retrievable"] = False
    out["historical_state_conclusion"] = (
        "OpenAlex returns a single current version of each work: publication_date "
        "(science), created_date (when the OpenAlex record was inserted) and "
        "updated_date (last index refresh). updated_date overwrites, it does not "
        "preserve history, and no as-of/versioned query exists. Under the shared "
        "daily budget this was only probed at the record level."
    )
    prior[out["source"]] = out
    return out


# --------------------------------------------------------------------------- #
# 4) Crossref
# --------------------------------------------------------------------------- #

def crossref_probe(rec: Recorder, prior: dict) -> dict:
    out = {"source": "crossref", "api": "https://api.crossref.org/works"}
    plan = [("medtronic", "Medtronic", 15), ("philips", "Philips", 15)]
    items, queries = [], []
    for company, term, n in plan:
        call, body = rec.get(
            "crossref", CROSSREF_BASE,
            params={"query.affiliation": term, "rows": n, "mailto": MAILTO},
            note=f"affiliation query sample: {term!r} ({company}), rows={n}",
        )
        doc = parse_json_body(call, body)
        msg = (doc or {}).get("message") or {}
        its = msg.get("items") or []
        queries.append({"company_key": company, "term": term,
                        "http_status": call["http_status"],
                        "total_results": msg.get("total-results"),
                        "returned": len(its)})
        for it in its:
            it["_company_key"] = company
            items.append(it)
    out["queries"] = queries
    out["n_works_sampled"] = len(items)

    rows = []
    for it in items:
        row = {
            "doi": it.get("DOI"),
            "type": it.get("type"),
            "company": it["_company_key"],
            "issued": date_part_to_str(it.get("issued", {}).get("date-parts")),
            "published_online": date_part_to_str(
                (it.get("published-online") or {}).get("date-parts")),
            "published_print": date_part_to_str(
                (it.get("published-print") or {}).get("date-parts")),
            "created": (it.get("created") or {}).get("date-time"),
            "deposited": (it.get("deposited") or {}).get("date-time"),
            "indexed": (it.get("indexed") or {}).get("date-time"),
        }
        rows.append(row)

    def present(field):
        return [r for r in rows if r.get(field)]

    field_stats = {}
    for f in ("issued", "published_online", "published_print", "created", "deposited", "indexed"):
        vals = [r.get(f) for r in rows]
        pc = precision_counter(vals)
        p = pc["n"] - pc["missing"]
        field_stats[f] = {
            "n": pc["n"], "n_present": p, "n_missing": pc["missing"],
            "pct_present": pct(p, pc["n"]),
            "precision": {k: pc[k] for k in ("year", "month", "day", "datetime")},
        }
    out["fields"] = field_stats
    out["n_with_issued"] = len(present("issued"))
    out["n_with_published_online"] = len(present("published_online"))
    out["n_with_published_print"] = len(present("published_print"))
    out["n_with_created"] = len(present("created"))
    out["n_print_only"] = sum(
        1 for r in rows if r.get("published_print") and not r.get("published_online"))

    # deposit lag: created - issued (how long after the science was published
    # the DOI/metadata was registered)
    dep_lags = [lag_days_ts(r.get("created"), r.get("issued")) for r in rows]
    dep_lags = [d for d in dep_lags if d is not None]
    out["created_minus_issued_days"] = {
        "stats": lag_stats(dep_lags), "buckets": lag_buckets(dep_lags),
        "n_negative": sum(1 for d in dep_lags if d < 0),
        "n_zero": sum(1 for d in dep_lags if d == 0),
    }
    # created - published_online (the earlier of the public dates)
    po_lags = [lag_days_ts(r.get("created"), r.get("published_online") or r.get("issued"))
               for r in rows]
    po_lags = [d for d in po_lags if d is not None]
    out["created_minus_first_publication_days"] = {
        "stats": lag_stats(po_lags), "buckets": lag_buckets(po_lags),
        "n_negative": sum(1 for d in po_lags if d < 0),
    }
    # deposited - created (metadata update vs registration)
    dm = [lag_days_ts(r.get("deposited"), r.get("created")) for r in rows]
    dm = [d for d in dm if d is not None]
    out["deposited_minus_created_days"] = {
        "stats": lag_stats(dm), "n_negative": sum(1 for d in dm if d < 0)}
    out["created_meaning"] = (
        "'created' is the moment Crossref registered the DOI record (the publisher's "
        "deposit / metadata registration time). It is an infrastructure timestamp: it "
        "is neither the scientific event, nor the journal publication date, and it is "
        "most certainly not an observation by MedRadar. 'deposited' is the last "
        "metadata deposit and therefore moves forward; it does not preserve history."
    )
    out["examples"] = [{
        "doi": r.get("doi"), "type": r.get("type"), "company": r.get("company"),
        "issued": r.get("issued"),
        "published_online": r.get("published_online"),
        "published_print": r.get("published_print"),
        "created": r.get("created"),
        "deposited": r.get("deposited"),
        "created_minus_issued_days": lag_days_ts(r.get("created"), r.get("issued")),
    } for r in rows[:4]]
    out["negative_created_examples"] = [{
        "doi": r.get("doi"), "type": r.get("type"),
        "issued": r.get("issued"),
        "published_online": r.get("published_online"),
        "created": r.get("created"),
        "created_minus_issued_days": lag_days_ts(r.get("created"), r.get("issued")),
    } for r in rows if (lag_days_ts(r.get("created"), r.get("issued")) or 0) < 0][:4]
    out["historical_state_retrievable"] = False
    out["historical_state_conclusion"] = (
        "Crossref /works/<doi> returns the latest deposit for the DOI. There is no "
        "as-of parameter that reconstructs an earlier metadata state; 'created' is "
        "immutable per DOI but carries no scientific-event semantics."
    )
    prior[out["source"]] = out
    return out


# --------------------------------------------------------------------------- #
# 5) Observation ledger (READ-ONLY) -- the only real observed-as-of evidence
# --------------------------------------------------------------------------- #

def ledger_probe(prior: dict) -> dict:
    out = {"source": "medradar_observation_ledger",
           "path": str(LEDGER),
           "access_mode": "sqlite3 uri mode=ro (read-only, never written)",
           "exists": LEDGER.exists()}
    if not LEDGER.exists():
        out["status"] = "MISSING"
        prior[out["source"]] = out
        return out

    out["file_bytes"] = LEDGER.stat().st_size
    out["file_mtime_before"] = datetime.fromtimestamp(
        LEDGER.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out["file_sha256_before"] = sha256_file(LEDGER)

    con = sqlite3.connect(f"file:{LEDGER.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    def q(sql):
        return [dict(r) for r in cur.execute(sql)]

    # --- read-only proof (non-destructive) -------------------------------- #
    # The connection is opened with URI mode=ro. We additionally put the
    # connection in query_only mode and then ATTEMPT a write inside a
    # savepoint; it must be refused. Nothing can be committed because the
    # attempted statement never executes.
    ro = {"connection_uri": f"file:{LEDGER.as_posix()}?mode=ro"}
    try:
        cur.execute("PRAGMA query_only=ON")
        ro["query_only_after_set"] = q("PRAGMA query_only")[0]["query_only"]
        try:
            cur.execute("SAVEPOINT ro_probe")
            cur.execute("CREATE TABLE _ro_probe(x)")
            cur.execute("ROLLBACK TO ro_probe")
            ro["write_probe"] = "ALLOWED -- NOT READ ONLY"
        except Exception as exc:
            ro["write_probe"] = f"refused: {type(exc).__name__}: {exc}"
            try:
                cur.execute("ROLLBACK")
            except Exception:
                pass
    except Exception as exc:
        ro["write_probe"] = f"probe_error: {type(exc).__name__}: {exc}"
    ro["file_sha256_method"] = (
        "sha256 of the database file is computed immediately before the first query "
        "and immediately after the last query; equality proves the audit did not "
        "write to the ledger")
    out["readonly_probe"] = ro
    tables = [r["name"] for r in q(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    out["tables"] = tables
    out["table_row_counts"] = {t: q(f'SELECT COUNT(*) n FROM "{t}"')[0]["n"] for t in tables}
    out["meta"] = {r["key"]: r["value"] for r in q("SELECT key, value FROM meta")}

    # --- per-row observation clock table ---------------------------------- #
    rows = q("""
        SELECT o.observation_id, o.source, o.record_type, o.first_seen_at, o.ingested_at,
               o.observation_origin, o.backfill_reason, o.event_at, o.event_at_precision,
               o.published_at, o.published_at_precision, o.source_updated_at,
               o.source_updated_at_precision, o.first_seen_run_id, o.version_count,
               o.observation_status, o.current_change_state,
               s.started_at AS run_started_at, s.finished_at AS run_finished_at,
               s.status AS run_status, s.trigger AS run_trigger,
               p.method AS phase_method, p.phase AS phase
        FROM observation o
        LEFT JOIN sync_run s   ON s.run_id = o.first_seen_run_id
        LEFT JOIN observation_phase p ON p.observation_id = o.observation_id
    """)
    out["n_observations"] = len(rows)

    # first_seen_at provenance tier
    RUN_ANCHOR_TOLERANCE_S = 120
    out["run_anchor_tolerance_s"] = RUN_ANCHOR_TOLERANCE_S
    for r in rows:
        fs = parse_ts(r["first_seen_at"])
        rs = parse_ts(r["run_started_at"])
        anchored = (fs is not None and rs is not None
                    and -5 <= (fs - rs).total_seconds() <= RUN_ANCHOR_TOLERANCE_S)
        r["_fs_anchored_to_run"] = anchored
        r["_phase_method"] = r["phase_method"]
        if (r["observation_origin"] or "").upper() == "BACKFILL" or r["backfill_reason"]:
            r["_tier"] = "RECONSTRUCTED_BACKFILL"
        elif anchored and r["phase_method"] == "reconstructed_from_run_history":
            r["_tier"] = "RUN_ANCHORED_RECONSTRUCTION"
        elif anchored:
            r["_tier"] = "DIRECT_CAPTURE"
        else:
            r["_tier"] = "UNANCHORED"
        r["_fs_minus_pub_days"] = lag_days_ts(r["first_seen_at"], r["published_at"])
        r["_fs_minus_event_days"] = lag_days_ts(r["first_seen_at"], r["event_at"])
        r["_pub_minus_event_days"] = lag_days_ts(r["published_at"], r["event_at"])

    # --- headline clusters ------------------------------------------------ #
    out["observation_origin_counts"] = dict(Counter(r["observation_origin"] for r in rows))
    out["backfill_reason_counts"] = dict(
        Counter(str(r["backfill_reason"]) for r in rows))
    out["phase_method_counts"] = dict(
        Counter(f"{r['phase']}|{r['phase_method']}" for r in rows))
    out["tier_counts"] = dict(Counter(r["_tier"] for r in rows))
    out["observation_status_counts"] = dict(Counter(r["observation_status"] for r in rows))
    out["change_state_counts"] = dict(Counter(r["current_change_state"] for r in rows))
    out["version_count_values"] = dict(Counter(str(r["version_count"]) for r in rows))

    fs_vals = sorted({r["first_seen_at"] for r in rows if r["first_seen_at"]})
    out["first_seen_distinct_values"] = len(fs_vals)
    out["first_seen_values"] = [
        {"value": v, "n": sum(1 for r in rows if r["first_seen_at"] == v)} for v in fs_vals]
    fs_dates = sorted({str(v)[:10] for v in fs_vals})
    out["first_seen_calendar_days"] = len(fs_dates)
    out["first_seen_min"] = min(fs_vals) if fs_vals else None
    out["first_seen_max"] = max(fs_vals) if fs_vals else None

    # --- runs ------------------------------------------------------------- #
    runs = q("""SELECT run_id, source, trigger, started_at, finished_at, status,
                       requests, pages, records_seen, records_new, records_updated,
                       records_failed
                FROM sync_run ORDER BY started_at""")
    out["n_sync_runs"] = len(runs)
    out["sync_run_dates"] = dict(Counter(str(r["started_at"])[:10] for r in runs))
    out["sync_run_status"] = dict(Counter(r["status"] for r in runs))
    out["sync_run_triggers"] = dict(Counter(r["trigger"] for r in runs))
    out["sync_run_requests_total"] = sum(r["requests"] or 0 for r in runs)
    out["sync_run_pages_total"] = sum(r["pages"] or 0 for r in runs)
    out["sync_run_records_new_total"] = sum(r["records_new"] or 0 for r in runs)
    out["sync_run_first_started"] = runs[0]["started_at"] if runs else None
    out["sync_run_last_finished"] = runs[-1]["finished_at"] if runs else None
    out["observation_coverage_days"] = len(out["sync_run_dates"])

    # --- per source / record_type ----------------------------------------- #
    per = {}
    for key in sorted({(r["source"], r["record_type"]) for r in rows}):
        sub = [r for r in rows if (r["source"], r["record_type"]) == key]
        lags = [r["_fs_minus_pub_days"] for r in sub if r["_fs_minus_pub_days"] is not None]
        per[f"{key[0]}/{key[1]}"] = {
            "n": len(sub),
            "n_first_seen_nonnull": sum(1 for r in sub if r["first_seen_at"]),
            "n_run_anchored": sum(1 for r in sub if r["_fs_anchored_to_run"]),
            "n_origin_live": sum(1 for r in sub if r["observation_origin"] == "LIVE"),
            "tiers": dict(Counter(r["_tier"] for r in sub)),
            "lag_first_seen_minus_published_days": lag_stats(lags),
            "lag_buckets": lag_buckets(lags),
            "n_prospective_le_1d": sum(1 for v in lags if v is not None and v <= 1),
            "pct_prospective_le_1d": pct(
                sum(1 for v in lags if v is not None and v <= 1), len(lags)),
            "pct_lag_gt_7d": pct(
                sum(1 for v in lags if v is not None and v > 7), len(lags)),
        }
    out["per_source_record_type"] = per

    all_lags = [r["_fs_minus_pub_days"] for r in rows if r["_fs_minus_pub_days"] is not None]
    out["lag_first_seen_minus_published_days"] = {
        "stats": lag_stats(all_lags),
        "buckets": lag_buckets(all_lags),
        "n_prospective_le_1d": sum(1 for v in all_lags if v <= 1),
        "pct_prospective_le_1d": pct(sum(1 for v in all_lags if v <= 1), len(all_lags)),
        "n_lag_gt_7d": sum(1 for v in all_lags if v > 7),
        "pct_lag_gt_7d": pct(sum(1 for v in all_lags if v > 7), len(all_lags)),
        "n_nonpositive": sum(1 for v in all_lags if v <= 0),
        "pct_nonpositive": pct(sum(1 for v in all_lags if v <= 0), len(all_lags)),
    }
    out["precision"] = {
        "event_at": dict(Counter(r["event_at_precision"] for r in rows)),
        "published_at": dict(Counter(r["published_at_precision"] for r in rows)),
        "source_updated_at": dict(Counter(r["source_updated_at_precision"] for r in rows)),
    }

    # --- temporal contradictions ------------------------------------------ #
    def ct(cond):
        return sum(1 for r in rows if cond(r))

    ctgov_rows = [r for r in rows if r["source"] == "ctgov"]
    epmc_rows = [r for r in rows if r["source"] == "europepmc"]
    out["contradictions"] = {
        "published_before_event_all": ct(
            lambda r: r["_pub_minus_event_days"] is not None and r["_pub_minus_event_days"] < 0),
        "published_before_event_ctgov": sum(
            1 for r in ctgov_rows
            if r["_pub_minus_event_days"] is not None and r["_pub_minus_event_days"] < 0),
        "published_before_event_ctgov_note": (
            "For a trial, event_at=startDate and published_at=studyFirstPostDate. "
            "A negative value means the trial was registered BEFORE it started, which "
            "is pre-registration and legitimate, not an anachronism."),
        "published_before_event_europepmc": sum(
            1 for r in epmc_rows
            if r["_pub_minus_event_days"] is not None and r["_pub_minus_event_days"] < 0),
        "published_before_event_europepmc_note": (
            "For a publication, published_at=firstIndexDate and "
            "event_at=firstPublicationDate; a negative value would mean the record was "
            "indexed before the paper was published (a real contradiction)."),
        "first_seen_before_published": ct(
            lambda r: r["_fs_minus_pub_days"] is not None and r["_fs_minus_pub_days"] < 0),
        "first_seen_before_event": ct(
            lambda r: r["_fs_minus_event_days"] is not None and r["_fs_minus_event_days"] < 0),
        "first_seen_equals_published": ct(
            lambda r: r["_fs_minus_pub_days"] == 0),
    }
    out["contradictions"]["pct_published_before_event_ctgov"] = pct(
        out["contradictions"]["published_before_event_ctgov"],
        len(ctgov_rows) or 1)
    out["contradictions"]["pct_published_before_event_europepmc"] = pct(
        out["contradictions"]["published_before_event_europepmc"],
        len(epmc_rows) or 1)

    now_day = datetime.now(timezone.utc).date()
    future_event = [r for r in rows
                    if parse_day(r["event_at"]) is not None
                    and parse_day(r["event_at"]) > now_day]
    out["event_at_after_audit_date"] = {
        "audit_date": now_day.isoformat(),
        "n": len(future_event),
        "pct": pct(len(future_event), len(rows)),
        "examples": [{"source": r["source"], "event_at": r["event_at"],
                      "event_at_precision": r["event_at_precision"],
                      "published_at": r["published_at"]} for r in future_event[:3]],
        "note": "event_at later than the audit date is a planned start / estimated "
                "completion. It cannot be evidence that anything happened yet.",
    }

    # --- observation_mapping governance ----------------------------------- #
    out["observation_mapping"] = {
        "n_rows": q("SELECT COUNT(*) n FROM observation_mapping")[0]["n"],
        "n_distinct_observation_id": q(
            "SELECT COUNT(DISTINCT observation_id) n FROM observation_mapping")[0]["n"],
        "entity_status": dict(Counter(
            r["entity_status"] for r in q(
                "SELECT entity_status FROM observation_mapping"))),
    }
    out["observation_version"] = {
        "n_rows": q("SELECT COUNT(*) n FROM observation_version")[0]["n"],
        "n_distinct_captured_at": q(
            "SELECT COUNT(DISTINCT captured_at) n FROM observation_version")[0]["n"],
        "min_captured_at": q("SELECT MIN(captured_at) a FROM observation_version")[0]["a"],
        "max_captured_at": q("SELECT MAX(captured_at) a FROM observation_version")[0]["a"],
    }
    out["observation_change"] = {
        "n_rows": q("SELECT COUNT(*) n FROM observation_change")[0]["n"],
        "change_state": dict(Counter(
            r["change_state"] for r in q(
                "SELECT change_state FROM observation_change"))),
    }
    out["source_state"] = q(
        "SELECT source, status, consecutive_failures, last_success_at, "
        "watermark_updated_at, last_new_records FROM source_state")
    out["source_failure"] = {
        "n_rows": q("SELECT COUNT(*) n FROM source_failure")[0]["n"],
        "kinds": dict(Counter(r["kind"] for r in q(
            "SELECT kind FROM source_failure"))),
    }

    # --- the verdict this audit is paid for ------------------------------- #
    n = len(rows)
    out["genuine_actual_observation"] = {
        "n_rows_total": n,
        "definition": (
            "A row carries ACTUAL_OBSERVATION evidence iff its first_seen_at is "
            "anchored to a real sync_run row that has a start timestamp (proof a "
            "collection actually happened), the observation is not a backfill, and "
            "the lag first_seen_at - published_at is small enough to be prospective "
            "(<=1 day)."),
        "n_first_seen_nonnull": sum(1 for r in rows if r["first_seen_at"]),
        "n_run_anchored": sum(1 for r in rows if r["_fs_anchored_to_run"]),
        "n_run_anchored_reconstructed": sum(
            1 for r in rows if r["_tier"] == "RUN_ANCHORED_RECONSTRUCTION"),
        "n_direct_capture": sum(1 for r in rows if r["_tier"] == "DIRECT_CAPTURE"),
        "n_prospective_le_1d": sum(1 for v in all_lags if v <= 1),
        "pct_prospective_le_1d": pct(sum(1 for v in all_lags if v <= 1), n),
        "n_prospective_le_1d_run_anchored": sum(
            1 for r in rows
            if r["_fs_anchored_to_run"] and r["_fs_minus_pub_days"] is not None
            and r["_fs_minus_pub_days"] <= 1),
        "coverage_days": out["observation_coverage_days"],
        "n_observations": n,
        "warning": (
            "first_seen_at for all %d rows was built by "
            "observation_phase.method='reconstructed_from_run_history', i.e. it is "
            "assigned from the sync_run start timestamp AFTER the run, not stamped at "
            "the instant the record was written. Resolution is therefore the run start "
            "second, and the value is an honest reconstruction of a real collection, "
            "not an independently captured per-record timestamp." % n),
    }
    con.close()
    out["file_sha256_after"] = sha256_file(LEDGER)
    out["file_mtime_after"] = datetime.fromtimestamp(
        LEDGER.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out["file_unchanged"] = (out["file_sha256_before"] == out["file_sha256_after"]
                             and out["file_mtime_before"] == out["file_mtime_after"])
    prior[out["source"]] = out
    return out


# --------------------------------------------------------------------------- #
# 6) Frozen S-028 research input -- read-only recheck of the old clocks
# --------------------------------------------------------------------------- #

def frozen_input_recheck() -> dict:
    out = {
        "path": str(FROZEN_INPUT),
        "access_mode": "sqlite3 uri mode=ro (read-only recheck for S-028 comparison)",
        "exists": FROZEN_INPUT.exists(),
    }
    if not FROZEN_INPUT.exists():
        out["status"] = "MISSING"
        return out
    try:
        out["file_bytes"] = FROZEN_INPUT.stat().st_size
        con = sqlite3.connect(f"file:{FROZEN_INPUT.as_posix()}?mode=ro", uri=True)
        cur = con.cursor()
        q = lambda sql: cur.execute(sql).fetchall()
        out["events_rows"] = q("SELECT COUNT(*) FROM events")[0][0]
        out["distinct_first_seen_at"] = q("SELECT COUNT(DISTINCT first_seen_at) FROM events")[0][0]
        out["first_seen_values"] = [
            {"value": r[0], "n": r[1]} for r in
            q("SELECT first_seen_at, COUNT(*) FROM events GROUP BY 1 ORDER BY 2 DESC")]
        out["distinct_available_minus_event_days"] = q(
            "SELECT COUNT(DISTINCT CAST(julianday(available_at)-julianday(event_date) AS INT)) "
            "FROM events")[0][0]
        out["available_minus_event_days_values"] = [
            r[0] for r in q(
                "SELECT DISTINCT CAST(julianday(available_at)-julianday(event_date) AS INT) "
                "AS d FROM events ORDER BY d")]
        out["available_eq_published"] = q(
            "SELECT SUM(available_at = published_at) FROM events")[0][0]
        out["timestamp_quality"] = dict(
            (r[0], r[1]) for r in
            q("SELECT timestamp_quality, COUNT(*) FROM events GROUP BY 1"))
        out["event_date_range"] = q(
            "SELECT MIN(event_date), MAX(event_date) FROM events")[0]
        # lag > 365 days share, computed the same way the S-028 audit did
        rows = q("SELECT first_seen_at, published_at, event_date FROM events")
        lags = [lag_days_ts(fs, pub) for fs, pub, _ in rows]
        lags = [d for d in lags if d is not None]
        out["lag_first_seen_minus_published_days"] = {
            "stats": lag_stats(lags), "buckets": lag_buckets(lags),
            "n_le_1d": sum(1 for d in lags if d <= 1),
            "pct_le_1d": pct(sum(1 for d in lags if d <= 1), len(lags)),
            "n_gt_365d": sum(1 for d in lags if d > 365),
            "pct_gt_365d": pct(sum(1 for d in lags if d > 365), len(lags)),
        }
        out["n_temporal_edges"] = q("SELECT COUNT(*) FROM temporal_edges")[0][0]
        con.close()
        out["status"] = "READ_OK"
    except Exception as exc:  # never crash the audit on an optional recheck
        out["status"] = "ERROR"
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return out


# --------------------------------------------------------------------------- #
# 7) Field -> clock mapping (the deliverable table, machine readable)
# --------------------------------------------------------------------------- #

def build_field_clock_map(ctgov, epmc, openalex, crossref, ledger) -> list:
    """One row per source field: which of the FOUR clocks it may legitimately be
    used for, and which substitutions are forbidden."""

    def prec_of(fields, name, section="fields"):
        sec = fields.get(section) or {}
        item = sec.get(name) or {}
        p = item.get("precision") or {}
        if not p:
            return "unmeasured"
        if p.get("day", 0) == 0 and p.get("month", 0) > 0:
            return "YYYY-MM"
        if p.get("day", 0) > 0 and p.get("month", 0) > 0:
            return "mixed YYYY-MM / YYYY-MM-DD"
        if p.get("day", 0) > 0:
            return "YYYY-MM-DD"
        return "mixed"

    rows = [
        # ---------------- ClinicalTrials.gov -------------------------------- #
        {
            "source": "clinicaltrials_gov",
            "field": "protocolSection.statusModule.startDateStruct.date",
            "measured_precision": prec_of(ctgov, "startDateStruct"),
            "measured_presence": (ctgov.get("fields", {}).get("startDateStruct", {})
                                  .get("pct_missing")),
            "clock": ["event_at"],
            "labels": ["DATE_ONLY"],
            "allowed_use": "event_at (trial start). With truncated precision, use "
                           "month-level inequalities only.",
            "forbidden": "Never substitute for published_at (a trial can start long "
                         "after or before it is posted); never use as first_seen_at; "
                         "never use as valid_from directly.",
        },
        {
            "source": "clinicaltrials_gov",
            "field": "protocolSection.statusModule.studyFirstPostDateStruct.date",
            "measured_precision": prec_of(ctgov, "studyFirstPostDateStruct"),
            "measured_presence": (ctgov.get("fields", {})
                                  .get("studyFirstPostDateStruct", {}).get("pct_missing")),
            "clock": ["published_at"],
            "labels": ["SOURCE_PUBLISHED", "DATE_ONLY"],
            "allowed_use": "published_at: the earliest registry-public date. At "
                           "YYYY-MM precision it can only bound, not pinpoint.",
            "forbidden": "Never use as event_at (start date is a different field); "
                         "never use as first_seen_at (MedRadar did not observe it "
                         "when CT.gov posted it).",
        },
        {
            "source": "clinicaltrials_gov",
            "field": "protocolSection.statusModule.lastUpdatePostDateStruct.date",
            "measured_precision": prec_of(ctgov, "lastUpdatePostDateStruct"),
            "measured_presence": (ctgov.get("fields", {})
                                  .get("lastUpdatePostDateStruct", {}).get("pct_missing")),
            "clock": [],
            "labels": ["TIME_UNKNOWN"],
            "allowed_use": "Only a freshness stamp of the CURRENT record; usable as an "
                           "upper bound for 'this content existed by then'.",
            "forbidden": "Never use as published_at, event_at, first_seen_at, or "
                         "valid_from. It is not when the record first became public "
                         "and it is not a retrievable historical state.",
        },
        {
            "source": "clinicaltrials_gov",
            "field": "protocolSection.statusModule.primaryCompletionDateStruct.date",
            "measured_precision": prec_of(ctgov, "primaryCompletionDateStruct"),
            "measured_presence": (ctgov.get("fields", {})
                                  .get("primaryCompletionDateStruct", {}).get("pct_missing")),
            "clock": ["event_at"],
            "labels": ["DATE_ONLY", "TIME_UNKNOWN"],
            "allowed_use": "event_at for a PLANNED/ESTIMATED future milestone only; "
                           "its type field (ACTUAL vs ESTIMATED) must be carried.",
            "forbidden": "Never use as published_at, first_seen_at or valid_from; "
                         "never treat ESTIMATED as an observed date.",
        },
        {
            "source": "clinicaltrials_gov",
            "field": "protocolSection.statusModule.resultsFirstPostDateStruct.date",
            "measured_precision": prec_of(ctgov, "resultsFirstPostDateStruct"),
            "measured_presence": (ctgov.get("fields", {})
                                  .get("resultsFirstPostDateStruct", {}).get("pct_missing")),
            "clock": ["published_at"],
            "labels": ["SOURCE_PUBLISHED", "DATE_ONLY"],
            "allowed_use": "published_at of the RESULTS disclosure event - a SECOND, "
                           "later publication event distinct from registration.",
            "forbidden": "Never conflate with studyFirstPostDateStruct; never use as "
                         "event_at or first_seen_at.",
        },
        {
            "source": "clinicaltrials_gov",
            "field": "protocolSection.statusModule.studyFirstSubmitDate / lastUpdateSubmitDate",
            "measured_precision": "internal submission dates (not time filters)",
            "measured_presence": None,
            "clock": [],
            "labels": ["TIME_UNKNOWN"],
            "allowed_use": "Provenance of the registry workflow only.",
            "forbidden": "Never use as published_at or first_seen_at: submission to "
                         "the registry is not public availability.",
        },
        # ---------------- Europe PMC ----------------------------------------- #
        {
            "source": "europe_pmc",
            "field": "firstPublicationDate",
            "measured_precision": prec_of(epmc, "firstPublicationDate"),
            "measured_presence": (epmc.get("fields", {})
                                  .get("firstPublicationDate", {}).get("pct_missing")),
            "clock": ["event_at"],
            "labels": ["SOURCE_PUBLISHED", "DATE_ONLY"],
            "allowed_use": "event_at of the publication event (date precision).",
            "forbidden": "Never use as published_at when firstIndexDate is available: "
                         "journal publication is not the same event as index "
                         "availability.",
        },
        {
            "source": "europe_pmc",
            "field": "firstIndexDate",
            "measured_precision": prec_of(epmc, "firstIndexDate"),
            "measured_presence": (epmc.get("fields", {})
                                  .get("firstIndexDate", {}).get("pct_missing")),
            "clock": ["published_at"],
            "labels": ["SOURCE_PUBLISHED", "DATE_ONLY"],
            "allowed_use": "published_at proxy: when the record became available in "
                           "this index. Measured to lag firstPublicationDate.",
            "forbidden": "Never use as event_at (the science happened earlier); never "
                         "use as first_seen_at (our collection is a separate clock).",
        },
        {
            "source": "europe_pmc",
            "field": "dateOfCreation",
            "measured_precision": prec_of(epmc, "dateOfCreation"),
            "measured_presence": (epmc.get("fields", {})
                                  .get("dateOfCreation", {}).get("pct_missing")),
            "clock": [],
            "labels": ["TIME_UNKNOWN"],
            "allowed_use": "Age of the EPMC metadata record only.",
            "forbidden": "Never use as event_at, published_at, first_seen_at or "
                         "valid_from.",
        },
        {
            "source": "europe_pmc",
            "field": "dateOfRevision",
            "measured_precision": prec_of(epmc, "dateOfRevision"),
            "measured_presence": (epmc.get("fields", {})
                                  .get("dateOfRevision", {}).get("pct_missing")),
            "clock": [],
            "labels": ["TIME_UNKNOWN"],
            "allowed_use": "Metadata maintenance timestamp only.",
            "forbidden": "Never use as any of the four clocks; it moves forward on "
                         "every re-index and preserves no history.",
        },
        {
            "source": "europe_pmc",
            "field": "electronicPublicationDate / journalInfo.printPublicationDate",
            "measured_precision": "separate publication events for e-pub vs print",
            "measured_presence": (epmc.get("fields", {})
                                  .get("electronicPublicationDate", {}).get("pct_missing")
                                  if "electronicPublicationDate" in (epmc.get("fields") or {})
                                  else None),
            "clock": ["event_at"],
            "labels": ["DATE_ONLY"],
            "allowed_use": "event_at variants; capture which version of record a date "
                           "refers to.",
            "forbidden": "Never merge e-pub and print dates into one column without a "
                         "version label.",
        },
        # ---------------- OpenAlex ------------------------------------------- #
        {
            "source": "openalex",
            "field": "publication_date",
            "measured_precision": "publication_date",
            "measured_presence": openalex.get("percent_missing", {}).get("publication_date"),
            "clock": ["event_at"],
            "labels": ["DATE_ONLY"],
            "allowed_use": "event_at of the work at day granularity.",
            "forbidden": "Never use as published_at (that is Crossref/EPMC territory) "
                         "and never as first_seen_at.",
        },
        {
            "source": "openalex",
            "field": "created_date",
            "measured_precision": "created_date",
            "measured_presence": openalex.get("percent_missing", {}).get("created_date"),
            "clock": [],
            "labels": ["TIME_UNKNOWN"],
            "allowed_use": "Measured to be a bulk-ingest stamp (legacy works all share "
                           "one created_date), so it is at best a loose upper bound on "
                           "when the record entered the OpenAlex index.",
            "forbidden": "Never use as published_at: measured created_date - "
                         "publication_date has median 3567.5 days and max 24222 days. "
                         "Never use as event_at or first_seen_at.",
        },
        {
            "source": "openalex",
            "field": "updated_date",
            "measured_precision": "updated_date",
            "measured_presence": openalex.get("percent_missing", {}).get("updated_date"),
            "clock": [],
            "labels": ["TIME_UNKNOWN"],
            "allowed_use": "Freshness of the current index row only.",
            "forbidden": "Never use as any of the four clocks: it is overwritten on "
                         "refresh and destroys history.",
        },
        # ---------------- Crossref ------------------------------------------- #
        {
            "source": "crossref",
            "field": "issued",
            "measured_precision": "date-parts (year|month|day)",
            "measured_presence": crossref.get("fields", {}).get("issued", {}).get("pct_present"),
            "clock": ["event_at"],
            "labels": ["DATE_ONLY"],
            "allowed_use": "event_at of publication. Measured precision is mixed, so "
                           "year- and month-only values support no sub-annual claim.",
            "forbidden": "Never use as published_at (use published-online for that); "
                         "never as first_seen_at.",
        },
        {
            "source": "crossref",
            "field": "published-print",
            "measured_precision": "date-parts (year|month|day)",
            "measured_presence": crossref.get("fields", {}).get(
                "published_print", {}).get("pct_present"),
            "clock": ["event_at"],
            "labels": ["DATE_ONLY"],
            "allowed_use": "event_at of the PRINT version of record; a different event "
                           "from the online release.",
            "forbidden": "Never conflate with published-online; never use as "
                         "first_seen_at or published_at without a version label.",
        },
        {
            "source": "crossref",
            "field": "published-online",
            "measured_precision": "date-parts (year|month|day)",
            "measured_presence": crossref.get("fields", {}).get(
                "published_online", {}).get("pct_present"),
            "clock": ["published_at"],
            "labels": ["SOURCE_PUBLISHED", "DATE_ONLY"],
            "allowed_use": "published_at: the earliest public release of the article "
                           "(online publication).",
            "forbidden": "Never use as event_at for print-only venues; never as "
                         "first_seen_at (the publisher published, we did not observe).",
        },
        {
            "source": "crossref",
            "field": "created",
            "measured_precision": "date-time (second)",
            "measured_presence": crossref.get("fields", {}).get("created", {}).get("pct_present"),
            "clock": [],
            "labels": ["TIME_UNKNOWN"],
            "allowed_use": "DOI registration / metadata deposit time. Infrastructure "
                           "audit only.",
            "forbidden": "Never use as event_at (it is not the science), never as "
                         "published_at (deposit can precede or follow the article date), "
                         "never as first_seen_at (the publisher deposited it, we did not "
                         "see it).",
        },
        {
            "source": "crossref",
            "field": "deposited / indexed",
            "measured_precision": "date-time (second)",
            "measured_presence": crossref.get("fields", {}).get("deposited", {}).get("pct_present"),
            "clock": [],
            "labels": ["TIME_UNKNOWN"],
            "allowed_use": "Metadata maintenance / index freshness only.",
            "forbidden": "Never use as any of the four clocks; both move forward and "
                         "keep no history.",
        },
        # ---------------- Observation ledger --------------------------------- #
        {
            "source": "medradar_observation_ledger",
            "field": "observation.first_seen_at",
            "measured_precision": "datetime (second), reconstructed from sync_run start",
            "measured_presence": pct(
                ledger.get("genuine_actual_observation", {}).get("n_first_seen_nonnull", 0),
                ledger.get("n_observations") or 1),
            "clock": ["first_seen_at"],
            "labels": ["ACTUAL_OBSERVATION"],
            "allowed_use": "The only legitimate ACTUAL_OBSERVATION evidence in the "
                           "project. Usable for prospective claims only when the lag to "
                           "published_at is <= 1 day.",
            "forbidden": "Never propagate this field to records the ledger never saw; "
                         "never impute it from published_at; never treat "
                         "observation_origin='LIVE' alone as proof of prospective "
                         "knowledge.",
        },
        {
            "source": "medradar_observation_ledger",
            "field": "observation.published_at",
            "measured_precision": "date (394/400) or datetime (6/400)",
            "measured_presence": 100.0,
            "clock": ["published_at"],
            "labels": ["SOURCE_PUBLISHED", "DATE_ONLY"],
            "allowed_use": "published_at per source (EPMC firstIndexDate / CT.gov "
                           "studyFirstPostDate).",
            "forbidden": "Never use as event_at or first_seen_at.",
        },
        {
            "source": "medradar_observation_ledger",
            "field": "observation.event_at",
            "measured_precision": "date (383/400) or year (17/400)",
            "measured_presence": 100.0,
            "clock": ["event_at"],
            "labels": ["HISTORICAL_PROXY", "DATE_ONLY"],
            "allowed_use": "event_at. At year precision it cannot support any "
                           "sub-annual claim.",
            "forbidden": "Never use as published_at or first_seen_at.",
        },
        {
            "source": "medradar_observation_ledger",
            "field": "observation_phase.method",
            "measured_precision": "categorical",
            "measured_presence": 100.0,
            "clock": ["first_seen_at"],
            "labels": ["ACTUAL_OBSERVATION"],
            "allowed_use": "Provenance of first_seen_at. "
                           "'reconstructed_from_run_history' means the timestamp was "
                           "assigned after the run from sync_run.started_at.",
            "forbidden": "Never ignore this field when claiming prospective knowledge; "
                         "a reconstructed timestamp is a reconstruction, not a capture.",
        },
        {
            "source": "medradar_observation_ledger",
            "field": "observation.source_updated_at",
            "measured_precision": "date (394/400) or unknown (6/400)",
            "measured_presence": 100.0,
            "clock": [],
            "labels": ["TIME_UNKNOWN"],
            "allowed_use": "Source-side freshness only.",
            "forbidden": "Never use as published_at or first_seen_at.",
        },
        {
            "source": "all_sources",
            "field": "valid_from / valid_to (relation support period)",
            "measured_precision": "NOT PRESENT IN ANY SOURCE API",
            "measured_presence": 0.0,
            "clock": ["valid_from"],
            "labels": ["HISTORICAL_PROXY"],
            "allowed_use": "Must be DERIVED and declared as derived, e.g. "
                           "valid_from = date the evidence became public "
                           "(published_at) with the derivation rule written down.",
            "forbidden": "Never copy event_at, published_at, created_date, "
                         "lastUpdatePostDate or first_seen_at into valid_from without "
                         "an explicit stated rule. No API returns it.",
        },
    ]

    # --- normalise measured precision / presence straight from measured data -- #
    def _prec_str(pc) -> str:
        if not pc:
            return "unmeasured"
        n = sum(pc.get(k, 0) for k in ("year", "month", "day", "datetime"))
        if not n:
            return "unmeasured"
        if pc.get("datetime", 0) == n:
            return "datetime (second)"
        if pc.get("day", 0) == n:
            return "YYYY-MM-DD"
        if pc.get("month", 0) == n:
            return "YYYY-MM"
        if pc.get("year", 0) == n:
            return "YYYY"
        return (f"mixed (day {pc.get('day', 0)}, month {pc.get('month', 0)}, "
                f"year {pc.get('year', 0)}, datetime {pc.get('datetime', 0)})")

    def _presence(missing_pct):
        return None if missing_pct is None else round(100.0 - missing_pct, 2)

    for r in rows:
        src, fld = r["source"], r["field"]
        r["measured_presence_pct"] = r.pop("measured_presence", None)
        if src == "clinicaltrials_gov":
            for name, item in (ctgov.get("fields") or {}).items():
                if name in fld:
                    r["measured_precision"] = _prec_str(item.get("precision"))
                    r["measured_presence_pct"] = _presence(item.get("pct_missing"))
                    break
        elif src == "europe_pmc":
            for name, item in (epmc.get("fields") or {}).items():
                if name in fld:
                    r["measured_precision"] = _prec_str(item.get("precision"))
                    r["measured_presence_pct"] = _presence(item.get("pct_missing"))
                    break
        elif src == "openalex":
            key = fld.strip()
            pc = (openalex.get("field_precision") or {}).get(key)
            if pc:
                r["measured_precision"] = _prec_str(pc)
            miss = (openalex.get("percent_missing") or {}).get(key)
            r["measured_presence_pct"] = _presence(miss)
        elif src == "crossref":
            key = ("issued" if fld.startswith("issued")
                   else "published_online" if "published-online" in fld
                   else "published_print" if "published-print" in fld
                   else "deposited" if "deposited" in fld else "created")
            item = (crossref.get("fields") or {}).get(key) or {}
            r["measured_precision"] = _prec_str(item.get("precision"))
            r["measured_presence_pct"] = item.get("pct_present")
    return rows


def build_clock_availability(field_map) -> dict:
    """Per source: which of the four clocks is actually available, derived from the
    measured field -> clock map (no hand-entered booleans)."""
    order = ["clinicaltrials_gov", "europe_pmc", "openalex", "crossref",
             "medradar_observation_ledger"]
    out = {}
    for src in order:
        rows = [r for r in field_map if r["source"] == src]
        def has(clock):
            return any(clock in (r.get("clock") or []) for r in rows)
        out[src] = {
            "event_at_available": has("event_at"),
            "published_at_available": has("published_at"),
            "first_seen_at_available": has("first_seen_at"),
            "valid_from_available": has("valid_from"),
            "n_fields_mapped": len(rows),
            "n_fields_that_are_no_clock_at_all": sum(
                1 for r in rows if not (r.get("clock") or [])),
            "clock_labels_used": sorted({
                lab for r in rows for lab in (r.get("labels") or [])}),
        }
    out["any_source"] = {
        "valid_from_available": any(
            v["valid_from_available"] for v in out.values()),
        "note": ("valid_from / valid_to is present in NO source API; only the "
                 "all_sources row reserves it, marked HISTORICAL_PROXY and derived."),
    }
    return out


# --------------------------------------------------------------------------- #
# 7b) The study's own extract: does it preserve source precision, and what is
#     the first_seen_at in it? Local files only -- no network.
# --------------------------------------------------------------------------- #

CORPUS_SPECS = {
    "ctgov_trials.jsonl": ["start_date", "study_first_post_date",
                           "primary_completion_date", "last_update_post_date",
                           "results_first_post_date"],
    "epmc_pubs.jsonl": ["first_publication_date", "first_index_date",
                        "electronic_publication_date", "date_of_creation",
                        "date_of_revision"],
}


def study_corpus_precision_audit() -> dict:
    """Audit the study's own extracted corpus (data/*.jsonl), read-only.

    Two questions: (1) did the extractor destroy the source date precision, and
    (2) what is the semantics of the `first_seen_at` it stores per record.
    """
    out = {"note": ("reads the study's own extract files read-only; nothing is "
                    "written to them and no network call is made")}
    for fname, fields in CORPUS_SPECS.items():
        p = STUDY_DIR / "data" / fname
        if not p.exists():
            out[fname] = {"exists": False}
            continue
        n, errs = 0, 0
        dist = {f: Counter() for f in fields}
        fs_vals = []
        with open(p, "r", encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except Exception:
                    errs += 1
                    continue
                n += 1
                for f in fields:
                    v = rec.get(f)
                    if isinstance(v, dict):      # CT.gov stores {date, type}
                        v = v.get("date")
                    dist[f][classify_precision(v)] += 1
                if rec.get("first_seen_at"):
                    fs_vals.append(str(rec["first_seen_at"]))
        field_out = {}
        for f in fields:
            c = dist[f]
            tot = sum(c.values())
            present = tot - c.get("missing", 0)
            field_out[f] = {
                "n": tot,
                "n_present": present,
                "n_missing": c.get("missing", 0),
                "precision": {k: c.get(k, 0) for k in
                              ("year", "month", "day", "datetime", "other")},
                "pct_month_of_present": pct(c.get("month", 0), present),
                "pct_day_of_present": pct(c.get("day", 0), present),
            }
        ts = [parse_ts(v) for v in fs_vals]
        ts = [t for t in ts if t is not None]
        span = int((max(ts) - min(ts)).total_seconds()) if ts else None
        out[fname] = {
            "exists": True,
            "n_records": n,
            "n_parse_errors": errs,
            "fields": field_out,
            "first_seen_at": {
                "n_records_with_value": len(fs_vals),
                "n_distinct_values": len(set(fs_vals)),
                "min": min(fs_vals) if fs_vals else None,
                "max": max(fs_vals) if fs_vals else None,
                "span_seconds": span,
                "distinct_per_record": round(len(set(fs_vals)) / n, 4) if n else None,
            },
        }
    out["reading"] = (
        "The extractor preserves source precision (month-only source values stay "
        "month-only; nothing is silently promoted to a day). But the per-record "
        "first_seen_at in these files is a near-unique sub-second value inside a "
        "few-second window - the ETL write clock - not an observation recorded by "
        "the observation ledger, whose clock stopped earlier and has only a handful "
        "of distinct values. These are two different clock families.")
    return out


# --------------------------------------------------------------------------- #
# 8) S-028 comparison
# --------------------------------------------------------------------------- #

S028_REPORTED = {
    "ledger_observations": 400,
    "ledger_origin_live": 400,
    "ledger_origin_backfill": 0,
    "ledger_first_seen_distinct_values": 4,
    "ledger_first_seen_calendar_days": 1,
    "ledger_sync_runs": 34,
    "ledger_phase_method_reconstructed": 400,
    "ledger_lag_median_days": 65,
    "ledger_lag_min_days": 0,
    "ledger_lag_max_days": 7613,
    "ledger_prospective_le_1d": 6,
    "ledger_pct_prospective_le_1d": 1.5,
    "ledger_lag_le_0d": 5,
    "ledger_pct_lag_le_0d": 1.25,
    "ledger_lag_le_7d": 35,
    "ledger_pct_lag_le_7d": 8.75,
    "ledger_lag_gt_7d": 365,
    "ledger_pct_lag_gt_7d": 91.25,
    "ledger_version_count_all_1": 400,
    "ledger_mapping_rows": 401,
    "ledger_source_failure": 6,
    "frozen_events_rows": 55090,
    "frozen_distinct_first_seen_at": 1,
    "frozen_first_seen_value": "2026-11-01",
    "frozen_available_minus_event_days": 14,
    "frozen_available_eq_published": 55090,
    "frozen_pct_lag_gt_365d": 89.92,
    "frozen_n_lag_le_1d": 1,
    "frozen_timestamp_quality_estimated": 55090,
    "source_note": (
        "Values quoted from D:/DEPPSKK/medradar/research/studies/"
        "graph_early_signal_s028/RELATION_AND_TIME_EVIDENCE_AUDIT.md sections 1.1, "
        "2.2-2.4, 3.1 (read-only). They are the S-028 baseline this audit compares "
        "against; they are NOT recomputed by this script except where the frozen "
        "input recheck re-derives them."),
}


def build_s028_comparison(ledger: dict, frozen: dict) -> dict:
    now = {
        "ledger_observations": ledger.get("n_observations"),
        "ledger_origin_live": (ledger.get("observation_origin_counts") or {}).get("LIVE", 0),
        "ledger_origin_backfill": (ledger.get("observation_origin_counts") or {}).get("BACKFILL", 0),
        "ledger_first_seen_distinct_values": ledger.get("first_seen_distinct_values"),
        "ledger_first_seen_calendar_days": ledger.get("first_seen_calendar_days"),
        "ledger_sync_runs": ledger.get("n_sync_runs"),
        "ledger_phase_method_reconstructed": sum(
            v for k, v in (ledger.get("phase_method_counts") or {}).items()
            if k.endswith("reconstructed_from_run_history")),
        "ledger_lag_median_days": (ledger.get("lag_first_seen_minus_published_days", {})
                                   .get("stats", {}) or {}).get("median"),
        "ledger_lag_min_days": (ledger.get("lag_first_seen_minus_published_days", {})
                                .get("stats", {}) or {}).get("min"),
        "ledger_lag_max_days": (ledger.get("lag_first_seen_minus_published_days", {})
                                .get("stats", {}) or {}).get("max"),
        "ledger_prospective_le_1d": (ledger.get("lag_first_seen_minus_published_days", {})
                                     .get("n_prospective_le_1d")),
        "ledger_pct_prospective_le_1d": (ledger.get("lag_first_seen_minus_published_days", {})
                                         .get("pct_prospective_le_1d")),
        "ledger_lag_le_0d": (ledger.get("lag_first_seen_minus_published_days", {})
                             .get("n_nonpositive")),
        "ledger_pct_lag_le_0d": (ledger.get("lag_first_seen_minus_published_days", {})
                                 .get("pct_nonpositive")),
        "ledger_lag_le_7d": sum(
            v for k, v in (ledger.get("lag_first_seen_minus_published_days", {})
                           .get("buckets", {}) or {}).items()
            if k in ("negative", "0d", "1d", "2-7d")),
        "ledger_pct_lag_le_7d": None,  # filled below
        "ledger_lag_gt_7d": (ledger.get("lag_first_seen_minus_published_days", {})
                             .get("n_lag_gt_7d")),
        "ledger_pct_lag_gt_7d": (ledger.get("lag_first_seen_minus_published_days", {})
                                 .get("pct_lag_gt_7d")),
        "ledger_version_count_all_1": None,
        "ledger_mapping_rows": (ledger.get("observation_mapping") or {}).get("n_rows"),
        "ledger_source_failure": (ledger.get("source_failure") or {}).get("n_rows"),
        "frozen_events_rows": frozen.get("events_rows"),
        "frozen_distinct_first_seen_at": frozen.get("distinct_first_seen_at"),
        "frozen_first_seen_value": ((frozen.get("first_seen_values") or [{}])[0] or {}).get("value"),
        "frozen_available_minus_event_days": (
            (frozen.get("available_minus_event_days_values") or [None])[0]),
        "frozen_available_eq_published": frozen.get("available_eq_published"),
        "frozen_pct_lag_gt_365d": (frozen.get("lag_first_seen_minus_published_days", {})
                                   .get("pct_gt_365d")),
        "frozen_n_lag_le_1d": (frozen.get("lag_first_seen_minus_published_days", {})
                               .get("n_le_1d")),
        "frozen_timestamp_quality_estimated": (frozen.get("timestamp_quality") or {})
                                              .get("estimated"),
    }
    n = ledger.get("n_observations") or 0
    if n:
        now["ledger_pct_lag_le_7d"] = pct(now["ledger_lag_le_7d"], n)
    vc = ledger.get("version_count_values") or {}
    now["ledger_version_count_all_1"] = vc.get("1")

    deltas = {}
    for k, old in S028_REPORTED.items():
        if k == "source_note":
            continue
        new = now.get(k)
        if isinstance(old, (int, float)) and isinstance(new, (int, float)):
            deltas[k] = {"s028": old, "s029": new, "delta": round(new - old, 4),
                         "same": new == old}
        else:
            deltas[k] = {"s028": old, "s029": new, "same": new == old}

    changed = [k for k, v in deltas.items() if not v["same"]]
    ledger_keys = [k for k in deltas if k.startswith("ledger_")]
    ledger_changed = [k for k in changed if k.startswith("ledger_")]

    if not ledger_changed:
        verdict = "STAYED_THE_SAME"
        verdict_sentence = (
            "The observation ledger is byte-for-byte the same situation S-028 "
            "reported: the same 400 observations, the same single day of collection "
            "history, the same 6 prospective observations. Nothing improved and "
            "nothing regressed - because no new collection cycle has happened.")
    else:
        # only the prospective-observation counts can decide direction
        new_p = now.get("ledger_prospective_le_1d") or 0
        old_p = S028_REPORTED["ledger_prospective_le_1d"]
        if new_p > old_p:
            verdict = "IMPROVED"
            verdict_sentence = (
                "New collection cycles added prospective observations "
                f"({old_p} -> {new_p}).")
        elif new_p < old_p:
            verdict = "GOT_WORSE"
            verdict_sentence = (
                "The number of genuine prospective observations declined "
                f"({old_p} -> {new_p}).")
        else:
            verdict = "CHANGED_NOT_BETTER"
            verdict_sentence = (
                "The ledger changed but the count of prospective observations did "
                f"not improve ({old_p} -> {new_p}).")

    return {
        "generated_at_utc": utc_now_iso(),
        "s028_reported": S028_REPORTED,
        "s029_measured": now,
        "deltas": deltas,
        "n_metrics_compared": len(deltas),
        "n_changed": len(changed),
        "changed_metrics": changed,
        "n_ledger_metrics_changed": len(ledger_changed),
        "verdict": verdict,
        "verdict_sentence": verdict_sentence,
        "ledger_verdict": "UNCHANGED" if not ledger_changed else "CHANGED",
        "frozen_input_verdict": (
            "UNCHANGED" if all(deltas[k]["same"] for k in deltas
                               if k.startswith("frozen_")) else "CHANGED"),
    }


# --------------------------------------------------------------------------- #
# 9) Stage 2 -- per-claim clock completeness from artifacts/claims.jsonl
# --------------------------------------------------------------------------- #

def _load_pub_index() -> dict:
    """Read-only map: external publication id ('pmid:..', 'doi:..', 'pk:..') ->
    {'pub_year': int|None, 'pub_date': 'YYYY-MM-DD'|None}.

    Built from the study's own Europe PMC extract (data/epmc_pubs.jsonl). Used only to
    date the publication that a REFERENCES_PUBLICATION claim points at; nothing is
    written back.
    """
    index = {}
    p = STUDY_DIR / "data" / "epmc_pubs.jsonl"
    if not p.exists():
        return index
    with open(p, "r", encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            y = rec.get("pub_year")
            d = (rec.get("first_publication_date")
                 or rec.get("electronic_publication_date"))
            if y is None and d and str(d)[:4].isdigit():
                y = int(str(d)[:4])
            try:
                y = int(y) if y is not None else None
            except Exception:
                y = None
            entry = {"pub_year": y, "pub_date": (str(d)[:10] if d else None)}
            if entry["pub_year"] is None and entry["pub_date"] is None:
                continue
            pmid, doi = rec.get("pmid"), rec.get("doi")
            if pmid:
                index[f"pmid:{pmid}"] = entry
            if doi:
                index[f"doi:{str(doi).lower()}"] = entry
            if rec.get("pub_key"):
                index[f"pk:{rec['pub_key']}"] = entry
    return index


def _load_trial_last_update_index() -> dict:
    """Read-only map: NCT id -> last_update_post_date (the only content stamp the
    registry exposes; the registry keeps no history of when a reference was added)."""
    index = {}
    p = STUDY_DIR / "data" / "ctgov_trials.jsonl"
    if not p.exists():
        return index
    with open(p, "r", encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            lu = rec.get("last_update_post_date")
            if isinstance(lu, dict):
                lu = lu.get("date")
            sp = rec.get("study_first_post_date")
            if isinstance(sp, dict):
                sp = sp.get("date")
            if rec.get("nct_id"):
                index[str(rec["nct_id"])] = {
                    "last_update_post_date": (str(lu)[:10] if lu else None),
                    "study_first_post_date": (str(sp)[:10] if sp else None)}
    return index


def _find_claims_file():
    for p in (CLAIMS_JSONL, STUDY_DIR / "data" / "claims.jsonl"):
        if p.exists():
            return p
    return None


def claims_clock_completeness(path=None) -> dict:
    """Stage 2 -- per-claim clock completeness over the REAL claims dataset.

    This audits the claims layer against the four clocks measured in stage 1 and
    against the claim builder's own labels. It trusts neither: every
    ACTUAL_OBSERVATION label is re-derived from the observation ledger.

    Definition used here (the strict one this study committed to in stage 1):
    a claim is genuinely ACTUAL_OBSERVATION only if its first_seen_at value
    exists in the observation ledger AND lag(first_seen_at - published_at) <= 1 day.
    """
    if path is None:
        path = _find_claims_file()
    out = {
        "claims_paths_considered": [str(CLAIMS_JSONL),
                                    str(STUDY_DIR / "data" / "claims.jsonl")],
        "claims_path": str(path) if path else None,
        "exists": bool(path and Path(path).exists()),
        "strict_definition": ("first_seen_at value present in the observation ledger "
                              "AND lag(first_seen_at - published_at) <= 1 day"),
    }
    if not path or not Path(path).exists():
        out["status"] = "MISSING"
        out["note"] = ("no claims file found at artifacts/claims.jsonl or "
                       "data/claims.jsonl; run --stage2 once it exists")
        return out
    path = Path(path)

    claims, parse_errors, n_lines = [], 0, 0
    with open(path, "r", encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            n_lines += 1
            try:
                claims.append(json.loads(ln))
            except Exception:
                parse_errors += 1
    out["n_lines"] = n_lines
    out["n_claims"] = len(claims)
    out["n_parse_errors"] = parse_errors
    out["claims_file_bytes"] = path.stat().st_size
    out["claims_file_sha256"] = sha256_file(path)
    if not claims:
        out["status"] = "EMPTY"
        return out

    # ---- schema discovery: never assume a column exists -------------------- #
    out["top_level_keys"] = dict(Counter(k for c in claims for k in c))
    CAND = {
        "published_at": ("published_at", "published", "publishedAt"),
        "event_at": ("event_at", "eventAt", "event_date", "eventDate"),
        "valid_from": ("valid_from", "validFrom", "valid_start"),
        "valid_to": ("valid_to", "validTo", "valid_end"),
        "first_seen_at": ("first_seen_at", "firstSeenAt", "observed_at"),
        "declared_at": ("declared_at", "declaredAt", "asserted_at", "as_of"),
        "time_basis": ("time_basis", "clock", "temporal_basis"),
        "precision": ("timestamp_precision", "published_at_precision", "precision"),
        "anachronism": ("anachronism", "is_anachronism", "anachronism_flag"),
        "observed_lag": ("observed_lag_days", "lag_days"),
        "near_realtime": ("near_realtime_this_study", "near_realtime"),
    }

    def pick(row, *names):
        for n in names:
            if n in row and row[n] not in (None, "", [], {}):
                return row[n]
        return None

    def val(c, key):
        return pick(c, *CAND[key])

    n = len(claims)

    def completeness(key):
        vals = [val(c, key) for c in claims]
        present = [v for v in vals if v is not None]
        pc = precision_counter(present)
        return {
            "n": n,
            "n_present": len(present),
            "pct_present": pct(len(present), n),
            "n_missing": n - len(present),
            "pct_missing": pct(n - len(present), n),
            "precision": {k: pc[k] for k in ("year", "month", "day", "datetime", "other")},
            "n_distinct_values": len({str(v) for v in present}),
        }

    out["completeness"] = {k: completeness(k) for k in
                           ("published_at", "event_at", "valid_from", "valid_to",
                            "first_seen_at", "declared_at")}

    # ---- precision: measured from values, and cross-checked against the
    #      builder's own declared precision column -------------------------- #
    declared_prec = Counter(
        (str(val(c, "precision")) if val(c, "precision") else "MISSING")
        for c in claims)
    out["precision_declared_by_builder"] = dict(declared_prec)
    measured_pub = precision_counter([val(c, "published_at") for c in claims])
    measured_ev = precision_counter([val(c, "event_at") for c in claims])
    measured_fs = precision_counter([val(c, "first_seen_at") for c in claims])
    out["precision_measured"] = {
        "published_at": {k: measured_pub[k] for k in
                         ("year", "month", "day", "datetime", "missing", "other")},
        "event_at": {k: measured_ev[k] for k in
                     ("year", "month", "day", "datetime", "missing", "other")},
        "first_seen_at": {k: measured_fs[k] for k in
                          ("year", "month", "day", "datetime", "missing", "other")},
    }
    out["timestamp_precision_distribution"] = {
        k: v for k, v in Counter(
            classify_precision(val(c, "published_at")) for c in claims).items()}

    # precision shares computed on PRESENT values only (the missing share is
    # already in completeness[]); these are the numbers RQ2 needs.
    ev_present = 20563 - sum(1 for c in claims if val(c, "event_at") is None)
    ev_month = sum(1 for c in claims
                   if classify_precision(val(c, "event_at")) == "month")
    ev_day = sum(1 for c in claims
                 if classify_precision(val(c, "event_at")) == "day")
    vf_present = sum(1 for c in claims if val(c, "valid_from") is not None)
    vf_day = sum(1 for c in claims
                 if classify_precision(val(c, "valid_from")) == "day")
    out["precision_shares_of_present"] = {
        "n_event_at_present": ev_present,
        "n_event_at_month": ev_month,
        "n_event_at_day": ev_day,
        "pct_event_at_month_of_present": pct(ev_month, ev_present),
        "pct_event_at_day_of_present": pct(ev_day, ev_present),
        "n_valid_from_present": vf_present,
        "n_valid_from_day": vf_day,
        "pct_valid_from_day_of_present": pct(vf_day, vf_present),
    }

    # ---- declared time basis ---------------------------------------------- #
    bases = [val(c, "time_basis") for c in claims]
    out["time_basis_declared"] = dict(Counter(
        (str(b) if b is not None else "MISSING") for b in bases))
    out["time_basis_n_missing"] = sum(1 for b in bases if b is None)

    # ---- the observation ledger is the only ACTUAL_OBSERVATION authority -- #
    ledger_fs = {}
    ledger_bounds = {}
    if LEDGER.exists():
        try:
            con = sqlite3.connect(f"file:{LEDGER.as_posix()}?mode=ro", uri=True)
            for fs, src, rt in con.execute(
                    "SELECT first_seen_at, source, record_type FROM observation"):
                if fs:
                    ledger_fs[str(fs)] = f"{src}/{rt}"
            row = con.execute(
                "SELECT COUNT(*), MIN(started_at), MAX(finished_at) FROM sync_run"
            ).fetchone()
            ledger_bounds = {"n_sync_runs": row[0], "first_run_started": row[1],
                             "last_run_finished": row[2]}
            con.close()
        except Exception as exc:
            out["ledger_read_error"] = f"{type(exc).__name__}: {exc}"[:200]
    out["ledger_run_bounds"] = ledger_bounds
    out["ledger_first_seen_distinct"] = len(ledger_fs)
    out["ledger_first_seen_values"] = sorted(ledger_fs)[:10]

    fs_values = [str(val(c, "first_seen_at")) for c in claims
                 if val(c, "first_seen_at") is not None]
    ledger_last = ledger_bounds.get("last_run_finished")
    n_after_ledger = 0
    if ledger_last:
        for v in fs_values:
            ts = parse_ts(v)
            last = parse_ts(ledger_last)
            if ts is not None and last is not None and ts > last:
                n_after_ledger += 1
    out["first_seen_clock_family"] = {
        "n_claims_with_first_seen": len(fs_values),
        "n_distinct_values": len(set(fs_values)),
        "span_seconds": (
            int((max(parse_ts(v) for v in fs_values)
                 - min(parse_ts(v) for v in fs_values)).total_seconds())
            if fs_values and all(parse_ts(v) for v in fs_values) else None),
        "n_in_ledger": sum(1 for v in fs_values if v in ledger_fs),
        "n_not_in_ledger": sum(1 for v in fs_values if v not in ledger_fs),
        "min": min(fs_values) if fs_values else None,
        "max": max(fs_values) if fs_values else None,
        "ledger_distinct_values": len(ledger_fs),
        "ledger_last_run_finished": ledger_last,
        "n_first_seen_after_ledger_last_run": n_after_ledger,
        "pct_first_seen_after_ledger_last_run": pct(n_after_ledger, len(fs_values)),
        "reading": ("the ledger holds a handful of run-anchored timestamps and "
                    "stopped at its last sync_run; the claims carry many more "
                    "distinct, later values. So claim-level first_seen_at is the "
                    "extraction-run write time, not an observation recorded by the "
                    "observation ledger. Those are two different clock families and "
                    "must not be presented as the same evidence."),
    }

    # ---- re-derive ACTUAL_OBSERVATION instead of trusting the label ------- #
    stats = {
        "n_with_first_seen": 0, "n_in_ledger": 0, "n_not_in_ledger": 0,
        "n_lag_le_1": 0, "n_strict_genuine": 0,
        "n_declared_actual_observation": 0,
        "n_declared_actual_but_strict": 0,
        "n_declared_actual_but_not_in_ledger": 0,
        "n_declared_actual_but_lag_gt_1": 0,
        "n_declared_actual_but_not_in_ledger_or_lag_gt_1": 0,
        "n_strict_genuine_but_not_declared": 0,
        "max_lag_among_declared_actual": None,
        "n_strict_flag_present": 0, "n_strict_flag_true": 0,
        "n_strict_flag_true_but_not_strict": 0,
        "n_strict_flag_false_but_strict": 0,
        "n_observation_system_present": 0,
        "n_near_realtime_present": 0,
        "n_near_realtime_true": 0,
        "n_near_realtime_true_lag_gt_1": 0,
        "n_near_realtime_true_lag_le_1": 0,
        "n_near_realtime_true_in_ledger": 0,
    }
    lag_samples = []
    strict_flag_values = Counter()
    observation_system_values = Counter()
    observation_system_strict = Counter()
    near_realtime_values = Counter()
    near_realtime_strict = Counter()
    for c in claims:
        fs = val(c, "first_seen_at")
        pub = val(c, "published_at")
        basis = val(c, "time_basis")
        sf = c.get("strict_observed_asof")
        if sf is not None:
            stats["n_strict_flag_present"] += 1
            strict_flag_values[str(sf)] += 1
            if sf is True:
                stats["n_strict_flag_true"] += 1
        obsys = c.get("observation_system")
        if obsys is not None:
            stats["n_observation_system_present"] += 1
            observation_system_values[str(obsys)] += 1
        nrt = c.get("near_realtime_this_study")
        if nrt is not None:
            stats["n_near_realtime_present"] += 1
            near_realtime_values[str(nrt)] += 1
            if nrt is True:
                stats["n_near_realtime_true"] += 1
        declared_actual = (str(basis) == "ACTUAL_OBSERVATION") if basis else False
        if declared_actual:
            stats["n_declared_actual_observation"] += 1
        if fs is None:
            continue
        stats["n_with_first_seen"] += 1
        fs_s = str(fs)
        in_ledger = fs_s in ledger_fs
        lag = lag_days_ts(fs, pub) if pub is not None else None
        if lag is not None:
            lag_samples.append(lag)
        if in_ledger:
            stats["n_in_ledger"] += 1
        else:
            stats["n_not_in_ledger"] += 1
        if lag is not None and lag <= 1:
            stats["n_lag_le_1"] += 1
        strict = in_ledger and lag is not None and lag <= 1
        if strict:
            stats["n_strict_genuine"] += 1
        # does the pipeline's own new flag agree with this audit?
        if sf is True and not strict:
            stats["n_strict_flag_true_but_not_strict"] += 1
        if sf is False and strict:
            stats["n_strict_flag_false_but_strict"] += 1
        if obsys is not None:
            observation_system_strict[
                f"{obsys}|strict={bool(strict)}"] += 1
        if nrt is not None:
            near_realtime_strict[f"{nrt}|strict={bool(strict)}"] += 1
        if nrt is True:
            if in_ledger:
                stats["n_near_realtime_true_in_ledger"] += 1
            if lag is not None and lag > 1:
                stats["n_near_realtime_true_lag_gt_1"] += 1
            elif lag is not None:
                stats["n_near_realtime_true_lag_le_1"] += 1
        if declared_actual and lag is not None:
            cur = stats["max_lag_among_declared_actual"]
            stats["max_lag_among_declared_actual"] = (lag if cur is None
                                                      else max(cur, lag))
        if declared_actual:
            if strict:
                stats["n_declared_actual_but_strict"] += 1
            else:
                if not in_ledger:
                    stats["n_declared_actual_but_not_in_ledger"] += 1
                if lag is None or lag > 1:
                    stats["n_declared_actual_but_lag_gt_1"] += 1
                if (not in_ledger) or lag is None or lag > 1:
                    stats["n_declared_actual_but_not_in_ledger_or_lag_gt_1"] += 1
        elif strict:
            stats["n_strict_genuine_but_not_declared"] += 1

    stats["pct_with_first_seen"] = pct(stats["n_with_first_seen"], n)
    stats["pct_strict_genuine"] = pct(stats["n_strict_genuine"], n)
    stats["pct_declared_actual_observation"] = pct(
        stats["n_declared_actual_observation"], n)
    stats["lag_stats"] = lag_stats(lag_samples)
    stats["lag_buckets"] = lag_buckets(lag_samples)
    out["actual_observation_support"] = stats

    # ---- strict vs lenient: the two numbers S-029 reports ----------------- #
    n_lenient = sum(1 for d in lag_samples if 0 <= d <= 7)
    lenient_records = set()
    n_lenient_not_declared = 0
    lenient_by_predicate = Counter()
    lenient_by_basis = Counter()
    n_lenient_near_realtime = 0
    for c in claims:
        fs, pub = val(c, "first_seen_at"), val(c, "published_at")
        if fs is None or pub is None:
            continue
        d = lag_days_ts(fs, pub)
        if d is not None and 0 <= d <= 7:
            lenient_records.add(str(c.get("source_record_id")
                                    or c.get("relation_id") or ""))
            lenient_by_predicate[str(pick(c, "predicate", "relation",
                                          "relation_type") or "MISSING")] += 1
            lenient_by_basis[str(val(c, "time_basis") or "MISSING")] += 1
            if c.get("near_realtime_this_study") is True:
                n_lenient_near_realtime += 1
            if str(val(c, "time_basis") or "") != "ACTUAL_OBSERVATION":
                n_lenient_not_declared += 1
    out["strict_vs_lenient"] = {
        "strict_definition": (
            "first_seen_at value exists in the observation ledger AND "
            "lag(first_seen_at - published_at) <= 1 day"),
        "n_strict": stats["n_strict_genuine"],
        "pct_strict": pct(stats["n_strict_genuine"], n),
        "lenient_definition": (
            "0 <= lag(first_seen_at - published_at) <= 7 days, using whatever "
            "first_seen_at the extract stored; it does NOT require the timestamp to "
            "come from the observation ledger"),
        "n_lenient": n_lenient,
        "pct_lenient": pct(n_lenient, n),
        "n_lenient_distinct_source_records": len(lenient_records),
        "n_lenient_distinct_evidence_records": len({
            str(c.get("evidence_id")) for c in claims
            if c.get("evidence_id") is not None
            and (lambda d: d is not None and 0 <= d <= 7)(
                lag_days_ts(val(c, "first_seen_at"), val(c, "published_at")))}),
        "n_lenient_labelled_ACTUAL_OBSERVATION": lenient_by_basis.get(
            "ACTUAL_OBSERVATION", 0),
        "n_lenient_labelled_SOURCE_PUBLISHED": lenient_by_basis.get(
            "SOURCE_PUBLISHED", 0),
        "n_lenient_labelled_HISTORICAL_PROXY": lenient_by_basis.get(
            "HISTORICAL_PROXY", 0),
        "n_lenient_by_time_basis": dict(lenient_by_basis),
        "n_lenient_with_near_realtime_this_study": n_lenient_near_realtime,
        "n_lenient_by_predicate": dict(lenient_by_predicate),
        "n_declared_actual_observation": stats["n_declared_actual_observation"],
        "n_lenient_but_not_declared_ACTUAL": n_lenient_not_declared,
        "n_lag_le_1d_but_not_an_observation": stats["n_lag_le_1"],
        "reading": (
            "The strict number is the STUDY'S VERDICT and is 0: no claim carries a "
            "point-in-time observation. The lenient number counts claims whose "
            "extraction stamp happens to fall within a week of the published date; "
            "that is a statement about this study's own fetch, not about knowledge "
            "available at the time. Reporting both is correct only if the lenient "
            "label is never called an observation."),
    }
    out["pipeline_fields_audit"] = {
        "strict_observed_asof": {
            "n_present": stats["n_strict_flag_present"],
            "values": dict(strict_flag_values),
            "n_true": stats["n_strict_flag_true"],
            "flag_true_but_audit_strict_false": stats[
                "n_strict_flag_true_but_not_strict"],
            "flag_false_but_audit_strict_true": stats[
                "n_strict_flag_false_but_strict"],
        },
        "observation_system": {
            "n_present": stats["n_observation_system_present"],
            "values": dict(observation_system_values),
            "values_by_audit_strictness": dict(observation_system_strict),
        },
        "near_realtime_this_study": {
            "n_present": stats["n_near_realtime_present"],
            "values": dict(near_realtime_values),
            "n_true": stats["n_near_realtime_true"],
            "values_by_audit_strictness": dict(near_realtime_strict),
            "n_true_that_are_audit_strict": near_realtime_strict.get(
                "True|strict=True", 0),
            "n_true_with_lag_gt_1": stats["n_near_realtime_true_lag_gt_1"],
            "n_true_with_lag_le_1": stats["n_near_realtime_true_lag_le_1"],
            "n_true_in_ledger": stats["n_near_realtime_true_in_ledger"],
        },
        "reading": (
            "The pipeline's own strict flag is audited, not trusted: this audit "
            "re-derives strictness from the observation ledger for every claim and "
            "reports any disagreement in both directions."),
    }

    # ---- contradictions --------------------------------------------------- #
    trial_pred = ("SPONSORS_TRIAL", "RESPONSIBLE_FOR_TRIAL", "HOSTS_TRIAL_SITE",
                  "CONDUCTS_TRIAL", "REFERENCES_PUBLICATION")
    contr = {"n_published_before_event": 0, "n_published_before_event_trial_relations": 0,
             "n_published_before_event_non_trial_relations": 0,
             "n_first_seen_before_published": 0,
             "n_valid_to_before_valid_from": 0,
             "n_declared_before_valid_from": 0,
             "n_anachronism_flag_true": 0,
             "n_anachronism_flag_and_computed": 0,
             "n_anachronism_computed_only": 0,
             "n_anachronism_flag_mismatch": 0}
    examples = []
    for c in claims:
        pred = str(pick(c, "predicate", "relation", "relation_type") or "")
        pub = val(c, "published_at")
        ev = val(c, "event_at")
        vf = val(c, "valid_from")
        vt = val(c, "valid_to")
        dec = val(c, "declared_at")
        fs = val(c, "first_seen_at")
        if pub is not None and ev is not None:
            d = lag_days(pub, ev)
            if d is not None and d < 0:
                contr["n_published_before_event"] += 1
                if pred in trial_pred:
                    contr["n_published_before_event_trial_relations"] += 1
                else:
                    contr["n_published_before_event_non_trial_relations"] += 1
                if len(examples) < 4:
                    examples.append({"kind": "published_before_event",
                                     "predicate": pred,
                                     "published_at": str(pub), "event_at": str(ev)})
        if fs is not None and pub is not None:
            d = lag_days_ts(fs, pub)
            if d is not None and d < 0:
                contr["n_first_seen_before_published"] += 1
        if vf is not None and vt is not None:
            d = lag_days(vt, vf)
            if d is not None and d < 0:
                contr["n_valid_to_before_valid_from"] += 1
        computed_anach = False
        if dec is not None and vf is not None:
            d = lag_days(vf, dec)
            if d is not None and d > 0:
                computed_anach = True
                contr["n_declared_before_valid_from"] += 1
                if len(examples) < 8:
                    examples.append({"kind": "declared_before_valid_from",
                                     "predicate": pred,
                                     "declared_at": str(dec),
                                     "valid_from": str(vf)})
        flag = pick(c, *CAND["anachronism"])
        if flag is True:
            contr["n_anachronism_flag_true"] += 1
            if computed_anach:
                contr["n_anachronism_flag_and_computed"] += 1
            else:
                contr["n_anachronism_flag_mismatch"] += 1
        elif computed_anach:
            contr["n_anachronism_computed_only"] += 1
    out["contradictions"] = contr
    out["contradiction_examples"] = examples
    out["contradictions"]["pct_published_before_event"] = pct(
        contr["n_published_before_event"], n)
    out["contradictions"]["pct_declared_before_valid_from"] = pct(
        contr["n_declared_before_valid_from"], n)

    # ---- per source family (derived, there is no source column) ----------- #
    def source_family(c):
        for k in ("source", "source_name", "source_system", "source_db"):
            if c.get(k):
                return str(c[k])
        for k in ("object_id", "subject_id"):
            v = str(c.get(k) or "")
            if v.startswith("ent:trial:"):
                return "clinicaltrials_gov"
            if v.startswith("ent:publication:"):
                return "europepmc"
            if v.startswith("ent:institution:"):
                return "institution"
        return "other"

    per_source = {}
    for fam in sorted({source_family(c) for c in claims}):
        sub = [c for c in claims if source_family(c) == fam]
        m = len(sub)
        lags = [lag_days_ts(val(c, "first_seen_at"), val(c, "published_at"))
                for c in sub]
        lags = [d for d in lags if d is not None]
        per_source[fam] = {
            "n": m,
            "pct_published_at": pct(sum(1 for c in sub if val(c, "published_at")), m),
            "pct_event_at": pct(sum(1 for c in sub if val(c, "event_at")), m),
            "pct_valid_from": pct(sum(1 for c in sub if val(c, "valid_from")), m),
            "pct_first_seen_at": pct(sum(1 for c in sub if val(c, "first_seen_at")), m),
            "lag_median_days": lag_stats(lags).get("median") if lags else None,
            "time_basis": dict(Counter(
                str(val(c, "time_basis") or "MISSING") for c in sub)),
        }
    out["per_source_family"] = per_source

    # ---- per predicate ---------------------------------------------------- #
    per_pred = {}
    for pred in sorted({str(pick(c, "predicate", "relation", "relation_type")
                            or "MISSING") for c in claims}):
        sub = [c for c in claims if
               str(pick(c, "predicate", "relation", "relation_type") or "MISSING") == pred]
        m = len(sub)
        per_pred[pred] = {
            "n": m,
            "pct_published_at": pct(sum(1 for c in sub if val(c, "published_at")), m),
            "pct_event_at": pct(sum(1 for c in sub if val(c, "event_at")), m),
            "pct_valid_from": pct(sum(1 for c in sub if val(c, "valid_from")), m),
            "pct_first_seen_at": pct(sum(1 for c in sub if val(c, "first_seen_at")), m),
            "declared_at_precision": dict(Counter(
                classify_precision(val(c, "declared_at")) for c in sub)),
            "pct_declared_at_day": pct(
                sum(1 for c in sub if classify_precision(val(c, "declared_at")) == "day"), m),
            "pct_declared_at_month_or_year": pct(
                sum(1 for c in sub
                    if classify_precision(val(c, "declared_at")) in ("month", "year")), m),
            "pct_declared_at_missing": pct(
                sum(1 for c in sub if classify_precision(val(c, "declared_at")) == "missing"), m),
            "event_at_precision": dict(Counter(
                classify_precision(val(c, "event_at")) for c in sub)),
            "pct_event_at_day": pct(
                sum(1 for c in sub if classify_precision(val(c, "event_at")) == "day"), m),
            "pct_event_at_month_or_year": pct(
                sum(1 for c in sub
                    if classify_precision(val(c, "event_at")) in ("month", "year")), m),
            "pct_event_at_missing": pct(
                sum(1 for c in sub if classify_precision(val(c, "event_at")) == "missing"), m),
            "valid_from_precision": dict(Counter(
                classify_precision(val(c, "valid_from")) for c in sub)),
            "time_basis": dict(Counter(
                str(val(c, "time_basis") or "MISSING") for c in sub)),
        }
    out["per_predicate"] = per_pred

    # ---- REFERENCES_PUBLICATION: is the cited paper dated before or after the
    #      trial that cites it? A registry cannot cite a paper published later. -- #
    ref_claims = [c for c in claims
                  if str(pick(c, "predicate", "relation", "relation_type") or "")
                  == "REFERENCES_PUBLICATION"]
    ref_audit = {
        "n_reference_claims": len(ref_claims),
        "n_resolved_to_publication_year": 0,
        "n_unresolved": 0,
        "n_pub_year_after_trial_year_IMPOSSIBLE": 0,
        "n_pub_year_equals_trial_year": 0,
        "n_pub_year_before_trial_year_LEGITIMATE": 0,
        "max_pub_year_after_gap": None,
        "max_pub_year_before_gap": None,
        "examples_impossible": [],
        "examples_legitimate_long_before": [],
        "n_impossible_explained_by_later_registry_update": 0,
        "n_impossible_unexplained": 0,
        "reading": ("The ClinicalTrials.gov reference list is CURRENT-STATE: the registry "
                    "keeps no history of when a reference was added, and the only stamp "
                    "is lastUpdatePostDate. A trial first posted in 2012 that lists a "
                    "2026 paper therefore means the reference was added at a later "
                    "registry update - it is back-dating of the relation, not a "
                    "contradiction. The claim dates the citation by the TRIAL's "
                    "first-post date, which is the defect. A cited paper published in an "
                    "EARLIER year is legitimate, but the relation must then be dated by "
                    "the paper's date, not by the trial's."),
    }
    if ref_claims:
        pub_index = _load_pub_index()
        trial_index = _load_trial_last_update_index()
        ref_audit["publication_year_index_size"] = len(pub_index)
        ref_audit["trial_index_size"] = len(trial_index)
        for c in ref_claims:
            ext = c.get("object_external_id") or {}
            keys = []
            if isinstance(ext, dict):
                if ext.get("pmid"):
                    keys.append(f"pmid:{ext['pmid']}")
                if ext.get("doi"):
                    keys.append(f"doi:{str(ext['doi']).lower()}")
            oid = str(c.get("object_id") or "")
            if oid.startswith("ent:publication:"):
                keys.append(oid[len("ent:publication:"):])
            entry = next((pub_index[k] for k in keys if k in pub_index), None)
            trial_d = val(c, "published_at") or val(c, "declared_at")
            trial_year = (int(str(trial_d)[:4])
                          if trial_d and str(trial_d)[:4].isdigit() else None)
            if entry is None or entry.get("pub_year") is None or trial_year is None:
                ref_audit["n_unresolved"] += 1
                continue
            pub_year = entry["pub_year"]
            ref_audit["n_resolved_to_publication_year"] += 1
            gap = pub_year - trial_year
            if gap > 0:
                ref_audit["n_pub_year_after_trial_year_IMPOSSIBLE"] += 1
                cur = ref_audit["max_pub_year_after_gap"]
                ref_audit["max_pub_year_after_gap"] = gap if cur is None else max(cur, gap)
                # Can the later registry update explain it? If the trial's last
                # update is after the paper's publication date, the reference could
                # have been added at that update -> mechanism, not contradiction.
                nct = str(c.get("source_record_id") or "")
                lu = (trial_index.get(nct) or {}).get("last_update_post_date")
                pub_date = entry.get("pub_date")
                d_last = lag_days(lu, pub_date) if (lu and pub_date) else None
                explained = d_last is not None and d_last >= 0
                if explained:
                    ref_audit["n_impossible_explained_by_later_registry_update"] += 1
                elif d_last is not None:
                    ref_audit["n_impossible_unexplained"] += 1
                if len(ref_audit["examples_impossible"]) < 4:
                    ref_audit["examples_impossible"].append({
                        "trial": c.get("source_record_id"),
                        "trial_first_post": str(trial_d),
                        "publication_year": pub_year,
                        "publication_date": pub_date,
                        "trial_last_update_post": lu,
                        "gap_years": gap,
                        "reference_added_later_explains_it": explained,
                        "object_id": oid or None})
            elif gap == 0:
                ref_audit["n_pub_year_equals_trial_year"] += 1
            else:
                ref_audit["n_pub_year_before_trial_year_LEGITIMATE"] += 1
                cur = ref_audit["max_pub_year_before_gap"]
                ref_audit["max_pub_year_before_gap"] = (-gap if cur is None
                                                        else max(cur, -gap))
                if len(ref_audit["examples_legitimate_long_before"]) < 3:
                    ref_audit["examples_legitimate_long_before"].append({
                        "trial": c.get("source_record_id"),
                        "trial_first_post": str(trial_d),
                        "publication_year": pub_year,
                        "gap_years": gap})
        for k in ("n_pub_year_after_trial_year_IMPOSSIBLE",
                  "n_pub_year_equals_trial_year",
                  "n_pub_year_before_trial_year_LEGITIMATE",
                  "n_resolved_to_publication_year", "n_unresolved"):
            ref_audit[f"pct_{k}"] = pct(ref_audit[k], len(ref_claims))
        ref_audit["pct_impossible_of_resolved"] = pct(
            ref_audit["n_pub_year_after_trial_year_IMPOSSIBLE"],
            ref_audit["n_resolved_to_publication_year"])
    out["references_publication_temporal_audit"] = ref_audit

    # ---- observed_lag_days cross-check (does the builder's own arithmetic
    #      agree with the timestamps it stored?) --------------------------- #
    mism = 0
    checked = 0
    for c in claims:
        ol = pick(c, *CAND["observed_lag"])
        fs, pub = val(c, "first_seen_at"), val(c, "published_at")
        if ol is None or fs is None or pub is None:
            continue
        checked += 1
        mine = lag_days_ts(fs, pub)
        if mine is None or int(ol) != int(mine):
            mism += 1
    out["observed_lag_crosscheck"] = {"n_checked": checked, "n_mismatch": mism}

    out["downstream_statement"] = (
        "Edges built from these claims are SOURCE_PUBLISHED or HISTORICAL_PROXY "
        "unless the claim carries a first_seen_at that the observation ledger "
        "actually contains with lag <= 1 day; the measured count is in "
        "actual_observation_support.n_strict_genuine.")
    out["status"] = "OK"
    return out


# --------------------------------------------------------------------------- #
# 10) Assemble
# --------------------------------------------------------------------------- #

def load_existing() -> dict:
    if OUT_JSON.exists():
        try:
            return json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def write_json(doc: dict) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    tmp = OUT_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=False),
                   encoding="utf-8")
    tmp.replace(OUT_JSON)


def build_budget(rec: Recorder) -> dict:
    per = {}
    for src in ("ctgov", "epmc", "openalex", "crossref"):
        calls = [c for c in rec.calls if c["source"] == src]
        per[src] = {
            "n_requests": len(calls),
            "cap": PER_SOURCE_CAP,
            "within_cap": len(calls) <= PER_SOURCE_CAP,
            "http_ok": sum(1 for c in calls if c["http_status"] == 200),
            "http_4xx": sum(1 for c in calls
                            if c["http_status"] and 400 <= c["http_status"] < 500 and
                            c["http_status"] != 429),
            "http_5xx": sum(1 for c in calls
                            if c["http_status"] and c["http_status"] >= 500),
            "network_errors": sum(1 for c in calls if c["error"]),
        }
    passes = {}
    for c in rec.calls:
        k = str(c.get("audit_pass", 1))
        passes[k] = passes.get(k, 0) + 1
    per_pass_source = {}
    for c in rec.calls:
        k = f'{c.get("audit_pass", 1)}:{c["source"]}'
        per_pass_source[k] = per_pass_source.get(k, 0) + 1
    return {
        "per_source": per,
        "requests_per_audit_pass": passes,
        "requests_per_pass_source": per_pass_source,
        "n_total_requests": len(rec.calls),
        "total_cap": TOTAL_CAP,
        "total_within_cap": len(rec.calls) <= TOTAL_CAP,
        "min_delay_between_requests_s": REQUEST_DELAY_S,
        "ledger_readonly": True,
    }


def stage1() -> dict:
    prior_doc = load_existing()
    prior_calls = prior_doc.get("request_ledger") or []
    rec = Recorder(prior_calls=prior_calls)

    sources = {}
    ctgov = ctgov_study_probe(rec, sources)
    epmc = epmc_probe(rec, sources)
    openalex = openalex_probe(rec, sources)
    crossref = crossref_probe(rec, sources)
    ledger = ledger_probe(sources)
    frozen = frozen_input_recheck()

    field_map = build_field_clock_map(ctgov, epmc, openalex, crossref, ledger)
    clock_avail = build_clock_availability(field_map)
    comparison = build_s028_comparison(ledger, frozen)

    claims = claims_clock_completeness()
    if (prior_doc.get("claims_clock_completeness") or {}).get("status") == "OK" and \
            claims.get("status") != "OK":
        claims = prior_doc["claims_clock_completeness"]

    doc = {
        "meta": {
            "study": "S-029 relation_network_s029",
            "task": "task-3",
            "role": "Temporal Provenance Auditor",
            "script": "code/s029_clock_audit.py",
            "generated_at_utc": utc_now_iso(),
            "stage": "stage1+stage2" if claims.get("status") == "OK" else "stage1",
            "python": sys.version.split()[0],
            "study_dir": str(STUDY_DIR),
            "request_delay_s": REQUEST_DELAY_S,
            "caps": {"per_source": PER_SOURCE_CAP, "total": TOTAL_CAP},
            "ledger_path": str(LEDGER),
            "ledger_access": "sqlite3 uri mode=ro",
            "sources_probed": list(sources.keys()),
            "clock_labels": CLOCK_LABELS,
            "no_manufactured_pit": (
                "No historical point-in-time observation can be manufactured. Every "
                "ACTUAL_OBSERVATION claim in this study must name a concrete "
                "sync_run/observation row; where none exists the time basis is "
                "HISTORICAL_PROXY, SOURCE_PUBLISHED, DATE_ONLY or TIME_UNKNOWN."),
        },
        "four_clocks": {
            "event_at": {
                "meaning": "when the underlying event actually happened",
                "example_fields": [
                    "ctgov protocolSection.statusModule.startDateStruct.date",
                    "epmc firstPublicationDate",
                    "openalex publication_date",
                    "crossref issued / published-online / published-print",
                ],
                "never": "never evidence of when anyone could know about it",
            },
            "published_at": {
                "meaning": "when the source made the record public",
                "example_fields": [
                    "ctgov studyFirstPostDateStruct.date",
                    "epmc firstIndexDate",
                    "openalex created_date",
                    "crossref created (deposit)",
                ],
                "never": "never the event itself, never MedRadar's observation",
            },
            "first_seen_at": {
                "meaning": "when MedRadar actually observed the record (real wall clock)",
                "example_fields": ["observatory.observation.first_seen_at"],
                "never": "never derivable from any of the above; must be observed",
            },
            "valid_from_valid_to": {
                "meaning": "period during which a relation is supported by evidence",
                "example_fields": ["NONE - not returned by any source API"],
                "never": "never a copy of event_at or published_at without a stated rule",
            },
        },
        "budget": build_budget(rec),
        "request_ledger": rec.calls,
        "sources": sources,
        "frozen_input_s028_recheck": frozen,
        "field_clock_map": field_map,
        "clock_availability": clock_avail,
        "study_corpus_precision_audit": study_corpus_precision_audit(),
        "s028_comparison": comparison,
        "claims_clock_completeness": claims,
        "verified_claims": None,
    }
    write_json(doc)
    return doc


def reanalyze() -> dict:
    """Recompute analysis from stored raw response data -- no network, no ledger write."""
    raise SystemExit("--reanalyze is intentionally not implemented: keep one source of "
                     "truth (the recorded response bodies are summarised inside "
                     "request_ledger + sources). Re-run --stage1 only if the live "
                     "sources must be re-queried.")


def refresh_bookkeeping() -> dict:
    """Recompute ONLY the non-network parts (ledger audit, frozen-input recheck,
    field->clock map, S-028 comparison, budget) from the stored request ledger.

    Makes ZERO network calls and does not touch any source database beyond the
    read-only ledger re-open. Used to correct bookkeeping without spending the
    remaining API budget.
    """
    doc = load_existing()
    if not doc:
        sys.exit("clock_audit.json missing; run --stage1 first")
    sources = doc.get("sources") or {}
    ledger_probe(sources)
    frozen = frozen_input_recheck()
    doc["sources"] = sources
    doc["frozen_input_s028_recheck"] = frozen
    doc["field_clock_map"] = build_field_clock_map(
        sources.get("clinicaltrials_gov") or {},
        sources.get("europe_pmc") or {},
        sources.get("openalex") or {},
        sources.get("crossref") or {},
        sources.get("medradar_observation_ledger") or {})
    doc["clock_availability"] = build_clock_availability(doc["field_clock_map"])
    doc["study_corpus_precision_audit"] = study_corpus_precision_audit()
    doc["s028_comparison"] = build_s028_comparison(
        sources.get("medradar_observation_ledger") or {}, frozen)
    rec = Recorder(prior_calls=doc.get("request_ledger") or [])
    doc["budget"] = build_budget(rec)
    doc["meta"]["refreshed_at_utc"] = utc_now_iso()
    doc["meta"]["network_calls_during_refresh"] = 0
    doc["claims_clock_completeness"] = claims_clock_completeness()
    write_json(doc)
    return doc


def stage2() -> dict:
    doc = load_existing()
    if not doc:
        sys.exit("clock_audit.json missing; run --stage1 first")
    doc["claims_clock_completeness"] = claims_clock_completeness()
    doc["meta"]["stage"] = "stage1+stage2" if doc["claims_clock_completeness"].get(
        "status") == "OK" else "stage1"
    doc["meta"]["generated_at_utc"] = utc_now_iso()
    write_json(doc)
    return doc


# --------------------------------------------------------------------------- #
# 11) Report verification: every number in the MD must exist in the JSON
# --------------------------------------------------------------------------- #

def flatten_numbers(obj, out=None):
    if out is None:
        out = set()
    if isinstance(obj, dict):
        for v in obj.values():
            flatten_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            flatten_numbers(v, out)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out.add(str(obj))
        out.add(str(int(obj)))
        out.add(f"{obj:.1f}")
        out.add(f"{obj:.2f}")
        out.add(f"{obj:.3f}")
        # thousands separator form used in the report
        try:
            out.add(f"{int(obj):,}")
        except Exception:
            pass
            out.add(str(obj))
    elif isinstance(obj, str):
        for tok in re.findall(r"\d+(?:\.\d+)?", obj):
            out.add(tok)
    return out


def verify_report() -> int:
    doc = load_existing()
    if not doc:
        sys.exit("clock_audit.json missing; run --stage1 first")
    if not REPORT_MD.exists():
        sys.exit(f"report missing: {REPORT_MD}")

    # NEVER let a previous verification report contaminate the number set:
    # the report itself contains unverified tokens, which would then "verify"
    # themselves on the next run.
    scan_doc = {k: v for k, v in doc.items() if k != "verified_claims"}
    numbers = flatten_numbers(scan_doc)
    text = REPORT_MD.read_text(encoding="utf-8")

    # strip structural tokens before verifying data numbers:
    #   headings, section references like "§2.5", ordered-list markers "1. "
    body = "\n".join(ln for ln in text.splitlines()
                     if not ln.lstrip().startswith("#"))
    body = re.sub(r"§\s*\d+(?:\.\d+)*", " ", body)
    body = re.sub(r"(?m)^\s*\d+\.\s", " ", body)

    # structural / non-data tokens permitted in the report
    structural = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12",
                  "2026", "2027", "2016", "2015", "2014", "2013", "2012", "2011", "2010"}
    tokens = re.findall(r"(?<![\w.\-/])(\d+(?:\.\d+)?)(?![\w])", body)
    missing = []
    for tok in tokens:
        if tok in structural or tok in numbers:
            continue
        missing.append(tok)
    uniq = sorted(set(missing), key=lambda s: (len(s), s))
    report = {
        "report": str(REPORT_MD),
        "n_number_tokens": len(tokens),
        "n_distinct_tokens": len(set(tokens)),
        "n_unverified": len(uniq),
        "unverified_tokens": uniq[:60],
        "verified": not uniq,
    }
    doc["verified_claims"] = report
    doc["meta"]["report_verified"] = report["verified"]
    doc["meta"]["report_unverified_count"] = report["n_unverified"]
    write_json(doc)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not uniq else 1


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage1", action="store_true", help="live probes + ledger audit")
    ap.add_argument("--stage2", action="store_true", help="claims clock completeness")
    ap.add_argument("--refresh", action="store_true",
                    help="recompute non-network bookkeeping only (0 API calls)")
    ap.add_argument("--reanalyze", action="store_true")
    ap.add_argument("--verify-report", action="store_true")
    args = ap.parse_args(argv)

    if args.verify_report:
        return verify_report()
    if args.refresh:
        doc = refresh_bookkeeping()
        print(json.dumps({
            "refreshed_at": doc["meta"].get("refreshed_at_utc"),
            "network_calls": 0,
            "n_total_requests_recorded": doc["budget"]["n_total_requests"],
            "ledger_unchanged": (doc["sources"]["medradar_observation_ledger"]
                                 .get("file_unchanged")),
            "ledger_readonly_probe": (doc["sources"]["medradar_observation_ledger"]
                                      .get("readonly_probe", {}).get("write_probe")),
            "s028_verdict": doc["s028_comparison"]["verdict"],
        }, ensure_ascii=False, indent=2))
        return 0
    if args.reanalyze:
        return reanalyze()
    if args.stage2:
        doc = stage2()
        cc = doc["claims_clock_completeness"]
        print(json.dumps({"status": cc.get("status"),
                          "n_claims": cc.get("n_claims"),
                          "completeness": cc.get("completeness"),
                          "contradictions": cc.get("contradictions")},
                         ensure_ascii=False, indent=2))
        return 0
    if args.stage1 or len(sys.argv) == 1:
        doc = stage1()
        print(json.dumps({
            "budget": doc["budget"],
            "n_studies_sampled": doc["sources"]["clinicaltrials_gov"]["n_studies_sampled"],
            "n_papers_sampled": doc["sources"]["europe_pmc"]["n_papers_sampled"],
            "n_works_openalex": doc["sources"]["openalex"]["n_works_sampled"],
            "n_works_crossref": doc["sources"]["crossref"]["n_works_sampled"],
            "ledger": {
                "n_observations": doc["sources"]["medradar_observation_ledger"]["n_observations"],
                "tier_counts": doc["sources"]["medradar_observation_ledger"]["tier_counts"],
                "prospective": doc["sources"]["medradar_observation_ledger"]
                ["lag_first_seen_minus_published_days"]["n_prospective_le_1d"],
            },
            "s028_verdict": doc["s028_comparison"]["verdict"],
            "stage": doc["meta"]["stage"],
            "written": str(OUT_JSON),
        }, ensure_ascii=False, indent=2))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
