"""Offline tests for the benchmark harness: scoring, runner, resume and report.

The end-to-end run uses the scripted test double and the rules baseline only.  No
model is loaded, no socket is opened, and every artifact lives in ``tmp_path``.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from experiments.local_llm_event_extraction.adapters import build_registry
from experiments.local_llm_event_extraction.benchmark import (
    SYNTHETIC_BANNER,
    run_benchmark,
    score_predictions,
    write_report,
)
from experiments.local_llm_event_extraction.contracts import (
    DatasetCase,
    DatasetManifest,
    EventJudgement,
    GoldEvent,
    ValidationResult,
    Verdict,
    is_research_grade,
)
from experiments.local_llm_event_extraction.datasets import (
    assign_grouped_splits,
    assert_no_leakage,
    build_dataset,
    describe_fixture,
    load_cases,
    load_responses,
)
from experiments.local_llm_event_extraction.schema import (
    EVENT_CATEGORIES,
    EntityClaim,
    EventExtraction,
    EvidenceSpan,
    ExtractionResult,
    ExtractorProvenance,
    SourceDocument,
)

PROVENANCE = ExtractorProvenance(system="scripted", adapter_id="scripted-fixture")
TOTAL_GOLD_EVENTS = 12


def _stub_validator(result, *, document, roster=None, taxonomy=None, config=None):
    """A permissive validator stand-in: proves injection and recording work."""
    judgements = tuple(
        EventJudgement(index=index, verdict=Verdict.ACCEPTED)
        for index, _event in enumerate(result.events)
    )
    return ValidationResult(
        doc_id=result.doc_id,
        verdict=Verdict.ACCEPTED,
        judgements=judgements,
    )


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ------------------------------------------------------------ dataset fixtures
def test_synthetic_fixture_integrity() -> None:
    cases = load_cases()
    assert len(cases) == 14
    assert {case.label_tier for case in cases} == {"synthetic_fixture"}
    assert sum(len(case.gold_events) for case in cases) == TOTAL_GOLD_EVENTS
    assert sum(1 for case in cases if case.is_negative_control) == 3
    assert sum(1 for case in cases if len(case.gold_events) == 2) == 1
    categories = {event.event_category for case in cases for event in case.gold_events}
    assert categories <= set(EVENT_CATEGORIES)
    for case in cases:
        for event in case.gold_events:
            assert event.label_tier == "synthetic_fixture"
            assert event.evidence_quote
            assert event.evidence_quote in case.document.text, event.event_id
    info = describe_fixture()
    assert info["case_count"] == 14
    assert info["gold_event_count"] == TOTAL_GOLD_EVENTS
    assert info["negative_controls"] == 3


def test_scripted_responses_cover_every_case() -> None:
    doc_ids = {case.document.doc_id for case in load_cases()}
    responses = load_responses()
    assert set(responses) == doc_ids
    assert all(isinstance(text, str) and text.strip() for text in responses.values())


def test_trap_document_has_distinct_event_and_publication_dates() -> None:
    case = next(case for case in load_cases() if case.case_id == "nv-002")
    gold = case.gold_events[0]
    assert gold.event_date == "2023-09-12"
    assert gold.published_at == "2024-03-05"
    assert case.document.published_at == "2024-03-05"
    # The text states the date in prose; the label stores the canonical ISO form.
    assert "12 September 2023" in case.document.text
    assert "12 September 2023" in (gold.evidence_quote or "")


# ---------------------------------------------------------------- grouped split
def test_grouped_splits_are_deterministic_and_leak_free() -> None:
    first = assign_grouped_splits(load_cases())
    second = assign_grouped_splits(load_cases())
    assignment = {case.case_id: case.split for case in first.cases}
    assert assignment == {case.case_id: case.split for case in second.cases}
    assert set(assignment.values()) == {"train", "validation", "test"}
    assert_no_leakage(first)
    # No group appears in more than one split.
    group_splits: dict[str, set[str]] = {}
    for case in first.cases:
        group_splits.setdefault(case.group, set()).add(case.split)
    assert all(len(splits) == 1 for splits in group_splits.values())
    dataset = build_dataset()
    assert dataset.source_sha256
    assert all(case.split in ("train", "validation", "test") for case in dataset.cases)


def test_leakage_guard_raises_when_a_group_crosses_splits() -> None:
    dataset = build_dataset()
    cases = list(dataset.cases)
    first = cases[0]
    other_split = "test" if first.split != "test" else "train"
    broken_group = next(case for case in cases if case.group == first.group and case.split != other_split)
    cases[cases.index(broken_group)] = dataclasses.replace(broken_group, split=other_split)
    broken = DatasetManifest(
        name=dataset.name,
        version=dataset.version,
        cases=tuple(cases),
    )
    with pytest.raises(ValueError):
        assert_no_leakage(broken)


# -------------------------------------------------------------- scoring units
def _tiny_dataset() -> DatasetManifest:
    positive_text = "Acme Medical received FDA clearance on 1 May 2025."
    positive = DatasetCase(
        case_id="pos",
        document=SourceDocument(
            doc_id="pos", source_type="press_release", text=positive_text, published_at="2025-05-02"
        ),
        gold_events=(
            GoldEvent(
                event_id="pos-e1",
                company_canonical_id="acme-medical",
                event_category="regulatory_clearance",
                event_date="2025-05-01",
                published_at="2025-05-02",
                evidence_quote=positive_text,
                label_tier="synthetic_fixture",
                label_source="test fixture",
            ),
        ),
        label_tier="synthetic_fixture",
        group="acme",
        split="test",
    )
    negative = DatasetCase(
        case_id="neg",
        document=SourceDocument(
            doc_id="neg",
            source_type="press_release",
            text="Acme Medical reported quarterly revenue.",
            published_at="2025-08-01",
        ),
        gold_events=(),
        expected_abstain=True,
        label_tier="synthetic_fixture",
        group="acme",
        split="test",
    )
    return DatasetManifest(name="tiny", version="v0", cases=(positive, negative))


def _asserted_clearance(doc_id: str = "pos") -> EventExtraction:
    return EventExtraction(
        status="extracted",
        company=EntityClaim(
            raw_text="Acme Medical", canonical_id="acme-medical", match_basis="roster_alias_verbatim"
        ),
        event_category="regulatory_clearance",
        event_date="2025-05-01",
        published_at="2025-05-02",
        evidence=(
            EvidenceSpan(quote="Acme Medical received FDA clearance on 1 May 2025.", field="event_category"),
        ),
    )


def _abstained() -> EventExtraction:
    return EventExtraction(status="abstained", abstain_reason="no_event")


def _result(doc_id: str, events) -> ExtractionResult:
    return ExtractionResult(
        doc_id=doc_id,
        parse_status="ok",
        extractor=PROVENANCE,
        events=tuple(events),
    )


def test_negative_control_scoring_counts_correct_abstention_and_false_assertion() -> None:
    dataset = _tiny_dataset()
    good = {
        "pos": _result("pos", [_asserted_clearance()]),
        "neg": _result("neg", [_abstained()]),
    }
    report = score_predictions(dataset.cases, good)
    assert report.tp == 1 and report.fp == 0 and report.fn == 0
    assert report.precision == 1.0 and report.recall == 1.0
    assert report.abstention_rate == pytest.approx(0.5)
    assert report.wrong_abstention_rate == 0.0
    assert report.false_assertion_rate == 0.0
    assert report.entity_match_accuracy == 1.0
    assert report.parse_failure_rate == 0.0

    bad = {
        "pos": _result("pos", [_abstained()]),
        "neg": _result("neg", [_asserted_clearance("neg")]),
    }
    bad_report = score_predictions(dataset.cases, bad)
    assert bad_report.wrong_abstention_rate == 1.0
    assert bad_report.false_assertion_rate == 1.0
    assert bad_report.recall == 0.0
    assert bad_report.fp == 1 and bad_report.fn == 1


def test_zero_denominators_are_none_not_zero() -> None:
    dataset = _tiny_dataset()
    report = score_predictions(dataset.cases, [])
    assert report.support == 0
    assert report.precision is None
    assert report.recall is None
    assert report.f1 is None
    assert report.abstention_rate is None
    assert report.wrong_abstention_rate is None
    assert report.false_assertion_rate is None
    assert report.parse_failure_rate is None
    assert report.error_taxonomy["missing_prediction"] == 2


def test_parse_failure_is_scored_as_a_failure_not_an_empty_success() -> None:
    dataset = _tiny_dataset()
    failed = ExtractionResult(
        doc_id="pos", parse_status="refused", extractor=PROVENANCE, events=()
    )
    report = score_predictions(dataset.cases, {"pos": failed})
    assert report.recall == 0.0
    assert report.precision is None  # zero predicted events: no denominator
    assert report.f1 is None
    assert report.parse_failure_rate == 1.0
    assert report.error_taxonomy["parse_refused"] == 1


# ------------------------------------------------------------ end to end runs
def _registry_run_kwargs(tmp_path, **overrides):
    kwargs = dict(
        output_dir=tmp_path,
        adapter_ids=["rules-baseline", "scripted-fixture"],
        validator=_stub_validator,
        config={"run_status": "SYNTHETIC_FIXTURE_ONLY"},
    )
    kwargs.update(overrides)
    return kwargs


def test_end_to_end_run_writes_artifacts_and_consistent_metrics(tmp_path) -> None:
    dataset = build_dataset()
    registry = build_registry(environ={})
    run = run_benchmark(dataset, registry, **_registry_run_kwargs(tmp_path))

    assert run.status == "SYNTHETIC_FIXTURE_ONLY"
    assert set(run.metrics_by_adapter) == {"rules-baseline", "scripted-fixture"}
    assert run.not_run == {}
    for name in ("manifest.json", "predictions.jsonl", "metrics.json", "REPORT.md"):
        assert (run.run_dir / name).is_file(), name

    records = _read_jsonl(run.run_dir / "predictions.jsonl")
    assert len(records) == len(dataset.cases) * 2
    assert {(record["adapter_id"], record["case_id"]) for record in records} == {
        (adapter_id, case.case_id)
        for adapter_id in run.metrics_by_adapter
        for case in dataset.cases
    }
    assert all(record["validation_status"] == "ok" for record in records)
    assert all(record["seed"] == 0 for record in records)
    assert all(record["run_status"] == "SYNTHETIC_FIXTURE_ONLY" for record in records)
    assert all(record["label_tier"] == "synthetic_fixture" for record in records)

    asserted_by_adapter: dict[str, int] = {}
    for record in records:
        asserted = sum(
            1
            for event in (record["result"] or {}).get("events", [])
            if event.get("status") == "extracted"
        )
        asserted_by_adapter[record["adapter_id"]] = asserted_by_adapter.get(record["adapter_id"], 0) + asserted

    for adapter_id, report in run.metrics_by_adapter.items():
        # Accounting identities that must hold for every arm.
        assert report.tp + report.fn == TOTAL_GOLD_EVENTS, adapter_id
        assert report.fp == asserted_by_adapter[adapter_id] - report.tp, adapter_id
        assert report.support == len(dataset.cases)
        # Rates with a denominator must be measured (not None), and must be in range.
        for field in (
            "precision",
            "recall",
            "f1",
            "entity_match_accuracy",
            "event_date_accuracy",
            "published_at_accuracy",
            "citation_correctness_rate",
            "abstention_rate",
            "wrong_abstention_rate",
            "false_assertion_rate",
            "parse_failure_rate",
        ):
            value = getattr(report, field)
            assert value is not None, (adapter_id, field)
            assert 0.0 <= value <= 1.0, (adapter_id, field, value)
        assert report.matching_protocol["zero_denominator"] == "null (not measured), never 0.0"

    # The synthetic failures in the canned responses must be visible in the taxonomy.
    taxonomy = run.metrics_by_adapter["scripted-fixture"].error_taxonomy
    assert taxonomy["parse_refused"] >= 1
    assert taxonomy["parse_invalid_json"] >= 1
    assert taxonomy["duplicate_event"] >= 1
    assert taxonomy["citation_not_verbatim"] >= 1
    assert taxonomy["false_assertion"] >= 1
    assert taxonomy["date_mismatch"] >= 1
    assert run.metrics_by_adapter["rules-baseline"].error_taxonomy["false_positive"] == 0

    manifest = json.loads((run.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "SYNTHETIC_FIXTURE_ONLY"
    assert manifest["dataset"]["label_tiers"] == ["synthetic_fixture"]
    assert manifest["seeds"] == [0]
    assert manifest["config_sha256"]
    assert manifest["dataset"]["source_sha256"] == dataset.source_sha256
    assert {entry["adapter_id"] for entry in manifest["adapter"]["adapters"]} == {
        "rules-baseline",
        "scripted-fixture",
    }

    metrics_payload = json.loads((run.run_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics_payload["status"] == "SYNTHETIC_FIXTURE_ONLY"
    assert SYNTHETIC_BANNER in metrics_payload["banner"]

    report_text = (run.run_dir / "REPORT.md").read_text(encoding="utf-8")
    assert SYNTHETIC_BANNER in report_text
    assert "What this does not show" in report_text
    assert "Matching protocol" in report_text
    assert "Per-arm summary" in report_text
    assert "predictions.jsonl" in report_text
    assert "not measured" in report_text

    # Resource honesty: the rules/scripted arms are fast but not tokenised or GPU-backed.
    resources = manifest["resources"]
    assert {"rules-baseline", "scripted-fixture"} <= set(resources)
    for adapter_id in ("rules-baseline", "scripted-fixture"):
        resource = resources[adapter_id]
        assert resource["wall_time_s"] is not None
        assert len(resource["per_case_wall_time_s"]) == len(dataset.cases)
        assert resource["cpu_time_s"] is not None
        assert resource["tokens_in"] is None  # not measured, never 0
        assert resource["tokens_out"] is None
        assert resource["peak_vram_mb"] is None
    assert manifest["config_sha256"] == run.manifest.config_sha256
    assert manifest["git"]["commit"]  # read-only git identity was captured


def test_resume_reuses_completed_cases_and_keeps_metrics_identical(tmp_path) -> None:
    dataset = build_dataset()
    registry = build_registry(environ={})
    kwargs = _registry_run_kwargs(tmp_path)

    first_rules = registry.create("rules-baseline")
    first_scripted = registry.create("scripted-fixture")
    first = run_benchmark(dataset, [first_rules, first_scripted], **kwargs)
    lines_after_first = (first.run_dir / "predictions.jsonl").read_text(encoding="utf-8")
    assert len(first_scripted.calls) == len(dataset.cases)

    second_scripted = registry.create("scripted-fixture")
    second_rules = registry.create("rules-baseline")
    second = run_benchmark(
        dataset,
        [second_rules, second_scripted],
        **{**kwargs, "adapter_ids": None},
    )

    assert second.run_id == first.run_id
    assert (second.run_dir / "predictions.jsonl").read_text(encoding="utf-8") == lines_after_first
    assert len(second_scripted.calls) == 0  # every case reused, nothing re-generated
    for adapter_id in first.metrics_by_adapter:
        assert first.metrics_by_adapter[adapter_id].to_dict() == second.metrics_by_adapter[adapter_id].to_dict()
    assert second.manifest.seeds == first.manifest.seeds


def test_gated_adapters_are_recorded_not_run_without_raising(tmp_path) -> None:
    dataset = build_dataset()
    run = run_benchmark(
        dataset,
        build_registry(environ={}),
        output_dir=tmp_path,
        config={"run_status": "SYNTHETIC_FIXTURE_ONLY"},
    )
    assert run.status == "SYNTHETIC_FIXTURE_ONLY"
    assert set(run.metrics_by_adapter) == {"rules-baseline", "scripted-fixture"}
    assert {"hf-qwen3-4b", "remote-openai-compat"} <= set(run.not_run)
    assert "MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD" in run.not_run["hf-qwen3-4b"]
    assert "MEDRADAR_LOCAL_LLM_ALLOW_REMOTE_API" in run.not_run["remote-openai-compat"]

    manifest = json.loads((run.run_dir / "manifest.json").read_text(encoding="utf-8"))
    by_id = {entry["adapter_id"]: entry for entry in manifest["adapter"]["adapters"]}
    for adapter_id in ("hf-qwen3-4b", "remote-openai-compat"):
        assert by_id[adapter_id]["status"] == "NOT_RUN"
        assert by_id[adapter_id]["loaded"] is False
        assert manifest["adapter"]["not_run"][adapter_id]
        # No fabricated metric row for a gated arm.
        assert adapter_id not in run.metrics_by_adapter
        assert manifest["metrics"][adapter_id]["status"] == "NOT_RUN"

    report_text = (run.run_dir / "REPORT.md").read_text(encoding="utf-8")
    assert "NOT RUN:" in report_text
    assert "`hf-qwen3-4b`" in report_text
    assert "`remote-openai-compat`" in report_text


def test_research_grade_is_refused_before_writing_artifacts(tmp_path) -> None:
    dataset = build_dataset()
    assert is_research_grade(dataset.label_tiers) is False
    with pytest.raises(ValueError):
        run_benchmark(
            dataset,
            build_registry(environ={}),
            output_dir=tmp_path,
            adapter_ids=["scripted-fixture"],
            config={"run_status": "RESEARCH_GRADE"},
        )
    assert list(tmp_path.iterdir()) == []


def test_case_limit_is_recorded_and_applied(tmp_path) -> None:
    dataset = build_dataset()
    run = run_benchmark(
        dataset,
        build_registry(environ={}),
        adapter_ids=["scripted-fixture"],
        output_dir=tmp_path,
        limit=3,
        config={"run_status": "SYNTHETIC_FIXTURE_ONLY"},
    )
    records = _read_jsonl(run.run_dir / "predictions.jsonl")
    assert len(records) == 3
    assert run.manifest.dataset["case_count"] == 3
    assert run.metrics_by_adapter["scripted-fixture"].support == 3
    assert any("case limit" in note for note in run.manifest.notes)


def test_report_writer_refuses_research_grade_for_synthetic_labels(tmp_path) -> None:
    manifest = {
        "run_id": "ripoff",
        "created_at": "2026-01-01T00:00:00+00:00",
        "status": "RESEARCH_GRADE",
        "dataset": {"label_tiers": ["synthetic_fixture"]},
        "adapter": {"adapters": [], "not_run": {}},
        "metrics": {},
        "resources": {},
        "config": {},
        "config_sha256": "0" * 64,
        "seeds": [0],
        "notes": [],
        "git": {},
    }
    with pytest.raises(ValueError):
        write_report(tmp_path, manifest, {})
    assert not (tmp_path / "REPORT.md").exists()
