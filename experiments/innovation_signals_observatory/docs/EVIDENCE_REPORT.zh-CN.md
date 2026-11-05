# Phase 4 · 招聘信号 × 独立证据 关联审查报告（WP2c）

**日期**：2026-11-04（Asia/Shanghai）
**对象**：美敦力（Medtronic）T0 单次岗位快照 × 只读器械证据库 × ClinicalTrials.gov（有限、缓存）
**机器可核查产物**：`experiments/innovation_signals_observatory/results/2026-11-04/evidence_linking.json`
**本报告立场**：只陈述「观察到什么、按哪条规则、证据在哪里、还缺什么」。**不**陈述「美敦力正在开发/转向某技术方向」。

---

## 0. 一句话结论

在 992 个去重后的美敦力公开岗位中，只有 61 个（6.1%）能被确定性规则归入既有技术 track，形成 10 个 `(企业 × track)` 单元；其中 **8 个达到「候选技术招聘信号」门槛**，但独立证据核验的结果是：

- **7 个单元 = `INDEPENDENTLY_SUPPORTED`（有独立证据支持）**：含义被有意收窄为「独立来源确认该企业在该 track 有公开活动」。这是**必要但很弱的核验**——美敦力在本证据库的 **23/38** 个 track 中都有事件，因此同企业 + 同 track 的核验对这家企业几乎自动成立，**不能读作「新兴方向被证实」**。
- **1 个单元 = `NO_INDEPENDENT_SUPPORT`（无独立支持）**：`wearable_remote`，证据库中该 track 有 0 条美敦力事件。
- **0 个单元 = `NEW_DIRECTION_CANDIDATE`**；方向新颖度分布为：**既有方向 6 个、近期活动 1 个、基线不足 3 个**。
- **0 个单元被建议升级人工审查**（按本轮预注册门槛：≥3 个独立岗位 ID **且** 新颖度为「新方向候选/近期活动」）。

**诚实的方法论结论**：本轮真正学到的不是「美敦力在做什么新方向」，而是 **核验很容易、信息量很低；有区分度的问题是「方向是否新颖」，而在这个证据库上，多数 track 只能判为既有方向或基线不足。** 这不是数据「没有信号」，而是**单快照 + 25 个月证据库**能支持的结论尺度本来就这么小。

---

## 1. 这份报告回答什么、不回答什么

| 可以回答 | 不可以回答 |
|---|---|
| T0 快照中某 track 有几个**独立岗位 ID**、职能类别是什么、原文引文在哪 | 企业是否**正在开发**某技术方向 |
| 某条独立证据是否**通过**预注册的四条关联规则 | 企业是否发生了**战略转向** |
| 独立证据的**来源类型与特异性**（器械许可/临床试验/行政类 PMA 补充/召回） | 招聘是否意味着**研发投入增加** |
| 方向**新颖度**（相对证据库可见基线）及其**审计计数** | 岗位数是否等于**新增需求**（未区分补缺与新增） |
| 哪些问题**目前不可知**、缺哪一条信息 | 任何**趋势、领先/滞后、因果**判断 |

本报告的所有判断都可回查到：岗位 ID + 源 URL + 原文引文 + 规则编号 + 证据 ID（FDA K/P/召回编号或 NCT 号）。**模型没有生成任何事实或引文**；岗位分类来自确定性规则臂 A（`medradar.recruitment.taxonomy`），证据关联来自本工作包的确定性管线。

---

## 2. 数据与口径

### 2.1 岗位快照（T0）

| 项目 | 值 |
|---|---|
| 来源 | Medtronic 官方 Careers（Workday，`medtronic.wd1.myworkdayjobs.com`），robots.txt 允许 |
| 采集时间 | 2026-11-04 20:53–21:09（Asia/Shanghai），50 个列表页，1,045 次请求，详情失败 0 |
| 文件行数 | **994** 行 |
| 去重后独立岗位 | **992** 个（`posting_id` 为身份键；2 行是偏移分页重复，已在 JSON 的 `snapshot.duplicate_rows` 中列出） |
| 快照 SHA-256 | `165dce8e8c6b8127ba445d3a668117d614ad47193daf74b250d8b67c51f80217` |
| 来源发布日期范围 | **2025-11-07 … 2026-11-04** |
| 首次观察时间（我们的墙钟） | 2026-11-04 12:53–13:09 UTC（`first_seen_at`，写一次不覆盖） |

> **重要读法**：这是一份**「当前在招岗位存量（stock）」**，不是「新增岗位流量（flow）」。`source_posted_at` 横跨约 12 个月，说明很多岗位是几个月前发布、现在仍开放。因此**岗位数不能当新增招聘需求**，更不能当研发投入。

### 2.2 岗位分类（确定性规则臂 A）

- 分类器：`medradar.recruitment.taxonomy.classify_rules`，规则版本 `recruitment_taxonomy_rules_2026-11-04`，函数词表 `recruitment_function_classes_2026-11-04`，技术 track 词表 `tracks_device_2026-11`（既有 50 个 track，不新造分类）。
- 职能类分布（992 个）：`SALES_ADMIN_OTHER` 583、`UNCLASSIFIED` 132、`QUALITY_REGULATORY` 88、`ALGORITHM_SOFTWARE` 70、`MANUFACTURING_PROCESS` 47、`PRODUCT_ENGINEERING` 34、`CORE_R&D` 14、`CLINICAL_R&D` 13、`HARDWARE_SYSTEMS` 11。
- track 赋值状态：`MAPPED` **61**、`AMBIENT_ONLY` 147、`SUPPRESSED_BY_FUNCTION_CLASS` 715、`NO_EVIDENCE` 69。
  - 商业/现场类岗位被函数门槛**故意压制**，不赋 track（避免把「卖什么」当「研发什么」）；未赋 track 的岗位全部保留在 JSON 的 `unclassified_postings` 中供审计。
- **仅描述命中率**（标题里没有 track 关键词、只靠岗位描述关键词归入 track 的岗位占比）在逐 track 表中给出。这个比例是本轮**最重要的数据质量指标之一**：比例高说明 track 归属依赖描述文本，关键词通胀风险高。

### 2.3 独立证据源 1：只读器械证据库

| 项目 | 实测值（不采信任务书描述） |
|---|---|
| 路径 | `D:\DEPPSKK\medradar\data\dev_device.sqlite`（仓库外，**未复制进 git**） |
| 打开方式 | SQLite URI `mode=ro` + `PRAGMA query_only=1`（只读；测试断言写入会失败） |
| 事件总数 | 17,730 |
| 实测事件窗口 | **2024-10-01 … 2026-10-28**（不是 2016-11 起；这是近期窗口 dev 库） |
| 事件类型 | 510(k) 6,752；PMA 4,752；召回 6,226 |
| 美敦力事件 | 1,268 条，分布在 **23/38** 个 track（+126 条未归 track） |
| 数据质量 | 8,596 条 payload 在约 4KB 处被截断（510k 3,541、召回 5,049、PMA 6）；标识提取因此需要 payload 前缀/URL 回退，**17,730 条全部仍能解析出 FDA 标识** |
| 两家重点企业 | Dräger、Mindray 在该 dev 库中 **0 条事件**（后续快照若出现其岗位，只能记为来源限制） |

### 2.4 独立证据源 2：ClinicalTrials.gov（8 次有界请求，全部 200 OK，缓存不入 git）

每个候选 track 只发 1 次请求：`query.spons=<企业显示名>` + `query.term=<该 track 最长的 frontier 关键词>` + `pageSize=10`。原始响应缓存于 `results/2026-11-04/_httpcache_evidence/ctgov/`（**不提交**），JSON 中记录每个请求的 URL、状态、条数、SHA-256。

| track | 查询词 | 返回研究数 | 通过四条规则 |
|---|---|---:|---:|
| ep_pfa | PULSED FIELD ABLATION | 7 | **2** |
| cardiac_rhythm | CARDIAC RESYNCHRONIZATION | 10 | 0 |
| medical_ai | CLINICAL DECISION SUPPORT | 2 | 0 |
| neurostimulation | VAGUS NERVE STIMULATION | 1 | 0 |
| neurovascular | NEUROVASCULAR | 10 | 0 |
| respiratory | RESPIRATORY | 10 | 0 |
| structural_heart | TRANSCATHETER VALVE | 10 | **1** |
| surgical_robotics | AUTONOMOUS SURGERY | **0** | 0 |

> Europe PMC **本轮明确为 `NOT_QUERIED`**：可达，但没有采用可接受的精确机构归属查询，因此论文维度记为「未查询的缺口」，而不是「零」。这是有意的保守选择，写进 JSON 的 `evidence_source.external_publications`。

### 2.5 关联规则（协议 §6 的操作化；写死在代码中）

| 规则 | 要求 | 本轮的确定性实现 |
|---|---|---|
| **R1 同一企业** | 企业键完全相等 | `events.company_key == cell.company_key` 且该键在 `config/universe_v1.json.focus_companies`；**不做模糊/子串匹配**；CT.gov 用机构名中的**整词**企业别名匹配 |
| **R2 同一 track** | track id 相等且属于既有词表 | `events.track_id == cell.track_id` 且 track 在 `config/tracks_device.json`；CT.gov 要求 trial 文本**逐字出现**该 track 的 keyword/frontier keyword |
| **R3 时间窗** | 不早于招聘观察 24 个月，且不晚于观察日 | `window = [anchor − 24 个月, anchor]`，其中 `anchor` = 该单元最早 `first_seen_at`（本轮 2026-11-04）；同时要求证据的 `as_of ≤ anchor`（无前视） |
| **R4 可回查标识** | 每条关联证据带外部编号 | FDA：K 号 / P 号（+补充号）/ 召回编号（Z-… 或 RES-…）；CT.gov：`NCT########` |

常量：`HIRE_EVIDENCE_MAX_LOOKBACK_MONTHS = 24`、`MIN_DISTINCT_POSTINGS_FOR_CANDIDATE = 2`、`MIN_DISTINCT_POSTINGS_FOR_HUMAN_REVIEW = 3`。全部在测量前声明，未按单元调整。

### 2.6 方向新颖度（本轮的科学主张字段）

`INDEPENDENTLY_SUPPORTED` 只说「有活动」。**是否有新方向**由独立字段 `direction_novelty` 回答，它完全由证据库中该企业该 track 的**时间分布计数**导出：

- 常量：近期窗 = 12 个月；可见基线 = 证据库起点到近期窗之前（本轮 `2024-10-01 → 2025-11-04`，**13.1 个月**）；要求基线至少 6 个月才做判断；「既有方向」要求活动**跨 ≥18 个月且 ≥6 条事件且近期仍有活动**。
- 取值（封闭词表）：
  - `NEW_DIRECTION_CANDIDATE`：可见基线窗内 0 条、最近 12 个月 ≥1 条。**含义只是「相对可见基线为新」，绝非「对企业全新」**（更早历史来源看不到）。
  - `RECENT_ACTIVITY`：近期有活动、基线也有，但不足以判为持续既有方向；方向状态模糊。
  - `ESTABLISHED_DIRECTION`：活动跨 ≥18 个月且 ≥6 条、近期仍有活动；对该企业是既有业务，**招聘更可能是业务常态**。
  - `NO_BASELINE_DATA`：来源看得不够远/没有可用日期，无法区分新与旧。**「没有信号」不是「有新信号」。**

每格的计数（事件总数、首末事件日期、24 个月窗口内条数、基线/近期条数、涉及事件类型、基线覆盖月数）都写在 JSON 的 `cells[].direction_novelty` 中，可逐项复核。

---

## 3. 逐 track 计数总表

> 读法：**候选** = 该 `(企业×track)` 单元有 ≥2 个独立岗位 ID 且 ≥1 个研发职能类岗位。**证据判定**遵循 §2.5 四条规则；**新颖度**见 §2.6。**仅描述命中率** = 标题无 track 关键词、只靠描述归入该 track 的岗位占比。

| track | 中文名 | 单元内岗位 | 独立岗位 ID | 研发职能岗位 | 仅描述命中率 | 候选？ | 招聘信号判定 | 方向新颖度 | 独立证据判定 | 高特异性支持证据 | 建议人工审查 |
|---|---|---:|---:|---:|---:|:--:|---|---|---|---:|:--:|
| `medical_ai` | 医疗AI/软件(SaMD) | 25 | 25 | 15 | 68% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | ESTABLISHED_DIRECTION | INDEPENDENTLY_SUPPORTED | 7 | 否 |
| `neurostimulation` | 神经调控 | 14 | 14 | 6 | 93% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | ESTABLISHED_DIRECTION | INDEPENDENTLY_SUPPORTED | 0 | 否 |
| `ep_pfa` | 电生理与脉冲场消融 | 8 | 8 | 7 | 50% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | ESTABLISHED_DIRECTION | INDEPENDENTLY_SUPPORTED | 2 | 否 |
| `neurovascular` | 神经介入 | 4 | 4 | 1 | 100% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | ESTABLISHED_DIRECTION | INDEPENDENTLY_SUPPORTED | 2 | 否 |
| `cardiac_rhythm` | 心脏节律（起搏/ICD） | 2 | 2 | 2 | 100% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | ESTABLISHED_DIRECTION | INDEPENDENTLY_SUPPORTED | 1 | 否 |
| `respiratory` | 呼吸与麻醉 | 2 | 2 | 2 | 100% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | **RECENT_ACTIVITY** | INDEPENDENTLY_SUPPORTED | 4 | 否（<3 个 ID） |
| `structural_heart` | 结构性心脏病 | 2 | 2 | 2 | 100% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | ESTABLISHED_DIRECTION | INDEPENDENTLY_SUPPORTED | 1 | 否 |
| `wearable_remote` | 可穿戴与远程监测 | 2 | 2 | 2 | 100% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | **NO_BASELINE_DATA** | **NO_INDEPENDENT_SUPPORT** | 0 | 否 |
| `imaging_us` | 超声 | 1 | 1 | 1 | 0% | 否 | UNKNOWN | NO_BASELINE_DATA | UNKNOWN（低于候选门槛） | 0 | 否 |
| `resuscitation` | 急救与复苏 | 1 | 1 | 0 | 100% | 否 | UNKNOWN | NO_BASELINE_DATA | UNKNOWN（低于候选门槛） | 0 | 否 |

**计数小结**：10 个单元 / 8 个候选 / 7 个有独立支持 / 1 个无独立支持 / 2 个未知；方向新颖度 0 个新方向候选、1 个近期活动、6 个既有方向、3 个基线不足；**人工审查建议 0 个**。

**方法学注记（必读）**：8 个候选里 7 个「有独立支持」，看起来像一个正面的结果；但把 `direction_novelty` 放在旁边看，7 个中有 6 个是**既有方向**、1 个是**近期活动**、0 个是**新方向候选**。因此本轮的诚实表述是：

> **同企业 + 同 track 的核验几乎自动成立（美敦力在 23/38 个 track 有事件），它只回答「这家公司在这个领域有没有公开活动」，不回答「这是不是新方向」。**

---

## 4. 候选案例（5 个真实案例，可逐条手查）

> 每个案例都给出：源 URL、岗位 ID + 标题 + 原文引文、分类与规则依据、独立证据（或明确缺失）、支持与反证、研究假设（`HYPOTHESIS`，不是结论）、仍未知、建议的人工复核步骤。

### 4.1 案例 A：`medical_ai` —— 最大的招聘单元，但方向已经存在

**单元**：25 个独立岗位 ID，15 个研发职能类岗位；**仅描述命中率 68%**（17/25 的 track 证据只来自岗位描述）。
**判定**：`CANDIDATE_TECHNICAL_HIRING_SIGNAL` + `INDEPENDENTLY_SUPPORTED` + `ESTABLISHED_DIRECTION`；**不建议升级**（既有方向）。

**代表性岗位**（完整 25 条见 `evidence_linking.json` 的 `cells[medical_ai].postings`）：

| posting_id | 标题 | 职能类 | 标题/描述中的 track 引文 | 源 URL |
|---|---|---|---|---|
| `d15f631c147b1039890d24ab95bc0001` | Senior Artificial Intelligence Engineer | ALGORITHM_SOFTWARE | `Artificial Intelligence`（标题）；`Machine Learning`（描述） | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/London-London-United-Kingdom/Senior-Artificial-Intelligence-Engineer_R79657-1 |
| `d2836d4abd1d102983e1041ff11f0000` | Principal AI/ML Software Engineer | ALGORITHM_SOFTWARE | `artificial intelligence`、`software`（描述） | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Galway-County-Galway-Ireland/Principal-AI-ML-Software-Engineer_R71975-1 |
| `91a67527aabe1048df242159edd00001` | Senior AI Data Science Engineer | ALGORITHM_SOFTWARE | `Artificial Intelligence`（标题）；`machine learning`（描述） | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Nanakramguda-Hyderabad-India/Senior-AI-Data-Science-Engineer_R79295-1 |
| `052583cdd3f910343eac54978bbb0001` | AI/Data Science Engineer II | ALGORITHM_SOFTWARE | `Artificial Intelligence`（标题）；`software`、`machine learning`（描述） | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Nanakramguda-Hyderabad-India/AI-Data-Science-Engineer-II_R78701-2 |

**同一单元里的「关键词通胀」反例（必须看，否则 25 会被误读成 25 个 AI 研发岗）**：

| posting_id | 标题 | 为什么会被归入 `medical_ai` |
|---|---|---|
| `b968d27c521f103baf2b306f2e70000` | Privacy Legal Counsel（布鲁塞尔） | 描述里出现 `artificial intelligence`（隐私/合规段落） |
| `d4784440efb810287d69680e2fcd0000` | Quality Assurance Specialist（马尼拉） | 描述里出现 `artificial intelligence`、`AI-enabled` |
| `b968d27c521f10378c362eaf87f00000` | Principal Systems Administrator（海得拉巴） | 描述里出现 `software` |
| `0a4ce1c6eba810444861188d6d5e0000` | Principal Customer Experience Specialist - Service & Repair EMEA | 描述里出现 `AI-enabled` |

**分类依据**：函数类来自标题短语（如 `Software Engineer`/`Artificial Intelligence` → `ALGORITHM_SOFTWARE`）；track 由既有词表 keyword/frontier keyword 命中（`ARTIFICIAL INTELLIGENCE`、`AI-ENABLED`、`MACHINE LEARNING`、`SOFTWARE`），其中 17/25 只在描述命中（`track_evidence_quality.description_only_rate = 0.68`）。分类器**不是**概率模型，`confidence_basis` 是规则计数，不是校准概率。

**独立证据（通过四条规则，7 条，全部为 510(k)，高特异性）**：

| 证据 ID | 日期 | 标题 | 链接 |
|---|---|---|---|
| K262005 | 2026-08-21 | Medtronic, Inc. 510(k)：Affera Integrated Mapping System | https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K262005 |
| K260907 | 2026-08-13 | Covidien LP 510(k)：BIS Advance pEEG Module | https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K260907 |
| K261289 | 2026-05-15 | Medicrea International S.A.S. (Medtronic) 510(k)：UNiD Spine Analyzer (SW3002) | https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K261289 |
| K250725 | 2025-12-03 | Covidien, LLC 510(k)：Hugo RAS System | https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K250725 |
| K251629 / K243892 / K243435 | 2025-08-07 / 2025-01-17 / 2024-12-05 | UNiD Spine Analyzer；Affera Mapping System；Magnetic Localization Patch Kit | 同上格式 |

**支持 vs 反证**：
- 支持：7 条 510(k) 通过 R1–R4；track 内 19 条 FDA 事件（2024-11-01 … 2026-10-21，跨 23 个月，基线窗 11 条、最近 12 个月 8 条）→ 这是**既有方向**。
- 反证/反语境：track 内 11 条召回（如 `Z-0203-2027` CareLink Clinic 2026-10-21、`Z-2201-2026` SynchroMed A810 2026-05-14、`Z-0958-2026` InPen App 2025-12-18）。**召回是上市后问题，不是「该方向不存在」的反证**；本轮 `CONTRADICTED` 不可达。
- 上游风险：这些 510(k) 的 track 归属继承自证据库既有的 product-code→track 映射，本管线**不重新分类**；因此「Affera/Hugo/UNiD 被算作 medical_ai」是上游事实，需人工抽查。

**研究假设（HYPOTHESIS，不是结论）**：美敦力在 2026 年持续招聘 AI/数据科学岗位，且该方向在器械许可与召回层面都有连续活动；一个可检验的假设是——**这些岗位主要支撑既有的软件化器械产品线（如 Affera 标测、Hugo、UNiD），而不是一个全新的 AI 产品方向**。

**仍未知**：这些岗位是新增编制还是补缺；AI 职责是产品研发还是内部 IT/合规；上游 track 赋值是否把「设备软件」误算成「医疗 AI」；没有岗位编制、团队归属或项目立项信息。

**建议人工复核步骤**：
1. 对 4 个代表性岗位，打开 URL 核对 `Artificial Intelligence`/`Machine Learning` 是**岗位职责**还是公司介绍/合规段落（`track_quotes` 已给出原文，但上下文需人工判断）。
2. 按地点分组：海得拉巴（IT 中心）vs Galway/Mounds View（产品团队）——若 AI 岗位集中在 IT 中心，更可能是基础设施而非 SaMD 产品。
3. 把 7 条 510(k) 的器械名称与产品线对应起来，确认它们是否真属「医疗 AI/SaMD」而非普通设备软件。
4. 结论只能写成「候选招聘观察」，留给**下一次快照**做变化比较；本轮不得下方向结论。

---

### 4.2 案例 B：`ep_pfa` —— 唯一有「高特异性临床试验」支持的候选，但方向仍是既有

**单元**：8 个独立岗位 ID，7 个研发职能岗位；仅描述命中率 50%（4/8 标题直接含 `Cardiac Ablation`/`CAS`）。
**判定**：`CANDIDATE_TECHNICAL_HIRING_SIGNAL` + `INDEPENDENTLY_SUPPORTED` + `ESTABLISHED_DIRECTION`；**不建议升级**。

**代表性岗位**：

| posting_id | 标题 | 职能类 | track 引文 | 源 URL |
|---|---|---|---|---|
| `a2978683a3e9101bc263418791910000` | Principal Systems Engineer - Cardiac Ablation Solutions | PRODUCT_ENGINEERING | 标题 `Cardiac Ablation`；描述 `Electrophysiology` | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Mounds-View-Minnesota-United-States-of-America/Principal-Systems-Engineer_R70312-1 |
| `749d96337e9610244c630a3758ce0001` | Software Engineering Manager - Cardiac Ablation Solutions | ALGORITHM_SOFTWARE | 标题 `Cardiac Ablation`；描述 `electrophysiology` | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Mounds-View-Minnesota-United-States-of-America/Software-Engineering-Manager---Cardiac-Ablation-Solutions_R74270-1 |
| `58053233949c103bc4587ed3cb1c0002` | Principal Systems Engineer (CAS) | PRODUCT_ENGINEERING | 描述 `Cardiac Ablation`、`electrophysiology` | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Mounds-View-Minnesota-United-States-of-America/Principal-Systems-Engineer--CAS-_R79717-2 |
| `6ecf0680c83f10305359c438588e0000` | Software Engineering Program Manager - Cardiac Ablation Solutions | ALGORITHM_SOFTWARE | 标题 `Cardiac Ablation` | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Newton-Massachusetts-United-States-of-America/Software-Engineering-Program-Manager---Cardiac-Ablation-Solutions_R75518 |

**独立证据（2 条高特异性临床试验 + 59 条证据库记录）**：

| 证据 | 日期 | 内容 | 链接 |
|---|---|---|---|
| NCT07575828 | 2026-05-08（启动；2026-05-08 首次登记） | PulseSelect PFA 系统优化流程研究（Medtronic Cardiac Ablation Solutions；NOT_YET_RECRUITING） | https://clinicaltrials.gov/study/NCT07575828 |
| NCT07308847 | 2026-01-15（启动；2025-12-30 首次登记） | Horizon 360：Sphere-360 消融导管 + Affera 标测消融系统（ACTIVE_NOT_RECRUITING） | https://clinicaltrials.gov/study/NCT07308847 |
| P240013/S032 | 2026-10-09 | Affera Sphere-9 Mapping and Ablation Catheter PMA 补充 | https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?id=P240013 |
| P100010/S154 | 2026-09-25 | Medtronic Cryocath「STOP Persistent AF」PMA 补充（上市后研究类） | https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?id=P100010 |

证据库 59 条通过规则的记录中，特异性分布为：生产流程类 33、标签类 5、地点类 6、设计变更 7、上市后研究 8；**高特异性只有 2 条（即上面两个 NCT）**。

**支持 vs 反证**：
- 支持：2 个 NCT + 59 条 PMA 补充 → 企业在该 track 有连续、可查的公开活动（跨 24 个月，基线 34、近期 27）。
- 反证/反语境：`Z-1948-2026` Sphere-9 Catheter 召回（2026-04-24）——上市后问题，不是方向反证；另有 `Senior Medical Safety Specialist` 岗位，提示该产品线处于上市后安全监测阶段。
- **被规则拒绝的「看起来很强」的证据（必须披露）**：`NCT07298473`（Conquer-AF，Medtronic Cardiac Ablation Solutions，2026-04-08 启动）与 `NCT07789925`（Sphere-9 PAF China Study，2026-09-02 启动）均因 **R2 失败**被拒——抓取字段（标题/条件/干预/简介）中没有逐字出现 track 关键词（标题写的是 `Ablation`、`PAF`，并非 `PFA`/`PULSED FIELD ABLATION`）。**这是规则的保守性，不是证据不存在**；这两条列在 JSON 的 `cells[ep_pfa].evidence.external.rejected` 中。

**研究假设（HYPOTHESIS）**：美敦力在 Mounds View/Newton 的 8 个岗位（含 6 个系统/软件工程岗）指向 **Affera/Sphere-9/Sphere-360 + PulseSelect 平台的持续工程投入**；该方向已有 2 个在研试验和持续 PMA 补充，因此更可能是**平台迭代**而非新模态。

**仍未知**：这 8 个岗位是新增还是替换；系统工程师集群对应的是新版本开发还是量产支持；没有项目名称/预算/编制信息。

**建议人工复核步骤**：核对每个岗位描述是否**明确**提到 Sphere-9 / Sphere-360 / PulseSelect / Affera；把岗位与两个 NCT 的器械版本对齐；记录 Sphere-9 召回对岗位需求的可能影响（安全监测 vs 研发）。

---

### 4.3 案例 C：`neurostimulation` —— 116 条独立证据，但没有一条是「技术方向」证据

**单元**：14 个独立岗位 ID，6 个研发职能岗位；**仅描述命中率 93%**（13/14 只在描述里出现 `Neuromodulation` 等词）。
**判定**：`CANDIDATE_TECHNICAL_HIRING_SIGNAL` + `INDEPENDENTLY_SUPPORTED` + `ESTABLISHED_DIRECTION`；**不建议升级**。

**代表性岗位**：

| posting_id | 标题 | 职能类 | track 引文 | 源 URL |
|---|---|---|---|---|
| `d15f631c147b1038b65c01dd7bb50000` | Senior Scientist, Pain Interventions - Onsite | CORE_R&D | 描述 `neuromodulation` | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Minneapolis-Minnesota-United-States-of-America/Senior-Scientist--Pain-Interventions---Onsite_R79352-1 |
| `d2836d4abd1d102a88bde4e41e330001` | Sr. Principal Embedded Software Engineer | ALGORITHM_SOFTWARE | 描述 `Neuromodulation` | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Fridley-Minnesota-United-States-of-America/Sr-Principal-Embedded-Software-Engineer_R75845-1 |
| `8e5a383db9e0103931cdae751c300002` | Mechanical Design Engineer II | PRODUCT_ENGINEERING | 描述 `Neuromodulation` | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Fridley-Minnesota-United-States-of-America/Mechanical-Design-Engineer-II_R80098-2 |
| `62cbbafaa709104ae3007fde4fcb0000` | Senior Clinical Evidence Specialist - NM | CLINICAL_R&D | 描述 `Neuromodulation` | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Fridley-Minnesota-United-States-of-America/Senior-Clinical-Evidence-Specialist---NM---Rice-Creek-Fridley--MN--Onsite-_R80673 |

**独立证据（116 条通过规则，但特异性极低）**：

| 特异性 | 条数 | 说明 |
|---|---:|---|
| 生产流程变更（PMA 补充） | 90 | 行政类，不是技术方向证据 |
| 标签变更 | 4 | 行政类 |
| 地点变更 | 2 | 行政类 |
| 设计变更 | 19 | 中等（可能有技术含义） |
| 上市后研究方案 | 1 | 中等 |
| **高特异性（设备许可/临床试验）** | **0** | 无 |

示例：`P960009/S542`（2026-10-06，Activa DBS / Percept PC BrainSense）、`P840001/S632`（2026-10-06，Vanta/Intellis/Vanta/Inceptiv SCS）——均为 PMA 补充。CT.gov 查询 `VAGUS NERVE STIMULATION` 返回 1 条、通过规则 0 条。

**支持 vs 反证**：支持仅是「该方向长期存在」；反语境为 6 条召回（深部脑刺激口袋转接件、临床程控 App 等，2025-04 至 2026-05）。**这条单元最能说明问题：独立证据数量多（116）不代表信息量大（0 条高特异性）。** 数量是由美敦力在该 track 的行政类申报体量决定的，不是由「技术新颖」决定的。

**研究假设（HYPOTHESIS）**：招聘集中在 Fridley（神经调控总部）的嵌入式软件/机械设计/临床证据岗位，指向**既有 DBS/SCS 产品线的下一代硬件/软件迭代**。

**仍未知**：`Pain Interventions` 科学家是否涉及新适应症；没有产品路线图或试验登记支持「新模态」。

**建议人工复核步骤**：抽查 19 条「设计变更」PMA 补充的具体内容，确认是否涉及新一代硬件/软件；核对岗位描述是否提到具体适应症（如疼痛、癫痫、尿失禁）。

---

### 4.4 案例 D：`respiratory` —— 本轮唯一「近期活动」单元，但只有 2 个岗位 ID

**单元**：2 个独立岗位 ID，均研发职能；**仅描述命中率 100%**。
**判定**：`CANDIDATE_TECHNICAL_HIRING_SIGNAL` + `INDEPENDENTLY_SUPPORTED` + **`RECENT_ACTIVITY`**；按预注册门槛（≥3 个独立岗位 ID）**不建议人工审查**，但列为下次快照的观察对象。

| posting_id | 标题 | 职能类 | track 引文 | 源 URL |
|---|---|---|---|---|
| `451227adcdb71028901ade82ae990000` | Senior Embedded Software Engineer | ALGORITHM_SOFTWARE | 描述 `anesthesia`、`respiratory` | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Galway-County-Galway-Ireland/Senior-Embedded-Software-Engineer_R75499 |
| `d4784440efb810289500e2efe66b0001` | Sr Electronics Hardware Engineer | HARDWARE_SYSTEMS | 描述 `anesthesia`、`respiratory` | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Galway-County-Galway-Ireland/Sr-Electronics-Hardware-Engineer_R74831-1 |

**独立证据（4 条 510(k)，全部高特异性）**：

| 证据 ID | 日期 | 标题 | 链接 |
|---|---|---|---|
| K261335 | 2026-07-31 | Medtronic, Inc. 510(k)：VitalFlow Set with Balance Biosurface | https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K261335 |
| K253030 | 2026-05-01 | Covidien, LLC 510(k)：Capnostream 35 Portable Respiratory Monitor (PM35MN) | https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K253030 |
| K251831 | 2026-01-15 | Medtronic, Inc. 510(k)：Bio-Medicus Life Support Catheter and Introducer | https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K251831 |
| K250199 | 2025-05-20 | Medtronic, Inc. 510(k)：VitalFlow Console | https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K250199 |

**支持 vs 反证**：支持为 4 条 510(k)；反语境为 6 条召回（Shiley 气管切开套管、MC3 VitalFlow 控制台、Nellcor SpO2、Newport HT70 呼吸机等）。方向新颖度 = `RECENT_ACTIVITY`：10 条事件跨 16 个月（基线 4 条、最近 12 个月 6 条），**未达「跨 ≥18 个月且 ≥6 条」**，所以既不能说「既有方向」，也不能说「新方向」。

**研究假设（HYPOTHESIS）**：Galway 基地（呼吸/麻醉产品线）正在为监护/通气类产品做嵌入式软件与电子硬件更新；可能与 VitalFlow、Capnostream 等 2025–2026 年的许可活动有关。

**仍未知**：2 个岗位是新增还是补缺；证据库看不到 2024-10 之前，无法判断「近期」是否真的近期；CT.gov 的 `RESPIRATORY` 查询 10 条无一条通过规则（多为窗口外或非美敦力）。

**建议人工复核步骤（下一轮）**：若下一次快照该 track 出现 ≥3 个独立岗位 ID，则按「近期活动」升级审查；先核对这 2 个岗位的 req id 是否连续、是否属于同一团队。

---

### 4.5 案例 E：`wearable_remote`（无独立支持）+ 三个「不能给结论」的单元

**E1 `wearable_remote` — `NO_INDEPENDENT_SUPPORT`**

- 岗位（2 个，均为海得拉巴的软件岗）：
  - `959c2c1510e71042322df7d9daf20001` Lead Enterprise Software Engineer，描述引文 `remote monitoring`、`wearables`；
    https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Nanakramguda-Hyderabad-India/Lead-Enterprise-Software-Engineer_R78090-1
  - `0b2e3ccd74e81032e3673866b37a0001` Software Test Engineer II，同引文；
    https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Nanakramguda-Hyderabad-India/Software-Test-Engineer-II_R78270-1
- 独立证据：证据库中 **美敦力在 `wearable_remote` 有 0 条事件**；CT.gov 未对该 track 发起查询（缓存中无该 track）。
- 判定：`NO_INDEPENDENT_SUPPORT`，原因码 `NO_EVIDENCE_ROWS_IN_TRACK`；方向新颖度 `NO_BASELINE_DATA`。
- **这个案例直接对应本任务最硬的规则**：两个岗位提到 `wearables`，证据库没有同 track 记录——**「同企业 + 关键词」不是研发项目证据，这里连独立来源都没有记录**。也不得反过来说「美敦力没有可穿戴业务」：这是来源覆盖问题。

**E2 `resuscitation` — `UNKNOWN`（低于候选门槛）+ 关键词通胀示例**

- 岗位：`7855805f1fb5104b1bf74b12d4b50000` Environmental Health and Safety (EHS) Manager，1 个 ID。
- 被归入 `resuscitation` 的引文是描述中的 `Cardiopulmonary Resuscitation`、`CPR`、`Automated External Defibrillator`——这是 EHS 岗位的**安全培训语境**，不是心肺复苏产品研发。
- 判定：`UNKNOWN`（原因 `BELOW_CANDIDATE_THRESHOLD`，且该岗位不是研发职能类）。**这是一个「分类器给出 track、但人工一眼应否决」的例子**，说明 `MAPPED` 不等于「研发方向」。

**E3 `imaging_us` — `UNKNOWN`（低于候选门槛）**

- 岗位：`aa89d21dee97101c9ef3824c056f0000` Principal Algorithm Engineer – Imaging / Ultrasound (ML)，标题直接含 `Ultrasound`，是**看起来最像真实技术方向**的单条岗位。
- 但只有 1 个独立岗位 ID，未达候选门槛；证据库中 `imaging_us` 有 0 条美敦力事件。判定 `UNKNOWN`，**不把它写成信号**。

**E4 `surgical_robotics` — 没有候选单元；CT.gov 查询 0 条**

- 992 个岗位中，标题含 `Robotic`/`Robotics` 的岗位有 **20 个**（如 `Training & Education Manager - Robotics`、`Area Sales Manager - Robotic Surgical Technologies`、`Robotic Startup Specialist`、`Business Developer Surgical Robotics`、`Senior Principal Robotics & AMR Automation Platforms Engineer`），但**没有一个**被确定性规则归入 `surgical_robotics`：它们的函数类别是商业/现场服务/培训（`SALES_ADMIN_OTHER`）或弃答（`UNCLASSIFIED`），按分类器的函数门槛被压制（`SUPPRESSED_BY_FUNCTION_CLASS`）。
- 其中 `Senior Principal Robotics & AMR Automation Platforms Engineer`（`032f142d5d2f102243bf17e153bd0001`）本身是工程岗，函数类却被判为 `UNCLASSIFIED`——这是分类器的保守性：宁可弃答、不硬赋 track；但也说明**函数/技术分类的覆盖不完美**，人工复核需要看原文。
- 证据库中美敦力 `surgical_robotics` 事件 **0 条**；CT.gov 查询 `AUTONOMOUS SURGERY` 返回 **0** 条（URL 见 JSON）。
- **硬规则示例**：即使将来出现「Robotics 岗位 + 同 track 的 FDA 事件」，那也只是「同企业同 track 的活动」，不是「同一研发项目」；本案例连 track 归属都不成立，因此**没有候选、没有支持、没有结论**。不能把「很多销售/培训岗提到机器人」写成「手术机器人研发信号」。

---

## 5. 「没有独立支持 / 未知」完整清单

| 单元/对象 | 状态 | 原因码 / 说明 | 该说什么、不该说什么 |
|---|---|---|---|
| `wearable_remote` | `NO_INDEPENDENT_SUPPORT` | `NO_EVIDENCE_ROWS_IN_TRACK`：证据库 0 条同 track 美敦力事件 | 说「该来源没有记录」；不说「没有可穿戴业务」 |
| `imaging_us` | `UNKNOWN` | `BELOW_CANDIDATE_THRESHOLD`（1 个 ID）；证据库 0 条 | 说「数据不足，不构成候选」；不说「没有布局」 |
| `resuscitation` | `UNKNOWN` | `BELOW_CANDIDATE_THRESHOLD`（1 个 ID）+ 非研发职能 | 说「不构成技术招聘信号」 |
| `surgical_robotics` | 无候选 | 无 track 归属 + FDA 0 条 + CT.gov 0 条 | 说「本轮没有候选，也没有独立支持」；不说「美敦力没有手术机器人」 |
| `CONTRADICTED` | **本轮不可达** | FDA 事件流没有「退出/撤回该技术方向」类信号；召回只记为反语境 | 说「数据能力边界，不是没有反证」 |
| `NEW_DIRECTION_CANDIDATE` | **0 个** | 所有候选 track 在可见基线上都已有活动 | 说「没有新方向候选」；不说「没有新方向」 |
| 12 个 config track | 证据库无该词表 | `brain_computer`、`ecmo`、`oxygen_therapy`、`resuscitation`、`ivd_ngs`、`ivd_liquid_biopsy`、`ivd_mrd`、`ivd_companion`、`ivd_microbiology`、`ivd_chemistry`、`ivd_hematology`、`ivd_digital_pathology` | 若未来有岗位落入这些 track，只能判 `UNKNOWN`（来源结构无法表示），不得判 `NO_INDEPENDENT_SUPPORT` |
| Dräger / Mindray | 来源限制 | 本 dev 证据库中 0 条事件 | 若其岗位出现，不得把「来源没有记录」解释为「企业没有创新」 |
| Europe PMC / 论文 | `NOT_QUERIED` | 无精确机构归属查询 | 记为缺口，不是零 |
| 2 个 CT.gov 强证据 | 被规则拒绝 | `NCT07298473`、`NCT07789925` 因 R2（文本无逐字 track 关键词） | 说明规则保守性；不得悄悄算作支持 |
| 8 个候选的人工审查 | 0 个建议升级 | 10 个单元的新颖度：既有方向 6、近期活动 1（`respiratory`，仅 2 个 ID）、基线不足 3 | 说「本轮不上调」；不说「没有值得关注的东西」 |

---

## 6. 这份单快照不能说明什么（必须与结论一起读）

1. **单快照 = 没有变化**。只有一次 T0（`first_seen_at` 2026-11-04）。没有第二次快照，就无法定义「新增/减少/换方向」，也无法做趋势、领先/滞后、基线比较。
2. **存量 ≠ 流量**。`source_posted_at` 跨 2025-11-07 … 2026-11-04；这是**当前挂着**的岗位，不是「新发布的岗位」。岗位数不是新增需求，更不是研发投入。
3. **覆盖率未知**。只覆盖美敦力公开 Careers 站点上合法可见的部分；分母（企业实际在招总数）未知；「看不见」≠「没有」。
4. **岗位 ≠ 编制 ≠ 项目**。没有 headcount、预算、组织归属；同一岗位可能补缺、可能多城市重复（本轮已按 `posting_id` 去重，但同 req 多城市仍可能是同一需求）。
5. **证据库只有 25 个月、且只含 FDA 三事件流**。实测 2024-10-01 … 2026-10-28；无临床试验、无论文、无企业公告。**方向新颖度的可用基线只有 13.1 个月**，所以 `NEW_DIRECTION_CANDIDATE` 只能读作「相对可见基线为新」。
6. **PMA 补充的绝大多数是行政类**（生产/地点/标签），不是技术方向证据；本报告用 `evidence_specificity` 把这一点逐条记录。独立证据「数量多」不等于「信息量大」。
7. **同企业 + 同 track 的核验几乎自动成立**。美敦力在本证据库 23/38 个 track 有事件；因此 `INDEPENDENTLY_SUPPORTED` 是**必要但很弱**的背景核验，**不是**「新兴方向被证实」。
8. **track 归属继承上游映射，且存在关键词通胀**。管线不重新分类 FDA 事件；进入 track 单元的 61 个岗位中，**47 个（77%）的 track 证据只来自岗位描述、标题里没有该 track 关键词**（最高单元 100%，`medical_ai` 68%，`ep_pfa` 50%）。`medical_ai` 的 25 个岗位里混有法务/QA/系统管理员等，`resuscitation` 单元是一个 EHS 岗位——**人工复核第一步必须是核对引文上下文**。
9. **没有因果、没有意图、没有内部研发**。所有材料都是公开活动；「招聘 → 研发方向 → 未来产品」每一环都需要独立证据与时间序列，本轮都没有。
10. **没有概率校准**。分类器的 `confidence_basis` 是规则计数，不是概率；本报告不输出任何「X% 准确率/概率」。
11. **CT.gov 查询是「每 track 一个最长关键词」的有界查询**，不是穷尽检索；`n=0` 和 `0 条通过规则` 都受查询词限制（例如 `surgical_robotics` 用 `AUTONOMOUS SURGERY`，可能过窄）。
12. **数据质量已实测**：payload 截断 8,596 条；Draeger/Mindray 在该 dev 库 0 条；CT.gov 缓存不入 git。这些都已写进 `evidence_linking.json` 的 `limitations` 与 `evidence_source.db_probe`。

---

## 7. 建议的人工复核步骤（通用清单）

对任何候选单元，按顺序做，且只产出「候选观察」或「否决理由」，不产出方向结论：

1. **核对引文上下文**：打开 `postings[].source_url`，确认 `track_quotes[].quote` 出现在职责/技术要求中，而不是公司介绍、合规声明或福利段落。
2. **核对职能真实性**：`function_class` 是规则臂 A 的结果；确认岗位是否真的属于研发（例如 `ALGORITHM_SOFTWARE` 的 IT 运维岗 vs 产品算法岗）。
3. **核对独立证据**：打开 `linked[].url`，确认 K/P/Z/NCT 号与日期；看 `evidence_specificity`——**行政类 PMA 补充不能当技术方向证据**。
4. **核对时间关系**：证据是否在 `[anchor−24 个月, anchor]` 内；`as_of ≤ anchor`；越界证据在 `failed_rule_counts` / `rejected` 里。
5. **核对方向新颖度**：读 `direction_novelty` 的计数（首末事件、基线/近期条数、事件类型），而不是只看标签。
6. **记录反语境**：召回、行政申报、上游 track 归属异常都要写进人工复核记录。
7. **留给下一次快照**：本轮所有单元都不升级为方向结论；下一次快照（同源、同口径）时再做「新增/消失/改写」的差异比较；**两次快照是定义「变化」的最低条件**。
8. **失败也记录**：被规则拒绝的强证据（如 NCT07298473）要保留，供下一轮修改规则时审计——但**修改规则必须在测量前预注册**，不能事后为了让某条证据通过而改。

---

## 8. 复现与文件清单

```bash
# 1) 生成证据关联（离线、确定性；自动选择权威快照）
python experiments/innovation_signals_observatory/evidence/link_evidence.py

# 2) 重新抓取 ClinicalTrials.gov（可选；有界、8 次请求、缓存不入 git）
python experiments/innovation_signals_observatory/evidence/fetch_ctgov_evidence.py \
  --tracks ep_pfa,cardiac_rhythm,medical_ai,neurostimulation,neurovascular,respiratory,structural_heart,surgical_robotics \
  --company-key medtronic

# 3) 离线测试（18 项：同企业≠支持、超窗拒绝、无证据不静默丢弃、词汇封闭、方向新颖度、只读 DB 等）
python -m pytest tests/test_innovation_signals_evidence.py -q
```

| 产物 | 说明 |
|---|---|
| `experiments/innovation_signals_observatory/evidence/link_evidence.py` | 确定性关联管线（无网络；只读 DB；规则常量写死） |
| `experiments/innovation_signals_observatory/evidence/fetch_ctgov_evidence.py` | 唯一联网组件；有界请求 + 原始缓存（不入 git） |
| `experiments/innovation_signals_observatory/results/2026-11-04/evidence_linking.json` | 机器可核查产物：逐格岗位/证据/计数/失败规则/查询/SQL/局限性 |
| `experiments/innovation_signals_observatory/results/2026-11-04/evidence_linking.md` | 简短机器摘要 |
| `tests/test_innovation_signals_evidence.py` | 离线测试 |
| `results/2026-11-04/_httpcache_evidence/ctgov/` | CT.gov 原始响应缓存（**不提交**，可重建） |

**关键版本/指纹**（详见 JSON 的 `snapshot`、`classifier`、`evidence_source.db_probe`）：岗位快照 SHA-256 `165dce8e…f80217`；证据库 SHA-256 `2b5c36f0…e15548`（76,632,064 字节）；分类器 `recruitment_taxonomy_rules_2026-11-04` / 函数映射 `recruitment_function_classes_2026-11-04`；track 词表 `tracks_device_2026-11`。

---

## 9. 术语与判定词汇表（封闭集合）

| 标记 | 含义（本轮实际用法） | 允许的表述 |
|---|---|---|
| `OBSERVED_FACT` | 来源明确写出、可逐字定位（岗位标题、发布日、K/P/Z/NCT 号） | 「观察到……」 |
| `CLASSIFIED` | 按确定性规则归类，附引文与规则依据 | 「按……规则归类为……」 |
| `CANDIDATE_TECHNICAL_HIRING_SIGNAL` | 同一企业同一 track、≥2 个独立岗位 ID、≥1 个研发职能岗位 | 「值得进一步调查的候选信号」 |
| `HYPOTHESIS` | 需要独立证据/时间序列核验的研究假设 | 「假设……」 |
| `INDEPENDENTLY_SUPPORTED` | 通过 §2.5 四条规则（**必要但很弱**：只说明该 track 有独立公开活动） | 「有独立证据支持『该方向存在活动』」 |
| `NO_INDEPENDENT_SUPPORT` | 没有条目通过四条规则（**不等于**「没有活动」） | 「该来源没有记录/记录不满足规则」 |
| `CONTRADICTED` | 有独立证据显示退出/撤回该方向（本轮不可达） | 「存在反证」（若未来可达） |
| `UNKNOWN` | 现有数据无法回答（低于门槛、来源无法表示该 track） | 「目前不可知」 |
| `NEW_DIRECTION_CANDIDATE` | 可见基线窗 0 条、最近 12 个月 ≥1 条（**仅相对可见基线**） | 「相对可见基线为新方向的候选」 |
| `RECENT_ACTIVITY` | 近期有活动、有部分历史，但不足以判为持续既有 | 「近期有活动，方向状态模糊」 |
| `ESTABLISHED_DIRECTION` | 活动跨 ≥18 个月且 ≥6 条、近期仍有；对该企业是既有业务 | 「既有方向，招聘更可能是业务常态」 |
| `NO_BASELINE_DATA` | 来源看得不够远，无法区分新/旧 | 「基线不足，无法判断」 |

**禁止的表述（本报告与 JSON 均不包含）**：企业「正在开发/正在转向某方向」；招聘数等于研发投入；模型置信数字当作概率；把单次快照岗位数当趋势；把「同企业同 track 的两条公开事件」当同一个研发项目。

---

*本报告由 `evidence-linker`（Phase 4 · WP2c）依据 `evidence_linking.json` 撰写；所有数字可回溯到该 JSON 的对应字段。报告本身不新增任何未记录的事实。*
