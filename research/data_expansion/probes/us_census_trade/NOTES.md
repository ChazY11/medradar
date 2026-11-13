# us_census_trade — US Census International Trade API

Probe: 2026-11-09, 3 requests, **no API key**.

| probe | URL | status | note |
|---|---|---|---|
| keyless_imports_query | https://api.census.gov/data/timeseries/intltrade/imports/hs?get=CTY_CODE%2CI_COMMODITY%2CGEN_VAL_MO&YEAR=2023&MONTH=01&I | 200 | <html style="font-size: 14px;">  <head>     <title>Missing K |
| api_docs_page | https://www.census.gov/data/developers/data-sets/international-trade.html | 200 |  <!DOCTYPE HTML> <!-- /*Per CMS-3223 we need the line below  |
| demo_key_attempt | https://api.census.gov/data/timeseries/intltrade/imports/hs?get=CTY_CODE%2CGEN_VAL_MO&time=2023-01&I_COMMODITY=9018&key= | 200 | <html style="font-size: 14px;">  <head>     <title>Invalid K |

## The trap: HTTP 200 with no data
- **REQUIRES_REGISTRATION**. The keyless call returns **HTTP 200**, `Content-Type: text/html`, and a page
  whose `<title>` is **"Missing Key"** — i.e. the endpoint now requires an API key for every
  request and signals it with a 200 status instead of 401/403.
- Consequence for any client: `if response.ok:` would happily treat this as success and parse
  an HTML error page as if it were data. The connector/register therefore must check
  `Content-Type` **and** the payload shape, not just the status code. This is the single
  most useful operational finding of this source.
- The key itself is free (Census API signup); it is the *key requirement*, not price, that
  blocks anonymous use.

## What it provides (documented)
- `timeseries/intltrade/imports/hs` and `.../exports/hs`: monthly and annual US goods trade
  by HS code (10-digit HTS at detail level), value and quantity, by country.
- Also end-use, port-level and NAICS variants. Still **aggregate**: no company, no shipment.

## Time semantics
- `time=YYYY-MM` monthly, revised for months after first release. No publication timestamp is
  exposed by the API → the only honest quality is `coarse` (month).
- Census first-release lag for goods is roughly 3-6 weeks after month end, and revisions
  follow; using a month key as if it were a known-at date overstates availability.
