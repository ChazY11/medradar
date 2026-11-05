# 五家企业招聘数据源调查与可行性矩阵（Phase 4 · WP2 第一层）

**日期**：2026-11-04（Asia/Shanghai）
**探测时间窗**：2026-11-04 20:2x–21:4x（Asia/Shanghai）
**本机网络位置**：中国大陆（这一点对结果有实质影响，见 §5）
**可复现脚本**：`sources/probe_careers.py`（第一轮，23 次请求）、`sources/deep_probe.py`（深查，35 次请求）、
`sources/_probe_workday_medtronic.py`、`sources/_probe_workday_paging.py`、`sources/stability_check.py`、
`sources/profile_snapshot.py`、`sources/diagnose_track_coverage.py`
**原始记录**：`results/2026-11-04/source_probe.json`、`source_probe_summary.json`、`source_probe_<company>.json`、
`probe_workday_medtronic.json`、`probe_workday_paging.json`

> 本文件只记录**测量到的**东西：状态码、robots 规则原文、端点形状、字段是否存在、请求数。
> 任何「应该可以」「一般来说」都不构成证据。

---

## 1. 判定标准（先写死，再看结果）

| 状态 | 含义 |
|---|---|
| `VERIFIED` | 存在合法稳定路线；岗位 ≥20；唯一 ID 可用率 ≥0.95；描述可用率 ≥0.90；来源日期可用率 ≥0.50 |
| `EXPLORATORY` | 能拿到真实岗位，但上述任一项不达标或样本过小 |
| `BLOCKED` | 无合法稳定路线 / robots 拒绝 / 网络不可达 / 需绕过访问控制 |
| `NOT_RUN` | 未尝试 |

**未观察到岗位 ≠ 企业没有招聘。** 覆盖率分母未知，本文件只报告「我们能看见多少」。

---

## 2. 可行性矩阵（五家，全部实测）

| 企业 | 招聘系统 | 合法公开路线 | 唯一 ID | 来源发布日期 | 完整描述 | robots 判定 | 状态 |
|---|---|---|---|---|---|---|---|
| **Medtronic** | Workday（`medtronic.wd1.myworkdayjobs.com`） | 站点自身使用的公开 JSON 端点（列表 + 详情）；`jobs.medtronic.com` 301 到此域 | `id`（不透明 32 位）1.00 | `startDate` → `SOURCE_DATE` 1.00 | 详情 JSON `jobDescription` 1.00 | `Allow: /MedtronicCareers/`，robots 自行公布 sitemap | **VERIFIED**（**全量** 994） |
| **GE HealthCare** | Phenom（`careers.gehealthcare.com/global/en`） | robots 公布的 `sitemap_index.xml` → **1,035** 个职位 URL；职位页含 `JobPosting` JSON-LD | JSON-LD `identifier.value`（如 `R4045928`）1.00 | `datePosted` → `SOURCE_DATE` .91 | JSON-LD 全文描述 .91 | 仅禁 `*/apply`、`*/jobcart`、`*/chatbot` 等交互路径 | **VERIFIED**（有界样本 80/1,035） |
| **Philips** | Phenom（`www.careers.philips.com`） | sitemap → **805** 个职位 URL；职位页含 JSON-LD | `identifier.value`（如 `594302`）1.00 | `datePosted` → `SOURCE_DATE` .95（另有 00:00:00 时间戳渲染，按 `SOURCE_DATETIME` 原样保留并备注日精度） | JSON-LD 全文描述 .95 | **无可用 robots.txt**：`/robots.txt` 返回 200 `text/html` 的 SPA 外壳（无 REP 指令）→ 按 RFC 9309 §2.3.1.3「不可用即无限制」处理，**并原样记录，不写成「明确允许」** | **VERIFIED**（有界样本 80/805） |
| **Dräger** | 官方电子招聘门户 `erecruitment.draeger.com` + Beesite 搜索 JSON | 门户 + sitemap（213 locs / **171** 个在职岗位 URL）+ 每页 `JobPosting` JSON-LD | 门户 URL id（如 `19717`）/ JSON-LD `J000019717` 1.00 | `datePosted` → `SOURCE_DATE` 1.00 | JSON-LD 全文 .96 | 门户 robots：仅一行 `Sitemap`，无 Disallow；Beesite 主机 robots 404（不可用，已记录） | **VERIFIED**（有界样本 80/171） |
| **Mindray** | 北森 Beisen（`mindray.zhiye.com`） | 官方 JSON：`POST /api/Jobad/GetJobAdPageList`（141 社招）+ `GET /api/JobAd/GetJobAdInfo` | `Id`（GUID）1.00 | `PostDateInt`（epoch ms）→ UTC 1.00；`PostDate`（UTC+8）原样保留并核对一致 | `Duty` + `Require` 1.00 | `User-agent: * / Allow: /` | **VERIFIED**（有界样本 80/141） |

**结论**：五家企业**全部**找到了合法、稳定、可核实的公开路线（`VERIFIED`）。
这与 D-031 记录的「Wayback 历史路线只能覆盖 1/5」是**不同的路线、不同的结论**：
本轮是**实时前瞻采集**，不是历史归档重建。

**但这不等于「五家研究已完成」**：四家仍是有界样本（各 80 条），只有 Medtronic 做了全量（994 条）。
覆盖率分母：GEHC 1,035 / Philips 805 / Mindray 141（社招）/ Dräger 171（当前在聘）。

---

## 3. Medtronic：从「能访问」到「可核实的观察」（本轮唯一走完全链路的企业）

| 问题 | 实测答案 | 证据 |
|---|---|---|
| 列表分页 | `limit` 上限 20（>20 返回 400）；`offset` 翻页 | `probe_workday_paging.json` |
| 分页陷阱 | **`total` 只在 offset=0 出现**，后续页 `total: 0` 但仍返回 20 条 → 信任 `total` 会在第 2 页停止，把 994 条读成 40 条 | 同上；回归测试 `test_listing_pagination_does_not_stop_when_total_is_only_reported_once` |
| 站点自报总量 | 994（同一站点 20 分钟内从 992 变 994，见 §6） | `collection_medtronic.json` |
| 一次全量采集 | 50 个列表页 + 994 次详情 = **1,045 次请求**，0 失败 | 同上 |
| 唯一 ID | `id`（32 位不透明 id）可用率 **1.00**；`jobPostingId` 是含标题的 slug（改标题会变，故**不作身份**）；`jobReqId` 是需求号（可跨多城/多岗位） | `snapshot_profile_medtronic.json` |
| 来源发布日期 | `startDate`（ISO 日期）可用率 **1.00**，质量全部 `SOURCE_DATE`；相对串 `postedOn:"Posted 29 Days Ago"` 同时保留为 `source_posted_raw`，**不换算成日期** | 同上 |
| 描述 / 地点 | 可用率均为 **1.00** | 同上 |
| 法律实体 | 可用率 **0.00** —— 招聘页只写品牌名，不写雇佣法人实体 | 同上（结论，不是缺陷） |
| 重复 | 994 行 = 994 个唯一 ID（第二次全量已无分页重复；第一次有 2 行重复） | 同上 |

**因此 Medtronic 的岗位是「可核实观察」而不是「抓到的文本」**：每条有来源 ID、来源日期及其精度、
可定位的描述、来源 URL、以及我们自己的 `first_seen_at`。

---

## 4. robots / 自动化访问条款：逐主机记录

| 主机 | robots 状态 | 与本任务相关的规则 | 判定 |
|---|---|---|---|
| `medtronic.wd1.myworkdayjobs.com` | 200 | `Allow: /MedtronicCareers/`；`Disallow: /RedeploymentMedtronicCareers/`、`/refreshFacet/`；公布 `Sitemap` | 允许（采集只用 `/wday/cxs/...`，未被 Disallow 命中） |
| `jobs.medtronic.com` | 不可读（TLS 证书不匹配 `SEC_E_WRONG_PRINCIPAL`） | — | 不采集该主机（其 301 到 Workday 域即可） |
| `careers.gehealthcare.com` | 200 | 禁 `*/apply`、`*/jobcart`、`*/chatbot` 等交互路径 | 职位页/列表页允许 |
| `www.careers.philips.com` | **返回 SPA 外壳而非 robots** | 无 REP 指令 | 按「不可用 → 无限制」处理并**原样记录**；同时确认页面 `<meta name="robots" content="index">`；本轮**未**审阅其法律条款全文，已在 `EXTRAS` 声明 |
| `mindray.zhiye.com` | 200 | `Allow: /` | 允许 |
| `erecruitment.draeger.com` | 200 | 仅 `Sitemap:` 一行 | 允许 |
| `www.draeger.com` | 200 | `Disallow: /*api/` | 主页可读；本任务不使用该 CMS 的 API |

**代码层面的强制**：`medradar/recruitment/politeness.py` 在采集前**断言** robots 允许目标路径，
否则抛 `PermissionError` 并写 `BLOCKED` 记录；robots 取不到（非 200）同样拒绝采集。
由 `tests/test_recruitment_records.py::test_collector_refuses_when_robots_disallows_the_needed_path` 保证。

---

## 5. 更正：Dräger 不是 `SOURCE_UNAVAILABLE`（第一轮结论被本轮深查推翻）

第一轮探测（`probe_careers.py`）只看了企业官网，得到：`www.draeger.com/en/careers` 超时、
`career.draeger.com` 与 `draeger.taleo.net` DNS 不解析 → 当时判为 `BLOCKED`。
**深查后发现这个判断是错的**，原因有两层，必须分开写：

| 现象 | 实测（精确） | 归因 |
|---|---|---|
| `www.draeger.com/en/careers` | 脚本 UA：无 HTTP 状态，`TimeoutError` 20,233 ms（更早一次 90,030 ms 也超时） | **客户端被 bot 管理拦停**（Akamai），不是页面不存在 |
| 同一 URL，curl 默认 UA | **404**，106 ms | 该路径**确实是 404**（源站属性） |
| 同一 URL，真实 Chromium | **HTTP 404 "Page not found"** | 确认是 404（源站属性） |
| 真正的招聘板 | `erecruitment.draeger.com`：根 200、robots 200（仅 Sitemap 一行）、sitemap 200（213 locs / **171** 个在职岗位）、职位页 200（~120 KB，含 JSON-LD） | **合法公开路线存在** |
| `career.draeger.com`、`draeger.taleo.net` | DNS 不解析 | 历史/猜测主机不存在（D-031 记录的 Taléo 主机已消失） |

**教训（已写入协议）**：「官网某路径超时」不能直接推出「该企业没有可用的公开招聘数据」。
本轮把「网络不可达」「bot 拦停」「页面 404」「路线根本不存在」四种情况分开记录，
并且**没有尝试绕过** bot 管理——只是换到了企业自己公开的门户。

---

## 6. 采集与去重稳定性（同一来源重复观测的实测结果）

| 检查 | 方法 | 结果 |
|---|---|---|
| 小样本重复采集 | `stability_check.py`：同一天连续两次各 200 条 | 身份重叠 **1.00**；内容哈希一致 **1.00**；`first_seen_at` **100% 未被覆盖** |
| 全量重复采集 | 20 分钟内两次全量（`snapshot_stability_full.json`） | 身份重叠 **1.00**；**0 条消失**；**2 条新增**（站点自报总量 992 → 994） |
| 内容哈希跨运行比较 | 两次全量 | **明确标记为不可比较**：第一次是在旧哈希规则（`normalise_text`）下生成的，第二次是 `canonical_ws` 规则。跨规则比较会把「我们改了一行代码」报成「992 条描述同时被修改」——这正是 `hash_rule_version` 与 `HASH_RULE_REBASELINED` 状态存在的原因 |

**读法**：这证明的是**采集链路稳定**，不是**招聘需求稳定**。20 分钟内的 2 条新增不能当流量或趋势。

---

## 7. 与 D-028/D-029/D-031 的关系（不得重包装失败方案）

* D-029/D-030/D-031 的结论是：**Wayback 历史路线覆盖率不足**，五家目标企业中只有 Medtronic 可用。
* 本轮**没有**重新使用 Wayback，也没有把历史归档路线包装成新成果。
* 本轮改变的是方向：**历史回填 → 前瞻性实时采集**，并证明五家都有合法稳定路线。
* 仍未改变的是：**四家只有 80 条有界样本**，覆盖率分母 1,035 / 805 / 141 / 171 我们并未取全；
  「五家企业研究已完成」仍然是错的表述。

---

## 8. 附：请求预算

| 阶段 | 请求数 | 说明 |
|---|---:|---|
| 第一轮来源探测（五家） | 23 | 每主机 ≥1.2 s 间隔 |
| 深查（四家） | 35 | `deep_probe.py`，`source_probe_<company>.json` 逐条记录 |
| Workday 端点验证 + 分页测量 | 30 | 见两个 probe JSON |
| Medtronic 全量采集 ×2 | 2 × 1,045 | 0 失败 |
| GEHC / Philips / Mindray / Dräger 有界采集 | 85 / 84 / 6 / 83 | 各 80 条 |
| 稳定性小样本（2×200） | ≈420 | `stability_check.py` |

所有请求均在 robots 允许范围内（或已按 RFC 9309 处理「robots 不可用」并记录），
均为**无需认证**的公开页面/公开 JSON，未绕过任何访问控制，未采集任何应聘者个人数据。
