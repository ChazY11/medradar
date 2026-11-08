# Probe notes — pubmed_eutils

**Status:** `VERIFIED_API`  ·  **Requests:** 3  ·  **Probed at:** 2026-11-08T21:43:49.266735Z

## What was tested

| Probe | Method | HTTP | Counts as working access | Error |
|---|---|---|---|---|
| esearch | GET | 200 | yes | - |
| esummary | GET | 200 | yes | - |
| esearch_doi | GET | 200 | yes | - |

## Conclusion

E-utilities esearch/esummary returned 200 JSON.  No key is needed at 3 req/s; the connector declares `tool`/`email` for a better politeness tier and stays below the limit with a 1.2 s minimum interval.  esummary gives `pubdate`/`epubdate` (coarse when only a year/month is published), DOI and PMC id for de-duplication.

## Documentation checked

- https://www.ncbi.nlm.nih.gov/books/NBK25501/
- https://www.ncbi.nlm.nih.gov/books/NBK25497/
- https://www.ncbi.nlm.nih.gov/pmc/tools/openftlist/

## Reported status rationale

A source is only marked `VERIFIED_*` when a machine request returned 2xx **and**
a real parseable body with records.  HTML 200 pages are recorded but never
counted as verified access.  Probe artifacts: `PROBE_RESULT.json`,
`requests.jsonl`, and raw slices under `research/data_expansion/samples/pubmed_eutils/`.

## Re-run

```
python research/data_expansion/probes/pubmed_eutils/probe.py
```
