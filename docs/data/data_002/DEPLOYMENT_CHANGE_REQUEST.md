# DATA-002 — Production Change Request

**Status: NOT APPROVED — DO NOT EXECUTE YET.**

This is the concrete request. The engineering work, offline tests and isolated server tests are
done first; the listed production mutations require an explicit approval naming this change
request and the fixed SHA.

## Fixed deployment identity

| Item | Value |
|---|---|
| Repository | `ChazY11/medradar` |
| DATA-002 branch | `feat/data-002-production-readiness` |
| Draft PR | https://github.com/ChazY11/medradar/pull/51 |
| Base | `feat/data-001-continuous-pipeline` (stacked; PR #50 remains Draft) |
| Fixed SHA to deploy | `bb1ef34df3c15e2b1339432abce899eebea5e1f6` |
| Current production SHA | `1bdb1c349c59713e1a11426f15a6c06e892f87e0` |
| Current production snapshot | `2026-11-14T22:09:22Z-openfda` |
| Target pipeline root | `/srv/medradar/data/fda` |
| Target review DB | `/srv/medradar/data/identity/review.db` (create as needed, never delete) |
| Target backup root | `/srv/medradar/var/backup/data` |
| Timer | hourly `medradar-data-update.timer` |

## Approval requested for

1. Deploy the fixed SHA into `/srv/medradar/app`.
2. Create `/srv/medradar/data/fda` owned by `medradar:medradar`, mode 0750.
3. Bootstrap the production pipeline from the existing package snapshot.
4. Run the first scoped production reconciliation(s).
5. Add `MEDRADAR_DATA_DIR=/srv/medradar/data/fda` to `medradar-web.service`.
6. Restart the web service and switch the active pointer.
7. Install/enable the hourly update timer.
8. Add the new pipeline backup timer and (separately) replace the health adapter with
   `deploy/scripts/medradar-health-v2.sh`.
9. Keep the old package snapshot and old code SHA as the rollback target.

The current `/usr/local/bin/medradar-health` and `/usr/local/bin/medradar-backup` are **not**
overwritten by this change. Their replacement is a follow-up after the new endpoints/backup
have been observed.

## Stage 1 — code only, old data continues

```bash
sudo -u medradar git -C /srv/medradar/app fetch origin
sudo -u medradar git -C /srv/medradar/app checkout bb1ef34df3c15e2b1339432abce899eebea5e1f6
sudo -u medradar /srv/medradar/.venv/bin/pip install -e /srv/medradar/app
sudo systemctl restart medradar-web.service
curl -fsS http://127.0.0.1:8787/api/livez
curl -fsS http://127.0.0.1:8787/api/health
```

At this point the old package snapshot must still be served. Abort and restore the old SHA if
`/api/health` is not readable.

## Stage 2 — create and bootstrap the production state

```bash
sudo install -d -o medradar -g medradar -m 0750 /srv/medradar/data/fda
sudo -u medradar env \
  MEDRADAR_PIPELINE_ROOT=/srv/medradar/data/fda \
  MEDRADAR_REVIEW_DB=/srv/medradar/data/identity/review.db \
  /srv/medradar/.venv/bin/python -m medradar.data_pipeline bootstrap \
  --from /srv/medradar/app/medradar/product/snapshot --json
```

Expected: a new immutable snapshot, `active.json`, and `pipeline.db` under the new root; 91,457
baseline records; zero fabricated ADDED rows. The web service still serves the package snapshot.

## Stage 3 — source reconciliation

Run one source at a time (the CLI caps are explicit; do not use an all-source `sync` on this
host):

```bash
for source in openfda_510k openfda_pma openfda_recall; do
  sudo -u medradar env \
    MEDRADAR_PIPELINE_ROOT=/srv/medradar/data/fda \
    MEDRADAR_REVIEW_DB=/srv/medradar/data/identity/review.db \
    /srv/medradar/.venv/bin/python -m medradar.data_pipeline sync \
    --sources "$source" --force --json
done
```

Capture for each: official version, requests, records, added/updated/removed, peak RSS and
validation result. A failed source must be reported as failed; do not retry with `--allow-record-drop`
unless a human has reviewed the drop.

## Stage 4 — switch web to the pipeline root

```bash
sudo systemctl edit --full medradar-web.service   # add Environment=MEDRADAR_DATA_DIR=/srv/medradar/data/fda
sudo systemctl daemon-reload
sudo systemctl restart medradar-web.service
curl -fsS http://127.0.0.1:8787/api/health | python3 -m json.tool
```

Require `status=ok` or an explicitly understood `unknown`/`degraded` (not `not_ready`) before
continuing.

## Stage 5 — Web acceptance via SSH tunnel

From the reviewer machine:

```bash
ssh -i <key> -L 8788:127.0.0.1:8787 ubuntu@170.106.142.49
```

Open `http://127.0.0.1:8788/` and exercise: home, search, organization detail, regulatory events,
devices, PMA supplement, recall, compare, CSV/Markdown, Data Status, Change Feed. The status page
must show the production snapshot and the per-source official versions.

## Stage 6 — enable scheduler and backup

```bash
sudo cp /srv/medradar/app/deploy/systemd/medradar-data-update.service /etc/systemd/system/
sudo cp /srv/medradar/app/deploy/systemd/medradar-data-update.timer /etc/systemd/system/
sudo cp /srv/medradar/app/deploy/systemd/medradar-data-backup.service /etc/systemd/system/
sudo cp /srv/medradar/app/deploy/systemd/medradar-data-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now medradar-data-update.timer
sudo systemctl enable --now medradar-data-backup.timer
```

Do not claim continuous operation from installation alone. Observe at least one timer-triggered
`run`, confirm it skips undued sources, check the JSON result, and confirm the web service memory
and latency.

## Rollback

1. Stop/disable the new timers.
2. Restore `medradar-web.service` environment to its prior value (no `MEDRADAR_DATA_DIR`).
3. Checkout the old SHA and restart the service.
4. The old package snapshot is untouched.
5. The new `/srv/medradar/data/fda` state is retained for inspection; do not delete it.
6. If a pipeline snapshot must be reverted, use `rollback <prior_snapshot_id>`; never delete the
   change ledger.

## Approval text

> I approve DATA-002 production change request for SHA `<sha>`: deploy the code, create the
> production pipeline root, bootstrap, reconcile the sources, switch the web data directory,
> enable the update and backup timers, and perform the limited acceptance. I understand the
> old package snapshot remains the rollback target and the new state is a same-host backup.

No production command in this document has been executed.
