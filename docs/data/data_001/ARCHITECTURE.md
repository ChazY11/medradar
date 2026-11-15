# DATA-001 — Architecture

## Purpose

DATA-001 turns the manually refreshed MedRadar openFDA snapshot into a monitored data product:

```text
official openFDA endpoint
        │  version probe (meta.last_updated + total)
        ▼
Source Detector ──► source state (SQLite)
        │ UPDATE_AVAILABLE / UNKNOWN
        ▼
Scoped Collector ──► full reconciliation of the reviewed organization scope
        │ records + hashes + query coverage
        ▼
Change Detector ──► ADDED / UPDATED / MISSING_ON_RECHECK / REMOVED_CONFIRMED
        │
        ▼
Immutable Candidate Snapshot (staging)
        │ structural + coverage + product + device-index validation
        ▼
Publisher ──► atomic active.json pointer switch
        │
        ├──► FastAPI reads the new snapshot on the next request (atomic in-process swap)
        └──► Change Ledger is published with the snapshot
```

The design is deliberately boring: SQLite, files, one process lock, and systemd timers. The
server has 2 vCPU / 4 GB RAM. There is no queue, broker, cluster, or managed database in this
task.

## Boundaries

### What MedRadar monitors

The product scope is the reviewed organization roster in
`medradar/product/identity/organizations.json`: 59 organizations and their exact openFDA
search tokens. The collector records the query expression, official total, pages, partitions
and completion state for every organization/source pair.

This is **not** the complete FDA applicant universe. A company that is not in the roster is
not monitored, and a record that does not match a roster token is not collected. The product
and the data-status page state this.

### What "update" means

openFDA exposes `meta.last_updated` per endpoint. That is an endpoint-level publication
marker, not a per-record revision timestamp. Individual 510(k)/PMA records expose no
"last modified" field. The detector can therefore say "the endpoint advertises a new
version"; it cannot say which records changed without reconciliation.

The pipeline reconciles the complete scoped set and compares content hashes. This is the only
method that can detect revisions to old records honestly. Date-window queries are useful for
finding new event dates, but not sufficient for revisions, so they are not used as the sole
sync mechanism.

## Components

| Module | Responsibility |
|---|---|
| `config.py` | paths, request budget, retention, thresholds, credential loading |
| `model.py` | source catalogue, status/change vocabularies, interval policy |
| `openfda.py` | HTTP, retry/backoff, 429 handling, 404 semantics, budget, credential redaction |
| `detector.py` | `NO_CHANGE`, `UPDATE_AVAILABLE`, `CHECK_FAILED`, `SOURCE_DEGRADED`, `UNKNOWN` |
| `collector.py` | scoped queries, pagination, date partitioning, coverage audit, exact-ID recheck |
| `normalize.py` | deterministic normalisation, full-record content hashes, display compaction |
| `changes.py` | record diff, removal policy, observations, first-observed preservation |
| `snapshot.py` | immutable candidate files and manifest |
| `validator.py` | manifest/file/record/coverage/product/device-index validation |
| `publisher.py` | atomic active pointer, publication journal, rollback, crash recovery |
| `pipeline.py` | orchestration, locking, disk/budget checks, report |
| `db.py` | source state, sync runs, change ledger, observations, request usage, incidents |
| `status_service.py` | read-only `/api/data-status` and `/api/changes` projections |
| `cli.py` | operator/systemd commands |

## State storage

```text
<MEDRADAR_PIPELINE_ROOT>/
  pipeline.db                 source state, ledger, observations, publication journal
  active.json                 atomic pointer to the active snapshot
  pipeline.lock               single-writer lock
  snapshots/
    fda-snapshot-<ts>-<hash>/ immutable data files + manifest
  staging/                    private candidate directories; never served
  logs/
```

`pipeline.db` is not a replacement for snapshots. It records what MedRadar observed and
decided. The snapshot files remain the authoritative data artifact.

## Snapshot format

The product reads the same three files as before: `events.jsonl.gz`, `applicants.jsonl.gz`,
`classifications.jsonl.gz`, plus `snapshot.json`. DATA-001 adds per-record fields:

* `first_observed_at` — preserved across snapshots; never rewritten by a later collection;
* `last_synced_at` — the latest successful reconciliation, not an event date;
* `source_updated_at` — the endpoint-level official version used for the record;
* `content_hash` — hash of the full normalised record before display truncation;
* `snapshot_hash` — hash of the compacted stored record; recomputed by validation;
* `record_state` / `missing_count` — lifecycle state for a record absent from a sweep;
* `collection_scopes` — which roster scopes returned the record.

The manifest records source versions, query coverage, change summary, validation evidence,
lineage and time semantics. The snapshot id is
`fda-snapshot-<UTC timestamp>-<first 12 of content hash>`. Once published, the directory is
not edited.

## Runtime reload

`DatasetHolder` fingerprints the `active.json` pointer, the resolved `snapshot.json`, and
the identity-review database. On a change it builds a new `Dataset` while holding the old
dataset reference, then swaps the reference. If loading fails, the old dataset remains
served and the normal `503` error path applies to a first load.

This avoids a double-memory requirement for a full second process and does not stop the
existing service. A controlled restart remains available as a fallback, but is not required
by the pointer design.

## Failure isolation

* Collection writes only to staging; the active snapshot is untouched.
* Validation failure blocks publication and leaves the old pointer.
* Pointer writes use `os.replace`; readers never see a partial JSON pointer.
* Ledger rows are inserted as `staged` and become visible only when the matching snapshot
  is published.
* If the pointer switch succeeds but the DB commit fails, the next pipeline operation
  recovers the DB side from the pointer and marks the staged change set published.
* A single process lock prevents concurrent check/sync/publish/rollback.
* The daily request budget is persisted before each network attempt, so a crash loop cannot
  silently exceed the source quota.

## Resource posture

* One collector process; serial organization/source queries.
* In-memory candidate is scoped to the 91k-record product snapshot, not the entire FDA
  universe.
* Disk use: one compressed snapshot is about 13–20 MB; retention keeps a small number.
* Validation builds the product dataset and device index once; this is the main memory peak.
  The measured peak for the real reconciliation is recorded in `DELIVERY_REPORT.md`.
* The systemd unit is configured with a memory cap and idle I/O priority in
  `deploy/systemd/medradar-data-update.service`; it is not installed by this change.
