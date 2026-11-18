# V1-001 / COMPLEXITY DELTA — 新增、复用、删除、简化与技术债

## 0. 一句话

本轮**没有**第二套系统：新增 3 个模块（1 个适配器、1 个筛选规则、1 个派生视图），
其余全部复用现有的 Adapter / Ledger / assessment / taxonomy / API；
**没有新表、没有数据库迁移、没有新服务、没有新前端、没有新分类引擎。**

## 1. 代码改动（按文件）

| 文件 | 变更 | 性质 |
| --- | --- | --- |
| `medradar/radar/adapters/openfda_recall.py` | +329 | **新增**：召回读取（实现既有 `SourceAdapter` 契约） |
| `medradar/radar/recall.py` | +258 | **新增**：监护设备四级筛选规则（无状态、可单测） |
| `medradar/radar/intelligence.py` | +913 | **新增**：ARCHIVE / CANDIDATE / INTELLIGENCE 派生视图 + 周报渲染 + 指标 |
| `medradar/radar/assessment.py` | +266 | 修改：`grade_importance`（四档 + 理由）、召回分支、弱设计/综述封顶 |
| `medradar/radar/adapter.py` | +25 | 修改：试运行不再留下运行记录；失败记录不写入试运行 |
| `medradar/radar/engine.py` | +30 | 修改：`ingest` 透传 `origin` / `backfill_reason`（复用既有回填机制）；召回重映射分支 |
| `medradar/radar/records.py` | +13 | 修改：`standard_identifiers` 接受适配器声明的事件标识 |
| `medradar/radar/cli.py` | +98 | 修改：`radar brief` 子命令；`radar run --backfill-reason` |
| `medradar/radar/api.py` | +34 | 修改：只读端点 `/api/radar/brief` |
| `medradar/radar/adapters/__init__.py` | +6 | 修改：注册一个工厂 + 默认顺序 |
| `config/radar/sources.json` | +30 | 修改：声明 `openfda_recall`（含访问与许可依据） |
| `tests/test_radar_recall.py` | +297 | **新增** 16 个测试 |
| `tests/test_radar_intelligence.py` | +451 | **新增** 25 个测试 |
| `tests/test_radar_api.py` | +19 | 新增 2 个测试 |
| `docs/v1/001/*` | ~1,100 | 文档 + 2 个证据脚本 + 5 个证据 JSON + 1 个反馈表模板 |

合计：**+2,739 / −30 行**（14 个源文件），加测试 748 行、文档约 1,100 行。

## 2. 复用了什么（逐项，附证据）

| 复用对象 | 复用方式 |
| --- | --- |
| `SourceAdapter` 契约与 `run_source` 引擎 | 召回适配器只实现 `plan` / `fetch_page` / `map_record`；游标、重试、失败不推进水位线、断点续跑全部继承 |
| `data_pipeline.openfda.build_url` 与 `model.SOURCES` | 端点与官方 URL 构造没有第二份实现 |
| 观测账本的五张表 | `observation` / `observation_version` / `observation_change` / `observation_identifier` / `observation_status_history` 原样使用 |
| 判定表 | `observation_admission` + `admission_current` 原样使用，**追加**新版本决策（4 个版本并存） |
| REFOUNDATION-004 的维度化判定 | 只新增 `grade_importance`，未新建分类器；`monitoring_relevance` / `domain` / `freshness` 全部沿用 |
| 既有回填机制 | `origin=BACKFILLED` + `backfill_reason` + `discovery_phase`（原本已实现但没有 CLI 入口，本轮只加了入口） |
| 产品码与企业注册表 | 全部来自 `config/radar/topics.json` 与 `organizations.json`；召回筛选的产品码列表**在运行时从 taxonomy 派生** |
| API 结构 | `/api/radar/*` 既有 router 与只读 `svc.ledger()` 上下文 |
| 事件去重 | 复用 `observation_identifier` 表的 (kind, value) 索引，事件计数 = `GROUP BY` |

## 3. 强制复杂度审查（任务书第九节的 8 个问题）

| # | 问题 | 回答 |
| --- | --- | --- |
| 1 | 是否新增了事实来源？ | **没有新增来源类型**。`/device/recall.json` 早已在产品线（DATA-001/002）与本仓库的 `sources.json` 中声明；本轮只是让雷达车道真正读它。如果严格按「雷达账本新增了一条读取路径」计，答案是有，但同一份官方数据、同一套许可与归属声明。 |
| 2 | 是否重复实现已有能力？ | 没有。见第 2 节。唯一的新逻辑是「这条召回记录是不是监护设备」——这个问题此前不存在。 |
| 3 | 是否增加了跨模块耦合？ | `assessment → recall`（单向）、`intelligence → assessment + recall + ledger`（单向）。没有循环导入。代价：`assessment.py` 现在依赖 `recall.py`，两者需一起演进。 |
| 4 | 是否使未来修改更困难？ | 用版本号控制：`ASSESSMENT_VERSION` / `RULES_VERSION` / `POLICY_VERSION`；规则改变触发 `rules_digest` 差异 → 追加新决策，旧决策保留。视图是派生的，改动不迁移数据。 |
| 5 | 是否可以使用更简单的实现？ | 可以更小、但会更差：把筛选规则写进适配器（无法单测、无法解释、无法复判）；手写周报（无法每周重跑）；不加事件身份（无法做事件计数）。这三处是本轮唯一「必须有点结构」的地方。 |
| 6 | 是否具有明确的用户价值？ | 三块分别对应工作包 A / B / C，见 `SCOPE.md`；`WEEKLY_BRIEF_001.md` 是这三块合起来的产物。 |
| 7 | 是否有回归测试保护？ | 新增 43 个测试；全量套件与治理门见 `FINAL_REPORT.md`。 |
| 8 | 是否可独立回滚？ | 是。三个新模块可整体删除；`config/radar/sources.json` 删掉一条即停用召回（账本数据保留，不删）；`grade_importance` 的改动由版本号隔离，回滚代码后旧决策仍是历史。 |

## 4. 删除 / 简化了什么

| 项 | 变更 |
| --- | --- |
| 适配器里的预存储过滤 | 未新增（REF-004 已删除）；召回行全部入库，由判定层排除并计数 |
| `importance` 的「常量」逻辑 | **删除**（原逻辑：召回即 HIGH，否则 MEDIUM） |
| 「所有 admitted 记录都进 feed」的隐含假设 | **删除**：新增 ARCHIVE / CANDIDATE / INTELLIGENCE 三视图，feed 不再等于情报 |
| 试运行造成的幽灵运行记录 | **删除**（缺陷） |
| `--json` 输出里的 15,000 键索引 | **默认不输出**（改由 `--with-index` 显式请求） |

## 5. 新增的技术债（诚实清单）

| # | 债务 | 为什么可以接受 | 何时必须还 |
| --- | --- | --- | --- |
| 1 | `intelligence.py` 913 行（视图 + 渲染 + 指标在一个文件） | 单一职责、无外部依赖、全部被测试覆盖 | 如果试验继续，按 render / metrics / views 拆三个文件 |
| 2 | `merge_importance` 的「LOW 是否决、其它是忽略」语义略反直觉 | 有 docstring、有测试、有实测动机（8,590/8,593 常量事件） | 下一轮若再加等级，需重新审视 |
| 3 | `recall.DEVICE_TEXT` 的词表需要维护 | 实测抓到 4 个码表外真实设备，也产生 3 个误判；误判只进 REVIEW | 每次周报复核时记录误判词，季度收敛一次 |
| 4 | `engine.advance()` 在 1.5 万条语料上不收敛（**既有缺陷，不是本轮引入**） | 采集与准入已拆开执行，`reproject` 幂等收敛 | **下一轮第一优先**：用实际插入行数判断收敛 |
| 5 | 建库周 `excluded_in_window` 很大（6,421） | 语义正确（全部是本周首次采集），但首次读者会误以为噪声高 | 稳态后自然下降；文档已注明 |
| 6 | 周报中「研发关注点」是规则模板 | 明确标注 `rule` 且不是断言；比编造一段像样的分析更诚实 | 有真实用户后再决定是否值得人工撰写 |

## 6. 回滚步骤（如果需要）

1. 停用召回：从 `config/radar/sources.json` 删除 `openfda_recall` 条目（或设 `enabled: false`）→ 下一次周期不再采集，**已有观测保留**；
2. 回滚判定：把 `assessment.ASSESSMENT_VERSION` 改回上一版本并重新 `reproject` → 追加旧规则决策，新决策作为历史保留；
3. 回滚代码：`git revert` 本轮提交；三个新模块可整文件删除；
4. 回滚数据：从已验证备份恢复账本（本轮未修改任何既有观测）。
