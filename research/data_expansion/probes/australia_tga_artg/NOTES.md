# australia_tga_artg - probe notes

- **status**: `UNAVAILABLE`
- **run at**: `2026-11-08T22:11:40.869550Z`
- **requests made**: 4
- **evidence dirs**: `probes/australia_tga_artg/`, `samples/australia_tga_artg/`

## What was tested

Four requests across two runs: the TGA root and the ARTG search path (with and without a query string). Every request from this host either timed out after 90-120 s or was reset by the remote end, so nothing was retrieved.

## Verdict

UNAVAILABLE **for this probe**, and the honest status matters: the probe captured only timeouts/resets, so it cannot claim a policy block on the basis of its own evidence. Context from reconnaissance the same day (not reproduced inside the logged probe): the ARTG path served an Akamai Bot Manager proof-of-work interstitial (`bm-verify`, then POST to `/_sec/verify`), which the protocol forbids solving. No ARTG dataset is mirrored on data.gov.au (checked through the CKAN API).

## Time semantics (`event_at` vs `source_public_at`)

UNKNOWN - no record was served.

## Cross-national product identity

Stable product ID: unknown - the ARTG number is documented by TGA but was never observed from the source. Australia therefore contributes no cross-country anchor this round.

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `artg_search_attempt1` | None | 0 | 120233 | <https://www.tga.gov.au/resources/artg> |
| `artg_search_attempt2` | None | 0 | 120266 | <https://www.tga.gov.au/resources/artg> |
| `portal_home` | None | 0 | 120250 | <https://www.tga.gov.au/> |
| `artg_query_medtronic` | None | 0 | 120233 | <https://www.tga.gov.au/resources/artg?search_api_fulltext=Medtronic> |

## Probe-level note

Every request to tga.gov.au timed out (90-120 s) or was reset by the remote end from this host, so the ARTG could not be verified either way. During reconnaissance the ARTG path returned an Akamai bot-manager proof-of-work interstitial (`bm-verify` / `/_sec/verify`); that observation is recorded here but was NOT reproduced inside this logged probe, so the probe status is UNAVAILABLE, not BLOCKED_BY_POLICY.

## Documentation opened

- ARTG: https://www.tga.gov.au/resources/artg (not reachable from this host)
- alternative checked and empty: https://data.gov.au/data/api/3/action/package_search?q=%22ARTG%22

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
