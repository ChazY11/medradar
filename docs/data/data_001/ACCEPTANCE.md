# DATA-001 — Acceptance

This file distinguishes what was implemented and tested from what was deployed. A code test
or a local isolated run is not a production deployment.

## Gate summary

| Gate | Status | Evidence |
|---|---|---|
| G1 Source freshness | **PASS** | Live probe of all four endpoints; statuses `NO_CHANGE`/`UPDATE_AVAILABLE`/`CHECK_FAILED`/`SOURCE_DEGRADED`/`UNKNOWN`; HTTP failure never becomes no-change; 404 semantics. |
| G2 Change detection | **PASS** | Offline scenarios: add, update, duplicate sync, first reconciliation rebaseline, missing recheck, confirmed removal; deterministic change ids; repeated builds do not duplicate rows. |
| G3 Data safety | **PASS** | Fault-injection tests: collection failure leaves old active; corrupt hash/duplicate ids/missing files/record drop block publication; atomic pointer and rollback. |
| G4 Product consistency | **PASS** | Candidate validation loads the product dataset and builds the device index; new snapshot served by API in tests; PMA families, 510(k) devices, recall evidence and review DB compatibility. |
| G5 Operations | **PASS (software) / NOT DEPLOYED** | Single-writer lock, source due/retry, request budget, systemd service/timer templates, status/incident tables. Timer was not installed and no production unit was changed. |
| G6 Transparency | **PASS** | `/api/data-status`, `/api/changes`, Data Status page, real snapshot/source/version/check/sync/change counts; unconfigured state is explicit and has no fake dates. |
| G7 Real-world acceptance | **PASS (isolated)** | One real openFDA scoped reconciliation in an isolated state root; report below. Production was intentionally not modified. |

## Test inventory

`python -m pytest tests/data_pipeline tests/product -q`

The DATA-001 suite covers:

1. **No change** — after the first reconciliation, a repeat check does not create a snapshot
   or a change row.
2. **New record** — new official id is `ADDED`, first observed is recorded, product events
   include it, repeat sync does not duplicate it.
3. **Revision** — same official id with a changed field is `UPDATED`; old and new values are
   kept; event date is unchanged.
4. **Network failure** — collection failure leaves the old pointer and old web dataset.
5. **Validation failure** — corrupt file, duplicate event id, incomplete coverage, missing
   file, and record-count drop block publication.
6. **Publish and rollback** — a candidate is published; rollback returns the pointer to the
   prior validated snapshot; a newer snapshot is not deleted.
7. **First-observed preservation** — later snapshots do not rewrite historical first-seen
   time; legacy fallback is explicit; first reconciliation does not report 91k fake updates.
8. **Removal policy** — one missing sweep retains; a second complete sweep plus exact-ID
   recheck confirms removal; the drop gate still requires explicit review.
9. **Detector states** — no-change, update, check failure, three-failure degrade, source total
   drop, version regression, missing baseline.
10. **API/UI integration** — `/api/data-status`, `/api/changes`, `/data-status` route, and
    unconfigured-state semantics.
11. **Locking** — a second concurrent pipeline operation is refused.
12. **Pointer safety** — path escape, malformed pointer, manifest/id mismatch are rejected.

The existing PRODUCT-001/002/003 suite and the DATA-001 suite together collect 161 tests;
all pass. The broader `medradar selftest` runs 1,270 tests (3 skipped, OK).

## Scenario evidence

### Scenario A — no new data

Offline: `test_no_change_does_not_publish_a_snapshot`.
Live: after the real reconciliation, a repeated probe with the same source versions yields
`NO_CHANGE`; no new snapshot is created unless the source version changes.

### Scenario B — new FDA record

Offline with official-format fixtures: `test_added_record_is_published_and_visible_to_product`.
The candidate is validated, published, and appears in `events.jsonl.gz`; the record's
`first_observed_at` is new while the official event date is unchanged.

### Scenario C — historical revision

Offline: `test_updated_record_keeps_event_date_and_records_old_and_new_values`.
A changed `device_name` produces one `UPDATED` row with `previous`/`current` values and no
second event identity.

### Scenario D — network failure during collection

Offline: `test_collection_failure_keeps_the_old_active_snapshot`.
The candidate is abandoned; the active pointer is unchanged; the status run is failed and
the incident/error is recorded.

### Scenario E — invalid candidate

Offline: `test_validator_rejects_corrupt_hash_duplicate_ids_and_record_drop`.
The validator returns a non-empty error list and the pipeline status is `BLOCKED`; no pointer
switch occurs.

### Scenario F — publish and rollback

Offline: `test_rollback_switches_pointer_to_verified_prior_snapshot`.
The baseline and newer snapshot both remain on disk; the active pointer returns to the
baseline and the product loader resolves it.

### Scenario G — real FDA reconciliation

See `DELIVERY_REPORT.md` and `evidence/real-sync.json`. It is a real openFDA recall
reconciliation in an isolated state root on the 2 vCPU / 4 GB host, not the production data
directory: 85 requests, 901,187,267 response bytes, 4:01, 1.98 GiB peak RSS, 0 added, 0
updated, 0 removed. Production remained healthy on the old snapshot.

## What is not claimed

* The production timer is not enabled.
* The production service was not switched to the pipeline data root.
* No new records were required; a zero-change real run is still a valid chain test.
* No external alert was configured.
* No AI summary/forecast is part of DATA-001.
