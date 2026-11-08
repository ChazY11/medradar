# Probe notes — openalex

**Status:** `VERIFIED_API`  ·  **Requests:** 6  ·  **Probed at:** 2026-11-08T21:42:25.576709Z

## What was tested

| Probe | Method | HTTP | Counts as working access | Error |
|---|---|---|---|---|
| works_search | GET | 200 | yes | - |
| works_company | GET | 200 | yes | - |
| works_doi | GET | 200 | yes | - |
| works_year_filter | GET | 200 | yes | - |
| institutions_search | GET | 200 | yes | - |
| works_affiliation_filter | GET | 200 | yes | - |

## Conclusion

OpenAlex answered every query with 200 and real work objects, no key required. Works carry `publication_date` (first online publication), `created_date` (metadata ingestion - NOT a publication clock), DOI/PMID ids, author institutions and `grants`. Use the polite pool (`mailto=`) and never treat `created_date` as public visibility.

## Documentation checked

- https://docs.openalex.org/
- https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication
- https://docs.openalex.org/api-entities/works/work-object

## Reported status rationale

A source is only marked `VERIFIED_*` when a machine request returned 2xx **and**
a real parseable body with records.  HTML 200 pages are recorded but never
counted as verified access.  Probe artifacts: `PROBE_RESULT.json`,
`requests.jsonl`, and raw slices under `research/data_expansion/samples/openalex/`.

## Re-run

```
python research/data_expansion/probes/openalex/probe.py
```
