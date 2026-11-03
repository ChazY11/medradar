# S-028 文献综述 — 关系结构能否带来增量信息？

**研究**：S-028 *Relational Early Signals in Medical Technology Development: A Temporal Network Study*
**分支**：`research/s028-temporal-graph-early-signal`｜**作者**：`literature-verifier`（独立文献核验）
**检索与核验日期**：2026-11-04（Asia/Shanghai）
**配套文件**：`research/studies/graph_early_signal_s028/artifacts/literature_refs.json`（45 条，逐条含核验状态与所抓取 URL；其中 R45 为全文核验）；**更正记录**：`LITERATURE_CORRECTION_NOTE.md`（S-028-CORRECTION-1）

> 写作规则：关于某篇论文的陈述必须能在 `literature_refs.json` 按 [Rxx] 追溯；只核到题录者仅作题录级陈述并在 §10 标 †；未核实的字段（会议归属、出版年）不写成确定事实。

---

## §0 检索与核验方法

检索于 2026-11-04 完成，核验只用一手/近一手记录：**arXiv 官方 API**与 abs 页（标题、完整作者、摘要、`arxiv:comment` 中的会议、`journal_ref`、DOI）；**Crossref REST API**（DOI 注册记录：按 `filter=doi:` 批量解析，或按题名 `query.bibliographic=` 反查）；**出版社页面**（ACM DL 的 R43、Simon & Schuster 的 R20）；**NBER 官方 working paper 页 + NBER 托管全文 PDF**（R45，2026-11-04 补正时新增；该条以官方页、Crossref DOI 记录与 67 页全文为准）。**OpenAlex** 仅用于发现（含机构 ROR 过滤的"耶鲁"排查），不作为核验依据。检索主线：`temporal graph neural network`、`dynamic graph representation learning`、`heterogeneous graph neural network`、`link prediction evaluation negative sampling`、`temporal link prediction survey`、`technology diffusion networks`、`innovation networks co-patent alliance`、`scientific knowledge graph`、`weak signal early warning`、`data leakage backtest overfitting`、`rare events AUPRC calibration`。

**结果分布。** 45 条全部标识已核对到实抓记录：`verified_primary` 45、`verified_secondary` 0、`unverified` 0。其中 **1 条读到全文（R45，67 页 NBER PDF）**、23 条读摘要（正文实质陈述转述摘要原文）、21 条仅题录（Crossref 对 JSTOR/ACM/OUP/Wiley 普遍无摘要），仅作题录级陈述并标 †。10 条的**会议归属未核验**（R01、R02、R04、R06、R10、R12、R17、R18、R35、R44）：arXiv 记录无 venue 字段，而 dblp 返回反爬页、OpenReview 端点跨域重定向、Semantic Scholar 返回 429——故一律写"arXiv 预印本"，**不写** ICLR/WSDM/ESWC 等未证实归属。1 条出版年未核验（R20：出版社页面确认题名、作者、版次、ISBN，但片段未显示 2003 年）。

**一个必须写下的教训：我记忆中的 DOI 有六处是错的。**

| 我以为 | 实际 | 处理 |
|---|---|---|
| 1812.09430 = DyRep | 是 **DySAT**（DyRep 是 1803.04051） | 拆为 R04 / R06 |
| 10.1093/rfs/hhaa009 = Kelly, Pruitt & Su | 是 **Gu, Kelly & Xiu (2020)** | 改写 §8（且该文无关系图） |
| 10.2307/2393986 = Powell et al. | 是 Adler & Borys | 反查得 10.2307/2393988（R25） |
| 10.1257/0022051043004577 = Keller | 是 Harrison & List | 反查得 10.1257/0022051042177685（R22） |
| 10.1287/orsc.1070.0297 = Fleming et al. | 末位数字错 | 应为 …0289（R26） |
| 10.1007/s10618-014-0368-8 = Yang et al. | 是 Henelius 等；且期刊为 **KAIS 非 DMKD** | 反查得 10.1007/s10115-014-0789-0（R15） |

每一条都"读起来很顺"，正是综述最典型的污染源。**因此宁可少一条，也不补一条。**

**局限。**（a）无 Web of Science / Scopus / Google Scholar，故为定向检索而非系统综述，知名文献偏置明显；（b）21 条只能题录级引用；（c）10 条会议归属留白；（d）未覆盖非英文文献与学位论文，工作论文涉两处（R27 的 NBER 版本、R45 的 NBER 全文）；（e）文献中系统性缺少"图结构无增量信息"的负结果——这正是本研究要自己回答的问题（§9）；（f）**"已验证"的口径**：原 44 条的 `verified_primary` 只表示"书目身份已对上实抓记录"，不表示读过全文或方法；0/44 读过全文（R45 是本轮唯一全文核验条目，见 R45 的 `method_level_claims`）。因此本综述只允许"在本文检索范围内未发现 X"，不允许"文献中不存在 X"；§8.1 的旧结论正是把前者写成了后者（S-028-CORRECTION-1）。

**§0.4 更正记录（S-028-CORRECTION-1，2026-11-04）。** 本轮补正推翻了 §8.1 的旧结论"耶鲁金融关系网络论文不存在"。真实工作为 **Clayton & Coppola (2026), *The Optimal Use of AI in Financial Regulation*, NBER WP 35227, DOI 10.3386/w35227**（May 2026；67 页 NBER 全文，含 Online Appendix），其中含一个显式声明**保留 degree distributions** 的 "Shuffled edges" 消融（Figure 6）。原文错误、成因、一手证据、方法级区分与对 S-028 论证的影响，逐条记录在 **`LITERATURE_CORRECTION_NOTE.md`**；本文件采用原位标注，不删除历史。要点：(i) 存在性主张撤回；(ii) "打乱边/删结构在金融关系网络无先例"的推论撤回，[R45] 即最近先例；(iii) 但该文的 shuffle 是**单次消融**，无零分布/分位数/p 值/种子数，不保时序，其"保度"的具体实现算法未说明，故 S-028 的"重复约束随机化 + 配对 ΔAP/MDE"仍属方法扩展，不能写成"使用了同一方法"；(iv) "44 条全部核验"按上段 (f) 收紧为"书目身份核验；原 44 条中 0 条读过全文"。

---

## §1 时序图与动态异构图

TGAT 用自注意力配合基于 Bochner 定理的**功能性时间编码**，把邻居聚合变成"时间-拓扑"联合聚合，可对训练期未见过的新节点做归纳推断 [R01]。TGN 把图视为**带时间戳的事件序列**，用记忆模块加图算子处理，并指出若干已有动态图模型是其框架特例 [R02]。EvolveGCN 反过来用 RNN **演化 GCN 参数**，不依赖节点嵌入，适配节点集合大幅变动的情形 [R03]。DySAT 在"结构"与"时间"两维分别做自注意力，其链路预测实验包含**二部评分网络** [R04]——与 S-028 的公司—技术二部形态最接近；JODIE 同样处理二部交互网络，学嵌入**轨迹**并用投影算子估计未来嵌入，提出保持时间一致的 t-Batch [R05]；DyRep 用时间尺度相关的多元点过程刻画"通信"与"关联"两类过程 [R06]。

**但基准证据正在给这条主线降温，这对 S-028 是决定性的。** TGB 报告同一批模型跨数据集差异极大，且在动态节点属性预测上**简单方法常优于时序图模型** [R07]；TGB 2.0 自述三点：边类型信息关键、简单启发式常与复杂方法相当、多数方法在最大数据集上跑不动 [R08]；DyGLib 在统一协议后报告**部分基线结果与此前文献不一致**，归因于实现差异 [R09]；GraphMixer 仅用 MLP + 邻居均值池化即取得强性能 [R10]。

**异质图三条基础件**：HAN 的"节点级 + 元路径级"分层注意力 [R11]、R-GCN 的关系相关多关系消息传递 [R12]、HGT 的类型相关注意力 + **相对时间编码**（1.79 亿节点、20 亿边学术图，作者报告较基线提升 9%–21%）[R13]。

**对 S-028 的读法**：公司—技术天然二部、异质、"节点集合随时间新增"，R01/R03/R04/R13 技术上适配；但 R07–R10 四条独立证据同指"复杂架构收益不稳、简单基线很强"，这为"GNN 可选、基线与结构特征先行"提供了文献依据，而非仅凭算力的妥协。

---

## §2 链路预测与时间链路预测（含评估陷阱）

链路预测的经典表述见 [R14]†；启发式各有强假设，SEAL 用 γ-衰减理论说明其可由**局部子图**近似，进而用 GNN 学"启发式" [R16]；评估实践本身有专门检讨 [R15]†，时间链路预测亦有综述 [R19]†。

**最该记住的是"数据视角"的再评估**：它把驱动力拆为局部结构邻近、全局结构邻近与特征邻近，并给出两个关系——全局结构邻近**只在局部结构邻近不足时**显效；特征邻近与结构邻近可**不相容**，在特征邻近主导的边上面向链路预测的 GNN 一致地更差 [R17]。这几乎就是 S-028 的零假设：若信号主要活在**节点特征**（公司规模、赛道活跃度、历史事件率）里，图卷积的边际增益本就应接近零——不是模型没调好，而是数据结构决定。

**负采样不是细节**：采样策略显著改变结论，且最优策略**依数据集而变**（两个基准上结论相反）[R18]。对 S-028 的直接含义：负样本须来自"τ 时刻真实可观测的候选集"，否则评估基率与部署基率不同，AP 与 precision@k 都会失真。

**评估陷阱清单**（综合 R07/R08/R09/R17/R18）：① 切分必须按时间，不能随机；② 负样本须与评估期同分布且当时可观测；③ 频率、持久性等简单启发式必须作基线（R07/R08 均报告它们"意外地强"）；④ 跨数据集结论不可迁移，别处的成功不能当先验；⑤ 实现差异会造成"文献结论"级差异 [R09]，须报告种子数与方差；⑥ 超参与阈值不得在测试期选择（同源于 §6 的过拟合）。

---

## §3 技术扩散与创新网络

**宏观结论：慢、不自动、受本地条件约束。** Rogers 的框架是教科书起点 [R20]†（出版年未核验）。Comin & Hobijn 用 15 项技术、166 个国家、约两个世纪的数据，作者报告**平均在发明后 45 年才被采纳**，跨国采纳差异**至少解释 25% 的人均收入差距**（作者自述）[R23]；Keller 的摘要在明写："没有迹象表明国际扩散是必然或自动的，相反，本国的技术投入是必要的" [R22]。Jaffe 等以专利引用证据研究知识溢出的**地理局部化** [R21]†。

**医疗器械这一支的关键差异**：卫生政策研究把**融资安排**视为核心机制之一 [R24]†。这对 S-028 是硬约束——MedRadar 看到的是**申报行为**，看不到支付、报销、采购与临床采纳；因此本研究语境的"扩散"只能是**公开申报率的扩散**，任何"技术扩散"措辞都须加此限定。

**创新网络：关系是渠道，不是属性。** Powell 等研究生物技术企业间合作网络与"创新所在" [R25]†；Fleming 等讨论发明人网络的小世界结构与区域创新 [R26]†；Bloom 等用**技术邻近度**识别技术溢出与产品市场竞争，是"在企业—技术空间构造企业间关系"的代表作 [R27]†。这一支的边是**合作、引用或技术相似性**，是资源与信息流动的**渠道**：删一条边 = 切断一条传导路径。S-028 的边是"某公司某赛道有过一次监管事件"，是**归属/属性**：删掉改变的是"这个格子有没有历史"。两者都叫网络，但**零模型解释完全不同**（§8.3）；把"网络位置→创新绩效"直接搬成"网络位置→首次申报"是本领域最易犯的类比错误。

---

## §4 科学知识图谱

OpenAlex 作为 MAG 的开放替代，自述覆盖 2.09 亿著作、20.13 亿消歧作者、12.4 万出版方、10.9 万机构、6.5 万 Wikidata 概念，以 GUI、全量 dump 与 REST API 三种方式开放（均为作者自述）[R28]；MAG 构建说明见 [R29]†；异质图模型在开放学术图上的可行性由 HGT 的规模间接支持 [R13]。

对 S-028 的价值不在"用 KG 预测"，而在三点工程提醒：（a）**技术分类体系与实体解析本身就是 KG 构建问题**，节点/边类型与时间戳应是一等公民而非事后补的字段；（b）KG 的边是**观测**不是结果变量，把观测边同时用作特征与标签正是 §6 的泄漏；（c）覆盖率缺口会变成特征误差，且该误差与"公司规模"相关（大公司更易被正确解析），从而与结果相关。这三点都不是换模型能解决的，属测量层面问题。

---

## §5 早期信号检测

"early signal / weak signal"在三个互不相通的传统里含义不同，混用会导致错误的方法迁移。① **战略管理**：Ansoff 的"弱信号"指信息不完整、尚不足以行动时对战略突袭的早期响应 [R30]†——这是决策语境概念，没有对应统计量。② **复杂系统/生态学**：Scheffer 等提出临界转变前可能存在可检测的早期预警信号 [R31]†；Dakos 等系统比较了时间序列上的多种预警指标检测方法 [R32]†。③ **文献计量**：CiteSpace II 以文献网络检测并可视化"新兴趋势"与"瞬态模式" [R33]†——描述性主题突现检测，非概率预测，无虚警率概念。

**对 S-028 的判断**：第 ② 支的**统计量不可借用**——其前提是较长、近等间隔、噪声结构可分辨的序列，而本研究是稀疏计数（仓库审计约 0.2 事件/单元-月），强套临界慢化类指标只会制造噪声；能借的只有其**评估思想**——在提前期上评估、显式以虚警率为代价。第 ③ 支可借"新兴"的操作化定义，但须补概率语义。故本研究的 early signal 应明确定义为：**在 τ 时刻可得信息下，对 (τ, τ+12m] 内首次监管活动事件的排序能力**；它不是临界转变，也不是主题突现，借用后两者词汇时须标注为隐喻。

---

## §6 时间感知评估与数据泄漏

泄漏的经典形式化见 Kaufman 等（训练期不可得信息进入，并给出检测与规避）[R34]†。规模化证据来自 Kapoor & Narayanan：称在 17 个领域、329 篇论文发现因泄漏导致的复现失败，提出 8 类泄漏分类，并以内战预测为例报告——所有声称"复杂 ML 优于逻辑回归"的论文均因泄漏而无法复现，复杂模型并不实质优于数十年前的逻辑回归（作者自述）[R35]。这是"baselines before models"的外部支撑，也最难反驳。多次尝试的选择偏差由回测过拟合概率（PBO）刻画 [R36]†：在大量策略/模型/窗口组合中择优，样本内最优者的样本外表现会系统性低于预期。S-028 的组合空间（多窗口 × 多模型 × 多特征集 × 多阈值）足以产生这种偏差，故窗口与主指标必须**先注册后看结果**（仓库 `PREDICTION_PROTOCOL.md`、`HYPOTHESES.md` 的既有约束）。

**可落地的四条时间纪律**（对应 R34/R35 的泄漏类型）：① 特征须 `event_date <= τ` **且** `available_at <= τ`（金融另加 `filed <= τ`）；② 标签窗 `(τ, τ+12m]`，故训练集须在 `cutoff + 12m <= origin` 处 **purge**，滚动起点之间不得共享标签窗口；③ `event_date` / `published_at` / `first_seen_at` / `available_at` 四者永不同义替换，混同后两者即典型 temporal leakage；④ 任何事后选择的窗口、阈值、特征集都要报告搜索空间大小（PBO 思想），否则 ΔAP 不可解释。

---

## §7 稀有事件预测与 AUPRC 评估

**为何不以 ROC-AUC 为主指标**：Saito & Rehmsmeier 的标题即结论——不平衡数据上 PR 图比 ROC 图提供更多信息 [R37]†；两者有形式化关系，但 PR 空间的插值需专门处理，不能照搬 ROC 做法 [R38]†。S-028 主口径基率为 **1.019%**（H=4q、qualifying、418 正例），material 敏感性口径为 1.227%（`DATA_FEASIBILITY.md` §3）；此基率下 ROC-AUC 会被大量真负例抬高却与操作价值脱钩——这是基于 R37 的推论，非其原文结论。稀有事件下逻辑回归的估计偏差与修正见 King & Zeng [R41]†：在单窗 **25–27** 个正例（pooled 78）上，系数与概率都不稳，须用配对 ΔAP、企业聚类 bootstrap 与 MDE 报告，而非单点数值。严格适当评分规则的性质见 Gneiting & Raftery [R39]†；校准被 Van Calster 等点名为"阿喀琉斯之踵"——长期被忽视，而"校准不佳的算法可能误导甚至有害"，且复杂度须与可用样本量平衡（摘要原文）[R40]。

**指标集合的直接结论**：主指标 AP（=AUPRC，配对 ΔAP）；次要 precision@k（k 取候选集的预设比例）、Brier、校准斜率/截距；AUC 仅作参考且须与基率同报；所有比较在同一批行上配对，且不得跨面板比较原始 AP（基率不同）。在约 1% 基率、单窗 25–27 正例下，10 分箱 ECE 几乎不可估（多数箱 0 正例），应改分位数分箱并要求每箱 ≥50 正例，否则标"不可估"；协议已把 `ece`（10 bins）列为辅助指标（`EXPERIMENT_PROTOCOL.md` §6），建议同时标注其不可估性。

---

## §8 金融关系网络的方法论启发（含对"耶鲁论文"的核验结论；**已更正：S-028-CORRECTION-1**）

### 8.1 核验结论【**已更正：S-028-CORRECTION-1**】

> **原文（错误，保留记录）：** 标题"核验结论：找不到这样一篇论文"；正文"**没有任何一篇同时满足'耶鲁 + 金融实体动态关系图 + 边置换或删结构对照'**"；以及"不能引一个并不存在的'方法先例'"。原文位置：本文件 §8.1（更正前 L105–L115）与 `PHASE_REPORT_ZH.md` §3（更正前 L128–L136）；完整原文、错误成因与一手证据见 **`LITERATURE_CORRECTION_NOTE.md` §2–§4**。

**更正后的事实。** 该文存在：**Christopher Clayton & Antonio Coppola, *The Optimal Use of AI in Financial Regulation*, NBER Working Paper 35227, May 2026, DOI 10.3386/w35227**（NBER 官方页与 67 页全文 PDF，2026-11-04 抓取；PDF 第 2 页载 **JEL No. C4, G1, G2**；第 1 页脚注说明此前以 *"Financial Regulation and AI: A Faustian Bargain?"* 为题流传）。Clayton 为 Yale University / NBER（论文第 2 页、NBER 作者页、其个人主页均载 Yale / Yale School of Management）；Coppola 的现职单位在 PDF（Stanford）与 NBER/OpenAlex（Chicago）之间不一致，记录为未核实，但"该文有耶鲁作者"这一条由论文自身与 NBER 页面即可确证。它不是"不存在的先例"：它建的是**投资者—资产二部持仓图**（节点=非银金融中介与证券，边=持仓，含市值与数量），用 graph transformer 做**季度横截面 + 逐年 walk-forward** 的持仓变动预测，并在 Figure 6 的消融中报告一个 **"Shuffled edges"（打乱边）** 对照；图注原文为 *"randomly permutes edge indices to destroy network topology while preserving node features and degree distributions"*（printed p.19），正文称该对照把 walk-forward R² 由 **6.6% 降到 2.3%**（§3.2, printed p.20）。详见 `LITERATURE_CORRECTION_NOTE.md` §5–§6。

**但"存在"≠"用了与 S-028 相同的随机化方法"。**（a）该文是**单次消融**：每个 walk-forward 窗口重训一次、报一个 R² 点；全文**没有**随机化分布、分位数、p 值，也没有报告种子数（全文检索 "seed" 0 次）。（b）**保度机制未说明**：只声明保留 "degree distributions"，未给出 configuration-model / stub-matching / 边交换等具体算法（Appendix B 亦未说明），故实现层面的"保度交换"标为 **UNVERIFIED**。（c）该文不保活跃度/时间分布，也不做按赛道日期池的分块约束；其边是**持仓**、单位是投资者—资产交易量变化，S-028 的边是"公司在某赛道有过一次监管事件"、目标是稀有首次事件。故 S-028 的"重复约束随机化 + 零分布 + 配对 ΔAP/MDE"设计仍是**方法扩展**，不是对 w35227 的复制。

**旧检索中列出的三篇"最接近"工作仍然各自只满足前提的一部分**（保留供追溯；它们不再是"最接近"）：

- **[R42] Gu, Kelly & Xiu (2020), RFS 33:2223–2273**：真正的"耶鲁金融机器学习"论文——Crossref 作者机构字段载明 Bryan Kelly 隶属 Yale University（兼 AQR、NBER）。但它做的是**用机器学习对公司特征做资产定价预测**：没有关系图、没有动态图学习、没有边置换对照。"耶鲁 + 金融 + ML"这一半是真的，"关系图 + 打乱链接"那一半不在其中。
- **[R43] Niu, Lu, Dolphin, Potì & Dong (2024), ICAIF '24, 564–572**：方法论主张上最接近——摘要指出既有方法把关系图评估**绑在下游模型性能上**"导致混乱与不精确"，故提出**不依赖下游任务**的关系图评估，并发布基于 S&P 500 的 SPNews 数据集。但（a）五位作者单位均为 University College Dublin，**与耶鲁无关**；（b）装置是图级解释性任务，**不是打乱链接或删结构**。
- **[R44] Xu 等 (2021), HIST**：把"股票—概念"共享信息建图、并用预定义与隐藏概念的金融图模型，摘要批评此前工作假设股票—概念连接是静态的。它是"金融图模型会做图消融"的例子，但**非耶鲁、无打乱链接对照**，图本质是成员矩阵。

**真正的最近邻是 [R45] Clayton & Coppola (2026)**：它同时满足"耶鲁作者 + 金融实体关系图 + 打乱边对照"，但**不满足** S-028 的方法要件（重复随机化、零分布、保时序、ΔAP/MDE）。

**正确表述（更正后）**：打乱边/删结构的零模型传统确实源自**网络科学的零模型与约束随机化**；但"在金融关系网络上做保度打乱并观察性能坍塌"已有金融学先例 [R45]（NBER working paper，未经同行评审）。S-028 应引其**应用先例**（拓扑在金融关系中承载信息）并引网络科学文献说明**零模型方法**；不可再写"不存在先例"。S-028 的差异化主张须写成检索范围内的表述："**在本文所检索的文献中**，未见将**保度 + 保活跃度 + 保时间**的分块约束随机化与**配对 ΔAP / 零分布分位 / MDE 判据**同时用于**稀疏、稀有事件的二部监管事件图**的研究"——是"未检索到"，不是"不存在"。把"检索未命中"写成"文献中不存在"，正是 §0 所记六处 DOI 记忆错误的结构同类项（本次错误的成因已记录在 `LITERATURE_CORRECTION_NOTE.md` §3）。

### 8.2 许可迁移什么

① **对照设计的逻辑**：模型 vs 非图基线 vs 结构被破坏的对照，三者并列报告 Δ，而非只报相对基线的提升（[R45] 的 Figure 6 即此逻辑的金融实例：基线 / 去 FSI / 去 attention / 单层 / 打乱边五种设定并列报 walk-forward R²）。② **把"图是否有效"与"模型是否准"分开**（R43 的核心主张）：S-028 应先回答"公司—技术二部图的关联结构是否超出保度零模型"，再回答"它是否提升 AP"；混在一起会把"图有结构"误读为"图有预测力"。③ **评估纪律**：purge/embargo、PBO 式搜索空间披露 [R35][R36]、以及"简单基线可能极强"的预期 [R07][R08]——与领域无关，可直接迁移。

### 8.3 不许可迁移什么

① **数据形态**：金融关系图常被笼统描述为"稠密、近似全覆盖、高频（全部上市公司 × 日频收益/持仓/供应链），缺失可当噪声"——但最近的同类先例 [R45] 并不支持这一笼统化：其持仓图为**季度频**、每季度约 **231 万条边**、**二部图密度仅 0.406%**、只覆盖非银中介（见 JSON R45 与 PDF Table 1）；与本研究的二部图观测覆盖率 16.6% 相比并不更稠密，只是绝对边数更大。故"稠密"只能指**信息在边上足够充分**，不能默认节点覆盖率近全覆盖，引用时必须给出定义。S-028 是**极稀疏二部事件图**：全期 51×38=1,938 个可能对中仅 322 对（16.6%）被观测到，单个 12 个月快照只有 135–148 条边、51 节点投影图密度 0.093–0.101（`DATA_FEASIBILITY.md` §4；注意这是投影图密度，不是二部图密度），事件密度约 0.2 次/单元-月。此密度下"打乱边"会把图打散成近乎全空的图，功效极低；必须用**保度**约束随机化才可能得到有意义的零分布——这也是本研究 `GRAPH_SCHEMA.md` §8 已冻结的设计（块级保度交换 + 每赛道日期池 + R=20 种子）。② **结果变量**：金融侧是连续、稠密、同期的收益/波动/违约，指标（Sharpe、IC、R²）在 S-028 完全不适用；S-028 是**稀有、离散、右删失的首次事件**（12 个月窗、主口径基率 1.019%），只能走 AP / precision@k / 校准（§7）。③ **因果语义**：金融的边对应可解释经济渠道（供应链、共同分析师覆盖、行业），删边 = 切断渠道，"删边掉性能"有经济学解释；S-028 的边"该申请人在这条赛道申报过"与标签**同源**，主要风险是**重言与泄漏**，而非渠道缺失。这条最致命：金融里"图有用"是好消息，MedRadar 里"图有用"首先得排除"图就是标签的影子"。④ **零模型的问题不同**：金融打乱边问"经济渠道是否承载信息"；S-028 若保持度、活跃度与时间分布，剩下的只是"**边的排列顺序**是否承载信息"——明显更弱，必须在论文里写清，否则读者会把"显著"误读为"关系有信息"。（[R45] 的 shuffle 只声明保 degree distributions，未声明保时间/活跃度，也未构造零分布；S-028 的约束更强、推断更正式，两者不可混同——此处"S-028 的约束"指修正后的 N1/N2 设计，原 Phase 0–3 实现被同一轮修正的随机化审计判定未真正保度，见 `RANDOMISATION_DEFECT_ANALYSIS.md`。另：R45 的边是持仓，"删边=改变谁持有谁"确有经济渠道含义；S-028 的边与标签同源，④ 的核心风险因此仍然成立。）⑤ **制度语境**：医疗器械首次申报经由 FDA 510(k)/PMA 一类**守门机制**，并有分类、召回、支付与采购制度，扩散受融资与报销驱动 [R24]；金融侧无对应守门人与申报队列。故 S-028 的"首次进入"机制上更接近"制度性事件的时间"，而非"市场参与者逐步采纳"。

---

## §9 本研究的定位与研究空白

**可以声称**：在**预先固定**的 purge/embargo 与起点协议下，量化"关系结构"相对强非图时序基线（频率、持久性、正则化统计模型、梯度提升 + 结构特征）的**增量排序能力**，给出配对 ΔAP 及其 MDE；可在预先声明的窗口上报告 **well-powered negative**——"在这个正例规模上，关系结构的增量小于可分辨的最小效应"。后者是**可发表结果**而非失败：R07/R08/R17 提供了"复杂结构未必有增益"的先例，R35 更说明"看起来的增益常是泄漏"。

**不可以声称**：① **因果机制**——无识别设计，任何"因处于网络中心所以更可能进入"均不成立；② **"更早预警"**——AP 提升不等于提前期优势，匹配虚警率下的提前期检验（仓库 H-C2-4 框架）通过前不能写 earlier warning；③ **GNN 优越性**——单窗 25–27、pooled 78 个正例的规模上，GNN 与提升树/正则化模型的差异远超可分辨范围，R07/R08/R09 亦说明该差距在不同数据上不稳；④ **跨域外推**——金融图模型的成功不构成对医械二部事件图的先验（§8.3）；⑤ **意图与内部 R&D**——语料只能看到公开申报行为，不因引入图模型而改变。

**方法空白（本文献综述最有价值的部分）：**
- **B1｜保度保时序零模型在医械二部事件图上未见先例（检索范围内）。** 文献给出通用随机化思想与 TGB 式评估协议 [R07][R08]；最近的金融先例 [R45] 在持仓图上做了**单次**保度打乱消融（walk-forward R² 6.6%→2.3%），但无零分布/分位数/p 值、不保时序、不报 ΔAP。**在本文检索范围内未见**"公司—技术二部图、按年切片、保度保活跃度保时间、并同时报告图统计与预测 ΔAP"的具体设计（此为检索结论，不是"文献中不存在"）。本研究已在 `GRAPH_SCHEMA.md` §8 与 `EXPERIMENT_PROTOCOL.md` §5 冻结该对照（块级保度交换、每赛道日期池、R=20、报告 ΔAP(real−randomised) 与真实 AP 的分位；原 Phase 0–3 实现未达到该不变量，已由同一轮修正的随机化审计 `RANDOMISATION_DEFECT_ANALYSIS.md` 判定并代之以 N1/N2 修正零模型——故上一句的"更强的约束"指修正版设计），故文献综述不再重复其定义，只指出两点必须写进报告的风险：(i) **问题被弱化**——保持度、活跃度与时间分布之后，零模型所检验的只是"边的排列是否携带信息"，不能升级为"关系是否携带信息"；(ii) **分辨力**——R=20 时所谓 97.5% 分位实际是 20 个次序统计量中的最末一个，单侧最小可达 p 约为 1/21≈0.048，需在报告中说明该分辨力，或提高种子数以支撑更细的尾部判断。
- **B2｜时间负采样在极稀疏二部图上无标准做法。** R18 的结论只在知识图谱上得到；"负样本须来自 τ 时刻可观测候选集"的原则清楚，但如何在 16.6% 覆盖率的稀疏图上构造同分布负样本，文献未答。
- **B3｜异质性不可估。** pooled 78 个正例分散在 51 家企业 × 38 个赛道，按企业/赛道分层后多数单元正例为 0–2；协议要求分层最小 n=10 且正例 ≥5、否则标 `insufficient`（`EXPERIMENT_PROTOCOL.md` §7），故"关系结构对哪类公司有效"本轮多为**不可估**。
- **B4｜低基率下校准几乎不可估** [R40]，概率输出只能作排序分数，不能作决策概率。
- **B5｜分辨率依赖。** 边须在某时间分辨率上定义（月/季/年），而 R07 表明模型排序随任务设定而变；S-028 须固定分辨率并显式说明，跨分辨率比较不可识别。

**一句话定位**：本研究的贡献不在"再加一个 GNN"，而在把"关系结构是否携带增量信息"变成**可被零模型否证、并被 MDE 界定**的问题——在一个稀疏、稀有、点位时间受限的真实监管语料上。按现有证据，最可能的诚实结果是"增量小于可分辨下界"，而这恰恰要求把 MDE、零模型与图有效性检验做对。

---

## §10 参考文献（编号，含核验状态）

**标记**：`P` = `verified_primary`；`F` = 已读全文（仅 R45）；† = 仅题录级（未读摘要）；‡ = 会议归属未核验（arXiv 记录无 venue 字段）。记录类型：`arxiv` / `crossref`（DOI 注册记录）/ `publisher` / `acm` / `nber`。逐条的抓取 URL 与字段标记见 `literature_refs.json`；R45 的方法级核验（保度打乱=已声明、具体算法=UNVERIFIED）见该条目的 `method_level_claims`。

**[R01]** Xu, D., Ruan, C., Korpeoglu, E., Kumar, S., Achan, K. (2020). *Inductive Representation Learning on Temporal Graphs.* arXiv:2002.07962v1. — P, arxiv, ‡
**[R02]** Rossi, E., Chamberlain, B., Frasca, F., Eynard, D., Monti, F., Bronstein, M. (2020). *Temporal Graph Networks for Deep Learning on Dynamic Graphs.* arXiv:2006.10637v3. — P, arxiv, ‡
**[R03]** Pareja, A., Domeniconi, G., Chen, J., Ma, T., Suzumura, T., Kanezashi, H., Kaler, T., Schardl, T. B., Leiserson, C. E. (2019). *EvolveGCN: Evolving Graph Convolutional Networks for Dynamic Graphs.* arXiv:1902.10191v3；AAAI 2020（arXiv comment）. — P, arxiv
**[R04]** Sankar, A., Wu, Y., Gou, L., Zhang, W., Yang, H. (2018). *Dynamic Graph Representation Learning via Self-Attention Networks* (DySAT). arXiv:1812.09430v2. — P, arxiv, ‡
**[R05]** Kumar, S., Zhang, X., Leskovec, J. (2019). *Predicting Dynamic Embedding Trajectory in Temporal Interaction Networks.* KDD 2019；DOI 10.1145/3292500.3330895；arXiv:1908.01207v1. — P, arxiv
**[R06]** Trivedi, R., Farajtabar, M., Biswal, P., Zha, H. (2018). *Representation Learning over Dynamic Graphs* (DyRep). arXiv:1803.04051v2. — P, arxiv, ‡
**[R07]** Huang, S., Poursafaei, F., Danovitch, J., Fey, M., Hu, W., Rossi, E., Leskovec, J., Bronstein, M., Rabusseau, G., Rabbany, R. (2023). *Temporal Graph Benchmark for Machine Learning on Temporal Graphs.* NeurIPS 2023 D&B；arXiv:2307.01026v2. — P, arxiv
**[R08]** Gastinger, J., Huang, S., Galkin, M., Loghmani, E., Parviz, A., Poursafaei, F., Danovitch, J., Rossi, E., Koutis, I., Stuckenschmidt, H., Rabbany, R., Rabusseau, G. (2024). *TGB 2.0: A Benchmark for Learning on Temporal Knowledge Graphs and Heterogeneous Graphs.* NeurIPS 2024 D&B；arXiv:2406.09639v2. — P, arxiv
**[R09]** Yu, L., Sun, L., Du, B., Lv, W. (2023). *Towards Better Dynamic Graph Learning: New Architecture and Unified Library.* NeurIPS 2023；arXiv:2303.13047v3. — P, arxiv
**[R10]** Cong, W., Zhang, S., Kang, J., Yuan, B., Wu, H., Zhou, X., Tong, H., Mahdavi, M. (2023). *Do We Really Need Complicated Model Architectures For Temporal Networks?* arXiv:2302.11636v1. — P, arxiv, ‡
**[R11]** Wang, X., Ji, H., Shi, C., Wang, B., Cui, P., Yu, P., Ye, Y. (2019). *Heterogeneous Graph Attention Network.* WWW 2019（arXiv journal_ref）；arXiv:1903.07293v2. — P, arxiv
**[R12]** Schlichtkrull, M., Kipf, T. N., Bloem, P., van den Berg, R., Titov, I., Welling, M. (2017). *Modeling Relational Data with Graph Convolutional Networks.* arXiv:1703.06103v4. — P, arxiv, ‡
**[R13]** Hu, Z., Dong, Y., Wang, K., Sun, Y. (2020). *Heterogeneous Graph Transformer.* WWW 2020；arXiv:2003.01332v1. — P, arxiv
**[R14]** Liben-Nowell, D., Kleinberg, J. (2007). *The link-prediction problem for social networks.* JASIST 58:1019–1031；DOI 10.1002/asi.20591. — P, crossref, †
**[R15]** Yang, Y., Lichtenwalter, R. N., Chawla, N. V. (2015). *Evaluating link prediction methods.* Knowledge and Information Systems 45:751–782；DOI 10.1007/s10115-014-0789-0. — P, crossref, †
**[R16]** Zhang, M., Chen, Y. (2018). *Link Prediction Based on Graph Neural Networks.* NIPS 2018；arXiv:1802.09691v3. — P, arxiv
**[R17]** Mao, H., Li, J., Shomer, H., Li, B., Fan, W., Ma, Y., Zhao, T., Shah, N., Tang, J. (2023). *Revisiting Link Prediction: A Data Perspective.* arXiv:2310.00793v3. — P, arxiv, ‡
**[R18]** Kotnis, B., Nastase, V. (2017/2018). *Analysis of the Impact of Negative Sampling on Link Prediction in Knowledge Graphs.* arXiv:1708.06816v2. — P, arxiv, ‡
**[R19]** Divakaran, A., Mohan, A. (2020). *Temporal Link Prediction: A Survey.* New Generation Computing 38:213–258；DOI 10.1007/s00354-019-00065-z. — P, crossref, †
**[R20]** Rogers, E. M. (2003). *Diffusion of Innovations*, 5th ed. Simon & Schuster / Free Press；ISBN 9780743222099. — P, publisher, †；**出版年未核验**
**[R21]** Jaffe, A. B., Trajtenberg, M., Henderson, R. (1993). *Geographic Localization of Knowledge Spillovers as Evidenced by Patent Citations.* QJE 108:577–598；DOI 10.2307/2118401. — P, crossref, †
**[R22]** Keller, W. (2004). *International Technology Diffusion.* JEL 42:752–782；DOI 10.1257/0022051042177685. — P, crossref（含摘要）
**[R23]** Comin, D., Hobijn, B. (2010). *An Exploration of Technology Diffusion.* AER 100:2031–2059；DOI 10.1257/aer.100.5.2031. — P, crossref（含摘要）
**[R24]** Cappellaro, G., Ghislandi, S., Anessi-Pessina, E. (2011). *Diffusion of medical technology: The role of financing.* Health Policy 100:51–59；DOI 10.1016/j.healthpol.2010.10.004. — P, crossref, †
**[R25]** Powell, W. W., Koput, K. W., Smith-Doerr, L. (1996). *Interorganizational Collaboration and the Locus of Innovation: Networks of Learning in Biotechnology.* ASQ 41:116–；DOI 10.2307/2393988. — P, crossref, †
**[R26]** Fleming, L., King, C. III, Juda, A. I. (2007). *Small Worlds and Regional Innovation.* Organization Science 18:938–954；DOI 10.1287/orsc.1070.0289. — P, crossref, †
**[R27]** Bloom, N., Schankerman, M., Van Reenen, J. (2013). *Identifying Technology Spillovers and Product Market Rivalry.* Econometrica 81:1347–1393；DOI 10.3982/ECTA9466. — P, crossref, †
**[R28]** Priem, J., Piwowar, H., Orr, R. (2022). *OpenAlex: A fully-open index of scholarly works, authors, venues, institutions, and concepts.* STI 2022；arXiv:2205.01833v2. — P, arxiv
**[R29]** Wang, K., Shen, Z., Huang, C., Wu, C.-H., Dong, Y., Kanakia, A. (2020). *Microsoft Academic Graph: When experts are not enough.* Quantitative Science Studies 1:396–413；DOI 10.1162/qss_a_00021. — P, crossref, †
**[R30]** Ansoff, H. I. (1975). *Managing Strategic Surprise by Response to Weak Signals.* California Management Review 18:21–33；DOI 10.2307/41164635. — P, crossref, †
**[R31]** Scheffer, M., Bascompte, J., Brock, W. A., Brovkin, V., Carpenter, S. R., Dakos, V., Held, H., van Nes, E. H., Rietkerk, M., Sugihara, G. (2009). *Early-warning signals for critical transitions.* Nature 461:53–59；DOI 10.1038/nature08227. — P, crossref, †
**[R32]** Dakos, V., Carpenter, S. R., Brock, W. A., Ellison, A. M., Guttal, V., Ives, A. R., Kéfi, S., Livina, V., Seekell, D. A., van Nes, E. H., Scheffer, M. (2012). *Methods for Detecting Early Warnings of Critical Transitions in Time Series Illustrated Using Simulated Ecological Data.* PLoS ONE 7:e41010；DOI 10.1371/journal.pone.0041010. — P, crossref, †
**[R33]** Chen, C. (2006). *CiteSpace II: Detecting and visualizing emerging trends and transient patterns in scientific literature.* JASIST 57:359–377；DOI 10.1002/asi.20317. — P, crossref, †
**[R34]** Kaufman, S., Rosset, S., Perlich, C., Stitelman, O. (2012). *Leakage in data mining: Formulation, detection, and avoidance.* TKDD 6:1–21；DOI 10.1145/2382577.2382579. — P, crossref, †
**[R35]** Kapoor, S., Narayanan, A. (2022). *Leakage and the Reproducibility Crisis in ML-based Science.* arXiv:2207.07048v1. — P, arxiv, ‡
**[R36]** Bailey, D. H., Borwein, J., López de Prado, M., Zhu, Q. J. (2016). *The probability of backtest overfitting.* Journal of Computational Finance；DOI 10.21314/JCF.2016.322. — P, crossref, †；**卷/期/页未在记录中出现，故不写**
**[R37]** Saito, T., Rehmsmeier, M. (2015). *The Precision-Recall Plot Is More Informative than the ROC Plot When Evaluating Binary Classifiers on Imbalanced Datasets.* PLoS ONE 10:e0118432；DOI 10.1371/journal.pone.0118432. — P, crossref, †
**[R38]** Davis, J., Goadrich, M. (2006). *The relationship between Precision-Recall and ROC curves.* ICML '06, 233–240；DOI 10.1145/1143844.1143874. — P, crossref, †
**[R39]** Gneiting, T., Raftery, A. E. (2007). *Strictly Proper Scoring Rules, Prediction, and Estimation.* JASA 102:359–378；DOI 10.1198/016214506000001437. — P, crossref, †
**[R40]** Van Calster, B., McLernon, D. J., van Smeden, M., Wynants, L., Steyerberg, E. W. (2019). *Calibration: the Achilles heel of predictive analytics.* BMC Medicine 17；DOI 10.1186/s12916-019-1466-7. — P, crossref（含摘要）
**[R41]** King, G., Zeng, L. (2001). *Logistic Regression in Rare Events Data.* Political Analysis 9:137–163；DOI 10.1093/oxfordjournals.pan.a004868. — P, crossref, †
**[R42]** Gu, S., Kelly, B., Xiu, D. (2020). *Empirical Asset Pricing via Machine Learning.* Review of Financial Studies 33:2223–2273；DOI 10.1093/rfs/hhaa009. — P, crossref, †（作者机构字段载明 Kelly 隶属 Yale University）
**[R43]** Niu, Y., Lu, L., Dolphin, R., Potì, V., Dong, R. (2024). *Evaluating Financial Relational Graphs: Interpretation Before Prediction.* ICAIF '24, 564–572；DOI 10.1145/3677052.3698644. — P, acm（含摘要；作者单位 University College Dublin）
**[R44]** Xu, W., Liu, W., Wang, L., Xia, Y., Bian, J., Yin, J., Liu, T.-Y. (2021). *HIST: A Graph-based Framework for Stock Trend Forecasting via Mining Concept-Oriented Shared Information.* arXiv:2110.13716v2. — P, arxiv, ‡
**[R45]** Clayton, C., Coppola, A. (2026). *The Optimal Use of AI in Financial Regulation.* NBER Working Paper 35227, May 2026；DOI 10.3386/w35227；67 页 NBER 全文（含 Online Appendix）。— P（NBER 官方页 + 全文 PDF）, F, crossref, nber。方法级：**"Shuffled edges" 保 degree distributions 的打乱边消融 = 已声明（verified）**；具体保度算法、随机化次数/种子、零分布/分位数/p 值 = **UNVERIFIED**（论文未报告）；见 `LITERATURE_CORRECTION_NOTE.md` §6–§7 与 JSON R45 的 `method_level_claims`。此前以 *"Financial Regulation and AI: A Faustian Bargain?"* 为题流传。

**合计 45 条：`verified_primary` 45 / `verified_secondary` 0 / `unverified` 0；含全文 1 条（R45）、摘要 23 条、仅题录 21 条、会议归属未核验 10 条、出版年未核验 1 条。** 未核验项已在 §0 与本节逐条标明，不进入正文的确定陈述；`verified_primary` 只表示书目身份已对上实抓记录，不表示读过全文（§0 局限 f）。
