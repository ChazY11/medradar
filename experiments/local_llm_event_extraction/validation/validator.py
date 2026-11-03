"""The evidence validator: quarantine, never repair.

What this module is for
-----------------------
A small language model can always produce something that *looks* like an event.
The validator's job is to decide whether that output is **scorable evidence** or
a plausible-looking guess, and to do so without ever improving the output.  It
does not fill in missing dates, it does not correct a category, it does not trim
a quote until it matches, and it does not drop a bad event: every event receives
a judgement, and the event object is returned exactly as the extractor produced
it.  The only thing that changes is the *verdict* (and the recorded findings).

Fixed check order
-----------------
Checks run in a stable order so two runs over the same input produce the same
findings in the same order (:data:`CHECK_ORDER`):

1. document parse status (``REJECTED`` unless ``parse_status == "ok"``);
2. ``EVENT_LIMIT_EXCEEDED`` -- events past ``config.max_events_per_document``;
3. schema conformance -- ``SCHEMA_INVALID``;
4. evidence presence -- ``EVIDENCE_MISSING``;
5. abstention shape -- ``ABSTAIN_REASON_MISSING``, ``ABSTAIN_EVIDENCE_PRESENT``;
6. verbatim evidence -- ``QUOTE_NOT_VERBATIM``, ``EVIDENCE_TOO_SHORT``,
   ``EVIDENCE_TOO_LONG``, ``EVIDENCE_QUOTE_NORMALISED`` (info);
7. timestamps -- ``DATE_QUALITY_MISMATCH``, ``DATE_NOT_IN_EVIDENCE``,
   ``DATE_ORDER_VIOLATION``, ``DATE_IN_FUTURE``, ``FIRST_SEEN_MISMATCH``;
8. entity -- ``ENTITY_UNRESOLVED``, ``ENTITY_NOT_IN_ROSTER``,
   ``ENTITY_ALIAS_NOT_IN_DOCUMENT``, ``ENTITY_MODEL_INFERENCE``;
9. closed vocabularies -- ``CATEGORY_UNKNOWN``, ``DOMAIN_UNKNOWN``;
10. duplicates -- ``DUPLICATE_EVENT``.

Stable error codes (:data:`ERROR_CODES`)
---------------------------------------
``SCHEMA_INVALID``, ``EVIDENCE_MISSING``, ``ABSTAIN_REASON_MISSING``,
``ABSTAIN_EVIDENCE_PRESENT``, ``QUOTE_NOT_VERBATIM``, ``EVIDENCE_TOO_SHORT``,
``EVIDENCE_TOO_LONG``, ``EVIDENCE_QUOTE_NORMALISED``, ``DATE_NOT_IN_EVIDENCE``,
``DATE_QUALITY_MISMATCH``, ``DATE_ORDER_VIOLATION``, ``DATE_IN_FUTURE``,
``FIRST_SEEN_MISMATCH``, ``ENTITY_UNRESOLVED``, ``ENTITY_NOT_IN_ROSTER``,
``ENTITY_ALIAS_NOT_IN_DOCUMENT``, ``ENTITY_MODEL_INFERENCE``,
``CATEGORY_UNKNOWN``, ``DOMAIN_UNKNOWN``, ``DUPLICATE_EVENT``,
``EVENT_LIMIT_EXCEEDED``.

Severity mapping (:data:`CODE_SEVERITY`) is the contract: ``ERROR`` =>
``QUARANTINED``; ``WARNING`` => ``ACCEPTED`` with the issue attached; ``INFO`` =>
informational only.  No issue of any severity mutates the event.

Frozen entry point
------------------
::

    validate_extraction(result, *, document, roster, taxonomy, config=ValidationConfig())
        -> ValidationResult

``EntityRoster`` and ``Taxonomy`` are re-exported here because
``contracts.py`` freezes this import path for the benchmark.

Optional configuration extensions
---------------------------------
``ValidationConfig`` is frozen and deliberately has no knobs for every check.
Three deterministic extras are read with ``getattr`` so a caller can supply a
subclass (a frozen dataclass can be subclassed) without editing the contract:

* ``as_of`` -- the future-date boundary (else ``document.metadata["as_of"]``);
* ``allow_event_after_published`` -- skip the ordering rule;
* ``date_order_violation_fatal`` -- promote ``DATE_ORDER_VIOLATION`` to ERROR.

Without an ``as_of`` boundary the future-date check is skipped rather than
defaulting to "today": a time-dependent validator cannot be reproduced.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Mapping, Sequence

from ..contracts import (
    EventJudgement,
    Severity,
    ValidationConfig,
    ValidationIssue,
    ValidationResult,
    Verdict,
)
from ..schema import EVENT_CATEGORIES, ExtractionResult, MAX_QUOTE_CHARS
from .dedup import dedup_key, find_duplicates
from .entities import EntityRoster, Taxonomy
from .evidence import check_quote
from .schema_validator import validate_event_payload
from .timefields import check_event_timestamps, resolve_as_of

__all__ = [
    "CHECK_ORDER",
    "ERROR_CODES",
    "CODE_SEVERITY",
    "validate_extraction",
    "EntityRoster",
    "Taxonomy",
]

CHECK_ORDER: tuple[str, ...] = (
    "document_parse_status",
    "event_limit",
    "schema",
    "evidence_presence",
    "abstention",
    "verbatim_evidence",
    "timestamps",
    "entity",
    "closed_vocabularies",
    "duplicates",
)

ERROR_CODES: tuple[str, ...] = (
    "SCHEMA_INVALID",
    "EVIDENCE_MISSING",
    "ABSTAIN_REASON_MISSING",
    "ABSTAIN_EVIDENCE_PRESENT",
    "QUOTE_NOT_VERBATIM",
    "EVIDENCE_TOO_SHORT",
    "EVIDENCE_TOO_LONG",
    "EVIDENCE_QUOTE_NORMALISED",
    "DATE_NOT_IN_EVIDENCE",
    "DATE_QUALITY_MISMATCH",
    "DATE_ORDER_VIOLATION",
    "DATE_IN_FUTURE",
    "FIRST_SEEN_MISMATCH",
    "ENTITY_UNRESOLVED",
    "ENTITY_NOT_IN_ROSTER",
    "ENTITY_ALIAS_NOT_IN_DOCUMENT",
    "ENTITY_MODEL_INFERENCE",
    "CATEGORY_UNKNOWN",
    "DOMAIN_UNKNOWN",
    "DUPLICATE_EVENT",
    "EVENT_LIMIT_EXCEEDED",
)

CODE_SEVERITY: Mapping[str, Severity] = {
    "SCHEMA_INVALID": Severity.ERROR,
    "EVIDENCE_MISSING": Severity.ERROR,
    "ABSTAIN_REASON_MISSING": Severity.ERROR,
    "ABSTAIN_EVIDENCE_PRESENT": Severity.WARNING,
    "QUOTE_NOT_VERBATIM": Severity.ERROR,
    "EVIDENCE_TOO_SHORT": Severity.ERROR,
    "EVIDENCE_TOO_LONG": Severity.ERROR,
    "EVIDENCE_QUOTE_NORMALISED": Severity.INFO,
    "DATE_NOT_IN_EVIDENCE": Severity.ERROR,
    "DATE_QUALITY_MISMATCH": Severity.ERROR,
    "DATE_ORDER_VIOLATION": Severity.WARNING,
    "DATE_IN_FUTURE": Severity.ERROR,
    "FIRST_SEEN_MISMATCH": Severity.ERROR,
    "ENTITY_UNRESOLVED": Severity.ERROR,
    "ENTITY_NOT_IN_ROSTER": Severity.ERROR,
    "ENTITY_ALIAS_NOT_IN_DOCUMENT": Severity.ERROR,
    "ENTITY_MODEL_INFERENCE": Severity.ERROR,
    "CATEGORY_UNKNOWN": Severity.ERROR,
    "DOMAIN_UNKNOWN": Severity.ERROR,
    "DUPLICATE_EVENT": Severity.ERROR,
    "EVENT_LIMIT_EXCEEDED": Severity.ERROR,
}


# --------------------------------------------------------------------- helpers
def _issue(
    code: str,
    field: str,
    detail: str,
    *,
    severity: Severity | None = None,
) -> ValidationIssue:
    if code not in CODE_SEVERITY:
        raise ValueError(f"unknown validation code {code!r}; add it to ERROR_CODES first")
    return ValidationIssue(
        code=code,
        severity=severity if severity is not None else CODE_SEVERITY[code],
        field=field,
        detail=detail,
    )


def _string_field(payload: Mapping[str, Any], name: str) -> str | None:
    value = payload.get(name)
    if isinstance(value, str) and value:
        return value
    return None


def _company_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    company = payload.get("company")
    return company if isinstance(company, Mapping) else {}


def _evidence_spans(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    evidence = payload.get("evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        return ()
    return tuple(span for span in evidence if isinstance(span, Mapping))


def _has_error(issues: Sequence[ValidationIssue]) -> bool:
    return any(issue.severity is Severity.ERROR for issue in issues)


# ----------------------------------------------------------------- event checks
def _check_abstention(
    payload: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    config: ValidationConfig,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    status = payload.get("status")
    if status != "abstained":
        return issues
    if not payload.get("abstain_reason"):
        issues.append(
            _issue(
                "ABSTAIN_REASON_MISSING",
                "abstain_reason",
                "an 'abstained' event must state one of the closed abstain_reason values",
            )
        )
    if len(evidence) > 1:
        issues.append(
            _issue(
                "ABSTAIN_EVIDENCE_PRESENT",
                "evidence",
                f"an 'abstained' event carries {len(evidence)} evidence spans; an abstention "
                "should cite none or at most one supporting span",
            )
        )
    if not evidence and not config.allow_empty_evidence_for_abstained:
        issues.append(
            _issue(
                "EVIDENCE_MISSING",
                "evidence",
                "config.allow_empty_evidence_for_abstained is false and this abstention has no evidence",
            )
        )
    return issues


def _check_evidence_quotes(
    evidence: Sequence[Mapping[str, Any]],
    *,
    document_text: str,
    config: ValidationConfig,
) -> tuple[list[ValidationIssue], list[str]]:
    issues: list[ValidationIssue] = []
    notes: list[str] = []
    for span_index, span in enumerate(evidence):
        quote = span.get("quote")
        if not isinstance(quote, str) or not quote:
            # Type/shape problems are the schema check's job; locating needs a string.
            continue
        check = check_quote(
            quote,
            document_text=document_text,
            min_chars=config.min_quote_chars,
            max_chars=MAX_QUOTE_CHARS,
            require_verbatim=config.require_verbatim_quote,
        )
        for issue in check.issues:
            issues.append(
                dataclasses.replace(issue, field=f"evidence[{span_index}].{issue.field}")
            )
        if check.note:
            notes.append(f"evidence[{span_index}]: {check.note}")
    return issues, notes


def _check_entity(
    payload: Mapping[str, Any],
    *,
    document_text: str,
    roster: EntityRoster,
    config: ValidationConfig,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    company = _company_payload(payload)
    canonical_id = _string_field(company, "canonical_id")
    raw_text = _string_field(company, "raw_text")
    match_basis = company.get("match_basis")
    if not isinstance(match_basis, str):
        match_basis = "none"
    status = payload.get("status")

    if status == "extracted" and canonical_id is None:
        issues.append(
            _issue(
                "ENTITY_UNRESOLVED",
                "company.canonical_id",
                "an 'extracted' event must resolve the company to a roster canonical id",
            )
        )
    if canonical_id is not None and canonical_id not in roster:
        issues.append(
            _issue(
                "ENTITY_NOT_IN_ROSTER",
                "company.canonical_id",
                f"canonical_id {canonical_id!r} is not in the entity roster "
                f"({len(roster)} canonical ids from configuration)",
            )
        )
    if (
        status == "extracted"
        and match_basis == "model_inference"
        and config.reject_model_inference_entity
    ):
        issues.append(
            _issue(
                "ENTITY_MODEL_INFERENCE",
                "company.match_basis",
                "'model_inference' is not provenance: the model's belief that a document is "
                "about a company is not evidence that the document names it",
            )
        )
    if (
        status == "extracted"
        and config.require_entity_alias_in_document
        and canonical_id is not None
        and match_basis != "document_metadata"
        and canonical_id in roster
    ):
        if not roster.canonical_id_named_in_document(
            canonical_id, document_text, raw_text=raw_text
        ):
            issues.append(
                _issue(
                    "ENTITY_ALIAS_NOT_IN_DOCUMENT",
                    "company.raw_text",
                    f"neither the claimed raw_text {raw_text!r} nor any configured alias of "
                    f"{canonical_id!r} appears verbatim in the document",
                )
            )
    return issues


def _check_closed_vocabularies(
    payload: Mapping[str, Any],
    *,
    taxonomy: Taxonomy,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    category = payload.get("event_category")
    if isinstance(category, str) and category not in EVENT_CATEGORIES:
        issues.append(
            _issue(
                "CATEGORY_UNKNOWN",
                "event_category",
                f"event_category {category!r} is not one of the pre-registered categories "
                f"({len(EVENT_CATEGORIES)} values)",
            )
        )
    domains = payload.get("technology_domains")
    if isinstance(domains, Sequence) and not isinstance(domains, (str, bytes)):
        for term in domains:
            if not isinstance(term, str):
                continue
            if not taxonomy.accepts_technology_domain(term):
                issues.append(
                    _issue(
                        "DOMAIN_UNKNOWN",
                        "technology_domains",
                        f"technology domain {term!r} is neither a declared domain nor a declared "
                        f"track ({len(taxonomy.domain_ids)} domains / {len(taxonomy.track_ids)} tracks)",
                    )
                )
    return issues


def _judge_event(
    index: int,
    payload: Mapping[str, Any],
    *,
    document: Any,
    roster: EntityRoster,
    taxonomy: Taxonomy,
    config: ValidationConfig,
    as_of: Any,
    duplicate_matches: Sequence[Any],
    over_event_limit: bool,
) -> tuple[EventJudgement, list[str]]:
    issues: list[ValidationIssue] = []
    normalizations: list[str] = []
    document_text = document.text
    status = payload.get("status")
    evidence = _evidence_spans(payload)

    # 3. schema conformance.
    schema_validation = validate_event_payload(payload)
    for finding in schema_validation.findings:
        issues.append(
            _issue(
                "SCHEMA_INVALID",
                finding.path or "",
                f"{finding.keyword} violation: {finding.message}",
            )
        )

    # 4. evidence presence for an asserted event.
    if status == "extracted" and not evidence and config.require_evidence_for_extracted:
        issues.append(
            _issue(
                "EVIDENCE_MISSING",
                "evidence",
                "an 'extracted' event carries no EvidenceSpan; an assertion without a quote is "
                "not a scored prediction",
            )
        )

    # 5. abstention shape.
    issues.extend(_check_abstention(payload, evidence, config))

    # 6. verbatim evidence.
    quote_issues, quote_notes = _check_evidence_quotes(
        evidence, document_text=document_text, config=config
    )
    issues.extend(quote_issues)
    normalizations.extend(f"event[{index}].{note}" for note in quote_notes)

    # 7. timestamps.
    issues.extend(
        check_event_timestamps(payload, document=document, config=config, as_of=as_of)
    )

    # 8. entity resolution.
    issues.extend(
        _check_entity(payload, document_text=document_text, roster=roster, config=config)
    )

    # 9. closed vocabularies.
    issues.extend(_check_closed_vocabularies(payload, taxonomy=taxonomy))

    # 10. duplicates (the second and later occurrence is the duplicate).
    for match in duplicate_matches:
        if match.second_index != index:
            continue
        issues.append(
            _issue(
                "DUPLICATE_EVENT",
                "client_ref",
                f"event duplicates event {match.first_index}: {match.detail}",
            )
        )
        break

    if over_event_limit:
        issues.append(
            _issue(
                "EVENT_LIMIT_EXCEEDED",
                "",
                f"event index {index} exceeds max_events_per_document="
                f"{config.max_events_per_document}",
            )
        )

    verdict = Verdict.QUARANTINED if _has_error(issues) else Verdict.ACCEPTED
    judgement = EventJudgement(
        index=index,
        verdict=verdict,
        issues=tuple(issues),
        dedup_key=dedup_key(payload),
    )
    return judgement, normalizations


# ------------------------------------------------------------------- entry point
def validate_extraction(
    result: ExtractionResult,
    *,
    document: Any,
    roster: EntityRoster,
    taxonomy: Taxonomy,
    config: ValidationConfig = ValidationConfig(),
) -> ValidationResult:
    """Validate one extractor's output for one document.

    The result is a :class:`~..contracts.ValidationResult` holding one
    :class:`~..contracts.EventJudgement` per event, in input order.  Nothing is
    filtered out and the input ``result`` is never mutated (its events are frozen
    dataclasses and are only read through ``to_dict()``).

    Document verdict: ``REJECTED`` when ``result.parse_status != "ok"``,
    ``QUARANTINED`` when parsing succeeded but at least one event was quarantined,
    otherwise ``ACCEPTED``.  Event verdicts are independent of the document
    verdict: a quarantined event is reported, never deleted.
    """
    if roster is None:
        raise TypeError("roster is required; build one with EntityRoster.from_config()")
    if taxonomy is None:
        raise TypeError("taxonomy is required; build one with Taxonomy.from_config()")
    if not isinstance(config, ValidationConfig):
        raise TypeError(
            f"config must be a ValidationConfig (a subclass is fine), got {type(config).__name__}"
        )
    if not isinstance(getattr(result, "events", None), Sequence):
        raise TypeError("result.events must be a sequence of events")

    payloads = tuple(event.to_dict() for event in result.events)
    as_of = resolve_as_of(config, document)
    duplicate_matches = find_duplicates(
        payloads, threshold=config.duplicate_jaccard_threshold
    )

    judgements: list[EventJudgement] = []
    normalizations: list[str] = []
    for index, payload in enumerate(payloads):
        judgement, event_notes = _judge_event(
            index,
            payload,
            document=document,
            roster=roster,
            taxonomy=taxonomy,
            config=config,
            as_of=as_of,
            duplicate_matches=duplicate_matches,
            over_event_limit=index >= config.max_events_per_document,
        )
        judgements.append(judgement)
        normalizations.extend(event_notes)

    if result.parse_status != "ok":
        document_verdict = Verdict.REJECTED
    elif any(judgement.verdict is Verdict.QUARANTINED for judgement in judgements):
        document_verdict = Verdict.QUARANTINED
    else:
        document_verdict = Verdict.ACCEPTED

    return ValidationResult(
        doc_id=document.doc_id,
        verdict=document_verdict,
        judgements=tuple(judgements),
        normalizations=tuple(normalizations),
    )
