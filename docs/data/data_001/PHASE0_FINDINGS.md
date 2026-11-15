# DATA-001 — Phase 0 Technical Findings

This is the investigation record that drove the design. It is not a post-hoc architecture
description.

## A. MedRadar code review

### 1. What of the existing collector is reusable?

Reusable semantics, not the script's control flow:

* the reviewed organization roster and exact `acceptance`/`search_tokens` matching rule;
* the openFDA endpoint choice and the product's normalised event fields;
* the 59-organization scope and the applicant/recalling-firm query shape;
* the product's attribution/status model, identity registry and review overlay;
* the device-index builder, which already rebuilds a deterministic index from a snapshot;
* the `Dataset` measurement layer and FastAPI projection.

The legacy collector itself combines fetch, pagination, normalisation, compaction and write
into one 676-line script. It is a snapshot generator, not a scheduler-safe state machine. The
pipeline reuses its **semantics** and replaces its write path.

### 2. How was the existing data version generated?

`scripts/product_collect.py` writes directly into `medradar/product/snapshot/`:

* it walks 59 organizations × 3 endpoints with `applicant`/`recalling_firm` searches;
* it accumulates all records in memory, applies display compaction, writes three gzip JSONL
  files, then writes `snapshot.json`;
* the manifest id is `2026-11-14T22:09:22Z-openfda` (collection time + source);
* the manifest has flat file hashes and counts; it has one global `openfda.last_updated`
  taken from the last meta response, not a per-source version;
* no candidate/staging/pointer exists. A re-run overwrites the package data.

The live deployment at `1bdb1c3` serves this package snapshot. The state root
`/srv/medradar/data` contains only `cache/` and `identity/`, not a served FDA snapshot.

### 3. Was there pagination truncation?

Yes, in two ways:

* `MAX_PAGES = 60` and `PAGE_LIMIT = 1000` assume 60,000 records per query, but openFDA
  rejects `skip > 25,000`. Any query above the window would fail rather than partition;
* the manifest recorded errors, but a partial query could still leave the whole output as if
  it were complete. There was no `reported_total == collected` assertion and no per-query
  completion state.

The new collector distinguishes a legitimate empty filtered 404 from an error, records
`reported_total`, pages, partitions and `complete`, and aborts on any mismatch or partial
page.

### 4. Was there duplicate fetching?

Yes:

* the same record can match multiple organization tokens; the legacy merge removed duplicates
  by `event_id`, but did not retain which organization scopes returned it;
* the product split PMA originals and supplements into two event types, even though they
  come from one official endpoint and therefore have no independent update version;
* classification was fetched again for every run without a per-source version check.

The new pipeline de-duplicates by `source_id + official id`, stores the union of scopes, and
treats PMA originals/supplements as one official source.

### 5. How could it tell a new record from a revision?

It could not. It generated no per-record hash and no previous/candidate comparison. The
manifest only recorded collection-level counts. A new run simply replaced the snapshot.

### 6. How does the API load new data?

`medradar/product/api.py::DatasetHolder` loads a `Dataset` from `MEDRADAR_DATA_DIR` (or the
package snapshot) once per process and caches it. It only reloads when the identity-review
fingerprint changes. A new snapshot on disk was not observed by the web process, and no
atomic pointer existed.

DATA-001 adds `active.json`, `resolve_snapshot_dir()`, pointer/review fingerprints and an
in-process reload with fallback to the last validated dataset.

### 7. How is the Device Intelligence index regenerated?

`medradar/product/device/build.py::build_index(dataset)` deterministically rebuilds the
index from the `Dataset`. The CLI `scripts/backfill_device.py` writes derived files for a
fixed snapshot. There is no incremental graph mutation and no safe persisted cache.

The pipeline rebuilds and validates the index for every candidate. That is slower than an
incremental graph, but on this data scale it is the reliable choice.

### 8. Are identity-review decisions preserved across snapshots?

Yes, because the review ledger is a separate SQLite database and the registry overlay is
applied at read time. The snapshot itself contains no review decisions. The pipeline must
therefore never touch the review DB; validation hashes it before/after and the publish path
keeps data and review lifetimes separate.

### 9. Is there code that rewrites first-observed time?

Yes. `load_dataset()` set `first_observed_at = collected_at` for every record in the loaded
manifest, and `org_stats.first_observed_at = collected_at`. That is true for one snapshot but
wrong as a historical first-seen value: every new snapshot would claim all old records were
first seen today.

DATA-001 stores per-record `first_observed_at`, preserves it through observations/previous
snapshots, and updates the old invariant test to require preservation rather than equality
with the latest collection time.

### 10. Which steps are expensive on 2 vCPU / 4 GB?

* the full openFDA scoped collection: 1.2 GB of responses, 241 requests, minutes;
* holding the previous snapshot + candidate + collector records at once;
* the product `Dataset` load and full device-index build during validation;
* loading two full `Dataset` objects at once (old and new) if a restart-based reload is used.

The pipeline therefore serialises collection, drops the candidate event map before product
validation, drops the validator's raw event list before product load, uses one process lock,
and proposes a bounded systemd unit. Measured isolated peak: 1.98 GiB for recall; bootstrap
1.40 GiB.

## B. Official openFDA source findings (live verified)

### Update field and frequency

* 510(k): `/device/510k.json`, `meta.last_updated`, monthly declared.
* PMA: `/device/pma.json`, `meta.last_updated`, monthly declared. Originals and supplements
  share this endpoint and version.
* Recall: `/device/recall.json`, `meta.last_updated`, weekly declared.
* Classification: `/device/classification.json`, `meta.last_updated`, monthly declared.

Live probe on 2026-11-15/16:

| Source | `last_updated` | total |
|---|---:|---:|
| 510(k) | 2026-11-02 | 176,625 |
| PMA | 2026-11-02 | 57,487 |
| Recall | 2026-11-12 | 59,705 |
| Classification | 2026-11-02 | 7,098 |

### Rate limits

Official docs: 240 requests/minute and 1,000/day without a key; 240/minute and 120,000/day
with a key. The client enforces 60/minute and 900/day without a key (100,000/day with a key),
consumed before each attempt.

### Filtering, pagination and maximum results

* Date-range filters work with range syntax:
  `search=decision_date:[2026-10-01+TO+2026-10-31]`.
* `limit` maximum is 1,000 for search requests.
* `skip` must be ≤25,000; the effective window is about 26,000 records.
* The collector partitions larger queries by year/month on the source date field.
* `sort` supports the date field, used to find partition bounds.

### Bulk download

`https://api.fda.gov/download.json` lists official zipped JSON parts. Observed:

* 510(k) 176,625 records, 238.38 MB zip;
* PMA 57,487 records, 21.24 MB zip;
* recall 59,705 records, 276.47 MB zip;
* classification 7,098 records, 3.13 MB zip.

The download page explicitly warns that every update can change any record and that an
up-to-date copy requires re-downloading all parts. Bulk is therefore not a magic
"new-only" feed. This release uses the API scoped reconciliation; the bulk route is a future
option for a global archive.

### Corrections and identifiers

* 510(k): `k_number`.
* PMA original: `pma_number`; supplement: `pma_number + supplement_number`.
* Recall: `product_res_number` (fallback `cfres_id`, `res_event_number`).
* There is no per-record revision timestamp. Corrections to old records are possible and
  must be found by content comparison.
* A filtered query with no match returns HTTP 404 `NOT_FOUND`. An unfiltered probe returning
  404 is an error.
* FDA can correct/withdraw records; a single missing response is not proof of removal.

### Licence and redistribution

openFDA terms/licence are linked in every response meta. The data is public-domain/openFDA
terms with a disclaimer; MedRadar records the official URL and does not present the data as
medical advice. No API key or restricted dataset is required.

### Documentation versus behaviour

The docs' date-range example uses unencoded `+` between dates. A fully URL-encoded `%2B`
inside the range is parsed as a literal plus and returns a 500 `parse_exception`; the
pipeline builds the range with real spaces (encoded as `+` by `urlencode`) and verified the
syntax against live data. This is recorded because "the docs say it works" is not enough.
