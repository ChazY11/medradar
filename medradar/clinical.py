"""ClinicalTrials.gov v2 collector: interventional study registrations -> ``trial``.

Why ``StudyFirstPostDate``
--------------------------
For a backtest we need the date on which the market could *first* learn that a
trial exists. ``StartDate`` is often back-dated and only published later;
``LastUpdatePostDate`` moves every edit. ``StudyFirstPostDate`` is the
registration date - the earliest public knowledge - so it is the one used for
``event_date`` (no look-ahead bias).

Coverage
--------
Both watchlists are queried: ``config/companies_drug.json`` and
``config/companies_device.json``. Each company contributes one or two sponsor
search terms (parent name + one alias that adds a token, e.g. ``JANSSEN`` for
J&J, ``COVIDIEN`` for Medtronic). Results are fetched newest-first, so paging can
stop as soon as the window is exhausted, and are de-duplicated by NCT id across
sponsors.

Track assignment uses the **drug** therapeutic-area dictionary on the study
``Condition`` field (``tracks_drug.json``) - that is what the drug radar reports
on. Company attribution uses ``CompanyRegistry.resolve(LeadSponsorName)``. A
study whose lead sponsor does not resolve is kept with ``company_key = NULL``
(docs/SCHEMA.md §6) instead of being guessed or silently dropped, and the
unmatched rate plus the noisiest unmatched sponsors are reported in ``stats``.

Payload contract (shared with ``analyze``)
------------------------------------------
``payload`` keeps the raw study under ``raw`` and a flat normalised block::

    {"nct_id": "NCT...", "phase": ["PHASE3"], "status": "RECRUITING",
     "conditions": [...], "enrollment": 520, "study_type": "INTERVENTIONAL",
     "lead_sponsor": "...", "first_posted": "2024-06-01", "raw": {...}}
"""

from __future__ import annotations

import calendar
import re
import sys
from datetime import date
from typing import Any, Iterable, Mapping

from .config import (
    CompanyRegistry,
    TrackRegistry,
    load_companies,
    load_tracks,
)
from .db import DB, make_event_id
from .util import iso, norm_text, parse_date, today_utc

SOURCE = "ctgov"
KIND = "trial"
API_URL = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = (
    "NCTId,BriefTitle,Phase,StartDate,StudyFirstPostDate,OverallStatus,"
    "LeadSponsorName,Condition,StudyType,EnrollmentCount"
)
PAGE_SIZE = 100
STUDY_TYPE = "INTERVENTIONAL"
#: Hard cap on how deep one sponsor query is paged.
MAX_PAGES_PER_TERM = 3
#: This collector refuses to spend more than this many requests per run.
MAX_REQUESTS = 360
#: Stop paging when the fetcher's own budget gets this close to exhaustion.
BUDGET_FLOOR = 12

_ALLOWED_PHASES = {"PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"}
_SUFFIXES = {
    "INC",
    "INCORPORATED",
    "LLC",
    "LTD",
    "LIMITED",
    "CORP",
    "CORPORATION",
    "CO",
    "COMPANY",
    "USA",
    "US",
    "GMBH",
    "AG",
    "SA",
    "AS",
    "PLC",
    "NV",
    "BV",
    "PTY",
    "LP",
    "HOLDING",
    "HOLDINGS",
    "INNOVATIVE",
    "MEDICINE",
    "MEDICINES",
    "MEDTECH",
}


# --------------------------------------------------------------------------- dates
def window(months: int, today: date | None = None) -> tuple[date, date]:
    end = today or today_utc()
    months = max(1, int(months or 1))
    total = end.year * 12 + (end.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    day = min(end.day, calendar.monthrange(year, month)[1])
    return date(year, month, day), end


# ------------------------------------------------------------------- normalising
def normalize_phase(phases: Iterable[Any] | None) -> list[str]:
    """Upper-case phase strings; ``EARLY_PHASE1`` counts as phase 1, junk -> NA.

    Missing phases yield ``[]`` (``analyze`` degrades to "unknown" rather than
    inventing a phase).
    """
    result: list[str] = []
    for raw in phases or []:
        text = re.sub(r"[\s\-_]+", "", str(raw or "").strip().upper())
        if not text:
            continue
        if text in ("EARLYPHASE1", "EARLYPHASEI"):
            text = "PHASE1"
        if text not in _ALLOWED_PHASES:
            text = "NA"
        if text not in result:
            result.append(text)
    return result


def normalize_conditions(conditions: Iterable[Any] | None) -> list[str]:
    result: list[str] = []
    for raw in conditions or []:
        text = str(raw or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _enrollment(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def normalize_study(study: Mapping[str, Any]) -> dict[str, Any] | None:
    """Flatten one CT.gov v2 study into the normalised payload block, or ``None``.

    Returns ``None`` when the study lacks an NCT id, a ``StudyFirstPostDate`` or
    is not interventional - the caller then drops it without writing anything.
    """
    protocol = study.get("protocolSection") or {}
    identification = protocol.get("identificationModule") or {}
    nct_id = str(identification.get("nctId") or "").strip()
    if not nct_id:
        return None

    design = protocol.get("designModule") or {}
    study_type = str(design.get("studyType") or "").strip().upper()
    if study_type != STUDY_TYPE:
        return None

    status_module = protocol.get("statusModule") or {}
    first_posted_raw = str(
        (status_module.get("studyFirstPostDateStruct") or {}).get("date") or ""
    ).strip()
    if not first_posted_raw:
        return None
    # CT.gov sometimes only knows ``YYYY-MM``; normalise to the first of the
    # month so ``event_date`` is a real ISO date (never a guess beyond that).
    first_posted = iso(first_posted_raw) or first_posted_raw

    start_raw = str(
        (status_module.get("startDateStruct") or {}).get("date") or ""
    ).strip()
    start_date = iso(start_raw) or start_raw
    sponsor_module = protocol.get("sponsorCollaboratorsModule") or {}
    lead_sponsor = str(
        (sponsor_module.get("leadSponsor") or {}).get("name") or ""
    ).strip()
    conditions = normalize_conditions(
        (protocol.get("conditionsModule") or {}).get("conditions")
    )
    enrollment = _enrollment((design.get("enrollmentInfo") or {}).get("count"))

    return {
        "nct_id": nct_id,
        "phase": normalize_phase(design.get("phases")),
        "status": str(status_module.get("overallStatus") or "").strip().upper(),
        "conditions": conditions,
        "enrollment": enrollment,
        "study_type": study_type,
        "lead_sponsor": lead_sponsor,
        "first_posted": first_posted,
        "start_date": start_date or None,
        "brief_title": str(identification.get("briefTitle") or "").strip(),
        "raw": dict(study),
    }


def build_event(
    payload: Mapping[str, Any],
    *,
    company_key: str | None,
    confidence: float,
    alias: str,
    track_id: str | None,
    as_of: str,
) -> dict[str, Any]:
    """Wrap a normalised study payload into an ``events`` row."""
    nct_id = payload["nct_id"]
    conditions = "、".join(payload.get("conditions") or []) or "未标注适应症"
    phases = "/".join(payload.get("phase") or []) or "N/A"
    title = payload.get("brief_title") or nct_id
    return {
        "event_id": make_event_id(SOURCE, KIND, nct_id),
        "source": SOURCE,
        "kind": KIND,
        "event_date": payload["first_posted"],
        "as_of": as_of,
        "company_key": company_key,
        "applicant_raw": payload.get("lead_sponsor") or "",
        "country": "US",
        "track_id": track_id,
        "product_code": None,
        "title": title,
        "summary": (
            f"{payload.get('lead_sponsor') or '未知申办方'}｜{nct_id}"
            f"｜{phases}｜{conditions}"
        ),
        "url": f"https://clinicaltrials.gov/study/{nct_id}",
        "payload": {**payload, "match_confidence": confidence, "matched_alias": alias},
    }


# --------------------------------------------------------------------- query plan
def clean_name(value: Any) -> str:
    """Normalise an org name for the CT.gov sponsor query (drop legal suffixes)."""
    tokens = norm_text(value).split()
    while len(tokens) >= 2 and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def query_terms(company: Mapping[str, Any]) -> list[str]:
    """Parent name plus one alias that contributes a new token (max two terms)."""
    primary = clean_name(company.get("name_en"))
    terms: list[str] = []
    if primary:
        terms.append(primary)
    primary_tokens = set(primary.split())
    for alias in company.get("aliases") or []:
        candidate = clean_name(alias)
        if not candidate or candidate in terms:
            continue
        if set(candidate.split()) - primary_tokens:
            terms.append(candidate)
            break
    return terms


def plan_terms(companies: Iterable[Mapping[str, Any]]) -> list[str]:
    """De-duplicate sponsor terms across both watchlists, majors first."""
    ordered = sorted(
        companies, key=lambda company: (-int(company.get("is_major") or 0), company.get("key", ""))
    )
    seen: set[str] = set()
    terms: list[str] = []
    for company in ordered:
        for term in query_terms(company):
            if term not in seen:
                seen.add(term)
                terms.append(term)
    return terms


# ---------------------------------------------------------------------- collector
def _fetch_term(
    fetcher: Any,
    term: str,
    start: date,
    end: date,
    requests_used: int,
    budget: int,
) -> tuple[list[dict[str, Any]], int, int]:
    """Page one sponsor term newest-first. Returns (studies, pages, total)."""
    studies: list[dict[str, Any]] = []
    pages = 0
    total = 0
    token: str | None = None
    while pages < MAX_PAGES_PER_TERM:
        left = budget - int(fetcher.stats.get("requests", 0))
        if left <= BUDGET_FLOOR or requests_used >= MAX_REQUESTS:
            break
        params: dict[str, Any] = {
            "query.spons": term,
            "pageSize": PAGE_SIZE,
            "countTotal": "true",
            "fields": FIELDS,
            "sort": "StudyFirstPostDate:desc",
            "filter.advanced": (
                f"AREA[StudyFirstPostDate]RANGE[{start.isoformat()},{end.isoformat()}]"
            ),
        }
        if token:
            params["pageToken"] = token
        payload = fetcher.get_json(API_URL, params)
        pages += 1
        requests_used += 1
        batch = (payload or {}).get("studies") or []
        total = int((payload or {}).get("totalCount") or total or 0)
        studies.extend(study for study in batch if isinstance(study, Mapping))
        token = (payload or {}).get("nextPageToken")
        if len(batch) < PAGE_SIZE or not token:
            break
    return studies, pages, total


def collect_trials(
    db: DB,
    fetcher: Any,
    months: int = 120,
    limit: int = 0,
    *,
    registry: CompanyRegistry | None = None,
    tracks: TrackRegistry | None = None,
    companies: list[Mapping[str, Any]] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Query both watchlists, keep interventional studies, upsert ``trial`` events."""
    if companies is None:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for kind in ("drug", "device"):
            for company in load_companies(kind).all():
                if company["key"] not in seen:
                    seen.add(company["key"])
                    merged.append(company)
        companies = merged
    registry = registry or CompanyRegistry(companies)
    drug_tracks = tracks or load_tracks("drug")
    device_tracks = load_tracks("device")
    db.upsert_companies(registry.all())
    db.upsert_tracks(drug_tracks.all())
    db.upsert_tracks(device_tracks.all())

    start, end = window(months, today)
    requests_before = int(fetcher.stats.get("requests", 0))
    budget = int(getattr(fetcher, "max_requests", 10**9))
    as_of = (today or today_utc()).isoformat()

    terms = plan_terms(companies)
    studies: dict[str, Mapping[str, Any]] = {}
    pages = 0
    sponsor_totals: dict[str, int] = {}
    truncated = False
    for index, term in enumerate(terms, start=1):
        if int(fetcher.stats.get("requests", 0)) - requests_before >= MAX_REQUESTS:
            truncated = True
            break
        try:
            batch, used_pages, total = _fetch_term(
                fetcher,
                term,
                start,
                end,
                int(fetcher.stats.get("requests", 0)) - requests_before,
                budget,
            )
        except Exception as exc:  # one bad sponsor must not kill the collector
            print(f"[trials] sponsor {term!r} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        pages += used_pages
        sponsor_totals[term] = total
        for study in batch:
            protocol = study.get("protocolSection") or {}
            nct_id = ((protocol.get("identificationModule") or {}).get("nctId") or "").strip()
            if nct_id and nct_id not in studies:
                studies[nct_id] = study
        if index % 10 == 0:
            print(
                f"[trials] {index}/{len(terms)} sponsor terms, {len(studies)} studies, "
                f"{int(fetcher.stats.get('requests', 0)) - requests_before} requests",
                file=sys.stderr,
            )

    events: dict[str, dict[str, Any]] = {}
    interventional = 0
    in_window = 0
    track_matched = 0
    unmatched: dict[str, int] = {}
    for study in studies.values():
        payload = normalize_study(study)
        if payload is None:
            continue
        interventional += 1
        posted = parse_date(payload["first_posted"])
        if posted is None or posted < start or posted > end:
            continue
        in_window += 1
        lead = payload.get("lead_sponsor") or ""
        company_key, confidence, alias = registry.resolve(lead)
        if not company_key:
            # Keep the trial (docs/SCHEMA.md §6: unmatched => company_key NULL)
            # instead of dropping it: it may still be an industry-collaborator
            # study and it still carries a therapeutic-area signal.
            name = lead.strip() or "(empty)"
            unmatched[name] = unmatched.get(name, 0) + 1
        track_id = drug_tracks.match_text(" ".join(payload.get("conditions") or []))
        if track_id:
            track_matched += 1
        event = build_event(
            payload,
            company_key=company_key,
            confidence=confidence,
            alias=alias,
            track_id=track_id,
            as_of=as_of,
        )
        events[event["event_id"]] = event

    chosen = list(events.values())
    chosen.sort(key=lambda event: event["event_date"])
    if limit:
        chosen = chosen[:limit]
    inserted = db.upsert_events(chosen) if chosen else 0
    if chosen:
        db.log_run("collect_trials", {"events": inserted, "pages": pages})

    matched = sum(1 for event in chosen if event.get("company_key"))
    top_unmatched = sorted(unmatched.items(), key=lambda pair: -pair[1])[:12]
    stats = {
        "source": SOURCE,
        "status": "ok",
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "sponsor_terms": len(terms),
        "pages": pages,
        "studies": len(studies),
        "interventional": interventional,
        "in_window": in_window,
        "events": inserted,
        "per_kind": {KIND: inserted},
        "matched": matched,
        "match_rate": round(matched / inserted, 4) if inserted else 0.0,
        "unmatched": inserted - matched,
        "top_unmatched": [[name, count] for name, count in top_unmatched],
        "track_matched": track_matched,
        "track_match_rate": round(track_matched / inserted, 4) if inserted else 0.0,
        "truncated": truncated,
        "requests": int(fetcher.stats.get("requests", 0)) - requests_before,
    }
    print(
        f"[trials] {inserted} trial events from {len(studies)} studies "
        f"({interventional} interventional, {in_window} in window), "
        f"{matched}/{inserted} attributable ({stats['match_rate']:.0%}), "
        f"track match {stats['track_match_rate']:.0%}, {stats['requests']} requests",
        file=sys.stderr,
    )
    return stats
