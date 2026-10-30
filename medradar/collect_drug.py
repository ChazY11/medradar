"""openFDA Drugs@FDA collector: original NDA/BLA approvals -> ``drug_approval``.

Why this shape
--------------
``drug/drugsfda.json`` is application-centric: one document holds *all*
submissions ever filed for an application (original approval, supplements,
labeling changes...). A "new drug approval" in the industry-radar sense is only
the **ORIG** submission whose status is **AP** (approved), and only for
NDA/BLA applications - ANDAs are generic copies of an already-approved molecule
and would drown the signal.

``event_date`` is therefore the ``submission_status_date`` of that ORIG
submission: the day the decision became public. Using the collection date (or
the latest submission date) would leak future information into every
downstream backtest.

Payload contract (shared with ``analyze``)
------------------------------------------
``payload`` keeps the raw openFDA record under ``raw`` **and** a flat set of
normalised keys, because the analysis stage must not need to know openFDA's
nested layout::

    {"application_number": "NDA215859", "sponsor_name": "...",
     "brand_name": "...", "active_ingredient": "...",
     "submission_class_code": "TYPE 1", "submission_status_date": "2023-01-15",
     "raw": {...}}
"""

from __future__ import annotations

import calendar
import re
import sys
from datetime import date
from typing import Any, Mapping

from .config import CompanyRegistry, load_companies, load_tracks
from .db import DB, make_event_id
from .http import NotFound
from .util import today_utc, utc_now_iso

SOURCE = "openfda_drug_drugsfda"
KIND = "drug_approval"
API_URL = "https://api.fda.gov/drug/drugsfda.json"

PAGE_LIMIT = 1000
# openFDA rejects ``skip`` beyond 25_000, so deep windows stop there and are
# flagged as truncated instead of silently losing data.
MAX_SKIP = 25_000
MAX_PAGES = 40

_APP_RE = re.compile(r"^(NDA|BLA)\d{3,}$")
_WS = re.compile(r"[^A-Z0-9]+")


# --------------------------------------------------------------------------- dates
def window(months: int, today: date | None = None) -> tuple[date, date]:
    """Return ``(start, end)`` for a ``months``-long lookback window."""
    end = today or today_utc()
    months = max(1, int(months or 1))
    total = end.year * 12 + (end.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    day = min(end.day, calendar.monthrange(year, month)[1])
    return date(year, month, day), end


# ----------------------------------------------------------------- drug filters
def is_nda_or_bla(application_number: Any) -> bool:
    """True for ``NDA...``/``BLA...``; ANDA (generic) applications are excluded."""
    text = str(application_number or "").strip().upper()
    return bool(_APP_RE.match(text))


def is_original_approval(submission: Mapping[str, Any] | None) -> bool:
    """True only for an ORIG submission that ended in AP (approved)."""
    if not submission:
        return False
    return (
        str(submission.get("submission_type", "")).strip().upper() == "ORIG"
        and str(submission.get("submission_status", "")).strip().upper() == "AP"
    )


def _first(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def brand_name(record: Mapping[str, Any]) -> str:
    products = record.get("products") or []
    for product in products:
        if product.get("brand_name"):
            return str(product["brand_name"]).strip()
    return str(_first((record.get("openfda") or {}).get("brand_name")) or "").strip()


def active_ingredient(record: Mapping[str, Any]) -> str:
    for product in record.get("products") or []:
        for ingredient in product.get("active_ingredients") or []:
            if ingredient.get("name"):
                return str(ingredient["name"]).strip()
    return str(_first((record.get("openfda") or {}).get("generic_name")) or "").strip()


def drugsfda_url(application_number: str) -> str:
    digits = "".join(ch for ch in str(application_number) if ch.isdigit())
    if not digits:
        return "https://www.accessdata.fda.gov/scripts/cder/daf/"
    return (
        "https://www.accessdata.fda.gov/scripts/cder/daf/"
        f"index.cfm?event=overview.process&ApplNo={digits}"
    )


def normalize_approval(
    record: Mapping[str, Any],
    submission: Mapping[str, Any],
    *,
    company_key: str | None = None,
    confidence: float = 0.0,
    alias: str = "",
    as_of: str | None = None,
) -> dict[str, Any] | None:
    """Build one normalised ``drug_approval`` event, or ``None`` if not eligible.

    Pure function: no I/O, so the NDA/BLA + ORIG/AP rules are unit-testable
    without a database or a network call.
    """
    application_number = str(record.get("application_number") or "").strip().upper()
    if not is_nda_or_bla(application_number) or not is_original_approval(submission):
        return None

    event_date = str(submission.get("submission_status_date") or "").strip()
    if not event_date:
        return None

    sponsor = str(record.get("sponsor_name") or "").strip()
    brand = brand_name(record)
    ingredient = active_ingredient(record)
    class_code = submission.get("submission_class_code")
    class_code = str(class_code).strip() if class_code else None
    if class_code and class_code.upper() == "UNKNOWN":
        # openFDA stores "UNKNOWN" for older records; keep it visible but tagged.
        class_code = "UNKNOWN"
    submission_number = str(submission.get("submission_number") or "").strip()

    label = brand or ingredient or application_number
    detail = f" ({ingredient})" if ingredient and ingredient.upper() != label.upper() else ""
    title = f"{label}{detail}"

    event = {
        "event_id": make_event_id(
            SOURCE, KIND, application_number, submission_number or event_date
        ),
        "source": SOURCE,
        "kind": KIND,
        "event_date": event_date,
        "as_of": as_of or today_utc().isoformat(),
        "company_key": company_key,
        "applicant_raw": sponsor,
        "country": "US",
        "track_id": None,  # Drugs@FDA has no indication field; trials carry tracks.
        "product_code": None,
        "title": title,
        "summary": (
            f"{sponsor or '未知申请人'}｜{application_number}｜{title}"
            f"｜{class_code or 'N/A'}｜{event_date}"
        ),
        "url": drugsfda_url(application_number),
        "payload": {
            "application_number": application_number,
            "sponsor_name": sponsor,
            "brand_name": brand,
            "active_ingredient": ingredient,
            "submission_class_code": class_code,
            "submission_status_date": event_date,
            "submission_type": submission.get("submission_type"),
            "submission_status": submission.get("submission_status"),
            "submission_number": submission_number or None,
            "match_confidence": confidence,
            "matched_alias": alias,
            "raw": dict(record),
        },
    }
    return event


# ---------------------------------------------------------------------- collector
def collect(
    db: DB,
    fetcher: Any,
    months: int = 120,
    limit: int = 0,
    *,
    registry: CompanyRegistry | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Fetch ORIG/AP NDA/BLA approvals inside the window and upsert events."""
    registry = registry or load_companies("drug")
    tracks = load_tracks("drug")
    db.upsert_companies(registry.all())
    db.upsert_tracks(tracks.all())

    start, end = window(months, today)
    search = (
        "submissions.submission_status_date:"
        f"[{start.strftime('%Y%m%d')} TO {end.strftime('%Y%m%d')}]"
    )
    requests_before = int(fetcher.stats.get("requests", 0))
    budget = int(getattr(fetcher, "max_requests", 10**9))

    pages = 0
    documents = 0
    events: dict[str, dict[str, Any]] = {}
    truncated = False
    skip = 0
    while pages < MAX_PAGES:
        if int(fetcher.stats.get("requests", 0)) + 3 >= budget:
            truncated = True
            break
        try:
            payload = fetcher.get_json(
                API_URL,
                {"search": search, "limit": PAGE_LIMIT, "skip": skip},
            )
        except NotFound:
            break
        pages += 1
        results = (payload or {}).get("results") or []
        total = int(
            (((payload or {}).get("meta") or {}).get("results") or {}).get("total") or 0
        )
        if not results:
            break
        documents += len(results)

        for record in results:
            if not isinstance(record, Mapping):
                continue
            application_number = str(record.get("application_number") or "")
            if not is_nda_or_bla(application_number):
                continue
            sponsor = str(record.get("sponsor_name") or "")
            company_key, confidence, alias = registry.resolve(sponsor)
            for submission in record.get("submissions") or []:
                if not isinstance(submission, Mapping):
                    continue
                event = normalize_approval(
                    record,
                    submission,
                    company_key=company_key,
                    confidence=confidence,
                    alias=alias,
                )
                if event is not None:
                    events[event["event_id"]] = event

        if limit and len(events) >= limit:
            break
        skip += PAGE_LIMIT
        if skip >= total:
            break
        if skip > MAX_SKIP:
            truncated = True
            break

    chosen = list(events.values())
    chosen.sort(key=lambda event: event["event_date"])
    if limit:
        chosen = chosen[:limit]
    inserted = db.upsert_events(chosen) if chosen else 0
    if chosen:
        db.log_run("collect_drug", {"events": inserted, "pages": pages})

    matched = sum(1 for event in chosen if event.get("company_key"))
    unmatched: dict[str, int] = {}
    for event in chosen:
        if not event.get("company_key"):
            name = str(event.get("applicant_raw") or "").strip() or "(empty)"
            unmatched[name] = unmatched.get(name, 0) + 1
    top_unmatched = sorted(unmatched.items(), key=lambda pair: -pair[1])[:12]

    stats = {
        "source": SOURCE,
        "status": "ok",
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "pages": pages,
        "documents": documents,
        "events": inserted,
        "per_kind": {KIND: inserted},
        "matched": matched,
        "match_rate": round(matched / inserted, 4) if inserted else 0.0,
        "unmatched": inserted - matched,
        "top_unmatched": [[name, count] for name, count in top_unmatched],
        "truncated": truncated,
        "requests": int(fetcher.stats.get("requests", 0)) - requests_before,
    }
    print(
        f"[drug] {inserted} drug_approval events / {documents} documents, "
        f"{matched} matched ({stats['match_rate']:.0%}), {stats['requests']} requests",
        file=sys.stderr,
    )
    return stats
