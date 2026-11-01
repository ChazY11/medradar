# MedRadar 数据清单与规模（DATA）

> 本文件分成两块：
> 1. **自动生成区**（下方 `stats` 标记之间）——由 `medradar.stats_cmd.data_stats` 生成，
>    运行 `python -m medradar stats --db data/medradar.sqlite` 或 `scripts/nightly.ps1` 会原地刷新；
> 2. **人工说明区**——口径、来源、覆盖窗口解释、已知缺口、复现方式。
>
> `data/` 与 `out/` 不入库（见 `.gitignore`），所以这里的数字只代表**生成时**的本地/CI 数据库，
> 不是仓库内容。最新一行增长记录见第四节。
>
> 口径：主库 `data/medradar.sqlite`（WAL 模式），schema 见 `docs/SCHEMA.md`。

<!-- stats:start -->

> **自动生成区**（`medradar.stats_cmd.data_stats` 快照，生成于 2026-10-31T05:33:25Z）。
> 请勿手工编辑本区块：运行 `python -m medradar stats --db data/medradar.sqlite`
> 或 `scripts/nightly.ps1` 即会原地刷新。

### 总览

| 指标 | 当前值 |
| --- | ---: |
| 事件 `events` | **375,378** |
| 事件日期范围 | 1966-12-14 → 2026-10-30 |
| 无日期事件 | 0 |
| 公司 `companies` | **89**（有 ticker 81，重点 43） |
| 赛道 `tracks` | **60** |
| 产品码 `product_codes` | **7,097**（已映射赛道 1,958，27.6%） |
| 价格 `prices` | **1,898,409 行 / 1,017 个 ticker**（2016-10-31 → 2026-10-30） |
| 信号 `signals` | **127** |
| 模拟盘 `paper_trades` / `paper_equity` | 38 / 236 |
| 实时通道 `live_alerts` / `live_equity` | 11 / 4 |
| 当前持仓 `positions` / 挂单 `paper_orders` | 0 / 0 |
| 运行记录 `runs` | 14 |
| LLM 缓存 `llm_verdicts` | 0 |
| 数据库体积 | **1.3 GiB**（1,368,469,504 B；WAL 0 B；SQLite 3.49.1） |

### 来源与类型

| `source` | `kind` | 条数 | 覆盖区间 |
| --- | --- | ---: | --- |
| `openfda_device_510k` | `510k` | 176,466 | 1976-07-15 → 2026-10-18 |
| `openfda_device_recall` | `device_recall` | 59,646 | 2002-11-01 → 2026-10-28 |
| `openfda_device_pma` | `pma` | 57,372 | 1968-10-09 → 2026-10-16 |
| `ctgov` | `trial` | 55,592 | 1999-10-19 → 2026-10-30 |
| `sec_edgar_corpus` | `8k_catalyst` | 20,976 | 2015-01-02 → 2026-10-30 |
| `openfda_drug_drugsfda` | `drug_approval` | 5,326 | 1966-12-14 → 2026-10-22 |

### 覆盖年份（按 `event_date`）

| 年份 | 事件数 |
| --- | ---: |
| 1966–2015（合计） | 240,494 |
| 2016 | 12,902 |
| 2017 | 13,308 |
| 2018 | 12,991 |
| 2019 | 12,778 |
| 2020 | 12,494 |
| 2021 | 11,706 |
| 2022 | 11,349 |
| 2023 | 11,895 |
| 2024 | 12,787 |
| 2025 | 12,170 |
| 2026 | 10,504 |

### 覆盖质量

| 指标 | 数值 |
| --- | ---: |
| 公司已归属 `company_key` | 132,293 (35.2%) |
| 赛道已归属 `track_id` | 196,542 (52.4%) |
| 产品码已归属 | 290,909 (77.5%) |
| 时间戳精度 | date 375,378 |
| 国家字段 Top 10（原始值，未归一化） | US 341,005 ｜ CN 5,747 ｜ DE 2,485 ｜ CA 2,247 ｜ KR 2,085 ｜ TW 1,926 ｜ GB 1,881 ｜ IL 1,685 ｜ MY 1,334 ｜ JP 1,267 |

### 价格覆盖

| 项 | 值 |
| --- | --- |
| 基准 SPY / XBI | 有 / 有 |
| 覆盖 ticker 数 | 1,017 |
| 日期范围 | 2016-10-31 → 2026-10-30 |

### 交易与回放

| 项 | 值 |
| --- | --- |
| 信号 `kind` 分布 | `drug_approval` 56 ｜ `recall_cluster` 41 ｜ `device_novel_code` 28 ｜ `trial_start` 2 |
| 信号日期范围 | 2025-11-20 → 2026-10-28 |
| 最近一次运行 | `collect_trials` @ 2026-10-30T19:19:48Z |

### 数据健康

- 查询失败：无
<!-- stats:end -->

## 一、口径与来源说明

所有来源统一落到一张 `events` 表（`source` + `kind` + `event_date` + `company_key` + `track_id`），
这样"谁的哪个方向在升温"只是一次 group-by；报告/事件研究/回放都只读这张表。

| `source` | 采集端 | 口径要点 |
| --- | --- | --- |
| `openfda_device_510k` | openFDA `/device/510k` | 按时间窗**全量**抓取（不按申请人过滤，否则漏子公司）；本地用 `CompanyRegistry.resolve(applicant)` 归属；决定日不冒充公开日 |
| `openfda_device_pma` | openFDA `/device/pma` | 含 supplement；`kind="pma"`；决定日不冒充公开日 |
| `openfda_device_recall` | openFDA `/device/recall` | 事件日取 `center_classification_date`（缺失回退 `report_date`）；只有真实 `event_date_posted` 才可作为公开日 |
| `ctgov` | ClinicalTrials.gov v2 | 只要 `INTERVENTIONAL`；事件日与公开日均取 `StudyFirstPostDate`（首次公示，避免前视） |
| `openfda_drug_drugsfda` | openFDA `/drug/drugsfda` | 仅 `ORIG` + `AP` 且 NDA/BLA（**排除 ANDA 仿制药**） |
| `sec_edgar_corpus` | SEC EDGAR 8-K 全文语料 | 公开时间取真实申报日；预申请、资格认定、临床暂停和拒绝受理独立分类 |
| `fda_advisory_committee` | FDA Advisory Committee Calendar | ⚠️ **experimental / 当前不可用**：日历 `<tbody>` 由 Drupal/DataTables 在浏览器端渲染，静态 HTML 只有表头；解析 0 行时采集器返回 `status="empty"`（页面结构变化时为 `"source_changed"`）并写 warning，**绝不报 `ok`**。“截至日期”优先从 `<time datetime>` 元素解析；事件标 `estimated`，不进交易研究 |
| `nmpa` | 本地 CSV 适配器 | 官网有 JS WAF 无法直接抓；详见缺口 1，未加载时报告显式写"不可用" |

时间口径：`event_date` 是事件发生日，`published_at` 是真实公开发布时间，`available_at` 是
**回测允许使用**的时点。`available_at` 只能来自显式公开时间或真实 `published_at`，不再回退到
`event_date`。只有真实 `available_at` 且 `timestamp_quality=datetime/date` 的记录能进入交易研究；
缺失、`estimated`、`unknown` 的记录仍可用于描述性行业分析，但必须排除并计数。
公开数据通常比事件日延迟入库，所以“事后看很准”的结论必须用 `available_at` 复核，见
`docs/ASSUMPTIONS.md`、`docs/RESEARCH.md`。

### 1.1 案例库价格口径（拆股/分红不变，v0.3.0 修复）

案例库的“价格反应”入场价用 `prices.adjusted_open`（= 原始 open × adj_close / close），
出场价用 `prices.adjusted_close`，两端统一在**调整后收盘价基准**上；因此持仓窗口内发生
拆股或分红时，`price_1d/5d/20d/60d` 与 `raw_*` 不会变成假 alpha。修复前入场缓存的是原始
open、出场却是调整 close，一次 2:1 拆股就会产生 ±50% 的假超额（这正是极端收益审计会
亮灯的原因之一）。回归测试见 `tests/test_cases.py::PriceBasisSplitTests`
（同一条价格路径“有/无 2:1 拆股”必须得到相同的超额收益）。
仓库里已提交的 `docs/CASES.md` 是修复前的生成快照，**未重算**；重新生成 `cases` 后才会反映新口径。

### 1.2 时间戳门槛只对**新采集**行生效（旧库需重建或降级）

`medradar.db.trading_timestamp_ok` 只允许 `timestamp_quality IN ('datetime','date')` 且
`available_at` 非空的行进入交易研究。但**已发布的 375,378 行快照是旧口径**：旧版
`upsert_events` 把 `published_at`/`available_at` 默认填成 `event_date` 并标 `date`，所以这些
历史行在当前闸门下的判定仍是“可交易”。**闸门是前瞻性的（prospective-only），不会追溯改写旧行**。

- 重新采集只对**刷新窗口内**的行 `INSERT OR REPLACE`，窗口外的历史行保持旧口径；且 REPLACE
  会重置 `first_seen_at`（首次入库时间，属于来源追溯信息），所以“再跑一次全量采集”不是修复手段。
- 在把历史行当作 trading / PIT（point-in-time）证据前，必须**重建**（从源站按真实公开时间重灌）
  或**显式降级**。`python -m medradar audit` 输出中的 `legacy_timestamp_promotions` 块会给出
  按来源统计的“会被降级行数”（只读；仓库**不会自动执行**降级）。
- 降级只改 `events.timestamp_quality`：描述性分析仍可用，交易研究排除；审计里
  `legacy_timestamp_promotions_demoted` 变为 PASS。降级后需重跑 `analyze` / `trade` /
  `replay` / `cases` 等下游阶段，已生成的 `docs/` 快照仍是旧口径。

一次性降级 SQL（**手工执行**、先备份 `data/medradar.sqlite`；本仓库不会自动运行）：

```sql
-- 0) 先看规模（只读）：哪些来源会被降级
SELECT source, COUNT(*) AS n FROM events
WHERE timestamp_quality = 'date'
  AND event_date <> ''
  AND date(published_at) = event_date
  AND date(available_at) = event_date
GROUP BY source ORDER BY n DESC;

-- 1) 备份后，把“决定日冒充公开日”的 openFDA 行降级为 estimated
UPDATE events
SET timestamp_quality = 'estimated'
WHERE timestamp_quality = 'date'
  AND event_date <> ''
  AND date(published_at) = event_date
  AND date(available_at) = event_date
  AND source IN ('openfda_device_510k','openfda_device_pma','openfda_device_recall','openfda_drug_drugsfda');

-- 2) 更严格的口径（可选）：把推断出来的 available_at 也清空，只保留描述性用途
-- UPDATE events SET available_at = NULL, timestamp_quality = 'estimated'
-- WHERE timestamp_quality = 'date' AND event_date <> ''
--   AND date(published_at) = event_date AND date(available_at) = event_date
--   AND source IN ('openfda_device_510k','openfda_device_pma','openfda_device_recall','openfda_drug_drugsfda');
```

`ctgov`（首次公示日）与 `sec_edgar_corpus`（真实申报日）的 `date` 是真实公开日期，**不在降级范围**。
降级后若因清空 `available_at` 使 `audit` 的 `availability_complete` 变红，是有意的强口径选择。

## 二、覆盖年份与窗口解释

- **器械与试验**：当前自动生成快照中，510(k) 自 1976 年起、PMA 自 1968 年起、召回自 2002 年起、
  临床试验自 1999 年起；这些区间描述事件历史，不代表每条记录都有真实公开时间。
- **药品批准**：openFDA drugsfda 自带历史，`ORIG` 批准日期可回溯到 1960 年代；
  当前快照最早事件为 1966 年（见自动生成区的日期范围）。
- **价格**：日线约 10 年（Yahoo chart API），1 分钟线只在回放中按需抓最近约 7 天、不落库。
- **当年数据未走完**：最新的年份列只到生成日，不能当作全年同比。
- 无日期事件单独计数（`undated`）：统计年份分布时它们不计入任何一年。

## 三、已知缺口（引用数据时必须一起引用）

1. **NMPA = 0 条**。官网查询页有 JS WAF（实测 HTTP 412/202），无法稳定抓取。需要人工/合作方
   导出 CSV 到 `data/nmpa_registrations.csv` 后运行 `collect --sources nmpa`；在此之前报告里的
   "中国空白度"显式显示*不可用（NMPA 数据未加载）*，**不会把 null 写成 0**。
   可选演示种子 `config/nmpa_demo_seed.csv` 仅在 `MEDRADAR_NMPA_DEMO=1` 时加载，且全程标记 demo。
2. **退市 / 被并购公司生存偏差**：公司表只保留当前存续主体，历史退市标的的价格与事件未补齐；
   事件研究/回放对此敏感，见 `docs/ASSUMPTIONS.md` 的"生存偏差"条目。
3. **1 分钟行情仅最近约 7 天**：更早成交只能用日线次日开盘，无法还原盘中滑点。
4. **历史公开时点不完整**：openFDA 510(k)/PMA 的决定日不是公开证据；没有真实公开时间的器械事件只用于描述性分析，
   不进入交易研究。AdCom 页面“截至日期”标为 `estimated`，同样排除。
5. **药品侧不含 ANDA 仿制药**：只保留 NDA/BLA 的 ORIG 批准，仿制药竞争不在覆盖范围。
6. **试验仅 `INTERVENTIONAL`**：观察性研究被有意排除，避免赛道热度失真。
7. **国家字段未归一化**：`country` 保留 openFDA 原文（`CHINA`/`CN`、`NETHERLANDS`/`NL` 并存），
   国家维度统计前需归并；当前报告不据此下结论。
8. **当前快照无 datetime 级时间戳**：自动生成区中的既有事件全为 `date`，无法做“发布后 1 小时”类研究；
   新 AdCom 事件使用 `estimated`，只用于前沿行业监测。旧库时间戳门槛是前瞻性的，历史行的降级/重建见 §1.2。
9. **公司匹配率偏低是设计选择**：长尾小申请人有意不匹配（宁漏不错），会低估小公司动量；
   提升方向是扩充 `config/companies_*.json` 别名，而不是降低置信阈值。
10. **模拟盘只做多**：无做空/借券费/并购逼平建模（v1 范围，见 `docs/ASSUMPTIONS.md`）。
11. **LLM judge 未启用**：无 key 时全部走启发式判分，校准结论见 `docs/CALIBRATION.md`。
12. **AdCom 采集当前 experimental / unavailable**：`https://www.fda.gov/advisory-committees/advisory-committee-calendar`
    的日历 `<tbody>` 由 Drupal/DataTables 在浏览器端渲染，服务器返回的静态 HTML 只有 `<thead>`（实测 2026-11-02，
    HTTP 200 / 31,219 B，解析 0 行）。采集器现在在 0 行时返回 `status="empty"`（表结构消失时为 `"source_changed"`）
    并写 warning，不会假报 `ok`；在 FDA 提供静态或 JSON 端点前，AdCom 事件为 0，frontier 不含咨询委员会信号。

## 四、增长记录

> 由 `scripts/nightly.ps1` 的 stats 阶段自动维护（`medradar.stats_cmd.append_growth_row`）：
> 同一天重复运行会**替换**当天行而不是重复追加，新日期追加在表格末尾。

<!-- growth:start -->
| 日期 | events | companies | tracks | product_codes | prices 行数 | DB 体积 | 备注 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2026-10-31 | 87517 | 89 | 60 | 7097 | 180535 | 328.5 MiB | nightly |
<!-- growth:end -->

手工追加（等价于 nightly 行为）：

```python
from medradar.db import DB
from medradar.stats_cmd import append_growth_row, data_stats, update_stats_markdown

with DB("data/medradar.sqlite") as db:
    stats = data_stats(db)
update_stats_markdown(stats, "docs/DATA.md")   # 刷新自动生成区
append_growth_row(stats, "docs/DATA.md", note="manual")
```

## 五、如何刷新 / 复现

```powershell
# 一条命令跑完整夜间流水线：collect → trade → replay → analyze → report → stats
powershell -ExecutionPolicy Bypass -File scripts/nightly.ps1

# 只统计，打印 JSON 到 stdout
python -m medradar stats --db data/medradar.sqlite

# 统计并原地刷新本文的「自动生成区」
python -m medradar stats --db data/medradar.sqlite --markdown docs/DATA.md

# 函数级复现
python -c "import json; from medradar.db import DB; from medradar.stats_cmd import data_stats; \
db = DB('data/medradar.sqlite'); print(json.dumps(data_stats(db), ensure_ascii=False, indent=1)); db.close()"
```

产出位置：

| 文件 | 内容 |
| --- | --- |
| `out/nightly.log` | 每个阶段的完整输出（UTF-8，含中文） |
| `out/nightly_status.json` | 各阶段退出码 / 耗时 / `core_failed` |
| `out/data_stats.json` | 最近一次 `data_stats` 的完整 JSON 快照 |
| `out/metrics.json` | 分析结果（报告输入） |
| `out/frontier.json` / `out/frontier.md` | 获批前公开信号、阶段/领域汇总与器械前沿报告 |
| `docs/DATA.md` | 本文（自动生成区 + 增长表由 nightly 更新） |

`scripts/nightly.ps1` 关键参数：`-Database`（默认 `data/medradar.sqlite`）、`-Months`（默认 24，
采集是窗口内增量 upsert）、`-Offline`（只用缓存）、
`-SkipCollect/-SkipTrade/-SkipReplay/-SkipAnalyze/-SkipReport/-SkipStats`、
`-NoDataMd`（只写 JSON，不改本文）。
采集/分析/报告任一核心阶段失败时脚本退出码为 1（其余阶段失败只记 WARN 继续）；
逐阶段状态永远写入 `out/nightly_status.json`——夜间任务不能因为一个价格源挂掉而整夜空白。

## 六、数据文件约定

| 路径 | 入库 | 说明 |
| --- | --- | --- |
| `data/medradar.sqlite` | 否 | 主库（WAL 模式）；schema 见 `docs/SCHEMA.md` |
| `data/*.sqlite` | 否 | 开发/验证库（dev_device、dev_drug、合成库等） |
| `config/*.json` | 是 | 公司/赛道/产品码/来源定义，人工维护的知识库 |
| `docs/metrics.json` | 是 | 已提交的报告快照（`medradar demo` 用它离线出报告） |
| `out/` | 否 | 运行产物（metrics、报告、回放、日志、stats 快照） |

## 七、一致性校验（CI 与测试）

- `.github/workflows/ci.yml` 的 `data-stats` job：用 `tests/fixtures/stats/mini_events.json` 现场构建
  合成 mini DB，**离线**跑 `data_stats` 的分布键/空库/年份边界测试（不联网、不碰 `data/`）。
- Windows job：`scripts/nightly.ps1` 统计阶段烟测（空库也不崩）。
- 单元测试：`tests/test_stats_cmd.py`（`python -m unittest tests.test_stats_cmd -v`），
  覆盖 events 年份/来源/kind/国家/精度分布、注册表与价格覆盖、容错（空库/缺表/缺文件/目录误传）、
  增长行与自动生成区的幂等追加。
