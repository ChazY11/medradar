# S-028 时间有效性 / 未来信息泄漏独立复核（更正轮 1）

**Temporal-Validity & Leakage Correction Audit — S-028**

| 项目 | 值 |
|---|---|
| 审计日期 | 2026-11-04 |
| 审计角色 | 独立于 S-028 建模路径的时间有效性审计员（不是原审计作者） |
| 审计对象 | `research/studies/graph_early_signal_s028/`，冻结输入 `research.sqlite`（只读） |
| 冻结输入 SHA-256 | `dd241bfe…1eeeb71e0d`，289,443,840 B —— **开工前校验一致，收工后再校验一致**（未改动 1 字节） |
| 可执行交付 | `code/audit_23_leakage_correction.py`（自包含、确定性，约 61 s，numpy；只读 URI 打开 DB） |
| 机器可读结果 | `artifacts/correction_round_1/leakage_audit.json`（21 个审计项、逐项 PASS/FAIL/UNRESOLVED + 全部计数） |
| 未改动 | 原代码、原工件、`TEMPORAL_LEAKAGE_AUDIT.md`、`HUMAN_REVIEW_WORKSHEET.csv` 均未编辑；未运行任何 git 命令 |

**标记约定（本文与 JSON 使用同一套）：**

| tag | 含义 |
|---|---|
| `ORIGINAL_RESULT` | 独立重算确认原结论/原数字成立 |
| `CORRECTED_RESULT` | 原结论的方向或措辞需要更正（本轮给出更正后的数字） |
| `UNCHANGED_FINDING` | 原审计已提出，本轮量化后仍然成立 |
| `INVALIDATED_FINDING` | 原审计/可行性报告的具体断言被证据推翻 |
| `UNRESOLVED_LIMITATION` | 在本轮数据上无法判定，列出能定案的证据 |

---

## 0. 复核方法论：复现 ≠ 无泄漏

原审计的核心论证是"冻结 cycle-2 基准被复现到 <3e-7 AP，因此没有未来泄漏"。本轮**首先把这句话拆开**：

- 本轮独立重跑冻结基准（material label、H=12m、`company_key`、24 起点）：
  panel **41,003 行 / 503 正样本 / 24 起点**；pooled AP **0.101060**（复现目标 0.101060）、persistence **0.044614**；
  三个 holdout 窗口 AP = **0.137085 / 0.095027 / 0.100476**（与 `frozen_validation.json` 的 0.137085 / 0.095027 / 0.100476 一致）。
  → 这只证明**代码/面板保真度**（`ORIGINAL_RESULT`），不证明没有未来信息。

本轮因此改用三个**结构性**工具，而不是复现：

1. **截断不变性（truncation invariance）**：对 24 个起点逐一"只保留 `day ≤ t` 且 `available ≤ t` 的事件"重建整个快照与面板，要求与原结果**逐位相同**。这直接检验"任何特征是否携带 t 之后的信息"。
2. **事件级 purge 矩阵**：对 24 个起点计算训练标签窗口与测试标签窗口的日级重叠，并在**物理事件 ID** 层面求集合交集。
3. **上游参照 + 随机图对照 + 共享方差**：用非冻结产品库量化左截断/右删失；用 40 次随机图分布检验"图结构是否携带信息"（原始臂已证有缺陷，以修正后 N1/N2 为准，见 `G2_CORRECTION_RESULTS.md`）；用 G1 对 B3 的多元 R² 与消融量化"图特征是否只是历史活动的重述"。

---

## 1. 检查 1：知识时钟（Knowledge clock）

### 1.1 逐行事实（全部行，不是抽样）

| 指标 | 数值 |
|---|---|
| `events` 总行数 | **55,090**（510k 31,219 + PMA 23,871；material 31,802） |
| `available_at − event_date` | **+14 天，55,090 / 55,090 = 100.00%**（唯一取值，零方差） |
| `timestamp_quality` | `estimated` **55,090 / 55,090 = 100%**（无 measured/observed 行） |
| `available_at < event_date` | **0** |
| `available_at` 缺失 / 不可解析 | **0 / 0** |
| `available_at` 晚于快照日 | **0** |
| `event_date == payload.decision_date` | **55,090 / 55,090 = 100%**（`event_date` 就是决定日） |
| `available_at == published_at` | **55,090 / 55,090 = 100%**（两列是同一个合成值） |
| `first_seen_at` 不同取值 | **1 个**（2026-11-01，全部行） |
| `as_of` 不同取值 | **1 个**（2026-11-01） |
| 冻结库 `meta` 表 | **0 行**（无冻结行数/来源元数据） |

**结论：** 原审计 §0/§1 的核心事实成立，且本轮把口径从"31,802 material 事件"扩展到"55,090 全部事件"，结论不变（`ORIGINAL_RESULT`）。所谓"两侧过滤器 `day ≤ t and available ≤ t`"在本数据上等价于 `day ≤ t − 14d`：**这是一个只延迟信息、不会提前授予信息的保守规则**（`available_at` 恒晚于 `event_date`，故不存在"在事件自己的决定日之前就知道它"的行）。

### 1.2 "decision_date + 14 天"是代理，不是测量

`available_at` 与 `published_at` 是同一个 `decision_date + 14d` 的合成值；`first_seen_at`/`as_of` 只有一个批量抓取日，**不含任何 point-in-time 信息**。因此：

- **无法从冻结数据验证 14 天真伪**；它只是"对 bulk-lane 发布延迟的估计"。
- 更有反向风险：payload 里保留了 `date_received`（提交日），它比决定日**系统性地早**：中位 **86 天**、P90 **268 天**、24.2% 超过 180 天（55,090 行全部有该字段）。真实分析师在决定日之前很久就能看到"已受理"，所以本研究的 lead-time 只是**下界**（`UNCHANGED_FINDING`，原审计 §5 已提出，本轮给出行级分布）。

### 1.3 泄漏方向与量级（本轮新增量化）

- 14 天盲区：每个起点平均有 **0.73%** 的 lane 事件因 `available_at > t` 而被隐藏——这是"少看"，不是"多看"。
- 但若 14 天**低估**了真实发布延迟，则 `(t−真实延迟, t−14d]` 这一段就会变成"模型看到了公众还看不到的信息"。按"真实延迟 = 30 / 60 / 90 / 180 天"假设，该假设性泄漏带平均占 lane 的 **0.86% / 2.35% / 3.81% / 8.36%**（单起点最大 1.61% / 4.18% / 6.84% / 14.27%）。量级不大，但**不可从冻结数据排除**。

**逐项判决：**

| 项 | 判决 | tag |
|---|---|---|
| 1a 内部一致性（100% = +14d、无缺失/垃圾/负滞后、事件日=决定日） | **PASS** | `ORIGINAL_RESULT` |
| 1b 知识时钟是估计代理、无实测首次公开时间 | **UNRESOLVED** | `UNCHANGED_FINDING` |
| 1c 无"早于事件日"的泄漏；残余风险是 14d 低估时的反向泄漏（量级见上） | **PASS**（条件式） | `UNCHANGED_FINDING` |

---

## 2. 检查 2：特征前视（Feature look-ahead）

### 2.1 全部 28 个特征的计算路径（provenance 表在 JSON `2a_provenance_table`）

- **B1（`BASE_FEATURES` 10 个）+ B2/B3（`B3_FEATURES` 16 个 = BASE + ENTRY）**：全部来自 `build_entry_panel` 内按起点构建的 `history = {event: day ≤ t 且 available ≤ t}` 计数器；`_pair_history_features` 只读 `pair_days` 与 `by_company/by_track/by_company36` 这些由 history 生成的 Counter。**没有任何一个读取 payload 标签字段、`first_target_event_date` 或全期统计。**
- **G1（12 个图特征）**：全部来自 `SnapshotSeries._build(t)/_decorate(t)/_compute(snap)`；`_history(t)` 使用同一两侧过滤，12 个月窗口为 `(t−12m, t]`；余弦相似度、邻接、特征向量中心性、聚类系数、first-touch 都在该快照内计算。**没有全期图对象、没有跨起点缓存共享。**

### 2.2 截断不变性（结构性证明，非代码阅读）

| 测试 | 规模 | 最大绝对差 | 结构不一致 |
|---|---|---|---|
| 24 个起点的 snapshot（10 类结构：weighted/portfolio/track_companies/first_touch/similarity/adjacency/eigenvector/clustering/entrants_by_track/entrant_centrality） | 24 origins | **0.0** | **0** |
| 24 个起点 × 全部候选对的 12 个 G1 特征 | **492,036 个数值** | **0.0** | 0 处 |
| 24 个起点 × 全部候选行的 16 个 B3 特征（+`feature_available_at == cutoff`） | **656,048 个数值**，候选集合差异 **0** | **0.0** | 0 处 |

即：把 t 之后的所有事件删掉，t 时点的一切特征**逐位不变**。这是"特征不含未来事件"的充分结构证据（`ORIGINAL_RESULT`）。

### 2.3 中位数/标准化是否只用训练集

`FastLogisticRegression.fit` 的 `medians/means/scales` 只由传入的 `rows` 计算；`run_spec` 只传 `eligible_training_rows`（已 purge）。数值验证（holdout 2025-10-01）：

- `model.means[j] == purged-train.mean[j]`：最大绝对差 **0.0**（16/16 特征）；
- `purged-train.mean` 与 `all-rows.mean` 的最大差 = **0.2742**（若用全样本标准化会得到后者）。
→ **训练集唯一标准化成立**（`ORIGINAL_RESULT`）。

### 2.4 跨起点"全局对象"清单（这是真正的结构性限制）

代码里只有三类对象是**全样本一次性知识**、被复用到每个历史起点：

1. `companies.aliases`（2026-10-31 快照，含被收购子公司别名）；
2. `tracks.keywords`（2026-10-31 快照的 38 赛道词表）；
3. `config/product_code_tracks.json`（1,958 条 code→track，无生效日期）。

它们是**时间不变的标签**，不会把"事件值"从未来搬到过去；但会把 **2026 年的分类学与股权边界**带进 2017 年的快照。原审计 §2/§3 已如实披露；本轮把它量化为"结构性 look-ahead（方向使图更密，利于关系假设；不可能凭空制造本不存在的正结果）"（`UNCHANGED_FINDING`）。**没有**发现全局 scaler、IDF、embedding 权重或全期图统计（`2a` 中逐条标注）。

**逐项判决：**

| 项 | 判决 | tag |
|---|---|---|
| 2a 28 个特征来源表；无标签字段/未来字段 | **PASS** | `ORIGINAL_RESULT` |
| 2b snapshot 截断不变性（492,036 值，max diff 0） | **PASS** | `ORIGINAL_RESULT` |
| 2c 面板特征截断不变性（656,048 值，max diff 0） | **PASS** | `ORIGINAL_RESULT` |
| 2d 训练集唯一中位数/标准化 | **PASS** | `ORIGINAL_RESULT` |
| 2e 静态 2026 分类学/实体映射跨起点复用 | **UNRESOLVED** | `UNCHANGED_FINDING` |

---

## 3. 检查 3：标签/测试隔离（Purged rolling origin）

### 3.1 Purge 本身是正确的

对 24 个季度起点、H=12m：

- **训练集违规 0 条**：`eligible_training_rows` 对任何训练行都满足 `cutoff + 12m ≤ t`；每个起点最大训练 cutoff 的标签窗口终点**恰好等于 t**（clearance = 0 天，最小也是 0）。
- 24 个起点彼此的标签窗口**按设计重叠**：共 **66 个起点对**重叠（每个起点与前后 3 个季度各重叠 6–9 个月），但这不影响 purge：只要训练窗口碰到测试起点就被排除。
- **物理事件级交集 = 0**（三个 holdout）：训练标签事件集合（119 / 124 / 129 个）与测试标签事件集合（22 / 27 / 26 个）交集均为 **0**。**同一物理事件不可能同时是训练标签和测试标签。**
- **14 天可用性带（本轮新增）**：窗口边界上存在 **5 个**训练正样本事件（1 + 2 + 2），其 `available_at = day+14d > t`，即"标签已实现但当时公众还看不到"。这是训练标签里的 14 天前视成分，**不涉及测试标签、也不涉及特征**，量级 5 个事件（`CORRECTED_RESULT` 级别的细化，不改变 purge 结论）。

### 3.2 36 个月休眠规则与左截断

- 休眠窗口 `(t−36m, t]` 对每个起点都**完整落在**冻结覆盖内：首个起点 2020-01-01，其 `t−36m = 2017-01-01 ≥ 2016-11-01`（`dormancy_window_inside_coverage = true`）。规则在"数据库覆盖期内"是严格可执行的。
- 但覆盖期之前的历史不存在（见 §4），所以这里的"休眠/首次"必然是**窗口内休眠、窗口内首次**（`UNCHANGED_FINDING`，与预注册 §5 一致）。

### 3.3 三个 holdout 窗口**不是**独立的（原审计措辞错误）

原审计 §6 写"Test rows at different holdout origins are disjoint by construction"，这是**错的**（同一段后文又承认标签窗口重叠）。本轮量化：

| 事实 | 数值 |
|---|---|
| holdout 起点 | 2025-04-01 / 2025-07-01 / 2025-10-01（H=12m） |
| 两两标签窗口重叠 | **9 / 6 / 9 个月**；三者共同重叠 **2025-10-01 … 2026-04-01（6 个月）** |
| pooled 行数 | 5,159 |
| 不同 (company,track) 对 | **1,729**；其中 **1,721（99.5%）出现在 >1 个 holdout**（最多 3 次） |
| pooled 正样本行 | 67 |
| 不同 (pair, first-target-date) 身份 | **32**（35 行为重复计数） |
| holdout 窗口并集内**真正作为正标签**的物理事件 | **37 个**，被三个窗口计了 **75 次**；**25 个事件被 >1 个窗口计入**（12 个 1 次 / 12 个 2 次 / 13 个 3 次） |
| 参考：三个窗口内全部合格事件（不要求是候选对的标签） | 475 个 |

**含义：** "pooled n=5,159 / pooled 67 positives"不是 5,159 条独立观测，而是**同一批 ~1.7k 个企业-赛道横截面被三个高度重叠的窗口重复评分**；67 条正样本行只对应 **37 个物理正事件**、被计 75 次。按企业聚类的 bootstrap 只能部分吸收这种相关性。**单窗口结果（每窗 25–27 个正样本）才是干净的推断单元**；pooled 只应作为描述性汇总。这是**统计有效性问题，不是未来信息泄漏**（`CORRECTED_RESULT`）。

**逐项判决：**

| 项 | 判决 | tag |
|---|---|---|
| 3a 24 起点 purge（0 违规、clearance 0 天；66 对窗口按设计重叠） | **PASS** | `ORIGINAL_RESULT` |
| 3b 物理事件级训练/测试标签交集 = 0（边界 14 天带 5 个事件） | **PASS** | `ORIGINAL_RESULT` |
| 3c 三个 holdout 窗口"disjoint by construction" | **FAIL**（应更正为高度重叠） | `CORRECTED_RESULT` |
---

## 4. 检查 4：左截断 / 右删失（Left truncation & right censoring）

### 4.1 覆盖边界与窗口完整性

| 指标 | 数值 |
|---|---|
| 全部事件覆盖 | 2016-11-01 … 2026-10-18 |
| material 事件覆盖 | 2016-11-01 … 2026-10-18 |
| 进入图的 usable 事件覆盖 | 2016-11-01 … 2026-10-16 |
| 2016-11 / 12 月 material 事件数 | 257 / 266（与 2017 年月均 ~240 同量级，**不是部分摄取**） |
| 与上游产品库同窗口事件数对比 | 上游窗口内 510k/PMA = 55,090；冻结库 = 55,090；**缺失 0、多余 0**（`window_ids_missing_from_frozen=0`、`frozen_ids_not_in_live=0`） |

即：冻结窗口内部**没有**被截断，2016-11-01 是一个**硬设计切口**。

### 4.2 左截断的量级（用上游完整 openFDA lane 作参照）

> 参照对象 `D:\DEPPSKK\medradar\data\medradar.sqlite` 是**非冻结、可变**的上游产品库（本次记录其路径/size/hash 于 JSON），仅用于度量"冻结窗口之外还有多少历史"。

| 指标 | 数值 |
|---|---|
| 上游 510k/PMA 总行数（可回溯到 1976） | **233,838** |
| 其中 2016-11-01 之前 | **178,748（76.4%）** |
| 冻结库保留 | 55,090（窗口内 100%） |
| 冻结窗口内最终被观测到的 322 个 pair 中，**窗口前已有活动** | **268 / 322 = 83.2%** |
| 有窗口前活动的企业 / 赛道 | **50 / 51** 家企业、**38 / 38** 个赛道 |
| 首次观测落在覆盖前 6 个月 / 12 个月内的 pair | **94 / 149（46.3%）** |
| 首个起点前已经活动过的最终 pair | **230 / 322 = 71.43%**（**独立重算 = 预注册的 71.4%**） |
| 企业首次出现于前 6 个月 | 42 / 51；赛道 36 / 38 |
| 三个 holdout 快照中"first_touch 落在覆盖前 12 个月"的 pair 占比 | **49.3% / 49.0% / 48.5%** |

### 4.3 三个 holdout 窗口具体受什么影响

- **它们的标签窗口本身不受左截断影响**（2025-04→2026-10 远离 2016-11 边界）。
- 但**正样本语义**受影响：holdout 的 **32 个不同正样本 pair 中 20 个（62.5%）在 2016-11 之前就已经活动过**——这些是"休眠后的再进入"，不是企业历史首次进入。
- **图特征的时间年龄被边界截断**：holdout 快照里约 **49%** 的 pair 的 first_touch 落在覆盖头 12 个月（它们的真实首次更早、不可观测），因此 `rd_pair_active_years`/`g_twoentry*` 之类的时间量在结构上被压缩。

### 4.4 右删失

- 三个 holdout 标签窗口终点 2026-04-01 / 2026-07-01 / **2026-10-01**，距覆盖终点分别 **197 / 106 / 14 天**；冻结数据在结构上覆盖它们（最后窗口 2026-10-01 早于 coverage_end 2026-10-15）。
- 2026 年尾部月事件数（vs 2023–25 同月均值）：07 月 292（1.09×）、08 月 259（0.90×）、09 月 326（1.19×）、10 月 140（0.45×，但 10 月只有 18 天数据且最后一个标签窗口在 10-01 就关闭，故不影响标签）。
- **无法验证**：上游 openFDA 在抓取时（2026-11-01）是否已发布 2026-09/10 的全部决定；若上游本身滞后，最后一个 holdout 窗口会出现**假阴性**。冻结库 `meta` 表为空（0 行），没有任何来源行数/抓取完成度元数据可供核对（`UNRESOLVED_LIMITATION`）。

**逐项判决：**

| 项 | 判决 | tag |
|---|---|---|
| 4a 覆盖边界清晰；窗口内完整（与上游 0 缺失）；2016-11 是硬切口 | **PASS** | `ORIGINAL_RESULT` |
| 4b 左截断严重（83.2% pair、76.4% lane 在窗口之外；holdout 正样本 62.5% 是再进入） | **UNRESOLVED** | `UNCHANGED_FINDING` |
| 4c 右删失：内部余量 14 天，上游发布完整度不可验证 | **UNRESOLVED** | `UNRESOLVED_LIMITATION` |

---

## 5. 检查 5：历史代理 —— 图特征是否只是历史活动的重述（科学关键）

### 5.1 审计工具的保真度（先证明"我在看的就是实验的那批行/特征"）

- 用审计脚本独立重建 H=4q qualifying panel：**41,003 行 / 418 正样本 / 24 起点 / holdout 5,159 行 / 67 正样本**，与归档一致。
- 用 `SnapshotSeries` 重建 G1 特征、重新拟合 B2 与 G1 逻辑回归，与 `artifacts/predictions_H4q.json.gz` 的逐行概率比较：**最大绝对差 0.0（B2）与 1.4e-16（G1）**。→ 下文的共享方差与消融都是在**实验自己的行/特征**上算出。

### 5.2 归档 AP 的重算（`ORIGINAL_RESULT`）

| 模型 | pooled holdout AP |
|---|---|
| 常数训练流行率 | 0.0134 |
| 企业基率（B0） | 0.0380 |
| 赛道基率（B0） | 0.0339 |
| pair 基率（B0） | 0.0406 |
| B1（10 历史特征） | **0.0690** |
| **B2/B3（16 历史特征）** | **0.0751** |
| **G1（16 历史 + 12 图）** | **0.0690** |

### 5.3 共享方差：每个 G1 特征被 16 个 B3 特征解释多少（41,003 行）

| G1 特征 | R²（pooled） | R²（起点内去均值） | max\|Pearson\|（对应特征） | max\|Spearman\| |
|---|---:|---:|---|---:|
| `g_twohop_reach` | **0.727** | 0.733 | 0.849（`rd_company_active_tracks_12m`） | **0.891** |
| `g_company_eigenvector` | **0.623** | 0.624 | 0.779（`rd_company_active_tracks_12m`） | **0.870** |
| `g_coentry_count_12m` | 0.259 | 0.266 | 0.445（`rd_track_active_companies_12m`） | 0.384 |
| `g_track_entrant_centrality` | 0.248 | 0.251 | 0.436（`rd_track_active_companies_12m`） | 0.380 |
| `g_coentry_decay` | 0.244 | 0.248 | 0.432（`rd_track_active_companies_12m`） | 0.380 |
| `g_similarity_to_track_max` | 0.193 | 0.193 | 0.353（`rd_track_active_companies_12m`） | 0.464 |
| `g_track_cooccurrence_pull` | 0.147 | 0.148 | 0.355（`rd_track_active_companies_12m`） | 0.458 |
| `g_similarity_to_track_incumbents` | 0.070 | 0.070 | 0.224（`rd_company_active_tracks_12m`） | 0.415 |
| `g_twohop_activity_decay` | 0.050 | 0.049 | 0.193（`rd_company_count_12m`） | 0.505 |
| `g_coentry_similarity_weighted` | 0.040 | 0.040 | 0.153（`rd_track_active_companies_12m`） | 0.179 |
| `g_max_entrant_similarity` | 0.038 | 0.038 | 0.148（`rd_track_active_companies_12m`） | 0.179 |
| `g_company_clustering` | 0.012 | 0.011 | 0.089（`rd_company_active_tracks_delta`） | 0.044 |

- 块平均 R² = **0.221**（中位 0.170；起点内 0.223）；**2 个特征 R² > 0.5**、3 个 > 0.25。
- 原 `DATA_FEASIBILITY.md` §7 的 max|Pearson| 列（0.849 / 0.779 / 0.445 / 0.436 / 0.432 …）**被独立逐项重算复现**（`ORIGINAL_RESULT`）。
- 但**秩相关**显示：两个"结构性"图特征与"企业活跃赛道数"的 Spearman 高达 **0.891 / 0.870**——它们基本是**企业活动量的单调重述**。

### 5.4 消融：图特征是否有增量信息（purged，3 个 holdout，pooled AP）

| 特征集 | pooled AP | 说明 |
|---|---:|---|
| B3（16 历史特征） | **0.07509** | 强非图基线 |
| B3 + G1（=实验的 G1） | **0.06900** | **Δ = −0.00609**（加图反而更差） |
| B3 + 对 B3 残差化后的 G1 | **0.07099** | 仍低于 B3（−0.0041） |
| 只用 G1（12 图特征） | **0.01964** | 接近"4 个历史计数"模型 |
| 只用 4 个历史计数（公司 12m、公司 36m、赛道 12m、公司活跃赛道 12m） | **0.02282** | 目标本身只有很弱的持续性 |
| 原始随机化臂（**已证有缺陷**，数字仅作历史对照） | 均值 **0.07461**（min 0.06919，max 0.08198） | 40 / 40 次 ≥ 真实图 0.06900 |
| 修正后 N1（严格保度零模型） | 0.069730 / **0.075508** / 0.082003 | **40 / 40 ≥ 真实**，p(真实偏低)=1/41=0.0244 |
| 修正后 N2（保度+赛道活动量+逐赛道时间） | 0.069160 / **0.075184** / 0.083421 | 40 / 40 ≥ 真实，p=0.0244 |

> **CORRECTED in `S-028-CORRECTION-1`（本审计收尾时同步）**：原始 Phase 0–3 随机化臂自称的"保度随机图"标签**不成立**。
> Phase 0–3 的随机化实现经独立审查判定不具备其声明的性质（72/72 次不变量检查失败：度序列漂移、
> 边权塌缩、100% 随机边被当作"新进入"而观察臂只有 10.5%；见 `RANDOMISATION_DEFECT_ANALYSIS.md`）。
> 用有效零模型重跑后的结论见 `G2_CORRECTION_RESULTS.md`：H4q 方向仍为负（40/40，p=1/41），
> **但集中于 2025-04-01 单窗口**（40/40 vs 另两窗 23/40、31/40）；H2q **无差异**（N1 16/40、N2 20/40）。
> 因此本表中"40/40"不能作为方法证据；H2 的正确表述是"未获支持 + 一个窗口特异的探索性反向尾部"。
> 本轮据此明确：**不得把 H4q 的 40/40 解读为"真实图有害"**——反转只出现在一个窗口、没有机制被建立，且 H2q 完全没有反转；正确表述仅是"关系特异性未获支持"。

- 真实图 AP 0.0690 低于原始（有缺陷）随机臂的最小值 0.0692；在**修正后**的零模型下同样低于全部 40 次抽样（p=1/41），但该反差集中于单一窗口（见上）。
- H1 同样不成立：ΔAP(G1−B2) = −0.0061，p_one_sided = 0.89，企业聚类 95% CI 含 0（[−0.0222, 0.0045]），且低于**pooled 单检验** MDE(80%) = 0.0194。注意：预注册合取判定规则的规则级 MDE 是 0.0374（基线 49.8%），该规则在 0.0194 处功效仅 16.3%——详见 `STATISTICAL_REVIEW_CORRECTION.md`。

### 5.5 回答"科学关键问题"

**图特征在多大程度上只是历史的重述？**

1. **作为构造，100% 来自历史事件**（§2.2 已证明它们只由 `≤t` 的事件算出）；
2. **作为统计量，两个"最像结构"的特征（twohop_reach、eigenvector）可被 B3 历史特征解释 62–73% 的方差、秩相关 0.87–0.89**——接近"活动量重述"；
3. **作为预测信息，剩余部分没有价值**：G1-only AP 0.0196 ≈ 4-count 模型 0.0228 « B3 0.0751；加图后 pooled AP 下降；残差化后仍下降；修正后的保度零模型同样不劣于真实图（H4q 40/40，p=1/41，但集中于单窗口；H2q 无差异——见 `G2_CORRECTION_RESULTS.md`）。
4. 目标本身（"未来四季度首次合格活动"）**只有弱持续性**：B2 AP 0.0751 对基础率 0.0130 约 5.8× lift，但绝对水平仍低；公司/赛道/pair 基率的 AP 都在 0.034–0.041。因此"图只是历史重述"与"历史本身也不强"两者同时成立。

**判决：** 5c **FAIL**（"图特征携带独立信息"不成立）→ 记为 `CORRECTED_RESULT`（本轮把原研究自己的警告升级为定量结论）。

---

## 6. 检查 6：映射不可复现性（Mapping reproducibility）

### 6.1 规则级可复现性：**原结论被推翻**

在冻结库自带的 `companies` / `tracks` 表 + 仓库 `config/product_code_tracks.json` + 生产代码（`medradar.config.CompanyRegistry`、`medradar.collect_device._event_track` / `_match_candidates`）下复算：

| 映射 | 复算一致 | 说明 |
|---|---|---|
| 公司 `company_key` | **55,090 / 55,090 = 100.00%** | 512 个 (applicant, company) 组合：**500** 个由记录在案的 alias 命中，**12** 个由 `companies` 表自带的 `key`/`name_en` 列命中；**0** 个需要模糊匹配 |
| 赛道 `track_id` | **55,090 / 55,090 = 100.00%** | 路由：`product_code` 35,693；无 code 的 19,397 条中 keyword 命中 **1,772**、词干化 token-set 命中 **317**、歧义/无命中留空 17,308 |

- 原报告称"8 个 (applicant, company_key) 组合在不含任何别名时匹配成功 → 存在未记录匹配路径"：本轮证明这些组合命中的是 `companies` 表**自己的 `key`/`name_en` 列**（如 `Bd`→`bd`、`Canon Medical Systems Corporation`→`canon_medical`），并非未记录规则；`CompanyRegistry.resolve` 里确有 0.82 阈值的 token-Jaccard 模糊回退（原审计 §5 称"无模糊匹配"不准确），但在本冻结数据上**一次也没用到**。
- 原报告称"2,089 条赛道赋值中 325 条连关键词回退都复现不出"：本轮用生产函数 `_event_track` 复算，2,089 = **1,772 keyword + 317 stemmed token-set**；原复算只实现了 keyword 路径、漏掉了 `_match_candidates` 的词干 token-set 回退，才产生"325 条不可复现"。
- 结论：**映射是"代码 + 配置"的确定性函数，不是不可复现的黑箱**（`INVALIDATED_FINDING`）。

### 6.2 但映射**没有**版本化（这部分成立，且要更正措辞）

| 证据 | 数值/事实 |
|---|---|
| `companies_device.json` / `tracks_device.json` 的时间信息 | 只有一个 `updated = 2026-10-31`；每条 alias/keyword **无生效日期** |
| `config/product_code_tracks.json` | 1,958 条，**无日期、无置信度** |
| 冻结库 `product_codes` 表 | **0 行** → 仅凭冻结库无法重建 `track_id` |
| `company_identifiers`（唯一带时间字段的表） | 34 行；`valid_from` / `valid_to` **全为 NULL**；`available_at` 只有 1 个快照值（2026-11-01T22:48:06Z） |
| 同一 event_id 在冻结库 vs 上游产品库 | `track_id` 一致 **55,090/55,090**；`company_key` 有 **30 / 55,090（0.05%）不一致**（上游把 GE OEC/GE Hualun/GE Hangwei 归到 `ge_healthcare`、Cook Biotech 归到 `cook_medical`，冻结库仍为 NULL）→ 映射是可变动快照 |
| 用仓库当前 50 赛道配置替代冻结时点的 38 赛道 | 55,090 中 **116 条**不一致（114 条"冻结为 NULL、现配置给出赛道"，2 条改类），一致率 99.79% |

### 6.3 "能否重建 3,833 / 31,802 覆盖？"

- **数据集层面：能。** 3,833 = material 31,802 中同时有 `company_key` 与 `track_id` 的行数；逐项独立重算：company 5,489（17.26%）、track 18,889（59.40%）、both **3,833（12.05%）** —— 与 `DATA_FEASIBILITY.md` 完全一致（`ORIGINAL_RESULT`）。
- **规则层面：能**（见 6.1，需仓库代码 + 配置；100%）。
- **仅凭冻结库：不能**（`product_codes` 空表；且没有逐行 `matched_alias`/`match_confidence` 列）。
- **时间版本层面：不能**（无生效日期映射；同一冻结行在今天上游已有 30 条不同归属）。

**逐项判决：**

| 项 | 判决 | tag |
|---|---|---|
| 6a 映射规则可复现（公司 100%、赛道 100%；"8/325"残差可用已记录规则解释） | **PASS** | `INVALIDATED_FINDING` |
| 6b 映射版本化（无生效日期、product_codes 空、30 条漂移、116 条配置漂移） | **FAIL** | `CORRECTED_RESULT` |
| 6c 3,833/31,802 覆盖率算术与可重建性 | **PASS** | `ORIGINAL_RESULT` |

---

## 7. 原审计证明/未证明什么；本轮新增结论

### 7.1 原审计**证明**了的（本轮独立确认）

1. 冻结基准可复现（41,003/503/24；pooled AP 0.101060、persistence 0.044614；三窗 AP 0.137085/0.095027/0.100476）。
2. 特征/快照在代码路径上只使用 `day ≤ t and available ≤ t`（本轮进一步以**逐位不变的截断实验**证明，而不只是读代码）。
3. Purge 正确：训练标签窗口在测试起点前关闭，物理事件级交集为 0。
4. 知识时钟是 `decision_date + 14d` 代理，不是实测（`first_seen_at`/`as_of` 只有 1 个值）。
5. 分类学/实体映射是 2026 年静态快照，存在结构性 look-ahead。
6. 3,833/31,802 覆盖算术正确。

### 7.2 原审计**没有证明**、或**说错**的（本轮更正）

| # | 原断言 | 本轮结论 | tag |
|---|---|---|---|
| 1 | 复现基准即说明"无未来泄漏" | 复现只证明保真度；无泄漏由本次截断不变性/事件级 purge 证明 | `CORRECTED_RESULT`（方法论） |
| 2 | "三个 holdout 起点 disjoint by construction" | 错：窗口重叠 6–9 个月，1,721/1,729 pair 跨窗口重复，67 条正样本行只对应 37 个物理事件、被计 75 次 | `CORRECTED_RESULT` |
| 3 | 公司/赛道映射"不可由交付工件复现"（8 个无别名组合、325 条无 keyword 的赛道赋值） | 错：规则级 100% 可复现（key/name_en 列 + 词干 token-set 回退） | `INVALIDATED_FINDING` |
| 4 | "无模糊匹配" | `CompanyRegistry.resolve` 含 0.82 token-Jaccard 回退（本数据未触发）；映射并非纯别名 | `CORRECTED_RESULT` |
| 5 | 图特征"最大 |r| 0.849/0.779，可能只是重述" | 确认并升级：R² 0.727/0.623，秩相关 0.891/0.870；消融与修正后零模型均显示**无增量信息**（原始随机化臂已证有缺陷，数字只作历史对照） | `CORRECTED_RESULT` |

### 7.3 最强的剩余泄漏/有效性风险（按对本研究结论的威胁排序）

1. **左截断（最大威胁，但方向不利于"首次进入"解释）**：上游 76.4% 的 lane 历史在冻结窗口之外；83.2% 的最终 pair 在窗口前已活跃；holdout 正样本 62.5% 是"再进入"。它不制造未来信息，但使标签语义（"首次"）系统性偏斜。
2. **右删失不可验证（唯一可能制造"假阴性"的未知）**：最后 holdout 标签窗口只剩 14 天余量；上游 openFDA 发布完整度无冻结元数据可核（`meta` 表 0 行）。
3. **知识时钟 14 天假设（唯一可能制造"未来信息"的未知）**：若真实发布延迟 > 14 天，泄漏带平均占 lane 0.86%–8.36%；无法用冻结数据排除。
4. **静态 2026 分类学/实体 look-ahead**：使图更密、更稳定，方向**利于**关系假设；但本研究没有观察到正结果（G1 < B2；有效零模型不劣于真实图——H4q 40/40 但只集中于一个窗口、H2q 无反转），因此它不能解释任何"阳性发现"。
5. **holdout 窗口重叠**：是推断有效性问题（pooled n 被夸大），不是泄漏；已给出更干净的"单窗口"口径。

### 7.4 剩余 `UNRESOLVED_LIMITATION` 与"能定案的证据"

| # | 未决限制 | 为什么本轮无法判定 | 什么证据能定案 |
|---|---|---|---|
| U1 | `available_at` 的真实性（14 天是否足够） | 无任何实测 first-observation/publication 时间；payload 只有 `date_received` | 真实 point-in-time 存档（Wayback/regulations.gov 快照的首次出现日）或前瞻采集的 `first_seen_at`（lag ≤ 1 天） |
| U2 | 右删失 / 上游 2026-09…10 完整性 | 冻结库 `meta` 空；上游库可变且无抓取完成度 | 对 2026-08…10 独立重新抓取 openFDA 并逐 event_id 比对；或冻结时记录 `table_row_counts` + 抓取窗口 |
| U3 | 分类学/实体映射的时点正确性 | 所有映射无生效日期；只有 1 个 `updated` | 按生效日期版本化的 product_code→track 与 alias→company 表（含 `valid_from/valid_to`），并给 2016–2026 每年重建一次映射做敏感性 |
| U4 | 左截断（窗口前 76.4% 历史缺席） | 冻结输入被硬切在 2016-11-01 | 把冻结 lane 扩展到上游完整 510k/PMA 历史（1976 起），或改用带左删失/风险集校正的估计（如自 2016 起的左截断生存模型） |
| U5 | 三个 holdout 窗口重叠导致的 pooled 独立性 | 协议固定"最后 3 个可评估起点"且 H=12m，窗口必然重叠 | 以单窗口结论为主（预注册本已要求分窗报告），或改用不重叠 holdout（例如以 12 个月为间隔取 3 个起点） |
| U6 | 逐行映射证据缺失 | `events` 无 `matched_alias`/`match_confidence`/`mapping_version` 列 | 在 `events` 写入 `matched_alias`、`match_confidence`、`mapping_version`（如 `2026-10-31`）并冻结 |

**严格无法验证（UNVERIFIABLE）的清单：** ① 真实公开发布时间；② 冻结时点上游是否已完整收录 2026-09/10 决定；③ 2016-11 之前的真实"首次进入"；④ 任何历史时点的分类学/股权边界。原因统一为：这些信息**不存在于冻结工件中**，而本轮禁止改动/扩展冻结输入。

---

## 8. 逐项判决总表

| 检查 | 项 | 判决 | tag | 关键数字 |
|---|---|---|---|---|
| C0 | 冻结基准复现 | PASS | ORIGINAL_RESULT | 41,003/503/24；pooled AP 0.101060（目标 0.101060） |
| C1 | 知识时钟内部一致 | PASS | ORIGINAL_RESULT | +14d 55,090/55,090；缺失/负滞后 0 |
| C1 | 时钟是估计代理 | UNRESOLVED | UNCHANGED_FINDING | 1 个 first_seen；date_received 中位早 86 天 |
| C1 | 泄漏方向/量级 | PASS | UNCHANGED_FINDING | 盲区 0.73%；假想泄漏带 0.86–8.36% |
| C2 | 28 特征来源表 | PASS | ORIGINAL_RESULT | 无标签/未来字段 |
| C2 | 快照截断不变性 | PASS | ORIGINAL_RESULT | 492,036 值 max diff 0.0 |
| C2 | 面板特征截断不变性 | PASS | ORIGINAL_RESULT | 656,048 值 max diff 0.0 |
| C2 | 训练集唯一标准化 | PASS | ORIGINAL_RESULT | model means = train means；train vs all mean gap 0.274 |
| C2 | 静态 2026 分类学/实体复用 | UNRESOLVED | UNCHANGED_FINDING | 3 个全局静态映射 |
| C3 | 24 起点 purge | PASS | ORIGINAL_RESULT | 违规 0；clearance 0 天 |
| C3 | 物理事件级标签隔离 | PASS | ORIGINAL_RESULT | 交集 0（119/124/129 vs 22/27/26）；边界带 5 事件 |
| C3 | holdout 窗口独立性 | **FAIL** | CORRECTED_RESULT | 1,721/1,729 pair 重复；67 正样本行 = 37 个物理事件（计 75 次） |
| C4 | 覆盖边界/窗口完整 | PASS | ORIGINAL_RESULT | 0 缺失；55,090/55,090 与上游一致 |
| C4 | 左截断 | UNRESOLVED | UNCHANGED_FINDING | 窗口外 76.4%；83.2% pair 有窗口前活动；holdout 正样本 62.5% 为再进入 |
| C4 | 右删失 | UNRESOLVED | UNRESOLVED_LIMITATION | 最后窗口余量 14 天；meta 0 行 |
| C5 | 审计工具保真 | PASS | ORIGINAL_RESULT | 概率差 0.0 / 1.4e-16 |
| C5 | 归档 AP 重算 | PASS | ORIGINAL_RESULT | B1 0.0690 / B2 0.0751 / G1 0.0690 |
| C5 | 图=历史重述 / 无增量 | **FAIL** | CORRECTED_RESULT | 平均 R² 0.221；R²_max 0.727；ΔAP −0.0061；修正后零模型下真实图仍 ≤ 全部抽样（H4q 40/40，p=1/41，单窗口驱动；H2q 无差异） |
| C6 | 映射规则可复现 | PASS | INVALIDATED_FINDING | 公司 55,090/55,090；赛道 55,090/55,090 |
| C6 | 映射版本化 | **FAIL** | CORRECTED_RESULT | 无生效日期；product_codes 0 行；30 条漂移；116 条配置漂移 |
| C6 | 覆盖算术/可重建 | PASS | ORIGINAL_RESULT | 3,833/31,802 = 12.05% |

**总计：PASS 14 / FAIL 3 / UNRESOLVED 4**；tag：`ORIGINAL_RESULT` 12、`UNCHANGED_FINDING` 4、`CORRECTED_RESULT` 3、`UNRESOLVED_LIMITATION` 1、`INVALIDATED_FINDING` 1。

---

## 9. 复现

```bash
cd D:/DEPPSKK/medradar/research/studies/graph_early_signal_s028
python code/audit_23_leakage_correction.py        # ~61 s, deterministic
# 输出: artifacts/correction_round_1/leakage_audit.json
```

脚本在**任何**计算之前用 `sha256_file` 校验冻结 DB（`dd241bfe…1eeeb71e0d`，289,443,840 B），不匹配则拒绝运行；结束再校验一次并写入 `frozen_db.verified_after`。脚本只读打开数据库，不写任何原始工件；它记录的输入哈希（`s028_lib.py`、`s028_experiment.py`、`config/*.json`、上游产品库）都在 JSON 的 `inputs` 字段中。

若 `artifacts/correction_round_1/g2_corrected_{H4q,H2q}_{N1,N2}.json` 存在，脚本会**只读**汇总修正零模型的抽样范围、逐窗口"≥真实"计数与反向尾 p，并写入 JSON 的 `5c_historical_restatement.numbers.g2_corrected_null_models`；若不存在则如实标注为 absent。因此 §5.4 中 N1/N2 的计数可由本脚本重新生成，而原始 Phase 0–3 随机化臂始终被标为 `DEFECTIVE_NOT_DEGREE_PRESERVING`、仅作历史对照（依据 `RANDOMISATION_DEFECT_ANALYSIS.md` 的 72/72 不变量失败）。

*本文档不修改原 `TEMPORAL_LEAKAGE_AUDIT.md`；两者的差异以本文为准。*
