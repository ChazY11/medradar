# DATA-002 — Controlled Production Deployment Report

**Status: EXECUTED under the user's 2026-11-16 approval.**
**Deployed SHA:** `bb1ef34df3c15e2b1339432abce899eebea5e1f6`
**Active snapshot:** `fda-snapshot-20261116T032632Z-18ce4d0cbbe4`
**Report time:** 2026-11-16 11:30 CST (03:30 UTC)

No PR was merged. PR #50 and #51 remain Draft. SSH, firewall, DeepSeek Harness, the
CLOUD-003 health script and the CLOUD-003 backup script were not modified.

## Stage results

| Stage | Result |
|---|---|
| 1. Deploy fixed SHA, old data | PASS — `bb1ef34`, old package snapshot still served; health 200 `unknown` |
| 2. Create pipeline root + bootstrap | PASS — 91,457 records, 48.84 s, 1.40 GiB peak |
| 3. Per-source real FDA sync | PASS — 510(k), PMA, recall each exit 0, validation true |
| 4. Switch web data dir | PASS — web `2.2.0-data-002`, active pipeline snapshot, all health layers ok |
| 5. Real browser acceptance | PASS — home, organizations, events, devices, sources, compare, org/device detail, Data Status |
| 6. Install/enable timers | PASS — update timer and pipeline backup timer enabled |
| 7. Automatic systemd trigger | PASS — timer triggered `run` at 11:20:22, exit 0, `NO_CHANGE` |
| 8. Backup/restore/rollback | PASS — final backup, isolated restore, production rollback A→B→A |

## Per-source production result

| Source | Official version | Records | Check | Last successful sync (UTC) |
|---|---|---|---|---|
| 510(k) | `2026-11-02` | 176,625 | `NO_CHANGE` | `2026-11-16T03:07:08.125155Z` |
| PMA | `2026-11-02` | 57,487 | `NO_CHANGE` | `2026-11-16T03:10:27.142864Z` |
| Recall | `2026-11-12` | 59,705 | `NO_CHANGE` | `2026-11-16T03:27:18.550991Z` |
| Classification | `2026-11-02` | 7,098 | `NO_CHANGE` | `2026-11-16T03:27:18.568032Z` |

The first source syncs are a **rebaseline**, not fabricated changes:
23,400 + 38,232 + 29,825 = **91,457 rebaselined** records. The active snapshot contains
91,457 records.

**Real changes in the first reconciliation:**

* ADDED: **0**
* UPDATED: **0**
* REMOVED: **0**
* UNRESOLVED: **0**

A second forced recall sync and classification refresh produced the same zero changes.

## Web / API acceptance

All returned HTTP 200:

`/`, `/organizations`, `/events`, `/devices`, `/sources`, `/compare`, `/data-status`,
`/api/livez`, `/api/readyz`, `/api/health`, `/api/data-status`, `/api/meta`,
`/api/changes`, `/api/organizations`, `/api/events`, `/api/devices`, `/api/coverage`,
`/api/devices/quality`, `/api/search`.

Browser checks: home, organization list, organization detail (`draeger`), regulatory event
browser, device list, device detail (`PMA P980016`), sources, compare, Data Status. No browser
console errors. Production screenshot:
`evidence/production-final-data-status.png`.

Final `/api/health`:

* overall `ok`, version `2.2.0-data-002`, active snapshot `…032632…`;
* liveness/readiness/data/sync/freshness all `ok`/`available`/`current`;
* `using_fallback=false`.

## Resource and request budget

* Web RSS: **1.65 GB** current, **1.87 GB** peak; web swap ~557 MB.
* One real recall sync with the new web process: **3:58**, peak RSS **1.956 GB**, 0 OOM.
* Host: 3,724 MB total; ~1.7 GB available after the sync; swap 1,987 MB with ~557 MB used.
* Data root: **146 MB**; final backup: ~146 MB; disk 59 GB, 49 GB free.
* Daily request usage: **359 / 900**; by source:
  510(k) 68, PMA 92, recall 157, classification 42.
* No `--allow-record-drop`, `--allow-degraded` or other lowering flag was used.

### Observed performance caveat

During the concurrent recall sync, one `/api/health` request timed out after 8 s while the web
process was swapping/reloading the new snapshot. The service recovered without restart; the
next health requests returned 200. There was no OOM, no 5xx, no data loss and no failed
publication. This is a real residual risk on a 3.7 GB host: web (~1.65–1.87 GB) plus a
single-source sync (~1.96 GB) is close to the RAM limit. The automatic scheduler still uses one
product source per run, and swap absorbs the transient. A follow-up memory optimization is
desirable; it was not attempted as an unapproved architecture change.

## Automatic timer evidence

* `medradar-data-update.timer` enabled, next **12:24:32 CST**.
* Systemd automatically started `medradar-data-update.service` at **11:20:22 CST**.
* Result: `status=NO_CHANGE`, exit code **0**, all four sources `SKIPPED_NOT_DUE`.
* `medradar-data-backup.timer` enabled, next **2026-11-17 03:23:16 CST**.
* Initial pipeline backups were run successfully at 11:20:49 and 11:28:41 CST; DB integrity
  `ok`, all six snapshots included.
* Existing CLOUD-003 `medradar-health.timer` continued to pass (`status=ok`) at 11:19 and 11:29.

## Backup / rollback

* Latest backup: `data-backup-20261116T032839Z-e5362d`, active snapshot `…032632…`,
  pipeline DB integrity `ok`, six snapshots.
* Restore into empty `/tmp/data002-prod-restore-final`: validation `true`, active snapshot
  `…032632…`; no production directory was modified by the restore.
* Production rollback A→B→A: active `…031623… → …031349… → …031623…`, then the final sync
  produced `…032632…`. Health followed the pointer each time.
* Old code rollback artifacts:
  `/srv/medradar/var/backup/data002-pre/app-1bdb1c3.tar.gz`,
  `package-snapshot/`, `medradar-web.service.before`; old SHA
  `1bdb1c349c59713e1a11426f15a6c06e892f87e0`.
* Old-code spot check: extracted the archive to `/tmp/medradar-old` and served the old
  `2026-11-14T22:09:22Z-openfda` snapshot on port 8789; `/` and `/api/health` returned 200,
  old status `ok`, version `2.0.0-product-002`. The process was stopped; production was not
  touched. Evidence: `evidence/old-code-rollback-check.txt`.

## Remaining risks

1. **Memory headroom is thin.** A concurrent sync caused a transient web stall; no OOM.
   The default one-source cap is retained.
2. **Same-host backup.** Not disaster recovery; no off-host copy was purchased.
3. **CLOUD-003 scripts unchanged.** The legacy health script still checks only HTTP 200; the
   layered adapter is installed/tested separately but not yet wired into monitoring.
4. **No long soak.** This report covers the first production run, not weeks of operation.
5. **No PR merge.** The branch remains Draft; the deployed SHA is fixed and documented.

## Rollback

If rollback is required:

1. `systemctl disable --now medradar-data-update.timer medradar-data-backup.timer`
2. restore `/etc/systemd/system/medradar-web.service` from
   `/srv/medradar/var/backup/data002-pre/medradar-web.service.before`
3. `git -C /srv/medradar/app checkout 1bdb1c349c59713e1a11426f15a6c06e892f87e0`
4. `systemctl daemon-reload && systemctl restart medradar-web.service`
5. old package snapshot remains at `/srv/medradar/app/medradar/product/snapshot`;
   `/srv/medradar/data/fda` is retained for inspection, not deleted.
