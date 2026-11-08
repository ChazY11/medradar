# Probe notes — eu_ctis

**Status:** `VERIFIED_API`  ·  **Requests:** 4  ·  **Probed at:** 2026-11-08T21:43:34.910562Z

## What was tested

| Probe | Method | HTTP | Counts as working access | Error |
|---|---|---|---|---|
| api_search | POST | 200 | yes | - |
| api_search_sponsor | POST | 200 | yes | - |
| api_retrieve | GET | 200 | yes | - |
| site_home | GET | 200 | no | JSONDecodeError: json decode failed |

## Conclusion

CTIS exposes an unauthenticated JSON API at `https://euclinicaltrials.eu/ctis-public-api` (`POST /search`, `GET /retrieve/{ctNumber}`), used by its own public search front end. It is not a formally versioned/documented developer API, so the register records `api_available: PARTIAL`; `ctNumber` is the authoritative identifier and `decisionDate`/`publishDate` are the clock candidates (first public visibility).

## Documentation references

- https://euclinicaltrials.eu/
- https://euclinicaltrials.eu/ctis-public-api
- https://www.ema.europa.eu/en/human-regulatory-overview/research-development/clinical-trials-human-medicines/clinical-trials-information-system-ctis

These are the reference pages recorded in the source register. Only the request
URLs in the table above were exercised by this probe; a documentation URL is a
citation, not a claim that the page was fetched during the probe.

## Reported status rationale

A source is only marked `VERIFIED_*` when a machine request returned 2xx **and**
a real parseable body with records.  HTML 200 pages are recorded but never
counted as verified access.  Probe artifacts: `PROBE_RESULT.json`,
`requests.jsonl`, and raw slices under `research/data_expansion/samples/eu_ctis/`.

## Re-run

```
python research/data_expansion/probes/eu_ctis/probe.py
```
