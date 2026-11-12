# EXECUTIVE_SUMMARY_ZH — HORIZON-001 中文总结

**全球医疗技术数据前沿探索与真实数据资产建设**
分支 `research/horizon-001` · 基线 `b2a14c0`（已核实的 origin/main HEAD）· 独立 worktree
`<REDACTED_LOCAL_PATH> · 与 ATLAS-001 零文件重叠

---

## 一、这次究竟拿到了哪些新数据

| 指标 | 结果 |
|---|---|
| 深度审计来源 | **51 个**（每个都有 registry 记录：访问状态、许可、阻断原因、合法解锁路径；`hz.cli verify` 0 问题） |
| 实际产出数据并进入导出 | **24 个来源** |
| 导出记录总数 | **6,492 条**（`exports/horizon-2026-11-10/`，24 个 JSONL + MANIFEST + 每文件 SHA-256）；CIPO 以分层抽样 2,000 条入栈，全量 19,702 条由已提交连接器可再生 |
| 新增专利管辖区 | **2 个**（EPO 欧洲、CIPO 加拿大），此前专利资产为零 |
| 真实专利记录 | **19,930 条**（EPO 228 + CIPO 19,702，后者导出时抽样 2,000），全部带官方号与日期 |
| 监管器械记录 | **954 条**（AccessGUDID 320、Health Canada MDALL 174、openFDA 510(k) 160、分类 60、PMA 60、注册列名 60、巴西 ANVISA 120），**954/954 带来源方签发的官方标识** |
| 科技文献记录 | 308 源行 → **60 篇去重后的独立作品**（同一作品最多同时出现在 6 个库里） |
| 采购与贸易记录 | 贸易序列 1,408 行；采购中标 370 家有具名供应商 |
| 可确认关系数 | 试验↔论文 69 CONFIRMED / 113 CANDIDATE；资助↔成果 10 CONFIRMED / 33 CANDIDATE；**器械↔采购 0 CONFIRMED** |

**最重要的一句话**：这一轮真正的突破不是"更多行"，而是**打通了两条此前拿不到的、带明确许可与真实公开时间的专利通道**，并且证明了现有文献库的"发表日期"字段不能直接当作可观测时间使用。

---

## 二、全球专利数据有没有真正突破

**有，而且是本轮最大成果。** 五家目标企业的专利样本第一次真正建立起来。

### 突破 1：EPO 欧洲公布服务器（无需任何 Key）

此前被反复调查的 EPO OPS / USPTO ODP / PatentsView / Lens / Espacenet **全部需要免费 Key 或被 WAF 拦死**。真正的通道不在这些 API 上，而在 EPO **自己的 robots.txt** 里：

```
Sitemap: https://data.epo.org/publication-server/sitemap.xml
```

这是一个按周切分的完整 EP 公布清单（1978-12-20 至今）。每周 gzip XML 给出每件公布的**公布号、申请号、申请日、IPC**；再取 `document.html` 就得到完整 INID 著录项：申请人（71）、发明人（72）、专利权人（73）、IPC（51）、CPC（52）、申请日（22）、公布日（43）、授权日（45）、优先权（30）、标题（54）、摘要（57）。

实测：10 周 sitemap → 37,989 件公布 → **3,093 件医疗器械相关**（8.14%）→ 取 228 篇正文 → 228 条记录，其中 **197 条是独立技术披露**。

### 突破 2：CIPO 加拿大专利全库（明确开放许可）

`open.canada.ca` 上的 CIPO 专利数据集采用 **Open Government Licence – Canada**，原文授权"worldwide, royalty-free, perpetual, non-exclusive licence … including for commercial purposes"。覆盖 **1869 → 2022-02-28**。

本轮取回 `PT_Main` + `PT_Interested_Party` + `PT_Priority_Claim`（337 MB），扫描 1,321 万条当事人行，得到 **19,702 条**目标企业相关加拿大专利。

### 这项突破最有价值的发现：历史子公司归属被低估 2.8 倍

| 申请人别名 | 专利数 |
|---|---|
| PHILIPS | 13,508 |
| MEDTRONIC | 1,837 |
| **TYCO HEALTHCARE** | **1,613** |
| **COVIDIEN** | **1,553** |
| GE HEALTHCARE | 572 |
| ST. JUDE | 245 |
| DRAGER / DRAEGER | 180 / 113 |
| RESPIRONICS / VOLCANO / OHMEDA / DATEX-OHMEDA / GE MEDICAL SYSTEMS / ARTERIAL VASCULAR / INSTRUMENTARIUM / SPECTRANETICS / ST JUDE | 78 / 77 / 50 / 35 / 26 / 20 / 13 / 13 / 1 |
| MINDRAY | **0** |

**如果只用"Medtronic"这个名字过滤，只能找到 1,837 件；该集团在本数据集中的真实足迹是 5,078 件——因为其中 3,166 件是以 Tyco Healthcare / Covidien / St. Jude Medical / Arterial Vascular 名义申请的。**

这正是任务书点名的头号瓶颈，现在有了可复现的实测数字。CIPO 的 `Owner Enable Date` / `Ownership End date` 还提供了带生效日期的**所有权时间线**，是唯一能找到的、可用于"当时是谁的"而不是"现在是谁的"的结构。

### 专利时间语义陷阱（已处理，代价可量化）

同一件 EP 授权文本同时印着两个公布日：
`EP2490731B1`：(43) 申请公布 **2012-08-29**，(45) 授权公布 **2024-06-05**。
若把 (43) 当作授权日的公开时间，会把 2024 年的文件放到 2012 年，**误差 11.8 年**。连接器按 kind 选择，并把两个原始值都存下来。

实测 公开日−申请日 间隔：EPO 中位 **1,738 天（4.8 年）**，最长 6,881 天；CIPO 中位 **1,588 天**，最长 6,861 天。

另一个陷阱：EP 公布的 A3（检索报告）和 B8（更正扉页）**不是独立技术披露**。228 篇里有 31 篇属于此类，直接计数会把语料虚增 **13.6%**。

---

## 三、海外医疗器械注册数据扩展到了什么程度

| 管辖 | 状态 | 记录 | 官方标识 | 限制 |
|---|---|---|---|---|
| 美国 AccessGUDID | 打通 | 320 | **UDI-DI（GS1/官方）** | 无公开时间字段（100% `EVENT_ONLY`） |
| 美国 openFDA 510(k) | 打通 | 160 | **K 号** | 只有决定日期，无记录公开日 |
| 美国 openFDA 分类/注册列名/PMA | 打通 | 60/60/60 | 产品码、注册号、PMA 号 | 同上 |
| 加拿大 MDALL | 深化 | 174 | **器械许可证号** | 有许可日期，但**没有"首次公开"时间** |
| 巴西 ANVISA | 部分 | 120 | 部分缺失 | 分页不完整，多数记录缺标识 |
| 欧盟 EUDAMED | 阻断 | 0 | — | 需 EU 登录，无匿名机器接口 |
| 澳大利亚 TGA | 未取得 | 0 | — | 目录开放但样本内未找到完整著录数据集 |
| 日本 PMDA / 英国 MHRA / 中国 NMPA UDI | 阻断 | 0 | — | 均需注册或人工 |

**关键结论**：这些库都提供**官方产品标识**（UDI-DI、K 号、许可证号）——这是身份解析唯一可靠的锚点。但它们**普遍不提供"这条记录何时可被公众看到"**。所以这批数据能做身份比对，不能单独做历史可观测性研究。834 条监管记录中 **0 条**具备完整双时钟。

---

## 四、有没有找到真正新的医疗技术证据

分三类，严格区分：

**A. 独立新增证据（可据以改变判断）**
1. CIPO 历史子公司归属：Medtronic 集团真实足迹 5,078 件 vs 名称直搜 1,837 件（**2.8 倍差**）。
2. EPO 双时钟：228/228 条记录都同时具备申请日与公布日，中位间隔 4.8 年——直接证明"用申请日当观测时间"会制造 5 年级别的伪前瞻。
3. 跨库发表日期分歧：**60% 的作品在不同数据库里发表日期不一致，36.7% 相差超过 30 天**（Europe PMC vs Semantic Scholar 达 56.8%）。同一批作品的 DOI/PMID/PMCID 却**零冲突**。
4. 索引延迟：OpenAlex `created`−发表日中位 **+14 天**（最长 969 天）；Crossref 中位 0 天，且 **21/59 在名义发表日之前就已登记**。
5. 临床试验登记队列：提交→首次公示中位 8 天，最长 **892 天**。
6. 文献去重比例：**308 源行 = 60 篇作品（0.195）**，天真的"多库相加"会虚增 5.1 倍。
7. 采购：370 家中标供应商，其中 **245 家由 SAM UEI 官方标识钉死**；CPV `33100000` 经实测**不是**器械过滤器（匹配结果含洗衣、皮革类）；任务书给的 PSC 映射 **6 个里错了 3 个**（6540 是眼科、6545 是成套野战医疗包，试剂是 6550）。

**B. 重复收录（不计为新增）**
EP 的 A3/B8 共 31 篇；跨库同一 DOI 的 308 源行中 248 行是重复；TED 299 行对应 93 个公告、FTS 62 行对应 16 个发布。

**C. 无法确认的候选**
693 条 `CANDIDATE` 关系（试验↔论文 113、资助↔成果 33、采购器械↔中标 124、专利企业归属 423 等）。**没有任何一条跨源器械身份达到 CONFIRMED。** 这是证据的真实状态，不是代码偷懒。

---

## 五、哪些数据值得进 MedRadar 正式基座（按优先级）

| 优先级 | 数据 | 理由 | 建议动作 |
|---|---|---|---|
| **P0** | `epo_publication_server`（EP 专利） | 唯一 keyless 且带申请人/日期/IPC/优先权的专利源；已证明可复现 | 直接入基座；下一步加密采样 |
| **P0** | `cipo_canada`（CA 专利 + 所有权时间线） | 明确开放许可 + 150 年深度 + 带日期的所有权变更 | 入基座，但**必须标注 firm-scoped 而非技术-scoped** |
| **P0** | `accessgudid` + `openfda_device_classification` | UDI-DI 与产品码是产品身份解析的锚点 | 入基座，作为身份主键 |
| **P1** | `canada_mdall` | 许可证号是跨国比对的第二锚点 | 入基座 |
| **P1** | `openfda_device_510k` / `_pma` | 批准时间线（事件时钟） | 入基座，只用于事件时钟 |
| **P1** | `clinicaltrials_gov` + `nih_reporter` | 唯一可核实"资助/试验↔成果"关系 | 入基座，关系保留 CONFIRMED/CANDIDATE 两态 |
| **P2** | `crossref` / `europepmc` / `openalex` | 有真实创建时间戳，可支撑索引延迟研究 | 入基座，**但不要合并成单一发表日期** |
| **P2** | `usaspending` / `eu_ted` / `uk_find_a_tender` | 有具名中标方（UEI/注册号） | 入基座，作产业采用证据，**不得推断厂商收入** |
| **P3** | `eurostat_comext` / `uk_hmrc_trade` | 明确的开放许可宏观序列 | 仅作行业背景，**不得归因到企业** |
| **不入座** | `un_comtrade` | 公开 API 与其使用协议**直接冲突**，需 UNSD 书面许可 | 待负责人决策；可先用 Comext+HMRC 替代 |
| **不入座** | `brazil_anvisa` | 分页不完整、多数缺标识 | 补齐后再评估 |
| **不入座** | 4 家提单商 | 全部付费/条款禁止 | 不采购 |

---

## 六、哪些方法失败了（保留记录与修复方式）

| 失败 | 精确原因 | 合法修复路径 |
|---|---|---|
| EPO OPS | 匿名 403 / 208 B | 负责人在 `developers.epo.org` 免费注册取 OAuth Key（**未代注册**） |
| USPTO ODP | 401 / 403；`bulkdata.uspto.gov` 已无法解析 DNS | 免费 API Key（`data.uspto.gov/apis/getting-started`） |
| **PatentsView** | **已退役**：旧 API 返回 ODP 单页外壳、`search./ped./assignment-api.` 全部 DNS 消失、S3 bucket 403 | 不要再去试，改用 ODP |
| Espacenet | AWS WAF 403 / 5,878 B 挑战页 | 视为反自动化措施，**未绕过** |
| EU CTIS | 403 `{"message":"Missing Authentication Token"}`；`/retrieve/<n>` 返回 **200 + 2 字节 `{}`**（假成功） | 向 EMA 申请凭据 |
| EU CORDIS | `contenttype='publication'` → 500 `index_not_found_exception`，**根本没有 publication 索引** | EU 资助↔论文关系无法从 CORDIS 建 |
| WIPO PATENTSCOPE | 无匿名机器接口，JSF 有状态会话 | 不抓取；走 WIPO 申请 |
| Google Patents | 批量需 BigQuery + 计费账户 | 由负责人自建 GCP 项目 |
| ImportYeti / ImportGenius / Panjiva / Descartes | robots 禁止 / ToS 禁止 / 纯商业授权 | 结论：企业级提单数据应付费且不应获取 |
| UN Comtrade | 许可冲突（见上） | 需 UNSD 书面许可 |
| OpenAlex 匿名配额 | `meta.notice` 明示每 IP 每天 $0.10（约 100 请求） | 免费 Key 需点邮件确认，未代操作 |
| **自己引入的缺陷** | `BoundedClient` 缓存只按 URL、忽略 `params`，会把第一次响应贴上后续标签 | 已修复为 `(url, sorted params)`；两个受影响工作流已用原始响应重验，结论：数据干净 |

**另外三个只有实测才能发现的技术坑（都已修复并记录）**：EPO 的 IPC 压缩格式（`A61M0005142`＝4+4+剩余，写错会让器械过滤静默归零）；CIPO CSV 是**竖线分隔**且表头中英双语（按逗号读会得到 0 行）；CIPO 某字段超过 `csv` 默认 128 KiB 上限会直接抛异常。

---

## 七、能交给 ATLAS-001 什么

**导出物（不需要访问本机环境）**
- `exports/horizon-2026-11-10/`：24 个来源的 JSONL + `MANIFEST.json`（含每文件 SHA-256、每来源覆盖率、许可摘要）+ `README.md`（说明"不能据此宣称什么"）

**接口与代码（不 import `medradar.*`）**
`hz/schema.py`（记录契约与去重键）、`hz/timeq.py`（四时钟准入判定）、`hz/http.py`（有预算/上限/重试/日志的 HTTP）、`hz/probe.py`（探针证据）、`hz/registry.py`（来源登记）、`hz/export.py`（版本化导出）、`hz/tls.py`（AIA 补链，验证仍然开启）、`hz/verify.py`（离线自检）

**测试**
- `python -m hz.cli verify` → **`ok: true`**：导出全部 `ok:true`（6,492 条记录 0 违反），注册表 51 条 0 问题，5 个探针套件齐全。
- 离线可复现：`experiments/patents/measure_patents.py`、`experiments/scholarly/analyze_exp_h1.py`、`analyze_exp_h3.py`

**依赖**：Python 3.12 + `requests` + `lxml`（+ `pandas`/`openpyxl` 仅用于读数据字典）。无 GPU、无模型训练、无付费 API。

**兼容性**：使用自定义 `horizon.evidence.v1`，未改动 ATLAS-001 任何文件。`ATLAS_HANDOFF.md` 给出字段级映射表、`attributes` 字典、`quality_flags` 闭集、以及 4 个需要 ATLAS-001 回答的接口问题。若 A 发布正式 Evidence Contract，通过 `tools/convert_to_atlas.py` 适配，**不静默改字段含义**。

---

## 八、下一轮最值得挖什么（按真实结果排序）

1. **两把免费 Key（5 分钟，价值最大）**：EPO OPS + USPTO ODP。可解锁专利族、引用、美国专利权人，以及"申请人检索"能力（当前 sitemap 只能按周采样，不能按企业检索）。
2. **CIPO 的 `PT_IPC_classification`**：唯一能把这 19,702 条从"企业口径"变成"医疗技术口径"的表。约 230 MB/分卷，本轮因体积预算主动放弃，是本轮最大的已知缺口。
3. **提高 EP 采样密度而非广度**：单条成本约 135 KB，取连续 4–6 周全部器械公布（约 1,500 篇、200 MB）即可让五家企业都有实质覆盖；本轮 228 篇跨 10 周，三家企业为零。
4. **用 CIPO 所有权时间线校验 ATLAS-001 的母子公司逻辑**：这是唯一带生效日期的所有权事实源，可作为对照组。
5. **把"跨库发表日期分歧"变成正式测量**：已测 60%/36.7%，下一步应给出"以哪个库为权威"的经验依据。
6. **不要再碰**：PatentsView、`bulkdata.uspto.gov`、PEDS、USPTO assignment API（均已消失）。

---

## 九、科学结论的自我约束

- 本轮**没有**制造任何预测能力宣称，**没有**用关键词命中率代替识别准确率，**没有**把回顾性资料的早期存在当成预测成功。
- **0 条**跨源器械身份达到 `CONFIRMED`；全部为 `CANDIDATE` 或 `UNKNOWN`。
- 2,928 条记录（贸易、采购、510(k)、PMA、MDALL）**没有**记录公开时间，被 `hz.timeq` 判定为不可用于可观测性研究——这是来源属性，不是采集缺陷，已在导出清单中标注。
- 228 篇 EP 样本、10 周窗口，**不能**支持"三年内五家企业专利申请趋势"之类的结论。
