# DATA-003 — Production change request

**Status: REQUESTED. Not executed. Every step below requires explicit approval.**

| Item | Value |
|---|---|
| Current production code | `bb1ef34df3c15e2b1339432abce899eebea5e1f6` (deployed under DATA-002; git tip of that branch `edbde0a`) |
| Proposed code | branch `feat/data-003-runtime-reliability`, commit recorded in Draft PR #52 |
| Active snapshot at request time | `fda-snapshot-20261116T032632Z-18ce4d0cbbe4` |
| Host | Tencent Lighthouse, Ubuntu 24.04, 2 vCPU, 3.72 GiB RAM, 1.99 GiB swap |
| Rollback code | `edbde0a` / the archived `app-1bdb1c3.tar.gz` already on the host |
| PR merge | **not requested**; this is a fixed-SHA deployment like DATA-002 |

## 1. What changes

| # | Change | Risk |
|---|---|---|
| 1 | Replace the application code with the DATA-003 SHA (dataset representation, activation path, resource guards, additive health fields) | medium: process restart |
| 2 | Add DATA-003 guard variables to `/etc/medradar/pipeline.env` (defaults are already in code; the file makes them explicit and tunable) | low |
| 3 | **Restart `medradar-web.service`** so the new code is loaded | low: ~10 s of 503/connection refusals during cold load |
| 4 | *(optional)* install `deploy/scripts/medradar-health-v3.sh` as `/usr/local/bin/medradar-health` | low: read-only adapter |
| 5 | *(optional)* schedule a weekly `prune-backups --keep 7` after a verified restore | low, but it deletes backups — explicit approval needed |

Not changed: SSH, firewall, ports, timers' schedules, data snapshots, review ledger, backup
scripts (unless #5), systemd unit limits.

## 2. Pre-flight (read-only, 10 min)

```bash
# a. current state
systemctl status medradar-web --no-pager
curl -s http://127.0.0.1:8787/api/health | python3 -m json.tool | head -40
cat /sys/fs/cgroup/system.slice/medradar-web.service/memory.current \
    /sys/fs/cgroup/system.slice/medradar-web.service/memory.peak
free -m; cat /proc/pressure/memory; df -h /

# b. a fresh backup and an isolated restore verification (never into production)
sudo systemctl start medradar-data-backup.service
python3 -m medradar.data_pipeline backup --destination /srv/medradar/var/backup/data --json   # via the unit
# restore drill into a scratch directory, then delete the scratch copy
```

Acceptance to proceed: health `ok`, `memory.peak` recorded, ≥10 GB disk free, newest backup
restores with `validation=true`.

## 3. Execution

```bash
# 1. record the pre-change evidence
sudo -u medradar git -C /srv/medradar rev-parse HEAD
curl -s http://127.0.0.1:8787/api/data-status > /tmp/data003-pre-data-status.json

# 2. deploy the fixed SHA (same mechanics as DATA-002; no PR merge)
sudo -u medradar git -C /srv/medradar fetch origin feat/data-003-runtime-reliability
sudo -u medradar git -C /srv/medradar checkout <DATA-003_SHA>
sudo -u medradar /srv/medradar/.venv/bin/pip install -e /srv/medradar --no-deps   # if packaging changed

# 3. add guard settings (defaults shown; no behaviour change vs code defaults)
sudoedit /etc/medradar/pipeline.env
# MEDRADAR_PIPELINE_RESOURCE_GUARD=1
# MEDRADAR_PIPELINE_MIN_AVAILABLE_MB=1200
# MEDRADAR_PIPELINE_MIN_SWAP_FREE_MB=384
# MEDRADAR_PIPELINE_MAX_PSI_SOME=8.0
# MEDRADAR_PIPELINE_MIN_DISK_FREE_MB=2048

# 4. restart the web (the only service interruption)
sudo systemctl restart medradar-web.service
# cold load is ~8-15 s on this host; livez answers immediately, readyz is 503 until loaded
for i in $(seq 1 60); do curl -sf -o /dev/null http://127.0.0.1:8787/api/readyz && break; sleep 1; done
```

Expected downtime: **10–20 s** (process restart + one cold dataset load). Port 8787 is
loopback-only; the public entry point is the existing reverse proxy, which returns 502 during
that window.

## 4. Post-change verification (must all pass before closing)

```bash
# 1. service and snapshot
systemctl show medradar-web -p NRestarts -p MemoryCurrent -p MemoryPeak
curl -s http://127.0.0.1:8787/api/health | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["status"], d["checks"]["activation"], d["snapshot"]["id"])'
curl -s http://127.0.0.1:8787/api/data-status | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["state"], d["dataset_activation"])'

# 2. memory after the restart and after one forced activation
#    (switch to the previous real snapshot and back, as in the DATA-002 rollback test)
python3 -m medradar.data_pipeline rollback fda-snapshot-20261116T031623Z-556883ca1bc7 --json
# wait for activation, read /api/health, then:
python3 -m medradar.data_pipeline rollback fda-snapshot-20261116T032632Z-18ce4d0cbbe4 --json

# 3. latency with the service idle
for p in /api/health /api/data-status /api/organizations /api/events?page_size=25; do
  curl -s -o /dev/null -w "$p %{http_code} %{time_total}\n" "http://127.0.0.1:8787$p"
done

# 4. one real guarded sync (it will be DEFERRED if the host is busy; both are acceptable)
sudo systemctl start medradar-data-update.service
journalctl -u medradar-data-update.service --since '-5 min' --no-pager | tail -20
```

Record at minimum:

| Metric | Expected | Actually observed |
|---|---|---|
| web `memory.current` after restart + one activation | ≤ 1.2 GB (target 0.4–0.8 GB) | — |
| web `memory.peak` | < 1.5 GB (target < 1.0 GB) | — |
| `/api/health` status | `ok` (`using_fallback=false`) | — |
| `/api/health` latency | < 100 ms idle | — |
| activation of the previous snapshot | completes, `state=ok`, no request failure | — |
| `data-status.synchronization.state` | `ok` or `deferred` with a reason here: | — |
| OOM / 5xx during the window | none | — |

**If `memory.current` is not materially below the pre-change 1.6 GB, stop and roll back**: the
expected win did not materialise and the deployment should not be kept on optimism.

## 5. Rollback (15 min, no data migration)

```bash
sudo systemctl disable --now medradar-data-update.timer      # if the new guard causes defers
sudo -u medradar git -C /srv/medradar checkout edbde0a
sudo systemctl restart medradar-web.service
# optional: restore the pre-change unit file
#   /srv/medradar/var/backup/data002-pre/medradar-web.service.before
```

The snapshot schema and the pipeline DB schema are unchanged, so no data rollback is needed.
`/srv/medradar/data/fda` and the backups remain untouched by the code change.

## 6. Optional: health adapter and backup retention

* Install `medradar-health-v3.sh` only after it has been run side by side on the host for a day
  (`bash /path/to/medradar-health-v3.sh; cat /var/lib/medradar-health/last.json`) and compared
  with the current script. It exits 0 to keep the timer quiet; the *status line* carries the
  severity.
* Backup retention: `prune-backups --keep 7` is a dry run. **Before** adding `--apply` to any
  schedule, restore the newest backup into a scratch directory and verify it. Expected reclaim:
  ~146 MB per removed backup; keeping 7 caps the pipeline backup set at ~1 GB.

## 7. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Cold load fails on the new code | low (same loader, fingerprint-identical output) | rollback SHA; the old package snapshot is retained |
| Restart at a busy moment | low | perform at the same quiet window used by DATA-002 (early morning UTC+8) |
| Guard thresholds defer syncs too often | medium | thresholds are env-tunable; watch one week and re-calibrate (`OPERATIONS.md` §8) |
| Activation latency under load | medium | documented; requests are not blocked; monitor `activation.elapsed_s` |
| Health adapter mis-reports | low | it is optional and separate from the web deploy |

## 8. Approval

* [ ] User approves deploying commit `<DATA-003_SHA>` and restarting `medradar-web`.
* [ ] User approves adding the guard variables to `/etc/medradar/pipeline.env`.
* [ ] User approves (separately) installing the health adapter.
* [ ] User approves (separately) enabling backup pruning after a verified restore.

No step in this document has been executed. Production remains on `bb1ef34` / `edbde0a`
semantics with the DATA-002 deployment records intact.
