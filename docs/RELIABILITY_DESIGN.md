# MedRadar Observatory Reliability — Architecture & Interface Contract (v1)

Status: binding for `feat/observatory-reliability-v1` (stacked on PR #13 head `5335dfd`).

Mission: the system must still be able to answer, years from now, **what MedRadar had
observed at a given past instant**. That requires durable storage, verified backups,
restorable snapshots, a supervised long-running collector, honest health reporting, an
append-only acquisition-phase classification, and a repeatable integrity audit.

No new predictors, no new data sources, no rewrite of the product. Reliability only.

---

## 0. Two status vocabularies that must never be conflated

| vocabulary | values | meaning |
|---|---|---|
| `deployment_status` | `NOT_DEPLOYED` · `DEPLOYED_LOCAL` · `DEPLOYED_SERVICE` | whether a durable supervised deployment exists. This branch **cannot** deploy to a paid host; after local verification the honest value is `DEPLOYED_LOCAL` and, unless a supervisor is actually installed and verified, `NOT_DEPLOYED` must be used for “service”. |
| `validation_status` | `VALIDATION_NOT_STARTED` · `VALIDATION_IN_PROGRESS` · `VALIDATION_PASSED` · `VALIDATION_FAILED` | the seven-day continuous observation experiment. A run of a few hours is always `VALIDATION_IN_PROGRESS`; **never** `PASSED`. |
| `health` | `OPERATIONAL` · `DEGRADED` · `PAUSED` · `NOT_DEPLOYED` · `VALIDATION_IN_PROGRESS` | per-source + overall health, derived from real signals (freshness, runs, backups, structure alerts), not from a 200 response. |

Overall health precedence (documented, tested): `NOT_DEPLOYED` (no supervisor/deployment
evidence) → `PAUSED` (explicit pause) → `DEGRADED` (any source failed/stale, backup
overdue/failed, unresolved structure alert) → `VALIDATION_IN_PROGRESS` (validation
running and otherwise healthy) → `OPERATIONAL` (deployed, healthy, validation passed).
The API also returns per-component details so a single green dot can never hide a
partial source failure.

---

## 1. Persistence architecture decision (P0)

### Options considered

| option | shape | monthly cost (order) | recovery | verdict |
|---|---|---|---|---|
| **A. Local persistent disk + automated offsite backup** | one small host/VM, SQLite, encrypted snapshots to S3-compatible object storage | host ~€4–7 + object storage ~€0–1 (<10 GB) | copy one file + verify manifest | **recommended** |
| B. small VPS + SQLite + object-storage backup | same as A with the host being a €4 VPS | ~€4–7 | same | **recommended host for A** |
| C. managed DB + object storage | managed Postgres/MySQL + evidence bucket | ≥€15–40, migration work | dump/restore, higher complexity | rejected for current scale |
| D. GitHub Actions cache/artifact as system of record | ephemeral runners + cache | €0 | cache eviction | **rejected** (already documented as not a system of record) |

### Decision: A hosted as a small Linux VM, i.e. **A + B**

SQLite remains the right engine at this scale (single writer, one file, transactional,
zero-ops). The durable layout:

```
/srv/medradar/                    # persistent disk (survives reboot)
  data/observatory/observatory.sqlite     # the ledger (system of record)
  data/observatory/cache/                 # raw HTTP responses (re-derivable evidence)
  data/prospective/                       # frozen prospective registry entries
  backups/                                # local staged backups (not the only copy)
  logs/                                   # collector logs (journald also captures)
```

Offsite copy: `observatory backup --dest backups --upload` (provider adapter is pluggable;
this round ships a local-directory target plus documented `rclone`/`restic`/S3 command
lines — no credentials are stored in Git and no paid resource is created without
authorization).

Cost estimate (2026 prices, order of magnitude): host €4–7/month (1 vCPU, 1–2 GB RAM,
20 GB SSD); object storage €0.15–0.60/month for the current <2 GB with 30–90 day
retention (or free tier); **total ≈ €5–8/month**. No managed database, no Kubernetes.

Growth: current ledger 1.7 MB / 400 observations; steady state ~30–80 observations/day
≈ 15–30 k/year ≈ 50–150 MB/year including versions. Raw response cache grows faster
(≈0.5–2 GB/year); it is **regenerable** and is pruned by policy while the ledger is
kept forever. Migration path at >2 GB or multi-writer needs: export `observation*`
tables to Parquet/Postgres read replica; not needed now.

Single point of failure: the host. Mitigated by daily offsite snapshots + restore drills
+ hash manifests. Data safety: backups optionally encrypted (age/restic); no secrets in
Git; SEC User-Agent contact comes from `MEDRADAR_SEC_UA` env (never committed).

### What this branch can honestly claim

No paid resource is created. The implementation is verified locally (real backup of the
real ledger, isolated restore drill) and a supervisor can be installed by the operator
with the provided templates. Therefore the report must say: **storage architecture
designed + local backups verified + restore drill passed; production deployment
`NOT_DEPLOYED` pending authorization** (host + object storage + credentials).

---

## 2. Backup & restore (P0) — module contract

Owner: `medradar/observatory/backup.py`, `medradar/observatory/restore.py`,
`scripts/observatory_backup_drill.py`, `tests/test_observatory_backup.py`,
`docs/BACKUP_AND_RECOVERY.md`.

Backup bundle layout (one directory per snapshot, atomic via temp dir + rename):

```
backups/observatory-YYYYMMDDTHHMMSSZ/
  ledger.sqlite                 # SQLite online-backup API snapshot (consistent, WAL-safe)
  MANIFEST.json                 # schema: name, created_at, size, sha256 per file,
                                # counts (observations/versions/changes/runs),
                                # ledger schema_version, integrity_check result,
                                # latest first_seen_at, source watermarks, tool versions
  raw-cache/                    # optional; only files referenced/needed, copied read-only
  prospective/                  # frozen registry snapshot (hashes only + files)
  README.txt                    # human-readable restore instructions
```

Requirements:
- consistency via `sqlite3.Connection.backup()` (never a raw file copy of a live WAL db);
- SHA-256 for every artifact, verified immediately after writing and again in `verify`;
- `PRAGMA integrity_check` + ledger `consistency_check()` recorded in the manifest;
- restore verifies manifest hashes before restoring, refuses on mismatch;
- restore never regenerates `first_seen_at` (it copies rows; a post-restore audit must
  prove identity with the manifest: counts, min/max `first_seen_at`, per-source
  observation counts, version/change counts, watermarks);
- retention: keep **7 daily** + **4 weekly** + **6 monthly** labels; `--prune` removes only
  bundles not covered by that policy, and **never** removes a bundle whose
  `MANIFEST.json` is missing/corrupt (quarantine instead);
- cache cleanup: raw cache older than `--cache-retention-days` (default 180) may be
  deleted only when the corresponding observation payload already exists in the ledger;
  prospective registry files and the ledger are never pruned;
- the last backup result is recorded in ledger `runtime_state` key `last_backup`
  (structure below) so the health panel can report it honestly.

`runtime_state["last_backup"]`:
```json
{"at":"ISO","status":"OK|FAILED","bundle":"observatory-...","path":"...","bytes":123,
 "sha256_manifest":"...","verified":true,"integrity_check":"ok","consistency_ok":true,
 "counts":{"observations":400,"versions":400,"changes":400},
 "cache_included":true,"retention":{"kept":8,"pruned":0},"duration_ms":1234,
 "error":null}
```

---

## 3. Supervised continuous operation (P0) — contract

Owner: `deploy/systemd/*`, `deploy/windows/*`, `scripts/install_*.ps1`,
`docs/DEPLOYMENT.md`; engine changes in `scheduler.py`/`runner.py` (Lead).

### Single-writer guarantee (Lead)

`medradar/observatory/lock.py` implements a lease file
`<ledger-dir>/collector.lock` (JSON: `pid, host, mode, run_id, started_at, heartbeat_at`):

- acquire atomically with `O_CREAT|O_EXCL`; if held: if owner pid is alive on this host
  **and** heartbeat is newer than `stale_after` (90 s) → refuse with a clear message;
  otherwise steal the lock and append a `runtime_state["lock_recovery"]` audit record;
- heartbeat updated during collection; released in `finally` and on SIGTERM/SIGINT;
- every write path (`sync`, `watch`, `validate start` probes) must hold the lock; the
  web app and read-only commands never take it;
- two collectors therefore cannot write the same ledger; concurrency tests must prove
  refusal, stale takeover and clean release.

### Service modes

| mode | how |
|---|---|
| Windows dev | `scripts/observatory_watch.ps1` + optional Task Scheduler registration (`scripts/install_windows_task.ps1`), `-Uninstall` to remove |
| Linux production | `deploy/systemd/medradar-observatory.service` (Restart=always, MemoryMax=512M, CPUQuota=50%, logs to journald) + `.timer` every 6 h (or long-running `watch` service) |
| manual one-shot | `python -m medradar observatory sync --trigger manual` |

Both supervisors set `MEDRADAR_DEPLOYMENT_STATUS=DEPLOYED_SERVICE` and
`MEDRADAR_DEPLOYMENT_INSTALLED_AT`; `observatory deploy-status` records them in
`runtime_state["deployment"]`. Logs: journald for systemd, rotating file
(`logs/collector-YYYYMMDD.log`) on Windows; `--log-file` option. Graceful stop: SIGTERM →
finish/mark current run, release lock, exit 0 (systemd `KillSignal=SIGTERM`,
`TimeoutStopSec=120`). Resource limits in the unit file; Windows job object is out of
scope (documented).

---

## 4. Seven-day continuous validation (P0) — contract

Owner: `medradar/observatory/validation.py` + `observatory validate …` CLI (Lead wires) +
`docs/CONTINUOUS_VALIDATION_PROTOCOL.md`.

Protocol `obs-validation-v1`:
- interval 6 h, target duration 7 days, expected slots = 28;
- `validation_started_at` is a real wall-clock moment stored in
  `runtime_state["validation"]`; it is **never** back-dated or fabricated;
- a slot counts as **executed** only if a `sync_run.started_at` falls inside
  `[slot_start − tolerance, slot_start + interval)`, where
  `tolerance = min(60 min, interval / 2)` so ordinary scheduler jitter is tolerated
  while one run can never satisfy two adjacent slots;
- scheduled vs executed vs succeeded vs partial vs failed vs missed are all reported;
  missed is never counted as success;
- metrics: scheduler success rate (ok/planned), per-source success rate (ok/attempts),
  observation freshness per source, measured collection latency (only where the source
  provides a real timestamp; otherwise “无法测量”), duplicate rate (must be 0),
  integrity violations (from audit + trigger counts; must be 0), recovery success
  (runs that resumed an interrupted run and then completed), storage growth
  (daily observation count + ledger bytes, recorded as ops metrics);
- status transitions only by explicit command (`validate stop` can set PASSED/FAILED
  only when the window actually ended and the numbers are computed from recorded runs);
- dashboard/health exposes `validation_status` and expected-vs-completed slots.

CLI: `observatory validate start [--days 7] [--interval-hours 6]`,
`observatory validate status [--json]`, `observatory validate stop --outcome passed|failed`.

---

## 5. Acquisition-phase classification (P1) — append-only, never rewrites rows

Owner: Lead (`ledger.py`, `adapter.py`, `runner.py`) + health/product owner for display.

New table (append-only, audited):

```sql
CREATE TABLE observation_phase (
  observation_id TEXT NOT NULL,
  phase          TEXT NOT NULL,   -- INITIAL_DISCOVERY | INCREMENTAL_DISCOVERY | HISTORICAL_BACKFILL
  assigned_at    TEXT NOT NULL,
  run_id         TEXT,
  method         TEXT NOT NULL,   -- collector_assigned | reconstructed_from_run_history
  note_zh        TEXT,
  PRIMARY KEY (observation_id, assigned_at)
);
```

- phase is assigned at observation time from the run context: `BACKFILLED` origin →
  `HISTORICAL_BACKFILL`; the source's first live successful run → `INITIAL_DISCOVERY`;
  later live runs → `INCREMENTAL_DISCOVERY`;
- the existing 400 observations get **new metadata rows** derived from
  `sync_run` history (`method=reconstructed_from_run_history`), never an UPDATE of the
  ledger rows;
- trigger blocks UPDATE/DELETE on `observation_phase`;
- API/UI: `phase` on each event + facet filter; summary splits initial vs incremental;
  the homepage block is labelled with the same distinction.

---

## 6. Observatory Health (P1) — contract

Owner: `medradar/observatory/health.py` (Lead-provided skeleton) + product/UI owner.

`health()` returns:

```json
{"generated_at":"ISO","overall":"OPERATIONAL|DEGRADED|PAUSED|NOT_DEPLOYED|VALIDATION_IN_PROGRESS",
 "deployment":{"status":"NOT_DEPLOYED|DEPLOYED_LOCAL|DEPLOYED_SERVICE","installed_at":null,"host":"...","supervisor":"none|systemd|windows_task"},
 "validation":{"status":"VALIDATION_IN_PROGRESS","started_at":"...","ends_at":"...","planned_slots":28,"completed_slots":3,"days_elapsed":0.1,"days_remaining":6.9},
 "collector":{"running":false,"lock":{"held":false,"mode":null,"pid":null,"heartbeat_age_seconds":null},"last_run_at":null,"uptime_days":0.0},
 "persistence":{"ledger_bytes":1699840,"raw_cache_bytes":0,"backup":{"at":null,"status":"NEVER","verified":false,"age_hours":null},"restore_drill":{"at":null,"status":"NEVER","ok":null}},
 "sources":[{"source":"sec_edgar","status":"OK|DEGRADED|FAILED|NEVER_RUN","last_success_at":"...","last_attempt_at":"...","consecutive_failures":0,"last_outcome":"NO_NEW_RECORDS","freshness_hours":1.2,"next_expected_at":"...","stale":false,"structure_alert":false}],
 "checks":[{"id":"freshness","ok":true,"detail":"..."}],
 "unresolved_structure_alerts":[],"limitations_zh":["..."]}
```

Health is computed from the ledger, filesystem and runtime_state only — never from a
plain HTTP 200. `overall` uses the precedence in §0 and the response exposes every
component so `DEGRADED` can point at the failing source.

---

## 7. Ledger integrity audit (P1) — contract

Owner: `medradar/observatory/audit.py`, tests `tests/test_observatory_audit.py`.

`python -m medradar observatory audit [--json] [--verbose]` produces a human-reviewable
report (Markdown/text + JSON) covering at least these checks, each with verdict
`PASS | FAIL | REQUIRES_MANUAL_REVIEW` and evidence details (never a naked PASS/FAIL):

1. duplicate observations per `(source, source_record_id)`;
2. `first_seen_at` integrity (first version captured at first_seen, first status history
   entry at first_seen, not modified after — trigger existence is also verified);
3. payload version chain (seq contiguous, hash chain, latest hash matches observation);
4. version ↔ change consistency (NEW/UPDATED rows, changed_fields match payload diff);
5. timestamp ordering (version captured_at monotonic, ≥ first_seen_at);
6. watermark safety (parseable; updated only at/after a successful run; scopes with
   failed pages not silently claimed complete → manual review when not decidable);
7. replay correctness (sample multi-version observations; `snapshot` before/after);
8. prospective registry freeze integrity (`verify_frozen` for every entry; none → manual);
9. mapping history preservation (≥1 mapping row per observation, latest row matches
   observation fields, no observation without mapping history);
10. backup/restore reproducibility (latest verified backup manifest vs live counts and
    first_seen min/max; missing backup/drill → `REQUIRES_MANUAL_REVIEW`, not PASS).

Overall: `FAIL` if any check fails; else `REQUIRES_MANUAL_REVIEW` if any check needs a
human; else `PASS`. Exit code 1 on FAIL, 0 otherwise (manual review is reported, not
hidden). Audit must be read-only.

---

## 8. File ownership (parallel work, disjoint scopes)

| path | owner |
|---|---|
| `medradar/observatory/{ledger,records,adapter,runner,scheduler,mapping,lag}.py` | **Lead** |
| `medradar/observatory/lock.py` | **Lead** |
| `medradar/observatory/{backup,restore}.py`, `scripts/observatory_backup_drill.py`, `tests/test_observatory_backup.py`, `docs/BACKUP_AND_RECOVERY.md` | **backup-recovery** |
| `deploy/**`, `scripts/observatory_watch.ps1`, `scripts/install_windows_task.ps1`, `scripts/uninstall_windows_task.ps1`, `docs/DEPLOYMENT.md`, `tests/test_observatory_deploy.py` | **deploy-runtime** |
| `medradar/observatory/{audit.py}`, `tests/test_observatory_audit.py` | **ledger-audit** |
| `medradar/observatory/health.py`, `medradar/observatory/validation.py`, `tests/test_observatory_health.py` | **health-validation** |
| `medradar/product/observatory.py`, `medradar/web/routes_observatory.py`, `web/js/pages/observatory.js`, `web/styles.css`, `web/js/pages/overview.js`, `tests/test_observatory_api.py` | **health-validation** (additive) |
| `medradar/__main__.py`, `medradar/web/app.py`, docs for design/validation/acceptance, PR | **Lead** |

Nobody runs git state-changing commands except the Lead. No paid resources, no secrets in
Git, no ledger committed, no merge of PR #12/#13.
