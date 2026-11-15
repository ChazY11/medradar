# DATA-002 — Source Isolation Contract

## Problem

DATA-001's `run()` checked all sources, then passed `ALL_SOURCE_IDS` into `_sync_locked()`.
`_targets()` raised on any `CHECK_FAILED` / `SOURCE_DEGRADED` source. A temporary 510(k)
probe failure therefore blocked a perfectly healthy recall update. That is unacceptable for a
continuous collector.

## Behaviour now

`run()` classifies each source independently after the scheduled checks:

| Source state | This run |
|---|---|
| `UPDATE_AVAILABLE`, healthy | eligible for collection |
| `NO_CHANGE`, healthy | not collected; may be selected by the rolling full sweep |
| `UNKNOWN`, healthy with update | eligible for one baseline reconciliation |
| `CHECK_FAILED` | **skipped**, old events retained, source marked failed, hourly retry |
| `SOURCE_DEGRADED` | **skipped**, old events retained, manual/degraded review required |

A healthy source is collected even if another source failed. Collection itself is wrapped
per source (`isolate_sources=True` for automatic runs). A collection failure:

* records `source_collection_failed`;
* sets the source to `CHECK_FAILED` and increments consecutive failures;
* discards that source's partial candidate records;
* keeps its previous events and official version;
* does not prevent another source's candidate from being published.

## Snapshot semantics

Every new snapshot contains an explicit version/status for **all four** sources, not only the
ones updated. For a failed or deferred source:

* `official_last_updated` / `official_total` remain those of the events actually present;
* `sync_status` is `FAILED` or `UNCHANGED`;
* `last_sync_error` records the reason;
* `source_outcomes` carries the same facts for machine consumers;
* `change_summary.partial` is `true` and lists `failed_sources`.

A source is never marked `SYNCED` unless its collection succeeded and the containing snapshot
was published. A failed source is not written to `last_success_sync_at`.

## Combined snapshots and the device index

PMA originals/supplements are one official source with one version. Recall and 510(k) remain
separate sources. The candidate is built from the previous snapshot plus only the successful
sources' replacement events. Therefore a partial snapshot is internally consistent: each
source's records are all from the version stated for that source.

The validator still runs the same complete product + device-index checks. Source isolation
does **not** relax a single quality gate. If a partial candidate cannot validate, it is not
published; the previous snapshot remains active.

## Automatic memory cap versus manual combined runs

`MEDRADAR_PIPELINE_MAX_PRODUCT_SOURCES_PER_RUN` defaults to **1** on the 4 GB host. If two
product sources are both due, the first is published this hour, the second stays
`UPDATE_AVAILABLE` and is collected on the next hourly wake-up. This is an explicit partial
publication, not a failure. Acceptance test
`test_multiple_sources_update_in_one_partial_snapshot` exercises a combined two-source
snapshot with the cap raised, proving the format is supported.

## Tests

`tests/data_pipeline/test_pipeline.py` now covers:

* one source check failure while another source publishes;
* one source collection failure while another source publishes;
* all product sources failed → `BLOCKED`, active snapshot unchanged;
* two sources updated into a combined snapshot;
* partial failure followed by recovery;
* retry does not duplicate ledger rows;
* partial snapshot source versions are the old version for the failed source;
* default one-source-per-run leaves the other sources `update_available`.
