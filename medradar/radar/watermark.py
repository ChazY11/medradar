"""What a coverage watermark means, in one place.

The problem this fixes
----------------------
Measured on the live ledger, three sources disagreed about what their watermark meant:

  crossref          2026-11-25   today
  europepmc         2026-11-26   tomorrow - the exclusive end of a window that covers today
  openfda_device    2026-11-09   the date of the newest record found

All three are defensible on their own and ambiguous together. A reader comparing them cannot tell
whether crossref is a day ahead of openfda or behind it, and the health check could only guess: it
flagged the tomorrow values as "in the future" while the real anomaly - a watermark six days behind a
successful run - went unmentioned.

The convention
--------------
**A watermark is the exclusive upper bound of covered time.** Every moment strictly before it has
been looked at; the watermark itself has not. That is the same convention a half-open interval uses,
it makes "2026-11-26" mean "covered through the 25th", and it lets a window adapter record the end of
its window without lying.

Record-derived adapters observe an *inclusive* date - the newest record they saw - so their value is
normalised by adding a day here rather than being stored with a different meaning from everyone else.

Nothing about a watermark says a source is current. A source that found nothing new for a week
legitimately keeps an old watermark; freshness is measured separately, from the newest observation.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y/%m/%d")


def parse(value: Any) -> dt.date | dt.datetime | None:
    """A watermark as a date or datetime, or None when it is not a moment at all.

    A bare "YYYY-MM-DD" stays a date. `fromisoformat` would happily turn it into midnight and the
    difference matters: midnight is a datetime, and a datetime means "a moment we covered" rather than
    "a whole day we covered".
    """
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    for pattern in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return dt.datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def as_exclusive(value: Any, *, inclusive_observation: bool = False) -> str | None:
    """Normalise a watermark to the exclusive-end convention.

    ``inclusive_observation`` marks a value derived from the newest record found rather than from the
    end of a window: "we saw a record dated 2026-11-09" covers the 9th, so its exclusive bound is the
    10th. Window ends are already exclusive and are left alone.
    """
    moment = parse(value)
    if moment is None:
        return None if value in (None, "") else str(value)
    if isinstance(moment, dt.datetime):
        # A datetime names a moment, not a day: nothing to shift, and shifting would invent coverage.
        return moment.isoformat()
    if inclusive_observation:
        return (moment + dt.timedelta(days=1)).isoformat()
    return moment.isoformat()


def covered_through(value: Any) -> str | None:
    """The last moment a watermark claims to cover, for anything a human reads.

    A watermark of 2026-11-26 covers through 2026-11-25; printing "covers through 2026-11-26" is the
    off-by-one that made the three conventions look like a bug in the data.
    """
    moment = parse(value)
    if moment is None:
        return None
    if isinstance(moment, dt.datetime):
        if moment.time() == dt.time(0, 0):
            return (moment - dt.timedelta(days=1)).date().isoformat()
        return moment.isoformat()
    return (moment - dt.timedelta(days=1)).isoformat()


def lead_days(value: Any, *, today: dt.date | None = None) -> int | None:
    """How many days a watermark sits ahead of the given date. Negative means behind."""
    moment = parse(value)
    if moment is None:
        return None
    reference = today or dt.datetime.now(dt.timezone.utc).date()
    as_date = moment.date() if isinstance(moment, dt.datetime) else moment
    return (as_date - reference).days


def utc_today() -> dt.date:
    """Today in UTC, the clock every stored watermark is compared against.

    Adapters used `date.today()`, which is local: this host runs at UTC+8, so between 00:00 and 08:00
    local the adapters were a day ahead of the ledger they wrote into. Measured: crossref stored
    2026-11-27 as an exclusive bound while the UTC date was 2026-11-25.
    """
    return dt.datetime.now(dt.timezone.utc).date()


__all__ = ["as_exclusive", "covered_through", "lead_days", "parse", "utc_today"]
