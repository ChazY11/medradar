"""Offline contract tests for the frozen extraction schema (``schema.py``).

Nothing here needs a model, a network connection or a database.  The tests pin
three things that later work depends on:

1. the strict decoder rejects anything the contract does not allow (unknown
   keys, bad enum members, missing required fields) -- it never "fills in" a
   default that a model failed to produce;
2. ``schema/event.schema.json`` is byte-identical to the generator, so the
   committed artefact cannot drift away from the code that defines the contract;
3. the validator's dependency-free JSON-Schema subset engine agrees with the real
   ``jsonschema`` package on a matrix of deliberately broken fixtures (the
   reference check is skipped only when ``jsonschema`` is not installed).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from experiments.local_llm_event_extraction import schema
from experiments.local_llm_event_extraction.validation.schema_validator import (
    SchemaEngineError,
    SchemaValidator,
    index_schemas,
    validate_event_payload,
    validate_result_payload,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMITTED_SCHEMA_PATH = (
    REPO_ROOT / "experiments" / "local_llm_event_extraction" / "schema" / "event.schema.json"
)


# ------------------------------------------------------------------- fixtures
def _base_event(**overrides: object) -> schema.EventExtraction:
    values: dict[str, object] = {
        "status": "extracted",
        "company": schema.EntityClaim(
            raw_text="Medtronic",
            canonical_id="medtronic",
            match_basis="roster_alias_in_document",
        ),
        "event_category": "regulatory_clearance",
        "technology_domains": ("cardiology",),
        "product_or_technology": "MiniMed 780G",
        "event_date": "2023-05-12",
        "published_at": "2023-05-13",
        "first_seen_at": "2023-05-16",
        "timestamp_quality": schema.TimestampQuality("exact_day", "exact_day", "exact_day"),
        "evidence": (
            schema.EvidenceSpan(
                quote="Medtronic said on 2023-05-12 that it received FDA clearance",
                field="event_date",
            ),
        ),
        "rationale": "The clearance is stated explicitly in the sentence.",
    }
    values.update(overrides)
    return schema.EventExtraction(**values)  # type: ignore[arg-type]


def _base_result(**overrides: object) -> schema.ExtractionResult:
    values: dict[str, object] = {
        "doc_id": "doc-1",
        "parse_status": "ok",
        "extractor": schema.ExtractorProvenance(system="scripted", adapter_id="fixture"),
        "events": (_base_event(),),
    }
    values.update(overrides)
    return schema.ExtractionResult(**values)  # type: ignore[arg-type]


def _base_event_payload() -> dict[str, object]:
    return json.loads(json.dumps(_base_event().to_dict()))


def _base_result_payload() -> dict[str, object]:
    return json.loads(json.dumps(_base_result().to_dict()))


def _at(payload: object, path: tuple[object, ...]) -> object:
    target: object = payload
    for key in path:
        if isinstance(key, int):
            assert isinstance(target, list)
            target = target[key]
        else:
            assert isinstance(target, dict)
            target = target[key]
    return target


def _set(payload: dict[str, object], path: tuple[object, ...], value: object) -> dict[str, object]:
    target = _at(payload, path[:-1]) if len(path) > 1 else payload
    key = path[-1]
    if isinstance(key, int):
        assert isinstance(target, list)
        target[key] = value
    else:
        assert isinstance(target, dict)
        target[key] = value
    return payload


def _remove(payload: dict[str, object], path: tuple[object, ...]) -> dict[str, object]:
    target = _at(payload, path[:-1]) if len(path) > 1 else payload
    key = path[-1]
    if isinstance(key, int):
        assert isinstance(target, list)
        del target[key]
    else:
        assert isinstance(target, dict)
        del target[key]
    return payload


# ------------------------------------------------------------------- drift test
def test_committed_schema_file_matches_generator_exactly() -> None:
    committed = COMMITTED_SCHEMA_PATH.read_text(encoding="utf-8")
    generated = schema.dumps_schema_document()
    assert committed == generated, (
        "schema/event.schema.json has drifted from schema.py; regenerate it with "
        "dumps_schema_document() instead of editing it"
    )


def test_schema_document_is_json_serialisable_and_round_trips() -> None:
    document = schema.schema_document()
    assert json.loads(json.dumps(document)) == document
    assert json.loads(schema.dumps_schema_document()) == document
    assert set(document) == {"$comment", "schema_version", "event", "result"}
    assert document["schema_version"] == schema.SCHEMA_VERSION


def test_index_schemas_finds_both_ids() -> None:
    indexed = index_schemas(schema.schema_document())
    assert set(indexed) == {schema.EVENT_JSON_SCHEMA["$id"], schema.EXTRACTION_JSON_SCHEMA["$id"]}


# ------------------------------------------------------------- strict decoding
def test_event_from_dict_rejects_unknown_keys() -> None:
    payload = _base_event_payload()
    payload["surprise"] = 1
    with pytest.raises(schema.ContractError, match="unknown key"):
        schema.event_from_dict(payload)

    payload = _base_event_payload()
    _set(payload, ("company", "ticker"), "MDT")
    with pytest.raises(schema.ContractError, match="unknown key"):
        schema.event_from_dict(payload)

    payload = _base_event_payload()
    _set(payload, ("evidence", 0), {"quote": "Medtronic", "field": "company", "confidence": 0.9})
    with pytest.raises(schema.ContractError, match="unknown key"):
        schema.event_from_dict(payload)

    payload = _base_event_payload()
    _set(payload, ("timestamp_quality", "retrieved_at"), "exact_day")
    with pytest.raises(schema.ContractError, match="unknown key"):
        schema.event_from_dict(payload)


def test_result_from_dict_rejects_unknown_keys() -> None:
    payload = _base_result_payload()
    payload["surprise"] = 1
    with pytest.raises(schema.ContractError, match="unknown key"):
        schema.result_from_dict(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("status",), "maybe"),
        (("event_category",), "miracle_breakthrough"),
        (("abstain_reason",), "because_i_said_so"),
        (("company", "match_basis"), "vibes"),
        (("timestamp_quality", "event_date"), "sometime"),
    ],
)
def test_event_from_dict_rejects_bad_enum_members(path: tuple[str, ...], value: object) -> None:
    payload = _base_event_payload()
    _set(payload, path, value)
    with pytest.raises(schema.ContractError):
        schema.event_from_dict(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: _set(payload, ("evidence", 0), {"field": "event_date"}),
        lambda payload: _set(payload, ("evidence", 0), {"quote": "Medtronic", "field": ""}),
        lambda payload: _set(payload, ("evidence", 0, "quote"), ""),
        lambda payload: _set(payload, ("evidence", 0, "quote"), "x" * (schema.MAX_QUOTE_CHARS + 1)),
        lambda payload: _set(payload, ("rationale",), "x" * (schema.MAX_RATIONALE_CHARS + 1)),
        lambda payload: _set(payload, ("evidence",), []),
        lambda payload: (
            _set(payload, ("status",), "abstained"),
            _set(payload, ("abstain_reason",), None),
            _set(payload, ("evidence",), []),
        ),
    ],
    ids=[
        "evidence-missing-quote",
        "evidence-missing-field",
        "empty-quote",
        "quote-too-long",
        "rationale-too-long",
        "extracted-without-evidence",
        "abstained-without-reason",
    ],
)
def test_event_from_dict_requires_the_contracted_fields(mutate) -> None:
    payload = _base_event_payload()
    mutate(payload)
    with pytest.raises(schema.ContractError):
        schema.event_from_dict(payload)


def test_event_from_dict_frozen_defaults_are_documented() -> None:
    """``event_from_dict`` defaults ``status``/``company.match_basis``.

    This is a property of the frozen module (its JSON Schema marks both as
    *required*, but the decoder fills a default).  The test records the behaviour
    so a future contract change is noticed, and so the validator's schema check
    -- which runs on the decoded ``to_dict()`` -- is understood to see the
    defaulted values, not the original omissions.
    """
    payload = _base_event_payload()
    _remove(payload, ("status",))
    _remove(payload, ("company", "match_basis"))
    decoded = schema.event_from_dict(payload)
    assert decoded.status == "extracted"
    assert decoded.company.match_basis == "none"


def test_event_round_trips_through_to_dict() -> None:
    for event in (
        _base_event(),
        _base_event(status="abstained", abstain_reason="no_event", evidence=()),
        schema.EventExtraction(status="abstained", abstain_reason="ambiguous_date"),
    ):
        payload = event.to_dict()
        assert json.loads(json.dumps(payload)) == payload
        assert schema.event_from_dict(payload) == event


def test_result_round_trips_through_to_dict() -> None:
    result = _base_result()
    payload = result.to_dict()
    assert json.loads(json.dumps(payload)) == payload
    assert schema.result_from_dict(payload) == result


def test_raw_output_is_only_serialised_on_request() -> None:
    result = _base_result(raw_output='{"broken": true}')
    assert "raw_output" not in result.to_dict()
    assert result.to_dict(include_raw=True)["raw_output"] == '{"broken": true}'


# ------------------------------------------- reference jsonschema agreement test
def _reference_validators():
    jsonschema = pytest.importorskip("jsonschema")
    referencing = pytest.importorskip("referencing")
    document = schema.schema_document()
    event_schema = document["event"]
    result_schema = document["result"]
    jsonschema.Draft202012Validator.check_schema(event_schema)
    jsonschema.Draft202012Validator.check_schema(result_schema)
    registry = referencing.Registry().with_resources(
        [
            (event_schema["$id"], referencing.Resource.from_contents(event_schema)),
            (result_schema["$id"], referencing.Resource.from_contents(result_schema)),
        ]
    )
    return (
        jsonschema,
        jsonschema.Draft202012Validator(event_schema),
        jsonschema.Draft202012Validator(result_schema, registry=registry),
    )


def test_frozen_schemas_are_valid_jsonschema_documents() -> None:
    jsonschema, event_validator, result_validator = _reference_validators()
    # ``check_schema`` ran inside the helper; a valid instance must also pass.
    assert event_validator.is_valid(_base_event_payload())
    assert result_validator.is_valid(_base_result_payload())


def _event_fixture_cases() -> list[tuple[str, object, bool]]:
    """(name, payload, expected_valid) for the event schema."""
    cases: list[tuple[str, object, bool]] = [
        ("valid", _base_event_payload(), True),
    ]

    payload = _base_event_payload()
    cases.append(("missing_status", _remove(payload, ("status",)), False))

    payload = _base_event_payload()
    cases.append(("unknown_status", _set(payload, ("status",), "maybe"), False))

    payload = _base_event_payload()
    payload["extra"] = 1
    cases.append(("extra_root_property", payload, False))

    payload = _base_event_payload()
    cases.append(
        ("company_missing_match_basis", _remove(payload, ("company", "match_basis")), False)
    )

    payload = _base_event_payload()
    cases.append(
        ("evidence_empty_quote", _set(payload, ("evidence", 0, "quote"), ""), False)
    )

    payload = _base_event_payload()
    cases.append(
        (
            "evidence_quote_too_long",
            _set(payload, ("evidence", 0, "quote"), "x" * (schema.MAX_QUOTE_CHARS + 1)),
            False,
        )
    )

    payload = _base_event_payload()
    cases.append(
        ("too_many_domains", _set(payload, ("technology_domains",), ["a"] * 7), False)
    )

    payload = _base_event_payload()
    cases.append(("bool_is_not_an_integer", _set(payload, ("evidence", 0, "char_start"), True), False))

    payload = _base_event_payload()
    cases.append(
        ("integral_float_is_an_integer", _set(payload, ("evidence", 0, "char_start"), 1.0), True)
    )

    payload = _base_event_payload()
    cases.append(
        ("fractional_float_is_not_an_integer", _set(payload, ("evidence", 0, "char_start"), 1.5), False)
    )

    payload = _base_event_payload()
    cases.append(("negative_char_start", _set(payload, ("evidence", 0, "char_start"), -1), False))

    payload = _base_event_payload()
    cases.append(
        ("bad_date_pattern", _set(payload, ("event_date",), "2023-5-1"), False)
    )

    payload = _base_event_payload()
    cases.append(
        (
            "rationale_too_long",
            _set(payload, ("rationale",), "x" * (schema.MAX_RATIONALE_CHARS + 1)),
            False,
        )
    )

    payload = _base_event_payload()
    cases.append(("extracted_without_evidence", _set(payload, ("evidence",), []), False))

    payload = _base_event_payload()
    _set(payload, ("status",), "abstained")
    _set(payload, ("abstain_reason",), None)
    _set(payload, ("evidence",), [])
    cases.append(("abstained_without_reason", payload, False))

    payload = _base_event_payload()
    _set(payload, ("status",), "abstained")
    _set(payload, ("abstain_reason",), "no_event")
    _set(payload, ("evidence",), [])
    cases.append(("abstained_with_reason", payload, True))

    payload = _base_event_payload()
    cases.append(
        ("missing_quality_field", _remove(payload, ("timestamp_quality", "event_date")), False)
    )

    payload = _base_event_payload()
    cases.append(
        (
            "unknown_quality_member",
            _set(payload, ("timestamp_quality", "event_date"), "sometimes"),
            False,
        )
    )

    cases.append(("wrong_root_type", [], False))
    cases.append(("null_payload", None, False))
    return cases


def _result_fixture_cases() -> list[tuple[str, object, bool]]:
    """(name, payload, expected_valid) for the result schema."""
    cases: list[tuple[str, object, bool]] = [
        ("valid", _base_result_payload(), True),
    ]

    payload = _base_result_payload()
    cases.append(("missing_schema_version", _remove(payload, ("schema_version",)), False))

    payload = _base_result_payload()
    cases.append(("unknown_parse_status", _set(payload, ("parse_status",), "maybe"), False))

    payload = _base_result_payload()
    cases.append(
        ("extractor_missing_adapter_id", _remove(payload, ("extractor", "adapter_id")), False)
    )

    payload = _base_result_payload()
    _remove(payload, ("events", 0, "status"))
    cases.append(("nested_event_missing_status", payload, False))

    payload = _base_result_payload()
    cases.append(("events_not_array", _set(payload, ("events",), "nope"), False))

    payload = _base_result_payload()
    payload["extra"] = 1
    cases.append(("extra_root_property", payload, False))

    payload = _base_result_payload()
    cases.append(("missing_doc_id", _remove(payload, ("doc_id",)), False))
    return cases


@pytest.mark.parametrize(
    ("name", "payload", "expected_valid"),
    _event_fixture_cases(),
    ids=[case[0] for case in _event_fixture_cases()],
)
def test_schema_engine_agrees_with_jsonschema_for_events(
    name: str, payload: object, expected_valid: bool
) -> None:
    _jsonschema, reference_event_validator, _reference_result_validator = _reference_validators()
    ours = validate_event_payload(payload)
    reference_valid = reference_event_validator.is_valid(payload)
    assert ours.valid == reference_valid, (
        f"engine disagreement on {name!r}: engine={ours.valid} jsonschema={reference_valid} "
        f"findings={[finding.to_dict() for finding in ours.findings]}"
    )
    assert ours.valid == expected_valid, f"fixture {name!r} expectation is wrong"


@pytest.mark.parametrize(
    ("name", "payload", "expected_valid"),
    _result_fixture_cases(),
    ids=[case[0] for case in _result_fixture_cases()],
)
def test_schema_engine_agrees_with_jsonschema_for_results(
    name: str, payload: object, expected_valid: bool
) -> None:
    _jsonschema, _reference_event_validator, reference_result_validator = _reference_validators()
    ours = validate_result_payload(payload)
    reference_valid = reference_result_validator.is_valid(payload)
    assert ours.valid == reference_valid, (
        f"engine disagreement on {name!r}: engine={ours.valid} jsonschema={reference_valid} "
        f"findings={[finding.to_dict() for finding in ours.findings]}"
    )
    assert ours.valid == expected_valid, f"fixture {name!r} expectation is wrong"


# --------------------------------------------------- engine behaviour specifics
def test_engine_reports_json_pointer_paths() -> None:
    payload = _base_event_payload()
    _remove(payload, ("status",))
    _set(payload, ("evidence", 0, "quote"), "")
    payload["extra"] = 1
    findings = validate_event_payload(payload).findings
    located = {(finding.path, finding.keyword) for finding in findings}
    assert ("/status", "required") in located
    assert ("/evidence/0/quote", "minLength") in located
    assert ("/extra", "additionalProperties") in located


def test_engine_composes_pointer_paths_through_ref() -> None:
    payload = _base_result_payload()
    _remove(payload, ("events", 0, "status"))
    findings = validate_result_payload(payload).findings
    located = {(finding.path, finding.keyword) for finding in findings}
    assert ("/events/0/status", "required") in located


def test_engine_reports_structural_findings_without_mutating_input() -> None:
    payload = _base_event_payload()
    _set(payload, ("event_category",), "not_a_category")
    snapshot = copy.deepcopy(payload)
    validation = validate_event_payload(payload)
    assert not validation.valid
    assert payload == snapshot, "the schema engine must never mutate the instance"


def test_engine_raises_for_unresolvable_ref() -> None:
    validator = SchemaValidator({"$ref": "does/not/exist"})
    with pytest.raises(SchemaEngineError, match="unresolvable"):
        validator.validate({})


def test_engine_rejects_unsupported_schema_type_keyword() -> None:
    validator = SchemaValidator({"type": "banana"})
    with pytest.raises(SchemaEngineError, match="unsupported schema type"):
        validator.validate("nope")


def test_engine_from_document_rejects_unknown_kind() -> None:
    with pytest.raises(SchemaEngineError):
        SchemaValidator.from_document(schema.schema_document(), kind="benchmark")
