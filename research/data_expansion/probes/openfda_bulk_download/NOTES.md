# openfda_bulk_download - probe notes

- **status**: `VERIFIED_BULK_DOWNLOAD`
- **run at**: `2026-11-08T21:51:05.457635Z`
- **requests made**: 2
- **evidence dirs**: `probes/openfda_bulk_download/`, `samples/openfda_bulk_download/`

## What was tested

Two requests: `api.fda.gov/download.json` (601,654 bytes of manifest) and the smallest device export partition (`device/classification`, 3.13 MB zip) which was downloaded and parsed in-memory: 7,097 records recovered, matching the manifest's declared count.

## Verdict

VERIFIED_BULK_DOWNLOAD. The manifest publishes, per endpoint, `total_records`, `export_date` and per-partition `size_mb`/`records`. device/510k is a single 238.55 MB file and device/udi is 52 parts, so a full mirror is out of scope; the classification partition proves the download path byte-for-byte.

## Time semantics (`event_at` vs `source_public_at`)

`export_date` is a genuine **snapshot clock** (2026-11-02/03/06 per endpoint) and is the reason bulk acquisition is preferable to the API for a bitemporal study: it pins the vintage. It is still not a per-record publication date, so it is stored in `normalized.export_date` and never in the record clocks.

## Cross-national product identity

Identity is inherited from whichever endpoint is exported (510(k) number, PMA number, UDI-DI, product_code, registration number). Because the bulk connector delegates to the per-endpoint normalisers, a bulk record and an API record for the same submission produce the **same `evidence_id`** - verified in `tests/test_extsrc_regulatory.py` - so the two acquisition routes cannot double-count.

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `download_manifest` | 200 | 601654 | 1577 | <https://api.fda.gov/download.json> |
| `classification_export_zip` | 200 | 3285255 | 6468 | <https://download.open.fda.gov/device/classification/device-classification-0001-of-0001.json.zip> |

## Probe-level note

api.fda.gov/download.json is the official export manifest: per-endpoint `total_records` and an `export_date` that is a genuine snapshot clock (unlike the API's per-endpoint `last_updated`). One export partition was downloaded and parsed, which is what distinguishes VERIFIED_BULK_DOWNLOAD from a doc claim.

## Documentation opened

- manifest: https://api.fda.gov/download.json
- licence: https://open.fda.gov/license/

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
