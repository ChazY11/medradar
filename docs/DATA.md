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

> **自动生成区**（`medradar.stats_cmd.data_stats` 快照，生成于 2026-10-30T20:10:17Z）。
> 请勿手工编辑本区块：运行 `python -m medradar stats --db data/medradar.sqlite`
> 或 `scripts/nightly.ps1` 即会原地刷新。

### 总览

| 指标 | 当前值 |
| --- | ---: |
| 事件 `events` | **363,177** |
| 事件日期范围 | 1966-12-14 → 2026-10-30 |
| 无日期事件 | 0 |
| 公司 `companies` | **89**（有 ticker 81，重点 43） |
| 赛道 `tracks` | **60** |
| 产品码 `product_codes` | **7,097**（已映射赛道 1,958，27.6%） |
| 价格 `prices` | **1,284,001 行 / 674 个 ticker**（2016-10-31 → 2026-10-30） |
| 信号 `signals` | **127** |
| 模拟盘 `paper_trades` / `paper_equity` | 38 / 236 |
| 实时通道 `live_alerts` / `live_equity` | 11 / 4 |
| 当前持仓 `positions` / 挂单 `paper_orders` | 0 / 0 |
| 运行记录 `runs` | 14 |
| LLM 缓存 `llm_verdicts` | 0 |
| 数据库体积 | **1.2 GiB**（1,294,217,216 B；WAL 0 B；SQLite 3.49.1） |

### 来源与类型

| `source` | `kind` | 条数 | 覆盖区间 |
| --- | --- | ---: | --- |
| `openfda_device_510k` | `510k` | 176,466 | 1976-07-15 → 2026-10-18 |
| `openfda_device_recall` | `device_recall` | 59,646 | 2002-11-01 → 2026-10-28 |
| `openfda_device_pma` | `pma` | 57,372 | 1968-10-09 → 2026-10-16 |
| `ctgov` | `trial` | 55,592 | 1999-10-19 → 2026-10-30 |
| `sec_edgar_corpus` | `8k_catalyst` | 8,775 | 2015-01-02 → 2026-10-30 |
| `openfda_drug_drugsfda` | `drug_approval` | 5,326 | 1966-12-14 → 2026-10-22 |

### 覆盖年份（按 `event_date`）

| 年份 | 事件数 |
| --- | ---: |
| 1966–2015（合计） | 239,413 |
| 2016 | 11,839 |
| 2017 | 12,207 |
| 2018 | 11,808 |
| 2019 | 12,257 |
| 2020 | 11,488 |
| 2021 | 10,665 |
| 2022 | 10,269 |
| 2023 | 10,862 |
| 2024 | 11,724 |
| 2025 | 11,108 |
| 2026 | 9,537 |

### 覆盖质量

| 指标 | 数值 |
| --- | ---: |
| 公司已归属 `company_key` | 131,526 (36.2%) |
| 赛道已归属 `track_id` | 196,542 (54.1%) |
| 产品码已归属 | 290,909 (80.1%) |
| 时间戳精度 | date 363,177 |
| 国家字段 Top 10（原始值，未归一化） | US 328,804 ｜ CN 5,747 ｜ DE 2,485 ｜ CA 2,247 ｜ KR 2,085 ｜ TW 1,926 ｜ GB 1,881 ｜ IL 1,685 ｜ MY 1,334 ｜ JP 1,267 |

### 价格覆盖

| 项 | 值 |
| --- | --- |
| 基准 SPY / XBI | 有 / 有 |
| 覆盖 ticker 数 | 674 |
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
| `openfda_device_510k` | openFDA `/device/510k` | 按时间窗**全量**抓取（不按申请人过滤，否则漏子公司）；本地用 `CompanyRegistry.resolve(applicant)` 归属 |
| `openfda_device_pma` | openFDA `/device/pma` | 含 supplement；`kind="pma"` |
| `openfda_device_recall` | openFDA `/device/recall` | 事件日取 `center_classification_date`（缺失回退 `report_date`） |
| `ctgov` | ClinicalTrials.gov v2 | 只要 `INTERVENTIONAL`；事件日取 `StudyFirstPostDate`（最早公开可得，避免前视） |
| `openfda_drug_drugsfda` | openFDA `/drug/drugsfda` | 仅 `ORIG` + `AP` 且 NDA/BLA（**排除 ANDA 仿制药**） |
| `nmpa` | 本地 CSV 适配器 | 官网有 JS WAF 无法直接抓；详见缺口 1，未加载时报告显式写"不可用" |

时间口径：`event_date` 是事件发生日，`available_at` 是**回测允许使用**的时点（`published_at` →
`event_date` 回退链，见 `medradar/db.py`）。公开数据通常比事件日延迟 2–12 天入库，
所以"事后看很准"的结论必须用 `available_at` 复核，见 `docs/ASSUMPTIONS.md`、`docs/RESEARCH.md`。

## 二、覆盖年份与窗口解释

- **器械侧（510(k) / PMA / 召回）+ 临床试验**：collector 按约 10 年窗口抓取，最早约 2016 年 10 月；
  更早的器械历史尚未回填（见缺口 4）。因此按年看，2016 年只有 Q4 的数据量。
- **药品批准**：openFDA drugsfda 自带历史，`ORIG` 批准日期可回溯到 1960 年代；
  这解释了"最早事件"远早于 2016（见自动生成区的日期范围）。
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
4. **器械侧 10 年窗口**：510(k)/PMA/召回/试验均自 2016 年 10 月起，更早器械历史未回填；
   药品批准因 drugsfda 自带历史而回溯很深（两边不可比）。
5. **药品侧不含 ANDA 仿制药**：只保留 NDA/BLA 的 ORIG 批准，仿制药竞争不在覆盖范围。
6. **试验仅 `INTERVENTIONAL`**：观察性研究/器械早期可行性研究被有意排除，避免赛道热度失真。
7. **国家字段未归一化**：`country` 保留 openFDA 原文（`CHINA`/`CN`、`NETHERLANDS`/`NL` 并存），
   国家维度统计前需归并；当前报告不据此下结论。
8. **无 datetime 级时间戳**：`timestamp_quality` 全为 `date`，无法做"发布后 1 小时"类研究。
9. **公司匹配率偏低是设计选择**：长尾小申请人有意不匹配（宁漏不错），会低估小公司动量；
   提升方向是扩充 `config/companies_*.json` 别名，而不是降低置信阈值。
10. **模拟盘只做多**：无做空/借券费/并购逼平建模（v1 范围，见 `docs/ASSUMPTIONS.md`）。
11. **LLM judge 未启用**：无 key 时全部走启发式判分，校准结论见 `docs/CALIBRATION.md`。

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
