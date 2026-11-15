# DATA-002 — Production Acceptance

## Gate status

| Gate | Status | Evidence |
|---|---|---|
| G1 Source independence | **PASS (software/isolation)** | per-source failure tests; check + collection failures; healthy update publishes; failed source old version retained |
| G2 Data integrity | **PASS** | added/updated/missing/duplicate/rebaseline tests; full reconcile 0 fabricated changes; 175-test suite |
| G3 Snapshot safety | **PASS** | atomic publish, corrupt candidate rejection, runtime reload/fallback, real rollback A→B→A |
| G4 Resource safety | **PASS (measured)** | 2C/4GB full-all sync 8:32, 2.16 GiB peak, live web stayed `ok`; auto cap 1 source/run |
| G5 Backup & recovery | **PASS (same-host)** | consistent backup + isolated restore drill; off-host remains a stated limitation |
| G6 Operational health | **PASS** | `/api/livez`, `/api/readyz`, layered `/api/health`; adapter exit codes; fallback visible |
| G7 Continuous operation | **BLOCKED** | timer not installed/enabled; no production automatic trigger. Cannot claim PASS. |
| G8 Product acceptance | **PARTIAL** | isolated real Web/API/Data Status accepted; production URL not switched; requires approval |

## Scenario results

### 1. One source exception, other sources healthy

Offline:
`test_partial_source_failure_publishes_healthy_source_and_reports_failed`,
`test_collection_failure_in_one_source_does_not_block_another`.

Observed: recall publishes a new snapshot; 510(k) retains its old official version and records
`sync_status=FAILED`; run status `PARTIAL`; no fake `SYNCED`.

### 2. Two sources update together

`test_multiple_sources_update_in_one_partial_snapshot` (cap raised for the test): both PMA and
recall versions appear in one snapshot. Production default is one source per automatic run;
the combined format is still supported and validated.

### 3. No data change

Real isolated all-source sync: 241 requests, 1.236 GB, 8:32, **0 added / 0 updated / 0 removed**,
91,457 unchanged; no fabricated change rows.

### 4. Historical record revision

`test_updated_record_keeps_event_date_and_records_old_and_new_values`: UPDATED row keeps
event date, old/new content hash and changed fields. Real production data had no revision in
the observed interval.

### 5. Corrupt candidate

`test_validator_rejects_corrupt_hash_duplicate_ids_and_record_drop`: tampered file/hash,
duplicate ids and record-drop gate block publication; old pointer remains.

### 6. New snapshot publication and runtime reload

`test_runtime_holder_reloads_on_active_pointer_switch`: the same process sees the new snapshot
without restart. `test_health_distinguishes...` shows fallback if a new pointer is unusable.
The isolated Data Status page was captured from the real pipeline state:
`evidence/data-status-isolated.png`.

### 7. Rollback

Real isolated rollback:
`5c8e966… → 0a54369… → 5c8e966…`; publication journal retained all three actions; change ledger
was not deleted. See `evidence/status-after-old.json`, `status-after-new.json`.

### 8. Long source failure

Real isolated check with an unreachable openFDA base returned `CHECK_FAILED` and left the
active snapshot `5c8e966…` unchanged (`evidence/check-failure.json`). Offline all-source
failure returns `BLOCKED`; per-source failure retries hourly. Production timeout is not
claimed.

### 9. Memory pressure

Full all-source manual sync under `MemoryMax=2400M`: 8:32, peak 2.16 GiB, no OOM, live web
`ok`. One-source full reconcile: 3:11, 1.76 GiB. Automatic cap is 1 product source/run.

### 10. Backup restore

Real isolated backup: 30.9 MiB peak, DB integrity `ok`, all snapshots and pointer included.
Restore into an empty directory: 26.26 s, product dataset/device index validated, active
snapshot `5c8e966…`, change ledger empty because the real run had no changes. A non-empty
destination is refused (test). Evidence: `evidence/backup.json`, `backup.time.txt`,
`restore.json`, `restore.time.txt`.

## Test totals

* `python -m pytest tests/data_pipeline tests/product -q`: 175 tests, all pass.
* `python -m medradar selftest`: 1,270 tests, OK (3 skipped).
* `systemd-analyze verify`: all four templates pass (one unrelated host unit warning).

## Not tested / not claimed

* No production timer trigger.
* No production data path switch.
* No off-host disaster recovery.
* No long-duration soak (days/weeks).
* No guarantee that every FDA correction arrives before the official version; the rolling
  full sweep is a mitigation, not a proof of completeness.
