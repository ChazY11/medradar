# Backup & Recovery — MedRadar Observatory

Status: implemented and verified locally on `feat/observatory-reliability-v1`.
**Production deployment is `NOT_DEPLOYED`** pending authorization (host + object
storage + credentials). No paid resource has been created and no credentials are
stored in this repository.

The system of record is the append-only observation ledger
(`data/observatory/observatory.sqlite`). This document describes how that ledger
is backed up, verified, restored, pruned and shipped offsite.

---

## 1. What is backed up

| artifact | irreplaceable? | contents |
|---|---|---|
| `ledger.sqlite` | **yes** — system of record | observations, payload versions, change/status/mapping history, sync runs, failures, source state and watermarks, runtime state |
| `MANIFEST.json` | yes (it makes the bundle verifiable) | sha256 + size of every artifact, counts, first_seen min/max, per-source counts, watermarks, schema version, integrity/consistency results, tool versions |
| `raw-cache/` (optional) | **no** — regenerable | raw HTTP responses archived by `medradar.http.Fetcher`; can be re-fetched if a parser bug is found |
| `prospective/` (optional) | **yes** — never regenerated | frozen prospective-registry documents copied read-only (hashes only + files) |
| `README.txt` | no | human-readable restore instructions |

`first_seen_at` is immutable in the ledger (SQLite trigger). A backup is a
consistent snapshot of the file, so restoring it **copies** those timestamps; it
never regenerates them.

## 2. Bundle layout

One directory per snapshot, built in a temp dir under the destination and
published with a single rename (a crash can never leave a half-written bundle
that looks valid):

The default destination is ``<ledger directory>/backups`` (i.e.
``data/observatory/backups`` for the production ledger), which is where
``medradar.observatory.health`` and ``medradar.observatory.audit`` discover the
newest bundle.  Pass an explicit destination to stage backups on another volume.

```
backups/observatory-YYYYMMDDTHHMMSSZ[-label]/
  ledger.sqlite                 # sqlite3.Connection.backup() snapshot (WAL-safe, single file)
  MANIFEST.json                 # sha256+size per artifact, counts, first_seen, watermarks, ...
  raw-cache/                    # optional, read-only copy of the raw HTTP cache
  prospective/                  # optional, read-only copy of the frozen registry
  README.txt                    # restore instructions
```

The ledger snapshot is taken with the **SQLite online backup API**, never a raw
file copy of a live WAL database. The destination is switched back to a
rollback journal so the bundle is one self-contained file (no `-wal`/`-shm`).

## 3. Verify (always, before trusting a backup)

```bash
python -c "import json; from medradar.observatory.backup import verify_backup; \
print(json.dumps(verify_backup(r'data/observatory/backups/observatory-20261103T235900Z'), indent=2))"
```

`verify_backup` re-hashes every artifact and re-runs `PRAGMA integrity_check` on
the copied database, then compares counts, first_seen min/max, per-source
counts, version/change/run counts and source watermarks against the manifest.
Verdicts:

- `OK` — everything re-derived and matched.
- `FAILED` — verification ran and found a mismatch (hash, size, count, integrity).
- `UNVERIFIED` — the manifest or the ledger is missing/corrupt, so the bundle
  could not be verified. **An UNVERIFIED bundle is never reported OK.**

`create_backup()` verifies its own published bundle and only returns
`status="OK"` when that verification passed. Until then it is
`UNVERIFIED`/`FAILED`.

## 4. Restore

```bash
python -c "import json; from medradar.observatory.restore import restore_backup; \
print(json.dumps(restore_backup(r'data/observatory/backups/observatory-20261103T235900Z', r'out/restore-target'), indent=2))"
```

Restore refuses a bundle whose manifest hashes do not verify, and refuses a
non-empty target unless `overwrite=True`. With `overwrite=True` an existing
restored ledger is renamed to `observatory.sqlite.before-restore-<stamp>` —
never deleted. The restored layout is:

```
<target>/observatory.sqlite     # copied, not regenerated
<target>/cache/                 # if the bundle had raw-cache/
<target>/prospective/           # if the bundle had prospective/
<target>/RESTORE_REPORT.json    # verification evidence (hashes, counts, first_seen)
```

Point the collector at the restored copy with
`MEDRADAR_OBSERVATORY_DB=<target>/observatory.sqlite` after verifying it.

### Restore drill

```bash
python scripts/observatory_backup_drill.py --work-dir out/reliability_drill --json
# optional: --ledger <path>   (defaults to MEDRADAR_OBSERVATORY_DB / data/observatory/observatory.sqlite)
```

The drill runs the full loop in an isolated temp directory under `--work-dir`:
fresh backup → hash verification → restore → restored-content verification →
**continuity check**. The continuity check writes one synthetic observation into
the restored ledger through `ObservationLedger.record_observation`, then proves
that all pre-existing `first_seen_at` values are unchanged and the new row
received a genuinely fresh one. The outcome is recorded in the real ledger's
`runtime_state["last_restore_drill"]`:

```json
{"at":"ISO","status":"OK|FAILED","ok":true,"bundle":"observatory-...",
 "checks":[{"id":"continuity_old_rows_unchanged","ok":true,"detail":"..."}],
 "first_seen_max":"ISO","counts":{...},"error":null}
```

The drill only reads production data; its files live under `--work-dir`, and the
runtime-state records (`last_backup`, `last_restore_drill`) are the intended
operational journal. Exit code is non-zero when the drill fails.

## 5. Retention / prune

```bash
python -c "import json; from medradar.observatory.backup import prune_backups; \
print(json.dumps(prune_backups(r'data/observatory/backups'), indent=2))"
# dry run: prune_backups(r'data/observatory/backups', dry_run=True)
```

Retention labels (Grandfather-Father-Son), computed from each bundle's
`created_at` in its manifest:

| label | rule |
|---|---|
| daily | keep the newest bundle of each of the **7** most recent calendar days |
| weekly | keep the newest bundle of each of the **4** most recent ISO weeks |
| monthly | keep the newest bundle of each of the **6** most recent months |

Additional safety rules, all enforced by `prune_backups`:

- the newest bundle overall is **never** deleted;
- the newest *verifiable* bundle is never deleted either;
- a bundle whose `MANIFEST.json` is missing, corrupt or incomplete is **never
  deleted**: it is moved to `<dest>/quarantine/<bundle>` and reported;
- bundles are only touched when they are direct children of the backup
  directory (nothing outside is pruned);
- `dry_run=True` reports what would happen and changes nothing.

## 6. Raw-cache pruning (cache is regenerable, the ledger is not)

```bash
python -c "import json; from medradar.observatory.backup import prune_raw_cache; \
from medradar.observatory.ledger import open_ledger_readonly; \
print(json.dumps(prune_raw_cache(r'data/observatory/cache', open_ledger_readonly(), retention_days=180), indent=2))"
```

`prune_raw_cache` deletes a cache file only when **both** hold:

1. the file is older than `retention_days` (default 180), and
2. the ledger already stores the canonical payload for a URL whose key matches
   the cache file name (i.e. the response is safe to re-derive).

Everything else is retained and reported: recent files, files without ledger
evidence, files that do not look like cache entries (including `*.sqlite`,
`MANIFEST.json`, `*.zip`, directories) and prospective-registry files. Cache
files that cannot be mapped to ledger evidence are deliberately kept — the cache
is a superset archive and deleting unproven duplicates is not worth the risk.

## 7. Offsite copy (options, no credentials committed)

Backups become real only when they leave the host. The branch ships a
local-directory target; these commands are examples an operator may run after
explicit authorization. Never commit credentials, tokens or keys.

```bash
# rclone (S3-compatible, B2, Google Drive, ...): one-way sync of verified bundles
rclone sync data/observatory/backups remote:medradar-backups --immutable --checksum

# restic: encrypted, deduplicated repository (password from env/secret store only)
export RESTIC_REPOSITORY=s3:https://s3.example.com/medradar-restic
export RESTIC_PASSWORD_FILE=/etc/medradar/restic.pass
restic backup data/observatory/backups/observatory-*/
restic check --read-data-subset=1/20

# aws s3: server-side encryption + versioning, credentials from the instance role
aws s3 sync data/observatory/backups/ s3://medradar-backups/observatory/ \
  --sse AES256 --only-show-errors
```

Recommended operational order: `create_backup` → `verify_backup` → offsite
upload → prune local. Keep at least one verified offsite copy per day and run a
restore drill (not just a backup) monthly.

## 8. What this branch can and cannot claim

- Implemented and verified **locally**: real backup of the real ledger
  (400 observations / 400 versions / 400 changes at the time of writing),
  isolated restore drill with first_seen continuity, retention and quarantine
  behaviour.
- **Not deployed**: no supervisor, no object storage, no offsite copy exists yet.
  `deployment_status` for a service is `NOT_DEPLOYED` until an operator installs
  a supervisor and authorizes a storage target.
- Backups are not encrypted by this code. Use `restic`/`age`/bucket-side
  encryption if the ledger or prospective registry must be confidential.

## 9. Scheduled daily backup (registered on this workstation)

A verified backup is only a backup if something actually runs it. The Windows Task
Scheduler task **`MedRadarObservatoryBackup`** runs
`scripts/observatory_backup_task.ps1` daily at **04:17 local**:

```
python -m medradar observatory backup --dest data\observatory\backups --verify --prune
```

- one-shot process (clean task lifecycle; never a long-running child);
- `--verify` means the manifest hash and `PRAGMA integrity_check` are re-checked
  before the task reports success (`Last Result=0` only on a verified backup);
- `--prune` applies the 7 daily / 4 weekly / 6 monthly policy (quarantine instead
  of delete for unverifiable bundles);
- log: `logs/backup-YYYYMMDD.log`; operational record: ledger
  `runtime_state["last_backup"]` (the health panel reads it).

Verify / remove:

```powershell
schtasks /Query /TN MedRadarObservatoryBackup /V /FO LIST
Unregister-ScheduledTask -TaskName MedRadarObservatoryBackup
```

Linux equivalent: a systemd timer running the same CLI command
(`deploy/systemd/` already contains the pattern for the collector; add a second
unit with `Type=oneshot` and the backup command).

