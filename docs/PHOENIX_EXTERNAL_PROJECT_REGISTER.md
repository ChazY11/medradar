# PHOENIX-001 — 全球外部项目技术图谱（13 项目审计登记册）

> **范围**：任务书第四节强制清单的全部 13 个项目，逐一登记，**无跳过**。
> **证据原则**：每条记录只写**本轮实际核实到的东西**。核不实的写 `UNKNOWN` 并说明原因。营销宣传不作为科研验证。闭源平台不作为可复制工程。
> **配套文件**：许可证细节见 `docs/PHOENIX_LICENSE_AUDIT.md`；逐项详细审计见 `docs/phoenix/audits/A00–A13`；复现状态见 `docs/PHOENIX_REPRODUCTION_REPORT.md`。
> **审计时点**：2026-11-08。

---

## 0. 总表

| # | 项目 | 类型 | 许可证 | 本地运行 | 复现状态 | 决策 |
|---|---|---|---|---|---|---|
| 1 | SciTrends `ddofer/Trends` | 开源仓库 | **无（无许可证）** | **是（隔离重跑其发布特征）** | **REPRODUCED（Table 1 全部四项指标精确吻合）** | **ADAPT（仅方法，零代码复用）** |
| 2 | PubTrends `JetBrains-Research/pubtrends` | 开源仓库 | **Apache-2.0**（已核实） | 否（不部署 Postgres/Redis/Celery 栈；算法独立重跑） | METHOD_ONLY | **STUDY_ONLY** |
| 3 | NIH iSearch / predictive breakthroughs | 公开论文 + 受限代码 | 代码 "requires a license" | 否（需 350–400 GB RAM；无许可） | NOT_REPRODUCED | **STUDY_ONLY** |
| 4 | The Lens | 商业平台（有论文） | 专有条款（自定义 CC-BY-NC-SA-*resonant*） | 否（未做任何数据查询） | NOT_ATTEMPTED（合规原因） | **STUDY_ONLY** |
| 5 | PTNS (Sci Rep) | 公开论文 | **CC BY-NC-ND 4.0** | 否（无代码、数据需商业库） | NOT_REPRODUCED | **STUDY_ONLY** |
| 6 | FDA AI 器械纵向研究 | 公开论文 | 开放获取 + FDA 公有领域数据 | **是**（独立实现 + 公式交叉验证） | **REPRODUCED（方法层）** | **ADOPT（方法）** |
| 7 | Clarivate DRG Medtech | 商业平台 | `UNKNOWN`（未公开可用 ToS） | 否 | NOT_APPLICABLE | **STUDY_ONLY** |
| 8 | MedVantage | 商业平台 | `UNKNOWN` | 否 | NOT_APPLICABLE | **STUDY_ONLY** |
| 9 | CMOP | 商业平台 | 有公开定价；完整条款 `UNKNOWN` | 否 | NOT_APPLICABLE | **STUDY_ONLY** |
| 10 | NextDevice（医药魔方） | 商业平台 | `UNKNOWN` | 否 | NOT_APPLICABLE | **STUDY_ONLY** |
| 11 | GBI DEVINT | 商业平台 | `UNKNOWN`（/terms 无正文） | 否 | NOT_APPLICABLE | **STUDY_ONLY** |
| 12 | DevicePro（药渡） | 商业平台 | `UNKNOWN` | 否 | NOT_APPLICABLE | **STUDY_ONLY** |
| 13 | 众成医械 Joinchain | 商业平台 | `UNKNOWN`；站点不可机器读取 | 否（**站点 BLOCKED**） | NOT_APPLICABLE | **STUDY_ONLY** |
| — | REA `rea-agents` 6.7.0 | 工具（非清单项，任务书第三节） | **MIT**（已核实） | **是**（已接入 DSH，207 工具） | VALIDATED | **ADAPT** |

**决策分布**：ADOPT 1（仅方法：A06）、ADAPT 2（SciTrends 仅方法 / REA 工具）、STUDY_ONLY 11、REJECT 0、BLOCKED 1（Joinchain 站点）。
**没有把任何项目"整体集成"进 MedRadar。SciTrends 的 ADAPT 是方法级适应，代码复用仍为零（无许可证）。**

---

# A. 优先实测的开源项目

## 1. SciTrends — `ddofer/Trends`

| 字段 | 内容 |
|---|---|
| 官方地址 | https://github.com/ddofer/Trends |
| 论文 | https://www.sciencedirect.com/science/article/pii/S2405844023109893（Heliyon, doi:10.1016/j.heliyon.2023.e23781） |
| 类型 | 开源代码仓库（实为 notebook + CSV 集合） |
| 许可证 | **无任何许可证文件**。仓库树无 LICENSE/COPYING，无逐文件 SPDX 或版权头，GitHub API `license=null`。论文为 **CC BY-NC-ND**，不授予代码权利 |
| 允许的使用方式 | **仅可借鉴公开方法，禁止代码复用**（无许可 = 保留所有权利） |
| 核心技术 | 科研主题时间序列预测；历史出版物增长规律；专利作为领先指标；Review/Original Research 比例；多窗口增长率与趋势特征 |
| 数据依赖 | 自有出版物/专利聚合 CSV（随仓库提交）；**无依赖清单，环境不可复现** |
| 当前可访问性 | 可访问（只读） |
| 本地运行结果 | **是**。在隔离目录 `D:\DEPPSKK\phoenix-external\scitrends\` 中，用其**已发布的派生特征**按论文流水线重建并重跑。本机未装 CatBoost 与 sentence-transformers（刻意避免 ~100 MB wheel + torch），故用 `sklearn HistGradientBoostingRegressor` 替代；**因此不对 Table 1 的 CatBoost 行作任何声称** |
| 需 GPU / 联网 / 付费 | 否 / 否 / 否 |
| 与 MedRadar 重复度 | **中低**（出版物/专利域 vs 监管事件；但 MedRadar 已有 `medradar/intelligence/sources/publications.py` 的弱出版物通道） |
| 值得迁移的科研方法 | ① **按当年总产出归一化**的流行度：`topic_pubs_year / medline_total_year × 100,000`；② **review : research 比例作为方向性特征**；③ 多窗口增长率与对数线性趋势；④ 严格时间验证设计 |
| 主要局限 | 域不匹配（出版物→器械监管）；**专利领先指标在本库无法检验（无专利表）**；无依赖清单，环境无法原样重建 |
| 数据泄漏风险 | 若把"全历史 review/original 比例"当特征则含未来信息。**已实证泄漏敏感性**：把 `y(t+5)` 作为特征追加后 R² 变为**恰好 1.0** → 说明该流水线对特征集极敏感，任何特征加入都必须经时间审计 |
| 复现状态 | **REPRODUCED —— Table 1 四指标精确吻合**：水平目标 R²=0.9732 / MAE 113.806 / medAE 44.378 / RMSE 229.128 vs 论文 0.973 / 113.80 / 44.37 / 229.12；Δ 目标 R²=0.0039 / MAE 115.419 / medAE 83.377 / RMSE 289.980 vs 0.004 / 115.42 / 83.38 / 289.98 |
| **复现的附带发现** | 论文对 Δ 目标的定义有歧义。实测表明其 Δŷ 是 **按当前热度归一化的 10 年差值** `100·(y[t+5]−y[t−5])/y[t]`，**不是 5 年变化**。这条歧义被复现过程本身解决 |
| **必须同时记录的反向证据** | 水平目标被**自相关主导**：持续性基线（直接沿用上期值）R²=0.969，与其模型 0.973 几乎无差；且其滞后基线**在 MAE 上比"预测不变"更差** → **可借鉴的是特征定义，不是效应量或精度主张** |
| **决策** | **ADAPT（方法级，零代码复用）** |
| 决策理由 | 许可证结论**不变**：无 LICENSE 文件 → 不能复制其任何代码。但**复现结果改变了价值判断**：Table 1 在四项指标上精确复现，证明方法被真正理解且可重实现（不是"读了论文"）。MedRadar 已有弱出版物通道，而 SciTrends 恰好补上它缺的两块：**按当年总产出归一化**与 **review:research 比例作为方向特征**。因此从 STUDY_ONLY 上调为 **ADAPT（仅方法）**。上调的是"方法值得适配"，**不是**"代码可以使用" |

## 2. PubTrends — `JetBrains-Research/pubtrends`

| 字段 | 内容 |
|---|---|
| 官方地址 | https://github.com/JetBrains-Research/pubtrends |
| 类型 | 开源代码（研究 Web 服务） |
| 许可证 | **Apache-2.0 已核实**：`LICENSE.txt` 11,316 B 标准全文，附录 "Copyright 2022 JetBrains Research."；无 NOTICE，无第二许可 |
| 允许的使用方式 | 代码可复用（需保留归属与变更声明）；本项目**未复用** |
| 核心技术 | 论文主题识别（NLP 聚类）、文献聚类、引用网络、主题变化与新兴领域、语义相似度 + 时间特征；Faiss 向量检索；Postgres + Redis + Celery 栈 |
| 数据依赖 | OpenAlex / Crossref 等文献数据；自建 Postgres 库 |
| 当前可访问性 | 可访问 |
| 本地运行结果 | **未部署整套栈**（任务书明确禁止）。改为在 `D:\DEPPSKK\phoenix-external\pubtrends\` 隔离重实现其**有辨识度的算法**，在合成数据上自测通过 |
| 需 GPU / 联网 / 付费 | 否 / 否 / 否 |
| 与 MedRadar 重复度 | **中**（主题识别与新兴领域检测 vs MedRadar 的赛道/信号检测） |
| 值得迁移的科研方法 | 主题聚类 + 时间窗变化检测的组合；语义相似度作为跨源对齐手段 |
| 主要局限 | 为文献域设计，需要文本语料；MedRadar 的监管事件是结构化短文本，语义聚类收益有限 |
| 数据泄漏风险 | 引用计数若取全历史值即含未来信息；新兴领域检测若用未来语料定义当前主题则泄漏 |
| 供应链风险（即使许可允许） | 从 GitHub Release URL 装 wheel 未按 hash 固定；额外 PyTorch 索引；Dockerfile 远程执行 `curl \| sh` 安装脚本；~50 依赖几乎全未固定；**提交了默认数据库/管理员口令** |
| 复现状态 | **METHOD_ONLY** — 算法逻辑独立重实现并自测；**未复现原论文数字** |
| **决策** | **STUDY_ONLY** |
| 决策理由 | 许可允许复用，但**资源约束**（不部署多服务栈）与**供应链不可控**共同否决实际集成；算法思想已被吸收进方法库。这是"资源/风险驱动"而非"质量驱动"的决策，明确记录以免被误读为否定其价值 |

---

# B. 公开科研方法

## 3. NIH iSearch Analytics — Predicted breakthroughs in biomedicine

| 字段 | 内容 |
|---|---|
| 官方地址 | https://support.analytics.nih.gov/hc/en-us/articles/16798095205531-Predicted-breakthroughs-in-biomedicine |
| 代码 | https://github.com/NIHOPA/predictivebreakthroughs |
| 类型 | 公开论文 + 可见但未授权使用的代码 |
| 许可证 | 代码 README 原文：**"Use of this software requires a license. No rights are granted beyond the view access permitted by the GitHub Terms and Conditions."** 论文（bioRxiv）未见复用许可 |
| 允许的使用方式 | **仅阅读，不可使用代码**；方法可独立重实现 |
| 核心技术 | 递归多层聚类（文章声称）；实际可核实的是 **R-MCL 单层聚类**（约 23,867 簇）+ 一个粗化簇图；轨迹特征（两年 %New、祖先 %New、熵内聚度、同期影响）；多数重叠轨迹链接器 |
| 数据依赖 | 内部引用语料（外部不可得）；figshare 快照许可未核实（短链被挑战页拦截） |
| 当前可访问性 | **官方产品页在审计期间不可用**：HTTP 403 Cloudflare *Error 1034 "Edge IP Restricted"*；https 与 Zendesk JSON API 均失败 |
| 本地运行结果 | **未运行**。算力要求：完整 CCN 约 "至少 384 GB RAM"、约 8 小时大型 EC2；最新年 R-MCL 需 "JVM 350g"。本机 32 GB，**BLOCKED**。仅轨迹特征逻辑被独立重实现并在合成数据上自测 |
| 需 GPU / 联网 / 付费 | 否 / 需（原环境）/ **需 AWS 算力**（未使用） |
| 与 MedRadar 重复度 | **中**（突破检测 vs 早期信号检测；轨迹特征高度可迁移） |
| 值得迁移的科研方法 | 轨迹特征（%New、祖先 %New、熵内聚度）；多数重叠轨迹链接 |
| 主要局限 | 标签定义不可得；引用数据不可得；代码许可阻断；算力远超本机 |
| 数据泄漏风险 | "祖先 %New"的定义极易引入未来信息（用后续快照定义当前簇的祖先）；本项目重实现时严格要求只用当时及更早快照 |
| 复现状态 | **NOT_REPRODUCED**。"递归多层聚类"这一主张**未被任何可访问材料证实**，记录为未核实，禁止在后续文档当作事实 |
| **决策** | **STUDY_ONLY** |
| 决策理由 | 三重阻断（许可、算力、数据）叠加，且核心主张无法核实。可迁移的只有轨迹特征思想，已独立实现。**产品内部机制保持 UNKNOWN** |

## 4. The Lens

| 字段 | 内容 |
|---|---|
| 官方地址 | https://www.lens.org/ ；条款 https://about.lens.org/policies/ |
| 类型 | 商业平台（附公开方法论文，Nat Biotechnol 2018, CC BY） |
| 许可证 / 条款 | **自定义专有条款**（ToU v2026.06.01）：数据使用条件"与 CC BY-NC-SA 许可证的精神一致"，强制保留 Lens ID 并署名 "Enabled by The Lens"；API 仅机构订阅、非商业；匿名用户导出 ≤ 1,000 条；禁止自动提取与批量下载 |
| 允许的使用方式 | **不可复用**。本轮**没有发出任何数据查询** |
| 核心技术 | 论文—专利关联（31.6M NPL 字符串 → 14.1M 以 match-score ≥0.9 匹配到 PubMed/Crossref）；In4M 指标 = 家族规模加权引用 / 已解决文章数 |
| 数据依赖 | 商业授权语料库 |
| 当前可访问性 | 站点可访问；条款可读 |
| 本地运行结果 | **NOT ATTEMPTED，且是刻意的**。条文明确禁止自动提取；无订阅 |
| 需 GPU / 联网 / 付费 | 否 / 是 / **是（机构订阅，未购买）** |
| 与 MedRadar 重复度 | **低**（MedRadar 无专利表、无论文表） |
| 值得迁移的科研方法 | In4M 的"家族规模加权"思路（避免只数专利而不看同族）；论文—技术时滞的测量框架 |
| 主要局限 | 数据不可得；**论文—专利时滞分布在任何可及来源中都未公开** |
| 数据泄漏风险 | 若用后续引用数作为当前特征，即典型未来信息泄漏 |
| 复现状态 | **NOT_ATTEMPTED**（合规与数据不可得） |
| **决策** | **STUDY_ONLY** |
| 决策理由 | 许可风险压倒一切。"CC BY-NC-SA-resonant" **不是** CC BY-NC-SA，是更严的自定义条款。且 MedRadar 当前**根本没有可供关联的专利或文献语料**——即便获得许可也无数据可跑 |

## 5. PTNS — 专利引用轨迹预测

| 字段 | 内容 |
|---|---|
| 官方地址 | https://www.nature.com/articles/s41598-024-75913-0 |
| 类型 | 公开论文（Scientific Reports） |
| 许可证 | **CC BY-NC-ND 4.0**（Europe PMC `license` 字段 `cc by-nc-nd`）。可读、可引用；**禁商用、禁演绎** |
| 允许的使用方式 | 阅读与引用；不可复用数据或图 |
| 核心技术 | 专利引用轨迹预测；时序网络快照；Richards 曲线拟合；模型评价（MALE/MSLE/RMSLE） |
| 数据依赖 | Incopat **商业**专利库；数据 "on request" |
| 当前可访问性 | 论文可读；**无 code availability 声明** |
| 本地运行结果 | **未运行**。无代码；数据不可得。轨迹/Richards/评价指标的逻辑被独立重实现并在合成数据上自测（56/56 PASS 的一部分） |
| 需 GPU / 联网 / 付费 | 否 / 否 / **数据需商业库** |
| 与 MedRadar 重复度 | **低**（专利轨迹 vs 监管事件） |
| 值得迁移的科研方法 | Richards 生长曲线（含不对称 nu 参数）用于技术采纳 S 曲线；MALE/RMSLE 作为计数预测指标；**跨快照的轨迹链接思想** |
| 主要局限 | 无代码、无数据、公式以图片给出；论文本身有两处内部矛盾（引言举"航空业"但语料是聚氨酯；"10+10 快照 2:1"表述不清） |
| 数据泄漏风险 | 用后续快照的引用数预测更后续 —— 必须严格只用 ≤t 的快照 |
| 复现状态 | **NOT_REPRODUCED**（代码与数据均不可得）。**未声称重现原结果** |
| **决策** | **STUDY_ONLY** |
| 决策理由 | 不可复现是客观事实，不是努力不足。可迁移的 Richards/MALE 已独立实现为通用工具，可在 MedRadar 赛道采纳曲线上试用（下一轮） |

## 6. FDA AI 医疗器械纵向研究

| 字段 | 内容 |
|---|---|
| 官方地址 | https://pmc.ncbi.nlm.nih.gov/articles/PMC13505343/ |
| 类型 | 公开论文（JMIR 系，开放获取） |
| 许可证 | 期刊开放获取条款；**底层 FDA 登记数据为美国政府公有领域** |
| 允许的使用方式 | 方法可自由独立实现 |
| 核心技术 | 历史技术赛道集中度；**HHI**；技术扩散与专业领域变化；年度增长 + 统计显著性；企业类型差异；小样本稳健性 |
| 数据依赖 | FDA AI/ML 器械授权清单（公开） |
| 当前可访问性 | 可访问 |
| 本地运行结果 | **是**。`experiments/phoenix/external/methods/hhi.py` 独立实现 + `selftest_synthetic.py` 自测 |
| 需 GPU / 联网 / 付费 | 否 / 否 / 否 |
| 与 MedRadar 重复度 | **高**（同域：器械监管数据 + 赛道 + 集中度） |
| 值得迁移的科研方法 | HHI + 有效类别数；Cochran-Armitage 趋势检验；Wilson 区间 + 设计效应修正；Bonferroni 多重比较；稀疏表卡方；置换检验；**份额基数敏感性分析** |
| 主要局限 | 论文对"份额基数"未明确说明，导致 Era 1 的 HHI 不可从公开表重算 |
| 数据泄漏风险 | 低（描述性统计，无预测目标） |
| 复现状态 | **REPRODUCED（方法层，含公式交叉验证）**：Wilson 74.49–80.30% vs 发表 74.5–80.3%；两项比例 z 检验 p=0.0011 vs P=.001；Cochran-Armitage Z=+5.300 vs +5.30；HHI Era 2/3/4 差异 ≤0.006 |
| **复现差异（如实记录）** | **Era 1 的 HHI 复现失败**：用论文自己的合并表算出 0.2234，发表值 0.181。把合并的 "Other (n=9)" 拆开后得 0.1746，接近发表值。→ **结论：发表值依赖一个论文未声明的份额基数**。这是真实发现，不是隐藏的误差 |
| **决策** | **ADOPT（仅方法）** |
| 决策理由 | 四条晋级门槛全部满足：来源与授权清楚、本地可复现、能在 MedRadar 数据上重跑、有明确研究价值。**但只采用方法，不复用其数据**。HHI 分析已作为 H6 的检验工具进入实验 |

---

# C. 商业平台对标（M7–M13）

## 通用结论（先讲共性，再逐项）

**七家全部 STUDY_ONLY，没有一家可以 ADOPT 或 ADAPT。** 原因是结构性的：

- **零开放代码、零开放数据、零公开 schema、零公开 API 文档**（7/7）。
- **0/7 公开任何预测能力的验证证据**。唯一明确宣称"forecast … accurately"的是 Clarivate，属**无依据的营销**。MedVantage、DevicePro、Joinchain **根本没有预测主张**——离原始数据越近的厂商，宣称越少。
- **1/7**（NextDevice）把"技术代际"作为标准字段，但**未公开语义**。
- **0/7** 提供逐记录 as-of 日期、覆盖起始日、或可检查的 schema。
- **0/7** 披露中英文名对应（CN↔EN）处理方式——**MedRadar 的这项难题在整个语料里没有任何行业证据可供借鉴**。
- DevicePro 自己的页面自相矛盾（12W+ vs 285W+ 产品），**直接证明厂商计数不是测量**。

**最重要的一条可迁移设计结论**（来自 A00 综合）：

> **以不可变监管标识锚定的"产品"才是原子单位；企业是对该锚点的解析归属，永远不能做主键。**
> 产品有硬键（注册证号 / 510(k) number / FDA product code），可对齐、可去重；企业只有名字，这正是七家平台共同的最弱环节。
> 推论：**把归一化规则写下来**。NextDevice 公布了自己的去重规则（同批次/同主体/同产品，覆盖单平台、多平台、省份编号差异），这是整份审计里**最可复用的资产**。规则是免费的，执行才是护城河。

这条结论直接催生了本项目的候选创新模块 RAEA（见 `docs/phoenix/INNOVATION_RAEA.md`）。

---

### 7. Clarivate DRG Medtech
- 地址：https://clarivate.com/life-sciences-healthcare/medtech/drg-medtech-competitive-intelligence/
- 类型：商业平台｜许可证：**未发布可用 ToS（`UNKNOWN`）**｜可访问性：普通 HTTP 403，仅能通过浏览器会话阅读公开页
- 数据结构：分析师分段式竞争情报；无公开 schema｜企业身份解析：`UNKNOWN`｜技术分类：`UNKNOWN`
- 溯源与证据呈现：无逐记录 as-of｜竞品比较：有（分析师维度）｜技术代际：`UNKNOWN`｜历史活动展示：`UNKNOWN`
- **预测能力：宣称 "forecast … accurately"，无任何验证证据 → 记为营销，不作为科研结果**
- 与 MedRadar 重复度：中｜可迁移：分析师分段的产品化表达（概念）
- 局限：完全闭源；条款不明使任何数据借用都不可判断｜泄漏风险：N/A（不使用其数据）
- 复现状态：NOT_APPLICABLE｜**决策：STUDY_ONLY**｜理由：无任何可复制资产，且预测主张不可验证

### 8. MedVantage
- 地址：https://medvantage.ai/｜类型：商业平台（**预发布状态**）
- 许可证：**未发布可用 ToS（`UNKNOWN`）**｜可访问性：单页，内容极少
- 全部技术维度：`UNKNOWN` / 未公开｜**无预测主张**
- 决策：**STUDY_ONLY**｜理由：产品尚未成型，无任何可审计内容

### 9. CMOP（cmoinyourpocket）
- 地址：https://www.cmoinyourpocket.com/｜类型：商业平台（自助式）｜**有公开定价**
- 许可证：完整条款 `UNKNOWN`｜可访问性：可访问
- 数据结构：**以企业/股票为锚，没有产品实体** → 无法表达技术代际与可复现份额
- 决策：**STUDY_ONLY**｜理由：anchor 选择导致它结构上做不到代际与扩散分析；这是**反面教材**，正好印证"锚在监管标识"的结论

### 10. NextDevice（医药魔方）
- 地址：**任务书给出的 `medicube.cn/product/nextdevice/index` 已失效**；实际站点为 pharmcube.com
- 类型：商业平台｜许可证：**未发布可用 ToS（`UNKNOWN`）**
- 数据结构：**以注册证号锚定产品**（正确做法）｜**公布去重/归一化规则**（同批次、同主体、同产品；覆盖单平台、多平台、省份编号差异）——**本轮最有价值的单一资产**
- 技术代际：**7 家中唯一把它作为标准字段的**，但未公开语义 → **开放赛道**
- 决策：**STUDY_ONLY**｜理由：设计最佳，但仍无数据/代码可复用；其规则文本作为**思想来源**被吸收

### 11. GBI DEVINT
- 地址：https://www.gbihealth.com.cn/products/gbi-devint｜类型：商业平台
- 许可证：`/terms` 页面**渲染不出条款正文**（`UNKNOWN`）｜可访问性：可访问
- 结构与 schema：未公开｜预测能力：无公开验证
- 决策：**STUDY_ONLY**

### 12. DevicePro（药渡）
- 地址：https://pharmacodia.com/devicepro.html｜类型：商业平台
- 许可证：**未发布可用 ToS（`UNKNOWN`）**｜可访问性：可访问
- **内部自相矛盾**：页面同时出现 "12W+" 与 "285W+" 产品数 → 厂商计数不可作为测量
- 决策：**STUDY_ONLY**

### 13. 众成医械大数据（Joinchain）
- 地址：https://www.joinchain.cn/｜类型：商业平台
- **可访问性：BLOCKED**。SPA 对 HTTP 返回空 body；浏览器内 >120 s 挂起；`ERR_BLOCKED_BY_CLIENT`；微信 CAPTCHA **未尝试绕过**
- 证据来源降级：改用厂商自己的搜狐/东方财富转载文章与交易所披露文件 → 其**3 级产品 + 4 级赛道的双分类体系**只能算"陈述级"事实，非直接观察
- 有价值之处：双分类架构是 7 家中最完整的分类体系；其**四维数据交换合规评估**是唯一经外部审视的溯源模型
- 决策：**STUDY_ONLY**｜理由：站点不可机器读取，记录 BLOCKED 而非猜测

---

## 附录：REA（工具，非 13 项清单成员）

| 字段 | 内容 |
|---|---|
| 地址 | https://github.com/morluto/rea ，npm `rea-agents` |
| 类型 | 工具（CLI + MCP 服务器），非研究对象 |
| 许可证 | **MIT**（已读 LICENSE 文件） |
| 验证版本 | **6.7.0**（精确锁定；npm 最新 6.8.0 未采用） |
| 接入结果 | **成功**。已注册为 DSH 的 MCP 服务器，**207 个工具**以 `mcp__rea__*` 形式可用；其中 2 次调用经 DSH 自身执行并返回真实 Evidence |
| 静态分析验证 | **12/14 通过**（自建无害测试件：PE 资源树、PE/CLI 元数据、P/Invoke 边界、SQLite schema+行、Rust/Go 构建元数据、归档图） |
| 不可用能力（已记录） | 原生反编译/函数/xrefs（无 Ghidra/Hopper/IDA）；`inspect_binary_layout` **仅 Linux-x64**，对任何 Windows PE 失败；`.py` 源码不支持 |
| 资源开销 | CLI 启动 1,534 ms；spawn→207 工具 2,671 ms；峰值 RSS 391 MB；磁盘 124.2 MB / 7,371 文件；**运行时零 TCP 外发**；协议成功率 17/25（68%），8 个失败全部有类型化错误，0 崩溃/超时 |
| 与 MedRadar 重复度 | 无（工具层） |
| 用途边界 | 仅用于**有实际价值且获授权**的目标。对有源码的项目优先直接审计源码（本轮全部如此）。**不把反编译当作必经步骤** |
| **决策** | **ADAPT** |
| 理由 | 来源可验证（lockfile sha512 = SLSA attestation subject，Rekor 有条目）、本地可跑、静态分析对二进制/包/SQLite 确实有用。但 207 工具的能力面远大于需要，且带未修复的 `zod` CVE 与未签名原生扩展 → **ADAPT（按需使用、哈希钉扎），不做默认依赖** |

---

## 未决问题（供下一轮）

1. SciTrends 作者是否愿意以宽松许可发布代码？（未联系）
2. NIH iSearch 的"递归多层聚类"主张是否真实？产品页恢复后可重查。
3. The Lens 是否在 2026-06 改版中调整许可制度？（细则未读全）
4. Joinchain 是否有可用的公开 API 或数据字典？（站点不可读，未得）
5. 7 家中 4 家的服务条款能否合法取得？（目前 `UNKNOWN`）
6. REA 的 `zod` CVE 在 6.8.0 是否修复？（未升级故未验证）
