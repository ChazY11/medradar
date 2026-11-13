# REFOUNDATION-001 执行摘要

**面向：** 项目负责人
**编制：** MedRadar 首席架构 / 科研基础设施 / 技术审计（REFOUNDATION-001 审计组）
**数据截止：** 2026-11-12（Asia/Shanghai）
**证据基线：** `origin/main` @ `b2a14c0`（2026-11-02）＋ GitHub 实时 API ＋ 全部 34 个远端分支
**配套文件：** 本目录下 11 份专项审计文档；机器可读事实见 `_evidence/repo_facts.json`

> **阅读约定。** 本文严格区分四类陈述：**[事实]** 由 git 对象、GitHub API、文件字节或可复现命令直接验证；**[推断]** 由事实推理得出，附推理链；**[建议]** 提案，不是结论；**[未验证]** 无法核实，注明原因。所有引用均给出路径、分支、PR 或提交。

---

## 〇、一页结论

**MedRadar 真实的科研资产，比它的 GitHub 首页所呈现的更强；它真实的工程状态，比它的分支数量所暗示的更脆弱。**

三句话概括本轮审计：

1. **`main` 只有一个版本，而且相当健康。** `main` = `b2a14c0`，仅合并了 PR #2–#11。我在干净工作树上实测：`python -m pytest` 全部通过，共 **1,074** 个测试。但 README 声称的 678、`STATE.json` 声称的 795、`ATTRIBUTION.md` 声称的 625，三个数字互不一致——**说明"状态"没有单一事实源**。
2. **19 个草稿 PR、约 282 万行未合并增量，构成了项目的"影子主体"。** 用户简报中提到的 MedRadar 2.0、Live Observatory、PHOENIX、ATLAS、HORIZON、CONVERGENCE、S-028–S-031，**没有一项在 `main` 上**，因此 GitHub Pages 上也一个都没有。
3. **最有价值的资产不是产品，而是一份可复现、含 5 次自我撤回的科研记录。** `research/RESULTS/README.md` 的 R1–R124 记录、`papers/PAPER_NEGATIVE_v1.md` 的负结果论文、以及 `research/DECISIONS.md` 的 ADR，质量高于大多数开源科研项目。**但这些资产目前被埋在分支和长文档里，首页完全看不到。**

**最严重的三个风险（按优先级）：**

| # | 风险 | 严重度 | 证据 |
|---|---|---|---|
| 1 | 本机 PHOENIX 分支有 **7 个提交不在任何远端**（领先远端 33、落后 16）；一旦清理分支即永久丢失 | **P0 / 不可逆** | `git rev-list c385553 --not --remotes` |
| 2 | 未合并分支在 git 中提交了**受限第三方原始数据**：PR #29 的 UN Comtrade（30 路径 / 6,234,301 B，许可明文禁止再分发）、PR #27 的第二份 Comtrade、PR #26 的 22,622 条非 OA 摘要 | **P0 / 法律** | `DATA_GOVERNANCE_AUDIT.md` §2/§3 |
| 3 | `main` **未设分支保护**（API 返回 404），19 个草稿并行、无 CODEOWNERS，任何人都能直接推送 | **P1 / 治理** | `GET /branches/main/protection` |

**一句话建议：** 先做"保命"（推送 7 个独有提交到 rescue 分支、给研究产物打不可变标签），再做"治理"（单一状态源 + 分支保护），最后才做"合并"（证据契约 → 产品栈 → 研究迁移）。**不要先合并。**

---

## 一、审计范围、方法与局限

### 1.1 范围

| 维度 | 覆盖 |
|---|---|
| 代码 | `main` 全部 1,135 个文件；6 大分支族的实际代码 |
| 分支 | 34 个远端分支 + 18 个仅本地分支 + 39 个 worktree |
| PR | 全部 30 个（合并 10 / 开放 20 / 草稿 19） |
| 科研 | 主分支 124 条结果记录 + 11 个分支研究族 |
| 数据 | 主分支与分支的提交数据、许可证、溯源 |
| 展示 | README ×2、GitHub Pages、5 张看板截图、徽章、架构图 |

### 1.2 方法

- `gh` CLI 实时读取 PR/仓库/Pages/分支保护；`git merge-base --is-ancestor` 重建真实血缘；blob hash 判定"复制 vs 继承"；path-collision 统计跨分支冲突面。
- 在 `origin/main` 的**独立 worktree** 中执行只读验证（`pytest`、`git show`），不触碰任何开发分支。
- 本轮**没有**执行：合并、删除、force-push、历史重写、生产数据修改、对数据源的网络探测。

### 1.3 局限（必须如实说明）

| 局限 | 影响 | 可验证范围 |
|---|---|---|
| 无法访问 GitHub 私有审计日志与 Actions 全量历史 | 无法确认是否存在过强制推送 | 仅能确认当前 refs 状态 |
| 未重跑各分支研究实验（部分需网络/大数据） | 分支研究结论以**其提交的产物与文档**为准 | 主分支已实测；分支标注为"未独立复跑" |
| 未做法律意见 | 数据再分发风险为**工程判断**，非法律结论 | 已定位文件与许可证文本，交法务确认 |
| 未验证 1.2 GiB SQLite 快照 | 主分支数据不可在干净克隆中重现 | 只能确认 README/指标声称值 |

---

## 二、第一部分：当前 MedRadar 到底拥有什么

### 2.1 事实基线

| 项 | 值 | 等级 |
|---|---|---|
| 仓库 | `github.com/ChazY11/medradar`，public，151 stars / 8 forks | 事实 |
| 创建 | 2026-10-31 | 事实 |
| `main` HEAD | `b2a14c0`，2026-11-02，PR #11 合并提交 | 事实 |
| `main` 文件数 | 1,135（Python 约 4.26 MB） | 事实 |
| 合并 PR | 10 个（#2–#11），共 +541,569 行 | 事实 |
| 开放 PR | 20 个（#1, #12–#30），其中 19 个草稿，共 **+2,824,212 行** | 事实 |
| 远端分支 | 34 个；其中 7 个含未合并产品栈血缘 | 事实 |
| 本地独有提交 | 5 个分支合计 39 个"领先"提交；PHOENIX 领先 33 / 落后 16，其中**仅 7 个为本地独有** | 事实 |
| Releases | 0 | 事实 |
| Issues | 0（开/关均无），issue 模板却已存在 | 事实 |
| Pages | `main:/docs` legacy 构建，最近构建 `b2a14c0` | 事实 |
| 许可证 | `LICENSE` = MIT；GitHub 识别为 `other` | 事实 |
| `main` 测试 | **1,074 collected，全部通过**（2026-11-12 实测） | 事实 |

**[推断]** "0 issues + 19 草稿 + 0 release + 无分支保护" 四个信号叠加，说明这个仓库的协作模式是**"分支即工作区、PR 即存档"**，而不是"issue → PR → review → merge"的常规开源流程。这解释了为什么研究会以 PR 草稿形式堆积，而不是以论文/报告形式发布。

### 2.2 `main` 真正拥有的能力（可验证）

`main` 是一个**可运行的证据采集 + 研究基础设施 + 离线演示**的混合体，而非纯产品：

| 能力 | 位置 | 状态 |
|---|---|---|
| openFDA 510(k)/PMA/召回/分类、药品批准、ClinicalTrials.gov v2、SEC 8-K 采集 | `medradar/collect_*.py`、`medradar/intelligence/sources/` | 可运行（离线测试覆盖） |
| 统一 point-in-time 事件表：`available_at` + `timestamp_quality` | `medradar/db.py` | 可运行 |
| 实体/技术赛道解析 + 未匹配计数外显 | `medradar/config.py`、`config/*.json` | 可运行 |
| 赛道热度（THI、Gamma–Poisson 收缩）、方向（JS 散度）、新颖度 | `medradar/analyze.py` | 可运行 |
| 双时态知识库（valid time vs knowledge time）+ 不可变预测注册表 | `medradar/tkg/`、`medradar/forecast_registry.py` | 可运行，31+43 测试 |
| 净化式多窗口 Market-to-R&D 评估 + 7 源消融 + 朴素基线 | `experiments/reverse_rd_v1/`、`v2/` | 冻结产物已提交 |
| 确定性、可引用证据的研究代理 | `medradar/research_agent.py` | 可运行 |
| 离线 demo、自包含看板（零外部请求） | `medradar demo`、`docs/dashboard.html`（3.35 MB） | 可运行 |
| 研究代理（profile / snapshot / promotion） | `medradar/intelligence/profile.py`、`snapshot.py`、`promotion.py` | 可运行 |

**[事实]** `main` 的架构是清晰的五层：`CLI → pipeline/analyze → collectors → SQLite(events) → intelligence/tkg/studies`；`docs/SCHEMA.md` 有 schema 文档；`verifier/` 有验收运行记录。**这不是一个失控的代码库——失控的是它之上的分支层。**

### 2.3 分支上"存在但未发布"的能力（严禁在首页暗示）

| 能力族 | 分支 / PR | 规模 | 状态 |
|---|---|---|---|
| MedRadar 2.0 产品面（company/radar/analyst/evidence + `web/`） | `feat/medradar-2.0-mvp` / #12 | +17,646 | 草稿 |
| Live Observatory v1（append-only 观测账本 + 官方源适配器） | `feat/live-observatory-v1` / #13 | +31,301 | 草稿 |
| Observatory Reliability（单写者租约、备份、7 天验证、systemd） | `feat/observatory-reliability-v1` / #14 | +22,899 | 草稿 |
| S-028 时序公司-技术图谱早信号研究（负结果） | `research/s028-...` / #15 | +114,442 | 草稿，**负结果** |
| S-029 基于证据的时序关系重构（NO-GO） | `research/s029-...` / #16 | +133,237 | 草稿，**NO-GO** |
| 仓库整理 / 研究索引 / 数据资产治理 | `maintenance/repository-consolidation` / #17 | +947/−805 | 草稿 |
| AI 证据复核（机器复核，非人类真值） | `research/ai-evidence-review` / #18 | +575 | 草稿 |
| 本地小模型 + QLoRA（Qwen3-4B） | `research/local-llm-foundation` / #19、#20 | +49,290 | 草稿 |
| Phase 4 创新信号观测（招聘通道） | `research/innovation-signals-observatory` / #21 | +64,441 | 草稿 |
| S-031 招聘能力与研发证据研究（100 条 AI 初标） | `research/s031-...` / #22 | +303,926 | 草稿，**不得当作已验证** |
| PHOENIX-001 / 002 / 003 | `research/phoenix-*` / #23–#26 | +420,708 | 草稿，**NO-GO 为主** |
| DATA-EXPANSION-001 全球数据源 | `research/data-expansion-001` / #27 | +260,389 | 草稿 |
| ATLAS-001 身份/证据/图谱底座 | `foundation/atlas-001` / #28 | +18,648 | 草稿 |
| HORIZON-001 全球数据前沿 | `research/horizon-001` / #29 | +692,975 | 草稿，**数据许可风险** |
| CONVERGENCE-001 ATLAS × HORIZON 集成 | `integration/convergence-001` / #30 | +690,079 | 草稿，**含 HORIZON 拷贝** |

**[事实]** 用户简报未提及的 **#1、#18、#21、#22** 也是真实工作，其中 #22 规模排第三、#21 是唯一的招聘通道产品化尝试。

### 2.4 科研资产：这个项目真正的护城河

**[事实]** `research/RESULTS/README.md` 记录了 **R1–R124** 条结果，全部绑定 `experiments/**` 下的已提交产物；`papers/CLAIMS.json` + `verify_claims.py` 对论文的 45–51 条定量声明做**双向机器校验**（0 失败）；`papers/figures/` 的 4 张 SVG 由 `verify_figures.py` 重算 131 个点。

研究方法论上，这是**教科书级别**的自我纠错记录：

| 关键结论 | 编号 | 方向 |
|---|---|---|
| 持续配对可预测，但**不超过持续性基线** | R1 | null |
| 新增 SEC 财务 / PIT 市场 / OpenAlex 论文**均无可检测排序增益** | R3–R5 | 负 |
| 校正后 naive-increase 的"预测力"从 0.49 翻转为 **1.22（区间含 1）**，无预测因子显著 | R67 | null |
| 校准把"35 个动量告警"压缩到"**4 个统计支持**" | R63 | 方法 |
| 检测器在 2% 误报下只捕捉 **0.223** 的注入漂移；**2× 变化在任何诚实预算下不可检测** | R15/R17 | 负 |
| 检测器排名**随分辨率反转到 Kendall τ = −1.0**，不存在全局最优 | R88 | 负 |
| 首个"阳性"（ivd_immuno 入场聚集）被**撤回**：79% 是法事实体首次出现 | R37 | **撤回** |
| 入场聚集线索**以 null 关闭**，转向数据获取而非继续调参 | R43 | 决策 |
| 首个经预注册确认的预测：二分类 BA 0.584、precision 0.914 vs 基线 0.696；但**只能分二元，ramp 召回 0.142** | R82/R83 | 窄阳性 |
| 招聘通道覆盖 5 家深案公司中的 **1 家**；招聘-监管滞后检验**从未运行**（不是 null） | R53/R54 | 结构性限制 |
| 密度缩放经**失败后修订准则**确认：ramp 召回 0.444 vs 0.204，2.18× | R118 | 阳性（事后确认） |
| 6 份快照 0 泄漏；轮末 7 项验证全通过 | R123/R124 | 基础设施 |

**[事实]** `papers/PAPER_NEGATIVE_v1.md` 是一篇完整的负结果论文：55,592 条试验中**映射到器械赛道的为 0**；20,976 条 8-K 中仅 **1,360** 条带 company key；预注册门槛（≥10 对）实际只有 **3 对**；16 个 firm-track 单元只有 **1** 个合格 onset；主评估窗口 **0** 个。结论原文：*"the binding constraint is information, not modelling."*

**[事实] 结论统计（必须原样保留）：** 4 项研究级明确 NO-GO（early-signal G1、S-029、PHOENIX-002、PHOENIX-003）；1 项线索级 NO-GO（DATA-EXPANSION EXP-C，`NO_DETECTABLE_LEAD`，p=0.569）；4 项"不可评估/被阻断/功效不足"（S-030 QLoRA、early-signal O1、S-031、hiring lag）；S-028 被"封存为可信的探索性负结果，但不能封存为确证性结果"。论文自身结算是 **"五次撤回 : 一条被确认的决策规则"**。这份"负结果多于正结果"的记录，是项目最可信的部分。

**[事实] 科研完整性上必须知道的三件事：**

1. **项目至今没有任何前瞻性（prospective）证据。** 所有"预测"都是带注入滞后的 class-S 回测；class-P（真实前瞻）为空。`research/STATE.json` 自己写着 Understand = "prototypes only; no validated research-quality output"，Anticipate Level A = "not built"。**因此对外只能说"方法可运行"，不能说"具备预测能力"。**
2. **身份解析是普遍性瓶颈，而且会系统性偏置结论。** 93.1% 的申请人为 `UNKNOWN`；按规范名检索会丢失 67.68% 证据；86.1% 的事件没有 roster 公司；UDI 桥接覆盖率仅 0.329%。所有 firm-level 结论实际上只关于一个**小而高度精选**的子集。
3. **文字与机器产物已在关键处漂移。** HORIZON 的 EXP-H2 叙述在 9 个数字中错了 8 个（官方为 726/0/0/726，叙述为 712/387/325）；`AUDIT.json` 记 "retractions marked: 3" 而论文记五次撤回且未解释；S-028 的 `HYPOTHESIS_REGISTRY.md` 与任一 freeze hash 都不匹配；S-029 的 prereg/metrics/hash 是同一提交一次性入库。**哈希只能证明字节，不能证明句子。**

**[事实] CONVERGENCE 的独立验证并不干净：** 其独立 verifier 结果为 **81 PASS / 10 FAIL / 4 UNVERIFIABLE**，不是"全部通过"。

**[推断]** 该论文 + R1–R124 的组合，其学术可信度**高于**任何"早期信号预测"营销叙事。如果项目只能对外发布一件东西，应该是它，而不是 dashboard 截图。

### 2.5 数据资产

| 资产 | 位置 | 状态 |
|---|---|---|
| `config/*.json`（公司、赛道、产品族、universe） | `main`，2.18 MB | 已提交，核心知识 |
| `experiments/**` 冻结产物 | `main`，15.05 MB / 657 文件 | 已提交 |
| `docs/metrics.json`、`summary.csv`、`report_*.md` | `main`，6.39 MB | 生成物，已提交 |
| SQLite 主库（README 称 1.2 GiB） | **不在 git**（`.gitignore` 的 `data/`） | 需重建 |
| HORIZON 原始数据集 | `research/horizon-001`，约 101 MB / 1,826 blobs | **未合并，许可风险** |
| UN Comtrade 原始响应 | `.../un_comtrade/raw/*`，约 2.56 MB | **未合并，P0 风险** |

**[事实]** `main` 的 `.gitignore` 明确排除 `data/`、`out/`、`*.xlsx`，并把 `docs/` 作为 Pages 站点提交——数据卫生在**主分支上是有纪律的**；风险全部来自未合并分支。

---

## 三、第二部分：现在为什么会变得混乱，哪些问题最严重

### 3.1 根因链（不是"代码乱"，而是"状态没有单一事实源"）

```
无分支保护 + 无 CODEOWNERS + 0 issues
        ↓
"分支即工作区"：每个 Agent 从自己看到的时点 fork，PR 只作存档
        ↓
19 个草稿并行，PR base 与真实血缘脱节（如 #22 基于 main 却含 #12–#14 血缘）
        ↓
状态分散在 README / STATE.json / AUDIT.json / BACKLOG.yaml / DECISIONS.md / metrics.json
        ↓
同一事实出现 625 / 678 / 795 / 1074 四个测试数；0.2.2 / 0.3.0 / 0.4.0 / 0.5.0 四个版本
        ↓
Agent 之间无法判断"什么是真的"，于是重复建设底座（6 套证据 store、6 个身份解析器）与重复拷贝分支（CONVERGENCE）
```

### 3.2 最严重的问题（P0 → P2）

#### P0-1 未推送的 PHOENIX 提交（不可逆丢失风险）

**[事实]** 本地 `research/phoenix-001-external-methods` = `c385553`，远端同名分支 = `bd2f839`：本地**领先 33 个提交、同时落后 16 个提交**，其中**只有 7 个提交不在任何远端引用中**；该本地分支从 **S-028 的 tip** 分出，而不是从 main。因此"33 个未推送提交"混淆了三件事：领先数（33）、落后数（16）、真正本地独有（7）。
**[事实]** 另外还有 4 个分支有未推送提交：`research/temporal-knowledge-graph`（2）、`research/forecast-registry`（2）、`phase3/registry-cycle`（1）、`integration/audit-dryrun`（1）。此外 `research/early-signal-ai-review` 是第 4 个"无 PR 的远端分支"，且是 `full-history-v1` 工作的唯一存放处。
**[建议]** 本轮结束前先把 7 个独有提交推到一个 `rescue/*` 分支并打标签。**这是唯一无法靠事后补救解决的问题。**

#### P0-2 第三方原始数据进入 git（法律与体积双重风险）——比预想更严重

**[事实] 经 `DATA_GOVERNANCE_AUDIT.md` 逐字节复核，这不是一个分支的问题，而是三条 RED 分支：**

| 分支 / PR | 受限内容 | 体量 | 判定 |
|---|---|---|---|
| `research/horizon-001` / #29 | UN Comtrade 原始 + 派生数据（`raw/*.json` 24 个、`un_comtrade.jsonl` ×2、派生的 `comtrade_usd` 单元） | **30 路径 / 6,234,301 B** | **RED**：Usage Agreement §5 明文禁止复制、再分发、发表 |
| `research/data-expansion-001` / #27 | **第二份** Comtrade preview payload（此前未被报告） | 255,265 B | **RED** |
| `research/phoenix-003-early-evidence` / #26 | Europe PMC 全量摘要，其中 **22,622 / 36,644（61.7%）为非 OA** | 29.0 MB 压缩 | **RED**：非 OA 摘要不随聚合器许可再分发 |
| `research/s029` / #16 | 约 1,300 条缓存摘要 | ~3 MB | AMBER：删 `data/raw/` 即消除且无损 |
| `integration/convergence-001` / #30 | 原始 payload 已不在，但被限制的**派生单元**仍残留在 5 个文件中（含 `licence_policy.json` 与生成它的脚本） | 5 文件 / 7 处 | AMBER：先做 5 文件脱敏 |
| #21 / #22 | 雇主招聘全文 9.5 MB + ~26 MB | ~35 MB | AMBER：robots 允许抓取 ≠ 允许再发布 |

**[事实] 还有两处"元数据自相矛盾"：** ① `LICENSE`（24 个 ref 同一 blob）在 MIT 正文后附加了一段"不批量再分发源数据"的声明——**该声明在 3 条分支上是假的**；② 仓库没有任何 `NOTICE`/`THIRD_PARTY` 文件，`docs/ATTRIBUTION.md` 是开发署名而非数据署名，因此 OGL/CC-BY 的署名义务在所有分支上都未履行。

**[事实] 好消息：全仓库 24 个 ref、3,896 个文本 blob 扫描后，0 个真实凭据（9 个命中均为误报），无 `.env`/密钥库。** 因此不需要轮换凭据；风险在数据与流程，不在密钥。

**[事实] 另外还有个人数据：** UK Find a Tender 的 3 个原始 OCDS 包含 **248 条具名采购方工作邮箱**（仅 #29）；`s029` 含 ≥417 个作者邮箱；ClinicalTrials/Europe PMC 含联系人信息。即使删除分支，已推送的对象仍可能被 fork/缓存保留。

**[事实] 结论：当前没有任何一个开放研究分支处于可合并状态。** 3 个 RED（#29、#27、#26），4 个 AMBER-conditional（#16、#22、#21、#30）。`main` 本身是安全的，只需两处外观性修复。

**[建议]** ① 在未获 UNSD 书面许可前，不要合并 #29/#27；② #26 去掉 `abstract` 字段、只保留 OA 记录；③ 个人数据文件在进入公开历史前先脱敏；④ 用 `licence_gate.py` + `licence_policy.json` 把"能否再分发"变成 CI 闸门，而不是文档。详见 `DATA_GOVERNANCE_AUDIT.md` §8。

#### P1-1 "影子主体"：PR base 与真实血缘不一致，且栈是 5 层深

**[事实]** 7 个分支包含未合并的 #12 产品栈血缘（#13、#14、#15、#16、#21、#22、phase4-base）。**更关键的是 `#15`（S-028）本身也是 `phase4-base`、`#21`、`#22` 的祖先**（`git rev-list --count s028 ^phase4-base` = **0**）——栈实际是 **5 层深**，`#21/#22` 静默引入了产品栈**和** S-028。
**[事实]** 因此评审看到的 diff 严重失真：
- **#22** 声明 base = `main`，600 个变更文件中 **567 个（94.5%）与 #21 字节相同**，真实增量只有 **33 文件 / +4,032 行**；
- **#30** 的 815 个变更文件中 **651 个（79.9%）与 #29 字节相同、68 个与 #28 相同**，真实增量远小于 +690,079 行；
- **#21** 的 base 是一个没有 PR 的分支 `integration/phase4-base`。
**[推断]** 评审者看到的 diff 与分支真实依赖不符，**代码审查在结构上不可能有效**——这不是"草稿多"，而是"草稿的元数据在说谎"。

#### P1-2 并行"证据/身份/图谱"底座：不是三套，是六套

**[事实]** `TECHNICAL_DEBT_REGISTER.md` 逐文件核对后确认：**6 套证据实现**（`db.py`、`tkg/store.py`、`intelligence/storage.py`、`#14 ledger.py`、`#28 atlas/db/migrations.py`、`#27 store.py`）、**6 个身份解析器**（公司至少有 5 种不兼容主键）、**8 个来源注册表**（`config/sources.json` 几乎从未被加载）、**4 个观测账本**（不可变性各不相同）、**6 个查询引擎**、**3 处预测记录**（两种 id 命名）。
**[推断]** 这与研究中"没有独立来源确认"的困境同源：每套 store 有自己的 schema、时间字段与去重规则，跨 store 无法 join，只能重算哈希（TD-033）。
**[事实]** 债务总账共 **40 项：6 Critical / 13 High / 15 Medium / 6 Low**。其中 ATLAS 的 `identity/normalize.py` 自己写着 *"Ported from medradar.external_sources.identity"*，`schema.py`/`store.py` 与旧实现的相似度为 42.4% / 19.8%——**它是"移植"，不是"继承"**。另有 `medradar run` 在 `__main__.py:296` 与 `:349` **重复调用 `build_metrics` 两次**，使每周主流程的 CPU 翻倍。
**[建议]** 以 `tkg/` + ATLAS 的 `identity`/`quality` 为收敛点，其余退为 adapter；这一项是 TD-001/002/003 的根因。

#### P1-2b `main` 的事件库是可变的（科研完整性风险）

**[事实]** 主分支的 `medradar/db.py:537` 对 `event_id` 使用 **`INSERT OR REPLACE`**，而所有较新的 store（TKG、forecast registry、#14 ledger）都是 append-only。
**[推断]** 一次重跑可以**静默改写**已被回测消费过的历史事实。这与 `DECISIONS.md` D-005"冻结产物不可变"的原则直接冲突，而冻结保护只覆盖 `experiments/`，没有覆盖 `events` 表。
**[建议]** 把 `events` 改为 append-only（`event_version` 表或 soft-delete），并在 Phase 2 的契约中强制。

#### P1-3 CONVERGENCE 是 HORIZON 的拷贝，但它也是唯一"已消毒"的版本

**[事实]** `integration/convergence-001` 的 815 个变更文件中 **651 个（79.9%）与 `research/horizon-001` 字节相同**，而 horizon **不是** convergence 的祖先（`merge-base --is-ancestor` 为假）；ATLAS 则是其祖先（68 个相同文件）。
**[事实] 重要的反转：** 两者相差的 37 个文件恰好是 **30 个受限 Comtrade 路径 + 3 个 UK 招标原始包 + 4 个派生报告**——**#29 是未消毒的原始版本且已公开，#30 才是消毒后的拷贝**（其派生单元仍残留 5 个文件，见 P0-2）。
**[建议]** 不应合并 #29；**#30 是更合适的交付载体**，但必须先把 5 文件派生泄漏脱敏。#29 与 #30 应视为**一份工作**，不可同时合并。

#### P1-4 治理缺口

**[事实]** `main` **无分支保护**（404）；无 `CODEOWNERS`；4 个 workflow（ci / forecast-cycle / live / weekly），Pages 只从 `main:/docs` 构建。
**[推断]** 任何人都可以绕过 CI 直接推送 `main`；19 个草稿无人清理；Pages 永远落后于真实研发状态。

#### P2-1 状态与版本文档漂移

**[事实]** 测试数：README 678 / ATTRIBUTION 625 / STATE.json 795 / 实测 1,074；`main` 上还能找到 **七个**不同的测试计数（274/578/625/636/678/679/795）。版本：`pyproject.toml` `0.5.0` / README "v0.2.2 稳定核心、v0.3.0 整合" / ATTRIBUTION "v0.4.0"。跨 `main` + 20 个开放 head，`README.md` 有 **7 个不同 blob**、`pyproject.toml` **5 个**、`CHANGELOG.md` **3 个**。`research/DECISIONS.md` 的 D-001 仍写 *"`main` is frozen at `7a639f7` (v0.2.2)"*，而 `main` 已比该提交前进 154 个提交。`research/STATE.json` 甚至硬编码了本机路径 `<REDACTED_LOCAL_PATH> `main_untouched_at: 7a639f7` 并非当前 `main` HEAD。
**[建议]** 全部改为生成式，见 `AGENT_COLLABORATION_PROTOCOL.md`。

#### P2-1b 已经存在一份"竞争版"首页

**[事实]** PR #17 `maintenance/repository-consolidation` 已经包含一份 **README 重写**（+689/−443）以及 `docs/PROJECT_STATUS.md`、`docs/REPOSITORY_AUDIT.md`、`docs/DATA_ASSET_REGISTER.md`，其定位与"科研优先"一致。
**[推断]** 若直接按 `README_REDESIGN_PROPOSAL.md` 覆盖，会与 #17 产生第二次重复建设。
**[建议]** 先决定首页唯一 owner（D-19）：建议**先落 #17 的基础事实页，再以重设计方案做第二遍**（provenance ledger + 中英一致 + 视觉规范 + CI 门禁）。

#### P2-2 仓库体积与生成物混入

**[事实]** `main` 提交了 `docs/dashboard.html`（3.35 MB 单文件，历史上有 4 个修订）、`docs/preview.png`（489 KB ×12 修订）、`docs/metrics.json`（469 KB ×11 修订）、`papers/*.log`、`tools/*.log`、`tools/round_end.json` 等生成物；`experiments/` 占主分支 15 MB。**所有 ref 合计 476.46 MiB 唯一 blob，而 `main` 只有 29.06 MiB**——历史体积约是工作树的 3 倍。
**[建议]** 保留必要展示物，其余迁出或用 Release 资产；生成物加 `BEGIN GENERATED` 标记与校验；停止提交生成的 HTML。

#### P2-2b CI 的覆盖面不足

**[事实]** `ci.yml` 只有 4 类作业（3 个 Python 版本的测试、data-stats、Windows 安装、离线 demo）；**没有 lint、类型检查、覆盖率、安全扫描**；没有依赖锁文件（`pip install .` 解析未固定版本）；CI 跑的是 `python -m medradar selftest`（unittest），而 `pyproject.toml` 配置的是 pytest——两个 runner 可能给出不同结论。
**[建议]** 加 ruff/mypy/pip-audit/secret-scan 与锁文件；统一 runner；见 `AGENT_COLLABORATION_PROTOCOL.md` 的 gate 清单。

#### P2-3 首页与真实状态脱节

**[事实]** README 以"周度 FDA 情报简报 + 纸面交易"开场，仓库描述却是"evidence-first research platform"；31.7 KB 的 README 里没有任何一处说明 **19 个草稿 PR 不在 `main` 上**。Pages 站点与 README 停留在 2026-10-31 快照。
**[建议]** 按 `README_REDESIGN_PROPOSAL.md` 重建信息架构，首页第一屏回答"这是什么/不是什么/现在能做什么"。

---

## 四、第三部分：理想的统一 MedRadar 应当是什么样

### 4.1 定位（建议采纳，需负责人决策 D-01）

> **MedRadar 是一个以"公开证据能否提前识别医疗技术变化"为唯一科学问题的研究仪器，附带一个可运行的情报演示，而不是一个预测产品。**

三层结构不变，但**边界必须可执行**：

```
A. 科学研究层（核心）
   research/protocols/  research/runs/  research/results/
   冻结协议 → 运行 → 结果 → 结论（含负结果）
        ↑ 只通过"证据契约"读取数据，不直接读采集器
B. 证据与情报平台层（基础设施）
   evidence contract · identity · temporal store · quality/licence gate
        ↑ 采集器只负责"取回并登记"，不负责"解释"
C. 应用层（价值出口）
   研究台 / 情报页 / 报告 / API
   只消费"已验证"的结论视图，不消费原始推断
```

### 4.2 目标架构的十条设计约束

1. **一个证据契约。** 所有来源归一为 `EvidenceRecord`：`source_id`、`source_record_id`、`retrieved_at`、`published_at`、`event_time`、`valid_from/to`、`payload_hash`、`licence_tag`、`quality_flags`。字段级定义见 `ARCHITECTURE_TO_BE.md`。
2. **身份是"主张"而非"事实"。** `EntityRef` + `IdentityClaim`（含置信度、方法、可复核证据），禁止模糊匹配直接改写标签（沿用 `DECISIONS.md` D-002 的教训）。
3. **采集与归一化解耦。** connector 产出 raw + manifest；normalizer 产出一致化证据。**raw 不进 git**，只进内容寻址存储 + hash manifest。
4. **四个时间轴。** `event_time` / `published_at` / `observed_at` / `ingested_at` 必须同时存在；任何 as-of 查询以 `published_at`（或明确声明的 knowledge time）为准，并**自动泄漏审计**（沿用 R70 的教训：trial lane 与 code-map 曾整表读取，是真实泄漏路径）。
5. **质量与许可是一等公民。** 每条证据带 `quality_flags` 与 `licence_tag`；合并/导出前有 gate；`DATA_LICENSES.md` 逐源登记。
6. **冻结是一等公民。** 协议、数据、代码、结果四元组哈希进 `FREEZE.json`；CI 阻止无新冻结记录的修改。旧结果**可复现但不被覆盖**（沿用 D-005）。
7. **新旧实验共享底座，不共享结论。** `StudyRun` 记录"用哪个契约版本、哪份快照、哪版代码"；应用层只能读 `verified` 视图。
8. **本地优先。** 单机 SQLite + Parquet/JSONL + 文件工件即可跑全流程；大算力通过 `Runner` 接口外挂，不引入分布式系统。
9. **旧系统以适配器退役。** `tkg/`、`forecast_registry.py` 保留为主干；ATLAS 的 identity/quality 被吸收，其重复 store 退为 adapter；`observatory/ledger.py` 合并进 TKG。
10. **可删除性。** 每个模块必须有 owner、测试、文档与"删除它会破坏什么"的说明；无主模块标记 `deprecated`。

### 4.3 新旧模块映射（建议，详见 `ARCHITECTURE_TO_BE.md`）

| 现状 | 目标归属 | 处置 |
|---|---|---|
| `medradar/db.py` + `events` 表 | Evidence Store 的 SQLite 后端 | **保留**，扩展四时间轴 |
| `medradar/tkg/` | Temporal Store / as-of 查询 | **保留为主干** |
| `medradar/forecast_registry.py` | Forecast Registry | **保留为主干** |
| `medradar/atlas/{evidence,identity,quality}` | Evidence Contract / Identity Resolver / Quality Gate | **吸收** |
| `medradar/atlas/{store,graph,db/migrations}` | 与 TKG 重复 | **退役为 adapter** |
| `medradar/observatory/ledger.py` | Observation Ledger | **并入 TKG** |
| `medradar/intelligence/*` | 特征/模型/评估层 | **保留**，加 PIT 契约 |
| `medradar/studies/*` | 研究统计工具 | **保留** |
| `web/` + `medradar/product/` | 应用层 | **保留**，只读 verified 视图 |
| `research/horizon/*` | 全球数据 connector 集 | **拆分**：connector 保留，raw 数据外置 |

---

## 五、第四部分：具体应该怎样分阶段整合

> 原则：**每个阶段独立可上线、可验证、可回滚**；任何阶段失败都不影响 `main` 继续可用。详细工作项见 `MIGRATION_PLAN.md`。

### Phase 0 — 保命与冻结（0.5 天，**无代码变更**）

| 项 | 内容 |
|---|---|
| 目标 | 消除不可逆风险 |
| 动作 | ① 把 5 个本地分支的未推送提交推到 **`rescue/*` 新分支**（PHOENIX 的远端孪生已分叉，不能直接推它；本地领先 33、落后 16，独有 7）；② 为每个研究分支打 `archive/<study>-<sha>` 标签；③ 导出 `_evidence/` 快照；④ 记录所有 PR 的 head sha |
| 验证 | `git rev-list <branch> --not --remotes` 为空；标签数 = 研究族数 |
| 回滚 | 纯增量，无需回滚；标签可删 |
| 退出 | 0 个未推送提交；0 个无标签研究分支 |

### Phase 1 — 治理脊柱（2 天）

| 项 | 内容 |
|---|---|
| 目标 | 让"什么是真的"只有一个来源 |
| 动作 | ① `PROJECT_STATE.yaml` + 生成脚本；② 分支保护（require PR + ci）；③ `CODEOWNERS`；④ 修 licence 识别；⑤ CI 加"生成物未手改""冻结未被修改"两道门 |
| 验证 | 改动状态文件后 CI 失败；直接 push main 被拒 |
| 回滚 | 关闭保护规则即可；状态文件可删除 |
| 退出 | README/研究索引/CHANGELOG 均由状态文件生成 |

### Phase 2 — 证据契约与身份（5 天，核心）

| 项 | 内容 |
|---|---|
| 目标 | 一套 `EvidenceRecord` + 一套 identity + 一个 TKG |
| 动作 | ① 定义契约与 schema 迁移；② **#28 作为载体先行合并**（纯新增、70 文件、零冲突），但其重复 store 立即退为 adapter；③ 吸收 ATLAS identity/quality；④ `observatory/ledger` 并入 TKG；⑤ 四时间轴与泄漏审计进 CI；⑥ 许可证 gate |
| 验证 | 同一 as-of 日期，新旧路径产出**逐字节一致**的 PIT 快照；泄漏测试全绿 |
| 回滚 | 契约版本化（v1 并存），旧路径保留一个版本周期 |
| 退出 | 6 套证据 store 收敛为 1 套 + adapter；6 个身份解析器收敛为 1 套；`main` 测试仍全绿 |

### Phase 3 — 产品栈合并（4 天）

| 项 | 内容 |
|---|---|
| 目标 | 把 #12 → #13 → #14 按序合并 |
| 动作 | ① 以 Phase 2 契约 rebase；② 一次整体评审；③ `v0.6.0` |
| 验证 | 合并后 1,074+ 测试全绿；Observatory 7 天验证脚本可跑 |
| 回滚 | 合并前打 `pre-product-stack` 标签；`git revert -m 1` |
| 退出 | `main` 具备产品面且 Pages 更新 |

### Phase 4 — 研究迁移（3 天）

| 项 | 内容 |
|---|---|
| 目标 | 研究结论进主分支，研究代码按需迁移 |
| 动作 | ① 每项研究产出 `FREEZE.json` + 结论页；② S-028/S-029/PHOENIX/S-031 的**结论文档**进 `research/results/`；③ 代码在契约上重跑后才合并 |
| 验证 | 复跑结果与冻结产物逐项对比；不一致即缺陷 |
| 回滚 | 研究文档为新增，可整体 revert |
| 退出 | `RESEARCH_ASSET_REGISTER.md` 中每项研究在 `main` 有可追溯记录 |

### Phase 5 — 全球数据与许可闸门（3 天）

| 项 | 内容 |
|---|---|
| 目标 | #26/#27/#29 的数据能力可用且合法，且仓库体积不增长 |
| 动作 | ① raw 数据外置 + hash manifest；② 逐源许可登记与 `licence_gate.py`；③ #26 去摘要化（仅保留 OA 记录）；④ #27 移除第二份 Comtrade；⑤ connector 保留、数据按需重取 |
| 验证 | 干净克隆可仅凭 manifest + 脚本重建数据集；仓库体积不增长 |
| 回滚 | 关闭数据分支，不触碰 main |
| 退出 | 数据治理审计的 RED 项清零 |

### Phase 6 — CONVERGENCE 与展示层（4 天）

| 项 | 内容 |
|---|---|
| 目标 | 集成能力与首页同步 |
| 动作 | ① 基于 Phase 2 契约重新推导 #30，而非合并拷贝；② 新 README + Pages |
| 验证 | 首页每个数字有 provenance；"不在 main"清单为空或准确 |
| 回滚 | 首页为独立 PR，可 revert |
| 退出 | 首页与 `main` 完全一致 |

---

## 六、第五部分：需要项目负责人做出的关键决策

完整版见 `DECISION_REGISTER.md`（19 项，含选项、证据、风险）。**最需要本周拍板的 6 项：**

| ID | 决策 | 建议 | 不决定的后果 |
|---|---|---|---|
| D-08 | 是否立即推送 39 个未推送提交 | **是，立刻** | 不可逆丢失 |
| D-06 | 是否允许原始第三方数据进 git | **否**，改为 hash manifest | 法律与体积风险 |
| D-01 | 项目身份：科研平台还是情报产品 | **科研优先** | 首页与架构无法定稿 |
| D-09 | 哪套证据/身份底座为准 | **main 的 tkg + 吸收 ATLAS identity** | #28/#30 无法合并 |
| D-03 | 产品栈 #12–#14 是否按序合并 | **是，在 Phase 2 之后** | 7 个分支继续漂移 |
| D-14 | 是否保护 main | **是** | 碎片化会立刻复发 |

其余：D-04（19 个草稿的归档策略）、D-05（#1 关闭）、D-07（不重写历史）、D-10（#30 不按现状合并）、D-12（冻结机制）、D-13（版本号）、D-15（单一状态源）、D-16（交易叙事降级）、D-17（许可证）、D-18（发表负结果论文）。

---

## 七、第六部分：下一轮可以直接执行的工程任务

> 全部为**低风险、可独立验收**的任务，不含合并/删除/重写。按依赖排序。

| # | 任务 | 产出 | 验收 | 工作量 |
|---|---|---|---|---|
| T1 | 把 7 个独有提交推到 `rescue/*` 并给研究分支打 archive 标签 | rescue 分支 + ~20 标签 | `rev-list --not --remotes` 为空 | 0.5 天 |
| T2 | 生成 `PROJECT_STATE.yaml` 与 README 状态表 | 状态文件 + 生成脚本 | CI 中手改即失败 | 2 天 |
| T3 | 开启 main 分支保护 + CODEOWNERS | 仓库设置 + 文件 | 直接 push 被拒 | 0.5 天 |
| T4 | 修 `LICENSE` 的 SPDX 识别与 `DATA_LICENSES.md` | 两个文件 | GitHub 显示 MIT | 0.5 天 |
| T5 | 编写 `EvidenceRecord` v1 schema + 迁移草案 | `medradar/evidence/contract.py`（新增） | 单测 + 与现有 `events` 映射 | 3 天 |
| T6 | 把 ATLAS identity/quality 抽成独立模块 | 2 个模块 + 测试 | 不依赖 atlas store | 3 天 |
| T7 | 提交 `observatory/ledger` → TKG 适配器设计 | ADR + 适配器 | as-of 结果一致 | 3 天 |
| T8 | 对 #12–#14 做一次 rebase 可行性试运行（不推送） | 冲突报告 | 冲突文件清单 + 处置 | 1 天 |
| T9 | 为 S-028/S-029/PHOENIX/S-031 生成 `FREEZE.json` | 每研究一份 | hash 可复算 | 2 天 |
| T10 | 把 HORIZON raw 数据替换为 hash manifest | manifest + 抓取脚本 | 干净克隆可重建 | 2 天 |
| T11 | 用 `PROJECT_STATE` 生成新 README（英文+中文） | README PR | 所有数字有 provenance | 2 天 |
| T12 | CI 增加"冻结保护"与"生成物保护"两道门 | workflow 修改 | 故意改冻结文件即失败 | 1 天 |

---

## 八、优先级路线图（0 → 3 周，可按周并行）

> 采用 `MIGRATION_PLAN.md` 的实测工作量：**21.5 人日**。关键路径 = Phase 2 → Phase 3、Phase 5 → Phase 6；Phase 1 与 Phase 4 可并行。

```
2026-11-12 ┃ P0 保命（0.5d）：推送 39 提交 · 打 archive 标签 · 导出证据      → tag refoundation/p0
2026-11-13 ┃ P1 治理（2d）：PROJECT_STATE.yaml · 分支保护 · CODEOWNERS · 4 道 CI 门 → p1
2026-11-15 ┃ P2 证据契约 + 身份（5d）：#28 载体合并 → 吸收 identity/quality
           ┃                          → ledger 并入 TKG → 泄漏审计 → 许可 gate → p2
2026-11-20 ┃ P3 产品栈（4d）：#12 → #13 → #14（各自 rebase 到 p2）        → v0.6.0
2026-11-24 ┃ P4 研究迁移（3d）：S-028/S-029/PHOENIX/S-031 冻结 + 结论页     → p4
2026-11-27 ┃ P5 全球数据（3d）：#27/#29 raw 外置 + 逐源许可                  → p5
2026-11-30 ┃ P6 集成 + 首页（4d）：#30 去重后重新推导 · 新 README/Pages       → p6
```

**里程碑判据：**
- **M1（11-12 末）**：0 个未推送提交；所有研究分支有不可变标签。
- **M2（11-19 末）**：证据契约 v1 合入；6 套证据 store 的收敛路径确定；`main` 仍全绿。
- **M3（11-23 末）**：产品栈合入，`v0.6.0` 发布，Pages 与 `main` 一致。
- **M4（12-03 末）**：每项研究在 `main` 有可追溯结论页；首页每个数字有 provenance。

**若只能做一件事：** 做 Phase 2。单一契约 + resolver + gates 交付了大部分架构价值，并让其余分支以后都还能合并；只合产品栈而不建契约，等于"更多代码的现状"。

---

## 九、验收对照（用户简报的十项标准）

| 标准 | 达成 | 证据 |
|---|---|---|
| 区分 main 与 Draft PR 能力 | ✅ | §2.2 / §2.3；`_FACTS.md` §3–4 |
| 解释主要模块归属与依赖 | ✅ | `ARCHITECTURE_AS_IS.md`；§4.3 映射 |
| 识别重复实现与技术债务 | ✅ | `TECHNICAL_DEBT_REGISTER.md`；§3.2 |
| 追溯关键科研结论与负结果 | ✅ | `RESEARCH_ASSET_REGISTER.md`；§2.4 |
| 列出数据许可与科研完整性风险 | ✅ | `DATA_GOVERNANCE_AUDIT.md`；§3.2 P0-2 |
| 提供可执行架构整合方案 | ✅ | `ARCHITECTURE_TO_BE.md`；§4 |
| 说明每阶段验证与回滚 | ✅ | `MIGRATION_PLAN.md`；§5 |
| 提出 README 与视觉规范 | ✅ | `README_REDESIGN_PROPOSAL.md` |
| 不破坏现有系统与历史实验 | ✅ | 全程只读；唯一写入是 `docs/refoundation/` |
| 不擅自合并/删除/重写 | ✅ | `git status` 仅新增审计目录 |

---

## 十、给负责人的最后三句话

1. **这个项目最值钱的不是"能预测"，而是"知道自己不能预测，并把它记录了下来"。** 请先保护这份记录（T1、T9），再谈整合。
2. **混乱的根源不是代码质量，而是没有单一事实源 + 没有分支保护。** 这两件事各花半天就能修，收益大于任何一次大规模重构。
3. **本轮不修改任何代码，是对的决定。** 在 19 个草稿、6 套并行底座、2.8M 行未合并增量的情况下，先建立"可信的地图"比"快速清理"重要得多。

---

## 附录 A：证据索引

| 文档 | 内容 |
|---|---|
| `_FACTS.md` | 全团队共享的已验证事实基线 |
| `_evidence/repo_facts.json` | 仓库/PR/分支/体积的机器可读快照 |
| `_evidence/ancestry.json` | 分支真实血缘矩阵 |
| `_evidence/collisions.json` | 跨分支路径冲突面 |
| `_evidence/blob_identity.json` | 字节级复制/继承判定 |
| `_evidence/copy_volume.json` | 拷贝体积量化 |
| `REPOSITORY_INVENTORY.md` | 全仓库资产清单 |
| `BRANCH_PR_AUDIT.md` | 30 PR / 34 分支逐项处置 |
| `ARCHITECTURE_AS_IS.md` | 现状架构 |
| `TECHNICAL_DEBT_REGISTER.md` | 技术债务登记 |
| `RESEARCH_ASSET_REGISTER.md` | 科研资产总账 |
| `DATA_GOVERNANCE_AUDIT.md` | 数据许可与溯源 |
| `ARCHITECTURE_TO_BE.md` | 目标架构 |
| `MIGRATION_PLAN.md` | 迁移与回滚 |
| `README_REDESIGN_PROPOSAL.md` | 首页重设计 |
| `AGENT_COLLABORATION_PROTOCOL.md` | 多 Agent 协作制度 |
| `DECISION_REGISTER.md` | 19 项待决策 |

## 附录 B：本轮明确未做

- 未合并任何 PR，未删除/重写任何分支，未 force-push。
- 未修改 `main` 或任何开发分支；未改动冻结数据。
- 未覆盖 README，未生成任何"成果截图"。
- 未对生产数据源发起网络采集。
- 审计写入仅限 `docs/refoundation/`（独立 worktree `audit/refoundation-001`）。
