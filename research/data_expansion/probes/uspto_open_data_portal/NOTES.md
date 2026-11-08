# uspto_open_data_portal — USPTO Open Data Portal (ODP) API

Probe: 2026-11-09, 3 requests, **no API key**.

| probe | URL | status | body |
|---|---|---|---|
| official_api_docs_page | https://data.uspto.gov/apis | 200 | `<!doctype html> <html lang="en" data-beasties-container> <he` |
| unauthenticated_application_search | https://api.uspto.gov/api/v1/patent/applications/search?q=stent&limit=2 | 401 | `{"message":"Unauthorized"}` |
| unauthenticated_dataset_product | https://api.uspto.gov/api/v1/datasets/products/applications | 401 | `{"message":"Unauthorized"}` |

## Conclusion (empirical)
- **REQUIRES_REGISTRATION**. `api.uspto.gov` answers unauthenticated calls with HTTP `401` and the body
  `{"message":"Unauthorized"}`. A free API key (`X-API-KEY`) is issued from the USPTO
  developer portal after creating an account; the docs describe it as free.
- The portal UI itself (`data.uspto.gov`) is a public single-page app; the *data* is behind
  the key.

## What ODP is (documented, and consistent with what we observed)
- It is USPTO's consolidated platform; its own meta description says: *"The Open Data Portal
  (ODP) is USPTO's data platform that empowers you to discover and easily extract USPTO data
  in one place for free."*
- It absorbed the former `developer.uspto.gov` APIs and (as observed here) the PatentsView
  surface — see `patentsview` NOTES.
- Endpoint families: patent application search, assignment, petition decisions, and
  **dataset products** (bulk files) — all key-gated through the same API.

## Time semantics
Application records carry `filingDate`, `publicationDate` and `grantDate` separately.
`source_public_at` = publication date. Do not derive publication from filing+18 months.

## Doc link
- https://data.uspto.gov/apis
