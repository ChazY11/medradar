# wipo_patentscope — WIPO PATENTSCOPE

Probe: 2026-11-09, 4 requests, no credentials.

| probe | URL | status |
|---|---|---|
| search_ui_page | https://patentscope.wipo.int/search/en/search.jsf | 200 |
| data_products_page | https://www.wipo.int/patentscope/en/data/ | 200 |
| pct_data_products_subscription_page | https://www.wipo.int/en/web/patentscope/data/subscribe-pct-data-products-services | 200 |
| undocumented_api_guess | https://patentscope.wipo.int/search/api/search?q=stent | 404 |

## Conclusion
- **REQUIRES_REGISTRATION**: no open machine interface. The search UI is a JSF application (server-side
  session state, `j_idt` view ids); scraping it is brittle *and* outside the collection policy,
  so it was not attempted beyond one liveness check.
- The data-products page links a **subscription** channel for PCT data products
  (`…/data/subscribe-pct-data-products-services`), i.e. PATENTSCOPE data is registration /
  subscription gated, not open. An undocumented `/search/api/…` path is 404.

## What PATENTSCOPE uniquely adds (if ever registered)
- **WO (PCT) publications**: published 18 months from priority, *before* most national grants,
  and for many jurisdictions it is the only public trace of the application. For a
  public-visibility clock this is materially earlier than US grant data.
- INPADOC-style family/national-phase entries, IPC/CPC, applicant and inventor with addresses.

## Time semantics
The correct `source_public_at` is the WO publication date; the priority date is `event_at`.
