# FINAL-PREFLIGHT-001 / 发布阻塞项状态

三个指定阻塞项 + 过程中新发现并修复的阻塞项。

---

## 1. 三个指定阻塞项

| # | 阻塞项 | 状态 | 证据 |
| --- | --- | --- | --- |
| 1 | 真实浏览器验收 | **已关闭** | 19 项交互全部通过；Console 0 错误；`BROWSER_E2E.md` |
| 2 | 切换后回滚的数据保护 | **已关闭** | 12 步演练；重放后 3/3 记录逐字段一致；恢复 0.55 s；`ROLLBACK_DRILL.md` |
| 3 | 健康监控在隔离环境实装 | **已关闭** | systemd 服务 + 2 分钟定时器已安装；6 类故障全部识别；`FAULT_INJECTION_RESULTS.md` |

---

## 2. 过程中发现并修复的发布阻塞

### B1. 证据抽屉与 Feed 互相矛盾（浏览器验收发现）

| 项 | 内容 |
| --- | --- |
| 现象 | 卡片显示判定维度，抽屉却说 "No qualification decision is recorded for this observation yet" |
| 根因 | `/intelligence/{id}` 用 `observation_row()`（不含 `admission`），`_event()` 读 `row["admission"]` 恒为 None |
| 影响 | 读者核验"为什么这条在我面前"的唯一入口失效 → 核心流程故障 |
| 修复 | `b6f4506`：新增 `ledger.current_admission()`，详情端点显式附加 |
| 测试 | `test_the_evidence_drawer_reports_the_same_decision_as_the_feed` |
| 验证 | API：`decision=FEED, tier=HIGH_RELEVANCE, 9 个 dimension keys`；浏览器："Why this record is here" 显示 Relevant + 三条理由 + score |

### B2. 健康探针把自己锁死（故障注入发现）

| 项 | 内容 |
| --- | --- |
| 现象 | 探针连续运行几次后收到 HTTP 429，把健康系统判成 UNHEALTHY |
| 根因 | 每轮都请求受 Alpha 门保护的 API，门把每次 401 计为认证失败并锁定来源地址 |
| 影响 | 误报 + 可能连带锁定同 IP 的真实用户 |
| 修复 | `55b269e`：定时探针不调用受门保护的 API；用 `/healthz` + 账本直读；带认证探针改为手动可选 |

### B3. WAL 账本只读打开也需要目录写权限（故障注入发现）

| 项 | 内容 |
| --- | --- |
| 现象 | 探针报 `unable to open database file`，把健康系统判成 UNHEALTHY |
| 根因 | SQLite WAL 模式下即使 `mode=ro` 也要创建 `-shm`；单元 `ProtectSystem=strict` 且缺 `ReadWritePaths` |
| 修复 | 单元加 `ReadWritePaths=<data dir>`（探针不写业务数据） |

### B4. 探针崩溃会留下陈旧结论

| 项 | 内容 |
| --- | --- |
| 现象 | 探针抛异常时，磁盘上保留上一次的 DEGRADED/HEALTHY，看起来像"一切正常" |
| 修复 | 崩溃时写 `state: UNKNOWN` + `probe_error`，退出码 2 |

### B5. 新证据文件未登记到许可清单（治理门禁）

| 项 | 内容 |
| --- | --- |
| 现象 | `pytest` 全量出现 1 个失败：`inventory.coverage: tracked data file has no inventory entry` |
| 影响 | 治理门禁红灯，阻断"全绿"这一发布前提 |
| 处理 | 手工新增 3 条 `medradar_derived_artifacts / GREEN` 条目（15 行，只增不改） |
| 注意 | `check_licence.py --write-inventory` **会把已有的 13 条人工分类降级为 unclassified/RED**，本轮已回退该工具的自动重写，改为手工登记 |

---

## 3. 不构成阻塞、但必须记录的问题

| # | 问题 | 为什么不是阻塞 | 归属 |
| --- | --- | --- | --- |
| N1 | 英文界面混入中文（公司名、Knowledge-time 说明段） | 数据正确、导航可用；既有问题（`TechnologyMapPage.tsx` 未被本次候选改动） | 已知缺陷，后续修 |
| N2 | 26/62 个按钮某一维 < 44px（最小 26×31） | 0 个 < 24px，满足 WCAG AA；主控件均为 44px | 既有问题 |
| N3 | `/api/radar/graph/summary` 在回填后 1.15 s → 2.3 s | 2×2 实验证明是数据量而非代码；不在首屏关键路径 | 需在回填后观察，必要时加缓存 |
| N4 | 无外部通知渠道 | 任务允许"先实现可观察的故障记录，并把外部告警标记为未完成" | 明确标记未完成 |
| N5 | 公网入口是 Quick Tunnel 临时域名 | 与本次代码发布无关，属于试验运营 | 试验前决策 |
| N6 | 周报生成器仍以文献为主、模板化 | 内容质量问题，非发布阻塞；由人工取舍兜底 | 产品迭代 |
| N7 | 服务器重启后的依赖行为未测 | 不许重启生产机 | 未验证项 |

---

## 4. 仍然存在的"发布时必须同时做"的事项

这些不是代码阻塞，但**如果切换时不一起做，等于把能力关在盒子里**：

| # | 事项 | 状态 |
| --- | --- | --- |
| 1 | 安装生产健康监控（`medradar-radar-health.service/.timer`） | 单元已备好，未安装 |
| 2 | 首次 `advance` 会重判 8,360 条（约 12 s） | 已量化，需在观察期确认 |
| 3 | 召回通道首次回填（+206 MB，图谱 23k→45k） | 已量化，需接受或先关闭该源 |
| 4 | 备份目录统一（`data/radar/backups` 与 `/srv/medradar/backups/radar`） | 未处理 |
| 5 | 回滚前必须先复制 v3 库（否则重放无从谈起） | 已写入 Runbook §7.2 |

---

## 5. 结论

三个指定阻塞项全部关闭；过程中新增的 5 个阻塞（B1–B5）全部修复并验证。
剩余 7 项为已记录的已知缺陷/未验证项，均不在任务书定义的 NO-GO 判据内。
