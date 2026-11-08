# 数据质量报告（DATA-EXPANSION-001）

**范围：** 本轮采集的 688 条证据（staging 去重后 688 个 evidence_id / 693 个版本）、
31 个已验证来源、58 个已探测来源的请求日志。
**原则：** 只报告能被 `probes/`、`samples/`、`staging/` 三类证据支持的事实。
凡是"看起来应该没问题但没有证据"的，写 `UNKNOWN`。

---

## 0. 质量结论摘要

| 项目 | 结果 |
|---|---|
| Staging 证据数（去重后 / 版本） | **688 / 693**（5 次内容变更产生新版本，未产生新证据） |
| 企业关联 | 确认级 **92** 条（`exact_alias` 为主），候选级 **1** 条 |
| 重复检测 | 内容哈希重复 **8** 条（shortages 242→234）全部被识别为同版本，未虚增 |
| 时间语义 | 688 条中 `source_public_at` 非空且有日期精度者占多数，但 **5 个来源完全没有公开日字段**（见 §4） |
| 采集请求 | 探针类 346 次 + 实验类 337 次 + C3 14 次；失败请求 **102** 次全部留证 |
| 过程缺陷 | **2 起**：SAMPLES.json 越界写（已修）、61MB 响应挂起（已规避） |
| 已知未修复缺陷 | `collection_run_id` 为空、`raw_objects` 表未使用（见 §7） |

---

## 1. 覆盖与代表性

**本轮采集不是"全量镜像"，而是"可审计的小样本"。** 每个连接器单次运行最多取 25 条，
目的有二：（a）验证字段与时间语义；（b）留下可复核的真实切片。
因此**任何"总量"陈述都不应从这 688 条外推**——它们证明接口可用，不证明数据集规模。

| 类别 | 条数 | 说明 |
|---|---|---|
| `publication` | 100 | 4 个文献源各 25 |
| `shortage` | 229 | FDA 短缺/停产页解析 |
| `import_alert` | 154 | FDA 进口警报索引 |
| `procurement_award` / `procurement_notice` | 40 / 10 | USAspending、UK FTS |
| `trade_aggregate` / `trade_by_trader` | 30 / 25 | Comtrade、Eurostat、HMRC |
| `clinical_trial` | 25 | CT.gov |
| `grant` | 25 | NIH RePORTER |
| `recall` / `postmarket_event` | 25 / 25 | openFDA |

---

## 2. 缺失（missingness）

| 现象 | 证据 | 影响 |
|---|---|---|
| **Medtronic recall 缺 17% 的公开日** | 1,932 条 recalled 中只有 1,599 条有 `event_date_posted`；`event_date_initiated` 全有 | 用公开日做年度序列会**静默丢 333 条**，且缺失不是随机零 |
| **MAUDE 顶层 `manufacturer_name` 为空** | 历史记录中为空，必须用 `device.manufacturer_d_name` | 用错路径会得到"零记录"，且不会报错 |
| **Comtrade preview 描述字段为 null** | `reporterDesc`/`partnerDesc`/`cmdDesc` 在 preview 端点全部为 null | 只能用数字代码，标签需另表连接 |
| **USAspending 无公开日** | award 记录只有 action / signature / performance 日期 | `source_public_at` 只能留空，`quality=unknown` |
| **shortages 只有停产值有厂商列** | 短缺表无厂商列；当前快照 37 家厂商，五家 0 条 | 五家 0 条是**真实负结果**，不是解析失败 |
| **import alerts 索引无公司列** | 154 条 alert 的 Red List 单页 44KB–5MB，超预算 | 企业级覆盖记 `UNKNOWN`，不猜 |

---

## 3. 重复（duplication）

| 类型 | 结果 | 处理 |
|---|---|---|
| **同源重复**（同一 `(evidence_id, content_hash)` 重复入库） | 8 条（shortages 242→234） | 幂等 upsert 识别为同版本，不新增证据 |
| **跨源重复**（同一作品被多源收录） | 同一 DOI 在 4 源 → 4 条 → 1 篇唯一作品（**重复率 75%**） | `canonical_key` 以 DOI 归一（小写、去 `https://doi.org/`） |
| **再发布重复**（聚合平台转发另一来源） | GUDID ↔ openFDA `/device/udi` 是同一上游 | `canonical_key=di:…` 相同 → 判为重复，不计独立证据 |
| **采购多 stage 重复** | 同一 `ocid` 的 tender / award / contract 是不同对象 | 以 `ocid` 为 `canonical_key` 的采购级身份，stage 另存 |

**去重键的边界：** 没有权威标识符的记录 `canonical_key = null`，**不参与去重**。
这是刻意的保守选择——宁可少去重，也不因标题相似而误合并。

---

## 4. 时间语义缺陷（按来源）

| 缺陷等级 | 来源 | 具体问题 |
|---|---|---|
| **A · 完全无公开日** | `usaspending`、`un_comtrade`、`eurostat_comext` | 只有履约/统计期间。`source_public_at` 留空，`quality=unknown`，**禁止进入任何提前量统计** |
| **B · 只有事件日，无首次公开日** | `openfda_device_510k`、`openfda_device_pma` | 有 `decision_date`，FDA 不提供每条记录的首次公开时间戳。锚点用 `event_at` 合法，但"当时何时可知"不可回答 |
| **C · 有双时钟但需人工区分** | `openfda_device_recall`（initiated vs posted）、`uk_find_a_tender`（release.date vs dateSigned）、`eu_ctis`（publishDate vs decisionDateOverall） | 字段齐全，但选错字段会静默改变结论 |
| **D · 元数据时钟易被误当公开时钟** | `openalex`（`created_date`）、`crossref`（`deposited`） | 样本中 `created_date` 曾晚于 `publication_date` 数年。连接器把它单列为 `metadata_clock_fields` |
| **E · 精度不足** | `un_comtrade`（年）、`eurostat_comext`（月/年） | `quality=coarse`，按 `timeq.quality_allows_lead_time()` 自动排除出提前量结论 |
| **F · 快照时钟（可用于版本判断，但不是记录公开日）** | `openfda_bulk_download`（`export_date`） | 正确用途是"这份快照是什么时候导出的"，不是"某条记录何时公开" |

**验证方式：** 上述每一条都有对应的请求与响应切片，或对应来源的官方字段名。
`timeq.build_time()` 是唯一入口，`quality_allows_lead_time()` 是唯一准入判断。

---

## 5. 错误关联与误配（EXP-B 的证据）

| 风险 | 实测 | 处理 |
|---|---|---|
| **品牌词跨产品误配** | C3 中 `Infinity` 同时是 Draeger 监护系统与呼吸气囊套件的品牌词：9/11 匹配属于此类 | C3 把匹配分为 strong/weak 并分别报告；弱匹配不计入重分类 |
| **企业 token 搜索污染** | USAspending `recipient_search_text="GE HealthCare"` 返回 **CHANGE HEALTHCARE** 实体；首页 10 条仅 1 条确认 | 人口计数只作上界；确认关联必须过 `CompanyIndex` |
| **单 token 不足以做候选** | `CompanyIndex` 规定 alias <2 个 token 不参与候选匹配 | 避免 `PHILIPS` 命中 `PHILIPS 66` 一类 |
| **负向守卫降级** | `PHILIPS LIGHTING`、`GE AVIATION`、`DRAEGER SAFETY` 命中品牌词但非医疗器械主体 | 不丢弃，**降级为 candidate 并记录 `negative_guard`**，便于审计降级是否过度 |
| **候选层污染确认层** | 688 条证据中 candidate 仅 1 条 | schema 强制 candidate 置信度 <0.9，且不计入确认分母 |

---

## 6. 来源偏差（必须在结论旁注明）

| 偏差 | 说明 |
|---|---|
| **上报偏差** | MAUDE/recall 的计数反映上报激励、诉讼环境、装机量，**不是故障率**。Dräger 2,742 vs Medtronic 3,360,860 差 3 个数量级，不能解释为质量差 3 个数量级 |
| **监管辖区偏差** | FDA 覆盖最强、Health Canada 意外开放、EUDAMED 需注册、英国无公开产品注册库、中国被反自动化阻断。**"美国看是新的"不等于"世界上是新的"**（C3 已量化这一点） |
| **出版偏差** | 文献侧偏向英文、被索引的期刊；企业负面结果不发表 |
| **平台偏差** | Greenhouse/Lever 只覆盖使用该 ATS 的公司——五家目标企业**都不使用**，因此"招聘数据不可得"是该平台的覆盖性质，不是这些公司不招人 |
| **生存者偏差** | 锚点是"最终获批"的产品；失败项目不在样本内 |
| **索引偏差** | 本轮 688 条是小样本，不代表数据集规模或时间跨度 |

---

## 7. 过程缺陷与已修复问题（如实披露）

### 7.1 缺陷 1：SAMPLES.json 越界写（已修复）

- **现象**：采集阶段一次通配写入重写了 **58 个** sample 目录的 `SAMPLES.json`。
- **范围**：只重写了 manifest（元数据），**样本文件本体未改动**。
- **后果**：**156 条** 条目的 `sha256_full` 被置空；部分条目的 `request_url`/`probe_name` 元数据可能永久丢失。
- **修复方式**：`tools/repair_sample_manifests.py` 采用**重算 + 显式标注**而非还原：
  - 从磁盘重算 sha256，条目记 `sha256_source: recomputed_from_disk`；
  - 保留原声明值，冲突时记 `declared_sha256_full` 并置 `hash_verified: false`（**不掩盖真实损坏**）；
  - 从 `PROBE_RESULT.json`/`requests.jsonl` 能唯一匹配时回填 `request_url`。
- **修复后核验**：194 条目 / 已核验 38 / 重算 156 / **冲突 0** / 缺失 0。
  **冲突为 0 说明样本本体确实未被改动。**
- **教训**：采集脚本必须限定 `OWNED_SAMPLE_DIRS`，不得使用跨 owner 的通配。

### 7.2 缺陷 2：61MB 响应导致挂起（已规避）

- **现象**：openFDA `device/recall` 在 `limit=1000` 时解压后约 61MB，超过 8MB 安全上限，一次请求挂起。
- **处理**：改为**服务端 count 聚合**（43 次请求完成五家普查），并保持响应体上限。
- **教训**：官方 API 的"一条记录"可能非常大；必须按响应体而非记录数设限。

### 7.3 未修复缺陷（明确记录，不隐藏）

| 缺陷 | 原因 | 影响 | 建议 |
|---|---|---|---|
| `collection_run_id` 在连接器产出的证据里为空 | 连接器按协议必须无状态、幂等，不知道运行 id | 证据与运行只能按"来源 + `fetched_at`"关联，不能逐条精确回指 | 若需要逐条追溯，应在 harness 层重写该字段并重算内容哈希（本轮未做，以免破坏证据不可变性） |
| staging `raw_objects` 表 0 行 | 原始字节保存在 `samples/<source>/`，未重复写入 SQLite | 原始字节仍可按 `raw.content_hash` 校验，但 staging 内不自包含 | 若要把 staging 做成自包含快照，需把 raw 写入 blob 目录 |
| `greenhouse`/`lever` 未进入 staging | 需要 board token，而五家目标企业无公开板 | 平台已验证但无目标企业数据 | 采集控制板只会引入无关岗位，故刻意不采 |
| `patentsview` 记录仍存在于索引 | 索引冻结于本轮开始时，其后实测发现主机已 NXDOMAIN | 索引里有一条"死链"条目 | 下一轮把 `superseded_by: uspto_open_data_portal` 写入索引 |

---

## 8. 质量门与其执行结果

| 门 | 执行情况 |
|---|---|
| `schema.validate_evidence()` 写入前校验 | 688 条全部通过；无效记录 **0** 条写入（被拒绝的记录会计入 `invalid_rejected`） |
| 时间四时钟齐全 | 是（键必须存在，可为空串） |
| `source_public_at_quality` 枚举 | 是 |
| 置信度上限（candidate <0.9） | 是 |
| 确认级关联必须带 `evidence` | 是 |
| 请求预算与最小间隔 | 是（每源 ≤20 请求，`min_interval ≥0.6s`） |
| 失败留证 | 是（102 次失败请求全部在 `requests.jsonl`） |
| 离线测试 | **1248 通过 / 3 跳过**（含 174 条外部源测试） |

---

## 9. 若要进入生产，还缺什么

1. **产品级身份**（UDI-DI 与型号），否则 EXP-B 的瓶颈无法突破。
2. **逐条 `collection_run_id`** 与自包含 raw 存储。
3. **字段级 schema 校验**（本轮只校验信封，不校验 `normalized` 内部字段）。
4. **变更检测**：本轮用内容哈希做版本判定，但未评估上游"静默改字段"的情况。
5. **人工标注预算**：没有它，跨源关联永远只能报告"权威子集错误率"，不能报告总体准确率。
