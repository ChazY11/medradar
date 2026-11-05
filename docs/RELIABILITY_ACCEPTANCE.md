# MedRadar Observatory Reliability — 验收报告（A–G）

- 分支：`feat/observatory-reliability-v1`（stacked on PR #13 head `5335dfd`）
- 验收日期：2026-11-03（UTC；本机时区 UTC+8）
- 环境：Windows 10/11，Python 3.12.10，SQLite WAL，单机
- 证据目录：`docs/reliability/evidence/`（由 `scripts/observatory_reliability_evidence.py` 从真实账本重新生成）
- 关联 PR：本文提交后创建的 Draft PR（stacked on `feat/live-observatory-v1`）

> 本报告只写真实发生的事。七天连续验证**尚未结束**，因此验证状态只能是
> `VALIDATION_IN_PROGRESS`，绝不写“通过”。生产环境部署状态仍是 **NOT_DEPLOYED**（未授权
> 主机/对象存储/正式 SEC 联系方式），本机状态为 `DEPLOYED_LOCAL`。

---

## A. 工程现状：哪些能力已经真实运行，哪些只是部署准备

### A.1 已经真实运行（有账本/日志/任务记录为证）

| 能力 | 真实证据 |
|---|---|
| 单写租约（单实例采集） | 计划任务运行期间，第二个采集进程被拒绝：`docs/reliability/evidence/concurrency_refusal_live.json`（`lease_held_by_supervisor=true`、`refused=true`、`LOCKED_SKIPPED`）；旧进程被强制结束后，下一个进程自动接管并写入 `runtime_state["lock_recovery"]` |
| Windows 计划任务（每 360 分钟一轮单次采集） | 任务 `MedRadarObservatory`：`State=Ready`、`Last Result=0`、`Last Run Time=2026-11-03 23:58:40 (local)`；日志 `logs/collector-20261103.log` 记录 one-shot pass OK、`watch finished: cycles=1 status=OK failures=0`、`[watcher] exit: code=0` |
| 每日一致性备份任务 | 任务 `MedRadarObservatoryBackup`：`Last Result=0`，日志 `logs/backup-20261103.log`；账本 `runtime_state["last_backup"]` = bundle `observatory-20261103T160001Z`，`status=OK`、`verified=true`、`manifest sha256=50bfef00…` |
| 一致性备份 + 哈希清单 + 保留策略 | 备份包含 `ledger.sqlite`（SQLite 在线备份 API）+ `raw-cache/`（原始 HTTP 响应）+ `MANIFEST.json`；`--prune` 本次 `kept=1, pruned=1`；实现包含“不可验证 bundle 只隔离不删除、最新 bundle 永不删除”（测试覆盖） |
| 隔离恢复演练 | `docs/reliability/evidence/backup_and_restore.json`：drill `status=OK`，11/11 检查通过，`first_seen_identity` 400 行 0 mismatch，新写入行获得**新的** `first_seen_at` 而旧 400 行保持不变 |
| 账本完整性审计 | `docs/reliability/evidence/audit_report.md`（真实账本，只读）：9 PASS / 0 FAIL / 2 REQUIRES_MANUAL_REVIEW |
| 健康状态 | `observatory health` = `VALIDATION_IN_PROGRESS`（部署 `DEPLOYED_LOCAL`、验证进行中、备份/演练/新鲜度/一致性全部通过；无任何“绿色掩盖失败”） |
| 七天验证的记录机制 | `runtime_state["validation"]`：`started_at=2026-11-03T15:35:37Z`、`ends_at=2026-11-10T15:35:37Z`、`planned_slots=28`；12 次真实运行全部 OK，0 duplicates，0 integrity violations |
| 采集阶段标注（append-only） | 真实账本 400 条：`INITIAL_DISCOVERY=399`、`INCREMENTAL_DISCOVERY=1`、`HISTORICAL_BACKFILL=0`；历史 400 行未被改写，只追加 `observation_phase` 元数据行 |
| 采集结果区分 | `source_state.last_outcome`：三源均为 `NO_NEW_RECORDS`（正常），与 `FETCH_FAILED`（故障）在 API/UI 中分别呈现 |

### A.2 只是“部署准备”（没有真实部署，不能宣称）

- Linux systemd service/timer 模板（`deploy/systemd/`）：内容与必需指令已验证，但**从未在授权主机上安装**。
- 生产持久化主机 + 异地对象存储备份：只给出成本与操作方案，**未购买、未创建**任何资源。
- `DEPLOYED_SERVICE` 状态：未记录（当前部署记录为 `DEPLOYED_LOCAL` + `supervisor=windows_task`）。

---

## B. 存储方案：选了什么、为什么、多少钱、怎么恢复

### B.1 决策：A + B（持久磁盘 + 自动异地备份，宿主为小型 VPS）

| 方案 | 月成本量级 | 恢复复杂度 | 结论 |
|---|---|---|---|
| **A. 持久磁盘 + 自动异地备份** | 主机 €4–7 + 对象存储 €0–1 | 复制一个文件 + 校验清单 | **采纳（作为架构）** |
| **B. 小型 VPS + SQLite + 对象存储** | €4–7 | 同上 | **采纳（作为宿主形态）** |
| C. 托管数据库 + 对象存储 | €15–40+ | dump/restore，迁移复杂 | 当前规模拒绝 |
| D. GitHub Actions cache/artifact 作为系统记录 | €0 | 缓存会被驱逐 | **拒绝**（仅作低频补充） |

理由：单写者、单文件、事务完整、零运维；当前账本 1.9 MB，按 30–80 条观察/天的稳态增长
约 50–150 MB/年（含版本），SQLite 在可预见的数年内仍是正确选择。真正的风险不是数据库引擎，
而是“只有一份拷贝”——因此异地备份是必选项。

### B.2 预估费用与扩展

- 估算：**€5–8/月**（1 vCPU / 1–2 GB RAM / 20 GB SSD 的小型 VPS；对象存储 <10 GB + 30–90 天保留）。
- 不引入 Kubernetes/Kafka/分布式数据库；迁移阈值：账本 >2 GB 或多写入者需求时，先把
  `observation*` 导出为 Parquet/只读副本，再考虑托管数据库。
- **未产生任何费用**；创建付费资源需要项目负责人授权（见 F 节）。

### B.3 备份与恢复（已实现并真实验证）

- 一致性：`sqlite3.Connection.backup()`（在线备份 API），绝不复制正在写的 WAL 文件。
- 完整性：每件 artifact 记录 SHA-256 + 字节数；`verify_backup` 重新计算并重跑
  `PRAGMA integrity_check` 与账本一致性检查；**未验证的备份不报告 OK**。
- 保留：7 日 + 4 周 + 6 月；不可验证 bundle 移入 `quarantine/`（不删除）；最新 bundle 永不删除。
- 缓存：原始 HTTP 响应随备份归档；`prune_raw_cache` 只删除超过保留期且账本已保存其规范
  payload 的缓存文件，绝不触碰账本/冻结研究文件。
- 恢复流程：`observatory restore --from <bundle> --to <dir>`，恢复前校验清单哈希；
  恢复后 `verify_restored` 比对计数、`first_seen_at` 最值、来源分布、版本/变更计数、watermark。
- 异地：`docs/BACKUP_AND_RECOVERY.md` 提供 rclone/restic/S3 命令模板（不写入任何凭据）。

---

## C. 真实运行证据

| 项目 | 真实值 |
|---|---|
| 首次真实采集 | `2026-11-03T14:39:53Z`（SEC EDGAR） |
| 观察总数 | **400**（SEC 6 · ClinicalTrials.gov 157 · Europe PMC 237），全部 `LIVE`，0 回填 |
| payload 版本 / 变更记录 | 400 / 400 |
| 首次观察时间范围 | `2026-11-03T14:39:53Z` → `2026-11-03T14:49:51Z` |
| 同步运行总数 | **34**（全部 `status=OK`；其中 6 条历史 `STRUCTURE_CHANGE` 告警保留在 `source_failure`，来自 v1 检测器误报，已修正并重建基线） |
| 最近成功采集 | SEC `2026-11-03T15:58:43Z` · CT.gov `15:58:45Z` · Europe PMC `15:58:46Z` |
| 计划任务实际执行 | `MedRadarObservatory`：`Last Result=0`，`Last Run Time=2026-11-03 23:58:40`；单轮采集 3 源全部 OK |
| 每日备份任务实际执行 | `MedRadarObservatoryBackup`：`Last Result=0`，bundle `observatory-20261103T160001Z`（6.8 MB，含原始缓存 36 files），manifest 已验证 |
| 账本大小 | 1.9 MB（不同备份含缓存后约 6.8 MB） |

说明：34 次运行中绝大多数是人工触发的验证轮次；它们被如实记录为真实运行，但**不作为七天
计划轮次**（slots 只按验证窗口内的计划时刻统计）。这正是“不伪造时间跨度”的实现方式。

---

## D. 可靠性数据

### D.1 当前窗口指标（`observatory validate status`）

| 指标 | 值 |
|---|---|
| 验证状态 | `VALIDATION_IN_PROGRESS` |
| 窗口 | `2026-11-03T15:35:37Z` → `2026-11-10T15:35:37Z`（已过 0.017 天，剩余 6.983 天） |
| 计划轮次 / 已到期 / 已执行 / 遗漏 | 28 / 0 / 0 / 0（首个计划轮次在窗口开始后 6 小时，尚未到期） |
| 窗口内启动运行 / 成功 / 部分 / 失败 | 12 / 12 / 0 / 0 |
| 每来源成功率 | SEC 4/4、CT.gov 4/4、Europe PMC 4/4 = 100% |
| Duplicate rate | **0**（0 重复观察组，0 重复 payload 版本） |
| Integrity violations | **0**（触发器 + `consistency_check`） |
| 可测采集延迟 | SEC 唯一可测（来源提供秒级 `acceptanceDateTime`）；CT.gov/Europe PMC 明确“无法测量”（仅日期） |
| 采集新鲜度 | 三源均 < 1 小时（截至报告生成时刻） |
| 存储增长 | 账本 1.9 MB / 400 条观察；每日快照由 `ops_metric: daily_snapshot` 记录 |
| 恢复演练 | 11/11 检查通过，耗时 796 ms |
| 备份 | `status=OK`、`verified=true`、哈希清单 `50bfef00…`、计数与账本一致（400/400/400/34） |

### D.2 单写者并发保护（真实运行验证）

- 计划任务执行期间（租约持有人 `mode=watch`，heartbeat 4.6 秒前），另一进程执行
  `observatory sync` → `locked=true`、`LOCKED_SKIPPED`，未创建任何 `sync_run`、未写任何观察。
- 租约被强制结束（模拟崩溃）后的下一次采集：自动接管并写入
  `runtime_state["lock_recovery"]`（含旧 pid/host/heartbeat 与接管原因）。
- 合成测试另证：非陈旧租约拒绝、陈旧租约接管、强制释放留痕、watch 全程持有租约且不自我拒绝。

### D.3 故障注入（自动化测试，非口头保证）

`tests/test_observatory_reliability.py` · `tests/test_observatory_backup.py` ·
`tests/test_observatory_audit.py` · `tests/test_observatory_health.py` ·
`tests/test_observatory_deploy.py`（共 **80** 项离线测试；其中 PowerShell/schtasks 相关的
1 项在缺少 Windows 工具的 CI 主机上显式 skip，绝不冒充通过）：

- 分页超时/中断 → `PARTIAL`，续跑后记录数正确、无重复、`NEW` 恰 N 条；
- 备份 artifact 被篡改 1 字节 → `verify_backup` 失败；恢复拒绝被篡改 bundle；
- 缺失/损坏 MANIFEST 的 bundle 只隔离不删除；保留策略不会删除最新 bundle；
- 捕获陈旧租约并留审计；第二个采集进程被拒绝；
- 审计注入（孤立版本行、重复观察、水位异常、冻结文档篡改）→ FAIL / REQUIRES_MANUAL_REVIEW；
- 健康优先级：无部署 `NOT_DEPLOYED`、暂停 `PAUSED`、单源失败/备份缺失 `DEGRADED`、
  验证中 `VALIDATION_IN_PROGRESS`、全部达标 `OPERATIONAL`；
- 七天验证：窗口结束前 `stop --outcome passed` 被拒绝；遗漏轮次计为 missed 而非成功。

### D.4 账本一致性审计（真实账本，只读）

`overall = REQUIRES_MANUAL_REVIEW`（8→9 PASS、0 FAIL、2 人工复核）：

| 检查 | 结论 |
|---|---|
| 重复观察 / first_seen 完整性（含 13 个不可变触发器）/ 版本链 / 版本-变更一致 / 时间顺序 / 水位安全 / 映射历史 / 备份可复现 / 阶段完整性 | **PASS**（9 项，均有具体计数与证据） |
| 时点回放正确性 | `REQUIRES_MANUAL_REVIEW`：真实账本没有任何 `version_count>1` 的观察（本轮真实修订为 0），因此**没有多版本样本可验证**；补充诊断 20 条单版本样本全部能在 `snapshot(first_seen_at)` 返回（曾发现并修复了 `Z`/`+00:00` 拼写导致的边界缺陷） |
| 前瞻登记器冻结完整性 | `REQUIRES_MANUAL_REVIEW`：`data/prospective` 目前没有冻结研究输入，缺少证据不能算 PASS |

审计工具对“无法自动证明”的事项返回人工复核，而不是默认通过——这是设计目标。

---

## E. 科研可信度

- **可回放证据完整**：400 条观察的 `first_seen_at` 在隔离恢复后 400/400 完全一致；
  版本链、变更历史、状态历史、映射历史、watermark 全部随备份恢复且审计通过。
- **不可变约束有物理实现**：`first_seen_at`、版本行、status/mapping/phase 日志由 SQLite
  触发器保护；并发写入由租约阻止；审计每次都会验证这些触发器是否存在。
- **没有无法解释的时间异常**：审计 0 FAIL；近期修复的 `Z` 与 `+00:00` 时间拼写问题
  已用回归测试锁定（同一瞬间在两种拼写下必须等价）。**历史不可变行没有被改写**。
- **阶段与来源标记诚实**：399 条为“系统初次上线时发现的既有公开记录”，1 条是持续监测
  期间的新发现；`observation_origin` 仍全部为 `LIVE`，0 回填。“事件发生在过去”没有被
  错误标记为历史回填。
- **仍然没有的东西**：真实多版本修订样本（真实世界本轮未发生可观察修订）、已验证的
  前瞻预测、人工真值复核、全球数据完整性——这些继续明确列为边界。

---

## F. 未完成事项 / 需要授权

| 事项 | 状态 | 需要什么 |
|---|---|---|
| 七天连续观察验证 | **VALIDATION_IN_PROGRESS**（窗口至 `2026-11-10T15:35:37Z`） | 真实时间；期间采集由已注册的单轮计划任务执行，结束后用 `observatory validate stop` 生成最终结论 |
| 生产级持久化部署（`DEPLOYED_SERVICE`） | **NOT_DEPLOYED** | 授权购买小型 VPS（€4–7/月）+ 异地对象存储；在授权主机安装 systemd 单元并用 `deploy-status --status DEPLOYED_SERVICE` 记录 |
| 异地/加密备份通道 | 本机备份已验证；异地**未启用** | 对象存储凭据（不写入 Git）；rclone/restic/S3 命令模板已提供 |
| SEC 生产联系方式 | 使用仓库内置示例 UA；真实 SEC 会拒绝通用占位联系人 | 一个**已授权的真实联系邮箱**，通过 `MEDRADAR_SEC_UA` 环境变量注入（绝不写入仓库） |
| 前瞻登记器真实冻结点 | 无（只有合成测试条目） | 有科学假设且冻结时点证据齐备时，由研究负责人确认后冻结 |
| 真实修订/删除事件 | 0 条 | 只能等真实世界发生；机制由可控合成测试证明 |
| 真实多版本回放审计样本 | 0 条 | 同上；审计保持 REQUIRES_MANUAL_REVIEW，不伪造 |

---

## G. 交付与运行方式

### G.1 代码/文档/测试

- 新增：`medradar/observatory/{lock,backup,restore,audit,health,validation}.py`、
  `scripts/{observatory_watch,install_windows_task,uninstall_windows_task,observatory_backup_task,observatory_backup_drill,observatory_reliability_evidence}.ps1/py`、
  `deploy/systemd/*`、`deploy/windows/README.md`、`tests/test_observatory_{reliability,backup,audit,deploy,health}.py`、
  `docs/{RELIABILITY_DESIGN,DEPLOYMENT,BACKUP_AND_RECOVERY,CONTINUOUS_VALIDATION_PROTOCOL,HEALTH_AND_VALIDATION}.md`。
- 修改：`ledger.py`（追加式 phase、状态列迁移、时间规范化）、`runner.py`/`scheduler.py`
  （租约、结果语义、优雅停止、日志）、`__main__.py`（audit/health/validate/backup/restore/lock/deploy-status/phase/watch --trigger/--log-file）、
  产品层与 UI（Observatory Health 面板、采集阶段筛选）、CI（新增 5 组离线测试）。
- 测试：全量收集 **1316** 项；`python -m pytest tests -q` 通过（离线套件，含所有原有产品测试）。

### G.2 常用命令

```bash
# 健康 / 审计 / 验证
python -m medradar observatory health --json
python -m medradar observatory audit
python -m medradar observatory validate status --json

# 备份 / 校验 / 恢复（隔离目录）
python -m medradar observatory backup --dest data/observatory/backups --verify --prune
python scripts/observatory_backup_drill.py --work-dir out/reliability_drill_final
python -m medradar observatory restore --from data/observatory/backups/<bundle> --to out/restore_check

# 单写租约
python -m medradar observatory lock status
python -m medradar observatory lock release --reason "operator verified stuck"

# 持续运行（Windows 计划任务已注册：采集单轮 / 每日备份）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_windows_task.ps1 -Status
python -m medradar observatory watch --interval-minutes 60 --trigger schedule --log-file logs/collector.log
```

### G.3 重新生成验收证据

```bash
python scripts/observatory_reliability_evidence.py   # docs/reliability/evidence/*
python -m pytest tests/test_observatory_reliability.py tests/test_observatory_backup.py \
  tests/test_observatory_audit.py tests/test_observatory_health.py tests/test_observatory_deploy.py -q
node scripts/product_e2e.cjs http://127.0.0.1:8787   # 需先启动 web
```

### G.4 已注册的本机计划任务（真实状态，可一键移除）

| 任务 | 动作 | 最近结果 | 下次运行 |
|---|---|---|---|
| `MedRadarObservatory` | `observatory_watch.ps1 -IntervalMinutes 360 -MaxCycles 1` | `0` | 2026-11-04 05:50（local） |
| `MedRadarObservatoryBackup` | `observatory_backup_task.ps1`（备份+校验+保留） | `0` | 2026-11-04 04:17（local） |

移除方式：`powershell -File scripts/install_windows_task.ps1 -Uninstall` 与
`Unregister-ScheduledTask -TaskName MedRadarObservatoryBackup`。

---

## 结论

工程实现已经完成并通过本地真实验证：**单写者持续采集、可验证备份、隔离恢复、完整性审计、
诚实健康状态、append-only 阶段标注、可部署模板，以及一个真正在跑的七天验证记录**。

但“七天连续运行验证通过”**还不是事实**：窗口刚开始约 25 分钟，剩余 6.98 天。
因此本报告的状态是 **`VALIDATION_IN_PROGRESS`**，生产部署状态是 **`NOT_DEPLOYED`**。
七天后（`2026-11-10T15:35:37Z` 之后）才能用真实记录生成最终结论。
