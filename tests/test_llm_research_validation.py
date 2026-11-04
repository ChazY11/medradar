"""Adversarial tests for the evidence validator.

The validator exists to make model output *scorable* rather than *plausible*, so
these tests are written as attacks: a paraphrase, an invented date, a date that
appears only elsewhere in the document, an invented ``first_seen_at``, a company
the document never names, a category outside the closed set, and a duplicate.  In
every case the expected behaviour is a stable error code and a quarantine -- not
a repair, not a deletion, and never a mutation of the input event.

Everything is offline and CPU-only: synthetic documents, synthetic roster and
taxonomy, plus one test that loads the *real* five-firm roster from
``config/universe_v1.json`` to prove the configuration wiring is real.
"""

from __future__ import annotations

import copy
import dataclasses
import json

import pytest

from experiments.local_llm_event_extraction import schema
from experiments.local_llm_event_extraction.contracts import (
    Severity,
    ValidationConfig,
    Verdict,
)
from experiments.local_llm_event_extraction.validation import validator as validator_module
from experiments.local_llm_event_extraction.validation.dedup import find_duplicate_clusters
from experiments.local_llm_event_extraction.validation.entities import (
    EntityRoster,
    Taxonomy,
)
from experiments.local_llm_event_extraction.validation.evidence import (
    locate_quote,
    normalise_text,
    sentence_boundary,
    span_boundary,
)
from experiments.local_llm_event_extraction.validation.schema_validator import (
    validate_event_payload,
)
from experiments.local_llm_event_extraction.validation.timefields import (
    dates_in_text,
    parse_date_value,
)
from experiments.local_llm_event_extraction.validation.validator import (
    CHECK_ORDER,
    CODE_SEVERITY,
    ERROR_CODES,
    validate_extraction,
)

DOC_ID = "doc-1"
AS_OF = "2026-11-04"
DOC_TEXT = (
    "Medtronic said on 2023-05-12 that it received FDA clearance for the MiniMed 780G "
    "insulin pump.\n"
    "The MiniMed 780G is intended for people with diabetes."
)
QUOTE = "Medtronic said on 2023-05-12 that it received FDA clearance"


# ----------------------------------------------------------------- fixtures
def _document(**overrides: object) -> schema.SourceDocument:
    values: dict[str, object] = {
        "doc_id": DOC_ID,
        "source_type": "press_release",
        "text": DOC_TEXT,
        "title": "Medtronic clearance",
        "published_at": "2023-05-13",
        "first_seen_at": "2023-05-16",
        "metadata": {"as_of": AS_OF},
    }
    values.update(overrides)
    return schema.SourceDocument(**values)  # type: ignore[arg-type]


def _event(**overrides: object) -> schema.EventExtraction:
    values: dict[str, object] = {
        "status": "extracted",
        "company": schema.EntityClaim(
            raw_text="Medtronic",
            canonical_id="medtronic",
            match_basis="roster_alias_in_document",
        ),
        "event_category": "regulatory_clearance",
        "technology_domains": ("diabetes",),
        "product_or_technology": "MiniMed 780G",
        "event_date": "2023-05-12",
        "published_at": "2023-05-13",
        "first_seen_at": "2023-05-16",
        "timestamp_quality": schema.TimestampQuality("exact_day", "exact_day", "exact_day"),
        "evidence": (schema.EvidenceSpan(quote=QUOTE, field="event_date"),),
        "rationale": "The clearance and its date are stated in the quoted sentence.",
    }
    values.update(overrides)
    return schema.EventExtraction(**values)  # type: ignore[arg-type]


def _result(
    events: tuple[schema.EventExtraction, ...] = (),
    *,
    parse_status: str = "ok",
) -> schema.ExtractionResult:
    return schema.ExtractionResult(
        doc_id=DOC_ID,
        parse_status=parse_status,
        extractor=schema.ExtractorProvenance(system="scripted", adapter_id="fixture"),
        events=events,
    )


def _roster() -> EntityRoster:
    return EntityRoster.from_synthetic(
        {
            "medtronic": ["MEDTRONIC", "MEDTRONIC MINIMED"],
            "stryker": ["STRYKER"],
        }
    )


def _taxonomy() -> Taxonomy:
    return Taxonomy.from_synthetic(
        tracks=[{"id": "diabetes_cgm", "domain": "diabetes"}],
        domains=[{"id": "diabetes"}, {"id": "cardiovascular"}],
    )


def _validate(
    events: tuple[schema.EventExtraction, ...],
    *,
    document: schema.SourceDocument | None = None,
    config: ValidationConfig | None = None,
    roster: EntityRoster | None = None,
    taxonomy: Taxonomy | None = None,
    parse_status: str = "ok",
):
    return validate_extraction(
        _result(events, parse_status=parse_status),
        document=document or _document(),
        roster=roster or _roster(),
        taxonomy=taxonomy or _taxonomy(),
        config=config or ValidationConfig(),
    )


def _codes(validation_result) -> set[str]:
    return set(validation_result.error_codes)


class _RawEvent:
    """Duck-typed event that carries a payload the frozen dataclass would refuse.

    The frozen ``EventExtraction`` rejects unknown enum members, an unknown
    category and a missing abstain reason *structurally*.  The validator still
    has to handle those shapes defensively (a different extractor or a future
    schema version may hand it one), so these tests construct the payload
    directly and assert on the defensive checks.
    """

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def to_dict(self) -> dict[str, object]:
        return copy.deepcopy(self._payload)


def _raw_payload(**overrides: object) -> dict[str, object]:
    payload = json.loads(json.dumps(_event().to_dict()))
    payload.update(overrides)
    return payload


def _raw_result(payload: dict[str, object]) -> schema.ExtractionResult:
    return schema.ExtractionResult(
        doc_id=DOC_ID,
        parse_status="ok",
        extractor=schema.ExtractorProvenance(system="scripted", adapter_id="fixture"),
        events=(_RawEvent(payload),),  # type: ignore[arg-type]
    )


# ------------------------------------------------------ the good path
def test_correct_event_is_accepted_with_zero_issues() -> None:
    validation = _validate((_event(),))
    assert validation.verdict is Verdict.ACCEPTED
    assert len(validation.judgements) == 1
    judgement = validation.judgements[0]
    assert judgement.verdict is Verdict.ACCEPTED
    assert judgement.issues == ()
    assert judgement.reason_codes == ()
    assert validation.normalizations == ()
    assert validation.error_codes == ()
    assert validation.doc_id == DOC_ID


def test_evidence_is_located_verbatim_with_offsets() -> None:
    location = locate_quote(DOC_TEXT, QUOTE)
    assert location is not None
    assert location.exact_raw
    assert location.raw_text == QUOTE
    assert DOC_TEXT[location.raw_start : location.raw_end] == QUOTE
    assert location.normalised_quote == normalise_text(QUOTE)


def test_sentence_and_paragraph_boundaries_contain_the_quote() -> None:
    location = locate_quote(DOC_TEXT, QUOTE)
    assert location is not None
    sentence = span_boundary(DOC_TEXT, location.raw_start, location.raw_end)
    sentence_text = sentence.text_in(DOC_TEXT)
    assert sentence.unit == "sentence"
    assert QUOTE in sentence_text
    assert sentence_text.startswith("Medtronic")
    assert sentence_text.rstrip().endswith("pump.")

    paragraph = span_boundary(
        DOC_TEXT, location.raw_start, location.raw_end, unit="paragraph"
    )
    assert paragraph.unit == "paragraph"
    assert paragraph.text_in(DOC_TEXT) == DOC_TEXT


# ------------------------------------------------------ evidence attacks
def test_paraphrased_quote_is_quarantined() -> None:
    paraphrase = "Medtronic announced FDA clearance for the MiniMed 780G insulin pump"
    validation = _validate((_event(evidence=(schema.EvidenceSpan(quote=paraphrase, field="event_date"),)),))
    judgement = validation.judgements[0]
    assert judgement.verdict is Verdict.QUARANTINED
    assert "QUOTE_NOT_VERBATIM" in judgement.reason_codes
    assert validation.verdict is Verdict.QUARANTINED


def test_quote_differing_only_by_whitespace_is_accepted_with_recorded_offsets() -> None:
    wrapped_text = DOC_TEXT.replace("2023-05-12 that", "2023-05-12\n\n   that")
    document = _document(text=wrapped_text)
    quote = QUOTE  # single space where the source has a line break and spaces

    location = locate_quote(wrapped_text, quote)
    assert location is not None
    assert location.exact_raw is False
    assert location.raw_text != quote
    assert wrapped_text[location.raw_start : location.raw_end] == location.raw_text
    assert location.normalised_quote == normalise_text(quote)

    validation = _validate((_event(),), document=document)
    judgement = validation.judgements[0]
    assert judgement.verdict is Verdict.ACCEPTED
    assert judgement.reason_codes == ()
    assert validation.verdict is Verdict.ACCEPTED
    assert validation.normalizations, "formatting-only match must be recorded"
    assert "raw span" in validation.normalizations[0]
    info_codes = [issue.code for issue in judgement.issues]
    assert "EVIDENCE_QUOTE_NORMALISED" in info_codes
    assert all(issue.severity is Severity.INFO for issue in judgement.issues)


def test_too_short_quote_is_rejected() -> None:
    config = ValidationConfig(min_quote_chars=len(QUOTE) + 1)
    validation = _validate((_event(),), config=config)
    judgement = validation.judgements[0]
    assert "EVIDENCE_TOO_SHORT" in judgement.reason_codes
    assert judgement.verdict is Verdict.QUARANTINED


# ------------------------------------------------------ date attacks
def test_invented_event_date_is_rejected() -> None:
    validation = _validate((_event(event_date="2024-03-01"),))
    judgement = validation.judgements[0]
    assert "DATE_NOT_IN_EVIDENCE" in judgement.reason_codes
    assert judgement.verdict is Verdict.QUARANTINED


def test_month_only_date_claimed_as_exact_day_is_rejected() -> None:
    event = _event(
        event_date="2023-05",
        timestamp_quality=schema.TimestampQuality("exact_day", "exact_day", "exact_day"),
    )
    validation = _validate((event,))
    judgement = validation.judgements[0]
    assert "DATE_QUALITY_MISMATCH" in judgement.reason_codes
    assert "DATE_NOT_IN_EVIDENCE" not in judgement.reason_codes


def test_date_present_only_elsewhere_in_the_document_is_rejected() -> None:
    text_with_date_elsewhere = (
        "Medtronic announced regulatory clearance for the MiniMed 780G insulin pump.\n"
        "\n"
        "The company said the clearance was granted on 2023-05-12."
    )
    quote = "Medtronic announced regulatory clearance for the MiniMed 780G insulin pump."
    assert "2023-05-12" in text_with_date_elsewhere
    assert "2023-05-12" not in quote
    document = _document(text=text_with_date_elsewhere)
    event = _event(
        event_date="2023-05-12",
        evidence=(schema.EvidenceSpan(quote=quote, field="event_date"),),
    )
    validation = _validate((event,), document=document)
    judgement = validation.judgements[0]
    assert "DATE_NOT_IN_EVIDENCE" in judgement.reason_codes
    assert judgement.verdict is Verdict.QUARANTINED


def test_date_order_violation_is_a_warning_not_a_quarantine() -> None:
    later_text = (
        "Medtronic said on 2023-06-01 that it received FDA clearance for its insulin pump.\n"
        "The pump is intended for people with diabetes."
    )
    document = _document(text=later_text)
    event = _event(
        event_date="2023-06-01",
        evidence=(
            schema.EvidenceSpan(
                quote="Medtronic said on 2023-06-01 that it received FDA clearance",
                field="event_date",
            ),
        ),
    )
    validation = _validate((event,), document=document)
    judgement = validation.judgements[0]
    assert judgement.verdict is Verdict.ACCEPTED
    order_issues = [issue for issue in judgement.issues if issue.code == "DATE_ORDER_VIOLATION"]
    assert len(order_issues) == 1
    assert order_issues[0].severity is Severity.WARNING
    assert "DATE_ORDER_VIOLATION" not in judgement.reason_codes
    assert validation.verdict is Verdict.ACCEPTED


def test_date_order_violation_can_be_made_fatal_by_config() -> None:
    @dataclasses.dataclass(frozen=True)
    class _FatalOrderConfig(ValidationConfig):
        date_order_violation_fatal: bool = True

    later_text = (
        "Medtronic said on 2023-06-01 that it received FDA clearance for its insulin pump.\n"
        "The pump is intended for people with diabetes."
    )
    document = _document(text=later_text)
    event = _event(
        event_date="2023-06-01",
        evidence=(
            schema.EvidenceSpan(
                quote="Medtronic said on 2023-06-01 that it received FDA clearance",
                field="event_date",
            ),
        ),
    )
    validation = _validate((event,), document=document, config=_FatalOrderConfig())
    assert "DATE_ORDER_VIOLATION" in validation.judgements[0].reason_codes
    assert validation.judgements[0].verdict is Verdict.QUARANTINED


def test_future_event_date_is_rejected_when_as_of_is_supplied() -> None:
    future_text = (
        "Medtronic said on 2027-05-12 that it received FDA clearance for its insulin pump.\n"
        "The pump is intended for people with diabetes."
    )
    document = _document(
        text=future_text, published_at=None, first_seen_at=None, metadata={"as_of": AS_OF}
    )
    event = _event(
        event_date="2027-05-12",
        published_at=None,
        first_seen_at=None,
        timestamp_quality=schema.TimestampQuality("exact_day", "absent", "absent"),
        evidence=(
            schema.EvidenceSpan(
                quote="Medtronic said on 2027-05-12 that it received FDA clearance",
                field="event_date",
            ),
        ),
    )
    validation = _validate((event,), document=document)
    assert "DATE_IN_FUTURE" in validation.judgements[0].reason_codes
    assert validation.judgements[0].verdict is Verdict.QUARANTINED


def test_as_of_can_be_supplied_by_an_extended_config() -> None:
    @dataclasses.dataclass(frozen=True)
    class _BoundaryConfig(ValidationConfig):
        as_of: str = AS_OF

    future_text = (
        "Medtronic said on 2027-05-12 that it received FDA clearance for its insulin pump.\n"
        "The pump is intended for people with diabetes."
    )
    document = _document(text=future_text, published_at=None, first_seen_at=None, metadata={})
    event = _event(
        event_date="2027-05-12",
        published_at=None,
        first_seen_at=None,
        timestamp_quality=schema.TimestampQuality("exact_day", "absent", "absent"),
        evidence=(
            schema.EvidenceSpan(
                quote="Medtronic said on 2027-05-12 that it received FDA clearance",
                field="event_date",
            ),
        ),
    )
    without_boundary = _validate((event,), document=document)
    assert "DATE_IN_FUTURE" not in without_boundary.error_codes

    with_boundary = _validate((event,), document=document, config=_BoundaryConfig())
    assert "DATE_IN_FUTURE" in with_boundary.error_codes


def test_invented_first_seen_at_is_rejected() -> None:
    event = _event(first_seen_at="2023-01-01")
    validation = _validate((event,))
    judgement = validation.judgements[0]
    assert "FIRST_SEEN_MISMATCH" in judgement.reason_codes
    assert judgement.verdict is Verdict.QUARANTINED


def test_correct_first_seen_at_passes() -> None:
    validation = _validate((_event(),))
    assert "FIRST_SEEN_MISMATCH" not in validation.error_codes


# ------------------------------------------------------ entity attacks
def test_model_inference_entity_claim_is_quarantined() -> None:
    event = _event(
        company=schema.EntityClaim(
            raw_text="Medtronic", canonical_id="medtronic", match_basis="model_inference"
        )
    )
    validation = _validate((event,))
    judgement = validation.judgements[0]
    assert "ENTITY_MODEL_INFERENCE" in judgement.reason_codes
    assert judgement.verdict is Verdict.QUARANTINED


def test_config_toggle_can_accept_model_inference_entity_claim() -> None:
    event = _event(
        company=schema.EntityClaim(
            raw_text="Medtronic", canonical_id="medtronic", match_basis="model_inference"
        )
    )
    relaxed = ValidationConfig(reject_model_inference_entity=False)
    validation = _validate((event,), config=relaxed)
    assert "ENTITY_MODEL_INFERENCE" not in validation.error_codes
    assert validation.judgements[0].verdict is Verdict.ACCEPTED


def test_company_alias_absent_from_document_is_rejected() -> None:
    event = _event(
        company=schema.EntityClaim(
            raw_text="Stryker", canonical_id="stryker", match_basis="roster_alias_in_document"
        )
    )
    validation = _validate((event,))
    judgement = validation.judgements[0]
    assert "ENTITY_ALIAS_NOT_IN_DOCUMENT" in judgement.reason_codes
    assert judgement.verdict is Verdict.QUARANTINED


def test_canonical_id_outside_the_roster_is_rejected() -> None:
    event = _event(
        company=schema.EntityClaim(
            raw_text="Medtronic", canonical_id="not_a_real_firm", match_basis="roster_alias_in_document"
        )
    )
    validation = _validate((event,))
    assert "ENTITY_NOT_IN_ROSTER" in validation.error_codes


def test_unresolved_company_is_rejected_for_an_extracted_event() -> None:
    event = _event(company=schema.EntityClaim(raw_text="Medtronic", match_basis="none"))
    validation = _validate((event,))
    assert "ENTITY_UNRESOLVED" in validation.error_codes


# ------------------------------------------------------ vocabulary attacks
def test_unknown_technology_domain_is_rejected() -> None:
    event = _event(technology_domains=("quantum_teleportation",))
    validation = _validate((event,))
    judgement = validation.judgements[0]
    assert "DOMAIN_UNKNOWN" in judgement.reason_codes
    assert judgement.verdict is Verdict.QUARANTINED


def test_unknown_category_is_rejected() -> None:
    payload = _raw_payload()
    payload["event_category"] = "miracle_breakthrough"
    validation = validate_extraction(
        _raw_result(payload),
        document=_document(),
        roster=_roster(),
        taxonomy=_taxonomy(),
    )
    judgement = validation.judgements[0]
    assert "CATEGORY_UNKNOWN" in judgement.reason_codes
    assert "SCHEMA_INVALID" in judgement.reason_codes
    assert judgement.verdict is Verdict.QUARANTINED


# ------------------------------------------------------ structural attacks
def test_extracted_event_without_evidence_is_rejected() -> None:
    payload = _raw_payload()
    payload["evidence"] = []
    validation = validate_extraction(
        _raw_result(payload), document=_document(), roster=_roster(), taxonomy=_taxonomy()
    )
    assert "EVIDENCE_MISSING" in validation.error_codes


def test_abstained_event_without_reason_is_rejected() -> None:
    payload = _raw_payload()
    payload["status"] = "abstained"
    payload["abstain_reason"] = None
    payload["evidence"] = []
    validation = validate_extraction(
        _raw_result(payload), document=_document(), roster=_roster(), taxonomy=_taxonomy()
    )
    judgement = validation.judgements[0]
    assert "ABSTAIN_REASON_MISSING" in judgement.reason_codes
    assert judgement.verdict is Verdict.QUARANTINED


def test_abstained_event_with_reason_and_no_evidence_is_accepted() -> None:
    event = schema.EventExtraction(status="abstained", abstain_reason="no_event")
    validation = _validate((event,))
    judgement = validation.judgements[0]
    assert judgement.verdict is Verdict.ACCEPTED
    assert judgement.issues == ()
    assert validation.verdict is Verdict.ACCEPTED


def test_config_toggle_requires_evidence_for_abstained_event() -> None:
    event = schema.EventExtraction(status="abstained", abstain_reason="no_event")
    strict = ValidationConfig(allow_empty_evidence_for_abstained=False)
    validation = _validate((event,), config=strict)
    assert "EVIDENCE_MISSING" in validation.error_codes
    assert validation.judgements[0].verdict is Verdict.QUARANTINED


# ------------------------------------------------------ duplicates
def test_second_identical_event_is_a_duplicate() -> None:
    validation = _validate((_event(), _event()))
    first, second = validation.judgements
    assert first.verdict is Verdict.ACCEPTED
    assert second.verdict is Verdict.QUARANTINED
    assert "DUPLICATE_EVENT" in second.reason_codes
    # schema v2: the product is part of the key, so the key has four segments.
    assert second.dedup_key is not None and second.dedup_key.count("|") == 3
    assert second.dedup_key.split("|")[3] == "minimed 780g"
    assert validation.verdict is Verdict.QUARANTINED


def test_event_limit_exceeded_is_reported_on_excess_events() -> None:
    config = ValidationConfig(max_events_per_document=1)
    validation = _validate((_event(), _event()), config=config)
    assert "EVENT_LIMIT_EXCEEDED" in validation.judgements[1].reason_codes
    assert validation.judgements[1].verdict is Verdict.QUARANTINED


# ------------------------------------------------------ document verdicts
def test_parse_failure_rejects_the_document() -> None:
    validation = _validate((), parse_status="invalid_json")
    assert validation.verdict is Verdict.REJECTED
    assert validation.judgements == ()
    assert validation.to_dict()["verdict"] == "rejected"


def test_document_is_quarantined_when_a_single_event_is_quarantined() -> None:
    validation = _validate((_event(first_seen_at="2020-01-01"),))
    assert validation.verdict is Verdict.QUARANTINED


# ------------------------------------------------------ purity & serialisation
def test_validator_never_mutates_its_input() -> None:
    result = _result((_event(), _event(event_date="2024-01-01")))
    document = _document()
    result_before = result.to_dict()
    document_before = document.to_dict()
    events_before = [event.to_dict() for event in result.events]

    validate_extraction(result, document=document, roster=_roster(), taxonomy=_taxonomy())

    assert result.to_dict() == result_before
    assert document.to_dict() == document_before
    assert [event.to_dict() for event in result.events] == events_before


def test_validation_result_is_json_serialisable() -> None:
    validation = _validate((_event(), _event()))
    payload = validation.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False)
    assert json.loads(encoded) == payload
    assert set(payload) == {
        "doc_id",
        "verdict",
        "schema_version",
        "normalizations",
        "error_codes",
        "judgements",
    }
    for judgement in payload["judgements"]:
        assert set(judgement) == {"index", "verdict", "reason_codes", "dedup_key", "issues"}
        for issue in judgement["issues"]:
            assert set(issue) == {"code", "severity", "field", "detail", "event_index"}


def test_every_reported_code_is_declared_and_documented() -> None:
    assert set(ERROR_CODES) == set(CODE_SEVERITY)
    assert len(ERROR_CODES) == len(set(ERROR_CODES))
    for code in ERROR_CODES:
        assert code in validator_module.__doc__, f"{code} missing from the module docstring"
        assert CODE_SEVERITY[code] in (Severity.ERROR, Severity.WARNING, Severity.INFO)
    assert CHECK_ORDER[0] == "document_parse_status"
    assert len(CHECK_ORDER) == len(set(CHECK_ORDER))

    validation = _validate((_event(), _event(event_date="2024-01-01")))
    for judgement in validation.judgements:
        for issue in judgement.issues:
            assert issue.code in ERROR_CODES


# ------------------------------------------------------ helper module tests
def test_dates_in_text_reports_precision_and_ignores_ambiguous_slash_dates() -> None:
    tokens = dates_in_text("signed on 2023-05-12, announced May 2023, filed 12 March 2024, saw 05/12/2023")
    rendered = {(token.text, token.precision) for token in tokens}
    assert ("2023-05-12", "day") in rendered
    assert ("May 2023", "month") in rendered
    assert ("12 March 2024", "day") in rendered
    assert all("05/12/2023" not in token.text for token in tokens)


def test_parse_date_value_is_strict() -> None:
    assert parse_date_value("2023-05-12").iso == "2023-05-12"
    assert parse_date_value("2023-05").precision == "month"
    assert parse_date_value("2023").precision == "year"
    assert parse_date_value("2023-02-30") is None
    assert parse_date_value("2023-13") is None
    assert parse_date_value(" 2023-05-12") is None
    assert parse_date_value("12 May 2023") is None


def test_cross_document_duplicate_clusters_find_leaks() -> None:
    payload = json.loads(json.dumps(_event().to_dict()))
    clusters = find_duplicate_clusters({"doc-a": [payload], "doc-b": [payload]})
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.doc_ids == ("doc-a", "doc-b")
    assert cluster.basis == "dedup_key"
    assert len(cluster.members) == 2


def test_cross_document_clusters_do_not_merge_distinct_events() -> None:
    first = json.loads(json.dumps(_event().to_dict()))
    second = json.loads(
        json.dumps(
            _event(
                event_date="2024-03-01",
                product_or_technology="Other device",
                evidence=(
                    schema.EvidenceSpan(
                        quote="The MiniMed 780G is intended for people with diabetes.",
                        field="event_date",
                    ),
                ),
            ).to_dict()
        )
    )
    clusters = find_duplicate_clusters({"doc-a": [first], "doc-b": [second]})
    assert clusters == ()


def test_quote_length_ceiling_is_enforced_by_the_evidence_checker() -> None:
    from experiments.local_llm_event_extraction.validation.evidence import check_quote

    quote = "x" * (schema.MAX_QUOTE_CHARS + 1)
    check = check_quote(quote, document_text=quote)
    assert "EVIDENCE_TOO_LONG" in {issue.code for issue in check.issues}
    assert check.location is not None


def test_synthetic_constructors_accept_plain_data_shapes() -> None:
    roster = EntityRoster.from_synthetic(medtronic=["MEDTRONIC"], stryker="STRYKER")
    assert roster.resolve_alias("Medtronic, Inc.") == "medtronic"
    assert roster.resolve_alias("Stryker") == "stryker"
    assert roster.canonical_ids == ("medtronic", "stryker")

    taxonomy = Taxonomy.from_synthetic(["diabetes_cgm"], ["diabetes"])
    assert taxonomy.is_known_track("diabetes_cgm")
    assert taxonomy.is_known_domain("diabetes")
    assert taxonomy.accepts_technology_domain("diabetes_cgm")


def test_cross_document_clusters_accept_event_objects() -> None:
    event = _event()
    payload = json.loads(json.dumps(event.to_dict()))
    clusters = find_duplicate_clusters({"doc-a": [event], "doc-b": [payload]})
    assert len(clusters) == 1
    assert clusters[0].doc_ids == ("doc-a", "doc-b")


def test_taxonomy_config_picks_up_track_names_from_product_codes(tmp_path) -> None:
    (tmp_path / "tracks_device.json").write_text(
        json.dumps(
            {
                "tracks": [{"id": "known_track", "name_en": "Known", "domain": "domain_a"}],
                "domains": [{"id": "domain_a", "name_en": "Domain A"}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "product_code_tracks.json").write_text(
        json.dumps({"AAA": "known_track", "BBB": "only_in_product_codes"}),
        encoding="utf-8",
    )
    taxonomy = Taxonomy.from_config(tmp_path)
    assert taxonomy.is_known_track("known_track")
    assert taxonomy.is_known_track("only_in_product_codes")
    assert taxonomy.domain_of_track("known_track") == "domain_a"
    assert getattr(taxonomy, "added_track_ids_from_product_codes") == ("only_in_product_codes",)


def test_entity_roster_config_merges_focus_companies_and_device_list(tmp_path) -> None:
    (tmp_path / "universe_v1.json").write_text(
        json.dumps(
            {
                "focus_companies": {
                    "firm_a": {"display_name": "Firm A", "aliases": ["FIRM A", "A CORP"]},
                    "firm_b": {"display_name": "Firm B", "aliases": ["FIRM B"]},
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "companies_device.json").write_text(
        json.dumps(
            {
                "companies": [
                    {"key": "firm_a", "name_en": "Firm A Ltd", "aliases": ["FIRM A LTD"]},
                    {"key": "firm_c", "name_en": "Firm C", "aliases": ["FIRM C"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    roster = EntityRoster.from_config(tmp_path)
    assert set(roster.canonical_ids) == {"firm_a", "firm_b", "firm_c"}
    # Aliases from both files survive the merge for the overlapping canonical id.
    assert "A CORP" in roster.aliases_for("firm_a")
    assert "FIRM A LTD" in roster.aliases_for("firm_a")
    assert roster.resolve_alias("Firm C") == "firm_c"


def test_config_loaders_fail_loudly_when_configuration_is_absent(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        EntityRoster.from_config(tmp_path)
    with pytest.raises(FileNotFoundError):
        Taxonomy.from_config(tmp_path)


# ------------------------------------------------------ real configuration wiring
def test_real_roster_loads_the_five_focus_firms_from_config() -> None:
    roster = EntityRoster.from_config()
    canonical_ids = set(roster.canonical_ids)
    assert {"medtronic", "ge_healthcare", "philips", "draeger", "mindray"} <= canonical_ids
    assert len(roster.canonical_ids) >= 50

    # Aliases come from config/universe_v1.json and config/companies_device.json.
    assert roster.resolve_alias("MEDTRONIC MINIMED") == "medtronic"
    assert roster.resolve_alias("GE MEDICAL SYSTEMS") == "ge_healthcare"
    assert roster.resolve_alias("PHILIPS ULTRASOUND") == "philips"
    assert roster.resolve_alias("DRAEGER") == "draeger"
    assert roster.resolve_alias("MINDRAY") == "mindray"
    assert "COVIDIEN" in roster.aliases_for("medtronic")

    # Deterministic matching: no fuzzy fallback for a misspelling.
    assert roster.resolve_alias("Medtronicc") is None
    assert roster.resolve_alias("a company that does not exist") is None


def test_real_taxonomy_loads_domains_and_tracks_from_config() -> None:
    taxonomy = Taxonomy.from_config()
    assert len(taxonomy.domain_ids) >= 20
    assert len(taxonomy.track_ids) >= 40
    assert taxonomy.is_known_domain("diabetes")
    assert taxonomy.is_known_domain("cardiovascular")
    assert taxonomy.is_known_track("ep_pfa")
    assert taxonomy.accepts_technology_domain("diabetes")
    assert taxonomy.accepts_technology_domain("ep_pfa")
    assert not taxonomy.accepts_technology_domain("quantum_teleportation")
    assert taxonomy.domain_of_track("ep_pfa") == "cardiovascular"


def test_validator_accepts_a_correct_event_using_the_real_config_roster() -> None:
    event = _event(
        company=schema.EntityClaim(
            raw_text="Medtronic",
            canonical_id="medtronic",
            match_basis="roster_alias_in_document",
        ),
        technology_domains=("diabetes",),
    )
    validation = _validate(
        (event,),
        roster=EntityRoster.from_config(),
        taxonomy=Taxonomy.from_config(),
    )
    assert validation.judgements[0].issues == ()
    assert validation.verdict is Verdict.ACCEPTED
