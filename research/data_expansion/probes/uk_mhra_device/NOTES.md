# uk_mhra_device - probe notes

- **status**: `UNAVAILABLE`
- **run at**: `2026-11-08T21:59:18.612348Z`
- **requests made**: 2
- **evidence dirs**: `probes/uk_mhra_device/`, `samples/uk_mhra_device/`

## What was tested

Two requests to the GOV.UK search API, filtered to MHRA: 'medical device register' and 'public register medical devices searchable'. Both returned HTTP 200 with guidance items only.

## Verdict

UNAVAILABLE, structurally. The results are guidance ('Register medical devices to place on the market', 'Regulating medical devices in the UK'), not a register of licensed products. The UK has no searchable public device register equivalent to MDALL / EUDAMED / GUDID: MHRA registration is an obligation on the manufacturer and is not published as a product listing. No amount of retrying would produce data.

## Time semantics (`event_at` vs `source_public_at`)

UNKNOWN - nothing to date.

## Cross-national product identity

Stable product ID: none exists in public form. The UK therefore cannot anchor a device identity, which means UK market entry cannot be dated from an official register at all.

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `govuk_search_medical_device_register` | 200 | 2396 | 375 | <https://www.gov.uk/api/search.json?q=medical+device+register&filter_organisations=medicines-and-healthcare-products-regulatory-agency&count=5&fields=title%2Clink%2Cdescription%2Cpublic_timestamp> |
| `govuk_search_public_register` | 200 | 1549 | 297 | <https://www.gov.uk/api/search.json?q=public+register+medical+devices+searchable&filter_organisations=medicines-and-healthcare-products-regulatory-agency&count=3&fields=title%2Clink%2Cpublic_timestamp> |

## Probe-level note

GOV.UK search for MHRA device material returns only *guidance* (how a manufacturer registers a device), not a public register of licensed products: the UK has no searchable public medical-device register equivalent to MDALL/EUDAMED/GUDID. There is therefore no product-level UK regulatory dataset to collect.

## Documentation opened

- GOV.UK search used: https://www.gov.uk/api/search.json?q=medical+device+register&filter_organisations=medicines-and-healthcare-products-regulatory-agency

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
