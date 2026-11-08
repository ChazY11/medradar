# china_customs_stats — 中国海关统计数据在线查询平台 / China Customs statistics

Probe: 2026-11-09, 3 requests.

| probe | URL | status | note |
|---|---|---|---|
| stats_portal | http://stats.customs.gov.cn/ | 412 | HTTP 412 Precondition Failed |
| customs_website | http://www.customs.gov.cn/ | 412 | HTTP 412 Precondition Failed |
| query_endpoint_guess | http://stats.customs.gov.cn/queryData | 412 | HTTP 412 Precondition Failed |

## Conclusion
- **UNAVAILABLE**. `stats.customs.gov.cn` answers non-browser clients with **HTTP 412** and an
  anti-automation interstitial (obfuscated JS challenge). `www.customs.gov.cn` (the ministry
  portal) returns 200 but carries only news/policy pages, no query interface.
- The statistics platform is a form/captcha-driven query UI with no documented API and no
  bulk download for anonymous users. There is no lawful automated path.

## What would be needed
- A registered/browser session with captcha solving (out of policy), or
- the paid customs data products (China Customs / commercial resellers).

## What it would provide
- China's own import/export statistics by HS code and partner country — the authoritative
  mirror for Chinese device imports/exports, still **aggregate** (no company identities).
- Note that Chinese customs does not publish company-level bill-of-lading data; the
  company-level Chinese export data sold by vendors comes from separate sources.
