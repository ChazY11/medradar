# FINAL-PREFLIGHT-001 / 候选与生产的版本身份

- 复核时间：2026-11-19 04:16–04:40 CST（2026-11-18 20:16–20:40 UTC）
- 原则：**不靠文本文件判断版本**。内容指纹 + 运行进程路径 + 应用响应三路互证。

---

## 1. 身份结论

| 对象 | SHA | 怎么确认的 |
| --- | --- | --- |
| **候选代码冻结** | `55b269e`（`medradar/` 最后一次修改；其后的提交只含文档与工具） | `git diff --stat 55b269e HEAD -- medradar web config scripts` 为空 |
| **候选的代码内容** | 与 staging 部署目录逐字节一致 | 第 2 节 |
| **生产运行** | `14eaf615` | 1,759 个文件指纹全等 + 进程 cwd + 实际 import 路径 |

### 1.1 本轮 HEAD 的变化

| 提交 | 内容 | 为什么 |
| --- | --- | --- |
| `b6f4506` | 证据抽屉与 Feed 显示同一个判定 | 浏览器验收发现的发布阻塞（见 `RELEASE_BLOCKERS.md`） |
| `55b269e` | 健康探针不把自己锁死；WAL 目录写权限；崩溃时写 UNKNOWN | 故障注入发现的两个监控缺陷 |

起草预算时 HEAD 是 `58067da`；这两个提交都是**发布阻塞修复**，不是新功能。

---

## 2. 候选内容与 staging 部署的一致性

`staging/release-b6f4506…` 是导出包解压的结果；本轮的探针与工具不随发布目录走
（探针在 `release-gate/001/health/`，用 `MEDRADAR_CODE_ROOT` 指向发布目录）。
代码层面的差异只有一处已知的**预期差**：

```
staging release dir : b6f4506（导出于该提交）
HEAD                : 55b269e（在其上增加了 docs/ 与 health/ 探针，medradar/ 未变）
```

证据：

```
$ git diff --stat b6f4506 55b269e -- medradar web config scripts
(空)
```

也就是说：**staging 里跑的 `medradar/` 代码与 HEAD 完全相同**，本轮只改了发布外围
（探针、单元、文档、回滚工具）。

---

## 3. 生产身份：三路互证（重新做了一遍）

### 3.1 内容指纹

```
$ python3 verify_tree.py expected-14eaf61.txt /srv/medradar/radar/releases/14eaf615…
identical: 1759
missing:   0
mismatched: 0
```

### 3.2 运行进程

```
web   pid=681920 cwd=/srv/medradar/radar/releases/14eaf615…
sched pid=681928 cwd=/srv/medradar/radar/releases/14eaf615…
```

### 3.3 应用响应

```
$ curl /healthz            -> 200 {"status":"ok","service":"medradar-radar-alpha"}
$ curl /api/radar/health    -> 401（Alpha 门在回环上也生效，符合设计）
```

---

## 4. 功能清单核对（任务书第二节）

| # | 要求 | 是否包含 | 证据 |
| --- | --- | --- | --- |
| 1 | 当前真实 Git HEAD | — | `55b269e` |
| 2 | RELEASE-GATE-001 的迁移中断修复 | ✅ | `e4aaff6` 是 HEAD 的祖先；`test_radar_migration_resume.py` 2 项通过 |
| 3 | `advance()` 收敛修复 | ✅ | `388c115`；`test_radar_advance_convergence.py` 9 项通过 |
| 4 | 健康状态四态聚合 | ✅ | `388c115` + `f2f70dd`；`test_radar_health_verdict.py` 14 项通过 |
| 5 | V1 召回通道 | ✅ | `300a864`；staging 实采 6,563 条召回 |
| 6 | 历史档案与情报视图分离 | ✅ | Feed 四个视图（最新发现/最新观察/历史资料库/待核实）+ 卡片上的 `historical backfill` 标记 |
| 7 | 服务器实际运行 SHA | — | `14eaf615` |
| 8 | staging 与生产独立 | ✅ | 独立数据目录、独立端口 8792 vs 8791、独立写入者（`medradar-staging-*` 单元） |

### 4.1 "历史档案与情报视图分离"的实测证据

浏览器里看到的分层（staging，16,253 条观测）：

```
tab "Newly published (47)"   ← 来源在窗口内公开的
tab "Newly observed (8168)"  ← MedRadar 在窗口内首次看到的（可能是旧文档）
tab "Archive (8006)"
tab "Needs review (162)"
卡片徽章：NEW / historical backfill / 维度（source·domain·relevance·confidence·date precision）
```

一条 2026-10-09 公开的召回在"最新观察"里显示 `historical backfill`，且抽屉里
`Discovery phase: HISTORICAL_BACKFILL` —— 历史记录不会冒充最新情报。

---

## 5. staging 与生产的隔离（逐项）

| 维度 | 生产 | staging |
| --- | --- | --- |
| 代码目录 | `releases/14eaf615…` | `release-gate/001/staging/release-b6f4506…` |
| 数据 | `/srv/medradar/data/radar/radar.db`（v2，8,360 条） | `release-gate/001/staging/data/radar.db`（v3，16,253 条） |
| 端口 | 127.0.0.1:8791 | 127.0.0.1:8792 |
| 写入者 | `medradar-radar-scheduler` | `medradar-staging-scheduler` |
| 单元 | `medradar-radar-*` | `medradar-staging-*`（本轮新增，未触碰生产单元） |
| 认证 | Alpha 门（生产凭据） | Alpha 门（**临时**测试凭据，见 §6） |

**两个写入者不会碰同一个库**：`radar.db.lock` 单写者锁 + 不同目录；本轮实测 staging 与生产
同时运行，生产库行数 delta 为 0（见 `FINAL_DECISION.md` §证据）。

---

## 6. 认证环境说明（不泄露凭据）

- 生产门：Basic over TLS，PBKDF2 哈希存于 `/etc/medradar/radar-alpha.env`（本轮只读变量名，未读值）。
- staging 门：为本轮浏览器验收**临时生成**的独立凭据（`release-gate/001/staging/secrets/alpha.env`，
  0600，`medradar` 属主，**不入 git**）。
- 该凭据只对 127.0.0.1:8792 有效，通过 SSH 隧道从本机访问；测试结束后已停用 staging 门并计划轮换。
- 截图与日志中未出现凭据值（浏览器地址栏显示的是 `127.0.0.1:8792/radar`，无 userinfo）。

---

## 7. 结论

- 候选身份明确：`55b269e`，其 `medradar/` 代码与 staging 运行的一致。
- 生产身份明确：`14eaf615`，三路互证，未变。
- 两侧完全隔离：目录、端口、数据库、写入者、单元、凭据。