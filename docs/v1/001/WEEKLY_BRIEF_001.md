# WEEKLY BRIEF 001 — 候选周报（首期）

- 窗口 / window：**2026-10-19 .. 2026-11-18**（30 天）
- 生成 / generated：2026-11-18T15:07Z，由 `python -m medradar radar brief --since 2026-10-19 --until 2026-11-18` 生成
- 策略版本 / policy：`radar-intelligence-2026.11.21`（分级 `radar-assessment-2026.11.21`）
- 数据 / ledger：`radar.db`，15,156 条观测（openFDA 清关 6,936 / openFDA 召回 6,563 / PubMed 484 / Crossref 1,137 / Dräger 31 / Philips 5）
- 复核状态 / review：**没有任何真实用户或人工评审者复核过本期**；本节结论只到 Agent 级。

## 0. 这一期是怎么产生的（可复现）

```
python -m medradar radar run --source openfda_recall --backfill-reason "..."   # 历史回填，标记 BACKFILLED
python -m medradar radar reproject                                            # 判定（append-only）
python -m medradar radar brief --since 2026-10-19 --until 2026-11-18 \
    --reference docs/v1/001/_evidence/reference_events.json \
    --review    docs/v1/001/_evidence/review_2026-11-18.json \
    --output    docs/v1/001/WEEKLY_BRIEF_001.md
```

## 1. 本期的定量结果（自动计算，含分母）

| 指标 | 值 | 说明 |
| --- | --- | --- |
| 窗口内观测（载入） | 15,156 | 账本全量；窗口判定在视图层 |
| ARCHIVE / CANDIDATE / INTELLIGENCE | 14,674 / 462 / 20 | 三个视图之和 = 全量 |
| 本周公开 / 本周更新 / 历史首次采集 / 日期不明 | 354 / 0 / 14,771 / 31 | 新颖度分布 |
| 正式情报条数（上限 15） | 15 | 超过上限 5 条未展示 |
| 重要性分布（正式情报） | CRITICAL 0 / HIGH 1 / MEDIUM 14 / LOW 0 | 不按比例分配 |
| 历史安全事件补充 | 5 | 均为 CRITICAL 召回，已标明“不是本周新发生” |
| 参考事件召回 | **8 / 8 = 1.00** | 参考集见 `_evidence/reference_events.json`，8 条全部经 live openFDA 复核 |
| 参考事件进入正式情报条 | **0 / 8** | 它们都在窗口之前公开，因此按策略进入“历史补充”而不是正文 |
| 重复事件合并 | 0 | 本期正式情报没有同事件多行 |
| 人工复核覆盖 | 0 / 15 | 正式情报 0 条经人工复核；5 条历史补充中 3 条经 Agent 对源核对 |
| 发现延迟（正式情报） | 中位数 15.9 天，最大 24.9 天 | 采集运行在 2026-11-16；这是建库延迟，不是产品承诺 |

## 2. 本期最重要的真实发现（人工阅读本文件时的入口）

窗口内**没有**新公开的监护设备召回（最后一条监护召回的公开日期是 2026-11-05，落在监护范围之外的设备）。
本期真正的安全价值在“历史安全事件补充”里，共 5 条，全部为 CRITICAL：

| 公开日期 | 事件 | 为什么重要 | 官方记录 |
| --- | --- | --- | --- |
| 2026-10-16 | Philips Smart-hopping 2.0 AP / PIC iX 中央站连接中断 | 转运过程中无线漫游失败导致中央监护连接丢失 | [99908](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=99908) |
| 2026-10-09 | Curaplex 二氧化碳采样鼻导管套件 | 套件装配错误（成人套件装入儿科导管），影响 EtCO2 采样 | [99838](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=99838) |
| 2026-10-06 | Nihon Kohden CNS-6200 中央护士站 | 空指针漏洞，可能中断多床集中监护与报警显示 | [99549](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=99549) |
| 2026-10-02 | Medtronic Microstream 组件（Presource 套包） | 说明书更新：接头难以从气管插管断开 | [99801](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=99801) |
| 2026-09-28 | Percussionaire IPV / Phasitron 5 呼吸回路 | 标签警告：不得与挥发性麻醉气体输送系统并用 | [99617](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=99617) |

同一窗口内，系统在更早版本曾完全漏掉其中 2 条（PIC iX、Nihon Kohden 中央站）——见 `RECALL_COVERAGE.md`。

## 3. 原文简报（系统生成，逐条带来源、时间精度、重要性理由与复核状态）

---
# MedRadar 监护设备情报周报

- 窗口 / window: 2026-10-19 .. 2026-11-18
- 生成时间 / generated_at: 2026-11-18T15:08:16+00:00
- 策略版本 / policy: radar-intelligence-2026.11.21
- 账本观测总数 / observations loaded: 15156
- 视图 / views: ARCHIVE 14674 · CANDIDATE 462 · INTELLIGENCE 20
- 新颖度 / novelty: 本周公开 354 · 本周更新 0 · 历史首次采集 14771 · 日期不明 31 · 无变化 0

## 1. 本周正式情报 / Deliverable intelligence

### 1. Agreement of consumer wearable pulse oximeters across activity conditions and skin pigmentation.

- **重要性 / importance**: HIGH
  - 理由 / reasons: monitoring technology is the subject of the record · the record evaluates the measurement itself (accuracy/agreement/validation) · the source-stated date is within the last 30 days
- **事件日期 / event date**: 2026-10-30 (date)
- **公开日期 / published**: 2026-10-30 (date)
- **系统发现 / first observed**: 2026-11-16T22:20:43+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: pubmed · PMID:43031681
- **原始链接 / source URL**: https://pubmed.ncbi.nlm.nih.gov/43031681/
- **发生了什么 / what happened**: Wearable pulse oximetry devices are increasingly used in consumer-grade health products and patient monitoring; however, concerns remain regarding their accuracy across diverse populations and non-ideal conditions. This study evaluated the agreement of four consumer wearable pulse oximeters with two clinical comparator monitors in a cohort of 49 adults during seated rest, treadmill walking, and seated recovery conditions. Skin tone was assessed using both the visual Fitzpatrick scale and the Individual Typology Angle (ITA), derived from objective skin color measurements. Device performance was evaluated using signed and absolute measurement error, generalized estimating equations accounting for repeated measurements, and repeated-measures Bland-Altman analysis. Agreement varied by device and activity condition. Garmin showed a significant negative signed bias relative to the GE Dash dur…
- **为什么与监护安全或性能有关 / why it matters**: title names a monitoring device / evaluates accuracy/performance/agreement
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

### 2. Automated Detection of Abnormal Pediatric Electroencephalograms Using Machine Learning: Retrospective Study.

- **重要性 / importance**: MEDIUM
  - 理由 / reasons: monitoring technology is the subject of the record · the source-stated date is within the last 12 months
- **事件日期 / event date**: 2026-11-13 (date)
- **公开日期 / published**: 2026-11-13 (date)
- **系统发现 / first observed**: 2026-11-16T22:20:52+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: pubmed · PMID:43025848
- **原始链接 / source URL**: https://pubmed.ncbi.nlm.nih.gov/43025848/
- **发生了什么 / what happened**: Electroencephalography (EEG) is widely used in medicine as a technique for the assessment of several brain-related pathologies. However, EEG interpretation requires specialized expertise and remains a labor-intensive task, particularly for prolonged recordings in intensive care, where timely expert review is often challenging. The aim of this study is to address this problem by using AI methods to automate EEG interpretation and compare the performance of different modeling approaches. A gradient boosting-based model, inspired by the work of Albaqami et al, was implemented and compared to deep learning (DL)-based models using convolutional neural networks to classify images generated from raw EEG signals. The models were trained and tested on pediatric EEGs acquired at the University Hospital in Essen. The DL model showed higher observed sensitivity (78.3%) and F1-score (80%) compared t…
- **为什么与监护安全或性能有关 / why it matters**: title names a monitoring measurement with an evaluation/engineering signal / evaluates accuracy/performance/agreement / engineering or algorithm is the object
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

### 3. Feasibility Assessment of Smartphone Camera–Based Atrial Fibrillation Detection Compared With Portable Electrocardiogram: Single-Patient Case Study

- **重要性 / importance**: MEDIUM
  - 理由 / reasons: monitoring technology is the subject of the record · the source-stated date is within the last 12 months
- **事件日期 / event date**: 2026-11-13 (date)
- **公开日期 / published**: 2026-11-13 (date)
- **系统发现 / first observed**: 2026-11-16T22:21:09+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: crossref · DOI:10.2196/94661
- **原始链接 / source URL**: https://doi.org/10.2196/94661
- **发生了什么 / what happened**: Background Atrial fibrillation (AF) affects more than 33 million people globally, with many cases remaining undiagnosed due to the paroxysmal nature of the condition. Current portable AF detection devices require additional hardware, and their cost may limit their accessibility in community screening programs. Facial camera–based remote photoplethysmography (rPPG) is a novel alternative to conventional fingertip-based photoplethysmography (PPG) that enables contact-free cardiac rhythm assessment. Objective This study aimed to assess the technical feasibility of a novel smartphone camera–based facial rPPG AF detection system by comparing its performance with that of a portable electrocardiogram (ECG) device under real-world home monitoring conditions. Methods We conducted a prospective, single-patient volunteer case study involving a patient with diagnosed paroxysmal AF and atrial flutte…
- **为什么与监护安全或性能有关 / why it matters**: title names a monitoring device / evaluates accuracy/performance/agreement
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

### 4. Non-Invasive Intracranial Pressure Monitoring and Management: Algorithm- Based Applications in Resource-Constrained Settings

- **重要性 / importance**: MEDIUM
  - 理由 / reasons: monitoring technology is the subject of the record · the source-stated date is within the last 12 months
- **事件日期 / event date**: 2026-11-12 (date)
- **公开日期 / published**: 2026-11-12 (date)
- **系统发现 / first observed**: 2026-11-16T22:21:17+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: crossref · DOI:10.67570/jnsccm.v4i3.159
- **原始链接 / source URL**: https://doi.org/10.67570/jnsccm.v4i3.159
- **发生了什么 / what happened**: Intracranial hypertension is a major cause of secondary brain injury and adverse outcome following severe traumatic brain injury and other acute neurological conditions. Invasive intracranial pressure (ICP) monitoring remains the reference standard, but its availability isinconsistent in low- and middle-income countries (LMICs). Non-invasive ICP (nICP) technologies, including optic nerve sheath diameter (ONSD) ultrasonography, transcranial Doppler (TCD), quantitative pupillometry and imaging-derived markers, offer potentially scalable alternatives. This narrative review summarizes the current evidence for clinically available nICP techniques and examines their integration into algorithm-based management in resource-constrained settings. Contemporary consensus recommendations, including the Brussels consensus for non-invasive ICP monitoring (B-ICONIC), and the Consensus REVised Imaging a…
- **为什么与监护安全或性能有关 / why it matters**: title names a monitoring measurement with an evaluation/engineering signal / engineering or algorithm is the object
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

### 5. Accelerometer- and Gyroscope-Based Sensor System for Detecting Swallowing, Speaking, and Coughing Events in ICU Patients.

- **重要性 / importance**: MEDIUM
  - 理由 / reasons: monitoring technology is the subject of the record · the source-stated date is within the last 12 months
- **事件日期 / event date**: 2026-11-09 (date)
- **公开日期 / published**: 2026-11-09 (date)
- **系统发现 / first observed**: 2026-11-16T22:20:52+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: pubmed · PMID:43029887
- **原始链接 / source URL**: https://pubmed.ncbi.nlm.nih.gov/43029887/
- **发生了什么 / what happened**: (1) Background: Swallowing, coughing, and speaking are clinically relevant physiological events, but they are not routinely and continuously monitored in intensive care. This study evaluates the feasibility of detecting these events using inertial measurement unit (IMU) signals acquired from the cricoid and thoracic regions. (2) Methods: Data were collected from 29 patients in the intensive care unit (ICU) during predefined swallowing, coughing, speaking, and movement tasks. A classical machine learning pipeline was developed and evaluated using leave-one-patient-out cross-validation. (3) Results: Cricoid and thoracic accelerometer signals were informative for event detection, with the thoracic sensor particularly contributing to cough detection. Speaking (F1=0.80), coughing (F1=0.72), and aggregated swallowing (F1=0.74) were detected in this controlled experimental setting. (4) Conclus…
- **为什么与监护安全或性能有关 / why it matters**: title names a monitoring device
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

### 6. Towards Contact-Free Cardiac Magnetic Resonance: Feasibility of Remote Photoplethysmography for Cardiac Triggering and Gating.

- **重要性 / importance**: MEDIUM
  - 理由 / reasons: monitoring technology is the subject of the record · the source-stated date is within the last 12 months
- **事件日期 / event date**: 2026-11-06 (date)
- **公开日期 / published**: 2026-11-06 (date)
- **系统发现 / first observed**: 2026-11-16T22:21:01+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: pubmed · PMID:42994798
- **原始链接 / source URL**: https://pubmed.ncbi.nlm.nih.gov/42994798/
- **企业 / company**: philips
- **发生了什么 / what happened**: Cardiac magnetic resonance (CMR) sequences necessitate synchronisation with the cardiac cycle. This is routinely obtained through electrocardiographic (ECG) detection of the R-wave with subsequent triggering or gating of the acquisition, depending on the type of sequence. An accepted alternative is the use of transmissive photoplethysmography using a fingerclip (fPPG) to detect the peripheral pulse wave. To assess the feasibility of contact-free remote photoplethysmography (rPPG) for CMR triggering/gating. In this prospective study (www.drks.de, DRKS00036686), CMR sequences were triggered/gated by ECG, fPPG and rPPG. The primary endpoint was trigger accuracy, measured by true positive rate (TPR), positive predictive value (PPV), beat detection error rate (BDER) and trigger-latency variability (TLV) in the rPPG and fPPG tracings compared to the ECG tracing. Secondary endpoints were techn…
- **为什么与监护安全或性能有关 / why it matters**: title names a monitoring device / evaluates accuracy/performance/agreement
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

### 7. Multi-Modal FHIR Sensor Fusion for Real-Time Clinical Decision Support: An Architecture for the Hospital Bedside and Its Extension Toward Remote Patient Monitoring.

- **重要性 / importance**: MEDIUM
  - 理由 / reasons: monitoring technology is the subject of the record · the source-stated date is within the last 12 months
- **事件日期 / event date**: 2026-11-06 (date)
- **公开日期 / published**: 2026-11-06 (date)
- **系统发现 / first observed**: 2026-11-16T22:20:52+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: pubmed · PMID:43029823
- **原始链接 / source URL**: https://pubmed.ncbi.nlm.nih.gov/43029823/
- **发生了什么 / what happened**: MedROAD V3 is a real-time FHIR R4 streaming platform that turns clinical sensor streams into calibrated deterioration risk, evaluated retrospectively on a cardiac ICU cohort. FHIR event sourcing, Kafka and Faust assemble an 86-element feature vector every five minutes. An XGBoost, LSTM and Transformer ensemble, combined by logistic meta-learning with SHAP attribution, scores each window; a write-back client returns the alert to the chart with a runtime-filtered language-model narrative. On 5049 held-out MIMIC-IV patients it reaches AUROC 0.816 at an Expected Calibration Error of 0.001, with a median inference path of 3.1 ms, so latency is governed by the EHR rather than by computation. The FHIR Observation resource is device-agnostic, so the pipeline ingests wearable streams unmodified. Three limits qualify these results. It is retrospective, and the remote-monitoring figures are a feat…
- **为什么与监护安全或性能有关 / why it matters**: title names a monitoring measurement with an evaluation/engineering signal / engineering or algorithm is the object
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

### 8. Beyond classification accuracy: Building trustworthy artificial intelligence for clinical electroencephalography.

- **重要性 / importance**: MEDIUM
  - 理由 / reasons: the record evaluates the measurement itself · but the title states a review, commentary or perspective, not a primary study · the source-stated date is within the last 30 days
- **事件日期 / event date**: 2026-11-02 (date)
- **公开日期 / published**: 2026-11-02 (date)
- **系统发现 / first observed**: 2026-11-16T22:20:52+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: pubmed · PMID:42971410
- **原始链接 / source URL**: https://pubmed.ncbi.nlm.nih.gov/42971410/
- **发生了什么 / what happened**: Electroencephalography (EEG) remains important in clinical neuroscience because it records brain activity as a time-resolved physiological process. It offers millisecond temporal resolution, can be used at the bedside and supports prolonged monitoring. Artificial intelligence (AI) has expanded EEG analysis through automated pattern recognition, representation learning, large-scale screening and decision support in epilepsy, sleep medicine, cognitive disorders, psychiatric conditions, intensive care, disorders of consciousness and anaesthesia monitoring. High classification accuracy in a research dataset, however, is not clinical readiness. EEG signals are shaped by physiological state, artefacts, acquisition systems, preprocessing choices and clinical context. Labels may come from expert annotations, diagnostic categories, behavioural scales, treatment responses or long-term outcomes, a…
- **为什么与监护安全或性能有关 / why it matters**: title names a monitoring measurement with an evaluation/engineering signal / evaluates accuracy/performance/agreement
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

### 9. Extended Wearable ECG Monitoring Detects Unrecognised Arrhythmias After COPD Exacerbation: The PRECURSOR Pilot Study.

- **重要性 / importance**: MEDIUM
  - 理由 / reasons: monitoring technology is the subject of the record · the source-stated date is within the last 12 months
- **事件日期 / event date**: 2026-11 (year)
- **公开日期 / published**: 2026-11 (year)
- **系统发现 / first observed**: 2026-11-16T22:20:40+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: pubmed · PMID:42969162
- **原始链接 / source URL**: https://pubmed.ncbi.nlm.nih.gov/42969162/
- **发生了什么 / what happened**: The period after hospitalisation for an acute exacerbation of chronic obstructive pulmonary disease (COPD) is associated with cardiovascular vulnerability. Clinically important rhythm disturbances may be intermittent or asymptomatic and escape routine postdischarge assessment; however, the diagnostic yield of prolonged monitoring is intrinsically influenced by monitoring duration. In this prospective, single-centre observational pilot, 18 adults recently hospitalised for COPD exacerbation underwent continuous remote monitoring for 21 days between September 2019 and February 2020. The three-lead ZENSOR wearable recorded electrocardiographic rhythm, heart rate and respiratory rate and transmitted full-disclosure data and predefined alerts for clinician review. The primary outcome was participant-level detection of previously unrecognised, cardiologist-confirmed arrhythmias warranting ther…
- **为什么与监护安全或性能有关 / why it matters**: title names a monitoring device
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: the source states the date at year precision, not to the day · no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

### 10. Peripheral Perfusion: The Missing Physiological Variable in ICU Pulse Oximetry Accuracy Studies.

- **重要性 / importance**: MEDIUM
  - 理由 / reasons: monitoring technology is the subject of the record · the source-stated date is within the last 12 months
- **事件日期 / event date**: 2026-11 (year)
- **公开日期 / published**: 2026-11 (year)
- **系统发现 / first observed**: 2026-11-16T22:20:44+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: pubmed · PMID:42786793
- **原始链接 / source URL**: https://pubmed.ncbi.nlm.nih.gov/42786793/
- **发生了什么 / what happened**: Peripheral Perfusion: The Missing Physiological Variable in ICU Pulse Oximetry Accuracy Studies.
- **为什么与监护安全或性能有关 / why it matters**: title names a monitoring device / evaluates accuracy/performance/agreement / no abstract: judged from the title only
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: the source states the date at year precision, not to the day · no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

### 11. The Duke Clinically Linked Electrocardiogram and Arrhythmia Repository

- **重要性 / importance**: MEDIUM
  - 理由 / reasons: monitoring technology is the subject of the record · the source-stated date is within the last 12 months
- **事件日期 / event date**: 2026-11 (year)
- **公开日期 / published**: 2026-11 (year)
- **系统发现 / first observed**: 2026-11-16T22:21:09+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: crossref · DOI:10.1016/j.jacadv.2026.103381
- **原始链接 / source URL**: https://doi.org/10.1016/j.jacadv.2026.103381
- **发生了什么 / what happened**: The Duke Clinically Linked Electrocardiogram and Arrhythmia Repository
- **为什么与监护安全或性能有关 / why it matters**: title names a monitoring device / no abstract: judged from the title only
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: the source states the date at year precision, not to the day · no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

### 12. Cerebral near infrared spectroscopy - clinical use in the neonatal intensive care unit.

- **重要性 / importance**: MEDIUM
  - 理由 / reasons: monitoring technology is the subject of the record · the source-stated date is within the last 12 months
- **事件日期 / event date**: 2026-10-31 (date)
- **公开日期 / published**: 2026-10-31 (date)
- **系统发现 / first observed**: 2026-11-16T22:20:43+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: pubmed · PMID:42982663
- **原始链接 / source URL**: https://pubmed.ncbi.nlm.nih.gov/42982663/
- **发生了什么 / what happened**: Preventing brain injury and optimising neurodevelopmental outcome are central goals of neonatal intensive care, yet routine cerebral monitoring remains uncommon. Near-infrared spectroscopy (NIRS) offers a continuous, non-invasive, cot-side measure of cerebral oxygenation and perfusion, and has been investigated in the newborn for nearly forty years. The introduction of spatially resolved spectroscopy enabled absolute measurement of regional tissue oxygen saturation (rStO2), bringing the technology from the research laboratory into routine bedside use. Abnormal cerebral oxygenation patterns are associated with intraventricular haemorrhage in preterm infants, with injury severity in hypoxic-ischaemic encephalopathy, and with adverse events in congenital heart disease, although signals are strongly influenced by systemic factors and are best interpreted within the broader clinical context.…
- **为什么与监护安全或性能有关 / why it matters**: title names a monitoring device
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

### 13. Current strategies of cerebral oxygenation monitoring in general intensive care units: a narrative review.

- **重要性 / importance**: MEDIUM
  - 理由 / reasons: monitoring technology is the subject of the record · the source-stated date is within the last 12 months
- **事件日期 / event date**: 2026-10-30 (date)
- **公开日期 / published**: 2026-10-30 (date)
- **系统发现 / first observed**: 2026-11-16T22:20:43+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: pubmed · PMID:43016824
- **原始链接 / source URL**: https://pubmed.ncbi.nlm.nih.gov/43016824/
- **发生了什么 / what happened**: Cerebral hypoxia represents the final metabolic consequence of sustained intracranial pressure and impaired autoregulation. Continuous cerebral oxygen monitoring is essential to prevent secondary ischemic injury in neurocritical care particularly in severe traumatic brain injury, malignant infarction, and aneurysmal subarachnoid hemorrhage. It also guides management of systemic disturbances such as shock, sepsis, and respiratory failure and is increasingly used perioperatively in high-risk cardiac, carotid, and neurosurgical procedures. To synthesize physiological principles, monitoring modalities, and clinical applications of cerebral oxygenation across neurocritical care and perioperative settings, emphasizing bedside interpretation and integration within multimodal neuromonitoring. PubMed and Scopus were searched (January 2010-January 2025) using MeSH terms and keywords including "ce…
- **为什么与监护安全或性能有关 / why it matters**: structured review whose subject is monitoring technology
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

### 14. Patient-Specific Explainable Arrhythmia Detection Using Attention-‎Based Deep Networks‏ ‏

- **重要性 / importance**: MEDIUM
  - 理由 / reasons: monitoring technology is the subject of the record · the source-stated date is within the last 12 months
- **事件日期 / event date**: 2026-10-29 (date)
- **公开日期 / published**: 2026-10-29 (date)
- **系统发现 / first observed**: 2026-11-16T22:21:07+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: crossref · DOI:10.29196/jubes.v34i4.6922
- **原始链接 / source URL**: https://doi.org/10.29196/jubes.v34i4.6922
- **发生了什么 / what happened**: The aim of this study is to provide a patient-centered and explainable deep learning framework for arrhythmia detection from multi-lead electrocardiogram (ECG) signals, a framework that, in addition to improving classification performance, can provide meaningful interpretive evidence to support clinical decision-making. In this study, the PTB-XL dataset was used as the main data source, and a complete process, including patient-wise data partitioning, signal preprocessing, target label construction, and multi-label classification, was designed. The proposed model was developed based on learning patient-specific representations and used an attention-based deep network to extract temporal dependencies and lead-wise importance in the ECG signal. The key idea is to combine information from the current ECG recording with patient-specific representations to provide a more patient-aware predic…
- **为什么与监护安全或性能有关 / why it matters**: title names a monitoring measurement with an evaluation/engineering signal / evaluates accuracy/performance/agreement
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

### 15. Unexplained neurological deterioration after acute brain injury: A structured intensive care framework for targeted continuous electroencephalogram.

- **重要性 / importance**: MEDIUM
  - 理由 / reasons: monitoring technology is the subject of the record · the source-stated date is within the last 12 months
- **事件日期 / event date**: 2026-10-23 (date)
- **公开日期 / published**: 2026-10-23 (date)
- **系统发现 / first observed**: 2026-11-16T22:20:52+00:00
- **新颖度 / novelty**: Became public inside the window
- **来源 / source**: pubmed · PMID:42974604
- **原始链接 / source URL**: https://pubmed.ncbi.nlm.nih.gov/42974604/
- **发生了什么 / what happened**: Neurological deterioration after acute brain injury is common in the intensive care unit, yet its cause may remain uncertain when repeat imaging is stable or does not fully explain the examination. Delayed recognition of occult structural, vascular, systemic, metabolic, medication-related, or electrographic mechanisms may postpone time-sensitive treatment. We aimed to provide a structured bedside framework and define the role of targeted continuous electroencephalography (cEEG). We performed a narrative synthesis of evidence and consensus recommendations across aneurysmal subarachnoid hemorrhage, intracerebral hemorrhage, ischemic stroke, traumatic brain injury, and acute subdural hematoma, emphasizing bedside examination, repeat neuroimaging, vascular reassessment, systemic physiology, medication effects, and critical care electroencephalogram (EEG). Deterioration should first be confi…
- **为什么与监护安全或性能有关 / why it matters**: title names a monitoring measurement with an evaluation/engineering signal
- **研发关注点 / R&D attention**: Check whether the evaluated method or measurement applies to your product line, and whether the validation design is comparable to yours
- **不确定性 / uncertainty**: no human reviewer has confirmed this item
- **复核状态 / review**: not reviewed
- **字段依据 / field basis**: what_happened=source (verbatim, trimmed); why=rule; importance=rule (assessment.grade_importance); rd_attention=rule

## 2. 待人工复核 / Needs review

- Creation and verification of an interpretable machine learning model for forecasting in-hospital results in Cardiorenal syndrome patients in critical condition. — LOW · not reviewed · https://pubmed.ncbi.nlm.nih.gov/42986174/
- The measure that matters: What medicine asks of artificial intelligence. — LOW · not reviewed · https://pubmed.ncbi.nlm.nih.gov/42998474/
- Clinical Phenotypes, Machine-Learning Risk Stratification and Treatment Outcomes of Constipation in Stroke Patients Receiving Enteral Nutrition: A Retrospectiv… — LOW · not reviewed · https://pubmed.ncbi.nlm.nih.gov/42952327/
- Data Stream and Hospital-Level Variation in Intensive Care Unit Vital-Sign Record Density Across Medical Information Mart for Intensive Care IV and eICU Collab… — LOW · not reviewed · https://pubmed.ncbi.nlm.nih.gov/42956367/
- Dual-layer edge intelligence for secure real-time medical IoT: a Zero-Trust sequential framework integrating soft-voting intrusion detection and Histogram Grad… — LOW · not reviewed · https://pubmed.ncbi.nlm.nih.gov/43022072/
- Automated phase recognition in the cardiac catheterization laboratory with deep learning. — LOW · not reviewed · https://pubmed.ncbi.nlm.nih.gov/42907878/

## 3. 历史安全事件补充 / Historical safety supplements

这些不是本周新发生的事件，是本周首次采集到的历史记录。

- 2026-10-16 · Philips Smart-hopping 2.0 AP 1.4 GHz; Product/Model Number: 867216; — CRITICAL · checked against the official record by the agent; not a human review · https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=99908
- 2026-10-09 · Curaplex Capnography EtCO2/O2 Oral/Nasal Cannula Multipack (10 pk), Item Number 670272-KIT — CRITICAL · not reviewed · https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=99838
- 2026-10-06 · Product Name: Nihon Kohden CNS-6200 Series Central Nurse Station, Model/Catalog Number: CN-6201 Software Version: software versions: 01-03, 01-04, 01-05, 01-06… — CRITICAL · checked against the official record by the agent; not a human review · https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=99549
- 2026-10-02 · Presource Packs containing Medtronic Microstream Components: Intubation Kit Catalog Numbers AN23366084 AN23366085 AN2336608H AN2336608J Intubating Bag Kit Cata… — CRITICAL · checked against the official record by the agent; not a human review · https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=99801
- 2026-09-28 · Intrapulmonary Percussive Ventilation, IPV-2C, Product Number: S00002-C; Phasitron 5, Product Number: P5 used with Instruction Manual — CRITICAL · not reviewed · https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=99617

## 5. 本期没有进入简报的内容 / What was set aside

- 窗口内被判定为监护范围之外而排除的观测 / excluded in window: 6421
  - 2950 × outside the monitoring scope: not a monitoring device: the product code is not a monitored family and the official text names no monitoring device or measurement
  - 579 × outside the monitoring scope: not a monitoring device: the product code is not a monitored family and the official text names no monitoring device or measurement (catheter)
  - 389 × outside the monitoring scope: clinical application or care pathway, not monitoring technology itself
  - 383 × outside the monitoring scope: not a monitoring device: the product code is not a monitored family and the official text names no monitoring device or measurement (x-ray)
  - 283 × outside the monitoring scope: not a monitoring device: the product code is not a monitored family and the official text names no monitoring device or measurement (implant)
  - 261 × outside the monitoring scope: clinical question; monitoring technology is not under study
  - 193 × outside the monitoring scope: the object is a clinical target/outcome, not monitoring technology
  - 172 × outside the monitoring scope: not a monitoring device: the product code is not a monitored family and the official text names no monitoring device or measurement (infusion pump)
- 同一事件的多条记录已合并 / rows collapsed into one event: 0
- 超过本期条数上限而未展示 / over the item cap: 5

## 6. 方法与限制 / Method and limits

- Only sources the radar registry marks ENABLED were read: openFDA clearances and recalls, PubMed, Crossref, the Philips newsroom and the Draeger newsroom. GE HealthCare is BLOCKED_BY_ACCESS_POLICY, so its feed is not monitored.
- No NMPA (China), EU MDR/EUDAMED or health-canada source is connected. An action published only there cannot appear, so absence from this brief is not evidence of absence.
- Importance is a rule-based grade over the source's own fields. It is not a clinical judgement and it is not a probability.
- Everything here is derived from the observation ledger; no field is generated by a model.
- At least one item has not been reviewed by a human; see review_status.

重要级别由 assessment.grade_importance 依据记录类型、官方召回原因文本、监护相关性、新鲜度和是否评估测量本身分级，并记录理由；不按比例强行分配。
