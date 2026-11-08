# openfda_device_registrationlisting - probe notes

- **status**: `VERIFIED_API`
- **run at**: `2026-11-08T21:52:29.258372Z`
- **requests made**: 2
- **evidence dirs**: `probes/openfda_device_registrationlisting/`, `samples/openfda_device_registrationlisting/`

## What was tested

Two requests: an unfiltered page (337,116 records reported) and a registrant search for `Medtronic`. Both returned HTTP 200 and real establishment records.

## Verdict

VERIFIED_API. Establishment-level data: `registration`, `k_number`, `pma_number`, `products[]`, `proprietary_name`. The probe verified the top-level keys only; the inner `registration` object's date fields were **not** enumerated, so this source is deliberately recorded with no clock at all rather than an assumed one.

## Time semantics (`event_at` vs `source_public_at`)

No clock claimed. Only the endpoint-level `meta.last_updated` is visible, and it dates the endpoint, not the establishment. `source_public_at` and `event_at` are empty with quality `unknown`.

## Cross-national product identity

Stable product ID: **no** - the identity here is the establishment (`registration_number` / `fei_number`), i.e. a facility, not a product. It does carry `k_number` and `pma_number` references, so it is a **registrant-level bridge** to clearances. It must never be counted as a second clearance record: one clearance can appear on many establishments.

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `page_smoke` | 200 | 6803 | 2250 | <https://api.fda.gov/device/registrationlisting.json?limit=2> |
| `search_registrant_medtronic` | 200 | 5060 | 1141 | <https://api.fda.gov/device/registrationlisting.json?search=registration.name%3A%22Medtronic%22&limit=2> |

## Probe-level note

Registration & listing is establishment-level (who may distribute what), not product-level; it carries k_number/pma_number per establishment which makes it a registrant bridge, but it must not be counted as a second clearance record.

## Documentation opened

- endpoint: https://open.fda.gov/apis/device/registrationlisting/

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
