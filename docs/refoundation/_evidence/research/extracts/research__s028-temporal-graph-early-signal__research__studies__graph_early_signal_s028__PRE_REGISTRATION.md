# S-028 预注册 / Pre-Registration
## Relational Early Signals in Medical Technology Development: A Temporal Network Study

**Study ID:** S-028
**Frozen at:** 2026-11-04T01:30+08:00 (before any S-028 model was fitted)
**Branch:** `research/s028-temporal-graph-early-signal`
**Status:** FROZEN. Amendments are permitted only as dated, appended, and explicitly labelled
amendments that state what was found before the amendment and why it was needed. Silent edits
are a research-integrity failure.

This document fixes the scientific question, the target, the data, the split, the metric, the
baselines, the graph model, the randomisation control, the statistical tests and the stopping
rules **before** any result from the S-028 target was observed. At freeze time only label
census and data-feasibility statistics existed (`artifacts/feasibility.json`); no model had
been fitted and no average-precision number for any model had been computed.

---

## 1. 研究问题

**RQ.** 在企业自身历史活动、技术赛道历史活动与总体时间趋势已被强非图基线控制之后，
企业—技术关系网络的历史结构特征，是否仍能提高对企业未来**首次可观察的合格监管活动**的
样本外预测能力？

英文：Does the historical structure of a company–technology bipartite network improve
out-of-sample prediction of a company's future **first observed qualifying regulatory
activity** in a technology track, beyond strong non-graph temporal baselines?

This is a question about *public regulatory filings*, not about innovation, R&D intent,
capability, or causal diffusion. All four are outside what the data can identify.

## 2. 可证伪假设（与 HYPOTHESIS_REGISTRY.md 对应）

- **H1 (incremental information):** G1（真实图结构特征）的样本外 AP 高于 B3（同一模型、
  同一基础特征、无网络结构特征）。零假设：ΔAP ≤ 0。
- **H2 (relational specificity):** 保持样本、训练流程、特征计算程序不变，把企业—技术连接
  做保度随机化（G2）后，AP 下降。零假设：G2 与 G1 无差异，即"网络结构"不携带特殊关系信息。
- **H3 (cross-subject early signal):** 其他主体的先期活动（同赛道新进入者、组合相似企业）
  在预测时点已公开的前提下，先于目标企业自身的首次合格活动。**本轮只能部分检验**：
  数据中不存在企业↔企业的显式合作关系、不存在论文作者或研究机构关系（见
  `RELATION_AND_TIME_EVIDENCE_AUDIT.md`），因此"H3 跨主体"只能以**统计关联**形式检验，
  不得表述为合作、供应链或因果传播。
- **H4 (conditionality):** 网络增益在不同技术赛道、企业类型、时间段之间存在异质性。
  必须完整报告所有预先声明的分层；只报告表现最好的赛道属于违规。

## 3. 数据（冻结输入）

| item | value |
|---|---|
| 主数据源 | `<REDACTED_LOCAL_PATH> |
| size | 289,443,840 bytes |
| SHA-256 | `dd241bfec138d7977d7eb8f4c1db25119d59b6fe7ff573060b24d14eeeb71e0d` |
| 读取器 | `code/s028_lib.py::load_events`；使用前强制校验 size + SHA-256 |
| lane | `openfda_device_510k_bulk`, `openfda_device_pma_bulk`；material 事件 31,802 条 |
| 知识时钟 | `available_at = event_date/decision_date + 14 days`（**估计值**，非实测首次公开时间） |
| `first_seen_at` | 全部历史行为单一批次抓取日 2026-11-01 → 不含 point-in-time 信息 |

**必须声明的结构性限制：** 这是 `historical_proxy_asof`，不是 `observed_asof`。
本研究是**历史模拟**，不是真实前瞻验证。真实前瞻评价只能使用 Live Observatory ledger
（400 条观察）另行开展，且本轮不把它与历史库混合。

### 3.1 实体面板（P1）

- 实体：`company_key` 策展企业键，**51 家**（MedRadar 设备 roster）。
- 技术赛道：`track_id`，**38 个**设备技术赛道（`t_` 前缀的医药赛道不参与）。
- 观测到的企业—赛道对：**322**；可能对 51×38 = 1,938；观测密度 **16.6%**。
- **映射覆盖率（关键限制）：** material 事件中同时具备 `company_key` 与 `track_id` 的仅
  **3,833 / 31,802 = 12.1%**。企业—技术图只建立在 12% 的通道上；其余事件对企业或赛道
  不可归属，不进入图。这一限制会在 LIMITATIONS.md 中再次出现，不允许被淡化。
- 不构建 P2（200 实体法人口径）于本轮：它在 E11 中已单独研究，且与本轮研究问题
  （既有 53 家企业范围内的关系结构）不同。列为下一轮扩展，不作为本轮结果。

### 3.2 合格事件（label 定义）

`first_observed_qualifying_regulatory_activity`：

- **Traditional 510(k)**：payload `clearance_type == "Traditional"`；
- **原始 PMA**：payload 无补充号（`supplement_number ∈ {"", "0", "S0"}`）。

排除：Special 510(k)（同一申报人自家器械的变更）、Abbreviated/Direct/Dual-Track/Post-NSE
510(k)、PMA Supplement。理由：这些是维护性/派生性活动，把它们计入"首次进入"会把
"器械变更"误读为"技术进入"。排除比例见 DATA_FEASIBILITY.md（Special 占 510(k) 的 14.7%）。

**明确区分：** 这是"数据库覆盖期内首次观察到"，不是"企业历史上首次"。左截断在 §5 处理。

## 4. 预测单元与风险集

在季度起点 `t`，单元为 `(company c, track k)`，当且仅当：

1. `c` 在 `t` 时点可观察：存在 material 事件满足 `event_date ≤ t` 且 `available_at ≤ t`；
2. `k` 在 `t` 时点可观察：存在 material 事件满足 `event_date ≤ t` 且 `available_at ≤ t`；
3. `(c,k)` 处于**休眠**状态：该对在 `(t − 36 months, t]` 内没有 material 事件。
   "从未在图窗口内出现过"的对同样满足（赋 `rd_pair_inactive_months = 120` 上限）。

`label = 1` 当且仅当 `(c,k)` 在 `(t, t + H]` 内出现至少一次**合格事件**。

## 5. 左截断与"首次"的诚实定义

通道窗口为 2016-11-01 起。任何"第一次"都只能是窗口内第一次观察。冻结时测得：
在首个起点 (2020-01-01) 之前，**71.4%** 的最终被观察到的对已经活动过。
因此本研究的 target 实质上是"休眠对在窗口内的首次（再）出现"，不是企业历史上的首次进入。
本预注册明确拒绝把它表述为"首次技术创新"或"首次进入市场"。

## 6. 时间范围、起点与切分

| 参数 | 值 |
|---|---|
| 主 horizon `H` | **4 个季度 = 12 个月**（主） |
| 次 horizon `H` | **2 个季度 = 6 个月**（预先声明的次要分析） |
| 起点 | 季度首日；`t − 36m ≥ 2016-11-01` 且 `t + H ≤ coverage_end` |
| 主分析起点数 | 24（2020-01-01 … 2025-10-01） |
| 次分析起点数 | 26（2020-01-01 … 2026-04-01） |
| 切分 | 扩展窗口滚动起点（expanding-window rolling origin），**绝不随机打散** |
| 净化（purge） | 训练样本在起点 `t` 可用，当且仅当 `cutoff + H ≤ t` |
| 主要 holdout | 最后 3 个可评估起点（`H=4q`：2025-04-01 / 2025-07-01 / 2025-10-01） |
| 次要 holdout | 同样最后 3 个可评估起点（`H=2q`） |

**为什么 H=4q 是主分析：** (a) 它与冻结基准 E11/cycle-2 的 12 个月 target 完全一致，
使 B3 成为真正的同口径对照；(b) 决策节奏为季度，4 个季度是有意义的预警窗口；
(c) 正样本量（418）支持企业聚类 bootstrap。此选择在**看到任何 AP 之前**作出，
且 H=2q 的全部结果同样报告，不因表现优劣而替换主分析。

**为什么不做 H 的事后选择：** 若两个 horizon 结论冲突，两者都如实报告，不选取更好的那个。

## 7. 评价指标

- **主指标：Average Precision（AP / AUPRC）**，在同一测试集上与强基线比较。
- 同时必须报告：正样本比例、ROC-AUC、Brier、ECE（10 分箱校准）、Precision@K
  （K = ceil(0.10 × n)，即按 10% 审查预算）、Recall@K、每季度候选数与正样本数、
  提前量（lead time）分布。
- 模型排序指标之外的校准指标不得省略；CALIBRATION 不因 AP 高而不报。

## 8. 模型（统一，避免模型-特征混淆）

**所有特征集比较使用同一个模型与同一组超参数**，使 AP 差异可归因于特征，而非模型：

- `LogisticBaseline(features)`：仓库内确定性批量梯度下降逻辑回归，
  `epochs=180, learning_rate=0.15, l2=1.0`，训练集唯一中位数填补 + 训练集标准化。
  （与冻结 E11 基准完全相同的学习器。）
- 稳健性检查（不作为主结论）：`HistGradientBoostingClassifier`，固定随机种子，
  同一特征集。仅在主结论出现后作为"更强非图学习器"下的复现检查。

## 9. 实验组与对照组（逐级递进）

| id | 特征 | 学习器 | 作用 |
|---|---|---|---|
| B0 | 无（确定性持久性预测器） | 常数训练流行率 / 企业基率 / 赛道基率 / 对基率 | 频率基线 |
| B1 | `BASE_FEATURES`(10) 企业/赛道/对历史 | 逻辑回归 | 历史特征基线 |
| B2 | `B3_FEATURES`(16) = BASE + ENTRY | 逻辑回归 | 强非图基线（= 冻结 E11 规格重实现） |
| B3 | 同 B2 | 同 B2 | **B2 即在 S-028 target/切分下的 B3 重实现**；二者数值必然相同，命名上分别对应"任务书 B2"与"任务书 B3" |
| B2g | `B3_FEATURES`(16) | HistGradientBoosting | 更强非图学习器（稳健性） |
| **G1** | `B3_FEATURES`(16) + `G1_FEATURES`(12) | 逻辑回归 | 首个关键实验：真实图特征 |
| G1g | 同 G1 | HistGradientBoosting | 稳健性 |
| **G2** | 同 G1，但图特征由**保度随机化图**计算 | 逻辑回归 | 关系随机化对照，重复 R 次 |
| **G3** | G1 去掉特征组 | 逻辑回归 | 消融：peer-entry / similarity / twohop / cooccurrence / centrality / decay |

### 9.1 G1 图特征定义（12 个，全部只用 `≤ t` 快照）

| 组 | 特征 | 定义 |
|---|---|---|
| peer-entry | `g_coentry_count_12m` | 近 12 个月内在赛道 k 首次出现的**其他**企业数 |
| peer-entry | `g_coentry_decay` | 同上，按进入时间指数衰减（半衰期 12 个月） |
| peer-entry | `g_coentry_similarity_weighted` | 进入者按与 c 的组合余弦相似度加权求和 |
| peer-entry | `g_max_entrant_similarity` | 最近进入者中与 c 最相似者的相似度 |
| similarity | `g_similarity_to_track_incumbents` | c 与 k 在位企业的平均组合相似度 |
| similarity | `g_similarity_to_track_max` | 最大相似度 |
| two-hop | `g_twohop_reach` | 经共享赛道可达的二跳企业数 |
| two-hop | `g_twohop_activity_decay` | 二跳邻域活动强度（时间衰减） |
| cooccurrence | `g_track_cooccurrence_pull` | k 与 c 当前组合的赛道共现强度 |
| centrality | `g_company_eigenvector` | 企业共活动投影图特征向量中心性 |
| centrality | `g_company_clustering` | 企业投影图局部聚类系数 |
| centrality | `g_track_entrant_centrality` | 赛道进入者在全部进入中的份额 |

**已知冗余风险（冻结前已测）：** `g_twohop_reach` 与 B3 特征的 max|r| = 0.849，
`g_company_eigenvector` = 0.779，其余 ≤ 0.445。这两个特征高度可能只是历史计数的
重新表达；G3 消融必须能显示这一点，且不得因此悄悄删除它们而不报告（删除只能作为 G3 的
一个预先声明消融项）。

### 9.2 G2 保度随机化程序（预先声明）

1. 在每个起点快照上，取 12 个月活动块的集合 `(company, track)`。
2. 用**块级二部保度交换**（block-preserving bipartite swaps）随机重排块的赛道端点：
   交换 `(c1,k1),(c2,k2) → (c1,k2),(c2,k1)`，拒绝产生重边的交换。
   这精确保持每家企业活跃赛道数、每个赛道活跃企业数（二部度序列）。
3. 每个块的**事件日期序列随块移动**，因此时间分布被保留。
4. 由随机化图重新计算全部 12 个 G1 特征，其余特征（B3）保持不变。
5. 重复 **R = 20** 个随机种子；报告 ΔAP 的分布（中位数、2.5/97.5 分位），
   而不是单次抽取。随机化种子固定并记录。
6. **这不是稻草人对照：** 度序列、样本、学习器、超参数、purge、metric 全部相同，
   唯一被破坏的是"哪家企业活跃在哪个赛道"。

## 10. 统计推断（预先声明）

1. 滚动时间样本外验证（§6）。
2. **企业聚类 bootstrap**：对 holdout 行按 `company_key` 整簇重采样 2,000 次（seed=7），
   得到 ΔAP 的 95% 百分位 CI；同时报告按 `(company,track)` 对聚类的 CI。
3. **差异必须是配对差异**：同一重采样行集同时评分两个模型。
4. **MDE**：以 bootstrap 的 ΔAP 标准误反推 80% 功效下的最小可检测效应，
   报告 `MDE(80%)`，并对每个不显著结论一并报告。
5. **多重比较**：预先声明的假设族 = {H1: 3 个 holdout 窗口 + pooled, H2: 3 窗口},
   以 Benjamini–Hochberg q=0.10 控制 FDR，同时报告未校正 CI。
6. **稳定性**：按年份、企业、赛道分别报告 AP 与 ΔAP（最小 n=10 / 正样本=5，
   不做事后子群挑选）。
7. **H2 重复实验**：R=20 次随机化的 ΔAP 分布。
8. 失败案例分析：主指标下排名最高但为负样本的案例，逐条列出（不隐藏）。

## 11. 决策规则（预先声明，直接引用）

**H1 SUPPORTED** 当且仅当同时满足：
- (a) 主分析 `H=4q` 的 ΔAP(G1 − B2) 的企业聚类 95% CI 在 **≥2/3** 个 holdout 窗口排除 0；
- (b) pooled ΔAP 在**两种聚类**下 CI 均排除 0；
- (c) 点估计 ΔAP ≥ pooled MDE(80%)。

**H1 NULL (well-powered)**：CI 包含 0 且观测效应小于 MDE。
**H1 UNDERPOWERED**：CI 包含 0 且 MDE 大于任何合理效应量（此时不得声称"无效应"）。

**H2 SUPPORTED** 当且仅当：
- (d) 真实图 G1 的 pooled AP 高于 **R=20 次随机化图** ΔAP 分布的第 97.5 百分位；
- (e) 且 (a)(b) 已成立。

**若 G1 与 G2 表现相同 → 禁止任何"网络结构发现"的表述。** 这种情况本身就是有效的
负结果（Outcome B），必须按负结果完整报告。

**H3** 只有在 H1 SUPPORTED 之后才进行提前量分析；否则提前量分析降级为描述性附录。
**H4** 全部分层如实报告，不做选择。

**停止规则：**
- 若 H1 不成立（NULL 或 UNDERPOWERED），**不得**启动 GNN（Phase 4），
  不得更换 target、horizon、metric 或数据集以追求正结果。
- 若 H2 不成立，关系结构主张永久撤销，不通过增加随机化次数或更换随机化算法挽救。
- 本轮结束即产出阶段报告；是否进入下一轮由报告中的决策门槛决定。

## 12. 明确禁止（本次研究自我约束）

- 不随机打散行做交叉验证；不随机切分时间。
- 不用测试集调参、调阈值、选特征、选 horizon、选聚类方式。
- 不事后更改预注册假设；如确需更改，以追加修订并说明动机，不覆盖原文。
- 不只展示最优模型；删除失败实验视为科研不端。
- 不把 `historical_proxy_asof` 称为严格 point-in-time。
- 不把统计显著等同于科学重要；不把预测能力等同于因果解释。
- 不把监管活动等同于技术创新；不把企业—技术共现解释为合作关系。
- 不虚构论文、数据、DOI 或实验结果。

## 13. 本轮可行性门槛（Phase 0 → Phase 1）

在冻结时已知：正样本 418（H=4q）/ 239（H=2q）；企业 51；观测对 322；图边（12m）135–148。
若在 holdout 上 `min` 窗口正样本 < 10，则该窗口不用于 H1 判定但必须报告。
若所有窗口均不满足，则结论为 **Outcome D: 统计功效不足**，不进入 Phase 2。

---

*Freeze hash is recorded in `artifacts/prereg_freeze.json` (SHA-256 of this file and of
`HYPOTHESIS_REGISTRY.md`) and is written by `code/s028_freeze.py`.*

---

## Amendment 1 — 2026-11-04, recorded **before any G1/G2/G3 result was observed**

**Context at the time of this amendment.** The frozen-harness validation had passed
(`artifacts/frozen_validation.json`: every frozen AP reproduced to <3e-7). The label census and
`DATA_FEASIBILITY.md` were complete. **No graph-model AP, no ΔAP, and no randomisation result had
been computed or seen.** The amendment is therefore not a reaction to any result.

**Trigger.** The independent literature reviewer (`LITERATURE_REVIEW.md` §9 B1) raised two
methodological points about the pre-registered H2 design. Both are accepted.

**A1.1 — Randomisation resolution raised from R = 20 to R = 40.**
Reason: with only 20 draws, the "97.5th percentile" of the randomisation distribution is
effectively the maximum of 20 order statistics, so the smallest attainable one-sided p-value is
about 1/21 ≈ 0.048 even if the real graph is best in every draw. That resolution is too coarse to
state an H2 verdict cleanly. With R = 40 the attainable one-sided resolution is about
1/41 ≈ 0.024 and the 97.5th percentile is no longer simply the maximum.
**The criterion is unchanged** — real pooled AP must exceed the 97.5th percentile of the
randomised distribution, and H1 must be SUPPORTED. Only the resolution of the null distribution
changes. All R values used are recorded in the artifact.

**A1.2 — The null model's scope is stated explicitly (interpretation, not method).**
After preserving node degrees **and** the per-track time distribution, what the G2 null tests is
whether **the arrangement of edges** (which company in which track) carries information. It does
**not** test whether "relationships" in any richer sense carry information, and it cannot, because
the data contain no richer relationship at all (no company↔company edge; see
`HYPOTHESIS_REGISTRY.md`). Therefore:
- a **positive** H2 licenses only: "the specific company–track arrangement beats a degree- and
  time-matched rearrangement";
- a **negative** H2 (G1 ≈ G2) is a valid negative about *this* null only, and the relational claim
  is withdrawn;
- neither outcome licenses any statement about partnership, supply chain, collaboration,
  diffusion, or causality.

**A1.3 — Nothing else changes.** Target, horizons, risk set, split, purge, metric, feature sets,
learner, clustering choices, MDE method, FDR procedure and decision rules are exactly as frozen in
§1–§13. This amendment is appended, not substituted; the original text above is unmodified.

*Amendment freeze hash: `artifacts/prereg_freeze_amendment1.json`.*

