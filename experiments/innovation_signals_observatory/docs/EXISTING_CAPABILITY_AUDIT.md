# Phase 4 · 现有 AI 抽取能力审计（Work Package 1）

**日期**：2026-11-04（Asia/Shanghai）
**审计对象**：PR #19 `research/local-llm-foundation`、PR #20 `research/overnight-qlora-s030`、
`research/MISSION.md`、`research/DECISIONS.md`（D-028 / D-029 / D-030 / D-031 / D-074）、
以及 `experiments/local_llm_event_extraction/` 与 `experiments/local_llm_event_extraction/results/`。
**审计目的**：在写任何一行新研究代码之前，先确定「哪个能力已经存在、哪些结论已被证明、
哪些结论不能被再次稀释」。本文件只记录审计事实与可复用的接口，不产生新的科研结论。

---

## 1. Git 与依赖关系审计（先做，因为它决定基线）

### 1.1 实测的 PR 状态（`gh pr list`，2026-11-04）

| PR | 分支 | 状态 | 与本次工作的关系 |
|---|---|---|---|
| #17 | `maintenance/repository-consolidation` | OPEN / Draft | 文档与数据资产治理；与代码无依赖 |
| #19 | `research/local-llm-foundation` | OPEN / Draft | **本地模型抽取基础设施**：schema、prompting、parsing、validation、训练守卫、离线测试 |
| #20 | `research/overnight-qlora-s030` | OPEN / Draft | 基于 #19：隔夜 QLoRA 训练 + 四臂独立评价 + 中文晨报 |
| #15 | `research/s028-temporal-graph-early-signal` | OPEN / Draft | **本仓库代码最完整的基线**：Live Observatory、Product 2.0、TKG、studies、冻结研究流水线 |
| #13 / #14 | `feat/live-observatory-v1` / `feat/observatory-reliability-v1` | OPEN / Draft | 已被 #15 的分支历史包含 |

`main` 停留在 `b2a14c0`（PR #11 合并点），**本轮不修改 `main`**。

### 1.2 基线选择（代码依赖审计的结果，不是偏好）

招聘观察必须复用两套既有系统：

* **Live Observatory 采集与账本**（`medradar/observatory/`）：append-only 观察记录、
  `first_seen_at` 写一次不可覆盖、NEW/UPDATED/REMOVED 状态机、robots/限流/预算/断点续采。
  这套代码只在 `research/s028-...`（#15）上。
* **本地模型抽取基础设施**（`experiments/local_llm_event_extraction/`）：
  提示词渲染、JSON 解析、schema 校验、逐字引用定位、运行记录。这套代码只在 #19/#20 上。

两者互不包含，因此本轮建立了**显式的集成基线分支** `integration/phase4-base`：

```
integration/phase4-base = research/s028-temporal-graph-early-signal (4c6686f)
                        + merge research/overnight-qlora-s030 (5954d7d, 含 #19)
                        + fix(test): 一个时间脆弱测试的修复（见 §4）
```

Draft PR 以 `integration/phase4-base` 为 base 分支，**本 PR 的 diff 因此只包含 Phase 4 的工作**，
依赖关系在 Git 历史里可见，而不是靠口头说明。

### 1.3 合并中发现的既有缺陷（如实记录，未修改对方研究产物）

* `experiments/local_llm_event_extraction/results/overnight-2026-11-04/.gitattributes`
  带 UTF-8 BOM，git 在每次 merge/status 时告警
  `ARTIFACT_INDEX.json is not a valid attribute name`。属 #20 的冻结结果树，
  **本轮只记录、不修改**（修改会改变该目录的字节内容与 SHA-256 索引语义）。
* `pyproject.toml` 单处冲突（#15 的 `web` extra 与 #20 的 `local-llm` extra），
  已按「两者都保留」解决。

---

## 2. PR #19 提供了什么（可直接复用）

`experiments/local_llm_event_extraction/` 是一个**离线可测、拒绝越权**的抽取框架，
不是一次性的 notebook。可复用部分：

| 文件 | 作用 | 本轮用法 |
|---|---|---|
| `schema.py` / `schema/event.schema.json` | 事件抽取 JSON schema（v2：日期/词表修复） | **不可直接复用**：任务对象是监管事件 |
| `prompting.py` | 提示词模板渲染、模板 SHA-256、版本化 | 复用其「模板版本 + 哈希」纪律，新建 job-text 模板 |
| `parsing.py` | 宽松 JSON 解析 + 失败分类 | 复用 |
| `validation/schema_validator.py` | 结构校验 | 复用机制，换 schema |
| `validation/evidence.py` | **逐字引用定位**（quote 必须能在原文中找到） | **直接复用思想与实现**（本轮最关键的可核实性工具） |
| `validation/dedup.py`、`timefields.py`、`entities.py` | 去重、时间字段规范、实体校验 | 复用纪律 |
| `adapters/{hf_local,rule_based,mock}.py` | 模型/规则/mock 适配器 | 复用 `hf_local` 的加载与生成封装 |
| `scripts/run_real_document_experiment.py`、`scripts/env_probe.py` | 真实运行与资源检测 | 复用资源检测 |
| `training/guard.py`、`vrma_guard.py`、`checkpoint.py` | 训练前的显存/数据守卫 | **本轮不训练**，仅保留约束 |

同时 #19 已把「本地推理环境」固化为：Python 3.12 + torch 2.9.1+cu128 + transformers 5.22.1
+ peft 0.21.2，模型 `Qwen/Qwen3-4B-Instruct-2507`（revision `cdbee75f17c01a7cc42f958dc650907174af0554`），
本地权重 `D:\DEPPSKK\ml-models\Qwen3-4B-Instruct-2507`。本轮**直接复用该环境，不新建环境、不下载新模型**。

---

## 3. PR #20 已经证明了什么（必须原样保留的五条结论）

以下结论来自 #20 的真实运行，本轮**不得**用新的高分把它们盖过去：

1. **4B 模型可以在本地完成 QLoRA 技术训练。** 60 步、1200 s GPU 墙钟、验证 loss 0.00522，
   训练过程真实（前向/反向/参数更新/checkpoint/推理可用）。
2. **结构化抽取格式可以靠弱监督训练改善。** 同一测试集：JSON 合法率 B 0.750 → C 0.950，
   schema 通过率 0.650 → 0.850。
3. **训练损失接近零 ≠ 真实能力提升。** 训练 loss 0.0012、验证 loss 0.00522，
   但类别一致率 0.706 → 1.000 是在**源记录派生的银标签**上取得的，不是人工金标准；
   P/R/F1 为 `NOT_EVALUABLE`。
4. **负对照误报因为缺少弃答训练样本而恶化。** 负样本误报率 **B 0.000 → C 0.667**
   （C 臂在 3 个负对照中误报 2 次）。**这是本轮必须继承的头号风险。**
5. **模板化测试文档不能证明模型适用于真实人类语言。** #20 的测试集 `text_origin` 只有
   `structural_rendering` 与 `synthetic_narrative` 两类，**没有人写的真实文本**；
   这正是 Phase 4 要补的那一步（真实招聘描述）。
   另外，正式科研微调仍受**人工金标准缺失**限制：`RESEARCH_TRAINING_BLOCKED` 未解除。

### 3.1 #20 的四臂实测表（`results/overnight-2026-11-04/evaluation/ARM_TABLES.md`，prompt v2）

| 实验臂 | JSON 合法 | Schema 通过 | 逐字引用定位 | 弃答率 | 错误弃答率 | **负样本误报率** | 中位延迟(s) | 峰值显存(MiB) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B 未微调 Qwen3-4B | 0.750 | 0.650 | 0.750 | 0.400 | 0.294 | **0.000** | 28.6 | 3834 |
| C 探索性 QLoRA | 0.950 | 0.850 | 0.950 | 0.050 | 0.000 | **0.667** | 37.7 | 3963 |
| A0 规则基线 | 1.000 | 1.000 | 1.000 | 0.600 | 0.529 | 0.000 | 0.005 | — |
| A1 强化规则 | 1.000 | 0.800 | 0.800 | 0.600 | 0.529 | 0.000 | 0.005 | — |

**读法（不允许跳过的部分）**：C 臂在**格式**上全面领先，在**弃答纪律**上明确变差；
在这个规模（20 条测试样本，其中 3 条负对照）下，任何一对数字的差异都可能是噪声。
本轮不做新的 QLoRA 训练，正是因为这组数字还没有告诉我们「训练值得再投入」。

---

## 4. 基线审计中发现的一个真实缺陷（已修，已披露）

在 `integration/phase4-base` 上跑完整测试套件时，唯一失败的测试是：

`tests/test_observatory_core.py::test_filtered_change_queries_bind_every_parameter`

它把 `first_seen_at` 硬编码为 `2026-11-03T10:00:00+00:00`，再用
`ledger.change_rows(hours=24, ...)` 查询——而 `hours` 是**相对当前墙钟**的窗口。
也就是说：**这个测试只在它被写下的那一天通过**，之后会静默变成失败（本次审计时已失败 26 小时）。
这不是科研成果问题，是测试缺陷。修复方式是最小化的：把 fixture 改成相对 `now()`，
并在代码注释里写明原因。**没有任何研究产物、结论或数据被修改。**

> 这一条本身就是 Phase 4 评价方法的一部分：**「测试全绿」不是可继承的状态，而是一个需要
> 每天重新测量的状态**。任何声称「既有测试都通过」的说法，必须附带运行时间与失败清单。

---

## 5. 任务分工（本轮的执行契约）

### A. 确定性数据处理（优先，能由可信源字段确定的事实）

| 事实 | 处理方式 |
|---|---|
| 企业唯一 ID | `config/universe_v1.json` 的 `focus_companies`（本轮五家都在里面；其中 Dräger/Mindray 的 `roster_status` 是 `absent_from_curated_roster`，本轮**不擅自补名册**） |
| 职位 ID | 源站自带的 opaque posting id（Workday `id`），不是我们生成的 |
| 岗位发布时间 | 源站的 `startDate`（精度：日），或 JSON-LD `datePosted`；**相对字符串永不转成日期** |
| URL / 内容哈希 | 源 URL + 规范化正文 `content_sha256` |
| 首次观察时间 | **我们的墙钟**，写一次，永不覆盖 |
| 重复记录判断 | 规则化（见 `medradar/recruitment/identity.py`），不是模型判断 |

### B. 本地语言模型理解（语义、模糊、需要解释的部分）

| 任务 | 归属 |
|---|---|
| 岗位职责涉及的技术方向 | 模型臂（B）与规则臂（A）**同时**给出，逐条对照 |
| 研发能力要求、研发/非研发判定 | 模型臂，必须附原文引用 |
| 企业活动的语义分类 | 本轮不扩展到招聘以外的事件 |
| 跨文档技术关联候选 | 模型只提候选，关联由确定性证据核验 |
| 反证与不确定性标注 | 模型必须显式输出 `abstain` / `UNCLASSIFIED` / `uncertainty_note` |

**硬约束**：模型不得补出不存在的招聘、技术能力或研发活动；每条结论必须能在原文中逐字定位。

---

## 6. 任务兼容性判定：为什么 C 臂（既有 QLoRA 适配器）在招聘文本上不成立

| 维度 | #20 的适配器 | 招聘文本需求 | 是否兼容 |
|---|---|---|---|
| 输入 | 监管记录的模板化渲染/合成叙述 | 人类撰写的 5–18k 字符招聘描述 | 否 |
| 输出 schema | `event.schema.json`（事件类型、日期、企业、器械） | 岗位职能、技术方向、能力短语、弃答 | 否 |
| 训练数据 | 104 篇政府公开记录派生银标签 | 无（本轮故意不训练） | 否 |
| 日期语义 | 监管事件发生日 | 岗位发布日期（来源字段，非抽取） | 否 |
| 负对照 | 3 条器械分类记录 | 真实非技术岗位（Buyer/Planner 等） | 否 |

结论：**C 臂 = `NOT_RUN`**，原因是任务与 schema 不兼容，而不是「模型能力不足」。
把不兼容的分类器硬套到招聘文本上，再把错误结果解释成模型能力问题，是本轮明确禁止的推理。

---

## 7. 资源约束（来自 #19/#20 的实测，本轮据此约束自己）

| 项目 | 实测 | 本轮策略 |
|---|---|---|
| GPU | RTX 5080 Laptop，16 303 MiB | 单臂、batch 1、bf16 推理；不并发跑两个模型 |
| 4B 推理峰值显存 | 3.4–4.0 GB（#20 四臂表） | 有余量；但仍控制输入长度与输出长度 |
| 4B 单条延迟 | 25–38 s（长 prompt + 结构化输出） | 因此 B 臂样本量受控（数十条），并如实报告延迟 |
| 训练 | 60 步即需 1200 s，且曾因换页被中止 3 次 | **本轮不训练**；训练必须有独立数据和明确失败判定条件（未被满足） |

---

## 8. 审计结论（一句话版）

既有系统已经提供了「结构化抽取 + 逐字引用定位 + 弃答」的**基础设施**，
也提供了「4B 模型在真实 GPU 上可跑、格式可改善、但负对照会变差」的**负面证据**；
它**没有**提供任何关于真实招聘文本的能力证据。因此 Phase 4 的正确起点不是再训练一次，
而是：**先证明招聘数据可被合法、稳定、可核实地观察，再用真实岗位文本测量抽取可靠性。**
