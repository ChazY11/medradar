# KIMI_AUDIT — MedRadar 独立审计报告

- **TASK_ID**: AUDIT-KIMI-001
- **AGENT**: Kimi Code（独立审计，未调用 Codex 或其他付费代理）
- **分支**: `research/independent-validation` @ `7a639f7`（v0.2.2）
- **日期**: 2026-11-01
- **性质**: 只读审计 + 报告。除本文件与测试证据外**零代码改动**；无 push/merge；无生产库操作。

---

## 0. 执行摘要（STATUS: PASS，附条件）

MedRadar 是本次审计见过的**双时态纪律最好的同类研究仓库之一**：`events` 表显式区分
`event_date / published_at / first_seen_at / available_at / timestamp_quality`（`medradar/db.py:73-79`），
回放引擎有硬前视断言（`replay.py:1583-1585`，`fill_time > available_at` 违者拒单并计数），
实时通道是真双时态（`live_alerts.event_time` + `detected_at`，`live.py:768-783`），
文档层（METHODS/ASSUMPTIONS/RESEARCH/SCHEMA）与方法实现高度一致。

但有**两个系统性缺口**使"回溯快照冒充历史可知性"在特定路径上仍然成立：

1. **写入路径默认塌缩**：所有 openFDA/NMPA/CT.gov 采集器只写 `as_of`（=采集日），
   `db.py:489-491` 默认 `available_at = published_at = event_date`、`timestamp_quality='date'`。
   一条 1976 年 PMA 记录今天回填，其回测时钟被断言为 1976 年当日可知（日精度），
   而诚实的"今天才首次见到"只躺在 `first_seen_at` 里，**没有任何消费方以它为门槛**
   （回放仅以 `_first_seen_lags` 诊断形式报告滞后，`replay.py:2222-2241`）。
2. **价格层完全单时态**：`prices` 无 `as_of/fetched_at`，`INSERT OR REPLACE`
   （`db.py:544-548`），Yahoo `adj_close` 在每次公司行动后**重述整条历史**
   （`prices.py:8-12, 187-214`），无冻结首写、无快照表、无退市处理（404 → `failed` 列表）。

测试基线健康：`pytest` 437 passed + 3 skipped + 12 subtests；官方入口
`python -m medradar selftest` = **440 tests OK (skipped=3)**，与 README 声明一致。

---

## 1. 审计范围与方法

| 项 | 覆盖 |
|---|---|
| 文档 | README(中/EN)、ROADMAP、docs/METHODS、SCHEMA、DATA、ASSUMPTIONS、RESEARCH、CALIBRATION（全文） |
| 数据层 | `db.py`(607 行全文)、`collect_device.py`、`collect_drug.py`、`clinical.py`、`nmpa.py`、`http.py`、`prices.py`、`scripts/backfill_*.py` |
| 分析层 | `analyze.py`、`eventstudy.py`、`replay.py`(关键路径)、`cases.py`、`calibration.py`、`stats.py`、`audit.py`、`live.py`、`corpus.py` |
| 测试/CI | 全部 18 个测试文件清点（431 个 test 方法）、`ci.yml`/`live.yml`/`weekly.yml`、`scripts/check_install.py`、`nightly.ps1`、`pyproject.toml` |
| 方法 | 三路并行只读深查（数据层/分析层/测试层）+ 主代理对全部高风险结论逐条独立复核行号 |

所有风险条目均给出 `文件:行号`；抽查过的关键行号已在审计中二次打开原文确认（见 §5 证据）。

## 2. 测试与 CI 证据

**命令与结果**（Python 3.12.10，本机 worktree，无网络、无 API key）：

```text
$ python -m pytest tests -p no:cacheprovider
437 passed, 3 skipped, 12 subtests passed in 13.84s        # 18 个文件 / 431 个 test 方法

$ python -m medradar selftest            # README 钦定入口
Ran 440 tests in 8.977s
OK (skipped=3)                           # 与 README "440 offline tests" 声明一致
```

证据文件：`docs/research/selftest_tail.txt`（selftest 尾部快照）。完整日志见本地会话任务输出。

**时态纪律相关测试（项目核心不变量，均有真断言而非 smoke）**：
- 回放无前视：`test_intraday_fill_is_first_bar_after_public_moment`、`test_daily_fill_is_next_session_open_not_event_day_open`、`test_future_public_time_is_rejected`、`test_unknown_timestamp_quality_is_excluded`、`test_weekend_public_date_fills_on_next_monday`（`tests/test_replay.py`）
- 事件研究：`test_signal_day_close_is_not_used_as_entry`（`tests/test_quant.py:336`）
- 实时通道：`test_stale_quote_blocks_entry`、`test_quote_before_news_is_rejected`、`test_cash_never_negative_after_slippage`、`test_interrupted_fill_rolls_back_and_is_not_masked`（`tests/test_live.py`）
- 校准回放：`ReplayJudge` 顺序无关、缺录音即 raise、禁硬编码判定、字节级复现（`tests/test_stats.py:524-910`）

**CI**：`ci.yml` 三 job × py3.10/3.11/3.12 + windows，全程零网络（连 demo 都用提交内快照）；
`weekly.yml` 联网重建（openFDA 免费配额）；`live.yml` 仅手动触发（cron 被有意注释，附理由）。
`test_release.py` 守卫版本一致与 README 测试数区间。

## 3. 现有时间设施 vs 双时态要求（对照表）

| 时态轴 | 要求 | 现状 | 判定 |
|---|---|---|---|
| 有效时间 valid time | 事件发生日 | `event_date`（各源取决策日/StudyFirstPostDate/批准日，选择理由文档化，`clinical.py:1-9`） | ✅ 良好 |
| 公开可得时间 public availability | 信息真正可被公众获取的时点 | `available_at`，但 openFDA/NMPA/CT.gov 路径默认 = `event_date`（`db.py:491`），openFDA 实际滞后 2–12 天（METHODS §9.6 自认）；仅 8-K 语料路径显式置 `available_at = filed`（`__main__.py:658-660`） | ⚠️ **名义正确、写入塌缩** |
| 采集/知识时间 ingestion time | 系统首次得知的时点 | `first_seen_at`，但 (a) 回填即今天（诚实），(b) `INSERT OR REPLACE` 重采集会**静默重置**它（`db.py:490,519`），(c) 无任何消费方以它设门槛 | ⚠️ **存在但脆弱且被忽视** |
| 快照语义 as-of | 任一历史时刻 T 可重建"T 时知道什么" | **不具备**：无版本表、无 append-only 日志、回填用今天 `as_of` 覆盖全部历史窗口（`backfill_device.py:180`）、`as_of` 是单行最后写入值 | ❌ **缺失（TKG 的核心缺口）** |
| 价格的双时态 | 成交价只能用 T 时可得行情 | 单态 `prices` 表，公司行动后历史被重述；生存偏差仅"标记"不"建模" | ❌ **最薄弱层** |

**结论**：四列时态模型是优秀骨架，但只有 live 通道和 8-K 语料真正落地；
批处理事件与价格两层不满足"回溯快照不得冒充历史可知性"的验收标准。

## 4. 风险清单（按严重度；行号已抽查）

### 高

- **H1 `available_at` 默认塌缩 + 质量标级虚高** — `db.py:489-494`（默认 `available_at=event_date, quality='date'`）；
  `collect_device.py:679-694`、`collect_drug.py:153-160`、`nmpa.py:201-222`、`clinical.py:217-234`（采集器均不设 `published_at/available_at`）。
  后果：回放/事件研究时钟从决策日+1 起跳，比真实可获知早 2–12 天（openFDA 滞后）。
  缓解（日内扩张到 23:59:59、`_first_seen_lags` 披露）只吸收同日误差，不吸收跨日源滞后；
  且被默认标成 `'date'`（源观测）而非 `'estimated'`（推断），下游无法区分。
- **H2 价格层单时态 + 历史重述 + 无退市建模** — `db.py:86-96,544-548`；`prices.py:8-18,187-214,291-293,343-345`。
  `adj_close` 重述使同一回测在拆股前后跑出不同历史成交价；退市票 404 静默落入 `failed`。
  与 `cases.py:296-305,324` 结合产生**价格基 bug（H3）**。

### 中

- **H3 `cases.py` 混用原始开盘价与复权收盘价** — `_load_price_cache` 把 `close` 映射为 `adj_close`，
  入场用原始 `open`（`cases.py:296-305,324,336`）。`prices.py:8-12` 明文禁止此混用，
  `prices.adjusted_open`（`prices.py:71-85`）存在但未被调用 → 持有期内任何拆股/分红产生虚假收益，
  直接污染对外发布的 2,384 案例库与 "Holm 12-test family" 结论的输入。
- **H4 `eventstudy.run_event_study` 无 winsorize、无多重检验校正** — `eventstudy.py:357-374`。
  原始肥尾 AR 直接进 block bootstrap，每 kind×horizon 一个 p 值但族内不校正；
  README 的 "Holm over the 12-test family" 仅指 `cases.py`。若报告引用 eventstudy 的 p 值即构成未校正推断。
- **H5 回放内嵌事件研究同样未校正且只统计多头** — `replay.py:1755-1793`（标了 `in_sample: true`，`replay.py:2172`，
  但方法与 cases.py 不对称，存在被断章引用风险）。
- **H6 校准 n=25 无置信区间 + 同批样本既校准生产 judge** — `calibration.py:455-585`；"类型准确率 1.00" 的二项宽度巨大；
  阈值（`HIGH_MATERIALITY=0.5`、`POSITION_FLOOR=0.20`）是否对照该样本调过，代码无防护，仅靠自律。
  fixture 自承 `raw_source="reconstructed_from_parsed_verdict"`，不构成端点独立验证（RESEARCH §7.6 已诚实披露）。

### 低 / 次要

- **L1** `timestamp_quality` 写入默认 `'date'`（`db.py:492`）vs 读取默认 `'estimated'`（`analyze.py:90`）vs 回放逐条推断（`replay.py:288-308`）——同一行在不同路径质量等级不一致。
- **L2** `signals.signal_id` 为位置序号（`analyze.py:677`），重跑重编号，`created_at` 被 `INSERT OR REPLACE` 改写；信号溯源跨 run 不稳定（`db.py:561-589`）。
- **L3** `audit.py:44-48,95-110` 缺 `available_at ≥ event_date`、缺 `available_at` 未来值、缺 `available_at − event_date` 滞后分布检查——H1 的天然侦测点未设防。
- **L4** 样本切分键为 `event_date` 而非 `available_at`（`stats.py:1021` + `analyze.py:818`）：回填行可在阶段边界处把"后可知"事件放进前一折。
- **L5** `analyze.py:1071` 对 `signal_date` 的 metrics.json 文字定义（"event_date + 1"）落后于代码（`available_at + 1`，`analyze.py:679`）——文档保守方向正确但表述过期。
- **L6** `http.py` 缓存不记抓取时间；`fetched_at` 盖在 DB 写入时刻而非 HTTP 时刻（`http.py:96-99`）。
- **L7** 次要不一致：`ASSUMPTIONS.md §5.1` 称 prices 仅覆盖"74 个活跃代码"，而 `DATA.md` 自动生成区显示 1,017 个 ticker——文档间过期，需复核口径。
- **L8** 回放消费**已物化的 signals 表**：analyze 规则若引入未来信息，回放不可见（`ASSUMPTIONS.md` 1.7 已自认，属已知局限）。

### 做得对、应当保留的

四列时间模型与 SCHEMA §6.1 契约；日精度扩到当日 23:59:59 UTC（`replay.py:304-305`）；
`fill_time > available_at` 硬拒单 + 公开计数（`replay.py:1583-1585,2203-2206`）；
live 通道 `quote_before_news` 守卫、backfill 永不成交（`live.py:530-535,843-845`）；
现金守恒不变量（`live.py:602-633`）；8-K `available_at=filed` 源接地写法（`__main__.py:658-660`）；
`prior_track_count` 真 PIT（bisect，`analyze.py:649-665`，且注释承认旧版曾泄漏并已修）；
`StudyFirstPostDate` 作为最早公开日（`clinical.py:1-9`）；校准的指纹/重放/禁硬编码纪律；
`cn_gap` "unavailable ≠ 0" 诚实原则；G<2 时拒报区间而非伪造（`stats.py:499-554`）。

## 5. 研究空白（research gaps）

1. **无 as-of 快照能力**（H1/H2 之根）：无法回答"2021-06-01 时本系统知道什么"。
   需要 append-only 事件日志（或 `events_history(event_id, valid_from, tx_time)` 双时态表）
   与 `prices_asof(ticker, date, fetched_at)` 快照表；这是 TKG 化（见 §7）的前提。
2. **公开可得时间的源接地缺失**：openFDA 无发布日字段，需要以 FDA 网站/press/rss 的独立滞后测量
   为 `available_at` 提供 `estimated` 等级的经验分布（按 kind 分层的 lag 先验），而非一律当日。
3. **价格基统一**（H3）：全部下游统一 `adjusted_open` 口径；补拆股/分红敏感性分析。
4. **统计口径不一致**（H4/H5）：eventstudy/replay 对齐 cases.py 的 winsorize+Holm，或在报告中显式降级标注。
5. **校准扩样**：n=100、双人标注 + Cohen's κ、真实端点重跑（ROADMAP 已列，属"需 key"项）。
6. **退市/生存偏差只标不建**：需要 delisting 事件建模（现金对价/−100% 两档敏感性）才算闭合。
7. **多重检验之外的探索性偏差**（RESEARCH §8.9 已自认）：协议只能约束已登记家族。

## 6. 数据集 / 基准计划（proposal）

- **D1 双时态基准库（合成，离线）**：构造含 6 类陷阱的迷你 SQLite：
  ① `available_at < first_seen_at`；② 同一 `event_id` 两次采集内容不同（源修正）；
  ③ 日精度 vs datetime 精度混合；④ `quality='unknown'`；⑤ 拆股中途的价格序列；
  ⑥ 退市 ticker。作为 TKG/PIT 验收测试的固定夹具，进 `tests/fixtures/`。
- **D2 滞后先验数据集**：对每 kind 抽样事件，记录 openFDA `event_date` 与 FDA 官网可检索日的差，
  形成 lag 经验分布，供 `available_at` 的 `estimated` 标级使用（需联网一次，结果固化为 fixture）。
- **D3 案例库复算基准**：修复 H3 后对 2,384 案例全量复算，输出 before/after 收益差分布
  （预期：接近拆股/分红日期的案例子集变动最大），作为回归基准。
- **B1 报告指标指纹**：`run_calibration` 已有 `metrics_sha1` 先例；扩展为全链路
  （analyze → replay → report）的确定性指纹，任何时态语义改动必改指纹。

## 7. 拟议独立 TKG / PIT 验收测试（先写测试、再改实现）

> 定位：这些是**应当新增且当前会失败**的验收测试（先红后绿），不在本次审计中实现。

1. `test_available_at_never_predates_first_seen`：全表断言 `available_at ≥ first_seen_at::date`；
   当前快照必然失败（回填即反例）→ 驱动 H1 修复（引入 lag 先验或 as-of 门槛开关）。
2. `test_first_seen_at_is_monotone_across_reingest`：同一 event 两次 upsert，`first_seen_at` 不得变大；
   当前因 `INSERT OR REPLACE` 失败 → 驱动 append-only/`COALESCE(first_seen_at, excluded)` 修复。
3. `test_replay_supports_asof_clock`：`build_replay(..., clock="first_seen")` 模式下，任何 fill 必须
   满足 `fill_time > first_seen_at`；与 `clock="available"`（默认）结果对比并输出差值报告。
4. `test_prices_freeze_on_first_write`：重复抓取含拆股的合成行情，历史 bar 的 `adj_close` 不得被
   后续重述改变；`prices_asof` 查询 `as_of=T` 必须返回 T 时刻的可见序列。
5. `test_delisted_ticker_is_modeled_not_dropped`：退市票必须产出 delisting 事件（两档敏感性），
   不得静默落入 `failed`。
6. `test_case_returns_use_adjusted_open`：构造持有期内拆股案例，案例收益必须等于复权口径收益；
   当前因 H3 失败。
7. `test_eventstudy_family_is_corrected`：`run_event_study` 输出必须带 Holm 校正族（≥ kind×horizon 个 look）。
8. `test_audit_flags_temporal_anomalies`：`audit.py` 输出必须包含 `available_at<event_date`、
   `available_at>today`、`available_at−event_date` 滞后分布三项检查（L3）。

## 8. 建议首批任务（good first tasks，按 ROI 排序）

1. **H3 修复（小而急）**：`cases.py` 改用 `prices.adjusted_open`；加 D1-⑤ 与测试 6；复算 D3。估计 <1 天，直接提升对外结论可信度。
2. **L3+H1 侦测（纯增量）**：`audit.py` 加三条时态异常检查（测试 1/8），先让风险"可见"，再决定修复策略。半天。
3. **L2 信号溯源稳定化**：`signal_id` 改内容哈希（仿 `llm_verdicts.content_hash`），upsert 保留最早 `created_at`。
4. **H1 方案设计**（需决策）：三选一并写入 SCHEMA：a) `available_at = event_date + kind 分层 lag 先验`，quality 改 `'estimated'`；b) 回放增加 `clock="first_seen"` 模式（保守回放）；c) 全量双时态表（重）。建议先做 a+b。
5. **H2 最小闭合**：`prices` 加 `fetched_at` 列 + 首写冻结（`INSERT ... ON CONFLICT DO NOTHING` 或快照表），加测试 4/5。
6. **H4/H5 口径对齐**：eventstudy/replay 接 `stats.multiple_testing` + winsorize 开关。
7. 文档收敛：L5、L7 两处过期定义/数字刷新。

## 9. 证据索引

| 证据 | 位置 |
|---|---|
| selftest 快照（440 OK） | `docs/research/selftest_tail.txt` |
| pytest 全量输出 | 本地会话后台任务日志（437 passed, 3 skipped, 12 subtests, 13.84s） |
| 关键行号抽查 | `db.py:489-494,544-548`；`collect_device.py:679-694`；`cases.py:296-336`；`analyze.py:679,1071`；`replay.py:1583-1585,2222-2241`；`live.py:530-535`；`prices.py:8-18,71-85` |
| 环境 | Python 3.12.10 / pytest 9.1.1 / Windows，零网络零凭证 |

> 审计限制：本 worktree 无 `data/medradar.sqlite`（主 worktree 只读），故 375k 行真实数据的
> 分布级验证（如 H1 的实际滞后分布、L7 的 74 vs 1017）留待有库环境复核；本报告的 H1 判定
> 依据的是写入路径的必然行为而非数据抽样，不受影响。
