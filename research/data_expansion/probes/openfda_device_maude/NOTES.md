# openfda_device_maude — probe notes

- **source_id**: `openfda_device_maude`
- **最终状态**: `VERIFIED_API`
- **probe 脚本**: `probe.py`（budget=6，min_interval=0.9s；实际 4 次请求）
- **probe 时间**: 2026-11-09（UTC 2026-11-08T21:48Z）
- **官方文档**: <https://open.fda.gov/apis/device/event/>

## 1. 测了什么（真实请求，见 `requests.jsonl`）

| # | 请求 | 结果 |
|---|---|---|
| 1 | `GET /device/event.json?limit=2` | 200，12984 B，2 条真实 MDR |
| 2 | `search=manufacturer_d_name:"Medtronic"&limit=1` | **404 NOT_FOUND** — 裸字段名无法寻址嵌套数组 |
| 3 | `search=device.manufacturer_d_name:medtronic&limit=1` | 200，`meta.total = 3,360,860` |
| 4 | `search=device.manufacturer_d_name:medtronic&count=date_received` | 200，9619 个日期桶，桶和 3,360,860 = meta.total（证明日期桶是穷尽的） |

侦察阶段额外确认（同一 ledger）：

- 全库 `meta.total = 26,557,775` 条。
- `count=device.manufacturer_d_name`（非 `.exact`）→ HTTP 500
  `Text fields are not optimised for aggregations`；**必须用 `.exact` 子字段**。
- `count=device.manufacturer_d_name.exact&limit=1000` → **403 API_KEY_MISSING**：
  无 key 时关键字 count 的桶上限是 **100**（实证，不是假设）。
- `search=recalling...` 之外，`manufacturer_name`（顶层）在历史记录中为空，不能用于企业识别。

## 2. 结论

`VERIFIED_API`。MAUDE = 制造商/进口商/使用机构强制报告 + 自愿报告。

**三个日期是三个不同事实（连接器与每条 `time.notes` 均已分开）：**

| 字段 | 含义 | 在 MedRadar 中的角色 |
|---|---|---|
| `date_of_event` | 事件实际发生日 | **`event_at`** |
| `date_received` | FDA 收到报告的日期 | **`source_public_at`（代理）** |
| `date_report` | 报告者提交日 | 仅存 normalized |
| `date_report_to_fda` | 报告到达 FDA 的日期 | 仅存 normalized |
| `date_added` | 进入数据库的日期 | 仅存 normalized |

`date_received` 只是"FDA 收到"的代理，**不是已验证的首次公开可见日**；契约允许在
notes 标注依据的前提下用它，因此每条证据都写明这一依据。

## 3. 五家企业关联（真实返回）

两步：①服务端 `count=date_received` 得到该关键字族的**报告级**年度计数；
②服务端 `count=device.manufacturer_d_name.exact` 得到精确厂商名分布（无 key 时最多 100 桶），
再用 `CompanyIndex.resolve` 本地解析，confirmed / candidate 分开统计。

| 企业 | 关键字族查询 | 报告数 | 事件日计数和 | 精确名桶 | confirmed device-entry | candidate | 未返回残差 |
|---|---|---|---|---|---|---|---|
| Medtronic | `device.manufacturer_d_name:medtronic` | 3,360,860 | 3,160,723 | 100（触顶） | 3,350,895 | 0 | 9,965 |
| GE HealthCare | `device.manufacturer_d_name:"ge healthcare"` | 3,893 | 2,889 | 100（触顶） | 3,838 | 0 | 43 |
| Philips | `device.manufacturer_d_name:philips` | 202,348 | 83,352 | 100（触顶） | 201,583 | 0 | 736 |
| Dräger | `device.manufacturer_d_name:draeger` | 2,742 | 2,547 | 72（完整） | 2,746 | 1 | 0 |
| Mindray | `device.manufacturer_d_name:mindray` | 3,700 | 3,654 | 89（完整） | 3,702 | 0 | 0 |

**读法（重要）**：

- 年度序列的单位是 **MDR 报告数**；identity census 的单位是**命中报告中的 device-entry 次数**
  （一份报告可含多台器械，所以 device-entry 之和可以略大于报告数，例如 Dräger 2755 > 2742）。
- 触顶的 3 家：`residual_not_returned_by_api` = 未返回桶对应的量，**列为 unknown，绝不摊派**。
- GE 只统计了 `"ge healthcare"` 关键字；旧名 `GE MEDICAL`（MAUDE 里有）**未纳入**该 census，
  这是已声明的方法边界，不是估算成 0。
- Dräger：openFDA 拒绝非 ASCII 检索词（`dräger` → HTTP 400 `Search not supported`），
  只能检索 ASCII 变体，因此 `Dräger` 拼写的记录可能漏检——已在 register 记录。

## 4. 科学纪律（本来源最关键）

- **被动上报数量 ≠ 真实故障率。** MAUDE 没有"在用器械数"分母；openFDA 官方原文：
  "the incidence or prevalence of an event cannot be determined from this reporting system alone
  due to potential under-reporting of events and lack of information about frequency of device use"，
  且报告量上升 "likely caused by improved reporting"。
- 报告数受上报激励、诉讼、媒体报道、产品使用量、FDA 采集力度强烈影响，
  **上升可以只是上报变好，不能解释为质量恶化**。
- 连接器把上述警告写进每条证据的 `normalized["interpretation_warning"]`；
  严禁把报告计数直接当故障率、缺陷率或质量恶化指标使用。
- 一次报告可以含多个器械、多个患者；同一报告的多条 device 不是多条独立事件。

## 5. 请求与样本记账

- `requests.jsonl`：24 行（含侦察；正式 probe 4 行）
- `series_requests.jsonl`：30 行（两次 census 运行；最终一次 15 请求）
- `samples/`：12 个真实切片，见 `samples/SAMPLES.json`；`count_medtronic_date_received.json`
  超 512 KB 截断并标注，`sha256_full = null`。
- 单次运行 ≤ 12 请求，`min_interval = 0.8–0.9 s`。
