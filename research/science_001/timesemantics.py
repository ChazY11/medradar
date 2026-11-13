"""EDGAR time semantics: what each timestamp field can and cannot support.

The scientific model this module implements
-------------------------------------------
Four times are kept strictly apart. They are never copied into each other.

  event time          when the described commercial/technical event happened
                      (8-K: CONFORMED PERIOD OF REPORT / reportDate)
  filing acceptance   when EDGAR's system accepted the submission
                      (raw header ACCEPTANCE-DATETIME, US/Eastern wall clock)
  public availability when an outside party could retrieve the content
                      (no SEC-published field exists; bounded, never asserted)
  first observation   when MedRadar actually fetched it (collection time)

Empirical basis for "ACCEPTANCE-DATETIME is US/Eastern wall clock"
-----------------------------------------------------------------
Verified here, not assumed: for every filing in the verification strata the
raw header value, interpreted as America/New_York, converts to exactly the
data.sec.gov acceptanceDateTime instant (offset exactly -4h in EDT and -5h in
EST, tracking the DST transitions). Confidence shows up as the *distribution*
of the residual: residual == 0 s for the Eastern interpretation, and a
240/300-minute residual for the "the raw field is already UTC" interpretation.

Why a hand-written DST rule instead of zoneinfo
-----------------------------------------------
Three reasons. (1) Reproducibility: Windows installations frequently have no
IANA database, so zoneinfo may raise; the study must not depend on that.
(2) Auditability: the offset rule is the object of study, so it belongs in the
code in front of the reader. (3) Determinism: no tz-database updates can change
a published result. The rule is cross-checked against zoneinfo when available
(see tests).
"""

from __future__ import annotations

import datetime as dt
import email.utils
from dataclasses import dataclass
from typing import Any

UTC = dt.timezone.utc

# --------------------------------------------------------------------------- #
# US Eastern offset rule (no tz database required)
# --------------------------------------------------------------------------- #
def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """The n-th (1-based) given weekday (Mon=0) of a month."""
    day = dt.date(year, month, 1)
    shift = (weekday - day.weekday()) % 7
    return day + dt.timedelta(days=shift + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    day = dt.date(year, month, 1)
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def dst_bounds_utc(year: int) -> tuple[dt.datetime, dt.datetime]:
    """Daylight saving start/end instants for a year, as naive US/Eastern.

    Since 2007 (Energy Policy Act 2005): DST starts the second Sunday in March
    at 02:00 local standard time and ends the first Sunday in November at
    02:00 local daylight time. Before 2007: first Sunday April / last Sunday
    October. Filings in this study start in 2017, but the older rule is kept so
    a pre-2007 extension cannot silently produce a wrong offset.
    """
    if year >= 2007:
        start = _nth_weekday(year, 3, 6, 2)
        end = _nth_weekday(year, 11, 6, 1)
    else:
        start = _nth_weekday(year, 4, 6, 1)
        end = _last_weekday(year, 10, 6)
    return (
        dt.datetime.combine(start, dt.time(2, 0)),
        dt.datetime.combine(end, dt.time(2, 0)),
    )


def eastern_utc_offset_hours(local_naive: dt.datetime) -> int:
    """UTC offset in hours for a US/Eastern wall-clock value: -4 (EDT) or -5.

    For a wall-clock value inside the repeated autumn hour this returns -4, the
    first (daylight) occurrence. Callers that need a conservative instant must
    check local_time_status() first; see parse_header_acceptance().
    """
    start, end = dst_bounds_utc(local_naive.year)
    return -4 if start <= local_naive < end else -5


class LocalTimeStatus:
    UNIQUE = "unique"
    AMBIGUOUS = "ambiguous"        # repeated hour on the autumn transition
    NONEXISTENT = "nonexistent"    # skipped hour on the spring transition


def local_time_status(local_naive: dt.datetime) -> str:
    """Flag wall-clock values that DST makes ambiguous or impossible."""
    start, end = dst_bounds_utc(local_naive.year)
    # Spring forward: the clock jumps 02:00 -> 03:00, so [start, start+1h)
    # never occurs.
    if start <= local_naive < start + dt.timedelta(hours=1):
        return LocalTimeStatus.NONEXISTENT
    # Autumn fall-back: the clock repeats 01:00 -> 01:59, so the hour before
    # the recorded end instant is ambiguous for a wall-clock reader.
    if end - dt.timedelta(hours=1) <= local_naive < end:
        return LocalTimeStatus.AMBIGUOUS
    return LocalTimeStatus.UNIQUE


# --------------------------------------------------------------------------- #
# header -> UTC
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AcceptanceTime:
    raw: str
    local_naive: dt.datetime
    utc: dt.datetime
    offset_hours: int
    local_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "acceptance_raw": self.raw,
            "acceptance_local_naive": self.local_naive.strftime("%Y-%m-%dT%H:%M:%S"),
            "acceptance_utc": self.utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "offset_hours": self.offset_hours,
            "local_time_status": self.local_status,
        }


def parse_header_acceptance(raw: str) -> AcceptanceTime:
    """Convert a raw YYYYMMDDHHMMSS header value (US/Eastern) to a UTC instant."""
    if not raw or not raw.isdigit() or len(raw) != 14:
        raise ValueError("not a 14-digit EDGAR ACCEPTANCE-DATETIME: %r" % (raw,))
    local = dt.datetime.strptime(raw, "%Y%m%d%H%M%S")
    status = local_time_status(local)
    # eastern_utc_offset_hours() reports the daylight (-4) reading for the
    # repeated autumn hour, which is the FIRST occurrence. For a point-in-time
    # claim we must take the LATER reading (-5): "public by T" may then be too
    # pessimistic, never too optimistic.
    offset = -5 if status == LocalTimeStatus.AMBIGUOUS else eastern_utc_offset_hours(local)
    # For the ambiguous autumn hour the standard-time reading (-5) is the
    # conservative choice: it yields the LATER UTC instant, so a claim of
    # "public by T" can only be too pessimistic, never too optimistic.
    utc = (local.replace(tzinfo=dt.timezone(dt.timedelta(hours=offset)))
                .astimezone(UTC).replace(tzinfo=None))
    return AcceptanceTime(raw, local, utc, offset, status)


def parse_api_acceptance(value: str | None) -> dt.datetime | None:
    """Parse data.sec.gov acceptanceDateTime (ISO-8601 with a Z suffix)."""
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0, tzinfo=None)


def parse_http_date(value: str | None) -> dt.datetime | None:
    """Parse an HTTP Last-Modified / Date header into a naive UTC instant."""
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0, tzinfo=None)


# --------------------------------------------------------------------------- #
# evidence grades
# --------------------------------------------------------------------------- #
#: Every grade names exactly what it supports. A grade is never a probability.
TIERS: dict[str, dict[str, Any]] = {
    "A_acceptance_verified": {
        "label": "A",
        "meaning": ("Raw header ACCEPTANCE-DATETIME (US/Eastern) is present and its"
                    " DST-correct conversion equals data.sec.gov acceptanceDateTime."),
        "supports": [
            "the filing was accepted by EDGAR no later than this UTC instant",
            "intraday ordering of filings by this issuer",
            "a lower bound for public availability",
        ],
        "does_not_support": [
            "that the content was retrievable by an outsider at this instant",
            "that the market had processed it",
            "any claim about when the described event happened",
        ],
    },
    "A2_acceptance_header_only": {
        "label": "A2",
        "meaning": ("Raw header present; API value absent or inconsistent."
                    " The UTC instant is derived from the header alone."),
        "supports": ["same as A, against the primitive field only"],
        "does_not_support": ["independent corroboration by a second SEC field"],
    },
    "B_acceptance_api_only": {
        "label": "B",
        "meaning": "Only the API acceptanceDateTime is available; no raw header read.",
        "supports": ["a SEC-supplied acceptance instant, unverified against the archive"],
        "does_not_support": ["verification of the field's encoding or offset"],
    },
    "C_filing_date_only": {
        "label": "C",
        "meaning": "Only the calendar filingDate (US/Eastern day) is available.",
        "supports": ["day-level membership: the filing is dated this Eastern day"],
        "does_not_support": ["any intraday ordering", "an exact availability instant"],
    },
    "D_unknown": {
        "label": "D",
        "meaning": "No usable time field. Must be excluded from timed analysis.",
        "supports": [],
        "does_not_support": ["any point-in-time claim"],
    },
}


def grade_filing(header_present: bool, header_raw: str | None,
                 api_value: str | None, filing_date: str | None) -> dict[str, Any]:
    """Assign the evidence grade for one filing's *acceptance* instant."""
    if header_present and header_raw:
        try:
            acceptance = parse_header_acceptance(header_raw)
        except ValueError:
            return {"tier": "D_unknown", "reason": "unparseable header acceptance value"}
        api_utc = parse_api_acceptance(api_value)
        record = acceptance.as_dict()
        record["api_acceptance_utc"] = (api_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                                        if api_utc else None)
        if api_utc is None:
            record.update(tier="A2_acceptance_header_only", residual_seconds=None,
                          reason="no API acceptanceDateTime to cross-check")
            return record
        residual = int((api_utc - acceptance.utc).total_seconds())
        record["residual_seconds"] = residual
        if residual == 0:
            record.update(tier="A_acceptance_verified",
                          reason="header->UTC equals API instant exactly")
        else:
            record.update(tier="A2_acceptance_header_only",
                          reason="header and API disagree by %d s" % residual)
        return record
    if api_value:
        api_utc = parse_api_acceptance(api_value)
        return {
            "tier": "B_acceptance_api_only",
            "acceptance_utc": api_utc.strftime("%Y-%m-%dT%H:%M:%SZ") if api_utc else None,
            "api_acceptance_utc": api_utc.strftime("%Y-%m-%dT%H:%M:%SZ") if api_utc else None,
            "acceptance_raw": None,
            "reason": "raw header not read",
        }
    if filing_date:
        return {"tier": "C_filing_date_only", "filing_date": filing_date,
                "reason": "only calendar filingDate available"}
    return {"tier": "D_unknown", "reason": "no time field at all"}


# --------------------------------------------------------------------------- #
# public availability bounds
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AvailabilityBounds:
    """A *bounded* claim about public availability, never a point estimate."""

    not_before_utc: dt.datetime           # acceptance: content cannot precede this
    not_after_utc: dt.datetime | None     # archival Last-Modified: file existed by then
    basis: str
    lag_seconds: int | None = None

    @property
    def bounded(self) -> bool:
        return self.not_after_utc is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "public_not_before_utc": self.not_before_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "public_not_after_utc": (self.not_after_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                                     if self.not_after_utc else None),
            "public_interval_seconds": self.lag_seconds,
            "public_interval_basis": self.basis,
            "public_interval_bounded": self.bounded,
        }


def availability_bounds(acceptance_utc: dt.datetime,
                        last_modified_utc: dt.datetime | None,
                        filing_date: str | None = None) -> AvailabilityBounds:
    """Bound public availability using only SEC-side evidence.

    EDGAR publishes no dissemination timestamp. The archival Last-Modified of
    the document is the earliest server-side moment we can *prove* the bytes
    existed in the public archive; acceptance is the moment they cannot have
    preceded. The interval between them is therefore a measured bandwidth
    around the true (unobserved) dissemination instant, not a proxy for it.
    """
    if last_modified_utc is not None:
        lag = int((last_modified_utc - acceptance_utc).total_seconds())
        return AvailabilityBounds(acceptance_utc, last_modified_utc,
                                  "acceptance..archival Last-Modified", lag)
    not_after = None
    basis = "acceptance only (Lower bound)"
    if filing_date:
        try:
            day = dt.date.fromisoformat(filing_date)
            # end of the Eastern calendar day, expressed in UTC (max offset +5h)
            not_after = dt.datetime.combine(day, dt.time(23, 59, 59)) + dt.timedelta(hours=5)
            basis = "acceptance..end of filingDate (Eastern day)"
        except ValueError:
            pass
    return AvailabilityBounds(acceptance_utc, not_after, basis,
                              int((not_after - acceptance_utc).total_seconds())
                              if not_after else None)
