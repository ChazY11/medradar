# MedRadar 2.0 — Product Architecture

本轮没有重建数据系统，也没有另起一套"演示数据"。产品层是一个**只读的产品接口 + 静态前端**，复用既有研究数据库、企业名册、赛道分类与研究产物。

```
┌───────────────────────────────────────────────────────────────────┐
│  Browser SPA (web/)                                               │
│  vanilla JS + SVG charts · hash routing · 无 CDN / 无构建步骤     │
└───────────────▲───────────────────────────────────────────────────┘
                │  JSON  /api/*
┌───────────────┴───────────────────────────────────────────────────┐
│  FastAPI app (medradar/web/app.py)                                │
│  routes: companies · compare · radar · evidence · analyst · lab    │
└───────────────▲───────────────────────────────────────────────────┘
                │  Python calls (read-only)
┌───────────────┴───────────────────────────────────────────────────┐
│  Product measurement layer (medradar/product/)                    │
│  store.py     SQL aggregations, windows, signals, evidence        │
│  entities.py  company attribution (roster + exact aliases)        │
│  catalog.py   curated names/sources/metrics/limitations/studies   │
│  analyst.py   deterministic question → real queries → answer      │
│  lab.py       research artifacts (read-only references)           │
└───────────────▲───────────────────────────────────────────────────┘
                │  reuse (never rewrite science)
┌───────────────┴───────────────────────────────────────────────────┐
│  Existing research infrastructure                                 │
│  data/medradar.sqlite   events 375k · companies · tracks · codes  │
│  config/companies_device.json   company aliases                   │
│  config/product_code_tracks.json · tracks                         │
│  research/  studies · results · forecast registry · artifacts     │
│  medradar/*.py  collectors · analysis · studies · research agent  │
└───────────────────────────────────────────────────────────────────┘
```

## 1. 为什么新增一个产品层，而不是继续扩展单文件 Dashboard

现有 `docs/dashboard.html` 是 3.2MB 的离线单文件生成物，适合 GitHub Pages 静态展示，但存在三个硬限制：

1. 数据在构建时固化，无法按任意企业/赛道/时间窗动态查询；
2. 结论与证据之间没有可交互的展开链路；
3. 无法承载研究助手、证据浏览器与比较界面。

因此新增 `medradar/product/` + `medradar/web/` + `web/`，但**不重写**任何科研模块：所有数字仍然来自同一 SQLite、同一企业名册、同一产品代码→赛道映射、同一研究产物。旧的 Dashboard 与 CLI 继续可用，互不破坏。

## 2. 数据访问与口径

### 2.1 只读连接

`store.read()` 以 `mode=ro` 打开 `data/medradar.sqlite`，产品不会写入、迁移或删除研究数据。

### 2.2 事件与指标

| 指标 | event.kind | 说明 |
| --- | --- | --- |
| `approvals` | `510k` + `pma` | 美国 FDA 公开审批/许可记录条数；PMA 中绝大多数是**补充申请**，不是新器械批准 |
| `510k` / `pma` | 单一类型 | 路径不同，不能混为创新能力 |
| `recalls` | `device_recall` | 安全性事件，不是研发活动 |
| `trials` | `trial` | ClinicalTrials.gov 注册 |
| `corporate` | `8k_catalyst` | SEC 8-K 语料（2015 起） |

一条记录 ≠ 一个产品：同一申请可能拆成多条，同一产品也可能多次申报。产品在 UI 与文档中反复声明这一点。

**审批类型分类（P1-1）**：openFDA PMA payload 的 `supplement_number` 对所有 57,372 条 PMA 记录可用（空=原始批准，非空=补充申请），510(k) 的 `clearance_type` 对所有 176,466 条记录可用。产品据此区分：

- 原始 PMA 批准 / PMA 补充申请 / 类型不可判定；
- Traditional / Special / Abbreviated / 其他 510(k) / 类型不可判定；
- "首次进入"只使用**原始 PMA + Traditional 510(k)**；PMA 补充申请与 Special/Abbreviated 510(k) 是已上市器械的变更，不作为首次进入证据；
- 无法解析 payload 的记录标记为 `unknown`，`dataset.approval_classification` 报告不可判定数量；产品不凭申请编号猜测类型。

审批总量指标保留原有口径（以维持既有研究/产品功能），但所有"首次进入/新技术/新产品"判断使用上述分类口径。

### 2.3 技术赛道

赛道来自仓库既有分类体系（`tracks` 表 + `product_codes.track_id` 映射），事件在采集时写入 `events.track_id`。未映射的记录在产品里显示为"未映射"，**不当作零活动**。当前全库赛道映射覆盖率约 52%，产品在雷达页按窗口显示覆盖率。

### 2.4 企业归属

1. **主名册**：复用 `config/companies_device.json` 的 `company_key` 映射（51 家企业），产品不改写；
2. **补充精确映射**：Dräger 与 Mindray 不在主名册，所有事件 `company_key=NULL`。产品使用 `medradar/product/entity_aliases.json`（来自 `research/full-history-v1:config/hist_entity_aliases.json`，21 + 10 条精确申请人字符串）做**逐条精确匹配**，状态标记为 `PENDING_HUMAN_REVIEW`；
3. 未匹配的字符串保持未归属，不强行归类。

为在不修改研究库的前提下加速，产品首次运行会把这一小部分事件（约 550 条）物化到 `<store>.product_entity_map.sqlite`，之后通过只读 ATTACH 查询。研究库 mtime 变化时自动重建；合成 fixture 使用独立文件名，绝不读取真实数据的派生索引。

### 2.5 时间窗、完整周期与数据截止

- 默认截止日 = 数据库内最新事件日期（不是系统时间），保证同一份数据的视图稳定；
- 公司页/比较页提供 3/5/10/20 年窗口；
- **比较与结论只使用完整自然周期（季度）**：请求窗口起点/终点所在的不完整季度只展示、不参与同比、份额与 LQ；
- 对照窗口是"紧邻的、与本期周期数完全相同的完整周期"；例如请求 2021-10-31 至 2026-10-30 的 5 年窗口，完整比较窗口为 2022-01-01 至 2026-09-30（19 个季度），对照为 2017-04-01 至 2021-12-31（19 个季度），两者连续且等长；
- 窗口内完整周期数不足 1 时，API 返回 `comparable=false` 与原因，不计算同比/LQ；
- **日历完整 ≠ 数据完整**：距离数据截止不足 90 天的完整周期标记 `source_lag_risk`（源数据可能仍会修订/补录），与 `partial` 分开披露；
- 数据源起点不同：召回约 2002 起、8-K 约 2015 起，产品在覆盖面板中展示各源实际观测范围。

### 2.6 Location Quotient（LQ）

比较页的 LQ 使用**严格一致的已映射分母**：

```
LQ = (企业该赛道已映射记录 / 企业已映射记录)
   / (全行业该赛道已映射记录 / 全行业已映射记录)
```

- 企业与行业都只使用窗口内已映射到赛道的记录作为分母；未映射记录单独列出，不当作零活动；
- 企业已映射记录 < 10、行业该赛道记录 < 5、任一分母为 0、或该企业在该赛道 0 条时，返回 `lq_status != "ok"` 与 `"不适用"`，不制造数值；
- 窗口不具备完整周期时返回 `not_comparable`；
- LQ 只描述监管记录分布的相对专业化程度，**不是创新能力、技术实力或市场份额**。

## 3. 结论与信号如何产生

### 3.1 企业结论（Observed Change）

`store._company_claims()` 的固定规则：

1. 使用**紧邻、等长、完整自然季度**窗口比较审批记录数（不是日历裸窗口）；
2. 同时计算该赛道全行业的变化；
3. 输出绝对数、变化率、企业内赛道占比变化、行业对照，并披露该赛道 PMA 原始批准/补充申请构成；
4. 记录数过少（任一期 < 5）时只陈述原始计数，明确"不足以判断趋势"；
5. 每条结论携带 `evidence_params`，`POST /api/evidence/claim` 用同一口径重算并列出事件，前端展示 `recomputed` 与记录数以便核对；
6. 结论文本禁止因果与战略语言；"首次观察到"只表示数据覆盖期内首次，不等于企业首次进入市场。

### 3.2 统计探测信号（Detected Signal）

技术雷达对季度审批记录计算 z 分数：当前完整季度相对前 8 个季度均值的标准化偏离；`|z| ≥ 2.5` 且计数 ≥ 5 时标记为"统计探测信号"。UI 同时显示方法说明：

> 统计探测只说明记录数偏离历史基线，不证明真实技术变化，也不是预测。

### 3.3 研究结论（Hypothesis / Negative）

研究状态、方法与负面结论来自 `medradar/product/lab.py`，只读取仓库内冻结产物：

- 主分支：`research/studies/early_signal_5firms/`（69 份证据包、AI 预标注、Pilot、跨源检验、人工复核工作表）；
- 只读引用：`research/full-history-v1` 的 Cycle 43 报告与 `five_firm_timeline.json`（来源 commit `969fd0c`，**未合并**）。

## 4. API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 数据集签名与产品版本 |
| GET | `/api/meta` | 数据基础、来源目录、指标定义、限制、研究列表 |
| GET | `/api/companies` | 企业目录（含真实计数） |
| GET | `/api/companies/{key}?years=` | 企业主页：概览、覆盖、赛道、趋势、里程碑、结论 |
| GET | `/api/compare?companies=&metric=&years=&granularity=` | 2–5 家企业比较 + 可比性警告 |
| GET | `/api/radar?years=` | 8 大领域 / 18 个赛道总览 + 信号 |
| GET | `/api/radar/{track}?years=` | 赛道详情、企业构成、首次进入、信号、事件 |
| GET | `/api/evidence?...` | 证据检索（企业/赛道/指标/来源/时间/关键词/分页） |
| GET | `/api/evidence/{event_id}` | 单条证据的完整来源与映射说明 |
| POST | `/api/evidence/claim` | 用结论参数重算并列出事件 |
| GET | `/api/analyst/examples` | 研究助手示例与能力边界 |
| POST | `/api/analyst/ask` | 自然语言问题 → 确定性检索与结构化回答 |
| GET | `/api/lab` · `/api/lab/{id}` | 研究项目与研究产物 |

完整字段见 [`web/CONTRACT.md`](../web/CONTRACT.md)。

## 5. 前端

- 纯静态：`web/index.html` + `styles.css` + `app.js`（ES module），无框架、无构建、无 CDN；
- hash 路由：`#/overview`、`#/companies/{key}`、`#/compare`、`#/radar/{track}`、`#/analyst`、`#/lab/{id}`、`#/evidence`；
- SVG 图表：hover 显示精确数值，点击跳转到对应证据筛选；
- 所有页面包含加载/空/错误状态；
- 响应式：桌面 1440×900 与手机 390×844。

## 6. 运行与部署

```bash
# 依赖：Python 3.10+，已安装 fastapi/uvicorn（本仓库开发环境已具备）
python -m medradar web --port 8787
# 打开 http://127.0.0.1:8787
```

- 启动时预热 meta/企业/雷达缓存（可用 `--no-warm` 跳过）；
- 数据缺失时给出明确提示（`python -m medradar run` 构建研究库）；
- 静态页面可由任意 HTTP 服务器托管，但**动态查询需要本地 Python 后端**；GitHub Pages 只能承载静态快照，本项目没有声称 Pages 可直接运行后端。

## 7. 性能

- 产品查询走 SQLite 现有索引（`company_key+event_date`、`track_id+event_date`、`kind+event_date`）；
- 聚合结果按“数据库 mtime + 参数”缓存（LRU 256），同一数据集内重复访问为毫秒级；
- Dräger/Mindray 的补充映射通过辅助索引 + 只读 ATTACH，避免对 `applicant_raw` 全表扫描；
- 首次冷启动约 3–5 秒预热，之后主要页面 < 300ms（本地笔记本）。

## 8. 维护成本与边界

- 新增一个数据源或指标：在 `catalog.py` 增加定义 + 在 `store.py` 增加聚合，不需要改前端；
- 新增企业：写入 `config/companies_device.json` 或补充别名（需人工复核）；
- 新增研究：在 `catalog.STUDIES` 与 `lab._study_artifacts()` 注册；
- 产品层不写研究库；任何研究口径变更仍由既有科研流程负责。

