# MedRadar Live Observatory v1 — 验收与真实采集报告

- 分支：`feat/live-observatory-v1`
- 基线：`ee7d011`（已验收的 MedRadar 2.0 MVP HEAD；PR #12 仍为 **DRAFT，未合并**）
- 验收日期：2026-11-03（UTC）
- 环境：Windows，Python 3.12.10，本地 SQLite，无付费服务
- 证据目录：`docs/observatory/evidence/`（本次运行产生的 JSON 原始证据）与
  `out/observatory_acceptance/`（一次性账本验收运行，gitignored）

> 本报告只写实际发生了什么。**没有**把合成测试通过说成持续运行已经成功，**没有**
> 把历史资料伪装成当年观察，**没有**宣称实时推送或已验证的预测。

---

## 0. 结论摘要

| 问题 | 实测答案 |
|---|---|
| 端到端通路是否真实打通？ | 是：SEC EDGAR 官方 API → 增量采集 → 真实 `first_seen_at` → 只追加 Observation Ledger → FastAPI → Live Observatory 页面（含首页 `Newly Observed Evidence` 区块） |
| 真实接入了哪些来源？ | 3 个官方来源：SEC EDGAR、ClinicalTrials.gov API v2、Europe PMC REST（另复用既有 FDA 510(k)/PMA 采集，**不宣称实时**；Crossref 未接入） |
| 首次真实采集发生于何时？ | **2026-11-03T14:39:53Z**（SEC EDGAR）；ClinicalTrials.gov 14:44:26Z；Europe PMC 14:44:29Z |
| 抓到了多少真实新增记录？ | **400 条观察**：SEC 6、ClinicalTrials.gov 157、Europe PMC 237；全部 `observation_origin=LIVE`；**0 条**历史回填 |
| 抓到了多少真实修订记录？ | 生产账本中 **0 条真实 `UPDATED`**（本轮会话仅约 13 分钟，官方记录未发生可观察修订）。修订机制在**合成层级**用可控数据证明：两版 payload 均可追溯、`first_seen_at` 不变 |
| 各来源实际更新延迟？ | SEC **可测**（有 `acceptanceDateTime`，秒级 UTC）：首轮含历史积压 p50=251 h；会话期间唯一“发布后上线”的 1 条（Philips 6-K）延迟 **1.48 小时**。ClinicalTrials.gov / Europe PMC **只能到日**，小时级延迟明确标为“无法测量”，不推算 |
| 数据如何持久保存？ | 独立 SQLite 账本 `data/observatory/observatory.sqlite`（WAL + `synchronous=FULL`）；原始 HTTP 响应归档在 `data/observatory/cache/`；`observatory backup` 用在线备份 API 生成一致快照 |
| 断电/中断后如何恢复？ | 每页提交 + `sync_checkpoint`；重启先把手写中断的运行标为 `INTERRUPTED` 再按检查点续跑；失败页不推进 watermark。已用中断/超时/分页失败注入验证 |
| 哪些数据有真实 `first_seen_at`？ | 账本内 **400/400 条**均由采集程序在首次成功抓取时写入，SQLite 触发器禁止改写 |
| 哪些只是历史回填？ | **0 条**。本轮未做任何历史回填；回填能力已实现并被测试：没有 `backfill_reason` 的 `BACKFILLED` 写入会被拒绝 |
| 以前五个产品场景是否仍通过？ | 是：浏览器 e2e **8/8**（原 5 个 MVP 场景 + Live Observatory + 2 个 390px 移动端检查）；全量 pytest **exit 0**（1232 个测试被收集） |

---

## 1. 交付物清单（对应任务书 §11）

| # | 交付物 | 位置 |
|---|---|---|
| 1 | 统一增量采集框架（Adapter 协议 + 通用采集引擎） | `medradar/observatory/adapter.py`、`adapters/__init__.py` |
| 2 | ≥2 个可工作的官方来源 Adapter | `adapters/sec_edgar.py`、`adapters/ctgov.py`、`adapters/europepmc.py`（3 个） |
| 3 | 带版本的 Observation Ledger | `medradar/observatory/ledger.py`（只追加 + 触发器 + 时点回放） |
| 4 | Live Observatory 可交互页面 | `web/js/pages/observatory.js`、`medradar/product/observatory.py`、`medradar/web/routes_observatory.py` |
| 5 | 数据源同步状态与失败监测 | `source_state` / `sync_run` / `source_failure` + `/api/observatory/sources` + 页面“数据源同步状态”面板 |
| 6 | 本地定时采集能力 | `medradar/observatory/scheduler.py`、`observatory watch`、`.github/workflows/observatory.yml` |
| 7 | 可复现的前瞻时点回放 | `ledger.snapshot(as_of)`、`observatory replay --as-of`、`/api/observatory/replay`、Prospective Observation Registry |
| 8 | 自动化测试 + 实际采集验证记录 | 5 个 `tests/test_observatory_*.py`、`scripts/observatory_acceptance.py`、`docs/observatory/evidence/` |
| 9 | 简明用户使用文档 | `docs/LIVE_OBSERVATORY.md`、`docs/PROSPECTIVE_OBSERVATION_REGISTRY.md`、`docs/LIVE_OBSERVATORY_DESIGN.md` |
| 10 | 独立开发分支 + Draft PR | 分支 `feat/live-observatory-v1`；Draft PR（本报告提交后创建，未授权不合并） |

---

## 2. 实际接入来源与真实覆盖

| 来源 | 官方端点 | 状态 | 观察内容 | 时间精度 | 更新延迟 |
|---|---|---|---|---|---|
| SEC EDGAR | `data.sec.gov/submissions`、`www.sec.gov/files/company_tickers.json`、EDGAR 公司检索 | **已接入并真实采集** | 8-K/8-K-A/6-K/10-Q/10-K/20-F，每个 accession 一条观察 | 事件 `filingDate`=日；公开 `acceptanceDateTime`=秒级 UTC | **可测** |
| ClinicalTrials.gov | `clinicaltrials.gov/api/v2/studies` | **已接入并真实采集** | 介入性研究注册；状态/阶段/入组/干预/申办方变更 | 仅日期（`startDate`/`studyFirstPostDate`/`lastUpdatePostDate`） | **不可测**（无时间戳） |
| Europe PMC | `ebi.ac.uk/europepmc/webservices/rest/search` | **已接入并真实采集** | 文献元数据增量（标题/期刊/作者/DOI/首次发表/索引日期/修订日期） | 仅日期 | **不可测**（无可用时间戳） |
| FDA 510(k) / PMA | 既有 openFDA 批量采集代码 | 复用既有代码，**不宣称实时** | 按官方发布频率同步；本轮不改变其语义 | 日 | 由 FDA 发布节奏决定 |
| Crossref | — | 未接入（任务书列为可选补充） | — | — | — |

### SEC 披露覆盖是逐家核验的（不是“五家企业都有 8-K”）

`python -m medradar observatory sources` 输出的真实核对结果：

| 企业 | 状态 | 证据（系统内保存） |
|---|---|---|
| Medtronic（MDT） | `COVERED` | 官方 ticker 表 MDT → CIK 0001613103（Medtronic plc），并在该 CIK 的 submissions 文件中复核 ticker 列表 |
| GE HealthCare（GEHC） | `COVERED` | GEHC → CIK 0001932393（GE HealthCare Technologies Inc.） |
| Philips（PHG） | `COVERED` | PHG → CIK 0000313216（KONINKLIJKE PHILIPS NV，20-F 外国发行人） |
| Dräger（DRW3） | `NOT_CURRENT_REGISTRANT` | 官方 ticker 表无 DRW3；EDGAR 公司检索只匹配到个人申报人 `DRAEGER DENNIS M`（CIK 0001111174，最近申报 **2003-07-01**），不是该医疗技术企业 |
| Mindray（300760） | `NOT_CURRENT_REGISTRANT` | 检索匹配到 `Mindray Medical International LTD`（CIK 0001373060），最近申报 **2016-03-15**（15-12B / 25-NSE 退市类），当前无持续披露；历史记录不在本轮实时观察范围 |

> 状态语义：SEC 渠道没有该企业的当前披露，**不代表**该企业没有产品、销售或研发活动；
> 其他来源独立观察，不做跨源合并。

---

## 3. 首次真实采集与真实数据量

### 3.1 时间线（UTC，来自账本真实记录）

| 时刻 | 事件 |
|---|---|
| 2026-11-03T14:39:53Z | **首次真实采集**：SEC 同步开始；同秒写入 6 条 SEC 观察（`first_seen_at` = 14:39:53Z） |
| 2026-11-03T14:44:26Z | ClinicalTrials.gov 首次采集（157 条观察，`first_seen_at` 14:44:26Z 起） |
| 2026-11-03T14:44:29Z | Europe PMC 首次采集（237 条观察，`first_seen_at` 14:44:29Z） |
| 2026-11-03T14:49:51Z | 增量轮次中发现 1 条**此前不存在的新记录**：`NCT07307300`（ClinicalTrials.gov） |
| 2026-11-03T14:51:58Z | 一轮真实同步完成（三源均 `OK`，0 new / 0 updated / 全 unchanged） |
| 2026-11-03T15:09:01Z | 交付前确认轮：三源再次 `OK`，20 次请求，37 条命中全部 `unchanged`，0 new / 0 updated；观察总数保持 400 |

### 3.2 账本实际内容（`docs/observatory/evidence/09_final_ledger_evidence.json`）

| 指标 | 数值 |
|---|---|
| 观察记录 | **400**（SEC 6 · ClinicalTrials.gov 157 · Europe PMC 237） |
| payload 版本 | 400（每条当前 1 版） |
| 变更记录 | 400（全部 `NEW`；`UPDATED` / `REMOVED_OR_UNAVAILABLE` / `FETCH_FAILED` 各 0） |
| `observation_origin` | `LIVE` 400 · `BACKFILLED` **0** |
| 账本大小 | 1.69 MB（SQLite，WAL） |
| 运行记录 | 22 条（历史中断/结构告警的运行已被后续续跑收尾；所有失败同时保留在 `source_failure`） |
| 结构告警历史 | 6 条 `STRUCTURE_CHANGE`（见 §10 缺陷记录：初版检测器误报，已修正并重建基线） |
| 企业映射 | `MAPPED` 102 · `PENDING_REVIEW` 237 · `UNMAPPED` 61 |

**“事件发生于过去”与“今天才观察到”是两件事**（UI 分行陈述）：

- 400 条中有 **390 条**的 `event_at` 早于首次观察日期（典型：9 月的 8-K、2025 年注册的试验在今天被首次观察到）；
- 400 条**全部**满足 `published_at < first_seen_at`；
- 同一天发布即被观察到的：SEC 1 条、Europe PMC 4 条、ClinicalTrials.gov 0 条。

这 400 条**不是**历史回填：它们的 `first_seen_at` 是本次采集的真实时刻；
`BACKFILLED` 只用于“明知是历史归档、有意补入”的数据，本轮没有这样做。

---

## 4. 各来源实际更新延迟（能测才测）

| 来源 | 可测？ | 真实数值 | 说明 |
|---|---|---|---|
| SEC EDGAR | **是**（n=6，`datetime` 精度） | p50 **251.3 h**、p90 **1062.4 h**、max **1122.3 h** | 首轮窗口覆盖过去 60 天，5/6 条为历史积压（首次观察即迟到 15–47 天） |
| SEC EDGAR（会话内新发布样本） | 是（n=1） | **1.48 h** | Philips 6-K：来源公开 `2026-11-03T13:11:19Z` → 首次观察 `2026-11-03T14:39:53Z`。这更接近持续运行时的真实延迟，但样本量 n=1，**不能当作稳定统计** |
| ClinicalTrials.gov | 否 | 无法测量 | API 只给日期（无时间），h 级延迟不推算；`approximate_n=157` |
| Europe PMC | 否 | 无法测量 | 同上；`approximate_n=237`。另外 Europe PMC 的 `published_at` 采用 `firstIndexDate`（进入索引的日期），已在 payload 与文档中注明它**不是**网页可用时刻 |
| FDA 510(k)/PMA | 不适用本轮 | — | 未纳入实时通道；仍按既有批量采集运行 |

页面把“来源声明轮询周期”与“实测延迟”并列展示；不可测时显示“无法测量 + 原因”，
不显示推算值。

---

## 5. 持久化、备份与故障恢复

- **账本**：`data/observatory/observatory.sqlite`（`MEDRADAR_OBSERVATORY_DB` 可重定向；`data/` 已在 `.gitignore`，不会把大库提交进 Git）。
  - WAL + `synchronous=FULL`：已提交的观察在断电后不丢。
  - 只追加不变量由 SQLite 触发器强制：`first_seen_at` 不可改；版本行不可改/删；change/status/mapping/failure 日志不可改/删；观察不可删（只能标 `REMOVED_OR_UNAVAILABLE`）。
- **原始数据备份**：`data/observatory/cache/` 保存每个 HTTP 响应的原始 JSON；解析器如有缺陷可离线重放（`--offline --fixtures`）。
- **一致备份命令**：`python -m medradar observatory backup --dest data/backups`（SQLite 在线备份 API + 原始缓存复制），本次实测生成 160 KB 快照并通过 `reconcile`。
- **中断恢复**：每页写 `sync_checkpoint`；进程重启先把遗留 `RUNNING` 标为 `INTERRUPTED`，再从检查点续跑；失败页不推进 watermark、不写 `UNCHANGED`。
  - 本轮真实发生：初次同步失败（SEC 403，UA 不合规）→ 修正 UA 后**从同一 run 续跑成功**；结构告警导致的 `PARTIAL` 运行也在后续运行中从检查点收尾。
- **暂停/恢复**：`observatory pause --reason ...` / `resume`，状态入账本，cron、Actions、本地 watch 均遵守（验收实测：暂停后 sync 返回 `SKIPPED`）。
- **持续运行**：本地 `observatory watch --interval-minutes N`（含 heartbeat、失败指数退避）；GitHub Actions 模板每 6 小时运行并通过 cache/artifact 持久化账本——但**明确不作为唯一系统记录**，因为 Actions cron 可能延迟/丢失、工作目录是临时的。
- **费用**：未购买任何服务、未产生费用。

---

## 6. 验收场景 A–G（层级 + 结果 + 证据）

验收工具：`python scripts/observatory_acceptance.py --live --with-e2e`
（结果：**24 passed / 0 failed**，六层分别统计；报告 `docs/observatory/evidence/16_acceptance_report_full.json`）

| 场景 | 层级 | 结果 | 真实证据 |
|---|---|---|---|
| **A 首次发现** | synthetic / real_api_connectivity / real_incremental | PASS | 真实 SEC 记录写入账本，`first_seen_at` 均在本次采集开始之后；页面与 API 可查（`09_final_ledger_evidence.json`、`11_sec_observation_timeline.json`） |
| **B 重复采集** | synthetic / real_incremental / operations | PASS | 真实第二轮：`new=0`、`unchanged=4`，观察数 6→6，`first_seen_at` 逐条比对不变；backfill 无理由写入被拒绝 |
| **C 修订检测** | synthetic（可控数据）+ real 计数 | PASS（机制）/ 真实 0 条 | 合成层级：v1 `recruiting` → v2 `completed` 两版均保留、`changed_fields=["status"]`、`first_seen_at` 不变；真实层级诚实报告 0 条修订 |
| **D 故障恢复** | synthetic / real_scheduled / operations | PASS | 分页超时注入：`PARTIAL` → 续跑后 3/3 记录、`NEW` 恰 3 条、无重复；真实定时器 2 轮成功、heartbeat 落盘 |
| **E 跨源观察** | synthetic / real_incremental | PASS | SEC 6 条 + ClinicalTrials.gov 109 条（一次性验收账本）各自独立 `source_state`、独立状态与失败记录；Europe PMC 为第三源 |
| **F 科研回放** | synthetic + real 回放 | PASS | 真实账本：`as_of=2026-11-03T14:00Z` → **total 0**、`excluded_discovered_later=400`；`as_of=2026-11-03T23:00Z` → total 400。合成层级另证历史版本读取（`10_replay_demo.json`、`F_synthetic_replay.json`） |
| **G 产品兼容** | product_compatibility | PASS | 全量 pytest exit 0（1232 收集）；浏览器 e2e **8/8**：原五个 MVP 场景 + Live Observatory + 390px 移动端（`17_product_e2e_report.json`） |

### 测试分层与数量（不混为一谈）

| 层级 | 内容 | 本次结果 |
|---|---|---|
| 合成测试 | `tests/test_observatory_core.py` 19 · `test_observatory_ctgov.py` 9 · `test_observatory_europepmc.py` 10 · `test_observatory_api.py` 15 · `test_observatory_prospective.py` 9 | **60 通过**（另有 2 个 live 测试默认 skip） |
| 真实 API 连通性 | 每源 1 次礼貌请求（`MEDRADAR_LIVE_TESTS=1` 或验收工具 real_api_connectivity 层） | 5/5 PASS（SEC tickers、SEC submissions、CTGov v2、Europe PMC、dry-run 不写入） |
| 实际增量采集 | 一次性账本上的两轮真实采集 | 4/4 PASS（A/B/E + 真实修订计数） |
| 真实定时运行 | `watch` 两轮真实轮询 | 1/1 PASS（2 轮、run 记录、heartbeat） |
| 产品兼容 | pytest + Playwright e2e | 2/2 PASS（e2e 8/8） |

---

## 7. 产品兼容性（原有口径未被改动）

- 原有产品只读层 `medradar/product/store.py`、统计口径（LQ 一致分母、完整季度窗口、
  PMA 原始批准 vs Supplement、未映射披露、企业归属不确定性）**一行未改**。
- 1.37 GB 科研库 `data/medradar.sqlite` **未写入**（观测账本是独立 SQLite 文件）。
- `web/` 改动均为**增补**：新增 `#/observatory` 路由、导航项、API 方法与样式；总览页新增
  `Newly Observed Evidence` 区块（无账本时显示诚实空状态，不填充虚构新闻）。
- 浏览器 e2e 8/8：企业研究、企业对比、技术趋势、证据追溯、研究助手（原 5 个）+ Live
  Observatory + 两个 390px 移动端检查；控制台 0 error。
- 研究实验室新增 Prospective Observation Registry（`#/lab` 内独立区块），原有 5 个研究
  卡片与详情接口保持不变（`/api/lab`、`/api/lab/{study_id}` 仍 200）。

---

## 8. 本轮发现并修复的缺陷（自查记录）

这些问题都是在**真实运行**中暴露、被修掉并有回归测试的，不属于“宣称已完美”：

1. **SEC 403**：默认 User-Agent 不含联系方式，SEC 按政策拒绝。修复：观测采集统一使用
   可配置的合规 UA（`MEDRADAR_SEC_UA`），并在文档中要求部署者填写自己的联系方式；
   失败被如实记录为 `source_failure`，修正后从检查点续跑成功。
2. **账本过滤查询未绑定参数**：`change_rows` / `change_facets` 的过滤分支漏绑参数，
   带筛选的 API 会抛 `sqlite3.ProgrammingError`。已修复并新增回归测试。
3. **结构漂移检测误报**：初版把单条记录的可选字段纳入指纹，正常数据每轮都“结构变化”。
   修复：指纹改为**来源级信封字段**（top-level 契约 + 必选模块存在性），并且每轮只在
   第一个 scope 检查一次。历史 6 条误报**保留**在 `source_failure`（只追加），
   当前告警状态在同一 `runtime_state` 审计条目（`structure_rebaseline`）说明下重建基线。
4. **“续跑收尾”被记成新成功同步**：从检查点收尾、未发请求的运行会把 `last_success_at`
   推到当前时间。修复：无请求的收尾只更新运行指针并写明“未发起新请求”，不伪造新鲜度。
5. **映射历史微秒碰撞**：同一微秒写入两条映射时 `INSERT OR IGNORE` 会丢一行。修复：
   `mapped_at` 单调递增。
6. **REMOVED 后重新出现**：内容未变却会重复写入同 hash 版本（违反唯一约束）。修复：
   恢复事件记录为 `UPDATED(changed_fields=["status"])` 且**不新增版本**，payload 链保持真实。
7. **Prospective Registry 冻结输入含可变展示字段**：`snapshot()` 的 `title` 是可变展示缓存，
   后续修订会让“冻结证据”发生字节变化。修复：冻结时从该版本对应的只追加
   `observation_change` 行取展示事实；测试证明后续写入后冻结文档字节/哈希不变。
8. **Europe PMC 时间语义**：`lite` 结果类型没有 `dateOfRevision`/摘要，无法满足
   `source_updated_at` 与修订检测。修复：默认 `resultType=core`，并在 payload 与文档中
   记录 `published_at` 实际取自 `firstIndexDate`（索引日期，不是网页可用时刻）。
9. **CI 离线自检在无 pytest 环境把“缺开发依赖”变成失败**：基线分支的
   `python -m medradar selftest` 用 unittest 发现并导入 pytest 风格测试模块，在只装
   `pip install .` 的 CI 环境触发 `ModuleNotFoundError: pytest`。修复：`selftest` 优先使用
   pytest；pytest 缺失时**显式跳过** pytest-only 模块并打印清单（绝不冒充通过），
   unittest 模块照常运行（实测 1074 个 unittest 全部通过、9 个 pytest-only 模块被明确跳过）。
   同时在 CI 的 `product-statistics` job 中新增观测站离线测试步骤。
10. **观测站 workflow 文件无效**：`MEDRADAR_SEC_UA` 默认值里含 `: `（`contact: …`）且未加引号，
   YAML 解析失败，GitHub 直接标记为 workflow file issue。修复：整段表达式加引号；
   本地用 YAML 解析验证 9 个步骤结构正确。

---

## 9. 明确不能宣称的事（与原任务书 §9 一致）

- **不是实时系统**：所有来源都是按声明周期轮询；页面文案写“轮询采集（非实时推送）”。
- **不是全球医疗技术全貌**：FDA 数据仅美国监管记录；SEC 仅美国披露；CT.gov 是注册库；
  Europe PMC 是文献索引。跨源不合并、不互相冒充独立验证。
- **真实修订/删除/失败事件在本轮生产账本中为 0**：机制已被合成层级与注入测试证明，
  但没有真实样本前不宣称“已抓到修订”。
- **映射不确定是显式展示的**：Europe PMC 的企业归属一律 `PENDING_REVIEW`（单位署名检索
  ≠ 已核实法人实体）；CT.gov 仍有 61 条申办方无法映射到名册企业（UNMAPPED，未当作零活动）。
- **无预测**：Prospective Observation Registry 只保存冻结的假设与到期评价，
  当前条目为**合成测试**并明确标注“合成测试（非真实前瞻结果）”；没有任何经验证的预测。
- **未做常驻部署**：只提供本地 `watch` 与 GitHub Actions 模板；未购买服务、未产生费用。
- **PR #12 未合并**：本分支基于已验收 HEAD 开发，Draft PR 待明确授权后再合并。

---

## 10. 复现命令

```bash
# 1) 查看真实账本与同步状态（本地已有本次采集结果）
python -m medradar observatory status
python -m medradar observatory sources

# 2) 再跑一轮真实增量（三源）
python -m medradar observatory sync --since-days 90

# 3) 时点回放：首次观察之前 vs 之后
python -m medradar observatory replay --as-of 2026-11-03T14:00:00Z
python -m medradar observatory replay --as-of 2026-11-03T23:00:00Z

# 4) 一致性 + 备份
python -m medradar observatory reconcile
python -m medradar observatory backup --dest data/backups

# 5) 本地持续轮询（Ctrl+C 停止）
python -m medradar observatory watch --interval-minutes 60

# 6) 页面
python -m medradar web --port 8787   # → http://127.0.0.1:8787/#/observatory

# 7) 测试与验收（分层）
python -m pytest tests/test_observatory_core.py tests/test_observatory_ctgov.py \
                 tests/test_observatory_europepmc.py tests/test_observatory_api.py \
                 tests/test_observatory_prospective.py -q
MEDRADAR_LIVE_TESTS=1 python -m pytest tests -q -k observatory
python scripts/observatory_acceptance.py --live --with-e2e
python scripts/observatory_evidence_bundle.py      # 重新生成本报告引用的证据 JSON
```

证据文件（`docs/observatory/evidence/`）：`09_final_ledger_evidence.json`
（账本全量摘要）、`10_replay_demo.json`（时点回放）、`11_sec_observation_timeline.json`
（SEC 逐条时间线）、`12/13/14/15_*`（增量轮次与结构稳定性）、`16_acceptance_report_full.json`
（24 项验收六层结果）、`17_product_e2e_report.json`（浏览器 8/8）。
