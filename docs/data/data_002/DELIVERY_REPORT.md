# MedRadar DATA-002 — Production Readiness & Continuous Sync Delivery Report

**Task:** DATA-002
**Branch:** `feat/data-002-production-readiness`
**Draft PR:** https://github.com/ChazY11/medradar/pull/51
**Base:** `feat/data-001-continuous-pipeline` (stacked; PR #50 remains Draft)
**Fixed SHA:** `bb1ef34df3c15e2b1339432abce899eebea5e1f6`
**Production deployment:** **EXECUTED 2026-11-16** under the user approval; active snapshot
`fda-snapshot-20261116T032632Z-18ce4d0cbbe4`; timer active. Full details:
`PRODUCTION_DEPLOYMENT_REPORT.md`.

## What changed in code

### 1. Source isolation

`Pipeline.run()` now classifies every source independently. A failed/degraded source is
recorded and skipped; healthy sources still reconcile. Automatic runs catch collection
failures per source, discard that source's partial candidate, keep its old official version,
and publish a partial snapshot with `sync_status=FAILED` and `source_outcomes`. The old
quality gate is unchanged. See `SOURCE_ISOLATION.md`.

Default automatic cap: **one product source per run** on this host. Combined two-source
snapshots remain supported and are tested with the cap raised.

### 2. Layered health

New `/api/livez`, `/api/readyz`, and layered `/api/health` with `checks` for liveness,
readiness, data, sync and freshness. A readable fallback is HTTP 200 / `degraded` with
`using_fallback=true`; no dataset is HTTP 503 / `not_ready`. A live process is not a
successful sync. The old CLOUD-003 health adapter is not modified; a compatible replacement
is supplied at `deploy/scripts/medradar-health-v2.sh`.

### 3. Scheduler, full reconciliation and CLI

* hourly timer wake-up; per-source intervals still 6 h / 24 h;
* failed sources retry after 1 h;
* rolling weekly full-content reconciliation, one product source per run, budget-guarded,
  never half-run as success;
* `--json` accepted before or after every subcommand, tested by
  `tests/data_pipeline/test_cli.py`;
* new `backup` and `restore` commands.

### 4. Resource behavior

| Operation | Result |
|---|---|
| Bootstrap | 47.2 s, 1.40 GiB peak |
| **All sources** (510k+PMA+recall) | **8:32, 241 requests, 1.236 GB, 2.16 GiB peak**, under 2.4 GiB cgroup |
| One-source full reconcile (PMA) | 3:11, 1.84 GiB peak |
| Production web during all tests | stayed `ok`, old snapshot |

Automatic production uses one product source per run; the all-source run proves the combined
format but is not the default scheduler shape.

### 5. Backup and restore

`backup` uses SQLite's backup API under the pipeline lock, includes pointer, DB, all snapshots
and the review DB with SHA-256. Real isolated restore: 26.26 s, DB integrity ok, active
snapshot and ledger preserved, product + device index validated. Same-host only; off-host
disaster recovery is explicitly not claimed.

## Test totals

* `python -m pytest tests/data_pipeline tests/product -q`: **175 tests, all pass**.
* `python -m medradar selftest`: **1,270 tests, OK (3 skipped)**.
* `systemd-analyze verify`: all four proposed units pass.
* Isolated real server: bootstrap, all-source sync, full one-source reconcile, rollback
  A→B→A, backup, restore, layered health adapter, Data Status page.

Evidence: `docs/data/data_002/evidence/`.

## Gate status

| Gate | Status |
|---|---|
| G1 Source independence | PASS (software/isolation) |
| G2 Data integrity | PASS |
| G3 Snapshot safety | PASS |
| G4 Resource safety | PASS with residual risk (measured) |
| G5 Backup & recovery | PASS (same-host); off-host limitation stated |
| G6 Operational health | PASS (code + isolated endpoint) |
| G7 Continuous operation | **PASS (first trigger)** — automatic `run` at 11:20:22, exit 0; next 12:24 |
| G8 Product acceptance | **PASS (first run)** — production Web/API/Data Status accepted; residual sync latency risk |

## Production state

Production now runs fixed SHA `bb1ef34df3c15e2b1339432abce899eebea5e1f6`, serves
`/srv/medradar/data/fda`, active snapshot
`fda-snapshot-20261116T032632Z-18ce4d0cbbe4`, all four source versions recorded, and the
hourly update plus daily pipeline backup timers are enabled. The first systemd-triggered
`run` completed with exit 0 and `NO_CHANGE`.

The old code and package snapshot are retained under
`/srv/medradar/var/backup/data002-pre/`; the old package snapshot remains available. No PR
was merged. The CLOUD-003 health/backup scripts remain unchanged.

One residual risk is recorded: during the concurrent production recall sync, one
`/api/health` request stalled for 8 s while the web process swapped/reloaded; no OOM, no 5xx,
no data loss, and the service recovered without restart.

## Approval record

The exact commands, fixed SHA and rollback steps are in
`DEPLOYMENT_CHANGE_REQUEST.md`; the approval was granted and the controlled deployment was
executed. No PR merge is included.
