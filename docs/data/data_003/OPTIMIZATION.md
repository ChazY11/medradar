# DATA-003 — Optimisation and trade-offs

Four code changes and two new mechanisms. Each one has a measurement in `MEMORY_PROFILE.md`
or `BENCHMARK.md`; the behaviour-preservation proof is in §5.

## 1. Dataset representation (memory)

### 1.1 `slots=True` on the hot dataclasses

`Event` is a 41-field dataclass. Without slots, every instance carries a 1,584-byte
`__dict__`; 91,457 events therefore paid 142 MB just for attribute dictionaries. The same is
true, at smaller scale, for `Application`, `DeviceIdentity`, `ProductFamily`, `DeviceRelation`,
`RecallRecord` and `EvidenceRef` in the device index.

Change: `@dataclass(slots=True)` for `Event`; `@dataclass(frozen=True, slots=True)` for the
device model. `build.py` no longer copies a `DeviceIdentity` through `__dict__` (it uses
`dataclasses.replace`, which is required once slots remove `__dict__`).

Measured: load 866 → 742 MB, +index 956 → 812 MB (before the other changes).

`Dataset` stays a normal dataclass on purpose: it carries dynamic per-instance caches
(`_metrics`, `_device_index`) and is created once.

### 1.2 String canonicalisation during load

`json` creates a new `str` for every occurrence. On this snapshot:

* raw values: 51.7 MB of characters, only 20.3 MB distinct;
* raw keys: 20 per record, **57 distinct strings** in total;
* `source_id`, `event_type`, `record_state`, `published_at_status`, `time_quality`: 1–4
  distinct values each, repeated 91,457 times.

Change: `_StringPool` canonicalises strings while the snapshot is loaded, for event fields,
raw keys and raw values (lists are rebuilt element-wise). The pool is local to `load_dataset`
and is released when loading ends; only the canonical strings survive, referenced by the
events.

Semantics: string values are unchanged. Only object identity changes, and identity is not
observable through the public API (`==`, JSON serialisation and hashing by value are
unaffected).

### 1.3 Streaming parse

`_read_jsonl_gz` returned a list of 91 k row dicts. Those rows stayed alive while `Event`
objects were being built, so the loader held the JSON rows *and* the events. `_iter_jsonl_gz`
yields one row at a time; a row (and its duplicate strings) becomes garbage as soon as its
`Event` exists.

### 1.4 Reuse of the attributed-events list

`load_dataset` already materialised `attributed = [event for event in events if
event.organization_key]` for the global counts, then threw it away. `filter_events` rebuilt
the same 91 k-element list on every `/api/events` request.

Change: keep it on the dataset (`_attributed_events`) and use it when no organization filter is
applied. This is the largest single latency improvement for the event browser, and it also
reduces the GIL pressure that a snapshot activation has to compete with.

## 2. Snapshot activation (`DatasetHolder`)

DATA-002 loaded the new dataset inside the request that noticed the pointer change, under one
global lock. DATA-003 replaces that with a small state machine:

* `get()` **never loads** when a dataset is already active. It returns the current dataset and,
  at most every 2 s, checks whether the pointer or review fingerprint changed.
* One background thread (`medradar-dataset-activation`) loads and validates the new snapshot.
  The swap is a single reference assignment; a request sees either the old or the new dataset.
* A failure keeps the old dataset, records `last_error`, sets `state=failed`, and retries with
  backoff (30/60/120/300 s). The degraded state is visible in `/api/health` and
  `/api/data-status`, exactly like DATA-002's fallback semantics.
* A cold start still blocks on the first load: there is no older dataset to serve.
* The same thread builds the device index **before** the swap (Correction-1), so the swap
  publishes a complete dataset and `/api/devices` never sees an index that is not ready. The
  index build is guarded by a per-dataset lock so a concurrent request cannot build it twice.
* `reload_status()` exposes state, phase, progress, elapsed time, attempts, deferrals, the last
  guard decision, and the pending snapshot. `/api/health` adds an `activation` check and
  `/api/data-status` adds `dataset_activation`.
* `invalidate(wait=True)` / `reload_now()` stay synchronous for the loopback review service,
  which must show a decision on the next read. `poll_once()` lets an operator tool ask
  "is there a new snapshot?" without waiting for request traffic.

Trade-off: after a publish, the site serves the previous snapshot for the duration of the
background load (~8 s idle, longer under CPU load). `using_fallback=false` and
`activation.state=loading` make that explicit. DATA-002 behaved the same way in practice (it
served the old data until the new load finished) — it just blocked every other request while
doing it.

## 3. Web activation resource guard

Before allocating a second dataset, the holder asks `medradar/product/resources.py`:

* is a pipeline operation running? (it probes the existing `pipeline.lock` with `flock`)
* does the host have `MemAvailable >= 384 MB + 1.0 × our anonymous RSS` (the new copy is the
  dataset *and* its index)?
* `SwapFree >= 192 MB`, PSI memory `some avg10 <= 6.0`?
* does the data filesystem have room?

If not, the activation is **deferred**: the old dataset keeps serving, `state=deferred` and the
reasons are recorded and retried after 15 s. No request waits, nothing is dropped, and the
condition is visible in health. The constants are calibrated in `RESOURCE_GUARDS.md`; they are
not guesses.

## 4. Pipeline host guard

`Pipeline.run()` and `sync()` now refuse to start a memory-heavy reconciliation without host
headroom (defaults: `MemAvailable >= 1200 MB`, `SwapFree >= 384 MB`, PSI <= 8.0, disk >=
2 GB). The guard runs **before** the source checks, so a deferred run cannot record a check
that it then refuses to act on (which would postpone the update until the next check interval).

The refusal is a real state, not an exception:

* `RunStatus.DEFERRED` in the run ledger, with `reason=DEFERRED_RESOURCE_PRESSURE`, the guard
  snapshot, and `retry` text;
* process exit code 0 (the job ran; it deliberately did no work), so systemd does not raise a
  false failure, while `status`, `message` and `/api/data-status` say DEFERRED;
* three consecutive deferrals also record an incident, so a permanently starved host is not
  silent;
* `--allow-resource-pressure` is the explicit operator override.

This is deliberately the *only* new pipeline behaviour: collection, change detection,
validation, publication and rollback are untouched.

## 5. Behaviour preservation proof

`tools/data003/dataset_fingerprint.py` hashes every event's public projection, the global
counts/aggregations, every organization's `OrgStats`, every device-index object and the device
quality report. Run against the old tree and the new tree on the same snapshot:

| Digest | Old tree (edbde0a) | New tree |
|---|---|---|
| events | `560ff100db4d…` | **identical** |
| aggregates | `c3068d32e6…` | **identical** |
| device index | `cad9bc43f4…` | **identical** |
| quality report | `bd3040f3b6…` | **identical** |

The full test suite (PRODUCT-001/002/003, DATA-001/002) passes; four DATA-002 tests that
asserted the *synchronous* reload contract were updated to the new asynchronous contract and
now also assert the new guarantees (non-blocking, failed activation visible, deferred
activation, escalation).

## 6. Rejected alternatives

| Alternative | Why not |
|---|---|
| **Controlled process restart** to load the new snapshot | Would lose the in-process review-ledger reload (admin decisions must appear without a restart), needs systemd changes, and gives a guaranteed multi-second outage. The double-buffer peak is now 285 MB, which the guard can cover; a restart is not justified by the evidence. Kept as an emergency option in `RELIABILITY.md`. |
| **Persisted pickle/derived cache** of the index | Explicitly forbidden by the task and by DATA-001's documented rule (untrusted deserialisation). The index rebuild is 5.7 s, once, in the background. |
| **Lazy/partial event loading** | Would change request semantics (a page could return incomplete data), risks the evidence guarantees, and is not needed: 213 MB for the full live dataset is acceptable on this host. |
| **Deleting or truncating `raw`** | Changes the evidence payload and the `/api/events/{id}` contract. Forbidden. |
| **`gc.freeze()` after load** | Would move the *old* dataset to the permanent generation too, so every switch would leak a full dataset. |
| **Lowering `sys.setswitchinterval` globally** | Helps a background thread slightly but slows every request; measured benefit did not justify a global interpreter setting. |
| **A second Uvicorn worker** | Doubles resident memory for no availability gain here; explicitly out of scope. |

## 7. Rollback

Every change is in `feat/data-003-runtime-reliability` on top of `edbde0a`
(DATA-002 tip). Production rollback is a checkout of the previous SHA plus a service restart;
the data format is unchanged, so snapshots written by the new code are readable by the old code
and vice versa. See `DEPLOYMENT_CHANGE_REQUEST.md` §Rollback.
