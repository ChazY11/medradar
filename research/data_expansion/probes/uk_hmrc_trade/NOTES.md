# uk_hmrc_trade — HMRC UK Trade Info API (OData)

Probe: 2026-11-09, 5 requests, no key.

| probe | URL | status | bytes |
|---|---|---|---|
| service_document | https://api.uktradeinfo.com/ | 200 | 920 |
| trader_search_medtronic | https://api.uktradeinfo.com/Trader?%24filter=contains%28CompanyName%2C%27MEDTRONIC%27%29&%24top=5&%24select=TraderId%2CCompanyName%2CPostCode | 200 | 461 |
| yearly_trade_presence | https://api.uktradeinfo.com/YearlyTrade?%24filter=TraderId+eq+213902+and+Year+eq+2023&%24top=5 | 200 | 1543 |
| commodity_search_hs9018 | https://api.uktradeinfo.com/CommoditySearch?%24filter=startswith%28Hs4Code%2C%279018%27%29&%24top=2 | 200 | 1289 |
| ots_aggregate_sample | https://api.uktradeinfo.com/OTS?%24top=2 | 200 | 420 |

## Conclusion — the most interesting open trade source surveyed
- **VERIFIED_API**: `https://api.uktradeinfo.com/` is an open OData v4 service, no key, no
  registration. Everything below was returned live.

### Entity sets exposed (from the service document)
`Commodity, CommoditySearch, Country, Date, Export, FlowType, Import, OTS, Port, Region,
RTS, SITC, Trade, Trader, TradeType, YearlyTrade`.

### It publishes NAMED TRADERS, not just national totals
- `Trader` has `TraderId, CompanyName, Address1-5, PostCode`.
  A `contains(CompanyName,'MEDTRONIC')` filter returned real rows, e.g.
  `MEDTRONIC VASCULAR GALWAY UNLIMITEDCOMPANY`, `MEDTRONIC LIMITED`, `MEDTRONIC INTERNATIONAL
  TRADING SARL`, `MEDTRONIC BIOPHARMA B.V.`; `PHILIPS` returned `PHILIPS CONSUMER LIFESTYLE
  BV`, `PHILIPS IN LIGHTING LTD`; `DRAEGER` returned `DRAEGER MEDICAL UK LTD`; `MINDRAY`
  returned `MINDRAY UK LTD`.
- `Trade` / `YearlyTrade` join `TraderId × CommodityId (CN8) × MonthId` (plus
  `TradeTypeId`); `YearlyTrade.ImportMonths` / `ExportMonths` list the months in which that
  trader traded that CN8 code.
- **There are no values, quantities or partners at trader level.** `Trader`-joined records
  are *presence* evidence (who traded which commodity, in which month, import or export),
  not shipments and not amounts.
- `OTS` (aggregate) is the entity that does carry `Value`, `NetMass`, `SuppUnit`, keyed by
  `MonthId × FlowTypeId × CommodityId × CountryId × PortId` — that is the national aggregate.

### Practical caveats measured on real rows
- Company names are raw declarant strings with OCR-grade noise
  (`PHILIPS PHILIPHS`, `MEDTRONIC VASCULAR GALWAY UNLIMITEDCOMPANY`). Alias matching must stay
  in the `candidate` tier unless manually reviewed.
- The same `PostCode` (`AB10 1ZP`) and address (`HM REVENUE AND CUSTOMS, RUBY HOUSE, ABERDEEN`)
  appears for several non-UK-established traders — the address is HMRC's own, so address is
  **not** a usable disambiguator for those rows.
- Supplier/consumer names in HMRC OTS trader tables are rounded/processed by HMRC; treat them
  as published administrative data, subject to HMRC's own terms.
- `Commodity` entity rejects `startswith(Cn8Code,...)` filters with a 500-class runtime error;
  use `CommoditySearch` (Hs2/Hs4/Hs6 + description) instead.

## Time semantics
- `MonthId` is `YYYYMM`; `YearlyTrade` carries `Year`. Publication of a month's trader data
  lags the month by several months (HMRC publishes OTS trade in arrears). The API exposes no
  published-at field, so `source_public_at` must be `coarse` with the lag documented, or the
  record must be flagged as not lead-time-eligible.
