# eurostat_comext — Eurostat Comext (EU trade since 1988 by HS2-4-6 and CN8)

Probe: 2026-11-09, 4 requests, no key.

| probe | URL | status | bytes |
|---|---|---|---|
| hs9018_de_imports_2023 | https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409?format=JSON&lang=EN&reporter=DE&partner=US&product=9018&flow=1&ti | 200 | 2027 |
| hs9018_de_exports_2023 | https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409?format=JSON&lang=EN&reporter=DE&partner=US&product=9018&flow=2&ti | 200 | 2027 |
| hs9402_de_imports_2023 | https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409?format=JSON&lang=EN&reporter=DE&partner=US&product=9402&flow=1&ti | 200 | 2109 |
| official_data_page | https://ec.europa.eu/eurostat/web/international-trade-in-goods/database | 200 | 195343 |

## Conclusion
- **VERIFIED_API**: the Comext dissemination API is open, keyless and returned real numbers.
  Dataset `DS-045409` = *EU trade since 1988 by HS2-4-6 and CN8*.
- Values observed (annual 2023, reporter DE, partner US, VALUE_IN_EUROS):
  - `hs9018_de_imports_2023` → `{"label": "EU trade since 1988 by HS2-4-6 and CN8", "value": {"0": 2682137903}, "updated": "2026-10-16T11:00:00+0200"}`
  - `hs9018_de_exports_2023` → `{"label": "EU trade since 1988 by HS2-4-6 and CN8", "value": {"0": 3376125154}, "updated": "2026-10-16T11:00:00+0200"}`
  - `hs9402_de_imports_2023` → `{"label": "EU trade since 1988 by HS2-4-6 and CN8", "value": {"0": 15552361}, "updated": "2026-10-16T11:00:00+0200"}`

## Correct call shape (the gotcha)
- The **Comext** base path is `/api/comext/dissemination/statistics/1.0/data/…`, not the plain
  `/api/dissemination/…` used for mainstream Eurostat datasets. The mainstream path answers
  `404 ERR_NOT_FOUND_4: DS-045409 … is not available for dissemination`.
- Dimension names are `freq, reporter, partner, product, flow, indicators, time` — **not**
  `geo`. Using `geo=` returns `400 INVALID_QUERY_DIMENSION: Dimension "GEO" is not defined`.
- `flow=1` imports, `flow=2` exports (Comext convention).
- Response is the standard JSON-stat 2.0 block: `value` keyed by index, `size`, `id`,
  `dimension`; `updated` carries the dataset release timestamp.

## Time semantics
- Annual (`freq=A`) and monthly (`freq=M`) series. Eurostat exposes the dataset `updated`
  timestamp (e.g. `2026-10-16T11:00:00+0200`) — that is a *dataset refresh* time, not the
  publication date of an individual figure. `source_public_at` for a record must therefore be
  `coarse` (month/year) with an explicit note; it may not support lead-time claims.

## What it is NOT
Country-level **aggregate** trade statistics by HS/CN code. No company, no shipment, no
product. Useful as macro demand background for the EU market; useless for firm-level
supply-chain inference.
