"""Canonical shapes for the recruitment lane (Phase 4 · Innovation Signals Observatory).

Why this module exists
----------------------
The Live Observatory (`medradar.observatory`) records *what a source said and when
we first saw it*. A job posting needs the same discipline plus three fields no
regulatory record has:

  * a **posting identity** that survives re-publication, multi-city copies and
    career-site migrations;
  * a **source publication time** whose quality is stated, because career sites
    publish absolute dates on some platforms and only "Posted 29 Days Ago" on
    others. Converting that relative string into a date would manufacture a
    timestamp, so this module refuses to do it;
  * an explicit **collection status**, so "we could not read the description" is
    never stored as "the posting has no description".

Rules encoded here
------------------
* ``source_posted_at`` is only ever a value the *source* published, with the
  precision it published it at. ``RELATIVE_ONLY`` means we have an ordering hint
  and no date; it must never be turned into one.
* ``first_seen_at`` is written once, by our clock, and never overwritten — a
  later run that observes the same posting is a *re-observation*, not a new
  posting and not a new date.
* ``content_sha256`` is a hash of the *normalised* job content (title + location
  + description text), so a whitespace-only re-render is not a revision, while a
  changed requirement sentence is.
* Every field that can be absent is allowed to be ``None``; there is no default
  that fills in a plausible value.

This module is pure: no network, no database. Collection lives in
``medradar/recruitment/workday.py`` (and per-platform siblings); storage lives in
``medradar/recruitment/store.py``.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

SCHEMA_VERSION = "recruitment-obs-v1"
COLLECTOR_VERSION = "recruitment/1.0.0"
#: Version of the *content-hash rule*, not of the record schema. A content hash is only
#: comparable between two observations that were hashed by the same rule: changing the
#: normalisation changes every hash at once, and without this field such a change is
#: indistinguishable from "every posting was edited overnight". The store refuses to
#: report REVISION across a rule change and records a re-baseline instead.
HASH_RULE_VERSION = "content_sha256_canonical_ws_v2"

# --------------------------------------------------------------------- platforms
PLATFORM_WORKDAY = "workday"
PLATFORM_PHENOM = "phenom"
PLATFORM_BEISEN = "beisen"
#: Dräger publishes through an e-recruitment portal ("Beesite") rather than one of the
#: three platforms above. The value is explicit rather than folded into "phenom" because
#: a source platform is part of a record's provenance: two different platforms behave
#: differently (pagination, id scheme, date field), and a later reader must be able to
#: tell which contract the record was parsed under.
PLATFORM_BEESITE = "beesite"
PLATFORMS = (PLATFORM_WORKDAY, PLATFORM_PHENOM, PLATFORM_BEISEN, PLATFORM_BEESITE)

# ---------------------------------------------------------------- time semantics
#: The source published a full date (``2026-10-06``). Precision: day.
QUALITY_SOURCE_DATE = "SOURCE_DATE"
#: The source published a date-time with a timezone. Precision: second.
QUALITY_SOURCE_DATETIME = "SOURCE_DATETIME"
#: The source published a *relative* string ("Posted 29 Days Ago"). This is an
#: ordering hint with a coarse bucket, **not** a date. Never converted.
QUALITY_RELATIVE_ONLY = "RELATIVE_ONLY"
#: The source published nothing usable about when the posting went live.
QUALITY_NONE = "NONE"
TIME_QUALITIES = (QUALITY_SOURCE_DATE, QUALITY_SOURCE_DATETIME, QUALITY_RELATIVE_ONLY, QUALITY_NONE)

#: Buckets for a relative string, kept as data rather than as an estimate.
RELATIVE_BUCKETS = {
    "today": "same_day",
    "yesterday": "previous_day",
    "days ago": "days",
    "30+ days ago": "thirty_plus_days",
    "hours ago": "hours",
}

# --------------------------------------------------------------- collection status
STATUS_COMPLETE = "COMPLETE"            # listing + detail + non-empty description
STATUS_NO_DESCRIPTION = "NO_DESCRIPTION"  # detail read, description empty/absent
STATUS_DETAIL_FAILED = "DETAIL_FAILED"    # listing seen, detail request failed
STATUS_LISTING_ONLY = "LISTING_ONLY"      # discovered from a sitemap/listing, no detail read
STATUS_BLOCKED = "BLOCKED"                # source refused or robots disallows
STATUSES = (STATUS_COMPLETE, STATUS_NO_DESCRIPTION, STATUS_DETAIL_FAILED,
            STATUS_LISTING_ONLY, STATUS_BLOCKED)

# --------------------------------------------------------------- entity resolution
#: A posting names an employer brand, not a registered legal entity. These status
#: values keep that distinction visible instead of guessing a subsidiary.
ENTITY_STATUS_COMPANY_KEY = "COMPANY_KEY_ONLY"      # mapped to a focus-company key
ENTITY_STATUS_CANONICAL = "CANONICAL_ENTITY"        # mapped to a universe entity key
ENTITY_STATUS_AMBIGUOUS = "AMBIGUOUS"
ENTITY_STATUS_UNRESOLVED = "UNRESOLVED"


def utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_RELATIVE_RE = re.compile(r"posted\s+(?P<value>today|yesterday|\d+\+?\s*(?:days?|hours?)\s+ago)", re.I)
_WS_RE = re.compile(r"[ \t\u00a0]+")
_NEWLINE_RE = re.compile(r"\n{3,}")


def parse_relative_posted(text: str | None) -> dict[str, Any]:
    """Classify a career-site "posted" string without inventing a date.

    ``"Posted 29 Days Ago"`` becomes ``{"bucket": "days", "value_days": 29}`` with
    quality ``RELATIVE_ONLY``; it does **not** become ``2026-10-06``. Downstream
    code may use the bucket to order postings *within one collection snapshot*;
    it may not use it as a posting date or as a first-seen time.
    """
    if not text:
        return {"raw": text, "bucket": None, "value_days": None, "quality": QUALITY_NONE}
    match = _RELATIVE_RE.search(text)
    if not match:
        return {"raw": text, "bucket": None, "value_days": None, "quality": QUALITY_NONE}
    value = match.group("value").strip().lower()
    if value in ("today", "yesterday"):
        return {"raw": text, "bucket": RELATIVE_BUCKETS[value], "value_days": 0, "quality": QUALITY_RELATIVE_ONLY}
    if value.startswith("30+") or "30+ days" in value:
        return {"raw": text, "bucket": RELATIVE_BUCKETS["30+ days ago"], "value_days": None,
                "quality": QUALITY_RELATIVE_ONLY}
    number = re.match(r"(\d+)", value)
    unit = "hours" if "hour" in value else "days"
    return {
        "raw": text,
        "bucket": RELATIVE_BUCKETS["hours ago" if unit == "hours" else "days ago"],
        "value_days": (int(number.group(1)) if number else None) if unit == "days" else None,
        "value_hours": (int(number.group(1)) if number else None) if unit == "hours" else None,
        "quality": QUALITY_RELATIVE_ONLY,
    }


def normalise_text(text: str | None) -> str:
    """Whitespace-normalise source text for display and evidence alignment.

    Newlines are preserved (they carry paragraph structure that evidence quotes
    rely on); runs of spaces and 3+ blank lines are collapsed. For *identity*
    purposes use :func:`canonical_ws`, which also collapses newlines, so a re-render
    of the same content is not mistaken for a revision.
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def canonical_ws(text: str | None) -> str:
    """All whitespace runs (including newlines) collapsed to one space.

    Used for content identity and for locating a quoted span in the source text:
    "does this quote appear in the posting" must not depend on how the source
    rendered paragraph breaks.
    """
    if not text:
        return ""
    return " ".join(text.split())


def content_hash(*, title: str | None, location: str | None, description: str | None) -> str:
    payload = {
        "title": canonical_ws(title),
        "location": canonical_ws(location),
        "description": canonical_ws(description),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def observation_id(*, source_platform: str, company_key: str, posting_id: str) -> str:
    """Deterministic id for (platform, company, posting). Stable across runs."""
    blob = f"{source_platform}|{company_key}|{posting_id}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]


@dataclass
class JobObservation:
    """One posting, as one source described it, at one moment."""

    # --- identity
    company_key: str                      # canonical focus-company key (universe_v1 focus_companies)
    posting_id: str                       # source-stable posting id (never ours)
    source_platform: str
    source_url: str
    # --- content
    job_title: str | None = None
    job_description: str | None = None
    job_location: str | None = None
    additional_locations: list[str] = field(default_factory=list)
    # --- time (three different fields with three different owners)
    source_posted_at: str | None = None            # the source's claim, or None
    source_posted_quality: str = QUALITY_NONE
    source_posted_raw: str | None = None           # verbatim source string
    first_seen_at: str | None = None               # our clock, write-once
    fetched_at: str | None = None                  # this collection attempt
    source_updated_at: str | None = None           # if the source exposes it
    # --- entity resolution
    legal_entity: str | None = None
    entity_resolution_status: str = ENTITY_STATUS_COMPANY_KEY
    entity_resolution_note: str | None = None
    # --- provenance / integrity
    collection_status: str = STATUS_LISTING_ONLY
    content_sha256: str | None = None
    hash_rule_version: str = HASH_RULE_VERSION
    collector_version: str = COLLECTOR_VERSION
    schema_version: str = SCHEMA_VERSION
    raw: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ derived
    @property
    def obs_id(self) -> str:
        return observation_id(source_platform=self.source_platform, company_key=self.company_key,
                              posting_id=self.posting_id)

    def finalise(self, *, fetched_at: str | None = None, first_seen_at: str | None = None) -> "JobObservation":
        """Fill the content hash and the two collector-owned timestamps."""
        self.source_platform = self.source_platform or PLATFORM_WORKDAY
        self.fetched_at = fetched_at or self.fetched_at or utc_now_iso()
        if self.first_seen_at is None:
            self.first_seen_at = first_seen_at or self.fetched_at
        self.content_sha256 = content_hash(title=self.job_title, location=self.job_location,
                                           description=self.job_description)
        self.validate()
        return self

    def validate(self) -> None:
        problems: list[str] = []
        if not self.company_key:
            problems.append("company_key is required")
        if not self.posting_id:
            problems.append("posting_id is required (a synthetic id is not an identity)")
        if self.source_platform not in PLATFORMS:
            problems.append(f"unknown source_platform {self.source_platform!r}")
        if self.source_posted_quality not in TIME_QUALITIES:
            problems.append(f"unknown source_posted_quality {self.source_posted_quality!r}")
        if self.collection_status not in STATUSES:
            problems.append(f"unknown collection_status {self.collection_status!r}")
        if self.entity_resolution_status not in (ENTITY_STATUS_COMPANY_KEY, ENTITY_STATUS_CANONICAL,
                                                 ENTITY_STATUS_AMBIGUOUS, ENTITY_STATUS_UNRESOLVED):
            problems.append(f"unknown entity_resolution_status {self.entity_resolution_status!r}")
        # The central time rule: a dated value implies a dated quality and vice versa.
        if self.source_posted_at and self.source_posted_quality in (QUALITY_NONE, QUALITY_RELATIVE_ONLY):
            problems.append("source_posted_at is set but its quality says it is not a date")
        if not self.source_posted_at and self.source_posted_quality in (QUALITY_SOURCE_DATE, QUALITY_SOURCE_DATETIME):
            problems.append("quality claims a source date but source_posted_at is empty")
        if problems:
            raise ValueError(f"invalid job observation {self.posting_id}: " + "; ".join(problems))

    # --------------------------------------------------------------- serialisation
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "obs_id": self.obs_id,
            "company_key": self.company_key,
            "legal_entity": self.legal_entity,
            "entity_resolution_status": self.entity_resolution_status,
            "entity_resolution_note": self.entity_resolution_note,
            "posting_id": self.posting_id,
            "job_title": self.job_title,
            "job_location": self.job_location,
            "additional_locations": list(self.additional_locations),
            "job_description": self.job_description,
            "source_url": self.source_url,
            "source_platform": self.source_platform,
            "source_posted_at": self.source_posted_at,
            "source_posted_quality": self.source_posted_quality,
            "source_posted_raw": self.source_posted_raw,
            "source_updated_at": self.source_updated_at,
            "first_seen_at": self.first_seen_at,
            "fetched_at": self.fetched_at,
            "collection_status": self.collection_status,
            "content_sha256": self.content_sha256,
            "hash_rule_version": self.hash_rule_version,
            "collector_version": self.collector_version,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "JobObservation":
        known = {
            "company_key", "legal_entity", "entity_resolution_status", "entity_resolution_note",
            "posting_id", "job_title", "job_location", "job_description", "source_url",
            "source_platform", "source_posted_at", "source_posted_quality", "source_posted_raw",
            "source_updated_at", "first_seen_at", "fetched_at", "collection_status",
            "content_sha256", "hash_rule_version", "collector_version", "raw",
        }
        kwargs = {k: v for k, v in data.items() if k in known}
        kwargs.setdefault("additional_locations", list(data.get("additional_locations") or []))
        obs = cls(**kwargs)  # type: ignore[arg-type]
        if data.get("schema_version") and data["schema_version"] != SCHEMA_VERSION:
            obs.raw = dict(obs.raw or {}, loaded_schema_version=data["schema_version"])
        return obs


def availability_counts(observations: list[JobObservation]) -> dict[str, Any]:
    """Field-availability report for a collection run.

    This is the WP2 evidence-instrument: a count of postings is meaningless
    without the rate at which identity, date, description and location were
    actually obtainable.
    """
    n = len(observations)
    if n == 0:
        return {"n": 0, "rates": {}, "by_quality": {}, "by_status": {}, "by_platform": {}}

    def rate(pred) -> float:
        return round(sum(1 for o in observations if pred(o)) / n, 4)

    by_quality: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_platform: dict[str, int] = {}
    for o in observations:
        by_quality[o.source_posted_quality] = by_quality.get(o.source_posted_quality, 0) + 1
        by_status[o.collection_status] = by_status.get(o.collection_status, 0) + 1
        by_platform[o.source_platform] = by_platform.get(o.source_platform, 0) + 1
    return {
        "n": n,
        "rates": {
            "posting_id": rate(lambda o: bool(o.posting_id)),
            "source_url": rate(lambda o: bool(o.source_url)),
            "job_title": rate(lambda o: bool(o.job_title)),
            "description_nonempty": rate(lambda o: bool(o.job_description)),
            "location": rate(lambda o: bool(o.job_location)),
            "source_date": rate(lambda o: o.source_posted_quality in (QUALITY_SOURCE_DATE, QUALITY_SOURCE_DATETIME)),
            "relative_only": rate(lambda o: o.source_posted_quality == QUALITY_RELATIVE_ONLY),
            "no_time": rate(lambda o: o.source_posted_quality == QUALITY_NONE),
            "first_seen": rate(lambda o: bool(o.first_seen_at)),
            "legal_entity": rate(lambda o: bool(o.legal_entity)),
        },
        "by_quality": by_quality,
        "by_status": by_status,
        "by_platform": by_platform,
        "distinct_postings": len({(o.company_key, o.posting_id) for o in observations}),
    }
