# 假设登记表（Assumptions Register）

> 本文件是 MedRadar 回放研究（`medradar/replay.py`）与事件研究 / 模拟交易的**口径合同**。
> 报告、HTML 回放页与 README 在解释任何收益数字时都必须引用它。
> 更新时间：2026-10-31（对应 `replay_v1` / `SCHEMA v1 §11`）。
>
> 标注含义：
> **已建模** = 代码里有明确实现，可审计；
> **未建模** = 已知偏差，代码不处理，报告必须写出方向；
> **免费数据做不到** = 不是实现取舍，而是公开免费数据本身不提供。

---

## 1. 成交时点（Entry timing）

| # | 项目 | 状态 | 参数 / 做法 | 出处与说明 |
|---|---|---|---|---|
| 1.1 | 决策时点 | 已建模 | 只用 `events.available_at`；缺失时依次回退 `published_at` → payload → `event_date` → `signal_date` | `db.py` 的时间列；SCHEMA §9：回测只使用 `available_at` |
| 1.2 | 日精度公开时间的语义 | 已建模 | `timestamp_quality='date'` 视为**当日 23:59:59 UTC** 才可用，因此首根可用 bar 一定落在下一交易日 | 当前 83,578 条历史事件全部是 `date` 精度（`data/medradar.sqlite` 实测）；把日期当成 00:00 会允许"当天开盘成交"，属于前视 |
| 1.3 | 1 分钟分支成交价 | 已建模 | 公开时点 `available_at` 落在最近 `intraday_days`（默认 7）天内且 Yahoo 1m 可得时：成交 = **公开时点之后第一根 1 分钟 bar 的开盘价**（bar 的 ts 严格大于 `available_at`，且 bar 时间 ≤ 回放 `now`）。日精度 `available_at` 按当日 23:59:59 UTC 处理，因此首根可用 bar 通常是下一交易日 09:30 ET。`includePrePost=false` 排除盘前盘后；无 bid/ask，bar open 只是假定成交价。窗口外/未请求 1m → 日线；1m 请求失败或无 bar → 日线并标记 `fallback` | `replay.py::_resolve_step` / `_first_intraday_fill`；`intraday_window_days`、`price_source_counts` 可在 replay JSON 中验证；单测 `test_intraday_fill_is_first_bar_after_public_moment` 等 |
| 1.4 | 日线分支成交价 | 已建模 | 公开日**之后第一个交易日**的开盘价（严格大于公开日期），且开盘时刻 ≤ `now`；窗口内有 1m 的 step 不走日线 | 与 `eventstudy.py` / `paper.py` "next-open entry" 同源；回放比 event study 早一天（event study 还要等 `signal_date`），已在 HTML 方法区写明 |
| 1.5 | 前视硬校验 | 已建模 | 每个成交在入账前断言 `fill_time > available_at`，违者记为 `lookahead_rejected` 并拒绝；`audit.fill_after_available` 只统计通过校验的成交 | `replay.py::_resolve_step`；单测 `test_future_public_time_is_rejected` 等 |
| 1.6 | 未来事件 | 已建模 | `available_at > now` 的信号进入时间轴但判定为 `SKIP / not_yet_public`，不成交 | 回放 `now` 可注入（默认 UTC 当前时刻） |
| 1.7 | 前视的剩余来源 | 未建模 | 信号规则本身（"首次出现"、召回聚集）在 `analyze.py` 中已改为只用 `available_at` 之前的历史；但回放使用的是**已落库的最终信号表**，若某次 analyze 规则改动包含未来信息，回放不会发现 | `docs/METHODS.md` §1、§7；ROADMAP "Point-in-time features" 仍未完成 |
| 1.8 | 基准相对收益 | 未建模 | 回放的 1/5/20 日是**原始收益**（方向调整），不含 SPY 超额；benchmark-relative AR 只在 `eventstudy.run_event_study` 中 | SCHEMA §7 `event_study` |

## 2. 滑点 / 价差 / 成本（Slippage & costs）

| # | 项目 | 状态 | 参数 / 做法 | 出处与说明 |
|---|---|---|---|---|
| 2.1 | 成本模型 | 已建模 | 三档**单边** bps：`(10, 25, 50)`；买入与卖出各收一次，往返扣 `2×bps`；`net_ret = gross_ret − 2×bps/10000` | 与 `paper.py` 的"20 bps + $1 **per fill**"同一口径；单测 `test_cost_tiers_are_strictly_monotone_and_arithmetic_is_exact` |
| 2.2 | 参数出处 | 已建模 | 10 bps ≈ 流动性好的大型器械/药企（价差 1–5 bps + 佣金 + 温和滑点）的乐观档；25 bps 基准；50 bps 压力档 | Frazzini, Israel & Moskowitz (2018) *Trading Costs*（大型股实际交易成本常 <10 bps 单边）；Almgren, Thum, Hauptmann & Li (2005) 市场冲击模型；`paper.py COST_BPS=20` 为团队既有基准 |
| 2.3 | bid/ask 价差 | 免费数据做不到 | 无买卖报价，无法做 half-spread / 有效价差分解；只能用 bps 档整体近似 | Yahoo chart 只有 OHLCV；NBBO 需要付费（TAQ / Polygon / IBKR）或交易所数据 |
| 2.4 | 市场冲击 / 规模 | 未建模 | 成交按名义额无冲击、无分批、无参与率上限；固定名义额（`capital × 20% × clamp(score,0.2,1)`）与单笔真实规模无关 | 免费行情无盘口深度；Almgren 模型需要 volume/ADV 与冲击系数，未接入 |
| 2.5 | 佣金 / 税费 / 融资 | 未建模 | 佣金并入 bps 档；无 SEC/TAF 费、无利息、无保证金 | 各券商差异大，v1 不模拟 |
| 2.6 | 盘前盘后 / 隔夜跳空 | 未建模 | 只使用常规交易时段 bar；盘前盘后成交与隔夜跳空不模拟 | Yahoo 1m 默认不含 pre/post；回放 `includePrePost=false` |
| 2.7 | 成本对成交选择的影响 | 已建模（明确假设） | 成本档**不影响**成交选择与仓位，只重估同一批成交 → 成本敏感性严格单调 | 固定名义额 + 成本只作用于收益；`replay.py::_summarize` |

## 3. 延迟（Publication lag）

| # | 项目 | 状态 | 参数 / 做法 | 出处与说明 |
|---|---|---|---|---|
| 3.1 | 公开时间优先 | 已建模 | 有 `timestamp_quality='datetime'` 时用精确时刻；`date` 按当日收盘后可用（见 1.2） | SCHEMA §8 实测延迟事实 |
| 3.2 | 采集延迟 | 未建模（回放假设在线） | 回放假设"公开时点当时已采集到"；真实批量采集的延迟见 §3.3。`meta.first_seen_lag_days` 会报告"首次采集 − 公开时间"的滞后分布 | 当前快照的 `first_seen_at` 多数为 2026-10-30（批量回填），中位滞后是几十到上千天；回放把它作为**已知乐观项**，不做 as-of-first-seen 切换 |
| 3.3 | 各源延迟（实测） | 免费数据做不到（只能缓解） | EDGAR 8-K 秒级；FDA 新闻 RSS 滞后数天；CT.gov 小时级；openFDA 器械约 12 天；FDA 在审队列无公开数据 | `docs/SCHEMA.md` §8 末尾 "延迟事实（实测 2026-10-31）" |
| 3.4 | 盘中/盘后判别 | 未建模 | 日精度数据无法知道消息是盘前、盘中还是盘后发布；统一按"当日收盘后"处理（最保守） | 需要新闻/8-K 精确时间戳，免费源不完整 |
| 3.5 | 交易日历 | 已建模 | 优先使用 `prices` 表中 SPY 的交易日；缺失时用候选标的日线日期并集 | `replay.py::_PriceBook.calendar`；非美上市标的（如 `SHL.DE`）与 SPY 日历不一致时用最近可用收盘 |

## 4. 借券 / 做空（Shorting & borrow）

| # | 项目 | 状态 | 参数 / 做法 | 出处与说明 |
|---|---|---|---|---|
| 4.1 | 默认只做多 | 已建模 | `direction=-1`（召回聚集）判定 `SKIP / short_not_supported`，不计入收益；仍会解析一个参考成交价并标记 `reference_only`（只用于时间轴审计，不入账）。`allow_short=True` 仅用于研究对照 | 与 `paper.py` v1 一致；HTML 顶部与 `method.long_only` 明示 |
| 4.2 | 借券费 / locate | 未建模 | 无借券费率、无 locate 可得性、无 recall 强制平仓；若开启 `allow_short` 也只按等名义额做空 | 借券费需券商/Prime Broker 数据（如 IBKR borrow rates、Markit Securities Finance），免费源不提供 |
| 4.3 | 做空逼平 / 并购 | 未建模 | 无 squeeze、无并购现金对价、无 delisting cash-out；仍持有到固定 20 日收盘 | 需要公司行动数据（CRSP/Compustat 或付费 vendor） |
| 4.4 | 免费替代指标 | 未建模 | FINRA 双周做空兴趣（short interest）是免费的，但它不是借券费，也不能当日交易 | FINRA Equity Short Interest 数据（双周、T+结算滞后） |

## 5. 生存偏差 / 公司行动（Survivorship & corporate actions）

| # | 项目 | 状态 | 参数 / 做法 | 出处与说明 |
|---|---|---|---|---|
| 5.1 | 股票池 | 免费数据做不到 | 只回放当前 watchlist 里有 ticker 的公司（`config/companies_*.json`）；退市、被并购、破产标的**不在样本**，长期多头收益被高估 | `data/medradar.sqlite` 的 `prices` 仅覆盖当前 74 个活跃代码；完整无生存偏差样本需要 CRSP 或付费数据 |
| 5.2 | 退市收益 | 未建模 | 标的在数据末端仍有价格时按 `end_of_data` 收盘平仓；真实退市可能 −100% 或现金对价 | `replay.py::_close_at_or_after` |
| 5.3 | 拆股 / 分红 | 已建模 | 收益一律用 `adj_close` 口径；开盘价按 `open × adj_close / close` 重标到同一基准 | `prices.adjusted_open/adjusted_close`；单测覆盖 |
| 5.4 | 并购逼平 | 未建模 | 与 4.3 相同：无并购/换股/现金对价建模 | 需要公司行动数据 |
| 5.5 | 停牌 / 涨跌停 / 流动性 | 未建模 | 假设所有 bar 可成交、无涨跌停、无停牌、无最小报价单位 | 免费数据无 halt 标记与盘口 |

## 6. 数据质量（Data quality）

| # | 项目 | 状态 | 参数 / 做法 | 出处与说明 |
|---|---|---|---|---|
| 6.1 | 时间质量分级 | 已建模 | `datetime` / `date` / `estimated` 可用；`unknown` **不进回放**，计入 `quality.excluded` | `db.py TIMESTAMP_QUALITIES`、SCHEMA §9；`replay.py::_resolve_available_at` |
| 6.2 | 重复信号 | 已建模 | 按 `(event_id, ticker, direction, kind, signal_date)` 去重，保留最新 `created_at`（并列取高分） | `analyze` 重跑会生成新 `signal_id`；当前快照 signals 表 127 行，重跑痕迹按上述键去重 |
| 6.3 | 1 分钟数据覆盖边界 | 免费数据做不到 | 仅最近约 **7 个自然日**（Yahoo `range=7d&interval=1m`，实测约 7 个交易日）；更早窗口只有日线；页面顶部固定声明。JSON 输出 `intraday_window_days` 与 `price_source_counts{1m,daily,fallback,missing,total}`；HTML「价格来源与 1 分钟边界」逐条列出哪些 step 用 1m、哪些用日线及原因。窗口外/离线**不请求** 1m；请求失败/无 bar → fallback 日线；`intraday_days=0` 强制日线 | 实测 2026-10-22 → 2026-10-30 共 2,640 根 1m bar；成品见 `out/replay_intraday/` 与 §11.6 |
| 6.4 | 1 分钟数据质量 | 未建模 | 不剔除异常 bar（错价、零成交、集合竞价外 bar）；缺失 bar 顺延到下一根；无成交量约束 | Yahoo 免费 1m 可能含异常；未与交易所对账 |
| 6.5 | 日线数据来源 | 已建模 | 先读 SQLite `prices`；缺失时用 `prices.fetch_ticker_rows` 临时回填到内存（**不写 DB**），受 60 次请求预算约束 | `replay.py::_PriceBook`；预算见 `meta.request_stats` |
| 6.6 | 价格缺口 | 已建模 | 平仓用"目标日收盘，缺失则向后找最近收盘"；1/5/20 日窗口缺失记为 `null`（不猜） | `_close_at_or_after`；与 event study "missing rather than guessed" 一致 |
| 6.7 | 事件日期 vs 采集日期 | 已建模 | `event_date` 是事件日，`as_of` 是采集日；回放**不用** `as_of` 当可用时间（否则历史回填全部推后到采集日） | `meta.first_seen_lag_days` 报告其差距；SCHEMA §6 |
| 6.8 | 公司名匹配 | 未建模（上游偏差） | 依赖 `CompanyRegistry` 别名匹配（≥0.82），漏配公司记为 `NULL` 而非猜测 | `docs/METHODS.md` §2；回放只处理已有 `company_key/ticker` 的信号 |
| 6.9 | 多重检验 | 未建模 | 回放逐笔展示信号，未做 Holm/Bonferroni 校正；不能把单条 t 值当显著性 | ROADMAP "Multiple-testing correction"；`research.multiple_testing` 为后续项 |
| 6.10 | 样本内外划分 | 未建模 | 回放窗口是用户给定区间，不是 walk-forward 样本外测试 | 报告中的 `research.sample_split` 是研究元信息，未接入回放校验 |
| 6.11 | `signals` 表为空时的回退 | 已建模 | 表为空时从 `events` 按 point-in-time 规则生成简易信号：首次产品码 / 药品获批 / 90 天召回聚集；信号日 = 公开日 + 1；只用于演示回放链路，不替代 `analyze` 的完整信号 | `replay.py::_auto_signal_rows`；`meta.counts.signal_source='events_fallback'` 可审计 |

## 7. 组合与回放机制（Portfolio mechanics）

| # | 项目 | 状态 | 参数 / 做法 | 出处与说明 |
|---|---|---|---|---|
| 7.1 | 仓位 | 已建模 | 每笔 `capital × 20% × clamp(score, 0.2, 1.0)`；固定名义额、不复利、不模拟现金余额约束 | `replay.py` `DEFAULT_POSITION_PCT`；score 来自 `signals.score` |
| 7.2 | 并发上限 | 已建模 | 单标的不叠加；同时最多 5 笔；被拒的步骤记为 `SKIP / already_open` 或 `no_capacity` | `_assign_capacity`；容量判断只用既定持有期，不用未来价格 |
| 7.3 | 持有期 / 平仓 | 已建模 | 成交后第 20 个交易日收盘平仓；数据不足则用最后可用收盘（`end_of_data`）；无止损、无移动止盈 | `DEFAULT_HOLD_DAYS=20`；与 `paper.py` 的 60 日/止损不同，回放是"事件后 1/5/20 日"研究窗口 |
| 7.4 | 权益 / 回撤 | 已建模 | 已实现口径：按平仓日累计 PnL；最大回撤为已实现权益曲线峰谷；**不含浮亏** | `_summarize`；页面与报告均标注"已实现" |
| 7.5 | 收益聚合 | 已建模 | 总收益 = ΣPnL / 初始资金；胜率 = 净收益 > 0 的笔数占比；平均持有 = 交易日差均值 | 单测 `test_cost_tiers...` 校准 |
| 7.6 | 复利 / 现金约束 | 未建模 | 固定名义额，不做资金曲线复利、不做"没钱就不开仓"的现金约束 | 与 7.1 一致；诚实标注 |

## 8. 参数与阈值速查

```text
capital                 默认 100,000（仅用于名义额与收益率分母）
costs_bps               单边成本档 (10, 25, 50)，往返 = 2 × bps
intraday_days           7（Yahoo 1m 免费覆盖约 7 个自然日；events/signals 模式同规则；0 = 强制日线）
price_source_counts     1m / daily / fallback / missing / total（replay JSON 顶层，可验证 1m 边界）
hold_days               20 个交易日
position_pct            0.20（× score 缩放，clamp 到 [0.2, 1.0]）
max_concurrent          5
max_requests            60（1m + 日线回填的硬预算）
source                  auto | signals | events（默认 auto）
max_steps               events 模式默认 400（目标 200–500），signals 模式不设上限
per_kind_limit          events 模式默认 150 条/类（可传 int 或 {kind: limit}）
event sampling          kind×year 分层；每 (kind, company, year) 首轮 ≤2 条
timestamp_quality       允许 datetime/date/estimated；unknown 剔除
dedupe key              (event_id, ticker, direction, kind, signal_date)
date-quality available  = 当日 23:59:59 UTC
```

## 9. 复现方式

```bash
cd D:\DEPPSKK\medradar
$env:PYTHONPATH="D:\DEPPSKK\medradar"
python -m medradar selftest          # 离线单测，含 tests/test_replay.py
```

```python
from medradar.db import DB
from medradar.replay import build_replay

with DB("data/medradar.sqlite") as db:
    payload = build_replay(db, "2025-11-01", "2026-10-31")  # -> out/replay/{replay.json,index.html}
```

多年历史（直接由 events 语料生成候选；CLI 透传 `--source/--max-steps` 由命令行层负责）：

```python
with DB("data/medradar.sqlite") as db:
    payload = build_replay(
        db, "2019-01-01", "2026-10-31",
        source="events", max_steps=400, per_kind_limit=150,
    )
```

访问 `out/replay/index.html` 即可逐步回放；`out/replay/replay.json` 是同一份机器可读数据（SCHEMA §11 契约）。

## 10. 已知偏差方向（读数字前先看）

1. **只做多 + 当前 watchlist** ⇒ 长期收益偏乐观（生存偏差、无借券费、无并购逼平）。
2. **日精度公开时间按收盘后处理** ⇒ 成交普遍晚半天到一天，短线反应被低估，但不会前视。
3. **1 分钟数据只有 7 天** ⇒ 近期事件的成交价更"真实"，历史事件只能用日线开盘。
4. **无 bid/ask、无冲击成本** ⇒ 实际可成交价通常差于回放价，成本 10 bps 档尤其乐观。
5. **回填数据的 `first_seen_at` 滞后** ⇒ 历史回放假设"当时在线采集"，实际做不到，属于已知乐观项。
6. **样本小、无多重检验校正** ⇒ 单条信号的回放只用于**个案审计**，不能据此宣称策略有效。

> 结论口径：回放是**可审计的研究工具与演示**，不是可部署策略。任何对外材料引用收益数字时，必须同时出现"模拟研究、非投资建议"以及上述偏差方向。

---

## 11. 多年回放的信号生成规则（`source="events"`）

`signals` 表只包含 `analyze` 最近窗口（约 8 个季度）的信号，无法回放多年历史。`source="events"`
直接读 `events` 事实表（当前快照 **312,566 行**，`event_date` 1966–2026），在 `replay.py` 内
**独立实现**一套 point-in-time 规则（不 import `analyze`），再把候选送进同一套"决策→成交→成本→HTML"
流水线。

### 11.1 规则与上限

| 信号 `kind` | 数据来源 | 规则（point-in-time） | 方向 / 分数 | 默认上限 |
|---|---|---|---|---|
| `device_novel_code` | `510k` / `pma` | `(company_key, product_code)` 在**全历史**中首次出现的日期落在回放窗口内 | +1 / 0.60 | 150 |
| `device_new_track` | `510k` / `pma` | `(company_key, track_id)` 全历史首次出现；若该事件已被 `device_novel_code` 选中则不重复 | +1 / 0.55 | 150 |
| `drug_approval` | `drug_approval` | 每条原始批准事件；要求 `company_key` 可映射到 ticker | +1 / 0.70 | 150 |
| `trial_start` | `trial` | `payload.phase` 含 `PHASE3`（先 SQL `LIKE '%PHASE3%'` 预筛，再逐条解析） | +1 / 0.50 | 150 |
| `recall_cluster` | `device_recall` | 同一公司 **90 天内第 2 起**召回起，每个 90 天窗口最多 1 条；计数只含当前事件之前的历史 | −1 / 0.70 | 150 |
| `8k_catalyst` | `8k_catalyst` | 标题 / `payload.buckets` 关键词定向（正/负词表见下）；`payload.backfill=true` 跳过；ticker 由公司表或标题括号解析 | ±1 / 0.60 | 150 |

**为什么不是 analyze 的精确复刻**：这些规则只用于"枚举可回放的事件"，分数是启发式；不复刻
`analyze` 的 THI/novelty boost，也不做组合信号合并。回放结果不能当作新的选股信号产品。

**8-K 方向词表（未建模语义理解）**：

* 负面：`did not meet` / `failed` / `missed` / `complete response letter` / `crl` / `refus` /
  `reject` / `terminated` / `discontinued` / `clinical hold` / `halt` / `safety` / `adverse` /
  `warning letter` / `recall` / `withdraw`；
* 正面：`fda approval` / `approved` / `clearance` / `met the primary` / `positive topline` /
  `positive results` / `positive data` / `breakthrough` / `fast track` / `priority review` /
  `orphan` / `granted` / `agreement` / `acquisition`；
* **同时命中正负词、或都不命中的标题直接丢弃**（不猜方向）。这是"未建模"的 NLP 判断，
  不是数据缺陷。

### 11.2 Point-in-time 与成交

1. 候选窗口按 **`available_at` 的日期** 落在 `[start, end]` 内；事件按 `available_at` 升序处理。
2. "首次出现"用 `MIN(avail)`（只统计 `event_date <= end` 的历史）⇒ 2019 年的"首次"不会被
   2024 年的数据改写；90 天召回簇只数当前事件之前的召回。
3. `timestamp_quality='unknown'` 的候选剔除；日精度 `available_at` 仍按当日 23:59:59 UTC 处理。
4. **成交价分支**：`available_at` 落在最近 `intraday_days`（默认 7）天内且 1m 可得时用
   1 分钟 bar 开盘（bar ts 严格晚于公开时点）；窗口外/离线直接日线（公开日后第一个交易日开盘，
   且开盘时刻 ≤ 回放 `now`）；1m 请求失败/无 bar → 日线并标记 `fallback`。
   `fill_time > available_at` 硬校验不变；`out/replay_intraday/` 是这一分支的成品验证（§11.6）。
5. 去重键：`(event_id, ticker, direction, kind, signal_date)`；每条 step 仍带原文链接。

### 11.3 上限与多样性抽样（避免 279k 级事件炸内存）

* 先用 SQL 聚合 + 索引逐条规则生成候选（不把 31 万行事件读进 Python 内存；device 首次出现用
  `GROUP BY company_key, product_code` 的 CTE，trial/recall 只取所需子集）。
* **每类上限** `per_kind_limit`：默认 150（可传 `int` 或 `{kind: limit}`）。
* **两阶段确定性抽样**（无随机数，可复现）：
  1. 每个 kind 内按 `(kind, year)` 分桶，每 `(kind, company, year)` 首轮最多 2 条，轮转取；
  2. 汇总后再按 `(kind, year)` 分桶、`(kind, company, year)` 首轮最多 3 条，轮转到 `max_steps`；
  3. 若因公司上限取不满，则按时间顺序放宽补齐。
* `max_steps`：`events` 模式默认 **400**（目标 200–500）；`signals` 模式默认不截断。
* 只有 **`prices` 表里已有 ticker** 的候选才入选（否则会生成大量 `no_price` 步骤）；
  8-K 标题解析出的 ticker 同样要求在 `prices` 中存在。

### 11.4 多年回放的额外偏差（在 §10 之外的）

| # | 项目 | 状态 | 说明 |
|---|---|---|---|
| 11.4.1 | 8-K ticker 映射 | 免费数据做不到 | 语料没有 CIK→ticker 映射（`companies.cik` 为空），只能用标题括号启发式；未匹配的 8-K 直接丢弃，不猜 |
| 11.4.2 | 8-K 方向 | 未建模 | 关键词词表不理解否定嵌套、程度与语境；模糊标题丢弃，覆盖率偏低（当前约 135 条可交易候选） |
| 11.4.3 | 事件宇宙完整性 | 免费数据做不到 | 多年窗口内的 trial/approval 数量是"当前快照中可解析"的数量，不是历史实时宇宙；退市/无价格公司不在样本（生存偏差同 §5） |
| 11.4.4 | 回填时点 | 未建模 | 与 §3.2 相同：假设公开时点当时已采集，`first_seen_at` 滞后仍是已知乐观项 |
| 11.4.5 | 1 分钟精度 | 免费数据做不到 | 多年窗口的绝大多数 step 只能日线开盘（1m 仅覆盖最近 ~7 天）；即使近期 step 用 1m，也只是"公开时点后第一根 bar 开盘"，无法还原真实逐笔成交与盘中滑点 |
| 11.4.6 | 8-K 原文语义 | 未建模 | 未使用 LLM 判定（成本/可复现性考虑）；`payload.backfill=true` 的告警一律不成交 |

### 11.5 实测（2026-10-31 快照，离线、只读 DB）

```text
调用：build_replay(db, "2019-01-01", "2026-10-31", source="events", max_steps=400)
语料：312,566 events（窗口内 510k 24,444 / pma 17,921 / trial 15,543 / recall 14,592 /
      drug_approval 1,068 / 8k_catalyst 1,046）
候选：3,755（novel 373 / new_track 3 / approval 294 / trial 2,598 / recall 352 / 8k 135）
每类上限后：738  →  全局 max_steps 后：400 steps（2019–2026 每年 44–61 步）
成交：129 笔入账（其余为做空参考价/容量上限/无未来价格跳过）；窗口跨度 7 年多，
      因此几乎全部为日线，仅最近 7 天内的事件可能用 1 分钟 bar（offline 验证为全 daily）
耗时：约 7–9 秒（offline=True，含 SQL 候选生成 + 400 步价格解析 + HTML/JSON 写出）
产物：验证时写入 out/replay_events/{replay.json,index.html}（避免覆盖 signals 模式的 out/replay；
      `out_dir` 默认仍是 out/replay）；HTML 约 1.0 MB，自包含无外链
```

复现（引擎级；命令行参数由 `__main__.py` 负责透传）：

```python
from medradar.db import DB
from medradar.replay import build_replay

with DB("data/medradar.sqlite") as db:
    payload = build_replay(
        db, "2019-01-01", "2026-10-31",
        source="events", max_steps=400, per_kind_limit=150,
    )
```

### 11.6 1 分钟边界成品（`out/replay_intraday/`，任务 P1）

为把"1m 只覆盖最近约 7 天"做成可验证成品，用一段覆盖边界两侧的近期窗口生成
`out/replay_intraday/{replay.json,index.html}`：

```text
窗口：2026-10-23 → 2026-10-31（8 个日历日；多取 1 天以便同时展示 7 天边界内外的 step）
调用：build_replay(db, "2026-10-23", "2026-10-31", source="events", max_steps=200)
steps：20
price_source_counts：{"1m": 12, "daily": 3, "fallback": 1, "missing": 4, "total": 20}
  - 1m 12：公开时点 10-26..10-29，成交 = 公开时点后第一根 1m bar 开盘（多数为下一交易日 09:30 ET）
  - daily 3：公开时点 10-23，已超出最近 7 天 1m 覆盖窗口 → 日线次日开盘
  - fallback 1：DBVTF 的 1m 响应无可用 bar → 日线降级并标记
  - missing 4：10-30 公开的事件在回放时点前没有下一交易日（no_future_price）
请求：13 次 Yahoo 请求（预算 60；DBVTF/OABIW 两个 ticker 的 1m 无可用 bar）
耗时：约 16 秒（冷缓存、在线 1m 请求；13 次缓存命中时约 10 秒）
自检：HTML「价格来源与 1 分钟边界」逐条列出 1m/日线 step 与原因，页面自包含无外链
```

该成品同时是 `price_source_counts` / `intraday_window_days` 两个 JSON 字段的可视化验收页面：
`price_source_counts` 恒满足 `1m + daily + fallback + missing = total = len(steps)`。

> 多年回放的定位仍是**研究工具**：它把十年事件摊开成可审计的时间轴，用来检查"规则在历史上
> 长什么样"，而不是证明规则能赚钱。样本内、未做多重检验校正、只做多、无借券费，结论口径同 §10。
