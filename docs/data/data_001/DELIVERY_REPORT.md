# MedRadar DATA-001 — Continuous FDA Pipeline Delivery Report

**Branch:** `feat/data-001-continuous-pipeline`
**Draft PR:** https://github.com/ChazY11/medradar/pull/50
**Base:** `feat/product-003-device-intelligence` at `1bdb1c349c59713e1a11426f15a6c06e892f87e0`
**Environment:** local Windows development + isolated `/tmp` test on the 2 vCPU / 4 GB
Tencent Cloud server. Production data and service units were not changed.

## 1. Which FDA data can we now check automatically?

Four official openFDA device endpoints:

| Source | Records in live probe | Purpose |
|---|---:|---|
| `openfda_510k` | 176,625 | 510(k) premarket notifications |
| `openfda_pma` | 57,487 | PMA originals and supplements; one official source/version |
| `openfda_recall` | 59,705 | device recall records |
| `openfda_classification` | 7,098 | product-code dictionary used by the product |

The product event scope remains the 59 reviewed organizations (91,457 records in the
adopted baseline), not the entire FDA applicant universe.

## 2. Check frequency

* 510(k): every 24 hours.
* PMA: every 24 hours.
* Recall: every 6 hours.
* Classification: every 24 hours.
* Failed/degraded checks are retried hourly, not after a full interval.

Official declared frequency is monthly for 510(k)/PMA and weekly for recall. The scheduler
checks more often so it notices a publication promptly; it cannot observe before publication.

## 3. Which sources support true incremental synchronization?

**None at the HTTP record level.** openFDA exposes `meta.last_updated` per endpoint but no
per-record modified timestamp for 510(k)/PMA; recall `event_date_posted` is a publication
date, not a revision timestamp. A date-window fetch can find new event dates, but cannot
prove that an old record was corrected.

DATA-001 therefore uses:

* **cheap version detection** (one `limit=1` probe) as the incremental trigger;
* **complete scoped reconciliation + full-record content hashes** as the correctness
  mechanism;
* an incremental **change ledger** as the output.

PMA originals and supplements share one official endpoint and one version. No fake separate
PMA-original feed is created.

## 4. Which sources need periodic full re-collection?

All product sources do, when their official version changes. The collection is scoped to the
59 organizations, not the global FDA universe. Classification is small and is refreshed with
any product reconciliation. There is no silent date-window-only "incremental" mode.

## 5. How new records are discovered

The previous and candidate snapshots are keyed by `source_id + official_record_identity`.
An identity absent before and present now is `ADDED`. It keeps the official event date,
records `first_observed_at` separately, writes the source URL and scope, and enters the
candidate before validation.

## 6. How historical revisions are detected

Every full normalised record is hashed before display truncation. If the official identity is
the same and the hash differs, the change is `UPDATED`; the old/new hashes and changed fields
are stored, and the event date is not changed. A long free-text change beyond display
truncation is still detected.

## 7. Why repeated synchronization does not duplicate data

* No official version change and no total change ⇒ detector says `NO_CHANGE`; no snapshot is
  built.
* Change rows use a deterministic content fingerprint; retries insert zero duplicates.
* A record's `first_observed_at` is preserved from the observation table/previous snapshot.
* A first reconciliation from a legacy display projection is a **rebaseline**: only fields
  that existed in the legacy projection are compared. The real run reports
  `rebaselined=91,457`, not 91,457 fake `UPDATED` rows.
* A source-version-only change produces a snapshot with zero added/updated content rows, not
  fake events.

## 8. Failure impact on the live snapshot

Collection writes only to staging. Any HTTP/page/coverage failure aborts the candidate; the
old active pointer is untouched. Validation failure, budget exhaustion, disk shortage, lock
contention and source degradation all leave the old snapshot serving. The API returns the old
snapshot, not an empty database.

## 9. Rollback

`python -m medradar.data_pipeline rollback <snapshot_id>` re-validates the prior snapshot,
atomically switches `active.json`, records a publication action, and keeps the newer snapshot
and all change evidence. The identity review database is independent and is never part of
snapshot rollback.

## 10. How PRODUCT-003 device relationships refresh

Validation loads the candidate through `load_dataset()` and builds the complete device index.
PMA supplements are attached to their PMA family by the official PMA number; 510(k)s enter
the device explorer; recall links are created only from official K-number references.
Candidates remain candidates. The index is rebuilt from the snapshot rather than mutated
incrementally, which is the reliable choice at this scale. No pickle cache is used.

## 11. What the real isolated run found

The real scoped reconciliation used the live openFDA API with no key. Final sanitized result:
`docs/data/data_001/evidence/real-sync.json`.

| Measure | Value |
|---|---|
| Baseline records | 91,457 |
| Recall records reconciled | 29,825 |
| Requests | 85 |
| Response bytes | 901,187,267 |
| Elapsed | 4:01.00 |
| Peak process working set | 2,077,472 KiB (~1.98 GiB) |
| Added | 0 |
| Updated | 0 |
| Confirmed removed | 0 |
| Missing on recheck | 0 |
| Unresolved | 0 |
| Rebaselined (legacy projection) | 29,825 |
| Unchanged | 29,825 |
| Active snapshot | `fda-snapshot-20261115T213848Z-753ecfc3c03a` |

The isolated run reconciled the recall source against the live openFDA version
`2026-11-12`; 510(k)/PMA/classification were left for a later reconciliation and are shown
as unknown/pending, not as "no change". No new or revised recall record was present in the
tracked scope in this interval; a zero-change run is a valid chain test. The report is not
claiming that no FDA record was published globally.

**Corrections found during acceptance:** an earlier real run reported 934 `UPDATED` records
because legacy values were already truncated; a later one reported 106 because the legacy
collector had capped recall `k_numbers` at five and the new full hash saw the sixth. Those
were schema-transition artifacts, not revisions. The rebaseline comparison now uses the
display projection, set semantics, and the legacy list cap. The erroneous runs were
discarded; the final server run above reports 0. This correction is recorded rather than
hidden.

## 12. Actual resource consumption on 2 vCPU / 4 GB

* Isolated server bootstrap: 47.8 s, peak RSS 1,465,832 KiB (1.40 GiB).
* Isolated server recall reconciliation: 4:01, peak RSS 2,077,472 KiB (1.98 GiB). The live
  service stayed at 1.4–1.5 GiB; available memory was 2.1–2.2 GiB before and after; swap use
  was small (~23 MiB), and the live health endpoint stayed `ok` on the old snapshot.
* The pipeline drops the candidate event map before loading the product dataset for
  validation, and the validator drops its raw event list before product load. This reduces
  the sum-of-two-models peak.
* The initial 1800M unit cap was too small; the template now uses
  `MemoryHigh=2200M` / `MemoryMax=2400M`. Production is **not** enabled.

## 13. What is deployed vs not deployed

**Implemented and tested locally:** source detector, scoped collector, normalizer, change
ledger, snapshot validation, atomic publisher, rollback, runtime reload, data-status API,
change feed, Data Status UI, systemd unit templates, CI jobs, docs.

**Not deployed:** production code checkout, production data directory, `medradar-web.service`
environment change, systemd timer enablement, openFDA API key, external alerts. The live
service still serves snapshot `2026-11-14T22:09:22Z-openfda`.

## 14. What still requires user approval

* deploy the branch to `/srv/medradar/app`;
* create `/srv/medradar/data/fda`;
* change the production service to `MEDRADAR_DATA_DIR=/srv/medradar/data/fda`;
* install/enable `medradar-data-update.timer`;
* optionally install an openFDA API key;
* any alert destination.

The exact plan is `DEPLOYMENT_PLAN.md`. Merging the Draft PR is not deployment approval.

## 15. Is the foundation ready for more sources?

Yes, for the same pattern:

* a `SourceSpec` with endpoint, scope field, date field, official frequency and URL builder;
* a normalizer and record identity;
* a source-specific scope or full-fetch policy;
* validation and change-ledger rules;
* the same status/change-feed UI.

The limiting factor is not the scheduler; it is defining an honest record identity and
revision policy for each new source. Bulk-only or non-date-versioned sources need their own
coverage policy. The current design deliberately does not pretend that every new feed is
incremental.
