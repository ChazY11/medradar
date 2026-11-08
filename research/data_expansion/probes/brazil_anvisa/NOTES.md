# brazil_anvisa - probe notes

- **status**: `REQUIRES_REGISTRATION`
- **run at**: `2026-11-08T21:59:29.256132Z`
- **requests made**: 3
- **evidence dirs**: `probes/brazil_anvisa/`, `samples/brazil_anvisa/`

## What was tested

Three requests: the Consultas SPA, and two `/api/consulta/` paths without a token.

## Verdict

REQUIRES_REGISTRATION. The SPA loads, but the JSON API answers 403 without a bearer token issued by the ANVISA login flow. No public bulk release for device registrations was found.

## Time semantics (`event_at` vs `source_public_at`)

UNKNOWN - no record was served.

## Cross-national product identity

Stable product ID: unknown - the registro ANVISA number is documented but was not observed. Brazil contributes no cross-country anchor this round.

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `consultas_spa` | 200 | 19812 | 500 | <https://consultas.anvisa.gov.br/> |
| `api_produtos_saude_without_token` | 403 | 2380 | 219 | <https://consultas.anvisa.gov.br/api/consulta/produtos-saude> |
| `api_medicamentos_without_token` | 403 | 2380 | 375 | <https://consultas.anvisa.gov.br/api/consulta/medicamentos?page=1> |

## Probe-level note

consultas.anvisa.gov.br is an Angular SPA; its JSON API answers 401/403 without a bearer token issued by the ANVISA login flow, so device registrations require a registered account. No anonymous machine interface was found.

## Documentation opened

- SPA: https://consultas.anvisa.gov.br/
- API (403 without a token): https://consultas.anvisa.gov.br/api/consulta/medicamentos

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
