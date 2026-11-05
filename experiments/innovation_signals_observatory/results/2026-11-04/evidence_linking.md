# 证据关联 · 简要机器摘要（WP2c）

- 生成时间（UTC）：`2026-11-04T14:16:42+00:00`
- 快照：`D:\DEPPSKK\worktrees\phase4\experiments\innovation_signals_observatory\results\2026-11-04\jobs_medtronic.jsonl`（AUTHORITATIVE，文件行数 n=994，按 posting_id 去重后 n=994，丢弃分页重复行 0 行）
- 分类器：`RULES_ARM_A_recruitment_taxonomy_rules_2026-11-04b`
- 证据库：`D:\DEPPSKK\medradar\data\dev_device.sqlite`，实测窗口 2024-10-01 … 2026-10-28，共 17730 条
- 关联规则：PROTOCOL §6 四条（R1 同企业 / R2 同 track / R3 时间窗 / R4 可回查标识）；回看窗口 = 24 个月

## 逐 track 计数

> 读法：`INDEPENDENTLY_SUPPORTED` 只表示「独立来源确认该企业在该 track 有公开活动」，这是必要但很弱的核验，对既有大企业几乎自动成立；真正有区分度的是 `方向新颖度`。

| track | 名称 | 岗位数 | 独立岗位 ID | R&D 岗位 | 仅描述命中率 | 候选？ | 招聘信号判定 | 方向新颖度 | 独立证据判定 | 高特异性支持证据 | 建议人工审查 |
|---|---|---:|---:|---:|---:|:--:|---|---|---|---:|:--:|
| `medical_ai` | 医疗AI/软件(SaMD) | 25 | 25 | 15 | 68% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | ESTABLISHED_DIRECTION | INDEPENDENTLY_SUPPORTED | 7 | 否 |
| `neurostimulation` | 神经调控 | 14 | 14 | 6 | 93% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | ESTABLISHED_DIRECTION | INDEPENDENTLY_SUPPORTED | 0 | 否 |
| `ep_pfa` | 电生理与脉冲场消融 | 8 | 8 | 7 | 50% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | ESTABLISHED_DIRECTION | INDEPENDENTLY_SUPPORTED | 2 | 否 |
| `neurovascular` | 神经介入 | 4 | 4 | 1 | 100% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | ESTABLISHED_DIRECTION | INDEPENDENTLY_SUPPORTED | 2 | 否 |
| `cardiac_rhythm` | 心脏节律（起搏/ICD） | 2 | 2 | 2 | 100% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | ESTABLISHED_DIRECTION | INDEPENDENTLY_SUPPORTED | 1 | 否 |
| `respiratory` | 呼吸与麻醉 | 2 | 2 | 2 | 100% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | RECENT_ACTIVITY | INDEPENDENTLY_SUPPORTED | 4 | 否 |
| `structural_heart` | 结构性心脏病 | 2 | 2 | 2 | 100% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | ESTABLISHED_DIRECTION | INDEPENDENTLY_SUPPORTED | 1 | 否 |
| `wearable_remote` | 可穿戴与远程监测 | 2 | 2 | 2 | 100% | 是 | CANDIDATE_TECHNICAL_HIRING_SIGNAL | NO_BASELINE_DATA | NO_INDEPENDENT_SUPPORT | 0 | 否 |
| `imaging_us` | 超声 | 1 | 1 | 1 | 0% | 否 | UNKNOWN | NO_BASELINE_DATA | UNKNOWN | 0 | 否 |
| `resuscitation` | 急救与复苏 | 1 | 1 | 0 | 100% | 否 | UNKNOWN | NO_BASELINE_DATA | UNKNOWN | 0 | 否 |

> 仅描述命中率 = 标题里没有 track 关键词、只靠正文关键词归入该 track 的岗位占比；比例高说明关键词通胀风险高，人工复核要优先核对原文。

## 判定计数

- 招聘信号分级：`CANDIDATE_TECHNICAL_HIRING_SIGNAL` = 8，`UNKNOWN` = 2
- 独立证据判定 `CANDIDATE_TECHNICAL_HIRING_SIGNAL`：0
- 独立证据判定 `INDEPENDENTLY_SUPPORTED`：7
- 独立证据判定 `NO_INDEPENDENT_SUPPORT`：1
- 独立证据判定 `CONTRADICTED`：0
- 独立证据判定 `UNKNOWN`：2

## 岗位职能分类与 track 赋值（分类器 = 规则臂 A）

| 职能类 | 岗位数 |
|---|---:|
| `ALGORITHM_SOFTWARE` | 70 |
| `CLINICAL_R&D` | 13 |
| `CORE_R&D` | 14 |
| `HARDWARE_SYSTEMS` | 11 |
| `MANUFACTURING_PROCESS` | 47 |
| `PRODUCT_ENGINEERING` | 34 |
| `QUALITY_REGULATORY` | 88 |
| `SALES_ADMIN_OTHER` | 585 |
| `UNCLASSIFIED` | 132 |

| track 状态 | 岗位数 |
|---|---:|
| `AMBIENT_ONLY` | 147 |
| `MAPPED` | 61 |
| `NO_EVIDENCE` | 69 |
| `SUPPRESSED_BY_FUNCTION_CLASS` | 717 |

## 数据质量与边界

- 本轮最重要的方法是「先证明核验很弱，再区分新颖度」：同企业 + 同 track 的独立证据核验对既有大企业几乎自动成立（Medtronic 在本证据库 23/38 个 track 中有事件），因此 INDEPENDENTLY_SUPPORTED 不是「新兴方向被证实」，只是必要但很弱的背景核验；真正有区分度的是 direction_novelty。本轮方向新颖度分布：{'ESTABLISHED_DIRECTION': 6, 'RECENT_ACTIVITY': 1, 'NO_BASELINE_DATA': 3}。诚实结论是：核验容易且信息量低，判别性问题是新颖度；在这个证据库上，多数 track 只能判为既有方向或基线不足。
- INDEPENDENTLY_SUPPORTED 的定义被有意收窄：它 = 「独立来源确认该企业在该 track 有公开活动」，这是 NECESSARY-BUT-WEAK 核验，对长期在该 track 经营的企业几乎自动成立，不得读作「新兴方向被证实」。有科学含义的字段是 direction_novelty（NEW_DIRECTION_CANDIDATE / RECENT_ACTIVITY / ESTABLISHED_DIRECTION / NO_BASELINE_DATA），其基线窗口与覆盖月份在每格 direction_novelty 中逐项给出。
- 单快照：本轮只有一次 T0 观察（first_seen_at 2026-11-04T13:11:30+00:00 … 2026-11-04T13:28:37+00:00），去重后岗位数 994、进入 track 单元的岗位 61、track 单元 10 个。单次快照无法定义「变化」，也无法做趋势、领先/滞后或基线比较。
- 岗位数按 posting_id 去重后计：同一 posting_id 的重复行是 Workday 偏移分页造成的重复返回，不是两个岗位；文件行数一般会略多于独立岗位数（本轮见 snapshot.n_duplicate_rows_dropped）。
- 覆盖率未知：采集只覆盖该企业公开 Careers 站点上我们合法可见的部分；分母（企业实际在招岗位总数）未知，「看不见」不等于「没有」。
- 岗位 ≠ 投入：岗位数量不能换算成研发投入、团队规模或项目立项；本文件不把岗位数当投入指标。
- 时间窗：独立证据的回看窗口固定为 24 个月，写死在代码中；窗口外的证据（例如 2024-11-04 之前的记录）按规则拒绝，并计入 failed_rule_counts。
- 证据库实测窗口只有 2024-10-01 … 2026-10-28（17730 条），不是任务书最初描述的 2016-11 起全历史；因此 24 个月回看窗几乎覆盖了整个证据库，更早的历史无法被检验。方向新颖度的可用基线只有约 13.1 个月（2024-10-01 到「近期窗」之前），NEW_DIRECTION_CANDIDATE 只能读作「相对可见基线为新」，绝不能读作「企业对该公司全新」。
- 证据库 payload 截断：8596 条记录的 payload 无法完整解析（{'510k': 3541, 'device_recall': 5049, 'pma': 6}），标识与 PMA 补充类型改用 url / payload 前缀正则提取；这一步本身已计入可回查率与特异性判定。
- 证据来源结构限制：dev_device.sqlite 只含 FDA 510(k)/PMA/召回三类事件（无临床试验、无论文、无企业公告）；本轮临床试验仅用离线缓存中的 ClinicalTrials.gov 记录，论文（Europe PMC）明确记为 NOT_QUERIED。
- 两家重点企业在证据库中为 0 条事件（Draeger、Mindray），若其岗位出现在后续快照中，只能记为来源限制导致的 NO_INDEPENDENT_SUPPORT，不得解释为「没有创新」。
- CONTRADICTED 在本轮不可达：FDA 事件流中没有「退出/撤回该技术方向」的信号；召回只作为售后背景记录，不当作反证。因此本轮没有任何单元被判为 CONTRADICTED，这是数据能力边界，不是「没有反证」。
- PMA 补充的绝大多数是行政类（生产/地点/标签变更），不是技术方向证据；本文件把每条关联证据的特异性（HIGH/MEDIUM/LOW）逐条记录，低特异性证据不能让一个候选变成「被证实的新方向」。
- 分类器是保守的规则臂（A arm）：track 只在函数类别允许且关键词证据足够时才赋值，商业/临床现场岗位的 track 会被函数门槛压制（SUPPRESSED_BY_FUNCTION_CLASS）。因此本文件中的 track 覆盖是下限，未进入 track 的岗位保留在 unclassified_postings 中供审计。反过来，一次见到的关键词通胀是真实存在的：进入 track 单元的 61 个岗位中，47 个（77.0%）的 track 证据只来自岗位描述、标题里没有该 track 关键词（medical_ai 的正文里 artificial intelligence / software 尤其容易出现在普通工程或合规段落）。每格的 track_evidence_quality 给出该比例；人工复核第一步必须是核对 postings[].track_quotes 的原文上下文。
- 关联继承证据库既有的 track 赋值（上游 product-code→track 映射），本管线不重新分类上游事件；上游一个错误 track 赋值会原样传播到 same-track 关联，这一点必须在人工复核时抽查。
- 规则匹配只做确定性字符串/结构化字段匹配，不做语义相似、不做模糊企业名匹配；「同一企业同一 track 两条公开事件」不构成「同一个研发项目」的证据（PROTOCOL §6 末条）。
