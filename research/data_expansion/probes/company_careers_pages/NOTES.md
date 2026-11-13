# company_careers_pages — probe notes

**Status: UNAVAILABLE for records** · 6 requests · 2026-11-09 · no JS executed

## What was tested

| # | URL | Result |
|---|---|---|
| 1 | `https://www.medtronic.com/us-en/about/careers.html` | 200 — but it renders the corporate homepage (`<title>Health tech for the digital age</title>`) |
| 2 | `https://www.careers.philips.com/global/en` | 200 — careers landing page |
| 3 | `https://www.draeger.com/en-us/Company/Careers` | **403 Forbidden** |
| 4 | `https://www.mindray.com/en/careers` | **404** |
| 5 | `https://www.careers.philips.com/global/en/search-results` | 200 — **no job records in the HTML** |
| 6 | `https://www.medtronic.com/robots.txt` | 200 — fetched to respect crawl policy |

## Why the status is UNAVAILABLE even though pages answer

A careers page is a **front door**, not a job feed. Two of four firm pages
returned 200, and the one that actually lists jobs (Philips search-results) is
client-rendered: the served HTML contains no vacancy entries — 322 occurrences of
"job" in that page are navigation and template text, not postings. Extracting
records would require executing JavaScript, which this task does not do.

Word counts on a marketing page are **not** evidence of hiring. That is exactly
the kind of pseudo-signal the collection protocol forbids, so no count is claimed.

## Structure findings

* No publication timestamp in the HTML shell → `source_public_at` is unavailable,
  so `first_observed_at` would be the only clock and no publication-relative
  analysis would be possible.
* One firm returns 403 to a non-browser client, one URL 404s (page layout
  changed), which shows how brittle a per-firm scraper would be.
* `robots.txt` for medtronic.com was fetched before any further work, to check
  policy rather than assume it.

## Consequence for the hiring question

Together with the Greenhouse/Lever/GTS results this closes the generic route:
for these five firms, hiring data would need five bespoke, client-rendering
adapters with no publication clock and no cross-firm comparability. The register
recommends against using hiring volume as a MedRadar signal for them at this
stage, and says why.

## Artifacts

* `requests.jsonl`, `PROBE_RESULT.json`
* samples: `../../../samples/company_careers_pages/` (4 HTML/txt files, hash-verified)
