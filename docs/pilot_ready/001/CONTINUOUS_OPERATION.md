# PILOT-READY-001 / 阶段三：服务器上的真实持续采集验证

- 验证对象：`https://silly-facing-deferred-radar.trycloudflare.com` 背后的 `medradar-radar-scheduler`
  与 `data/radar/radar.db`（服务器实测，非本地）
- 数据截取时间：2026-11-19 01:47–02:20 CST（= 2026-11-18 17:47–18:20 UTC）
- 方法：以只读方式在线备份生产库到 `/tmp`，离线用 `sqlite3`/Python 读取；对公开来源直接发起
  受控的只读 API 查询以核对；**未向生产库写入任何行**。

> 先说结论：调度器确实在跑，也确实在按 cadence 采集，并且在 2026-11-17 首次导入之后
> **真实新增了 131 条记录**。但它跑的是 `14eaf61`，缺少三层修复，且**没有召回通道**——
> 也就是说，对"ICU / 床旁监护设备的安全事件"这一最核心的承诺，线上目前**一条都采不到**。

---

## 0. 一句话回答

| 问题 | 答案 |
| --- | --- |
| 最近一次真正成功的采集 | 2026-11-18T13:04:34Z（Philips / Dräger 官网）；核心通道 Crossref / PubMed 为 12:24Z |
| 最近一次真正新增记录 | 2026-11-18T12:24:24Z（Crossref） |
| 是否有"发现了但没入库" | 无证据（0 次失败、0 个延迟 scope）；但**未做网络层抓包**，故标记 NOT VERIFIED |
| 是否有"入库了但分类错" | 有：8,358 条中 7,166 条（85.7%）为 HIGH_RELEVANCE，其中 6,938 条来自单一通道；另有 15 条标题残留 JATS 标记 |
| 是否"调度器正常但水位线不推进" | 当前不成立：水位线在 11-17→11-18 两次推进；但部署代码**缺少**水位线不可用检测与钳制 |
| 连续多日无新增能否区分"正常安静"与"故障" | **修复前不能，修复后能**（见 §6） |
| 历史回填是否会被当作新情报 | 不会：`discovery_phase` / `observation_origin` / `backfill_reason` 三重约束，实测 8,227/8,358 标记为 INITIAL_DISCOVERY |
| 数据更新与安全事件状态变化能否追踪 | 结构齐备，但**生产上从未发生过一次** UPDATE/REMOVE（8,358 条全是 NEW） |

---

## 1. 最近一次真正成功的采集发生在什么时候？

```
$ SELECT source_id, cadence_hours, last_success_check_at, last_checked_at FROM source_state
openfda_device   24h  2026-11-18T00:17:56Z  2026-11-18T00:17:56Z
pubmed            6h  2026-11-18T12:23:57Z  2026-11-18T12:23:57Z
crossref         12h  2026-11-18T12:24:29Z  2026-11-18T12:24:29Z
philips_official 12h  2026-11-18T13:04:34Z  2026-11-18T13:04:34Z
draeger_official 12h  2026-11-18T13:04:34Z  2026-11-18T13:04:34Z
gehealthcare     24h  (null)                (null)                 ← access_state=BLOCKED，enabled=0
```

最近一次成功是 **2026-11-18T13:04:34Z（本地 21:04）**，距采集时刻约 5.3 小时——在一个 12 小时
cadence 之内，**不是故障**。

cadence 遵守情况（`sync_run` 共 23 次，**全部 status=OK，0 次失败**）：

```
crossref       4 次   2026-11-17T00:14:39Z .. 2026-11-18T12:23:57Z   （跨度 36.2 h，12 h cadence → 期望 3，实到 4）
pubmed         7 次   2026-11-17T00:14:22Z .. 2026-11-18T12:23:52Z   （36.2 h，6 h cadence → 期望 6，实到 7）
openfda_device 2 次   2026-11-17T00:13:34Z .. 2026-11-18T00:17:55Z   （24 h cadence → 期望 2，实到 2）
philips        5 次 / draeger 5 次（12 h cadence）
```

调度器自身的心跳：`runtime_state.cycle_counter = 517`，`last_cycle.status = IDLE`，
`finished_at = 2026-11-18T17:44:37Z`，每 300 秒一跳，无重启（`NRestarts=0`）。

调度日志最近 6 个周期全部是：

```
[scheduler] openfda_device is not due yet
[scheduler] pubmed is not due yet
[scheduler] crossref is not due yet
[scheduler] philips_official is not due yet
[scheduler] draeger_official is not due yet
[scheduler] gehealthcare_official is not due yet
[scheduler] cycle 303: IDLE new=0 updated=0 ai=None
```

**这 6 行不是"空转"**：所有来源的 `last_checked_at + cadence` 都还没到，调度器正确地什么都没做，
`last_cycle.status = IDLE` 也如实写成了 IDLE 而不是 OK。这一点很重要——如果它把 IDLE 写成 OK，
"没到时间"和"采集成功但没新东西"就会被混为一谈。它没有。

---

## 2. 最近一次真正新增记录发生在什么时候？

按 `discovery_phase` 拆分 8,358 条观测：

| phase | 数量 | 时间范围 |
| --- | --- | --- |
| `INITIAL_DISCOVERY`（首次导入的历史存量） | 8,227 | 2026-11-17T00:13:36Z .. 00:39:37Z |
| `INCREMENTAL_DISCOVERY`（首次导入之后真正新发现） | **131** | 2026-11-17T06:17:53Z .. **2026-11-18T12:24:24Z** |

最近一条是 **2026-11-18T12:24:24Z（本地 20:24）** 由 Crossref 发现。

131 条增量按来源：Crossref 117、PubMed 12、openFDA 2。

增量记录的"新鲜度"（`first_observed_at - published_at`）：

| 差值 | 条数 |
| --- | --- |
| ≤ 0 天（当天公开当天发现） | 20 |
| 1–7 天 | 50 |
| 8–30 天 | 5 |
| 31–365 天 | 7 |
| > 365 天 | 2 |
| 无公开日期（unknown） | 47 |

在有日期的 84 条里，**70 条（83%）在 7 天内被发现**。这说明增量通道确实在工作，不是空转。

一个必须如实写出的观察：增量里也包含 `published_at = 2021-10-25` 的老文章。这是
"今天才被 MedRadar 看见"，不是"今天才公开"。账本用 `discovery_phase` + `first_observed_at` 把
两者分开，产品视图也分开——这是正确的设计，但它意味着**"本周新增 N 条"不能等同于"本周有 N 条新闻"**。

---

## 3. 是否存在"已经发现但未入库"的记录？

能查到的部分：**没有**。

- `source_failure` 表：0 行；
- `sync_run`：23 次全 OK，无 PARTIAL / INTERRUPTED；
- 没有被推迟的 scope（`deferred_update_sources: []`）；
- `processing_queue`：8,227 条 `SKIPPED`——这是 AI 队列被 `--no-ai` 显式关闭的结果，
  不是丢弃；观测本身已 `PUBLISHED`。

不能查到的部分（**NOT VERIFIED**）：网络层是否静默丢页、适配器是否在翻页上限处截断。
本轮没有抓包，也没有在服务器上重放一次完整抓取，因此不做断言。

一个**设计层面**的相关事实：REFOUNDATION-004 移除了适配器内的"入库前相关性闸门"，理由是
"被闸门拒掉的记录永远无法被后续规则重判"。因此账本现在**故意**保存了领域外记录
（例如 `Trade-off among Missed Alarms, False Alarms, and Fuel in Spacecraft Collision Avoidance`
被存进了账本）。这是"证据不删"的正确取舍，代价是精度必须由判定层承担——见下一节。

---

## 4. 是否存在"已入库但未正确分类"的记录？

**存在，而且这是当前最值得关注的数据质量问题。**

### 4.1 相关性分级在真实数据上几乎没有区分度

```
tier 分布（8,358 条）: HIGH_RELEVANCE 7,166 | LOW_RELEVANCE 680 | NEEDS_REVIEW 395 | IRRELEVANT 117
```

85.7% 的观测被判为 HIGH_RELEVANCE。按来源拆开后原因很清楚：

```
openfda_device → HIGH 6,938 / 6,938   （100%，因为查询本身就是按监护类 product code 取的）
crossref       → HIGH 207 / 1,112    （19%）
pubmed         → HIGH 16 / 272        （6%）
philips        → HIGH 3 / 5
draeger        → HIGH 2 / 31
```

**单一通道贡献了 97% 的 HIGH**。也就是说，`HIGH_RELEVANCE` 在聚合层面基本等价于
"这条来自 openFDA 器械通道"。这不是判定规则的错——openFDA 的查询条件已经替它做完了筛选——
而是说：**"多少条 HIGH"这个数字不能当作情报价值指标来读。**

### 4.2 领域外与格式异常的记录确实入库了

| 类型 | 实测 | 举例 |
| --- | --- | --- |
| 领域外（非医疗） | 账本内可见 | `Trade-off among Missed Alarms, False Alarms, and Fuel in Spacecraft Collision Avoidance`；`Pengembangan Sistem Monitoring … Tanah Longsor`（滑坡监测） |
| 标题残留 JATS/HTML 标记 | **15 条** | `Performance of Transcutaneous Pco <sub>2</sub> and Pulse Oximetry Moni…` |
| 标题含换行符 | **14 条** | `Multimodal Physiological and\n<scp>EEG</scp>\nResponses…` |

根因（可定位到行）：
- 标题未清洗：`medradar/radar/adapters/crossref.py:135` 用 `_first_text()` 取标题，而摘要走了
  `_strip_markup()`（第 137 行）。标题漏了同样的处理。
- 领域外记录入库：见 §3 的设计取舍，由判定层拦截；判定层确实把它们放进了 ARCHIVE/IRRELEVANT，
  但它们仍然出现在"账本全量"计数里。

这两项都不构成运行故障，但都会出现在读者眼前，属于**内容质量缺陷**，已在
`BRIEF_001_INDEPENDENT_REVIEW.md` §5 记录并给出精确补丁位置。

---

## 5. 是否存在"调度器运行正常、却没有实际推进水位线"的情况？

**当前不存在。** 水位线在本轮观察窗口内推进过：

| 来源 | 水位线 | 是否合法 |
| --- | --- | --- |
| openfda_device | `2026-11-09` | 合法（过去日期） |
| pubmed | `2026-11-18` | 合法（当天） |
| crossref | `2026-11-18` | 合法（当天） |
| philips_official | `2026-11-16T07:30:00+00:00` | 合法 |
| draeger_official | `2026-11-09T12:41:36+00:00` | 合法 |

### 5.1 Crossref 未来水位线：问题没有被"隐藏"，但它也**没有被修复**

必须区分三件事：

1. **当前库里没有非法水位线。** 生产库 `created_at = 2026-11-17T00:13:33Z`，是 FIRST PRINCIPLES-001
   讨论之后新建的库；其中的 crossref 水位线是 `2026-11-18`，不是 `2027-02`。
2. **部署代码不具备检测能力。** `14eaf61` 的 `consistency_check()` 只有
   `watermark_without_successful_run`，**没有** `watermark_in_future`：
   ```
   $ git show 14eaf61:medradar/radar/ledger.py | grep watermark
       problems.append({"kind": "watermark_without_successful_run", ...})
   （无 watermark_in_future）
   ```
3. **部署代码也不具备钳制能力。** `usable_incremental_watermark()` 是 `6f4d079`（FIRST
   PRINCIPLES-001）引入的，`14eaf61` 早于它。

结论：**未来水位线目前不是"被隐藏"，而是"在当前库里不存在"。** 但如果它再次出现，服务器上
跑的这版代码既不会修复它、也不会报告它——上一轮那个"检查成功、实际空转"的失效模式**仍然可以在
线上重演**。这正是候选版本必须部署的理由之一。

### 5.2 现在有没有"看起来在跑、其实没推进"的迹象？

没有。三条独立证据同时成立：
- 增量记录在 11-17 与 11-18 都有（131 条）；
- `last_observed_update_at` 与 `last_success_check_at` 在核心通道上同刻刷新；
- `last_cycle.status` 明确区分 `IDLE`（未到时间）与 `OK`（已采集）。

但要注意一个**语义陷阱**：`IDLE` 与 "OK 但 0 新增" 在日志里都表现为 `new=0 updated=0`。
前者在 `[scheduler] X is not due yet` 行里有说明，后者靠 `cycle N: OK new=0` 的 `OK` 区分。
如果只看后半行，两者确实容易混。这是下一节要解决的问题。

---

## 6. 如果连续几天没有新增，能否判断是"正常无更新"还是"系统故障"？

**修复前：不能。修复后：能。**

修复前（服务器现状）：`system_status()` 只看 `consecutive_failures` 与 `last_checked_at` 是否为空。
一个来源连续 5 天成功返回"没有新东西"，与一个来源连续 5 天根本没被调度，在顶层状态上**都可能是 ok**。
此外 `/usr/local/bin/medradar-health` 只探 8787（旧工作台），根本不看雷达与调度器。

修复后（候选版本），三条互补的证据把两者分开：

| 判据 | 正常安静 | 系统故障 |
| --- | --- | --- |
| `critical_sources` | PASS（检查间隔在 cadence 内） | **FAIL / CRITICAL**：连续失败 ≥3、从未检查、或超过 3× cadence 未检查 |
| `scheduler_heartbeat` | PASS（心跳在 `max(30 min, 3×最小 cadence)` 内） | **FAIL / CRITICAL**：心跳超时 |
| `acquisition_progress` | WARN / MINOR，点名该来源，**不降级** | 不变（它不承担故障判定） |

阈值是显式的（`HEALTH_RULES`：`QUIET_INTERVALS_BEFORE_NOTE = 12`、`HEARTBEAT_INTERVALS = 3`、
`MIN_HEARTBEAT_SECONDS = 1800`），并且有测试固定：
`test_no_new_records_is_not_a_fault`（安静 40 天仍 HEALTHY）与
`test_a_core_source_that_is_silently_not_checked_is_unhealthy`（7 天未检查即 UNHEALTHY）。

**但必须说清楚：这套判定目前只存在于候选分支，服务器上还没有。** 见 `DEPLOYMENT_READINESS.md`。

---

## 7. 历史回填是否会被错误当作新情报？

**不会。** 三重机制，且都有生产数据佐证。

1. **`discovery_phase`**：8,227 条 = `INITIAL_DISCOVERY`（2026-11-17T00:13–00:39 一次性导入），
   131 条 = `INCREMENTAL_DISCOVERY`。产品视图把两者分开展示。
2. **`observation_origin = BACKFILLED` 必须带 `backfill_reason`**，否则
   `record_observation()` 直接抛 `ValueError`（`ledger.py` 内的显式校验）；
   `consistency_check` 还会把"有 BACKFILLED 但没有理由"报成 `backfill_without_reason`。
3. **简报渲染层**把"本周公开 / 本周更新 / 历史首次采集 / 日期不明"分成四个计数并且不合并。
   V1 简报里 14,771 条历史首次采集与 354 条本周公开是分开列的——这一点做对了。

因此"历史回填冒充新情报"在本轮数据上**没有发生**。风险不在机制，而在读者是否会忽略那个标签；
候选简报把它放在显眼位置（`PILOT_BRIEF_CANDIDATE.md` 的新颖度声明）。

---

## 8. 数据更新与安全事件状态变化能否被追踪？

**结构齐备，但生产上从未发生过一次真实更新。**

```
observation_version        8,358 行   （每条观测恰好 1 个版本）
observation_change         8,358 行   change_state 全部 = NEW
observation_status_history 8,358 行   status 全部 = ACTIVE
observation               8,358 行   current_change_state 全部 = NEW，observation_status 全部 = ACTIVE
sync_run  23 次                      全部 OK；0 次 UPDATED，0 次 REMOVED
```

也就是说：**"记录被更新"和"记录被撤下"这两条代码路径，在一个跑了两天的真实部署上，一次都没有
被真实事件触发过。** 它们在合成测试里是验证过的
（`CONTINUOUS_DISCOVERY.md` 记录了三轮合成实验：新增 / 更新 + `changed_fields=["title"]` / 失败不推进水位线），
但**生产环境覆盖率为零**。

对四周试验的含义：如果第一周就出现一次真实的"召回状态从 Ongoing 变成 Completed"，系统会写
第 2 个版本并标记 `changed_fields`——这是设计承诺，但目前只是**代码承诺**。
这一点在 `PILOT_OPERATIONS.md` 中列为试验期必须观察的头号未知。

---

## 9. 受控的真实公开来源增量验证（本轮实际做了什么）

允许的是"范围有限、频率受控"的真实来源验证，不允许向生产情报库写伪造记录。本轮执行的是
**只读**真实查询，未写入任何账本：

| 来源 | 查询 | 结果 |
| --- | --- | --- |
| openFDA device/recall | `event_date_posted:[2026-10-19 TO 2026-11-18]`，全量 | 167 行；其中属于监护类 product code 的仅 1 行（`LRP`，2026-11-02，Cardinal Health 含 BD Alaris 输液附件的套包），**不是监护仪** |
| openFDA device/recall | 逐个 `res_event_number` 核对 99908 / 99838 / 99549 / 99801 / 99617 | 5/5 存在，发布日期与字段与官方一致 |
| PubMed esummary | 17 个 PMID 一次性核验 | 17/17 存在，标题一致 |
| Crossref works | 4 个 DOI | 3 个存在；`10.29196/jubes.v4i4.6922` **404**（见评审文档） |
| Crossref works | 6 个 DOI 的全部日期字段 | `published-online` 与账本日期一致 |

这次验证同时回答了"窗口内有没有漏掉的监护召回"：**没有**。在 167 行里，唯一命中监护类
product code 的是一条输液附件套包，不属于床旁监护设备。V1 简报里"窗口内没有新公开的监护设备召回"
这句话，**独立复核成立**。

---

## 10. 结论与未验证项

**已验证（有实测证据）：**
- 调度器连续运行 2 天 23 小时，517 个周期，0 次重启，23 次来源检查全部成功；
- 采集按 cadence 执行，无迟到证据；
- 首次导入之后真实新增 131 条，最近一条在 2026-11-18T12:24:24Z；
- 水位线合法且在推进；
- 回填不会被当作新情报（三重机制 + 生产数据佐证）；
- 窗口内确实没有新的监护设备召回（独立 openFDA 全量查询确认）。

**未验证（明确标记，不含推测）：**
- 网络层是否静默丢弃过记录（NOT VERIFIED，未抓包）；
- "记录被更新/撤下"路径的生产覆盖率（结构性为零，无真实样本）；
- 部署代码是否会在下一次出现非法水位线时停滞（**会**——因为它既无检测也无钳制，这是代码事实，
  不是推测；只是当前没有触发条件）。

**最要紧的一句：** 服务器上的持续采集是真的，但它采集的**不是 V1 产品承诺的那个东西**。
召回通道（`openfda_recall`）在 `14eaf61` 里根本不存在，生产库里 0 条召回记录。
把 Nihon Kohden 中央护士站 null-pointer 召回、Philips Smart-hopping 导致 PIC iX 断连这两条
写进情报的，是本地 `v1/001` 分支上的代码，**不是线上正在跑的东西**。
