# TKG_ADR — 双时态知识图谱 MVP 架构决策记录

- **TASK_ID**: TKG-MVP-003（实现：Kimi Code，分支 `research/tkg-mvp`）
- **日期**: 2026-11-01｜**状态**: 已实施（本分支）
- **依据**: `docs/research/TKG_ACCEPTANCE.md`（VALIDATION-DESIGN-002，经 Director 覆盖修订，见文末附录 A）、`docs/research/KIMI_AUDIT.md`（AUDIT-KIMI-001）
- **验收**: `tests/test_tkg.py`（42 个离线测试，全部合成数据）
- **加固修订**（2026-11-01，TKG-HARDEN-005 对抗性复审，分支 `research/kimi-tkg-hardening`，
  基线 f1b8132）：端点可见性合同、重提交守卫、微秒级规范时间戳；见 D2/D3/D4 与
  `docs/research/TKG_HARDENING_REPORT.md`。schema 版本升至 `tkg-schema-2`。

---

## 1. 背景与动机

KIMI_AUDIT 的 H1/H2 指出：现有 `events` 表虽有四列时态字段，但 `INSERT OR REPLACE`
写入语义使"任一历史时刻 T 的系统知识"无法重建（回填用今天覆盖全部历史窗口；
`first_seen_at` 无消费方；无任何 as-of 查询模式）。本 ADR 记录以最小可行面
（MVP）修复该结构缺口的决策。

## 2. 决策（已采纳）

### D1 — 仅严格系统知识时钟；公开时钟重建整体推迟

- 查询与导出只暴露**系统知识时钟**（`recorded_at`）。公开可得时间重建
  （public-clock reconstruction）**不进入本 MVP**：现有源的 `available_at`
  写入已塌缩为 `event_date`（KIMI_AUDIT H1），从当前版本证据做公开时钟重建
  **在科学上不可辩护**。
- `public_time` + `public_time_basis` 作为**可选源元数据**随断言保存
  （允许早于摄取时间，`public_time < recorded_at` 合法），**绝不充当系统时钟**、
  不参与任何切割或过滤。
- 后果：接受规范 C9 的 `clock="public"` 模式删除；A4/A5 的知识侧语义保留并测试，
  公开侧语义标记为 DEFERRED。

### D2 — 断言级版本化 + 显式节点/有向关系

- 版本单元是**断言**（assertion），不是实体：每个节点身份与每个有向边身份
  各是一条独立版本谱系，以稳定 `assertion_id`（内容 SHA256）标识。一个实体的
  多条关系即多条边谱系。**节点属性整体作为一个 JSON 对象版本化**——无属性级
  diff、无属性级独立谱系（"属性级断言"不在本 MVP 范围，旧表述已按实现更正）。
- 图模型：显式节点（`node_type`/`node_id`，属性同样版本化）+ 类型化有向边
  （`edge_type`, `src -> dst`），实体/关系词表可扩展，无硬编码业务关系。
- 每条断言必备证据五元组：`source_locator`、`evidence_sha256`（载荷规范序列化
  的 SHA256）、`evidence_kind`（`source_observed|inferred|reconstructed`）、
  有限 `confidence ∈ [0,1]`、`public_time(_basis)`（可选）。
- 边的导出**只携带端点引用**；节点元数据一律来自同一组切割线下选中的节点版本，
  因此历史导出不可能泄漏未来的节点属性。

### D3 — 查询语义：先选后滤（防复活）

- 查询暴露**独立的** `known_at` 与 `valid_at` 两个切割线：
  1. 取 `recorded_at <= known_at` 的全部版本；
  2. 按 `(recorded_at, seq)` 取每个断言谱系的**最新**版本；
  3. 再对选中版本应用有效区间过滤 `[valid_from, valid_to)`（半开，`to > from`，
     `NULL` = 至今有效）。
- 顺序不可颠倒：先过滤后选新会把"后来被修正/撤销的旧版本"在 T 视角复活。
  后来的撤销永远不会让旧版本复活（测试锁定）。
- `snapshot(known_at, valid_at=None)` 中 `valid_at=None` 表示不做有效时间过滤。
- **端点可见性合同（TKG-HARDEN-005 增补）**：节点与边是独立谱系，同一组切割线
  下"边的选中版本仍在、端点的选中版本已不在"是合法状态（端点被撤销/未生效/
  不存在）。快照与导出**只输出两端点都在选中节点集合中的边**；不输出悬空引用、
  不回填未来元数据、不为边复活节点（测试锁定：撤销端点、未生效端点、缺失端点
  三个场景 + 固定哈希向量回归）。

### D4 — 存储层强约束

- **纯 append**：`nodes`/`edges` 上的 `UPDATE`/`DELETE` 由 SQL 触发器物理禁止；
  API 不暴露改写路径。
- **重提交守卫（TKG-HARDEN-005 增补）**：`INSERT OR REPLACE` 以"删旧插新"解决主键
  冲突，不会触发上述 UPDATE/DELETE 触发器，曾可绕过守卫覆写历史（实测确认）。
  现以 `BEFORE INSERT` 守卫拒绝任何主键已存在的插入（`nodes`/`edges`），并守护
  `idempotency` 表防止幂等键被重新绑定。边界声明：防游离 SQL 会话，**不防数据库
  属主**（可删触发器/重建库）。
- **`recorded_at` 一律由存储层在写事务内赋值**（timezone-aware UTC）；调用方
  无任何传入通道，不能倒签/预签。缺失输入知识时间对普通新观测**不构成错误**
  （存储层盖"现在"的章）；**导入断言禁止从事件日期静默推导知识时间**。
- 生产写时钟**每存储单调**（持久化锚点，回退即拒绝 `ClockRegressionError`）；
  同一时刻的多个版本由每谱系 `seq` 确定性定序。
- **测试时钟仅允许注入内存存储**（`":memory:"`）；持久化路径注入测试时钟一律
  拒绝。**无 60 秒启发式**要求（接受规范 C3 该条被 Director 覆盖废除），也
  **无基于文件名的安全机制**。
- 时间输入严格化：naive 时间拒绝（不猜时区）；带偏移输入归一化为 UTC；日期级
  输入显式记零点并存 `valid_precision='date'`。
- **规范渲染固定 6 位微秒**（TKG-HARDEN-005 增补，`tkg-schema-2` 起）：
  `YYYY-MM-DDTHH:MM:SS.ffffffZ`。混合精度（`...T00:00:00Z` vs `...T00:00:00.5Z`）
  下字典序 ≠ 时间序（`Z` > `.`），会导致切割线/单调锚点误判（实测确认），故渲染
  宽度必须固定。
- 浮点严格化：`confidence` 必须有限且在 `[0,1]`；attrs 规范序列化拒绝
  NaN/Infinity。

### D5 — 幂等键显式化

- 调用方必须提供 `idempotency_key`：
  - 同键 + 同内容重试 → 返回原始版本（`status='duplicate'`），**不产生新历史**；
  - 同键 + 不同内容 → `IdempotencyConflict` 显式失败；
  - 不同键 → 合法的新版本（修正/撤销的通道）。
- 适配器使用内容寻址键（`event:<id>#<内容哈希12位>`），使源端修正自然成为
  新版本、完全重复导入自然成为幂等重放。

### D6 — 确定性 PIT 导出

- 导出 = 排序后的规范 JSON（键序、紧凑分隔符、UTF-8、`\n`、无 NaN）或
  JSONL（nodes/edges 分文件）+ manifest。
- manifest 含：**两个切割线**、schema/adapter/code 版本、选中证据溯源
  （逐条 `assertion_id`/`source_locator`/`evidence_sha256`/`evidence_kind`）、
  计数、内容 `snapshot_sha256`。**排除任何墙钟生成时间**；**不使用整库活指纹**，
  因此切割线之后的写入不可能改变历史导出的哈希。
- 导出是**数据集快照，不是预测基准**。

### D7 — 适配器只读 + 保守实体策略

- 源库以 `mode=ro` + `PRAGMA query_only=ON` 打开，**永不修改源表**；集成测试
  使用合成临时 fixture，对生产库零接触（测试断言源文件字节级不变）。
- 导入的 `recorded_at` **无条件等于实际导入观测时刻**（存储层时钟）；
  `first_seen_at`/`available_at` 仅作为溯源元数据随断言保存。本实现**不主张**
  任何"源指纹证明 first_seen_at 从未被覆写"（接受规范 A10 证明机制被 Director
  覆盖废除）。
- 实体 ID 复用源库现有标识符（`event_id`/`company_key`/`track_id`/
  `product_code`）；关系仅为现存列推出的保守包含关系
  （`company_event`/`event_in_track`/`event_has_code`），**不猜测**股权、技术
  或竞争关系。
- 缺 `event_id`/`event_date` 的行跳过并计数；`available_at` 不可解析时丢弃该
  公开元数据（保留断言本身）并计数；全部经 report 显式返回。
- 覆盖边界（文档化）：适配器导入"源库中**存在哪些行、它们声称什么**"，不解释、
  不与外部世界去重、不认证公开可得性。

## 3. 被否决的备选方案

| 备选 | 否决理由 |
|---|---|
| 公开时钟查询模式（C9 `clock="public"`） | 现有源 `available_at` 塌缩为 `event_date`，公开重建无证据基础；推迟至 D2 经验测量之后 |
| `recorded_at` 与系统时钟偏差 >60s 拒绝（C3） | 启发式武断且与单调锚点重复；Director 明确废除 |
| `replay_fixture=1` 连接参数 + 测试库命名约定（C5） | 文件名/连接串安全机制不可靠；改为"注入时钟仅内存存储"的硬边界 |
| 源指纹证明 first_seen_at 不可变（A10） | 现有 `INSERT OR REPLACE` 语义下无法证明；主张即过声明 |
| 每实体单行 + 版本号递增 | 实体多关系无法表达；断言级版本化才能独立演化 |
| 导出 manifest 含整库哈希 | 后续写入会改变历史导出哈希，违背确定性 |

## 4. 影响

- 新增 `medradar/tkg/` 子包（store/query/export/adapter/CLI），零新依赖；
  `pyproject.toml` 打包列表加入 `medradar.tkg`。
- 现有采集/回放/分析路径**不变**；TKG 库为并行事实源，经导出文件对接。
- 测试总数 440 → 482（MVP 31 + 加固 11）；README 计数同步更新。
- 残余风险与限制见 `docs/TKG.md` §限制。

## 5. 附录 A — 与 TKG_ACCEPTANCE 规范的差异对照

本实现遵循该规范经 Director 覆盖后的合同；逐条差异与测试映射见
`docs/research/TKG_ACCEPTANCE.md` 附录（修订块，2026-11-01）。
