# Probe notes — crossref

**Status:** `VERIFIED_API`  ·  **Requests:** 5  ·  **Probed at:** 2026-11-08T21:42:29.723296Z

## What was tested

| Probe | Method | HTTP | Counts as working access | Error |
|---|---|---|---|---|
| works_search | GET | 200 | yes | - |
| works_bibliographic | GET | 200 | yes | - |
| work_doi | GET | 200 | yes | - |
| works_filter | GET | 200 | yes | - |
| works_funder | GET | 200 | yes | - |

## Conclusion

Crossref REST returned 200 JSON with `message.items` for query, bibliographic query and filter calls.  Works give DOI, `published-online`/`published-print` (must be kept apart), `created`/`deposited` (registration clocks, never publication dates), `funder[]` with award numbers and `relation`.  `mailto=` puts us in the polite pool.

## Documentation references

- https://api.crossref.org/
- https://github.com/CrossRef/rest-api-doc
- https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/

These are the reference pages recorded in the source register. Only the request
URLs in the table above were exercised by this probe; a documentation URL is a
citation, not a claim that the page was fetched during the probe.

## Reported status rationale

A source is only marked `VERIFIED_*` when a machine request returned 2xx **and**
a real parseable body with records.  HTML 200 pages are recorded but never
counted as verified access.  Probe artifacts: `PROBE_RESULT.json`,
`requests.jsonl`, and raw slices under `research/data_expansion/samples/crossref/`.

## Re-run

```
python research/data_expansion/probes/crossref/probe.py
```
