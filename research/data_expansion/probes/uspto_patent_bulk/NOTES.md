# uspto_patent_bulk — USPTO patent full-text bulk data

Probe: 2026-11-09, 6 requests, no credentials.

| probe | URL | status | note |
|---|---|---|---|
| legacy_anonymous_host | https://bulkdata.uspto.gov/ | None | URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| odp_bulkdata_page | https://data.uspto.gov/bulkdata | 200 | <!doctype html> <html lang="en" data-beasties-container> <he |
| odp_dataset_products_api | https://api.uspto.gov/api/v1/datasets/products/applications | 401 | HTTP 401 Unauthorized |
| odp_dataset_products_api_alt | https://api.uspto.gov/api/v1/datasets/products | 403 | HTTP 403 Forbidden |

## Conclusion — the anonymous bulk tree is gone; bulk delivery is now key-gated
- **REQUIRES_REGISTRATION**.
- `https://bulkdata.uspto.gov/` **does not resolve** (DNS NXDOMAIN; retried, and confirmed with
  the public 8.8.8.8 resolver). The long-standing anonymous bulk-file tree is retired in this
  environment.
- `https://data.uspto.gov/bulkdata` returns the ODP SPA shell (200 HTML, no file listing).
- The ODP dataset-product API answers **401 Unauthorized** without `X-API-KEY`:
  `{"message":"Unauthorized"}`.
- **No bulk file was downloaded.** Not one byte. So MedRadar has *no* verified anonymous
  patent bulk channel as of this round.

## What the old channel used to be (documented) and what it costs
- Weekly grant full-text ZIPs (`ipgYYMMDD.zip`, 100–600 MB each) and weekly pre-grant
  publication ZIPs (`ipgpub`), plus the back catalogue since 2001 — roughly multi-TB total,
  no key, public domain.
- Even if it comes back, ingesting it is a bandwidth/streaming job, not an API: a full
  historical pull is days of download and tens of GB of XML to grep by assignee.
- The practical alternative for applicant/date-level linkage is the keyed ODP API
  (`uspto_open_data_portal`) — free key, per-request paging, no multi-TB staging.
