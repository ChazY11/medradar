"""The daily digest: what arrived in the last day, and what is worth the reader's attention.

The live feed answers "what exists" and the weekly brief answers "what is deliverable". Neither
answers the question a reader actually opens the site with: "anything new that I need to look
at?". That is a different question, and it has a different answer shape - a handful of items,
not a stream, and an explicit statement when there is nothing.

Everything here is derived from records the ledger already holds: the admission decision, its
dimensions and the source state. Nothing is generated, invented or summarised by a model, so a
digest entry is always a pointer to a record that can be opened and checked.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from typing import Any, Iterable, Mapping

#: A stated public date this far ahead of today is treated as not-yet-published. Conference
#: abstracts routinely carry a future issue date; presenting one as today's news would be wrong.
FUTURE_TOLERANCE_DAYS = 7

#: Decisions the digest reports separately. EXCLUDED records are counted, never listed.
_SAFETY_SOURCES = frozenset({"openfda_recall", "openfda_device"})
_SAFETY_RECORD_TYPES = frozenset({"regulatory_record", "recall"})

_ABSTRACT_PREFIX = re.compile(r"^\s*abstract\s+[a-z]{1,3}\s*\d+\s*[:.\-]\s*", re.IGNORECASE)
_NON_WORD = re.compile(r"[^a-z0-9]+")


def _normalise_title(title: str | None, *, length: int = 64) -> str:
    """A key that collapses the same work recorded twice."""
    text = _ABSTRACT_PREFIX.sub("", str(title or ""))
    text = _NON_WORD.sub(" ", text.lower()).strip()
    return text[:length]


def _lead_days(value: str | None, today: _dt.date) -> int | None:
    """How far the stated date is ahead of today, or None when unusable."""
    text = str(value or "")[:10]
    if len(text) < 7:
        return None
    try:
        parsed = _dt.date.fromisoformat(text if len(text) == 10 else text + "-01")
    except ValueError:
        return None
    return (parsed - today).days


def _starts_with_abstract(title: str | None) -> bool:
    return bool(_ABSTRACT_PREFIX.match(str(title or "")))


def _display_title(title: str | None) -> str | None:
    """The title a reader should see: a supplement abstract prefix is not part of it."""
    if title is None:
        return None
    return _ABSTRACT_PREFIX.sub("", str(title)).strip() or str(title)


def _reasons(raw: str | None, limit: int = 2) -> list[str]:
    try:
        values = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [str(value) for value in values][:limit]


def _dimensions(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _entry(row: Mapping[str, Any], today: _dt.date) -> dict[str, Any]:
    dimensions = _dimensions(row.get("dimensions"))
    published_lead = _lead_days(row.get("published_at"), today)
    event_lead = _lead_days(row.get("event_at"), today)
    leads = [lead for lead in (published_lead, event_lead) if lead is not None]
    return {
        "observation_id": row["observation_id"],
        "title": _display_title(row.get("title")),
        "source": row.get("source"),
        "record_type": row.get("record_type"),
        "source_url": row.get("source_url"),
        "published_at": row.get("published_at"),
        "event_at": row.get("event_at"),
        "first_observed_at": row.get("first_observed_at"),
        "decision": row.get("decision"),
        "tier": row.get("tier"),
        "category": row.get("category"),
        "score": row.get("score"),
        "relevance": dimensions.get("monitoring_relevance"),
        "reasons": _reasons(row.get("reasons")),
        "future_dated": bool(leads) and max(leads) > FUTURE_TOLERANCE_DAYS,
        "duplicates": 1,
    }


def _collapse(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per work, keeping the best-scored record and counting the rest."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for entry in entries:
        key = _normalise_title(entry.get("title"))
        if not key:
            key = str(entry.get("observation_id"))
        current = merged.get(key)
        if current is None:
            merged[key] = entry
            order.append(key)
            continue
        current["duplicates"] += 1
        prefer_entry = (entry.get("score") or 0) > (current.get("score") or 0)
        if not prefer_entry and (entry.get("score") or 0) == (current.get("score") or 0):
            # Same work, same score: keep the article rather than its supplement abstract.
            prefer_entry = _starts_with_abstract(current.get("title")) and not _starts_with_abstract(
                entry.get("title"))
        if prefer_entry:
            entry["duplicates"] = current["duplicates"]
            merged[key] = entry
    return [merged[key] for key in order]


def _rank(entry: Mapping[str, Any]) -> tuple:
    return (
        1 if entry.get("future_dated") else 0,
        0 if str(entry.get("relevance") or "") == "DIRECT" else 1,
        -(float(entry.get("score") or 0)),
        str(entry.get("published_at") or entry.get("event_at") or ""),
    )


def digest(ledger, *, hours: int = 24, limit: int = 5, now: _dt.datetime | None = None) -> dict[str, Any]:
    """Build the digest for the last ``hours`` of newly observed records."""
    moment = now or _dt.datetime.now(_dt.timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_dt.timezone.utc)
    since = (moment - _dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = moment.date()

    rows = [dict(row) for row in ledger.raw(
        "SELECT o.observation_id, o.source, o.record_type, o.title, o.source_url,"
        " o.published_at, o.event_at, o.first_observed_at, o.observation_origin,"
        " o.discovery_phase, a.decision, a.tier, a.category, a.score, a.reasons, a.dimensions"
        " FROM observation o"
        " LEFT JOIN admission_current a ON a.observation_id = o.observation_id"
        " WHERE o.first_observed_at >= ?"
        " ORDER BY o.first_observed_at DESC", (since,))]

    entries = [_entry(row, today) for row in rows]
    feed = [entry for entry in entries if entry.get("decision") == "FEED"]
    review = [entry for entry in entries if entry.get("decision") == "REVIEW"]
    excluded = [entry for entry in entries if entry.get("decision") == "EXCLUDED"]

    safety = [entry for entry in feed
            if str(entry.get("source") or "") in _SAFETY_SOURCES
            or str(entry.get("record_type") or "") in _SAFETY_RECORD_TYPES]
    safety_collapsed = _collapse(safety)[:limit]
    ordinary = [entry for entry in feed if entry not in safety]
    ordinary_collapsed = sorted(_collapse(ordinary), key=_rank)
    chosen: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for entry in ordinary_collapsed:
        key = _normalise_title(entry.get("title"))
        if key in seen_titles:
            continue
        seen_titles.add(key)
        chosen.append(entry)
        if len(chosen) >= limit:
            break

    review_categories: dict[str, int] = {}
    for entry in review:
        key = str(entry.get("category") or "uncategorised")
        review_categories[key] = review_categories.get(key, 0) + 1

    future = [entry for entry in feed + review if entry.get("future_dated")]
    merged_duplicates = sum(max(0, entry["duplicates"] - 1) for entry in chosen)

    sources = [dict(row) for row in ledger.raw(
        "SELECT source_id, access_state, consecutive_failures, last_success_check_at"
        " FROM source_state ORDER BY source_id")]
    ok = [row for row in sources if str(row.get("access_state") or "") == "ENABLED"]
    blocked = [str(row["source_id"]) for row in sources
               if str(row.get("access_state") or "") == "BLOCKED"]
    failing = [str(row["source_id"]) for row in sources
               if int(row.get("consecutive_failures") or 0) >= 3]

    warnings: list[dict[str, Any]] = []
    if future:
        warnings.append({"code": "future_dated", "count": len(future)})
    if merged_duplicates:
        warnings.append({"code": "near_duplicates", "count": merged_duplicates})
    if blocked:
        warnings.append({"code": "blocked_sources", "sources": blocked})
    if failing:
        warnings.append({"code": "failing_sources", "sources": failing})
    if not feed and not review:
        warnings.append({"code": "quiet_day"})

    return {
        "schema": "medradar.radar.digest.v1",
        "generated_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {"since": since, "until": until, "hours": hours},
        "totals": {
            "arrived": len(entries),
            "feed": len(feed),
            "review": len(review),
            "excluded": len(excluded),
            "safety": len(safety),
            "duplicates_merged": merged_duplicates,
        },
        "items": chosen,
        "safety": safety_collapsed,
        "review": {
            "count": len(review),
            "categories": [{"category": key, "count": value}
                           for key, value in sorted(review_categories.items(),
                                                    key=lambda item: -item[1])],
            "examples": _collapse(review)[:3],
        },
        "sources": {"ok": len(ok), "blocked": blocked, "failing": failing, "total": len(sources)},
        "warnings": warnings,
        "empty": not entries,
    }