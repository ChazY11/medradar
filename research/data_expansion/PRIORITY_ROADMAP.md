# 数据源优先级路线图（DATA-EXPANSION-001）

**评分规则：** [`EXPERIMENT_DESIGN.md`](EXPERIMENT_DESIGN.md) §5 + [`registry/SOURCE_SCORING_RUBRIC.json`](registry/SOURCE_SCORING_RUBRIC.json)
**逐源评分：** [`registry/source_priority_scores.json`](registry/source_priority_scores.json)（含每个维度的规则或人工覆盖理由）
**重算：** `python research/data_expansion/tools/derive_scores.py --write && python research/data_expansion/tools/score_sources.py`

> 权重在**看到任何实验结果之前**冻结（哈希见 `experiments/pre_registration.json`）。
> 十个维度的权重之和 = 1.000000，评分工具每次运行都会校验这一点。

---

## 0. 一句话

**立即接入 3 个（openalex / crossref / clinicaltrials_gov），试点 12 个，其余按下表处置。**
但真正的结论不是排名，而是：**排名靠前的来源都属于"证据补充"，没有一个能解决本轮暴露的核心瓶颈——产品级身份。**

---

## 1. 评分分布（59 个来源）

| 分类 | 数量 | 来源 |
|---|---|---|
| **ADOPT NOW** | 3 | `openalex` (83.5)、`crossref` (81.0)、`clinicaltrials_gov` (71.0) |
| **PILOT** | 15 | `accessgudid` (80.8)、`openfda_device_510k` (77.0)、`uk_find_a_tender` (76.5)、`fda_gudid_download` (75.8)、`openaire` (73.5)、`openfda_device_pma` (72.0)、`openfda_device_maude` (70.0)、`openfda_device_recall` (68.3)、`eu_ctis` (67.3)、`europepmc` (67.3)、`nih_reporter` (67.3)、`openfda_device_classification` (67.0)、`openfda_device_registrationlisting` (67.0)、`uk_hmrc_trade` (66.5)、`pubmed_eutils` (63.5)、`eu_cordis` (62.5)、`canada_mdall` (62.0)、`semantic_scholar` (57.3)、`openfda_bulk_download` (57.0)、`usaspending` (56.5)、`un_comtrade` (54.0)、`eu_ted` (52.8)、`eurostat_comext` (52.8)、`fda_device_shortages` (52.3)、`greenhouse` (50.3) |
| **RESEARCH ONLY** | 5 | `ocds_registry`、`china_ccgp`、`fda_import_alerts`、`lever`、`company_careers_pages` |
| **BLOCKED** | 30 | 见 `source_priority_scores.json` |
| **REJECT** | 5 | `lens_org`、`importgenius`、`panjiva`、`descartes_datamyne`、`korea_mfds` |

（PILOT 实际 25 个；上表合并了同分项以便阅读，精确清单以 JSON 为准。）

---

## 2. 与评分标签不一致的三处，以及为什么

评分规则是机械的；下面三处**机械标签与工程判断不一致**，必须显式说明而不是偷偷调分。

### 2.1 监管注册库无法拿到 `ADOPT NOW`，因为 EXP-A 没测它们

`accessgudid` (80.8)、`openfda_device_510k` (77.0)、`canada_mdall` (62.0) 的分数足够，
但 `ADOPT NOW` 要求 `EXP-A = INCREMENTAL`，而 EXP-A 的锚点检索只覆盖了**可按产品名检索**的
文献/试验/采购来源。监管注册库是**身份锚**，不是"按名字搜索的内容源"，EXP-A 的方法对它不适用。

**处置：** 保留 `PILOT` 标签（规则一致），但**路线图决定是"立即接入"**。理由：
它们提供 DI / licence_no / 官方编号，是本轮所有其它关联的前提；没有它们，EXP-A/EXP-B 的
"产品专长"永远无法升级为"确认关联"。
**这是规则的表达力不足，不是这些源的缺陷。**

### 2.2 `greenhouse` / `lever` 得分 50+，但对本项目覆盖为零

平台验证通过（控制板正常返回），但**五家目标企业在两个 ATS 上全部不存在**。
评分衡量的是"来源能力"，不是"对目标企业的覆盖"——**rubric 没有这个维度**。

**处置：** 路线图决定 **`REJECT`（对本项目）**，并在 `DATA_QUALITY_REPORT.md` 记录
"404 = 无此板，不是平台不可用"。

### 2.3 商业来源一律落到 `REJECT`

`lens_org` (39.5)、`importgenius` (35.8)、`panjiva` (35.8)、`descartes_datamyne` (33.3)。
原因是 rubrics 的反作弊规则：**未验证的能力维度记 0 分**。付费源无法试用以验证时间语义与
产品关联，所以分数天然低。

**处置：** 保留 `REJECT` 标签（规则一致），但在下面 §4 单列为 **`COMMERCIAL CANDIDATE`**。
**"按规则被拒" ≠ "没有价值"**：它们的问题是无法在用钱之前验证，而不是已知的无用。

---

## 3. 立即行动（ADOPT NOW + 等价项）

| 顺序 | 来源 | 理由 | 具体动作 |
|---|---|---|---|
| 1 | `accessgudid` + `fda_gudid_download` | 产品身份的唯一全球锚（DI） | 每日增量 + 周期性全量；把 DI 作为主键接入 staging |
| 2 | `openalex` + `crossref` + `europepmc` | 证据覆盖最广、时间语义可分离、企业归因有结构化路径 | 复用 scholarly 连接器；**强制走 `dedupe.py`**（4 源同文 → 1 篇） |
| 3 | `clinicaltrials_gov` + `eu_ctis` | 监管前的研发活动，双辖区 | CT.gov 已有；CTIS 是本轮新增通道 |
| 4 | `canada_mdall` | 唯一可跑的非美国注册库，且可与 DI 联合匹配 | 作为 C3 检查的常驻通道 |
| 5 | `openfda_bulk_download` | 唯一带快照时钟的监管通道 | 用它给监管语料打"快照日期"，而不是用 API 的采集时间 |

---

## 4. 试点（PILOT）：按"能补哪个缺口"分组

| 缺口 | 来源 | 试点要回答的问题 |
|---|---|---|
| 上市后证据 | `openfda_device_maude`、`openfda_device_recall`、`fda_device_shortages`、`fda_import_alerts` | 报告量能否作为**相对**变化指标（而非故障率）使用 |
| 资助与产业合作 | `nih_reporter`、`eu_cordis` | 资助→机构→技术方向的确定性链条能建多长 |
| 采购 | `uk_find_a_tender`、`usaspending`、`eu_ted`、`china_ccgp` | 企业级需求证据能否在不依赖产品 ID 的前提下成立 |
| 宏观需求背景 | `un_comtrade`、`eurostat_comext`、`uk_hmrc_trade` | 只做背景，不做企业推断 |
| 欧盟视角 | `openaire`、`eu_ctis` | 与英语世界来源的互补度 |
| 补充检索 | `semantic_scholar`、`pubmed_eutils` | 限流下的可用吞吐 |

---

## 5. 商业候选（规则标 REJECT，但值得采购评估）

| 来源 | 它唯一能解决什么 | 代价（公开信息） | 采购前必须先验证 |
|---|---|---|---|
| `epo_ops`（免费注册，不是付费） | 专利公开日 + 专利族 + 引用 | 免费，配额按体积 | 配额是否够 5 家企业的长窗口 |
| `uspto_open_data_portal`（免费注册） | 美国申请/公开全文检索 | 免费 key | 字段是否含公开日与申请人历史名 |
| `lens_org` | 论文—专利关联（31.6M NPL 匹配） | 机构订阅，价格不公开 | 是否允许科研二次分发 |
| `importgenius` | 企业级提单 | $229/月起 | 字段完整性与五家企业的实际覆盖 |
| `panjiva` / `descartes_datamyne` | 同上 | 议价 / 报价制 | 同上 |

**注意 `epo_ops` 与 `uspto_open_data_portal` 是免费注册，不是采购。**
它们被归入 BLOCKED 只是因为本轮不做注册。**这是本轮最便宜的两个能力解锁点。**

---

## 6. 阻断（BLOCKED）：按"为什么阻断"分组

| 原因 | 来源 | 是否有合法替代 |
|---|---|---|
| 需免费注册 | `us_census_trade`、`sam_gov`、`eu_ted`（批量）、`brazil_anvisa`、`eudamed` | 有（注册）或部分（TED 搜索 API 可用但无供应商） |
| 需商业授权 | `wipo_patentscope`、`google_patents_bigquery` | 有（免费注册路径） |
| 站点主动阻断自动化 | `china_nmpa_device`、`china_nmpa_udi`、`australia_tga_artg`、`china_customs_stats`、`usitc_dataweb` | **无**（不得绕过） |
| 制度上不存在公开数据 | `uk_mhra_device`（无公开产品注册库）、`who_ictrp`（无机器接口） | 无 |
| 站点已死 / 退役 | `patentsview`（NXDOMAIN）、`uspto_patent_bulk`（主机不解析） | 有（USPTO ODP） |
| 服务不可用 | `sbir_gov`、`company_careers_pages`、`workday_phenom` | 部分 |
| 明确禁止自动访问 | `importyeti`（robots 明示） | 无（合规选择） |

---

## 7. 长期维护成本排序（谁最可能先坏）

| 风险 | 来源类型 | 例子 |
|---|---|---|
| **高**（HTML 解析、无文档端点） | 公开查询页 | `fda_device_shortages`、`fda_import_alerts`、`china_ccgp`、`eu_cordis` |
| **中**（稳定 API，但字段语义会变） | 官方 API | `openfda_*`、`un_comtrade`、`usaspending` |
| **低**（有 schema 版本与文档） | 成熟开放 API | `openalex`、`crossref`、`clinicaltrials_gov`、`canada_mdall`（有官方字段文档） |

**结论：`VERIFIED_PUBLIC_QUERY` 的 4 个来源都应当视为"随时会坏"，必须配套
"解析失败即报警、绝不用空结果冒充无数据"的守卫。** 本轮 `fda_device_shortages` 与
`fda_import_alerts` 的解析器已经这样做了。

---

## 8. 下一轮的唯一高优先级建议

**不要先加第 60 个数据源。** 本轮的三个实验指向同一个瓶颈：

- EXP-B：一旦要求企业确认，覆盖率从 84.2% 掉到 18.4%，拒绝率 78.1%；
- C3：36.7% 的"更早加拿大足迹"里只有 2/30 通过严格匹配，其余是品牌词误配；
- EXP-C：`NO_DETECTABLE_LEAD`，且与 PHOENIX-003 独立复现同一负面结论。

**这三条都是产品身份问题，不是数据量问题。** 下一轮应该做的是：

1. 把 `accessgudid` 的 DI 作为主键建产品身份表；
2. 用 MDALL 的 `deviceidentifier` 端点做 US↔CA 的 DI 级对齐（`canada_mdall` 已支持该端点）；
3. 只有在产品身份可用之后，才重新跑 EXP-B 与 EXP-C——**届时"能否提前发现"才是一个可测问题**。
