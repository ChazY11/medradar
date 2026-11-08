# japan_pmda - probe notes

- **status**: `UNAVAILABLE`
- **run at**: `2026-11-08T21:59:26.473986Z`
- **requests made**: 3
- **evidence dirs**: `probes/japan_pmda/`, `samples/japan_pmda/`

## What was tested

Three requests: the English portal, the device database form (`/PmdaSearch/kikiSearch/`) and the same URL with a query parameter.

## Verdict

UNAVAILABLE. The pages are reachable and the device database exists, but it is a legacy servlet that renders an HTML form and only answers a form POST - a GET with query parameters returned the empty form again (verified). No documented API and no bulk release. This is 'no machine interface', not 'no data'.

## Time semantics (`event_at` vs `source_public_at`)

UNKNOWN - results exist only as HTML rendered after a POST.

## Cross-national product identity

Stable product ID: unknown in machine form - the PMDA approval number (承認番号) is documented but was not observed from a machine response. Japan therefore cannot be placed on the cross-market timeline this round.

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `english_portal` | 200 | 57643 | 2608 | <https://www.pmda.go.jp/english/> |
| `device_search_page` | 200 | 139894 | 2766 | <https://www.pmda.go.jp/PmdaSearch/kikiSearch/> |
| `get_with_query_rejected` | 200 | 139903 | 2437 | <https://www.pmda.go.jp/PmdaSearch/kikiSearch/?nameWord=Medtronic> |

## Probe-level note

PMDA's device database (kikiSearch) is a legacy servlet that renders an HTML form and only answers a form POST; a GET with query parameters returns the empty form again. No documented API and no bulk release exist, so there is no machine-readable path for this study. The pages themselves are reachable, so this is 'no machine interface', not 'no data'.

## Documentation opened

- English portal: https://www.pmda.go.jp/english/
- device database (form POST only): https://www.pmda.go.jp/PmdaSearch/kikiSearch/

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
