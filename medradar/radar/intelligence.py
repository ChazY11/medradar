"""Archive / candidate / deliverable-intelligence, and the weekly brief (V1-001).

The product problem this module answers
---------------------------------------
The ledger held 8,593 observations, 7,360 of them admitted to the feed, and 95.6% of those were
older than 24 months. "We have a lot of records" was being presented as "there is something worth
reading", and importance was a constant (8,590 MEDIUM / 3 HIGH). This module separates three
different things over the *same* stored evidence - no second store, no second classifier:

ARCHIVE       every observation, searchable and traceable. Historical records are evidence and
              are not required to be newsworthy.
CANDIDATE     discovered or materially changed inside the brief window and possibly about
              monitoring, but not yet a deliverable (needs review, or the date is unknown).
INTELLIGENCE  a candidate that also passes the deliverable gate: monitoring relevance, an
              official source with a URL, a known event identity, a dated event, a graded
              importance with recorded reasons, no duplicate event, and a recorded review state.

Novelty is derived, never assumed. The five states are different things and the brief prints them
separately:

NEW_EVENT                    the source states the event became public inside the window
UPDATED_EVENT                an already known record changed its content inside the window
FIRST_DISCOVERED_HISTORICAL  MedRadar first saw it inside the window but the source dates it
                             before the window. This is a historical supplement, never news.
UNDATED_FIRST_DISCOVERY      first seen inside the window, but the source states no usable date;
                             freshness cannot be claimed
ARCHIVE_ONLY                 nothing about it changed inside the window

Importance is graded by the assessment layer (assessment.grade_importance) and only read here;
this module never invents a second importance scale.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Mapping, Sequence

from .assessment import IMPORTANCE_CRITICAL, IMPORTANCE_HIGH, IMPORTANCE_LEVELS, IMPORTANCE_MEDIUM
from .records import (
    CHANGE_UPDATED, ORIGIN_BACKFILLED, PHASE_BACKFILL, PRECISION_UNKNOWN,
    effective_precision, parse_moment,
)
from .recall import is_recall_payload, recall_event_id

#: Bumped when the view or the brief policy changes. Recorded on every brief.
POLICY_VERSION = "radar-intelligence-2026.11.21"

ARCHIVE = "ARCHIVE"
CANDIDATE = "CANDIDATE"
INTELLIGENCE = "INTELLIGENCE"
VIEWS = (ARCHIVE, CANDIDATE, INTELLIGENCE)

NEW_EVENT = "NEW_EVENT"
UPDATED_EVENT = "UPDATED_EVENT"
FIRST_DISCOVERED_HISTORICAL = "FIRST_DISCOVERED_HISTORICAL"
UNDATED_FIRST_DISCOVERY = "UNDATED_FIRST_DISCOVERY"
ARCHIVE_ONLY = "ARCHIVE_ONLY"
NOVELTY_STATES = (NEW_EVENT, UPDATED_EVENT, FIRST_DISCOVERED_HISTORICAL,
                  UNDATED_FIRST_DISCOVERY, ARCHIVE_ONLY)

NOVELTY_LABELS_EN = {
    NEW_EVENT: "Became public inside the window",
    UPDATED_EVENT: "Updated inside the window",
    FIRST_DISCOVERED_HISTORICAL: "Historical event, first collected inside the window",
    UNDATED_FIRST_DISCOVERY: "First collected inside the window, public date not stated",
    ARCHIVE_ONLY: "No change inside the window",
}
NOVELTY_LABELS_ZH = {
    NEW_EVENT: "窗口内公开",
    UPDATED_EVENT: "窗口内更新",
    FIRST_DISCOVERED_HISTORICAL: "历史事件首次采集",
    UNDATED_FIRST_DISCOVERY: "首次采集，公开日期未标注",
    ARCHIVE_ONLY: "窗口内无变化",
}

REVIEW_NOT_REVIEWED = "NOT_REVIEWED"
REVIEW_AGENT_VERIFIED = "AGENT_VERIFIED_AGAINST_SOURCE"
REVIEW_HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
REVIEW_HUMAN_CORRECTED = "HUMAN_CORRECTED"
REVIEW_STATES = (REVIEW_NOT_REVIEWED, REVIEW_AGENT_VERIFIED, REVIEW_HUMAN_CONFIRMED,
                 REVIEW_HUMAN_CORRECTED)
REVIEW_LABELS_EN = {
    REVIEW_NOT_REVIEWED: "not reviewed",
    REVIEW_AGENT_VERIFIED: "checked against the official record by the agent; not a human review",
    REVIEW_HUMAN_CONFIRMED: "confirmed by a human reviewer",
    REVIEW_HUMAN_CORRECTED: "corrected by a human reviewer",
}

#: Importance levels that may appear in a deliverable brief, most important first.
DELIVERABLE_IMPORTANCE = (IMPORTANCE_CRITICAL, IMPORTANCE_HIGH, IMPORTANCE_MEDIUM)
#: Monitoring relevance classes a deliverable may carry.
DELIVERABLE_RELEVANCE = ("DIRECT",)


# --------------------------------------------------------------------------- time helpers
def _day(value: Any) -> date | None:
    moment = parse_moment(value)
    return moment.date() if moment is not None else None


def _in_window(value: Any, start: date, end: date) -> bool:
    day = _day(value)
    return day is not None and start <= day <= end


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value)) if value else default
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- identity
def event_identity(row: Mapping[str, Any]) -> str:
    """The identity of what happened, not of the row that describes it.

    For an FDA recall that is the recall event number, so 42 product rows belonging to 19 events
    cannot become 42 brief items. For a publication it is the work key the ledger already derives
    (normalised DOI/PMID/title), so one paper seen through Crossref and PubMed is one item.
    Anything else falls back to the observation id, which never merges two records by mistake.
    """
    # The stored official identifier is preferred over the payload: the loader selects it for
    # every row, so the identity is the same before and after the payload is hydrated. Reading it
    # only from the payload made the event index disagree with the collapsed items (measured: a
    # reference recall event matched 0 of 8 because the index held WORK: identities instead).
    stored_event = str(row.get("recall_event_id") or "").strip()
    if stored_event:
        return "FDA_RECALL_EVENT:" + stored_event
    payload = row.get("payload") or {}
    if is_recall_payload(payload):
        event = recall_event_id(payload)
        if event:
            return "FDA_RECALL_EVENT:" + event
    work_key = str(row.get("work_key") or "").strip()
    if work_key:
        return "WORK:" + work_key
    official = str(row.get("official_identifier") or "").strip()
    if official:
        return "OFFICIAL:" + official
    return "OBSERVATION:" + str(row.get("observation_id") or "")


def distinguish_novelty(row: Mapping[str, Any], *, start: date, end: date) -> tuple[str, list[str]]:
    """What changed about this record inside the window, and why we say so."""
    # The precision belongs to the field that supplied the date. openFDA publishes a record with
    # a decision date and no publication date, so taking published_at_precision first labelled a
    # dated 510(k) as undated (measured on the real ledger, 6967 records).
    if row.get("published_at"):
        published = row.get("published_at")
        precision = str(row.get("published_at_precision") or "")
    else:
        published = row.get("event_at")
        precision = str(row.get("event_at_precision") or "")
    origin = str(row.get("observation_origin") or "")
    phase = str(row.get("discovery_phase") or "")
    version_count = int(row.get("version_count") or 1)
    first_observed = row.get("first_observed_at")

    if not published or precision in ("", PRECISION_UNKNOWN):
        if _in_window(first_observed, start, end):
            return UNDATED_FIRST_DISCOVERY, [
                "MedRadar first collected it inside the window",
                "the source states no usable public date, so freshness cannot be claimed",
            ]
        return ARCHIVE_ONLY, ["no public date and no first observation inside the window"]
    if _in_window(published, start, end):
        reasons = ["the source states the event became public inside the window"]
        if phase == PHASE_BACKFILL or origin == ORIGIN_BACKFILLED:
            reasons.append("imported by a declared historical backfill, not discovered live")
        return NEW_EVENT, reasons
    if (version_count > 1 and _in_window(row.get("last_change_at"), start, end)
            and row.get("current_change_state") == CHANGE_UPDATED):
        return UPDATED_EVENT, ["the content of an already known record changed inside the window"]
    if _in_window(first_observed, start, end):
        return FIRST_DISCOVERED_HISTORICAL, [
            "MedRadar first collected it inside the window",
            "the source dates the event before the window: this is a historical supplement",
        ]
    return ARCHIVE_ONLY, ["neither the public date nor the content changed inside the window"]


# --------------------------------------------------------------------------- views
def admission_reasons(row: Mapping[str, Any]) -> list[str]:
    raw = row.get("admission_reasons") or row.get("reasons") or "[]"
    value = _loads(raw, [])
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def view_for(row: Mapping[str, Any], *, novelty: str) -> tuple[str, list[str]]:
    """Decide ARCHIVE / CANDIDATE / INTELLIGENCE for one admitted observation."""
    dimensions = _loads(row.get("dimensions"), {})
    decision = str(row.get("decision") or dimensions.get("decision") or "")
    importance = str(dimensions.get("importance") or "")
    relevance = str(dimensions.get("monitoring_relevance") or "")
    domain = str(dimensions.get("medical_domain") or "")

    if novelty == ARCHIVE_ONLY:
        return ARCHIVE, ["nothing changed about this record inside the window"]
    if decision == "EXCLUDED":
        reasons = admission_reasons(row)
        return ARCHIVE, ["outside the monitoring scope: " + (reasons[0] if reasons else "excluded")]
    if relevance not in DELIVERABLE_RELEVANCE + ("TRANSFER",) or domain != "MEDICAL":
        return ARCHIVE, [
            "admitted to the wider feed but the subject is not monitoring technology ("
            + (relevance or "unclassified") + ")"
        ]
    if novelty == UNDATED_FIRST_DISCOVERY:
        return CANDIDATE, [NOVELTY_LABELS_EN[novelty]]
    if novelty == FIRST_DISCOVERED_HISTORICAL:
        # A historical record collected for the first time is not news. It is flagged only when
        # the grade is high enough that the reader would want to know it exists at all.
        if importance in (IMPORTANCE_CRITICAL, IMPORTANCE_HIGH):
            return CANDIDATE, [NOVELTY_LABELS_EN[novelty], "flagged as a historical supplement"]
        return ARCHIVE, [
            "a historical record first collected now; below the importance bar for a supplement"
        ]

    blockers: list[str] = []
    if not str(row.get("source_url") or "").strip():
        blockers.append("no official URL to cite")
    if not str(row.get("official_identifier") or "").strip():
        blockers.append("no official identifier")
    if importance not in DELIVERABLE_IMPORTANCE:
        blockers.append("importance " + (importance or "ungraded") + " is below the deliverable bar")
    if decision == "REVIEW":
        blockers.append("a reviewer has to confirm the classification")
    if importance == IMPORTANCE_CRITICAL and not admission_reasons(row):
        blockers.append("a CRITICAL grade without a recorded reason")
    if blockers:
        return CANDIDATE, blockers
    return INTELLIGENCE, ["passes the deliverable gate"]


# --------------------------------------------------------------------------- loading
BRIEF_SQL = """
SELECT o.observation_id, o.source, o.source_record_id, o.record_type,
       o.official_identifier, o.title, o.source_url, o.first_observed_at,
       o.observation_origin, o.discovery_phase, o.event_at, o.event_at_precision,
       o.published_at, o.published_at_precision, o.source_updated_at,
       o.source_updated_at_precision, o.last_checked_at, o.version_count,
       o.observation_status, o.current_change_state, o.last_change_at, o.work_key,
       (SELECT i.value FROM observation_identifier i
         WHERE i.observation_id = o.observation_id AND i.kind = 'FDA_RECALL_EVENT'
         LIMIT 1) AS recall_event_id,
       ac.decision, ac.dimensions, ac.reasons AS admission_reasons, ac.category,
       ac.score, ac.admission_version, ac.decided_at
  FROM observation o
  JOIN admission_current ac
    ON ac.observation_id = o.observation_id
   AND ac.admission_version = (
         SELECT MAX(z.admission_version) FROM admission_current z
          WHERE z.observation_id = o.observation_id)
 WHERE 1 = 1
"""


def load_admitted(ledger, *, since: str | None = None, limit: int = 0) -> list[dict[str, Any]]:
    """Every observation with its current decision. No payload yet: it is hydrated on demand.

    The SQL filter is an optimisation only; the caller re-checks the window because novelty also
    depends on the first-observed time.
    """
    sql = BRIEF_SQL
    params: list[Any] = []
    if since:
        sql += (
            " AND (substr(COALESCE(o.published_at, o.event_at), 1, 10) >= ?"
            "      OR substr(o.first_observed_at, 1, 10) >= ?"
            "      OR substr(o.last_change_at, 1, 10) >= ?)"
        )
        params.extend([since, since, since])
    sql += (
        " ORDER BY COALESCE(o.published_at, o.event_at, o.first_observed_at) DESC,"
        " o.observation_id"
    )
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    rows = [dict(row) for row in ledger.raw(sql, tuple(params))]
    for row in rows:
        row["dimensions"] = json.dumps(_loads(row.get("dimensions"), {}))
    return rows


def hydrate(ledger, rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach the latest payload and the mapped facets to the rows that need them.

    Batched so a 20k-observation ledger never builds one giant parameter list.
    """
    result = [dict(row) for row in rows]
    ids = [str(row["observation_id"]) for row in result]
    payloads: dict[str, Any] = {}
    facets: dict[str, list[dict[str, Any]]] = {}
    for offset in range(0, len(ids), 400):
        chunk = ids[offset:offset + 400]
        marks = ",".join("?" for _ in chunk)
        for item in ledger.raw(
            "SELECT v.observation_id, v.payload FROM observation_version v"
            " JOIN observation o ON o.latest_version_id = v.version_id"
            " WHERE v.observation_id IN (" + marks + ")",
            tuple(chunk),
        ):
            payloads[str(item["observation_id"])] = _loads(item.get("payload"), {})
        for item in ledger.raw(
            "SELECT observation_id, kind, value, confirmation FROM observation_facet"
            " WHERE observation_id IN (" + marks + ") ORDER BY kind, value",
            tuple(chunk),
        ):
            facets.setdefault(str(item["observation_id"]), []).append(dict(item))
    for row in result:
        key = str(row["observation_id"])
        row["payload"] = payloads.get(key) or {}
        row["facets"] = facets.get(key) or []
    return result


# --------------------------------------------------------------------------- item fields
def _first_organization(row: Mapping[str, Any]) -> str | None:
    for facet in row.get("facets") or ():
        if facet.get("kind") == "organization":
            return str(facet.get("value") or "") or None
    return None


def _device_and_company(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("payload") or {}
    if is_recall_payload(payload):
        official = payload.get("openfda_device") or {}
        return {
            "company": str(payload.get("recalling_firm") or "").strip() or None,
            "device": str(payload.get("product_description") or "").strip() or None,
            "device_class": str((official or {}).get("device_class") or "").strip() or None,
            "official_device_name": str((official or {}).get("device_name") or "").strip() or None,
            "product_code": str(payload.get("product_code") or "").strip() or None,
        }
    return {
        "company": _first_organization(row),
        "device": None,
        "device_class": None,
        "official_device_name": None,
        "product_code": None,
    }


def _what_happened(row: Mapping[str, Any]) -> str:
    payload = row.get("payload") or {}
    if is_recall_payload(payload):
        reason = " ".join(str(payload.get("reason_for_recall") or "").split())
        if reason:
            return reason
        return " ".join(str(payload.get("product_description") or "").split())
    abstract = " ".join(str(payload.get("abstract") or "").split())
    return abstract or " ".join(str(row.get("title") or "").split())


def _why_it_matters(row: Mapping[str, Any], device: Mapping[str, Any]) -> tuple[str, str]:
    """Why this is monitoring safety or performance evidence, and what the statement rests on."""
    dimensions = _loads(row.get("dimensions"), {})
    relevance = str(dimensions.get("monitoring_relevance") or "")
    payload = row.get("payload") or {}
    if is_recall_payload(payload):
        code = str(device.get("product_code") or "unstated")
        name = str(device.get("official_device_name") or "the device class the code denotes")
        basis = (
            "FDA product code " + code + " (" + name + ") is classified by the committed taxonomy "
            "as a monitoring device family, and this record is an official safety action on it"
        )
        return basis, "rule + source"
    reasons = admission_reasons(row)
    if reasons:
        return " / ".join(reasons[:3]), "rule"
    return "admitted as monitoring technology (" + (relevance or "unclassified") + ")", "rule"


def _rd_attention(row: Mapping[str, Any]) -> tuple[str, str]:
    """A rule-derived suggestion of what a monitoring R&D team may need to check.

    A template keyed on the record type and the source's own root cause, not a claim about the
    reader's product. The basis is recorded so the reader can discount it.
    """
    payload = row.get("payload") or {}
    if not is_recall_payload(payload):
        return (
            "Check whether the evaluated method or measurement applies to your product line, and "
            "whether the validation design is comparable to yours",
            "rule",
        )
    root_cause = " ".join(str(payload.get("root_cause_description") or "").split()).lower()
    suggestions: list[str] = []
    if "software" in root_cause:
        suggestions.append("software defect: look for the same failure mode in your firmware and its test coverage")
    if "labeling" in root_cause or "labelling" in root_cause:
        suggestions.append("labeling defect: check the manual's alarm and measurement wording")
    if "component" in root_cause or "material" in root_cause:
        suggestions.append("component or material defect: check the affected part and its supplier")
    if "design" in root_cause:
        suggestions.append("design defect: check whether your device shares the same design assumption")
    if "nonconforming" in root_cause or "process" in root_cause:
        suggestions.append("process defect: check the affected production or service step")
    if not suggestions:
        suggestions.append("identify the failure mode from the official action and check it against your device")
    suggestions.append("confirm whether the affected models or serial ranges include devices you support")
    return "; ".join(suggestions), "rule"


def _uncertainty(row: Mapping[str, Any], novelty: str, review: str) -> list[str]:
    payload = row.get("payload") or {}
    notes: list[str] = []
    if is_recall_payload(payload):
        notes.append(
            "one FDA recall event can list several product records; this item is one event, and "
            "the models it names may not be the models you support"
        )
        status = str(payload.get("recall_status") or "").strip()
        if status:
            notes.append("the source-stated action status is " + status)
        terminated = str(payload.get("event_date_terminated") or "").strip()
        if terminated:
            notes.append("the source states the action ended on " + terminated)
    precision = effective_precision(
        row.get("published_at") or row.get("event_at"),
        str(row.get("published_at_precision") or row.get("event_at_precision") or "unknown"),
    )
    if precision in ("year", "month"):
        notes.append("the source states the date at " + precision + " precision, not to the day")
    if not row.get("published_at"):
        notes.append("the source states no publication date for this record")
    if novelty == FIRST_DISCOVERED_HISTORICAL:
        notes.append("this is a historical event that MedRadar only collected now")
    if novelty == UNDATED_FIRST_DISCOVERY:
        notes.append("the public date is unknown, so this cannot be called new")
    if review != REVIEW_HUMAN_CONFIRMED:
        notes.append("no human reviewer has confirmed this item")
    return notes


def _dates(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_date": row.get("event_at"),
        "event_date_precision": effective_precision(
            row.get("event_at"), str(row.get("event_at_precision") or "unknown")),
        "published_date": row.get("published_at"),
        "published_date_precision": effective_precision(
            row.get("published_at"), str(row.get("published_at_precision") or "unknown")),
        "first_observed_at": row.get("first_observed_at"),
        "source_updated_at": row.get("source_updated_at"),
    }


def build_item(row: Mapping[str, Any], *, novelty: str, review: str) -> dict[str, Any]:
    dimensions = _loads(row.get("dimensions"), {})
    device = _device_and_company(row)
    why, why_basis = _why_it_matters(row, device)
    attention, attention_basis = _rd_attention(row)
    return {
        "event_identity": event_identity(row),
        "observation_id": row.get("observation_id"),
        "source": row.get("source"),
        "source_url": row.get("source_url"),
        "official_identifier": row.get("official_identifier"),
        "title": row.get("title"),
        "dates": _dates(row),
        "discovery_phase": row.get("discovery_phase"),
        "observation_origin": row.get("observation_origin"),
        "novelty": novelty,
        "novelty_label": NOVELTY_LABELS_EN[novelty],
        "device": device,
        "what_happened": _what_happened(row),
        "why_it_matters": why,
        "importance": dimensions.get("importance"),
        "importance_reasons": _loads(dimensions.get("importance_reasons"), []),
        "monitoring_relevance": dimensions.get("monitoring_relevance"),
        "confidence": dimensions.get("confidence"),
        "rd_attention": attention,
        "uncertainty": _uncertainty(row, novelty, review),
        "review_status": review,
        "review_label": REVIEW_LABELS_EN[review],
        "field_basis": {
            "what_happened": "source (verbatim, trimmed)",
            "why_it_matters": why_basis,
            "importance": "rule (assessment.grade_importance)",
            "rd_attention": attention_basis,
            "uncertainty": "rule",
        },
        "category": row.get("category"),
        "decided_at": row.get("decided_at"),
        "admission_version": row.get("admission_version"),
    }


def _importance_rank(level: Any) -> int:
    try:
        return IMPORTANCE_LEVELS.index(str(level))
    except ValueError:
        return len(IMPORTANCE_LEVELS)


# --------------------------------------------------------------------------- the brief
@dataclass
class Brief:
    start: str
    end: str
    generated_at: str
    policy_version: str = POLICY_VERSION
    items: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    historical: list[dict[str, Any]] = field(default_factory=list)
    undated: list[dict[str, Any]] = field(default_factory=list)
    duplicate_events: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)
    limits: list[str] = field(default_factory=list)
    index: dict[str, dict[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "window": {"start": self.start, "end": self.end},
            "generated_at": self.generated_at,
            "counts": self.counts,
            "items": self.items,
            "candidates": self.candidates,
            "historical_supplements": self.historical,
            "undated": self.undated,
            "duplicate_events": self.duplicate_events,
            "limits": self.limits,
            "index": self.index,
        }


def _collapse(rows: Sequence[dict[str, Any]], *, review: Mapping[str, str],
              max_items: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One item per event identity, keeping the most important row and reporting the rest."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(event_identity(row), []).append(row)
    kept: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for identity, group in grouped.items():
        group.sort(key=lambda row: (
            _importance_rank(_loads(row.get("dimensions"), {}).get("importance")),
            str(row.get("published_at") or row.get("event_at") or ""),
        ))
        best = group[0]
        status = review.get(identity) or review.get(str(best.get("observation_id"))) or REVIEW_NOT_REVIEWED
        kept.append(build_item(best, novelty=str(best.get("_novelty")), review=status))
        if len(group) > 1:
            duplicates.append({
                "event_identity": identity,
                "kept_observation_id": best.get("observation_id"),
                "collapsed_rows": len(group) - 1,
            })
    # Newest first, then most important first: two stable sorts, so within one importance level
    # the most recently published event is on top.
    kept.sort(key=lambda item: str(item["dates"].get("published_date") or ""), reverse=True)
    kept.sort(key=lambda item: _importance_rank(item.get("importance")))
    return kept, duplicates


def build_brief(ledger, *, start: str, end: str, generated_at: str,
                review: Mapping[str, str] | None = None,
                max_items: int = 15) -> Brief:
    """Build one weekly brief from the ledger. Read-only: it writes nothing.

    review maps an event identity or observation id to a REVIEW_* state. An item with no entry is
    reported as NOT_REVIEWED instead of being presented as checked.
    """
    start_day, end_day = date.fromisoformat(start), date.fromisoformat(end)
    if start_day > end_day:
        raise ValueError("the brief window start is after its end")
    review = dict(review or {})
    rows = load_admitted(ledger, since=start_day.isoformat())

    views = {ARCHIVE: 0, CANDIDATE: 0, INTELLIGENCE: 0}
    novelty_counts = {state: 0 for state in NOVELTY_STATES}
    excluded_reasons: dict[str, int] = {}
    index: dict[str, dict[str, Any]] = {}
    selected: list[dict[str, Any]] = []

    for row in rows:
        novelty, _novelty_reasons = distinguish_novelty(row, start=start_day, end=end_day)
        view, view_reasons = view_for(row, novelty=novelty)
        identity = event_identity(row)
        index[identity] = {"view": view, "novelty": novelty}
        views[view] += 1
        novelty_counts[novelty] += 1
        dimensions = _loads(row.get("dimensions"), {})
        if str(row.get("decision") or "") == "EXCLUDED" and novelty != ARCHIVE_ONLY:
            reason = view_reasons[0] if view_reasons else "excluded"
            excluded_reasons[reason] = excluded_reasons.get(reason, 0) + 1
        if view == ARCHIVE:
            continue
        row["_novelty"] = novelty
        row["_view"] = view
        row["_view_reasons"] = view_reasons
        row["_importance"] = dimensions.get("importance")
        selected.append(row)

    hydrated = hydrate(ledger, selected)
    intelligence_rows = [row for row in hydrated if row.get("_view") == INTELLIGENCE]
    candidate_rows = [row for row in hydrated if row.get("_view") != INTELLIGENCE]

    items, duplicates = _collapse(intelligence_rows, review=review, max_items=max_items)
    overflow = max(0, len(items) - max_items)
    items = items[:max_items]

    historical_rows = [row for row in candidate_rows
                       if row.get("_novelty") == FIRST_DISCOVERED_HISTORICAL
                       and _importance_rank(row.get("_importance")) <= 1]
    undated_rows = [row for row in candidate_rows
                    if row.get("_novelty") == UNDATED_FIRST_DISCOVERY]
    other_rows = [row for row in candidate_rows
                  if row not in historical_rows and row not in undated_rows]

    def _items(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        collapsed, _ = _collapse(rows, review=review, max_items=limit)
        return collapsed[:limit]

    historical = _items(historical_rows, 5)
    undated = _items(undated_rows, 5)
    candidates = _items(other_rows, 10)

    by_source: dict[str, int] = {}
    importance_counts = {level: 0 for level in IMPORTANCE_LEVELS}
    for item in items:
        by_source[str(item.get("source"))] = by_source.get(str(item.get("source")), 0) + 1
        level = str(item.get("importance"))
        if level in importance_counts:
            importance_counts[level] += 1

    limits = [
        "Only sources the radar registry marks ENABLED were read: openFDA clearances and recalls, "
        "PubMed, Crossref, the Philips newsroom and the Draeger newsroom. GE HealthCare is "
        "BLOCKED_BY_ACCESS_POLICY, so its feed is not monitored.",
        "No NMPA (China), EU MDR/EUDAMED or health-canada source is connected. An action published "
        "only there cannot appear, so absence from this brief is not evidence of absence.",
        "Importance is a rule-based grade over the source's own fields. It is not a clinical "
        "judgement and it is not a probability.",
        "Everything here is derived from the observation ledger; no field is generated by a model.",
    ]
    if any(item.get("review_status") != REVIEW_HUMAN_CONFIRMED for item in items):
        limits.append("At least one item has not been reviewed by a human; see review_status.")

    return Brief(
        start=start,
        end=end,
        generated_at=generated_at,
        items=items,
        candidates=candidates,
        historical=historical,
        undated=undated,
        duplicate_events=duplicates,
        counts={
            "loaded_observations": len(rows),
            "views": views,
            "novelty": novelty_counts,
            "items": len(items),
            "items_overflow_over_max": overflow,
            "events_collapsed_from_rows": sum(item["collapsed_rows"] for item in duplicates),
            "importance": importance_counts,
            "by_source": by_source,
            "excluded_in_window": sum(excluded_reasons.values()),
            "excluded_reasons": dict(sorted(excluded_reasons.items(), key=lambda kv: -kv[1])[:8]),
            "historical_supplements": len(historical),
            "undated": len(undated),
            "candidates": len(candidates),
        },
        limits=limits,
        index=index,
    )


# --------------------------------------------------------------------------- rendering
_COLUMNS = ("title", "event_date", "first_observed_at", "source", "device", "importance")


def _cell(value: Any, limit: int = 0) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split()).replace("|", "/")
    if limit and len(text) > limit:
        text = text[: limit - 1] + "\u2026"
    return text


def render_markdown(brief: Brief, *, title: str = "MedRadar 监护设备情报周报") -> str:
    """Render the brief as Markdown. Every field states where it came from."""
    counts = brief.counts
    lines: list[str] = []
    lines.append("# " + title)
    lines.append("")
    lines.append("- 窗口 / window: " + brief.start + " .. " + brief.end)
    lines.append("- 生成时间 / generated_at: " + brief.generated_at)
    lines.append("- 策略版本 / policy: " + brief.policy_version)
    lines.append("- 账本观测总数 / observations loaded: " + str(counts.get("loaded_observations")))
    views = counts.get("views") or {}
    lines.append(
        "- 视图 / views: ARCHIVE " + str(views.get("ARCHIVE")) + " · CANDIDATE "
        + str(views.get("CANDIDATE")) + " · INTELLIGENCE " + str(views.get("INTELLIGENCE"))
    )
    novelty = counts.get("novelty") or {}
    lines.append(
        "- 新颖度 / novelty: 本周公开 " + str(novelty.get("NEW_EVENT"))
        + " · 本周更新 " + str(novelty.get("UPDATED_EVENT"))
        + " · 历史首次采集 " + str(novelty.get("FIRST_DISCOVERED_HISTORICAL"))
        + " · 日期不明 " + str(novelty.get("UNDATED_FIRST_DISCOVERY"))
        + " · 无变化 " + str(novelty.get("ARCHIVE_ONLY"))
    )
    lines.append("")
    lines.append("## 1. 本周正式情报 / Deliverable intelligence")
    lines.append("")
    if not brief.items:
        lines.append("本期没有满足可交付标准的新情报。No item passed the deliverable gate this window.")
    for number, item in enumerate(brief.items, start=1):
        dates = item["dates"]
        device = item.get("device") or {}
        lines.append("### " + str(number) + ". " + _cell(item.get("title"), 200))
        lines.append("")
        lines.append("- **重要性 / importance**: " + str(item.get("importance")))
        reasons = item.get("importance_reasons") or []
        if reasons:
            lines.append("  - 理由 / reasons: " + " · ".join(_cell(reason) for reason in reasons))
        lines.append(
            "- **事件日期 / event date**: " + str(dates.get("event_date") or "未标注")
            + " (" + str(dates.get("event_date_precision")) + ")"
        )
        lines.append(
            "- **公开日期 / published**: " + str(dates.get("published_date") or "未标注")
            + " (" + str(dates.get("published_date_precision")) + ")"
        )
        lines.append("- **系统发现 / first observed**: " + str(dates.get("first_observed_at")))
        lines.append("- **新颖度 / novelty**: " + str(item.get("novelty_label")))
        lines.append(
            "- **来源 / source**: " + str(item.get("source")) + " · "
            + str(item.get("official_identifier"))
        )
        lines.append("- **原始链接 / source URL**: " + str(item.get("source_url")))
        if device.get("company"):
            lines.append("- **企业 / company**: " + _cell(device.get("company")))
        if device.get("device"):
            lines.append("- **设备 / device**: " + _cell(device.get("device")))
        if device.get("official_device_name"):
            lines.append(
                "- **官方器械分类 / official device class**: "
                + _cell(device.get("official_device_name"))
                + " (class " + str(device.get("device_class")) + ", code "
                + str(device.get("product_code")) + ")"
            )
        lines.append("- **发生了什么 / what happened**: " + _cell(item.get("what_happened"), 900))
        lines.append("- **为什么与监护安全或性能有关 / why it matters**: "
                     + _cell(item.get("why_it_matters")))
        lines.append("- **研发关注点 / R&D attention**: " + _cell(item.get("rd_attention")))
        uncertainty = item.get("uncertainty") or []
        if uncertainty:
            lines.append("- **不确定性 / uncertainty**: " + " · ".join(_cell(note) for note in uncertainty))
        lines.append("- **复核状态 / review**: " + str(item.get("review_label")))
        basis = item.get("field_basis") or {}
        lines.append(
            "- **字段依据 / field basis**: what_happened=" + str(basis.get("what_happened"))
            + "; why=" + str(basis.get("why_it_matters"))
            + "; importance=" + str(basis.get("importance"))
            + "; rd_attention=" + str(basis.get("rd_attention"))
        )
        lines.append("")
    lines.append("## 2. 待人工复核 / Needs review")
    lines.append("")
    if not brief.candidates:
        lines.append("无。None.")
    for item in brief.candidates:
        lines.append(
            "- " + _cell(item.get("title"), 160) + " — " + str(item.get("importance")) + " · "
            + str(item.get("review_label")) + " · " + str(item.get("source_url"))
        )
    lines.append("")
    lines.append("## 3. 历史安全事件补充 / Historical safety supplements")
    lines.append("")
    lines.append("这些不是本周新发生的事件，是本周首次采集到的历史记录。")
    lines.append("")
    if not brief.historical:
        lines.append("无。None.")
    for item in brief.historical:
        lines.append(
            "- " + str(item["dates"].get("published_date")) + " · "
            + _cell(item.get("title"), 160) + " — " + str(item.get("importance")) + " · "
            + str(item.get("review_label")) + " · " + str(item.get("source_url"))
        )
    lines.append("")
    if brief.undated:
        lines.append("## 4. 首次采集但公开日期不明 / First collected, public date not stated")
        lines.append("")
        for item in brief.undated:
            lines.append("- " + _cell(item.get("title"), 160) + " — " + str(item.get("review_label"))
                         + " · " + str(item.get("source_url")))
        lines.append("")
    lines.append("## 5. 本期没有进入简报的内容 / What was set aside")
    lines.append("")
    lines.append(
        "- 窗口内被判定为监护范围之外而排除的观测 / excluded in window: "
        + str(counts.get("excluded_in_window"))
    )
    for reason, count in (counts.get("excluded_reasons") or {}).items():
        lines.append("  - " + str(count) + " × " + _cell(reason))
    lines.append(
        "- 同一事件的多条记录已合并 / rows collapsed into one event: "
        + str(counts.get("events_collapsed_from_rows"))
    )
    lines.append(
        "- 超过本期条数上限而未展示 / over the item cap: " + str(counts.get("items_overflow_over_max"))
    )
    lines.append("")
    lines.append("## 6. 方法与限制 / Method and limits")
    lines.append("")
    for limit in brief.limits:
        lines.append("- " + limit)
    lines.append("")
    lines.append(
        "重要级别由 assessment.grade_importance 依据记录类型、官方召回原因文本、监护相关性、"
        "新鲜度和是否评估测量本身分级，并记录理由；不按比例强行分配。"
    )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- measurement
def _normalise(value: str) -> str:
    return " ".join(str(value or "").lower().replace("-", " ").split())


def evaluate(brief: Brief, reference: Sequence[Mapping[str, Any]] | None = None,
             feedback: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Compute the pilot metrics with explicit denominators and sample limits.

    reference  events found by an independent collection process (see PILOT_PROTOCOL.md):
               each entry needs at least one of event_identity / official_identifier / title.
    feedback   per-item user verdicts: {event_identity, verdict} where verdict is one of
               VALUABLE / ALREADY_KNOWN / NOT_RELEVANT / INACCURATE / INVESTIGATE.

    Nothing is extrapolated: with a handful of items the numbers are counts, not estimates.
    """
    reference = list(reference or [])
    feedback = list(feedback or [])
    identities = set(brief.index)
    titles = {_normalise(item.get("title")): item for item in brief.items}
    delivered_ids = {str(item.get("official_identifier")) for item in brief.items
                     if item.get("official_identifier")}
    delivered_identities = {str(item.get("event_identity")) for item in brief.items}
    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for entry in reference:
        identity = str(entry.get("event_identity") or "").strip()
        official = str(entry.get("official_identifier") or "").strip()
        hit = None
        if identity and identity in identities:
            hit = identity
        elif official:
            for key in identities:
                if key.endswith(":" + official):
                    hit = key
                    break
        if hit is None and official and official in delivered_ids:
            hit = "DELIVERED_OFFICIAL:" + official
        if hit is None and _normalise(entry.get("title")) in titles:
            hit = _normalise(entry.get("title"))
        matched_entry = {**dict(entry), "matched": hit,
                         "delivered": (hit in delivered_identities
                                       or (hit or "").startswith("DELIVERED_OFFICIAL:"))}
        (matched if hit else unmatched).append(matched_entry)

    verdicts: dict[str, int] = {}
    for entry in feedback:
        verdict = str(entry.get("verdict") or "").upper()
        if verdict:
            verdicts[verdict] = verdicts.get(verdict, 0) + 1

    latencies: list[float] = []
    for item in brief.items:
        dates = item.get("dates") or {}
        published = parse_moment(dates.get("published_date") or dates.get("event_date"))
        observed = parse_moment(dates.get("first_observed_at"))
        if published and observed:
            latencies.append((observed - published).total_seconds() / 86400.0)
    latencies.sort()

    reviewed = sum(1 for item in brief.items
                   if str(item.get("review_status")) == REVIEW_HUMAN_CONFIRMED)
    return {
        "policy_version": brief.policy_version,
        "window": {"start": brief.start, "end": brief.end},
        "delivered_items": len(brief.items),
        "reference_events": len(reference),
        "reference_matched": len(matched),
        "reference_delivered_in_brief": sum(1 for entry in matched if entry.get("delivered")),
        "reference_unmatched": len(unmatched),
        "recall": (round(len(matched) / len(reference), 4) if reference else None),
        "reference_unmatched_entries": unmatched,
        "duplicate_events_collapsed": len(brief.duplicate_events),
        "duplicate_rows_collapsed": brief.counts.get("events_collapsed_from_rows"),
        "importance_distribution": brief.counts.get("importance"),
        "reviewed_items": reviewed,
        "review_coverage": (round(reviewed / len(brief.items), 4) if brief.items else None),
        "discovery_latency_days": {
            "n": len(latencies),
            "median": (round(latencies[len(latencies) // 2], 1) if latencies else None),
            "max": (round(latencies[-1], 1) if latencies else None),
        },
        "feedback_counts": verdicts,
        "feedback_positive_share": (
            round(verdicts.get("VALUABLE", 0) / sum(verdicts.values()), 4) if verdicts else None
        ),
        "limitations": [
            "recall is measured against a reference set built by one analyst with its own queries; "
            "it is a lower bound on what exists, not the truth",
            "precision needs user verdicts; without them it is reported as not measured",
            "feedback_positive_share is reported only alongside the counts: a small sample cannot "
            "establish a rate",
        ],
    }
