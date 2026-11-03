# MedRadar 2.0 — Statistical Audit & Fix Report

**审计对象**：`feat/medradar-2.0-mvp` / PR #12（Draft）
**审计基线**：`f3ea1e4` → 修复 HEAD 见文末
**数据**：`data/medradar.sqlite`，data edge **2026-10-30**，375,378 events（openFDA 510(k) 176,466 · PMA 57,372 · 召回 59,646 · 试验 55,592 · 8-K 20,976 · 药品 5,326）
**原则**：优先修正计算与口径，不通过修改文案/测试预期掩盖错误；所有关键数字独立复算。

---

## 1. 问题与修复

### P0-1 — Location Quotient 分母不一致（Blocking）

- **原始错误**：`company_compare()` 中企业赛道占比用
  `company_track / company_total_records`（企业窗口内**全部**审批记录，含未映射赛道），
  而行业占比用 `industry_track / industry_mapped_records`（行业**仅已映射**记录）。
  两者分母口径不同，未映射记录在分子/分母之间不对称，LQ 被系统性放大或缩小。
- **根本原因**：企业侧 `total` 取自完整窗口序列（mapped+unmapped），行业侧 `industry_total`
  只求和 `track_id IS NOT NULL`；代码没有把“企业分母”和“行业分母”绑定为同一定义。
- **修改位置**：`medradar/product/store.py`
  - 新增纯函数 `location_quotient()`（统一阈值与状态）；
  - `company_compare()` 使用 `company.total_mapped`（窗口内已映射）与 `industry_mapped_records`；
  - 新增企业/行业 `mapping_coverage`、`total_unmapped`、`industry_all_total` 等披露字段；
  - 样本不足/零分母返回 `lq_status != "ok"`，Web 显示“不适用”，不制造数值。
- **新口径**：
  `LQ = (企业该赛道已映射记录 / 企业已映射记录) / (行业该赛道已映射记录 / 行业已映射记录)`
  阈值：企业已映射 < 10、行业赛道 < 5、任一分母 0、该企业该赛道 0 → 不适用。
- **回归测试**：
  - Tier A `test_lq_uses_mapped_denominators_not_all_records`（断言 1.8 而非旧公式 1.44）；
  - Tier B `test_fixture_compare_lq_uses_consistent_denominators`（合成 fixture，独立手算）；
  - API `test_compare_lq_matches_its_own_disclosed_denominators`（用响应自身
    `n / total_mapped / industry_total / industry_mapped` 复算每一个 LQ）。
- **状态**：已解决。

### P0-2 — 不完整周期只识别终点（Blocking）

- **原始错误**：`is_period_partial(period, edge)` 只把“包含数据截止日的周期”标为不完整。
  当研究窗口从季度中途开始（如 2021-10-31 起的 5 年窗口），起始季度 2021-Q4
  也被截断，却仍被当作完整周期参与同比。
- **根本原因**：函数没有窗口起点参数；`_fill_series` 只拿到 `edge`；
  `previous_window()` 直接用起止日期回退，不保证对照窗口与本期都是完整周期。
- **修改位置**：`medradar/product/store.py`
  - 新增 `period_bounds()` / `period_flags()` / `complete_window()` /
    `comparison_windows()`；
  - `is_period_partial(period, granularity, window_start, window_end)` 同时检查起点与终点；
  - `comparison_windows()` 生成**紧邻、等长、完整自然季度**的本期/对照窗口
    （例：2022-01-01–2026-09-30 vs 2017-04-01–2021-12-31，各 19 季度，无缝隙）；
  - 企业结论、比较、雷达、研究助手全部改用完整周期计数；窗口全部记录单独披露；
  - `partial` 与 `source_lag_risk` 分离：日历完整但距截止 < 90 天的周期标记源数据可能修订；
  - 无法形成完整周期时 `comparable=false`，同比/份额/LQ 不计算。
- **回归测试**：
  - Tier A：起止不完整、同一周期、完整年度、跨年季度、月度边界、空窗口、等长连续性；
  - Tier B：2021-Q4/2026-Q4 partial、2026-Q3 source_lag_risk、完整窗口 vs 请求窗口计数；
  - Tier C：真实数据 Medtronic/Philips 五年窗口复算。
- **状态**：已解决。

### P1-1 — PMA 原始批准与 Supplement 未区分（Major）

- **原始错误**：`approvals = 510(k) + PMA` 把 PMA 补充申请当作独立“批准/新技术”计数；
  “首次进入”“里程碑”使用任意 PMA 记录，导致补充申请（如工艺变更、30-Day Notice）
  被误读为新器械首次进入。
- **数据可用性结论**：openFDA PMA payload 对 **57,372/57,372** 条记录提供
  `supplement_number`（空=原始批准，非空=补充申请）；510(k) payload 对
  **176,466/176,466** 条提供 `clearance_type`（Traditional/Special/Abbreviated/…）。
  **可以可靠区分，不需要 `classification_unavailable`。**
- **修改位置**：`medradar/product/store.py`
  - 新增 `approval_classification()`、`_pma_original_sql()`、`_pma_supplement_sql()`、
    `_traditional_510k_sql()`、`first_entry_sql()`、`classification_audit()`；
  - “首次进入/里程碑/雷达新进入企业”只使用**原始 PMA + Traditional 510(k)**；
  - 企业页/比较页/事件详情展示 PMA 原始 vs 补充申请、510(k) 类型；
  - 审批总量指标保留原口径（不破坏既有模块），但新增 `pma_original/` `pma_supplement`
    独立计数与披露；无法解析 payload 的记录标记 `unknown`，绝不猜测。
- **影响检查**：企业主页、比较、雷达、首次进入、研究助手、Evidence Explorer
  均已更新；既有科研实验（research/）未被改写。
- **回归测试**：Tier A 分类纯函数；Tier B 原始/补充/未知/510k 类型与首次进入顺序；
  API 事件详情分类字段。
- **状态**：已解决（真实数据分类可用；历史研究结论未被重新解释）。

### P1-2 — 监管路径结构使用全历史窗口（Major）

- **原始错误**：比较页 `pathway` 使用 `_company_counts()` 的全历史 PMA/510(k) 计数，
  而总量/份额使用最近五年窗口；同一行数字来自两个时间范围。
- **根本原因**：`company_compare()` 未传窗口给路径结构计算。
- **修改位置**：`store._pathway_window()` / `company_compare()` /
  `company_profile()`；路径结构按**同一完整比较窗口**计算；
  全历史结构仅作为 `pathway_mix_all_time` 明确标注展示（比较页默认不计算，
  需 `include_all_time=true`）；比较警告同步使用窗口口径。
- **回归测试**：Tier B `test_fixture_pathway_is_window_based_and_all_time_is_separate`
  （2010/2011 全历史事件不进入窗口结构；全历史值单独请求后不同）；真实数据复算。
- **状态**：已解决。

### P1-3 — 无效/空转测试断言（Major）

- **原始错误**：`tests/test_product_store.py` 关键词测试含
  `... or True`，断言恒真；部分测试只检查字段存在、或把 API 输出与同一函数
  的返回值比较，无法发现计算回归。
- **修改位置**：`tests/test_product_store.py` / `test_product_api.py` /
  `test_product_analyst.py` / `scripts/product_e2e.cjs`
  - 删除恒真断言；关键词检索改为独立 SQL LIKE 计数；
  - 新增 API LQ 公式复算测试；
  - 新增 Tier A/B 独立算术/fixture 预期值；
  - 研究助手测试改为与 `comparison_windows()` 及独立 `evidence_search` 对齐；
  - E2E 比较场景新增“无效选择清空旧图/警告”检查。
- **回答“若错误重现，测试能否发现？”**：能。LQ 旧分母公式在 fixture 测试中
  给出不同数值（1.44 vs 1.8）；完全不完整周期处理会被
  `partial=True` / 完整窗口计数测试捕获；PMA supplement 被当作首次进入会被
  `first_entry`/`entrants` 测试捕获。
- **状态**：已解决。

### P1-4 — 测试依赖本地 1.37GB 数据库（Major）

- **问题**：产品测试模块在无 `data/medradar.sqlite` 时整模块 skip，CI 无法覆盖核心计算。
- **修改位置**：
  - 新增 `tests/product_fixture.py`：运行时生成**合成 SQLite**（明确 synthetic），
    含多家虚拟企业、4 个赛道、已映射/未映射记录、510(k) Traditional/Special、
    PMA 原始/补充/损坏 payload、不完整周期、无法归属记录、证据来源；
  - `store.use_database()` 允许测试把生产代码指向 fixture，禁止 mock 计算；
  - 新增 `tests/test_product_statistics.py`（Tier A + Tier B，不依赖真实 DB）；
  - `.github/workflows/ci.yml` 新增 `product-statistics` job：安装 `.[dev,web]`，
    在无数据环境下运行 Tier A/B，并对 Tier C 显式输出 skipped（不当作 passed）。
- **状态**：已解决。

---

## 2. 数值变化（真实数据，修复前 → 修复后）

> 修复前 = `f3ea1e4` 的实现；修复后 = 本报告 HEAD。
> 旧 LQ 的分母为企业窗口内全部审批记录；新 LQ 的企业与行业分母都是已映射记录。

### 2.1 Medtronic vs Philips：LQ（同赛道）

| 指标 | 旧 LQ（旧分母 + 请求窗口） | 仅修分母（请求窗口） | 新口径（完整季度） |
| --- | --- | --- | --- |
| Medtronic · 心脏节律 | 3.417 | 3.698 | **3.721** |
| Philips · 超声 | 8.114 | 9.101 | **9.323** |
| Philips · 患者监护 | 3.520 | 3.948 | **4.042** |
| Philips · 心脏节律 | 0.912 | 1.023 | **1.068** |
| Medtronic · 患者监护 | 0.021 | 0.023 | **不适用**（企业该赛道 0 条） |

旧/新差异来源：旧公式企业分母 2,734（Medtronic 请求窗口全部审批，含 208 条未映射）
vs 新分母 2,396（完整季度已映射）；行业分母均为已映射（旧口径行业 18,640 条请求窗口，
新口径完整季度 17,804 条）。**LQ 只描述记录分布，不是创新能力/市场份额。**

### 2.2 完整周期 vs 请求窗口（五年）

| 指标 | 请求窗口（旧） | 完整季度（新） |
| --- | --- | --- |
| Medtronic 审批记录（已映射） | 2,526 | **2,396** |
| Medtronic 审批记录（全部） | 2,734 | **2,595** |
| Philips 审批记录（已映射） | 148 | **143** |
| Philips 审批记录（全部） | 166 | **161** |
| 比较窗口 | 2021-10-31–2026-10-30 | **2022-01-01–2026-09-30（19 季度）** |
| 对照窗口 | 2016-11-01–2021-10-30 | **2017-04-01–2021-12-31（19 季度）** |

### 2.3 PMA 路径结构与补充申请（五年完整窗口）

| 指标 | 旧（全历史） | 新（窗口） |
| --- | --- | --- |
| Medtronic PMA 占审批记录 | 86.7% | **93.6%** |
| Medtronic 原始 PMA / 补充申请 | —（未区分） | **7 / 2,423** |
| Medtronic 原始 PMA 占 PMA | — | **0.29%** |
| Philips PMA 占审批记录 | 14.5% | **24.2%** |
| Philips 原始 PMA / 补充申请 | —（未区分） | **1 / 38** |

结论：Medtronic 的“审批记录”绝大多数是 PMA 补充申请；旧版把补充申请与原始批准
一起当作创新事件会严重误导。产品现在在总量旁明确披露该构成，首次进入只用原始批准。

### 2.4 企业结论数字变化（Medtronic 心脏节律）

| 指标 | 旧 | 新 |
| --- | --- | --- |
| 本期（近 5 年） | 1,111（请求窗口） | **1,051（完整季度）** |
| 上期 | 1,552（请求窗口） | **1,480（紧邻 19 季度）** |
| PMA 原始 / 补充（本期） | 未显示 | **2 / 1,048** |

### 2.5 雷达（呼吸与麻醉）

| 指标 | 旧 | 新 |
| --- | --- | --- |
| 近 10 年 | 570（请求窗口） | **560（完整季度）** |
| 对照窗口 | 763 | **740** |
| 窗口全部记录 | 570 | **570（单独展示）** |
| 部分周期记录 | 未拆分 | **10** |

---

## 3. 测试执行情况

> 以下为最终 HEAD 上实际执行的命令与结果（详见 `docs/PRODUCT_ACCEPTANCE.md`）。

| 层级 | 命令 | 结果 |
| --- | --- | --- |
| Tier A + B（无真实 DB） | `python -m pytest tests/test_product_statistics.py` | **21 passed**（纯单元 + 合成 fixture） |
| Tier C（真实 DB） | `python -m pytest tests/test_product_store.py tests/test_product_api.py tests/test_product_analyst.py` | **75 passed, 0 failed, 0 skipped** |
| 全量回归 | `python -m pytest` | **1170 passed + 224 subtests, exit 0**（115.4s） |
| Tier D（浏览器 E2E） | `node scripts/product_e2e.cjs` | **6/6 passed** |
| 旧 selftest（unittest discovery） | `python -m medradar selftest` | **1,074 tests OK, exit 0** |
| CI 分层 | `.github/workflows/ci.yml` `product-statistics` job | 无数据环境运行 Tier A/B；Tier C 显式 skipped |

**跳过策略**：Tier C 在缺少 `data/medradar.sqlite` 时整模块 skip；CI 使用 `-rs`
输出 skip 原因，报告中不把 skipped 计入 passed。Tier D 需要本地运行服务，不在 CI 默认执行。

---

## 4. 最终结果

- **五个 MVP 场景**：最终验收见 `docs/PRODUCT_ACCEPTANCE.md`（独立验收员基于本 HEAD 复跑）。
- **阻断性问题**：P0-1、P0-2 已解决；P1-1、P1-2、P1-3、P1-4 已解决。
- **是否建议进入最终人工验收**：待最终 E2E/独立验收通过后确认。
- **必须留给下一阶段**：
  - 赛道映射覆盖仍约 52%，未映射记录不能进入赛道份额/LQ；
  - 企业实体映射（Dräger/Mindray）仍待人工复核；
  - 无真正 point-in-time（first_seen 不可用），当前按事件日期回看；
  - 69 份证据包人工标签仍为 0；无经验证预测；
  - 外部来源链接未逐条做 HTTP 可达性验证。
- **当前 HEAD**：见提交记录与 PR。
- **PR**：https://github.com/ChazY11/medradar/pull/12 （保持 Draft，main 未改动）

---

## 5. 独立审计补充（本轮有限范围）

| 审计项 | 结论 |
| --- | --- |
| 企业归属重复计数 | 无重复 `event_id`；`company_key` 单值映射；Dräger/Mindray 补充索引与主名册事件不相交；未发现同一事件归属两家企业。 |
| 企业监管路径可比性 | 比较页按同一完整窗口计算 PMA/510(k) 结构，并以 warning 披露路径差异；PMA 以补充申请为主时单独警告。 |
| 同事件跨来源重复统计 | 无重复 event_id / payload+url；1,501 组“同来源+同日期+同标题”是不同产品/型号记录（payload 与 URL 不同），不是同一条记录重复入库。 |
| 全行业分母 vs 企业分母 | 已统一为“已映射记录”，并分别披露覆盖率与未映射数量。 |
| 未映射赛道披露 | 企业页/比较页/雷达页均显示未映射/未归属计数，未映射不当作零活动。 |
| 时间窗 off-by-one | SQL 使用 `>= start AND <= end` 闭区间；完整周期边界有 Tier A 测试（起始/结束/同周期/跨年/月边界/空窗口）。 |
| 研究助手不可追溯数字 | 每个回答的数字来自 store 查询，evidence 事件可 `event_detail` 命中；测试校验数量一致。 |
| “首次进入”语义 | 已改为“数据覆盖期内首次观察到**原始批准**”，明确不等于企业首次进入市场。 |
| 缺失被误判为零 | 未映射/未归属单独列出；赛道表中未出现的赛道只表示数据覆盖期内未观察到记录，不等同于零活动。 |
| 统计信号误导 | UI/API 均标注“不是预测/不是因果”，信号只基于完整季度历史基线。 |

---

## 6. 交付前追加修复（独立审计 D1–D4，commit `9237c1d`）

独立验收员在 `5a349f4` 上发现 4 个非阻断问题，已在 `9237c1d` 修复并复验：

| # | 问题 | 修复 |
| --- | --- | --- |
| D1 | 本报告 §2.4 的请求窗口本期/上期数字写反 | 已改为 1,111 / 1,552；完整季度 1,051 / 1,480 |
| D2 | SQL 谓词把“合法 JSON 但缺 `supplement_number`”当作原始 PMA，而 Python 分类器/审计计为 unknown（真实数据 0 例） | SQL 增加 `json_type(...) IS NOT NULL`，与 Python 一致；合成 fixture 增加缺键记录，Tier B 断言 SQL/列表/详情三处一致 |
| D3 | `/api/compare` 未透传 `include_all_time`，经 HTTP 无法取得全历史路径结构 | 路由新增参数并透传；API 测试覆盖默认 null / 请求后非空 |
| D4 | 企业页 PMA 拆分/路径结构含未映射记录，而“已映射赛道审批”KPI 仅含已映射，标签未说明 | PMA 拆分说明明确“全部窗口审批记录（含未映射）”，并指向上方已映射 KPI |

复验：D1–D4 全部通过；产品测试 **96 passed**，全量 **1170 passed + 224 subtests**，E2E 6/6，selftest 1,074 OK；五场景数字与 `5a349f4` 一致（修复不改变测量值）。完整独立验收见 [`PRODUCT_ACCEPTANCE.md`](PRODUCT_ACCEPTANCE.md)。
