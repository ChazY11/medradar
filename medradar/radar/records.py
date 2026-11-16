"""Canonical record shapes and time semantics for RADAR-001.

A public record is not a row that gets overwritten. It is an *observation*: what a
specific source said, first seen by this collector at a specific real moment. This module
defines the vocabulary every adapter, the ledger, the graph and the API share, so that the
difference between "it happened" and "we found out" cannot be blurred by an implementation
detail.

Rules encoded here
------------------
* A moment is stored with the precision the source actually published. Missing time is
  ``None`` / ``unknown`` - never a guessed midnight, never ``today``.
* ``event_at``, ``published_at``, ``source_updated_at``, ``first_observed_at`` and
  ``last_checked_at`` are different fields with different owners.
* Change states are a closed vocabulary. ``UNCHANGED`` is deliberately **not** a stored
  change row: it is a check result (run counters plus ``last_checked_at``), because a
  version that did not change is not evidence of a new version.
* ``discovery_phase`` separates the records that were already public when MedRadar first
  switched a source on (``INITIAL_DISCOVERY``) from records that became public while the
  system was running (``INCREMENTAL_DISCOVERY``). A historical record imported on purpose
  is ``HISTORICAL_BACKFILL`` and must carry a reason. "The event is older than the
  collection" is *not* backfill.

Provenance
----------
Adapted from the Live Observatory record contract (PR #13/#14,
``medradar/observatory/records.py``) and extended with the RADAR-001 intelligence-event
fields (organisation/product candidates, technology topics, content hash, version,
processing state, evidence references).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "radar-ledger-v1"
COLLECTOR_VERSION = "radar-001/1.0.0"
#: Version of the *rule layer*. A change here makes the next ``advance`` re-classify every
#: observation, so a rule edit is a visible version change rather than a silent behaviour change.
MAPPING_VERSION = "radar-rules-2026.11.2"
GRAPH_VERSION = "radar-graph-1"

# --------------------------------------------------------------------- vocabulary
CHANGE_NEW = "NEW"
CHANGE_UPDATED = "UPDATED"
CHANGE_UNCHANGED = "UNCHANGED"
CHANGE_REMOVED = "REMOVED_OR_UNAVAILABLE"
CHANGE_FETCH_FAILED = "FETCH_FAILED"

#: States written as change rows. ``UNCHANGED`` is a check result, never a change row.
CHANGE_STATES = (CHANGE_NEW, CHANGE_UPDATED, CHANGE_REMOVED, CHANGE_FETCH_FAILED)
ALL_CHANGE_STATES = (CHANGE_NEW, CHANGE_UPDATED, CHANGE_UNCHANGED, CHANGE_REMOVED, CHANGE_FETCH_FAILED)

CHANGE_LABELS_EN = {
    CHANGE_NEW: "Newly observed",
    CHANGE_UPDATED: "Updated",
    CHANGE_UNCHANGED: "Unchanged",
    CHANGE_REMOVED: "Removed or unavailable",
    CHANGE_FETCH_FAILED: "Fetch failed",
}

CHANGE_LABELS_ZH = {
    CHANGE_NEW: "新增观察",
    CHANGE_UPDATED: "来源修订",
    CHANGE_UNCHANGED: "无变化",
    CHANGE_REMOVED: "来源不再提供",
    CHANGE_FETCH_FAILED: "采集失败",
}

PRECISION_DATETIME = "datetime"
PRECISION_DATE = "date"
PRECISION_YEAR = "year"
PRECISION_UNKNOWN = "unknown"
PRECISIONS = (PRECISION_DATETIME, PRECISION_DATE, PRECISION_YEAR, PRECISION_UNKNOWN)

ORIGIN_LIVE = "LIVE"
ORIGIN_BACKFILLED = "BACKFILLED"
ORIGINS = (ORIGIN_LIVE, ORIGIN_BACKFILLED)

PHASE_INITIAL = "INITIAL_DISCOVERY"
PHASE_INCREMENTAL = "INCREMENTAL_DISCOVERY"
PHASE_BACKFILL = "HISTORICAL_BACKFILL"
PHASES = (PHASE_INITIAL, PHASE_INCREMENTAL, PHASE_BACKFILL)

PHASE_LABELS_EN = {
    PHASE_INITIAL: "Initial discovery (already public when the source was first enabled)",
    PHASE_INCREMENTAL: "Incremental discovery (became public while the system was running)",
    PHASE_BACKFILL: "Historical backfill (deliberate import, with a reason)",
}

STATUS_ACTIVE = "ACTIVE"
STATUS_REMOVED = "REMOVED_OR_UNAVAILABLE"
OBSERVATION_STATUSES = (STATUS_ACTIVE, STATUS_REMOVED)

#: Where an observation sits in the intelligence pipeline.
#: ``PUBLISHED`` means classified + resolved + linked and visible in the feed/graph.
PROC_RAW = "RAW"
PROC_CLASSIFIED = "CLASSIFIED"
PROC_RESOLVED = "RESOLVED"
PROC_LINKED = "LINKED"
PROC_PUBLISHED = "PUBLISHED"
PROC_AI_PENDING = "AI_PENDING"
PROC_AI_DONE = "AI_DONE"
PROC_AI_FAILED = "AI_FAILED"
PROC_SKIPPED = "SKIPPED"
PROCESSING_STATES = (
    PROC_RAW, PROC_CLASSIFIED, PROC_RESOLVED, PROC_LINKED, PROC_PUBLISHED,
    PROC_AI_PENDING, PROC_AI_DONE, PROC_AI_FAILED, PROC_SKIPPED,
)

#: Relation confirmation levels. ``UNKNOWN`` is a state, not an absence.
CONFIRMED = "CONFIRMED"
CANDIDATE = "CANDIDATE"
TOPIC_RELATED = "TOPIC_RELATED"
UNKNOWN_RELATION = "UNKNOWN"
CONFIRMATION_LEVELS = (CONFIRMED, CANDIDATE, TOPIC_RELATED, UNKNOWN_RELATION)

#: How a candidate was produced. Rules and models are never mixed silently.
METHOD_OFFICIAL_ID = "official_identifier"
METHOD_RULE_ALIAS = "rule_alias"
METHOD_RULE_TEXT = "rule_text"
METHOD_RULE_PRODUCT_CODE = "rule_product_code"
METHOD_MODEL = "model"
METHOD_PIPELINE_BRIDGE = "pipeline_bridge"

#: Record types an intelligence event can carry.
RECORD_TYPES = (
    "regulatory_record",   # FDA 510(k)/PMA/recall
    "publication",         # journal article / preprint
    "press_release",       # vendor official news
    "product_document",    # vendor official product page/datasheet
    "clinical_trial",      # reserved for a later adapter
)

RUN_RUNNING = "RUNNING"
RUN_OK = "OK"
RUN_PARTIAL = "PARTIAL"
RUN_FAILED = "FAILED"
RUN_INTERRUPTED = "INTERRUPTED"
RUN_SKIPPED = "SKIPPED"
RUN_DEFERRED = "DEFERRED"

OUTCOME_NEW_RECORDS = "NEW_RECORDS"
OUTCOME_UPDATED_RECORDS = "UPDATED_RECORDS"
OUTCOME_NO_NEW_RECORDS = "NO_NEW_RECORDS"
OUTCOME_PARTIAL = "PARTIAL"
OUTCOME_FETCH_FAILED = "FETCH_FAILED"
OUTCOME_PAUSED = "PAUSED_SKIPPED"
OUTCOME_LOCKED = "LOCKED_SKIPPED"
OUTCOME_DEFERRED = "DEFERRED"
OUTCOMES = (
    OUTCOME_NEW_RECORDS, OUTCOME_UPDATED_RECORDS, OUTCOME_NO_NEW_RECORDS, OUTCOME_PARTIAL,
    OUTCOME_FETCH_FAILED, OUTCOME_PAUSED, OUTCOME_LOCKED, OUTCOME_DEFERRED,
)

SOURCE_STATUS_NEVER_RUN = "NEVER_RUN"
SOURCE_STATUS_OK = "OK"
SOURCE_STATUS_DEGRADED = "DEGRADED"
SOURCE_STATUS_FAILED = "FAILED"
SOURCE_STATUS_PAUSED = "PAUSED"
SOURCE_STATUS_BLOCKED = "BLOCKED_BY_ACCESS_POLICY"

#: Access decisions recorded by ``scripts/radar_source_probe.py``.
ACCESS_ENABLED = "ENABLED"
ACCESS_BLOCKED = "BLOCKED"
ACCESS_UNVERIFIED = "UNVERIFIED"

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YEAR_ONLY = re.compile(r"^\d{4}$")
_YEAR_MONTH = re.compile(r"^\d{4}-\d{2}$")


# ------------------------------------------------------------------ time handling
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Real wall clock, second precision, UTC - the only writer of ``first_observed_at``."""
    return utc_now().replace(microsecond=0).isoformat()


def canonical_moment(value: Any) -> str:
    """Canonical, lexically sortable UTC moment (fixed-width microseconds)."""
    moment = parse_moment(value)
    if moment is None:
        raise ValueError(f"not a parseable moment: {value!r}")
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def normalize_moment(value: Any) -> tuple[str | None, str]:
    """Return ``(canonical_value, precision)`` without inventing information.

    * aware datetime -> ``YYYY-MM-DDTHH:MM:SS+00:00`` (precision ``datetime``)
    * naive datetime -> the date part only, precision ``date``; a zone is never guessed
    * date -> ``YYYY-MM-DD`` (precision ``date``), **not** a fake midnight
    * ``YYYY`` / ``YYYY-MM`` -> precision ``year``
    """
    if value is None:
        return None, PRECISION_UNKNOWN
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.date().isoformat(), PRECISION_DATE
        moment = value.astimezone(timezone.utc).replace(microsecond=0)
        return moment.isoformat(), PRECISION_DATETIME
    if isinstance(value, date):
        return value.isoformat(), PRECISION_DATE
    text = str(value).strip()
    if not text:
        return None, PRECISION_UNKNOWN
    if _YEAR_ONLY.match(text):
        return text, PRECISION_YEAR
    if _YEAR_MONTH.match(text):
        return text, PRECISION_YEAR
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            return parsed.date().isoformat(), PRECISION_DATE
        moment = parsed.astimezone(timezone.utc).replace(microsecond=0)
        return moment.isoformat(), PRECISION_DATETIME
    try:
        return datetime.strptime(text, "%Y/%m/%d").date().isoformat(), PRECISION_DATE
    except ValueError:
        return None, PRECISION_UNKNOWN


def parse_moment(value: Any, precision: str | None = None) -> datetime | None:
    """Parse a stored moment for arithmetic.

    A ``date``-precision value is anchored at 00:00 UTC **for interval arithmetic only**;
    callers must surface the precision so an approximate interval is never presented as a
    measured one.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if _YEAR_ONLY.match(text):
        return datetime(int(text), 1, 1, tzinfo=timezone.utc)
    if _YEAR_MONTH.match(text):
        year, month = text.split("-")
        return datetime(int(year), int(month), 1, tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def hours_between(earlier: Any, later: Any) -> float | None:
    left = parse_moment(earlier)
    right = parse_moment(later)
    if left is None or right is None:
        return None
    return round((right - left).total_seconds() / 3600.0, 3)


# --------------------------------------------------------------- canonical payload
def canonical_json(value: Any) -> str:
    """Stable JSON used for hashing and for the audit payload column.

    ``allow_nan=False`` makes a non-finite float a hard error: NaN/Infinity would break both
    hashing and JSON round-tripping, and a content hash that cannot round-trip is not an
    identity.
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      default=str, allow_nan=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(payload: Mapping[str, Any]) -> str:
    """sha256 over the content fields of a record (volatile bookkeeping excluded)."""
    return sha256_hex(canonical_json(payload))


def observation_id(source: str, source_record_id: str) -> str:
    """Deterministic identity: re-collecting the same record is the same row."""
    return hashlib.sha256(f"{source}|{source_record_id}".encode("utf-8")).hexdigest()[:32]


def version_id(observation: str, digest: str) -> str:
    return hashlib.sha256(f"{observation}|{digest}".encode("utf-8")).hexdigest()[:32]


# ------------------------------------------------------------------- record shapes
@dataclass(frozen=True)
class RawRecord:
    """One record exactly as the source served it (normalised field names only)."""

    source: str
    source_record_id: str
    record_type: str
    title: str
    #: The identifier the *source* published (K-number, PMID, DOI, article slug). It is the
    #: cross-source join key and is stored separately from our internal record identity.
    official_identifier: str | None = None
    url: str | None = None
    event_at: str | None = None
    event_at_precision: str = PRECISION_UNKNOWN
    published_at: str | None = None
    published_at_precision: str = PRECISION_UNKNOWN
    source_updated_at: str | None = None
    source_updated_at_precision: str = PRECISION_UNKNOWN
    payload: Mapping[str, Any] = field(default_factory=dict)
    #: Text a classification rule may use (title + abstract + device name + keywords).
    text: str = ""
    #: Free-form source fields that are not part of the hashed payload.
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source or not self.source_record_id:
            raise ValueError("RawRecord requires source and source_record_id")
        if self.record_type not in RECORD_TYPES:
            raise ValueError(f"unknown record_type: {self.record_type!r}")
        for name in ("event_at", "published_at", "source_updated_at"):
            precision = getattr(self, f"{name}_precision")
            if precision not in PRECISIONS:
                raise ValueError(f"bad {name} precision: {precision}")
            if getattr(self, name) is None and precision != PRECISION_UNKNOWN:
                raise ValueError(f"{name} is None but precision is not unknown")

    @property
    def observation_id(self) -> str:
        return observation_id(self.source, self.source_record_id)

    @property
    def payload_hash(self) -> str:
        return content_hash(self.payload)


@dataclass(frozen=True)
class MappingResult:
    """Attribution produced by the rule layer. Deliberately more granular than a string."""

    organization_candidates: tuple[dict[str, Any], ...] = ()
    product_candidates: tuple[dict[str, Any], ...] = ()
    technology_topics: tuple[dict[str, Any], ...] = ()
    method_version: str = MAPPING_VERSION
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "organization_candidates": list(self.organization_candidates),
            "product_candidates": list(self.product_candidates),
            "technology_topics": list(self.technology_topics),
            "method_version": self.method_version,
            "note": self.note,
        }


@dataclass
class Scope:
    """A resumable unit of work (one query, one sitemap, one product-code sweep)."""

    scope_id: str
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class Page:
    """One page of results plus the cursor that continues the scope."""

    records: list[RawRecord] = field(default_factory=list)
    next_cursor: str | None = None
    watermark: str | None = None
    #: Identifiers the source no longer serves (only set when that is provable).
    removed_ids: list[str] = field(default_factory=list)
    failed_ids: list[str] = field(default_factory=list)
    failure_note: str | None = None
    note: str | None = None


@dataclass
class RecordOutcome:
    """What a single ``record_observation`` call did (used by run counters)."""

    observation_id: str
    state: str
    version_id: str | None
    previous_version_id: str | None = None
    changed_fields: tuple[str, ...] = ()
    first_observed_at: str | None = None
    phase: str = PHASE_INITIAL

    @property
    def is_new(self) -> bool:
        return self.state == CHANGE_NEW

    @property
    def is_updated(self) -> bool:
        return self.state == CHANGE_UPDATED


def changed_fields(previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None) -> list[str]:
    """Field name deltas between two canonical payloads (shallow, stable order)."""
    previous = previous or {}
    current = current or {}
    return [name for name in sorted(set(previous) | set(current)) if previous.get(name) != current.get(name)]


def short_preview(value: Any, limit: int = 160) -> str:
    """A bounded, single-line preview for revision diffs (never rewrites data)."""
    if value is None:
        return ""
    text = canonical_json(value) if isinstance(value, (dict, list)) else str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


# ------------------------------------------------------- standard intelligence event
#: The fields every published intelligence event carries (RADAR-001 section 6).
INTELLIGENCE_EVENT_FIELDS: tuple[str, ...] = (
    "observation_id",
    "source",
    "official_identifier",
    "title",
    "source_url",
    "record_type",
    "event_date",
    "event_date_precision",
    "source_published_at",
    "source_published_at_precision",
    "first_observed_at",
    "last_checked_at",
    "source_updated_at",
    "source_updated_at_precision",
    "content_hash",
    "version",
    "organization_candidates",
    "product_candidates",
    "technology_topics",
    "evidence_references",
    "processing_state",
    "change_state",
    "discovery_phase",
)


def evidence_reference(
    *,
    observation_id_value: str,
    version_id_value: str | None,
    content_hash_value: str,
    source: str,
    url: str | None,
    official_identifier: str,
) -> dict[str, Any]:
    """One citable pointer from a graph assertion back to the exact source bytes."""
    return {
        "evidence_id": version_id_value or observation_id_value,
        "observation_id": observation_id_value,
        "version_id": version_id_value,
        "content_hash": content_hash_value,
        "source": source,
        "url": url,
        "official_identifier": official_identifier,
    }


def unique_preserving_order(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return tuple(ordered)
