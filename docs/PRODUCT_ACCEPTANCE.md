# MedRadar 2.0 MVP — 独立验收报告

> 验收对象：`D:\DEPPSKK\medradar` · 分支 `feat/medradar-2.0-mvp` · 最终审计 commit `22817c5`
> 数据截止：**2026-10-30** · 事件总数：**375,378** · 产品版本：`2.0.0-mvp`
> 验收人：独立验收员（verifier）· 审计时间：**2026-11-03 11:47–12:14（Asia/Shanghai）**
> 结论：**五个必需场景全部 PASS（真实数据、可复现），属于可交付的 MVP；但仍是"证据型研究终端"，不是预测产品，且覆盖率/时点口径等弱点明确存在。**

---

## 1. 结论摘要

- 五个任务场景（研究公司、对比竞品、分析技术趋势、追溯结论、研究助手）都在真实数据上跑通，数字与 `/api/*`、SQLite 只读 SQL 独立复算一致。
- 反造假、反误导检查通过：没有伪造来源 URL（375,378/375,378 均带 http(s) 链接；294,756 条可用 payload ID 校验的记录 100% 一致）、没有展示"经验证预测"、迈瑞/德尔格补充映射标注 `PENDING_HUMAN_REVIEW`、69 份证据包 0 条人工标签、`research/full-history-v1` 未合并均属实。
- 五类限制（仅美国、记录≠产品、赛道映射覆盖、召回≠研发、无经验证预测）在总览、企业页、比较页、雷达页、研究助手、研究实验室均有可见声明。
- 审计期间发现并推动修复了 5 个数字口径/标签缺陷（详见 §8.1）；最终冻结版已复验通过。
- 残留问题均为低严重度或已知限制（空态重复文案、移动端宽表、point-in-time 不可回放、文档小口径不一致等），不阻塞五场景验收。

---

## 2. 环境与版本（可复现事实）

| 项目 | 实测值 |
| --- | --- |
| 仓库 / 分支 | `D:\DEPPSKK\medradar` / `feat/medradar-2.0-mvp` |
| 最终审计 commit | `22817c5cee186df9cad60121b73a2bc38ad37ed1`（2026-11-03 12:09:18 +0800，fix(product): distinguish track-mapping from entity-attribution KPIs） |
| 冻结中间版本 | `838b8543deb129231497e3e36d04bd30c699da84`（12:02:31，五场景与 D1–D4 修复的冻结基线） |
| 工作区状态 | 除本报告交付文件 `docs/PRODUCT_ACCEPTANCE.md` 外，仅 `research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv` 显示 modified；`git diff --numstat` 无内容差异，属 CRLF/LF 行尾差异，`human_label` 仍为 0 条 |
| 服务 | `http://127.0.0.1:8787`，`GET /api/health` → `{"status":"ok","product":"2.0.0-mvp"}`；审计期间未重启服务 |
| 数据文件 | `data/medradar.sqlite`，1,368,469,504 bytes，mtime `2026-10-31T05:28:25Z` |
| 数据范围 | `1966-12-14` → `2026-10-30`（数据截止 2026-10-30） |
| 数据规模 | events 375,378；companies（有事件）89；tracks 60；product_codes 7,097 |
| 来源 | openFDA 510(k) 176,466 / PMA 57,372 / 召回 59,646；ClinicalTrials.gov 55,592；SEC 8-K 20,976；FDA 药品 5,326（六源合计 375,378） |
| 赛道映射 | 已映射 196,542 / 未映射 178,836 = 375,378，覆盖率 **52.4%**（API `dataset.track_unmapped_events=178,836`，与 `attributed_events=132,293 / unattributed_events=243,085` 明确区分） |
| 浏览器 | Chrome（Playwright），桌面 1440×900 + 移动 390×844；隔离 headless 上下文独立复跑 |

> 说明：审计开始时（11:47）产品代码仍在被实时编辑；12:02 冻结到 `838b854`，12:09 修复 D5 到 `22817c5`。本报告所有 PASS 结论均在 `22817c5` 上重新执行/复验；未使用冻结前状态作为通过依据。

---

## 3. 方法（实际执行了什么）

1. **读文档核对口径**：`docs/PRODUCT_VISION.md`、`docs/PRODUCT_ARCHITECTURE.md`、`web/CONTRACT.md`、`docs/PRODUCT_USER_GUIDE.md`、`docs/PRODUCT_ROADMAP.md`。
2. **官方测试**：`python -m pytest tests/test_product_api.py tests/test_product_store.py tests/test_product_analyst.py -q`（7 + 20 + 44 = 71 项，exit 0）。
3. **仓库 E2E**：`node scripts/product_e2e.cjs` → 6/6 PASS，报告 `out/product_e2e/report.json`。
4. **独立浏览器复跑**（自写隔离 Playwright 脚本，不复用仓库 E2E 判定）：1440×900 依次点击 `#/overview`、`#/companies`→迈瑞、`#/compare`（Medtronic+Philips）、`#/radar/respiratory`、企业结论→证据→事件详情、`#/analyst`（两问）、`#/lab`、`#/evidence`；21 个检查步骤，0 pageerror。
5. **独立数据复算**：只读打开 `data/medradar.sqlite`（`mode=ro`），用自己的 SQL 复算事件数、企业计数、窗口计数、赛道计数、claims 计数；迈瑞/德尔格用 `medradar/product/entity_aliases.json` 的精确别名列表独立匹配，不信任产品层汇总。
6. **claims 复算**：对 18 条企业结论逐条 `POST /api/evidence/claim`，并用 SQL 按同一窗口/赛道/指标重算，三方（claim.metrics、API recomputed、SQL）比对。
7. **来源链接审计**：全库 375,378 条 URL 检查空值/协议；对 294,756 条 payload 带 ID 的记录（510(k)/PMA/试验/药品）校验 URL 内 ID 与 payload ID 一致；召回按 `res_event_number`、8-K 按 accession 抽样核对。
8. **反造假点名检查**：`PENDING_HUMAN_REVIEW`、`merged=false`、负结果、无验证预测、69 包/0 人工标签（API + CSV 双侧核对）。
9. **交互与状态**：导航、图表点击→证据筛选、结论"查看证据"→事件行→原始链接、研究助手示例 chip/证据事件、比较页非法选择清空旧图、证据分页/搜索/重置、雷达领域卡→赛道页；用路由延迟制造 loading 观察骨架屏、未知企业制造 error 观察重试、无结果搜索观察 empty。
10. **移动端 390×844**：总览、企业页、雷达赛道页、研究助手 4 个路由 + 折叠菜单展开；检查 `scrollWidth-clientWidth` 横向溢出。
11. **性能**：对 8 个 API 暖缓存各测 3 次取中位数。
12. **Git 事实**：`git rev-parse`、`git log -1`、`git status`、`git merge-base --is-ancestor 969fd0c HEAD`（exit 1，证明 hist_v1 未合并）。

---

## 4. 五个必需场景逐项验收

> 全部在 `22817c5`、1440×900 实测；截图位于 `out/acceptance/`（gitignored 构建产物，不入库）。仓库内可提交的等价截图见 [`docs/product/`](product/)：企业页、比较页、雷达赛道、证据链、研究助手、移动端、总览与证据空态。

### 4.0 场景验收总表

| # | 场景 | 检查内容 | 关键观测值（真实数据） | 结果 | 截图 |
| --- | --- | --- | --- | --- | --- |
| 1 | 研究一家公司（迈瑞医疗） | 企业 KPI、技术分布、历史趋势、里程碑、数据覆盖、结论→证据 | 244 事件 / 已映射审批 38（另未映射 2）/ 3 条结论 / 3 条赛道 + 未映射 2·4 / 2 个来源 / 8 条限制；`PENDING_HUMAN_REVIEW` | **PASS** | `02-companies-1440.png`、`03-company-mindray-1440.png`、`05-claim-evidence-panel.png` |
| 2 | 比较竞争对手（Medtronic vs Philips） | 同赛道/同指标/同窗口、可比性警告、路径结构、LQ 矩阵、非法选择 | 2,734（仅完整 2,713，partial 21）/ 前窗 3,548 / 未映射 208；飞利浦 166/166/184/18；1 条 pathway_mix 警告；28 条赛道矩阵；旧图清除 | **PASS** | `06-compare-medtronic-philips.png`、`30-compare-totals-1440.png` |
| 3 | 分析技术趋势（呼吸与麻醉） | 相关企业、历史趋势、重要事件、趋势解释、观察 vs 探测信号 | 570 vs 763（-25.3%）/ 全时 4,091 / 已归属 128·未归属 442（77.5%）/ 14 家企业 / 3 家新进入 / 30 条事件 / 无检出信号 + 方法说明 | **PASS** | `07-radar-respiratory-1440.png`、`23-radar-overview-1440.png` |
| 4 | 追溯结论到原始证据 | 结论→证据面板→事件→详情→来源链接 | 心脏节律 1,111/1,552 复算、57 行可点击事件、真实 FDA PMA 链接 `pma.cfm?id=P030036`、日期/映射/限制齐全 | **PASS** | `08-event-detail-source.png`、`05-claim-evidence-panel.png`、`33-evidence-drawer.png` |
| 5 | 使用研究助手 | 确定性问答、数字可核验、证据 id 解析、越界拒绝 | Q1：32→28（-12%）、行业 411→429、3 条证据 3/3 解析；Q2：`out_of_scope` 诚实拒绝、无编造数字 | **PASS** | `09-analyst-q1.png`、`10-analyst-evidence-detail.png`、`11-analyst-out-of-scope.png` |

### 4.1 场景 1 — 研究一家公司：迈瑞医疗（Mindray） — **PASS**

入口：`#/companies` → 点击"迈瑞医疗"卡片 → `#/companies/mindray?years=5`。

| 检查点 | 实测观测 |
| --- | --- |
| 企业身份与数据基础 | 迈瑞医疗 / Mindray / 300760 / SZSE；标"重点企业""补充映射 · 待人工复核"；覆盖期 2004-03-03 → 2026-10-16 |
| KPI | 事件（全时）244；已映射赛道审批（近 5 年）**38**，旁注"另有未映射 **2** 条"；审批（全时）180；召回 64；试验 0 |
| 技术分布 | 技术赛道结构（近窗 / 前窗）：超声 28 / 32（-13%）、监护与生命体征 5 / 11（-55%）、呼吸与麻醉 5 / 3（+67%）；"未映射赛道：近窗 2 条 / 前窗 4 条，未映射不等于零活动"；全行业对照 18,640 条 |
| 历史活动 | 季度审批趋势图（1,382px 宽，SVG），3/5/10 年窗口可切换；切到 3 年后结论变为"16→18（+12%）"，URL 变为 `?years=3` |
| 重要事件 | 里程碑时间线：首个 510(k) 2004-03-03（PM-8000 监护仪）、首次进入监护 2004-03-03、首次进入超声 2006-12-06、首个召回 2008-12-05、首次进入呼吸 2011-02-11；派生项明确标"不可点击" |
| 数据覆盖 | 2 个来源：FDA 510(k) 180 条（2004-03-03→2026-10-16）、FDA 召回 64 条（2008-12-05→2026-10-07），各带口径说明 |
| 证据入口 | 3 张结论卡（超声/监护/呼吸），均有"查看证据"，展开后显示"复算结果：近窗 28 条 / 对照窗 32 条"并列出事件行 |
| 归属与限制 | 页面顶部明确 `PENDING_HUMAN_REVIEW` + 10 条接受匹配字符串；赛道映射说明 2 条未映射；页面限制面板 8 条（仅美国、记录≠产品、无预测、覆盖变化、实体映射、不可排名、赛道映射、召回≠技术） |

证据：`out/acceptance/02-companies-1440.png`、`03-company-mindray-1440.png`（整页）、`04-company-mindray-window3.png`、`05-claim-evidence-panel.png`。

### 4.2 场景 2 — 比较竞争对手：Medtronic vs Philips — **PASS**

入口：`#/compare`（默认已选美敦力+飞利浦）→ 指标"公开审批/许可记录"→ 5 年 → 季度 → "应用对比"。

| 检查点 | 实测观测 |
| --- | --- |
| 同赛道/同指标/同窗口 | 头部明确"近 5 年 / 季度 / 公开审批/许可记录"；对比组合标签可增删（2–5 家） |
| 可比性警告 | 页面首要位置渲染 1 条 medium 警告："所选企业的监管路径结构差异明显（PMA 占比相差 30 个百分点以上），审批记录数不宜直接横比，请优先看赛道内占比与专业化指数。"（`pathway_mix`） |
| 数字 | 美敦力：窗口内合计 **2,734**、仅完整周期 **2,713**、前窗 3,548、Δ -814、-22.9%、PMA/510(k) 87%/13%、未映射 **208**；飞利浦：166 / 166 / 184、-9.8%、15%/85%、未映射 18 |
| 可比性解释 | 面板脚注明确："窗口内合计包含数据截止所在的不完整周期（partial_total）；仅完整周期用于趋势比较。未映射记录不进入赛道统计，但也不代表零活动。"；另附 4 条可比性说明（路径差异/美国记录≠全球/源起点不同/因此同时给占比与 LQ） |
| 赛道矩阵 | 28 条赛道，含记录数、企业内占比、专业化指数 LQ；如美敦力心脏节律 1,111（41% · LQ 3.42）、飞利浦超声 31（19% · LQ 8.11），并声明"LQ 不是创新能力或市场地位" |
| 防陈旧/防误导 | 取消美敦力后显示"选择无效 / 需要 2–5 家企业"，旧图表 `staleChartVisible=false`，并说明"旧图表与警告已被清除"；"恢复默认"按钮可恢复 |

证据：`out/acceptance/06-compare-medtronic-philips.png`（整页）、`30-compare-totals-1440.png`。

### 4.3 场景 3 — 分析技术趋势：呼吸与通气 / 呼吸与麻醉 — **PASS**

入口：`#/radar/respiratory`（近 10 年）。

| 检查点 | 实测观测 |
| --- | --- |
| 相关企业 | 企业构成 14 家（激励医疗 56、瑞思迈 23、麦朗 10、美敦力 9、迈瑞 8、德尔格 6…），副标题"已归属 **128** / 赛道合计 **570** 条" |
| 归属透明 | 表中追加"未归属企业 **442**（**77.5%**）"行，并注明"企业构成只统计能归到具体企业的记录；未归属记录仍计入赛道总量与份额分母，因此企业份额之和不等于 100%" |
| 历史/趋势 | 窗口 2016-11-01→2026-10-30（对照 2006-11-04→2016-10-31）；近 10 年 570 vs 前窗 763（-25.3%，Δ -193）；全时 4,091；季度堆叠图 1,382px，41 个季度（完整 40 个） |
| 重要公开事件 | "最近事件"30 条，逐条带日期/类型/企业/标题，点击开事件详情（如 2026-08-28 Inspire Medical PMA P130008/S123、2026-07-31 Medtronic 510(k)） |
| 趋势解释 + 观察/探测分离 | 数量面板标"观察到的事实"口径；独立的"统计探测信号"面板明确"检出 ≠ 因果 ≠ 预测"，并明确"该窗口内没有达到阈值的统计探测信号"，附方法（前 8 季度均值 z 分数，\|z\|≥2.5 且计数≥5）；不把未检出信号当作趋势 |
| 数据截止处理 | 明确标注"未完整周期：2026-Q4（API partial 标记；计数仍显示，勿与完整季度直接比较）" |
| 首次进入 | 3 家新进入企业（强生医疗科技 2019-04-19、费森尤斯 2020-02-21、麦朗 2023-06-23），注明受数据覆盖起点限制 |

证据：`out/acceptance/07-radar-respiratory-1440.png`（整页）、`23-radar-overview-1440.png`。

### 4.4 场景 4 — 从结论追溯原始证据 — **PASS**

入口：`#/companies/medtronic` → 第一条结论"查看证据" → 证据面板 → 点击事件行 → 事件详情 → 原始来源。

| 检查点 | 实测观测 |
| --- | --- |
| 结论→事件 | 证据面板复算"近窗 1,111 / 对照窗 1,552"（心脏节律赛道），并按窗口列出可点击事件行（本次 57 行，UI 列表有展示上限；`recomputed` 为全量计数） |
| 事件→详情 | 事件详情包含：事件日期/公开日期/数据可用日、来源、产品代码、赛道、企业归属方式（roster / exact_alias）、payload 摘要、限制说明 |
| 原始链接 | 实际拿到 `https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?id=P030036`（按钮"打开原始来源 ↗"），与 API `links.source_url` 一致；非伪造、非空 |
| 无链接情形 | 前端代码存在显式分支（`web/js/event.js:196-215`，无 URL 时显示"该记录没有可用的原始链接"）；当前数据 0/375,378 条空 URL，故该分支无法用真实数据触发（见 §9） |
| 空态/错误态 | 证据浏览器 0 结果时显示"该筛选下没有记录"+"重置筛选"；未知企业显示"企业画像加载失败"+错误详情+"重试" |

证据：`out/acceptance/08-event-detail-source.png`（整页）、`05-claim-evidence-panel.png`、`33-evidence-drawer.png`、`24-evidence-empty.png`、`13-error-state-404.png`。

### 4.5 场景 5 — 使用研究助手 — **PASS**

入口：`#/analyst`；问题 1"过去五年，迈瑞的超声产品发生了什么变化？"，问题 2"Medtronic 的内部研发战略是什么？"。

| 检查点 | 实测观测 |
| --- | --- |
| 确定性引擎标识 | 顶部徽标"确定性检索引擎（无 LLM）"；页面明示"不接 LLM、不需要 API Key、所有数字来自本次查询"；解析意图（企业/赛道/时间窗/指标）逐项展示 |
| 可核验答案 | 回答："近5年，迈瑞医疗在超声赛道的公开审批记录由 **32** 条降至 **28** 条（-12%）；同期该赛道全行业变化 **+4%**，份额 69.6%→73.7%。以上为观察到的记录条数变化，不是因果结论或未来预测。" |
| 表格数字 | 公开审批/许可记录 28/32；全行业对照 411→429（+4%）；"企业已映射赛道审批记录（条）" 38/46，并在方法与口径中说明"未映射记录不计入分母" |
| 证据可解析 | 证据事件 3 条，逐条打开事件详情；3/3 个 event_id 均能在 `/api/evidence/{id}` 解析，链接为真实 FDA 510(k)（K261585 / K261617 / K260846） |
| 超出范围诚实拒绝 | 问题 2 返回 `status=out_of_scope`："这个问题超出了当前数据的可回答范围：企业内部战略 / 研发投入……数据库中没有企业内部经营数据……不能给出该问题的答案。"；无编造数字、无证据事件；并列出"能做/不能做"能力边界 |
| 限制声明 | 引擎返回 5 条 limitations（仅美国、记录≠产品、赛道映射、无验证预测、实体映射风险）并逐条显示 |

证据：`out/acceptance/09-analyst-q1.png`（整页）、`10-analyst-evidence-detail.png`、`11-analyst-out-of-scope.png`、`32-analyst-example-chip.png`。

---

## 5. 独立数据完整性核查（不采信产品自述）

> UI = 浏览器实际渲染文本；API = `GET /api/...`；SQL = 独立只读 SQLite 复算（`mode=ro`）。

| # | 项目 | UI 实测 | API | 独立 SQL / 文件 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 1 | 事件总数 | 375,378（总览 KPI） | `meta.dataset.counts.events=375,378` | `COUNT(*) events=375,378` | PASS |
| 2 | 赛道映射 | "已映射 196,542 / 未映射 **178,836**"，覆盖 52.4% | `track_mapped_events=196,542`、`track_unmapped_events=178,836` | 196,542 + 178,836 = 375,378；196,542/375,378 = 52.36% | PASS |
| 3 | 迈瑞基础计数 | 事件 244 / 审批 180 / 召回 64 / 试验 0 | `/api/companies/mindray` 一致 | 按 10 条精确申请人字符串 SQL：510(k) 180 + 召回 64 = 244 | PASS |
| 4 | 迈瑞 5 年窗口 | "已映射赛道审批 38 · 另有未映射 2 条" | `approvals_window=38`、`approvals_window_all=40`、`unmapped_window=2`、前窗 46/50/4 | SQL：已映射 38 / 前窗 46；全量 40 / 50；38+2=40、46+4=50 | PASS |
| 5 | 迈瑞超声结论 | 32→28（-12%）；份额 69.6%→73.7% | claim metrics 28/32；`/api/evidence/claim` recent=28、prior=32 | SQL：迈瑞×超声 28/32；全行业 429/411 | PASS |
| 6 | 比较页总量 | 美敦力 2,734 / 仅完整 2,713 / partial 21 / 前窗 3,548 / 未映射 208；飞利浦 166/166/184/18 | `/api/compare` 同值（`total/total_complete/partial_total`） | SQL：美敦力窗口审批 2,734、前窗 3,548；飞利浦 166、184 | PASS |
| 7 | 呼吸赛道 | 570 vs 763（-25.3%）、全时 4,091；已归属 128 / 赛道合计 570；未归属 442（77.5%） | `totals.recent=570`、`prior=763`、`all_time=4,091`；`attribution.attributed_recent=128`、`unattributed_recent=442` | SQL：recent 570、prior 763、all_time 4,091；roster 归属 114 + 补充精确别名 14（迈瑞 8 / 德尔格 6）= 128，570-128 = 未归属 442 | PASS |
| 8 | 雷达窗口映射 | "已映射 11,472 / 未映射 4,886（覆盖 70.1%）" | `radar.mapped_records=11,472`、`unmapped_records=4,886` | 11,472/(11,472+4,886)=70.13% | PASS |
| 9 | claims 证据复算 | 18 条可见结论（3 家抽样页） | `POST /api/evidence/claim` 逐条 `recomputed` | 18/18 与 claim.metrics 及独立 SQL 三方一致；如美敦力心脏节律 1,111/1,552、飞利浦超声 31/15、迈瑞监护 5/11 | PASS |
| 10 | 来源 URL | 事件详情链接均为真实域（fda.gov / clinicaltrials.gov / sec.gov） | `links.source_url` 与 event.url 一致 | 375,378/375,378 非空且 http(s)；294,756 条 payload ID 与 URL 100% 匹配，0 条不一致；召回 `res_event_number`、8-K accession 抽样一致 | PASS |
| 11 | 研究实验室 | Lab 5 项研究；S-027「69 份证据包 / 人工真值未完成」，`PENDING_HUMAN_REVIEW`；C43 未合并；预测注册表"无已验证的前瞻校准" | `human_review.packets=69`、`human_labels_recorded=0`、agent 预标注 45/18/6；`provenance.hist_v1.merged=false`；`C43` report artifact 已提供 | CSV `HUMAN_REVIEW_WORKSHEET.csv` 69 行、`human_label` 非空 0 行；`git merge-base --is-ancestor 969fd0c HEAD` exit 1 | PASS |
| 12 | 研究助手证据 | 3 条证据均可打开事件详情 | Q1 evidence 3 条；Q2 `status=out_of_scope`、evidence=[] | 3/3 event_id 可解析为真实事件，URL 为 K261585/K261617/K260846 | PASS |

补充反造假核对：

- **无伪造 URL**：数据库层面 `url` 为空 0 条、非 http(s) 0 条；产品只渲染 API 返回的链接（`web/js/event.js`），没有拼接/生成 URL 的逻辑证据。
- **无经验证预测**：全站文本扫描未出现"已验证预测/验证过的预测"的正面展示；研究实验室明确"无已验证的前瞻校准"；总览与各页反复声明"当前没有经过前瞻验证的预测模型"。
- **Dräger / Mindray 补充映射**：两家企业页均显示"补充映射 · 待人工复核"、`PENDING_HUMAN_REVIEW`、接受字符串清单与置信度；Dräger 另有 `reject_exact: ["Drager Safety"]`。
- **69 包 / 0 人工标签**：API 与 CSV 双侧一致（45 Uncertain / 18 Routine Iteration / 6 Not Assessable，均 agent-preliminary）。
- **hist_v1 未合并**：分支 `research/full-history-v1` 存在，commit `969fd0c` 不是 HEAD 祖先（`is-ancestor` exit 1）；Lab provenance 明确 `merged=false` 并注明只读引用。
- **负结果可见**：C43「未击败双向暴露基线 B3、MDE 大于观测效应、泄漏修复」；R-change-detection「2% 误报下仅回收 0.223、2 倍位移不可检测」；R-forecast-registry「无成熟前瞻样本」。

---

## 6. 限制与声明可见性（逐项核对）

| 必需限制 | 是否可见 | 实际位置/原文（抽样） |
| --- | --- | --- |
| 仅美国数据（US-only） | 是 | 总览限制第 1 条"监管数据只覆盖美国 FDA 记录…"；企业页/比较页/研究助手 limitations 同款 |
| 记录 ≠ 产品（record not product） | 是 | 总览"一条记录不等于一个产品…"；比较页脚注；企业页口径说明；研究助手 limitations |
| 赛道映射覆盖（track mapping） | 是 | 总览 KPI 52.4%（196,542/178,836）；雷达"覆盖 X%"；企业页"未映射 N 条，未映射不等于零活动"；赛道矩阵排除未映射 |
| 召回 ≠ 研发（recall not R&D） | 是 | 总览限制"召回记录是安全性事件…"；企业 KPI"安全性事件，不是技术活动" |
| 无经验证预测（no validated prediction） | 是 | 总览"没有经过前瞻验证的预测模型"；证据分层表"Validated Forecast：当前没有，产品不展示"；研究实验室"无已验证的前瞻校准"；研究助手"经过验证的未来预测（当前没有成熟的前瞻校准）" |
| 人工标签未完成 | 是 | Lab：69 份证据包 / 人工真值未完成 / `PENDING_HUMAN_REVIEW`；总览限制第 10 条 |
| 数据源起点不同 | 是 | 总览来源表（召回 2002 起、8-K 2015 起）；比较页可比性说明 |
| 事件日期/可用日期差异 | 是 | 事件详情 dates 区块；证据浏览器"日期口径"说明 |

---

## 7. 测试命令、结果与质量观测

### 7.1 自动测试与 E2E

| 命令 | 结果 |
| --- | --- |
| `python -m pytest tests/test_product_api.py tests/test_product_store.py tests/test_product_analyst.py -q` | **exit 0，71 项通过**（test_product_api 7、test_product_store 20、test_product_analyst 44）；日志 `out/acceptance/pytest_final.log` |
| `node scripts/product_e2e.cjs` | **6 passed, 0 failed**（五个场景 + 移动 390px，`horizontal overflow=0px`）；报告 `out/product_e2e/report.json`（`console_errors: []`，ran_at 2026-11-03T04:10:17Z） |
| 独立 Playwright 复跑（自写，隔离上下文） | 21 个检查步骤通过；0 pageerror；仅 1 条 console error，为"故意访问不存在企业"触发的预期 `/api/companies/nope` 404 |
| 全量 pytest 收集 | `python -m pytest --co -q` exit 0（仓库测试可收集，未发现导入/collect 错误） |

### 7.2 API 暖缓存延迟（本地笔记本，3 次中位数）

| 端点 | ms |
| --- | --- |
| `/api/meta` | 16 |
| `/api/companies?include_all=true` | 16 |
| `/api/companies/mindray?years=5` | 15 |
| `/api/compare?...` | 15 |
| `/api/radar?years=3` | 15 |
| `/api/radar/respiratory?years=10` | 15 |
| `/api/evidence?limit=50` | 16 |
| `/api/lab` | 7 |

架构文档声称"主要页面 < 300ms"，与暖缓存实测一致；"首次冷启动 3–5 秒预热"未验证（未重启 8787 服务）。

### 7.3 UI 质量清单

| 检查项 | 结果 |
| --- | --- |
| 加载态 | PASS：路由延迟 2.5s 时页面显示骨架屏（`.skeleton/.sk-line` 9 个节点），截图 `14-loading-state.png` |
| 空态 | PASS：`#/evidence` 搜索无结果 → "该筛选下没有记录" + "重置筛选"（`24-evidence-empty.png`）；注意见 §8 R1 重复文案 |
| 错误态 | PASS：未知企业 → "企业画像加载失败 / 接口 404 / unknown company" + "重试"（`13-error-state-404.png`） |
| 死按钮 | 未发现：导航 7 路由、图表点击→证据筛选、结论"查看证据"、比较非法选择→恢复默认、证据分页/重置/搜索、研究助手示例 chip、雷达领域卡→赛道页均实测有响应 |
| 全局检索 | 头部输入 `PMA` 回车 → `#/evidence?q=PMA` |
| 控制台 | 仅预期 404；0 pageerror |
| 移动端 390×844 | 总览/企业页/雷达赛道/研究助手 4 路由横向溢出均为 0px；折叠菜单可展开（`15–19-mobile-*.png`）；宽表在移动端变为逐字段堆叠，可用但阅读成本高（见 R2） |
| 桌面 1440×900 | 总览/企业/比较/雷达/助手/Lab 布局正常，无横向溢出，数据密度符合"研究终端"定位 |

---

## 8. 已知问题 / 缺陷

### 8.1 审计期间已发现并修复（最终版复验通过）

| # | 缺陷（审计发现时） | 修复（commit） | 最终版实测 |
| --- | --- | --- | --- |
| D1 | 企业 KPI「审批记录（近 5 年）」只含已映射赛道却未标注：迈瑞 38 vs 原始 40；美敦力 2,526 vs 2,734；飞利浦 148 vs 166 | `838b854` | 现为"已映射赛道审批（近 5 年）38 · 另有未映射 2 条"，美敦力"2,526 · 另有未映射 208 条"；API 增 `approvals_window_all/unmapped_window/window_basis_zh` |
| D2 | 比较页「窗口内」总量按粒度静默剔除不完整周期（quarter 2,713 vs 原始 2,734） | `838b854` | 现为「窗口内合计 2,734 / 仅完整周期 2,713」并在表下解释 partial_total 含义 |
| D3 | 雷达赛道「企业构成」只列 14 家（128/570），页面/API 未披露 442 条未归属 | `838b854` | 副标题"已归属 128 / 赛道合计 570 条"，表内"未归属企业 442（77.5%）"，并注明份额分母仍为全赛道 |
| D4 | 研究助手表格「企业全部审批记录 38/46」措辞与"不含未映射"矛盾 | `838b854` | 改为「企业已映射赛道审批记录（条）」并在方法与口径说明未映射不计入分母 |
| D5 | 总览「赛道映射覆盖 52.4%」副标题把 `unattributed_events=243,085`（企业未归属）当作"未映射赛道"，导致 196,542+243,085=439,627 与事件总数矛盾 | `22817c5` | 现为"已映射 196,542 / 未映射 **178,836**"（196,542+178,836=375,378）；`/api/meta` 新增 `track_unmapped_events` 与 `attribution_note_zh`；截图 `34-overview-kpi-mapping.png` |

### 8.2 残留问题（不阻塞五场景，建议后续修）

| # | 严重度 | 问题 | 说明 / 建议 |
| --- | --- | --- | --- |
| R1 | 低 | 证据浏览器 0 结果时空态重复渲染：同页出现两处"该筛选下没有记录"，且仍显示"第 1 / 1 页"分页器 | 截图 `24-evidence-empty.png`；建议去重并隐藏无意义分页 |
| R2 | 低 | 移动端 390px 宽表（最近事件/证据列表）压成逐字段纵向堆叠，可用但阅读成本高 | 截图 `17-mobile-company-390.png`；建议移动端卡片化或横向滚动 + 粘性表头 |
| R3 | 低 | 文档口径小不一致：`PRODUCT_VISION.md` 写"59 个医疗技术赛道/17 个真实赛道"，实测 tracks 表 60、8 领域引用 18 条赛道 | 建议更新文档或统一口径 |
| R4 | 低 | 总览 KPI「技术赛道 60 · 8 个技术领域」与雷达实际覆盖 18 条并列，初读易误解（60 含药品/疗法分类） | 建议 caption 区分"事件分类 60（含药品/疗法）/ 器械雷达 18" |
| R5 | 低 | 证据浏览器关键词 `q` 为英文原文 LIKE（title/applicant_raw/summary），不支持中文语义 | UI 已明示该限制；属已知设计边界 |
| R6 | 中低 | 无真正 point-in-time/as-of 回放：`first_seen_at` 仅 2 个值（2026-10-30/31），`available_at == published_at` 375,378/375,378 | 事件详情仅给日期提示，未显式说明"不能回放当时可见性"；Roadmap 已列 P0，建议 UI 明示 |
| R7 | 低 | 旧 `docs/dashboard.html`（3.2MB 单文件）仍在且未接入 2.0 导航，两套界面并存 | 不影响五场景（导航无死链）；建议文档标注或下线 |
| R8 | 信息 | "该记录没有可用的原始链接"分支存在于 `web/js/event.js:196-215`，但当前 0/375,378 空 URL，无法在真实数据上触发验证 | 该能力**未被真实数据验证**（见 §9） |
| R9 | 低 | 赛道页 KPI「近 10 年记录 570」含 2 条不完整季度记录，与"完整 40 个季度"并列需读者自行注意 | 图表已显式标注 2026-Q4 partial；可考虑与比较页一致地拆分"合计/完整周期" |
| R10 | 信息 | 同页出现两个"企业"数字：KPI「收录企业（名册）53」与页脚「企业 89（有事件）」 | 均有标签，可接受；若面向普通读者建议加一句口径说明 |

**交付前追加修复（在本报告审计之后，不改变五场景 PASS 结论）**：R1（证据空态去重、0 结果隐藏分页器）、R3（文档口径统一为 60 条分类 / 18 条雷达赛道）、R4（总览 KPI 标注「全库分类；雷达展示 18 条重点赛道」）、R6（证据浏览器新增「时点回放限制」说明）、R9（赛道 KPI 标注含数据截止所在未完整季度）、R10（页脚区分「有事件企业」与「产品名册」）。R2（移动端宽表可读性）、R5（q 仅英文原文匹配）、R7（旧 dashboard 未接入）、R8（空链接提示未被真实数据触发）保留为已知边界，列入 [`PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md)。

> 本报告的 PASS/FAIL 基于 commit `22817c5` 实测；上述追加修复仅涉及标签与空态文案，不改变任何数字口径或五场景结论。

---

## 9. 未验证 / 不可用（明确边界）

以下内容本次审计**没有**或**无法**验证，不应被当作已验收能力：

1. **没有经过前瞻验证的预测**：产品不展示预测（已核实其"不展示"）。五家企业早期信号研究 69 份证据包 **0 条人工标签**，研究处于 blocked；C43 为混合结论（H1 边际支持，但 MDE 大于观测效应且未击败强基线 B3），不构成实用预测。任何"预测能力"均不可用。
2. **没有全球（美国以外）监管数据**：只有美国 FDA 记录 + 部分全球临床试验注册；迈瑞/德尔格的美国记录不代表其全球活动。界面已声明，但产品不能回答"全球注册/销售/市场份额"类问题。
3. **没有企业内部数据**：研发战略、研发投入、营收、份额均无字段；研究助手对"Medtronic 内部研发战略"正确返回 out_of_scope。
4. **无人工真值标签**：69 包只有 AI 规则化预标注（45/18/6），不能作为研究结论或检测器评分依据。
5. **`research/full-history-v1` 未合并**：仅只读引用 commit `969fd0c` 的冻结产物；产品不包含该分支代码/结论。
6. **point-in-time / as-of 不可用**：见 R6，无法严格回答"当时能看到什么"。
7. **无空 URL 真实样本**："没有可用原始链接"提示路径存在，但当前数据 0 条空 URL，该分支未被真实数据触发（R8）。
8. **外部来源可达性未逐条验证**：本次只验证 URL 结构与 payload ID 一致；尝试抓取 FDA/SEC 时分别遇到人机校验/403（自动化访问限制），**未**验证每条链接当前 HTTP 200。
9. **冷启动性能未验证**：未重启 8787 服务；"首次 3–5 秒预热"只有文档声明。
10. **未做多浏览器/无障碍/安全/压力测试**：仅 Chrome（Playwright）；未测 Firefox/Safari、屏幕阅读器、并发压力、越权/注入等。
11. **移动端只覆盖 4 个路由 + 导航**：其余路由未在 390px 逐页验收（桌面 1440×900 覆盖全部主要页面）。
12. **数据新鲜度/增量采集未验证**：使用 2026-10-30 的冻结快照；未验证定时采集、源更新、失败重试。
13. **既有 Research Agent CLI 未实际运行**：Lab 中仅核对了研究记录与元数据，未执行其 CLI 模板。

---

## 10. 最终验收结论

**是：这是真实可用的 MVP（五个场景均 PASS），但它是"证据驱动的医疗技术研究终端"，不是预测产品。**

- **真实**：375,378 条真实公开记录、6 个真实数据源、18/18 条企业结论可逐条复算到事件、事件可展开到真实 FDA/ClinicalTrials.gov/SEC 链接；UI 数字与 API、SQLite 独立复算一致。
- **可用**：非工程用户可在无需脚本的情况下完成五个场景；加载/空/错误态完整，无死按钮，桌面与 390px 移动端基本可用；控制台无异常（除故意的 404 测试）。
- **诚实**：主动暴露赛道映射覆盖（52.4%）、企业归属覆盖、未映射记录、69 包 0 人工标签、hist_v1 未合并、无经验证预测；比较页主动警告路径差异、不诱导排名。

**仍然偏弱的环节**（决定它还不是"完整产品"）：

1. **覆盖与归属**：全库赛道映射仅 52.4%（窗口级 70.1%）；企业归属覆盖不足（呼吸赛道仅 22.5% 记录能归到企业），很多企业的"活动"只能看赛道总量，不能看企业构成。
2. **时点能力**：无法做真正的 point-in-time 复盘（first_seen 不可用），削弱"当时可发现"类研究叙事。
3. **数据边界**：仅美国监管记录，非美企业（迈瑞/德尔格）覆盖天然偏低，比较时必须依赖现有警告。
4. **科研闭环**：69 份证据包人工复核未完成、预测注册表无成熟前瞻样本——研究结论不能产品化为预测。
5. **体验细节**：移动端宽表、证据空态重复文案、文档口径小不一致等低严重度问题仍需打磨。

**验收建议**：按"带明确限制声明的证据研究 MVP"发布/交付；对外表述必须保留"记录数不是产品数、不是创新能力排名、当前没有经验证预测"三条；下一阶段优先级仍是赛道映射覆盖率、实体映射治理、point-in-time 能力与 69 包人工复核。

---

## 11. 证据索引

**截图（`out/acceptance/`，gitignored 构建产物）**

| 场景/状态 | 文件 |
| --- | --- |
| 总览 + KPI | `01-overview-1440.png`、`34-overview-kpi-mapping.png` |
| 场景 1 企业列表/迈瑞/窗口切换/证据面板 | `02-companies-1440.png`、`03-company-mindray-1440.png`、`04-company-mindray-window3.png`、`05-claim-evidence-panel.png` |
| 场景 2 比较 | `06-compare-medtronic-philips.png`、`30-compare-totals-1440.png` |
| 场景 3 雷达 | `07-radar-respiratory-1440.png`、`23-radar-overview-1440.png` |
| 场景 4 追溯 | `08-event-detail-source.png`、`33-evidence-drawer.png` |
| 场景 5 助手 | `09-analyst-q1.png`、`10-analyst-evidence-detail.png`、`11-analyst-out-of-scope.png`、`32-analyst-example-chip.png` |
| 状态 | `12-evidence-empty-state.png`、`13-error-state-404.png`、`14-loading-state.png`、`24-evidence-empty.png` |
| 移动端 390 | `15-mobile-overview-390.png`、`16-mobile-nav-390.png`、`17-mobile-company-390.png`、`18-mobile-radar-390.png`、`19-mobile-analyst-390.png` |
| 研究实验室 | `20-lab-1440.png`、`21-lab-s027.png`、`22-lab-c43.png`、`25-lab.png`、`31-lab-c43-1440.png` |
| 企业（美敦力/德尔格） | `28-company-medtronic-1440.png`、`29-company-draeger-1440.png` |

**报告与日志**

- `out/product_e2e/report.json`（E2E 6/6，console_errors 为空）
- `out/acceptance/pytest_final.log`（71 项通过，exit 0）
- `out/acceptance/replay_report.json`（独立浏览器复跑 21 步）
- `out/acceptance/dump_report.json`、`out/acceptance/interact_report.json`、`out/acceptance/profile_frozen_report.json`
- `%TEMP%\medradar_audit\audit_report.json`（API + SQLite 独立复算原始数据，审计机临时目录）
- 页面文本快照：`out/acceptance/texts/*.txt`（企业、比较、雷达、研究助手、Lab、证据空态等）

**关键接口/文件**

- `GET /api/health`、`GET /api/meta`、`GET /api/companies/mindray?years=5`、`GET /api/compare?...`、`GET /api/radar/respiratory?years=10`、`POST /api/evidence/claim`、`POST /api/analyst/ask`
- `data/medradar.sqlite`（只读）、`medradar/product/entity_aliases.json`、`research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv`
