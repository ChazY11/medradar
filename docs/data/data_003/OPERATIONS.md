# DATA-003 — Operations guide

This is the day-2 guide for the version that includes DATA-003. Nothing here may be executed
against production without the approval in `DEPLOYMENT_CHANGE_REQUEST.md`.

## 1. Health: what to look at, in order

`/api/health` is the source of truth; the adapter (`deploy/scripts/medradar-health-v3.sh`,
proposal) prints one line and writes `/var/lib/medradar-health/last.json`.

Read the **layers**, not just the HTTP code:

| Field | Meaning | Alarm when |
|---|---|---|
| `checks.readiness.state` | a validated dataset exists | `not_ready` → critical |
| `checks.data.state` | `available` / `degraded` (serving the previous dataset) | `degraded` → warn |
| `checks.data.using_fallback` | a new snapshot failed to load; old data is served | `true` → warn |
| `checks.activation.state` | `ok` / `loading` / `degraded` (deferred or failed) | `degraded` → warn |
| `activation.phase`, `activation.progress` | where the activation is (`events 20000/…`) | no progress for > 15 min → investigate |
| `checks.sync.state` / `sync.deferral` | pipeline state; `deferred` includes the guard reasons | `deferred` > 3 consecutive runs → warn |
| `checks.freshness.state` | source version age | `degraded`/`stale` → warn |
| `checks.liveness.state` | the process answers | never; use `livez` |

Rules of thumb:

* HTTP 200 with `status=degraded` is **not** healthy. The v2 adapter treated 200 as a pass;
  v3 uses exit 1 for degraded/deferred and exit 2 for not-ready.
* `deferred` is not `failed`. It means the host guard refused to start; the data is intact and
  the next run retries.
* An official FDA version that has not changed is **not** an alert. Only a failed check, a
  deferred run, or a stale *pending* update is.

## 2. Daily (2 minutes)

```bash
# 1. service + timers
systemctl status medradar-web --no-pager
systemctl list-timers 'medradar-*' --no-pager

# 2. layered health (the adapter installs the same data to /var/lib/medradar-health/last.json)
curl -s http://127.0.0.1:8787/api/health | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["status"], d["checks"]["data"], d["checks"]["activation"], d["checks"]["sync"])'

# 3. memory that actually matters
cat /sys/fs/cgroup/system.slice/medradar-web.service/memory.current \
    /sys/fs/cgroup/system.slice/medradar-web.service/memory.peak
grep -E 'MemAvailable|SwapFree' /proc/meminfo
cat /proc/pressure/memory

# 4. last runs and deferrals
curl -s http://127.0.0.1:8787/api/data-status | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["state"], d["synchronization"]["state"], d["synchronization"].get("deferral"), d["dataset_activation"]["state"], d["dataset_activation"].get("elapsed_s"))'
```

Watch `memory.peak`, not only `memory.current`: the peak is where the double-buffer used to
show up. The expected post-DATA-003 shape on production is a steady state of roughly
0.4–0.7 GB and a peak below ~1.2 GB (measure and record the real numbers in the deployment
report; the Windows probe is not a production measurement).

## 3. Weekly (10 minutes)

1. `pipeline.repository` growth: `du -sh /srv/medradar/data/fda /srv/medradar/var/backup`.
2. Backup presence + newest restore drill (see §6).
3. Deferral count over the week: `curl /api/data-status | … recent_runs` — more than a few
   `DEFERRED` rows means the host budget is too tight for the current traffic.
4. `journalctl -u medradar-web --since '7 days ago' | grep -iE 'error|timeout'`.
5. `curl -s -o /dev/null -w '%{time_total}\n' http://127.0.0.1:8787/api/data-status` a few
   times; it should stay in the tens of milliseconds when the service is idle.

## 4. Tuning the guards

The knobs and their calibration are in `RESOURCE_GUARDS.md`. To change them:

```bash
sudoedit /etc/medradar/pipeline.env        # MEDRADAR_PIPELINE_MIN_AVAILABLE_MB=...
sudo systemctl daemon-reload               # EnvironmentFile is read per run; reload is enough
```

Web activation thresholds are code constants (`ACTIVATION_GUARD` in
`medradar/product/resources.py`); changing them is a code change, not an env change. The guard
can be disabled at runtime for diagnosis with `DatasetHolder.guard_enabled = False` (a Python
session on the loopback app), which is deliberately not exposed over HTTP.

**Never** "fix" memory pressure by:
* killing the web or pipeline on a timer;
* lowering validation (record-drop / degraded flags);
* raising the pipeline's `MemoryMax` above the host budget;
* deleting old snapshots that have not been restored-verified.

## 5. Snapshot activation and rollback

* Publish a new snapshot with the pipeline (normal path); the web activates it on the next
  request after the pointer changes (`activation.state=loading`, then `ok`).
* If activation stays `deferred`, read `activation.guard.reasons` and
  `activation.pending_snapshot`. Free headroom or wait; do not force it.
* If activation is `failed`, the old snapshot is still serving. `activation.last_error` has the
  reason. The pipeline can `rollback <previous-snapshot-id>` to make the pointer consistent.
* `dataset_activation.last_activated_snapshot` records the last successful switch, so "which
  snapshot did the web actually load?" has an explicit answer.

## 6. Backups (reviewed 2026-11-17)

Two independent timers exist; they do not overlap:

| Timer | Schedule | Unit | Contents | Retention |
|---|---|---|---|---|
| `medradar-data-backup.timer` (DATA-002) | daily 03:20 + up to 10 min jitter | `medradar-data-backup.service` (MemoryMax 768 M, CPUQuota 50 %) | `active.json`, consistent `pipeline.db` (SQLite online backup), **all** snapshot dirs, `review.db` if present, `backup.json` manifest with SHA-256 per file | **none** |
| `medradar-backup.timer` (CLOUD-003) | daily 04:30 | `medradar-backup.service` | tar of `data/identity`, `data/cache`, `var/DEPLOYED_SHA` + manifest | 7 archives |

Findings:

1. **No duplication of the heavy data** — CLOUD-003 backs up identity/cache only; DATA-002 backs
   up the pipeline state. Together they cover everything, with one overlap on `data/identity`
   (tiny).
2. **No schedule collision.** 03:20 (+10 min) and 04:30 are an hour apart. Measured backup cost:
   1.1 s CPU and a ~146 MB copy, so contention with the hourly update timer is possible if the
   update run is long (a recall sync is ~7 min); the backup unit holds the pipeline lock, so it
   waits rather than races.
3. **The latest pipeline DB is included correctly** (`StateStore` SQLite backup API, integrity
   checked by `restore`). A restore into an isolated directory was verified in DATA-002.
4. **Unbounded growth risk (real).** One backup is ~146 MB (six snapshots + a 31 MB DB), daily.
   With 49 GB free that is ~11 months of headroom, and nothing prunes it. DATA-003 adds a safe,
   explicit command:

   ```bash
   python -m medradar.data_pipeline prune-backups --destination /srv/medradar/var/backup/data --keep 7
   # dry run: lists what would be removed and how much it would free
   python -m medradar.data_pipeline prune-backups --destination /srv/medradar/var/backup/data --keep 7 --apply
   ```

   It only removes `data-backup-*` directories that have a valid `backup.json`, keeps the newest
   `--keep`, and refuses to touch anything else. It is a dry run by default. Schedule it only
   after a restore from the newest backup has been verified.
5. **Same-host only.** Neither backup survives loss of the instance or the cloud volume. This is
   documented, not fixed by DATA-003 (no off-host copy was purchased).

## 7. Emergency procedures (each needs approval)

| Situation | Safe action |
|---|---|
| Web RSS keeps climbing across many switches | restart `medradar-web` (clears allocator high-water); capture `memory.peak` first |
| Repeated activation failures | `pipeline rollback <last-good-snapshot>`; keep the failed snapshot for inspection |
| Pipeline consistently deferred | check `MemAvailable`/`SwapFree`/PSI; raise `MEDRADAR_PIPELINE_MIN_AVAILABLE_MB` is *not* the fix — find what is holding memory |
| Host OOM risk | stop the pipeline timer (not the web); do not touch the web's data |
| Disk nearly full | `prune-backups` dry run, verify newest restore, then `--apply`; `pipeline prune --keep N` for snapshots (keeps the change ledger) |

## 8. Re-calibration (after one week of real data)

Collect, for 7 days: `memory.peak` (web + pipeline), `MemAvailable` min, `SwapFree` min,
PSI `some` max, count of `DEFERRED` runs, count of `activation.state=deferred`, activation
`elapsed_s`.

Decision rules:

* **No defers, peak < 80 % of RAM** → relax nothing; keep the guard as a safety net.
* **Defers because `mem_available_below_floor` but the host was idle** → lower
  `MEDRADAR_PIPELINE_MIN_AVAILABLE_MB` by 200 and observe for a week.
* **Activation deferred regularly while idle** → the floor is too high; adjust
  `ACTIVATION_GUARD.min_available_mb` in code.
* **PSI `some` > 10 % for minutes** → the host is genuinely over-committed; the correct fix is
  a resource upgrade or moving the pipeline off-host, not a bigger `MemoryMax`.
