# ocds_registry — probe notes

**Status: NOT_TESTED (deliberate)** · 3 requests · 2026-11-09

## What was tested

| # | Request | Result |
|---|---|---|
| 1 | `GET https://standard.open-contracting.org/latest/en/` | 200 — OCDS site |
| 2 | `GET .../en/schema/release_package/` | 200 — "Release Package Schema — OCDS v1.1.5" |
| 3 | `GET .../en/101/` | 404 |

## Why NOT_TESTED instead of VERIFIED_PUBLIC_QUERY

OCDS is a **standard plus a publisher registry**, not a publisher. The site
documents the release/record model; it does not serve contract records. Calling a
documentation site "verified records" would be a category error, so the probe ran
(its outcome is real evidence that the docs are reachable) and the status is set
to `NOT_TESTED`, which makes the merged register report
`verified_by: documentation_only`.

Real OCDS records **were** verified — through a publisher, in
`probes/uk_find_a_tender/` (OCDS 1.1 release packages, stage-tagged
`tender` vs `award`/`contract`).

## Why it is still worth a register entry

Because it is the reason a single normaliser can serve many publishers: UK FTS
verified here, and other national portals publish the same release-package model.
The value is architectural (a design contract), and the register says so instead
of pretending it is a data source.

## Cross-reference

* `probes/uk_find_a_tender/NOTES.md` — the verified OCDS publisher
* `registry/sources/ocds_registry.json` — field list and limitations

## Artifacts

* `requests.jsonl`, `PROBE_RESULT.json`
* samples: `../../../samples/ocds_registry/` (2 documentation pages, hash-verified)
