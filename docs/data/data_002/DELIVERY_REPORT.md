# MedRadar DATA-002 — Production Readiness & Continuous Sync Delivery Report

**Task:** DATA-002
**Branch:** `feat/data-002-production-readiness`
**Draft PR:** https://github.com/ChazY11/medradar/pull/51
**Base:** `feat/data-001-continuous-pipeline` (stacked; PR #50 remains Draft)
**Fixed SHA:** `bb1ef34df3c15e2b1339432abce899eebea5e1f6`
**Production deployment:** **NOT EXECUTED** — requires the approval in
`DEPLOYMENT_CHANGE_REQUEST.md`.

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
| G4 Resource safety | PASS (measured) |
| G5 Backup & recovery | PASS (same-host); off-host limitation stated |
| G6 Operational health | PASS (code + isolated endpoint) |
| G7 Continuous operation | **BLOCKED** — timer not enabled, no production trigger |
| G8 Product acceptance | **PARTIAL** — isolated real UI accepted; production URL not switched |

## What is not deployed

Production still runs:
`1bdb1c349c59713e1a11426f15a6c06e892f87e0`, `medradar-web.service` on 200,
package snapshot `2026-11-14T22:09:22Z-openfda`, `/srv/medradar/data` with only `cache/` and
`identity/`. No timer, no pipeline DB, no API key, no backup/health script replacement, no
public port, no PR merge.

## Approval needed

The exact commands, fixed SHA and rollback steps are in
`DEPLOYMENT_CHANGE_REQUEST.md`. Approval covers code deploy, production data root, bootstrap,
source reconciliation, web data-dir switch, timer enablement and the new backup/health
scripts. Until then G7 is **BLOCKED**, not PASS.
