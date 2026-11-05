# S-028 逐例假阳性失败分析（Correction Round 1 · audit 22 / task-4）

> **本文件完成的是原研究自己承认未做的工作。** `LIMITATIONS.md` L14 / `NEGATIVE_RESULTS.md` B-NEXT-2 明确写着“逐例失败分析未完成 / 叙事性逐例复核未完成，论文中不得声称已完成”。本审计把它做完，并给出机器可读证据。
>
> - 代码：`code/audit_22_false_positives.py`（确定性、只读；重建特征矩阵并对 stored probs 做 1e-9 级 parity 校验）
> - 机器可读结果：`artifacts/correction_round_1/false_positive_cases.json`（90 例逐例证据 + 聚合分布 + 选择规则）
> - 输入：frozen DB `sha256=dd241bfec138d797…`（289,443,840 bytes，运行前 size+SHA-256 校验）；`artifacts/predictions_H4q.json.gz`；`config/product_code_tracks.json`
> - 时间标签：`ORIGINAL_RESULT` / `CORRECTED_RESULT` / `UNCHANGED_FINDING` / `INVALIDATED_FINDING` / `UNRESOLVED_LIMITATION`

---

## 0. 结论摘要

1. **选择并复核了 90 个 top 假阳性**：H=4q 三个 holdout origin 各取 `k=30`（规则见 §1），全部 90 例都有原始监管记录可查，**UNVERIFIABLE = 0**。
2. **类别分布**：MODEL_FAILURE 53（58.89%）、LABEL_FAILURE 24（26.67%）、DATA_FAILURE 1（1.11%）、RELATIONAL_CONSTRUCT_FAILURE 12（13.33%）、UNVERIFIABLE 0（0%）。
3. **83.3%（75/90）的 top FP 在 B2（强非图基线）里同样进入 top-k FP 集**（每个窗口 25/30）；只有 15/90 是 graph-specific。也就是说：顶排假阳性的主体不是“图特征带来的错误”。[`CORRECTED_RESULT`]
4. **26.7%（24/90）是标签口径假阳性**：同一 (企业, 赛道) 在窗口内有 555 条非合格申报（PMA supplement / Special 510(k) 等），按预注册标签规则记为 0。**其中 8 例是维护性申报数百条的成熟 PMA 家族**（如 Boston Scientific 心脏节律：窗口内 97 条 supplement）——它们不是“新进入”，而是“已在场、只做维护”。[`CORRECTED_RESULT`]
5. **只有 1 例是数据失败**（BD/medical_ai：窗口前 11 天的 Traditional 510(k) 被 `available_at=event_date+14d` 的估计知识时钟挡在模型视野之外，使“休眠对”前提失真）。[`CORRECTED_RESULT`]
6. **12/90 是关系构造失败**：graph-specific，图增量 Δlogit 平均 +0.30；其中 3 例由与历史计数近乎重述的 `g_twohop_reach`/`g_company_eigenvector` 驱动（我们复现 r=0.84/0.80），9 例由“相似度 / 同批进入”的类比关系驱动——类比没有兑现为进入。
7. **数据归属检查几乎全部通过**：实体换键 0 例、歧义申请人字符串 0 例、赛道映射冲突 0 例、左截断/右删失影响 0 例；但 42/90 例的企业历史包含已验证的并购子公司别名（如 bd 45.1% 事件来自 Bard/CareFusion），28/90 例的先验产品码不在随包 config 映射表内——这些是**可靠性 caveat**，不是这些 FP 的直接原因。[`UNCHANGED_FINDING` + `UNRESOLVED_LIMITATION`]
8. **对 AP −0.006 的含义**：主结果（H1 null，ΔAP=-0.00609，CI [-0.02219, +0.00450]，MDE=0.0194）不变 [`UNCHANGED_FINDING`]；逐例复核进一步说明这个损失主要发生在**两个近乎相同的排序器之间**、且顶排区域被标签口径伪影污染——**不能**把它读成“图结构有害”。把它读成“图信号错误”的解读被否定 [`INVALIDATED_FINDING`]。

---

## 1. 选择规则（固定，先于逐例复核）

```
for each H=4q holdout origin t in {2025-04-01, 2025-07-01, 2025-10-01}:
    rank all rows by G1_graph predicted probability (descending, stable)
    k = max(30, ceil(0.01 * n_origin))
    select the first k rows with label == 0
    # identical rule applied to B2_frozen_spec16 for the comparison set
    graph_specific := selected row is NOT in the B2 top-k label==0 set
```

n_origin = 1722 / 1721 / 1716，1% = 17.22 / 17.21 / 17.16，因此 `k=30` 在三个窗口都由下限决定；共 **90** 例。该规则在看任何逐例内容之前固定，脚本中写死为常量。

| origin | n rows | k | 正样本 | 第 k 个 FP 的 G1 全表名次 | 被选 FP 的 G1 概率下界 | 排在其前面的正样本 | B2 top-k FP 重叠 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2025-04-01 | 1722 | 30 | 20 | 33 | 0.13814 | 3 | 25/30 |
| 2025-07-01 | 1721 | 30 | 23 | 32 | 0.13430 | 2 | 25/30 |
| 2025-10-01 | 1716 | 30 | 24 | 34 | 0.11233 | 4 | 25/30 |

边界说明：被选 FP 位于全表第 1–34 名，正样本与其交错（每窗口只有 2–4 个正样本排在所选 FP 之下/之上），这正是基础率 1.02% 下“排序器只有弱分辨力”的直接体现（对应 N6）。

---

## 2. 方法：证据链、分数分解、类别定义

### 2.1 逐例证据（全部来自 frozen DB 原始行）

对每个案例记录：

- **企业**：`company_key`、名称/别名、`applicant_raw` 变体及其事件数、库内首末事件；
- **赛道**：`track_id`、英文/中文名、category、关键词、库内事件数与企业数、该对的先验产品码与器械名样例；
- **原始事件**：窗口前/窗口内/窗口后的 510(k)/PMA 行，逐条给出 `event_id`、`event_date`、`available_at`、`clearance_type`、`supplement_type/supplement_number`、`device_name`、`applicant_raw`；
- **真实未来**：该 (企业,赛道) 在 4 个季度内是否出现合格/非合格申报；企业在窗口内其他赛道的申报；窗口后才出现的合格申报；
- **四项可靠性检查**：实体归属（同申请人字符串是否换 key、是否有歧义串、并购别名 hindsight）、赛道归属（产品码→赛道是否可由随包 config 复现、分类法是否为单一无日期版本）、DB 左截断（36 个月休眠窗是否完全被库覆盖）、右删失（标签窗是否超出库覆盖）；
- **图/历史特征**：该行的 16 个 B3 与 12 个 g_* 特征值，以及逐特征对 logit 的贡献。

研究通道（material 510(k)+原始 PMA）与原始库（55,090 条 510(k)/PMA 全部行）分开：标签只由 material 行构造，但 LABEL_FAILURE 的判定使用**全部原始行**（含 23k PMA supplements），因为“窗口内是否真有申报”是原始事实问题。

### 2.2 可复现性：stored probs 的 bit 级 parity

脚本用 frozen DB 重建 H=4q panel（41003 行 / 418 正样本 / base rate 0.010194）、重建 `SnapshotSeries` 图快照、重新拟合 G1 与 B2，再与 `predictions_H4q.json.gz` 中的逐行概率比较：

| origin | n_test | G1 max\|Δp\| | B2 max\|Δp\| |
|---|---:|---:|---:|
| 2025-04-01 | 1722 | 5.6e-17 | 0.0e+00 |
| 2025-07-01 | 1721 | 1.4e-16 | 0.0e+00 |
| 2025-10-01 | 1716 | 1.1e-16 | 0.0e+00 |

三个窗口的 G1 最大偏差 1.4e-16（parity 阈值 1e-9；B2 偏差 ≤1e-16）——**重建的特征矩阵与实验一致**。因此下面的分数分解（权重 × 标准化特征值）是对该模型实际打分的精确分解，不是近似。

### 2.3 类别定义与固定优先级

每例只归入一个 primary category，按以下顺序判定（`build_case_record` 内固定顺序判定）：

1. **LABEL_FAILURE** — 窗口内存在同一 (company_key, track_id) 的原始申报，但它是非合格事件：Special/Abbreviated/Direct/Dual/Post-NSE 510(k)，或 PMA supplement（含 Panel Track）。标签规则因此记为 0。
2. **DATA_FAILURE** — 标签被数据问题遮蔽/扭曲：实体换 key、赛道映射冲突、**估计知识时钟（+14 天）把窗口前 material 申报挡在模型视野外**、研究通道看不到的对前提、或 DB 截断/删失。
3. **RELATIONAL_CONSTRUCT_FAILURE** — 无 label/data 伪影，且该行是 graph-specific（B2 不会选它）且图增量 Δlogit>0：假阳性由图的“关系性”特征造成。
4. **MODEL_FAILURE** — 与 B2 共享 top-k FP 的其余情况：分数由公司/赛道活动计数解释，且无 label/data/relational 伪影。
5. **UNVERIFIABLE** — 冻结库中没有任何可核查证据。

“重述型图特征”的判定阈值：图特征与任一 B3 历史特征的 |Pearson r| ≥ 0.70（在 5,159 个 holdout 行上计算）。结果：`g_twohop_reach` r=0.837（对应 `rd_company_active_tracks_12m`）、`g_company_eigenvector` r=0.795，复现 N4 的 0.849/0.779（口径差异为 holdout 池 vs 全 panel）。

---

## 3. 总体分布

### 3.1 类别分布（90 例）

| 类别 | 例数 | 占比 | 每窗（04/07/10） | 平均 G1 | 平均 B2 | 平均 Δlogit |
|---|---:|---:|---|---:|---:|---:|
| MODEL_FAILURE | 53 | 58.89% | 15/18/20 | 0.1851 | 0.1778 | +0.050 |
| LABEL_FAILURE | 24 | 26.67% | 10/7/7 | 0.1766 | 0.1633 | +0.102 |
| DATA_FAILURE | 1 | 1.11% | 0/1/0 | 0.2846 | 0.2047 | +0.435 |
| RELATIONAL_CONSTRUCT_FAILURE | 12 | 13.33% | 5/4/3 | 0.1448 | 0.1132 | +0.280 |
| UNVERIFIABLE | 0 | 0.00% | 0/0/0 | – | – | – |

**UNVERIFIABLE = 0（明确标记：无）。** 这不是“没查”，而是冻结库的原始事件覆盖到 2026-10-18（研究可用通道到 2026-10-15），三个标签窗口（最晚 2026-10-01）都在覆盖内；因此“窗口内没有申报”是可核查的阳性证据，而不是缺失证据。真正不可核查的是**窗口之后**的长期行为（见 §8）。

### 3.2 与 B2 的关系：共享 vs graph-specific

| 集合 | 例数 | 占比 | 构成 | 平均 Δlogit（图模型 − B2） |
|---|---:|---|---|---:|
| 与 B2 top-k FP 共享 | 75 | 83.33% | MODEL 53 + LABEL 21 + DATA 1 | +0.058 |
| graph-specific | 15 | 16.67% | RELATIONAL 12 + LABEL 3 | +0.301 |

每个窗口都是 25/30 重叠（Jaccard 0.714）。“共享”按集合归属定义，是保守口径：另有 13 例虽然仍在 B2 top-k 集内，但图增量 Δlogit>0.3（最大为 J&J cardiac_rhythm 2025-04：G1 第 4 名 vs B2 第 28 名，Δlogit=+0.81）。

### 3.3 图贡献与“历史计数重述”检验

- Δlogit 分布：57/90 为正；均值 +0.0985，中位 +0.0766，范围 [-0.3312, +0.8066]。
- 图贡献占该行 logit 绝对质量的比例：shared 平均 0.040，graph-specific 平均 0.067——**即使顶排 FP，图的边际作用也很小**，主项始终是 B3 活动计数 + 负截距。
- 重述检验（holdout 池 5,159 行）：`g_twohop_reach` 与 `rd_company_active_tracks_12m` r=0.837；`g_company_eigenvector` r=0.795。其余图特征与 B3 的 |r| 在 0.14–0.40。
- 因此“图特征只是历史计数的重述”这一怀疑**成立但只针对 2/12 个图特征**；12 个 relational 案例中 3 例由这两个重述特征驱动，9 例由真正独立的 relational 特征（portfolio 相似度、co-entry、entrant centrality）驱动。

---

## 4. 机制发现（每一类都是可核查的原始记录结论）

### 4.1 顶排假阳性主体不是图特征造成的 [`CORRECTED_RESULT`]

83.3% 的 top FP 同时是 B2 的 top FP；图增量均值只有 +0.058（shared），graph-specific 也只有 +0.301。逐例复核中没有任何一例是“只有图特征才能解释的高置信错误”；graph-specific 案例在概率上也只是 0.12–0.19 的弱排序。

### 4.2 26.7% 是标签口径假阳性：维护性申报在通道里“不存在” [`CORRECTED_RESULT`]

24 例在窗口内有同一 (企业, 赛道) 的原始申报，但全部不是 qualifying 事件：PMA supplement 共 327 条 30-Day Notice、97 条 Real-Time、56 条 135-day、23 条 180-day、45 条 180-day(no-fee)、3 条 Panel Track、3 条 Special-immediate，以及 1 条 Special 510(k)。

关键点是这 24 例中 **8 例的先验原始历史有 239–939 条**，几乎全是 supplement：Boston Scientific 心脏节律（939 条，窗口内又 97 条）、Medtronic 结构性心脏病（353 条，窗口内 39 条）、Abbott 心衰（264 条，窗口内 48 条）等。这些不是“潜在新进入者”，而是**已经拥有大型 PMA 家族、只通过 supplement 维持的在位者**；研究通道在加载阶段丢弃 23,288/23,871 条 PMA supplement（只保留原始 PMA 与 Panel Track supplement），因此它们在特征里也不存在。标签把“维护”排除在外是预注册决定，但后果是：**顶排 FP 中有四分之一其实是“标签口径 vs 现实活动”的错配，不是模型/图构造的错误，且对 G1 与 B2 完全对称。**

### 4.3 1 例数据失败：估计知识时钟造出“假休眠对” [`CORRECTED_RESULT`]

BD / medical_ai / 2025-07-01：该对最后一次合格申报 `71ad134695…` 的 `event_date=2025-06-20`（Traditional 510(k)，BD Intelliport System），但 `available_at=2025-07-04`——落在窗口起点之后 3 天。研究的知识时钟是常数 `event_date+14d`（L1，全部历史行都是估计值），于是模型在 2025-07-01 看不到这条申报，pair 被视为休眠 57 个月。真实世界里公司 11 天前刚刚在该赛道拿证；**“进入”预测本身是对既有活动的重复计数**，属于数据时钟失败而非模型失败。

全样本里 9/90 例有“窗口前事件、available_at 晚于起点”的时钟滞后；其中只有 2 例是 material 事件（BD 与 Edwards），其余是 PMA supplement（本来就不在通道内）。

### 4.4 13.3% 是关系构造失败：相似度/同批进入的类比没有兑现 [`CORRECTED_RESULT`]

12 例 graph-specific 且无 label/data 伪影：这些行进入 top-k **只因为图增量**（Δlogit 均值 +0.28），但窗口内该对 0 条申报、企业仍在其他赛道活跃。驱动项分两类：

- **9 例 = relational analogy**：`g_similarity_to_track_max`、`g_track_entrant_centrality`、`g_coentry_*`（与 B3 的 |r| 仅 0.15–0.40，确实是独立的关系性信息）。图的隐含主张是“与在位者相似 / 同业刚进入 → 该企业也会进入”，样本外没有兑现。
- **3 例 = count restatement**：最大图贡献是 `g_twohop_reach` 或 `g_company_eigenvector`（与活动计数 r≈0.84/0.80），即“关系信号”实际上只是活动规模。

这也回答了预注册关心的问题：图的边际贡献不仅小，而且在它真正改变排序的那 15 行里，失败方式是**关系类比失效**，不是“关系数据被错误计算”。

### 4.5 数据归属检查：0 例实体/赛道/截断失败，但有明确的可靠性 caveat [`UNCHANGED_FINDING` + `UNRESOLVED_LIMITATION`]

| 检查 | 结果 |
|---|---|
| 实体换键（同一 applicant_raw 在窗口内落到不同 company_key） | 0/90 |
| 歧义 applicant_raw（同一字符串历史上映射到 >1 个 company_key） | 0/90 |
| 窗口内合格申报的 product_code 按 config 应属本赛道、却记在别的赛道 | 0/90 |
| 左截断影响（36 个月休眠窗早于 DB 覆盖起点 2016-11-01） | 0/90（holdout 的休眠窗从 2022-04/07/10 开始） |
| 右删失影响（标签窗晚于 DB 覆盖终点） | 0/90（最晚窗口止于 2026-10-01） |
| 企业历史含已验证并购子公司别名的事件 | 42/90 |
| 该对先验原始历史无任何 material 事件（通道完全失明） | 0/90 |
| 先验产品码不在随包 config 代码表内（赛道赋值不可复现） | 28/90（79 个先验码中 13 个，16.5%） |

并购 hindsight 最重的是 bd：45.1% 的事件经 C R Bard / Bard Access 别名归属（与 audit_13 的 44.11% 一致），Siemens Healthineers 12.8%（Varian）、Stryker 5.4%（Wright/MAKO）、Abbott 4.5%（St. Jude）。赛道映射是单一无日期分类法（`tracks.updated_at=2026-11-01`），把 2016 年申报映射到 2026 年的 38 赛道分类本身是时代错置（L4）。**这两项没有在本样本中制造任何 label 错判**，但会削弱“企业/赛道活动计数”与“图位置”的可比性，属于必须披露、不能消除的限制。

### 4.6 58.9% 是共享模型失败：大企业活跃，但没有跨入该赛道 [`CORRECTED_RESULT`]

53 例与 B2 共享、无 label/data 伪影：企业窗口内**仍有申报**（没有一例“公司消失”），但所有申报都在别的赛道；该 (企业,赛道) 对 0 条申报，其中 4 例在 horizon 之后才出现合格申报（时间误差而非方向误差）。

案例高度集中在大企业：Medtronic 14 例、J&J MedTech 9、Stryker 9、BD 6、Boston Scientific 6（前 5 家占 49%）；赛道集中在 endoscopy 11、cardiac_rhythm 8、medical_ai 7、respiratory 6、vascular_access 6、dialysis 6。这与“模型把‘大而多赛道的在位者 × 热门赛道 × 长休眠’排到前面”的机制一致；该机制在 B2 里由活动计数特征主导，图特征只是叠了一点点。

---

## 5. 逐例表（90 例）

列：window | 企业（★ = graph-specific，即 B2 未把该行选进 top-k FP） | 赛道 | G1 | B2 | G1名次 / B2名次 | B2 共享 | 类别 | 一行证据。

### 5.1 origin = 2025-04-01（30 例）

| window | 企业 | 赛道 | G1 | B2 | G1/B2 名次 | B2共享 | 类别 | 一行证据 |
|---|---|---|---:|---:|---|---|---|---|
| 2025-04-01 | GE医疗 | 呼吸与麻醉 | 0.3185 | 0.2276 | 1 / 6 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.46；该对窗口内 0 申报；企业窗口内于 4 个其他赛道有 28 条合格申报 |
| 2025-04-01 | 美敦力 | 血管通路 | 0.2954 | 0.3299 | 2 / 1 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.16；该对窗口内 0 申报；企业窗口内于 18 个其他赛道有 38 条合格申报 |
| 2025-04-01 | 强生医疗科技 | 心脏节律（起搏/ICD） | 0.2668 | 0.1397 | 4 / 28 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.81；该对窗口内 0 申报；企业窗口内于 9 个其他赛道有 16 条合格申报 |
| 2025-04-01 | 美敦力 | 监护与生命体征 | 0.2580 | 0.2858 | 5 / 2 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.14；该对窗口内 0 申报；企业窗口内于 18 个其他赛道有 38 条合格申报 |
| 2025-04-01 | 碧迪 | 血液净化 | 0.2455 | 0.1733 | 6 / 14 | 是 | LABEL_FAILURE | 窗口内非合格申报 2 条（PMA补充(30-Day)×2）；如 2d17d9051a… 2025-06-26 |
| 2025-04-01 | 美敦力 | 创伤骨科 | 0.2409 | 0.2340 | 7 / 4 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.04；该对窗口内 0 申报；企业窗口内于 18 个其他赛道有 38 条合格申报 |
| 2025-04-01 | 美敦力 | 血液净化 | 0.2197 | 0.2284 | 9 / 5 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.05；该对窗口内 0 申报；企业窗口内于 18 个其他赛道有 38 条合格申报 |
| 2025-04-01 | 史赛克 | 电生理与脉冲场消融 | 0.2185 | 0.1775 | 10 / 13 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.26；该对窗口内 0 申报；企业窗口内于 9 个其他赛道有 24 条合格申报 |
| 2025-04-01 | 史赛克 | 伤口与敷料 | 0.2060 | 0.1327 | 11 / 33 | 是 | LABEL_FAILURE | 窗口内非合格申报 1 条（PMA补充(135天)×1）；如 e7ec45ccbf… 2025-11-06 |
| 2025-04-01 | 史赛克 | 冠脉介入 | 0.1969 | 0.1937 | 12 / 10 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.02；该对窗口内 0 申报；企业窗口内于 9 个其他赛道有 24 条合格申报 |
| 2025-04-01 | 美敦力 | 结构性心脏病 | 0.1848 | 0.2014 | 13 / 9 | 是 | LABEL_FAILURE | 窗口内非合格申报 46 条（PMA补充(30-Day)×33、PMA补充(135天)×7、PMA补充(Real-Time)×4、PMA补充(Panel Track)×1、PMA补充(180天)×1）；如 3efe43fd39… 2025-04-07 |
| 2025-04-01 | 雅培 | 心衰与机械循环支持 | 0.1844 | 0.2224 | 14 / 7 | 是 | LABEL_FAILURE | 窗口内非合格申报 47 条（PMA补充(30-Day)×30、PMA补充(Real-Time)×8、PMA补充(135天)×4、PMA补充(180天)×3、PMA补充(Special)×1、PMA补充(180天免fee)×1）；如 50dbc0430c… 2025-04-07 |
| 2025-04-01 | 波士顿科学 | 心脏节律（起搏/ICD） | 0.1791 | 0.1369 | 16 / 30 | 是 | LABEL_FAILURE | 窗口内非合格申报 76 条（PMA补充(30-Day)×44、PMA补充(180天免fee)×11、PMA补充(Real-Time)×10、PMA补充(135天)×9、PMA补充(180天)×2）；如 1695af322a… 2025-04-11 |
| 2025-04-01 | 强生医疗科技 | 呼吸与麻醉 | 0.1754 | 0.1587 | 17 / 17 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.12；该对窗口内 0 申报；企业窗口内于 9 个其他赛道有 16 条合格申报 |
| 2025-04-01 | 美瑞特 | 外周血管 | 0.1653 | 0.1532 | 18 / 21 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.09；该对窗口内 0 申报；企业窗口内于 3 个其他赛道有 4 条合格申报 |
| 2025-04-01 | 捷迈邦美 ★ | 内窥镜 | 0.1627 | 0.1310 | 19 / 35 | 否 | RELATIONAL_CONSTRUCT_FAILURE | 图特有（B2 未入 top-k）：Δlogit=+0.25，主因 g_similarity_to_track_max(贡献+0.24, r=+0.33)；窗口内该对 0 申报 |
| 2025-04-01 | 飞利浦 | 心脏节律（起搏/ICD） | 0.1597 | 0.1418 | 20 / 26 | 是 | LABEL_FAILURE | 窗口内非合格申报 4 条（PMA补充(30-Day)×4）；如 03425d5927… 2025-06-09 |
| 2025-04-01 | 贝朗 | 神经介入 | 0.1556 | 0.1509 | 21 / 22 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.04；该对窗口内 0 申报；企业窗口内于 1 个其他赛道有 2 条合格申报 |
| 2025-04-01 | 奥林巴斯 | 普外与手术耗材 | 0.1544 | 0.1507 | 22 / 23 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.03；该对窗口内 0 申报；企业窗口内于 3 个其他赛道有 31 条合格申报 |
| 2025-04-01 | 爱德华生命科学 | 血管通路 | 0.1522 | 0.1607 | 23 / 15 | 是 | LABEL_FAILURE | 窗口内非合格申报 1 条（Special 510(k)×1）；如 484178713c… 2025-08-29 |
| 2025-04-01 | 强生医疗科技 | 可穿戴与远程监测 | 0.1518 | 0.1341 | 24 / 31 | 是 | LABEL_FAILURE | 窗口内非合格申报 4 条（PMA补充(30-Day)×3、PMA补充(180天免fee)×1）；如 8f73304bc5… 2026-01-22 |
| 2025-04-01 | 强生医疗科技 ★ | 医美与皮肤 | 0.1510 | 0.1291 | 25 / 37 | 否 | RELATIONAL_CONSTRUCT_FAILURE | 图特有（B2 未入 top-k）：Δlogit=+0.18，主因 g_twohop_reach(贡献+0.12, r=+0.84)；窗口内该对 0 申报 |
| 2025-04-01 | 卡尔史托斯 ★ | 医疗AI/软件(SaMD) | 0.1505 | 0.1063 | 26 / 53 | 否 | RELATIONAL_CONSTRUCT_FAILURE | 图特有（B2 未入 top-k）：Δlogit=+0.40，主因 g_similarity_to_track_max(贡献+0.18, r=+0.33)；窗口内该对 0 申报 |
| 2025-04-01 | 高博医疗 ★ | 内窥镜 | 0.1494 | 0.1280 | 27 / 38 | 否 | RELATIONAL_CONSTRUCT_FAILURE | 图特有（B2 未入 top-k）：Δlogit=+0.18，主因 g_similarity_to_track_max(贡献+0.26, r=+0.33)；窗口内该对 0 申报 |
| 2025-04-01 | 捷迈邦美 ★ | 伤口与敷料 | 0.1489 | 0.0996 | 28 / 59 | 否 | RELATIONAL_CONSTRUCT_FAILURE | 图特有（B2 未入 top-k）：Δlogit=+0.46，主因 g_similarity_to_track_max(贡献+0.24, r=+0.33)；窗口内该对 0 申报 |
| 2025-04-01 | 波士顿科学 | 关节与骨科植入 | 0.1410 | 0.1583 | 29 / 18 | 是 | LABEL_FAILURE | 窗口内非合格申报 3 条（PMA补充(180天免fee)×2、PMA补充(30-Day)×1）；如 4e8b1f1e92… 2025-07-16 |
| 2025-04-01 | 高博医疗 | 影像（MR/CT/PET/X-ray） | 0.1401 | 0.1313 | 30 / 34 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.08；该对窗口内 0 申报；企业窗口内于 3 个其他赛道有 5 条合格申报 |
| 2025-04-01 | 半影 | 内窥镜 | 0.1392 | 0.1461 | 31 / 24 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.06；该对窗口内 0 申报；企业窗口内于 1 个其他赛道有 2 条合格申报 |
| 2025-04-01 | 麦朗 | 血管通路 | 0.1384 | 0.1599 | 32 / 16 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.17；该对窗口内 0 申报；企业窗口内于 1 个其他赛道有 6 条合格申报；窗口后 2026-07-29 才出现合格申报 |
| 2025-04-01 | 豪洛捷 | 影像（MR/CT/PET/X-ray） | 0.1381 | 0.1825 | 33 / 12 | 是 | LABEL_FAILURE | 窗口内非合格申报 1 条（PMA补充(180天免fee)×1）；如 c22f640852… 2025-11-24 |

### 5.2 origin = 2025-07-01（30 例）

| window | 企业 | 赛道 | G1 | B2 | G1/B2 名次 | B2共享 | 类别 | 一行证据 |
|---|---|---|---:|---:|---|---|---|---|
| 2025-07-01 | 美敦力 | 血管通路 | 0.3115 | 0.3401 | 1 / 1 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.13；该对窗口内 0 申报；企业窗口内于 21 个其他赛道有 35 条合格申报 |
| 2025-07-01 | GE医疗 | 呼吸与麻醉 | 0.2940 | 0.2043 | 2 / 9 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.48；该对窗口内 0 申报；企业窗口内于 4 个其他赛道有 26 条合格申报 |
| 2025-07-01 | 碧迪 | 医疗AI/软件(SaMD) | 0.2846 | 0.2047 | 3 / 8 | 是 | DATA_FAILURE | 知识时钟滞后：窗口前合格申报 71ad134695… 决策2025-06-20 / available 2025-07-04，模型看不到 → 该对并非休眠对 |
| 2025-07-01 | 美敦力 | 监护与生命体征 | 0.2430 | 0.2768 | 5 / 2 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.18；该对窗口内 0 申报；企业窗口内于 21 个其他赛道有 35 条合格申报 |
| 2025-07-01 | 碧迪 | 血液净化 | 0.2283 | 0.1668 | 6 / 15 | 是 | LABEL_FAILURE | 窗口内非合格申报 2 条（PMA补充(30-Day)×2）；如 651ca889af… 2025-12-16 |
| 2025-07-01 | 强生医疗科技 | 泌尿 | 0.2251 | 0.2445 | 7 / 3 | 是 | LABEL_FAILURE | 窗口内非合格申报 6 条（PMA补充(30-Day)×4、PMA补充(180天)×1、PMA补充(135天)×1）；如 9fc0022f24… 2025-10-14 |
| 2025-07-01 | 美敦力 | 创伤骨科 | 0.2143 | 0.2235 | 8 / 5 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.05；该对窗口内 0 申报；企业窗口内于 21 个其他赛道有 35 条合格申报 |
| 2025-07-01 | 美敦力 | 血液净化 | 0.2064 | 0.2239 | 9 / 4 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.10；该对窗口内 0 申报；企业窗口内于 21 个其他赛道有 35 条合格申报 |
| 2025-07-01 | 史赛克 | 冠脉介入 | 0.2058 | 0.1856 | 10 / 12 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.13；该对窗口内 0 申报；企业窗口内于 10 个其他赛道有 29 条合格申报 |
| 2025-07-01 | 史赛克 | 电生理与脉冲场消融 | 0.2003 | 0.1636 | 11 / 16 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.25；该对窗口内 0 申报；企业窗口内于 10 个其他赛道有 29 条合格申报 |
| 2025-07-01 | 奥林巴斯 | 普外与手术耗材 | 0.1939 | 0.1556 | 12 / 17 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.27；该对窗口内 0 申报；企业窗口内于 4 个其他赛道有 27 条合格申报 |
| 2025-07-01 | 史赛克 ★ | 伤口与敷料 | 0.1859 | 0.1175 | 13 / 35 | 否 | LABEL_FAILURE | 窗口内非合格申报 1 条（PMA补充(135天)×1）；如 e7ec45ccbf… 2025-11-06 |
| 2025-07-01 | 美敦力 | 结构性心脏病 | 0.1795 | 0.1983 | 15 / 10 | 是 | LABEL_FAILURE | 窗口内非合格申报 39 条（PMA补充(30-Day)×24、PMA补充(135天)×8、PMA补充(Real-Time)×5、PMA补充(Panel Track)×1、PMA补充(180天)×1）；如 becd5b6a3a… 2025-08-14 |
| 2025-07-01 | 卡尔史托斯 ★ | 医疗AI/软件(SaMD) | 0.1683 | 0.1180 | 16 / 34 | 否 | RELATIONAL_CONSTRUCT_FAILURE | 图特有（B2 未入 top-k）：Δlogit=+0.41，主因 g_track_entrant_centrality(贡献+0.16, r=+0.40)；窗口内该对 0 申报 |
| 2025-07-01 | 碧迪 ★ | 冠脉介入 | 0.1662 | 0.1139 | 17 / 41 | 否 | RELATIONAL_CONSTRUCT_FAILURE | 图特有（B2 未入 top-k）：Δlogit=+0.44，主因 g_similarity_to_track_max(贡献+0.18, r=+0.33)；窗口内该对 0 申报 |
| 2025-07-01 | 雅培 | 心衰与机械循环支持 | 0.1659 | 0.2079 | 18 / 7 | 是 | LABEL_FAILURE | 窗口内非合格申报 45 条（PMA补充(30-Day)×24、PMA补充(Real-Time)×11、PMA补充(135天)×4、PMA补充(180天)×3、PMA补充(180天免fee)×2、PMA补充(Special)×1）；如 5373f62e7c… 2025-07-11 |
| 2025-07-01 | 英特格拉 | 手术能量器械 | 0.1655 | 0.1444 | 19 / 22 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.16；该对窗口内 0 申报；企业窗口内于 4 个其他赛道有 4 条合格申报 |
| 2025-07-01 | 波士顿科学 | 心脏节律（起搏/ICD） | 0.1649 | 0.1227 | 20 / 31 | 是 | LABEL_FAILURE | 窗口内非合格申报 112 条（PMA补充(30-Day)×63、PMA补充(Real-Time)×25、PMA补充(180天免fee)×11、PMA补充(135天)×9、PMA补充(180天)×4）；如 00366cba57… 2025-07-11 |
| 2025-07-01 | 美瑞特 | 外周血管 | 0.1619 | 0.1523 | 21 / 19 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.07；该对窗口内 0 申报；企业窗口内于 3 个其他赛道有 6 条合格申报 |
| 2025-07-01 | 波士顿科学 | 关节与骨科植入 | 0.1555 | 0.1503 | 22 / 21 | 是 | LABEL_FAILURE | 窗口内非合格申报 3 条（PMA补充(180天免fee)×2、PMA补充(30-Day)×1）；如 4e8b1f1e92… 2025-07-16 |
| 2025-07-01 | 贝朗 | 神经介入 | 0.1548 | 0.1371 | 23 / 25 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.14；该对窗口内 0 申报；企业窗口内于 1 个其他赛道有 2 条合格申报 |
| 2025-07-01 | 强生医疗科技 | 呼吸与麻醉 | 0.1518 | 0.1317 | 24 / 28 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.17；该对窗口内 0 申报；企业窗口内于 9 个其他赛道有 20 条合格申报 |
| 2025-07-01 | 美瑞特 | 内窥镜 | 0.1478 | 0.1699 | 25 / 14 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.17；该对窗口内 0 申报；企业窗口内于 3 个其他赛道有 6 条合格申报 |
| 2025-07-01 | 半影 | 内窥镜 | 0.1432 | 0.1515 | 26 / 20 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.07；该对窗口内 0 申报；企业窗口内于 2 个其他赛道有 4 条合格申报 |
| 2025-07-01 | 麦朗 | 血管通路 | 0.1427 | 0.1699 | 27 / 13 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.21；该对窗口内 0 申报；企业窗口内于 2 个其他赛道有 6 条合格申报；窗口后 2026-07-29 才出现合格申报 |
| 2025-07-01 | 捷迈邦美 | 内窥镜 | 0.1411 | 0.1372 | 28 / 24 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.03；该对窗口内 0 申报；企业窗口内于 3 个其他赛道有 20 条合格申报 |
| 2025-07-01 | 高博医疗 | 内窥镜 | 0.1382 | 0.1337 | 29 / 27 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.04；该对窗口内 0 申报；企业窗口内于 3 个其他赛道有 6 条合格申报 |
| 2025-07-01 | 强生医疗科技 ★ | 心脏节律（起搏/ICD） | 0.1372 | 0.1147 | 30 / 39 | 否 | RELATIONAL_CONSTRUCT_FAILURE | 图特有（B2 未入 top-k）：Δlogit=+0.20，主因 g_twohop_reach(贡献+0.12, r=+0.84)；窗口内该对 0 申报 |
| 2025-07-01 | 英特格拉 | 创伤骨科 | 0.1345 | 0.1342 | 31 / 26 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.00；该对窗口内 0 申报；企业窗口内于 4 个其他赛道有 4 条合格申报 |
| 2025-07-01 | 奥林巴斯 ★ | 影像（MR/CT/PET/X-ray） | 0.1343 | 0.1058 | 32 / 49 | 否 | RELATIONAL_CONSTRUCT_FAILURE | 图特有（B2 未入 top-k）：Δlogit=+0.27，主因 g_similarity_to_track_max(贡献+0.25, r=+0.33)；窗口内该对 0 申报 |

### 5.3 origin = 2025-10-01（30 例）

| window | 企业 | 赛道 | G1 | B2 | G1/B2 名次 | B2共享 | 类别 | 一行证据 |
|---|---|---|---:|---:|---|---|---|---|
| 2025-10-01 | 美敦力 | 血管通路 | 0.3705 | 0.3429 | 1 / 1 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.12；该对窗口内 0 申报；企业窗口内于 21 个其他赛道有 37 条合格申报 |
| 2025-10-01 | 强生医疗科技 | 泌尿 | 0.2514 | 0.2144 | 2 / 3 | 是 | LABEL_FAILURE | 窗口内非合格申报 7 条（PMA补充(30-Day)×5、PMA补充(180天)×1、PMA补充(135天)×1）；如 9fc0022f24… 2025-10-14 |
| 2025-10-01 | 美敦力 | 监护与生命体征 | 0.2307 | 0.2645 | 3 / 2 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.18；该对窗口内 0 申报；企业窗口内于 21 个其他赛道有 37 条合格申报 |
| 2025-10-01 | 施乐辉 | 医疗AI/软件(SaMD) | 0.2190 | 0.1664 | 4 / 12 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.34；该对窗口内 0 申报；企业窗口内于 2 个其他赛道有 6 条合格申报 |
| 2025-10-01 | 碧迪 | 血液净化 | 0.2106 | 0.1563 | 6 / 14 | 是 | LABEL_FAILURE | 窗口内非合格申报 2 条（PMA补充(30-Day)×2）；如 651ca889af… 2025-12-16 |
| 2025-10-01 | 美敦力 | 血液净化 | 0.1898 | 0.2097 | 7 / 4 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.12；该对窗口内 0 申报；企业窗口内于 21 个其他赛道有 37 条合格申报 |
| 2025-10-01 | 美敦力 | 创伤骨科 | 0.1878 | 0.2021 | 8 / 6 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.09；该对窗口内 0 申报；企业窗口内于 21 个其他赛道有 37 条合格申报 |
| 2025-10-01 | 史赛克 | 电生理与脉冲场消融 | 0.1744 | 0.1503 | 10 / 16 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.18；该对窗口内 0 申报；企业窗口内于 10 个其他赛道有 23 条合格申报 |
| 2025-10-01 | 卡尔史托斯 | 医疗AI/软件(SaMD) | 0.1685 | 0.1307 | 11 / 25 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.30；该对窗口内 0 申报；企业窗口内于 3 个其他赛道有 16 条合格申报 |
| 2025-10-01 | 盈纬达 | 医疗AI/软件(SaMD) | 0.1673 | 0.1170 | 12 / 32 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.42；该对窗口内 0 申报；企业窗口内于 1 个其他赛道有 4 条合格申报 |
| 2025-10-01 | 英特格拉 | 手术能量器械 | 0.1636 | 0.1210 | 13 / 30 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.35；该对窗口内 0 申报；企业窗口内于 4 个其他赛道有 2 条合格申报 |
| 2025-10-01 | 史赛克 | 冠脉介入 | 0.1629 | 0.1721 | 14 / 11 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.07；该对窗口内 0 申报；企业窗口内于 10 个其他赛道有 23 条合格申报 |
| 2025-10-01 | GE医疗 | 呼吸与麻醉 | 0.1579 | 0.1944 | 15 / 8 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.25；该对窗口内 0 申报；企业窗口内于 4 个其他赛道有 29 条合格申报 |
| 2025-10-01 | 雅培 | 心衰与机械循环支持 | 0.1537 | 0.1949 | 17 / 7 | 是 | LABEL_FAILURE | 窗口内非合格申报 48 条（PMA补充(30-Day)×28、PMA补充(Real-Time)×11、PMA补充(135天)×4、PMA补充(180天)×3、PMA补充(180天免fee)×2）；如 04ee3614c0… 2025-10-06 |
| 2025-10-01 | 美瑞特 | 外周血管 | 0.1532 | 0.1379 | 18 / 22 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.12；该对窗口内 0 申报；企业窗口内于 3 个其他赛道有 6 条合格申报 |
| 2025-10-01 | 波士顿科学 | 关节与骨科植入 | 0.1453 | 0.1417 | 19 / 19 | 是 | LABEL_FAILURE | 窗口内非合格申报 4 条（PMA补充(30-Day)×3、PMA补充(180天免fee)×1）；如 b91d444b74… 2025-10-02 |
| 2025-10-01 | 波士顿科学 ★ | 心脏节律（起搏/ICD） | 0.1448 | 0.1116 | 20 / 36 | 否 | LABEL_FAILURE | 窗口内非合格申报 97 条（PMA补充(30-Day)×52、PMA补充(Real-Time)×23、PMA补充(180天免fee)×11、PMA补充(135天)×6、PMA补充(180天)×4、PMA补充(Special)×1）；如 01969b08e3… 2025-10-22 |
| 2025-10-01 | 飞利浦 | 心脏节律（起搏/ICD） | 0.1436 | 0.1432 | 21 / 18 | 是 | LABEL_FAILURE | 窗口内非合格申报 2 条（PMA补充(30-Day)×2）；如 c20cfb3503… 2025-12-18 |
| 2025-10-01 | 贝朗 | 神经介入 | 0.1406 | 0.1298 | 22 / 26 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=+0.09；该对窗口内 0 申报；企业窗口内于 2 个其他赛道有 2 条合格申报 |
| 2025-10-01 | 史赛克 ★ | 伤口与敷料 | 0.1401 | 0.1057 | 23 / 45 | 否 | LABEL_FAILURE | 窗口内非合格申报 2 条（PMA补充(135天)×1、PMA补充(Panel Track)×1）；如 e7ec45ccbf… 2025-11-06 |
| 2025-10-01 | 美瑞特 | 内窥镜 | 0.1395 | 0.1636 | 24 / 13 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.19；该对窗口内 0 申报；企业窗口内于 3 个其他赛道有 6 条合格申报 |
| 2025-10-01 | 奥林巴斯 ★ | 影像（MR/CT/PET/X-ray） | 0.1350 | 0.1072 | 26 / 41 | 否 | RELATIONAL_CONSTRUCT_FAILURE | 图特有（B2 未入 top-k）：Δlogit=+0.26，主因 g_similarity_to_track_max(贡献+0.22, r=+0.33)；窗口内该对 0 申报 |
| 2025-10-01 | 费森尤斯医疗 | 医疗AI/软件(SaMD) | 0.1335 | 0.1436 | 27 / 17 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.08；该对窗口内 0 申报；企业窗口内于 1 个其他赛道有 8 条合格申报 |
| 2025-10-01 | 捷迈邦美 | 内窥镜 | 0.1322 | 0.1344 | 28 / 24 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.02；该对窗口内 0 申报；企业窗口内于 3 个其他赛道有 17 条合格申报 |
| 2025-10-01 | 奥林巴斯 | 普外与手术耗材 | 0.1285 | 0.1407 | 29 / 20 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.10；该对窗口内 0 申报；企业窗口内于 5 个其他赛道有 25 条合格申报 |
| 2025-10-01 | 高博医疗 | 内窥镜 | 0.1250 | 0.1254 | 30 / 28 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.00；该对窗口内 0 申报；企业窗口内于 3 个其他赛道有 5 条合格申报 |
| 2025-10-01 | 半影 | 内窥镜 | 0.1215 | 0.1386 | 31 / 21 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.15；该对窗口内 0 申报；企业窗口内于 2 个其他赛道有 4 条合格申报 |
| 2025-10-01 | 强生医疗科技 ★ | 心脏节律（起搏/ICD） | 0.1187 | 0.0973 | 32 / 51 | 否 | RELATIONAL_CONSTRUCT_FAILURE | 图特有（B2 未入 top-k）：Δlogit=+0.22，主因 g_twohop_reach(贡献+0.13, r=+0.84)；窗口内该对 0 申报 |
| 2025-10-01 | 碧迪 ★ | 冠脉介入 | 0.1156 | 0.1079 | 33 / 39 | 否 | RELATIONAL_CONSTRUCT_FAILURE | 图特有（B2 未入 top-k）：Δlogit=+0.08，主因 g_similarity_to_track_max(贡献+0.12, r=+0.33)；窗口内该对 0 申报 |
| 2025-10-01 | 西门子医疗 | 呼吸与麻醉 | 0.1123 | 0.1368 | 34 / 23 | 是 | MODEL_FAILURE | 与 B2 共享 top-k FP；Δlogit=-0.23；该对窗口内 0 申报；企业窗口内于 5 个其他赛道有 46 条合格申报 |

---

## 6. 深度案例（8 例，附原始 event_id）

### 案例 1 — Boston Scientific × 心脏节律（2025-10-01，LABEL_FAILURE，graph-specific）

- **判定**：`LABEL_FAILURE`（窗口内 97 条 PMA supplement；该对是成熟 PMA 家族，标签规则记为 0）
- **分数/名次**：G1=0.1448（全表第 20/1716，FP 第 17） vs B2=0.1116（第 36）；Δlogit=+0.298；graph-specific（B2 未进入 top-k FP 集）
- **企业/赛道**：波士顿科学 `boston_scientific`；心脏节律（起搏/ICD） `cardiac_rhythm`（category=cardiovascular；库内该赛道 5270 条事件 / 9 家企业）；窗口=[2025-10-01, 2026-10-01]
- **先验历史**：原始 939 条（material 2，qualifying 2），首/末 = 2016-11-01 / 2025-09-22；模型可见 934 条，知识时钟滞后 5 条
  - 先验事件 `8c01a8dcb948…` 2025-09-22 pma/30-Day Notice 「Implantable cardioverter defibrillator (non-CRT)」
  - 先验事件 `f1e7791a0776…` 2025-09-22 pma/30-Day Notice 「Pulse generator, pacemaker, implantable, with cardiac resynchronization (CRT-P)」
  - **时钟滞后事件** `28929814aa91…` 2025-09-22 pma/30-Day Notice 「Defibrillator, automatic implantable cardioverter, with cardiac resynchronization (CRT-D)」（决策早于窗口起点，available_at 却晚于起点）
  - 窗口内非合格申报 `01969b08e352…` 2025-10-22 pma/30-Day Notice 「Defibrillator, automatic implantable cardioverter, with cardiac resynchronization (CRT-D)」
  - 窗口内非合格申报 `31b6881196ee…` 2025-10-22 pma/30-Day Notice 「Pulse generator, pacemaker, implantable, with cardiac resynchronization (CRT-P)」
- **真实未来（4 个季度内）**：该对合格申报 0 条、非合格 97 条；企业在窗口内共 243 条事件，其中本赛道 97 条、其他赛道 146 条（16 个赛道分组）
  - 其他赛道活动 `未分类`：39 条（qualifying 3），2025-10-02 … 2026-09-14
  - 其他赛道活动 `urology`：35 条（qualifying 2），2025-12-19 … 2026-09-14
  - 其他赛道活动 `neurostimulation`：25 条（qualifying 0），2025-12-10 … 2026-09-22
  - 其他赛道合格申报例 `8befa47f4498…` 2025-10-28 510k/Traditional 「TheraSphere 360 Y-90 Management Platform」
- **图特征分解**：graph 贡献 +0.499，B3 贡献 +2.397，截距 -4.672；图占全 logit 质量 0.066；重述型图特征占图贡献 0.40。主要图贡献：`g_twohop_reach` +0.134（与 B3 最大 |r|=+0.84，对应 rd_company_active_tracks_12m）；`g_company_eigenvector` +0.063（与 B3 最大 |r|=+0.80，对应 rd_company_active_tracks_12m）
- **归因/覆盖检查**：实体换键 0 条、歧义申请人字符串 0 个、acquired-alias 事件占比 0.0%；未在 config 代码表中的先验产品码 ['GZF']；左截断影响=False、右删失影响=False、窗口后可见天数=17

### 案例 2 — Abbott × 心衰（2025-04-01，LABEL_FAILURE，shared）

- **判定**：`LABEL_FAILURE`（窗口内 47 条 PMA supplement；先验 239 条原始历史）
- **分数/名次**：G1=0.1844（全表第 14/1722，FP 第 12） vs B2=0.2224（第 7）；Δlogit=-0.235；与 B2 共享 top-k FP
- **企业/赛道**：雅培 `abbott`；心衰与机械循环支持 `heart_failure`（category=cardiovascular；库内该赛道 736 条事件 / 2 家企业）；窗口=[2025-04-01, 2026-04-01]
- **先验历史**：原始 239 条（material 4，qualifying 2），首/末 = 2016-11-16 / 2025-03-18；模型可见 239 条，知识时钟滞后 0 条
  - 先验事件 `567e3c7e48fd…` 2025-03-12 pma/30-Day Notice 「Ventricular (assist) bypass」
  - 先验事件 `8d87b07d6dbe…` 2025-03-18 pma/30-Day Notice 「Ventricular (assist) bypass」
  - 窗口内非合格申报 `50dbc0430cde…` 2025-04-07 pma/30-Day Notice 「Ventricular (assist) bypass」
  - 窗口内非合格申报 `9299417088f7…` 2025-04-14 pma/30-Day Notice 「Ventricular (assist) bypass」
- **真实未来（4 个季度内）**：该对合格申报 0 条、非合格 47 条；企业在窗口内共 303 条事件，其中本赛道 47 条、其他赛道 256 条（16 个赛道分组）
  - 其他赛道活动 `cardiac_rhythm`：56 条（qualifying 0），2025-04-03 … 2026-03-27
  - 其他赛道活动 `structural_heart`：46 条（qualifying 1），2025-04-18 … 2026-03-19
  - 其他赛道活动 `未分类`：44 条（qualifying 5），2025-04-03 … 2026-03-13
  - 其他赛道合格申报例 `5acd1396ad7f…` 2025-04-04 510k/Traditional 「JETi Hydrodynamic Thrombectomy System」
- **图特征分解**：graph 贡献 -0.035，B3 贡献 +3.223，截距 -4.675；图占全 logit 质量 0.004；图贡献≈0（-0.035），重述占比不可解释。主要图贡献：`g_twohop_reach` +0.066（与 B3 最大 |r|=+0.84，对应 rd_company_active_tracks_12m）；`g_track_cooccurrence_pull` -0.050（与 B3 最大 |r|=+0.31，对应 rd_track_active_companies_12m）
- **归因/覆盖检查**：实体换键 0 条、歧义申请人字符串 0 个、acquired-alias 事件占比 4.53%；未在 config 代码表中的先验产品码 []；左截断影响=False、右删失影响=False、窗口后可见天数=200

### 案例 3 — BD × 医疗AI（2025-07-01，DATA_FAILURE）

- **判定**：`DATA_FAILURE`（窗口前 11 天的 Traditional 510(k) 被 +14 天知识时钟遮蔽）
- **分数/名次**：G1=0.2846（全表第 3/1721，FP 第 3） vs B2=0.2047（第 8）；Δlogit=+0.435；与 B2 共享 top-k FP
- **企业/赛道**：碧迪 `bd`；医疗AI/软件(SaMD) `medical_ai`（category=software；库内该赛道 1164 条事件 / 26 家企业）；窗口=[2025-07-01, 2026-07-01]
- **先验历史**：原始 4 条（material 4，qualifying 4），首/末 = 2017-07-03 / 2025-06-20；模型可见 3 条，知识时钟滞后 1 条
  - 先验事件 `45e6474a45ef…` 2020-09-28 510k/Traditional 「BD FACSLyric Flow Cytometer (3-1, 4-2, 4-2-2, 4-3-3 and 4-3-5 optical configurations), BD FACSDuet Sample Preparation System, BD FACS Universal Loader, BD FACSu」
  - 先验事件 `71ad134695d5…` 2025-06-20 510k/Traditional 「BD Intelliport System; BD Intelliport Reader (516230); BD Intelliport Sensor (516229); BD Intelliport Gateway (516232); BD Intelliport Mount (516233); BD Intell」
  - **时钟滞后事件** `71ad134695d5…` 2025-06-20 510k/Traditional 「BD Intelliport System; BD Intelliport Reader (516230); BD Intelliport Sensor (516229); BD Intelliport Gateway (516232); BD Intelliport Mount (516233); BD Intell」（决策早于窗口起点，available_at 却晚于起点）
- **真实未来（4 个季度内）**：该对合格申报 0 条、非合格 0 条；企业在窗口内共 32 条事件，其中本赛道 0 条、其他赛道 32 条（7 个赛道分组）
  - 其他赛道活动 `未分类`：18 条（qualifying 11），2025-07-02 … 2026-05-29
  - 其他赛道活动 `vascular_access`：7 条（qualifying 6），2025-07-11 … 2026-04-02
  - 其他赛道活动 `ivd_molecular`：2 条（qualifying 1），2025-10-31 … 2026-02-12
  - 其他赛道合格申报例 `bd7297b7f5d5…` 2025-07-03 510k/Traditional 「BD Vacutainer® Eclipse Blood Collection Needle」
- **图特征分解**：graph 贡献 +0.720，B3 贡献 +3.029，截距 -4.671；图占全 logit 质量 0.086；重述型图特征占图贡献 0.07。主要图贡献：`g_track_entrant_centrality` +0.163（与 B3 最大 |r|=+0.40，对应 rd_track_active_companies_delta）；`g_coentry_count_12m` +0.138（与 B3 最大 |r|=+0.40，对应 rd_track_active_companies_delta）
- **归因/覆盖检查**：实体换键 0 条、歧义申请人字符串 0 个、acquired-alias 事件占比 45.12%；未在 config 代码表中的先验产品码 ['OYE']；左截断影响=False、右删失影响=False、窗口后可见天数=109

### 案例 4 — Edwards × 血管通路（2025-04-01，LABEL_FAILURE + 时钟滞后 + 晚到）

- **判定**：`LABEL_FAILURE`（窗口内只有 1 条 Special 510(k)；窗口前 5 天的 Traditional 被时钟遮蔽；窗口后 2026-04-17 才出现合格申报）
- **分数/名次**：G1=0.1522（全表第 23/1722，FP 第 20） vs B2=0.1607（第 15）；Δlogit=-0.065；与 B2 共享 top-k FP
- **企业/赛道**：爱德华生命科学 `edwards_lifesciences`；血管通路 `vascular_access`（category=vascular；库内该赛道 707 条事件 / 21 家企业）；窗口=[2025-04-01, 2026-04-01]
- **先验历史**：原始 3 条（material 3，qualifying 3），首/末 = 2020-03-09 / 2025-03-27；模型可见 2 条，知识时钟滞后 1 条
  - 先验事件 `3a3b66046b03…` 2022-02-14 510k/Traditional 「Fogarty Occlusion Catheter」
  - 先验事件 `3f2351bebcc9…` 2025-03-27 510k/Traditional 「Edwards eSheath Optima introducer set」
  - **时钟滞后事件** `3f2351bebcc9…` 2025-03-27 510k/Traditional 「Edwards eSheath Optima introducer set」（决策早于窗口起点，available_at 却晚于起点）
  - 窗口内非合格申报 `484178713c46…` 2025-08-29 510k/Special 「Edwards eSheath Optima introducer set」
- **真实未来（4 个季度内）**：该对合格申报 0 条、非合格 1 条；企业在窗口内共 65 条事件，其中本赛道 1 条、其他赛道 64 条（4 个赛道分组）
  - 其他赛道活动 `structural_heart`：53 条（qualifying 1），2025-04-10 … 2026-03-11
  - 其他赛道活动 `未分类`：6 条（qualifying 0），2025-04-23 … 2026-02-12
  - 其他赛道活动 `medical_ai`：4 条（qualifying 3），2025-07-23 … 2026-02-24
  - 其他赛道合格申报例 `5a22d2cc8738…` 2025-05-15 510k/Traditional 「Hypertension Prediction Index (HePI) Algorithm」
  - **窗口后**才出现的合格申报 `35aac30ad384…` 2026-04-17 510k/Traditional 「Edwards eSheath+ introducer set」（晚于 horizon，不计入标签）
- **图特征分解**：graph 贡献 +0.156，B3 贡献 +2.802，截距 -4.675；图占全 logit 质量 0.021；重述型图特征占图贡献 0.24。主要图贡献：`g_similarity_to_track_max` +0.153（与 B3 最大 |r|=+0.33，对应 rd_track_active_companies_12m）；`g_company_eigenvector` +0.023（与 B3 最大 |r|=+0.80，对应 rd_company_active_tracks_12m）
- **归因/覆盖检查**：实体换键 0 条、歧义申请人字符串 0 个、acquired-alias 事件占比 0.0%；未在 config 代码表中的先验产品码 []；左截断影响=False、右删失影响=False、窗口后可见天数=200

### 案例 5 — Medtronic × 血管通路（2025-10-01，MODEL_FAILURE，两模型第 1 名）

- **判定**：`MODEL_FAILURE`（G1 与 B2 都排第 1；窗口内 516 条企业事件，全部在别的赛道）
- **分数/名次**：G1=0.3705（全表第 1/1716，FP 第 1） vs B2=0.3429（第 1）；Δlogit=+0.121；与 B2 共享 top-k FP
- **企业/赛道**：美敦力 `medtronic`；血管通路 `vascular_access`（category=vascular；库内该赛道 707 条事件 / 21 家企业）；窗口=[2025-10-01, 2026-10-01]
- **先验历史**：原始 6 条（material 6，qualifying 4），首/末 = 2016-11-17 / 2021-07-15；模型可见 6 条，知识时钟滞后 0 条
  - 先验事件 `d74307685d00…` 2018-10-23 510k/Traditional 「Kangaroo Gastrostomy Feeding Tube with ENFit Y-Port」
  - 先验事件 `9ce63eccefc4…` 2021-07-15 510k/Traditional 「Bio-Medicus Life Support Catheter and Introducer」
- **真实未来（4 个季度内）**：该对合格申报 0 条、非合格 0 条；企业在窗口内共 516 条事件，其中本赛道 0 条、其他赛道 516 条（22 个赛道分组）
  - 其他赛道活动 `cardiac_rhythm`：172 条（qualifying 0），2025-10-02 … 2026-09-25
  - 其他赛道活动 `neurostimulation`：53 条（qualifying 0），2025-10-16 … 2026-09-24
  - 其他赛道活动 `urology`：45 条（qualifying 0），2025-10-16 … 2026-09-14
  - 其他赛道合格申报例 `0224c60a2e92…` 2025-10-06 510k/Traditional 「Shiley Oral RAE Tracheal Tube Cuffless, Murphy Eye (113-XX) Shiley Nasal RAE Tracheal Tube Cuffless, Murphy Eye (114-XX) Shiley Oral RAE Tracheal Tube Cuffed」
- **图特征分解**：graph 贡献 +0.587，B3 贡献 +3.556，截距 -4.672；图占全 logit 质量 0.067；重述型图特征占图贡献 0.24。主要图贡献：`g_track_entrant_centrality` +0.108（与 B3 最大 |r|=+0.40，对应 rd_track_active_companies_delta）；`g_coentry_decay` +0.099（与 B3 最大 |r|=+0.38，对应 rd_track_active_companies_delta）
- **归因/覆盖检查**：实体换键 0 条、歧义申请人字符串 0 个、acquired-alias 事件占比 1.72%；未在 config 代码表中的先验产品码 ['DWF', 'KNT']；左截断影响=False、右删失影响=False、窗口后可见天数=17

### 案例 6 — GE HealthCare × 呼吸与麻醉（2025-04-01，MODEL_FAILURE，但图增量 +0.46）

- **判定**：`MODEL_FAILURE`（两模型共享 top-k，但图把该行从 B2 第 6 名推到 G1 第 1 名；窗口内只做影像）
- **分数/名次**：G1=0.3185（全表第 1/1722，FP 第 1） vs B2=0.2276（第 6）；Δlogit=+0.461；与 B2 共享 top-k FP
- **企业/赛道**：GE医疗 `ge_healthcare`；呼吸与麻醉 `respiratory`（category=respiratory；库内该赛道 570 条事件 / 12 家企业）；窗口=[2025-04-01, 2026-04-01]
- **先验历史**：原始 3 条（material 3，qualifying 2），首/末 = 2017-08-17 / 2021-10-21；模型可见 3 条，知识时钟滞后 0 条
  - 先验事件 `c6bd759ae6a0…` 2019-05-01 510k/Special 「CARESCAPE Respiratory Modules, E-sCO, E-sCOV, E-sCOVX, E-sCAiO」
  - 先验事件 `e4ddb73567b4…` 2021-10-21 510k/Traditional 「CARESCAPE Respiratory Modules E-sCO, E-sCOV, E-sCOVX, E-sCAiO, E-sCAiOV, E-sCAiOVX, E-sCAiOE, E-sCAiOVE and accessories」
- **真实未来（4 个季度内）**：该对合格申报 0 条、非合格 0 条；企业在窗口内共 30 条事件，其中本赛道 0 条、其他赛道 30 条（5 个赛道分组）
  - 其他赛道活动 `imaging_mr_ct`：15 条（qualifying 14），2025-04-21 … 2026-03-24
  - 其他赛道活动 `imaging_us`：10 条（qualifying 10），2025-05-01 … 2026-03-24
  - 其他赛道活动 `medical_ai`：2 条（qualifying 2），2025-07-16 … 2026-03-27
  - 其他赛道合格申报例 `850602baff6e…` 2025-04-21 510k/Traditional 「VersaViewer」
- **图特征分解**：graph 贡献 +0.731，B3 贡献 +3.183，截距 -4.675；图占全 logit 质量 0.085；重述型图特征占图贡献 0.09。主要图贡献：`g_similarity_to_track_max` +0.271（与 B3 最大 |r|=+0.33，对应 rd_track_active_companies_12m）；`g_max_entrant_similarity` +0.120（与 B3 最大 |r|=+0.15，对应 rd_track_active_companies_delta）
- **归因/覆盖检查**：实体换键 0 条、歧义申请人字符串 0 个、acquired-alias 事件占比 0.0%；未在 config 代码表中的先验产品码 ['CCK']；左截断影响=False、右删失影响=False、窗口后可见天数=200

### 案例 7 — Karl Storz × 医疗AI（2025-07-01，RELATIONAL_CONSTRUCT_FAILURE）

- **判定**：`RELATIONAL_CONSTRUCT_FAILURE`（graph-specific：co-entry/entrant-centrality 类比失效）
- **分数/名次**：G1=0.1683（全表第 16/1721，FP 第 14） vs B2=0.1180（第 34）；Δlogit=+0.414；graph-specific（B2 未进入 top-k FP 集）
- **企业/赛道**：卡尔史托斯 `karl_storz`；医疗AI/软件(SaMD) `medical_ai`（category=software；库内该赛道 1164 条事件 / 26 家企业）；窗口=[2025-07-01, 2026-07-01]
- **先验历史**：原始 1 条（material 1，qualifying 0），首/末 = 2020-07-22 / 2020-07-22；模型可见 1 条，知识时钟滞后 0 条
  - 先验事件 `91c766b3c86f…` 2020-07-22 510k/Special 「Endomat Select, IBS Shaver Software, License」
- **真实未来（4 个季度内）**：该对合格申报 0 条、非合格 0 条；企业在窗口内共 13 条事件，其中本赛道 0 条、其他赛道 13 条（4 个赛道分组）
  - 其他赛道活动 `endoscopy`：6 条（qualifying 3），2025-10-01 … 2026-06-03
  - 其他赛道活动 `未分类`：4 条（qualifying 4），2025-09-22 … 2026-03-02
  - 其他赛道活动 `urology`：2 条（qualifying 2），2025-08-13 … 2025-11-18
  - 其他赛道合格申报例 `5ab27e24470b…` 2025-08-13 510k/Traditional 「KARL STORZ HOPKINS Telescopes for Urology」
- **图特征分解**：graph 贡献 +0.615，B3 贡献 +2.458，截距 -4.671；图占全 logit 质量 0.079；重述型图特征占图贡献 0.02。主要图贡献：`g_track_entrant_centrality` +0.163（与 B3 最大 |r|=+0.40，对应 rd_track_active_companies_delta）；`g_coentry_count_12m` +0.138（与 B3 最大 |r|=+0.40，对应 rd_track_active_companies_delta）
- **归因/覆盖检查**：实体换键 0 条、歧义申请人字符串 0 个、acquired-alias 事件占比 0.0%；未在 config 代码表中的先验产品码 ['HIG']；左截断影响=False、右删失影响=False、窗口后可见天数=109

### 案例 8 — Zimmer Biomet × 伤口与敷料（2025-04-01，RELATIONAL_CONSTRUCT_FAILURE）

- **判定**：`RELATIONAL_CONSTRUCT_FAILURE`（graph-specific：portfolio 相似度类比失效，B2 第 59 名 → G1 第 28 名）
- **分数/名次**：G1=0.1489（全表第 28/1722，FP 第 25） vs B2=0.0996（第 59）；Δlogit=+0.459；graph-specific（B2 未进入 top-k FP 集）
- **企业/赛道**：捷迈邦美 `zimmer_biomet`；伤口与敷料 `wound_care`（category=wound；库内该赛道 804 条事件 / 12 家企业）；窗口=[2025-04-01, 2026-04-01]
- **先验历史**：原始 2 条（material 2，qualifying 2），首/末 = 2016-12-19 / 2017-02-17；模型可见 2 条，知识时钟滞后 0 条
  - 先验事件 `c5efcf01331f…` 2016-12-19 510k/Traditional 「MaxBraid BroadBand Suture and Expressbraid BroadBand Graft Manipulation Suture」
  - 先验事件 `5d9305fff1ee…` 2017-02-17 510k/Traditional 「ExpressBraid Graft Manipulation」
- **真实未来（4 个季度内）**：该对合格申报 0 条、非合格 0 条；企业在窗口内共 25 条事件，其中本赛道 0 条、其他赛道 25 条（5 个赛道分组）
  - 其他赛道活动 `ortho_joint`：16 条（qualifying 5），2025-04-09 … 2026-03-09
  - 其他赛道活动 `未分类`：3 条（qualifying 2），2025-07-02 … 2026-02-04
  - 其他赛道活动 `trauma`：3 条（qualifying 2），2025-07-25 … 2026-03-12
  - 其他赛道合格申报例 `06ae3d7277d3…` 2025-07-02 510k/Traditional 「Identity Shoulder System」
- **图特征分解**：graph 贡献 +0.662，B3 贡献 +2.270，截距 -4.675；图占全 logit 质量 0.087；重述型图特征占图贡献 0.13。主要图贡献：`g_similarity_to_track_max` +0.237（与 B3 最大 |r|=+0.33，对应 rd_track_active_companies_12m）；`g_similarity_to_track_incumbents` +0.107（与 B3 最大 |r|=+0.23，对应 rd_company_active_tracks_12m）
- **归因/覆盖检查**：实体换键 0 条、歧义申请人字符串 0 个、acquired-alias 事件占比 0.0%；未在 config 代码表中的先验产品码 []；左截断影响=False、右删失影响=False、窗口后可见天数=200

---

## 7. AP −0.006 到底意味着什么

先把数值原样保留（round-1 artifact，不重新估计 AP）：

| 指标 | 值 |
|---|---|
| G1 pooled AP | 0.069003 |
| B2 pooled AP | 0.075093 |
| ΔAP (G1−B2) | -0.006089 |
| company bootstrap 95% CI | [-0.022187, +0.004500] |
| MDE(80%) | 0.019428 |
| \|ΔAP\| / MDE | 0.313 |

逐例复核能补充的是**这个数字的构成**，而不是重新算它：

**它说明：**

1. 在两个模型选出的 top-30 假阳性中，83.3% 是同一批行；每个窗口 25/30 相同。顶排区域的两个排序器几乎重合，ΔAP −0.006（只有 MDE 的 31%）来自其余排序位置的细微重排，而不是“图模型多出一批独特的高分错误”。
2. 顶排区域被两类与图无关的伪影占据：26.7% 的标签口径伪影（维护性申报）与 1 例知识时钟伪影；这些对 G1/B2 是对称的，会同时压低两个模型的 AP，并让 ΔAP 的估计更噪声化。
3. 图特征真正改变排序的 15 行里，失败模式是“相似度/同批进入的类比不兑现”（9 例）与“图特征重述活动计数”（4 例含 1 例 label），没有一例是关系数据被正确计算但被市场证明的“早期信号”。

**它不说明：**

1. 不说明“图结构/关系信息对医疗技术演化无用”——这只覆盖 12.1% 事件通道上的 51×38 二部图、单一学习器、单一 target（L2/L3/L13）。
2. 不说明“图特征有害”——点估计为负但 CI 跨零、且 |ΔAP| < MDE/3；逐例层面图对 57/90 行是正增量、13 例 shared 行的图增量 >0.3。
3. 更不能把顶排 FP 当作“图发现了但市场没实现的机会”：这些行中 0 例得到原始记录支持为“后来真的进入”，4 例在 horizon 之后才进入（时间误差），其余是活动计数/标签口径/关系类比失败。

> 结论标签：主结果 `UNCHANGED_FINDING`（H1 null 不变）；“顶排假阳性是图信号”的解读 `INVALIDATED_FINDING`；“AP −0.006 说明图有害”的解读 `INVALIDATED_FINDING`。

---

## 8. 局限 / UNRESOLVED_LIMITATION

1. **窗口后行为不可核查（右删失）**：三个窗口 horizon 分别止于 2026-04-01 / 2026-07-01 / 2026-10-01，而原始库事件覆盖止于 2026-10-18（研究可用通道 2026-10-15）。最早的窗口有 200 天窗口后观察，最晚的只有 17 天——因此“4 例晚到”是下限，不能据此说其余 86 例“永远不会进入”。
2. **外部并购/退市不可见**：本审计的实体检查只能使用 frozen DB；若某 roster 公司在窗口前后被非 roster 公司收购/私有化，其活动可能完全离开本通道，而 DB 内没有任何记录。因此“企业仍活跃”只对 DB 内证据成立。
3. **标签口径本身是预注册决定**：LABEL_FAILURE 的分类不等于“研究应该把 supplements 计入标签”。本审计的结论是：在现行标签下，这 24 例的 0 标签是维护性申报造成的口径伪影；修改标签会改变 target 语义（L6/L7），需要新的预注册，不能由本审计事后决定。
4. **赛道/实体映射不可复现**：28/90 例含不在 config 代码表中的先验产品码；8 个 (applicant, company) 组合无别名却匹配成功（audit_13）。这些没有在本样本中改变任何标签，但意味着“图节点/边不能由原始证据逐条重建”（L4）。
5. **关系边类型缺失**：图只有 Company–Track 二部边，没有 Company–Company 边（L8）。因此 RELATIONAL_CONSTRUCT_FAILURE 只针对“相似度/共进入/二跳”这类代理关系，不能推广到真正的合作/许可/供应链关系。
6. **选择规则的主观边界**：k=30 是“至少 30”的下限口径（1% 规则只给 17–18）；top-30 之外的假阳性没有逐例复核。若把 k 扩到 100，类别比例可能变化（尤其 label 类可能更多，因为顶排越往下越接近“在位者维护”区）。
7. **分数分解的边界**：图贡献是按训练好的模型权重精确分解的（parity 1e-16 已证），但“贡献小”不等于“因果作用小”——特征高度相关，且 logistic 的标准化尺度会压缩稀有特征的影响。本审计只主张“在这套模型与特征下，顶排 FP 的分数主要由 B3 活动计数决定”。

---

## 9. 复现

```powershell
cd D:\DEPPSKK\medradar\research\studies\graph_early_signal_s028
python code\audit_22_false_positives.py
```

- 运行前脚本用 size + SHA-256 校验 frozen DB；重建 panel/图/模型并与 stored predictions 比对（失败即 raise）；
- 确定性：脚本启动时若未设置 `PYTHONHASHSEED=0` 会以该环境变量 re-exec 自身（消除原 `SnapshotSeries` power iteration 对 Python set 迭代顺序的依赖），输出浮点统一 round 到 1e-10——连续运行 SHA-256 相同；
- 输出 `artifacts/correction_round_1/false_positive_cases.json`（约 1.7 MB，含 90 例逐例证据与聚合分布）；
- 运行时间约 10–20 秒（事件加载 1.3s、panel 2s、snapshot 与拟合 <5s、逐例证据与 DB 查询数秒）；
- 依赖：`code/s028_lib.py`、`code/s028_experiment.py`（只 import，不修改）、Python 3.12 + numpy。

---

## 10. 标签化结论汇总

| 标签 | 结论 |
|---|---|
| `ORIGINAL_RESULT` | 原研究的负结果登记（N1–N9、L1–L16）完整保留；本审计不修改任何原始 artifact。 |
| `CORRECTED_RESULT` | 完成 L14/B-NEXT-2 未完成的逐例复核：53 MODEL_FAILURE、24 LABEL_FAILURE、1 DATA_FAILURE、12 RELATIONAL_CONSTRUCT_FAILURE、0 UNVERIFIABLE。 |
| `CORRECTED_RESULT` | 顶排假阳性的 83.3% 已是 B2 top FP；“图特有的高置信错误”这一预期不成立。 |
| `CORRECTED_RESULT` | 26.7% 的顶排 FP 是标签口径伪影（维护性申报）；1 例是 +14 天知识时钟伪影；12 例是关系类比失败。 |
| `UNCHANGED_FINDING` | H1 null（ΔAP −0.00609，CI 跨 0，MDE 0.01943）不变；N4 的“图特征重述活动计数”在 holdout 池上复现（r=0.837/0.795 vs 0.849/0.779）。 |
| `UNCHANGED_FINDING` | 实体/赛道/截断检查在本样本中未发现任何 label 错判；L4 的并购 hindsight（bd 45.1%）与映射不可复现（28/90）被再次确认。 |
| `INVALIDATED_FINDING` | 把 top 假阳性读成“图结构早期信号”的解读被逐例证据否定；把 ΔAP −0.006 读成“图特征有害”的解读被 CI/MDE 与共享集合证据否定。 |
| `UNRESOLVED_LIMITATION` | 窗口后长期行为不可核查（最晚窗口仅 17 天观察）；外部并购/退市不可见；标签口径是否应改需新预注册；k=30 之外未复核；关系边类型缺失。 |

---

*生成：`code/audit_22_false_positives.py` → `artifacts/correction_round_1/false_positive_cases.json`；本文件由该 JSON 的数值与逐例记录组装（所有数字可在 JSON 中逐项核对）。*
