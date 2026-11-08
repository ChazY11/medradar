# openfda_device_classification - probe notes

- **status**: `VERIFIED_API`
- **run at**: `2026-11-08T21:52:25.839101Z`
- **requests made**: 2
- **evidence dirs**: `probes/openfda_device_classification/`, `samples/openfda_device_classification/`

## What was tested

Two requests: an unfiltered page of the dictionary and a lookup of a single product code (`DQA`). Both returned HTTP 200; the dictionary reports 7,097 codes.

## Verdict

VERIFIED_API. The whole dictionary is 7,097 rows, i.e. at most 8 pages at `limit=1000`, so it can be mirrored in full and should be (it is the join key, not a stream).

## Time semantics (`event_at` vs `source_public_at`)

**No dates at all.** FDA publishes the current value of each product code with no effective date and no publication date. Both clocks stay empty and quality is `unknown`; dating a classification with the fetch day would silently apply today's risk class to a 2004 clearance.

## Cross-national product identity

Stable product ID: **yes, at the device-family level** - `product_code` plus the 21 CFR `regulation_number`. It is not a device instance identifier and carries no company. Its role in cross-source identity is as a join key: it maps a 510(k)/PMA to a device family, which is what makes the US submission stream analysable per track.

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `page_smoke` | 200 | 8324 | 1094 | <https://api.fda.gov/device/classification.json?limit=2> |
| `product_code_dqa` | 200 | 35212 | 1046 | <https://api.fda.gov/device/classification.json?search=product_code%3A%22DQA%22&limit=2> |

## Probe-level note

The product-code dictionary is small (~7k codes) and is the join key between a 510(k)/PMA submission and a device family, so it is a cheap full pull (<=8 pages at limit=1000) rather than a windowed collection.

## Documentation opened

- endpoint: https://open.fda.gov/apis/device/classification/

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
