# DATA-003 — Benchmark: method, results and reproducibility

Every number below states the tree, the snapshot, the host, the sample size and whether the
device index was warm. No number is compared across different conditions.

## 1. Test objects

| Item | Value |
|---|---|
| Snapshot | `fda-snapshot-20261116T032632Z-18ce4d0cbbe4` (91,457 events, 25,007,667 B `events.jsonl.gz`) |
| Baseline tree | `edbde0a` (DATA-002 tip, production code `bb1ef34` + docs), `D:\DEPPSKK\data003-baseline` |
| Optimised tree | branch `feat/data-003-runtime-reliability`, commit recorded in the Draft PR |
| Benchmark host | Windows 11, 16 logical CPUs, 32 GiB, Python 3.12.10 (busy: other agents were using CPUs; absolute timing is *not* production timing) |
| Production host | Ubuntu 24.04, 2 vCPU, 3.72 GiB, Python from `/srv/medradar/.venv` (read-only baseline only) |
| Data root for web runs | isolated copy of `/srv/medradar/data/fda` (pipeline.db + 6 real snapshots) |
| Snapshot switches | real prior snapshot `…031623Z-556883ca1bc7` ↔ active `…032632Z-18ce4d0cbbe4` |
| Web server | `python -m medradar.product.web --host 127.0.0.1 --port 8899 --no-reload`, one worker, device index pre-warmed |

Reproduce:

```bash
# memory states and reload
python tools/data003/memory_probe.py --data-dir <snapshot> --mode full
python tools/data003/memory_probe.py --data-dir <snapshot> --mode reload --reloads 3
# behaviour-preservation digest
python tools/data003/dataset_fingerprint.py --data-dir <snapshot> --json-out fp.json
# web availability under load + switch
python tools/data003/bench_web.py --repo-root <tree> --data-root <root> \
  --duration 30 --concurrency 2 --think-ms 100 --switch-at 6 --json-out out.json
# real pipeline reconciliation (isolated root only, never production)
python tools/data003/bench_pipeline.py --root <copy-of-fda> \
  --args "sync --sources openfda_recall --force --json" --json-out sync.json
```

## 2. A. Web baseline (single client, paced, no switch, no sync)

Optimised tree, concurrency 1, 12 s, 89 requests, 0 errors, index warm:

| Endpoint | p50 | max |
|---|---|---|
| `/api/health` | 28.3 ms | 39.0 ms |
| `/api/data-status` | 36.2 ms | 49.7 ms |
| `/api/organizations` | 3.3 ms | 5.5 ms |
| `/api/organizations/medtronic` | 75.8 ms | 85.6 ms |
| `/api/devices` | 115.6 ms | 507.2 ms |
| `/api/events?page_size=25` | 491.4 ms | 544.2 ms |
| `/api/meta` | 148.9 ms | 165.2 ms |
| `/api/compare` | 109.0 ms | 133.3 ms |
| `/` | 5.0 ms | 72.4 ms |

Whole-run p50 76 ms, p95 505 ms, max 544 ms, RSS 367 MB.

`/api/events` is the most expensive endpoint because it filters 91 k events, sorts them and
counts them. DATA-003 removed the per-request list rebuild and the per-request org-stats
recomputation; the remaining ~490 ms is the sort + counts pass in Python. It is the main source
of GIL pressure during an activation (see §6) and is the next optimisation candidate, not a
regression.

## 3. B. Dataset warm-up (isolated process)

See `MEMORY_PROFILE.md` §1. Summary: cold load 213 MB / 8.1 s; warm dataset +0.4 MB;
warm device index +122.7 MB / 5.7 s; reload coexistence +163 MB, +283 MB with a new index.

## 4. C. Snapshot switch under load (the DATA-002 failure)

Paced load: 2 clients, one request every 100 ms per client, 12-endpoint mix, 30 s, switch at 6 s,
device index warm, no pipeline running. Same load, same snapshot, same switch, both trees.

| Metric | DATA-002 baseline (`edbde0a`) | DATA-003 | Change |
|---|---|---|---|
| completed requests in 30 s | **29** | **239** | 8.2× |
| errors (harness 20 s timeout) | **2** | 0 | eliminated |
| p50 | 203 ms | 164 ms | −19 % |
| p95 | **20,009 ms** | 950 ms | −95 % |
| p99 | 20,010 ms | 2,079 ms | −90 % |
| max | **20,009 ms** | 3,333 ms | −83 % |
| requests > 1 s | 8 | 6 | — |
| `/api/health` p50 / max | 51 / 67 ms (only 2 completed) | 117 / **163 ms** | no stall |
| snapshot observed after switch | 22.8 s | 43.1 s (background) | data older for longer, service alive |

Interpretation: in DATA-002 every request that arrived during the load queued behind the
holder's global lock, so clients sat for the entire load (the harness gave up at 20 s). In
DATA-003 the activation is a background thread: the same clients completed 239 requests, health
never exceeded 163 ms, and the new snapshot became active 43 s later without any request
failure.

The activation took longer under load (43 s vs ~8 s idle) because it shares the GIL with the
CPU-bound clients. This is disclosed as the central residual limitation (`RELIABILITY.md` §4);
it is not a lock stall, and no request waits for it.

## 5. D. Background FDA synchronization with the web serving queries

Real openFDA collection against an isolated copy of the production pipeline root. Two runs:

| Run | Source | Records seen | Wall time | Pipeline peak RSS | Result |
|---|---|---|---|---|---|
| recall full reconciliation | `openfda_recall` | 29,825 | 403.2 s | **1,827.9 MB** | SUCCEEDED, validation ok, 0 changes |
| 510(k) reconciliation **while the web was under the 2-client load** | `openfda_510k` | 23,400 | 279.6 s | **1,533.2 MB** | SUCCEEDED, validation ok, 0 changes |

Web behaviour during the 510(k) run (80 s window, 2 clients, 100 ms think):

| Metric | Value |
|---|---|
| requests / errors / timeouts / 5xx | 499 / 0 / 0 / 0 |
| p50 / p95 / p99 / max | 142 / 645 / 839 / **1,056 ms** |
| `/api/health` p50 / p95 / max | 124 / 183 / **259 ms** |
| `/api/data-status` p50 / max | 49 / 416 ms |
| server RSS max | 370 MB |

Control (same web load, no sync): 495 requests, p50 126, p95 658, max 768 ms, health p50 44,
max 74 ms. The real sync added CPU/I/O contention but no stall, no timeout and no 5xx.

The pipeline peak is unchanged by DATA-003 (memory work was web-side); what changed is that the
pipeline now refuses to *start* without host headroom (§7 and `RESOURCE_GUARDS.md`).

## 6. GIL contention (measured, disclosed)

The activation thread is pure Python. Isolated probe (`tools/data003/probe_gil.py`), loading the
same snapshot while *N* CPU-bound threads run the `/api/events` work:

| Competing threads | Load time |
|---|---|
| 0 | 8.9 s |
| 1 | did not finish 91 k events within 150 s (20 k in 89 s) |
| 2 | 10 k events in 126 s |

Interpreter-level change tested: `sys.setswitchinterval(0.001)` improved the same scenario from
126 s to 74 s for the first 10 k events, but at a cost to every request, so it was **not**
adopted. This is a property of CPython's GIL under saturating CPU load, not a bug introduced by
DATA-003; it is why the activation is guarded and why `OPERATIONS.md` tracks activation
duration. On the production host (low request rate, 2 vCPU, no other CPU-bound work) the
measured idle activation is ~8 s and the benchmark's health latency stayed ≤163 ms.

## 7. E. Repeated reload

`memory_probe --mode reload --reloads 3` on the same snapshot:

| Cycle | Old tree peak | New tree peak | Old post-release | New post-release |
|---|---|---|---|---|
| 1 | 1,717.8 MB | 636.9 MB | 1,491.0 MB | 583.2 MB |
| 2 | 1,927.6 MB | 781.2 MB | 1,560.8 MB | 556.9 MB |
| 3 | 1,930.3 MB | 781.4 MB | 1,630.8 MB | 652.8 MB |

No unbounded growth: the peak is ~2× one dataset, and the post-release floor is allocator
high-water, not retained objects. The new peak (781 MB) is 60 % below the old one, which is
what makes a 4 GB host safe.

## 8. F. Fault injection

| Injection | Result |
|---|---|
| New snapshot's `snapshot.json` removed after publish | activation failed; previous dataset still served; `status=degraded`, `using_fallback=true`; retries bounded (`test_runtime_falls_back_to_previous_dataset_when_new_pointer_is_unusable`) |
| Host memory below the web guard floor | activation deferred; old data served; reasons visible; retry succeeds (`test_activation_is_deferred_under_memory_pressure_and_retried`) |
| Pipeline memory floor impossible (`--env MEDRADAR_PIPELINE_MIN_AVAILABLE_MB=999999`) | real CLI run → `DEFERRED`, peak 30.9 MB, exit 0, pointer unchanged, run row `DEFERRED` (`evidence/guard-defer.json`) |
| Three consecutive deferrals | incident recorded; `escalated=true` (`test_repeated_deferrals_escalate_to_an_incident`) |
| Pipeline operation active during a snapshot change | activation deferred with `pipeline_operation_active` (guard probes `pipeline.lock`) |
| Dataset activation in flight when the timer fires | pipeline defers with `dataset_activation_in_flight` (activation marker) |
| Rollback A→B→A | both switches activated; health followed the pointer (`test_runtime_holder_reloads_on_active_pointer_switch`, benchmark `switch_back`) |
| Pipeline validation failure | unchanged DATA-001/002 behaviour: candidate rejected, no publish, previous snapshot active (`test_pipeline.py`) |

## 9. G. No regression

* `dataset_fingerprint.py` on both trees: events, aggregates, device index and quality report
  digests are **identical** (`evidence/fingerprint-*.json`).
* Full pytest suite: pass (one pre-existing governance check requires a licence inventory
  update for the new files, which is included in the branch).
* API shape: additions only (`checks.activation`, top-level `activation`,
  `dataset_activation`, `synchronization.deferral`). No field was removed or renamed.
* Data semantics: no record removed, no evidence field dropped, no candidate promoted, no
  timestamp changed.

## 10. Honest caveats

1. Absolute web latency on this benchmark host is higher than production (other agents were
   running; `/api/events` ~0.5 s here). The baseline-vs-optimised comparison is same-host and
   same-workload; the production health latency was 18 ms.
2. The pipeline runs used this host's network and IP request budget (~482 of 900 requests), not
   the production key. They hit the real FDA endpoints.
3. The switch benchmark used real prior snapshots from the same pipeline; it did not fabricate
   data.
4. No OOM or cgroup-limit test was run on this host (Windows has no cgroups); the production
   change request includes a capped canary.
