# Probe notes — clinicaltrials_gov

**Status:** `VERIFIED_API`  ·  **Requests:** 4  ·  **Probed at:** 2026-11-08T21:43:30.567402Z

## What was tested

| Probe | Method | HTTP | Counts as working access | Error |
|---|---|---|---|---|
| sponsor_search | GET | 200 | yes | - |
| term_search | GET | 200 | yes | - |
| sponsor_philips | GET | 200 | yes | - |
| study_detail | GET | 200 | yes | - |

## Conclusion

CT.gov v2 returned 200 JSON with `studies`, `totalCount` and `nextPageToken`.  `statusModule.studyFirstPostDateStruct.date` is the first-public-registration date and is the only defensible `source_public_at`; `startDateStruct.date` is the study start and must not be substituted.  `sponsorCollaboratorsModule.leadSponsor.name` is the deterministic company field (identity.CompanyIndex.resolve).

## Documentation checked

- https://clinicaltrials.gov/data-api/api
- https://clinicaltrials.gov/data-api/about-api
- https://clinicaltrials.gov/data-api/api#/Studies/getStudies

## Reported status rationale

A source is only marked `VERIFIED_*` when a machine request returned 2xx **and**
a real parseable body with records.  HTML 200 pages are recorded but never
counted as verified access.  Probe artifacts: `PROBE_RESULT.json`,
`requests.jsonl`, and raw slices under `research/data_expansion/samples/clinicaltrials_gov/`.

## Re-run

```
python research/data_expansion/probes/clinicaltrials_gov/probe.py
```
