# MedRadar · FDA 产业方向雷达

[![由 DeepSeek Harness · deepseek-flash 构建](https://img.shields.io/badge/%E7%94%B1-DeepSeek%20Harness%20%C2%B7%20deepseek--flash%20%E6%9E%84%E5%BB%BA-4D6BFE)](https://github.com/ChazY11/medradar/blob/main/docs/ATTRIBUTION.md)


> 一个研究项目，核心科学问题是：**公开可观测的证据，能否可靠、可复现地提前揭示医疗技术发展的实质变化？**
> 工程产出与负面结果本身就是交付物；产品界面只是查看数据的方式。
>
> **当前状态：研究基础设施，不是经验证的预测产品。** 本仓库尚无任何方法证明样本外预测能力；
> 且历史数据不足以支撑真正的 point-in-time 结论（见下文“数据局限”）。
>
> **当前包版本：`0.5.0`**（以 `pyproject.toml` 为准）。`v0.2.2` 及此前的稳定核心由 DeepSeek Harness
> 智能体团队使用 `deepseek-flash` 构建。
> 研究底座（`medradar/tkg`、`forecast_registry`）与 Market-to-R&D 层由独立的 Kimi Code 会话完成；
> `v0.3.0` 在独立取证审计与缺陷修复后合并这些分支。逐项署名见 [docs/ATTRIBUTION.md](docs/ATTRIBUTION.md)，
> 合并/审计/修复决策见 [docs/INTEGRATION_2026-11-02.md](docs/INTEGRATION_2026-11-02.md)。

> 英文版 → [README.md](README.md) · 方法论 → [docs/METHODS.md](docs/METHODS.md)

## 项目状态（2026‑11‑13）

| | |
|---|---|
| `main` | `b2a14c0`，合并至 PR #11（2026‑11‑02） |
| 开放工作 | **23 个 open PR（22 个 Draft）不在 `main`** |
| `main` 测试 | **1,074 个离线测试**（1,071 通过 / 3 跳过，2026‑11‑12 实测） |
| 数据快照 | 375,378 条事件，1966–2026，SQLite 1.2 GiB，不提交进 git |
| 修订账本 | **尚未进入 `main`**：Event Revision Ledger v1 在 Phase 2 分支开发中 |
| 治理 | 5 道本地门存在于 Draft 分支；**未启用**分支保护 |

**`main` 今天真正能做的：** 离线 demo 与看板；采集 openFDA 器械/药品、ClinicalTrials.gov、SEC EDGAR；
事件时间描述统计与回测；导入双时态 TKG；用预测登记簿做 as-of 评分；生成中文报告与静态看板。

**仍是 Draft（不在 `main`）：** MedRadar 2.0（#12）、Live Observatory（#13/#14）、S‑028/S‑029（#15/#16）、
PHOENIX（#23–#26）、ATLAS/HORIZON/CONVERGENCE/DATA‑EXPANSION（#27–#30），以及 Phase 0–2 审计与治理分支。

**已完成的负面结果：** Market‑to‑R&D 未复现 Q1 转折；S‑028/S‑029 关系研究为 NO‑GO；prospective 预测尚无到期证据。
完整登记见 Draft PR #31 中的 `docs/refoundation/RESEARCH_ASSET_REGISTER.md` 与 `research/RESULTS/`。

### 数据局限（2026‑11‑13 实测）

- 提交快照中 **100%** 的行满足 `published_at = available_at = event_date`，且 `timestamp_quality` 全为 `'date'`；
  `first_seen_at` 是两天的批量导入时间 → **独立公开时间 = 0 行**。
- `INSERT OR REPLACE` 意味着重跑会覆盖旧行；快照没有修订历史。
- 因此：**支持事件时间描述性分析；不支持真正的 point-in-time / lead-time 主张**，除非重新采集来源公开时间。
- 实体解析不完整：约 35% 事件有 company key，约 11% 有可审计依据。

### 研究复现入口

```bash
pip install -e .
python -m pytest -q -o addopts=""     # 1,074 个离线测试，不联网
medradar demo                          # 离线，使用提交快照
medradar run --months 24 --with-trade  # 需联网；重建数据集（约 3 分钟）
```

下表数字需要**联网重新采集**才能复现；1.2 GiB SQLite 快照不入库，干净克隆复现的是**过程**，不是精确数字。

### 看板快照（2026‑10‑31 数据集）

<p align="center">
  <img src="docs/preview.png" alt="MedRadar 演示看板，数据集快照 2026-10-31" width="760">
</p>

*由 **2026‑10‑31** 提交数据集、包版本 **v0.5.0** 生成；仅示意 demo 视图，不是实时服务，也不是预测。
可用 `medradar dashboard` 重建；交互文件为 [`docs/dashboard.html`](docs/dashboard.html)。*

### 一次运行的实际产出（2026‑10‑31 快照）

| 指标 | 数值 |
|---|---|
| 入库事件 | **375,378** 件（510(k) 176,466 · PMA 57,372 · 召回 59,646 · 临床试验 55,592 · 药品批准 5,326 · EDGAR 催化剂 20,976） |
| 覆盖 | 89 家公司、60 个赛道、**204 个器械产品族**、7,097 个产品码、1.2 GiB SQLite |
| 当前最热赛道 | 心脏节律 THI 1.94（P=98.2%）· 可穿戴与远程监测 1.80 · 结构性心脏病 1.57 · 手术机器人 1.54 |
| 生成信号 | 281 条 |
| 案例库 | 历史快照含 **2,384 个可追溯案例**；v0.3.0 起按新监管分类与异常收益审计重新计算，旧分类计数不再沿用 |
| 回放 | **400 步、2019–2026 七年时间轴**，10/25/50bps 三档成本；最近 7 天用 1 分钟成交 |
| 前沿雷达 | **50 个器械细分赛道、23 个领域**；AdCom 日程/材料、试验首次公示、预申请与资格认定统一汇总 |
| 研究完整性 | 临床暂停、拒绝受理、CRL、预申请与资格认定独立分类；绝对超额收益超过 100% 的案例单列审计并退出推断样本 |
| Market-to-R&D | 由 55,090 条 FDA 事件 + 43,420 条 SEC 财务事实 + 3,453 条采购授予构造 **6,701 条持续性样本 + 41,003 条"休眠→进入"样本**（25/24 个季度起点）；purged 多窗口评估与 7 组特征消融，负面结果如实报告（见下） |
| 研究基础设施 | 双时态知识库（valid time / knowledge time）与 append-only 预测登记簿，支持 as-of 查询和确定性导出。**机制**支持 as-of/导出；**当前数据集**尚无独立公开时间，as-of 结果受此限制 |
| 预测闭环 | 规范登记簿新增独立 `nowcast` 队列；持续预测周期登记 25 条真实预测、核验到期结果、导出确定性工件；重跑幂等 |
| 时序图谱 | 55,090 条事件只读导入 → **57,381 节点 / 114,419 边**；PIT 快照哈希稳定、重复导入幂等、只读 pair 上下文/时间线查询 |
| 研究 Agent | 确定性 8 工具工作流，逐条引用证据、5 个问题模板、冲突检测与反证；真实演示：5 个问题 / 55 条论点 / 224 个唯一引用 / 0 缺失 |
| 测试 | **1,074 个离线测试**（`b2a14c0`，1,071 通过 / 3 跳过，2026‑11‑12 实测），不联网、不需要 API key |

> 数字每周都会变，价值在于每一个数字都能用 `python -m medradar run` 复现。

**一句话**：不猜大厂"想做什么"，只统计它"已经做了什么、往哪儿挪"。

---

## 60 秒试用

```bash
pip install -e .        # 或 git clone https://github.com/<你的用户名>/medradar.git && cd medradar
medradar demo           # 离线、用已提交快照、不需要 API key、<60 秒
# 打开 out/demo/index.html
```

真实数据运行：

```bash
medradar run --months 24 --with-trade    # 约 3 分钟，仅免费公开数据
medradar replay --days 30                # 事件→成交回放，含多档成本
```

## 这个项目回答什么问题

| 问题 | 指标 | 产物 |
|---|---|---|
| 获批之前发生了什么？ | AdCom、试验首次公示、预申请、突破性器械等资格认定 | `out/frontier.json` + `out/frontier.md` |
| 哪些器械赛道在升温？ | `THI`＝收缩后的近期速率 ÷ 基线速率 | 赛道热度榜 |
| 某家公司在换方向吗？ | 产品码结构的 JS 散度 | 迁移表（"谁在重新分配"） |
| 什么是真正新的？ | 该公司历史上首次出现的产品码 | 每周"首次出现"清单 |
| 药企的治疗领域在往哪走？ | 试验启动速率 + 各期占比 | 药品雷达 |
| 中国缺什么？ | 美国活动份额 vs 已加载的 NMPA 注册证 | 中国空白度（无数据时诚实标 `unavailable`） |
| 这些信号对股价有信息含量吗？ | 事件研究：相对 SPY 的超额收益（+1/+5/+20/+60 交易日） | `out/trading.json`（**仅模拟**） |

## 前沿层：获批之前的公开信号

```bash
python -m medradar collect --sources adcom,trials --months 24
python -m medradar frontier
```

`frontier` 把四类公开事件放进同一领域视图：FDA 咨询委员会日程与简报、临床试验首次公示、
SEC 公告中的预申请、突破性器械/优先审评等资格认定。赛道配置包含生命支持（呼吸机、ECMO、
氧疗、急救、监护）、IVD（NGS、液体活检、MRD、伴随诊断、微生物、数字病理等）、脑机接口、
神经调控、心血管、影像、手术机器人、SaMD/AI、肾脏和糖尿病等。

这是一层**公开信息监测**，不是 pending 申请窥探器。未公开的 510(k)/PMA 审评状态依法不可见，
系统明确返回 `pending_510k_pma_monitoring=false`，不会用决定日或宣传稿补造“在审管线”。

**已知限制（2026-11）**：FDA 的咨询委员会日历表格由前端 JS 渲染，静态抓取解析出 0 条会议，
因此 `collect --sources adcom` 现在返回 `status="empty"`/`"source_changed"` 并给出警告，
不再静默报 `"ok"`；该数据源在 [docs/DATA.md](docs/DATA.md) 中标记为实验性。
前沿层的其余输入（试验首次公示、8-K 预申请/资格认定）不受影响。

## 实时层：事件告警 + 模拟交易（5–15 分钟）

批处理回答"行业在做什么"，实时层回答"刚刚发生了什么"。

```bash
python -m medradar live --once --since-hours 2              # 单轮（cron / DSH 自动化）
python -m medradar live --interval 600                      # 每 10 分钟循环
python -m medradar live --once --backfill-days 7 --no-trade # 回填近期催化剂（只告警不下单）
python -m medradar live --reset                             # 清空模拟账户
```

每一轮：SEC EDGAR 8-K 实时流（秒级）→ EDGAR 全文检索回填 → FDA 新闻 RSS →
ClinicalTrials.gov 状态变更 → 关键词分类 → **按 Yahoo 最新真实报价 + 10bps 滑点模拟成交** →
按市值重估 → 告警（终端 + `out/live_alerts.jsonl` + 可选 `MEDRADAR_WEBHOOK_URL`）。

实测延迟（2026‑10‑31）：

| 数据源 | 延迟 | 能否交易 |
|---|---|---|
| SEC 8-K 申报 | 秒级 | ✅ |
| FDA 新闻 RSS | 实测滞后约 8 天 | ❌ 仅参考 |
| ClinicalTrials.gov 更新 | 小时级 | 仅终止/暂停 |
| openFDA 510(k)/PMA | 12 天 | ❌ 只属于慢车道 |
| FDA 在审提交 | **不公开** | 物理上不可能 |

只做多、单票 ≤5%、单赛道 ≤25%、−20% 止损、60 个交易日离场。做空信号**只告警不下单**：
借券费和并购逼平会让模拟收益变成假的。这是模拟盘，不接券商、不下真单、不构成投资建议。

**执行护栏**（发布前评审后补上）：

* 只有实时 EDGAR 流可以开仓；回填、FDA RSS、试验状态变更只告警不成交；
* 报价超过 30 分钟一律不能成交（只能用于估值）；
* 仓位按**含滑点的成交价**计算，现金不会变负；
* `--no-trade` 同时冻结买入和卖出；
* 同一 `(ticker, 日期, 类型)` 的跨源重复告警会被合并。

**时间口径**：`signal_date = event_date + 1`，成交取其后第一个交易日开盘，即**事件后约 2 个交易日**。
这是保守口径，不是"当日成交"。**注意：** 提交快照中所有事件都只有日期级时间，且
`available_at = event_date`；因此这些回测实质是“事件日 = 公开日”的同日假设，不是真实公开时点回测。
真正的 point-in-time 结论需要重新采集来源公开时间（见“数据局限”）。

### 8-K 全文 LLM 判定（决定仓位大小）

关键词只能判断"像利好"，判断不了"这是公司首个 20 亿美元级适应症，还是一个小标签变更"——
而这恰恰决定仓位该给 1% 还是 5%。所以实时层把 8-K 全文交给 LLM，要求输出**结构化 + 带原文引用**的判定：

```json
{"direction": 1, "materiality": 0.82, "confidence": 0.9, "catalyst_type": "approval",
 "asset": "Keytruda", "indication": "一线非小细胞肺癌", "is_pivotal": true,
 "revenue_relevance": "high", "evidence_quotes": ["原文逐字引用"], "rationale_zh": "……"}
```

* **任意 OpenAI 兼容端点**：`MEDRADAR_LLM_BASE_URL`（默认 `https://api.deepseek.com`）、
  `MEDRADAR_LLM_API_KEY`、`MEDRADAR_LLM_MODEL`（默认 `deepseek-chat`）。
* **按内容哈希缓存**：同一份文件永不重复计费。
* **预算硬上限**：`--llm-budget 4`，超预算自动回退关键词判定。
* **证据优先**：没有逐字引用的判定，置信度直接砍半。
* **仓位映射**：`仓位 = 5% × clamp(materiality, 20%, 100%)`——常规财报约 1%，首创获批给满 5%。

```bash
# 没 key 时用确定性回退，并在结果里标注 "judge": "heuristic(no-llm-key)"
python -m medradar judge --file filing.txt --headline "Company 8-K"

# 有 key 时
export MEDRADAR_LLM_API_KEY=sk-...
python -m medradar judge --url https://www.sec.gov/Archives/... --headline "Company 8-K"
```

在 **25 份人工标注的真实 8‑K**（批准 / CRL / 试验读出 / 财报）上校准，完整报告见
[docs/CALIBRATION.md](docs/CALIBRATION.md)：

| 指标 | LLM 判定 | 关键词基线 |
|---|---|---|
| catalyst_type 准确率 | **1.00** | 0.60 |
| direction 准确率 | **0.92** | 0.72 |
| 材料性 Spearman ρ | **0.80** | 0.58 |
| 高材料性 F1（≥0.5） | **0.94** | 0.67 |
| 把 CRL 判成"买入" | **0** | 5 份里 2 份 |

基线把 4/9 试验读数和 5/5 财报都判成 `approval`——而 `earnings` 是"不交易"的开关，这个错误是
实盘级别的。材料性相对人工标签系统性偏高约 +0.15：建议按排序使用，或乘 0.85 收缩后再算仓位。

## 快速开始

```bash
git clone https://github.com/<你的用户名>/medradar.git
cd medradar

# 不需要 API key，除 Python 3.10+ 外无依赖
# 24 个月是快速体验（约 2-3 分钟）；完整十年历史用 --months 120
python -m medradar run --months 24 --with-trade

# 打开
#   out/index.html      自包含看板（同时复制到 docs/index.html 供 GitHub Pages）
#   out/report_zh.md    中文研究报告
#   out/summary.csv     Excel 友好平表
#   out/frontier.json   前沿事件机器可读 feed
#   out/frontier.md     按领域组织的前沿中文报告
```

分步执行（可断点续跑，HTTP 响应全部缓存在 `data/cache/`）：

```bash
python -m medradar collect --sources device,drug,trials,adcom --months 120
python -m medradar analyze --window-quarters 8 --baseline-quarters 20
python -m medradar frontier
python -m medradar report
python -m medradar trade --capital 100000
python -m medradar status
python -m medradar selftest      # 离线单测，不联网
```

## 数据源（全部免费、无需凭证）

| 数据源 | 内容 | 新鲜度（2026‑10‑31 实测） |
|---|---|---|
| openFDA `device/510k` | 510(k) 清关，17.6 万条 | 更新至 2026‑10‑19（T−12 天） |
| openFDA `device/pma` | PMA 及补充申请，5.7 万条 | T−12 天 |
| openFDA `device/recall` | 器械召回，6 万条 | T−2 天 |
| openFDA `device/classification` | 约 6,500 个产品码定义 | 静态 |
| openFDA `drug/drugsfda` | NDA/BLA/ANDA 审评与批准，2.9 万条 | T−2 天 |
| ClinicalTrials.gov API v2 | 临床试验登记（**药品 + 器械都覆盖**） | 使用 `first_posted` 真实公示日 |
| FDA Advisory Committee Calendar | 公开会议日程、议程与简报材料 | 页面更新时间为估计口径，不进入交易研究 |
| SEC EDGAR 全文检索 | 8-K 监管/临床/资格认定事件流（可选） | 近实时 |
| NMPA（中国） | 医疗器械注册证 | **不爬取**：官网有 JS WAF（HTTP 412/202），见下 |

### 关于 NMPA 的诚实说明

`www.nmpa.gov.cn` 返回 412、`www.cmde.org.cn` 返回 202（JavaScript 挑战），
**MedRadar 不做绕过 WAF 的抓取**。替代方案是适配器：

1. 从国家药监局"医疗器械注册证"查询页导出 CSV；
2. 放到 `data/nmpa_registrations.csv`（列名兼容中英文，见 `config/sources.json`）；
3. 重跑 `collect --sources nmpa`，中国空白度表即生效。

没有 CSV 时，`cn_count`/`gap_index` 全部为 `null`，报告显式写"不可用（NMPA 数据未加载）"，
**绝不用 0 冒充真实空白**。演示用途可设 `MEDRADAR_NMPA_DEMO=1` 加载明显标注为虚构的样例种子。

## 方法要点（完整版见 docs/METHODS.md）

* **先收缩再喊话**：某公司本季度 2 件获批、上季度 0 件，增长率无穷大但信息量为零。所有速率都做
  Gamma–Poisson 后验，先验收缩强度 = 3 个季度；`THI` 是后验均值 ÷ 基线速率，`prob_up` 是
  "真实速率高于基线"的后验概率。
* **方向看结构，不看总量**：公司可以获批数量下降，但产品结构决定性地转向新品类。用
  Jensen–Shannon 散度衡量结构迁移，只报告变动 ≥8 个百分点的赛道。
* **新颖性＝首次出现**：某公司首次出现的产品码，是新产品线最早的可见痕迹。
* **信号带明确时间戳**：`signal_date = event_date + 1 天`，确保回测不可能偷看未来。
* **公司口径是生死线**：实测按名称直接匹配，J&J 两年只有 2 件 510(k)（真实申报主体是 Ethicon /
  DePuy Synthes / Biosense Webster / Cerenovus），GE HealthCare 只有 6 件。子地图谱做不好，
  这个工具就是废的。

## 中文看板包含什么

数据状态条 → KPI → 赛道热度榜（SVG 热力条 + THI + 后验概率）→ 大厂动量 → 结构迁移 →
本期首次出现 → 召回与风险 → 药品侧（批准/治疗领域/试验各期结构）→ 中国空白度 →
信号清单与模拟盘净值 → 方法与局限 → 免责声明。

看板是**完全自包含**的 HTML（无 CDN、无外链字体），可离线打开、可托管在 GitHub Pages。

## Market-to-R&D 与 Horizon 预测

研究层新增 SEC XBRL Company Facts、USAspending 合同授予、官方 openFDA 批量流式入库、
按时间一致原则构造的公司—赛道样本、purged rolling-origin Reverse R&D 基线，以及可持续核验的
12 个月预测登记。预测对象是**未来公开可见的研发/监管里程碑**，不是股价，也不是无法公开观测的内部研发启动日。

```bash
pip install -e '.[bulk]'          # 唯一新增可选依赖 ijson，用于流式解析官方 openFDA ZIP
python -m medradar.intelligence.pipeline collect --source fda --months 120
python -m medradar.intelligence.pipeline collect --source sec
python -m medradar.intelligence.pipeline collect --source procurement --start-date 2016-01-01
python -m medradar.intelligence.pipeline research --horizon 12
```

冻结的真实数据实验：

- **v1**（`experiments/reverse_rd_v1/`，2026-11-02 重建）：窗口内 55,090 条 FDA 事件、32 家公司
  43,420 条 SEC 财务事实、3,453 条采购授予（义务金额，0 条可作时点使用）、25 个季度起点共
  6,701 个样本，holdout 为 2025-10-01（307 行 / 129 正例）。
- **v2**（`experiments/reverse_rd_v2/`）：purged 三窗口评估（2025-04 / 2025-07 / 2025-10）加上
  更难的**休眠→进入赛道**目标（41,003 条样本、24 个起点、503 正例、基准率 1.23%，左删失限制已写明）。

| holdout 2025-10-01 | 持续性（307 行 / 129 正例） | 进入（1,716 行 / 26 正例） |
|---|---:|---:|
| PR-AUC，仅 R&D | 0.7935 | 0.1139 |
| PR-AUC，+ 合并财务 | 0.7922 | 0.1163 |
| Brier，仅 R&D / + 财务 | 0.1721 / 0.1721 | 0.0143 / 0.0143 |
| ECE-10，仅 R&D / + 财务 | 0.0811 / 0.0737 | 0.0041 / 0.0046 |

**来源消融（A–G，同一批 purged 样本、3 个窗口）**：在 R&D 基线之上分别加入市场特征（8 个，来自
本地日线价格）、OpenAlex 论文特征（5 个）与合并财务特征。**没有任何新增来源带来统计可检测的排序增益。**
持续性目标上所有边际 PR-AUC 均为负（财务 −0.0013、市场 −0.0015、论文 −0.0001、全来源 −0.0068），
而全来源模型改善了校准（ECE 0.0811→0.0628）与 FPR（0.2753→0.2472）——校准更好，不是排序更好。
进入目标上，最终 holdout 偏向"仅共享特征"基线，而三窗口均值偏向更丰富规格，差异落在
0.014–0.026 的窗口标准差内，不构成稳定效应。采购因当前快照不可作时点使用而排除，专利因
USPTO Open Data Portal 需要 API key 而**未评估**，招聘信号暂缓。持续性的 0.79 PR-AUC 仍主要来自
持续性本身：per-pair 基线 AP 0.7913 vs 模型 0.7935（Δ +0.0022，95% CI [−0.032, +0.037]）。

```bash
pip install -e '.[bulk]'
python -m medradar.intelligence.pipeline collect --source fda --months 120
python -m medradar.intelligence.pipeline collect --source sec
python -m medradar.intelligence.pipeline collect --source procurement --start-date 2016-01-01
python -m medradar.intelligence.pipeline collect --source market --prices-db /path/to/base-medradar/data/medradar.sqlite
python -m medradar.intelligence.pipeline collect --source publications
python -m medradar.intelligence.pipeline research --horizon 12
python experiments/reverse_rd_v2/run_v2.py --db data/medradar.sqlite --holdouts 3
python experiments/reverse_rd_v2/run_ablation.py --db data/medradar.sqlite --target continuation --spec C --out cells/continuation_C.json
python experiments/reverse_rd_v2/merge_ablation.py --cells cells --out experiments/reverse_rd_v2/ablation_metrics.json
```

研究层下还有两个底座：**双时态知识库**（`medradar/tkg`，独立的 valid-time / knowledge-time 查询、
确定性 PIT 导出、只读 events 适配器）与**不可篡改预测登记簿**（`medradar/forecast_registry.py`，
3/6/12/24 日历月窗口、追加式结果修订、as-of Brier/log-loss/ECE 评估）。

## Phase 3：研究闭环

- **统一预测账本**：规范登记簿为唯一事实来源，新增不可变 `nowcast` 记录类型（窗口已打开时登记的
  真实前瞻预测，即季度 Horizon 场景），单独成队列、绝不混入"纯未来"主口径。
  `registry_adapter.py` 用稳定幂等键映射 Horizon 记录，并按来源覆盖门槛从真实事件表结算到期预测。
- **持续预测周期**：`scripts/forecast_cycle.py` 训练冻结模型 → 评分当前季度 → 登记 nowcast →
  核验到期 → 导出确定性工件与周期日志。真实运行：25 条 nowcast 登记、25 条 pending（窗口 2027-10
  结束）、校准状态 `insufficient_matured_forecasts`、第二次运行完全幂等。周度 GitHub workflow 已提交
  （`forecast-cycle.yml`）但未在本环境执行，不声称 CI 通过。
- **时序图谱**：`scripts/tkg_import_research.py` 把真实 55,090 条事件只读导入双时态库
  （171,800 条断言 → 57,381 节点 / 114,419 边，源文件哈希不变），导出确定性 PIT 快照并证明重复导入
  幂等；`graph_context.py` 提供只读 pair 上下文/时间线（独立 known-time/valid-time 截断）。
- **研究 Agent**：`medradar/research_agent.py` 是确定性的证据驱动工作流（不是聊天机器人）：
  plan → 8 个时点工具 → 证据表 → 5 条冲突规则 → 带标签的假设 → 反证 → 基线/统计校验 → 引用式综合 →
  不确定性 → 研究日志 → 停止条件。每条论点都引用真实存储 id，概率只来自模型/登记簿。真实演示
  （`experiments/reverse_rd_v2/agent_demo.json`）：5 个问题、55 条论点、224 个唯一引用、
  314 次引用校验、0 缺失、3 个跨来源冲突。

**不声称**：尚无到期预测（校准为 `insufficient_data`）；当前导入的 TKG knowledge clock 是回填时间
（不是历史公开时间）；Agent 只叙述存储证据，不做因果断言；专利/招聘仍是明确的证据缺口。详见
[docs/PHASE3.md](docs/PHASE3.md)、[PHASE3_REGISTRY](docs/PHASE3_REGISTRY.md)、
[PHASE3_AGENT](docs/PHASE3_AGENT.md)、[TKG_INTEGRATION](docs/TKG_INTEGRATION.md)。

```bash
python scripts/forecast_cycle.py --db data/research.sqlite --registry data/registry.sqlite \
  --out out/forecast_cycle --horizon 12 --top-n 25 --coverage-end 2026-10-15 --offline
python scripts/tkg_import_research.py --db data/research.sqlite --tkg data/tkg.sqlite \
  --known-at 2026-12-31T00:00:00Z --report-out experiments/reverse_rd_v2/tkg_import_report.json
python -m medradar.research_agent ask --company medtronic --track spine \
  --template market_leading_indicator --as-of 2026-11-02 \
  --db data/research.sqlite --registry data/registry.sqlite --tkg data/tkg.sqlite
```

SEC 营收始终保持公司合并口径，不会冒充产品或器械业务收入。USAspending 合同授予金额不等于营收，
其当前快照不参与历史增益结论。完整口径见 [Reverse R&D 方法](docs/REVERSE_RD.md)、
[集成记录](docs/INTEGRATION_2026-11-02.md)、[docs/TKG.md](docs/TKG.md)、
[docs/FORECAST_REGISTRY.md](docs/FORECAST_REGISTRY.md)、[Phase 1](docs/PHASE1.md)、
[Phase 2](docs/PHASE2.md)、[Phase 3](docs/PHASE3.md)；冻结实验配置与真实结果位于
`experiments/reverse_rd_v1/`（v1）与 `experiments/reverse_rd_v2/`（v2 多窗口 + 来源消融 + Phase 3 报告）。

## 模拟美股：定位与边界

`medradar trade` 在信号上跑一个**纯模拟**组合：次日开盘入场、持有 60 个交易日、−20% 止损、
单票 ≤5%、单赛道 ≤25%、每次成交 20bps + \$1、v1 仅做多。

它输出**事件研究**（相对 SPY 的超额收益、t 值、bootstrap 置信区间）而不只是一条好看的净值曲线，
因为"信号有没有信息含量"才是可证伪的问题。

v1 **不建模**：做空借券费、并购逼平、退市收益。所以做多口径会高估真实策略表现，报告每页都会写明。
**这不是投资建议。**

## 目录结构

```
config/         知识库：母公司→子公司别名、中文赛道词典、数据源说明
medradar/       纯标准库实现
  util.py       日期/文本/统计（Gamma-Poisson、bootstrap、JS 散度）
  http.py       限速、重试、响应缓存、离线回放
  db.py         统一 events 表 + 注册表 + 价格 + 信号 + 模拟盘表
  config.py     CompanyRegistry / TrackRegistry 模糊匹配
  collect_*     openFDA / ClinicalTrials.gov 采集器
  nmpa.py       诚实的中国数据适配器（CSV / demo / 关闭）
  analyze.py    指标引擎 → out/metrics.json（契约：docs/SCHEMA.md）
  report.py     中文报告 + 自包含 HTML 看板
  prices.py     Yahoo 日线（研究用途）
  eventstudy.py 事件研究
  paper.py      含摩擦成本的模拟盘
  tkg/          双时态知识库：valid time / knowledge time、as-of 查询、确定性 PIT 导出
  forecast_registry.py 追加式预测账本 + as-of Brier/log-loss/ECE 评估
  intelligence/ Market-to-R&D 层：SEC XBRL、USAspending、openFDA 批量、时点样本、Reverse R&D 模型
  adcom.py      FDA 咨询委员会日历（目前实验性：表格由前端 JS 渲染）
  frontier.py   获批前前沿信号（AdCom + 试验首次公示 + 8-K 预申请）
docs/           数据契约、方法论、GitHub Pages 演示
tests/          离线测试（合成 fixture，不联网）
```

## 如何扩展

* **加一家公司**：在 `config/companies_device.json` 里加 parent key + 子公司别名。
* **加一个赛道**：在 `config/tracks_device.json` 里加中文名 + 英文关键词，产品码映射会在下次采集时
  从 openFDA classification 自动生成。
* **加一个数据源**：只写 `collect_<name>(db, fetcher, months, limit)` 并往 `events` 表写，
  分析、报告、交易都不用改。

## 路线图

- [x] `v0.3.0` —— 合并研究底座（双时态 TKG + 不可篡改预测登记簿）与 Market-to-R&D 层
  （SEC XBRL / USAspending / openFDA 批量、时点数据集、purged 滚动起点基线、独立泄漏重放、朴素/persistence 基线）
- [x] `v0.4.0` Phase 1 —— 更难的目标：**休眠→进入**某技术赛道（左删失，已写明限制）；
  purged 多窗口评估（`holdouts=K`），含每窗口基线与 bootstrap 置信区间
- [x] `v0.4.0` Phase 2 —— 市场特征（本地日线：12 个月收益、波动、回撤、相对 SPY/XBI、市场状态）
  与 OpenAlex 论文特征，全部 point-in-time；冻结 A–G 来源消融（专利因 API key 缺失未评估，
  采购因快照不可作时点使用而排除，均已写明）
- [x] `v0.5.0` Phase 3 —— 规范登记簿新增独立 nowcast 队列、Horizon 适配器与幂等持续预测周期；
  真实 55,090 条事件导入双时态 TKG（确定性 PIT 快照）；确定性、证据驱动的研究 Agent（引用式综合 + 反证）
- [ ] Phase 3 剩余 —— 窗口到期后在 GitHub 执行周度 workflow（需要 ≥20 条到期预测才能谈校准）；
  把图特征接入模型而不只是 Agent
- [ ] Phase 2 剩余 —— 拿到 USPTO ODP API key 后补专利特征；用版本化历史赛道分类替代当前静态映射
- [ ] 因果设计（DiD / 合成控制）—— 需要先有可辩护的时点需求冲击
- [ ] NMPA CSV 导入向导 + 省级空白度
- [ ] FDA 统计审评 PDF 挖掘（直接从 FDA 统计师笔下提取"试验设计红旗"）
- [ ] 赛道 THI 变动的归因分析
- [ ] 有借券费数据后开做空侧事件研究

## 许可证与免责

MIT。源数据版权归各发布方（openFDA 属公共领域；ClinicalTrials.gov、SEC EDGAR 有各自条款）。
本项目不构成投资建议，是研究与教育项目。
