from __future__ import annotations

import gzip
import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from medradar.data_pipeline.config import Settings
from medradar.data_pipeline.db import StateStore
from medradar.data_pipeline.detector import check_source
from medradar.data_pipeline.lock import PipelineLock, PipelineLocked
from medradar.data_pipeline.model import CheckStatus, SOURCES
from medradar.data_pipeline.normalize import compact_event, content_hash, normalise_510k
from medradar.data_pipeline.openfda import OpenFDAError
from medradar.data_pipeline.publisher import active_snapshot
from medradar.data_pipeline.snapshot import build_snapshot, write_jsonl_gz
from medradar.data_pipeline.validator import validate_snapshot
from medradar.product.data_dir import ActivePointerError, read_active_pointer
from medradar.product.api import create_app


def _active_id(env) -> str:
    active = active_snapshot(env.settings)
    assert active is not None
    return str(active[1]["id"])


def _event_ids(env) -> set[str]:
    active = active_snapshot(env.settings)
    assert active is not None
    with gzip.open(active[0] / "events.jsonl.gz", "rt", encoding="utf-8") as handle:
        return {json.loads(line)["event_id"] for line in handle if line.strip()}


def test_bootstrap_preserves_legacy_time_and_records(pipeline_env) -> None:
    env = pipeline_env
    active = active_snapshot(env.settings)
    assert active is not None
    manifest = active[1]
    assert manifest["schema"] == "medradar.snapshot.v2"
    assert manifest["counts"]["records"] == 2
    assert manifest["scope"]["organization_count"] == 1
    events = []
    with gzip.open(active[0] / "events.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            events.append(json.loads(line))
    assert all(event["first_observed_at"] == "2026-01-01T00:00:00Z" for event in events)
    assert all(event["record_state"] == "ACTIVE" for event in events)


def test_no_change_does_not_publish_a_snapshot(pipeline_env) -> None:
    env = pipeline_env
    first = env.pipeline.sync(sources=["openfda_510k"])
    assert first["status"] == "SUCCEEDED"
    assert first["updated"] == 0, "legacy projection fields must not be reported as 91k fake revisions"
    assert first["counts"]["changes"]["first_reconciliation"] is True
    active_after_first = _active_id(env)
    second = env.pipeline.sync(sources=["openfda_510k"])
    assert second["status"] == "NO_CHANGE"
    assert _active_id(env) == active_after_first


def test_added_record_is_published_and_visible_to_product(pipeline_env) -> None:
    env = pipeline_env
    env.pipeline.sync(sources=["openfda_510k"])
    env.raw.append({
        "k_number": "K000003", "applicant": "ACME", "decision_date": "2026-03-01",
        "device_name": "Widget C", "product_code": "ABC", "date_received": "2026-02-01",
    })
    env.fake.records = list(env.raw)
    env.fake.total = 3
    env.fake.version = "2026-11-09"
    result = env.pipeline.sync(sources=["openfda_510k"])
    assert result["status"] == "SUCCEEDED"
    assert result["added"] == 1
    assert "openfda_510k:K000003" in _event_ids(env)
    active = active_snapshot(env.settings)
    assert active is not None
    with gzip.open(active[0] / "events.jsonl.gz", "rt", encoding="utf-8") as handle:
        events = {json.loads(line)["event_id"]: json.loads(line) for line in handle if line.strip()}
    new_count = sum(1 for event in events.values() if event["first_observed_at"] > "2026-01-01T00:00:00Z")
    assert new_count == 1
    # A repeat with the same source version must not create a second ADDED row.
    before = env.pipeline.status()["change_counts"].get("ADDED", 0)
    no_change = env.pipeline.sync(sources=["openfda_510k"])
    assert no_change["status"] == "NO_CHANGE"
    assert env.pipeline.status()["change_counts"].get("ADDED", 0) == before


def test_updated_record_keeps_event_date_and_records_old_and_new_values(pipeline_env) -> None:
    env = pipeline_env
    env.pipeline.sync(sources=["openfda_510k"])
    env.raw[0]["device_name"] = "Widget A revised"
    env.raw[0]["decision_date"] = "2026-01-01"
    env.fake.records = list(env.raw)
    env.fake.version = "2026-11-10"
    result = env.pipeline.sync(sources=["openfda_510k"])
    assert result["status"] == "SUCCEEDED"
    assert result["updated"] == 1
    changes = env.pipeline.store.list_changes(change_type="UPDATED", limit=10)[0]
    assert changes
    row = changes[0]
    assert row["event_date"] == "2026-01-01"
    assert "device_name" in row["changed_fields"]
    assert row["changed_fields"]["device_name"]["previous"] == "Widget A"
    assert row["changed_fields"]["device_name"]["current"] == "Widget A revised"


def test_missing_record_is_retained_then_removed_only_with_explicit_drop_permission(pipeline_env) -> None:
    env = pipeline_env
    env.pipeline.sync(sources=["openfda_510k"])
    env.fake.records = [row for row in env.fake.records if row["k_number"] != "K000002"]
    env.fake.total = len(env.fake.records)
    env.fake.version = "2026-11-11"
    first = env.pipeline.sync(sources=["openfda_510k"], force=True, allow_degraded=True)
    assert first["status"] == "SUCCEEDED"
    assert first["missing_on_recheck"] == 1
    assert "openfda_510k:K000002" in _event_ids(env), "one missing sweep must not delete a record"
    second = env.pipeline.sync(sources=["openfda_510k"], force=True, allow_degraded=True)
    assert second["status"] == "BLOCKED", "a 33% drop must require explicit review"
    assert "openfda_510k:K000002" in _event_ids(env)
    third = env.pipeline.sync(sources=["openfda_510k"], force=True, allow_degraded=True, allow_record_drop=True)
    assert third["status"] == "SUCCEEDED"
    assert third["removed_confirmed"] == 1
    assert "openfda_510k:K000002" not in _event_ids(env)
    changes = env.pipeline.store.list_changes(change_type="REMOVED_CONFIRMED", limit=10)[0]
    assert len(changes) == 1


def test_collection_failure_keeps_the_old_active_snapshot(pipeline_env) -> None:
    env = pipeline_env
    env.pipeline.sync(sources=["openfda_510k"])
    before = _active_id(env)
    env.raw.append({
        "k_number": "K000004", "applicant": "ACME", "decision_date": "2026-04-01",
        "device_name": "Widget D", "product_code": "ABC",
    })
    env.fake.records = list(env.raw)
    env.fake.version = "2026-11-12"
    env.fake.total = len(env.raw)
    env.fake.fail_fetch = True
    from medradar.data_pipeline.collector import CollectionError

    with pytest.raises(CollectionError):
        env.pipeline.sync(sources=["openfda_510k"])
    assert _active_id(env) == before
    active = active_snapshot(env.settings)
    assert active is not None
    assert "openfda_510k:K000004" not in _event_ids(env)


def test_rollback_switches_pointer_to_verified_prior_snapshot(pipeline_env) -> None:
    env = pipeline_env
    baseline = _active_id(env)
    env.pipeline.sync(sources=["openfda_510k"])
    assert _active_id(env) != baseline
    result = env.pipeline.rollback(baseline)
    assert result["snapshot_id"] == baseline
    assert _active_id(env) == baseline
    assert env.pipeline.status()["active"]["snapshot_id"] == baseline


def test_ledger_insert_is_idempotent(pipeline_env) -> None:
    env = pipeline_env
    env.pipeline.sync(sources=["openfda_510k"])
    row = {
        "change_id": "chg_deterministic_test",
        "source_id": "openfda_510k",
        "official_record_id": "K000001",
        "event_id": "openfda_510k:K000001",
        "change_type": "ADDED",
        "detected_at": "2026-11-16T00:00:00Z",
        "previous_content_hash": None,
        "new_content_hash": "a" * 64,
        "previous_snapshot_id": None,
        "candidate_snapshot_id": "fda-snapshot-test",
        "changed_fields": {},
        "evidence": {},
        "record": {},
    }
    assert env.pipeline.store.add_changes("run_test", "fda-snapshot-test", [row]) == 1
    assert env.pipeline.store.add_changes("run_test", "fda-snapshot-test", [row]) == 0
    env.pipeline.store.publish_changes("run_test", "fda-snapshot-test", "2026-11-16T00:00:00Z")
    _items, total = env.pipeline.store.list_changes(limit=100)
    assert total == 1


def test_detector_distinguishes_no_change_update_failure_and_degraded(tmp_path: Path) -> None:
    from tests.data_pipeline.conftest import FakeOpenFDA

    store = StateStore(tmp_path / "state.db")
    fake = FakeOpenFDA([])
    fake.total = 10
    manifest = {
        "id": "snap-1",
        "sources": {
            "openfda_510k": {"official_last_updated": "2026-11-02", "official_total": 10},
        },
    }
    source = SOURCES["openfda_510k"]
    same = check_source(store, fake, source, manifest)
    assert same["status"] == CheckStatus.NO_CHANGE.value
    fake.version = "2026-11-03"
    updated = check_source(store, fake, source, manifest)
    assert updated["status"] == CheckStatus.UPDATE_AVAILABLE.value
    fake.fail_probe = True
    failed = check_source(store, fake, source, manifest)
    assert failed["status"] == CheckStatus.CHECK_FAILED.value
    check_source(store, fake, source, manifest)
    degraded = check_source(store, fake, source, manifest)
    assert degraded["status"] == CheckStatus.SOURCE_DEGRADED.value
    assert degraded["consecutive_failures"] == 3


def test_validator_rejects_corrupt_hash_duplicate_ids_and_record_drop(tmp_path: Path, pipeline_env) -> None:
    env = pipeline_env
    active = active_snapshot(env.settings)
    assert active is not None
    path, manifest, _ = active
    # Corrupt a data file without changing the manifest.
    with (path / "events.jsonl.gz").open("ab") as handle:
        handle.write(b"tamper")
    report = validate_snapshot(path, settings=env.settings, previous_dir=None)
    assert not report.ok
    assert any(error.code in ("file_hash", "file_size", "compressed_size", "file_unreadable", "events_empty") for error in report.errors)

    # Build a candidate with duplicate event IDs under two map keys.
    source_versions = {source_id: {"official_last_updated": None, "official_total": None} for source_id in ("openfda_510k", "openfda_pma", "openfda_recall")}
    record = normalise_510k({
        "k_number": "K000010", "applicant": "ACME", "decision_date": "2026-01-01",
        "device_name": "Duplicate", "product_code": "ABC",
    })
    record["content_hash"] = content_hash(record)
    record["first_observed_at"] = "2026-01-01T00:00:00Z"
    record["last_synced_at"] = "2026-01-01T00:00:00Z"
    record["source_updated_at"] = None
    record["record_state"] = "ACTIVE"
    record["missing_count"] = 0
    record["collection_scopes"] = ["acme"]
    duplicate_path, duplicate_manifest = build_snapshot(
        env.settings,
        events={"a": record, "b": dict(record)},
        classifications=[{"product_code": "ABC", "device_name": "Test", "specialty": "Test", "device_class": "2"}],
        source_versions=source_versions,
        collection_audit={"sources": {}, "classification": {}, "by_source_requests": {}, "by_source_bytes": {}},
        change_summary={"added": 2},
        scope={"organizations": {}, "scope_hash": "x", "organization_count": 1},
        previous_snapshot_id=None,
        collection_started_at="2026-01-01T00:00:00Z",
    )
    duplicate_report = validate_snapshot(duplicate_path, settings=env.settings, previous_dir=None, validate_product=False)
    assert any(error.code == "duplicate_event_id" for error in duplicate_report.errors)


def test_pointer_escape_and_lock(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ActivePointerError):
        (root / "active.json").write_text(json.dumps({
            "schema": "medradar.pipeline.active.v1",
            "snapshot_id": "x",
            "path": "../outside",
        }), encoding="utf-8")
        read_active_pointer(root)

    lock = PipelineLock(root / "lock")
    with lock:
        with pytest.raises(PipelineLocked):
            with PipelineLock(root / "lock"):
                pass


def test_api_reports_configuration_and_change_feed(pipeline_env) -> None:
    env = pipeline_env
    env.pipeline.sync(sources=["openfda_510k"])
    env.raw.append({
        "k_number": "K000020", "applicant": "ACME", "decision_date": "2026-05-01",
        "device_name": "Widget E", "product_code": "ABC",
    })
    env.fake.records = list(env.raw)
    env.fake.total = len(env.raw)
    env.fake.version = "2026-11-13"
    env.pipeline.sync(sources=["openfda_510k"])

    app = create_app(data_dir=env.settings.root, pipeline_db=env.settings.state_db)
    client = TestClient(app)
    status = client.get("/api/data-status")
    assert status.status_code == 200
    body = status.json()
    assert body["configured"] is True
    assert body["snapshot"]["id"]
    assert body["sources"]
    assert body["change_counts"].get("ADDED", 0) >= 1
    source_510k = next(row for row in body["sources"] if row["source_id"] == "openfda_510k")
    assert source_510k["status"] == "NO_CHANGE"
    assert source_510k["last_success_sync_at"]
    changes = client.get("/api/changes?type=ADDED&limit=10")
    assert changes.status_code == 200
    assert changes.json()["total"] >= 1
    assert any(item["official_record_id"] == "K000020" for item in changes.json()["items"])
    assert client.get("/data-status").status_code == 200
    assert client.get("/api/livez").json()["status"] == "alive"
    ready = client.get("/api/readyz")
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    health = client.get("/api/health")
    assert health.status_code == 200
    checks = health.json()["checks"]
    assert health.json()["status"] in ("ok", "unknown")
    assert set(health.json()["checks"]) == {"liveness", "readiness", "data", "sync", "freshness"}
    assert health.json()["checks"]["data"]["state"] == "available"


def test_api_is_explicit_when_pipeline_is_not_configured(tmp_path: Path) -> None:
    from tests.data_pipeline.conftest import make_legacy_snapshot

    legacy = make_legacy_snapshot(tmp_path / "legacy", [{
        "k_number": "K000099", "applicant": "ACME", "decision_date": "2026-01-01",
        "device_name": "No pipeline", "product_code": "ABC",
    }])
    client = TestClient(create_app(data_dir=legacy))
    body = client.get("/api/data-status").json()
    assert body["configured"] is False
    assert body["state"] == "not_configured"
    assert body["synchronization"]["last_successful_sync"] is None
    assert body["terminology"]["real_time_claim"] is False
    changes = client.get("/api/changes").json()
    assert changes["configured"] is False
    assert changes["items"] == []

def test_failed_source_is_retried_hourly_not_after_full_interval():
    from datetime import datetime, timezone, timedelta
    from medradar.data_pipeline.model import SOURCES

    source = SOURCES["openfda_510k"]
    now = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
    checked = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    assert source.is_due(checked, now, last_status="CHECK_FAILED")
    assert not source.is_due(checked, now, last_status="NO_CHANGE")

def test_legacy_rebaseline_ignores_truncation_and_kn_number_order():
    from medradar.data_pipeline.changes import _legacy_equivalent, changed_fields
    from medradar.data_pipeline.normalize import compact_event, normalise_recall

    long_action = "A" * 450
    old_raw = normalise_recall({
        "product_res_number": "Z-0001-2026",
        "res_event_number": "12345",
        "recalling_firm": "ACME",
        "event_date_initiated": "2026-01-01",
        "event_date_posted": "2026-01-02",
        "product_description": "Widget " + "B" * 400,
        "reason_for_recall": "Reason " + "C" * 500,
        "action": long_action[:299] + "…",
        "k_numbers": ["K000002", "K000001"],
        "product_code": "ABC",
    })
    new_raw = normalise_recall({
        "product_res_number": "Z-0001-2026",
        "res_event_number": "12345",
        "recalling_firm": "ACME",
        "event_date_initiated": "2026-01-01",
        "event_date_posted": "2026-01-02",
        "product_description": "Widget " + "B" * 400,
        "reason_for_recall": "Reason " + "C" * 500,
        "action": long_action,
        "k_numbers": ["K000001", "K000002"],
        "product_code": "ABC",
    })
    old = dict(old_raw)
    old["first_observed_at"] = "2026-01-01T00:00:00Z"
    old["content_hash"] = "a" * 64
    new = dict(new_raw)
    new["first_observed_at"] = "2026-01-01T00:00:00Z"
    new["content_hash"] = "b" * 64
    assert _legacy_equivalent(old, new)
    assert changed_fields(old, new, legacy_projection=True) == {}
    # But a real visible change is still detected.
    changed = dict(new)
    changed["raw"] = dict(new["raw"])
    changed["raw"]["k_numbers"] = ["K000001"]
    assert not _legacy_equivalent(old, changed)
    # The legacy display projection capped k_numbers at five; an extra official reference
    # is not a revision on the first reconciliation when the old entries are preserved.
    expanded = dict(new)
    expanded["raw"] = dict(new["raw"])
    expanded["raw"]["k_numbers"] = ["K000001", "K000002", "K000003"]
    assert _legacy_equivalent(old, expanded)
    assert "raw.k_numbers" not in changed_fields(old, expanded, legacy_projection=True)
    fields = changed_fields(old, changed, legacy_projection=True)
    assert "raw.k_numbers" in fields

def test_runtime_holder_reloads_on_active_pointer_switch(pipeline_env) -> None:
    from medradar.product.api import DatasetHolder

    env = pipeline_env
    baseline = _active_id(env)
    holder = DatasetHolder(env.settings.root)
    first = holder.get().snapshot_id
    assert first == baseline
    env.pipeline.sync(sources=["openfda_510k"])
    newer = _active_id(env)
    assert newer != baseline
    assert holder.get().snapshot_id == newer
    env.pipeline.rollback(baseline)
    assert holder.get().snapshot_id == baseline

def test_runtime_falls_back_to_previous_dataset_when_new_pointer_is_unusable(pipeline_env) -> None:
    from medradar.product.api import DatasetHolder

    env = pipeline_env
    baseline = _active_id(env)
    holder = DatasetHolder(env.settings.root)
    assert holder.get().snapshot_id == baseline
    env.pipeline.sync(sources=["openfda_510k"])
    active = active_snapshot(env.settings)
    assert active is not None
    assert active[1]["id"] != baseline
    # Break the new active snapshot after it was published, then force the holder to
    # notice the new pointer. It must keep serving the validated previous dataset.
    (active[0] / "snapshot.json").unlink()
    loaded = holder.get()
    assert loaded.snapshot_id == baseline
    assert holder.degraded_error
    state, message = holder.status()
    assert state == "degraded"
    assert message

def _set_checked_hours_ago(env, hours: int = 30) -> None:
    from datetime import datetime, timedelta, timezone
    stamp = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")
    with env.pipeline.store._conn() as connection:
        connection.execute("UPDATE sources SET last_checked_at = ?", (stamp,))


def _active_manifest(env):
    active = active_snapshot(env.settings)
    assert active is not None
    return active[1]


def test_partial_source_failure_publishes_healthy_source_and_reports_failed(multi_source_env) -> None:
    env = multi_source_env
    first = env.pipeline.run()
    assert first["status"] == "SUCCEEDED"
    assert first["sync"]["status"] == "SUCCEEDED"
    before = _active_id(env)
    env.fake.fail_sources = {"openfda_510k"}
    env.fake.versions = {"openfda_recall": "2026-11-09"}
    _set_checked_hours_ago(env)
    result = env.pipeline.run()
    assert result["status"] == "PARTIAL"
    assert "openfda_510k" in result["failed_sources"]
    assert result["sync"]["status"] == "PARTIAL"
    assert _active_id(env) != before
    manifest = _active_manifest(env)
    sources = manifest["sources"]
    assert sources["openfda_510k"]["official_last_updated"] == "2026-11-02"
    assert sources["openfda_510k"]["sync_status"] == "FAILED"
    assert sources["openfda_recall"]["official_last_updated"] == "2026-11-09"
    assert sources["openfda_recall"]["sync_status"] == "SYNCED"
    assert sources["openfda_pma"]["official_last_updated"] == "2026-11-02"
    assert manifest["source_outcomes"]["openfda_510k"]["sync_status"] == "FAILED"
    assert manifest["change_summary"]["partial"] is True
    active_after = _active_id(env)
    # The failed source must remain failed and retrying must not duplicate a change row.
    change_rows = env.pipeline.store.change_counts(active_after)
    _set_checked_hours_ago(env)
    retry = env.pipeline.run()
    assert retry["status"] in ("PARTIAL", "BLOCKED")
    assert _active_id(env) == active_after
    assert env.pipeline.store.change_counts(active_after) == change_rows


def test_multiple_sources_update_in_one_partial_snapshot(multi_source_env) -> None:
    env = multi_source_env
    env.pipeline.run()
    env.fake.versions = {"openfda_pma": "2026-11-09", "openfda_recall": "2026-11-09"}
    _set_checked_hours_ago(env)
    result = env.pipeline.run()
    assert result["status"] == "SUCCEEDED", result
    manifest = _active_manifest(env)
    assert manifest["sources"]["openfda_pma"]["official_last_updated"] == "2026-11-09"
    assert manifest["sources"]["openfda_recall"]["official_last_updated"] == "2026-11-09"
    assert manifest["sources"]["openfda_classification"]["official_last_updated"] == "2026-11-02"
    assert manifest["sources"]["openfda_pma"]["sync_status"] == "SYNCED"
    assert manifest["sources"]["openfda_recall"]["sync_status"] == "SYNCED"


def test_all_sources_failed_keeps_active_snapshot_and_is_blocked(multi_source_env) -> None:
    from medradar.data_pipeline.model import ALL_SOURCE_IDS
    env = multi_source_env
    env.pipeline.run()
    before = _active_id(env)
    env.fake.fail_sources = set(ALL_SOURCE_IDS)
    _set_checked_hours_ago(env)
    result = env.pipeline.run()
    assert result["status"] == "BLOCKED"
    assert result["sync"] is None
    assert _active_id(env) == before


def test_partial_source_recovers_without_duplicate_ledger_rows(multi_source_env) -> None:
    env = multi_source_env
    env.pipeline.run()
    env.fake.fail_sources = {"openfda_510k"}
    env.fake.versions = {"openfda_recall": "2026-11-09"}
    _set_checked_hours_ago(env)
    partial = env.pipeline.run()
    assert partial["status"] == "PARTIAL"
    # Recovery: 510(k) is healthy again and every source has a newer official version.
    env.fake.fail_sources = set()
    env.fake.versions = {
        "openfda_510k": "2026-11-09",
        "openfda_pma": "2026-11-09",
        "openfda_recall": "2026-11-09",
    }
    _set_checked_hours_ago(env)
    recovered = env.pipeline.run()
    assert recovered["status"] == "SUCCEEDED"
    manifest = _active_manifest(env)
    assert manifest["sources"]["openfda_510k"]["sync_status"] == "SYNCED"
    assert manifest["sources"]["openfda_pma"]["sync_status"] == "SYNCED"
    # Recall was already synced to 2026-11-09 by the partial run; retrying it must not
    # fabricate a second "SYNCED" attempt when there is no update.
    assert manifest["sources"]["openfda_recall"]["sync_status"] == "UNCHANGED"
    assert manifest["sources"]["openfda_510k"]["official_last_updated"] == "2026-11-09"


def test_full_reconciliation_runs_when_version_is_unchanged(multi_source_env) -> None:
    env = multi_source_env
    env.pipeline.run()
    _set_checked_hours_ago(env, hours=200)
    with env.pipeline.store._conn() as connection:
        connection.execute("UPDATE sources SET last_full_reconciliation_at = '2026-01-01T00:00:00Z' WHERE source_id = 'openfda_pma'")
    result = env.pipeline.run()
    assert result["full_reconciliation_sources"] == ["openfda_pma"]
    manifest = _active_manifest(env)
    assert manifest["sources"]["openfda_pma"]["reconciliation_mode"] == "FULL"
    assert manifest["sources"]["openfda_pma"]["last_full_reconciliation_at"]

def test_collection_failure_in_one_source_does_not_block_another(multi_source_env) -> None:
    env = multi_source_env
    env.pipeline.run()
    before = _active_id(env)
    env.fake.versions = {"openfda_510k": "2026-11-09", "openfda_recall": "2026-11-09"}
    env.fake.fail_fetch_sources = {"openfda_510k"}
    _set_checked_hours_ago(env)
    result = env.pipeline.run()
    assert result["status"] == "PARTIAL"
    assert "openfda_510k" in result["failed_sources"]
    assert result["sync"]["status"] == "PARTIAL"
    assert _active_id(env) != before
    manifest = _active_manifest(env)
    assert manifest["sources"]["openfda_510k"]["official_last_updated"] == "2026-11-02"
    assert manifest["sources"]["openfda_510k"]["sync_status"] == "FAILED"
    assert manifest["sources"]["openfda_recall"]["official_last_updated"] == "2026-11-09"
    assert manifest["sources"]["openfda_recall"]["sync_status"] == "SYNCED"

def test_health_distinguishes_liveness_readiness_and_fallback(pipeline_env) -> None:
    from medradar.data_pipeline.publisher import active_snapshot as current_active
    env = pipeline_env
    client = TestClient(create_app(data_dir=env.settings.root, pipeline_db=env.settings.state_db))
    before = client.get("/api/health")
    assert before.status_code == 200
    old_snapshot = before.json()["snapshot"]["id"]
    env.pipeline.sync(sources=["openfda_510k"], force=True)
    active = current_active(env.settings)
    assert active is not None
    (active[0] / "snapshot.json").unlink()
    health = client.get("/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "degraded"
    assert body["checks"]["readiness"]["state"] == "ok"
    assert body["checks"]["data"]["using_fallback"] is True
    assert body["snapshot"]["id"] == old_snapshot
    # Liveness never depends on the data file; readiness still serves the old dataset.
    assert client.get("/api/livez").status_code == 200
    assert client.get("/api/readyz").status_code == 200


def test_health_is_503_when_no_dataset_can_be_loaded(tmp_path: Path) -> None:
    client = TestClient(create_app(data_dir=tmp_path / "missing"))
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["readiness"]["state"] == "not_ready"
    assert client.get("/api/livez").status_code == 200
    assert client.get("/api/readyz").status_code == 503

def test_backup_and_isolated_restore_preserve_ledger_and_active_snapshot(pipeline_env) -> None:
    from medradar.data_pipeline.backup import backup, restore
    from medradar.data_pipeline.publisher import active_snapshot as current_active
    from medradar.product.dataset import load_dataset

    env = pipeline_env
    env.pipeline.sync(sources=["openfda_510k"])
    env.pipeline.sync(sources=["openfda_510k"], force=True)
    active = current_active(env.settings)
    assert active is not None
    active_id = str(active[1]["id"])
    expected_changes = env.pipeline.store.change_counts(active_id)
    result = backup(env.settings, env.tmp_path / "backups")
    archive = Path(result["backup"])
    assert (archive / "backup.json").is_file()
    assert (archive / "pipeline.db").is_file()
    restored_root = env.tmp_path / "restored"
    restored = restore(archive, restored_root)
    assert restored["active_snapshot_id"] == active_id
    restored_active = current_active(Settings(root=restored_root))
    assert restored_active is not None
    assert str(restored_active[1]["id"]) == active_id
    restored_store = StateStore(restored_root / "pipeline.db")
    assert restored_store.change_counts(active_id) == expected_changes
    dataset = load_dataset(restored_root, review_db=None)
    assert dataset.snapshot_ref()["id"] == active_id
    assert len(dataset.events) > 0


def test_restore_refuses_non_empty_destination(pipeline_env) -> None:
    from medradar.data_pipeline.backup import BackupError, backup, restore

    env = pipeline_env
    result = backup(env.settings, env.tmp_path / "backups")
    victim = env.tmp_path / "occupied"
    victim.mkdir()
    (victim / "do-not-overwrite").write_text("x", encoding="utf-8")
    with pytest.raises(BackupError):
        restore(result["backup"], victim)
    assert (victim / "do-not-overwrite").read_text(encoding="utf-8") == "x"

def test_health_reports_ok_only_when_all_layers_are_known_good(multi_source_env) -> None:
    env = multi_source_env
    env.pipeline.run()
    client = TestClient(create_app(data_dir=env.settings.root, pipeline_db=env.settings.state_db))
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["checks"]["data"]["state"] == "available"
    assert body["checks"]["sync"]["state"] == "ok"
    assert body["checks"]["freshness"]["state"] == "current"

def test_default_one_product_source_per_run_leaves_other_updates_pending(multi_source_env) -> None:
    env = multi_source_env
    env.settings.max_product_sources_per_run = 1
    env.pipeline.settings.max_product_sources_per_run = 1
    result = env.pipeline.run()
    assert result["status"] == "PARTIAL"
    assert result["deferred_update_sources"]
    manifest = _active_manifest(env)
    assert manifest["change_summary"]["deferred_sources"]
    assert manifest["change_summary"]["partial"] is True
    assert manifest["sources"]["openfda_510k"]["sync_status"] == "SYNCED"
    assert manifest["sources"]["openfda_pma"]["official_last_updated"] is None
    assert manifest["sources"]["openfda_recall"]["official_last_updated"] is None
    # The unselected sources are still pending, not falsely marked as unchanged/synced.
    rows = {row["source_id"]: row for row in env.pipeline.store.list_sources()}
    assert rows["openfda_pma"]["update_available"] == 1
    assert rows["openfda_recall"]["update_available"] == 1
