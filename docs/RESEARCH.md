# 研究协议（Research Protocol）v1

> 状态：**生效中**｜版本：v1｜日期：2026-10-31｜实现：`medradar/stats.py`、`medradar/calibration.py`
> 本文档是 MedRadar 一切"数字结论"的**事前规则**。任何对外发布的数字，必须能回答三个问题：
> ① 用什么样本算的？② 多重检验怎么处理的？③ 缺失/偏差被标出来了吗？
> 方法细节见 [`docs/METHODS.md`](METHODS.md)，数据契约见 [`docs/SCHEMA.md`](SCHEMA.md)，
> 校准报告见 [`docs/CALIBRATION.md`](CALIBRATION.md)。

---

## 0. 一页速览

| 问题 | 本项目当前答案 |
|---|---|
| 研究性质 | **假设生成（hypothesis generation）**，不是策略验证，不是投资建议 |
| 观察单位 | 一条公开监管/临床事件（`events` 行）+ 一个信号（`signals` 行） |
| 时间锚点 | `event_date` = 事件**最早可公开获知**的日期；信号日 = `event_date + 1` |
| 主统计量 | 事件后 h 个交易日的**异常收益**（个股收益 − SPY 同期收益），h ∈ {1, 5, 20, 60} |
| 不确定性 | 按**事件日分块的 block bootstrap**（不是 i.i.d. bootstrap） |
| 多重检验 | 家族 = 信号类型 × 持有期，Holm 逐步下降法控制 FWER 0.05；Bonferroni 作上界 |
| 样本切分 | 按事件日/申报日**时间切分** dev 60% / validation 20% / holdout 20%，同日不跨阶段 |
| 权重 | 默认等权；市值权重只用于描述性分析，且必须用**当时**市值（当前版本只做等权结论） |
| 生存偏差 | `stats.survivorship_flags` 显式标记缺价格/已退市标的，报告必须显示该计数 |
| 校准 | LLM 判定经**可回放 fixture** 复现（`tests/fixtures/calibration/`），无 key、无网络可重跑 |

**一句话结论**：本仓库能对外说"我们观察到了 X，样本 n=…，Holm 校正后 p=…，区间为 …，
且有 N 个标的因数据缺失未进入样本"；**不能**对外说"模型准确率 100%""策略年化 X%""可以据此交易"。

---

## 1. 研究问题与可证伪假设

每条假设都写明**否证条件**与**检验家族**。未经本表登记的假设，其 p 值只能算探索性结果。

| ID | 假设 | 检验方式 | 否证条件 |
|---|---|---|---|
| H1 | 器械获批/首次产品码类信号（`device_novel_code`、`device_new_track`）之后 20 个交易日的异常收益 > 0 | 单侧方向 + block bootstrap CI + Holm（家族 S） | 20 日平均 AR ≤ 0，或 Holm 校正后 p > 0.05 |
| H2 | 药品 ORIG NDA/BLA 批准（`drug_approval`）之后 5/20 日 AR > 0 | 同上 | 同上 |
| H3 | III 期试验登记（`trial_start`）之后 60 日 AR 与 0 无差异（登记是流程性信息，不应当是催化剂） | 双侧检验，**预期不显著** | 显著为正/负即说明数据或信号有前视/混淆 |
| H4 | 召回聚集（`recall_cluster`）之后 20 日 AR < 0 | 方向 −1 的 AR，单侧 + Holm | 平均 AR ≥ 0，或 CI 覆盖 0 |
| H5 | LLM 判定在**类型**（4 类）与**方向**（−1/0/+1）上优于关键词基线 | 配对比较（同一 25 份文件），报告差值而非单独 p | 类型准确率差值 ≤ 0 或高材料性 F1 差值 ≤ 0 |
| H6 | LLM 材料性存在系统性高估 | 材料性 bias = mean(pred − gt) | bias 的 95% CI 覆盖 0（当前观测 +0.123） |

> 家族的 p 值必须来自**同一批**事件（同一 DB 快照、同一窗口），不得为了显著性更换窗口。

---

## 2. 观察单位与反前视（anti-lookahead）规则

1. 事件日期一律使用**最早公开可获知日**（`docs/METHODS.md` §1）：510(k) 用 `decision_date`、
   试验用 `studyFirstPostDate`、召回用 `center_classification_date`。
2. 交易/信号只在 `event_date + 1` 之后生效；事件研究**入场 = 信号日之后第一个交易日开盘价**，
   禁止用信号日收盘价或当日开盘价。
3. 任何"当时不可知"的字段不得进入特征：当前市值不能给历史事件加权（见 §6）；
   公司归属只能用当时已存在的主体（子公司清单本身是今天的知识，这一项只能作为已知局限）。
4. `payload.backfill = true` 的回填告警永不成交（见 `docs/SCHEMA.md` §8）。

---

## 3. 样本与切分

### 3.1 事件研究样本

* 窗口：`docs/metrics.json` 的 `meta.window`（当前 2025Q1–2026Q4，8 个季度）。
* 信号总量：303 条（`trial_start` 198、`device_novel_code` 47、`drug_approval` 37、
  `recall_cluster` 20、`device_new_track` 1）；`device_new_track` 仅 1 条，**不单独检验**，
  只并入描述性汇总。
* 切分（按 `signal_date` 时间排序，同日整体归入同一阶段）：

  | 阶段 | 占比 | 用途 |
  |---|---|---|
  | dev | 60% | 允许调参、挑窗口、选阈值；结果**不得**对外作为证据 |
  | validation | 20% | 只在 dev 方案冻结后看一次；用于确认不是单点过拟合 |
  | holdout | 20% | **发布前不看**；只在最终复核时跑，且不得据此回头改方案 |

  实现：`medradar.stats.time_split(signals, key="signal_date", fractions=(0.6, 0.2, 0.2))`
  （切事件行时 `key="event_date"`；切校准记录时 `key="filed"`），
  切点会向前吸附到日边界，保证同一天不会被拆到两个阶段（否则会通过 §4 的分块结构泄漏）。
  默认只返回 `bounds`（各阶段的起止日/条数），需要分阶段事件列表时传 `return_items=True`。

### 3.2 校准样本（25 份 8-K）

按申报日 `filed` 用**日历年边界**切分
（`stats.time_split_by_dates(records, dev_end="2024-12-31", validation_end="2025-12-31", key="filed")`）：

| 阶段 | 区间 | n |
|---|---|---|
| dev | 2023-03-06 – 2024-12-16 | 18 |
| validation | 2025-02-26 – 2025-07-30 | 5 |
| holdout | 2026-02-13 – 2026-03-03 | 2 |

> 若改用 60/20/20 的**比例切分**（`stats.time_split(records, key="filed")`），结果是
> dev 15（2023-03-06 – 2024-10-29）/ validation 5（2024-11-12 – 2025-04-01）/
> holdout 5（2025-04-03 – 2026-03-03）；两种切分都不共享同一申报日。本文协议采用日历年边界，
> 因为它对读者可解释，且与 `analyze` 的 `research.sample_split` 口径一致。
>
> 现有 `docs/CALIBRATION.md` 的指标是**全 25 份**的试点结果（历史上没有按阶段分别报告）。
> 因为 n=25，dev 已占 72%，任何"按阶段重算"都只是把同一批数据切碎。协议要求：
> 下一次扩样（目标 100 份）必须先在 dev 上冻结 prompt/schema，再报 validation/holdout；
> holdout n=2 只能发现"灾难性错误"，不能证明准确率。

---

## 4. 统计方法

### 4.1 分块 bootstrap（block / cluster bootstrap）

事件收益存在**重叠窗口相关**：相邻事件的 20 日 AR 可能重叠 19 天，同一天的多个事件也共享
市场冲击。因此有效样本量是**事件日数**，不是事件数。i.i.d. bootstrap 会低估方差。

设事件日 g 下的观测为 {y_i : g(i) = g}，G 个块。每次重采样**整块**抽取 G 次（有放回），
拼接后计算统计量，重复 B 次，取分位数 [α/2, 1−α/2] 作为区间（percentile bootstrap）：

```
θ*_b = stat( union of blocks drawn in replication b ),  b = 1..B
CI    = [ Q_{α/2}(θ*),  Q_{1−α/2}(θ*) ]
```

有效性随**块数** G 渐近成立（Cameron–Gelbach–Miller），故 G < 2 时不报告区间（返回 `null`），
而不是伪造一个。默认 `B = 2000`、`seed = 7`，可完全复现。

API：`stats.block_bootstrap_ci(values, blocks, *, n_boot=2000, alpha=0.05, seed=7)`。

### 4.2 事件研究聚合

对每个 horizon h、每个 `kind`（及 `all`）报告：

* `n`（有效事件数）、`n_blocks`（事件日数）；
* `mean`（默认等权；有 `weight` 字段时加权）、`median`、`std`；
* `t = x̄ / (s/√n)`、双侧 `p_value`（仅等权；加权时 `t = null`，因为加权均值没有干净的 t 分布）；
* `ci95`（block bootstrap）、`hit_rate` 及其 block bootstrap 区间；
* `mde`（该 n 下的最小可检测效应，见 §4.5）。

API：`stats.aggregate_event_study(events, horizons=(1,5,20,60), returns_key="ar", block_key="event_date", ...)`。
输入行示例：`{"event_date": "2025-03-03", "kind": "drug_approval", "ar": {"1": 0.012, "5": null}}`。
**缺失记为 missing，绝不按 0 处理。**

### 4.3 多重检验

已登记的检验家族 = 有足够样本（n ≥ 3）的 `kind × horizon` 组合（典型 4 类 × 4 期 = 16，
加上 `all` 共 20 个"look"）。规则：

1. 主报告：**Holm 逐步下降**（FWER ≤ 0.05，不要求独立性，一致优于 Bonferroni）；
2. 同时给出 Bonferroni 校正值作为**保守上界**（Holm 的 adjusted p 恒 ≤ Bonferroni 的）；
3. `t = 2`（p ≈ 0.05）在 20 次观察下**不构成证据**；
4. 未在 §1 登记的假设，其 p 值只能是"探索性"，正文必须标注 `exploratory`，不得进入结论句。

Holm 定义（升序 p_(1) ≤ … ≤ p_(m)）：

```
p_adj_(k) = max_{j ≤ k} min(1, (m − j + 1) · p_(j))
reject k  ⇔  p_adj_(k) ≤ α
```

API：`stats.multiple_testing(p_values, method="holm", alpha=0.05, labels=[...])`。
返回里 `adjusted` 是**报表友好**的 dict 列表（`key` / `raw_p` / `adjusted_p` / `significant`，
按 adjusted p 升序，`metrics.research` 与报告表格直接消费），`adjusted_p_values` 是与输入
p 值一一对应的数值列表（供程序化 join）。

### 4.4 方向与命中率

* 方向准确率：`direction ∈ {−1, 0, +1}` 完全一致的比例；
* 命中率：AR > 0 的比例（方向已按信号方向取号），同时给出 block bootstrap 区间；
* 高材料性（≥ 0.5）分类：Precision / Recall / F1，用于回答"该不该下单"。

### 4.5 样本量 / 功效提示

正态近似下的一样本最小可检测效应：

```
MDE = (z_{1−α/2} + z_{power}) · σ / √n
```

`n` 固定时 20 日 AR 的 σ 通常约 0.10–0.15，n=20 → MDE ≈ 0.06–0.09，即**只有 ±6–9% 的效应
才可能被看见**。报告的每个 horizon 都带 `mde`；`stats.power_hint` 会把
"观测效应 / 满足所需 n / 是否 underpowered" 写成中文提示，供报告"方法与局限"章节引用。

---

## 5. 权重（equal vs market-cap）

* **默认等权**：不需要额外数据，且不会把"今天的市值"泄漏到历史事件（用当前市值给 2019 年
  事件加权是前视偏差 + 生存偏差的双重错误）。
* 市值权重 `stats.market_cap_weights(caps, cap=0.05)` 仅用于**描述性**组合分析；使用时必须：
  ① 用事件发生时的市值快照；② 报告单票上限（cap）与触发次数；③ 在报告中注明"weighted"。
* 等权/加权的 `ci95` 都按分块 bootstrap 计算；加权时不给 t/p。

---

## 6. 生存偏差与缺失数据

`stats.survivorship_flags(entities, price_tickers=..., delisted=..., listed_until=..., window_end=...)`
把"因为我们拿不到它的价格，所以它不在结果里"标出来，理由只有三种，全部机械判定：

| 理由 | 含义 | 报告处理 |
|---|---|---|
| `no_ticker` | 无美股代码（A 股/港股/未上市） | 不计入美股收益样本，计数公开 |
| `no_prices` | 有代码但价格层缺失（退市、被并购、OTC） | 同上；这类缺失**系统性偏向多头** |
| `delisted_before_window_end` | 明确退市或 `listed_until` 早于窗口末 | 同上 |

`metrics["research"]["survivorship"]["flagged"]` 必须出现在报告与看板里。
同时：`meta.data_status.nmpa = "unavailable"` 时，`cn_gap` 一律为 `null`，
禁止把"无数据"写成"空白度为 0"（见 `docs/SCHEMA.md` §4）。

---

## 7. LLM 判定校准协议

校准回答"judge 的判定可不可信"，不回答"策略赚不赚钱"。协议要点：

1. **标签先于判定**：人工标注在任何 LLM 调用之前完成（避免锚定），存
   `docs/calibration/ground_truth.csv`。
2. **只用生产 prompt/schema**：`medradar/llm.py` 的 system prompt、JSON schema、温度 0。
3. **保存原始响应**：每次调用记录 raw response、prompt 版本（`PROMPT_VERSION`）、模型名、
   UTC 时间戳、耗时（`run_calibration` 写 `verdicts.jsonl`、`raw_responses/<id>.txt`、
   `manifest.json`）。
4. **可回放**：`ReplayJudge` 按内容指纹（`sha1(PROMPT_VERSION|headline|text[:24k])`）从
   `tests/fixtures/calibration/` 回放录制响应，判定在回放时用生产 `parse_verdict` **重新解析**；
   回放与调用顺序无关、幂等，CI 无 key 无网络可复现（`python docs/calibration/score.py`）。
5. **绝不硬编码判定**：源码里不允许出现任何 `cal-XX` 判定字面量（测试
   `test_no_verdicts_are_hardcoded_in_the_harness` 守着这条）。
6. **诚实标注录制来源**：本仓库现有 25 份的 fixture 的 `raw_source =
   "reconstructed_from_parsed_verdict"`——原始模型字符串当时未留档，raw 字段由已解析判定重建，
   只用于复现**打分流程**，不构成对端点的独立验证。要升级为独立验证，必须配置
   `MEDRADAR_LLM_API_KEY` 并用 `HttpJudgeRecorder` 重跑同一批文件。
7. **指标**：类型混淆矩阵/准确率、方向准确率、材料性 Spearman/MAE/RMSE/bias、
   高材料性（≥ 0.5）P/R/F1、每类仓位影响；分母一律是可用判定数，错误/缺失单独计数。
8. **扩样要求**：目标 n=100（每类 25），双人独立标注并报告 Cohen's κ；加入混合型 8-K 与
   无明确事件词的噪声样本；同批文件对比主备模型。

命令：

```bash
# 离线复现（无 key、无网络）
python docs/calibration/score.py

# 真实端点校准（需要 key；会覆盖同目录的 run 产物，fixture 不动）
MEDRADAR_LLM_API_KEY=... python -m medradar.calibration run \
  --judge http --filings data/calibration/filings \
  --labels docs/calibration/ground_truth.csv --out data/calibration/runs/http
```

---

## 8. 局限（引用任何数字前先读）

1. **样本量小**：事件研究单类事件常 < 50；校准 n=25 且单标注者。n=25 时 MDE 约 0.06（20 日 AR），
   只能看见大效应；不要把"不显著"读成"无效应"。
2. **名称口径**：`CompanyRegistry` 的漏检/误检是最大误差源；未匹配事件被计数而非插补，
   大集团（J&J、GE、Medtronic）系统性低估（见 `docs/METHODS.md` §2）。
3. **批准 ≠ 研发投入**：510(k) 与 PMA、仿制药与首创药、并购带来的证件都会扭曲"批准数"。
4. **发布延迟**：openFDA 滞后 2–12 天；周频任务可以吸收，日内策略不行。
5. **免费价格数据**：无 bid/ask、无借券费、无并购逼平、退市收益缺失 → 多头回测被美化；
   v1 只做多，明确**高估**可实盘性。
6. **LLM 校准是试点**：类型准确率 100% 建立在"标题即含事件词"的样本上，真实 8-K 有大量
   模糊/混合文件，应对 100% 乐观打折；材料性有 +0.12 系统性高估，线上建议乘 0.85 收缩系数。
7. **共同偏置**：人工 rubric 与 LLM prompt 同源，可能同时偏向同一解读。
8. **NMPA 缺失**：无 CSV 时中国空白度不可用；demo 数据永远不参与计算。
9. **多重检验之外的 p-hacking**：窗口、horizon、kind 的组合本身就构成隐性的多重比较；
   本协议只能约束"已登记家族"，不能消除未登记的探索。
10. **公司主体知识是今天的**：子公司映射表用了当前知识，历史归属可能不准确（已知局限，未建模）。

---

## 9. 哪些结论可以对外，哪些只能内部

| 结论类型 | 可对外？ | 措辞要求 |
|---|---|---|
| 数据覆盖/事件计数（"过去 8 季度共 303 条信号"） | ✅ | 注明窗口、来源、未匹配计数 |
| 描述性趋势（THI、赛道热度、结构迁移） | ✅ | 必须写"收缩后指标，非投资建议" |
| 校准指标（类型/方向/材料性） | ✅（有限） | 必须同时给 n、Spearman/MAE、`raw_source` 与"试点"字样；**禁止**单独引用"100% 准确率" |
| 事件研究平均 AR + CI + Holm 校正 p | ✅（有条件） | 必须同句给出 n、block bootstrap 区间、校正方法与"假设生成"定位 |
| 单条信号的"预期收益" | ❌ | 样本不足，属个案 |
| "策略年化收益 / 夏普" | ❌ | 未建模借券费、滑点、容量；只能作为模拟盘演示并标注"非实盘" |
| "某公司因 X 即将上涨" | ❌ | 不做个股推荐 |
| 中国空白度（NMPA 不可用时） | ❌ | 只能写"不可用（NMPA 数据未加载）"，禁止写 0 |
| LLM"准确率 100%"作为独立验证 | ❌ | 只有 fixture 回放，不构成端点验证；需 key 重跑后升级 |

---

## 10. 可复现性清单

| 机制 | 位置 |
|---|---|
| 固定随机种子（默认 7） | `stats.DEFAULT_SEED` |
| 分块/事件日定义 | `stats.aggregate_event_study(block_key="event_date")` |
| 冻结的校准录制 | `tests/fixtures/calibration/{manifest.json,filings,llm,heuristic}` |
| 录制来源与日期 | fixture `manifest.json` 的 `suites.<suite>.{source,recorded_at,raw_source}` |
| 计时无关的指标指纹 | `run_calibration(...)["metrics_sha1"]`（两次重跑必须相同） |
| 提交的指标快照 | `docs/metrics.json`、`docs/calibration/metrics.json` |
| 离线测试 | `python -m medradar selftest`（全量离线测试，含统计/校准测试，0 网络） |

复现命令：

```bash
cd D:\DEPPSKK\medradar
$env:PYTHONPATH = "D:\DEPPSKK\medradar"

python -m medradar selftest        # 全量离线测试
python docs/calibration/score.py   # 回放校准，校验并重写 metrics.json
```

---

## 11. 变更控制

* **改 prompt/schema** → 必须 bump `medradar.llm.PROMPT_VERSION`；旧 fixture 的指纹随之失效，
  必须重录（`python -m medradar.calibration export-fixtures`），并在 `docs/CALIBRATION.md`
  记录新版本与日期。
* **改统计方法**（block 定义、alpha、seed、多重检验方法）→ 先改本文档，再改代码；
  报告必须标注方法与版本。
* **改样本窗口/切分** → 视为新的研究轮次，新的 dev/validation/holdout，不与旧结果混算。
* **任何对外数字** → 必须能在 `docs/metrics.json` / `docs/calibration/metrics.json` 中找到
  对应字段与样本量；找不到就不发。

---

## 12. 相关文档

* [`docs/METHODS.md`](METHODS.md) — 观察模型、公司解析、THI、JS、事件研究定义
* [`docs/SCHEMA.md`](SCHEMA.md) — `metrics.json` 契约（含 `research` 块）
* [`docs/CALIBRATION.md`](CALIBRATION.md) — 25 份 8-K 校准报告（试点）
* [`docs/ASSUMPTIONS.md`](ASSUMPTIONS.md) — 建模假设登记表（回放引擎）
* `medradar/stats.py` / `medradar/calibration.py` — 本文档的代码实现（每个函数带数学说明）
