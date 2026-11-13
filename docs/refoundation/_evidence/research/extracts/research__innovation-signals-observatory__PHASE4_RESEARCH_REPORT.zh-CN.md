# MedRadar Phase 4 · Innovation Signals Observatory（中文科研总结）

**日期**：2026-11-04（Asia/Shanghai）
**分支**：`research/innovation-signals-observatory`，base = `integration/phase4-base`
**工作区**：`experiments/innovation_signals_observatory/`
**状态分级**：`VERIFIED` / `EXPLORATORY` / `BLOCKED` / `NOT_RUN`（全文严格使用这四级）

---

## 0. 一句话结论

**今天可以可靠地观察五家企业当前公开的研发岗位**（五家全部找到合法、稳定、可核实的公开路线，
Medtronic 已全量采集 994 条、字段可用率 1.00）；
**但「招聘信号是否领先技术突破」这个问题今天仍然无法回答**，因为只有单次快照（存量而非流量）、
技术分类在岗位文本上的可迁移性只有 6.1%、并且独立证据核验容易成立到几乎无信息量。
本轮真正交付的是一条**可审计的研究链路**，以及这条链路上每一环的**实测失败与缺口**。

---

## 1. 本轮做了什么 / 没做什么

| 做了 | 产物 |
|---|---|
| 审计既有本地模型与抽取能力，确定可复用/不可复用边界 | `docs/EXISTING_CAPABILITY_AUDIT.md` |
| 预注册研究问题的操作化、三层评价指标、信号分级、关联规则 | `docs/PROTOCOL.md`（含「写定前已观察到什么」的披露） |
| 五家企业数据源调查 + 合法采集路线验证 | `docs/SOURCE_DISCOVERY.md`、`sources/deep_probe.py` |
| 真实岗位采集（Medtronic 全量 994；其余四家各 80 有界样本） | `results/2026-11-04/jobs_*.jsonl`、`collection_*.json` |
| 观察契约、身份/版本/去重、append-only 存储 | `medradar/recruitment/{records,identity,store}.py` |
| 确定性分类基线（A 臂）+ 覆盖诊断 | `medradar/recruitment/taxonomy.py`、`track_coverage_diagnostic.json` |
| 真实岗位文本上的本地 4B 模型实验（B 臂） | `docs/LLM_EXPERIMENT.md`、`results/2026-11-04/llm/` |
| 候选信号 × 独立证据核验（含「无独立支持」） | `docs/EVIDENCE_REPORT.zh-CN.md`、`evidence_linking.json` |
| 90 天前瞻观察方案与启动条件 | `docs/NINETY_DAY_PLAN.zh-CN.md` |

| 没做（且不应被读成做过） | 原因 |
|---|---|
| 新的 QLoRA 训练 | 训练损失≈0 已被证明不等于能力；负对照误报在微调后从 0.00 升到 0.67；本轮先验证数据与任务 |
| 招聘 → 未来产品/销量的预测 | 单快照 + 无人工金标准，任何预测都是噪声 |
| 趋势/领先滞后判断 | 需要 ≥2 次时间上分离的快照，本轮只有 T0（另有 20 分钟内的重复采集，仅用于稳定性） |
| 把「分类成功」写成「科学发现」 | 分类是工具，不是结论 |
| 部署任何持续运行的服务 | 长期观察需满足启动条件，本轮只交付命令、配置样例与离线测试 |

---

## 2. 直接回答六个科研问题

### 第一：我们今天是否能够可靠观察五家企业当前公开的研发岗位？

**能——五家企业全部 `VERIFIED`，但「可靠」的含义要说清楚。**

| 企业 | 路线 | 唯一 ID | 来源日期 | 描述 | 本轮采集 | 站点分母 |
|---|---|---|---|---:|---:|---|
| Medtronic | Workday 公开 JSON 端点 | 1.00 | 1.00（`SOURCE_DATE`） | 1.00 | **994（全量）** | 994 |
| GE HealthCare | Phenom sitemap + JSON-LD | 1.00 | 0.91 | 0.91 | 80（有界） | 1,035 |
| Philips | Phenom sitemap + JSON-LD | 1.00 | 0.95 | 0.95 | 80（有界） | 805 |
| Dräger | 官方电子招聘门户 + Beesite JSON | 1.00 | 1.00 | 0.96 | 80（有界） | 171 |
| Mindray | 北森官方 JSON 接口 | 1.00 | 1.00 | 1.00 | 80（有界） | 141（社招） |

「可靠」= 每条岗位有**来源自带 ID、来源日期（含精度）、可定位描述、来源 URL**，并且我们自己的
`first_seen_at` 与之严格分离。**不是**「覆盖全部岗位」：四家仍是 80 条有界样本，
分母（1,035 / 805 / 171 / 141）并没有取全。**未观察到的岗位不能推出企业没有招聘。**

重复采集稳定性（同一天两次）：小样本 2×200 条 → 身份重叠 **1.00**、内容哈希一致 **1.00**、
`first_seen_at` **100% 未被覆盖**；全量 20 分钟两次 → 身份重叠 **1.00**、**0 条消失**、2 条新增。

### 第二：AI 能否从真实招聘描述中提取可信的技术能力信息？

**规则臂（A）与本地 4B 模型臂（B）都能产出「结构上合规、引用可定位」的输出；
但可信度的瓶颈不在格式，而在①分类体系能否迁移到岗位文本、②模型是否在无技术内容的岗位上保持弃答。**
（详细数字见 §6 与 `docs/LLM_EXPERIMENT.md`。）

预先声明的判定规则：**没有人工金标准 → 不计算 Precision / Recall / F1**。
任何「一致率」都只对机器可核查的部分生效。既有的 QLoRA 适配器是监管事件专用的，
其 schema 与任务都不兼容招聘文本，因此 **C 臂 = `NOT_RUN`**，
而不是「模型能力不足」——把不兼容分类器的错误解释成能力问题是被本轮明确禁止的推理。

### 第三：是否存在值得长期观察的候选研发方向？有哪些独立证据或反证？

**存在候选，但没有一个达到「新兴方向」的证据门槛。**

* 992 个去重岗位中只有 **61 个（6.1%）** 能被确定性规则归入既有技术 track，形成 **10 个 `(企业×track)` 单元**。
* 其中 **8 个** 达到「候选技术招聘信号」门槛（定义：同企业、同 track、多个独立岗位 ID 同时存在）。
* 独立证据核验：**7 个 `INDEPENDENTLY_SUPPORTED`、1 个 `NO_INDEPENDENT_SUPPORT`（`wearable_remote`）、
  2 个 `UNKNOWN`（样本不足）、0 个 `CONTRADICTED`**。
* **但这条结论必须连同它的弱点一起读**：Medtronic 在既有器械证据库的 **23/38** 个 track 中都有事件，
  所以「同企业 + 同 track」的核验对这家企业**几乎自动成立**——它是必要但**很弱**的核验。
* 真正有区分度的字段是**方向新颖度**：`NEW_DIRECTION_CANDIDATE` **0 个**、`RECENT_ACTIVITY` **1 个**、
  `ESTABLISHED_DIRECTION` **6 个**、`NO_BASELINE_DATA` **3 个**。
  → **本轮没有任何一个单元被建议升级人工审查**（门槛：≥3 个独立岗位 ID **且** 新颖度为新方向/近期活动）。

**反证与「找不到支持」是结果，不是空白**：`wearable_remote` 在证据库中 0 条美敦力事件；
`surgical_robotics` 有 20 个机器人相关岗位，但**没有任何一个**被归入该 track（全部被函数门槛压制为销售/未分类），
且证据库中 Medtronic 的 `surgical_robotics` 事件为 0、CT.gov 自主手术相关研究为 0
——这正是「岗位 ≠ 研发项目」的直接例证。

### 第四：招聘数据能否成为 MedRadar 长期研究企业战略转向的有效数据源？目前缺什么？

**能作为「观察层」的数据源（已证明可采集、可核实、可去重），但现在还不能作为「信号层」的数据源。**

缺的四件事，按重要性排序：

1. **时间序列**：目前是存量（stock），`source_posted_at` 横跨 2025-11-07 … 2026-11-04。
   需要 ≥8–12 周的连续采集，才能区分「新增 / 修订 / 下架」并把岗位数从存量变成流量。
2. **可迁移的技术分类**：既有设备 track 词表是为产品编码/监管文本建的，在岗位文本上只覆盖 6.1%
   （`surgical_robotics` 在 80 个岗位里被提到，但 0 个被归类）。这不是「企业没有这些岗位」，
   是**分类器不迁移**。需要岗位专用的技术能力词表（并保持与既有 taxonomy 的可映射关系）。
3. **可判别的独立证据**：现有器械证据库只有 2024-10-01 … 2026-10-28 的近期窗口，
   且同企业同 track 的核验几乎自动成立。要检验「领先性」，需要**带时间戳的、能区分方向新增 vs 既有**
   的独立证据（监管审批/试验/论文/官方公告），且时间跨度 ≥2 年。
4. **人工金标准**：没有人工标注，就无法给出任何准确率；只能给出可核查性（引用可定位、弃答是否正确）。

### 第五：现有 4B 模型适合什么、不适合什么？是否有必要为招聘文本单独微调？

**适合**：结构化抽取的**格式**工作（JSON/schema 合规）、把长文本压缩成带原文引用的候选标签、
在同一批文本上做**可对照**的第二意见。
**不适合**：被当作事实来源（它会漏、会过度归类）、被当作校准概率（置信数字无概率意义）、
在**没有技术内容的岗位上保持弃答**（这是本轮最重要的风险，见 §6 与 #20 的负对照结果 C 臂 0.67 误报）。
**是否要微调**：**现在不需要**。理由：① 招聘文本的真实任务边界还没定义清楚（A 臂覆盖 6.1% 正是证据）；
② 没有人工金标准，微调后的「提升」无法与「过拟合到我们自己写的规则」区分；
③ #20 已经证明微调会显著恶化负对照纪律。
先做的工作是：定义岗位技术能力词表 + 人工抽检 50–100 条建立小型金标准，再决定是否训练。

### 第六：还需要多长时间、什么类型的数据，才能真正开始检验招聘信号是否领先技术突破？

| 阶段 | 需要什么 | 现实估计 |
|---|---|---|
| 可用时间序列 | 同一企业连续采集，能区分新增/修订/下架 | **≥8–12 周** |
| 技术方向可分类 | 岗位专用词表 + 人工抽检（50–100 条金标准） | 2–3 轮迭代 |
| 观测到「变化」 | track 级岗位结构变化（不只是数量波动） | **可能 90 天内不发生** |
| 检验「领先性」 | 带时间戳的独立证据与招聘序列对齐，预注册检验方式 | **≥12–24 个月连续数据** |

这不是工作量问题，是**数据成熟度**问题：时间尺度由「企业实际多快发布新方向岗位、
监管/试验证据多快出现」决定，不由我们加班决定。

---

## 3. 交付物清单与状态

| # | 交付标准 | 产物 | 状态 |
|---|---|---|---|
| 1 | 五家数据源调查与可行性矩阵 | `docs/SOURCE_DISCOVERY.md` + `source_probe_*.json` | **VERIFIED**（五家全部找到合法路线） |
| 2 | 至少一个合法来源的真实端到端采集 | `jobs_medtronic.jsonl`（994）+ 四家各 80 | **VERIFIED** |
| 3 | 可重复运行的招聘观察适配器 | `medradar/recruitment/*`、`scripts/collect_recruitment*.py` | **VERIFIED**（离线测试 + 实跑） |
| 4 | 职位身份/版本/时间/去重机制 | `identity.py`、`store.py`、`records.py` | **VERIFIED**（含哈希规则变更保护） |
| 5 | 本地模型对真实岗位文本的分类试验 | `docs/LLM_EXPERIMENT.md`、`results/.../llm/` | **EXPLORATORY**（真实文本、小样本、无人工金标准） |
| 6 | 确定性规则与模型输出对照 | 同上 ARM 表 | **EXPLORATORY** |
| 7 | 中文可读的早期研发活动证据样例报告 | `docs/EVIDENCE_REPORT.zh-CN.md` | **VERIFIED**（可回查每条判断） |
| 8 | 真实失败、误归因与数据缺口记录 | 见 §7 | **VERIFIED** |
| 9 | 90 天前瞻方案与启动条件 | `docs/NINETY_DAY_PLAN.zh-CN.md` | **VERIFIED**（设计）+ **NOT_RUN**（部署） |
| 10 | 独立 Draft PR + 中文总结 | 本文件 + PR | **VERIFIED** |

---

## 4. 观察链路：从公开来源到可核实记录

```
企业招聘页（公开、无需认证、robots 允许）
  → 采集器（限速/预算/robots 断言/失败即记录）
  → JobObservation（来源 ID + 来源日期与精度 + 内容哈希 + 我们的 first_seen_at）
  → append-only store（NEW / UNCHANGED / REVISION / REMOVED / REAPPEARED / UNREADABLE / HASH_RULE_REBASELINED）
  → 确定性分类（函数类 + 技术 track + 原文引用 + 规则依据）
  → (企业 × track × 时间) 单元
  → 候选信号（不是结论）
  → 独立证据核验（含「无独立支持」与「基线不足」）
```

这条链路上每一环都有测试或实测证据；每一环都允许「不知道」，并把「不知道」写进数据。

---

## 5. 技术分类的实测：为什么 6.1% 不是「企业没有这些岗位」

**先看分类器自己的产出（994 条，规则臂 A，确定性）**：

| 函数类 | 岗位数 | 占比 |
|---|---:|---:|
| `SALES_ADMIN_OTHER` | 585 | 58.85% |
| `UNCLASSIFIED` | 132 | **13.28%** |
| `QUALITY_REGULATORY` | 88 | 8.85% |
| `ALGORITHM_SOFTWARE` | 70 | 7.04% |
| `MANUFACTURING_PROCESS` | 47 | 4.73% |
| `PRODUCT_ENGINEERING` | 34 | 3.42% |
| `CORE_R&D` | 14 | 1.41% |
| `CLINICAL_R&D` | 13 | 1.31% |
| `HARDWARE_SYSTEMS` | 11 | 1.11% |

`UNCLASSIFIED` 的 132 条各有机制：**87 条**描述证据不足（低于 3 个不同短语门槛）、
**33 条**标题与描述都无任何线索、**12 条**两类描述线索打平。分类依据：598 条标题线索、
264 条描述回退、132 条弃答。**没有一条是「兜底强制赋值」**：
SALES_ADMIN_OTHER 585 条全部有原文线索（409 标题 + 176 描述），0 条因无线索而落入该类。

**track 赋值（6.14%）的质量必须一起报**：61 个被归入 track 的岗位中，
**50 个是 WEAK、11 个是 MODERATE；54 个只靠描述命中、7 个靠标题命中**。
换句话说：**6.1% 的覆盖率本身也已经是很弱的证据**，不能当作「这些方向被确认」。

再看**独立于词表**的通俗词探测（`track_coverage_diagnostic.json`）：

| track | 岗位提到该方向 | 被规则归入该 track | 说明 |
|---|---:|---:|---|
| `surgical_robotics` | **80** | **0** | 49 个是销售/现场岗位被函数门槛压制，18 个未分类，6 个产品工程类**也没能归类** |
| `medical_ai` | 141 | 25 | 37 个是算法软件岗、48 个销售、17 个质量/法规 |
| `ep_pfa` | 117 | 8 | 86 个是销售岗 |
| `neurostimulation` | 57 | 14 | 40 个销售岗 |
| `cardiac_rhythm` | 56 | 2 | 43 个销售岗 |

**结论**：既有设备 taxonomy 的关键词体系（为产品编码/监管文本设计）**不能直接迁移到岗位文本**。
这不是数据缺陷，而是**方法论发现**：要想从招聘观察技术方向，需要岗位专用的能力词表，
且必须把「卖这个产品」与「研发这个技术」用函数类别门槛分开——本轮的规则臂已经实现了这个门槛
（**717 个岗位被 `SUPPRESSED_BY_FUNCTION_CLASS`** 压制；若不设门槛，**168 个**岗位会被关键词
误标成技术 track），但也因此丢失了部分真实技术岗位（如 `surgical_robotics` 的 6 个产品工程岗）。

---

## 6. 本地模型实验（真实岗位文本）

**设计**：从 994 条真实岗位中按固定规则抽 20 条（12 条主样本 + **8 条真实负对照**：Buyer/Planner、
客服、仓库、行政、财务、非技术 Co-op 等标题明确非技术的在招岗位），两臂看**同一批文本**；
文本截断 3000 字符（两臂一致，公平性要求），`max_new_tokens=320`，batch 1，bf16，不训练、不联网。
模型：本地 `Qwen/Qwen3-4B-Instruct-2507`（权重指纹 `6e200db3…`）；提示词 `job-extract-v2`
（模板哈希 `76266549…`）；schema `medradar.job_text_extraction.v1`。
**样本量的偏差如实披露**：原计划 32+10，因实测延迟尾部（最长 193 s）降到 **12+8**（保留全部负对照）。

| 指标 | A 臂（确定性规则） | B 臂（未微调 4B） |
|---|---:|---:|
| JSON 合法率 | 1.000 | **1.000** |
| Schema 通过率 | 1.000 | **1.000** |
| 引用逐字可定位率 | 0.940（79/84） | **0.894（59/66）** |
| 函数类线索支持率 | 1.000（构造上循环） | **0.588** |
| 技术 track 线索支持率 | 1.000 | **0.500** |
| 弃答率 | 0.100 | **0.000** |
| **负对照误报率** | **0.000（0/8）** | **0.125（1/8）** |
| **内部自洽矛盾率** | **0.000（0/20）** | **0.200（4/20）** |
| 中位延迟 | 0.005 s | **20.9 s**（均值 36.4 s，p95 159.6 s，最长 193.0 s） |
| 峰值显存 | — | **13,199 MiB / 16,303 MiB（81%）** |

**A/B 一致率（只表示一致，不表示正确）**：12 条主样本中，双方都给标签 10 条、
函数类相同 8 条、**技术 track 相同仅 1 条**；A 判 `UNCLASSIFIED` 而 B 给了标签 2 条；反向 0 条。

**结论（四句话）**：
1. **格式不是瓶颈**：B 臂在 20 条真实文本上 JSON 与 schema 合规率都是 1.000。
2. **语义锚定才是瓶颈**：引用可定位率 0.894、线索支持率 0.588、**4/20 内部自洽矛盾**、
   **负对照误报 1/8**。A 臂在这些指标上更好，但覆盖率只有 6.1%。
3. **两臂都「从不弃答」到可疑**：负对照上两臂都没有一次 `abstain`（都改用 `SALES_ADMIN_OTHER` 吸收），
   所以 A 的 0 误报**部分是偶然**，不是被明确指示的行为。
4. **部署成本是硬约束**：中位 20.9 s/条、峰值显存 13.2/16 GB、最长 193 s 超时；
   「4B 在笔记本上可跑」是真的，「4B 可以批量处理」不是。

**5 个具体失败样例（可复查，全部来自 `adjudication_candidates.md` / `MANUAL_ADJUDICATION.md`）**：

| # | 岗位（真实标题） | 输出 | 问题 |
|---|---|---|---|
| 1 | Senior Marketing Specialist, EndoVenous（负对照） | 函数=`SALES_ADMIN_OTHER` + track=`peripheral_vascular`，引用 "Endovenous (EV) business" | **负对照误报**：把业务单元名当技术；且函数类引用并非逐字 |
| 2 | EP Mapping Specialist（销售/临床支持） | 函数=`SALES_ADMIN_OTHER` + track=`ep_pfa` | **内部自洽矛盾**：把「支持用什么产品」当「研发什么技术」 |
| 3 | Product Manager/Associate | 函数引用为**改写后的句子**（拼接小标题） | **引用不可逐字定位**（locatability 失败） |
| 4 | Senior Principal Software Engineer | track=`cardiac_rhythm`，引用 "…Cardiovascular, Medical Surgical and Neuroscience **portfolios**…" | **产品组合上下文被当成技术方向**（线索支持 = False） |
| 5 | Legal Counsel（A 臂） | 引用 `budget` | **我们自己的规则臂缺陷**：单复数匹配到 "budgets" 却输出 `budget` → 引用不可定位（5/5 未定位都是这一类，非幻觉）。已记录，未静默修补 |

另有一条不计入 FP 指标但必须写下的观察：B 臂把 **2/8** 条非研发负对照（法务、财务）判成
`QUALITY_REGULATORY` —— 它并非「技术方向」，但对非技术岗位给出研发类函数标签，同样是错误。

**C 臂 = `NOT_RUN`**：唯一既有 QLoRA 适配器是在监管事件文本上、按事件 schema（事件类别、
三个时间戳、企业实体、产品）训练的；招聘文本是不同任务、不同输出契约，且从未见过岗位文本。
硬套它测到的是「schema 不兼容」，不是「模型能力不足」——后一种解释本轮明确禁止。

**是否要为招聘文本单独微调？本轮结论：不需要（还不该）。** 三个理由：
① 本轮暴露的失败是 **角色 vs 产品（role-vs-product）监督缺失**（4/20 track overreach + 1/8 负对照误报），
不是格式问题；② 没有人工金标准，微调后的「提升」无法与「过拟合到我们自己写的规则」区分；
③ PR #20 已实测微调会让负对照误报从 0.000 升到 0.667。
**先做**：200–400 条人工标注岗位（含弃答样例）+ 冻结的负对照集 + 预先声明的判定规则
（训练必须在不降低引用可定位率的前提下降低负对照误报率与内部矛盾率），再决定是否训练。
在满足这些条件之前：**A 臂用于可审计的批量用途，B 臂只能作为「引用已核验的候选生成器」**。

---

## 7. 真实失败、误归因与数据缺口（必须保留的部分）

| 事件 | 事实 | 处理 |
|---|---|---|
| 首次 Medtronic 采集只得到 40 条 | Workday 只在第一页返回 `total`，后续页返回 `total: 0`，采集器误以为已到末尾 | 记录为缺陷；修复并加回归测试；重采 |
| 采集器第一次把 994 读成 40 | 同上 | 在 `SOURCE_DISCOVERY.md` §3 明写，作为「测量本身也要被测量」的案例 |
| Dräger 首轮被判 `BLOCKED` | 官网 `/en/careers` 对脚本超时、子域 DNS 不解析 | 深查后推翻：真实板在 `erecruitment.draeger.com`；**四种失败（不可达/bot 拦停/真 404/主机不存在）必须分开记录** |
| 内容哈希规则在采集过程中被修改 | 994 条记录存的是旧规则哈希，跨运行比较会把「改了一行代码」报成「992 条描述被修改」 | 新增 `hash_rule_version` 与 `HASH_RULE_REBASELINED` 状态；重采一次使全量一致；跨规则比较明确标记**不可比较**。**如实记录一处不完美**：`hash_rule_version` 字段在重采文件写盘之后 17 秒才加入代码，因此**这份 994 行快照里没有该字段**；已通过重算验证「994/994 与当前规则一致」，并把字段缺失本身写进记录，而不是事后改写数据 |
| 重复发布的归因不可判定 | 5 个簇是「同一标题+同一描述+同一城市、但不同 id 与不同需求号」（如 Intern MBA/Graduate Mumbai 的 R78653 vs R79383、Assembler I 胡志明市 3 个、Agent de production II 法国 2 个）；3 个簇是同一岗位多城市发布、每城不同需求号 | **无法区分「重复发布」与「同时招多人」**：按保守侧当作副本（不当作新增需求），并在每个簇上写 `ambiguity` 字段。这是「规则不能决定」的案例，必须保留而不是猜 |
| 去重后的真实规模 | 994 行 / 994 个唯一 id / 8 个重复簇（5 重复发布 + 3 多城）→ **去重后 983 个岗位** | 报告所有岗位数都注明是「行数」还是「去重后规模」 |
| 基线分支上一个测试按墙钟失效 | `test_filtered_change_queries_bind_every_parameter` 硬编码 2026-11-03 却用 `hours=24` 相对窗口 | 最小化修复 fixture；记录在审计文档；**「测试全绿」不是可继承状态** |
| `medical_ai` 关键词通胀 | 25 个岗位中 17 个只靠描述命中（含 Privacy Legal Counsel、QA Specialist 等） | 在证据报告逐格披露「仅描述命中率」 |
| 两个看起来很强的 Medtronic 试验被拒 | NCT07298473、NCT07789925 标题含 "Ablation/PAF" 但正文无逐字 `PFA/PULSED FIELD ABLATION` | 按预注册规则拒绝，并列入 `external.rejected` 供复核 |
| Europe PMC 未查询 | 没有可接受的确定性机构归属查询方式 | 记为 `NOT_QUERIED`（声明缺口，不当作 0） |
| Draeger/Mindray 在器械证据库中无事件 | dev 库只有 2024-10 起的近期窗口 | 记为源限制：这两家的「无独立支持」是**数据源限制**，不是「没有创新」 |

---

## 8. 与既有结论的关系（不允许覆盖的部分）

PR #20 已经证明、本轮**原样保留**的五条结论：
4B 可本地完成 QLoRA 训练；结构化格式可靠弱监督改善；训练损失≈0 ≠ 能力提升；
**负对照误报因缺少弃答样本而恶化（C 臂 3 个负对照中误报 2 个，0.000 → 0.667）**；
模板化文档不能证明模型适用于真实人类语言。
本轮**没有**用任何新数字去淡化第 4 条，反而把它作为模型实验的头号风险指标。

D-028 / D-029 / D-031 的结论（Wayback 历史路线覆盖不足、五家目标企业只有 1 家可用）**继续有效**。
本轮换了路线（实时前瞻采集）而不是重包装旧路线，并在 `SOURCE_DISCOVERY.md` §7 明确写出差别。

---

## 9. 90 天前瞻观察：何时可以启动

设计见 `docs/NINETY_DAY_PLAN.zh-CN.md`。**本轮不部署**。启动前必须逐条满足：

- [x] 采集器可重复运行（同一天两次全量：身份重叠 1.00、0 消失）
- [x] 身份键稳定（2×200：1.00）且 `first_seen_at` 未被覆盖（100%）
- [ ] robots 变更时采集器拒绝运行（代码已实现 + 单测通过；**尚未在真实 robots 变更下演练**）
- [ ] 分类器的 `UNCLASSIFIED` 率与负对照误报率已知且可接受（本轮只有小样本、无金标准）
- [ ] 人工复核入口可用（`EVIDENCE_REPORT.zh-CN.md` 是入口样例，但尚无固定流程）

**未勾选项 → 不启动。** 这是设计，不是保守。

---

## 10. 结论的边界（本报告的自我限制）

1. 本报告全部结论基于**一次快照**（T0）= 存量，不是流量；不含任何趋势、领先/滞后、因果判断。
2. 五家企业中四家是有界样本（各 80），覆盖率分母未知；只有 Medtronic 是全量。
3. 技术分类只有 6.1% 覆盖率，且**分类正确的另一面是大量 `UNCLASSIFIED`**；`UNCLASSIFIED` 不是失败，是诚实。
4. 独立证据核验「7/8 支持」**不是成功指标**——它几乎自动成立；真正有信息量的是「0 个新方向候选」。
5. 模型实验没有人工金标准，因此没有准确率；只有可核查性、弃答纪律与延迟。
6. 任何「企业正在开发 X」「招聘显示研发投入增加」「模型能识别技术方向」的表述，本报告都不支持。

---

## 11. 复现

```bash
# 采集（有界、可重入、robots 先断言）
python scripts/collect_recruitment.py --company medtronic --limit 1000 --min-interval 0.8 \
    --store-dir data/recruitment/store \
    --out experiments/innovation_signals_observatory/results/2026-11-04

# 稳定性 + 快照画像 + 覆盖诊断
python experiments/innovation_signals_observatory/sources/stability_check.py --company medtronic --limit 200 \
    --out experiments/innovation_signals_observatory/results/2026-11-04
python experiments/innovation_signals_observatory/sources/profile_snapshot.py \
    --jobs experiments/innovation_signals_observatory/results/2026-11-04/jobs_medtronic.jsonl \
    --collection experiments/innovation_signals_observatory/results/2026-11-04/collection_medtronic.json \
    --out experiments/innovation_signals_observatory/results/2026-11-04
python experiments/innovation_signals_observatory/sources/diagnose_track_coverage.py \
    --jobs experiments/innovation_signals_observatory/results/2026-11-04/jobs_medtronic.jsonl \
    --out experiments/innovation_signals_observatory/results/2026-11-04

# 证据关联 + 模型实验
python experiments/innovation_signals_observatory/evidence/link_evidence.py
python experiments/innovation_signals_observatory/llm/run_job_text_experiment.py --help

# 测试
python -m pytest -q
```
