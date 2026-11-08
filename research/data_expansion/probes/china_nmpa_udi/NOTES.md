# china_nmpa_udi - probe notes

- **status**: `UNAVAILABLE`
- **run at**: `2026-11-08T21:53:13.162103Z`
- **requests made**: 3
- **evidence dirs**: `probes/china_nmpa_udi/`, `samples/china_nmpa_udi/`

## What was tested

Three requests: the UDI portal root (HTTP 200, a JSP/JS shell) and two documented-looking query paths. The shell loaded; the query paths returned no device records.

## Verdict

UNAVAILABLE. The portal is a session-bound JSP/JS application with no public machine interface and no bulk release. A 200 on the shell is **not** evidence of data access, so this is recorded as unavailable rather than verified.

## Time semantics (`event_at` vs `source_public_at`)

UNKNOWN - no record was served.

## Cross-national product identity

Stable product ID: unknown. The Chinese UDI database is expected to carry a domestic UDI-DI, but no value was observed, so a Chinese DI cannot be resolved and the Chinese side cannot be joined to GUDID by identifier. This is the single largest identity gap for Mindray in this round.

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `udi_portal_home` | 200 | 49373 | 2093 | <https://udi.nmpa.gov.cn/> |
| `query_udi_query` | 404 | 11664 | 1078 | <https://udi.nmpa.gov.cn/udi/query?di=00643169718425> |
| `query_api_udi_search` | 404 | 11664 | 891 | <https://udi.nmpa.gov.cn/api/udi/search?di=00643169718425> |

## Probe-level note

The NMPA UDI portal serves a JSP/JS shell whose data calls are session-bound and undocumented; no public machine interface was found and the documented paths did not return records. Recorded as unavailable rather than guessed at.

## Documentation opened

- UDI portal: https://udi.nmpa.gov.cn/

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
