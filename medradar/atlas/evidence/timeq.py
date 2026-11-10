"""Time semantics for external evidence.

MedRadar's data contract already separates ``event_date`` from ``published_at``
and ``first_seen_at``.  This module makes that separation explicit for *every*
external source, and refuses to let a convenient date stand in for a defensible
one.

Four clocks
-----------
``event_at``
    When the underlying event happened (a decision date, a grant start, a
    shipment date).  This is what a study usually wants to align on.
``source_public_at``
    When the record first became publicly visible *at the source*.  This is
    the earliest date a third party could have known it.  For a patent this is
    the **publication** date, never the filing date.
``first_observed_at``
    When the MedRadar pipeline first saw the record.  It is a fetch clock, not
    a knowledge clock: a backfill of 2016 data today has
    ``first_observed_at = today``.  Studies that need "what could we have known
    on date D" must use ``source_public_at``, and must say so.
``fetched_at``
    When this particular copy was retrieved.

Quality levels apply to ``source_public_at`` (see
:data:`medradar.external_sources.schema.TIME_QUALITIES`).  A ``coarse`` or
``derived`` publication date may be used descriptively but is excluded from
lead-time claims by :func:`lead_time_days` unless the caller opts in.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping

DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y%m%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%b %d, %Y",
)

_MONTHS = {name.lower(): idx for idx, name in enumerate(calendar.month_abbr) if name}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso() -> str:
    """Current UTC time as an ISO-8601 string with a ``Z`` suffix."""
    return iso(utc_now())


def iso(dt: datetime | date | None) -> str:
    """ISO-8601 UTC string, or ``""`` for a missing value (never ``None``)."""
    if dt is None:
        return ""
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt.isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_date(value: Any) -> date | None:
    """Best-effort calendar-date parse.  Returns ``None`` rather than guessing."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)
    # ISO datetime prefix (e.g. "2024-06-01T12:00:00Z")
    if "T" in text:
        text = text.split("T", 1)[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    m = re.match(r"^(\d{4})-(\d{2})$", text)
    if m:  # month precision -> first of month, caller must downgrade quality
        return date(int(m.group(1)), int(m.group(2)), 1)
    m = re.match(r"^(\d{4})$", text)
    if m:
        return date(int(m.group(1)), 1, 1)
    return None


def parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp with a timezone, or ``None``."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        day = parse_date(text)
        return datetime.combine(day, time.min, tzinfo=timezone.utc) if day else None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def implied_quality(raw_value: Any) -> str:
    """Infer the precision a source actually published, without inflating it."""
    if raw_value is None:
        return "unknown"
    text = str(raw_value).strip()
    if not text:
        return "unknown"
    if "T" in text:
        return "exact"
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return "day"
    if re.match(r"^\d{4}[-/]?\d{2}$", text) or re.match(r"^\d{4}$", text):
        return "coarse"
    return "day" if parse_date(text) else "unknown"


def build_time(
    *,
    event_at: Any = None,
    source_public_at: Any = None,
    quality: str | None = None,
    fetched_at: datetime | None = None,
    first_observed_at: datetime | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Assemble the four-clock block required by the schema.

    ``first_observed_at`` defaults to ``fetched_at``, because for a first
    backfill they are the same event.  It is never defaulted to
    ``source_public_at``: that would fabricate an observation history.
    """
    # Connectors pass ISO strings from the HTTP ledger; callers may also pass
    # datetimes.  Coerce uniformly rather than assuming one representation.
    fetched = parse_datetime(fetched_at) if fetched_at else utc_now()
    if fetched is None:
        fetched = utc_now()
    observed = parse_datetime(first_observed_at) if first_observed_at else fetched
    if observed is None:
        observed = fetched
    derived_quality = quality or implied_quality(source_public_at)
    return {
        "event_at": iso(parse_date(event_at)),
        "source_public_at": iso(parse_date(source_public_at)),
        "first_observed_at": iso(observed),
        "fetched_at": iso(fetched),
        "source_public_at_quality": derived_quality,
        "observation_basis": "fetch_clock",
        "notes": notes,
    }


def lead_time_days(public_at: Any, event_at: Any) -> int | None:
    """Days between first public visibility and the event, or ``None``.

    Positive means the evidence was public *before* the event.  Returns
    ``None`` when either date is missing — never 0, never an estimate.
    """
    published = parse_date(public_at)
    happened = parse_date(event_at)
    if published is None or happened is None:
        return None
    return (happened - published).days


def quality_allows_lead_time(quality: str) -> bool:
    """Only day-or-better publication dates may support a lead-time claim."""
    return quality in {"exact", "day"}


def check_ordering(block: Mapping[str, Any]) -> list[str]:
    """Flag logically impossible clock orderings.

    ``source_public_at`` *after* ``fetched_at`` is possible for a source that
    publishes future-dated records (e.g. a scheduled effective date typed into
    a publication field); it is reported rather than silently accepted.
    """
    problems: list[str] = []
    fetched = parse_datetime(block.get("fetched_at"))
    observed = parse_datetime(block.get("first_observed_at"))
    public = parse_date(block.get("source_public_at"))
    event = parse_date(block.get("event_at"))
    if fetched and observed and observed > fetched + timedelta(minutes=5):
        problems.append("first_observed_at is after fetched_at")
    if public and fetched and public > fetched.date() + timedelta(days=1):
        problems.append("source_public_at is in the future relative to fetched_at")
    if event and public and event.year < 1900:
        problems.append("event_at is implausibly old")
    return problems


def bucket_lead_time(days: int | None) -> str:
    """Buckets used by EXP-C.  Fixed before looking at results."""
    if days is None:
        return "undatable"
    if days < 0:
        return "after_event"
    if days <= 90:
        return "0-90d"
    if days <= 180:
        return "91-180d"
    if days <= 365:
        return "181-365d"
    if days <= 730:
        return "366-730d"
    return ">730d"
