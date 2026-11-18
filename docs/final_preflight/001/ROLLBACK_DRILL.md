# FINAL-PREFLIGHT-001 / 回滚演练（实际执行）

- 位置：`/srv/medradar/release-gate/001/rollback/`（隔离副本，生产从未参与）
- 旧版本：`14eaf61`（v2 代码） · 新版本：`b6f4506`（v3 代码）
- 结论：**12 步全部执行；重放后 3/3 条切换后记录逐字段一致；恢复耗时 0.55 s。**

---

## 1. 十二步的实际执行

| # | 步骤 | 实际做法 | 结果 |
| --- | --- | --- | --- |
| 1 | 旧版本持续运行 | 用生产备份做底（8,360 条，v2） | 基线：8,360 观测 / 8,360 版本 / 8,360 判定 |
| 2 | 一致性备份 | SQLite 在线备份 API | `rollback-point.db`，integrity **ok** |
| 3 | 停止旧写入者 | 演练中由脚本串行执行（真实切换用 `systemctl stop`） | 无并发写 |
| 4 | 执行 v2→v3 迁移 | 新版本打开库 | **0.6 s**，schema → `radar-ledger-v3` |
| 5 | 启动新版本 | 用新版本代码写入 | — |
| 6 | 新版本产生新 Observation | 3 条合成记录（`DRILL-1..3`，明确标记） | 8,360 → **8,363** |
| 7 | 新版本产生新 Admission | `apply_admissions` | 判定 8,360 → **13,360**（+5,000 条 v3 判定） |
| 8 | 新版本更新水位线/来源状态 | `set_watermark` + `note_source_success` | openfda_device 水位线 `2026-11-09` → `2026-11-18` |
| 9 | 模拟新版本故障 | 进程结束，只留下 `live.db` | — |
| 10 | 执行回滚 | 恢复 `rollback-point.db` 到新文件 | 观测回落到 8,360，DRILL 记录 **0** 条（如预期丢失） |
| 11 | 恢复旧版本可读状态 | 旧代码打开 + 重放增量 + 重判 | 观测 **8,363**，DRILL **3/3** 恢复 |
| 12 | 比较故障前后 | 逐字段对比 | 见 §2 |

### 1.1 步骤 6 的合成数据（明确标记）

```
DRILL-1  [DRILL] patient monitor firmware update 1   first_observed 2026-11-18T21:00Z
         随后更新一次 → version 2 @ 2026-11-18T23:30Z (changed_fields: abstract)
DRILL-2  [DRILL] patient monitor firmware update 2   first_observed 2026-11-18T22:00Z
DRILL-3  [DRILL] patient monitor firmware update 3   first_observed 2026-11-18T23:00Z
```

只写入隔离副本，从未进入生产库，也从未进入任何简报。

---

## 2. 逐字段比较（故障后 vs 回滚后）

```
drill records in the new-version ledger: 3
drill records recovered after rollback: 3
   DRILL-1 identical | (first_observed 2026-11-18T21:00:00+00:00, v2, 1624667d8f1d…)
   DRILL-2 identical | (first_observed 2026-11-18T22:00:00+00:00, v1, d7734021dd7a…)
   DRILL-3 identical | (first_observed 2026-11-18T23:00:00+00:00, v1, 3f01fd66e02e…)
```

版本链（回滚后仍然完整，且每条版本保留原始时间戳）：

```
v1 2026-11-18T22:00:00+00:00 NEW      d7734021dd7a…   (DRILL-2)
v1 2026-11-18T21:00:00+00:00 NEW      2414f64ba866…   (DRILL-1 的首版)
v2 2026-11-18T23:30:00+00:00 UPDATED  1624667d8f1d…   (DRILL-1 的更新)
v1 2026-11-18T23:00:00+00:00 NEW      3f01fd66e02e…   (DRILL-3)
```

计数对比：

| 指标 | 切换前 | 切换后 | 回滚+重放后 |
| --- | --- | --- | --- |
| 观测 | 8,360 | 8,363 | **8,363** |
| 版本 | 8,360 | 8,364 | **8,364** |
| 判定 | 8,360 | 13,360 | 8,363（旧版本重判，v3 判定不保留） |
| 水位线 openfda_device | 2026-11-09 | 2026-11-18 | **2026-11-09**（退回，意味着重查） |

---

## 3. 回滚后的产品可用性（不是"文件能打开"，而是"产品能跑"）

用**旧版本**对恢复后的账本执行产品自带命令：

```
$ radar verify
integrity: OK
counts: {'observations': 8363, 'versions': 8364, 'changes': 8364, 'mappings': 8363}

$ radar advance
graph: pending 3, materialized 3, assertions_created 38, duplicates 10, errors []
published: 3   ai_queued: 8363   batches: 22   converged: true
```

也就是说：回滚后的账本不仅能被旧代码读取，还能被旧版本正常推进到一个收敛状态。

---

## 4. 耗时

| 步骤 | 耗时 |
| --- | --- |
| 恢复备份（文件复制） | < 0.1 s |
| 重放 3 条（含 4 个版本） | `0.2 s |
| 旧版本重判 | `0.2 s |
| **合计（restore + replay + re-decide）** | **0.55 s** |

对 8,363 条的账本，这个量级意味着回滚是"分钟级操作里的秒级步骤"。

---

## 5. 演练中的两次失败（诚实记录）

| 失败 | 原因 | 修正 |
| --- | --- | --- |
| 迁移报 "attempt to write a readonly database" | 演练脚本以 root 复制文件，文件属主变成 root，medradar 无法写 | 复制后 chown；正式 Runbook 里也应注明 |
| 重放报 "RecordOutcome has no attribute change_state" | 我按假设的字段名写工具，实际字段是 state | 修正工具并重跑；这类错误只有在真跑时才暴露 |

两次都发生在**演练**中，没有触及生产。这正是演练存在的意义。

---

## 6. 结论

- 12 步全部实际执行，不是推演。
- 切换后的观测、版本链、首次发现时间、内容哈希**逐字段一致**。
- 旧版本在恢复后能通过自身完整性审计并完成一个收敛周期。
- 剩余风险（v3 判定、运行审计、水位线）都是派生/可重建的，不构成记录丢失。
- **回滚不再是发布阻塞。**
