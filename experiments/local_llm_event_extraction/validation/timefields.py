"""Timestamp semantics: parsing, quality/value consistency, and evidence support.

Three timestamps, three different meanings
------------------------------------------
``schema.py`` separates the date the real-world event happened
(``event_date``), the date the source published it (``published_at``) and the
date *our collector* first observed it (``first_seen_at``).  The validator treats
them differently on purpose:

* ``event_date`` and ``published_at`` are *assertions about the world* and must
  be traceable to the source: an asserted date has to appear in some evidence
  quote at the claimed precision (``DATE_NOT_IN_EVIDENCE``).
* ``first_seen_at`` is *our own metadata*.  The model has no way to know it, so
  any value that differs from the source document's record is rejected
  (``FIRST_SEEN_MISMATCH``) rather than compared for plausibility.

Quality is asserted, never inferred
-----------------------------------
The ``timestamp_quality`` field says how precise the claim is, and the value has
to be consistent with it: ``absent`` means a null value (and a null value means
``absent``); ``exact_day`` needs ``YYYY-MM-DD``; ``exact_month`` needs
``YYYY-MM``; ``exact_year`` needs ``YYYY``; ``approximate``/``conflicting``
accept any parseable value.  Recording a day-level value as ``exact_month`` is
reported as a contradiction rather than quietly upgraded.

``conflicting`` is the one enum value that may accompany a null value: the
schema documents it as "the source states more than one incompatible date and
the extractor refuses to pick".  That is the single documented exception to
"``absent`` iff ``None``".

Dates in free text
------------------
:func:`dates_in_text` recognises unambiguous date tokens: ISO ``YYYY-MM-DD`` /
``YYYY-MM`` / ``YYYY``, English month-name forms (``May 12, 2023``,
``12 March 2024``, ``May 2023``).  Numeric slash formats (``05/12/2023``) are
deliberately **not** recognised: day-first and month-first are indistinguishable
without a locale, and guessing would make the date metric depend on the guess.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..contracts import Severity, ValidationConfig, ValidationIssue
from ..schema import TIMESTAMP_FIELDS, TIMESTAMP_QUALITIES

__all__ = [
    "ParsedDate",
    "DateToken",
    "PRECISION_ORDER",
    "parse_date_value",
    "dates_in_text",
    "date_supports",
    "supporting_tokens",
    "check_timestamp_quality",
    "check_event_timestamps",
    "resolve_as_of",
]

PRECISION_ORDER: Mapping[str, int] = {"year": 1, "month": 2, "day": 3}
"""How much information a precision carries (bigger = more precise)."""

_QUALITY_TO_PRECISION: Mapping[str, str] = {
    "exact_day": "day",
    "exact_month": "month",
    "exact_year": "year",
}

_ISO_FULL = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_ISO_MONTH = re.compile(r"(?<!\d)(\d{4})-(\d{2})(?!\d)")
_ISO_YEAR = re.compile(r"(?<!\d)(\d{4})(?!\d)")

MONTH_NUMBERS: Mapping[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

_MONTH_ALTERNATION = "|".join(sorted(MONTH_NUMBERS, key=len, reverse=True))
_MONTH_DAY_YEAR = re.compile(
    rf"(?<!\w)({_MONTH_ALTERNATION})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})(?!\d)",
    re.IGNORECASE,
)
_DAY_MONTH_YEAR = re.compile(
    rf"(?<!\w)(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_ALTERNATION})\.?,?\s+(\d{{4}})(?!\d)",
    re.IGNORECASE,
)
_MONTH_YEAR = re.compile(
    rf"(?<!\w)({_MONTH_ALTERNATION})\.?,?\s+(\d{{4}})(?!\d)",
    re.IGNORECASE,
)


# ------------------------------------------------------------------ date values
def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _is_valid_date(year: int, month: int, day: int) -> bool:
    if not 1 <= month <= 12:
        return False
    if year < 1:
        return False
    return 1 <= day <= _days_in_month(year, month)


@dataclass(frozen=True)
class ParsedDate:
    """A parsed date at a declared precision (no time-zone, no time of day)."""

    year: int
    month: int | None = None
    day: int | None = None
    precision: str = "year"

    def __post_init__(self) -> None:
        if self.precision not in PRECISION_ORDER:
            raise ValueError(f"unknown date precision {self.precision!r}")
        if self.precision == "day" and (self.month is None or self.day is None):
            raise ValueError("day precision requires month and day")
        if self.precision == "month" and self.month is None:
            raise ValueError("month precision requires month")
        if self.precision == "year" and (self.month is not None or self.day is not None):
            raise ValueError("year precision must not carry a month or day")

    @property
    def iso(self) -> str:
        if self.precision == "day":
            return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"
        if self.precision == "month":
            return f"{self.year:04d}-{self.month:02d}"
        return f"{self.year:04d}"

    @property
    def quality(self) -> str:
        return {"day": "exact_day", "month": "exact_month", "year": "exact_year"}[self.precision]

    def earliest(self) -> tuple[int, int, int]:
        """Earliest calendar instant this value could denote."""
        return (self.year, self.month or 1, self.day or 1)

    def latest(self) -> tuple[int, int, int]:
        """Latest calendar instant this value could denote."""
        month = self.month or 12
        day = self.day or _days_in_month(self.year, month)
        return (self.year, month, day)

    def to_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "month": self.month,
            "day": self.day,
            "precision": self.precision,
            "iso": self.iso,
        }


def parse_date_value(value: str | None) -> ParsedDate | None:
    """Strictly parse ``YYYY-MM-DD``, ``YYYY-MM`` or ``YYYY``; else ``None``.

    Calendar validity is checked (``2023-02-30`` is not a date), and a value with
    surrounding whitespace is rejected rather than trimmed: the schema pattern
    already forbids it, and silently repairing it would hide a model bug.
    """
    if not isinstance(value, str):
        return None
    match = _ISO_FULL.fullmatch(value)
    if match is not None:
        year, month, day = (int(part) for part in match.groups())
        if not _is_valid_date(year, month, day):
            return None
        return ParsedDate(year=year, month=month, day=day, precision="day")
    match = _ISO_MONTH.fullmatch(value)
    if match is not None:
        year, month = (int(part) for part in match.groups())
        if not 1 <= month <= 12 or year < 1:
            return None
        return ParsedDate(year=year, month=month, precision="month")
    match = _ISO_YEAR.fullmatch(value)
    if match is not None:
        year = int(match.group(1))
        if year < 1:
            return None
        return ParsedDate(year=year, precision="year")
    return None


# ------------------------------------------------------------------ text tokens
@dataclass(frozen=True)
class DateToken:
    """A date recognised inside free text, with its raw span and precision."""

    text: str
    start: int
    end: int
    date: ParsedDate

    @property
    def year(self) -> int:
        return self.date.year

    @property
    def month(self) -> int | None:
        return self.date.month

    @property
    def day(self) -> int | None:
        return self.date.day

    @property
    def precision(self) -> str:
        return self.date.precision

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "date": self.date.iso,
            "precision": self.precision,
        }


def _candidate_tokens(text: str) -> list[DateToken]:
    candidates: list[DateToken] = []

    def add(start: int, end: int, parsed: ParsedDate | None) -> None:
        if parsed is not None:
            candidates.append(DateToken(text=text[start:end], start=start, end=end, date=parsed))

    for match in _ISO_FULL.finditer(text):
        year, month, day = (int(part) for part in match.groups())
        if _is_valid_date(year, month, day):
            add(match.start(), match.end(), ParsedDate(year, month, day, "day"))
    for match in _ISO_MONTH.finditer(text):
        year, month = (int(part) for part in match.groups())
        if 1 <= month <= 12 and year >= 1:
            add(match.start(), match.end(), ParsedDate(year, month, precision="month"))
    for match in _ISO_YEAR.finditer(text):
        year = int(match.group(1))
        if year >= 1:
            add(match.start(), match.end(), ParsedDate(year, precision="year"))
    for match in _MONTH_DAY_YEAR.finditer(text):
        month = MONTH_NUMBERS[match.group(1).lower()]
        day, year = int(match.group(2)), int(match.group(3))
        if _is_valid_date(year, month, day):
            add(match.start(), match.end(), ParsedDate(year, month, day, "day"))
    for match in _DAY_MONTH_YEAR.finditer(text):
        day = int(match.group(1))
        month = MONTH_NUMBERS[match.group(2).lower()]
        year = int(match.group(3))
        if _is_valid_date(year, month, day):
            add(match.start(), match.end(), ParsedDate(year, month, day, "day"))
    for match in _MONTH_YEAR.finditer(text):
        month = MONTH_NUMBERS[match.group(1).lower()]
        year = int(match.group(2))
        if year >= 1:
            add(match.start(), match.end(), ParsedDate(year, month, precision="month"))
    return candidates


def dates_in_text(text: str) -> tuple[DateToken, ...]:
    """Every recognisable date token in ``text``, in source order.

    Overlapping matches are resolved in favour of the longest token, so
    ``2023-05-12`` yields one day-precision token, not a day token plus its year.
    """
    if not isinstance(text, str) or not text:
        return ()
    candidates = _candidate_tokens(text)
    # Longest first, then leftmost; drop anything overlapping an accepted token.
    ordered = sorted(candidates, key=lambda token: (token.start, -(token.end - token.start), token.end))
    accepted: list[DateToken] = []
    for token in ordered:
        if any(token.start < kept.end and kept.start < token.end for kept in accepted):
            continue
        accepted.append(token)
    accepted.sort(key=lambda token: (token.start, token.end))
    return tuple(accepted)


# ------------------------------------------------------------------ support
def date_supports(known: ParsedDate, claimed: ParsedDate) -> bool:
    """True when ``known`` entails ``claimed`` at the claimed precision."""
    if claimed.precision == "year":
        return known.year == claimed.year
    if claimed.precision == "month":
        return known.month is not None and known.year == claimed.year and known.month == claimed.month
    return (
        known.day is not None
        and known.year == claimed.year
        and known.month == claimed.month
        and known.day == claimed.day
    )


def supporting_tokens(claimed: ParsedDate, texts: Sequence[str]) -> tuple[DateToken, ...]:
    """Every token across ``texts`` that supports the claimed date."""
    found: list[DateToken] = []
    for text in texts:
        for token in dates_in_text(text):
            if date_supports(token.date, claimed):
                found.append(token)
    return tuple(found)


# ------------------------------------------------------------------ consistency
def _issue(
    code: str,
    field: str,
    detail: str,
    *,
    severity: Severity = Severity.ERROR,
) -> ValidationIssue:
    return ValidationIssue(code=code, severity=severity, field=field, detail=detail)


def check_timestamp_quality(field: str, value: Any, quality: Any) -> tuple[ValidationIssue, ...]:
    """Check one timestamp's value against its asserted quality."""
    if quality not in TIMESTAMP_QUALITIES:
        return (
            _issue(
                "DATE_QUALITY_MISMATCH",
                field,
                f"{field} has unknown timestamp quality {quality!r}; declared qualities are "
                f"{list(TIMESTAMP_QUALITIES)}",
            ),
        )
    if value is None:
        if quality not in ("absent", "conflicting"):
            return (
                _issue(
                    "DATE_QUALITY_MISMATCH",
                    field,
                    f"{field} is null but quality is {quality!r}; a null value must be recorded "
                    "as 'absent' (or 'conflicting' when the source is contradictory)",
                ),
            )
        return ()
    if not isinstance(value, str):
        return (
            _issue(
                "DATE_QUALITY_MISMATCH",
                field,
                f"{field} must be a string or null, got {type(value).__name__}",
            ),
        )
    if quality == "absent":
        return (
            _issue(
                "DATE_QUALITY_MISMATCH",
                field,
                f"{field} is {value!r} but quality is 'absent'; absence must not carry a value",
            ),
        )
    parsed = parse_date_value(value)
    if parsed is None:
        return (
            _issue(
                "DATE_QUALITY_MISMATCH",
                field,
                f"{field} value {value!r} is not a valid YYYY-MM-DD, YYYY-MM or YYYY date",
            ),
        )
    expected = _QUALITY_TO_PRECISION.get(quality)
    if expected is not None and parsed.precision != expected:
        return (
            _issue(
                "DATE_QUALITY_MISMATCH",
                field,
                f"{field} quality {quality!r} requires a {expected}-precision value; "
                f"{value!r} has {parsed.precision} precision",
            ),
        )
    return ()


def resolve_as_of(config: ValidationConfig, document: Any = None) -> ParsedDate | None:
    """Resolve the ``as_of`` boundary used by the future-date check.

    The frozen ``ValidationConfig`` has no ``as_of`` field, so the boundary is
    read from ``config.as_of`` when a caller supplies an extended config, else
    from ``document.metadata["as_of"]``.  When neither exists the future check is
    skipped: defaulting to "today" would make validation time-dependent and
    therefore irreproducible.
    """
    raw = getattr(config, "as_of", None)
    if raw is None and document is not None:
        metadata = getattr(document, "metadata", None) or {}
        if isinstance(metadata, Mapping):
            raw = metadata.get("as_of")
    if raw is None:
        return None
    if isinstance(raw, ParsedDate):
        return raw
    parsed = parse_date_value(str(raw))
    if parsed is None:
        raise ValueError(
            f"as_of {raw!r} is not a valid YYYY-MM-DD/YYYY-MM/YYYY date; the future-date "
            "check needs a real boundary"
        )
    return parsed


def check_event_timestamps(
    event: Mapping[str, Any],
    *,
    document: Any,
    config: ValidationConfig,
    as_of: ParsedDate | None = None,
) -> tuple[ValidationIssue, ...]:
    """All timestamp findings for one event payload (fixed order, deterministic)."""
    issues: list[ValidationIssue] = []
    raw_qualities = event.get("timestamp_quality")
    qualities: Mapping[str, Any] = raw_qualities if isinstance(raw_qualities, Mapping) else {}
    values: dict[str, Any] = {field: event.get(field) for field in TIMESTAMP_FIELDS}
    parsed: dict[str, ParsedDate | None] = {}

    # 1. value/quality consistency for every timestamp field.
    for field in TIMESTAMP_FIELDS:
        field_issues = check_timestamp_quality(field, values[field], qualities.get(field))
        issues.extend(field_issues)
        parsed[field] = parse_date_value(values[field]) if not field_issues else None

    evidence_texts = tuple(
        span.get("quote")
        for span in (event.get("evidence") or ())
        if isinstance(span, Mapping) and isinstance(span.get("quote"), str)
    )

    # 2. an asserted event_date must be traceable to an evidence quote.
    event_date = parsed.get("event_date")
    if event_date is not None and config.require_date_supported_by_quote:
        if not supporting_tokens(event_date, evidence_texts):
            issues.append(
                _issue(
                    "DATE_NOT_IN_EVIDENCE",
                    "event_date",
                    f"event_date {event_date.iso!r} (precision {event_date.precision}) does not "
                    "appear in any evidence quote at that precision",
                )
            )

    # 3. published_at may additionally come from document metadata: it is a
    #    property of the document, not of the quote.
    published = parsed.get("published_at")
    if published is not None and config.require_date_supported_by_quote:
        quoted = supporting_tokens(published, evidence_texts)
        metadata_match = False
        document_published = getattr(document, "published_at", None)
        document_parsed = parse_date_value(document_published) if isinstance(document_published, str) else None
        if document_parsed is not None and date_supports(document_parsed, published):
            metadata_match = True
        if not quoted and not metadata_match:
            issues.append(
                _issue(
                    "DATE_NOT_IN_EVIDENCE",
                    "published_at",
                    f"published_at {published.iso!r} is neither in an evidence quote nor equal to "
                    "the source document's published_at",
                )
            )

    # 4. event_date <= published_at unless the extractor declares uncertainty or
    #    the (extended) config explicitly allows an event after its publication.
    if event_date is not None and published is not None:
        allow_after = bool(getattr(config, "allow_event_after_published", False))
        declared_uncertain = qualities.get("event_date") in ("approximate", "conflicting")
        if not allow_after and not declared_uncertain and event_date.earliest() > published.latest():
            fatal = bool(getattr(config, "date_order_violation_fatal", False))
            issues.append(
                _issue(
                    "DATE_ORDER_VIOLATION",
                    "event_date",
                    f"event_date {event_date.iso!r} is after published_at {published.iso!r}; "
                    "a document cannot publish an event before it happened",
                    severity=Severity.ERROR if fatal else Severity.WARNING,
                )
            )

    # 5. no dates beyond the supplied as_of boundary.
    if as_of is not None and config.reject_future_dates:
        boundary = as_of.latest()
        for field in ("event_date", "published_at"):
            value = parsed.get(field)
            if value is not None and value.earliest() > boundary:
                issues.append(
                    _issue(
                        "DATE_IN_FUTURE",
                        field,
                        f"{field} {value.iso!r} is after the configured as_of date {as_of.iso!r}",
                    )
                )

    # 6. first_seen_at is collector metadata: it must equal the document record.
    first_seen_value = values.get("first_seen_at")
    if first_seen_value is not None:
        expected = getattr(document, "first_seen_at", None)
        if first_seen_value != expected:
            severity = (
                Severity.ERROR if config.reject_model_invented_first_seen else Severity.WARNING
            )
            issues.append(
                _issue(
                    "FIRST_SEEN_MISMATCH",
                    "first_seen_at",
                    f"first_seen_at {first_seen_value!r} differs from the source document's "
                    f"first_seen_at {expected!r}; it is system metadata, not model knowledge",
                    severity=severity,
                )
            )
    return tuple(issues)
