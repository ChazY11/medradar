# RELEASE-GATE-001 / v2 → v3 隔离迁移证据

- 迁移代码：`f2f70dd`（候选分支 `pilot/pilot-ready-001`）
- 迁移对象：`20261118T185150Z` 备份的**副本**（生产库从未被迁移）
- 结论：**迁移成功、可重复、中断可恢复；旧代码会安全拒绝 v3 库而不是写坏它。**

---

## 1. 迁移做了什么

`ObservationLedger._ensure_schema()` 打开 v2 库时执行四步：

1. `observation_admission` 改名为 `observation_admission_v2`（旧表原样保留）；
2. `meta.schema_version` 提升到 `radar-ledger-v3`；
3. 执行 v3 的 `SCHEMA` 脚本（建新表、索引、触发器；对已存在的表是幂等的）；
4. 把旧表的每一行**复制**进新的追加型判定表，然后删除旧表。

旧的 8,360 条判定不是被"重算"，而是被"搬运"：`rules_digest = 'legacy-v2'`、
`evidence_key = 'legacy:' || admission_version`、`decision` 由 `tier` 映射而来。
新规则产生的判定是**另起一行**追加，不覆盖。

---

## 2. 实测：耗时、体积、幂等

| 指标 | 值 |
| --- | --- |
| 首次打开（含迁移）耗时 | **0.58 s**（进程内计时）；含解释器启动 0.75 s |
| 第二次打开耗时 | **0.011 s**（不再迁移） |
| 账本体积 | 45,268,992 B → **52,322,304 B**（+15.6%） |
| 表数量 | 18 → 20（新增 `admission_current`、`admission_workqueue`） |
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` | 0 违规 |

> 更正一个早前的估算：上一轮曾用"迁移 + 全量重判"后的体积（75 MB）推断迁移会让库增长 66%。
> 本轮把两件事分开测了：**迁移本身只增长 15.6%**；额外的增长来自 v3 追加判定与召回回填的数据。

### 2.1 幂等

同一份库连续打开两次，第二次 0.011 s，行数、`admission_current` 行数与第一次完全相同：

```
"idempotent": true
```

`test_radar_migration_resume.py::test_finishing_a_migration_twice_adds_nothing` 固定了这一点。

---

## 3. 迁移前后：一行都没有丢

| 表 | 迁移前 | 迁移后 | 判定 |
| --- | --- | --- | --- |
| observation | 8,360 | 8,360 | 不变 |
| observation_version | 8,360 | 8,360 | 不变 |
| observation_change | 8,360 | 8,360 | 不变 |
| observation_mapping | 8,360 | 8,360 | 不变 |
| observation_facet | 17,285 | 17,285 | 不变 |
| observation_identifier | 1,660 | 1,660 | 不变 |
| source_state | 6 | 6 | 不变 |
| sync_run | 24 | 24 | 不变 |
| observation_admission | 8,360 | **8,360** | 全部搬入，`rules_digest='legacy-v2'` |
| admission_current | —（不存在） | 8,360 | 从历史重建 |
| observation.work_key | —（不存在） | 8,360 行全部填充 | 新增的派生列 |

旧判定的 `tier` 到新 `decision` 的映射（逐类计数，与迁移前完全吻合）：

```
HIGH_RELEVANCE 7,166 → FEED      7,166
LOW_RELEVANCE    682 ┐
IRRELEVANT       117 ┘ → EXCLUDED  799      （682 + 117 = 799 ✓）
NEEDS_REVIEW     395 → REVIEW      395
                    合计 8,360 ✓
```

**判断历史没有被静默改写**：`observation_admission` 上的 BEFORE UPDATE / BEFORE DELETE 触发器
在迁移后重新创建，实测 `UPDATE`/`DELETE` 仍然抛 `IntegrityError`（沿用
`test_an_admission_decision_cannot_be_updated_or_deleted`）。

---

## 4. 中断恢复：本轮发现并修复的一个发布阻塞缺陷

### 4.1 缺陷

迁移把 `schema_version` 提升到 v3 的时机**早于**旧行复制完成。如果进程在这个窗口内被杀：

- `meta` 已经是 v3；
- `observation_admission` 是空的新表；
- 8,360 条判定还在 `observation_admission_v2` 里；
- 下一次打开看到"已经是 v3"，**跳过迁移分支**，永远不会去复制。

结果：**判定历史永久不可见**（数据还在，但产品读到 0 条），而且没有任何报错。

### 4.2 复现（确定性）

在隔离副本上手工重建那个中间状态（改名 + 提升版本号），然后用**未修复**的代码打开：

```
INTERMEDIATE: meta=v3, leftover_v2=true, observation_admission=null
AFTER_OPEN  : meta=v3, leftover_v2=true, observation_admission=0, admission_current=0
```

8,360 → 0。用 `SIGKILL` 的真杀测试因为迁移只要 0.5 s，反而不容易命中窗口；
确定性复现才是这条缺陷的可信证据。

### 4.3 修复

`e4aaff6`：把"完成复制"从"只在改名的那一次运行"改成**每次写打开都尝试**。
复制本身是幂等的（`INSERT OR IGNORE` + 确定性 evidence key），失败时旧表不会被删。

修复后同一中间状态：

```
AFTER_OPEN: meta=v3, leftover_v2=false, observation_admission=8360, admission_current=8360
```

回归测试：`test_a_crash_between_the_version_bump_and_the_copy_is_repaired_on_reopen`、
`test_finishing_a_migration_twice_adds_nothing`。

---

## 5. 旧代码遇到 v3 库会怎样（回滚安全性的关键）

实测：用**生产正在跑的 `14eaf61`** 打开一份已迁移的 v3 库。

```
refused: RuntimeError
message: … unsupported radar ledger schema 'radar-ledger-v3' (this build requires
         'radar-ledger-v2'). There is no automatic migration from that version and
         no data was modified …
sha256 before: 451abf3be6ac45a8c0d5949be3f2866ec30edf7cb2cc1f840005ca00f316109e
sha256 after : 451abf3be6ac45a8c0d5949be3f2866ec30edf7cb2cc1f840005ca00f316109e
VERDICT: old code refused and modified nothing
```

两个结论：

1. **好消息**：代码回滚不会悄悄写坏 v3 库——它大声失败，文件哈希不变。
2. **代价**：只回滚代码 = 服务起不来。所以路径 B 必须"代码 + 数据"一起回滚
   （见 `BACKUP_AND_RESTORE.md` §5.2）。

---

## 6. 迁移后的读写兼容性

迁移完成后，候选版的所有读写路径都在同一份数据上跑过：

| 检查 | 结果 |
| --- | --- |
| `radar verify` | 通过（除水位线告警，见下） |
| `radar status` | 正常输出 7 个来源、状态、水位线、backlog |
| `radar advance` | `CONVERGED`，1 批 |
| `radar reproject` | `decided now = 0`（幂等） |
| `radar run`（真实采集） | 6 个来源，新增 1,330 条，42 批收敛 |
| `radar brief` | 7 天窗口生成成功 |
| API（health/sources/feed/detail/brief/graph/technology-map/pipeline/notices） | 全部 200 |
| 图谱 | 45,174 节点 / 29,082 边，可由 `rebuild-graph` 重建 |

迁移后 `radar verify` 报的唯一问题是 `watermark_in_future`（crossref、pubmed 各领先 1 天），
这是**生产原有的数据问题**，不是迁移引入的。详见 `HEALTH_MONITORING.md` §4。

---

## 7. 迁移的外部风险与缓解

| 风险 | 实测/评估 | 缓解 |
| --- | --- | --- |
| 迁移期间写锁 | 迁移在 `_ensure_schema` 里同步完成，0.58 s，SQLite 会短暂持有写锁 | 切换时先停调度器，再启动 Web（见 `RELEASE_RUNBOOK.md`） |
| 迁移期间磁盘不足 | 迁移是原地操作，峰值需求 ≈ 新表大小（约 7 MB） | 磁盘 44 GB 可用，无压力 |
| 迁移失败后库处于中间态 | 修后可恢复；旧代码会拒绝并保持文件不变 | 迁移前必备份；失败时用备份重来 |
| 迁移后立刻发布 | 迁移与 `advance` 是两个动作 | 先迁移并校验，再让调度器跑第一轮 |

---

## 8. 复现命令

```bash
# 1) 迁移（隔离副本）
cp /srv/medradar/release-gate/001/backup/20261118T185150Z/radar.db /tmp/mig/radar.db
sudo -u medradar env PYTHONPATH=<release> python -c \
  "from medradar.radar.ledger import ObservationLedger; ObservationLedger('/tmp/mig/radar.db').close()"

# 2) 校验
sqlite3 /tmp/mig/radar.db "PRAGMA integrity_check; SELECT * FROM meta;"
# 或使用产品自带审计
sudo -u medradar env MEDRADAR_RADAR_DIR=/tmp/mig PYTHONPATH=<release> \
  python -m medradar radar verify

# 3) 中断恢复回归
python -m pytest tests/test_radar_migration_resume.py -q
```
