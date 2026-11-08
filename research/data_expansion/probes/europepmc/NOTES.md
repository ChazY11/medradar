# Probe notes — europepmc

**Status:** `VERIFIED_API`  ·  **Requests:** 4  ·  **Probed at:** 2026-11-08T21:38:26.868881Z

## What was tested

| Probe | Method | HTTP | Counts as working access | Error |
|---|---|---|---|---|
| search_lite | GET | 200 | yes | - |
| search_core | GET | 200 | yes | - |
| affiliation_company | GET | 200 | yes | - |
| doi_lookup | GET | 200 | yes | - |

## Conclusion

Europe PMC REST returned 200 JSON with `resultList.result` and `hitCount`. `resultType=core` supplies `firstPublicationDate`, `firstIndexDate`, DOI/PMID/PMCID, `authorList[].affiliation`, `grantsList` and `dbCrossReferenceList` - enough for DOI-based cross-source de-duplication, author-affiliation company matching and grant-number linking.  `firstIndexDate` is an ingestion clock, not publication.

## Documentation references

- https://europepmc.org/RestfulWebService
- https://europepmc.org/help

These are the reference pages recorded in the source register. Only the request
URLs in the table above were exercised by this probe; a documentation URL is a
citation, not a claim that the page was fetched during the probe.

## Reported status rationale

A source is only marked `VERIFIED_*` when a machine request returned 2xx **and**
a real parseable body with records.  HTML 200 pages are recorded but never
counted as verified access.  Probe artifacts: `PROBE_RESULT.json`,
`requests.jsonl`, and raw slices under `research/data_expansion/samples/europepmc/`.

## Re-run

```
python research/data_expansion/probes/europepmc/probe.py
```
