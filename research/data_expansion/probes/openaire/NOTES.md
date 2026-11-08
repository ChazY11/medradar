# Probe notes — openaire

**Status:** `VERIFIED_API`  ·  **Requests:** 2  ·  **Probed at:** 2026-11-08T21:39:02.164629Z

## What was tested

| Probe | Method | HTTP | Counts as working access | Error |
|---|---|---|---|---|
| graph_research_products | GET | 200 | yes | - |
| search_publications_legacy | GET | 200 | yes | - |

## Conclusion

Probes the Graph v1 `researchProducts` endpoint and the legacy `search/publications` endpoint.  OpenAIRE aggregates repository copies, so the same paper appears many times: only DOI-based canonical keys may be counted as independent evidence.

## Documentation checked

- https://api.openaire.eu/
- https://graph.openaire.eu/docs/
- https://graph.openaire.eu/docs/apis/graph-api/

## Reported status rationale

A source is only marked `VERIFIED_*` when a machine request returned 2xx **and**
a real parseable body with records.  HTML 200 pages are recorded but never
counted as verified access.  Probe artifacts: `PROBE_RESULT.json`,
`requests.jsonl`, and raw slices under `research/data_expansion/samples/openaire/`.

## Re-run

```
python research/data_expansion/probes/openaire/probe.py
```
