# MedRadar 七天连续观察验证协议（CONTINUOUS VALIDATION PROTOCOL）

协议版本：`obs-validation-v1`
适用范围：Live Observatory 的三个官方来源（SEC EDGAR、ClinicalTrials.gov、Europe PMC）
与独立 Observation Ledger（`data/observatory/observatory.sqlite`）。

> 本协议的核心约束只有一句：**没有真实经过七天，就不能报告验证通过。**
> 短时间高频运行只能产生 `VALIDATION_IN_PROGRESS`，不能替代真实时间跨度。

---

## 1. 被验证的科学工程命题

如果今天建立 MedRadar，并按声明周期持续运行，那么七天后必须能够证明：

1. 调度没有被悄悄遗漏，或被遗漏的轮次被如实记录（missed ≠ success）；
2. 单个来源失败不会阻塞其他来源，也不会被健康面板掩盖；
3. 所有观察记录的 `first_seen_at` 只写一次，版本链与变更历史完整、可回放；
4. 采集进程崩溃/中断后能够从检查点恢复，且不重复、不丢失；
5. 账本与备份一致，恢复后仍能复现同一历史观察；
6. 数据新鲜度（freshness）与可测的采集延迟（latency）被真实计算，不可测的明确标注。

验证对象是**可靠性**，不是采集数量，也不是预测能力。

---

## 2. 运行配置（验证期间冻结）

| 项目 | 值 | 说明 |
|---|---|---|
| 采集周期 | **6 小时** | `--interval-hours 6`，7 天计划 **28** 个轮次 |
| 来源 | `sec_edgar,ctgov,europepmc` | 三源独立状态、独立失败记录 |
| 调度方式 | 常驻 `watch`（Linux systemd / Windows 计划任务）或 6 小时 timer | 二者都写入同一 `sync_run` 表 |
| 单写租约 | 必须启用 | `data/observatory/collector.lock`，第二个采集进程被拒绝 |
| 备份 | 每日一次一致性备份 + 最近一次恢复演练 | 备份结果写入 `runtime_state["last_backup"]` |
| 时钟 | 真实系统时钟（UTC 记录） | 人为改时钟会使窗口失效 |

验证窗口启动时，以下内容被写入账本 `runtime_state["validation"]` 并冻结：
`protocol_version, started_at, ends_at, target_days, interval_hours, planned_slots`。
`started_at` 是真实墙钟时间，不允许回填或伪造。

---

## 3. 轮次与状态的严格定义

对每个计划轮次 `slot_i = started_at + i × interval`（i = 1..28）：

| 状态 | 定义 |
|---|---|
| **planned** | 协议规定的计划轮次（28） |
| **due** | 截至当前真实时间已经到期的轮次 |
| **executed** | 在 `[slot_i − tolerance, slot_i + interval)` 内确实存在 `sync_run.started_at`；`tolerance = min(60 min, interval/2)`，且一条运行最多命中一个轮次 |
| **succeeded** | 该轮次对应运行最终 `status = OK`（全部来源成功） |
| **partial** | 运行最终 `status = PARTIAL`（部分来源/页失败） |
| **failed** | 运行最终 `status ∈ {FAILED, INTERRUPTED}` |
| **missed** | 已到期但没有任何运行命中的轮次；**永远不计为成功** |

注意：extra runs（例如人工触发的同步）会被记录为 launched runs，可以让 slot 被命中，
但不会改变 planned 数量；它们也不等于"计划执行"。

---

## 4. 指标与计算口径

所有指标由 `medradar/observatory/validation.py` 从**账本真实行**计算，不维护第二份日志。

| 指标 | 口径 | 目标 |
|---|---|---|
| Scheduler Success Rate | `ok runs / due slots` | 越高越好；验证通过要求 ≥ 0.9 |
| Source Success Rate | 每个来源 `status=OK 次数 / attempts` | 三源分别报告，单个来源失败不得被平均掉 |
| Observation Freshness | `now − source_state.last_success_at`（小时） | 不应超过 `max(3 × 声明周期, 12 h)`；超出标记 stale |
| Collection Latency | 仅对发布时间精确到时刻的记录计算 `first_seen_at − published_at`（SEC 可测；其余“无法测量”） | 不推算、不伪造 |
| Duplicate Rate | 重复 `(source, source_record_id)` 行 + 同一 observation 重复 payload_hash 版本的占比 | **0** |
| Integrity Violations | `ledger.consistency_check()` 的问题数（不可变时间戳、版本链、状态历史等） | **0** |
| Recovery Success | 窗口内 `INTERRUPTED` 运行被后续运行恢复的比例；窗口内无中断时明确写“无法据此证明” | 有失败则必须恢复 |
| Storage Growth | 每日 observation 增量、账本字节数（`ops_metric: daily_snapshot`） | 仅记录，不设硬目标 |

`VALIDATION_PASSED` 的判定（窗口真实结束后才允许）：
1. `now ≥ ends_at`；
2. `scheduler_success_rate ≥ 0.9`；
3. duplicate rate = 0；
4. integrity violations = 0；
5. 所有来源最终状态为 OK（或明确记录且已恢复的失败）；
否则必须 `VALIDATION_FAILED`。判定由 `observatory validate stop` 显式执行并写入账本。

---

## 5. 操作流程

```bash
# 0) 部署与基础设施就绪（详见 docs/DEPLOYMENT.md、docs/BACKUP_AND_RECOVERY.md）
python -m medradar observatory deploy-status --status DEPLOYED_LOCAL --supervisor windows_task --note "本地计划任务"
python -m medradar observatory backup --dest data/observatory/backups --verify
python scripts/observatory_backup_drill.py --json

# 1) 启动验证窗口（写入真实 started_at/ends_at/planned_slots）
python -m medradar observatory validate start --days 7 --interval-hours 6

# 2) 期间：采集由常驻服务/计划任务执行；随时查看真实指标
python -m medradar observatory validate status --json
python -m medradar observatory health --json

# 3) 第 7 天真实结束后，才能关闭窗口
python -m medradar observatory validate stop --outcome passed   # 或 failed
```

日常运维（不改变验证窗口）：
`observatory status | sources | health | audit | backup | restore | pause | resume`。

---

## 6. 记录机制（为什么无法伪造）

- **轮次执行**只来自 `sync_run` 表（由采集引擎写入，`started_at` 不可改）。
- **验证窗口**只来自 `runtime_state["validation"]`，只能由 `validate start/stop` 写入。
- **每日存储增长**来自 `ops_metric: daily_snapshot`（每次 watch 轮询写入）。
- **备份/演练状态**来自 `runtime_state["last_backup"]` / `["last_restore_drill"]`。
- **健康**在读取时实时计算，不缓存结论。
- 因此：把系统时钟调到未来再 `validate stop --outcome passed` 会被窗口判定拒绝（窗口未结束），
  而伪造成本高于真实运行；验证报告中的每个数字都可以被第三方重新计算。

---

## 7. 哪些情况会使验证失效（必须重新开始）

1. 从早于 `validation.started_at` 的备份恢复账本（历史被回退）；
2. 手动修改 `first_seen_at` / 版本行 / `sync_run`（触发器会阻止，若绕过即失去可信性）；
3. 在窗口期内更换账本文件或清理 observation 数据；
4. 系统时钟被大幅调整（运行行与槽位对不上）；
5. 在窗口内用合成数据填充 observation 表（验证报告必须来自真实官方 API 采集）。

发生上述情况时，`validate stop --outcome failed` 并重新 `validate start`。

---

## 8. 当前状态（随代码更新）

截至本协议提交时：

- 验证状态：**VALIDATION_IN_PROGRESS**（真实开始于 2026-11-03T15:35:37Z，计划结束 2026-11-10T15:35:37Z）；
- 计划轮次 28，当前已到期 0（首轮在开始后 6 小时）；
- 账本：400 条观察（399 INITIAL_DISCOVERY + 1 INCREMENTAL_DISCOVERY），0 条历史回填；
- 本报告**不宣称验证通过**；最终结果只能在 2026-11-10T15:35:37Z 之后由 `validate stop` 产生。

七天验证报告模板（验证结束后填写）：`docs/RELIABILITY_ACCEPTANCE.md` 的“验证结果”章节。
