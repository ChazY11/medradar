"""PILOT-READY-001 P0-01: advance() must converge, and say why it stopped.

Before the fix, continuation was tested against the *cumulative* admission counter, so the first
run that admitted anything could never observe an empty batch: it always burnt the whole batch
budget and reported converged=False even when it had finished. On the production-shaped ledger
(8,358 observations) that was 60 batches instead of 22, and on a 15,000-observation load fixture
60 instead of 39. The tests below pin the behaviour that replaced it:

* an idle ledger converges in one batch;
* a run that does real work converges as soon as the work is gone;
* a re-queued judgement with identical evidence neither duplicates history nor loops;
* an exhausted budget is reported as PARTIAL with the remaining counts, and the next call
  finishes the job instead of the work being skipped;
* a deadline stops the call with its own reported reason.
"""

from __future__ import annotations

from pathlib import Path

try:
    import pytest  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - the offline CI suite has no pytest
    raise unittest.SkipTest("pytest is not installed; run these tests with pytest")

from medradar.radar.classify import RuleMapper
from medradar.radar.engine import advance, apply_admissions, pipeline_backlog
from medradar.radar.graph import open_graph
from medradar.radar.ledger import ObservationLedger
from medradar.radar.records import MAPPING_VERSION, RawRecord
from medradar.radar.relevance import ADMISSION_VERSION
from medradar.radar.taxonomy import load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"


def _taxonomy():
    return load_taxonomy(str(CONFIG_DIR))


def _ledger(tmp_path: Path) -> ObservationLedger:
    handle = ObservationLedger(tmp_path / "radar.db")
    handle.ensure_source("openfda_device", label="FDA", adapter_version="a1", cadence_hours=24)
    handle.ensure_source("pubmed", label="PubMed", adapter_version="a1", cadence_hours=6)
    return handle


def _add(ledger: ObservationLedger, index: int, *, source: str = "pubmed") -> str:
    record = RawRecord(
        source=source, source_record_id=f"rec-{index}", official_identifier=f"rec-{index}",
        record_type="publication", title=f"Accuracy of a bedside monitor, study {index}",
        url=f"https://example.test/rec-{index}", published_at="2026-11-10",
        published_at_precision="date",
        payload={"title": f"Accuracy of a bedside monitor, study {index}",
                 "abstract": "We evaluated accuracy of a patient monitor against reference oximetry."},
        text="accuracy patient monitor oximetry",
        extra={"official_identifier": f"rec-{index}"},
    )
    return ledger.record_observation(
        record, RuleMapper(_taxonomy()).map(record), run_id="r", adapter_version="a1",
        mapping_version=MAPPING_VERSION,
    ).observation_id


def _run(ledger: ObservationLedger, tmp_path: Path, **kwargs):
    graph = open_graph(tmp_path / "graph.db", _taxonomy())
    try:
        return advance(ledger, graph, _taxonomy(), log=lambda *_a: None, **kwargs)
    finally:
        graph.store.close()


def test_an_idle_ledger_converges_in_one_batch(tmp_path: Path):
    ledger = _ledger(tmp_path)
    result = _run(ledger, tmp_path, enqueue_ai=False)
    assert result["status"] == "CONVERGED"
    assert result["converged"] is True
    assert result["batches"] == 1
    assert result["backlog"]["total"] == 0
    ledger.close()


def test_a_run_that_admits_records_converges_instead_of_burning_the_budget(tmp_path: Path):
    ledger = _ledger(tmp_path)
    for index in range(3):
        _add(ledger, index)
    result = _run(ledger, tmp_path, enqueue_ai=False)
    assert result["admitted"] == 3, "three new admission history rows"
    assert result["converged"] is True, (
        "the batch after the admissions did no work, so this must be finished - testing the "
        "cumulative counter instead of this batch's delta made this unreachable")
    assert result["batches"] < 10
    assert result["status"] == "CONVERGED"
    assert result["backlog"]["total"] == 0


def test_a_second_run_changes_nothing_and_says_so(tmp_path: Path):
    ledger = _ledger(tmp_path)
    for index in range(2):
        _add(ledger, index)
    first = _run(ledger, tmp_path, enqueue_ai=False)
    assert first["converged"] is True
    history_before = ledger.con.execute(
        "SELECT COUNT(*) FROM observation_admission").fetchone()[0]

    second = _run(ledger, tmp_path, enqueue_ai=False)
    assert second["batches"] == 1
    assert second["admitted"] == 0
    assert second["reclassified"] == 0
    assert second["converged"] is True
    assert ledger.con.execute(
        "SELECT COUNT(*) FROM observation_admission").fetchone()[0] == history_before
    ledger.close()


def test_a_requeued_judgement_with_identical_evidence_neither_duplicates_nor_loops(tmp_path: Path):
    ledger = _ledger(tmp_path)
    observation_id = _add(ledger, 0)
    _run(ledger, tmp_path, enqueue_ai=False)
    history_before = ledger.con.execute(
        "SELECT COUNT(*) FROM observation_admission").fetchone()[0]

    # A mapping edit that produces byte-identical output re-queues the judgement. Same evidence
    # and same rules means the same evidence_key, so no new history row may appear.
    ledger.queue_admission(observation_id, "mapping_changed")
    assert apply_admissions(ledger, limit=100) == 0, (
        "identical evidence must insert nothing, so the caller must not read it as progress")
    assert ledger.con.execute(
        "SELECT COUNT(*) FROM observation_admission").fetchone()[0] == history_before
    assert apply_admissions(ledger, limit=100) == 0

    result = _run(ledger, tmp_path, enqueue_ai=False)
    assert result["converged"] is True
    assert result["batches"] == 1
    ledger.close()


def test_an_exhausted_budget_is_reported_and_the_next_call_finishes_the_work(tmp_path: Path):
    ledger = _ledger(tmp_path)
    for index in range(5):
        _add(ledger, index)

    part = _run(ledger, tmp_path, enqueue_ai=False, limit=1, max_batches=1)
    assert part["converged"] is False
    assert part["status"] == "PARTIAL"
    assert part["stop_reason"] == "batch_budget_exhausted"
    assert part["backlog"]["total"] > 0, "the remaining work is counted, not guessed"
    assert part["backlog"]["admission"] + part["backlog"]["publish"] > 0

    rest = _run(ledger, tmp_path, enqueue_ai=False)
    assert rest["status"] == "CONVERGED"
    assert rest["backlog"]["total"] == 0, "no record was skipped to reach this"
    assert ledger.con.execute(
        "SELECT COUNT(*) FROM observation_admission").fetchone()[0] == 5
    ledger.close()


def test_a_deadline_stops_the_call_with_its_own_reason(tmp_path: Path):
    ledger = _ledger(tmp_path)
    for index in range(4):
        _add(ledger, index)
    result = _run(ledger, tmp_path, enqueue_ai=False, limit=1, deadline_seconds=0.0)
    assert result["converged"] is False
    assert result["status"] == "PARTIAL"
    assert result["stop_reason"] == "deadline_exceeded"
    assert result["elapsed_seconds"] >= 0
    ledger.close()


def test_the_backlog_count_matches_the_pending_query(tmp_path: Path):
    ledger = _ledger(tmp_path)
    for index in range(4):
        _add(ledger, index)
    pending = ledger.admission_pending(ADMISSION_VERSION, limit=100)
    backlog = pipeline_backlog(ledger, enqueue_ai=False)
    assert backlog["admission"] == len(pending)
    assert backlog["mapping"] == 0, "every record was written under the current rule version"
    ledger.close()


def test_stale_rules_are_rechecked_without_fabricating_a_second_judgement(tmp_path: Path):
    ledger = _ledger(tmp_path)
    for index in range(3):
        _add(ledger, index)
    _run(ledger, tmp_path, enqueue_ai=False)
    history_before = ledger.con.execute(
        "SELECT COUNT(*) FROM observation_admission").fetchone()[0]

    # A deployment can leave rows whose stored rule digest is older than the running rules. The
    # records become pending again, are re-judged, and - because the evidence and the rules are
    # the same as before - the same evidence_key is produced. Nothing is appended and nothing is
    # looped over: the decision is refreshed in place and the run converges.
    ledger.con.execute("UPDATE admission_current SET rules_digest='older-rules'")
    ledger.con.commit()
    assert len(ledger.admission_pending(ADMISSION_VERSION, limit=100)) == 3

    result = _run(ledger, tmp_path, enqueue_ai=False)
    assert result["admitted"] == 0, "identical evidence under identical rules adds no history"
    assert result["converged"] is True
    assert ledger.con.execute(
        "SELECT COUNT(*) FROM observation_admission").fetchone()[0] == history_before
    assert ledger.con.execute(
        "SELECT COUNT(*) FROM admission_current WHERE rules_digest='older-rules'"
    ).fetchone()[0] == 0, "the stale digest was refreshed, so it will not be pending again"
    ledger.close()


def test_a_real_rules_change_appends_history_and_keeps_the_earlier_judgement(
        tmp_path: Path, monkeypatch):
    ledger = _ledger(tmp_path)
    for index in range(3):
        _add(ledger, index)
    _run(ledger, tmp_path, enqueue_ai=False)
    history_before = ledger.con.execute(
        "SELECT COUNT(*) FROM observation_admission").fetchone()[0]

    # A rules edit changes the digest, which is part of what was judged. The judgement is a new
    # one: it is appended next to the old row, never written over it.
    import medradar.radar.engine as engine_module
    monkeypatch.setattr(engine_module, "rules_digest", lambda: "a-different-rule-set")
    assert len(ledger.admission_pending(ADMISSION_VERSION, limit=100)) == 3
    result = _run(ledger, tmp_path, enqueue_ai=False)
    assert result["admitted"] == 3
    assert result["converged"] is True
    assert ledger.con.execute(
        "SELECT COUNT(*) FROM observation_admission").fetchone()[0] == history_before + 3, (
        "the earlier judgement stays as history")
    assert ledger.con.execute(
        "SELECT COUNT(*) FROM admission_current WHERE rules_digest='a-different-rule-set'"
    ).fetchone()[0] == 3
    ledger.close()
