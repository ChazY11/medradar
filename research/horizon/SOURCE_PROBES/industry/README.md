# `SOURCE_PROBES/industry/` — what is in here and why

| file | content |
|---|---|
| `PROBES.json` | the 54 declared GET probes run by `python -m hz.cli probe --suite industry`; each row has status, bytes, sha256, outcome and the question it answers |
| `REQUEST_LOG.jsonl` | **every** request the workstream made — 249 GET (written by `hz.http.BoundedClient`) plus **21 POST** logged manually with `method`, `sha256` of the response and `request_body_sha256`, because `BoundedClient` is GET-only by contract |
| `_ted_field_error.json` | verbatim 48,100-byte TED error body from which the **complete list of 1,830 supported search fields** was extracted (it is what proves `winner-name` and `BT-768-Contract` are recognised field names) |
| `_ted_fields.txt` | the 1,830 field names, one per line, extracted from the body above |
| `ted_probe.json` | one verbatim `POST /v3/notices/search` response used to inspect notice shape |

Expected-failure probes are kept on purpose: an HTTP 400/403/405 with a recorded
body signature is the *evidence* for a BLOCKED_* verdict in
`registry/sources/<id>.json`. Do not "clean up" failing probes.

POST endpoints are not expressible as a `hz.probe.Probe`, so USAspending and TED
POST evidence lives in `REQUEST_LOG.jsonl` rather than in `PROBES.json`.
