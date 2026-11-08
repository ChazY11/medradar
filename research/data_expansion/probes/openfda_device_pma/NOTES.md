# openfda_device_pma - probe notes

- **status**: `VERIFIED_API`
- **run at**: `2026-11-08T21:50:48.731550Z`
- **requests made**: 8
- **evidence dirs**: `probes/openfda_device_pma/`, `samples/openfda_device_pma/`

## What was tested

Eight requests mirroring the 510(k) probe: bounded 2024 window, 2025 count, five applicant searches, deep-pagination probe. Two applicant variants returned no rows (the phrase forms that do not match a filed submitter string), the rest returned real PMA records.

## Verdict

VERIFIED_API. PMA originals and supplements are both present. A supplement is a separate regulatory record under the same `pma_number`, so counting rows over-counts devices while counting distinct `pma_number` under-counts post-approval activity - the connector keeps `pma_number/supplement` as the record id for that reason.

## Time semantics (`event_at` vs `source_public_at`)

Same as 510(k): `decision_date` is an event clock and there is no per-record publication date, so `source_public_at` is derived from the decision date and flagged `derived`.

## Cross-national product identity

Stable product ID: **yes** - `pma_number` (+ `supplement_number`), official. Linkable to FDA DI/UDI: same reverse-direction story as 510(k) - GUDID `premarket_submissions` names PMA numbers too, so a DI resolves to its PMA, but a PMA record cannot name a DI. Cross-country: no official field; candidate only.

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `window_smoke_2024` | 200 | 4419 | 1437 | <https://api.fda.gov/device/pma.json?search=decision_date%3A%5B2024-01-01+TO+2024-12-31%5D&limit=2> |
| `window_2025_count` | 200 | 2742 | 1000 | <https://api.fda.gov/device/pma.json?search=decision_date%3A%5B2025-01-01+TO+2025-12-31%5D&limit=1> |
| `search_applicant:medtronic` | 200 | 9709 | 1031 | <https://api.fda.gov/device/pma.json?search=applicant%3Amedtronic&limit=3> |
| `search_applicant:"ge healthcare"` | 200 | 9298 | 1217 | <https://api.fda.gov/device/pma.json?search=applicant%3A%22ge+healthcare%22&limit=3> |
| `search_applicant:philips` | 200 | 11589 | 1218 | <https://api.fda.gov/device/pma.json?search=applicant%3Aphilips&limit=3> |
| `search_applicant:draeger` | 404 | 93 | 1453 | <https://api.fda.gov/device/pma.json?search=applicant%3Adraeger&limit=3> |
| `search_applicant:mindray` | 404 | 93 | 3516 | <https://api.fda.gov/device/pma.json?search=applicant%3Amindray&limit=3> |
| `skip_25000_behaviour` | 200 | 2820 | 1061 | <https://api.fda.gov/device/pma.json?search=decision_date%3A%5B1990-01-01+TO+2026-12-31%5D&skip=25000&limit=1> |

## Probe-level note

device/pma returns PMA originals and supplements; a supplement is a distinct record (pma_number + supplement_number) under the same approval. Same date caveat as 510(k): decision_date is an event date, not a publication date.

## Documentation opened

- licence / terms: https://open.fda.gov/license/ , https://open.fda.gov/terms/
- rate limits: https://open.fda.gov/apis/authentication/
- endpoint: https://open.fda.gov/apis/device/pma/

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
