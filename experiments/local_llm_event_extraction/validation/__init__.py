"""Validation: schema, verbatim evidence, entities, timestamps, duplicates, quarantine.

The entry point is frozen as::

    validate_extraction(result, *, document, roster, taxonomy, config) -> ValidationResult

See :mod:`experiments.local_llm_event_extraction.contracts` for the result types.

The instrument's one rule
-------------------------
Validation **never repairs an output**.  A paraphrase fails, a date the text does
not state fails, a company the document does not name fails, and every event is
still returned with a judgement (QUARANTINED is a verdict, not a deletion).  The
stable error codes live in :data:`ERROR_CODES` (see
:mod:`experiments.local_llm_event_extraction.validation.validator`).

Module map
----------
``schema_validator.py``  dependency-free JSON-Schema subset engine with JSON-pointer findings
``evidence.py``          verbatim quote location under NFC + whitespace collapse only (no fuzzy match)
``entities.py``          EntityRoster / Taxonomy loaded from ``config/`` (deterministic aliases)
``timefields.py``        date parsing, quality/value consistency, "is the date in the quote?"
``dedup.py``             within-document duplicates and cross-document leakage clusters
``validator.py``         the orchestrator: fixed check order, per-event verdict, quarantine
"""

from __future__ import annotations

from ..contracts import (
    EventJudgement,
    Severity,
    ValidationConfig,
    ValidationIssue,
    ValidationResult,
    Verdict,
)
from .dedup import (
    DuplicateCluster,
    DuplicateClusterMember,
    DuplicateMatch,
    dedup_key,
    find_duplicate_clusters,
    find_duplicates,
)
from .entities import DomainRecord, EntityRecord, EntityRoster, Taxonomy, TrackRecord
from .evidence import (
    QuoteCheck,
    QuoteLocation,
    TextBoundary,
    check_quote,
    locate_all_quotes,
    locate_quote,
    normalise_text,
    span_boundary,
)
from .schema_validator import (
    SchemaEngineError,
    SchemaFinding,
    SchemaValidation,
    SchemaValidator,
    validate_event_payload,
    validate_result_payload,
)
from .timefields import (
    DateToken,
    ParsedDate,
    check_timestamp_quality,
    dates_in_text,
    parse_date_value,
)
from .validator import CHECK_ORDER, CODE_SEVERITY, ERROR_CODES, validate_extraction

__all__ = [
    # frozen entry point + error taxonomy
    "validate_extraction",
    "ERROR_CODES",
    "CODE_SEVERITY",
    "CHECK_ORDER",
    # config-driven vocabularies
    "EntityRoster",
    "EntityRecord",
    "Taxonomy",
    "TrackRecord",
    "DomainRecord",
    # contract types re-exported for callers
    "Severity",
    "Verdict",
    "ValidationIssue",
    "EventJudgement",
    "ValidationResult",
    "ValidationConfig",
    # evidence
    "QuoteLocation",
    "QuoteCheck",
    "TextBoundary",
    "normalise_text",
    "locate_quote",
    "locate_all_quotes",
    "check_quote",
    "span_boundary",
    # schema engine
    "SchemaValidator",
    "SchemaFinding",
    "SchemaValidation",
    "SchemaEngineError",
    "validate_event_payload",
    "validate_result_payload",
    # time
    "ParsedDate",
    "DateToken",
    "parse_date_value",
    "dates_in_text",
    "check_timestamp_quality",
    # dedup
    "DuplicateMatch",
    "DuplicateCluster",
    "DuplicateClusterMember",
    "dedup_key",
    "find_duplicates",
    "find_duplicate_clusters",
]
