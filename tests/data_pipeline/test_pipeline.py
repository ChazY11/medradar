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
