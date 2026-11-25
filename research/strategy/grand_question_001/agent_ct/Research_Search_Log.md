# MedRadar GRAND QUESTION-001：调查记录与剩余证据缺口

> **意见来源：Agent CT。** 本文为 Agent CT 于 2026-11-14 提交的独立科研战略意见，供比较、质疑与讨论；不代表 MedRadar 已采纳的正式路线、已验证的新发现或其他 Agent 的共识。

日期：2026-11-14（伦敦）。本文件记录调查结构、代表性真实查询与影响决策的核验；不是完整搜索引擎流水，也不是PRISMA计数表。搜索未发现不等于不存在。

## 1. 覆盖矩阵

| 调查领域 | 代表性真实查询或检索主题 | 进入核心索引的来源 | 影响 |
|---|---|---|---|
| NLP for Scientific Discovery | scientific discovery NLP benchmark；Unsupervised word embeddings capture latent knowledge | R02/R03/R09 | 历史文本预测和商业潜力已有直接先例 |
| Scientific Information Extraction | scientific information extraction SciER SciREX SciERC | R10–R12/R24/R25 | 新行业和LLM不等于新任务 |
| Science of Science | science of science Fortunato 2018；SciSciNet | R01/R06/R31 | 科学演化与数据连接研究成熟 |
| Scientometrics | NPL v NLP；Measuring technological novelty | R07/R08 | 相似、引用、创新构念不相同 |
| Technology Forecasting / Early Signal | Learning on knowledge graph dynamics；Measuring the Commercial Potential of Science | R03/R09 | 学术影响/商业化代理不能直接转成产品突破 |
| Innovation Diffusion | patent publication innovation diffusion；organization links knowledge flows | R04–R06/R09 | 传播研究需独立采用标签与分母 |
| Technology Evolution | medical devices predicate drift；predicate creep | R19–R21 | 跨代漂移已被直接研究 |
| Temporal Knowledge Graphs | temporal knowledge graph forecasting benchmark TGB 2 evaluation leakage | R15/R16 | 时间图与强简单基线已有标准 |
| Cross-document Entity Resolution | temporal corporate entity linking benchmark acquisition；TempEL；CorpFam | R11/R13/R14 | 公司家族与same-entity必须区分 |
| Research-to-Product Translation | medical device patent publication translation linkage | R04–R09/R27 | 跨源链并非空白，产品级ground truth困难 |
| Biomedical Innovation | Innovation under regulatory uncertainty；De Novo innovation competition | R26–R28 | 监管进入与先行者已有强近邻 |
| Medical Device Regulatory Science | Scaling medical device regulatory science using large language models | R19–R29 | 直接竞争者显著压缩宽泛创新空间 |
| Patent and Publication Analytics | patent in-text references scientific publications；patent text novelty Arts | R05/R07/R08 | 复用已有开放链接，勿重造全部数据工程 |
| Time-aware Machine Learning | leakage reproducibility crisis；WILDS；time-aware entity linking | R13/R15–R17 | 只展示随机切分问题不够新 |
| 拓展：测量与公开证据 | medical device evidence inheritance/renewal/cumulative；public availability | R24/R29/D02–D06 | 区分公开记录与实际发生/验证充分性 |
| 拓展：证据核验 | SciFact；FActScore；device version evidence | R18/R30 | 版本/日期/人群条件可能是窄任务空间 |
| 拓展：标准化与互操作 | medical devices standards network diffusion；FDA Recognized Consensus Standards | D07 | 标准目录开放不代表实施能力/全文开放 |

## 2. 对最重要先验答案的反驳证据

- “跨源知识链是新领域”：R04–R09已覆盖论文—专利连接、语义与引用差异、商业潜力预测和开放数据基座。
- “监管谱系变化没人测过”：R19–R21已直接研究文本比较、predicate creep和AI任务变化。
- “可以用GNN预测召回”：R22/R23已有大样本关联与深度预测。
- “LLM自动抽监管特征就是机会”：R24已有验证实践、MDR编码、技术修改及上市前后关联。
- “企业母子关系有新benchmark空间”：R14已有静态corporate-family benchmark；C03必须新增有效期、证据可得期、unknown和自然时间变化。
- “新产品码代表无人研究的创新扩散”：R26–R28已有监管路径、先行者、类别复用工作。
- “摘要没验证就是没有验证”：R29与R24均要求区分公开证据和实际活动，不能重演已知测量错误。

## 3. 本轮实际核查深度

仓库：读取main完整树、实时PR元数据、SCIENCE-001结果和时间报告、SCIENCE-002结果/数据卡、002R findings/entity/statistical review、论文专利源状态、Evidence Core与E1b。

关键论文：R19/R20的原文方法与讨论；R24的原文Results/Methods片段；R27原文；R29原文；ACL/NeurIPS正式资源条目；R08公开摘要、附录与参考文献；其余逐项见文献索引。

关键代码：实际读取jjfenglab/LLM-FDA-device的LICENSE、目录树与以下三个文件（未执行）：

- `scripts/analysis_pre_post_associations/extract_all_device_features.py`
- `scripts/analysis_validation/survey_validation_trends_all_devices.py`
- `scripts/utils/extract_primary_predicate.py`

由此确认前作已有多维技术差异和验证布尔属性；未在这些schema中见到维度级证据指向、明确研究复用和完整多代配对任务，但这**不证明**其他文件/补充材料/后续论文不存在。

CorpFam：读取作者README、标签/数据构建、许可与保守子集说明；arXiv正文访问失败，所以其性能只标为作者报告，未独立证实。

数据：核到FDA的发布节奏、下载与产品码/标准说明，CT.gov的Record History与AACT路径，OpenAlex现行访问/CC0说明，SEC fair access，Reliance数据许可，USPTO账户/key条件。没有申请凭证、没有批量下载、没有重新运行实验。

## 4. 没有完成的工作与对结论的影响

1. 未进行Scopus/Web of Science订阅库的完整引文导出和去重；不能认定无同题研究。
2. 若正式立项，仍需阅读全文与补充材料、追踪R19–R24的引用/后续研究，并具体对照任务、标签和统计设计。
3. 没有新数据试点，所以C01是否能稳定标注、C03日期gold覆盖、C02时间界限是否有信息均未知。
4. 没有本机GPU实测，资源预算是规划；没有独立读者承诺。
5. 没有检查全部原始许可/第三方附件，不能承诺所有raw文档统一再许可。
6. 搜索中出现的二手解读、非相关命中和未核元数据的论文，未作为关键新颖性依据。

所有候选因此保留Novelty not established。最终推荐是有证据约束的研究投资决定，不是已发表成果、优先权认证或新实验结论。
