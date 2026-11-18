# RELEASE-001 / 生产发布报告

- 执行时间：2026-11-19 04:57–05:10 CST（2026-11-18 20:57–21:10 UTC）
- 依据：`RELEASE_RUNBOOK.md` §2，批准人：项目负责人
- 结果：**发布成功**，生产 Radar 由 `14eaf61`（v2）升级为 `55b269e`（v3）

---

## 1. 实际运行版本与文件指纹

| 项 | 值 |
| --- | --- |
| `DEPLOYED_SHA` | `55b269e2e06f948ce759514269fa962aea956347` |
| 活动目录 | `/srv/medradar/radar/app` → `releases/55b269e…` |
| 回退目录 | `/srv/medradar/radar/app.previous` → `releases/14eaf615…` |
| **文件指纹** | 1,856 个受版本控制文件 sha256 **全等**（missing 0 / mismatched 0） |
| 前端 bundle | `index-Bxn-0Rgq.js`（570,457 B），sha256 `e0a1bba3007cfa30…` |
| 指纹对象 | 通过符号链接对**活动目录**校验，而不是对解压源校验 |

指纹命令：`verify_tree.py expected-55b269e.txt /srv/medradar/radar/app`

发布物由 `git archive 55b269e` 生成，与 staging 验证过的 `b6f4506` 在
`medradar/ web/ config/ scripts/` 上逐字节相同（发布前已核）。

---

## 2. 数据库 Schema 与记录一致性

| 项 | 发布前（v2） | 发布后（v3） |
| --- | --- | --- |
| schema | `radar-ledger-v2` | `radar-ledger-v3` |
| 观测 | 8,360 | **14,923** |
| 版本 | 8,360 | 14,923 |
| 变更事件 | 8,360 | 14,923 |
| 判定（历史） | 8,360 | **23,283** |
| integrity_check | ok | **ok** |
| foreign_key_check | — | **0 violations** |
| 迁移耗时 | — | **0.54 s** |

迁移后立即核对：观测/版本/判定**一行未丢**，8,360 条旧判定以 `rules_digest='legacy-v2'`
原样保留在历史表，新判定另写一行（`radar-assessment-2026.11.21`），
`admission_current` 同时可见两个版本。append-only 触发器未被绕过。

来源分布：

```
openfda_device 6938 | openfda_recall 6563 | crossref 1112 | pubmed 274
draeger_official 31 | philips_official 5
origin: LIVE 8360 | BACKFILLED 6563
```

账本体积 271.4 MB（发布前 45.3 MB），增长来自召回回填的 payload。

---

## 3. 召回通道真实运行结果

以**受控**方式单独执行，未等调度器自行触发：

```
[openfda_recall] 29 of 29 monitoring product codes still need an inventory pass
[openfda_recall] OK NEW_RECORDS new=6563 updated=0 unchanged=154 failed=0 in 94.16s (36 requests)
advance: 18 batches, CONVERGED, published 6563, admitted 6563,
         graph materialized 6563 -> 33,154 assertions (3,804 duplicates, 0 errors)
         elapsed 180.6 s
```

标记为 `observation_origin=BACKFILLED` / `discovery_phase=HISTORICAL_BACKFILL`，
回填理由写入来源状态：**"RELEASE-001: the deployed ledger never collected the recall channel"**。

六个已知安全事件的逐字段核对（全部命中）：

| 事件 | 企业 | 公开日 | 行数 |
| --- | --- | --- | --- |
| 99536 | GE Medical Systems | 2026-08-27 | 4 |
| 99475 | GE Medical Systems | 2026-08-04 | 1 |
| 99908 | Philips North America | 2026-10-16 | 1 |
| 99126 | Philips North America | 2026-06-24 | 1 |
| 99828 | Mindray DS USA | 2026-10-07 | 8 |
| 99549 | Nihon Kohden America | 2026-10-06 | 1 |

每条都带官方 FDA 链接（`accessdata.fda.gov/...res.cfm?id=<event>`）。

**界面行为正确**：在"最新发现"（来源近 30 天公开）视图下过滤 `openfda_recall`
得到 **0 条** —— 最新召回公开于 2026-10-16（33 天前），历史回填**不冒充最新情报**。
切到"最新观察"则显示 1,342 条窗口内记录。

---

## 4. 健康监控真实运行结果

已安装：`medradar-radar-health.service` + `.timer`（5 分钟，开机 2 分钟后首跑）。

```
STATE: DEGRADED
  avail    port ok | 127.0.0.1:8791
  avail    healthz ok | 200 in 66.1 ms
  avail    api_probe ok | skipped (alpha gate; liveness via /healthz, ledger read directly)
  avail    spa_index ok | …/app/web/dist/index.html
  pipeline critical_sources PASS
  pipeline watermark_legal WARN | a watermark leads UTC by 1 day (inside the 1-day grace)
  pipeline scheduler_heartbeat PASS
  pipeline acquisition_progress PASS
  product  ledger_integrity PASS
  product  ledger_writable UNKNOWN | read-only connection by design
  product  recall_channel PASS | 6563 records
  product  brief_generation PASS | 1.28 s
```

运行记录：04:58:35 首次失败（探针文件尚未上传，**正确 fail-fast**）→ 05:03:39、05:04:01、05:09:02 均 Finished。

**DEGRADED 的唯一原因**是 pubmed/crossref 的水位线比 UTC 早一天——真实存在的源时钟偏差，
不是探针噪声，也不影响读取。

---

## 5. 服务与浏览器验收

| 服务 | 状态 | 说明 |
| --- | --- | --- |
| `medradar-radar-web` | active | 8791，MainPID cwd = 55b269e |
| `medradar-radar-scheduler` | active | MainPID cwd = 55b269e |
| `medradar-radar-tunnel` | active | 公网入口未改动 |
| `medradar-radar-health.timer` | active | 5 分钟 |
| `medradar-web` / `medradar-data-update.timer` | active | **FDA 快照管线未触碰** |

`systemctl --failed` → **0 units**。

**API（13 个端点，生产数据）**：全部 **200**

```
/api/radar/feed?limit=20       0.131 s     /api/radar/graph/summary    2.327 s
/api/radar/feed/facets         0.018 s     /api/radar/technology-map   2.234 s
/api/radar/sources             0.110 s     /api/radar/pipeline         2.512 s
/api/radar/health              2.707 s     /api/radar/brief?days=7     1.326 s
/api/radar/notices             0.014 s     /healthz                    0.002 s
```

**浏览器（真实 Chrome，生产数据、同一发布物）**：

- 页面正常渲染，20 张卡片，4 个首屏 API 全部 200，**Console 0 错误 0 警告**
- 四个视图计数正确：最新发现 36 / 最新观察 8,139 / 历史资料库 7,990 / 待核实 149
- 来源筛选生效（`openfda_recall` → pressed）
- **证据抽屉修复在生产数据上确认**：`admission is null: False`，decision `REVIEW`，
  tier `NEEDS_REVIEW`，9 个维度，**Feed 与详情判定一致**，`discovery_phase=HISTORICAL_BACKFILL`

**公网入口**：`https://…trycloudflare.com/` → **401**（门有效），`/healthz` → **200**（可达）。
认证方案未改动。

---

## 6. 备份与回滚资产

| 资产 | 路径 | sha256 | 内容 |
| --- | --- | --- | --- |
| **切换前（v2）** | `/srv/medradar/data/radar/backups/radar-20261118T205711090.db` | `2a054522fd349907…` | 8,360 条，integrity ok |
| **发布后（v3）** | `/srv/medradar/data/radar/backups/radar-20261118T211019641.db` | `518b3583fc686a25…` | 14,923 条，integrity ok |
| 回退代码 | `/srv/medradar/radar/releases/14eaf615…`（`app.previous`） | 1,759 文件指纹 | 完整旧树 |
| 重放工具 | `docs/final_preflight/001/tools/rollback_replay.py` | — | v3→v2 增量重放 |

回滚路径三选一：①仅改符号链接（切换后无写入，零损失）；②恢复 v2 备份 + 重放 v3 增量（0.55 s，记录无损）；
③恢复 v3 快照（保留回滚前的完整审计历史，满足门禁要求）。

备份目录共 478 MB，保留 14 份。

---

## 7. 首轮调度执行结果

```
05:04:08  Started medradar-radar-scheduler (55b269e)
05:04:09  cycle 1: IDLE new=0 updated=0 ai=None
          [graph] materialized 0 observation(s): 0 new, 0 duplicate, 0 error
05:09:09  cycle 2: IDLE new=0 updated=0 ai=None
```

五个来源均报 "not due yet"（刚回填完，水位线已推进），图谱无需再物化。
调度器按 5 分钟节拍稳定运行，没有异常退出。

---

## 8. 切换窗口

| 步骤 | 时刻（UTC） |
| --- | --- |
| 冻结写入者 | 20:57:09 |
| 一致性备份完成 | 20:57:11 |
| 停止 Web | 20:57:2x |
| 迁移完成（0.54 s） | 20:57:28 |
| 新 Web 就绪 | 20:58:20 |

**公网不可用窗口约 55 秒**，在 Runbook 许可的 60 秒内。

---

## 9. 剩余风险与后续观察要求

| # | 风险 | 严重度 | 观察要求 |
| --- | --- | --- | --- |
| R1 | pubmed/crossref 水位线领先 UTC 1 天 | 低 | 健康状态会长期停在 DEGRADED；确认它**只**由这一项触发，否则视为新问题 |
| R2 | `/api/radar/graph/summary` 2.33 s（回填后节点 42,754） | 中 | 观察一周；若科技地图首访持续 >3 s，考虑加缓存（不在本次范围） |
| R3 | AI 待办 133 条 | 低 | AI worker 不属于本次发布；确认队列不再增长 |
| R4 | 无外部告警渠道 | 中 | 人工每日查看 `/var/lib/medradar-radar-health/last.json` 与 `systemctl --failed` |
| R5 | 公网入口为临时 Quick Tunnel | 中 | 试验期可用；正式对外前需换成命名隧道 |
| R6 | 备份保留 14 份（约 4 GB 上限） | 低 | 录像回填后单份 284 MB，需确认磁盘余量 |
| R7 | 召回是历史回填 | 中 | 第一次**真实增量**召回出现时，确认它是 `LIVE` 而非 `BACKFILLED` |

**后续 24 小时检查清单**：调度器周期稳定、无来源连续失败、健康状态未恶化、
磁盘余量 >30 GB、无 5xx 增长、备份定时器产出正常。

---

## 10. 门禁核对

| 门禁 | 结果 |
| --- | --- |
| 部署代码匹配冻结候选 | ✅ 1,856 文件指纹全等 |
| 未临时加入未验证功能 | ✅ 发布物 = `git archive 55b269e` |
| 新旧版本不同时写同一库 | ✅ 旧调度器 20:57:09 停止后才迁移；新调度器 21:04 启动 |
| 不可逆步骤前验证备份 | ✅ 备份 verified=True + integrity ok 后才迁移 |
| 回滚保留完整 v3 副本 | ✅ `radar-20261118T211019641.db` + 旧代码树 |
| 异常即停 | ✅ 未触发（唯一的失败是探针文件未就绪，已即时修复） |
| 现场与 Runbook 无实质差异 | ✅ 唯一差异是备份命令会先打印一行进度再用 JSON，已按此解析 |
| 不改 FDA 管线/入口/认证 | ✅ 三者均未触碰 |

---

## 11. 结论

生产 Radar 已运行在 `55b269e`，v3 账本 14,923 条观测、42,754 节点图谱、7 个来源（2 个 blocked-by-policy 之外全部 OK），
召回通道已建立并有 6,563 条历史记录，健康监控已安装并在 5 分钟节拍上运行。

**发布完成。** 但**正式发布完成 ≠ 四周产品试验完成**：
接下来的观察期与试验机制见 `PILOT_BRIEF.md` 与 `RELEASE_RUNBOOK.md` §7.3。
