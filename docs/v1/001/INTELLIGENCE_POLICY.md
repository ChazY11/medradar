# V1-001 / INTELLIGENCE POLICY

- 日期：2026-11-18　｜　策略版本：`radar-intelligence-2026.11.20` / `radar-assessment-2026.11.20`
- 代码：`medradar/radar/assessment.py`（分级）、`medradar/radar/intelligence.py`（视图与周报）
- 数据：不新增任何存储；三个概念是同一批观测上的**派生视图**。

## 0. 为什么需要这一层

本轮开始前的真实账本（8,593 条观测）：

| 现象 | 数值 | 后果 |
| --- | --- | --- |
| 判为 FEED（可进情报流） | 7,360 条 | “有很多记录”被当成“有值得看的新信息” |
| FEED 中早于 24 个月 | 7,039 条（95.6%） | 默认视图被历史档案淹没 |
| importance | MEDIUM 7,357 / HIGH 3 / LOW 0 | 该维度没有区分度 |
| discovery_phase = INITIAL_DISCOVERY | 8,588 条 | “变化”视图显示的是建库噪声 |

所以问题不是分类器不够聪明，而是**没有把“档案”“候选”“可交付情报”分开**，
也没有一个能解释自己为什么重要的等级。

## 1. 三个概念（同一份证据，三种用途）

### ARCHIVE — 历史证据档案

每一条观测都属于档案。它要求：真实、可追溯、保留原始时间与来源。
它**不要求**有当下情报价值。档案可搜索、可查看，但不进周报。

### CANDIDATE — 待审阅情报

在指定窗口内被发现或发生实质变化、可能与监护有关，但**尚未满足正式输出标准**。原因只有三类：
1. 需要人工确认（分类是我们的判断，不是 FDA 的）；
2. 公开日期不明（无法声称新鲜）；
3. 重要历史事件（值得提醒，但必须标注为“历史补充”）。

### INTELLIGENCE — 可交付情报

候选且同时满足全部交付门槛（见第 5 节）。只有这一类进入周报第 1 节。

### 实现方式

三个视图由 `intelligence.view_for()` 在查询时计算，输入是 `observation` + `admission_current` + 最新 `payload`。
不写回数据库，因此规则改变不会污染历史；同一份证据可以被重新解释而不被改写。

## 2. 新颖度（Novelty）：四种必须分开的事

| 状态 | 判定 | 周报中的位置 |
| --- | --- | --- |
| `NEW_EVENT` | 来源声明的公开日期落在窗口内 | 第 1 节（正文） |
| `UPDATED_EVENT` | 已知记录的内容在窗口内发生变化（version_count>1 且 change_state=UPDATED） | 第 1 节（标注“本周更新”） |
| `FIRST_DISCOVERED_HISTORICAL` | MedRadar 在窗口内首次采集，但来源把事件定在窗口之前 | 第 3 节“历史安全事件补充” |
| `UNDATED_FIRST_DISCOVERY` | 窗口内首次采集，来源没有可用日期 | 第 4 节，且不能称为“新” |
| `ARCHIVE_ONLY` | 窗口内没有任何变化 | 不进周报 |

两条必须写清的实现细节：

1. **日期的精度属于提供日期的那一列。** openFDA 510(k) 只有 decision_date、没有 publication date，
   早期实现先读 `published_at_precision`（值为 unknown），把 6,967 条有明确决定日期的记录误判为“日期不明”。
   现已修正：有 `published_at` 用它和它的精度，否则用 `event_at` 和它的精度。
2. **首次采集不等于本周发生。** 建库当天 8,593 条全部 `first_observed_at` 在窗口内，
   若不加区分，档案会被包装成新闻。

## 3. 重要性的四个等级

`assessment.grade_importance()` 是唯一的分级实现，输出 level + reasons，理由随记录一起存储。

| 等级 | 含义 | 触发规则（按顺序，先匹配先返回） |
| --- | --- | --- |
| **CRITICAL / 立即关注** | 已核实、可能直接影响监护安全或临床风险 | 仍在生效的监护设备安全行动（召回），且官方原因文本包含后果语言（失去监护、报警失效、数值错误、冻结、伤害/死亡）；**或** FDA class 1 的监护设备行动 |
| **HIGH / 本周重点** | 明确的监护研发意义 | 仍在生效的监护设备安全行动但原因未述后果；**或** 30 天内公开、评估测量本身的性能证据（accuracy/agreement/validation 等，且不是单例/病例报告） |
| **MEDIUM / 值得跟踪** | 相关，但短期行动价值或证据强度有限 | 12 个月内的监护设备监管决定（清关/PMA）；**或** 12 个月内的 DIRECT 监护记录；**或** 12 个月内、仍需复核的记录；**或** 单例/病例报告类性能证据 |
| **LOW / 归档参考** | 保留作证据，不进默认重点 | 其余全部：早于 12 个月、日期不明、非 DIRECT、非监护范围 |

三条硬规则：

1. **不按比例分配。** 不存在“每周必须 3 条 HIGH”的机制；安静的一周全是 LOW 是允许的结果。
2. **决策分支只能否决、不能抬升。** 若某个判断分支已确定“这不是情报”（动物实验、社论、单例个案），
   它可以给 LOW；但它不能把 stale 的记录抬成 MEDIUM——上一轮 8,593 条里 8,590 条 MEDIUM 正是这么来的。
3. **弱设计封顶。** 标题声明 single-patient / case study / case series 的性能证据最高只能到 MEDIUM：
   “一个病人的可行性研究”不足以改变验证方案。

## 4. 维度（复用 REFOUNDATION-004，不新建）

| 维度 | 取值 | 谁决定 |
| --- | --- | --- |
| `source_authenticity` | PRIMARY_REGULATORY / OFFICIAL_VENDOR / SCHOLARLY / SECONDARY | 记录类型 |
| `medical_domain` | MEDICAL / NON_MEDICAL / UNCERTAIN | 主题文本 |
| `monitoring_relevance` | DIRECT / TRANSFER / CLINICAL / MEDICAL_UNRELATED / NON_MEDICAL | 主题文本 + 官方产品码 |
| `entity_link` | NONE / AFFILIATION / VENDOR / APPLICANT | 记录中的企业角色 |
| `freshness` | FRESH(≤30d) / RECENT(≤365d) / STALE / UNKNOWN | 来源声明日期 + 精度 |
| `importance` | CRITICAL / HIGH / MEDIUM / LOW | 见第 3 节 |
| `importance_reasons` | 字符串数组 | 分级函数的实际触发理由 |
| `confidence` | 0..1 | 规则置信度（无摘要时下调） |
| `decision` | FEED / REVIEW / EXCLUDED | 判断策略 |

## 5. 交付门槛（进入周报第 1 节的充要条件）

一条情报必须**同时**满足：

1. `monitoring_relevance = DIRECT` 且 `medical_domain = MEDICAL`；
2. `decision != EXCLUDED`，且不是 `REVIEW`；
3. 新颖度为 `NEW_EVENT` 或 `UPDATED_EVENT`；
4. 有官方 URL 与官方标识；
5. `importance ∈ {CRITICAL, HIGH, MEDIUM}`，且 CRITICAL 必须带理由；
6. 按**事件身份**去重（见第 6 节）；
7. 每条都记录 `review_status`。

任何一条不满足 → 进入 CANDIDATE（并写明是哪一条不满足）或 ARCHIVE（若连窗口内的变化都没有）。

## 6. 事件身份与去重

| 记录类型 | 事件身份 | 理由 |
| --- | --- | --- |
| FDA 召回 | `FDA_RECALL_EVENT:<res_event_number>` | 一次召回事件可包含多条产品记录（2026 年实测：42 行 = 19 事件） |
| 文献 | `WORK:<work_key>`（归一化 DOI / PMID / 标题） | 同一作品经 Crossref 与 PubMed 到达时只应出现一次 |
| 其他 | `OFFICIAL:<identifier>` 或观测 ID | 宁可不合并，也不错误合并 |

召回事件号作为官方标识存进既有的 `observation_identifier` 表（kind = `FDA_RECALL_EVENT`），
**不新建表**：事件计数就是一次 `GROUP BY`。

## 7. 复核状态（不许含糊）

| 值 | 含义 |
| --- | --- |
| `NOT_REVIEWED` | 默认值。没有任何人核对过 |
| `AGENT_VERIFIED_AGAINST_SOURCE` | 由 Agent 打开官方记录逐条核对；**不是人工复核** |
| `HUMAN_CONFIRMED` | 真实人工复核确认 |
| `HUMAN_CORRECTED` | 真实人工复核并修正 |

周报每条都显示复核状态；`HUMAN_CONFIRMED` 之外的条目在不确定性里自动加一句“没有人工复核”。

## 8. 每个字段的依据（禁止把推测写成事实）

| 字段 | 依据 |
| --- | --- |
| 标题 / 发生了什么 | 来源原文（截断），`source (verbatim, trimmed)` |
| 事件日期 / 公开日期 / 系统发现 | 来源字段 + 精度；系统发现是账本时钟 |
| 为什么与监护有关 | 规则（产品码映射 / 主题信号 / 判断理由） |
| 重要性及理由 | 规则（`grade_importance`），理由原文 |
| 研发关注点 | 规则模板（按记录类型与来源 root cause），标注 `rule` |
| 不确定性 | 规则（事件/记录关系、状态、精度、复核状态） |

周报每条的 `field_basis` 字段直接打印上述依据。**没有任何字段由模型生成。**

## 9. 这套策略明确拒绝做的事

- 不为了分布好看强行分配等级；
- 不把“企业是监护厂商”当作设备判定；
- 不把历史首次采集写成“本周新发生”；
- 不删除被排除的记录（保留理由并计数）；
- 不用模型生成解释；
- 不在没有人工复核时声称“已复核”。

## 10. 如何修改与回滚

1. 改 `assessment.py` 的规则 → 提升 `ASSESSMENT_VERSION` / `RULES_VERSION`；
2. 运行 `python -m medradar radar reproject` → 追加新决策（旧决策保留，不改写）；
3. 改视图/周报策略 → 提升 `intelligence.POLICY_VERSION`（不需要迁移：视图是派生的）；
4. 回滚：代码回到上一版本即可；已有的 admission 行是历史，不会被删除。
