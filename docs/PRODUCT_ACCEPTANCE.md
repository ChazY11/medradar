# MedRadar 2.0 — 统计修复后独立验收报告（commit `9237c1d`）

> **验收对象**：`D:\DEPPSKK\medradar` · 分支 `feat/medradar-2.0-mvp` · 独立审计锚点 **`9237c1d`**；R1 修复 **`01ba4aa`**（`fix(product): close statistical audit findings D1-D4 and add independent acceptance`，父提交 `5a349f4`）
> **数据**：`data/medradar.sqlite`（1,368,469,504 bytes，mtime `2026-10-31T05:28:25Z`），data edge **2026-10-30**，events **375,378**
> **产品**：`2.0.0-mvp`，服务 `http://127.0.0.1:8787`（2026-11-03 21:40:57 +0800 重启；`include_all_time` 行为证明运行新代码）
> **验收人**：独立验收员 `verifier2`（与实现者、Lead 相互独立）
> **审计时间**：首轮 2026-11-03 21:19–21:38 针对 `5a349f4`；本轮 21:46–21:54 针对 `9237c1d` 复验（Asia/Shanghai）
> **结论**：**D1–D4 已全部修复并经独立复验；残余 R1（全历史 basis 标签）已由 Lead 在 `01ba4aa` 修复并重新验证；五个必需场景在 1440×900 与 390×844 下仍全部 PASS 且测量值不变；测试 21 + 75 + 1,170+224 + 6/6 + 1,074 全过、0 skipped。未发现阻断性缺陷。建议进入最终人工验收。** 产品仍是“证据型研究终端”，不是预测产品。

---

## 0. 结论摘要（针对 `9237c1d`）

1. **五场景全 PASS**：迈瑞企业画像、美敦力 vs 飞利浦比较、呼吸与麻醉雷达、结论→证据→事件→来源链路、研究助手（含 out_of_scope），在 1440×900 与 390×844 各自独立复跑，共 **10/10 PASS**，**0 个控制台错误、0 个横向溢出**；`9237c1d` 不改变任何测量值（与 `5a349f4` 首轮审计的数字逐项一致）。
2. **D1 已修复**：`docs/PRODUCT_STATISTICAL_AUDIT.md` §2.4 现为“本期请求窗口 **1,111**、上期请求窗口 **1,552**”（完整季度 1,051 / 1,480 不变），与独立 SQL 一致。
3. **D2 已修复**：`_pma_original_sql()` 增加 `json_type(payload,'$.supplement_number') IS NOT NULL`；合成 fixture 新增“合法 JSON 缺 `supplement_number`”记录，Tier B 断言 SQL / `/api/evidence` 列表 / `/api/evidence/{id}` 三处均为 `pma_unknown`。我的独立复现：新 SQL original=7、旧 SQL 会得 8（差 1 条缺键记录）、unknown=2、Python=`pma_unknown` 且非首次进入；真实数据仍 0 unknown、Medtronic 7/2,423 不变。
4. **D3 已修复**：`/api/compare` 新增 `include_all_time` 参数并透传。HTTP 实测：默认与 `include_all_time=false` → `pathway_all_time=null`；`include_all_time=true` → 美敦力 12,920 PMA（100 原始 / 12,820 补充）/ 14,896 审批，飞利浦 169 / 1,163，窗口 `1900-01-01..2026-10-30`，与独立 SQL 完全一致；默认路径结构窗口不变。新增 API 测试通过。
5. **D4 已修复**：企业页 PMA 拆分说明现在明确“PMA 拆分与路径结构使用该企业完整窗口内全部审批记录（含未映射赛道记录）；上方‘已映射赛道审批’KPI 仅统计已映射记录。”浏览器实测文本存在，数字可对账：2,396（已映射）+ 199（未映射）= 2,595。
6. **测试（`9237c1d` 实测）**：Tier A/B **21 passed**、Tier C **75 passed**、全量 **1,170 passed + 224 subtests**、仓库 E2E **6/6**、selftest **1,074 OK**，全部 exit 0、**0 skipped**。旧 `... or True` 已删除；LQ 分母、起始不完整季度、补充申请误作首次进入、缺键 PMA 四类历史缺陷均有会在回归时失败的测试。
7. **诚实性边界不变**：迈瑞/德尔格 `PENDING_HUMAN_REVIEW`；69 份证据包 0 条人工标签；`research/full-history-v1` 未合入 main；无经验证预测；限制可见；`main` 未被改动（`b2a14c0`）；PR #12 **Draft / OPEN**，产品代码 head 为 `01ba4aa`（R1 修复），报告提交见 PR head。
8. **残余观察均已关闭**：R1 —— `pathway_all_time.basis` 已由 Lead 在 `01ba4aa` 改为 `all_time_approvals_only` 并新增 API 断言，HTTP 复验通过（数值不变）。R2 —— 两份文档已随 `9237c1d`/`01ba4aa` 提交，交付时工作区仅剩用户本地 CSV。

---

## 1. 审计锚点与环境（`9237c1d` 可复现事实）

| 项目 | 实测值 | 来源 |
| --- | --- | --- |
| 仓库 / 分支 | `D:\DEPPSKK\medradar` / `feat/medradar-2.0-mvp` | `git status` / `git branch --show-current` |
| HEAD（产品代码） | **`01ba4aa`**（R1 修复；独立审计锚点 `9237c1d`，父提交 `5a349f4`） | `git log -1` / `git rev-parse HEAD^` |
| 首轮审计锚点 | `5a349f4e230cbba911d5c623ae83bb173b601c77`（本轮所有 D1–D4 修复在此基础上） | `git log` |
| `main` / `origin/main` | 均为 `b2a14c0a92332c004445de686daee97754cf94cb`；`9237c1d` **不是** main 祖先（`merge-base --is-ancestor` exit 1） | `git rev-parse` / `git merge-base` |
| PR | #12，**OPEN / Draft**，`headRefName=feat/medradar-2.0-mvp`，base=main；产品代码 head=`01ba4aa`，报告提交后 head 为文档提交 | `gh pr view 12` |
| 服务 | `http://127.0.0.1:8787`，`/api/health` → `status=ok`、`product=2.0.0-mvp`；进程 `python -m medradar web --port 8787`，2026-11-03 **21:40:57** 启动；`include_all_time` 新行为证明运行 `9237c1d` 代码 | Invoke-RestMethod / `Get-CimInstance Win32_Process` |
| 数据文件 | `data/medradar.sqlite`，1,368,469,504 bytes，mtime `2026-10-31T05:28:25Z`；只读 `mode=ro` 打开，审计期间未修改 | 文件系统 / `/api/health` |
| 数据范围 | `1966-12-14` → **`2026-10-30`** | `SELECT MIN/MAX(event_date)` |
| 事件规模 | **375,378**（event_id 去重后同为 375,378） | 只读 SQL |
| 来源构成 | 510(k) 176,466 · PMA 57,372 · 器械召回 59,646 · 临床试验 55,592 · 8-K 20,976 · 药品批准 5,326 | 只读 SQL |
| 分类维度 | 赛道已映射 196,542 / 未映射 178,836（覆盖率 **52.36%**）；企业已归属 132,293 / 未归属 243,085；companies 表 89 家、tracks 60、product_codes 7,097 | `/api/meta` + SQL |
| 复验开始时工作区 | 仅 `M research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv`（用户本地修改）；产品代码/测试/前端/文档干净 | 复验首条 `git status --short` |
| 复验/交付工作区 | R1/R2 修复与文档已提交；交付时仅 `research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv` 为用户本地修改，未提交 | `git status --short` |

> 说明：服务只暴露产品版本号；本轮通过新参数 `include_all_time` 的 HTTP 行为（`5a349f4` 不支持）确认服务运行的是 `9237c1d` 代码，而非仅凭版本字串。

---

## 2. 方法与独立性声明

1. **不信任 Lead 审计/测试**：`docs/PRODUCT_STATISTICAL_AUDIT.md` 只作为“待验证的主张清单”；核心数字用**自写只读 SQL**（`sqlite3` `mode=ro`，不调用 `medradar.product.store` 聚合函数）重算，再与 API/UI 对照。
2. **只读数据**：`data/medradar.sqlite` 以 `file:...?mode=ro` 打开；未写入、未迁移、未重启服务、未修改任何产品代码或测试；唯一写入范围是 `docs/PRODUCT_ACCEPTANCE.md`（本文件），截图/脚本在 `out/acceptance2/`（已 gitignore）。
3. **浏览器独立复跑**：自写 Playwright 脚本 `out/acceptance2/browser_scenarios.cjs`，不复用仓库 E2E 判定；1440×900 与 390×844 两个隔离 context，记录 DOM 文本 + 自取 API + 截图，并收集 console error/pageerror。
4. **API 自身字段复算**：LQ 用 `/api/compare` 响应中的 `n / total_mapped / industry_total / industry_records.mapped_records` 重算；D3 用独立 SQL 重算全历史路径结构。
5. **修复点专项复验**：D1 读文档 + SQL 对照；D2 在临时目录用 `tests/product_fixture.py` 重建合成库，再分别用**自写 SQL / Python 纯函数 / 产品读路径（evidence_search + event_detail）**验证；D3 直接 HTTP + SQL；D4 浏览器 DOM 文本 + 数字对账。
6. **测试执行**：按 Tier A/B、Tier C、全量、E2E、selftest 分层执行并记录命令、计数、退出码、skip；逐条阅读测试代码，回答“旧缺陷若回归是否会被抓住”。
7. **Git/产物核验**：`git rev-parse/log/status/diff --cached/merge-base`、`gh pr view`、`git cat-file`；CSV 仅读取与 diff 检查，未 touch/暂存/提交。
8. **时间边界**：首轮审计 `5a349f4`（21:19–21:38）；本轮 `9237c1d`（21:46 起）。并行文档编辑已记录，不影响 `9237c1d` 产物与五场景判定。

---

## 3. 五个必需场景验收（`9237c1d`，1440×900 + 390×844）

### 3.0 场景总表

| # | 场景 | 1440×900 | 390×844 | 关键实测数字（与 `5a349f4` 一致） | 截图（`out/acceptance2/`） |
| --- | --- | --- | --- | --- | --- |
| 1 | 研究一家公司（迈瑞医疗 `#/companies/mindray`） | **PASS** | **PASS** | 全时事件 244；已映射赛道审批（5 年完整季度）**34**；窗口全部 40；完整窗口全部（已映射+未映射）36；结论 3 条；8 条限制；`PENDING_HUMAN_REVIEW` 可见；横向溢出 0 | `s1-company-mindray-desktop.png` / `s1-company-mindray-mobile.png` |
| 2 | 比较竞争对手（Medtronic vs Philips `#/compare`） | **PASS** | **PASS** | 分析窗口 2022-01-01→2026-09-30（19 季度），对照 2017-04-01→2021-12-31；28 条赛道矩阵 / 56 个 LQ 单元格（34 ok + 22「不适用」）；3 条警告；LQ 3.72 / 9.32 / 4.04 / 不适用 | `s2-compare-desktop.png` / `s2-compare-mobile.png` |
| 3 | 分析技术趋势（呼吸与麻醉 `#/radar/respiratory`） | **PASS** | **PASS** | 完整周期 560 vs 740（-24.3%）；窗口全部 570；partial 10；全时 4,091；39+2 个季度；3 家新进入；14 家企业；未归属 435/560（77.7%）；无统计探测信号 | `s3-radar-respiratory-desktop.png` / `s3-radar-respiratory-mobile.png` |
| 4 | 追溯结论到原始证据（结论→查看证据→事件→详情→来源） | **PASS** | **PASS** | 结论复算显示“近窗 **1,051** / 对照窗 **1,480**”；事件 `fdfacf2f…`；`approval_type=pma_supplement`；来源链接与 API 一致（`pma.cfm?id=P980016`） | `s4-evidence-trace-desktop.png` / `s4-evidence-trace-mobile.png`；`s4a-claim-evidence-panel.png` |
| 5 | 使用研究助手（`#/analyst`，含 out_of_scope） | **PASS** | **PASS** | 迈瑞超声 **24 vs 32（-25%）**、行业 **+6%**、份额 **69.6%→70.6%**；证据 3 条；越界问题返回“超出范围”，无编造数字 | `s5a-analyst-answered-desktop.png` / `...-mobile.png`；`s5b-analyst-outofscope-desktop.png` / `...-mobile.png` |

补充证据：`s6-draeger-pending-desktop.png`（德尔格 PENDING）、`s7-lab-desktop.png`（研究实验室）、`s8-overview-desktop.png`（总览限制）、`s9-mobile-claim-evidence.png`、`s10-mobile-analyst.png`、`s11-lab-s027-detail.png`、`s12b-company-pma-split-visible.png`（D4 说明可见）。

> **仓库截图等价物说明**：`docs/product/` 已在 `01ba4aa` 重新生成（企业页含 D4 说明、其余页面同 HEAD）；本次独立运行截图见 `out/acceptance2/`（gitignored 构建产物，不入库）。

### 3.1–3.5 场景细节

- **S1 迈瑞**：DOM 显示“迈瑞医疗 / Mindray / 300760 / SZSE”、`PENDING_HUMAN_REVIEW`“实体归属待人工复核”（10 条接受匹配字符串）、8 条“该视图的限制”；KPI 34 / 40 / 36；结论 3 条（超声 24/32、监护 5/11、呼吸 5/3）。
- **S2 比较**：页面展示“分析窗口 2022-01-01 → 2026-09-30”“对照窗口 2017-04-01 → 2021-12-31 · 完整周期 19 个”；美敦力 2,595（已映射 2,396 / 未映射 199，92.3%；前窗 3,354；Δ -759 / -22.6%）；飞利浦 161（143 / 18，88.8%；前窗 171；Δ -10 / -5.8%）；22 个非 ok 单元格全部 `zero_company_track` 且渲染“不适用”+原因；3 条警告：`complete_quarter_basis`、`pathway_mix`、`pma_supplement_share`。
- **S3 雷达**：完整窗口 560 / 前窗 740 / 窗口全部 570 / partial 10；attributed 125 / unattributed 435（77.7%）；新进入 3 家（强生 2019-04-19、费森尤斯 2020-02-21、麦朗 2023-06-23）；无信号。
- **S4 证据链**：结论卡“查看证据”→ 面板“复算结果：近窗 1,051 条 / 对照窗 1,480 条” → 事件行 → 事件详情（`pma_supplement`，含 `approval_type`/`is_first_entry_candidate=否`/`supplement_type`/`source_fields`）→ 原始来源链接与 API 一致。
- **S5 研究助手**：`answered`（迈瑞超声 24 vs 32，-25%、行业 +6%、份额 69.6%→70.6%，3 条证据）；`帮我预测明年迈瑞的营收` → `out_of_scope`（“超出范围”，0 证据）。

---

## 4. 独立复算（`9237c1d` 重跑，数值与 `5a349f4` 完全一致）

### 4.1 Location Quotient：旧公式 vs 一致分母 vs 完整窗口

公式（新口径，企业与行业都用完整窗口内**已映射赛道记录**作分母）：

```
LQ = (企业该赛道已映射记录 / 企业已映射记录)
   / (全行业该赛道已映射记录 / 全行业已映射记录)
```

旧实现（`f3ea1e4`）：企业侧 `share = n / company["total"]`（请求窗口内**全部**审批记录，含未映射），行业侧只含已映射。

| 企业 · 赛道 | 请求窗口企业赛道 / 企业全部 / 行业赛道 / 行业已映射 | 旧 LQ（旧分母 + 请求窗口） | 仅统一分母（请求窗口） | 完整窗口企业赛道 / 企业已映射 / 行业赛道 / 行业已映射 | 新 LQ（完整窗口） | API / UI |
| --- | --- | --- | --- | --- | --- | --- |
| Medtronic · 心脏节律 | 1,111 / 2,734 / 2,217 / 18,640 | **3.417** | 3.698 | 1,051 / 2,396 / 2,099 / 17,804 | **3.721** | 3.721 / UI 3.72 |
| Philips · 超声 | 31 / 166 / 429 / 18,640 | **8.114** | 9.101 | 31 / 143 / 414 / 17,804 | **9.323** | 9.323 / UI 9.32 |
| Philips · 患者监护 | 10 / 166 / 319 / 18,640 | **3.520** | 3.948 | 10 / 143 / 308 / 17,804 | **4.042** | 4.042 / UI 4.04 |
| Philips · 心脏节律 | 18 / 166 / 2,217 / 18,640 | **0.912** | 1.023 | 18 / 143 / 2,099 / 17,804 | **1.068** | 1.068 / UI 1.07 |
| Medtronic · 患者监护 | 1 / 2,734 / 319 / 18,640 | **0.021** | 0.023 | **0** / 2,396 / 308 / 17,804 | **null（`zero_company_track`）** | null / UI“不适用”+原因 |

- **API 披露字段复算**：56 个单元格用响应自身 `cell.n / company.total_mapped / (row.industry_total / industry_records.mapped_records)` 重算，**56/56 一致**（34 个 ok 误差 < 0.0015；22 个非 ok 全部 `location_quotient=null`）。
- **不适用渲染核验**：22 个非 ok 单元格 UI 全部显示“不适用”，`data-lq-status=zero_company_track`，tooltip 给出原因；无一处以 0/空值伪装有效 LQ。
- 口径提示：LQ 只描述记录分布，UI/API 均声明“不是创新能力、技术实力或市场份额”。

### 4.2 完整季度窗口 vs 请求窗口

| 检查项 | 请求窗口 | 完整窗口 / 结果 |
| --- | --- | --- |
| 时间范围 | 2021-10-31 → 2026-10-30（1,825 天） | **2022-01-01 → 2026-09-30（19 个自然季度）** |
| 对照窗口 | 2016-11-01 → 2021-10-30 | **2017-04-01 → 2021-12-31（19 个季度；与本期紧邻，间隔 0 天）** |
| Medtronic 审批（全部 / 已映射） | 2,734 / 2,526 | **2,595 / 2,396**（映射率 92.33%） |
| Medtronic 前窗（全部 / 已映射） | 3,548 / 3,224 | **3,354 / 3,050** |
| Philips 审批（全部 / 已映射） | 166 / 148 | **161 / 143**（88.82%） |
| 行业已映射审批（LQ 分母） | 18,640 | **17,804**（同窗口行业全部 25,912，映射率 68.7%） |
| 被排除的不完整周期 | 2021-Q4（2021-11-01..12-31）**118** + 2026-Q4（2026-10-01..10-30）**21** = **139** | 2,734 − 139 = **2,595**（吻合） |
| 心脏节律赛道的不完整期记录 | 1,111 | 排除 60 条（1,111 − 60 = 1,051） |
| `partial` 与 `source_lag_risk` | — | 2021-Q4、2026-Q4 标 `partial`；**2026-Q3 日历完整但距 edge 30 天 → 仅 `source_lag_risk=true`**（两者分离） |
| 雷达（10 年） | 2016-11-01 → 2026-10-30 | 完整 **2017-01-01 → 2026-09-30（39 季度）**；对照 2007-04-01 → 2016-12-31（39 季度）；partial 2016-Q4=8 + 2026-Q4=2 = **10**；recent 560 / recent_all 570 / prior 740 / prior_all 763 |
| claims 依据 | — | 8 条美敦力结论的 `recent/prior` 逐条与“完整窗口、已映射赛道”SQL 重算一致（如心脏节律 1,051/1,480）；`claim_evidence` 返回 `recomputed` 同值 |

SQL 侧核对：分析窗口与对照窗口各出现 19 个自然季度，`prior_end` 与 `analysis_start` 相隔 0 天，无重叠、无缝隙；窗口边界闭区间（`>= start AND <= end`）。D1 相关：本期请求窗口 = 1,111、上期请求窗口 = 1,552（与修正后的审计 §2.4 一致）。

### 4.3 PMA 原始批准 vs 补充申请（含 D2 缺键路径）

**数据集分类可用性（真实数据，`9237c1d` 重跑）**

| 检查项 | 结果 |
| --- | --- |
| PMA 总数 | **57,372** |
| 缺少/无法读取 `supplement_number`（应计 unknown） | **0** |
| PMA payload 非法 JSON / 合法 JSON 但非 object | **0 / 0** |
| 510(k) 总数 / 缺少 `clearance_type` | **176,466 / 0** |
| `/api/meta.dataset.approval_classification` | 两类分类均 `available=true`、unknown 均为 0 |

**企业分类计数（只读 SQL，`json_extract(payload,'$.supplement_number')` 空=原始、非空=补充）**

| 企业 / 窗口 | 原始 PMA | PMA 补充申请 | unknown | 510(k) Traditional | 510(k) 合计 |
| --- | --- | --- | --- | --- | --- |
| Medtronic · 5 年完整窗口（2022-01-01..2026-09-30） | **7** | **2,423** | 0 | 111 | 165 |
| Medtronic · 全时（..2026-10-30） | **100** | **12,820** | 0 | 1,386 | 1,976 |
| Philips · 5 年完整窗口 | **1** | **38** | 0 | 84 | 122 |
| Philips · 全时 | **8** | **161** | 0 | 729 | 994 |

- **首次进入只使用原始 PMA + Traditional 510(k)**：真实数据可判别示例——飞利浦呼吸赛道首条审批为 **2003-07-15 的 Special 510(k) K030939**，产品正确取 **2011-10-04 的 Traditional 510(k) K111378**（`first_any_approval=2003-07-15` 仅背景展示）。
- **D2 缺键路径（独立复验）**：见 §6；fixture 中“合法 JSON 缺 `supplement_number`”被计为 unknown，SQL/Python/列表/详情一致。
- **`/api/evidence` 列表与 `/api/evidence/{id}` 分类一致**：真实数据抽样 40 条 PMA + 60 条 510(k)，`approval_type` 与 `is_first_entry_candidate` **100/100 一致**；fixture 缺键记录在 `evidence_search` 与 `event_detail` 均为 `pma_unknown`、`classification_available=false`。

### 4.4 监管路径结构（window vs all-time；D3 复验）

| 指标 | Medtronic（5 年完整窗口） | Philips（5 年完整窗口） |
| --- | --- | --- |
| 审批记录分母（510(k)+PMA） | **2,595** | **161** |
| PMA 合计（原始+补充+unknown） | 2,430 | 39 |
| PMA 占比 | **93.64%** | **24.22%** |
| 原始 PMA / 补充申请 | 7 / 2,423 | 1 / 38 |
| 510(k) 合计（Traditional/Special/Abbrev/其他） | 165（111/53/0/1） | 122（84/29/9/0） |
| 全时对照（`include_all_time=true`） | 86.73%（12,920 PMA / 1,976 510(k) = 14,896） | 14.53%（169 / 994 = 1,163） |

- 比较页 `pathway` 的 `basis="complete_window_approvals_only"`、`window={2022-01-01, 2026-09-30}`，与总量使用同一完整窗口（不是全历史）。
- **D3 修复后行为**：`/api/compare` 默认与 `include_all_time=false` → `pathway_all_time=null`；`include_all_time=true` → 非空，且与独立 SQL 完全一致（美敦力 100 原始 / 12,820 补充 / 12,920 PMA / 14,896 审批；飞利浦 8 / 161 / 169 / 1,163；窗口 `1900-01-01..2026-10-30`）。UI 默认仍不请求该字段（脚注保持“全时结构未返回”），符合“窗口为主口径”的设计。
- **残余观察 R1（Low，已修复）**：`pathway_all_time.basis` 已在 `01ba4aa` 改为 `all_time_approvals_only`；HTTP 复验 `include_all_time=true` 返回该标签，数值与独立 SQL 一致，新增 API 测试断言此标签。

### 4.5 重复 / 多计审计（不变）

| 检查项 | 结果 | 结论 |
| --- | --- | --- |
| events 总行数 vs 去重 event_id | 375,378 vs **375,378** | 无重复主键 |
| 重复 `payload + url` / 重复 payload | **0 组 / 0 组** | 同一记录未重复入库 |
| 重复 url 组 | 8,512 组 | 正常：同一来源页服务多条不同产品记录 |
| 同 `source+kind+event_date+title` 组 | **1,501 组，覆盖 5,072 行** | 与 Lead 声称一致 |
| 组内不同 `(payload,url)` 对 / 组内重复 payload+url 的组数 | **5,072 / 0** | 不是重复记录 |
| 示例 | 2024-08-28 Beaver Visitec 召回：159 行、159 个不同 payload、1 个 URL | 同一次召回下 159 个产品条目 |
| 企业归属 | `company_key` 单值；Dräger/Mindray 精确别名且与主名册不相交（244 / 347，主名册 0） | 未发现同一事件归属两家 |

### 4.6 研究助手数字复算（不变）

| 回答数字 | API/UI | 独立 SQL（别名精确匹配，不调用产品归属函数） | 一致 |
| --- | --- | --- | --- |
| 迈瑞超声近窗 / 前窗 | 24 / 32 | 24 / 32 | ✅ |
| 行业超声近窗 / 前窗 | 414 / 392 | 414 / 392（+5.6%，答案取整 +6%） | ✅ |
| 迈瑞超声份额 近窗 / 前窗 | 70.6% / 69.6% | 0.7059 / 0.6957 | ✅ |
| 越界问题 | `out_of_scope`，0 证据 | —（无数据可答） | ✅ |

---

## 5. 测试可信度（`9237c1d` 实测）

### 5.1 实际执行（命令、结果、退出码、skipped）

| 层级 | 命令（工作目录 `D:\DEPPSKK\medradar`） | 实际结果 | skip | 退出码 |
| --- | --- | --- | --- | --- |
| Tier A/B（无真实 DB） | `python -m pytest tests/test_product_statistics.py` | **21 passed**（0.53s） | **0** | 0 |
| Tier C（真实 DB） | `python -m pytest tests/test_product_store.py tests/test_product_api.py tests/test_product_analyst.py` | **75 passed**（43.73s；较 `5a349f4` +1：`test_compare_all_time_pathway_is_opt_in`） | **0** | 0 |
| 全量 | `python -m pytest` | **1,170 passed + 224 subtests passed**（111.78s；较 `5a349f4` +1） | **0** | 0 |
| Tier D（浏览器 E2E） | `node scripts/product_e2e.cjs` | **6 passed, 0 failed**（18.6s；报告 `out/product_e2e/report.json`） | 0 | 0 |
| 旧 selftest | `python -m medradar selftest` | **Ran 1,074 tests — OK**（53.28s） | — | 0 |
| CI 分层 | `.github/workflows/ci.yml` `product-statistics` job | 静态确认存在：Tier A/B 无数据仓库运行；Tier C 用 `-rs` 显式报告 skip | 未执行（见 §8） | — |

> 说明：仓库 `addopts="-q"`；若命令行再传 `-q` 会叠加为 `-qq` 并抑制总结行。本表使用**不额外传 `-q`** 的标准调用取得总结行；Tier C 与全量均确认 **0 skipped**。Tier A/B 使用 `tests/product_fixture.py` 生成的临时合成 SQLite，不读取 `data/medradar.sqlite`；本次真实数据存在，故 Tier C 无 skip。专项复验：`test_fixture_meta_reports_classification_unavailable`（D2，扩展）与 `test_compare_all_time_pathway_is_opt_in`（D3，新增）均 PASS。

### 5.2 旧缺陷若回归，现有测试会不会失败？

| 历史缺陷 | 会失败的测试（已逐行阅读） | 判定 |
| --- | --- | --- |
| **旧 LQ 分母**（企业用全部记录、行业用已映射） | Tier A `test_lq_uses_mapped_denominators_not_all_records`：手算 1.8 并断言 `value != old_wrong`（1.44）；Tier B `test_fixture_compare_lq_uses_consistent_denominators`：1.8 且 `!= old_wrong_lq`；API `test_compare_lq_matches_its_own_disclosed_denominators`：用 `total_mapped`/`industry.mapped_records` 复算每个 ok 单元格 | **会失败**。旧公式回归：Tier A 得 1.44；API 真实数据美敦力心脏节律得 3.417 vs 复算 3.721，超出 `abs=1e-3`。Tier A 纯函数保证不依赖“披露字段也被一起改错” |
| **起始不完整季度未被识别**（旧 `is_period_partial(period, edge)` 只看终点） | Tier A `test_partial_period_at_both_window_edges`、`test_complete_window_quarter_year_month`、`test_comparison_windows_are_contiguous_and_equal_length`；Tier B `test_fixture_complete_period_totals_exclude_partial_edges`（`2021-Q4.partial=True`、`recent=30` vs `recent_all=32`、`partial_periods=2`、`2026-Q3.source_lag_risk=True`） | **会失败**。旧实现会把 2021-Q4 标为完整 → fixture `recent` 变 32、`partial_periods` 变 1，三处断言失败 |
| **PMA 补充申请被当作首次进入** | Tier B `test_fixture_pma_first_entry_ignores_supplements_and_special_510k`：补充申请 2015-05-01 早于原始批准 2016-09-01，断言 `first_approval=2016-09-01`、`first_any_approval=2015-05-01` 与里程碑标签；`test_fixture_event_detail_exposes_approval_type` 断言 list/detail 一致 | **会失败**。旧 `_company_track_firsts` 用 `MIN(event_date)` 取任意 510(k)/PMA → fixture 呼吸 `first_approval` 变 2015-05-01 |
| **D2：合法 JSON 缺 `supplement_number` 被当原始批准** | Tier B `test_fixture_meta_reports_classification_unavailable`（`9237c1d` 扩展）：fixture 新增缺键记录，断言 `headline.pma_unknown_all_time==2`、`pma_classification_available=false`、`evidence_search` 返回 1 条且 `approval_type=pma_unknown`、`event_detail` 同为 `pma_unknown` | **会失败**。若 SQL 谓词退回旧版：缺键记录被计入 original → `pma_unknown_all_time` 变 1、列表/详情与 fixture 期望 2 不符，断言失败；我的独立复现也显示旧 SQL original=8 vs 新 SQL 7 |

补充核验：旧恒真断言 `assert all(... or True ...)` 存在于 `f3ea1e4:tests/test_product_store.py`；当前版本已替换为“API 返回总数 == 独立 `SQL LIKE` 计数”并逐条详情复核。`grep` 在 `tests/`、`scripts/` 无 `or True` 残留。Tier B fixture 期望值由手算常量与显式事件计数构造。

### 5.3 测试剩余盲区（供 Lead 决策，非阻断）

1. API LQ 测试从响应自身字段复算；若“计算与披露字段被同一回归一起改错”可能漏检，目前由 Tier A 纯函数兜底。
2. 真实数据中不存在“补充申请早于原始批准”的呼吸赛道企业，supplement-as-first-entry 的判别主要依赖合成 fixture。
3. 无 HTTP 外链可达性测试（只验证 URL 非空与字段一致）。
4. `pathway_all_time.basis` 标签语义已有 API 测试断言（`01ba4aa`）。
5. 无针对 `/api/compare` 的 `include_all_time=true` 与 UI 展示联动的测试（UI 默认不请求，属设计）。

---

## 6. 交付前追加修复（D1–D4）验证

> 以下问题由本审计员在 `5a349f4` 首轮审计中发现；Lead 在 `9237c1d`（父 `5a349f4`，10 个文件变更）中修复。本节为**独立复验**（不采信修复说明）。

| # | `5a349f4` 首轮问题 | `9237c1d` 修复（代码/文档证据） | 我的独立复验（命令/观测） | 结论 |
| --- | --- | --- | --- | --- |
| **D1** | `docs/PRODUCT_STATISTICAL_AUDIT.md` §2.4 本期/上期请求窗口数字写反（写成 1,552/1,111） | diff `5a349f4..9237c1d`：§2.4 改为本期 **1,111**、上期 **1,552**（完整季度 1,051/1,480 不变） | 读文件确认；独立 SQL：本期请求窗口 cardiac = **1,111**、上期请求窗口 = **1,552**；产品 claim = 1,051/1,480 | **PASS（已修复）** |
| **D2** | SQL 把“合法 JSON 但缺 `supplement_number`”计为原始批准，Python/审计计为 unknown（真实数据 0 例） | `store._pma_original_sql()` 增加 `json_type(payload,'$.supplement_number') IS NOT NULL`；`tests/product_fixture.py` 新增缺键 PMA（2021-11-21，`{"pma_number":"P900002"}`），`classification_unknown=2`；Tier B 断言 SQL/列表/详情一致 | `out/acceptance2/d2_check.py`：fixture 新 SQL original=**7**、旧 SQL=**8**、unknown=**2**；Python=`pma_unknown` 且 `is_first_entry_candidate=false`；`evidence_search` 与 `event_detail` 均为 `pma_unknown`、`classification_available=false`；真实数据 PMA 57,372 / unknown **0**、Medtronic 窗口 **7/2,423** 不变 | **PASS（已修复）** |
| **D3** | `/api/compare` 未透传 `include_all_time`，经 HTTP 无法取得全历史路径结构 | `medradar/web/app.py` 新增 `include_all_time: bool = Query(False)` 并透传；新增 API 测试 `test_compare_all_time_pathway_is_opt_in` | `out/acceptance2/d3_check.py`：默认/`false` → 两企业均 null；`true` → 美敦力 pma 12,920（100/12,820）、approvals 14,896；飞利浦 169（8/161）、1,163；窗口 `1900-01-01..2026-10-30`；与独立 SQL 完全一致；默认 `pathway` 窗口仍为 2022-01-01..2026-09-30 | **PASS（已修复）** |
| **D4** | 企业页 PMA 拆分/路径分母含未映射记录，而“已映射赛道审批”KPI 仅含已映射，标签未说明 | `web/js/pages/company.js` 在 `company-pma-split` 说明中追加“PMA 拆分与路径结构使用该企业完整窗口内全部审批记录（含未映射赛道记录）；上方‘已映射赛道审批’KPI 仅统计已映射记录。” | `out/acceptance2/d4_check.cjs`：该文本存在；KPI 2,396 / 2,734 / 7 / 2,423；完整窗口全部 2,595 = 已映射 2,396 + 未映射 199；路径 approvals_total 2,595，自洽 | **PASS（已修复）** |
| **D5** | 工作区未提交的 README / PRODUCT_ROADMAP / 验收文档（首轮） | 上述文档已随 `9237c1d` 提交；复验开始时工作区仅用户 CSV 为 M | `git status --short`；`git show --stat 9237c1d` 含 README、ROADMAP、验收文档 | **PASS（已解决）** |

**R2（Info，已解决）**：复验期间出现的两份文档修改（`docs/PRODUCT_STATISTICAL_AUDIT.md` 追加 §6、`web/CONTRACT.md` 补充 `include_all_time` 参数）已随 `01ba4aa` 提交；交付时工作区仅剩用户本地 CSV 修改。

---

## 7. 缺陷台账（`9237c1d` 最终状态）

| ID | 严重度 | 位置 | `5a349f4` 状态 | `9237c1d` 复验状态 |
| --- | --- | --- | --- | --- |
| **D1** | Major（文档） | `docs/PRODUCT_STATISTICAL_AUDIT.md` §2.4 | 数字写反（1,552/1,111） | **已修复并复验 PASS**（1,111/1,552） |
| **D2** | Medium（潜在产品） | `medradar/product/store.py` `_pma_original_sql()` | 缺键 PMA 被当原始批准（真实 0 例） | **已修复并复验 PASS**（SQL/Python/列表/详情一致；真实数据仍 0 unknown） |
| **D3** | Low（API/文档） | `medradar/web/app.py` `/api/compare` | `pathway_all_time` 经 HTTP 恒 null | **已修复并复验 PASS**（默认 null；`include_all_time=true` 返回且与 SQL 一致） |
| **D4** | Low（标注清晰度） | `web/js/pages/company.js` PMA 拆分说明 | 未说明含未映射 | **已修复并复验 PASS**（页面文本明确 + 数字对账） |
| **D5** | Info（发布状态） | 工作区 | README/ROADMAP/验收文档未提交 | **已解决**（随 `9237c1d` 提交；复验时仅用户 CSV 为 M） |
| **R1** | Low（已修复） | `/api/compare?include_all_time=true` 的 `pathway_all_time.basis` | Lead 后续提交 `01ba4aa` | **已修复**：basis=`all_time_approvals_only`，新增 API 断言；数值不变 |
| **R2** | Info（已解决） | 工作区 | 已提交 | 两份文档已纳入 `9237c1d`/`01ba4aa`；交付时仅用户 CSV 为本地修改 |

> 首轮对 Lead 审计 §2.1/§2.2/§2.3/§2.5 的数字复算全部吻合；§3 测试计数在 `9237c1d` 上更新为 21/75/1,170+224/6/1,074，均已实测。`9237c1d` 未改变任何已观测测量值。

---

## 8. 明确“未验证 / 不可用”

**未验证（本轮无权限/无网络/超出范围，不能宣称通过）**

1. **外部来源链接的 HTTP 可达性**：仅验证了 375,378/375,378 条记录 URL 非空且为 `http(s)`，并抽查事件详情链接与 API 一致；未逐条请求，也未验证失效/重定向/付费墙。
2. **CI 实际运行**：只静态确认 `.github/workflows/ci.yml` 存在 `product-statistics` job；未触发 GitHub Actions，未验证远端绿/红。
3. **浏览器覆盖面**：仅 Chrome（Playwright headless）；未测 Firefox/Safari/Edge、真实移动设备、触屏手势、键盘导航与完整无障碍（a11y）审计。
4. **其他路由/指标/赛道**：只验收任务指定的五场景；未穷举 8 条路由、6 个指标、雷达其余 17 个重点赛道（全库共 60 个赛道）、5+ 企业比较、证据分页/搜索完整交互、`recalls`/`trials`/`corporate` 指标、导出/打印等。
5. **性能**：未做基准测试（不在本轮统计验收范围）。
6. **API 非 `approvals` 指标下的 LQ/窗口一致性**：逻辑共用，但未逐指标复算。

**不可用（产品如实声明或数据本身不具备）**

1. **真正的 point-in-time 回放**：`first_seen_at` 仅 2026-10-30/31 抓取日，`available_at` 等于事件日，无法还原“当时可知”的信息集；产品按事件日期回看。
2. **经验证预测**：不存在（lab 明确“无已验证的前瞻校准”），产品不提供预测/因果结论。
3. **人工真值标签**：69 份证据包 **0 条人工标签**，AI 预标注不可当人工真值；研究结论仍待人工复核。
4. **人工复核后的企业归属**：Dräger/Mindray 为 `PENDING_HUMAN_REVIEW`，计数可能随复核变化。
5. **全球/非美国数据**：仅美国 FDA 等公开记录，不代表企业全球活动（尤其迈瑞、德尔格）。
6. **产品级计数**：记录 ≠ 产品，一次申请可拆多行；产品已在 UI/文档声明。
7. **未映射赛道的行业份额**：完整窗口审批记录中约 31.3% 未映射赛道（行业映射率 68.7%），LQ/份额只在已映射口径内成立。
8. **比较页 UI 的全历史路径结构**：API 已支持 `include_all_time`（D3 已修复），但 UI 默认不请求、页面脚注仍显示“全时结构未返回”；这是设计选择，不是缺陷，但“页面无全历史结构”本身未经验证。

---

## 9. 最终判定与剩余阻断项

**最终判定（基于 `9237c1d`、真实数据、独立复验）**

- 五个必需场景：**PASS（1440×900 与 390×844 共 10/10）**，`9237c1d` 未改变测量值。
- 统计修复核心主张（一致 LQ 分母、完整季度窗口、PMA 原始/补充分类、window-based 路径结构、无重复计数）：**经验证成立**。
- 交付前 D1–D4：**全部修复并独立复验 PASS**；D5 已随提交解决。
- 测试：21 + 75 + 1,170+224 + 6/6 + 1,074，全部 exit 0、0 skipped；四类历史缺陷均有会失败的回归测试。
- 未发现阻断性缺陷；R1/R2 已全部关闭（R1 于 `01ba4aa` 修复并验证，R2 已提交）。
- **建议：进入最终人工验收（final human acceptance）。** 产品定位仍为“证据型研究终端”，不得描述为预测、因果或企业创新能力排名工具。

**剩余阻断项（应带到下一阶段/人工验收）**

1. 赛道映射覆盖：全库 52.36%；完整窗口审批映射率 68.7%（行业）/ 92.33%（美敦力）/ 88.82%（飞利浦）——未映射记录不能进入赛道份额/LQ。
2. Dräger/Mindray 企业归属 `PENDING_HUMAN_REVIEW`（244 / 347 事件），需人工复核后才可作为定论。
3. 69 份证据包 0 条人工标签：任何研究结论（H1–H4、Target B）仍不可用。
4. 无真正 point-in-time；当前视图是“按事件日期回看”。
5. 无经验证预测/因果模型；研究实验室只展示不确定与负面状态。
6. 外部 URL 可达性未验证；对外发布前需一次外链健康检查。
7. R1/R2 已处理；用户 CSV 仍为本地修改，需保持未提交或由用户自行决定。

---

## 10. 复现命令与证据文件索引

```bash
# 锚点与仓库事实（产品代码 01ba4aa；独立审计锚点 9237c1d）
git rev-parse HEAD                      # 报告提交前：01ba4aa
git rev-parse HEAD^                     # 5a349f4e230cbba911d5c623ae83bb173b601c77
git log -1 --format='%H %ci %s'
git rev-parse main origin/main          # b2a14c0a92332c004445de686daee97754cf94cb
git merge-base --is-ancestor 9237c1d main; echo $?   # 1 → main 未包含 9237c1d
git merge-base --is-ancestor research/full-history-v1 main; echo $?  # 1 → hist_v1 未合并
gh pr view 12 --json number,state,isDraft,headRefOid # OPEN / true / 9237c1d…
git status --short                      # 复验开始：仅用户 CSV 为 M；复验期间出现两份文档 M（非本审计员）

# 服务 / 数据
curl -s http://127.0.0.1:8787/api/health

# 测试（§5.1 的实际命令）
python -m pytest tests/test_product_statistics.py
python -m pytest tests/test_product_store.py tests/test_product_api.py tests/test_product_analyst.py
python -m pytest
node scripts/product_e2e.cjs
python -m medradar selftest

# 独立复算与浏览器（本审计员自写，均在 out/acceptance2/）
python out/acceptance2/recompute.py          # LQ / 窗口 / PMA / 路径 / 重复 只读 SQL 复算
python out/acceptance2/final_facts.py        # API/SQL 事实汇总
python out/acceptance2/d2_check.py           # D2：fixture 缺键 PMA（SQL/Python/列表/详情）
python out/acceptance2/d3_check.py           # D3：include_all_time 默认 null / 请求后非空 + SQL 对照
node out/acceptance2/d4_check.cjs            # D4：企业页 PMA 拆分说明 + 数字对账
node out/acceptance2/browser_scenarios.cjs   # 10 次场景运行 + 截图 + browser_report.json
node out/acceptance2/extra_checks.cjs        # DOM 细节（不适用单元格、PENDING、移动端溢出）
node out/acceptance2/claim_panel_check.cjs   # 结论→证据面板复算文本
```

**证据文件（`out/acceptance2/`，gitignored）**

- 报告 JSON：`browser_report.json`（`9237c1d` 重跑，10 项、console errors=0）、`extra_report.json`、`recompute_result.json`、`final_facts.json`、`d2_result.json`、`d3_result.json`。
- 日志：`pytest_statistics_9237.log`、`pytest_tierC_9237.log`、`pytest_full_9237.log`、`product_e2e_9237.log`、`selftest_9237.log`、`d2_check.log`、`d3_check.log`、`d4_check.log`、`extra_checks_9237.log`、`claim_panel_9237.log`。
- 截图：`s1-company-mindray-{desktop,mobile}.png`、`s2-compare-{desktop,mobile}.png`、`s3-radar-respiratory-{desktop,mobile}.png`、`s4-evidence-trace-{desktop,mobile}.png`、`s4a-claim-evidence-panel.png`、`s5a-analyst-answered-{desktop,mobile}.png`、`s5b-analyst-outofscope-{desktop,mobile}.png`、`s6-draeger-pending-desktop.png`、`s7-lab-desktop.png`、`s8-overview-desktop.png`、`s9-mobile-claim-evidence.png`、`s10-mobile-analyst.png`、`s11-lab-s027-detail.png`、`s12b-company-pma-split-visible.png`。
- 仓库可提交截图：`docs/product/company-mindray.png`、`compare.png`、`radar-respiratory.png`、`evidence-trace.png`、`analyst.png`、`mobile-company.png`、`overview.png`（已于 `01ba4aa` 按当前 HEAD 重新生成）。

---

*本报告基于独立审计锚点 `9237c1d`、R1 修复 `01ba4aa` 与 2026-10-30 数据截止的真实观测；未观测到的不标记为 PASS。审计期间未修改产品代码、测试、数据或服务。*
