# workday_phenom — probe notes

**Status: UNAVAILABLE** · 4 requests · 2026-11-09

## What was tested

| # | Request | Result |
|---|---|---|
| 1 | `GET https://jobs.medtronic.com/` (Phenom host) | **TLS failure**: `CERTIFICATE_VERIFY_FAILED`, certificate is not valid for `jobs.medtronic.com` |
| 2 | `POST https://philips.wd3.myworkdayjobs.com/wday/cxs/philips/Philips_Careers/jobs` | **404** JSON |
| 3 | `POST https://gehc.wd5.myworkdayjobs.com/wday/cxs/gehc/GEHC/jobs` | **404** JSON |
| 4 | `GET https://www.workday.com/en-us/products/talent-acquisition.html` | 404 (page moved) |

`max_retries=0` on purpose: an earlier run with retries spent its whole budget
re-attempting the broken TLS host (3 attempts each), which is why this run is
scoped to one attempt per endpoint.

## The TLS finding

`jobs.medtronic.com` resolves (144.15.206.71) and answers TCP, but the presented
certificate does not match the hostname. The compliant response is to record it as
unfetchable. **Disabling certificate verification to "make it work" would be
bypassing a security control**, which this task does not do.

## The Workday finding

Workday's public careers sites call `POST /wday/cxs/<tenant>/<site>/jobs`. The
tenant **and** site name are employer-specific and there is no directory of them;
both guesses returned 404 JSON. So a Workday adapter is per-employer discovery
work, not a generalisable connector — and guessing further would be enumeration.

## Conclusion (recorded, not glossed)

There is no vendor-neutral Workday/Phenom API. Whatever an employer exposes is
site-specific, undocumented, unversioned and can change without notice. This is
why `registry/sources/workday_phenom.json` says `api_available: PARTIAL` and why
the hiring evidence for these five firms cannot be produced from a generic API.

## Artifacts

* `requests.jsonl`, `PROBE_RESULT.json`
* **no samples**: every request failed, so there is no response body to store.
  `samples/workday_phenom/SAMPLES.json` is intentionally absent.
