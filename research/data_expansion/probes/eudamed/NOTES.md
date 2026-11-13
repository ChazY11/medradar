# eudamed - probe notes

- **status**: `REQUIRES_REGISTRATION`
- **run at**: `2026-11-08T21:53:02.327296Z`
- **requests made**: 4
- **evidence dirs**: `probes/eudamed/`, `samples/eudamed/`

## What was tested

Four requests: the public SPA shell, two public API paths (`/api/devices`, `/api/public/devices`) and the DG SANTE developer portal page named by the block message.

## Verdict

REQUIRES_REGISTRATION. The SPA loads (HTTP 200), but every public data endpoint answers **HTTP 429 with an explicit policy message**: 'For automated/machine-to-machine access, please use the official EUDAMED data API instead of scraping the public endpoints', with a link to `developer.datalake.sante.service.ec.europa.eu`. That is the operator telling automated clients not to do what this study would do, so the public path is off-limits by policy and the official data API needs registered credentials.

## Time semantics (`event_at` vs `source_public_at`)

UNKNOWN. No record was ever served, so no field semantics can be claimed. Nothing about EUDAMED dates is asserted anywhere in the register.

## Cross-national product identity

Stable product ID: **expected but unverified** - EUDAMED is documented to carry the Basic UDI-DI (device-family level) plus UDI-DI and the SRN for economic operators, but none of that was observed from the source. The scientific significance is high: Basic UDI-DI is the EU-side counterpart of the US device family, so it is the natural key for an EU-vs-US registration-timing comparison - which this round could not build.

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `public_spa_shell` | 200 | 48322 | 781 | <https://ec.europa.eu/tools/eudamed/> |
| `public_api_devices` | 429 | 321 | 312 | <https://ec.europa.eu/tools/eudamed/api/devices?page=0&size=2> |
| `official_machine_api_portal` | 200 | 9981 | 405 | <https://developer.datalake.sante.service.ec.europa.eu/api-details#api=94b9e658-d721-4b58-8d96-022c490f7a17> |

## Probe-level note

EUDAMED's public SPA loads, but every public data endpoint answers HTTP 429 with an explicit policy message telling automated clients to use the official EUDAMED data API instead of scraping. That machine API lives on the DG SANTE developer portal and needs registered credentials, so the source is reachable only after registration; the public endpoints are off-limits to this study by the operator's own instruction (probe stores the exact message).

## Documentation opened

- public database: https://ec.europa.eu/tools/eudamed/
- the block message as returned: https://ec.europa.eu/tools/eudamed/api/devices?page=0&size=2
- official machine API portal: https://developer.datalake.sante.service.ec.europa.eu/api-details#api=94b9e658-d721-4b58-8d96-022c490f7a17

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
