# china_nmpa_device - probe notes

- **status**: `BLOCKED_BY_POLICY`
- **run at**: `2026-11-08T21:53:08.981675Z`
- **requests made**: 2
- **evidence dirs**: `probes/china_nmpa_device/`, `samples/china_nmpa_device/`

## What was tested

Two requests: the NMPA portal root and the datasearch page. Both answered **HTTP 412** with a JavaScript anti-bot challenge (a dynamic `<meta>` token plus obfuscated script) before any content was served.

## Verdict

BLOCKED_BY_POLICY. HTTP 412 + JS challenge on every path. Clearing that challenge programmatically is a WAF bypass, which the protocol forbids, so this was recorded rather than retried. No official bulk release or open-data mirror for device registrations was identified.

## Time semantics (`event_at` vs `source_public_at`)

UNKNOWN - no record was ever served, so no date field is claimed. In particular the NMPA registration-certificate date is **not** assumed to exist in machine-readable form.

## Cross-national product identity

Stable product ID: unknown in practice - the NMPA registration certificate number is documented in secondary literature but was never observed from the source. Consequence for the core question: the Chinese market cannot be anchored for any of the five firms, and Mindray's home-market registrations therefore cannot be linked to its US GUDID/510(k) records. Any China-inclusive identity claim this round would be unfounded.

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `portal_home` | 412 | 2502 | 905 | <https://www.nmpa.gov.cn/> |
| `datasearch_query` | 412 | 2562 | 1108 | <https://www.nmpa.gov.cn/datasearch/search-result.html?q=Medtronic> |

## Probe-level note

NMPA answers HTTP 412 with a JavaScript anti-bot challenge (a dynamic <meta> token that must be solved by running obfuscated script) before any content is served. Solving or replaying that challenge is a WAF bypass, which the collection protocol forbids, so the source is recorded as blocked rather than retried.

## Documentation opened

- portal: https://www.nmpa.gov.cn/ (answers HTTP 412 to non-browser clients)

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
