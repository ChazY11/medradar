# 使用许可、认证与成本审计（DATA-EXPANSION-001）

**逐源原始记录：** [`GLOBAL_DATA_SOURCE_REGISTER.json`](GLOBAL_DATA_SOURCE_REGISTER.json) 的
`licence` / `redistribution_allowed` / `authentication` / `free_tier` / `rate_limits` / `cost_notes` 字段
**审计时点：** 2026-11-09（一次性快照；条款会变，引用前请复核）
**态度声明：** 只记录**读到原文**的条款。没读到原始条款文本的，一律 `UNKNOWN` 并说明原因。
不用 README 宣传代替许可条款，不用价格页猜测最终报价。

> **本轮的事实基线：没有付费、没有注册、没有使用任何凭据、没有绕过任何访问控制。**
> 所有 `PAID_ONLY` / `REQUIRES_REGISTRATION` 结论都来自**未授权状态下收到的拒绝响应 + 官方条款页**。

---

## 0. 一页结论

| 许可姿态 | 来源数 | 说明 |
|---|---|---|
| 公有领域 / 开放许可，**允许再分发** | **16** | 美国联邦政府作品为主（openFDA、GUDID、USAspending、CT.gov、NIH、HMRC 统计、Eurostat、Data.gov 系） |
| 免费可用但**再分发受限**（`PARTIAL`） | **13** | 学术聚合器（OpenAlex 除外）、欧委会部分数据、PubMed/NLM、Semantic Scholar、Comtrade |
| 完全开放（CC0）且允许再分发 | **2** | `openalex`（CC0 1.0）、`openfda_*`（FDA 明确公有领域奉献） |
| **再分发受限且不明确**（`UNKNOWN`） | **3** | `greenhouse`、`lever`、`china_ccgp` —— 平台公开但内容归属不明确 |
| 需注册（免费） | **9** | 见 §3 |
| 需商业授权 | **4** | 见 §4 |
| 无公开数据可授权 | **1** | `uk_mhra_device`（英国没有公开产品注册库） |

**一句话：本轮没有任何来源需要付费就能拿到已验证的数据；但"免费"不等于"可再分发"。**

---

## 1. 再分发矩阵（决定能不能进 Git / 能不能对外发布）

| `redistribution_allowed` | 含义 | 数量 | 对本项目的操作含义 |
|---|---|---|---|
| `YES` | 可再分发（通常需署名） | 19 | 样本切片可以进 Git（仍受体积上限约束） |
| `PARTIAL` | 可作科研使用，再分发受限或需逐条看 | 17 | **只提交极小切片 + 哈希 + 获取脚本**，不提交批量数据 |
| `NO` | 禁止再分发 | 6 | **不提交任何内容**；只提交 URL、字段名与哈希 |
| `UNKNOWN` | 未读到条款 | 15 | 按 `NO` 处理，直到读到原文 |

**默认策略（本仓库已执行）：**
- `samples/` 里只放**单个响应切片**，单文件 ≤512KB，超出的截断并记录 `sha256_full`；
- 大规模原始数据**不进 Git**（见 `.gitignore` 的 staging 条目）；
- 每个样本在 `SAMPLES.json` 里带 `request_url` 与哈希，使复核者可以**自己重新取一次**而不是依赖我们的副本。

---

## 2. 需要署名的来源（若将来对外发布结果）

| 来源 | 要求的署名/条件 | 依据 |
|---|---|---|
| `canada_mdall` | Open Government Licence – Canada：需注明来源 | register `licence` 字段 |
| `eurostat_comext` | Eurostat 再利用政策：免费 + 署名 | register |
| `eu_cordis` | CC-BY 4.0：署名 | register |
| `uk_find_a_tender` | Open Government Licence v3.0 | register |
| `openalex` | CC0（无强制署名，但建议注明） | 其 terms 页 |
| `openaire` | CC-BY 4.0 | register |
| `europepmc` / `pubmed_eutils` | NLM 条款：摘要可复用需署名，部分记录受限 | register |
| `un_comtrade` | 非商业使用 + 署名；批量再分发受限 | register |
| `crossref` | 每条记录自带 `license[]`，必须逐条尊重 | register |
| `uk_hmrc_trade` | 推定 OGL v3.0（未逐字核实，标 `PARTIAL`） | register |

**注意 `crossref` 的特殊性：** 它不是单一许可——**每条记录**都带自己的 `license[]`，
再分发必须以记录级许可为准。这是本轮唯一一个"许可粒度细于数据集"的来源。

---

## 3. 需注册（免费）——本轮刻意未做

| 来源 | 注册要求 | 解锁什么 | 预计成本 |
|---|---|---|---|
| `uspto_open_data_portal` | 免费 `X-API-KEY` | 美国专利申请/公开检索 | 0 元 + 一次注册 |
| `epo_ops` | 免费 OAuth2（consumer key/secret） | 专利公开日 + 族 + 引用 | 0 元 + 一次注册 |
| `us_census_trade` | 免费 key | 美国进出口 HS 统计 | 0 元 |
| `sam_gov` | 免费 key | 美国联邦招标机会 | 0 元 |
| `brazil_anvisa` | ANVISA 账号 | 巴西器械注册 | 0 元（条款未读） |
| `eudamed` | 官方 EUDAMED 数据 API 凭据 | 欧盟 Basic UDI-DI / 器械/证书 | 0 元（配额未知） |
| `eu_ted`（批量） | 免费 API key（搜索 API 匿名可用） | 批量公告 XML | 0 元 |
| `google_patents_bigquery` | GCP 项目 + OAuth（首 1TB/月免费） | Google Patents 公共数据集 | 0 元起，超出按量 |
| `wipo_patentscope` | 注册制 Web Services | PCT 数据 | 未核实 |

**为什么本轮一个都没注册：** 创建账号/申请凭据属于**需要项目负责人授权的行为**，
不是数据科学家可以自行决定的动作。任务书也把"使用未经授权的凭据"列为禁止项。
**这 9 个是本轮最便宜的解锁点，等待决策，不需要预算。**

---

## 4. 商业授权（需采购决策）

| 来源 | 公开价格信息（2026-11-09 抓取） | 字段能力 | 采购前必须验证 |
|---|---|---|---|
| `importgenius` | **$229/月起**（年付 $183/月） | 企业级提单：进口商/出口商/发货日/HS/描述/港口 | 五家企业的实际覆盖；描述字段质量；历史深度 |
| `panjiva`（S&P Global） | 无公开价，议价 | 同上 + 供应链图谱 | 同上；合约是否允许科研发表 |
| `descartes_datamyne` | 报价制 | 同上 | 同上 |
| `lens_org` | 机构订阅，价格不公开 | 论文—专利关联（31.6M NPL → 14.1M 匹配） | 是否允许科研二次分发；是否有 API 配额 |

**采购的原则性提醒：**
1. **先用免费替代验证需求是否真实存在。** 本轮的 C3 已证明：即使拿到更早的监管足迹，
   **产品身份匹配才是瓶颈**。在买提单数据之前，先确认我们能解决产品身份问题，
   否则买来的数据同样无法与器械连接。
2. **要求试用样本。** 4 个商业来源全部无法在付费前验证字段质量——这是它们按评分规则落到
   `REJECT` 的真实原因（未验证能力维度记 0 分），而不是已知的无用。
3. **`importgenius` 是唯一有公开价格的**，因此也是唯一可以现在就算清预算的：
   $229/月 × 12 = **$2,748/年**（年付 $2,196/年）。这笔钱应当由"能否解决产品身份"来决定，
   而不是由"海关数据听起来有用"来决定。

---

## 5. 被禁止或不可用的路径（明确记录）

| 来源 | 阻断性质 | 本轮的处置 |
|---|---|---|
| `china_nmpa_device` | HTTP 412 + JS 反爬挑战 | 记为 `BLOCKED_BY_POLICY`；**未尝试求解** |
| `china_nmpa_udi` | JSP/JS 外壳，无公开接口 | `UNAVAILABLE` |
| `australia_tga_artg` | 自动化请求被拒 | `BLOCKED_BY_POLICY`；未绕过 |
| `china_customs_stats` | 全路径 412 | `UNAVAILABLE` |
| `importyeti` | robots.txt 明确 `Disallow /search?q` 与 JSON API | `BLOCKED_BY_POLICY`；**一个数据请求都没发** |
| `usitc_dataweb` | 纯 SPA + 站点 403 | `UNAVAILABLE` |
| `uk_mhra_device` | 制度上不存在公开产品注册库 | `UNAVAILABLE`；不是技术问题 |
| `workday_phenom` | 无厂商中立 API；`jobs.medtronic.com` 证书主机名不匹配 | `UNAVAILABLE`；**未关闭 TLS 校验** |

**这些都不构成"再努力一点就能拿到"。** 绕过它们会违反任务书的明确禁令。

---

## 6. 长期维护成本（许可之外的隐性成本）

| 成本类型 | 来源 | 说明 |
|---|---|---|
| **解析器会坏** | `fda_device_shortages`、`fda_import_alerts`、`china_ccgp`、`eu_cordis` | HTML/无文档端点；必须"解析失败即报警"，不得用空结果冒充无数据 |
| **限流会变** | `semantic_scholar`（匿名 429）、`openfda`（无 key 1000/日） | 需要退避与预算；本轮客户端已内置 |
| **配额会变** | `epo_ops`（体积计量）、`google_patents_bigquery`（1TB/月） | 注册后需监控用量 |
| **条款会变** | `lens_org`、`crossref`（记录级许可） | 每轮复核，不缓存旧结论 |
| **依赖第三方重构** | `eu_cordis`、`china_ccgp` | 页面一改即失效 |

**结论：** 21 个 `VERIFIED_*` 来源里，**4 个应视为"随时会坏"**（全部是 `VERIFIED_PUBLIC_QUERY`）。
路线图把这 4 个都放在 `PILOT` 或 `RESEARCH ONLY`，没有一个进入 `ADOPT NOW`。

---

## 7. 本项目的许可姿态（不变）

- MedRadar 本体是 **MIT**（`LICENSE` + `pyproject.toml`）。MIT **不含专利授权条款**，
  若将来引入专利敏感方法需单独处理。
- **核心零第三方依赖**（仅标准库）。本轮**未新增任何依赖**：
  所有连接器只用标准库 + 仓库既有的 `medradar.external_sources` 基础设施。
- 本轮**没有复制任何第三方代码**；所有连接器为独立实现。
- 本轮新增的数据资产全部是"外部证据的极小切片 + 哈希 + 可重放脚本"，
  不改变仓库的许可姿态。
