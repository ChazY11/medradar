# fda_gudid_download - probe notes

- **status**: `VERIFIED_BULK_DOWNLOAD`
- **run at**: `2026-11-08T21:52:07.834859Z`
- **requests made**: 2
- **evidence dirs**: `probes/fda_gudid_download/`, `samples/fda_gudid_download/`

## What was tested

Two requests: the download index page (46,951 bytes, 27 release files enumerated) and the 2026-11-02 daily delta zip (547,350 bytes). The zip parsed to 5,548 `<device>` records, exactly the `numberRecordXML` the file header declares.

## Verdict

VERIFIED_BULK_DOWNLOAD. Daily deltas are small (hundreds of KB) and self-describing; the full release is multiple GB and was not attempted. The `header` block gives `creationDate`, `period/@start..@end` and a declared record count, which is a far better provenance story than any API.

## Time semantics (`event_at` vs `source_public_at`)

Three distinct dates, deliberately kept apart: `header/creationDate` dates the **file**, `period start/end` describes the **change window**, and `devicePublishDate` (per record) is the **first-publication date** used as `source_public_at` with `quality="day"`. `publicVersionDate` is a version stamp and is never promoted to a clock.

## Cross-national product identity

Stable product ID: **yes** - UDI-DI plus `publicDeviceRecordKey`. Linkable to FDA 510(k)/PMA: yes where the labeler recorded the submission (the XML carries `premarketSubmissions`). Cross-country: the DI is the identifier MDALL can resolve; the delta stream is what allows a point-in-time reconstruction, which is a prerequisite for any honest 'what did the US know on date D' comparison against another regulator.

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `download_page` | 200 | 46951 | 2250 | <https://accessgudid.nlm.nih.gov/download> |
| `daily_release_zip` | 200 | 547350 | 2843 | <https://accessgudid.nlm.nih.gov/release_files/download/gudid_daily_update_20261102.zip> |

## Probe-level note

NLM publishes GUDID release files: daily / weekly / monthly change sets and a full release. Daily files are small enough to download inside the protocol budget and carry an explicit 'Date Created' + record count + MD5, which gives a true per-batch publication clock. The full release is far above the 8 MB cap.

## Documentation opened

- release index: https://accessgudid.nlm.nih.gov/download
- a real daily file: https://accessgudid.nlm.nih.gov/release_files/download/gudid_daily_update_20261102.zip

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
