# DATA-002 — Production Readiness

## Scope

DATA-002 hardens the DATA-001 pipeline for continuous operation on the existing 2 vCPU /
4 GB Tencent Cloud host. It does not add new product features or new FDA sources.

The production switch is **not** part of this software change. The exact approval checklist is
`DEPLOYMENT_CHANGE_REQUEST.md`; Gate G7 remains BLOCKED until that is approved and a timer
actually fires.

## 1. Source isolation

Implemented in `Pipeline.run()` and `Pipeline._sync_locked()`. See `SOURCE_ISOLATION.md`.

At a glance:

* failures are classified per source;
* healthy updates are collected even when another source fails;
* collection itself is caught per source for automatic runs;
* partial snapshots carry old versions for failed/deferred sources and never claim `SYNCED`;
* the quality gate is unchanged;
* one product source per automatic run by default for 4 GB safety;
* a combined two-source snapshot remains supported and tested.

## 2. Health semantics

New endpoints:

| Endpoint | Meaning | HTTP |
|---|---|---|
| `/api/livez` | process answered; no data file dependency | always 200 when process alive |
| `/api/readyz` | a validated dataset can be served (including fallback) | 200 ready; 503 no dataset |
| `/api/health` | layered data/sync/freshness report | 200 when readable; 503 only when no dataset |

`/api/health.checks`:

* `liveness`;
* `readiness`;
* `data` (`available` / `degraded` / `unavailable`, `using_fallback`);
* `sync` (`ok` / `running` / `update_pending` / `degraded` / `stale` / `unknown`);
* `freshness` (`current` / `update_pending` / `degraded` / `unknown`).

A readable fallback is **degraded**, not `ok`, but it remains HTTP 200 because read-only
queries still work. A missing dataset is `not_ready`/503. A live process is never presented as
a successful sync. Official version age alone does not create `stale`; a pending update or a
failed check does. This avoids treating FDA's monthly/weekly cadence as a MedRadar outage.

`deploy/scripts/medradar-health-v2.sh` is the CLOUD-003-compatible adapter. It checks JSON
states and exits 1 for `degraded`/`unknown`, 2 for `not_ready`; the old script only checked
HTTP 200 and is not silently replaced.

## 3. Scheduler

* Timer wake-up: **hourly** (`OnUnitActiveSec=1h`), not every six hours.
* Per-source due logic still enforces 24 h (510(k)/PMA), 6 h (recall), 24 h (classification).
* Failed sources retry after 1 h.
* `run` never collects an undued source.
* `run` catches per-source failures and returns `PARTIAL`/`BLOCKED`; it does not pretend a
  partial run is fully successful.
* `run` returns exit 0 for `PARTIAL` only because the active snapshot is readable; monitoring
  must read the JSON status. `BLOCKED`/`FAILED` return nonzero.
* Full reconciliation is a rolling low-frequency sweep: one product source per run,
  `MEDRADAR_PIPELINE_FULL_RECONCILE_HOURS=168` by default. It is not a substitute for the
  version check, and it is not run if the remaining daily request budget cannot cover the
  estimate. A deferred sweep is recorded and retried later, never a half sweep reported as
  success.

## 4. CLI

All commands accept `--json` before or after the subcommand. The deployment examples are
executed by `tests/data_pipeline/test_cli.py` against an isolated state root.

Commands: `bootstrap`, `check`, `run`, `sync`, `status`, `changes`, `rollback`, `prune`,
`backup`, `restore`.

`backup` and `restore` are new in DATA-002; see `BACKUP_RECOVERY.md`.

## 5. Systemd templates

`deploy/systemd/medradar-data-update.service`:

* `MemoryHigh=2200M`, `MemoryMax=2400M` (measured; not the stale 1800M);
* `CPUQuota=150%`, `Nice=10`, idle I/O, `TimeoutStartSec=1h`;
* hard write scope `/srv/medradar/data`;
* no API key in unit or repository;
* per-run product-source cap = 1.

`medradar-data-update.timer` is hourly. `medradar-data-backup.service/timer` is a new
same-host backup proposal. None are installed before approval.

## 6. Full reconciliation

`run` selects at most one product source whose
`last_full_reconciliation_at` is null or older than the configured interval, provided the
source is healthy and not already being version-synced. A successful scoped collection marks
that source's full sweep complete. The source remains under the same hash/ledger/validation
rules. This closes the theoretical blind spot where the endpoint version and total do not
change but an old record is corrected.

Cost guard: remaining daily request budget must cover the estimate plus a 5% reserve; if not,
the sweep is deferred with an incident and no snapshot is built. The request budget is still
enforced by `OpenFDAClient` before every attempt.

## 7. Backup

SQLite is copied with its backup API, not a file copy. The active pointer, all immutable
snapshots, the change ledger, source history, request usage and incidents, and the identity
review database are captured in a self-describing directory with per-file SHA-256. Restore
refuses a non-empty destination, verifies every digest, runs `PRAGMA integrity_check`, checks
the active pointer/DB agreement and runs the full snapshot validator before reporting success.
The same-host limitation is stated: this is operational recovery, not off-host disaster
recovery.

## 8. Production status

The approved deployment of fixed SHA `bb1ef34df3c15e2b1339432abce899eebea5e1f6` executed on
2026-11-16. Production serves `/srv/medradar/data/fda`, active snapshot
`fda-snapshot-20261116T032632Z-18ce4d0cbbe4`; the update and pipeline-backup timers are
enabled. The first systemd-triggered `run` completed with exit 0 and `NO_CHANGE`.

Residual risk: web RSS (1.65–1.87 GiB) plus a one-source sync (1.956 GiB peak) is close to
this 3.7 GiB host's RAM and uses swap. During the production recall sync one `/api/health`
request stalled for 8 s; it recovered without restart and there was no OOM or data loss.
Do not raise `MEDRADAR_PIPELINE_MAX_PRODUCT_SOURCES_PER_RUN` without a new memory test.
