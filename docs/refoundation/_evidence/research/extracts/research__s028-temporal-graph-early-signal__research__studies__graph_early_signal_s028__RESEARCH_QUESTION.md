# S-028 研究问题 / Research Question

**Study:** S-028
**Title (EN):** Relational Early Signals in Medical Technology Development: A Temporal Network Study
**Title (ZH):** 《医疗技术发展中的关系网络早期信号：一项时间网络研究》
**Branch:** `research/s028-temporal-graph-early-signal`
**Programme:** MedRadar scientific research programme (工程 PR #12/#13/#14 不受影响)

---

## 1. 一句话问题

**在控制企业自身历史活动、技术赛道历史活动和总体时间趋势之后，企业—技术关系网络的历史结构，
是否仍能为"某企业将在未来 H 个季度内首次出现可观察的合格监管活动"提供增量预测信息？**

英文：*After controlling for a firm's own filing history, the track's history and common time
trends, does the historical structure of the firm–technology network add out-of-sample
information about that firm's first observed qualifying regulatory activity in the next H
quarters?*

## 2. 为什么这是一个值得做的科学问题

1. **它可证伪。** 有明确的零假设（无增量信息）、明确的指标（AP）、明确的分割（滚动时间、
   净化）和明确的对照（同模型同超参、仅换特征；以及保度随机化图）。
2. **它区分了两类解释。** 若加入图特征后 AP 上升，且随机化图使该上升消失，则"连接的具体
   排列"携带信息；若随机化后表现相同，则图结构不携带超越度的信息。
3. **先前的 programme 恰好在此处留下空白。** S-027/cycle-11 的 entry-clustering 线程
   （"同一赛道是否出现企业进入潮"）已被 CLOSED AS NULL：按月聚合、在赛道自身体量条件下，
   0/32 赛道可拒绝零假设。同期的 E11 基准建立了**强非图基线**（16 特征、ΔAP +0.0973，3/3
   窗口排除零）。二者之间的问题——"**个体企业的进入，能否由其邻居结构预测**"——尚未被检验。
   S-028 就是这个问题。
4. **它刻意不同于金融关系网络。** 金融工作预测连续收益、有稠密高频关系；本研究预测**右删失的
   首次事件**、关系**极稀疏**（每次快照仅 135–148 条边）、且边与标签**同源**（都来自同一条
   FDA 申报通道）。因此本研究的主风险不是"渠道缺失"，而是**重言/泄漏**，必须用严格的
   as-of 截断与随机化对照来排除。

## 3. 明确的非问题（本研究不回答，也不允许被引申）

| 不做 | 原因 |
|---|---|
| 不预测"技术创新"或"技术突破" | 标签只是公开监管活动；Traditional 510(k) 不是突破性产品 |
| 不建立因果 | 观测数据 + 无外生变化；领先 ≠ 因果 |
| 不把企业共现解释为合作/供应链 | 数据中不存在任何企业↔企业关系 |
| 不宣称实时前瞻验证 | 历史库无真实 `first_seen_at`；本研究是 historical simulation |
| 不宣称"网络无用"若只是功效不足 | 必须区分 NULL 与 UNDERPOWERED，并报告 MDE |
| 不主张 GNN 必要性 | GNN 是可选 Phase 4，只有 G1 通过门槛才允许 |

## 4. 与 programme 既有结论的关系

| 既有结论（`research/STATE.json`） | 对 S-028 的含义 |
|---|---|
| entry-clustering CLOSED AS NULL（0/32 赛道） | 赛道层面的"进入潮"不可检；S-028 转向**个体企业—赛道对**的关系结构 |
| E11 P2 ΔAP +0.0973（200 实体） / P1 ΔAP +0.0564（51 企业，MDE 0.0708 > 效应） | 强非图基线存在且**P1 口径本身功效不足**；S-028 主分析用 P1，必须报告 MDE |
| "no month-level cross-firm co-movement" | 本研究的 peer-entry 特征必须**不是**它的重复；G3 消融检验这一点 |
| "bulk lane availability = decision_date + 14 days (estimated)" | 这就是 S-028 的知识时钟；必须标注为估计 |
| "technology taxonomy is not versioned by effective date" | 分类后见之明不可修复，只能披露 |

## 5. 成功标准（来自任务书，逐条对应）

1. 提出明确且可证伪的科学问题 → 本文档 + `HYPOTHESIS_REGISTRY.md`
2. 使用适合回答该问题的数据 → `DATA_FEASIBILITY.md`（并诚实报告 12.1% 映射覆盖）
3. 建立严格的时间验证 → `TEMPORAL_LEAKAGE_AUDIT.md` + 净化滚动起点 + 冻结基准精确复现
4. 认真对待最强对照 → B2/B3 重实现 + 保度随机化图 G2
5. 验证真实网络结构确实携带增量信息 → G1 vs G2 vs G3
6. 所有关键结果可复现 → `REPRODUCE.md` + 确定性种子 + SHA-256 输入校验
7. 完整披露负结果 → `NEGATIVE_RESULTS.md`
8. 获得值得进一步研究的新知识 → `PAPER_DRAFT.md` 的结论与下一阶段门槛

## 6. 预期结果与诚实立场

由于图仅建立在 **12.1%** 的事件上、只有 **51 个节点**、平均企业度 **3.1–3.4**，
本研究**先验地预期 Outcomes B 或 D**（无增量信息 / 功效不足）比 Outcome A 更可能出现。
这不削弱研究的价值：一个 well-powered 的 NULL 会明确回答"在当前数据基础设施下，关系结构
是否值得投入"，从而为是否投资于更丰富的关系数据（合作、专利、试验、论文）提供依据。
**本研究不以"找到正结果"为目的。**
