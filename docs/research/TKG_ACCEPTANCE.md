# TKG_ACCEPTANCE — 双时态存储 + PIT 导出：独立验收规范

- **TASK_ID**: VALIDATION-DESIGN-002
- **AGENT**: Kimi Code（独立验收设计；DeepSeek 侧后续实现与对账）
- **日期**: 2026-11-01｜**状态**: 规范定稿，**不含实现**
- **依据**: `docs/research/KIMI_AUDIT.md`（51be2bd，经 Director 复核修正）

---

## 0. 范围与非目标

**目标**：在现有 stdlib/SQLite 架构内，新增一个 **append-only 双时态（TKG）事实存储**与
**确定性 point-in-time（PIT）导出**机制，使任一历史时刻 T 的系统知识可以被精确重建与独立复核。

**非目标（明确排除）**：
- **价格层（H2/H3，KIMI_AUDIT）属独立 backlog**，不列入本 MVP（Director 裁定）；
- 不改动现有 `events`/`prices` 表的写入语义（适配器只读源库）；
- 不引入任何新基础设施依赖（无新服务、无新存储引擎、无第三方库；仅 Python stdlib + SQLite）；
- 本规范不含实现。实现方（DeepSeek）须先按 §4 验收清单逐条自查，再交付对账。

## 1. 术语（规范内唯一语义）

| 术语 | 定义 |
|---|---|
| **valid time** | 断言为真的世界时间区间，半开区间 `[valid_from, valid_to)`；`valid_to = ∞` 用 `NULL` 表示当前有效 |
| **knowledge time / recorded time** | 系统**记录**该版本的时间（transaction time），写入后**不可变** |
| **公开时间（public availability）** | 信息可被公众获得的时间；**可合法早于 knowledge time**（先公开后被抓取）。公开时间重建是与系统知识查询**分别命名**的模式，须有源/版本证据支撑 |
| **as-of 查询（知识视角）** | "T 时系统记录了什么"——只按 knowledge time ≤ T 过滤，再取各实体最新版本 |
| **as-of 查询（公开视角）** | "T 时公众可获得什么"——按公开时间过滤，且每条断言附证据定位符；**不得**与知识视角混用或互相冒充 |
| **revision / retraction** | 同一实体的后续版本/撤销：新增一条记录（knowledge time 更晚），**禁止改写或删除旧版本** |
| **PIT 导出** | 某一切割线下、某一时钟模式下的确定性只读快照 |

> 反例（Director 复核明确禁止）：`available_at < first_seen_at` 本身**不是**异常，
> 不得作为校验告警条件，也不得设计"强制公开时间 ≥ 知识时间"的约束。

## 2. 存储契约（C1–C6）

**C1 双时态核心列（每条版本记录必备）**
- `entity_type TEXT NOT NULL`、`entity_id TEXT NOT NULL`（逻辑主键分量）
- `valid_from TEXT NOT NULL`、`valid_to TEXT NULL`（半开区间；`NULL` = 至今有效）
- `recorded_at TEXT NOT NULL`（knowledge time，写入后不可变）
- `record_id TEXT NOT NULL`（确定性内容哈希，见 C6）
- `payload TEXT NOT NULL`（原始断言 JSON）
- 单调序号：`(entity_type, entity_id, recorded_at, seq)` 唯一；同刻多版本按 `seq` 定序

**C2 证据字段（`source_locator`/`content_hash`/`evidence_type`/`confidence` 必备，缺一则拒绝写入）**
`source_locator`（URL/库表行号/文件名）、`content_hash`（payload 的 sha1）、
`evidence_type`（`source_observed | inferred | reconstructed`）、
`confidence`（0..1 实数）、`source_version`（**未实现**：实现不存储逐断言源版本，缺省视为显式
`"unknown"`；manifest 级 schema/adapter/code 版本是代码与 manifest 身份，不声称等价于源数据版本；
`content_hash`/`evidence_sha256` 是内容哈希，不是源修订号。源修订号关键时由调用方显式写入
`source_locator`/`attrs`，随导出保留）。
`evidence_type != source_observed` 时，公开时间字段必须显式标注为推断（`public_time_basis`）。

**C3 写入规则**
- 纯 append：`UPDATE/DELETE` 对历史版本物理禁止（API 层不暴露；数据库层以触发器或
  `PRAGMA query_only` + 独立写连接双保险）；
- `recorded_at` 一律由存储层以写入事务的 UTC 时刻赋值，**调用方不得传入**；
- 拒绝 future/backdated 写入：`recorded_at` 与系统 UTC 时钟偏差 > 60s 拒绝（隔离例外见 C5）；
- `valid_from` 允许历史日期（历史断言合法），但 `valid_to < valid_from` 拒绝；
- 未知/缺失 knowledge time 的输入记录**整体拒绝**，**不存在 event-date 回退**。

**C4 时区**
所有时间列以严格 timezone-aware UTC ISO-8601 存储（`YYYY-MM-DDTHH:MM:SSZ` 或带 `+00:00`）；
接受输入时非 UTC 一律归一化（naive 输入按**拒绝**处理，而非猜测时区）。
日期级输入显式记 `T00:00:00Z` 并令 `precision='date'`（单独列），不得静默升格为 datetime。

**C5 历史导入 / 观测语义（回填的合法通道）**
- 从现有库导入历史事实时，`recorded_at` **保守地使用实际导入观测时刻**；仅当存在
  **可信的持久化原始观测记录**（如 `first_seen_at` 在源库中自首次写入未被覆写，可审计证明）
  才可沿用其值，且须在 `source_locator` 中注明依据；
- 显式隔离的重放 fixture 机制：仅当连接以 `replay_fixture=1` 打开且库路径匹配测试命名
  约定时，允许写入指定 `recorded_at`（用于 §4 的复活/篡改测试）；生产路径拒绝。

**C6 完整性**
- 外键/引用完整性：版本记录引用的实体元数据表（C7）存在；导入后 `PRAGMA foreign_keys=ON`
  校验通过；孤儿引用拒绝提交；
- 事务回滚：任一批次内任一行违反 C1–C5，整批 `ROLLBACK`，已写部分不得残留；
- 幂等冲突拒绝：同一 `record_id` 重放写入必须**冲突拒绝（不覆盖、不重复）**；
  内容相同但 `recorded_at` 不同的重试视为新合法版本（由 C1 序号区分），不得去重丢弃。

## 3. 查询与导出契约（C7–C10）

**C7 实体元数据时态一致**
公司/赛道/产品码等元数据（别名、映射、ticker）同样是版本化双时态记录：
归属解析必须按"as-of T 的元数据版本"执行，禁止用今天的子公司映射解释历史事件
（KIMI_AUDIT RESEARCH §8.10 已知局限的结构性修复）。

**C8 as-of 语义（防复活）**
对任一 as-of T 查询：
1. 先取 `recorded_at ≤ T` 的全部版本；
2. **先按 knowledge time 取每实体最新版本，再应用 valid-time 过滤**（`valid_from ≤ T < valid_to`）。
   顺序颠倒会把"后来被修正/撤销的旧版本"在 T 视角复活——这是必须测试的明确缺陷类。
   撤销（retraction）表示为 `valid_to` 被新版本关闭或 `retraction=true` 新版本。

**C9 双时钟模式分离**
导出 API 必须显式二选一（默认 knowledge）：
- `clock="knowledge"`：门控 `recorded_at`（系统知识）；
- `clock="public"`：门控公开时间字段 + 仅含 `evidence_type='source_observed'` 的记录，
  输出附逐条证据定位符；调用方文档与 CLI help 必须说明两者差异。

**C10 确定性快照哈希**
PIT 导出必须附带 `snapshot_hash = sha1(canonical)`，其中 canonical 序列化包含：
`cutoff`、`clock` 模式、schema 版本、provenance（工具版本/源库指纹）**以及排序后的数据内容**；
**排除**易变的生成时间戳。同一切割线重复导出必须逐字节一致（跨平台：统一 `\n`、UTF-8、
键序排序）。schema 版本或 provenance 变化必须反映到哈希变化。

## 4. 验收清单（先红后绿；每条 = 可离线运行的失败→通过测试）

| # | 验收测试 | 覆盖 | 当前预期 |
|---|---|---|---|
| A1 | `revision_cannot_alter_history`：写入 v1(k=T0) 后于 T1 写 v2 修正同一实体；as-of T0.5 查询必须仍返回 v1 原值 | C3, C8 | 现有 `INSERT OR REPLACE` 语义下失败 → 红 |
| A2 | `retraction_respected_asof`：T1 撤销 v1；as-of T0 仍见 v1，as-of T1+ 不得见 v1（复活 = 失败） | C8 | 红 |
| A3 | `latest_before_valid_filter`：构造"旧版本 valid 区间更长"陷阱；as-of T 不得复活已被新版取代的旧版本 | C8 | 红 |
| A4 | `knowledge_clock_gates_on_recorded_at`：记录 A(recorded T1, valid_from T0) 与记录 B(recorded T0, valid_from T0)；as-of T0.5 knowledge 查询**只**见 B；public 查询按公开时间另算且附证据 | C9 | 红（无知识时钟模式） |
| A5 | `public_before_knowledge_is_legal`：`public_time < recorded_at` 写入与查询均合法、零告警 | §1 反例 | 红（若校验误报） |
| A6 | `missing_knowledge_time_rejected_no_fallback`：缺 knowledge time 的导入记录被拒；**不存在**任何 event-date/公开时间回退补 knowledge time 的代码路径 | C3 | 红 |
| A7 | `timezone_strictness`：naive 时间、非 UTC 带偏移、夏令时歧义输入分别被拒或显式归一；存储值全为 UTC | C4 | 红 |
| A8 | `future_backdated_writes_rejected`：未来/倒签 `recorded_at` 被拒；`replay_fixture` 通道仅在测试库可用且生产路径拒绝 | C3, C5 | 红 |
| A9 | `historical_import_uses_observation_time`：从现有 events 库导入时，`recorded_at` = 实际导入时刻；若源 `first_seen_at` 可证未被覆写（A10 辅助审计）可沿用并注明依据；源库全程只读 | C5 | 红 |
| A10 | `source_db_readonly_and_first_seen_auditable`：适配器打开源库 `mode=ro`；并对源库提供"`first_seen_at` 自首次写入未变"的可审计证明（如对导入批次记录源指纹），无法证明则一律用导入观测时刻 | C5 | 红 |
| A11 | `fk_rollback_idempotency`：批次含孤儿 FK 行 → 整批回滚零残留；重复 `record_id` 重放 → 冲突拒绝；同内容不同时刻重试 → 新版本保留 | C6 | 红 |
| A12 | `snapshot_hash_determinism`：同参数导出两次字节一致；改 cutoff/clock/schema/provenance 任一项哈希必变；哈希不含生成时间戳（固定时钟注入下两次运行哈希相等） | C10 | 红 |
| A13 | `metadata_temporally_consistent`：实体别名在 T 时刻的版本决定 T 时刻事件的归属；用今天的映射解析历史事件 = 失败 | C7 | 红 |
| A14 | `offline_cli_and_wheel`：`python -m medradar tkg export --asof ... --clock knowledge`（命名可调整）在空网络、无 API key 环境完成端到端（合成 fixture 库）；安装 wheel 后从非仓库 cwd 可运行；不新增第三方依赖 | §0 | 红 |

## 5. 迁移适配与兼容

- 适配器（C5/A9）从现有 `events` 导入时，保守策略优先级：
  `可信持久化 first_seen_at`（须 A10 证明）> `实际导入观测时刻`。**禁止**用 `event_date`、
  `available_at` 或任何推断值充当 knowledge time。
- 现有 `available_at` 在 TKG 库中只能映射为**公开时间字段**且 `evidence_type='inferred'`
  （openFDA 无发布日证据，见 KIMI_AUDIT H1）；其滞后幅度修复须先经 D2 经验测量，测量前不得推断先验。
- 现有回放/分析读路径在 TKG MVP 期间保持原样；TKG 库为并行只读事实源，通过导出文件对接。

## 6. 简版路线图

| 阶段 | 内容 | 验收 |
|---|---|---|
| R1 | 存储层：C1–C6 schema + append-only 写路径 + fixture 通道（C5） | A1, A2, A5–A8, A11 |
| R2 | 查询层：C7 元数据版本化 + C8 防复活 as-of + C9 双时钟 | A3, A4, A13 |
| R3 | 导出层：C10 确定性快照哈希 + CLI + wheel 兼容 | A12, A14 |
| R4 | 适配器：C5/A9/A10 从现有 events 只读导入 + 证明机制 | A9, A10 |
| R5 | 对账：DeepSeek 实现与本规范逐条走查；Kimi 独立复跑 A1–A14 | 全清单 |

**禁止事项**（Director 裁定，写入规范）：不得将 `available_at ≥ first_seen_at` 作为约束或告警；
未测量不得推断公开滞后先验；价格层修复不得混入 TKG MVP；历史回填不得把
`event_date`/`available_at` 冒充 knowledge time；重放 fixture 机制不得在生产路径可达。


---

## 附录（2026-11-01 修订，Director 覆盖后之实施合同）

> 本附录由 TKG-MVP-003 实现方（Kimi Code，`research/tkg-mvp`）按 Director 覆盖
> 裁定修订。**原规范正文保留作历史记录**；凡与本附录冲突处，以本附录为准。
> 实现见 `medradar/tkg/`，决策理由见 `docs/research/TKG_ADR.md`，用法见
> `docs/TKG.md`。

### 覆盖条款 → 实施对照

| # | 原规范条目 | 修订后合同（Director 裁定） | 实施/测试 |
|---|---|---|---|
| O1 | C9 双时钟模式 | **仅严格系统知识查询**。公开时钟重建整体 DEFERRED（现有源证据不足）；`public_time(_basis)` 为可选源元数据，允许早于摄取，**永不充当系统时钟** | `test_public_time_is_metadata_never_clock` |
| O2 | C1 实体级版本 | **断言级版本化**：显式节点 + 类型化有向边；`assertion_id`（内容 SHA256）为稳定版本标识；节点属性同样版本化；边导出仅携带端点引用，不泄漏未来节点元数据 | `test_entity_has_many_relations_versioned_by_assertion`、`test_edge_export_does_not_leak_future_node_metadata` |
| O3 | C3 60s 偏差拒绝 | **废除该启发式**。`recorded_at` 一律由存储层赋值（tz-aware UTC），调用方无传入通道；每存储单调锚点（回退即拒）；同时刻按 `seq` 确定性定序 | `test_recorded_at_assigned_by_store_not_caller`、`test_clock_regression_rejected_and_equal_timestamps_sequenced` |
| O4 | C5 `replay_fixture=1` + 测试库命名约定 | **废除文件名/连接串机制**。注入时钟**仅允许内存存储**（`":memory:"`）；持久化路径注入即拒绝 | `test_test_clock_rejected_on_persistent_path` |
| O5 | C5/A9/A10 first_seen 沿用 + 源指纹证明 | **无条件使用实际导入观测时刻**；`first_seen_at`/`available_at` 仅为溯源元数据；**不主张**指纹证明 first_seen 不可变 | `test_import_uses_observation_time_and_keeps_source_readonly` |
| O6 | C10 sha1、provenance 含源库指纹 | SHA256；manifest 含双切割线、schema/adapter/code 版本、选中证据溯源、内容哈希；**排除墙钟生成时间，不含整库活指纹** | `test_snapshot_stability_after_later_writes`、`test_export_is_byte_deterministic_and_cutoff_sensitive` |
| O7 | —（TKG-HARDEN-005 增补） | **端点可见性合同**：快照/导出只输出两端点在同一组 `(known_at, valid_at)` 选中节点集合中的边；端点被撤销/未生效/缺失时排除该边，不输出悬空引用、不回填未来元数据、不复活节点 | `HardeningTests::test_snapshot_excludes_edge_when_*`、`test_snapshot_keeps_edge_when_endpoints_visible_and_hash_regresses` |
| O8 | C3 纯 append 强化 | 增补**重提交守卫**：`BEFORE INSERT` 拒绝主键已存在的插入，`INSERT OR REPLACE`/upsert 无法覆写 `nodes`/`edges`/`idempotency` 历史；**边界：不防数据库属主** | `HardeningTests::test_insert_or_replace_cannot_rewrite_history`、`test_idempotency_key_cannot_be_rebound_via_replace` |
| O9 | C4 时间格式强化 | 规范渲染固定 6 位微秒 `...SS.ffffffZ`，字典序=时间序；schema 版本 `tkg-schema-2`（不自动迁移旧库） | `HardeningTests::test_timestamps_fixed_width_microseconds_lexical_order`、`test_cutoff_at_equal_instant_excludes_subsecond_later_write`、`test_clock_guard_rejects_same_second_regression` |

### 验收清单 A1–A14 现状映射

| # | 验收测试 | 状态 | 落点（tests/test_tkg.py） |
|---|---|---|---|
| A1 | revision_cannot_alter_history | ✅ | `test_revision_cannot_alter_history` |
| A2 | retraction_respected_asof | ✅ | `test_retraction_never_resurrects_older_revision` |
| A3 | latest_before_valid_filter | ✅ | `test_latest_before_valid_filtering` |
| A4 | knowledge_clock_gates_on_recorded_at | ✅（知识侧；公开侧 DEFERRED，见 O1） | `test_late_arrival_gated_on_recorded_at` |
| A5 | public_before_knowledge_is_legal | ✅（作为源元数据合法、零告警） | `test_public_time_is_metadata_never_clock` |
| A6 | missing_knowledge_time_rejected_no_fallback | ✅（改写为：新观测由存储层盖时戳；导入断言不得由事件日期推导知识时间） | `test_recorded_at_assigned_by_store_not_caller`、`test_import_uses_observation_time_and_keeps_source_readonly` |
| A7 | timezone_strictness | ✅（naive 拒绝、偏移归一 UTC、日期级显式记 precision） | `test_clock_timezone_strictness` |
| A8 | future_backdated_writes_rejected | ✅（改写为：调用方无时戳通道 + 每存储单调锚点；无 60s 启发式，见 O3/O4） | `test_clock_regression_rejected_and_equal_timestamps_sequenced`、`test_test_clock_rejected_on_persistent_path` |
| A9 | historical_import_uses_observation_time | ✅ | `test_import_uses_observation_time_and_keeps_source_readonly` |
| A10 | first_seen_auditable 证明机制 | **已废除**（O5）；只读源库 + 字节级不变测试保留 | `test_import_uses_observation_time_and_keeps_source_readonly`、`test_source_is_opened_read_only` |
| A11 | fk_rollback_idempotency | ✅ | `test_batch_is_atomic_rollback`、`test_orphan_edge_fails_and_rolls_back`、`test_identical_retry_returns_original_unchanged`、`test_conflicting_reuse_of_key_fails`、`test_different_keys_permit_later_revisions` |
| A12 | snapshot_hash_determinism | ✅（sha256；manifest 变更项映射见 O6） | `test_export_is_byte_deterministic_and_cutoff_sensitive`、`test_snapshot_stability_after_later_writes`、`test_manifest_carries_cutoffs_versions_and_provenance` |
| A13 | metadata_temporally_consistent | ✅（节点属性为版本化断言，先选后滤保证 as-of 一致） | `test_revision_cannot_alter_history`、`test_edge_export_does_not_leak_future_node_metadata` |
| A14 | offline_cli_and_wheel | ✅（`python -m medradar.tkg demo/import/export` 离线端到端；wheel 安装 smoke 见任务报告） | `CliTests`、`test_import_export_cli_roundtrip` |

**说明**：A4/A5 的"公开视角"半边整体 DEFERRED（O1）；A6/A8 按 O3/O4 改写而非原
文逐字实现；A10 证明机制废除，改为保守的"导入观测时刻"策略。其余条目逐字落地。
O7–O9 为 TKG-HARDEN-005 对抗性加固增补（2026-11-01），原规范无对应条目。
DeepSeek 侧独立实现的对账仍待进行；本附录不构成对独立验证完成的声明。
