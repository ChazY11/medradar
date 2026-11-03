# S-028 实验协议 / Experiment Protocol

This is the operational form of `PRE_REGISTRATION.md`. It describes exactly how to
run, verify and re-derive every number. The protocol was frozen before any model fit.

## 1. 执行顺序（不可颠倒）

```
0. s028_freeze.py          # hash PRE_REGISTRATION.md + HYPOTHESIS_REGISTRY.md
1. s028_feasibility.py     # label census + fidelity self-check (no model)
2. s028_experiment.py --mode validate       # reproduce frozen benchmark
3. s028_experiment.py --mode main --horizons 4,2 --randomisations 40
4. s028_stats.py           # bootstrap CIs, BH, MDE, stability, decision rules
5. s028_report.py          # generate results documents from artifacts
```

Step 2 **must print `OVERALL: PASS`** before step 3 may be interpreted. A failure means the
harness is wrong and no S-028 result exists.

## 2. 单元、风险集、标签（摘要）

- 单元：`(company c, track k, origin t)`，t 为季度首日。
- 风险集：c 可观察 且 k 可观察 且 `(c,k)` 在 `(t−36m, t]` 无 material 事件。
- 标签：`(t, t+H]` 内至少一次**合格**事件（Traditional 510(k) 或原始 PMA）。
- `H = 4 quarters`（主）/ `2 quarters`（次）。

## 3. 切分与净化

| 项目 | 规则 |
|---|---|
| 起点 | 季度首日，`t − 36m ≥ coverage_start` 且 `t + H ≤ coverage_end` |
| 训练集（在起点 t） | 所有 `cutoff < t` 且 `cutoff + H ≤ t` 的已成熟行 |
| 测试集（在起点 t） | `cutoff == t` 的行 |
| 最少训练起点数 | 3 |
| holdout | 最后 3 个"有净化训练集"的起点 |
| 严禁 | 随机打散、随机切分、K-fold、用未成熟标签训练 |

**Purge 规则原文：** `cutoff + horizon_months <= origin`。
**Embargo：** 由 purge 隐含（标签窗口与测试窗口不重叠）。

## 4. 特征集

- `B1_history10` = 10 个企业/赛道/对历史特征（`BASE_FEATURES`）。
- `B2_frozen_spec16` = 16 个特征（`BASE + ENTRY`），即冻结 E11 规格 → **任务书中的 B2 与 B3**。
- `G1_graph` = 16 + 12 个图特征 = 28。
- `G3_*` = 从 28 中删除一个特征组（peer-entry / similarity / twohop / cooccurrence /
  centrality / decay）。
- `B2g_hgb_spec16`、`G1g_hgb_graph` = 相同特征集 + `HistGradientBoostingClassifier`
  （稳健性，不作主结论）。

**所有主比较使用同一个学习器**：`FastLogisticRegression`，它是仓库
`LogisticBaseline(epochs=180, lr=0.15, l2=1.0)` 的向量化等价实现
（`parity_check` 实测最大绝对差 **3.5e-17**）。这保证特征集差异可归因于特征。

## 5. 随机化对照（G2）

> **CORRECTED in `S-028-CORRECTION-1`（2026-11-04）。** 本节写的程序（"重建一个保度随机快照"）在
> Phase 0–3 的**实现**中并未实现：72/72 次不变量检查失败（度序列漂移、边权塌缩、100% 随机边被
> 当作"新进入"）。协议文本保持不变以保留预注册记录；实际执行以 `code/s028_nullmodels.py` 的
> N1/N2 为准，见 `RANDOMISATION_DEFECT_ANALYSIS.md` 与 `G2_CORRECTION_RESULTS.md`。

- 每个起点、每个种子（`20261104 + r`, `r = 0..19`）重建一个保度随机快照。
- 仅 12 个图特征被替换；16 个 B3 特征、标签、样本、训练流程、purge、metric 全部不变。
- 每个种子跑完整滚动起点流程，得到 pooled AP 与 ΔAP(real − randomised)。
- 报告：20 个 ΔAP 的中位数/2.5/97.5 分位、真实 AP 在随机化分布中的分位。

## 6. 指标

- 主：`pr_auc`（Average Precision，仓库 `medradar.intelligence.evaluation.metrics.pr_auc`）。
- 辅：`roc_auc`、`brier`、`ece`（10 bins）、`precision_at_k`（K = ceil(0.10·n)）、
  `recall_at_k`、`false_positive_rate`、`mean_lead_time_days`。
- 每窗口报告 `n`、`positives`、`prevalence`。

## 7. 统计推断

| 项目 | 实现 |
|---|---|
| 配对 ΔAP | 同一 holdout 行集同时评分两个模型 |
| 置信区间 | **企业聚类 bootstrap**，整簇重采样，B=2,000，seed=7，95% 百分位区间 |
| MDE(80%) | `(z_{0.975} + z_{0.80}) × SE_bootstrap(ΔAP)` = `2.8016 × SE` |
| p 值 | bootstrap 中 `ΔAP ≤ 0` 的比例（单侧，配对） |
| 多重比较 | 预注册假设族内 BH q=0.10；同时报告未校正 CI |
| 稳定性 | 按年 / 企业 / 赛道分层；最小 n=10 且正样本≥5，否则标为 insufficient |
| 重复 | G2 随机化 20 次 |

## 8. 决策规则（摘自预注册，直接执行）

**H1 SUPPORTED** ⇔ (a) 主分析 ΔAP(G1−B2) 企业聚类 95% CI 在 ≥2/3 窗口排除 0；
(b) pooled ΔAP 在两种聚类（企业 / 企业—赛道对）下均排除 0；(c) 点估计 ≥ pooled MDE(80%)。

**H2 SUPPORTED** ⇔ 真实图 pooled AP > 40 次随机化 ΔAP 分布的第 97.5 百分位，且 H1 SUPPORTED。

**H1 NULL (well-powered)** ⇔ CI 含 0 且观测 |ΔAP| < MDE。
**H1 UNDERPOWERED** ⇔ CI 含 0 且 MDE > 合理效应量（此时禁止说"无效应"）。
**G1 ≈ G2** ⇒ 关系结构主张撤销（Outcome B）。

## 9. 停止规则

- H1 不成立 → 不进入 GNN；不改 target/horizon/metric/dataset 重试。
- H2 不成立 → 关系主张永久撤销。
- 本轮结束必须产出阶段报告，并明确下一阶段决策门槛。

## 10. 复现命令

```powershell
cd D:\DEPPSKK\medradar
$env:PYTHONIOENCODING="utf-8"
python research/studies/graph_early_signal_s028/code/s028_freeze.py
python research/studies/graph_early_signal_s028/code/s028_feasibility.py
python research/studies/graph_early_signal_s028/code/s028_experiment.py --mode validate
python research/studies/graph_early_signal_s028/code/s028_experiment.py --mode main --horizons 4,2 --randomisations 40
python research/studies/graph_early_signal_s028/code/s028_stats.py
```

All commands are deterministic given the fixed seeds and the SHA-256-verified input database.
`code/s028_stats.py` re-derives every reported statistic from the stored predictions, so the
analysis can be re-run without refitting any model.

