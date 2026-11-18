# FIRST PRINCIPLES-001 / 第六阶段：持续情报能力验证

- 验证时间：2026-11-18
- 真实数据源可用性：PubMed / Crossref / openFDA **均可直连**（本轮实测 HTTP 200）
- 生产部署：**不可访问**（无凭据、无 SSH），因此"生产环境的持续采集"标记为 **NOT VERIFIED**

## 0. 结论摘要

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| 新记录能被持续发现（机制） | 机制正确，但 Crossref 通道此前**实际空转** | 合成实验 + 真实水位线复现 |
| 历史漏采能否重新捕获 | **不具备** | 无回填路径；8,588/8,593 标记为 INITIAL_DISCOVERY |
| 来源更新时间水位线正确 | 修复前**错误**，本轮修复并验证 | `2027-02` → `2026-11-16` |
| 同一记录更新后正确处理 | 正确 | 合成：版本 2 + `changed_fields=["title"]` |
| 重复记录归并 | 部分（展示层归并，存储层不归并） | 合成：同 DOI 两个记录 id → 2 条观测 |
| 首次发现 vs 实际公开 | 字段齐全，但**产品未正确利用** | `first_observed_at` 与 `published_at` 均有值；但 99.94% 是首次导入 |
| 调度器失败恢复 | 正确 | 失败不推进水位线；`consecutive_failures` 累加；中断可续跑 |
| 长期沉默是否告警 | **不会** | 健康检查不包含"水位线停滞"或"长时间无新增" |

## 1. 真实增量采集测试：能不能做（以及为什么没做）

本轮**没有**执行长时间的真实增量采集，原因与替代证据如下：

| 条件 | 状态 |
| --- | --- |
| 数据源直连 | 可用（本轮已用 PubMed esearch、Crossref works、openFDA recall 实测） |
| 有一个可写的真实账本 | 有，但它是从生产复制的快照，**不是生产库**；向它写入会污染唯一的研究副本 |
| 生产环境访问 | 无 |
| 时间预算 | 增量采集若要有意义，需要 ≥ 24 小时、跨多个 cadence（PubMed 6h、Crossref 12h） |

因此本轮采取三条替代路径，并明确它们**不能**证明"真实新情报被发现"：

1. 复现真实水位线缺陷并修复（第 2 节）；
2. 在隔离临时库中验证增量的全部机制（第 3 节）；
3. 用真实公开源核对"如果修复了，能不能取到之前取不到的东西"（第 4 节）。

## 2. 遗留问题一：Crossref 未来水位线（已修复并验证）

### 2.1 复现

```
stored crossref watermark : 2027-02
BEFORE fix  from-created-date: 2018-01-01
AFTER  fix  from-created-date: 2026-11-16   (clamped_from = 2027-02)
```

注意实际机制比 REFOUNDATION-004 审计里写的更糟：审计认为"未来水位线导致取不到记录"，
真实情况是 **月精度水位线使 `date.fromisoformat` 抛异常，适配器回退到 `EARLIEST=2018-01-01`**，
于是每次运行都在近 9 年语料上做相关性排序取前 3 页；同时 `_max_moment` 取字典序最大值，
`2027-02` 永远不会被 `2026-11-xx` 覆盖，所以系统**无法自愈**。

### 2.2 修复（最小改动）

- `medradar/radar/adapter.py`：新增 `usable_incremental_watermark()`；
  `run_source()` 用它生成传给适配器的下界；运行结果新增 `watermark_adjustment`。
- `medradar/radar/ledger.py`：`consistency_check()` 新增 `watermark_in_future` 问题项。
- `tests/test_radar_watermark.py`：4 个回归用例。
- **不改写存储状态**：那是证据，不是缓存。

### 2.3 验证

| 检查 | 结果 |
| --- | --- |
| 新的 4 个测试 | 通过 |
| 既有雷达测试（7 个文件） | 通过 |
| 全量测试套件 | 通过（无失败；`pytest -q`，见 `_fp001/full_suite.txt`） |
| 真实账本上的窗口变化 | `2018-01-01` → `2026-11-16`（同日） |

## 3. 遗留问题二：Dräger 日期缺失（结论与 REFOUNDATION-004 不同）

REFOUNDATION-004 的审计（D14）写："all 31 draeger_official observations have `published_at =
`event_at = null` and precision unknown; the adapter scrapes titles without the article date."

**本轮实测的更正**：

| 检查 | 结果 |
| --- | --- |
| 31 条记录的 `source_updated_at` | **全部有值**，精度 `datetime`（来自 sitemap `<lastmod>`） |
| 实时抓取 sitemap | HTTP 200，5,002 字节，**31 个 `<url>`，31 个 `<lastmod>`** |
| 适配器是否丢弃日期 | 否：`_record_from_entry()` 把 lastmod 存入 `source_updated_at` |
| UI/查询是否使用 `source_updated_at` | **否**：时间视图只用 `published_at`/`event_at` |

所以真正的问题不是"适配器没有解析日期"，而是两件不同的事：

1. **产品的时间语义只认"公开时间"，不认"来源更新时间"**，于是这 31 条永远无法进入任何时间视图；
2. **这个来源采的是 Dräger Safety（工业安全）的业务板块，不是医疗/监护板块**。
   31 条内容为：海滩清理、Women at Dräger、CleanTech、矿山安全、气体检测 INARA、呼吸器 LAR 8000、
   "Be creative"、"Almost all that glitters is gold"；只有 2 条与 connected acute care 有关。

这意味着 D14 的修复方向（"给适配器加日期解析"）**会做无用功**，正确的动作是换来源。
这也是本轮"不要相信历史结论"的一个具体收获。

## 4. 隔离环境中的增量机制验证（合成数据，不冒充真实情报）

隔离临时库，三轮合成采集：

| 轮次 | 输入 | 结果 |
| --- | --- | --- |
| 1 | 2 条新记录，watermark=2026-11-02 | `NEW_RECORDS`，new=2，watermark 推进到 2026-11-02 |
| 2 | 1 条未变、1 条内容更新、1 条新增 | new=1，**updated=1**，watermark 推进到 2026-11-03；
  被更新记录的 `version_count=2`，`observation_change.changed_fields=["title"]` |
| 3 | 适配器抛异常 | `FETCH_FAILED`，**watermark 仍为 2026-11-03**，`consecutive_failures=1` |

另外两项：

- `discovery_phase`：第 1 轮的两条是 `INITIAL_DISCOVERY`，第 2 轮新增的是 `INCREMENTAL_DISCOVERY`。
- 去重：**同一 DOI、两个不同 `source_record_id` → 2 条 observation**（两条都 NEW）。
  存储身份是 `(source, source_record_id)`；展示层的 `work_key` 会归并显示，但账本计数会翻倍。
  这是一个**已知的行为选择**（跨源同 DOI 被视为两条独立观测，由图谱合并），
  但同一来源用不同 id 重复投递时，它会产生真实的重复。

**合成数据不被当作真实发现**：本轮没有把任何合成记录写入真实账本或候选简报。

## 5. 调度与失败恢复（代码 + 测试证据）

| 机制 | 实现 | 验证 |
| --- | --- | --- |
| 失败不推进水位线 | `run_source` 只合并"完成且无失败"的 scope watermark | 合成第 3 轮 + 既有测试 |
| 中断可续跑 | `sync_run` + `sync_checkpoint`；中断状态保留在历史里 | 既有 `test_radar_pipeline` |
| 逐 scope 隔离 | 一个 scope 失败不阻塞其它 scope | 既有测试 |
| 单写者锁 | 复用 `data_pipeline.lock` | 既有测试 |
| 连续失败可见 | `consecutive_failures` → `FAILED`（≥3）/`DEGRADED` | `health.sources()` |
| 发现延迟 | `detection_latency()` 已实现 | `health.py` |

## 6. 长期沉默检测：**不具备**（本轮未修）

- `health.py` 会报告每个来源的 `status`、`last_checked_at`、`last_success_check_at`、`watermark`、
  `consecutive_failures`、`next_due_at`、`discovery_phases`——**观测面是完整的**。
- 但**没有任何判据把"水位线连续 N 个 cadence 未推进"或"连续 N 天无新增记录"变成告警**。
  这就是 Crossref 以 2027-02 空转多日而状态仍为 `OK` 的原因。
- 本轮的修复只覆盖"水位线在**未来**"这一种不可能状态（`watermark_in_future`）；
  "水位线停滞"仍然不可见。这是一个已知的、明确记录下来的剩余缺口。

建议（下一阶段，不属本轮）：在 `health.sources()` 增加 `watermark_stagnant`，判据为
`now - max(last_watermark_advance_at) > 3 × cadence`，并把 `last_watermark_advance_at` 记入 `source_state`。
这需要一次 schema 变更，因此本轮没有做。

## 7. 真实增量采集：NOT VERIFIED

明确列出本轮**没有**验证的东西，避免被误读为"已验证"：

- 生产环境 24 小时内的真实新增（PubMed 6h / Crossref 12h 的 cadence 是否真的在跑）；
- 修复后生产 Crossref 通道是否真的取到了新记录（需要部署 + 24h）；
- 来源更新（同一 URL 内容变化）在真实源上的表现；
- 备份/恢复演练与真实磁盘水位；
- 调度器在真实中断（进程被杀）后的行为（只有单测覆盖）。

**结论**：机制层面（增量、版本、失败、水位线）**已在本轮通过隔离实验和全量测试验证**；
真实世界的持续发现**未验证**，且有一个已知的本轮修复（R4）需要部署后才能观察到效果。
