"""Turn raw backend text into a structured, strictly decoded extraction result.

The parser is the harness's honesty boundary.  A model output either satisfies the
frozen schema or it does not; this module never fills a missing field, never drops
an unknown key to make a payload pass, and never repairs a truncated JSON string.
If the text cannot be decoded, the result carries ``parse_status`` in
``{"invalid_json", "refused", "empty"}``, zero events and a ``parse_error`` detail
that the benchmark's error taxonomy counts.

The contract types live in :mod:`schema`.  ``parse_status`` is a property of the
*parse*, not of the extraction: a model that correctly abstains decodes to
``parse_status="ok"`` with an event whose ``status`` is ``"abstained"``.  A model
that emits prose about being unable to help decodes to ``parse_status="refused"``
with no events at all -- those are different failures and are scored differently.

Design decisions
----------------
* Markdown fences are stripped, and the first *balanced* JSON object/array is
  located inside surrounding prose.  Finding the payload is not repairing it: the
  payload itself is decoded with the strict ``schema`` decoders.
* Model-supplied provenance is discarded.  The caller's ``ExtractorProvenance``
  is stamped onto the result, so a model cannot claim a different adapter or
  schema version.
* Refusal is recognised in English and Chinese because the comparison arm may be
  configured with a model whose refusals are not in English.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable, Mapping

from .schema import (
    SCHEMA_VERSION,
    ContractError,
    EventExtraction,
    ExtractionResult,
    ExtractorProvenance,
    event_from_dict,
    result_from_dict,
)

# Keys accepted at the top level of a result-shaped payload.
_RESULT_KEYS = (
    "doc_id",
    "parse_status",
    "schema_version",
    "extractor",
    "events",
    "raw_output",
)
# Keys accepted inside one event object (mirrors schema._EVENT_KEYS, copied on
# purpose: if the frozen schema adds a field, this module must be updated and the
# test matrix extended rather than silently accepting the new key).
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

_FENCE_RE = re.compile(
    r"^\s*```[A-Za-z0-9_+-]*\s*\n?(?P<body>.*?)\n?\s*```\s*$", re.DOTALL
)

_REFUSAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:i|we)\s+(?:cannot|can\s*not|can't|can’t|am\s+unable|are\s+unable)\b", re.I),
    re.compile(r"\b(?:i|we)\s+(?:won't|will\s+not)\s+(?:help|assist|comply|extract)\b", re.I),
    re.compile(r"\b(?:i'?m|i\s+am)\s+(?:sorry|unable)\b", re.I),
    re.compile(r"\bi\s+apologi[sz]e\b", re.I),
    re.compile(r"\bas\s+an\s+ai\b", re.I),
    re.compile(r"\bunable\s+to\s+(?:help|assist|comply|extract|provide)\b", re.I),
    re.compile(r"无法"),
    re.compile(r"不能"),
    re.compile(r"抱歉"),
    re.compile(r"对不起"),
    re.compile(r"我不会"),
    re.compile(r"拒绝"),
)


@dataclass(frozen=True)
class ParsedExtraction(ExtractionResult):
    """An :class:`ExtractionResult` that also carries the parse-error detail.

    Subclassing the frozen contract keeps the documented signature
    ``parse_response(...) -> ExtractionResult`` true (an instance *is* an
    ``ExtractionResult``) while giving the error taxonomy the detail it needs
    without extending the frozen schema.  ``parse_error`` is ``None`` whenever
    ``parse_status == "ok"``.
    """

    parse_error: str | None = None

    @property
    def failed(self) -> bool:
        return self.parse_status != "ok"


def _coerce_extractor(extractor: ExtractorProvenance | Mapping[str, object]) -> ExtractorProvenance:
    if isinstance(extractor, ExtractorProvenance):
        return extractor
    if isinstance(extractor, Mapping):
        system = extractor.get("system")
        adapter_id = extractor.get("adapter_id")
        if not system or not adapter_id:
            raise TypeError("extractor mapping needs non-empty 'system' and 'adapter_id'")
        return ExtractorProvenance(
            system=str(system),
            adapter_id=str(adapter_id),
            model_id=extractor.get("model_id"),  # type: ignore[arg-type]
            model_revision=extractor.get("model_revision"),  # type: ignore[arg-type]
            prompt_version=extractor.get("prompt_version"),  # type: ignore[arg-type]
            decoding=dict(extractor.get("decoding") or {}),  # type: ignore[arg-type]
            schema_version=str(extractor.get("schema_version") or SCHEMA_VERSION),
        )
    raise TypeError(f"extractor must be ExtractorProvenance, got {type(extractor).__name__}")


def _looks_like_refusal(text: str) -> bool:
    return any(pattern.search(text) for pattern in _REFUSAL_PATTERNS)


def strip_code_fences(text: str) -> str:
    """Remove one surrounding markdown code fence, if present (and nothing else)."""
    match = _FENCE_RE.match(text)
    if match:
        return match.group("body")
    return text


def _balanced_json_at(text: str, start: int) -> str | None:
    opener = text[start]
    if opener not in "{[":
        return None
    stack: list[str] = []
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]":
            if not stack:
                return None
            opened = stack.pop()
            if (opened, char) not in (("{", "}"), ("[", "]")):  # mismatched nesting
                return None
            if not stack:
                return text[start : index + 1]
    return None


def first_balanced_json(text: str, *, max_attempts: int = 64) -> str | None:
    """Return the first balanced JSON object/array inside ``text``, or ``None``.

    Trailing prose after the object is ignored; a truncated object yields
    ``None`` (and therefore an ``invalid_json`` parse status) rather than being
    completed here.
    """
    attempts = 0
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        attempts += 1
        if attempts > max_attempts:
            return None
        candidate = _balanced_json_at(text, index)
        if candidate is not None:
            return candidate
    return None


def _failure(
    text: str | None,
    parse_status: str,
    detail: str,
    *,
    doc_id: str,
    extractor: ExtractorProvenance,
) -> ParsedExtraction:
    return ParsedExtraction(
        doc_id=doc_id,
        parse_status=parse_status,
        extractor=extractor,
        events=(),
        raw_output=text,
        parse_error=detail,
    )


def _events_from_payload(payload: object) -> tuple[EventExtraction, ...]:
    """Strictly decode the events of one payload.

    Accepts (a) an array of event objects, (b) a result-shaped object with an
    ``"events"`` list, (c) a single bare event object.  Anything else is
    ``ContractError``; unknown keys anywhere are rejected by the schema decoders.
    """
    if isinstance(payload, list):
        return tuple(event_from_dict(item) for item in payload)
    if not isinstance(payload, Mapping):
        raise ContractError(f"payload must be a JSON object or array, got {type(payload).__name__}")

    if "events" in payload:
        unknown_top = sorted(set(payload) - set(_RESULT_KEYS))
        if unknown_top:
            raise ContractError(f"result has unknown key(s): {', '.join(unknown_top)}")
        events_raw = payload.get("events")
        if events_raw is None:
            events_raw = []
        if not isinstance(events_raw, list):
            raise ContractError("result.events must be a list")
        return tuple(event_from_dict(event) for event in events_raw)

    # A bare event: every key belongs to the event object and it identifies itself.
    unknown_event = sorted(set(payload) - set(_EVENT_KEYS))
    if unknown_event:
        raise ContractError(f"event has unknown key(s): {', '.join(unknown_event)}")
    if payload and ("event_category" in payload or "status" in payload):
        return (event_from_dict(payload),)
    raise ContractError("payload is neither a result object nor an event object")


def parse_response(
    text: str | None,
    *,
    doc_id: str,
    extractor: ExtractorProvenance | Mapping[str, object],
    schema_version: str = SCHEMA_VERSION,
    finish_reason: str | None = None,
) -> ParsedExtraction:
    """Decode one backend response into an :class:`ExtractionResult`.

    Never raises for malformed model output: all failures become a result with
    ``parse_status`` in ``{"invalid_json", "refused", "empty", "truncated"}`` and
    zero events.

    ``finish_reason`` comes from the backend.  When a generation stopped at the
    token limit (``"length"``) and no balanced JSON object was produced, the
    failure is recorded as ``"truncated"`` rather than ``"invalid_json"``.  Those
    are different defects with different fixes -- an output-budget problem versus
    a conformance problem -- and the Phase 2 report conflated them, which is why
    the 512-token truncation of a multi-event document looked like a JSON bug.
    """
    provenance = _coerce_extractor(extractor)
    if provenance.schema_version != schema_version:
        provenance = ExtractorProvenance(
            system=provenance.system,
            adapter_id=provenance.adapter_id,
            model_id=provenance.model_id,
            model_revision=provenance.model_revision,
            prompt_version=provenance.prompt_version,
            decoding=provenance.decoding,
            schema_version=schema_version,
        )

    if not isinstance(text, str):
        return _failure(None, "empty", "no output text (None or non-string)", doc_id=doc_id, extractor=provenance)
    raw = text
    if not text.strip():
        return _failure(raw, "empty", "empty output text", doc_id=doc_id, extractor=provenance)

    stripped = strip_code_fences(text.strip()).strip()
    candidate = first_balanced_json(stripped)
    if candidate is None:
        if finish_reason == "length":
            return _failure(
                raw,
                "truncated",
                "generation stopped at the token limit before a balanced JSON object was "
                "produced; this is an output-budget failure, not a conformance failure",
                doc_id=doc_id,
                extractor=provenance,
            )
        status = "refused" if _looks_like_refusal(text) else "invalid_json"
        detail = "refusal text without JSON payload" if status == "refused" else "no balanced JSON object/array in output"
        return _failure(raw, status, detail, doc_id=doc_id, extractor=provenance)

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        status = "refused" if _looks_like_refusal(text) else "invalid_json"
        return _failure(raw, status, f"JSON decode error: {exc}", doc_id=doc_id, extractor=provenance)

    if isinstance(payload, Mapping) and "schema_version" in payload:
        declared = payload.get("schema_version")
        if declared != schema_version:
            return _failure(
                raw,
                "invalid_json",
                f"schema_version mismatch: model declared {declared!r}, parser expects {schema_version!r}",
                doc_id=doc_id,
                extractor=provenance,
            )

    try:
        events = _events_from_payload(payload)
    except ContractError as exc:
        status = "refused" if _looks_like_refusal(text) else "invalid_json"
        return _failure(raw, status, f"schema decode error: {exc}", doc_id=doc_id, extractor=provenance)

    # Re-decode through the contract's strict result decoder so the result shape
    # itself is checked in one place; provenance and doc id are then re-stamped so
    # a model can never claim another adapter or another document.
    if isinstance(payload, Mapping) and "events" in payload:
        envelope = {
            key: value
            for key, value in payload.items()
            if key in ("doc_id", "parse_status", "schema_version", "events")
        }
        envelope["doc_id"] = doc_id
        envelope["parse_status"] = "ok"
        envelope["schema_version"] = schema_version
        envelope["extractor"] = provenance.to_dict()
        try:
            decoded = result_from_dict(envelope)
        except ContractError as exc:
            return _failure(raw, "invalid_json", f"result decode error: {exc}", doc_id=doc_id, extractor=provenance)
        events = decoded.events

    return ParsedExtraction(
        doc_id=doc_id,
        parse_status="ok",
        extractor=provenance,
        events=events,
        raw_output=raw,
        parse_error=None,
    )


def parse_batch(
    responses: Mapping[str, str | None] | Iterable[tuple[str, str | None]],
    *,
    extractor: ExtractorProvenance | Mapping[str, object],
    schema_version: str = SCHEMA_VERSION,
) -> dict[str, ParsedExtraction]:
    """Parse many responses, keyed by doc id.  Order of the input is preserved."""
    items = responses.items() if isinstance(responses, Mapping) else responses
    return {
        doc_id: parse_response(
            text, doc_id=doc_id, extractor=extractor, schema_version=schema_version
        )
        for doc_id, text in items
    }


__all__ = [
    "ParsedExtraction",
    "first_balanced_json",
    "parse_batch",
    "parse_response",
    "strip_code_fences",
]
