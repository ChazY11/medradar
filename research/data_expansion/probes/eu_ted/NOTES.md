# eu_ted — probe notes

**Status: VERIFIED_API** (search endpoint only) · 9 requests · 2026-11-09 · no API key

## What was tested

| # | Request | Result |
|---|---|---|
| 1 | `POST /v3/notices/search` `FT~"stent"`, 7 fields | 200, `totalNoticeCount` 11,151 |
| 2 | `notice-type = cn-standard` | 200, 2,952,676 |
| 3 | `notice-type = can-standard` | 200, 2,855,759 |
| 4 | `can-standard AND FT~"stent" AND publication-date >= 20240101`, winner fields requested | 200, 2,125 — **winner fields null** |
| 5 | `FT~"Medtronic" AND publication-date >= 20240101` | 200, 8,122 (keyword hits) |
| 6 | `FT~"Mindray" AND publication-date >= 20240101` | 200, 1,952 (keyword hits) |
| 7 | `classification-cpv = 33100000` | 200, 488,133 |
| 8 | `GET https://ted.europa.eu/en/notice/391299-2016/xml` | **405** "Human Verification" |
| 9 | `GET https://ted.europa.eu/en/bulk-downloads` | **405** "Human Verification" |

## The result that changes how TED can be used

The **awarded supplier is not in the search index**. Even for a 2024
`can-standard` medical-device award notice, `winner-name`, `winner-partname`,
`winner-country` and `winner-selection-status` all came back `null`.

A full-text query *does* match firm names (8,122 notices mention "Medtronic"
since 2024) because the winner name is inside the notice body — but that is a
**keyword hit, not an award→supplier link**, and the register forbids conflating
them.

The notice XML, which does contain the winner, lives on `ted.europa.eu`, and that
host answers this client with a JavaScript challenge. The challenge was
**not** bypassed, so no anonymous bulk XML package was verified; the register
records `bulk_download_available = UNKNOWN`, not `YES`.

## Query-language facts a connector must encode

* `FT~"phrase"` for free text, but `~` is **rejected** for enumerated fields
  (`notice-type`, `classification-cpv` → HTTP 400 `Operation 'PHRASE' is not supported`). Use `=` / `IN`.
* `publication-date` in an expert query must be `YYYYMMDD`
  (`>= 20240101`), not ISO (`>= 2024-01-01` → HTTP 400).
* An unsupported `fields` value returns a 47 KB error listing all **1,830**
  supported field names — saved verbatim as `ted_field_names.txt` (real server
  response, used to find the correct winner field names).

## Notice vs award

`cn-standard` (contract notice) and `can-standard` (contract award notice) are
distinct `notice-type` values in one index, and the same notice carries a
`publication-date`. That is a clean way to keep "tender published" and "award
published" apart — the layering the task requires.

## Docs opened

* <https://developer.ted.europa.eu/docs> (200)
* <https://developer.ted.europa.eu/docs/services/> (200)

## Artifacts

* `requests.jsonl`, `PROBE_RESULT.json`, `ted_field_names.txt`
* samples: `../../../samples/eu_ted/` (7 files, hash-verified)
