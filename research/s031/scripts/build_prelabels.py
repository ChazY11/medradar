#!/usr/bin/env python3
"""Build S-031 AI preliminary labels from the frozen 100-posting sample.
No model weights or network access. Every quote is checked against the frozen text.
"""
import csv, json, os, re, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(os.environ.get('S031_OUTPUT_DIR', '/mnt/agents/output'))
WORK = Path(os.environ.get('S031_WORK_DIR', str(ROOT/'research/s031/work')))
records = {}
_record_counts = {}
for line in (WORK/'selected_records.jsonl').open():
    r = json.loads(line)
    co = r['company_key']
    _record_counts[co] = _record_counts.get(co, 0) + 1
    records[(co, _record_counts[co])] = r

D='DIRECT_R&D_EVIDENCE'; I='INDIRECT_TECHNICAL_EVIDENCE'; P='PRODUCT_CONTEXT_ONLY'; N='NON_R&D'; U='INSUFFICIENT_EVIDENCE'; C='CONFLICTING_EVIDENCE'
specs={}
def a(co,n,primary,secondary,caps,products,strength,quote,supports,alt=None,missing=None,review=False):
    specs[(co,n)] = dict(primary=primary,secondary=secondary,caps=caps,products=products,strength=strength,quote=quote,supports=supports,alt=alt,missing=missing,review=review)

def sales(co,n,quote,caps=None,products=None,review=False):
    a(co,n,'SALES_MARKETING',[],caps or [],products or [],P,quote,'原文将职责限定为销售、推广、培训或市场采用；产品术语只构成业务背景。',review=review)
def service(co,n,quote,caps,products=None):
    a(co,n,'FIELD_SERVICE',[],caps,products or [],I,quote,'原文要求安装、维护、诊断或维修能力，但未要求设计或开发新产品。')
def quality(co,n,quote,caps,products=None,review=False):
    a(co,n,'QUALITY_REGULATORY',[],caps,products or [],I,quote,'技术或法规能力用于质量、供应商、验证或合规活动，不能单独证明新研发项目。',review=review)
def clinical(co,n,quote,caps,products=None,secondary=None,review=False):
    a(co,n,'CLINICAL_APPLICATION',secondary or ['SALES_MARKETING'],caps,products or [],I,quote,'原文体现临床或产品应用能力，主要目的为培训、支持或商业采用，不是技术开发。',review=review)
def business(co,n,quote,caps=None):
    a(co,n,'BUSINESS_OPERATIONS',[],caps or [],[],I if caps else N,quote,'原文是经营、采购、财务、人力或行政职责，不构成医疗器械产品研发证据。')
def unavailable(co,n):
    a(co,n,'UNCLASSIFIED',[],[],[],U,'','正文采集失败，只有 URL 中可见的标题线索，不能据此判断职能或研发能力。',alt='URL 标题可提供弱线索，但不足以核验实际职责。',missing='职位正文、职责、任职要求、来源发布日期均缺失。',review=True)

# Medtronic: indexes follow S031_SAMPLE_100.csv within each company.
co='medtronic'
sales(co,1,'At Medtronic, the Sales Representative II, Spine is responsible for making field sales calls, soliciting orders, selling assigned Medtronic Spinal and Biologics products and representing the company in accordance with its policies and in the assigned territory; for maintaining an awareness of local competitive conditions and for reporting back promptly to the district manager.',products=['spine','surgical navigation','robotic guidance'])
sales(co,2,"Achieve and exceed sales targets by driving the adoption of Medtronic's robotic surgery portfolio within an assigned territory",products=['robotic surgery'])
a(co,3,'CLINICAL_APPLICATION',['SALES_MARKETING'],['clinical therapy support','physician training'],['cardiac rhythm therapies'],I,'The Therapy Development Specialist (TDS) provides advanced clinical and technical support for new PVH vascular therapies and products to a wide range of clinical settings and customers.','Development 在标题中指疗法采用与临床支持，正文不是产品开发。',review=True)
a(co,4,'RESEARCH_DEVELOPMENT',['PRODUCT_ENGINEERING'],['mechanical design','Creo','GD&T','tolerance analysis','design for manufacturing','prototyping'],['new product development'],D,'Apply GD&T principles and perform tolerance stack-up analyses to support robust product designs.','职责直接包含机械设计、容差与原型开发。')
a(co,5,'SOFTWARE_ALGORITHM',['RESEARCH_DEVELOPMENT'],['C++','real-time video processing','AI inference','hardware acceleration','embedded systems','low-latency processing'],['surgical video'],D,'Leverage hardware acceleration to develop high-performance, low-latency video capture, processing, AI inference, visualization and streaming software.','直接开发实时视频、AI 推理与硬件加速软件。')
a(co,6,'PRODUCT_ENGINEERING',['SOFTWARE_ALGORITHM','QUALITY_REGULATORY'],['software test automation','hardware-in-the-loop','real-time systems','system verification'],['Affera cardiac ablation'],D,'Test the functionality and performance of systems software in both standalone and hardware-in-the-loop (HIL) test environments','直接建设产品软硬件验证能力，但属于测试验证而非算法研发。',review=True)
a(co,7,'PRODUCT_ENGINEERING',['BUSINESS_OPERATIONS','RESEARCH_DEVELOPMENT'],['systems engineering','system architecture','design verification','design transfer'],['endoscopic devices'],D,'Develop and review system architectures, product requirements, design concepts, specifications, and technical documentation, ensuring engineering decisions are based on sound technical principles, risk management, usability, reliability, and patient safety','正文同时包含产品技术领导和初级项目管理，证明单标签不足。',review=True)
a(co,8,'MANUFACTURING_PROCESS',[],['manufacturing equipment support','troubleshooting','process optimization'],[],I,'The Engineering Technician provides hands-on technical support for manufacturing equipment, production processes, and engineering initiatives.','Engineering Technician 在正文中属于制造运营，不是产品设计。')
a(co,9,'MANUFACTURING_PROCESS',[],['mechanical assembly'],[],I,'May disassemble, modify, rework, reassemble, and test experimental or prototype assemblies and subassemblies according to specifications and under simulated conditions.','原型字样来自职业序列通用表述，本岗位是否实际承担原型任务不明确。',alt='也可能只是装配工职业描述中的可能性条款，不能认定其参与实验原型开发。',missing='未说明原型任务在该岗位实际工作中的频率、项目与交付物。',review=True)
a(co,10,'MANUFACTURING_PROCESS',[],['machining','production equipment operation'],[],I,'Operates light-duty bench- or floor-type machine tools and equipment such as small lathes, power mills, extruding machines, drills or punch presses, power brakes, shears or saws.','按既定规范操作生产设备，不是新研发方向。')
quality(co,11,'Develop Regulatory Strategies for new or modified products for assigned projects.',['regulatory submissions','design and development controls','regulatory strategy'])
quality(co,12,'Coordinate Design of Experiments (DOE) methods for process development and statistical analysis tools for process capability (Cpk/Ppk), ANOVA, Gage Repeatability and Reproducibility (Gage R&R), Attribute Agreement Analysis, and Test Method Validation (TMV).',['design of experiments','PFMEA','verification and validation','statistical analysis','process capability'],review=True)
sales(co,13,'The CoreValve Principal Therapy Consultant achieves sales revenue targets and grows market share for a specified geography by promoting, selling and servicing Medtronic CoreValve and related products, post approval, while ensuring safe adoption and growth.',['clinical case support'],['transcatheter heart valves'],True)
clinical(co,14,'Provide technical expertise on three-dimensional mapping systems and support simple to semi-complex electrophysiology mapping procedures.',['three-dimensional cardiac mapping','clinical electrophysiology'],['cardiac ablation','pulsed field ablation'],review=True)
a(co,15,'MANUFACTURING_PROCESS',[],['manufacturing equipment support','equipment calibration','process control','lean manufacturing'],[],I,'The Engineering Technician is part of Medtronic\'s Operations and Manufacturing function, supporting the production of medical devices used by healthcare providers and patients worldwide.','正文明确归属运营与制造。')
sales(co,16,'Proven experience in commercial operations, sales support, channel management, distributor management, or related business functions',['channel performance analytics'])
a(co,17,'SALES_MARKETING',['CLINICAL_APPLICATION'],['clinical therapy support'],['specialty therapies'],P,'Responsible for medical sales territory growth within Sacramento, CA servicing the Northern California, Central Valley, and Nevada regions including Sacramento, Chico, Redding, Stockton, Modesto, Fresno, Visalia, Reno, and Las Vegas territories for Cardiac Rhythm Management (CRM) department in terms of revenue and implants.','标题与职责均指向专科疗法销售，不是疗法开发。')
a(co,18,'LEGAL_COMPLIANCE',[],[],[],N,'Provides legal advice, counsel and service to internal business clients concerning legal rights, obligations, and privileges of corporations.','法律顾问职责与研发能力建设无直接关系。')
sales(co,19,'Develop and execute regional sales and account strategies to achieve Annual Operating Plan targets, growth objectives and Enterprise Accounts priorities.',['commercial account analytics'])
sales(co,20,'Lead the development and execution of product, portfolio, and market strategies for Cardiac Ablation Solutions across ANZ.',['market analysis'],['cardiac ablation','electrophysiology'],True)

# GE HealthCare
co='ge_healthcare'; unavailable(co,1)
clinical(co,2,'Execute product demonstrations in the operating room with surgical imaging products in presales and postsales environment',['surgical imaging demonstration','clinical workflow support'],['surgical imaging','robotics','navigation'],review=True)
sales(co,3,'Lead and manage a team of sales managers and application specialists as well as distribution channel partners to drive orders and sales in the territory.',['technical product communication'],['intraoperative ultrasound','surgical visualization and guidance'],True)
a(co,4,'CLINICAL_RESEARCH',['QUALITY_REGULATORY'],['clinical study coordination','GCP compliance','ultrasound scanning session management'],['new ultrasound imaging techniques'],D,'Well managed In-house Ultrasound Scanning Sessions are critical for clinical evaluation of new ultrasound imaging techniques.','直接组织新超声成像技术的临床评价研究，但不是工程开发岗位。',review=True)
quality(co,5,'Lead execution of Supplier Quality & Development strategies that support business priorities, including New Product Introductions (NPI), product transfers, and sustaining quality improvement initiatives.',['supplier quality','NPI quality readiness','CAPA','data analytics'],['molecular imaging','computed tomography'])
a(co,6,'BUSINESS_OPERATIONS',['SOFTWARE_ALGORITHM'],['enterprise data governance','SQL','business intelligence','agentic AI','digital twin','predictive analytics','simulation and optimization'],['integrated supply chain'],D,'The agentic AI factory, digital twin, forecasting, simulation and optimization, and generative capabilities are part of the Capabilities portfolio you own – managed with the same roadmap, certification, and ownership discipline as the data products, not as side projects.','直接建设企业 AI 与数据产品能力，但用途是供应链，不应误报为医疗产品 AI 研发。',review=True)
sales(co,7,'Lead product demonstrations and manage digital solution trials to support adoption of Radiation Oncology software and platforms.',['digital solution adoption','customer usage analytics'],['radiation oncology software','MIM software'],True)
service(co,8,'Perform timely and accurate preventative maintenance, installations, and troubleshooting on medical equipment within a hospital or healthcare system to ensure optimal delivery of healthcare services to patients.',['electromechanical troubleshooting','medical equipment installation'],['anesthesia','maternal infant care','diagnostic cardiology'])
a(co,9,'SOFTWARE_ALGORITHM',['SALES_MARKETING'],['Apex','Python','REST API','agentic AI','multi-agent orchestration','Model Context Protocol','MuleSoft','enterprise integration'],['sales enablement'],D,'Configure and develop using Apex, Flow, Python, the REST Query API, Agentforce script, Lightning Actions and HXL as required - following security, change-management, and release controls.','直接开发企业销售工作流 AI 与集成，不是医疗产品软件研发。',review=True)
a(co,10,'BUSINESS_OPERATIONS',['MANUFACTURING_PROCESS'],['capacity planning','manufacturing network analysis','Lean Six Sigma'],[],I,'Support development and evaluation strategic business cases for manufacturing network design, capacity expansion, and resiliency initiatives, including cost–benefit and risk trade‑off analyses.','制造战略与产能分析有技术含量，但没有具体工艺或产品开发交付物。')
business(co,11,'Developing, implement, and manage global procurement strategies for all external manufacturing categories, including contract manufacturing organizations (CMOs) for finished goods, sub-assemblies, and specialized components.',['strategic sourcing','supplier management'])
quality(co,12,'Develops regulatory strategies to help optimize regulatory submission pathways, taking into consideration regulatory requirements (including product testing, clinical data, etc), product claims and country regulatory dependencies to ensure optimized sequencing for submissions.',['regulatory strategy','technical documentation','premarket submissions'])
quality(co,13,'Support a program (plan, prepare and execute) of internal and external audits for QRA.',['GMP auditing','pharmacovigilance','CAPA','quality trend analysis'])
a(co,14,'CLINICAL_APPLICATION',['SALES_MARKETING','PRODUCT_ENGINEERING'],['clinical product evaluation','clinical requirements translation'],['interventional cardiology','CT'],I,'Evaluate new software, systems, and options from a clinical perspective before release.','存在上市前临床评价和需求转化，但主职仍是销售过程中的临床顾问；不可直接算软件研发。',review=True)
sales(co,15,'The Clinical Solutions Specialist, ASC is a customer-facing sales role responsible for growing product penetration within Electrophysiology (EP)-focused Ambulatory Surgery Centers — both existing accounts and net-new (de novo) ASCs in planning or development.',['clinical workflow consulting'],['electrophysiology','ambulatory surgery centers'],True)
service(co,16,'Works independently to trouble shoot and perform basic repairs on assigned equipment.',['CT service','nuclear medicine service','preventive maintenance'],['CT','nuclear medicine'])
sales(co,17,'以区域销售业绩增长为核心，深耕区域医疗市场，优化客户结构与销售渠道，实现公司产品在区域内的市场份额稳步提升，建立良好的品牌口碑。',['market analysis'])
sales(co,18,'Build and drive launch plans per product launch, including internal readiness, training, and milestone tracking (PRD & NCA support).',['launch analytics','competitive intelligence'],['X-ray','digital X-ray AI'],True)
business(co,19,'Drive the adoption of AI and automation to accelerate planning, forecasting, reporting, and analysis while improving accuracy and consistency.',['financial analysis','AI-assisted forecasting','business intelligence'])
a(co,20,'PRODUCT_ENGINEERING',['MANUFACTURING_PROCESS','QUALITY_REGULATORY'],['API process development','synthetic chemistry','scale-up','technology transfer','impurity control','CMC'],['contrast media','molecular imaging agents'],D,'Lead the development and manufacturing of APIs, precursors, and key materials at external CMOs from early development through commercialization.','直接负责药物成分工艺开发、放大和技术转移；API 在此不是软件接口。',review=True)

# Philips
co='philips'; unavailable(co,1)
a(co,2,'SALES_MARKETING',['CLINICAL_APPLICATION'],['clinical sales training','echocardiography','3D imaging','procedural guidance'],['structural heart','intracardiac echocardiography'],P,'As the Clinical Sales Training Specialist for Structural Heart (SH), you will be responsible for developing all Clinical Sales Training programs and delivering sales training material to the field sales force.','临床和成像知识用于销售培训，不是影像算法或器械开发。',review=True)
a(co,3,'SOFTWARE_ALGORITHM',['RESEARCH_DEVELOPMENT'],['C','C++','embedded software','cybersecurity','real-time operating systems','CI/CD'],['hospital patient monitoring'],D,'Design, develop, maintain, and enhance C and C++ applications throughout the software lifecycle, delivering reliable, efficient, and well-documented code that follows established standards and best practices.','直接开发患者监护嵌入式软件。')
a(co,4,'RESEARCH_DEVELOPMENT',['BUSINESS_OPERATIONS'],['systems engineering','hardware engineering','technology roadmap','product development lifecycle'],[],D,'The Innovation and Engineering Leader is responsible for managing and guiding R&D and product implementation, coordinating cross-functional teams, monitoring development progress, staying updated on technical developments, and overseeing personnel for efficient operation of the development function, while assessing emerging technologies for product roadmap integration.','直接领导研发和产品实施，但文本未指明具体新产品或技术路线。')
a(co,5,'SOFTWARE_ALGORITHM',['RESEARCH_DEVELOPMENT'],['C++','real-time operating systems','Linux','Python','CI/CD','API design','performance optimization'],[],D,'Senior Software Technologist who can own and deliver end to end software of a component or set of components.','直接承担软件组件端到端交付；AI 只是开发工具背景，不标 AI 产品研发。',review=True)
sales(co,6,'Drive growth for Philips\' Digital Pathology business across North America by developing and executing strategic go-to-market initiatives that deliver value for customers and commercial results for the business.',['healthcare IT sales'],['digital pathology'],True)
service(co,7,'Utilize tools, support, resources, and escalation processes within required time frames to resolve customer and system problems timely and effectively.',['electronic troubleshooting','mechanical troubleshooting','network troubleshooting','imaging equipment service'],['diagnostic imaging','ultrasound','diagnostic X-ray'])
a(co,8,'CLINICAL_RESEARCH',['RESEARCH_DEVELOPMENT'],['clinical research','feasibility studies','clinical prototype evaluation','evidence generation'],['computed tomography'],D,'Shape CT business strategy by contributing to clinical prototypes, innovation roadmaps, and long-term clinical plans that align with business and marketing objectives.','直接参与临床原型、可行性与新技术证据生成，属于临床研发而非一般应用支持。',review=True)
a(co,9,'MANUFACTURING_PROCESS',['BUSINESS_OPERATIONS'],['production planning','MRP','capacity planning','NPI planning'],[],I,'You\'ll apply your planning expertise to manage our current portfolio and New Product Introductions (NPIs).','NPI 只体现生产计划支持，不等于参与产品设计。')
a(co,10,'MANUFACTURING_PROCESS',[],['precision assembly','soldering','wiring'],['MRI superconducting magnets'],I,'This is an excellent opportunity to be a key player at our Latham, New York facility where we manufacture magnets for MRI machines.','MRI 磁体是生产背景，装配岗位本身没有研发设计职责。')
quality(co,11,'Helps to conduct the assessment of impact to Process Failure Mode and Effects Analysis (PFMEA) and associated controls in relation to design changes and assists in Manufacturing Process Development and Design Transfer activities.',['PFMEA','CAPA','process validation','statistical analysis','design transfer'])
quality(co,12,'Conducts & reviews DFMAT (Design for Manufacturing and Assembly Technique), SRPQP (Specification review and part qualification plan), MSA (Measurement System Analysis), PFMEA (Process Failure Mode and Effects Analysis), Control Plan, SPC (Statistical Process Control), PV&V (Process Validation and Verification), FAI (First Article Inspection), LRA (Line Readiness Assessment), and SICR (Supplier Initiated Change Request).',['DFMA','MSA','PFMEA','SPC','process validation','APQP','supplier quality'],review=True)
clinical(co,13,'Apporter un soutien supplémentaire à l’équipe Clinical Application Specialist Ultrasons pour les démonstrations, les installations et les formations clients.',['ultrasound demonstration','customer training'],['ultrasound'])
clinical(co,14,'Providing clinical and technical expertise to customers, users and other members of the Clinical Application Team by training them in order to optimize the usage of our products.',['ultrasound clinical application','customer training'],['ultrasound'])
a(co,15,'PRODUCT_ENGINEERING',['RESEARCH_DEVELOPMENT'],['cryogenic systems','superconducting magnets','mechanical design','prototype testing','3D modeling'],['MRI'],D,'Assist in the design, assembly, and testing of cryogenic systems and superconducting magnets.','实习生也直接参与低温与超导磁体设计、装配和原型测试。')
sales(co,16,'Lead the Philips Mobile C-arm (MOS) business towards profitable growth.',['capital equipment sales'],['mobile C-arm','image guided therapy'])
sales(co,17,'You will assist in the planning, execution and monitoring of marketing campaigns across various channels (digital, social media, gaming, TVC and others).',['market research'],['male grooming'])
business(co,18,'Conducts inventory analysis, handles supply chain master data setup and maintenance, manages product life cycles, takes ownership of inventory management, implements buy-item stock and replenishment policies, monitors item changes, and implements supplier-managed and owned inventories within enterprise resource planning (ERP) software.',['ERP','inventory optimization','supply chain analytics'])
a(co,19,'FIELD_SERVICE',['SALES_MARKETING'],['healthcare IT integration','computer networking','cybersecurity','system maintenance','VMware','Microsoft SQL'],['hospital patient monitoring'],I,'Lead the deployment, configuration, integration, optimization, maintenance, and remediation of complex patient monitoring and software solutions across servers, wireless networks, and routing and switching.','高级技术交付与维护能力明确，但职责是客户环境部署和服务合同，不是产品软件开发。',review=True)
business(co,20,'Supporting the process to complete and correct the order information until the order is ready to be booked.')

# Dräger
co='draeger'; unavailable(co,1)
a(co,2,'RESEARCH_DEVELOPMENT',['BUSINESS_OPERATIONS'],['agile program management','SAFe','development partner management'],['neonatal care'],D,'Entwicklungsprojekte mit externen Kooperations- und Entwicklungspartnern steuern und vereinbarte Qualitäts-, Termin- und Projektziele verantworten','直接管理医疗技术开发项目，但没有证据支持某一具体工程能力。')
a(co,3,'PRODUCT_ENGINEERING',['RESEARCH_DEVELOPMENT'],['industrial design','bionic structures','usability engineering','SolidWorks'],['medical device accessories'],D,'ein funktionales Produktdesign bei der gestalterischen Konzeption sicherstellen','直接参与产品外观、结构和可用性设计。')
a(co,4,'SOFTWARE_ALGORITHM',['RESEARCH_DEVELOPMENT','BUSINESS_OPERATIONS'],['embedded software','C++','software project management','software integration'],['neonatal care'],D,'Technische Mitverantwortung für die Embedded-Software im Bereich Neonatal Care über den gesamten Lebenszyklus — von Spezifikation und Implementierung über Test und Optimierung bis zur Serienbetreuung','同时承担嵌入式软件技术工作与软件项目领导。')
a(co,5,'SOFTWARE_ALGORITHM',['RESEARCH_DEVELOPMENT'],['Qt6','QML','C++','embedded UI','cross-platform software','automated testing'],['anesthesia','ventilation','incubators','patient monitoring'],D,'Im agilen Team bringst du dich bei Spezifikation, Umsetzung, Test und Optimierung zentraler UI-Softwarekomponenten für unsere Produkte aktiv ein.','直接开发跨产品复用的嵌入式 UI 平台组件。')
service(co,6,'Perform with sole responsibility all tasks in Life Cycle of devices (installation, maintenance, repair, corrective actions, etc.)',['medical device installation','maintenance','repair','basic networking'])
a(co,7,'SALES_MARKETING',['FIELD_SERVICE'],['BIM','3D product configuration','technical proposal design'],['workplace infrastructure','supply units','operating lights'],I,'Du kommer att ta fram tekniska lösningar baserade på kundspecifikationer, genom att omvandla kundens behov och teknisk kapacitet till detaljerade tekniska erbjudanden, lösningar och förslag.','按客户规格做配置和技术方案，属于销售工程，不等于新产品开发。',review=True)
a(co,8,'MANUFACTURING_PROCESS',[],['automated production','machine setup','process control','fault analysis'],['respiratory filters'],I,'Sie bestücken und bedienen Maschinen und Produktionsanlagen im Bereich Atemfilterfertigung und führen auftragsbezogene Rüstarbeiten nach Arbeitsanweisungen (inkl. Einrichtparametern) und Prozessanweisungen.','自动化产线操作、换型和故障处理，没有新工艺开发职责。')
quality(co,9,'Analyse von Qualitätsabweichungen sowie Einleitung und Nachverfolgung geeigneter Korrektur- und Verbesserungsmaßnahmen unter Anwendung etablierter Qualitätsmethoden wie FMEA, 8D, APQP etc.',['FMEA','8D','APQP','process validation'],['respiratory filters'])
quality(co,10,'Prüfstrategie gemäß Anforderungen festlegen und Prüfpläne erstellen bzw. anpassen',['supplier quality','inspection planning','first article inspection'])
quality(co,11,'Reklamationsanalyse: Sie erkennen Muster und Ursachen über Produkte und Prozesse hinweg, priorisieren Handlungsbedarfe und schlagen Lösungen vor.',['failure analysis','complaint trend analysis','SAP'],['safety devices','measurement technology'])
service(co,12,'Du bist verantwortlich für die Serviceleistungen und Wartungsarbeiten von stationärer und mobiler Gasmesstechnik sowie Atemschutz.',['gas detection service','respiratory protection service','electrical troubleshooting'],['gas measurement','respiratory protection'])
service(co,13,'Du führst Wartungs-, Service- und Funktionskontrollen an Monitoring-Geräten und -Systemen durch.',['patient monitoring service','IT networking','software updates'],['monitoring','anesthesia','ventilation','pediatrics'])
service(co,14,'Tragbare Gaswarngeräte und stationäre Gaswarnanlagen bei unseren Kunden vor Ort zu warten, zu reparieren und Instand zu halten',['mechatronics','gas detection maintenance'],['gas detection'])
sales(co,15,'Umsatzverantwortung: Sie kennen alle Kennziffern Ihres Kundenportfolios, erstellen Potenzial- und Umsatzprognosen und übernehmen Verantwortung für Ihre Verkaufszahlen.',['technical project sales'],['laboratory gas supply systems'])
sales(co,16,'Prepare and submit quotations, technical proposals, and compliance documents.',['technical sales','gas detection knowledge','ATEX','IECEx'],['oil and gas safety','gas detection','respiratory protection'])
business(co,17,'Sie setzen die Einkaufsstrategie für unsere Materialsegmente und Lieferanten in enger Abstimmung mit dem Commodity Management um.',['strategic sourcing','mechanical components procurement'])
business(co,18,'Sie verantworten das Bid- und Claim Management für nationale und internationale Kundenprojekte bei Dräger Engineered Solutions.',['bid management','contract risk analysis'])
a(co,19,'FIELD_SERVICE',[],['gas supply installation','soldering','welding'],['hospital gas supply'],I,'Du installierst „Technik für das Leben“ in verschiedenen Krankenhausbereichen und sorgst dafür, dass die Gasversorgung zuverlässig funktioniert.','职业培训内容是医院供气设施安装，不是医疗器械研发。')
a(co,20,'BUSINESS_OPERATIONS',['SOFTWARE_ALGORITHM'],['client device management','Windows','Linux','macOS','IT lifecycle management'],[],I,'Client Management & Lifecycle (HW/OS), Support aller Plattformen (Windows, Linux, MacOS etc.)','企业内部终端与 IT 产品管理，不是医疗设备软件或产品研发。',review=True)

# Mindray
co='mindray'
a(co,1,'PRODUCT_ENGINEERING',['MANUFACTURING_PROCESS','RESEARCH_DEVELOPMENT'],['IVD reagent process development','design transfer','process validation','scale-up'],['IVD reagents'],D,'主要负责试剂产品制造工艺开发及工艺验证工作','直接承担试剂工艺开发、验证与放大，不是单纯生产操作。')
a(co,2,'SOFTWARE_ALGORITHM',['RESEARCH_DEVELOPMENT'],['embedded software','C++','UML','Qt','Linux'],['anesthesia machines','ventilators','CRRT'],D,'负责麻醉呼吸的软件产品开发，比如CRRT，麻醉机、呼吸机等医疗设备的嵌入式软件开发','直接开发麻醉呼吸设备嵌入式软件。')
business(co,3,'根据区域业务需求，准确、及时的对销售数据进行统计与分析，为各级业务领导提供销售报表，监控和通报各项运营指标，推动区域业务健康、稳定的发展',['sales data analysis','customer master data'])
a(co,4,'PRODUCT_ENGINEERING',['SOFTWARE_ALGORITHM','BUSINESS_OPERATIONS'],['AI solution architecture','data architecture','large language models','AI agents','AIGC','technical solution review'],['enterprise AI applications'],D,'参与 AI 能力平台、数据平台或智能应用的整体架构设计与能力选型，推动标准化、模块化与可复用解决方案沉淀','直接负责 AI 方案、架构选型与项目交付，但明确不以亲自编码为主，且未证明用于医疗器械产品。',review=True)
a(co,5,'PRODUCT_ENGINEERING',['QUALITY_REGULATORY'],['functional verification','performance verification','reliability testing','test method development','risk management','regulatory standards'],['defibrillators','patient monitors','infusion pumps'],D,'负责产品开发过中功能、性能及可靠性验证','直接参与产品开发验证和测试方法研究。')
sales(co,6,'负责在所属区域进行超声影像专项产品的销售工作',['ultrasound product knowledge'],['ultrasound imaging'])
a(co,7,'MANUFACTURING_PROCESS',[],['lean manufacturing','DFMA','PFMEA','production management','design for manufacturability'],[],I,'熟悉新产品可制造性分析，可制造性需求提炼及验收，产品作业风险及工艺缺陷识别及排查改善能力，熟悉DFMA\\QEP\\PFMEA\\QCP工具应用','主职生产管理，兼有新产品可制造性支持；不能由此推断新产品方向。')
a(co,8,'MANUFACTURING_PROCESS',['QUALITY_REGULATORY'],['CNC machining','titanium alloy processing','cobalt chromium molybdenum processing','OEE','SMED','TPM'],['orthopedic implants'],I,'参与新设备新工艺导入爬坡','核心职责是骨科植入物生产交付、质量与效率，新设备导入为辅助证据。')
a(co,9,'CLINICAL_RESEARCH',['SALES_MARKETING'],['clinical study design','multicenter research','biostatistics training','medical writing'],['IVD diagnostic products'],D,'组织开展迈瑞疾病诊断产品全生命周期的相关临床研究，包括纵向课题和横向课题的多中心、单中心研究','直接组织产品临床研究，但兼有学术推广和医学教育，不等于试剂工程研发。',review=True)
clinical(co,10,'负责区域内产品售前售后支持及临床应用培训，销售及渠道专业化培训及渠道人员培养',['ventilator operation','anesthesia clinical application','hemodynamics','respiratory mechanics'],['anesthesia machines','ventilators','patient monitoring'])
service(co,11,'负责医疗信息化服务项目的发掘、实施与维护',['healthcare IT implementation','system maintenance'],['medical informatics'])
sales(co,12,'整体市场分析，市场策略的研究输出，从专业的角度指导销售开展超声工作',['ultrasound clinical knowledge','market analysis'],['ultrasound imaging'])
sales(co,13,'负责区域内超声影像专项产品的市场调研，市场信息收集、分析，推广活动以及产品的宣传和培训',['ultrasound clinical application','market research'],['ultrasound imaging'])
business(co,14,'员工技能培养体系、课程体系的建设及优化')
business(co,15,'密切关注国家及地方各项政策，研判政策走向，及时做好分析解读工作，提出有价值的意见与建议',['policy analysis'])
sales(co,16,'负责所属区域内非公市场全线产品的销售工作')
a(co,17,'CLINICAL_APPLICATION',['SALES_MARKETING'],['immunoassay clinical interpretation','clinical training','medical literature analysis'],['IVD immunodiagnostics','chemiluminescence'],I,'熟悉化学发光的行业发展、具备深厚的项目专业知识与基础，能够独立进行复杂场景的临床报告分析，客户沟通，具备学术推广思维与相应工作经验','具备临床检验专业能力，但职责为价值传播、培训和营销支持，不是免疫试剂开发。',review=True)
sales(co,18,'负责俄罗斯西伯利亚监护产品的销售工作，根据销售目标指定计划并执行',['international channel sales'],['patient monitoring'])
a(co,19,'MANUFACTURING_PROCESS',['PRODUCT_ENGINEERING'],['automation equipment development','URS development','mechanical design','failure analysis','equipment validation'],['IVD reagent production'],D,'主导并推进设备设计、失效分析、制造、测试验证、验收确认，输出相应的方案与报告','直接开发试剂生产非标自动化设备，属于工艺装备开发而非试剂产品研发。',review=True)
a(co,20,'FIELD_SERVICE',['SALES_MARKETING'],['technical support','engineer training','medical device troubleshooting'],['life information and support'],I,'技术支持：内外部团队技术支持，重大问题、大型项目、新产品支持、客户需求、问题上升以及反馈。','新产品支持只是技术支持场景，不能证明该岗位开发新产品。',review=True)

DEFAULT_ALT={
 D:'该招聘也可能属于既有产品维护、团队扩编或常规项目交付，不能仅凭单条岗位推断新研发战略。',
 I:'这些技术内容可能仅服务于生产、服务、质量、临床采用或内部运营，并不证明产品研发。',
 P:'产品知识可能只用于销售、培训、市场采用或客户沟通，不能证明技术开发。',
 N:'即使企业整体从事研发，也不能把该非研发岗位当作研发能力证据。',
 U:'可用文本不足，任何进一步分类都会超出证据。',
 C:'文本中的不同线索可能对应不同团队或混合职责，需要人工核验。'
}
DEFAULT_MISSING='未说明项目阶段、是否新增编制、具体团队边界及可归属的产品交付物；单条快照不能证明战略变化。'

def ws(s): return re.sub(r'\s+',' ',unicodedata.normalize('NFC',s or '')).strip()

sample=list(csv.DictReader((OUT/'S031_SAMPLE_100.csv').open(encoding='utf-8-sig')))
counts={}
items=[]
for row in sample:
    co=row['company']; counts[co]=counts.get(co,0)+1; n=counts[co]
    key=(co,n)
    if key not in specs: raise AssertionError(f'missing spec {key}')
    s=specs[key]; r=records[key]
    assert r['posting_id']==row['job_id'],(key,r['posting_id'],row['job_id'])
    desc=r.get('job_description') or ''
    quotes=[]
    if s['quote']:
        assert ws(s['quote']) in ws(desc),f'quote not found {key}: {s["quote"]}'
        quotes=[{'quote':s['quote'],'supports':s['supports'],'match_policy':'exact_text_after_unicode_whitespace_normalization'}]
    item={
      'schema_version':'s031-ai-prelabel-v1','study_id':'S-031','label_status':'AI_PRELIMINARY_LABEL',
      'preliminary_label_source':'AI_PRELIMINARY_LABEL',
      'company':co,'sample_index':n,'job_id':row['job_id'],'job_title':row['job_title'],
      'source_url':row['source_url'],'source_jsonl_line':int(row['source_jsonl_line']),
      'raw_record_sha256':row['raw_record_sha256'],'content_sha256':row['content_sha256'],
      'role_function':{'primary':s['primary'],'secondary':s['secondary']},
      'technical_capabilities':s['caps'],'product_business_context':s['products'],
      'rd_evidence_strength':s['strength'],'exact_evidence_quotes':quotes,
      'support_explanation':s['supports'],
      'alternative_explanation':s['alt'] or DEFAULT_ALT[s['strength']],
      'missing_information':s['missing'] or DEFAULT_MISSING,
      'needs_human_review':bool(s['review']),
      'human_review_reason':'困难产品背景、混合职能、证据边界或采集缺陷需要复核。' if s['review'] else '常规复核；未标记为优先争议案例。',
      'not_truth_assertion':'AI 预标注，不是人工金标准，不得用于计算准确率、Precision、Recall 或 F1。'
    }
    items.append(item)
assert len(items)==100 and len(specs)==100,(len(items),len(specs))
with (OUT/'S031_AI_PRELABELS.jsonl').open('w',encoding='utf-8') as f:
    for x in items: f.write(json.dumps(x,ensure_ascii=False)+'\n')
print('wrote',len(items),'labels')
from collections import Counter
print('strength',dict(Counter(x['rd_evidence_strength'] for x in items)))
print('primary',dict(Counter(x['role_function']['primary'] for x in items)))
print('priority human review',sum(x['needs_human_review'] for x in items))
