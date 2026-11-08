# fda_import_alerts — probe notes

- **source_id**: `fda_import_alerts`
- **最终状态**: `VERIFIED_PUBLIC_QUERY`
- **probe 脚本**: `probe.py`（budget=8，min_interval=0.9s；实际 4 次请求）
- **probe 时间**: 2026-11-09（UTC 2026-11-08T21:49Z）
- **入口页**: <https://www.accessdata.fda.gov/cms_ia/ialist.html>
- **设备分类页**: <https://www.accessdata.fda.gov/cms_ia/industrygroup_9.html>

## 1. 测了什么（真实请求，见 `requests.jsonl`）

| # | 请求 | 结果 | 结论 |
|---|---|---|---|
| 1 | `GET https://www.accessdata.fda.gov/cms_ia/` | **403.14** | 目录列表被禁，必须用具体 `.html` 页 |
| 2 | `GET .../cms_ia/ialist.html` | 200，66,100 B | 4 列表格，**154 条** import alert |
| 3 | `GET .../cms_ia/industrygroup_9.html` | 200，27,514 B | 官方 "Medical Devices & Diagnostic Products" 组，**19 个**设备子行业 |
| 4 | `GET .../cms_ia/importalert_1182.html` | 200，44,684 B | 单条 alert 详情页真实存在（含 Red List） |

侦察阶段还确认：`iapublishdate.html` 同构（154 条，按最后发布日排序）；
设备相关 alert 的详情页大小差异很大（44 KB ~ 5.07 MB，Red List 用 `<div>` 而非 `<table>`）。

## 2. 结论

`VERIFIED_PUBLIC_QUERY`：**无 openFDA 端点**，但索引页结构化可解析，产出真实记录。

`ialist.html` 的 4 列：

`Import Alert Number | Import Alert Type | Publish Date | Import Alert Name`

→ 解析出 **154 条** schema-v1 证据记录（`kind = import_alert`），每条含
alert number（如 `76-01`）、类型（DWPE）、Publish Date、名称、详情页 URL。
设备维度有官方页面：`industrygroup_9.html` 列出 19 个设备子行业
（`industry_73.html` … `industry_91.html`）。按名称关键字筛出的设备类 alert 为 **10 条**
（该筛选仅为便捷，**不是**权威分类，payload 里已标注 `is_authoritative = false`）。

**时间语义：**

- `source_public_at` = 该 alert 的 **Publish Date**（MM/DD/YYYY → ISO，`day` 精度）。
- `event_at` = **null**：索引不发布违规/检查日期，不编造。

## 3. 五家企业关联（**UNKNOWN**，如实记录）

- 索引表**没有公司列**；公司名只存在于每条 alert 详情页的 "Red List"（div 结构，
  单页可达数 MB）。
- 有界抽样：抓取 3 个设备类 alert 的详情页并做**纯文本**扫描
  （`importalert_1182` / `231` / `241`），五家别名命中数全部为 **0**。
  这只是一个关于这 3 个页面的**负观察**，**不是**五家企业在该来源的普查结论。
- 因此 `FIVE_FIRM_SERIES.json` 中该来源的 firm-level 覆盖记为 `UNKNOWN`，
  原因写明"索引无公司列；逐条 Red List 枚举超出预算"。
- 即使命中，也只能是 `candidate`（文本匹配不是 identity 关联），不得升级为确认。
- 154 条 alert × 每页数 MB 的 Red List，在 ≤12 请求/次的预算内无法做完整企业普查；
  这是**如实的范围限制**，不是放弃。

## 4. 科学纪律

- import alert 是**针对外国生产场所/产品类型的扣留指令**（DWPE），不是企业质量评级；
  列入/移出 Red List 是行政行为，**不在当前列表 ≠ 合规历史良好**。
- Publish Date 是 alert 发布/修订日，不是违规发生日。
- 解析依赖页面结构（div Red List），布局变化会失效；索引表解析有离线单测。

## 5. 请求与样本记账

- `requests.jsonl`：16 行（含侦察；正式 probe 4 行）
- `series_requests.jsonl`：10 行（两次 census 运行；最终一次 5 请求）
- `samples/`：5 个真实切片（`ialist.html`、`industrygroup_9_medical_devices.html`、
  3 个 alert 详情页），见 `samples/SAMPLES.json`；`importalert_241.html` 579 KB 超过
  512 KB 内联上限，已标注 `truncated: true`，`sha256_full = null`。
- 单次运行 ≤ 8 请求，`min_interval = 0.8–0.9 s`。
