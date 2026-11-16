# MedRadar DATA-003 — Production Performance Acceptance Report

| Item | Value |
|---|---|
| Report date | 2026-11-17 (CST) |
| Host | Tencent Lighthouse, 2 vCPU, 3.72 GiB RAM, 1.99 GiB swap, Ubuntu 24.04 |
| Deployed code | **`7415382df8d449194557a440cf9a869da3b25c59`** (PR #52, Correction-1) |
| Previous code / rollback target | **`bb1ef34df3c15e2b1339432abce899eebea5e1f6`** |
| Active data snapshot | `fda-snapshot-20261116T032632Z-18ce4d0cbbe4` (unchanged before and after) |
| Deployment window | 04:22:20–04:22:36 CST (restart); verification 04:22–04:31 |
| Production pointer changed by the deployment | **no** |

## 1. Verdict

**PASS.** The DATA-003 optimisation is live and materially reduced production memory without
changing data, the snapshot pointer or the API contract:

| Metric | Before (DATA-002, 04:20) | After (DATA-003, 04:29) | Change |
|---|---|---|---|
| cgroup `memory.current` | 1,644,937,216 B (1,568.7 MiB) | **390,156,288 B (372.1 MiB)** | **−76.3 %** |
| cgroup `memory.peak` | 1,871,839,232 B (1,785.1 MiB) | **398,688,256 B (380.2 MiB)** | **−78.7 %** |
| `VmRSS` | 1,609,700 kB (1,572.0 MiB) | **368,948 kB (360.3 MiB)** | **−77.1 %** |
| `VmSwap` / cgroup `memory.swap.current` | 277,512 kB / 331.9 MiB | **0 / 0** | −100 % |
| host swap used | 538 MiB | **206 MiB** | −332 MiB |
| host `MemAvailable` | 1,625 MiB | **2,793 MiB** | +1,168 MiB |
| `/api/health` latency (20 samples) | 19.1 ms (single sample) | **p50 17.1 / p95 19.8 / max 20.7 ms** | no regression |
| cold start | not measured under DATA-002 | **15.0 s** (load 9 s + index 5.05 s) | measured |

Service: `active`, `NRestarts=0`, `memory.events oom=0`, no journal errors since the restart.
Data unchanged: 91,457 events, 61,632 applications, 23,974 devices, 630 families, 77,823
relations — all identical to the pre-deployment counts.

## 2. What was executed

1. **Pre-flight (read-only).** `git` at `bb1ef34…`, clean; active snapshot
   `…032632Z-18ce4d0cbbe4`; service `active`, `NRestarts=0`; listener `127.0.0.1:8787` only;
   48 GB free; PSI 0.00. A fresh DATA-002 backup was created
   (`data-backup-20261116T202050Z-8a500a`, 171 MB, 26 files) and **restored into `/tmp` with
   `validation.ok=true`** (91,457 events, device index 61,632 / 23,974 / 77,823, pipeline DB
   integrity `ok`) before any change.
2. **Code.** `git -C /srv/medradar/app checkout 7415382…` (editable install points at
   `/srv/medradar/app`; **no pip step**). HEAD verified, tree clean, `import medradar` resolves to
   `/srv/medradar/app/medradar/…`.
3. **Guard configuration.** `/etc/medradar` did not exist; it was created (`root:medradar 0750`)
   and `/etc/medradar/pipeline.env` written (`root:medradar 0640`) with
   `MEDRADAR_PIPELINE_RESOURCE_GUARD=1`, `MIN_AVAILABLE_MB=1200`, `MIN_SWAP_FREE_MB=384`,
   `MAX_PSI_SOME=8.0`, `MIN_DISK_FREE_MB=2048`.
4. **Restart.** `systemctl restart medradar-web`; journal shows process start 04:22:21 and the
   unit "Started" (after its `ExecStartPost` readiness probe) at 04:22:36 → **cold start 15.0 s**.
   No 5xx, no OOM.
5. **Deploy record.** `/srv/medradar/var/DEPLOYED_SHA` (stale since CLOUD-003, `1bdb1c3…`) was
   backed up to `DEPLOYED_SHA.pre-data003` and rewritten with the new SHA, previous SHA, branch,
   data snapshot and the preserved CLOUD-003 cloud-snapshot line.

No snapshot, timer schedule, service unit, firewall or SSH configuration was changed.

## 3. Cold start and endpoint latency (after)

| Measurement | Result |
|---|---|
| process start → unit Started (`readyz` 200) | **15.0 s** (dataset load 9.0 s + device index 5.05 s + uvicorn) |
| `/api/health` | p50 17.1 ms, p95 19.8 ms, max 20.7 ms (20 samples, idle) |
| `/api/data-status` | 16.6 ms |
| `/api/organizations` | 2.1 ms |
| `/api/events?page_size=25` | 430 ms |
| `/api/devices` | 100 ms |
| `/api/devices/quality` | 256 ms |
| `/api/meta` | 165 ms |

The restart's `readyz` probe can look instantaneous because `systemctl restart` waits for
`ExecStartPost`, which itself polls `/api/devices` and therefore blocks on the cold load; the
15.0 s figure comes from the journal timestamps (process start vs unit Started), not from the
probe loop.

## 4. Snapshot activation acceptance (isolated on the production host)

The production pointer was deliberately **not** switched. The deployed code was exercised
against a byte-copy of the data root in `/tmp`, inside a transient cgroup with
`MemoryMax=1200M` and `MemorySwapMax=0`:

```
sudo systemd-run --scope --uid=medradar -p MemoryMax=1200M -p MemorySwapMax=0 -p CPUQuota=200% \
  env MEDRADAR_REVIEW_DB=/srv/medradar/data/identity/review.db \
  sh -c 'cd /srv/medradar && exec /srv/medradar/.venv/bin/python \
    /srv/medradar/app/tools/data003/bench_web.py --data-root /tmp/d3-accept --port 8898 \
    --duration 25 --concurrency 1 --think-ms 300 --switch-at 5 --json-out /tmp/result.json'
```

| Result | Value |
|---|---|
| requests / errors / timeouts / 5xx | 57 / 0 / 0 / 0 |
| activation (idle→loading→idle) | **24.18 s** (load + index + first device page) |
| `/api/health` during the window | p50 51.0 ms, **max 58.3 ms** |
| overall request p50 / p95 / max | 101 / 841 / 887 ms |
| server RSS max | **671 MB** |
| swap used in the scope | **0** |
| OOM / cap kill under 1200 M | none |
| pointer after the run | restored to the original snapshot (isolated copy only) |

**Index/data consistency on the live service**: `/api/devices/quality.snapshot.id` equals
`/api/readyz.snapshot.id` (`…032632Z-18ce4d0cbbe4`), `index_build_ms=5054.6`, and the index
counts match the pre-deployment snapshot. `activation.index_ready=true` on the live service.
This is the Correction-1 guarantee: a dataset is published only after its index is built.

## 5. Resource guard status

* Guard enabled with the calibrated defaults; no activation deferral (`deferrals=0`) and no
  pipeline deferral (`synchronization.deferral=null`).
* `memory.events`: `low=0 high=0 max=0 oom=0 oom_kill=0`.
* The guard's effect is preventive: the sync peak is ~1.8 GB measured; with the web now at
  0.37 GB the host has 2.7 GB available, so the next reconciliation starts with headroom instead
  of competing with a 1.6 GB web process.

## 6. Timers and automatic work (post-deployment)

| Unit | Result | Detail |
|---|---|---|
| `medradar-health.timer` | **success** (04:24, 04:29) | 5-minute health checks continue; exit 0 |
| `medradar-data-update.service` (manual run, same path as the timer) | **NO_CHANGE**, exit 0, 1 s | sources not due; no deferral; active pointer unchanged |
| `medradar-data-update.timer` | next 05:28:51 | schedule intact |
| `medradar-data-backup.service` (manual run) | **success**, 171 MB, 26 files, DB integrity `ok` | new backup `data-backup-20261116T202427Z-584318` |
| `medradar-data-backup.timer` | next 2026-11-18 03:27:29 | schedule intact |
| `medradar-backup.timer` (CLOUD-003, 04:30) | **success**, 372 B | pre-existing scope: `data/identity/`, `data/cache/`, `var/DEPLOYED_SHA` — it never contained the dataset |

No unit entered a failed state; no resource-pressure delay was observed.

## 7. Rollback verification (not executed)

* `bb1ef34df3c15e2b1339432abce899eebea5e1f6` is present in `/srv/medradar/app`.
* Its tree was exported with `git archive` (132 Python files) and **compiled successfully with
  the production interpreter** (Python 3.12.3); it contains no DATA-003 marker.
* `/srv/medradar/var/DEPLOYED_SHA.pre-data003` keeps the previous deploy record.
* Rollback is: `git -C /srv/medradar/app checkout bb1ef34… && systemctl restart medradar-web`
  (the editable install follows automatically; no data migration, no snapshot change).

**Decision rule (from the change request):** if `memory.current` had not fallen materially below
1.6 GB, or if a sustained 5xx/OOM/snapshot inconsistency/index failure had appeared, the service
would have been rolled back to `bb1ef34…`. None of those conditions occurred; the observed
372 MiB is well inside the intended target.

## 8. Deviations and findings

1. **`/etc/medradar` did not exist.** Created as part of the approved guard configuration; the
   file is optional (`EnvironmentFile=-`), so this changes nothing for units that do not use it.
2. **Restore drill needs the service environment.** Running `restore` from a foreign working
   directory resolves the default review-DB path relative to that directory and fails with
   `Permission denied: 'data/identity/review.db'`. The drill succeeded with
   `cd /srv/medradar` and `MEDRADAR_REVIEW_DB=/srv/medradar/data/identity/review.db`. The
   runbook command is corrected in this commit.
3. **`readyz` timing.** The first `readyz` probe after `systemctl restart` returns only after
   `ExecStartPost` has warmed `/api/devices`; the cold-start duration must be read from journal
   timestamps (or `ExecMainStartTimestamp` → `ActiveEnterTimestamp`).
4. **CLOUD-003 backup scope.** Its archive is 372 B because it covers identity/cache/deploy
   record only; this is pre-existing and not a DATA-003 regression. The dataset backup is the
   DATA-002 unit (171 MB, verified restore).
5. **Deploy record typo** (`branch=...relability`) was noticed and corrected immediately after
   writing; the file now reads `reliability`.
6. **No health-adapter replacement, no backup pruning, no snapshot deletion, no PR merge** were
   performed — all remain outside this authorisation.

## 9. Follow-ups (not part of this deployment)

* Re-read the same metrics after 24 h and after the next real snapshot publish, to confirm the
  post-activation peak on the live service (isolated measurement suggests ~0.7–0.8 GB, still
  far below the old 1.87 GB peak).
* Install the health adapter v3 only after a side-by-side trial (separate approval).
* Enable backup pruning only after a verified restore of the newest backup (separate approval).

## 10. Evidence

| File | Content |
|---|---|
| `/tmp/pf-health.json`, `/tmp/pf-data-status.json` (host) | pre-deployment health and data-status |
| `/tmp/d3-health-post.json`, `/tmp/d3-datastatus-post.json` (host) | post-deployment health and data-status |
| `/tmp/d3-quality-post.json`, `/tmp/d3-readyz-post.json` (host) | index/snapshot consistency |
| `/srv/medradar/var/backup/data/data-backup-20261116T202427Z-584318` | post-deployment backup with manifest |
| `/srv/medradar/var/DEPLOYED_SHA`, `DEPLOYED_SHA.pre-data003` | deployment record and its predecessor |
| journald (`medradar-web`, `medradar-data-update`, `medradar-data-backup`, `medradar-backup`) | execution timings and results |

The host-side `/tmp` files are transient; the authoritative values are reproduced in this report
together with the commands that produced them.
