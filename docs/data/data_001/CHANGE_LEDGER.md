# DATA-001 — Change Ledger

The ledger lives in `pipeline.db` (SQLite). It answers: *what did MedRadar observe changing,
when did it observe it, and which snapshots prove it?*

## Tables

### `changes`

| Column | Meaning |
|---|---|
| `change_id` | deterministic SHA-256 fingerprint; idempotency key |
| `run_id` | sync run that produced the candidate |
| `source_id` | official endpoint family |
| `official_record_id` | FDA identifier (K number, PMA/supplement, recall product reference) |
| `event_id` | MedRadar event key (`source_id:official_id`) |
| `change_type` | `ADDED`, `UPDATED`, `REMOVED_CONFIRMED`, `MISSING_ON_RECHECK`, `UNRESOLVED` |
| `detected_at` | when MedRadar detected the change (not the event date) |
| `source_updated_at` | endpoint-level official version at detection |
| `previous_content_hash`, `new_content_hash` | full-record hashes before display truncation |
| `previous_snapshot_id`, `candidate_snapshot_id` | evidence snapshots |
| `changed_fields_json` | field-level old/current values (bounded for display) |
| `evidence_json` | official URL, endpoint, collection scopes, reason, snapshot ids |
| `organization_key` | current attribution at detection time, where decidable |
| `applicant_name`, `event_type`, `event_date` | searchable record context |
| `record_json` | compact record as of the change |
| `status` | `staged` or `published` |
| `published_at` | set when the candidate pointer becomes active |

`UNCHANGED` is a **count**, not 91,000 rows per run. The snapshot manifest stores the
unchanged count; the ledger stores only changes. This keeps the ledger useful rather than
turning every check into a write amplification exercise. The change type vocabulary still
includes `UNCHANGED`; it is represented as the absence of a row plus `change_summary.unchanged`.

### Supporting tables

* `record_observations` — immutable `first_observed_at`, latest seen time, hash, state,
  missing count per official identity.
* `snapshots` — candidate/published/superseded/rejected snapshot inventory, hashes,
  validation evidence and parent.
* `publications` — append-only pointer actions (bootstrap, sync, rollback, recovery).
* `sources` — last check/sync, official version/total, failures, update flag.
* `sync_runs` — every run, status, requested sources, counts, error, metrics.
* `request_usage` — daily request count/bytes by source.
* `incidents` — validation failures, post-publication warnings, sync failures.

## Publication transaction

1. Candidate is built in staging and validated.
2. `snapshots` row is inserted as `staged`.
3. Change rows are inserted as `staged` in one transaction.
4. `active.json` is atomically replaced.
5. A DB transaction marks the snapshot published and the change rows published.
6. Record observations and source sync times are written.

A failure before step 4 discards staged changes and leaves the old active pointer. A failure
between 4 and 5 leaves the new pointer active and the changes staged; the next pipeline
operation runs `recover_publication`, verifies the pointer's manifest id, and completes the
DB transaction. There is never a published pointer with unpublished ledger rows after
recovery.

## Diff semantics

* Top-level record fields are compared, including all source fields under `raw.*`.
* Display-only fields (`title`, `official_url`) are not treated as content changes.
* Discovery metadata (`first_observed_at`, `last_synced_at`, `source_updated_at`,
  `record_state`, `missing_count`, hashes) is excluded from the diff.
* Values are bounded to 400 characters in the ledger; the full official record is linked by
  URL and retained in the snapshot.
* A change is not a new regulatory event. The event date is copied unchanged; a
  `UPDATED` row can have an event date years in the past.

## Read surface

`GET /api/changes?source=&type=&org=&limit=&offset=` returns published rows only. It is a
read-only projection; the public app has no write route. The Data Status page renders the
same rows with official links and changed fields.

If no pipeline database exists, the API returns `configured=false`, an empty list and an
explicit message. It does not return a made-up empty change history.
