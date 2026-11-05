# S-028 数据可行性报告 / Data Feasibility Report

**Phase:** 0 (data audit and feasibility) — completed before any S-028 model was fitted.
**Artifacts (all committed):**
- `artifacts/feasibility.json` — every number in this document, computed by
  `code/s028_feasibility.py`
- `artifacts/entity_time_audit.json` + `RELATION_AND_TIME_EVIDENCE_AUDIT.md` — independent
  provenance audit by the evidence auditor
- `artifacts/frozen_validation.json` — proof the analytical harness reproduces the frozen benchmark

**Verdict: GO (conditional).** The data can support a temporally honest company–technology
bipartite entry study, and there is a valid, exactly reproducible evaluation harness. But the
graph rests on **12.1%** of the event lane and **51 nodes**, so the relational hypothesis is
**low-powered by construction** and a null result is the *expected* outcome. Conditions attached
in §9.

---

## 1. 数据规模与实体存在性（brief 第三章要求的逐项确认）

冻结主库 `research.sqlite`（SHA-256 `dd241bfe…1eeeb71e0d`，289,443,840 bytes）内：

| 实体 | 是否存在 | 规模 | 质量/限制 |
|---|---|---|---|
| 医疗器械企业 | ✅ | 51 家策展 `company_key` | 名称+别名策展；别名含被收购子公司（见 §5） |
| 技术赛道 | ✅ | 38 个设备赛道 | 产品代码→赛道映射，非按生效日期版本化（§6） |
| 产品代码 | ⚠️ | `product_codes` 表在本库为 **0 行**；代码只出现在 `events.payload.product_code` | 无法独立审计代码→赛道映射表，只能通过 payload 反推 |
| 监管事件 | ✅ | 55,090 行（510k 31,219 + pma 23,871）→ material 31,802 | 2016-11-01 … 2026-10-18 |
| 临床试验 | ❌（冻结库） | 仅产品库 `medradar.sqlite` 有 `ctgov` 55,592 行 | 未纳入本实验；见 §8 |
| 临床试验申办机构 | ❌（冻结库） | 产品库中有 `lead_sponsor` 字符串与 `match_confidence` | 字符串匹配，非实体解析 |
| 研究机构 | ❌ | **不存在**独立机构实体 | 只有申办方字符串，无法建立机构节点 |
| 科研论文 | ❌ | 只有聚合 `publication_counts`（616 行） | **无作者、无 DOI、无 paper-level 记录** → 无法建论文/作者图 |
| 企业之间的明确关系 | ❌ | `temporal_edges` 仅 4 类，**全部不含 company↔company** | 见 §4；不允许用名称相似度或同赛道共现创造合作关系 |

> **结论：** "论文—作者—机构"这一整类跨主体关系在本数据中**不可构建**。
> 任何涉及科研机构或论文作者的 H3 表述都必须在报告中降级为"数据不支持"。
> 这一条已写入 `HYPOTHESIS_REGISTRY.md`。

## 2. 事件构成：material 与合格（qualifying）事件

| 类别 | 数量 | 占 510(k) | 是否计入 label |
|---|---:|---:|---|
| 510(k) Traditional | 25,603 | 82.0% | ✅ 计入 |
| 510(k) Special | 4,685 | **15.0%** | ❌ 排除（自家器械变更） |
| 510(k) Abbreviated | 527 | 1.7% | ❌ 排除 |
| 510(k) Direct | 321 | 1.0% | ❌ 排除 |
| 510(k) Dual Track | 76 | 0.2% | ❌ 排除 |
| 510(k) Post-NSE | 7 | 0.02% | ❌ 排除 |
| PMA 原始（无补充号） | 344 | — | ✅ 计入 |
| PMA 补充（Supplement） | 239 | — | ❌ 排除 |

- material 事件合计 **31,802**；合格事件 **25,947（81.59%）**。
- **这修正了冻结基准的一个已知缺陷**：`research/STATE.json` 记录 "~15% of lane 510(k)s are
  Special"，而冻结 E11 基准把它们计入了 label。S-028 的 label 明确排除它们，因此
  "首次进入"不会被维护性变更污染。两种口径的结果都报告（见 §3）。

**这不是创新度量。** 合格事件只是"可核验的公开监管活动"。Traditional 510(k) 不等于突破性
产品，原始 PMA 也不等于技术突破。报告中的 label 一律命名为
`first_observed_qualifying_regulatory_activity`。

## 3. 目标可行性：样本量、发生率、覆盖

| panel | 行数 | 正样本 | 基础率 | 起点数 | 起点范围 |
|---|---:|---:|---:|---:|---|
| **H=4q qualifying（主）** | 41,003 | **418** | 1.019% | 24 | 2020-01-01 … 2025-10-01 |
| H=4q material（冻结口径，敏感性） | 41,003 | 503 | 1.227% | 24 | 同上 |
| H=2q qualifying（次） | 44,433 | **239** | 0.538% | 26 | 2020-01-01 … 2026-04-01 |
| H=2q material（敏感性） | 44,433 | 287 | 0.646% | 26 | 同上 |

- **正样本充足**：主分析 pooled holdout 有 78 个正样本（3 个窗口），足以做企业聚类 bootstrap；
  但**单个窗口只有约 25–27 个正样本**，单窗口估计会很不稳定。这决定了结论必须以 pooled
  为主、单窗口为辅，且必须报告 MDE。
- 每个起点平均约 1,708 个候选（= 休眠对），正样本约 17 个 → 每季度真实"进入"事件很少。
- 剔除维护性申报后正样本从 503 降到 418（−17%），说明**六分之一的"首次活动"其实是维护性
  申报**。这是本报告最重要的口径发现之一。

## 4. 企业—技术二部图的实际规模（关系可建性）

| 指标 | 2020-01-01 快照 | 2025-10-01 快照 |
|---|---:|---:|
| 12 个月内活跃企业 | 43 | 44 |
| 12 个月内活跃赛道 | 34 | 33 |
| 12 个月内边（企业—赛道活动） | 148 | 135 |
| 图密度 | 0.101 | 0.093 |
| 企业平均度 / 最大度 | 3.44 / 11 | 3.07 / 13 |
| 赛道平均度 / 最大度 | 4.35 / 15 | 4.09 / 17 |

全期口径：51 企业 × 38 赛道 = 1,938 个可能对，**观测到 322 对（16.6%）**；其中有合格事件的
303 对。

**这是本次可行性审计的第二个关键发现：图很小。** 平均每家企业只在 3–4 个赛道同时活跃，
每个赛道只有 4 个左右活跃企业。在这样的图上，"网络结构"的可用信息量有限，二阶邻域几乎
覆盖全图。任何 GNN 在此规模上都不可能有稳定优势——因此 GNN 被明确推迟为可选（Phase 4），
且需先通过 G1。

### 4.1 关系类型清单（brief 要求逐类记录）

| 关系 | 定义 | 证据来源 | 时间字段 | 是否含未来信息 | 覆盖 | 结论 |
|---|---|---|---|---|---|---|
| 企业→技术赛道 | 企业某事件被映射到某赛道 | `events.company_key` + `events.track_id` | `event_date`(+14d 代理) | 否（按 as-of 截断） | 3,833 条（**12.1%** 的 material 事件） | ✅ 唯一可用的关系骨架 |
| 企业→产品→技术 | 产品归属技术 | `temporal_edges.PRODUCT_BELONGS_TO_TECHNOLOGY` | `valid_time`/`available_at` | 否 | 1,087 | ✅ 但与本图冗余 |
| 企业→产品 | 企业开发产品 | `temporal_edges.COMPANY_DEVELOPS_PRODUCT` | 同上 | 否 | 1,087 | ✅ 与事件同源 |
| 企业→合同 | 政府采购中标 | `temporal_edges.COMPANY_WINS_CONTRACT` / `procurement_awards` | 合同日期 | **当前快照**（非历史全量） | 3,372 | ⚠️ 不可用于历史增益 |
| 企业→财报 | SEC 事实 | `temporal_edges.COMPANY_FILES_FINANCIAL_FACT` | `available_at` | 否 | 34 | 与本问题无关 |
| 企业↔企业 | 合作/供应/许可/共专利 | **不存在** | — | — | 0 | ❌ 不可构建 |
| 企业↔研究机构 / 论文作者 | — | **不存在** | — | — | 0 | ❌ 不可构建 |
| 企业↔临床试验申办 | 仅产品库 | `ctgov` `lead_sponsor` | `first_posted` | 字符串匹配 | 55,592（另一库） | ⚠️ 未纳入本轮 |

## 5. 映射覆盖率与实体归属（最重要的限制）

| 覆盖率 | 数值 |
|---|---:|
| material 事件有 `company_key` | 5,489 / 31,802 = **17.3%** |
| material 事件有 `track_id` | 18,889 / 31,802 = **59.4%** |
| 两者都有（**真正进入图**） | 3,833 / 31,802 = **12.1%** |

- **87.9% 的 material 事件不进入企业—技术图。** 这不是可以轻描淡写的细节：图中看到的
  "企业活动"不到事件通道的八分之一。赛道映射缺失（40.6%）与企业映射缺失（82.7%）是两个
  独立的损失来源。
- 企业归属是**策展键 + 别名**，无模糊匹配；但别名包含被收购子公司，因此存在**实体身份后见
  之明**（见 `TEMPORAL_LEAKAGE_AUDIT.md` §3）。
- 赛道归属依赖产品代码→赛道映射，且该映射**未按生效日期版本化**（`research/STATE.json` 已
  记录同一缺陷）→ 存在**分类映射后见之明**（同审计 §2）。

### 5.1 映射的可复现性（独立审计发现的第三个重要限制）

企业归属与赛道归属**无法从冻结库中完整复现**：

- `events` 表**没有** `match_confidence` 或 `matched_alias` 列，无法逐边审计匹配依据。
- 审计发现 **8 个 (applicant, company_key) 组合在不含任何别名的情况下匹配成功**——存在
  未记录的匹配路径。
- 2,089 条赛道赋值中有 **325 条连关键词回退规则都复现不出**。
- `research.product_codes` 是**空表**，因此"产品代码→赛道"映射表本身不可审计，只能通过
  payload 反推。
- 合格事件 25,947 条中，只有 **2,885 条（11.12%）** 同时具备公司与赛道，最终形成
  **303 个企业—赛道对**。

**这意味着：** 图的节点与边不是可由原始证据逐条重建的产物，而是依赖一个**部分不可复现的
映射黑箱**。这不是可以留给下一轮的小瑕疵——它直接限制了任何"关系结构"结论的可验证性，
并在 `LIMITATIONS.md` 与最终结论中被列为 Outcome D 的主要依据之一。

## 6. 时间与左截断

- 知识时钟：`available_at = event_date + 14 days`，**31,802/31,802 全部如此** → 这是
  `historical_proxy_asof`，不是实测首次公开时间。
- `first_seen_at` 在全部历史行只有**一个取值**（2026-11-01）→ 不含 point-in-time 信息。
- **左截断（两种口径，都必须报告）：**
  - 口径 A（本研究使用）：首个起点 (2020-01-01) 之前，已有 **230 / 322 = 71.4%** 的最终被观测对活动过。
  - 口径 B（独立审计）：**30 / 303 = 9.90%** 的对在 36 个月休眠窗口内左截断。
  - 两者度量不同：A 问"首起点时已有多少对不再处于休眠"，B 问"多少对的休眠窗口不完整"。结论相同：
    本研究的 "first" 一律是"**数据库覆盖期内首次观察到**"，不是企业历史上首次进入。
- 逐年首次观测进入数：2016:30, 2017:101, 2018:47, 2019:29, 2020:15, 2021:12, 2022:16,
  2023:15, 2024:15, 2025:13, 2026:10。
  → **2016–2017 的"进入"高峰是窗口边界效应**（窗口从 2016-11-01 开始，大量企业此前已在
  活动），这不是真实的行业进入潮。任何"进入加速/放缓"的叙述都不得基于此表。

## 7. 图特征是否只是历史计数的重新表达（brief 第四章要求）

冻结前测得每个 G1 图特征与 16 个 B3 历史特征的最大 |Pearson r|：

| 图特征 | max\|r\| | 判读 |
|---|---:|---|
| `g_twohop_reach` | **0.849** | 高度可能只是企业活跃赛道数的非线性重述 |
| `g_company_eigenvector` | **0.779** | 在近完全二部图上近似退化为度 |
| `g_coentry_count_12m` | 0.445 | 部分独立 |
| `g_track_entrant_centrality` | 0.436 | 部分独立 |
| `g_coentry_decay` | 0.432 | 部分独立 |
| `g_track_cooccurrence_pull` | 0.355 | 较独立 |
| `g_similarity_to_track_max` | 0.353 | 较独立 |
| `g_similarity_to_track_incumbents` | 0.224 | 较独立 |
| `g_twohop_activity_decay` | 0.193 | 较独立 |
| `g_coentry_similarity_weighted` | 0.153 | 较独立 |
| `g_max_entrant_similarity` | 0.148 | 较独立 |
| `g_company_clustering` | 0.089 | 较独立 |

**必须与 G3 消融一起读。** 相关系数低不等于携带新信息（可能是噪声）；相关系数高也不等于
无用（可能是同一信号的更稳定版本）。G3 的 no-twohop / no-centrality 消融就是为这两个特征
准备的，若去掉它们 AP 不变，则它们只是重述。

## 8. 未纳入本轮的数据（及原因）

| 数据 | 位置 | 未纳入原因 |
|---|---|---|
| ClinicalTrials.gov 试验 | `medradar.sqlite`（55,592） | 与冻结实验库不同源；申办方为字符串匹配；与本轮"企业—技术图"问题不同层次。列为下一轮独立来源验证 |
| Live Observatory（400 条） | `observatory.sqlite` | **独立审计的修正：只有 6 / 400 条是真正的 observed_asof。** `observation_origin=LIVE` 是**采集方式标签**，不是前瞻性证据：400 条全部在 2026-11-03 单日首次入库，其中 365 条（91.25%）的公开时间比首次看到早 7 天以上，中位 lag 65 天、最大 7,613 天；`first_seen_at` 只有 4 个取值。真正 lag ≤ 1 天的只有 6 条（1 条 ctgov trial、4 条 europepmc、1 条 sec_edgar 6-K）。6 条不足以做任何模型评估，因此本轮**不使用**观察台账；它只能作为未来前瞻研究的起点，且必须先积累足够的前瞻样本。 |
| 论文 / 作者 / 机构 | 无 | 数据不存在 |
| 专利 | 无 | 无 key、无可用批量路由（`research/STATE.json` 已记录 403） |
| 招聘 | Wayback（实验性） | 覆盖不足；与本问题非直接相关 |

## 9. Phase-0 决策与条件

**决策：GO（条件式）。** 允许进入 Phase 1（强非图基线）与 Phase 2（简单网络特征）。

**条件（不满足则不进入下一阶段）：**

1. 任何结果必须标注为 **historical simulation**，知识时钟为 `decision_date + 14 days` 的估计值。
2. 必须以 **pooled 三窗口** 为主要判定，单窗口仅作稳定性证据；必须同时报告 MDE(80%)。
3. 由于图仅建立在 12.1% 的事件上且只有 51 个节点，**负结果被视为高先验概率结果**；
   不得通过更换 target/horizon/dataset 去"抢救"正结果（`PRE_REGISTRATION.md` §11 停止规则）。
4. 禁止把 2016–2017 的进入高峰解释为行业趋势（§6）。
5. 禁止把任何共现或领先解释为合作、传播或因果（H3 限制，§4.1）。
6. GNN 只有在 G1 通过预注册门槛后才允许启动（Phase 4，可选）。

**若后续发现以下任一情况，应转为 NO-GO 并如实报告：**
- 主分析 holdout 单窗口正样本 < 10（当前约 25–27，暂不触发）；
- 随机化对照与真实图无差异（则关系结构主张撤销，Outcome B）；
- 所有 G1/G2 差异的 CI 均包含零且 MDE 大于任何合理效应（则写为"统计功效不足"，Outcome D，
  而不是"网络无用"）。
