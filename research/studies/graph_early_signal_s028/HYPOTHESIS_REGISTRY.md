# S-028 假设登记表 / Hypothesis Registry

Each hypothesis is registered with its **falsifier**, the **exact statistic**, the
**pre-declared sample**, and its **decision rule**. A hypothesis is never "supported"
by a point estimate alone.

| id | hypothesis (Chinese) | formal null | statistic | pre-declared unit / split | falsifier | decision rule | status |
|---|---|---|---|---|---|---|---|
| **H1** | 控制企业自身历史、赛道历史与时间趋势后，真实企业—技术网络的历史结构特征仍提高未来首个合格监管活动的样本外预测 | ΔAP(G1−B2) ≤ 0 | Average Precision (AUPRC) difference, paired, enterprise-clustered bootstrap | P1 企业 51 / 赛道 38；H=4q 主，H=2q 次；24 / 26 起点；purge `cutoff+H ≤ origin`；holdout 最后 3 个可评估起点 | ΔAP 的 95% CI 包含 0，或点估计 < MDE(80%) | SUPPORTED 需 (a) ≥2/3 窗口 CI 排除 0 且 (b) pooled 两种聚类均排除 0 且 (c) ΔAP ≥ pooled MDE | NOT TESTED at freeze |
| **H2** | 真实连接比保度随机化连接携带更多信息 | randomized-graph AP ≥ real-graph AP | pooled AP(G1) vs the R=20 randomisation distribution; ΔAP(real − randomized) | identical rows, learner, hyperparameters, purge, metric; only edge assignment randomised | real AP 落在随机化分布 95% 区间内 | SUPPORTED 需 REAL pooled AP > randomization 97.5th percentile **and** H1 SUPPORTED | NOT TESTED at freeze |
| **H3** | 跨主体关系可提供更早信号 | 其他主体的先期活动与 c 的首次合格活动无预测关联 | (i) peer-entry feature coefficients/AP contribution; (ii) lead time at matched false-alarm budget | only features whose source events satisfy `available_at ≤ t`; lead time only after H1 | 无增量 AP；或 lead-time 差在匹配误报率下不优于基线 | 描述性，除非 H1 SUPPORTED；**不得**表述为合作/因果传播 | PARTIALLY TESTABLE (no company↔company edge, no author/institution data) |
| **H4** | 网络增益具有条件性（赛道/企业类型/时间异质） | ΔAP 在所有预先声明分层内均相同 | per-stratum AP and ΔAP with min n=10 / pos=5 | pre-declared strata: track, `is_major`, year | 只有个别分层显著且其余为零 | 全部分层如实报告；不得只报最好赛道；BH q=0.10 | NOT TESTED at freeze |

## 结果登记（2026-11-04 追加；预注册正文未改动）

> 结果只追加，不覆盖。证据：`artifacts/experiment_H4q.json`、`experiment_H2q.json`、
> `statistical_validation.json`。

| id | 结果 | 关键数字 | 判读 |
|---|---|---|---|
| **H1** | **NULL（well-powered）** | 主分析 ΔAP = **−0.00609**，company CI [−0.02219, +0.00450]，pair CI [−0.03347, +0.01043]，MDE 0.01943，0/3 窗口排除 0 | 图特征**没有**提高样本外 AP；点估计为负；可排除 >0.019 AP 的收益，但无法排除更小的收益 |
| **H2** | **不成立（方向相反）** | H4q 真实 0.06900 vs 40 次保度随机化 0.06919–0.08198（median 0.07432）；**40/40 随机化更优**。H2q 30/40 更优 | 真实连接安排在匹配随机安排下**不占优**；关系结构主张撤销 |
| **H3** | **未进入提前量分析** | 预注册规定 H1 必须 SUPPORTED 才做 lead-time | 按停止规则降级；且数据无企业↔企业/机构/论文关系，H3 只能以统计关联表述 |
| **H4** | **不可判定** | H4q 仅 6/38 赛道、5/51 企业达 n≥10/pos≥5 门槛；H2q 仅 1/1 | 不存在"某些赛道有效"的可报告证据；不得做事后赛道挑选 |

> **CORRECTED in `S-028-CORRECTION-1`（2026-11-04）。** 上表的 H1 与 H2 判读按本轮独立复核更正：
> - **H1**：数值不变（ΔAP −0.00609，CI 跨零，0/3 窗口），但 **"NULL (well-powered)" 标签作废**
>   （`INVALIDATED_FINDING`）。预注册合取规则的规则级 MDE 为 0.0374 AP（基线 49.8%），该规则在
>   0.0194 处功效仅 16.3%；pair 聚类 CI 上界 +0.0104 无法排除更小的增益。
> - **H2**：判读改为 **"不成立（理由：没有证据）"**，而不是 **"方向相反"**。Phase 0–3 的随机化实现
>   不具备其声明的保度性质（72/72 次不变量失败，见 `RANDOMISATION_DEFECT_ANALYSIS.md`）。修正后
>   有效零模型 N1/N2 重跑：H4q 仍为 40/40（p=1/41）但集中于单一窗口；H2q 无反转（16/40、20/40）。
>   见 `G2_CORRECTION_RESULTS.md`。
> - **H4**：唯一 pair 口径下 0/38 赛道、0/51 企业达标（比"不可判定"更强：无可报告分层）。
>
> 另：本文件与 `artifacts/prereg_freeze*.json` 记录的冻结哈希**不一致**（结果表是冻结后填入的），
> 该溯源限制已在 `CORRECTION_REPORT_ZH.md` §8 记录为 `UNRESOLVED_LIMITATION`。预注册的**期望内容**
> 可从哈希一致的 `PRE_REGISTRATION.md` 独立核验。

**最终 outcome：B — 网络特征没有超出强非图基线的额外信息。**
（按 `PRE_REGISTRATION.md` §11 的 A/B/C/D 分类；`statistical_validation.json` 的
`decision.outcome` 字段同此结论。）

### 修订记录

- `Amendment 1`（2026-11-04，在任何 G1/G2/G3 结果被观察到之前）：随机化 R 从 20 提到 40；
  明确零模型只检验"边排列"。见 `PRE_REGISTRATION.md` 末尾与
  `artifacts/prereg_freeze_amendment1.json`。

## H3 的可检验范围（冻结前已确认的数据事实）

数据面审计确认以下关系**不存在**，因此 H3 不能以它们的形式检验：

- **企业↔企业显式关系：不存在。** `temporal_edges` 仅含
  `COMPANY_WINS_CONTRACT`(3,372)、`COMPANY_DEVELOPS_PRODUCT`(1,087)、
  `PRODUCT_BELONGS_TO_TECHNOLOGY`(1,087)、`COMPANY_FILES_FINANCIAL_FACT`(34)。
  没有合作、供应链、许可、合资、专利共有人、共同申办等边。
- **论文作者 / 研究机构关系：不存在。** 冻结库只有聚合的 `publication_counts`(616)，
  无作者、无机构、无 paper-level 记录。
- **临床试验申办机构：不在冻结库。** 仅在产品库 `medradar.sqlite` 有 `ctgov` trial
  事件（55,592），且申办机构归属为字符串匹配、置信度字段存在缺失。

因此 H3 的合法形式只能是："**其他企业的先期公开活动，是否在统计上先于**目标企业的首次
合格活动"，且必须附上"这不是合作关系、不是传播、不是因果"的明示。任何把共现读作
合作或把领先读作因果的表述都违反本登记表。

## 记录规则

- 每次实验运行写入一个不可变 artifact，登记表引用其路径与哈希。
- 结果为负时登记表保留，不做删除；负结果进入 `NEGATIVE_RESULTS.md`。
- 修订只能追加：`### Amendment N (date) — 原因 / 修订前已知信息 / 修订内容`。
