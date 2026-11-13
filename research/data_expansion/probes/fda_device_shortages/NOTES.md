# fda_device_shortages — probe notes

- **source_id**: `fda_device_shortages`
- **最终状态**: `VERIFIED_PUBLIC_QUERY`
- **probe 脚本**: `probe.py`（budget=4，min_interval=0.9s；实际 2 次请求）
- **probe 时间**: 2026-11-09（UTC 2026-11-08T21:49Z）
- **官方页面**: <https://www.fda.gov/medical-devices/medical-device-supply-chain-and-shortages/medical-device-shortages-list>
- **注意**：`registry/SOURCE_ID_INDEX.json` 里登记的旧 URL
  `.../medical-device-supply-chain/medical-device-shortages` 现在返回 **404**；
  可用页面是上面的 `medical-device-supply-chain-and-shortages/medical-device-shortages-list`。

## 1. 测了什么（真实请求，见 `requests.jsonl`）

| # | 请求 | 结果 | 结论 |
|---|---|---|---|
| 1 | `GET https://api.fda.gov/device/shortage.json?limit=1` | **404** | openFDA **没有** device shortage 端点（负结果证据） |
| 2 | `GET .../medical-device-shortages-list` | 200，128,205 B | 页面源码内直接有 2 个 `<table>`，无需 JS/XHR |

## 2. 结论

`VERIFIED_PUBLIC_QUERY`（不是 UNAVAILABLE）：从 HTML 中解析出**真实条目 + 字段**。

页面两张表（均服务端渲染在源码里）：

1. **Medical Device Shortages List**，6 列：
   `Category / Product Code (Description) / Availability and Estimated Shortage Duration /
   Additional Information / Reason for Interruption (per 506J) / Date (YYYY/MM/DD)`
   → **6 行**。
2. **Medical Device Discontinuance List**，6 列：
   `Date Posted / Category / Product Code / Manufacturer Name / Device Trade Name / Reason for Discontinuance`
   → **236 行**。

解析后生成 **242 条** schema-v1 证据记录（`kind = shortage`，
`normalized.record_type` 区分 `shortage` / `discontinuance`），每条都通过 `validate_evidence`。
`product_code` 从 `"GKZ  (COUNTER, DIFFERENTIAL CELL)"` 这类单元格中拆成 `GKZ` + 描述，
不猜；`Date` 单元格里的 `2026/05/06 initial` 只取首个日期 token。

**时间语义（关键限制）：**

- 页面只发布**列表登记日**（shortage 的 initial / Reverified；discontinuance 的 Date Posted），
  **不发布短缺/停产真正开始的那天**。
- 因此 `source_public_at` = 登记日（`day` 精度），`event_at` = **null**（绝不编造）。
- 所有 HTML 日期按 **MM/DD/YYYY** 解析（`common.us_date_iso`）：`timeq.parse_date` 会先试
  `%d/%m/%Y`，把 `11/06/2026` 误读成 6 月 11 日——这是实测发现并修掉的坑。

## 3. 五家企业关联（真实返回）

- **shortage 表没有厂商列**，只有产品码 → 结构上**无法**做企业关联（不是解析失败）。
- 只有 discontinuance 表有 `Manufacturer Name`。当前快照 236 行共 **37 家不同厂商**，
  用 `CompanyIndex.resolve` 逐一解析后：**五家目标企业 = 0 条 confirmed、0 条 candidate**。
  该清单目前由 Abbott（多个事业部）、SunMed/AirLife、BioFire 等构成，**没有任何一行**属于
  Medtronic / GE HealthCare / Philips / Dräger / Mindray（也不是拼写变体——已用纯文本扫描复核）。
  这是关于**当前快照**的真实负结果，不是"没查到"。

## 4. 科学纪律

- 两张表都是**当前快照，不是档案**：条目解决后会消失，历史状态不可查询，
  所以"现在列表很短"不能证明过去没有短缺，也不能据此构建时间序列。
- 登记日 ≠ 事件日；`Date (YYYY/MM/DD)` 后可能同时有 initial 和 Reverified 两个日期，
  当前只取第一个 token，第二日期不参与计算。
- discontinuance 名单混合了主动停产与制造中断，**不是供应风险评分**。
- HTML 布局变化会使解析失效；因此解析器有离线单测（用真实样本的形状做 fixture），
  并在 `probe.py` 里对表头/行数做断言。

## 5. 请求与样本记账

- `requests.jsonl`：5 行（含侦察；正式 probe 2 行）
- `series_requests.jsonl`：2 行（两次 census 运行各 1 请求）
- `samples/`：1 个完整 HTML（128 KB，未截断）→ `samples/SAMPLES.json`
- 单次运行 1–2 请求，`min_interval = 0.9 s`。
