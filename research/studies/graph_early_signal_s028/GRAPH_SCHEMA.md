# S-028 图模式 / Graph Schema

## 1. 图类型

**Company–Technology Temporal Bipartite Graph（企业—技术时序二部图）**

```
        ┌──────────────┐        activity edge        ┌───────────────────┐
        │   Company    │ ──────────────────────────► │  TechnologyTrack  │
        │ (company_key)│   (event block, 12m window) │    (track_id)     │
        └──────────────┘                             └───────────────────┘
```

- **节点类型（v1 只有两类，刻意保持最小）：**
  - `Company`：51 家策展企业键（`company_key`）。属性：无独立属性向量；企业规模只作为
    事后分层变量 `is_major`，**不作为特征**（避免把"大企业更容易申报"当成网络效应）。
  - `TechnologyTrack`：38 个设备技术赛道（`track_id`）。属性：`category`（手术/心血管/影像/
    骨科/…），**不作为特征**（赛道类别与赛道身份共线）。
  - **不建第三类节点**：无 Product 节点、无 Institution 节点、无 Paper 节点。原因见
    `DATA_FEASIBILITY.md` §1：机构与论文数据不存在；Product 节点与事件同源且会造成多重共线。
- **边类型（v1 只有一类）：** `ACTIVITY_IN`，表示"企业在某时间窗口内于某赛道存在可追溯的
  公开监管活动"。
- **边权重：** 窗口内事件数（计数，**不是**创新强度）。
- **边时间：** 每条边携带其构成事件的事件日期序列；快照层另有窗口起点/终点。

## 2. 快照语义（关键）

图**不是**一个全期对象。对每个预测起点 `t`，构建一个**独立快照** `G_t`：

```
V_company(G_t) = { c : c 在部分 events 中存在 event_date ≤ t 且 available_at ≤ t }
V_track(G_t)   = { k : k 同上 }
E(G_t)         = { (c,k, w) : 在 (t − 12m, t] 内存在 c 的、track_id = k 的 events，
                             且 event_date ≤ t 且 available_at ≤ t,
                             w = 该窗口内事件数 }
```

- 12 个月是固定的滚动窗口（不是累积全史），因此 `G_t` 描述的是**近期活动结构**。
- 另缓存一个累积的 first-touch 表 `first_touch[(c,k)] = min(event_date)`（同样受
  `available_at ≤ t` 约束），用于判定"近 12 个月内是否有**其他**企业首次进入赛道 k"。
- **没有任何跨快照的全期统计量。** 中心性、相似度、二跳邻域全部在 `G_t` 内部计算。

## 3. 节点与边的来源字段

| 图元素 | 来源 | 字段 |
|---|---|---|
| Company 节点 | `events.company_key` | 策展键（无模糊匹配） |
| Track 节点 | `events.track_id` | 产品代码→赛道映射结果 |
| Edge 存在 | `events` 行 | `(company_key, track_id)` 在同一 12m 窗口共现 |
| Edge 权重 | `count(*)` | 窗口内事件数 |
| Edge 时间 | `events.event_date` | 事件/决定日期（+14d 知识时钟代理） |
| Edge 类型（事件级） | `events.kind` + payload | `510k`/`pma`；`clearance_type`；`supplement_number` |
| 监管路径 | payload | `advisory_committee`, `decision_code` |
| 来源 | `events.source` | `openfda_device_510k_bulk` / `openfda_device_pma_bulk` |
| 映射可信度 | 无独立字段 | 策展键=高；赛道映射=产品代码确定性映射（无逐边置信度字段） |

## 4. 边上允许与禁止的解释

| 允许 | 禁止 |
|---|---|
| "该企业在该赛道有公开监管记录" | "该企业与该赛道有合作关系" |
| "事件数量=活动频率" | "事件数量=创新程度/技术突破" |
| "两家企业共享多个活跃赛道（组合相似）" | "这两家企业是竞争对手/合作伙伴"（数据不支持） |
| "其他企业在 k 赛道的首次出现早于本企业" | "存在技术扩散或传染（因果）" |
| "中心性高=在二部图中连接多" | "中心性高=企业更重要/更强" |

## 5. 图特征族（G1，12 个）

见 `PRE_REGISTRATION.md` §9.1 的完整定义。分组：

| 组 | 特征 | 理论含义（仅作为假设，不作为结论） |
|---|---|---|
| peer-entry | `g_coentry_count_12m`, `g_coentry_decay`, `g_coentry_similarity_weighted`, `g_max_entrant_similarity` | 同赛道他企先期进入是否提供先行信号 |
| similarity | `g_similarity_to_track_incumbents`, `g_similarity_to_track_max` | 本企业组合与赛道在位者组合的接近程度 |
| two-hop | `g_twohop_reach`, `g_twohop_activity_decay` | 经共享赛道的二阶邻域活跃度 |
| co-occurrence | `g_track_cooccurrence_pull` | 目标赛道与本企业现有赛道的共现倾向 |
| centrality | `g_company_eigenvector`, `g_company_clustering`, `g_track_entrant_centrality` | 结构位置（可能退化为度） |

## 6. 已知退化模式（必须在结果中检查）

1. **近完全二部投影：** 平均企业度 3–4，平均赛道度 4；企业—企业投影图接近完全图，
   `g_company_eigenvector` 近似退化为度 (`max|r|=0.779`)，`g_company_clustering` 近似退化为
   常数（`max|r|=0.089` 但方差极小）。二者若在消融中无贡献，应判定为退化特征。
2. **二跳邻域≈全图：** `g_twohop_reach` 与度高度相关 (`max|r|=0.849`)，因为图太小。
3. **稀疏性：** 每次随机 12m 快照只有约 135–148 条边，任何依赖路径长度的量都不稳定。

## 7. 图与标签的独立性约束

- 标签取自 `(t, t+H]` 的**合格事件**；图的边取自 `≤ t` 的**material 事件**。
- 两者时间区间不相交，且 material ⊃ qualifying。
- 若一个事件在 `(t, t+H]` 内合格，它**不能**影响 `G_t`（`available_at ≤ t` 保证它尚未公开）。
- 该约束由 `SnapshotSeries._history` 与 `build_entry_panel` 的同一过滤条件实现，
  并由 `artifacts/frozen_validation.json` 端到端验证。

## 8. 随机化图（G2）的模式

- 同一节点集、同一时间窗口、同样 12 个特征定义。
- 边由**块级保度交换**生成：保持每企业活跃赛道数、每赛道活跃企业数（二部度序列精确不变）。
- 时间分布：重连后的边从该赛道观测到的日期池抽取日期 → 每赛道时间分布保留。
- 每起点一个随机快照；重复 R=20 个种子。
- **保留：** 节点属性、企业活动规模、赛道活跃度、时间分布、样本、学习器、purge、metric。
- **破坏：** 只有"哪家企业活跃在哪个赛道"这一关联。
