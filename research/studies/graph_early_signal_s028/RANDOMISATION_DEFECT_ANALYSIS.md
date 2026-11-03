# S-028-CORRECTION-1 随机化方法缺陷分析（Randomisation Defect Analysis）

- 研究：S-028 temporal company–technology bipartite graph early-signal study
- 审查对象：`code/s028_lib.py::SnapshotSeries._build_randomised()`（Phase 0–3，commit `51c7fce`）
- 修正版本标识：`S-028-CORRECTION-1`
- 审计脚本：`code/audit_20_randomisation_invariants.py`
- 机器可读审计输出：`artifacts/correction_round_1/randomisation_invariants.json`
- 原始证据清单：`artifacts/correction_round_1/ORIGINAL_EVIDENCE_MANIFEST.json`
- 原始结论状态：**H2 的"随机图反超真实图"结论作废（INVALIDATED_FINDING）**；主结果 H1（图特征未改善 AP）不受本缺陷影响（`UNCHANGED_FINDING`）。

本文件回答一个问题：**Phase 0–3 的 G2 随机化对照，究竟做了什么？** 结论是：它既不是保度随机化，也不是保权随机化，也不是保时间分布随机化；它同时破坏了二部图度序列、边权语义与进入时间分布，因此 40/40 次随机化结果不能被解释为对"图结构是否携带信息"的检验。

---

## 1. 被审查的代码

```text
SnapshotSeries._build_randomised()          # s028_lib.py:492-550
  blocks = [(entity, track) for entity, tracks in weighted.items() for track in tracks]
  for _ in range(swaps_per_edge * len(blocks)):
      i, j = rng.randrange(len(blocks)), rng.randrange(len(blocks))
      ...
      if k2 in weighted[e1] or k1 in weighted[e2]:
          continue                     # <-- 检查的是原始 weighted，而不是当前边集
      blocks[i], blocks[j] = (e1, k2), (e2, k1)
  ...
  count = size.get((entity, track), 1) # <-- 交换后的新边几乎总是得到 1
  drawn = [pool[rng.randrange(len(pool))] for _ in range(count)]   # 有放回
  first_touch2[(entity, track)] = min(drawn)                       # 仅来自窗口日期
```

三个缺陷彼此独立，但叠加后使零模型失去可解释性。

---

## 2. 缺陷 A：交换过程破坏简单二部图约束（度序列漂移）

### 机制
候选边是否存在的判断 `k2 in weighted[e1]` / `k1 in weighted[e2]` 读取的是**原始** `weighted` 字典；`weighted` 在整个交换循环中从未更新。交换实际改变的是 `blocks` 列表。

因此在第一次交换之后，判断条件与实际图状态脱节：某条新产生的边 `(a, y)` 在后续交换中不会被识别为"已存在"，于是同一个 `(company, track)` 对可以被再次生成。`weighted2` 是 `dict`，重复边**静默合并**，对应的度配额凭空消失。

这与注释 "keep the randomised graph simple" 相反：注释声称的保护恰恰是失效的那一行。

### 最小反例（无需真实数据，可复现）
`audit_20_randomisation_invariants.py::minimal_counterexample()` 在 6 条边的二部图上自动搜索到反例：

| 项目 | 值 |
|---|---|
| 原始图 | `(a,x) (b,x) (b,y) (c,y) (d,z) (a,z)`，6 条边 |
| 复现种子 | `seed = 1` |
| 交换後边数 | **4**（丢失 2 条） |
| 度序列是否一致 | **否** |
| 总事件数是否一致 | **否** |
| 节点集合 | 是（该反例中恰好仍保留） |

在同一个图、同一个 seed 上，修正后的 N1 / N2 实现通过全部不变量（`corrected_on_same_case` 字段）。

### 真实数据上的规模（24 个 H=4q origin × 3 个 seed = 72 次随机化）

| 检查项 | 失败次数 / 72 | 说明 |
|---|---|---|
| 公司端 + 赛道端二元度序列一致 | **72 / 72 失败** | 每一次随机化都改变了度序列 |
| 总事件数一致 | **72 / 72 失败** | 权重塌缩的联合后果 |
| 逐赛道"近 12 个月首次进入"计数一致 | **72 / 72 失败** | 见缺陷 C |
| 单次随机化最多静默丢失边数 | **25 条** | 单个快照约 123–148 条边 |

因此原始实验宣称的 "degree-preserving rewiring"（`s028_lib.py` docstring、`PRE_REGISTRATION.md` Amendment 1、`PHASE_REPORT_ZH.md`）在实现层面**不成立**。

---

## 3. 缺陷 B：随机化改变了边权语义（加权图 vs 无权图混用）

### 机制
观察图的边权是 `weighted[entity][track]` = 该 12 个月窗口内该 (公司, 赛道) 的事件数。`_build_randomised` 用
`count = size.get((entity, track), 1)` 给交换后的边赋权，而 `size` 只包含**原始**边。交换产生的新边几乎全部落入默认值 `1`，原始边的事件数配额随之丢失。

于是：**原始 G1 在有权的活动图上计算余弦相似度特征，而随机臂在近似无权的图上计算同一批特征。** 两臂的特征语义不一致，AP 之差不再是"拓扑随机化"的效应。

### 规模（72 次随机化）
- 总事件数不一致：**72 / 72**
- 公司强度（公司窗口事件总数）最大偏差：**39 个事件**；平均最大偏差 **28.8 个事件**
- 原始 G1 快照平均约 334 个窗口事件（单快照示例），即偏差量级达到总量的 ~10%

### 一个直接的推论
`g_coentry_similarity_weighted`、`g_similarity_to_track_incumbents`、`g_similarity_to_track_max`、`g_max_entrant_similarity` 四个特征完全依赖权重。随机臂中这些特征被系统性压平。原报告没有区分"拓扑随机化"与"权重语义改变"，因此不能把随机图的 AP 变化归因于拓扑。

---

## 4. 缺陷 C：时间分布未被保留，且 first_touch 语义被系统性改变

### 机制
1. 窗口日期池 `pool[track]` 使用 **有放回** 抽样：`pool[rng.randrange(len(pool))]`。每赛道日期分布不守恒。
2. 观察快照的 `first_touch` 由**全部历史**（`day <= t`）计算；随机快照的 `first_touch` 却只由窗口内重抽样日期取 `min`。两者语义不同。
3. 后果方向明确：观察图中"近 12 个月首次进入某赛道"的公司只是少数；随机图中**几乎每条边看起来都是新进入**。`g_coentry_count_12m`、`g_coentry_decay`、`g_coentry_similarity_weighted`、`g_max_entrant_similarity`、`g_track_entrant_centrality` 五个特征因此被系统性抬高。

### 量级（72 次随机化，24 origin × 3 seed）
- 逐赛道新进入计数不一致：**72 / 72**
- "近 12 个月首次进入"的边占全部边的比例：
  - 观察图：均值 **10.5%**（每个快照约 14.5 条"新进入"边，共约 138 条边）
  - 原始随机化实现：均值 **100.0%**（每个快照约 119.8 条"新进入"边）
  - 修正后 N1 / N2：均值 **10.5%**（精确保持）

也就是说：原始随机化把"进入"这个事件从 10.5% 的边扩散到了**全部**边。这不是一个小的实现误差，而是把 `g_coentry_*` 系列特征的定义整个替换掉了——在随机臂中它们退化为"赛道成员数"。

### 为什么这足以单独毁掉 H2
`g_coentry_count_12m` 在随机臂中退化为"该赛道的成员数"，即一个纯粹的赛道活跃度代理。赛道活跃度与未来监管活动高度相关。于是一个**被注入的活跃度代理**可能单独抬高随机臂 AP——这与"随机关系更有预测力"无关。40/40 随机图反超真实图的模式，与这一机制的方向一致。

> 注意：上述机制是**可检验的解释**，不是已证实的因果。修正后的 N1/N2 重跑（`G2_CORRECTION_RESULTS.md`）用于确定反超现象是否仍然存在。

---

## 5. 原结论的状态

| 原报告表述 | 状态 | 理由 |
|---|---|---|
| "40/40 次随机化 AP 高于真实图，H2 不仅未满足而且反转" | **INVALIDATED_FINDING** | 随机化实现同时破坏度序列、权重语义与进入时间；该比较不是保度零模型比较 |
| "degree-preserving randomised graphs" | **INVALIDATED_FINDING** | 72/72 次随机化度序列不一致 |
| "per-track time distribution is preserved"（`_build_randomised` docstring） | **INVALIDATED_FINDING** | 有放回抽样 + first_touch 语义不同；72/72 次新进入计数不一致 |
| 主结果：G1 AP 0.0690 vs B2 AP 0.0751，ΔAP −0.0061 | **UNCHANGED_FINDING**（待独立复核确认） | G1 与 B2 走 `_build`/`run_spec` 路径，不经过 `_build_randomised`；`frozen_controls_check_*.json` 重新推导核对 |
| GNN 未启动（停止规则） | **UNCHANGED_FINDING** | 与随机化缺陷无关 |

因此：**原始"负结果"中唯一依赖随机化对照的那一半（H2 反转）作废；不依赖随机化对照的部分（H1 未获支持）需要独立复核后保留。**

---

## 6. 修正实现：Null Model N1 / N2

实现：`code/s028_nullmodels.py`（`NullSnapshotSeries` 直接复用未改动的 `SnapshotSeries._decorate` / `_compute`，保证特征语义与 G1 完全一致）。

### N1 — 拓扑零模型（Topology null）
**零假设**：在给定公司端与赛道端**二元度序列**的条件下，"哪家公司连接到哪个赛道"可交换。

- 动态维护边集与邻接索引的双边交换（double-edge swap），每条候选边都针对**当前**图状态检查，保证简单性；
- 边权：置换观察权重多重集（总事件数与权重边际分布精确保持；节点强度改变，已测量）；
- 赛道窗口日期：有放回重抽样（时间分布仅期望保持，已测量）；
- `first_touch`：在**每个赛道内**置换观察到的 first-touch 日期多重集（赛道级进入时间分布精确保持）。

### N2 — 拓扑 + 活动量 + 时间零模型
**零假设**：在 N1 之上，进一步以**赛道活动量**（每赛道窗口事件总数）与**逐赛道时间分布**为条件。

- 拓扑：同 N1；
- 边权：整数运输问题。优先用 `scipy` 整数最大流同时精确保持公司强度与赛道强度；**该问题在随机支撑上通常不可行**（见 §7），此时退化为精确保持赛道强度；
- 窗口日期：**无放回**发牌，逐赛道日期多重集**精确**保持；
- `first_touch`：同 N1，逐赛道日期多重集精确保持。

### 无法同时严格保持的约束（明确报告，不宣称）
在"二分度序列精确 + 简单图 + 整数边权"的约束下，**公司强度与赛道强度不能同时精确保持**：

- 在 24 个真实快照 × 3 个 seed = 72 次抽取中，同时保持两侧强度的整数运输解只在 **1 / 72** 个快照上可行；
- 不可行的原因是结构性的：随机支撑把高强度的公司连接到"剩余容量不足"的赛道集合，Hall 型条件不满足；
- 因此 N2 的声明是："精确保持度序列 + 赛道活动量 + 逐赛道时间分布；公司活动量偏差已测量"（公司强度平均最大偏差见审计输出）。

**公司级历史（公司自身的首次进入日期、自身事件日期）在任何这类零模型下都无法保留。** 这不是实现缺陷，而是零假设本身的含义：如果公司—赛道连接不携带信息，公司级历史就不能在零模型下存活。凡是依赖公司级历史的特征（`g_coentry_*`、`g_twohop_activity_decay`）在零模型下只能保持赛道级边际。该限制在 `G2_CORRECTION_RESULTS.md` 与科学边界声明中单独标注为 `UNRESOLVED_LIMITATION`。

---

## 7. 不变量门禁（Invariant gate）

只有全部通过才允许重跑 G2。`artifacts/correction_round_1/randomisation_invariants.json` 记录：

| 检查 | 原始实现 | N1 | N2 |
|---|---|---|---|
| 度序列保持（两侧） | FAIL 72/72 | PASS | PASS |
| 无重复边（简单图） | 隐含 FAIL（重复边被 dict 静默合并） | PASS | PASS |
| 节点集合保持 | 72/72 PASS（但边数减少） | PASS | PASS |
| 权重/强度偏差 | 总事件数 72/72 改变 | 报告偏差（非零） | 赛道强度精确；公司强度偏差已报告 |
| 时间分布偏差 | 72/72 新进入计数不一致 | TV 均值 0.54（有放回） | TV = 0（精确） |
| 交换接受率 | 未统计 | 均值 0.61（最小 0.52） | 同 N1 |
| 重连多样性（边改变比例） | 均值 0.87 | 均值 0.75（最小 0.65） | 同 N1 |
| 确定性可复现 | 单种子可复现但跨 origin 共享 RNG 流 | 同 seed 逐字节一致 72/72；异 seed 全部不同 72/72 | 同 N1 |

**Gate 结论：`PASS`（原始实现 FAIL，N1/N2 PASS），允许重跑 G2。**

重连多样性说明：N1/N2 每次随机化平均改变 75% 的边（最小 65%），因此不是因为"交换基本没发生"而接近原图。交换被拒绝的主因是 `would_duplicate`（约 30% 尝试）与退化选择（同边/同端点），属正常范围。

---

## 8. 复现方式

```powershell
cd research/studies/graph_early_signal_s028/code
python audit_20_randomisation_invariants.py --quick        # 合成最小反例
python audit_20_randomisation_invariants.py --seeds 3      # 真实快照全量不变量审计
python s028_g2_corrected.py --label H4q --quarters 4 --model N1 --randomisations 40
python s028_g2_corrected.py --label H4q --quarters 4 --model N2 --randomisations 40
```

原始文件未被覆盖：`artifacts/` 下 13 个 Phase 0–3 文件的 SHA-256 记录在 `ORIGINAL_EVIDENCE_MANIFEST.json`，修正轮结束后重新校验。
