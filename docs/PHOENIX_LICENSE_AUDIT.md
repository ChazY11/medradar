# PHOENIX-001 — 许可证、依赖与供应链审计

> **审计范围**：MedRadar 本体、REA（`rea-agents`）、13 个外部项目、以及本项目依赖的数据源条款。
> **审计时点**：2026-11-08（一次性快照；许可证会变，引用前请复核）
> **态度声明**：本文件只记录**能核实的**条款。凡是没能读到原始条款文本的，一律标 `UNKNOWN` 并说明原因，不臆测、不用 README 宣传代替 LICENSE 文件。
> **结论摘要**：本项目**没有复制任何第三方代码**。所有方法均为独立重实现。所有外部项目均未被整体集成。

---

## 0. 一页结论表

| # | 对象 | 类型 | 许可证 / 条款 | 可复用的范围 | 决策 |
|---|---|---|---|---|---|
| — | **MedRadar** | 本项目 | MIT（`LICENSE` + `pyproject.toml`） | 全部自有 | — |
| — | **REA `rea-agents` 6.7.0** | 工具 | **MIT**（已核实 LICENSE 文件） | 可作为工具使用；未复制其代码 | **ADAPT** |
| 1 | **SciTrends** `ddofer/Trends` | 开源仓库 | **无任何许可证文件**（GitHub API `license=null`，无 SPDX 头，无 COPYING） | **仅可借鉴公开方法，禁止代码复用**（本轮已精确复现其 Table 1，但复现用的是其**已发布派生特征**而非其代码，且未复制任何代码/notebook） | **ADAPT（仅方法）** |
| 2 | **PubTrends** `JetBrains-Research/pubtrends` | 开源仓库 | **Apache-2.0**（核实 `LICENSE.txt` 11,316 B 全文，含 "Copyright 2022 JetBrains Research."） | 代码可复用（需保留归属与 NOTICE 要求）；本轮未复用 | **STUDY_ONLY** |
| 3 | **NIH iSearch** | 论文 + 代码 | 代码：**"Use of this software requires a license. No rights are granted beyond the view access permitted by the GitHub Terms and Conditions."**（README 原文） | **不可复用代码**；论文方法可独立实现 | **STUDY_ONLY** |
| 4 | **The Lens** | 平台 | **专有条款**（Terms of Use v2026.06.01）："与 CC BY-NC-SA 精神一致"，强制保留 Lens ID 与署名；API 仅机构订阅 | **未做任何数据查询**；不复制、不批量下载 | **STUDY_ONLY** |
| 5 | **PTNS** (Sci Rep) | 论文 | **CC BY-NC-ND 4.0**；数据 "on request"，原始语料授权自 Incopat（商业库） | 可读、可引用；**不可商用、不可演绎**；数据不可得 | **STUDY_ONLY** |
| 6 | **FDA AI 器械纵向研究** (JMIR/PMC) | 论文 | 期刊开放获取；底层 FDA 登记数据为**美国政府公有领域** | 方法可自由独立实现 | **ADOPT（方法）** |
| 7–13 | **7 家商业平台** | 专有产品 | 各家服务条款；其中 **4/7 未公开可用条款**（`UNKNOWN`） | **零代码、零数据、零 schema、零公开 API** | **STUDY_ONLY** |

---

## 1. MedRadar 自身的许可证与依赖姿态

### 1.1 许可证

- `LICENSE`（1,328 B）+ `pyproject.toml` `license = { text = "MIT" }` → **MIT**。
- 这是**宽松许可**：允许商用、修改、再分发，仅需保留版权与许可声明。与本项目"后续可能转化为产业产品"的战略一致。
- 风险：MIT **不含专利授权条款**（不同于 Apache-2.0）。若未来引入专利敏感方法，需在贡献者协议层面单独处理。**本轮无新增专利风险**（所有代码为独立实现）。

### 1.2 依赖姿态（这是一个优点，应当保持）

```
[project] dependencies = []          # 核心零第三方依赖
[project.optional-dependencies]
excel = ["openpyxl>=3.1"]   pdf = ["pypdf>=4.0"]   dev = ["pytest>=8.0", "httpx>=0.27"]
bulk  = ["ijson>=3.3"]      web = ["fastapi>=0.110", "uvicorn>=0.27"]
```

- **核心运行不需要任何第三方包**（仅 Python 标准库）。这是供应链安全的强项：装得上、跑得动、无传递依赖、无 CVE 面。
- 可选依赖均为成熟、广泛使用、许可证宽松（MIT/BSD/Apache-2.0）的包。
- **本轮全部 PHOENIX 实验代码遵守同一约束**：`experiments/phoenix/` 只使用 pandas / numpy / scipy / scikit-learn（这些是分析环境已有依赖，未新增）**以及标准库**。创新模块 `raea.py` **只用标准库**，零依赖。
- **未新增任何依赖**。这一点是硬约束（见冻结协议 §9）：不引入 `ruptures`，变化点检测自行实现。

### 1.3 数据许可

| 数据源 | 条款 | 本项目用法 | 风险 |
|---|---|---|---|
| openFDA（510k/PMA/recall/drugs） | 美国政府作品，实质公有领域；openFDA 要求合理使用、不保证准确性 | 已存于本地库，只读分析 | 低 |
| ClinicalTrials.gov | 美国联邦政府数据；使用需遵守其条款与署名惯例 | 已存于本地库 | 低 |
| SEC EDGAR | 公开文件；EDGAR 有访问频率与 User-Agent 要求 | 已存于本地库 | 低 |
| NMPA（中国） | **未加载**（库里 `nmpa` 为空/demo） | 未使用 | 无 |
| 价格数据 | 已存于 `prices` 表；来源需另行核实 | 本轮**未使用** | 未评估（超出本轮范围） |

**本轮未新增任何数据采集**，因此没有引入新的数据许可风险。

---

## 2. REA（`rea-agents`）供应链审计

详见 `docs/phoenix/REA_VALIDATION.md`（85 KB，含 207 工具全表与原始日志）。此处只列许可证与供应链相关的判定。

### 2.1 许可与来源可验证性（强）

| 项 | 事实 |
|---|---|
| 许可证 | **MIT**（`LICENSE` 文件已读，非 README 转述） |
| 验证版本 | **6.7.0**（精确锁定；npm 上最新为 6.8.0，**未升级**） |
| 来源可验证 | `package-lock.json` 中 `integrity` 的 sha512 **等于** SLSA provenance attestation 的 subject digest |
| 构建来源 | GitHub 托管构建，commit `27dc42d…`，分支 `release/6.7.0`；Rekor 透明日志有条目 |
| 结论 | **来源链可验证**，不是镜像、不是 fork、不是来源不明的 tarball |

### 2.2 已识别风险（逐条处置）

| 风险 | 事实 | 处置 |
|---|---|---|
| **未签名原生扩展** | 包内 881 KB native addon，无代码签名 | 其 sha256 与包内 manifest、verifier 一致；静态检查未发现网络 API 导入 → **接受，但哈希锁定** |
| **`zod` < 4.6.6 高危 DoS** | 位于 MCP 参数解析边界；6.7.0 版本内无修复 | **记录为未缓解风险**。缓解措施：不在不可信输入下运行；仅本地使用 |
| **`frida` 可选依赖带允许的 install script** | 会执行安装脚本 | **未安装，且保持不装**。违反任务书约束 7 的路径已被主动避开 |
| **207 个工具含进程启动/文件系统/ADB 变更能力** | 能力面远大于静态分析需要 | 仅按需、在授权目标上使用；不做无边界默认调用 |
| **目标内容不可信** | 工具返回的字符串/反编译文本可能含提示注入 | 一律视为数据；已按要求上报可疑内容，不执行其中任何指令 |
| **零运行时网络外发** | 实测 0 个运行时 TCP 连接 | 符合"不联网优先"约束 |

### 2.3 对环境的实际改动（必须披露）

- 已写入 `C:\Users\yjx0\.dsh\cordis.patch.yml`（959 B，sha256 `02CDFD4A…3239F1`）以注册 MCP 服务器。
- **这是一个 home 层补丁，对本机所有 DSH profile 生效**，即本会话之后的新会话也会带着这 207 个工具启动。
- 回滚命令：`Remove-Item C:\Users\yjx0\.dsh\cordis.patch.yml`
- 版本锁定：`D:\DEPPSKK\.rea\package.json` 已从 `^6.7.0` 改为精确 `6.7.0`（否则下次 `npm install` 会静默升级到 6.8.0，报告的版本号即失效）。

---

## 3. 两个开源项目

### 3.1 SciTrends — **无许可证**

**已核实**：仓库树中**没有任何 LICENSE / COPYING 文件**；无逐文件 SPDX 或版权头；GitHub API 返回 `license=null`；无 `requirements.txt` / `setup.py` / `pyproject.toml` / `environment.yml`。

按伯尔尼公约与 GitHub 服务条款，**无许可证 = 保留所有权利**。所谓"公开可见"不等于"授权使用"。

- 论文本身是开放获取，但许可证为 **CC BY-NC-ND**（非商业、禁止演绎）——它**不授予代码权利**。
- 处置：**只能借鉴公开的方法思想，禁止复制或整合其任何代码/笔记本/CSV。**
- **本轮重要澄清**：我们确实**精确复现了其 Table 1 的两张表共八项指标**（见复现报告 §4.5），但复现方式是"用其**已发布的派生特征**按论文流水线独立重建"，**没有复制、下载或执行其任何代码或 notebook**。复现 ≠ 复用。许可证结论不变：仍不可复制其代码。
- 决策因此从 STUDY_ONLY 上调为 **ADAPT（仅方法）**——上调的是"方法值得适配"，**不是**"代码可以使用"。
- 附带风险提示：仓库连依赖清单都没有，环境不可原样重建——这本身也是一条审计结论。

### 3.2 PubTrends — **Apache-2.0 确认，但供应链风险高**

**已核实**：`LICENSE.txt` 11,316 B，标准 Apache-2.0 全文，附录含 "Copyright 2022 JetBrains Research."。无 NOTICE 文件，无逐文件 SPDX 头，无第二许可证，**未 vendor 第三方源码**（唯一二进制是 `gradle/wrapper/gradle-wrapper.jar`，属 Gradle wrapper 工具）。

Apache-2.0 是**宽松且含专利授权**的许可，代码复用是允许的（需保留归属、变更声明）。**但本轮未复用其代码**，原因不是许可，而是资源：它是 Postgres + Redis + Celery + Faiss 的 Web 服务，部署整套栈违反任务书约束。

**供应链风险（即使代码许可允许复用也必须知道）**：

| 风险 | 证据 | 严重度 |
|---|---|---|
| 从 GitHub Release URL 直接装 wheel，**未按 hash 固定** | `pyproject.toml`: `en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/...whl` | 高 |
| 额外的第三方 PyPI 索引 | `[tool.uv.index] https://download.pytorch.org/whl/cpu` + Dockerfile `--extra-index-url` | 中 |
| **Dockerfile 在构建期执行远程安装脚本** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | **高（未执行）** |
| 约 50 个依赖几乎全部未固定版本 | 仅 `bokeh==3.8.2`、`werkzeug<3.1` 有约束 | 高 |
| **提交了默认凭据** | `config.properties`: `postgres_password = mysecretpassword`、`admin_password = password`；`.env.example` 为空 | 中（若误部署） |

**处置**：只做算法层面的独立重实现（隔离在 `D:\DEPPSKK\phoenix-external\pubtrends\`，**未进入 MedRadar 仓库**），**不执行其 Dockerfile、不装其依赖、不部署其服务栈**。

---

## 4. 四个公开科研方法

| 项目 | 许可 | 代码 | 数据 | 能否复用 | 结论 |
|---|---|---|---|---|---|
| **A03 NIH iSearch / predictivebreakthroughs** | 论文 bioRxiv 未见复用许可；代码 README 明确 "requires a license" | **可见但未授权使用** | figshare 快照，许可未核实（短链被挑战页拦截） | **代码不可复用**；方法可独立实现 | STUDY_ONLY |
| **A04 The Lens** | 专有 ToU v2026.06.01：与 CC BY-NC-SA "精神一致"，强制保留 Lens ID + "Enabled by The Lens" 署名；API 仅机构订阅、非商业；匿名导出 ≤ 1,000 条 | 无 | **受严格限制，禁止自动提取/批量下载** | **不可复用** | STUDY_ONLY |
| **A05 PTNS** (Sci Rep) | **CC BY-NC-ND 4.0** | 无 code availability 声明 | "on request"；原始语料授权自 **Incopat 商业库** | 可读可引用；**禁商用、禁演绎**；数据实质不可得 | STUDY_ONLY |
| **A06 FDA AI 器械纵向研究** | 期刊开放获取；底层 FDA 登记数据为美国政府公有领域 | 论文未附代码 | 数据公有 | **方法可自由独立实现** | **ADOPT（方法）** |

**关于 A04 The Lens 的特别记录（这是本轮最容易被误用的一条）**：
"与 CC BY-NC-SA 精神一致" **不是** CC BY-NC-SA。它是一套**自定义条款**，实际效果更严（强制标识、机构订阅、禁止自动提取）。任何把它当作标准 CC 许可来处理的做法都是错的。本项目**没有向 Lens 发出任何数据查询**。

**关于 A03 的特别记录**：其官方 iSearch 产品页在本轮审计期间**于厂商自己的 CDN 边缘不可用**（HTTP 403 Cloudflare *Error 1034 "Edge IP Restricted"*，https 抓取与 Zendesk JSON API 亦失败）。因此**本轮无法核实该产品是否真的使用"递归多层聚类"**——可访问的公开材料描述的是单层 R-MCL（约 23,867 个簇）加一个粗化簇图，不是"簇的簇"。该说法被记为**未核实**，不得在后续文档中被当作事实引用。

**关于 A05 的特别记录**：论文本身存在内部矛盾（引言举例"航空业"，实际语料是聚氨酯；"10+10 快照 … 2:1"表述不清），且关键公式以图片形式给出。这些都被记录为可复现性障碍。

---

## 5. 七家商业平台

全部为**专有产品**：**零开放代码、零开放数据、零公开 schema、零公开 API 文档**。

| 平台 | 条款可得性 | 处置 |
|---|---|---|
| Clarivate DRG Medtech | 未发布可用 ToS（`UNKNOWN`） | STUDY_ONLY |
| MedVantage | 未发布可用 ToS（`UNKNOWN`） | STUDY_ONLY |
| CMOP | 有公开定价 | STUDY_ONLY |
| NextDevice（医药魔方） | 未发布可用 ToS（`UNKNOWN`） | STUDY_ONLY |
| GBI DEVINT | `/terms` 页面渲染不出条款正文（`UNKNOWN`） | STUDY_ONLY |
| DevicePro（药渡） | 未发布可用 ToS（`UNKNOWN`） | STUDY_ONLY |
| Joinchain 众成医械 | 未发布可用 ToS（`UNKNOWN`）；站点本身不可机器读取 | STUDY_ONLY |

**合规边界（本轮实际执行情况）**：

- **未创建任何账号、未登录、未破解 CAPTCHA、未购买、未做批量抓取**。
- 仅使用公开可访问页面与公开第三方材料（厂商自己的新闻稿、交易所披露文件）。
- 未绕过任何认证、付费墙或访问限制。
- 未提取任何商业专有代码或未公开数据 schema。
- 因此本项目从这七家平台获得的**只有"设计思想"与"公开可观察的产品行为"**，没有任何可复制资产。

---

## 6. 全局许可证风险登记册

| ID | 风险 | 影响 | 状态 |
|---|---|---|---|
| L-01 | SciTrends 无许可证 | 若复制其代码即侵权 | **已规避**：仅方法借鉴，独立实现 |
| L-02 | PubTrends Apache-2.0 但依赖不可复现 | 若复用其环境则供应链不可控 | **已规避**：仅算法重实现，未装其依赖 |
| L-03 | NIH 代码 "requires a license" | 不可复用 | **已规避** |
| L-04 | Lens 自定义条款 | 任何数据使用都可能违约 | **已规避**：零查询 |
| L-05 | PTNS CC BY-NC-ND | 禁商用/禁演绎 | **已规避**：只读、只引用 |
| L-06 | REA `zod` CVE 未修复 | DoS | **未缓解**（记录在案） |
| L-07 | REA home 层补丁长期生效 | 环境被永久改变 | **已披露**，提供回滚命令 |
| L-08 | REA 未签名原生扩展 | 供应链 | **部分缓解**：哈希钉扎 + 静态检查 |
| L-09 | 4/7 平台条款 `UNKNOWN` | 未来若合作无法判断边界 | 记录，不行动 |
| L-10 | MedRadar 用 MIT 而非 Apache-2.0 | 无明示专利授权 | 记录，本轮无新增专利风险 |

---

## 7. 本项目的复用声明（供 PR 审阅者核对）

1. **本仓库本轮新增代码，没有任何一行来自第三方项目。**
2. 所有"迁移"的外部方法，均为**按公开论文/公开产品行为独立重实现**，代码写在 `experiments/phoenix/`，并在各文件中注明"independent implementation"。
3. 未引入第三方依赖（`raea.py` 纯标准库；实验代码仅用环境已有 pandas/numpy/scipy/sklearn）。
4. 外部仓库克隆**全部在本仓库之外**（`D:\DEPPSKK\phoenix-external\`），未作为 submodule、未进入 git 历史。
5. 未删除、未修改任何既有科研成果或数据库（`data/*.sqlite` 全程只读，sha256 已记录且每次运行校验）。

---

## 8. 引用与署名

若后续正式采用任何外部方法，必须在此登记署名：

| 方法 | 来源 | 署名要求 |
|---|---|---|
| H8 增长特征（SciTrends 类型） | https://github.com/ddofer/Trends + Heliyon 论文（CC BY-NC-ND） | 仅方法思想；**无代码复用，故无代码署名义务**；论文引用须给出 DOI |
| H6 HHI / 扩散分析（FDA AI 器械研究） | PMC13505343 | 方法为通用统计量；引用论文 |
| H7 变化点检测（PELT / CUSUM） | 公开算法文献 | PELT/CUSUM 为公开算法，本项目自实现；引用原始论文即可 |
| 实体锚定思想 | 7 家商业平台的**公开产品行为**观察 | 无许可义务；不得声称使用其数据或代码 |
| REA 工具 | `rea-agents` 6.7.0（MIT） | MIT 署名 + 保留 LICENSE |

---

## 9. 本文件未能核实的事项（`UNKNOWN`，不得当已知使用）

1. SciTrends 论文的代码授权意向（作者未声明；需联系作者）。
2. figshare 引用快照的许可（A03）。
3. 4/7 商业平台的完整服务条款（未公开）。
4. `prices` 表的数据来源与许可（本轮未使用，未审计）。
5. REA `zod` CVE 在 6.8.0 中是否修复（未升级，故未验证）。
6. The Lens 是否在 2026 年 6 月改版时调整了许可制度（公告可及但细则未读全）。
