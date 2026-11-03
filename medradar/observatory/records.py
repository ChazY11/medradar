"""Canonical record shapes and time semantics for the Live Observatory.

A public record is not a row that gets overwritten. It is an *observation*: what
a specific source said, first seen by this collector at a specific real moment.
This module defines the vocabulary every adapter and the ledger share, so that
the difference between "the event happened" and "we found out" can never again
be blurred by an implementation detail.

Rules encoded here
------------------
* A moment is stored with the *precision the source actually published*. Missing
  time is ``None`` / ``"unknown"`` — never a guessed midnight, never ``today``.
* ``event_at``, ``published_at``, ``first_seen_at`` and ``last_checked_at`` are
  different fields with different owners (see ``docs/LIVE_OBSERVATORY_DESIGN.md``).
* Change states are a closed vocabulary. ``UNCHANGED`` is deliberately not stored
  as a change row; it is a *check result* (run counters + ``last_checked_at``),
  because a version that did not change is not evidence of a new version.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Mapping

# --------------------------------------------------------------------- vocabulary
SCHEMA_VERSION = "obs-ledger-v1"
COLLECTOR_VERSION = "live-observatory/1.0.0"

SOURCE_SEC_EDGAR = "sec_edgar"
SOURCE_CTGOV = "ctgov"
SOURCE_EUROPEPMC = "europepmc"

CHANGE_NEW = "NEW"
CHANGE_UPDATED = "UPDATED"
CHANGE_UNCHANGED = "UNCHANGED"
CHANGE_REMOVED = "REMOVED_OR_UNAVAILABLE"
CHANGE_FETCH_FAILED = "FETCH_FAILED"

CHANGE_STATES = (CHANGE_NEW, CHANGE_UPDATED, CHANGE_REMOVED, CHANGE_FETCH_FAILED)
#: States that are listed in the Live Observatory as observer-visible changes.
CHANGE_STATES_LISTED = CHANGE_STATES

CHANGE_LABELS_ZH = {
    CHANGE_NEW: "新增观察",
    CHANGE_UPDATED: "修订",
    CHANGE_UNCHANGED: "无变化",
    CHANGE_REMOVED: "来源不再提供",
    CHANGE_FETCH_FAILED: "采集失败",
}

CHANGE_LABELS_EN = {
    CHANGE_NEW: "Newly observed",
    CHANGE_UPDATED: "Updated",
    CHANGE_UNCHANGED: "Unchanged",
    CHANGE_REMOVED: "Removed or unavailable",
    CHANGE_FETCH_FAILED: "Fetch failed",
}

PRECISION_DATETIME = "datetime"
PRECISION_DATE = "date"
PRECISION_YEAR = "year"
PRECISION_UNKNOWN = "unknown"
PRECISIONS = (PRECISION_DATETIME, PRECISION_DATE, PRECISION_YEAR, PRECISION_UNKNOWN)

ORIGIN_LIVE = "LIVE"
ORIGIN_BACKFILLED = "BACKFILLED"
ORIGINS = (ORIGIN_LIVE, ORIGIN_BACKFILLED)

#: Acquisition phase — *when in the system's life* a record was first observed.
#: This is deliberately independent of ``observation_origin``: a record observed
#: in the first live sweep is INITIAL_DISCOVERY with a real first_seen_at, while a
#: record deliberately imported from a historical archive is HISTORICAL_BACKFILL
#: and must carry a reason. "Event older than collection" is NOT backfill.
PHASE_INITIAL = "INITIAL_DISCOVERY"
PHASE_INCREMENTAL = "INCREMENTAL_DISCOVERY"
PHASE_BACKFILL = "HISTORICAL_BACKFILL"
PHASES = (PHASE_INITIAL, PHASE_INCREMENTAL, PHASE_BACKFILL)

PHASE_LABELS_ZH = {
    PHASE_INITIAL: "初次上线发现（系统首次上线时观察到的既有公开记录）",
    PHASE_INCREMENTAL: "持续监测新发现（系统持续运行期间新观察到的公开记录）",
    PHASE_BACKFILL: "历史回填（有意导入的历史归档，带来源与理由）",
}

PHASE_SHORT_ZH = {
    PHASE_INITIAL: "初次发现",
    PHASE_INCREMENTAL: "增量发现",
    PHASE_BACKFILL: "历史回填",
}

#: What a completed sync run actually produced. NO_NEW_RECORDS is a normal
#: result; FETCH_FAILED is a system failure — they must never be shown as the same
#: thing.
OUTCOME_NEW_RECORDS = "NEW_RECORDS"
OUTCOME_UPDATED_RECORDS = "UPDATED_RECORDS"
OUTCOME_NO_NEW_RECORDS = "NO_NEW_RECORDS"
OUTCOME_PARTIAL = "PARTIAL"
OUTCOME_FETCH_FAILED = "FETCH_FAILED"
OUTCOME_PAUSED = "PAUSED_SKIPPED"
OUTCOME_LOCKED = "LOCKED_SKIPPED"
OUTCOMES = (OUTCOME_NEW_RECORDS, OUTCOME_UPDATED_RECORDS, OUTCOME_NO_NEW_RECORDS,
            OUTCOME_PARTIAL, OUTCOME_FETCH_FAILED, OUTCOME_PAUSED, OUTCOME_LOCKED)

OUTCOME_LABELS_ZH = {
    OUTCOME_NEW_RECORDS: "有新记录",
    OUTCOME_UPDATED_RECORDS: "有修订记录",
    OUTCOME_NO_NEW_RECORDS: "正常：无新记录",
    OUTCOME_PARTIAL: "部分完成",
    OUTCOME_FETCH_FAILED: "采集失败",
    OUTCOME_PAUSED: "已暂停跳过",
    OUTCOME_LOCKED: "另一采集进程持有锁，已跳过",
}

#: Deployment vocabulary (see docs/RELIABILITY_DESIGN.md §0).
DEPLOYMENT_NOT_DEPLOYED = "NOT_DEPLOYED"
DEPLOYMENT_LOCAL = "DEPLOYED_LOCAL"
DEPLOYMENT_SERVICE = "DEPLOYED_SERVICE"

#: Seven-day validation vocabulary.
VALIDATION_NOT_STARTED = "VALIDATION_NOT_STARTED"
VALIDATION_IN_PROGRESS = "VALIDATION_IN_PROGRESS"
VALIDATION_PASSED = "VALIDATION_PASSED"
VALIDATION_FAILED = "VALIDATION_FAILED"

HEALTH_OPERATIONAL = "OPERATIONAL"
HEALTH_DEGRADED = "DEGRADED"
HEALTH_PAUSED = "PAUSED"
HEALTH_NOT_DEPLOYED = "NOT_DEPLOYED"
HEALTH_VALIDATION = "VALIDATION_IN_PROGRESS"


STATUS_ACTIVE = "ACTIVE"
STATUS_REMOVED = "REMOVED_OR_UNAVAILABLE"
OBSERVATION_STATUSES = (STATUS_ACTIVE, STATUS_REMOVED)

ENTITY_MAPPED = "MAPPED"
ENTITY_PENDING_REVIEW = "PENDING_REVIEW"
ENTITY_UNMAPPED = "UNMAPPED"
ENTITY_AMBIGUOUS = "AMBIGUOUS"
ENTITY_STATUSES = (ENTITY_MAPPED, ENTITY_PENDING_REVIEW, ENTITY_UNMAPPED, ENTITY_AMBIGUOUS)

TRACK_MAPPED = "MAPPED"
TRACK_PENDING_REVIEW = "PENDING_REVIEW"
TRACK_UNMAPPED = "UNMAPPED"
TRACK_STATUSES = (TRACK_MAPPED, TRACK_PENDING_REVIEW, TRACK_UNMAPPED)

RUN_RUNNING = "RUNNING"
RUN_OK = "OK"
RUN_PARTIAL = "PARTIAL"
RUN_FAILED = "FAILED"
RUN_INTERRUPTED = "INTERRUPTED"
RUN_SKIPPED = "SKIPPED"

SOURCE_STATUS_NEVER_RUN = "NEVER_RUN"
SOURCE_STATUS_OK = "OK"
SOURCE_STATUS_DEGRADED = "DEGRADED"
SOURCE_STATUS_FAILED = "FAILED"
SOURCE_STATUS_PAUSED = "PAUSED"

SOURCE_STATUS_LABELS_ZH = {
    SOURCE_STATUS_NEVER_RUN: "从未运行",
    SOURCE_STATUS_OK: "正常",
    SOURCE_STATUS_DEGRADED: "部分失败",
    SOURCE_STATUS_FAILED: "失败",
    SOURCE_STATUS_PAUSED: "已暂停",
}

RUN_STATUS_LABELS_ZH = {
    RUN_RUNNING: "运行中",
    RUN_OK: "成功",
    RUN_PARTIAL: "部分成功",
    RUN_FAILED: "失败",
    RUN_INTERRUPTED: "中断",
    RUN_SKIPPED: "跳过",
}

#: Human readable labels for the fields an adapter can declare as changeable.
FIELD_LABELS_ZH = {
    "title": "标题",
    "status": "状态",
    "phase": "阶段",
    "enrollment": "计划入组",
    "items": "8-K 事项",
    "form": "表单类型",
    "primary_document": "主文档",
    "event_at": "事件时间",
    "published_at": "发布时间",
    "source_updated_at": "来源更新时间",
    "authors": "作者",
    "journal": "期刊",
    "abstract": "摘要",
    "conditions": "适应症",
    "sponsor": "申办方",
    "url": "来源链接",
    "payload": "其他字段",
}


# ------------------------------------------------------------------ time handling
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Real wall clock, second precision, UTC — the only writer of `first_seen_at`."""
    return utc_now().replace(microsecond=0).isoformat()


def normalize_moment(value: Any) -> tuple[str | None, str]:
    """Return ``(canonical_value, precision)`` without inventing information.

    * aware datetime → ``YYYY-MM-DDTHH:MM:SS+00:00`` (precision ``datetime``)
    * naive datetime → same, interpreted as UTC only when the caller already
      declared it UTC; we never guess a timezone from a naive value, so a naive
      *time* is rejected and reported as unknown precision with the raw string.
    * date → ``YYYY-MM-DD`` (precision ``date``), **not** a fake midnight
    * ``YYYY`` / ``YYYY-MM`` → ``YYYY`` (precision ``year``)
    """
    if value is None:
        return None, PRECISION_UNKNOWN
    if isinstance(value, datetime):
        if value.tzinfo is None:
            # No timezone information: keep the date part only rather than
            # pretending we know the UTC instant.
            return value.date().isoformat(), PRECISION_DATE
        moment = value.astimezone(timezone.utc).replace(microsecond=0)
        return moment.isoformat(), PRECISION_DATETIME
    if isinstance(value, date):
        return value.isoformat(), PRECISION_DATE
    text = str(value).strip()
    if not text:
        return None, PRECISION_UNKNOWN
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            # A bare date/datetime without a zone: keep only what the source
            # actually stated (a day).
            return parsed.date().isoformat(), PRECISION_DATE
        moment = parsed.astimezone(timezone.utc).replace(microsecond=0)
        return moment.isoformat(), PRECISION_DATETIME
    # year / year-month precision
    if len(text) == 4 and text.isdigit():
        return text, PRECISION_YEAR
    if len(text) == 7 and text[4] == "-" and text.replace("-", "").isdigit():
        return text, PRECISION_YEAR
    try:
        parsed_date = datetime.strptime(text, "%Y/%m/%d").date()
    except ValueError:
        return None, PRECISION_UNKNOWN
    return parsed_date.isoformat(), PRECISION_DATE


def parse_moment(value: str | None, precision: str | None = None) -> datetime | None:
    """Parse a stored moment for lag arithmetic.

    A ``date``-precision value is anchored at 00:00 UTC **for interval
    arithmetic only**; callers must surface the precision (``lag_is_exact``), so
    an approximate interval is never presented as a measured one.
    """
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 4 and text.isdigit():
        return datetime(int(text), 1, 1, tzinfo=timezone.utc)
    if len(text) == 7 and text[4] == "-":
        year, month = text.split("-")
        return datetime(int(year), int(month), 1, tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def hours_between(earlier: str | None, later: str | None) -> float | None:
    left = parse_moment(earlier)
    right = parse_moment(later)
    if left is None or right is None:
        return None
    return round((right - left).total_seconds() / 3600.0, 3)


# --------------------------------------------------------------- canonical payload
def canonical_json(value: Any) -> str:
    """Stable JSON used for hashing and for the audit payload column."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def payload_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha1(canonical_json(payload).encode("utf-8")).hexdigest()


def observation_id(source: str, source_record_id: str) -> str:
    """Deterministic identity: re-collecting the same record is the same row."""
    return hashlib.sha1(f"{source}|{source_record_id}".encode("utf-8")).hexdigest()


def version_id(observation: str, digest: str) -> str:
    return hashlib.sha1(f"{observation}|{digest}".encode("utf-8")).hexdigest()


def mapped_observation_id(record: "RawRecord") -> str:
    return observation_id(record.source, record.source_record_id)


# ------------------------------------------------------------------- record shapes
@dataclass(frozen=True)
class RawRecord:
    """One record exactly as the source served it (normalised field names only)."""

    source: str
    source_record_id: str
    record_type: str
    title: str
    url: str | None = None
    event_at: str | None = None
    event_at_precision: str = PRECISION_UNKNOWN
    published_at: str | None = None
    published_at_precision: str = PRECISION_UNKNOWN
    source_updated_at: str | None = None
    source_updated_at_precision: str = PRECISION_UNKNOWN
    payload: Mapping[str, Any] = field(default_factory=dict)
    company_hint: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source or not self.source_record_id:
            raise ValueError("RawRecord requires source and source_record_id")
        if self.event_at_precision not in PRECISIONS:
            raise ValueError(f"bad event_at precision: {self.event_at_precision}")
        if self.published_at_precision not in PRECISIONS:
            raise ValueError(f"bad published_at precision: {self.published_at_precision}")
        if self.source_updated_at_precision not in PRECISIONS:
            raise ValueError(f"bad source_updated_at precision: {self.source_updated_at_precision}")
        if self.event_at is None and self.event_at_precision != PRECISION_UNKNOWN:
            raise ValueError("event_at is None but precision is not unknown")
        if self.published_at is None and self.published_at_precision != PRECISION_UNKNOWN:
            raise ValueError("published_at is None but precision is not unknown")

    @property
    def observation_id(self) -> str:
        return observation_id(self.source, self.source_record_id)

    @property
    def payload_hash(self) -> str:
        return payload_hash(self.payload)


@dataclass(frozen=True)
class MappingResult:
    """Entity / technology attribution, deliberately more granular than a string."""

    entity_id: str | None = None
    entity_status: str = ENTITY_UNMAPPED
    entity_method: str | None = None
    entity_confidence: float | None = None
    track_id: str | None = None
    track_status: str = TRACK_UNMAPPED
    track_method: str | None = None
    note_zh: str | None = None

    def __post_init__(self) -> None:
        if self.entity_status not in ENTITY_STATUSES:
            raise ValueError(f"bad entity_status: {self.entity_status}")
        if self.track_status not in TRACK_STATUSES:
            raise ValueError(f"bad track_status: {self.track_status}")
        if self.entity_status == ENTITY_MAPPED and not self.entity_id:
            raise ValueError("MAPPED entity requires an entity_id")
        if self.track_status == TRACK_MAPPED and not self.track_id:
            raise ValueError("MAPPED track requires a track_id")


@dataclass
class Scope:
    """A resumable unit of work (one issuer CIK, one query term, ...)."""

    scope_id: str
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class Page:
    """One page of results plus the cursor that continues the scope."""

    records: list[RawRecord] = field(default_factory=list)
    next_cursor: str | None = None
    watermark: str | None = None
    structure_sample: Any = None
    note_zh: str | None = None
    removed_ids: list[str] = field(default_factory=list)
    failed_ids: list[str] = field(default_factory=list)
    failure_note_zh: str | None = None


@dataclass
class RecordOutcome:
    """What a single ``record_observation`` call did (used by run counters)."""

    observation_id: str
    state: str
    version_id: str | None
    previous_version_id: str | None = None
    changed_fields: tuple[str, ...] = ()
    first_seen_at: str | None = None

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
    names = sorted(set(previous) | set(current))
    return [name for name in names if previous.get(name) != current.get(name)]


def short_preview(value: Any, limit: int = 160) -> str:
    """A bounded, single-line preview for revision diffs (never re-writes data)."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = canonical_json(value)
    else:
        text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def now_iso() -> str:
    return utc_now_iso()
