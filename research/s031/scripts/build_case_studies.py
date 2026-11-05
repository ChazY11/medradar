#!/usr/bin/env python3
"""Render 24 auditable S-031 case studies from frozen labels and rule outputs."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(os.environ.get('S031_OUTPUT_DIR', '/mnt/agents/output'))
WORK = Path(os.environ.get('S031_WORK_DIR', str(ROOT / 'research/s031/work')))


def load(path):
    with path.open(encoding='utf-8') as f:
        return [json.loads(x) for x in f if x.strip()]


labels = {(x['company'], x['sample_index']): x for x in load(OUT / 'S031_AI_PRELABELS.jsonl')}
old = {(x['company'], x['sample_index']): x for x in load(WORK / 'legacy_rule_comparison.jsonl')}
records = {}
counts = Counter()
for r in load(WORK / 'selected_records.jsonl'):
    co = r['company_key']
    counts[co] += 1
    records[(co, counts[co])] = r

# company, sample index, audit type, mechanism, additional evidence needed, review priority,
# optional extra verbatim quote
CASES = [
    ('medtronic', 2, '产品—能力负对照', '标题没有说明研发对象，正文把目标写成销售机器人产品组合。旧规则的商业门槛在这里发挥了正确作用；机器人是所售产品，不是岗位开发的能力。', '若要把机器人研发归因到该岗位，需要具体设计、控制、导航或软件交付职责；当前还需确认其是否仅承担销售指标。', '常规复核，保留为高价值负对照', None),
    ('medtronic', 3, '标题语义与职能分歧', 'Development 在标题里像产品开发，正文却是临床技术支持。旧规则把它归为商业/其他过粗，AI 则必须防止把 Development 直译为研发。', '需要团队归属、日常时间分配及是否负责产品设计或临床方案开发。', '优先人工复核', None),
    ('medtronic', 4, '漏掉具体机械研发能力', '旧函数类识别到 CORE_R&D，但既有 track 没有承接 GD&T、容差分析和原型等机械设计能力。没有产品 track 不等于没有研发内容。', '需要对应产品、项目阶段，以及这些设计活动属于新产品还是既有产品维护。', '常规复核，用于能力词表验证', None),
    ('medtronic', 5, '漏掉软件与视频能力', '旧规则识别软件函数，却没有把实时视频、AI inference、硬件加速和低延迟处理转成能力证据。单一 medical_ai 产品 track 无法表达这些工程差异。', '需要确认软件最终部署产品、AI 模型任务和是否属于新开发而非维护。', '优先人工复核', None),
    ('medtronic', 6, '研发子类型混淆', 'HIL 和实时系统验证是直接产品研发证据，但它是测试验证能力，不应被改写成 AI 或算法研发。旧规则只给 ALGORITHM_SOFTWARE，丢失了工程交付类型。', '需要被测系统、验证对象、测试平台是否新开发，以及与 Affera 产品的实际关系。', '优先人工复核', None),
    ('medtronic', 7, '混合职能与旧函数误判', '正文明确包含系统架构、产品需求和设计概念，同时标题又包含项目管理。旧规则落到 QUALITY_REGULATORY，说明标题局部词和单标签会掩盖主交付物。', '需要工程与项目管理的职责比例、汇报线及风险/可用性工作是否只是辅助职责。', '优先人工复核', None),
    ('medtronic', 12, '质量技术能力不等于产品研发', 'DOE、统计、Gage R&R 和测试方法验证是强技术能力，但主职仍是质量与工艺能力保障。把它升为新产品研发或贬为无技术内容都不准确。', '需要确认 DOE 服务的具体工艺、是否承担新过程开发，以及质量与研发团队的边界。', '优先人工复核', None),
    ('ge_healthcare', 1, '正文缺失', '原始记录为 DETAIL_FAILED，标题和正文不可用。旧规则与 AI 都没有可靠文本可判定；此时不赋能力标签是研究结论，而不是低覆盖率失败。', '需要重新合法采集正文，或获得可审计的 archived copy；不能从 URL slug 反推职责。', '优先人工复核，先补数据再标注', None),
    ('ge_healthcare', 4, '临床研究与工程研发边界', '原文支持新超声成像技术的临床评价，是直接临床研究证据；它没有证明该协调员开发超声硬件或成像算法。', '需要研究方案职责、是否参与产品需求定义，以及临床评价对应的具体研发项目。', '优先人工复核', None),
    ('ge_healthcare', 6, '企业内部 AI 与医疗产品 AI 混淆', '岗位确实建设 agentic AI、digital twin 等直接技术能力，但组织与流程都属于 Integrated Supply Chain。旧规则给 medical_ai 会把“真实 AI 能力”误读成“医疗产品 AI”。', '需要能力交付物是否进入患者护理产品，还是仅服务供应链预测、计划和运营。', '优先人工复核', 'We are seeking a Director to lead AIS ISC Digital & AI Capabilities, the AI, analytics, and data organization within the AIS Integrated Supply Chain.'),
    ('ge_healthcare', 9, '商业门槛误杀真实软件开发', '标题中的 Sales Enablement 触发商业类，正文却明确要求 Apex、Python、REST API 等开发。它是直接软件研发，但交付物服务销售体系，不是医疗产品软件。', '需要确认开发的系统、部署环境和交付物；还需排除仅配置低代码而没有实际开发的情况。', '优先人工复核', None),
    ('ge_healthcare', 20, '多义词与漏掉工艺开发', 'API 在本文是 active pharmaceutical ingredient，不是软件接口。正文另有早期开发、工艺优化、放大和技术转移；旧 UNCLASSIFIED 不能代表没有研发。', '需要确认外协 CMO 模式下企业自身掌握哪些工艺开发活动，以及对应产品是否属于医疗器械研究范围。', '优先人工复核', 'As API Lead, you provide technical leadership for the development and manufacturing of precursors and active pharmaceutical ingredients (APIs) through external Contract Manufacturing Organizations (CMOs).'),
    ('philips', 5, '开发工具与产品能力混淆', '旧规则给 patient_monitoring 与直接软件交付可以并存，但 Copilot 只是提高软件工程效率的工具背景，不能额外推出医疗 AI 研发。', '需要所交付组件的产品归属、软件类型，以及是否实际包含模型或算法开发。', '常规复核，保留 AI 工具负对照', 'Stays current with emerging technologies and industry trends such as use on Copilot and other AI platforms for efficiency in software engineering.'),
    ('philips', 8, '临床研发而非工程研发', '临床 prototype、可行性研究和证据生成是直接研究活动。旧 imaging_mr_ct 提供产品方向，但不能替代对“临床研究”与“CT 工程开发”的区分。', '需要是否参与工程需求、原型设计，还是主要负责临床方案、执行与证据生成。', '优先人工复核', None),
    ('philips', 15, '商业/弃答门槛漏掉产品工程', '旧规则未识别函数并压制 track；正文却明确要求低温系统和超导磁体的设计、装配与测试。这是具体产品工程证据，不只是 MRI 产品词。', '需要 co-op 的实际责任边界、设计独立性和项目是否属于既有 MRI 产品维护。', '优先人工复核', None),
    ('philips', 19, '复杂客户实施不等于产品开发', '部署、集成、网络和维护要求很强医疗 IT 能力，但交付发生在客户环境。没有软件设计或产品需求交付时，不应因 patient monitoring 背景升为研发。', '需要是否开发可复用产品组件、是否只配置现有系统，以及客户反馈是否进入正式研发流程。', '优先人工复核', None),
    ('draeger', 4, '软件与项目管理混合职能', '正文覆盖嵌入式软件全生命周期，同时标题包含子项目领导。旧 UNCLASSIFIED 与技术内容不符；只标软件也会丢失项目交付职责。', '需要技术工作与项目领导的时间比例，以及量产维护和新开发各自占比。', '优先人工复核', None),
    ('draeger', 7, '销售工程与产品开发边界', 'BIM/3D 配置和技术方案是明确能力，但用途是客户报价、产品配置和提案。旧 SALES_ADMIN_OTHER 遮住能力细节，直接改标研发又会越过证据。', '需要是否开发 BIM 工具本身，还是使用既有工具为客户配置产品。', '优先人工复核', 'Du kommer att ha tillgång till 3D ritprogram där du konfigurerar produkterna för att kunna visualisera lösningar till kunderna.'),
    ('draeger', 20, 'Device 多义与企业 IT 边界', 'Client Management、Windows/Linux/macOS 表明 Device Management 指企业终端，而非医疗设备。技术能力真实存在，但证据只支持企业 IT 运营。', '需要管理对象清单和是否涉及医疗设备接入、医疗器械软件或临床系统。', '优先人工复核', None),
    ('mindray', 1, '中文规则覆盖与工艺研发', '旧规则对中文标题和正文未给出函数，但原文直接说明试剂制造工艺开发与验证。工艺研发是直接开发证据，不应与试剂配方研发混写。', '需要是否同时负责配方、反应体系或仅生产工艺，以及放大和验证对应的产品阶段。', '优先人工复核', None),
    ('mindray', 4, 'AI 产品经理的证据边界', '架构设计、能力选型和端到端交付提供直接 AI 方案证据，但原文明确不以亲自编码为主，也未证明交付物进入医疗器械产品。', '需要目标业务、AI 交付物、是否医疗产品、本人技术职责与纯项目管理的边界。', '优先人工复核', '指导并评审技术实现方案（不以亲自编码为主），确保 AI 架构、数据方案与系统设计的可行性与可扩展性'),
    ('mindray', 7, '可制造性支持不是新产品研发', 'DFMA、PFMEA 等体现可制造性和工艺风险能力，主职仍是生产主管。旧 UNCLASSIFIED 漏掉能力，但若据此推断新产品开发又会过度。', '需要新产品导入职责占比、是否参与设计评审，以及生产管理与工程开发的实际边界。', '优先人工复核', None),
    ('mindray', 9, '医学事务中的直接临床研究', '多中心和单中心临床研究是直接研究证据，但医学事务还可能兼顾学术推广。不能把整条岗位等同于工程研发，也不能因商业辅助职责否定研究活动。', '需要研究设计、执行、统计和写作的本人职责，以及学术推广占比和研究对应产品阶段。', '优先人工复核', None),
    ('mindray', 19, '工艺装备开发不是试剂产品开发', '设备设计、失效分析、测试验证和验收是直接工程开发，目标是试剂生产装备。标题中的“试剂”只是生产背景，不能推出试剂配方研发。', '需要设备交付对象、是否新开发、是否涉及试剂工艺本身，以及与生产团队的边界。', '优先人工复核', None),
]


def ws(s):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', s or '')).strip()


lines = [
    '# S-031 争议案例研究：24 条真实岗位',
    '',
    '这些案例用于解释分类机制和证据边界，不是人工金标准，也不是旧规则或 AI 的错误率统计。每条均可凭公司、样本序号、岗位 ID 和原始行号回查。旧规则版本为 `recruitment_taxonomy_rules_2026-11-04b`；独立判断均为 `AI_PRELIMINARY_LABEL`。',
    '',
    '阅读方法：先看原文，再看旧规则和 AI 预判断，最后问“还需要什么证据”。“优先人工复核”表示争议值得投入人工时间，不表示 AI 判断必然错误。',
    ''
]

for i, (co, n, kind, mechanism, needed, review, extra) in enumerate(CASES, 1):
    key = (co, n)
    a, o, r = labels[key], old[key], records[key]
    quote = a['exact_evidence_quotes'][0]['quote'] if a['exact_evidence_quotes'] else None
    desc = r.get('job_description') or ''
    if quote:
        assert ws(quote) in ws(desc)
    if extra:
        assert ws(extra) in ws(desc), (key, extra)
    legacy = o['legacy']
    role = a['role_function']
    caps = '、'.join(f'`{x}`' for x in a['technical_capabilities']) or '空数组：没有充分能力证据'
    products = '、'.join(f'`{x}`' for x in a['product_business_context']) or '空数组'
    title = a['job_title'] or '[标题缺失]'
    lines += [
        f'## {i}. {title}',
        '',
        f'**定位**：{co}，样本 {n}/20；`job_id={a["job_id"]}`；原始 JSONL 第 {a["source_jsonl_line"]} 行。  ',
        f'**来源**：{a["source_url"]}  ',
        f'**审计类型**：{kind}。',
        '',
        '**真实原文**',
        '',
        f'> {quote}' if quote else '> 无可用正文；原始采集状态为 DETAIL_FAILED，故不提供伪造引文。',
        '',
    ]
    if extra:
        lines += [f'> {extra}', '']
    lines += [
        f'**旧规则判断**：`{legacy["function_class"]}`；track=`{legacy["track_id"]}`；状态=`{legacy["track_status"]}`。',
        '',
        f'**独立 AI 预判断**：主职能 `{role["primary"]}`；辅助职能 {role["secondary"] or "空数组"}；能力 {caps}；产品/业务背景 {products}；证据强度 `{a["rd_evidence_strength"]}`。',
        '',
        f'**分歧机制**：{mechanism}',
        '',
        f'**还缺什么证据**：{needed}',
        '',
        f'**人工复核决定**：{review}。AI 自身的替代解释是：{a["alternative_explanation"]}',
        ''
    ]

path = OUT / 'S031_CASE_STUDIES.zh-CN.md'
path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('wrote', path, 'cases', len(CASES))
