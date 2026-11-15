# DATA-001 — Operations

## First installation (after approval)

The pipeline is **not enabled by this pull request**. The production service was not
modified. The following is the deployment proposal that must be approved before execution.

```bash
# 1. Install the approved commit into a separate virtualenv or the existing app venv.
# 2. Choose the state root. The working deployment uses /srv/medradar/data.
sudo install -d -o medradar -g medradar -m 0750 /srv/medradar/data/fda

# 3. Bootstrap from the currently served immutable snapshot. This only reads the snapshot
#    and writes under the new state root; it does not change the live service.
sudo -u medradar env MEDRADAR_PIPELINE_ROOT=/srv/medradar/data/fda \
  MEDRADAR_REVIEW_DB=/srv/medradar/data/identity/review.db \
  /srv/medradar/.venv/bin/python -m medradar.data_pipeline bootstrap \
  --from /srv/medradar/app/medradar/product/snapshot --json

# 4. Run one real reconciliation in isolation and inspect the result before switching the
#    web process.
sudo -u medradar env MEDRADAR_PIPELINE_ROOT=/srv/medradar/data/fda \
  MEDRADAR_REVIEW_DB=/srv/medradar/data/identity/review.db \
  /srv/medradar/.venv/bin/python -m medradar.data_pipeline sync --force --json

# 5. Only after the candidate passes: update the service environment to
#    MEDRADAR_DATA_DIR=/srv/medradar/data/fda and restart once. Then install the timer.
```

The exact production change requires changing `medradar-web.service` to add:

```ini
Environment=MEDRADAR_DATA_DIR=/srv/medradar/data/fda
```

and installing the approved `medradar-data-update.timer`. This is deliberately a separate
approval from merging the code.

## Commands

```bash
python -m medradar.data_pipeline check --due --json
python -m medradar.data_pipeline check --sources openfda_recall --json
python -m medradar.data_pipeline run --json
python -m medradar.data_pipeline sync --sources openfda_recall --force --json
python -m medradar.data_pipeline status --json
python -m medradar.data_pipeline changes --type UPDATED --limit 50 --json
python -m medradar.data_pipeline rollback fda-snapshot-... --actor operator --json
python -m medradar.data_pipeline prune --keep 4 --json
```

`check` only probes versions. `sync` checks then collects. `run` is the scheduled entry point:
it checks only due sources and reconciles any source with an available update.

## Environment

| Variable | Default | Notes |
|---|---|---|
| `MEDRADAR_PIPELINE_ROOT` | `data/data_pipeline` | state root |
| `MEDRADAR_REVIEW_DB` | `data/identity/review.db` | read-only during validation |
| `MEDRADAR_OPENFDA_KEY_FILE` | unset | must not be group/world readable |
| `OPENFDA_API_KEY` | unset | alternative; never logged |
| `MEDRADAR_PIPELINE_DAILY_LIMIT` | 900 no key / 100000 key | persisted per UTC day |
| `MEDRADAR_OPENFDA_RPM` | 60 | polite client-side rate limit |
| `MEDRADAR_OPENFDA_TIMEOUT` | 90 | seconds |
| `MEDRADAR_OPENFDA_RETRIES` | 4 | 429/5xx/network attempts |
| `MEDRADAR_PIPELINE_RETENTION` | 4 | full snapshots kept |
| `MEDRADAR_PIPELINE_MIN_FREE_BYTES` | 2 GiB | sync refuses below this |
| `MEDRADAR_PIPELINE_MAX_DROP_RATIO` | 0.02 | record drop gate |
| `MEDRADAR_PIPELINE_REMOVAL_CONFIRMATIONS` | 2 | complete sweeps before removal |
| `MEDRADAR_PIPELINE_RECHECK_CAP` | 50 | exact-ID rechecks per run |

API key handling: the key is sent as HTTP Basic auth, not in the URL. It is not written to
the manifest, ledger, logs or status payload. `Settings` has `repr=False` on the key.
A leaked key must be rotated outside this system; the pipeline does not print it.

## systemd templates

The proposed units are `deploy/systemd/medradar-data-update.service` and `.timer`. They run
as `medradar`, with:

* `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes`;
* `ReadWritePaths=/srv/medradar/data`;
* `MemoryHigh=2200M`, `MemoryMax=2400M`, `CPUQuota=150%` (measured isolated recall peak
  was 1.98 GiB; the earlier 1800M template would have been too small);
* `Nice=10`, `IOSchedulingClass=idle`;
* `TimeoutStartSec=1h`;
* `EnvironmentFile=-/etc/medradar/pipeline.env` (mode 0600);
* `ExecStart` runs `run --json` and logs to the journal.

The code also holds a single `pipeline.lock`; a second sync cannot overlap.

## Failure handling

| Failure | Behavior |
|---|---|
| Probe timeout/429/5xx | `CHECK_FAILED`; retried hourly; old snapshot served |
| Three consecutive probe failures | `SOURCE_DEGRADED`; automatic sync blocked |
| Collection error in any org/page | run fails; staging removed; old snapshot served |
| Budget exhausted | run fails before the next request; old snapshot served |
| Disk below threshold | run refuses; old snapshot served |
| Candidate validation failure | `BLOCKED`; candidate path and issues logged; old snapshot served |
| Pointer/DB crash gap | next pipeline operation recovers from pointer |
| Web process dataset load failure | old in-memory dataset remains; a first-load failure returns 503 |
| Source total drop ≥5% | `SOURCE_DEGRADED`; operator must investigate |

Run `status --json` and `journalctl -u medradar-data-update` after an incident. The
`incidents` table stores validation and post-publication issues.

## Backup

The existing CLOUD-003 backup covers `/srv/medradar/data/identity` and the deploy record. The
pipeline adds `pipeline.db` and the active snapshot pointer. Back up:

* `/srv/medradar/data/fda/pipeline.db` (use SQLite `.backup` or stop the timer briefly);
* `/srv/medradar/data/fda/active.json`;
* the snapshot directory it points to (or retain at least two full snapshots);
* `/srv/medradar/data/identity/review.db` — already the CLOUD-003 backup target.

Do not delete the identity review database. It is independent of FDA snapshot retention.

## Monitoring

`GET /api/data-status` returns source states and the last successful sync. A scheduler health
check should alert when:

* any source is `CHECK_FAILED` or `SOURCE_DEGRADED`;
* `update_available=true` for more than one interval;
* no successful publication for more than 45 days (given monthly 510(k)/PMA updates);
* `request_usage_today.total_requests` is above 80% of the configured limit;
* free disk is below 5 GiB.

No alert channel is created by this task. The status API and the journal are the evidence
surface; the user must approve any external alert destination.

## Resource expectations

The real isolated run's measured elapsed time and peak RSS are in
`DELIVERY_REPORT.md` and `evidence/real-sync.json`. The service has 2 vCPU / 4 GB and about
2 GB available. The unit's `MemoryMax=1800M` leaves headroom for the web process. The
pipeline does not run more than one collection concurrently.
