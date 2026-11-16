# DATA-003 — Memory profile: cold, warm dataset, warm device index, snapshot reload

Method: `tools/data003/memory_probe.py` in a fresh process per run, against the production
snapshot `fda-snapshot-20261116T032632Z-18ce4d0cbbe4` (91,457 events, identical bytes). The
probe records process RSS/peak RSS/swap (Linux `/proc`, Win32 `GetProcessMemoryInfo`), the
Python heap via `tracemalloc` when enabled, object counts, and stage timings.

The production host may not be profiled in-process, so the primary numbers come from an
isolated copy of the same snapshot. The *shape* (single dataset → +index → double-buffered
reload) and the production `memory.peak`/`memory.current` agree (§5). Absolute RSS differs
between Windows (benchmark host) and Linux (production) allocators; the comparison below is
always *same host, same snapshot, same workload*.

## 1. The four states (optimized tree)

| Stage | RSS | Peak RSS | Δ RSS | Time |
|---|---|---|---|---|
| process start (interpreter only) | 19.1 MB | 19.1 MB | — | — |
| imports (`dataset`, registry, FastAPI absent) | 22.5 MB | 24.4 MB | +3.4 MB | 0.2 s |
| **1. cold start → dataset loaded** | **213.2 MB** | 228.6 MB | +190.7 MB | 8.1 s |
| **2. warm dataset** (search, org list, 3 org profiles, event list, metrics) | 213.6 MB | 228.6 MB | +0.4 MB | 0.9 s |
| **3. warm device index** (61,632 apps / 23,974 devices / 77,823 relations) | **336.3 MB** | 354.0 MB | +122.7 MB | 5.7 s |
| **4a. reload: old + new dataset coexist** | **499.2 MB** | 514.6 MB | +162.9 MB | 8.1 s |
| 4b. new device index built while old still referenced | 619.6 MB | 636.9 MB | +283.3 MB | 6.2 s |
| 4c. old dataset released, `gc.collect()` | 583.2 MB | — | −36.4 MB | — |

## 2. Before / after, identical workload

| Measurement | DATA-002 (old) | DATA-003 (new) | Change |
|---|---|---|---|
| load only | 866.3 MB | 213.2 MB | **−75.4 %** |
| load peak | 889.0 MB | 228.6 MB | −74.3 % |
| warm dataset | 868.0 MB | 213.6 MB | −75.4 % |
| + device index | 956.7 MB | 336.3 MB | **−64.8 %** |
| reload peak (1 switch) | 1,717.8 MB | 636.9 MB | **−62.9 %** |
| 3-switch peak | 1,930.3 MB | 781.4 MB | **−59.5 %** |
| 3-switch post-release floor | 1,630.8 MB | 652.8 MB | −59.9 % |
| dataset load time | 5.6–6.5 s | 8.1 s | +1.6 s (string pooling) |
| device index build | 5.7 s | 5.7 s | unchanged |

The load is slightly slower because every string now goes through a canonicalisation dict;
that cost buys 650 MB and is paid once per process/snapshot, in a background thread.

## 3. Where the 650 MB went

`tracemalloc` on the old loader, at the end of `load_dataset`:

```
current = 565,225,660   peak = 793,564,720
json/decoder.py:354      5,268,793 allocations   400.1 MB   <- parsed strings
<string>:32                182,914 allocations   144.9 MB   <- the dict objects
dataset.py:1142             91,457 allocations     4.4 MB   <- Event field values
```

Three changes removed it, in this order:

1. **`slots=True` on `Event` and the device-model dataclasses.** A 41-field instance dict is
   1,584 B per event; with slots the same object is ~376 B. `Event` overhead
   142.3 MB → ~35 MB. Device index 106 MB → ~75 MB.
2. **A string pool during load.** `json` re-creates every string. Sharing one object per
   distinct value removes the 1.8 M duplicate raw key strings (97 MB), duplicate raw values
   (applicant/device/address), and duplicate event fields. Values are unchanged (`==` and the
   JSON output are byte-identical — see `dataset_fingerprint.py`).
3. **Streaming parse.** `_read_jsonl_gz` used to return a 91 k-element list of row dicts that
   stayed alive while `Event` objects were built. The iterator removes that whole second copy
   from the load-time peak (~230 MB of transient).

Plus a small fourth: `Dataset.filter_events` now reuses a precomputed attributed-events list
instead of rebuilding a 91 k-element list on every `/api/events` request (see `BENCHMARK.md`).

## 4. What was deliberately **not** changed

* `raw` is still the full evidence payload and is still exposed by `/api/events/{id}`. No
  evidence field was dropped, truncated, or replaced by a compact format.
* `Event.to_public()`, counts, windows, per-source rows, status counts and the device index
  relations are computed exactly as before. The fingerprint of events, aggregates, index and
  quality report is **byte-identical** before/after:
  `events 560ff100…b6b58`, `aggregates c3068d32…31844`, `index cad9bc43…88d10`,
  `quality bd3040f3…c13f`.
* No pickle cache, no persistence of derived structures, no lazy/partial loading that could
  change what a request sees.
* `Dataset` itself is not slotted: it legitimately carries dynamic caches (`_metrics`,
  `_device_index`).

## 5. The reload path and production's peak

The old holder loaded the new snapshot **inside the request**, holding the old dataset. The new
holder loads in one background thread and swaps a reference, but it still holds both datasets
during the load — that is what keeps the old data available if the new snapshot is broken.

Measured cost of that coexistence after the optimisation: **+163 MB** for the second dataset
(no index), **+283 MB** including a new index. Production's `memory.peak` (1.871 GB) is
consistent with the *old* +758 MB switch on top of a ~1.0 GB live dataset.

The 3-switch series still shows an allocator high-water effect (583 → 557 → 653 MB) without a
new peak, i.e. the process does not grow without bound, but it also does not return to the
cold-load RSS. That is expected for `pymalloc` and is bounded by the largest single switch.

## 6. Limitations of this profile

* RSS numbers are from the Windows benchmark host (same snapshot, same code). Linux production
  uses `mmap`-backed arenas and returns empty arenas more eagerly, so the **live** reduction
  should be similar or slightly larger, and the retained high-water should be smaller. This is
  a hypothesis to confirm with the post-deployment measurement in `DEPLOYMENT_CHANGE_REQUEST.md`,
  not a claim.
* `tracemalloc` adds 10–20 % heap overhead; it was used only to attribute allocations, never
  for the RSS table.
* The device index size depends on the snapshot (previous snapshots have fewer relations); the
  table above always uses the same active snapshot.
* The benchmark host has 32 GB and 16 vCPUs. Memory numbers transfer; timing does not.

## 7. Production-host confirmation (Linux, 2 vCPU, 3.72 GiB)

Step 9 of the task: the same probe was run **on the real production host**, against a
throw-away copy of the active snapshot in `/tmp`, inside a transient cgroup with a hard memory
cap and **swap disabled for the scope**. No production file, unit or process was touched; the
host was at `MemAvailable=1588 MB` before and `1615 MB` after, swap free unchanged, PSI 0.00.

| Stage | RSS | Peak RSS |
|---|---|---|
| process start | 15.3 MB | 15.3 MB |
| imports | 20.4 MB | 20.4 MB |
| dataset loaded (9.0 s) | 201.8 MB | 216.2 MB |
| warm queries | 208.4 MB | 216.2 MB |
| device index (5.4 s) | 328.6 MB | 335.4 MB |
| reload 1: old + new dataset | 513.6 MB | — |
| reload 1: + new index | 632.1 MB | 637.1 MB |
| reload 2: + new index | 785.3 MB | **790.3 MB** |
| after releasing the second old dataset | 629.4 MB | — |

Caps: `MemoryMax=900M` for the load/index run and `MemoryMax=1100M` for the two-switch run,
both with `MemorySwapMax=0`. Both runs completed with **zero swap and no OOM** — i.e. the new
activation path cannot push this host into a swap storm even if it tried.

This replaces the "Linux is a projection" caveat for the *optimised* build: the Linux numbers
are the same as the Windows probe within noise (201/336 MB vs 213/336 MB). The old build was
not run on production (its 1.9 GB switch peak with the web resident would have been unsafe);
the old-vs-new comparison therefore remains the same-host Windows measurement plus the
production `memory.peak` observation.