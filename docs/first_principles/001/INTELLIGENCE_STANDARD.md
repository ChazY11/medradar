# FIRST PRINCIPLES-001 / 第二阶段：独立的监护技术情报判断标准

- 版本：`fp-standard-2026.11.18`（本文件自带版本号，与代码中的 `radar-assessment-*` **无关**）
- 适用范围：ICU / 床旁患者监护技术情报（ECG、SpO2、血压、脑氧/神经监护、多参数平台、
  监护算法与报警、相关监管安全事件、有明确迁移价值的新型监护方法）
- 使用者：任何一位能读懂临床摘要的评审者，不需要读代码

> **独立性声明**：本标准的定义、例子与优先级顺序由"用户要做什么决策"推导而来，
> 不是从 `medradar/radar/assessment.py` 或 `relevance.py` 反推或抄写。
> 现有代码在本轮中只是**被评价对象**。两者恰好部分相似，是因为它们面对同一批文本，
> 相似不能作为本标准正确性的证据；不一致处（第 8 节）才是本轮要报告的内容。

## 1. 设计原则

1. **先问对象，再问词汇**：一条记录的"主题"只由它自己关于什么决定（标题、摘要、官方描述）；
   期刊名、作者单位、发布机构、数据库索引词都不是主题证据。
2. **相关性 ≠ 重要性**：`DIRECT` 回答"是不是监护技术"，行动档位回答"现在要不要动"。
   两者必须分开打分，且**允许"高度相关但只值得归档"**（1981 年的压力传感器清关）。
3. **时间语义是证据的一部分**：源站声明的时间、精度（年/月/日/时刻）、以及"我们首次看到它"
   是三个不同事实。任何判断都必须能追溯到它用的是哪一个。
4. **信息不足就降级，不猜**：缺摘要、缺日期、缺主体时，输出"无法判定 + 缺什么"，
   而不是用词汇补全。
5. **可执行**：每个分类都必须能由一个人在两分钟内依据标题+摘要完成；不能完成的，
   归入"需人工复核"而不是强行分类。

## 2. 五个相关性类别（主分类，互斥且穷尽）

### 2.1 DIRECT —— 直接监护技术证据

**定义**：记录**自身的主题**是监护设备、传感、测量链、监护算法、报警逻辑或其性能/安全/合规状态。
三个条件同时成立才算 DIRECT：

- （a）对象属于监护测量链：ECG/心电、SpO2/脉搏血氧、有创/无创血压、呼吸/EtCO2、体温、
  脑氧(NIRS)/连续 EEG/颅内压、多参数平台与中央站、报警与信号质量、设备互操作；
- （b）记录关于该对象**本身**（性能、算法、结构、注册、故障、使用方法对测量的影响）；
- （c）证据形式可核验（有来源、有日期、有主体）。

**正例**
- `Peripheral Perfusion: The Missing Physiological Variable in ICU Pulse Oximetry Accuracy Studies`
  （PubMed 2026-11）：论述灌注对 SpO2 精度的影响——对象就是测量误差本身。
- `Kinetic Software Library`（openFDA K260640，2026-10-23，产品码 DPS=Electrocardiograph）：
  一条 ECG 分析软件的清关，主体是算法产品。
- `Accuracy and precision of continuous non-invasive arterial pressure monitoring in critical care:
  A systematic review and meta-analysis`（Crossref 2021-12）：对象是无创连续血压测量的精度。

**反例**
- `Risk model prediction of ICU mortality in aortic dissection patients based on MIMIC-IV`：
  数据来源是监护/病历数据，但对象是死亡风险，不是测量。→ CLINICAL。
- `Philips launches UniGuide 3D Live Guidance`：官方、竞品、医疗器械，但对象是影像引导。
  → MEDICAL_UNRELATED。

**边界案例**
- `Accelerometer- and Gyroscope-Based Sensor System for Detecting Swallowing, Speaking, and Coughing
  Events in ICU Patients`（PubMed 2026-11）：传感系统在 ICU，被测对象是吞咽/咳嗽（生理事件，
  非经典监护参数）。判定：**DIRECT（低置信）**，因为它服务于气道/误吸监护，属监护平台扩展；
  若用户方立场是"只做 ECG/SpO2/血压/脑氧四类"，则降为 TRANSFER。**这类分歧必须记录，不要合并**。
- `Alarm fatigue`（仅标题、无摘要）：可能是社论、也可能是报警管理综述。判定：**需人工复核**。

**判断时要看的证据**：标题中的被测对象与动词；摘要中的方法（对照/精度/队列）；
官方描述中的设备名与产品码；如果只有标题，置信度上限 0.6。

**信息不足时**：只有标题 → DIRECT 最多给"低置信 DIRECT"，不进入"立即行动"档；
无标题只有产品码 → 按产品码映射，但仍需人工确认产品形态。

### 2.2 TRANSFER —— 有明确监护迁移价值

**定义**：技术本身不是监护设备，但**有明确、可描述的迁移路径**到上述测量链，
且记录给出了足够的方法细节使迁移可评估。必须能写出"迁移到什么参数、解决什么问题"，
写不出来就不是 TRANSFER。

**正例**
- `Strain-Insensitive Hydrogel Fiber Electrodes With Micropillar Arrays for Dynamic ECG Monitoring`
  （PubMed 2026-10）：材料/电极技术，明确用于动态 ECG——迁移路径就是"电极→ECG 采集"。
- `Towards Contact-Free Cardiac Magnetic Resonance: Feasibility of Remote Photoplethysmography for
  Cardiac Triggering`（PubMed 2026-11）：rPPG 用于 MRI 门控，但 rPPG 正是监护的传感原理。

**反例**
- `MarkerScout: A Disease-Agnostic Machine Learning Framework for Biomarker Prediction`：
  通用 ML 方法，没有具体生理信号/设备路径 → CLINICAL 或 MEDICAL_UNRELATED。
- `Beyond classification accuracy: Building trustworthy artificial intelligence for clinical
  EEG`：对象是 AI 可信性方法论，不是监护技术；可作 TRANSFER（低）但不应进默认简报。

**边界案例**：`Leveraging High-Frequency Postoperative ICU Arterial Blood Pressure Data from EHR for
Research`（PubMed 2026-10-14）：对象是数据工程方法，不是设备，但直接处理动脉压波形。
判定：**TRANSFER（低）**——迁移价值在"数据基础设施"，对算法团队有用，对产品线决策无用。

**信息不足时**：无法写出迁移路径 → 不允许标 TRANSFER（这是最容易被滥用的类别）。

### 2.3 CLINICAL —— 临床应用/预测研究，无明确监护技术贡献

**定义**：使用监护数据回答临床问题（预后、疗效、流行病学、卫生经济、护理流程），
或提出临床评分/预测模型，但**不产出**可用的监护技术、算法或设备知识。

**正例**：`Longitudinal Trajectories of Autonomic Maturation in Preterm Infants Using Serial 24-Hour
Heart Rate Variability Monitoring`（PubMed 2026-10-19）：用 HRV 监护数据研究发育问题。

**反例**：`Development of a novel non-invasive blood pressure measurement technique using near-infrared
spectroscopy and deep neural networks`：虽然发表在临床期刊，但产出的是测量技术 → DIRECT。

**边界案例**：`Occult hypoxemia in the ICU: Clinical risk factors, mortality and implications for
nursing practice`（PubMed 2026-10-21）。表面是"危险因素+死亡率"（像 CLINICAL），
实质是"SpO2 在什么情况下会骗人"（设备性能失效）。判定：**DIRECT（高价值）**。
判据：当一条记录的结论会改变"我们设备的读数是否可信"，它就是设备证据，不是临床研究。

**信息不足时**：无法判断是"用数据"还是"研究测量" → CLINICAL（保守，排除默认简报），并标记复核。

### 2.4 MEDICAL_UNRELATED —— 医疗，但非监护技术

**定义**：属于医疗/医疗器械/医疗商业，但对象与监护测量链无关。

**正例**：`Philips Sonicare launches Global Clinical Advisory Board`（牙科）；
`Philips to nominate Boer, Debroux and Brinton to SvB at the 2027 AGM`（公司治理）；
`COBE DISPOSABLE PRESSURE TRANSDUCER` 的反面——注意它是 DIRECT 而不是本类，因为它服务于体外循环压力监测。

**反例**：`Brain Tissue Oxygenation in the Contralateral Hemisphere of Critically Ill Patients`：
听起来是影像/神经科学，但对象是脑组织氧合监测 → DIRECT。

**边界案例**：`Dräger and B. Braun Expand Strategic Collaboration ... connected Acute Care`
（企业官方，2026-06-05，无技术细节）。判定：**MEDICAL_UNRELATED（相关性）+ 商业信号（行动档 A2 低）**。
这就是"企业关联 ≠ 企业产品能力"的典型：它是竞争对手的动作，值得记录，但**不能**据此推断任何技术能力。

**信息不足时**：无摘要的企业公告 → MEDICAL_UNRELATED + 商业信号标记，禁止推断技术内容。

### 2.5 NON_MEDICAL —— 不属于医疗技术

**定义**：工业、航空航天、能源、通信、金融、法律等领域的监测/报警/检测研究。
**正例**：`BFAR: improving radar odometry estimation using a bounded false alarm rate detector`；
`Gear Health Threshold Setting Based on a Probability of False Alarm`；
`An Automated Real Time Oil Leakage Detection without False Alarm`；
`False opinion or false alarm? About the criminal liability of an expert`（法律）。

**关键判据**：`false alarm`、`detector`、`monitoring`、`sensor` 是**跨领域通用词**，本身不构成医疗证据。
必须存在"患者/生理/临床"锚点，否则一律 NON_MEDICAL。

**信息不足时**：只有通用工程词、无医疗锚点 → NON_MEDICAL（宁可错杀，因为这类噪声占比最高）。

## 3. 行动价值五档（与主分类正交）

| 档 | 名称 | 判据（满足任一） | 时间窗 |
| --- | --- | --- | --- |
| A1 | 立即 | 已上市监护设备的召回/安全通告/性能失效；或明确的患者安全风险 | 事件时间 ≤ 90 天，或监管状态为进行中 |
| A2 | 跟踪 | 竞品在监护主题上的注册状态变化（510(k)/PMA/新证）、产品发布、说明书修订 | ≤ 24 个月 |
| A3 | 参考 | 可复用的性能/方法学证据（一致性、验证、系统综述、数据集） | ≤ 36 个月 |
| A4 | 背景 | 临床使用研究、行业综述、商业动态 | 不限 |
| A5 | 超范围 | CLINICAL / MEDICAL_UNRELATED / NON_MEDICAL | — |

**组合规则**：
- `DIRECT + A1/A2/A3` → 进入默认情报流（本周简报）。
- `DIRECT + A4/A5` → 进入档案，不推送；**但必须可搜索**（例如 1981 年的压力传感器清关）。
- `TRANSFER` → 默认进"待评估"，只有标题明确写出监护用途时才进简报。
- `CLINICAL / MEDICAL_UNRELATED / NON_MEDICAL` → 不进简报，但**保留理由**。

**硬性禁止**：不允许因为"来源权威""是企业""是监管记录""数量多"而提升任何一条记录的档位。
这四条是本轮在真实数据中反复观察到的四类误判。

## 4. 六个关键概念的定义

### 4.1 技术创新
满足其一：新的测量原理/传感材料；已知原理的新部位或新连续化方式；
新的信号处理或算法结构**并有性能证据**；系统架构变化使部署方式改变（如无线化、去缆化）。
仅"用了深度学习"不构成创新。

### 4.2 普通研究
在已知方法上做增量应用，或用既有数据回答一个临床问题。**普通不等于无价值**，
但它应进 A4 背景档而不是简报。

### 4.3 企业官方证据
企业自己发布的、关于自己产品/合作/财务/人事的陈述。它证明"企业说了什么"，
**不证明**"技术做到了什么"。可用作 A2 跟踪的触发点，不可用作技术结论。

### 4.4 企业关联 ≠ 企业产品能力
以下都不是能力证据：论文作者含企业；企业发布了新闻；监管记录里出现了企业名；
专利属于企业。能力证据只有两类：监管文件中的具体产品与适应症；企业公开的技术规格/临床数据。

### 4.5 重要监管安全信息
同时满足：涉及**已上市**设备；存在**患者/使用者风险**；有**可执行的处置**（纠正/移除/软件更新）。
仅"清关"不是安全信息；仅"警告信"若不含处置也不是。

### 4.6 新信息 / 历史信息被系统首次发现
- **新信息**：源站声明的时间（含精度）晚于我们上一次成功采集的时间窗。
- **首次发现**：我们的 `first_observed_at`。
- **历史回填**：源站时间早于采集窗口，但我们第一次入库。
三者**必须分开计数**。本轮实测：8,593 条中 8,588 条是"首次导入"（INITIAL_DISCOVERY），
只有 5 条是增量——这意味着在 2026-11-16 那天，系统的"变化"视图里 99.94% 是建库噪声。

### 4.7 需要人工复核的边界内容（强制）
以下情形一律输出 REVIEW + 缺什么，不得自动判定：
只有标题；无主体（无设备/无企业）；时间精度未知且影响新鲜度；跨领域词（sensor/monitoring）但无医疗锚点；
企业公告无技术细节；同一标题对应多个不同 DOI。

## 5. 判定流程（按顺序执行，前一步命中即停）

```
0. 记录是否可读？无标题 → REVIEW（缺标题）
1. 有非医疗领域强锚点（雷达/风机/电网/航空/法律）且无患者锚点 → NON_MEDICAL
2. 是书目通告（勘误/撤稿/社论）→ MEDICAL_UNRELATED(notice)
3. 对象是否监护测量链？
   3a. 是，且记录关于该对象本身 → DIRECT，进入第 4 步
   3b. 否，但有可写出的迁移路径 → TRANSFER
   3c. 否，且是临床问题/预测模型 → CLINICAL
   3d. 否，且与监护无关的医疗 → MEDICAL_UNRELATED
4. 行动档：按第 3 节规则；安全事件优先 A1，竞品注册 A2，性能证据 A3
5. 时间：标注源站时间与精度 + 首次发现；精度未知或时间在未来 → REVIEW（时间不可用）
```

**顺序的意义**：第 1 步（非医疗）必须早于"测量词命中"，否则雷达/风机的 `false alarm` 会污染；
第 3c 步（临床）必须晚于"设备对象"判断，否则"SpO2 骗人"（2.3 边界案例）会被误判为临床。
本轮在真实数据中同时观察到了这两类错误（见 INDEPENDENT_EVALUATION）。

## 6. 与本标准相关的三个硬性约束

1. **同一批文本只允许一套相关性规则**。若采集阶段另有一套过滤，则该过滤必须删除或降级为"标记"，
   否则被过滤的记录永远无法被新规则重新评价（REFOUNDATION-004 已删除了 PubMed/Crossref 的入库前过滤，本轮核对了代码，确认删除）。
2. **判断必须可解释**：每条记录必须能回答"按哪一条规则、用了哪些文本"。
3. **判断必须可重放**：规则版本 + 输入文本 → 结论，三者可核对。

## 7. 本标准如何被使用（本轮实际用法）

- 对 120 条真实记录逐条标注（单评审，见 INDEPENDENT_EVALUATION）；
- 对 400 条 PubMed 参考文献（来自 454 条候选）判断"是否被系统发现"，并只对可能 DIRECT/TRANSFER 的条目计入高价值漏检；
- 对 8 条候选情报做"证据 → 结论"的可追溯表述（INTELLIGENCE_BRIEF）。

## 8. 本标准与现有代码的已知差异（必须报告，不得掩盖）

| 差异点 | 本标准 | 现行 `assessment.py` | 实测后果 |
| --- | --- | --- | --- |
| 行动价值 | 单独五档 | 有 `importance` 维度，但全库 7,360 条 FEED 中 7,357 条为 MEDIUM | 无法排序，用户看到的 21 条（30 天）没有优先级 |
| 归档与简报分离 | DIRECT + A4/A5 应进档案 | 6,936 条历史清关全部 FEED，仅靠 30 天窗口挡住 | 主题/企业视图被 1976–2011 年数据淹没 |
| TRANSFER 判定 | 必须写出迁移路径 | 有 TRANSFER 类，但 120 条样本中只输出 3 条，召回 1/6 | 迁移价值几乎未被识别 |
| 非医疗判断 | 通用工程词无锚点即排除 | 有排除词表，但 11 条非医疗中只识别 4 条 | 排除理由不可信（不影响简报，影响解释） |
| "首次发现"与"新信息" | 三个计数必须分开 | 有 `discovery_phase`，但 8,588/8,593 为 INITIAL | "变化"视图无效 |

这些差异**不是**本轮修改代码的理由（除已证明造成真实损失的项，见 ROOT_CAUSE_ANALYSIS）；
它们是"下一步应该收敛到哪里"的输入。

## 9. 本标准自身的局限

- **单评审**：没有第二人独立标注，一致性未知。
- **标题为主**：120 条中约一半无摘要或摘要被截断，判断基于标题。
- **未覆盖中文来源**：中国监管与企业信息不在本轮判断范围内，标准对此无定义。
- **行动档依赖企业规模假设**：对一家只做 NIBP 的厂商，A2 清关中"血压袖带"比"心电图机"更重要，
  本标准没有把"用户产品组合"纳入判据——这需要真实用户才能定义。
