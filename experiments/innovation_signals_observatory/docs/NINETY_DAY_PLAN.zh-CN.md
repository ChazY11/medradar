# 90 天前瞻观察方案（设计，本轮不部署）

**日期**：2026-11-04（Asia/Shanghai）  
**状态**：设计 + 可重入单次采集命令已实现；**尚无任何持续运行的服务被部署**。  
**前置条件**：见 `PROTOCOL.md` §8。启动前必须逐条核实，不满足就先修链路。

---

## 1. 这一节要回答什么

90 天观察的目的**不是**「证明招聘能预测技术突破」，而是把本轮的单次快照 `T0`
变成一条可审计的时间序列，从而第一次有可能回答 Q3（能否区分一般招聘与值得调查的方向变化）。

如果 90 天后仍然只有 1 次快照，那么本轮的一切分类、关联都只是横截面描述，
这一点必须在报告里继续写明。

---

## 2. 观察对象与记录单位

* 观察对象：Medtronic（本轮唯一达到 `VERIFIED` 采集条件的企业）+ 其他企业一旦满足
  `PROTOCOL.md` §4 第一层标准后逐个加入。**不因为想凑满五家而降低标准。**
* 记录单位：`Company × Technology Track × Observation Time`，其中
  `Observation Time` = 每次采集的 `fetched_at`（不是岗位发布日期）。
* 每次采集写入**新的快照**，不覆盖旧快照；`first_seen_at` 写一次，永不覆盖。

---

## 3. 采集节奏（有意保守）

| 频率 | 动作 | 预计成本 |
|---|---|---|
| 每日 1 次 | Medtronic 全量岗位列表 + 岗位详情（增量：新增岗位取详情，已见岗位只取列表页做存在性检查） | ~50–100 次请求/天，10–20 分钟 |
| 每周 1 次 | 全量详情重取（用于发现描述修订） | ~1000 次请求，约 20 分钟 |
| 每月 1 次 | 校验：robots.txt 重取、平台指纹检查、身份稳定率、去重率、覆盖率 | 数分钟 |

**为什么不是每小时**：岗位发布不是高频事件；提高频率只会增加对来源的压力，
不会提高信息量。1 次/天足以把「首次观察时间」的误差控制在 24 小时内，
而这已经远小于任何有意义的技术方向变化的时间尺度。

---

## 4. 每次采集必须写入的字段（与 `medradar/recruitment/records.py` 一致）

来源侧：`posting_id`、`source_url`、`job_title`、`job_description`、`job_location`、
`source_posted_at` + `source_posted_quality` + `source_posted_raw`、`source_updated_at`（若有）。  
观察侧：`first_seen_at`（写一次）、`fetched_at`、`collection_status`、`content_sha256`、
`collector_version`、`schema_version`。  
归属侧：`company_key`（固定五家之一）、`legal_entity`（未知则 null）、
`entity_resolution_status` + `entity_resolution_note`。

**运行级**元数据：请求数、robots 判定原文、被截断标记、失败明细、平台结构指纹
（用于发现「网站改版」而不是「招聘变化」）。

---

## 5. 每次采集必须计算的差分（否则时间序列没有意义）

对同一 `(company_key, posting_id)`：

| 状态 | 判定 | 解释边界 |
|---|---|---|
| `NEW_POSTING` | 上次快照没有，本次有 | 只是「我们第一次看见」，不等于「企业今天开始招」 |
| `UNCHANGED` | 内容哈希不变 | 仍存在，无修订 |
| `REVISION` | 同一身份，`content_sha256` 变化 | 描述被修改；**不是**新岗位 |
| `REMOVED` | 上次有，本次没有 | 岗位下架/关闭/网站迁移；**不等于**招到人 |
| `REAPPEARED` | 曾经 REMOVED，又出现 | 重新发布；不等于新增需求 |
| `MULTI_CITY_COPY` | 同 requisition、不同地点/不同 posting id | 同一需求的多地点发布，计数时去重 |
| `PLATFORM_CHANGE` | 列表结构/URL 方案整体变化 | 采集伪影，**不得**解释为招聘策略变化 |

差分结果写入 append-only 的变更记录，**不做就地更新**。

---

## 6. 每周汇总（机器产出 + 人读摘要）

每周固定输出：

1. 每家企业：`NEW_POSTING` / `REVISION` / `REMOVED` 计数，以及**独立岗位 ID 数**（去重后）。
2. 每个 track：新增岗位数、涉及职能类别、**该 track 是否出现「此前没有的职能组合」**
   （例如首次出现「机器人运动控制 + 临床研发」同时招聘）。
3. 数据缺口：本周采集失败次数、被截断标记、robots 变化、覆盖率异常。
4. 反证栏：本周观察是否与既有独立证据（监管/试验/论文）冲突。
5. `UNCLASSIFIED` 率与该周分类器版本。

**周报不得**写「企业正在转向 X」。允许写「本周在 track Y 观察到 N 个新岗位，
其中 M 个包含可逐字定位的能力短语，建议人工复核」。

---

## 7. 每月信号质量评估（决定要不要继续）

月结时回答四个可失败的问题：

1. **身份稳定性**：同一岗位在连续两次采集中的身份键一致率（目标 ≥ 0.98；低于则修身份规则）。
2. **去重有效性**：`MULTI_CITY_COPY` 与实际新增岗位的比例是否稳定（不稳定则去重规则有偏）。
3. **分类可靠性**：`UNCLASSIFIED` 率、规则臂与模型臂的一致率、**负对照误报率**（必须报）。
4. **数据可得性漂移**：字段可获得率是否下降（日期/描述/ID），是否出现平台改版。

**停止条件（写死，避免「再观察一下」）**：
* 连续 4 周覆盖率下降 >30%，且无法归因于真实岗位减少；
* 身份稳定率 <0.95 且修不好；
* robots 变更为禁止，或来源要求停止自动访问；
* 采集失败率 >20% 且持续两周。

---

## 8. 调度配置样例（本轮**不启用**）

### 8.1 任务清单（与实现一致）

```json
{
  "schema": "recruitment-observation-plan-v1",
  "companies": ["medtronic"],
  "cadence": {
    "daily_list":   {"cron_local": "10 3 * * *",  "mode": "listing_exists_check"},
    "weekly_full":  {"cron_local": "40 3 * * 1",  "mode": "full_detail_refresh"},
    "monthly_check":{"cron_local": "50 3 1 * *",  "mode": "source_integrity_check"}
  },
  "budgets": {"max_requests_per_run": 1200, "max_postings_per_run": 1200, "min_interval_s": 0.8},
  "outputs": {
    "snapshot_dir": "data/recruitment/snapshots",
    "change_log": "data/recruitment/changes.jsonl",
    "weekly_summary_dir": "reports/recruitment/weekly",
    "monthly_quality_dir": "reports/recruitment/monthly"
  },
  "guards": {
    "refuse_if_robots_unreadable": true,
    "refuse_if_robots_disallows": true,
    "record_platform_fingerprint": true,
    "single_writer": true
  }
}
```

### 8.2 Windows（本机实测环境）——一次性任务，不是常驻进程

```powershell
# 每日 03:10 采集一次（Task Scheduler，非服务、非后台常驻）
$action  = New-ScheduledTaskAction -Execute "python" `
  -Argument "scripts/collect_recruitment.py --company medtronic --limit 1200 --min-interval 0.8 --out data/recruitment/snapshots" `
  -WorkingDirectory "D:\DEPPSKK\worktrees\phase4"
$trigger = New-ScheduledTaskTrigger -Daily -At 03:10
Register-ScheduledTask -TaskName "MedRadar-Recruitment-Daily" -Action $action -Trigger $trigger `
  -Description "MedRadar Phase4 recruitment observation (single bounded run)"
```

### 8.3 Linux（若将来搬到服务器）

```ini
# /etc/systemd/system/medradar-recruitment.service
[Service]
Type=oneshot
WorkingDirectory=/srv/medradar
ExecStart=/usr/bin/python3 scripts/collect_recruitment.py --company medtronic \
          --limit 1200 --min-interval 0.8 --out /srv/medradar/data/recruitment/snapshots
```

```ini
# /etc/systemd/system/medradar-recruitment.timer
[Timer]
OnCalendar=*-*-* 03:10:00
Persistent=true
```

> 与既有的 `deploy/medradar-observatory.{service,timer}` 保持同一形态：**一次性任务 + 定时器**，
> 不使用常驻 daemon。理由：一次采集失败不应该让整个观察停下来，
> 而常驻进程会掩盖失败（进程活着 ≠ 采集成功）。

---

## 9. 启动条件（必须逐条打勾才允许启用定时任务）

- [ ] `python -m pytest tests/test_recruitment_records.py -q` 全绿；
- [ ] 同一天内**连续两次**全量采集，身份稳定率 ≥0.98，第二次采集的 `first_seen_at` 未被覆盖；
- [ ] 人为断开网络一次，确认采集失败被记录为 `FETCH_FAILED`/`DETAIL_FAILED` 而不是 0 条；
- [ ] 人为把 robots.txt 换成 `Disallow: /`，确认采集器**拒绝运行**并留下 `BLOCKED` 记录；
- [ ] 分类器的 `UNCLASSIFIED` 率与负对照误报率已知；
- [ ] 有人工复核入口（本轮的 `docs/EVIDENCE_REPORT.zh-CN.md` 就是入口样例）。

**未满足任何一条 → 不启用。** 本轮明确不启用，也不创建任何持续运行的进程。

---

## 10. 时间预算：多久才可能真正检验「招聘是否领先技术突破」

诚实估计（基于本轮实测的数据结构，而不是乐观假设）：

| 阶段 | 需要的条件 | 现实估计 |
|---|---|---|
| 建立可用时间序列 | 同一企业连续采集，且能区分 NEW / REVISION / REMOVED | **≥ 8–12 周**（覆盖一次季度级别的招聘波动） |
| 技术方向可分类 | 分类器在真实文本上可用，`UNCLASSIFIED` 率已知且有上限 | 已有初步版本；需 2–3 轮人工抽检迭代 |
| 有「变化」可检验 | 观察到 track 级岗位结构变化（不只是数量波动） | 取决于是否真的发生；**可能 90 天内不发生** |
| 与领先性关联 | 独立证据（审批/试验/论文）时间戳可靠 + 足够事件数 | 需要 ≥2 年带时间戳的独立证据与招聘序列对齐；**本轮不具备** |

因此：**90 天内最多能回答「招聘观察是否稳定、可分类、可去重」，不能回答「招聘是否领先技术突破」。**
后者至少需要 12–24 个月的连续数据与独立证据对齐，且必须预注册检验方式。
这个时间尺度是数据本身决定的，不是工作量决定的。
