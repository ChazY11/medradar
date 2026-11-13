# china_ccgp — probe notes

**Status: VERIFIED_PUBLIC_QUERY** · 2 requests · 2026-11-09 · no login, no captcha solved

## What was tested

| # | Request | Result |
|---|---|---|
| 1 | `GET http://www.ccgp.gov.cn/` | 200, portal HTML |
| 2 | `GET http://search.ccgp.gov.cn/bxsearch?...&kw=内窥镜` | 200, 50 KB, **90 real announcements** |

The keyword `内窥镜` (endoscope) returned a result list with real, dated
announcements, e.g.:

> 新疆维吾尔自治区第三人民医院进口新生儿科电子支气管内窥镜采购项目**废标公告** …
> 2026.11.07 18:24:08 | 采购人：新疆维吾尔自治区第三人民医院

## What this positive result does **not** license

* **The listing mixes announcement types.** The same page contains
  采购公告 (tender notice), 中标/成交公告 (award), 废标公告 (failed tender) and
  更正公告 (correction). Counting the listing as "tenders" would conflate
  notice with award — exactly the error the task forbids.
* **The search form carries a captcha field** (`请输入左侧验证码`). This keyword
  query answered without it, but that cannot be assumed to hold; the task did
  not attempt to solve a captcha and no challenge was bypassed.
* No structured supplier identifier in the listing; winner names live inside the
  announcement body, so award→supplier linking needs per-notice fetches and
  free-text parsing.
* Only 2 requests were made. Any coverage statement beyond "the search page
  answers with real records" would be unsupported.

## Docs / policy opened

* <http://www.ccgp.gov.cn/> — no explicit reuse licence found on the page opened,
  so `redistribution_allowed` is recorded as `UNKNOWN`.

## Artifacts

* `requests.jsonl`, `PROBE_RESULT.json`
* samples: `../../../samples/china_ccgp/` (portal home + search page, hash-verified)
