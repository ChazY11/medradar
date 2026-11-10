"""The four clocks.

MedRadar's central temporal claim is that "when a fact happened", "when it
became publicly observable", "when we first observed it" and "when we fetched
it" are four different things, and that conflating them manufactures fake
predictive power.

This module makes the distinction executable:

* ``event_at``          — when the described real-world event occurred
                          (e.g. a patent filing date, a clearance decision).
* ``source_public_at``  — when the *source* made the record publicly visible
                          (e.g. a patent publication date, a gazette date).
* ``first_observed_at`` — the first time HORIZON saw the record.
* ``fetched_at``        — this particular retrieval.

``observability_gap_days`` is the only quantity that can legitimately enter a
retrospective study, and it is defined as
``source_public_at - event_at`` — never the other way round.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

FMT_DATE = "%Y-%m-%d"


def parse_iso(value: str | None) -> _dt.date | None:
    if not value:
        return None
    v = value.strip()
    if not v:
        return None
    # tolerate compact YYYYMMDD from patent offices
    if len(v) == 8 and v.isdigit():
        return _dt.date(int(v[0:4]), int(v[4:6]), int(v[6:8]))
    try:
        return _dt.date.fromisoformat(v[:10])
    except ValueError:
        return None


def now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ClockAudit:
    """Result of checking whether a record is allowed into a time study."""

    eligible: bool
    reason: str
    observability_gap_days: int | None
    confusion_risk: str   # "none" | "event_used_as_public" | "public_missing"

    def to_dict(self) -> dict:
        return {
            "eligible": self.eligible,
            "reason": self.reason,
            "observability_gap_days": self.observability_gap_days,
            "confusion_risk": self.confusion_risk,
        }


def audit_clocks(event_at: str | None, source_public_at: str | None) -> ClockAudit:
    """Decide whether a record can support a historical-observability claim.

    Rules:
    * no ``source_public_at`` -> NOT eligible. We cannot know when a human
      could have seen it, so any "early signal" claim on it is unfalsifiable.
    * ``source_public_at`` before ``event_at`` -> the record became public *before*
      the event it describes. This is **not** an error: a trial is registered
      before it starts, and a DOI is registered before the issue date. It is
      still NOT eligible for "the event was observable at publication", because
      the event had not happened yet. It is reported separately so the pattern is
      visible rather than silently bracketed with genuine data errors.
    * otherwise eligible, with the gap reported.
    """
    ev = parse_iso(event_at)
    pub = parse_iso(source_public_at)
    if pub is None:
        return ClockAudit(
            eligible=False,
            reason="no source_public_at: record cannot be placed on the observability timeline",
            observability_gap_days=None,
            confusion_risk="public_missing",
        )
    if ev is None:
        return ClockAudit(
            eligible=True,
            reason="public date known, event date unknown: usable as publication observation only",
            observability_gap_days=None,
            confusion_risk="none",
        )
    gap = (pub - ev).days
    if gap < 0:
        return ClockAudit(
            eligible=False,
            reason=(
                f"record became public {-gap} days BEFORE the event it describes "
                f"(prospective registration / early DOI registration); the event was "
                f"not yet observable, so the record cannot date it"
            ),
            observability_gap_days=gap,
            confusion_risk="event_after_publication",
        )
    return ClockAudit(
        eligible=True,
        reason="both clocks present and ordered",
        observability_gap_days=gap,
        confusion_risk="none",
    )


def classify_record(event_at, source_public_at) -> dict:
    """Compact, serialisable classification used in EXP-H3."""
    a = audit_clocks(event_at, source_public_at)
    d = a.to_dict()
    if a.eligible and a.observability_gap_days is not None:
        d["class"] = "FULL_TWO_CLOCK"
    elif a.eligible:
        d["class"] = "PUBLICATION_ONLY"
    elif a.confusion_risk == "public_missing":
        d["class"] = "EVENT_ONLY"
    else:
        d["class"] = "PUBLICATION_BEFORE_EVENT"
    return d
