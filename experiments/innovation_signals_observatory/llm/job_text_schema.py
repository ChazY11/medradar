"""The job-text extraction contract for Phase 4 (new schema; not the event schema).

Why this file exists, and why it is *not* ``local_llm_event_extraction/schema.py``
-------------------------------------------------------------------------------
PR #19's frozen schema extracts **regulatory events** (event category, three
timestamps, company entity, product).  A job posting is a different task: the
output is a function class, a technology track, capability phrases and an
explicit R&D-evidence judgement, and the date on the posting comes from the
source's own ``startDate`` field rather than from extraction.  Reusing the event
schema would mean either lying about the task or dropping the fields the mission
needs (``research/MISSION.md`` Layer 2; ``docs/EXISTING_CAPABILITY_AUDIT.md``
§6).  So the *plumbing* is reused (see ``parsing.py`` and ``validation/evidence.py``
imports at the bottom of this module) and the *contract* is re-declared here.

Design rules carried over from the event schema, deliberately
-------------------------------------------------------------
1. **Absence is representable.**  ``UNCLASSIFIED`` is a value, not a failure.
   ``abstain`` is a first-class result with a closed reason list.  A posting with
   no technical content has a correct output: abstain.
2. **A claim without a verbatim quote is not a claim.**  ``function_class``,
   ``technology_track`` and ``r_and_d_evidence=true`` are structurally invalid
   unless the matching ``*_evidence_quote`` is present.  Every capability phrase
   carries its own quote.  The decoder never fills a quote in.
3. **Closed vocabularies fixed before the run.**  Function classes are the
   mission's vocabulary (identical to the deterministic A-arm vocabulary in
   ``config/recruitment_function_classes.json``); technology tracks are the
   existing ``config/tracks_device.json`` ids.  A model cannot invent a class or
   a track that flatters its output -- an unknown value is a contract error, not
   a scored prediction.
4. **Semantic rules are measured, not silently enforced.**  The rule "a
   commercial/administrative posting must not carry a technology track" is *not*
   a schema constraint: if the model emits a track for a Buyer/Planner, the
   payload is structurally valid and the evaluator counts it as a
   negative-control false positive.  Making it a schema error would hide the very
   failure the programme's prior run made worse after fine-tuning (B 0.000 ->
   C 0.667 negative-control false positives, PR #20).
5. **No confidence / probability field.**  A small model's self-reported
   confidence is not a calibrated probability; the schema cannot invite the
   reader to treat it as one.  Uncertainty is expressed as an optional
   ``uncertainty_note`` string, which is qualitative and quoted in the report.

Nothing here imports a model library or touches the network.
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Collection, Mapping

from experiments.local_llm_event_extraction.parsing import (
    first_balanced_json,
    strip_code_fences,
)
from experiments.local_llm_event_extraction.parsing import (
    _looks_like_refusal as _harness_refusal_check,  # documented private reuse
)
from experiments.local_llm_event_extraction.schema import ContractError, ExtractorProvenance

SCHEMA_VERSION = "medradar.job_text_extraction.v1"
"""Job-text schema version.  Bump only with a documented migration; every run
manifest and prediction record records it."""

FUNCTION_CLASSES: tuple[str, ...] = (
    "CORE_R&D",
    "CLINICAL_R&D",
    "PRODUCT_ENGINEERING",
    "ALGORITHM_SOFTWARE",
    "HARDWARE_SYSTEMS",
    "MANUFACTURING_PROCESS",
    "QUALITY_REGULATORY",
    "SALES_ADMIN_OTHER",
    "UNCLASSIFIED",
)
"""The mission's job-function vocabulary (see
``config/recruitment_function_classes.json``; do not extend here).  The A arm and
the B arm are given the same closed list so a difference in score is a difference
in the classifier, not in the label set."""

RND_FUNCTION_CLASSES: tuple[str, ...] = (
    "CORE_R&D",
    "CLINICAL_R&D",
    "PRODUCT_ENGINEERING",
    "ALGORITHM_SOFTWARE",
    "HARDWARE_SYSTEMS",
)
"""Function classes that assert research/engineering work.  Used by the evaluator
to separate "the model invented an R&D direction" from "the model correctly put a
commercial posting in the commercial bucket".  ``MANUFACTURING_PROCESS`` and
``QUALITY_REGULATORY`` are deliberately *not* here: they are technical functions
but not evidence of an R&D direction."""

UNCLASSIFIED = "UNCLASSIFIED"
TRACK_FIELD_UNCLASSIFIED = "UNCLASSIFIED"
"""The literal the model must emit when no track/function is supported by text.
Using one sentinel for both keeps the prompt and the evaluator simple and makes
'abstained' directly checkable."""

ABSTAIN_REASONS: tuple[str, ...] = (
    "no_technical_content",
    "not_a_job_posting",
    "insufficient_context",
    "ambiguous_function",
    "ambiguous_track",
    "unsupported_by_text",
    "other",
)
"""Closed abstain vocabulary.  ``no_technical_content`` is the correct answer for
the deliberate negative-control postings (Buyer/Planner, Customer Service,
Co-op Non-Tech); the evaluator scores whether the model actually uses it."""

PARSE_STATUSES: tuple[str, ...] = ("ok", "invalid_json", "refused", "empty", "truncated")

MAX_QUOTE_CHARS = 600
MAX_CAPABILITY_PHRASES = 4
MAX_CAPABILITY_TEXT_CHARS = 160
MAX_UNCERTAINTY_CHARS = 400

ARM_C_NOT_RUN_REASON = (
    "NOT_RUN: the only existing QLoRA adapter (PR #20, overnight-2026-11-04) was trained on "
    "regulatory-event text under the frozen event schema (event category, three timestamps, "
    "company entity, product). Job text is a different task with a different output contract, "
    "and the adapter was never trained on job postings. Running it would measure schema/task "
    "incompatibility, not job-text extraction capability, so arm C produces no number here. "
    "This is a statement about the experiment design, not about the model."
)
"""Why arm C has no number in this experiment.  Recorded verbatim in metrics.json,
the ARM_TABLE and the docs so the absence of C can never be re-read as a capability claim."""

#: Repo-root-relative paths for the two vocabularies the contract validates against.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TRACKS_CONFIG = _REPO_ROOT / "config" / "tracks_device.json"


# ----------------------------------------------------------------- vocabularies
def load_track_registry(config_path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Load the existing device taxonomy: ``track_id -> {name_en, domain, keywords...}``.

    This is the *only* technology vocabulary this experiment may use.  It is read
    from ``config/tracks_device.json`` (existing, frozen for this phase); nothing
    is invented here.  A missing/unreadable file yields an empty registry, which
    makes every non-``UNCLASSIFIED`` track a contract error -- fail closed rather
    than silently accepting free-text technology names.
    """
    path = Path(config_path) if config_path is not None else DEFAULT_TRACKS_CONFIG
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    registry: dict[str, dict[str, Any]] = {}
    for track in payload.get("tracks", []):
        track_id = track.get("id")
        if not track_id or not isinstance(track_id, str):
            continue
        registry[track_id] = {
            "name_en": track.get("name_en"),
            "name_zh": track.get("name_zh"),
            "domain": track.get("domain"),
            "keywords": tuple(track.get("keywords") or ()),
            "frontier_keywords": tuple(track.get("frontier_keywords") or ()),
        }
    return registry


@functools.lru_cache(maxsize=4)
def known_track_ids(config_path: str | None = None) -> tuple[str, ...]:
    """The closed set of technology-track ids a valid payload may name."""
    return tuple(sorted(load_track_registry(config_path)))


# ---------------------------------------------------------------------- records
def _require_nonempty_str(value: Any, where: str, *, max_chars: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{where} must be a non-empty string")
    if max_chars is not None and len(value) > max_chars:
        raise ContractError(f"{where} exceeds {max_chars} characters ({len(value)})")
    return value


def _optional_quote(value: Any, where: str) -> str | None:
    """Decode an optional claim quote.

    Declared tolerance (a contract rule, not a silent repair): an empty / blank
    string is the same encoding of "no quote" as JSON ``null``.  Models routinely
    emit ``""`` for an inapplicable field, and failing the whole payload for that
    would measure JSON formatting rather than extraction.  The tolerance cannot
    weaken an actual claim: a non-``UNCLASSIFIED`` label with an empty quote is
    normalised to ``None`` here and then *rejected* by ``JobTextExtraction`` as
    "must carry a quote".
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractError(f"{where} must be null or a string")
    if not value.strip():
        return None
    if len(value) > MAX_QUOTE_CHARS:
        raise ContractError(f"{where} exceeds {MAX_QUOTE_CHARS} characters")
    return value


@dataclass(frozen=True)
class CapabilityPhrase:
    """One capability the posting requires, plus the verbatim span that supports it.

    ``text`` is a short analyst-readable label (a claim).  ``evidence_quote`` is
    the posting substring that supports it.  The evaluator locates the quote in
    the posting; a paraphrase fails.  The quote is what makes the claim checkable;
    ``text`` is not required to be verbatim (it is a label, not a citation).
    """

    text: str
    evidence_quote: str

    def __post_init__(self) -> None:
        _require_nonempty_str(self.text, "capability_phrase.text", max_chars=MAX_CAPABILITY_TEXT_CHARS)
        _require_nonempty_str(self.evidence_quote, "capability_phrase.evidence_quote", max_chars=MAX_QUOTE_CHARS)

    def to_dict(self) -> dict[str, str]:
        return {"text": self.text, "evidence_quote": self.evidence_quote}


@dataclass(frozen=True)
class JobTextExtraction:
    """One posting read by one extractor.  Never silently repaired.

    Structural invariants (all enforced, none of them "filled in"):

    * ``abstain=True``  -> ``abstain_reason`` set, function and track are
      ``UNCLASSIFIED``, no capability phrases, ``r_and_d_evidence=False`` and no
      claim quote may be present.  An abstention that still asserts labels is a
      contract error, not a low-confidence extraction.
    * ``abstain=False`` -> at least one claim was made, and every claim that names
      a function/track/affirmative R&D finding carries its own verbatim quote.
    * ``technology_track`` is either ``UNCLASSIFIED`` or an id from
      ``config/tracks_device.json``; anything else is a contract error so the
      model cannot invent a technology.
    """

    abstain: bool
    abstain_reason: str | None
    function_class: str
    function_evidence_quote: str | None
    technology_track: str
    track_evidence_quote: str | None
    capability_phrases: tuple[CapabilityPhrase, ...] = ()
    r_and_d_evidence: bool = False
    r_and_d_evidence_quote: str | None = None
    uncertainty_note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.abstain, bool):
            raise ContractError("abstain must be a boolean")
        if not isinstance(self.r_and_d_evidence, bool):
            raise ContractError("r_and_d_evidence must be a boolean")
        if self.function_class not in FUNCTION_CLASSES:
            raise ContractError(
                f"unknown function_class {self.function_class!r}; allowed: {list(FUNCTION_CLASSES)}"
            )
        if self.abstain_reason is not None and self.abstain_reason not in ABSTAIN_REASONS:
            raise ContractError(
                f"unknown abstain_reason {self.abstain_reason!r}; allowed: {list(ABSTAIN_REASONS)}"
            )
        if self.technology_track != TRACK_FIELD_UNCLASSIFIED:
            allowed = known_track_ids()
            if self.technology_track not in allowed:
                raise ContractError(
                    f"unknown technology_track {self.technology_track!r}; it must be "
                    f"{TRACK_FIELD_UNCLASSIFIED!r} or one of the {len(allowed)} ids in "
                    "config/tracks_device.json"
                )
        if len(self.capability_phrases) > MAX_CAPABILITY_PHRASES:
            raise ContractError(
                f"capability_phrases has {len(self.capability_phrases)} entries; maximum is "
                f"{MAX_CAPABILITY_PHRASES}"
            )
        if self.uncertainty_note is not None and len(self.uncertainty_note) > MAX_UNCERTAINTY_CHARS:
            raise ContractError(f"uncertainty_note exceeds {MAX_UNCERTAINTY_CHARS} characters")

        if self.abstain:
            if self.abstain_reason is None:
                raise ContractError("an abstained extraction must state abstain_reason")
            if self.function_class != UNCLASSIFIED or self.technology_track != TRACK_FIELD_UNCLASSIFIED:
                raise ContractError(
                    "an abstained extraction must emit UNCLASSIFIED for both function_class and "
                    "technology_track; 'abstain' is not a way to attach unsupported labels"
                )
            if self.capability_phrases:
                raise ContractError("an abstained extraction must not carry capability_phrases")
            if self.r_and_d_evidence:
                raise ContractError("an abstained extraction must not assert r_and_d_evidence")
            if any(
                (self.function_evidence_quote, self.track_evidence_quote, self.r_and_d_evidence_quote)
            ):
                raise ContractError(
                    "an abstained extraction must not carry claim quotes; abstention states that "
                    "nothing was asserted"
                )
            return

        # Non-abstained: it must make at least one claim, and each claim carries a quote.
        made_claim = (
            self.function_class != UNCLASSIFIED
            or self.technology_track != TRACK_FIELD_UNCLASSIFIED
            or bool(self.capability_phrases)
            or self.r_and_d_evidence
        )
        if not made_claim:
            raise ContractError(
                "a non-abstained extraction made no claim at all; either assert something with "
                "evidence or set abstain=true"
            )
        if self.abstain_reason is not None:
            raise ContractError("abstain_reason must be null when abstain is false")
        if self.function_class != UNCLASSIFIED and self.function_evidence_quote is None:
            raise ContractError(
                f"function_class {self.function_class!r} is a claim and must carry "
                "function_evidence_quote; a label without a verbatim quote is not a result"
            )
        if (
            self.technology_track != TRACK_FIELD_UNCLASSIFIED
            and self.track_evidence_quote is None
        ):
            raise ContractError(
                f"technology_track {self.technology_track!r} is a claim and must carry "
                "track_evidence_quote; a label without a verbatim quote is not a result"
            )
        if self.r_and_d_evidence and self.r_and_d_evidence_quote is None:
            raise ContractError(
                "r_and_d_evidence=true is a claim and must carry r_and_d_evidence_quote"
            )
        for index, phrase in enumerate(self.capability_phrases):
            if not isinstance(phrase, CapabilityPhrase):
                raise ContractError(
                    f"capability_phrases[{index}] must be a CapabilityPhrase, got "
                    f"{type(phrase).__name__}"
                )

    # ------------------------------------------------------------------ helpers
    def claim_quotes(self) -> tuple[tuple[str, str], ...]:
        """``(field, quote)`` for every quote this extraction asserts (evidence order)."""
        quotes: list[tuple[str, str]] = []
        if self.function_evidence_quote is not None:
            quotes.append(("function_class", self.function_evidence_quote))
        if self.track_evidence_quote is not None:
            quotes.append(("technology_track", self.track_evidence_quote))
        if self.r_and_d_evidence_quote is not None:
            quotes.append(("r_and_d_evidence", self.r_and_d_evidence_quote))
        for index, phrase in enumerate(self.capability_phrases):
            quotes.append((f"capability_phrases[{index}]", phrase.evidence_quote))
        return tuple(quotes)

    def claimed_direction(self) -> bool:
        """True when this record asserts *any* technology/function direction.

        This is the quantity the negative-control metric counts: a Buyer/Planner
        posting on which the extractor claims a track or an R&D function class has
        a false positive, however many other fields it got "compliant".
        """
        return (
            self.function_class != UNCLASSIFIED
            or self.technology_track != TRACK_FIELD_UNCLASSIFIED
            or self.r_and_d_evidence
            or bool(self.capability_phrases)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "abstain": self.abstain,
            "abstain_reason": self.abstain_reason,
            "function_class": self.function_class,
            "function_evidence_quote": self.function_evidence_quote,
            "technology_track": self.technology_track,
            "track_evidence_quote": self.track_evidence_quote,
            "capability_phrases": [phrase.to_dict() for phrase in self.capability_phrases],
            "r_and_d_evidence": self.r_and_d_evidence,
            "r_and_d_evidence_quote": self.r_and_d_evidence_quote,
            "uncertainty_note": self.uncertainty_note,
        }


@dataclass(frozen=True)
class JobTextResult:
    """Everything one extractor produced for one posting (parse + extraction)."""

    posting_id: str
    parse_status: str
    extractor: ExtractorProvenance
    extraction: JobTextExtraction | None = None
    raw_output: str | None = None
    json_parsed: bool = False
    parse_error: str | None = None

    def __post_init__(self) -> None:
        if self.parse_status not in PARSE_STATUSES:
            raise ContractError(f"unknown parse_status {self.parse_status!r}")
        if not self.posting_id:
            raise ContractError("posting_id is required")
        if self.parse_status == "ok" and self.extraction is None:
            raise ContractError("parse_status 'ok' requires an extraction")
        if self.parse_status != "ok" and self.extraction is not None:
            raise ContractError("a failed parse cannot carry an extraction")

    def to_dict(self, include_raw: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "posting_id": self.posting_id,
            "parse_status": self.parse_status,
            "json_parsed": self.json_parsed,
            "parse_error": self.parse_error,
            "schema_version": SCHEMA_VERSION,
            "extractor": self.extractor.to_dict(),
            "extraction": self.extraction.to_dict() if self.extraction else None,
        }
        if include_raw:
            payload["raw_output"] = self.raw_output
        return payload


# ------------------------------------------------------------- strict decoding
_EXTRACTION_KEYS = (
    "abstain",
    "abstain_reason",
    "function_class",
    "function_evidence_quote",
    "technology_track",
    "track_evidence_quote",
    "capability_phrases",
    "r_and_d_evidence",
    "r_and_d_evidence_quote",
    "uncertainty_note",
)
_RESULT_KEYS = (
    "posting_id",
    "parse_status",
    "json_parsed",
    "parse_error",
    "schema_version",
    "extractor",
    "extraction",
    "raw_output",
)


def _require_mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{where} must be an object, got {type(value).__name__}")
    return value


def _reject_unknown_keys(value: Mapping[str, Any], allowed: Collection[str], where: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise ContractError(f"{where} has unknown key(s): {', '.join(unknown)}")


def _optional_str(value: Any, where: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractError(f"{where} must be a string or null")
    return value


def extraction_from_dict(payload: Any) -> JobTextExtraction:
    """Strict structural decode of one job-text extraction.  Unknown keys are errors."""
    data = _require_mapping(payload, "extraction")
    _reject_unknown_keys(data, _EXTRACTION_KEYS, "extraction")

    missing = sorted(set(_EXTRACTION_KEYS) - set(data))
    if missing:
        raise ContractError(f"extraction is missing required key(s): {', '.join(missing)}")

    phrases_raw = data.get("capability_phrases") or []
    if not isinstance(phrases_raw, list):
        raise ContractError("extraction.capability_phrases must be a list")
    phrases: list[CapabilityPhrase] = []
    for index, item in enumerate(phrases_raw):
        item_data = _require_mapping(item, f"capability_phrases[{index}]")
        _reject_unknown_keys(item_data, ("text", "evidence_quote"), f"capability_phrases[{index}]")
        if "text" not in item_data or "evidence_quote" not in item_data:
            raise ContractError(
                f"capability_phrases[{index}] requires both 'text' and 'evidence_quote'"
            )
        phrases.append(
            CapabilityPhrase(text=item_data["text"], evidence_quote=item_data["evidence_quote"])
        )

    return JobTextExtraction(
        abstain=data.get("abstain", False),
        abstain_reason=_optional_str(data.get("abstain_reason"), "abstain_reason"),
        function_class=data.get("function_class", UNCLASSIFIED),
        function_evidence_quote=_optional_quote(
            data.get("function_evidence_quote"), "function_evidence_quote"
        ),
        technology_track=data.get("technology_track", TRACK_FIELD_UNCLASSIFIED),
        track_evidence_quote=_optional_quote(
            data.get("track_evidence_quote"), "track_evidence_quote"
        ),
        capability_phrases=tuple(phrases),
        r_and_d_evidence=data.get("r_and_d_evidence", False),
        r_and_d_evidence_quote=_optional_quote(
            data.get("r_and_d_evidence_quote"), "r_and_d_evidence_quote"
        ),
        uncertainty_note=_optional_str(data.get("uncertainty_note"), "uncertainty_note"),
    )


def result_from_dict(payload: Any) -> JobTextResult:
    data = _require_mapping(payload, "result")
    _reject_unknown_keys(data, _RESULT_KEYS, "result")
    extractor_raw = _require_mapping(data.get("extractor") or {}, "result.extractor")
    extractor = ExtractorProvenance(
        system=str(extractor_raw.get("system", "")),
        adapter_id=str(extractor_raw.get("adapter_id", "")),
        model_id=extractor_raw.get("model_id"),
        model_revision=extractor_raw.get("model_revision"),
        prompt_version=extractor_raw.get("prompt_version"),
        decoding=dict(extractor_raw.get("decoding") or {}),
        schema_version=str(extractor_raw.get("schema_version") or SCHEMA_VERSION),
    )
    extraction_raw = data.get("extraction")
    status = data.get("parse_status", "ok")
    if status != "ok":
        extraction = None
    elif extraction_raw is None:
        raise ContractError("parse_status 'ok' requires result.extraction")
    else:
        extraction = extraction_from_dict(extraction_raw)
    return JobTextResult(
        posting_id=str(data.get("posting_id", "")),
        parse_status=status,
        extractor=extractor,
        extraction=extraction,
        raw_output=data.get("raw_output"),
        json_parsed=bool(data.get("json_parsed")),
        parse_error=data.get("parse_error"),
    )


# ------------------------------------------------------------------- parsing
def _failure(
    text: str | None,
    status: str,
    detail: str,
    *,
    posting_id: str,
    extractor: ExtractorProvenance,
    json_parsed: bool = False,
) -> JobTextResult:
    return JobTextResult(
        posting_id=posting_id,
        parse_status=status,
        extractor=extractor,
        extraction=None,
        raw_output=text,
        json_parsed=json_parsed,
        parse_error=detail,
    )


def _coerce_extractor(extractor: ExtractorProvenance | Mapping[str, Any]) -> ExtractorProvenance:
    if isinstance(extractor, ExtractorProvenance):
        return extractor
    if isinstance(extractor, Mapping):
        return ExtractorProvenance(
            system=str(extractor.get("system") or ""),
            adapter_id=str(extractor.get("adapter_id") or ""),
            model_id=extractor.get("model_id"),
            model_revision=extractor.get("model_revision"),
            prompt_version=extractor.get("prompt_version"),
            decoding=dict(extractor.get("decoding") or {}),
            schema_version=str(extractor.get("schema_version") or SCHEMA_VERSION),
        )
    raise TypeError(f"extractor must be ExtractorProvenance, got {type(extractor).__name__}")


def _payload_from_text(text: str) -> Any:
    """Extract the first balanced JSON value from a model response (no repair)."""
    stripped = strip_code_fences(text.strip()).strip()
    candidate = first_balanced_json(stripped)
    if candidate is None:
        raise json.JSONDecodeError("no balanced JSON object/array in output", stripped, 0)
    return json.loads(candidate)


def parse_job_response(
    text: str | None,
    *,
    posting_id: str,
    extractor: ExtractorProvenance | Mapping[str, Any],
    finish_reason: str | None = None,
) -> JobTextResult:
    """Decode one model response.  Never raises for malformed model output.

    Distinguishes four different failures because they have four different fixes
    (the same taxonomy the event harness uses):

    ``empty``        no text at all
    ``truncated``    generation hit the token limit before a balanced JSON object
    ``refused``      prose refusal, no JSON payload
    ``invalid_json`` JSON found but not decodable / not schema-valid
    """
    provenance = _coerce_extractor(extractor)
    if provenance.schema_version != SCHEMA_VERSION:
        provenance = ExtractorProvenance(
            system=provenance.system,
            adapter_id=provenance.adapter_id,
            model_id=provenance.model_id,
            model_revision=provenance.model_revision,
            prompt_version=provenance.prompt_version,
            decoding=provenance.decoding,
            schema_version=SCHEMA_VERSION,
        )
    if not isinstance(text, str):
        return _failure(None, "empty", "no output text (None or non-string)", posting_id=posting_id, extractor=provenance)
    if not text.strip():
        return _failure(text, "empty", "empty output text", posting_id=posting_id, extractor=provenance)

    try:
        payload = _payload_from_text(text)
    except json.JSONDecodeError as exc:
        if finish_reason == "length":
            return _failure(
                text,
                "truncated",
                "generation stopped at the token limit before a balanced JSON object was produced",
                posting_id=posting_id,
                extractor=provenance,
            )
        if _harness_refusal_check(text):
            return _failure(
                text,
                "refused",
                "refusal text without a JSON payload",
                posting_id=posting_id,
                extractor=provenance,
            )
        return _failure(
            text,
            "invalid_json",
            f"no balanced JSON object/array in output ({exc})",
            posting_id=posting_id,
            extractor=provenance,
        )

    if isinstance(payload, Mapping) and "extraction" in payload:
        unknown_top = sorted(set(payload) - {"extraction", "posting_id", "schema_version"})
        if unknown_top:
            return _failure(
                text,
                "invalid_json",
                f"result envelope has unknown key(s): {', '.join(unknown_top)}",
                posting_id=posting_id,
                extractor=provenance,
                json_parsed=True,
            )
        raw_extraction = payload.get("extraction")
    else:
        raw_extraction = payload

    try:
        extraction = extraction_from_dict(raw_extraction)
    except ContractError as exc:
        if finish_reason == "length":
            # The output budget ended the generation; the parser may have found a
            # balanced *inner* object (e.g. one capability phrase) which of course
            # is not the extraction. That is an output-budget failure, not a
            # conformance failure, and the two must be counted separately.
            return _failure(
                text,
                "truncated",
                f"output token budget exhausted before a valid extraction was produced: {exc}",
                posting_id=posting_id,
                extractor=provenance,
                json_parsed=True,
            )
        return _failure(
            text,
            "invalid_json",
            f"schema decode error: {exc}",
            posting_id=posting_id,
            extractor=provenance,
            json_parsed=True,
        )
    return JobTextResult(
        posting_id=posting_id,
        parse_status="ok",
        extractor=provenance,
        extraction=extraction,
        raw_output=text,
        json_parsed=True,
        parse_error=None,
    )


def parse_job_batch(
    responses: Mapping[str, str | None],
    *,
    extractor: ExtractorProvenance | Mapping[str, Any],
) -> dict[str, JobTextResult]:
    """Parse many model responses, keyed by posting id (input order preserved)."""
    return {
        posting_id: parse_job_response(
            text, posting_id=posting_id, extractor=extractor
        )
        for posting_id, text in responses.items()
    }


# ------------------------------------------------------------- JSON Schema (v1)
JOB_EXTRACTION_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "medradar/job_text_extraction/v1/job_text",
    "title": "MedRadar job-text extraction record",
    "type": "object",
    "additionalProperties": False,
    "required": list(_EXTRACTION_KEYS),
    "properties": {
        "abstain": {"type": "boolean"},
        "abstain_reason": {"enum": [*ABSTAIN_REASONS, None]},
        "function_class": {"enum": list(FUNCTION_CLASSES)},
        "function_evidence_quote": {
            "type": ["string", "null"],
            "minLength": 1,
            "maxLength": MAX_QUOTE_CHARS,
        },
        "technology_track": {"type": "string", "minLength": 1},
        "track_evidence_quote": {
            "type": ["string", "null"],
            "minLength": 1,
            "maxLength": MAX_QUOTE_CHARS,
        },
        "capability_phrases": {
            "type": "array",
            "maxItems": MAX_CAPABILITY_PHRASES,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "evidence_quote"],
                "properties": {
                    "text": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": MAX_CAPABILITY_TEXT_CHARS,
                    },
                    "evidence_quote": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": MAX_QUOTE_CHARS,
                    },
                },
            },
        },
        "r_and_d_evidence": {"type": "boolean"},
        "r_and_d_evidence_quote": {
            "type": ["string", "null"],
            "minLength": 1,
            "maxLength": MAX_QUOTE_CHARS,
        },
        "uncertainty_note": {"type": ["string", "null"], "maxLength": MAX_UNCERTAINTY_CHARS},
    },
    "allOf": [
        {
            "description": (
                "an abstention asserts nothing: labels are UNCLASSIFIED, no phrases, "
                "no affirmative R&D finding and a closed reason"
            ),
            "if": {"properties": {"abstain": {"const": True}}, "required": ["abstain"]},
            "then": {
                "properties": {
                    "abstain_reason": {"type": "string"},
                    "function_class": {"const": UNCLASSIFIED},
                    "technology_track": {"const": TRACK_FIELD_UNCLASSIFIED},
                    "capability_phrases": {"maxItems": 0},
                    "r_and_d_evidence": {"const": False},
                    "function_evidence_quote": {"const": None},
                    "track_evidence_quote": {"const": None},
                    "r_and_d_evidence_quote": {"const": None},
                }
            },
        },
        {
            "description": "a non-abstained record must not carry an abstain reason",
            "if": {"properties": {"abstain": {"const": False}}, "required": ["abstain"]},
            "then": {"properties": {"abstain_reason": {"const": None}}},
        },
    ],
}

JOB_RESULT_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "medradar/job_text_extraction/v1/result",
    "title": "MedRadar job-text extraction result for one posting",
    "type": "object",
    "additionalProperties": False,
    "required": ["posting_id", "parse_status", "json_parsed", "schema_version", "extractor", "extraction"],
    "properties": {
        "posting_id": {"type": "string", "minLength": 1},
        "parse_status": {"enum": list(PARSE_STATUSES)},
        "json_parsed": {"type": "boolean"},
        "parse_error": {"type": ["string", "null"]},
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
        "extraction": {"$ref": "medradar/job_text_extraction/v1/job_text"},
        "raw_output": {"type": ["string", "null"]},
    },
    "allOf": [
        {
            "description": "a failed parse has no extraction",
            "if": {"properties": {"parse_status": {"not": {"const": "ok"}}}, "required": ["parse_status"]},
            "then": {"properties": {"extraction": {"const": None}}},
        }
    ],
}


def schema_document() -> dict[str, Any]:
    """One self-contained document holding the job-text schema (generated, never hand-edited)."""
    return {
        "$comment": (
            "Generated from experiments/innovation_signals_observatory/llm/job_text_schema.py -- "
            "do not edit by hand."
        ),
        "schema_version": SCHEMA_VERSION,
        "job_text": JOB_EXTRACTION_JSON_SCHEMA,
        "result": JOB_RESULT_JSON_SCHEMA,
    }


def dumps_schema_document(indent: int = 2) -> str:
    return json.dumps(schema_document(), indent=indent, ensure_ascii=False) + "\n"


__all__ = [
    "ABSTAIN_REASONS",
    "ARM_C_NOT_RUN_REASON",
    "CapabilityPhrase",
    "ContractError",
    "DEFAULT_TRACKS_CONFIG",
    "ExtractorProvenance",
    "FUNCTION_CLASSES",
    "JOB_EXTRACTION_JSON_SCHEMA",
    "JOB_RESULT_JSON_SCHEMA",
    "JobTextExtraction",
    "JobTextResult",
    "MAX_CAPABILITY_PHRASES",
    "MAX_QUOTE_CHARS",
    "PARSE_STATUSES",
    "RND_FUNCTION_CLASSES",
    "SCHEMA_VERSION",
    "TRACK_FIELD_UNCLASSIFIED",
    "UNCLASSIFIED",
    "dumps_schema_document",
    "extraction_from_dict",
    "known_track_ids",
    "load_track_registry",
    "parse_job_batch",
    "parse_job_response",
    "result_from_dict",
    "schema_document",
]
