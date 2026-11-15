# DATA_COVERAGE

What the device module covers, what it does not, and the exact numbers behind every statement.

## Input data

One immutable openFDA snapshot: `medradar/product/snapshot/` (id `2026-11-14T22:09:22Z-openfda`,
collected 2026-11-14, openFDA last updated 2026-11-02, model 91,457 records). No new data source was
added for PRODUCT-003, and the device index is derived from the same committed files (no new
committed data artefacts, no governance exception needed).

## Coverage by application

| Source | Records | Applications | Device identities |
|---|---|---|---|
| openFDA 510(k) | 23,400 | 23,400 | 23,400 |
| openFDA PMA originals | 574 | 574 | 574 |
| openFDA PMA supplements | 37,658 | 37,658 (in 630 families) | 0 (versions, not devices) |
| FDA device recalls | 29,825 | 0 | 0 (records, not identities) |
| **Total** | **91,457** | **61,632** | **23,974** |

## Product families

* 630 PMA families: 574 with the original approval in the snapshot, **56 supplement-only** (the
  original PMA is not in this snapshot; the family is labelled and never fabricated).
* 612 families have at least one supplement; the largest is `P980016` with 934 supplements.
* No 510(k) family exists in the product, because openFDA exposes no family identifier for 510(k)
  submissions. The alternative - grouping by name - would be a candidate, not a family.

## Recall linkage

| | Recalls | Share |
|---|---|---|
| Linked by the official `k_numbers` field to an application in this snapshot | **15,022** | 50.4% |
| Reference only applications outside this snapshot (8,457 external edges) | 6,227 | 20.9% |
| No official reference at all (unlinked browser) | **8,576** | 28.8% |
| Total | 29,825 | 100% |

The 8,576 unlinked recalls are visible in `/devices?view=unlinked` and served by
`GET /api/devices/unlinked` with a reason per record. They are not deleted and not guessed.

## Relation coverage per device

| Devices | Count |
|---|---|
| With at least one confirmed relation (own application, PMA hierarchy or official recall reference) | 4,496 |
| With candidate relations only | 4,736 |
| With no relation at all | **14,742** |

Most 510(k) devices have no relation beyond their own application. That is a property of the source,
not a backlog MedRadar can close by guessing, and the device page says so.

## Explicitly out of scope in this release

| Not covered | Why it is not covered |
|---|---|
| Predicate relationships | openFDA exposes no predicate identifier; the 510(k) summaries were not collected |
| UDI / GUDID device identifiers | not collected; would need its own governance review and adds no identity that the application does not already provide |
| EU MDR / CE, NMPA, global registries | out of scope by design; the product says so on the sources page |
| Commercial product / SKU catalogue, pricing, market share | not public regulatory data and not claimed anywhere |
| Cross-pathway device equivalence | no official identifier or document in this data establishes it |
| Manufacturer of record | the applicant field is a record claim; shown as applicant with attribution status |
| Device-level accuracy estimate | no independent sample reviewed; the quality report returns UNKNOWN |

## Performance

* Device index built lazily on the first device request of a process: **~4.7 s** for 91,457 records
  (61,632 applications, 77,751 relations), cached in memory for the process.
* Explorer query (24k devices): ~90 ms; organization filter: ~10 ms; device detail: ~10 ms; quality
  report: ~190 ms. No query blocks the organization or event pages, which never build the index.
* The explorer response states `index_build_ms` so the first-request cost is visible, not hidden.
