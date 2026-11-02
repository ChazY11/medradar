# TKG ⇐ real `events` integration (Phase 3B)

Bitemporal knowledge-graph integration for the research database
(`data/research.sqlite`, gitignored): the real `events` table is imported through
the existing read-only adapter into an append-only TKG store, exported as a
deterministic point-in-time snapshot, and exposed to research code through
read-only graph-context helpers.

Status: **real 55,090-row import executed** on branch `phase3/tkg-integration`
(base `bffc9d2`), Python 3.12.10. Full suite: **636 tests OK (skipped=3)**
(625 existing + 11 new in `tests/test_tkg_integration.py`).

- Import driver: `scripts/tkg_import_research.py`
- Read-only helpers: `medradar/intelligence/graph_context.py`
- Committed evidence: `experiments/reverse_rd_v2/tkg_import_report.json`
- Tests: `tests/test_tkg_integration.py`

**Not committed** (gitignored on purpose): `data/tkg.sqlite` (~186 MiB) and
`out/tkg_import/snapshot.json` (~200 MB). They are rebuildable with the command
below.

## What is imported (and what is not)

Imported: **existence + stated fields + stated containment** from the `events`
table, via `medradar.tkg.adapter.import_events` (source opened `mode=ro`):

| TKG fact | Source column | Real count |
|---|---|---|
| `event` node | one row in `events` | 55,090 nodes |
| `company` entity + `company_event` edge | `company_key` (when present) | 51 companies, 21,670 edges |
| `track` entity + `event_in_track` edge | `track_id` (when present) | 38 tracks, 37,782 edges |
| `product_code` entity + `event_has_code` edge | `product_code` (when present) | 2,202 codes, 54,967 edges |

The edge counts match the non-null column counts exactly (33,420 rows have no
`company_key`, 17,308 no `track_id`, 123 no `product_code`), i.e. **no relation
is invented**: no ownership, technology, competition or investment edges, no
entity resolution beyond identifiers already present in the source, no
deduplication against the outside world. Company/track/product entities are
conservative "this identifier exists in the source registry" stubs.

Event attributes are the source's own claims (`source`, `kind`, `event_date`,
`title`, `first_seen_at`, `available_at`, `timestamp_quality`) plus evidence
provenance (`source_locator` = row URL, `evidence_sha256` = content hash of the
assertion, `evidence_kind = source_observed`, `confidence = 1.0`).

## Time semantics (the point of the bi-temporal store)

| TKG field | Meaning | Where it comes from |
|---|---|---|
| `recorded_at` | **knowledge time** (when the system learned it) | assigned inside the store from the real clock at import time; callers cannot backdate or future-date it |
| `valid_from` / `valid_to` | **valid time** (when the fact is true) | `event_date` (date-only, widened to `T00:00:00.000000Z`), half-open `[from, to)` |
| `public_time` / `public_time_basis` | optional public-availability metadata | `available_at` + `timestamp_quality` — never used as a clock |

`known_at` queries gate `recorded_at`; `valid_at` queries gate the valid
interval. A snapshot selects the latest revision visible at `known_at` first and
*then* applies the validity filter, so later corrections/retractions cannot
resurrect older revisions. `valid_at=None` defaults to `known_at` (see
`medradar.tkg.export.export_snapshot`).

Honest caveat: this run is a **backfill**, so knowledge time is the backfill
observation time (2026-11-02), not the historical publication date. Every source
row also carries `first_seen_at = 2026-11-01` (bulk load date), and the source's
`available_at` values are timezone-naive, so the adapter drops them as unusable
public-time metadata (`invalid_public_time_dropped = 55,090`; exported
`public_time` is `null` for every row). The PIT machinery is demonstrated, not
historical information availability; incremental ingestion with real observation
timestamps is what makes backtesting possible later.

## Real run evidence (2026-11-02, Python 3.12.10)

Source: `data/research.sqlite`, 289,443,840 bytes,
sha256 `dd241bfec138d7977d7eb8f4c1db25119d59b6fe7ff573060b24d14eeeb71e0d`
**before and after** the import (source provably unchanged; opened `mode=ro`).
Rows: 55,090 (`510k` 31,219 · `pma` 23,871; `event_date` 2016-11-01 → 2026-10-18).

| Quantity | Value |
|---|---|
| Assertions created (first import) | **171,800** (55,090 nodes + 2,291 entity stubs + 114,419 edges) |
| Idempotent duplicates inside the first batch | 112,128 |
| Rows skipped (missing id / missing date / invalid) | 0 |
| Store: nodes / edges / entities / idempotency keys | **57,381 / 114,419 / 57,381 / 171,800** |
| Store file size (not committed) | 194,723,840 bytes (~186 MiB) |
| Import time | **32.59 s** (1,690 rows/s) |
| Idempotent re-import (same process) | created **0**, duplicates 283,928, **13.66 s**, counts unchanged |
| Re-run of the whole script on the reopened store | created **0**, duplicates 283,928, same store counts |
| Snapshot `known_at` | `2026-12-31T00:00:00Z` (`valid_at` defaults to the same) |
| Snapshot counts | **57,381 nodes / 114,419 edges** |
| **`snapshot_sha256`** | **`b60c8360656d15def5f7a81115ab069e48fb21281ac8d51167667c226c3010f3`** |
| Re-export at the same cutoffs | identical sha256 (`true`) |
| Export / re-export / write `snapshot.json` | 6.51 s / 7.30 s / 5.70 s |
| Whole script wall time | 67.6 s |

Node breakdown: `event` 55,090 · `product_code` 2,202 · `company` 51 · `track` 38.
Edge breakdown: `event_has_code` 54,967 · `event_in_track` 37,782 · `company_event` 21,670.

### Point-in-time gating (real store)

| `known_at` | nodes | edges | `snapshot_sha256` |
|---|---|---|---|
| `2026-01-01T00:00:00Z` (before the import) | **0** | **0** | `d2da586ae329ffe0cf93631411f8ea2f9c4004a20a122e88978ecba07de05ab3` |
| `2026-12-31T00:00:00Z` (after the import) | 57,381 | 114,419 | `b60c8360…3010f3` |

So the knowledge-time gate is physically enforced: a query at a knowledge time
before the backfill sees an empty graph; after it, the full one. (A more
interesting intermediate PIT view requires incremental ingestion — see caveats.)

### Determinism caveat (honest)

Re-exporting the **same store** at the **same cutoffs and versions** is
byte-identical (demonstrated above; also asserted on every script run). A fresh
import, however, produces a different `snapshot_sha256`, because `recorded_at` is
the real observation time and therefore differs across runs — that is the
intended semantics, not a defect. The committed hash is pinned to the store
built in this run.

## Graph-context helpers (`medradar/intelligence/graph_context.py`)

Read-only (`mode=ro`, `PRAGMA query_only`) as-of helpers; they reuse the store's
own latest-revision/validity selection primitives and never mutate the store
(verified by hashing the TKG file before/after).

```python
from medradar.intelligence.graph_context import graph_context, timeline, counts

ctx = graph_context(
    "data/tkg.sqlite",
    company_key="medtronic", track_id="cardiac_rhythm",
    known_at="2026-12-31T00:00:00Z",   # knowledge cutoff (recorded_at)
    valid_at=None,                      # optional independent validity cutoff
)
ctx["status"]        # "ok" | "empty"
ctx["counts"]        # nodes/edges/events/products (+ per-type breakdown)
ctx["company"], ctx["track"], ctx["events"], ctx["products"], ctx["nodes"], ctx["edges"]
                     # each node/edge: type, id, assertion_id, valid_from/valid_to,
                     # recorded_at, seq, evidence provenance, confidence, attrs

timeline(...)        # pair events sorted by (valid_from, event_id), provenance included
counts("data/tkg.sqlite", known_at=...)  # whole-store visible counts by node/edge type
```

Pair semantics: an event belongs to the `(company_key, track_id)` context iff it
has **both** a `company_event` edge from that company and an
`event_in_track` edge into that track under the cutoffs; product codes come from
those events' `event_has_code` edges. Edges are emitted only when both endpoints
are visible (same endpoint contract as `TKGQuery.snapshot`). Unknown identities
or pairs without shared events return `status="empty"` with an explicit
`reason` — never a fabricated link. The whole output is deterministically sorted.

Real-data smoke test (same store, `known_at=2026-12-31T00:00:00Z`):

| Pair (from `events`) | events | products | edges | context | timeline | counts (whole store) |
|---|---|---|---|---|---|---|
| `medtronic` × `cardiac_rhythm` | 2,663 | 14 | 7,989 | 0.50 s | 2,663 rows, 0.45 s | 1.31 s |

`counts()` returns 57,381 nodes / 114,419 edges at the late cutoff, matching the
snapshot manifest exactly; at `known_at=2026-01-01` it returns 0 / 0. The TKG
file hash was unchanged after these read-only calls. (Other large observed pairs:
`boston_scientific`×`cardiac_rhythm` 1,040 events, `abbott`×`cardiac_rhythm` 716,
`edwards_lifesciences`×`structural_heart` 584, `medtronic`×`neurostimulation` 564.)

## Performance notes (55k events) and the honest bottleneck

The events adapter imports each callback as one atomic batch, and `tkg-schema-2`
defines **no index on `nodes/edges.idempotency_key`**. Duplicate-retry lookups
therefore scan the growing tables: measured on real data, importing 10,000 rows
took **50.7 s** without an index and **4.2 s** with one (full 55,090 rows:
projected ~27 min vs **32.6 s** measured). `scripts/tkg_import_research.py`
therefore creates two *operational* indexes on the target store before importing
(`tkg_import_nodes_idempotency`, `tkg_import_edges_idempotency`). They are local
store plumbing — not committed, not part of the exported artefact, and they do
not change any exported content or hash. The schema-level fix (an indexed
idempotency key in a future `tkg-schema-3`) is out of this task's scope.

## Limitations

- **Backfill, not historical knowledge**: `recorded_at` = backfill observation
  time; the source's `first_seen_at` is a bulk-load date, so pre-import PIT
  snapshots are empty by design. Incremental ingestion is required for
  publication-time-aware backtests.
- **Public-time metadata is empty** in this import: source `available_at` values
  are timezone-naive and are dropped (`invalid_public_time_dropped=55,090`)
  rather than guessed.
- **Static taxonomy**: company/track/product identifiers are the source's own
  columns; no entity resolution, no inferred investment/ownership/competition
  edges, no external deduplication.
- **Single writer per store file** (documented in the TKG layer); this script is
  not a concurrent ingester.
- The store and the exported snapshot are **not** committed; only the report and
  code are.
- Snapshot hashes are store-specific (knowledge time = observation time), see the
  determinism caveat above.

## Reproduce

```bash
# 1) full real import + PIT snapshot + idempotency/determinism checks (~68 s, no network)
python scripts/tkg_import_research.py --db data/research.sqlite --tkg data/tkg.sqlite \
    --known-at 2026-12-31T00:00:00Z --report-out experiments/reverse_rd_v2/tkg_import_report.json

# 2) re-run on the reopened store: import created must be 0, snapshot hash identical
python scripts/tkg_import_research.py --db data/research.sqlite --tkg data/tkg.sqlite \
    --known-at 2026-12-31T00:00:00Z --no-write-export

# 3) quick offline subset smoke (creates a throwaway store)
python scripts/tkg_import_research.py --db data/research.sqlite --tkg data/tkg_smoke.sqlite \
    --known-at 2026-12-31T00:00:00Z --kinds 510k --limit 500 --no-write-export

# 4) tests (synthetic, no network) and the full suite
python -m pytest tests/test_tkg_integration.py -q      # 11 passed
python -m medradar selftest                            # Ran 636 tests ... OK (skipped=3)
```

The script exits non-zero and lists `failures` if the source hash changed, the
re-import created assertions, the store grew, or the re-export hash differs.
