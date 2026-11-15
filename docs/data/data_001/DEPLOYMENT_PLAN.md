# DATA-001 — Deployment Plan (requires explicit approval)

**Status: not executed.** The live service, production data directory, systemd units and
SSH policy were not changed by this task. This plan is the requested approval artifact.

## Verified current state (2026-11-16)

* GitHub `feat/product-003-device-intelligence` HEAD:
  `1bdb1c349c59713e1a11426f15a6c06e892f87e0`.
* Server: Tencent Cloud Lighthouse, Ubuntu 24.04, 2 vCPU / 4 GB, 50 GB free disk.
* `medradar-web.service`: active, `127.0.0.1:8787`, `WorkingDirectory=/srv/medradar`,
  `User=medradar`, app at `/srv/medradar/app`, Python at `/srv/medradar/.venv/bin/python`.
* Live health reports snapshot `2026-11-14T22:09:22Z-openfda`; 91,457 records.
* Existing timers: `medradar-health.timer` (5 min), `medradar-backup.timer` (daily 04:30).
* `/srv/medradar/data` currently contains only `cache/` and `identity/`; the production
  service still serves the snapshot inside the app package.
* The live state was inspected read-only. No production file was modified.

## Proposed change (one deployment, after approval)

1. Deploy the approved DATA-001 commit to `/srv/medradar/app` using the existing deployment
   procedure. Do **not** reset the app directory.
2. Create `/srv/medradar/data/fda` with owner `medradar`, mode 0750.
3. Bootstrap from the currently served package snapshot:

   ```bash
   sudo -u medradar env \
     MEDRADAR_PIPELINE_ROOT=/srv/medradar/data/fda \
     MEDRADAR_REVIEW_DB=/srv/medradar/data/identity/review.db \
     /srv/medradar/.venv/bin/python -m medradar.data_pipeline bootstrap \
       --from /srv/medradar/app/medradar/product/snapshot --json
   ```

4. Run one real reconciliation in isolation (still no service change):

   ```bash
   sudo -u medradar env \
     MEDRADAR_PIPELINE_ROOT=/srv/medradar/data/fda \
     MEDRADAR_REVIEW_DB=/srv/medradar/data/identity/review.db \
     /srv/medradar/.venv/bin/python -m medradar.data_pipeline sync --force --json
   ```

5. Review:
   * `/api/data-status` equivalent via `status --json`;
   * the candidate's validation report;
   * changed counts and any `MISSING_ON_RECHECK` / `UNRESOLVED` rows;
   * the live web service remains healthy throughout (health timer and `curl /api/health`).
6. Only after review: add
   `Environment=MEDRADAR_DATA_DIR=/srv/medradar/data/fda` to
   `/etc/systemd/system/medradar-web.service`, run `systemctl daemon-reload`, then
   `systemctl restart medradar-web.service`.
7. Verify the new `/api/health` snapshot id and run the product acceptance smoke test.
8. Install `medradar-data-update.service` and `.timer`, plus
   `/etc/medradar/pipeline.env` (mode 0640; no key committed). Run
   `systemctl enable --now medradar-data-update.timer` only if the user approves automatic
   scheduling. DATA-002 changes the timer to an hourly wake-up; per-source due logic prevents unnecessary checks and retries failures after one hour.

## Rollback

* Before switching the live service, delete only `/srv/medradar/data/fda` to abandon the
  candidate; the live service is untouched.
* After switching, `pipeline rollback <previous-snapshot-id>` atomically restores the prior
  snapshot. If the web process cannot load it, revert `MEDRADAR_DATA_DIR` and restart.
* Keep at least two full snapshots and `pipeline.db` until the new system has run through one
  monthly 510(k)/PMA update and one weekly recall update.
* Do not roll back the identity-review database. It is independent and must be backed up.

## Resource and risk controls

* `MemoryHigh=2200M`, `MemoryMax=2400M`, `CPUQuota=150%`, idle I/O, 1-hour timeout. DATA-002 supersedes this with measured full-sync limits and an hourly scheduler wake-up.
* Daily request budget persisted; no key committed.
* One process lock prevents overlap.
* Disk guard refuses below 2 GiB free.
* Candidate validation blocks record drops >2% without explicit review.
* No new public port is opened; the service remains on `127.0.0.1:8787`.
* DeepSeek Harness and SSH configuration are not touched.

## Approval checklist

The user must explicitly approve each item before execution:

- [ ] deploy the DATA-001 commit to the app directory;
- [ ] create and write the pipeline state under `/srv/medradar/data/fda`;
- [ ] change `medradar-web.service` to serve the pipeline active pointer;
- [ ] install and enable `medradar-data-update.timer`;
- [ ] install a real openFDA API key file (optional; without it request budget is 900/day);
- [ ] any external alert destination (none is created by this task).

Merging the Draft PR and creating this plan are **not** approval of any item above.
