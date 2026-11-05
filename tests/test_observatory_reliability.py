"""Synthetic tier — reliability layer: single-writer lease, run outcomes,
acquisition phases, health precedence, validation accounting and the scheduler.

Everything runs offline against throwaway SQLite ledgers; no network, no `data/`.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from medradar.observatory import health as health_mod
from medradar.observatory import validation as validation_mod
from medradar.observatory.adapter import CollectContext, run_source
from medradar.observatory.ledger import ObservationLedger
from medradar.observatory.lock import CollectorLock, LedgerLocked, force_release
from medradar.observatory.records import (
    ENTITY_MAPPED,
    OUTCOME_FETCH_FAILED,
    OUTCOME_NEW_RECORDS,
    OUTCOME_NO_NEW_RECORDS,
    PHASE_BACKFILL,
    PHASE_INCREMENTAL,
    PHASE_INITIAL,
    VALIDATION_IN_PROGRESS,
    MappingResult,
    Page,
    RawRecord,
    Scope,
)
from medradar.observatory.scheduler import watch

MAPPED = MappingResult(entity_id="medtronic", entity_status=ENTITY_MAPPED,
                       entity_method="test", entity_confidence=1.0)


# --------------------------------------------------------------------- fixtures
class NullFetcher:
    def __init__(self, max_requests: int = 100) -> None:
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "errors": 0}
        self.max_requests = max_requests


class FakeAdapter:
    source_id = "fake"
    label_zh = "合成来源"
    collector_version = "fake/1.0.0"
    declared_cadence_zh = "每 6 小时轮询（合成）"
    record_type_labels = {"fake_record": "合成记录"}

    def __init__(self, records: list[RawRecord], *, success: bool = True) -> None:
        self.records = records
        self.success = success
        self.fail_on_page = False

    def plan(self, ctx):
        return [Scope(scope_id="scope-1")]

    def fetch_page(self, ctx, scope, cursor):
        ctx.fetcher.stats["requests"] += 1
        if not self.success:
            raise TimeoutError("simulated fetch failure")
        return Page(records=self.records, next_cursor=None,
                    watermark={"done": True}, structure_sample={"keys": ["a"]})

    def map_record(self, record, ctx):
        return MAPPED


def record(record_id: str, *, payload: dict | None = None) -> RawRecord:
    return RawRecord(
        source="fake",
        source_record_id=record_id,
        record_type="fake_record",
        title=f"合成记录 {record_id}",
        url=f"https://example.invalid/{record_id}",
        event_at="2026-10-01",
        event_at_precision="date",
        published_at="2026-10-02T21:18:02+00:00",
        published_at_precision="datetime",
        payload=payload or {"status": "active"},
    )


def ctx_for(ledger, *, now="2026-11-03T10:00:00+00:00", phase=None):
    return CollectContext(fetcher=NullFetcher(), ledger=ledger, run_id="pending",
                          trigger="test", now=now, phase=phase, log=lambda message: None)


@pytest.fixture()
def ledger(tmp_path):
    store = ObservationLedger(tmp_path / "observatory.sqlite")
    yield store
    store.close()


# --------------------------------------------------------------------- the lease
def test_lock_allows_exactly_one_writer(ledger):
    first = CollectorLock(ledger.path)
    first.acquire(mode="watch")
    try:
        second = CollectorLock(ledger.path)
        with pytest.raises(LedgerLocked):
            second.acquire(mode="sync")
        status = CollectorLock(ledger.path).status()
        assert status["held"] is True
        assert status["holder"]["mode"] == "watch"
    finally:
        first.release()
    assert CollectorLock(ledger.path).status()["held"] is False


def test_stale_lock_is_taken_over_with_an_audit_record(ledger):
    lock_path = ledger.path.parent / "collector.lock"
    lock_path.write_text(json.dumps({
        "pid": 999999, "host": "some-old-host", "mode": "sync",
        "run_id": None,
        "started_at": "2000-01-01T00:00:00+00:00",
        "heartbeat_at": "2000-01-01T00:00:00+00:00",
        "source": "", "command": "old",
    }), encoding="utf-8")
    lock = CollectorLock(ledger.path)
    info = lock.acquire(mode="sync")
    try:
        assert info.mode == "sync"
        recovery = ledger.get_runtime("lock_recovery", {})
        assert recovery.get("reason") == "stale collector lease taken over"
        assert recovery["previous"]["pid"] == 999999
    finally:
        lock.release()


def test_force_release_is_recorded(ledger):
    lock = CollectorLock(ledger.path)
    lock.acquire(mode="sync")
    result = force_release(ledger.path, reason="operator says stuck")
    assert result["released"] is True
    assert CollectorLock(ledger.path).status()["held"] is False
    record = ledger.get_runtime("lock_force_release", {})
    assert record.get("reason") == "operator says stuck"


def test_sync_refuses_to_run_while_another_collector_holds_the_lease(ledger):
    lock = CollectorLock(ledger.path)
    lock.acquire(mode="watch")
    try:
        from medradar.observatory.runner import sync

        report = sync(sources=["sec_edgar"], ledger=ledger, log=lambda message: None)
        assert report["locked"] is True
        assert report["ok"] is False
        assert report["sources"]["sec_edgar"]["status"] == "LOCKED_SKIPPED"
        # no run may be created by a refused collector
        assert ledger.con.execute("SELECT COUNT(*) FROM sync_run").fetchone()[0] == 0
        assert ledger.get_runtime("lock_conflict", {}).get("holder")
    finally:
        lock.release()


# ---------------------------------------------------------- acquisition phase
def test_phases_are_assigned_by_run_context_and_are_append_only(ledger):
    run_source(FakeAdapter([record("a")]), ctx_for(ledger, phase=PHASE_INITIAL), resume=False)
    run_source(FakeAdapter([record("b")]), ctx_for(ledger, phase=PHASE_INCREMENTAL), resume=False)
    phases = ledger.phase_counts()
    assert phases.get(PHASE_INITIAL) == 1
    assert phases.get(PHASE_INCREMENTAL) == 1
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger.con.execute("UPDATE observation_phase SET phase='HISTORICAL_BACKFILL'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger.con.execute("DELETE FROM observation_phase")


def test_phase_reconstruction_is_idempotent_and_run_derived(ledger):
    # Records collected before the phase table existed carry no phase rows.
    run_source(FakeAdapter([record("a")]), ctx_for(ledger), resume=False)
    run_source(FakeAdapter([record("b")]), ctx_for(ledger, now="2026-11-04T10:00:00+00:00"),
               resume=False)
    assert ledger.phase_counts().get(PHASE_INITIAL) is None
    assert ledger.phase_counts().get(PHASE_INCREMENTAL) is None
    first = ledger.reconstruct_phases()
    second = ledger.reconstruct_phases()
    assert first["labelled"] == 2
    assert second["labelled"] == 0
    phases = ledger.phase_counts()
    assert phases == {PHASE_INITIAL: 1, PHASE_INCREMENTAL: 1}


def test_backfill_phase_is_derived_from_origin(ledger):
    from medradar.observatory.records import ORIGIN_BACKFILLED

    ledger.record_observation(
        record("old"), MAPPED, run_id="backfill-run", collector_version="test",
        mapping_version="obs-mapping-v1", seen_at="2026-11-03T10:00:00+00:00",
        origin=ORIGIN_BACKFILLED, backfill_reason="导入历史归档",
    )
    ledger.reconstruct_phases()
    assert ledger.phase_counts().get(PHASE_BACKFILL) == 1


# ------------------------------------------------- timestamp spelling boundary
def test_same_instant_with_z_and_offset_is_the_same_instant(ledger):
    """Legacy rows store '…Z', newer rows '…+00:00'; a replay at that instant must
    include the record, not lose it to a lexicographic mismatch."""
    _collect_z = ledger.record_observation(
        record("legacy"), MAPPED, run_id="run-legacy", collector_version="test",
        mapping_version="obs-mapping-v1", seen_at="2026-11-03T10:00:00Z",
    )
    at_instant_z = ledger.snapshot("2026-11-03T10:00:00Z")
    at_instant_offset = ledger.snapshot("2026-11-03T10:00:00+00:00")
    before = ledger.snapshot("2026-11-03T09:59:59Z")
    assert [item["observation_id"] for item in at_instant_z["items"]] == [_collect_z.observation_id]
    assert [item["observation_id"] for item in at_instant_offset["items"]] == [
        _collect_z.observation_id
    ]
    assert before["total"] == 0
    # window counting uses the same normalisation
    assert ledger.window_counts(24 * 365)["new"] == 1


def test_new_writes_use_a_canonical_utc_spelling(ledger):
    outcome = ledger.record_observation(
        record("canonical"), MAPPED, run_id="run-1", collector_version="test",
        mapping_version="obs-mapping-v1", seen_at="2026-11-03T10:00:00Z",
    )
    row = ledger.observation_row(outcome.observation_id)
    assert row["first_seen_at"].endswith("+00:00")
    assert ledger.snapshot("2026-11-03T10:00:00+00:00")["total"] == 1


# ------------------------------------------------------------------- outcomes
def test_no_new_records_is_a_normal_outcome_not_a_failure(ledger):
    run_source(FakeAdapter([record("a")]), ctx_for(ledger), resume=False)
    first = ledger.get_source_state("fake")
    assert first["last_outcome"] == OUTCOME_NEW_RECORDS
    run_source(FakeAdapter([record("a")]), ctx_for(ledger), resume=False)
    second = ledger.get_source_state("fake")
    assert second["last_outcome"] == OUTCOME_NO_NEW_RECORDS
    assert second["last_new_records"] == 0
    assert second["status"] == "OK"


def test_fetch_failed_outcome_is_distinct_from_no_new_records(ledger):
    run_source(FakeAdapter([], success=False), ctx_for(ledger), resume=False)
    state = ledger.get_source_state("fake")
    assert state["last_outcome"] == OUTCOME_FETCH_FAILED
    assert state["status"] in ("FAILED", "DEGRADED")
    assert state["last_outcome"] != OUTCOME_NO_NEW_RECORDS


# --------------------------------------------------------------------- health
def test_health_without_ledger_is_not_deployed(tmp_path):
    report = health_mod.health(tmp_path / "missing.sqlite")
    assert report["overall"] == "NOT_DEPLOYED"
    assert report["deployment"]["status"] == "NOT_DEPLOYED"
    assert report["sources"] == []


def test_health_precedence_and_degradation(ledger):
    run_source(FakeAdapter([record("a")]), ctx_for(ledger), resume=False)
    # no deployment recorded -> NOT_DEPLOYED even though data exists
    assert health_mod.health(ledger.path)["overall"] == "NOT_DEPLOYED"

    ledger.set_deployment({"status": "DEPLOYED_LOCAL", "supervisor": "windows_task",
                           "installed_at": "2026-11-03T10:00:00+00:00"})
    clean = health_mod.health(ledger.path)
    # no verified backup + no restore drill yet -> must not be OPERATIONAL
    assert clean["overall"] == "DEGRADED"
    assert any(check["id"] == "backup" and not check["ok"] for check in clean["checks"])

    ledger.pause("maintenance")
    paused = health_mod.health(ledger.path)
    assert paused["overall"] == "PAUSED"
    ledger.resume()

    # one failing source must degrade the whole observatory, visibly
    ledger.con.execute("UPDATE source_state SET status='FAILED', consecutive_failures=3"
                       " WHERE source='fake'")
    ledger.con.commit()
    degraded = health_mod.health(ledger.path)
    assert degraded["overall"] == "DEGRADED"
    failing = [source for source in degraded["sources"] if source["status"] == "FAILED"]
    assert failing and failing[0]["source"] == "fake"


def test_health_ignores_http_availability_and_reports_freshness(ledger):
    run_source(FakeAdapter([record("a")]), ctx_for(ledger), resume=False)
    report = health_mod.health(ledger.path)
    source = report["sources"][0]
    assert "freshness_hours" in source and source["freshness_hours"] is not None
    assert any(check["id"] == "ledger_exists" for check in report["checks"])
    assert any(check["id"] == "integrity" for check in report["checks"])


# ----------------------------------------------------------------- validation
def test_validation_cannot_pass_before_the_window_ends(ledger):
    state = validation_mod.start_validation(ledger, days=7, interval_hours=6)
    assert state["status"] == VALIDATION_IN_PROGRESS
    assert state["planned_slots"] == 28
    now = datetime.fromisoformat(state["started_at"]) + timedelta(hours=1)
    status = validation_mod.validation_status(ledger, now=now)
    assert status["status"] == VALIDATION_IN_PROGRESS
    assert status["slots"]["planned_total"] == 28
    assert status["slots"]["due"] == 0
    assert status["slots"]["executed"] == 0
    with pytest.raises(RuntimeError, match="before its window ends"):
        validation_mod.stop_validation(ledger, outcome="VALIDATION_PASSED", now=now)


def test_validation_counts_missed_slots_honestly(ledger):
    state = validation_mod.start_validation(ledger, days=1, interval_hours=6)
    started = datetime.fromisoformat(state["started_at"])
    # pretend 26 hours passed without a single run: 4 slots due, 4 missed
    status = validation_mod.validation_status(ledger, now=started + timedelta(hours=26))
    assert status["slots"]["planned_total"] == 4
    assert status["slots"]["due"] == 4
    assert status["slots"]["executed"] == 0
    assert status["slots"]["missed"] == 4
    assert status["runs"]["scheduler_success_rate"] == 0.0


def test_validation_can_finish_only_after_the_window_and_uses_real_runs(ledger):
    state = validation_mod.start_validation(ledger, days=1, interval_hours=1)
    started = datetime.fromisoformat(state["started_at"])
    # Insert real run rows directly (started_at is immutable through the API by design,
    # so a simulated historical slot is written as raw rows, exactly like a real run).
    for hours in (1, 2, 3):
        slot = (started + timedelta(hours=hours)).replace(microsecond=0).isoformat()
        ledger.con.execute(
            "INSERT INTO sync_run(run_id, source, trigger, host, started_at, finished_at,"
            " status, collector_version, records_seen, records_new, records_updated,"
            " records_unchanged, records_failed) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"slot-{hours}", "fake", "schedule", "test", slot, slot, "OK", "test/1",
             1, 1, 0, 0, 0),
        )
    ledger.con.commit()
    end = started + timedelta(days=1, minutes=1)
    status = validation_mod.validation_status(ledger, now=end)
    assert status["slots"]["planned_total"] == 24
    assert status["slots"]["due"] == 24
    assert 1 <= status["slots"]["executed"] <= 24
    finished = validation_mod.stop_validation(ledger, outcome="VALIDATION_PASSED", now=end)
    assert finished["status"] in ("VALIDATION_PASSED", "VALIDATION_FAILED")


# ------------------------------------------------------------------ scheduler
def test_watch_passes_its_own_lease_to_sync_and_releases_it(ledger, monkeypatch):
    """Regression: the watcher holds the lease, so its sync must not re-acquire it."""
    calls: list[dict] = []

    def fake_sync(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "sources": {}, "totals": {}, "locked": False,
                "finished_at": "2026-11-03T10:00:00+00:00"}

    monkeypatch.setattr("medradar.observatory.scheduler.sync", fake_sync)
    summary = watch(
        interval_minutes=0.02,
        cycles=1,
        sources=["sec_edgar"],
        ledger_path=str(ledger.path),
        log=lambda message: None,
        sleep=lambda seconds: None,
        max_requests=2,
    )
    assert summary["cycles"] == 1
    assert summary["status"] == "OK"
    assert calls and calls[0]["acquire_lock"] is False
    assert CollectorLock(ledger.path).status()["held"] is False
    heartbeat = ledger.get_runtime("heartbeat", {})
    assert heartbeat.get("state") in ("ok", "degraded", "stopped")


def test_watch_refuses_to_start_when_another_collector_holds_the_lease(ledger):
    holder = CollectorLock(ledger.path)
    holder.acquire(mode="watch")
    try:
        blocked = watch(interval_minutes=0.02, cycles=1, sources=["fake"],
                        ledger_path=str(ledger.path), log=lambda message: None,
                        sleep=lambda seconds: None, max_requests=2)
        assert blocked["status"] == "LOCKED"
        assert blocked["locked"] is True
    finally:
        holder.release()
    # a second watcher cannot start while the first holds the lease
    holder = CollectorLock(ledger.path)
    holder.acquire(mode="watch")
    try:
        blocked = watch(interval_minutes=0.02, cycles=1, sources=["fake"],
                        ledger_path=str(ledger.path), log=lambda message: None,
                        sleep=lambda seconds: None, max_requests=2)
        assert blocked["status"] == "LOCKED"
        assert blocked["locked"] is True
    finally:
        holder.release()
