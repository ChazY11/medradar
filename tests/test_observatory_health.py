"""Synthetic tier — Observatory health, acquisition phases and seven-day validation.

Everything runs offline against throwaway SQLite ledgers in ``tmp_path``: no network,
no ``data/`` and no real research data. The tests pin the §0 precedence order and the
§6 contract: a source failure, a stale source, a missing backup or a missing restore
drill must never produce an ``OPERATIONAL`` verdict, and a validation that has not
finished can never be reported as passed.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from medradar.observatory import health as health_mod
from medradar.observatory import validation as validation_mod
from medradar.observatory.ledger import ObservationLedger
from medradar.observatory.records import (
    ENTITY_MAPPED,
    OUTCOME_NEW_RECORDS,
    PHASE_BACKFILL,
    PHASE_INCREMENTAL,
    PHASE_INITIAL,
    VALIDATION_IN_PROGRESS,
    VALIDATION_NOT_STARTED,
    VALIDATION_PASSED,
    MappingResult,
    RawRecord,
)

NOW = datetime.now(timezone.utc).replace(microsecond=0)
SOURCES = (
    ("sec_edgar", "SEC EDGAR 公开披露"),
    ("ctgov", "ClinicalTrials.gov 注册库"),
    ("europepmc", "Europe PMC 文献库"),
)
MAPPED = MappingResult(
    entity_id="medtronic", entity_status=ENTITY_MAPPED,
    entity_method="synthetic", entity_confidence=1.0,
)
COLLECTOR = "synthetic-collector/1.0"
MAPPING = "obs-mapping-v1"


# --------------------------------------------------------------------- helpers
def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _record(record_id: str, *, source: str = "sec_edgar") -> RawRecord:
    return RawRecord(
        source=source,
        source_record_id=record_id,
        record_type="sec_8k",
        title=f"合成记录 {record_id}",
        url=f"https://example.invalid/{record_id}",
        payload={"id": record_id},
    )


@pytest.fixture()
def ledger(tmp_path):
    store = ObservationLedger(tmp_path / "observatory.sqlite")
    try:
        for source, label in SOURCES:
            store.ensure_source(
                source,
                label_zh=label,
                adapter_version="test/1.0",
                declared_cadence_zh="每 6 小时轮询",
            )
        yield store
    finally:
        store.close()


def _record_one(ledger: ObservationLedger, record_id: str, *, source: str = "sec_edgar",
                run_id: str, seen_at: str | None = None):
    return ledger.record_observation(
        _record(record_id, source=source),
        MAPPED,
        run_id=run_id,
        collector_version=COLLECTOR,
        mapping_version=MAPPING,
        seen_at=seen_at or _iso(NOW),
    )


def _healthy_sources(ledger: ObservationLedger, *, moment: datetime = NOW) -> None:
    """Give every source a real successful run and freshness at ``moment``."""
    for source, _label in SOURCES:
        run = ledger.start_run(source, trigger="test", collector_version=COLLECTOR)
        ledger.finish_run(run, status="OK", counters={"records_seen": 1, "records_new": 1})
        ledger.note_source_success(source, run_id=run)
        ledger.record_outcome(
            source, run_id=run, outcome=OUTCOME_NEW_RECORDS, new=1, updated=0,
            finished_at=_iso(moment),
        )
        ledger.con.execute(
            "UPDATE source_state SET last_success_at=?, last_attempt_at=? WHERE source=?",
            (_iso(moment), _iso(moment), source),
        )
        ledger.con.commit()


def _healthy_persistence(ledger: ObservationLedger, *, moment: datetime = NOW) -> None:
    ledger.set_runtime("last_backup", {
        "at": _iso(moment - timedelta(hours=2)),
        "status": "OK",
        "verified": True,
        "bundle": "observatory-synthetic",
    })
    ledger.set_runtime("last_restore_drill", {
        "at": _iso(moment - timedelta(days=1)),
        "status": "OK",
        "ok": True,
    })


def _deployed(ledger: ObservationLedger, status: str = "DEPLOYED_LOCAL") -> None:
    ledger.set_deployment({
        "status": status,
        "supervisor": "windows_task",
        "installed_at": _iso(NOW - timedelta(days=1)),
        "host": "synthetic-host",
    })


def _passed_validation(ledger: ObservationLedger) -> None:
    """Simulate a validation explicitly finished by ``validate stop`` after 7 days."""
    ledger.set_validation({
        "protocol_version": validation_mod.PROTOCOL_VERSION,
        "status": VALIDATION_PASSED,
        "started_at": _iso(NOW - timedelta(days=8)),
        "ends_at": _iso(NOW - timedelta(days=1)),
        "target_days": 7,
        "interval_hours": 6.0,
        "planned_slots": 28,
        "note_zh": "synthetic: written by validate stop only after the window ended",
    })


# ----------------------------------------------------------------------- health
def test_health_without_ledger_is_not_deployed(tmp_path):
    """Tier: SYNTHETIC — a missing ledger is an honest NOT_DEPLOYED, not an error."""
    report = health_mod.health(tmp_path / "missing.sqlite")
    assert report["overall"] == "NOT_DEPLOYED"
    assert report["deployment"]["status"] == "NOT_DEPLOYED"
    assert report["sources"] == []
    checks = {check["id"]: check for check in report["checks"]}
    assert checks["ledger_exists"]["ok"] is False
    assert report["persistence"]["backup"]["status"] == "NEVER"
    assert report["persistence"]["restore_drill"]["status"] == "NEVER"


def test_ledger_without_deployment_is_not_deployed_even_with_data(ledger):
    """Tier: SYNTHETIC — observed data does not prove a deployment exists."""
    run = ledger.start_run("sec_edgar", trigger="test", collector_version=COLLECTOR)
    outcome = _record_one(ledger, "DEPLOY-0001", run_id=run)
    ledger.finish_run(run, status="OK", counters={"records_new": 1})
    ledger.note_source_success("sec_edgar", run_id=run)

    report = health_mod.health(ledger.path, now=NOW)
    assert report["overall"] == "NOT_DEPLOYED"
    assert report["deployment"]["status"] == "NOT_DEPLOYED"
    assert report["deployment"]["supervisor"] == "none"
    # the data is real and visible; only the deployment claim is absent
    assert report["ledger"]["observations"] == 1
    assert outcome.observation_id


def test_deployed_healthy_validation_in_progress(ledger):
    """Tier: SYNTHETIC — deployed + healthy + validation running -> VALIDATION_IN_PROGRESS."""
    _healthy_sources(ledger)
    _healthy_persistence(ledger)
    _deployed(ledger)
    validation_mod.start_validation(ledger, started_at=NOW - timedelta(hours=1))

    report = health_mod.health(ledger.path, now=NOW)
    assert report["overall"] == "VALIDATION_IN_PROGRESS"
    assert report["validation"]["status"] == VALIDATION_IN_PROGRESS
    assert report["validation"]["planned_slots"] == 28
    assert report["validation"]["days_remaining"] == pytest.approx(6.958, abs=0.01)
    assert report["deployment"]["status"] == "DEPLOYED_LOCAL"


def test_paused_precedes_degradation(ledger):
    """Tier: SYNTHETIC — an explicit pause is PAUSED, never a fake 'healthy'."""
    _healthy_sources(ledger)
    _healthy_persistence(ledger)
    _deployed(ledger)
    ledger.pause("synthetic maintenance")

    report = health_mod.health(ledger.path, now=NOW)
    assert report["overall"] == "PAUSED"
    assert report["collector"]["running"] is False

    ledger.resume()
    resumed = health_mod.health(ledger.path, now=NOW)
    assert resumed["overall"] != "PAUSED"


def test_one_failing_source_degrades_even_when_others_are_ok(ledger):
    """Tier: SYNTHETIC — a single failing source is visible in the overall verdict."""
    _healthy_sources(ledger)
    _healthy_persistence(ledger)
    _deployed(ledger)
    ledger.con.execute(
        "UPDATE source_state SET status='FAILED', consecutive_failures=3 WHERE source='ctgov'"
    )
    ledger.con.commit()

    report = health_mod.health(ledger.path, now=NOW)
    assert report["overall"] == "DEGRADED"
    failing = [source for source in report["sources"] if source["status"] == "FAILED"]
    assert len(failing) == 1
    assert failing[0]["source"] == "ctgov"
    assert failing[0]["consecutive_failures"] == 3
    # the other two sources stay OK, so the degradation points at a specific source
    assert sum(1 for source in report["sources"] if source["status"] == "OK") == 2
    checks = {check["id"]: check for check in report["checks"]}
    assert checks["sources_healthy"]["ok"] is False
    assert "ctgov" in checks["sources_healthy"]["detail_zh"]


def test_stale_source_degrades(ledger):
    """Tier: SYNTHETIC — an OK source that stopped being fresh is still degraded."""
    _healthy_sources(ledger)
    _healthy_persistence(ledger)
    _deployed(ledger)
    ledger.con.execute(
        "UPDATE source_state SET last_success_at=? WHERE source='europepmc'",
        (_iso(NOW - timedelta(hours=30)),),
    )
    ledger.con.commit()

    report = health_mod.health(ledger.path, now=NOW)
    assert report["overall"] == "DEGRADED"
    stale = [source for source in report["sources"] if source["stale"]]
    assert [source["source"] for source in stale] == ["europepmc"]
    assert stale[0]["freshness_hours"] == pytest.approx(30.0, abs=0.01)
    checks = {check["id"]: check for check in report["checks"]}
    assert checks["freshness"]["ok"] is False


def test_missing_backup_and_drill_never_operational(ledger):
    """Tier: SYNTHETIC — no backup/drill -> checks FAIL and overall DEGRADED."""
    _healthy_sources(ledger)
    _deployed(ledger)

    report = health_mod.health(ledger.path, now=NOW)
    assert report["overall"] == "DEGRADED"
    assert report["overall"] != "OPERATIONAL"
    checks = {check["id"]: check for check in report["checks"]}
    assert checks["backup"]["ok"] is False
    assert checks["backup_freshness"]["ok"] is False
    assert checks["restore_drill"]["ok"] is False
    assert report["persistence"]["backup"]["status"] == "NEVER"
    assert report["persistence"]["restore_drill"]["status"] == "NEVER"

    # a verified backup but no restore drill is still not enough for OPERATIONAL
    ledger.set_runtime("last_backup", {
        "at": _iso(NOW - timedelta(hours=2)), "status": "OK", "verified": True,
    })
    still_degraded = health_mod.health(ledger.path, now=NOW)
    assert still_degraded["overall"] == "DEGRADED"
    checks = {check["id"]: check for check in still_degraded["checks"]}
    assert checks["backup"]["ok"] is True
    assert checks["restore_drill"]["ok"] is False


def test_operational_requires_deployment_backup_drill_and_passed_validation(ledger):
    """Tier: SYNTHETIC — OPERATIONAL is the only state where all checks pass."""
    _healthy_sources(ledger)
    _healthy_persistence(ledger)
    _deployed(ledger)
    _passed_validation(ledger)

    report = health_mod.health(ledger.path, now=NOW)
    assert report["overall"] == "OPERATIONAL"
    assert report["validation"]["status"] == VALIDATION_PASSED
    failing = [check for check in report["checks"] if not check["ok"]]
    assert failing == [], [(check["id"], check["detail_zh"]) for check in failing]


# ------------------------------------------------------------ acquisition phase
def test_phase_assignment_reconstruction_and_append_only(ledger):
    """Tier: SYNTHETIC — phases are append-only metadata, never an UPDATE of rows."""
    first_run = ledger.start_run("sec_edgar", trigger="test", collector_version=COLLECTOR)
    first = _record_one(ledger, "PHASE-A", run_id=first_run)
    ledger.finish_run(first_run, status="OK", counters={"records_new": 1})
    second_run = ledger.start_run("sec_edgar", trigger="test", collector_version=COLLECTOR)
    second = _record_one(ledger, "PHASE-B", run_id=second_run)
    ledger.finish_run(second_run, status="OK", counters={"records_new": 1})

    # Records collected without a phase context carry no labels at all; they are
    # counted as unlabelled rather than guessed into a phase.
    assert ledger.phase_counts() == {"__unlabelled__": 2}

    result = ledger.reconstruct_phases()
    assert result["labelled"] == 2
    assert result["counts"][PHASE_INITIAL] + result["counts"][PHASE_INCREMENTAL] == 2
    counts = ledger.phase_counts()
    assert counts.get(PHASE_INITIAL) == 1
    assert counts.get(PHASE_INCREMENTAL) == 1
    assert sum(counts.values()) == 2

    # Reconstruction is idempotent and never re-labels existing rows.
    assert ledger.reconstruct_phases()["labelled"] == 0
    assert ledger.phase_counts() == counts

    with pytest.raises(ValueError, match="bad acquisition phase"):
        ledger.assign_phase(first.observation_id, "NOT_A_PHASE")

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger.con.execute("UPDATE observation_phase SET phase='HISTORICAL_BACKFILL'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger.con.execute("DELETE FROM observation_phase")

    # The latest phase row wins (append-only history, latest is current).
    ledger.assign_phase(
        first.observation_id, PHASE_INCREMENTAL,
        method="collector_assigned", assigned_at=_iso(NOW + timedelta(days=1)),
    )
    latest = ledger.phase_counts()
    assert latest.get(PHASE_INITIAL, 0) == 0
    assert latest.get(PHASE_INCREMENTAL) == 2


def test_phase_summary_and_backfill_from_origin(ledger):
    """Tier: SYNTHETIC — BACKFILLED origin becomes HISTORICAL_BACKFILL, not initial."""
    from medradar.observatory.records import ORIGIN_BACKFILLED

    live_run = ledger.start_run("sec_edgar", trigger="test", collector_version=COLLECTOR)
    _record_one(ledger, "LIVE-0001", run_id=live_run)
    ledger.finish_run(live_run, status="OK")
    backfill = ledger.record_observation(
        _record("OLD-0001"),
        MAPPED,
        run_id="backfill-run",
        collector_version=COLLECTOR,
        mapping_version=MAPPING,
        seen_at=_iso(NOW),
        origin=ORIGIN_BACKFILLED,
        backfill_reason="synthetic: intentionally imported historical material",
    )
    ledger.reconstruct_phases()

    counts = ledger.phase_counts()
    assert counts.get(PHASE_INITIAL) == 1
    assert counts.get(PHASE_BACKFILL) == 1
    assert ledger.phases_for([backfill.observation_id])[backfill.observation_id] == PHASE_BACKFILL
    summary = ledger.phase_summary()
    assert summary["counts"] == counts
    assert summary["unlabelled"] == 0


# -------------------------------------------------------------------- validation
def test_validation_status_not_started(ledger):
    """Tier: SYNTHETIC — a validation that never started is NOT_STARTED, not passed."""
    status = validation_mod.validation_status(ledger)
    assert status["status"] == VALIDATION_NOT_STARTED
    assert status["planned_slots"] == 0
    assert "不会把未开始的任务报告为通过" in status["note_zh"]


def test_validation_started_now_is_in_progress(ledger):
    """Tier: SYNTHETIC — 28 planned slots, due slots below planned immediately."""
    state = validation_mod.start_validation(ledger, started_at=NOW)
    assert state["status"] == VALIDATION_IN_PROGRESS
    assert state["planned_slots"] == 28

    status = validation_mod.validation_status(ledger, now=NOW)
    assert status["status"] == VALIDATION_IN_PROGRESS
    assert status["slots"]["planned_total"] == 28
    assert status["slots"]["due"] == 0
    assert status["slots"]["due"] < status["slots"]["planned_total"]
    assert status["slots"]["executed"] == 0
    assert status["days_elapsed"] == 0.0
    assert status["days_remaining"] == pytest.approx(7.0, abs=0.001)
    assert status["window_ended"] is False


def test_validation_cannot_stop_passed_before_the_window_ends(ledger):
    """Tier: SYNTHETIC — 'passed' is refused while the seven-day window is open."""
    validation_mod.start_validation(ledger, started_at=NOW)
    with pytest.raises(RuntimeError, match="before its window ends"):
        validation_mod.stop_validation(
            ledger, outcome=VALIDATION_PASSED, now=NOW + timedelta(hours=2),
        )
    # the failed attempt must not mutate the stored state
    assert ledger.get_validation()["status"] == VALIDATION_IN_PROGRESS


def test_validation_simulated_future_computes_metrics_and_allows_passed(ledger):
    """Tier: SYNTHETIC — only after the real window ends may PASSED be written."""
    validation_mod.start_validation(ledger, started_at=NOW)
    future = NOW + timedelta(days=8)

    status = validation_mod.validation_status(ledger, now=future)
    assert status["status"] == VALIDATION_IN_PROGRESS  # still not passed by time alone
    assert status["window_ended"] is True
    assert status["slots"]["planned_total"] == 28
    assert status["slots"]["due"] == 28
    assert status["slots"]["executed"] == 0
    assert status["slots"]["missed"] == 28  # missed is never counted as success
    assert status["runs"]["scheduler_success_rate"] == 0.0

    finished = validation_mod.stop_validation(
        ledger, outcome=VALIDATION_PASSED, now=future,
    )
    assert finished["status"] == VALIDATION_PASSED
    metrics = finished["final_metrics"]
    assert metrics["days_elapsed"] == 7.0
    assert metrics["slots"]["due"] == 28
    assert metrics["duplicates"]["rate"] == 0
    assert metrics["duplicates"]["duplicate_observations"] == 0
    assert metrics["integrity"]["violations"] == 0
    assert metrics["integrity"]["trigger_present"] is True


def test_clean_ledger_has_zero_duplicates_and_integrity_violations(ledger):
    """Tier: SYNTHETIC — the baseline used by the validation metrics is clean."""
    run = ledger.start_run("sec_edgar", trigger="test", collector_version=COLLECTOR)
    _record_one(ledger, "CLEAN-0001", run_id=run)
    ledger.finish_run(run, status="OK", counters={"records_new": 1})
    validation_mod.start_validation(ledger, started_at=NOW)

    status = validation_mod.validation_status(ledger, now=NOW + timedelta(hours=1))
    duplicates = status["duplicates"]
    assert duplicates["duplicate_observations"] == 0
    assert duplicates["replayed_versions"] == 0
    assert duplicates["rate"] == 0
    integrity = status["integrity"]
    assert integrity["violations"] == 0
    assert integrity["issue_kinds"] == []
    assert integrity["trigger_present"] is True
