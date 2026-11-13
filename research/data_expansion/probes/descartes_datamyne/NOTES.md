# descartes_datamyne — Descartes Datamyne

Probe: 2026-11-09, 3 requests, no account.

| probe | URL | status |
|---|---|---|
| datamyne_home | https://www.datamyne.com/ | 200 |
| descartes_datamyne_page | https://www.descartes.com/datamyne | 200 |
| descartes_solutions_page | https://www.descartes.com/solutions/customs-and-regulatory-compliance | 200 |

## Conclusion
- **PAID_ONLY**. Datamyne is a commercial trade-data product (now under Descartes); both
  datamyne.com and the Descartes product page are marketing pages only. Pricing is by quote;
  there is no public price list, no free tier, no API key available without a contract.
- Note: the `official_url` in `SOURCE_ID_INDEX.json`
  (`https://www.descartes.com/solutions/global-trade-data`) is **404** — the product moved.
  The live product page is `https://www.descartes.com/datamyne` (200, saved).

## Field inventory advertised
- Latin-America-origin and US customs bill-of-lading records: importer/exporter names and
  addresses, HS codes, product descriptions, weights, FOB values, ports, dates, carriers.
- Datamyne's differentiator is Latin American import records (Brazil, Colombia, Peru, Chile…).

## Verdict
Paid only, quote-based, licence restricted. Same class as Panjiva/ImportGenius.
