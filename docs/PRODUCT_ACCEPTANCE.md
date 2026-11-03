# MedRadar 2.0 — 统计修复后独立验收报告（commit `5a349f4`）

> **验收对象**：`D:\DEPPSKK\medradar` · 分支 `feat/medradar-2.0-mvp` · 审计锚点提交 **`5a349f4e230cbba911d5c623ae83bb173b601c77`**（`fix(product): consistent LQ denominators, complete-quarter windows, PMA classification`）
> **数据**：`data/medradar.sqlite`（1,368,469,504 bytes，mtime `2026-10-31T05:28:25Z`），data edge **2026-10-30**，events **375,378**
> **产品**：`2.0.0-mvp`，服务 `http://127.0.0.1:8787`（审计期间未重启）
> **验收人**：独立验收员 `verifier2`（与实现者、Lead 相互独立）· 审计时间：2026-11-03 21:19–21:38（Asia/Shanghai）
> **结论**：**五个必需场景在 1440×900 与 390×844 两种视口均 PASS；关键统计口径已与只读 SQL 独立复算一致；旧缺陷具备“若回归则测试会失败”的回归测试。未发现阻断性产品缺陷。** 但发现 **1 个报告级数字错误（Lead 审计 §2.4）**、**1 个潜在分类不一致（当前真实数据 0 例）**、**2 个低严重度披露/API 缺口**，以及交付前需 Lead 处理的工作区未提交文件。本产品仍是“证据型研究终端”，不是预测产品。

---

## 0. 结论摘要

1. **五场景全 PASS**：迈瑞企业画像、美敦力 vs 飞利浦比较、呼吸与麻醉雷达、结论→证据→事件→来源链路、研究助手（含 out_of_scope），在 1440×900 与 390×844 各自独立复跑，共 **10/10 PASS**，**0 个控制台错误、0 个横向溢出**；截图见 `out/acceptance2/`。
2. **统计口径复算一致**：LQ 的旧分母错误可精确复现（旧 3.417/8.114/3.520/0.912/0.021），新口径与 API 完全一致（3.721/9.323/4.042/1.068/不适用）；`/api/compare` 全部 **56 个 LQ 单元格**均可由响应自带的已映射分母复算（34 ok + 22 不适用，0 例外）。
3. **完整季度窗口成立**：请求窗口 2021-10-31–2026-10-30 → 完整分析窗口 **2022-01-01–2026-09-30（19 个季度）**，对照 **2017-04-01–2021-12-31（19 个季度）**，紧邻无缝隙；不完整季度记录（139 条）被排除并单独披露；`source_lag_risk` 仅 2026-Q3 且与 `partial` 分离。
4. **PMA 分类可用**：57,372/57,372 条 PMA 有 `supplement_number`（0 条 unknown），176,466/176,466 条 510(k) 有 `clearance_type`；美敦力 5 年完整窗口原始/补充 = **7 / 2,423**，飞利浦 = **1 / 38**；首次进入已排除 Special 510(k)（真实数据示例：飞利浦呼吸赛道首条 2003-07-15 为 **Special** 510(k)，产品正确取 2011-10-04 的 Traditional 510(k)）。
5. **测试可信**：Tier A/B **21 passed**、Tier C **74 passed**、全量 **1,169 passed + 224 subtests**、仓库 E2E **6/6**、selftest **1,074 OK**，全部 exit 0，**0 skipped**。旧恒真断言 `... or True` 已删除；LQ 分母、起始不完整季度、补充申请误作首次进入三类历史缺陷，若回归均会使现有测试失败（逐项论证见 §5.2）。
6. **诚实性边界成立**：迈瑞/德尔格为 `PENDING_HUMAN_REVIEW`；研究实验室 69 份证据包 **0 条人工标签**；`research/full-history-v1` 未合入 main；无经验证预测；限制在总览/企业页/雷达页/研究助手/实验室可见；`main` 未被改动（`b2a14c0`）；PR #12 仍为 **Draft / OPEN**，head = `5a349f4`。
7. **发现的问题**（详见 §7）：
   - **D1（Major，文档）**：`docs/PRODUCT_STATISTICAL_AUDIT.md` §2.4 的“本期/上期”请求窗口数字**写反**（实际本期请求窗口 1,111、上期请求窗口 1,552；审计写成 1,552/1,111）。产品自身 1,051/1,480 正确。
   - **D2（Medium，潜在产品缺陷）**：PMA 分类的 SQL 谓词与 Python 分类器对“**合法 JSON 但缺 `supplement_number`**”不一致——SQL 计为原始批准，Python/数据集审计计为 unknown。真实数据当前 **0 例**，不影响已观测数字，但属静默误分类风险，且无测试覆盖该形态（fixture 只覆盖 malformed JSON）。
   - **D3（Low，API/文档缺口）**：`/api/compare` 路由不接受 `include_all_time` 参数，`pathway_all_time` 经 HTTP 永远为 `null`（store 层支持，但 API 未透传）；审计称“需 `include_all_time=true`”，该能力实际不可经 API 触发。UI 已明确提示未请求，无数值错误。
   - **D4（Low，标注清晰度）**：企业页 PMA 拆分 KPI（7 + 2,423）与路径结构分母（2,595）包含未映射赛道的审批记录，而 headline“已映射赛道审批”= 2,396；旁侧蓝色提示已给出 2,396 + 199 = 2,595，但 KPI 标签本身未写“含未映射”。
   - **D5（Info，发布状态）**：审计期间工作区存在未提交的 `README.md`、`docs/PRODUCT_ROADMAP.md`（并行文档编辑，非本审计员写入，未包含在 `5a349f4`）；用户 CSV 仍仅为本地修改。`main`/PR 未受影响，但交付前需 Lead 决定这些文件的去留。

---

## 1. 审计锚点与环境（可复现事实）

| 项目 | 实测值 | 来源 |
| --- | --- | --- |
| 仓库 / 分支 | `D:\DEPPSKK\medradar` / `feat/medradar-2.0-mvp` | `git status` / `git branch --show-current` |
| HEAD | `5a349f4e230cbba911d5c623ae83bb173b601c77` | `git rev-parse HEAD` |
| `main` / `origin/main` | 均为 `b2a14c0a92332c004445de686daee97754cf94cb`；`5a349f4` **不是** main 祖先（`merge-base --is-ancestor` exit 1） | `git rev-parse` / `git merge-base` |
| PR | #12 `MedRadar 2.0 MVP: ...`，**OPEN / Draft**，`headRefName=feat/medradar-2.0-mvp`，`headRefOid=5a349f4…`，base=main | `gh pr view 12` |
| 服务 | `http://127.0.0.1:8787`，`/api/health` → `status=ok`、`product=2.0.0-mvp`；进程 `python -m medradar web --port 8787`（2026-11-03 21:19:21 +0800 启动，cwd=`D:\DEPPSKK\medradar`） | Invoke-RestMethod / `Get-CimInstance Win32_Process` |
| 数据文件 | `data/medradar.sqlite`，1,368,469,504 bytes，mtime `2026-10-31T05:28:25Z`；只读 `mode=ro` 打开，审计期间未修改（WAL 0 字节） | 文件系统 / `/api/health` |
| 数据范围 | `1966-12-14` → **`2026-10-30`** | `SELECT MIN/MAX(event_date)` |
| 事件规模 | **375,378**（event_id 去重后同为 375,378） | 只读 SQL |
| 来源构成 | 510(k) 176,466 · PMA 57,372 · 器械召回 59,646 · 临床试验 55,592 · 8-K 20,976 · 药品批准 5,326 | 只读 SQL |
| 分类维度 | 赛道已映射 196,542 / 未映射 178,836（覆盖率 **52.36%**）；企业已归属 132,293 / 未归属 243,085；companies 表 89 家、tracks 60、product_codes 7,097 | `/api/meta` + SQL |
| 审计时工作区 | `M README.md`、`M docs/PRODUCT_ROADMAP.md`（并行文档编辑，非本审计员）、`M research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv`（用户本地修改）；产品代码/测试/前端均干净 | `git status --short` |

> 说明：服务只暴露产品版本号，**不能字节级证明运行进程的代码 commit**；本报告依据“进程 cwd + 产品代码相对 HEAD 干净 + 行为与 HEAD 测试一致”判定其运行 `5a349f4`，未做进程内存指纹（见 §8）。

---

## 2. 方法与独立性声明

1. **不信任 Lead 审计**：`docs/PRODUCT_STATISTICAL_AUDIT.md` 只作为“待验证的主张清单”；所有数字用**自写只读 SQL**（`sqlite3` `mode=ro`，不调用 `medradar.product.store` 的聚合函数）重算，再与 API/UI 对照。
2. **只读数据**：`data/medradar.sqlite` 以 `file:...?mode=ro` 打开；未写入、未迁移、未重启服务、未修改任何产品代码或测试；唯一写入范围是 `docs/PRODUCT_ACCEPTANCE.md`（本文件），截图/脚本在 `out/acceptance2/`（已 gitignore）。
3. **浏览器独立复跑**：自写 Playwright 脚本 `out/acceptance2/browser_scenarios.cjs`，不复用仓库 E2E 的判定逻辑；1440×900 与 390×844 两个隔离 context，每场景记录 DOM 文本 + 自取 API + 截图，并收集 console error/pageerror。
4. **API 自身字段复算**：LQ 用 `/api/compare` 响应中的 `n / total_mapped / industry_total / industry_records.mapped_records` 重算，验证“披露字段 ↔ 指标”自洽。
5. **测试执行**：按 Tier A/B、Tier C、全量、E2E、selftest 分层执行并记录命令、计数、退出码、skip；逐条阅读测试代码，回答“旧缺陷若回归是否会被抓住”。
6. **Git/产物核验**：`git rev-parse/log/status/diff --cached/merge-base`、`gh pr view`、`git cat-file`；CSV 仅读取与 diff 检查，未 touch/暂存/提交。
7. **时间边界**：审计于 2026-11-03 21:19 开始；期间工作区出现并行文档修改（README、PRODUCT_ROADMAP），已在 §1/§7-D5 记录，不影响 `5a349f4` 与五场景判定。

---

## 3. 五个必需场景验收（1440×900 + 390×844）

### 3.0 场景总表

| # | 场景 | 1440×900 | 390×844 | 关键实测数字 | 截图（`out/acceptance2/`） |
| --- | --- | --- | --- | --- | --- |
| 1 | 研究一家公司（迈瑞医疗 `#/companies/mindray`） | **PASS** | **PASS** | 全时事件 244；已映射赛道审批（5 年完整季度）**34**；窗口全部 40；完整窗口全部（已映射+未映射）36；结论 3 条；8 条限制；`PENDING_HUMAN_REVIEW` 可见；横向溢出 0 | `s1-company-mindray-desktop.png` / `s1-company-mindray-mobile.png` |
| 2 | 比较竞争对手（Medtronic vs Philips `#/compare`） | **PASS** | **PASS** | 分析窗口 2022-01-01→2026-09-30（19 季度），对照 2017-04-01→2021-12-31；28 条赛道矩阵 / 56 个 LQ 单元格（34 ok + 22「不适用」）；3 条警告；LQ 3.72 / 9.32 / 4.04 / 不适用 | `s2-compare-desktop.png` / `s2-compare-mobile.png` |
| 3 | 分析技术趋势（呼吸与麻醉 `#/radar/respiratory`） | **PASS** | **PASS** | 完整周期 560 vs 740（-24.3%）；窗口全部 570；partial 10；全时 4,091；39+2 个季度；3 家新进入；14 家企业；未归属 435/560（77.7%）；无统计探测信号 | `s3-radar-respiratory-desktop.png` / `s3-radar-respiratory-mobile.png` |
| 4 | 追溯结论到原始证据（结论→查看证据→事件→详情→来源） | **PASS** | **PASS** | 结论复算显示“近窗 **1,051** / 对照窗 **1,480**”；事件 `fdfacf2f…`；`approval_type=pma_supplement`；来源链接与 API 一致（`pma.cfm?id=P980016`） | `s4-evidence-trace-desktop.png` / `s4-evidence-trace-mobile.png`；`s4a-claim-evidence-panel.png` |
| 5 | 使用研究助手（`#/analyst`，含 out_of_scope） | **PASS** | **PASS** | 迈瑞超声 **24 vs 32（-25%）**、行业 **+6%**、份额 **69.6%→70.6%**；证据 3 条；越界问题返回“超出范围”，无编造数字 | `s5a-analyst-answered-desktop.png` / `...-mobile.png`；`s5b-analyst-outofscope-desktop.png` / `...-mobile.png` |

补充证据：`s6-draeger-pending-desktop.png`（德尔格 PENDING）、`s7-lab-desktop.png`（研究实验室）、`s8-overview-desktop.png`（总览限制）、`s9-mobile-claim-evidence.png`（移动端证据面板）、`s10-mobile-analyst.png`、`s11-lab-s027-detail.png`。

> **截图仓库等价物**：仓库内 `docs/product/` 中 6 张提交截图与本次独立运行的 PNG **SHA256 完全相同**：`company-mindray.png`、`radar-respiratory.png`、`evidence-trace.png`、`analyst.png`、`mobile-company.png`、`overview.png`（证明可提交资产确实对应当前 HEAD 的真实运行）；`compare.png` 因交互状态/滚动位置不同而像素不同，但页面与数字一致。`out/acceptance2/` 为 gitignored 构建产物，不入库。

### 3.1 场景 1 — 迈瑞医疗企业画像

- 入口 `#/companies/mindray`；DOM 显示“迈瑞医疗 / Mindray / 300760 / SZSE”、`PENDING_HUMAN_REVIEW`“实体归属待人工复核”、10 条接受匹配字符串、8 条“该视图的限制”。
- KPI 实测：**已映射赛道审批（完整季度，近 5 年）34**；窗口全部记录（含起止不完整季度）**40**；完整窗口全部记录 **36（已映射 34 + 未映射 2）**；全时事件 **244**；结论 3 条（超声 24/32、监护 5/11、呼吸 5/3）。
- 边界：API `headline` 与页面文本逐项核对一致；390px 横向溢出 **0px**；console error **0**。

### 3.2 场景 2 — 美敦力 vs 飞利浦比较

- 页面明确展示“分析窗口 2022-01-01 → 2026-09-30（完整自然季度）”“请求窗口 2021-10-31 → 2026-10-30”“对照窗口 2017-04-01 → 2021-12-31 · 完整周期 19 个”。
- 企业总量：美敦力 **2,595**（已映射 **2,396** / 未映射 **199**，映射率 92.3%；前窗 3,354；Δ -759 / -22.6%）；飞利浦 **161**（143 / 18，88.8%；前窗 171；Δ -10 / -5.8%）。
- 赛道矩阵 28 行 / 56 单元格：**34 个 LQ 数值 + 22 个「不适用」**，22 个全部为 `zero_company_track`（标题提示“该企业在本完整窗口内该赛道没有已映射记录，LQ 不适用。”）。关键渲染值：心脏节律-美敦力 `1,051 · LQ 3.72`；超声-飞利浦 `31 · LQ 9.32`；监护-飞利浦 `10 · LQ 4.04`；监护-美敦力 `0 · LQ 不适用`。
- 3 条可比性警告全部渲染：`complete_quarter_basis`(info)、`pathway_mix`(medium)、`pma_supplement_share`(medium)；路径面板脚注明确“全时结构未返回（`pathway_all_time=null`，默认不请求 `include_all_time`）”。

### 3.3 场景 3 — 呼吸与麻醉雷达

- 窗口：请求 2016-11-01→2026-10-30；完整分析 2017-01-01→2026-09-30（**39 季度**）；对照 2007-04-01→2016-12-31（39 季度）。
- KPI：**完整周期合计 560**（前窗 740，-24.3%）；窗口全部 **570**；序列 partial 合计 **10**（2016-Q4=8 + 2026-Q4=2）；全时 4,091；`pma_unknown=0`。
- 归属：attributed 125 / unattributed 435（77.7%），页面明确“企业份额之和不等于 100%”。
- 新进入 3 家（按“数据覆盖期内首次原始批准”）：强生医疗科技 2019-04-19、费森尤斯医疗 2020-02-21、麦朗 2023-06-23；无达到阈值的统计探测信号（`|z|≥2.5` 且计数≥5），并展示方法与“检出≠因果≠预测”说明。

### 3.4 场景 4 — 从结论追溯原始证据

- `#/companies/medtronic` → 首条结论卡“查看证据”：面板显示 **“复算结果：近窗 1,051 条 / 对照窗 1,480 条”**，窗口 `2022-01-01 → 2026-09-30 vs 2017-04-01 → 2021-12-31`，与 `POST /api/evidence/claim` 返回的 `recomputed.recent=1051 / prior=1480` 一致，也与 SQL 重算一致。
- 点击事件行 → 事件详情：`event_id=fdfacf2f546e5000bfecbc6c84622456`，`approval_type=pma_supplement`（“PMA 补充申请”），分类区含 `approval_type` / `is_first_entry_candidate=否` / `supplement_type` / `source_fields` / 说明；详情含“企业归属（映射来源）”“日期与时间口径”“限制说明”。
- 来源链接：`https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?id=P980016`，与 `/api/evidence/{id}.links.source_url` 完全一致（未伪造）。

### 3.5 场景 5 — 研究助手

- 问题 `过去五年，迈瑞的超声产品发生了什么变化？` → `status=answered`，intent `company_track_trend`；答案核心数字：**由 32 条降至 24 条（-25%）**、同期行业 **+6%**、份额 **69.6%→70.6%**；证据 3 条；解析意图面板显示企业=迈瑞医疗、赛道=超声、请求窗口 2021-10-31→2026-10-30。独立 SQL（用 `entity_aliases.json` 的 10 条精确别名匹配，不使用产品归属函数）复算：24/32、行业 414/392（+5.6%）、份额 0.7059/0.6957，**完全一致**。
- 越界问题 `帮我预测明年迈瑞的营收` → `status=out_of_scope`，页面状态“超出范围”，明确说明无营收数据、无经验证预测模型，不给出编造答案（0 条证据）。
- 引擎徽标“确定性检索引擎（无 LLM）”可见；所有回答带限制与可打开证据。

---

## 4. 独立复算（只读 SQL + API 自身字段）

### 4.1 Location Quotient：旧公式 vs 一致分母 vs 完整窗口

公式（新口径，企业与行业都用完整窗口内**已映射赛道记录**作分母）：

```
LQ = (企业该赛道已映射记录 / 企业已映射记录)
   / (全行业该赛道已映射记录 / 全行业已映射记录)
```

旧实现（`f3ea1e4:medradar/product/store.py`，`company_compare()`）：企业侧 `share = n / company["total"]`（`total` 为**请求窗口内全部**审批记录，含未映射），行业侧 `industry_share = industry_track / industry_total`（只含已映射）。本表另给“仅统一分母但仍用请求窗口”的中间值，以区分“分母错误”和“窗口口径”两个来源。

| 企业 · 赛道 | 请求窗口企业赛道 / 企业全部 / 行业赛道 / 行业已映射 | 旧 LQ（旧分母 + 请求窗口） | 仅统一分母（请求窗口） | 完整窗口企业赛道 / 企业已映射 / 行业赛道 / 行业已映射 | 新 LQ（完整窗口） | API / UI |
| --- | --- | --- | --- | --- | --- | --- |
| Medtronic · 心脏节律 | 1,111 / 2,734 / 2,217 / 18,640 | **3.417** | 3.698 | 1,051 / 2,396 / 2,099 / 17,804 | **3.721** | 3.721 / UI 3.72 |
| Philips · 超声 | 31 / 166 / 429 / 18,640 | **8.114** | 9.101 | 31 / 143 / 414 / 17,804 | **9.323** | 9.323 / UI 9.32 |
| Philips · 患者监护 | 10 / 166 / 319 / 18,640 | **3.520** | 3.948 | 10 / 143 / 308 / 17,804 | **4.042** | 4.042 / UI 4.04 |
| Philips · 心脏节律 | 18 / 166 / 2,217 / 18,640 | **0.912** | 1.023 | 18 / 143 / 2,099 / 17,804 | **1.068** | 1.068 / UI 1.07 |
| Medtronic · 患者监护 | 1 / 2,734 / 319 / 18,640 | **0.021** | 0.023 | **0** / 2,396 / 308 / 17,804 | **null（`zero_company_track`）** | null / UI“不适用”+原因 |

- **旧/新差异来源**：企业分母从“请求窗口全部审批 2,734（含 208 条未映射）”变为“完整窗口已映射 2,396”；行业分母从 18,640（请求窗口已映射）变为 17,804（完整窗口已映射）。差异由两个变化来源叠加（分母口径 + 窗口口径），新口径内部一致。
- **API 披露字段复算**：对 `/api/compare?companies=medtronic,philips&metric=approvals&years=5&granularity=quarter` 的 **56 个单元格**，用响应自身 `cell.n / company.total_mapped / (row.industry_total / industry_records.mapped_records)` 重算，**56/56 一致**（34 个 ok 误差 < 0.0015；22 个非 ok 全部 `location_quotient=null`）。
- **不适用渲染核验**：22 个非 ok 单元格在 UI 中全部显示“不适用”，`data-lq-status=zero_company_track`，tooltip 给出具体原因；无一处以 0 或空值伪装成有效 LQ。
- 口径提示：LQ 只描述记录分布，UI/API 均声明“不是创新能力、技术实力或市场份额”。

### 4.2 完整季度窗口 vs 请求窗口

| 检查项 | 请求窗口 | 完整窗口 / 结果 |
| --- | --- | --- |
| 时间范围 | 2021-10-31 → 2026-10-30（1,825 天） | **2022-01-01 → 2026-09-30（19 个自然季度）** |
| 对照窗口 | 2016-11-01 → 2021-10-30 | **2017-04-01 → 2021-12-31（19 个季度；与本期紧邻，间隔 0 天）** |
| Medtronic 审批（全部） | 2,734 | **2,595** |
| Medtronic 审批（已映射） | 2,526 | **2,396**（映射率 92.33%） |
| Medtronic 前窗（全部 / 已映射） | 3,548 / 3,224 | **3,354 / 3,050** |
| Philips 审批（全部 / 已映射） | 166 / 148 | **161 / 143**（88.82%） |
| 行业已映射审批（LQ 分母） | 18,640 | **17,804**（同窗口行业全部 25,912，映射率 68.7%） |
| 被排除的不完整周期 | 2021-Q4（2021-11-01..12-31）**118** + 2026-Q4（2026-10-01..10-30）**21** = **139** | 2,734 − 139 = **2,595**（吻合） |
| 心脏节律赛道的不完整期记录 | 1,111 | 排除 60 条（1,111 − 60 = 1,051） |
| `partial` 与 `source_lag_risk` | — | 2021-Q4、2026-Q4 标 `partial`；**2026-Q3 日历完整但距 edge 30 天 → 仅 `source_lag_risk=true`**（两者分离，未混算） |
| 雷达（10 年） | 2016-11-01 → 2026-10-30 | 完整 **2017-01-01 → 2026-09-30（39 季度）**；对照 2007-04-01 → 2016-12-31（39 季度）；partial 2016-Q4=8 + 2026-Q4=2 = **10**；recent 560 / recent_all 570 / prior 740 / prior_all 763 |
| claims 依据 | — | 8 条美敦力结论的 `recent/prior` 逐条与“完整窗口、已映射赛道”SQL 重算一致（如心脏节律 1,051/1,480）；`claim_evidence` 返回 `recomputed` 同值 |

SQL 侧核对：分析窗口内实际出现的自然季度 = 19，对照窗口 = 19，`prior_end` 与 `analysis_start` 相隔 0 天（`2021-12-31` 的下一日即 `2022-01-01`），无重叠、无缝隙。窗口边界使用闭区间（`>= start AND <= end`）；`2021-12-31` 属于请求窗口但不在完整窗口内，`2022-01-01` 起计入本期完整窗口。

### 4.3 PMA 原始批准 vs 补充申请

**数据集分类可用性（真实数据）**

| 检查项 | 结果 |
| --- | --- |
| PMA 总数 | **57,372** |
| 缺少/无法读取 `supplement_number`（应计 unknown） | **0** |
| PMA payload 非法 JSON | **0** |
| PMA payload 为合法 JSON 但非 object | **0** |
| 510(k) 总数 | **176,466** |
| 缺少 `clearance_type` | **0** |
| `/api/meta.dataset.approval_classification` | `pma_classification_available=true`、`k510_classification_available=true`、unknown 均为 0 |

**企业分类计数（只读 SQL，`json_extract(payload,'$.supplement_number')` 空=原始、非空=补充）**

| 企业 / 窗口 | 原始 PMA | PMA 补充申请 | unknown | 510(k) Traditional | 510(k) 合计 |
| --- | --- | --- | --- | --- | --- |
| Medtronic · 5 年完整窗口（2022-01-01..2026-09-30） | **7** | **2,423** | 0 | 111 | 165 |
| Medtronic · 全时（..2026-10-30） | **100** | **12,820** | 0 | 1,386 | 1,976 |
| Philips · 5 年完整窗口 | **1** | **38** | 0 | 84 | 122 |
| Philips · 全时 | **8** | **161** | 0 | 729 | 994 |

- **首次进入只使用原始 PMA + Traditional 510(k)**：真实数据可判别示例——飞利浦呼吸赛道的首条审批是 **2003-07-15 的 Special 510(k) K030939**，而赛道 `first_approval` 正确显示 **2011-10-04 的 Traditional 510(k) K111378**（`first_any_approval=2003-07-15` 仅作背景展示）；里程碑措辞为“数据覆盖期内首次观察到原始批准”。
- **雷达 entrants**：3 家新进入的 `first_date` 与 SQL 的“首次原始批准”逐家一致；在本数据集中不存在“若把补充申请/Special 算入会改变 entrant 身份”的企业，因此该修复的判别证据来自合成 fixture（补充申请早于原始批准），而非真实数据。
- **合成 fixture 的 malformed/unknown 路径**：`tests/product_fixture.py` 写入 1 条 payload=`{not-json` 的 PMA，`build_fixture()` 期望 `classification_unknown=1`；`tests/test_product_statistics.py` 断言 `dataset.approval_classification.pma_unknown==1`、`pma_classification_available=false`，并在事件详情测试中断言出现 `pma_unknown` 且 list/detail 一致——`pytest tests/test_product_statistics.py` **21 passed** 证实该路径被覆盖。真实数据 0 条 unknown，故 unknown 分支只有合成证据。
- **`/api/evidence` 列表与 `/api/evidence/{id}` 分类一致**：抽样 40 条 PMA（`pma_original`/`pma_supplement`）+ 60 条 510(k)（`510k_traditional`/`510k_special`），`approval_type` 与 `is_first_entry_candidate` **100/100 一致**，无冲突。

### 4.4 监管路径结构（window vs all-time）

| 指标 | Medtronic（5 年完整窗口） | Philips（5 年完整窗口） |
| --- | --- | --- |
| 审批记录分母（510(k)+PMA） | **2,595** | **161** |
| PMA 合计（原始+补充+unknown） | 2,430 | 39 |
| PMA 占比 | **93.64%** | **24.22%** |
| 原始 PMA / 补充申请 | 7 / 2,423 | 1 / 38 |
| 原始 PMA 占 PMA | **0.29%** | **2.56%** |
| 510(k) 合计（Traditional/Special/Abbrev/其他） | 165（111/53/0/1） | 122（84/29/9/0） |
| 全时对照（all-time） | 86.73%（12,920 PMA / 1,976 510(k)） | 14.53%（169 / 994） |

- 比较页 `pathway` 的 `basis="complete_window_approvals_only"`、`window={2022-01-01, 2026-09-30}`，与总量使用**同一完整窗口**（不是全历史）。
- `pathway_all_time` 默认 **null**；`include_all_time=true` 在 store 层可计算，但 `/api/compare` 路由未透传该参数，故经 HTTP 始终为 null；比较页脚注明确写出这一点，未用全时结构代替窗口结构。
- 口径说明：路径结构分母为“窗口内全部 510(k)+PMA 记录”（含未映射赛道），而 headline“已映射赛道审批”为 2,396；两者差异 199 条 = 未映射记录，页面蓝色提示已披露 `2,396 + 199 = 2,595`。见 §7-D4（低严重度标注问题）。

### 4.5 重复 / 多计审计

| 检查项 | 结果 | 结论 |
| --- | --- | --- |
| events 总行数 vs 去重 event_id | 375,378 vs **375,378** | 无重复主键（且 event_id 为主键） |
| 重复 `payload + url` 组 | **0 组 / 0 条多余行** | 同一记录未被重复入库 |
| 重复 payload 组 | **0 组** | 无同 payload 多行 |
| 重复 url 组 | 8,512 组 | 正常：同一来源页（如召回详情页）服务多条不同产品记录 |
| 同 `source+kind+event_date+title` 组 | **1,501 组，覆盖 5,072 行** | 与 Lead 声称的 1,501 组一致 |
| 上述组内不同的 `(payload,url)` 对 | **5,072 个**（= 行数） | 每条 payload+url 都不同 |
| 组内存在重复 payload+url 的组数 | **0** | 不是重复记录 |
| 组内 kind 分布 | 召回 992、510(k) 188、药品批准 156、8-K 101、试验 64 | 多为“同一召回事件覆盖多个产品/型号”或同批次公告 |
| 示例 | 2024-08-28 Beaver Visitec 召回：159 行、159 个不同 payload、1 个 URL | 同一次召回下 159 个产品条目，属于不同记录而非重复 |
| 企业归属 | `company_key` 单值列；Dräger/Mindray 走精确别名且与主名册不相交（Mindray 244、Dräger 347，主名册键 0） | 未发现同一事件归属两家企业 |

### 4.6 研究助手数字复算

| 回答数字 | API/UI | 独立 SQL（别名精确匹配，不调用产品归属函数） | 一致 |
| --- | --- | --- | --- |
| 迈瑞超声近窗 / 前窗 | 24 / 32 | 24 / 32 | ✅ |
| 行业超声近窗 / 前窗 | 414 / 392 | 414 / 392（+5.6%，UI/答案取整 +6%） | ✅ |
| 迈瑞超声份额 近窗 / 前窗 | 70.6% / 69.6% | 0.7059 / 0.6957 | ✅ |
| 越界问题 | `out_of_scope`，0 证据 | —（无数据可答） | ✅ |

---

## 5. 测试可信度

### 5.1 实际执行（命令、结果、退出码、skipped）

| 层级 | 命令（工作目录 `D:\DEPPSKK\medradar`） | 实际结果 | skip | 退出码 |
| --- | --- | --- | --- | --- |
| Tier A/B（无真实 DB） | `python -m pytest tests/test_product_statistics.py` | **21 passed**（0.67s） | **0** | 0 |
| Tier C（真实 DB） | `python -m pytest tests/test_product_store.py tests/test_product_api.py tests/test_product_analyst.py` | **74 passed**（44.20s） | **0** | 0 |
| 全量 | `python -m pytest` | **1,169 passed + 224 subtests passed**（120.13s） | **0** | 0 |
| Tier D（浏览器 E2E） | `node scripts/product_e2e.cjs` | **6 passed, 0 failed**（18.3s；报告 `out/product_e2e/report.json`） | 0 | 0 |
| 旧 selftest | `python -m medradar selftest` | **Ran 1,074 tests — OK**（54.13s） | — | 0 |
| CI 分层 | `.github/workflows/ci.yml` `product-statistics` job | 已静态确认存在：Tier A/B 无数据仓库运行；Tier C 用 `-rs` 显式报告 skip | 未执行（见 §8） | — |

> 说明：仓库 `addopts="-q"`；若命令行再传 `-q` 会叠加为 `-qq` 并抑制总结行。本表使用**不额外传 `-q`** 的标准调用（由仓库配置提供单层 `-q`）以取得总结行；Tier C 与全量均确认 **0 skipped**。Tier A/B 使用 `tests/product_fixture.py` 生成的临时合成 SQLite（`use_database()` 指向 tmp），不读取 `data/medradar.sqlite`；本次真实数据存在，故 Tier C 无 skip。

### 5.2 旧缺陷若回归，现有测试会不会失败？

| 历史缺陷 | 会失败的测试（已逐行阅读） | 判定 |
| --- | --- | --- |
| **旧 LQ 分母**（企业用全部记录、行业用已映射） | Tier A `test_lq_uses_mapped_denominators_not_all_records`：手算 30/40 ÷ 50/120 = **1.8**，并显式断言 `value != old_wrong`（旧公式 1.44）；Tier B `test_fixture_compare_lq_uses_consistent_denominators`：fixture 中 30/40 ÷ 50/120 = 1.8，且 `!= old_wrong_lq`（1.44）；API `test_compare_lq_matches_its_own_disclosed_denominators`：用响应自带 `total_mapped` 与 `industry.mapped_records` 复算每个 ok 单元格 | **会失败**。若旧公式回归：Tier A 得 1.44≠1.8；Tier B 得 1.44；API 真实数据美敦力心脏节律会得 3.417 vs 复算 3.721，超出 `abs=1e-3`。纯函数 Tier A 保证不依赖“披露字段也被一起改错” |
| **起始不完整季度未被识别**（旧 `is_period_partial(period, edge)` 只看终点） | Tier A `test_partial_period_at_both_window_edges`（2021-Q4 起端被裁剪必须 `partial=True`）、`test_complete_window_quarter_year_month`、`test_comparison_windows_are_contiguous_and_equal_length`；Tier B `test_fixture_complete_period_totals_exclude_partial_edges`（`2021-Q4.partial=True`、`recent=30` vs `recent_all=32`、`partial_periods=2`、`2026-Q3.source_lag_risk=True`） | **会失败**。旧实现会把 2021-Q4 标为完整 → fixture `recent` 变 32、`partial_periods` 变 1、`2021-Q4.partial=False`，三处断言同时失败 |
| **PMA 补充申请被当作首次进入** | Tier B `test_fixture_pma_first_entry_ignores_supplements_and_special_510k`：fixture 中呼吸赛道补充申请 2015-05-01 早于原始批准 2016-09-01，断言 `first_approval=2016-09-01` 且 `first_any_approval=2015-05-01`，并断言里程碑标签含“首次观察到原始批准”；`test_fixture_event_detail_exposes_approval_type` 断言 list/detail 分类一致 | **会失败**。旧实现 `_company_track_firsts` 用 `MIN(event_date)` 取任意 510(k)/PMA → fixture 呼吸 `first_approval` 会变成 2015-05-01，直接违反断言。（`test_fixture_radar_uses_complete_windows_and_discloses_attribution` 的 `entrants first_date >= analysis_start` 是补充一致性检查；该 fixture 情境下旧实现更可能表现为“漏报 entrant”而非“误报”，故不等于主要判别依据。） |

补充核验：旧恒真断言 `assert all(... or True ...)` 存在于 `f3ea1e4:tests/test_product_store.py`，当前版本已替换为“API 返回总数 == 独立 `SQL LIKE` 计数”且逐条详情复核（`test_evidence_search_filters_are_exact`），`grep -R "or True" tests scripts` 无残留。Tier B fixture 的期望值由手算常量与显式事件计数构造，不通过“调用被测函数再与自身比较”生成。

### 5.3 测试剩余盲区（供 Lead 决策，非阻断）

1. **D2 的形态无测试**：没有测试覆盖“合法 JSON PMA、但缺少 `supplement_number` 字段”——fixture 只覆盖 malformed JSON；该形态下 SQL 分类（原始）与 Python/数据集审计（unknown）不一致（见 §7-D2）。
2. API LQ 测试从响应自身字段复算，若“计算与披露字段被同一回归一起改错”则可能漏检；目前由 Tier A 纯函数测试兜底。
3. 真实数据中不存在“补充申请早于原始批准”的呼吸赛道企业，因此 supplement-as-first-entry 的判别只有合成 fixture 证据；建议保留并在文档中如此说明（本报告已说明）。
4. 无 HTTP 外链可达性测试（只验证 URL 非空与字段一致）。

---

## 6. 诚实性与边界核验

| 检查项 | 实测结果 | 判定 |
| --- | --- | --- |
| Dräger / Mindray 归属状态 | API `entity_review` 与两个企业页均显示 `PENDING_HUMAN_REVIEW`（“实体归属待人工复核”）；Mindray 244 事件 / 10 条精确别名，Dräger 347 事件 / 22 条精确别名；主名册键均为 0 | 属实 |
| 研究人工标签 | `/api/lab` artifact：`packets=69`、`human_labels_recorded=0`；CSV 69 数据行，`human_label`/`human_reason`/`independent_confirmation`/`reviewer`/`reviewed_at` 非空数均为 **0**；页面显示“受限于人工复核：AI 初审完成，人工真值未完成” | 属实 |
| hist_v1 未合并 | `research/full-history-v1` 不是 `main` 祖先（`merge-base --is-ancestor` exit 1）；lab provenance `merged=false`、只读引用 commit `969fd0c`（对象存在）；页面显示“未合入 main…（commit 969fd0c）” | 属实 |
| 无经验证预测 | lab `R-forecast-registry` 状态“**无已验证的前瞻校准**”；meta 限制 `not_prediction`；雷达/助手均声明“不是预测” | 属实 |
| 限制可见 | 总览限制横幅、企业页“该视图的限制”（8 条）、雷达方法说明、研究助手 limitations、实验室 limits 均实测可见 | 属实 |
| main 未被改动 | `main=origin/main=b2a14c0`；`5a349f4` 不是 main 祖先；当前分支为 `feat/medradar-2.0-mvp` | 属实 |
| PR #12 | OPEN、**Draft**、head `5a349f4e230cbba911d5c623ae83bb173b601c77`、base main | 属实 |
| 用户 CSV | `git status` 为 `M`；`git diff --cached` 为空（未暂存）；HEAD 中 blob 未变（未提交）；本地 diff 只改 `evidence_summary` 字段（`gap-days=…` → 描述性文字），`human_label` 仍全空 | 仅本地修改，属实 |
| 只读数据 | 全程 `mode=ro`；`medradar.sqlite` mtime 未变；未执行写库操作 | 属实 |
| point-in-time | `first_seen_at` 仅 2 个值（2026-10-30/31，即抓取日），`available_at` 为 `event_date + 00:00:00` | **不可用作真正的“当时可知”回放**，如实标注 |

---

## 7. 我在本轮审计中发现的缺陷

| ID | 严重度 | 位置 | 现象与证据 | 影响 | 建议 |
| --- | --- | --- | --- | --- | --- |
| **D1** | **Major（文档）** | `docs/PRODUCT_STATISTICAL_AUDIT.md` §2.4 表格 | “企业结论数字变化（Medtronic 心脏节律）”中，**本期“请求窗口”写了 1,552，上期写了 1,111**；独立 SQL 实测：本期请求窗口（2021-10-31–2026-10-30）= **1,111**，上期请求窗口（2016-11-01–2021-10-30）= **1,552**。两行数字互换。产品本身 `claim.metrics` 与页面为正确的 **1,051 / 1,480**（完整季度），PMA 2 / 1,048 亦正确 | 审计报告可信度受损；若被引用会把“近期 1,552”误当事实。**不影响产品计算** | 修正 §2.4 两行：本期请求窗口 1,111、上期请求窗口 1,552（或删去“请求窗口”列，只保留完整季度 1,051/1,480 并注明来源） |
| **D2** | **Medium（潜在产品缺陷）** | `medradar/product/store.py` `_pma_original_sql()` / `_pma_supplement_sql()` vs `approval_classification()` / `classification_audit()` | 对 payload=`{"pma_number":"P900001"}`（**合法 JSON、无 `supplement_number` 字段**）的 PMA：`_pma_original_sql()` 因 `coalesce(json_extract(...),'')=''` 计为**原始批准**；`classification_audit()` 用 `json_type(...,'$.supplement_number') IS NULL` 计为 **unknown**；Python `approval_classification()` 返回 **pma_unknown**。用内存 SQLite 独立复现：original=1、audit unknown=1、python=pma_unknown。真实数据该形态 **0 条**（`pma_missing_supplement_number=0`、`valid_non_object=0`），故当前所有已观测数字不受影响 | 若未来 payload 模式变化/缺字段，unknown 会被静默计为原始批准，污染“首次进入候选”与路径结构；三处口径不一致本身也是维护风险 | 统一为“字段必须存在且为字符串”的谓词（如 `json_type(...,'$.supplement_number') IS NOT NULL AND coalesce(...)=''`），并加 Tier A 测试“合法 JSON 缺字段 → unknown”；当前数据下可安全重跑 |
| **D3** | **Low（API/文档缺口）** | `medradar/web/app.py` `/api/compare` | 路由签名无 `include_all_time`，调用 `/api/compare?...&include_all_time=true` 返回与默认完全相同（`pathway_all_time=null`）；store `company_compare(..., include_all_time=True)` 与 fixture 测试支持该能力。审计称“需 `include_all_time=true`”，但该参数经 HTTP 无法触发 | 无用户可见数值错误（UI 明确写“未返回，默认不请求”，未以全时冒充窗口）；但“全历史结构单独展示”在 API 层不可达，文档表述不准确 | 在路由透传可选 `include_all_time: bool = False`，或在审计/契约中明确“比较 API 不提供全时结构，仅企业页有 `pathway_mix_all_time`” |
| **D4** | **Low（标注清晰度）** | `#/companies/{key}` KPI + 路径面板 | PMA 原始/补充 KPI = 7 / 2,423（合计 2,430）、路径分母 = 2,595，包含 134 条未映射 PMA 与 65 条未映射 510(k)；headline“已映射赛道审批”= 2,396。旁侧蓝色提示写有 `2,396 + 199 = 2,595`，但 PMA KPI 与路径子标题只写“完整季度 / 分母为 510(k)+PMA 记录”，未显式说“含未映射” | 用户需跨面板心算才能解释 7+2,423=2,430 ≠ 2,396；属可避免的困惑，不构成错误数字 | KPI 标签加“全部记录（含未映射）”或同时给出已映射口径；路径子标题注明“含未映射 / 已映射 2,396” |
| **D5** | **Info（发布状态）** | 工作区 | 审计期间出现未提交的 `README.md`、`docs/PRODUCT_ROADMAP.md` 修改（非本审计员写入，未包含在 `5a349f4`）；用户 CSV 仍为本地修改。产品代码/测试/前端无未提交修改 | 若直接交付，PR head `5a349f4` 与工作区内容不完全一致；不影响 HEAD 产物与本次验收 | Lead 决定是否把文档修改纳入新提交；交付前保持 `git status` 透明并说明 CSV 为用户本地修改 |

> 另：Lead 审计 §2.1/§2.2/§2.3/§2.5 的数字经独立复算**全部吻合**（旧 LQ、完整 vs 请求窗口、PMA 拆分、雷达 560/740/570/10 等）；§3 测试计数吻合；§5 的重复计数结论吻合。以上 D1 是 §2.4 的局部转录错误。

---

## 8. 明确“未验证 / 不可用”

**未验证（本轮无权限/无网络/超出范围，不能宣称通过）**

1. **外部来源链接的 HTTP 可达性**：仅验证了 375,378/375,378 条记录 URL 非空且为 `http(s)`，并抽查事件详情链接与 API 一致；未逐条请求，也未验证失效/重定向/付费墙。
2. **CI 实际运行**：只静态确认 `.github/workflows/ci.yml` 存在 `product-statistics` job（Tier A/B + Tier C `-rs`）；未触发 GitHub Actions，未验证远端绿/红。
3. **运行进程的 commit 字节级指纹**：服务只报 `product=2.0.0-mvp`；依据 cwd、产品代码相对 HEAD 干净、行为与 HEAD 测试一致推断其为 `5a349f4`，未做二进制/内存校验。
4. **浏览器覆盖面**：仅 Chrome（Playwright headless）；未测 Firefox/Safari/Edge、真实移动设备、触屏手势、键盘导航与完整无障碍（a11y）审计。
5. **其他路由/指标/赛道**：只验收了任务指定的五场景；未穷举 8 条路由、6 个指标、雷达其余 17 个重点赛道（全库共 60 个赛道）、5+ 企业比较、证据分页/搜索完整交互、`recalls`/`trials`/`corporate` 指标、导出/打印等。
6. **性能**：未做基准测试（不在本轮统计验收范围）。
7. **API 非 `approvals` 指标下的 LQ/窗口一致性**：逻辑共用，但未逐指标复算。

**不可用（产品如实声明或数据本身不具备）**

1. **真正的 point-in-time 回放**：`first_seen_at` 仅 2026-10-30/31 抓取日，`available_at` 等于事件日，无法还原“当时可知”的信息集；产品按事件日期回看。
2. **经验证预测**：不存在（lab 明确“无已验证的前瞻校准”），产品不提供预测/因果结论。
3. **人工真值标签**：69 份证据包 **0 条人工标签**，AI 预标注不可当人工真值；研究结论仍待人工复核。
4. **人工复核后的企业归属**：Dräger/Mindray 为 `PENDING_HUMAN_REVIEW`，计数可能随复核变化。
5. **全球/非美国数据**：仅美国 FDA 等公开记录，不代表企业全球活动（尤其迈瑞、德尔格）。
6. **产品级计数**：记录 ≠ 产品，一次申请可拆多行；产品已在 UI/文档声明。
7. **未映射赛道的行业份额**：完整窗口审批记录中约 31.3% 未映射赛道（行业映射率 68.7%），LQ/份额只在已映射口径内成立。
8. **`pathway_all_time`（比较 API）**：默认 null 且 API 无参数可请求（D3），故“全时结构”只能视为不可用/未验证。

---

## 9. 最终判定与剩余阻断项

**最终判定（基于 `5a349f4`、真实数据、独立复算）**

- 五个必需场景：**PASS（1440×900 与 390×844 共 10/10）**。
- 统计修复核心主张（一致 LQ 分母、完整季度窗口、PMA 原始/补充分类、window-based 路径结构、无重复计数）：**经验证成立**；旧值与新值差异可精确复现，API/UI 与独立 SQL 一致。
- 测试可信度：**通过**（21 + 74 + 1,169+224 + 6 + 1,074，0 skipped，exit 0）；三类历史缺陷均有会在回归时失败的测试。
- 未发现**阻断性产品缺陷**；发现 **D1（Major，报告数字写反）**、**D2（Medium，潜在分类不一致，当前 0 例）**、D3/D4（Low，API/标注）、D5（Info，工作区）。
- 建议：**修复 D1 后可进入最终人工验收**；D2 建议作为下一提交的防守性修复（当前数据可安全重跑）；D3/D4 可作为文档/标签优化。**不应**把本产品描述为预测、因果或企业创新能力排名工具。

**剩余阻断项（应带到下一阶段/人工验收）**

1. 赛道映射覆盖：全库 52.36%；完整窗口审批映射率 68.7%（行业）/ 92.33%（美敦力）/ 88.82%（飞利浦）——未映射记录不能进入赛道份额/LQ，产品已披露，但仍是解释力上限。
2. Dräger/Mindray 企业归属 `PENDING_HUMAN_REVIEW`（244 / 347 事件），需人工复核后才可作为定论。
3. 69 份证据包 0 条人工标签：任何研究结论（H1–H4、Target B）仍不可用。
4. 无真正 point-in-time；当前视图是“按事件日期回看”，不是当时决策视角。
5. 无经验证预测/因果模型；研究实验室只展示不确定与负面状态。
6. 外部 URL 可达性未验证；若对外发布需一次外链健康检查。
7. 交付前处理 D1（审计文档）与 D5（README/PRODUCT_ROADMAP 未提交修改、用户 CSV 的归属说明）。

---

## 10. 复现命令与证据文件索引

```bash
# 锚点与仓库事实
git rev-parse HEAD                      # 5a349f4e230cbba911d5c623ae83bb173b601c77
git rev-parse main origin/main          # b2a14c0a92332c004445de686daee97754cf94cb
git merge-base --is-ancestor 5a349f4 main; echo $?   # 1 → main 未包含 5a349f4
git merge-base --is-ancestor research/full-history-v1 main; echo $?  # 1 → hist_v1 未合并
gh pr view 12 --json number,state,isDraft,headRefOid # OPEN / true / 5a349f4…
git status --short                      # 审计结束时：README.md、docs/PRODUCT_ROADMAP.md、用户 CSV、本报告（docs/PRODUCT_ACCEPTANCE.md）为 M；产品代码/测试/前端干净

# 服务 / 数据
curl -s http://127.0.0.1:8787/api/health

# 测试（本报告 §5.1 的实际命令）
python -m pytest tests/test_product_statistics.py
python -m pytest tests/test_product_store.py tests/test_product_api.py tests/test_product_analyst.py
python -m pytest
node scripts/product_e2e.cjs
python -m medradar selftest

# 独立复算与浏览器（本审计员自写，均在 out/acceptance2/）
python out/acceptance2/recompute.py          # 只读 SQL 复算，输出 recompute_result.json
python out/acceptance2/final_facts.py        # API/SQL 事实汇总，输出 final_facts.json
node out/acceptance2/browser_scenarios.cjs   # 10 次场景运行 + 截图 + browser_report.json
node out/acceptance2/extra_checks.cjs        # DOM 细节（不适用单元格、PENDING、移动端溢出）
node out/acceptance2/claim_panel_check.cjs   # 结论→证据面板复算文本、pathway_all_time=null 提示
```

**证据文件（`out/acceptance2/`，gitignored）**

- 报告 JSON：`browser_report.json`（10 项、console errors=0）、`extra_report.json`、`recompute_result.json`、`final_facts.json`、`browser_scenarios.log`、`extra_checks.log`。
- 测试日志：`pytest_statistics2.log`、`pytest_tierC2.log`、`pytest_full.log`、`product_e2e.log`、`selftest.log`。
- 截图：`s1-company-mindray-{desktop,mobile}.png`、`s2-compare-{desktop,mobile}.png`、`s3-radar-respiratory-{desktop,mobile}.png`、`s4-evidence-trace-{desktop,mobile}.png`、`s4a-claim-evidence-panel.png`、`s5a-analyst-answered-{desktop,mobile}.png`、`s5b-analyst-outofscope-{desktop,mobile}.png`、`s6-draeger-pending-desktop.png`、`s7-lab-desktop.png`、`s8-overview-desktop.png`、`s9-mobile-claim-evidence.png`、`s10-mobile-analyst.png`、`s11-lab-s027-detail.png`。
- 仓库可提交等价截图：`docs/product/company-mindray.png`、`compare.png`、`radar-respiratory.png`、`evidence-trace.png`、`analyst.png`、`mobile-company.png`、`overview.png`（其中 6 张与本次运行 SHA256 相同）。

---

*本报告只基于 `5a349f4` 与 2026-10-30 数据截止的真实观测；未观测到的不标记为 PASS。审计期间未修改产品代码、测试、数据或服务。*
