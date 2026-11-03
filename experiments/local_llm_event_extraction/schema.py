"""The structured event-extraction contract (frozen for v0 of the experiment).

Why this file is deliberately boring and strict
----------------------------------------------
Every downstream part of the local-LLM experiment -- the validator, the
benchmark, the training-data builder -- depends on one canonical shape.  If the
shape lives in one place, a model output that satisfies it can be scored, and a
model output that does not can be rejected.  If the shape were re-declared per
script, "validation" would degrade into "whatever the script expected".

Design rules encoded here
-------------------------
1. **Absence is representable.** A field the extractor cannot determine is
   ``None`` (JSON ``null``) plus an explicit quality/status value.  There is no
   sentinel string, no ``"unknown"`` placeholder, no guessed value.
2. **Time is three different things.** ``event_date`` (when the real-world event
   happened), ``published_at`` (when the source published it) and
   ``first_seen_at`` (when *our* collector first observed it) are separate
   fields with separate qualities.  Conflating them is the specific methodological
   error ``research/DATA_PROVENANCE.md`` §1 forbids.
3. **``first_seen_at`` is not the model's to invent.** It is system-supplied data
   about our own collection.  The field exists so a document's own record can be
   carried through, and the validator rejects any value that differs from the
   source record.
4. **Evidence is a quote, not a summary.** ``EvidenceSpan.quote`` must be a
   verbatim span of the source text; the validator locates it exactly.  There is
   no "confidence" field: an uncalibrated self-report is not evidence, and this
   experiment is about measurability.
5. **Categories and qualities are closed vocabularies.** They were fixed before
   any model ran, so a model cannot invent a category that flatters its score.
6. **Availability is derived, not asserted.** MedRadar's timing vocabulary has six
   terms, but only three belong to an *extraction*: when the event happened, when
   the source published it, and when we first saw it. ``available_at`` (the earliest
   instant a historical analyst could have used the fact) and the knowledge cut-off
   ``tau`` are **not** model outputs: they are reconstructed from the source's
   declared publication lag, which is audited per source in
   ``research/studies/early_signal_5firms/EVIDENCE_TIME_AUDIT.json``. A model that
   estimated its own availability would be circular, and a model that filled in
   "today" as the availability date would silently destroy point-in-time validity.
   So :class:`SourceDocument` derives ``available_at`` from ``published_at`` plus a
   declared lag, and :class:`EventExtraction` has no availability field at all.

Nothing in this module imports a model library, opens a network connection, or
reads the medradar databases.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Mapping

SCHEMA_VERSION = "medradar.event_extraction.v1"
"""Bump only with a documented migration; benchmarks record it per run."""

# --------------------------------------------------------------------- vocabulary
EVENT_CATEGORIES: tuple[str, ...] = (
    "regulatory_clearance",
    "regulatory_approval",
    "regulatory_submission",
    "regulatory_negative",
    "safety_recall",
    "clinical_trial_start",
    "clinical_trial_result",
    "product_launch",
    "product_discontinuation",
    "rd_collaboration",
    "m_and_a",
    "partnership",
    "manufacturing_change",
    "patent_grant",
    "scientific_publication",
    "other",
)
"""Pre-registered event categories for medtech public evidence.

Kept small on purpose: a 16-way closed set can be scored per class on a few
hundred human labels; a 200-way taxonomy cannot.  Adding a category is a schema
version bump and must be declared before an evaluation run, never after seeing
which classes a model gets wrong.
"""

SOURCE_TYPES: tuple[str, ...] = (
    "press_release",
    "fda_510k",
    "fda_pma",
    "fda_recall",
    "clinical_trial_record",
    "sec_filing",
    "scientific_publication",
    "product_page",
    "regulatory_notice",
    "other",
)

STATUSES: tuple[str, ...] = ("extracted", "abstained")
"""``abstained`` means: the extractor read the document and declines to assert an
event.  It is a *result*, scored separately from a wrong extraction, and is the
mechanism that keeps a model from guessing a missing date."""

ABSTAIN_REASONS: tuple[str, ...] = (
    "no_event",
    "not_an_event",
    "ambiguous_company",
    "ambiguous_date",
    "ambiguous_category",
    "unsupported_by_text",
    "out_of_scope",
    "insufficient_context",
    "other",
)

MATCH_BASIS: tuple[str, ...] = (
    "document_metadata",
    "roster_alias_verbatim",
    "roster_alias_in_document",
    "model_inference",
    "none",
)
"""How a canonical company id was reached.  Only the first three are acceptable
for an accepted event; ``model_inference`` may be recorded but is quarantined by
the validator because "the model thought this was Medtronic" is not provenance."""

TIMESTAMP_QUALITIES: tuple[str, ...] = (
    "exact_day",
    "exact_month",
    "exact_year",
    "approximate",
    "absent",
    "conflicting",
)
"""Quality of a timestamp field, asserted alongside the value.

``absent`` is mandatory whenever the value is ``None``; ``conflicting`` means the
source states more than one incompatible date and the extractor refuses to pick.
"""

TIMESTAMP_FIELDS: tuple[str, ...] = ("event_date", "published_at", "first_seen_at")

PARSE_STATUSES: tuple[str, ...] = ("ok", "invalid_json", "refused", "empty")

MAX_QUOTE_CHARS = 600
MAX_RATIONALE_CHARS = 400


class ContractError(ValueError):
    """Raised when a payload does not have the contracted *shape*.

    Semantic problems (a quote that is not in the document, a date with no
    support) are findings for the validator, not exceptions from this module.
    """


# ----------------------------------------------------------------------- records
@dataclass(frozen=True)
class SourceDocument:
    """One input document plus the collection metadata we are allowed to know."""

    doc_id: str
    source_type: str
    text: str
    title: str | None = None
    published_at: str | None = None
    first_seen_at: str | None = None
    retrieved_at: str | None = None
    url: str | None = None
    publisher: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.source_type not in SOURCE_TYPES:
            raise ContractError(f"unknown source_type {self.source_type!r}")
        if not self.doc_id:
            raise ContractError("doc_id is required")
        if not isinstance(self.text, str):
            raise ContractError("text must be a string")

    # ------------------------------------------------------------------ derived
    @property
    def availability_lag_days(self) -> int | None:
        """Declared publication lag for this source, or ``None`` when undeclared.

        The lag is an explicit assumption audited in ``EVIDENCE_TIME_AUDIT.json``
        (e.g. 30 days for openFDA bulk extracts, 5 days for the SEC 8-K corpus), not
        something a model may estimate.  An undeclared lag means availability is
        *unknown*, which is different from zero.
        """
        raw = self.metadata.get("availability_lag_days")
        if raw is None or raw == "":
            return None
        try:
            lag = int(str(raw))
        except (TypeError, ValueError):
            return None
        return lag if lag >= 0 else None

    @property
    def available_at(self) -> str | None:
        """Conservative earliest knowledge time, ``published_at + lag``, ISO date.

        Returns ``None`` -- never a guess -- when either the publication date or the
        declared lag is missing, or when the publication date is only month/year
        precise (adding days to ``2022-04`` would fabricate a precision the source
        does not have).
        """
        lag = self.availability_lag_days
        if lag is None or not self.published_at or len(self.published_at) != 10:
            return None
        try:
            published = date.fromisoformat(self.published_at)
        except ValueError:
            return None
        return (published + timedelta(days=lag)).isoformat()

    @property
    def fetched_at(self) -> str | None:
        """Alias for the collection time; the store calls it ``retrieved_at``."""
        return self.retrieved_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source_type": self.source_type,
            "text": self.text,
            "title": self.title,
            "published_at": self.published_at,
            "first_seen_at": self.first_seen_at,
            "retrieved_at": self.retrieved_at,
            "url": self.url,
            "publisher": self.publisher,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class EvidenceSpan:
    """A verbatim span of the source text that supports one output field."""

    quote: str
    field: str
    char_start: int | None = None
    char_end: int | None = None
    locator: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.quote, str) or not self.quote.strip():
            raise ContractError("evidence quote must be a non-empty string")
        if len(self.quote) > MAX_QUOTE_CHARS:
            raise ContractError(f"evidence quote exceeds {MAX_QUOTE_CHARS} characters")
        if not self.field:
            raise ContractError("evidence.field is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "quote": self.quote,
            "field": self.field,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "locator": self.locator,
        }


@dataclass(frozen=True)
class EntityClaim:
    """Company as the extractor identified it, with the basis of the mapping."""

    raw_text: str | None = None
    canonical_id: str | None = None
    match_basis: str = "none"

    def __post_init__(self) -> None:
        if self.match_basis not in MATCH_BASIS:
            raise ContractError(f"unknown match_basis {self.match_basis!r}")
        if self.canonical_id is not None and not self.canonical_id:
            raise ContractError("canonical_id must be null or a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "canonical_id": self.canonical_id,
            "match_basis": self.match_basis,
        }


@dataclass(frozen=True)
class TimestampQuality:
    """Per-field timestamp quality; never inferred from the value."""

    event_date: str = "absent"
    published_at: str = "absent"
    first_seen_at: str = "absent"

    def __post_init__(self) -> None:
        for name in TIMESTAMP_FIELDS:
            value = getattr(self, name)
            if value not in TIMESTAMP_QUALITIES:
                raise ContractError(f"unknown timestamp quality {value!r} for {name}")

    def get(self, name: str) -> str:
        return getattr(self, name)

    def to_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in TIMESTAMP_FIELDS}


@dataclass(frozen=True)
class ExtractorProvenance:
    """Who produced an extraction, with exactly which artefact versions."""

    system: str
    adapter_id: str
    model_id: str | None = None
    model_revision: str | None = None
    prompt_version: str | None = None
    decoding: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.system:
            raise ContractError("extractor.system is required")
        if not self.adapter_id:
            raise ContractError("extractor.adapter_id is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "adapter_id": self.adapter_id,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "prompt_version": self.prompt_version,
            "decoding": dict(self.decoding),
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class EventExtraction:
    """One event as asserted by an extractor.  Never silently repaired."""

    status: str
    company: EntityClaim = field(default_factory=EntityClaim)
    event_category: str | None = None
    technology_domains: tuple[str, ...] = ()
    product_or_technology: str | None = None
    event_date: str | None = None
    published_at: str | None = None
    first_seen_at: str | None = None
    timestamp_quality: TimestampQuality = field(default_factory=TimestampQuality)
    evidence: tuple[EvidenceSpan, ...] = ()
    abstain_reason: str | None = None
    client_ref: str | None = None
    rationale: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ContractError(f"unknown status {self.status!r}")
        if self.event_category is not None and self.event_category not in EVENT_CATEGORIES:
            raise ContractError(f"unknown event_category {self.event_category!r}")
        if self.abstain_reason is not None and self.abstain_reason not in ABSTAIN_REASONS:
            raise ContractError(f"unknown abstain_reason {self.abstain_reason!r}")
        if self.rationale is not None and len(self.rationale) > MAX_RATIONALE_CHARS:
            raise ContractError(f"rationale exceeds {MAX_RATIONALE_CHARS} characters")
        if self.status == "extracted" and not self.evidence:
            # Structural, not semantic: an extracted event with zero evidence is
            # not a scored prediction, it is a hallucination by construction.
            raise ContractError("an 'extracted' event must carry at least one EvidenceSpan")
        if self.status == "abstained" and self.abstain_reason is None:
            raise ContractError("an 'abstained' event must state abstain_reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_ref": self.client_ref,
            "status": self.status,
            "abstain_reason": self.abstain_reason,
            "company": self.company.to_dict(),
            "event_category": self.event_category,
            "technology_domains": list(self.technology_domains),
            "product_or_technology": self.product_or_technology,
            "event_date": self.event_date,
            "published_at": self.published_at,
            "first_seen_at": self.first_seen_at,
            "timestamp_quality": self.timestamp_quality.to_dict(),
            "evidence": [span.to_dict() for span in self.evidence],
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class ExtractionResult:
    """Everything one extractor produced for one document."""

    doc_id: str
    parse_status: str
    extractor: ExtractorProvenance
    events: tuple[EventExtraction, ...] = ()
    raw_output: str | None = None

    def __post_init__(self) -> None:
        if self.parse_status not in PARSE_STATUSES:
            raise ContractError(f"unknown parse_status {self.parse_status!r}")

    def to_dict(self, include_raw: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "doc_id": self.doc_id,
            "parse_status": self.parse_status,
            "schema_version": SCHEMA_VERSION,
            "extractor": self.extractor.to_dict(),
            "events": [event.to_dict() for event in self.events],
        }
        if include_raw:
            payload["raw_output"] = self.raw_output
        return payload


# ------------------------------------------------------------- strict (de)coding
_EVENT_KEYS = (
    "client_ref",
    "status",
    "abstain_reason",
    "company",
    "event_category",
    "technology_domains",
    "product_or_technology",
    "event_date",
    "published_at",
    "first_seen_at",
    "timestamp_quality",
    "evidence",
    "rationale",
)


def _require_mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{where} must be an object, got {type(value).__name__}")
    return value


def _reject_unknown_keys(value: Mapping[str, Any], allowed: tuple[str, ...], where: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise ContractError(f"{where} has unknown key(s): {', '.join(unknown)}")


def _optional_str(value: Any, where: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractError(f"{where} must be a string or null")
    return value


def event_from_dict(payload: Any) -> EventExtraction:
    """Strict structural decode.  Unknown keys are an error, never ignored."""
    data = _require_mapping(payload, "event")
    _reject_unknown_keys(data, _EVENT_KEYS, "event")

    company_raw = _require_mapping(data.get("company") or {}, "event.company")
    _reject_unknown_keys(company_raw, ("raw_text", "canonical_id", "match_basis"), "event.company")
    company = EntityClaim(
        raw_text=_optional_str(company_raw.get("raw_text"), "company.raw_text"),
        canonical_id=_optional_str(company_raw.get("canonical_id"), "company.canonical_id"),
        match_basis=company_raw.get("match_basis") or "none",
    )

    quality_raw = _require_mapping(data.get("timestamp_quality") or {}, "event.timestamp_quality")
    _reject_unknown_keys(quality_raw, TIMESTAMP_FIELDS, "event.timestamp_quality")
    quality = TimestampQuality(
        **{name: quality_raw.get(name, "absent") for name in TIMESTAMP_FIELDS}
    )

    evidence_raw = data.get("evidence") or []
    if not isinstance(evidence_raw, list):
        raise ContractError("event.evidence must be a list")
    evidence = []
    for index, span in enumerate(evidence_raw):
        span_data = _require_mapping(span, f"event.evidence[{index}]")
        _reject_unknown_keys(
            span_data, ("quote", "field", "char_start", "char_end", "locator"),
            f"event.evidence[{index}]",
        )
        try:
            evidence.append(
                EvidenceSpan(
                    quote=span_data["quote"],
                    field=span_data["field"],
                    char_start=span_data.get("char_start"),
                    char_end=span_data.get("char_end"),
                    locator=span_data.get("locator"),
                )
            )
        except KeyError as exc:
            raise ContractError(f"event.evidence[{index}] missing {exc}") from exc

    domains_raw = data.get("technology_domains") or []
    if not isinstance(domains_raw, list) or not all(isinstance(d, str) for d in domains_raw):
        raise ContractError("event.technology_domains must be a list of strings")

    try:
        return EventExtraction(
            client_ref=_optional_str(data.get("client_ref"), "client_ref"),
            status=data.get("status", "extracted"),
            abstain_reason=data.get("abstain_reason"),
            company=company,
            event_category=data.get("event_category"),
            technology_domains=tuple(domains_raw),
            product_or_technology=_optional_str(
                data.get("product_or_technology"), "product_or_technology"
            ),
            event_date=_optional_str(data.get("event_date"), "event_date"),
            published_at=_optional_str(data.get("published_at"), "published_at"),
            first_seen_at=_optional_str(data.get("first_seen_at"), "first_seen_at"),
            timestamp_quality=quality,
            evidence=tuple(evidence),
            rationale=_optional_str(data.get("rationale"), "rationale"),
        )
    except TypeError as exc:  # pragma: no cover - defensive
        raise ContractError(f"event has an unusable field set: {exc}") from exc


def result_from_dict(payload: Any) -> ExtractionResult:
    data = _require_mapping(payload, "result")
    _reject_unknown_keys(
        data, ("doc_id", "parse_status", "extractor", "events", "schema_version", "raw_output"),
        "result",
    )
    extractor_raw = _require_mapping(data.get("extractor") or {}, "result.extractor")
    extractor = ExtractorProvenance(
        system=extractor_raw.get("system", ""),
        adapter_id=extractor_raw.get("adapter_id", ""),
        model_id=extractor_raw.get("model_id"),
        model_revision=extractor_raw.get("model_revision"),
        prompt_version=extractor_raw.get("prompt_version"),
        decoding=dict(extractor_raw.get("decoding") or {}),
        schema_version=extractor_raw.get("schema_version", SCHEMA_VERSION),
    )
    events_raw = data.get("events") or []
    if not isinstance(events_raw, list):
        raise ContractError("result.events must be a list")
    return ExtractionResult(
        doc_id=str(data.get("doc_id", "")),
        parse_status=data.get("parse_status", "ok"),
        extractor=extractor,
        events=tuple(event_from_dict(event) for event in events_raw),
        raw_output=data.get("raw_output"),
    )


# ------------------------------------------------------------- JSON Schema (v1)
_QUALITY_ENUM = list(TIMESTAMP_QUALITIES)
_DATE_PATTERN = r"^\d{4}(-\d{2}(-\d{2})?)?$"

EVENT_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "medradar/event_extraction/v1/event",
    "title": "MedRadar extracted medtech event",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "status", "company", "event_category", "technology_domains",
        "product_or_technology", "event_date", "published_at", "first_seen_at",
        "timestamp_quality", "evidence",
    ],
    "properties": {
        "client_ref": {"type": ["string", "null"]},
        "status": {"enum": list(STATUSES)},
        "abstain_reason": {"enum": [*ABSTAIN_REASONS, None]},
        "company": {
            "type": "object",
            "additionalProperties": False,
            "required": ["raw_text", "canonical_id", "match_basis"],
            "properties": {
                "raw_text": {"type": ["string", "null"]},
                "canonical_id": {"type": ["string", "null"]},
                "match_basis": {"enum": list(MATCH_BASIS)},
            },
        },
        "event_category": {"enum": [*EVENT_CATEGORIES, None]},
        "technology_domains": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "product_or_technology": {"type": ["string", "null"]},
        "event_date": {"type": ["string", "null"], "pattern": _DATE_PATTERN},
        "published_at": {"type": ["string", "null"], "pattern": _DATE_PATTERN},
        "first_seen_at": {"type": ["string", "null"], "pattern": _DATE_PATTERN},
        "timestamp_quality": {
            "type": "object",
            "additionalProperties": False,
            "required": list(TIMESTAMP_FIELDS),
            "properties": {name: {"enum": _QUALITY_ENUM} for name in TIMESTAMP_FIELDS},
        },
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["quote", "field"],
                "properties": {
                    "quote": {"type": "string", "minLength": 1, "maxLength": MAX_QUOTE_CHARS},
                    "field": {"type": "string", "minLength": 1},
                    "char_start": {"type": ["integer", "null"], "minimum": 0},
                    "char_end": {"type": ["integer", "null"], "minimum": 0},
                    "locator": {"type": ["string", "null"]},
                },
            },
        },
        "rationale": {"type": ["string", "null"], "maxLength": MAX_RATIONALE_CHARS},
    },
    "allOf": [
        {
            "description": "an extracted event must carry evidence and a category",
            "if": {"properties": {"status": {"const": "extracted"}}, "required": ["status"]},
            "then": {
                "properties": {
                    "evidence": {"type": "array", "minItems": 1},
                    "event_category": {"type": "string"},
                }
            },
        },
        {
            "description": "an abstained event must state a reason",
            "if": {"properties": {"status": {"const": "abstained"}}, "required": ["status"]},
            "then": {"properties": {"abstain_reason": {"type": "string"}}},
        },
    ],
}

EXTRACTION_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "medradar/event_extraction/v1/result",
    "title": "MedRadar extraction result for one document",
    "type": "object",
    "additionalProperties": False,
    "required": ["doc_id", "parse_status", "schema_version", "extractor", "events"],
    "properties": {
        "doc_id": {"type": "string", "minLength": 1},
        "parse_status": {"enum": list(PARSE_STATUSES)},
        "schema_version": {"const": SCHEMA_VERSION},
        "extractor": {
            "type": "object",
            "additionalProperties": False,
            "required": ["system", "adapter_id"],
            "properties": {
                "system": {"type": "string", "minLength": 1},
                "adapter_id": {"type": "string", "minLength": 1},
                "model_id": {"type": ["string", "null"]},
                "model_revision": {"type": ["string", "null"]},
                "prompt_version": {"type": ["string", "null"]},
                "decoding": {"type": "object"},
                "schema_version": {"type": "string"},
            },
        },
        "events": {"type": "array", "items": {"$ref": "medradar/event_extraction/v1/event"}},
    },
}


def schema_document() -> dict[str, Any]:
    """One self-contained document holding both schemas (committed as JSON)."""
    return {
        "$comment": (
            "Generated from experiments/local_llm_event_extraction/schema.py -- "
            "do not edit by hand. A drift check in the offline test suite compares "
            "this document to the generator."
        ),
        "schema_version": SCHEMA_VERSION,
        "event": EVENT_JSON_SCHEMA,
        "result": EXTRACTION_JSON_SCHEMA,
    }


def dumps_schema_document(indent: int = 2) -> str:
    return json.dumps(schema_document(), indent=indent, ensure_ascii=False, sort_keys=False) + "\n"
