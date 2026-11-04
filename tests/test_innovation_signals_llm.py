"""Offline tests for the Phase 4 job-text extraction experiment.

No model is loaded, no network is touched, and torch/transformers are never
imported: the model arm is exercised through the harness's scripted (fixture)
adapter, exactly as the existing local-LLM test suite does.  The tests pin the
four properties the experiment's credibility depends on:

1. the job-text contract rejects anything malformed, and in particular **refuses
   to accept a label that carries no verbatim quote**;
2. the evidence locatability check is strict (whitespace-normalised verbatim
   only; a paraphrase fails);
3. abstention is representable and scored, including the negative-control false
   positive that the programme's prior fine-tuning run made worse;
4. the runner + evaluator produce artefacts end to end, and no Precision /
   Recall / F1 number is ever produced without a human gold standard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.innovation_signals_observatory.llm import (
    evaluate,
    job_text_schema as schema,
    prompt_job_v1 as prompt,
    subset,
)
from experiments.innovation_signals_observatory.llm.run_job_text_experiment import (
    _rules_record,
    run_experiment,
)

POSTING_TEXT = (
    "Design and develop next-generation pulsed field ablation catheters. "
    "You will prototype and validate cardiac ablation devices for the EP portfolio."
)


def _valid_payload(**overrides):
    payload = {
        "abstain": False,
        "abstain_reason": None,
        "function_class": "CORE_R&D",
        "function_evidence_quote": "Design and develop next-generation pulsed field ablation catheters",
        "technology_track": "ep_pfa",
        "track_evidence_quote": "pulsed field ablation catheters",
        "capability_phrases": [
            {"text": "pulsed field ablation", "evidence_quote": "pulsed field ablation catheters"}
        ],
        "r_and_d_evidence": True,
        "r_and_d_evidence_quote": "You will prototype and validate cardiac ablation devices",
        "uncertainty_note": None,
    }
    payload.update(overrides)
    return payload


def _abstain_payload(**overrides):
    payload = {
        "abstain": True,
        "abstain_reason": "no_technical_content",
        "function_class": "UNCLASSIFIED",
        "function_evidence_quote": None,
        "technology_track": "UNCLASSIFIED",
        "track_evidence_quote": None,
        "capability_phrases": [],
        "r_and_d_evidence": False,
        "r_and_d_evidence_quote": None,
        "uncertainty_note": None,
    }
    payload.update(overrides)
    return payload


PROVENANCE = schema.ExtractorProvenance(
    system="test",
    adapter_id="test-adapter",
    model_id=None,
    prompt_version="job-extract-v1",
    schema_version=schema.SCHEMA_VERSION,
)


# ------------------------------------------------------------------- contract
def test_valid_extraction_round_trips():
    extraction = schema.extraction_from_dict(_valid_payload())
    assert extraction.function_class == "CORE_R&D"
    assert extraction.technology_track == "ep_pfa"
    assert extraction.r_and_d_evidence is True
    assert extraction.claimed_direction() is True
    assert dict(extraction.claim_quotes())["function_class"].startswith("Design and develop")


def test_unknown_function_class_rejected():
    with pytest.raises(schema.ContractError, match="unknown function_class"):
        schema.extraction_from_dict(_valid_payload(function_class="MADE_UP_CLASS"))


def test_unknown_technology_track_rejected():
    with pytest.raises(schema.ContractError, match="unknown technology_track"):
        schema.extraction_from_dict(
            _valid_payload(technology_track="quantum_teleportation")
        )


@pytest.mark.parametrize(
    "field",
    ["function_evidence_quote", "track_evidence_quote", "r_and_d_evidence_quote"],
)
def test_label_without_quote_is_a_contract_error(field):
    """The core rule: an asserted label with no verbatim quote is not a result."""
    with pytest.raises(schema.ContractError, match="must carry"):
        schema.extraction_from_dict(_valid_payload(**{field: None}))


def test_capability_phrase_requires_evidence_quote():
    with pytest.raises(schema.ContractError, match="requires both"):
        schema.extraction_from_dict(
            _valid_payload(capability_phrases=[{"text": "robotic surgery"}])
        )


def test_abstain_requires_reason():
    with pytest.raises(schema.ContractError, match="must state abstain_reason"):
        schema.extraction_from_dict(_abstain_payload(abstain_reason=None))


def test_abstain_must_not_carry_labels():
    with pytest.raises(schema.ContractError, match="must emit UNCLASSIFIED"):
        schema.extraction_from_dict(_abstain_payload(function_class="CORE_R&D"))
    with pytest.raises(schema.ContractError, match="must not carry capability_phrases"):
        schema.extraction_from_dict(
            _abstain_payload(
                capability_phrases=[
                    {"text": "x", "evidence_quote": "pulsed field ablation catheters"}
                ]
            )
        )


def test_non_abstained_record_must_assert_something():
    with pytest.raises(schema.ContractError, match="made no claim"):
        schema.extraction_from_dict(
            _valid_payload(
                function_class="UNCLASSIFIED",
                function_evidence_quote=None,
                technology_track="UNCLASSIFIED",
                track_evidence_quote=None,
                capability_phrases=[],
                r_and_d_evidence=False,
                r_and_d_evidence_quote=None,
            )
        )


def test_empty_optional_quote_is_absent_but_never_a_claim_quote():
    """Models sometimes encode "no quote" as ""; that is tolerated only when unused."""
    extraction = schema.extraction_from_dict(
        _valid_payload(r_and_d_evidence=False, r_and_d_evidence_quote="")
    )
    assert extraction.r_and_d_evidence_quote is None
    with pytest.raises(schema.ContractError, match="must carry"):
        schema.extraction_from_dict(_valid_payload(function_evidence_quote=""))


def test_unknown_keys_rejected():
    payload = _valid_payload()
    payload["confidence"] = 0.97
    with pytest.raises(schema.ContractError, match="unknown key"):
        schema.extraction_from_dict(payload)


def test_abstain_result_is_valid_and_claims_nothing():
    extraction = schema.extraction_from_dict(_abstain_payload())
    assert extraction.abstain is True
    assert extraction.claimed_direction() is False
    assert extraction.claim_quotes() == ()


# --------------------------------------------------------------------- parsing
def test_parse_fenced_json_and_envelope():
    fenced = "```json\n" + json.dumps(_valid_payload()) + "\n```"
    result = schema.parse_job_response(fenced, posting_id="p1", extractor=PROVENANCE)
    assert result.parse_status == "ok"
    assert result.json_parsed is True

    envelope = json.dumps({"posting_id": "p1", "extraction": _valid_payload()})
    result = schema.parse_job_response(envelope, posting_id="p1", extractor=PROVENANCE)
    assert result.parse_status == "ok"


def test_parse_refusal_and_empty_and_invalid():
    refused = schema.parse_job_response(
        "I am sorry, I cannot help with that.", posting_id="p1", extractor=PROVENANCE
    )
    assert refused.parse_status == "refused"
    assert refused.extraction is None

    empty = schema.parse_job_response("   ", posting_id="p1", extractor=PROVENANCE)
    assert empty.parse_status == "empty"

    broken = schema.parse_job_response(
        '{"abstain": false, "function_class": ', posting_id="p1", extractor=PROVENANCE
    )
    assert broken.parse_status == "invalid_json"


def test_parse_truncated_is_not_invalid_json():
    truncated = schema.parse_job_response(
        '{"abstain": false, "function_class": "CORE_R&D"',
        posting_id="p1",
        extractor=PROVENANCE,
        finish_reason="length",
    )
    assert truncated.parse_status == "truncated"


def test_parse_schema_violation_reports_the_reason():
    result = schema.parse_job_response(
        json.dumps(_valid_payload(function_class="NOPE")),
        posting_id="p1",
        extractor=PROVENANCE,
    )
    assert result.parse_status == "invalid_json"
    assert result.json_parsed is True
    assert "schema decode error" in (result.parse_error or "")


# ---------------------------------------------------------------- locatability
def _record(**overrides):
    record = {
        "arm": "B",
        "posting_id": "p1",
        "sample": "primary",
        "parse_status": "ok",
        "json_parsed": True,
        "abstain": False,
        "abstain_reason": None,
        "technology_track": "ep_pfa",
        "track_evidence_quote": "pulsed field ablation catheters",
        "capability_phrases": [],
        "r_and_d_evidence": True,
        "r_and_d_evidence_quote": "You will prototype and validate cardiac ablation devices",
        "latency_s": 1.0,
    }
    record.update(overrides)
    return record


def _posting(**overrides):
    posting = {"posting_id": "p1", "job_title": "R&D Engineer II", "job_description": POSTING_TEXT}
    posting.update(overrides)
    return posting


def test_quote_locatability_allows_whitespace_differences_only():
    tracks = schema.load_track_registry()
    cues = evaluate.load_function_cues()
    spaced = _record(
        function_class="CORE_R&D",
        function_evidence_quote="Design  and develop   next-generation pulsed field ablation catheters",
    )
    item = evaluate.evaluate_record(spaced, _posting(), tracks=tracks, function_cues=cues)
    assert item["claims_total"] >= 1
    assert item["claims_located"] == item["claims_total"]


def test_paraphrased_quote_is_not_located():
    tracks = schema.load_track_registry()
    cues = evaluate.load_function_cues()
    paraphrased = _record(
        function_class="CORE_R&D",
        function_evidence_quote="Designs and develops new generation PFA catheters",
    )
    item = evaluate.evaluate_record(paraphrased, _posting(), tracks=tracks, function_cues=cues)
    function_claims = [c for c in item["claims"] if c["field"] == "function_class"]
    assert function_claims and function_claims[0]["located"] is False
    assert "quote_not_located" in item["errors"]


def test_track_support_requires_the_track_keyword_family():
    tracks = schema.load_track_registry()
    cues = evaluate.load_function_cues()
    supported = evaluate.evaluate_record(
        _record(function_class="CORE_R&D", function_evidence_quote="pulsed field ablation catheters"),
        _posting(),
        tracks=tracks,
        function_cues=cues,
    )
    assert supported["track_support"] is True

    unsupported = evaluate.evaluate_record(
        _record(
            function_class="CORE_R&D",
            function_evidence_quote="Design and develop next-generation pulsed field ablation catheters",
            technology_track="ep_pfa",
            track_evidence_quote="You will prototype and validate",
        ),
        _posting(),
        tracks=tracks,
        function_cues=cues,
    )
    assert unsupported["track_support"] is False
    assert "track_quote_lacks_track_keyword" in unsupported["errors"]


# ------------------------------------------------------------------- aggregate
def test_summarise_arm_negative_control_and_abstention():
    tracks = schema.load_track_registry()
    cues = evaluate.load_function_cues()
    posting = _posting()
    records = [
        _record(
            posting_id="p1",
            function_class="CORE_R&D",
            function_evidence_quote="pulsed field ablation catheters",
        ),
        # negative control on which the arm invents a track: a false positive
        _record(
            posting_id="p2",
            sample="negative",
            function_class="UNCLASSIFIED",
            function_evidence_quote=None,
            technology_track="ep_pfa",
            track_evidence_quote="pulsed field ablation catheters",
            r_and_d_evidence=False,
            r_and_d_evidence_quote=None,
        ),
        # negative control on which the arm abstains: a correct rejection
        _record(
            posting_id="p3",
            sample="negative",
            abstain=True,
            abstain_reason="no_technical_content",
            function_class="UNCLASSIFIED",
            function_evidence_quote=None,
            technology_track="UNCLASSIFIED",
            track_evidence_quote=None,
            r_and_d_evidence=False,
            r_and_d_evidence_quote=None,
        ),
    ]
    items = [evaluate.evaluate_record(record, posting, tracks=tracks, function_cues=cues) for record in records]
    summary = evaluate.summarise_arm(records, items)
    assert summary["n"] == 3
    assert summary["negative_control"]["n"] == 2
    assert summary["negative_control"]["false_positive_count"] == 1
    assert summary["negative_control"]["false_positive_rate"] == pytest.approx(0.5)
    assert summary["negative_control"]["abstained_count"] == 1
    assert summary["abstention"]["abstain_rate"] == pytest.approx(1 / 3)
    assert summary["precision_recall_f1"].startswith("NOT_EVALUABLE")
    assert "precision" not in {key.lower() for key in summary}


def test_arm_a_prediction_mapping_keeps_raw_output():
    def fake_classifier(job):
        return {
            "function_class": "PRODUCT_ENGINEERING",
            "track_id": None,
            "evidence_spans": [
                {"kind": "function", "field": "job_title", "text": "Engineer", "quote": "Engineer", "target": "PRODUCT_ENGINEERING"}
            ],
            "confidence_basis": {"kind": "rule_derived_not_probability", "calibrated_probability": False},
        }

    posting = {"posting_id": "p9", "job_title": "Engineer II", "job_description": "Engineer work."}
    record = _rules_record(
        posting, sample="primary", run_id="t", classifier=fake_classifier, max_input_chars=3_000
    )
    assert record["arm"] == "A"
    assert record["technology_track"] == "UNCLASSIFIED"  # None is mapped, not passed through
    assert record["raw_arm_output"]["confidence_basis"]["calibrated_probability"] is False
    assert record["evidence_spans"][0]["quote"] == "Engineer"


# ----------------------------------------------------------------- sampling
def _fixture_postings():
    rows = [
        {"posting_id": "a1", "job_title": "R&D Engineer", "job_description": "pulsed field ablation"},
        {"posting_id": "a2", "job_title": "Buyer/Planner", "job_description": "procurement"},
        {"posting_id": "a3", "job_title": "Senior Software Engineer", "job_description": "python"},
        {"posting_id": "a4", "job_title": "Co-op/Apprentice (Non-Tech)", "job_description": "admin"},
        {"posting_id": "a5", "job_title": "Warehouse Assistant", "job_description": "pick and pack"},
        {"posting_id": "a6", "job_title": "Quality Engineer", "job_description": "iso 13485"},
    ]
    return rows


def test_subset_rule_is_deterministic_and_disjoint():
    rows = _fixture_postings()
    first = subset.select_subset(rows, n_primary=3, n_negative=2)
    second = subset.select_subset(list(reversed(rows)), n_primary=3, n_negative=2)
    assert first["primary_ids"] == second["primary_ids"]
    assert first["negative_ids"] == second["negative_ids"]
    assert not set(first["primary_ids"]) & set(first["negative_ids"])
    for row in first["negative"]:
        assert subset.is_negative_title(row["job_title"])
    for row in first["primary"]:
        assert not subset.is_negative_title(row["job_title"])
    # hash order, not file order: the ordering key is reproducible
    assert first["primary_ids"] == sorted(
        first["primary_ids"], key=lambda pid: subset.hash_key(pid)
    )


def test_negative_pattern_does_not_match_technical_titles():
    for title in ("R&D Engineer II", "Senior Software Engineer", "EP Mapping Specialist"):
        assert not subset.is_negative_title(title)
    for title in ("Buyer/Planner", "Warehouse Assistant", "Co-op/Apprentice (Non-Tech)"):
        assert subset.is_negative_title(title)


# --------------------------------------------------------------------- prompt
def test_prompt_is_bounded_closed_and_marks_truncation():
    fp = prompt.prompt_fingerprint()
    assert fp["n_tracks"] > 20
    assert fp["prompt_version"] == prompt.PROMPT_VERSION
    long_posting = {
        "posting_id": "p1",
        "job_title": "R&D Engineer",
        "job_description": "x" * (prompt.DEFAULT_MAX_INPUT_CHARS + 500),
    }
    rendered, meta = prompt.build_job_prompt(long_posting)
    assert meta["truncated"] is True
    assert meta["omitted_chars"] == 500
    assert "[TRUNCATED:" in rendered.user
    assert rendered.system.count("- ") >= len(schema.FUNCTION_CLASSES)
    for track_id in schema.known_track_ids():
        assert track_id in rendered.system
    assert "abstain" in rendered.system.lower()


def test_prompt_template_hash_changes_with_budget():
    assert prompt.template_sha256(max_input_chars=5000) != prompt.template_sha256(max_input_chars=4000)


# ------------------------------------------------------------- end to end stub
def _write_fixture(tmp_path: Path):
    postings = [
        {
            "posting_id": "p1",
            "job_title": "R&D Engineer II",
            "job_description": POSTING_TEXT,
            "job_location": "X",
            "source_posted_at": "2026-11-01",
        },
        {
            "posting_id": "p2",
            "job_title": "Buyer/Planner",
            "job_description": "Sources, purchases and schedules raw materials with production and warehouse personnel.",
            "job_location": "X",
            "source_posted_at": "2026-11-01",
        },
        {
            "posting_id": "p3",
            "job_title": "Data Steward",
            "job_description": "Maintains master data records.",
            "job_location": "X",
            "source_posted_at": "2026-11-01",
        },
    ]
    data_path = tmp_path / "jobs.jsonl"
    data_path.write_text("\n".join(json.dumps(row) for row in postings) + "\n", encoding="utf-8")
    return data_path


def test_end_to_end_stub_run_produces_artefacts(tmp_path):
    data_path = _write_fixture(tmp_path)
    responses = {
        "p1": json.dumps(_valid_payload()),
        "p2": json.dumps(_abstain_payload()),
        "p3": "I am sorry, I cannot help with that.",
    }
    out_dir = tmp_path / "llm"
    manifest = run_experiment(
        arm="stub",
        data_path=data_path,
        out_dir=out_dir,
        n_primary=2,
        n_negative=1,
        max_items=3,
        stub_responses=responses,
    )
    assert manifest["status"] == "COMPLETED"
    assert manifest["subset"]["n_run"] == 3
    assert manifest["arm_C"]["status"] == "NOT_RUN"

    predictions = [json.loads(line) for line in (out_dir / "predictions_stub.jsonl").read_text().splitlines()]
    assert len(predictions) == 3
    assert {row["posting_id"] for row in predictions} == {"p1", "p2", "p3"}

    metrics = json.loads((out_dir / "metrics.json").read_text(encoding="utf-8"))
    arm = metrics["arms"]["stub"]
    assert arm["precision_recall_f1"].startswith("NOT_EVALUABLE")
    assert metrics["arms"]["C"]["status"] == "NOT_RUN"
    assert "regulatory-event" in metrics["arms"]["C"]["reason"]

    table = (out_dir / "ARM_TABLE.md").read_text(encoding="utf-8")
    assert "NOT_RUN" in table
    assert "Precision / Recall / F1" in table
    assert (out_dir / "evaluation_items.json").exists()
    assert (out_dir / "manifest_stub.json").exists()
    # A failed parse is recorded as its own failure class, not as abstention.
    assert arm["parse_status_counts"].get("refused") == 1
    assert arm["abstention"]["abstain_reasons"].get("no_technical_content") == 1
    assert arm["negative_control"]["n"] == 1
    assert arm["negative_control"]["false_positive_count"] == 0
