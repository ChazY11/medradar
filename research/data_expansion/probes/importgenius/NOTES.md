# importgenius — ImportGenius

Probe: 2026-11-09, 2 requests, no account, no purchase.

| probe | URL | status |
|---|---|---|
| pricing_page | https://www.importgenius.com/pricing | 200 |
| homepage | https://www.importgenius.com/ | 200 |

## Conclusion
- **PAID_ONLY**. Public pricing page exists and is readable; the data itself is behind a
  paid account. No free API, no free bulk export, no trial without signup.
- Price tokens found on the public page: `$159, $183, $1999, $2,198, $229, $359, $4,310, $449`
  (the page shows a monthly starting price and annual billing; per-plan details vary by
  record volume). Treat these as indicative; the contractual price is whatever the order form
  says.

## Field inventory advertised (from the public site)
- US sea/air import bill-of-lading records: importer name + address, supplier name + address,
  notify party, product description, HS code, weight/quantity, container count, port of
  unlading, carrier, arrival date, bill-of-lading number.
- Supplier↔buyer relationship graphs and shipment counts.

## Licence / redistribution
- Commercial terms; redistribution of raw records is not permitted. Any MedRadar use would be
  internal-analysis only, with no derived-data publication.

## Verdict
This is the only class of source that answers *company-level shipment* questions, and it is
uniformly paid. If MedRadar ever needs firm-level supply-chain evidence, budget for one
vendor rather than expecting an open substitute to appear.
