# PHOENIX-001 — 全球项目技术图谱

状态：13 个项目已全部完成审计。机器可读主记录为 `experiments/phoenix_001/external_projects.json`。

| # | 项目 | 类型 | 当前状态 | 决策 |
|---:|---|---|---|---|
| 1 | SciTrends | 开源代码 + 论文 | 无 DL 核心实验与 CRISPR 滞后相关已复现；发现时间切分与预处理风险 | **ADAPT** |
| 2 | PubTrends | 开源代码 | Apache-2.0 主题词算法隔离 smoke test 通过；未部署完整堆栈 | **STUDY_ONLY** |
| 3 | NIH iSearch Analytics | 公开科研方法 | rMLC 与历史案例已核查；实现和训练快照未公开，不能复现评分 | **STUDY_ONLY** |
| 4 | The Lens | 数据与科研平台 | MetaRecord、论文—专利关联与 API 条款已核查；未请求 token 或批量数据 | **STUDY_ONLY** |
| 5 | PTNS | 公开论文 | 方法和评价已核查；无公开代码，Incopat 原始数据仅应请求提供 | **BLOCKED** |
| 6 | FDA AI 医疗器械纵向研究 | 公开论文 | 17×4 补充表上的 HHI、趋势、卡方与置换检验已独立复算 | **ADAPT** |
| 7 | Clarivate DRG Medtech | 商业平台 | 字段与预测宣传已核查；无公开回测 | **STUDY_ONLY** |
| 8 | MedVantage | 商业平台 | 九类 FDA 来源、证据回溯与实体解析设计已核查；产品仍属预发布 | **ADAPT** |
| 9 | CMOP | 商业平台 | 绝对准确、实时和实体解析宣传均缺公开评价 | **REJECT** |
| 10 | NextDevice | 商业平台 | 技术代际与全生命周期标签已核查；无预测验证 | **ADAPT** |
| 11 | GBI DEVINT | 商业平台 | 生命周期展示已核查；无独特可复现方法 | **STUDY_ONLY** |
| 12 | DevicePro | 商业平台 | AI+人工归一可借鉴；同页两套规模口径已标记 | **ADAPT** |
| 13 | 众成医械大数据 | 商业平台 | 标讯结构与公开报告已核查；首次公开时间风险未解决 | **STUDY_ONLY** |

“待审计”不是跳过；最终记录不得保留待定项。

## 1. SciTrends — ADAPT

**方法。** 主题—年份出版计数、五年后差分目标、滞后与增长特征、Review/Original Research 比例、专利特征、Ridge 历史基线、CatBoost 和文本嵌入。CRISPR 笔记本另做论文与专利的年度滞后相关。

**实测。** 固定官方提交 `81711b94181bb8d1f5bd93379670bf3250dfc343`，执行作者提供的 `GET_DL_EMBEDS=False` 分支。4,020 个评估行、123 个主题、30 折：

| 方法 | R² | MAE | RMSE |
|---|---:|---:|---:|
| 单特征 Ridge | 0.196297 | 180.444744 | 350.339664 |
| 全量均值插补 Ridge | 0.494889 | 143.115992 | 277.737547 |
| 完整列 Ridge | 0.464486 | 148.725164 | 285.974056 |
| CatBoost 全特征 | 0.845321 | 68.084334 | 153.694052 |

CatBoost 衰退二分类 F1 为 0.791634。这里只说明作者核心 notebook 在本环境产生了这些数值，不等于独立前瞻验证。

**关键反证。** 30/30 折都有日历年同时出现在训练和测试中。逐年排序再做行级 `TimeSeriesSplit`，不等于干净的公开时间截点。另一个 notebook 单元在 CV 前用全量 X 的均值插补。MedRadar 不得照搬这两种做法。

**CRISPR。** 19 个年度观测的同年相关为 0.938010，`patents.shift(-1)` 与论文相关为 0.887012。这是回顾性相关，不是专利提前量的独立预测证据。

**迁移决定。** 独立实现增长、差分和文献类型比例类特征；必须改为按年份净化的滚动原点、训练内预处理，并证明每个特征的当时可知性。仓库无许可证，不能把代码或数据复制进 MedRadar。当前研究库 USPTO 专利为 0 行，因此专利特征没有迁移实验基础。

## 2. PubTrends — STUDY_ONLY

**方法。** 论文/引用网络、图聚类、主题描述、语义嵌入、引用年度增益。主题词描述使用各词在不同聚类中的频率向量，对“理想单聚类向量”的余弦接近度加权。

**实测。** 固定官方提交 `8520f2a19493baa776d929cb3d31a0ae9498132a`，直接执行上游 `topics.py`，只 stub 未使用且会加载重型 NLP 模型的 `text.py`。官方 fixture 通过：

- 聚类 0：`frequent`，权重 2.604346；
- 聚类 1：`rare-1`，权重 2.772589；
- 聚类 2：`rare-2`，权重 2.772589；
- ignore-component 分支也通过。

**边界。** 没有启动 PostgreSQL、Redis、Web、 embedding 服务，也没有抓取 PubMed 或 Semantic Scholar。这个 smoke test 只验证一个主题词函数，不验证聚类质量、主题演化或预测能力。

**迁移决定。** Apache-2.0 允许合规复用，但 MedRadar 当前没有可重建历史知识状态的论文—引用语料。保留“可解释聚类标签”方法，暂不部署完整系统，也不用全历史引用聚类冒充早期特征。


## 3. NIH iSearch Analytics — STUDY_ONLY

公开资料确认其使用 Recursive MultiLevel Clustering 预测科研突破，历史案例包括 CAR-T、mRNA 疫苗和 PrEP 行为研究。NIH 的预算文件称该系统扫描超过 3,500 万篇出版物，目标窗口为 2—12 年。

这些资料没有给出足以无歧义实现 NIH 评分的特征、阈值、训练快照和代码。不能用同名序列聚类算法代替，也不能把历史成功案例当成冻结预测登记。可迁移的是：先操作化定义“突破”，再用带日期的案例检验，而不是拿当前聚类讲述历史。

## 4. The Lens — STUDY_ONLY

MetaRecord 与 LensID 用于规范论文、专利及其实体关系，论文—专利引用连接可用于观察知识扩散。API 需要审批和 token；公开文档描述的试用权限为非商业/有限学术用途且有时间限制，更广泛或商业使用可能要求定制付费方案。本轮未请求 token、未调用 API、未批量下载。

可迁移的是持久标识、来源追踪和分开记录申请日、公开日、引用可知日。当前引用连接是回填结果，不能直接当历史特征。MedRadar 专利行为 0 行，不具备迁移实验输入。

## 5. PTNS — BLOCKED

论文用年度快照表示 publication、IPC、applicant、country 和 citation 关系，依次经过 R-GCN、BiLSTM、PCA/MLP，并用 Richards 曲线拟合引用轨迹。评价区分 new、grown、random patents，并有组件消融和不同预测窗口误差。

论文数据为 Incopat 的 133,857 件聚氨酯专利，公开声明是“向作者请求提供”，没有随文原始数据；也未找到官方代码。作者使用 RTX 4060，报告 PTNS 运行约 46.49 分钟。上述论文数值只作为外部声明记录，本轮没有复现。MedRadar 没有专利图数据，故直接复现与迁移均为 BLOCKED。

## 6. FDA AI 医疗器械纵向研究 — ADAPT

使用 Europe PMC 公开补充表的完整 17×4 专科计数，独立实现 HHI、bootstrap、Cochran–Armitage、卡方、Cramér's V 和 10,000 次置换检验：

| 指标 | 独立复算 | 论文对应值 |
|---|---:|---:|
| Era 1 HHI | 0.181406 | 0.181 |
| Era 2 HHI | 0.427424 | 0.427 |
| Era 3 HHI | 0.738128 | 0.738 |
| Era 4 HHI | 0.611688 | 0.612 |
| Era 4 − Era 3 HHI | −0.126439 | −0.126 |
| χ² | 328.013095 | 328.0 |
| Cramér's V | 0.276514 | 0.28 |
| 期望数 <5 的单元格 | 51 | 51 |
| Radiology Z | 5.300241 | +5.30 |
| Cardiovascular Z | −3.435419 | −3.44 |

置换检验 p=0.00009999；本次随机种子的 HHI 双侧 bootstrap p=0.001，论文报告 p<.001，属于 Monte Carlo/报告差异。复算支持“近期构成多样化”的描述性结论，不支持“HHI 可预测后续扩散”。

未复现企业类型回归和设备级实体去重，因为补充表没有设备×企业类型明细。MedRadar 原始数据库仍缺失，也没有把论文聚合数据冒充 MedRadar 迁移结果。


## 7. Clarivate DRG Medtech — STUDY_ONLY

公开字段包括 company、device series、geography、brand、product type、indication、timeline 和 estimated launch date，另有销售、市场份额、新闻和分析师观点。可借鉴的是字段分层和“观察日期/估计上市日期”分离。

页面声称可做 pipeline 和财务预测，但没有公开回测、校准、误差或独立评价。完整平台为闭源商业产品，本轮只读公开页面。

## 8. MedVantage — ADAPT

其公开设计把九类 FDA 来源连接到 device、company、product code 和 submission 档案，并强调每个聚合点回到原始 filing；企业侧合并 applicant、owner-operator、brand 和 subsidiary，另从 510(k) PDF 重建 predicate lineage。

这与 MedRadar 当前“事件上没有 matched alias、置信度和规则版本”的缺陷直接对应。可独立采用：原始证据链接、匹配规则与置信度、带证据的 predicate 边、源文本与生成摘要分离。产品页面明确仍为 pre-launch，界面为 illustrative，未提供实体解析或预警准确率，不能当成已验证平台。

## 9. CMOP — REJECT

公开页面宣传 15+ 来源、24 小时采集、语义搜索、AI 引用回答和竞争对手自动解析，但没有给出可复核基准。 unnamed testimonials、“not hallucinations”、99.9% uptime 和安全合规口号都不是科研评价。“Pending”监管状态也未定义，不能理解为获得 FDA 保密在审信息。

通用“生成回答必须带引用”原则可以保留，但本页不提供足以进入 PHOENIX 模型或采集管线的独特方法，且实时监控超出本轮范围。

## 10. NextDevice — ADAPT

产品把产品、销售、研发、投资分开，并对产品分类、技术代际、医疗服务项目、适应症、热门赛道、性能特色和中标信息进行标准化。旧 `medicube.cn` 地址无法访问，当前官方 `pharmcube.com` 页面可访问。

技术代际与生命周期分层值得独立实现，但必须为标签记录版本和当时可知性，不能把当前分类体系回填成历史特征。公开报告展示的是描述性注册/中标分析，不是预测验证。

## 11. GBI DEVINT — STUDY_ONLY

公开页面覆盖研发、临床、注册、准入、招投标和商业化，适合作为生命周期展示对标。AI 数据治理、可追溯和竞争分析没有公开质量指标或算法细节，未找到可复现的预测评价，因此不做方法集成。

## 12. DevicePro — ADAPT

AI+人工进行产品/企业归一、跨库链接和标签化是值得借鉴的数据治理方式，但必须保存匹配规则、审核者和源记录。

同一公开页面同时出现“12W+ 产品、7.8W 企业”和“285W+ 产品、11W+ 公司/机构”，注册记录也出现 130W+ 与 143W+ 两种数字，未给出可统一口径。这些数字不作为 MedRadar 基准，反而说明必须建立带日期和分母的覆盖指标字典。

## 13. 众成医械大数据 — STUDY_ONLY

公开资料包括 MDCLOUD、MDCER 和 MDBIDS，标讯结构可区分项目、招标方、中标方、金额、产品线和标识。公开报告主要是描述性采购分析，没有预测评价。

MedRadar 已有 USAspending 因无法重建首次公开时间而排除出历史增益声明，众成同样没有公开解决这一时钟问题。新增采购源之前应先补齐首次公开时间和独立覆盖核查；中标金额不能当企业收入或研发投入。
