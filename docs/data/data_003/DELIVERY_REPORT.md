# DATA-003 — Delivery report

**Task:** runtime memory optimisation and zero-regression reliability for MedRadar.
**Scope executed:** production read-only Phase 0, isolated root-cause analysis, code changes,
resource guards, monitoring/backup review, benchmarks, tests, this documentation set and a
stacked Draft PR.
**Scope not executed:** any production mutation. No deploy, no restart, no timer change, no PR
merge.

## 1. What was asked, and what was found

| Question | Answer | Evidence |
|---|---|---|
| Where did 800 MB → 1.61 GB come from? | The live dataset is ~0.85–1.0 GB (181 MB of JSON parsed into 91 k evidence records). The rest is the allocator high-water left by the DATA-002 snapshot switch, which held the old **and** new dataset at once (+758 MB measured). It is not a reference leak. | `ROOT_CAUSE.md` §1–§3 |
| How big is the device index? | 90 MB RSS / 106 MB of objects, 5.7 s to build. It is not the cause. | `MEMORY_PROFILE.md` §1 |
| Did `DatasetHolder` keep the old dataset alive? | During the switch, yes — by design, for fallback. It doubled the peak. | `ROOT_CAUSE.md` §3 |
| Direct cause of the 8 s health timeout? | One global lock held for the entire in-request load; every request (including health) queued behind it; swap amplified it. | `ROOT_CAUSE.md` §4 |
| GIL vs CPU vs locks vs swap? | Lock queueing dominated (seconds–minutes); swap amplified fault latency; the GIL slows *all* threads under saturating CPU load and can starve the background activation (measured 10–40×, disclosed). | `BENCHMARK.md` §6 |
| Can 4 GB still run automatic updates? | Yes, with the new activation path and a host-level guard that stops a sync and an activation from overlapping. | `RESOURCE_GUARDS.md` |
| Is 8 GB needed? | **Not demonstrated.** No measurement requires it. Re-evaluate after a week of `memory.peak` and deferral data. | `OPERATIONS.md` §8 |

## 2. Delivered changes

1. **Dataset representation** — `slots=True` on `Event` and the device model, a string
   canonicalisation pool, a streaming JSONL loader, and a cached attributed-events list.
   Live dataset 956 MB → 336 MB; switch peak 1,930 MB → 781 MB (same host, same snapshot).
2. **Non-blocking, guarded snapshot activation** — one background loader, single-reference
   swap, failure fallback, bounded retries, device-index warm-up, full activation status in
   `/api/health` and `/api/data-status`. A request never waits for a load.
3. **Host resource guard for the web** — activation is deferred (old data keeps serving) when
   the host cannot hold a second dataset, or while a pipeline operation holds the lock.
4. **Host resource guard for the pipeline** — `DEFERRED_RESOURCE_PRESSURE` before any source
   check, recorded as a real run state, exit 0, escalation after three consecutive deferrals,
   explicit operator override.
5. **Monitoring adapter** (`deploy/scripts/medradar-health-v3.sh`, proposal) — layered health,
   activation state, sync deferral, fallback, memory/PSI, severity exit codes.
6. **Backup review + safe pruning** — `prune-backups` (dry run by default) closes the unbounded
   growth risk; the operations guide documents the two-timer layout, the overlap/jitter
   analysis and the restore-before-prune rule.
7. **Tests** — new DATA-003 reliability suite (non-blocking activation, deferral/retry,
   failure fallback, guard arithmetic, lock visibility, pipeline deferral/escalation, backup
   pruning); DATA-002 tests updated to the asynchronous activation contract. Full suite passes.

## 3. Acceptance against G1–G7

| Goal | Verdict | Basis |
|---|---|---|
| **G1 Root cause** | **PASS** | Measured live dataset, switch delta, lock path; production readings agree with the isolated reproduction. |
| **G2 Memory improvement** | **PASS** | −65 % steady, −60 % switch peak, same snapshot and host; fingerprint-identical semantics. |
| **G3 Request availability** | **PASS** | Same load + same switch: baseline 20 s stalls and 2 timeouts vs 0 timeouts, health ≤ 163 ms; real FDA sync under load: 0 timeouts, health max 259 ms. Residual: GIL slowdown under saturating CPU load (disclosed). |
| **G4 Resource protection** | **PASS** | Deferral keeps the old data, records reasons, retries, escalates; a real CLI deferral touched nothing (peak 31 MB, pointer unchanged). |
| **G5 No regression** | **PASS** | Byte-identical dataset/index/quality digests; full pytest suite; API additions only; no evidence field removed. |
| **G6 Repeatability** | **PASS** | Three reload cycles bounded (781 MB peak, no growth), four independent measurement setups, same digests on re-run. |
| **G7 Production safety** | **PASS (as delivered)** | Everything is on a branch; a fixed-SHA deploy + rollback plan is written and **not executed**. |

## 4. What is still limited (do not oversell)

1. **Activation under saturating CPU load.** The loader is pure Python and shares the GIL. It
   never blocks requests through a lock, but it can take tens of seconds when the interpreter is
   saturated, and every thread slows down. Production traffic is low; the guard prevents a sync
   and an activation from overlapping. This is the main residual risk.
2. **The pipeline's own peak is unchanged (~1.8 GB).** DATA-003 protects the host around it; it
   does not shrink it. That is a separate project (streaming change-set build/validation).
3. **The web still has no `MemoryMax`.** A guard prevents the known doubling; it does not cap an
   unknown leak. A `MemoryHigh` on a 4 GB host would throttle rather than protect.
4. **Production numbers are projections.** All optimised measurements ran on the 32 GB Windows
   benchmark host against the identical snapshot. The deployment verification table is the place
   where the real post-change `memory.current`/`memory.peak` must be recorded; if the win is not
   there, the change request says to roll back.
5. **Backups are still same-host.** Not disaster recovery; unchanged by this task.
6. **The health adapter is a proposal.** CLOUD-003's script is untouched in production.

## 5. Recommended next steps (in order)

1. Approve and execute `DEPLOYMENT_CHANGE_REQUEST.md`; record the real post-change memory and
   latency; keep the old SHA ready.
2. After one week, re-calibrate the guards from real `memory.peak`, deferral counts and PSI
   (`OPERATIONS.md` §8).
3. Optimise `/api/events` (the remaining ~0.5 s endpoint): it is the largest GIL consumer and
   the main reason an activation is slower under synthetic load.
4. Consider reducing the pipeline's peak by streaming the change-set build and validation — the
   only remaining way to make the host comfortable during a recall reconciliation.
5. Revisit 8 GB only if the measured peak/deferral data after deployment says the host cannot
   keep up; today's evidence does not support it.

## 6. How to verify this delivery without trusting the report

```bash
# semantics unchanged
python tools/data003/dataset_fingerprint.py --data-dir <snapshot>   # compare with evidence/fingerprint-baseline.json
# memory
python tools/data003/memory_probe.py --data-dir <snapshot> --mode full
python tools/data003/memory_probe.py --data-dir <snapshot> --mode reload --reloads 3
# availability (run once per tree)
python tools/data003/bench_web.py --repo-root <tree> --data-root <root> \
  --duration 30 --concurrency 2 --think-ms 100 --switch-at 6 --json-out out.json
# real sync (isolated root only)
python tools/data003/bench_pipeline.py --root <copy> --args "sync --sources openfda_510k --force --json" --json-out sync.json
# regression
python -m pytest -q
```

Raw evidence for every table is in `docs/data/data_003/evidence/`.

## 7. Repository state

* Branch: `feat/data-003-runtime-reliability`, stacked on `edbde0a` (DATA-002 tip / PR #51).
* Code commit: `b1b841bdc2381b910cdbd53efa75c8aa3a791ddd` (docs follow in the same branch head).
* Draft PR: **#52** (created, not merged).
* Production: unchanged (`bb1ef34`, snapshot `…032632Z-18ce4d0cbbe4`, timers untouched).
* The branch is self-contained: code, tests, tools, docs and evidence.
