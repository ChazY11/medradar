# S-031 争议案例研究：24 条真实岗位

这些案例用于解释分类机制和证据边界，不是人工金标准，也不是旧规则或 AI 的错误率统计。每条均可凭公司、样本序号、岗位 ID 和原始行号回查。旧规则版本为 `recruitment_taxonomy_rules_2026-11-04b`；独立判断均为 `AI_PRELIMINARY_LABEL`。

阅读方法：先看原文，再看旧规则和 AI 预判断，最后问“还需要什么证据”。“优先人工复核”表示争议值得投入人工时间，不表示 AI 判断必然错误。

## 1. Senior Sales Representative

**定位**：medtronic，样本 2/20；`job_id=2e1ef6324d1810356d452b7124080001`；原始 JSONL 第 686 行。  
**来源**：https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Prague-Hlavni-MestoPraha-Czech-Republic/Senior-Sales-Representative_R76366-1  
**审计类型**：产品—能力负对照。

**真实原文**

> Achieve and exceed sales targets by driving the adoption of Medtronic's robotic surgery portfolio within an assigned territory

**旧规则判断**：`SALES_ADMIN_OTHER`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `SALES_MARKETING`；辅助职能 空数组；能力 空数组：没有充分能力证据；产品/业务背景 `robotic surgery`；证据强度 `PRODUCT_CONTEXT_ONLY`。

**分歧机制**：标题没有说明研发对象，正文把目标写成销售机器人产品组合。旧规则的商业门槛在这里发挥了正确作用；机器人是所售产品，不是岗位开发的能力。

**还缺什么证据**：若要把机器人研发归因到该岗位，需要具体设计、控制、导航或软件交付职责；当前还需确认其是否仅承担销售指标。

**人工复核决定**：常规复核，保留为高价值负对照。AI 自身的替代解释是：产品知识可能只用于销售、培训、市场采用或客户沟通，不能证明技术开发。

## 2. Therapy Development Specialist - Charlotte, NC

**定位**：medtronic，样本 3/20；`job_id=62cbbafaa709104a852a3e4f9e310001`；原始 JSONL 第 398 行。  
**来源**：https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Charlotte-North-Carolina-United-States-of-America/Therapy-Development-Specialist---Charlotte--NC_R79695-1  
**审计类型**：标题语义与职能分歧。

**真实原文**

> The Therapy Development Specialist (TDS) provides advanced clinical and technical support for new PVH vascular therapies and products to a wide range of clinical settings and customers.

**旧规则判断**：`SALES_ADMIN_OTHER`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `CLINICAL_APPLICATION`；辅助职能 ['SALES_MARKETING']；能力 `clinical therapy support`、`physician training`；产品/业务背景 `cardiac rhythm therapies`；证据强度 `INDIRECT_TECHNICAL_EVIDENCE`。

**分歧机制**：Development 在标题里像产品开发，正文却是临床技术支持。旧规则把它归为商业/其他过粗，AI 则必须防止把 Development 直译为研发。

**还缺什么证据**：需要团队归属、日常时间分配及是否负责产品设计或临床方案开发。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：这些技术内容可能仅服务于生产、服务、质量、临床采用或内部运营，并不证明产品研发。

## 3. R&D Engineer II

**定位**：medtronic，样本 4/20；`job_id=a817339b4ba1103ccfc32246fd6f0002`；原始 JSONL 第 204 行。  
**来源**：https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Nanakramguda-Hyderabad-India/R-D-Engineer-II_R80755-3  
**审计类型**：漏掉具体机械研发能力。

**真实原文**

> Apply GD&T principles and perform tolerance stack-up analyses to support robust product designs.

**旧规则判断**：`CORE_R&D`；track=`None`；状态=`AMBIENT_ONLY`。

**独立 AI 预判断**：主职能 `RESEARCH_DEVELOPMENT`；辅助职能 ['PRODUCT_ENGINEERING']；能力 `mechanical design`、`Creo`、`GD&T`、`tolerance analysis`、`design for manufacturing`、`prototyping`；产品/业务背景 `new product development`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：旧函数类识别到 CORE_R&D，但既有 track 没有承接 GD&T、容差分析和原型等机械设计能力。没有产品 track 不等于没有研发内容。

**还缺什么证据**：需要对应产品、项目阶段，以及这些设计活动属于新产品还是既有产品维护。

**人工复核决定**：常规复核，用于能力词表验证。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 4. Senior Software Engineer – C++ / Video Processing

**定位**：medtronic，样本 5/20；`job_id=61874c4986ba102e37cbc4cc7f1a0000`；原始 JSONL 第 821 行。  
**来源**：https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/London-London-United-Kingdom/Senior-Software-Engineer---C-----Video-Processing_R77369  
**审计类型**：漏掉软件与视频能力。

**真实原文**

> Leverage hardware acceleration to develop high-performance, low-latency video capture, processing, AI inference, visualization and streaming software.

**旧规则判断**：`ALGORITHM_SOFTWARE`；track=`None`；状态=`AMBIENT_ONLY`。

**独立 AI 预判断**：主职能 `SOFTWARE_ALGORITHM`；辅助职能 ['RESEARCH_DEVELOPMENT']；能力 `C++`、`real-time video processing`、`AI inference`、`hardware acceleration`、`embedded systems`、`low-latency processing`；产品/业务背景 `surgical video`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：旧规则识别软件函数，却没有把实时视频、AI inference、硬件加速和低延迟处理转成能力证据。单一 medical_ai 产品 track 无法表达这些工程差异。

**还缺什么证据**：需要确认软件最终部署产品、AI 模型任务和是否属于新开发而非维护。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 5. Sr. Software Test Automation Engineer - HIL

**定位**：medtronic，样本 6/20；`job_id=70591926cba81039e1a55a2c57190000`；原始 JSONL 第 148 行。  
**来源**：https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Mounds-View-Minnesota-United-States-of-America/Sr-Software-Test-Automation-Engineer---HIL_R79528-1  
**审计类型**：研发子类型混淆。

**真实原文**

> Test the functionality and performance of systems software in both standalone and hardware-in-the-loop (HIL) test environments

**旧规则判断**：`ALGORITHM_SOFTWARE`；track=`None`；状态=`AMBIENT_ONLY`。

**独立 AI 预判断**：主职能 `PRODUCT_ENGINEERING`；辅助职能 ['SOFTWARE_ALGORITHM', 'QUALITY_REGULATORY']；能力 `software test automation`、`hardware-in-the-loop`、`real-time systems`、`system verification`；产品/业务背景 `Affera cardiac ablation`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：HIL 和实时系统验证是直接产品研发证据，但它是测试验证能力，不应被改写成 AI 或算法研发。旧规则只给 ALGORITHM_SOFTWARE，丢失了工程交付类型。

**还缺什么证据**：需要被测系统、验证对象、测试平台是否新开发，以及与 Affera 产品的实际关系。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 6. Principal Engineer / Junior Program Manager

**定位**：medtronic，样本 7/20；`job_id=263538b340e510183468e175401c0002`；原始 JSONL 第 812 行。  
**来源**：https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Geleen-Limburg-Netherlands/Principal-Engineer---Junior-Program-Manager_R76978-2  
**审计类型**：混合职能与旧函数误判。

**真实原文**

> Develop and review system architectures, product requirements, design concepts, specifications, and technical documentation, ensuring engineering decisions are based on sound technical principles, risk management, usability, reliability, and patient safety

**旧规则判断**：`QUALITY_REGULATORY`；track=`None`；状态=`AMBIENT_ONLY`。

**独立 AI 预判断**：主职能 `PRODUCT_ENGINEERING`；辅助职能 ['BUSINESS_OPERATIONS', 'RESEARCH_DEVELOPMENT']；能力 `systems engineering`、`system architecture`、`design verification`、`design transfer`；产品/业务背景 `endoscopic devices`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：正文明确包含系统架构、产品需求和设计概念，同时标题又包含项目管理。旧规则落到 QUALITY_REGULATORY，说明标题局部词和单标签会掩盖主交付物。

**还缺什么证据**：需要工程与项目管理的职责比例、汇报线及风险/可用性工作是否只是辅助职责。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 7. Principal Quality Engineer

**定位**：medtronic，样本 12/20；`job_id=7855805f1fb5104a3658e8a0cf9d0002`；原始 JSONL 第 440 行。  
**来源**：https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/Grand-Rapids-Michigan-United-States-of-America/Principal-Quality-Engineer_R80693-2  
**审计类型**：质量技术能力不等于产品研发。

**真实原文**

> Coordinate Design of Experiments (DOE) methods for process development and statistical analysis tools for process capability (Cpk/Ppk), ANOVA, Gage Repeatability and Reproducibility (Gage R&R), Attribute Agreement Analysis, and Test Method Validation (TMV).

**旧规则判断**：`QUALITY_REGULATORY`；track=`None`；状态=`AMBIENT_ONLY`。

**独立 AI 预判断**：主职能 `QUALITY_REGULATORY`；辅助职能 空数组；能力 `design of experiments`、`PFMEA`、`verification and validation`、`statistical analysis`、`process capability`；产品/业务背景 空数组；证据强度 `INDIRECT_TECHNICAL_EVIDENCE`。

**分歧机制**：DOE、统计、Gage R&R 和测试方法验证是强技术能力，但主职仍是质量与工艺能力保障。把它升为新产品研发或贬为无技术内容都不准确。

**还缺什么证据**：需要确认 DOE 服务的具体工艺、是否承担新过程开发，以及质量与研发团队的边界。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：这些技术内容可能仅服务于生产、服务、质量、临床采用或内部运营，并不证明产品研发。

## 8. [标题缺失]

**定位**：ge_healthcare，样本 1/20；`job_id=GEVGHLGLOBALR4045934EXTERNALENGLOBAL`；原始 JSONL 第 54 行。  
**来源**：https://careers.gehealthcare.com/global/en/job/GEVGHLGLOBALR4045934EXTERNALENGLOBAL/Strategic-Account-Manager-f-m-d-Süddeutschland  
**审计类型**：正文缺失。

**真实原文**

> 无可用正文；原始采集状态为 DETAIL_FAILED，故不提供伪造引文。

**旧规则判断**：`UNCLASSIFIED`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `UNCLASSIFIED`；辅助职能 空数组；能力 空数组：没有充分能力证据；产品/业务背景 空数组；证据强度 `INSUFFICIENT_EVIDENCE`。

**分歧机制**：原始记录为 DETAIL_FAILED，标题和正文不可用。旧规则与 AI 都没有可靠文本可判定；此时不赋能力标签是研究结论，而不是低覆盖率失败。

**还缺什么证据**：需要重新合法采集正文，或获得可审计的 archived copy；不能从 URL slug 反推职责。

**人工复核决定**：优先人工复核，先补数据再标注。AI 自身的替代解释是：URL 标题可提供弱线索，但不足以核验实际职责。

## 9. Clinical Research Coordinator

**定位**：ge_healthcare，样本 4/20；`job_id=R4048843`；原始 JSONL 第 44 行。  
**来源**：https://careers.gehealthcare.com/global/en/job/GEVGHLGLOBALR4048843EXTERNALENGLOBAL/Clinical-Research-Coordinator  
**审计类型**：临床研究与工程研发边界。

**真实原文**

> Well managed In-house Ultrasound Scanning Sessions are critical for clinical evaluation of new ultrasound imaging techniques.

**旧规则判断**：`CLINICAL_R&D`；track=`None`；状态=`AMBIENT_ONLY`。

**独立 AI 预判断**：主职能 `CLINICAL_RESEARCH`；辅助职能 ['QUALITY_REGULATORY']；能力 `clinical study coordination`、`GCP compliance`、`ultrasound scanning session management`；产品/业务背景 `new ultrasound imaging techniques`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：原文支持新超声成像技术的临床评价，是直接临床研究证据；它没有证明该协调员开发超声硬件或成像算法。

**还缺什么证据**：需要研究方案职责、是否参与产品需求定义，以及临床评价对应的具体研发项目。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 10. AIS ISC Digital & AI Capabilities, Director

**定位**：ge_healthcare，样本 6/20；`job_id=R4047229`；原始 JSONL 第 1 行。  
**来源**：https://careers.gehealthcare.com/global/en/job/GEVGHLGLOBALR4047229EXTERNALENGLOBAL/AIS-ISC-Digital-AI-Capabilities-Director  
**审计类型**：企业内部 AI 与医疗产品 AI 混淆。

**真实原文**

> The agentic AI factory, digital twin, forecasting, simulation and optimization, and generative capabilities are part of the Capabilities portfolio you own – managed with the same roadmap, certification, and ownership discipline as the data products, not as side projects.

> We are seeking a Director to lead AIS ISC Digital & AI Capabilities, the AI, analytics, and data organization within the AIS Integrated Supply Chain.

**旧规则判断**：`MANUFACTURING_PROCESS`；track=`medical_ai`；状态=`MAPPED`。

**独立 AI 预判断**：主职能 `BUSINESS_OPERATIONS`；辅助职能 ['SOFTWARE_ALGORITHM']；能力 `enterprise data governance`、`SQL`、`business intelligence`、`agentic AI`、`digital twin`、`predictive analytics`、`simulation and optimization`；产品/业务背景 `integrated supply chain`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：岗位确实建设 agentic AI、digital twin 等直接技术能力，但组织与流程都属于 Integrated Supply Chain。旧规则给 medical_ai 会把“真实 AI 能力”误读成“医疗产品 AI”。

**还缺什么证据**：需要能力交付物是否进入患者护理产品，还是仅服务供应链预测、计划和运营。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 11. Sales Enablement GTM Engineer

**定位**：ge_healthcare，样本 9/20；`job_id=R4047009`；原始 JSONL 第 2 行。  
**来源**：https://careers.gehealthcare.com/global/en/job/GEVGHLGLOBALR4047009EXTERNALENGLOBAL/Sales-Enablement-GTM-Engineer  
**审计类型**：商业门槛误杀真实软件开发。

**真实原文**

> Configure and develop using Apex, Flow, Python, the REST Query API, Agentforce script, Lightning Actions and HXL as required - following security, change-management, and release controls.

**旧规则判断**：`SALES_ADMIN_OTHER`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `SOFTWARE_ALGORITHM`；辅助职能 ['SALES_MARKETING']；能力 `Apex`、`Python`、`REST API`、`agentic AI`、`multi-agent orchestration`、`Model Context Protocol`、`MuleSoft`、`enterprise integration`；产品/业务背景 `sales enablement`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：标题中的 Sales Enablement 触发商业类，正文却明确要求 Apex、Python、REST API 等开发。它是直接软件研发，但交付物服务销售体系，不是医疗产品软件。

**还缺什么证据**：需要确认开发的系统、部署环境和交付物；还需排除仅配置低代码而没有实际开发的情况。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 12. API Lead

**定位**：ge_healthcare，样本 20/20；`job_id=R4048087`；原始 JSONL 第 21 行。  
**来源**：https://careers.gehealthcare.com/global/en/job/GEVGHLGLOBALR4048087EXTERNALENGLOBAL/API-Lead  
**审计类型**：多义词与漏掉工艺开发。

**真实原文**

> Lead the development and manufacturing of APIs, precursors, and key materials at external CMOs from early development through commercialization.

> As API Lead, you provide technical leadership for the development and manufacturing of precursors and active pharmaceutical ingredients (APIs) through external Contract Manufacturing Organizations (CMOs).

**旧规则判断**：`UNCLASSIFIED`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `PRODUCT_ENGINEERING`；辅助职能 ['MANUFACTURING_PROCESS', 'QUALITY_REGULATORY']；能力 `API process development`、`synthetic chemistry`、`scale-up`、`technology transfer`、`impurity control`、`CMC`；产品/业务背景 `contrast media`、`molecular imaging agents`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：API 在本文是 active pharmaceutical ingredient，不是软件接口。正文另有早期开发、工艺优化、放大和技术转移；旧 UNCLASSIFIED 不能代表没有研发。

**还缺什么证据**：需要确认外协 CMO 模式下企业自身掌握哪些工艺开发活动，以及对应产品是否属于医疗器械研究范围。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 13. Senior Software Technologist

**定位**：philips，样本 5/20；`job_id=579943`；原始 JSONL 第 32 行。  
**来源**：https://www.careers.philips.com/global/en/job/579943/Senior-Software-Technologist  
**审计类型**：开发工具与产品能力混淆。

**真实原文**

> Senior Software Technologist who can own and deliver end to end software of a component or set of components.

> Stays current with emerging technologies and industry trends such as use on Copilot and other AI platforms for efficiency in software engineering.

**旧规则判断**：`ALGORITHM_SOFTWARE`；track=`patient_monitoring`；状态=`MAPPED`。

**独立 AI 预判断**：主职能 `SOFTWARE_ALGORITHM`；辅助职能 ['RESEARCH_DEVELOPMENT']；能力 `C++`、`real-time operating systems`、`Linux`、`Python`、`CI/CD`、`API design`、`performance optimization`；产品/业务背景 空数组；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：旧规则给 patient_monitoring 与直接软件交付可以并存，但 Copilot 只是提高软件工程效率的工具背景，不能额外推出医疗 AI 研发。

**还缺什么证据**：需要所交付组件的产品归属、软件类型，以及是否实际包含模型或算法开发。

**人工复核决定**：常规复核，保留 AI 工具负对照。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 14. Senior Clinical Scientist – Computed Tomography (Rochester, MN)

**定位**：philips，样本 8/20；`job_id=586163`；原始 JSONL 第 14 行。  
**来源**：https://www.careers.philips.com/global/en/job/586163/Senior-Clinical-Scientist-Computed-Tomography-Rochester-MN  
**审计类型**：临床研发而非工程研发。

**真实原文**

> Shape CT business strategy by contributing to clinical prototypes, innovation roadmaps, and long-term clinical plans that align with business and marketing objectives.

**旧规则判断**：`CLINICAL_R&D`；track=`imaging_mr_ct`；状态=`MAPPED`。

**独立 AI 预判断**：主职能 `CLINICAL_RESEARCH`；辅助职能 ['RESEARCH_DEVELOPMENT']；能力 `clinical research`、`feasibility studies`、`clinical prototype evaluation`、`evidence generation`；产品/业务背景 `computed tomography`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：临床 prototype、可行性研究和证据生成是直接研究活动。旧 imaging_mr_ct 提供产品方向，但不能替代对“临床研究”与“CT 工程开发”的区分。

**还缺什么证据**：需要是否参与工程需求、原型设计，还是主要负责临床方案、执行与证据生成。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 15. Co-op - Mechanical Engineering Technician - Latham, NY - January-June 2027

**定位**：philips，样本 15/20；`job_id=590339`；原始 JSONL 第 51 行。  
**来源**：https://www.careers.philips.com/global/en/job/590339/Co-op-Mechanical-Engineering-Technician-Latham-NY-January-June-2027  
**审计类型**：商业/弃答门槛漏掉产品工程。

**真实原文**

> Assist in the design, assembly, and testing of cryogenic systems and superconducting magnets.

**旧规则判断**：`UNCLASSIFIED`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `PRODUCT_ENGINEERING`；辅助职能 ['RESEARCH_DEVELOPMENT']；能力 `cryogenic systems`、`superconducting magnets`、`mechanical design`、`prototype testing`、`3D modeling`；产品/业务背景 `MRI`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：旧规则未识别函数并压制 track；正文却明确要求低温系统和超导磁体的设计、装配与测试。这是具体产品工程证据，不只是 MRI 产品词。

**还缺什么证据**：需要 co-op 的实际责任边界、设计独立性和项目是否属于既有 MRI 产品维护。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 16. Technical Solutions Consultant - Patient Monitoring (Field: Richmond, VA)

**定位**：philips，样本 19/20；`job_id=588510`；原始 JSONL 第 19 行。  
**来源**：https://www.careers.philips.com/global/en/job/588510/Technical-Solutions-Consultant-Patient-Monitoring-Field-Richmond-VA  
**审计类型**：复杂客户实施不等于产品开发。

**真实原文**

> Lead the deployment, configuration, integration, optimization, maintenance, and remediation of complex patient monitoring and software solutions across servers, wireless networks, and routing and switching.

**旧规则判断**：`UNCLASSIFIED`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `FIELD_SERVICE`；辅助职能 ['SALES_MARKETING']；能力 `healthcare IT integration`、`computer networking`、`cybersecurity`、`system maintenance`、`VMware`、`Microsoft SQL`；产品/业务背景 `hospital patient monitoring`；证据强度 `INDIRECT_TECHNICAL_EVIDENCE`。

**分歧机制**：部署、集成、网络和维护要求很强医疗 IT 能力，但交付发生在客户环境。没有软件设计或产品需求交付时，不应因 patient monitoring 背景升为研发。

**还缺什么证据**：需要是否开发可复用产品组件、是否只配置现有系统，以及客户反馈是否进入正式研发流程。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：这些技术内容可能仅服务于生产、服务、质量、临床采用或内部运营，并不证明产品研发。

## 17. Softwareentwickler als Teilprojektleiter (m/w/d) - Drägerwerk AG & Co. KGaA - Job-ID V000011378

**定位**：draeger，样本 4/20；`job_id=19670`；原始 JSONL 第 16 行。  
**来源**：https://erecruitment.draeger.com/index.php?ac=jobad&id=19670  
**审计类型**：软件与项目管理混合职能。

**真实原文**

> Technische Mitverantwortung für die Embedded-Software im Bereich Neonatal Care über den gesamten Lebenszyklus — von Spezifikation und Implementierung über Test und Optimierung bis zur Serienbetreuung

**旧规则判断**：`UNCLASSIFIED`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `SOFTWARE_ALGORITHM`；辅助职能 ['RESEARCH_DEVELOPMENT', 'BUSINESS_OPERATIONS']；能力 `embedded software`、`C++`、`software project management`、`software integration`；产品/业务背景 `neonatal care`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：正文覆盖嵌入式软件全生命周期，同时标题包含子项目领导。旧 UNCLASSIFIED 与技术内容不符；只标软件也会丢失项目交付职责。

**还缺什么证据**：需要技术工作与项目领导的时间比例，以及量产维护和新开发各自占比。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 18. Junior Sales Engineer - Vi söker vår nästa Sales Engineer!

**定位**：draeger，样本 7/20；`job_id=19656`；原始 JSONL 第 25 行。  
**来源**：https://erecruitment.draeger.com/index.php?ac=jobad&id=19656  
**审计类型**：销售工程与产品开发边界。

**真实原文**

> Du kommer att ta fram tekniska lösningar baserade på kundspecifikationer, genom att omvandla kundens behov och teknisk kapacitet till detaljerade tekniska erbjudanden, lösningar och förslag.

> Du kommer att ha tillgång till 3D ritprogram där du konfigurerar produkterna för att kunna visualisera lösningar till kunderna.

**旧规则判断**：`SALES_ADMIN_OTHER`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `SALES_MARKETING`；辅助职能 ['FIELD_SERVICE']；能力 `BIM`、`3D product configuration`、`technical proposal design`；产品/业务背景 `workplace infrastructure`、`supply units`、`operating lights`；证据强度 `INDIRECT_TECHNICAL_EVIDENCE`。

**分歧机制**：BIM/3D 配置和技术方案是明确能力，但用途是客户报价、产品配置和提案。旧 SALES_ADMIN_OTHER 遮住能力细节，直接改标研发又会越过证据。

**还缺什么证据**：需要是否开发 BIM 工具本身，还是使用既有工具为客户配置产品。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：这些技术内容可能仅服务于生产、服务、质量、临床采用或内部运营，并不证明产品研发。

## 19. IT Technical Lead Device Management (m/w/d) - Drägerwerk AG & Co. KGaA - Job-ID V000011153

**定位**：draeger，样本 20/20；`job_id=19277`；原始 JSONL 第 80 行。  
**来源**：https://erecruitment.draeger.com/index.php?ac=jobad&id=19277  
**审计类型**：Device 多义与企业 IT 边界。

**真实原文**

> Client Management & Lifecycle (HW/OS), Support aller Plattformen (Windows, Linux, MacOS etc.)

**旧规则判断**：`UNCLASSIFIED`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `BUSINESS_OPERATIONS`；辅助职能 ['SOFTWARE_ALGORITHM']；能力 `client device management`、`Windows`、`Linux`、`macOS`、`IT lifecycle management`；产品/业务背景 空数组；证据强度 `INDIRECT_TECHNICAL_EVIDENCE`。

**分歧机制**：Client Management、Windows/Linux/macOS 表明 Device Management 指企业终端，而非医疗设备。技术能力真实存在，但证据只支持企业 IT 运营。

**还缺什么证据**：需要管理对象清单和是否涉及医疗设备接入、医疗器械软件或临床系统。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：这些技术内容可能仅服务于生产、服务、质量、临床采用或内部运营，并不证明产品研发。

## 20. 试剂工程开发工程师(J19184)

**定位**：mindray，样本 1/20；`job_id=33544a5e-93b7-45b2-a2fc-91b46fbbe244`；原始 JSONL 第 72 行。  
**来源**：https://mindray.zhiye.com/social/detail?jobAdId=33544a5e-93b7-45b2-a2fc-91b46fbbe244  
**审计类型**：中文规则覆盖与工艺研发。

**真实原文**

> 主要负责试剂产品制造工艺开发及工艺验证工作

**旧规则判断**：`UNCLASSIFIED`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `PRODUCT_ENGINEERING`；辅助职能 ['MANUFACTURING_PROCESS', 'RESEARCH_DEVELOPMENT']；能力 `IVD reagent process development`、`design transfer`、`process validation`、`scale-up`；产品/业务背景 `IVD reagents`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：旧规则对中文标题和正文未给出函数，但原文直接说明试剂制造工艺开发与验证。工艺研发是直接开发证据，不应与试剂配方研发混写。

**还缺什么证据**：需要是否同时负责配方、反应体系或仅生产工艺，以及放大和验证对应的产品阶段。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 21. 产品经理(AI)(J17248)

**定位**：mindray，样本 4/20；`job_id=a08b6644-b2c9-4582-9590-70f87a14453e`；原始 JSONL 第 48 行。  
**来源**：https://mindray.zhiye.com/social/detail?jobAdId=a08b6644-b2c9-4582-9590-70f87a14453e  
**审计类型**：AI 产品经理的证据边界。

**真实原文**

> 参与 AI 能力平台、数据平台或智能应用的整体架构设计与能力选型，推动标准化、模块化与可复用解决方案沉淀

> 指导并评审技术实现方案（不以亲自编码为主），确保 AI 架构、数据方案与系统设计的可行性与可扩展性

**旧规则判断**：`UNCLASSIFIED`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `PRODUCT_ENGINEERING`；辅助职能 ['SOFTWARE_ALGORITHM', 'BUSINESS_OPERATIONS']；能力 `AI solution architecture`、`data architecture`、`large language models`、`AI agents`、`AIGC`、`technical solution review`；产品/业务背景 `enterprise AI applications`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：架构设计、能力选型和端到端交付提供直接 AI 方案证据，但原文明确不以亲自编码为主，也未证明交付物进入医疗器械产品。

**还缺什么证据**：需要目标业务、AI 交付物、是否医疗产品、本人技术职责与纯项目管理的边界。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 22. 生产主管(MIS)(J19152)

**定位**：mindray，样本 7/20；`job_id=4b0f7feb-9290-41df-beb6-3e6cca77c93b`；原始 JSONL 第 74 行。  
**来源**：https://mindray.zhiye.com/social/detail?jobAdId=4b0f7feb-9290-41df-beb6-3e6cca77c93b  
**审计类型**：可制造性支持不是新产品研发。

**真实原文**

> 熟悉新产品可制造性分析，可制造性需求提炼及验收，产品作业风险及工艺缺陷识别及排查改善能力，熟悉DFMA\QEP\PFMEA\QCP工具应用

**旧规则判断**：`UNCLASSIFIED`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `MANUFACTURING_PROCESS`；辅助职能 空数组；能力 `lean manufacturing`、`DFMA`、`PFMEA`、`production management`、`design for manufacturability`；产品/业务背景 空数组；证据强度 `INDIRECT_TECHNICAL_EVIDENCE`。

**分歧机制**：DFMA、PFMEA 等体现可制造性和工艺风险能力，主职仍是生产主管。旧 UNCLASSIFIED 漏掉能力，但若据此推断新产品开发又会过度。

**还缺什么证据**：需要新产品导入职责占比、是否参与设计评审，以及生产管理与工程开发的实际边界。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：这些技术内容可能仅服务于生产、服务、质量、临床采用或内部运营，并不证明产品研发。

## 23. 高级医学事务专员/经理（体外诊断产品）(J19133)

**定位**：mindray，样本 9/20；`job_id=dedb6254-99a4-4058-a1a8-80a67b4269f9`；原始 JSONL 第 11 行。  
**来源**：https://mindray.zhiye.com/social/detail?jobAdId=dedb6254-99a4-4058-a1a8-80a67b4269f9  
**审计类型**：医学事务中的直接临床研究。

**真实原文**

> 组织开展迈瑞疾病诊断产品全生命周期的相关临床研究，包括纵向课题和横向课题的多中心、单中心研究

**旧规则判断**：`UNCLASSIFIED`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `CLINICAL_RESEARCH`；辅助职能 ['SALES_MARKETING']；能力 `clinical study design`、`multicenter research`、`biostatistics training`、`medical writing`；产品/业务背景 `IVD diagnostic products`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：多中心和单中心临床研究是直接研究证据，但医学事务还可能兼顾学术推广。不能把整条岗位等同于工程研发，也不能因商业辅助职责否定研究活动。

**还缺什么证据**：需要研究设计、执行、统计和写作的本人职责，以及学术推广占比和研究对应产品阶段。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

## 24. 设备资深工程师（试剂）(J19240)

**定位**：mindray，样本 19/20；`job_id=01c937d8-0a37-4806-9ba3-376c29cbd69c`；原始 JSONL 第 68 行。  
**来源**：https://mindray.zhiye.com/social/detail?jobAdId=01c937d8-0a37-4806-9ba3-376c29cbd69c  
**审计类型**：工艺装备开发不是试剂产品开发。

**真实原文**

> 主导并推进设备设计、失效分析、制造、测试验证、验收确认，输出相应的方案与报告

**旧规则判断**：`UNCLASSIFIED`；track=`None`；状态=`SUPPRESSED_BY_FUNCTION_CLASS`。

**独立 AI 预判断**：主职能 `MANUFACTURING_PROCESS`；辅助职能 ['PRODUCT_ENGINEERING']；能力 `automation equipment development`、`URS development`、`mechanical design`、`failure analysis`、`equipment validation`；产品/业务背景 `IVD reagent production`；证据强度 `DIRECT_R&D_EVIDENCE`。

**分歧机制**：设备设计、失效分析、测试验证和验收是直接工程开发，目标是试剂生产装备。标题中的“试剂”只是生产背景，不能推出试剂配方研发。

**还缺什么证据**：需要设备交付对象、是否新开发、是否涉及试剂工艺本身，以及与生产团队的边界。

**人工复核决定**：优先人工复核。AI 自身的替代解释是：该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。

