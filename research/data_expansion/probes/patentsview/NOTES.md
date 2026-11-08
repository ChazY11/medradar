# patentsview — PatentsView search API

Probe: 2026-11-09, 8 requests, no API key.

| probe | URL | status | note |
|---|---|---|---|
| documented_api_host | https://search.patentsview.org/api/v1/patent/?q=%7B%22_text_any%22%3A+%7B%22patent_title%22%3A+%22stent%22%7D%7D&f=%5B%22patent_id%22%2C%22patent_date%22%5D | None | URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| documented_docs_host | https://search.patentsview.org/docs/ | None | URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| legacy_api_host | https://api.patentsview.org/patents/query?q=%7B%7D&f=%5B%22patent_number%22%5D | 200 | html |
| project_website | https://patentsview.org/apis/api-endpoints | 200 | html |

## Conclusion — the documented endpoint no longer exists
- **UNAVAILABLE**. `https://search.patentsview.org/...` **does not resolve in DNS**
  (Windows resolver and 8.8.8.8 both answer NXDOMAIN, repeated on 2026-11-09).
- `https://api.patentsview.org/patents/query` returns HTTP 200 but the body is an **HTML
  single-page app shell**, not JSON — the retired API host now serves the project website.
- `https://patentsview.org/apis/api-endpoints` likewise returns that shell, and the shell's own
  `<meta name="description">` says it is **"The Open Data Portal (ODP) … USPTO's data
  platform"** — byte-identical in purpose and in size (20,666 bytes) to `data.uspto.gov/apis`
  from the `uspto_open_data_portal` probe.

## Interpretation (be explicit when citing this)
- The standalone PatentsView API is **gone as an independent source**; the surface has been
  folded into USPTO's Open Data Portal. Counting PatentsView and ODP as two independent
  patent sources would **double-count one upstream authority**.
- `registry/SOURCE_ID_INDEX.json` still lists `patentsview` as a separate P0 with
  `official_url = https://search.patentsview.org/docs/`; that URL is dead. The register record
  written for this source says so.

## If it is ever restored
The v1 API took an `X-Api-Key` header (free registration) and offered `assignee_id` /
`inventor_id` disambiguation — valuable because patent assignee strings are subsidiaries.
It had **no patent-family identifier** and **no pre-grant publication date**, so its only
dated field (`patent_date`) is a grant clock, i.e. systematically later than true public
visibility. It could not have served as a publication clock even when it worked.
