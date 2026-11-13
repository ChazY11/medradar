# MedRadar External Evidence Schema v1

**标识：** `medradar.external.evidence.v1`
**实现：** `medradar/external_sources/schema.py`、`timeq.py`、`identity.py`、`store.py`
**状态：** 已实现并通过 38 个离线单测（`tests/test_external_sources_foundation.py`）

> 本文档是**契约**。任何字段语义改动必须先改本文档再改代码（沿用 `docs/SCHEMA.md` 的既有规则）。

---

## 1. 设计目标与不变量

跨来源外部证据最容易在四个地方静默出错。Schema 的每一条设计都对应其中一个：

| 失败模式 | 后果 | 本 Schema 的对策 |
|---|---|---|
| **时间塌缩**：把"事件发生日""首次公开日""我们抓到它的日子"混成一个字段 | 回测出现前视偏差；提前量被系统性高估 | 四个时钟强制分离，公开时间带质量等级，`first_observed_at` 永不回填 |
| **重复计数**：同一原始记录经聚合平台重复出现被当作多条独立证据 | 覆盖率与证据强度被虚增 | `canonical_key` 只由权威标识符构成；跨源同键判为重复 |
| **身份幻觉**：关键词相同即视为同一产品/企业 | 错误关联混入确认集，污染一切下游统计 | 确定性关联与 `candidate` 分层存储；`candidate` 置信度上限 0.75 且不得达到 0.9 |
| **不可追溯**：只存归一化结果，原始字节丢失 | 无法复核，也无法发现解析错误 | 原始体按内容哈希存储；归一化哈希与原始哈希都进 provenance |

**不变量（代码强制）：**

- **I1** 一条 `evidence_id` 标识一个**记录**，与其内容、抓取时间无关；
  内容变化产生**新版本**，不产生新证据项。
- **I2** `content_hash = sha256(canonical_json(normalized))`，`provenance.normalized_content_hash` 必须等于它。
- **I3** `raw.content_hash` 必须是完整原始响应的 sha256（截断的样本另行标注 `truncated`）。
- **I4** 任何记录都必须有 `event_at`、`source_public_at`、`first_observed_at`、`fetched_at` 四个键（可为空串，但键必须存在）。
- **I5** `source_public_at_quality` 必须属于 `{exact, day, coarse, derived, unknown}`。
- **I6** `candidate` 关联的 `confidence < 0.9`；确认级关联必须写出 `evidence`（凭什么确认）。
- **I7** 没有权威标识符的记录 `canonical_key = null`，且**不得**参与跨源去重。

---

## 2. 记录信封

```jsonc
{
  "schema": "medradar.external.evidence.v1",
  "evidence_id": "ev_<32 hex>",              // 稳定：sha256(source_id|kind|source_record_id)
  "kind": "device_registration",             // 见 §3
  "source_id": "accessgudid",
  "source_record_id": "DI:00812345678901",   // 来源内的原生标识，越稳定越好
  "source_url": "https://accessgudid.nlm.nih.gov/api/v3/devices/lookup?di=...",
  "collection_run_id": "run_accessgudid_20261109T054000Z",
  "fetched_at": "2026-11-09T05:40:00Z",

  "normalized": { /* 归一化后的类型化字段，见 §3 */ },
  "identifiers": [
    {"scheme": "di", "value": "00812345678901", "raw_value": "0081 2345 6789 01",
     "is_primary": true, "note": ""}
  ],
  "entity_refs": [
    {"entity_type": "company", "name_raw": "Medtronic MiniMed",
     "resolved_key": "medtronic", "method": "exact_alias", "confidence": 0.95,
     "evidence": {"matched_alias": "MEDTRONIC MINIMED"}, "note": ""}
  ],
  "time": {
    "event_at": "2024-01-15",                // 事件发生日
    "source_public_at": "2024-02-01",        // 首次对公众可见日
    "first_observed_at": "2026-11-09T05:40:00Z",  // 我们第一次看到它（fetch 时钟）
    "fetched_at": "2026-11-09T05:40:00Z",
    "source_public_at_quality": "day",       // exact|day|coarse|derived|unknown
    "observation_basis": "fetch_clock",
    "notes": ""
  },
  "provenance": {
    "source_name": "AccessGUDID",
    "licence_status": "public_domain",
    "redistribution": "allowed",
    "attribution": "",
    "evidence_reference": "",               // 人可读的复核指引（文件+行/URL+查询串）
    "raw_path": "samples/accessgudid/lookup.json",
    "raw_content_hash": "<sha256>",
    "normalized_content_hash": "<sha256>",
    "source_time_quality": ""
  },
  "canonical_key": "di:00812345678901",      // 去重键，可为 null
  "content_hash": "<sha256>",                // == provenance.normalized_content_hash
  "raw": {"content_hash": "<sha256>", "bytes": 128, "path": "..."}
}
```

`raw` 与 `provenance` 有重叠是刻意的：`raw` 是机器校验用，`provenance` 是人读用。
校验器会检查两者不矛盾。

---

## 3. 实体与证据类型

### 3.1 实体（Entity）

| 实体 | 关键标识 | 在 MedRadar 中的角色 |
|---|---|---|
| 企业（company） | `company_key`（内部）、官方企业号（CIK/LEI/备案号） | 主分析单位 |
| 企业历史名称 / 别名 | 归一化名 + 时间段 | **防止把历史实体回填给今天的母公司** |
| 子公司 | 归属关系 + 起止时间 | 同上 |
| 医疗器械产品 | DI / Basic UDI-DI / 注册证号 / 510(k)/PMA 号 | 产品级判断的单位 |
| 技术领域 | MedRadar `track_id`（既有 taxonomy） | 与既有体系对接 |
| 监管事件 | 官方编号（`K…`/`P…`/召回号/证书号） | 锚点 |
| 专利 | 专利号（规范化为无分隔大写） | 技术方向证据 |
| 论文 | DOI（优先）/ PMID / PMCID | 研究活动证据 |
| 临床试验 | NCT / EudraCT 等注册号 | 研究→临床证据 |
| 采购合同 | 合同/授予 ID | 市场采用证据 |
| 招聘岗位 | `(company, title, location, source_board)` 去重键 | 能力建设证据 |
| 供应链运输记录 | 提单号 / 批次 ID（若可得） | 生产与供应网络证据 |

**企业时间边界是硬要求。** "Covidien 在 2015 年的记录"属于 Covidien；
把它直接算作 Medtronic 的历史，是**事后信息泄漏**。`entity_refs` 因此允许
`valid_from`/`valid_to`，并在 EXP-C 中把跨越收购边界的关联从强证据层剔除。

### 3.2 证据类型（`kind`，代码封闭集）

| kind | 典型来源 | 关键归一化字段 |
|---|---|---|
| `device_registration` | AccessGUDID、MDALL、EUDAMED、TGA | DI、商品名、型号、制造商、发证/生效日 |
| `regulatory_clearance` | openFDA 510(k)/PMA、CE 证书 | 官方编号、申请人、产品代码、决策日 |
| `postmarket_event` | MAUDE | 报告号、事件类型、器械、`date_received` |
| `recall` | openFDA recall | 召回号、分类、发起日、数量 |
| `import_alert` | FDA import alerts | 警报号、国家、产品、发布日 |
| `shortage` | FDA shortages | 器械、短缺状态、起止日 |
| `patent` | EPO OPS / USPTO / PatentsView | 专利号、申请人、IPC/CPC、**公开日** |
| `publication` | OpenAlex / Europe PMC / Crossref / PubMed | DOI/PMID、作者、机构、首次发表日期 |
| `clinical_trial` | ClinicalTrials.gov / CTIS | 注册号、申办者、`studyFirstPostDate` |
| `procurement_notice` | TED / SAM.gov / Find a Tender | 公告号、买方、CPV/产品描述、发布日期 |
| `procurement_award` | USAspending | 授予 ID、受让方、金额、履约开始日 |
| `grant` | NIH RePORTER / CORDIS / SBIR | 项目号、机构、金额、开始日 |
| `job_posting` | Greenhouse / Lever / Workday | 岗位 ID、标题、地点、`created_at` |
| `shipment` | 企业级提单（商业） | 进口商/出口商、HS、发货日 |
| `trade_aggregate` | UN Comtrade / Census / Eurostat | 报告国、伙伴国、HS、期间、金额/数量 |
| `company_registry` | 企业注册库 | 法律名、注册号、状态 |

> **`shipment` 与 `trade_aggregate` 是两种不同的数据，禁止互换。**
> 前者可识别企业，后者只能到国家×HS 层。Schema 用不同 `kind` 强制这一区分。

---

## 4. 身份与置信度

### 4.1 关联方法分层（`entity_refs[].method`）

| method | 含义 | 是否计入"确认关联" | 置信度区间 |
|---|---|---|---|
| `official_id` | 权威标识符匹配（CIK、DI、注册号等） | ✅ 是 | 0.95–1.00 |
| `exact_alias` | 归一化后命中注册别名（含 token 对齐 + 负向守卫） | ✅ 是 | 0.90–0.97 |
| `multi_field` | 别名 + ≥1 个独立字段一致（国别、型号等） | ✅ 是 | 0.97 |
| `candidate` | 语义/模糊候选 | ❌ **否** | 0.40–0.75 |
| `none` | 拒绝匹配 | ❌ 否 | 0.0 |

**代码强制：** `candidate` 的置信度不得 ≥ 0.9（`validate_evidence` 会报错）。
这条规则存在的唯一目的，是让"看起来很确定"的猜测无法悄悄进入确认集。

**负向守卫（negative guard）：** 某些字符串包含目标企业 token 却属于另一家公司
（`PHILIPS LIGHTING`、`GE AVIATION`、`PHILIPS 66`）。命中守卫时不丢弃，而是
**降级为 `candidate` 并记录 `negative_guard` 字段**，以便审计"降级是否过度"。

### 4.2 跨来源去重键 `canonical_key`

优先级固定（`schema.canonical_key`）：

```
di > basic_udi_di > licence_no > 510k > pma > denovo > recall_number
   > nct > doi > pmid > patent_no > award_id > accession
```

- 只使用**权威标识符**。名称、关键词、标题**一律不参与**。
- 无权威标识符 → `null` → 不参与去重（宁可少去重，也不误去重）。
- 同一 `canonical_key` 的两条记录 = 同一条上游事实的不同呈现，**不构成独立证据**。
- 聚合平台（如把 openFDA 数据再包装的第三方站）因此不会虚增证据量。

### 4.3 关联阶梯（匹配策略的强弱顺序）

1. 官方统一标识符
2. 产品型号 + 制造商一致
3. 可验证的公司/产品注册关系
4. 多字段联合证据（≥2 独立字段）
5. 语义候选（**必须单独保存、单独统计、单独报告**）

**诱饵对照（decoy control，强制）：** 任何"关联成功率"必须同时报告一个匹配负例的误连率
（同企业、日期 ±2 年、不同产品代码）。没有诱饵对照的关联率不作为证据。

---

## 5. 时间模型

### 5.1 四个时钟

| 字段 | 回答的问题 | 典型错误 |
|---|---|---|
| `event_at` | 事情**发生**在什么时候？ | 用抓取日代替 |
| `source_public_at` | 世界**最早什么时候能知道**它？ | 专利用申请日；论文用期刊期号日；试验用 startDate |
| `first_observed_at` | **我们**第一次看到它是什么时候？ | 回填历史数据时伪造成历史观测 |
| `fetched_at` | 这一份副本是什么时候取的？ | — |

### 5.2 质量等级

| 值 | 含义 | 可用于提前量结论 |
|---|---|---|
| `exact` | 完整时间戳 | ✅ |
| `day` | 日精度日期 | ✅ |
| `coarse` | 月/年精度或区间 | ❌ 仅描述性 |
| `derived` | 我们从其他信息推断的 | ❌ |
| `unknown` | 未公开 | ❌ |

`timeq.quality_allows_lead_time()` 是唯一的准入判断，不允许调用方自行放宽。

### 5.3 分来源的强制规则

- **专利**：`source_public_at` = 公开日（publication date），**绝不是申请日/优先权日**。
  申请日可放 `event_at`，但不得用于"当时可见"的推断。
- **论文**：`source_public_at` = 首次在线发表日期。
  OpenAlex `created_date`、Crossref `deposited` 是**元数据录入时间**，只能作为附加信息，
  不得当作公开发表日。
- **临床试验**：`source_public_at` = `studyFirstPostDate`（首次登记公开日）。
- **采购**：`source_public_at` = 公告发布日；`event_at` = 授予/履约开始日（若不同必须分开）。
- **上市后事件**：`event_at` = 事件发生日；`source_public_at` 可用 `date_received`
  （FDA 收到报告的日期），但必须在 `notes` 写明这一选择的依据。

### 5.4 `first_observed_at` 的诚实性

除来源本身提供可验证的观测历史外，`first_observed_at` **一律等于 `fetched_at`**。
`timeq.build_time` 在实现上就不允许把它默认成 `source_public_at`。
这条限制会让"我们其实早就知道"这类说法无法成立——这正是目的。

---

## 6. 溯源（Provenance）

| 字段 | 作用 |
|---|---|
| `source_name` / `source_record_id` / `source_url` | 定位原始记录 |
| `raw_content_hash` | 完整原始字节的 sha256（可独立复核） |
| `normalized_content_hash` | 归一化后内容的 sha256（与 `content_hash` 相同） |
| `collection_run_id` | 哪一次采集（可重跑） |
| `licence_status` / `redistribution` | 该条记录的使用边界 |
| `evidence_reference` | 人可读复核指引（查询串、页码、文件行号） |

**职责分离：**

- `store.raw_objects` 保存原始字节（按 sha256 寻址，不重复存）；
- `store.evidence` 保存每个 `(evidence_id, content_hash)` 版本；
- `store.evidence_head` 保存记录的首次/最近观测时间与版本数；
- 样本文件进 Git 时**全部截断上限 512 KB** 并记录 `sha256_full` 与 `truncated` 标志。

---

## 7. 存储与幂等

`StagingStore`（SQLite，位于 `research/data_expansion/staging/`，**不入 Git**）：

```
collection_runs   每次采集一行（requests / records / raw_bytes / status）
raw_objects       sha256 → 原始字节元数据
evidence          (evidence_id, content_hash) → 版本
evidence_head     evidence_id → first_observed_at, versions, duplicate_of
entity_refs       每个版本的实体关联（确认与候选同表不同 method）
identifiers       每个版本的权威标识符
request_log       每个 HTTP 请求（含失败）
```

**幂等性验证（单测覆盖）：** 同一记录重复 `upsert` 不新增行；内容变化时
`versions` +1 且 `first_observed_at` 保持最早值。

**隔离性：** 本 store 与 `data/medradar.sqlite` 无任何共享表、无外键、无写入路径。
删除 `staging/` 不影响任何既有科研资产。

---

## 8. 质量门

`validate_evidence()` 会拒绝下列记录（单测逐条覆盖）：

- 未知 `kind`；
- 四时钟缺键；
- 时间质量不在枚举内；
- `raw.content_hash` 不是合法 sha256；
- `provenance.licence_status` 不在枚举内；
- 归一化哈希与 `content_hash` 不一致；
- `candidate` 关联置信度 ≥ 0.9；
- 确认级关联缺少 `evidence`。

写入前校验失败 → 抛 `EvidenceError`，**不落库**。宁可不写，也不写坏数据。

---

## 9. 与 MedRadar 既有 schema 的关系

本 Schema **不替换** `docs/SCHEMA.md` 的 `metrics.json` 契约，也不写入既有事实表。
映射关系：

| 本 Schema | MedRadar 既有 |
|---|---|
| `event_at` | `events.event_date` |
| `source_public_at` | `events.published_at` |
| `first_observed_at` | `events.first_seen_at` |
| `source_public_at_quality` | `events.timestamp_quality` |
| `company_key` | `companies.key` |
| `track_id` | `tracks.id`（`config/tracks_device.json`） |
| `canonical_key` | 新增：既有库没有跨源去重键，这是本轮的主要贡献之一 |

未来若要合并进主库，走"外部证据 → 事件表"的显式适配器，
**不得**让外部采集直接写 `data/medradar.sqlite`。

---

## 10. 已知局限（必须随结果一起披露）

1. **`first_observed_at` 是抓取时钟**，不是知识时钟。任何"当时是否可知"的问题只能用
   `source_public_at`，且需要来源确实公开了该日期。
2. **`canonical_key` 依赖来源提供权威标识符**。不提供标识符的来源无法去重，
   其"记录数"不可与其他来源直接相加。
3. **企业归属的时间边界**目前只有别名表，没有系统化的收购时间线；
   跨收购的关联在 EXP-C 中被标为需要人工核查。
4. **`candidate` 层不参与任何确认性统计**，因此本轮所有 precision 类指标的分母都偏小，
   且偏向"有权威标识符"的记录——这一偏差在选择偏差一节中必须写明。
5. **Schema 不解决来源本身的测量偏差**（例如被动上报数量不等于故障率）。
   这属于分析层责任，在 `DATA_QUALITY_REPORT.md` 中逐来源说明。
