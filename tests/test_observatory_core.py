"""Synthetic tier — Live Observatory core: ledger invariants, engine, replay.

Everything here runs offline against a throwaway SQLite file and a fake adapter.
Nothing in this file proves that a real API works; that is what the acceptance
harness (`scripts/observatory_acceptance.py`) and the `MEDRADAR_LIVE_TESTS` tests
are for. This file proves the *scientific guarantees* hold mechanically.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from medradar.observatory.adapter import CollectContext, run_source
from medradar.observatory.ledger import ObservationLedger
from medradar.observatory.records import (
    CHANGE_FETCH_FAILED,
    CHANGE_NEW,
    CHANGE_REMOVED,
    CHANGE_UNCHANGED,
    CHANGE_UPDATED,
    ENTITY_MAPPED,
    ENTITY_PENDING_REVIEW,
    ORIGIN_BACKFILLED,
    PRECISION_DATE,
    PRECISION_DATETIME,
    MappingResult,
    Page,
    RawRecord,
    Scope,
    hours_between,
)


# ----------------------------------------------------------------------- helpers
class DummyFetcher:
    """Minimal stand-in for medradar.http.Fetcher (engine only reads counters)."""

    def __init__(self, max_requests: int = 100) -> None:
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "errors": 0}
        self.max_requests = max_requests


def make_record(
    record_id: str,
    *,
    title: str = "测试记录",
    event_at: str = "2026-10-01",
    published_at: str | None = "2026-10-02T21:18:02+00:00",
    payload: dict | None = None,
    source: str = "fake",
    record_type: str = "fake_record",
) -> RawRecord:
    return RawRecord(
        source=source,
        source_record_id=record_id,
        record_type=record_type,
        title=title,
        url=f"https://example.invalid/{record_id}",
        event_at=event_at,
        event_at_precision=PRECISION_DATE if event_at else "unknown",
        published_at=published_at,
        published_at_precision=PRECISION_DATETIME if published_at else "unknown",
        payload=payload if payload is not None else {"status": "active", "title": title},
        company_hint="Medtronic",
        extra={"company_key": "medtronic"},
    )


MAPPED = MappingResult(
    entity_id="medtronic",
    entity_status=ENTITY_MAPPED,
    entity_method="test_exact",
    entity_confidence=1.0,
    track_id="cardiac_rhythm",
    track_status="MAPPED",
    track_method="test_keyword",
)


@pytest.fixture()
def ledger(tmp_path):
    store = ObservationLedger(tmp_path / "observatory.sqlite")
    yield store
    store.close()


def _collect(ledger, record, *, run_id, seen_at, mapping=MAPPED, origin="LIVE", reason=None):
    return ledger.record_observation(
        record,
        mapping,
        run_id=run_id,
        collector_version="test/1",
        mapping_version="obs-mapping-v1",
        seen_at=seen_at,
        origin=origin,
        backfill_reason=reason,
    )


# ------------------------------------------------------------- ledger guarantees
def test_first_observation_records_real_first_seen(ledger):
    record = make_record("rec-1")
    outcome = _collect(ledger, record, run_id="run-1", seen_at="2026-11-03T10:00:00+00:00")
    assert outcome.state == CHANGE_NEW
    row = ledger.observation_row(record.observation_id)
    assert row["first_seen_at"] == "2026-11-03T10:00:00+00:00"
    assert row["observation_origin"] == "LIVE"
    assert row["observation_status"] == "ACTIVE"
    assert row["version_count"] == 1
    versions = ledger.versions(record.observation_id)
    assert [version["change_state"] for version in versions] == [CHANGE_NEW]
    # published_at came from the source, not from the event date
    assert row["published_at"] == "2026-10-02T21:18:02+00:00"
    assert row["published_at_precision"] == PRECISION_DATETIME
    assert row["event_at"] == "2026-10-01" and row["event_at_precision"] == PRECISION_DATE
    # the measured lag is a real interval, not a guess
    assert hours_between(row["published_at"], row["first_seen_at"]) > 0


def test_repeat_collection_is_idempotent(ledger):
    record = make_record("rec-1")
    _collect(ledger, record, run_id="run-1", seen_at="2026-11-03T10:00:00+00:00")
    again = _collect(ledger, record, run_id="run-2", seen_at="2026-11-04T10:00:00+00:00")
    assert again.state == CHANGE_UNCHANGED
    row = ledger.observation_row(record.observation_id)
    assert row["first_seen_at"] == "2026-11-03T10:00:00+00:00"   # never overwritten
    assert row["last_checked_at"] == "2026-11-04T10:00:00+00:00"
    assert row["version_count"] == 1
    assert len(ledger.versions(record.observation_id)) == 1
    assert len(ledger.changes_for(record.observation_id)) == 1
    assert ledger.counts()["observations"] == 1


def test_revision_keeps_both_versions_and_names_changed_fields(ledger):
    first = make_record("rec-1", title="原始标题", payload={"status": "recruiting", "enrollment": 100})
    _collect(ledger, first, run_id="run-1", seen_at="2026-11-01T10:00:00+00:00")
    second = make_record("rec-1", title="修订标题", payload={"status": "completed", "enrollment": 100})
    outcome = _collect(ledger, second, run_id="run-2", seen_at="2026-11-05T10:00:00+00:00")
    assert outcome.state == CHANGE_UPDATED
    assert outcome.changed_fields == ("status",)
    versions = ledger.versions(first.observation_id)
    assert [version["version_seq"] for version in versions] == [1, 2]
    assert json.loads(versions[0]["payload"])["status"] == "recruiting"   # first version intact
    assert json.loads(versions[1]["payload"])["status"] == "completed"
    changes = ledger.changes_for(first.observation_id)
    assert [change["change_state"] for change in changes] == [CHANGE_NEW, CHANGE_UPDATED]
    row = ledger.observation_row(first.observation_id)
    assert row["first_seen_at"] == "2026-11-01T10:00:00+00:00"
    assert row["title"] == "修订标题"


def test_first_seen_at_is_immutable_at_the_sqlite_layer(ledger):
    record = make_record("rec-1")
    _collect(ledger, record, run_id="run-1", seen_at="2026-11-03T10:00:00+00:00")
    with pytest.raises(sqlite3.IntegrityError, match="first_seen_at is immutable"):
        ledger.con.execute("UPDATE observation SET first_seen_at='2000-01-01T00:00:00+00:00'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger.con.execute("UPDATE observation_version SET payload='{}'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger.con.execute("DELETE FROM observation_version")
    with pytest.raises(sqlite3.IntegrityError, match="never deleted"):
        ledger.con.execute("DELETE FROM observation")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger.con.execute("DELETE FROM observation_change")


def test_removed_is_recorded_as_its_own_state_not_inferred(ledger):
    record = make_record("rec-1")
    _collect(ledger, record, run_id="run-1", seen_at="2026-11-01T10:00:00+00:00")
    assert ledger.mark_removed(record.observation_id, run_id="run-2",
                               seen_at="2026-11-02T10:00:00+00:00",
                               note_zh="来源不再提供") is True
    row = ledger.observation_row(record.observation_id)
    assert row["observation_status"] == "REMOVED_OR_UNAVAILABLE"
    assert [c["change_state"] for c in ledger.changes_for(record.observation_id)] == [
        CHANGE_NEW, CHANGE_REMOVED,
    ]
    # a second absence is not a second removal event
    assert ledger.mark_removed(record.observation_id, run_id="run-3",
                               seen_at="2026-11-03T10:00:00+00:00",
                               note_zh="仍然不提供") is False
    # the record re-appearing is a real revision, and first_seen_at is untouched
    outcome = _collect(ledger, record, run_id="run-4", seen_at="2026-11-04T10:00:00+00:00")
    assert outcome.state == CHANGE_UPDATED
    assert outcome.changed_fields == ("status",)
    row = ledger.observation_row(record.observation_id)
    assert row["observation_status"] == "ACTIVE"
    assert row["first_seen_at"] == "2026-11-01T10:00:00+00:00"


def test_fetch_failed_is_not_a_no_change_signal(ledger):
    record = make_record("rec-1")
    _collect(ledger, record, run_id="run-1", seen_at="2026-11-01T10:00:00+00:00")
    before = ledger.observation_row(record.observation_id)
    ledger.mark_fetch_failed(record.observation_id, run_id="run-2",
                             seen_at="2026-11-02T10:00:00+00:00", message="HTTP 503")
    after = ledger.observation_row(record.observation_id)
    assert after["last_checked_at"] == before["last_checked_at"]   # no false freshness
    changes = ledger.changes_for(record.observation_id)
    assert changes[-1]["change_state"] == CHANGE_FETCH_FAILED
    assert changes[-1]["version_id"] is None
    # the payload history did not grow: a failure is not a version
    assert len(ledger.versions(record.observation_id)) == 1


def test_backfilled_data_must_say_so(ledger):
    record = make_record("rec-old")
    with pytest.raises(ValueError, match="BACKFILLED"):
        _collect(ledger, record, run_id="run-1", seen_at="2026-11-03T10:00:00+00:00",
                 origin=ORIGIN_BACKFILLED)
    outcome = _collect(ledger, record, run_id="run-1", seen_at="2026-11-03T10:00:00+00:00",
                       origin=ORIGIN_BACKFILLED, reason="导入历史归档以补齐覆盖")
    assert outcome.state == CHANGE_NEW
    row = ledger.observation_row(record.observation_id)
    assert row["observation_origin"] == "BACKFILLED"
    assert "历史归档" in row["backfill_reason"]
    counts = ledger.counts()
    assert counts["backfilled_observations"] == 1
    assert counts["live_observations"] == 0


def test_mapping_changes_append_history_instead_of_rewriting_identity(ledger):
    record = make_record("rec-1")
    pending = MappingResult(entity_id="medtronic", entity_status=ENTITY_PENDING_REVIEW,
                            entity_method="name_fuzzy", entity_confidence=0.7)
    _collect(ledger, record, run_id="run-1", seen_at="2026-11-01T10:00:00+00:00", mapping=pending)
    _collect(ledger, record, run_id="run-2", seen_at="2026-11-02T10:00:00+00:00")
    history = ledger.mapping_history(record.observation_id)
    assert [entry["entity_status"] for entry in history] == ["PENDING_REVIEW", "MAPPED"]
    # the improvement did not create a new version of the source evidence
    assert len(ledger.versions(record.observation_id)) == 1


# ------------------------------------------------------------------- point in time
def test_replay_excludes_records_discovered_after_the_cutoff(ledger):
    older_event = make_record("old-event", event_at="2026-01-15",
                              payload={"detail": "old but observed late"})
    newer_event = make_record("new-event", event_at="2026-10-25")
    _collect(ledger, newer_event, run_id="run-1", seen_at="2026-11-01T10:00:00+00:00")
    _collect(ledger, older_event, run_id="run-2", seen_at="2026-11-05T10:00:00+00:00")

    early = ledger.snapshot("2026-11-02T00:00:00+00:00")
    assert [item["source_record_id"] for item in early["items"]] == ["new-event"]
    assert early["excluded_discovered_later"] == 1

    later = ledger.snapshot("2026-11-06T00:00:00+00:00")
    assert {item["source_record_id"] for item in later["items"]} == {"new-event", "old-event"}


def test_replay_returns_the_version_that_existed_then(ledger):
    first = make_record("rec-1", title="v1", payload={"status": "recruiting"})
    _collect(ledger, first, run_id="run-1", seen_at="2026-11-01T10:00:00+00:00")
    second = make_record("rec-1", title="v2", payload={"status": "completed"})
    _collect(ledger, second, run_id="run-2", seen_at="2026-11-04T10:00:00+00:00")

    early = ledger.snapshot("2026-11-02T00:00:00+00:00")
    assert early["total"] == 1
    assert early["items"][0]["version_seq"] == 1
    assert early["items"][0]["payload"]["status"] == "recruiting"

    late = ledger.snapshot("2026-11-05T00:00:00+00:00")
    assert late["items"][0]["version_seq"] == 2
    assert late["items"][0]["payload"]["status"] == "completed"


def test_replay_as_of_before_any_observation_is_empty(ledger):
    _collect(ledger, make_record("rec-1"), run_id="run-1", seen_at="2026-11-03T10:00:00+00:00")
    snapshot = ledger.snapshot("2026-10-01T00:00:00+00:00")
    assert snapshot["total"] == 0
    assert snapshot["excluded_discovered_later"] == 1


# ------------------------------------------------------------------- consistency
def test_consistency_check_passes_on_a_clean_ledger(ledger):
    _collect(ledger, make_record("rec-1"), run_id="run-1", seen_at="2026-11-03T10:00:00+00:00")
    check = ledger.consistency_check()
    assert check["ok"] is True, check["issues"]


def test_consistency_check_catches_a_row_written_behind_its_back(ledger):
    # Simulates a corrupt/buggy write that bypasses the ledger API (raw SQL insert).
    ledger.con.execute(
        "INSERT INTO observation(observation_id, source, source_record_id, record_type,"
        " first_seen_at, ingested_at, observation_origin, last_checked_at, source_payload_hash,"
        " version_count, observation_status, current_change_state, last_change_at,"
        " first_seen_run_id, last_checked_run_id) VALUES('broken','fake','broken','fake_record',"
        "'2026-11-03T10:00:00+00:00','2026-11-03T10:00:00+00:00','LIVE',"
        "'2026-11-03T10:00:00+00:00','deadbeef',3,'ACTIVE','NEW',"
        "'2026-11-03T10:00:00+00:00','run-x','run-x')"
    )
    check = ledger.consistency_check()
    assert check["ok"] is False
    assert "version_count_mismatch" in check["issues"]
    assert "missing_mapping" in check["issues"]


def test_filtered_change_queries_bind_every_parameter(ledger):
    first = make_record("rec-1")
    second = make_record("rec-2", title="另一家企业的记录")
    other = MappingResult(entity_id="philips", entity_status=ENTITY_MAPPED,
                          entity_method="test_exact", entity_confidence=1.0)
    # `change_rows(hours=...)` is a *relative* window measured from the wall clock,
    # so this fixture must be relative too. A hard-coded 2026-11-03 timestamp made
    # the test pass only on the day it was written and fail silently later
    # (Phase 4 audit, 2026-11-04: it had already started failing). The test is about
    # parameter binding, not about dates.
    seen_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _collect(ledger, first, run_id="run-1", seen_at=seen_at)
    _collect(ledger, second, run_id="run-1", seen_at=seen_at,
             mapping=other)
    rows, total = ledger.change_rows(hours=24, states=[CHANGE_NEW], source="fake")
    assert total == 2
    rows, total = ledger.change_rows(hours=24, source="fake", entity_id="philips")
    assert total == 1 and rows[0]["source_record_id"] == "rec-2"
    rows, total = ledger.change_rows(hours=24, source="fake", track_id="cardiac_rhythm")
    assert total == 1
    rows, total = ledger.change_rows(hours=24, source="fake", query="另一家")
    assert total == 1
    facets = ledger.change_facets(hours=24, source="fake", query="另一家")
    assert facets["sources"][0]["n"] == 1


# ------------------------------------------------------------------------ engine
class FakeAdapter:
    """Deterministic adapter with pagination, optional failure and structure drift."""

    source_id = "fake"
    label_zh = "合成测试来源"
    collector_version = "fake/1.0.0"
    declared_cadence_zh = "每 6 小时轮询（合成）"
    record_type_labels = {"fake_record": "合成记录"}

    def __init__(self, pages: list[list[RawRecord]], *, fail_page: int | None = None,
                 structure: dict | None = None, known_ids: list[str] | None = None) -> None:
        self.pages = pages
        self.fail_page = fail_page
        self.structure = structure or {"keys": ["status", "title"]}
        self.known_ids = known_ids
        self.calls = 0

    def plan(self, ctx):
        return [Scope(scope_id="scope-1")]

    def fetch_page(self, ctx, scope, cursor):
        index = int(cursor) if cursor else 0
        self.calls += 1
        ctx.fetcher.stats["requests"] += 1
        if self.fail_page is not None and index == self.fail_page:
            raise TimeoutError("simulated page timeout")
        records = self.pages[index] if index < len(self.pages) else []
        next_cursor = str(index + 1) if index + 1 < len(self.pages) else None
        return Page(
            records=records,
            next_cursor=next_cursor,
            watermark={"cursor": index} if next_cursor is None else None,
            structure_sample=self.structure,
        )

    def map_record(self, record, ctx):
        return MAPPED

    def scope_known_ids(self, ctx, scope):
        return self.known_ids or []


def _engine_context(ledger, now="2026-11-03T12:00:00+00:00"):
    return CollectContext(
        fetcher=DummyFetcher(),
        ledger=ledger,
        run_id="pending",
        trigger="test",
        now=now,
        log=lambda message: None,
    )


def test_engine_paginates_commits_every_page_and_is_resumable(ledger):
    pages = [[make_record("a"), make_record("b")], [make_record("c")]]
    result = run_source(FakeAdapter(pages), _engine_context(ledger))
    assert result["status"] == "OK"
    assert result["counters"]["records_new"] == 3
    assert result["counters"]["pages"] == 2
    assert result["watermark"] == {"scope-1": {"cursor": 1}}
    assert ledger.counts()["observations"] == 3
    # re-running is idempotent
    again = run_source(FakeAdapter(pages), _engine_context(ledger), resume=False)
    assert again["counters"]["records_unchanged"] == 3
    assert ledger.counts()["observations"] == 3
    assert ledger.counts()["versions"] == 3


def test_engine_resumes_an_interrupted_run_without_duplicates(ledger):
    pages = [[make_record("a")], [make_record("b")], [make_record("c")]]
    first = run_source(FakeAdapter(pages, fail_page=1), _engine_context(ledger), resume=False)
    assert first["status"] == "PARTIAL"
    assert ledger.counts()["observations"] == 1
    # a failed page must not advance the watermark
    state = ledger.get_source_state("fake")
    assert state["status"] == "DEGRADED"
    second = run_source(FakeAdapter(pages), _engine_context(ledger), resume=True)
    assert second["resumed"] is True
    assert second["status"] == "OK"
    assert ledger.counts()["observations"] == 3
    assert ledger.counts()["changes"] == 3


def test_engine_marks_known_records_fetch_failed_when_a_scope_breaks(ledger):
    record = make_record("a")
    run_source(FakeAdapter([[record]]), _engine_context(ledger), resume=False)
    failures = run_source(
        FakeAdapter([[record]], fail_page=0, known_ids=[record.observation_id]),
        _engine_context(ledger),
        resume=False,
    )
    assert failures["status"] == "PARTIAL"
    changes = ledger.changes_for(record.observation_id)
    assert [change["change_state"] for change in changes] == [CHANGE_NEW, CHANGE_FETCH_FAILED]
    failure_rows = ledger.con.execute("SELECT * FROM source_failure").fetchall()
    assert failure_rows and failure_rows[0]["kind"] == "TIMEOUT"
    # the record itself is still present and its payload history untouched
    assert ledger.observation_row(record.observation_id)["observation_status"] == "ACTIVE"
    assert len(ledger.versions(record.observation_id)) == 1


def test_engine_detects_a_structure_change_and_flags_the_source(ledger):
    first_pages = [[make_record("a")]]
    run_source(FakeAdapter(first_pages, structure={"keys": ["status", "title"]}),
               _engine_context(ledger), resume=False)
    assert ledger.get_source_state("fake")["structure_signature"]
    shifted = run_source(
        FakeAdapter([[make_record("b")]], structure={"keys": ["state", "name"], "new": True}),
        _engine_context(ledger),
        resume=False,
    )
    assert shifted["status"] == "PARTIAL"
    assert shifted["structure"]["changed"] is True
    state = ledger.get_source_state("fake")
    assert state["structure_changed_at"]
    assert "结构指纹变化" in (state["structure_note_zh"] or "")
    kinds = [row["kind"] for row in ledger.con.execute("SELECT kind FROM source_failure").fetchall()]
    assert "STRUCTURE_CHANGE" in kinds


def test_engine_reports_counts_and_never_loses_a_page(ledger):
    pages = [[make_record("a")], [make_record("b")], [make_record("c")], [make_record("d")]]
    partial = run_source(FakeAdapter(pages, fail_page=2), _engine_context(ledger), resume=False)
    assert partial["counters"]["records_new"] == 2
    assert partial["status"] == "PARTIAL"
    resumed = run_source(FakeAdapter(pages), _engine_context(ledger), resume=True)
    assert resumed["counters"]["records_new"] == 2
    assert resumed["counters"]["records_unchanged"] == 0
    assert ledger.counts()["observations"] == 4
    # every observation has exactly one NEW change entry
    new_changes = ledger.con.execute(
        "SELECT COUNT(*) FROM observation_change WHERE change_state='NEW'"
    ).fetchone()[0]
    assert new_changes == 4
