# usitc_dataweb — USITC DataWeb

Probe: 2026-11-09, 4 requests.

| probe | URL | status | note |
|---|---|---|---|
| dataweb_app | https://dataweb.usitc.gov/ | 200 | <!doctype html> <html lang="en" data-beasties-container>   < |
| usitc_dataweb_docs | https://www.usitc.gov/dataweb | 403 | HTTP 403 Forbidden |
| dataweb_help_route | https://dataweb.usitc.gov/help | 200 | <!doctype html> <html lang="en" data-beasties-container>   < |
| api_route_guess | https://dataweb.usitc.gov/api/v1/data | 200 | <!doctype html> <html lang="en" data-beasties-container>   < |

## Conclusion
- **UNAVAILABLE**: no machine interface found. `dataweb.usitc.gov` is an Angular SPA that
  returns the same 9.5 KB shell for *every* path (including `/api/...` guesses), so there is
  no discoverable REST endpoint and nothing parseable without a browser session.
- `www.usitc.gov/dataweb` answered `403 Access Denied` (Akamai).
- DataWeb's documented usage model is a free **registered web account** driving a form-based
  query tool. Extracting data would require browser automation of a logged-in session, which
  this round's rules forbid (no account, no bypass).

## What it would add
- US import/export statistics by HTS-10, customs district and country, with USITC's own
  reconciliation — a finer geography than Census's country totals.
- Still **aggregate**: no company names, no shipments.

## Verdict for MedRadar
Not usable in this round. If ever needed, the Census API (`us_census_trade`) covers the same
research question (HS-code country aggregates) with a documented key, so DataWeb is
redundant as well as blocked.
