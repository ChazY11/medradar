"""RELEASE-GATE-001: a month is a precision, not a year.

The ledger stored `YYYY-MM` values with precision `year` because the model had no month class.
Two consequences, both measured on the production ledger (308 rows):

* the reader was told the source stated a year, when it had stated a month - a *less* precise
  claim than the truth;
* freshness is graded from the earliest instant a date can denote, so a November record was
  aged from 1 January and could be graded as ten months old.

The fix adds the month class, and derives the effective precision at read time so the rows that
are already stored (and never rewritten, because the ledger is append-only) are also corrected.
"""

from __future__ import annotations

from datetime import datetime, timezone

try:
    import pytest  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    raise unittest.SkipTest("pytest is not installed; run these tests with pytest")

from medradar.radar.assessment import _freshness, _precision_of
from medradar.radar.intelligence import _dates
from medradar.radar.records import (
    PRECISION_DATE,
    PRECISION_MONTH,
    PRECISION_UNKNOWN,
    PRECISION_YEAR,
    effective_precision,
    normalize_moment,
)


def test_a_month_is_normalised_as_a_month():
    assert normalize_moment("2026-11") == ("2026-11", PRECISION_MONTH)
    assert normalize_moment("2026") == ("2026", PRECISION_YEAR)
    assert normalize_moment("2026-11-17") == ("2026-11-17", PRECISION_DATE)


def test_an_understated_label_is_sharpened_from_the_value():
    # The production shape: value is a month, stored label says year.
    assert effective_precision("2026-11", "year") == PRECISION_MONTH
    # A value that is more specific than its label is sharpened too.
    assert effective_precision("2026-11-17", "year") == PRECISION_DATE
    # A label that is already at least as specific is never weakened.
    assert effective_precision("2026", "year") == PRECISION_YEAR
    assert effective_precision("2026-11", "date") == PRECISION_DATE
    assert effective_precision(None, "unknown") == PRECISION_UNKNOWN
    assert effective_precision("", "year") == PRECISION_YEAR
    assert effective_precision("2026-13-99", "unknown") == PRECISION_DATE


def test_freshness_ages_a_month_from_the_first_of_that_month():
    now = datetime(2026, 11, 19, tzinfo=timezone.utc)
    # With the value in hand the record is 18 days old and still fresh.
    assert _precision_of("2026-11", "year") == PRECISION_MONTH
    assert _freshness("2026-11", _precision_of("2026-11", "year"), now) == "FRESH"
    # Graded from January instead, the same record is 322 days old.
    assert _freshness("2026-11", "year", now) != "FRESH"


def test_the_brief_reports_the_precision_the_source_actually_stated():
    row = {"published_at": "2026-11", "published_at_precision": "year",
           "event_at": None, "event_at_precision": "unknown"}
    dates = _dates(row)
    assert dates["published_date_precision"] == PRECISION_MONTH
    assert dates["event_date_precision"] == PRECISION_UNKNOWN
