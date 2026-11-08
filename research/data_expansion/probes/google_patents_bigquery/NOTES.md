# google_patents_bigquery — Google Patents Public Data on BigQuery

Probe: 2026-11-09, 3 requests, no Google Cloud credentials.

| probe | URL | status |
|---|---|---|
| bigquery_public_data_index | https://cloud.google.com/bigquery/public-data | 200 |
| marketplace_dataset_listing | https://console.cloud.google.com/marketplace/product/google_patents_public_datasets/google-patents-public-data | 200 |
| unauthenticated_bigquery_rest | https://bigquery.googleapis.com/bigquery/v2/projects/bigquery-public-data/datasets/google_patents_public_datasets | 401 |

## Conclusion
- **REQUIRES_REGISTRATION**: the tables are free to query, but every access path requires a Google Cloud
  project, OAuth credentials and an **enabled billing account**. The BigQuery REST endpoint
  returns `401` for anonymous callers.
- 'Free' here means *1 TB of query data per month at no charge*; it does not mean free of setup.
  A credit card and a GCP project are prerequisites, which puts it outside this round.

## Contents (documented)
- `patents.publications` (one row per publication, with `publication_number` **including kind
  code**, `family_id`, `filing_date`, `publication_date`, `priority_date`),
  `patents.gclaims`, `patents.gdetail_desc`, `patents.cpc`, `patents.ipc`, plus USPTO
  assignment tables. Includes pre-grant publications, so it can serve as a real
  publication-date clock and supports family/citation work.

## Cost warning
An unfiltered `SELECT` over `patents.publications` scans tens of TB (billions of rows) and
burns the monthly free tier in a couple of queries; partitioning/clustering filters are
mandatory. Treat this as a paid product with a small free allowance, not a free API.

## Doc links
- https://cloud.google.com/bigquery/public-data
- https://console.cloud.google.com/marketplace/product/google_patents_public_datasets/google-patents-public-data
