"""Regression tests for the overnight Phase-A defect fixes (schema v2).

Each test names the defect it pins, so a future change that reintroduces the
defect fails here with a reason rather than silently restoring the bug.

A1  closed technology-domain vocabulary rendered into the prompt
A2  locale-declared numeric dates (US/UK) are parsed; undeclared ones are not
A3  the temporal ordering rule is applied per event-date *kind*
A4  same-day different-product events are not duplicates
A4  output stopped at the token budget is `truncated`, not `invalid_json`
A4  the runner can restrict evaluation to a split and audits leakage
A4  the frozen JSON Schema and the Python contract agree on required keys
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from experiments.local_llm_event_extraction.contracts import ValidationConfig
from experiments.local_llm_event_extraction.datasets.splits import assign_grouped_splits
from experiments.local_llm_event_extraction.parsing import parse_response
from experiments.local_llm_event_extraction.prompting import (
    PROMPT_VERSIONS,
    build_prompt,
    prompt_fingerprint,
    render_template_sha256,
)
from experiments.local_llm_event_extraction.schema import (
    EVENT_DATE_KINDS,
    EVENT_JSON_SCHEMA,
    SCHEMA_VERSION,
    SourceDocument,
    event_from_dict,
)
from experiments.local_llm_event_extraction.validation.dedup import dedup_key
from experiments.local_llm_event_extraction.validation.entities import Taxonomy
from experiments.local_llm_event_extraction.validation.timefields import (
    check_event_timestamps,
    dates_in_text,
    parse_date_value,
    resolve_date_locale,
    supporting_tokens,
)

DOCUMENT_TEXT = (
    "Medtronic announced today that it received FDA 510(k) clearance for the "
    "Infinity OCT System. The decision was dated 12/15/2025 and the device is "
    "intended for posterior cervical fixation."
)


def _document(**metadata: str) -> SourceDocument:
    base = {
        "company_hint": "Medtronic [canonical_id: medtronic]",
        "company_canonical_id": "medtronic",
    }
    base.update(metadata)
    return SourceDocument(
        doc_id="doc-test",
        source_type="fda_510k",
        text=DOCUMENT_TEXT,
        title="510(k) clearance",
        published_at="2025-12-20",
        metadata=base,
    )


def _event(**overrides):
    payload = {
        "client_ref": None,
        "status": "extracted",
        "abstain_reason": None,
        "company": {
            "raw_text": "Medtronic",
            "canonical_id": "medtronic",
            "match_basis": "roster_alias_verbatim",
        },
        "event_category": "regulatory_clearance",
        "technology_domains": [],
        "product_or_technology": "Infinity OCT System",
        "event_date": "2025-12-15",
        "event_date_kind": "decision",
        "published_at": None,
        "first_seen_at": None,
        "timestamp_quality": {
            "event_date": "exact_day",
            "published_at": "absent",
            "first_seen_at": "absent",
        },
        "evidence": [
            {
                "quote": "The decision was dated 12/15/2025",
                "field": "event_date",
            }
        ],
        "rationale": None,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------- A1: vocabulary
def test_v2_prompt_renders_the_closed_domain_vocabulary() -> None:
    taxonomy = Taxonomy.from_config()
    prompt = build_prompt(
        _document(),
        technology_domains=taxonomy.domain_ids,
        domain_track_map={track.track_id: track.domain for track in taxonomy.tracks},
    )
    assert prompt.prompt_version == "extract-v2"
    for domain in taxonomy.domain_ids:
        assert f"  - {domain}" in prompt.system, domain
    # The defect: v1 never mentioned a single declared domain.
    v1 = build_prompt(_document(), prompt_version="extract-v1")
    assert "cardiovascular" not in v1.system


def test_prompt_hash_separates_wording_from_version() -> None:
    taxonomy = Taxonomy.from_config()
    with_vocab = render_template_sha256(
        domains=taxonomy.domain_ids,
        domain_track_map={track.track_id: track.domain for track in taxonomy.tracks},
    )
    without_vocab = render_template_sha256()
    v1 = render_template_sha256(prompt_version="extract-v1")
    assert len({with_vocab, without_vocab, v1}) == 3
    assert set(PROMPT_VERSIONS) == {"extract-v1", "extract-v2"}
    assert prompt_fingerprint()["prompt_version"] == "extract-v2"


def test_empty_vocabulary_is_declared_as_unavailable_not_silently_omitted() -> None:
    prompt = build_prompt(_document())
    assert "technology-domain vocabulary is unavailable" in prompt.system


# --------------------------------------------------------------- A2: date locale
def test_numeric_dates_are_not_guessed_without_a_declared_locale() -> None:
    assert [token.date.iso for token in dates_in_text(DOCUMENT_TEXT)] == ["2025"]
    assert resolve_date_locale(_document()) is None


def test_us_locale_parses_month_first_numeric_dates() -> None:
    document = _document(date_locale="us")
    assert resolve_date_locale(document) == "us"
    tokens = dates_in_text(DOCUMENT_TEXT, "us")
    day_tokens = [token for token in tokens if token.precision == "day"]
    assert [token.date.iso for token in day_tokens] == ["2025-12-15"]
    assert parse_date_value("2025-12-15") is not None
    claimed = parse_date_value("2025-12-15")
    assert supporting_tokens(claimed, [DOCUMENT_TEXT], "us")
    assert not supporting_tokens(claimed, [DOCUMENT_TEXT], None)


def test_uk_locale_parses_day_first_numeric_dates() -> None:
    text = "Clearance was granted on 15/12/2025."
    uk = [token for token in dates_in_text(text, "uk") if token.precision == "day"]
    assert [token.date.iso for token in uk] == ["2025-12-15"]
    # Under the US reading 15/12/2025 is not a calendar date (month 15), so no
    # day-precision token may be produced -- guessing must never happen.
    us = [token for token in dates_in_text(text, "us") if token.precision == "day"]
    assert us == []


def test_unknown_locale_is_an_error_not_a_silent_fallback() -> None:
    with pytest.raises(ValueError):
        resolve_date_locale(_document(date_locale="mars"))


def test_locale_declaration_makes_the_date_check_pass_where_v1_failed() -> None:
    """The Phase 2 `DATE_NOT_IN_EVIDENCE` failure on numeric US dates."""
    config = ValidationConfig()
    document = _document(date_locale="us")
    issues = check_event_timestamps(_event(), document=document, config=config, as_of=None)
    assert [issue.code for issue in issues] == []

    undeclared = _document()
    issues = check_event_timestamps(_event(), document=undeclared, config=config, as_of=None)
    assert "DATE_NOT_IN_EVIDENCE" in {issue.code for issue in issues}


# ------------------------------------------------------ A3: event-date semantics
def test_planned_trial_start_after_publication_is_not_a_violation() -> None:
    document = _document(published_at="2025-01-10")
    event = _event(
        event_date="2027-06-30",
        event_date_kind="trial_start_planned",
        timestamp_quality={
            "event_date": "exact_day",
            "published_at": "absent",
            "first_seen_at": "absent",
        },
        evidence=[{"quote": "estimated start date 2027-06-30", "field": "event_date"}],
    )
    document = SourceDocument(
        doc_id="trial",
        source_type="clinical_trial_record",
        text="Trial record. Estimated start date 2027-06-30.",
        published_at="2025-01-10",
        metadata={"date_locale": "iso"},
    )
    issues = check_event_timestamps(event, document=document, config=ValidationConfig(), as_of=None)
    assert "DATE_ORDER_VIOLATION" not in {issue.code for issue in issues}


def test_unspecified_kind_keeps_the_strict_ordering_rule() -> None:
    """Omitting the kind must never buy an exemption."""
    document = SourceDocument(
        doc_id="trial",
        source_type="clinical_trial_record",
        text="Trial record. Estimated start date 2027-06-30.",
        published_at="2025-01-10",
        metadata={"date_locale": "iso"},
    )
    event = _event(
        event_date="2027-06-30",
        event_date_kind="unspecified",
        evidence=[{"quote": "Estimated start date 2027-06-30", "field": "event_date"}],
    )
    issues = check_event_timestamps(event, document=document, config=ValidationConfig(), as_of=None)
    assert "DATE_ORDER_VIOLATION" in {issue.code for issue in issues}


def test_event_date_kind_is_a_closed_vocabulary_in_both_representations() -> None:
    assert "decision" in EVENT_DATE_KINDS
    assert event_from_dict(_event()).event_date_kind == "decision"
    # absent -> unspecified, and an unknown kind is a contract error
    payload = _event()
    payload.pop("event_date_kind")
    assert event_from_dict(payload).event_date_kind == "unspecified"
    from experiments.local_llm_event_extraction.schema import ContractError

    with pytest.raises(ContractError):
        event_from_dict(_event(event_date_kind="sometime"))
    assert EVENT_JSON_SCHEMA["properties"]["event_date_kind"]["enum"] == list(EVENT_DATE_KINDS)


# ------------------------------------------------------------- A4: dedup product
def test_same_day_different_products_are_not_duplicates() -> None:
    first = _event(product_or_technology="Infinity OCT System")
    second = _event(product_or_technology="Hugo RAS System")
    assert dedup_key(first) != dedup_key(second)
    assert dedup_key(first) == dedup_key(_event(product_or_technology="infinity oct system"))


# ------------------------------------------------------------ A4: truncation
def test_truncated_output_is_still_invalid_json() -> None:
    result = parse_response(
        '{"events": [{"status": "extracted", "company":',
        doc_id="doc",
        extractor={"system": "test", "adapter_id": "test"},
        finish_reason="truncated",
    )
    assert result.parse_status == "invalid_json"


def test_length_limited_output_is_reported_as_truncated() -> None:
    result = parse_response(
        '{"events": [{"status": "extracted", "company":',
        doc_id="doc",
        extractor={"system": "test", "adapter_id": "test"},
        finish_reason="length",
    )
    assert result.parse_status == "truncated"
    assert result.events == ()


# ------------------------------------------------- A4: split filter + leakage audit
def _dataset_cases():
    from experiments.local_llm_event_extraction.contracts import DatasetCase, DatasetManifest, GoldEvent

    cases = []
    for index, (group, split) in enumerate(
        [("a", "train"), ("b", "train"), ("c", "validation"), ("d", "test")]
    ):
        document = SourceDocument(
            doc_id=f"doc-{index}", source_type="fda_510k", text=f"document {index} " * 40
        )
        cases.append(
            DatasetCase(
                case_id=f"case-{index}",
                document=document,
                gold_events=(
                    GoldEvent(
                        event_id=f"g-{index}",
                        company_canonical_id="medtronic",
                        event_category="regulatory_clearance",
                        event_date="2025-01-02",
                        label_tier="source_record_derived",
                    ),
                ),
                label_tier="source_record_derived",
                group=group,
                split=split,
            )
        )
    return DatasetManifest(name="x", version="v", cases=tuple(cases))


def test_runner_split_filter_selects_only_the_named_split(tmp_path) -> None:
    from experiments.local_llm_event_extraction.adapters.mock import RefusingAdapter
    from experiments.local_llm_event_extraction.benchmark.runner import run_benchmark

    dataset = _dataset_cases()
    run = run_benchmark(
        dataset,
        [RefusingAdapter()],
        output_dir=tmp_path,
        splits=["test"],
        validator=None,
        config={"run_status": "REAL_DOCUMENT_UNLABELLED"},
    )
    assert run.manifest.dataset["splits"] == {"test": 1}
    observed = {record["split"] for record in run.predictions["refusing-stub"]}
    assert observed == {"test"}


def test_runner_refuses_an_unknown_split(tmp_path) -> None:
    from experiments.local_llm_event_extraction.adapters.mock import RefusingAdapter
    from experiments.local_llm_event_extraction.benchmark.runner import run_benchmark

    with pytest.raises(ValueError, match="do not occur in this dataset"):
        run_benchmark(
            _dataset_cases(),
            [RefusingAdapter()],
            output_dir=tmp_path,
            splits=["nope"],
            validator=None,
            config={"run_status": "REAL_DOCUMENT_UNLABELLED"},
        )


def test_leakage_audit_is_called_by_the_runner(tmp_path) -> None:
    from dataclasses import replace

    from experiments.local_llm_event_extraction.adapters.mock import RefusingAdapter
    from experiments.local_llm_event_extraction.benchmark.runner import run_benchmark

    dataset = _dataset_cases()
    leaky_cases = tuple(
        replace(case, group="a") if case.case_id == "case-3" else case for case in dataset.cases
    )
    leaked = type(dataset)(
        name="leaky",
        version="v",
        cases=leaky_cases,
        source_sha256=dataset.source_sha256,
    )
    with pytest.raises(ValueError, match="leakage audit"):
        run_benchmark(
            leaked,
            [RefusingAdapter()],
            output_dir=tmp_path,
            validator=None,
            config={"run_status": "REAL_DOCUMENT_UNLABELLED"},
        )


def test_grouped_split_assignment_never_leaks_a_group() -> None:
    dataset = _dataset_cases()
    manifest = assign_grouped_splits(list(dataset.cases))
    seen: dict[str, set[str]] = {}
    for case in manifest.cases:
        seen.setdefault(case.group, set()).add(case.split)
    assert all(len(splits) == 1 for splits in seen.values())


# -------------------------------------------------- A4: schema/contract parity
def test_json_schema_and_python_contract_agree_on_the_event_keys() -> None:
    event = event_from_dict(_event())
    payload = event.to_dict()
    schema_keys = set(EVENT_JSON_SCHEMA["properties"])
    assert set(payload) == schema_keys
    for required in EVENT_JSON_SCHEMA["required"]:
        assert required in payload, required
    assert EVENT_JSON_SCHEMA["additionalProperties"] is False
    assert SCHEMA_VERSION.endswith(".v2")
    # The committed schema document must not drift from the generator.
    from pathlib import Path

    from experiments.local_llm_event_extraction.schema import schema_document

    path = (
        Path(__file__).resolve().parents[1]
        / "experiments/local_llm_event_extraction/schema/event.schema.json"
    )
    committed = json.loads(path.read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(schema_document()))
