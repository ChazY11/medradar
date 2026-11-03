# MedRadar Live Observatory — 用户与运维指南

> 从历史快照分析，走向持续、可审计的科学观察。
> 本轮目标不是“看起来实时”的仪表盘，而是能够持续积累科研证据、并随时回答
> **“在某个历史时点，我们究竟观察到了什么、何时观察到的”** 的基础设施。

Live Observatory 是 MedRadar 2.0 产品之上的一层**独立增量观察系统**：它轮询
权威公开来源，把每条公开记录作为一次「观察」写入一个只追加的 Observation
Ledger，并在现有 Web 产品中以「实时观察站」页面呈现。旧的 1.37 GB 科研数据库
`data/medradar.sqlite` **只读、不被写入**；原有企业统计、技术雷达、证据追踪等
口径完全不变。

---

## 1. 一分钟了解它是什么 / 不是什么

**是：**

- 一个增量采集框架：`Source Adapter` 统一接口 + 分页/限速/重试/预算/断点续传/幂等。
- 一份只追加的观察账本：`first_seen_at` 由真实采集程序在首次成功观察时写入一次，SQLite 触发器保证永不被改写。
- 一套版本与修订追踪：`NEW / UPDATED / UNCHANGED / REMOVED_OR_UNAVAILABLE / FETCH_FAILED` 五态分明，每个 payload 版本都可回溯。
- 一个**时点回放**能力：`as_of` 之前未被观察到的记录，即使其事件日期更早，也绝不出现。
- 一个诚实的同步状态面板：上次成功时间、连续失败、结构漂移、已核验的企业覆盖、**实测**发布→观察延迟（无法测量时明确写“无法测量”）。

**不是：**

- 不是分钟级实时系统。它是**轮询**，每个来源的实际节奏写在 UI 与状态里。
- 不是“FDA 数据 = 全球医疗技术全貌”。覆盖范围与缺口逐条展示。
- 不是预测。新公开活动不会被解释为战略转变；没有已验证的前瞻预测。
- 不是把历史资料伪装成当年观察。历史回填必须标记 `BACKFILLED` 并写明理由（本轮未做任何历史回填）。

---

## 2. 已接入来源与真实覆盖

| 来源 | 官方 API | 状态 | 观察内容 | 更新延迟可否测量 |
|---|---|---|---|---|
| SEC EDGAR | `data.sec.gov/submissions`、`www.sec.gov/files/company_tickers.json` | 已接入 | 发行人披露（8-K/8-K/A/6-K/10-Q/10-K/20-F），每条 accession 一条观察 | **可以**：SEC 提供 `acceptanceDateTime`（UTC 秒级） |
| ClinicalTrials.gov | `clinicaltrials.gov/api/v2/studies` | 已接入 | 注册试验（状态/阶段/入组/干预…）的元数据与修订 | 只能到**日**：API 只提供日期 |
| Europe PMC | `ebi.ac.uk/europepmc/webservices/rest/search` | 已接入 | 文献元数据增量和修订 | 只能到**日**：仅首次发表日期 |
| FDA 510(k) / PMA | 既有 openFDA 采集代码 | **不宣称实时** | 按官方发布频率同步，复用既有采集与修订核对 | 延迟由 FDA 发布节奏决定，不做分钟级承诺 |

### SEC 企业覆盖是逐家核验的，不是假定的

系统不会假设每家企业都有 SEC 披露。核对结果写入 `source_state.entity_coverage`，
并在页面逐条显示证据（`python -m medradar observatory sources` 查看）：

- **Medtronic (MDT)**：COVERED，CIK 0001613103（官方 ticker 表 + submissions 文件复核）。
- **GE HealthCare (GEHC)**：COVERED，CIK 0001932393。
- **Philips (PHG)**：COVERED，CIK 0000313216（20-F 外国发行人）。
- **Dräger (DRW3)**：当前无持续 SEC 披露。官方 ticker 表无 DRW3；EDGAR 公司检索只匹配到
  个人申报人 `DRAEGER DENNIS M`（最近申报 2003 年），不是该医疗技术企业。
- **Mindray (300760)**：**曾有** ADR 时代披露（Mindray Medical International LTD，
  最近 2016-03-15 的 15-12B / 25-NSE 退市类申报），当前无持续披露；历史记录不在本轮实时观察范围。

> 这些状态的含义是「SEC 渠道没有该企业的当前披露」，**不是**「该企业没有产品、销售或研发活动」。
> 其他来源独立观察。

---

## 3. 快速开始

前置：Python ≥ 3.10，仓库根目录，可选 `pip install -e .[web]`。

```bash
# 1) 手动触发一次增量采集（默认来源：sec_edgar, ctgov, europepmc）
python -m medradar observatory sync

# 只采一个来源 / 限定企业 / 只看最近 30 天首次发现
python -m medradar observatory sync --source sec_edgar --company medtronic --since-days 30

# 2) 先看要采什么，不写任何数据
python -m medradar observatory sync --source sec_edgar --dry-run

# 3) 查看账本与各来源同步状态（JSON 可给监控使用）
python -m medradar observatory status
python -m medradar observatory status --json

# 4) 查看已核验的企业覆盖与结构漂移
python -m medradar observatory sources

# 5) 时点回放：这个时刻之前，我们真正观察到了什么？
python -m medradar observatory replay --as-of 2026-11-03T10:00:00Z --json

# 6) 数据一致性 + SQLite 完整性审计
python -m medradar observatory reconcile

# 7) 一致备份（账本 + 原始 HTTP 响应归档）
python -m medradar observatory backup --dest data/backups
```

Web 页面：

```bash
python -m medradar web --port 8787
# 打开 http://127.0.0.1:8787/#/observatory
```

页面上的两种时间永远分开写：

- 「事件发生于 2026-10-19」——来源记录的事件日期；
- 「MedRadar 于 2026-11-03 14:39 首次观察到它」——真实采集时间。

> 当你刚接入一个来源时，很多「过去的事件」会在同一天被首次观察。那正是
> 「MedRadar 今天才观察到一条过去的事件」，不是「今天发生了很多事」。

---

## 4. 持续运行

### 4.1 本地定时（推荐用于一台常开的机器）

```bash
# 每 60 分钟一轮，直到 Ctrl+C；每轮都会写 run 记录与 heartbeat
python -m medradar observatory watch --interval-minutes 60

# 只跑两轮（验收/测试用）
python -m medradar observatory watch --max-cycles 2 --interval-minutes 1
```

- 暂停 / 恢复（对所有调度方式生效，状态写入账本）：

```bash
python -m medradar observatory pause --reason "维护窗口"
python -m medradar observatory resume
```

- 崩溃恢复：进程中断后，`sync` 会先把遗留的 `RUNNING` 记录标为 `INTERRUPTED`，
  再按 `sync_checkpoint` 从上次成功的页继续；**已提交的页不会重写，未提交的页不会丢失**。
- 失败退避：单个范围（如一家发行人）失败不会终止整轮；连续失败会在 `watch` 中指数退避
  （最多 8 倍间隔），并写入 `source_failure`。

### 4.2 Windows 计划任务（本机已注册，见 docs/DEPLOYMENT.md）

```powershell
# 注册/更新（默认每 360 分钟触发一次单轮采集；-WhatIf 只打印不执行）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -WhatIf
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Status
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Uninstall
```

任务名 `MedRadarObservatory`，动作是 `scripts\observatory_watch.ps1`（前台运行
`observatory watch --trigger schedule`），日志写入 `logs/collector-YYYYMMDD.log`。
计划任务每 360 分钟触发一次；`StartWhenAvailable` 会让休眠/关机期间错过的轮次在恢复后补跑一次，
`MultipleInstances IgnoreNew` 与账本单写租约共同保证不会并发写同一账本。

### 4.3 单写租约与并发防护（必须启用）

```bash
python -m medradar observatory lock status          # 当前租约持有人 / heartbeat 年龄
python -m medradar observatory lock release --reason "运维确认卡死"   # 强制释放（会留审计记录）
```

- 采集进程启动时以原子方式创建 `data/observatory/collector.lock`（pid/host/mode/run_id/heartbeat），
  心跳每 15 秒更新；第二个采集进程会被明确拒绝（`LOCKED_SKIPPED`），不会写同一 SQLite。
- 持有者崩溃后，下一个进程在心跳过期（默认 90 秒）或 pid 不存在时接管，并把接管原因写入
  `runtime_state["lock_recovery"]`（可审计）。

### 4.4 Linux 常驻服务（systemd，模板见 deploy/systemd/）

`deploy/systemd/medradar-observatory.service`（`Restart=always`、`MemoryMax=512M`、`CPUQuota=50%`、
`KillSignal=SIGTERM`、journald 日志）与 `medradar-observatory.timer`（每 6 小时）任选其一，
详见 `docs/DEPLOYMENT.md`。**Windows 计划任务无法可靠终止长驻子进程，因此本机采用单轮触发模式**
（每次触发跑完一轮即退出，配合租约与 `IgnoreNew` 防重叠）。

### 4.5 健康、审计与七天验证

```bash
python -m medradar observatory health --json       # 部署状态 / 新鲜度 / 备份 / 恢复演练 / 验证进度
python -m medradar observatory audit               # 账本完整性审计（人类可读报告；可 --json）
python -m medradar observatory validate status     # 七天连续观察验证的真实指标
python -m medradar observatory deploy-status --status DEPLOYED_LOCAL --supervisor windows_task
```

健康状态词表：`OPERATIONAL` / `DEGRADED` / `PAUSED` / `NOT_DEPLOYED` / `VALIDATION_IN_PROGRESS`；
优先级与判定见 `docs/RELIABILITY_DESIGN.md §0`，七天验证协议见 `docs/CONTINUOUS_VALIDATION_PROTOCOL.md`。

### 4.3 GitHub Actions（低频补充，不是唯一保障）

`.github/workflows/observatory.yml` 每 6 小时运行一次。Actions 的 cron 可能延迟甚至丢失，
工作目录是临时的，因此：

- 账本通过 `actions/cache` 在运行之间恢复/保存，并额外上传为 artifact（保留期见 workflow）；
- **绝不以 Actions 临时目录作为唯一科研记录**：生产部署应使用常开机器（上节）或持久卷；
- 即使某次定时被跳过，`watermark` + 重叠窗口会在下一次运行时补齐缺口——这正是账本设计不依赖运行频率的原因。

### 4.4 最小持久化部署（可选，需人工授权后才可产生费用）

| 项目 | 最小规格 | 说明 |
|---|---|---|
| 计算 | 1 vCPU / 512 MB–1 GB | 纯轮询 + SQLite，单进程即可 |
| 磁盘 | 5–20 GB | 账本 + 原始响应缓存；按来源增长速度估算（见下） |
| 网络 | 出站 HTTPS | SEC 要求带联系方式的 User-Agent（`MEDRADAR_SEC_UA`） |
| 调度 | cron / systemd timer / 计划任务 | 每 1–6 小时一次 |

容量参考：SEC 3 家覆盖企业 60 天窗口首轮约数十条观察、账本 < 1 MB；原始响应缓存更大
（每页一个 JSON）。持续运行一年、5 家覆盖企业 + 试验 + 文献，量级仍在数百 MB 以内。

**禁止**：未经授权购买云服务；不得把大型 SQLite 反复提交进 Git（`data/` 已在 `.gitignore`）。

---

## 5. 数据如何持久保存与恢复

- 账本：`data/observatory/observatory.sqlite`（可用 `MEDRADAR_OBSERVATORY_DB` 指向别处）。
  - WAL 模式 + `synchronous=FULL`：断电后已提交的观察不会丢失。
  - `observatory backup` 使用 SQLite 在线备份 API 生成一致快照，并复制原始响应缓存。
- 原始数据备份：`data/observatory/cache/` 保存每个 HTTP 响应的原始 JSON；即使解析器
  以后发现缺陷，证据仍可离线重放（`--offline --fixtures`）。
- 断电/中断恢复：见 4.1；`observatory reconcile` 会检查版本链、首次观察时间、映射、
  状态历史、运行记录等 11 类一致性不变量。
- 账本不可变约束（触发器强制，测试覆盖）：`first_seen_at` 不可改；payload 版本不可改/删；
  change/status/mapping/failure 日志不可改/删；观察记录不可删（只能标 `REMOVED_OR_UNAVAILABLE`）。

---

## 6. 真实可回答的问题（以及仍不能回答的）

**可以回答：**

1. 某条公开记录我们第一次看到是什么内容、什么时候看到的？（版本链 + `first_seen_at`）
2. 它后来哪些字段变了？变化前后的两个版本是什么？（`UPDATED` + `changed_fields`）
3. 在 2026-11-03 10:00 这个时点，数据库里存了什么？（`replay --as-of`，严格排除之后才发现的记录）
4. 每个来源上次成功同步是什么时候、连续失败几次、结构是否漂移？（同步状态）
5. 从来源公开到 MedRadar 观察到，实际延迟多少？（有真实时间戳才计算；否则写“无法测量”）
6. 某企业到底有没有 SEC 披露？（逐家核验证据，含“只有历史记录”和“匹配到同名个人”）

**不能回答（会明确说明）：**

- 企业内部战略、研发投入、销售额；全球所有市场的监管活动；因果关系；经验证的前瞻预测。
- 采集失败 ≠ 没有新事件：失败记录为 `FETCH_FAILED`，并在页面单独展示。
- 同源多次出现 ≠ 跨源独立验证；来源不再提供 ≠ 现实事件消失。

---

## 7. 验证与测试分层

四层必须分开汇报，不得用合成测试冒充持续运行：

| 层 | 命令 | 说明 |
|---|---|---|
| 合成测试 | `python -m pytest tests/test_observatory_core.py tests/test_observatory_ctgov.py tests/test_observatory_europepmc.py tests/test_observatory_api.py tests/test_observatory_prospective.py -q` | 离线、确定性，验证机制不变量 |
| 真实 API 连通性 | `MEDRADAR_LIVE_TESTS=1 python -m pytest tests/ -q -k observatory` | 每个来源一次礼貌请求，校验文档化字段 |
| 真实增量采集 | `python scripts/observatory_acceptance.py --live` | 写入一次性账本，验证 A/B/E，产出证据到 `out/observatory_acceptance/` |
| 真实定时运行 | `python -m medradar observatory watch --max-cycles 2 --interval-minutes 1` | 两轮真实轮询 + heartbeat + 运行记录 |

完整验收（含浏览器产品场景 G）：

```bash
python scripts/observatory_acceptance.py --live --with-e2e
```

---

## 8. 字段速查（Observation Ledger）

| 字段 | 含义 | 谁写入 |
|---|---|---|
| `event_at` (+`event_at_precision`) | 事件在来源语境中发生的日期/时刻 | 来源，缺失就为空 |
| `published_at` (+precision) | 来源**公开该记录**的时间；缺失不推测 | 来源 |
| `first_seen_at` | MedRadar **首次成功观察**该记录的真实时间，只写一次、不可改 | 采集程序 |
| `last_checked_at` | 最近一次核对时间（失败不更新） | 采集程序 |
| `source_updated_at` | 来源自己的“最后更新”字段 | 来源 |
| `observation_origin` | `LIVE` 或 `BACKFILLED`（后者必须有 `backfill_reason`） | 采集程序 |
| `source_payload_hash` | 当前 payload 的 sha1（canonical JSON） | 账本 |
| `observation_status` | `ACTIVE` / `REMOVED_OR_UNAVAILABLE` | 账本 |
| 版本表 | 每个不同 payload 一版，含 `changed_fields` 与 `captured_at` | 账本（只追加） |
| `entity_status` | `MAPPED` / `PENDING_REVIEW` / `UNMAPPED` / `AMBIGUOUS` | 映射层（只追加剧历史） |
| `track_status` | `MAPPED` / `PENDING_REVIEW` / `UNMAPPED` | 映射层（只追加剧历史） |

时间一律 UTC；来源只给日期就不编造时刻；同日不同精度按字符串可比较存储。

---

## 9. 常见问题

**Q：为什么我刚运行就出现很多“新增观察”，它们的事件日期是几周前？**
A：因为我们今天才第一次真正观察到它们。这正是 `first_seen_at` 与 `event_at` 必须分开的原因；
`BACKFILLED` 标签只用于“明知是历史归档、有意补入”的数据，本轮没有做任何回填。

**Q：第一次运行的延迟数字很大，之后会变小吗？**
A：会。首轮观察窗口包含过去几十天的记录，因此“发布→首次观察”包含历史积压；持续轮询后
该延迟反映真实轮询周期（SEC 通常为小时级）。页面同时展示“来源声明节奏”和“实测延迟”，
并标明可测/不可测。

**Q：SEC 的 8-K 会不会被改写？**
A：不会。SEC 的更正以新的 accession（如 8-K/A）出现，是一条新记录。系统只在 SEC 自己
修订某条已观察 accession 的元数据时才会出现 `UPDATED`。

**Q：采集失败会不会被当成“没有新事件”？**
A：不会。失败写入 `source_failure`，已知记录标 `FETCH_FAILED`，运行状态为 `PARTIAL`/`FAILED`，
`last_checked_at` 不前进，watermark 不前进。

**Q：如何暂停全部采集？**
A：`python -m medradar observatory pause --reason "..."`；`resume` 恢复。两者都会写入账本，
因此 cron、Actions 与本地 watch 都会遵守。
