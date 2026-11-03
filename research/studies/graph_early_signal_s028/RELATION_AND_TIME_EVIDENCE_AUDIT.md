# S-028 关系与时间证据审计

**RELATION_AND_TIME_EVIDENCE_AUDIT** · 研究：`graph_early_signal_s028`
**审计角色**：独立数据来源审计（Data-Provenance Auditor），不参与建模、不参与假设检验
**审计日期**：2026-11-04 · **分支**：`research/s028-temporal-graph-early-signal`
**机器可读结果**：`research/studies/graph_early_signal_s028/artifacts/entity_time_audit.json`
**复现脚本**：`research/studies/graph_early_signal_s028/code/audit_10…audit_19*.py`

> 本报告中的每一个数字都来自脚本输出，并写入 `entity_time_audit.json`。
> 报告不含手工录入的数值；`audit_19_verify_report.py` 会把本文的每个数字回查 JSON。

---

## 0. 审计范围与冻结输入校验

三个数据存储全部以只读 URI 打开（`sqlite3.connect(f"file:{path}?mode=ro", uri=True)`）。
冻结研究输入经逐字节校验，与任务书声明完全一致：

| 存储 | 路径 | 字节数 | 表数 |
|---|---|---|---|
| 冻结研究输入 | `worktrees/integration-v2/data/research.sqlite` | 289,443,840 | 26 |
| 产品库 | `medradar/data/medradar.sqlite` | 1,368,469,504 | 18 |
| 观察台账 | `medradar/data/observatory/observatory.sqlite` | 1,945,600 | 13 |

- `sha256 = dd241bfec138d7977d7eb8f4c1db25119d59b6fe7ff573060b24d14eeeb71e0d` → **校验通过**（`sha256_verified=true`）。
- 冻结输入的 9 张“实时状态”表（`live_alerts`、`signals`、`positions`、`paper_trades`、`paper_orders`、`llm_verdicts`、`live_equity`、`live_pending`、`live_skips`）全部 0 行：没有任何实盘/前瞻状态混入研究输入。

冻结输入的实际内容（`meta.table_row_counts`）：`events` 55,090（`openfda_device_510k_bulk` 31,219 + `openfda_device_pma_bulk` 23,871）、`temporal_edges` 5,580、`procurement_awards` 3,453、`financial_facts` 43,420、`market_bars` 95,725、`publication_counts` 616、`companies` 51、`tracks` 38、`company_identifiers` 34、`forecast_examples` 47,704、`horizon_forecasts` 25，而 `signals`、`prices`、`product_codes`、`meta`、`runs` 等均为 **0 行**。

> **重要事实**：冻结研究输入里根本没有试验、论文、召回、药品审批数据。它只有 510(k) 与 PMA 两类监管事件，加上三张外部补充表（采购、财报、论文年度计数）。这一点决定了第 6 节（Q-F）的一连串否定结论。

---

## 1. 两个时钟：`historical_proxy_asof` 与 `observed_asof`

本审计的两个核心术语，先定义再使用：

| 术语 | 定义 | 可支撑的结论 |
|---|---|---|
| **`historical_proxy_asof`** | 用事后回填、派生或合成的时点，把历史事件“放回”过去某一时刻。它假定“事件发生时我们就知道”，但这个假定本身没有被任何观察记录证明。 | 只可用于**历史模拟**（backtest / simulation），不得声称当时已知 |
| **`observed_asof`** | 记录公开之后，在很短时间内（本审计取 ≤1 个自然日）被系统真实抓取并落库的时点。台账里有真实的 `first_seen_at` 与抓取运行记录。 | 可用于**真正的前瞻性**主张（prospective claim） |

整个 S-028 的可信度取决于：研究用的是哪一个。答案是——**历史部分 100% 是 `historical_proxy_asof`；`observed_asof` 的样本量只有 6 条，且全部产生于 2026-11-03 这一天。**

### 1.1 结论速览

| 问题 | 结论 | 关键数字 |
|---|---|---|
| `research.events.first_seen_at` 是不是单一批量日？ | **是**，任务书的怀疑成立 | 55,090 / 55,090 行同为 `2026-11-01`，只有 1 个不同取值 |
| 有多少历史事件有真实的首次观察？ | **1 行**（且只是日历日粒度巧合） | `lag ≤ 1 天` 的仅 1 行（0.0018%），`lag > 365 天` 的 49,539 行（89.92%） |
| `available_at` 等于 `event_date` 吗？ | **不等于，且零方差** | 全部 55,090 行 `available_at = event_date + 14 天`，等于 `published_at` |
| 产品库呢？ | **相反方向的合成量** | 6 个来源 375,378 行，`available_at == event_date` 占 100.00% |
| 观察台账里有几条是真正的 prospective？ | **6 条 / 400 条** | `observation_origin` 全部标 `LIVE`，但 `lag > 7 天` 的有 365 条（91.25%） |
| 存在公司↔公司关系吗？ | **不存在** | `temporal_edges` 里 Company→Company 边 0 条；唯一近似物是无日期无证据的 `companies.aliases` 字符串清单 |
| 合格事件（正样本）有多少？ | **25,947 个** | 其中同时有公司+赛道的只有 2,885 个（11.12%），最终 303 个 company–track 对 |

---

## 2. Q-A：时点问题（point-in-time problem）

### 2.1 冻结输入：`first_seen_at` 是单一批量抓取日

| 来源 | 行数 | `first_seen_at` 不同取值数 | 取值分布 | 事件日期范围 | `published_at` 范围 |
|---|---|---|---|---|---|
| `openfda_device_510k_bulk` | 31,219 | 1 | `2026-11-01` × 31,219 | 2016-11-01 .. 2026-10-18 | 2016-11-15T00:00:00 .. 2026-11-01T00:00:00 |
| `openfda_device_pma_bulk` | 23,871 | 1 | `2026-11-01` × 23,871 | 2016-11-01 .. 2026-10-16 | 2016-11-15T00:00:00 .. 2026-10-30T00:00:00 |

**`first_seen_at` 的全部信息量等于 0**：它对 55,090 行给出同一个值。`as_of` 列同样是单值 `2026-11-01`（55,090 行），也就是“这批数据是哪天抓的”，而不是每个事件的当时可得性。
`timestamp_quality` 只有 1 个取值 `estimated`，覆盖 55,090 行——数据库自己承认这是**估计**时间。

### 2.2 量化：lag 分布（`first_seen_at` − `published_at`，按自然日）

| lag 区间 | 行数 |
|---|---|
| 0 天 | 1 |
| 2–7 天 | 101 |
| 8–30 天 | 356 |
| 31–365 天 | 5,093 |
| **> 365 天** | **49,539** |

- min = 0，median = **1,844 天**（约 5 年），max = **3,638 天**。
- 真正意义上的 point-in-time 首次观察（`lag ≤ 1 天`）：**1 行（0.0018%）**；`lag ≤ 7 天`：102 行（0.1852%）。
- 那 1 行 `lag = 0` 也只是“日历日相同”：`published_at` 为 `2026-11-01T00:00:00`，抓取发生在同日 22:46 左右，因为 `first_seen_at` 只有日期粒度（无时分秒），所以看起来是同日。

**结论**：冻结研究输入里历史事件的“首次观察时间”**100% 是 `historical_proxy_asof`**。任何形如“我们在事件发生时就知道”的表述，在这份数据上无法成立；只能写“我们事后按 X 规则重建了当时可知的信息集”。

### 2.3 对照：观察台账里的 `observation_origin`

观察台账是三个库里唯一有真正逐条观察记录的：

| 字段 | 状态 |
|---|---|
| `observation_origin` | 全部 400 条 = `LIVE`，`BACKFILL` 0 条 |
| `backfill_reason` | 全部 400 条为 NULL |
| `first_seen_at` | 4 个不同时间戳，**全部在 2026-11-03 当天** |
| `ingested_at` | 只有 1 个日期（2026-11-03） |
| 台账创建时间 `meta.created_at` | `2026-11-03T14:39:53+00:00` |
| `observation_status` / `current_change_state` | `ACTIVE` × 400 / `NEW` × 400 |
| `version_count` | 全部为 1 |
| `observation_phase.method` | 400 条全部为 `reconstructed_from_run_history`（399 条 `INITIAL_DISCOVERY` + 1 条 `INCREMENTAL_DISCOVERY`） |

`first_seen_at` 的 4 个取值分布：`2026-11-03T14:39:53Z` 6 条、`2026-11-03T14:44:26Z` 156 条、`2026-11-03T14:44:29Z` 237 条、`2026-11-03T14:49:51Z` 1 条。

**这就是问题所在**：`observation_origin = LIVE` 描述的是**采集方式**（这条记录来自线上抓取，而不是回填脚本），而不是**前瞻性**。台账存在时间只有 1 天，400 条观察全部在首次运行中被“一次性发现”，其中 365 条的公开时间比首次看到的时间早了 7 天以上。

### 2.4 前瞻性量化（`lag = first_seen_at − published_at`）

| 判定 | 条数 | 占比 |
|---|---|---|
| `lag ≤ 0 天` | 5 | 1.25% |
| **`lag ≤ 1 天`（真正的 `observed_asof`）** | **6** | **1.5%** |
| `lag ≤ 7 天` | 35 | 8.75% |
| `lag > 7 天`（事实上等同回填） | 365 | 91.25% |

min = 0，median = **65 天**，max = **7,613 天**。6 条真正的 prospective 记录是：1 条 `ctgov` trial（lag 1 天，`published_at` 2026-11-02）、4 条 `europepmc` publication（lag 0 天，`published_at` 2026-11-03）、1 条 `sec_edgar` `sec_6k`（lag 0 天，公开 13:11:19Z、抓取 14:39:53Z）。

### 2.5 `observation_origin` × `source` × `record_type`

| observation_origin | source | record_type | 条数 |
|---|---|---|---|
| LIVE | europepmc | publication | 237 |
| LIVE | ctgov | trial | 157 |
| LIVE | sec_edgar | sec_8k | 4 |
| LIVE | sec_edgar | sec_10q | 1 |
| LIVE | sec_edgar | sec_6k | 1 |

按来源的 lag 分桶（同日 / 1 天 / 2–7 天 / 8–30 天 / 31–365 天 / >365 天 / 合计）：

| source | ≤0d | 1d | 2–7d | 8–30d | 31–365d | >365d | 合计 |
|---|---|---|---|---|---|---|---|
| ctgov | 0 | 1 | 2 | 9 | 50 | 95 | 157 |
| europepmc | 4 | 0 | 25 | 58 | 150 | 0 | 237 |
| sec_edgar | 1 | 0 | 2 | 1 | 2 | 0 | 6 |

`ctgov` 的 157 条里有 95 条 lag 超过 365 天——因为 `published_at` 取 `study_first_post_date`，而 `event_at` 最早到 1983-01、`published_at` 最早到 2005-12-30。这类记录在 2026-11-03 被“首次发现”，只能算回填。

台账自身的完整性还有一处小瑕疵，如实记录：`observation_mapping` 有 401 行、400 个不同 `observation_id`，存在 1 个重复 `observation_id`（`25f638d0b688a3698629ce02d7e1a3b9ca26772f`）；`sync_run` 34 次全部 `OK`，`source_failure` 6 条（均为结构指纹变化告警，非数据缺失）。

---

## 3. Q-B：`available_at` 到底是什么

### 3.1 冻结输入：`available_at` = `event_date` + 14 天（零方差）

| 检验 | 结果 |
|---|---|
| `available_at − event_date` 的不同取值 | **只有 1 个：14 天** |
| `available_at == event_date` 的行数 | **0**（0.0%） |
| `available_at == published_at` 的行数 | **55,090 / 55,090** |
| `published_at − event_date` | min = 14、median = 14、max = 14 |
| 按来源 | `510k` 31,219 行全部落在 8–30 天桶；`pma` 23,871 行同样 |

也就是说：`available_at` **既不是** `event_date`（差 14 天整），**也不是**任何观测到的公开延迟——它的方差是 0。`published_at` 同样是被构造出来的，14 天是一个写死的假设。

### 3.2 这个 14 天假设能从原始 payload 复核吗？不能

- `510k` payload 的日期字段只有 `decision_date` 与 `date_received`；`pma` 多一个 `fed_reg_notice_date`。
- `events.event_date` 与 `payload.decision_date` 完全一致：55,090 行（100.00%）。
- `date_received` 早于决定日的：55,079 行（99.98%）。
- `fed_reg_notice_date` 只存在于 461 行 PMA 中；与 `published_at` 相等的仅 15 行，**早于** `published_at` 的有 317 行。
- 没有任何 openFDA device 字段承载“首次对公众可见”的时间戳。

**结论**：`available_at`/`published_at` 是构建脚本的**假设**（decision_date + 14 天），而且构建时**忽略了唯一真实的公开日期字段** `fed_reg_notice_date`（461 行）。用 `available_at` 做 as-of 过滤，等于把假设当证据。

### 3.3 产品库：`available_at == event_date`（100.00%）

| 来源 | 行数 | `available_at == event_date` 占比 | `first_seen_at` 取值 |
|---|---|---|---|
| `openfda_device_510k` | 176,466 | 100.00% | `2026-10-30` × 176,466 |
| `openfda_device_recall` | 59,646 | 100.00% | `2026-10-30` × 59,646 |
| `openfda_device_pma` | 57,372 | 100.00% | `2026-10-30` × 57,372 |
| `ctgov` | 55,592 | 100.00% | `2026-10-30` × 55,592 |
| `sec_edgar_corpus` | 20,976 | 100.00% | `2026-10-31` × 20,976 |
| `openfda_drug_drugsfda` | 5,326 | 100.00% | `2026-10-30` × 5,326 |

两个库对 `available_at` 的语义**互相矛盾且都是合成量**：冻结输入取 `event_date + 14 天`，产品库取 `event_date + 0 天`。产品库的 6 个来源同样是单一批量 `first_seen_at`。

### 3.4 唯一站得住的历史知识时钟

- 监管事件（510k/PMA）的 `event_date` = FDA 决定日，是**来源自带、可复核**的日期，应作为知识时钟的基准；
- `available_at` 只能作为“保守外扩界”（假设公开晚 14 天），必须显式声明为假设；
- 任何“as-of T”的图，其边集必须只由 `event_date ≤ T` 的事件构成，并在论文中写明这是 `historical_proxy_asof`。

---

## 4. Q-C：到底存在哪些关系，缺哪些

### 4.1 `temporal_edges` 全量清单（5,580 条，4 种关系）

| relation | subject_type | object_type | 边数 | 主体数 | 客体数 | `valid_time` 空 | `available_at` |
|---|---|---|---|---|---|---|---|
| `COMPANY_WINS_CONTRACT` | Company | ProcurementContract | 3,372 | 22 | 3,372 | 0 | 全部 = `2026-11-01T22:48:28Z` |
| `COMPANY_DEVELOPS_PRODUCT` | Company | Product | 1,087 | 51 | 516 | 0 | `2016-11-15T00:00:00` .. `2026-10-16T00:00:00` |
| `PRODUCT_BELONGS_TO_TECHNOLOGY` | Product | Technology | 1,087 | 516 | 38 | 0 | `2016-11-15T00:00:00` .. `2026-10-16T00:00:00` |
| `COMPANY_FILES_FINANCIAL_FACT` | Company | FinancialFiling | 34 | 34 | 34 | **34** | 全部 = `2026-11-01T22:48:06Z` |

`subject_type` 只有 2 种（`Company`、`Product`），`object_type` 只有 4 种（`FinancialFiling`、`ProcurementContract`、`Product`、`Technology`）。

### 4.2 明确不存在的证据（任务书要求逐条声明）

| 不在的东西 | 实测 | 说明 |
|---|---|---|
| 公司↔公司（任何形式） | **0 条边** | 没有母子公司、竞争对手、合资、授权、供应链边表 |
| 自反边（subject_type = object_type） | 0 条 | — |
| 任意 `object_id` 命中 `companies.key` | 0 条 | 客体里不存在第二家公司 |
| 公司→技术赛道直连边 | 0 条 | 只能经 `Product` 中转（1,087 × 1,087） |
| 公司→试验 / 试验申办方 | 0 条 | 冻结输入没有试验数据 |
| 公司→论文 / 作者 / 机构 | 0 条 | 冻结输入只有年度计数 |
| 公司→事件 / 监管事件节点 | 0 条 | 事件没有被物化为图节点 |
| 公司→采购合同的买方↔卖方映射 | 0 条 | 3,453 行的买方只有 7 个联邦机构，不是公司 |

**必须写进论文的否定结论**：这份数据**无法构建任何公司–公司关系**。唯一近似物是 `companies.aliases`（178 个别名字符串，51 家公司全部有，人均 3.49 个，最多 18 个）——它是母公司名下的子公司名字列表，隐含所有权，但**没有方向字段、没有生效日期、没有证据编号、没有置信度**。

### 4.3 物化边覆盖率远低于事件规模

| 指标 | 数值 |
|---|---|
| `events` 总行数 | 55,090 |
| 有 `company_key` 的事件 | 21,670（39.34%） |
| 同时有 `company_key` 与 `track_id` 的事件 | 18,031（32.73%） |
| `COMPANY_DEVELOPS_PRODUCT` 边数 | 1,087 |
| 边 / 有公司事件 | **5.0162%** |
| 边涉及的不同 `product_code` | 516 |
| 事件里的 (company, product_code) 组合 | 1,698 → 物化 1,087，**611 组未物化** |
| 由事件得出的 (company, track) 组合 | 334 |

边的时间语义经复核：`COMPANY_DEVELOPS_PRODUCT.valid_time` 等于该 (company, product_code) 组内最早事件的 `event_date`（1,087 条中 1,016 条严格吻合），`available_at` 继承该最早事件的合成 `published_at`（同样 1,016 条），与 `evidence_id` 指向事件的 `available_at` 直接相等的有 533 条。**即：边的时间也是从事件派生出来的合成量，不是独立观测。**

### 4.4 采购与财报：证据表本身的时间质量

`procurement_awards`（3,453 行）：

| 指标 | 数值 |
|---|---|
| `award_date` 为空 | **3,453 / 3,453（100%）** |
| `announcement_date` 为空 | **3,453 / 3,453（100%）** |
| `pit_usable = 1` 的行 | **0** |
| `data_quality` | 全部 `current_snapshot_obligation_not_revenue_first_publication_unknown` |
| `available_at` 不同取值 | **1** 个（`2026-11-01T22:48:28Z`） |
| `match_confidence` 均值 | 0.935012 |
| 有 `company_key` 的工厂 | 22 行不同公司、81 行空 |
| 买方数 | 7 个联邦机构 |

边上的 `valid_time` 实际取自 `period_start`（履约期起点），不是授予日、更不是首次公开日；payload 里只有 `award_id`、`contract_award_type`、`generated_internal_id`、`internal_id`、`last_modified_date`。

`financial_facts`（43,420 行，32 家公司，`valid_time` 2006-09-30 .. 2026-09-30，`available_at` 2009-04-23 .. 2026-10-30，949 个不同 `available_at`，空值 0）——事实行的时间质量尚可，但对应的 34 条 `COMPANY_FILES_FINANCIAL_FACT` 边**全部没有 `valid_time`**。

---

## 5. 十字段关系台账（按候选关系类型逐项）

以下每类关系给出任务书要求的 10 个字段。数值全部对应 `entity_time_audit.json → relation_types[]`。

### 5.1 R1 公司→技术赛道（监管申报事件直连）

| # | 字段 | 内容 |
|---|---|---|
| 1 | 关系定义 | 事件 e 的 `company_key=c` 且 `track_id=t` ⇒ 在 `event_date` 建立 c→t 关系（隐式边，未物化） |
| 2 | 原始证据来源 | 表 `events`；`source ∈ {openfda_device_510k_bulk, openfda_device_pma_bulk}`；字段 `payload.applicant`、`payload.product_code`、派生 `track_id` |
| 3 | 事件时间 | `event_date`，与 `payload.decision_date` 100.00% 一致；2016-11-01 .. 2026-10-18；`timestamp_quality=estimated` |
| 4 | 公开时间 | `published_at = event_date + 14 天`（100%），非真实来源字段 |
| 5 | 首次观察 | `first_seen_at = 2026-11-01`（55,090 行单值）→ 无信息量 |
| 6 | 实体归属方法 | 赛道：`config/product_code_tracks.json`（1,958 条，确定性）；公司：`companies.aliases` 模糊子串/前缀匹配 |
| 7 | 可信度/待审 | `events` 表**没有** `match_confidence`、**没有** `matched_alias` 列 → 逐行映射置信度不可审计 |
| 8 | 是否含未来信息 | 事件本身否；风险在赛道路径是 2026 年分类学、公司名册是 2026 年名册 |
| 9 | 历史覆盖 | 55,090 事件 / 21,670 有公司 / 18,031 有公司+赛道 / 334 个 (company,track) 对；逐年缺失率见 5 节末表 |
| 10 | 数据缺失 | `company_key` 空：510k 25,932（83.06%）、pma 7,488（31.37%）；`track_id` 空：510k 12,765（40.89%）、pma 4,543（19.03%）；`product_code` 空：13 与 110 |

### 5.2 R2 公司→产品→技术（物化边表）

| # | 字段 | 内容 |
|---|---|---|
| 1 | 关系定义 | 每个 (company, product_code) 组取最早事件建 `COMPANY_DEVELOPS_PRODUCT`；再经 code→track 建 `PRODUCT_BELONGS_TO_TECHNOLOGY` |
| 2 | 原始证据来源 | 表 `temporal_edges`；`evidence_source ∈ {openfda_regulatory_event, medradar_product_code_mapping}`；1,087 条 `evidence_id` 全部可回连 `events` |
| 3 | 事件时间 | `valid_time`（0 空值），= 组内最早 `event_date`（1,016 条吻合）；范围 2016-11-15T00:00:00 .. 2026-10-16T00:00:00 |
| 4 | 公开时间 | 边 `available_at` 继承最早事件的 `event_date + 14 天` |
| 5 | 首次观察 | 无 `first_seen_at` 列；`available_at` 是派生量 |
| 6 | 实体归属方法 | 主体=company_key（模糊）；客体=product_code 原样；技术=config 映射（确定性） |
| 7 | 可信度/待审 | `confidence` 全部 1.0；`assertion_status` 全部 `observed` |
| 8 | 是否含未来信息 | 否；但把派生 `available_at` 当“可知时点”即把假设当事实 |
| 9 | 历史覆盖 | 1,087 + 1,087 边；51 公司 / 516 产品 / 38 赛道；逐年 2016:149、2017:270、2018:135、2019:102、2020:85、2021:60、2022:60、2023:61、2024:57、2025:55、2026:53 |
| 10 | 数据缺失 | `valid_time` 空 0、`available_at` 空 0；事件中 1,698 个 (company, code) 组只物化 1,087（缺 611） |

### 5.3 R3 公司→采购合同

| # | 字段 | 内容 |
|---|---|---|
| 1 | 关系定义 | USAspending 合同/订单受方经别名匹配到 `company_key` ⇒ `COMPANY_WINS_CONTRACT`；`valid_time` 取履约期起点 `period_start` |
| 2 | 原始证据来源 | 表 `procurement_awards`；`original_source = usaspending_api_v2_spending_by_award`；3,453 行 |
| 3 | 事件时间 | `valid_time == period_start`；`award_date` 空 3,453、`announcement_date` 空 3,453（**授予日与公开日均缺失**） |
| 4 | 公开时间 | 边 `available_at` 单值 `2026-11-01T22:48:28Z`（抓取时刻，非公开时刻） |
| 5 | 首次观察 | 无该列；批量时间戳即抓取日 |
| 6 | 实体归属方法 | supplier 字符串→别名匹配，逐行有 `match_confidence`（均值 0.935012）与 `matched_alias`；买方只有 7 个联邦机构 |
| 7 | 可信度/待审 | `pit_usable = 1` 的行 **0**；`data_quality` 全部 `current_snapshot_obligation_not_revenue_first_publication_unknown` |
| 8 | 是否含未来信息 | **是**：只剩当前快照，无首次公开日，可用到事后金额与存续状态 |
| 9 | 历史覆盖 | 3,372 边 / 22 家公司；逐年 2007:1、2008:1、2009:1、2010:2、2011:7、2012:14、2013:32、2014:77、2015:69、2016:455、2017:514、2018:378、2019:218、2020:267、2021:237、2022:260、2023:302、2024:203、2025:175、2026:159 |
| 10 | 数据缺失 | `company_key` 空 81；`award_date` 空 100%、`announcement_date` 空 100% |

### 5.4 R4 公司→财报事实

| # | 字段 | 内容 |
|---|---|---|
| 1 | 关系定义 | SEC XBRL companyfacts 每条事实一条 `COMPANY_FILES_FINANCIAL_FACT` 边（company→CIK） |
| 2 | 原始证据来源 | `financial_facts`（43,420 行，`source=sec_xbrl_companyfacts`）+ `company_identifiers`（34 行，`scheme=SEC_CIK` 为唯一 scheme） |
| 3 | 事件时间 | 事实行 `valid_time` 2006-09-30 .. 2026-09-30（空 0）；**边上 `valid_time` 空 34/34** |
| 4 | 公开时间 | 事实行 `available_at` 2009-04-23 .. 2026-10-30（949 个不同值）；边上 `available_at` 单值 `2026-11-01T22:48:06Z` |
| 5 | 首次观察 | 无该列 |
| 6 | 实体归属方法 | CIK 精确匹配（确定性），覆盖 32 家公司 |
| 7 | 可信度/待审 | `confidence` 1.0；`data_quality = companyfacts_no_segment_dimension` |
| 8 | 是否含未来信息 | 事实行层面否；无时间的边上无法判定 |
| 9 | 历史覆盖 | 43,420 行 / 32 家公司（51 家中 19 家无事实） |
| 10 | 数据缺失 | `valid_time` 空 0、`available_at` 空 0、`payload` 空 0；边 `valid_time` 空 34 |

### 5.5 R5 公司→临床试验申办方

| # | 字段 | 内容 |
|---|---|---|
| 1 | 关系定义 | ctgov 试验 `lead_sponsor` 经别名匹配到 `company_key`；事件时间取首次公示日 |
| 2 | 原始证据来源 | **产品库** `events`（`source=ctgov`，55,592 行）——冻结研究输入中不存在 |
| 3 | 事件时间 | `event_date == payload.first_posted`（55,592 / 55,592）；范围 1999-10-19 .. 2026-10-30；`start_date` 在 payload 中有 55,143 行 |
| 4 | 公开时间 | 产品库中 `published_at` 与 `available_at` 都等于 `event_date`（100.00%） |
| 5 | 首次观察 | `first_seen_at = 2026-10-30`（55,592 行单值） |
| 6 | 实体归属方法 | 别名匹配，逐行保留 `match_confidence` 与 `matched_alias` |
| 7 | 可信度/待审 | ≥0.90 被接受 38,715 行；0<mc<0.90 仅候选 8,311 行；mc=0 未匹配 8,566 行 |
| 8 | 是否含未来信息 | 首公示日之后的状态/结果/完成日期若被使用即含未来信息（payload 含 `overall_status`、`completion_date`） |
| 9 | 历史覆盖 | 4,527 个不同 `lead_sponsor`；映射到冻结 51 家名册的 4,367 条，覆盖 46 家公司（abbott 840、medtronic 624、alcon 580、boston_scientific 379、cooper_companies 175、philips 130、ge_healthcare 127、zimmer_biomet 124 等） |
| 10 | 数据缺失 | `company_key` 空 16,877（30.36%）；在冻结输入中该关系 0 条 |

### 5.6 R6 公司↔公司（任何形式）

| # | 字段 | 内容 |
|---|---|---|
| 1 | 关系定义 | **不存在**。`temporal_edges` 没有任何 Company→Company 边，也没有子公司、竞争对手、合作、授权、供应链边表 |
| 2 | 原始证据来源 | 无。唯一近似物是 `companies.aliases` 字符串数组 |
| 3 | 事件时间 | 无 |
| 4 | 公开时间 | 无 |
| 5 | 首次观察 | 无 |
| 6 | 实体归属方法 | 别名清单隐含“母公司包含子公司名”，但无方向、无日期、无证据 id、无置信度 |
| 7 | 可信度/待审 | 无任何置信度字段 |
| 8 | 是否含未来信息 | **是**：名单是 2026 年的并购结果，用它构造 t 时刻的“母公司拥有该技术”即使用当时不可知的信息 |
| 9 | 历史覆盖 | Company→Company 边 0；自反边 0；`object_id` 命中公司主键 0 |
| 10 | 数据缺失 | 整类关系 100% 缺失 |

### 5.7 R7 公司→论文产出（年度聚合）

| # | 字段 | 内容 |
|---|---|---|
| 1 | 关系定义 | OpenAlex 按公司名检索后按 (company, year) 计 works 数——不是论文级关系 |
| 2 | 原始证据来源 | 表 `publication_counts`，616 行，`source=openalex_group_by_publication_year`，列 = `company_key, year, works, source, retrieved_at` |
| 3 | 事件时间 | 仅 `year`，2014 .. 2026 |
| 4 | 公开时间 | 仅 `retrieved_at`（抓取时间） |
| 5 | 首次观察 | 无 |
| 6 | 实体归属方法 | 公司名检索，检索式未落库，无 paper id 可回溯 |
| 7 | 可信度/待审 | 无 |
| 8 | 是否含未来信息 | **是**：年度计数是事后回填的汇总值，无法在年内任意时点还原“当时已知篇数” |
| 9 | 历史覆盖 | 616 行 / 51 家公司 / 2014–2026 |
| 10 | 数据缺失 | 论文级记录 0、作者记录 0、机构记录 0 |

### 5.8 R8 公司→单篇论文（观察台账）

| # | 字段 | 内容 |
|---|---|---|
| 1 | 关系定义 | Europe PMC 单位署名检索（`AFF:"公司名"`）命中后写入台账，`entity_method = europepmc_affiliation_query` |
| 2 | 原始证据来源 | `observatory.observation` + `observation_version.payload`，`source = europepmc`，237 条 |
| 3 | 事件时间 | `event_at`（precision=date），2026-08-05 .. 2026-11-02 |
| 4 | 公开时间 | `published_at = firstIndexDate`，2025-12-18 .. 2026-11-03 |
| 5 | 首次观察 | 全部在 2026-11-03 单日（4 个时间戳） |
| 6 | 实体归属方法 | 单位署名检索；`entity_status = PENDING_REVIEW` 238 行（含 1 条重复映射） |
| 7 | 可信度/待审 | 待审 238、已接受 102、未映射 61（合计 401 行） |
| 8 | 是否含未来信息 | **是**：237 条中 208 条 lag 超过 7 天 |
| 9 | 历史覆盖 | 237 条观察 / 窗口 2025-12-18 .. 2026-11-03 |
| 10 | 数据缺失 | payload **无任何单位/机构字段**；只有 `author_string` 自由文本 |

### 5.9 逐年缺失率（R1/R2 的可用样本）

| 年份 | 事件数 | `track_id` 空 | 公司空 | 公司或赛道缺失 |
|---|---|---|---|---|
| 2016 | 956 | 300 | 519 | 590（61.72%） |
| 2017 | 5,917 | 1,820 | 3,311 | 3,756（63.48%） |
| 2018 | 5,852 | 1,787 | 3,303 | 3,763（64.30%） |
| 2019 | 5,556 | 1,778 | 3,207 | 3,666（65.98%） |
| 2020 | 5,426 | 1,647 | 3,105 | 3,475（64.04%） |
| 2021 | 5,227 | 1,797 | 3,213 | 3,528（67.50%） |
| 2022 | 5,301 | 1,826 | 3,378 | 3,664（69.12%） |
| 2023 | 5,531 | 1,777 | 3,562 | 3,929（71.04%） |
| 2024 | 5,359 | 1,629 | 3,397 | 3,712（69.27%） |
| 2025 | 5,447 | 1,625 | 3,517 | 3,830（70.31%） |
| 2026 | 4,518 | 1,322 | 2,908 | 3,146（69.63%） |

注意趋势：可用样本比例**随时间恶化**（61.72% → 71.04%），因为名册固定为 51 家而 FDA 申报主体逐年扩散。这会与“首次进入”目标直接冲突（见第 8 节）。

---

## 6. Q-D：公司映射治理与实体泄漏

### 6.1 映射到底怎么做的（可复核性）

在 `events` 里，把每条 `applicant_raw` 与所属公司的别名做归一化子串匹配，可以重建 512 个 (applicant, company) 组合的归属：

| 匹配情形 | 组合数 |
|---|---|
| 归一化后以别名开头（前缀匹配） | 431 |
| 别名只作为子串命中（如 `Davol Inc., Subsidiary of C. R. Bard`） | 73 |
| **完全不含该公司的任何别名** | **8** |

那 8 个组合（例如申请人写成 `Bd`、`Bd Diagnostic Systems`，被归到 `bd`）证明：**冻结构建用了一条数据库里没有记录额外的规则**。也就是说，公司归属**不可由已交付的工件完全复现**。赛道侧同样有不可复现的部分（见「赛道映射方法与漂移」小节）。这是治理问题，而不是数值问题。

`events` 表没有 `match_confidence` 也没有 `matched_alias`（对照：产品库的 ctgov payload 两者都有），所以 25,932 个空值和 21,670 个非空值**共享同一份不可审计的映射**。

### 6.2 别名规模

- 178 个别名字符串，51 家公司全部有别名列表，人均 3.49 个、最多 18 个（`johnson_johnson_medtech`）。
- 承载事件的别名 144 个，**34 个别名从未命中任何事件**。
- 事件量最大的别名（同一公司名下）：`MEDTRONIC` 4,251（2016-11-02 .. 2026-10-16）、`BOSTON SCIENTIFIC` 2,885（2016-11-01 .. 2026-10-15）、`ABBOTT MEDICAL` 1,831、`MEDTRONIC NEUROMODULATION` 762、`EDWARDS LIFESCIENCES` 687、`BIOTRONIK` 660、`GORE ASSOCIATES` 514、`MEDTRONIC VASCULAR` 466、`MEDTRONIC MINIMED` 394、`SIEMENS HEALTHCARE` 336、`STRYKER` 309、`JOHNSON & JOHNSON` 303。

### 6.3 被并购子公司的历史事件归属（含外部收购日期）

**外部来源声明**：下表的收购完成日期来自本审计之外公开检索，仅作对照，精度为“月”时以 `YYYY-MM` 比较（误差不超过 31 天）；标 `unverified` 的条目本轮**未取到可引用来源**，不参与数值计算。

| 母公司 | 被并购别名 | 收购完成（外部） | 精度 | 别名事件数 | 其中早于收购完成 | 涉及早期产品码 | 别名最早事件日 | 来源 |
|---|---|---|---|---|---|---|---|---|
| medtronic | COVIDIEN | 2015-01 | month | 102 | 0 | 0 | 2016-11-14 | [SEC EX-99.1](https://www.sec.gov/Archives/edgar/data/1613103/000119312515020681/d859999dex991.htm) |
| bd | C R BARD | 2017-12 | month | 107 | **19** | 16 | 2016-11-04 | [BD 8-K EX-99.1](https://investors.bd.com/sec-filings/all-sec-filings/content/0001193125-17-383523/d517273dex991.htm) |
| bd | BARD ACCESS SYSTEMS | 2017-12 | month | 15 | 0 | 0 | 2019-11-01 | 同上 |
| bd | CAREFUSION | 2015-03 | month | 9 | 0 | 0 | 2017-01-18 | [BD 新闻稿](https://news.bd.com/2015-03-17-Becton-Dickinson-Completes-Acquisition-Of-CareFusion) |
| abbott | ST JUDE MEDICAL | 2017-01 | month | 126 | **6** | 4 | 2016-11-22 | [Abbott 新闻稿](https://abbott.mediaroom.com/2017-01-04-Abbott-Completes-the-Acquisition-of-St-Jude-Medical) |
| stryker | WRIGHT MEDICAL | 2020-11 | month | 9 | **1** | 1 | 2017-03-06 | [Stryker 新闻稿](https://www.nasdaq.com/press-release/stryker-completes-acquisition-of-wright-medical-2020-11-11) |
| stryker | MAKO SURGICAL | 2013-12 | month | 16 | 0 | 0 | 2017-04-18 | [Stryker 新闻稿](https://investors.stryker.com/press-releases/news-details/2013/Stryker-Completes-Acquisition-of-MAKO-Surgical-Corp/default.aspx) |
| siemens_healthineers | VARIAN MEDICAL SYSTEMS | 2021-04 | month | 92 | **36** | 5 | 2016-11-17 | [Siemens Healthineers 新闻稿](https://www.siemens-healthineers.com/press/releases/varian-closing) |
| johnson_johnson_medtech | SHOCKWAVE MEDICAL | 2024-05 | month | 37 | **22** | 2 | 2016-12-22 | [J&J 新闻稿](https://www.investor.jnj.com/investor-news/news-details/2024/Johnson--Johnson-Completes-Acquisition-of-Shockwave-Medical/) |
| canon_medical | TOSHIBA MEDICAL | 2016-12 | month | 3 | 0 | 0 | 2017-06-16 | [Canon 新闻稿](https://global.canon/en/news/2016/20161219.html) |
| globus_medical | NUVASIVE | unverified | unverified | 29 | n/a | n/a | 2017-03-07 | 未取证 |
| icu_medical | SMITHS MEDICAL | 2023-01 | unverified | 18 | n/a | n/a | 2017-05-24 | 未取证 |
| zimmer_biomet | BIOMET | 2015-06 | unverified | 120 | n/a | n/a | 2016-11-03 | 未取证 |
| bbraun | AESCULAP | unverified | unverified | 39 | n/a | n/a | 2016-12-14 | 未取证 |

**合计 84 条早于收购完成日的历史事件被记在母公司名下**（C R BARD 19、VARIAN 36、SHOCKWAVE 22、ST JUDE 6、WRIGHT 1）。

### 6.4 这是不是 look-ahead？要区分两种泄漏

**(a) 日期级泄漏（可量化，规模不大）**：84 条事件。例如 Siemens Healthineers 名下的 VARIAN 事件从 2016-11-17 就存在，而并购 2021-04 才完成；在 2018 年做 as-of 建模时，图里就出现“西门子已进入该赛道”，而当时公众只知道 Varian 是独立公司。同理 J&J 名下的 SHOCKWAVE 有 22 条早于 2024-05。这一类泄漏**方向明确、规模有限**，而且因为冻结窗口起点是 2016-11-01，COVIDIEN（2015）与 CAREFUSION（2015）的窗口内事件全部在收购之后，泄漏为 0。

**(b) 结构性泄漏（更严重，无法用日期修正）**：`companies.aliases` 是**无日期的静态清单**。因此无论把 as-of 时点设在哪一年，映射都只能给出“2026 年的实体边界”。后果是：
- 无法表达“2018 年 Bard 是独立公司”，任何 as-of 图都把 Bard 归给 BD；
- `bd` 的 297 条事件里有 131 条（**44.11%**）来自被并购别名，`siemens_healthineers` 719 条里 92 条（**12.80%**）、`stryker` 460 条里 25 条（**5.43%**）、`abbott` 2,784 条里 126 条（**4.53%**）、`johnson_johnson_medtech` 1,326 条里 37 条（**2.79%**）、`medtronic` 6,282 条里 102 条（**1.62%**）、`canon_medical` 106 条里 3 条（**2.83%**）——对这些公司，“首次进入某赛道”的年份完全由并购时间表决定，而不是由技术进入决定。

**(c) 反向证据：有 77 条事件（0.14%）的申请人字符串自己写明了隶属关系**（`SUBSIDIARY` 35、`PART OF` 26、`A DIVISION OF` 8、`(AKA` 7、`WHOLLY OWNED` 1）。这 77 条归到母公司在**原始证据里是可辩护的**；其余绝大多数归并只有别名清单支撑。

**审计意见**：论文若使用母公司口径，必须（i）声明实体边界是 2026 年快照、（ii）把这 84 条日期级泄漏单独做稳健性检验、（iii）对 `bd`、`siemens_healthineers` 这两个别名占比超过 10% 的公司单独报告结果。若无法做到，应改用“申报主体口径”而不是“母公司口径”。

### 6.5 赛道映射方法与漂移（Q-E 的映射部分）

| 映射工件 | 内容 |
|---|---|
| `config/product_code_tracks.json` | 1,958 条 `product_code → track_id` 的确定性字典，无日期、无置信度 |
| `config/tracks_device.json` | 50 个赛道定义 + 关键词表，但 `product_codes` 数组为**空**（0 条） |
| `research.sqlite.product_codes` | **0 行**（冻结输入没有装载 code→track 表） |

事件级分类：

| 情形 | 事件数 | 占比 | 不同产品码 |
|---|---|---|---|
| `track_id` 为空 | 17,308 | 31.42% | 1,241 |
| 有 `track_id` 且与 config 字典一致 | 35,693 | 64.79% | 928 |
| 有 `track_id` 但产品码不在 config 字典里 | 2,089 | 3.79% | 283 |

那 2,089 条（283 个码）中，**1,764 条（84.44%）**的 `device_name` 文本确实包含所赋赛道的关键词 → 说明它们来自**关键词回退**，而这条回退规则的版本与阈值没有落库。剩下 325 条连关键词都不命中，规则完全不可复现。

产品码总量：事件里出现 2,202 个不同产品码，其中只有 928 个在 2026 年字典里（**57.86%** 的产品码不在字典中）。赛道路径是 2026-11-01T22:46:09Z 的快照，38 个赛道全部被使用、0 个闲置。

---

## 7. Q-E：赛道覆盖范围与漂移（churn）

| 指标 | 数值 |
|---|---|
| 事件中的不同产品码 | 2,202 |
| 2020 年后首次出现的码 | 720 个，承载 2,468 事件（4.48%） |
| **2022 年后首次出现的码** | **487 个，承载 1,348 事件（2.45%）** |
| 2024 年后首次出现的码 | 275 个，承载 616 事件（1.12%） |
| 2020 年前就消失的码 | 260 个，承载 427 事件 |
| 赛道数 | 38（表内 38，全部被使用，0 未用） |

晚出现的码在赛道层面并非均匀分布，例如 `QZI`（2023-12-13 首现，105 条事件，`ep_pfa`）、`NPW`（2024-02-01，31 条，`structural_heart`）、`QYI`（2023-11-07，29 条，`ep_pfa`）、`QPT`（2022-03-01，27 条，`ortho_joint`）。

**含义**：新赛道（尤其 `ep_pfa`、`structural_heart` 这类 PFA/结构性心脏）在样本早期几乎空白，其“首次进入”事件在时间上高度集中——这与“图能否提前给出信号”是同一枚硬币的两面，但也是**分类学漂移**的直接证据：用 2026 年的赛道定义去解释 2017 年的申报，赛道本身在 2017 年可能还不作为一个类别存在。这一点不泄漏事件值，但必须声明。

---

## 8. Q-F：试验 / 论文 / 研究机构覆盖

### 8.1 冻结输入里有什么

`meta.table_row_counts` 显示冻结输入只有 510(k) + PMA 两类事件；`publication_counts` 是唯一的“研究产出”表（616 行 / 51 家公司 / 2014–2026 / `openalex_group_by_publication_year`），列只有 `company_key, year, works, source, retrieved_at`。

### 8.2 试验：只在产品库里有

| 指标 | 数值 |
|---|---|
| `ctgov` 试验行数 | 55,592 |
| 不同 `lead_sponsor` | 4,527 |
| 有 `company_key` | 38,715（69.64%） |
| `match_confidence ≥ 0.90` 被接受 | 38,715 |
| `0 < mc < 0.90` 仅候选 | 8,311 |
| `mc = 0` 未匹配 | 8,566 |
| `event_date == payload.first_posted` | 55,592 / 55,592 |
| payload 含 `start_date` | 55,143 |
| 事件日期范围 | 1999-10-19 .. 2026-10-30 |
| `first_seen_at` | `2026-10-30` × 55,592 |
| **映射到冻结 51 家名册的试验** | **4,367 条，覆盖 46 家公司** |

所以：**试验申办方关系可以建，但只在产品库里建**；在冻结研究输入里它是 0 条。名册内覆盖前几名：abbott 840、medtronic 624、alcon 580、boston_scientific 379、cooper_companies 175、philips 130、ge_healthcare 127、zimmer_biomet 124。

### 8.3 论文与研究机构：不能建

| 问题 | 结论 | 依据 |
|---|---|---|
| 公司–论文（论文级）关系 | **不能建（冻结输入）** | `publication_counts` 只有年度计数，无 paper id；观察台账只有 237 条 europepmc 观察 |
| 公司–论文（观察台账） | 237 条，但 238 条映射全部 `PENDING_REVIEW` | `observation_mapping.entity_status` 分布：待审 238 / 已接受 102 / 未映射 61 |
| 论文–作者关系 | **只能部分建（237 条）** | payload 只有 `author_string` 自由文本（逗号分隔姓名），无 ORCID、无作者 id |
| 公司–研究机构关系 | **完全不能建** | 所有存储的 europepmc payload 字段里**没有任何单位/机构字段**（`institution_field_present = false`）；单位名只出现在检索式 `AFF:"Medtronic"` 里，从未作为数据属性落库 |
| 机构标识符体系 | **不存在** | `company_identifiers` 只有 `scheme=SEC_CIK`（34 行），无 ROR/GRID/LEI/ORCID |

**明确结论**：S-028 想做的“公司–研究机构”或“论文作者–公司”关系在这套数据上**无法构建**，不要在设计里保留它们；如果必须做“研究强度”代理，只能用 `publication_counts` 的年度 works 计数，并声明它是公司名检索的聚合值、不是论文级证据。

---

## 9. Q-G：首次进入目标的正样本可行性

### 9.1 payload 字段确认与正确过滤条件

- `510k` 的 `clearance_type` 字段存在于 **31,219 / 31,219** 行，取值 6 种：`Traditional` 25,603、`Special` 4,685、`Abbreviated` 527、`Direct` 321、`Dual Track` 76、`Post-NSE` 7。
- `pma` 的 `supplement_number` 字段存在于 **23,871 / 23,871** 行；其中空字符串 **344** 行、非空 23,527 行。这 344 行的 `supplement_type` 也全部为空字符串（344 行）→ 确认它们就是 original PMA。
- 因此任务书给出的定义是**正确且可执行**的：`(kind='510k' AND payload.clearance_type='Traditional') OR (kind='pma' AND payload.supplement_number IS NULL/empty)`。

### 9.2 合格事件计数与敏感性

| 定义变体 | 事件数 |
|---|---|
| **Traditional 510(k)** | **25,603** |
| **Original PMA（无 supplement）** | **344** |
| **合计（本文采用的合格事件）** | **25,947**（占 55,090 的 47.10%） |
| 敏感性：全部 510(k) | 31,219 |
| 敏感性：Traditional + Special 510(k) | 30,288 |
| 敏感性：全部 PMA | 23,871 |

逐年分布：

| 年份 | 合格事件合计 | 其中 Traditional 510(k) | 其中 Original PMA |
|---|---|---|---|
| 2016 | 419 | 415 | 4 |
| 2017 | 2,660 | 2,614 | 46 |
| 2018 | 2,552 | 2,521 | 31 |
| 2019 | 2,381 | 2,349 | 32 |
| 2020 | 2,376 | 2,342 | 34 |
| 2021 | 2,542 | 2,511 | 31 |
| 2022 | 2,747 | 2,725 | 22 |
| 2023 | 2,760 | 2,725 | 35 |
| 2024 | 2,577 | 2,544 | 33 |
| 2025 | 2,695 | 2,655 | 40 |
| 2026 | 2,238 | 2,202 | 36 |

（2016 与 2026 是**不完整年**：窗口为 2016-11-01 .. 2026-10-18。）

### 9.3 从合格事件到可用正样本：88.88% 被实体映射吃掉

| 步骤 | 数量 | 损失 |
|---|---|---|
| 合格事件 | 25,947 | — |
| 同时有 `company_key` 与 `track_id` | **2,885** | 丢弃 23,062（**88.88%**） |
| 由此得到的 (company, track) 对 | **303** | — |

303 个对覆盖 49 家公司、38 个赛道（51 家公司里 2 家没有任何合格对）。作为对照，全部事件给出的 (company, track) 对是 334 个，合格事件保留了其中的 **90.72%**——也就是说，“合格”过滤本身只损失约 9%，而**实体映射损失了 88.88%**。瓶颈在映射，不在定义。

### 9.4 首次进入事件（positive label）的年度分布与风险集

| 年份 | 当年新增首次进入 | 之前已进入的对数 | 仍未进入的对数 |
|---|---|---|---|
| 2017 | 101 | 131 | 172 |
| 2018 | 47 | 178 | 125 |
| 2019 | 29 | 207 | 96 |
| 2020 | 15 | 222 | 81 |
| 2021 | 12 | 234 | 69 |
| 2022 | 16 | 250 | 53 |
| 2023 | 15 | 265 | 38 |
| 2024 | 15 | 280 | 23 |
| 2025 | 13 | 293 | 10 |
| 2026 | 10 | 303 | 0 |

首次进入按年的整体口径：2016: 30、2017: 101、2018: 47、2019: 29、2020: 15、2021: 12、2022: 16、2023: 15、2024: 15、2025: 13、2026: 10。

**可行性判断**：
- 2018 年以后每年只有 **10–16 个**正样本；303 个对里 27.06%（82 个）只有 1 条合格事件。
- 有 30 个对（9.90%）的首次出现落在窗口第一年 2016，属于**左截断**（censored），不能当作“新进入”标签。
- 平均每对只有 4 条合格事件（中位数）。
- 若按公司×赛道做 entry hazard，风险集在 2025 年只剩 10 个对，2026 年归零——**尾部年份的估计会极不稳定**。

这与上文「逐年缺失率」互为因果：映射覆盖率随时间恶化（2016 年 61.72% 可缺失 → 2023 年 71.04%），而正样本恰好集中在后期。

**审计意见**：303 个对、每年 10–16 个正样本，只够做**小规模描述性分析或分层验证**，不足以支撑复杂的多变量时序模型（尤其不能做深度学习/图神经网络式的结论）。论文必须报告 (i) 事件级与对级两种样本口径、(ii) 左截断处理方式、(iii) 逐年风险集规模。

---

## 10. 三个最大的数据缺口

**缺口 1：没有真实的 point-in-time 覆盖。**
冻结输入的 `first_seen_at` 对 55,090 行只有一个值 `2026-11-01`，`lag > 365 天` 的占 89.92%，真正 `lag ≤ 1 天` 的只有 1 行；`available_at` 是 `event_date + 14 天` 的常数偏移（零方差），且忽略了 461 行 PMA 里唯一真实的公开日期字段 `fed_reg_notice_date`。观察台账虽然是唯一有逐条观察记录的地方，但只有 1 天历史、400 条记录，真正 `lag ≤ 1 天` 的只有 6 条（1.5%），`lag > 7 天` 的 365 条（91.25%）。**结论：S-028 的历史部分必须自我定位为 `historical_proxy_asof` 模拟，不能宣称“当时可用的早期信号”。**

**缺口 2：正样本被实体映射掐住，且映射不可复现。**
25,947 个合格事件里只有 2,885 个（11.12%）同时有公司和技术赛道，最终只剩 303 个 company–track 对；2018 年后每年新增首次进入只有 10–16 个。映射规则本身不可审计：`events` 没有 `match_confidence`/`matched_alias` 列；8 个 (applicant, company) 组合不含任何别名却能匹配上（说明有未落库的规则）；2,089 条赛道路径中有 325 条连关键词回退都无法复现；`research.sqlite.product_codes` 是空表。**结论：任何人无法从交付工件独立复算出同一份 company-track 样本。**

**缺口 3：关系证据类型严重不足，且采购/财报边的时间语义不可用。**
不存在任何公司↔公司边（0 条）、公司→赛道直连边（0 条）、公司→论文/机构边（0 条）；冻结输入里没有试验数据。采购关系 3,453 行**全部** `pit_usable = 0`，`award_date` 与 `announcement_date` 均 100% 为空，`available_at` 只有 1 个批量抓取值，`valid_time` 实际是履约期起点。34 条财务边**全部没有 `valid_time`**。**结论：所谓“多源时间图”，当前有效的时序关系实际上只有监管事件一条线；其余三张表不能提供可信的历史时点。**

---

## 11. 建议（供主研人决定，不属审计结论）

1. **明确命名**：报告中的时间口径一律写 `historical_proxy_asof`；把 `observation_origin=LIVE` 改称“线上抓取通道”，避免与前瞻性混淆。
2. **重建时钟**：把 `published_at` 从“decision_date+14”改成可复核的规则，并优先使用 461 行 PMA 的 `fed_reg_notice_date`；对无真实公开时间的行，把 `available_at` 标记为 `assumed`。
3. **映射留痕**：为 `events` 增加 `match_confidence` / `matched_alias` / `mapping_version` 三列；把 `product_code_tracks.json` 的关键词回退规则随数据一起存档。
4. **实体口径二选一**：要么改用申报主体口径（避免 84 条日期泄漏与结构性别名泄漏），要么对 7 家受影响公司（`bd` 44.11%、`siemens_healthineers` 12.80% 最突出）单独做稳健性报告。
5. **正样本策略**：在 303 个对、每年 10–16 个事件的规模下，建议先做“事件级 early-signal”与“对级 entry”两套分层验证，不要直接上高维模型。
6. **删除不可做的事**：公司–机构、论文–作者、公司↔公司这三类关系在现有数据上不能建；从研究设计里移除，或明确标注为 future work 并说明需要新数据源。

---

## 12. 复现附录

| 脚本 | 覆盖内容 | 输出段 |
|---|---|---|
| `code/audit_10_provenance.py` | 冻结输入字节数/sha256/表行数、实时状态表检查 | `meta` |
| `code/audit_11_time_clocks.py` | Q-A（`first_seen_at`/lag/observatory origin/prospective）、Q-B 前半 | `A_point_in_time` |
| `code/audit_12_relations.py` | Q-C：`temporal_edges` 清单、缺失检验、边覆盖率、采购/财报时间质量 | `C_relations` |
| `code/audit_13_entity_mapping.py` | Q-D：别名匹配复现、别名日期范围、收购日期对照、母公司组成 | `D_entity_leakage` |
| `code/audit_14_track_coverage.py` | Q-E：赛道映射分类、关键词回退、产品码漂移、逐年缺失 | `E_track_coverage` |
| `code/audit_15_research_coverage.py` | Q-F：试验/论文/机构可建性 | `F_research_coverage` |
| `code/audit_16_positive_sample.py` | Q-G：payload 字段、合格事件、对级样本、entry hazard | `G_positive_sample` |
| `code/audit_17_crosschecks.py` | `event_date` vs `decision_date`、`fed_reg_notice_date` 对照、`timestamp_quality` | `crosschecks` |
| `code/audit_18_assemble.py` | 合并为 `artifacts/entity_time_audit.json`（含 `relation_types[]` 十字段台账） | 全部 |
| `code/audit_19_verify_report.py` | 回查本文每个数字是否出现在 JSON 中 | 校验报告 |

所有数据库连接均为 `mode=ro` 只读 URI；本审计未修改任何 `data/` 路径下的文件，未执行 git 命令。
