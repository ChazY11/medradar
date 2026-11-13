# sam_gov — probe notes

**Status: REQUIRES_REGISTRATION** · 3 requests · 2026-11-09 · no account created

## What was tested

| # | Request | Result |
|---|---|---|
| 1 | `GET /opportunities/v2/search?limit=1` (no key) | **404**, empty body, `server: istio-envoy` |
| 2 | `GET ...&api_key=<40 chars of '0'>` (invalid key) | **404**, empty body, `server: istio-envoy` |
| 3 | `GET https://open.gsa.gov/api/get-opportunities-public-api/` | 200, docs |

## Why the status is REQUIRES_REGISTRATION and not, say, UNAVAILABLE

The documentation page states `api_key` is a **required** query parameter
("Public Key of users", *Required: Yes*) and describes obtaining it from a
SAM.gov system account. That is the basis for the status.

The live observation is *weaker* than the protocol's canonical signal: a missing
or bogus key produces **404 with an empty body**, not 401/403. A 404 alone would
not justify "needs registration", so the register states which fact comes from
which source rather than smoothing them together.

Deliberately not done: registering an account, using `DEMO_KEY`, or retrying
`api-alpha.sam.gov` (which returned a plain 403). No credential was used.

## Why it still matters

SAM.gov is the **pre-award** US signal (solicitations, sources-sought). USAspending
is post-award only, so without SAM.gov the US procurement chain starts at the
award. That gap is recorded in the register as a research limitation, not hidden.

## Artifacts

* `requests.jsonl`, `PROBE_RESULT.json`
* samples: `../../../samples/sam_gov/` (the docs page; no API body exists to save)
