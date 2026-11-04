"""Contract-level tests: safety gates, derived availability, inert imports, schema drift.

These are the invariants the rest of the experiment depends on and that no single
work package owns.  They are cheap and they are the ones that would hurt most if
they silently broke:

* the four run gates are closed by default, and a typo fails *closed*;
* ``available_at`` is derived from a declared lag and never invented;
* importing every module of the package imports no model library;
* the committed JSON Schema is still exactly what the generator produces.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from experiments.local_llm_event_extraction import schema, safety
from experiments.local_llm_event_extraction.schema import (
    ContractError,
    EntityClaim,
    EventExtraction,
    EvidenceSpan,
    ExtractionResult,
    ExtractorProvenance,
    SourceDocument,
    TimestampQuality,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "experiments" / "local_llm_event_extraction"
SCHEMA_PATH = PACKAGE_ROOT / "schema" / "event.schema.json"


# ------------------------------------------------------------------ safety gates
def test_all_gates_are_closed_by_default() -> None:
    assert safety.all_gates_closed({}) is True
    report = safety.gate_report({})
    assert set(report) == {"model_load", "training", "network", "remote_api"}
    assert all(item["open"] is False for item in report.values())


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " tRuE "])
def test_truthy_values_open_a_gate(value: str) -> None:
    assert safety.gate_open("training", {"MEDRADAR_LOCAL_LLM_ALLOW_TRAINING": value}) is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "disabled", "y", "enable"])
def test_typos_and_negations_fail_closed(value: str) -> None:
    assert safety.gate_open("training", {"MEDRADAR_LOCAL_LLM_ALLOW_TRAINING": value}) is False


def test_require_gate_raises_with_the_variable_name() -> None:
    with pytest.raises(safety.GateClosed) as excinfo:
        safety.require_gate("model_load", environ={})
    assert "MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD" in str(excinfo.value)
    assert excinfo.value.gate == "model_load"
    # Opening it explicitly must make the call a no-op.
    safety.require_gate("model_load", environ={"MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD": "1"})


def test_unknown_gate_is_rejected() -> None:
    with pytest.raises(KeyError):
        safety.gate_open("does_not_exist", {})


# --------------------------------------------------------- derived availability
def _document(**overrides: object) -> SourceDocument:
    payload: dict[str, object] = {
        "doc_id": "doc-1",
        "source_type": "fda_510k",
        "text": "A text body.",
        "published_at": "2024-03-05",
        "metadata": {"availability_lag_days": "30"},
    }
    payload.update(overrides)
    return SourceDocument(**payload)  # type: ignore[arg-type]


def test_available_at_is_published_plus_declared_lag() -> None:
    document = _document()
    assert document.availability_lag_days == 30
    assert document.available_at == "2024-04-04"
    assert document.fetched_at is None


def test_available_at_is_none_without_a_declared_lag() -> None:
    document = _document(metadata={})
    assert document.availability_lag_days is None
    assert document.available_at is None, "an undeclared lag is unknown, not zero"


def test_available_at_is_none_for_month_precision_publication() -> None:
    document = _document(published_at="2024-03")
    # Adding 30 days to "2024-03" would fabricate day precision.
    assert document.available_at is None


def test_available_at_is_none_for_bad_input_and_negative_lag() -> None:
    assert _document(published_at="not-a-date").available_at is None
    assert _document(metadata={"availability_lag_days": "-5"}).availability_lag_days is None
    assert _document(metadata={"availability_lag_days": "thirty"}).available_at is None


def test_fetched_at_alias() -> None:
    document = _document(retrieved_at="2026-11-04T01:02:03Z")
    assert document.fetched_at == "2026-11-04T01:02:03Z"


# ------------------------------------------------------------ structural contract
def test_extracted_event_requires_evidence() -> None:
    with pytest.raises(ContractError, match="at least one EvidenceSpan"):
        EventExtraction(status="extracted", event_category="regulatory_clearance")


def test_abstained_event_requires_a_reason() -> None:
    with pytest.raises(ContractError, match="abstain_reason"):
        EventExtraction(status="abstained")


def test_unknown_category_is_rejected_structurally() -> None:
    with pytest.raises(ContractError, match="unknown event_category"):
        EventExtraction(
            status="abstained",
            abstain_reason="no_event",
            event_category="made_up_category",
        )


def test_strict_decode_rejects_unknown_keys() -> None:
    payload = {
        "status": "abstained",
        "abstain_reason": "no_event",
        "company": {"raw_text": None, "canonical_id": None, "match_basis": "none"},
        "event_category": None,
        "technology_domains": [],
        "product_or_technology": None,
        "event_date": None,
        "published_at": None,
        "first_seen_at": None,
        "timestamp_quality": {
            "event_date": "absent",
            "published_at": "absent",
            "first_seen_at": "absent",
        },
        "evidence": [],
        "invented_field": 1,
    }
    with pytest.raises(ContractError, match="unknown key"):
        schema.event_from_dict(payload)


def test_round_trip_is_lossless_for_a_complete_event() -> None:
    event = EventExtraction(
        status="extracted",
        client_ref="e1",
        company=EntityClaim(raw_text="Medtronic", canonical_id="medtronic-4bdceace",
                            match_basis="roster_alias_verbatim"),
        event_category="regulatory_clearance",
        technology_domains=("patient_monitoring",),
        product_or_technology="Monitor X",
        event_date="2024-03-05",
        published_at="2024-03-06",
        first_seen_at=None,
        timestamp_quality=TimestampQuality(event_date="exact_day", published_at="exact_day"),
        evidence=(EvidenceSpan(quote="cleared Monitor X on March 5, 2024", field="event_date"),),
        rationale="one clearance",
    )
    assert schema.event_from_dict(event.to_dict()) == event


def test_extraction_result_round_trip() -> None:
    result = ExtractionResult(
        doc_id="doc-1",
        parse_status="empty",
        extractor=ExtractorProvenance(system="rule_based", adapter_id="rules-baseline"),
    )
    assert schema.result_from_dict(result.to_dict()) == result


# ------------------------------------------------------------- inert import proof
def test_importing_the_package_does_not_import_a_model_library() -> None:
    code = (
        "import sys;"
        "import experiments.local_llm_event_extraction;"
        "import experiments.local_llm_event_extraction.safety;"
        "import experiments.local_llm_event_extraction.contracts;"
        "import experiments.local_llm_event_extraction.adapters.base;"
        "heavy=[m for m in ('torch','transformers','peft','accelerate','bitsandbytes','datasets')"
        " if m in sys.modules];"
        "print(','.join(heavy))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PACKAGE_ROOT.parents[1]),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "", f"heavy imports leaked: {completed.stdout!r}"


# ------------------------------------------------------------------ schema drift
@pytest.mark.skipif(not SCHEMA_PATH.is_file(), reason="committed schema file is absent")
def test_committed_json_schema_matches_the_generator() -> None:
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    generated = json.loads(schema.dumps_schema_document())
    assert committed == generated, (
        "schema/event.schema.json is stale; regenerate it from schema.dumps_schema_document()"
    )


def test_schema_document_is_json_serialisable() -> None:
    payload = schema.schema_document()
    assert payload["schema_version"] == schema.SCHEMA_VERSION
    json.dumps(payload)


# ----------------------------------------------------- dataset manifest identity
def test_dataset_manifest_serialises_and_carries_its_cases() -> None:
    """The benchmark hashes ``DatasetManifest.to_dict()`` to identify a dataset.

    Regression guard: the harness called this method for its dataset id and the
    contract did not implement it, so every run failed at manifest construction.
    """
    from experiments.local_llm_event_extraction.contracts import (
        DatasetCase,
        DatasetManifest,
        GoldEvent,
    )

    document = SourceDocument(doc_id="d1", source_type="press_release", text="A body.")
    case = DatasetCase(
        case_id="c1",
        document=document,
        gold_events=(
            GoldEvent(
                event_id="g1",
                company_canonical_id="medtronic-4bdceace",
                event_category="regulatory_clearance",
                label_tier="synthetic_fixture",
            ),
        ),
        label_tier="synthetic_fixture",
        group="group-a",
        split="train",
    )
    manifest = DatasetManifest(name="unit", version="v0", cases=(case,))
    payload = manifest.to_dict()
    assert payload["case_count"] == 1
    assert payload["label_tiers"] == ["synthetic_fixture"]
    assert payload["cases"][0]["case_id"] == "c1"
    assert payload["cases"][0]["gold_events"][0]["event_id"] == "g1"
    json.dumps(payload)
