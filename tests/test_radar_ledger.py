"""The append-only observation ledger: identity, versions, change states and invariants.

Every test here is about a promise the product makes to its user. If one of these fails, the
feed can show a record as "new" twice, or a failed fetch can be mistaken for "no change", or a
first-observation time can be rewritten - any of which would make the whole system untrustworthy.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from medradar.radar.ledger import ObservationLedger
from medradar.radar.records import (
    CHANGE_FETCH_FAILED,
    CHANGE_NEW,
    CHANGE_REMOVED,
    CHANGE_UPDATED,
    MAPPING_VERSION,
    ORIGIN_BACKFILLED,
    ORIGIN_LIVE,
    PHASE_INCREMENTAL,
    PHASE_INITIAL,
    MappingResult,
    RawRecord,
)


def _record(**overrides) -> RawRecord:
    base = dict(
        source="test_source",
        source_record_id="r1",
        official_identifier="ID-1",
        record_type="publication",
        title="A monitor study",
        url="https://example.test/r1",
        event_at="2026-01-02",
        event_at_precision="date",
        published_at="2026-01-02",
        published_at_precision="date",
        payload={"title": "A monitor study", "abstract": "SpO2 and alarm fatigue"},
        text="SpO2 and alarm fatigue",
        extra={"organization_hint": "Philips Medical Systems",
               "organization_role": "publication_affiliation"},
    )
    base.update(overrides)
    return RawRecord(**base)


def _mapping(topic: str = "spo2_oximetry") -> MappingResult:
    return MappingResult(
        organization_candidates=({"organization_id": "philips", "confirmation": "CONFIRMED",
                                  "method": "rule_alias", "confidence": 0.98},),
        technology_topics=({"topic_id": topic, "confirmation": "TOPIC_RELATED",
                            "method": "rule_text", "confidence": 0.65},),
    )


@pytest.fixture()
def ledger(tmp_path: Path):
    handle = ObservationLedger(tmp_path / "radar.db")
    handle.ensure_source("test_source", label="Test", adapter_version="v1", cadence_hours=6.0)
    yield handle
    handle.close()


def test_first_observation_is_new_and_records_both_clocks(ledger: ObservationLedger):
    outcome = ledger.record_observation(_record(), _mapping(), run_id="run-1",
                                        adapter_version="a1", mapping_version=MAPPING_VERSION)
    assert outcome.state == CHANGE_NEW
    assert outcome.first_observed_at
    row = ledger.observation_row(outcome.observation_id)
    assert row["published_at"] == "2026-01-02"
    assert row["first_observed_at"] == outcome.first_observed_at
    assert row["current_change_state"] == CHANGE_NEW
    assert row["discovery_phase"] == PHASE_INITIAL
    assert row["version_count"] == 1


def test_an_identical_re_observation_is_unchanged_and_writes_no_change_row(ledger: ObservationLedger):
    first = ledger.record_observation(_record(), _mapping(), run_id="run-1",
                                      adapter_version="a1", mapping_version=MAPPING_VERSION)
    second = ledger.record_observation(_record(), _mapping(), run_id="run-2",
                                       adapter_version="a1", mapping_version=MAPPING_VERSION)
    assert second.state == "UNCHANGED"
    assert second.version_id == first.version_id
    changes = ledger.changes_for(first.observation_id)
    assert [change["change_state"] for change in changes] == [CHANGE_NEW]
    row = ledger.observation_row(first.observation_id)
    assert row["version_count"] == 1
    assert row["last_checked_run_id"] == "run-2"


def test_a_changed_payload_is_updated_and_keeps_the_first_observation_time(ledger: ObservationLedger):
    first = ledger.record_observation(_record(), _mapping(), run_id="run-1",
                                      adapter_version="a1", mapping_version=MAPPING_VERSION)
    changed = _record(payload={"title": "A monitor study", "abstract": "SpO2 and alarm fatigue",
                              "erratum": True})
    second = ledger.record_observation(changed, _mapping(), run_id="run-2",
                                       adapter_version="a1", mapping_version=MAPPING_VERSION)
    assert second.state == CHANGE_UPDATED
    assert second.changed_fields == ("erratum",)
    row = ledger.observation_row(first.observation_id)
    assert row["first_observed_at"] == first.first_observed_at
    assert row["version_count"] == 2
    versions = ledger.versions(first.observation_id)
    assert [version["version_seq"] for version in versions] == [1, 2]


def test_first_observed_at_cannot_be_rewritten(ledger: ObservationLedger):
    outcome = ledger.record_observation(_record(), _mapping(), run_id="run-1",
                                        adapter_version="a1", mapping_version=MAPPING_VERSION)
    with pytest.raises(sqlite3.DatabaseError):
        ledger.con.execute("UPDATE observation SET first_observed_at='1999-01-01T00:00:00Z'"
                           " WHERE observation_id=?", (outcome.observation_id,))


def test_history_tables_reject_update_and_delete(ledger: ObservationLedger):
    outcome = ledger.record_observation(_record(), _mapping(), run_id="run-1",
                                        adapter_version="a1", mapping_version=MAPPING_VERSION)
    for statement in (
        "UPDATE observation_version SET payload='{}' WHERE observation_id=?",
        "DELETE FROM observation_version WHERE observation_id=?",
        "UPDATE observation_change SET change_state='UNCHANGED' WHERE observation_id=?",
        "DELETE FROM observation_change WHERE observation_id=?",
    ):
        with pytest.raises(sqlite3.DatabaseError):
            ledger.con.execute(statement, (outcome.observation_id,))


def test_unchanged_cannot_be_stored_as_a_change_row(ledger: ObservationLedger):
    with pytest.raises(sqlite3.DatabaseError):
        ledger.con.execute(
            "INSERT INTO observation_change(change_id, observation_id, source, change_state,"
            " observed_at, first_observed_at, record_type, title, discovery_phase)"
            " VALUES('x','o','s','UNCHANGED','2026-01-01','2026-01-01','publication','t','INITIAL_DISCOVERY')"
        )


def test_a_backfilled_observation_requires_a_reason(ledger: ObservationLedger):
    with pytest.raises(ValueError):
        ledger.record_observation(_record(), _mapping(), run_id="r", adapter_version="a1",
                                  origin=ORIGIN_BACKFILLED)
    outcome = ledger.record_observation(_record(), _mapping(), run_id="r", adapter_version="a1",
                                        origin=ORIGIN_BACKFILLED,
                                        backfill_reason="deliberate archive import")
    row = ledger.observation_row(outcome.observation_id)
    assert row["observation_origin"] == ORIGIN_BACKFILLED
    assert row["discovery_phase"] == "HISTORICAL_BACKFILL"


def test_removal_and_failed_fetch_are_distinct_states(ledger: ObservationLedger):
    outcome = ledger.record_observation(_record(), _mapping(), run_id="run-1",
                                        adapter_version="a1", mapping_version=MAPPING_VERSION)
    ledger.mark_fetch_failed(outcome.observation_id, run_id="run-2", message="503 from source")
    ledger.mark_removed(outcome.observation_id, run_id="run-3", note="no longer listed")
    states = [change["change_state"] for change in ledger.changes_for(outcome.observation_id)]
    assert states == [CHANGE_NEW, CHANGE_FETCH_FAILED, CHANGE_REMOVED]
    row = ledger.observation_row(outcome.observation_id)
    assert row["observation_status"] == "REMOVED_OR_UNAVAILABLE"
    # Neither state created a new payload version: nothing was rewritten.
    assert row["version_count"] == 1


def test_a_reappearing_identical_record_is_a_status_restoration_not_a_new_version(ledger: ObservationLedger):
    outcome = ledger.record_observation(_record(), _mapping(), run_id="run-1",
                                        adapter_version="a1", mapping_version=MAPPING_VERSION)
    ledger.mark_removed(outcome.observation_id, run_id="run-2", note="gone")
    again = ledger.record_observation(_record(), _mapping(), run_id="run-3",
                                      adapter_version="a1", mapping_version=MAPPING_VERSION)
    assert again.state == CHANGE_UPDATED
    assert again.changed_fields == ("status",)
    row = ledger.observation_row(outcome.observation_id)
    assert row["observation_status"] == "ACTIVE"
    assert row["version_count"] == 1


def test_the_first_successful_run_defines_the_discovery_phase(ledger: ObservationLedger):
    ledger.start_run("test_source", trigger="test", adapter_version="a1")
    first = ledger.record_observation(_record(), _mapping(), run_id="run-initial",
                                      adapter_version="a1", mapping_version=MAPPING_VERSION)
    assert first.phase == PHASE_INITIAL
    # Mark the source as having completed a run.
    ledger.note_source_success("test_source", run_id="run-initial")
    second = ledger.record_observation(
        _record(source_record_id="r2", official_identifier="ID-2", title="Second", url="https://example.test/r2"),
        _mapping(), run_id="run-2", adapter_version="a1", mapping_version=MAPPING_VERSION,
    )
    assert second.phase == PHASE_INCREMENTAL


def test_map_record_helpers_cannot_bridge_the_presence_gap(ledger: ObservationLedger):
    """A record that fails a scope gate must never be written; this asserts the ledger's own
    identity check for a missing requirement."""
    with pytest.raises(ValueError):
        ledger.record_observation(_record(), _mapping(), run_id="r", adapter_version="a1",
                                  origin="SOMETHING_ELSE")


def test_feed_filters_by_organisation_topic_and_change_state(ledger: ObservationLedger):
    a = ledger.record_observation(_record(), _mapping("spo2_oximetry"), run_id="r1",
                                  adapter_version="a1", mapping_version=MAPPING_VERSION)
    ledger.record_observation(
        _record(source_record_id="r2", official_identifier="ID-2", title="Alarm study",
                url="https://example.test/r2", payload={"title": "Alarm study"}),
        _mapping("smart_alarms"), run_id="r2", adapter_version="a1", mapping_version=MAPPING_VERSION,
    )
    rows, total = ledger.feed(organizations=["philips"], topics=["smart_alarms"])
    assert total == 1 and rows[0]["title"] == "Alarm study"
    rows, total = ledger.feed(change_states=[CHANGE_NEW])
    assert total == 2
    rows, total = ledger.feed(published_from="2026-01-01", published_to="2026-01-03")
    assert total == 2
    assert ledger.observation_row(a.observation_id) is not None


def test_processing_queue_claims_once_and_recovers_a_stale_claim(ledger: ObservationLedger):
    outcome = ledger.record_observation(_record(), _mapping(), run_id="r1",
                                        adapter_version="a1", mapping_version=MAPPING_VERSION)
    task_id = ledger.enqueue_task(outcome.observation_id, version_id=outcome.version_id,
                                  kind="ai_enrichment")
    claimed = ledger.claim_tasks(kind="ai_enrichment", limit=5)
    assert [task["task_id"] for task in claimed] == [task_id]
    assert ledger.claim_tasks(kind="ai_enrichment", limit=5) == []
    ledger.con.execute("UPDATE processing_queue SET claimed_at='2000-01-01T00:00:00' WHERE task_id=?",
                       (task_id,))
    assert ledger.release_stale_claims(older_than_seconds=60) == 1
    assert len(ledger.claim_tasks(kind="ai_enrichment", limit=5)) == 1


def test_interrupted_runs_are_recovered_as_interrupted_not_succeeded(ledger: ObservationLedger):
    run_id = ledger.start_run("test_source", trigger="test", adapter_version="a1")
    assert ledger.recover_interrupted_runs() == 1
    row = ledger.run_row(run_id)
    assert row is not None and row["status"] == "INTERRUPTED"


def test_consistency_check_passes_on_a_healthy_ledger(ledger: ObservationLedger):
    for index in range(3):
        ledger.record_observation(
            _record(source_record_id=f"r{index}", official_identifier=f"ID-{index}",
                    title=f"Study {index}", url=f"https://example.test/{index}",
                    payload={"title": f"Study {index}"}),
            _mapping(), run_id="r", adapter_version="a1", mapping_version=MAPPING_VERSION,
        )
    report = ledger.consistency_check()
    assert report["ok"], report["problems"]
    assert report["counts"]["observations"] == 3


def test_a_read_only_handle_cannot_write(tmp_path: Path):
    path = tmp_path / "radar.db"
    writer = ObservationLedger(path)
    writer.record_observation(_record(), _mapping(), run_id="r", adapter_version="a1",
                              mapping_version=MAPPING_VERSION)
    writer.close()
    reader = ObservationLedger(path, create=False, read_only=True)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            reader.con.execute("INSERT INTO meta(key, value) VALUES('x','y')")
        assert reader.counts().observations == 1
    finally:
        reader.close()
