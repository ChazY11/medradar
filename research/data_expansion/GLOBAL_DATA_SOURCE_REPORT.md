# 全球医疗技术数据源调查报告（DATA-EXPANSION-001）

**核查时点：** 2026-11-09（一次性快照；接口与条款会变，引用前请复核）
**机读注册表：** [`GLOBAL_DATA_SOURCE_REGISTER.json`](GLOBAL_DATA_SOURCE_REGISTER.json)
**逐请求证据：** [`ACCESS_VERIFICATION.json`](ACCESS_VERIFICATION.json) + `probes/<source_id>/requests.jsonl`
**实验规则（结果前冻结）：** [`EXPERIMENT_DESIGN.md`](EXPERIMENT_DESIGN.md)

> **本报告的写法约束。** 每个"已验证"都对应 `probes/` 下可重放的请求与被截断保存的真实响应；
> 每个"不可用"都对应一条失败请求或一份明确的条款原文。**没有任何一行来自记忆、推测或二手转述。**
> 无法核实的字段一律写 `UNKNOWN`。

---

## 0. 一句话结论

在 59 个候选来源中，**31 个在无注册、无付费、无绕过访问控制的前提下返回了真实记录**（25 个官方 API、
2 个官方批量下载、4 个可解析的公开查询页）；**9 个需要免费注册即可解锁**；
**4 个只能商业采购**；**12 个在当前条件下不可用**（其中 2 个被反自动化机制主动阻断）。

但**"能拿到"与"对 MedRadar 科学问题有用"是两件事**。本轮最重要的负面发现是：
**专利数据在无账号条件下获得量为 0 条**，而专利是 MedRadar 现有能力中最大的缺口。

---

## 1. 判定口径

| 状态 | 含义 | 本轮的证据要求 |
|---|---|---|
| `VERIFIED_API` | 官方机器接口返回真实记录 | ≥1 次 2xx + 真实记录结构 + 请求日志 |
| `VERIFIED_BULK_DOWNLOAD` | 官方批量文件可下载并可解析 | 下载清单/文件头可解析，未下载超大文件 |
| `VERIFIED_PUBLIC_QUERY` | 公开查询页返回结构化真实记录 | 解析出 ≥1 条真实条目 + 字段可辨 |
| `REQUIRES_REGISTRATION` | 真实访问存在但需账号/key | 无凭据时收到 401/403/429 且文档确认需凭据 |
| `PAID_ONLY` | 仅商业授权 | 官方条款/定价页原文 |
| `BLOCKED_BY_POLICY` | 技术可行但被明示禁止或被主动阻断 | robots/条款原文，或反自动化挑战的实测响应 |
| `UNAVAILABLE` | 未找到可用的程序化访问 | 多路径探测失败记录 |
| `NOT_TESTED` | 未测 | — |

**浏览器能打开 ≠ 程序能批量采集。** 本轮所有 `VERIFIED_*` 都是程序请求的结果；
反过来，`UNAVAILABLE` 只代表"本轮没找到合法程序化路径"，不代表该机构没有内部数据。

---

## 2. A · 全球医疗器械监管与 UDI

| 来源 | 国家/地区 | 状态 | 关键判断 |
|---|---|---|---|
| `openfda_device_510k` | US | `VERIFIED_API` | 真实记录；`decision_date` 是**决定日，不是首次公开日**——FDA 不提供每条的首次公开时间戳 |
| `openfda_device_pma` | US | `VERIFIED_API` | PMA 补充件是独立记录（`pma_number`+`supplement_number`）；把补充件当"新批准"会把 PMA 活动放大约 39 倍（PHOENIX-003 F1 已实证） |
| `openfda_device_classification` | US | `VERIFIED_API` | ~7000 个产品代码字典，是 510(k)/PMA → 器械族的**连接键**，可全量拉取（≤8 页） |
| `openfda_device_registrationlisting` | US | `VERIFIED_API` | **机构级**（谁可以分销什么），不是产品级；适合做注册人背书，不能当产品目录 |
| `openfda_bulk_download` | US | `VERIFIED_BULK_DOWNLOAD` | `download.json` 是官方导出清单，带 `export_date`——这是**真正的快照时钟**，API 本身没有 |
| `accessgudid` | US | `VERIFIED_API` | NLM 的 `/api/v3/devices/lookup?di=` 返回 GUDID 原始记录；**GUDID 是上游，openFDA `/device/udi` 是其再发布**，同一 DI 只能算一条证据 |
| `fda_gudid_download` | US | `VERIFIED_BULK_DOWNLOAD` | 日/周/月增量与全量发布文件；日文件小到可在预算内下载，带发布日期 |
| `canada_mdall` | CA | `VERIFIED_API` | **本轮最大的监管类意外收获**：Health Canada 提供无需 key 的 JSON/XML API（company / licence / device / deviceidentifier 四类端点） |
| `eudamed` | EU | `REQUIRES_REGISTRATION` | 公共 SPA 可打开，但所有公共数据端点返回 **HTTP 429 + 明确要求使用官方 EUDAMED 数据 API**（需注册）。不是"没有数据"，是"有数据但没有匿名通道" |
| `china_nmpa_device` | CN | `BLOCKED_BY_POLICY` | HTTP 412 + 动态 `<meta>` token 的 JS 反爬挑战。**未尝试求解，也不应求解** |
| `china_nmpa_udi` | CN | `UNAVAILABLE` | JSP/JS 外壳，数据调用 session 绑定且无文档；未找到公开机器接口 |
| `australia_tga_artg` | AU | `BLOCKED_BY_POLICY` | 见该源 NOTES（本轮以反自动化阻断处理，未绕过） |
| `uk_mhra_device` | UK | `UNAVAILABLE` | GOV.UK 只有**注册指南**，英国**没有公开的持证产品注册库**可查。这是制度性缺失，不是技术问题 |
| `japan_pmda` | JP | `UNAVAILABLE` | PMDA 器械库是 legacy servlet，只响应表单 POST，GET 一律返回空表单 |
| `brazil_anvisa` | BR | `REQUIRES_REGISTRATION` | Angular SPA，JSON 接口需 ANVISA 登录流程签发的 bearer token |
| `korea_mfds` | KR | `NOT_TESTED` | 优先级 P3，未测 |

**跨国产品身份：能做到什么程度。**
唯一真正**全球可用**的产品锚是 **UDI-DI**：GUDID（美国）直接给 DI；MDALL 给 licence + device identifier
并可与制造商名联合匹配；openFDA 全系可按 DI 或 510(k)/PMA 号交叉引用。
**EUDAMED 的 Basic UDI-DI 本应是把这三者缝合起来的关键**，但它匿名不可得。
因此在当前条件下：**美国 → 加拿大**可做确定性关联（DI + 制造商 + 型号）；
**欧盟**只能停留在"产品名 + 制造商"的多字段候选层，除非获得 EUDAMED 访问。
这是本轮对"跨国一致产品身份"最诚实的回答。

---

## 3. B · 全球专利数据（本轮最重要的负面结果）

| 来源 | 状态 | 实际结果 |
|---|---|---|
| `epo_ops` | `REQUIRES_REGISTRATION` | 两个 REST 端点 403 `Fair Use policy`，token 端点 401。免费注册（OAuth2） |
| `uspto_open_data_portal` | `REQUIRES_REGISTRATION` | 401 `Unauthorized`，需免费 `X-API-KEY` |
| `patentsview` | `UNAVAILABLE` | **已退役**：`search.patentsview.org` 双解析器 NXDOMAIN；`api.patentsview.org/patents/query` 返回 200 但内容是 ODP 品牌 SPA 外壳 |
| `uspto_patent_bulk` | `REQUIRES_REGISTRATION` | `bulkdata.uspto.gov` 不再解析；仅存 keyed ODP dataset API，下载 0 字节 |
| `wipo_patentscope` | `REQUIRES_REGISTRATION` | 无开放 API（JSF UI）；PCT 数据产品走订阅 |
| `google_patents_bigquery` | `REQUIRES_REGISTRATION` | 匿名 401；需 GCP 项目 + OAuth（首 1TB/月免费，超出计费） |
| `lens_org` | `PAID_ONLY` | 条款原文只提供机构订阅；无 token 401 |

**结论：在"无账号、无付费"的前提下，本轮获得的专利记录数是 0。**
不是"少量"，不是"降级"，是零。因此**本轮没有、也不可能**做出任何专利相关的证据增量结论。

这不是坏消息的全部：它把下一轮的成本问题变清楚了。两个**免费**账号就能打开专利通道：
USPTO ODP key（美国申请/公开检索）与 EPO OPS app（公开日 + 专利族 + 引用）。
按本轮实测，这两个是性价比最高的注册动作，但**注册账号属于需要项目负责人授权的行为，本轮未做**。

**时间语义警告（即使将来拿到数据也必须遵守）**：专利的申请日/优先权日**不是**公众可见日；
公开日通常在申请后 18 个月。把未公开的申请当作"当时已可观察的早期信号"，是本项目明令禁止的错误。

---

## 4. C · 科研论文与学术关系

| 来源 | 状态 | 关键判断 |
|---|---|---|
| `openalex` | `VERIFIED_API` | 覆盖最大，带 ROR 机构与 DOI；`created_date` 是**元数据录入时钟**（样本中曾晚于 `publication_date` 数年），绝不可当公开时钟 |
| `crossref` | `VERIFIED_API` | **资助方元数据最强**：`funder[].award[]` 可做论文↔资助↔企业的确定性连接；`deposited` 同样是录入时钟 |
| `europepmc` | `VERIFIED_API` | `firstPublicationDate` 与 `firstIndexDate` **同时暴露**，是本轮时间语义最干净的文献源 |
| `pubmed_eutils` | `VERIFIED_API` | 检索稳；但 `esummary` **既无机构也无 funder id** → 单靠 PubMed 永远无法把论文归因到企业 |
| `semantic_scholar` | `VERIFIED_API` | DOI 查询 200；匿名 `/paper/search` 两次 429 → 检索通道受限，仅可做补充 |
| `openaire` | `VERIFIED_API` | Graph v1 与 legacy 均可用，作为欧盟视角补充 |

**去重是硬指标，不是整洁度问题。** 实测：同一 DOI 在四个来源原生查询 → 4 条记录 → **1 篇唯一论文（重复率 75%）**。
如果不做跨源去重，任何"论文证据数量"都会被高估最多 4 倍。
同时，在**企业级检索**上四个引擎的结果集重叠仅 0–9%（Medtronic 0%，Mindray 9%）——
即**去重后多源仍然增加召回**。这两个结论同时成立，必须一起报告。

**企业归因的来源分工**（本轮实测）：
Crossref 的 funder 元数据最强（"Medtronic" 检索前 25 条中 21 条由 Medtronic 资助）；
OpenAlex 的 ROR `company` 机构可做作者机构归因；Europe PMC 的 `grantsList` 可补资助；
PubMed 不能单独归因。**这三者证据强度不同，不得混算成一个"命中数"。**

---

## 5. D · 临床试验

| 来源 | 状态 | 关键判断 |
|---|---|---|
| `clinicaltrials_gov` | `VERIFIED_API` | v2 API 免 key；`studyFirstPostDate` 是**首次登记公开日**，`startDate` 常被回填，不可混用 |
| `eu_ctis` | `VERIFIED_API` ⭐ | **本轮最有价值的新增通道**：`https://euclinicaltrials.eu/ctis-public-api` 匿名可用（`POST /search`、`GET /retrieve/{ctNumber}`），返回 `publishDate` / `decisionDateOverall` / `startDateEU` / `sponsor`——打开了 CT.gov 看不到的欧盟试验 |
| `who_ictrp` | `UNAVAILABLE` | 仅 ASP.NET 门户，无机器接口；各国注册库数据未聚合为可下载数据集 |

EU CTIS 的意义不止"多一个源"：它让"某医疗器械技术在欧洲进入临床试验"这一事件首次具备
**可核实公开日期**，而 PHOENIX-003 的 N3 建议正是要补非 FDA 的监管足迹。

---

## 6. E · 海关、贸易与供应链（重点章节）

这一节必须把两类完全不同的数据分开：

* **国家级贸易统计**：某国 × HS 编码 × 期间的进出口总额。**不能识别企业。**
* **企业级货运/提单**：进口商、出口商、发货日、HS、货物描述、港口。**能识别企业。**

**它们不是同一种数据，不能互相替代。** 本轮把二者用不同 `kind` 固化在 schema 里
（`trade_aggregate` vs `shipment` vs `trade_by_trader`）。

### 6.1 官方贸易统计

| 来源 | 状态 | 关键判断 |
|---|---|---|
| `un_comtrade` | `VERIFIED_API` | `/public/v1/preview/...` **免 key 返回真实数据**（HS 9018/9022/9402, reporter 842, 2023）；正式 `/data/v1` 需（免费）订阅 key。preview 会静默截断，描述字段为 null，且**没有任何发布日期字段** |
| `eurostat_comext` | `VERIFIED_API` | 免 key；2023 德国进口 HS9018 = €2.68bn（真实检索值）。同样只有期间，没有发布日期 |
| `uk_hmrc_trade` | `VERIFIED_API` | **唯一开放的企业级通道**：Trader 实体含 CompanyName + PostCode，可与 CN8 × 月份 join。但**无金额、无数量、无伙伴、无提单号** |
| `us_census_trade` | `REQUIRES_REGISTRATION` | ⚠️ **最危险的坑**：无 key 时返回 **HTTP 200 + text/html "Missing Key"**。任何 `if response.ok` 的客户端都会把错误页当数据解析 |
| `usitc_dataweb` | `UNAVAILABLE` | 纯 SPA，无可发现 API；`www.usitc.gov` 403 |
| `china_customs_stats` | `UNAVAILABLE` | 所有路径 HTTP 412 反自动化 |

### 6.2 企业级货运与提单

| 来源 | 状态 | 关键判断 |
|---|---|---|
| `importyeti` | `BLOCKED_BY_POLICY` | robots.txt 明确 `Disallow /search?q` 与 JSON API。**一个数据请求都没发** |
| `importgenius` | `PAID_ONLY` | 公开价目：$229/月起（年付 $183/月） |
| `panjiva` | `PAID_ONLY` | S&P Global 议价，无公开价 |
| `descartes_datamyne` | `PAID_ONLY` | 报价制；索引中的 URL 已 404 |

### 6.3 对七个必答问题的直接回答

1. **能否识别五家企业的真实运输记录？** 不能。没有任何合法的企业级提单数据可用。
2. **能否找到其供应商或进口商关系？** 不能。
3. **货物描述能否关联具体器械或零部件？** 在可获得的数据里不能（HS 是品类，不是产品）。
4. **能否识别供应链变化？** 只有在**国家×HS**层面，且只能看到总量波动，看不到企业转移。
5. **有无可靠历史时间序列？** Comtrade 回溯到 1962（年），Eurostat/HMRC 多年；但**都没有发布日期**，
   无法回答"当时何时可知"。
6. **数据覆盖是否偏向海运？** 提单类数据确实偏向海运与美线；本轮未获得该类数据，故不评价其覆盖。
7. **能否与监管产品身份建立可信关联？** 不能。所有已获得的贸易数据都没有器械产品标识符。

**HMRC 的真实价值边界**：它是唯一能说"某具名英国实体在某年某 CN8 编码下有贸易活动"的开放来源，
五家企业的英国实体全部命中（Medtronic 4 / Philips 3 / Draeger 3 / GE HealthCare 2 / Mindray 1）。
但这只证明**存在性**，不含金额、数量、伙伴；且名称噪声大（如 `PHILIPS PHILIPHS`），
多家共用 HMRC 自己的地址 `AB10 1ZP`，**地址不能用于消歧**。

**结论：海关数据对国家层面的需求背景有价值，对企业级供应链研究在本轮条件下没有可用的合法入口。**
任何声称"用海关数据追踪五家企业供应链"的方案，必须以采购授权为前提，且要先验证其
企业标识符与产品描述质量——本轮无法验证。

---

## 7. F · 医院采购与政府招投标

| 来源 | 状态 | 关键判断 |
|---|---|---|
| `usaspending` | `VERIFIED_API` | 匿名可读（award search 是 POST-only）。**但没有任何"公众可见日"字段**——只有 action / signature / performance 日期 |
| `uk_find_a_tender` | `VERIFIED_API` ⭐ | **本轮最好的采购源**：同一 `ocid` 下 tender 与 award/contract 是不同 stage-tagged 对象、不同日期；唯一同时给出供应商名 + OCDS 组织 ID（`GB-FTS-…`） |
| `eu_ted` | `VERIFIED_API` | Search API v3 匿名 POST 可用，`notice-type` 干净区分 cn-standard(2.95M) 与 can-standard(2.86M)；**但 `winner-name`/`winner-partname` 即便 2024 年医疗器械中标公告也返回 null** |
| `china_ccgp` | `VERIFIED_PUBLIC_QUERY` | 解析出 90 条真实公告；中文页面，结构稳定性未知 |
| `sam_gov` | `REQUIRES_REGISTRATION` | 文档明确 `api_key` 必填；**无 key 时网关返回 404 空 body（不是 401/403）**，容易被误判为"路径错误" |
| `ocds_registry` | `NOT_TESTED` | 它是标准层，不是发布方，刻意不测 |
| `china_ccgp` | — | 见上 |

**采购链条必须分层：招标公告 → 中标 → 合同签署 → 交付 → 实际收入，这五步不是一件事。**
本轮的实测结论是：**产品级采购关联不成立**。所有 10 个源都没有器械产品标识符；
CPV `33100000` 命中 48.8 万条是"品类"，不是产品；合同描述是自由文本。
EUDAMED/UDI 与采购合同之间**没有可用的连接键**。

因此 `eu_ted` 被**故意不写连接器**：它的 search API 能返回公告，但不含中标供应商，
产出"没有供应商的 award"比不产出更糟。

---

## 8. G · 企业招聘与研发能力

| 来源 | 状态 | 关键判断 |
|---|---|---|
| `greenhouse` | `VERIFIED_API` | 平台可用（控制板 stripe 返回 766 个岗位）；但**五家目标企业在 Greenhouse 上全部不存在（404）** |
| `lever` | `VERIFIED_API` | 同上（控制板 leverdemo 返回 10 条）；五家全部不存在 |
| `workday_phenom` | `UNAVAILABLE` | 无厂商中立 API；`jobs.medtronic.com` 存在**证书主机名不匹配**（未关闭校验绕过） |
| `company_careers_pages` | `UNAVAILABLE` | 4 个页面中 2 个 200、1 个 403、1 个 404；Philips 岗位页客户端渲染，HTML 无岗位记录 |

**这是本轮最干净的负面结论之一**：404 出现在同一轮里控制 token 正常返回的情况下，
所以它说明"这五家公司不使用这两个 ATS"，而不是"网络故障"。
**结论是"招聘数据在本轮条件下对五家企业不可得"，不是"这些公司不招人"。**

即使将来拿到岗位数据，也必须遵守三条：岗位新增 ≠ 技术突破；必须区分研发/销售/生产；
必须记录原始公开时间与实际首次观测时间。

**与既有研究的关系**：`research/s031-hiring-capability-study`（PR #22，未合并）已有一套
确定性的职能与技术赛道分类器（`classify_rules(job)`）。本轮**刻意不耦合**未合并代码，
也不重复实现它——本轮的岗位记录只到"证据记录"层，不做职能分类。正确的未来集成方式是
把岗位证据路由进 s031 的分类器，而不是并存两套口径。

---

## 9. H · 科研资助、产业合作与政府项目

| 来源 | 状态 | 关键判断 |
|---|---|---|
| `nih_reporter` | `VERIFIED_API` | **POST-only 且免 key**；返回项目号、机构、开始日。可作为"某机构在某方向获资助"的确定性证据 |
| `eu_cordis` | `VERIFIED_PUBLIC_QUERY` | 无官方 API，但站点自带匿名 JSON 端点：`/search/en?format=json` 返回"result 报告"，其 `relations.associations.project.id` 可再取 `/project/id/{id}?format=json` 拿真实项目（startDate、ecMaxContribution、参与机构）。直接按 project 类型搜会静默返回空/500 |
| `sbir_gov` | `UNAVAILABLE` | 全部 403 + 官网维护公告 |

资助数据的独特价值：它记录的是**监管之前的研发投入**，且参与方有明确机构名与项目号，
是本轮唯一"既在监管之前、又有稳定标识符"的通道之一。

---

## 10. I · 上市后安全、质量与生产网络

| 来源 | 状态 | 关键判断 |
|---|---|---|
| `openfda_device_recall` | `VERIFIED_API` | 真实记录；`event_date_initiated`（发起）与 `event_date_posted`（公开）**是不同字段**。Medtronic 1932 条中只有 1599 条有 `posted`（缺 333，约 17%）——用公开日做年度序列会**静默丢记录** |
| `openfda_device_maude` | `VERIFIED_API` | 厂商识别必须走嵌套 `device.manufacturer_d_name`（裸字段 404，顶层 `manufacturer_name` 为空）。无 key 时关键字 count 上限 100 桶（实证 403） |
| `fda_device_shortages` | `VERIFIED_PUBLIC_QUERY` | 无 openFDA 端点（404 实证）；解析 HTML 双表得 242 条（6 短缺 + 236 停产）。**短缺表本身没有厂商列**，只有停产值有 → 五家 0 条是真实负结果 |
| `fda_import_alerts` | `VERIFIED_PUBLIC_QUERY` | `ialist.html` 解析 154 条 alert；设备组 19 个子类；**索引完全没有公司列** → 企业级覆盖 `UNKNOWN` |

**科学纪律（必须随任何数字一起出现）：被动上报数量 ≠ 真实故障率。**
MAUDE 五家报告量级：Medtronic 3,360,860、Philips 202,348、GE 3,893、Mindray 3,700、Dräger 2,742。
Dräger 与 Medtronic 相差 **3 个数量级**，这反映的是上报激励、诉讼环境、装机量与流程，
**不是质量相差 3 个数量级**。本仓库每条 MAUDE 证据的 `normalized.interpretation_warning`
都写死了 "PASSIVE REPORTING COUNT, NOT AN INCIDENCE RATE"。

---

## 11. 六个跨领域结论

**C1 · 时间语义的缺陷比数据缺失更常见。**
31 个已验证来源里，真正同时提供（事件日 + 首次公开日 + 版本历史）的**不超过 5 个**。
USAspending 完全没有公开日；Comtrade/Eurostat 只有期间；
PubMed 只有出版日没有录入日区分；openFDA 有决定日但无首次公开日。
**"能拿到数据"和"能用它做时间敏感的科学研究"是两个不同的门槛。**

**C2 · 企业身份关联是比覆盖量更紧的瓶颈。**
EXP-B 显示：仅靠产品名称匹配可以覆盖 84.2% 的锚点（对无关证据的误连率仅 0.3%），
但一旦要求**记录本身能确认制造商**，覆盖率跌到 18.4%，且 78.1% 的锚点被拒绝。
这不是匹配算法不够好，而是**来源本身不携带企业身份**。

**C3 · 跨源去重必须先做，且它同时保护两个方向。**
同一 DOI 在 4 源 → 75% 重复；但企业级多源检索重叠仅 0–9%。
**去重防虚增，多源增召回，两件事同时成立**——只报其一是选择性汇报。

**C4 · 有 4 个来源会"用成功状态码返回错误页"。**
Census（200 + HTML "Missing Key"）、SAM.gov（404 空 body）、
PatentsView legacy（200 + SPA 外壳）、CORDIS（project 类型搜静默返回空）。
**状态码不是数据有效性证明**，每个连接器都必须校验内容形状。

**C5 · 反自动化阻断是真实存在的，且必须绕开而不是绕过。**
NMPA（412 + JS challenge）、TGA、ImportYeti（robots 明示禁止）都被如实记为阻断。
本轮**没有任何一次尝试求解验证码、伪造 UA、使用代理或关闭 TLS 校验**。

**C6 · 专利是最大缺口，且它有明确的、免费的解。**
7 个专利源产出 0 条记录。两个免费账号（USPTO ODP、EPO OPS）即可打开。
这是本轮给出的最可执行的一条建议。

---

## 12. 与 PHOENIX-001 的分工（避免重复）

| 项目 | 它审的是 | 本报告审的是 |
|---|---|---|
| PHOENIX-001 `PHOENIX_EXTERNAL_PROJECT_REGISTER.md` | 13 个**外部项目/商业平台**的许可与可复现性 | 59 个**原始数据源**的可访问性、字段、时间语义 |
| PHOENIX-001 `PHOENIX_LICENSE_AUDIT.md` | 第三方**代码**许可与供应链 | 数据**条款**、认证、费用、再分发权限 |

两者互补而不重叠：PHOENIX-001 回答"别人怎么做的、能不能抄"，
本报告回答"原始证据从哪来、能不能合法自动获取"。本报告未重复审计任何 PHOENIX-001 已登记的项目。

---

## 13. 本轮未能解决的未知

1. **EUDAMED** 注册后能拿到什么字段、历史版本是否可回溯——未验证（需授权）。
2. **TED 的中标供应商字段**为何恒为 null——是索引未含还是 API 层裁剪，未确定。
3. **CTIS `publishDate` 的精确语义**（是首次公开还是状态变更时间）——需更大样本。
4. **CORDIS 的字段化查询语法**——目前只能用自由文本检索 + 报告解析。
5. **HMRC trader 数据的完整性**（是否覆盖所有英国进口商）——未评估。
6. **五家企业的真实招聘数据从何获得**——Greenhouse/Lever 已排除，Workday/Phenom 无中立接口。
   候补路径：企业官网定向解析（本轮的 4 个页面样本质量不足）或商业 ATS 数据商（未评估）。
7. **商业提单数据的字段质量**——无样本，无法评估。这是"值得采购但无法在采购前验证"的典型情况，
   本报告不给推荐分。

---

## 14. 复现方式

```bash
# 1. 逐源重放探针（每个源的请求与响应都在 probes/<id>/ 下）
python research/data_expansion/tools/build_access_verification.py

# 2. 重建合并注册表（文档层 + 探针层）
python research/data_expansion/tools/build_register.py --check

# 3. 由注册表派生评分（规则透明、可审计）
python research/data_expansion/tools/derive_scores.py --check
python research/data_expansion/tools/score_sources.py --check

# 4. 校验预注册哈希未被修改
python research/data_expansion/tools/pre_registration.py --check

# 5. 全部交付物 + 离线测试
python research/data_expansion/tools/verify_deliverables.py
```
