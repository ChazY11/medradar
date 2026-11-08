# Probe notes — who_ictrp

**Status:** `UNAVAILABLE`  ·  **Requests:** 2  ·  **Probed at:** 2026-11-08T21:39:09.629684Z

## What was tested

| Probe | Method | HTTP | Counts as working access | Error |
|---|---|---|---|---|
| search_portal | GET | 200 | no | JSONDecodeError: json decode failed |
| platform_page | GET | 200 | no | JSONDecodeError: json decode failed |

## Conclusion

ICTRP is a search portal over national registries, with no public machine API.  The probe records the portal responses but they are HTML forms, not queryable records, so the source is recorded UNAVAILABLE for programmatic collection.  The registries it indexes (CT.gov, CTIS, ChiCTR, ...) are collected directly instead.

## Documentation checked

- https://www.who.int/clinical-trials-registry-platform
- https://trialsearch.who.int/

## Reported status rationale

A source is only marked `VERIFIED_*` when a machine request returned 2xx **and**
a real parseable body with records.  HTML 200 pages are recorded but never
counted as verified access.  Probe artifacts: `PROBE_RESULT.json`,
`requests.jsonl`, and raw slices under `research/data_expansion/samples/who_ictrp/`.

## Re-run

```
python research/data_expansion/probes/who_ictrp/probe.py
```
