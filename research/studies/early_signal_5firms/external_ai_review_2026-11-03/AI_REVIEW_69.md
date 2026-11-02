# 69份packet逐条独立AI复核

固定提交：`969fd0cc4fea040cbdb7a518f3c300b9122980b5`。日期：2026-11-03（Asia/Shanghai）。

**仅AI建议，不是人工金标准；不能用于检测器评分。** 原人工字段保持空白。本复核看过旧标签，不是盲评。低/中/高表示标注不确定性，不是经过校准的概率。

对LT的False Signal仅指本packet的证据链不能支持同项目技术转向；不否认试验本身、企业创新或原协议所计算的宽赛道时间顺序。

## ES5-001 · philips · imaging_mr_ct

**AI建议：Routine Iteration；不确定性：中。**

Zenition 70沿用自家Veradius Unity的基本技术与适应证，变更为PC架构、机头及显示配置；支持同方向产品迭代，不能仅因新商品名视为企业转向。

原始记录：K183040 — Philips Medical Systems Nederland B.V. 510(k)：Zenition 70

证据定位：K183040 pp6-8。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：这些配置改动是否达到预先定义的战略转向门槛？

- [K183040](https://www.accessdata.fda.gov/cdrh_docs/pdf18/K183040.pdf)（retrieved）；[本地快照](external_sources/K183040.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-002 · mindray · patient_monitoring

**AI建议：Routine Iteration；不确定性：低。**

Passport既有型号更新，适应证未变，比较对象包括自家K152902/K170876；新增功能在既有监护方向内。

原始记录：K190011 — Shenzhen Mindray Bio-Medical Electronics Co., Ltd. 510(k)：Passport Series Patient Monitors (including Passport 17m, Passport 12m and T1)

证据定位：K190011 pp5-9。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准常规产品更新的排除口径。

- [K190011](https://www.accessdata.fda.gov/cdrh_docs/pdf19/K190011.pdf)（retrieved）；[本地快照](external_sources/K190011.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-003 · medtronic · medical_ai

**AI建议：Routine Iteration；不确定性：低。**

明确为StealthStation颅脑导航软件小版本更新，自家v2.2.7/v3.0已有记录；HAW立体定位器械不能仅凭软件字样证明AI转向。

原始记录：K190672 — Medtronic Navigation, Inc. 510(k)：StealthStation Synergy Cranial S7 Software v.2.2.8, StealthStation Cranial Software v3.1.1

证据定位：K190672 pp4-8。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：确认medical_ai是否包括非AI导航软件。

- [K190672](https://www.accessdata.fda.gov/cdrh_docs/pdf19/K190672.pdf)（retrieved）；[本地快照](external_sources/K190672.pdf)

风险标记：AI_VS_BROAD_SOFTWARE_TRACK。

旧规则标签：Not Assessable (agent-preliminary)。

## ES5-004 · philips · patient_monitoring

**AI建议：Routine Iteration；不确定性：低。**

PIC iX从C.01到C.03，核心变化为QRS检测阈值，基本技术和用途保持一致。

原始记录：K183387 — Philips Medical Systems 510(k)：M3290B Patient Information Center iX

证据定位：K183387 pp6-8。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：确认这种算法参数更新属于常规迭代。

- [K183387](https://www.accessdata.fda.gov/cdrh_docs/pdf18/K183387.pdf)（retrieved）；[本地快照](external_sources/K183387.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-005 · philips · imaging_us

**AI建议：Routine Iteration；不确定性：中。**

Lumify既有超声平台新增iOS应用与电源接口模块；探头、扫描模式及适应证沿用K162549，没有新增3D胎儿自动测量的证据。

原始记录：K192226 — Philips Health Care 510(k)：Lumify Diagnostic Ultrasound System

证据定位：K192226 pp4-6。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：是否把跨操作系统适配视为战略转向？

- [K192226](https://www.accessdata.fda.gov/cdrh_docs/pdf19/K192226.pdf)（retrieved）；[本地快照](external_sources/K192226.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-006 · philips · imaging_mr_ct

**AI建议：Routine Iteration；不确定性：低。**

IQon Spectral CT沿用K163711的探测器和主要组件，摘要将改动描述为适应证文字及小幅修改。

原始记录：K193454 — Philips Medical Systems Nederland B.V. 510(k)：IQon Spectral CT

证据定位：K193454 pp5-7。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准此版本作为已有光谱CT方向的延续。

- [K193454](https://www.accessdata.fda.gov/cdrh_docs/pdf19/K193454.pdf)（retrieved）；[本地快照](external_sources/K193454.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-007 · ge_healthcare · imaging_mr_ct

**AI建议：Uncertain；不确定性：高。**

SIGNA Artist沿用扫描硬件但新增AIR Recon DL深度学习重建；存在实质算法功能，不能由112天间隔或SE结论判定其战略重要性。缺独立来源的转向与持续性证据。

原始记录：K202238 — Ge Healthcare (Tianjin) Company Limited 510(k)：SIGNA Artist

证据定位：K202238 pp5-7。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：AIR Recon DL在本研究中属于MR产品迭代还是新的技术定位？补同产品推出和持续采用证据。

- [K202238](https://www.accessdata.fda.gov/cdrh_docs/pdf20/K202238.pdf)（retrieved）；[本地快照](external_sources/K202238.pdf)

风险标记：GE_LINEAGE_REQUIRES_HUMAN_POLICY。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-008 · philips · patient_monitoring

**AI建议：Routine Iteration；不确定性：中。**

MX500/MX550在既有同型号监护仪基础上更新，摘要以K161531为主对照并列出相同生理监测用途；支持已有监护平台演进。

原始记录：K192137 — Philips Medizin Systeme Boeblingen GmbH 510(k)：IntelliVue Patient Monitor MX500, IntelliVue Patient Monitor MX550

证据定位：K192137 pp5-12。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准新增功能是否改变定位，不能只依据297天间隔。

- [K192137](https://www.accessdata.fda.gov/cdrh_docs/pdf19/K192137.pdf)（retrieved）；[本地快照](external_sources/K192137.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-009 · mindray · imaging_us

**AI建议：Routine Iteration；不确定性：中。**

TE系列新增探头、腹腔镜/胸膜应用和自动测量功能，多个功能已在自家M9等产品获准；倾向平台扩展而非进入新方向。

原始记录：K203391 — Shenzhen Mindray Bio-Medical Electronics Co., Ltd. 510(k)：TE7/TE5/TE7 Max/TE5 Max/TE9 Diagnostic Ultrasound System

证据定位：K203391 pp5-8。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：新增应用范围是否超过常规产品线扩展？

- [K203391](https://www.accessdata.fda.gov/cdrh_docs/pdf20/K203391.pdf)（retrieved）；[本地快照](external_sources/K203391.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-010 · medtronic · medical_ai

**AI建议：Uncertain；不确定性：高。**

SureTune4是DBS编程规划软件的De Novo分类，packet将它写为510k不准确。新的监管类别本身不能证明企业战略转向；需要比较既有SureTune及神经调控业务。

原始记录：DEN210003 — Medtronic Neuromodulation 510(k)：SureTune4 Software

证据定位：DEN210003 pp1-5。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：先修正监管路径，再裁决软件新类别是否构成企业转向；补独立商业化及持续性证据。

- [DEN210003](https://www.accessdata.fda.gov/cdrh_docs/reviews/DEN210003.pdf)（retrieved）；[本地快照](external_sources/DEN210003.pdf)

风险标记：AI_VS_BROAD_SOFTWARE_TRACK, DE_NOVO_MISRECORDED_AS_510K。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-011 · mindray · patient_monitoring

**AI建议：Routine Iteration；不确定性：中。**

Accutorr 3/Rosebud延续K132037生命体征监护仪，新增TrueTemp模块及探头；不是首次进入监护领域。

原始记录：K221113 — Shenzhen Mindray Bio-Medical Electronics Co., Ltd. 510(k)：Accutorr 3 Vital Signs Monitor, Rosebud Vital Signs Monitor

证据定位：K221113 pp5-10。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准温度测量模块增加是否属常规迭代。

- [K221113](https://www.accessdata.fda.gov/cdrh_docs/pdf22/K221113.pdf)（retrieved）；[本地快照](external_sources/K221113.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-012 · philips · patient_monitoring

**AI建议：Routine Iteration；不确定性：低。**

MX750/MX850硬件架构与既有测量性能保留，主要接入此前获准的Masimo外部测量模块。

原始记录：K221348 — Philips Medizin Systeme Böblingen GmbH 510(k)：IntelliVue Patient Monitor MX750 (866471);IntelliVue Patient Monitor MX850 (866470)

证据定位：K221348 pp8-10。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：确认模块接入属于既有监护方向延续。

- [K221348](https://www.accessdata.fda.gov/cdrh_docs/pdf22/K221348.pdf)（retrieved）；[本地快照](external_sources/K221348.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-013 · mindray · imaging_us

**AI建议：Routine Iteration；不确定性：低。**

明确以K210416同系列为对照，主要新增P8-2s探头；已有M9系列延伸。

原始记录：K230768 — Shenzhen Mindray Bio-Medical Electronics Co., Ltd. 510(k)：M9/M9CV/M9T/M8 Elite/M10/M10CV/Crius M10/M11/M11CV/Crius M11/Operus M11/M9 Premium Diagnostic Ultrasound System

证据定位：K230768 pp5-8。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准探头增加的常规迭代归类。

- [K230768](https://www.accessdata.fda.gov/cdrh_docs/pdf23/K230768.pdf)（retrieved）；[本地快照](external_sources/K230768.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-014 · philips · imaging_mr_ct

**AI建议：Routine Iteration；不确定性：低。**

Ingenia Elition R5.7.1 SP4为Special 510(k)修改，适应证未改，沿用既有脉冲序列及线圈。

原始记录：K232030 — Philips Medical Systems Nederland B.V. 510(k)：Ingenia Elition R5.7.1 SP4 MR Systems

证据定位：K232030 pp4-6。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准该软硬件修订不单独计作技术转向。

- [K232030](https://www.accessdata.fda.gov/cdrh_docs/pdf23/K232030.pdf)（retrieved）；[本地快照](external_sources/K232030.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-015 · mindray · imaging_us

**AI建议：Routine Iteration；不确定性：中。**

TE Air无线超声已存在于K220051；本次新增AutoEF和Android支持并更新iOS，不是首次无线超声进入。

原始记录：K231685 — Shenzhen Mindray Bio-Medical Electronics Co., Ltd. 510(k)：TE Air Diagnostic Ultrasound System

证据定位：K231685 pp5-6。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：AutoEF是否达到转向门槛需按统一定义判断。

- [K231685](https://www.accessdata.fda.gov/cdrh_docs/pdf23/K231685.pdf)（retrieved）；[本地快照](external_sources/K231685.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-016 · philips · medical_ai

**AI建议：Routine Iteration；不确定性：低。**

LumiGuide继承AltaTrack，导丝体内长度由120cm改为160cm并增加配置；设备与3D Hub无显著技术变化，名称变化不能当作新方向。

原始记录：K233853 — Philips Medical Systems Nederland B.V. 510(k)：LumiGuide Wire; LumiGuide Equipment R2.0; LumiGuide 3D Hub

证据定位：K233853 pp5-8。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准重命名及导丝长度变化的处理。

- [K233853](https://www.accessdata.fda.gov/cdrh_docs/pdf23/K233853.pdf)（retrieved）；[本地快照](external_sources/K233853.pdf)

风险标记：AI_VS_BROAD_SOFTWARE_TRACK。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-017 · medtronic · respiratory

**AI建议：Uncertain；不确定性：高。**

VitalFlow ECMO套装整合既有泵、氧合器及涂层组件；2024-09-26公司发布新系统并说明此前收购MC3及多年合作。存在商业推进，但新系统、并购归属与企业原有ECMO方向的界限未定。

原始记录：K240880 — Medtronic, Inc. 510(k)：VitalFlow Set with Balance Biosurface

证据定位：K240880 pp5-8; MEDTRONIC_VITALFLOW_2024。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：MC3并购及系统整合应计为战略转向还是既有业务扩展？需同项目后续持续性材料。

- [K240880](https://www.accessdata.fda.gov/cdrh_docs/pdf24/K240880.pdf)（retrieved）；[本地快照](external_sources/K240880.pdf)
- [MEDTRONIC_VITALFLOW_2024](https://news.medtronic.com/Medtronic-launches-VitalFlow-TM-%2C-a-new-Extracorporeal-Membrane-Oxygenation-ECMO-system)（retrieved）；[本地快照](external_sources/MEDTRONIC_VITALFLOW_2024.html)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-018 · philips · imaging_mr_ct

**AI建议：Routine Iteration；不确定性：中。**

Spectral CT保留K203020主要组件，增加呼吸门控4DCT等功能，且参考既有放疗CT；倾向现有光谱CT平台扩展。

原始记录：K244008 — Philips Medical Systems Technologies , Ltd. 510(k)：Spectral CT

证据定位：K244008 pp6-16。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：新增放疗工作流是否跨越预定转向阈值？

- [K244008](https://www.accessdata.fda.gov/cdrh_docs/pdf24/K244008.pdf)（retrieved）；[本地快照](external_sources/K244008.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-019 · medtronic · respiratory

**AI建议：Routine Iteration；不确定性：低。**

VitalFlow Console此次变更为维修人员通过USB升级软件及配套网络安全措施，使用说明延续K230364；不能把整个平台的上市意义归给此次USB更新。

原始记录：K250199 — Medtronic, Inc. 510(k)：VitalFlow Console

证据定位：K250199 pp5-7。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准事件级与平台级判断的分离。

- [K250199](https://www.accessdata.fda.gov/cdrh_docs/pdf25/K250199.pdf)（retrieved）；[本地快照](external_sources/K250199.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-020 · medtronic · medical_ai

**AI建议：Routine Iteration；不确定性：中。**

UNiD Spine Analyzer由4.0升至5.0，扩展退变预测模型至L5情形，原有脊柱手术规划用途仍在；有AI功能但并非由此证明新AI战略。

原始记录：K251629 — Medicrea International S.A.S. (Medtronic) 510(k)：UNiD Spine Analyzer

证据定位：K251629 pp5-9。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准模型扩展阈值及Medicrea并购实体归属。

- [K251629](https://www.accessdata.fda.gov/cdrh_docs/pdf25/K251629.pdf)（retrieved）；[本地快照](external_sources/K251629.pdf)

风险标记：AI_VS_BROAD_SOFTWARE_TRACK。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-021 · mindray · imaging_us

**AI建议：Routine Iteration；不确定性：中。**

Resona 5/6系列以既有Resona 7、M9为参照；库中2017年已有同申请人超声记录。gap=None是左删失，不能证明至少12个月无活动。

原始记录：K172860 — Shenzhen Mindray Bio-Medical Electronics Co., Ltd. 510(k)：Resona 6/Resona 6T/Resona 6EXP/Resona 6Elite Diagnostic Ultrasound System/Resona 6S/Resona 6PRO/Resona 6OB Diagnostic Ultrasound System /Resona 5/Resona 5T/Resona 5EXP/Resona 5Elite Diagnostic Ultrasound System

证据定位：K172860 pp5-8。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：确认补历史后重新计算gap，不把窗口首条当首次进入。

- [K172860](https://www.accessdata.fda.gov/cdrh_docs/pdf17/K172860.pdf)（retrieved）；[本地快照](external_sources/K172860.pdf)

风险标记：LEFT_CENSORED_GAP_NONE。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-022 · medtronic · cardiac_rhythm

**AI建议：Routine Iteration；不确定性：低。**

S615仅增加制造过程中切割互连带所用设备，属于30-Day Notice；2017年已有同申请人的CRT-D补充记录，既非新产品批准也非新赛道进入。

原始记录：P010031S615 — Medtronic Cardiac Rhythm Disease Management PMA 补充 P010031/S615：Amplia MRI CRT-D / Amplia MRI Quad CRT-D / Brava CRT-D / Brava Quad CRT-D / Claria MRI & Quad Quad CRT-D / Compia MRI &

证据定位：P010031S615 results[0].ao_statement。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准将制造工艺通知排除出实质技术转向。

- [P010031S615](https://api.fda.gov/device/pma.json?search=pma_number:P010031+AND+supplement_number:S615&limit=10)（retrieved）；[本地快照](external_sources/P010031S615.json)

风险标记：LEFT_CENSORED_GAP_NONE, MANUFACTURING_NOTICE_NOT_NEW_PRODUCT。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-023 · ge_healthcare · imaging_mr_ct

**AI建议：Routine Iteration；不确定性：中。**

ViewPoint 6是以超声报告为主要用途的影像归档软件，本次在既有K162743基础上加入已在Voluson E10获准的模型；LLZ映射为MR/CT不等于开发了新MR/CT设备。

原始记录：K173456 — Ge Medical Systems Ultrasound and Primary 510(k)：ViewPoint 6

证据定位：K173456 pp4-6 (visually checked)。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：审核LLZ泛影像软件的赛道归属，以及GE业务谱系连续性。

- [K173456](https://www.accessdata.fda.gov/cdrh_docs/pdf17/K173456.pdf)（retrieved）；[本地快照](external_sources/K173456.pdf)

风险标记：LEFT_CENSORED_GAP_NONE, GE_LINEAGE_REQUIRES_HUMAN_POLICY。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-024 · philips · imaging_mr_ct

**AI建议：Routine Iteration；不确定性：低。**

Illumeo是I4的营销重命名并有小幅可视化改动；摘要明确不改变用途和基本技术。窗口首条不构成新技术进入。

原始记录：K173588 — Philips Medical Systems Technologies , Ltd. 510(k)：Illumeo System

证据定位：K173588 pp4-8。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准重命名不计转向，并补窗口前历史。

- [K173588](https://www.accessdata.fda.gov/cdrh_docs/pdf17/K173588.pdf)（retrieved）；[本地快照](external_sources/K173588.pdf)

风险标记：LEFT_CENSORED_GAP_NONE。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-025 · ge_healthcare · imaging_us

**AI建议：Routine Iteration；不确定性：中。**

Voluson S8/S10延续S系列平台，主要调整探头；2017年同申请人已有超声记录，gap=None不是无既往活动。

原始记录：K180374 — GE Healthcare 510(k)：Voluson S8/ Voluson S10/ Voluson S10 Expert

证据定位：K180374 pp4-6。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准系列扩展，并按GE影像业务谱系处理实体。

- [K180374](https://www.accessdata.fda.gov/cdrh_docs/pdf18/K180374.pdf)（retrieved）；[本地快照](external_sources/K180374.pdf)

风险标记：LEFT_CENSORED_GAP_NONE, GE_LINEAGE_REQUIRES_HUMAN_POLICY。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-026 · philips · imaging_us

**AI建议：Routine Iteration；不确定性：中。**

EPIQ/Affiniti继承K172607，增加S9-2探头与弹性成像应用；已有同企业超声方向，不能用窗口首条认定新进入。

原始记录：K181485 — Philips Ultrasound, Inc. 510(k)：EPIQ , EPIQ 5, EPIQ 7, Affiniti 30, Affiniti 50 and Affiniti 70 Diagnostic Ultrasound System

证据定位：K181485 pp4-7。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：确认探头及弹性成像功能扩展的分类门槛。

- [K181485](https://www.accessdata.fda.gov/cdrh_docs/pdf18/K181485.pdf)（retrieved）；[本地快照](external_sources/K181485.pdf)

风险标记：LEFT_CENSORED_GAP_NONE。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-027 · philips · medical_ai

**AI建议：Uncertain；不确定性：高。**

KODEX-EPD采用介电心脏标测；2019合作发布与2022新版发布支持同项目延续。但并购引入的心脏标测是否构成medical_ai/SaMD方向改变、改变起点为何，仍需统一裁决。它是优先复核的潜在转向案例。

原始记录：K180940 — Philips Medical Systems Nederland B.V. 510(k)：KODEX EPD System

证据定位：K180940 pp4-10; PHILIPS_KODEX_2019; PHILIPS_KODEX_2022。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：先确定并购业务是否计转向、DQK心脏标测是否属本赛道，再确认改变日期与首次公开确认日期。

- [K180940](https://www.accessdata.fda.gov/cdrh_docs/pdf18/K180940.pdf)（retrieved）；[本地快照](external_sources/K180940.pdf)
- [PHILIPS_KODEX_2019](https://www.philips.com/a-w/about/news/archive/standard/news/press/2019/20190509-philips-announces-collaboration-with-medtronic-to-further-advance-the-image-guided-treatment-of-atrial-fibrillation.html)（retrieved）；[本地快照](external_sources/PHILIPS_KODEX_2019.html)
- [PHILIPS_KODEX_2022](https://www.usa.philips.com/a-w/about/news/archive/standard/news/press/2022/20220401-philips-showcases-new-innovations-in-the-treatment-of-heart-rhythm-disorders-at-ehra-2022.html)（retrieved）；[本地快照](external_sources/PHILIPS_KODEX_2022.html)

风险标记：LEFT_CENSORED_GAP_NONE, AI_VS_BROAD_SOFTWARE_TRACK。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-028 · medtronic · medical_ai

**AI建议：Routine Iteration；不确定性：低。**

CardioInsight由v3.0到v3.5，软件增强、问题修复和安全功能基于2016年K162440；并非窗口首见即新进入。

原始记录：K181918 — Medtronic, Inc. 510(k)：CardioInsight Cardiac Mapping System

证据定位：K181918 pp4-8。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准DQK心脏标测的软件赛道口径。

- [K181918](https://www.accessdata.fda.gov/cdrh_docs/pdf18/K181918.pdf)（retrieved）；[本地快照](external_sources/K181918.pdf)

风险标记：LEFT_CENSORED_GAP_NONE, AI_VS_BROAD_SOFTWARE_TRACK。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-029 · ge_healthcare · patient_monitoring

**AI建议：Routine Iteration；不确定性：中。**

Unity Network ID已有V8及2015/2017记录，本次是监护数据互联产品延续；gap=None不支持首次进入。

原始记录：K183116 — GE Healthcare 510(k)：Unity Network ID

证据定位：K183116 pp4-6。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：补历史并核准GE业务谱系，确认更新范围。

- [K183116](https://www.accessdata.fda.gov/cdrh_docs/pdf18/K183116.pdf)（retrieved）；[本地快照](external_sources/K183116.pdf)

风险标记：LEFT_CENSORED_GAP_NONE, GE_LINEAGE_REQUIRES_HUMAN_POLICY。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-030 · mindray · patient_monitoring

**AI建议：Uncertain；不确定性：高。**

BeneVision N为新一代监护产品族，比较既有Passport并新增EEG、NMT及多模块能力；既不是首次监护进入，也不能只因同类器械实质等同就断言普通迭代。缺独立定位变化证据。

原始记录：K182075 — Shenzhen Mindray Bio-Medical Electronics Co., Ltd. 510(k)：BeneVision N Series Patient Monitors (Including BeneVision N12, BeneVision N15, BeneVision N17, BeneVision N19. BeneVision N22, BeneVision N1)

证据定位：K182075 embedded 510kSummary pp3-6。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：新平台与多模块扩展是否属于企业技术定位改变？补上市与后续持续性证据。

- [K182075](https://www.accessdata.fda.gov/cdrh_docs/pdf18/K182075.pdf)（retrieved）；[本地快照](external_sources/K182075.pdf)

风险标记：LEFT_CENSORED_GAP_NONE。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-031 · ge_healthcare · respiratory

**AI建议：Routine Iteration；不确定性：中。**

CARESCAPE呼吸模块此次重点改变D-lite++传感器接头和材料，使用范围保留；CCK本地映射缺失不代表装置不相关。

原始记录：K183394 — GE Healthcare Finland Oy 510(k)：CARESCAPE Respiratory Modules, E-sCO, E-sCOV, E-sCOVX, E-sCAiO

证据定位：K183394 pp6-10。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：修复映射缺项并核准呼吸监测模块属于respiratory还是patient_monitoring。

- [K183394](https://www.accessdata.fda.gov/cdrh_docs/pdf18/K183394.pdf)（retrieved）；[本地快照](external_sources/K183394.pdf)

风险标记：LEFT_CENSORED_GAP_NONE, GE_LINEAGE_REQUIRES_HUMAN_POLICY。

旧规则标签：Not Assessable (agent-preliminary)。

## ES5-032 · ge_healthcare · respiratory

**AI建议：Routine Iteration；不确定性：中。**

CARESCAPE在K183394基础上增加E-sCAiOE/E-sCAiOVE型号，沿用软件，现有宿主设备下表现相同；904天间隔不足以定义战略变化。

原始记录：K211171 — GE Healthcare Finland Oy 510(k)：CARESCAPE Respiratory Modules E-sCO, E-sCOV, E-sCOVX, E-sCAiO, E-sCAiOV, E-sCAiOVX, E-sCAiOE, E-sCAiOVE and accessories

证据定位：K211171 pp6-13。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准新增模块及气体接口属于迭代，另审GE谱系。

- [K211171](https://www.accessdata.fda.gov/cdrh_docs/pdf21/K211171.pdf)（retrieved）；[本地快照](external_sources/K211171.pdf)

风险标记：GE_LINEAGE_REQUIRES_HUMAN_POLICY。

旧规则标签：Not Assessable (agent-preliminary)。

## ES5-033 · medtronic · respiratory

**AI建议：Uncertain；不确定性：高。**

Bio-Medicus从原有套管扩展到较长期ECMO/ECLS使用，改变部分材料及耐久要求；确有适用范围变化，但可能受监管再分类影响，缺独立企业转向确认。

原始记录：K201057 — Medtronic, Inc. 510(k)：Bio-Medicus Life Support Catheter and Introducer

证据定位：K201057 pp4-7。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：长期ECMO用途扩展与监管分类变化应如何区分？补同产品商业材料及持续性。

- [K201057](https://www.accessdata.fda.gov/cdrh_docs/pdf20/K201057.pdf)（retrieved）；[本地快照](external_sources/K201057.pdf)

风险标记：LEFT_CENSORED_GAP_NONE。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-034 · ge_healthcare · patient_monitoring

**AI建议：Routine Iteration；不确定性：中。**

B105/B125系列硬件功能延续K201941，加入已获准测量模块、软件和网络安全增强；513天gap不能推导新监护方向。

原始记录：K213490 — Ge Medical Systems Information Technologies, Inc. 510(k)：Monitor B105M, Monitor B125M, Monitor B155M, Monitor B105P, Monitor B125P

证据定位：K213490 pp7-10。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准功能增强及GE实体连续性。

- [K213490](https://www.accessdata.fda.gov/cdrh_docs/pdf21/K213490.pdf)（retrieved）；[本地快照](external_sources/K213490.pdf)

风险标记：GE_LINEAGE_REQUIRES_HUMAN_POLICY。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-035 · philips · imaging_us

**AI建议：Routine Iteration；不确定性：中。**

5000 Compact以Affiniti/CX50为基础，延续成像、信号处理及用途，主要为便携产品形态整合；368天gap只是采样规则。

原始记录：K222648 — Philips Ultrasound, LLC 510(k)：5000 Compact Series Ultrasound Systems (Ultrasound System 5500 G, Ultrasound System 5500 P, Ultrasound System 5500 W, Ultrasound System 5500 CV, Ultrasound System 5300 G, Ultrasound System 5300 P, Ultrasound System 5300 W)

证据定位：K222648 pp5-10。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：便携形态整合在本研究中是否达到战略转向门槛？

- [K222648](https://www.accessdata.fda.gov/cdrh_docs/pdf22/K222648.pdf)（retrieved）；[本地快照](external_sources/K222648.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-036 · philips · medical_ai

**AI建议：Routine Iteration；不确定性：中。**

KODEX-EPD 1.5.0直接继承K180940，心脏标测适应证未改；应与早期平台引入事件分开，676天gap不使更新变成新方向。

原始记录：K212493 — Philips Medical Systems Nederland, B.V. (Pmsn) 510(k)：KODEX  EPD System 1.5.0

证据定位：K212493 pp4-11。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：确认以ES5-027作为平台引入候选，避免重复把新版计作转向。

- [K212493](https://www.accessdata.fda.gov/cdrh_docs/pdf21/K212493.pdf)（retrieved）；[本地快照](external_sources/K212493.pdf)

风险标记：AI_VS_BROAD_SOFTWARE_TRACK。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-037 · medtronic · medical_ai

**AI建议：Routine Iteration；不确定性：中。**

PillCam增加云端阅片与报告选项，摘要明确该组件不处理或分析获取的图像，基础胶囊和软件沿用K211684；不能据medical_ai字段宣称新增AI。

原始记录：K230991 — Given Imaging Ltd. (Medtronic) 510(k)：PillCam SB 3 capsule endoscopy system, PillCam Software 9.0E

证据定位：K230991 pp4-6。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：云端工作流是否单独算技术定位变化？保持与AI功能区分。

- [K230991](https://www.accessdata.fda.gov/cdrh_docs/pdf23/K230991.pdf)（retrieved）；[本地快照](external_sources/K230991.pdf)

风险标记：AI_VS_BROAD_SOFTWARE_TRACK。

旧规则标签：Not Assessable (agent-preliminary)。

## ES5-038 · medtronic · respiratory

**AI建议：Routine Iteration；不确定性：低。**

Bio-Medicus此次明确修改通气连接型号的鲁尔帽材料配方，参照K201057/K201100；826天间隔不是新技术进入。

原始记录：K240534 — Medtronic, Inc. 510(k)：Bio-Medicus Life Support Catheter and Introducer

证据定位：K240534 pp4-6。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准材料配方改动作为常规迭代。

- [K240534](https://www.accessdata.fda.gov/cdrh_docs/pdf24/K240534.pdf)（retrieved）；[本地快照](external_sources/K240534.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-039 · philips · respiratory

**AI建议：Uncertain；不确定性：高。**

实际器械为AF531口鼻面罩，源记录能确认型号及日期，但本次摘要链接404，尚不能确定具体改动；不能凭respiratory首次记录或缺资料判为转向或假信号。

原始记录：K233555 — Philips Respironics 510(k)：AF531 Oro-Nasal EE Leak 1 Face Mask; AF531 Oro-Nasal EE Leak 2 Face Mask

证据定位：K233555 store payload; FDA PDF fetch 404。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：取得K233555摘要或正式产品变更资料，比较既有AF531并补公司归属历史。

- [K233555](https://www.accessdata.fda.gov/cdrh_docs/pdf23/K233555.pdf)（failed）

风险标记：LEFT_CENSORED_GAP_NONE, FDA_SUMMARY_HTTP_404。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-040 · philips · patient_monitoring

**AI建议：Routine Iteration；不确定性：中。**

Telemetry Monitor 5500延续MX40院内遥测用途，主要更新无线硬件、报警及端到端加密；503天gap不能证明新的远程监护方向，且用途不包含居家。

原始记录：K242962 — Philips Medizin Systeme Böblingen GmbH 510(k)：Telemetry Monitor 5500 Release 4.0 (867232)

证据定位：K242962 pp6-10。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准院内遥测升级，不混同居家远程监护转向。

- [K242962](https://www.accessdata.fda.gov/cdrh_docs/pdf24/K242962.pdf)（retrieved）；[本地快照](external_sources/K242962.pdf)

风险标记：无额外机器标记。

旧规则标签：Uncertain (agent-preliminary)。

## ES5-041 · philips · patient_monitoring

**AI建议：Routine Iteration；不确定性：低。**

MMX与既有X1/X3提供同范围监测参数，测量实现及工作原理延续；有具体产品延续证据，不仅是routine分层。

原始记录：K181831 — Philips Medizin Systeme Boeblingen GmbH 510(k)：IntelliVue Multi-Measurement Module MMX

证据定位：K181831 pp5-7。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准该模块更新的归类。

- [K181831](https://www.accessdata.fda.gov/cdrh_docs/pdf18/K181831.pdf)（retrieved）；[本地快照](external_sources/K181831.pdf)

风险标记：无额外机器标记。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-042 · ge_healthcare · imaging_mr_ct

**AI建议：Routine Iteration；不确定性：中。**

深度学习重建不是本事件首次出现：摘要明确K183202已有DLIR，本次移植到Revolution EVO及Edison平台；支持既有算法部署扩展。

原始记录：K193170 — Ge Healthcare Japan Corporation 510(k)：Deep Learning Image Reconstruction

证据定位：K193170 pp4-8。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准跨机型移植为迭代，不能仅凭Deep Learning名称判转向。

- [K193170](https://www.accessdata.fda.gov/cdrh_docs/pdf19/K193170.pdf)（retrieved）；[本地快照](external_sources/K193170.pdf)

风险标记：GE_LINEAGE_REQUIRES_HUMAN_POLICY。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-043 · ge_healthcare · patient_monitoring

**AI建议：Routine Iteration；不确定性：中。**

CARESCAPE B850 V3沿用既有B850基础功能，无新的监测参数类型；倾向平台更新。GE谱系尚需人工统一处理。

原始记录：K191323 — GE Healthcare Finland Oy 510(k)：Carescape B850

证据定位：K191323 pp7-9。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准具体改动与GE法律实体/业务谱系处理。

- [K191323](https://www.accessdata.fda.gov/cdrh_docs/pdf19/K191323.pdf)（retrieved）；[本地快照](external_sources/K191323.pdf)

风险标记：GE_LINEAGE_REQUIRES_HUMAN_POLICY。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-044 · medtronic · cardiac_rhythm

**AI建议：Routine Iteration；不确定性：低。**

此次Micra AV记录仅更新Galway制造中的灭菌后测试；不能把Micra AV产品整体创新归给该制造通知。

原始记录：P150033S071 — Medtronic, Inc. PMA 补充 P150033/S071：Micra AV Transcatheter Pacemaker System

证据定位：P150033S071 results[0].ao_statement。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准事件级排除，而非评价整个Micra AV平台。

- [P150033S071](https://api.fda.gov/device/pma.json?search=pma_number:P150033+AND+supplement_number:S071&limit=10)（retrieved）；[本地快照](external_sources/P150033S071.json)

风险标记：MANUFACTURING_NOTICE_NOT_NEW_PRODUCT。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-045 · ge_healthcare · imaging_mr_ct

**AI建议：Routine Iteration；不确定性：中。**

AMX Navigate延续移动X射线的基本技术和用途，未改变供电、电池、驱动和X射线发生子系统；倾向已有产品方向扩展。

原始记录：K210982 — Ge Medical Systems, LLC 510(k)：AMX Navigate

证据定位：K210982 pp4-7。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：新增操作/机械功能是否达到转向门槛，另审GE谱系。

- [K210982](https://www.accessdata.fda.gov/cdrh_docs/pdf21/K210982.pdf)（retrieved）；[本地快照](external_sources/K210982.pdf)

风险标记：GE_LINEAGE_REQUIRES_HUMAN_POLICY。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-046 · medtronic · cardiac_rhythm

**AI建议：Routine Iteration；不确定性：中。**

S096批准在已有CareLink SmartSync管理器上增加CIED软件应用，属于已存在起搏器管理方向；不能由一天gap直接判断重要性。

原始记录：P150033S096 — Medtronic, Inc. PMA 补充 P150033/S096：CareLink SmartSync Micra VR/AV Application

证据定位：P150033S096 results[0].ao_statement。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准软件应用扩展是否仍属原方向。

- [P150033S096](https://api.fda.gov/device/pma.json?search=pma_number:P150033+AND+supplement_number:S096&limit=10)（retrieved）；[本地快照](external_sources/P150033S096.json)

风险标记：无额外机器标记。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-047 · mindray · imaging_us

**AI建议：Routine Iteration；不确定性：中。**

M9系列增加型号、探头和自动测量功能，沿用既有超声平台；同日事件可能是批量申报，不是负例证明，结论依据器械内容。

原始记录：K210416 — Shenzhen Mindray Bio-Medical Electronics Co., Ltd. 510(k)：M9/M9CV/M9T/M8 Elite/M10/M10CV/Crius M10/M11/M11CV/Crius M11/Operus M11/M9 Premium Diagnostic Ultrasound System

证据定位：K210416 pp5-8。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：确认新增应用的战略阈值，排除同日批量记录造成的分层偏差。

- [K210416](https://www.accessdata.fda.gov/cdrh_docs/pdf21/K210416.pdf)（retrieved）；[本地快照](external_sources/K210416.pdf)

风险标记：无额外机器标记。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-048 · medtronic · medical_ai

**AI建议：Routine Iteration；不确定性：中。**

PillCam硬件和主要软件组件延续既有产品，本次增加远程给药/实施工作流；可能有业务模式意义，但现有资料倾向既有胶囊内镜应用扩展。

原始记录：K211684 — Given Imaging Ltd. (Medtronic) 510(k)：PillCam SB 3 capsule endoscopy system, PillCam Software 9.0E

证据定位：K211684 pp4-6。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：远程实施工作流是否计技术转向？不要把其与新AI算法混为一谈。

- [K211684](https://www.accessdata.fda.gov/cdrh_docs/pdf21/K211684.pdf)（retrieved）；[本地快照](external_sources/K211684.pdf)

风险标记：AI_VS_BROAD_SOFTWARE_TRACK。

旧规则标签：Not Assessable (agent-preliminary)。

## ES5-049 · ge_healthcare · imaging_us

**AI建议：Routine Iteration；不确定性：中。**

Versana Premier沿用K200138及既有影像模式和基础技术，参考自家多种超声设备；支持已有系列更新。

原始记录：K210438 — GE Medical Systems Ultrasound and Primary Care Diagnostics 510(k)：Versana Premier

证据定位：K210438 pp4-7。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准功能组合扩展及GE业务谱系。

- [K210438](https://www.accessdata.fda.gov/cdrh_docs/pdf21/K210438.pdf)（retrieved）；[本地快照](external_sources/K210438.pdf)

风险标记：GE_LINEAGE_REQUIRES_HUMAN_POLICY。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-050 · ge_healthcare · medical_ai

**AI建议：Uncertain；不确定性：高。**

该AI实际识别气管插管、定位尖端及隆突并量化距离，不能仅因routine分层就判常规。2021发布提供不同来源族的产品证据，但未充分建立相对于既有Critical Care Suite的企业定位改变与持续性。 公司公告另称2020年11月起已分发该技术，因此2021年监管日期并非最早商业公开/使用日期。

原始记录：K211161 — Ge Medical Systems, LLC 510(k)：Critical Care Suite with Endotracheal Tube Positing AI algorithm

证据定位：K211161 pp5-9; GE_ETT_2021 web retrieval。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：ETT量化新用途是平台迭代还是技术转向？需要前后产品组合及持续商业应用证据。

- [K211161](https://www.accessdata.fda.gov/cdrh_docs/pdf21/K211161.pdf)（retrieved）；[本地快照](external_sources/K211161.pdf)
- [GE_ETT_2021](https://www.gehealthcare.com/en/about/newsroom/press-releases/ge-healthcare-x-ray-ai-receives-fda-clearance-to-assess-endotracheal-tube-placement)（full page retrieved via web tool; direct HTTP download 403）

风险标记：GE_LINEAGE_REQUIRES_HUMAN_POLICY, AI_VS_BROAD_SOFTWARE_TRACK。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-051 · ge_healthcare · patient_monitoring

**AI建议：Routine Iteration；不确定性：中。**

CARESCAPE B650以K191149为对照，更新软件和小幅硬件，基础功能和工作方式延续。

原始记录：K213181 — GE Healthcare Finland Oy 510(k)：CARESCAPE B650, E-musb

证据定位：K213181 pp7-9。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准改动范围及GE谱系连续性。

- [K213181](https://www.accessdata.fda.gov/cdrh_docs/pdf21/K213181.pdf)（retrieved）；[本地快照](external_sources/K213181.pdf)

风险标记：GE_LINEAGE_REQUIRES_HUMAN_POLICY。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-052 · medtronic · cardiac_rhythm

**AI建议：Routine Iteration；不确定性：低。**

补充记录仅在Polaris电池制造过程中增加阳极密封检查；没有新的ICD技术方向证据。

原始记录：P980016S822 — Medtronic Cardiac Rhythm Disease Management PMA 补充 P980016/S822：Cobalt MRI ICD, Cobalt XT MRI ICD, Crome MRI ICD

证据定位：P980016S822 results[0].ao_statement。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准制造质检变更不计战略转向。

- [P980016S822](https://api.fda.gov/device/pma.json?search=pma_number:P980016+AND+supplement_number:S822&limit=10)（retrieved）；[本地快照](external_sources/P980016S822.json)

风险标记：MANUFACTURING_NOTICE_NOT_NEW_PRODUCT。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-053 · medtronic · cardiac_rhythm

**AI建议：Routine Iteration；不确定性：低。**

S787仅新增电容器生产线，属于制造流程通知；并非Cobalt/CRT-D平台的首次创新事件。

原始记录：P010031S787 — Medtronic Cardiac Rhythm Disease Management PMA 补充 P010031/S787：Amplia MRI CRT-D, Amplia MRI Quad CRT-D, Brava CRT-D, Brava Quad CRT-D, Claria MRI CRT-D, Claria MRI Quad CRT-D, Cobalt

证据定位：P010031S787 results[0].ao_statement。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准生产线增加的排除。

- [P010031S787](https://api.fda.gov/device/pma.json?search=pma_number:P010031+AND+supplement_number:S787&limit=10)（retrieved）；[本地快照](external_sources/P010031S787.json)

风险标记：MANUFACTURING_NOTICE_NOT_NEW_PRODUCT。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-054 · philips · imaging_mr_ct

**AI建议：Routine Iteration；不确定性：中。**

MR5300/MR7700 R11是Special 510(k)平台修订，沿用已有MR平台及获准序列/线圈；支持版本迭代。

原始记录：K223442 — Philips Medical Systems Nederlands B.V. 510(k)：MR 5300 and MR 7700 R11 MR Systems

证据定位：K223442 pp4-7。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准硬软件组合修订是否仍在既有方向。

- [K223442](https://www.accessdata.fda.gov/cdrh_docs/pdf22/K223442.pdf)（retrieved）；[本地快照](external_sources/K223442.pdf)

风险标记：无额外机器标记。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-055 · ge_healthcare · imaging_us

**AI建议：Routine Iteration；不确定性：中。**

Vivid S60N/S70N直接继承K220619，保持基本成像技术，结合既有参考设备；倾向既有心脏超声产品扩展。

原始记录：K223832 — Ge Medical System Ultrasound and Primary Care Diagnostics 510(k)：Vivid S60N, Vivid S70N

证据定位：K223832 pp4-7。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准新增探头/应用范围及GE谱系。

- [K223832](https://www.accessdata.fda.gov/cdrh_docs/pdf22/K223832.pdf)（retrieved）；[本地快照](external_sources/K223832.pdf)

风险标记：GE_LINEAGE_REQUIRES_HUMAN_POLICY。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-056 · philips · patient_monitoring

**AI建议：Routine Iteration；不确定性：低。**

IntelliVue X3/MX100硬件和测量性能延续，新增报警音、权限及单点登录等功能；属于明确的监护软件更新。

原始记录：K230604 — Philips Medizin Systeme Boeblingen GmbH 510(k)：IntelliVue Patient Monitor MX100 (867033), IntelliVue Multi-Measurement Module X3 (867030)

证据定位：K230604 pp8-9。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准报警与权限管理更新归类。

- [K230604](https://www.accessdata.fda.gov/cdrh_docs/pdf23/K230604.pdf)（retrieved）；[本地快照](external_sources/K230604.pdf)

风险标记：无额外机器标记。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-057 · medtronic · medical_ai

**AI建议：Routine Iteration；不确定性：低。**

虽然product_code为空，ao_statement明确仅将收货与检验活动从Rice Creek转至Memphis；可判断本次是生产运营变化，无需因缺映射一律无法评估。

原始记录：P980035S782 — Medtronic, Inc. PMA 补充 P980035/S782：SWCOMBO / Application Software, SW030 / Application Software

证据定位：P980035S782 results[0].ao_statement。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：另核medical_ai映射，但该通知本身不应视为技术转向。

- [P980035S782](https://api.fda.gov/device/pma.json?search=pma_number:P980035+AND+supplement_number:S782&limit=10)（retrieved）；[本地快照](external_sources/P980035S782.json)

风险标记：AI_VS_BROAD_SOFTWARE_TRACK, LOCAL_PRODUCT_CODE_MAPPING_MISSING, MANUFACTURING_NOTICE_NOT_NEW_PRODUCT。

旧规则标签：Not Assessable (agent-preliminary)。

## ES5-058 · medtronic · medical_ai

**AI建议：Routine Iteration；不确定性：中。**

Affera Integrated Mapping System以K241828为直接对照，沿用用途及电磁/阻抗定位机制；本次记录倾向既有系统更新。

原始记录：K243892 — Medtronic, Inc. 510(k)：Affera Integrated Mapping System

证据定位：K243892 pp5-7。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：确认新增功能的重要性及Affera并购归属。

- [K243892](https://www.accessdata.fda.gov/cdrh_docs/pdf24/K243892.pdf)（retrieved）；[本地快照](external_sources/K243892.pdf)

风险标记：AI_VS_BROAD_SOFTWARE_TRACK。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-059 · ge_healthcare · imaging_mr_ct

**AI建议：Routine Iteration；不确定性：中。**

CardIQ Suite沿用K233731，新增非增强心脏分割并提高冠脉追踪分辨率；属于现有心脏CT软件算法扩展，AI特征本身不等于新方向。

原始记录：K243672 — GE Medical Systems SCS 510(k)：CardIQ Suite

证据定位：K243672 pp9-14。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准算法范围扩展阈值及GE谱系。

- [K243672](https://www.accessdata.fda.gov/cdrh_docs/pdf24/K243672.pdf)（retrieved）；[本地快照](external_sources/K243672.pdf)

风险标记：GE_LINEAGE_REQUIRES_HUMAN_POLICY。

旧规则标签：Routine Iteration (agent-preliminary)。

## ES5-060 · mindray · imaging_us

**AI建议：Routine Iteration；不确定性：中。**

Consona N5/N3系列主要复用N9及Resona/MX6已获准用途、探头和附件；新增打印机固定架等配置，支持产品线扩展。近期事件不能用于声称长期持续转向。

原始记录：K251853 — Shenzhen Mindray Bio-Medical Electronics Co., Ltd. 510(k)：Consona N5, Consona N5 Pro, Consona N5 Super, Consona N5 Exp, Consona ER, Consona N5S, Consona EI, Consona EF, Consona N5 Elite, Consona N5 Ultra, Consona N3, Consona N3 Exp Diagnostic Ultrasound System

证据定位：K251853 pp6-10。

判断范围：该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度。

需要真人回答：核准系列扩展；若改判转向，必须另定义后续观察窗口。

- [K251853](https://www.accessdata.fda.gov/cdrh_docs/pdf25/K251853.pdf)（retrieved）；[本地快照](external_sources/K251853.pdf)

风险标记：无额外机器标记。

旧规则标签：Routine Iteration (agent-preliminary)。

## LT-01 · ge_healthcare · patient_monitoring

**AI建议：Uncertain；不确定性：高。**

试验研究连续无创血压与未来AMS工程用途，候选监管结果是B105/B125/B155多参数监护仪。记录未给出具体试验设备型号，无法证明或排除同一项目；SpO2论文不能补齐此关联。

原始记录：NCT04876664 — Evaluation of Continuous Non Invasive Blood Pressure With Adult Volunteers

证据定位：NCT04876664 protocolSection; K213490 pp7-10。

判断范围：该packet作为技术转向证据的有效性；错配不等于企业无转向。

需要真人回答：索取试验设备型号、申办方项目编号或FDA摘要中的明确交叉引用。

- [NCT04876664](https://clinicaltrials.gov/api/v2/studies/NCT04876664)（retrieved）；[本地快照](external_sources/NCT04876664.json)
- [K213490](https://www.accessdata.fda.gov/cdrh_docs/pdf21/K213490.pdf)（retrieved）；[本地快照](external_sources/K213490.pdf)

对应监管记录（当前库中同公司×赛道×日期匹配，非原packet唯一主键）：
- [K213490](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K213490) — Ge Medical Systems Information Technologies, Inc. 510(k)：Monitor B105M, Monitor B125M, Monitor B155M, Monitor B105P, Monitor B125P

风险标记：SYNTHETIC_CLEARANCE_ID_RESOLVED_IN_CURRENT_STORE, CURRENT_TRIAL_VERSION_NOT_HISTORICAL_REPLAY。

旧规则标签：Uncertain (agent-preliminary)。

## LT-02 · medtronic · imaging_mr_ct

**AI建议：False Signal / No Confirmed Shift；不确定性：低。**

试验是superDimension肺部活检导航，监管结果为Visualase热疗系统；不是同一器械项目。试验确实器械相关，旧规则因关键词未命中而给出的理由不成立。

原始记录：NCT03585959 — superDimension™ Navigation System Version 7.2 With Fluoroscopic Navigation Technology

证据定位：NCT03585959 protocolSection; K181859 pp3-6。

判断范围：该packet作为技术转向证据的有效性；错配不等于企业无转向。

需要真人回答：核准排除的是该配对支持技术转向的主张，不是否认试验真实或设备相关。

- [NCT03585959](https://clinicaltrials.gov/api/v2/studies/NCT03585959)（retrieved）；[本地快照](external_sources/NCT03585959.json)
- [K181859](https://www.accessdata.fda.gov/cdrh_docs/pdf18/K181859.pdf)（retrieved）；[本地快照](external_sources/K181859.pdf)

对应监管记录（当前库中同公司×赛道×日期匹配，非原packet唯一主键）：
- [K181859](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K181859) — Medtronic Navigation, Inc. 510(k)：Visualase Thermal Therapy System

风险标记：SYNTHETIC_CLEARANCE_ID_RESOLVED_IN_CURRENT_STORE, CURRENT_TRIAL_VERSION_NOT_HISTORICAL_REPLAY, UNSUPPORTED_SAME_PROGRAM_INFERENCE。

旧规则标签：Uncertain (agent-preliminary)。

## LT-03 · medtronic · respiratory

**AI建议：False Signal / No Confirmed Shift；不确定性：低。**

试验使用Capnostream/PM1000N-RR/Vital Sync进行病房呼吸监测，监管结果为Puritan Bennett 980呼吸机；监测与机械通气被宽赛道归到一起，未建立同项目关联。

原始记录：NCT03571646 — LIFEGUARD Study - Continuous Respiratory Monitoring on the General Ward

证据定位：NCT03571646 protocolSection; K193056 pp3-6。

判断范围：该packet作为技术转向证据的有效性；错配不等于企业无转向。

需要真人回答：确认不能用同公司同赛道的先后顺序证明该项目转向。

- [NCT03571646](https://clinicaltrials.gov/api/v2/studies/NCT03571646)（retrieved）；[本地快照](external_sources/NCT03571646.json)
- [K193056](https://www.accessdata.fda.gov/cdrh_docs/pdf19/K193056.pdf)（retrieved）；[本地快照](external_sources/K193056.pdf)

对应监管记录（当前库中同公司×赛道×日期匹配，非原packet唯一主键）：
- [K193056](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K193056) — Covidien, LLC 510(k)：Puritan Bennett 980 Series Ventilator System

风险标记：SYNTHETIC_CLEARANCE_ID_RESOLVED_IN_CURRENT_STORE, CURRENT_TRIAL_VERSION_NOT_HISTORICAL_REPLAY, UNSUPPORTED_SAME_PROGRAM_INFERENCE。

旧规则标签：Uncertain (agent-preliminary)。

## LT-04 · medtronic · respiratory

**AI建议：False Signal / No Confirmed Shift；不确定性：低。**

试验研究BIS脑电麻醉深度监测，监管结果为Bio-Medicus ECMO套管；仅麻醉关键词与宽呼吸赛道相连，器械及机制不同。

原始记录：NCT04810481 — Bispectral Index and End-Tidal Anesthetic Gas Concentration in Pediatric Patients

证据定位：NCT04810481 protocolSection; K201057 pp4-6。

判断范围：该packet作为技术转向证据的有效性；错配不等于企业无转向。

需要真人回答：核准该跨项目配对不可作为技术转向证据。

- [NCT04810481](https://clinicaltrials.gov/api/v2/studies/NCT04810481)（retrieved）；[本地快照](external_sources/NCT04810481.json)
- [K201057](https://www.accessdata.fda.gov/cdrh_docs/pdf20/K201057.pdf)（retrieved）；[本地快照](external_sources/K201057.pdf)

对应监管记录（当前库中同公司×赛道×日期匹配，非原packet唯一主键）：
- [K201057](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K201057) — Medtronic, Inc. 510(k)：Bio-Medicus Life Support Catheter and Introducer

风险标记：SYNTHETIC_CLEARANCE_ID_RESOLVED_IN_CURRENT_STORE, CURRENT_TRIAL_VERSION_NOT_HISTORICAL_REPLAY, UNSUPPORTED_SAME_PROGRAM_INFERENCE。

旧规则标签：Uncertain (agent-preliminary)。

## LT-05 · medtronic · vascular_access

**AI建议：False Signal / No Confirmed Shift；不确定性：低。**

Ellipsys试验明确为已上市AV瘘建立系统的上市后监测，而监管结果是Bio-Medicus生命支持套管；既非同产品，也不是该产品上市前预警。1998导管引入器标题不补足关联。

原始记录：NCT04484220 — Ellipsys Vascular Access System Post Market Surveillance (PS) Study

证据定位：NCT04484220 protocolSection; K201100 pp3-6。

判断范围：该packet作为技术转向证据的有效性；错配不等于企业无转向。

需要真人回答：核准排除该配对；不要把上市后试验日期当首次研发信号。

- [NCT04484220](https://clinicaltrials.gov/api/v2/studies/NCT04484220)（retrieved）；[本地快照](external_sources/NCT04484220.json)
- [K201100](https://www.accessdata.fda.gov/cdrh_docs/pdf20/K201100.pdf)（retrieved）；[本地快照](external_sources/K201100.pdf)

对应监管记录（当前库中同公司×赛道×日期匹配，非原packet唯一主键）：
- [K201100](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K201100) — Medtronic, Inc. 510(k)：Bio-Medicus Life Support Catheter and Introducer

风险标记：SYNTHETIC_CLEARANCE_ID_RESOLVED_IN_CURRENT_STORE, CURRENT_TRIAL_VERSION_NOT_HISTORICAL_REPLAY, UNSUPPORTED_SAME_PROGRAM_INFERENCE。

旧规则标签：Uncertain (agent-preliminary)。

## LT-06 · philips · imaging_us

**AI建议：False Signal / No Confirmed Shift；不确定性：中。**

试验为BabySize3D三维胎儿自动平面提取和测量，监管结果为Lumify增加iOS与电源模块；未见BabySize3D关联，现有摘要指向不同用途/改动。

原始记录：NCT03812471 — Optimization of Fetal Biometry With 3D Ultrasound and Image Recognition

证据定位：NCT03812471 protocolSection; K192226 pp4-6。

判断范围：该packet作为技术转向证据的有效性；错配不等于企业无转向。

需要真人回答：如主张同项目，提供BabySize3D与本次Lumify版本的明确技术交叉引用。

- [NCT03812471](https://clinicaltrials.gov/api/v2/studies/NCT03812471)（retrieved）；[本地快照](external_sources/NCT03812471.json)
- [K192226](https://www.accessdata.fda.gov/cdrh_docs/pdf19/K192226.pdf)（retrieved）；[本地快照](external_sources/K192226.pdf)

对应监管记录（当前库中同公司×赛道×日期匹配，非原packet唯一主键）：
- [K192226](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K192226) — Philips Health Care 510(k)：Lumify Diagnostic Ultrasound System

风险标记：SYNTHETIC_CLEARANCE_ID_RESOLVED_IN_CURRENT_STORE, CURRENT_TRIAL_VERSION_NOT_HISTORICAL_REPLAY, UNSUPPORTED_SAME_PROGRAM_INFERENCE。

旧规则标签：Uncertain (agent-preliminary)。

## LT-07 · philips · respiratory

**AI建议：False Signal / No Confirmed Shift；不确定性：低。**

DreamKit用于睡眠呼吸信号验证，监管结果是AF531面罩；第三来源是猪模型低成本呼吸机研究。三者不是同产品项目，论文仅提前76天不构成独立确认。

原始记录：NCT04926077 — DreamKit Respiratory Effort Signal Validation

证据定位：NCT04926077 protocolSection; K233555 store payload; PLOS_LT07。

判断范围：该packet作为技术转向证据的有效性；错配不等于企业无转向。

需要真人回答：核准排除这一证据链；若另有同项目来源，应重新建立packet。

- [NCT04926077](https://clinicaltrials.gov/api/v2/studies/NCT04926077)（retrieved）；[本地快照](external_sources/NCT04926077.json)
- [K233555](https://www.accessdata.fda.gov/cdrh_docs/pdf23/K233555.pdf)（failed）
- [PLOS_LT07](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0303443)（retrieved）；[本地快照](external_sources/PLOS_LT07.html)

对应监管记录（当前库中同公司×赛道×日期匹配，非原packet唯一主键）：
- [K233555](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K233555) — Philips Respironics 510(k)：AF531 Oro-Nasal EE Leak 1 Face Mask; AF531 Oro-Nasal EE Leak 2 Face Mask

风险标记：SYNTHETIC_CLEARANCE_ID_RESOLVED_IN_CURRENT_STORE, CURRENT_TRIAL_VERSION_NOT_HISTORICAL_REPLAY, UNSUPPORTED_SAME_PROGRAM_INFERENCE。

旧规则标签：Uncertain (agent-preliminary)。

## LT-08 · philips · vascular_access

**AI建议：False Signal / No Confirmed Shift；不确定性：低。**

试验为SyncVision/压力导丝指导PCI，监管结果为Bridge Plus阻断球囊；器械和用途不同，2011超声微泡溶栓论文也非该项目。

原始记录：NCT04451044 — Distal Evaluation of Functional Performance with Intravascular Sensors to Assess the Narrowing Effect: Guided Physiologic Stenting

证据定位：NCT04451044 protocolSection; K251358 pp3-6。

判断范围：该packet作为技术转向证据的有效性；错配不等于企业无转向。

需要真人回答：核准宽vascular_access标签不能替代同项目关联。

- [NCT04451044](https://clinicaltrials.gov/api/v2/studies/NCT04451044)（retrieved）；[本地快照](external_sources/NCT04451044.json)
- [K251358](https://www.accessdata.fda.gov/cdrh_docs/pdf25/K251358.pdf)（retrieved）；[本地快照](external_sources/K251358.pdf)

对应监管记录（当前库中同公司×赛道×日期匹配，非原packet唯一主键）：
- [K251358](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K251358) — Philips Image Guided Therapy Devices 510(k)：Bridge Plus Occlusion Balloon (590-002)

风险标记：SYNTHETIC_CLEARANCE_ID_RESOLVED_IN_CURRENT_STORE, CURRENT_TRIAL_VERSION_NOT_HISTORICAL_REPLAY, UNSUPPORTED_SAME_PROGRAM_INFERENCE。

旧规则标签：Uncertain (agent-preliminary)。

## LT-09 · philips · wearable_remote

**AI建议：False Signal / No Confirmed Shift；不确定性：低。**

ALPACA为儿童哮喘eHealth/居家监测，监管结果为HeartStart FRx除颤器的PMA补充；与远程哮喘照护无同项目关联，2016心血管术后远程监测论文也不对应。

原始记录：NCT05517096 — AmbuLatory Pediatric Asthma CAre

证据定位：NCT05517096 protocolSection; P180028S013 results[0]。

判断范围：该packet作为技术转向证据的有效性；错配不等于企业无转向。

需要真人回答：核准本配对不支持技术转向，另修除颤器的wearable_remote映射。

- [NCT05517096](https://clinicaltrials.gov/api/v2/studies/NCT05517096)（retrieved）；[本地快照](external_sources/NCT05517096.json)
- [P180028S013](https://api.fda.gov/device/pma.json?search=pma_number:P180028+AND+supplement_number:S013&limit=10)（retrieved）；[本地快照](external_sources/P180028S013.json)

对应监管记录（当前库中同公司×赛道×日期匹配，非原packet唯一主键）：
- [P180028S013](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?id=P180028) — Philips Medical Systems PMA 补充 P180028/S013：HeartStart FRx Defibrillator

风险标记：SYNTHETIC_CLEARANCE_ID_RESOLVED_IN_CURRENT_STORE, CURRENT_TRIAL_VERSION_NOT_HISTORICAL_REPLAY, UNSUPPORTED_SAME_PROGRAM_INFERENCE。

旧规则标签：Uncertain (agent-preliminary)。
