# openfda_device_recall — probe notes

- **source_id**: `openfda_device_recall`
- **最终状态**: `VERIFIED_API`
- **probe 脚本**: `probe.py`（`base.run_probe`，budget=6，min_interval=0.9s；实际 3 次请求）
- **probe 时间**: 2026-11-09（UTC 2026-11-08T21:48Z）
- **官方文档**: <https://open.fda.gov/apis/device/recall/>

## 1. 测了什么（全部为真实请求，见 `requests.jsonl`）

| # | 请求 | 结果 |
|---|---|---|
| 1 | `GET /device/recall.json?limit=2` | 200，9426 B，返回 2 条真实召回记录 |
| 2 | `GET ...?search=recalling_firm:"Medtronic"&limit=1` | 200，`meta.results.total = 1932` |
| 3 | `GET ...?search=recalling_firm:"Medtronic"&count=event_date_posted` | 200，449 个日期桶，桶和 1599 |

侦察阶段还验证了（同一 ledger）：

- **日期字段是 `event_date_initiated` / `event_date_posted`**；drug enforcement 的
  `report_date` / `center_classification_date` **在该端点不存在**（从真实响应字段列表实证）。
- `skip` 上限 25000；`limit` 上限 1000。
- 单条召回记录很大（约 18 KB/条），`limit=1000` 的响应解压后约 61 MB，会超过
  `HttpClient` 的 8 MB 上限——因此**不做整页拉取**，改用服务端 `count` 聚合（见下）。

## 2. 结论

`VERIFIED_API`：无 key 可访问，返回真实记录，字段与文档一致。

**时间语义（已写入连接器与每条证据的 `time.notes`）：**

- `event_at` = `event_date_initiated`（器械召回发起日；缺失时回退 `event_date_created`）
- `source_public_at` = `event_date_posted`（FDA enforcement 公报发布日，即公众可见日）
- `first_observed_at` = `fetched_at`
- `event_date_terminated` 只作行政状态，绝不当时间钟使用。

**重要数据质量观察**：Medtronic 的 1932 条记录中只有 1599 条有 `event_date_posted`
（333 条缺该字段）；`event_date_initiated` 则 1932 条全有。所以"公开日"序列天然比
"事件日"序列短，缺失不是 0，也不是可估算量。

## 3. 五家企业关联（真实返回，CompanyIndex 确认）

用服务端 `count=recalling_firm.exact`（返回该查询命中集合的**完整精确厂商名分布**），
再用 `identity.CompanyIndex.from_config().resolve(name)` 本地解析每个精确厂商名。
`exact_alias` 才计 confirmed；`candidate` 单独计。

| 企业 | 查询 | 命中记录 | confirmed | candidate | 精确厂商名桶 |
|---|---|---|---|---|---|
| Medtronic | `recalling_firm:medtronic` | 1932 | 1932 | 0 | 60 |
| GE HealthCare | `recalling_firm:"ge healthcare"` + `recalling_firm:"ge medical"` | 1280 | 1280 | 0 | 20 + 13 |
| Philips | `recalling_firm:philips` | 2274 | 2274 | 0 | 40 |
| Dräger | `recalling_firm:draeger` + `recalling_firm:drager` | 146 | 146 | 0 | 3 + 0（`drager` 返回 404 无匹配） |
| Mindray | `recalling_firm:mindray` | 64 | 64 | 0 | 4 |

- 桶数均 < 100，因此**精确厂商名枚举是完整的**（未触发无 key 的 100 桶上限）。
- 另取 1 页真实记录（`limit=100`，`recalling_firm:medtronic`）做记录级校验：
  100 条全部 confirmed，0 candidate。
- 五家在该来源中的 candidate = 0：召回记录的 `recalling_firm` 都是完整法人/事业部串，
  能直接精确命中别名；`Philips Lighting` 之类负例在 device recall 中未出现。

## 4. 科学纪律（必须保留）

- 一条召回 = 一次执法行动，**不是故障率**。没有暴露分母（装机量/使用量），
  且 FDA 只在认为公众需要知情时才公开，企业自我报告纠正动作。
- `event_date_posted` 晚于 `event_date_initiated`，所以召回证据**不能领先于它所报告的事件**，
  只能作为滞后确认；任何"提前量"结论都必须用事件钟而不是抓取日。
- FDA 分类后不再更新召回状态，`Terminated` 不是"产品安全"的证明。

## 5. 请求与样本记账

- `requests.jsonl`：14 行（含侦察请求；正式 probe 3 行）
- `series_requests.jsonl`：47 行（五企业 census 运行，两次完整重建；最终一次 22 请求）
- `samples/`：17 个真实响应切片，见 `samples/SAMPLES.json`；其中
  `records_page_recalling_firm_medtronic_limit100.json` 超过 512 KB，已标注 `truncated: true`，
  `sha256_full` 留 null（不猜）。
- 单次运行请求数均 ≤ 12；`min_interval = 0.8–0.9 s`；未使用 key、未绕过任何限制。
