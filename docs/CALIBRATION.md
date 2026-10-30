# 8-K 判定校准报告（Calibration）

> 样本：25 份真实 SEC 8-K（2023‑06 至 2026‑06）｜标注：人工逐份判定｜LLM：DeepSeek（生产默认
> `deepseek-chat`，JSON schema + 逐字证据）｜关键词基线：`HeuristicJudge`
> 结论先行：**类型准确率 100% vs 60%，方向 92% vs 72%，材料性 Spearman 0.80 vs 0.58。**
> 但 LLM 材料性系统性偏高约 +0.15，且样本小、单标注者——见 §6 局限。

---

## 1. 数据集怎么来的

构建脚本走 EDGAR 全文检索（`efts.sec.gov/LATEST/search-index`），按四类查询各取候选，
再按"新闻稿特征 + 事件关键词"过滤掉路演 PPT / 风险因素章节，最后每家只保留一份、人工确认：

| 桶 | 查询 | 入选数量 |
|---|---|---|
| 批准 | `announces fda approval` / `receives fda approval` / `fda approves` | 6 |
| CRL | `receives complete response letter` | 5 |
| 试验读出 | `announces positive topline` / `did not meet primary endpoint` | 9（正 4 / 负 5）|
| 财报 | `reports financial results` / `announces financial results` | 5 |

入选公司（均为美股上市、8‑K 主体为新闻稿附件，非 PPT）：
Verona、Autolus、Zevra、Day One、Elite、Iovance；Abeona、Disc、Citius、Galera、Aldeyra；
Aquestive、Reviva、Viridian、Armata、Spero、Avalo、VYNE、Theravance、Aerovate；
Madrigal、Ocular、Dare、Capricor、Heron。

标注在跑 LLM **之前**完成（避免锚定），标签存于 `docs/calibration/ground_truth.csv`。
材料性按与线上完全相同的 rubric 打分（0.8–1.0 首创获批/关键 III 期成功；0.5–0.79 有商业
价值的临床或监管胜利；0.2–0.49 增量标签/小适应症；0.0–0.19 行政性/财报）。

> 说明：LLM 判定通过 DSH 的并行子代理执行，使用与 `medradar/llm.py` 相同的 system prompt、
> JSON schema 与规则（温度 0、必须逐字引用证据），不是另一个宽松提示词。

## 2. 总体指标

| 指标 | LLM 判定 | 关键词基线 | 差值 |
|---|---|---|---|
| `catalyst_type` 准确率（4 类） | **1.000**（25/25） | 0.600（15/25） | +40pp |
| `direction` 准确率（−1/0/+1） | **0.920**（23/25） | 0.720（18/25） | +20pp |
| 材料性 Spearman ρ | **0.800** | 0.582 | +0.22 |
| 材料性 MAE | **0.146** | 0.184 | −0.04 |
| 高材料性（≥0.5）Precision | 0.94 | 1.00 | −0.06 |
| 高材料性（≥0.5）Recall | **0.94** | 0.50 | +44pp |
| 高材料性 F1 | **0.94** | 0.67 | +0.27 |

基线的高 Precision 是"少报"换来的：它只把 9/17 份真正高材料性文件识别出来，漏掉一半；
LLM 在保持 0.94 精确率的同时把召回从 0.50 提到 0.94。

## 3. 混淆矩阵

**LLM（行=人工真值，列=LLM 判定）**

| gt ＼ pred | approval | crl | trial_result | earnings |
|---|---|---|---|---|
| approval（6） | **6** | 0 | 0 | 0 |
| crl（5） | 0 | **5** | 0 | 0 |
| trial_result（9） | 0 | 0 | **9** | 0 |
| earnings（5） | 0 | 0 | 0 | **5** |

**关键词基线**

| gt ＼ pred | approval | crl | trial_result | earnings |
|---|---|---|---|---|
| approval（6） | 5 | 1 | 0 | 0 |
| crl（5） | 0 | 5 | 0 | 0 |
| trial_result（9） | **4** | 0 | 5 | 0 |
| earnings（5） | **5** | 0 | 0 | 0 |

基线的两类系统性错误：把 4/9 试验读出判成 `approval`，把 5/5 财报判成 `approval`。
后者在实盘里最危险——`catalyst_type == "earnings"` 是"不交易"的开关，判成 approval 就意味着
财报会被当成催化剂。

## 4. 逐份对照（材料性）

| id | 公司 | 真值 | 人工 | LLM | 基线 |
|---|---|---|---|---|---|
| cal-02 | Verona | approval | 0.80 | 0.90 | 0.50 |
| cal-09 | Autolus | approval | 0.70 | 0.88 | 0.25 |
| cal-13 | Zevra | approval | 0.60 | 0.85 | 0.25 |
| cal-14 | Day One | approval | 0.65 | 0.85 | 0.60 ⚠类型错 |
| cal-21 | Elite | approval | 0.15 | 0.42 | 0.25 |
| cal-24 | Iovance | approval | 0.80 | 0.85 | 0.50 |
| cal-15 | Abeona | crl | 0.50 | 0.82 | 0.50 ⚠方向错(+1) |
| cal-16 | Disc | crl | 0.60 | 0.85 | 0.25 |
| cal-18 | Citius | crl | 0.55 | 0.70 | 0.35 |
| cal-19 | Galera | crl | 0.60 | 0.88 | 0.40 ⚠方向错(+1) |
| cal-22 | Aldeyra | crl | 0.70 | 0.80 | 0.20 |
| cal-07 | Aquestive | trial+ | 0.55 | 0.42 | 0.35 |
| cal-29 | Reviva | trial+ | 0.70 | 0.85 | 0.60 |
| cal-30 | Viridian | trial+ | 0.85 | 0.85 | 0.50 ⚠类型错 |
| cal-31 | Armata | trial+ | 0.30 | 0.35 | 0.25 |
| cal-37 | Spero | trial− | 0.60 | 0.50 | 0.50 ⚠类型错 |
| cal-38 | Avalo | trial− | 0.35 | 0.42 | 0.35 |
| cal-39 | VYNE | trial− | 0.45 | 0.85 | 0.20 ⚠方向错(0) |
| cal-40 | Theravance | trial− | 0.65 | 0.90 | 0.20 ⚠类型错 |
| cal-41 | Aerovate | trial− | 0.60 | 0.90 | 0.50 |
| cal-06 | Madrigal | earnings | 0.20 | 0.17 | 0.20 ⚠类型错 |
| cal-17 | Ocular | earnings | 0.15 | 0.15 | 0.20 ⚠类型错 |
| cal-20 | Dare | earnings | 0.15 | 0.12 | 0.20 ⚠类型错 |
| cal-26 | Capricor | earnings | 0.15 | 0.15 | 0.20 ⚠类型错 |
| cal-28 | Heron | earnings | 0.15 | 0.15 | 0.20 ⚠类型错 |

## 5. 对仓位的实际影响

`仓位 = 5% × clamp(materiality, 20%, 100%)`，按类别取平均：

| 类别 | 人工真值 | LLM 判定 | 关键词基线 |
|---|---|---|---|
| approval | 3.12% | 3.96% | 1.96% |
| crl | 2.95% | 4.05% | 1.70% |
| trial_result | 2.81% | 3.36% | 1.92% |
| earnings | 1.00% | 1.00% | 1.00% |

LLM 能把"批准/CRL/试验"和"财报"拉开 4 个百分点的仓位差；基线把三类都压在 1.7–2.0%，
基本没有区分度。另有两个硬伤只有基线有：

| 风险 | LLM | 关键词基线 |
|---|---|---|
| 把负面催化剂判成"买入"（真值 −1，预测 +1） | **0** 例 | **2** 例（Abeona CRL、Galera CRL） |
| 把财报当催化剂 | 0 例 | 0 例（方向为 0 挡住了，但类型全错，属侥幸） |

## 6. 局限（不要跳过）

1. **n=25，单标注者**：没有第二标注者，无法计算 inter‑annotator agreement；材料性本身就是
   主观量，人工标签自身约 ±0.15 的噪声。
2. **类别在标题层面可辨**：25 份都是新闻稿，标题直接写 "Receives FDA Approval" / "Complete
   Response Letter" / "Topline" / "Financial Results"。真实 8‑K 里还会有大量混合型、模糊型
   文件，100% 类型准确率应当乐观打折。
3. **共同偏置**：人工标注和 LLM prompt 用的是同一份 rubric，可能同时偏向同一解读。
4. **样本非随机**：由 EDGAR 关键词检索筛出，偏向"有明确事件词"的文件；不含 8‑K 正文里顺带
   提及事件的噪声样本。
5. **材料性系统性偏高约 +0.15**：LLM 对批准/CRL/关键试验普遍给 0.82–0.90，而人工落在
   0.50–0.85。建议在线上乘一个 0.85 的收缩系数（或仅把材料性当**排序**用，不给绝对仓位）。
   25 个点不足以拟合更复杂的校准曲线，先不做 isotonic。
6. **模型部署差异**：本次用 DSH 子代理（DeepSeek）跑，生产默认是 `deepseek-chat` HTTP 端点；
   同提示词、温度 0，但部署差异会带来方差。
7. **方向上的两个错误都在财报**（Madrigal、Heron 判 +1，真值 0），财报不交易，因此对 P&L 无害。

## 7. 结论与下一步

* **可以上线**的是：类型判定（决定是否交易/是否跳过财报）+ 方向（决定多空）。这两项相对基线
  是数量级的改善，且基线会"买入 CRL"这个错误不可接受。
* **需要收缩**的是：材料性绝对值。建议 `effective_materiality = 0.85 × llm_materiality`，
  或只用分位数映射到 1%–5%。
* **下一步**：样本扩到 100 份（每类 25），双人独立标注算 Cohen's κ；加入"混合型 8‑K"
  （如同时含财报与临床数据）和"无明确事件词"的噪声样本；用同一套文件测 `deepseek-chat`
  与备用模型的稳定性。

## 8. 复现

```bash
# 1) 候选集：EDGAR 全文检索 + 新闻稿过滤（需要 network）
#    见本报告 §1；原始文本不入库，仅保留链接与哈希
# 2) 人工标签
docs/calibration/ground_truth.csv
# 3) LLM 判定（用生产 prompt/schema；本次经 DSH 子代理执行）
python -m medradar judge --file <filing.txt> --headline "<company> 8-K"
# 4) 打分
python docs/calibration/score.py
```

产物：`docs/calibration/{ground_truth,llm_verdicts,heuristic_verdicts,metrics.json}`。
