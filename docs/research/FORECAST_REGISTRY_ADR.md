# FORECAST_REGISTRY_ADR — 不可变预测注册表 + 确定性评估基座 架构决策记录

- **TASK_ID**: FORECAST-REGISTRY-006（实现：Kimi Code primary implementer，分支 `research/forecast-registry`，基线 f1b8132）
- **日期**: 2026-11-01｜**状态**: 已实施（本分支）
- **代码**: `medradar/forecast_registry.py`（单文件扁平模块，stdlib + SQLite，零新依赖）
- **验收**: `tests/test_forecast_registry.py`（39 个离线测试，全部合成数据）；全量 selftest 510 通过（基线 471 + 新增 39，skip 3 与基线一致）
- **边界**: 不含任何模型、不生成任何预测、不声称任何精度；demo 全部为内存合成记录，不冒充历史预测。

---

## 1. 背景与动机

后续 3/6/12/24 个月预测研究需要一条**事先登记、事后无法篡改**的预测
流水线：预测必须在目标窗口到来之前注册，结果解析必须与预测分离，评估
必须是"截至某时刻系统所知"的纯确定性函数。如果没有不可变注册表，
"预测-结果"对总可以在事后挑选或修饰，任何校准/评分结论都不可辩护。
本 ADR 记录该最小可行基座（foundation）的设计决策；**LLM 不做预测、
不声称模型精度**是硬性边界。

## 2. 决策（已采纳）

### D1 — 注册即不可变；generated_at 一律由存储层赋值

- 预测内容（目标、horizon、窗口、模型/特征版本、快照标识、证据、
  `p`）以规范序列化 JSON 的内容 SHA256 作为 `prediction_id`，注册后
  任何字段不可更改（`p` 绝不为改善分数而更新）。
- `generated_at` 由存储层在写事务内从**单调 UTC 时钟**赋值，调用方无
  传入通道；时钟回退拒绝（`ClockRegressionError`）。测试时钟只允许注
  入 `:memory:` 存储；持久化路径注入一律拒绝。
- 时间严格化：naive 拒绝；偏移/小数秒归一化为固定位微秒 UTC
  （`...Z`）；日期级输入显式扩为 `T00:00:00.000000Z` 并记录精度。
- **后果**：不针对 DB 拥有者做防篡改声明——SQL 触发器只防"误写/脚本
  意外"，不防恶意（与 TKG 相同立场）；单写者（single writer）按文档
  约定，不做强制。

### D2 — 目标窗口必须真实未来；月末钳制规则显式文档化

- `window_start` 默认等于 `generated_at`（**绝不**从事件日期隐式回退），
  显式值必须 `>= generated_at`；`window_end > window_start`，半开区间
  `[start, end)`。拒绝任何"事后补录"（pre-event after-the-fact）。
- 默认 `window_end = generated_at + horizon` 个日历月，**日钳制**到目标
  月最后一天：`2024-01-31 + 3m → 2024-04-30`；`2024-02-29 + 12m →
  2025-02-28`（闰年钳制，测试锁定）。horizon 仅支持 3/6/12/24。
- `information_cutoff <= generated_at`（SQL CHECK + 应用层双重校验）。
- `record_kind ∈ {forecast, retrospective_fixture}`：先前回溯 fixture 必须
  显式标记，与真实预测区分；demo 仅内存合成记录。

### D3 — 显式幂等键；冲突失败

- `idempotency_key` 必填。**完全重试**（同键同内容，或同内容异键）返回
  原始记录且**不消耗写时钟**（时钟已走动也不产生新历史）；**同键异内容**
  显式 `IdempotencyConflict`。注册校验全部发生在时钟读取之前，失败
  不消耗时钟、不留部分写入（原子性测试锁定）。

### D4 — 解析为独立 append-only 账本；更正不改历史

- `resolutions` 表以 `prediction_id`（FK）+ `resolution_version` 为主键，
  仅允许 0/1 结果（SQL CHECK），必须携带证据；`resolved_at` 由存储层
  赋值、不可倒签（证据元数据可以早于解析时间）。
- 正例可在事件到达时解析，`event_time` 必填且必须落在目标窗口内——
  **窗口外正例与预测前事件一律拒绝**；负例只能在窗口完全成熟后
  （存储时钟 ≥ `window_end`）解析，且不得携带 `event_time`。
- 更正 = 新 `resolution_version` 行 + 必填 `reason`；原版本保留。
  未知/删失目标以 `kind='censor'` 显式登记，**保持 unscored**。
- **as-of 语义**：评估在 `as_of` 只取 `generated_at <= as_of` 的预测与
  `resolved_at <= as_of` 的最新解析——后来的解析/更正/预测**无法污染**
  历史评估（测试锁定：更正前 as-of 只见 v1，更正后只见 v2，两者皆留档）。

### D5 — 评估为纯确定性函数；不计分的分母如实呈现

- 合格队列 = 最新解析为 0/1 且（负例）窗口截至 `as_of` 已成熟。未解析、
  删失、未成熟负例进入分母计数（`unresolved/censored`），**绝不静默按
  零计分**（防"提前按零打分"的评估层防线有测试锁定，即便有人绕过写
  守卫直接插行也成立）。
- 指标：Brier；log loss（**epsilon 截断** `p∈[1e-15, 1-1e-15]`，文档化）；
  校准分箱边界精确为 `i/10`（最后一箱闭区间）+ ECE。所有值有限；空
  队列返回显式 `null`。已知数值 fixture 独立手算对照（p=[0.9,0.2,0.4,
  0.7] → Brier=0.075，ECE=0.25），不盲从实现公式。
- 分层维度 `(horizon_months, model_version)`；headline 汇总所有合格预测
  但携带 `mixed_targets` 范围元数据，绝不静默混合目标。MVP 不做 AUC /
  AP（类别支持过少时无意义）；n=toy 不得读作校准证据。

### D6 — 确定性导出工件；快照来源诚实标注

- `evaluation.json`：as-of 可见的预测/解析版本、评估结果、
  `scoring_version`、schema/code 版本、provenance 元数据；规范 UTF-8 JSON
  （排序键、缩进、无 NaN）SHA256。**不含墙钟报告时间戳**：as-of 之后的
  任何写入无法改变历史工件哈希（测试锁定）；不含整库活指纹。
- 快照 manifest 标识（`snapshot_sha256`）入册并带验证标志：裸哈希为
  **declared provenance**（哈希长度不构成密码学验证，永不声称）；若注册
  时提供本地 `snapshot.json` 路径，则用既有 `medradar.tkg` API 重算哈希，
  不匹配即硬失败（`verified_local`）。不可验证者如实标注。

### D7 — 物理不可变护栏（含 INSERT OR REPLACE 陷阱）

- `forecasts`/`resolutions` 的 `UPDATE`/`DELETE` 由 BEFORE 触发器物理
  拒绝。**关键发现**：SQLite 的 `INSERT OR REPLACE` 在 btree 层解决冲突
  而不触发 DELETE 触发器，因此另加 `BEFORE INSERT ... WHEN EXISTS`
  存在性触发器兜底（本仓库 TKG 的 DELETE 触发器并不能挡住 OR REPLACE；
  本模块独立修复，不回改 TKG——另一代理负责该树）。

## 3. 明确不做（MVP 边界）

- 不做任何模型/预测生成/LLM 评分；不做 AUC、AP/PR-AUC；不做多分类或
  连续目标；不做多写者协调；不对 DB 拥有者承诺防篡改。
- 不编辑 README/版本号/计数/attribution（由集成代理在各分支接受后统一
  处理）；不改 `medradar/tkg` 及其文档/测试。

## 4. 验收报告（FORECAST-REGISTRY-006 附录）

| 验收项 | 证据（tests/test_forecast_registry.py） |
| --- | --- |
| 非法 p / 时间 / horizon / 证据 | `RegisterValidationTests`（7 组） |
| 日历边界、闰年、月末钳制 | `WindowTests` + `add_months_clamped` 单测 |
| 未来信息泄漏（as-of 过滤/更正） | `test_forecasts_after_as_of_*`、`test_correction_as_of_semantics` |
| 幂等重放 / 冲突 / 时钟移动 | `IdempotencyTests`、`ClockTests` |
| 不可变 SQL 护栏含 OR REPLACE | `ImmutabilityGuardTests`（UPDATE/DELETE/OR REPLACE） |
| 早熟负例 / 窗口外正例 | `ResolutionTests`、`test_immature_negative_*` |
| 更正 as-of、未知/删失分母 | `test_correction_as_of_semantics`、`test_unresolved_and_censored_denominators` |
| 历史哈希在后续写入后稳定 | `ArtifactTests` |
| 独立已知数值评分 fixture | `test_known_value_scoring_independently_computed` |
| CLI 离线 demo + 持久化 CLI 流程 | `CliTests`（demo 合成标记、register/resolve/evaluate/export 端到端） |
| 非仓库 cwd 的 wheel 导入 | 见下方验证记录 |

**验证记录（2026-11-01，本机）**
- `python -m pytest tests/test_forecast_registry.py -q` → 39 passed。
- `python -m medradar selftest` → Ran 510 tests, OK (skipped=3)（基线
  471 + 39 新增；3 个 skip 与基线一致）。
- wheel 安装后在非仓库目录运行 `python -m medradar.forecast_registry
  demo` 成功（合成输出，见 git 提交信息中的路径记录）。
- `python -m medradar.forecast_registry demo --out-dir <tmp>` 生成
  `evaluation.json`，其 `artifact_sha256` 与重复构建一致（确定性）。

## 5. 风险与后续

- `INSERT OR REPLACE` 绕过 DELETE 触发器是 SQLite 层行为，TKG 树存在同类
  缺口；本分支不越权修复，已在 D7 记录并建议 TKG 所有者跟进。
- 负例成熟度依赖存储时钟；评估层另有未成熟负例防线（D5），双保险。
- 后续接入真实预测流时，必须保留 `record_kind=forecast`、真实时钟与
  非空 provenance，禁止以 `retrospective_fixture` 充数。
