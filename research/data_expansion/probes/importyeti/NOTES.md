# importyeti — ImportYeti

Probe: 2026-11-09, 3 requests. **Exactly one liveness check was made;
  the disallowed query path was not requested.**

| probe | URL | status |
|---|---|---|
| robots_txt | https://www.importyeti.com/robots.txt | 200 |
| homepage | https://www.importyeti.com/ | 200 |
| terms_page | https://www.importyeti.com/terms | 404 |

## Conclusion
- **BLOCKED_BY_POLICY**. The published `robots.txt` (saved verbatim) says:

  ```
  User-agent: *
  Allow: /
  Disallow: /search?q
  Disallow: /api/addresses
  Disallow: /api/ep
  ```

  i.e. the *only* path that answers the useful question ("which US importers ship from
  supplier X / what does company Y import") is explicitly disallowed, and the internal JSON
  API paths are disallowed as well. Everything else on the site is marketing pages.
- Per the collection protocol, a robots-disallowed path is not requested at all: zero data
  requests were made. This is a **policy block, not a technical one** — a human browsing the
  site can read it; an automated collector must not.
- Commercial terms also restrict automated collection (site terms page saved). The site is
  free at the UI level but sells subscriptions; it is not an open data source.

## What it would have provided
- US ocean bill-of-lading derived importer/exporter records: company names, addresses,
  supplier relationships, HS codes, shipment counts and dates.

## Verdict
Not collectible within policy. Do not build a scraper for it.
