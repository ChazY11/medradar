# canada_mdall - probe notes

- **status**: `VERIFIED_API`
- **run at**: `2026-11-08T21:53:32.914756Z`
- **requests made**: 8
- **evidence dirs**: `probes/canada_mdall/`, `samples/canada_mdall/`

## What was tested

Eight requests: the API documentation page, `company/?company_name=` for all five target firms (Medtronic 29 companies, GE HealthCare 16, Philips 31, Dräger 4, Mindray 2), `licence/?company_id=` for the first Medtronic entity (461 active licences) and a `deviceidentifier/?device_identifier=` DI bridge probe.

## Verdict

VERIFIED_API. Health Canada publishes a documented JSON/XML API with no key and no session: `company` / `licence` / `device` / `deviceidentifier` / `licencetype` / `sbdlocation`. The unfiltered `state=active` device dump is too large to finish inside a timeout, so queries must be scoped by `company_id`, `licence_number` or `device_identifier`.

## Time semantics (`event_at` vs `source_public_at`)

This is the source where the protocol's time trap is live. A licence row exposes exactly three dates: `first_licence_status_dt`, `last_refresh_dt`, `end_date` (confirmed from the response itself). `last_refresh_dt` is a **database refresh stamp** and `end_date` is a **cancellation date**; using either as a first-publication date would be the error the protocol forbids. MDALL publishes no per-record publication date, so `source_public_at` is derived from `first_licence_status_dt` and flagged `derived`.

## Cross-national product identity

Stable product ID: **yes** - the MDALL licence number, plus `company_id` and `device_id`. Linkable to FDA DI: **officially in principle** - `/deviceidentifier/` accepts a real UDI-DI - but **sparse in practice**: the sampled Medtronic DI (a US-only device) returned 0 rows, so the bridge only covers devices actually licensed in Canada. Linkable to FDA 510(k)/PMA: no field; a link would have to be built from manufacturer + trade name, i.e. a **candidate**. Note also that `company/?company_name=` is a `%LIKE%` match, which is why 'MEDTRONIC' returns 29 distinct companies - company resolution must go through the alias index, not the substring hit.

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `api_documentation` | 200 | 72027 | 718 | <https://health-products.canada.ca/api/documentation/mdall-documentation-en.html> |
| `company_search_medtronic` | 200 | 6909 | 530 | <https://health-products.canada.ca/api/medical-devices/company/?company_name=MEDTRONIC&type=json> |
| `company_search_ge_healthcare` | 200 | 3836 | 546 | <https://health-products.canada.ca/api/medical-devices/company/?company_name=GE+HEALTHCARE&type=json> |
| `company_search_philips` | 200 | 7604 | 718 | <https://health-products.canada.ca/api/medical-devices/company/?company_name=PHILIPS&type=json> |
| `company_search_draeger` | 200 | 928 | 1625 | <https://health-products.canada.ca/api/medical-devices/company/?company_name=DRAEGER&type=json> |
| `company_search_mindray` | 200 | 532 | 594 | <https://health-products.canada.ca/api/medical-devices/company/?company_name=MINDRAY&type=json> |
| `licence_by_company` | 200 | 131018 | 67639 | <https://health-products.canada.ca/api/medical-devices/licence/?company_id=114663&state=active&lang=en&type=json> |
| `device_identifier_00643169718425` | 200 | 2 | 1610 | <https://health-products.canada.ca/api/medical-devices/deviceidentifier/?device_identifier=00643169718425&state=active&type=json> |

## Probe-level note

Health Canada publishes a documented JSON/XML API (no key) for MDALL: company / licence / device / deviceidentifier. `first_licence_status_dt` (licence) and `first_licence_dt` (device) are the only real dates; `last_refresh_dt` is a database refresh stamp and `end_date` is a cancellation date, so neither may be used as the first-publication date. The deviceidentifier endpoint takes a real UDI-DI, which is an official bridge to GUDID for devices sold in both markets.

## Documentation opened

- API guide: https://health-products.canada.ca/api/documentation/mdall-documentation-en.html
- dataset metadata (Open Government Licence - Canada): https://open.canada.ca/data/en/dataset/c801a084-210b-4cd2-8513-26a00b66eb6f
- human search UI: https://health-products.canada.ca/mdall-limh/

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
