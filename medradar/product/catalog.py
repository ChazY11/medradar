"""Static product knowledge for MedRadar 2.0.

Everything in this module is *human-curated product knowledge*: which firms are
featured, how the curated tech-track taxonomy is grouped into the eight radar
domains, what each data source means and covers, how each metric is computed,
and which limitations must be shown next to the numbers.

It deliberately contains **no measurement**. Every number the product shows is
computed from ``data/medradar.sqlite`` by :mod:`medradar.product.store`; the
only curated facts here are names, descriptions, source semantics and metric
definitions, so a reader can always tell "curated" from "measured".
"""
from __future__ import annotations

from typing import Any

PRODUCT_VERSION = "2.0.0-mvp"
PRODUCT_SCHEMA = "medradar.product.v1"

#: The five deep-coverage companies required by the MVP brief. ``stats_key`` is
#: the key used by the measurement layer (the store's ``company_key`` or the
#: vendored exact-alias set for the two firms absent from the store roster).
FEATURED_COMPANIES: list[dict[str, Any]] = [
    {
        "key": "medtronic",
        "name_en": "Medtronic",
        "name_zh": "美敦力",
        "ticker": "MDT",
        "exchange": "NYSE",
        "hq_zh": "爱尔兰都柏林（运营总部：美国明尼阿波利斯）",
        "founded": 1949,
        "profile_zh": (
            "全球规模最大的医疗器械企业之一，公开监管记录覆盖心脏节律、心血管介入、"
            "神经调控、外科、糖尿病管理等赛道，且以 PMA（上市前批准）路径为主。"
        ),
        "curated_note": "企业简介为人工整理的产品背景信息，不来自事件数据库。",
    },
    {
        "key": "ge_healthcare",
        "name_en": "GE HealthCare",
        "name_zh": "GE 医疗",
        "ticker": "GEHC",
        "exchange": "NASDAQ",
        "hq_zh": "美国芝加哥",
        "founded": 2023,
        "profile_zh": (
            "2023 年从 GE 分拆独立上市的医疗科技公司，业务集中于医学影像、超声、"
            "患者监护与药物诊断。历史记录中 2023 年以前的实体名称多为 GE Medical Systems。"
        ),
        "curated_note": "企业简介为人工整理的产品背景信息，不来自事件数据库。",
    },
    {
        "key": "philips",
        "name_en": "Philips",
        "name_zh": "飞利浦",
        "ticker": "PHG",
        "exchange": "NYSE / Euronext",
        "hq_zh": "荷兰阿姆斯特丹",
        "founded": 1891,
        "profile_zh": (
            "荷兰健康科技集团，医疗业务覆盖影像系统、患者监护、超声与睡眠呼吸治疗；"
            "公开记录中同时存在大量器械召回，需与产品审批活动分开解读。"
        ),
        "curated_note": "企业简介为人工整理的产品背景信息，不来自事件数据库。",
    },
    {
        "key": "draeger",
        "name_en": "Dräger",
        "name_zh": "德尔格",
        "ticker": "DRW3",
        "exchange": "XETRA",
        "hq_zh": "德国吕贝克",
        "founded": 1889,
        "profile_zh": (
            "德国医疗与安全技术企业，医疗业务以麻醉工作站、呼吸机、患者监护和新生儿护理为主。"
            "该企业不在仓库原有企业名册中，本轮通过逐条精确名称匹配补充映射。"
        ),
        "curated_note": "企业简介为人工整理的产品背景信息，不来自事件数据库。",
    },
    {
        "key": "mindray",
        "name_en": "Mindray",
        "name_zh": "迈瑞医疗",
        "ticker": "300760",
        "exchange": "SZSE",
        "hq_zh": "中国深圳",
        "founded": 1991,
        "profile_zh": (
            "中国医疗设备企业，业务覆盖生命信息与支持（监护、麻醉、呼吸）、体外诊断与医学影像（超声）。"
            "美国 openFDA 记录只反映其在美国的监管活动，不代表其全球产品与研发全貌。"
        ),
        "curated_note": "企业简介为人工整理的产品背景信息，不来自事件数据库。",
    },
]

FEATURED_KEYS = [c["key"] for c in FEATURED_COMPANIES]
FEATURED_BY_KEY = {c["key"]: c for c in FEATURED_COMPANIES}

#: Firms that are absent from ``config/companies_device.json`` and therefore
#: need the vendored exact-string applicant aliases (see entity_aliases.json).
EXTRA_ALIAS_COMPANIES = ("draeger", "mindray")

#: The eight radar domains requested by the brief. Each domain is a *grouping of
#: existing curated track ids* — no new taxonomy is invented. ``tracks`` lists
#: the member track ids; membership is exactly the store's ``tracks`` table.
RADAR_DOMAINS: list[dict[str, Any]] = [
    {
        "id": "patient_monitoring",
        "label_zh": "患者监护",
        "label_en": "Patient Monitoring",
        "tracks": ["patient_monitoring"],
        "blurb_zh": "床旁与中央监护、生命体征、可穿戴远程监测。",
    },
    {
        "id": "medical_imaging",
        "label_zh": "医学影像",
        "label_en": "Medical Imaging",
        "tracks": ["imaging_mr_ct"],
        "blurb_zh": "MR / CT / PET / X-ray 等大型影像设备与软件。",
    },
    {
        "id": "ultrasound",
        "label_zh": "超声",
        "label_en": "Ultrasound",
        "tracks": ["imaging_us"],
        "blurb_zh": "诊断与介入超声、便携与床旁超声。",
    },
    {
        "id": "respiratory",
        "label_zh": "呼吸与通气",
        "label_en": "Ventilation & Respiratory Care",
        "tracks": ["respiratory"],
        "blurb_zh": "呼吸机、麻醉工作站、氧疗与呼吸支持设备。",
    },
    {
        "id": "ivd",
        "label_zh": "体外诊断",
        "label_en": "In-vitro Diagnostics",
        "tracks": ["ivd_immuno", "ivd_molecular", "ivd_poct"],
        "blurb_zh": "免疫诊断、分子诊断与床旁即时检验。",
    },
    {
        "id": "medical_ai",
        "label_zh": "医疗 AI / 软件",
        "label_en": "Medical AI",
        "tracks": ["medical_ai"],
        "blurb_zh": "AI 辅助诊断、SaMD 与医疗软件类产品。",
    },
    {
        "id": "cardiovascular",
        "label_zh": "心血管器械",
        "label_en": "Cardiovascular Devices",
        "tracks": ["cardiac_rhythm", "coronary", "structural_heart", "heart_failure", "ep_pfa", "peripheral_vascular"],
        "blurb_zh": "心脏节律、冠脉与结构心、心衰、电生理与外周血管。",
    },
    {
        "id": "surgical",
        "label_zh": "外科技术",
        "label_en": "Surgical Technology",
        "tracks": ["surgical_robotics", "surgical_energy", "endoscopy", "general_surgery"],
        "blurb_zh": "手术机器人、手术能量器械、内窥镜与普外耗材。",
    },
]

DOMAIN_BY_ID = {d["id"]: d for d in RADAR_DOMAINS}
TRACK_TO_DOMAIN = {t: d["id"] for d in RADAR_DOMAINS for t in d["tracks"]}

#: Metric definitions. ``kinds`` are the store ``events.kind`` values that a
#: metric sums; the product never mixes them without saying so.
METRICS: dict[str, dict[str, Any]] = {
    "approvals": {
        "label_zh": "公开审批/许可记录",
        "label_en": "Public approvals / clearances",
        "kinds": ["510k", "pma"],
        "unit": "件",
        "definition_zh": (
            "美国 FDA 510(k) 实质等同通知与 PMA 上市前批准的公开记录条数之和。"
            "同一条批准可能对应多个产品/型号记录，因此它是“监管记录数”，不是“产品数”。"
        ),
        "caveats": [
            "只覆盖美国市场，不能代表全球注册与销售活动。",
            "510(k) 与 PMA 是不同监管路径，不同企业路径结构不同，直接比较绝对数量会失真。",
            "记录以公开文件条数为单位，同一申请可能拆分多条，需看相对变化而非绝对值。",
        ],
    },
    "510k": {
        "label_zh": "FDA 510(k)",
        "label_en": "510(k) clearances",
        "kinds": ["510k"],
        "unit": "件",
        "definition_zh": "美国 FDA 510(k) 实质等同上市前通知记录条数。",
        "caveats": ["510(k) 是“与已上市产品实质等同”的路径，不等同于技术首创或创新能力。"],
    },
    "pma": {
        "label_zh": "FDA PMA",
        "label_en": "PMA approvals",
        "kinds": ["pma"],
        "unit": "件",
        "definition_zh": "美国 FDA 上市前批准（PMA）记录条数，通常对应较高风险等级的器械。",
        "caveats": ["PMA 主要出现在高风险的 III 类器械，路径差异会放大企业间数量差异。"],
    },
    "recalls": {
        "label_zh": "器械召回记录",
        "label_en": "Device recalls",
        "kinds": ["device_recall"],
        "unit": "条",
        "definition_zh": "美国 FDA 器械召回数据库中的公开记录条数。",
        "caveats": [
            "召回记录反映安全性事件与纠正行动，不能被解读为技术活动或研发强度。",
            "召回数据自 2002 年左右才系统收录，与审批数据的历史深度不同。",
        ],
    },
    "trials": {
        "label_zh": "临床试验注册",
        "label_en": "Registered trials",
        "kinds": ["trial"],
        "unit": "条",
        "definition_zh": "ClinicalTrials.gov 注册记录条数（按申办方映射到企业）。",
        "caveats": [
            "试验注册不等于产品获批或上市；申办方名称与企业实体映射可能不完整。",
            "只有一部分试验记录能映射到器械技术赛道。",
        ],
    },
    "corporate": {
        "label_zh": "8-K 公司事件",
        "label_en": "8-K corporate events",
        "kinds": ["8k_catalyst"],
        "unit": "条",
        "definition_zh": "本项目 SEC EDGAR 8-K 语料中的公司事件记录条数。",
        "caveats": ["8-K 语料窗口为 2015 年起，且未全部完成技术赛道映射，不能与其他指标直接拼接。"],
    },
}

METRIC_ORDER = ["approvals", "510k", "pma", "recalls", "trials", "corporate"]

#: Per-source semantics and coverage caveats. ``coverage_zh`` is the *source
#: level* window; per-company observed windows are computed from the data.
SOURCES: dict[str, dict[str, Any]] = {
    "openfda_device_510k": {
        "label_zh": "FDA 510(k) 器械记录",
        "short_zh": "510(k)",
        "market": "美国",
        "coverage_zh": "1976 年至今（以 openFDA 批量数据实际返回为准）",
        "url_hint": "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm",
        "caveat_zh": "仅美国监管路径；同一条记录不代表一个独立产品。",
    },
    "openfda_device_pma": {
        "label_zh": "FDA PMA 器械记录",
        "short_zh": "PMA",
        "market": "美国",
        "coverage_zh": "1976 年至今（以 openFDA 批量数据实际返回为准）",
        "url_hint": "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPMA/pma.cfm",
        "caveat_zh": "仅美国监管路径，主要覆盖高风险 III 类器械。",
    },
    "openfda_device_recall": {
        "label_zh": "FDA 器械召回记录",
        "short_zh": "召回",
        "market": "美国",
        "coverage_zh": "约 2002 年至今（openFDA 召回库实际收录窗口）",
        "url_hint": "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRES/res.cfm",
        "caveat_zh": "安全性事件记录，不是研发或技术活动。",
    },
    "ctgov": {
        "label_zh": "ClinicalTrials.gov 注册",
        "short_zh": "临床试验",
        "market": "全球（美国注册库）",
        "coverage_zh": "约 2000 年至今（注册库实际记录）",
        "url_hint": "https://clinicaltrials.gov/",
        "caveat_zh": "注册记录不等于上市产品；部分记录无法映射到器械赛道。",
    },
    "sec_edgar_corpus": {
        "label_zh": "SEC EDGAR 8-K 事件语料",
        "short_zh": "8-K",
        "market": "美国上市公司",
        "coverage_zh": "2015 年至 2026 年（本项目语料窗口）",
        "url_hint": "https://www.sec.gov/edgar/search/",
        "caveat_zh": "仅美国上市公司披露；语料未全部完成技术赛道映射。",
    },
    "openfda_drug_drugsfda": {
        "label_zh": "FDA 药品批准记录",
        "short_zh": "药品批准",
        "market": "美国",
        "coverage_zh": "历史药品批准记录",
        "url_hint": "https://www.accessdata.fda.gov/scripts/cder/daf/",
        "caveat_zh": "药品记录，不属于医疗器械分析范围。",
    },
}

#: Evidence tiers shown next to every conclusion. The product may only label a
#: statement with a tier whose definition the system actually enforces.
EVIDENCE_TIERS = {
    "observed": {
        "label_zh": "观察到的事实",
        "label_en": "Observed",
        "desc_zh": "直接由数据库记录计数得到，可逐条展开到原始记录。",
    },
    "detected": {
        "label_zh": "统计探测信号",
        "label_en": "Detected Signal",
        "desc_zh": "用固定统计规则（相对历史基线的 z 分数）从数据中探测出的异常，不等于因果，也不等于预测。",
    },
    "hypothesis": {
        "label_zh": "研究假设",
        "label_en": "Research Hypothesis",
        "desc_zh": "来自研究项目、尚未完成独立验证的推断；本项目当前不提供经过验证的预测。",
    },
}

#: Hard limitations printed on the product pages. These are product policy, not
#: decoration: every aggregate endpoint returns the subset that applies.
LIMITATIONS: dict[str, str] = {
    "us_only": "监管数据只覆盖美国 FDA 记录。美国记录不等于全球产品、注册与研发活动；对迈瑞、德尔格等非美国企业尤其如此。",
    "no_global_rank": "不能用 FDA 记录数量给企业创新能力排名：产品组合、监管路径（510(k)/PMA）、地理市场与披露习惯都不同。",
    "record_not_product": "一条记录不等于一个产品。同一申请可能拆分为多条记录，同一产品也可能多次申报。",
    "recall_not_tech": "召回记录是安全性事件，不能当作技术活动或研发强度。",
    "entity_mapping": "企业归属由申办方/申请人字符串映射得到，存在错配风险；有争议的映射会单独标注。",
    "track_mapping": "技术赛道由 FDA 产品代码映射得到，部分记录无法映射；产品页会显示赛道覆盖率，避免把“未映射”当成“零活动”。",
    "coverage_change": "不同数据源的历史起始时间不同（召回约 2002 起、8-K 约 2015 起），跨期总量上升可能只是数据覆盖扩大。",
    "not_prediction": "当前没有经过前瞻验证的预测模型。产品只展示观察到的变化与统计探测信号，不展示确定性未来结论。",
    "ai_labels": "69 份证据包的 AI 预标注只是规则化初审，不是独立人工真值，不得当作研究结论。",
    "point_in_time": "事件日期与公开可获取日期可能不同；本产品默认使用事件日期，部分视图同时给出发布时间。",
}

#: Cross-source comparability notes for the comparison page.
COMPARABILITY_NOTES = [
    "不同企业的产品组合与监管路径不同：以 PMA 为主的企业与以 510(k) 为主的企业，记录数量天生不同。",
    "美国 FDA 记录不等于全球活动：迈瑞、德尔格的美国记录只是其全球业务的一部分。",
    "各数据源起点不同：召回约 2002 年起收录，8-K 语料 2015 年起，跨源比较必须先对齐时间窗。",
    "因此比较页同时给出绝对记录数、企业内赛道占比与相对全行业的专业化指数，并把不可比之处写在结果旁边。",
]

#: Research studies surfaced in the Research Lab. ``status`` is the honest
#: study status; nothing here claims validated prospective prediction.
STUDIES: list[dict[str, Any]] = [
    {
        "id": "S-027-early-signal-5firms",
        "title_zh": "五家企业早期信号研究（主分支，S-027）",
        "title_en": "Early-signal study, five mandated device firms",
        "branch": "main (merged via PR #6 / #9 / #10 / #11)",
        "period": "2018-01-01 – 2025-12-31（历史窗口）",
        "status_zh": "受限于人工复核：AI 初审完成，人工真值未完成",
        "status_tone": "blocked",
        "question_zh": "在五家指定器械企业的确认性赛道上，公开多源信息能否提前于首次进入事件给出可用的早期信号？",
        "method_zh": (
            "季度 firm×track 面板；Tier B 可用性规则（事件日期 + 30 天）；"
            "8 季度基线；z 分数与持续性两类检测器；69 份证据包按固定规则抽样复核。"
        ),
        "findings_zh": [
            "69 份证据包已做规则化 AI 预标注：45 份 Uncertain、18 份 Routine Iteration、6 份 Not Assessable（均为 agent-preliminary，不是人工真值）。",
            "Pilot 结果为描述性：确认性赛道上评估窗口内可用 onset 数量不足（少于预注册的 10 个下限），H1 既未被支持也未被否定。",
            "跨源检验：ClinicalTrials.gov 的疗法领域编码与器械赛道无法建立可辩护的交叉映射，提前量配对被判定为 NOT_EVALUABLE。",
            "结论：现有证据不足以支持“提前预测”的产品化结论；研究仍待具名人工复核。",
        ],
        "datasets_zh": ["openFDA 器械 510(k)/PMA/召回", "ClinicalTrials.gov", "SEC EDGAR 8-K 语料", "人工复核工作表（69 行）"],
        "reproduce_zh": [
            "python -m pytest tests/test_study_coverage.py tests/test_study_concurrent.py tests/test_study_adjudication.py -q",
            "研究材料：research/studies/early_signal_5firms/（PROTOCOL.md、PILOT_RESULTS.md、ADJUDICATION_AGENT_V1.md、HUMAN_REVIEW_WORKSHEET.xlsx）",
        ],
        "limits_zh": [
            "AI 预标注不等于人工真值；不得用于给检测器打分或宣称 Target B 结论。",
            "确认性赛道覆盖面有限，且医疗器械的“首次进入”在数据上很稀疏。",
        ],
    },
    {
        "id": "C43-hist-v1",
        "title_zh": "Cycle 43：全历史早期预警基准（research/full-history-v1，未合入 main）",
        "title_en": "Cycle 43 — full-history early-warning benchmark (hist_v1)",
        "branch": "research/full-history-v1 @ 969fd0c（本轮只读引用，未合并）",
        "period": "1976-Q1 – 2026-Q2；评估原点 1995–2024",
        "status_zh": "边际支持，尚未达到实用水平",
        "status_tone": "mixed",
        "question_zh": "在完整 1976–2026 器械历史上去掉人工 10 年窗口后，公开多源时序信号能否为企业的首次赛道批准提供提前预警？",
        "method_zh": (
            "53 家企业 × 38 个赛道、528 个 firm×track 对、14,704 条 material event；"
            "扩展窗口评估（30 个评估原点）、B0–B3 基线、公司聚类配对 bootstrap、200 次置换零分布、"
            "提前量前沿与消融；协议在拟合前冻结（含 A1–A5 修正）。"
        ),
        "findings_zh": [
            "预注册主检验边际支持 H1：AP 0.1137 vs 基线 0.0553，Δ +0.0584，95% CI [+0.0020, +0.1213]，置换 p=0.0299。",
            "但最小可检测效应（MDE 0.090）大于观测效应，且未击败双向暴露基线 B3（Δ +0.0438，CI 含 0）。",
            "提前量前沿代价高：1% 预算下 9/94 命中（精确率 0.206、中位提前 5 个季度），56–85 个进入事件被完全漏掉。",
            "融合检验为负：加入试验与论文特征反而降低 AP（−0.0053），H2 未获支持。",
            "泄漏审计发现并修复了一个真实实现缺陷（公司×类别索引未排序），修复后 0/300 重放不一致；首个结果未发布。",
        ],
        "datasets_zh": ["openFDA 器械全历史记录（1976–2026）", "ClinicalTrials.gov", "公开论文计数", "SEC 财务/市场特征"],
        "reproduce_zh": [
            "研究产物位于 research/full-history-v1 分支：experiments/hist_v1/（build_panel.py、eval.py、results.json、REPORT.md）",
            "python -m pytest tests/test_hist_eval.py -q（该分支内）",
        ],
        "limits_zh": [
            "边际显著不等于实用：MDE 大于观测效应，且未击败强基线。",
            "五家指定企业已接近赛道饱和，新进入事件稀少，样本以其他企业为主。",
            "无人类标签、无前瞻校准；在 2027-Q3 之前不可能有成熟的前瞻校准样本。",
        ],
    },
    {
        "id": "R-forecast-registry",
        "title_zh": "预测注册表：已登记的前瞻记录与校准状态",
        "title_en": "Forecast registry and calibration status",
        "branch": "main（research/forecasts、medradar/forecast_registry.py）",
        "period": "2026-11 起登记",
        "status_zh": "无已验证的前瞻校准",
        "status_tone": "negative",
        "question_zh": "模型给出的概率性预测，在时间推移后是否可信？",
        "method_zh": "预注册预测记录 + 到期后按 Brier / 校准曲线评估；预测集合区分真正前瞻与部分回填。",
        "findings_zh": [
            "当前没有任何已成熟并可计算校准误差的前瞻预测集合。",
            "独立审计发现“25 条真正前瞻”的记录实际为 12/25 部分回填，已修正为 13 条。",
            "因此产品不展示任何“已验证预测”；预测相关能力仅以研究实验视图呈现。",
        ],
        "datasets_zh": ["research/forecasts/FORECAST_SET_2026-11-03*.json", "forecast registry"],
        "reproduce_zh": ["python -m pytest tests/test_forecast_registry.py tests/test_forecasts.py -q"],
        "limits_zh": ["没有成熟预测样本之前，任何校准数字都不具备统计意义。"],
    },
    {
        "id": "R-change-detection",
        "title_zh": "变化探测：操作特性与数据密度约束（Cycle 3–4）",
        "title_en": "Change detection: operating characteristics under sparse data",
        "branch": "main / research/change-detection-v1",
        "period": "2016-11 – 2026-09（月度面板 104 个 cell）",
        "status_zh": "已量化局限的负结果",
        "status_tone": "negative",
        "question_zh": "现有公开数据密度下，统计变化探测能否可靠发现真实的活动跃迁？",
        "method_zh": "注入式持久位移回收实验 + 月度/季度两种分辨率 + 检测器排序比较。",
        "findings_zh": [
            "月度面板：在 2% 误报预算下最优检测器仅回收 0.223 的注入位移。",
            "季度分辨率更差（Bayes factor 0.129 vs 朴素 0.025），检测器排序依赖分辨率。",
            "数据密度是约束：2 倍位移在任何诚实预算下都不可检测。",
        ],
        "datasets_zh": ["medradar.sqlite 月度 firm×track 活动面板"],
        "reproduce_zh": ["python -m pytest tests/test_changepoint.py -q"],
        "limits_zh": ["这是负结果：产品中的“统计探测信号”只作为提示，不构成可靠的变化检测保证。"],
    },
    {
        "id": "R-research-agent",
        "title_zh": "既有 Research Agent：确定性 8 工具研究流程",
        "title_en": "Existing deterministic 8-tool research agent",
        "branch": "main（medradar/research_agent.py）",
        "period": "持续可用（离线，无 LLM、无网络）",
        "status_zh": "可运行的研究基础设施（不是产品预测）",
        "status_tone": "neutral",
        "question_zh": "对一家企业×一个赛道，按固定工作流检索事件历史、财务/市场/论文上下文、预测注册表与反证，并给出带引用的研究文档。",
        "method_zh": (
            "问题模板 → 计划 → 工具 → 证据表 → 冲突检测 → 假设（显式标注）→ 反证 → "
            "统计验证 → 引用式综合 → 不确定性 → 研究日志 → 停止条件；所有概率必须来自注册表/冻结模型/训练基率，缺失则明确为 None。"
        ),
        "findings_zh": [
            "该模块是 MedRadar 2.0 研究助手的方法学来源：确定性、无 LLM、每个 observed/derived 声明必须带可核验引用。",
            "产品内的 Research Analyst 复用同一测量层与证据查询（store/evidence_search），但把它面向普通用户重新组织为自然语言问答。",
            "既有 Agent 仍可通过 CLI 使用，用于需要模板化、带反证与预测注册表查询的研究文档。",
        ],
        "datasets_zh": ["medradar.sqlite 事件/财务/市场/论文特征", "forecast registry", "可选 temporal knowledge graph"],
        "reproduce_zh": [
            "python -m medradar.research_agent --list-templates",
            "python -m medradar.research_agent ask --company medtronic --track cardiac_rhythm --template entry_forecast --format markdown",
            "python -m pytest tests/test_research_agent.py -q",
        ],
        "limits_zh": [
            "它是研究工作流，不是经过前瞻验证的预测器；缺失概率不会被补全。",
            "依赖的财务/市场/论文特征覆盖范围有限，且不包含企业内部数据。",
        ],
    },
]

STUDY_BY_ID = {s["id"]: s for s in STUDIES}

#: Questions the deterministic analyst can really answer, shown as examples.
ANALYST_EXAMPLES = [
    "过去五年，迈瑞的超声产品发生了什么变化？",
    "Medtronic 和 Philips 在患者监护领域有哪些区别？",
    "哪些企业在呼吸支持设备领域的公开活动增加？",
    "GE HealthCare 近十年有哪些值得注意的技术变化？",
    "过去三年哪些医疗技术领域出现了明显加速？",
    "对比美敦力、GE 医疗、飞利浦、德尔格和迈瑞在患者监护赛道的公开活动。",
    "德爾格 2024 年有哪些麻醉/呼吸相关的公开审批记录？",
    "Medtronic 最近一次心脏节律相关的 PMA 是什么？",
]

#: What the analyst can and cannot do — printed in the analyst UI.
ANALYST_CAPABILITIES = {
    "can_zh": [
        "企业×技术赛道的公开活动趋势与时间窗对比（观察到的计数）",
        "多家企业在同一赛道 / 同一时间窗的横向比较（含量纲与可比性提示）",
        "技术赛道的加速/减速排名与基于历史基线的统计探测",
        "逐条证据检索：企业、赛道、来源、时间、关键词 → 原始记录与链接",
        "企业里程碑（首次 510(k)/PMA/试验/8-K）与数据覆盖边界",
    ],
    "cannot_zh": [
        "企业内部战略、研发投入、销售额、市场份额（数据库没有这些字段）",
        "全球所有市场的监管活动（只有美国 FDA 记录 + 部分全球试验注册）",
        "经过验证的未来预测（当前没有成熟的前瞻校准）",
        "因果关系判断（例如“因为 X 所以 Y”）",
    ],
}

#: Default analysis windows offered by the UI (years).
WINDOW_CHOICES = [3, 5, 10, 20]
