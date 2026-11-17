"""The optional AI layer: safe degradation, candidate-only output and measured reporting.

No model is loaded here. A stub classifier stands in for Qwen3-0.6B so the *contract* is tested
deterministically: a proposal is stored as a candidate, a fabricated quote is rejected, an
unparseable answer is counted as a JSON failure, and a missing model defers the backlog rather
than breaking discovery.
"""

from __future__ import annotations

import json
from pathlib import Path

import unittest

try:  # the repository's `medradar selftest` runs under unittest without pytest installed
    import pytest
except ModuleNotFoundError:  # pragma: no cover
    raise unittest.SkipTest("pytest is not installed; run these tests with pytest")

from medradar.radar.ai.evaluate import run_evaluation
from medradar.radar.ai.prompts import PROMPT_VERSION, build_prompt, extract_json
from medradar.radar.ai.worker import run_batch
from medradar.radar.ledger import ObservationLedger
from medradar.radar.records import MAPPING_VERSION, PROC_AI_DONE, PROC_AI_FAILED, RawRecord
from medradar.radar.taxonomy import load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"

TITLE = "A modular patient monitor reduced alarm fatigue in intensive care"


class StubClassifier:
    """Deterministic stand-in with the same surface as :class:`QwenClassifier`."""

    model_id = "stub"
    model_version = "stub-1"
    prompt_version = PROMPT_VERSION
    load_seconds = 0.01
    threads = 1
    model_path = Path("stub")

    def __init__(self, output: str) -> None:
        self.output = output

    def load(self):
        return self

    def generate(self, messages):
        return {"text": self.output, "prompt_tokens": 10, "generated_tokens": 20,
                "seconds": 0.5, "tokens_per_second": 40.0}


def _ledger_with_records(tmp_path: Path, count: int = 2) -> ObservationLedger:
    ledger = ObservationLedger(tmp_path / "radar.db")
    ledger.ensure_source("pubmed", label="PubMed", adapter_version="a1", cadence_hours=6)
    from medradar.radar.classify import RuleMapper

    mapper = RuleMapper(load_taxonomy(str(CONFIG_DIR)))
    for index in range(count):
        record = RawRecord(
            source="pubmed", source_record_id=f"pmid:{index}", official_identifier=f"PMID:{index}",
            record_type="publication", title=TITLE,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{index}/",
            published_at="2026-02-01", published_at_precision="date",
            payload={"pmid": str(index), "title": TITLE, "abstract": TITLE},
            text=TITLE, extra={"affiliations": []},
        )
        outcome = ledger.record_observation(record, mapper.map(record), run_id="r",
                                            adapter_version="a1", mapping_version=MAPPING_VERSION)
        ledger.enqueue_task(outcome.observation_id, version_id=outcome.version_id,
                            kind="ai_enrichment")
    return ledger


def test_extract_json_tolerates_a_code_fence_and_surrounding_prose():
    parsed, error = extract_json('Here you go:\n```json\n{"topics": []}\n```\nDone.')
    assert error is None and parsed == {"topics": []}
    assert extract_json("no json here")[0] is None


def test_the_prompt_lists_allowed_ids_and_requires_a_verbatim_quote():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    prompt = build_prompt(
        title=TITLE, body="abstract", record_type="publication", source="pubmed",
        allowed_topics=[topic.public() for topic in taxonomy.topics],
        allowed_organizations=[org.public() for org in taxonomy.organizations],
    )
    assert "ALLOWED TOPIC IDS" in prompt
    assert "spo2_oximetry" in prompt
    assert "copied exactly" in prompt
    assert "No markdown fence" in prompt


def test_an_accepted_proposal_is_a_candidate_and_never_a_confirmed_fact(tmp_path: Path):
    ledger = _ledger_with_records(tmp_path, count=1)
    output = json.dumps({
        "topics": [{"id": "smart_alarms", "evidence_quote": "alarm fatigue"}],
        "organizations": [],
        "summary": "A monitor reduced alarm fatigue.",
    })
    result = run_batch(ledger, load_taxonomy(str(CONFIG_DIR)), limit=1,
                       classifier=StubClassifier(output), log=lambda _m: None)
    assert result["processed"] == 1
    assert result["json_validity_rate"] == 1.0
    assert result["accepted_topic_claims"] == 1
    candidates = ledger.ai_candidates()
    assert len(candidates) == 1
    assert candidates[0]["validation_state"] == "ACCEPTED"
    observation = ledger.observation_row(candidates[0]["observation_id"])
    assert observation["processing_state"] == PROC_AI_DONE
    # The model's output never became a confirmed assertion by itself.
    facets = observation["facets"]
    assert all(item["confirmation"] != "CONFIRMED" for item in facets.get("topic", []))
    ledger.close()


def test_a_fabricated_quote_is_rejected_even_when_the_topic_id_is_valid(tmp_path: Path):
    ledger = _ledger_with_records(tmp_path, count=1)
    output = json.dumps({
        "topics": [{"id": "smart_alarms", "evidence_quote": "the device predicts sepsis"}],
        "organizations": [],
        "summary": "x",
    })
    result = run_batch(ledger, load_taxonomy(str(CONFIG_DIR)), limit=1,
                       classifier=StubClassifier(output), log=lambda _m: None)
    assert result["accepted_topic_claims"] == 0
    assert result["rejected_claims"] == 1
    candidate = ledger.ai_candidates()[0]
    assert candidate["validation_state"] == "REJECTED"
    reason = candidate["validation"]["claims"][0]["reason"]
    assert "verbatim" in reason
    ledger.close()


def test_unparseable_model_output_is_counted_as_a_json_failure(tmp_path: Path):
    ledger = _ledger_with_records(tmp_path, count=1)
    result = run_batch(ledger, load_taxonomy(str(CONFIG_DIR)), limit=1,
                       classifier=StubClassifier("I think this paper is about monitoring."),
                       log=lambda _m: None)
    assert result["json_validity_rate"] == 0.0
    candidate = ledger.ai_candidates()[0]
    assert candidate["validation_state"] == "JSON_INVALID"
    observation = ledger.observation_row(candidate["observation_id"])
    assert observation["processing_state"] == PROC_AI_FAILED
    ledger.close()


def test_a_missing_model_defers_the_backlog_without_losing_it(tmp_path: Path):
    ledger = _ledger_with_records(tmp_path, count=2)
    result = run_batch(ledger, load_taxonomy(str(CONFIG_DIR)), limit=5, model_path=None,
                       classifier=None, log=lambda _m: None)
    if result["state"] == "unavailable":
        assert result["processed"] == 0
        summary = ledger.queue_summary()
        # A deferred task is still backlog: it will be retried, nothing was lost.
        assert summary["by_state"].get("DEFERRED") == 2
        assert summary["backlog"] == 2
        observation = ledger.observation_row(
            ledger.raw("SELECT observation_id FROM observation LIMIT 1")[0]["observation_id"]
        )
        assert observation is not None
    else:  # a model directory happens to exist on this host
        assert result["processed"] >= 1
    ledger.close()


class SequenceClassifier(StubClassifier):
    """Returns one output per call, in order, to reproduce a mixed batch."""

    def __init__(self, outputs):
        super().__init__("")
        self.outputs = list(outputs)
        self.index = 0

    def generate(self, messages):
        text = self.outputs[min(self.index, len(self.outputs) - 1)]
        self.index += 1
        return {"text": text, "prompt_tokens": 10, "generated_tokens": 20,
                "seconds": 0.5, "tokens_per_second": 40.0}


def test_json_validity_is_divided_by_every_attempt_not_by_the_parsed_ones(tmp_path: Path):
    """Regression for the RADAR-001 evaluation defect.

    The acceptance batch had 14 model attempts, 11 parsed outputs and 3 ``json_invalid`` ones,
    but reported a 100% validity rate because the denominator was the parsed-only count. The
    true rate is 11/14 = 0.7857. The three failures are still part of the sample.
    """
    attempts = 14
    ledger = _ledger_with_records(tmp_path, count=attempts)
    good = json.dumps({"topics": [], "organizations": [], "summary": "s"})
    outputs = [good] * 11 + ["I could not answer in the requested format."] * 3
    eval_set = {
        "name": "denominator regression",
        "version": "1",
        "labelled_by": "test",
        "items": [
            {"official_identifier": f"PMID:{index}", "expected_topics": [],
             "expected_organization": None}
            for index in range(attempts)
        ],
    }
    report = run_evaluation(ledger, load_taxonomy(str(CONFIG_DIR)), eval_set,
                            classifier=SequenceClassifier(outputs), log=lambda _m: None)
    metrics = report["metrics"]
    assert metrics["model_attempts"] == attempts
    assert metrics["json_valid_outputs"] == 11
    assert metrics["json_invalid_outputs"] == 3
    assert metrics["json_validity_rate"] == round(11 / 14, 4)
    assert report["eval_set"]["evaluated"] == 11
    assert report["eval_set"]["not_in_ledger"] == 0
    # The three unparseable answers are wrong organisation answers, not absent samples.
    assert metrics["organization_samples"] == attempts
    ledger.close()


def test_evaluation_reports_measured_metrics_against_labels(tmp_path: Path):
    ledger = _ledger_with_records(tmp_path, count=2)
    eval_set = {
        "name": "unit",
        "version": "1",
        "labelled_by": "test",
        "items": [
            {"official_identifier": "PMID:0", "expected_topics": ["smart_alarms"],
             "expected_organization": None},
            {"official_identifier": "PMID:1", "expected_topics": ["spo2_oximetry"],
             "expected_organization": None},
        ],
    }
    output = json.dumps({
        "topics": [{"id": "smart_alarms", "evidence_quote": "alarm fatigue"}],
        "organizations": [],
        "summary": "s",
    })
    report = run_evaluation(ledger, load_taxonomy(str(CONFIG_DIR)), eval_set,
                            classifier=StubClassifier(output), log=lambda _m: None)
    metrics = report["metrics"]
    assert metrics["json_validity_rate"] == 1.0
    assert metrics["evidence_fidelity_rate"] == 1.0
    # The stub answers "smart_alarms" for both records. One label expects it, one expects
    # spO2, so the measured precision and recall are both 0.5 - the metric is real, not a badge.
    assert metrics["topic_precision"] == 0.5
    assert metrics["topic_recall"] == 0.5
    assert 0.0 <= metrics["topic_f1"] <= 1.0
    assert metrics["tokens_per_second"] and metrics["tokens_per_second"] > 0
    assert report["model"]["prompt_version"] == PROMPT_VERSION
    assert report["items"][0]["state"] == "evaluated"
    ledger.close()
