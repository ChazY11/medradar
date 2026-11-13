# Probe notes — nih_reporter

**Status:** `VERIFIED_API`  ·  **Requests:** 3  ·  **Probed at:** 2026-11-08T21:42:47.102813Z

## What was tested

| Probe | Method | HTTP | Counts as working access | Error |
|---|---|---|---|---|
| projects_text | POST | 200 | yes | - |
| projects_org_fy | POST | 200 | yes | - |
| projects_org_any_year | POST | 200 | yes | - |

## Conclusion

NIH RePORTER v2 is POST-only and needs no key: `POST /v2/projects/search` with a `criteria` object returned 200 JSON and `results`.  Grants carry `project_num`, `project_start_date` (event_at), `award_notice_date` (approximate public-visibility clock of the award record), `organization.org_name` (company field) and `agency_ic_*`.  The same grant must not be counted twice when several fiscal-year queries overlap.

## Documentation references

- https://api.reporter.nih.gov/
- https://support.researchallofus.org/hc/en-us/articles/
- https://reporter.nih.gov/

These are the reference pages recorded in the source register. Only the request
URLs in the table above were exercised by this probe; a documentation URL is a
citation, not a claim that the page was fetched during the probe.

## Reported status rationale

A source is only marked `VERIFIED_*` when a machine request returned 2xx **and**
a real parseable body with records.  HTML 200 pages are recorded but never
counted as verified access.  Probe artifacts: `PROBE_RESULT.json`,
`requests.jsonl`, and raw slices under `research/data_expansion/samples/nih_reporter/`.

## Re-run

```
python research/data_expansion/probes/nih_reporter/probe.py
```
