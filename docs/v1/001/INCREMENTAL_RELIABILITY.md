# V1-001 / INCREMENTAL RELIABILITY — 水位线、采集、更新、恢复与健康检查

> 原则：**系统看起来在跑**不等于**系统在前進**。本文件只报告实测到的前进、停滞与失败。

## 1. 水位线：已知缺陷的当前真实状态

| 项 | 实测值 | 证据 |
| --- | --- | --- |
| 存储的 Crossref 水位线 | **`2027-02`（在未来）** | `radar status` 表格；`_evidence/radar_verify.json` |
| 一致性检查是否发现 | **是**：`{"kind": "watermark_in_future", "sources": ["crossref"]}` | `radar verify` 返回 `ok: false`，退出码非 0 |
| 状态是否仍显示健康 | 部分：`integrity` 行写明问题，但顶层 `state` 仍为 `ok` | 见第 6 节残留缺口 |
| 适配器实际使用的下界 | 被夹到今天（`usable_incremental_watermark`），不是 2027-02 | `tests/test_radar_watermark.py` 四个用例 |
| 存储值是否被改写 | **没有被改写**（作为证据保留），调整只出现在运行结果的 `watermark_adjustment` | 同上 |

这是 FIRST PRINCIPLES-001 的修复，本轮**没有**重新实现，只验证它确实在真实账本上生效：
破坏性的 `2027-02` 不再导致 Crossref 从 2018 年扫起，同时也不会被静默修复。

**残留缺口（本轮未修）**：`system_status()` 的顶层 `state` 不考虑 consistency 问题，
因此一个人只看第一行仍会读到 `ok`。这是下一轮应当修的一行逻辑，不是本轮的范围。

## 2. 召回通道的增量正确性（真实运行）

### 2.1 三次运行的真实记录

| # | 时间 (UTC) | 触发 | 结果 | 请求/页 | 记录 | 新增/未变 | 耗时 | 水位线 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-11-18T14:51:24 | 历史回填（`--backfill-reason`） | PARTIAL（6 个产品码 404） | 36 / 30 | 6,717 | **6,563 / 154** | 138 s | 无 → 2026-11-05 |
| 2 | 2026-11-18T15:03:52 | 续跑（自动 resume 上一条 PARTIAL） | OK | 31 / 31 | 1,481 | 0 / 1,481 | 59.6 s | 2026-11-05 → 2026-11-05 |
| 3 | 2026-11-18T15:05:01 | 常规增量周期 | OK | 2 / 2 | 266 | 0 / 266 | **4.3 s** | 2026-11-05 → 2026-11-05 |

三次记录说明了四件事：

1. **幂等**：同一批记录重复采集不产生新观测（0 new），`records_unchanged` 精确计数；
2. **续跑**：PARTIAL 的运行被下一次调用续跑（这是引擎的既有契约），完成后状态转为 OK；
3. **清单只做一次**：清单完成后，常规周期只剩 2 个 scope（版本 + 窗口）、2 次请求、4.3 秒；
4. **水位线只在成功时前进**：失败的那次没有把水位线推到未来或错误值。

### 2.2 失败不推进水位线（回归测试）

`tests/test_radar_pipeline.py` 的既有用例覆盖了「scope 失败 → 水位线不前进」；
本轮新增的召回适配器复用同一 `run_source` 引擎，因此继承该保证，并有自己的用例：
`test_a_second_run_does_not_repeat_the_inventory`、`test_the_same_row_recorded_twice_is_one_observation`、
`test_the_ledger_stores_the_event_identifier_for_an_event_level_count`。

## 3. 本轮修复的采集正确性缺陷

| # | 缺陷（真实观测） | 症状 | 修复 | 回归测试 |
| --- | --- | --- | --- | --- |
| 1 | openFDA 对「无结果」返回 404，适配器当成失败 | 6 个产品码（CAP / DRW / FLA / GLY / QYW 及另一个）永远无法完成清单，来源状态 PARTIAL | `allow_not_found=True`，404 = 空清单 | `tests/test_radar_recall.py` |
| 2 | 试运行（`--dry-run`）会创建 `sync_run` 且不结束 | 账本里留下一个永久 `RUNNING` 的周期；状态页误报 | 试运行不创建/恢复运行记录，也不写失败记录 | 代码路径 + 手工复验 |
| 3 | 事件身份只存在于 payload | 事件级计数与去重依赖标题/载荷，索引与条目可能不一致 | 事件号写入 `observation_identifier`，加载时随行读出 | `test_one_recall_event_with_several_product_rows_is_one_item`（断言索引只有一个键） |

## 4. `advance` 在 1.5 万条语料上的不收敛（本轮实测的可靠性发现）

**现象**：`python -m medradar radar run` 在采集完成后进入 `advance()`，在 25 分钟内未收敛；
期间 `observation` 已全部处理（15,156 条状态到达 `AI_PENDING`），但循环仍在继续；进程被手工终止。

**随后**：单独运行 `radar reproject`（只做准入投影）**28 秒**完成（一次 1,749 条，第二次 0 条），
`admission_current` 达到 15,156 条、工作队列为空。

**观察到的事实（可用于定位，但未最终确认根因）**：

- `admission_workqueue` 中有 **2,149** 条 `mapping_changed` 记录；
- `ledger.record_admissions()` 返回的是**准备好的行数**，不是**实际插入的行数**（`INSERT OR IGNORE` 的重复不计）；
- `engine.advance()` 用 `admitted` 的非零值让 `batch_work` 保持为正，于是循环只在 `max_batches`（默认 60）处停止。

**结论**：这是一次**真实的、被记录下来的可靠性缺陷**，不在本轮授权范围内（属于既有 `advance` 的收敛条件），
因此本轮**没有**改它。已经做的是：把「采集」与「准入投影」拆开执行，并验证后者是幂等的。
下一轮的第一件事应当是把它修成「以实际插入行数判断收敛」。

## 5. 健康检查：能否反映真实进度

| 检查 | 是否反映实际进度 | 证据 |
| --- | --- | --- |
| 每源 `last_checked_at` / `watermark` / `last_run_outcome` | 是 | `radar status` 七行来源，`openfda_recall` 显示 2026-11-18T15:05:06 与水位线 2026-11-05 |
| 一致性检查（孤儿版本、首见时间漂移、未推进水位线、未来水位线） | 是（本轮新增的 `watermark_in_future` 是 FP-001 的成果） | `radar verify` 退出码非 0 |
| 顶层 `state` 是否聚合一致性 | **否**（残留缺口） | 见第 1 节 |
| AI 队列是否被误当成失败 | 否：15,152 条 `AI_PENDING` 是「本机未启用 AI」的真实状态 | `radar status` 的 `ai backlog` 行 |

## 6. NOT VERIFIED（本轮无法证明的事）

1. **一个新发布的召回能否在 X 小时内被发现**：窗口内**没有**新的监护召开发布（最后一条公开日期 2026-11-05），
   因此「持续发现能力」只证明了机器正确，没有证明在新事件上生效。
2. **Crossref / PubMed 的真实增量发现**：本轮没有运行这两个来源（避免扩大范围），其水位线行为来自既有测试与 FP-001 文档。
3. **生产环境的任何行为**：无访问权限。
4. **失败恢复的极端情形**（进程崩溃在事务中途、磁盘满、SQLite 锁超时）：未做破坏性实验。
