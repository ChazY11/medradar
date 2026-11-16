"""DATA-003 Correction-1: activation retry, bounded backoff and publication consistency.

These tests pin the four behaviours a failed background activation must have:

* a transient failure of the *same* snapshot is retried automatically after the backoff and can
  succeed without any pointer change (the DATA-003 pre-correction bug returned early and never
  retried);
* a persistent failure is retried at the backoff cadence, never in a tight loop;
* a *new* pointer state is attempted immediately, without inheriting the old backoff;
* the previous dataset stays readable throughout, and no request waits for the loader.

They also pin the Correction-1 consistency rule: a snapshot is only swapped in after its device
index has been built, so `/api/devices` never serves a dataset whose index is not ready.
"""
from __future__ import annotations

import threading
import time

import pytest

from medradar.product import api as api_module


def _holder(env):
    holder = api_module.DatasetHolder(env.settings.root)
    holder.guard_enabled = False
    holder.FINGERPRINT_INTERVAL = 0.01
    holder.RETRY_DELAYS = (0.2, 0.2, 0.2)
    return holder


def _active_id(env) -> str:
    from medradar.product.data_dir import read_active_pointer

    pointer = read_active_pointer(env.settings.root)
    assert pointer is not None
    return str(pointer["snapshot_id"])


def _publish_new_snapshot(env) -> str:
    env.pipeline.sync(sources=["openfda_510k"], force=True)
    return _active_id(env)


def test_transient_failure_is_retried_after_backoff_and_succeeds(pipeline_env, monkeypatch) -> None:
    env = pipeline_env
    holder = _holder(env)
    old_snapshot = holder.get().snapshot_id
    new_snapshot = _publish_new_snapshot(env)
    assert new_snapshot != old_snapshot

    real_load = api_module.load_dataset
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated corrupt snapshot")
        return real_load(*args, **kwargs)

    monkeypatch.setattr(api_module, "load_dataset", flaky)
    holder.poll_once()
    assert holder.wait_for_reload(30)
    status = holder.reload_status()
    assert status["state"] == "failed"
    assert status["attempts"] == 1
    assert "simulated corrupt snapshot" in (status["last_error"] or "")
    assert holder.get().snapshot_id == old_snapshot  # old data still serves
    assert calls["n"] == 1

    # No pointer change. Wait out the (shortened) backoff; the next poll must retry the same
    # snapshot and, because the loader now works, activate it.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and calls["n"] < 2:
        holder.poll_once()
        time.sleep(0.02)
    assert calls["n"] >= 2, "the same snapshot was never retried"
    assert holder.wait_for_reload(30)
    assert holder.get().snapshot_id == new_snapshot
    assert holder.reload_status()["state"] == "idle"


def test_persistent_failure_does_not_retry_tightly(pipeline_env, monkeypatch) -> None:
    env = pipeline_env
    holder = _holder(env)
    holder.RETRY_DELAYS = (0.5, 0.5, 0.5)
    old_snapshot = holder.get().snapshot_id
    _publish_new_snapshot(env)

    calls = {"n": 0}

    def always_fail(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("still broken")

    monkeypatch.setattr(api_module, "load_dataset", always_fail)
    started = time.monotonic()
    while time.monotonic() - started < 1.6:
        holder.poll_once()
        time.sleep(0.02)
    # ~80 polls in 1.6 s with a 0.5 s backoff must produce only a handful of loads.
    assert 1 <= calls["n"] <= 4, "retry loop is not bounded by the backoff: %d attempts" % calls["n"]
    assert holder.reload_status()["state"] == "failed"
    assert holder.get().snapshot_id == old_snapshot


def test_pointer_change_is_attempted_immediately_despite_long_backoff(pipeline_env, monkeypatch) -> None:
    env = pipeline_env
    holder = _holder(env)
    holder.RETRY_DELAYS = (3600.0,)  # a failure would otherwise postpone retries for an hour
    old_snapshot = holder.get().snapshot_id
    broken_snapshot = _publish_new_snapshot(env)

    real_load = api_module.load_dataset
    state = {"broken": True, "calls": 0}

    def maybe_fail(*args, **kwargs):
        state["calls"] += 1
        if state["broken"]:
            raise RuntimeError("broken snapshot")
        return real_load(*args, **kwargs)

    monkeypatch.setattr(api_module, "load_dataset", maybe_fail)
    holder.poll_once()
    assert holder.wait_for_reload(30)
    assert holder.reload_status()["state"] == "failed"
    assert holder.reload_status()["next_attempt_in_s"] > 1000

    # A rollback points the active pointer at the previous, valid snapshot. That is a *different*
    # pointer state, so it must be attempted immediately, not after the one-hour backoff.
    state["broken"] = False
    env.pipeline.rollback(old_snapshot)
    started = time.monotonic()
    holder.poll_once()
    assert holder.wait_for_reload(30)
    elapsed = time.monotonic() - started
    assert elapsed < 5.0, "a new pointer state waited for the old backoff (%.2fs)" % elapsed
    assert holder.get().snapshot_id == old_snapshot
    assert state["calls"] >= 2
    assert broken_snapshot != old_snapshot


def test_old_dataset_stays_readable_during_a_failing_activation(pipeline_env, monkeypatch) -> None:
    env = pipeline_env
    holder = _holder(env)
    old_snapshot = holder.get().snapshot_id
    _publish_new_snapshot(env)

    entered = threading.Event()
    release = threading.Event()

    def slow_failure(*args, **kwargs):
        entered.set()
        release.wait(10)
        raise RuntimeError("cannot load the new snapshot")

    monkeypatch.setattr(api_module, "load_dataset", slow_failure)
    holder.poll_once()
    assert entered.wait(10), "the activation never started"

    # While the loader is stuck, foreground reads return the old dataset and never wait on the
    # loader. This is the Correction-1 version of "no request waits for the load lock".
    latencies = []
    for _ in range(10):
        started = time.monotonic()
        current = holder.get()
        latencies.append((time.monotonic() - started) * 1000.0)
        assert current.snapshot_id == old_snapshot
    assert max(latencies) < 200.0, "a foreground read waited for the loader: %.1fms" % max(latencies)

    release.set()
    assert holder.wait_for_reload(30)
    assert holder.reload_status()["state"] == "failed"
    assert holder.get().snapshot_id == old_snapshot
    status, message = holder.status()
    assert status == "degraded"
    assert message


def test_activation_publishes_the_dataset_with_its_index_already_built(pipeline_env, monkeypatch) -> None:
    env = pipeline_env
    holder = _holder(env)
    old_snapshot = holder.get().snapshot_id
    new_snapshot = _publish_new_snapshot(env)

    from medradar.product import device as device_package

    real_build = device_package.build_index
    seen: list[tuple[str, str]] = []

    def spy(dataset):
        # Record which dataset is being indexed and which dataset is still active at that moment.
        seen.append((dataset.snapshot_id, holder.get().snapshot_id))
        return real_build(dataset)

    monkeypatch.setattr(device_package, "build_index", spy)
    holder.poll_once()
    assert holder.wait_for_reload(30)

    assert seen, "the device index was not built during activation"
    indexed_snapshot, active_at_build = seen[-1]
    assert indexed_snapshot == new_snapshot
    # The index of the new snapshot is built while the *old* dataset still serves, so the swap
    # publishes a complete dataset and never exposes a half-ready index.
    assert active_at_build == old_snapshot
    active = holder.get()
    assert active.snapshot_id == new_snapshot
    assert active._device_index is not None
    assert active.device_index().snapshot_id == new_snapshot
    assert holder.reload_status()["index_ready"] is True


def test_index_failure_does_not_publish_a_partial_dataset(pipeline_env, monkeypatch) -> None:
    env = pipeline_env
    holder = _holder(env)
    old_snapshot = holder.get().snapshot_id
    _publish_new_snapshot(env)

    from medradar.product import device as device_package

    def broken_index(dataset):
        raise RuntimeError("index build failed")

    monkeypatch.setattr(device_package, "build_index", broken_index)
    holder.poll_once()
    assert holder.wait_for_reload(30)
    status = holder.reload_status()
    assert status["state"] == "failed"
    assert "index build failed" in (status["last_error"] or "")
    assert holder.get().snapshot_id == old_snapshot
    assert holder.get()._device_index is not None  # the old dataset keeps its own index


def test_foreground_requests_do_not_wait_for_a_slow_loader(pipeline_env, monkeypatch) -> None:
    env = pipeline_env
    holder = _holder(env)
    holder.get()
    _publish_new_snapshot(env)

    entered = threading.Event()
    release = threading.Event()

    def slow_load(*args, **kwargs):
        entered.set()
        release.wait(10)
        raise RuntimeError("slow failure")

    monkeypatch.setattr(api_module, "load_dataset", slow_load)
    holder.poll_once()
    assert entered.wait(10)

    # Two foreground threads read concurrently while the loader is blocked.
    latencies: list[float] = []
    lock = threading.Lock()

    def reader():
        for _ in range(5):
            started = time.monotonic()
            holder.get()
            with lock:
                latencies.append((time.monotonic() - started) * 1000.0)

    threads = [threading.Thread(target=reader) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    release.set()
    assert holder.wait_for_reload(30)
    assert latencies
    assert max(latencies) < 200.0, "foreground reads waited on the loader: %.1fms" % max(latencies)
