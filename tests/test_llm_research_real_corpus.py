"""Offline tests for the real-document corpus bridge and the third run status.

Two things are covered:

1. ``datasets.real_documents`` -- the loader that turns collected public documents
   into benchmark cases.  Its integrity rule is the important part: a corpus edited
   after collection must fail loudly, and a document must only receive a silver label
   when its own source record carries the asserted value.
2. ``REAL_DOCUMENT_UNLABELLED`` -- the status that exists because real documents with
   no human labels are neither synthetic fixtures nor research grade.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from experiments.local_llm_event_extraction.contracts import (
    default_run_status,
    is_research_grade,
    is_synthetic,
    require_consistent_run_status,
)
from experiments.local_llm_event_extraction.datasets.real_documents import (
    CorpusError,
    build_real_document_dataset,
    load_corpus,
    to_cases,
)

LONG_PROSE = (
    "The sponsor reports that the device was evaluated in a prospective multicentre "
    "study of adults with suspected arrhythmia. Subjects were followed for twelve "
    "months and the primary endpoint was the incidence of device-related adverse "
    "events. The study completed enrolment in the prior year and the results have been "
    "submitted for publication. This paragraph exists only to make the document long "
    "enough to satisfy the loader's minimum length rule."
)


def _document(doc_id: str, company: str, source_type: str, text: str, **overrides):
    payload = {
        "doc_id": doc_id,
        "company_canonical_id": company,
        "source_type": source_type,
        "title": f"Test document {doc_id}",
        "publisher": "test publisher",
        "text": text,
        "text_style": "prose",
        "url": "https://example.invalid/doc",
        "api_endpoint": "https://example.invalid/api",
        "retrieved_at": "2026-11-04T08:00:00+08:00",
        "source_publication_date": "2026-09-01",
        "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "raw_sha256": "0" * 64,
    }
    payload.update(overrides)
    return payload


def _write_corpus(tmp_path, documents):
    corpus = tmp_path / "corpus"
    (corpus / "documents").mkdir(parents=True)
    for document in documents:
        (corpus / "documents" / f"{document['doc_id']}.json").write_text(
            json.dumps(document, indent=2), encoding="utf-8"
        )
    manifest = {"schema_version": "1.0", "documents": [{"doc_id": d["doc_id"]} for d in documents]}
    (corpus / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return corpus


def test_loader_maps_company_and_source_type_and_marks_every_case_as_test(tmp_path) -> None:
    corpus = _write_corpus(
        tmp_path,
        [
            _document("ctgov-T1", "siemens-healthineers", "clinical_trial_registration", LONG_PROSE),
            _document(
                "fda510k-T1",
                "ge-healthcare",
                "regulatory_clearance",
                LONG_PROSE,
                text_style="field_value_rendering",
                decision_date="2026-09-17",
            ),
        ],
    )
    dataset = build_real_document_dataset(corpus)
    assert dataset.case_count == 2
    assert {case.split for case in dataset.cases} == {"test"}  # evaluation-only, never train
    by_id = {case.case_id: case for case in dataset.cases}
    assert by_id["ctgov-T1"].document.source_type == "clinical_trial_record"
    assert by_id["fda510k-T1"].document.source_type == "fda_510k"
    # hyphenated corpus ids must reach the roster's underscore ids
    assert by_id["ctgov-T1"].group == "siemens-healthineers"
    assert by_id["ctgov-T1"].document.metadata["company_canonical_id"] == "siemens_healthineers"
    assert by_id["fda510k-T1"].document.metadata["company_canonical_id"] == "ge_healthcare"


def test_silver_label_uses_the_record_decision_date_and_names_its_source(tmp_path) -> None:
    corpus = _write_corpus(
        tmp_path,
        [
            _document("ctgov-T1", "philips", "clinical_trial_registration", LONG_PROSE),
            _document(
                "fda510k-T1",
                "philips",
                "regulatory_clearance",
                LONG_PROSE,
                decision_date="2026-09-17",
                decision_date_field="decision_date",
            ),
            _document("ctgov-T2", "philips", "clinical_trial_registration", LONG_PROSE, decision_date="2021-10-25", decision_date_field="protocolSection.statusModule.startDateStruct.date"),
        ],
    )
    dataset = build_real_document_dataset(corpus)
    by_id = {case.case_id: case for case in dataset.cases}
    silver = by_id["fda510k-T1"]
    assert silver.label_tier == "source_record_derived"
    assert len(silver.gold_events) == 1
    assert silver.gold_events[0].event_category == "regulatory_clearance"
    assert silver.gold_events[0].event_date == "2026-09-17"
    assert silver.gold_events[0].label_tier == "source_record_derived"
    assert "decision_date" in (silver.gold_events[0].label_source or "")
    # A trial registration's event is the study start, taken from the record's own
    # start-date field -- not the publication date.
    trial = by_id["ctgov-T2"]
    assert trial.gold_events[0].event_category == "clinical_trial_start"
    assert trial.gold_events[0].event_date == "2021-10-25"
    assert "startDateStruct" in (trial.gold_events[0].label_source or "")
    # With silver disabled, nothing is labelled.
    unlabelled = build_real_document_dataset(corpus, silver=False)
    assert all(case.gold_events == () for case in unlabelled.cases)
    assert sorted(set(unlabelled.label_tiers)) == ["unlabelled"]


def test_edited_text_is_rejected_by_the_hash_check(tmp_path) -> None:
    corpus = _write_corpus(tmp_path, [_document("tamper-1", "medtronic", "recall", LONG_PROSE)])
    path = corpus / "documents" / "tamper-1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["text"] = payload["text"] + " An appended sentence that changes the bytes."
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CorpusError) as excinfo:
        load_corpus(corpus)
    assert "content_sha256 mismatch" in str(excinfo.value)


def test_unknown_company_is_a_hard_error(tmp_path) -> None:
    corpus = _write_corpus(tmp_path, [_document("x-1", "unknown-firm", "recall", LONG_PROSE)])
    with pytest.raises(CorpusError) as excinfo:
        load_corpus(corpus)
    assert "unmapped company" in str(excinfo.value)


def test_unknown_source_type_is_a_hard_error(tmp_path) -> None:
    corpus = _write_corpus(tmp_path, [_document("x-2", "philips", "blog_post", LONG_PROSE)])
    with pytest.raises(CorpusError) as excinfo:
        load_corpus(corpus)
    assert "unmapped source_type" in str(excinfo.value)


def test_manifest_records_the_manifest_hash_and_notes(tmp_path) -> None:
    corpus = _write_corpus(tmp_path, [_document("ctgov-T9", "draeger", "recall", LONG_PROSE)])
    dataset = build_real_document_dataset(corpus)
    expected = hashlib.sha256((corpus / "MANIFEST.json").read_bytes()).hexdigest()
    assert dataset.source_sha256 == expected
    assert "no human labels" in (dataset.notes or "")
    assert sorted(set(dataset.label_tiers)) == ["unlabelled"]


# ------------------------------------------------- third run status
def test_real_unlabelled_tier_yields_the_real_document_status() -> None:
    assert default_run_status(("unlabelled",)) == "REAL_DOCUMENT_UNLABELLED"
    assert default_run_status(("source_record_derived", "unlabelled")) == "REAL_DOCUMENT_UNLABELLED"


def test_synthetic_tier_still_yields_the_fixture_status() -> None:
    assert default_run_status(("synthetic_fixture",)) == "SYNTHETIC_FIXTURE_ONLY"
    assert default_run_status(()) == "SYNTHETIC_FIXTURE_ONLY"
    assert is_synthetic(("synthetic_fixture", "unlabelled")) is True


def test_research_grade_requires_research_tiers() -> None:
    assert is_research_grade(("human_confirmed",)) is True
    assert default_run_status(("human_confirmed",)) == "RESEARCH_GRADE"
    with pytest.raises(ValueError):
        require_consistent_run_status("RESEARCH_GRADE", ("source_record_derived",))
    with pytest.raises(ValueError):
        require_consistent_run_status("RESEARCH_GRADE", ("synthetic_fixture",))


def test_synthetic_corpus_cannot_claim_to_be_real_documents() -> None:
    with pytest.raises(ValueError) as excinfo:
        require_consistent_run_status("REAL_DOCUMENT_UNLABELLED", ("synthetic_fixture",))
    assert "include synthetic fixture data" in str(excinfo.value)


def test_status_is_returned_unchanged_when_consistent() -> None:
    assert (
        require_consistent_run_status("REAL_DOCUMENT_UNLABELLED", ("unlabelled",))
        == "REAL_DOCUMENT_UNLABELLED"
    )


def test_report_status_banner_distinguishes_real_from_synthetic() -> None:
    from experiments.local_llm_event_extraction.benchmark.runner import status_banner

    assert status_banner(("human_confirmed",)) is None
    assert "SYNTHETIC_FIXTURE_ONLY" in status_banner(("synthetic_fixture",))
    real = status_banner(("unlabelled",))
    assert "REAL_DOCUMENT_UNLABELLED" in real
    assert "no accuracy claim" in real


def test_to_cases_is_deterministic(tmp_path) -> None:
    corpus = _write_corpus(tmp_path, [_document("ctgov-T9", "draeger", "recall", LONG_PROSE)])
    records = load_corpus(corpus)
    first = to_cases(records)
    second = to_cases(records)
    assert [c.case_id for c in first] == [c.case_id for c in second]
    assert first[0].document.text == second[0].document.text
