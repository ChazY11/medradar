# FINAL-PREFLIGHT-001 / 真实浏览器验收

- 环境：Playwright 驱动的 Chrome，通过 **SSH 隧道** 访问 staging `127.0.0.1:8792`
- 认证：staging Alpha 门（HTTP Basic → 会话 Cookie），凭据为本轮临时生成，不入库
- 数据：staging v3 账本，16,253 条观测 / 45,174 节点图谱
- 结论：**PASS**（发现并修复了 1 个发布阻塞；另有 3 个非阻塞问题记录在 §6）

---

## 1. 判定摘要

| 项 | 结果 |
| --- | --- |
| 页面首次加载 | ✅ 渲染完成，标题、导航、来源状态、筛选、四个视图全部出现 |
| 登录与会话保持 | ✅ Basic 认证后签发 `medradar_alpha_session`；**F5 刷新后无 401** |
| 默认情报 Feed | ✅ 47 条"最新发现"、8,168 条"最新观察"、8,006 历史、162 待核实 |
| 召回事件详情 | ✅ Curaplex 99838：FDA 号 Z-0144-2027、公开 2026-10-09、事件日 2026-06-12 |
| 原始证据链接 | ✅ "Open the original record" / "Open official source" 指向 accessdata.fda.gov |
| 企业与设备信息 | ✅ 图谱分支证据显示 company · topic、product candidate、CONFIRMED |
| 图谱展示 | ✅ 15 个技术分支、1,614 条企业证据行、两个时钟（Public / Knowledge time） |
| 图谱节点点击 | ✅ "Browse all evidence" → "Branch evidence" 对话框，含官方来源链接 |
| 历史时间查询 | ✅ Knowledge time + As-of 2026-11-01 → 分支数 15 → **0**（正确：账本 11-17 才建立） |
| 证据翻页 | ✅ Feed 分页 "42 records · Page 1 of 3" → 点 ">" 到 "Page 2 of 3" |
| 变化记录翻页 | ✅ "What changed" 面板：added 29,082 / changed 0 / removed 0，"listed 300 of up to 29082 per kind" |
| 中文界面 | ✅ `lang=zh-CN`，H1 "实时情报流"，导航 "实时雷达/科技地图"，卡片"打开官方来源" |
| 英文界面 | ✅ H1 "Live Intelligence Feed"，导航 "Live radar / Technology map" |
| 移动视图 | ✅ 390×844，`scrollWidth 375 < innerWidth 390`（无横向溢出） |
| 页面刷新 | ✅ F5 后页面完整、网络无 4xx/5xx、无 401 |
| 旧地址跳转 | ✅ `/events` → 302 → `/radar` |
| 空数据状态 | ✅ Knowledge-time 视图 0 分支时给出解释文案，不崩溃 |
| API 错误状态 | ✅ 503 时页面显示"出错了" + 服务端原因 + "重试"按钮，不白屏 |
| Console 错误 | ✅ **0 errors / 0 warnings**（整轮会话） |
| 网络 4xx/5xx | ✅ 正常路径全 200；仅故障注入时按预期出现 503 |

---

## 2. 发现并修复的发布阻塞

### 2.1 证据抽屉与 Feed 互相矛盾

**现象**：每张卡片的判定维度都正常显示，但点开"证据"抽屉时，"Why this record is here"
一节写着 **"No qualification decision is recorded for this observation yet."**

**根因**（定位到行）：`api.py` 的 `/intelligence/{id}` 用 `ledger.observation_row()` 取行，
该函数只附加 `facets`，不附加 `admission`；而 `_event()` 直接读 `row.get("admission")`，
于是恒为 `None`。Feed 走的是另一条路径（查询时 join 了 `admission_current`），所以两边不一致。

**为什么是发布阻塞**：证据抽屉是读者核验"这条为什么在我面前"的唯一入口。
产品在最关键的一处自相矛盾，属于核心使用流程故障。

**修复**（`b6f4506`）：新增 `ledger.current_admission()`（与 Feed 同一投影），
详情端点显式附加。回归测试：
`test_the_evidence_drawer_reports_the_same_decision_as_the_feed` —— 断言详情与 Feed 的
`decision`、`tier`、`dimensions` 完全一致。

**修复后实测**（同一 observation）：

```
admission is null: False
decision: FEED | tier: HIGH_RELEVANCE
dimensions keys: ['confidence','decision','entity_link','freshness','importance',
                  'importance_reasons','medical_domain','monitoring_relevance','source_authenticity']
```

浏览器里 "Why this record is here" 现在显示：Relevant · 监护设备/算法性能研究 · 三条理由 ·
"Qualification score 6…"。

---

## 3. 关键界面证据

### 3.1 英文 Feed（含新维度徽章与精度标签）

```
NEW | crossref | publication | Relevant | initial discovery
Patient-Specific Explainable Arrhythmia Detection Using Attention-Based Deep Networks
Published: 2026-10-29   First observed: 2026-11-17 00:14 UTC   Event date: 2026-10-2…
source · SCHOLARLY   domain · MEDICAL   relevance · DIRECT   confidence · 0.9   date · day precision
Arrhythmia detection · TOPIC_RELATED   ECG and electrocardiographic analysis · TOPIC_RELATED
[Open official source]
```

### 3.2 召回卡片（历史回填不得冒充新情报）

```
NEW | openfda_recall | regulatory_record | Needs review | historical backfill
Curaplex Capnography EtCO2/O2 Oral/Nasal Cannula Multipack (10 pk), Item Number 670272-KIT
Published: 2026-10-09   First observed: 2026-11-18 19:01 UTC   Event date: 2026-06-12   Z-0144-2027
source · PRIMARY_REGULATORY  domain · MEDICAL  relevance · DIRECT  confidence · 0.7  date · day precision
[Open official source]
```

抽屉里：

```
Why this record is here
  Needs review / recall_monitoring_device_unconfirmed
  - the product code is not a monitored family, but the official product description or reason for
    recall names a monitoring device or measurement (capnography)
  - the monitoring classification is MedRadar's, not FDA's: a reviewer must confirm it
  Discovery phase: HISTORICAL_BACKFILL
```

这一条同时证明了：召回详情、证据链接、企业/设备、历史标记、以及**产品对自己分类边界的诚实**。

### 3.3 移动端（390×844，中文）

截图见 `docs/final_preflight/001/evidence/mobile-390-zh.png`。可见：

- 单列布局，卡片完整，无横向滚动
- "42 条记录 · 第 2 页，共 3" + 四个翻页按钮
- 维度徽章换行显示："来源·PRIMARY_REGULATORY 领域·MEDICAL 相关性·DIRECT 置信度·0.95 日期·日精度"
- 筛选区单列："企业 Philips(895) / GE HealthCare(353) / Dräger(128)"

---

## 4. 认证与会话（如何在不泄露凭据的前提下验证）

1. 导航到带凭据的 URL 一次 → 服务器返回 200 + `Set-Cookie: medradar_alpha_session=…; HttpOnly; SameSite=Lax`。
2. 之后再以**不带凭据的 URL** 访问 `/radar` → 200（会话 Cookie 生效）。
3. F5 刷新 → 仍 200，网络记录里 **没有任何 401**。
4. 未认证访问 `/api/radar/health` → 401（门是有效的）。
5. 截图与日志中未出现凭据；地址栏显示 `127.0.0.1:8792/radar`。

---

## 5. 页面不崩溃的边界情况

| 情况 | 表现 |
| --- | --- |
| 时间点早于账本建立（2026-11-01） | 显示"本视图无分支"+ 解释"空树是关于证据的陈述，不是关于公司的" |
| 账本不存在（503） | 三个请求 503；页面显示"出错了" + 服务端原文 + "重试"按钮 |
| 数据量大（16,253 条） | Feed 分页稳定，无卡顿；图谱 45k 节点仍可交互 |

---

## 6. 非阻塞问题（记录，不修）

| # | 问题 | 证据 | 分类 |
| --- | --- | --- | --- |
| P1 | 英文界面里混入中文：公司名"德尔格 / GE 医疗 / 飞利浦"、Knowledge-time 说明段 | 快照中同时出现 "Company Technology Map" 与 "本视图只包含…" | **既有问题**（`TechnologyMapPage.tsx` 未被候选改动），i18n 未覆盖服务端下发的中文字段 |
| P2 | 62 个按钮中 26 个某一维 < 44px（最小 26×31：语言切换、菜单） | DOM 度量；**0 个 < 24px**（满足 WCAG 2.5.8 AA） | 既有问题，QA-002 修的是主控件 44px，头部紧凑控件未覆盖 |
| P3 | "What changed" 只列 300 条（写明 "listed 300 of up to 29082 per kind"） | 面板文案 | 设计上的有界展示，非缺陷，但读者需知道 |

三项都不影响核心情报阅读、证据核验或基本导航，**不构成发布阻塞**。

---

## 7. 未验证项

| 项 | 原因 |
| --- | --- |
| 真实公网域名下的浏览器验收 | 生产门需要生产凭据；本轮用 staging 同构建验证。公网入口的可达性另外用 curl 验证（401 = 门有效） |
| Safari / Firefox | 只测了 Chrome |
| 离线/弱网 | 未模拟 |

---

## 8. 结论

**浏览器验收 PASS。**

新前端在真实浏览器里完成了 19 项交互，Console 零错误、正常路径零 4xx/5xx，
中文/英文/移动视图/刷新/分页/历史查询/空数据/错误状态全部符合预期。
唯一的发布阻塞（证据抽屉与 Feed 矛盾）已被发现并修复，修复后回归测试固定。
