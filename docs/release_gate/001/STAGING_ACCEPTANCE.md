# RELEASE-GATE-001 / 候选版本隔离运行验收

- 候选版本：`f2f70dd`（分支 `pilot/pilot-ready-001`，17 个提交相对生产）
- 运行位置：`/srv/medradar/release-gate/001/staging/`（生产服务器上的隔离目录）
- 结论：**功能验收通过；内容质量验收部分不通过（见 §6）。**

---

## 1. 隔离环境

| 项 | 值 |
| --- | --- |
| 代码 | `staging/release-f2f70dd…/`（导出自 git HEAD，含 `web/dist`） |
| Python | `release-gate/001/venv`（3.12.3，pytest 9.2.0、fastapi、uvicorn、httpx） |
| 数据 | `staging/data/radar.db`（备份副本迁移到 v3 后回填） |
| 图谱 | `staging/data/graph.db`（由账本物化，45,174 节点 / 29,082 边） |
| 监听 | **127.0.0.1:8792**（仅回环；生产是 8791） |
| 日志 | `release-gate/001/logs/` |
| 身份 | `medradar`，与生产同用户但不同目录 |
| 生产隔离 | 未新增/修改/重启任何 systemd 单元；未触碰 `/srv/medradar/data` |

### 1.1 一次真实的隔离事故与它带来的护栏

第一次回填时我漏设了 `MEDRADAR_RADAR_DIR`，产品的路径解析回落到"源码树相对目录"，
于是那一次采集写进了 `staging/release-…/data/radar`（而不是 `staging/data`）。

- 影响：只写进了隔离目录，**生产库完全未被触碰**（事后核对：生产 `radar.db` mtime 仍是本轮开始前的
  `00:49:36`，行数 delta 全 0）。
- 处置：该目录已改名保留为证据（`staging/discarded-cwd-data-*`），随后**强制设置 env 前缀**重跑。
- 教训（已写入 `RELEASE_RUNBOOK.md` 的护栏）：任何针对隔离目录的产品命令，**必须显式设置
  `MEDRADAR_RADAR_DIR`**，并在执行前打印一次解析结果确认。产品在"没有 env 且 cwd 在源码树"时
  会静默选一个目录——这在生产上是正确行为，在隔离测试里却是陷阱。

---

## 2. A. 数据库验收

| 检查 | 结果 |
| --- | --- |
| schema v3 | `radar-ledger-v3` |
| 历史完整 | 迁移前后 8,360/8,360/8,360/8,360/17,285/1,660 全部不变 |
| 判定版本 | 历史：`radar-admission-2026.11.3`（8,360，`legacy-v2`）；当前：`radar-assessment-2026.11.21`（16,288） |
| 派生投影 | `admission_current` 16,253 行，与历史一致 |
| DOI/PMID 归并 | `observation_identifier` 14,786 行；`work_key` 全部填充；跨源同 DOI 以 `OFFICIAL_IDENTIFIER_MATCH` 连边（图谱 55 条） |
| 事件号归并 | 同一 FDA 事件多行（如 99828 有 8 个 product_res）在简报里折叠为 1 条（`rows collapsed into one event: 1`） |
| 重复执行稳定性 | 第二次 `advance` 1 批 0.21 s，`admitted=0`；`reproject` 决定 0 条 |
| 完整性 | `integrity_check=ok`，外键 0 违规 |

---

## 3. B. 调度验收（全部在服务器上真实执行）

| 场景 | 命令 | 实测 |
| --- | --- | --- |
| 首次迁移 + 回填后的 advance | `radar run --source openfda_recall` | 6,563 条新增，31/31 scope 完成，抓取 87 s；advance **18 批 / 139.4 s / CONVERGED / backlog 0** |
| 同源再跑（无新数据） | 同上 | `NO_NEW_RECORDS`，0 new / 266 unchanged / 2 请求 / **3.0 s**；advance 1 批 |
| 单源无新数据 | `radar run --source openfda_device` | `NO_NEW_RECORDS`，0/0/14，1.27 s；advance **1 批 0.21 s** |
| 存在新记录 | `radar run`（全源强制周期） | 新增 1,330 条；advance **42 批 / 31.1 s / CONVERGED**；wall 111 s |
| 再次 advance（幂等） | `radar advance` | 1 批 0.21 s，`admitted=0`，`backlog.total=0` |
| 规则重判 | `radar reproject` | `decided now = 0`（所有观测已在当前判定版本下） |
| 访问被拒的来源 | `radar run --source gehealthcare_official` | 策略拒绝被记录，不重试、不伪装成"无结果"；管道照常收敛 |
| 迁移中断恢复 | 见 `MIGRATION_TEST.md` §4 | 修复后可恢复；有回归测试 |
| 有界终止 | 所有 `advance` 都返回 `status / stop_reason / backlog` | 42 批内收敛，无"跑满预算仍不知是否完成" |

**关于"终止条件"**：`advance` 现在只用**实测积压**判断完成；预算或时限用完时返回 `PARTIAL` 并
报出四项剩余计数；若"某批无工作但积压非空"则返回 `STALLED`。三种状态都有测试。

---

## 4. C. API 验收

| 端点 | 状态 | 备注 |
| --- | --- | --- |
| `/healthz` | 200 | 免认证存活探针 |
| `/api/radar/health` | 200 | `state=DEGRADED`，附六项检查与 `legacy_state` |
| `/api/radar/sources` | 200 | 7 个来源（含 `openfda_recall`） |
| `/api/radar/feed` | 200 | 默认窗口 total=42；一条 28 个字段 |
| `/api/radar/intelligence/{id}` | 200 | 含 `evidence_references`、`event_date_precision`、`mapping_history` |
| `/api/radar/brief?days=7` | 200 | |
| `/api/radar/feed/admission-summary` | 200 | |
| `/api/radar/feed/facets` | 200 | |
| `/api/radar/technology-map` | 200 | |
| `/api/radar/graph/summary` | 200 | 45,174 节点 / 29,082 边 |
| `/api/radar/graph/changes` | 422 | **需要 `known_at` 参数**；不带参数时是参数错误，不是故障 |
| `/api/radar/compare` | 200 | |
| `/api/radar/notices` | 200 | |
| `/api/radar/pipeline` | 200 | |
| `/api/meta` | 503 | **环境差异**：这是旧工作台（FDA 快照）的元数据端点，隔离环境没有挂载快照目录。生产上它是 200。不是候选版本缺陷。 |
| `/`（SPA） | 200 | 返回 `index.html`，引用**新** bundle `index-Bxn-0Rgq.js`（570,457 B，200） |

前端：候选版本**包含重新构建的前端**（`web/dist` + `web/src` 三处改动），
与生产正在服务的 `index-tJRHX4KH.js` 不同。隔离环境服务的是新 bundle。

**"尚未构建"与"运行失败"的区分**：`graph.db` 缺失时 `/graph/*` 返回 503 并给出
`graph_not_built` 与重建命令；本轮图谱是建好的，所有图端点返回 200。这个区分在代码里是显式的。

---

## 5. D. 真实数据验收（逐条向官方记录核对）

回填的 6,563 条召回中，逐个事件核对已知的监护安全事件：

| 事件号 | 企业 | 监管号 | 公开日期 | 首次发现 | 行数 | 判定 |
| --- | --- | --- | --- | --- | --- | --- |
| 99536 | GE Medical Systems IT | Z-3036-2026 | 2026-08-27 | 2026-11-18T19:00:35Z | 4 | BACKFILLED / HIGH_RELEVANCE / FEED |
| 99475 | GE Medical Systems IT | Z-2878-2026 | 2026-08-04 | 2026-11-18T19:00:35Z | 1 | 同上 |
| 99908 | Philips North America | Z-0199-2027 | 2026-10-16 | 2026-11-18T19:00:33Z | 1 | 同上 |
| 99126 | Philips North America | Z-2579-2026 | 2026-06-24 | 2026-11-18T19:00:33Z | 1 | 同上 |
| 99828 | Mindray DS USA | Z-0109-2027 | 2026-10-07 | 2026-11-18T19:00:33Z | **8**（8 个 product_res） | 同上 |
| 99549 | Nihon Kohden America | Z-0089-2027 | 2026-10-06 | 2026-11-18T19:00:33Z | 1 | 同上 |

逐项核对的内容（以 99549 为例）：

```
identifier  Z-0089-2027
firm        Nihon Kohden America LLC
product     Nihon Kohden CNS-6200 Series Central Nurse Station, CN-6201 …
posted      2026-10-06  (precision: date)
initiated   2026-09-08
reason      cybersecurity issue … NULL Pointer Dereference … may cause disruption of the
            centralized monitoring of multiple beds and the visualization of alarms
url         https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=99549
origin      BACKFILLED   phase  HISTORICAL_BACKFILL
```

**回填不得冒充上线后新发现**——这一点被机制保证，不是靠自觉：

```
openfda_recall 全部 6,563 行： observation_origin=BACKFILLED, discovery_phase=HISTORICAL_BACKFILL
backfill_reason（唯一值）： RELEASE-GATE-001 staging: the deployed ledger never collected the recall channel
```

换句话说：**这些记录在账本里永远带着"我是导入的"这个标签**，简报也因此把它们放进
"历史安全事件补充"而不是正文。

---

## 6. E. 周报验收（7 天窗口）

命令：`radar brief --since 2026-11-12 --until 2026-11-18`，耗时 **1.64 s**，峰值 RSS 151 MB。

| 要求 | 结果 |
| --- | --- |
| 明确 7 天窗口 | ✅ 头部写明 `窗口 / window: 2026-11-12 .. 2026-11-18`，正文标题却是"周报"（这次窗口真的是 7 天，标题对上了） |
| 区分新增/更新/历史补充 | ✅ `novelty: 本周公开 82 · 本周更新 0 · 历史首次采集 14810 · 日期不明 31`，并有独立的"历史安全事件补充"章节 |
| 日期精度正确 | ✅ 本月精度修复后，`YYYY-MM` 显示为 `(month)` 而不是 `(year)` |
| DOI 与原始链接可核查 | ✅ 抽查 3 条 DOI 均可解析（上一轮那条 404 的 DOI 未再出现，因为它落在别的窗口） |
| 不强制凑足 15 条 | ❌ **仍然固定取满 15 条**（`--max-items` 默认 15，是上限不是目标，但候选池足够大时它总是填满） |
| 不重复摘要代替分析 | ❌ **"发生了什么"仍是原文摘要的逐字截断**，"研发关注点"仍是同一句模板 |
| 不虚构研发影响 | ✅ 没有虚构（因为根本没写具体影响） |
| 明确人工复核状态 | ✅ 每条都有 `复核状态 / review: not reviewed` 与 `不确定性` |

### 6.1 生成结果的真实质量

```
views: ARCHIVE 14448 · CANDIDATE 458 · INTELLIGENCE 17
15 条正文里，标题层面的实际监护设备相关条目约 5 条：
  #5  ICU 内用 PPG 估算血压（真实研究，相关）
  #8  手持容积二氧化碳计（相关）
  #9  运动鲁棒的非接触生命体征监测（相关）
  #10 血氧与脑氧合（相关）
  #7  TinyML PPG 房颤检测（边缘相关）
其余 10 条是 ECG 分类算法、胎儿 ECG、情绪识别、甚至"儿科氟康唑安全性综述"——都不是床旁监护设备。
```

**结论：生成器结构正确、内容不合格。** 它可以作为"机器下限"，但不能直接作为给研发负责人看的一页。
这正是上一轮 `PILOT_BRIEF_CANDIDATE.md` 由人（Agent）重写取舍的原因，本轮结论不变。

### 6.2 历史补充只有 5 条，且不是最相关的 5 条

简报的"历史安全事件补充"只列了 5 条（99908 / 99838 / 99549 / 99801 / 99617），
而账本里有 6,563 条召回、其中至少 6 个事件与本次验收直接相关。GE Portrait（99536/99475）、
Philips Telemetry 5500（99126）、Mindray（99828）都**不在**这个列表里。

原因是这一节按公开日期取最近的若干条。对读者来说，这意味着：
**最相关的历史事件可能因为"日期不够新"而被挤出补充列表**。这是一个需要产品决策的取舍，
本轮记录为内容缺陷，不作为上线阻塞。

---

## 7. 本轮未验收的部分（明确列出）

| 项 | 状态 | 原因 |
| --- | --- | --- |
| 真实浏览器走查 | **NOT VERIFIED** | 入口需要 Basic 凭据；本轮不代用户登录。SPA 与 bundle 的**可获取性**已验证（200 + 正确哈希），渲染未验证 |
| Alpha 门在候选版本下的行为 | 部分 | 生产门禁代码未改动；隔离环境**故意关闭**门禁以便 curl。门禁本身有既有测试 |
| Cloudflare 隧道在切换后的表现 | NOT VERIFIED | 需要生产切换后才能观察 |
| 长期稳定性（>1 小时） | NOT VERIFIED | 隔离实例运行了约 20 分钟 |
| 生产并发写入下的迁移 | NOT VERIFIED | 迁移在冷副本上做；切换流程用"停调度器"规避并发（见 `RELEASE_RUNBOOK.md`） |
| 通知渠道 | 未配置 | 只有可观察的故障记录（`HEALTH_MONITORING.md`） |
