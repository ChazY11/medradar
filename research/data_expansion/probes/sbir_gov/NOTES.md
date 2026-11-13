# Probe notes — sbir_gov

**Status:** `UNAVAILABLE`  ·  **Requests:** 3  ·  **Probed at:** 2026-11-08T21:42:59.868343Z

## What was tested

| Probe | Method | HTTP | Counts as working access | Error |
|---|---|---|---|---|
| awards_keyword | GET | 403 | no | HTTP 403 Forbidden |
| awards_firm | GET | 403 | no | HTTP 403 Forbidden |
| api_docs_page | GET | 200 | no | JSONDecodeError: json decode failed |

## Conclusion

SBIR.gov documents an unauthenticated awards API, but on every probe the API host answered 403 Forbidden (also to a plain browser-style fetch) while the official /api page carries a maintenance notice.  This is not a registration requirement: the documented endpoints need no key.  Recorded UNAVAILABLE (documented API temporarily refusing anonymous service) with the evidence preserved, not as a working source.

## Documentation references

- https://www.sbir.gov/api
- https://www.sbir.gov/api/awards.json
- https://www.sbir.gov/

These are the reference pages recorded in the source register. Only the request
URLs in the table above were exercised by this probe; a documentation URL is a
citation, not a claim that the page was fetched during the probe.

## Reported status rationale

A source is only marked `VERIFIED_*` when a machine request returned 2xx **and**
a real parseable body with records.  HTML 200 pages are recorded but never
counted as verified access.  Probe artifacts: `PROBE_RESULT.json`,
`requests.jsonl`, and raw slices under `research/data_expansion/samples/sbir_gov/`.

## Re-run

```
python research/data_expansion/probes/sbir_gov/probe.py
```
