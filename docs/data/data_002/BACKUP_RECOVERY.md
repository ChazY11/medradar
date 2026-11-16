# DATA-002 — Backup and Recovery

## What is backed up

A DATA-002 backup directory contains:

* `pipeline.db` — SQLite backup via `sqlite3.Connection.backup` (not a file copy; WAL-safe);
* `active.json` — the published pointer captured while the pipeline lock is held;
* `snapshots/<id>/` — immutable snapshot files (all by default; `--active-only` for a
  smaller operational copy);
* `review.db` — identity-review SQLite database via the same backup API, when present;
* `backup.json` — schema, source root, active snapshot, snapshot ids, per-file SHA-256/size,
  DB integrity, review DB identity, and limitations.

The change ledger, source checks, first-observed times, revision evidence, request usage and
incidents live in `pipeline.db`; they are not reconstructed from Git.

## Consistency

The backup job takes the single-writer `PipelineLock` (60 s wait) while it copies the pointer
and databases. A publish cannot change the pointer between the DB copy and the pointer copy.
If the lock cannot be acquired, the backup fails rather than producing a mixed-generation
archive.

## Restore

```bash
python -m medradar.data_pipeline restore \
  --archive /srv/medradar/var/backup/data/data-backup-... \
  --destination /tmp/data002-restore \
  --review-db-destination /tmp/data002-restore/review.db \
  --json
```

Restore:

1. refuses a non-empty destination;
2. verifies every manifest file's SHA-256 and size;
3. runs `PRAGMA integrity_check` on the restored pipeline DB;
4. checks the pointer's snapshot exists;
5. checks the DB active snapshot and pointer agree;
6. runs the full snapshot validator, including the product dataset and device index;
7. does not modify the source backup or any production pointer.

A failed restore leaves an explicit error and a partial isolated directory; it never runs
against production automatically.

## Real production and isolated drills

Latest production backup: `data-backup-20261116T032839Z-e5362d`, active snapshot
`fda-snapshot-20261116T032632Z-18ce4d0cbbe4`, six snapshots, pipeline DB integrity `ok`.
Restore into `/tmp/data002-prod-restore-final` validated the active snapshot and product/device
index without modifying production. The earlier isolated drill is also in
`docs/data/data_002/evidence/`:

* backup of an isolated pipeline state containing at least two immutable snapshots and change
  ledger rows;
* restore into a new empty directory;
* comparison of active snapshot id and change counts;
* product dataset load with the restored active snapshot;
* a non-empty destination refusal test.

## Limitation

This is **same-host operational backup**, not complete disaster recovery. The two existing
Tencent Cloud snapshots already consume the free quota and were not changed. A host/volume
loss would lose this copy. An off-host target (object storage or a second host) requires a
separate approved change and a cost decision. Until then the residual risk is explicit in
`KNOWN_LIMITATIONS.md`.
