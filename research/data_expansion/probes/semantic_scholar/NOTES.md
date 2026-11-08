# Probe notes — semantic_scholar

**Status:** `VERIFIED_API`  ·  **Requests:** 3  ·  **Probed at:** 2026-11-08T21:42:36.292233Z

## What was tested

| Probe | Method | HTTP | Counts as working access | Error |
|---|---|---|---|---|
| paper_search | GET | 429 | no | HTTP 429  |
| paper_search_retry | GET | 429 | no | HTTP 429  |
| paper_doi | GET | 200 | yes | - |

## Conclusion

Probed unauthenticated.  429 responses mean the shared un-keyed pool is exhausted, not that the API is private: a free API key raises the limit.  Recorded honestly as rate-limited (see PROBE_RESULT.json); no connector ships without a verified 2xx record.

## Documentation checked

- https://api.semanticscholar.org/
- https://www.semanticscholar.org/product/api
- https://api.semanticscholar.org/api-docs/graph

## Reported status rationale

A source is only marked `VERIFIED_*` when a machine request returned 2xx **and**
a real parseable body with records.  HTML 200 pages are recorded but never
counted as verified access.  Probe artifacts: `PROBE_RESULT.json`,
`requests.jsonl`, and raw slices under `research/data_expansion/samples/semantic_scholar/`.

## Re-run

```
python research/data_expansion/probes/semantic_scholar/probe.py
```
