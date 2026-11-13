# usaspending — probe notes

**Status: VERIFIED_API** · 18 requests · 2026-11-09 · no API key, no registration

## What was tested

| # | Request | Result |
|---|---|---|
| 1 | `POST /api/v2/search/spending_by_award/` keyword `stent`, 10 fields | 200, real awards |
| 2 | `GET /api/v2/awards/<generated_internal_id>/` | 200, award detail |
| 3 | `GET /api/v2/references/agency/1/` | 200 |
| 4–18 | per target firm: `recipient_search_text` search (10 rows) + `spending_by_award_count` + `POST /api/v2/autocomplete/recipient/` | 200 for all |

Discovery recorded because it cost requests: `/api/v2/autocomplete/recipient/` is
**POST-only** — a GET returns 405, which burned five requests in an earlier run
of this probe. The final run uses POST.

## Why the field list matters

`Start Date` came back as a period-of-performance start (e.g. `2013-04-11`) and the
award detail exposes `date_signed` separately. **USAspending publishes event dates,
not a publication date.** There is no "first public visibility" field anywhere in
the schema, so `source_public_at` cannot be honestly derived from this source — see
`registry/sources/usaspending.json`, `known_limitations`.

## The recipient-search trap (measured, not asserted)

`recipient_search_text` is a **token** search:

* `"GE HealthCare"` returned `CHANGE HEALTHCARE TECHNOLOGIES, LLC`,
  `CHANGE HEALTHCARE OPERATIONS, LLC`, … — on the first page only **1 of 10**
  names resolved to GE HealthCare through `identity.CompanyIndex`.
* `spending_by_award_count` for `"Medtronic"` reports 97,663 contract actions —
  that is "recipients whose name contains the token", an upper bound, **not** a
  count of Medtronic awards.

Both facts are carried into `samples/procurement/FIVE_FIRM_PROBE.json`, where each
returned recipient name is resolved and confirmed/candidate/other counts are
reported separately.

## No product identity

`Description` is free text written by a contracting officer (max length observed
134 chars). There is no UDI, no 510(k), no model field. A keyword hit in a
description is **not** a product link; the register says so explicitly.

## Docs opened

* <https://api.usaspending.gov/> (200)
* <https://api.usaspending.gov/docs/endpoints> (200)

## Artifacts

* `requests.jsonl`, `PROBE_RESULT.json`, `FIRM_ROWS.json` (per-firm rows + counts)
* samples: `../../../samples/usaspending/` (18 files, each hash-verified in `SAMPLES.json`)
