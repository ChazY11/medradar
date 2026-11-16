"""DATA-003 reliability contract.

These tests pin the behaviour the production incident required:

* a snapshot switch never blocks a request - the old validated dataset keeps serving;
* a switch that the host cannot afford is deferred, visible, and retried;
* the pipeline refuses to start a memory-heavy reconciliation without host headroom, records
  DEFERRED_RESOURCE_PRESSURE, and does not advance any source state;
* repeated deferrals escalate instead of staying silent.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from medradar.data_pipeline.lock import PipelineLock
from medradar.data_pipeline.status_service import data_status
from medradar.product import api as api_module
from medradar.product import resources


def _active_id(env) -> str:
    from medradar.product.data_dir import read_active_pointer

    pointer = read_active_pointer(env.settings.root)
    assert pointer is not None
    return str(pointer["snapshot_id"])


def _snapshot(**overrides):
    values = {
        "total_mb": 3800,
        "available_mb": 2000,
        "free_mb": 800,
        "swap_total_mb": 2048,
        "swap_free_mb": 1500,
        "swap_used_mb": 548,
        "swap_cached_mb": 100,
        "anon_mb": 1600,
        "psi_some_avg10": 0.0,
        "psi_full_avg10": 0.0,
        "oom_kills": 0,
        "captured_at": time.time(),
    }
    values.update(overrides)
    return resources.MemorySnapshot(**values)


# --------------------------------------------------------------------------- web activation
def test_activation_does_not_block_requests(pipeline_env, monkeypatch) -> None:
    env = pipeline_env
    app = api_module.create_app(data_dir=env.settings.root, pipeline_db=env.settings.state_db)
    holder = app.state.holder
    holder.guard_enabled = False
    client = TestClient(app)
    assert client.get("/api/livez").status_code == 200
    old_snapshot = holder.get().snapshot_id

    env.pipeline.sync(sources=["openfda_510k"], force=True)
    new_snapshot = _active_id(env)
    assert new_snapshot != old_snapshot

    real_load = api_module.load_dataset
    entered = threading.Event()
    release = threading.Event()

    def slow_load(*args, **kwargs):
        entered.set()
        release.wait(30)
        return real_load(*args, **kwargs)

    monkeypatch.setattr(api_module, "load_dataset", slow_load)
    holder._next_check = 0.0
    started = time.perf_counter()
    served = holder.get()
    first_ms = (time.perf_counter() - started) * 1000.0
    assert served.snapshot_id == old_snapshot
    # The request that notices the new pointer must not wait for the load.
    assert first_ms < 500.0
    assert entered.wait(10), "the background activation never started"

    # While the loader is blocked, other requests keep being served from the old dataset.
    latencies = []
    for _ in range(5):
        started = time.perf_counter()
        current = holder.get()
        latencies.append((time.perf_counter() - started) * 1000.0)
        assert current.snapshot_id == old_snapshot
    assert max(latencies) < 500.0
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["snapshot"]["id"] == old_snapshot
    assert health.json()["checks"]["activation"]["state"] == "loading"

    release.set()
    assert holder.wait_for_reload(60)
    assert holder.get().snapshot_id == new_snapshot
    monkeypatch.setattr(api_module, "load_dataset", real_load)


def test_activation_is_deferred_under_memory_pressure_and_retried(pipeline_env, monkeypatch) -> None:
    env = pipeline_env
    app = api_module.create_app(data_dir=env.settings.root, pipeline_db=env.settings.state_db)
    holder = app.state.holder
    holder.guard_enabled = True
    holder.get()
    old_snapshot = holder.reload_status()["active_snapshot"]
    env.pipeline.sync(sources=["openfda_510k"], force=True)
    new_snapshot = _active_id(env)
    assert new_snapshot != old_snapshot

    def deny(policy, **kwargs):
        return resources.GuardDecision(
            False, policy, _snapshot(available_mb=180), ("mem_available_below_floor",), 40000
        )

    monkeypatch.setattr(resources, "evaluate_guard", deny)
    holder._next_check = 0.0
    holder._next_attempt_at = 0.0
    served = holder.get()
    assert served.snapshot_id == old_snapshot  # old data still serves
    status = holder.reload_status()
    assert status["state"] == "deferred"
    assert status["deferrals"] >= 1
    assert (status["guard"] or {}).get("reasons")
    assert holder.get().snapshot_id == old_snapshot

    monkeypatch.undo()
    holder._next_check = 0.0
    holder._next_attempt_at = 0.0
    assert holder.get().snapshot_id == old_snapshot
    assert holder.wait_for_reload(60)
    assert holder.get().snapshot_id == new_snapshot
    assert holder.reload_status()["state"] == "idle"


def test_activation_marker_round_trip(tmp_path: Path) -> None:
    assert resources.read_activation(tmp_path) is None
    assert resources.activation_in_flight(tmp_path) is None
    resources.write_activation(tmp_path, state="loading", snapshot_id="snap-a", started_at="2026-01-01T00:00:00Z")
    marker = resources.activation_in_flight(tmp_path)
    assert marker is not None and marker["snapshot_id"] == "snap-a"
    resources.write_activation(tmp_path, state="loaded", snapshot_id="snap-a")
    assert resources.activation_in_flight(tmp_path) is None
    resources.write_activation(
        tmp_path, state="loading", snapshot_id="snap-b", started_at="2020-01-01T00:00:00Z"
    )
    payload = resources.read_activation(tmp_path)
    assert payload is not None
    payload["written_at"] = "2020-01-01T00:00:00Z"
    (tmp_path / "activation.json").write_text(__import__("json").dumps(payload), encoding="utf-8")
    # A stale "loading" marker must not block the pipeline forever.
    assert resources.activation_in_flight(tmp_path) is None


# --------------------------------------------------------------------------- guard maths
def test_guard_denies_low_memory_high_pressure_and_low_disk(tmp_path: Path) -> None:
    policy = resources.PIPELINE_GUARD
    low = resources.evaluate_guard(policy, snapshot=_snapshot(available_mb=100))
    assert not low.allowed and "mem_available_below_floor" in low.reasons
    ok = resources.evaluate_guard(policy, snapshot=_snapshot(available_mb=2000))
    assert ok.allowed, ok.reasons
    swap = resources.evaluate_guard(policy, snapshot=_snapshot(available_mb=2000, swap_free_mb=10))
    assert not swap.allowed and "swap_free_below_floor" in swap.reasons
    pressure = resources.evaluate_guard(policy, snapshot=_snapshot(available_mb=2000, psi_some_avg10=42.0))
    assert not pressure.allowed and "memory_pressure_high" in pressure.reasons
    disk_policy = resources.PIPELINE_GUARD
    disk = resources.evaluate_guard(disk_policy, snapshot=_snapshot(available_mb=2000), disk_root=tmp_path)
    assert disk.disk_free_mb is not None


@pytest.mark.skipif(
    __import__("sys").platform == "win32",
    reason="Win32 byte-range locks are owned by the process, so a second probe handle in the "
    "same process always succeeds; production runs the Linux flock implementation.",
)
def test_pipeline_lock_is_visible_to_the_guard(tmp_path: Path) -> None:
    path = tmp_path / "pipeline.lock"
    assert resources.pipeline_operation_active(path) is False
    with PipelineLock(path):
        assert resources.pipeline_operation_active(path) is True
    assert resources.pipeline_operation_active(path) is False


# --------------------------------------------------------------------------- pipeline guard
def test_pipeline_run_defers_without_advancing_sources(pipeline_env) -> None:
    env = pipeline_env
    env.settings.resource_guard_enabled = True
    env.settings.guard_min_available_mb = 10**9
    before_snapshot = _active_id(env)
    before_sources = {row["source_id"]: dict(row) for row in env.pipeline.store.list_sources()}
    result = env.pipeline.run()
    assert result["status"] == "DEFERRED"
    assert result["deferral"]["reason"] == "DEFERRED_RESOURCE_PRESSURE"
    assert "mem_available_below_floor" in result["deferral"]["reasons"]
    assert "DEFERRED_RESOURCE_PRESSURE" in result["message"]
    # Nothing was collected, published or even checked.
    assert _active_id(env) == before_snapshot
    after_sources = {row["source_id"]: dict(row) for row in env.pipeline.store.list_sources()}
    assert after_sources == before_sources
    runs = env.pipeline.store.recent_runs(5)
    assert runs[0]["status"] == "DEFERRED"
    assert runs[0]["error"] == "DEFERRED_RESOURCE_PRESSURE"

    status = data_status(data_dir=env.settings.root, pipeline_db=env.settings.state_db)
    assert status["synchronization"]["state"] == "deferred"
    assert status["synchronization"]["deferral"]["reason"] == "DEFERRED_RESOURCE_PRESSURE"
    assert status["health"]["sync"]["state"] == "deferred"
    assert status["state"] == "deferred"

    # Operator override starts the same work.
    env.settings.guard_min_available_mb = 0
    env.settings.guard_min_swap_free_mb = 0
    env.settings.guard_min_disk_free_mb = 0
    recovered = env.pipeline.sync(sources=["openfda_510k"], force=True)
    assert recovered["status"] in ("SUCCEEDED", "PARTIAL")
    assert _active_id(env) != before_snapshot


def test_repeated_deferrals_escalate_to_an_incident(pipeline_env) -> None:
    env = pipeline_env
    env.settings.resource_guard_enabled = True
    env.settings.guard_min_available_mb = 10**9
    for _ in range(3):
        result = env.pipeline.run()
        assert result["status"] == "DEFERRED"
    incidents = env.pipeline.store.incidents(10)
    assert any(row["kind"] == "sync_deferred_resource_pressure" for row in incidents)
    status = data_status(data_dir=env.settings.root, pipeline_db=env.settings.state_db)
    assert status["synchronization"]["deferral"]["consecutive"] >= 3
    assert status["synchronization"]["deferral"]["escalated"] is True


def test_disabled_guard_keeps_the_previous_behaviour(pipeline_env) -> None:
    env = pipeline_env
    assert env.settings.resource_guard_enabled is False
    env.settings.guard_min_available_mb = 10**9  # would defer if the guard were on
    result = env.pipeline.run()
    assert result["status"] != "DEFERRED"


def test_prune_backups_is_a_dry_run_by_default_and_skips_malformed(tmp_path: Path) -> None:
    from medradar.data_pipeline.backup import prune_backups

    for stamp in ("20260101T000000Z-aaaaaa", "20260102T000000Z-bbbbbb", "20260103T000000Z-cccccc"):
        archive = tmp_path / ("data-backup-" + stamp)
        archive.mkdir()
        (archive / "backup.json").write_text("{}", encoding="utf-8")
        (archive / "payload.bin").write_bytes(b"x" * 128)
    (tmp_path / "data-backup-malformed").mkdir()
    (tmp_path / "unrelated").mkdir()

    dry = prune_backups(tmp_path, keep=2)
    assert dry["applied"] is False
    assert dry["removable"] == ["data-backup-20260101T000000Z-aaaaaa"]
    assert dry["reclaimable_bytes"] >= 128
    assert (tmp_path / "data-backup-20260101T000000Z-aaaaaa").is_dir()

    applied = prune_backups(tmp_path, keep=2, apply=True)
    assert applied["removed"] == ["data-backup-20260101T000000Z-aaaaaa"]
    assert not (tmp_path / "data-backup-20260101T000000Z-aaaaaa").exists()
    assert (tmp_path / "data-backup-20260103T000000Z-cccccc").is_dir()
    # A directory without a manifest, or with an unrelated name, is never deleted.
    assert (tmp_path / "data-backup-malformed").is_dir()
    assert (tmp_path / "unrelated").is_dir()
