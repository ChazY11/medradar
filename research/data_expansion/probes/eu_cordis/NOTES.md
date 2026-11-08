# Probe notes — eu_cordis

**Status:** `VERIFIED_PUBLIC_QUERY`  ·  **Requests:** 7  ·  **Probed at:** 2026-11-08T21:43:46.223794Z

## What was tested

| Probe | Method | HTTP | Counts as working access | Error |
|---|---|---|---|---|
| search_json_free | GET | 200 | yes | - |
| search_project_id | GET | 500 | no | HTTP 500 Internal Server Error |
| search_contenttype_param | GET | 200 | yes | - |
| project_page | GET | 200 | no | JSONDecodeError: json decode failed |
| api_root | GET | None | no | URLError: <urlopen error [Errno 11001] getaddrinfo failed> |

## Conclusion

CORDIS publishes no documented, versioned developer API.  Its public search front end calls an unauthenticated JSON endpoint (`https://cordis.europa.eu/search/en?format=json`). Probed it directly; if it returns JSON project records the source is a public-query API (undocumented, so `api_available: PARTIAL`), the data being CC-BY 4.0.  No scraping of rendered HTML and no request amplification.

## Documentation checked

- https://cordis.europa.eu/
- https://cordis.europa.eu/about/services/en
- https://data.europa.eu/en/topics/open-data

## Reported status rationale

A source is only marked `VERIFIED_*` when a machine request returned 2xx **and**
a real parseable body with records.  HTML 200 pages are recorded but never
counted as verified access.  Probe artifacts: `PROBE_RESULT.json`,
`requests.jsonl`, and raw slices under `research/data_expansion/samples/eu_cordis/`.

## Re-run

```
python research/data_expansion/probes/eu_cordis/probe.py
```
