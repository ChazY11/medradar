# DATA-003 — Reliability: failure modes, recovery and rollback

The goal is not "nothing fails"; it is "when something fails, the service keeps the last
validated snapshot and says so". Every row below is either an automated test or a measured
experiment. No production mutation was performed.

## 1. Snapshot activation state machine

```
                 pointer/fingerprint changed
        idle ───────────────────────────────► loading ──success──► idle (new dataset)
          ▲                                     │
          │                                     └──failure──► failed ──backoff──► loading
          │                                                      │
          └──────────── guard denies ──► deferred ◄──────────────┘
                                          (retry in 15 s)
```

Invariants:

1. `holder.get()` always returns a fully validated `Dataset`; there is no partially loaded
   object.
2. The new dataset is swapped by one reference assignment only after `load_dataset` **and**
   its device index have completed (Correction-1). A snapshot whose index cannot be built is
   not published: the old dataset keeps serving and the attempt is retried.
3. On failure the old dataset stays active, `degraded_error` is set, and `/api/health` reports
   `checks.data.state=degraded` with `using_fallback=true`. A failure is **retried** after the
   backoff (Correction-1); the same snapshot is attempted again, and a *new* pointer state is
   attempted immediately without waiting out the old backoff.
4. A failed activation is retried with 30/60/120/300 s backoff; a *new* pointer state resets
   the backoff immediately.
5. A deferred activation keeps the old dataset, records the guard reasons, and retries after
   15 s. It is never silent (`activation.state=deferred`, `deferrals`, `guard.reasons`).
6. A cold start with no usable snapshot returns 503 `not_ready`; liveness stays 200.

## 2. Failure scenarios and observed behaviour

| Scenario | How it is exercised | Observed |
|---|---|---|
| **New pointer points to a corrupt snapshot** (`snapshot.json` removed after publish) | `test_runtime_falls_back_to_previous_dataset_when_new_pointer_is_unusable` | old snapshot keeps serving; `activation.state=failed`; `status=degraded`; message preserved; retries bounded; no 5xx |
| **Pointer switches A → B → A (rollback)** | `test_runtime_holder_reloads_on_active_pointer_switch` + benchmark `switch_back` | each switch activates the target snapshot; health follows; no stuck state |
| **Review-ledger change while serving** | `invalidate(wait=True)` (loopback review service) | synchronous for that one caller only; public requests unaffected |
| **Transient load failure, same snapshot** | `test_transient_failure_is_retried_after_backoff_and_succeeds` | retried after the backoff and activated, no pointer change; the test fails on `b1b841b` (pre-correction) |
| **Persistent load failure** | `test_persistent_failure_does_not_retry_tightly` | 1–4 attempts in 1.6 s with a 0.5 s backoff, not one per request |
| **Pointer changes while a failure backoff is pending** | `test_pointer_change_is_attempted_immediately_despite_long_backoff` | the new snapshot is attempted immediately, not after the one-hour backoff |
| **Index build fails for a new snapshot** | `test_index_failure_does_not_publish_a_partial_dataset` | not published; old dataset (with its own index) keeps serving; failed + retried |
| **Host cannot afford a second dataset** | `test_activation_is_deferred_under_memory_pressure_and_retried`, real CLI deferral | old dataset serves; `deferred` visible; retry succeeds when headroom returns |
| **Pipeline operation running while a snapshot change arrives** | guard probes `pipeline.lock` with `flock` | activation deferred with `pipeline_operation_active`, not attempted |
| **Dataset activation in flight while the timer fires** | activation marker file (`activation.json`) | pipeline run returns `DEFERRED_RESOURCE_PRESSURE` with `dataset_activation_in_flight` |
| **Host memory/swap/PSI/disk below floor** | `test_guard_denies_low_memory_high_pressure_and_low_disk`, `test_pipeline_run_defers_without_advancing_sources` | `DEFERRED` run row; no source state advanced; active snapshot unchanged |
| **Three consecutive deferrals** | `test_repeated_deferrals_escalate_to_an_incident` | incident `sync_deferred_resource_pressure`; `deferral.escalated=true` in data-status |
| **Pipeline validation failure** | existing DATA-001/002 tests (`test_pipeline.py`) | candidate rejected; no publish; run `BLOCKED`; previous snapshot active — unchanged by DATA-003 |
| **Publication interrupted mid-write** | existing `recover_publication` on startup | staging recovered/discarded; active pointer remains the last complete snapshot — unchanged |
| **Repeated reloads (3 switches)** | `memory_probe --mode reload --reloads 3` | peak 781 MB, post-release floors 583/557/653 MB; no unbounded growth |
| **OOM** | not reproduced (would require production mutation) | production `oom_kill=0`; new peaks are 60 % lower, see `BENCHMARK.md` |
| **Activation under saturating CPU load** | benchmark with 2 unthrottled CPU-bound clients | activation slowed (43 s vs 8 s idle); requests are *not* blocked by the holder, but all threads are slowed by the GIL. Documented limitation §4 |

## 3. What the service reports while things are abnormal

`/api/health` now has an `activation` check with `state` in
`ok | loading | degraded` (deferred and failed map to degraded) and a top-level `activation`
object with `phase`, `progress`, `elapsed_s`, `pending_snapshot`, `attempts`, `deferrals`,
`guard.reasons`, `last_error`.

`/api/data-status` adds `dataset_activation` and, when the last pipeline run was deferred,
`synchronization.state="deferred"` plus `synchronization.deferral{reason, reasons, phase,
guard, consecutive, escalated, retry}`.

A deferred sync is **not** reported as success: the run ledger status is `DEFERRED`, the
dashboard shows `deferred`, and the health adapter escalates it (see `OPERATIONS.md`).
It is also not reported as a failure: `BLOCKED`/`FAILED` remain reserved for real errors.

## 4. Known limitations (honest disclosure)

1. **GIL contention.** A snapshot activation is pure-Python parsing. It runs in a background
   thread, so it never queues requests behind a lock, but it competes for the GIL. On an idle
   host it finishes in ~8 s and a health request stays at ~30 ms. Under *saturating* synthetic
   CPU load it took 43 s, and very heavy clients saw their own latency rise (the GIL was
   already the bottleneck for them). Production traffic is low; the guard also prevents a sync
   and an activation from overlapping. This is the main residual risk and the reason
   `OPERATIONS.md` tracks activation duration.
2. **Allocator high-water.** After a switch the process does not return to its cold-load RSS
   (583–653 MB vs 336 MB in the probe). It is bounded by one extra dataset, not cumulative:
   the third switch does not exceed the first peak. A restart resets it.
3. **Deferred activation latency.** If the guard keeps deferring, the site keeps serving the
   previous snapshot. `/api/data-status` shows the pending snapshot and the reason, so this is
   visible rather than silent, but the data is older than the published snapshot until headroom
   returns.
4. **Cold start is still synchronous.** The first request after a process start waits for the
   load (~8 s here). Uvicorn starts answering `/api/livez` immediately; `/api/readyz` is 503
   until the dataset exists.
5. **No cgroup test on the benchmark host.** Windows has no cgroups, so the activation's
   behaviour under a hard `MemoryMax` was validated by unit tests of the guard arithmetic, not
   by inducing an OOM. The production change request includes a capped canary run.
6. **Single-worker assumption.** The activation state lives in one process; running two Uvicorn
   workers would duplicate the dataset and this design would need a shared activation lock.

## 5. Rollback

* **Data**: every snapshot is immutable; `active.json` is replaced atomically. `pipeline
  rollback <snapshot-id>` validates the target and re-points; the web activates it like any
  other change (`test_runtime_holder_reloads_on_active_pointer_switch`, and the benchmark's
  `switch_back`).
* **Code**: the DATA-003 branch is additive on top of `edbde0a`; reverting means checking out
  the previous SHA and restarting `medradar-web`. No on-disk format changed (same snapshot
  schema, same pipeline DB schema), so a rollback does not need a data migration.
* **Guard**: if the host guard is miscalibrated, set `MEDRADAR_PIPELINE_RESOURCE_GUARD=0`
  (pipeline) or `DatasetHolder.guard_enabled = False` (web, code-level) — both documented in
  `OPERATIONS.md`.
* **Emergency**: stopping `medradar-web` and letting systemd restart it clears the allocator
  high-water; because the activation path is the only thing that grows it, this should not be
  needed for correctness.
