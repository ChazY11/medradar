# un_comtrade — UN Comtrade (Comtrade Plus API)

Probe: 2026-11-09, 6 requests, no key.

| probe | URL | status | bytes |
|---|---|---|---|
| hs9018_medical_instruments | https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode=842&period=2023&cmdCode=9018&flowCode=M | 200 | 114128 |
| hs9022_xray_apparatus | https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode=842&period=2023&cmdCode=9022&flowCode=M | 200 | 72705 |
| hs9402_medical_furniture | https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode=842&period=2023&cmdCode=9402&flowCode=M | 200 | 63029 |
| keyed_data_endpoint | https://comtradeapi.un.org/data/v1/get/C/A/HS?reporterCode=842&period=2023&cmdCode=9018&flowCode=M | 401 | 152 |
| developer_portal | https://comtradedeveloper.un.org/ | 200 | 5403 |

## Two different capabilities — do not conflate them

1. **Public preview endpoint — WORKS, no key** (`VERIFIED_API`)
   `https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode=842&period=2023&cmdCode=9018&flowCode=M`
   returned HTTP 200 and a real JSON payload with a `count` and a `data[]` array.
   For reporter 842 (USA) 2023 imports of HS 9018 the preview reported **127 records**
   (one per partner country), each with `primaryValue` (CIF-ish trade value in USD),
   `netWgt`, `qty`, `classificationCode: H6`, `refYear`, `partnerCode`, `flowCode`.
   The three HS codes probed together returned several hundred partner-level rows.
2. **Full data endpoint — REQUIRES A SUBSCRIPTION KEY**
   `https://comtradeapi.un.org/data/v1/get/C/A/HS?...` answered **HTTP 401**:
   `{"statusCode": 401, "message": "Access denied due to missing subscription key."}`
   Comtrade Plus issues free-tier subscription keys by account registration (rate-limited);
   the preview endpoint is the anonymous slice.

## Preview limitations (important, measured)
- The preview returns a *capped* slice. The cap is not stated on any page we could reach
  (`comtradedeveloper.un.org` is only an Azure API Management portal that says "sign up to
  acquire keys"), so treat the cap as UNKNOWN: our largest single response was 127 partner rows /
  114 KB for one HS6 x reporter x year. Large reporter/partner/period combinations may be
  truncated silently — always reconcile the returned `count` before computing totals.
- Some descriptive fields come back `null` in preview (`reporterDesc`, `partnerDesc`,
  `cmdDesc`); only numeric codes are reliable. Any label must come from a separate code list.
- `reporterISO`/`partnerISO` were `null` for the rows we received, so ISO country mapping
  must use `partnerCode` against the Comtrade partner reference table.

## Time semantics
- `period`/`refYear` are **annual** and `refMonth` is the Comtrade month code (`52` = annual
  total). `source_public_at` for a Comtrade annual record: Comtrade publishes a calendar-year
  total only after the year closes, with revisions afterwards. The API exposes no
  `published_at`, so the only defensible clock is `coarse` (year) → **not usable for
  lead-time claims**, only as macro background.

## What this data is NOT
It is **country-level aggregate trade statistics by HS code**. It cannot identify a company,
a shipment, or a product. It must never be used as a proxy for Medtronic/GE/Philips/Dräger/
Mindray activity. Its only valid use in MedRadar is as a macro demand/import-volume
background series for the HS codes a device category belongs to.
