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
| 1.3 | 1 分钟分支成交价 | 已建模 | 公开时点之后**第一根 1 分钟 bar 的开盘价**；bar 时间必须晚于公开时点、且不晚于回放时点 | Yahoo `range=7d&interval=1m`；1m bar 的 open 是区间第一笔成交，不是 NBBO |
| 1.4 | 日线分支成交价 | 已建模 | 公开日**之后第一个交易日**的开盘价（严格大于公开日期） | 与 `eventstudy.py` / `paper.py` "next-open entry" 同源；回放比 event study 早一天（event study 还要等 `signal_date`），已在 HTML 方法区写明 |
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
| 4.1 | 默认只做多 | 已建模 | `direction=-1`（召回聚集）判定 `SKIP / short_not_supported`，不计入收益；`allow_short=True` 仅用于研究对照 | 与 `paper.py` v1 一致；HTML 顶部与 `method.long_only` 明示 |
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
| 6.2 | 重复信号 | 已建模 | 按 `(event_id, ticker, direction, kind, signal_date)` 去重，保留最新 `created_at`（并列取高分） | `analyze` 重跑会生成新 `signal_id`；当前库 120 行信号去重后 98 条 |
| 6.3 | 1 分钟数据覆盖 | 免费数据做不到 | 仅最近约 7 天（Yahoo `range=7d&interval=1m`，实测返回约 7 个交易日）；更早窗口只有日线；页面顶部固定声明 | 实测 2026-10-22 → 2026-10-30 共 2,640 根 1m bar |
| 6.4 | 1 分钟数据质量 | 未建模 | 不剔除异常 bar（错价、零成交、集合竞价外 bar）；缺失 bar 顺延到下一根；无成交量约束 | Yahoo 免费 1m 可能含异常；未与交易所对账 |
| 6.5 | 日线数据来源 | 已建模 | 先读 SQLite `prices`；缺失时用 `prices.fetch_ticker_rows` 临时回填到内存（**不写 DB**），受 60 次请求预算约束 | `replay.py::_PriceBook`；预算见 `meta.request_stats` |
| 6.6 | 价格缺口 | 已建模 | 平仓用"目标日收盘，缺失则向后找最近收盘"；1/5/20 日窗口缺失记为 `null`（不猜） | `_close_at_or_after`；与 event study "missing rather than guessed" 一致 |
| 6.7 | 事件日期 vs 采集日期 | 已建模 | `event_date` 是事件日，`as_of` 是采集日；回放**不用** `as_of` 当可用时间（否则历史回填全部推后到采集日） | `meta.first_seen_lag_days` 报告其差距；SCHEMA §6 |
| 6.8 | 公司名匹配 | 未建模（上游偏差） | 依赖 `CompanyRegistry` 别名匹配（≥0.82），漏配公司记为 `NULL` 而非猜测 | `docs/METHODS.md` §2；回放只处理已有 `company_key/ticker` 的信号 |
| 6.9 | 多重检验 | 未建模 | 回放对 98 条信号逐笔展示，未做 Holm/Bonferroni 校正；不能把单条 t 值当显著性 | ROADMAP "Multiple-testing correction"；`research.multiple_testing` 为后续项 |
| 6.10 | 样本内外划分 | 未建模 | 回放窗口是用户给定区间，不是 walk-forward 样本外测试 | 报告中的 `research.sample_split` 是研究元信息，未接入回放校验 |

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
intraday_days           7（Yahoo 1m 免费覆盖约 7 天）
hold_days               20 个交易日
position_pct            0.20（× score 缩放，clamp 到 [0.2, 1.0]）
max_concurrent          5
max_requests            60（1m + 日线回填的硬预算）
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

访问 `out/replay/index.html` 即可逐步回放；`out/replay/replay.json` 是同一份机器可读数据（SCHEMA §11 契约）。

## 10. 已知偏差方向（读数字前先看）

1. **只做多 + 当前 watchlist** ⇒ 长期收益偏乐观（生存偏差、无借券费、无并购逼平）。
2. **日精度公开时间按收盘后处理** ⇒ 成交普遍晚半天到一天，短线反应被低估，但不会前视。
3. **1 分钟数据只有 7 天** ⇒ 近期事件的成交价更"真实"，历史事件只能用日线开盘。
4. **无 bid/ask、无冲击成本** ⇒ 实际可成交价通常差于回放价，成本 10 bps 档尤其乐观。
5. **回填数据的 `first_seen_at` 滞后** ⇒ 历史回放假设"当时在线采集"，实际做不到，属于已知乐观项。
6. **样本小、无多重检验校正** ⇒ 单条信号的回放只用于**个案审计**，不能据此宣称策略有效。

> 结论口径：回放是**可审计的研究工具与演示**，不是可部署策略。任何对外材料引用收益数字时，必须同时出现"模拟研究、非投资建议"以及上述偏差方向。
