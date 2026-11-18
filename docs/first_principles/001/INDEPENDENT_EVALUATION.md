# FIRST PRINCIPLES-001 / 第三阶段 B：独立分类评估

- 评估对象：`refoundation/004`（HEAD 380aa37）中的 `medradar/radar/assessment.py`
  （`ASSESSMENT_VERSION = radar-assessment-2026.11.19`）
- 评估数据：`perf-v2.db` 的 `admission_current` 投影（8,593 条）+ 本轮独立抽取的 120 条
- 评审者：单人（本报告作者）。**这不是独立人类小组，一致性未知。**
- 样本与历史样本的关系：**完全不重叠**。种子 20261118，与 REFOUNDATION-004 的
  `independent-sample-1`（120 条）和 `heldout-sample-1`（80 条）无关；后两者只作为回归对照引用。

## 0. 必须先纠正的一个事实（关于 QA-002）

任务书假设"QA-002 有独立 120 条样本"。**本轮未能找到该样本。** 实际情况：

| 查找位置 | 结果 |
| --- | --- |
| 仓库内（所有分支、所有 worktree） | 无 QA-001/QA-002 样本文件；仅有 `docs/radar/QUALITY_001_ACCEPTANCE.md` 与 REF-004 自己的评估文件 |
| 工作目录 `_launch001/` | `qa_report.txt`（328 行，由 docx 转出）+ `qa_sample.json`（60 条，14 天窗口，含引擎输出）+ `qa_sample.py` |
| QA 报告正文自述的证据目录 `evidence/*.json` | **不存在于本机** |

QA-002 的真实形态是一份**浏览器实测验收报告**（结论 FAIL）：首屏 20 条 + 固定种子随机 10 条人工审查，
17/20 首屏条目明显不相关，外加 500/404/性能等缺陷。它的价值是"用户视角的失败证据"，
不是"120 条带标签的样本"。

**所以本轮另建了独立样本（见第 1 节），并明确标注：它不是 QA-002 的复测。**
唯一存在的 120 条带标签样本是 REFOUNDATION-004 自己的 `independent-sample-1`，
而它由写规则的同一位 Agent 标注（`QUALITY_BEFORE.md` 已如实注明），不能算独立验证。

## 1. 本轮独立样本的构造

种子 `20261118`，分层，共 120 条，全部来自真实账本：

| 层 | 抽取规则 | n | 目的 |
| --- | --- | --- | --- |
| A 默认简报 | 30 天窗口内所有 FEED（21 条**全部**纳入） | 21 | 用户一个月内真正看到的东西必须被评价 |
| B Crossref 非 FEED | 随机 42 | 42 | 检查被拒绝的文献 |
| C PubMed 非 FEED | 随机 32 | 32 | 检查 PubMed 表现（本轮重点） |
| D openFDA | 随机 20（跨年份） | 20 | 检查历史清关是否被正确分级 |
| E 企业官方 | 全部（5 条，取 5） | 5 | 检查"企业官方但主题无关" |

实际的来源分布：Crossref 48、PubMed 44、openFDA 23、Philips 2、Dräger 3。
引擎判定分布：FEED 41、REVIEW 3、EXCLUDED 76。

标注依据：`INTELLIGENCE_STANDARD.md`（本轮独立撰写）。每条标注 `label`、`feed_eligible`、
`priority`、`uncertain`、`note`。6 条标记为"存疑"（只有标题/跨域歧义），在统计中保留并单独列出。

## 2. 结果：二分类（是否应进入默认简报）

把"应进入默认简报"定义为 `DIRECT/TRANSFER + A1/A2/A3`（见标准第 3 节）。

| 指标 | 本轮独立测量 | REFOUNDATION-004 held-out 自报 | 差异 |
| --- | --- | --- | --- |
| 精确率 precision | **0.659**（27/41） | 0.933（28/30） | −0.27 |
| 召回率 recall | **0.730**（27/37） | 0.875（28/32） | −0.15 |
| 特异度 specificity | **0.831**（69/83） | 0.958（46/48） | −0.13 |
| 混淆 | TP 27 / FP 14 / FN 10 / TN 69 | TP 28 / FP 2 / FN 4 / TN 46 | — |

**解释差异的原因（重要，不是"谁对谁错"）**：

1. REF-004 的 held-out 刻意按"每类至少若干条"分层，因此阳性比例高（32/80 = 40%），
   而真实默认简报是全阳性（21/21），真实非 FEED 层几乎全阴——两者的基础率完全不同；
2. 本轮的 openFDA 层是跨年份随机抽取，13 条 1981–2011 年清关被引擎判 FEED，
   在我的标准下应进档案而不进简报，直接构成 13 个假阳性；
3. REF-004 的样本里 openFDA 只有 20 条且**全部标注为阳性**（其报告 per-source 表 20/20），
   等于没有测到"历史清关是否会被错误推送"这一维度。

结论：**"0.93 精确率"是在一个对引擎有利的分层上测出的，不能外推到用户看到的产品。**
本轮独立测量给出 0.66。两者都需更大样本与多名评审确认，但方向明确。

## 3. 结果：五分类一致率

| 本标准标签 | n | 引擎 `monitoring_relevance` 命中 | 一致率 | 主要误判方向 |
| --- | --- | --- | --- | --- |
| DIRECT | 45 | 38 | 0.84 | 3→CLINICAL，4→MEDICAL_UNRELATED |
| TRANSFER | 6 | 1 | **0.17** | 2→DIRECT，3→CLINICAL |
| CLINICAL | 38 | 32 | 0.84 | 2→TRANSFER，3→MEDICAL_UNRELATED |
| MEDICAL_UNRELATED | 20 | 6 | **0.30** | 14→CLINICAL |
| NON_MEDICAL | 11 | 4 | **0.36** | 3→CLINICAL，4→MEDICAL_UNRELATED |

三个可执行的结论：

1. **DIRECT 与 CLINICAL 的分离是可信的**（0.84 / 0.84），这是引擎最成熟的部分，也是 REF-004 最主要的成果。
2. **TRANSFER 基本失效**（1/6）。迁移价值是研发负责人最需要的一类信息（"别人家的技术能不能用在我这里"），
   而系统几乎不产出它。
3. **MEDICAL_UNRELATED 与 NON_MEDICAL 只有 0.30 / 0.36**。这不影响简报（两者都被排除），
   但影响**解释**：当用户问"这条为什么被排除"，系统给出的理由有 2/3 是错的。

## 4. 逐条错误（14 个假阳性 / 10 个假阴性）

### 4.1 假阳性（引擎 FEED，本标准认为不该进简报）

| # | 来源/时间 | 标题 | 原因 |
| --- | --- | --- | --- |
| 1 | PubMed 2026-10-19 | Longitudinal Trajectories of Autonomic Maturation in Preterm Infants (HRV) | 用监护数据做发育研究 → CLINICAL |
| 2–13 | openFDA 1981–2011 | RIGEL MULTICARE 409、MESAMIV RECORDER、TRANSDUCER DOME SD105、SENSATRACE、PMP4 SELFCHECK ECG、MONITRODE、CO2 TEST、LIONHEART 3、ARISTO 2101、K-SNAP、COBE TRANSDUCER、MEMORYTRACE ATM | 历史清关被判 DIRECT 且 FEED，缺少"归档"概念 |
| 14 | openFDA 2008 | MEDLINE SINGLE PATIENT USE BLOOD PRESSURE CUFF | 同上（耗材清关） |

### 4.2 假阴性（本标准认为应进简报，引擎拒绝）

| # | 来源/时间 | 标题 | 引擎判定 | 本标准 |
| --- | --- | --- | --- | --- |
| 1 | Crossref 2021-12 | Accuracy and precision of continuous non-invasive arterial pressure monitoring… | MEDICAL_UNRELATED / medical_not_monitoring | DIRECT / A3 |
| 2 | PubMed 2026-10-21 | Occult hypoxemia in the ICU | CLINICAL / clinical_prediction_model | DIRECT / A1 |
| 3 | Crossref 2025-03 | ECG analysis for arrhythmia classification (self-attention autoencoder) | CLINICAL / clinical_application_of_monitoring | DIRECT / A3 |
| 4 | Crossref 2024-05 | Remote Continuous Patient Monitoring Using IEWS (RCT) | CLINICAL | DIRECT / A2 |
| 5 | PubMed 2026-10-14 | High-Frequency Postoperative ICU Arterial BP Data from EHR | CLINICAL | TRANSFER / A3(低) |
| 6 | Crossref 2026-12 | ICU nurses, experiences with false alarms | CLINICAL | DIRECT(低) / A4 |
| 7 | Crossref 2026-03 | Beyond alarm fatigue: behavioural nudge fatigue | MEDICAL_UNRELATED | DIRECT(低) / A4 |
| 8 | Crossref 2026-02 | Escalation metrics and the early warning score paradox | MEDICAL_UNRELATED | DIRECT(低) / A4 |
| 9 | PubMed 2026-11-10 | Interpreting delayed ECG readings after telehealth outages | MEDICAL_UNRELATED / no_monitoring_signal | DIRECT(低) / A4 |
| 10 | Dräger 2026-06-05 | Dräger + B.Braun connected Acute Care | MEDICAL_UNRELATED / primary_record_unmapped | 商业信号 / A2(低) |

注意第 6–9 条属"低价值假阴性"（A4 背景档），它们的意义不是"漏掉重要情报"，而是"漏掉可解释性"。
真正造成业务损失的是第 1–4 条。

## 5. 强制复核：PubMed 表现（任务要求）

| 指标 | 数值 | 说明 |
| --- | --- | --- |
| 库内 PubMed 观测 | 484 | 2025-10 → 2027-01 的全部 PubMed 库存 |
| 其中 FEED | 30（6.2%） | 94% 被排除 |
| 本轮 44 条 PubMed 抽样中 FEED | 12 | 其中 11 条与我的标注一致 |
| 本轮 PubMed 二分类 | TP 11 / FP 1 / FN 3 / TN 29 | precision 0.917，recall 0.786 |
| 与 REF-004 held-out 的 PubMed 层对比 | 其 n=24，阳性仅 1 条，precision 0/recall 0 | 那一层几乎没有测到阳性样本 |

结论：**在"已入库的 PubMed 记录"上，引擎的精度是可以接受的（0.92）**；
真正的问题在入库之前——同一时期 PubMed 里有 286 条它没有请求（REFERENCE_EVENTS 2.2）。
换句话说：**PubMed 的问题不是分类器，是检索式。**

## 6. 引擎维度本身的可诊断性

| 维度 | 取值分布（全库 8,593） | 诊断 |
| --- | --- | --- |
| `importance` | HIGH 3 / MEDIUM 7,357 / LOW 0（FEED 内） | **常量，无信息量**；本轮 120 条抽样同样全部 MEDIUM |
| `confidence` | 0.95（6,944）、0.75（541）、0.8（348）… | 与来源高度相关，不是与判断难度相关 |
| `source_authenticity` | PRIMARY_REGULATORY 6,936 / SCHOLARLY 1,621 / OFFICIAL_VENDOR 36 | 正确，但 36 条 vendor 记录 0 条相关 |
| `entity_link` | AFFILIATION 6,940 / NONE 1,653 | AFFILIATION 全部来自 openFDA applicant，含义过宽 |
| `freshness` | 未在投影中单独统计 | 与 30 天窗口等价，未参与分级 |

**这是本轮对 REFOUNDATION-004 最重要的一条独立反馈**：它把"一个标签承载八个判断"拆成了八个维度，
方向完全正确；但其中最能改变用户行为的那个维度（`importance`）**在所有真实数据上都是常量**，
所以这次拆分在用户可见层面没有产生差别。

## 7. 分歧与需要领域专家裁定的样本

| # | 记录 | 我的判断 | 可能的另一种判断 | 需要谁裁定 |
| --- | --- | --- | --- | --- |
| 1 | Accelerometer/gyroscope 吞咽咳嗽检测（ICU） | DIRECT（低） | TRANSFER 或 A4 | 产品线负责人：是否属于你们的监护范围 |
| 2 | Trustworthy AI for clinical EEG | TRANSFER（低） | DIRECT（低） | 算法负责人 |
| 3 | `Alarm fatigue`（仅标题） | DIRECT（低，存疑） | 社论 → MEDICAL_UNRELATED | 需要原文 |
| 4 | `Alarm Management`（仅标题） | DIRECT（低，存疑） | 工业报警 → NON_MEDICAL | 需要原文 |
| 5 | Dräger+B.Braun 合作公告 | MEDICAL_UNRELATED + 商业信号 | 完全排除 | 产品线负责人：是否关心商业动态 |
| 6 | 1981–2011 年清关 | 档案，不进简报 | DIRECT 且应保留在"证据库" | 无人；这是产品定义问题 |

## 8. 本轮评估的局限（写在结论之前）

- 单评审，无一致性系数；6/120 存疑。
- 样本量 120，二分类 41 个阳性 → 精确率的 95% Wilson 区间约为 [0.51, 0.78]。
  即"精确率 0.66"只能支持"明显低于 0.93"，不能支持"精确率就是 0.66"。
- 抽样框是"当前库存"，因此**无法**估计"系统漏掉了多少不在库存里的东西"（那由 REFERENCE_EVENTS 回答）。
- 未测 UI：本评估只测"引擎判定"，不测"用户是否看得懂"。QA-002 已证明 UI 层另有失败（404/500/能力语义）。

## 9. 可复现命令

```
python _fp001/sample120.py     # 抽样（种子 20261118）
python _fp001/label120.py      # 标注 + 混淆矩阵
python _fp001/errs.py          # 逐条错误
```

标注原文：`_fp001/labelled120.json`（含 observation_id，可与账本逐条核对）。
