# PILOT-READY-001 / 阶段二：两个已知运行缺陷的根因、修复与验收

- 代码基线：`v1/001` = `a6da0f4a`（自 `first-principles/001` `6f4d079` 之后三层）
- 修复分支：`pilot/pilot-ready-001`（worktree `D:\DEPPSKK\medradar-pilot-001`）
- 改动文件：`medradar/radar/ledger.py`、`medradar/radar/engine.py`、`medradar/radar/health.py`、
  `tests/test_radar_watermark.py`（测试自身的时区缺陷）、新增
  `tests/test_radar_advance_convergence.py`、`tests/test_radar_health_verdict.py`
- 未改动：判定规则、分级阈值、适配器、API 契约、前端、数据模型字段

---

## P0-01：`advance()` 无法收敛

### 1. 独立复核：先验证线索，再接受线索

任务书给的线索是"`record_admissions()` 返回准备写入的行数，而不是实际新增的行数"。这条线索**成立，
但不是全部原因**。本轮在 8,358 条真实账本副本与 15,000 条真实规模负载副本上分别复现后，确认这是
**两个叠加的缺陷**。

#### 缺陷 A：返回值语义错误（确认线索）

`ledger.record_admissions()` 用 `INSERT OR IGNORE` 写入追加型判定历史，唯一键是
`(observation_id, admission_version, evidence_key)`；重复判定会被静默忽略。但函数返回的是
`len(prepared)`——即**提交上去的行数**，不是**真正新增的历史行数**。

```python
# 修复前 (medradar/radar/ledger.py)
        with self._transaction():
            self.con.executemany("INSERT OR IGNORE INTO observation_admission …", prepared)
            …
        return len(prepared)
```

后果：任何"证据未变、规则未变"的重复判定都会报告"我做了 N 件事"，即使一行都没写。

#### 缺陷 B：终止条件用了累计值（任务书未提到，但这是不收敛的直接原因）

`advance()` 的循环体末尾是：

```python
# 修复前 (medradar/radar/engine.py)
        admitted += apply_admissions(ledger, limit=limit)
        batch_work += 1 if admitted else 0        # ← admitted 是累计值
        if batch_work == 0:
            converged = True
            break
```

`admitted` 是**跨批次累计**的。只要本进程任意一批完成过一次判定，`admitted > 0` 就永久成立，
于是 `batch_work` 永远 ≥ 1，`batch_work == 0` 永远不可达，`converged` **结构上不可能为 True**。

#### 复现（真实规模，逐批记录）

用 `pilot001-scratch/probe_advance.py` 逐批复刻 `advance()` 的循环体并记录每一批的五项工作量，
在 8,358 条生产账本副本上得到：

```
第 21 批: stale_mapping=0 materialized=0 published=0 ai_queued=358 admission_pending=358
第 22 批: stale_mapping=0 materialized=0 published=0 ai_queued=0   admission_pending=0
          apply_admissions 返回 0
          → 真实工作量全部为 0，但 batch_work = 1（仅因为累计 admitted = 8358）
```

**第 22 批已经没有任何真实工作可做，循环却继续跑满 60 批。**

#### 这是"部署即触发"的缺陷，不是"每次都触发"的缺陷

同一份生产账本，用**已部署代码**（`14eaf61`）跑 `advance()`：22 批、2.23 s、`converged=true`
（因为该库的判定版本与代码一致，`apply_admissions` 全程返回 0）。只有当**规则版本 / 判定版本变化**
（也就是每一次部署新规则）时，才会真正执行判定，缺陷才被触发。

这解释了为什么它在约 15,000 条语料上"运行超过 25 分钟仍不收敛"——那是一次带着规则改动的运行。

### 2. 最小必要修复

#### 2.1 `record_admissions()` 返回真实新增数

用 SQLite 连接自带的变更计数器，在**同一个事务内**测量 `INSERT OR IGNORE` 的实际插入量：

```python
        with self._transaction():
            before = self.con.total_changes
            self.con.executemany("INSERT OR IGNORE INTO observation_admission …", prepared)
            inserted = self.con.total_changes - before
            self.con.executemany("INSERT INTO admission_current … ON CONFLICT … DO UPDATE …", prepared)
            self.con.executemany("DELETE FROM admission_workqueue WHERE observation_id=?", …)
        return int(inserted)
```

被忽略的行不计入 `total_changes`，因此这个差值就是"真正追加了几条历史"。

#### 2.2 `advance()` 用本批增量判断进展，并用可测量的积压证明已收敛

```python
        batch_admitted = apply_admissions(ledger, limit=limit)
        admitted += batch_admitted
        batch_work += batch_admitted
```

并把"是否收敛"从"猜"改成"量"：循环结束后统一计算账本侧积压（`pipeline_backlog()`：
待重判映射 / 待发布 / 待入 AI 队列 / 待判定），

- 积压为 0 且某批无工作 → `CONVERGED`；
- 预算（`max_batches`）或时限（新增 `deadline_seconds`）用完而积压 > 0 → `PARTIAL`，
  并**报出四项剩余计数**；
- 某批无工作但积压 > 0 → `STALLED`（说明选择工作的查询与消费工作的循环互相矛盾），
  **显式报告一次而不是空转**。

返回值新增 `status / stop_reason / elapsed_seconds / backlog`，日志在非收敛时打一行明确的告警。
"没有新数据就结束"与"没做完就说没做完"现在是两件可区分的事。

#### 2.3 一个共享谓词，避免计数与分页漂移

"这条观测还需要判定吗"这个条件原本只写在 `admission_pending()` 里。修复把这段 WHERE 提成模块常量
`_ADMISSION_PENDING_WHERE`，并新增只读计数 `admission_backlog()` 复用同一常量。
如果两处各写一份 SQL，用来判断"是否结束"的那个计数描述的可能就不是真正被处理的那批行。

### 3. 修复前后实测

#### 3.1 真实生产账本副本（8,358 条观测，本机 NVMe）

| 指标 | 修复前 | 修复后 |
| --- | --- | --- |
| 首次运行批次 | 60（跑满预算） | **22** |
| 首次运行耗时 | 16.2 s | 16.07 s |
| `converged` | **false** | **true**（`status=CONVERGED`） |
| 二次运行（幂等） | 1 批 / 0.11 s / true | 1 批 / 0.27 s / true |
| `admitted` 语义 | 提交行数 | 实际追加历史行数 |

耗时没有明显下降是**正确**的：真实工作量没有变，被消除的是第 23–60 批的空转。

#### 3.2 15,000 条真实规模负载副本 + 全新图谱（2 vCPU 开发机）

构造方式：以生产账本为模板，通过**真实代码路径** `record_observation()` 写入 6,642 条
`source_record_id = LOADTEST-*` 的克隆行，合计 15,000 条；`graph.db` 置空以强制完整物化。
克隆行只存在于隔离目录，**从未写入生产库，也从未进入任何简报**。

| 指标 | 修复前 | 修复后 |
| --- | --- | --- |
| 批次 | 60（跑满预算） | **39** |
| 墙钟 | 197.1 s | 195.7 s |
| `converged` | **false** | **true** |
| 图谱断言新建 | 20,329 | 20,329 |
| 二次运行 | — | 1 批 / 0.51 s / CONVERGED |

**关于"25 分钟"的诚实说明**：修复消除的是"跑满预算仍宣布未收敛"，它**不能**把 15,000 条观测的
真实处理成本降到零。真实成本主要是图谱物化（20,329 条断言）与逐条 Python 判定；在 2 vCPU 的服务器上
同等工作量约为开发机的数倍，这与"超过 25 分钟"的观察一致。修复后这类运行会**明确报告**自己跑完了
（`CONVERGED`）或还剩多少（`PARTIAL`），而不是在预算耗尽后仍不可判定。

#### 3.3 服务器隔离环境实测（同一台 2 vCPU / 3.7 GB 生产主机）

| 运行 | 代码 | 账本 | 批次 | 耗时 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 基线 | 已部署 `14eaf61` | 生产库副本（v2） | 22 | 2.23 s | `converged=true`、`admitted=0` |
| 候选 | `a6da0f4` + 修复 | 生产库副本（迁移到 v3） | 22 | 12.49 s | `CONVERGED`、`admitted=8358`、`backlog.total=0` |

12.49 s 里包含 v3 迁移与 8,358 条判定的首次补齐；这是**一次性成本**，之后每次运行 1 批。

### 4. 八条验收要求的逐条对照

| # | 要求 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | 无新数据时任务能够终止 | **PASS** | `test_an_idle_ledger_converges_in_one_batch`：1 批、`backlog.total=0`；生产副本二次运行 0.27 s |
| 2 | 重复执行不会无限重判 | **PASS** | `test_a_second_run_changes_nothing_and_says_so`：第二次 1 批、`admitted=0`、历史行数不变 |
| 3 | 新记录可以进入正确流程 | **PASS** | `test_a_run_that_admits_records_converges_instead_of_burning_the_budget`：3 条新记录，`admitted=3`，随后收敛 |
| 4 | 规则升级时仍可执行必要重判 | **PASS** | `test_a_real_rules_change_appends_history_and_keeps_the_earlier_judgement`：规则摘要变化 → 3 条新判定被追加 |
| 5 | 不覆盖不可变判断历史 | **PASS** | 同上 + 既有 `test_rejudgement_appends_history_instead_of_overwriting_it`；`observation_admission` 上的 UPDATE/DELETE 触发器仍在 |
| 6 | 不依赖人工绕过 | **PASS** | 无新增手工命令；`advance()` 与 `radar advance` 的调用方式不变 |
| 7 | 明确的超时 / 失败 / 日志语义 | **PASS** | `deadline_seconds`（`test_a_deadline_stops_the_call_with_its_own_reason`）、`max_batches` 用尽 → `PARTIAL` 带剩余计数、非收敛时打一行告警 |
| 8 | 隔离的真实规模库副本上通过测试 | **PASS** | §3.1 / §3.2 / §3.3 全部在隔离副本上完成；生产库未被写入 |

补充：**没有为了让任务快一点结束而跳过数据。** `PARTIAL` 状态下未处理的行仍然是 pending，
下一次 `advance()` 会继续；`test_an_exhausted_budget_is_reported_and_the_next_call_finishes_the_work`
证明了"预算不足 → 报剩余 → 下一次补齐 → 最终 5/5 条都有判定"。

---

## P0-02：健康状态错误显示 OK

### 1. 根因（不是"检查缺失"，而是"检查没有参与判定"）

`ledger.consistency_check()` 早就计算了 `watermark_in_future`（FIRST PRINCIPLES-001 加的），
`source_status()` 也早就算出了每个来源的 `FAILED / DEGRADED`。问题出在
`health.system_status()` 的顶层判定完全不看它们：

```python
# 修复前 (medradar/radar/health.py)
    if degraded:            overall = "degraded"
    elif never:             overall = "warming_up"
    elif blocking and len(blocking) == len(sources): overall = "blocked"
    else:                   overall = "ok"        # ← 其余一律 ok
    …
    payload = {… "consistency": ledger.consistency_check() …}   # ← 只被塞进 payload，不参与判定
```

于是：**顶层 `state` 与一致性报告可以是矛盾的**——报告说"水位线在未来"、`radar verify` 退出码 2，
而 `/api/radar/health` 的 `state` 仍是 `ok`。此外它还有三个盲区：

1. 不区分来源的重要性——一个核心通道长期失败与一个边缘来源失败同权；
2. 不检查调度的**心跳**——调度器停摆时只要 `last_checked_at` 非空就仍是 ok；
3. 只有 `ok/degraded/warming_up/blocked` 四个小写标签，没有 UNHEALTHY，也没有"证据不足"这一档。

### 2. 修复：四态判定 + 六项可测检查

| 判定 | 含义 | 触发条件（任一） |
| --- | --- | --- |
| `HEALTHY` | 关键能力正常 | 所有检查 PASS（或仅有 MINOR 级提示） |
| `DEGRADED` | 部分能力异常，仍可有限服务 | 非关键来源失败 / 未跑；非关键来源水位线非法；单次核心失败 |
| `UNHEALTHY` | 关键能力失效 | 库不可写；结构性完整性问题；**核心来源连续失败或长期未被检查**；**核心来源水位线非法**；调度器心跳超时 |
| `UNKNOWN` | 证据不足 | 从未有过成功检查；账本为空 |

六项检查（每项都带 `status / severity / detail / observed`）：

| 检查 | 回答的问题 | 失败时的严重度 |
| --- | --- | --- |
| `ledger_writable` | 库还能不能写入（`BEGIN IMMEDIATE` + `ROLLBACK` 实测） | CRITICAL |
| `ledger_integrity` | 历史是否自相矛盾（孤儿版本 / 断链 / `first_observed_at` 漂移） | CRITICAL |
| `watermark_legal` | 水位线是否合法、是否有成功运行背书 | 命中核心来源 CRITICAL，否则 MAJOR |
| `critical_sources` | 产品离不开的来源是否在被采集（失败、从未检查、超过 3× cadence 未检查） | CRITICAL |
| `scheduler_heartbeat` | 调度器还活着吗（`last_cycle.finished_at` vs `max(30 min, 3×最小 cadence)`） | CRITICAL |
| `acquisition_progress` | 采集是否在推进 | **MINOR，只提示不降级** |

关键设计取舍：

- **核心来源是显式清单**（`V1_CRITICAL_SOURCES`：`openfda_recall`、`openfda_device`、`pubmed`、
  `crossref`）。未列入的来源仍按 MAJOR 计入，所以新增来源不会悄悄变成低严重度。
- **"来源没有新记录"不判为故障。** 来源安静超过 12 个自身 cadence 只会触发 MINOR 提示并点名该来源，
  不改变顶层判定。安静与坏掉必须可区分，否则告警会被训练成噪声。
- **"从未检查过"是 UNKNOWN 而不是 FAIL。** 第一天部署就报 UNHEALTHY 是假警报。
- **只读连接不伪装成可写。** API 进程按设计以只读打开账本，因此 `ledger_writable` 在 API 侧如实返回
  `UNKNOWN`；写入能力由 `radar status`（读写打开）实测。库真的不可写时，写进程会停止，进而
  `scheduler_heartbeat` 超时 → UNHEALTHY，这条因果链是闭合的。

### 3. 证明"重要来源真的故障时不再显示一切正常"

`tests/test_radar_health_verdict.py`，12 项，全部通过（本机与服务器隔离环境分别跑过）：

| 测试 | 断言 |
| --- | --- |
| `test_a_core_source_that_keeps_failing_is_never_reported_healthy` | `pubmed` 连续 3 次失败 → `UNHEALTHY`，`critical_sources=FAIL/CRITICAL`，并点名 pubmed |
| `test_one_failed_core_check_degrades_even_before_the_third_failure` | 单次失败 → `DEGRADED`（不是 HEALTHY） |
| `test_a_core_source_that_is_silently_not_checked_is_unhealthy` | 心跳正常但核心来源 7 天未被检查 → `UNHEALTHY` |
| `test_a_future_watermark_on_a_core_source_is_not_healthy` | Crossref 水位线 `2027-02` → `UNHEALTHY`，且 `consistency.ok=false` 与判定一致 |
| `test_a_future_watermark_on_a_peripheral_source_degrades_only` | 边缘来源同类问题 → `DEGRADED`（分级确实有区别） |
| `test_a_stalled_scheduler_is_unhealthy` | 心跳停在 11-01 → `UNHEALTHY` |
| `test_a_broken_version_chain_is_unhealthy` | 断链 → `UNHEALTHY` |
| `test_no_new_records_is_not_a_fault` | 所有来源 40 天无新增但持续成功 → **仍 `HEALTHY`**，仅 `acquisition_progress` MINOR 提示 |
| `test_a_quiet_but_working_system_is_healthy` | 正常系统 → `HEALTHY`，`legacy_state=ok` |
| `test_an_empty_deployment_is_unknown_rather_than_healthy` | 空部署 → `UNKNOWN`（不是 HEALTHY，也不是 UNHEALTHY） |
| `test_a_read_only_connection_reports_the_probe_as_unknown_not_failed` | 只读连接 → 该项 UNKNOWN，顶层仍 HEALTHY |
| `test_the_critical_source_list_names_the_v1_dependencies` | 核心清单包含四个 V1 依赖 |

真实生产账本副本上的实测输出（服务器隔离环境，候选代码）：

```json
{"state": "HEALTHY", "legacy_state": "ok",
 "reasons": [{"id": "ledger_writable", "status": "UNKNOWN", "severity": "CRITICAL"}]}
```

——当前系统确实是健康的；唯一无法回答的是写入能力（只读连接）。这比原来的"永远 ok"诚实。

### 4. 向后兼容

`state` 改用新词表（`HEALTHY/DEGRADED/UNHEALTHY/UNKNOWN`），同时保留 `legacy_state`
（`ok/degraded/blocked/warming_up`）。已确认雷达前端只判断 `available` 与 `access_state`，
不按 `state` 字符串分支；`/health` 的未配置分支（`state=not_configured`）未被改动，
对应测试 `test_health_reports_not_configured_rather_than_green` 仍通过。

---

## 第三个修复：测试套件的时区缺陷（不修则无法作为验收门）

`tests/test_radar_watermark.py::test_a_future_watermark_does_not_stop_discovery` 在**未修改的 `v1/001`**
上就失败：

```
assert all(value == today for value in adapter.seen_watermarks)
E  AssertionError: ['2026-11-18', '2026-11-18']
```

原因：产品的水位线钳制以 **UTC** 为"今天"（`usable_incremental_watermark(..., now=utc_now().date())`），
测试却用**本地日期** `date.today()`。在 UTC+8 主机上，本地日 00:00–08:00 之间两者相差一天，
测试每天有 8 小时必然变红。

修复：测试改用与产品同一个时钟（`datetime.now(timezone.utc).date()`），并写明原因。
这不是"改测试让它绿"——是让测试与被测语义对齐；产品侧行为未变。

---

## 明确不做的事（以及为什么）

| 议题 | 决定 | 理由 |
| --- | --- | --- |
| 增加 `month` 精度类 | **不在本轮修** | `normalize_moment()` 把 `YYYY` 与 `YYYY-MM` 合并为 `year`（`records.py:319-320`），适配器也显式返回 `"year"`（`pubmed.py:322`、`crossref.py:228`）。新增一类精度会改变已存库中既有取值的语义，属于需要迁移决策的产品变更，不是运行缺陷。本轮在 `BRIEF_001_INDEPENDENT_REVIEW.md` §4 给出精确补丁方案，并在候选简报中**不选入任何月精度记录**，确保不重复该错误。 |
| 提高 `max_batches` 默认值 | 不做 | 60 批在 15,000 条规模下足够（实测 39 批收敛）。真正的缺陷是"跑满预算也不说清楚"，已由 `PARTIAL + backlog` 修复。调大默认值只会掩盖问题。 |
| 让 API 进程写库以测可写性 | 不做 | API 设计为只读打开是正确的。写入能力由写进程（`radar status` / 调度器）承担，见 P0-02 §2。 |
| 新增告警通道（邮件 / IM） | 不做 | 属于四周试验的运营配置，不在"关闭运行缺陷"范围。现有可观察面（单元状态、`/healthz`、`radar status`、journal）已足以人工值守。 |

---

## 全量回归

| 范围 | 结果 |
| --- | --- |
| `pytest tests`（本机，候选分支） | **1,702 项收集，0 失败，4 跳过**，退出码 0 |
| 雷达专项 8 个文件（本机） | 全部通过 |
| 雷达专项 8 个文件（服务器隔离 venv，候选代码） | 全部通过 |
| 新增回归测试 | 9（P0-01）+ 12（P0-02）= 21 项，全部通过 |

唯一一个在修复过程中被改动的既有测试是 `test_radar_watermark.py`（时区），理由是它在**未修改代码**
上同样失败，属于测试自身缺陷。
