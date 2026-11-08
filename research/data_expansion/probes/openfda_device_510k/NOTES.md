# openfda_device_510k - probe notes

- **status**: `VERIFIED_API`
- **run at**: `2026-11-08T21:50:36.768791Z`
- **requests made**: 8
- **evidence dirs**: `probes/openfda_device_510k/`, `samples/openfda_device_510k/`

## What was tested

Eight requests: a bounded 2024 `decision_date` window, a 2025 count probe, five applicant searches (one per target firm), and a deep-pagination probe at `skip=25000`. Every request returned HTTP 200 JSON with `meta.results.total`.

## Verdict

VERIFIED_API. Anonymous access works; the endpoints answer with real 510(k) records. `skip` is capped at 25,000, so any full backfill must be windowed by `decision_date`. Applicant-level search works for all five firms, but the applicant string is the filed submitter entity, so subsidiary names have to go through the alias index.

## Time semantics (`event_at` vs `source_public_at`)

`decision_date` (clearance decision) and `date_received` (filing) are the only dates on a record. FDA publishes **no per-record first-publication timestamp**, and the endpoint-level `meta.last_updated` is a refresh stamp for the whole endpoint - using it would date every record to the last refresh. The connector therefore sets `event_at` = decision_date and `source_public_at` = decision_date with `quality="derived"`, which makes `timeq.quality_allows_lead_time` refuse it for lead-time claims.

## Cross-national product identity

Stable product ID: **yes** - the 510(k) number (`k_number`), an official identifier that is unique per clearance decision. Linkable to FDA DI/UDI: **not from this side** - a 510(k) record carries no DI, model or labeler DUNS. The official join runs the other way: a GUDID record's `premarket_submissions[].submission_number` names the K number (verified live: GUDID DI 00643169718425 -> K973011). Linkable across countries: no official field; any 510(k)-to-MDALL/EUDAMED link would rest on manufacturer + trade name, i.e. a **candidate**, not a confirmed link.

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `window_smoke_2024` | 200 | 20941 | 1063 | <https://api.fda.gov/device/510k.json?search=decision_date%3A%5B2024-01-01+TO+2024-12-31%5D&limit=2> |
| `window_2025_count` | 200 | 17094 | 1157 | <https://api.fda.gov/device/510k.json?search=decision_date%3A%5B2025-01-01+TO+2025-12-31%5D&limit=1> |
| `search_applicant:medtronic` | 200 | 38299 | 1000 | <https://api.fda.gov/device/510k.json?search=applicant%3Amedtronic&limit=3> |
| `search_applicant:"ge healthcare"` | 200 | 30079 | 1500 | <https://api.fda.gov/device/510k.json?search=applicant%3A%22ge+healthcare%22&limit=3> |
| `search_applicant:philips` | 200 | 47938 | 1281 | <https://api.fda.gov/device/510k.json?search=applicant%3Aphilips&limit=3> |
| `search_applicant:draeger` | 200 | 27185 | 1093 | <https://api.fda.gov/device/510k.json?search=applicant%3Adraeger&limit=3> |
| `search_applicant:mindray` | 200 | 41806 | 1125 | <https://api.fda.gov/device/510k.json?search=applicant%3Amindray&limit=3> |
| `skip_25000_behaviour` | 200 | 7749 | 1218 | <https://api.fda.gov/device/510k.json?search=decision_date%3A%5B1990-01-01+TO+2026-12-31%5D&skip=25000&limit=1> |

## Probe-level note

device/510k returns real records (JSON, meta.results.total present). No key needed. `decision_date` is the clearance decision date; FDA publishes no per-record first-publication timestamp, so source_public_at may only be derived from the decision date and must be flagged as coarse evidence, never used as a published-on date.

## Documentation opened

- licence / terms: https://open.fda.gov/license/ , https://open.fda.gov/terms/
- rate limits: https://open.fda.gov/apis/authentication/
- endpoint: https://open.fda.gov/apis/device/510k/

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
