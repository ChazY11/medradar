# DATA-001 — Incremental Synchronization and Revision Detection

## Decision: scoped full reconciliation, with change-level increments

openFDA exposes `meta.last_updated` per endpoint, but no per-record "last modified" field for
510(k), PMA, or PMA supplements. Recall records expose `event_date_posted` (new posting) but
not a revision timestamp. Therefore a pure date-window fetch cannot detect corrections to old
records.

DATA-001 separates two things:

1. **Cheap update detection** — one `limit=1` probe per source, every 6/24 hours.
2. **Correct change detection** — on an available update, re-collect the complete reviewed
   scope and compare each record's full content hash.

The second step is a full network reconciliation of the scoped set, but the resulting change
ledger is incremental: only `ADDED`, `UPDATED`, `MISSING_ON_RECHECK`, `REMOVED_CONFIRMED`
and `UNRESOLVED` rows are written. Unchanged records are counted, not written.

This is slower than a date delta and much more correct. The task explicitly permits
re-collection plus record hashing when the API does not support reliable per-record
incremental timestamps.

## Scope

The scope is the reviewed roster in `organizations.json`, not all FDA applicants. For each
organization and source the query is the same shape the legacy collector used:

```text
applicant:("TOKEN" OR "TOKEN" ...)
recalling_firm:("TOKEN" OR "TOKEN" ...)
```

Every query's exact expression, token list, reported total, page count, partitions and
completion flag are stored in the snapshot manifest. A record may be returned by more than
one organization's search; records are de-duplicated by `source_id + official_id` and the
union of scopes is stored in `collection_scopes`.

## Pagination and coverage

* Page size: 1,000 (openFDA's maximum for search requests).
* `skip` is limited by openFDA to 25,000.
* A query whose reported total exceeds 26,000 is split by its own date field:
  * first by year, then by month if a year is still too large;
  * each partition repeats the official total check.
* Any of the following aborts the whole collection, leaving the active snapshot untouched:
  * a page fails after retries;
  * the reported total changes during pagination;
  * the API returns an empty page before the reported total is reached;
  * a query reaches the skip ceiling without partitioning;
  * two payloads for the same official identity disagree within one sweep.
* A 404 with an explicit search and `NOT_FOUND` is a legitimate empty result. It is recorded
  as `reported_total=0`, `complete=true`.
* A 404 on the unfiltered probe is a failed check, never an empty source.

The manifest is explicit about the difference between the endpoint's global `total` and the
scoped records actually retrieved. **"All results for this organization" is not "all FDA
records for this company."**

## New records

A record key is `source_id + official_record_identity`:

* 510(k): `k_number`
* PMA original: `pma_number`
* PMA supplement: `pma_number:supplement_number`
* Recall: `product_res_number` (fallback `cfres_id`, then `res_event_number`)

A key that was absent from the previous snapshot and present now is `ADDED`. It receives:

* `first_observed_at = detection time`;
* `last_synced_at = detection time`;
* official event date unchanged;
* full content hash and snapshot hash;
* collection scope and official URL.

No device name, applicant name, or product code is used as the primary key.

## Revisions

The same official identity with a different **full-record** content hash is `UPDATED`.
The hash is computed before display truncation, so a change in the tail of a long recall
description or PMA statement is still detected. The ledger stores:

* previous and new content hashes;
* previous and candidate snapshot ids;
* changed field names with bounded old/current values;
* official URL and source endpoint;
* the regulatory event date (unchanged).

An update does **not** create a second regulatory event and does not change `event_date`.

## First observed time

`first_observed_at` is preserved from:

1. the record observation table;
2. the previous snapshot's per-record value;
3. the previous snapshot's collection time, only when adopting a legacy snapshot that had no
   per-record value.

It is never rewritten with the newest snapshot time. The old PRODUCT-001 behavior (every
record's first observation equals the current snapshot time) was a truthful statement about
that one snapshot but not a historical first-seen record; DATA-001 replaces it and adds a
regression test.

## First reconciliation after adopting a legacy snapshot

A legacy snapshot stored a display projection: selected source fields, already truncated. A
new full-record hash cannot be compared with that projection without reporting every one of
91,457 records as `UPDATED`. On the **first** reconciliation of a source whose official
version was not recorded by the legacy snapshot, the pipeline:

* compares only the fields that the legacy projection actually contained;
* records matching records as unchanged (counted in `rebaseline`);
* records a real visible difference as `UPDATED`;
* establishes the full content hash going forward.

This is a one-time schema transition, not a fabricated revision. The snapshot manifest
records `first_reconciliation=true` and `rebaselined` count. From the next source update
onward, full hashes are compared. Fields that the legacy snapshot never stored cannot be
retroactively diffed; this is stated in `KNOWN_LIMITATIONS.md`.

## Missing records and deletion

A record absent from a complete scoped sweep is **not deleted**:

| Situation | State | Snapshot behavior |
|---|---|---|
| First complete sweep with record absent | `MISSING_ON_RECHECK` | retained with previous content |
| Second complete sweep absent, exact-ID recheck absent | `REMOVED_CONFIRMED` | removed from candidate |
| Query scope changed | `QUERY_SCOPE_CHANGED` (`UNRESOLVED` change row) | retained |
| Exact-ID recheck failed/cap exceeded | `UNRESOLVED` | retained |
| Reappeared on exact recheck | `UPDATED` or unchanged | restored/updated |

The exact-ID recheck is capped at 50 records per run. If more are missing, none is confirmed
removed; all are retained as unresolved. A confirmed removal can still be blocked by the
record-drop gate in validation. An operator must explicitly allow a percentage drop beyond
the configured threshold.

## Duplicate and idempotency behavior

* Duplicate official identities within a sweep are de-duplicated. Conflicting payloads raise.
* Change rows use a deterministic fingerprint of
  `source_id|event_id|change_type|previous_hash|new_hash`. Repeating the same publish
  attempt does not produce duplicate rows.
* A repeat check with the same official version and total returns `NO_CHANGE`; no snapshot is
  built.
* A source version change with no record change still creates a snapshot with a new source
  version and zero `ADDED`/`UPDATED` rows. That is a metadata-only publication, not a fake
  event.
* The per-source official version, not a local clock, decides whether a candidate is new.

## What is not implemented

* No per-record official revision timestamp exists to consume.
* No global FDA-universe archive; only the reviewed scope is collected.
* No incremental HTTP delta is used as the sole sync mechanism.
* No automated deletion on one missing response.
