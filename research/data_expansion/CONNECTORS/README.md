# CONNECTORS — 可复用连接器索引

本目录不是代码目录，而是**索引与使用说明**。代码位于：

```
medradar/external_sources/
├── __init__.py
├── schema.py        External Evidence Schema v1（信封、校验、去重键）
├── timeq.py         四时钟与时间质量（唯一的准入判断在这里）
├── identity.py      企业与产品身份（确认层 / 候选层强制分离）
├── base.py          有界 HTTP 客户端 + probe 运行器（预算、重试、日志）
├── store.py         隔离 staging 存储（SQLite，幂等、版本化）
├── registry.py      文档层与探针层合并
├── regulatory/      监管与上市后
├── scholarly/       文献
├── trials/          临床试验与资助
├── trade/           专利相关（无）与贸易
└── procurement/     采购与招聘
```

---

## 1. 连接器清单（17 个，全部有离线测试）

| `SOURCE_ID` | 模块 | `kind` | 许可证姿态 | 单次 `collect` 上限 |
|---|---|---|---|---|
| `openalex` | `scholarly/openalex.py` | `publication` | open_licence | 参数化 |
| `crossref` | `scholarly/crossref.py` | `publication` | open_no_explicit_licence | 参数化 |
| `europepmc` | `scholarly/europepmc.py` | `publication` | open_licence | 参数化 |
| `pubmed_eutils` | `scholarly/pubmed_eutils.py` | `publication` | open_no_explicit_licence | 参数化 |
| `clinicaltrials_gov` | `trials/clinicaltrials_gov.py` | `clinical_trial` | public_domain | 参数化 |
| `nih_reporter` | `trials/nih_reporter.py` | `grant` | public_domain | 参数化 |
| `usaspending` | `procurement/usaspending.py` | `procurement_award` | public_domain | 参数化 |
| `uk_find_a_tender` | `procurement/uk_find_a_tender.py` | `procurement_award` | open_licence | 参数化 |
| `greenhouse` | `procurement/greenhouse.py` | `job_posting` | unknown | 需 board token |
| `lever` | `procurement/lever.py` | `job_posting` | unknown | 需 company token |
| `un_comtrade` | `trade/un_comtrade.py` | `trade_aggregate` | open_no_explicit_licence | 参数化 |
| `eurostat_comext` | `trade/eurostat_comext.py` | `trade_aggregate` | open_licence | 参数化 |
| `uk_hmrc_trade` | `trade/uk_hmrc_trade.py` | `trade_by_trader` | open_licence | 参数化 |
| `openfda_device_recall` | `regulatory/postmarket_openfda_device_recall.py` | `recall` | public_domain | 25 |
| `openfda_device_maude` | `regulatory/postmarket_openfda_device_maude.py` | `postmarket_event` | public_domain | 25 |
| `fda_device_shortages` | `regulatory/postmarket_fda_device_shortages.py` | `shortage` | public_domain | 整页（忽略 limit） |
| `fda_import_alerts` | `regulatory/postmarket_fda_import_alerts.py` | `import_alert` | public_domain | 整页（忽略 limit） |

**没有连接器的已验证来源，是有意的**：
`accessgudid`、`canada_mdall`、`openfda_device_510k/pma/bulk`、`eu_ctis`、`eu_cordis`、`eu_ted`、
`semantic_scholar`、`openaire`、`china_ccgp` 均已 probe 验证，但本轮未交付连接器。
其中 `eu_ted` 是**刻意不写**：它的 search API 能返回公告但**不含中标供应商**，
产出"没有供应商的 award"比不产出更糟。

---

## 2. 连接器契约

```python
SOURCE_ID = "openalex"
KIND = "publication"          # schema.EVIDENCE_KINDS 之一
LICENCE_STATUS = "open_licence"

def collect(client, *, limit: int = 50) -> list[dict]:
    """取回 ≤ limit 条真实记录，返回 schema.make_evidence(...) 列表。"""

def to_evidence(raw_item, *, fetched_at) -> dict:
    """单条原始记录 → 证据记录。"""
```

**硬性保证（每个连接器都必须满足，离线测试覆盖）：**

1. **只用 `client.get(...)` / `client.post_json(...)`** —— 共享同一份请求预算与日志，
   不绕过限流、不直连 socket。
2. **分页有上限** —— `limit` 或 `max_pages`，不存在无界循环。
3. **幂等** —— 同一 `source_record_id` 必然得到同一 `evidence_id`；
   重跑不产生第二条证据（内容变化只产生新版本）。
4. **时间走 `timeq.build_time`** —— `event_at`（事件发生）与 `source_public_at`（首次公开）
   必须分开；`first_observed_at` 只等于抓取时钟。
5. **单位/字段缺失写 `null`，不猜。**
6. **企业匹配只用 `identity.CompanyIndex.resolve(...)`** —— `candidate` 永不升级为确认。
7. **`collect()` 不写任何文件** —— 落盘由调用方负责。

---

## 3. 怎么跑

```bash
# 发现所有连接器（不联网）
python research/data_expansion/experiments/harness.py

# 从每个连接器取一份有界样本，写入隔离 staging（默认每源 25 条）
python research/data_expansion/experiments/collect_all.py --limit 25

# 只跑某些源
python research/data_expansion/experiments/collect_all.py --only openalex crossref --limit 10
```

`harness` 会自动适配两种合法签名差异：
- 不声明 `limit` 的连接器（整页来源）→ 只传 `client`；
- 返回 `(records, meta)` 而不是 `list` 的连接器 → 自动解包并把 meta 记入备注。

**这两种差异是记录在案的偏离**，不是静默兼容：`experiments/collection/COLLECTION_REPORT.json`
里能看到每个源实际用了哪种调用方式、返回了什么、以及被拒绝的无效记录数。

---

## 4. Staging 存储

```
research/data_expansion/staging/external_evidence.sqlite   （git-ignored）
```

| 表 | 用途 |
|---|---|
| `collection_runs` | 每次运行一行：请求数、记录数、字节数、状态 |
| `evidence` | `(evidence_id, content_hash)` → 版本 |
| `evidence_head` | 每个证据的首次/最近观测时间、版本数 |
| `entity_refs` | 每个版本的关联（确认与候选同表不同 `method`） |
| `identifiers` | 每个版本的权威标识符 |
| `request_log` | 每个 HTTP 请求（含失败） |

**隔离性：** 与 `data/medradar.sqlite` 无共享表、无外键、无写入路径。删除 staging 不影响任何既有科研资产。

---

## 5. 写一个新连接器（最短路径）

1. 读 `research/data_expansion/COLLECTION_PROTOCOL.md` 第 3 节；
2. 先在 `probes/<source_id>/` 下跑一次 probe，确认状态是 `VERIFIED_*`；
3. 复制一个同类连接器（文献用 `scholarly/openalex.py`，采购用 `procurement/uk_find_a_tender.py`）；
4. 填 `SOURCE_ID` / `KIND` / `LICENCE_STATUS`，实现 `to_evidence` 与有界 `collect`；
5. 在 `tests/test_extsrc_<domain>.py` 加：归一化纯函数测试 + 用内联小样本的 `to_evidence` 测试 +
   `validate_evidence(...) == []` 断言 + 时间语义断言；
6. `python -m medradar selftest` 必须全绿；
7. 用 `harness.py` 确认它能被发现且 `collect_all.py --only <id>` 能跑通。

**不要**为了让连接器"有东西可返回"而放宽 `limit` 或去掉日期上界——
这会把一个诚实的小样本变成一个不可复核的大抓取。
