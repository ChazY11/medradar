# DATA-003 — Production change request (Correction-1)

**Status: REQUESTED. Not executed. Every step below requires explicit approval.**
**Revision:** Correction-1 (2026-11-17). Fixes the repository path, the rollback SHA, the
hard-coded snapshot, the loopback assumption and the index/activation consistency rule.

| Item | Value (verified read-only on the host, 2026-11-17 03:2x CST) |
|---|---|
| Production code | `/srv/medradar/app` @ `bb1ef34df3c15e2b1339432abce899eebea5e1f6` (git status clean) |
| Python environment | `/srv/medradar/.venv` (Python 3.12.3) with an **editable install** whose `.pth` finder points at `/srv/medradar/app`; `import medradar` resolves to `/srv/medradar/app/medradar/__init__.py` |
| Service | `medradar-web.service`, `WorkingDirectory=/srv/medradar`, `MEDRADAR_DATA_DIR=/srv/medradar/data/fda`, listens **127.0.0.1:8787 only** |
| Public exposure | **none for MedRadar**: `ss -ltnp` shows 8787 on loopback; no reverse-proxy config references it. SSH is the only public listener changed by nobody here. Do **not** assume a proxy. |
| Active snapshot | read at execution time into `$SNAPSHOT_ID` (see §2) — not hard-coded |
| Proposed code | branch `feat/data-003-runtime-reliability`, Correction-1 commit `7415382df8d449194557a440cf9a869da3b25c59` (PR #52; later docs-only commits do not change code) |
| Rollback target | **`bb1ef34df3c15e2b1339432abce899eebea5e1f6`** (the actual deployed SHA) |
| Data | unchanged; no migration; snapshots and ledger untouched |

## 1. What changes

| # | Change | Risk |
|---|---|---|
| 1 | `git -C /srv/medradar/app checkout <Correction-1 SHA>` (the editable install makes the new code live immediately; **no `pip install` needed** — dependencies and packaging are unchanged) | low |
| 2 | `systemctl restart medradar-web.service` (the only interruption) | low: loopback only, ~15 s until ready |
| 3 | Add the DATA-003 guard variables to `/etc/medradar/pipeline.env` (defaults already exist in code; explicit is better) | low |
| 4 | Update `/srv/medradar/var/DEPLOYED_SHA` (currently still records the CLOUD-003 SHA `1bdb1c3…`, which predates DATA-002) | low, bookkeeping |
| 5 | *(optional, separate approval)* install `deploy/scripts/medradar-health-v3.sh` | low |
| 6 | *(optional, separate approval)* schedule `prune-backups --keep 7` after a verified restore | low, deletes backups |

Not changed: SSH, firewall, ports, timers' schedules, snapshots, review ledger, backup scripts
(unless #6), unit limits.

## 2. Pre-flight (read-only, 10 minutes)

```bash
# 0. facts, recorded in the deployment log
sudo -u medradar git -C /srv/medradar/app rev-parse HEAD          # expect bb1ef34…
sudo -u medradar git -C /srv/medradar/app status --porcelain      # expect empty
SNAPSHOT_ID=$(curl -s http://127.0.0.1:8787/api/readyz \
  | python3 -c 'import json,sys; print((json.load(sys.stdin).get("snapshot") or {}).get("id",""))')
PREVIOUS_ID=$(curl -s http://127.0.0.1:8787/api/readyz \
  | python3 -c 'import json,sys; print((json.load(sys.stdin).get("snapshot") or {}).get("previous_snapshot_id",""))')
echo "active=$SNAPSHOT_ID previous=$PREVIOUS_ID"
sudo ss -ltnp | grep -E '8787|8080|:22'                          # confirm 8787 is loopback-only
systemctl status medradar-web --no-pager
sudo -u medradar git -C /srv/medradar/app ls-remote origin feat/data-003-runtime-reliability
cat /sys/fs/cgroup/system.slice/medradar-web.service/memory.current \
    /sys/fs/cgroup/system.slice/medradar-web.service/memory.peak
free -m; cat /proc/pressure/memory; df -h /

# 1. a fresh backup and an isolated restore verification (never into production)
sudo systemctl start medradar-data-backup.service
# then: python -m medradar.data_pipeline restore --archive <newest> --destination /tmp/d3-restore-check
# verify validation=true, then delete /tmp/d3-restore-check
```

Proceed only if: git is clean at `bb1ef34…`, `$SNAPSHOT_ID` is non-empty, `/srv/medradar` has
≥ 10 GB free, and the newest backup restores.

## 3. Execution

```bash
# 1. record the pre-change evidence
sudo -u medradar git -C /srv/medradar/app rev-parse HEAD | tee /tmp/data003-pre-sha.txt
curl -s http://127.0.0.1:8787/api/health > /tmp/data003-pre-health.json
curl -s http://127.0.0.1:8787/api/data-status > /tmp/data003-pre-data-status.json

# 2. deploy the fixed SHA (editable install: no pip step; dependencies unchanged)
sudo -u medradar git -C /srv/medradar/app fetch origin feat/data-003-runtime-reliability
sudo -u medradar git -C /srv/medradar/app checkout 7415382df8d449194557a440cf9a869da3b25c59
sudo -u medradar git -C /srv/medradar/app rev-parse HEAD            # equals 7415382df8d449194557a440cf9a869da3b25c59
sudo -u medradar /srv/medradar/.venv/bin/python -c "import medradar.product.api as a; print(a.__file__)"
# expect /srv/medradar/app/medradar/product/api.py

# 3. guard settings (defaults shown; no behaviour change vs code defaults)
sudoedit /etc/medradar/pipeline.env
# MEDRADAR_PIPELINE_RESOURCE_GUARD=1
# MEDRADAR_PIPELINE_MIN_AVAILABLE_MB=1200
# MEDRADAR_PIPELINE_MIN_SWAP_FREE_MB=384
# MEDRADAR_PIPELINE_MAX_PSI_SOME=8.0
# MEDRADAR_PIPELINE_MIN_DISK_FREE_MB=2048

# 4. restart the web (the only service interruption)
sudo systemctl restart medradar-web.service
# Cold start now loads the dataset AND builds the device index before it publishes the
# dataset: expect ~15 s on this host (9 s load + 5.4 s index). livez answers immediately,
# readyz is 503 until both are done. ExecStartPost already polls /api/devices for 20 s.
for i in $(seq 1 60); do curl -sf -o /dev/null http://127.0.0.1:8787/api/readyz && break; sleep 1; done
```

Expected interruption: the loopback listener restarts; there is **no configured public
reverse proxy**, so there is no public 502 window to describe. Clients that reach the service
(operators, local tooling) see connection refused for a few seconds and 503 on `readyz` until
the dataset is published.

## 4. Post-change verification (all must pass before closing)

```bash
# 1. code, service, memory
sudo -u medradar git -C /srv/medradar/app rev-parse HEAD
systemctl show medradar-web -p NRestarts -p MemoryCurrent -p MemoryPeak
curl -s http://127.0.0.1:8787/api/health | python3 -m json.tool | head -40

# 2. activation is complete: data AND index published together (Correction-1)
SNAPSHOT_NOW=$(curl -s http://127.0.0.1:8787/api/readyz \
  | python3 -c 'import json,sys; print((json.load(sys.stdin).get("snapshot") or {}).get("id",""))')
curl -s http://127.0.0.1:8787/api/health | python3 - <<'PY'
import json, sys
h = json.load(sys.stdin)
a = h.get("activation") or {}
print("status", h["status"], "snapshot", (h.get("snapshot") or {}).get("id"))
print("activation", a.get("state"), "index_ready", a.get("index_ready"),
      "build_ms", a.get("last_activated_snapshot"))
print("checks", {k: v.get("state") for k, v in h["checks"].items()})
PY
curl -s http://127.0.0.1:8787/api/devices/quality \
  | python3 -c 'import json,sys; q=json.load(sys.stdin); print("quality snapshot", (q.get("snapshot") or {}).get("id"), "index_build_ms", q.get("index_build_ms"))'
# the two snapshot ids must be identical; index_build_ms must be non-null

# 3. memory after restart and after one forced activation of the previous real snapshot
#    (only if $PREVIOUS_ID is non-empty and the file exists)
python3 -m medradar.data_pipeline rollback "$PREVIOUS_ID" --json
# wait for /api/health activation.state == idle, then switch back to "$SNAPSHOT_ID":
python3 -m medradar.data_pipeline rollback "$SNAPSHOT_NOW" --json

# 4. latency with the service idle
for p in /api/health /api/data-status /api/organizations "/api/events?page_size=25"; do
  curl -s -o /dev/null -w "$p %{http_code} %{time_total}\n" "http://127.0.0.1:8787$p"
done

# 5. one real guarded sync (DEFERRED is an acceptable, recorded outcome)
sudo systemctl start medradar-data-update.service
journalctl -u medradar-data-update.service --since '-5 min' --no-pager | tail -25

# 6. bookkeeping
printf 'sha=%s\nbranch=feat/data-003-runtime-reliability\ndeployed_at=%s\nsnapshot=%s\n' \
  "$(sudo -u medradar git -C /srv/medradar/app rev-parse HEAD)" \
  "$(date -Is)" "$SNAPSHOT_NOW" | sudo tee /srv/medradar/var/DEPLOYED_SHA
```

Record at minimum:

| Metric | Expected | Observed |
|---|---|---|
| `memory.current` after restart + one activation | ≤ 1.2 GB (target 0.4–0.8 GB) | — |
| `memory.peak` | < 1.5 GB (target < 1.0 GB) | — |
| `/api/health` status | `ok`, `using_fallback=false` | — |
| `activation.index_ready` | `true` | — |
| `/api/devices/quality.snapshot.id` | equals `/api/readyz` snapshot id | — |
| `/api/health` latency idle | < 100 ms | — |
| activation of the previous snapshot | `state=ok`, no request failure | — |
| sync state | `ok` or `deferred` with reason | — |
| OOM / 5xx in the window | none | — |

**If `memory.current` does not fall materially below the pre-change 1.6 GB, roll back.** A
successful deployment is not defined by the code being on disk.

## 5. Rollback (15 minutes, no data migration)

```bash
# code
sudo -u medradar git -C /srv/medradar/app checkout bb1ef34df3c15e2b1339432abce899eebea5e1f6
sudo -u medradar git -C /srv/medradar/app rev-parse HEAD      # equals bb1ef34…
sudo systemctl restart medradar-web.service
# the editable install follows /srv/medradar/app automatically; no pip step
# bookkeeping
printf 'sha=%s\nbranch=feat/data-002-production-readiness\nrolled_back_at=%s\n' \
  bb1ef34df3c15e2b1339432abce899eebea5e1f6 "$(date -Is)" | sudo tee /srv/medradar/var/DEPLOYED_SHA
```

Snapshot schema, pipeline DB schema and all data are unchanged, so a code rollback is complete
on its own. `/srv/medradar/data/fda` and the backups are not touched.

## 6. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Cold start slower (index is now built before publishing) | certain, ~+5 s | `ExecStartPost` polls 20 s; `livez` is immediate; monitor `readyz` |
| Activation fails on the new code | low (same loader + index builder, fingerprint-identical) | old dataset keeps serving; rollback SHA; the failed snapshot stays for inspection |
| Guard thresholds defer syncs too often | medium | env-tunable, watch one week, recalibrate (`OPERATIONS.md` §8) |
| Activation slower under heavy CPU load | medium | documented; requests are never blocked by the loader; the guard prevents overlap with a sync |
| `DEPLOYED_SHA` stale (was `1bdb1c3…`) | certain until step 6 | step 6 rewrites it |

## 7. Approval

* [ ] Deploy commit `7415382df8d449194557a440cf9a869da3b25c59` on PR #52 and restart `medradar-web` (loopback only).
* [ ] Add the guard variables to `/etc/medradar/pipeline.env`.
* [ ] Update `/srv/medradar/var/DEPLOYED_SHA`.
* [ ] *(separate)* install the health adapter.
* [ ] *(separate)* enable backup pruning after a verified restore.

Nothing in this document has been executed. Production remains at
`bb1ef34df3c15e2b1339432abce899eebea5e1f6`, snapshot read dynamically at execution time.
